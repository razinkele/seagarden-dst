# Package I-b — Five Languages Implementation Plan (rev 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Machine-draft catalogues for German, Polish, Danish, Lithuanian and Swedish, each honest about being a draft, behind the review gate I-a built; the hardening I-a's final review left for this package, done before any draft lands; a runbook a partner can follow to review a language and switch it on; the documentation amendments the spec requires.

**Architecture:** Two hardening tasks first — Task 1 tightens the guard tests (whitespace, loading, the reference status, the leak allowlist, tests that encoded I-a's "no German" state); Task 2 makes the gate disable a broken catalogue instead of failing the site, and marks draft-language downloads as drafts. Then three YAML files per language (core, app, params sidecar) with `status: machine-draft` headers; the parity, hygiene and gate tests decide whether a file is acceptable; the German task also adds the first test that renders a real translated page. The live instance keeps showing English until a reviewer flips a language's three headers to `reviewed`.

**Tech Stack:** YAML, pytest, Python 3.11 (`app/i18n.py`, `app/modules/report.py` for Task 2). The drafts are written by the implementer (an LLM) and are labelled as such in every file header.

**Spec:** `docs/superpowers/specs/2026-09-28-package-i-internationalisation-design.md` — I§6, I§7, I§9, I§10, I§11 clauses 11–14. **Prerequisite:** I-a merged (`main` at 57728f3).

**Revision 2 (2026-09-29).** Rev 1's seven tasks predate I-a's final review. The twelve items that review appended (the last section of this file) are folded in: items 1, 2, 4, 7, 8 and two notes from the project memory into Task 1; items 5 and 6 into Task 2; item 3 into Task 3 Step 6; items 9 and 10 into Task 8; items 11 and 12 stay deferred. The language tasks moved from 1–5 to 3–7, the runbook to 8, the documentation to 9. The runbook dry run no longer switches branches with edited catalogues in the tree. Commit trailers follow each agent's own harness.

## Global Constraints

- `MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest ...`; ruff `micromamba run -n shiny ruff check .` (line-length 100); the working tree is shared with other sessions: never stash, commit at the end of every task; every commit ends with the `Co-Authored-By:` line the committing agent's own harness specifies.
- **English output is byte-identical after every task.** `tests/golden/assessments.json` and `tests/golden/reports/*` never change. Drafts cannot touch English; Task 2's draft marking appears only under a draft language.
- **Every draft file header is exactly:** `language: <code>`, `status: machine-draft`, `translated_by: "machine draft (Claude), <ISO date written>"`, `reviewed_by: null`, `reviewed_on: null`, then `messages:`.
- **Translation rules, applied to every value:**
  - keep every `{placeholder}` name unchanged, and put it where the language wants it;
  - keep units, symbols, numbers, project codes (`WP3`, `A2.3`, `D2.2`, `STHB.02.02-IP.01-0006/25`), programme and product names (`SeaGarden`, `Interreg South Baltic`, `OLAMUR`, `EUTROPY`, `MARBEFES`, `Copernicus`, `EMODnet`, `HELCOM`) and Latin names untouched; `psu` stays `psu`;
  - **keep each value's leading and trailing whitespace exactly as in English** (many fragments start with a space, the report's option lines with two, the modal bodies end with a newline); Task 1's test enforces it;
  - keep the report's fixed-width prefixes (`Site:        {site}` etc.) at the same column widths where the language allows;
  - keep markdown structure (headings, list markers, table pipes, the indented code line in `app.site.no_map`) in the modal bodies;
  - do not add plural forms: no new keys at all, and the key set is fixed by English;
  - do not translate calibration `source:` citations;
  - **the bow-tie state names `Low`, `Moderate`, `High` stay verbatim everywhere**, including the `High` inside `P(top event High)` in `adapters.bowtie.framing_high` and `framing_low`: they are the engine's state names, shown raw beside those sentences. Translate the words around them (`top event`) the same way as in `app.results.p_top` and `app.report.p_top`;
  - `app.site.provenance_inline.*` are the three provenance labels as they read in the middle of a sentence (English lower-cases them; German keeps noun capitals);
  - `app.site.help_absent_single` / `help_absent_list` are the same sentence for one region name and for a list of names: the choice is verb agreement, not a numeric plural;
  - numbers keep the decimal point (`0.1 ha`), dates stay year-month-day.
- **The legal-weight sentences** — `app.report.footer`, the last paragraph of `app.shell.about.body`, `suitability.legal.no_record`, `app.report.legal_caveat` — must be translated conservatively; the runbook names them for the reviewer.
- No language is enabled by this package: with no environment variable set, `enabled_languages()` returns `("en",)` after every task.

## Review Focus

1. **A placeholder renamed or dropped in translation** (`{Tiefe}` for `{depth}`) renders as a `KeyError` in production for that one sentence. Test 4 catches it per key; every language task runs it.
2. **Decimal comma creeping into a value** (`0,1 ha` in a scale label). Spec I§7 keeps the point; the hygiene test cannot see it, so each language task greps its three files for `\d,\d`.
3. **A draft mistaken for a reviewed language** because someone edits `status` without the reviewer fields. `Catalogue.load` refuses `reviewed` without `reviewed_by` and `reviewed_on`; Task 1 adds a test that every catalogue on disk loads; the runbook says so.
4. **Report column alignment drifting** so `Nitrogen:`/`Phosphorus:` values no longer line up. Cosmetic, but the report is what gets printed; each language task's Step 4 renders its report and the implementer reads it.
5. **A sidecar key for a species that no longer exists** after a params change. Test 3 fails on stale keys; the runbook tells a reviewer what that failure means.
6. **A malformed catalogue on the server.** Before Task 2 one bad header returned 500 on every page, English included; after it, that language is simply not offered.
7. **A draft-language download forwarded as if reviewed.** After Task 2 the report's first line says it is a machine translation in both languages, and the JSON names its language and draft status.

