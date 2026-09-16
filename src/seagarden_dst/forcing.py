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
from dataclasses import dataclass, fields
from typing import Protocol, runtime_checkable

import numpy as np

# Sub-regions used for calibration lookup. These are coarse on purpose: they are
# calibration domains, not a spatial index.
REGIONS = {
    "LT-coastal": "Lithuanian coastal waters",
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

    region: str
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
            if isinstance(value, (int, float)) and not math.isfinite(value):
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


#: Where a site IS, as opposed to what the conditions there are — the coordinate package D
#: will use to index the artifact. Kept apart from `SiteConditions`, which is a summary of
#: conditions and carries no position, and apart from the website's `data/pilots.yaml`,
#: which carries town markers for a map.
#:
#: That distinction is the whole reason this exists. Package B checked all four published
#: pilot coordinates against the Copernicus land-sea mask and every one of them is a LAND
#: cell: they are map pins, correct for a map and unusable for assessment. A coordinate here
#: has to index a valid cell of the artifact, so it is recorded deliberately rather than
#: borrowed from the map.
#:
#: **Absent, not None.** Three pilots are still `planned` and have no site. A None or a
#: (0, 0) would be a coordinate-shaped value that code can index and get a wrong answer
#: from; a missing key raises, which is the honest failure.
SITE_COORDINATES: dict[str, tuple[float, float]] = {
    #: Kerteminde, Great Belt side. SNAPPED, NOT SITED: the farm's own position
    #: (55.4499, 10.6488) is the harbour, and its containing cell is land at the grid's
    #: 1.86 x 1.75 km resolution. This is the nearest sea cell, 2.20 km east, depth 11.2 m
    #: — checked against cmems_mod_bal_phy_my_static on 2026-09-16. Replace it with the
    #: farm's actual grow-out position when that is known; 11.2 m is plausible for one,
    #: but nobody has said this is where it is.
    #:
    #: Package B's warning applies and is why the depth matters: snapping selects the
    #: shallowest, most enclosed water near a town. The previously published pin snapped
    #: into Kerteminde Fjord at 3.1 m, which the write-up called eutrophic and enclosed;
    #: this cell is on the open belt instead.
    "DK-belt": (55.4416, 10.6804),
    #: Warnow mouth, off Rostock. SNAPPED, NOT SITED, and more strongly so than DK-belt:
    #: this is not a position anybody chose, it is byte-identical to the nearest-sea-cell
    #: value package B derived for the Rostock pin, which sat 11.04 km inland up the
    #: Warnow (see docs/spikes/2026-09-15-package-b/06_download_sites.py). Verified SEA on
    #: 2026-09-16 against cmems_mod_bal_phy_my_static, depth 8.5 m, exact grid match.
    #:
    #: Package B's bias warning applies to this cell more than any other: snapping
    #: "systematically selects the shallowest, most enclosed, most river-influenced water
    #: available, because that is what lies closest to a town", and this one is a river
    #: plume at 8 umol/L DIN and 10.6 psu. Deeper, less river-influenced water is close by
    #: — 11.3 m at 2.6 km, 12.9 m at 4.1 km, 17.8 m within 12 km — so if the pilot is
    #: sited anywhere offshore, this value should move rather than be confirmed.
    "DE-coastal": (54.1916, 12.0971),
    #: Szczecin Lagoon, on the Wolin National Park side. INDICATIVE, NOT SITED — and that
    #: is weaker than the two above, which were at least snapped from a published pin.
    #: No lagoon pin existed before 2026-09-16: the site was added to the website that day
    #: on partner review, so there was nothing to snap from. This is a representative
    #: lagoon cell CHOSEN and then verified, not derived from a position anybody gave.
    #:
    #: Verified SEA against cmems_mod_bal_phy_my_static, depth 4.0 m. The model does
    #: resolve the lagoon — 120 sea cells in it, 3.1-5.0 m, which matches its real
    #: bathymetry — so the artifact will have values here. The cells at 53.94-53.96 N are
    #: the Swina channel at 8-10 m, a different water body; do not drift north into them.
    #:
    #: Note the lagoon is genuinely the shallow, enclosed, river-influenced water package B
    #: warned that snapping selects by accident. Here that is the site, not an artefact.
    "PL-lagoon": (53.8416, 14.4859),
    #: LT-coastal, LT-lagoon, PL-coastal: not sited yet.
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
    region: str,
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

    The interface is deliberately narrow - two methods - because swapping the
    placeholder for the section 6 data layer must touch nothing in growth, shellfish,
    nutrients or suitability.
    """

    def conditions_for(self, region: str) -> SiteConditions: ...

    def daily_forcing(
        self, site: SiteConditions, window: tuple[int, int]
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]: ...


class PlaceholderForcing:
    """The scaffold's invented conditions. Not measurements - see PLACEHOLDER_SITES."""

    def conditions_for(self, region: str) -> SiteConditions:
        if region not in PLACEHOLDER_SITES:
            raise KeyError(f"No placeholder conditions for region {region!r}")
        return PLACEHOLDER_SITES[region]

    def daily_forcing(
        self, site: SiteConditions, window: tuple[int, int]
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        return daily_forcing(site, window)


#: The scaffold's forcing source. `growth.simulate`, `growth.harvest_biomass` and
#: `contracts.SiteContext.from_region` all take a `ForcingSource` defaulting to this,
#: so the section 6 data layer substitutes a `GriddedForcing` at the boundary without
#: any of those callers changing.
DEFAULT_FORCING: ForcingSource = PlaceholderForcing()
