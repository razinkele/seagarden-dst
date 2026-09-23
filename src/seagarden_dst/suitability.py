"""Site suitability - specification section 5.2.

Suitability is the MINIMUM across constraint classes, never a weighted composite:

    suitability = min(physical_feasibility,
                      environmental_tolerance,
                      growth_viability,
                      legal_permissibility)

A weighted index lets a site with a fatal legal exclusion score "moderately suitable"
because the water is good, which is exactly the failure mode a permitting authority
cannot tolerate. Where a class fails, the tool names it.

The legal_permissibility term is fed by the regulatory layer of section 9, which does
not exist yet - it is produced in-project by GMU's A2.2 legal expertise (M12) and
tested by WP3 A3.1. Until then it defaults to "unknown" and says so, rather than
defaulting to permitted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from .calibration import Tier
from .forcing import DEFAULT_FORCING, PLACEHOLDER_YEAR, ForcingSource, SiteConditions
from .growth import contraindication, harvest_biomass
from .params import MethodParams, SpeciesParams, default_parameters


class Verdict(StrEnum):
    SUITABLE = "suitable"
    MARGINAL = "marginal"
    UNSUITABLE = "unsuitable"
    UNKNOWN = "unknown"

    @property
    def score(self) -> float:
        """Severity ordering, worst first.

        UNSUITABLE outranks UNKNOWN: a site that is definitely not workable is more
        informative to report than one that is merely unassessed, and the overall
        verdict resolves the same way. Keep this consistent with `Suitability.verdict`.
        """
        return {
            Verdict.UNSUITABLE: 0.0,
            Verdict.UNKNOWN: 0.25,
            Verdict.MARGINAL: 0.5,
            Verdict.SUITABLE: 1.0,
        }[self]


@dataclass(frozen=True)
class Constraint:
    """One constraint class and why it landed where it did."""

    name: str
    verdict: Verdict
    reason: str


@dataclass
class Suitability:
    """Result of a suitability assessment for one species x method x site."""

    species_key: str
    method_key: str
    region: str
    constraints: list[Constraint] = field(default_factory=list)

    @property
    def verdict(self) -> Verdict:
        """The minimum, with UNKNOWN treated as blocking rather than permissive."""
        if not self.constraints:
            return Verdict.UNKNOWN
        if any(c.verdict is Verdict.UNSUITABLE for c in self.constraints):
            return Verdict.UNSUITABLE
        if any(c.verdict is Verdict.UNKNOWN for c in self.constraints):
            return Verdict.UNKNOWN
        if any(c.verdict is Verdict.MARGINAL for c in self.constraints):
            return Verdict.MARGINAL
        return Verdict.SUITABLE

    @property
    def binding_constraint(self) -> Constraint | None:
        """The class that determined the verdict - what the user actually needs told."""
        ordered = sorted(self.constraints, key=lambda c: c.verdict.score)
        return ordered[0] if ordered else None

    def explain(self) -> str:
        binding = self.binding_constraint
        if binding is None:
            return "No assessment performed."
        if self.verdict is Verdict.SUITABLE:
            return "No binding constraint identified."
        return f"{binding.name}: {binding.reason}"


def assess_physical(site: SiteConditions, method: MethodParams) -> Constraint:
    if not (method.min_depth_m <= site.depth_m <= method.max_depth_m):
        return Constraint(
            "Physical feasibility",
            Verdict.UNSUITABLE,
            f"Depth {site.depth_m:g} m is outside the workable window for "
            f"{method.name} ({method.min_depth_m:g}-{method.max_depth_m:g} m).",
        )
    if site.significant_wave_m > method.max_significant_wave_m:
        return Constraint(
            "Physical feasibility",
            Verdict.MARGINAL,
            f"Significant wave height {site.significant_wave_m:g} m exceeds the "
            f"design limit of {method.max_significant_wave_m:g} m for {method.name}.",
        )
    return Constraint("Physical feasibility", Verdict.SUITABLE, "Depth and exposure workable.")


def assess_environment(
    site: SiteConditions,
    species: SpeciesParams,
    salinity_factor_floor: float | None = None,
) -> Constraint:
    """`salinity_factor_floor=None` (the default) resolves `default_parameters()` here,
    inside the call, rather than once at import time - so a params/ recalibration
    reaches the next call that takes the default, not just the next process start.
    """
    if salinity_factor_floor is None:
        salinity_factor_floor = default_parameters().assessment.salinity_factor_floor
    contra = contraindication(species, site)
    if contra is not None:
        return Constraint(
            "Environmental tolerance",
            Verdict.UNSUITABLE,
            contra.note or "Contraindicated at this site.",
        )
    if species.salinity is not None and species.salinity.applies:
        factor = species.salinity.factor(site.salinity_psu)
        if factor < salinity_factor_floor:
            return Constraint(
                "Environmental tolerance",
                Verdict.MARGINAL,
                f"Salinity {site.salinity_psu:g} psu scales maximum yield to "
                f"{factor:.0%} of the reference.",
            )
    return Constraint(
        "Environmental tolerance", Verdict.SUITABLE, "Within the species' tolerance range."
    )


def assess_growth(
    site: SiteConditions,
    species: SpeciesParams,
    method: MethodParams,
    floor_kg_dw_per_m2: float | None = None,
    forcing: ForcingSource = DEFAULT_FORCING,
    year: int = PLACEHOLDER_YEAR,
) -> Constraint:
    """Growth viability against a yield floor.

    Shellfish are handled by the banded yield model rather than the ODE, so they
    return SUITABLE here and are constrained by environment and law instead.

    `floor_kg_dw_per_m2=None` (the default) resolves `default_parameters()` here,
    inside the call, rather than once at import time - see `assess_environment`.

    `forcing` and `year` are threaded through to `harvest_biomass()` so this constraint
    sees the same seasonal series, for the same year, as the harvest figure reported
    alongside it, rather than silently falling back to the placeholder while the rest
    of the assessment uses an injected source.
    """
    if floor_kg_dw_per_m2 is None:
        floor_kg_dw_per_m2 = default_parameters().assessment.yield_floor_kg_dw_per_m2
    if species.group != "macroalga":
        return Constraint(
            "Growth viability", Verdict.SUITABLE, "Assessed by the banded yield model."
        )
    harvest = harvest_biomass(
        species, site, area_m2=method.area_m2_per_unit, forcing=forcing, year=year
    )
    if not harvest.calibration.is_reportable:
        return Constraint(
            "Growth viability",
            Verdict.UNSUITABLE,
            harvest.calibration.note or "Contraindicated.",
        )
    per_m2 = harvest.value / method.area_m2_per_unit
    if per_m2 < floor_kg_dw_per_m2:
        return Constraint(
            "Growth viability",
            Verdict.MARGINAL,
            f"Predicted {per_m2:.2f} kg DW/m2 is below the {floor_kg_dw_per_m2:g} "
            f"kg DW/m2 default floor.",
        )
    tier_note = " (literature prior)" if harvest.calibration.tier is Tier.C else ""
    return Constraint(
        "Growth viability",
        Verdict.SUITABLE,
        f"Predicted {per_m2:.2f} kg DW/m2 over one cycle{tier_note}.",
    )


def assess_legal(site: SiteConditions, permitting_layer: object | None = None) -> Constraint:
    """Legal permissibility.

    Placeholder until the regulatory records of section 9 exist. Returning UNKNOWN
    rather than SUITABLE is deliberate: an absent permitting layer must block the
    verdict, not silently pass it.
    """
    if permitting_layer is None:
        return Constraint(
            "Legal permissibility",
            Verdict.UNKNOWN,
            "No regulatory record loaded for this jurisdiction. The permitting layer "
            "is produced in-project by A2.2 (M12) and tested by WP3 A3.1.",
        )
    raise NotImplementedError("Regulatory layer integration - specification section 9")


def assess(
    site: SiteConditions,
    species: SpeciesParams,
    method: MethodParams,
    permitting_layer: object | None = None,
    yield_floor_kg_dw_per_m2: float | None = None,
    forcing: ForcingSource = DEFAULT_FORCING,
    year: int = PLACEHOLDER_YEAR,
) -> Suitability:
    """Full suitability assessment for one species x method x site.

    `yield_floor_kg_dw_per_m2=None` is passed straight through to `assess_growth`,
    which resolves the default itself - see its docstring.

    `forcing` and `year` are passed straight through to `assess_growth` too, so an
    injected source and query year reach the growth-viability constraint, not only
    the headline harvest figure computed elsewhere.
    """
    if species.group not in method.suits_groups:
        return Suitability(
            species_key=species.key,
            method_key=method.key,
            region=site.region,
            constraints=[
                Constraint(
                    "Physical feasibility",
                    Verdict.UNSUITABLE,
                    f"{method.name} does not support {species.group} cultivation.",
                )
            ],
        )

    return Suitability(
        species_key=species.key,
        method_key=method.key,
        region=site.region,
        constraints=[
            assess_physical(site, method),
            assess_environment(site, species),
            assess_growth(
                site, species, method, yield_floor_kg_dw_per_m2, forcing=forcing, year=year
            ),
            assess_legal(site, permitting_layer),
        ],
    )