---

### Task 1: Harden the guards before any draft lands

**Files:**
- Modify: `tests/test_i18n_guards.py` (tests 4, new 4c and 4d)
- Modify: `tests/test_i18n.py` (the no-file catalogue test)
- Modify: `app/tests/test_i18n_app.py` (the two tests that assume German does not exist or is not reviewed)
- Modify: `app/tests/test_i18n_leaks.py` (the allowlist)

**Interfaces:**
- Consumes: `OWNERS`, `_files`, `_messages`, `_reference`, `_template_problem` in `tests/test_i18n_guards.py`; `Catalogue` and `core_catalogue` from `seagarden_dst.i18n`; `catalogue_status`, `enabled_languages`, `language_for` from `app.i18n`; `_leaks`, `_RAW_ALLOWED_TOKENS`, `ALLOWED_TOKENS`, `ENGLISH_DRAFT_BANNER` in the leak test.
- Produces: guards that hold whatever catalogues are on disk. No production code changes.

- [ ] **Step 1: Whitespace, loading and the reference status (inherited items 1, 2, 8)**

Add to `tests/test_i18n_guards.py`:

```python
def _edges(text: str) -> tuple[str, str]:
    """The leading and trailing whitespace of a value."""
    body = text.strip()
    if not body:
        return text, ""
    start = text.index(body)
    return text[:start], text[start + len(body):]


@pytest.mark.parametrize("owner", sorted(OWNERS))
def test_4c_leading_and_trailing_whitespace_match_english(owner):
    """A draft that trims `" and "` to `"and"` runs words together (inherited item 1)."""
    reference = _reference(owner)
    for path in _files(OWNERS[owner]):
        if path.stem == "en":
            continue
        for key, value in _messages(path).items():
            english = reference.get(key)
            if english is None:
                continue  # test 1 reports a key English lacks
            assert _edges(value) == _edges(english), (
                f"{path}: {key} has whitespace {_edges(value)!r}, English {_edges(english)!r}"
            )
            if english.strip():
                assert value.strip(), f"{path}: {key} is empty where English is not"


def test_4d_every_catalogue_file_on_disk_loads():
    """A bad header fails CI, not a page (inherited item 2)."""
    from seagarden_dst.i18n import Catalogue

    for root in OWNERS.values():
        for path in _files(root):
            Catalogue.load(path.stem, path.parent)  # raises on a bad header or value
```

In `test_4_catalogue_hygiene`, next to the existing header checks, pin the reference status (inherited item 8):

```python
        assert (data["status"] == "reference") == (path.stem == "en"), (
            f"{path}: only English is the reference; every other language is a draft or reviewed"
        )
```

- [ ] **Step 2: Sidecar values are not templates (project-memory note)**

Sidecar values are rendered verbatim — `Translator.species_name`, `method_name`, `method_field`, `group_label` return them as they are, and the text index substitutes them for a literal's text — never through `str.format`. So test 4's template rule must not apply to the `params` owner: an English YAML note containing a brace would otherwise fail every sidecar. In `test_4_catalogue_hygiene`, apply `_template_problem` only when `owner != "params"`; for `params`, assert each value is a non-empty string. Say why in a comment.

- [ ] **Step 3: Tests that encoded I-a's "no German" state (inherited item 4 and a project-memory note)**

These three tests break or become wrong as soon as `de.yaml` exists or a language is reviewed. Rewrite them to state the invariant rather than today's disk:

```python
# tests/test_i18n.py — replaces test_a_non_english_core_catalogue_without_a_file_is_english_with_that_language_code
def test_a_catalogue_for_a_language_with_no_file_is_english_with_that_code():
    """A browser may ask for a language nobody has translated; `core_catalogue` must not
    raise. "xx" has no file under any locale root, now or later."""
    xx = core_catalogue("xx")
    assert xx.language == "xx"
    assert xx.render(msg("calibration.tier.A.label")) == "Locally calibrated"
```

```python
# app/tests/test_i18n_app.py — replaces test_in_i_a_only_english_is_enabled_on_disk
def test_with_the_draft_switch_off_only_reviewed_languages_are_enabled():
    """Holds whatever is on disk: a draft never shows without the switch."""
    enabled = enabled_languages(env={})
    assert enabled[0] == "en"
    assert all(catalogue_status(language) == "reviewed" for language in enabled[1:])
    assert catalogue_status("en") == "reference"
    assert catalogue_status("xx") is None
```

```python
# app/tests/test_i18n_app.py — replaces the body of test_app_ui_takes_a_request_and_reads_lang_from_it
def test_app_ui_takes_a_request_and_reads_lang_from_it():
    from app.app import app_ui
    from app.i18n import language_for

    expected = language_for("?lang=de", "de", enabled_languages())
    assert f'lang="{expected}"' in str(app_ui(_request(b"lang=de", b"de")))
    assert 'lang="en"' in str(app_ui(_request(b"lang=zz", b"zz")))  # never a language
    assert 'lang="en"' in str(app_ui(_request(b"", None)))
```

