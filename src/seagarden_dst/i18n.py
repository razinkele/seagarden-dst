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
from functools import cache
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


@cache
def core_catalogue(language: str) -> Catalogue:
    """The core's own catalogue for `language`, English underneath. Loaded once."""
    english = Catalogue.load(DEFAULT_LANGUAGE, CORE_LOCALES)
    if language == DEFAULT_LANGUAGE:
        return english
    return Catalogue.load(language, CORE_LOCALES, fallback=english)
