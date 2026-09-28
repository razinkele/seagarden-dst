"""The English report is byte-identical before and after package I-a (spec test 10).

Captured here, in I-0, from a fixed date. The `Generated:` line also carries the core
version, which is normalised to `v*` so a release does not fail this test for a reason
that has nothing to do with wording. Lives under tests/ because tests/conftest.py is
where --snapshot-update is registered.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import date
from pathlib import Path

import pytest

# This file lives under tests/, which the `spatial` CI job collects WITHOUT the
# `shiny` extra installed (see .github/workflows/ci.yml). `-m` deselects only after
# collection, so a bare module-scope `import shiny` (via `app.modules.report` etc.)
# would kill collection for the whole job. Same pattern as tests/test_gridded.py's
# `pytest.importorskip("xarray")`.
pytest.importorskip("shiny")

from app.modules.report import render_report  # noqa: E402
from app.modules.results import run_assessment  # noqa: E402
from app.tests.test_app_smoke import _FakeState  # noqa: E402
from seagarden_dst import PLACEHOLDER_SITES, SiteContext, assess_site  # noqa: E402
from seagarden_dst.forcing import (  # noqa: E402
    DEFAULT_FORCING,
    Aggregation,
    Coverage,
    ForcingChoice,
    SiteReading,
    placeholder_choice,
)

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


def _check(golden_path: Path, current: str, pytestconfig) -> None:
    if pytestconfig.getoption("--snapshot-update", default=False):
        GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
        golden_path.write_text(current, encoding="utf-8")
        pytest.skip("golden report regenerated")
    assert golden_path.exists(), "run with --snapshot-update to create the golden reports"
    assert current == golden_path.read_text(encoding="utf-8"), (
        f"The English report for {golden_path.stem} changed. Package I-a must not change "
        "English wording; if this is I-0 or a deliberate rewording, regenerate with "
        "--snapshot-update and explain the diff in the commit."
    )


@pytest.mark.parametrize("region", sorted(PLACEHOLDER_SITES))
def test_the_english_report_matches_its_golden_file(region, pytestconfig):
    golden = GOLDEN_DIR / f"{region}.txt"
    current = _report(region)
    _check(golden, current, pytestconfig)


def _case_eutropy_bowtie() -> str:
    context = SiteContext.from_region("LT-lagoon", label="Curonian golden")
    result = assess_site(
        context,
        eutropy={"din_umol_l": 30.0, "dip_umol_l": 1.9, "label": "golden scenario"},
        bowtie={"Low": 0.2, "Moderate": 0.3, "High": 0.5},
    )
    return _normalise(
        render_report(result, placeholder_choice("golden fixture"), today=FIXED_TODAY)
    )


def _case_unsuitable_method() -> str:
    context = SiteContext.from_region("LT-coastal", label="LT-coastal golden")
    result = assess_site(
        context,
        species=["ulva"],
        methods={"ulva": "mini_farm_kit"},
    )
    return _normalise(
        render_report(result, placeholder_choice("golden fixture"), today=FIXED_TODAY)
    )


def _case_unassessable() -> str:
    from datetime import UTC, datetime

    reading = SiteReading(
        conditions=None,
        coverage=Coverage.CELL_INVALID,
        year=2024,
        aggregation=Aggregation.CONTAINING_CELL,
        nearest_valid_km=1.1,
        from_artifact=True,
    )
    context = SiteContext.from_reading(reading, label="Off-grid golden")
    result = assess_site(context)
    choice = ForcingChoice(
        source=DEFAULT_FORCING, kind="artifact", reason="", year=2025,
        built_on=datetime(2026, 9, 22, tzinfo=UTC), directory=None,
    )
    return _normalise(render_report(result, choice, today=FIXED_TODAY))


CASES: dict[str, Callable[[], str]] = {
    "case-eutropy-bowtie": _case_eutropy_bowtie,
    "case-unsuitable-method": _case_unsuitable_method,
    "case-unassessable": _case_unassessable,
}


@pytest.mark.parametrize("case", sorted(CASES))
def test_the_english_report_matches_its_golden_file_for_the_case(case, pytestconfig):
    golden = GOLDEN_DIR / f"{case}.txt"
    current = CASES[case]()
    _check(golden, current, pytestconfig)


def test_the_generated_line_uses_the_injected_date_not_the_clock():
    state = _FakeState(SiteContext.from_region("LT-coastal", label="Melnrage"))
    run_assessment(state)
    text = render_report(state.assessment.get(), today=date(2001, 2, 3))
    assert "Generated:   2001-02-03" in text
