# Package I — Internationalisation: the DST in German, Polish, Danish, Lithuanian and Swedish

**Status:** design, 2026-09-28. Binding authority above it:
`SeaGarden_DST_functional_specification_v0.1.md` (§1 premises, §3.2 stack, §4 doors, §7.4
tiers) and `docs/superpowers/specs/2026-09-13-dst-data-layer-design.md` (§8 work packages).
Neither document mentions a language other than English; I§9 records the amendment.

## I§1 What this package is, and what it is not

The tool serves four jurisdictions (DK, DE, PL, LT; `regulatory.JURISDICTIONS`), the Lead
Partner has asked for Swedish as well, and today it speaks English only. This package makes every sentence a user
reads available in **six languages — English, German, Polish, Danish, Lithuanian and
Swedish** — without changing what the tool says in English, without putting UI concerns
into the model core, and without adding a dependency.

Three packages, each reviewable on its own:

- **I-0 — the identifier split.** English prose is used as an *identifier* in three
  places (I§3). Splitting key from label is a pure refactor with no visible change, and
  it has to land before a single translation does, or the translation changes state keys.
- **I-a — the seam.** The `Message` type and catalogue in the core; every core prose
  site converted; the app built per request in a chosen language; the language menu;
  the params sidecar; the English reference catalogues; the guard tests. English output
  is byte-identical before and after.
- **I-b — the five languages.** Machine-draft catalogues for de, pl, da, lt, sv, each
  marked `status: machine-draft`; the review runbook; the enablement gate; README,
  CHANGELOG and the functional-spec amendment.

Not this package: live language switching without a page reload (I§2), locale-specific
number and date formats (I§7), plural grammar (I§7), translating docstrings, comments,
runbooks, commit messages or the README (I§7), and translating regulatory record content,
which does not exist yet (package F2 owns the display of whatever GMU delivers at M12).

## I§2 Decisions taken with the user (2026-09-28)

| Question | Decision | Why |
|---|---|---|
| Who produces the translations? | **Machine drafts, partner review before a language goes live.** A language appears in the menu only once a native speaker has reviewed its catalogue and said so in the file header (I§6). | The caveats carry legal weight — *"not a basis for permitting or consent"* — and a mistranslated one is a liability. Drafts get the partners something concrete to review instead of an empty spreadsheet. |
| How does a user change language? | **`?lang=xx` and a page reload**, from a navbar menu of relative links. First visit: the browser's `Accept-Language`, then English. | Smallest stack; every UI builder stays a plain function; the reload clears a stale assessment for free, which is the invariant `app.py` already defends. |
| Is the catalogue text in `params/` translated? | **Yes, in a sidecar beside the data** (`params/i18n/<lang>.yaml`). Scientific names stay Latin. | README rule: a new species is a YAML file, not a release. A translation of its name must be a YAML file too. |
| How does core-generated prose become translatable? | **A `Message` value** — stable key, parameters, English on `str()` — returned wherever the core produces prose today. The app translates by key. | Alternative A (keys only) makes the core unreadable from a notebook, which the README promises. Alternative B (a locale in a context variable inside the core) hides per-session state in a pure package and is unreliable under Shiny's async reactive contexts. `str(message)` equals today's English, so every core test asserting on prose keeps passing. |
| Catalogue format? | **YAML, flat dotted keys, one file per language**, English as the reference. | No compile step, `pyyaml` is already one of the core's four dependencies, and the tool must be reconstructible from the repository alone in 2034 (spec §1 premise 2). gettext's plural rules are not needed once the one counted sentence is phrased count-neutrally (I§7); its English-sentence-as-key convention means rewording English invalidates every translation, which dotted keys avoid. |

## I§3 I-0 — the identifier split

Three places use an English sentence as a key. Each is split into an identifier and a
label; the identifier is what state, signatures, CSS and tests hold. **I-0 knows nothing
of `Message`** — its labels are plain English `str` tables, and I-a converts them along
with everything else in I§5.1. That keeps I-0 a refactor with no new type.

