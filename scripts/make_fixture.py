"""Generate the committed synthetic fixture (C§7).

Run as a module, from the repository root:

    micromamba run -n shiny python -m scripts.make_fixture

Either `-m` from the repository root or a plain `python scripts/make_fixture.py`
works for a manual run: the `sys.path` block below puts `src/` and `tests/` on
`sys.path` itself, so nothing here depends on which of the two put the
repository root on `sys.path` too. `-m` plays no part in making
`from scripts.make_fixture import build_fixture` work under pytest, either —
that import resolves under pytest's `pythonpath = ["src", "."]` alone, which
pytest applies regardless of how this module is later invoked as a script.

The fixture is written by the *same* writer and manifest code as a production
refresh (`write_pair`), so a mismatch between the generator and the real
pipeline shows up here, not only downstream in package D or C1.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

# In the `shiny` development environment, `seagarden_dst` has no editable install
# (`pip show seagarden_dst` finds nothing there) — pytest resolves it via
# pyproject's `pythonpath = ["src", "."]`, but a plain script run with
# `python -m` or `python scripts/make_fixture.py` gets no such help, so this puts
# `src/` (and, for the same reason, `tests/`) on `sys.path` itself. CI's
# `pip install -e ".[spatial,dev]"` DOES install the package, so this block is
# development-environment insurance, not a repository-wide fact — do not "clean
# this up" by removing it and relying on an install that CI has but this
# environment does not.
_ROOT = Path(__file__).resolve().parent.parent
_SRC_DIR = _ROOT / "src"
_TESTS_DIR = _ROOT / "tests"
for _p in (_SRC_DIR, _TESTS_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# In the `shiny` development environment, `tests/` has no `__init__.py` (pytest's
# own import mode relies on that), and an unrelated `tests` package is installed
# in that environment's site-packages, which shadows a plain
# `import tests.refresh_builders`. `tests/` is on `sys.path` directly (above),
# exactly what pytest does for every test module in that directory, so the bare
# module name resolves — the same way `tests/conftest.py` imports it. CI's
# `pip install -e ".[spatial,dev]"` installs no such shadowing `tests` package,
# so this is again a development-environment fact, not a repository-wide one.
from refresh_builders import dataset, derived, fixture_grid, layers, manifest  # noqa: E402

from seagarden_dst.refresh.manifest import ARTIFACT_VARIABLES  # noqa: E402
from seagarden_dst.refresh.writer import write_pair  # noqa: E402

# The criterion C§4.4 states is "no baseline window applies", not "the production
# entry happens to be empty" — so these three are named explicitly rather than
# derived from whether `refresh_builders.baselines()`'s entries are truthy. A
# future change to that shape must not silently change what the fixture claims.
_STATIC_FIELDS = frozenset({"depth_mean_m", "depth_min_m", "valid"})

_RETRIEVED_ON = datetime(2026, 1, 1, tzinfo=UTC)
_YEARS = [2024, 2025]


def _fixture_manifest(grid):
    # `ARTIFACT_VARIABLES` is a `frozenset`, whose iteration order is not stable
    # across separate Python processes under hash randomization — iterating it
    # directly here made a fresh regeneration of `manifest.json` byte-different
    # from the committed one on every run, purely from `baselines` key order,
    # for no reason that would show up in a review diff. `sorted()` here fixes
    # a deterministic key order at the point of serialisation, without touching
    # `ARTIFACT_VARIABLES` itself.
    fixture_baselines = {
        name: ([] if name in _STATIC_FIELDS else _YEARS)
        for name in sorted(ARTIFACT_VARIABLES)
    }

    fixture_layers = [
        lyr.model_copy(update={"version": "synthetic", "retrieved_on": _RETRIEVED_ON})
        for lyr in layers()
    ]

    return manifest(
        built_on=_RETRIEVED_ON,
        grid=grid,
        baselines=fixture_baselines,
        layers=fixture_layers,
        derived=derived(),
    )


def build_fixture(target_dir: Path) -> tuple[Path, Path]:
    """Build the synthetic fixture pair into `target_dir`. Returns (artifact, manifest)."""
    grid = fixture_grid()
    ds = dataset(grid, _YEARS)
    fixture_manifest = _fixture_manifest(grid)
    return write_pair(ds, fixture_manifest, Path(target_dir))


if __name__ == "__main__":
    _here = Path(__file__).resolve().parent.parent
    artifact, manifest_path = build_fixture(_here / "tests" / "fixtures" / "data")
    print(f"wrote {artifact}")
    print(f"wrote {manifest_path}")
