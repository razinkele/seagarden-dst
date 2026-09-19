"""§7's mechanism: a site whose conditions are unknown must block, not score.

"There is today no representation for a site whose conditions are unknown.
`SiteContext.conditions` becomes `SiteConditions | None` and `assess_site` returns early
with an explicit `unassessable` flag; the UI reads that flag to distinguish 'unsuitable'
from 'unassessed'." — data-layer design §7, which assigns this to package D.
"""

import pytest

from seagarden_dst import SiteContext
from seagarden_dst.api import assess_site
from seagarden_dst.forcing import Aggregation, Coverage, SiteReading


def _blocked(coverage=Coverage.CELL_INVALID, km=1.12):
    return SiteReading(
        conditions=None, coverage=coverage, year=2024,
        aggregation=Aggregation.CONTAINING_CELL, nearest_valid_km=km,
        from_artifact=True,
    )


def test_a_context_can_hold_no_conditions():
    context = SiteContext.from_reading(_blocked(), label="Off-grid polygon")
    assert context.conditions is None


def test_an_unassessable_site_returns_unassessable_and_never_a_verdict():
    """The failure this exists to prevent is a definitive negative manufactured from
    missing data — an UNSUITABLE that means 'we did not look'."""
    context = SiteContext.from_reading(_blocked(), label="Off-grid polygon")
    result = assess_site(context)
    assert result.unassessable is True
    assert result.ranked == []


def test_the_reason_and_distance_survive_into_the_result():
    """§6.2 requires the distance to the nearest valid cell to be reported, and §7 makes
    the block visible. A flag with no reason cannot be displayed usefully."""
    context = SiteContext.from_reading(_blocked(km=0.75), label="Off-grid polygon")
    result = assess_site(context)
    assert result.coverage is Coverage.CELL_INVALID
    assert result.nearest_valid_km == pytest.approx(0.75)


def test_a_missing_year_blocks_the_same_way():
    context = SiteContext.from_reading(
        _blocked(coverage=Coverage.YEAR_ABSENT, km=None), label="2019 query"
    )
    result = assess_site(context)
    assert result.unassessable is True
    assert result.coverage is Coverage.YEAR_ABSENT


def test_an_assessable_site_is_not_flagged():
    """The flag must discriminate, not be always-on."""
    context = SiteContext.from_region("LT-coastal")
    result = assess_site(context)
    assert result.unassessable is False
    assert result.ranked
