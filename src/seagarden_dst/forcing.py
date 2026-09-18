"""Site conditions and seasonal forcing.

In the scaffold these are entered by hand or generated from a simple seasonal
climatology. In the delivered tool they are read from the curated layers of
specification section 6 (Copernicus reanalysis, EMODnet, HELCOM) for a drawn
polygon, via the optional `spatial` extra.

The interface between the two is deliberately narrow - `SiteConditions` and the
two-method `ForcingSource` protocol - so that swapping the stub for the real data
layer touches nothing in `growth`, `shellfish`, `nutrients` or `suitability`.
"""

from __future__ import annotations

import math
import numbers
from dataclasses import dataclass, fields
from datetime import date
from enum import StrEnum
from typing import Protocol, runtime_checkable

import numpy as np

# Sub-regions used for calibration lookup. These are coarse on purpose: they are
# calibration domains, not a spatial index.
REGIONS = {
    "LT-coastal": "Lithuanian coastal waters",
    "LT-lagoon": "Curonian Lagoon, Lithuanian side",
    "PL-coastal": "Polish coastal waters",
    "PL-lagoon": "Szczecin Lagoon",
    "DE-coastal": "Mecklenburg-Vorpommern coastal waters",
    "DK-belt": "Great Belt",
    "EE-coastal": "Estonian coastal waters (OLAMUR pilot)",
}


@dataclass(frozen=True)
class SiteConditions:
    """Environmental summary for one site.

    Units follow the sources: salinity in psu, temperature in degrees C, irradiance
    at cultivation depth in umol photons/m2/s, dissolved inorganic nitrogen in
    umol N/L, depth and wave height in m.
    """

    region: str | None
    salinity_psu: float
    mean_temp_c: float
    summer_temp_c: float
    winter_temp_c: float
    #: Surface PAR. NO SOURCE EXISTS for this field: package B established that the
    #: Copernicus Baltic BGC reanalysis carries no PAR variable of any kind, so unlike
    #: every other field here this one does NOT become a measurement when the data layer
    #: lands - it stays a placeholder constant that the tool has to say it is using.
    surface_par: float
    din_umol_l: float
    dip_umol_l: float
    depth_m: float
    significant_wave_m: float
    #: Beer-Lambert attenuation coefficient. Package B identified the source the design
    #: did not have: Secchi depth (`zsd`) via Poole-Atkins, k ~= 1.7 / z_SD, which makes
    #: this a DERIVED quantity rather than a measured layer when package D wires it. The
    #: 0.4 default is roughly twice the 0.198 measured at Tagalaht; it is left alone here
    #: because changing it moves every reported number.
    light_attenuation_k: float = 0.4
    cultivation_depth_m: float = 1.5

    def __post_init__(self) -> None:
        """Refuse a site whose conditions are not finite, at construction.

        A land cell in a gridded product gives NaN for every variable. Nothing
        downstream treats that as an error on its own: the tolerance tests compare
        against NaN and return False, so a NaN site passes them; the salinity-indexed
        yield multiplies through to NaN; and `solve_ivp` shrinks its step forever
        rather than raising. The result was a harvest of `nan` kg DW carried at a
        reportable tier, which the interface renders as a number with a calibration
        badge — a land cell reading as an assessable site.

        This is checked here, and not in each consumer, because `SiteConditions` is
        the one object they all share: `contraindication`, `salinity_indexed_yield`,
        `simulate` and the forcing series are every one of them derived from it. A
        frozen dataclass cannot be constructed OR `dataclasses.replace`d into an
        invalid state, so the guarantee is inherited by construction rather than by
        each caller remembering — including by package D's `GriddedForcing`, which
        does not exist yet.

        `require_finite_series` below remains, and is a different precondition: a
        source may hand back a non-finite SERIES built from finite site conditions.
        """
        bad = []
        for field in fields(self):
            value = getattr(self, field.name)
            # `numbers.Real`, NOT `(int, float)`. `np.float64` subclasses Python's
            # `float` and was caught; `np.float32` does not subclass it and was not —
            # and float32 is what every variable in the artifact is stored as, so the
            # one dtype this guard's docstring is about was the one it let through.
            # numpy registers its scalar types with the numbers ABCs, so `numbers.Real`
            # catches both widths and still excludes `str`.
            if isinstance(value, numbers.Real) and not math.isfinite(value):
                bad.append(f"{field.name}={value}")
        if bad:
            raise ValueError(
                f"site conditions for region {self.region!r} contain non-finite "
                f"values ({', '.join(bad)}). This usually means the coordinate "
                f"resolved to a land cell in the gridded product — check the "
                f"coordinate, because nothing downstream will reject it."
            )

    def par_at_depth(self) -> float:
        """Beer-Lambert attenuation to the cultivation depth."""
        attenuated = np.exp(-self.light_attenuation_k * self.cultivation_depth_m)
        return float(self.surface_par * attenuated)


