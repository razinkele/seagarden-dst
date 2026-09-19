# Package C-d — EMODnet Bathymetry, the Runbook, and the First Refresh: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Register the fifth and last layer, `emodnet_bathy`, so a refresh can write an artifact the manifest validator accepts; write the annual-refresh runbook C§8.1 owes; and run the first real refresh on laguna so the tool has an artifact to read.

**Architecture:** One new source module, `refresh/sources/emodnet.py`, in the C-c1 pattern: an injectable fetcher (like `cmems.DatasetOpener`), a stdlib probe, and a `Layer` class that builds a static two-field dataset on the artifact grid. Reduction is pure numpy (centre-binning into `GridSpec` cells, wet pixels only); tile I/O is rasterio behind a lazy import. Registering the layer tightens the registry guard to equality in the same commit. The runbook is a document with a test that checks it carries what C§8.1 lists. The first run is a human-executed runbook step, targeted outside the serving checkout.

**Tech Stack:** Python 3.11+, numpy, xarray, rasterio (the `spatial` extra), `urllib` + `xml.etree` (stdlib) for the WCS, pytest.

**Spec:** `docs/superpowers/specs/2026-09-15-package-c-refresh-tooling-design.md`, **C§13** (added 2026-09-19) for everything EMODnet, C§8.1 for the runbook, C§10 for the done-when. Binding above it: `docs/superpowers/specs/2026-09-13-dst-data-layer-design.md` §6.

## Global Constraints

- **Nothing under `refresh/` may import xarray, rasterio or copernicusmarine at module scope.** The default suite runs `-m 'not spatial'`, and `-m` deselects *after* collection, so a module-scope import reddens every test at collection. `tests/test_refresh_catalogue.py::test_no_refresh_module_imports_the_spatial_stack_at_module_scope` globs `sources/*.py` and will catch it; import inside functions.
- **No test touches the network.** The fetcher and the capabilities reader are injectable; every test hands in a fake.
- **Tests that need rasterio or xarray are marked `@pytest.mark.spatial`.** Pure numpy tests are unmarked and run in the default selection.
- The layer pins coverage `emodnet__mean_2022`; `dataset_id` is the coverage id, `version` is `"2022"` (C§13.1).
- `depth = -elevation`; wet = `elevation < 0`; NaN elevation is not wet; `depth_min_m` is the shallowest wet depth (C§13.2, C§13.3).
- Coordinates emitted are `GridSpec.lats()`/`lons()` exactly, the lower cell edges; binning is `floor((x - min) / step)` (C§13.3).
- Both depth fields are static: `baseline_years` returns `{"depth_mean_m": [], "depth_min_m": []}`, present not omitted (C§4.4).
- Local runs: `MKL_THREADING_LAYER=SEQUENTIAL` before every Python invocation (the env's numpy crashes under MKL's default threading layer), and `GDAL_DATA=C:\Users\arturas.baziukas\micromamba\envs\shiny\Library\share\gdal` for rasterio. The Windows `/tmp` of Git Bash is not the Windows temp; use `tmp_path` in tests.
- ruff: `line-length = 100`, `target-version = "py311"`. The repo is ruff-clean and stays so.
- Test discrimination standard (from the D-a plan): every negative test asserts `match=` on a fragment unique to its rule; record actual pytest output, never the word "verified"; commit implementation before running mutation proofs.
- Never `git add` anything under `.superpowers/`, `.refresh-work/`, or `data/forcing/forcing.nc`.
- The real refresh runs on laguna, by the user, against `--target ~/seagarden-data/forcing`, never inside `~/seagarden-dst` (C§13.6). The permission classifier denies deploy-class commands on laguna from the assistant; do not attempt them.

## Shipped interfaces this plan consumes — read, not remembered

| Thing | Fact |
|---|---|
| `Layer` protocol (`refresh/layer.py:84`) | `name: str`; `probe() -> ProbeResult`; `build(grid: GridSpec, years: YearRange, workdir: Path) -> xr.Dataset`; `provenance() -> LayerProvenance`; `baseline_years() -> dict[str, list[int]]` |
| `ProbeResult` | `name, status: Literal["ok","absent","version_drift","unreachable"], reachable: bool, detail: str`; validator refuses `ok` with `reachable=False` and vice versa |
| `LAYER_NAMES` (`layer.py:108`) | already lists `"emodnet_bathy"` fifth |
| `GridSpec` (`artifact/grid.py`) | fields `crs, lat_min, lat_max, lon_min, lon_max, lat_step, lon_step, n_lat, n_lon`; `lats()`/`lons()` return **lower cell edges**; `GridSpec.baltic()` is 53.5–60.0 N, 9.5–27.0 E, 390 × 630 |
| `check_shapes` (`refresh/shapes.py`) | `depth_mean_m` and `depth_min_m` must have dims exactly `("latitude", "longitude")` |
| `check_grid` (`refresh/driver.py:126`) | merged coords must `np.allclose` `grid.lats()`/`lons()` |
| `compute_valid` (`refresh/merge.py:54`) | a cell is valid only where every variable is finite; NaN depth ⇒ invalid |
| `LayerProvenance` / `Archive` (`artifact/manifest.py:72`, `:38`) | fields as C§13.5; `pending` needs `source_url` and `unblocked_by` |
| `cmems.ARCHIVE_UNBLOCKED_BY` (`sources/cmems.py:52`) | the shared `unblocked_by` string; reuse it |
| `check_registered_names` (`refresh/registry.py`) | currently `<=`; C§13.5 tightens to equality in the registering commit |
| `FakeLayer` (`tests/refresh_fakes.py`) | `FakeLayer(name, variables, shape="static", ...)` builds ones on the grid |
| `C11_1_CATALOGUE` (`tests/test_refresh_registry.py`) | `name -> (dataset_id, version)`; the registry must equal its key set |
| Existing CLI (`scripts/refresh_layers.py`) | `--probe`, `--start-year`, `--end-year`, `--target` (default `data/forcing`), `--workdir` (default `.refresh-work`); uses `GridSpec.baltic()` |
| Reader locator (`gridded.py:37`) | env `SEAGARDEN_DATA_DIR`, default `data` |

## File structure

| File | Responsibility |
|---|---|
| `src/seagarden_dst/refresh/sources/emodnet.py` | **Create.** Constants (`COVERAGE_ID`, `VERSION`, `WCS_URL`, ...); `Tile`, `tiles_for`, `tile_path`, `wcs_url`; `TileFetcher` protocol and `_default_fetcher`; `read_tile` (rasterio, lazy); `GridAccumulator` (pure numpy reduction); `coverage_ids` (capabilities parse) and `_default_capabilities`; `EmodnetBathy` layer |
| `src/seagarden_dst/refresh/registry.py` | **Modify.** Register `EmodnetBathy()`; guard tightened to `==`; stale comments removed |
| `tests/test_refresh_emodnet.py` | **Create.** Reduction (unmarked), tiling, probe parse, fetch cache, build shape (spatial) |
| `tests/test_refresh_registry.py` | **Modify.** Five layers; catalogue table gains the EMODnet row |
| `tests/test_refresh_cli.py` | **Modify.** The two "incomplete registry" tests become "complete registry" tests |
| `tests/refresh_builders.py` | **Modify.** The fixture's `emodnet_bathy` record reads the layer's constants |
| `tests/fixtures/data/manifest.json` | **Regenerate** with `scripts/make_fixture.py` |
| `pyproject.toml`, `README.md`, `CHANGELOG.md` | **Modify.** Comments and stub rows that say the layer is outstanding |
| `docs/runbooks/annual-refresh.md` | **Create.** C§8.1's runbook |
| `tests/test_runbooks.py` | **Create.** The runbook carries what C§8.1 lists |
| `docs/2026-09-XX-first-refresh.md` | **Create in Task 7**, dated on the day the run happens: the record of the first real run |

