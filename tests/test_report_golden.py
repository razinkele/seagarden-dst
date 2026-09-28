"""The English report is byte-identical before and after package I-a (spec test 10).

Captured here, in I-0, from a fixed date. The `Generated:` line also carries the core
version, which is normalised to `v*` so a release does not fail this test for a reason
that has nothing to do with wording. Lives under tests/ because tests/conftest.py is
where --snapshot-update is registered.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest

from app.modules.report import render_report
from app.modules.results import run_assessment
from app.tests.test_app_smoke import _FakeState
from seagarden_dst import PLACEHOLDER_SITES, SiteContext
from seagarden_dst.forcing import placeholder_choice

GOLDEN_DIR = Path(__file__).resolve().parent / "golden" / "reports"
FIXED_TODAY = date(2026, 9, 28)


def _normalise(text: str) -> str:
    return re.sub(r"core v\S+", "core v*", text)


def _report(region: str) -> str:
    state = _FakeState(SiteContext.from_region(region, label=f"{region} golden"))
    run_assessment(state)
    return _normalise(
        render_report(
            state.assessment.get(), placeholder_choice("golden fixture"), today=FIXED_TODAY
        )
    )


@pytest.mark.parametrize("region", sorted(PLACEHOLDER_SITES))
def test_the_english_report_matches_its_golden_file(region, pytestconfig):
    golden = GOLDEN_DIR / f"{region}.txt"
    current = _report(region)
    if pytestconfig.getoption("--snapshot-update", default=False):
        GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
        golden.write_text(current, encoding="utf-8")
        pytest.skip("golden report regenerated")
    assert golden.exists(), "run with --snapshot-update to create the golden reports"
    assert current == golden.read_text(encoding="utf-8"), (
        f"The English report for {region} changed. Package I-a must not change English "
        "wording; if this is I-0 or a deliberate rewording, regenerate with "
        "--snapshot-update and explain the diff in the commit."
    )


def test_the_generated_line_uses_the_injected_date_not_the_clock():
    state = _FakeState(SiteContext.from_region("LT-coastal", label="Melnrage"))
    run_assessment(state)
    text = render_report(state.assessment.get(), today=date(2001, 2, 3))
    assert "Generated:   2001-02-03" in text