class SiteProvenance(StrEnum):
    """How much a site coordinate is actually known.

    The same idea as `calibration.Tier`, for position rather than parameters: a
    coordinate that travels without saying where it came from gets promoted to a fact.
    All three values below were recorded in comments before this existed, which package D
    cannot read — a consumer holding a coordinate had no way to tell a default from a
    decision.
    """

    SITED = "sited"            # a position somebody chose and confirmed
    SNAPPED = "snapped"        # nearest valid cell to a position somebody gave
    INDICATIVE = "indicative"  # a representative cell of the right water, chosen not derived

    @property
    def label(self) -> str:
        return {
            SiteProvenance.SITED: "Sited",
            SiteProvenance.SNAPPED: "Snapped to the nearest modelled cell",
            SiteProvenance.INDICATIVE: "Indicative of the water body",
        }[self]

    @property
    def presentation(self) -> str:
        """What a result computed at this coordinate may claim to be about.

        Mirrors `Tier.presentation`, and for the same reason: the flag is only worth
        carrying if it tells a caller what it is allowed to say.
        """
        return {
            SiteProvenance.SITED: "result for the named site",
            SiteProvenance.SNAPPED: (
                "result for the nearest modelled cell, with its distance and depth named"
            ),
            SiteProvenance.INDICATIVE: (
                "result labelled indicative of the water body, not of a site"
            ),
        }[self]

    @property
    def is_sited(self) -> bool:
        return self is SiteProvenance.SITED


@dataclass(frozen=True)
class SiteCoordinate:
    """Where a site is, and how well that is known.

    Deliberately NOT a (lat, lon) tuple. It was one, and unpacking let a consumer take
    the numbers and drop the provenance silently — which is the failure this type exists
    to close, so `lat, lon = coordinate` now raises.
    """

    lat: float
    lon: float
    provenance: SiteProvenance
    #: Model depth at the cell, m. From the static mask, not a survey.
    depth_m: float | None = None
    #: When the cell was last checked against the land-sea mask.
    checked_on: date | None = None
    #: Why this position and not another — the part no enum can carry.
    note: str = ""

    @property
    def is_sited(self) -> bool:
        return self.provenance.is_sited


class Coverage(StrEnum):
    """Whether the artifact has data for a query, and if not, why not (§6.2).

    Read from the artifact's `valid` field, NEVER inferred from NaN. C§3.5 added that
    field precisely because inferring validity from NaN is unreliable, and the committed
    fixture proves it: its invalid cell holds finite values, so a NaN-inferring reader
    would return conditions for a cell the mask excludes.
    """

    VALID = "valid"
    CELL_INVALID = "cell_invalid"   # blocks; the distance to the nearest valid cell is reported
    YEAR_ABSENT = "year_absent"     # blocks; never substitutes another year


class Aggregation(StrEnum):
    """How a reading's numbers were produced from the cells under the polygon.

    Recorded on the reading so package D-b replaces a NAMED method rather than silently
    changing what every multi-cell result meant.
    """

    CONTAINING_CELL = "containing_cell"      # farm scale - the normal case (§6.2)
    UNWEIGHTED_MEAN = "unweighted_mean"      # provisional, multi-cell - package D-a
    SALINITY_WEIGHTED = "salinity_weighted"  # the Maar et al. port - package D-b


