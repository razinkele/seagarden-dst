"""The vocabulary D-a adds to `forcing.py`.

These types are read by the model core and by the app, so they must stay pure
pydantic/stdlib/numpy — no xarray, no shapely. `tests/test_gridded_isolation.py`
asserts that; these tests are about behaviour.
"""

import pytest

from seagarden_dst.forcing import (
    Aggregation,
    Coverage,
    PLACEHOLDER_SITES,
    SiteQuery,
    SiteReading,
)


def test_a_valid_reading_carries_its_conditions():
    reading = SiteReading(
        conditions=PLACEHOLDER_SITES["LT-coastal"],
        coverage=Coverage.VALID,
        year=2024,
        aggregation=Aggregation.CONTAINING_CELL,
    )
    assert reading.conditions is not None
    assert reading.coverage is Coverage.VALID


def test_a_blocked_reading_carries_the_reason_and_the_distance():
    """A bare `SiteConditions | None` says nothing about WHY, and §6.2 requires the
    distance to the nearest valid cell to be surfaced. That is the whole reason this
    record exists rather than an Optional."""
    reading = SiteReading(
        conditions=None,
        coverage=Coverage.CELL_INVALID,
        year=2024,
        aggregation=Aggregation.CONTAINING_CELL,
        nearest_valid_km=1.12,
    )
    assert reading.conditions is None
    assert reading.coverage is Coverage.CELL_INVALID
    assert reading.nearest_valid_km == pytest.approx(1.12)


def test_a_reading_says_whether_it_came_from_an_artifact():
    """§7's first row requires a banner naming what the tool is running on. The banner
    reads this, rather than the app guessing from which object it holds."""
    placeholder = SiteReading(
        conditions=PLACEHOLDER_SITES["LT-coastal"], coverage=Coverage.VALID,
        year=2024, aggregation=Aggregation.CONTAINING_CELL,
    )
    assert placeholder.from_artifact is False


def test_the_three_coverage_states_are_distinct():
    assert len({Coverage.VALID, Coverage.CELL_INVALID, Coverage.YEAR_ABSENT}) == 3


def test_the_provisional_aggregation_is_nameable():
    """D-b replaces the method, not the plumbing. A result computed the provisional way
    has to say so, the way a calibration tier says what a number rests on."""
    assert Aggregation.UNWEIGHTED_MEAN.value == "unweighted_mean"
    assert Aggregation.SALINITY_WEIGHTED.value == "salinity_weighted"


def test_a_query_carries_geometry_as_wkt_not_a_shapely_object():
    """`shapely` is in the `spatial` extra. A shapely geometry here would drag that
    extra into the model core, which is the failure this repository shipped on
    2026-09-17 with a conda-only import at module scope."""
    query = SiteQuery(geometry_wkt="POINT (21.13 55.67)", year=2024)
    assert isinstance(query.geometry_wkt, str)
    assert query.region is None


def test_a_query_may_name_a_region_instead_of_a_geometry():
    """The placeholder path has a region and no position."""
    query = SiteQuery(geometry_wkt="", year=2024, region="LT-coastal")
    assert query.region == "LT-coastal"


def test_the_placeholder_satisfies_the_widened_protocol():
    from seagarden_dst.forcing import ForcingSource, PlaceholderForcing

    assert isinstance(PlaceholderForcing(), ForcingSource)


def test_the_placeholder_answers_a_region_query():
    from seagarden_dst.forcing import PlaceholderForcing

    reading = PlaceholderForcing().reading_at(
        SiteQuery(geometry_wkt="", year=2024, region="LT-coastal")
    )
    assert reading.coverage is Coverage.VALID
    assert reading.aggregation is Aggregation.CONTAINING_CELL
    assert reading.from_artifact is False
    assert reading.conditions is PLACEHOLDER_SITES["LT-coastal"]


def test_the_placeholder_never_blocks():
    """It has no artifact, so it has no coverage to be missing. Its conditions are
    invented and say so through the calibration tiers, not through Coverage."""
    from seagarden_dst.forcing import PlaceholderForcing

    for region in PLACEHOLDER_SITES:
        reading = PlaceholderForcing().reading_at(
            SiteQuery(geometry_wkt="", year=2024, region=region)
        )
        assert reading.is_assessable


def test_an_unknown_region_still_raises_from_the_placeholder():
    """`conditions_for` raised KeyError for an unknown region and callers rely on it.
    Widening the protocol must not turn that into a silent blocked reading, which would
    hide a typo as a coverage failure."""
    from seagarden_dst.forcing import PlaceholderForcing

    with pytest.raises(KeyError, match="No placeholder conditions"):
        PlaceholderForcing().reading_at(
            SiteQuery(geometry_wkt="", year=2024, region="XX-nowhere")
        )


def test_daily_forcing_takes_a_year():
    """§6.2: the artifact carries one monthly field per year, so the series depends on
    which year is asked for. The placeholder ignores it — it has one invented year —
    but the signature has to carry it or `GriddedForcing` cannot satisfy the protocol."""
    from seagarden_dst.forcing import PlaceholderForcing

    days, par, temp, din = PlaceholderForcing().daily_forcing(
        PLACEHOLDER_SITES["LT-coastal"], (4, 9), 2024
    )
    assert len(days) == len(par) == len(temp) == len(din)