---

### Task 1: The reduction — pixels into cells, wet only

**Files:**
- Create: `src/seagarden_dst/refresh/sources/emodnet.py`
- Test: `tests/test_refresh_emodnet.py`

**Interfaces:**
- Produces: `class GridAccumulator: __init__(self, grid: GridSpec); add(self, elevation: np.ndarray, pixel_lats: np.ndarray, pixel_lons: np.ndarray) -> None; finish(self) -> tuple[np.ndarray, np.ndarray]` returning `(depth_mean, depth_min)` each shaped `(grid.n_lat, grid.n_lon)`, float64, NaN where no wet pixel.
- `elevation` is 2-D `(rows, cols)`; `pixel_lats` is 1-D of length `rows` (any order); `pixel_lons` is 1-D of length `cols`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_refresh_emodnet.py
"""EMODnet Bathymetry: reduction, tiling, probe and build (C§13)."""

from __future__ import annotations

import numpy as np
import pytest

from seagarden_dst.artifact.grid import GridSpec


def tiny_grid() -> GridSpec:
    """Three cells by two, on the real steps, so the lon step is NOT a whole number of
    pixels (C§13.3)."""
    return GridSpec(
        crs="EPSG:4326",
        lat_min=55.0, lat_max=55.05, lon_min=21.0, lon_max=21.0555,
        lat_step=0.016666, lon_step=0.027777, n_lat=3, n_lon=2,
    )


# --- GridAccumulator: C§13.3 ------------------------------------------------------


def test_depth_is_minus_elevation_averaged_over_wet_pixels():
    from seagarden_dst.refresh.sources.emodnet import GridAccumulator

    grid = tiny_grid()
    acc = GridAccumulator(grid)
    # Two pixels, both inside cell (0, 0): -10 m and -20 m.
    elevation = np.array([[-10.0, -20.0]])
    acc.add(elevation, pixel_lats=np.array([55.001]), pixel_lons=np.array([21.001, 21.010]))
    mean, minimum = acc.finish()
    assert mean[0, 0] == pytest.approx(15.0)
    assert minimum[0, 0] == pytest.approx(10.0), "depth_min is the SHALLOWEST wet depth"


def test_land_and_nan_pixels_are_not_wet_and_do_not_count():
    from seagarden_dst.refresh.sources.emodnet import GridAccumulator

    acc = GridAccumulator(tiny_grid())
    elevation = np.array([[-8.0, 0.0, 3.5, np.nan]])
    acc.add(elevation, np.array([55.001]), np.array([21.001, 21.002, 21.003, 21.004]))
    mean, minimum = acc.finish()
    assert mean[0, 0] == pytest.approx(8.0)
    assert minimum[0, 0] == pytest.approx(8.0)


def test_a_cell_with_no_wet_pixel_is_nan_so_valid_will_refuse_it():
    from seagarden_dst.refresh.sources.emodnet import GridAccumulator

    acc = GridAccumulator(tiny_grid())
    acc.add(np.array([[2.0, 0.0]]), np.array([55.001]), np.array([21.001, 21.002]))
    mean, minimum = acc.finish()
    assert np.isnan(mean[0, 0]) and np.isnan(minimum[0, 0])
    assert np.isnan(mean).all(), "untouched cells are NaN, not zero"


def test_pixels_bin_by_the_cell_containing_their_centre_with_lower_edge_coordinates():
    from seagarden_dst.refresh.sources.emodnet import GridAccumulator

    grid = tiny_grid()
    acc = GridAccumulator(grid)
    # One pixel per cell, placed just above each lower edge; lon step is 26.67 px so a
    # block reshape would misplace these, centre-binning must not.
    lats = grid.lats() + 0.0005
    lons = grid.lons() + 0.0005
    elevation = -np.arange(1, 7, dtype=float).reshape(3, 2)  # -1 .. -6
    acc.add(elevation, lats, lons)
    mean, _ = acc.finish()
    np.testing.assert_allclose(mean, np.arange(1, 7, dtype=float).reshape(3, 2))


def test_pixels_outside_the_grid_extent_are_dropped():
    from seagarden_dst.refresh.sources.emodnet import GridAccumulator

    grid = tiny_grid()
    acc = GridAccumulator(grid)
    lats = np.array([54.99, 55.001, 55.06])       # below, inside, above
    lons = np.array([20.99, 21.001, 21.06])       # left, inside, right
    acc.add(np.full((3, 3), -5.0), lats, lons)
    mean, _ = acc.finish()
    assert mean[0, 0] == pytest.approx(5.0)
    assert np.isnan(np.delete(mean.ravel(), 0)).all()


def test_accumulation_across_tiles_is_the_same_as_one_array():
    from seagarden_dst.refresh.sources.emodnet import GridAccumulator

    grid = tiny_grid()
    lats = np.array([55.001, 55.002])
    lons = np.array([21.001, 21.002])
    whole = GridAccumulator(grid)
    whole.add(np.array([[-1.0, -2.0], [-3.0, -4.0]]), lats, lons)
    split = GridAccumulator(grid)
    split.add(np.array([[-1.0, -2.0]]), lats[:1], lons)
    split.add(np.array([[-3.0, -4.0]]), lats[1:], lons)
    for a, b in zip(whole.finish(), split.finish(), strict=True):
        np.testing.assert_allclose(a, b, equal_nan=True)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `MKL_THREADING_LAYER=SEQUENTIAL python -m pytest tests/test_refresh_emodnet.py -q -p no:cacheprovider`
Expected: 6 failed, each with `ModuleNotFoundError: No module named 'seagarden_dst.refresh.sources.emodnet'`.

- [ ] **Step 3: Write the accumulator**

