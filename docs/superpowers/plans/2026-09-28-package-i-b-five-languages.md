# Package I-b — Five Languages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Machine-draft catalogues for German, Polish, Danish, Lithuanian and Swedish, each honest about being a draft, behind the review gate I-a built; a runbook a partner can follow to review one and switch it on; the documentation amendments the spec requires.

**Architecture:** No code changes to the seam. Three YAML files per language (core, app, params sidecar) with `status: machine-draft` headers; the parity, hygiene and gate tests of I-a decide whether a file is acceptable. The live instance keeps showing English until a reviewer flips a language's three headers to `reviewed`.

**Tech Stack:** YAML, pytest. The drafts are written by the implementer (an LLM) and are labelled as such in every file header.

**Spec:** `docs/superpowers/specs/2026-09-28-package-i-internationalisation-design.md` — I§6, I§9, I§10, I§11 clauses 11–14. **Prerequisite:** I-a merged.

## Global Constraints

- `MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest ...`; shared tree, commit per task; `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` on every commit.
- **Every draft file header is exactly:** `language: <code>`, `status: machine-draft`, `translated_by: "machine draft (Claude), <ISO date written>"`, `reviewed_by: null`, `reviewed_on: null`, then `messages:`.
- **Translation rules, applied to every value:** keep every `{placeholder}` name unchanged; keep units, symbols, numbers, project codes (`WP3`, `A2.3`, `D2.2`, `STHB.02.02-IP.01-0006/25`), programme and product names (`SeaGarden`, `Interreg South Baltic`, `OLAMUR`, `EUTROPY`, `MARBEFES`, `Copernicus`, `EMODnet`, `HELCOM`) and Latin names untouched; translate `psu` as `psu`; keep the report's fixed-width prefixes (`Site:        {site}` etc.) at the same column widths where the language allows, and at least keep the two-space indent on option lines; keep markdown structure (headings, list markers, table pipes) in the modal bodies; do not add plural forms (`_one`/`_other` keys are rejected by test 4); do not translate calibration `source:` strings, which are citations.
- **The legal-weight sentences** — `app.report.footer`, the last paragraph of `app.shell.about.body`, `suitability.legal.no_record`, `app.report.legal_caveat` — must be translated conservatively and are called out by name in the runbook for the reviewer.
- No language is enabled by this package: with no environment variable set, `enabled_languages()` returns `("en",)` after every task.

## Review Focus

1. **A placeholder renamed or dropped in translation** (`{Tiefe}` for `{depth}`) renders as a `KeyError` in production for that one sentence. Test 4 (I-a) catches it per key; every task runs it.
2. **Decimal comma creeping into a value** (`0,1 ha` in a scale label). Spec I§7 keeps the point; the hygiene test cannot see it, so each task's review step greps its three files for `\d,\d`.
3. **A draft mistaken for a reviewed language** because someone edits `status` without the reviewer fields. `Catalogue.load` refuses `reviewed` without `reviewed_by` and `reviewed_on` (I-a test); the runbook says so.
4. **Report column alignment drifting** so `Nitrogen:`/`Phosphorus:` values no longer line up in German. Cosmetic, but the report is what gets printed; Task 6's dry run renders a German report and the implementer eyeballs it.
5. **A sidecar key for a species that no longer exists** after a params change. Test 3 fails on stale keys; the runbook tells a reviewer what that failure means.

---

### Task 1: German (`de`)

**Files:**
- Create: `src/seagarden_dst/locales/de.yaml`, `app/locales/de.yaml`, `params/i18n/de.yaml`

**Interfaces:**
- Consumes: the three English key sets (`src/seagarden_dst/locales/en.yaml`, `app/locales/en.yaml`, `params_reference_keys()`).
- Produces: three files that pass tests 1–4 and leave `enabled_languages()` at `("en",)`.

- [ ] **Step 1: Generate the key skeletons from English**

