"""Scenario comparison - specification section 5.4.

Discharges the Application Form's commitment to "help users compare farming methods
*and scales*". A scenario is one species x method x scale at one site; up to four are
compared side by side.

Scales follow the project's own hardware: the A3.5 mini-farm kit, a community farm,
and a small commercial unit.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .calibration import Quantity, for_display
from .forcing import SiteConditions
from .growth import harvest_biomass
from .nutrients import NutrientRemoval, from_harvest
from .params import MethodParams, ParameterSet, SpeciesParams
from .shellfish import harvest as shellfish_harvest
from .suitability import Suitability, assess

#: Named scales, in m2. The mini-farm figure is the OLAMUR cage size, which is also
#: the order of the A3.5 citizen-science kit.
SCALES: dict[str, float] = {
    "mini-farm kit": 6.0,
    "community farm (0.1 ha)": 1_000.0,
    "community farm (1 ha)": 10_000.0,
    "small commercial (5 ha)": 50_000.0,
}


@dataclass
class Scenario:
    """One comparable configuration."""

    label: str
    species: SpeciesParams
    method: MethodParams
    site: SiteConditions
    area_m2: float

    @property
    def area_ha(self) -> float:
        return self.area_m2 / 10_000.0


@dataclass
class ScenarioResult:
    scenario: Scenario
    suitability: Suitability
    harvest: Quantity
    removal: NutrientRemoval | None

    @property
    def is_reportable(self) -> bool:
        return self.harvest.calibration.is_reportable


def evaluate(scenario: Scenario, permitting_layer: object | None = None) -> ScenarioResult:
    """Run one scenario end to end."""
    suit = assess(scenario.site, scenario.species, scenario.method, permitting_layer)

    if scenario.species.group == "shellfish":
        harvest = shellfish_harvest(
            scenario.species, scenario.site, area_ha=scenario.area_ha
        ).fresh_weight
    else:
        harvest = harvest_biomass(scenario.species, scenario.site, scenario.area_m2)

    removal = from_harvest(scenario.species, harvest) if harvest.calibration.is_reportable else None
    return ScenarioResult(scenario=scenario, suitability=suit, harvest=harvest, removal=removal)


def compare(
    scenarios: list[Scenario],
    permitting_layer: object | None = None,
    limit: int | None = 4,
) -> pd.DataFrame:
    """Side-by-side comparison table.

    Every numeric cell is rendered through `for_display`, so tier C values arrive as
    order-of-magnitude bands rather than spurious precision.

    `limit` defaults to 4 because that is the scenario comparison panel of
    specification section 5.4, which is a considered design constraint: more than four
    columns stops being a comparison and starts being a table. Pass `limit=None` for
    the Plan door's species overview, which is a different thing.
    """
    if limit is not None and len(scenarios) > limit:
        raise ValueError(f"The comparison panel takes at most {limit} scenarios")

    rows = []
    for scenario in scenarios:
        result = evaluate(scenario, permitting_layer)
        row = {
            "Scenario": scenario.label,
            "Species": scenario.species.common_name,
            "Method": scenario.method.name,
            "Area (ha)": round(scenario.area_ha, 4),
            "Verdict": result.suitability.verdict.value,
            "Binding constraint": result.suitability.explain(),
            "Harvest": str(for_display(result.harvest)),
            "Calibration": result.harvest.calibration.tier.label,
        }
        if result.removal is not None:
            row["Nitrogen removed"] = str(for_display(result.removal.nitrogen))
            row["Phosphorus removed"] = str(for_display(result.removal.phosphorus))
            row["Carbon in harvest"] = str(for_display(result.removal.carbon))
        else:
            row["Nitrogen removed"] = "-"
            row["Phosphorus removed"] = "-"
            row["Carbon in harvest"] = "-"
        rows.append(row)

    return pd.DataFrame(rows)


def default_scenarios(
    params: ParameterSet, site: SiteConditions, scale: str = "community farm (0.1 ha)"
) -> list[Scenario]:
    """A starting set: every species the parameter files carry, at one scale.

    Used by the Explore door and by the tests as a smoke check that every shipped
    species parameter file is at least internally runnable.
    """
    area = SCALES[scale]
    out: list[Scenario] = []
    for species in params.species.values():
        method = next(
            (m for m in params.methods.values() if species.group in m.suits_groups), None
        )
        if method is None:
            continue
        out.append(
            Scenario(
                label=f"{species.common_name} - {scale}",
                species=species,
                method=method,
                site=site,
                area_m2=area,
            )
        )
    return out
