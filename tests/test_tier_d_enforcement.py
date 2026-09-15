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
    """Placeholder sites where this species' salinity floor is breached.

    Routed through `salinity_floor()` rather than reading `species.salinity` directly:
    for a species whose floor lives only on `shellfish_yield` (Mytilus),
    `species.salinity` is `None` and a direct read would silently return `[]` - a test
    built on that would pass while asserting nothing. `salinity_floor()` is the one
    resolution path Ruling 2 exists to enforce; a helper that bypasses it reintroduces
    the "two resolution rules" problem in the test layer instead of the production one.
    """
    floor = species.salinity_floor()
    if floor is None:
        return []
    floor_psu, _basis = floor
    return [s for s in PLACEHOLDER_SITES.values() if s.salinity_psu < floor_psu]


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


def test_every_species_has_a_lower_salinity_bound(params):
    """The Szczecin Lagoon is 2.0 psu. Nothing shipped is cultivable there."""
    lagoon = PLACEHOLDER_SITES["PL-lagoon"]
    for species in params.species.values():
        contra = contraindication(species, lagoon)
        assert contra is not None, (
            f"{species.key} returns a confident yield at {lagoon.salinity_psu} psu"
        )


def test_an_assumed_floor_does_not_claim_an_observation(params):
    """`contraindication()` said 'cultivation failure has been observed at this salinity'
    for every species below its floor. For four of five that asserts a finding nobody
    made. Chorda is the test case: its coefficients are a structural analogue of Fucus
    and nothing about it has been observed anywhere."""
    chorda = params.species["chorda_filum"]
    lagoon = PLACEHOLDER_SITES["PL-lagoon"]

    assert chorda.salinity is not None
    assert chorda.salinity.floor_basis == "assumed"

    note = (contraindication(chorda, lagoon).note or "").lower()
    assert "observed" not in note
    assert "assumed" in note

    # Kelp's own registry carries an explicit tier D entry at PL-lagoon and at
    # LT-coastal (the OLAMUR Tagalaht finding, verbatim) - contraindication() returns
    # early on that static note before ever reaching the dynamic salinity-floor path,
    # so it cannot exercise floor_basis. DE-coastal (11.0 psu) has no such entry, falls
    # back to the "default" tier C registration, and is below the 16 psu floor - it
    # reaches the dynamic path this test is actually about.
    kelp = params.species["saccharina_latissima"]
    de_coastal = PLACEHOLDER_SITES["DE-coastal"]
    assert kelp.salinity.floor_basis == "observed"
    assert "observed" in (contraindication(kelp, de_coastal).note or "").lower()


def test_a_curated_tier_d_entry_requires_an_observed_floor(params):
    """Guards the ordering in `contraindication()`, which is deliberate and stays.

    `contraindication()` checks the static, per-region `calibration_for()` registry
    BEFORE `salinity_floor()`, and that order is correct: a curated, human-written
    finding for a specific region should always outrank a generic salinity threshold,
    not the other way around - reversing it would let a placeholder floor override
    documented evidence.

    But that ordering means a static tier D `CalibrationEntry` bypasses the whole
    `floor_basis` mechanism this task built: `contraindication()` returns the static
    note verbatim without ever calling `salinity_floor()`. Today every shipped tier D
    entry belongs to Saccharina, whose floor is `observed`, so no note is mismatched.
    Nothing stops a future maintainer from adding a curated tier D entry, worded as an
    observation, for a species whose floor is merely `assumed` - and contraindication()
    would show that over-claiming note straight through, since the static path never
    checks it.

    This test is the guard: any species carrying a tier D calibration entry must
    resolve an `observed` salinity floor. Add a tier D entry to an assumed-floor
    species and this goes red instead of the note quietly over-claiming.
    """
    for species in params.species.values():
        if not any(entry.tier is Tier.D for entry in species.calibration):
            continue
        floor = species.salinity_floor()
        assert floor is not None, (
            f"{species.key} has a tier D calibration entry but salinity_floor() "
            "resolves to None - a curated tier D finding needs a floor to back it"
        )
        _, basis = floor
        assert basis == "observed", (
            f"{species.key} has a tier D calibration entry but its salinity floor "
            f"basis is {basis!r}, not 'observed' - contraindication() will show this "
            "species' static tier D note without ever checking floor_basis, so an "
            "assumed floor here means the note can claim an observation nobody made"
        )