Run: `micromamba run -n shiny python scripts/i18n_review_sheet.py de > /tmp/de-sheet.md` (the third column is empty; the sheet is the worklist). Then create the three files by copying the English structure:

```bash
sed -e 's/^language: en$/language: de/' -e 's/^status: reference$/status: machine-draft\ntranslated_by: "machine draft (Claude), 2026-10-01"\nreviewed_by: null\nreviewed_on: null/' src/seagarden_dst/locales/en.yaml > src/seagarden_dst/locales/de.yaml
sed -e 's/^language: en$/language: de/' -e 's/^status: reference$/status: machine-draft\ntranslated_by: "machine draft (Claude), 2026-10-01"\nreviewed_by: null\nreviewed_on: null/' app/locales/en.yaml > app/locales/de.yaml
```

(Use the real date.) For the params sidecar there is no English file; write it from `params_reference_keys()`:

```bash
MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -c "
import yaml
from app.i18n import params_reference_keys
doc = {'language': 'de', 'status': 'machine-draft',
       'translated_by': 'machine draft (Claude), 2026-10-01',
       'reviewed_by': None, 'reviewed_on': None,
       'messages': dict(params_reference_keys())}
print(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, width=100), end='')
" > params/i18n/de.yaml
```

- [ ] **Step 2: Run the parity test to confirm the skeletons are complete**

Run: `MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest tests/test_i18n_guards.py -q`
Expected: tests 1–4 pass (the values are still English; parity and hygiene only look at keys and placeholders).

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

- [ ] **Step 4: Verify and review the three files**

Run: `MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest tests/test_i18n_guards.py tests/test_i18n.py app/tests/test_i18n_app.py -q`
Expected: pass. Then `grep -nE '[0-9],[0-9]' src/seagarden_dst/locales/de.yaml app/locales/de.yaml params/i18n/de.yaml` prints nothing (no decimal commas), and `grep -c '{' app/locales/de.yaml` equals the same count on `en.yaml` (a coarse placeholder check; test 4 is the exact one).

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

Expected: German throughout; species and method names German; units and numbers unchanged; the footer sentence present.

- [ ] **Step 5: Confirm the gate still hides it, and commit**

Run: `MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -c "from app.i18n import enabled_languages, catalogue_status; print(enabled_languages(env={}), catalogue_status('de'))"`
Expected: `('en',) machine-draft`.

