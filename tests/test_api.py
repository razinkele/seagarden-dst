"""The single core entry point the UI consumes."""

from __future__ import annotations

import pytest

from seagarden_dst import SiteContext, Tier, assess_site, default_parameters


@pytest.fixture(scope="module")
def params():
    return default_parameters()


@pytest.fixture
def lithuania():
    return SiteContext.from_region("LT-coastal", label="Melnrage test")


def test_context_from_region_is_low_confidence(lithuania):
    """Placeholder conditions must never present as measured."""
    assert lithuania.confidence == "low"
    assert lithuania.region == "LT-coastal"
    assert lithuania.label == "Melnrage test"


def test_unknown_region_is_refused():
    with pytest.raises(KeyError):
        SiteContext.from_region("XX-nowhere")


def test_assess_site_ranks_and_carries_calibration(lithuania):
    result = assess_site(lithuania)
    assert result.ranked
    assert all(o.tier is Tier.C for o in result.ranked), "SE Baltic is all priors today"
    # Ranking is by nitrogen removed, descending.
    values = [o.nitrogen_value for o in result.ranked]
    assert values == sorted(values, reverse=True)


def test_contraindicated_species_is_excluded_with_a_reason(lithuania):
    """Sugar kelp in Lithuania: excluded and explained, not ranked last."""
    result = assess_site(lithuania)
    assert "saccharina_latissima" in result.excluded
    assert "failed" in result.excluded["saccharina_latissima"].lower()
    assert all(o.species_key != "saccharina_latissima" for o in result.ranked)


def test_kelp_is_not_excluded_in_the_danish_belt():
    result = assess_site(SiteContext.from_region("DK-belt"))
    assert "saccharina_latissima" not in result.excluded


def test_calibration_caveat_is_attached_when_priors_are_used(lithuania):
    result = assess_site(lithuania)
    assert "calibration" in result.caveats
    assert "indicative" in result.caveats["calibration"].lower()


def test_unknown_scale_is_refused(lithuania):
    with pytest.raises(KeyError, match="Unknown scale"):
        assess_site(lithuania, scale="enormous")


def test_species_subset_is_honoured(lithuania):
    result = assess_site(lithuania, species=["ulva"])
    assert [o.species_key for o in result.ranked] == ["ulva"]


def test_unknown_species_is_excluded_not_crashed(lithuania):
    result = assess_site(lithuania, species=["ulva", "kelpo_invento"])
    assert "kelpo_invento" in result.excluded
    assert [o.species_key for o in result.ranked] == ["ulva"]


def test_best_skips_unsuitable_options(lithuania):
    result = assess_site(lithuania)
    if result.best is not None:
        assert result.best.verdict != "unsuitable"
        assert result.best.is_reportable


def test_assessment_serialises_for_the_report(lithuania):
    payload = assess_site(lithuania).to_dict()
    assert payload["site"]["region"] == "LT-coastal"
    assert isinstance(payload["ranked"], list)
    if payload["ranked"]:
        first = payload["ranked"][0]
        assert first["tier"] == "C"
        assert isinstance(first["harvest"], str), "quantities serialise with their tier"


def test_every_region_assesses_without_raising():
    from seagarden_dst import REGIONS

    for region in REGIONS:
        result = assess_site(SiteContext.from_region(region))
        assert result.ranked or result.excluded
