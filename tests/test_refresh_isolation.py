"""The `refresh/` import boundary holds in both directions, across the whole
runtime install.

C§10 clause 8 states one direction: the runtime install must not need `refresh/`
or its `spatial` extra. The other direction matters as much: a `refresh/` module
importing the model package would couple build-time tooling to model changes and
stop it being independently runnable in its own leaner environment — the property
C§5's "thin layer-plugin package" is meant to protect. Nothing about the core's
declared dependency floor is at stake in that direction; it is a coupling concern,
not a dependency-declaration one.

Both directions are checked over `src/seagarden_dst/` and `app/` together, not just
the installed package. `app/` is not part of the built wheel — `pyproject.toml` maps
only `seagarden_dst` and `seagarden_dst.paramdata` under `package-dir`/`packages` — but
it is the actual production consumer of the core: it runs by executing the checkout
directly (`shiny run app.app`, per `app/app.py` and the README), not by installing the
distribution. A Shiny module reaching into `refresh/` would be a real production defect
regardless of packaging mechanics, so it belongs in the same scan. The scan is recursive
so a future nested package (a `refresh/layers/` subpackage, a deeper `app/` module) stays
covered instead of silently falling outside a glob written for today's shape.

Parsed with `ast` rather than imported, because importing a core module to see
what it imports is exactly the coupling under test. `tests/test_packaging.py`'s
`test_the_core_package_does_not_import_pandas_at_module_level` is the same family
of technique — source inspection rather than import — but a different shape: it
scans rendered source text for a specific import at a specific indentation,
while this scans the AST for import targets by name, resolving relative imports
to absolute so a `from .grid import X` cannot slip past a check that only matches
strings.

KNOWN GAP: this check is static. `importlib.import_module("seagarden_dst.refresh.grid")`
or any other string-built dynamic import is invisible to an AST walk over `Import`/
`ImportFrom` nodes and is NOT caught by either test below, in either direction. That is
a documented hole, not an oversight: catching it would mean chasing string literals
through arbitrary computation, which is guesswork rather than a check. A reviewer
relying on these tests should know they prove the absence of static imports across
the boundary, not the absence of every possible way to cross it.
"""

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src"
CORE = SRC / "seagarden_dst"
REFRESH = CORE / "refresh"
APP = REPO / "app"


def _dotted_package(path: Path) -> str:
    """The dotted package name of the directory containing `path`.

    Used to resolve relative imports (`level > 0`) to absolute names. Computed
    from the file's location rather than hard-coded to two known depths, so a
    module nested arbitrarily deep — `refresh/layers/__init__.py`,
    `app/modules/sub/x.py` — still resolves correctly.
    """
    if path == SRC or SRC in path.parents:
        rel = path.parent.relative_to(SRC)
    else:
        rel = path.parent.relative_to(REPO)
    return ".".join(rel.parts)


def _imported_modules(path: Path) -> set[str]:
    """Absolute module names, with relative imports resolved to absolute.

    A relative import — `from .grid import GridSpec`, `from ..api import x` —
    carries `level > 0` and a `module` that is a bare suffix or None, so matching
    on the string alone misses it completely. That is exactly how a core import
    would slip into `refresh/` past a test claiming to forbid it.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    package = _dotted_package(path)
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


def _core_and_app_modules() -> list[Path]:
    """Every `.py` file in the core package or the deployed app, excluding `refresh/`.

    Recursive over both `src/seagarden_dst/` and `app/`. `app/` is not part of the
    built wheel, but it is what actually runs in production (a checkout, run
    directly, not an installed distribution), so it belongs in the same scan as
    the core package.
    """
    core_files = [p for p in CORE.rglob("*.py") if REFRESH not in p.parents and p != REFRESH]
    app_files = list(APP.rglob("*.py")) if APP.is_dir() else []
    return core_files + app_files


def test_no_core_module_imports_refresh():
    offenders = sorted(
        str(p.relative_to(REPO))
        for p in _core_and_app_modules()
        if any(m.startswith("seagarden_dst.refresh") for m in _imported_modules(p))
    )
    assert not offenders, f"runtime-install modules importing refresh/: {offenders}"


def test_refresh_imports_nothing_from_the_core():
    offenders = {}
    for p in REFRESH.rglob("*.py"):
        bad = sorted(
            m for m in _imported_modules(p)
            if m.startswith("seagarden_dst")
            and not m.startswith("seagarden_dst.refresh")
        )
        if bad:
            offenders[str(p.relative_to(REPO))] = bad
    assert not offenders, f"refresh/ modules importing the core: {offenders}"