```bash
git add src/seagarden_dst/locales/de.yaml app/locales/de.yaml params/i18n/de.yaml
git commit -m "i18n(de): machine-draft German catalogues, not enabled (I-b)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: Polish (`pl`)

**Files:**
- Create: `src/seagarden_dst/locales/pl.yaml`, `app/locales/pl.yaml`, `params/i18n/pl.yaml`

Repeat Task 1's five steps with `pl`. Polish-specific notes: the count-neutral phrasing exists for Polish's plural forms — keep every sentence with `{n}` in the form "Wybrane gatunki: {n}" (noun first, then the number), never "{n} gatunków"; the sidebar and report say "Ocena" for the Assess action consistently. Worked examples:

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

### Task 3: Danish (`da`)

**Files:**
- Create: `src/seagarden_dst/locales/da.yaml`, `app/locales/da.yaml`, `params/i18n/da.yaml`

Repeat Task 1's five steps with `da`. Worked examples:

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

### Task 4: Lithuanian (`lt`)

**Files:**
- Create: `src/seagarden_dst/locales/lt.yaml`, `app/locales/lt.yaml`, `params/i18n/lt.yaml`

Repeat Task 1's five steps with `lt`. Lithuanian has plural forms too: keep `{n}` sentences noun-first ("Pasirinkta rūšių: {n}"). Worked examples:

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

### Task 5: Swedish (`sv`)

**Files:**
- Create: `src/seagarden_dst/locales/sv.yaml`, `app/locales/sv.yaml`, `params/i18n/sv.yaml`

Repeat Task 1's five steps with `sv`. Worked examples:

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

After Task 5: `MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest -q` — the whole suite, and test 1 now runs against six languages per owner. `enabled_languages(env={})` is still `("en",)` (spec I§11 clause 12).

---

### Task 6: The translations runbook, dry-run once

**Files:**
- Create: `docs/runbooks/translations.md`
- Test: manual dry run on a throwaway branch (spec I§11 clause 13)

- [ ] **Step 1: Write the runbook**

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
your language wants them in the sentence.

Easiest way to read everything at once, English beside your language:

    micromamba run -n shiny python scripts/i18n_review_sheet.py <lang> > review-<lang>.md

Then edit the YAML files, not the sheet. The sheet is generated; the files are the truth.

## Rules that are not stylistic

- Units, numbers, Latin species names, project codes and programme names stay as they are.
- Numbers keep the decimal **point** (`0.1 ha`), dates are year-month-day. This is a
  deliberate tool-wide decision, not an oversight.
- Four sentences carry legal weight. Translate them conservatively and read them twice:
  `app.report.footer`, the last paragraph of `app.shell.about.body`,
  `suitability.legal.no_record`, `app.report.legal_caveat`. If the English is wrong or
  unclear, **say so** (issue or e-mail, addresses in the app's Feedback dialog) rather than
  translating around it; a corrected English sentence is re-translated into every language.
- Do not add or remove keys. If a sentence in your language needs a different structure,
  restructure the value; the key set is fixed by the English file.

## Checking your work

    MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest tests/test_i18n_guards.py -q

- "missing" or "extra" keys: the file's keys no longer match English — restore them.
- "placeholders differ from English": a `{name}` was changed or dropped — restore it.
- "has a format spec": a `{name:...}` was written — placeholders take names only.
- A failure naming `params.species.<key>` you did not touch: the parameter files changed
  under you (a species was added or renamed); ask the maintainer.

To see your language in the running app before it is enabled:

    SEAGARDEN_SHOW_DRAFT_LANGUAGES=1 shiny run app.app     # then open ?lang=<lang>

A bilingual "machine translation, not yet reviewed" banner shows under the navbar. That is
expected until the step below.

## Switching a language on (maintainer)

A language is live when **all three** files carry:

    status: reviewed
    reviewed_by: "Name, institution"
    reviewed_on: 2026-11-30

The loader refuses `reviewed` without both fields. Make the change in a pull request titled
`i18n(<lang>): reviewed by <institution>`, run the full suite, merge, deploy as usual
(`docs/runbooks/deploy.md`). No environment variable is needed on the live instance: the
menu shows every reviewed language. `SEAGARDEN_LANGUAGES=en,de` restricts it if a partner
asks for a staged rollout.

To take a language down again, set `status: machine-draft` in any one of its three files.
```

- [ ] **Step 2: Dry-run the runbook**