@dataclass(frozen=True)
class SiteQuery:
    """Where and when to read.

    `geometry_wkt` is a WKT string, not a `shapely` geometry: shapely lives in the
    `spatial` extra and this type is read by the model core. An empty string means
    "use the region's coordinate", which is the placeholder path.
    """

    geometry_wkt: str
    year: int
    region: str | None = None


@dataclass(frozen=True)
class SiteReading:
    """Conditions, and everything a caller needs to know about how far to trust them.

    Deliberately not `SiteConditions | None`. A bare `None` says nothing about why it is
    None or how far away data is, and §6.2 requires the distance to be surfaced — the
    same reasoning that makes `SiteCoordinate` refuse to be unpacked.
    """

    conditions: SiteConditions | None
    coverage: Coverage
    year: int
    aggregation: Aggregation
    #: Great-circle distance to the nearest valid cell, km. Set when coverage blocks.
    nearest_valid_km: float | None = None
    #: False for the placeholder. §7's banner reads this rather than guessing.
    from_artifact: bool = False
    #: Age of the artifact in months, for §7's 18-month staleness note.
    stale_months: int | None = None

    @property
    def is_assessable(self) -> bool:
        return self.conditions is not None


#: Where a site IS, as opposed to what the conditions there are — the coordinate package D
#: will use to index the artifact. Kept apart from `SiteConditions`, which is a summary of
#: conditions and carries no position, and apart from the website's `data/pilots.yaml`,
#: which carries town markers for a map.
#:
#: Package B checked all four published pilot coordinates against the Copernicus land-sea
#: mask and every one is a LAND cell: they are map pins, correct for a map and unusable for
#: assessment. A coordinate here has to index a valid cell of the artifact.
#:
#: **Absent, not None.** Regions with no site have no key. A None or a (0, 0) would be a
#: coordinate-shaped value that code can index and get a wrong answer from.
#:
#: **Nothing here is SITED yet.** Two were snapped from a pin somebody gave; one is a
#: representative cell nobody gave. Read `.provenance` before presenting any result.
SITE_COORDINATES: dict[str, SiteCoordinate] = {
    "DK-belt": SiteCoordinate(
        lat=55.4416, lon=10.6804,
        provenance=SiteProvenance.SNAPPED,
        depth_m=11.2, checked_on=date(2026, 9, 16),
        note=(
            "Kerteminde, Great Belt side. The farm's own position (55.4499, 10.6488) is "
            "the harbour, whose containing cell is land at 1.86 x 1.75 km; this is the "
            "nearest sea cell, 2.20 km east. Package B warned that snapping selects the "
            "shallowest, most enclosed water near a town: the previously published pin "
            "snapped into Kerteminde Fjord at 3.1 m, and this cell is on the open belt "
            "instead, which is what the corrected pin bought."
        ),
    ),
    "DE-coastal": SiteCoordinate(
        lat=54.1916, lon=12.0971,
        provenance=SiteProvenance.SNAPPED,
        depth_m=8.5, checked_on=date(2026, 9, 16),
        note=(
            "Warnow mouth, off Rostock. Byte-identical to the nearest-sea-cell value "
            "package B derived for the Rostock pin, which sat 11.04 km inland up the "
            "Warnow — so nobody chose this position, snapping did. It is the river plume "
            "at 8 umol/L DIN and 10.6 psu, the clearest case of the bias package B "
            "described. Deeper, less river-influenced water is close by: 11.3 m at 2.6 "
            "km, 12.9 m at 4.1 km, 17.8 m within 12 km. Expect this to MOVE if the pilot "
            "is sited offshore, rather than to be confirmed."
        ),
    ),
    "PL-lagoon": SiteCoordinate(
        lat=53.8416, lon=14.4859,
        provenance=SiteProvenance.INDICATIVE,
        depth_m=4.0, checked_on=date(2026, 9, 16),
        note=(
            "Szczecin Lagoon, Wolin National Park side. Weaker than the two above: no "
            "lagoon pin existed before 2026-09-16, so there was nothing to snap from and "
            "this cell was chosen, then verified. The model does resolve the lagoon — 120 "
            "sea cells at 3.1-5.0 m, matching its real bathymetry. The cells at "
            "53.94-53.96 N are the Swina channel at 8-10 m, a different water body; do "
            "not drift north into them. The shallow, enclosed, river-influenced water "
            "package B warned snapping selects by accident is, here, the site itself."
        ),
    ),
    "PL-coastal": SiteCoordinate(
        lat=54.5249, lon=18.5692,
        provenance=SiteProvenance.SNAPPED,
        depth_m=7.6, checked_on=date(2026, 9, 16),
        note=(
            "Open coast off Gdynia. Byte-identical to the nearest-sea-cell value package "
            "B derived for the Gdynia pin, 2.59 km away — so like DE-coastal, snapping "
            "chose this position rather than anybody else. Unlike DE-coastal it is the "
            "BENIGN case: package B called it 'open coast — the only realistic one' of "
            "the four cells it snapped, against a 3.1 m fjord at DK, a river plume at DE "
            "and a near-fresh lagoon cell at LT. Deeper water is close if the pilot goes "
            "further out: 11.5 m at 1.8 km, 17.9 m at 3.6 km, 33.9 m within 8 km. The "
            "provenance stays SNAPPED regardless — it records how the position was "
            "arrived at, not whether the water is any good."
        ),
    ),
    "LT-lagoon": SiteCoordinate(
        lat=55.672777, lon=21.133870,
        provenance=SiteProvenance.SITED,
        depth_m=3.1, checked_on=date(2026, 9, 16),
        note=(
            "The first SITED coordinate this tool has held, and the only one not arrived "
            "at by snapping. From KU Marine Research Institute's notification to the "
            "Curonian Spit National Park administration, signed 2026-06-12: 'Eksperimento vieta: "
            "vakarine Kursiu mariu pakrante 55.672777, 21.133870' — the western shore of "
            "the Curonian Lagoon. A 10 x 2 m installation of growing ropes on floats and "
            "anchors, or on stakes, cultivating Ulva intestinalis, 15 June to 30 October "
            "2026. A position the project chose, notified and is building on, not a cell "
            "a script picked. "
            "Its containing cell is SEA at 3.1 m, 0.62 km from the notified point, so it "
            "indexes the artifact directly and needs no snap. The shallow, near-fresh "
            "water is the site rather than an artefact of snapping: package B measured "
            "3.5 psu here, and Ulva intestinalis is the species chosen for it."
        ),
    ),
    #: LT-coastal: NOT SITED, and searched for rather than assumed. WP3's Lithuanian
    #: site-selection folder holds Site 1 (Klaipeda Strait) and Site 2 (northern Curonian
    #: Lagoon); only Site 2 has a coordinate anywhere, in the KNNP notification above.
    #: Site 1's photos carry no GPS EXIF, and the only Lithuanian pilot review
    #: (Chorda_Lithuania_pilot_review.docx) RECOMMENDS rather than sites: "a two-tier
    #: pilot: a land-and-strait-based nursery and instrumented micro-trial at Klaipeda
    #: (existing 'Sea Valley' infrastructure), paired with a small engineered, submerged
    #: longline trial on the open coast". A nursery at existing infrastructure and an
    #: open-coast longline are two different positions, and neither has been chosen.
    #: LT is two sub-sites, coastal and lagoon, and `LT-lagoon` is not in REGIONS yet.
}