Keep `test_core_catalogue_reuses_the_cached_english_catalogue` as it is: it holds with or without `de.yaml`.

- [ ] **Step 4: Prune the leak allowlist and narrow its exemptions (inherited item 7)**

In `app/tests/test_i18n_leaks.py`:
1. Factor every render the leak tests perform (the whole page, every per-region render, the empty and unassessable states) into one helper, `_all_renders() -> list[str]`, used by the existing tests.
2. Record which allowlist entries let a token pass: `_leaks` adds the normalised entry to a module-level set when it allows it. Add `test_every_allowlist_entry_is_needed`, which clears that set, calls `_all_renders()` through `_leaks` with `shiny_deckgl` hidden (`monkeypatch.setitem(sys.modules, "shiny_deckgl", None)`, as `app/tests/test_app_smoke.py` does), and asserts `ALLOWED_TOKENS` minus the matched set is empty, naming the dead entries.
3. Remove every entry that test names. Then run the same collection with `shiny_deckgl` present (it is installed locally); if any entry is matched only with the map, keep it in a separate, commented `MAP_ONLY_TOKENS` set excluded from the assertion.
4. Remove `"None"` from the allowlist. In `_leaks`, blank out only the exact pseudo-rendered line `⟦app.report.subregion⟧ None` — the `Sub-region` line of an unassessable site, pinned by `tests/golden/reports/case-unassessable.txt` (inherited item 12) — before scanning.
5. Stop replacing `ENGLISH_DRAFT_BANNER` in every chunk. The whole-page scan removes it once and asserts it occurred exactly once; no other render may contain it (Task 2 adds the report, and extends this rule there).

- [ ] **Step 5: Verify and commit**

Run: `MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest -q && micromamba run -n shiny ruff check . && git status --short tests/golden`
Expected: all pass; the last command prints nothing. Then prove the new checks can fail with scratch copies only (never committed): a `de.yaml` whose `app.site.and` is `"and"` fails 4c; a header with `status: reference` fails 4; an allowlist with an extra unused word fails `test_every_allowlist_entry_is_needed`.

```bash
git add tests/test_i18n_guards.py tests/test_i18n.py app/tests/test_i18n_app.py app/tests/test_i18n_leaks.py
git commit -m "test(i18n): whitespace, loading and reference guards; state-free gate tests; a pruned leak allowlist (I-b)"
```

---

### Task 2: The gate fails safe; draft downloads say they are drafts

**Files:**
- Modify: `app/i18n.py` (`enabled_languages`)
- Modify: `app/modules/report.py` (`render_report`, a new `export_json`, `download_json`)
- Modify: `app/tests/test_i18n_app.py`, `app/tests/test_i18n_leaks.py`

**Interfaces:**
- Consumes: `catalogue_status`, `enabled_languages`, `Translator.is_draft`, `Translator.language`, `english()` from `app.i18n`; `render_report` from `app.modules.report`.
- Produces: `enabled_languages` never raises for a broken catalogue; `render_report(..., tr=<draft>)` starts with a bilingual draft line; `export_json(assessment, tr) -> str` with top-level `"language"` and `"draft"` keys.

- [ ] **Step 1: Write the failing tests**

```python
# app/tests/test_i18n_app.py
def test_a_broken_catalogue_disables_its_language_and_never_the_site(tmp_path, caplog):
    """Inherited item 5: one malformed header used to 500 every page, English included."""
    import logging

    roots = {}
    for owner in ("core", "app", "params"):
        root = tmp_path / owner
        root.mkdir()
        # `reviewed` without reviewer fields: Catalogue.load raises ValueError
        (root / "de.yaml").write_text(
            "language: de\nstatus: reviewed\nmessages:\n  a.b: x\n", encoding="utf-8"
        )
        roots[owner] = root

    def status(language):
        return catalogue_status(
            language, core_root=roots["core"], app_root=roots["app"], params_root=roots["params"]
        )

    with caplog.at_level(logging.WARNING, logger="app.i18n"):
        enabled = enabled_languages(env={"SEAGARDEN_SHOW_DRAFT_LANGUAGES": "1"}, status=status)
    assert enabled == ("en",)
    assert "de" in caplog.text


def test_a_draft_report_says_so_in_both_languages_and_english_does_not():
    from datetime import date

    from app.modules.report import render_report

    today = date(2026, 9, 29)
    draft = render_report(None, today=today, tr=Translator.pseudo())
    assert draft.splitlines()[0] == (
        "⟦app.shell.draft_banner⟧ " + english()("app.shell.draft_banner")
    )
    assert render_report(None, today=today, tr=english()) == english()("app.report.none")


def test_the_json_export_names_its_language_and_draft_status():
    import json

    from app.modules.report import export_json

    assert json.loads(export_json(None, english())) == {"language": "en", "draft": False}
    marked = json.loads(export_json(None, Translator.pseudo()))
    assert marked["language"] == "xx" and marked["draft"] is True
```

Add a fourth test that `export_json` of a real assessment under English still carries every `to_dict()` key (`site`, `ranked`, `best`, `excluded`, `caveats`, `pressure`, `pressure_note`) beside `language` and `draft`.

- [ ] **Step 2: Run them to see them fail**

