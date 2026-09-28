# Package I-a — The i18n Seam Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every sentence a user reads is produced from a catalogue key, so a German, Polish, Danish, Lithuanian or Swedish catalogue can be dropped in (package I-b) without another code change — while the English output stays byte-identical and the core stays readable from a notebook.

**Architecture:** The core gains `seagarden_dst/i18n.py`: a frozen `Message(key, params)` whose `str()` is English from a packaged YAML catalogue, and a `Catalogue` loader. Every core prose site returns a `Message`. The app gains `app/i18n.py`: a per-language `Translator` (core + app + params catalogues merged, English fallback, a text index for YAML-sourced literals) chosen per request from `?lang=` / `Accept-Language`, passed explicitly into every UI builder and read reactively by every server renderer. Renderers become pure functions of `(data, tr)` so a pseudo-locale test can render everything headless and prove nothing bypassed the seam.

**Tech Stack:** Python 3.11, Shiny for Python 1.8 (`App(ui=callable(request))`, `page_navbar(lang=)`), pyyaml (already a core dependency), pytest, ruff. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-28-package-i-internationalisation-design.md` — I§4, I§5, I§6 (mechanism only; no non-English catalogue ships here), I§8 tests 1–11, I§11 clauses 5–10. **Prerequisite:** package I-0 merged (`docs/superpowers/plans/2026-09-28-package-i-0-identifier-split.md`); this plan assumes `SCALE_LABELS`, `CAVEAT_LABELS`, `Verdict.label`, `render_report(..., today=)` and `tests/golden/reports/` exist.

## Global Constraints

- Run every Python command as `MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest ...` (Git Bash). Never `pip install`.
- Shared working tree: never stash; commit at the end of every task.
- Commit messages end with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- **English is byte-identical.** `tests/golden/assessments.json` and `tests/golden/reports/*.txt` pass without `--snapshot-update` after every task. The one permitted English change is the sidebar status sentence (spec I§7: count-neutral phrasing), which no golden captures.
- Catalogue values carry placeholder **names** only, never format specs: numbers are formatted by the caller (`depth=f"{x:g}"`).
- `Message.literal(` appears nowhere under `app/` and only at the core call sites Task 8's allowlist names.
- The app never constructs a `Message`; app chrome goes through `tr(key, **params)`.
- No context variables; `tr` is passed explicitly, and server renderers read `state.translator()`.
- `ruff check .` clean after every task. No module-scope `shiny_deckgl` import (existing guard).
- Key syntax: dotted, segments `[a-z0-9_]+` except a trailing data-key segment reproduced verbatim (`forcing.region.LT-coastal`, `params.species.fucus_vesiculosus.calibration.LT-coastal.note`).

## Review Focus

1. **A truthy empty `Message` where an empty string was tested.** `SiteContext.source_note` becomes `Message | None`; `results.forcing_for`, the banner and the report tested `if context.source_note:`. Task 4 changes them to `is not None` and adds a test that a context without a note still assesses on the chosen source.
2. **A key present in English but never rendered because a renderer bypassed `tr`.** The pseudo-locale leak test (Task 8) renders every pure renderer under `xx` and rejects any non-marker text node, including `title`, `alt` and `placeholder` attributes.
3. **`str.format` on a catalogue value containing literal braces.** A translator writing `{` in prose would raise `KeyError` at render. Task 1's `Catalogue.render` reports the key and language in the exception, and Task 8's hygiene test asserts every `{…}` in every value is a known placeholder name.
4. **`?lang=xx` for a language whose catalogue is missing or draft.** `language_for` must fall to English, not raise; Task 5 tests garbage, an unknown code, a valid-but-unenabled code and a mixed-case code.
5. **JSON export no longer `json.dumps`-able.** `Message` inside `asdict()` output would serialise as a nested dict of `{"key", "params"}` without text, or fail on a nested `Message` in `params`. Task 4 rewrites `to_dict(render=)` by hand and tests `json.dumps(assessment.to_dict())` round-trips with `"text"` present on every message.

---

### Task 1: `seagarden_dst/i18n.py` — `Message`, `Catalogue`, and the full English core catalogue

**Files:**
- Create: `src/seagarden_dst/i18n.py`
- Create: `src/seagarden_dst/locales/en.yaml`
- Modify: `pyproject.toml:112-116` (package-data), `tests/test_packaging.py` (one test)
- Test: `tests/test_i18n.py` (create)

**Interfaces:**
- Produces:
  - `LANGUAGES = ("en", "de", "pl", "da", "lt", "sv")`, `DEFAULT_LANGUAGE = "en"`, `CORE_LOCALES: Path`.
  - `Message(key: str, params: Mapping[str, object] = {})` frozen dataclass; `str(m)` English; `m.to_dict(render=str) -> dict`; `Message.literal(text) -> Message` (key `"literal"`); `Message.join(*parts, sep=" ") -> Message` (key `"_join"`).
  - `msg(key, **params) -> Message` convenience constructor.
  - `Catalogue.load(language, *roots, fallback=None) -> Catalogue`; attributes `language, status, translated_by, reviewed_by, reviewed_on, messages`; `lookup(key) -> str`; `render(message, literal_index=None) -> str`; `keys() -> frozenset[str]`.
  - `core_catalogue(language) -> Catalogue` (cached; English fallback attached for non-English).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_i18n.py
"""The Message value and the catalogue (spec I§4). Core only; no Shiny."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from seagarden_dst.i18n import (
    CORE_LOCALES,
    DEFAULT_LANGUAGE,
    LANGUAGES,
    Catalogue,
    Message,
    core_catalogue,
    msg,
)


def test_str_of_a_message_is_its_english_text():
    assert str(msg("calibration.tier.A.label")) == "Locally calibrated"


def test_params_are_interpolated_and_nested_messages_render_in_place():
    inner = msg("suitability.class.legal")
    outer = msg("suitability.explain.binding", name=inner, reason="because")
    assert str(outer) == "Legal permissibility: because"


def test_a_literal_renders_as_its_own_text_in_every_language():
    lit = Message.literal("Raft")
    assert lit.key == "literal"
    assert str(lit) == "Raft"
    assert core_catalogue("de").render(lit) == "Raft"


def test_join_renders_its_parts_separated():
    joined = Message.join(msg("suitability.explain.none"), Message.literal("Also this."))
    assert str(joined) == "No assessment performed. Also this."
    assert Message.join().key == "_join" and str(Message.join()) == ""


def test_equality_is_structural():
    assert msg("a.b", x=1) == msg("a.b", x=1)
    assert msg("a.b", x=1) != msg("a.b", x=2)


def test_to_dict_carries_key_params_and_rendered_text():
    m = msg("suitability.explain.binding", name=msg("suitability.class.legal"), reason="r")
    d = m.to_dict()
    assert d == {
        "key": "suitability.explain.binding",
        "params": {"name": "Legal permissibility", "reason": "r"},
        "text": "Legal permissibility: r",
    }
    json.dumps(d)  # must be serialisable as-is
    upper = m.to_dict(render=lambda message: str(message).upper())
    assert upper["text"] == "LEGAL PERMISSIBILITY: R"


def test_a_missing_english_key_is_a_defect_named_in_the_error():
    with pytest.raises(KeyError, match="no.such.key"):
        str(msg("no.such.key"))


def test_a_missing_key_in_another_language_falls_back_to_english(tmp_path):
    (tmp_path / "en.yaml").write_text(
        "language: en\nstatus: reference\nmessages:\n  a.b: 'hello {x}'\n  a.c: 'only english'\n",
        encoding="utf-8",
    )
    (tmp_path / "xx.yaml").write_text(
        "language: xx\nstatus: machine-draft\ntranslated_by: test\nmessages:\n  a.b: 'hallo {x}'\n",
        encoding="utf-8",
    )
    en = Catalogue.load("en", tmp_path)
    xx = Catalogue.load("xx", tmp_path, fallback=en)
    assert xx.render(msg("a.b", x=1)) == "hallo 1"
    assert xx.render(msg("a.c")) == "only english"
    assert xx.status == "machine-draft" and xx.reviewed_by is None


def test_a_reviewed_catalogue_must_name_its_reviewer(tmp_path):
    (tmp_path / "xx.yaml").write_text(
        "language: xx\nstatus: reviewed\nmessages:\n  a.b: x\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="reviewed_by"):
        Catalogue.load("xx", tmp_path)


def test_a_brace_in_a_value_that_is_not_a_param_names_key_and_language(tmp_path):
    (tmp_path / "en.yaml").write_text(
        "language: en\nstatus: reference\nmessages:\n  a.b: 'oops {typo}'\n", encoding="utf-8"
    )
    with pytest.raises(KeyError, match=r"a\.b.*en.*typo"):
        Catalogue.load("en", tmp_path).render(msg("a.b"))


def test_the_english_core_catalogue_is_the_reference():
    en = core_catalogue(DEFAULT_LANGUAGE)
    assert en.status == "reference"
    assert (CORE_LOCALES / "en.yaml").is_file()
    assert "calibration.tier.D.presentation" in en.keys()


def test_languages_are_the_six_the_spec_names():
    assert LANGUAGES == ("en", "de", "pl", "da", "lt", "sv")


def test_a_non_english_core_catalogue_without_a_file_is_english_with_that_language_code():
    """Package I-b adds the files. Until then `core_catalogue("de")` must not raise: the
    app may be asked for German by a browser header before any German exists."""
    de = core_catalogue("de")
    assert de.language == "de"
    assert de.render(msg("calibration.tier.A.label")) == "Locally calibrated"


def test_every_core_yaml_parses_with_the_required_header():
    for path in sorted(CORE_LOCALES.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert data["language"] == path.stem
        assert data["status"] in {"reference", "machine-draft", "reviewed"}
        assert isinstance(data["messages"], dict) and data["messages"]
```

- [ ] **Step 2: Run to verify failure**

Run: `MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest tests/test_i18n.py -q`
Expected: `ModuleNotFoundError: No module named 'seagarden_dst.i18n'`.

- [ ] **Step 3: Write the module**

```python
# src/seagarden_dst/i18n.py
"""Messages and catalogues - package I (design I§4).

The core produces prose a user reads: a constraint's reason, a caveat, a tier label. It
must stay usable from a notebook and know nothing about the app, so it cannot ask a
session which language it wants. Instead every prose site returns a `Message`: a stable
key plus display-ready parameters. `str(message)` is English, from the reference
catalogue packaged beside this file, so a notebook reads what it always read. The app
renders the same message in another language by key.

This module imports nothing else from the package. `calibration`, `forcing`, `contracts`
and the rest import it, so an import from any of them here would be a cycle.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

LANGUAGES: tuple[str, ...] = ("en", "de", "pl", "da", "lt", "sv")
DEFAULT_LANGUAGE = "en"
CORE_LOCALES = Path(__file__).resolve().parent / "locales"

LITERAL_KEY = "literal"
JOIN_KEY = "_join"
_STATUSES = ("reference", "machine-draft", "reviewed")
_STATUS_RANK = {"machine-draft": 0, "reviewed": 1, "reference": 2}
_PLACEHOLDER = re.compile(r"\{([^{}]*)\}")


@dataclass(frozen=True)
class Message:
    """A sentence the core wants said, not yet said in any language.

    `params` are display-ready: a number is formatted by the caller before it gets
    here, so a catalogue value never carries a format spec a translator could break.
    A parameter may itself be a `Message`; it renders in the same language.
    Equality is structural. Not hashable in practice (a dict field); nothing needs it.
    """

    key: str
    params: Mapping[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return core_catalogue(DEFAULT_LANGUAGE).render(self)

    def to_dict(self, render: Callable[[Message], str] = str) -> dict:
        """`{"key", "params", "text"}` - stable structure, human text via `render`.

        A `join`'s `parts` tuple is rendered element by element, so the export is plain
        JSON all the way down.
        """

        def plain(value: Any) -> Any:
            if isinstance(value, Message):
                return render(value)
            if isinstance(value, (tuple, list)):
                return [plain(v) for v in value]
            return value

        return {
            "key": self.key,
            "params": {k: plain(v) for k, v in self.params.items()},
            "text": render(self),
        }

    @classmethod
    def literal(cls, text: str) -> Message:
        """Prose the core did not author (a YAML note, an engine's own message).

        Renders as itself in every language unless the renderer's literal index knows a
        translation of that exact text (the app's `Translator` builds one from the
        params sidecar). Allowed only at the call sites tests/test_i18n_guards.py lists.
        """
        return cls(LITERAL_KEY, {"text": text})

    @classmethod
    def join(cls, *parts: Message, sep: str = " ") -> Message:
        """Several messages as one, for notes composed of optional sentences."""
        return cls(JOIN_KEY, {"parts": tuple(parts), "sep": sep})


def msg(key: str, **params: Any) -> Message:
    return Message(key, params)


@dataclass(frozen=True)
class Catalogue:
    """One language's key -> template mapping, with an optional fallback catalogue."""

    language: str
    status: str
    messages: Mapping[str, str]
    translated_by: str | None = None
    reviewed_by: str | None = None
    reviewed_on: date | None = None
    fallback: Catalogue | None = None

    @classmethod
    def load(cls, language: str, *roots: Path, fallback: Catalogue | None = None) -> Catalogue:
        """Merge `<root>/<language>.yaml` over the given roots.

        A root without a file for this language contributes nothing. With no file at
        all the catalogue is empty and answers through `fallback` - which is how a
        language the app was asked for but nobody has translated yet renders English.
        """
        messages: dict[str, str] = {}
        header: dict[str, Any] = {}
        statuses: list[str] = []
        for root in roots:
            path = Path(root) / f"{language}.yaml"
            if not path.is_file():
                continue
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if data.get("language") != language:
                raise ValueError(f"{path}: header says language={data.get('language')!r}")
            status = data.get("status")
            if status not in _STATUSES:
                raise ValueError(f"{path}: status must be one of {_STATUSES}, got {status!r}")
            if status == "reviewed" and not (data.get("reviewed_by") and data.get("reviewed_on")):
                raise ValueError(f"{path}: status 'reviewed' needs reviewed_by and reviewed_on")
            statuses.append(status)
            for key in ("translated_by", "reviewed_by", "reviewed_on"):
                if data.get(key) is not None:
                    header.setdefault(key, data.get(key))
            for key, value in (data.get("messages") or {}).items():
                if not isinstance(value, str):
                    raise ValueError(f"{path}: value of {key!r} is not a string")
                messages[key] = value
        reviewed_on = header.get("reviewed_on")
        if isinstance(reviewed_on, str):
            reviewed_on = date.fromisoformat(reviewed_on)
        return cls(
            language=language,
            # The weakest status across the roots is the language's status; no file at
            # all is a draft of nothing, which the enablement gate treats as not enabled.
            status=min(statuses, key=_STATUS_RANK.__getitem__) if statuses else "machine-draft",
            messages=messages,
            translated_by=header.get("translated_by"),
            reviewed_by=header.get("reviewed_by"),
            reviewed_on=reviewed_on,
            fallback=fallback,
        )

    def keys(self) -> frozenset[str]:
        return frozenset(self.messages)

    def lookup(self, key: str) -> str:
        if key in self.messages:
            return self.messages[key]
        if self.fallback is not None:
            return self.fallback.lookup(key)
        raise KeyError(f"no catalogue entry for {key!r} in {self.language!r}")

    def render(self, message: Message, literal_index: Mapping[str, str] | None = None) -> str:
        if message.key == LITERAL_KEY:
            text = str(message.params["text"])
            if literal_index:
                return literal_index.get(_normalise(text), text)
            return text
        if message.key == JOIN_KEY:
            sep = message.params.get("sep", " ")
            return sep.join(self.render(p, literal_index) for p in message.params["parts"])
        template = self.lookup(message.key)
        rendered = {
            k: (self.render(v, literal_index) if isinstance(v, Message) else v)
            for k, v in message.params.items()
        }
        try:
            return template.format(**rendered)
        except (KeyError, IndexError) as exc:
            raise KeyError(
                f"catalogue value for {message.key!r} in {self.language!r} names a "
                f"placeholder the message does not supply: {exc}"
            ) from exc


def _normalise(text: str) -> str:
    return " ".join(text.split())


def placeholders(template: str) -> frozenset[str]:
    """The placeholder names a template uses - the hygiene tests compare these."""
    return frozenset(_PLACEHOLDER.findall(template))


@lru_cache(maxsize=None)
def core_catalogue(language: str) -> Catalogue:
    """The core's own catalogue for `language`, English underneath. Loaded once."""
    english = Catalogue.load(DEFAULT_LANGUAGE, CORE_LOCALES)
    if language == DEFAULT_LANGUAGE:
        return english
    return Catalogue.load(language, CORE_LOCALES, fallback=english)
```

- [ ] **Step 4: Write the English core catalogue, complete**

Every string the core says today, key by key. Values are copied verbatim from the code so English cannot move; where the code interpolated a number, the placeholder takes a pre-formatted string.

```yaml
# src/seagarden_dst/locales/en.yaml
# The reference catalogue for the model core (design I§4.3). Every other language file
# under this directory must carry exactly these keys. Values hold placeholder NAMES only,
# never format specs: the caller formats numbers before the message is built.
language: en
status: reference
messages:
  # --- calibration.py ---------------------------------------------------------
  calibration.tier.A.label: "Locally calibrated"
  calibration.tier.B.label: "Regionally extrapolated"
  calibration.tier.C.label: "Literature prior"
  calibration.tier.D.label: "Contraindicated"
  calibration.tier.A.presentation: "value with confidence interval"
  calibration.tier.B.presentation: "value as a range, calibration region named"
  calibration.tier.C.presentation: "order-of-magnitude band, labelled indicative"
  calibration.tier.D.presentation: "finding shown in place of the number"
  calibration.caveat.D_default: "Contraindicated for this region."
  calibration.caveat.C: "Indicative only - literature prior ({source}), no local validation."
  calibration.caveat.B: "Extrapolated - parameters calibrated on {where} ({source})."
  calibration.caveat.B_where_default: "elsewhere in the Baltic"
  calibration.caveat.A: "Calibrated on {where} pilot data ({source})."
  calibration.quantity.not_applicable: "not applicable - {caveat}"
  # --- params.py --------------------------------------------------------------
  paramset.calibration.none_for_region: "No calibration statement for this region."
  # --- growth.py --------------------------------------------------------------
  growth.contraindication.observed: "cultivation failure has been observed at this salinity"
  growth.contraindication.assumed: "the floor is assumed - no cultivation trial at this salinity is known to us"
  growth.contraindication.note: "Below {floor} psu the model returns a positive yield, but {detail}. Treat as not cultivable here."
  # --- suitability.py ---------------------------------------------------------
  suitability.class.physical: "Physical feasibility"
  suitability.class.environment: "Environmental tolerance"
  suitability.class.growth: "Growth viability"
  suitability.class.legal: "Legal permissibility"
  suitability.physical.depth_outside: "Depth {depth} m is outside the workable window for {method} ({min_depth}-{max_depth} m)."
  suitability.physical.wave_exceeds: "Significant wave height {wave} m exceeds the design limit of {limit} m for {method}."
  suitability.physical.ok: "Depth and exposure workable."
  suitability.physical.unsupported_group: "{method} does not support {group} cultivation."
  suitability.environment.contraindicated_default: "Contraindicated at this site."
  suitability.environment.salinity_scales: "Salinity {salinity} psu scales maximum yield to {factor} of the reference."
  suitability.environment.ok: "Within the species' tolerance range."
  suitability.growth.banded: "Assessed by the banded yield model."
  suitability.growth.contraindicated_default: "Contraindicated."
  suitability.growth.below_floor: "Predicted {per_m2} kg DW/m2 is below the {floor} kg DW/m2 default floor."
  suitability.growth.ok: "Predicted {per_m2} kg DW/m2 over one cycle{tier_note}."
  suitability.growth.tier_note_prior: " (literature prior)"
  suitability.growth.tier_note_none: ""
  suitability.legal.no_record: "No regulatory record loaded for this jurisdiction. The permitting layer is produced in-project by A2.2 (M12) and tested by WP3 A3.1."
  suitability.explain.none: "No assessment performed."
  suitability.explain.no_binding: "No binding constraint identified."
  suitability.explain.binding: "{name}: {reason}"
  suitability.verdict.suitable: "suitable"
  suitability.verdict.marginal: "marginal"
  suitability.verdict.unsuitable: "unsuitable"
  suitability.verdict.unknown: "unknown"
  # --- api.py -----------------------------------------------------------------
  api.caveat.label.nutrient_forcing: "nutrient forcing"
  api.caveat.label.site_conditions: "site conditions"
  api.caveat.label.calibration: "calibration"
  api.caveat.eutropy_not_applied: "EUTROPY forcing not applied: {error}"
  api.caveat.site_conditions: "Nutrient concentrations were overridden by a scenario; other conditions are unchanged."
  api.caveat.calibration: "At least one option rests on literature priors with no local validation. Read the harvest figures as indicative bands."
  api.excluded.no_parameter_file: "No parameter file for this species."
  api.excluded.no_method: "No cultivation method in the catalogue suits this species."
  api.excluded.contraindicated_default: "Contraindicated at this site."
  # --- scenarios.py -----------------------------------------------------------
  scenarios.scale.mini_farm_kit: "mini-farm kit"
  scenarios.scale.community_farm_0_1_ha: "community farm (0.1 ha)"
  scenarios.scale.community_farm_1_ha: "community farm (1 ha)"
  scenarios.scale.small_commercial_5_ha: "small commercial (5 ha)"
  # --- forcing.py -------------------------------------------------------------
  forcing.region.LT-coastal: "Lithuanian coastal waters"
  forcing.region.LT-lagoon: "Curonian Lagoon, Lithuanian side"
  forcing.region.PL-coastal: "Polish coastal waters"
  forcing.region.PL-lagoon: "Szczecin Lagoon"
  forcing.region.DE-coastal: "Mecklenburg-Vorpommern coastal waters"
  forcing.region.DK-belt: "Great Belt"
  forcing.region.EE-coastal: "Estonian coastal waters (OLAMUR pilot)"
  forcing.provenance.sited.label: "Sited"
  forcing.provenance.snapped.label: "Snapped to the nearest modelled cell"
  forcing.provenance.indicative.label: "Indicative of the water body"
  forcing.provenance.sited.presentation: "result for the named site"
  forcing.provenance.snapped.presentation: "result for the nearest modelled cell, with its distance and depth named"
  forcing.provenance.indicative.presentation: "result labelled indicative of the water body, not of a site"
  # --- contracts.py -----------------------------------------------------------
  contracts.source_note.no_position: "no confirmed position; conditions are the sub-region placeholder"
  contracts.confidence.low: "low"
  contracts.confidence.medium: "medium"
  contracts.confidence.high: "high"
  # --- eutropy_adapter.py / bowtie_adapter.py ---------------------------------
  adapters.eutropy.applied: "DIN and DIP from EUTROPY ({run})."
  adapters.eutropy.unlabelled_run: "unlabelled run"
  adapters.eutropy.out_of_domain: "EUTROPY is a Curonian Lagoon box model and this site is {region}, an open-coast sub-region: the lagoon's salinity, residence time and nutrient regime differ materially. Treat the result as scenario reasoning, not as a prediction for this site."
  adapters.eutropy.region_mismatch: "Scenario declared for {declared}, applied to {region}."
  adapters.bowtie.pressure: "Eutrophication pressure from the MARBEFES bow-tie ({label})."
  adapters.bowtie.default_label: "bow-tie scenario"
  adapters.bowtie.out_of_domain: "The published bow-tie is parameterised for the Curonian Lagoon; this site is {region}. Read it as pressure context for the decision, not as a risk estimate for this water body."
  adapters.bowtie.beside: "Reported beside the ranking and never folded into it: a yield weighted by a risk probability is neither a yield nor a risk."
  adapters.bowtie.framing_high: "P(top event High) = {p}. At this pressure, removal by farming is mitigation of an active problem, and the case for scale is stronger."
  adapters.bowtie.framing_low: "P(top event High) = {p}. At this pressure, removal by farming is maintenance rather than mitigation; the ecological case rests less on nutrient figures and more on habitat and community outcomes."
```

- [ ] **Step 5: Ship the catalogue in the wheel**

`pyproject.toml` `[tool.setuptools.package-data]` becomes:

```toml
[tool.setuptools.package-data]
# Two levels: params/*.yaml and params/{species,regulatory,i18n}/*.yaml. tests/test_packaging.py
# asserts these globs still cover the whole tree, so a third level cannot be added and
# silently dropped from the wheel while every checkout keeps working.
"seagarden_dst.paramdata" = ["*.yaml", "*/*.yaml"]
# The core's message catalogues (package I). str(Message) needs en.yaml in a core-only install.
"seagarden_dst" = ["locales/*.yaml"]
```

Append to `tests/test_packaging.py`:

```python
def test_every_core_locale_file_is_covered_by_a_package_data_glob():
    """`str(Message)` reads locales/en.yaml; a wheel without it cannot print a caveat."""
    import fnmatch

    globs = _pyproject()["tool"]["setuptools"]["package-data"]["seagarden_dst"]
    locales = REPO / "src" / "seagarden_dst" / "locales"
    files = sorted(locales.glob("*.yaml"))
    assert files, "no core catalogue committed"
    for path in files:
        rel = path.relative_to(locales.parent).as_posix()
        assert any(fnmatch.fnmatch(rel, g) for g in globs), f"{rel} not shipped"
