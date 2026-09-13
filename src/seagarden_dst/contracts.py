"""DST core data contracts (UI- and IO-agnostic).

Deliberately the same shape as `nid4ocean_dst.contracts`: a `SiteContext` in, a
result dataclass out, `to_dict()` on anything the report or an export touches, and
no Shiny, no file IO, no globals. The UI depends on this module; this module knows
nothing about the UI.

Differences from NiD4OCEAN are only where the science differs. There, a site is a
geometry plus habitats, species observations and activities, and the question is
which nature-inclusive design measure suits it. Here a site is a geometry plus the
environmental conditions that drive growth, and the question is what can be farmed
there and how much nutrient it removes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .calibration import Quantity, Tier
from .forcing import PLACEHOLDER_SITES, SiteConditions


@dataclass
class SiteContext:
    """Everything the core needs to know about one place.

    Attributes:
        region: calibration sub-region key, e.g. "LT-coastal". Drives which
            parameter calibration applies (see `params.SpeciesParams.calibration_for`).
        conditions: the environmental summary. Supplied by the data layer in the
            delivered tool; by `forcing.PLACEHOLDER_SITES` in the scaffold.
        geometry_wkt: the drawn polygon, when there is one. Empty in the scaffold.
        label: human-readable site name, carried into the report so a set of numbers
            can never be shown under the wrong site's name.
        confidence: site DATA confidence (low|medium|high). This is about the inputs,
            NOT the model calibration tier, which lives per species in `calibration`.
        activities: human-use conflicts present, once the spatial layers exist.
        protection: designations present (Natura 2000, HELCOM MPA, ...).
    """

    region: str
    conditions: SiteConditions
    geometry_wkt: str = ""
    label: str = ""
    confidence: str = "low"
    activities: list[str] = field(default_factory=list)
    protection: list[str] = field(default_factory=list)

    @classmethod
    def from_region(cls, region: str, *, label: str = "") -> SiteContext:
        """Build a context from the placeholder conditions for a sub-region.

        The scaffold's only way in. Confidence is "low" by construction, because the
        conditions are plausible order-of-magnitude values and not measurements.
        """
        if region not in PLACEHOLDER_SITES:
            raise KeyError(f"No placeholder conditions for region {region!r}")
        return cls(
            region=region,
            conditions=PLACEHOLDER_SITES[region],
            label=label or region,
            confidence="low",
        )


@dataclass
class SpeciesOption:
    """One species x method x scale, assessed at one site."""

    species_key: str
    species_name: str
    method_key: str
    method_name: str
    area_m2: float
    verdict: str
    binding_constraint: str
    tier: Tier
    harvest: Quantity
    nitrogen: Quantity | None = None
    phosphorus: Quantity | None = None
    carbon: Quantity | None = None
    constraints: list[tuple[str, str, str]] = field(default_factory=list)

    @property
    def is_reportable(self) -> bool:
        return self.harvest.calibration.is_reportable

    @property
    def nitrogen_value(self) -> float:
        """Sort key. Zero for anything not reportable, so tier D never ranks."""
        return self.nitrogen.value if (self.is_reportable and self.nitrogen) else 0.0

    def to_dict(self) -> dict:
        out = asdict(self)
        out["tier"] = self.tier.value
        for key in ("harvest", "nitrogen", "phosphorus", "carbon"):
            value = getattr(self, key)
            out[key] = None if value is None else str(value)
        return out


@dataclass
class SiteAssessment:
    """What `api.assess_site` returns. The UI renders this and nothing else."""

    context: SiteContext
    ranked: list[SpeciesOption]
    best: SpeciesOption | None = None
    excluded: dict[str, str] = field(default_factory=dict)
    caveats: dict[str, str] = field(default_factory=dict)
    pressure: dict[str, float] = field(default_factory=dict)
    pressure_note: str = ""

    @property
    def any_reportable(self) -> bool:
        return any(o.is_reportable for o in self.ranked)

    @property
    def lowest_tier(self) -> Tier | None:
        """The weakest calibration among reportable options - the headline caveat."""
        tiers = [o.tier for o in self.ranked if o.is_reportable]
        if not tiers:
            return None
        order = [Tier.A, Tier.B, Tier.C]
        return max(tiers, key=lambda t: order.index(t) if t in order else 99)

    def to_dict(self) -> dict:
        return {
            "site": {
                "region": self.context.region,
                "label": self.context.label,
                "confidence": self.context.confidence,
                "geometry_wkt": self.context.geometry_wkt,
            },
            "ranked": [o.to_dict() for o in self.ranked],
            "best": None if self.best is None else self.best.to_dict(),
            "excluded": dict(self.excluded),
            "caveats": dict(self.caveats),
            "pressure": dict(self.pressure),
            "pressure_note": self.pressure_note,
        }
