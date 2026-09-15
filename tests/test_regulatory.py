"""Regulatory record schema - specification section 9, data-layer package G.

The record set is empty until M12, so most of what can be tested here is the shape
and the two safety properties: an absent record must block rather than pass, and the
worked example must be impossible to serve as real law.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from seagarden_dst.forcing import PLACEHOLDER_SITES
from seagarden_dst.regulatory import (
    JURISDICTIONS,
    STALENESS_YEARS,
    RegulatoryRecord,
    default_registry,
    load_regulatory_records,
)
from seagarden_dst.suitability import Verdict, assess_legal

EXAMPLE_PATH = Path(__file__).resolve().parents[1] / "params" / "regulatory" / "example.yaml"

# Fixed, so the suite does not change behaviour on a calendar boundary. Every
# staleness assertion states its own `today` relative to the record's verified_on.
VERIFIED = date(2026, 9, 15)


@pytest.fixture(scope="module")
def example() -> RegulatoryRecord:
    with EXAMPLE_PATH.open(encoding="utf-8") as fh:
        return RegulatoryRecord(**yaml.safe_load(fh))


# --- the worked example round-trips (package G's done-when) ---------------------


def test_example_loads_and_round_trips(example):
    """Load YAML -> model -> dump -> same values. The G acceptance criterion."""
    raw = yaml.safe_load(EXAMPLE_PATH.read_text(encoding="utf-8"))
    dumped = example.model_dump(mode="json", exclude_defaults=False)

    # Dates survive as ISO strings; the raw YAML parses verified_on to a date object.
    assert dumped["verified_on"] == raw["verified_on"].isoformat()
    for key in ("jurisdiction", "illustrative", "source_note"):
        assert dumped[key] == raw[key]
    for key in ("authorities", "permits", "exclusions", "procedure",
                "assessment_triggers", "policy_hooks"):
        assert len(dumped[key]) == len(raw[key]), key

    assert RegulatoryRecord(**dumped) == example


def test_example_populates_every_section_of_spec_9_1(example):
    """A template with empty sections would not tell A2.2 what is wanted."""
    assert example.authorities
    assert example.permits
    assert example.exclusions
    assert example.procedure
    assert example.assessment_triggers
    assert example.policy_hooks


def test_example_carries_the_start_door_threshold(example):
    """Spec 9.2 calls the exemption threshold the most valuable fact for Start."""
    assert any(p.exempt_below for p in example.permits)


# --- an illustrative record can never be served as real ------------------------


def test_example_is_flagged_illustrative(example):
    assert example.illustrative is True
    assert example.jurisdiction == "EXAMPLE"
    assert example.jurisdiction not in JURISDICTIONS


def test_real_jurisdiction_cannot_be_marked_illustrative(example):
    payload = example.model_dump(mode="json")
    payload["jurisdiction"] = "LT"
    with pytest.raises(ValidationError, match="illustrative"):
        RegulatoryRecord(**payload)


def test_example_cannot_pose_as_real_law(example):
    """The dangerous direction: EXAMPLE content served without the flag."""
    payload = example.model_dump(mode="json")
    payload["illustrative"] = False
    with pytest.raises(ValidationError, match="illustrative"):
        RegulatoryRecord(**payload)


def test_registry_never_returns_the_example_for_a_real_jurisdiction():
    registry = load_regulatory_records()
    assert registry.example() is not None, "the worked example should be committed"
    for code in JURISDICTIONS:
        assert registry.for_jurisdiction(code) is None
    assert registry.for_jurisdiction("EXAMPLE") is None


# --- an absent record blocks, never passes -------------------------------------


def test_record_set_is_empty_for_all_four_jurisdictions():
    assert set(default_registry().missing()) == set(JURISDICTIONS)


def test_coverage_note_does_not_read_as_permissive():
    note = default_registry().coverage_note()
    assert "cannot be assessed" in note
    assert "not a finding that the site is clear" in note


def test_absent_layer_yields_unknown_not_suitable():
    """Package F2 owns the populated case; this guards the default it builds on."""
    site = PLACEHOLDER_SITES["LT-coastal"]
    constraint = assess_legal(site, permitting_layer=None)
    assert constraint.verdict is Verdict.UNKNOWN
    assert constraint.verdict is not Verdict.SUITABLE


def test_missing_directory_gives_an_empty_registry_not_an_error(tmp_path):
    registry = load_regulatory_records(tmp_path / "does-not-exist")
    assert registry.records == {}
    assert set(registry.missing()) == set(JURISDICTIONS)


# --- staleness, on an injected clock -------------------------------------------


def test_fresh_record_states_its_verification_date(example):
    note = example.staleness_note(VERIFIED)
    assert example.is_stale(VERIFIED) is False
    assert "2026-09-15" in note
    assert "more than" not in note


def test_record_goes_stale_after_the_threshold(example):
    just_under = date(VERIFIED.year + STALENESS_YEARS, VERIFIED.month, VERIFIED.day)
    just_over = date(just_under.year, just_under.month, just_under.day + 1)

    assert example.is_stale(just_under) is False, "exactly two years is not yet stale"
    assert example.is_stale(just_over) is True

    note = example.staleness_note(just_over)
    assert "more than 2 years ago" in note
    assert "re-check" in note


def test_staleness_never_reads_the_system_clock(example):
    """Regression guard: a model that called date.today() would ignore this."""
    assert example.is_stale(date(2099, 1, 1)) is True
    assert example.is_stale(date(2026, 9, 15)) is False


def test_leap_day_does_not_crash_the_threshold():
    record = RegulatoryRecord(
        jurisdiction="EXAMPLE",
        illustrative=True,
        verified_on=date(2024, 2, 29),
        source_note="leap-day fixture",
    )
    # A leap-day `today`: the two-year shift lands on 29 Feb 2026, which does not
    # exist, and folds to the 28th instead of raising. Four years on, so stale.
    assert record.is_stale(date(2028, 2, 29)) is True
    # Exactly two years after a leap-day verification, no fold needed on either side.
    assert record.is_stale(date(2026, 2, 28)) is False
    assert record.is_stale(date(2026, 3, 1)) is True


# --- referential integrity within a record -------------------------------------


def test_permit_must_name_a_listed_authority(example):
    payload = example.model_dump(mode="json")
    payload["permits"][0]["issuing_authority"] = "An Agency Not Listed Above"
    with pytest.raises(ValidationError, match="issuing_authority"):
        RegulatoryRecord(**payload)


def test_example_permits_all_name_listed_authorities(example):
    known = {a.name for a in example.authorities}
    assert {p.issuing_authority for p in example.permits} <= known