```

- [ ] **Step 6: Run, then commit**

Run: `MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest tests/test_i18n.py tests/test_packaging.py -q && micromamba run -n shiny ruff check .`
Expected: all pass.

```bash
git add src/seagarden_dst/i18n.py src/seagarden_dst/locales/en.yaml pyproject.toml tests/test_i18n.py tests/test_packaging.py
git commit -m "feat(core): Message and Catalogue, with the English reference catalogue (I-a)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: Calibration, params and growth speak in `Message`s

**Files:**
- Modify: `src/seagarden_dst/calibration.py:20-104`
- Modify: `src/seagarden_dst/params.py:341-346`
- Modify: `src/seagarden_dst/growth.py:254-269`
- Modify: `tests/test_growth.py:124`, `tests/test_tier_d_enforcement.py:103,116`
- Test: `tests/test_i18n_core.py` (create)

**Interfaces:**
- Consumes: `Message`, `msg`, `core_catalogue` from Task 1.
- Produces: `Tier.label -> Message`, `Tier.presentation -> Message`; `Calibration.note: str | Message | None`; `Calibration.caveat() -> Message`; `Quantity.__str__` text unchanged.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_i18n_core.py
"""Every core prose site returns a Message whose English is what it said before (I§5.1)."""

from __future__ import annotations

import dataclasses

from seagarden_dst import PLACEHOLDER_SITES, Tier, default_parameters
from seagarden_dst.calibration import Calibration, Quantity
from seagarden_dst.growth import contraindication
from seagarden_dst.i18n import Message, core_catalogue


def test_tier_label_and_presentation_are_messages_with_the_old_english():
    assert isinstance(Tier.C.label, Message)
    assert str(Tier.C.label) == "Literature prior"
    assert str(Tier.D.presentation) == "finding shown in place of the number"


def test_calibration_caveats_render_as_before():
    c = Calibration(tier=Tier.C, region="LT-coastal", source="OLAMUR D3.2")
    assert str(c.caveat()) == (
        "Indicative only - literature prior (OLAMUR D3.2), no local validation."
    )
    b = Calibration(tier=Tier.B, region="LT-coastal", source="S", calibrated_on="Tagalaht")
    assert str(b.caveat()) == "Extrapolated - parameters calibrated on Tagalaht (S)."
    b2 = Calibration(tier=Tier.B, region="LT-coastal", source="S")
    assert str(b2.caveat()) == "Extrapolated - parameters calibrated on elsewhere in the Baltic (S)."
    a = Calibration(tier=Tier.A, region="LT-coastal", source="S")
    assert str(a.caveat()) == "Calibrated on LT-coastal pilot data (S)."
    d = Calibration(tier=Tier.D, region="x", source="S")
    assert str(d.caveat()) == "Contraindicated for this region."


def test_a_yaml_note_becomes_a_literal_and_survives_untranslated():
    d = Calibration(tier=Tier.D, region="x", source="S", note="Fails below 16 psu.")
    caveat = d.caveat()
    assert caveat.key == "literal" and str(caveat) == "Fails below 16 psu."
    assert core_catalogue("de").render(caveat) == "Fails below 16 psu."


def test_quantity_str_is_unchanged():
    c = Calibration(tier=Tier.C, region="r", source="S")
    assert str(Quantity(3.0, "kg DW", c)) == "3 kg DW [C]"
    assert str(Quantity(3.0, "kg DW", c, low=1.0, high=9.0)) == "1-9 kg DW [C]"
    d = Calibration(tier=Tier.D, region="r", source="S", note="no")
    assert str(Quantity(0.0, "kg DW", d)) == "not applicable - no"


def test_contraindication_note_is_a_message_saying_what_it_said():
    kelp = default_parameters().species["saccharina_latissima"]
    site = dataclasses.replace(PLACEHOLDER_SITES["LT-lagoon"], salinity_psu=2.0)
    calibration = contraindication(kelp, site)
    assert calibration is not None and isinstance(calibration.note, Message)
    text = str(calibration.note)
    assert text.startswith("Below ") and text.endswith("Treat as not cultivable here.")
    assert "observed" in text or "assumed" in text


def test_the_default_calibration_statement_is_a_message():
    ulva = default_parameters().species["ulva"]
    fallback = ulva.calibration_for("nowhere")
    assert str(fallback.note) == "No calibration statement for this region."
```

- [ ] **Step 2: Run to verify failure**

Run: `MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest tests/test_i18n_core.py -q`
Expected: `AssertionError` on `isinstance(Tier.C.label, Message)`.

- [ ] **Step 3: Convert `calibration.py`**

Add `from .i18n import Message, msg` after the `enum` import. Replace the two properties (lines 28–45):

```python
    @property
    def label(self) -> Message:
        return msg(f"calibration.tier.{self.value}.label")

    @property
    def presentation(self) -> Message:
        """How a value at this tier must be rendered (specification section 7.4)."""
        return msg(f"calibration.tier.{self.value}.presentation")
```

Field (line 64): `note: str | Message | None = None`; docstring line 57: `note: shown to the user verbatim - a str from a parameter file, or a Message the code composed. For tier D this replaces the number.` Replace `caveat()` (lines 71–80):

```python
    def caveat(self) -> Message:
        """One line for display beside the value."""
        if self.tier is Tier.D:
            if self.note is None:
                return msg("calibration.caveat.D_default")
            return self.note if isinstance(self.note, Message) else Message.literal(self.note)
        if self.tier is Tier.C:
            return msg("calibration.caveat.C", source=self.source)
        if self.tier is Tier.B:
            where = self.calibrated_on or msg("calibration.caveat.B_where_default")
            return msg("calibration.caveat.B", where=where, source=self.source)
        return msg(
            "calibration.caveat.A", where=self.calibrated_on or self.region, source=self.source
        )
```

`Quantity.__str__` line 101:
`return str(msg("calibration.quantity.not_applicable", caveat=self.calibration.caveat()))`.

- [ ] **Step 4: Convert `params.py` and `growth.py`**

`params.py:341–346` (the fallback in `calibration_for`), with `from .i18n import msg` imported:

```python
        return Calibration(
            tier=Tier.C,
            region=region,
            source="unspecified",
            note=msg("paramset.calibration.none_for_region"),
        )
```

`growth.py:254–269`, with `from .i18n import msg` imported:

```python
            detail = msg(
                "growth.contraindication.observed"
                if floor_basis == "observed"
                else "growth.contraindication.assumed"
            )
            return Calibration(
                tier=Tier.D,
                region=site.region,
                source=calibration.source,
                note=msg("growth.contraindication.note", floor=f"{floor_psu:g}", detail=detail),
            )
```

- [ ] **Step 5: Wrap the tests that lower-cased a note**

`tests/test_growth.py:124`: `assert "not shown" in str(harvest.calibration.note or "").lower()`.
`tests/test_tier_d_enforcement.py:103`: `note = str(contraindication(chorda, lagoon).note or "").lower()`; `:116`: `assert "observed" in str(contraindication(kelp, de_coastal).note or "").lower()`.

- [ ] **Step 6: Run the suite and commit**

Run: `MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest -q && micromamba run -n shiny ruff check .`
Expected: all pass; both goldens untouched.

```bash
git add src/seagarden_dst/calibration.py src/seagarden_dst/params.py src/seagarden_dst/growth.py tests/
git commit -m "feat(core): tier labels, caveats and contraindication notes are Messages (I-a)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: Suitability, the API, scales and the adapters

**Files:**
- Modify: `src/seagarden_dst/suitability.py:31-263`
- Modify: `src/seagarden_dst/api.py:33-39`, `:94-108`, `:176-251`
- Modify: `src/seagarden_dst/contracts.py` (field types only)
- Modify: `src/seagarden_dst/scenarios.py` (`SCALE_LABELS`, `compare`)
- Modify: `src/seagarden_dst/eutropy_adapter.py:86-107`, `src/seagarden_dst/bowtie_adapter.py:86-119`
- Modify: `tests/test_api.py:45,57`, `tests/test_adapters.py:76,109,120,129`, `tests/test_assess_with_artifact.py:112`, `tests/test_gridded.py:402-404`, `tests/test_method_selection.py:67`, `tests/test_suitability.py:26,37,55,65`, `tests/test_golden_snapshot.py:90,100`
- Test: `tests/test_i18n_core.py` (extend)

**Interfaces:**
- Produces: `Verdict.label -> Message`; `Constraint.name: Message`, `.reason: Message`; `Suitability.explain() -> Message`; `SpeciesOption.binding_constraint: Message`, `.constraints: list[tuple[Message, str, Message]]`; `SiteAssessment.caveats: dict[str, Message]`, `.excluded: dict[str, Message]`, `.pressure_note: Message | None`; `CAVEAT_LABELS: dict[str, Message]`; `SCALE_LABELS: dict[str, Message]`; `removal_framing(...) -> Message | None`; `apply_nutrient_scenario -> tuple[SiteContext, Message]`; `eutrophication_pressure -> tuple[dict, Message]`.

- [ ] **Step 1: Extend the failing tests** (append to `tests/test_i18n_core.py`)

```python
def test_constraints_and_explanations_are_messages_saying_what_they_said():
    from seagarden_dst import SiteContext, assess_site

    result = assess_site(SiteContext.from_region("LT-coastal"))
    option = result.ranked[0]
    assert isinstance(option.binding_constraint, Message)
    for name, verdict, reason in option.constraints:
        assert isinstance(name, Message) and isinstance(reason, Message)
        assert verdict in {"suitable", "marginal", "unsuitable", "unknown"}
    names = {str(c[0]) for c in option.constraints}
    assert names == {
        "Physical feasibility", "Environmental tolerance", "Growth viability",
        "Legal permissibility",
    }
    legal = next(c for c in option.constraints if str(c[0]) == "Legal permissibility")
    assert str(legal[2]).startswith("No regulatory record loaded")
    assert str(option.binding_constraint).startswith("Legal permissibility: ")


def test_caveats_excluded_and_pressure_note_are_messages():
    from seagarden_dst import CAVEAT_LABELS, SiteContext, assess_site

    result = assess_site(
        SiteContext.from_region("LT-coastal"),
        eutropy={"nonsense": True},
        bowtie={"Catastrophe": 1.0},
    )
    assert all(isinstance(v, Message) for v in result.caveats.values())
    assert all(isinstance(v, Message) for v in result.excluded.values())
    assert isinstance(result.pressure_note, Message)
    assert str(result.caveats["nutrient_forcing"]).startswith("EUTROPY forcing not applied: ")
    assert str(CAVEAT_LABELS["nutrient_forcing"]) == "nutrient forcing"
    assert "failed" in str(result.excluded["saccharina_latissima"]).lower()


def test_pressure_note_without_a_bowtie_is_none_not_an_empty_message():
    from seagarden_dst import SiteContext, assess_site

    assert assess_site(SiteContext.from_region("LT-coastal")).pressure_note is None


def test_scale_labels_and_verdict_labels_are_messages():
    from seagarden_dst import SCALE_LABELS, Verdict

    assert str(SCALE_LABELS["community_farm_0_1_ha"]) == "community farm (0.1 ha)"
    assert isinstance(Verdict.SUITABLE.label, Message)
    assert str(Verdict.UNSUITABLE.label) == "unsuitable"


def test_the_adapter_notes_compose_from_keyed_sentences():
    from seagarden_dst import SiteContext, assess_site

    bowtie = {"Low": 0.2, "Moderate": 0.3, "High": 0.5}
    lagoon = assess_site(SiteContext.from_region("LT-lagoon"), bowtie=bowtie)
    note = str(lagoon.pressure_note)
    assert note.startswith("Eutrophication pressure from the MARBEFES bow-tie (bow-tie scenario).")
    assert note.endswith("neither a yield nor a risk.")
    assert "parameterised for the Curonian Lagoon" not in note  # in domain
    coast = assess_site(SiteContext.from_region("LT-coastal"), bowtie=bowtie)
    assert "this site is LT-coastal" in str(coast.pressure_note)
```

- [ ] **Step 2: Run to verify failure**

Run: `MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest tests/test_i18n_core.py -q`
Expected: the five new tests FAIL (`isinstance(..., Message)` false, `pressure_note == ""`).

- [ ] **Step 3: Convert `suitability.py`**

Import `from .i18n import Message, msg`. `Verdict.label` (added by I-0) becomes:

```python
    @property
    def label(self) -> Message:
        """What a user reads. The value is the identifier and the CSS class."""
        return msg(f"suitability.verdict.{self.value}")
```

`Constraint`: `name: Message`, `reason: Message`. `Suitability.explain()`:

```python
    def explain(self) -> Message:
        binding = self.binding_constraint
        if binding is None:
            return msg("suitability.explain.none")
        if self.verdict is Verdict.SUITABLE:
            return msg("suitability.explain.no_binding")
        return msg("suitability.explain.binding", name=binding.name, reason=binding.reason)
```

Module constants after `Constraint`:

```python
PHYSICAL = msg("suitability.class.physical")
ENVIRONMENT = msg("suitability.class.environment")
GROWTH = msg("suitability.class.growth")
LEGAL = msg("suitability.class.legal")
```

`assess_physical`:

```python
def assess_physical(site: SiteConditions, method: MethodParams) -> Constraint:
    method_name = Message.literal(method.name)  # literal: YAML data, translated by the sidecar
    if not (method.min_depth_m <= site.depth_m <= method.max_depth_m):
        return Constraint(
            PHYSICAL,
            Verdict.UNSUITABLE,
            msg(
                "suitability.physical.depth_outside",
                depth=f"{site.depth_m:g}", method=method_name,
                min_depth=f"{method.min_depth_m:g}", max_depth=f"{method.max_depth_m:g}",
            ),
        )
    if site.significant_wave_m > method.max_significant_wave_m:
        return Constraint(
            PHYSICAL,
            Verdict.MARGINAL,
            msg(
                "suitability.physical.wave_exceeds",
                wave=f"{site.significant_wave_m:g}",
                limit=f"{method.max_significant_wave_m:g}", method=method_name,
            ),
        )
    return Constraint(PHYSICAL, Verdict.SUITABLE, msg("suitability.physical.ok"))
```

`assess_environment`: contraindicated → `Constraint(ENVIRONMENT, Verdict.UNSUITABLE, contra.caveat())` (every contraindication carries a note, so `caveat()` yields it, as `contra.note or ...` did); salinity → `msg("suitability.environment.salinity_scales", salinity=f"{site.salinity_psu:g}", factor=f"{factor:.0%}")`; ok → `msg("suitability.environment.ok")`.

`assess_growth`: banded → `msg("suitability.growth.banded")`; not reportable → `Constraint(GROWTH, Verdict.UNSUITABLE, harvest.calibration.caveat())`; below floor → `msg("suitability.growth.below_floor", per_m2=f"{per_m2:.2f}", floor=f"{floor_kg_dw_per_m2:g}")`; ok →

```python
    tier_note = msg(
        "suitability.growth.tier_note_prior"
        if harvest.calibration.tier is Tier.C
        else "suitability.growth.tier_note_none"
    )
    return Constraint(
        GROWTH, Verdict.SUITABLE,
        msg("suitability.growth.ok", per_m2=f"{per_m2:.2f}", tier_note=tier_note),
    )
```

`assess_legal`: `Constraint(LEGAL, Verdict.UNKNOWN, msg("suitability.legal.no_record"))`. In `assess`, the unsupported-group constraint: `msg("suitability.physical.unsupported_group", method=Message.literal(method.name), group=Message.literal(species.group))` — the group is a literal too, so the sidecar's `params.group.<g>` entry translates it mid-sentence (I§5.1) through the text index; in English it renders as itself.

Then `grep -rn contraindicated_default src`: the three `*_default` keys for "Contraindicated." / "Contraindicated at this site." are no longer referenced; **delete them from `en.yaml`** (`suitability.environment.contraindicated_default`, `suitability.growth.contraindicated_default`, `api.excluded.contraindicated_default`). Task 8's hygiene test fails on an unused key otherwise.

- [ ] **Step 4: Convert `api.py` and the contract types**

`api.py` imports `from .i18n import Message, msg`. `CAVEAT_LABELS`:

```python
CAVEAT_LABELS: dict[str, Message] = {
    slug: msg(f"api.caveat.label.{slug}")
    for slug in ("nutrient_forcing", "site_conditions", "calibration")
}
```

In `assess_site`: `caveats: dict[str, Message] = {}`; on `EutropyUnavailable`: `caveats["nutrient_forcing"] = msg("api.caveat.eutropy_not_applied", error=str(exc))`; `excluded: dict[str, Message] = {}`; `excluded[key] = msg("api.excluded.no_parameter_file")`; `excluded[key] = msg("api.excluded.no_method")`; `excluded[key] = contra.caveat()`; on `ForcingUnavailable`: `excluded[key] = Message.literal(str(exc))  # literal: the reader's own message`; `pressure_note: Message | None = None`; on `BowtieUnavailable`: `pressure_note = Message.literal(str(exc))  # literal: the engine's own message`; `caveats.setdefault("site_conditions", msg("api.caveat.site_conditions"))`; `caveats.setdefault("calibration", msg("api.caveat.calibration"))`.

`contracts.py`: import `from .i18n import Message`; `SpeciesOption.binding_constraint: Message`; `constraints: list[tuple[Message, str, Message]]`; `SiteAssessment.excluded: dict[str, Message]`, `caveats: dict[str, Message]`, `pressure_note: Message | None = None`. Leave `to_dict` alone here; Task 4 rewrites it.

- [ ] **Step 5: Convert `scenarios.py` and the adapters**

`scenarios.py`: import `Message, msg`; `SCALE_LABELS: dict[str, Message] = {key: msg(f"scenarios.scale.{key}") for key in SCALES}`. In `compare`: `"Binding constraint": str(result.suitability.explain()),` and `"Calibration": str(result.harvest.calibration.tier.label),`. `default_scenarios`' f-string already stringifies.

`eutropy_adapter.py:93–107`, importing `Message, msg`:

```python
    # `run` stays a plain str: it is mostly data ("box 19", "fN=0.5, fP=0.5") around one
    # keyed word, and a Message inside a str.join would lose its key anyway.
    run = "; ".join(bits) or str(msg("adapters.eutropy.unlabelled_run"))

    scenario_region = scenario.get("region")
    parts = [msg("adapters.eutropy.applied", run=run)]
    if context.region not in LAGOON_REGIONS:
        parts.append(msg("adapters.eutropy.out_of_domain", region=context.region))
    elif scenario_region and scenario_region != context.region:
        parts.append(
            msg("adapters.eutropy.region_mismatch", declared=scenario_region, region=context.region)
        )
    return forced, Message.join(*parts)
```

Return annotation `-> tuple[SiteContext, Message]`.

`bowtie_adapter.py:86–98`, importing `Message, msg`:

```python
    label = inference.get("label") or msg("adapters.bowtie.default_label")
    parts = [msg("adapters.bowtie.pressure", label=label)]
    if context.region not in LAGOON_REGIONS:
        parts.append(msg("adapters.bowtie.out_of_domain", region=context.region))
    parts.append(msg("adapters.bowtie.beside"))
    return values, Message.join(*parts)
```

`removal_framing(...) -> Message | None`: `return None` when `pressure` is empty; otherwise `msg("adapters.bowtie.framing_high", p=f"{high:.2f}")` or `msg("adapters.bowtie.framing_low", p=f"{high:.2f}")`.

- [ ] **Step 6: Update the tests that read prose as `str`**

- `tests/test_api.py:45`: `str(result.excluded["saccharina_latissima"]).lower()`; `:57`: `str(result.caveats["calibration"]).lower()`.
- `tests/test_adapters.py:76`: `in str(degraded.caveats["nutrient_forcing"])`; `:109`: `in str(note)`; `:120`: `in str(with_pressure.pressure_note)`; `:129`: `in str(result.pressure_note)`. Any other `in note` in that file: wrap in `str()`.
- `tests/test_assess_with_artifact.py:112`: `in str(result.excluded["fucus_wrapped"])`.
- `tests/test_gridded.py:402`: `for why in map(str, assessment.excluded.values())`; `:404`: `in str(assessment.excluded["saccharina_latissima"])`.
- `tests/test_method_selection.py:67`: `in str(o.binding_constraint)`.
- `tests/test_suitability.py:26,37,55,65`: `in str(result.explain())`.
- `tests/test_golden_snapshot.py:90`: `"excluded": {k: str(v) for k, v in sorted(result.excluded.items())},`; `:100`: `"constraints": [[str(n), v, str(r)] for n, v, r in option.constraints],`.

- [ ] **Step 7: Run the suite and commit**

Run: `MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest -q && micromamba run -n shiny ruff check . && git status --short tests/golden`
Expected: all pass; the last command prints nothing (both goldens untouched).

```bash
git add src/seagarden_dst tests
git commit -m "feat(core): constraints, caveats, exclusions, scales and adapter notes are Messages (I-a)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: Regions, provenance, the source note, and `to_dict(render=)`

**Files:**
- Modify: `src/seagarden_dst/forcing.py:27-35`, `:130-153`
- Modify: `src/seagarden_dst/contracts.py:33`, `:67`, `:146-152`, `:183-199`
- Modify: `app/modules/results.py:29`, `app/modules/_widgets.py:106-108`, `app/modules/report.py:119-120,135-136`, `app/modules/site.py:78,80-81,124,169,283,295,302` (minimal `str()` / `is not None` so the app keeps running; Task 7 finishes them)
- Modify: `tests/test_forcing_choice.py:84-92`, `tests/test_select_forcing.py:228`, `app/tests/test_app_smoke.py:165,176,184,219,311-312,447-451,477-482`
- Test: `tests/test_i18n_core.py` (extend)

**Interfaces:**
- Produces: `REGIONS: dict[str, Message]`; `SiteProvenance.label -> Message`, `.presentation -> Message`; `SOURCE_NOTE_NO_POSITION: Message`; `SiteContext.source_note: Message | None = None`; `SpeciesOption.to_dict(render=str)`, `SiteAssessment.to_dict(render=str)`, both `json.dumps`-able, every `Message` as `{"key", "params", "text"}`.

- [ ] **Step 1: Extend the failing tests** (append to `tests/test_i18n_core.py`)

```python
def test_regions_and_provenance_are_messages():
    import json

    from seagarden_dst import REGIONS, SiteProvenance

    assert all(isinstance(v, Message) for v in REGIONS.values())
    assert str(REGIONS["DK-belt"]) == "Great Belt"
    assert str(SiteProvenance.SNAPPED.label) == "Snapped to the nearest modelled cell"
    assert str(SiteProvenance.INDICATIVE.presentation) == (
        "result labelled indicative of the water body, not of a site"
    )
    json.dumps({k: v.to_dict() for k, v in REGIONS.items()})


def test_source_note_is_none_until_set_and_a_message_when_set():
    from seagarden_dst import SiteContext
    from seagarden_dst.contracts import SOURCE_NOTE_NO_POSITION

    context = SiteContext.from_region("LT-coastal")
    assert context.source_note is None
    context.source_note = SOURCE_NOTE_NO_POSITION
    assert str(context.source_note) == (
        "no confirmed position; conditions are the sub-region placeholder"
    )


def test_to_dict_is_json_serialisable_with_text_on_every_message():
    import json

    from seagarden_dst import SiteContext, assess_site
    from seagarden_dst.contracts import SOURCE_NOTE_NO_POSITION

    context = SiteContext.from_region("LT-coastal", label="Melnrage")
    context.source_note = SOURCE_NOTE_NO_POSITION
    result = assess_site(context, bowtie={"Low": 0.2, "Moderate": 0.3, "High": 0.5})
    d = result.to_dict()
    json.dumps(d)
    assert d["site"]["source_note"]["key"] == "contracts.source_note.no_position"
    assert d["site"]["source_note"]["text"].startswith("no confirmed position")
    option = d["ranked"][0]
    assert set(option["binding_constraint"]) == {"key", "params", "text"}
    name, verdict, reason = option["constraints"][0]
    assert isinstance(verdict, str) and "text" in name and "text" in reason
    assert d["caveats"]["calibration"]["text"].startswith("At least one option")
    assert d["pressure_note"]["key"] == "_join"
    upper = result.to_dict(render=lambda m: str(m).upper())
    assert upper["caveats"]["calibration"]["text"].startswith("AT LEAST ONE OPTION")


def test_to_dict_without_a_note_or_pressure_writes_null():
    from seagarden_dst import SiteContext, assess_site

    d = assess_site(SiteContext.from_region("LT-coastal")).to_dict()
    assert d["site"]["source_note"] is None and d["pressure_note"] is None
```

- [ ] **Step 2: Run to verify failure**

Run: `MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest tests/test_i18n_core.py -q`
Expected: the four new tests FAIL.

- [ ] **Step 3: Convert `forcing.py`**

Import `from .i18n import Message, msg`. Lines 27–35:

```python
# Sub-regions used for calibration lookup. These are coarse on purpose: they are
# calibration domains, not a spatial index. The key is the identifier; the value is what
# a user reads, so it is a Message (package I) - `str(REGIONS[key])` is the English name.
REGIONS: dict[str, Message] = {
    key: msg(f"forcing.region.{key}")
    for key in (
        "LT-coastal", "LT-lagoon", "PL-coastal", "PL-lagoon", "DE-coastal", "DK-belt",
        "EE-coastal",
    )
}
```

`SiteProvenance.label` → `return msg(f"forcing.provenance.{self.value}.label")`; `.presentation` → `return msg(f"forcing.provenance.{self.value}.presentation")`, both annotated `-> Message`, docstrings kept.

- [ ] **Step 4: Convert `contracts.py`**

Line 33: `SOURCE_NOTE_NO_POSITION = msg("contracts.source_note.no_position")` with `msg` imported. Line 67: `source_note: Message | None = None` and the comment above it: `#: Why this site is on the placeholder while the session runs on the artifact; None otherwise (E§3.5). A Message, never "", so callers test `is not None`.`

Replace `SpeciesOption.to_dict` (146–152):

```python
    def to_dict(self, render: Callable[[Message], str] = str) -> dict:
        """Export. Every Message is `{"key", "params", "text"}` (I§5.1); quantities are
        their English `str()`, as before. Written by hand rather than `asdict`, which
        would recurse into Message and emit it without its text."""
        return {
            "species_key": self.species_key,
            "species_name": self.species_name,
            "method_key": self.method_key,
            "method_name": self.method_name,
            "area_m2": self.area_m2,
            "verdict": self.verdict,
            "binding_constraint": self.binding_constraint.to_dict(render),
            "tier": self.tier.value,
            "harvest": str(self.harvest),
            "nitrogen": None if self.nitrogen is None else str(self.nitrogen),
            "phosphorus": None if self.phosphorus is None else str(self.phosphorus),
            "carbon": None if self.carbon is None else str(self.carbon),
            "constraints": [
                [name.to_dict(render), verdict, reason.to_dict(render)]
                for name, verdict, reason in self.constraints
            ],
        }
```

Replace `SiteAssessment.to_dict` (183–199):

```python
    def to_dict(self, render: Callable[[Message], str] = str) -> dict:
        note = self.context.source_note
        return {
            "site": {
                "region": self.context.region,
                "label": self.context.label,
                "confidence": self.context.confidence,
                "geometry_wkt": self.context.geometry_wkt,
                "from_artifact": self.context.from_artifact,
                "source_note": None if note is None else note.to_dict(render),
            },
            "ranked": [o.to_dict(render) for o in self.ranked],
            "best": None if self.best is None else self.best.to_dict(render),
            "excluded": {k: v.to_dict(render) for k, v in self.excluded.items()},
            "caveats": {k: v.to_dict(render) for k, v in self.caveats.items()},
            "pressure": dict(self.pressure),
            "pressure_note": (
                None if self.pressure_note is None else self.pressure_note.to_dict(render)
            ),
        }
```

Add `from collections.abc import Callable` to the imports; `asdict` is no longer used — drop it from the `dataclasses` import.

- [ ] **Step 5: Keep the app running (minimal; Task 7 replaces these with `tr`)**

- `app/modules/results.py:29`: `return DEFAULT_FORCING if context.source_note is not None else choice.source`.
- `app/modules/_widgets.py:106`: `if context is not None and context.source_note is not None:` and `:107`: `text += f" This site: {context.source_note}."` (f-string stringifies).
- `app/modules/report.py:119`: `if context.source_note is not None:`; `:135`: same.
- `app/modules/site.py:78`: `"name": str(REGIONS.get(region, Message.literal(region))),` — simpler: `"name": str(REGIONS[region]),` since every coordinate's region is in `REGIONS`; `:80-81`: `str(coordinate.provenance.label)`, `str(coordinate.provenance.presentation)`; `:169`: `ui.tags.small(str(provenance.label))`; `:181`: `choices={k: str(v) for k, v in REGIONS.items()}`; `:185`: `' and '.join(str(REGIONS[r]) for r in absent)`; `:283`: `label = (input.label() or "").strip() or str(REGIONS[region])`; `:295`: `f"{REGIONS[region]} has no confirmed position..."` already stringifies inside the f-string; `:302-303`: `str(coordinate.provenance.label).lower()`, `{coordinate.provenance.presentation}` in an f-string is fine.
- `app/modules/report.py:168`: `payload = {} if assessment is None else assessment.to_dict()` unchanged (English until Task 7).

- [ ] **Step 6: Update the tests that compared the note to `""`**

- `tests/test_forcing_choice.py:89`: `assert context.source_note is None`; `:90-92`: `assert str(SOURCE_NOTE_NO_POSITION) == ("no confirmed position; conditions are the sub-region placeholder")`.
- `tests/test_select_forcing.py:228`: `assert context.source_note is None`.
- `app/tests/test_app_smoke.py:165`: `context.source_note is None`; `:176`: `context.source_note is SOURCE_NOTE_NO_POSITION`; `:184`: `context.source_note is None`; `:219`: unchanged (assigns the constant); `:311-312`: `marker["provenance_label"] == str(coordinate.provenance.label)` and `== str(coordinate.provenance.presentation)`; `:447`: `context.source_note = SOURCE_NOTE_NO_POSITION` (import it) — the banner text assertion at 449–451 stays; `:477-479`: `state.context.get().source_note = SOURCE_NOTE_NO_POSITION`; `:482`: `assert site["source_note"]["text"].startswith("no confirmed position")`.

- [ ] **Step 7: Run the suite and commit**

Run: `MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest -q && micromamba run -n shiny ruff check . && git status --short tests/golden`
Expected: all pass; nothing under `tests/golden` modified.

```bash
git add src/seagarden_dst app tests
git commit -m "feat(core): regions, provenance and the source note are Messages; to_dict(render=) (I-a)

The JSON export now writes every message as {key, params, text}. Structure
is stable across languages; text is what the requesting user read.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: `app/i18n.py` — `Translator`, `language_for`, the enablement gate, and the English app catalogue

**Files:**
- Create: `app/i18n.py`
- Create: `app/locales/en.yaml`
- Test: `app/tests/test_i18n_app.py` (create)

**Interfaces:**
- Consumes: `Catalogue`, `Message`, `core_catalogue`, `CORE_LOCALES`, `LANGUAGES`, `DEFAULT_LANGUAGE`, `placeholders` from `seagarden_dst.i18n`; `default_parameters`, `DEFAULT_PARAM_ROOT` from `seagarden_dst.params`; `Quantity`, `for_display` from `seagarden_dst.calibration`.
- Produces:
  - `APP_LOCALES: Path`, `PARAMS_LOCALES: Path` (`params/i18n`), `LANGUAGE_NAMES: dict[str, str]` (endonyms).
  - `Translator.for_language(language) -> Translator` (cached); `Translator.load(language, *, core_root, app_root, params_root) -> Translator` (uncached, for tests); `Translator.pseudo() -> Translator` (every value `⟦key⟧`, language `"xx"`).
  - `tr(key, **params) -> str`; `tr.render(message) -> str`; `tr.quantity(q) -> str`; `tr.species_name(key)`, `tr.method_name(key)`, `tr.method_field(key, field)`, `tr.group_label(group)`, `tr.confidence_label(c)`; `tr.language`, `tr.status`, `tr.is_draft`.
  - `catalogue_status(language, *, core_root, app_root, params_root) -> str | None`.
  - `enabled_languages(env=os.environ, status=catalogue_status) -> tuple[str, ...]`.
  - `language_for(query: str, accept_language: str | None, enabled: Sequence[str]) -> str`.
  - `english() -> Translator` shorthand for `Translator.for_language("en")`.

- [ ] **Step 1: Write the failing tests**

```python
# app/tests/test_i18n_app.py
"""The app-side Translator and the language chooser (spec I§5.2-I§5.4, I§6)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.i18n import (
    LANGUAGE_NAMES,
    Translator,
    catalogue_status,
    enabled_languages,
    language_for,
)
from seagarden_dst import Tier, default_parameters
from seagarden_dst.calibration import Calibration, Quantity
from seagarden_dst.i18n import LANGUAGES, Message, msg


def test_app_keys_and_core_keys_render_through_one_translator():
    tr = Translator.for_language("en")
    assert tr("app.shell.assess") == "Assess"
    assert tr.render(msg("calibration.tier.C.label")) == "Literature prior"
    assert tr.render(Message.literal("Raft")) == "Raft"


def test_species_and_method_names_fall_back_to_the_yaml_english():
    tr = Translator.for_language("en")
    params = default_parameters()
    assert tr.species_name("ulva") == params.species["ulva"].common_name
    assert tr.method_name("raft") == "Raft"
    assert tr.method_field("raft", "anchoring_unit") == "multi-point mooring"
    assert tr.group_label("macroalga") == "macroalga"
    assert tr.confidence_label("low") == "low"


def test_quantity_text_matches_the_core_str():
    tr = Translator.for_language("en")
    c = Calibration(tier=Tier.C, region="r", source="S")
    q = Quantity(3.0, "kg DW", c, low=1.0, high=9.0)
    assert tr.quantity(q) == str(q) == "1-9 kg DW [C]"
    d = Calibration(tier=Tier.D, region="r", source="S", note="no")
    assert tr.quantity(Quantity(0.0, "kg DW", d)) == "not applicable - no"


def test_a_sidecar_translates_yaml_text_and_literals_carrying_it(tmp_path):
    (tmp_path / "params").mkdir()
    (tmp_path / "params" / "xx.yaml").write_text(
        "language: xx\nstatus: machine-draft\ntranslated_by: t\nmessages:\n"
        "  params.methods.raft.name: 'FLOSS'\n"
        "  params.species.ulva.common_name: 'MEERSALAT'\n"
        "  params.group.macroalga: 'MAKROALGE'\n",
        encoding="utf-8",
    )
    tr = Translator.load(
        "xx", core_root=None, app_root=None, params_root=tmp_path / "params"
    )
    assert tr.method_name("raft") == "FLOSS"
    assert tr.species_name("ulva") == "MEERSALAT"
    assert tr.group_label("macroalga") == "MAKROALGE"
    # A literal carrying the English YAML text resolves through the text index.
    inner = msg("suitability.physical.unsupported_group", method=Message.literal("Raft"), group="x")
    assert tr.render(inner) == "FLOSS does not support x cultivation."
    assert tr.render(Message.literal("  Raft ")) == "FLOSS"  # whitespace-normalised


def test_pseudo_translator_marks_every_value():
    xx = Translator.pseudo()
    assert xx.language == "xx"
    assert xx("app.shell.assess") == "⟦app.shell.assess⟧"
    assert xx.render(msg("calibration.tier.C.label")) == "⟦calibration.tier.C.label⟧"
    assert xx.species_name("ulva") == "⟦params.species.ulva.common_name⟧"
    assert xx.render(Message.literal("Raft")) == "⟦params.methods.raft.name⟧"


def test_language_for_prefers_query_then_header_then_english():
    enabled = ("en", "de", "pl")
    assert language_for("?lang=de", None, enabled) == "de"
    assert language_for("?x=1&lang=pl&y=2", "de", enabled) == "pl"
    assert language_for("?lang=DE", None, enabled) == "de"
    assert language_for("", "pl-PL,pl;q=0.9,en;q=0.8", enabled) == "pl"
    assert language_for("", "sv-SE,sv;q=0.9,de;q=0.5", enabled) == "de"
    assert language_for("?lang=sv", "sv", enabled) == "en"  # exists, not enabled
    assert language_for("?lang=zz", "zz", enabled) == "en"
    assert language_for("?lang=", None, enabled) == "en"
    assert language_for("garbage", "garbage;;q=", enabled) == "en"
    assert language_for("", None, ("en",)) == "en"


def test_enabled_languages_is_english_plus_reviewed_unless_drafts_are_shown():
    def status(language: str) -> str | None:
        return {"de": "reviewed", "pl": "machine-draft", "da": None}.get(language)

    assert enabled_languages(env={}, status=status) == ("en", "de")
    assert enabled_languages(env={"SEAGARDEN_SHOW_DRAFT_LANGUAGES": "1"}, status=status) == (
        "en", "de", "pl",
    )
    assert enabled_languages(env={"SEAGARDEN_LANGUAGES": "en,pl,de"}, status=status) == (
        "en", "de",
    )
    assert enabled_languages(
        env={"SEAGARDEN_LANGUAGES": "pl", "SEAGARDEN_SHOW_DRAFT_LANGUAGES": "1"}, status=status
    ) == ("en", "pl")


def test_in_i_a_only_english_is_enabled_on_disk():
    """No non-English catalogue ships in I-a; package I-b adds them."""
    assert enabled_languages(env={}) == ("en",)
    assert catalogue_status("en") == "reference"
    assert catalogue_status("de") is None


def test_language_names_cover_the_six_languages_as_endonyms():
    assert set(LANGUAGE_NAMES) == set(LANGUAGES)
    assert LANGUAGE_NAMES["lt"] == "Lietuvių" and LANGUAGE_NAMES["en"] == "English"
```

- [ ] **Step 2: Run to verify failure**

Run: `MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest app/tests/test_i18n_app.py -q`
Expected: `ModuleNotFoundError: No module named 'app.i18n'`.

- [ ] **Step 3: Write `app/i18n.py`**

```python
# app/i18n.py
"""The app's side of package I: one Translator per language, chosen per request.

