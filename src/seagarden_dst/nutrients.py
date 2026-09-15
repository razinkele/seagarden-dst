"""Nutrient-removal and carbon accounting - specification section 7.

Converts a harvest into nitrogen, phosphorus and carbon removed from the water body,
using each species' own elemental fractions - `SpeciesParams.elemental`, read here
from `species.elemental` and defined per species in that species' own params file
under `params/species/`. There is no universal fraction: two illustrative examples,
both from OLAMUR D2.3, are

    Saccharina (kelp) DM -> 1% N, 0.17% P, 32% C
    mussel FW           -> 10.3% DM, 1.45% N, 0.083% P, 4.61% shell C

but Fucus, Chorda and Ulva each declare their own, different-valued fractions in
their own files - several marked ASSUMED, not fitted, not sourced. Treating the kelp
numbers above as a shared basis is exactly what let Fucus silently inherit
Saccharina's fractions unmarked, before that was caught.

Carbon is reported as carbon in harvested biomass, never as sequestration
(see shellfish.carbon_note).
"""

from __future__ import annotations

from dataclasses import dataclass

from .calibration import Quantity
from .params import SpeciesParams


@dataclass(frozen=True)
class NutrientRemoval:
    """What one harvest takes out of the water body."""

    nitrogen: Quantity  # kg N
    phosphorus: Quantity  # kg P
    carbon: Quantity  # kg C
    basis: str

    def as_rows(self) -> list[tuple[str, str]]:
        """Display rows, already carrying their calibration tier."""
        return [
            ("Nitrogen removed", str(self.nitrogen)),
            ("Phosphorus removed", str(self.phosphorus)),
            ("Carbon in harvested biomass", str(self.carbon)),
        ]


def _scaled(source: Quantity, fraction: float, unit: str) -> Quantity:
    """Apply an elemental fraction, preserving the band and the calibration."""
    return Quantity(
        value=source.value * fraction,
        unit=unit,
        calibration=source.calibration,
        low=None if source.low is None else source.low * fraction,
        high=None if source.high is None else source.high * fraction,
    )


def from_harvest(species: SpeciesParams, harvest: Quantity) -> NutrientRemoval:
    """Nutrient removal from a harvest quantity.

    `harvest` must be on the basis the species declares: dry weight for macroalgae,
    fresh weight for shellfish. The mismatch is caught here rather than producing a
    silently wrong number an order of magnitude out.
    """
    e = species.elemental
    expected_unit = "kg DW" if e.basis == "dry_weight" else "kg FW"
    if harvest.unit != expected_unit:
        raise ValueError(
            f"{species.key} expects harvest on {e.basis} ({expected_unit}), "
            f"got {harvest.unit!r}"
        )

    return NutrientRemoval(
        nitrogen=_scaled(harvest, e.nitrogen, "kg N"),
        phosphorus=_scaled(harvest, e.phosphorus, "kg P"),
        carbon=_scaled(harvest, e.carbon, "kg C"),
        basis=e.basis,
    )


def per_hectare(removal: NutrientRemoval, area_m2: float) -> NutrientRemoval:
    """Rescale a removal result to one hectare, for comparison across scales."""
    if area_m2 <= 0:
        raise ValueError("area_m2 must be positive")
    factor = 10_000.0 / area_m2
    return NutrientRemoval(
        nitrogen=_scaled(removal.nitrogen, factor, "kg N/ha"),
        phosphorus=_scaled(removal.phosphorus, factor, "kg P/ha"),
        carbon=_scaled(removal.carbon, factor, "kg C/ha"),
        basis=removal.basis,
    )
