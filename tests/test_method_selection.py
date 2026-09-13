"""Default cultivation-method selection.

Regression tests for a bug the first visual run exposed: every macroalga defaulted to
the 6 m2 mini-farm kit, whose depth window is 2-10 m, so at a 12 m site the entire
ranking read "unsuitable" for a reason that was an artefact of the default rather
than a fact about the place.
"""

from __future__ import annotations

import pytest

from seagarden_dst import PLACEHOLDER_SITES, SCALES, SiteContext, assess_site, default_parameters
from seagarden_dst.api import select_method


@pytest.fixture(scope="module")
def params():
    return default_parameters()


def test_default_respects_site_depth(params):
    """A 12 m site must not default to a method rated 2-10 m."""
    site = PLACEHOLDER_SITES["LT-coastal"]   # 12 m
    method = select_method(params.species["ulva"], params, site, SCALES["community farm (0.1 ha)"])
    assert method is not None
    assert method.min_depth_m <= site.depth_m <= method.max_depth_m


def test_default_respects_the_requested_scale(params):
    """A 0.1 ha farm must not be modelled as a citizen-science kit."""
    site = PLACEHOLDER_SITES["LT-coastal"]
    kit = select_method(params.species["ulva"], params, site, SCALES["mini-farm kit"])
    farm = select_method(params.species["ulva"], params, site, SCALES["community farm (0.1 ha)"])
    assert kit.area_m2_per_unit <= farm.area_m2_per_unit
    assert farm.area_m2_per_unit <= SCALES["community farm (0.1 ha)"]


def test_shallow_lagoon_gets_a_shallow_method(params):
    site = PLACEHOLDER_SITES["PL-lagoon"]    # 4 m
    method = select_method(params.species["ulva"], params, site, SCALES["community farm (0.1 ha)"])
    assert method.min_depth_m <= site.depth_m <= method.max_depth_m


def test_shellfish_get_a_shellfish_method(params):
    site = PLACEHOLDER_SITES["DK-belt"]
    method = select_method(params.species["mytilus"], params, site, SCALES["community farm (1 ha)"])
    assert "shellfish" in method.suits_groups


def test_no_workable_depth_still_returns_something(params):
    """Better to assess and fail honestly on depth than to exclude the species."""
    from dataclasses import replace

    abyss = replace(PLACEHOLDER_SITES["LT-coastal"], depth_m=400.0)
    method = select_method(params.species["ulva"], params, abyss, SCALES["community farm (0.1 ha)"])
    assert method is not None


def test_depth_is_no_longer_the_binding_constraint_at_a_normal_site():
    """The end-to-end shape of the bug: a 12 m Lithuanian site should not report
    every macroalga as unsuitable on depth."""
    result = assess_site(SiteContext.from_region("LT-coastal"))
    algae = [o for o in result.ranked if o.species_key != "mytilus"]
    assert algae
    assert not any(
        "outside the workable window" in o.binding_constraint for o in algae
    ), "default method is fighting the site depth again"


def test_explicit_override_is_still_honoured():
    result = assess_site(
        SiteContext.from_region("LT-coastal"),
        species=["ulva"],
        methods={"ulva": "mini_farm_kit"},
    )
    assert result.ranked[0].method_key == "mini_farm_kit"