The core hands the app `Message`s (design I§4). This module renders them, and the app's
own chrome, in the session's language. Three catalogues per language, prefix-owned
(I§5.4): the core's (`src/seagarden_dst/locales`), the app's (`app/locales`) and the
params sidecar (`params/i18n`), which translates text that lives in the parameter YAML -
species common names, method names, calibration notes - without the core knowing a
sidecar exists. A `Translator` is passed explicitly into every UI builder and read from
`state.translator()` in every server renderer. No context variables (I§5.2).
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import parse_qs

from seagarden_dst.calibration import Quantity
from seagarden_dst.i18n import (
    CORE_LOCALES,
    DEFAULT_LANGUAGE,
    LANGUAGES,
    Catalogue,
    Message,
    core_catalogue,
)
from seagarden_dst.params import DEFAULT_PARAM_ROOT, default_parameters

APP_LOCALES = Path(__file__).resolve().parent / "locales"
PARAMS_LOCALES = DEFAULT_PARAM_ROOT / "i18n"

#: Endonyms for the language menu. Proper nouns, not translated, so not catalogue keys.
LANGUAGE_NAMES: dict[str, str] = {
    "en": "English", "de": "Deutsch", "pl": "Polski", "da": "Dansk", "lt": "Lietuvių",
    "sv": "Svenska",
}

ENV_LANGUAGES = "SEAGARDEN_LANGUAGES"
ENV_SHOW_DRAFTS = "SEAGARDEN_SHOW_DRAFT_LANGUAGES"

_GROUPS = ("macroalga", "shellfish")
_METHOD_FIELDS = ("name", "anchoring_unit", "cultivation_unit")


@lru_cache(maxsize=None)
def params_reference_keys() -> dict[str, str]:
    """Every sidecar key the shipped params imply, with its English text. Cached; treat
    the returned dict as read-only.

    This is the params owner's 'English file' - derived, not written, so a new species
    YAML extends the key set by itself (I§5.4). Test 1 compares each sidecar against it.
    """
    params = default_parameters()
    out: dict[str, str] = {}
    for key, species in params.species.items():
        out[f"params.species.{key}.common_name"] = species.common_name
        for entry in species.calibration:
            if entry.note:
                out[f"params.species.{key}.calibration.{entry.region}.note"] = entry.note
    for key, method in params.methods.items():
        for field in _METHOD_FIELDS:
            out[f"params.methods.{key}.{field}"] = getattr(method, field)
    for group in _GROUPS:
        out[f"params.group.{group}"] = group
    return out


def _normalise(text: str) -> str:
    return " ".join(text.split())


@dataclass(frozen=True)
class Translator:
    language: str
    core: Catalogue
    app: Catalogue
    sidecar: Mapping[str, str]        # params.* keys -> text in this language
    text_index: Mapping[str, str]     # normalised English YAML text -> translation
    status: str                       # weakest of the three catalogues' statuses

    # -- construction -----------------------------------------------------------------

    @classmethod
    def load(
        cls,
        language: str,
        *,
        core_root: Path | None = CORE_LOCALES,
        app_root: Path | None = APP_LOCALES,
        params_root: Path | None = PARAMS_LOCALES,
    ) -> Translator:
        """Uncached. `None` for a root means 'use the packaged one, English only'."""
        english_core = core_catalogue(DEFAULT_LANGUAGE)
        english_app = Catalogue.load(DEFAULT_LANGUAGE, APP_LOCALES)
        if language == DEFAULT_LANGUAGE:
            core, app = english_core, english_app
        else:
            core = Catalogue.load(language, *(r for r in (core_root,) if r), fallback=english_core)
            app = Catalogue.load(language, *(r for r in (app_root,) if r), fallback=english_app)
        sidecar: dict[str, str] = {}
        sidecar_status = "reference" if language == DEFAULT_LANGUAGE else "machine-draft"
        if params_root is not None and language != DEFAULT_LANGUAGE:
            side = Catalogue.load(language, params_root)
            sidecar = dict(side.messages)
            sidecar_status = side.status
        reference = params_reference_keys()
        index = {
            _normalise(reference[key]): value
            for key, value in sidecar.items()
            if key in reference and reference[key]
        }
        statuses = [core.status, app.status, sidecar_status]
        rank = {"machine-draft": 0, "reviewed": 1, "reference": 2}
        return cls(
            language=language, core=core, app=app, sidecar=sidecar, text_index=index,
            status=min(statuses, key=rank.__getitem__),
        )

    @classmethod
    @lru_cache(maxsize=None)
    def for_language(cls, language: str) -> Translator:
        """The packaged catalogues for `language`, loaded once per process."""
        return cls.load(language)

    @classmethod
    def pseudo(cls) -> Translator:
        """Language `xx`: every value is `⟦key⟧`. The leak test renders with this."""
        mark = lambda keys: {k: f"⟦{k}⟧" for k in keys}  # noqa: E731
        core_keys = core_catalogue(DEFAULT_LANGUAGE).keys()
        app_keys = Catalogue.load(DEFAULT_LANGUAGE, APP_LOCALES).keys()
        reference = params_reference_keys()
        sidecar = mark(reference)
        return cls(
            language="xx",
            core=Catalogue("xx", "machine-draft", mark(core_keys)),
            app=Catalogue("xx", "machine-draft", mark(app_keys)),
            sidecar=sidecar,
            text_index={_normalise(v): sidecar[k] for k, v in reference.items() if v},
            status="machine-draft",
        )

    # -- rendering --------------------------------------------------------------------

    @property
    def is_draft(self) -> bool:
        return self.language != DEFAULT_LANGUAGE and self.status != "reviewed"

    def _lookup(self, key: str) -> str:
        if key.startswith("app."):
            return self.app.lookup(key)
        if key.startswith("params."):
            if key in self.sidecar:
                return self.sidecar[key]
            return params_reference_keys()[key]
        return self.core.lookup(key)

    def __call__(self, key: str, **params: object) -> str:
        """App chrome by key. Params are display-ready strings; nested Messages render."""
        rendered = {k: (self.render(v) if isinstance(v, Message) else v) for k, v in params.items()}
        try:
            return self._lookup(key).format(**rendered)
        except (KeyError, IndexError) as exc:
            raise KeyError(f"{key!r} in {self.language!r}: {exc}") from exc

    def render(self, message: Message) -> str:
        """Core prose. Literals resolve through the text index (I§5.4)."""
        catalogue = self.app if message.key.startswith("app.") else self.core
        return catalogue.render(message, literal_index=self.text_index)

    def quantity(self, q: Quantity) -> str:
        """The report's number-with-tier - `str(Quantity)`, but in this language."""
        if not q.calibration.is_reportable:
            return self("app.quantity.not_applicable", caveat=q.calibration.caveat())
        tier = q.calibration.tier.value
        if q.low is not None and q.high is not None:
            return self(
                "app.quantity.range_tiered",
                low=f"{q.low:.3g}", high=f"{q.high:.3g}", unit=q.unit, tier=tier,
            )
        return self("app.quantity.value_tiered", value=f"{q.value:.3g}", unit=q.unit, tier=tier)

    def species_name(self, key: str) -> str:
        return self._lookup(f"params.species.{key}.common_name")

    def method_name(self, key: str) -> str:
        return self._lookup(f"params.methods.{key}.name")

    def method_field(self, key: str, field: str) -> str:
        return self._lookup(f"params.methods.{key}.{field}")

    def group_label(self, group: str) -> str:
        return self._lookup(f"params.group.{group}")

    def confidence_label(self, confidence: str) -> str:
        # A lookup, not a Message: the app never constructs one (I§4.1).
        return self._lookup(f"contracts.confidence.{confidence}")


def english() -> Translator:
    return Translator.for_language(DEFAULT_LANGUAGE)


# -- the gate ---------------------------------------------------------------------------


def catalogue_status(
    language: str,
    *,
    core_root: Path = CORE_LOCALES,
    app_root: Path = APP_LOCALES,
    params_root: Path = PARAMS_LOCALES,
) -> str | None:
    """`reviewed` only if all three files say so; None if any is missing (I§6)."""
    if language == DEFAULT_LANGUAGE:
        return "reference"
    statuses = []
    for root in (core_root, app_root, params_root):
        if not (root / f"{language}.yaml").is_file():
            return None
        statuses.append(Catalogue.load(language, root).status)
    return "reviewed" if all(s == "reviewed" for s in statuses) else "machine-draft"


def enabled_languages(
    env: Mapping[str, str] = os.environ,
    status: Callable[[str], str | None] = catalogue_status,
) -> tuple[str, ...]:
    """English, plus every reviewed language, plus drafts when the deployment says so.

    `SEAGARDEN_LANGUAGES` (comma list) restricts the candidates; English is always in.
    """
    wanted = env.get(ENV_LANGUAGES)
    candidates = [c.strip().lower() for c in wanted.split(",")] if wanted else list(LANGUAGES)
    show_drafts = env.get(ENV_SHOW_DRAFTS, "") not in ("", "0", "false", "no")
    out = [DEFAULT_LANGUAGE]
    for language in LANGUAGES:
        if language == DEFAULT_LANGUAGE or language not in candidates:
            continue
        s = status(language)
        if s == "reviewed" or (show_drafts and s is not None):
            out.append(language)
    return tuple(out)


# -- the chooser (one function for both halves, I§5.3) ----------------------------------

_TAG = re.compile(r"^\s*([A-Za-z]{2,3})(?:-[A-Za-z0-9]+)*\s*(?:;\s*q\s*=\s*([0-9.]+))?\s*$")


def language_for(query: str, accept_language: str | None, enabled: Sequence[str]) -> str:
    """`?lang=` if enabled; else the best enabled `Accept-Language` primary tag; else English."""
    allowed = {code.lower() for code in enabled} | {DEFAULT_LANGUAGE}
    values = parse_qs(query.lstrip("?"), keep_blank_values=False).get("lang", [])
    for value in values:
        code = value.strip().lower()
        if code in allowed:
            return code
    ranked: list[tuple[float, int, str]] = []
    for position, part in enumerate((accept_language or "").split(",")):
        m = _TAG.match(part)
        if not m:
            continue
        try:
            q = float(m.group(2)) if m.group(2) is not None else 1.0
        except ValueError:
            continue
        ranked.append((-q, position, m.group(1).lower()))
    for _q, _pos, code in sorted(ranked):
        if code in allowed:
            return code
    return DEFAULT_LANGUAGE
```

Note `@classmethod` over `@lru_cache`: the cache keys on `(cls, language)`, which is what is wanted. If ruff flags `B019` (lru_cache on a method), move the cache to a module-level `_for_language(language)` helper and have the classmethod call it.

- [ ] **Step 4: Write the English app catalogue, complete**

Every string the app shows today, verbatim. Markdown bodies use `|` block scalars.

```yaml
# app/locales/en.yaml
# The reference catalogue for the app's own chrome (design I§4.3). Every other language
# file here must carry exactly these keys. Placeholder NAMES only, never format specs.
language: en
status: reference
messages:
  # --- navbar and shell (shell.py, app.py) ------------------------------------
  app.nav.site: "Site"
  app.nav.catalogue: "Catalogue"
  app.nav.results: "Results"
  app.nav.report: "Report"
  app.shell.about: "About"
  app.shell.help: "Help"
  app.shell.feedback: "Feedback"
  app.shell.language: "Language"
  app.shell.title: "SeaGarden Decision Support Tool"
  app.shell.window_title: "SeaGarden DST"
  app.shell.setup: "Setup"
  app.shell.workflow: "Workflow: 1) pick a Site · 2) choose species, method and scale in Catalogue · 3) click Assess · 4) read Results and Report."
  app.shell.assess: "Assess"
  app.shell.close: "Close"
  app.shell.funding_alt: "SeaGarden - Interreg South Baltic, co-funded by the European Union"
  app.shell.draft_banner: "Machine translation, not yet reviewed."
  app.shell.about.title: "About the SeaGarden DST"
  app.shell.about.body: |
    The **SeaGarden Decision Support Tool** helps plan community-driven regenerative marine farms in the South Baltic. Pick a site, choose what to grow and at what scale, and the tool returns a siting verdict, an expected harvest, and the nitrogen, phosphorus and carbon that harvest removes from the water.

    **What it gives you**

    - A siting verdict computed as the **minimum** across constraint classes, with the binding constraint named. Not a weighted index: a site with a fatal legal exclusion must not score 'moderate' because the water is good.
    - A **calibration tier** beside every number - locally calibrated, regionally extrapolated, literature prior, or contraindicated. Before the WP3 pilot data arrives, essentially every South Baltic figure is a literature prior, and the tool says so on the number itself.
    - **Eutrophication pressure** from the MARBEFES bow-tie, and optional **nutrient forcing** from the EUTROPY box model, both reported beside the ranking and never folded into it.

    - **Programme** - Interreg South Baltic 2021-2027 · **SeaGarden** (STHB.02.02-IP.01-0006/25)
    - **Work package / activity** - WP2 / A2.3 · Deliverable **D2.2**
    - **Lead** - Klaipeda University, Marine Research Institute
    - **Status** - prototype · core `v{version}`

    Source & issues: [{repo_name}]({repo_url})

    Numbers use a decimal point and dates are written year-month-day in every language.

    *Prototype. Outputs are indicative and are not a basis for permitting or consent. Co-funded by the European Union; views expressed are the authors' only.*
  app.shell.help.title: "Using the SeaGarden DST"
  app.shell.help.body: |
    **Workflow**

    1. **Site** - choose a sub-region. In the delivered tool you will draw a polygon; the prototype uses placeholder conditions per sub-region.
    2. **Catalogue** - choose species, cultivation method and scale.
    3. **Assess** - the sidebar button. Results and Report stay blank until you press it, and are cleared again the moment you change the site.
    4. **Results** - ranked options, the binding constraint for each, and the nutrient removal with its calibration tier.
    5. **Report** - the assessment as text, caveats included.

    **Reading the calibration tiers**

    | Tier | Meaning | How it is shown |
    |---|---|---|
    | A | Fitted to SeaGarden pilot data | value with an interval |
    | B | Fitted elsewhere in the Baltic | value as a range |
    | C | Literature prior, no local validation | order-of-magnitude band |
    | D | Contraindicated - a local finding contradicts the model | the finding, in place of the number |

    The tier D case worth knowing: sugar kelp below about 16 psu. The salinity scaling returns a small positive yield; the OLAMUR pilot found outright cultivation failure at 5.5-6.5 psu. The tool shows the finding.
  app.shell.feedback.title: "Send feedback"
  app.shell.feedback.body: |
    This is a co-development prototype for WP2 A2.3. Concrete feedback - which panel, which site, what you expected - is the most useful kind.

    - **Open an issue** - [{repo_url}/issues/new]({repo_url}/issues/new)
    - **Email** - [{email}](mailto:{email}?subject=SeaGarden%20DST%20feedback)
  # --- sidebar status (app.py, _widgets.py) -----------------------------------
  app.status.no_site: "No site selected. Open Site and choose one."
  app.status.site_ready: "Site ready: {label}. Species selected: {n}. Scale: {scale}. Click Assess."
  app.headline.unassessed: "Site unassessed: {reason}"
  app.headline.none: "No species could be assessed at this site."
  app.headline.nothing_reportable: "Nothing reportable here - every option is contraindicated."
  app.headline.none_suitable: "No option is currently suitable; see Results for the constraints."
  app.headline.best: "Best option: {species}, {verdict}{suffix}."
  app.headline.priors_suffix: " (literature priors)"
  app.headline.no_suffix: ""
  app.unassessable.cell_invalid: "no data at this cell.{distance}"
  app.unassessable.nearest: " Nearest valid cell is {km} km away."
  app.unassessable.no_distance: ""
  app.unassessable.year_absent: "the artifact does not carry the requested year."
  app.unassessable.no_conditions: "the data layer could not provide conditions."
  app.source.artifact: "gridded forcing artifact, conditions for {year}, built {built}"
  app.source.unknown_date: "unknown date"
  app.banner.artifact: "Data source: {source}."
  app.banner.placeholder: "Data source: placeholder conditions — plausible order-of-magnitude values, not measurements ({reason})."
  app.banner.this_site: " This site: {note}."
  # --- widgets ------------------------------------------------------------------
  app.tier.badge_title: "{label} - {presentation}"
  app.quantity.none: "-"
  app.quantity.range: "{low}-{high} {unit}"
  app.quantity.value: "{value} {unit}"
  app.quantity.range_tiered: "{low}-{high} {unit} [{tier}]"
  app.quantity.value_tiered: "{value} {unit} [{tier}]"
  app.quantity.not_applicable: "not applicable - {caveat}"
  app.legend.title: "Calibration tiers"
  app.legend.A: " fitted to SeaGarden pilot data"
  app.legend.B: " fitted elsewhere in the Baltic"
  app.legend.C: " literature prior, no local validation"
  app.legend.D: " contraindicated - a finding contradicts the model"
  app.legend.note: "Before WP3 pilot data arrives (M12-30), essentially every South Baltic result is tier C. Read those as indicative bands, not estimates."
  app.month.1: "Jan"
  app.month.2: "Feb"
  app.month.3: "Mar"
  app.month.4: "Apr"
  app.month.5: "May"
  app.month.6: "Jun"
  app.month.7: "Jul"
  app.month.8: "Aug"
  app.month.9: "Sep"
  app.month.10: "Oct"
  app.month.11: "Nov"
  app.month.12: "Dec"
  app.window.span: "{start}–{end}"
  app.window.over_winter: "{span} (over winter)"
  # --- user mode ----------------------------------------------------------------
  app.mode.label: "I am here as"
  app.mode.choice: "{title} - {audience}"
  app.mode.plan.title: "Plan"
  app.mode.plan.audience: "Authorities, spatial planners"
  app.mode.plan.question: "Where could regenerative farming go here, and what would it achieve?"
  app.mode.farm.title: "Farm"
  app.mode.farm.audience: "Farmers, SMEs, operators"
  app.mode.farm.question: "Can I farm this spot, what should I grow, and what will I get?"
  app.mode.start.title: "Start"
  app.mode.start.audience: "Communities, NGOs, citizen science"
  app.mode.start.question: "Could we run a small sea garden here, and what would it take?"
  app.mode.explore.title: "Explore"
  app.mode.explore.audience: "Researchers, students, consultants"
  app.mode.explore.question: "What do the models say, and how confident are they?"
  # --- site panel ---------------------------------------------------------------
  app.site.region: "Sub-region"
  app.site.help: "Click a marker on the map, or choose here. "
  app.site.help_absent_one: "{regions} has no confirmed position yet and can only be chosen here."
  app.site.help_absent_many: "{regions} have no confirmed position yet and can only be chosen here."
  app.site.and: " and "
  app.site.label: "Site name (optional)"
  app.site.label_placeholder: "e.g. Melnrage pilot"
  app.site.use: "Use this site"
  app.site.where: "Where"
  app.site.no_map: |
    *The map needs `shiny_deckgl`, which ships on a conda channel rather than PyPI and is not installed here:*

        micromamba install -n shiny -c razinka shiny-deckgl

    *Choosing a sub-region in the sidebar works either way.*
  app.site.tooltip_depth: "Model depth"
  app.site.depth_unknown: "unknown"
  app.site.no_position: "{region} has no confirmed position. Its conditions are a sub-region summary, so nothing here is about a particular cell."
  app.site.position: "{lat}, {lon} - {provenance}. A result here is a {presentation}."
  app.site.conditions: "Site conditions"
  app.site.cond.salinity: "Salinity"
  app.site.cond.mean_temp: "Mean temperature"
  app.site.cond.summer_winter: "Summer / winter temperature"
  app.site.cond.din: "Dissolved inorganic nitrogen"
  app.site.cond.dip: "Dissolved inorganic phosphorus"
  app.site.cond.depth: "Depth"
  app.site.cond.wave: "Significant wave height"
  app.site.cond.par: "PAR at cultivation depth"
  app.site.confidence_line: "Data confidence: {confidence} (placeholder). Calibration domain: {region}."
  app.site.provenance_card: "Where these numbers come from"
  app.site.provenance_body: |
    The map shows **where** a sub-region is. The numbers below are **placeholder conditions**, one set per sub-region: plausible order-of-magnitude values, not measurements, and not read from the position. Every result derived from them is a literature prior.

    In the delivered tool you draw a polygon and the conditions are read from the curated layers - Copernicus Marine reanalysis for salinity, temperature and nutrients, EMODnet for bathymetry and human use, HELCOM for protected areas. The contract between this panel and the model core does not change.
  # --- catalogue panel ----------------------------------------------------------
  app.catalogue.species: "Species"
  app.catalogue.scale: "Scale"
  app.catalogue.only_af: "Select only the species named in the Application Form"
  app.catalogue.methods: "Cultivation methods"
  app.catalogue.col.species: "Species"
  app.catalogue.col.scientific: "Scientific name"
  app.catalogue.col.group: "Group"
  app.catalogue.col.in_af: "In the AF"
  app.catalogue.col.window: "Cultivation window"
  app.catalogue.yes: "yes"
  app.catalogue.no: "no"
  app.catalogue.species_note: "Only Ulva and blue mussel are named in the Application Form. Fucus carries the OLAMUR low-salinity evidence, Chorda is what KU will actually cultivate in Lithuania (decision D1), and sugar kelp is carried for the Danish site and as the worked contraindication."
  app.catalogue.col.method: "Method"
  app.catalogue.col.anchoring: "Anchoring"
  app.catalogue.col.cultivation: "Cultivation"
  app.catalogue.col.depth: "Depth"
  app.catalogue.col.max_wave: "Max wave"
  app.catalogue.col.unit_area: "Unit area"
  app.catalogue.methods_note: "Costs and labour are deliberately empty. They are filled from WP3's actual procurement records - the viability figures are only defensible if the coefficients are what the project really paid."
  # --- results panel ------------------------------------------------------------
  app.results.ranked: "Ranked options"
  app.results.excluded: "Excluded"
  app.results.pressure: "Pressure context"
  app.results.pick_site: "Pick a site, then click Assess."
  app.results.unassessed: "This site is unassessed because the data layer could not provide conditions. See the report for the coverage reason."
  app.results.none: "No species could be assessed at this site."
  app.results.col.option: "Option"
  app.results.col.verdict: "Verdict"
  app.results.col.harvest: "Harvest"
  app.results.col.nitrogen: "Nitrogen"
  app.results.col.phosphorus: "Phosphorus"
  app.results.col.carbon: "Carbon"
  app.results.all_pass: "All constraints pass"
  app.results.constraint_line: "{name}: {verdict} - {reason}"
  app.results.caveats: "Caveats"
  app.results.caveat_line: "{label}: {text}"
  app.results.dash: "-"
  app.results.nothing_excluded: "Nothing excluded at this site."
  app.results.no_bowtie: "No bow-tie inference supplied. Nutrient removal is reported on its own terms."
  app.results.p_top: "P(top event {state}) = {p}"
  # --- report panel -------------------------------------------------------------
  app.report.title: "Assessment report"
  app.report.download_txt: "Download report (.txt)"
  app.report.download_json: "Download data (.json)"
  app.report.none: "No assessment yet. Pick a site and click Assess."
  app.report.heading: "SEAGARDEN DECISION SUPPORT TOOL - SITE ASSESSMENT"
  app.report.site: "Site:        {site}"
  app.report.subregion: "Sub-region:  {region}"
  app.report.conditions_unavailable: "Conditions:  unavailable — data layer could not assess this site"
  app.report.conditions: "Conditions:  salinity {salinity} psu, DIN {din} umol/L, depth {depth} m"
  app.report.confidence: "Data confidence: {confidence}"
  app.report.generated: "Generated:   {date} - core v{version}"
  app.report.ranked: "RANKED OPTIONS"
  app.report.unassessed: "UNASSESSED: {reason}"
  app.report.none_assessed: "No species could be assessed at this site."
  app.report.option: "{species} - {method} ({ha} ha)"
  app.report.verdict: "  Verdict:   {verdict}"
  app.report.binding: "  Binding:   {binding}"
  app.report.harvest: "  Harvest:   {harvest}"
  app.report.nitrogen: "  Nitrogen:  {value}"
  app.report.phosphorus: "  Phosphorus:{value}"
  app.report.carbon: "  Carbon:    {value}"
  app.report.calibration: "  Calibration: {label} - {presentation}"
  app.report.excluded: "EXCLUDED"
  app.report.excluded_line: "- {key}: {reason}"
  app.report.pressure: "PRESSURE CONTEXT"
  app.report.p_top: "- P(top event {state}) = {p}"
  app.report.pressure_note: "  {note}"
  app.report.caveats: "CAVEATS"
  app.report.caveat_line: "- {label}: {text}"
  app.report.carbon_caveat: "- Carbon is reported as carbon in harvested biomass only. Sequestration is not reported: calcification releases CO2, so a sequestration claim would depend on shell being removed from the water and kept out of it."
  app.report.legal_caveat: "- Legal permissibility is unassessed until the regulatory records exist (A2.2, M12). An unknown legal status blocks the verdict rather than passing it."
  app.report.footer: "Prototype output. Indicative only; not a basis for permitting or consent."
  app.report.unassessed.cell_invalid_near: "No data at this cell; nearest valid cell is {km} km away."
  app.report.unassessed.cell_invalid: "No data at this cell."
  app.report.unassessed.year_absent: "The artifact does not carry the requested year."
  app.report.unassessed.no_conditions: "The data layer could not provide conditions."
  app.report.source.artifact: "Data source: {source}"
  app.report.source.placeholder_reason: "Data source: placeholder conditions ({reason})"
  app.report.source.artifact_bare: "Data source: gridded forcing artifact"
  app.report.source.placeholder_bare: "Data source: placeholder conditions"
  app.report.source.this_site: " — this site: {note}"
  app.report.caveat.artifact: "- Site conditions come from the gridded forcing artifact."
  app.report.caveat.placeholder: "- Site conditions in this prototype are placeholders, not measurements."
  app.report.caveat.this_site: " This site: {note}."