Run: `MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest app/tests/test_i18n_app.py -q -k "broken or draft_report or json_export"`
Expected: the first raises `ValueError` out of `enabled_languages`; the report test fails on the first line; `export_json` does not exist.

- [ ] **Step 3: The fail-safe gate**

In `enabled_languages`, call `status(language)` inside `try/except (OSError, ValueError, yaml.YAMLError)`; on failure treat the language as not enabled and log `logging.getLogger(__name__).warning(...)` naming the language and the error — once per distinct error message per process (a module-level set), so a broken file does not log on every request. English is never passed to `status`, so it can never be disabled. Update the docstring.

- [ ] **Step 4: Draft-marked downloads**

In `render_report`, when `tr.is_draft`, prepend one line — `f"{tr('app.shell.draft_banner')} {english()('app.shell.draft_banner')}"` — to whatever the report returns, including the "no assessment" text. English reports are unchanged.

Add `export_json(assessment, tr) -> str`: `{"language": tr.language, "draft": tr.is_draft, **(assessment.to_dict(render=tr.render) if assessment is not None else {})}` dumped with `indent=2, default=str`, and make `download_json` yield it.

- [ ] **Step 5: The leak test sees the report's English line once**

The pseudo-locale is a draft, so every report the leak test renders now starts with the English banner sentence. Extend Task 1's rule: the report scan removes that sentence once and asserts it occurred exactly once; any other render still may not contain it.

- [ ] **Step 6: Verify and commit**

Run: `MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest -q && micromamba run -n shiny ruff check . && git status --short tests/golden`
Expected: all pass; nothing under `tests/golden` changed (English reports carry no draft line).

```bash
git add app/i18n.py app/modules/report.py app/tests/test_i18n_app.py app/tests/test_i18n_leaks.py
git commit -m "feat(app): a broken catalogue disables its language, not the site; draft downloads say they are drafts (I-b)"
```

---

### Task 3: German (`de`)

**Files:**
- Create: `src/seagarden_dst/locales/de.yaml`, `app/locales/de.yaml`, `params/i18n/de.yaml`
- Modify: `app/tests/test_i18n_leaks.py` (Step 6: the real spec test 8)

**Interfaces:**
- Consumes: the three English key sets (`src/seagarden_dst/locales/en.yaml`, `app/locales/en.yaml`, `params_reference_keys()` in `app/i18n.py`).
- Produces: three files that pass tests 1–4, 4c and 4d and leave `enabled_languages()` at `("en",)`; the first test that renders a real translated page.

- [ ] **Step 1: Generate the key skeletons from English**

Run: `micromamba run -n shiny python scripts/i18n_review_sheet.py de > "$TMPDIR/de-sheet.md"` (any scratch path outside the repo; the third column is empty; the sheet is the worklist). Then create the three files by copying the English structure, with today's date in `translated_by`:

```bash
D=$(date +%F)
sed -e 's/^language: en$/language: de/' -e "s/^status: reference\$/status: machine-draft\ntranslated_by: \"machine draft (Claude), $D\"\nreviewed_by: null\nreviewed_on: null/" src/seagarden_dst/locales/en.yaml > src/seagarden_dst/locales/de.yaml
sed -e 's/^language: en$/language: de/' -e "s/^status: reference\$/status: machine-draft\ntranslated_by: \"machine draft (Claude), $D\"\nreviewed_by: null\nreviewed_on: null/" app/locales/en.yaml > app/locales/de.yaml
```

For the params sidecar there is no English file; write it from `params_reference_keys()`:

```bash
MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -c "
import datetime, yaml
from app.i18n import params_reference_keys
doc = {'language': 'de', 'status': 'machine-draft',
       'translated_by': f'machine draft (Claude), {datetime.date.today().isoformat()}',
       'reviewed_by': None, 'reviewed_on': None,
       'messages': dict(params_reference_keys())}
print(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, width=100), end='')
" > params/i18n/de.yaml
```

- [ ] **Step 2: Run the guards to confirm the skeletons are complete**

Run: `MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest tests/test_i18n_guards.py -q`
Expected: pass (the values are still English; parity, hygiene, whitespace and loading look at keys, placeholders, edges and headers).

- [ ] **Step 3: Translate every value into German**

Work through each file top to bottom, replacing the English value with German under the Global Constraints. Worked examples that fix the register:

```yaml
  calibration.tier.A.label: "Lokal kalibriert"
  calibration.tier.C.label: "Literaturwert"
  calibration.caveat.C: "Nur indikativ - Literaturwert ({source}), keine lokale Validierung."
  suitability.class.legal: "Rechtliche Zulässigkeit"
  suitability.physical.depth_outside: "Die Tiefe von {depth} m liegt außerhalb des nutzbaren Bereichs für {method} ({min_depth}-{max_depth} m)."
  suitability.verdict.suitable: "geeignet"
  scenarios.scale.community_farm_0_1_ha: "Gemeinschaftsfarm (0.1 ha)"
  forcing.region.DK-belt: "Großer Belt"
```

```yaml
  app.shell.assess: "Bewerten"
  app.status.site_ready: "Standort bereit: {label}. Ausgewählte Arten: {n}. Maßstab: {scale}. Auf „Bewerten“ klicken."
  app.report.footer: "Prototyp-Ausgabe. Nur indikativ; keine Grundlage für Genehmigungen oder Zustimmungen."
  app.report.nitrogen: "  Stickstoff: {value}"
```