| Today | After I-0 | Where it is held today |
|---|---|---|
| `SCALES = {"community farm (0.1 ha)": 1_000.0, ...}` | `SCALES = {"community_farm_0_1_ha": 1_000.0, ...}` with keys `mini_farm_kit`, `community_farm_0_1_ha`, `community_farm_1_ha`, `small_commercial_5_ha`; `SCALE_LABELS: dict[str, str]` beside it, the only place the English label lives | `assess_site(scale=...)` default, `state._DEFAULTS["scale"]`, `user_mode.MODES[*]["scale"]`, the Catalogue select, `scenarios.compare` labels, the sidebar status sentence in `app.py` (`{scale}` must go through `SCALE_LABELS` or the slug reaches the screen), four test files, the golden snapshot's scenarios half |
| `caveats["nutrient forcing"]`, `["site conditions"]`, `["calibration"]` | `caveats["nutrient_forcing"]`, `["site_conditions"]`, `["calibration"]`; `CAVEAT_LABELS: dict[str, str]` for display | `api.assess_site`, `tests/test_adapters.py`, `tests/test_api.py`, both renderers |
| `Verdict` values (`"suitable"`, …) doubling as display text | Value stays the identifier and the CSS class (`sg-verdict-suitable`); `Verdict.label -> str` is what is displayed | `_widgets.verdict_pill`, `results.py`, `report.py` |

Two more identifiers are displayed raw and are the same conflation, but need no key
change: `SpeciesParams.group` (`"macroalga"`, `"shellfish"`, shown in the species table and
interpolated into a core sentence in `suitability.assess`) and `SiteContext.confidence`
(`"low"`, shown in the report). I-0 leaves them; I-a gives them catalogue keys
(`params.group.<g>`, `contracts.confidence.<c>`) and test 6 is what catches them if it
does not.

`excluded` is already keyed by species key and needs no split. `SpeciesOption.constraints`
tuples change type in I-a, not here.

**The golden snapshot does not change in I-0.** `tests/test_golden_snapshot.py` labels
its scenarios by species key, not by scale, so the rename touches no captured value; the
plan asserts the golden passes without `--snapshot-update`. (An earlier draft of this
section expected a label-only diff. The English *report* golden of test 10 is created in
I-0.)

## I§4 The core module `seagarden_dst/i18n.py`

No Shiny import, no file IO beyond reading its own package data, no global mutable state.

### I§4.1 `Message`

```python
@dataclass(frozen=True)
class Message:
    key: str
    params: Mapping[str, object]      # display-ready scalars, or nested Messages

    def __str__(self) -> str: ...      # English, from the packaged reference catalogue
    def to_dict(self, language: str = "en") -> dict: ...
        # {"key": ..., "params": {...}, "text": ...}; nested Messages become their text
    @classmethod
    def literal(cls, text: str) -> Message: ...
        # key "literal", params {"text": text}: for prose that is DATA, not code
```

Rules the type enforces:

- **Parameters are display-ready.** A caller that formats a number does so before building
  the message (`depth=f"{site.depth_m:g}"`), so catalogue values contain placeholder
  *names* only and never format specs. A translator cannot break `{depth:g}` because it
  never reaches them; test 4 of I§8 asserts no catalogue value contains `{name:spec}`.
- **Nested messages render in the same language.** `Message("suitability.physical.unsupported_group",
  method=method.label, group=...)` carries another `Message` as a parameter; rendering
  recurses. This is how `method.name` — data from `methods.yaml` — appears inside a
  sentence the core composes.
- **`literal` is for data, not for laziness.** A calibration `note:` from a species
  YAML, a `method.name` composed into a core sentence, a `ForcingUnavailable` message
  from the reader: text the core did not author. It renders as-is in every language
  unless the `Translator`'s text index (I§5.4) has a translation for that exact source
  string, which it does for every YAML-sourced string the sidecar covers and never for a
  reader diagnostic. Test 5 guards that `literal` appears only at allowlisted sites.