```

Two English changes are deliberate and outside every golden: `app.status.site_ready` is count-neutral (spec I§7), and `app.shell.about.body` gains the one sentence about decimal points and dates (spec I§7). Everything else is verbatim.

- [ ] **Step 5: Run, then commit**

Run: `MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest app/tests/test_i18n_app.py -q && micromamba run -n shiny ruff check .`
Expected: all pass.

```bash
git add app/i18n.py app/locales/en.yaml app/tests/test_i18n_app.py
git commit -m "feat(app): Translator, language chooser, enablement gate, English app catalogue (I-a)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6 (part 1 of 2, with Task 7): The shell and the entry point build per request, in a language

**Tasks 6 and 7 are one unit of work and one commit.** `app.py` here already calls the panel signatures Task 7 defines, so the suite is red between them. Implement 6 then 7, run the whole suite at the end of Task 7, commit once there. A reviewer gates the pair, not the halves.

**Files:**
- Modify: `app/shell.py` (whole file)
- Modify: `app/app.py` (whole file)
- Modify: `app/state.py:7-19`, `:29-47`
- Modify: `app/tests/test_app_smoke.py:21-26`, `:489-492`
- Test: `app/tests/test_i18n_app.py` (extend)

**Interfaces:**
- Consumes: `Translator`, `language_for`, `enabled_languages`, `LANGUAGE_NAMES`, `english` from Task 5. The five panel `*_ui(id, tr)` factories of Task 7 — until Task 7 lands, `app.py` calls them with the old one-argument signature; Task 7 flips the call sites. To keep every intermediate commit green, Task 6 changes `app.py` and `shell.py` only, and the panels keep rendering English through `str()`.
- Produces: `shell.app_shell(tr, *panels, language_menu: bool = True) -> Tag`; `shell.about_modal(tr)`, `help_modal(tr)`, `feedback_modal(tr)`; `shell.language_menu(tr, enabled) -> Tag`; `shell.draft_banner(tr) -> Tag | None`; `app.build_ui(language: str) -> Tag`; `app.app_ui(request) -> Tag`; `app.scale_sentence(*, label, count, scale_key, tr)`; `AppState.translator: Callable[[], Translator]` set by `server()`.

- [ ] **Step 1: Extend the failing tests** (append to `app/tests/test_i18n_app.py`)

```python
def test_the_page_builds_in_english_and_in_the_pseudo_locale():
    from app.app import build_ui

    en = str(build_ui("en"))
    assert 'lang="en"' in en and ">Assess<" in en
    xx = str(build_ui("xx"))
    assert 'lang="xx"' in xx and "⟦app.shell.assess⟧" in xx and ">Assess<" not in xx


def test_app_ui_takes_a_request_and_reads_lang_from_it():
    from starlette.requests import Request

    from app.app import app_ui

    def request(query: bytes, accept: bytes | None) -> Request:
        headers = [(b"accept-language", accept)] if accept else []
        return Request({
            "type": "http", "method": "GET", "scheme": "http", "path": "/",
            "query_string": query, "headers": headers, "server": ("test", 80),
        })

    assert 'lang="en"' in str(app_ui(request(b"lang=de", b"de")))  # de not enabled in I-a
    assert 'lang="en"' in str(app_ui(request(b"", None)))


def test_the_language_menu_lists_enabled_languages_as_relative_links():
    from app.shell import language_menu

    html = str(language_menu(Translator.for_language("en"), ("en", "de")))
    assert 'href="?lang=de"' in html and "Deutsch" in html
    assert 'href="?lang=en"' not in html, "the current language is marked, not linked"
    assert "English" in html


def test_a_draft_language_shows_the_bilingual_banner_and_english_does_not():
    from app.shell import draft_banner

    assert draft_banner(Translator.for_language("en")) is None
    banner = str(draft_banner(Translator.pseudo()))
    assert "⟦app.shell.draft_banner⟧" in banner
    assert "Machine translation, not yet reviewed." in banner


def test_state_carries_a_translator_slot_unset_until_the_session_sets_it():
    from app.state import AppState

    assert AppState.defaults()["translator"] is None
```

- [ ] **Step 2: Run to verify failure**

Run: `MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest app/tests/test_i18n_app.py -q`
Expected: five new FAIL (`ImportError: build_ui`, etc.).

- [ ] **Step 3: Rewrite `app/shell.py`**

Replace the whole file:

```python
"""DST app shell: branding, sidebar, top-bar actions, the language menu.

Same shape as the NiD4OCEAN DST shell. The brand theme is `www/seagarden.css`, inlined
into the page so it needs no static route and survives the sub-path proxy and an
offline host. The two logo PNGs are base64-inlined for the same reason: a broken image
link degrades silently to an empty box, and the funding lockup is one Interreg's
communication rules require to be visible.

Every string here comes from the session's `Translator` (package I). The old `t()`
passthrough is gone: `tr("app.shell.assess")` looks the key up in the language the
request asked for, and the pseudo-locale test in app/tests/test_i18n_guards.py fails
on any literal that slips past it.
"""

from __future__ import annotations

import base64
from collections.abc import Sequence
from pathlib import Path

from shiny import ui

from app.i18n import LANGUAGE_NAMES, Translator, english

_WWW = Path(__file__).parent / "www"
_BRAND_CSS = _WWW / "seagarden.css"
_ICON = _WWW / "seagarden-icon.png"  # the circular mark, from the Communication folder
_FUNDING = _WWW / "seagarden-funding-lockup.png"  # SeaGarden | Interreg South Baltic | EU

REPO_URL = "https://github.com/razinkele/seagarden-dst"
CONTACT_EMAIL = "arturas.razinkovas-baziukas@ku.lt"


def _data_uri(path: Path) -> str:
    """Base64-inline a PNG so the page needs no static-asset route for it."""
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def _brand() -> ui.Tag:
    """Navbar brand: the circular icon mark, the name with the lime 'Sea', a DST tag.
    Proper nouns, not translated."""
    return ui.tags.span(
        ui.tags.img(src=_data_uri(_ICON), class_="sg-logo", alt=""),
        ui.tags.span(ui.tags.b("Sea"), "Garden", class_="sg-name"),
        ui.tags.span("DST", class_="sg-dst"),
        class_="sg-brand",
    )


def _funding_strip(tr: Translator) -> ui.Tag:
    """The full lockup on a white strip: it is dark-on-white and cannot sit in the bar."""
    return ui.div(
        ui.tags.img(
            src=_data_uri(_FUNDING), class_="sg-funding", alt=tr("app.shell.funding_alt")
        ),
        class_="sg-funding-strip",
    )


_ICONS = {
    "about": "<circle cx='12' cy='12' r='9'/><path d='M12 11v5'/><path d='M12 7.5v.01'/>",
    "help": (
        "<circle cx='12' cy='12' r='9'/>"
        "<path d='M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.8.4-1 .9-1 1.7'/>"
        "<path d='M12 16.5v.01'/>"
    ),
    "feedback": "<path d='M4 5h16v11H9l-4 3v-3H4z'/>",
}


def _action(id_: str, label: str) -> ui.Tag:
    svg = (
        f"<svg class='sg-act-ico' viewBox='0 0 24 24' fill='none' stroke='currentColor' "
        f"stroke-width='1.7' stroke-linecap='round' stroke-linejoin='round' "
        f"aria-hidden='true'>{_ICONS[id_]}</svg>"
    )
    return ui.nav_control(
        ui.input_action_link(
            id_, ui.TagList(ui.HTML(svg), ui.tags.span(label)), class_="sg-action"
        )
    )


def about_modal(tr: Translator) -> ui.Tag:
    # Read the version from the package - a hand-copied one drifts silently, and this
    # dialog is exactly where a reader checks what they are looking at.
    from seagarden_dst import __version__

    return ui.modal(
        ui.markdown(
            tr(
                "app.shell.about.body",
                version=__version__, repo_name=REPO_URL.split("//")[1], repo_url=REPO_URL,
            )
        ),
        title=tr("app.shell.about.title"),
        easy_close=True,
        size="l",
        footer=ui.modal_button(tr("app.shell.close")),
    )


def help_modal(tr: Translator) -> ui.Tag:
    return ui.modal(
        ui.markdown(tr("app.shell.help.body")),
        title=tr("app.shell.help.title"),
        easy_close=True,
        size="xl",
        footer=ui.modal_button(tr("app.shell.close")),
    )


def feedback_modal(tr: Translator) -> ui.Tag:
    return ui.modal(
        ui.markdown(tr("app.shell.feedback.body", repo_url=REPO_URL, email=CONTACT_EMAIL)),
        title=tr("app.shell.feedback.title"),
        easy_close=True,
        size="m",
        footer=ui.modal_button(tr("app.shell.close")),
    )


def language_menu(tr: Translator, enabled: Sequence[str]) -> ui.Tag:
    """The navbar menu of enabled languages, as RELATIVE `?lang=` links (I§5.3).

    Relative so the sub-path proxy on laguna (`/seagarden-dst/`) needs nothing. The
    current language is a marked, unlinked item. Names are endonyms, not translated.
    """
    items = []
    for code in enabled:
        name = LANGUAGE_NAMES.get(code, code)
        if code == tr.language:
            items.append(ui.nav_control(ui.tags.span(f"✓ {name}", class_="sg-lang-current")))
        else:
            items.append(ui.nav_control(ui.tags.a(name, href=f"?lang={code}", class_="sg-lang")))
    return ui.nav_menu(tr("app.shell.language"), *items, align="right")


def draft_banner(tr: Translator) -> ui.Tag | None:
    """Bilingual notice under the navbar for a machine-draft language (I§6); None otherwise."""
    if not tr.is_draft:
        return None
    return ui.div(
        ui.tags.strong(tr("app.shell.draft_banner")),
        " ",
        english()("app.shell.draft_banner"),
        class_="sg-draft-banner",
        role="note",
    )


def _map_head() -> tuple:
    """deck.gl + MapLibre assets, when `shiny_deckgl` is installed.

    `MapWidget.ui()` returns a bare div with no dependency attached, so without this the
    map is an empty box and the failure is silent - the page renders, the panel looks
    fine, nothing draws. Imported lazily for the same reason as in `modules/site.py`:
    the package ships on a conda channel, is deliberately not a pip dependency, and
    `app/tests` imports this module, so a module-scope import turns CI red at collection.
    """
    try:
        from shiny_deckgl.ui import head_includes
    except ImportError:
        return ()
    return (head_includes(),)


def app_shell(tr: Translator, *panels, enabled: Sequence[str] = ("en",)) -> ui.Tag:
    banner = draft_banner(tr)
    header = [ui.include_css(_BRAND_CSS, method="inline")]
    if banner is not None:
        header.append(banner)
    return ui.page_navbar(
        *_map_head(),
        *panels,
        ui.nav_spacer(),
        _action("about", tr("app.shell.about")),
        _action("help", tr("app.shell.help")),
        _action("feedback", tr("app.shell.feedback")),
        language_menu(tr, enabled),
        title=_brand(),
        id="main_nav",
        # Inlined so it loads with no extra request and works offline.
        header=ui.TagList(*header),
        window_title=tr("app.shell.window_title"),
        lang=tr.language,
        sidebar=ui.sidebar(
            ui.tags.h1(tr("app.shell.title"), class_="visually-hidden"),
            ui.h2(tr("app.shell.setup")),
            ui.help_text(tr("app.shell.workflow")),
            ui.output_ui("user_mode_slot"),
            ui.input_action_button("assess", tr("app.shell.assess"), class_="btn-primary"),
            ui.output_ui("status_slot"),
            ui.output_ui("data_source_slot"),
            _funding_strip(tr),
            width=320,
        ),
    )
```

Add to `app/www/seagarden.css` (end of file):

```css
/* Package I: language menu and the machine-draft notice. */
.sg-lang-current { opacity: .7; }
.sg-draft-banner { padding: .4rem 1rem; font-size: .9em; background: var(--sg-sand, #f5efe3); }
```

(`--sg-sand` is whichever existing light token the stylesheet defines; if none fits, add one beside the other `--sg-*` tokens rather than inlining a hex in Python — `test_no_app_module_hard_codes_a_colour_in_an_inline_style` guards the Python side only, but the rule is the same.)

- [ ] **Step 4: Rewrite `app/app.py`**

