# Package I-0 — Identifier Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Separate every English sentence the code uses as an *identifier* (scale keys, caveat keys, verdict display) from its label, so that package I-a can translate labels without touching state keys, and capture the English report as a golden file that I-a must leave byte-identical.

**Architecture:** Pure refactor. `SCALES` gets slug keys and a sibling `SCALE_LABELS: dict[str, str]`; `assess_site`'s `caveats` dict gets slug keys and a sibling `CAVEAT_LABELS`; `Verdict` gets a `label` property. `render_report` takes an injected `today`. Nothing a user sees changes; the golden snapshot is expected not to move.

**Tech Stack:** Python 3.11, pytest, ruff. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-28-package-i-internationalisation-design.md` — I§3 and I§8 test 10.

## Global Constraints

- Run every Python command with `micromamba run -n shiny` and `MKL_THREADING_LAYER=SEQUENTIAL` set (the `shiny` env's numpy/MKL OpenMP crash kills pytest at collection otherwise). In Git Bash: `MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest ...`.
- The working tree is shared with other sessions: never stash, never leave work uncommitted between tasks.
- Every commit message ends with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- English output is unchanged: `pytest` must be green after every task without regenerating `tests/golden/assessments.json`. If that file wants to change, stop and report; the spec (I§3) expected only label changes and this plan finds none, because the golden's scenarios half labels scenarios by species key, not by scale.
- `ruff check .` clean after every task (`line-length = 100`).
- No `Message` type, no catalogue, no i18n import anywhere in I-0. Labels are `str`.

## Review Focus

1. **A scale slug reaching the screen.** The sidebar status sentence in `app.py` formats `state.scale.get()` directly; after the rename it would show `community_farm_0_1_ha`. Test in Task 2.
2. **`Verdict.label` changing the report text.** If `label` capitalised or reworded, the report and every `"unsuitable" in text` assertion would move. Task 4 pins `label == value` for every member.
3. **`render_report` called without `today` somewhere in the app.** A `TypeError` in a render callback shows as a blank panel, not a traceback. Task 5 makes `today` keyword-only and greps every call site.
4. **The English report golden capturing a machine-dependent line.** The `Generated:` line carries the version; Task 5's test normalises it and passes a fixed date.
5. **`assess_site(scale="community farm (0.1 ha)")` from an external caller.** The core is a public package; an old key now raises `KeyError("Unknown scale ...")`, which is the behaviour the existing `test_unknown_scale_is_refused` already pins. Task 1 records the rename in CHANGELOG so a notebook user finds it.

---

### Task 1: Scale slugs and `SCALE_LABELS` in the core

**Files:**
- Modify: `src/seagarden_dst/scenarios.py:27-34`, `:148-173`
- Modify: `src/seagarden_dst/api.py:119`
- Modify: `src/seagarden_dst/__init__.py:53`, `:63`
- Modify: `tests/test_method_selection.py:25-56`, `tests/test_suitability.py:89`, `tests/test_golden_snapshot.py:74`
- Test: `tests/test_scenarios_scales.py` (create)

**Interfaces:**
- Produces: `SCALES: dict[str, float]` keyed `mini_farm_kit | community_farm_0_1_ha | community_farm_1_ha | small_commercial_5_ha`; `SCALE_LABELS: dict[str, str]` with the same keys and today's English strings as values; `DEFAULT_SCALE = "community_farm_0_1_ha"`. All three exported from `seagarden_dst`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_scenarios_scales.py
"""The scale key is an identifier; the English sentence is a label (I§3)."""

from __future__ import annotations

import re

from seagarden_dst import DEFAULT_SCALE, SCALE_LABELS, SCALES, assess_site, SiteContext


def test_scale_keys_are_slugs_not_sentences():
    for key in SCALES:
        assert re.fullmatch(r"[a-z0-9_]+", key), f"{key!r} is prose, not an identifier"


def test_every_scale_has_exactly_one_label():
    assert set(SCALE_LABELS) == set(SCALES)


def test_labels_are_the_sentences_the_tool_showed_before_the_split():
    assert SCALE_LABELS == {
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest tests/test_scenarios_scales.py -v`
Expected: FAIL at import — `ImportError: cannot import name 'DEFAULT_SCALE'`.

