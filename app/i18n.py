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
from functools import cache
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
    placeholders,
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
#: The only values that turn `ENV_SHOW_DRAFTS` on, compared stripped and lower-cased.
_SWITCH_ON = frozenset({"1", "true", "yes", "on"})

_GROUPS = ("macroalga", "shellfish")
_METHOD_FIELDS = ("name", "anchoring_unit", "cultivation_unit")


@cache
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


def _pseudo_mark(keys) -> dict[str, str]:
    return {k: f"⟦{k}⟧" for k in keys}


def _pseudo_mark_templates(messages: Mapping[str, str]) -> dict[str, str]:
    """`⟦key⟧` plus one ` {name}` per placeholder of the English template, names sorted
    for determinism - so a parameter that bypasses `tr` still shows up in the pseudo
    render instead of being swallowed by a template with no `{...}` of its own."""
    out: dict[str, str] = {}
    for key, template in messages.items():
        names = sorted(placeholders(template))
        out[key] = f"⟦{key}⟧" + "".join(f" {{{name}}}" for name in names)
    return out


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
    def for_language(cls, language: str) -> Translator:
        """The packaged catalogues for `language`, loaded once per process."""
        return _for_language(cls, language)

    @classmethod
    def pseudo(cls) -> Translator:
        """Language `xx`: every value is ⟦key⟧ plus the English template's placeholders,
        so an untranslated parameter leaks visibly. The leak test renders with this."""
        core_messages = core_catalogue(DEFAULT_LANGUAGE).messages
        app_messages = Catalogue.load(DEFAULT_LANGUAGE, APP_LOCALES).messages
        reference = params_reference_keys()
        sidecar = _pseudo_mark(reference)
        return cls(
            language="xx",
            core=Catalogue("xx", "machine-draft", _pseudo_mark_templates(core_messages)),
            app=Catalogue("xx", "machine-draft", _pseudo_mark_templates(app_messages)),
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

    def __call__(self, key: str, /, **params: object) -> str:
        """App chrome by key. Params are display-ready strings; nested Messages render.

        `key` is positional-only so a catalogue placeholder literally named `{key}`
        (`app.report.excluded_line`, keyed by exclusion identifier) can still be passed
        as `key=...` in `**params` without colliding with this method's own parameter.
        """
        rendered = {k: (self.render(v) if isinstance(v, Message) else v) for k, v in params.items()}
        try:
            return self._lookup(key).format(**rendered)
        except (KeyError, IndexError) as exc:
            raise KeyError(f"{key!r} in {self.language!r}: {exc}") from exc
        except ValueError as exc:
            # A malformed template (an unbalanced brace) - test 4 refuses it in a file.
            raise ValueError(
                f"{key!r} in {self.language!r} is not a valid template: {exc}"
            ) from exc

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


@cache
def _for_language(cls: type[Translator], language: str) -> Translator:
    return cls.load(language)


def english() -> Translator:
    return Translator.for_language(DEFAULT_LANGUAGE)


# -- the gate ---------------------------------------------------------------------------


@cache
def catalogue_status(
    language: str,
    *,
    core_root: Path = CORE_LOCALES,
    app_root: Path = APP_LOCALES,
    params_root: Path = PARAMS_LOCALES,
) -> str | None:
    """`reviewed` only if all three files say so; None if any is missing (I§6).

    Cached per process and per root: the gate runs on every page load and every
    session, and the files change only with a deploy, which restarts the service. A
    `status:` header flipped on disk therefore takes effect at the next restart.
    """
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
    `SEAGARDEN_SHOW_DRAFT_LANGUAGES` shows drafts only when it is `1`, `true`, `yes` or
    `on` (any case): anything else, including a typo, keeps drafts hidden - the switch
    fails closed. The environment is read on every call; the default `status`,
    `catalogue_status`, is cached per process.
    """
    wanted = env.get(ENV_LANGUAGES)
    candidates = [c.strip().lower() for c in wanted.split(",")] if wanted else list(LANGUAGES)
    show_drafts = env.get(ENV_SHOW_DRAFTS, "").strip().lower() in _SWITCH_ON
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