```python
# src/seagarden_dst/refresh/sources/emodnet.py
"""EMODnet Bathymetry: the fifth layer, and the only non-Copernicus one (C§13).

Elevation, not depth, arrives from the service: metres relative to LAT, negative
below the surface, land carried as zero or positive. Depth is `-elevation`, a pixel is
wet when `elevation < 0`, and every reduction here runs over wet pixels only, so a
cell with no wet pixel comes out NaN and `compute_valid` (C§3.5) refuses it.

**Nothing here imports rasterio or xarray at module scope** (see registry.py for why).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:  # pragma: no cover - typing only
    from seagarden_dst.artifact.grid import GridSpec


class GridAccumulator:
    """Bin pixels by the artifact cell containing their centre; reduce over wet ones.

    `GridSpec.lats()`/`lons()` are LOWER cell edges (their docstrings say so), so cell
    `i` spans `[lat_min + i*step, lat_min + (i+1)*step)`. A block reshape cannot do
    this: the lon step is 26.67 EMODnet pixels (C§13.3).
    """

    def __init__(self, grid: GridSpec) -> None:
        self._grid = grid
        shape = (grid.n_lat, grid.n_lon)
        self._sum = np.zeros(shape, dtype="float64")
        self._count = np.zeros(shape, dtype="int64")
        self._max_elevation = np.full(shape, -np.inf, dtype="float64")

    def add(self, elevation: np.ndarray, pixel_lats: np.ndarray, pixel_lons: np.ndarray) -> None:
        grid = self._grid
        elevation = np.asarray(elevation, dtype="float64")
        rows = np.floor((np.asarray(pixel_lats) - grid.lat_min) / grid.lat_step).astype(int)
        cols = np.floor((np.asarray(pixel_lons) - grid.lon_min) / grid.lon_step).astype(int)
        row_ok = (rows >= 0) & (rows < grid.n_lat)
        col_ok = (cols >= 0) & (cols < grid.n_lon)
        wet = elevation < 0  # NaN < 0 is False, so nil pixels drop out here too
        keep = wet & row_ok[:, None] & col_ok[None, :]
        if not keep.any():
            return
        r = np.broadcast_to(rows[:, None], elevation.shape)[keep]
        c = np.broadcast_to(cols[None, :], elevation.shape)[keep]
        values = elevation[keep]
        np.add.at(self._sum, (r, c), -values)
        np.add.at(self._count, (r, c), 1)
        np.maximum.at(self._max_elevation, (r, c), values)

    def finish(self) -> tuple[np.ndarray, np.ndarray]:
        """`(depth_mean_m, depth_min_m)`, NaN where no wet pixel fell in the cell."""
        has = self._count > 0
        mean = np.full(self._sum.shape, np.nan, dtype="float64")
        minimum = np.full(self._sum.shape, np.nan, dtype="float64")
        mean[has] = self._sum[has] / self._count[has]
        minimum[has] = -self._max_elevation[has]
        return mean, minimum
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `MKL_THREADING_LAYER=SEQUENTIAL python -m pytest tests/test_refresh_emodnet.py -q -p no:cacheprovider`
Expected: `6 passed`.

- [ ] **Step 5: Mutation proof, then commit**

Change `-values` to `values` in `add`, run the tests: `test_depth_is_minus_elevation...` must fail on `15.0`. Restore. Change `wet = elevation < 0` to `<= 0`: `test_land_and_nan...` must fail on `8.0`. Restore.

```bash
git add src/seagarden_dst/refresh/sources/emodnet.py tests/test_refresh_emodnet.py
git commit -m "feat(refresh): EMODnet reduction: centre-binned mean and shallowest-wet min per cell (C§13.3)"
```

---

### Task 2: Tiles, the fetcher seam, the cache, and reading a tile

**Files:**
- Modify: `src/seagarden_dst/refresh/sources/emodnet.py`
- Test: `tests/test_refresh_emodnet.py`

**Interfaces:**
- Produces:
  - `COVERAGE_ID = "emodnet__mean_2022"`, `VERSION = "2022"`, `WCS_URL = "https://ows.emodnet-bathymetry.eu/wcs"`
  - `@dataclass(frozen=True) class Tile: lat0: float; lat1: float; lon0: float; lon1: float`
  - `tiles_for(grid: GridSpec) -> list[Tile]` — whole-degree tiles covering the extent
  - `wcs_url(tile: Tile) -> str`
  - `tile_path(workdir: Path, tile: Tile) -> Path` — `workdir / "emodnet" / f"{lat0}_{lon0}.tif"`
  - `class TileFetcher(Protocol): def __call__(self, url: str, destination: Path) -> None: ...`
  - `fetch_tiles(tiles, workdir, fetcher) -> list[Path]` — skips existing files
  - `read_tile(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]` — `(elevation, pixel_lats, pixel_lons)`, pixel **centres**, rasterio inside

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_refresh_emodnet.py`:

```python
# --- Tiles and fetching: C§13.4 -------------------------------------------------------


def test_the_baltic_extent_is_126_whole_degree_tiles():
    from seagarden_dst.refresh.sources.emodnet import Tile, tiles_for

    tiles = tiles_for(GridSpec.baltic())
    assert len(tiles) == 7 * 18
    assert tiles[0] == Tile(lat0=53.0, lat1=54.0, lon0=9.0, lon1=10.0)
    assert tiles[-1] == Tile(lat0=59.0, lat1=60.0, lon0=26.0, lon1=27.0)


def test_a_tile_request_pins_the_dated_coverage_and_asks_for_geotiff():
    from seagarden_dst.refresh.sources.emodnet import COVERAGE_ID, Tile, wcs_url

    url = wcs_url(Tile(55.0, 56.0, 20.0, 21.0))
    assert COVERAGE_ID == "emodnet__mean_2022"
    assert f"COVERAGEID={COVERAGE_ID}" in url
    assert "SUBSET=Lat(55.0,56.0)" in url and "SUBSET=Long(20.0,21.0)" in url
    assert "FORMAT=image/tiff" in url
    assert "emodnet__mean&" not in url, "the undated alias drifts silently (C§13.1)"


def test_fetch_tiles_skips_tiles_already_on_disk(tmp_path):
    from seagarden_dst.refresh.sources.emodnet import Tile, fetch_tiles, tile_path

    tiles = [Tile(55.0, 56.0, 20.0, 21.0), Tile(55.0, 56.0, 21.0, 22.0)]
    tile_path(tmp_path, tiles[0]).parent.mkdir(parents=True)
    tile_path(tmp_path, tiles[0]).write_bytes(b"cached")
    fetched: list[str] = []

    def fake_fetcher(url: str, destination: Path) -> None:
        fetched.append(url)
        destination.write_bytes(b"new")

    paths = fetch_tiles(tiles, tmp_path, fake_fetcher)
    assert len(fetched) == 1 and "Long(21.0,22.0)" in fetched[0]
    assert [p.read_bytes() for p in paths] == [b"cached", b"new"]


def test_a_tile_the_fetcher_cannot_deliver_aborts_the_build(tmp_path):
    from seagarden_dst.refresh.sources.emodnet import Tile, TileFetchFailed, fetch_tiles

    def dead(url: str, destination: Path) -> None:
        raise OSError("connection reset")

    with pytest.raises(TileFetchFailed, match="Long\\(20.0,21.0\\)"):
        fetch_tiles([Tile(55.0, 56.0, 20.0, 21.0)], tmp_path, dead)


@pytest.mark.spatial
def test_read_tile_returns_elevation_and_pixel_centres(tmp_path):
    import rasterio
    from rasterio.transform import from_origin

    from seagarden_dst.refresh.sources.emodnet import read_tile

    # 4 x 4 pixels of 0.25 deg over 55-56 N, 20-21 E, row 0 at the TOP (north).
    data = np.arange(16, dtype="float32").reshape(4, 4) - 20.0
    path = tmp_path / "t.tif"
    with rasterio.open(
        path, "w", driver="GTiff", height=4, width=4, count=1, dtype="float32",
        crs="EPSG:4326", transform=from_origin(20.0, 56.0, 0.25, 0.25),
    ) as dst:
        dst.write(data, 1)

    elevation, lats, lons = read_tile(path)
    np.testing.assert_array_equal(elevation, data)
    np.testing.assert_allclose(lats, [55.875, 55.625, 55.375, 55.125])
    np.testing.assert_allclose(lons, [20.125, 20.375, 20.625, 20.875])
```