- [ ] **Step 3: Rename the keys and add the labels in `scenarios.py`**

Replace lines 27–34 with:

```python
#: Named scales, in m2, keyed by IDENTIFIER. The mini-farm figure is the OLAMUR cage
#: size, which is also the order of the A3.5 citizen-science kit. The keys are slugs
#: because they are state: `AppState.scale`, `assess_site(scale=...)` and the door
#: defaults all hold one. What a user reads is `SCALE_LABELS[key]` (I§3), and package
#: I-a translates that table without moving a key.
SCALES: dict[str, float] = {
    "mini_farm_kit": 6.0,
    "community_farm_0_1_ha": 1_000.0,
    "community_farm_1_ha": 10_000.0,
    "small_commercial_5_ha": 50_000.0,
}

#: English label per scale key — the only place the sentence lives.
SCALE_LABELS: dict[str, str] = {
    "mini_farm_kit": "mini-farm kit",
    "community_farm_0_1_ha": "community farm (0.1 ha)",
    "community_farm_1_ha": "community farm (1 ha)",
    "small_commercial_5_ha": "small commercial (5 ha)",
}

#: The scale `assess_site` and `default_scenarios` assume when none is asked for.
DEFAULT_SCALE = "community_farm_0_1_ha"
```

In `default_scenarios` (line 149) change the signature to `scale: str = DEFAULT_SCALE` and the label (line 166) to `label=f"{species.common_name} - {SCALE_LABELS[scale]}",`.

- [ ] **Step 4: Point `api.assess_site` at the constant**

`src/seagarden_dst/api.py:30`: `from .scenarios import DEFAULT_SCALE, SCALES`. Line 119: `scale: str = DEFAULT_SCALE,`. Docstring line 145 becomes `scale: a key of `scenarios.SCALES`; `SCALE_LABELS` carries what the user reads.`

- [ ] **Step 5: Export from the package**

`src/seagarden_dst/__init__.py:53`: `from .scenarios import DEFAULT_SCALE, SCALE_LABELS, SCALES, Scenario, compare, evaluate`. Add `"DEFAULT_SCALE",` and `"SCALE_LABELS",` to `__all__` in alphabetical position (after `"DEFAULT_FORCING"` and after `"REGIONS"` respectively).

- [ ] **Step 6: Update the core tests that held the prose key**

`tests/test_method_selection.py`: replace every `SCALES["community farm (0.1 ha)"]` with `SCALES["community_farm_0_1_ha"]`, `SCALES["mini-farm kit"]` with `SCALES["mini_farm_kit"]`, `SCALES["community farm (1 ha)"]` with `SCALES["community_farm_1_ha"]` (lines 25, 33, 34, 36, 41, 47, 56).
`tests/test_suitability.py:89`: `area_m2=SCALES["mini_farm_kit"],`.
`tests/test_golden_snapshot.py:74`: `SCALE = "community_farm_0_1_ha"` and in its docstring line 31 write `"community_farm_0_1_ha"`.

- [ ] **Step 7: Run the whole suite**

Run: `MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest -q && micromamba run -n shiny ruff check .`
Expected: all pass, including `test_assessments_match_the_golden_file` **without** `--snapshot-update` — the scenarios half labels by species key. If the golden test fails, stop: the plan's premise is wrong and the diff must be read before anything is regenerated.

- [ ] **Step 8: Commit**

