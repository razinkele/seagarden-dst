"""Calibration registry.

Implements specification section 7.4. Every quantitative result the tool produces
carries a calibration tier, and the tier travels with the number all the way to the
user interface rather than sitting in a footnote.

The tiers exist because the South Baltic is the part of the Baltic nobody has
calibrated: OLAMUR's ODSS draws its growth-model training data from Estonia,
Finland, Sweden, Denmark and Germany. Lithuania and Poland are not calibration
sources, so before SeaGarden's own pilot data arrives (WP3 A3.4, M12-30) every
SE Baltic number is an extrapolation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Tier(StrEnum):
    """Calibration tier of a (species x region x parameter set) combination."""

    A = "A"  # locally calibrated - fitted to SeaGarden pilot data from this sub-region
    B = "B"  # regionally extrapolated - fitted elsewhere in the Baltic, comparable salinity
    C = "C"  # literature prior - published parameters, no local validation
    D = "D"  # contraindicated - a local finding contradicts the model

    @property
    def label(self) -> str:
        return {
            Tier.A: "Locally calibrated",
            Tier.B: "Regionally extrapolated",
            Tier.C: "Literature prior",
            Tier.D: "Contraindicated",
        }[self]

    @property
    def presentation(self) -> str:
        """How a value at this tier must be rendered (specification section 7.4)."""
        return {
            Tier.A: "value with confidence interval",
            Tier.B: "value as a range, calibration region named",
            Tier.C: "order-of-magnitude band, labelled indicative",
            Tier.D: "finding shown in place of the number",
        }[self]


@dataclass(frozen=True)
class Calibration:
    """Provenance of a parameter set as applied to one region.

    Attributes:
        tier: calibration tier.
        region: the region this statement applies to, e.g. "LT-coastal".
        source: where the parameters came from, e.g. "OLAMUR D3.2".
        calibrated_on: region the parameters were actually fitted to, if different.
        note: shown to the user verbatim. For tier D this replaces the number.
    """

    tier: Tier
    region: str
    source: str
    calibrated_on: str | None = None
    note: str | None = None

    @property
    def is_reportable(self) -> bool:
        """False when a numeric result must be suppressed in favour of the note."""
        return self.tier is not Tier.D

    def caveat(self) -> str:
        """One line for display beside the value."""
        if self.tier is Tier.D:
            return self.note or "Contraindicated for this region."
        if self.tier is Tier.C:
            return f"Indicative only - literature prior ({self.source}), no local validation."
        if self.tier is Tier.B:
            where = self.calibrated_on or "elsewhere in the Baltic"
            return f"Extrapolated - parameters calibrated on {where} ({self.source})."
        return f"Calibrated on {self.calibrated_on or self.region} pilot data ({self.source})."


@dataclass(frozen=True)
class Quantity:
    """A number that cannot be separated from its calibration status.

    Every public model function in this package returns Quantity (or a container of
    them) rather than a bare float, so that a value can never reach the interface
    without its provenance. Specification section 7.4, and risk register row
    "users read tier-C numbers as measurements".
    """

    value: float
    unit: str
    calibration: Calibration
    low: float | None = None
    high: float | None = None

    def __str__(self) -> str:
        if not self.calibration.is_reportable:
            return f"not applicable - {self.calibration.caveat()}"
        if self.low is not None and self.high is not None:
            return f"{self.low:.3g}-{self.high:.3g} {self.unit} [{self.calibration.tier.value}]"
        return f"{self.value:.3g} {self.unit} [{self.calibration.tier.value}]"

    def banded(self, factor: float = 3.0) -> Quantity:
        """Widen a point estimate into an order-of-magnitude band.

        Applied to tier C results before display, so that a literature prior is never
        shown with a precision it does not have.
        """
        if self.low is not None or self.high is not None:
            return self
        return Quantity(
            value=self.value,
            unit=self.unit,
            calibration=self.calibration,
            low=self.value / factor,
            high=self.value * factor,
        )


def for_display(q: Quantity) -> Quantity:
    """Apply the tier's presentation rule (specification section 7.4)."""
    if q.calibration.tier is Tier.C:
        return q.banded()
    return q
