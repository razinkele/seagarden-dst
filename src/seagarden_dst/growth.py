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
from .forcing import (
    DEFAULT_FORCING,
    ForcingSource,
    SiteConditions,
    require_finite_series,
)
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
    upper_temp_decline_c: float = 3.0,
) -> np.ndarray | float:
    """Arrhenius temperature correction, DEB-style.

        c_T = exp(T_A/T_ref - T_A/T)

    with an optional decline above `upper_temp_c` so that the model does not predict
    unbounded growth in a warming summer. `upper_temp_decline_c` sets the width of
    that decline and comes from the species parameter file - see
    `GrowthParams.upper_temp_decline_c`.
    """
    t = np.asarray(temp_c, dtype=float) + KELVIN
    t_ref = ref_temp_c + KELVIN
    correction = np.exp(arrhenius_temp / t_ref - arrhenius_temp / t)
    if upper_temp_c is not None:
        t_upper = upper_temp_c + KELVIN
        excess = np.clip(t - t_upper, 0.0, None)
        correction = correction * np.exp(-((excess / upper_temp_decline_c) ** 2))
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
    forcing: ForcingSource = DEFAULT_FORCING,
    year: int = 2024,
) -> GrowthTrajectory:
    """Integrate the seasonal growth trajectory with `scipy.integrate.solve_ivp`.

    All rate coefficients come from the species parameter file. Nothing here is
    hard-coded, so recalibration against WP3 A3.4 data is a parameter edit.

    `forcing` defaults to the scaffold's placeholder; the data layer substitutes a
    `ForcingSource` of its own without this function changing. `year` defaults to the
    scaffold's 2024 query when no artifact year has been threaded in yet.
    """
    if species.growth is None:
        raise ValueError(f"{species.key} has no growth parameters (not a macroalga?)")

    g = species.growth
    days, par, temp, din = forcing.daily_forcing(site, species.cultivation_window, year)
    require_finite_series(site.region, days, par, temp, din)

    f_i = np.asarray(f_irradiance(par, g.i_k), dtype=float)
    f_t = np.asarray(
        f_temperature(
            temp, g.arrhenius_temp, g.ref_temp_c, g.upper_temp_c, g.upper_temp_decline_c
        ),
        dtype=float,
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


def salinity_indexed_yield(species: SpeciesParams, site: SiteConditions) -> Quantity:
    """OLAMUR D2.3's published Saccharina model: f_salinity x a maximum yield.

    There is no growth ODE in the published form - yield is a function of salinity
    alone, anchored on 18.4 t FW/ha from Danish sites above 16 psu. Returns t FW/ha so
    the figure can be checked directly against the published anchor without passing
    through a dry-matter conversion.

    This is a public function in its own right (not only a step inside
    `harvest_biomass`), so it resolves its own calibration through `contraindication()`
    first, exactly as `harvest_biomass` does - a direct caller below the salinity floor
    must see tier D here too, not a tier C number that only turns into a finding one
    layer up. Enforcing it a second time in the one other function that can produce
    this figure is the same reasoning as commit 751de41 ("Resolve tier D where the
    number is produced, not only where it is orchestrated").

    A contraindicated pairing also zeroes the value, matching `harvest_biomass`: a
    tier D `Quantity` must not carry a usable figure for anyone who reads `.value`
    without first checking `is_reportable` - that is exactly the leak the tier
    apparatus exists to close.
    """
    if species.salinity is None or species.max_yield_t_fw_ha is None:
        raise ValueError(f"{species.key} has no salinity-indexed yield model")

    contra = contraindication(species, site)
    if contra is not None:
        return Quantity(value=0.0, unit="t FW/ha", calibration=contra)

    calibration = species.calibration_for(site.region)
    factor = species.salinity.factor(site.salinity_psu)
    return Quantity(
        value=factor * species.max_yield_t_fw_ha,
        unit="t FW/ha",
        calibration=calibration,
    )


def harvest_biomass(
    species: SpeciesParams,
    site: SiteConditions,
    area_m2: float,
    forcing: ForcingSource = DEFAULT_FORCING,
) -> Quantity:
    """Harvested dry biomass over one cultivation cycle, in kg DW.

    Returns a Quantity so the calibration tier travels with the number. A
    contraindicated combination (tier D) returns a zero-valued Quantity whose
    calibration is not reportable - callers must show the note, not the number.

    The tier is resolved through `contraindication()` rather than through
    `calibration_for()` so that the dynamic salinity rule and the per-region registry
    cannot disagree. Enforcing it here rather than only in `api.assess_site` is
    deliberate: this is the function that produces the number.

    `forcing` is threaded through to `simulate()` for the ODE branch below; the
    salinity-indexed branch never integrates the ODE, so it never touches it.
    """
    contra = contraindication(species, site)
    if contra is not None:
        return Quantity(value=0.0, unit="kg DW", calibration=contra)

    calibration = species.calibration_for(site.region)

    if species.yield_model == "salinity_indexed":
        fresh_t_per_ha = salinity_indexed_yield(species, site).value
        kg = fresh_t_per_ha * species.elemental.dry_matter * 1000.0 * (area_m2 / 10_000.0)
        return Quantity(value=kg, unit="kg DW", calibration=calibration)

    # The public API does not yet carry an artifact year through SiteContext, so the
    # model uses the default 2024 season until a real reader is explicitly threaded in.
    trajectory = simulate(species, site, forcing=forcing)
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
