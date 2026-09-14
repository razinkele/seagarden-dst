"""Macroalgal growth and harvest - specification section 7.2.

Adapted from OLAMUR D3.2, which re-parameterised a Saccharina framework for Fucus
after sugar kelp failed at low salinity in Tagalaht Bay (5.5-6.5 psu, essentially the
SE Baltic range). The formulation is multiplicative:

    dB/dt = mu_max * f(I) * f(T) * f(N) * B - losses(B)

with f(I) a saturating irradiance term, f(T) an Arrhenius-type DEB-style correction,
and f(N) Holling type II nitrate limitation. No explicit salinity term is applied to
Fucus: OLAMUR found none was needed once the model was calibrated for Baltic
conditions. Species that do need one carry a SalinityResponse in their parameter file.

Reference for validation (OLAMUR D3.2, Tagalaht Bay, April-October, per 6 m2 cage):
4800-5200 g DW/m2 harvest, ~10-13 kg C, 1.4-3.4 kg N, 15-120 g P.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.integrate import solve_ivp

from .calibration import Calibration, Quantity, Tier
from .forcing import SiteConditions, daily_forcing
from .params import SpeciesParams

KELVIN = 273.15


def f_irradiance(par: np.ndarray | float, i_k: float) -> np.ndarray | float:
    """Saturating photosynthesis-irradiance response, quantum-yield form."""
    return 1.0 - np.exp(-np.asarray(par, dtype=float) / i_k)


def f_temperature(
    temp_c: np.ndarray | float,
    arrhenius_temp: float,
    ref_temp_c: float,
    upper_temp_c: float | None = None,
) -> np.ndarray | float:
    """Arrhenius temperature correction, DEB-style.

        c_T = exp(T_A/T_ref - T_A/T)

    with an optional decline above `upper_temp_c` so that the model does not predict
    unbounded growth in a warming summer.
    """
    t = np.asarray(temp_c, dtype=float) + KELVIN
    t_ref = ref_temp_c + KELVIN
    correction = np.exp(arrhenius_temp / t_ref - arrhenius_temp / t)
    if upper_temp_c is not None:
        t_upper = upper_temp_c + KELVIN
        excess = np.clip(t - t_upper, 0.0, None)
        correction = correction * np.exp(-((excess / 3.0) ** 2))
    return correction


def f_nitrate(din: np.ndarray | float, k_nitrate: float) -> np.ndarray | float:
    """Holling type II nutrient limitation."""
    d = np.asarray(din, dtype=float)
    return d / (k_nitrate + d)


@dataclass(frozen=True)
class GrowthTrajectory:
    """Seasonal biomass trajectory and the limitation terms that produced it."""

    days: np.ndarray
    biomass: np.ndarray
    f_light: np.ndarray
    f_temp: np.ndarray
    f_nutrient: np.ndarray

    @property
    def final_biomass(self) -> float:
        return float(self.biomass[-1])

    def limiting_factor(self) -> str:
        """Which term constrained growth most over the season."""
        means = {
            "light": float(np.mean(self.f_light)),
            "temperature": float(np.mean(np.clip(self.f_temp, 0.0, 1.0))),
            "nutrients": float(np.mean(self.f_nutrient)),
        }
        return min(means, key=means.get)


def simulate(
    species: SpeciesParams,
    site: SiteConditions,
    max_step_days: float = 1.0,
) -> GrowthTrajectory:
    """Integrate the seasonal growth trajectory with `scipy.integrate.solve_ivp`.

    All rate coefficients come from the species parameter file. Nothing here is
    hard-coded, so recalibration against WP3 A3.4 data is a parameter edit.
    """
    if species.growth is None:
        raise ValueError(f"{species.key} has no growth parameters (not a macroalga?)")

    g = species.growth
    days, par, temp, din = daily_forcing(site, species.cultivation_window)

    f_i = np.asarray(f_irradiance(par, g.i_k), dtype=float)
    f_t = np.asarray(
        f_temperature(temp, g.arrhenius_temp, g.ref_temp_c, g.upper_temp_c), dtype=float
    )
    f_n = np.asarray(f_nitrate(din, g.k_nitrate), dtype=float)

    salinity_factor = species.salinity.factor(site.salinity_psu) if species.salinity else 1.0
    rate = g.mu_max * f_i * f_t * f_n * salinity_factor

    def dbdt(t: float, y: np.ndarray) -> list[float]:
        mu = float(np.interp(t, days, rate))
        biomass = max(float(y[0]), 0.0)
        logistic = 1.0 - biomass / g.b_max if g.b_max else 1.0
        return [mu * biomass * max(logistic, 0.0) - g.loss_rate * biomass]

    solution = solve_ivp(
        dbdt,
        t_span=(days[0], days[-1]),
        y0=[g.b_initial],
        t_eval=days,
        max_step=max_step_days,
        method="RK45",
    )
    if not solution.success:
        raise RuntimeError(f"Growth integration failed for {species.key}: {solution.message}")

    return GrowthTrajectory(
        days=days,
        biomass=np.clip(solution.y[0], 0.0, None),
        f_light=f_i,
        f_temp=f_t,
        f_nutrient=f_n,
    )


def harvest_biomass(
    species: SpeciesParams,
    site: SiteConditions,
    area_m2: float,
) -> Quantity:
    """Harvested dry biomass over one cultivation cycle, in kg DW.

    Returns a Quantity so the calibration tier travels with the number. A
    contraindicated combination (tier D) returns a zero-valued Quantity whose
    calibration is not reportable - callers must show the note, not the number.

    The tier is resolved through `contraindication()` rather than through
    `calibration_for()` so that the dynamic salinity rule and the per-region registry
    cannot disagree. Enforcing it here rather than only in `api.assess_site` is
    deliberate: this is the function that produces the number.
    """
    contra = contraindication(species, site)
    if contra is not None:
        return Quantity(value=0.0, unit="kg DW", calibration=contra)

    calibration = species.calibration_for(site.region)
    trajectory = simulate(species, site)
    kg = trajectory.final_biomass * area_m2 / 1000.0
    return Quantity(value=kg, unit="kg DW", calibration=calibration)


def contraindication(species: SpeciesParams, site: SiteConditions) -> Calibration | None:
    """Return the tier D calibration for this pairing, if there is one.

    The canonical case is Saccharina latissima below about 16 psu: OLAMUR's salinity
    scaling returns a small positive yield while their own pilot found outright
    cultivation failure. A number and a finding disagree, and the tool shows both -
    see specification section 5.3.

    The salinity floor itself is resolved through `species.salinity_floor()` alone,
    whether it lives on `SalinityResponse` (macroalgae) or `ShellfishYield` (Mytilus,
    which has no salinity block at all) - one resolution path, not two that could
    silently disagree.
    """
    calibration = species.calibration_for(site.region)
    if calibration.tier is Tier.D:
        return calibration
    floor = species.salinity_floor()
    if floor is not None:
        floor_psu, floor_basis = floor
        if site.salinity_psu < floor_psu:
            if floor_basis == "observed":
                detail = "cultivation failure has been observed at this salinity"
            else:
                detail = (
                    "the floor is assumed - no cultivation trial at this salinity is "
                    "known to us"
                )
            return Calibration(
                tier=Tier.D,
                region=site.region,
                source=calibration.source,
                note=(
                    f"Below {floor_psu:g} psu the model returns a positive yield, but "
                    f"{detail}. Treat as not cultivable here."
                ),
            )
    return None
