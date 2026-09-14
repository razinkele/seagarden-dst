"""Parameter files must load, validate, and declare their calibration honestly."""

from __future__ import annotations

import pytest

from seagarden_dst import default_parameters
from seagarden_dst.calibration import Tier


@pytest.fixture(scope="module")
def params():
    return default_parameters()


def test_all_species_load(params):
    assert set(params.species) == {
        "chorda_filum",
        "fucus_vesiculosus",
        "mytilus",
        "saccharina_latissima",
        "ulva",
    }


def test_methods_load(params):
    assert "mini_farm_kit" in params.methods
    assert params.methods["mini_farm_kit"].area_m2_per_unit == 6.0


def test_application_form_species_are_flagged(params):
    """Ulva and mussels are the species the AF actually names."""
    named = {k for k, v in params.species.items() if v.in_application_form}
    assert named == {"ulva", "mytilus"}


def test_every_species_has_a_calibration_fallback(params):
    """An unknown region must resolve to a literature prior, never to silence."""
    for species in params.species.values():
        calibration = species.calibration_for("XX-nowhere")
        assert calibration.tier in {Tier.A, Tier.B, Tier.C, Tier.D}
        assert calibration.source


def test_no_south_baltic_species_claims_local_calibration(params):
    """Tier A means fitted to SeaGarden pilot data, which does not exist yet.

    This test is expected to be updated - not deleted - when A3.4 data arrives and
    the first parameter set is promoted in the M24-30 window.
    """
    for species in params.species.values():
        for region in ("LT-coastal", "PL-coastal", "PL-lagoon"):
            assert species.calibration_for(region).tier is not Tier.A


def test_chorda_ships_but_stays_uncalibrated(params):
    """Decision D1: Chorda ships in v1 on assumed analogue parameters.

    It is the species KU will actually cultivate in Lithuania, so it is carried -
    but it has no published growth model, and these coefficients are assumed by
    analogy with Fucus rather than fitted. That makes its tier C status load-bearing:
    it is the only thing standing between an assumed curve and a user reading it as
    an estimate.

    Promote this ONLY when the coefficients have been fitted to WP3 A3.4 harvest
    data, and update this test in the same commit as the parameter file.
    """
    chorda = params.species["chorda_filum"]
    assert chorda.group == "macroalga"
    assert chorda.growth is not None, "Chorda must ship with a runnable growth model"

    for region in params_regions():
        calibration = chorda.calibration_for(region)
        assert calibration.tier is Tier.C, f"Chorda must remain tier C in {region}"
        assert "analogue" in calibration.source.lower()
        assert "not fitted" in (calibration.note or "").lower()


def params_regions() -> tuple[str, ...]:
    from seagarden_dst import REGIONS

    return tuple(REGIONS)


def test_macroalgae_are_on_dry_weight_and_shellfish_on_fresh(params):
    for species in params.species.values():
        if species.group == "macroalga":
            assert species.elemental.basis == "dry_weight"
        else:
            assert species.elemental.basis == "fresh_weight"
            assert species.elemental.dry_matter is not None


def test_fucus_does_not_silently_carry_kelp_stoichiometry():
    """Fucus's elemental fractions were byte-identical to Saccharina's, which OLAMUR
    labels 'Kelp DM'. Either they are sourced to Fucus, or they say they are assumed."""
    params = default_parameters()
    fucus = params.species["fucus_vesiculosus"]
    kelp = params.species["saccharina_latissima"]

    identical = (
        fucus.elemental.nitrogen == kelp.elemental.nitrogen
        and fucus.elemental.phosphorus == kelp.elemental.phosphorus
        and fucus.elemental.carbon == kelp.elemental.carbon
    )
    assert not identical, (
        "Fucus is running on kelp stoichiometry. Re-source the fractions, or mark them "
        "assumed_from and say so."
    )
