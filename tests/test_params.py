"""Parameter files must load, validate, and declare their calibration honestly."""

from __future__ import annotations

import pytest

from seagarden_dst import PLACEHOLDER_SITES, default_parameters
from seagarden_dst.calibration import Tier
from seagarden_dst.growth import simulate

# Every anchor's `basis` string reads "per 6 m2 cage, April-October cycle" (OLAMUR
# D3.2, Tagalaht Bay). Parsing that free-text field for the area would be more
# fragile than naming the number once, here, next to where it is used.
FUCUS_ANCHOR_CAGE_M2 = 6.0


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


def test_assessment_thresholds_are_data_not_code():
    """Specification 1's premise is that coefficients live in params/. These three decide
    suitability verdicts and lived in Python defaults."""
    import inspect

    from seagarden_dst import suitability

    source = inspect.getsource(suitability)
    assert "0.35" not in source, "salinity factor floor still hard-coded"
    assert "= 0.5" not in source, "yield floor still hard-coded"

    assessment = default_parameters().assessment
    assert assessment.salinity_factor_floor == 0.35
    assert assessment.yield_floor_kg_dw_per_m2 == 0.5


def test_the_yield_floor_message_does_not_claim_the_user_set_it():
    """Specification 5.2 says the floor is user-set. No user can set it. Until package E
    plumbs a control, the text must say 'default' rather than 'set for this assessment'."""
    import inspect

    from seagarden_dst import suitability

    assert "set for this assessment" not in inspect.getsource(suitability)


def test_upper_temp_decline_is_data_not_a_hard_coded_constant(params):
    """The supra-optimal decline width lived as a bare `3.0` inside `f_temperature`."""
    for key in ("chorda_filum", "fucus_vesiculosus", "ulva"):
        assert params.species[key].growth.upper_temp_decline_c == 3.0


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


def test_the_tagalaht_anchor_is_data_with_a_stated_basis():
    """The only published anchor the SE Baltic parameterisation has lived in prose in two
    documents and a test docstring, with its basis unstated - which is why the nitrogen
    arm could be out by several times without anyone being able to say against what."""
    fucus = default_parameters().species["fucus_vesiculosus"]
    assert fucus.anchors, "Fucus carries no anchors block"

    quantities = {a.quantity for a in fucus.anchors}
    assert {"dry_weight", "carbon", "nitrogen", "phosphorus"} <= quantities

    for anchor in fucus.anchors:
        assert anchor.basis, f"{anchor.quantity} anchor has no stated basis"
        assert anchor.source
        assert anchor.low <= anchor.high


def test_b_max_is_not_read_off_the_anchor_it_is_validated_against():
    """b_max = 5200 was the anchor's own upper bound, so the model could not overshoot
    the range it is checked against. Either it is independently sourced, or it says it
    is assumed - silence is what made the circularity invisible."""
    fucus = default_parameters().species["fucus_vesiculosus"]
    anchor = next(a for a in fucus.anchors if a.quantity == "dry_weight")
    if fucus.growth.b_max == anchor.high:
        assert fucus.growth.b_max_basis == "assumed_from_anchor", (
            "b_max equals the anchor's upper bound and does not say so"
        )


def test_every_anchor_flag_matches_what_the_model_actually_produces():
    """`reconciles` must be derived, not declared.

    The dry-weight flag was wrong on the first attempt precisely because nothing
    recomputed it. A flag a human maintains by hand, in a file inviting edits to the
    fractions it depends on, is a claim waiting to go stale. `reconciles` answers one
    specific question - does *this tool's model output* land inside the published
    range - not whether the elemental fractions are mutually consistent with each
    other (that is a different check, computed in this file's `notes:` block).
    """
    fucus = default_parameters().species["fucus_vesiculosus"]
    modelled = simulate(fucus, PLACEHOLDER_SITES["EE-coastal"]).final_biomass
    actual = {
        "dry_weight": modelled,
        "carbon": modelled * FUCUS_ANCHOR_CAGE_M2 * fucus.elemental.carbon / 1000.0,
        "nitrogen": modelled * FUCUS_ANCHOR_CAGE_M2 * fucus.elemental.nitrogen / 1000.0,
        "phosphorus": modelled * FUCUS_ANCHOR_CAGE_M2 * fucus.elemental.phosphorus,
    }
    for anchor in fucus.anchors:
        inside = anchor.low <= actual[anchor.quantity] <= anchor.high
        assert anchor.reconciles == inside, (
            f"{anchor.quantity}: model gives {actual[anchor.quantity]:.4g} {anchor.unit} "
            f"against {anchor.low}-{anchor.high}, so reconciles should be {inside}"
        )