```python
"""SeaGarden DST Shiny app entry point (wired).

Run from the REPO ROOT as a dotted module:

    shiny run app.app

NOT `shiny run app/app.py` - that puts app/ on sys.path and breaks `from app.* import`.
Same convention as the NiD4OCEAN DST, and `pyproject.toml` sets
`pythonpath = ["src", "."]` so both `seagarden_dst` and `app` resolve from the root.

The UI is a FUNCTION OF THE REQUEST (package I): `app_ui(request)` picks the language
from `?lang=` or `Accept-Language` through `language_for`, the same function the server
uses on the websocket side, so the page and its renders cannot disagree.
"""

from __future__ import annotations

from shiny import App, reactive, render, ui
from starlette.requests import Request

from app.i18n import Translator, enabled_languages, language_for
from app.modules._widgets import data_source_banner, headline_for
from app.modules.catalogue import catalogue_server, catalogue_ui
from app.modules.report import report_server, report_ui
from app.modules.results import results_server, results_ui, run_assessment
from app.modules.site import site_server, site_ui
from app.modules.user_mode import user_mode_server, user_mode_ui
from app.shell import about_modal, app_shell, feedback_modal, help_modal
from app.state import AppState
from seagarden_dst import SCALE_LABELS
from seagarden_dst.gridded import select_forcing


def build_ui(language: str) -> ui.Tag:
    """The whole page in one language. `app_ui` and the tests call this."""
    tr = Translator.pseudo() if language == "xx" else Translator.for_language(language)
    return app_shell(
        tr,
        ui.nav_panel(tr("app.nav.site"), site_ui("site", tr)),
        ui.nav_panel(tr("app.nav.catalogue"), catalogue_ui("cat", tr)),
        ui.nav_panel(tr("app.nav.results"), results_ui("res", tr)),
        ui.nav_panel(tr("app.nav.report"), report_ui("rep", tr)),
        enabled=enabled_languages(),
    )


def app_ui(request: Request) -> ui.Tag:
    language = language_for(
        request.url.query, request.headers.get("accept-language"), enabled_languages()
    )
    return build_ui(language)


def scale_sentence(*, label: str, count: int, scale_key: str, tr: Translator) -> str:
    """The 'site ready' sentence. `scale_key` is state; the user reads its label."""
    return tr(
        "app.status.site_ready", label=label, n=str(count), scale=SCALE_LABELS[scale_key]
    )


def server(input, output, session):  # noqa: A002 - Shiny's signature
    state = AppState()
    state.forcing.set(select_forcing())

    @reactive.calc
    def translator() -> Translator:
        # `.clientdata_url_search` is set by shiny.js from window.location.search on
        # connect; the header comes from the websocket handshake. Same chooser as the
        # page, same enabled set, so a render never speaks a different language than
        # the chrome around it.
        query = session.input[".clientdata_url_search"]()
        accept = session.http_conn.headers.get("accept-language")
        return Translator.for_language(language_for(query, accept, enabled_languages()))

    state.translator = translator

    user_mode_server("um", state=state)
    site_server("site", state=state)
    catalogue_server("cat", state=state)
    results_server("res", state=state)
    report_server("rep", state=state)

    @render.ui
    def user_mode_slot():
        return user_mode_ui("um", state.translator())

    @render.ui
    def status_slot():
        tr = state.translator()
        context = state.context.get()
        assessment = state.assessment.get()
        if context is None:
            return ui.p(tr("app.status.no_site"))
        if assessment is None:
            species = state.selected_species.get()
            count = len(species) if species else 0
            return ui.p(
                scale_sentence(
                    label=state.site_label.get(), count=count, scale_key=state.scale.get(), tr=tr
                )
            )
        _cls, text = headline_for(assessment, tr)
        return ui.p(text)

    @render.ui
    def data_source_slot():
        choice = state.forcing.get()
        assessment = state.assessment.get()
        context = assessment.context if assessment is not None else state.context.get()
        return ui.p(data_source_banner(choice, context, state.translator()))

    @reactive.effect
    @reactive.event(input.assess)
    def _on_assess():
        run_assessment(state)

    # CRITICAL: invalidate a stale assessment the moment the site, species, scale or
    # optional forcing changes, so Results and the DOWNLOADED REPORT can never show
    # one site's numbers under another site's label. Everything returns to its
    # placeholder until the user clicks Assess again.
    @reactive.effect
    @reactive.event(
        state.context,
        state.selected_species,
        state.scale,
        state.method_overrides,
        state.eutropy_scenario,
        state.bowtie_inference,
        ignore_init=True,
    )
    def _invalidate_stale_assessment():
        state.assessment.set(None)

    @reactive.effect
    @reactive.event(input.about)
    def _show_about():
        ui.modal_show(about_modal(state.translator()))

    @reactive.effect
    @reactive.event(input.help)
    def _show_help():
        ui.modal_show(help_modal(state.translator()))

    @reactive.effect
    @reactive.event(input.feedback)
    def _show_feedback():
        ui.modal_show(feedback_modal(state.translator()))


app = App(app_ui, server)
```

This file already calls the Task 7 signatures (`site_ui("site", tr)`, `headline_for(assessment, tr)`, `data_source_banner(choice, context, tr)`, `user_mode_ui("um", tr)`). **Tasks 6 and 7 therefore land in one commit series but are tested together at the end of Task 7**; Task 6's Step 6 runs only the shell-level tests that do not need the panels (`-k "menu or banner or state_carries"`). If the implementer prefers every commit green, do Task 7 first and this task second — the plan orders them this way because the shell is what defines `tr`'s journey.

- [ ] **Step 5: `AppState` gains the slot**

`app/state.py`: add `"translator": None,  # Callable[[], Translator]; set once per session by server(), never reset` to `_DEFAULTS`, and in `__init__`: `self.translator = _DEFAULTS["translator"]` (a plain attribute, not a `reactive.Value`: it is a `reactive.calc`, already reactive). Update the module docstring line to mention it.

`app/tests/test_app_smoke.py:489-492` `_page_html()` becomes `return str(build_ui("en"))` with `from app.app import build_ui`; `test_app_object_builds` keeps `from app.app import app, app_ui` and adds `assert callable(app_ui)`.

- [ ] **Step 6: Run the shell-only tests, then go straight to Task 7 — no commit yet**

Run: `MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest app/tests/test_i18n_app.py -k "menu or banner or state_carries" -q && micromamba run -n shiny ruff check app/shell.py app/state.py`
Expected: pass. Everything else goes green at the end of Task 7, whose commit covers both tasks.

---

### Task 7 (part 2 of 2, with Task 6): The five panels render through `tr`, as pure functions

**Files:**
- Modify: `app/modules/_widgets.py` (whole file), `app/modules/user_mode.py` (whole file), `app/modules/report.py` (whole file)
- Modify: `app/modules/catalogue.py`, `app/modules/results.py`, `app/modules/site.py` (targeted)
- Modify: `app/tests/test_app_smoke.py` (call sites), `tests/test_report_golden.py` (call site)
- Test: `app/tests/test_i18n_app.py` (extend)

**Interfaces:**
- Consumes: `Translator`, `english` (Task 5); every core `Message` site (Tasks 2–4).
- Produces pure renderers, each `(…, tr: Translator)`:
  - `_widgets`: `tier_badge(tier, tr)`, `quantity(q, tr)`, `verdict_pill(verdict, tr)`, `headline_for(assessment, tr) -> tuple[str, str]`, `artifact_source_text(choice, tr)`, `data_source_banner(choice, context, tr)`, `calibration_legend(tr)`, `window_label(window, tr)`.
  - `user_mode`: `user_mode_ui(id, tr)`, `mode_choices(tr) -> dict`, `mode_question(mode, tr) -> Tag`.
  - `site`: `site_ui(id, tr)`, `site_markers(tr)`, `render_position_note(region, tr)`, `render_conditions(region, tr)`, `absent_regions_note(tr) -> str`.
  - `catalogue`: `catalogue_ui(id, tr)`, `species_choices(tr)`, `species_table(tr)`, `method_table(tr)`.
  - `results`: `results_ui(id, tr)`, `render_ranking(assessment, tr)`, `render_excluded(assessment, tr)`, `render_pressure(assessment, tr)`.
  - `report`: `report_ui(id, tr)`, `render_report(assessment, choice=None, *, today, tr=english())`.
  - Every `*_server` reads `state.translator()` inside its renderers and delegates to the pure function.

- [ ] **Step 1: Extend the failing tests** (append to `app/tests/test_i18n_app.py`)

```python
def _assessed_state(region: str = "LT-coastal"):
    from app.modules.results import run_assessment
    from app.tests.test_app_smoke import _FakeState
    from seagarden_dst import SiteContext

    state = _FakeState(SiteContext.from_region(region, label="Melnrage"))
    run_assessment(state)
    return state


def test_every_panel_factory_takes_a_translator():
    from app.modules.catalogue import catalogue_ui
    from app.modules.report import report_ui
    from app.modules.results import results_ui
    from app.modules.site import site_ui
    from app.modules.user_mode import user_mode_ui

    xx = Translator.pseudo()
    for factory, id_ in (
        (site_ui, "site"), (catalogue_ui, "cat"), (results_ui, "res"), (report_ui, "rep"),
        (user_mode_ui, "um"),
    ):
        html = str(factory(id_, xx))
        assert "⟦app." in html, f"{factory.__name__} rendered nothing from the catalogue"


def test_the_pure_renderers_speak_the_translators_language():
    from datetime import date

    from app.modules._widgets import data_source_banner, headline_for
    from app.modules.report import render_report
    from app.modules.results import render_excluded, render_pressure, render_ranking
    from app.modules.site import render_conditions, render_position_note

    state = _assessed_state()
    xx = Translator.pseudo()
    assessment = state.assessment.get()
    assert "⟦app.headline.best⟧" == headline_for(assessment, xx)[1]
    assert "⟦app.banner.artifact⟧" == data_source_banner(state.forcing.get(), None, xx)
    for tag in (
        render_ranking(assessment, xx), render_excluded(assessment, xx),
        render_pressure(assessment, xx), render_conditions("LT-coastal", xx),
        render_position_note("LT-coastal", xx),
    ):
        assert "⟦app." in str(tag)
    text = render_report(assessment, state.forcing.get(), today=date(2026, 9, 28), tr=xx)
    assert text.splitlines()[0] == "⟦app.report.heading⟧"
    assert "⟦params.species." in text and "⟦calibration.tier." in text


def test_english_renderers_are_unchanged_from_before_the_seam():
    """The pure functions in English say exactly what the closures said."""
    from app.modules._widgets import data_source_banner, headline_for, window_label
    from seagarden_dst.forcing import placeholder_choice

    en = Translator.for_language("en")
    state = _assessed_state()
    assert headline_for(state.assessment.get(), en)[1].startswith("Best option: ")
    banner = data_source_banner(placeholder_choice("no artifact at data/forcing"), None, en)
    assert banner.startswith("Data source: placeholder conditions — plausible")
    assert window_label((10, 6), en) == "Oct–Jun (over winter)"
    assert window_label((4, 10), en) == "Apr–Oct"
```

- [ ] **Step 2: Run to verify failure**

Run: `MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest app/tests/test_i18n_app.py -q`
Expected: `TypeError` (factories take one argument) and `ImportError` (`render_ranking`).

- [ ] **Step 3: Rewrite `app/modules/_widgets.py`**

```python
"""Small shared renderers, every one of them a function of the session's Translator.

The important one is `tier_badge`: the calibration tier must be rendered inside the
same visual element as the number it qualifies (specification 7.4 and the risk
register row "users read tier-C numbers as measurements"). Putting it in a footnote
is the failure mode this function exists to prevent.
"""

from __future__ import annotations

from shiny import ui

from app.i18n import Translator
from seagarden_dst import SiteAssessment, SiteContext, Tier, Verdict
from seagarden_dst.calibration import Quantity, for_display
from seagarden_dst.forcing import Coverage, ForcingChoice

# Colours live in app/www/seagarden.css under these class names, so the badge follows
# the theme's tokens rather than carrying its own hex.
_VERDICTS = frozenset({"suitable", "marginal", "unsuitable", "unknown"})


def tier_badge(tier: Tier, tr: Translator) -> ui.Tag:
    return ui.tags.span(
        tier.value,
        title=tr("app.tier.badge_title", label=tier.label, presentation=tier.presentation),
        class_=f"sg-tier sg-tier-{tier.value.lower()}",
    )


def quantity(q: Quantity | None, tr: Translator) -> ui.Tag:
    """A number and its tier, inseparable."""
    if q is None:
        return ui.tags.span(tr("app.quantity.none"))
    shown = for_display(q)
    if not shown.calibration.is_reportable:
        return ui.tags.span(tr.render(shown.calibration.caveat()), class_="sg-caveat")
    if shown.low is not None and shown.high is not None:
        text = tr(
            "app.quantity.range", low=f"{shown.low:.3g}", high=f"{shown.high:.3g}", unit=shown.unit
        )
    else:
        text = tr("app.quantity.value", value=f"{shown.value:.3g}", unit=shown.unit)
    return ui.tags.span(text, tier_badge(shown.calibration.tier, tr))


def verdict_pill(verdict: str, tr: Translator) -> ui.Tag:
    kind = verdict if verdict in _VERDICTS else "unknown"
    shown = tr.render(Verdict(verdict).label) if verdict in _VERDICTS else verdict
    return ui.tags.span(shown, class_=f"sg-verdict sg-verdict-{kind}")


def headline_for(assessment: SiteAssessment, tr: Translator) -> tuple[str, str]:
    """(css class, sentence) for the sidebar status.

    Sign- and tier-aware: never announces a "best option" when nothing is reportable
    or everything is unsuitable, which is the equivalent of the NiD4OCEAN headline
    guard against a false "top" when all net contributions are non-positive.
    """
    if assessment.unassessable:
        return "warn", tr("app.headline.unassessed", reason=_unassessable_reason(assessment, tr))
    if not assessment.ranked:
        return "muted", tr("app.headline.none")
    if not assessment.any_reportable:
        return "warn", tr("app.headline.nothing_reportable")
    best = assessment.best
    if best is None:
        return "warn", tr("app.headline.none_suitable")
    suffix_key = (
        "app.headline.priors_suffix" if assessment.lowest_tier is Tier.C else "app.headline.no_suffix"
    )
    return "ok", tr(
        "app.headline.best",
        species=tr.species_name(best.species_key),
        verdict=Verdict(best.verdict).label,
        suffix=tr(suffix_key),
    )


def _unassessable_reason(assessment: SiteAssessment, tr: Translator) -> str:
    if assessment.coverage is Coverage.CELL_INVALID:
        distance = (
            tr("app.unassessable.nearest", km=f"{assessment.nearest_valid_km:.2f}")
            if assessment.nearest_valid_km is not None
            else tr("app.unassessable.no_distance")
        )
        return tr("app.unassessable.cell_invalid", distance=distance)
    if assessment.coverage is Coverage.YEAR_ABSENT:
        return tr("app.unassessable.year_absent")
    return tr("app.unassessable.no_conditions")


def artifact_source_text(choice: ForcingChoice, tr: Translator) -> str:
    """The artifact data-source sentence, minus its trailing period.

    Shared by `data_source_banner` here and `report._data_source_line`, so the
    banner and the downloadable report cannot drift on the wording that names the
    query year and the artifact's build date.
    """
    built = (
        choice.built_on.strftime("%Y-%m-%d") if choice.built_on else tr("app.source.unknown_date")
    )
    return tr("app.source.artifact", year=str(choice.year), built=built)


def data_source_banner(
    choice: ForcingChoice, context: SiteContext | None, tr: Translator
) -> str:
    """Sentence naming what the app is running on, and why if it is not the artifact.

    `choice.reason` is an operator diagnostic and stays English inside the keyed
    sentence (spec I§7).
    """
    if choice.is_artifact:
        text = tr("app.banner.artifact", source=artifact_source_text(choice, tr))
    else:
        text = tr("app.banner.placeholder", reason=choice.reason)
    if context is not None and context.source_note is not None:
        text += tr("app.banner.this_site", note=context.source_note)
    return text


def calibration_legend(tr: Translator) -> ui.Tag:
    return ui.card(
        ui.card_header(tr("app.legend.title")),
        ui.tags.ul(
            *[
                ui.tags.li(tier_badge(tier, tr), tr(f"app.legend.{tier.value}"))
                for tier in (Tier.A, Tier.B, Tier.C, Tier.D)
            ],
            style="list-style:none;padding-left:0;",
        ),
        ui.p(ui.tags.small(tr("app.legend.note"))),
    )


def window_label(window: tuple[int, int], tr: Translator) -> str:
    """Render a cultivation window as months.

    "months 10-6" reads as a typo. A window whose end month precedes its start month
    wraps the year boundary, and saying so is the difference between a user reading a
    backwards range and reading an over-winter deployment.
    """
    start, end = window
    span = tr("app.window.span", start=tr(f"app.month.{start}"), end=tr(f"app.month.{end}"))
    return tr("app.window.over_winter", span=span) if end < start else span
```

- [ ] **Step 4: Rewrite `app/modules/user_mode.py`**

```python
"""User mode - the four entry points of specification section 4.

The specification describes "one engine, four doors". Implemented as a mode selector
over a single workflow rather than four parallel copies of it: the door sets
vocabulary and defaults, never capability (design rule 1), so a community user who
wants the nitrogen figure still gets it.

The taxonomy is KU's hypothesis. Decision D9: validate it against the A2.2 stakeholder
findings (D2.1, M12) before building it out further.

`MODES` holds identifiers only; the words a door uses are catalogue keys
`app.mode.<door>.{title,audience,question}` (package I).
"""

from __future__ import annotations

from shiny import module, reactive, render, ui

from app.i18n import Translator

MODES: dict[str, dict] = {
    "plan": {"scale": "community_farm_1_ha", "register": "aggregate"},
    "farm": {"scale": "community_farm_0_1_ha", "register": "operational"},
    "start": {"scale": "mini_farm_kit", "register": "plain"},
    "explore": {"scale": "community_farm_0_1_ha", "register": "technical"},
}


def mode_choices(tr: Translator) -> dict[str, str]:
    return {
        key: tr(
            "app.mode.choice", title=tr(f"app.mode.{key}.title"), audience=tr(f"app.mode.{key}.audience")
        )
        for key in MODES
    }


def mode_question_tag(mode: str, tr: Translator) -> ui.Tag:
    """Pure: the door's question. Named `_tag` because the render function below must be
    called `mode_question` - Shiny binds an output by its function's name."""
    return ui.help_text(ui.tags.em(tr(f"app.mode.{mode}.question")))


@module.ui
def user_mode_ui(tr: Translator) -> ui.TagList:
    return ui.TagList(
        ui.input_select("mode", tr("app.mode.label"), choices=mode_choices(tr), selected="farm"),
        ui.output_ui("mode_question"),
    )


@module.server
def user_mode_server(input, output, session, state) -> None:  # noqa: A002
    @reactive.effect
    @reactive.event(input.mode)
    def _sync_mode():
        mode = input.mode()
        state.user_mode.set(mode)
        # The door sets the DEFAULT scale. It does not lock it: the user can still
        # change scale in Catalogue, because the door governs vocabulary, not capability.
        state.scale.set(MODES[mode]["scale"])

    @output
    @render.ui
    def mode_question():
        return mode_question_tag(state.user_mode.get(), state.translator())
```

- [ ] **Step 5: Rewrite `app/modules/report.py`**

