"""The scale key is an identifier; the English sentence is a label (I§3)."""

from __future__ import annotations

import re

from seagarden_dst import DEFAULT_SCALE, SCALE_LABELS, SCALES, SiteContext, assess_site


def test_scale_keys_are_slugs_not_sentences():
    for key in SCALES:
        assert re.fullmatch(r"[a-z0-9_]+", key), f"{key!r} is prose, not an identifier"


def test_every_scale_has_exactly_one_label():
    assert set(SCALE_LABELS) == set(SCALES)


def test_labels_are_the_sentences_the_tool_showed_before_the_split():
    assert {k: str(v) for k, v in SCALE_LABELS.items()} == {
        "mini_farm_kit": "mini-farm kit",
        "community_farm_0_1_ha": "community farm (0.1 ha)",
        "community_farm_1_ha": "community farm (1 ha)",
        "small_commercial_5_ha": "small commercial (5 ha)",
    }
    assert SCALES["community_farm_0_1_ha"] == 1_000.0


def test_assess_site_defaults_to_the_named_default_scale():
    import inspect

    assert DEFAULT_SCALE in SCALES
    assert inspect.signature(assess_site).parameters["scale"].default == DEFAULT_SCALE


def test_the_old_prose_key_is_refused_loudly():
    import pytest

    with pytest.raises(KeyError, match="Unknown scale"):
        assess_site(SiteContext.from_region("LT-coastal"), scale="community farm (0.1 ha)")
