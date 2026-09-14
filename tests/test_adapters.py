"""Optional engines must help when present and be harmless when not.

The house rule from `nid4ocean_dst.ses_signal`: an optional sibling engine never takes
the tool down with it, and never silently changes the ranking.
"""

from __future__ import annotations

import pytest

from seagarden_dst import BowtieUnavailable, EutropyUnavailable, SiteContext, assess_site
from seagarden_dst.bowtie_adapter import eutrophication_pressure, removal_framing
from seagarden_dst.eutropy_adapter import apply_nutrient_scenario, scenario_from_ensemble


@pytest.fixture
def lithuania():
    return SiteContext.from_region("LT-coastal")


@pytest.fixture
def lagoon():
    return SiteContext.from_region("PL-lagoon")


# --------------------------------------------------------------------- EUTROPY


def test_scenario_replaces_nutrients_only(lagoon):
    before = lagoon.conditions
    forced, note = apply_nutrient_scenario(
        lagoon, {"din_umol_l": 12.0, "dip_umol_l": 0.9, "label": "BSAP"}
    )
    assert forced.conditions.din_umol_l == 12.0
    assert forced.conditions.dip_umol_l == 0.9
    assert forced.conditions.salinity_psu == before.salinity_psu
    assert forced.conditions.depth_m == before.depth_m
    assert "BSAP" in note


def test_lagoon_model_applied_to_the_open_coast_says_so(lithuania):
    """The domain mismatch must reach the user, not a log file."""
    _forced, note = apply_nutrient_scenario(lithuania, {"din_umol_l": 9.0, "dip_umol_l": 0.5})
    assert "Curonian Lagoon box model" in note
    assert "scenario reasoning, not as a prediction" in note


def test_malformed_scenarios_are_refused(lagoon):
    with pytest.raises(EutropyUnavailable):
        apply_nutrient_scenario(lagoon, {"dip_umol_l": 0.5})
    with pytest.raises(EutropyUnavailable):
        apply_nutrient_scenario(lagoon, {"din_umol_l": "wet", "dip_umol_l": 0.5})
    with pytest.raises(EutropyUnavailable):
        apply_nutrient_scenario(lagoon, {"din_umol_l": -1.0, "dip_umol_l": 0.5})
    with pytest.raises(EutropyUnavailable):
        apply_nutrient_scenario(lagoon, [1, 2, 3])


def test_ensemble_lookup_is_exact_not_nearest():
    rows = [
        {"box": 19, "fN": 1.0, "fP": 1.0, "din_umol_l": 30.0, "dip_umol_l": 1.9},
        {"box": 19, "fN": 0.5, "fP": 0.5, "din_umol_l": 15.0, "dip_umol_l": 1.0},
    ]
    picked = scenario_from_ensemble(rows, box=19, f_n=0.5, f_p=0.5)
    assert picked["din_umol_l"] == 15.0
    # A nearest-neighbour match would quietly hand back a different scenario.
    with pytest.raises(EutropyUnavailable):
        scenario_from_ensemble(rows, box=19, f_n=0.6, f_p=0.5)


def test_bad_eutropy_input_does_not_break_the_assessment(lithuania):
    """The ranking must survive an unusable scenario, with the failure reported."""
    clean = assess_site(lithuania)
    degraded = assess_site(lithuania, eutropy={"nonsense": True})
    assert [o.species_key for o in degraded.ranked] == [o.species_key for o in clean.ranked]
    assert "EUTROPY forcing not applied" in degraded.caveats["nutrient forcing"]


# LT-coastal rather than the lagoon: this test needs a site with a non-empty
# ranking, and every species is now correctly contraindicated at 2.0 psu. What is
# under test here is the adapter, not where anything can be farmed. EUTROPY is a
# Curonian Lagoon model, so it is out-of-domain at LT-coastal - that caveat is
# asserted separately by test_lagoon_model_applied_to_the_open_coast_says_so.
def test_good_eutropy_input_changes_the_numbers(lithuania):
    lean = assess_site(lithuania, eutropy={"din_umol_l": 2.0, "dip_umol_l": 0.1})
    rich = assess_site(lithuania, eutropy={"din_umol_l": 40.0, "dip_umol_l": 2.5})
    lean_n = {o.species_key: o.nitrogen_value for o in lean.ranked}
    rich_n = {o.species_key: o.nitrogen_value for o in rich.ranked}
    shared = set(lean_n) & set(rich_n)
    assert shared, "expected at least one species assessable under both scenarios"
    assert any(rich_n[k] > lean_n[k] for k in shared), "more nutrients should grow more"


# ---------------------------------------------------------------------- bow-tie


def test_pressure_is_normalised(lagoon):
    values, _note = eutrophication_pressure(lagoon, {"Low": 2.0, "Moderate": 4.0, "High": 4.0})
    assert sum(values.values()) == pytest.approx(1.0)
    assert values["High"] == pytest.approx(0.4)


def test_pressure_accepts_the_wrapped_form(lagoon):
    values, note = eutrophication_pressure(
        lagoon,
        {"top_event": {"Low": 0.3, "Moderate": 0.25, "High": 0.45}, "label": "current loading"},
    )
    assert values["High"] == pytest.approx(0.45)
    assert "current loading" in note


def test_pressure_is_never_folded_into_the_ranking(lagoon):
    """Beside, never merged - the rule inherited from the NiD4OCEAN SES readings."""
    clean = assess_site(lagoon)
    with_pressure = assess_site(lagoon, bowtie={"Low": 0.2, "Moderate": 0.3, "High": 0.5})
    assert [o.nitrogen_value for o in clean.ranked] == [
        o.nitrogen_value for o in with_pressure.ranked
    ]
    assert with_pressure.pressure["High"] == pytest.approx(0.5)
    assert "never folded into it" in with_pressure.pressure_note


# LT-coastal rather than the lagoon: this test needs a site with a non-empty
# ranking, and every species is now correctly contraindicated at 2.0 psu. What is
# under test here is the adapter, not where anything can be farmed.
def test_malformed_bowtie_is_reported_not_raised(lithuania):
    result = assess_site(lithuania, bowtie={"Catastrophe": 1.0})
    assert result.pressure == {}
    assert "names none of" in result.pressure_note
    assert result.ranked, "the ranking is unaffected"


def test_bad_bowtie_shapes_are_refused(lagoon):
    for bad in ({"High": "lots"}, {"High": -0.2}, {"High": 0.0}, "not a mapping"):
        with pytest.raises(BowtieUnavailable):
            eutrophication_pressure(lagoon, bad)


def test_removal_framing_changes_with_pressure():
    high = removal_framing({"High": 0.47})
    low = removal_framing({"High": 0.12})
    assert "mitigation of an active problem" in high
    assert "maintenance rather than mitigation" in low
    assert removal_framing({}) == ""
