# Package C-c1 — the four Copernicus layers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the four Copernicus refresh layers against the frozen C-b `Layer` protocol and register them, so a refresh builds eight of the artifact's nine variables from real sources.

**Architecture:** Four thin layer classes, one shared client seam, no base class. `Layer` is a `Protocol` (C§5 chose structural typing deliberately), so each layer is a small standalone class implementing five members. All Copernicus access goes through `refresh/sources/cmems.py`, which wraps `copernicusmarine.open_dataset` behind an injectable callable returning `xr.Dataset` — tests inject a fake returning a synthetic Dataset, so every transform is proven with no network and no credential. Reachability is a separate stdlib-only module because the probe workflow installs no spatial extra.

**Tech Stack:** Python 3.11+, xarray, copernicusmarine 2.4, pydantic v2, pytest. Environment is micromamba `shiny` — run everything with `micromamba run -n shiny <cmd>`.

**Spec:** `docs/superpowers/specs/2026-09-15-package-c-refresh-tooling-design.md` (C§3.2, C§3.4, C§4.4, C§5, C§8.2)

## Global Constraints

- **R1 — the baseline window is stashed during `build()`.** `baseline_years()` takes no argument and `REGISTRY` holds instances constructed at import, so a yearly layer learns its window from the `YearRange` handed to `build()`. `driver.py:160` calls `build()` before `driver.py:174` calls `baseline_years()`, so this works today. Each layer stores the range on `self` in `build()` and **raises `RuntimeError` if `baseline_years()` is called first** — the ordering becomes enforced and tested rather than implicit.
- **R2 — the seam returns `xr.Dataset`, never a `Path`.** Use `copernicusmarine.open_dataset` (lazy, ARCO-backed), not `copernicusmarine.subset` (downloads to file). `copernicus_wav` reduces 25.8 GB of hourly `VHM0` to a monthly p95; a `subset`-to-file route would land the raw hours on a disk with 31 GB free.
- **R3 — no module-scope spatial imports.** `registry.py` is imported by `scripts/refresh_layers.py`, which the monthly probe job runs after `pip install -e .` — the **bare package, no `[spatial]` extra**. Any module-scope `import xarray` or `import copernicusmarine` in a layer module or in `cmems.py` breaks the probe job *and* the default CI run (`pyproject.toml:126` sets `addopts = "-m 'not engines and not e2e and not spatial'"`). Import inside methods only; use `if TYPE_CHECKING:` for annotations.
- **R4 — `probe()` uses the standard library only.** Follows from R3: `copernicusmarine` is not installed where the probe runs. Reachability is an HTTP check via `urllib.request`.
- **Dims are long form**: `("year", "month", "latitude", "longitude")` for yearly, `("month", "latitude", "longitude")` for `significant_wave_m`. `shapes.py:19` defines `SPATIAL_DIMS = ("latitude", "longitude")`. A `lat`/`lon` emission is refused downstream.
- **No unit conversion anywhere in this package.** `no3`/`nh4`/`po4` are mmol m⁻³ ≡ µmol L⁻¹; `so` is numerically psu; `thetao` is °C.
- **Surface level is 0.50 m**, the shallowest of the reanalysis's 56 levels — requested as a depth window of 0.0–1.0 m. This is a *model* level and is unrelated to EMODnet seabed depth.
- **`archive.status` is `pending`** for all four layers, which requires both a `source_url` and an `unblocked_by` note (`manifest.py:54-61`).
- **Line length 100** (`[tool.ruff]`), target py311. Run `micromamba run -n shiny ruff check .` before each commit.
- **The CLI's refresh branch refuses while `REGISTRY` is incomplete** (Task 7, Step 3b).
  Filling the registry removes the empty-registry guard's protection, and without a
  replacement a refresh would fail after the download instead of before it.
- **Out of scope — this is C-c2:** `emodnet_bathy`, the `rioxarray` regrid, the free-disk precheck, the measured transfer slice, and `docs/runbooks/annual-refresh.md`.

---

## File Structure

| File | Responsibility |
|---|---|
| `src/seagarden_dst/refresh/sources/__init__.py` | Package marker. No imports — R3. |
| `src/seagarden_dst/refresh/sources/reachability.py` | Stdlib-only HTTP reachability. No spatial import ever. |
| `src/seagarden_dst/refresh/sources/cmems.py` | The one Copernicus seam: lazy open + shared reshape helpers. |
| `src/seagarden_dst/refresh/sources/phy.py` | `CopernicusPhy` — `salinity_psu`, `temp_c`. |
| `src/seagarden_dst/refresh/sources/bgc.py` | `CopernicusBgc` — `din_umol_l`, `dip_umol_l`. |
| `src/seagarden_dst/refresh/sources/bgc_light.py` | `CopernicusBgcLight` — `light_attenuation_k`. |
| `src/seagarden_dst/refresh/sources/wav.py` | `CopernicusWav` — `significant_wave_m`. |
| `src/seagarden_dst/refresh/registry.py` | **Modify** — fill `REGISTRY`, add the subset assertion. |
| `tests/test_refresh_reachability.py` | Probe helper tests. Unmarked. |
| `tests/test_refresh_cmems.py` | Seam and reshape tests. Marked `spatial`. |
| `tests/test_refresh_sources.py` | The four layers' transform and provenance tests. Marked `spatial`. |
| `tests/test_refresh_registry.py` | Registry contents and import-purity tests. Unmarked. |

---

## Task 1: The stdlib-only reachability helper

**Files:**
- Create: `src/seagarden_dst/refresh/sources/__init__.py`
- Create: `src/seagarden_dst/refresh/sources/reachability.py`
- Test: `tests/test_refresh_reachability.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `url_reachable(url: str, *, timeout: float = 30.0, opener: Callable | None = None) -> tuple[bool, str]` — returns `(reachable, detail)`. Every layer's `probe()` calls this.

- [ ] **Step 1: Write the failing test**

Create `tests/test_refresh_reachability.py`:

```python
"""The probe path, which must work with the bare package installed (R4)."""

from __future__ import annotations

import urllib.error

import pytest

from seagarden_dst.refresh.sources.reachability import url_reachable


class _FakeResponse:
    def __init__(self, status: int) -> None:
        self.status = status

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def test_a_200_is_reachable():
    reachable, detail = url_reachable("https://example.invalid/x", opener=lambda *a, **k: _FakeResponse(200))
    assert reachable is True
    assert "200" in detail


def test_a_404_is_not_reachable_and_says_so():
    def raise_404(*args: object, **kwargs: object) -> None:
        raise urllib.error.HTTPError("https://example.invalid/x", 404, "Not Found", {}, None)

    reachable, detail = url_reachable("https://example.invalid/x", opener=raise_404)
    assert reachable is False
    assert "404" in detail


def test_a_network_failure_is_reported_not_raised():
    def raise_urlerror(*args: object, **kwargs: object) -> None:
        raise urllib.error.URLError("name resolution failed")

    reachable, detail = url_reachable("https://example.invalid/x", opener=raise_urlerror)
    assert reachable is False
    assert "unreachable" in detail


def test_the_module_imports_without_the_spatial_stack(monkeypatch):
    """R3/R4: nothing on the probe path may need xarray or copernicusmarine."""
    import sys

    monkeypatch.setitem(sys.modules, "xarray", None)
    monkeypatch.setitem(sys.modules, "copernicusmarine", None)
    import importlib

    import seagarden_dst.refresh.sources.reachability as module

    importlib.reload(module)  # would raise if either import were at module scope
    assert module.url_reachable is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `micromamba run -n shiny python -m pytest tests/test_refresh_reachability.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'seagarden_dst.refresh.sources'`

- [ ] **Step 3: Write minimal implementation**

Create `src/seagarden_dst/refresh/sources/__init__.py`:

```python
"""The five layer implementations (C§5).

Deliberately empty of imports: `registry.py` imports the layer modules and is itself
imported by the probe job, which installs the bare package. A convenience re-export
here would drag every layer module — and their method-scoped spatial imports stay
method-scoped only if nothing forces them earlier.
"""
```

Create `src/seagarden_dst/refresh/sources/reachability.py`:

```python
"""Whether a source still answers, using the standard library only (C§8.2, R4).

The monthly probe workflow installs the BARE package — `.github/workflows/
source-probe.yml` runs `pip install -e .` with no `[spatial]` extra — so nothing on
the probe path may import `copernicusmarine` or `xarray`. A reachability check that
needed the scientific stack would depend on the very thing it exists to avoid
needing, and would report a broken environment as a broken catalogue.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from collections.abc import Callable

# Long enough for a slow catalogue, short enough that five dead sources do not hang
# a monthly job past its timeout.
DEFAULT_TIMEOUT: float = 30.0


def url_reachable(
    url: str,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    opener: Callable[..., object] | None = None,
) -> tuple[bool, str]:
    """Ask whether `url` answers. Returns `(reachable, detail)`, never raises.

    `opener` is the injection seam: tests pass a callable, production gets
    `urllib.request.urlopen`. A probe that raised would turn one dead source into a
    failed job reporting nothing about the other four.
    """
    open_url = opener if opener is not None else urllib.request.urlopen
    request = urllib.request.Request(url, method="HEAD")
    try:
        with open_url(request, timeout=timeout) as response:  # type: ignore[union-attr]
            status = getattr(response, "status", None)
    except urllib.error.HTTPError as error:
        return False, f"HTTP {error.code}"
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        return False, f"unreachable: {error}"

    if status is not None and 200 <= int(status) < 400:
        return True, f"HTTP {status}"
    return False, f"HTTP {status}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `micromamba run -n shiny python -m pytest tests/test_refresh_reachability.py -v`
Expected: 4 passed

- [ ] **Step 5: Lint and commit**

```bash
micromamba run -n shiny ruff check src/seagarden_dst/refresh/sources/ tests/test_refresh_reachability.py
git add src/seagarden_dst/refresh/sources/__init__.py src/seagarden_dst/refresh/sources/reachability.py tests/test_refresh_reachability.py
git commit -m "feat(refresh): add the stdlib-only reachability probe (R4)

The probe workflow installs the bare package, so probe() cannot reach for
copernicusmarine. HTTP HEAD via urllib, with the opener injected so the four
layers' probes are provable offline.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: The Copernicus client seam

**Files:**
- Create: `src/seagarden_dst/refresh/sources/cmems.py`
- Test: `tests/test_refresh_cmems.py`

**Interfaces:**
- Consumes: `GridSpec` (`artifact/grid.py`), `YearRange` (`refresh/layer.py`).
- Produces:
  - `DatasetOpener` — a `Protocol` for the injected callable.
  - `open_window(dataset_id: str, variables: list[str], grid: GridSpec, years: YearRange, *, opener: DatasetOpener | None = None, surface: bool = True) -> xr.Dataset`
  - `to_yearly(data: xr.DataArray) -> xr.DataArray` — monthly `time` series → `(year, month, latitude, longitude)`
  - `SURFACE_MIN_DEPTH: float`, `SURFACE_MAX_DEPTH: float`

- [ ] **Step 1: Write the failing test**

Create `tests/test_refresh_cmems.py`:

```python
"""The one seam between the layers and Copernicus (R2)."""

from __future__ import annotations

import numpy as np
import pytest

from seagarden_dst.artifact.grid import GridSpec
from seagarden_dst.refresh.layer import YearRange

pytestmark = pytest.mark.spatial


def _tiny_grid() -> GridSpec:
    """A 3x3 grid, the fixture's shape (C§7)."""
    return GridSpec(
        crs="EPSG:4326",
        lat_min=54.0, lat_max=54.05, lon_min=10.0, lon_max=10.09,
        lat_step=0.016666, lon_step=0.027777,
        n_lat=3, n_lon=3,
    )


def _monthly_dataset(years: list[int], value: float = 1.0):
    import pandas as pd
    import xarray as xr

    times = pd.date_range(f"{years[0]}-01-01", f"{years[-1]}-12-01", freq="MS")
    grid = _tiny_grid()
    data = np.full((len(times), 3, 3), value, dtype="float32")
    return xr.Dataset(
        {"so": (("time", "latitude", "longitude"), data)},
        coords={"time": times, "latitude": grid.lats(), "longitude": grid.lons()},
    )


def test_open_window_passes_the_grid_extent_and_the_surface_depth():
    from seagarden_dst.refresh.sources import cmems

    seen: dict[str, object] = {}

    def fake_opener(**kwargs: object):
        seen.update(kwargs)
        return _monthly_dataset([2024])

    cmems.open_window("ds-id", ["so"], _tiny_grid(), YearRange(start=2024, end=2024), opener=fake_opener)

    assert seen["dataset_id"] == "ds-id"
    assert seen["variables"] == ["so"]
    assert seen["minimum_latitude"] == 54.0
    assert seen["maximum_longitude"] == 10.09
    assert seen["minimum_depth"] == cmems.SURFACE_MIN_DEPTH
    assert seen["maximum_depth"] == cmems.SURFACE_MAX_DEPTH
    assert seen["start_datetime"].startswith("2024-01-01")
    assert seen["end_datetime"].startswith("2024-12-31")


def test_open_window_omits_depth_when_the_product_has_no_depth_axis():
    """The wave product is 2-D; asking it for a depth window is an error."""
    from seagarden_dst.refresh.sources import cmems

    seen: dict[str, object] = {}

    def fake_opener(**kwargs: object):
        seen.update(kwargs)
        return _monthly_dataset([2024])

    cmems.open_window(
        "wav", ["VHM0"], _tiny_grid(), YearRange(start=2024, end=2024),
        opener=fake_opener, surface=False,
    )

    assert "minimum_depth" not in seen
    assert "maximum_depth" not in seen


def test_to_yearly_splits_time_into_year_and_month_in_that_order():
    from seagarden_dst.refresh.sources import cmems

    reshaped = cmems.to_yearly(_monthly_dataset([2024, 2025])["so"])

    assert tuple(reshaped.dims) == ("year", "month", "latitude", "longitude")
    assert list(reshaped["year"].values) == [2024, 2025]
    assert list(reshaped["month"].values) == list(range(1, 13))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `micromamba run -n shiny python -m pytest tests/test_refresh_cmems.py -v -m spatial`
Expected: FAIL — `ImportError: cannot import name 'cmems'`

- [ ] **Step 3: Write minimal implementation**

Create `src/seagarden_dst/refresh/sources/cmems.py`:

```python
"""The one seam between the refresh layers and Copernicus Marine (C§5, R2, R3).

Two rules hold this module together.

**It opens, it does not download (R2).** `copernicusmarine.open_dataset` returns a
lazy, ARCO-backed Dataset; `copernicusmarine.subset` writes a file. `copernicus_wav`
reduces ~25.8 GB of hourly `VHM0` to a monthly p95, and the lazy route never lands
those hours on disk. Package B used `subset` because it was measuring file sizes;
that is not what a refresh needs.

**Nothing spatial is imported at module scope (R3).** `registry.py` imports the layer
modules, which import this one, and `registry.py` is imported by the probe job after
`pip install -e .` with no `[spatial]` extra. `import copernicusmarine` therefore
lives inside `_default_opener`, and `xarray` appears only under `TYPE_CHECKING`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:  # pragma: no cover - typing only
    import xarray as xr

    from seagarden_dst.artifact.grid import GridSpec
    from seagarden_dst.refresh.layer import YearRange

# The surface model level, 0.50 m, is the shallowest of the reanalysis's 56 (C§3.2).
# Requested as a window rather than a point because the level's exact centre is a
# product detail; 0-1 m selects it and nothing below it.
SURFACE_MIN_DEPTH: float = 0.0
SURFACE_MAX_DEPTH: float = 1.0


class DatasetOpener(Protocol):
    """What `open_window` calls. The injection seam every layer test uses."""

    def __call__(self, **kwargs: Any) -> xr.Dataset: ...


def _default_opener() -> DatasetOpener:
    """Resolve the real opener, importing inside the call (R3)."""
    import copernicusmarine

    return copernicusmarine.open_dataset


def open_window(
    dataset_id: str,
    variables: list[str],
    grid: GridSpec,
    years: YearRange,
    *,
    opener: DatasetOpener | None = None,
    surface: bool = True,
) -> xr.Dataset:
    """Open `variables` from `dataset_id` over the grid extent and year span.

    `surface=False` for products with no depth axis — the wave product is 2-D, and
    handing it a depth window is an error rather than a no-op.
    """
    open_dataset = opener if opener is not None else _default_opener()
    request: dict[str, Any] = {
        "dataset_id": dataset_id,
        "variables": list(variables),
        "minimum_longitude": grid.lon_min,
        "maximum_longitude": grid.lon_max,
        "minimum_latitude": grid.lat_min,
        "maximum_latitude": grid.lat_max,
        "start_datetime": f"{years.start}-01-01T00:00:00",
        "end_datetime": f"{years.end}-12-31T23:59:59",
    }
    if surface:
        request["minimum_depth"] = SURFACE_MIN_DEPTH
        request["maximum_depth"] = SURFACE_MAX_DEPTH
    return open_dataset(**request)


def to_yearly(data: xr.DataArray) -> xr.DataArray:
    """Reshape a monthly `time` series into C§3.2's yearly shape.

    `(time, latitude, longitude)` -> `(year, month, latitude, longitude)`. Splitting
    the time axis rather than grouping twice keeps every (year, month) cell present,
    including months a source happens to be missing — those arrive as NaN, which is
    the validity signal D reads, instead of vanishing and shortening the axis.
    """
    split = data.assign_coords(
        year=data["time"].dt.year, month=data["time"].dt.month
    ).set_index(time=["year", "month"])
    return split.unstack("time").transpose("year", "month", "latitude", "longitude")


def drop_depth(data: xr.DataArray) -> xr.DataArray:
    """Remove the singleton depth axis a surface request still carries."""
    if "depth" in data.dims:
        data = data.isel(depth=0, drop=True)
    elif "depth" in data.coords:
        data = data.drop_vars("depth")
    return data
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `micromamba run -n shiny python -m pytest tests/test_refresh_cmems.py -v -m spatial`
Expected: 3 passed

- [ ] **Step 4b: Check the kwargs against the real signature**

The fake opener takes `**kwargs`, so it accepts a misspelled parameter name happily and
the first real call would die with `TypeError`. This costs nothing and needs no
credentials:

```bash
micromamba run -n shiny python -c "import inspect, copernicusmarine as cm; \
params = set(inspect.signature(cm.open_dataset).parameters); \
sent = {'dataset_id','variables','minimum_longitude','maximum_longitude', \
'minimum_latitude','maximum_latitude','start_datetime','end_datetime', \
'minimum_depth','maximum_depth'}; \
print('MISSING:', sorted(sent - params) or 'none')"
```

Expected: `MISSING: none`. If any name is missing, correct `open_window` to match the
installed `copernicusmarine` before continuing — do not adjust the test to agree with
the wrong name.

- [ ] **Step 5: Lint and commit**

```bash
micromamba run -n shiny ruff check src/seagarden_dst/refresh/sources/cmems.py tests/test_refresh_cmems.py
git add src/seagarden_dst/refresh/sources/cmems.py tests/test_refresh_cmems.py
git commit -m "feat(refresh): add the Copernicus client seam, lazy and injectable (R2, R3)

open_dataset not subset, so the wave reduction never lands raw hours on disk.
copernicusmarine imported inside the call so registry.py stays importable by the
probe job, which installs no spatial extra.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: `copernicus_phy`

**Files:**
- Create: `src/seagarden_dst/refresh/sources/phy.py`
- Test: `tests/test_refresh_sources.py`

**Interfaces:**
- Consumes: `cmems.open_window`, `cmems.to_yearly`, `cmems.drop_depth`, `reachability.url_reachable`.
- Produces: `CopernicusPhy(opener: DatasetOpener | None = None, reachability_opener: Callable | None = None)` with `.name == "copernicus_phy"`. Establishes the shape Tasks 4–6 repeat: `_years: YearRange | None` stashed in `build()`, `baseline_years()` raising if called first.

- [ ] **Step 1: Write the failing test**

Create `tests/test_refresh_sources.py`:

```python
"""The four Copernicus layers' transforms, claims and window rules (C§3.2, C§4.4)."""

from __future__ import annotations

import numpy as np
import pytest

from seagarden_dst.artifact.grid import GridSpec
from seagarden_dst.refresh.layer import YearRange

pytestmark = pytest.mark.spatial


def tiny_grid() -> GridSpec:
    return GridSpec(
        crs="EPSG:4326",
        lat_min=54.0, lat_max=54.05, lon_min=10.0, lon_max=10.09,
        lat_step=0.016666, lon_step=0.027777,
        n_lat=3, n_lon=3,
    )


def monthly_source(variables: dict[str, float], years: list[int]):
    """A monthly-frequency Dataset shaped like a CMEMS surface request."""
    import pandas as pd
    import xarray as xr

    times = pd.date_range(f"{years[0]}-01-01", f"{years[-1]}-12-01", freq="MS")
    grid = tiny_grid()
    return xr.Dataset(
        {
            name: (
                ("time", "latitude", "longitude"),
                np.full((len(times), 3, 3), value, dtype="float32"),
            )
            for name, value in variables.items()
        },
        coords={"time": times, "latitude": grid.lats(), "longitude": grid.lons()},
    )


def test_phy_emits_salinity_and_temperature_at_the_yearly_shape(tmp_path):
    from seagarden_dst.refresh.sources.phy import CopernicusPhy

    layer = CopernicusPhy(opener=lambda **kw: monthly_source({"so": 7.0, "thetao": 12.0}, [2024, 2025]))
    built = layer.build(tiny_grid(), YearRange(start=2024, end=2025), tmp_path)

    assert set(built.data_vars) == {"salinity_psu", "temp_c"}
    for name in built.data_vars:
        assert tuple(built[name].dims) == ("year", "month", "latitude", "longitude")
    assert float(built["salinity_psu"].isel(year=0, month=0, latitude=0, longitude=0)) == 7.0


def test_phy_claims_exactly_what_it_produces():
    from seagarden_dst.refresh.sources.phy import CopernicusPhy

    assert CopernicusPhy().provenance().variables == ["salinity_psu", "temp_c"]


def test_phy_baseline_window_is_the_requested_range(tmp_path):
    from seagarden_dst.refresh.sources.phy import CopernicusPhy

    layer = CopernicusPhy(opener=lambda **kw: monthly_source({"so": 7.0, "thetao": 12.0}, [2024, 2025]))
    layer.build(tiny_grid(), YearRange(start=2024, end=2025), tmp_path)

    assert layer.baseline_years() == {"salinity_psu": [2024, 2025], "temp_c": [2024, 2025]}


def test_phy_refuses_to_state_a_window_it_has_not_built():
    """R1: the ordering the driver happens to use is enforced, not assumed."""
    from seagarden_dst.refresh.sources.phy import CopernicusPhy

    with pytest.raises(RuntimeError, match="before build"):
        CopernicusPhy().baseline_years()


def test_phy_provenance_is_pending_with_a_source_url_and_an_unblocked_by():
    from seagarden_dst.refresh.sources.phy import CopernicusPhy

    archive = CopernicusPhy().provenance().archive
    assert archive.status == "pending"
    assert archive.source_url
    assert archive.unblocked_by