Add `from pathlib import Path` to the test module's imports.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `MKL_THREADING_LAYER=SEQUENTIAL python -m pytest tests/test_refresh_emodnet.py -q -p no:cacheprovider` and `... -m spatial`
Expected: the four unmarked new tests fail with `ImportError: cannot import name 'Tile'` (or `tiles_for`); the spatial one fails with `cannot import name 'read_tile'`.

- [ ] **Step 3: Implement tiles, fetcher, cache, reader**

Add to `emodnet.py` (imports at top: `import math`, `import os`, `import time`, `import urllib.request`, `from dataclasses import dataclass`, `from pathlib import Path`, `from typing import TYPE_CHECKING, Protocol`):

```python
COVERAGE_ID = "emodnet__mean_2022"
VERSION = "2022"
WCS_URL = "https://ows.emodnet-bathymetry.eu/wcs"
_RETRIES = 3


class TileFetchFailed(RuntimeError):
    """A tile could not be fetched after the retries. Partial data is not data (C§6.1)."""


@dataclass(frozen=True)
class Tile:
    lat0: float
    lat1: float
    lon0: float
    lon1: float


def tiles_for(grid: GridSpec) -> list[Tile]:
    """Whole-degree tiles covering the extent, south-west first, row-major."""
    lat_start, lat_stop = math.floor(grid.lat_min), math.ceil(grid.lat_max)
    lon_start, lon_stop = math.floor(grid.lon_min), math.ceil(grid.lon_max)
    return [
        Tile(float(lat), float(lat + 1), float(lon), float(lon + 1))
        for lat in range(lat_start, lat_stop)
        for lon in range(lon_start, lon_stop)
    ]


def wcs_url(tile: Tile) -> str:
    return (
        f"{WCS_URL}?SERVICE=WCS&VERSION=2.0.1&REQUEST=GetCoverage"
        f"&COVERAGEID={COVERAGE_ID}"
        f"&SUBSET=Lat({tile.lat0},{tile.lat1})&SUBSET=Long({tile.lon0},{tile.lon1})"
        f"&FORMAT=image/tiff"
    )


def tile_path(workdir: Path, tile: Tile) -> Path:
    return Path(workdir) / "emodnet" / f"{tile.lat0}_{tile.lon0}.tif"


class TileFetcher(Protocol):
    def __call__(self, url: str, destination: Path) -> None: ...


def _default_fetcher(url: str, destination: Path) -> None:
    """urllib, to a temp file, then an atomic rename, so a torn download is never cached."""
    partial = destination.with_suffix(".part")
    with urllib.request.urlopen(url, timeout=120) as response, partial.open("wb") as out:
        while chunk := response.read(1 << 20):
            out.write(chunk)
    os.replace(partial, destination)


def fetch_tiles(
    tiles: list[Tile], workdir: Path, fetcher: TileFetcher | None = None
) -> list[Path]:
    """Every tile on disk, fetching the missing ones; an existing file is trusted (C§13.4)."""
    fetch = fetcher if fetcher is not None else _default_fetcher
    paths: list[Path] = []
    for tile in tiles:
        path = tile_path(workdir, tile)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            url = wcs_url(tile)
            for attempt in range(1, _RETRIES + 1):
                try:
                    fetch(url, path)
                    break
                except OSError as exc:
                    if attempt == _RETRIES:
                        raise TileFetchFailed(
                            f"tile {url} failed {_RETRIES} times ({exc}); refusing to build "
                            "from partial bathymetry (C§6.1)"
                        ) from exc
                    time.sleep(2.0 * attempt)
        paths.append(path)
    return paths


def read_tile(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """`(elevation, pixel_lats, pixel_lons)`, coordinates at pixel CENTRES."""
    import rasterio  # lazy: the spatial extra (see module docstring)

    with rasterio.open(path) as src:
        elevation = src.read(1).astype("float64")
        transform = src.transform
        rows = np.arange(src.height)
        cols = np.arange(src.width)
        lons = transform.c + (cols + 0.5) * transform.a
        lats = transform.f + (rows + 0.5) * transform.e  # e is negative: north at row 0
    return elevation, lats, lons
```

Note: the tests do not exercise `time.sleep`'s duration; `_RETRIES` attempts with a dead fetcher take about 6 s. Acceptable for one test; do not add more that hit the retry path.

- [ ] **Step 4: Run the tests to verify they pass**

Run both selections as in Step 2. Expected: all pass; the retry test takes ~6 s.

- [ ] **Step 5: Commit**

```bash
git add src/seagarden_dst/refresh/sources/emodnet.py tests/test_refresh_emodnet.py
git commit -m "feat(refresh): EMODnet tile loop with a resumable cache and an injectable fetcher (C§13.4)"
```

---

### Task 3: The probe — a `GetCapabilities` parse

**Files:**
- Modify: `src/seagarden_dst/refresh/sources/emodnet.py`
- Test: `tests/test_refresh_emodnet.py`

**Interfaces:**
- Produces: `coverage_ids(xml: bytes) -> set[str]`; `class CapabilitiesReader(Protocol): def __call__(self) -> bytes: ...`; `_default_capabilities() -> bytes` (urllib, gzip-aware); `probe_coverage(name: str, *, capabilities: CapabilitiesReader | None = None) -> ProbeResult`

- [ ] **Step 1: Write the failing tests**

```python
# --- Probe: C§13.4 --------------------------------------------------------------------

_CAPS = b"""<?xml version="1.0"?>
<wcs:Capabilities xmlns:wcs="http://www.opengis.net/wcs/2.0">
  <wcs:Contents>
    <wcs:CoverageSummary><wcs:CoverageId>emodnet__mean</wcs:CoverageId></wcs:CoverageSummary>
    <wcs:CoverageSummary><wcs:CoverageId>emodnet__mean_2022</wcs:CoverageId></wcs:CoverageSummary>
  </wcs:Contents>
</wcs:Capabilities>"""


def test_coverage_ids_are_read_regardless_of_namespace_prefix():
    from seagarden_dst.refresh.sources.emodnet import coverage_ids

    assert coverage_ids(_CAPS) == {"emodnet__mean", "emodnet__mean_2022"}


def test_the_probe_is_ok_when_the_dated_coverage_is_listed():
    from seagarden_dst.refresh.sources.emodnet import probe_coverage

    result = probe_coverage("emodnet_bathy", capabilities=lambda: _CAPS)
    assert result.status == "ok" and result.reachable is True


def test_the_probe_reports_absent_when_the_service_answers_without_the_coverage():
    from seagarden_dst.refresh.sources.emodnet import probe_coverage

    gone = _CAPS.replace(b"emodnet__mean_2022", b"emodnet__mean_2024")
    result = probe_coverage("emodnet_bathy", capabilities=lambda: gone)
    assert result.status == "absent" and result.reachable is False
    assert "emodnet__mean_2022" in result.detail


def test_the_probe_reports_unreachable_on_a_transport_failure():
    from seagarden_dst.refresh.sources.emodnet import probe_coverage

    def dead() -> bytes:
        raise OSError("name resolution failed")

    result = probe_coverage("emodnet_bathy", capabilities=dead)
    assert result.status == "unreachable" and result.reachable is False
    assert "name resolution failed" in result.detail


def test_gzipped_capabilities_are_decompressed():
    """The live server gzips XML without being asked (C§13.1)."""
    import gzip

    from seagarden_dst.refresh.sources.emodnet import _decode_body

    assert _decode_body(gzip.compress(_CAPS), "gzip") == _CAPS
    assert _decode_body(_CAPS, None) == _CAPS
```

