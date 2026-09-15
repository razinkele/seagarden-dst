"""Shellfish yield banding, elemental accounting, and the carbon convention."""

from __future__ import annotations

import pytest

from seagarden_dst import PLACEHOLDER_SITES, default_parameters
from seagarden_dst.nutrients import from_harvest, per_hectare
from seagarden_dst.shellfish import (
    biomass_density,
    carbon_note,
    culture_mode,
    harvest,
    imta_sizing,
)


@pytest.fixture(scope="module")
def params():
    return default_parameters()


@pytest.fixture(scope="module")
def mussel(params):
    return params.species["mytilus"]


def test_culture_mode_follows_the_salinity_threshold(mussel):
    assert culture_mode(mussel, PLACEHOLDER_SITES["DK-belt"]) == "commercial"
    assert culture_mode(mussel, PLACEHOLDER_SITES["LT-coastal"]) == "mitigation"
    assert culture_mode(mussel, PLACEHOLDER_SITES["DE-coastal"]) == "mitigation"


def test_mitigation_yields_more_per_hectare_than_commercial(mussel):
    """Not a bug. Density is optimised for nutrient removal, not for size."""
    mitigation = harvest(mussel, PLACEHOLDER_SITES["LT-coastal"], area_ha=1.0)
    commercial = harvest(mussel, PLACEHOLDER_SITES["DK-belt"], area_ha=1.0)
    assert mitigation.mode == "mitigation"
    assert commercial.mode == "commercial"
    assert mitigation.fresh_weight.value > commercial.fresh_weight.value


def test_yield_is_reported_as_a_band_not_a_point(mussel):
    result = harvest(mussel, PLACEHOLDER_SITES["LT-coastal"], area_ha=2.0)
    q = result.fresh_weight
    assert q.low is not None and q.high is not None
    assert q.low < q.value < q.high
    assert q.low == pytest.approx(20.0 * 1000.0 * 2.0)
    assert q.high == pytest.approx(33.0 * 1000.0 * 2.0)


def test_commercial_density_is_lower_than_mitigation(mussel):
    mitigation = biomass_density(mussel, 1000.0, "mitigation")
    commercial = biomass_density(mussel, 1000.0, "commercial")
    assert commercial == pytest.approx(mitigation / 3.15)


def test_elemental_accounting_uses_the_published_fractions(mussel):
    result = harvest(mussel, PLACEHOLDER_SITES["LT-coastal"], area_ha=1.0)
    removal = from_harvest(mussel, result.fresh_weight)
    fw = result.fresh_weight.value
    assert removal.nitrogen.value == pytest.approx(fw * 0.0145)
    assert removal.phosphorus.value == pytest.approx(fw * 0.00083)
    assert removal.carbon.value == pytest.approx(fw * 0.0461)


def test_basis_mismatch_is_caught(params, mussel):
    """A dry-weight harvest passed to a fresh-weight species would be an order out."""
    from seagarden_dst.growth import harvest_biomass

    algal = harvest_biomass(
        params.species["ulva"], PLACEHOLDER_SITES["LT-coastal"], area_m2=100.0
    )
    with pytest.raises(ValueError, match="fresh_weight"):
        from_harvest(mussel, algal)


def test_per_hectare_rescaling(params):
    from seagarden_dst.growth import harvest_biomass

    species = params.species["ulva"]
    algal = harvest_biomass(species, PLACEHOLDER_SITES["LT-coastal"], area_m2=1000.0)
    removal = from_harvest(species, algal)
    scaled = per_hectare(removal, area_m2=1000.0)
    assert scaled.nitrogen.value == pytest.approx(removal.nitrogen.value * 10.0)
    assert scaled.nitrogen.unit == "kg N/ha"


def test_carbon_note_refuses_to_claim_sequestration():
    note = carbon_note()
    assert "Sequestration is not reported" in note
    assert "harvested biomass only" in note


def test_imta_heuristic():
    area, source = imta_sizing("phosphorus", low_p_feed=True)
    assert area == 0.8
    assert "OLAMUR" in source
    assert imta_sizing("both")[0] == 8.0


def test_mode_on_a_contraindicated_harvest_is_not_a_recommendation(params):
    """`.mode` describes the salinity band, not advice to cultivate.

    On the contraindicated path `harvest()` returns a real "commercial"/"mitigation"
    string beside a zero yield, so a caller reading `.mode` without first checking
    `fresh_weight.calibration.is_reportable` sees what reads as a recommendation for
    a pairing the tool is reporting as unusable. Inert today - `api._assess_one`
    discards `.mode`, and no shipped species reaches the branch at a placeholder
    site - which is exactly why it needs pinning rather than leaving to be discovered
    when something does read it.

    The field keeps its type: widening it to None would push the same question onto
    every caller. The contract asserted here is that `.mode` is only ever meaningful
    alongside a reportable calibration.
    """
    from dataclasses import replace

    mytilus = params.species["mytilus"]
    floor = mytilus.salinity_floor()
    assert floor is not None, "mytilus must resolve a salinity floor for this test to mean anything"
    floor_psu, _ = floor

    fresh = PLACEHOLDER_SITES["LT-coastal"]
    too_fresh = replace(fresh, salinity_psu=floor_psu - 1.0)

    result = harvest(mytilus, too_fresh, area_ha=0.1)
    assert not result.fresh_weight.calibration.is_reportable, (
        "the test site must actually be contraindicated"
    )
    assert result.fresh_weight.value == 0.0
    assert result.mode in {"commercial", "mitigation"}
    assert result.dry_matter_kg == 0.0 and result.density_kg_m3 == 0.0, (
        "mode must be the only non-zero field on a contraindicated harvest - every "
        "quantity that could be mistaken for a yield is zeroed"
    )