```python
"""Report panel - the assessment as text, with its caveats attached.

The report carries the site label and the caveats, because a table of numbers that
outlives the screen it was read on is exactly where a caveat gets lost.

`today` is a parameter for the same reason `regulatory.py` makes it one: the test suite
must not turn red on a calendar boundary. `tr` defaults to English so the core-style
call `render_report(assessment, today=...)` still reads as it always did.
"""

from __future__ import annotations

import json
from datetime import date

from shiny import module, render, ui

from app.i18n import Translator, english
from seagarden_dst import CAVEAT_LABELS, Verdict, __version__
from seagarden_dst.calibration import for_display
from seagarden_dst.forcing import Coverage, ForcingChoice

from ._widgets import artifact_source_text


def render_report(
    assessment, choice: ForcingChoice | None = None, *, today: date, tr: Translator | None = None
) -> str:
    tr = tr or english()
    if assessment is None:
        return tr("app.report.none")

    context = assessment.context
    if context.conditions is None:
        conditions_line = tr("app.report.conditions_unavailable")
    else:
        c = context.conditions
        conditions_line = tr(
            "app.report.conditions",
            salinity=f"{c.salinity_psu:g}", din=f"{c.din_umol_l:g}", depth=f"{c.depth_m:g}",
        )
    lines = [
        tr("app.report.heading"),
        "=" * 52,
        "",
        tr("app.report.site", site=context.label or context.region),
        tr("app.report.subregion", region=context.region),
        conditions_line,
        tr("app.report.confidence", confidence=tr.confidence_label(context.confidence)),
        _data_source_line(choice, context, tr),
        tr("app.report.generated", date=today.isoformat(), version=__version__),
        "",
        tr("app.report.ranked"),
        "-" * 52,
    ]

    if assessment.unassessable:
        lines.append(tr("app.report.unassessed", reason=_unassessed_reason(assessment, tr)))
    elif not assessment.ranked:
        lines.append(tr("app.report.none_assessed"))
    for option in assessment.ranked:
        lines += [
            "",
            tr(
                "app.report.option",
                species=tr.species_name(option.species_key),
                method=tr.method_name(option.method_key),
                ha=f"{option.area_m2 / 10_000:.4g}",
            ),
            tr("app.report.verdict", verdict=Verdict(option.verdict).label),
            tr("app.report.binding", binding=option.binding_constraint),
            tr("app.report.harvest", harvest=tr.quantity(for_display(option.harvest))),
        ]
        if option.nitrogen is not None:
            lines += [
                tr("app.report.nitrogen", value=tr.quantity(for_display(option.nitrogen))),
                tr("app.report.phosphorus", value=tr.quantity(for_display(option.phosphorus))),
                tr("app.report.carbon", value=tr.quantity(for_display(option.carbon))),
            ]
        lines.append(
            tr("app.report.calibration", label=option.tier.label, presentation=option.tier.presentation)
        )

    if assessment.excluded:
        lines += ["", tr("app.report.excluded"), "-" * 52]
        lines += [
            tr("app.report.excluded_line", key=k, reason=v) for k, v in assessment.excluded.items()
        ]

    if assessment.pressure:
        lines += ["", tr("app.report.pressure"), "-" * 52]
        lines += [
            tr("app.report.p_top", state=s, p=f"{p:.3f}") for s, p in assessment.pressure.items()
        ]
        if assessment.pressure_note is not None:
            lines.append(tr("app.report.pressure_note", note=assessment.pressure_note))

    lines += ["", tr("app.report.caveats"), "-" * 52]
    for key, value in assessment.caveats.items():
        lines.append(tr("app.report.caveat_line", label=CAVEAT_LABELS.get(key, key), text=value))
    lines += [
        tr("app.report.carbon_caveat"),
        _data_source_caveat(choice, context, tr),
        tr("app.report.legal_caveat"),
        "",
        tr("app.report.footer"),
    ]
    return "\n".join(lines)


def _unassessed_reason(assessment, tr: Translator) -> str:
    if assessment.coverage is Coverage.CELL_INVALID:
        if assessment.nearest_valid_km is not None:
            return tr("app.report.unassessed.cell_invalid_near", km=f"{assessment.nearest_valid_km:.2f}")
        return tr("app.report.unassessed.cell_invalid")
    if assessment.coverage is Coverage.YEAR_ABSENT:
        return tr("app.report.unassessed.year_absent")
    return tr("app.report.unassessed.no_conditions")


def _data_source_line(choice: ForcingChoice | None, context, tr: Translator) -> str:
    if choice is not None:
        if choice.is_artifact:
            text = tr("app.report.source.artifact", source=artifact_source_text(choice, tr))
        else:
            text = tr("app.report.source.placeholder_reason", reason=choice.reason)
    elif context.from_artifact:
        text = tr("app.report.source.artifact_bare")
    else:
        text = tr("app.report.source.placeholder_bare")
    if context.source_note is not None:
        text += tr("app.report.source.this_site", note=context.source_note)
    return text


def _data_source_caveat(choice: ForcingChoice | None, context, tr: Translator) -> str:
    on_artifact = choice.is_artifact if choice is not None else context.from_artifact
    text = tr("app.report.caveat.artifact" if on_artifact else "app.report.caveat.placeholder")
    if context.source_note is not None:
        text += tr("app.report.caveat.this_site", note=context.source_note)
    return text


@module.ui
def report_ui(tr: Translator) -> ui.Tag:
    return ui.TagList(
        ui.card(
            ui.card_header(tr("app.report.title")),
            ui.download_button("download_txt", tr("app.report.download_txt"), class_="btn-sm"),
            ui.download_button("download_json", tr("app.report.download_json"), class_="btn-sm"),
            ui.output_code("report_text"),
        ),
    )


@module.server
def report_server(input, output, session, state) -> None:  # noqa: A002
    @output
    @render.code
    def report_text():
        return render_report(
            state.assessment.get(), state.forcing.get(), today=date.today(), tr=state.translator()
        )

    @render.download(filename=lambda: f"seagarden-dst-{date.today().isoformat()}.txt")
    def download_txt():
        yield render_report(
            state.assessment.get(), state.forcing.get(), today=date.today(), tr=state.translator()
        )

    @render.download(filename=lambda: f"seagarden-dst-{date.today().isoformat()}.json")
    def download_json():
        assessment = state.assessment.get()
        tr = state.translator()
        payload = {} if assessment is None else assessment.to_dict(render=tr.render)
        yield json.dumps(payload, indent=2, default=str)
```

The `Data confidence:` line previously printed `context.confidence` raw (`low`); `tr.confidence_label("low")` is `"low"` in English, so the golden holds.

- [ ] **Step 6: Convert `app/modules/catalogue.py`**

Imports: `from app.i18n import Translator` and `from seagarden_dst import DEFAULT_SCALE, SCALE_LABELS, default_parameters`. Replace `SPECIES_CHOICES` with a function and keep `AF_SPECIES`:

```python
PARAMS = default_parameters()
AF_SPECIES = [k for k, v in PARAMS.species.items() if v.in_application_form]


def species_choices(tr: Translator) -> dict[str, str]:
    return {k: tr.species_name(k) for k in PARAMS.species}


def scale_choices(tr: Translator) -> dict[str, str]:
    return {k: tr.render(v) for k, v in SCALE_LABELS.items()}
```

`catalogue_ui(tr: Translator)`: the checkbox group takes `tr("app.catalogue.species")` and `choices=species_choices(tr)`, `selected=list(PARAMS.species)`; the select takes `tr("app.catalogue.scale")`, `choices=scale_choices(tr)`, `selected=DEFAULT_SCALE`; the link `tr("app.catalogue.only_af")`; the card headers `tr("app.catalogue.species")` and `tr("app.catalogue.methods")`.

Extract the two tables as pure functions and have the server delegate:

```python
def species_table(tr: Translator) -> ui.TagList:
    rows = []
    for key, species in PARAMS.species.items():
        named = tr("app.catalogue.yes" if species.in_application_form else "app.catalogue.no")
        rows.append(
            ui.tags.tr(
                ui.tags.td(ui.tags.b(tr.species_name(key))),
                ui.tags.td(ui.tags.em(species.scientific_name)),
                ui.tags.td(tr.group_label(species.group)),
                ui.tags.td(named),
                ui.tags.td(window_label(species.cultivation_window, tr)),
            )
        )
    headers = ("species", "scientific", "group", "in_af", "window")
    return ui.TagList(
        ui.tags.table(
            ui.tags.thead(
                ui.tags.tr(
                    *[
                        ui.tags.th(tr(f"app.catalogue.col.{h}"), style="text-align:left;padding-right:1rem;")
                        for h in headers
                    ]
                )
            ),
            ui.tags.tbody(*rows),
            style="width:100%;font-size:.92em;",
        ),
        ui.p(ui.tags.small(tr("app.catalogue.species_note"))),
    )


def method_table(tr: Translator) -> ui.TagList:
    rows = [
        ui.tags.tr(
            ui.tags.td(ui.tags.b(tr.method_name(key))),
            ui.tags.td(tr.method_field(key, "anchoring_unit")),
            ui.tags.td(tr.method_field(key, "cultivation_unit")),
            ui.tags.td(f"{m.min_depth_m:g}-{m.max_depth_m:g} m"),
            ui.tags.td(f"{m.max_significant_wave_m:g} m"),
            ui.tags.td(f"{m.area_m2_per_unit:g} m²"),
        )
        for key, m in PARAMS.methods.items()
    ]
    headers = ("method", "anchoring", "cultivation", "depth", "max_wave", "unit_area")
    return ui.TagList(
        ui.tags.table(
            ui.tags.thead(
                ui.tags.tr(
                    *[
                        ui.tags.th(tr(f"app.catalogue.col.{h}"), style="text-align:left;padding-right:1rem;")
                        for h in headers
                    ]
                )
            ),
            ui.tags.tbody(*rows),
            style="width:100%;font-size:.92em;",
        ),
        ui.p(ui.tags.small(tr("app.catalogue.methods_note"))),
    )
```

In `catalogue_server`, the two `@render.ui` bodies become `return species_table(state.translator())` and `return method_table(state.translator())`. Delete the old `SPECIES_CHOICES` constant and its import of `window_label` stays (now called with `tr`).

- [ ] **Step 7: Convert `app/modules/results.py`**

Imports: `from app.i18n import Translator`; `from seagarden_dst import CAVEAT_LABELS, Verdict, assess_site, removal_framing`. `results_ui(tr: Translator)`: card headers `tr("app.results.ranked")`, `tr("app.results.excluded")`, `tr("app.results.pressure")`, `calibration_legend(tr)`.

Pure renderers (module level), the server's three `@render.ui` bodies become one-liners delegating to them with `state.assessment.get()` and `state.translator()`:

```python
def render_ranking(assessment, tr: Translator) -> ui.Tag:
    if assessment is None:
        return ui.p(tr("app.results.pick_site"), style="opacity:.7;")
    if assessment.unassessable:
        return ui.p(tr("app.results.unassessed"), style="opacity:.7;")
    if not assessment.ranked:
        return ui.p(tr("app.results.none"))

    columns = ("option", "verdict", "harvest", "nitrogen", "phosphorus", "carbon")
    head = ui.tags.tr(
        *[
            ui.tags.th(tr(f"app.results.col.{c}"), style="text-align:left;padding:.3rem 1rem .3rem 0;")
            for c in columns
        ]
    )
    rows = []
    for option in assessment.ranked:
        rows.append(
            ui.tags.tr(
                ui.tags.td(
                    ui.tags.b(tr.species_name(option.species_key)),
                    ui.tags.br(),
                    ui.tags.small(tr.method_name(option.method_key), style="opacity:.7;"),
                ),
                ui.tags.td(verdict_pill(option.verdict, tr)),
                ui.tags.td(quantity(option.harvest, tr)),
                ui.tags.td(quantity(option.nitrogen, tr)),
                ui.tags.td(quantity(option.phosphorus, tr)),
                ui.tags.td(quantity(option.carbon, tr)),
                style="border-top:1px solid rgba(128,128,128,.25);",
            )
        )
        rows.append(
            ui.tags.tr(
                ui.tags.td(
                    ui.tags.details(
                        ui.tags.summary(ui.tags.small(tr.render(option.binding_constraint))),
                        ui.tags.ul(
                            *[
                                ui.tags.li(
                                    ui.tags.small(
                                        tr(
                                            "app.results.constraint_line",
                                            name=name, verdict=Verdict(verdict).label, reason=reason,
                                        )
                                    )
                                )
                                for name, verdict, reason in option.constraints
                            ]
                        ),
                    ),
                    colspan="6",
                    style="padding-bottom:.5rem;",
                )
            )
        )

    caveats = assessment.caveats
    caveat_block = (
        [
            ui.tags.div(
                ui.tags.b(tr("app.results.caveats")),
                ui.tags.ul(
                    *[
                        ui.tags.li(tr("app.results.caveat_line", label=CAVEAT_LABELS.get(k, k), text=v))
                        for k, v in caveats.items()
                    ]
                ),
                style="margin-top:.75rem;font-size:.9em;",
            )
        ]
        if caveats
        else []
    )
    return ui.TagList(
        ui.tags.table(ui.tags.thead(head), ui.tags.tbody(*rows), style="width:100%;"),
        *caveat_block,
    )


def render_excluded(assessment, tr: Translator) -> ui.Tag:
    if assessment is None:
        return ui.p(tr("app.results.dash"), style="opacity:.7;")
    if not assessment.excluded:
        return ui.p(tr("app.results.nothing_excluded"), style="opacity:.7;")
    # Exclusions are shown with their reason, not silently dropped: "why can't I
    # grow kelp here" is one of the questions the tool exists to answer.
    return ui.tags.ul(
        *[
            # The raw species key, as before: the excluded dict is keyed by identifier and
            # English never showed the common name here, so the seam must not either.
            ui.tags.li(ui.tags.b(key), ": ", tr.render(reason))
            for key, reason in assessment.excluded.items()
        ]
    )


def render_pressure(assessment, tr: Translator) -> ui.Tag:
    if assessment is None:
        return ui.p(tr("app.results.dash"), style="opacity:.7;")
    if not assessment.pressure:
        note = assessment.pressure_note
        return ui.p(
            tr.render(note) if note is not None else tr("app.results.no_bowtie"), style="opacity:.7;"
        )
    items = [
        ui.tags.li(tr("app.results.p_top", state=state_, p=f"{p:.3f}"))
        for state_, p in assessment.pressure.items()
    ]
    framing = removal_framing(assessment.pressure)
    return ui.TagList(
        ui.tags.ul(*items),
        ui.p(tr.render(framing) if framing is not None else ""),
        ui.p(ui.tags.small(tr.render(assessment.pressure_note) if assessment.pressure_note else "")),
    )
```

The old `binding_constraint or "All constraints pass"` fallback is gone: `explain()` always returns a message (`suitability.explain.no_binding` when nothing binds), so `app.results.all_pass` is unused — **delete that key from `app/locales/en.yaml`**.

- [ ] **Step 8: Convert `app/modules/site.py`**

Imports: `from app.i18n import Translator`. `site_markers(tr: Translator)`: `"name": tr.render(REGIONS[region])`, `"provenance_label": tr.render(coordinate.provenance.label)`, `"presentation": tr.render(coordinate.provenance.presentation)`, `"depth": tr("app.site.depth_unknown") if coordinate.depth_m is None else f"{coordinate.depth_m:g} m"`. `_widget(tr)` builds the tooltip as `f"<b>{{name}}</b><br/>{{provenance_label}}<br/>{tr('app.site.tooltip_depth')} {{depth}}<br/><i>{{presentation}}</i>"` (the doubled braces are deck.gl's runtime template, not Python's). `_legend(tr)`: `ui.tags.small(tr.render(provenance.label))`.

New pure helpers:

```python
def absent_regions_note(tr: Translator) -> str:
    absent = regions_without_a_position()
    if not absent:
        return ""
    names = tr("app.site.and").join(tr.render(REGIONS[r]) for r in absent)
    key = "app.site.help_absent_one" if len(absent) == 1 else "app.site.help_absent_many"
    return tr(key, regions=names)


def render_position_note(region: str, tr: Translator) -> ui.Tag:
    coordinate = SITE_COORDINATES.get(region)
    if coordinate is None:
        return ui.p(ui.tags.small(tr("app.site.no_position", region=REGIONS[region])))
    return ui.p(
        ui.tags.small(
            tr(
                "app.site.position",
                lat=f"{coordinate.lat:.4f}", lon=f"{coordinate.lon:.4f}",
                provenance=tr.render(coordinate.provenance.label).lower(),
                presentation=coordinate.provenance.presentation,
            )
        )
    )


def render_conditions(region: str, tr: Translator) -> ui.TagList:
    c = SiteContext.from_region(region).conditions
    rows = [
        (tr("app.site.cond.salinity"), f"{c.salinity_psu:g} psu"),
        (tr("app.site.cond.mean_temp"), f"{c.mean_temp_c:g} °C"),
        (tr("app.site.cond.summer_winter"), f"{c.summer_temp_c:g} / {c.winter_temp_c:g} °C"),
        (tr("app.site.cond.din"), f"{c.din_umol_l:g} µmol/L"),
        (tr("app.site.cond.dip"), f"{c.dip_umol_l:g} µmol/L"),
        (tr("app.site.cond.depth"), f"{c.depth_m:g} m"),
        (tr("app.site.cond.wave"), f"{c.significant_wave_m:g} m"),
        (tr("app.site.cond.par"), f"{c.par_at_depth():.0f} µmol photons/m²/s"),
    ]
    return ui.TagList(
        ui.tags.table(
            ui.tags.tbody(
                *[
                    ui.tags.tr(
                        ui.tags.td(k, style="padding:.15rem .9rem .15rem 0;opacity:.75;"),
                        ui.tags.td(v, style="padding:.15rem 0;font-variant-numeric:tabular-nums;"),
                    )
                    for k, v in rows
                ]
            ),
            style="width:100%;",
        ),
        ui.p(
            ui.tags.small(
                tr("app.site.confidence_line", confidence=tr.confidence_label("low"), region=region)
            )
        ),
    )
```

`site_ui(tr: Translator)`: select label `tr("app.site.region")`, `choices={k: tr.render(v) for k, v in REGIONS.items()}`; help text `tr("app.site.help") + absent_regions_note(tr)`; text input `tr("app.site.label")` with `placeholder=tr("app.site.label_placeholder")`; button `tr("app.site.use")`; card headers `tr("app.site.where")`, `tr("app.site.conditions")`, `tr("app.site.provenance_card")`; the no-map markdown `ui.markdown(tr("app.site.no_map"))`; the provenance body `ui.markdown(tr("app.site.provenance_body"))`; `_widget(tr).ui(...)`, `_legend(tr)`.

`site_server`: `widget = _widget(english()) if map_is_available() else None` — the tooltip template is fixed at widget construction, before the session's language is known; make it `_widget(state.translator())` inside the first effect instead if `MapWidget` can be constructed there, otherwise accept an English tooltip label and record it in the CHANGELOG known-limits line. `_draw_markers` passes `data=site_markers(state.translator())`. `_set_site`: `label = (input.label() or "").strip() or state.translator().render(REGIONS[region])`. The two renderers delegate: `return render_position_note(input.region(), state.translator())`, `return render_conditions(input.region(), state.translator())`.

- [ ] **Step 9: Update the tests, run everything, commit**

`app/tests/test_app_smoke.py`: every direct call gains `english()` (import `from app.i18n import english`): `site_ui("site", english())` etc. in `test_every_panel_ui_renders` and `test_the_site_panel_renders_without_shiny_deckgl`; `headline_for(result, english())`; `data_source_banner(choice, None, english())` / `(choice, context, english())`; `tier_badge(Tier.D, english())`, `verdict_pill("unsuitable", english())`, `verdict_pill(Verdict.MARGINAL.value, english())`; `_markers()` → `site_markers(english())`; `scale_sentence(..., tr=english())`. `tests/test_report_golden.py`: no change (defaults to English).

Run: `MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest -q && micromamba run -n shiny ruff check . && git status --short tests/golden`
Expected: all pass; nothing under `tests/golden` modified — the English report is byte-identical (spec test 10).