```yaml
  params.species.ulva.common_name: "Meersalat"
  params.species.mytilus.common_name: "Miesmuschel"
  params.methods.raft.name: "Floß"
  params.group.macroalga: "Makroalge"
  params.group.shellfish: "Muscheln"
```

Scientific names are not in the sidecar and never appear in it.

- [ ] **Step 4: Verify and read**

Run: `MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest tests/test_i18n_guards.py tests/test_i18n.py app/tests/test_i18n_app.py -q`
Expected: pass. Then `grep -nE '[0-9],[0-9]' src/seagarden_dst/locales/de.yaml app/locales/de.yaml params/i18n/de.yaml` prints nothing (no decimal commas).

Render the German report once and read it:

```bash
MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -c "
from datetime import date
from app.i18n import Translator
from app.modules.report import render_report
from app.tests.test_app_smoke import _FakeState
from app.modules.results import run_assessment
from seagarden_dst import SiteContext
s = _FakeState(SiteContext.from_region('DE-coastal', label='Rostock')); run_assessment(s)
print(render_report(s.assessment.get(), s.forcing.get(), today=date.today(), tr=Translator.load('de')))
"
```

Expected: the bilingual draft line first; German throughout; species and method names German; units and numbers unchanged; the footer sentence present; the option lines still aligned.

- [ ] **Step 5: Confirm the gate still hides it**

Run: `MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -c "from app.i18n import enabled_languages, catalogue_status; print(enabled_languages(env={}), catalogue_status('de'))"`
Expected: `('en',) machine-draft`.

- [ ] **Step 6: The real spec test 8 (inherited item 3)**

Until now the gate could be tested but no translated page could be rendered. Add to `app/tests/test_i18n_leaks.py`:

```python
def test_8_a_draft_language_renders_under_the_switch():
    """The first rendered page in a real second language: shown only with the switch,
    translated, and bannered in both languages."""
    import html as htmllib

    from app.app import build_ui
    from app.i18n import english, enabled_languages, language_for

    shown = enabled_languages(env={"SEAGARDEN_SHOW_DRAFT_LANGUAGES": "1"})
    assert "de" in shown and language_for("?lang=de", None, shown) == "de"
    de = Translator.for_language("de")
    assert de.is_draft
    page = htmllib.unescape(str(build_ui("de", enabled=shown)))
    assert 'lang="de"' in page
    assert de("app.shell.assess") != english()("app.shell.assess")
    assert de("app.shell.assess") in page
    assert de("app.shell.draft_banner") in page
    assert english()("app.shell.draft_banner") in page
```

Add the same for a German report: `render_report(...)` for a placeholder site under `Translator.for_language("de")` starts with the bilingual draft line and contains `de("app.report.footer")`.

- [ ] **Step 7: Commit**

```bash
git add src/seagarden_dst/locales/de.yaml app/locales/de.yaml params/i18n/de.yaml app/tests/test_i18n_leaks.py
git commit -m "i18n(de): machine-draft German catalogues, not enabled; the first rendered translated page (I-b)"
```

---

### Task 4: Polish (`pl`)

**Files:**
- Create: `src/seagarden_dst/locales/pl.yaml`, `app/locales/pl.yaml`, `params/i18n/pl.yaml`

Repeat Task 3's Steps 1–5 with `pl`, then commit (Step 6 is German-only). Polish-specific notes: the count-neutral phrasing exists for Polish's plural forms — keep every sentence with `{n}` in the form "Wybrane gatunki: {n}" (noun first, then the number), never "{n} gatunków"; the sidebar and report say "Ocena" for the Assess action consistently. Worked examples:

```yaml
  calibration.tier.C.label: "Wartość literaturowa"
  suitability.class.legal: "Dopuszczalność prawna"
  suitability.verdict.suitable: "odpowiednie"
  forcing.region.PL-lagoon: "Zalew Szczeciński"
  app.shell.assess: "Oceń"
  app.status.site_ready: "Lokalizacja gotowa: {label}. Wybrane gatunki: {n}. Skala: {scale}. Kliknij „Oceń”."
  app.report.footer: "Wynik prototypu. Wyłącznie orientacyjny; nie stanowi podstawy do wydania pozwolenia ani zgody."
  params.species.mytilus.common_name: "Omułek jadalny"
  params.methods.mussel_socks.name: "Rękawy na omułki na linie"
```

Commit: `i18n(pl): machine-draft Polish catalogues, not enabled (I-b)`.

---

### Task 5: Danish (`da`)

**Files:**
- Create: `src/seagarden_dst/locales/da.yaml`, `app/locales/da.yaml`, `params/i18n/da.yaml`

Repeat Task 3's Steps 1–5 with `da`, then commit. Worked examples:

```yaml
  calibration.tier.C.label: "Litteraturværdi"
  suitability.class.legal: "Juridisk tilladelighed"
  suitability.verdict.suitable: "egnet"
  forcing.region.DK-belt: "Storebælt"
  app.shell.assess: "Vurdér"
  app.report.footer: "Prototypeoutput. Kun vejledende; ikke grundlag for tilladelse eller godkendelse."
  params.species.saccharina_latissima.common_name: "Sukkertang"
  params.species.mytilus.common_name: "Blåmusling"
```

Commit: `i18n(da): machine-draft Danish catalogues, not enabled (I-b)`.

---

