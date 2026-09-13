"""Suitability must be a minimum, and an absent regulatory layer must block."""

from __future__ import annotations

import pytest

from seagarden_dst import PLACEHOLDER_SITES, SCALES, Scenario, compare, default_parameters
from seagarden_dst.forcing import SiteConditions
from seagarden_dst.suitability import Verdict, assess


@pytest.fixture(scope="module")
def params():
    return default_parameters()


def test_missing_regulatory_layer_yields_unknown_not_suitable(params):
    """The failure mode this guards against is silently passing an unassessed site."""
    result = assess(
        PLACEHOLDER_SITES["LT-coastal"],
        params.species["ulva"],
        params.methods["floating_longline"],
        permitting_layer=None,
    )
    assert result.verdict is Verdict.UNKNOWN
    assert "Legal permissibility" in result.explain()


def test_one_fatal_constraint_dominates_a_good_site(params):
    """A weighted index would average this away. The minimum must not."""
    result = assess(
        PLACEHOLDER_SITES["LT-coastal"],
        params.species["saccharina_latissima"],
        params.methods["floating_longline"],
    )
    assert result.verdict is Verdict.UNSUITABLE
    assert "Environmental tolerance" in result.explain()


def test_depth_outside_the_method_window_is_fatal(params):
    shallow = SiteConditions(
        region="LT-coastal",
        salinity_psu=7.0,
        mean_temp_c=10.5,
        summer_temp_c=19.0,
        winter_temp_c=2.0,
        surface_par=420.0,
        din_umol_l=6.0,
        dip_umol_l=0.6,
        depth_m=1.0,  # below every method's minimum
        significant_wave_m=0.4,
    )
    result = assess(shallow, params.species["ulva"], params.methods["floating_longline"])
    assert result.verdict is Verdict.UNSUITABLE
    assert "Depth" in result.explain()


def test_method_species_mismatch_is_rejected(params):
    result = assess(
        PLACEHOLDER_SITES["LT-coastal"],
        params.species["mytilus"],
        params.methods["floating_longline"],  # macroalgae only
    )
    assert result.verdict is Verdict.UNSUITABLE
    assert "does not support" in result.explain()


def test_binding_constraint_is_the_worst_one(params):
    result = assess(
        PLACEHOLDER_SITES["LT-coastal"],
        params.species["saccharina_latissima"],
        params.methods["floating_longline"],
    )
    binding = result.binding_constraint
    assert binding is not None
    assert binding.verdict is Verdict.UNSUITABLE


def test_comparison_table_shape_and_calibration_column(params):
    site = PLACEHOLDER_SITES["LT-coastal"]
    scenarios = [
        Scenario(
            label=f"{key} mini",
            species=params.species[key],
            method=params.methods["mini_farm_kit"]
            if params.species[key].group == "macroalga"
            else params.methods["mussel_socks"],
            site=site,
            area_m2=SCALES["mini-farm kit"],
        )
        for key in ("ulva", "fucus_vesiculosus", "chorda_filum")
    ]
    table = compare(scenarios)
    assert len(table) == 3
    assert "Calibration" in table.columns
    assert set(table["Calibration"]) == {"Literature prior"}


def test_comparison_panel_takes_at_most_four(params):
    site = PLACEHOLDER_SITES["LT-coastal"]
    scenario = Scenario(
        label="x",
        species=params.species["ulva"],
        method=params.methods["mini_farm_kit"],
        site=site,
        area_m2=6.0,
    )
    with pytest.raises(ValueError, match="at most 4"):
        compare([scenario] * 5)

    # The Plan door's species overview is a different thing and lifts the cap.
    assert len(compare([scenario] * 5, limit=None)) == 5