#: Placeholder conditions per region, used by the scaffold so the application runs
#: end to end before the data layer exists. These are plausible order-of-magnitude
#: values, NOT measurements, and every result derived from them inherits tier C.
#:
#: One of them has since been checked. Package B pulled the Copernicus cell at Tagalaht
#: (58.5249 N, 22.2910 E), 2023-2025, against the EE-coastal entry below
#: (docs/2026-09-15-package-b-measurements.md):
#:
#:   salinity_psu          6.0  vs measured 5.86-6.78, mean 6.33   - good
#:   din_umol_l            5.5  vs measured  0.28-6.21, mean 1.05  - 5.3x HIGH
#:   light_attenuation_k   0.4  vs measured  0.15-0.34, mean 0.20  - 2.0x HIGH
#:
#: So "order of magnitude" holds, but only just, and the two errors pull the growth model
#: in opposite directions - less nitrogen, clearer water. The values are deliberately NOT
#: corrected here: changing them moves every reported number and the golden snapshot, and
#: replacing them wholesale is package D's job, not a hand-patch of one of six sites from
#: one cell of one product. Recorded so nobody reads "plausible" as "checked".
PLACEHOLDER_SURFACE_PAR = 420.0

PLACEHOLDER_SITES: dict[str, SiteConditions] = {
    "LT-coastal": SiteConditions(
        region="LT-coastal",
        salinity_psu=7.0,
        mean_temp_c=10.5,
        summer_temp_c=19.0,
        winter_temp_c=2.0,
        surface_par=420.0,
        din_umol_l=6.0,
        dip_umol_l=0.6,
        depth_m=12.0,
        significant_wave_m=1.1,
    ),
    #: Curonian Lagoon, Lithuanian side — added with the LT-lagoon region so
    #: `conditions_for` has an answer for it. UNLIKE its neighbours, two fields here are
    #: MEASURED rather than assumed: package B read 3.5 psu and 36 umol/L DIN from the
    #: Copernicus reanalysis in this lagoon, and depth 3.1 m is the static mask at the
    #: notified site's own cell. The rest is placeholder in the same sense as everything
    #: below — temperatures widened for a shallow lagoon, waves cut for a sheltered one,
    #: surface_par carried over because no source for it exists at all.
    #:
    #: The salinity is the point of the entry. At 3.5 psu this water is near-fresh, which
    #: is why `eutropy_adapter` refuses lagoon-to-coast transfers and why the site's
    #: species is Ulva intestinalis rather than a kelp.
    "LT-lagoon": SiteConditions(
        region="LT-lagoon",
        salinity_psu=3.5,        # measured, package B
        mean_temp_c=11.0,
        summer_temp_c=21.0,      # shallow water warms further than the open coast
        winter_temp_c=1.0,
        surface_par=420.0,       # no source exists for this field anywhere
        din_umol_l=36.0,         # measured, package B — the Nemunas load
        dip_umol_l=1.6,
        depth_m=3.1,             # static mask at the notified site's cell
        significant_wave_m=0.4,  # sheltered
    ),
    "PL-coastal": SiteConditions(
        region="PL-coastal",
        salinity_psu=7.5,
        mean_temp_c=10.8,
        summer_temp_c=19.5,
        winter_temp_c=2.2,
        surface_par=430.0,
        din_umol_l=7.0,
        dip_umol_l=0.7,
        depth_m=14.0,
        significant_wave_m=1.2,
    ),
    "PL-lagoon": SiteConditions(
        region="PL-lagoon",
        salinity_psu=2.0,
        mean_temp_c=11.5,
        summer_temp_c=21.0,
        winter_temp_c=1.5,
        surface_par=400.0,
        din_umol_l=25.0,
        dip_umol_l=1.8,
        depth_m=4.0,
        significant_wave_m=0.5,
        light_attenuation_k=1.1,
    ),
    "DE-coastal": SiteConditions(
        region="DE-coastal",
        salinity_psu=11.0,
        mean_temp_c=11.0,
        summer_temp_c=19.5,
        winter_temp_c=2.5,
        surface_par=430.0,
        din_umol_l=8.0,
        dip_umol_l=0.8,
        depth_m=10.0,
        significant_wave_m=0.9,
    ),
    "DK-belt": SiteConditions(
        region="DK-belt",
        salinity_psu=18.0,
        mean_temp_c=11.5,
        summer_temp_c=19.0,
        winter_temp_c=3.5,
        surface_par=440.0,
        din_umol_l=5.0,
        dip_umol_l=0.5,
        depth_m=16.0,
        significant_wave_m=0.8,
    ),
    "EE-coastal": SiteConditions(
        region="EE-coastal",
        salinity_psu=6.0,
        mean_temp_c=10.0,
        summer_temp_c=18.5,
        winter_temp_c=1.0,
        surface_par=410.0,
        din_umol_l=5.5,
        dip_umol_l=0.5,
        depth_m=8.0,
        significant_wave_m=0.9,
    ),
}


