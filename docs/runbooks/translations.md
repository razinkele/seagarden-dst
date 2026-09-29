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
| `params/i18n/<lang>.yaml` | species names, method names and their unit labels, the two cultivation-group labels (`macroalga`/`shellfish`), and calibration notes - all derived from the parameter files, not hand-listed |

Every value is a sentence or label; `{words_in_braces}` are placeholders the tool fills in
(a number, a name). **Leave the placeholder names exactly as they are** and put them where
your language wants them in the sentence. Keep any space at the start or end of a value:
many values are fragments joined to others (`app.report.pressure_note`, one of the report's
option lines, keeps two leading spaces in front of `{note}` in every language, English
included).

Every command below runs from the repository root, in a Python environment set up as
README's "Run it" section describes (`pip install -e ".[app,dev]"`). They are written
exactly as the maintainer runs them, inside the micromamba environment `shiny`:
`micromamba run -n shiny` runs the rest of the line inside it, and
`MKL_THREADING_LAYER=SEQUENTIAL` works around a numpy build quirk specific to that one
environment. In any other environment, drop both prefixes and run what remains.

Easiest way to read everything at once, English beside your language:

    micromamba run -n shiny python scripts/i18n_review_sheet.py <lang> > review-<lang>.md

Then edit the YAML files, not the sheet. The sheet is generated; the files are the truth.

## Rules that are not stylistic

- Units, numbers, Latin species names, project codes and programme names stay as they are.
- Numbers keep the decimal **point** (`0.1 ha`), dates are year-month-day. This is a
  deliberate tool-wide decision, not an oversight.