```bash
git add src/seagarden_dst/scenarios.py src/seagarden_dst/api.py src/seagarden_dst/__init__.py tests/
git commit -m "refactor(core): scale keys are slugs; SCALE_LABELS carries the English (I-0)

The scale a user picks was an English sentence used as a dict key, an
AppState value and an assess_site argument. Package I translates labels,
so the key and the label part company here, with nothing visible moved.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: The app holds scale slugs and shows scale labels

**Files:**
- Modify: `app/state.py:13`
- Modify: `app/modules/user_mode.py:21,28,35,42`
- Modify: `app/modules/catalogue.py:11,30-32`
- Modify: `app/app.py:24,55-62`
- Modify: `app/tests/test_app_smoke.py:100`
- Test: `app/tests/test_app_smoke.py` (add two tests)

**Interfaces:**
- Consumes: `SCALES`, `SCALE_LABELS`, `DEFAULT_SCALE` from Task 1.

- [ ] **Step 1: Write the failing tests** (append to `app/tests/test_app_smoke.py`)

```python
def test_state_and_doors_hold_scale_identifiers_not_labels():
    from seagarden_dst import SCALES

    assert AppState.defaults()["scale"] in SCALES
    for mode, spec in MODES.items():
        assert spec["scale"] in SCALES, f"{mode} holds a label, not a key"


def test_the_sidebar_status_shows_the_scale_label_never_the_slug():
    """`app.py` formats the scale into a sentence; after I-0 the state holds a slug."""
    from app.app import scale_sentence

    text = scale_sentence(label="Melnrage", count=3, scale_key="community_farm_0_1_ha")
    assert "community farm (0.1 ha)" in text
    assert "community_farm_0_1_ha" not in text
```

- [ ] **Step 2: Run them to verify they fail**

Run: `MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest app/tests/test_app_smoke.py -k "scale" -v`
Expected: first FAILS (`"community farm (0.1 ha)" not in SCALES`); second FAILS (`ImportError: scale_sentence`).

- [ ] **Step 3: Switch the state default and the doors to slugs**

`app/state.py:13`: `"scale": "community_farm_0_1_ha",`.
`app/modules/user_mode.py`: `"scale": "community_farm_1_ha",` (plan), `"scale": "community_farm_0_1_ha",` (farm), `"scale": "mini_farm_kit",` (start), `"scale": "community_farm_0_1_ha",` (explore).

- [ ] **Step 4: The Catalogue select shows labels, holds keys**

`app/modules/catalogue.py:11`: `from seagarden_dst import DEFAULT_SCALE, SCALE_LABELS, default_parameters`. Lines 30–32:

```python
            ui.input_select(
                "scale", "Scale", choices=dict(SCALE_LABELS), selected=DEFAULT_SCALE
            ),
```

`SCALES` is no longer imported by this module; remove it from the import.

- [ ] **Step 5: The sidebar sentence goes through the label table**

`app/app.py:24`: add `from seagarden_dst import SCALE_LABELS`. Add a module-level function after the imports:

```python
def scale_sentence(*, label: str, count: int, scale_key: str) -> str:
    """The 'site ready' sentence. `scale_key` is state; the user reads its label."""
    # t() takes a STATIC template; interpolate AFTER the lookup.
    return t("Site ready: {label}. {n} species selected at {scale}. Click Assess.").format(
        label=label, n=count, scale=SCALE_LABELS[scale_key]
    )
```

and in `status_slot` replace lines 57–62 with:

```python
            return ui.p(
                scale_sentence(
                    label=state.site_label.get(), count=count, scale_key=state.scale.get()
                )
            )
```

- [ ] **Step 6: Fix the fake state in the smoke tests**

`app/tests/test_app_smoke.py:100`: `self.scale = _Value("community_farm_0_1_ha")`.

- [ ] **Step 7: Run the suite**

Run: `MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest -q && micromamba run -n shiny ruff check .`
Expected: all pass. Then `grep -rn "community farm\|mini-farm kit\|small commercial" src app tests --exclude-dir=golden` must list only `scenarios.py`'s `SCALE_LABELS` block, its module docstring lines 7–8, `api.py:45`'s prose comment, `test_method_selection.py:4`'s docstring and `test_golden_snapshot.py:39`'s docstring — comments, not keys.

- [ ] **Step 8: Commit**

```bash
git add app/
git commit -m "refactor(app): state and doors hold scale keys; the select and sidebar show labels (I-0)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: Caveat slugs and `CAVEAT_LABELS`