def day_of_year(month: int, day: int = 15) -> int:
    """Mid-month day number, no leap-year handling needed at this resolution."""
    cumulative = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    return cumulative[month - 1] + day


def daily_forcing(
    site: SiteConditions, window: tuple[int, int]
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Daily forcing series over the cultivation window.

    Returns (days, par, temperature, din) where `days` is the day-of-year axis.

    Seasonality is a simple sinusoid pinned to the site's winter and summer values,
    with irradiance peaking at the solstice and nutrients drawn down through the
    growing season - enough structure for the growth model to behave sensibly, and
    explicitly a placeholder for the Copernicus climatologies of section 6.

    A window whose end month precedes its start month wraps the year boundary - sugar
    kelp is deployed in autumn and harvested the following early summer. Such a window
    is handled by letting the day axis run past 365 rather than splicing two calendar
    segments: the seasonal term has period 365.25, so day 370 is already the same point
    in the season as day 5, and continuing the axis keeps the forcing continuous across
    New Year and the axis monotone for the interpolation in `growth.simulate`.

    Nitrogen is a property of the site and the date, not of the window asked about.
    It was not always: the drawdown used to be spread across however many days the
    window contained, so on 1 April at DK-belt this function returned 3.15 umol N/L
    for the Oct-Jun window and 5.00 for the April starts. It now shares the seasonal
    term with temperature and irradiance, so any two windows overlapping a date agree
    on it to within the phase residual of the 365.25-day period - about 1.8e-03
    relative across the Apr-Jun overlap, not zero.

    The values are still ASSUMED. The real seasonal cycle arrives with the section 6
    climatologies, and this change moved the modelled yields down: mu_max has never
    been fitted to the anchor - it carries its initial value, and b_max is set from
    the anchor's own upper bound, so the anchor is not an independent check either.
    """
    start, end = window
    first = day_of_year(start, 1)
    last = day_of_year(end, 28)
    if last < first:
        last += 365
    days = np.arange(first, last + 1, dtype=float)

    # Solstice-centred seasonal shape: 1 at midsummer (day 172), 0 at midwinter.
    season = 0.5 * (1.0 + np.cos(2.0 * np.pi * (days - 172.0) / 365.25))

    amplitude = 0.5 * (site.summer_temp_c - site.winter_temp_c)
    midpoint = 0.5 * (site.summer_temp_c + site.winter_temp_c)
    temperature = midpoint + amplitude * (2.0 * season - 1.0)

    par = site.par_at_depth() * (0.25 + 0.75 * season)

    # Nutrients by calendar day, not by position in the window. The previous
    # `np.linspace(1.0, 0.45, days.size)` spread a fixed drawdown across however many
    # days the window contained, so nitrogen was a property of the question asked: on
    # 1 April at DK-belt it returned 3.15 umol N/L for the Oct-Jun window and 5.00 for
    # the April starts. Highest in winter and lowest at midsummer is the Baltic
    # pattern - winter accumulation, spring-bloom drawdown.
    #
    # ASSUMED, not sourced, and replaced wholesale by the section 6 climatologies.
    # Note it is NOT amplitude-preserving within a window: the season term reaches 0
    # only at midwinter, so a window that never reaches midwinter sees less than the
    # full 0.450-1.000 range - Fucus's April-October spans 0.450-0.891. That is why
    # this change lowers the ODE yield of every window that stops short of midwinter,
    # which after the Saccharina yield-model change is every window still on the ODE.
    din = site.din_umol_l * (1.0 - 0.55 * season)

    return days, par, temperature, din


def require_finite_series(
    region: str | None,
    days: np.ndarray,
    par: np.ndarray,
    temperature: np.ndarray,
    din: np.ndarray,
) -> None:
    """Reject a forcing series the integrator cannot survive, before it reaches one.

    Package B fed `simulate` a series drawn from a land cell and nothing raised.
    `solve_ivp` does not error on a non-finite derivative; it shrinks the step until
    it underflows, so the run sat at 101% CPU producing nothing and read as a
    stiff-ODE performance problem. The cost was entirely in the diagnosis.

    This is the SERIES precondition - "are these numbers usable". It is called by
    `growth.simulate`, which is a CONSUMER of the protocol, not the protocol itself:
    an earlier version of this docstring claimed every source inherited it, and that
    was wrong. A Protocol cannot enforce a call, so a second consumer of
    `daily_forcing` - the shellfish path, a notebook, package D's polygon query -
    must call this itself.

    What IS inherited by construction is the SITE precondition on `SiteConditions`
    above, which no consumer can bypass because the dataclass cannot be built in an
    invalid state. That is the guard that closes the land-cell case; this one closes
    a source that returns a bad series from good site conditions. The SPATIAL
    precondition - "does this coordinate land on a valid cell, and how far is the
    nearest one" - remains the data layer's, answerable before any series exists.

    One NaN is rejected as firmly as all of them: the interpolation in `simulate`
    spreads a single hole across the derivative, and a part-filled series is the
    harder bug precisely because it looks populated.
    """
    suspect = {"days": days, "par": par, "temperature": temperature, "din": din}
    bad: dict[str, tuple[int, int]] = {}
    for name, values in suspect.items():
        array = np.asarray(values, dtype=float)
        finite = int(np.isfinite(array).sum())
        if finite != array.size:
            bad[name] = (finite, array.size)

    if not bad:
        return

    detail = ", ".join(f"{name}: {f}/{n} finite" for name, (f, n) in bad.items())
    raise ValueError(
        f"forcing series for region {region!r} contains non-finite values "
        f"({detail}). A series with no finite values usually means the site "
        f"coordinate resolved to a land cell in the gridded product - check the "
        f"coordinate before the integrator, because solve_ivp will not reject it."
    )


@runtime_checkable
class ForcingSource(Protocol):
    """Where site conditions and seasonal forcing come from.

    Widened by package D-a. `conditions_for(region)` became `reading_at(query)` because
    §7 requires a polygon outside every calibration domain to yield `region=None`, which
    the caller cannot know before the lookup; and `daily_forcing` gained a year because
    §6.2's measurement refutes the climatology — collapsing 2023-2025 into one costs
    -57% to +179% against the +17.4% monthly resolution buys.
    """

    def reading_at(self, query: SiteQuery) -> SiteReading: ...

    def daily_forcing(
        self, site: SiteConditions, window: tuple[int, int], year: int
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]: ...


class PlaceholderForcing:
    """The scaffold's invented conditions. Not measurements - see PLACEHOLDER_SITES."""

    def reading_at(self, query: SiteQuery) -> SiteReading:
        region = query.region
        if region is None or region not in PLACEHOLDER_SITES:
            raise KeyError(f"No placeholder conditions for region {region!r}")
        # Never blocks: there is no artifact, so there is no coverage to be missing.
        # That these numbers are invented is carried by the calibration tiers, not here.
        return SiteReading(
            conditions=PLACEHOLDER_SITES[region],
            coverage=Coverage.VALID,
            year=query.year,
            aggregation=Aggregation.CONTAINING_CELL,
            from_artifact=False,
        )

    def daily_forcing(
        self, site: SiteConditions, window: tuple[int, int], year: int
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        # `year` is ignored: the placeholder has one invented seasonal cycle, not one
        # per year. The parameter exists so GriddedForcing can satisfy the protocol.
        return daily_forcing(site, window)


#: The scaffold's forcing source. `growth.simulate`, `growth.harvest_biomass` and
#: `contracts.SiteContext.from_region` all take a `ForcingSource` defaulting to this,
#: so the section 6 data layer substitutes a `GriddedForcing` at the boundary without
#: any of those callers changing.
DEFAULT_FORCING: ForcingSource = PlaceholderForcing()