- **`Message.join(*parts)`** composes optional sentences (the adapters' notes) as one
  message with key `_join`; it renders its parts in the same language, separated by a
  space.
- **The app never constructs a `Message`.** `Message.__str__` reads the core's English
  catalogue, so an app-built `Message("app.…")` would raise on `str()`. App chrome goes
  through `Translator.__call__` with a key; core prose arrives as a `Message` and is
  rendered with `Translator.render`.
- **Equality is by key and params**, so tests can assert on structure without rendering.
  `Message` is not hashable; nothing needs it to be.

### I§4.2 `Catalogue` and rendering

```python
LANGUAGES: tuple[str, ...] = ("en", "de", "pl", "da", "lt", "sv")
DEFAULT_LANGUAGE = "en"

class Catalogue:
    @classmethod
    def load(cls, language: str, *roots: Path) -> Catalogue: ...
    status: Literal["reference", "machine-draft", "reviewed"]
    reviewed_by: str | None
    reviewed_on: date | None
    def render(self, message: Message) -> str: ...
```

`render` looks the key up in this language, falls back to English for a missing key, and
raises `KeyError` only if English lacks it too — a missing English key is a defect, a
missing German one is an incomplete draft. Catalogues are loaded **once per process**,
lazily, the way `catalogue.PARAMS` already is: the English core catalogue is what
`Message.__str__` uses, and `Translator.for_language` returns a cached instance, so
`language_for`'s enabled-set check does not read eighteen YAML files per request.

### I§4.3 File format

One file per language per owner (I§5.4 says why three owners):

```yaml
language: de
status: machine-draft            # reference | machine-draft | reviewed
translated_by: "machine draft (Claude), <ISO date the draft was written>"
reviewed_by: null                # "Name, institution" once reviewed
reviewed_on: null                # ISO date
messages:
  calibration.tier.A.label: "Lokal kalibriert"
  suitability.physical.depth_outside: "Die Tiefe von {depth} m liegt außerhalb ..."
```

Keys are `<owner>.<subject>.<field>`, lower-case, dotted, stable. The English file carries
`status: reference` and no reviewer fields. Every language file has **exactly** the English
key set (test 1), so a key added in English without its five siblings fails CI — the
translation debt is visible in the build, not discovered by a Polish user.

## I§5 What becomes a `Message`

### I§5.1 In the core

Every core attribute, property or return value that is prose a user reads. The rule for a
reviewer: *if the string would be wrong in German, it is a `Message`.*

| Site | Today | After I-a |
|---|---|---|
| `Tier.label`, `Tier.presentation` | `str` | `Message` (`calibration.tier.<A-D>.label` / `.presentation`) |
| `Calibration.caveat()` | `str` | `Message`; a tier-D `note` from YAML is `Message.literal` |
| `Quantity.__str__` | English with `[tier]` | unchanged text; the not-applicable branch renders a `Message` |
| `Constraint.name`, `Constraint.reason` | `str` | `Message` (`suitability.<class>.name`, `suitability.<class>.<case>`) |
| `Suitability.explain()` | `str` | `Message` (`suitability.explain.none`, `.no_binding`, `.binding` with nested name and reason) |
| `SpeciesOption.binding_constraint` | `str` | `Message` |
| `SpeciesOption.constraints` | `list[tuple[str, str, str]]` | `list[tuple[Message, str, Message]]` — verdict value stays the identifier |
| `SiteAssessment.caveats`, `.excluded` | `dict[str, str]` | `dict[str, Message]` (slugged keys per I§3) |
| `SiteAssessment.pressure_note`, `removal_framing()` | `str` | `Message` |
| `REGIONS` | `dict[str, str]` | `dict[str, Message]` (`forcing.region.<key>`) |
| `SiteProvenance.label`, `.presentation` | `str` | `Message` |
| `SOURCE_NOTE_NO_POSITION`; `SiteContext.source_note` | `str`; `str = ""` | `Message`; `Message \| None = None`. Three call sites test its falsiness today (`results.forcing_for`, the banner, the report) and must test `is not None`, because an empty `Message` would be truthy |
| `SCALE_LABELS`, `CAVEAT_LABELS`, `Verdict.label` (from I-0) | `str` | `Message` |
| `SpeciesParams.group`, `SiteContext.confidence` (displayed) | identifiers shown raw | unchanged type; displayed through `params.group.<g>` and `contracts.confidence.<c>` |
| `eutropy_adapter` and `bowtie_adapter` notes | `str` | `Message` |
| `SpeciesParams.common_name`, `MethodParams.name`, `.anchoring_unit`, `.cultivation_unit` | `str` from YAML | unchanged type; the app translates through `Translator.species_name(key)`, `.method_name(key)` and the text index (I§5.4). `scientific_name` is never translated |
| `ForcingChoice.reason`, reader refusals | `str` | **unchanged** — operator diagnostics, English by design (I§7); wrapping them would touch `forcing.py`, `gridded.py` and their tests for no translation |

`to_dict()` on `SpeciesOption` and `SiteAssessment` gains a `language` argument and emits
each `Message` as `{"key", "params", "text"}`. The structure is stable and machine-readable
across languages; the text is what the requesting user read. This is a JSON export schema
change and CHANGELOG says so.

### I§5.2 In the app

`t()` is replaced, not extended. The app gets one object, passed explicitly:

```python
class Translator:
    language: str
    catalogue: Catalogue          # core + app + params keys merged, prefix-owned
    @classmethod
    def for_language(cls, language: str) -> Translator: ...   # loads the three catalogues
    def __call__(self, key: str, **params) -> str: ...    # app chrome
    def render(self, message: Message) -> str: ...        # core prose
    def quantity(self, q: Quantity) -> str: ...           # the report's number-with-tier
    def species_name(self, key: str) -> str: ...          # sidecar, else the YAML English
    def method_name(self, key: str) -> str: ...
```

`SpeciesOption.species_name` and `.method_name` stay English from YAML; the headline, the
results table and the report call `tr.species_name(option.species_key)` instead of
reading them.

- `app_ui` becomes `def app_ui(request: Request)` — Shiny 1.8 accepts a callable of the
  request — and passes `tr` into every panel factory: `site_ui("site", tr)`,
  `catalogue_ui("cat", tr)`, and so on. The smoke test that calls each factory directly
  passes `Translator.for_language("en")`.
- `AppState` gains `language` and `translator`, set once by `server()` before any render,
  exactly as `forcing` is today. Module servers read `state.translator`. **No context
  variables**: Shiny's reactive contexts are async and a per-session contextvar is not
  reliably the same object in a render as in the effect that set it.
- Choices built at import today become functions of `tr`: `catalogue.SPECIES_CHOICES`,
  `user_mode.CHOICES`, the region select in `site.py`, the scale select.
- Small words that are prose get keys too: `_widgets._MONTHS` and `"(over winter)"`, the
  species table's `yes`/`no`, the marker tooltip's `unknown` depth, `Data confidence`.
  They are exactly what test 6 exists to find.
- `site_markers(tr)` renders region names and provenance labels to strings for deck.gl,
  and `test_every_marker_states_its_provenance` compares against rendered text. The
  default site label in `_set_site` (today `REGIONS[region]`) is rendered **at commit
  time in the session language**; `SiteContext.label` stays `str`, because it is what
  the user typed or accepted, not a message.
- The map tooltip's fixed label is the one string that stays English in every language,
  recorded as a known limit.
- The About, Help and Feedback modals are three keys each holding a whole markdown block,
  because a reviewer needs to read them as prose and a sentence-by-sentence split would
  produce German in English word order.
- The plain-text report is rendered through `tr`: section headings, field labels,
  `tr.quantity()` for every number, `tr.render()` for every message. The JSON download
  calls `assessment.to_dict(language=tr.language)`.
- The page carries `lang="<code>"` on the root element (accessibility, hyphenation,
  screen readers); `ui.page_navbar` takes `lang`.

### I§5.3 Choosing the language

One function, used by both halves so they cannot disagree:

```python
def language_for(query: str, accept_language: str | None, enabled: Sequence[str]) -> str
```

Order: `lang=` in the query string if it names an enabled language; otherwise the first
enabled primary subtag in `Accept-Language` by descending `q`; otherwise `en`. A request
for a language that exists but is not enabled (I§6) gets English — the gate is a gate,
not a menu filter. `app_ui(request)` reads `request.query_params` and `request.headers`;
`server()` reads `session.input[".clientdata_url_search"]()` (Shiny sets it from
`window.location.search` on connect) and `session.http_conn.headers`. Test 7 asserts the
same function drives both and that the two agree for the same inputs.

The navbar menu lists the enabled languages as relative links `?lang=xx` — relative, so
the sub-path proxy on laguna (`/seagarden-dst/`) needs no configuration. The current
language is marked and not a link.

### I§5.4 Three owners, three files per language

| Owner | Path | Keys | Why separate |
|---|---|---|---|
| Core | `src/seagarden_dst/locales/<lang>.yaml` | `calibration.*`, `suitability.*`, `api.*`, `forcing.*`, `adapters.*` | Package data; `str(Message)` must work with the core installed alone. `pyproject.toml` gains `"seagarden_dst" = ["locales/*.yaml"]` and `test_packaging.py` asserts the glob covers the tree |
| App | `app/locales/<lang>.yaml` | `app.*` | Chrome the core never sees |
| Params | `params/i18n/<lang>.yaml` | `params.species.<key>.common_name`, `params.methods.<key>.name`, `.anchoring_unit`, `.cultivation_unit`, `params.species.<key>.calibration.<region>.note` | Data beside data (I§2); covered by the existing `*/*.yaml` package-data glob |

`Translator` merges the three into one flat namespace. Prefixes are owned, and test 2
asserts no key appears in more than one file. A params key missing for a species falls
back to the species YAML's own English text, so a new species without translations ships
readable, in English, with the sidecar's absence visible in test 3 rather than in
production.

**The text index — how a `literal` gets translated.** The sidecar is keyed by species and
method key, but a `literal` carries only its English text. `Translator` therefore builds,
once, an index from whitespace-normalised English text to translated text by pairing each
sidecar entry with its counterpart in `params/` (`params.methods.raft.name` ↔
`methods.yaml`'s `name: Raft`). `render` on a `literal` consults the index and falls
through to the text itself. This is what makes `method.name` inside a core sentence and a
calibration `note:` translatable without the core knowing a sidecar exists. Test 3 also
asserts every sidecar entry has an English counterpart in `params/`, so a stale entry for
a renamed method is a failing test rather than a silently untranslated sentence.

For partner review, `scripts/i18n_review_sheet.py <lang>` writes one markdown table per
language merging all three files with the English beside each row. It is a convenience
for the reviewer, not a source of truth; the YAML files are.

## I§6 The enablement gate

A language is **enabled** when its three catalogues all carry `status: reviewed` with
`reviewed_by` and `reviewed_on` filled, **or** when the deployment sets
`SEAGARDEN_SHOW_DRAFT_LANGUAGES=1`, which is for a partner review round on a staging URL
and nothing else. `SEAGARDEN_LANGUAGES` may further restrict the set (a comma list); it
defaults to all six. English is always enabled.

A draft language, when shown under the override, carries a banner under the navbar in that
language and in English — *"Machine translation, not yet reviewed. Maschinelle
Übersetzung, noch nicht geprüft."* — so a screenshot of a draft page can never pass for
a reviewed one. The live instance, with neither variable set, shows English only until
the first review lands, and that is the intended state at the end of I-b.

Flipping a language on is a data change: the reviewer edits three header fields and opens
a pull request. The runbook `docs/runbooks/translations.md` tells them how, including the
review sheet, what "reviewed" commits them to (the caveats, by name), and how to report a
wrong English sentence rather than translating around it.

## I§7 Explicit exclusions, with reasons

- **Decimal separator and dates.** All five target languages use a decimal comma. Python's
  `locale` module is process-global and unsafe in a server, so the tool keeps the dot and
  ISO dates everywhere, and the About modal's help text says so in each language. Revisit
  only if a partner review asks for it; the change would live in `Translator.quantity()`.
- **Plurals.** Polish and Lithuanian have three or more plural forms. The catalogue has no
  plural machinery; the one counted sentence (`"{n} species selected"`) is rephrased
  count-neutrally (`"Species selected: {n}"`) and test 4 asserts no catalogue key ends in
  `_one` or `_other`, the convention that would signal someone adding plurals by hand.
- **Units and symbols** (`psu`, `µmol/L`, `kg DW`, `m²`, `°C`) are not translated.
- **Scientific names** are Latin in every language.
- **Operator diagnostics** — `ForcingChoice.reason`, reader refusals, `ValueError`
  messages — stay plain English `str`, not even wrapped in `literal`. They name paths and
  schema versions for whoever runs the service, and that person reads the runbooks,
  which are English. The banner sentence around `reason` is keyed; the reason inside it
  is not.
- **Everything that is not the running app**: docstrings, comments, commit messages,
  CHANGELOG, README, runbooks, this document.
- **Live switching.** Decided against in I§2; the design does not preclude it, because
  every builder already takes `tr` as an argument, but nobody has asked for it.

## I§8 Testing

English output is unchanged, so `tests/test_golden_snapshot.py` (unchanged by I-0),
every report assertion in `app/tests/test_app_smoke.py` and every core test
asserting on prose stand as they are, with `.lower()`-style calls on former strings
wrapped in `str()`. New:

1. **Key parity.** For each language file, its key set equals the English file's, per
   owner. Reports missing and extra keys by name.
2. **Prefix ownership.** No key in two files; every key's first segment matches its owner.
3. **Params coverage.** Every species and method key in `params/` has every sidecar key in
   every `params/i18n/*.yaml` that exists.
4. **Catalogue hygiene.** Placeholder *names* per key are identical across languages; no
   value contains a format spec (`{x:...}`); no key ends `_one`/`_other`; every file
   parses with the header fields I§4.3 names.
5. **`literal` discipline.** An AST scan finds `Message.literal(` nowhere under `app/` —
   app text is always keyed — and, in the core, only at call sites named in an allowlist
   inside the test (`file:function`), so a new `literal` fails until someone lists it and
   says which of I§4.1's three kinds it is. The same offenders-list pattern as
   `test_no_app_module_imports_shiny_deckgl_at_module_scope`.
6. **The pseudo-locale leak test.** A synthetic language `xx` whose every value is
   `⟦key⟧` is built in memory, including a synthetic sidecar; the whole page and each
   panel are rendered with `Translator` for `xx`, plus a full report and a JSON export
   for an assessment at a placeholder site. Then **every text node** of the HTML (with
   `<style>`, `<script>`, attributes and the base64 images stripped) and every line of
   the report must be one of: a `⟦…⟧` marker, a number, a unit or symbol, a Latin
   scientific name, a region key, a date, or an entry on an explicit allowlist inside
   the test (the brand mark `SeaGarden DST`, the funding lockup's alt text). Anything
   else is a string that bypassed the seam, whether or not it ever entered a catalogue —
   which is why this is stronger than asserting the English values are absent, and why
   it replaces an AST scan for literals reaching `ui.*`, which would flag CSS and ids all
   day.
7. **One chooser.** `language_for` is the only symbol either half imports for the
   purpose; parametrised cases for query wins, `Accept-Language` with `q`, an unenabled
   language falling to English, garbage falling to English.
8. **The gate.** With no environment override and a `machine-draft` German catalogue,
   `?lang=de` renders English and the menu omits German; with the override set, German
   renders and the draft banner is present in both languages.
9. **`Message` round trip.** `to_dict()` of a nested message renders inner text in the
   requested language; `str()` equals the English render; equality is structural.
10. **English byte-identity.** `render_report` for every placeholder site is identical
    before and after I-a, captured as a golden text file in I-0 (English only) and
    asserted unchanged in I-a. Two lines would otherwise defeat this: the `Generated:`
    line carries `date.today()` and `__version__`. `render_report` gains a keyword-only
    `today: date` parameter that the module server passes as `date.today()` — the
    pattern `regulatory.py` documents, for the same reason — and the golden test passes a
    fixed date and replaces `v{__version__}` with `v*` before comparing. I-0 makes the
    signature change; I-a inherits it.
11. **The catalogue is in the wheel.** `test_packaging.py` gains the locales glob.

Tests 1–5 and 7 live in `tests/test_i18n_guards.py`; test 9 lives in `tests/test_i18n.py`
(both core, default selection). Tests 6 and 8 live in `app/tests/test_i18n_leaks.py`;
test 10 lives in `tests/test_report_golden.py`, because `--snapshot-update` is registered
in `tests/conftest.py`, and it `importorskip`s `shiny` so the spatial CI job can collect
`tests/` without the app extra.

## I§9 Amendments this design requires

- **Functional specification** — a new **[Amendment 6]**, dated, under "Amendments since
  v0.1": the tool is delivered in six languages with English as the reference and
  fallback; a language goes live only after native-speaker review; number formats are
  not localised; the Application Form (`SeaGarden_DST_proposal_extract.md`) and v0.1 say
  nothing about language, so this is a requirement added by the Lead Partner on
  2026-09-28, not a correction.
- **Data-layer design §8** — a row **I** (I-0, I-a, I-b) with the effort below and a
  pointer to this document's done-when. Not a data-layer concern, but §8 is where every
  package is tracked, including A0 and G, which were not data-layer concerns either.
- **`pyproject.toml`** — the locales package-data glob; nothing in `dependencies`.
- **`README.md`** — a *Languages* section: the six codes, how to enable one, the review
  rule, the two environment variables; the layout block gains `i18n.py`, `locales/` and
  `params/i18n/`.
- **`docs/runbooks/deploy.md`** — the two environment variables on the systemd unit.
- **`CHANGELOG.md`** — I-0 under *Changed* (scale keys, caveat slugs, `Verdict.label`,
  `render_report(today=)`, the English report goldens; the assessments golden unchanged);
  I-a under *Added* (the seam, English only, JSON export schema change); I-b under
  *Added* (five draft catalogues, none enabled) with a *Known limits* line that the live
  instance is still English until the first review.

## I§10 Effort

| Package | Effort | Spec §13 row |
|---|---|---|
| I-0 | 0.1 PM | none — propose amendment |
| I-a | 0.5 PM | none — propose amendment |
| I-b | 0.3 PM, of which the drafts are a day and the runbook and gate the rest | none — propose amendment |

0.9 PM with no §13 row, added to the 1.7 PM the data-layer design already proposes
amending. Partner review time is theirs, not counted here.

## I§11 Done-when

**I-0**

1. `grep -rn "community farm\|mini-farm kit\|small commercial" src app tests
   --exclude-dir=golden` is expected to hit: `SCALE_LABELS` itself, its mirror in
   `test_scenarios_scales.py`, comments and docstrings that name the hardware in prose,
   and label assertions in tests (`assert "community farm (0.1 ha)" in text`, the old
   prose key rejected by `test_the_old_prose_key_is_refused_loudly`). Outside those, no
   code path builds or compares against a prose scale string. (`tests/golden/` embeds
   the labels by design, I§3; the English catalogue takes them over in I-a.)
2. `caveats` keys are slugs; `test_adapters.py` and `test_api.py` index by slug.
3. `tests/golden/assessments.json` is unchanged and its test passes without
   `--snapshot-update`.
4. `pytest` and `ruff` clean; the English report golden file (test 10) is committed.

**I-a**

5. `python -c "from seagarden_dst import assess_site, SiteContext; print(assess_site(SiteContext.from_region('LT-coastal')).caveats)"`
   prints readable English from a core-only install — the notebook promise holds.
6. Tests 1–11 pass; test 6's pseudo-locale render finds no leak.
7. `?lang=xx` for an enabled language renders the page, every panel, the report and the
   JSON in that language; `?lang=` for anything else renders English.
8. The English report is byte-identical to the I-0 golden file.
9. `to_dict()` emits `{"key", "params", "text"}` for every message and the CHANGELOG names
   the schema change.
10. No `t(` remains in `app/`; `grep -rn "def t(" app` is empty.

**I-b**

11. Five draft catalogues per owner exist, each `status: machine-draft` with
    `translated_by` filled, and test 1 passes for all six languages.
12. With no environment variable set the menu shows English alone and `?lang=de` renders
    English (test 8).
13. `docs/runbooks/translations.md` exists and has been followed once by the author to flip
    a language to `reviewed` on a throwaway branch and back, so the instructions are known
    to work.
14. `SeaGarden_DST_functional_specification_v0.1.md` carries Amendment 6; README, deploy
    runbook and CHANGELOG carry the I§9 items.
