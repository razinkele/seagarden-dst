"""Catalogue invariants (spec I§8 tests 1-5 and 7). Default selection; no Shiny."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
import yaml

from app.i18n import APP_LOCALES, PARAMS_LOCALES, params_reference_keys
from seagarden_dst.i18n import CORE_LOCALES, LANGUAGES, placeholders

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