```

- [ ] **Step 2: Run test to verify it fails**

Run: `micromamba run -n shiny python -m pytest tests/test_refresh_sources.py -v -m spatial`
Expected: FAIL — `ModuleNotFoundError: No module named 'seagarden_dst.refresh.sources.phy'`

- [ ] **Step 3: Write minimal implementation**

Create `src/seagarden_dst/refresh/sources/phy.py`:

```python
"""`copernicus_phy` — salinity and temperature from the monthly PHY reanalysis (C§3.2).

The simplest of the four: two source variables, two artifact variables, a rename and
a reshape. Both are linear in their source, so the monthly product is correct for
them — see C§3.4 for the one variable where that is false.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from seagarden_dst.artifact.manifest import Archive, LayerProvenance
from seagarden_dst.refresh.layer import ProbeResult, YearRange
from seagarden_dst.refresh.sources import cmems
from seagarden_dst.refresh.sources.reachability import url_reachable

if TYPE_CHECKING:  # pragma: no cover - typing only
    import xarray as xr

    from seagarden_dst.artifact.grid import GridSpec

DATASET_ID = "cmems_mod_bal_phy_my_P1M-m"
PRODUCT_ID = "BALTICSEA_MULTIYEAR_PHY_003_011"
SOURCE_URL = "https://data.marine.copernicus.eu/product/BALTICSEA_MULTIYEAR_PHY_003_011"

# source variable -> artifact variable. No unit conversion: `so` is numerically psu
# and `thetao` is degrees Celsius (package B's provenance table).
_RENAMES = {"so": "salinity_psu", "thetao": "temp_c"}


class CopernicusPhy:
    """One layer, one dataset (C§5)."""

    name = "copernicus_phy"

    def __init__(
        self,
        opener: cmems.DatasetOpener | None = None,
        reachability_opener: Callable[..., object] | None = None,
    ) -> None:
        self._opener = opener
        self._reachability_opener = reachability_opener
        # R1: set by `build`, read by `baseline_years`. None until then, and
        # `baseline_years` refuses rather than guessing.
        self._years: YearRange | None = None

    def probe(self) -> ProbeResult:
        reachable, detail = url_reachable(SOURCE_URL, opener=self._reachability_opener)
        return ProbeResult(name=self.name, reachable=reachable, detail=detail)

    def build(self, grid: GridSpec, years: YearRange, workdir: Path) -> xr.Dataset:
        import xarray as xr

        self._years = years
        source = cmems.open_window(
            DATASET_ID, list(_RENAMES), grid, years, opener=self._opener
        )
        return xr.Dataset(
            {
                artifact_name: cmems.to_yearly(cmems.drop_depth(source[source_name]))
                for source_name, artifact_name in _RENAMES.items()
            }
        )

    def provenance(self) -> LayerProvenance:
        return LayerProvenance(
            name=self.name,
            source="Copernicus Marine Service",
            product_id=PRODUCT_ID,
            dataset_id=DATASET_ID,
            version="202303",
            retrieved_on=datetime.now(UTC),
            licence="Copernicus Marine Service licence",
            redistribution="allowed",
            source_url=SOURCE_URL,
            archive=Archive(
                status="pending",
                source_url=SOURCE_URL,
                unblocked_by="Zenodo deposit of the built artifact; C§1 puts it outside package C",
            ),
            variables=["salinity_psu", "temp_c"],
        )

    def baseline_years(self) -> dict[str, list[int]]:
        if self._years is None:
            raise RuntimeError(
                f"{self.name}.baseline_years() called before build(): this layer's "
                "window IS the requested year range, which it only learns from "
                "build(). Returning a guess here would put a window in the manifest "
                "that no data backs (R1)"
            )
        window = self._years.years()
        return {"salinity_psu": list(window), "temp_c": list(window)}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `micromamba run -n shiny python -m pytest tests/test_refresh_sources.py -v -m spatial`
Expected: 5 passed

- [ ] **Step 5: Lint and commit**

```bash
micromamba run -n shiny ruff check src/seagarden_dst/refresh/sources/phy.py tests/test_refresh_sources.py
git add src/seagarden_dst/refresh/sources/phy.py tests/test_refresh_sources.py
git commit -m "feat(refresh): add the copernicus_phy layer (C§3.2)

salinity_psu and temp_c from the monthly PHY reanalysis. Establishes the shape the
other three follow: window stashed in build(), baseline_years() refusing if called
first (R1).

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: `copernicus_bgc` — two emissions, one claim

**Files:**
- Create: `src/seagarden_dst/refresh/sources/bgc.py`
- Modify: `tests/test_refresh_sources.py` (append)

**Interfaces:**
- Consumes: same as Task 3.
- Produces: `CopernicusBgc(...)` with `.name == "copernicus_bgc"`. **Emits two variables, claims one** — `din_umol_l` is claimed by a `Derivation`, not by this layer.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_refresh_sources.py`:

```python
def test_bgc_sums_nitrate_and_ammonium_into_din(tmp_path):
    from seagarden_dst.refresh.sources.bgc import CopernicusBgc

    layer = CopernicusBgc(
        opener=lambda **kw: monthly_source({"no3": 4.0, "nh4": 1.5, "po4": 0.8}, [2024])
    )
    built = layer.build(tiny_grid(), YearRange(start=2024, end=2024), tmp_path)

    assert set(built.data_vars) == {"din_umol_l", "dip_umol_l"}
    assert float(built["din_umol_l"].isel(year=0, month=0, latitude=0, longitude=0)) == 5.5
    # approx, not ==: float32 0.8 reads back as 0.800000011920929. 5.5 and 7.0 are
    # exactly representable; 0.8 is not.
    assert float(
        built["dip_umol_l"].isel(year=0, month=0, latitude=0, longitude=0)
    ) == pytest.approx(0.8)


def test_bgc_claims_dip_only_because_din_is_claimed_by_a_derivation():
    """C§4.4: a computed field cannot also be claimed by a layer, or it is claimed twice."""
    from seagarden_dst.refresh.sources.bgc import CopernicusBgc

    assert CopernicusBgc().provenance().variables == ["dip_umol_l"]


def test_bgc_declares_a_window_for_both_variables_it_produces(tmp_path):
    """The driver resolves baselines over merged data_vars, not over claims."""
    from seagarden_dst.refresh.sources.bgc import CopernicusBgc

    layer = CopernicusBgc(
        opener=lambda **kw: monthly_source({"no3": 4.0, "nh4": 1.5, "po4": 0.8}, [2024])
    )
    layer.build(tiny_grid(), YearRange(start=2024, end=2024), tmp_path)

    assert layer.baseline_years() == {"din_umol_l": [2024], "dip_umol_l": [2024]}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `micromamba run -n shiny python -m pytest tests/test_refresh_sources.py -v -m spatial -k bgc`
Expected: FAIL — `ModuleNotFoundError: No module named 'seagarden_dst.refresh.sources.bgc'`

- [ ] **Step 3: Write minimal implementation**

Create `src/seagarden_dst/refresh/sources/bgc.py`:

```python
"""`copernicus_bgc` — nutrients from the monthly BGC reanalysis (C§3.2).

**This layer emits two variables and claims one.** `din_umol_l = no3 + nh4` is
assembled from more than one source variable, so C§4.1 makes it a `Derivation` —
and C§4.4 then forbids it from appearing in any layer's `variables`, because a
variable claimed by both a layer and a derivation is claimed twice. `dip_umol_l` is
a straight passthrough of `po4` and is claimed here in the ordinary way.

Do not "fix" the asymmetry by adding `din_umol_l` to `variables`: the manifest's
every-variable-claimed-exactly-once validator will reject the result.