### Task 6: Lithuanian (`lt`)

**Files:**
- Create: `src/seagarden_dst/locales/lt.yaml`, `app/locales/lt.yaml`, `params/i18n/lt.yaml`

Repeat Task 3's Steps 1–5 with `lt`, then commit. Lithuanian has plural forms too: keep `{n}` sentences noun-first ("Pasirinkta rūšių: {n}"). Worked examples:

```yaml
  calibration.tier.C.label: "Literatūrinė vertė"
  suitability.class.legal: "Teisinis leistinumas"
  suitability.verdict.suitable: "tinkama"
  forcing.region.LT-lagoon: "Kuršių marios, Lietuvos dalis"
  forcing.region.LT-coastal: "Lietuvos priekrantės vandenys"
  app.shell.assess: "Vertinti"
  app.report.footer: "Prototipo rezultatas. Tik orientacinis; nėra pagrindas leidimui ar sutikimui."
  params.species.fucus_vesiculosus.common_name: "Pūslėtasis guveinis"
  params.species.mytilus.common_name: "Valgomoji midija"
```

Commit: `i18n(lt): machine-draft Lithuanian catalogues, not enabled (I-b)`.

---

### Task 7: Swedish (`sv`)

**Files:**
- Create: `src/seagarden_dst/locales/sv.yaml`, `app/locales/sv.yaml`, `params/i18n/sv.yaml`

Repeat Task 3's Steps 1–5 with `sv`, then commit. Worked examples:

```yaml
  calibration.tier.C.label: "Litteraturvärde"
  suitability.class.legal: "Rättslig tillåtlighet"
  suitability.verdict.suitable: "lämplig"
  app.shell.assess: "Bedöm"
  app.report.footer: "Prototyputdata. Endast vägledande; inte grund för tillstånd eller medgivande."
  params.species.saccharina_latissima.common_name: "Sockertare"
  params.species.mytilus.common_name: "Blåmussla"
```

Commit: `i18n(sv): machine-draft Swedish catalogues, not enabled (I-b)`.

After Task 7: `MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest -q` — the whole suite, and tests 1, 4, 4c and 4d now run against six languages per owner. `enabled_languages(env={})` is still `("en",)` (spec I§11 clause 12).

---

### Task 8: The translations runbook, dry-run once

**Files:**
- Create: `docs/runbooks/translations.md`
- Test: a dry run against a temporary copy of the German catalogues (spec I§11 clause 13); nothing in the repository is edited by it

- [ ] **Step 1: Write the runbook**

