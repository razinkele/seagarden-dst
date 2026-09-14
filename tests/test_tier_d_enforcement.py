"""Tier D must be enforced where the number is produced, not only where it is orchestrated.

`api.assess_site()` consults `contraindication()` and excludes correctly, so the Shiny
app was never affected. `harvest_biomass()` did not, and it is the function the README
invites notebook and batch users to call. The rule was right, the enforcement was at the
wrong layer.
"""

from __future__ import annotations

import pytest

from seagarden_dst import PLACEHOLDER_SITES, default_parameters
from seagarden_dst.calibration import Tier
from seagarden_dst.growth import contraindication, harvest_biomass


@pytest.fixture(scope="module")
def params():
    return default_parameters()


def _below_floor(species):
    """Placeholder sites where this species' salinity floor is breached."""
    floor = species.salinity.tolerance_floor_psu if species.salinity else None
    if floor is None:
        return []
    return [s for s in PLACEHOLDER_SITES.values() if s.salinity_psu < floor]


def test_nothing_is_reportable_below_its_salinity_floor(params):
    """The leak, in executable form. Sugar kelp reported 4.52-40.7 kg DW at DE-coastal."""
    kelp = params.species["saccharina_latissima"]
    sites = _below_floor(kelp)
    assert len(sites) == 5, "expected five placeholder sites below the 16 psu floor"

    for site in sites:
        harvest = harvest_biomass(kelp, site, area_m2=1000.0)
        assert not harvest.calibration.is_reportable, (
            f"{site.region} at {site.salinity_psu} psu reported {harvest.value:.1f} kg DW "
            "for a species contraindicated at that salinity"
        )
        assert harvest.calibration.tier is Tier.D
        assert harvest.value == 0.0


def test_the_dynamic_rule_and_the_produced_tier_agree(params):
    """Whenever contraindication() says D, the number-producing path must say D too.

    These were two disconnected mechanisms: a static per-region registry and a dynamic
    salinity rule. This asserts they can no longer disagree.
    """
    for species in params.species.values():
        for site in PLACEHOLDER_SITES.values():
            contra = contraindication(species, site)
            if contra is None:
                continue
            if species.group == "macroalga":
                quantity = harvest_biomass(species, site, area_m2=1000.0)
            else:
                from seagarden_dst.shellfish import harvest

                quantity = harvest(species, site, area_ha=0.1).fresh_weight
            assert quantity.calibration.tier is Tier.D, (
                f"{species.key} at {site.region}: contraindication() says D, "
                f"the harvest path says {quantity.calibration.tier.value}"
            )