No unit conversion: `no3`, `nh4` and `po4` are mmol m-3, which is micromol/L.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from seagarden_dst.artifact.manifest import Archive, LayerProvenance
from seagarden_dst.refresh.layer import ProbeResult, YearRange
from seagarden_dst.refresh.sources import cmems
from seagarden_dst.refresh.sources.reachability import url_reachable

if TYPE_CHECKING:  # pragma: no cover - typing only
    import xarray as xr

    from seagarden_dst.artifact.grid import GridSpec

DATASET_ID = "cmems_mod_bal_bgc_my_P1M-m"
PRODUCT_ID = "BALTICSEA_MULTIYEAR_BGC_003_012"
SOURCE_URL = "https://data.marine.copernicus.eu/product/BALTICSEA_MULTIYEAR_BGC_003_012"

_SOURCE_VARIABLES = ["no3", "nh4", "po4"]

# What this layer BUILDS. What it CLAIMS is `_CLAIMED` — they differ on purpose.
_PRODUCED = ["din_umol_l", "dip_umol_l"]
_CLAIMED = ["dip_umol_l"]


class CopernicusBgc:
    """One layer, one dataset (C§5)."""

    name = "copernicus_bgc"

    def __init__(
        self,
        opener: cmems.DatasetOpener | None = None,
        reachability_opener: Callable[..., object] | None = None,
    ) -> None:
        self._opener = opener
        self._reachability_opener = reachability_opener
        self._years: YearRange | None = None

    def probe(self) -> ProbeResult:
        reachable, detail = url_reachable(SOURCE_URL, opener=self._reachability_opener)
        return ProbeResult(name=self.name, reachable=reachable, detail=detail)

    def build(self, grid: GridSpec, years: YearRange, workdir: Path) -> xr.Dataset:
        import xarray as xr

        self._years = years
        source = cmems.open_window(
            DATASET_ID, _SOURCE_VARIABLES, grid, years, opener=self._opener
        )
        no3 = cmems.drop_depth(source["no3"])
        nh4 = cmems.drop_depth(source["nh4"])
        po4 = cmems.drop_depth(source["po4"])
        return xr.Dataset(
            {
                "din_umol_l": cmems.to_yearly(no3 + nh4),
                "dip_umol_l": cmems.to_yearly(po4),
            }
        )

    def provenance(self) -> LayerProvenance:
        return LayerProvenance(
            name=self.name,
            source="Copernicus Marine Service",
            product_id=PRODUCT_ID,
            dataset_id=DATASET_ID,
            version="202303",
            retrieved_on=datetime.now(UTC),
            licence="Copernicus Marine Service licence",
            redistribution="allowed",
            source_url=SOURCE_URL,
            archive=Archive(
                status="pending",
                source_url=SOURCE_URL,
                unblocked_by="Zenodo deposit of the built artifact; C§1 puts it outside package C",
            ),
            variables=list(_CLAIMED),
        )

    def baseline_years(self) -> dict[str, list[int]]:
        if self._years is None:
            raise RuntimeError(
                f"{self.name}.baseline_years() called before build(): this layer's "
                "window IS the requested year range, which it only learns from "
                "build() (R1)"
            )
        window = self._years.years()
        # Keyed on what is PRODUCED, not on what is claimed: the driver resolves
        # baselines against the merged dataset's data_vars, and `din_umol_l` is one
        # of them even though a Derivation claims it.
        return {name: list(window) for name in _PRODUCED}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `micromamba run -n shiny python -m pytest tests/test_refresh_sources.py -v -m spatial`
Expected: 8 passed

- [ ] **Step 5: Lint and commit**

```bash
micromamba run -n shiny ruff check src/seagarden_dst/refresh/sources/bgc.py tests/test_refresh_sources.py
git add src/seagarden_dst/refresh/sources/bgc.py tests/test_refresh_sources.py
git commit -m "feat(refresh): add the copernicus_bgc layer, emitting two and claiming one (C§4.4)

din_umol_l = no3 + nh4 is multi-source, so a Derivation claims it and this layer
must not. baseline_years keys on what is produced, since the driver resolves
baselines over merged data_vars.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: `copernicus_bgc_light` — the Jensen layer

**Files:**
- Create: `src/seagarden_dst/refresh/sources/bgc_light.py`
- Modify: `tests/test_refresh_sources.py` (append)

**Interfaces:**
- Consumes: same as Task 3, plus a **daily**-frequency source builder in the test.
- Produces: `CopernicusBgcLight(...)` with `.name == "copernicus_bgc_light"`, `provenance().variables == []`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_refresh_sources.py`:

```python
def daily_zsd_source(values_by_day: list[float], year: int = 2024):
    """A daily-frequency zsd Dataset. `values_by_day` repeats to fill the year."""
    import pandas as pd
    import xarray as xr

    times = pd.date_range(f"{year}-01-01", f"{year}-12-31", freq="D")
    grid = tiny_grid()
    column = np.resize(np.asarray(values_by_day, dtype="float32"), len(times))
    data = np.repeat(np.repeat(column[:, None, None], 3, axis=1), 3, axis=2)
    return xr.Dataset(
        {"zsd": (("time", "latitude", "longitude"), data)},
        coords={"time": times, "latitude": grid.lats(), "longitude": grid.lons()},
    )


def test_light_averages_k_over_days_rather_than_inverting_the_monthly_mean(tmp_path):
    """C§3.4 and Jensen: mean(1.7/z) != 1.7/mean(z), and the difference is the bug.

    This test FAILS if the derivation is moved to the monthly product or reordered
    to 1.7/mean(z). With z alternating 2 and 8, the two routes differ by ~28%.
    """
    from seagarden_dst.refresh.sources.bgc_light import CopernicusBgcLight

    layer = CopernicusBgcLight(opener=lambda **kw: daily_zsd_source([2.0, 8.0]))
    built = layer.build(tiny_grid(), YearRange(start=2024, end=2024), tmp_path)

    computed = float(built["light_attenuation_k"].isel(year=0, month=0, latitude=0, longitude=0))

    # Derive both expectations from the ACTUAL January the source builder produced.
    # January has 31 days, so [2.0, 8.0] repeating gives 16 twos and 15 eights - NOT
    # a balanced pair. Hard-coding mean([1.7/2, 1.7/8]) = 0.53125 would be wrong by
    # 1.9% against a CORRECT implementation, and the obvious way to make that green
    # is to reorder the division - which is the bug this test exists to catch.
    january = np.resize(np.asarray([2.0, 8.0], dtype="float32"), 366)[:31]
    correct = float(np.mean(1.7 / january))     # 0.5415
    wrong = 1.7 / float(np.mean(january))       # 0.3467

    assert computed == pytest.approx(correct, rel=1e-4)
    assert computed != pytest.approx(wrong, rel=1e-2)


def test_light_emits_only_k_at_the_yearly_shape(tmp_path):
    from seagarden_dst.refresh.sources.bgc_light import CopernicusBgcLight

    layer = CopernicusBgcLight(opener=lambda **kw: daily_zsd_source([3.0]))
    built = layer.build(tiny_grid(), YearRange(start=2024, end=2024), tmp_path)

    assert set(built.data_vars) == {"light_attenuation_k"}
    assert tuple(built["light_attenuation_k"].dims) == ("year", "month", "latitude", "longitude")


def test_light_claims_nothing_at_all():
    """C§5: its only output is derived, so its `variables` is empty BY DESIGN."""
    from seagarden_dst.refresh.sources.bgc_light import CopernicusBgcLight

    assert CopernicusBgcLight().provenance().variables == []


def test_light_reads_the_daily_dataset_not_the_monthly_one():
    from seagarden_dst.refresh.sources.bgc_light import CopernicusBgcLight

    assert CopernicusBgcLight().provenance().dataset_id.endswith("P1D-m")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `micromamba run -n shiny python -m pytest tests/test_refresh_sources.py -v -m spatial -k light`
Expected: FAIL — `ModuleNotFoundError: No module named 'seagarden_dst.refresh.sources.bgc_light'`

- [ ] **Step 3: Write minimal implementation**

Create `src/seagarden_dst/refresh/sources/bgc_light.py`:

```python
"""`copernicus_bgc_light` — light attenuation from DAILY Secchi depth (C§3.4).

**The order of operations is the whole point of this module.** k = 1.7/z_SD is
non-linear, and averaging does not commute through it. By Jensen's inequality, with
1/x convex for x > 0, computing 1.7/mean(z) gives a systematically LOWER k than
mean(1.7/z) — less attenuation, more light at cultivation depth, an optimistic
growth bias carrying no marker that anything went wrong.

So: open the DAILY product, compute k per day, then average k over the month. Never
the monthly product, and never the division after the mean.

It is its own layer rather than part of `copernicus_bgc` because it reads its own
dataset, and one layer describes one dataset (C§5). Its `variables` is EMPTY: the
only thing it produces is claimed by a `Derivation` (C§4.4). Populating it would
claim `light_attenuation_k` twice and fail the manifest.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from seagarden_dst.artifact.manifest import Archive, LayerProvenance
from seagarden_dst.refresh.layer import ProbeResult, YearRange
from seagarden_dst.refresh.sources import cmems
from seagarden_dst.refresh.sources.reachability import url_reachable

if TYPE_CHECKING:  # pragma: no cover - typing only
    import xarray as xr

    from seagarden_dst.artifact.grid import GridSpec

DATASET_ID = "cmems_mod_bal_bgc_my_P1D-m"
PRODUCT_ID = "BALTICSEA_MULTIYEAR_BGC_003_012"
SOURCE_URL = "https://data.marine.copernicus.eu/product/BALTICSEA_MULTIYEAR_BGC_003_012"

# Poole-Atkins. Named here once so the manifest's `relation` and the code agree.
POOLE_ATKINS_COEFFICIENT = 1.7


class CopernicusBgcLight:
    """One layer, one dataset (C§5). Claims nothing; a Derivation claims its output."""

    name = "copernicus_bgc_light"

    def __init__(
        self,
        opener: cmems.DatasetOpener | None = None,
        reachability_opener: Callable[..., object] | None = None,
    ) -> None:
        self._opener = opener
        self._reachability_opener = reachability_opener
        self._years: YearRange | None = None

    def probe(self) -> ProbeResult:
        reachable, detail = url_reachable(SOURCE_URL, opener=self._reachability_opener)
        return ProbeResult(name=self.name, reachable=reachable, detail=detail)

    def build(self, grid: GridSpec, years: YearRange, workdir: Path) -> xr.Dataset:
        import xarray as xr

        self._years = years
        source = cmems.open_window(DATASET_ID, ["zsd"], grid, years, opener=self._opener)
        zsd = cmems.drop_depth(source["zsd"])

        # Daily k first. This line and the next must not be swapped (C§3.4).
        daily_k = POOLE_ATKINS_COEFFICIENT / zsd
        monthly_k = daily_k.resample(time="MS").mean()

        return xr.Dataset({"light_attenuation_k": cmems.to_yearly(monthly_k)})

    def provenance(self) -> LayerProvenance:
        return LayerProvenance(
            name=self.name,
            source="Copernicus Marine Service",
            product_id=PRODUCT_ID,
            dataset_id=DATASET_ID,
            version="202303",
            retrieved_on=datetime.now(UTC),
            licence="Copernicus Marine Service licence",
            redistribution="allowed",
            source_url=SOURCE_URL,
            archive=Archive(
                status="pending",
                source_url=SOURCE_URL,
                unblocked_by="Zenodo deposit of the built artifact; C§1 puts it outside package C",
            ),
            # EMPTY BY DESIGN (C§4.4). See the module docstring before changing this.
            variables=[],
        )

    def baseline_years(self) -> dict[str, list[int]]:
        if self._years is None:
            raise RuntimeError(
                f"{self.name}.baseline_years() called before build(): this layer's "
                "window IS the requested year range, which it only learns from "
                "build() (R1)"
            )
        return {"light_attenuation_k": list(self._years.years())}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `micromamba run -n shiny python -m pytest tests/test_refresh_sources.py -v -m spatial`
Expected: 12 passed

- [ ] **Step 5: Lint and commit**

```bash
micromamba run -n shiny ruff check src/seagarden_dst/refresh/sources/bgc_light.py tests/test_refresh_sources.py
git add src/seagarden_dst/refresh/sources/bgc_light.py tests/test_refresh_sources.py
git commit -m "feat(refresh): add copernicus_bgc_light, daily k then monthly mean (C§3.4)

k = 1.7/z_SD is non-linear, so the daily product and this order are required:
1.7/mean(z) is systematically lower than mean(1.7/z), which biases growth
optimistically and silently. The test fails if either is changed.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: `copernicus_wav` — the fixed-window p95

**Files:**
- Create: `src/seagarden_dst/refresh/sources/wav.py`
- Modify: `tests/test_refresh_sources.py` (append)

**Interfaces:**
- Consumes: `cmems.open_window(..., surface=False)` — the wave product has no depth axis.
- Produces: `CopernicusWav(...)` with `.name == "copernicus_wav"`. Emits `significant_wave_m` at the **monthly** shape, and declares a window **fixed** at `[2023, 2024, 2025]`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_refresh_sources.py`:

```python
WAVE_BASELINE = [2023, 2024, 2025]


def hourly_wave_source(values: list[float], year: int = 2024):
    """An hourly VHM0 Dataset over January only, to keep the test small."""
    import pandas as pd
    import xarray as xr

    times = pd.date_range(f"{year}-01-01", f"{year}-01-31 23:00", freq="h")
    grid = tiny_grid()
    column = np.resize(np.asarray(values, dtype="float32"), len(times))
    data = np.repeat(np.repeat(column[:, None, None], 3, axis=1), 3, axis=2)
    return xr.Dataset(
        {"VHM0": (("time", "latitude", "longitude"), data)},
        coords={"time": times, "latitude": grid.lats(), "longitude": grid.lons()},
    )


def test_wav_reduces_hourly_waves_to_a_monthly_p95(tmp_path):
    from seagarden_dst.refresh.sources.wav import CopernicusWav

    hours = list(np.linspace(0.0, 10.0, 100))
    layer = CopernicusWav(opener=lambda **kw: hourly_wave_source(hours))
    built = layer.build(tiny_grid(), YearRange(start=2024, end=2024), tmp_path)

    assert set(built.data_vars) == {"significant_wave_m"}
    assert tuple(built["significant_wave_m"].dims) == ("month", "latitude", "longitude")
    january = float(built["significant_wave_m"].isel(month=0, latitude=0, longitude=0))
    assert january == pytest.approx(np.quantile(np.resize(hours, 31 * 24), 0.95), rel=1e-3)


def test_wav_carries_no_quantile_coordinate_into_the_artifact(tmp_path):
    """groupby().quantile() leaves a scalar `quantile` coord that must not ship."""
    from seagarden_dst.refresh.sources.wav import CopernicusWav

    layer = CopernicusWav(opener=lambda **kw: hourly_wave_source([1.0, 2.0]))
    built = layer.build(tiny_grid(), YearRange(start=2024, end=2024), tmp_path)

    assert "quantile" not in built.coords
    assert "quantile" not in built["significant_wave_m"].coords


def test_wav_window_is_fixed_and_ignores_the_requested_range(tmp_path):
    """C§3.2 fixes the p95 window at 2023-2025; R2 is the case this was written for."""
    from seagarden_dst.refresh.sources.wav import CopernicusWav

    layer = CopernicusWav(opener=lambda **kw: hourly_wave_source([1.0, 2.0]))
    layer.build(tiny_grid(), YearRange(start=2016, end=2025), tmp_path)

    assert layer.baseline_years() == {"significant_wave_m": WAVE_BASELINE}


def test_wav_asks_for_its_own_window_not_the_requested_one(tmp_path):
    from seagarden_dst.refresh.sources.wav import CopernicusWav

    seen: dict[str, object] = {}

    def fake_opener(**kwargs: object):
        seen.update(kwargs)
        return hourly_wave_source([1.0, 2.0])

    CopernicusWav(opener=fake_opener).build(
        tiny_grid(), YearRange(start=2016, end=2025), tmp_path
    )

    assert seen["start_datetime"].startswith("2023-01-01")
    assert seen["end_datetime"].startswith("2025-12-31")
    assert "minimum_depth" not in seen  # the wave product is 2-D


def test_wav_claims_the_variable_it_produces():
    from seagarden_dst.refresh.sources.wav import CopernicusWav

    assert CopernicusWav().provenance().variables == ["significant_wave_m"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `micromamba run -n shiny python -m pytest tests/test_refresh_sources.py -v -m spatial -k wav`
Expected: FAIL — `ModuleNotFoundError: No module named 'seagarden_dst.refresh.sources.wav'`

- [ ] **Step 3: Write minimal implementation**

Create `src/seagarden_dst/refresh/sources/wav.py`:

```python
"""`copernicus_wav` — the monthly p95 of hourly significant wave height (C§3.2).