```bash
git add app tests
git commit -m "feat(app): the page builds per request in the chosen language; every panel renders through the Translator (I-a)

Tasks 6 and 7 of the I-a plan, one commit: the shell defines the Translator's
journey and the panels are where it arrives, and app.py calls both.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 8: The guard tests — parity, hygiene, `literal` discipline, the pseudo-locale leak test, the gate

**Files:**
- Create: `tests/test_i18n_guards.py` (spec tests 1–5, 7)
- Create: `app/tests/test_i18n_leaks.py` (spec tests 6, 8)
- Modify: `app/tests/test_app_smoke.py` (the `t(` grep is gone; spec done-when 10)

**Interfaces:**
- Consumes: everything above. Produces no code; pins the invariants.

- [ ] **Step 1: Write the core-side guards**

```python
# tests/test_i18n_guards.py
"""Catalogue invariants (spec I§8 tests 1-5 and 7). Default selection; no Shiny."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
import yaml

from app.i18n import APP_LOCALES, PARAMS_LOCALES, params_reference_keys
from seagarden_dst.i18n import CORE_LOCALES, LANGUAGES, Catalogue, placeholders

REPO = Path(__file__).resolve().parents[1]
OWNERS = {"core": CORE_LOCALES, "app": APP_LOCALES, "params": PARAMS_LOCALES}
KEY = re.compile(r"^[a-z][a-z0-9_]*(\.[A-Za-z0-9_-]+)+$")


def _files(root: Path) -> list[Path]:
    return sorted(root.glob("*.yaml")) if root.is_dir() else []


def _messages(path: Path) -> dict[str, str]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))["messages"]


def _reference(owner: str) -> dict[str, str]:
    if owner == "params":
        return params_reference_keys()
    return _messages(OWNERS[owner] / "en.yaml")


@pytest.mark.parametrize("owner", sorted(OWNERS))
def test_1_every_language_file_has_exactly_the_english_keys(owner):
    reference = set(_reference(owner))
    for path in _files(OWNERS[owner]):
        if path.stem == "en":
            continue
        keys = set(_messages(path))
        missing, extra = sorted(reference - keys), sorted(keys - reference)
        assert not missing and not extra, f"{path}: missing {missing}, extra {extra}"


def test_2_prefixes_are_owned_and_no_key_lives_in_two_files():
    seen: dict[str, str] = {}
    for owner, root in OWNERS.items():
        for path in _files(root):
            for key in _messages(path):
                assert KEY.match(key), f"{path}: {key!r} is not a dotted lower-case key"
                first = key.split(".")[0]
                if owner == "app":
                    assert first == "app", f"{path}: {key!r} does not belong to the app"
                elif owner == "params":
                    assert first == "params", f"{path}: {key!r} does not belong to params"
                else:
                    assert first not in {"app", "params"}, f"{path}: {key!r} is not a core key"
                other = seen.setdefault(key, owner)
                assert other == owner, f"{key!r} appears in both {other} and {owner}"


def test_3_every_sidecar_covers_the_params_tree_and_nothing_stale():
    reference = params_reference_keys()
    for path in _files(PARAMS_LOCALES):
        keys = set(_messages(path))
        assert keys == set(reference), f"{path}: {sorted(keys ^ set(reference))}"


@pytest.mark.parametrize("owner", sorted(OWNERS))
def test_4_catalogue_hygiene(owner):
    reference = _reference(owner)
    ref_placeholders = {k: placeholders(v) for k, v in reference.items()}
    for path in _files(OWNERS[owner]):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert data["language"] == path.stem
        assert data["status"] in {"reference", "machine-draft", "reviewed"}
        if data["status"] != "reference":
            assert data.get("translated_by"), f"{path}: translated_by missing"
        for key, value in data["messages"].items():
            assert not key.endswith(("_one", "_other")), f"{key}: no plural forms (I§7)"
            for name in placeholders(value):
                assert ":" not in name and "!" not in name, f"{path}: {key} has a format spec"
            if key in ref_placeholders:
                assert placeholders(value) == ref_placeholders[key], (
                    f"{path}: {key} placeholders differ from English"
                )


def test_4b_every_english_key_is_used_somewhere():
    """A key nobody renders is a sentence nobody reviews; delete it or use it."""
    source = "".join(
        p.read_text(encoding="utf-8")
        for p in list((REPO / "src").rglob("*.py")) + list((REPO / "app").rglob("*.py"))
        if "__pycache__" not in p.parts and p.parts[-2] != "tests"
    )
    for owner in ("core", "app"):
        for key in _reference(owner):
            # Coarse on purpose: many sites build the tail with an f-string
            # (`f"calibration.tier.{self.value}.label"`), so the first two segments are
            # what a literal in the source is guaranteed to carry. Catches a whole family
            # nobody renders; a single dead key inside a live family it cannot see.
            family = ".".join(key.split(".")[:2])
            assert f'"{family}' in source or f"'{family}" in source, (
                f"{owner} key {key!r}: nothing references the family {family!r}"
            )


def test_5_literal_appears_only_where_the_spec_allows():
    """`Message.literal(` is for data and engine messages, never for app chrome (I§4.1)."""
    allowed = {
        ("src/seagarden_dst/calibration.py", "caveat"),
        ("src/seagarden_dst/suitability.py", "assess_physical"),
        ("src/seagarden_dst/suitability.py", "assess"),
        ("src/seagarden_dst/api.py", "assess_site"),
    }
    found = set()
    for path in sorted((REPO / "src").rglob("*.py")) + sorted((REPO / "app").rglob("*.py")):
        if "__pycache__" in path.parts or path.parts[-2] == "tests":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                for call in ast.walk(node):
                    if (
                        isinstance(call, ast.Call)
                        and isinstance(call.func, ast.Attribute)
                        and call.func.attr == "literal"
                        and isinstance(call.func.value, ast.Name)
                        and call.func.value.id == "Message"
                    ):
                        found.add((path.relative_to(REPO).as_posix(), node.name))
    assert found <= allowed, f"unlisted Message.literal sites: {sorted(found - allowed)}"
    assert not any(f.startswith("app/") for f, _ in found)


def test_7_one_chooser_drives_both_halves():
    """`language_for` is the only place a query string or Accept-Language is parsed."""
    shell = (REPO / "app" / "app.py").read_text(encoding="utf-8")
    assert "language_for(" in shell
    for path in sorted((REPO / "app").rglob("*.py")):
        if path.name in {"i18n.py", "app.py"} or path.parts[-2] == "tests":
            continue
        text = path.read_text(encoding="utf-8")
        assert "accept-language" not in text.lower() and "query_params" not in text, (
            f"{path}: parses the request itself; use language_for"
        )


def test_languages_constant_matches_the_endonym_table():
    from app.i18n import LANGUAGE_NAMES

    assert tuple(LANGUAGE_NAMES) == LANGUAGES
```

- [ ] **Step 2: Write the leak test and the gate test**

```python
# app/tests/test_i18n_leaks.py
"""Spec I§8 test 6 (the pseudo-locale leak test) and test 8 (the gate).

Every text node of every render under language `xx` must be a `⟦key⟧` marker, a
number, a unit, a Latin name, an identifier or an allowlisted proper noun. Anything
else is a sentence that bypassed the seam - whether or not it ever entered a
catalogue, which is why this is stronger than checking the English values are absent.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from html.parser import HTMLParser

import pytest

from app.i18n import LANGUAGE_NAMES, Translator, enabled_languages
from app.modules._widgets import calibration_legend, data_source_banner, headline_for
from app.modules.report import render_report
from app.modules.results import render_excluded, render_pressure, render_ranking, run_assessment
from app.modules.site import render_conditions, render_position_note, site_markers
from app.modules.user_mode import mode_question_tag
from app.shell import about_modal, feedback_modal, help_modal
from app.tests.test_app_smoke import _FakeState
from seagarden_dst import PLACEHOLDER_SITES, REGIONS, SiteContext, default_parameters
from seagarden_dst.bowtie_adapter import TOP_EVENT_STATES
from seagarden_dst.forcing import DEFAULT_FORCING, ForcingChoice

XX = Translator.pseudo()
PARAMS = default_parameters()

MARKER = re.compile(r"⟦[^⟧]*⟧")
NUMBER = re.compile(r"[-+]?\d[\d.,]*(?:e[-+]?\d+)?%?")
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
VERSION = re.compile(r"v\d[\w.]*|v\*")
URL = re.compile(r"https?://\S+|\S+@\S+\.\w+|mailto:\S+")
ALLOWED_TOKENS = {
    # units and symbols (I§7)
    "psu", "m", "ha", "kg", "t", "DW", "FW", "N", "P", "C", "CO2", "km", "°C", "µmol/L",
    "umol/L", "µmol", "photons/m²/s", "m²", "m2", "/", "-", "–", "—", "·", "=", "(", ")", "[", "]",
    "|", ":", ";", ",", ".", "×", "x", "%", "&", "✓", "*",
    # tiers, verdict identifiers (CSS class text never shows; the value does in the badge)
    "A", "B", "C", "D",
    # brand and programme proper nouns
    "Sea", "Garden", "SeaGarden", "DST", "Interreg", "South", "Baltic", "European", "Union",
    "KU", "MRI", "OLAMUR", "EUTROPY", "MARBEFES", "WP2", "WP3", "A2.3", "D2.2", "STHB.02.02-IP.01-0006/25",
    # bow-tie states are engine data
    *TOP_EVENT_STATES,
    # language endonyms in the menu
    *LANGUAGE_NAMES.values(),
    # identifiers that are legitimately shown raw
    *REGIONS, *PARAMS.species, *PARAMS.methods,
    # Latin names, word by word
    *{w for s in PARAMS.species.values() for w in s.scientific_name.split()},
}


class _Text(HTMLParser):
    """Collects text nodes plus the attributes a user can read."""

    def __init__(self):
        super().__init__()
        self.chunks: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("style", "script"):
            self._skip += 1
        for name, value in attrs:
            if name in ("title", "alt", "placeholder", "aria-label") and value:
                self.chunks.append(value)

    def handle_endtag(self, tag):
        if tag in ("style", "script"):
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self.chunks.append(data)


#: The one permitted category of English under `xx`: text the FRAMEWORK emits, not us.
#: Each entry names its origin. Verify the exact strings on the first run; do not guess.
FRAMEWORK_STRINGS = {
    "Close",              # Bootstrap modal close button aria-label
    "Toggle navigation",  # Bootstrap navbar toggler aria-label
    "Toggle sidebar",     # bslib sidebar collapse aria-label
}
#: The draft banner is bilingual BY DESIGN (I§6): the English sentence beside the
#: translated one is required, so it is stripped before the leak scan, exactly once.
ENGLISH_DRAFT_BANNER = Translator.for_language("en")("app.shell.draft_banner")


def _leaks(text: str) -> list[str]:
    out = []
    for chunk in text.split("\n"):
        stripped = chunk.replace(ENGLISH_DRAFT_BANNER, " ")
        if stripped.strip() in FRAMEWORK_STRINGS:
            continue
        for pattern in (MARKER, URL, DATE, VERSION, NUMBER):
            stripped = pattern.sub(" ", stripped)
        for token in stripped.split():
            if token.strip("().,;:[]*|") in ALLOWED_TOKENS or not re.search(r"[A-Za-z]", token):
                continue
            out.append(f"{token!r} in {chunk.strip()[:80]!r}")
    return out


def _html_text(tag) -> str:
    parser = _Text()
    parser.feed(str(tag))
    return "\n".join(c for c in parser.chunks if c.strip())


def _artifact_choice() -> ForcingChoice:
    # An artifact-kind choice with no reason: `reason` is an operator diagnostic that
    # stays English by design (I§7), so it is exercised separately below.
    return ForcingChoice(
        source=DEFAULT_FORCING, kind="artifact", reason="", year=2025,
        built_on=datetime(2026, 9, 22, tzinfo=UTC), directory=None,
    )


def _assessment(region: str):
    state = _FakeState(SiteContext.from_region(region, label="Melnrage"))
    state.forcing.set(_artifact_choice())
    state.bowtie_inference.set({"Low": 0.2, "Moderate": 0.3, "High": 0.5})
    run_assessment(state)
    return state.assessment.get()


def test_6_the_whole_page_has_no_untranslated_text():
    from app.app import build_ui

    leaks = _leaks(_html_text(build_ui("xx")))
    assert not leaks, "\n".join(leaks)


@pytest.mark.parametrize("region", sorted(PLACEHOLDER_SITES))
def test_6_every_render_has_no_untranslated_text(region):
    assessment = _assessment(region)
    rendered = [
        _html_text(render_ranking(assessment, XX)),
        _html_text(render_excluded(assessment, XX)),
        _html_text(render_pressure(assessment, XX)),
        _html_text(render_conditions(region, XX)),
        _html_text(render_position_note(region, XX)),
        _html_text(calibration_legend(XX)),
        _html_text(mode_question_tag("farm", XX)),
        headline_for(assessment, XX)[1],
        data_source_banner(_artifact_choice(), assessment.context, XX),
        render_report(assessment, _artifact_choice(), today=date(2026, 9, 28), tr=XX),
    ]
    for modal in (about_modal, help_modal, feedback_modal):
        rendered.append(_html_text(modal(XX)))
    for marker in site_markers(XX):
        rendered.append(" ".join(str(v) for k, v in marker.items() if k not in ("position", "colour", "region", "provenance")))
    leaks = [leak for text in rendered for leak in _leaks(text)]
    assert not leaks, "\n".join(leaks)


def test_6_the_empty_and_unassessable_states_have_no_untranslated_text():
    from seagarden_dst.api import assess_site
    from seagarden_dst.forcing import Aggregation, Coverage, SiteReading

    blocked = SiteReading(
        conditions=None, coverage=Coverage.CELL_INVALID, year=2024,
        aggregation=Aggregation.CONTAINING_CELL, nearest_valid_km=1.1, from_artifact=True,
    )
    unassessable = assess_site(SiteContext.from_reading(blocked, label="Off-grid"))
    texts = [
        _html_text(render_ranking(None, XX)), _html_text(render_excluded(None, XX)),
        _html_text(render_pressure(None, XX)),
        render_report(None, today=date(2026, 9, 28), tr=XX),
        _html_text(render_ranking(unassessable, XX)),
        headline_for(unassessable, XX)[1],
        render_report(unassessable, _artifact_choice(), today=date(2026, 9, 28), tr=XX),
    ]
    leaks = [leak for text in texts for leak in _leaks(text)]
    assert not leaks, "\n".join(leaks)


def test_the_placeholder_reason_is_the_only_english_in_the_placeholder_banner():
    from seagarden_dst.forcing import placeholder_choice

    banner = data_source_banner(placeholder_choice("REASON-TOKEN"), None, XX)
    assert banner == "⟦app.banner.placeholder⟧", banner  # the reason sits inside the keyed sentence


def test_8_a_draft_language_is_hidden_unless_the_deployment_shows_drafts():
    def status(language):
        return {"de": "machine-draft"}.get(language)

    from app.i18n import language_for

    hidden = enabled_languages(env={}, status=status)
    assert "de" not in hidden
    assert language_for("?lang=de", "de", hidden) == "en"
    shown = enabled_languages(env={"SEAGARDEN_SHOW_DRAFT_LANGUAGES": "1"}, status=status)
    assert "de" in shown and language_for("?lang=de", None, shown) == "de"
```

Expect the first run of test 6 to list leaks: that list is the work of this task. Each leak is fixed by giving the string a key (Task 7's pattern) or, for an identifier/unit/proper noun, by adding it to `ALLOWED_TOKENS` with a one-word justification comment. **Do not add an English sentence fragment to `ALLOWED_TOKENS`**; that is the failure the test exists to catch. The single exception is `FRAMEWORK_STRINGS`: attribute text Bootstrap or bslib emits on its own (a modal's close button, the navbar toggler), each entry with its origin in a comment.

- [ ] **Step 3: Retire the `t(` grep**

`grep -rn "def t(\|[^a-z_]t(\"" app` must be empty. Add to `app/tests/test_app_smoke.py`:

```python
def test_the_english_passthrough_seam_is_gone():
    """`t()` was the identity; the Translator replaced it (spec done-when 10)."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts or path.parts[-2] == "tests":
            continue
        assert "def t(" not in path.read_text(encoding="utf-8"), f"{path} still defines t()"
```

- [ ] **Step 4: Run the suite until the leak list is empty, then commit**

Run: `MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest -q && micromamba run -n shiny ruff check . && git status --short tests/golden`
Expected: all pass; goldens untouched.

```bash
git add tests/test_i18n_guards.py app/tests/test_i18n_leaks.py app/tests/test_app_smoke.py app src
git commit -m "test(i18n): key parity, hygiene, literal discipline, the pseudo-locale leak test, the gate (I-a)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 9: README, CHANGELOG, deploy runbook, the review-sheet script, and the spec touch-ups

**Files:**
- Create: `scripts/i18n_review_sheet.py`
- Modify: `README.md` (Layout block; new *Languages* section before *Testing*), `CHANGELOG.md` (`[Unreleased]`), `docs/runbooks/deploy.md` (environment variables), `docs/superpowers/specs/2026-09-28-package-i-internationalisation-design.md` (I§4.1, I§8)
- Test: `tests/test_i18n_guards.py` (one test for the script)

- [ ] **Step 1: The review sheet**

```python
# scripts/i18n_review_sheet.py
"""One markdown table per language for a partner reviewer (design I§5.4).

    micromamba run -n shiny python scripts/i18n_review_sheet.py de > review-de.md

Merges the three catalogues with the English beside each row. A convenience for the
reviewer, not a source of truth: the YAML files are. Never writes back.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from app.i18n import APP_LOCALES, PARAMS_LOCALES, params_reference_keys  # noqa: E402
from seagarden_dst.i18n import CORE_LOCALES  # noqa: E402


def _messages(root: Path, language: str) -> dict[str, str]:
    path = root / f"{language}.yaml"
    if not path.is_file():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8"))["messages"]


def sheet(language: str) -> str:
    rows = [f"# Review sheet — {language}", "", "| Key | English | " + language + " |", "|---|---|---|"]
    for owner, root in (("core", CORE_LOCALES), ("app", APP_LOCALES)):
        english = _messages(root, "en")
        other = _messages(root, language)
        for key in sorted(english):
            rows.append(f"| `{key}` | {_cell(english[key])} | {_cell(other.get(key, ''))} |")
    other = _messages(PARAMS_LOCALES, language)
    for key, english_text in sorted(params_reference_keys().items()):
        rows.append(f"| `{key}` | {_cell(english_text)} | {_cell(other.get(key, ''))} |")
    return "\n".join(rows) + "\n"


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", "<br>")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: i18n_review_sheet.py <language>")
    sys.stdout.write(sheet(sys.argv[1]))
```

Append to `tests/test_i18n_guards.py`:

```python
def test_the_review_sheet_lists_every_key_with_its_english():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "sheet", REPO / "scripts" / "i18n_review_sheet.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    text = module.sheet("de")
    for key in list(_reference("core"))[:3] + list(_reference("app"))[:3]:
        assert f"`{key}`" in text
    assert "`params.methods.raft.name` | Raft |" in text
```

- [ ] **Step 2: README**

In the Layout block add, under `app/`: `  i18n.py                 Translator: one per language, chosen per request from ?lang=` and `  locales/                app chrome, one YAML per language (en is the reference)`; under `src/seagarden_dst/`: `  i18n.py                 Message and Catalogue — the core's prose, keyed (package I)` and `  locales/                the core's catalogues, shipped in the wheel`; under `params/`: `  i18n/                   translations of species/method names and calibration notes`.

New section before `## Testing`:

```markdown
## Languages

The tool is built to speak English, German, Polish, Danish, Lithuanian and Swedish
(`de`, `pl`, `da`, `lt`, `sv`). English is the reference and the fallback. A user picks a
language from the navbar menu, which reloads the page with `?lang=xx`; a first visit
follows the browser's `Accept-Language`.

**A language is live only after a native speaker has reviewed it.** Each language has three
catalogue files — `src/seagarden_dst/locales/<lang>.yaml` (what the model says),
`app/locales/<lang>.yaml` (the app's chrome) and `params/i18n/<lang>.yaml` (species and
method names, calibration notes) — and each carries a `status:` header. The menu shows a
language when all three say `reviewed`, naming the reviewer and the date. Until then the
deployment can show drafts for a review round with `SEAGARDEN_SHOW_DRAFT_LANGUAGES=1`, under
a bilingual "machine translation, not yet reviewed" banner; `SEAGARDEN_LANGUAGES=en,de`
restricts the set. Numbers keep the decimal point and dates are ISO in every language.
How to review and enable a language: `docs/runbooks/translations.md` (package I-b).

The core stays readable from a notebook: every sentence it produces is a `Message`, and
`str(message)` is English. The JSON export writes each message as `{key, params, text}`.
```

- [ ] **Step 3: CHANGELOG, deploy runbook, spec**

`CHANGELOG.md` `[Unreleased]` under `### Added` (create the heading above I-0's `### Changed`):

```markdown
- **Package I-a — the internationalisation seam.** The core's prose is `Message`-valued
  (`seagarden_dst.i18n`), rendered from `locales/en.yaml`; the app builds its page per
  request in the language `?lang=` or `Accept-Language` asks for, through one `Translator`
  per language, and shows a language menu. English output is byte-identical (the report
  golden proves it) except the sidebar status sentence, now count-neutral. **Only English
  ships**: no other catalogue exists yet (package I-b), so the menu has one entry.
  **JSON export schema change:** every message field (`binding_constraint`, `constraints`,
  `excluded`, `caveats`, `pressure_note`, `site.source_note`) is now `{key, params, text}`
  rather than a string; quantities are unchanged. New environment variables
  `SEAGARDEN_LANGUAGES` and `SEAGARDEN_SHOW_DRAFT_LANGUAGES` (README, *Languages*).
  Known limit: the map tooltip's "Model depth" label is fixed at widget construction and
  may render in English if the widget cannot be built inside a reactive context.
```

`docs/runbooks/deploy.md`: in the service table row or a new paragraph beside the `Environment=` example the annual-refresh runbook shows (§10 there), add:

```markdown
Two optional variables govern languages (package I): `SEAGARDEN_LANGUAGES=en,de` restricts
the menu to those codes; `SEAGARDEN_SHOW_DRAFT_LANGUAGES=1` shows machine-draft catalogues
under a bilingual notice — for a partner review round on a staging instance, never on the
live one. Neither is set on laguna; the live instance shows English until a language is
reviewed (`docs/runbooks/translations.md`).
```

Spec touch-ups (`2026-09-28-package-i-internationalisation-design.md`): in I§4.1 add a bullet `**`Message.join(*parts)`** composes optional sentences (the adapters' notes) as one message with key `_join`; it renders its parts in the same language, separated by a space.`; in I§8 change `Test 6, 8 and 10 live in app/tests/test_i18n_app.py` to `Tests 6 and 8 live in app/tests/test_i18n_leaks.py; test 10 lives in tests/test_report_golden.py because --snapshot-update is registered in tests/conftest.py`; in I§5.2 add `The map tooltip's fixed label is the one string whose language may lag the session's, recorded as a known limit.`

- [ ] **Step 4: Run everything, commit, and check the done-when**

Run: `MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest -q && micromamba run -n shiny ruff check . && git status --short tests/golden`
Expected: all pass; goldens untouched.

Then spec I§11 clause 5, by hand:

```bash
MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -c "from seagarden_dst import assess_site, SiteContext; print({k: str(v) for k, v in assess_site(SiteContext.from_region('LT-coastal')).caveats.items()})"
```

Expected: readable English, e.g. `{'calibration': 'At least one option rests on literature priors ...'}`.

```bash
git add scripts/i18n_review_sheet.py README.md CHANGELOG.md docs/runbooks/deploy.md docs/superpowers/specs/2026-09-28-package-i-internationalisation-design.md tests/test_i18n_guards.py
git commit -m "docs(i18n): README Languages section, CHANGELOG, deploy variables, review sheet; spec touch-ups (I-a)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

I-a's done-when (spec I§11 clauses 5–10) is now met: the notebook prints English, tests 1–11 pass with no leak, `?lang=` renders an enabled language and falls to English otherwise, the report golden is byte-identical, `to_dict` emits `{key, params, text}`, and `def t(` is gone.