- Inside a value, use your language's own quotation marks for a quoted phrase - Polish
  „…”, Lithuanian „…“, Danish »…«, Swedish ”…”, German „…“ - **never a plain double
  quote.** Every value is itself wrapped in `"..."`; an unescaped `"` inside it ends the
  value early and the whole file stops loading (see the fifth bullet under "Checking your
  work").
  German already does this correctly today: `app.status.site_ready` reads `...Auf
  „Bewerten“ klicken.` with its own low-high quotes inside an ordinary double-quoted value.
- The bow-tie state names `Low`, `Moderate` and `High` stay in English everywhere. The
  words *around* them are translated, and read identically in all four places that say
  them: `app.results.p_top`, `app.report.p_top`, `adapters.bowtie.framing_high` and
  `adapters.bowtie.framing_low` - German has all four as "P(Top-Ereignis ...)". Only the
  state name itself (the literal `High` inside the two framing sentences; `{state}`
  elsewhere) stays English, shown raw beside the translated sentence.
- Four sentences carry legal weight. Translate them conservatively and read them twice:
  `app.report.footer`, the last paragraph of `app.shell.about.body`,
  `suitability.legal.no_record`, `app.report.legal_caveat`. If the English is wrong or
  unclear, **say so** (issue or e-mail, addresses in the app's Feedback dialog,
  `app.shell.feedback.body`) rather than translating around it; a corrected English
  sentence is re-translated into every language.
- Do not add or remove keys. If a sentence in your language needs a different structure,
  restructure the value; the key set is fixed by the English file.

## Checking your work

    MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest tests/test_i18n_guards.py -q

Every message below keeps the exception class pytest reports and the message text exactly
as printed, captured against a scratch copy of the German files broken on purpose for
this runbook, never against the repository's own files. pytest reports the file's *full*
path on whatever machine runs it; these examples shorten that to the path from the
repository root, `app/locales/de.yaml`, and change nothing else.

- **A placeholder mistyped or dropped** -
  `AssertionError: app/locales/de.yaml: app.status.site_ready: placeholders ['label', 'n', 'scal'] differ from English ['label', 'n', 'scale']`.
  Fix: spell the placeholder exactly as English does (`{scale}`, not `{scal}`) - move it
  in the sentence if you need to, never rename or drop it.
- **A key deleted, renamed or added** -
  `AssertionError: app/locales/de.yaml: missing ['app.shell.close'], extra ['app.shell.dismiss']`.
  Fix: put the key back under its original name. The key set is fixed by the English
  file: a deleted key shows up as "missing", an invented one as "extra", and a rename -
  shown here - as one of each at once.
- **A leading or trailing space lost** -
  `AssertionError: app/locales/de.yaml: app.report.pressure_note has whitespace (' ', ''), English ('  ', '')`.
  Fix: restore the value's whitespace exactly, even where it looks like a stray space in
  the editor - here, two leading spaces and none trailing.
- **A value emptied** -
  `AssertionError: app/locales/de.yaml: app.report.caveats is empty where English is not`.
  Fix: put the translated text back. An empty value is only allowed where English's own
  value is empty too.
- **A plain `"` inside a value** - one stray quote breaks the YAML file, which fails
  every guard test that reads it (six of the seventeen, in this example), each with the
  same parser error:

  ```
  yaml.parser.ParserError: while parsing a block mapping
    in "<unicode string>", line 12, column 3:
        app.nav.site: "Standort"
        ^
  expected <block end>, but found '<scalar>'
    in "<unicode string>", line 243, column 28:
        app.report.caveats: "VOR"BEHALTE"
                                 ^
  ```

  The first location (line 12) is just where the file's mapping began; ignore it. The
  second (line 243, column 28) is the actual stray quote. Fix: replace it with your
  language's own quotation marks (see "Rules that are not stylistic" above). Left
  uncaught, this is also the shape of failure the last paragraph below is written for:
  the stray quote fails inside the loader itself (`yaml.safe_load` in `Catalogue.load`,
  `src/seagarden_dst/i18n.py:135`), not in some later rendering step, and in the running
  app `enabled_languages` catches exactly that, disables the language, and logs the
  warning described there.
- **`status: reviewed` without `reviewed_by`/`reviewed_on`** -
  `ValueError: app/locales/de.yaml: status 'reviewed' needs reviewed_by and reviewed_on`.
  Fix: add both fields (see "Switching a language on" below for the exact lines), or set
  `status` back to `machine-draft` if the review is not actually finished.
- **`status: reference`** -
  `AssertionError: app/locales/de.yaml: only English is the reference; every other language is a draft or reviewed`.
  Fix: `reference` is reserved for `en.yaml`. Use `machine-draft` while reviewing, or
  `reviewed` once it is done.

To see your language in the running app before it is enabled:

    SEAGARDEN_SHOW_DRAFT_LANGUAGES=1 micromamba run -n shiny shiny run app.app

then open `http://127.0.0.1:8000/?lang=<lang>`. The switch accepts `1`, `true`, `yes` or
`on` (any case); anything else, including a typo, leaves drafts hidden - it fails closed,
so getting this wrong is safe, just unhelpful.

A bilingual "machine translation, not yet reviewed" banner shows under the navbar, and a
downloaded text report opens with the same two-language line (a downloaded JSON report
instead carries top-level `"language"` and `"draft"` keys). That is expected until the
step below.

## Switching a language on (maintainer)

A language is live when **all three** files carry:

    status: reviewed
    reviewed_by: "Name, institution"
    reviewed_on: 2026-11-30

next to the `translated_by` line already there - leave that one as it is; every
non-English file needs it, reviewed ones included, and removing it fails the suite too.

Two different checks enforce this, and the two mistakes above behave differently at
runtime, not only in the test:
`Catalogue.load` (`src/seagarden_dst/i18n.py`) refuses to load a file that says
`status: reviewed` without both `reviewed_by` and `reviewed_on` - that is the `ValueError`
above. It fails the suite (`test_4d_every_catalogue_file_on_disk_loads`) before the file
can ever reach a server, and if it somehow did reach one anyway, the language would be
fully disabled and logged (see the last paragraph below) - `SEAGARDEN_SHOW_DRAFT_LANGUAGES`
would not bring it back, because it is not a draft, it is unreadable.
The separate rule that only `en.yaml` may say `status: reference` is *not* the loader's:
the loader accepts `reference` on any file without complaint, so `catalogue_status`
(`app/i18n.py`) simply treats a non-English `reference` file the same as an ordinary
unfinished draft - `machine-draft` - hidden from the default menu but visible behind
`SEAGARDEN_SHOW_DRAFT_LANGUAGES`, same as any language still under review. Nothing at
runtime stops it; only guard test 4
(`test_i18n_guards.py::test_4_catalogue_hygiene`) does, which is why running the suite
before every merge matters here specifically.

Make the change in a pull request titled `i18n(<lang>): reviewed by <institution>`, run
the full suite (`MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest -q`),
merge, deploy as usual (`docs/runbooks/deploy.md`). **The change takes effect when the
service restarts**, which a deploy does: `catalogue_status` reads each language's status
once per process and caches it, so a `status:` header flipped on disk has no effect until
the next restart. No environment variable is needed on the live instance: the menu shows
every reviewed language on its own. `SEAGARDEN_LANGUAGES=en,de` restricts the menu to a
comma-separated list if a partner asks for a staged rollout - English is shown regardless
of whether you list it.

To take a language down again, set `status: machine-draft` in any one of its three files
and deploy.

A language that simply is not finished - a file missing entirely, or present but still
`machine-draft` - is left out of the menu without a fuss and without a log entry: that is
the ordinary state all five languages are in right now, and it is exactly what a language
mid-review looks like too. Only a file the tool cannot even parse is different - the
errors above, or any other malformed header, value or YAML: `enabled_languages`
(`app/i18n.py`) catches that failure, disables that language alone, and logs it once per
process as a WARNING, one per distinct message, worded `catalogue for language 'de' is
broken and disabled: <ExceptionType>: <text>`. English is never a candidate for this
check, so it can never be disabled this way. Either way - unfinished or actually broken -
one language's trouble never takes the rest of the site down.

Dry run by the author on 2026-09-29 against copies of the German files: both transitions
behaved as written.
