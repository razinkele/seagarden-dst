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

from collections.abc import Callable
from dataclasses import dataclass, field

from .calibration import Quantity, Tier
from .forcing import (
    DEFAULT_FORCING,
    PLACEHOLDER_YEAR,
    Coverage,
    ForcingSource,
    SiteConditions,
    SiteQuery,
    SiteReading,
)
from .i18n import Message, msg

#: E§3.5. Set on a context built through the reader whose region has no coordinate, so
#: the session runs on the artifact while this one site stays on the placeholder - a
#: fallback the banner and report must say, not one they infer from a boolean.
SOURCE_NOTE_NO_POSITION = msg("contracts.source_note.no_position")


@dataclass
class SiteContext:
    """Everything the core needs to know about one place.

    Attributes:
        region: calibration sub-region key, e.g. "LT-coastal", or None when unknown. Drives which
            parameter calibration applies (see `params.SpeciesParams.calibration_for`).
        conditions: the environmental summary. Supplied by the data layer in the
            delivered tool; by `forcing.PLACEHOLDER_SITES` in the scaffold. None means
            the data layer could not answer and the site must not score.
        geometry_wkt: the drawn polygon, when there is one. Empty in the scaffold.
        label: human-readable site name, carried into the report so a set of numbers
            can never be shown under the wrong site's name.
        confidence: site DATA confidence (low|medium|high). This is about the inputs,
            NOT the model calibration tier, which lives per species in `calibration`.
        activities: human-use conflicts present, once the spatial layers exist.
        protection: designations present (Natura 2000, HELCOM MPA, ...).
    """

    region: str | None
    conditions: SiteConditions | None
    geometry_wkt: str = ""
    label: str = ""
    confidence: str = "low"
    activities: list[str] = field(default_factory=list)
    protection: list[str] = field(default_factory=list)
    coverage: Coverage = Coverage.VALID
    nearest_valid_km: float | None = None
    from_artifact: bool = False
    #: Why this site is on the placeholder while the session runs on the artifact;
    #: None otherwise (E§3.5). A Message, never "", so callers test `is not None`.
    source_note: Message | None = None

    @classmethod
    def from_region(
        cls,
        region: str,
        *,
        label: str = "",
        forcing: ForcingSource = DEFAULT_FORCING,
        year: int = PLACEHOLDER_YEAR,
    ) -> SiteContext:
        """Build a context from the conditions a `ForcingSource` has for a sub-region.

        The scaffold's only way in. Confidence is "low" by construction, because the
        default `forcing` (the placeholder) returns plausible order-of-magnitude
        values and not measurements. The placeholder ignores `year`; it is present so
        the same query shape can reach a real artifact. `reading_at()` raises `KeyError`
        for a region it does not know about.
        """
        reading = forcing.reading_at(SiteQuery(geometry_wkt="", year=year, region=region))
        return cls(
            region=reading.conditions.region if reading.conditions else region,
            conditions=reading.conditions,
            label=label or region,
            confidence="low",
            coverage=reading.coverage,
            nearest_valid_km=reading.nearest_valid_km,
            from_artifact=reading.from_artifact,
        )

    @classmethod
    def from_reading(
        cls, reading: SiteReading, *, label: str = "", geometry_wkt: str = ""
    ) -> SiteContext:
        """Build a context from a `SiteReading`, blocked or not.

        `from_region` remains for the placeholder path, where a region is all there is.
        This is the path package D's reader uses, and it is the one that can carry a
        context with no conditions — §7's mechanism for a site that must not score.
        """
        return cls(
            region=reading.conditions.region if reading.conditions else None,
            conditions=reading.conditions,
            label=label,
            geometry_wkt=geometry_wkt,
            confidence="low",
            coverage=reading.coverage,
            nearest_valid_km=reading.nearest_valid_km,
            from_artifact=reading.from_artifact,
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
    binding_constraint: Message
    tier: Tier
    harvest: Quantity
    nitrogen: Quantity | None = None
    phosphorus: Quantity | None = None
    carbon: Quantity | None = None
    constraints: list[tuple[Message, str, Message]] = field(default_factory=list)

    @property
    def is_reportable(self) -> bool:
        return self.harvest.calibration.is_reportable

    @property
    def nitrogen_value(self) -> float:
        """Sort key. Zero for anything not reportable, so tier D never ranks."""
        return self.nitrogen.value if (self.is_reportable and self.nitrogen) else 0.0

    def to_dict(self, render: Callable[[Message], str] = str) -> dict:
        """Export. Every Message is `{"key", "params", "text"}` (I§5.1); quantities are
        their English `str()`, as before. Written by hand rather than `asdict`, which
        would recurse into Message and emit it without its text."""
        return {
            "species_key": self.species_key,
            "species_name": self.species_name,
            "method_key": self.method_key,
            "method_name": self.method_name,
            "area_m2": self.area_m2,
            "verdict": self.verdict,
            "binding_constraint": self.binding_constraint.to_dict(render),
            "tier": self.tier.value,
            "harvest": str(self.harvest),
            "nitrogen": None if self.nitrogen is None else str(self.nitrogen),
            "phosphorus": None if self.phosphorus is None else str(self.phosphorus),
            "carbon": None if self.carbon is None else str(self.carbon),
            "constraints": [
                [name.to_dict(render), verdict, reason.to_dict(render)]
                for name, verdict, reason in self.constraints
            ],
        }


@dataclass
class SiteAssessment:
    """What `api.assess_site` returns. The UI renders this and nothing else."""

    context: SiteContext
    ranked: list[SpeciesOption]
    best: SpeciesOption | None = None
    excluded: dict[str, Message] = field(default_factory=dict)
    caveats: dict[str, Message] = field(default_factory=dict)
    pressure: dict[str, float] = field(default_factory=dict)
    pressure_note: Message | None = None
    unassessable: bool = False
    coverage: Coverage = Coverage.VALID
    nearest_valid_km: float | None = None

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

    def to_dict(self, render: Callable[[Message], str] = str) -> dict:
        note = self.context.source_note
        return {
            "site": {
                "region": self.context.region,
                "label": self.context.label,
                "confidence": self.context.confidence,
                "geometry_wkt": self.context.geometry_wkt,
                "from_artifact": self.context.from_artifact,
                "source_note": None if note is None else note.to_dict(render),
            },
            "ranked": [o.to_dict(render) for o in self.ranked],
            "best": None if self.best is None else self.best.to_dict(render),
            "excluded": {k: v.to_dict(render) for k, v in self.excluded.items()},
            "caveats": {k: v.to_dict(render) for k, v in self.caveats.items()},
            "pressure": dict(self.pressure),
            "pressure_note": (
                None if self.pressure_note is None else self.pressure_note.to_dict(render)
            ),
        }