**Files:**
- Modify: `src/seagarden_dst/api.py:176-183`, `:235-251`
- Modify: `src/seagarden_dst/__init__.py`
- Modify: `app/modules/results.py:125-141`, `app/modules/report.py:80-82`
- Modify: `tests/test_adapters.py:76`, `tests/test_api.py:56-57`
- Test: `tests/test_api.py` (add one test)

**Interfaces:**
- Produces: `CAVEAT_LABELS: dict[str, str] = {"nutrient_forcing": "nutrient forcing", "site_conditions": "site conditions", "calibration": "calibration"}` in `api.py`, exported from `seagarden_dst`. `SiteAssessment.caveats` keys are exactly those slugs.

- [ ] **Step 1: Write the failing test** (append to `tests/test_api.py`)

```python
def test_caveat_keys_are_slugs_with_a_label_each(lithuania):
    import re

    from seagarden_dst import CAVEAT_LABELS

    result = assess_site(lithuania, eutropy={"nonsense": True})
    assert result.caveats, "expected at least the calibration and forcing caveats"
    for key in result.caveats:
        assert re.fullmatch(r"[a-z_]+", key), f"{key!r} is prose, not an identifier"
        assert key in CAVEAT_LABELS, f"no label for caveat {key!r}"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest tests/test_api.py::test_caveat_keys_are_slugs_with_a_label_each -v`
Expected: FAIL — `ImportError: cannot import name 'CAVEAT_LABELS'`.

- [ ] **Step 3: Slug the keys in `api.py`**

After the imports (line 33) add:

```python
#: English label per caveat slug. `SiteAssessment.caveats` is keyed by the slug (I§3);
#: the renderers look the label up here, and package I-a translates this table.
CAVEAT_LABELS: dict[str, str] = {
    "nutrient_forcing": "nutrient forcing",
    "site_conditions": "site conditions",
    "calibration": "calibration",
}
```

Line 181: `caveats["nutrient_forcing"] = note`. Line 183: `caveats["nutrient_forcing"] = f"EUTROPY forcing not applied: {exc}"`. Line 237: `"site_conditions",`. Line 248 stays `"calibration"`.

- [ ] **Step 4: Export and render**

`src/seagarden_dst/__init__.py:30`: `from .api import CAVEAT_LABELS, assess_site`; add `"CAVEAT_LABELS",` to `__all__` after `"BowtieUnavailable"`.

`app/modules/results.py:12`: `from seagarden_dst import CAVEAT_LABELS, assess_site, removal_framing`. Line 134:

```python
                        ui.tags.ul(
                            *[
                                ui.tags.li(f"{CAVEAT_LABELS.get(k, k)}: {v}")
                                for k, v in caveats.items()
                            ]
                        ),
```

`app/modules/report.py:14`: `from seagarden_dst import CAVEAT_LABELS, __version__`. Lines 81–82:

```python
    for key, value in assessment.caveats.items():
        lines.append(f"- {CAVEAT_LABELS.get(key, key)}: {value}")
```

- [ ] **Step 5: Update the two tests that indexed by prose**

`tests/test_adapters.py:76`: `degraded.caveats["nutrient_forcing"]`. `tests/test_api.py:56-57` already use `"calibration"`, unchanged.

- [ ] **Step 6: Run the suite**

Run: `MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest -q && micromamba run -n shiny ruff check .`
Expected: all pass; `test_report_carries_the_site_label_and_the_caveats` still sees `"CAVEATS"` and the rendered label text is unchanged.

- [ ] **Step 7: Commit**

```bash
git add src/seagarden_dst/api.py src/seagarden_dst/__init__.py app/modules/results.py app/modules/report.py tests/test_adapters.py tests/test_api.py
git commit -m "refactor: caveat dict keys are slugs; CAVEAT_LABELS carries the English (I-0)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: `Verdict.label`, and the three renderers use it

**Files:**
- Modify: `src/seagarden_dst/suitability.py:31-50`
- Modify: `app/modules/_widgets.py:44-46`, `:67`
- Modify: `app/modules/results.py:113`
- Modify: `app/modules/report.py:58`
- Test: `tests/test_suitability.py` (add one test), `app/tests/test_app_smoke.py` (add one test)

**Interfaces:**
- Produces: `Verdict.label -> str`, equal to `Verdict.value` for every member in I-0 (I-a turns it into a `Message`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_suitability.py`:

```python
def test_every_verdict_has_a_label_and_in_english_it_is_the_value():
    """I-0 opens the seam; I-a fills it. Until then the label must not move the report."""
    from seagarden_dst import Verdict

    for verdict in Verdict:
        assert verdict.label == verdict.value
```

Append to `app/tests/test_app_smoke.py`:

```python
def test_the_verdict_pill_keeps_the_value_as_its_class_and_shows_the_label():
    from app.modules._widgets import verdict_pill
    from seagarden_dst import Verdict

    pill = str(verdict_pill(Verdict.MARGINAL.value))
    assert 'class="sg-verdict sg-verdict-marginal"' in pill
    assert ">marginal<" in pill
```

- [ ] **Step 2: Run them to verify they fail**

Run: `MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest tests/test_suitability.py app/tests/test_app_smoke.py -k "verdict" -v`
Expected: the core test FAILS with `AttributeError: label`; the app test PASSES already (it pins current behaviour so Step 3 cannot break it).

- [ ] **Step 3: Add the property**

In `suitability.py`, inside `class Verdict`, after the `score` property:

```python
    @property
    def label(self) -> str:
        """What a user reads. Identical to the value in English; the identifier is the
        value, which is also the CSS class (`sg-verdict-<value>`). Package I-a makes this
        a `Message` so the pill can say 'geeignet' while the class stays 'suitable'."""
        return self.value
```

- [ ] **Step 4: Route the renderers through it**

`app/modules/_widgets.py:11`: `from seagarden_dst import SiteAssessment, SiteContext, Tier, Verdict`. Lines 44–46:

```python
def verdict_pill(verdict: str) -> ui.Tag:
    kind = verdict if verdict in _VERDICTS else "unknown"
    shown = Verdict(verdict).label if verdict in _VERDICTS else verdict
    return ui.tags.span(shown, class_=f"sg-verdict sg-verdict-{kind}")
```

Line 67: `return "ok", f"Best option: {best.species_name}, {Verdict(best.verdict).label}{suffix}."`

`app/modules/results.py:113`: `ui.tags.small(f"{name}: {Verdict(verdict).label} - {reason}")` with `from seagarden_dst import CAVEAT_LABELS, Verdict, assess_site, removal_framing` on line 12.

`app/modules/report.py:58`: `f"  Verdict:   {Verdict(option.verdict).label}",` with `Verdict` added to the line-14 import.

- [ ] **Step 5: Run the suite**

Run: `MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest -q && micromamba run -n shiny ruff check .`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/seagarden_dst/suitability.py app/modules/
git commit -m "refactor: Verdict.label is the display seam; the value stays the identifier and CSS class (I-0)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: `render_report` takes `today`; the English report becomes a golden file

**Files:**
- Modify: `app/modules/report.py:21`, `:42`, `:152-161`
- Modify: `app/tests/test_app_smoke.py` (existing calls to `render_report`)
- Create: `tests/golden/reports/` — one `.txt` per placeholder region
- Test: `tests/test_report_golden.py` (create)

**Interfaces:**
- Produces: `render_report(assessment, choice=None, *, today: date) -> str`. The golden files, regenerated only with `--snapshot-update`, which `tests/conftest.py` registers. **The test lives under `tests/`, not `app/tests/`, for that reason**: pytest loads `tests/conftest.py` only for paths under `tests/`, so `pytest app/tests/x.py --snapshot-update` would die on an unrecognised argument. `pyproject.toml`'s `pythonpath = ["src", "."]` lets a test under `tests/` import `app.modules` and `app.tests.test_app_smoke`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_report_golden.py
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
```

- [ ] **Step 2: Run it to verify it fails**

Run: `MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest tests/test_report_golden.py -v`
Expected: FAIL — `TypeError: render_report() got an unexpected keyword argument 'today'`.

- [ ] **Step 3: Inject `today`**

`app/modules/report.py:21`:

```python
def render_report(assessment, choice: ForcingChoice | None = None, *, today: date) -> str:
```

Line 42: `f"Generated:   {today.isoformat()} - core v{__version__}",`.

Lines 152–161, the module server:

```python
    @output
    @render.code
    def report_text():
        return render_report(state.assessment.get(), state.forcing.get(), today=date.today())

    @render.download(filename=lambda: f"seagarden-dst-{date.today().isoformat()}.txt")
    def download_txt():
        yield render_report(state.assessment.get(), state.forcing.get(), today=date.today())