- [ ] **Step 2: Run to verify they fail**

Expected: `ImportError: cannot import name 'coverage_ids'` and siblings.

- [ ] **Step 3: Implement**

Add to `emodnet.py` (imports: `import gzip`, `import xml.etree.ElementTree as ET`, and `from seagarden_dst.refresh.layer import ProbeResult`):

```python
class CapabilitiesReader(Protocol):
    def __call__(self) -> bytes: ...


def _decode_body(body: bytes, content_encoding: str | None) -> bytes:
    if content_encoding and "gzip" in content_encoding.lower():
        return gzip.decompress(body)
    return body


_MAX_CAPABILITIES_BYTES = 8 << 20  # the live document is ~8 KB; anything near this is not it


def _default_capabilities() -> bytes:
    url = f"{WCS_URL}?SERVICE=WCS&VERSION=2.0.1&REQUEST=GetCapabilities"
    with urllib.request.urlopen(url, timeout=60) as response:
        body = response.read(_MAX_CAPABILITIES_BYTES + 1)
    if len(body) > _MAX_CAPABILITIES_BYTES:
        raise OSError(f"GetCapabilities exceeded {_MAX_CAPABILITIES_BYTES} bytes; refusing to parse")
    return _decode_body(body, response.headers.get("Content-Encoding"))


def coverage_ids(xml: bytes) -> set[str]:
    """Every `CoverageId` in a capabilities document, whatever prefix the server used."""
    root = ET.fromstring(xml)
    return {el.text.strip() for el in root.iter("{*}CoverageId") if el.text}


def probe_coverage(
    name: str, *, capabilities: CapabilitiesReader | None = None
) -> ProbeResult:
    """`ok` when the dated coverage is listed; `absent` when it is not; `unreachable`
    when the service cannot be asked. The version IS the coverage id, so drift is
    absence and there is no `version_drift` here (C§13.4)."""
    read = capabilities if capabilities is not None else _default_capabilities
    try:
        listed = coverage_ids(read())
    except (OSError, ET.ParseError) as exc:
        return ProbeResult(
            name=name, status="unreachable", reachable=False,
            detail=f"GetCapabilities failed: {exc}",
        )
    if COVERAGE_ID in listed:
        return ProbeResult(
            name=name, status="ok", reachable=True,
            detail=f"{COVERAGE_ID} listed by {WCS_URL}",
        )
    return ProbeResult(
        name=name, status="absent", reachable=False,
        detail=f"{COVERAGE_ID} is no longer listed; the service lists {sorted(listed)}",
    )
```

The parse is stdlib `xml.etree`, which never resolves external entities, and CPython's bundled expat (2.6+) caps entity amplification, so a hostile capabilities document cannot pull files or blow up memory; the size cap above bounds the rest. `defusedxml` is not a dependency and is not added for one 8 KB document.

Note `ProbeResult` lives in `refresh/layer.py`, which is stdlib+pydantic; importing it at module scope is fine (the Copernicus layers do the same).

- [ ] **Step 4: Run to verify they pass; commit**

```bash
git add src/seagarden_dst/refresh/sources/emodnet.py tests/test_refresh_emodnet.py
git commit -m "feat(refresh): EMODnet probe parses GetCapabilities for the dated coverage (C§13.4)"
```

---

### Task 4: The `EmodnetBathy` layer, registered, and the guard tightened

**Files:**
- Modify: `src/seagarden_dst/refresh/sources/emodnet.py`, `src/seagarden_dst/refresh/registry.py`
- Modify: `tests/test_refresh_registry.py`, `tests/test_refresh_cli.py`, `tests/refresh_builders.py`
- Regenerate: `tests/fixtures/data/manifest.json` via `scripts/make_fixture.py`
- Test: `tests/test_refresh_emodnet.py`

**Interfaces:**
- Produces: `class EmodnetBathy: name = "emodnet_bathy"; __init__(self, fetcher: TileFetcher | None = None, capabilities: CapabilitiesReader | None = None); probe(); build(grid, years, workdir) -> xr.Dataset; provenance() -> LayerProvenance; baseline_years() -> {"depth_mean_m": [], "depth_min_m": []}`
- Constants used by the fixture builder: `PRODUCT_ID = "EMODnet DTM 2022"`, `SOURCE = "EMODnet Bathymetry"`, `LICENCE = "EMODnet Bathymetry licence (CC BY 4.0)"`, `SOURCE_URL = "https://emodnet.ec.europa.eu/en/bathymetry"`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_refresh_emodnet.py`:

```python
# --- The layer: C§13.5 ----------------------------------------------------------------


def _write_tile(path: Path, elevation: np.ndarray, tile) -> None:
    import rasterio
    from rasterio.transform import from_origin

    rows, cols = elevation.shape
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path, "w", driver="GTiff", height=rows, width=cols, count=1, dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(tile.lon0, tile.lat1, (tile.lon1 - tile.lon0) / cols,
                              (tile.lat1 - tile.lat0) / rows),
    ) as dst:
        dst.write(elevation.astype("float32"), 1)


@pytest.mark.spatial
def test_build_emits_the_two_static_depth_fields_on_the_grid(tmp_path):
    from seagarden_dst.refresh.layer import YearRange
    from seagarden_dst.refresh.shapes import check_shapes
    from seagarden_dst.refresh.sources.emodnet import EmodnetBathy, Tile

    grid = tiny_grid()  # 55.0-55.05 N, 21.0-21.0555 E -> one tile, 55-56 / 21-22

    def fake_fetcher(url: str, destination: Path) -> None:
        # 960 x 960 would be slow to write; 96 x 96 keeps ~10 px per cell in lat.
        elevation = np.full((96, 96), -12.0)
        elevation[:, 48:] = 1.0  # eastern half is land
        _write_tile(destination, elevation, Tile(55.0, 56.0, 21.0, 22.0))

    layer = EmodnetBathy(fetcher=fake_fetcher)
    ds = layer.build(grid, YearRange(start=2024, end=2024), tmp_path)
    check_shapes(ds)
    assert set(ds.data_vars) == {"depth_mean_m", "depth_min_m"}
    np.testing.assert_allclose(ds["latitude"].values, grid.lats())
    np.testing.assert_allclose(ds["longitude"].values, grid.lons())
    assert ds["depth_mean_m"].dtype == np.dtype("float32")
    # The whole tiny grid sits in the wet western half of the tile.
    assert float(ds["depth_mean_m"].min()) == pytest.approx(12.0)
    assert float(ds["depth_min_m"].max()) == pytest.approx(12.0)


@pytest.mark.spatial
def test_build_ignores_the_year_range_because_bathymetry_is_static(tmp_path):
    from seagarden_dst.refresh.layer import YearRange
    from seagarden_dst.refresh.sources.emodnet import EmodnetBathy, Tile

    calls: list[str] = []

    def fake_fetcher(url: str, destination: Path) -> None:
        calls.append(url)
        _write_tile(destination, np.full((8, 8), -5.0), Tile(55.0, 56.0, 21.0, 22.0))

    layer = EmodnetBathy(fetcher=fake_fetcher)
    a = layer.build(tiny_grid(), YearRange(start=2020, end=2020), tmp_path)
    b = layer.build(tiny_grid(), YearRange(start=2025, end=2025), tmp_path)
    assert a.identical(b)
    assert len(calls) == 1, "the second build read the cached tile"
    assert "start" not in calls[0] and "2020" not in calls[0]


