"""Shellfish yield and carbon - specification section 7.3.

Salinity-banded harvest model from OLAMUR D2.3 / Maar et al. 2023. Below the
threshold, *mitigation culture* is the intended mode in the SE Baltic: smaller
individuals, higher density, not food-grade, and a higher yield per hectare than
commercial culture precisely because density is optimised for nutrient removal.

Carbon accounting convention (specification section 7.3): the tool reports carbon in
harvested biomass only and never reports sequestration. Shellfish carbon capture is
contested - calcification releases CO2, so any sequestration claim depends on the
shell being physically removed from the water. Maar et al. deliberately counted only
harvested-biomass carbon, and this module follows them.
"""

from __future__ import annotations

from dataclasses import dataclass

from .calibration import Quantity, Tier
from .forcing import SiteConditions
from .params import SpeciesParams


@dataclass(frozen=True)
class ShellfishHarvest:
    """One cultivation cycle of shellfish on a given area."""

    mode: str  # "commercial" or "mitigation"
    fresh_weight: Quantity  # kg FW
    dry_matter_kg: float
    density_kg_m3: float


def culture_mode(species: SpeciesParams, site: SiteConditions) -> str:
    """Which culture mode applies at this salinity."""
    if species.shellfish_yield is None:
        raise ValueError(f"{species.key} has no shellfish yield parameters")
    return (
        "commercial"
        if site.salinity_psu >= species.shellfish_yield.threshold_psu
        else "mitigation"
    )


def biomass_density(species: SpeciesParams, biomass_kg: float, mode: str) -> float:
    """Biomass-density scaling, rho = 1269 * m_bio^(1/3).

    Commercial (food-grade) density is set 3.15x lower than mitigation density,
    following OLAMUR D2.3.
    """
    sy = species.shellfish_yield
    if sy is None:
        raise ValueError(f"{species.key} has no shellfish yield parameters")
    rho = sy.density_coefficient * max(biomass_kg, 0.0) ** (1.0 / 3.0)
    if mode == "commercial":
        rho /= sy.commercial_density_divisor
    return rho


def harvest(
    species: SpeciesParams,
    site: SiteConditions,
    area_ha: float,
) -> ShellfishHarvest:
    """Annual harvest for a shellfish farm of `area_ha` hectares.

    The yield band is carried through as the low/high of the returned Quantity rather
    than collapsed to a midpoint, because the band *is* the state of knowledge.
    """
    sy = species.shellfish_yield
    if sy is None:
        raise ValueError(f"{species.key} has no shellfish yield parameters")

    mode = culture_mode(species, site)
    low_t, high_t = (
        sy.commercial_t_fw_ha_yr if mode == "commercial" else sy.mitigation_t_fw_ha_yr
    )

    calibration = species.calibration_for(site.region)
    low_kg = low_t * 1000.0 * area_ha
    high_kg = high_t * 1000.0 * area_ha
    mid_kg = 0.5 * (low_kg + high_kg)

    fresh = Quantity(
        value=mid_kg,
        unit="kg FW",
        calibration=calibration,
        low=low_kg,
        high=high_kg,
    )

    dm_fraction = species.elemental.dry_matter or 0.103
    return ShellfishHarvest(
        mode=mode,
        fresh_weight=fresh,
        dry_matter_kg=mid_kg * dm_fraction,
        density_kg_m3=biomass_density(species, mid_kg, mode),
    )


def imta_sizing(nutrient: str = "both", low_p_feed: bool = False) -> tuple[float, str]:
    """IMTA planning heuristic from OLAMUR D2.3.

    An 8 ha mussel farm offsets the N and P emissions of a standard finfish farm;
    0.8 ha suffices for phosphorus alone with low-P (hydroxyapatite-binding) feed
    pellets. Returned as a ready planning number for the Plan and Farm doors, with
    the provenance string the interface must display alongside it.
    """
    source = "OLAMUR D2.3, indicative planning figure for a standard finfish farm"
    if nutrient == "phosphorus" and low_p_feed:
        return 0.8, source
    if nutrient == "phosphorus":
        return 8.0, source
    return 8.0, source


def carbon_note() -> str:
    """The sentence that must accompany any shellfish carbon figure."""
    return (
        "Carbon in harvested biomass only. Sequestration is not reported: calcification "
        "releases CO2, so a sequestration claim would depend on the shell being removed "
        "from the water and kept out of it. Low-salinity Baltic mussels stay small and "
        "shell-heavy, so they are carbon-efficient per unit biomass even though total "
        "yield is low - that efficiency framing is the defensible one."
    )


def is_contraindicated(species: SpeciesParams, site: SiteConditions) -> bool:
    return species.calibration_for(site.region).tier is Tier.D