Three things make this layer the odd one out.

**It ignores the year range it is handed.** C§3.2 fixes the p95 window at 2023-2025,
so `build` requests those years whatever it is asked for, and `baseline_years`
declares them. `significant_wave_m` has no `year` dim, so the driver cannot read the
window off the data and accepts the declaration as stated — the case R2 exists for.

**Its shape is monthly, not yearly**: `(month, latitude, longitude)`. The p95 is
collapsed over the whole window, so there is no year axis left.

**It is the expensive one.** ~25.8 GB of hourly `VHM0` crosses the wire, against
~0.59 GB for every monthly variable combined. The reduction runs against the lazy
Dataset `open_window` returns (R2) so those hours are never written to disk; a
`subset`-to-file route would need 25.8 GB of free space that this project's machines
do not have.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from seagarden_dst.artifact.manifest import Archive, LayerProvenance
from seagarden_dst.refresh.layer import ProbeResult, YearRange
from seagarden_dst.refresh.sources import cmems
from seagarden_dst.refresh.sources.reachability import url_reachable

if TYPE_CHECKING:  # pragma: no cover - typing only
    import xarray as xr

    from seagarden_dst.artifact.grid import GridSpec

DATASET_ID = "cmems_mod_bal_wav_my_PT1H-i"
PRODUCT_ID = "BALTICSEA_MULTIYEAR_WAV_003_015"
SOURCE_URL = "https://data.marine.copernicus.eu/product/BALTICSEA_MULTIYEAR_WAV_003_015"

# Fixed by C§3.2, not by the caller. See the module docstring.
WAVE_BASELINE_YEARS: list[int] = [2023, 2024, 2025]
P95 = 0.95


class CopernicusWav:
    """One layer, one dataset (C§5). The only layer with a window of its own."""

    name = "copernicus_wav"

    def __init__(
        self,
        opener: cmems.DatasetOpener | None = None,
        reachability_opener: Callable[..., object] | None = None,
    ) -> None:
        self._opener = opener
        self._reachability_opener = reachability_opener

    def probe(self) -> ProbeResult:
        reachable, detail = url_reachable(SOURCE_URL, opener=self._reachability_opener)
        return ProbeResult(name=self.name, reachable=reachable, detail=detail)

    def build(self, grid: GridSpec, years: YearRange, workdir: Path) -> xr.Dataset:
        import xarray as xr

        # `years` is deliberately unused: the window is this layer's own (C§3.2).
        del years
        own_window = YearRange(start=WAVE_BASELINE_YEARS[0], end=WAVE_BASELINE_YEARS[-1])
        source = cmems.open_window(
            DATASET_ID, ["VHM0"], grid, own_window, opener=self._opener, surface=False
        )
        hourly = source["VHM0"]

        # quantile needs the reduced axis in one chunk; on a lazy dask-backed array
        # that is a rechunk, not a load, so the hours still never land on disk.
        if hourly.chunks is not None:
            hourly = hourly.chunk({"time": -1})

        p95 = hourly.groupby("time.month").quantile(P95, dim="time")
        # groupby().quantile() attaches a scalar `quantile` coord. check_shapes looks
        # at dims, so it would pass — and the coord would ship in the artifact as an
        # unexplained 0.95 that no manifest field accounts for.
        p95 = p95.drop_vars("quantile", errors="ignore")

        return xr.Dataset(
            {"significant_wave_m": p95.transpose("month", "latitude", "longitude")}
        )

    def provenance(self) -> LayerProvenance:
        return LayerProvenance(
            name=self.name,
            source="Copernicus Marine Service",
            product_id=PRODUCT_ID,
            dataset_id=DATASET_ID,
            version="202303",
            retrieved_on=datetime.now(UTC),
            licence="Copernicus Marine Service licence",
            redistribution="allowed",
            source_url=SOURCE_URL,
            archive=Archive(
                status="pending",
                source_url=SOURCE_URL,
                unblocked_by="Zenodo deposit of the built artifact; C§1 puts it outside package C",
            ),
            variables=["significant_wave_m"],
        )

    def baseline_years(self) -> dict[str, list[int]]:
        # No build() guard here, and that is not an oversight: this window is a
        # constant of the design, not a function of the request, so this layer CAN
        # answer before building (the property C-b's handoff wanted of all of them).
        return {"significant_wave_m": list(WAVE_BASELINE_YEARS)}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `micromamba run -n shiny python -m pytest tests/test_refresh_sources.py -v -m spatial`
Expected: 17 passed

- [ ] **Step 5: Lint and commit**

```bash
micromamba run -n shiny ruff check src/seagarden_dst/refresh/sources/wav.py tests/test_refresh_sources.py
git add src/seagarden_dst/refresh/sources/wav.py tests/test_refresh_sources.py
git commit -m "feat(refresh): add copernicus_wav, a fixed-window monthly p95 (C§3.2)

Ignores the requested range because C§3.2 fixes the window at 2023-2025, reduces
lazily so 25.8 GB of hourly VHM0 never lands on disk, and drops the scalar quantile
coord groupby().quantile() leaves behind.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Fill the registry

**Files:**
- Modify: `src/seagarden_dst/refresh/registry.py`
- Test: `tests/test_refresh_registry.py`

**Interfaces:**
- Consumes: all four layer classes.
- Produces: a populated `REGISTRY: dict[str, Layer]`. `emodnet_bathy` stays unregistered until C-c2, so the assertion here is `set(REGISTRY) <= set(LAYER_NAMES)`; C-c2's first task tightens it to `==`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_refresh_registry.py`:

```python
"""What is registered, and that registering it did not poison the probe path."""

from __future__ import annotations

from seagarden_dst.refresh.layer import LAYER_NAMES, Layer
from seagarden_dst.refresh.registry import REGISTRY


def test_the_four_copernicus_layers_are_registered():
    assert set(REGISTRY) == {
        "copernicus_phy",
        "copernicus_bgc",
        "copernicus_bgc_light",
        "copernicus_wav",
    }


def test_every_registered_name_is_one_C5_names():
    """C-c2 tightens this to equality once emodnet_bathy lands."""
    assert set(REGISTRY) <= set(LAYER_NAMES)


def test_every_registered_key_matches_its_layers_own_name():
    for key, layer in REGISTRY.items():
        assert layer.name == key


def test_every_registered_layer_satisfies_the_protocol():
    for layer in REGISTRY.values():
        assert isinstance(layer, Layer)


def test_no_module_on_the_probe_path_imports_the_spatial_stack_at_module_scope():
    """R3: the probe job installs the bare package, so these imports must stay clean.

    Parsed with `ast` rather than imported or subprocessed, following
    `tests/test_refresh_isolation.py` - importing the module to see what it imports
    is the coupling under test, and a subprocess cannot resolve `seagarden_dst` in
    the development environment, where there is no editable install (see the
    comment at the top of `scripts/refresh_layers.py`). The AST walk asks the
    precise question R3 asks: is the import at MODULE scope, or inside a method?
    """
    import ast
    from pathlib import Path

    forbidden = {"xarray", "copernicusmarine"}
    refresh_dir = Path(__file__).resolve().parent.parent / "src" / "seagarden_dst" / "refresh"
    probe_path = [refresh_dir / "registry.py", *sorted((refresh_dir / "sources").glob("*.py"))]

    offenders: list[str] = []
    for module_path in probe_path:
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
        # Only the module body - an import inside a FunctionDef is what R3 allows.
        for node in tree.body:
            if isinstance(node, ast.Import):
                names = {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                names = {(node.module or "").split(".")[0]}
            else:
                continue
            for name in sorted(names & forbidden):
                offenders.append(f"{module_path.name}:{node.lineno} imports {name}")

    assert offenders == [], (
        "module-scope spatial imports on the probe path: " + "; ".join(offenders)
        + ". The probe job installs no spatial extra and would crash on import (R3)"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `micromamba run -n shiny python -m pytest tests/test_refresh_registry.py -v`
Expected: FAIL — `AssertionError: assert set() == {'copernicus_phy', ...}`

- [ ] **Step 3: Write minimal implementation**

Replace the body of `src/seagarden_dst/refresh/registry.py` below the docstring:

```python
"""The one place the source list lives (C§5).

Both the driver and the probe job read this, so a layer added here appears in the
refresh and in the monthly reachability check without being registered twice.

**Nothing here may import xarray or copernicusmarine at module scope.** The probe
workflow installs the bare package (`pip install -e .`, no `[spatial]` extra), so
this module and everything it imports must load without them. The layer modules
honour that by importing inside their methods; do not add a convenience import here
that breaks it.
"""

from __future__ import annotations

from seagarden_dst.refresh.layer import LAYER_NAMES, Layer
from seagarden_dst.refresh.sources.bgc import CopernicusBgc
from seagarden_dst.refresh.sources.bgc_light import CopernicusBgcLight
from seagarden_dst.refresh.sources.phy import CopernicusPhy
from seagarden_dst.refresh.sources.wav import CopernicusWav

# `emodnet_bathy` is package C-c2 and is deliberately absent. Until it lands, a
# refresh built from this registry produces seven of the nine variables and the
# manifest's every-variable-claimed-exactly-once validator will refuse it — which is
# correct: an artifact missing its depth fields should not be writable.
REGISTRY: dict[str, Layer] = {
    layer.name: layer
    for layer in (
        CopernicusPhy(),
        CopernicusBgc(),
        CopernicusBgcLight(),
        CopernicusWav(),
    )
}

# Every registered layer is one C§5 names. This is `<=` and not `==` only because
# `emodnet_bathy` is still to come; C-c2's first task tightens it to equality, at
# which point a registered layer C§5 does not name, or a named layer nobody
# registered, fails loudly at import.
# A `raise`, not an `assert`: module-scope asserts vanish under `python -O`, and a
# guard that disappears under an optimisation flag is a guard that cannot fail.
if not set(REGISTRY) <= set(LAYER_NAMES):
    raise RuntimeError(
        f"registered layers {sorted(set(REGISTRY) - set(LAYER_NAMES))} are not "
        "named in LAYER_NAMES (C§5)"
    )
```

- [ ] **Step 3b: Keep the CLI honest while the registry is incomplete**

Before Task 7, `refresh_layers.py <start> <end>` hit the empty-registry guard and
refused cleanly. After it, the guard passes, so a refresh would open four real
Copernicus datasets, pull data over the wire, and only then die deep inside
`compute_valid` or manifest validation, because `valid`'s derivation names
`emodnet_bathy` and no such layer is registered. That is a regression in a shipped
CLI: it trades a clean refusal for an expensive one.

In `scripts/refresh_layers.py`, add to the **refresh branch only** — `--probe` stays
permissive, because reporting on four reachable sources is still useful:

```python
    missing = sorted(set(LAYER_NAMES) - set(REGISTRY))
    if missing:
        parser.error(
            f"cannot refresh: {', '.join(missing)} "
            f"{'is' if len(missing) == 1 else 'are'} named in C\u00a75 but not "
            "registered, so the artifact would be missing variables the manifest "
            "must claim. Refusing before the download rather than after it."
        )
```

Import `LAYER_NAMES` alongside `REGISTRY` — it is already exported from
`refresh/layer.py`, which the CLI imports. Add a test to
`tests/test_refresh_cli.py` asserting the refresh branch exits non-zero and names
`emodnet_bathy`, and that `--probe` still reports its four rows. C-c2 deletes nothing
here: once `emodnet_bathy` registers, `missing` is empty and the check goes quiet.

- [ ] **Step 4: Run the whole suite**

Run: `micromamba run -n shiny python -m pytest tests/ -q`
Then: `micromamba run -n shiny python -m pytest tests/ -q -m spatial`
Expected: both green. The default run must pass **without** touching the spatial tests.

- [ ] **Step 5: Verify the probe path by hand**

Run: `micromamba run -n shiny python -m scripts.refresh_layers --probe`
Expected: four rows, one per layer, with real reachability. It no longer exits 1 on the empty-registry guard. If the network is unavailable, expect four `reachable=False` rows and a non-zero exit — that is the probe working, not failing.

- [ ] **Step 6: Lint and commit**

```bash
micromamba run -n shiny ruff check src/ tests/
git add src/seagarden_dst/refresh/registry.py tests/test_refresh_registry.py
git commit -m "feat(refresh): register the four Copernicus layers (C§5)

REGISTRY is no longer empty, so --probe reports reachability instead of refusing.
emodnet_bathy stays out until C-c2, so the LAYER_NAMES assertion is subset rather
than equality; C-c2's first task tightens it. An AST test pins that no module on the
probe path imports xarray or copernicusmarine at module scope, and the refresh branch
of the CLI refuses while the registry is incomplete.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage.** C§3.2's eight source-backed variables: `salinity_psu`/`temp_c` (Task 3), `din_umol_l`/`dip_umol_l` (Task 4), `light_attenuation_k` (Task 5), `significant_wave_m` (Task 6). `depth_mean_m`/`depth_min_m` and `valid` are C-c2 and the driver respectively. C§3.4's non-commuting derivation: Task 5, with a discriminating test. C§4.4's claim rules: Tasks 4 and 5 (`variables` lists that differ from what is produced). C§5's one-layer-one-dataset and the five protocol members: every layer task. C§8.2's probe: Tasks 1 and 7.

**Known gap, deliberate.** With `emodnet_bathy` unregistered, an end-to-end `run_refresh` cannot succeed — the manifest requires all nine variables claimed. C-c1 therefore ships no end-to-end refresh test; the driver's end-to-end behaviour is already proven against `FakeLayer` in C-b, and the real end-to-end run is C-c2's. This is recorded rather than papered over.

**Type consistency.** `cmems.DatasetOpener` is the annotation on every layer's `opener` parameter. `cmems.open_window(dataset_id, variables, grid, years, *, opener, surface)` is called identically in Tasks 3–6, with `surface=False` only in Task 6. `cmems.to_yearly` and `cmems.drop_depth` take and return `xr.DataArray`. `url_reachable` returns `tuple[bool, str]` and is unpacked the same way in all four `probe()` methods.

**Handoff to C-c2.** Tighten the registry assertion to `==`. Add `emodnet_bathy` with the `rioxarray` regrid. Add the free-disk precheck. Run the measured thin slice and write `docs/runbooks/annual-refresh.md` with observed rather than copied volumes.
