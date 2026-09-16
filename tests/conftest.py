"""Shared pytest configuration.

Registers `--snapshot-update`, used by `test_golden_snapshot.py` to regenerate the
golden files instead of asserting against them. pytest collects conftests along the
invocation path and rootdir ancestry before argument parsing finishes, regardless of
`testpaths` - `testpaths` only comes into play when a run is given no positional path
arguments to derive that walk from. Either way this conftest is found first, so the
flag is available whether pytest is invoked bare (falls back to `testpaths`) or with
an explicit path such as `pytest tests/test_golden_snapshot.py --snapshot-update`.
"""

from __future__ import annotations

import pytest
import refresh_builders


def pytest_addoption(parser):
    parser.addoption(
        "--snapshot-update",
        action="store_true",
        default=False,
        help="Regenerate golden files instead of asserting against them.",
    )


@pytest.fixture
def reference_manifest():
    """The Task 3 reference manifest, shared by every test module that needs one.

    Just `refresh_builders.manifest()` — the builder itself lives in
    `tests/refresh_builders.py` and is not duplicated here.
    """
    return refresh_builders.manifest()


@pytest.fixture
def tiny_dataset():
    """A 3x3-cell, 2-year dataset carrying all nine variables at C§3.2 shapes.

    Coordinates come from `refresh_builders.fixture_grid()` (via `.lats()`/
    `.lons()`), not from an independent `np.linspace` over round bounds: the
    `reference_manifest` fixture's grid describes this same fixture grid, so the
    manifest that travels with this dataset actually describes the artifact
    beside it.

    float32 everywhere except `valid`, which is bool — a float32 `valid` holding
    0.0/1.0 can never be NaN, so a reader applying the is-NaN test would find
    every cell valid, everywhere, silently.
    """
    import numpy as np
    import xarray as xr

    grid = refresh_builders.fixture_grid()
    rng = np.random.default_rng(20260916)
    years, months = [2024, 2025], list(range(1, 13))
    lat = grid.lats()
    lon = grid.lons()
    n = grid.n_lat
    four_d = ("year", "month", "latitude", "longitude")

    def f4():
        return (four_d, rng.random((len(years), len(months), n, n)).astype("float32"))

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
                rng.random((len(months), n, n)).astype("float32"),
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
        coords={"year": years, "month": months, "latitude": lat, "longitude": lon},
    )
