"""The `spatial` extra stays build-time only, and the boundary holds both ways.

C§10 clause 8 states one direction. The other matters as much: a `refresh/`
module importing the core would drag the core into the refresh environment and
make the core's four-dependency floor a fiction.

Parsed with `ast` rather than imported, because importing a core module to see
what it imports is exactly the coupling under test. `tests/test_packaging.py`'s
`test_the_core_package_does_not_import_pandas_at_module_level` is the same idiom,
added for the same reason — read it before writing this.
"""

import ast
from pathlib import Path

CORE = Path(__file__).resolve().parents[1] / "src" / "seagarden_dst"
REFRESH = CORE / "refresh"


def _imported_modules(path: Path) -> set[str]:
    """Absolute module names, with relative imports resolved to absolute.

    A relative import — `from .grid import GridSpec`, `from ..api import x` —
    carries `level > 0` and a `module` that is a bare suffix or None, so matching
    on the string alone misses it completely. That is exactly how a core import
    would slip into `refresh/` past a test claiming to forbid it.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    package = (
        "seagarden_dst.refresh" if path.parent.name == "refresh" else "seagarden_dst"
    )
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                parts = package.split(".")
                base = ".".join(parts[: len(parts) - node.level + 1])
                names.add(f"{base}.{node.module}" if node.module else base)
            elif node.module:
                names.add(node.module)
    return names


def test_no_core_module_imports_refresh():
    offenders = sorted(
        p.name for p in CORE.glob("*.py")
        if any(m.startswith("seagarden_dst.refresh") for m in _imported_modules(p))
    )
    assert not offenders, f"core modules importing refresh/: {offenders}"


def test_refresh_imports_nothing_from_the_core():
    offenders = {}
    for p in REFRESH.glob("*.py"):
        bad = sorted(
            m for m in _imported_modules(p)
            if m.startswith("seagarden_dst")
            and not m.startswith("seagarden_dst.refresh")
        )
        if bad:
            offenders[p.name] = bad
    assert not offenders, f"refresh/ modules importing the core: {offenders}"
