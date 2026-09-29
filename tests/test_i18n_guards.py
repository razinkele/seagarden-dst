"""Catalogue invariants (spec I§8 tests 1-5 and 7). Default selection; no Shiny."""

from __future__ import annotations

import ast
import re
import string
from pathlib import Path

import pytest
import yaml

from app.i18n import APP_LOCALES, PARAMS_LOCALES, params_reference_keys
from seagarden_dst.i18n import CORE_LOCALES, LANGUAGES

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


def _edges(text: str) -> tuple[str, str]:
    """The leading and trailing whitespace of a value."""
    body = text.strip()
    if not body:
        return text, ""
    start = text.index(body)
    return text[:start], text[start + len(body):]


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


_FORMATTER = string.Formatter()


def _template_fields(value: str) -> frozenset[str]:
    """The names `value.format(**params)` looks up, read by `str.format`'s own parser.

    Raises `ValueError` for a value that would fail at render or bend a parameter: an
    unbalanced brace (`"{depth} m}"`, `"{von {depth}"`, a trailing `{`), a field that is
    not a bare name (`{}`, `{0}`, `{a.b}`, `{a[0]}`), a conversion (`{a!r}`) or a format
    spec (`{a:>5}` - parameters arrive display-ready, I§4.1). `{{depth}}` is literal
    text and yields no field, so it surfaces as a placeholder missing against English.
    """
    fields = set()
    for _text, name, spec, conversion in _FORMATTER.parse(value):
        if name is None:
            continue
        if not name.isidentifier():
            raise ValueError(f"{{{name}}} is not a bare placeholder name")
        if spec or conversion:
            raise ValueError(
                f"{{{name}}} carries conversion {conversion!r} / format spec {spec!r}"
            )
        fields.add(name)
    return frozenset(fields)


def _template_problem(value: str, english: str | None) -> str | None:
    """Why test 4 refuses `value`, or None. `english` is the same key's reference value,
    None for a key English lacks (test 1 reports that one)."""
    try:
        fields = _template_fields(value)
    except ValueError as exc:
        return f"not a valid template: {exc}"
    if english is None:
        return None
    try:
        expected = _template_fields(english)
    except ValueError as exc:
        return f"its English reference is not a valid template: {exc}"
    if fields != expected:
        return f"placeholders {sorted(fields)} differ from English {sorted(expected)}"
    return None


@pytest.mark.parametrize("owner", sorted(OWNERS))
def test_4_catalogue_hygiene(owner):
    """Every value renders: it parses the way `str.format` parses it, names exactly the
    placeholders English names for that key, and carries no conversion or format spec.

    English is parsed per key a file holds, not eagerly over the whole reference.
    `params` values render verbatim (`species_name`, `method_name`, `method_field`,
    `group_label`, and the text index substitute them for a literal's text) - never
    through `str.format` - so they are exempt from the template rule below: an English
    YAML note containing a brace must not fail every sidecar value. Each `params` value
    is instead required to be a non-empty string.
    """
    reference = _reference(owner)
    for path in _files(OWNERS[owner]):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert data["language"] == path.stem
        assert data["status"] in {"reference", "machine-draft", "reviewed"}
        assert (data["status"] == "reference") == (path.stem == "en"), (
            f"{path}: only English is the reference; every other language is a draft or reviewed"
        )
        if data["status"] != "reference":
            assert data.get("translated_by"), f"{path}: translated_by missing"
        for key, value in data["messages"].items():
            assert not key.endswith(("_one", "_other")), f"{key}: no plural forms (I§7)"
            if owner == "params":
                assert isinstance(value, str) and value, f"{path}: {key} is not a non-empty string"
                continue
            problem = _template_problem(value, reference.get(key))
            assert problem is None, f"{path}: {key}: {problem}"


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


def _owner(parents: dict[ast.AST, ast.AST], node: ast.AST) -> str:
    """The innermost scope enclosing `node`: a function's name, `"<class Name>"` for a
    class body with no enclosing function, or `"<module>"` at top level. Walking up
    stops at the FIRST function/class def it meets, so a method (a `FunctionDef`
    nested in a `ClassDef`) reports its own name, not its class's - a bare class
    attribute is the only case that reports `"<class Name>"`.
    """
    current = parents.get(node)
    while current is not None:
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return current.name
        if isinstance(current, ast.ClassDef):
            return f"<class {current.name}>"
        current = parents.get(current)
    return "<module>"


def test_5_literal_appears_only_where_the_spec_allows():
    """`Message.literal(` is for data and engine messages, never for app chrome (I§4.1).

    Each allowed site is `file:function`, with a comment naming which of I§4.1's three
    kinds of literal it is: (1) YAML data - a note or a name read from `params/`; (2) an
    engine's or reader's own message; (3) a data identifier composed into a sentence.

    The scan attributes every call whose attribute name is `literal` to its innermost
    function (`_owner`, above), whatever the receiver expression is (`Message.literal`,
    `i18n.Message.literal`, `M.literal`, ...) and whatever scope it sits in - a bare
    module-level assignment, a class attribute, an `async def` - not only a call found
    by walking a `FunctionDef` node's own body, which is blind to all of those.
    """
    allowed = {
        # (1) YAML data: `self.note`, the plain string on a species YAML's own tier-D
        # calibration row (`calibration_for`'s row). `caveat()`'s tier-D branch is
        # `self.note if isinstance(self.note, Message) else Message.literal(self.note)`;
        # the salinity-floor contraindication `contraindication()` synthesises
        # separately passes a keyed `msg(...)` as `note`, so it takes the `if` arm, not
        # this `literal` one - but it DOES reach `caveat()`'s tier-D branch, same as
        # this YAML row does. Translated when the sidecar has a match (I§5.4).
        ("src/seagarden_dst/calibration.py", "caveat"),
        # (1) YAML data: `method.name`, from params/methods.yaml.
        ("src/seagarden_dst/suitability.py", "assess_physical"),
        # (1) YAML data (`method.name`) and (3) a data identifier composed into a
        # sentence (`species.group`, e.g. "macroalga"/"shellfish" - an identifier I§5.1
        # says is normally displayed raw, composed here into a constraint's reason).
        ("src/seagarden_dst/suitability.py", "assess"),
        # (2) the reader's own message (`str(exc)` for a `ForcingUnavailable` window)
        # and the engine's own message (`str(exc)` for a `BowtieUnavailable` window) -
        # operator diagnostics the core did not author, not YAML or catalogue text.
        ("src/seagarden_dst/api.py", "assess_site"),
    }
    found = set()
    for path in sorted((REPO / "src").rglob("*.py")) + sorted((REPO / "app").rglob("*.py")):
        if "__pycache__" in path.parts or path.parts[-2] == "tests":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
        for call in ast.walk(tree):
            if (
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Attribute)
                and call.func.attr == "literal"
            ):
                found.add((path.relative_to(REPO).as_posix(), _owner(parents, call)))
    assert found <= allowed, f"unlisted Message.literal sites: {sorted(found - allowed)}"
    assert not any(f.startswith("app/") for f, _ in found)

    # Backstop for app/: `.literal(` must never appear as text, whatever the receiver -
    # independent of the AST walk above, so a construct the parser cannot see through
    # (or a future change to this test) cannot let one slip past both checks at once.
    for path in sorted((REPO / "app").rglob("*.py")):
        if "__pycache__" in path.parts or path.parts[-2] == "tests":
            continue
        assert ".literal(" not in path.read_text(encoding="utf-8"), (
            f"{path}: .literal( must never appear under app/ (I§4.1)"
        )


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