On a throwaway branch (`git checkout -b tmp/translations-dry-run`), follow *Switching a language on* for `de` with `reviewed_by: "dry run"` and `reviewed_on: <today>` in all three files; run `MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -c "from app.i18n import enabled_languages; print(enabled_languages(env={}))"` and expect `('en', 'de')`; then set one file back to `machine-draft` and expect `('en',)`. `git checkout package-i-b-five-languages && git branch -D tmp/translations-dry-run` (branch names per the repository's convention at the time). Record in the runbook's last line: `Dry-run followed by the author on <date>; both transitions behaved as written.`

- [ ] **Step 3: Commit**

```bash
git add docs/runbooks/translations.md
git commit -m "docs(runbook): reviewing and enabling a language (I-b)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: The spec amendment, the work-package row, README and CHANGELOG

**Files:**
- Modify: `SeaGarden_DST_functional_specification_v0.1.md:28` (append Amendment 6 to the list)
- Modify: `docs/superpowers/specs/2026-09-13-dst-data-layer-design.md:773` (a row after G)
- Modify: `README.md` (*Languages* section: the sentence about I-b), `CHANGELOG.md` (`[Unreleased]`)

- [ ] **Step 1: Amendment 6**

After the `[Amendment 5]` bullet:

```markdown
- **[Amendment 6] — 2026-09-28, new requirement, not a correction.** The tool is delivered in six languages — English, German, Polish, Danish, Lithuanian and Swedish — with English as the reference and fallback. Neither the Application Form (`SeaGarden_DST_proposal_extract.md`) nor this document's v0.1 text mentions language; the requirement was added by the Lead Partner on 2026-09-28 and designed as package I (`docs/superpowers/specs/2026-09-28-package-i-internationalisation-design.md`). Two consequences a partner should know: a language is shown to users **only after a native speaker has reviewed its catalogue** and signed the file header (`docs/runbooks/translations.md`), so the live instance may show fewer than six languages at any time; and number and date formats are **not** localised — the decimal point and ISO dates are used in every language — because the Python `locale` machinery is process-global and unsafe in a server, and the tool must stay reconstructible with no extra dependency to 2034.
```

- [ ] **Step 2: The work-package row**

After row **G** in the data-layer design's §8 table:

```markdown
| **I** | Internationalisation (`docs/superpowers/specs/2026-09-28-package-i-internationalisation-design.md`) — I-0 identifier split, I-a the seam, I-b five machine-draft languages behind a review gate | `Message`-valued core prose; per-request `Translator`; `?lang=` menu; three catalogues per language; drafts for de/pl/da/lt/sv, none enabled until reviewed | — (not a data-layer concern; tracked here because every package is) | 0.9 PM *(no spec §13 row — propose amendment)* | I§11's fourteen clauses |
```

and change the opening line's "eleven packages" and total accordingly (`7.9 PM across twelve packages`), and the `**the spec §13 amendment to propose is 1.7 PM**` sentence to name `2.6 PM` with I's 0.9 added.

- [ ] **Step 3: README and CHANGELOG**

README *Languages*: replace `How to review and enable a language: docs/runbooks/translations.md (package I-b).` with `Machine-draft catalogues exist for all five languages; none is reviewed yet, so the live instance shows English. How to review and enable one: docs/runbooks/translations.md.`

CHANGELOG `[Unreleased]` `### Added`:

```markdown
- **Package I-b — five languages, as drafts.** Machine-draft catalogues for German, Polish,
  Danish, Lithuanian and Swedish (three files each: core, app, params sidecar), every header
  `status: machine-draft` and naming the machine as translator. **None is enabled**: the
  live instance shows English until a native speaker reviews a language and flips its
  three headers (`docs/runbooks/translations.md`). `SEAGARDEN_SHOW_DRAFT_LANGUAGES=1` shows
  them on a staging instance under a bilingual notice. Functional specification Amendment 6
  records the requirement; the data-layer design §8 gains row I.
  **Known limit:** the drafts have not been read by a speaker of any of the five languages;
  the legal-weight sentences in particular are unreviewed and must not be quoted from a
  draft.
```

- [ ] **Step 4: Run, commit**

Run: `MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest -q && micromamba run -n shiny ruff check .`
Expected: all pass (`tests/test_version.py` only checks the version heading, which is unchanged).

```bash
git add SeaGarden_DST_functional_specification_v0.1.md docs/superpowers/specs/2026-09-13-dst-data-layer-design.md README.md CHANGELOG.md
git commit -m "docs: Amendment 6 (six languages), data-layer §8 row I, README and CHANGELOG for I-b

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

I-b's done-when (spec I§11 clauses 11–14) is now met: fifteen draft files exist with filled `translated_by`, test 1 passes for six languages, the menu shows English alone with no variable set, the runbook has been dry-run once, and the four documents carry their amendments.
