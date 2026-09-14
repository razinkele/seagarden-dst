"""Site conditions and seasonal forcing.

In the scaffold these are entered by hand or generated from a simple seasonal
climatology. In the delivered tool they are read from the curated layers of
specification section 6 (Copernicus reanalysis, EMODnet, HELCOM) for a drawn
polygon, via the optional `spatial` extra.

The interface between the two is deliberately narrow - `SiteConditions` and
`daily_forcing()` - so that swapping the stub for the real data layer touches
nothing in `growth`, `shellfish`, `nutrients` or `suitability`.
"""

from __future__ import annotations

from dataclasses import dataclass

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
    surface_par: float
    din_umol_l: float
    dip_umol_l: float
    depth_m: float
    significant_wave_m: float
    light_attenuation_k: float = 0.4
    cultivation_depth_m: float = 1.5

    def par_at_depth(self) -> float:
        """Beer-Lambert attenuation to the cultivation depth."""
        attenuated = np.exp(-self.light_attenuation_k * self.cultivation_depth_m)
        return float(self.surface_par * attenuated)


#: Placeholder conditions per region, used by the scaffold so the application runs
#: end to end before the data layer exists. These are plausible order-of-magnitude
#: values, NOT measurements, and every result derived from them inherits tier C.
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

    One placeholder limitation is worth naming, because wrapping windows made it
    consequential: the nutrient drawdown below is indexed by position in the window
    rather than by calendar day. Nitrogen is therefore a property of the query and not
    of the site - on 1 April at DK-belt this function returns 3.15 umol N/L for the
    Oct-Jun window and 5.00 for the April-start windows: two values, not three, for
    the windows that reach this function. Mytilus ships cultivation_window [1, 12]
    and would give 4.3144 on the same date, but never reaches this function -
    shellfish have no growth: block and are handled outside `growth.simulate`. The
    real seasonal cycle arrives with the section 6 climatologies. Fixing it moves the
    modelled yields; mu_max has never been fitted to the anchor - it carries its
    initial value, and b_max is set from the anchor's own upper bound, so the anchor
    is not an independent check either.
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

    # Nutrients are highest early and drawn down as the season progresses.
    drawdown = np.linspace(1.0, 0.45, days.size)
    din = site.din_umol_l * drawdown

    return days, par, temperature, din
