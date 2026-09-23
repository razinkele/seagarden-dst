"""The record naming what the tool runs on, and the region-to-query helper (E§3.1, E§3.3)."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from seagarden_dst.forcing import (
    DEFAULT_FORCING,
    PLACEHOLDER_YEAR,
    SITE_COORDINATES,
    ForcingChoice,
    SiteQuery,
    placeholder_choice,
    region_query,
)


def test_the_placeholder_year_is_the_scaffolds_fixed_year():
    assert PLACEHOLDER_YEAR == 2024


def test_a_placeholder_choice_carries_its_reason_and_no_build_date():
    choice = placeholder_choice("no artifact at data/forcing", Path("data/forcing"))
    assert choice.kind == "placeholder" and choice.is_artifact is False
    assert choice.source is DEFAULT_FORCING
    assert choice.reason == "no artifact at data/forcing"
    assert choice.year == PLACEHOLDER_YEAR
    assert choice.built_on is None
    assert choice.directory == Path("data/forcing")


def test_the_choice_is_frozen():
    choice = placeholder_choice("x")
    with pytest.raises(dataclasses.FrozenInstanceError):
        choice.kind = "artifact"  # type: ignore[misc]


def test_an_artifact_choice_has_no_reason():
    with pytest.raises(ValueError, match="artifact choice carries no reason"):
        ForcingChoice(
            source=DEFAULT_FORCING, kind="artifact", reason="why?", year=2025,
            built_on=None, directory=None,
        )


def test_a_placeholder_choice_must_say_why():
    with pytest.raises(ValueError, match="placeholder choice must say why"):
        ForcingChoice(
            source=DEFAULT_FORCING, kind="placeholder", reason="", year=2024,
            built_on=None, directory=None,
        )


def test_a_coordinate_renders_as_wkt_lon_then_lat():
    assert SITE_COORDINATES["LT-lagoon"].as_wkt() == (
        f"POINT ({SITE_COORDINATES['LT-lagoon'].lon} {SITE_COORDINATES['LT-lagoon'].lat})"
    )


def test_a_region_with_a_coordinate_becomes_a_point_query_carrying_the_region():
    query = region_query("LT-lagoon", 2025)
    assert query == SiteQuery(
        geometry_wkt=SITE_COORDINATES["LT-lagoon"].as_wkt(), year=2025, region="LT-lagoon"
    )


@pytest.mark.parametrize("region", ["LT-coastal", "EE-coastal"])
def test_a_region_without_a_coordinate_yields_none_not_an_empty_geometry(region):
    assert region not in SITE_COORDINATES
    assert region_query(region, 2025) is None


def test_from_region_defaults_to_the_placeholder_year():
    import inspect

    from seagarden_dst import SiteContext

    assert inspect.signature(SiteContext.from_region).parameters["year"].default == PLACEHOLDER_YEAR


def test_a_context_carries_an_empty_source_note_by_default():
    from seagarden_dst import SiteContext
    from seagarden_dst.contracts import SOURCE_NOTE_NO_POSITION

    context = SiteContext.from_region("LT-lagoon")
    assert context.source_note == ""
    assert SOURCE_NOTE_NO_POSITION == (
        "no confirmed position; conditions are the sub-region placeholder"
    )
