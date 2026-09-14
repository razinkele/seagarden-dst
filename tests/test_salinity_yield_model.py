"""Saccharina follows OLAMUR D2.3's published form, which is not an ODE.

The salinity factor scales a maximum yield of 18.4 t FW/ha from Danish sites above
16 psu. The repository previously multiplied that factor into the growth rate of a
logistic ODE instead, which is a different model: at DK-belt the two differ by a factor
of 3.8, and a third reading (scaling b_max) differs from the second by 49%.
"""

from __future__ import annotations

import pytest

from seagarden_dst import PLACEHOLDER_SITES, default_parameters
from seagarden_dst.growth import harvest_biomass, salinity_indexed_yield


@pytest.fixture(scope="module")
def params():
    return default_parameters()


def test_the_published_form_reproduces_at_the_danish_pilot(params):
    """f(18) x 18.4 = 0.611 x 18.4 = 11.24 t FW/ha."""
    kelp = params.species["saccharina_latissima"]
    site = PLACEHOLDER_SITES["DK-belt"]

    factor = kelp.salinity.factor(site.salinity_psu)
    assert factor == pytest.approx(1.0 + (18.0 - 25.0) / 18.0, rel=1e-9)

    yield_fw = salinity_indexed_yield(kelp, site)
    assert yield_fw.unit == "t FW/ha"
    assert yield_fw.value == pytest.approx(11.24, abs=0.01)


def test_max_yield_is_no_longer_dead_data(params):
    """The parameter was declared, loaded and read by nothing."""
    kelp = params.species["saccharina_latissima"]
    site = PLACEHOLDER_SITES["DK-belt"]
    unscaled = salinity_indexed_yield(kelp, PLACEHOLDER_SITES["DK-belt"])
    assert unscaled.value < kelp.max_yield_t_fw_ha
    assert unscaled.value == pytest.approx(
        kelp.salinity.factor(site.salinity_psu) * kelp.max_yield_t_fw_ha, rel=1e-9
    )


def test_harvest_biomass_dispatches_on_the_yield_model(params):
    """Saccharina goes through the published form; the other three keep the ODE."""
    assert params.species["saccharina_latissima"].yield_model == "salinity_indexed"
    for key in ("fucus_vesiculosus", "ulva", "chorda_filum"):
        assert params.species[key].yield_model == "ode"

    kelp = params.species["saccharina_latissima"]
    site = PLACEHOLDER_SITES["DK-belt"]
    # 1 ha, so kg DW = t FW/ha * dry_matter * 1000
    harvest = harvest_biomass(kelp, site, area_m2=10_000.0)
    expected_kg = 11.24 * kelp.elemental.dry_matter * 1000.0
    assert harvest.value == pytest.approx(expected_kg, rel=1e-3)


def test_the_contraindication_rule_still_wins(params):
    """The published form returns a positive number below 16 psu. Tier D still suppresses
    it - the finding beats the formula, which is the whole point of specification 5.3."""
    kelp = params.species["saccharina_latissima"]
    harvest = harvest_biomass(kelp, PLACEHOLDER_SITES["EE-coastal"], area_m2=10_000.0)
    assert not harvest.calibration.is_reportable
    assert harvest.value == 0.0


def test_salinity_indexed_yield_itself_is_not_reportable_below_the_floor(params):
    """`salinity_indexed_yield` is a public function in its own right (the brief's
    Interfaces section names it directly), not only a step inside `harvest_biomass`.
    A caller who reaches it straight from the module must see the same tier D as a
    caller who goes through `harvest_biomass` - otherwise the guard added in
    `harvest_biomass` is enforcement at only one of the two number-producing layers,
    exactly the pattern commit 751de41 closed for the ODE path.

    DE-coastal is the case that actually exercises this: Saccharina carries no static
    tier D registry entry for it (only LT-coastal and PL-lagoon do), so it falls back
    to the 'default' tier C entry - the dynamic salinity-floor path is the only thing
    that can catch it, and only if `salinity_indexed_yield` consults it too.
    """
    kelp = params.species["saccharina_latissima"]
    site = PLACEHOLDER_SITES["DE-coastal"]
    assert site.salinity_psu < kelp.salinity.tolerance_floor_psu

    yield_fw = salinity_indexed_yield(kelp, site)
    assert not yield_fw.calibration.is_reportable
    assert yield_fw.calibration.tier.value == "D"
