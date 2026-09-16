"""Generate the committed synthetic fixture (C§7).

Run as a module, from the repository root:

    micromamba run -n shiny python -m scripts.make_fixture

`-m` keeps the repository root itself on `sys.path` (rather than `scripts/`,
which is what plain `python scripts/make_fixture.py` would do), which is what
makes `from scripts.make_fixture import build_fixture` work under pytest's
`pythonpath = ["src", "."]`. This module has no editable install of
`seagarden_dst` to rely on outside pytest — `pip show seagarden_dst` finds
nothing in the `shiny` environment — so it puts `src/` on `sys.path` itself,
below, rather than requiring `PYTHONPATH=src` to be set by hand.

The fixture is written by the *same* writer and manifest code as a production
refresh (`write_pair`), so a mismatch between the generator and the real
pipeline shows up here, not only downstream in package D or C1.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SRC_DIR = _ROOT / "src"
_TESTS_DIR = _ROOT / "tests"
for _p in (_SRC_DIR, _TESTS_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import numpy as np  # noqa: E402
import xarray as xr  # noqa: E402

# `tests/` has no `__init__.py` (pytest's own import mode relies on that), and an
# unrelated `tests` package is installed in the environment's site-packages, which
# shadows a plain `import tests.refresh_builders`. `tests/` is on `sys.path`
# directly (above), exactly what pytest does for every test module in that
# directory, so the bare module name resolves — the same way `tests/conftest.py`
# imports it.
from refresh_builders import baselines, derived, fixture_grid, layers, manifest  # noqa: E402

from seagarden_dst.refresh.writer import write_pair  # noqa: E402

_RETRIEVED_ON = datetime(2026, 1, 1, tzinfo=UTC)
_YEARS = [2024, 2025]
_MONTHS = list(range(1, 13))
_SEED = 20260916


def _fixture_dataset(grid) -> xr.Dataset:
    rng = np.random.default_rng(_SEED)
    lat = grid.lats()
    lon = grid.lons()
    n = grid.n_lat
    four_d = ("year", "month", "latitude", "longitude")

    def f4():
        return (four_d, rng.random((len(_YEARS), len(_MONTHS), n, n)).astype("float32"))

    valid = np.ones((n, n), dtype=bool)
    valid[0, 0] = False  # at least one invalid cell, so the field is exercised

    return xr.Dataset(
        {
            "salinity_psu": f4(),
            "temp_c": f4(),
            "din_umol_l": f4(),
            "dip_umol_l": f4(),
            "light_attenuation_k": f4(),
            "significant_wave_m": (
                ("month", "latitude", "longitude"),
                rng.random((len(_MONTHS), n, n)).astype("float32"),
            ),
            "depth_mean_m": (
                ("latitude", "longitude"),
                rng.random((n, n)).astype("float32"),
            ),
            "depth_min_m": (
                ("latitude", "longitude"),
                rng.random((n, n)).astype("float32"),
            ),
            "valid": (("latitude", "longitude"), valid),
        },
        coords={"year": _YEARS, "month": _MONTHS, "latitude": lat, "longitude": lon},
    )


def _fixture_manifest(grid):
    all_baselines = baselines()
    fixture_baselines = {
        name: (_YEARS if years else [])
        for name, years in all_baselines.items()
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
    dataset = _fixture_dataset(grid)
    fixture_manifest = _fixture_manifest(grid)
    return write_pair(dataset, fixture_manifest, Path(target_dir))


if __name__ == "__main__":
    _here = Path(__file__).resolve().parent.parent
    artifact, manifest_path = build_fixture(_here / "tests" / "fixtures" / "data")
    print(f"wrote {artifact}")
    print(f"wrote {manifest_path}")