Start from this text and correct it against the code (in particular, quote the guard tests' real failure messages — capture them by running the tests against scratch copies of a broken catalogue outside the repository, never committed):

```markdown
# Reviewing and enabling a language

For a native-speaking partner reviewing one of the machine-draft catalogues, and for the
maintainer who switches the language on afterwards. Written for somebody who is not the
author of the tool.

## What you are reviewing

Three files per language, `<lang>` one of `de`, `pl`, `da`, `lt`, `sv`:

| File | What it holds |
|---|---|
| `src/seagarden_dst/locales/<lang>.yaml` | what the model says: constraint reasons, caveats, tier labels, region names |
| `app/locales/<lang>.yaml` | the app's chrome: buttons, headings, the About/Help/Feedback texts, the report's fixed lines |
| `params/i18n/<lang>.yaml` | species and method names, and calibration notes from the parameter files |

Every value is a sentence or label; `{words_in_braces}` are placeholders the tool fills in
(a number, a name). **Leave the placeholder names exactly as they are** and put them where
your language wants them in the sentence. Keep any space at the start or end of a value:
many values are fragments joined to others.

Easiest way to read everything at once, English beside your language:

    micromamba run -n shiny python scripts/i18n_review_sheet.py <lang> > review-<lang>.md

Then edit the YAML files, not the sheet. The sheet is generated; the files are the truth.

## Rules that are not stylistic

- Units, numbers, Latin species names, project codes and programme names stay as they are.
- Numbers keep the decimal **point** (`0.1 ha`), dates are year-month-day. This is a
  deliberate tool-wide decision, not an oversight.
- The bow-tie state names `Low`, `Moderate` and `High` stay in English everywhere,
  including `P(top event High)` inside the two pressure-framing sentences: they are the
  model's own state names, shown beside those sentences exactly as written.
- Four sentences carry legal weight. Translate them conservatively and read them twice:
  `app.report.footer`, the last paragraph of `app.shell.about.body`,
  `suitability.legal.no_record`, `app.report.legal_caveat`. If the English is wrong or
  unclear, **say so** (issue or e-mail, addresses in the app's Feedback dialog) rather than
  translating around it; a corrected English sentence is re-translated into every language.
- Do not add or remove keys. If a sentence in your language needs a different structure,
  restructure the value; the key set is fixed by the English file.

## Checking your work

    MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest tests/test_i18n_guards.py -q

<one bullet per failure message a reviewer can meet, quoted as the tests print it, with the fix>

To see your language in the running app before it is enabled:

    SEAGARDEN_SHOW_DRAFT_LANGUAGES=1 shiny run app.app     # then open ?lang=<lang>

A bilingual "machine translation, not yet reviewed" banner shows under the navbar, and a
downloaded report starts with the same line. That is expected until the step below.

## Switching a language on (maintainer)

A language is live when **all three** files carry:

    status: reviewed
    reviewed_by: "Name, institution"
    reviewed_on: 2026-11-30

The loader refuses `reviewed` without both fields, and only English may say `reference`.
Make the change in a pull request titled `i18n(<lang>): reviewed by <institution>`, run the
full suite, merge, deploy as usual (`docs/runbooks/deploy.md`). **The change takes effect
when the service restarts**, which a deploy does: the tool reads each language's status
once per process. No environment variable is needed on the live instance: the menu shows
every reviewed language. `SEAGARDEN_LANGUAGES=en,de` restricts it if a partner asks for a
staged rollout.

To take a language down again, set `status: machine-draft` in any one of its three files
and deploy. A file the tool cannot read disables that language and is logged; it never
takes the site down.
```

- [ ] **Step 2: Dry-run the switch against a copy**

Copy the three German files into a temporary directory outside the repository (`T=$(mktemp -d)`, with `core/`, `app/`, `params/` inside; pass `cygpath -w "$T"` to Python on Windows), flip all three headers there as the runbook says (`reviewed_by: "dry run"`, `reviewed_on:` today), and in a fresh process:

```bash
MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -c "
import sys
from pathlib import Path
from app.i18n import catalogue_status, enabled_languages
T = Path(sys.argv[1])
status = lambda lang: catalogue_status(lang, core_root=T/'core', app_root=T/'app', params_root=T/'params')
print(enabled_languages(env={}, status=status))
" "$(cygpath -w "$T")"
```

Expect `('en', 'de')`. Set one copy back to `status: machine-draft` and run the same command in a new process (the status is cached per process): expect `('en',)`. Delete `$T`. Confirm `git status --short` shows only the new runbook. Record in the runbook's last line: `Dry run by the author on <date> against copies of the German files: both transitions behaved as written.`

- [ ] **Step 3: Commit**

```bash
git add docs/runbooks/translations.md
git commit -m "docs(runbook): reviewing and enabling a language (I-b)"
```

---

### Task 9: The spec amendment, the work-package row, README and CHANGELOG

**Files:**
- Modify: `SeaGarden_DST_functional_specification_v0.1.md` (append Amendment 6 to the amendments list)
- Modify: `docs/superpowers/specs/2026-09-13-dst-data-layer-design.md` (§8: a row after G)
- Modify: `README.md` (*Languages*), `CHANGELOG.md` (`[Unreleased]`)

- [ ] **Step 1: Amendment 6**

After the `[Amendment 5]` bullet:

```markdown
- **[Amendment 6] — 2026-09-28, new requirement, not a correction.** The tool is delivered in six languages — English, German, Polish, Danish, Lithuanian and Swedish — with English as the reference and fallback. Neither the Application Form (`SeaGarden_DST_proposal_extract.md`) nor this document's v0.1 text mentions language; the requirement was added by the Lead Partner on 2026-09-28 and designed as package I (`docs/superpowers/specs/2026-09-28-package-i-internationalisation-design.md`). Two consequences a partner should know: a language is shown to users **only after a native speaker has reviewed its catalogue** and signed the file header (`docs/runbooks/translations.md`), so the live instance may show fewer than six languages at any time; and number and date formats are **not** localised — the decimal point and ISO dates are used in every language — because the Python `locale` machinery is process-global and unsafe in a server, and the tool must stay reconstructible with no extra dependency to 2034.
```

- [ ] **Step 2: The work-package row**

After row **G** in the data-layer design's §8 table, add row **I**:

```markdown
| **I** | Internationalisation (`docs/superpowers/specs/2026-09-28-package-i-internationalisation-design.md`) — I-0 identifier split, I-a the seam, I-b five machine-draft languages behind a review gate | `Message`-valued core prose; per-request `Translator`; `?lang=` menu; three catalogues per language; drafts for de/pl/da/lt/sv, none enabled until reviewed | — (not a data-layer concern; tracked here because every package is) | 0.9 PM *(no spec §13 row — propose amendment)* | I§11's fourteen clauses |
```

Then read §8's opening paragraph and table as they stand now (packages have been added since this plan was first written) and update the package count, the total effort and the "spec §13 amendment to propose" figure consistently with the rows actually present, adding I's 0.9 PM. Say in the commit message what the figures were and what they became.

- [ ] **Step 3: README and CHANGELOG**

README *Languages*: find the sentence that points to the runbook "(package I-b)" and replace it with: `Machine-draft catalogues exist for all five languages; none is reviewed yet, so the live instance shows English. How to review and enable one: docs/runbooks/translations.md.`

CHANGELOG `[Unreleased]` `### Added`:

```markdown
- **Package I-b — five languages, as drafts.** Machine-draft catalogues for German, Polish,
  Danish, Lithuanian and Swedish (three files each: core, app, params sidecar), every header
  `status: machine-draft` and naming the machine as translator. **None is enabled**: the
  live instance shows English until a native speaker reviews a language and flips its
  three headers (`docs/runbooks/translations.md`). `SEAGARDEN_SHOW_DRAFT_LANGUAGES=1` shows
  them on a staging instance under a bilingual notice, and a report downloaded in a draft
  language now starts with the same notice while the JSON export carries `language` and
  `draft` fields. A catalogue file the tool cannot read now disables that language and is
  logged instead of failing every page. Functional specification Amendment 6 records the
  requirement; the data-layer design §8 gains row I.
  **Known limit:** the drafts have not been read by a speaker of any of the five languages;
  the legal-weight sentences in particular are unreviewed and must not be quoted from a
  draft.
```

- [ ] **Step 4: Run, commit**

Run: `MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest -q && micromamba run -n shiny ruff check .`
Expected: all pass (`tests/test_version.py` only checks the version heading, which is unchanged).

```bash
git add SeaGarden_DST_functional_specification_v0.1.md docs/superpowers/specs/2026-09-13-dst-data-layer-design.md README.md CHANGELOG.md
git commit -m "docs: Amendment 6 (six languages), data-layer §8 row I, README and CHANGELOG for I-b"
```

I-b's done-when (spec I§11 clauses 11–14) is then met: fifteen draft files exist with filled `translated_by`, tests 1, 4, 4c and 4d pass for six languages, the menu shows English alone with no variable set, the runbook has been dry-run once, and the four documents carry their amendments; the hardening of Tasks 1 and 2 is in place.

## Inherited from I-a's final review (2026-09-28)

I-a's final review left this work to I-b, to be done before or while the drafts are generated. Test 4 already parses every value the way `str.format` does (an unbalanced brace, a conversion, a format spec or an escaped `{{placeholder}}` fails it, naming file and key), so a draft that passes it renders; the items below are what it still cannot see. **Rev 2 assigns each item to a task** (in brackets).

1. **Whitespace hygiene** [Task 1 Step 1]. Add a check that each value's leading and trailing whitespace matches the English value for the same key, and that no value is empty where English is not: many fragment keys start with a space (`app.site.and` is `" and "`; `app.banner.this_site` and the `app.legend.*` fragments start with one, the report's option lines with two), and a draft that trims them runs words together.
2. **Every catalogue file loads** [Task 1 Step 1]. Add a test that every `*.yaml` under the three locale roots loads through `Catalogue.load`, so a bad header (wrong `language`, unknown `status`, `reviewed` without reviewer fields, a non-string value) fails CI rather than a page.
3. **A real spec test 8** [Task 3 Step 6]. Render the page with a German draft catalogue under `SEAGARDEN_SHOW_DRAFT_LANGUAGES=1` and assert German text and the bilingual draft banner; I-a had no German catalogue, so it could test only the gate, never a rendered German page.
4. **Two tests encode I-a's state and need editing when the drafts land** [Task 1 Step 3]: `tests/test_i18n.py::test_a_non_english_core_catalogue_without_a_file_is_english_with_that_language_code` (use a code with no file, or a temporary root) and `app/tests/test_i18n_app.py::test_in_i_a_only_english_is_enabled_on_disk` (`catalogue_status("de")` becomes `"machine-draft"`, not `None`).
5. **A broken catalogue must not take the site down** [Task 2 Step 3]. A malformed non-English header makes `catalogue_status` raise inside `enabled_languages()`, so every page returns 500, English included. Wrap each language's status check so a broken catalogue disables that language and logs why, never the site.
6. **Draft downloads say they are drafts** [Task 2 Step 4]. The `.txt` report and the JSON export carry no draft marking today: add the bilingual draft line to the report and a `language` field to the JSON before the staging review round.
7. **Prune the leak test's allowlist** [Task 1 Step 4]. Measured after I-a's final-review fixes, 43 of the 102 raw `ALLOWED_TOKENS` entries in `app/tests/test_i18n_leaks.py` never match (the review itself counted 63), and all seven digit-bearing entries (`WP2`, `A2.3`, `CO2`, `m2`, …) are unreachable because the number pattern strips digits before a token is looked up. Remove the dead entries and assert every remaining entry is matched at least once; narrow the `None` exemption to the report's `Sub-region` line (`app.report.subregion`) instead of allowing `None` anywhere, and strip the English draft banner once on the whole-page scan only, not per line of every render.
8. **Pin the reference status** [Task 1 Step 1]. Test 4 should require `status: reference` on `en` and forbid it on every other language.
9. **Tell reviewers to keep the bow-tie state names** [Task 8, and the Global Constraints' translation rules]. The translator runbook must say that `Low`, `Moderate` and `High` stay verbatim, including the `High` in `P(top event High)` inside the `adapters.bowtie.framing_*` sentences: they are the engine's state names (`TOP_EVENT_STATES`), shown raw beside those sentences, so a translated `Hoch` would no longer name what the reader sees next to it.
10. **Status changes need a restart** [Task 8]. `catalogue_status` is cached per process, so a flipped `status:` header takes effect after the service restart a deploy performs; the translator runbook must say so, or a reviewer will think the flip failed.
11. **The server's language on a stripped header** [deferred: when the first language is reviewed]. With no `?lang=`, the server re-derives the language from the websocket handshake's `Accept-Language`; a proxy that strips that header there makes server renders fall back to English while the page follows the browser. Harmless while only English is enabled; when the first other language is enabled, consider pinning the chosen language into the URL (for example with `history.replaceState`).
12. **`Sub-region:  None`** [deferred: a later package]. An unassessable site's report prints `Sub-region:  None`, a pre-existing defect pinned byte for byte by `tests/golden/reports/case-unassessable.txt` (and exempted in the leak test); fix it in a later package with a deliberate golden update.

Two further notes, from the project memory rather than the review, are also in Task 1: `test_app_ui_takes_a_request_and_reads_lang_from_it` assumed German is not reviewed (Step 3), and test 4 held sidecar values to the template rule although they render verbatim (Step 2).