def test_baseline_windows_are_empty_and_present_for_both_fields():
    from seagarden_dst.refresh.sources.emodnet import EmodnetBathy

    assert EmodnetBathy().baseline_years() == {"depth_mean_m": [], "depth_min_m": []}


def test_provenance_pins_the_dated_coverage_and_is_pending_like_the_others():
    from seagarden_dst.refresh.sources.cmems import ARCHIVE_UNBLOCKED_BY
    from seagarden_dst.refresh.sources.emodnet import EmodnetBathy

    p = EmodnetBathy().provenance()
    assert (p.name, p.dataset_id, p.version) == ("emodnet_bathy", "emodnet__mean_2022", "2022")
    assert p.source == "EMODnet Bathymetry" and p.redistribution == "allowed"
    assert p.variables == ["depth_mean_m", "depth_min_m"]
    assert p.archive.status == "pending" and p.archive.unblocked_by == ARCHIVE_UNBLOCKED_BY
    assert "LAT" in p.product_id or "LAT" in p.licence or True  # datum is in the runbook, not here


def test_the_layer_probe_goes_through_the_capabilities_seam():
    from seagarden_dst.refresh.sources.emodnet import EmodnetBathy

    result = EmodnetBathy(capabilities=lambda: _CAPS).probe()
    assert result.name == "emodnet_bathy" and result.status == "ok"
```

Remove the `or True` line's trailing clause before committing: the assertion should read `assert p.product_id == "EMODnet DTM 2022"`.

Now the registry tests. In `tests/test_refresh_registry.py`:

```python
def test_all_five_C5_layers_are_registered():
    assert set(REGISTRY) == set(LAYER_NAMES)


def test_every_registered_name_is_one_C5_names():
    """Tightened to equality with emodnet_bathy (C§13.5)."""
    assert set(REGISTRY) == set(LAYER_NAMES)
```

replacing `test_the_four_copernicus_layers_are_registered` and the `<=` body. Add to `C11_1_CATALOGUE`:

```python
    "emodnet_bathy": ("emodnet__mean_2022", "2022"),  # C§13.1, checked 2026-09-19
```

In `tests/test_refresh_cli.py`, replace `test_a_refresh_with_an_incomplete_registry_refuses_before_the_download` with:

```python
def test_a_refresh_with_a_layer_missing_refuses_before_the_download(monkeypatch, capsys):
    """The guard stays: if a layer is ever unregistered again, a refresh must refuse
    before opening a single Copernicus dataset over the wire."""
    import scripts.refresh_layers as cli

    monkeypatch.setattr(
        cli,
        "REGISTRY",
        {
            "copernicus_phy": FakeLayer("copernicus_phy", ["temp_c"]),
            "copernicus_bgc": FakeLayer("copernicus_bgc", ["din_umol_l"]),
            "copernicus_bgc_light": FakeLayer("copernicus_bgc_light", []),
            "copernicus_wav": FakeLayer("copernicus_wav", ["significant_wave_m"]),
        },
    )
    with pytest.raises(SystemExit) as excinfo:
        main(["--start-year", "2024", "--end-year", "2024"])
    assert excinfo.value.code != 0
    assert "emodnet_bathy" in capsys.readouterr().err
```

and rename `test_probe_still_reports_all_four_layers_with_an_incomplete_registry` to `test_probe_reports_whatever_is_registered_even_when_a_layer_is_missing`, body unchanged. Then read the rest of `test_refresh_cli.py` for any `== 4` or "four" assumption about the live `REGISTRY` and update it to five.

In `tests/refresh_builders.py`, the `emodnet_bathy` record becomes:

```python
        layer(
            name="emodnet_bathy",
            dataset_id=emodnet.COVERAGE_ID,
            version=emodnet.VERSION,
            source=emodnet.SOURCE,
            product_id=emodnet.PRODUCT_ID,
            licence=emodnet.LICENCE,
            source_url=emodnet.SOURCE_URL,
            archive=Archive(
                status="pending",
                source_url=emodnet.SOURCE_URL,
                unblocked_by="the Zenodo deposit is outside package C (C1)",
            ),
            variables=["depth_mean_m", "depth_min_m"],
        ),
```

with `from seagarden_dst.refresh.sources import emodnet` at the top of the builders module (it is stdlib+numpy at module scope, so this is safe for the default selection).

- [ ] **Step 2: Run to verify failures**

Run: `MKL_THREADING_LAYER=SEQUENTIAL python -m pytest tests/test_refresh_emodnet.py tests/test_refresh_registry.py tests/test_refresh_cli.py -q -p no:cacheprovider`
Expected: the emodnet layer tests fail on `cannot import name 'EmodnetBathy'`; `test_all_five...` fails with `emodnet_bathy` missing from the registry; `test_the_catalogue_table_covers_exactly...` fails; the builders import fails until the constants exist.

- [ ] **Step 3: Implement the layer and register it**

Add to `emodnet.py` (imports: `from datetime import UTC, datetime`; `from seagarden_dst.artifact.manifest import Archive, LayerProvenance`; `from seagarden_dst.refresh.sources.cmems import ARCHIVE_UNBLOCKED_BY`; under `TYPE_CHECKING`: `import xarray as xr` and `from seagarden_dst.refresh.layer import YearRange`):

```python
SOURCE = "EMODnet Bathymetry"
PRODUCT_ID = "EMODnet DTM 2022"
LICENCE = "EMODnet Bathymetry licence (CC BY 4.0)"
SOURCE_URL = "https://emodnet.ec.europa.eu/en/bathymetry"
VARIABLES = ["depth_mean_m", "depth_min_m"]


class EmodnetBathy:
    """One layer, one dataset: the 2022 DTM, reduced onto the artifact grid (C§13)."""

    name = "emodnet_bathy"

    def __init__(
        self,
        fetcher: TileFetcher | None = None,
        capabilities: CapabilitiesReader | None = None,
    ) -> None:
        self._fetcher = fetcher
        self._capabilities = capabilities

    def probe(self) -> ProbeResult:
        return probe_coverage(self.name, capabilities=self._capabilities)

    def build(self, grid: GridSpec, years: YearRange, workdir: Path) -> xr.Dataset:
        """Static: `years` is accepted for the protocol and ignored (C§13.5)."""
        import xarray as xr

        del years
        accumulator = GridAccumulator(grid)
        for path in fetch_tiles(tiles_for(grid), Path(workdir), self._fetcher):
            elevation, lats, lons = read_tile(path)
            accumulator.add(elevation, lats, lons)
        mean, minimum = accumulator.finish()
        dims = ("latitude", "longitude")
        return xr.Dataset(
            {
                "depth_mean_m": (dims, mean.astype("float32")),
                "depth_min_m": (dims, minimum.astype("float32")),
            },
            coords={"latitude": grid.lats(), "longitude": grid.lons()},
        )

    def provenance(self) -> LayerProvenance:
        return LayerProvenance(
            name=self.name,
            source=SOURCE,
            product_id=PRODUCT_ID,
            dataset_id=COVERAGE_ID,
            version=VERSION,
            retrieved_on=datetime.now(UTC),
            licence=LICENCE,
            redistribution="allowed",
            source_url=SOURCE_URL,
            archive=Archive(
                status="pending", source_url=SOURCE_URL, unblocked_by=ARCHIVE_UNBLOCKED_BY
            ),
            variables=list(VARIABLES),
        )

    def baseline_years(self) -> dict[str, list[int]]:
        return {name: [] for name in VARIABLES}