```

Add to the module docstring: `today` is a parameter for the same reason `regulatory.py` makes it one: the test suite must not turn red on a calendar boundary.

- [ ] **Step 4: Update every existing caller**

`grep -rn "render_report(" app tests` — each call in `app/tests/test_app_smoke.py` (lines 258, 266, 273, 460, 462, 471) gains `today=date.today()`; add `from datetime import date` to that file's imports. There must be no other caller.

- [ ] **Step 5: Create the golden files, then run the suite**

Run: `MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest tests/test_report_golden.py --snapshot-update -q`
Expected: 7 skipped ("golden report regenerated"), 1 passed. Check `ls tests/golden/reports/` shows seven `.txt` files and `head -12 tests/golden/reports/LT-coastal.txt` shows `Generated:   2026-09-28 - core v*`.

Then: `MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest -q && micromamba run -n shiny ruff check .`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add app/modules/report.py app/tests/ tests/test_report_golden.py tests/golden/reports/
git commit -m "test(report): render_report takes today; the English report is a golden file (I-0)

Package I-a must leave the English report byte-identical, and a report
that stamps date.today() cannot be compared across days. Seven golden
texts, one per placeholder region, version normalised.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: CHANGELOG and the spec's golden sentence

**Files:**
- Modify: `CHANGELOG.md:12-14` (the `[Unreleased]` section)
- Modify: `docs/superpowers/specs/2026-09-28-package-i-internationalisation-design.md` (I§3 last paragraph)

- [ ] **Step 1: Record I-0 under `[Unreleased]`**

Under `## [Unreleased]`, add before the existing `### Changed (documentation only)`:

```markdown
### Changed

- **Package I-0 — the identifier split.** `SCALES` is keyed by slug
  (`community_farm_0_1_ha`, not `"community farm (0.1 ha)"`), with `SCALE_LABELS` and
  `DEFAULT_SCALE` beside it; `SiteAssessment.caveats` is keyed by slug
  (`nutrient_forcing`, `site_conditions`, `calibration`) with `CAVEAT_LABELS`;
  `Verdict.label` exists and equals the value. `render_report` takes a keyword-only
  `today`. A caller passing the old prose scale key gets `KeyError("Unknown scale …")`.
  Nothing a user sees changes; the assessments golden is untouched and the English report
  is now a golden file of its own (`tests/golden/reports/`), which package I-a must leave
  byte-identical. Design: `docs/superpowers/specs/2026-09-28-package-i-internationalisation-design.md`.
```

- [ ] **Step 2: Correct the spec's expectation**

In I§3, replace the paragraph beginning `**The golden snapshot changes in I-0, and only in labels.**` with:

```markdown
**The golden snapshot does not change in I-0.** `tests/test_golden_snapshot.py` labels
its scenarios by species key, not by scale, so the rename touches no captured value; the
plan asserts the golden passes without `--snapshot-update`. (An earlier draft of this
section expected a label-only diff. The English *report* golden of test 10 is created in
I-0.)
```

- [ ] **Step 3: Run the suite one last time and commit**

Run: `MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest -q && micromamba run -n shiny ruff check .`
Expected: all pass.

```bash
git add CHANGELOG.md docs/superpowers/specs/2026-09-28-package-i-internationalisation-design.md
git commit -m "docs: CHANGELOG records I-0; the spec no longer expects a golden label diff

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

I-0's done-when (spec I§11 clauses 1–4) is now met: the grep is clean outside comments, caveat keys are slugs, the golden is unchanged, the report golden exists.