```

Check how the Copernicus layers set `retrieved_on` in `cmems.copernicus_provenance` and match it exactly (if they take it from a module-level clock or a `now()` helper, use the same one).

In `registry.py`: add `from seagarden_dst.refresh.sources.emodnet import EmodnetBathy`, add `EmodnetBathy()` to the tuple, delete the "not yet implemented" comment block, change `check_registered_names` to:

```python
    unknown = sorted(set(registry) - set(names))
    missing = sorted(set(names) - set(registry))
    if unknown or missing:
        raise RuntimeError(
            f"registry and LAYER_NAMES disagree: not named {unknown}, not registered "
            f"{missing} (C§5, tightened to equality with emodnet_bathy per C§13.5)"
        )
```

and rewrite its docstring to say the comparison is equality as of C-d, keeping the `raise`-not-`assert` paragraph. Update `tests/test_refresh_registry.py::test_an_unnamed_layer_in_the_registry_is_refused` to `match="not named \\['not_a_layer_C5_names'\\]"` and add:

```python
def test_a_named_layer_missing_from_the_registry_is_refused():
    partial = {k: v for k, v in REGISTRY.items() if k != "emodnet_bathy"}
    with pytest.raises(RuntimeError, match="not registered \\['emodnet_bathy'\\]"):
        check_registered_names(partial, LAYER_NAMES)
```

- [ ] **Step 4: Regenerate the fixture and run everything**

```bash
MKL_THREADING_LAYER=SEQUENTIAL python scripts/make_fixture.py
git diff --stat tests/fixtures/data/
```

Expected: only `manifest.json` changes (the `emodnet_bathy` record's `dataset_id`, `version`, `product_id`, `licence`); `forcing.nc` unchanged. If `forcing.nc` changed, stop: the fixture generator is not deterministic and that is a finding to report, not to commit around.

Run: `MKL_THREADING_LAYER=SEQUENTIAL python -m pytest -q -p no:cacheprovider` and `... -m spatial tests/`, then `ruff check .`
Expected: all green in both selections, ruff clean.

- [ ] **Step 5: Commit**

```bash
git add src/seagarden_dst/refresh/sources/emodnet.py src/seagarden_dst/refresh/registry.py \
        tests/test_refresh_emodnet.py tests/test_refresh_registry.py tests/test_refresh_cli.py \
        tests/refresh_builders.py tests/fixtures/data/manifest.json
git commit -m "feat(refresh): register emodnet_bathy, the fifth layer, and tighten the registry guard to equality (C§13.5)"
```

---

### Task 5: Say so everywhere that said the layer was outstanding

**Files:**
- Modify: `pyproject.toml` (the `spatial` extra comment), `README.md` (the "Light attenuation"/"Site conditions" stub rows mention package D; add nothing there, but the module table line for `forcing.py` says STUBBED — leave), `CHANGELOG.md` `[Unreleased]`
- Modify: `src/seagarden_dst/refresh/sources/__init__.py` if it lists layers

- [ ] **Step 1: Find every claim**

```bash
grep -rn "emodnet_bathy\|outstanding one\|four of the five\|four Copernicus layers\|seven of the nine" --include=*.py --include=*.toml --include=*.md . | grep -v "\.claude/\|\.superpowers/\|docs/superpowers/plans/"
```

- [ ] **Step 2: Rewrite each**

- `pyproject.toml`: the comment paragraph "Four of the five layers landed with package C-c1 — `emodnet_bathy` is the outstanding one — so a refresh run still exits 1 ..." becomes "All five layers are registered as of package C-d, so a refresh builds a complete artifact; see `docs/runbooks/annual-refresh.md`."
- `CHANGELOG.md` `[Unreleased]`: replace "Nothing yet." with

```markdown
### Added

- **The fifth layer, `emodnet_bathy`** (package C-d): EMODnet's 2022 DTM, fetched as 1°
  tiles over WCS with a resumable cache, reduced onto the artifact grid as the mean and
  shallowest wet depth per cell, referenced to LAT. A refresh now produces every variable
  the manifest requires, and the registry guard is tightened to equality.
- **The annual-refresh runbook**, `docs/runbooks/annual-refresh.md`, with volumes,
  runtimes, the institutional-credential rule, and where the artifact lives on laguna.
```

- [ ] **Step 3: Run the default suite and ruff; commit**

```bash
git add pyproject.toml CHANGELOG.md README.md src/seagarden_dst/refresh/sources/__init__.py
git commit -m "docs: the refresh registry is complete; say so where the code said otherwise"
```

(Only add files that actually changed.)

---

### Task 6: The annual-refresh runbook, and a test that it carries what C§8.1 lists

**Files:**
- Create: `docs/runbooks/annual-refresh.md`
- Create: `tests/test_runbooks.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_runbooks.py
"""The runbooks are deliverables (C§8.1, deploy §7), so their required content is
checked the way the workflows are: a document that lost its volume figure is one
somebody abandons halfway."""

from __future__ import annotations

from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_REFRESH = _ROOT / "docs" / "runbooks" / "annual-refresh.md"


def _text() -> str:
    return _REFRESH.read_text(encoding="utf-8")


def test_the_refresh_runbook_exists():
    assert _REFRESH.exists()


@pytest.mark.parametrize(
    "required",
    [
        "institutional",              # the credential rule (C§8.1)
        "30.5 GB",                    # on the wire, revised by C§13.7
        "~170 MB",                    # on disk
        "SEAGARDEN_DATA_DIR",         # where the service reads (C§13.6)
        "~/seagarden-data/forcing",   # outside the serving checkout (C§13.6)
        "--start-year",
        "--probe",
        "sha256",                     # how to verify
        "pending",                    # the committed vs deposited manifest sequence
        "Zenodo",
        "LAT",                        # the bathymetry datum (C§13.2)
        "check_grid",                 # the convention to confirm on the first run (C§13.3)
    ],
)
def test_the_refresh_runbook_carries_what_C8_1_lists(required):
    assert required in _text(), f"annual-refresh.md no longer mentions {required!r}"


def test_the_refresh_runbook_names_every_C6_1_failure_mode():
    spec = (_ROOT / "docs/superpowers/specs/2026-09-15-package-c-refresh-tooling-design.md")
    section = spec.read_text(encoding="utf-8").split("### C§6.1 Failure modes")[1].split("## C§7")[0]
    headings = [line.strip("*- ").split("**")[1] for line in section.splitlines()
                if line.startswith("- **")]
    assert headings, "C§6.1 lost its bulleted failure modes; update this test"
    text = _text()
    missing = [h for h in headings if h not in text]
    assert not missing, f"runbook does not name these C§6.1 failure modes: {missing}"
```

Before writing the last test, read C§6.1 and confirm its failure modes are bullets beginning `- **Name**`. If the format differs, adapt the parse to match the real structure, not the other way round.

- [ ] **Step 2: Run to verify it fails**

Expected: `test_the_refresh_runbook_exists` fails on `assert False`; the parametrised tests error on `FileNotFoundError`.

- [ ] **Step 3: Write the runbook**

`docs/runbooks/annual-refresh.md`, in the register of `deploy.md` (audience: someone who is not the author; say what a failure looks like, not only what to type). Sections, each with real content:

1. **What this does and when**: rebuilds `forcing.nc` + `manifest.json` for a year range from Copernicus Marine and EMODnet; once a year, or when the source probe reports drift.
2. **Prerequisites**: the `shiny` env on laguna (`/opt/micromamba/envs/shiny`, has `[spatial]`); the Copernicus credential is **institutional, never personal**, held in `~/.copernicusmarine/.copernicusmarine-credentials` on laguna; no EMODnet credential is needed; ~1 GB free in the workdir, ~200 MB in the target; hours of wall-clock.
3. **Where things go**: target `~/seagarden-data/forcing`, **never** inside `~/seagarden-dst` (the serving tree; a dirty tree fails the deploy preflight); workdir `~/seagarden-data/work`; the service reads the target through `SEAGARDEN_DATA_DIR=/home/razinka/seagarden-data` in the unit's environment.
4. **Volumes and runtime**: ~30.5 GB over the wire (0.59 GB monthly fields, 3.6 GB daily `zsd`, 25.8 GB hourly waves, 0.5 GB bathymetry once), ~170 MB on disk plus ~530 MB of cached bathymetry tiles; hours, waves dominating.
5. **The commands**:

```bash
cd ~/seagarden-dst
P=/opt/micromamba/envs/shiny/bin/python3
$P scripts/refresh_layers.py --probe                       # every layer must report ok
mkdir -p ~/seagarden-data/forcing ~/seagarden-data/work
nohup $P scripts/refresh_layers.py --start-year 2023 --end-year 2025 \
   --target ~/seagarden-data/forcing --workdir ~/seagarden-data/work \
   > ~/seagarden-data/refresh-$(date +%F).log 2>&1 &
```

6. **What success looks like**: the log ends with the pair's paths; `manifest.json` has `artifact_sha256` matching `sha256sum forcing.nc`; every layer `archive.status: pending`; `$P -c "from seagarden_dst.gridded import GriddedForcing; ..."` loads it.
7. **The convention to confirm on the first run** (C§13.3): if the build fails in `check_grid` naming a Copernicus layer, the reanalysis labels cells by centre while `GridSpec` uses lower edges; stop, report, and do not patch the bathymetry layer.
8. **Failure modes**: each C§6.1 mode by name, what it looks like in the log, what to do. Plus `TileFetchFailed` (EMODnet): re-run, the tile cache resumes.
9. **Deposit and record the DOI**: the C§8.1 sequence; the deposited and committed manifests differ and why; copy `manifest.json` into the repo at `data/forcing/manifest.json` **without** the artifact, commit.
10. **Wire the service**: add `Environment=SEAGARDEN_DATA_DIR=/home/razinka/seagarden-data` to `seagarden-dst.service` in the `seagarden` repo's `deploy/`, restart per `deploy.md`, confirm the Site panel banner reads "gridded forcing artifact".
11. **Who to contact**: the About box email.

- [ ] **Step 4: Run to verify the tests pass; commit**

```bash
git add docs/runbooks/annual-refresh.md tests/test_runbooks.py
git commit -m "docs(runbook): the annual refresh, with volumes, the credential rule, and where the artifact lives (C§8.1)"
```

---

### Task 7: The first real refresh, on laguna, by the user

**Files:**
- Create: `docs/2026-09-XX-first-refresh.md` (date it the day it runs)
- Possibly create: `data/forcing/manifest.json` (committed, per C§13.6)

This task is executed by the user following Task 6's runbook, because the permission classifier denies the assistant deploy-class commands on laguna and the run uses the institutional credential. The assistant's part is the preparation and the record.

- [ ] **Step 1: Preflight, read-only (assistant)**

```bash
ssh razinka@laguna.ku.lt 'cd ~/seagarden-dst && git fetch -q --tags && git describe --tags --always && df -h ~ | tail -1 && ls ~/.copernicusmarine'
```

Expected: the tag that contains Tasks 1–6, ≥ 5 GB free, the credentials file present.

- [ ] **Step 2: Probe, then run (user)**

The user runs the runbook's section 5 in their own terminal. The assistant waits; no polling loop.

- [ ] **Step 3: Verify (assistant, read-only)**

```bash
ssh razinka@laguna.ku.lt 'cd ~/seagarden-data/forcing && ls -la && sha256sum forcing.nc && python3 -c "import json;m=json.load(open(\"manifest.json\"));print(m[\"artifact_sha256\"], m[\"grid\"][\"n_lat\"], m[\"grid\"][\"n_lon\"], [l[\"name\"] for l in m[\"layers\"]])"'
```

Expected: sha matches; grid 390 × 630; five layers.

- [ ] **Step 4: Record the run**

`docs/2026-09-XX-first-refresh.md`: date, years, wall-clock, bytes moved per layer if the log says, the sha, any failure mode hit and how it resolved, and the `check_grid` outcome of C§13.3. If `check_grid` failed on a Copernicus layer, this document is the finding and the package stops here with a follow-up task written for `cmems.open_window`.

- [ ] **Step 5: Commit the manifest copy and the record**

```bash
mkdir -p data/forcing && scp razinka@laguna.ku.lt:~/seagarden-data/forcing/manifest.json data/forcing/manifest.json
git add data/forcing/manifest.json docs/2026-09-*-first-refresh.md
git commit -m "data: the first real refresh's manifest, and the record of the run"
```

Check `.gitignore` covers `data/forcing/forcing.nc` first; add the line if it does not.

---

## Self-review

**Spec coverage.** C§13.1 dated coverage → Task 2 constants and Task 3 probe. C§13.2 sign, wet rule, datum → Task 1 tests, runbook Task 6. C§13.3 centre binning, no-wet NaN, extent drop, the convention to confirm → Task 1, Task 6 section 7, Task 7. C§13.4 tile loop, cache, retries, GeoTIFF, stdlib probe, gzip → Tasks 2–3. C§13.5 provenance, `[]` baselines, equality guard, fixture constants → Task 4. C§13.6 target outside the checkout, `SEAGARDEN_DATA_DIR`, committed manifest → Tasks 6–7. C§13.7 volumes → Task 6 and its test. C§8.1 runbook contents → Task 6. C§10 clause 1 (a refresh builds a complete artifact) → Task 4 + Task 7. Clause 7 remains open by design.

**Placeholders.** None: every step has its code or its exact command. Task 6's runbook is specified section by section with the figures it must carry.

**Type consistency.** `GridAccumulator.add(elevation, pixel_lats, pixel_lons)` in Tasks 1 and 4; `fetch_tiles(tiles, workdir, fetcher)` in Tasks 2 and 4; `read_tile(path) -> (elevation, lats, lons)` in Tasks 2 and 4; `probe_coverage(name, *, capabilities)` in Tasks 3 and 4; `TileFetcher.__call__(url, destination)` everywhere.

**Known risk, carried openly.** `check_grid` against real Copernicus coordinates has never been observed. It is the first thing the first run will test, it is written into the runbook and the record, and the plan stops rather than patches if it fails.
