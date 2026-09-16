# Package C-b: Layer Protocol, Driver and Probe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the orchestration half of package C — the `Layer` protocol, the `REGISTRY`, the refresh driver that merges layers into the artifact pair, the `--probe` CLI and its scheduled workflow, and the deposit stub — all provable without a single network call.

**Architecture:** C-a delivered the *data* half: `GridSpec`, `Manifest`, `write_pair`, `check_declaration`. C-b delivers the *control* half that drives them. The five real layer implementations are **out of scope** (they are C-c); C-b defines the protocol they must satisfy and proves the driver against synthetic `FakeLayer` implementations living in `tests/`. This is what makes C-b independently testable: every clause it discharges is provable offline, and C-c becomes five isolated, individually-reviewable implementations of an interface that already has a green driver behind it.

**Tech Stack:** Python 3.11+, Pydantic v2, xarray + h5netcdf (the `spatial` extra), pytest, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-15-package-c-refresh-tooling-design.md`

## Global Constraints

- **Nothing in `refresh/` may be imported by the model core** (C§5). `tests/test_refresh_isolation.py` already asserts this — it must stay green.
- Every module that imports `xarray`, `rioxarray` or `rasterio` at runtime is `spatial`-extra territory; tests touching them carry `pytest.mark.spatial` **and** guard the import with `pytest.importorskip`. A marker alone does not prevent a collection-time `ImportError` — `-m` deselects *after* collection.
- Pydantic models in this package use `model_config = ConfigDict(extra="forbid")`.
- `ARTIFACT_SCHEMA_VERSION = 1`; the nine artifact variables are `seagarden_dst.refresh.variables.ARTIFACT_VARIABLES`.
- **Test discrimination standard (in force for every task):**
  - Every negative test asserts `match=` on a fragment **unique to the rule under test**.
  - **DELETE proof:** for each guard added, neutralise it, show the test goes red *for the right reason*, restore, show green. Record the actual pytest output in the task report, never the word "verified".
  - **SWAP proof:** wherever two sibling error messages share a matched substring, swap the two message bodies — *both* tests must go red. Deletion alone cannot catch that class.
  - Commit the implementation **before** running mutation proofs, so a stall does not lose the task.
- Never `git add` anything under `.superpowers/`.
- No network call in any test. No credential read in any test.

## Rulings Made While Writing This Plan

These resolve gaps between C§5 (written before C-a shipped) and the code that actually exists. Each is binding on implementers.

**R1 — `Layer.build` takes the year range.** C§5 shows `build(self, grid, workdir)`, but done-when clause 1 requires a refresh "for a named year range", and layers carry *different* baselines (waves 2023–2025, `light_attenuation_k` 2016–2025). A signature with no years cannot satisfy clause 1. The protocol therefore reads `build(self, grid: GridSpec, years: YearRange, workdir: Path) -> xr.Dataset`. *Cost if wrong:* a signature change across five C-c implementations.

**R2 — `baselines` is derived from the merged dataset, not declared.** `Manifest.baselines` maps each variable to the years behind it. Rather than have layers assert their years (a claim that can drift from the data), the driver reads each variable's `year` coordinate off the merged dataset; variables with no `year` dimension get `[]`. This makes `baselines` a *fact about the artifact*, and it is what lets C§4.4's "`[]` and omission told apart" rule mean something. *Cost if wrong:* baselines would need a sixth protocol member.

**R3 — the driver does NOT call `check_declaration`.** `write_pair` already calls it (`src/seagarden_dst/refresh/writer.py:57`). The driver's job is to populate `Manifest.variables` from `ARTIFACT_VARIABLES` and let the writer enforce. A second call would be dead code that looks load-bearing. *Cost if wrong:* none; the check still runs.

**Ordering note, which matters when writing tests:** R2 derives `baselines` from the built dataset, so `set(baselines) == set(merged.data_vars)`. The manifest's `_check_baseline_keys_are_exactly_the_artifact_variables` then compares that against `variables`. A produced-vs-declared mismatch therefore raises a `ValidationError` at `Manifest(...)` construction, **before** `write_pair` is called — which makes `check_declaration` structurally unreachable-as-failing from `run_refresh`. That is defence in depth, not redundancy: package D calls the same function on the *read* side, where nothing else is checking. Do not write a driver test that expects `check_declaration`'s message; it will never see it.

**R4 — `COVERAGE_LAYERS` moves into `refresh/` and `tests/refresh_builders.py` imports it.** Today `_COVERAGE_LAYERS` is a tuple of four layer names defined only in the test builders (`tests/refresh_builders.py:25`). The driver must compute `valid` over exactly the same four, or the manifest attests a four-layer intersection over five-layer data. One definition, imported by both. `copernicus_bgc_light` is excluded because its only output is derived and it shares the BGC footprint, so it adds no independent coverage constraint. *Cost if wrong:* `valid` disagrees with its own provenance record.

**R5 — a layer covers a cell only if every variable it contributes is non-null there, at every time slice.** "Intersection of contributing layer coverage" (C§3.5) needs a reduction rule over the non-spatial dims. `.all()` is the conservative reading: a cell wet in some months and absent in others is not coverage a farm verdict should rest on. *Cost if wrong:* `valid` is too small, which fails safe — D shows fewer cells rather than manufacturing a verdict from a gap.

**R6 — fakes live in `tests/`, never in `refresh/`.** A fake layer in production code is a test seam nobody can see.

---

## File Structure

| File | Responsibility |
|---|---|
| `src/seagarden_dst/refresh/layer.py` (create) | `YearRange`, `ProbeResult`, the `Layer` Protocol, `LAYER_NAMES`, `COVERAGE_LAYERS`. No xarray at runtime. |
| `src/seagarden_dst/refresh/registry.py` (create) | `REGISTRY`. The source list, in one place. |
| `src/seagarden_dst/refresh/merge.py` (create) | `compute_valid`, `merge_layers`. The `valid` intersection. |
| `src/seagarden_dst/refresh/driver.py` (create) | `run_refresh` — build, merge, derive baselines, assemble manifest, write. |
| `src/seagarden_dst/refresh/deposit.py` (create) | `Depositor` protocol, `record_doi`. |
| `scripts/refresh_layers.py` (create) | Thin CLI: year range, `--probe`, `--target`. |
| `.github/workflows/source-probe.yml` (create) | Monthly + `workflow_dispatch`, separate from `ci.yml`. |
| `tests/refresh_fakes.py` (create) | `FakeLayer` and friends. Test-only (R6). |
| `tests/refresh_builders.py` (modify) | Import `COVERAGE_LAYERS` instead of redefining it (R4). |
| `tests/test_refresh_layer.py`, `test_refresh_merge.py`, `test_refresh_driver.py`, `test_refresh_cli.py`, `test_refresh_deposit.py` (create) | One test module per unit. |

---

### Task 1: The layer protocol, the registry, and the fakes

**Files:**
- Create: `src/seagarden_dst/refresh/layer.py`, `src/seagarden_dst/refresh/registry.py`, `tests/refresh_fakes.py`
- Modify: `tests/refresh_builders.py:25` (replace `_COVERAGE_LAYERS` with an import — R4)
- Test: `tests/test_refresh_layer.py`

**Interfaces:**
- Consumes: `seagarden_dst.artifact.grid.GridSpec`, `seagarden_dst.artifact.manifest.LayerProvenance`, `seagarden_dst.artifact.manifest.Archive`
- Produces:
  - `YearRange(start: int, end: int)` with `.years() -> list[int]`; rejects `end < start`
  - `ProbeResult(name: str, reachable: bool, detail: str)`
  - `Layer` — a `@runtime_checkable` Protocol: `name: str`, `probe() -> ProbeResult`, `build(grid: GridSpec, years: YearRange, workdir: Path) -> xr.Dataset`, `provenance() -> LayerProvenance`
  - `REGISTRY: dict[str, Layer]` (empty in C-b — C-c fills it), `LAYER_NAMES: tuple[str, ...]` (the five names), `COVERAGE_LAYERS: tuple[str, ...]` (the four)
  - `tests/refresh_fakes.py`: `FakeLayer(name, variables, *, claims=None, static=False, data=None, fail_on_build=False, reachable=True, dataset_id=None)` implementing `Layer`; `LayerBuildFailed`

**Why `claims` is separate from `variables`:** a layer's `LayerProvenance.variables` is what it *claims*, and the dataset it builds is what it *produces*. These differ on purpose. `tests/refresh_builders.py:24` has `copernicus_bgc` claiming only `["dip_umol_l"]` while `din_umol_l` is claimed by a `Derivation`; `copernicus_bgc_light` claims `[]` while producing `light_attenuation_k`. A fake that conflated the two would double-claim `din_umol_l` and fail C§4.4's claimed-exactly-once validator — which is the rule working, not a bug to route around.

- [ ] **Step 1: Write the failing tests for `YearRange` and `ProbeResult`**

```python
# tests/test_refresh_layer.py
import pytest

from seagarden_dst.refresh.layer import COVERAGE_LAYERS, LAYER_NAMES, ProbeResult, YearRange


def test_year_range_enumerates_inclusively():
    assert YearRange(start=2023, end=2025).years() == [2023, 2024, 2025]


def test_year_range_of_one_year_is_that_year():
    assert YearRange(start=2024, end=2024).years() == [2024]


def test_year_range_rejects_an_end_before_its_start():
    with pytest.raises(ValueError, match="end year 2020 precedes start year 2025"):
        YearRange(start=2025, end=2020)


def test_probe_result_carries_a_detail_even_when_reachable():
    result = ProbeResult(name="copernicus_phy", reachable=True, detail="catalogue responded")
    assert (result.name, result.reachable) == ("copernicus_phy", True)


def test_coverage_layers_are_a_strict_subset_of_the_five():
    assert set(COVERAGE_LAYERS) < set(LAYER_NAMES)
    assert "copernicus_bgc_light" not in COVERAGE_LAYERS
```

- [ ] **Step 2: Run to verify it fails**

Run: `micromamba run -n shiny python -m pytest tests/test_refresh_layer.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'seagarden_dst.refresh.layer'`

- [ ] **Step 3: Write `layer.py`**

```python
"""The contract every refresh layer satisfies (C§5).

Deliberately free of xarray at runtime: the probe job imports this module to read
`REGISTRY` and must not drag the spatial stack in to ask whether a catalogue answers.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, model_validator

from seagarden_dst.artifact.grid import GridSpec
from seagarden_dst.artifact.manifest import LayerProvenance

if TYPE_CHECKING:  # pragma: no cover - typing only
    import xarray as xr


class YearRange(BaseModel):
    """The span a refresh covers (C§10 clause 1), inclusive at both ends."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    start: int
    end: int

    @model_validator(mode="after")
    def _check_end_does_not_precede_start(self) -> YearRange:
        if self.end < self.start:
            raise ValueError(
                f"end year {self.end} precedes start year {self.start}: a refresh "
                "covers an inclusive span, so an inverted range would silently "
                "build nothing"
            )
        return self

    def years(self) -> list[int]:
        return list(range(self.start, self.end + 1))


class ProbeResult(BaseModel):
    """One layer's answer to 'do you still exist?' (C§8.2)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    reachable: bool
    detail: str


@runtime_checkable
class Layer(Protocol):
    """One layer, one dataset (C§5).

    `build` takes the year range because layers carry different baselines and a
    refresh is named by its span — see ruling R1 in this package's plan.
    """

    name: str

    def probe(self) -> ProbeResult: ...

    def build(self, grid: GridSpec, years: YearRange, workdir: Path) -> xr.Dataset: ...

    def provenance(self) -> LayerProvenance: ...


# The five layers C-c implements. One layer, one dataset (C§5).
LAYER_NAMES: tuple[str, ...] = (
    "copernicus_phy",
    "copernicus_bgc",
    "copernicus_bgc_light",
    "copernicus_wav",
    "emodnet_bathy",
)

# The layers whose coverage the `valid` intersection is taken over (C§3.5).
# `copernicus_bgc_light` is absent because its only output is derived and it shares
# the BGC footprint, so it adds no independent constraint — see ruling R4.
COVERAGE_LAYERS: tuple[str, ...] = (
    "copernicus_phy",
    "copernicus_bgc",
    "copernicus_wav",
    "emodnet_bathy",
)
```

- [ ] **Step 4: Write `registry.py`**

```python
"""The one place the source list lives (C§5).

Both the driver and the probe job read this, so a layer added in C-c appears in the
refresh and in the monthly reachability check without being registered twice.
"""

from __future__ import annotations

from seagarden_dst.refresh.layer import Layer

# Empty until package C-c implements the five layers. The driver and the CLI are
# written against the mapping, not against its contents, which is what lets both be
# proven against synthetic layers before a single Copernicus call exists.
REGISTRY: dict[str, Layer] = {}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `micromamba run -n shiny python -m pytest tests/test_refresh_layer.py -v`
Expected: 5 passed

- [ ] **Step 6: Write `tests/refresh_fakes.py`**

```python
"""Synthetic `Layer` implementations for driver tests (ruling R6).

These live in `tests/` and never in `refresh/`: a fake in production code is a test
seam nobody can see. They exist so every driver clause — merge, `valid`, baselines,
fail-on-any-layer — is provable with no network and no credential.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import xarray as xr

from seagarden_dst.artifact.grid import GridSpec
from seagarden_dst.artifact.manifest import Archive, LayerProvenance
from seagarden_dst.refresh.layer import ProbeResult, YearRange


class LayerBuildFailed(RuntimeError):
    """Raised by a `FakeLayer` told to fail, so the driver's C§6.1 row 1 has a case."""


class FakeLayer:
    """A `Layer` that returns data handed to it instead of fetching any."""

    def __init__(
        self,
        name: str,
        variables: list[str],
        *,
        claims: list[str] | None = None,
        static: bool = False,
        data: dict[str, xr.DataArray] | None = None,
        fail_on_build: bool = False,
        reachable: bool = True,
        dataset_id: str | None = None,
    ) -> None:
        self.name = name
        self._variables = variables
        # What the layer CLAIMS, which is not always what it produces: `copernicus_bgc`
        # produces din_umol_l but a Derivation claims it, and `copernicus_bgc_light`
        # claims nothing at all (C§5). Defaults to the produced set.
        self._claims = list(variables) if claims is None else list(claims)
        self._static = static
        self._data = data
        self._fail_on_build = fail_on_build
        self._reachable = reachable
        self._dataset_id = dataset_id or f"{name}-dataset"

    def probe(self) -> ProbeResult:
        return ProbeResult(
            name=self.name,
            reachable=self._reachable,
            detail="catalogue responded" if self._reachable else "catalogue 404",
        )

    def build(self, grid: GridSpec, years: YearRange, workdir: Path) -> xr.Dataset:
        if self._fail_on_build:
            raise LayerBuildFailed(f"layer {self.name} could not build")
        if self._data is not None:
            return xr.Dataset(self._data)
        if self._static:
            # Bathymetry has no year dimension, so its baseline is `[]` — the case
            # C§4.4 tells apart from an omitted key.
            return xr.Dataset(
                {
                    name: (("lat", "lon"), np.ones((grid.n_lat, grid.n_lon)))
                    for name in self._variables
                },
                coords={"lat": grid.lats(), "lon": grid.lons()},
            )
        shape = (len(years.years()), grid.n_lat, grid.n_lon)
        coords = {"year": years.years(), "lat": grid.lats(), "lon": grid.lons()}
        return xr.Dataset(
            {
                name: (("year", "lat", "lon"), np.ones(shape, dtype="float64"))
                for name in self._variables
            },
            coords=coords,
        )

    def provenance(self) -> LayerProvenance:
        return LayerProvenance(
            name=self.name,
            source="Fake",
            product_id=f"{self.name}-product",
            dataset_id=self._dataset_id,
            version="1.0",
            retrieved_on=datetime(2026, 1, 1, tzinfo=UTC),
            licence="CC-BY-4.0",
            redistribution="allowed",
            source_url=f"https://example.invalid/{self.name}",
            archive=Archive(
                status="pending",
                source_url=f"https://example.invalid/{self.name}",
                unblocked_by="the Zenodo deposit in C§8.1",
            ),
            variables=list(self._claims),
        )
```

- [ ] **Step 7: Prove `FakeLayer` actually satisfies the Protocol**

Append to `tests/test_refresh_layer.py`:

```python
def test_fake_layer_satisfies_the_runtime_checkable_protocol():
    from refresh_fakes import FakeLayer

    from seagarden_dst.refresh.layer import Layer

    assert isinstance(FakeLayer("copernicus_phy", ["temp_c"]), Layer)
```

Run: `micromamba run -n shiny python -m pytest tests/test_refresh_layer.py -v`
Expected: 6 passed

- [ ] **Step 8: Remove the duplicated coverage tuple (R4)**

In `tests/refresh_builders.py`, delete the `_COVERAGE_LAYERS = (...)` assignment at line 25 and import the single definition instead:

```python
from seagarden_dst.refresh.layer import COVERAGE_LAYERS as _COVERAGE_LAYERS
```

Run the whole suite: `micromamba run -n shiny python -m pytest -q`
Expected: the pre-existing count, all passing. If any test changes behaviour, the two tuples had already drifted — report that, do not paper over it.

- [ ] **Step 9: Commit**

```bash
git add src/seagarden_dst/refresh/layer.py src/seagarden_dst/refresh/registry.py tests/refresh_fakes.py tests/test_refresh_layer.py tests/refresh_builders.py
git commit -m "feat(refresh): add the layer protocol, registry and test fakes"
```

- [ ] **Step 10: DELETE proof for the `YearRange` guard**

Comment out the body of `_check_end_does_not_precede_start` (leave `return self`). Run `micromamba run -n shiny python -m pytest tests/test_refresh_layer.py -v`. Record the actual failure line in the report — it must be `test_year_range_rejects_an_end_before_its_start` failing with `DID NOT RAISE`. Restore, re-run, record green. Paste both outputs into the task report.

---

### Task 2: The `valid` intersection and the merge

**Files:**
- Create: `src/seagarden_dst/refresh/merge.py`
- Test: `tests/test_refresh_merge.py`

**Interfaces:**
- Consumes: `COVERAGE_LAYERS` from Task 1
- Produces:
  - `compute_valid(per_layer: dict[str, xr.Dataset]) -> xr.DataArray` — a 2-D `(lat, lon)` bool array named `valid`, the intersection over `COVERAGE_LAYERS` (R5)
  - `merge_layers(per_layer: dict[str, xr.Dataset]) -> xr.Dataset` — the merged dataset carrying `valid`

- [ ] **Step 1: Write the failing test — two deliberately disagreeing masks (clause 11)**

```python
# tests/test_refresh_merge.py
import numpy as np
import pytest

pytest.importorskip("xarray")
import xarray as xr  # noqa: E402

from seagarden_dst.refresh.merge import compute_valid, merge_layers  # noqa: E402

pytestmark = pytest.mark.spatial

_COORDS = {"lat": [55.0, 55.5], "lon": [20.0, 20.5]}


def _spatial(name, values):
    return xr.Dataset(
        {name: (("lat", "lon"), np.array(values, dtype="float64"))}, coords=_COORDS
    )


def test_valid_is_the_intersection_of_two_disagreeing_masks():
    # Copernicus says the top row is wet; EMODnet says the left column is.
    # They agree only on the top-left cell.
    phy = _spatial("temp_c", [[1.0, 2.0], [np.nan, np.nan]])
    bathy = _spatial("depth_mean_m", [[3.0, np.nan], [4.0, np.nan]])
    valid = compute_valid({"copernicus_phy": phy, "emodnet_bathy": bathy})
    assert valid.dims == ("lat", "lon")
    np.testing.assert_array_equal(
        valid.values, np.array([[True, False], [False, False]])
    )


def test_a_cell_absent_in_any_timestep_is_not_covered():
    # R5: coverage is `.all()` over non-spatial dims, not `.any()`.
    layered = xr.Dataset(
        {
            "temp_c": (
                ("year", "lat", "lon"),
                np.array(
                    [[[1.0, 1.0], [1.0, 1.0]], [[1.0, np.nan], [1.0, 1.0]]],
                    dtype="float64",
                ),
            )
        },
        coords={"year": [2024, 2025], **_COORDS},
    )
    valid = compute_valid({"copernicus_phy": layered})
    np.testing.assert_array_equal(valid.values, np.array([[True, False], [True, True]]))


def test_the_light_layer_does_not_narrow_the_intersection():
    # `copernicus_bgc_light` is outside COVERAGE_LAYERS (ruling R4): an all-NaN
    # light layer must leave `valid` untouched, or the manifest's four-layer
    # attestation would describe a five-layer intersection.
    phy = _spatial("temp_c", [[1.0, 1.0], [1.0, 1.0]])
    light = _spatial("light_attenuation_k", [[np.nan, np.nan], [np.nan, np.nan]])
    valid = compute_valid({"copernicus_phy": phy, "copernicus_bgc_light": light})
    assert valid.values.all()


def test_merge_carries_valid_alongside_the_layer_variables():
    phy = _spatial("temp_c", [[1.0, 2.0], [3.0, np.nan]])
    bathy = _spatial("depth_mean_m", [[5.0, 6.0], [7.0, 8.0]])
    merged = merge_layers({"copernicus_phy": phy, "emodnet_bathy": bathy})
    assert set(merged.data_vars) == {"temp_c", "depth_mean_m", "valid"}
    assert merged["valid"].dtype == np.dtype("bool")


def test_compute_valid_refuses_when_no_coverage_layer_is_present():
    light = _spatial("light_attenuation_k", [[1.0, 1.0], [1.0, 1.0]])
    with pytest.raises(ValueError, match="no coverage layer was built"):
        compute_valid({"copernicus_bgc_light": light})
```

- [ ] **Step 2: Run to verify it fails**

Run: `micromamba run -n shiny python -m pytest tests/test_refresh_merge.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'seagarden_dst.refresh.merge'`

- [ ] **Step 3: Write `merge.py`**

```python
"""Merging layers, and the one field the driver computes rather than fetches (C§3.5).

Copernicus land-masking sits on the 2 km model grid; EMODnet bathymetry is an
independent ~115 m product. A cell can be wet in one and absent in the other, and the
disagreement concentrates at the coastline — which is where every farm is. So the
driver writes an explicit `valid`, and package D reads that rather than inferring
validity from whichever variable it happened to look at.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from seagarden_dst.refresh.layer import COVERAGE_LAYERS

if TYPE_CHECKING:  # pragma: no cover - typing only
    import xarray as xr

_SPATIAL_DIMS = ("lat", "lon")


def _coverage_of(dataset: xr.Dataset) -> xr.DataArray:
    """A 2-D mask: cells where every variable is present at every timestep.

    `.all()` rather than `.any()` (ruling R5) — a cell wet in some months and absent
    in others is not coverage a farm verdict should rest on. Failing small fails safe.
    """
    if not dataset.data_vars:
        raise ValueError(
            "a layer built no variables, so its coverage is undefined; an empty "
            "dataset here is a bug in the layer, not an empty intersection"
        )
    masks = [
        variable.notnull().all(
            dim=[d for d in variable.dims if d not in _SPATIAL_DIMS]
        )
        for variable in dataset.data_vars.values()
    ]
    covered = masks[0]
    for mask in masks[1:]:
        covered = covered & mask
    return covered


def compute_valid(per_layer: dict[str, xr.Dataset]) -> xr.DataArray:
    """The intersection of contributing layer coverage (C§3.5, C§10 clause 11).

    Taken over `COVERAGE_LAYERS` only. The manifest records that same list as the
    `valid` derivation's `input_layers`, so the two cannot disagree.
    """
    contributing = [name for name in COVERAGE_LAYERS if name in per_layer]
    if not contributing:
        raise ValueError(
            "no coverage layer was built, so `valid` would be an intersection over "
            "nothing and every cell would read as valid; expected at least one of "
            f"{list(COVERAGE_LAYERS)}"
        )
    valid = _coverage_of(per_layer[contributing[0]])
    for name in contributing[1:]:
        valid = valid & _coverage_of(per_layer[name])
    return valid.rename("valid")


def merge_layers(per_layer: dict[str, xr.Dataset]) -> xr.Dataset:
    """Merge every layer onto one dataset and attach `valid`."""
    import xarray as xr

    merged = xr.merge(list(per_layer.values()), join="exact", combine_attrs="drop")
    return merged.assign(valid=compute_valid(per_layer))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `micromamba run -n shiny python -m pytest tests/test_refresh_merge.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/seagarden_dst/refresh/merge.py tests/test_refresh_merge.py
git commit -m "feat(refresh): compute the valid mask as a layer-coverage intersection"
```

- [ ] **Step 6: DELETE proof — the `.all()` reduction**

Change `.all(` to `.any(` in `_coverage_of`. Run the module. `test_a_cell_absent_in_any_timestep_is_not_covered` must go red on the array comparison. Restore, re-run green. Record both outputs.

- [ ] **Step 7: DELETE proof — the `COVERAGE_LAYERS` filter**

Replace `contributing = [name for name in COVERAGE_LAYERS if name in per_layer]` with `contributing = list(per_layer)`. `test_the_light_layer_does_not_narrow_the_intersection` must go red, and `test_compute_valid_refuses_when_no_coverage_layer_is_present` must go red too. Restore, re-run green. Record both outputs — this is the mutation that proves R4 is load-bearing rather than decorative.

---

### Task 3: The driver

**Files:**
- Create: `src/seagarden_dst/refresh/driver.py`
- Modify: `tests/conftest.py` (two new fixtures)
- Test: `tests/test_refresh_driver.py`

**Interfaces:**
- Consumes: `merge_layers` (Task 2), `Layer`/`YearRange`/`COVERAGE_LAYERS` (Task 1), `seagarden_dst.refresh.variables.ARTIFACT_VARIABLES`, `seagarden_dst.refresh.writer.write_pair`, `seagarden_dst.artifact.manifest.{Manifest, Derivation, AbsentField, ARTIFACT_SCHEMA_VERSION}`, `seagarden_dst.artifact.grid.GridSpec`
- Produces:
  - `derive_baselines(dataset: xr.Dataset) -> dict[str, list[int]]` (R2)
  - `run_refresh(layers, grid, years, target_dir, workdir, *, synthetic=False) -> tuple[Path, Path]`
  - `RefreshFailed(RuntimeError)` — raised when any layer fails, naming the layer

- [ ] **Step 1: Add the two fixtures to `tests/conftest.py`**

```python
@pytest.fixture
def small_grid():
    from seagarden_dst.artifact.grid import GridSpec

    return GridSpec(
        crs="EPSG:4326",
        lat_min=55.0,
        lat_max=55.05,
        lon_min=20.0,
        lon_max=20.09,
        lat_step=0.016666,
        lon_step=0.027777,
        n_lat=3,
        n_lon=3,
    )


@pytest.fixture
def nine_variable_layers():
    """Five fakes between them producing exactly `ARTIFACT_VARIABLES` minus `valid`.

    `valid` is absent on purpose: the driver computes it, so a fake that supplied it
    would hide a driver that had stopped computing it.

    The `claims` arguments mirror `tests/refresh_builders.py` exactly — `din_umol_l`
    and `light_attenuation_k` are claimed by Derivations, not by the layers that
    produce them, so claiming them here too would trip C§4.4's claimed-exactly-once
    validator. `emodnet_bathy` is static, which is what gives `depth_mean_m` and
    `depth_min_m` the empty baselines C§4.4 tells apart from omission.
    """
    from refresh_fakes import FakeLayer

    return [
        FakeLayer("copernicus_phy", ["salinity_psu", "temp_c"]),
        FakeLayer("copernicus_bgc", ["din_umol_l", "dip_umol_l"], claims=["dip_umol_l"]),
        FakeLayer("copernicus_bgc_light", ["light_attenuation_k"], claims=[]),
        FakeLayer("copernicus_wav", ["significant_wave_m"]),
        FakeLayer(
            "emodnet_bathy", ["depth_mean_m", "depth_min_m"], static=True
        ),
    ]
```

The `GridSpec` values above must satisfy `GridSpec`'s own extent validator. Read `src/seagarden_dst/artifact/grid.py` and adjust the bounds if the validator rejects them — do not weaken the validator.

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_refresh_driver.py
import numpy as np
import pytest
from pydantic import ValidationError

pytest.importorskip("xarray")
import xarray as xr  # noqa: E402

from refresh_fakes import FakeLayer  # noqa: E402

from seagarden_dst.artifact.pair import load_pair  # noqa: E402
from seagarden_dst.refresh.driver import (  # noqa: E402
    RefreshFailed,
    derive_baselines,
    run_refresh,
)
from seagarden_dst.refresh.layer import YearRange  # noqa: E402

pytestmark = pytest.mark.spatial


def test_derive_baselines_reads_years_off_the_data():
    dataset = xr.Dataset(
        {
            "temp_c": (("year", "lat"), np.ones((2, 2))),
            "depth_mean_m": (("lat",), np.ones(2)),
        },
        coords={"year": [2024, 2025], "lat": [55.0, 55.5]},
    )
    assert derive_baselines(dataset) == {"temp_c": [2024, 2025], "depth_mean_m": []}


def test_a_static_field_gets_an_empty_baseline_not_an_omission():
    # C§4.4 tells `[]` and omission apart; a static field must be present-and-empty.
    dataset = xr.Dataset(
        {"depth_min_m": (("lat",), np.ones(2))}, coords={"lat": [55.0, 55.5]}
    )
    baselines = derive_baselines(dataset)
    assert "depth_min_m" in baselines
    assert baselines["depth_min_m"] == []


def test_one_failing_layer_fails_the_whole_refresh(tmp_path, small_grid):
    # C§6.1 row 1. A missing variable quietly defaulting is the unmarked-provenance
    # hazard the manifest exists to prevent.
    layers = [
        FakeLayer("copernicus_phy", ["temp_c"]),
        FakeLayer("emodnet_bathy", ["depth_mean_m"], fail_on_build=True),
    ]
    with pytest.raises(RefreshFailed, match="layer 'emodnet_bathy' failed to build"):
        run_refresh(
            layers,
            grid=small_grid,
            years=YearRange(start=2024, end=2024),
            target_dir=tmp_path / "out",
            workdir=tmp_path / "work",
        )


def test_a_failing_layer_writes_no_partial_artifact(tmp_path, small_grid):
    target = tmp_path / "out"
    layers = [
        FakeLayer("copernicus_phy", ["temp_c"]),
        FakeLayer("emodnet_bathy", ["depth_mean_m"], fail_on_build=True),
    ]
    with pytest.raises(RefreshFailed):
        run_refresh(
            layers,
            grid=small_grid,
            years=YearRange(start=2024, end=2024),
            target_dir=target,
            workdir=tmp_path / "work",
        )
    assert not (target / "forcing.nc").exists()
    assert not (target / "manifest.json").exists()


def test_an_interrupted_refresh_leaves_the_previous_pair_valid(
    tmp_path, small_grid, nine_variable_layers
):
    # C§10 clause 5 / C§6.1 row 2.
    target = tmp_path / "out"
    years = YearRange(start=2024, end=2024)
    run_refresh(
        nine_variable_layers,
        grid=small_grid,
        years=years,
        target_dir=target,
        workdir=tmp_path / "w1",
    )
    first_manifest, _ = load_pair(target)

    failing = [
        *nine_variable_layers[:-1],
        FakeLayer(
            "emodnet_bathy", ["depth_mean_m", "depth_min_m"], fail_on_build=True
        ),
    ]
    with pytest.raises(RefreshFailed):
        run_refresh(
            failing,
            grid=small_grid,
            years=years,
            target_dir=target,
            workdir=tmp_path / "w2",
        )

    second_manifest, artifact = load_pair(target)
    assert second_manifest.artifact_sha256 == first_manifest.artifact_sha256
    assert artifact.exists()


def test_a_successful_refresh_writes_a_loadable_pair(
    tmp_path, small_grid, nine_variable_layers
):
    # C§10 clause 1.
    target = tmp_path / "out"
    run_refresh(
        nine_variable_layers,
        grid=small_grid,
        years=YearRange(start=2024, end=2025),
        target_dir=target,
        workdir=tmp_path / "work",
    )
    manifest, artifact = load_pair(target)
    assert artifact.exists()
    assert set(manifest.variables) == {
        "salinity_psu",
        "temp_c",
        "din_umol_l",
        "dip_umol_l",
        "light_attenuation_k",
        "significant_wave_m",
        "depth_mean_m",
        "depth_min_m",
        "valid",
    }


def test_a_partial_layer_set_cannot_produce_a_manifest(tmp_path, small_grid):
    # A driver that built only one layer still declares all nine variables, so
    # C§4.4's claimed-exactly-once rule fires at manifest construction — before
    # `write_pair` and its `check_declaration` are ever reached. That ordering is
    # the point: the manifest refuses to describe an artifact nobody built.
    layers = [FakeLayer("copernicus_phy", ["salinity_psu", "temp_c"])]
    with pytest.raises(ValidationError) as caught:
        run_refresh(
            layers,
            grid=small_grid,
            years=YearRange(start=2024, end=2024),
            target_dir=tmp_path / "out",
            workdir=tmp_path / "work",
        )
    # Name the unclaimed variables, not merely "something raised".
    assert "dip_umol_l" in str(caught.value)


def test_a_layer_that_claims_more_than_it_builds_is_refused(
    tmp_path, small_grid, nine_variable_layers
):
    # Every layer present and claiming correctly, but the wave layer produces
    # something other than what it claims. Under ruling R2 `baselines` is derived
    # from the built data, so the manifest's baselines-keys validator catches this
    # at construction — see the ordering note in R3.
    crippled = [
        *nine_variable_layers[:3],
        FakeLayer("copernicus_wav", ["not_the_wave_field"], claims=["significant_wave_m"]),
        nine_variable_layers[4],
    ]
    with pytest.raises(ValidationError, match="baselines keys must be exactly"):
        run_refresh(
            crippled,
            grid=small_grid,
            years=YearRange(start=2024, end=2024),
            target_dir=tmp_path / "out",
            workdir=tmp_path / "work",
        )


def test_a_layer_building_nothing_is_a_loud_error(small_grid):
    # A real layer returning an empty dataset is a bug in that layer. It must say
    # so, not fall out of `_coverage_of` as an IndexError from `masks[0]`.
    empty = xr.Dataset(coords={"lat": small_grid.lats(), "lon": small_grid.lons()})
    from seagarden_dst.refresh.merge import compute_valid

    with pytest.raises(ValueError, match="built no variables"):
        compute_valid({"copernicus_phy": empty})
```

`ValidationError` imports from `pydantic`. The `match=` fragment is copied from `_check_baseline_keys_are_exactly_the_artifact_variables` in `src/seagarden_dst/artifact/manifest.py` — if it has changed, copy the current one rather than loosening the match.

- [ ] **Step 3: Run to verify it fails**

Run: `micromamba run -n shiny python -m pytest tests/test_refresh_driver.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'seagarden_dst.refresh.driver'`

- [ ] **Step 4: Write `driver.py`**

```python
"""Build every layer, merge, and write the pair (C§5, C§6).

The driver holds the real Dataset, which makes it the only place that can anchor the
manifest's `variables` declaration against what was actually built. It does not call
`check_declaration` itself — `write_pair` already does (ruling R3).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Sequence

from seagarden_dst.artifact.grid import GridSpec
from seagarden_dst.artifact.manifest import (
    ARTIFACT_SCHEMA_VERSION,
    Derivation,
    Manifest,
)
from seagarden_dst.refresh.layer import COVERAGE_LAYERS, Layer, YearRange
from seagarden_dst.refresh.merge import merge_layers
from seagarden_dst.refresh.variables import ARTIFACT_VARIABLES
from seagarden_dst.refresh.writer import write_pair

if TYPE_CHECKING:  # pragma: no cover - typing only
    import xarray as xr


class RefreshFailed(RuntimeError):
    """Any layer failing takes the whole refresh with it (C§6.1 row 1)."""


def derive_baselines(dataset: xr.Dataset) -> dict[str, list[int]]:
    """Read each variable's baseline years off the data (ruling R2).

    A declared baseline is a claim that can drift from the artifact; a derived one
    cannot. Variables with no `year` dimension get `[]` — present and empty, which
    C§4.4 tells apart from omission.
    """
    baselines: dict[str, list[int]] = {}
    for name, variable in dataset.data_vars.items():
        if "year" in variable.dims:
            baselines[str(name)] = [int(year) for year in variable["year"].values]
        else:
            baselines[str(name)] = []
    return baselines


def _build_all(
    layers: Sequence[Layer], grid: GridSpec, years: YearRange, workdir: Path
) -> dict[str, xr.Dataset]:
    built: dict[str, xr.Dataset] = {}
    for layer in layers:
        try:
            built[layer.name] = layer.build(grid, years, workdir)
        except Exception as error:  # noqa: BLE001 - re-raised with the layer named
            raise RefreshFailed(
                f"layer '{layer.name}' failed to build, so the whole refresh fails: "
                f"{error}. A missing variable quietly defaulting would leave the "
                "manifest attesting to a completeness the artifact lacks."
            ) from error
    return built


def _derivations() -> list[Derivation]:
    return [
        Derivation(
            field="light_attenuation_k",
            relation=(
                "Poole-Atkins k = 1.7/z_SD over daily zsd, computed daily then "
                "averaged monthly"
            ),
            input_layers=["copernicus_bgc_light"],
        ),
        Derivation(
            field="valid",
            relation="intersection of contributing layer coverage",
            input_layers=list(COVERAGE_LAYERS),
        ),
        Derivation(
            field="din_umol_l",
            relation=(
                "din_umol_l = no3 + nh4: sum of dissolved inorganic nitrogen "
                "species, no unit conversion"
            ),
            input_layers=["copernicus_bgc"],
        ),
    ]


def run_refresh(
    layers: Sequence[Layer],
    grid: GridSpec,
    years: YearRange,
    target_dir: Path,
    workdir: Path,
    *,
    synthetic: bool = False,
) -> tuple[Path, Path]:
    """Run a full refresh for `years` and write the pair (C§10 clause 1)."""
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)

    built = _build_all(layers, grid, years, workdir)
    merged = merge_layers(built)

    manifest = Manifest(
        artifact_schema_version=ARTIFACT_SCHEMA_VERSION,
        built_on=datetime.now(UTC),
        artifact_filename="forcing.nc",
        artifact_sha256="0" * 64,  # stamped by write_pair over the real bytes
        artifact_bytes=1,
        synthetic=synthetic,
        grid=grid,
        variables=sorted(ARTIFACT_VARIABLES),
        baselines=derive_baselines(merged),
        layers=[layer.provenance() for layer in layers],
        derived=_derivations(),
        absent=_absent_fields(),
    )
    return write_pair(merged, manifest, Path(target_dir))
```

`_absent_fields()` completes the module. `AbsentField` carries exactly three fields (`field`, `reason`, `unblocked_by`), and C§3.3 is why `surface_par` is the only entry:

```python
def _absent_fields() -> list[AbsentField]:
    """What the artifact deliberately does not carry (C§3.3, C§4.2).

    Machine-readable so the UI reads the manifest rather than carrying a hardcoded
    caveat that can drift away from the artifact it describes.
    """
    return [
        AbsentField(
            field="surface_par",
            reason="no integrated Baltic product carries PAR in any form",
            unblocked_by="a source outside the current layer set",
        )
    ]
```

Add `AbsentField` to the `seagarden_dst.artifact.manifest` import list at the top of the module.

- [ ] **Step 5: Run tests to verify they pass**

Run: `micromamba run -n shiny python -m pytest tests/test_refresh_driver.py -v`
Expected: 9 passed

- [ ] **Step 6: Commit**

```bash
git add src/seagarden_dst/refresh/driver.py tests/test_refresh_driver.py tests/conftest.py
git commit -m "feat(refresh): add the driver that builds, merges and writes the pair"
```

- [ ] **Step 7: DELETE proof — fail-on-any-layer**

Replace the `raise RefreshFailed(...)` in `_build_all` with `continue`. `test_one_failing_layer_fails_the_whole_refresh` and `test_a_failing_layer_writes_no_partial_artifact` must both go red. Restore, re-run green. Record both outputs.

- [ ] **Step 8: DELETE proof — the static-baseline branch**

Change the `else` branch of `derive_baselines` to `continue` (omitting the key instead of writing `[]`). `test_a_static_field_gets_an_empty_baseline_not_an_omission` must go red *and* the manifest's `baselines`-keys validator must reject, failing `test_a_successful_refresh_writes_a_loadable_pair`. Restore, re-run green. Record both outputs.

---

### Task 4: The CLI

**Files:**
- Create: `scripts/refresh_layers.py`
- Test: `tests/test_refresh_cli.py`

**Interfaces:**
- Consumes: `seagarden_dst.refresh.registry.REGISTRY`, `run_refresh` (Task 3), `YearRange`/`ProbeResult` (Task 1)
- Produces:
  - `build_parser() -> argparse.ArgumentParser`
  - `probe_all(layers: Sequence[Layer]) -> list[ProbeResult]`
  - `format_probe_report(results: Sequence[ProbeResult]) -> str`
  - `main(argv: list[str] | None = None) -> int` — 0 on success, 1 when any probe is unreachable
  - Module-level `REGISTRY` rebound name, so tests can monkeypatch it

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_refresh_cli.py
import pytest

from refresh_fakes import FakeLayer

from scripts.refresh_layers import build_parser, format_probe_report, main, probe_all


def test_the_parser_reads_an_inclusive_year_range():
    args = build_parser().parse_args(["--start-year", "2016", "--end-year", "2025"])
    assert (args.start_year, args.end_year) == (2016, 2025)


def test_probe_mode_needs_no_year_range():
    args = build_parser().parse_args(["--probe"])
    assert args.probe is True


def test_probe_all_reports_one_result_per_layer():
    layers = [
        FakeLayer("copernicus_phy", ["temp_c"]),
        FakeLayer("emodnet_bathy", ["depth_mean_m"], reachable=False),
    ]
    results = probe_all(layers)
    assert [(r.name, r.reachable) for r in results] == [
        ("copernicus_phy", True),
        ("emodnet_bathy", False),
    ]


def test_the_report_names_every_unreachable_layer():
    layers = [
        FakeLayer("copernicus_phy", ["temp_c"]),
        FakeLayer("emodnet_bathy", ["depth_mean_m"], reachable=False),
    ]
    report = format_probe_report(probe_all(layers))
    assert "UNREACHABLE emodnet_bathy" in report
    assert "ok          copernicus_phy" in report


def test_an_unreachable_layer_makes_the_probe_exit_nonzero(monkeypatch):
    # C§8.2: the job turns red so a dead upstream is loud — and it lives outside
    # ci.yml so that redness blocks no pull request.
    import scripts.refresh_layers as cli

    monkeypatch.setattr(
        cli,
        "REGISTRY",
        {
            "emodnet_bathy": FakeLayer(
                "emodnet_bathy", ["depth_mean_m"], reachable=False
            )
        },
    )
    assert main(["--probe"]) == 1


def test_an_all_reachable_probe_exits_zero(monkeypatch):
    import scripts.refresh_layers as cli

    monkeypatch.setattr(
        cli, "REGISTRY", {"copernicus_phy": FakeLayer("copernicus_phy", ["temp_c"])}
    )
    assert main(["--probe"]) == 0


def test_a_refresh_without_a_year_range_is_refused(capsys):
    with pytest.raises(SystemExit):
        main([])
    assert "--start-year and --end-year are required" in capsys.readouterr().err
```

- [ ] **Step 2: Run to verify it fails**

Run: `micromamba run -n shiny python -m pytest tests/test_refresh_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.refresh_layers'`

- [ ] **Step 3: Write `scripts/refresh_layers.py`**

Read `scripts/make_fixture.py` first and copy its `sys.path` preamble verbatim, comment included — the same development-environment reason applies here. Insert it where the `# ... sys.path preamble ...` marker sits below.

```python
"""The refresh entry point (C§5, C§8.2).

Two modes and no third: a full refresh for a named year range, and `--probe`, which
asks only whether each source still exists. `--probe` is what the monthly workflow
runs, so nothing on that path may import xarray — the probe job installs no spatial
extra, and a module-scope import would make a reachability check depend on the
scientific stack it exists to avoid needing.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

# ... sys.path preamble copied from scripts/make_fixture.py ...

from seagarden_dst.refresh.layer import Layer, ProbeResult, YearRange
from seagarden_dst.refresh.registry import REGISTRY


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="refresh_layers",
        description="Build the SeaGarden forcing artifact, or probe its sources.",
    )
    parser.add_argument(
        "--probe",
        action="store_true",
        help="report per-layer reachability and exit; performs no bulk transfer",
    )
    parser.add_argument("--start-year", type=int, help="first year of the refresh")
    parser.add_argument("--end-year", type=int, help="last year, inclusive")
    parser.add_argument(
        "--target",
        type=Path,
        default=Path("data/forcing"),
        help="directory receiving the artifact/manifest pair",
    )
    parser.add_argument(
        "--workdir",
        type=Path,
        default=Path(".refresh-work"),
        help="scratch space for layer builds",
    )
    return parser


def probe_all(layers: Sequence[Layer]) -> list[ProbeResult]:
    """Probe every layer. One result per layer, in the order given."""
    return [layer.probe() for layer in layers]


def format_probe_report(results: Sequence[ProbeResult]) -> str:
    """One line per layer, status first so a red job is readable at a glance."""
    lines = []
    for result in results:
        status = "ok         " if result.reachable else "UNREACHABLE"
        lines.append(f"{status} {result.name}  {result.detail}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.probe:
        results = probe_all(list(REGISTRY.values()))
        print(format_probe_report(results))
        unreachable = [r.name for r in results if not r.reachable]
        if unreachable:
            print(f"\n{len(unreachable)} source(s) unreachable: {unreachable}")
            return 1
        return 0

    if args.start_year is None or args.end_year is None:
        parser.error("--start-year and --end-year are required for a refresh")

    # Imported here, not at module scope: the probe path must stay free of xarray.
    from seagarden_dst.artifact.grid import GridSpec
    from seagarden_dst.refresh.driver import run_refresh

    artifact, manifest = run_refresh(
        list(REGISTRY.values()),
        grid=GridSpec.baltic(),
        years=YearRange(start=args.start_year, end=args.end_year),
        target_dir=args.target,
        workdir=args.workdir,
    )
    print(f"wrote {artifact}\nwrote {manifest}")
    return 0


if __name__ == "__main__":  # pragma: no cover - entry point
    raise SystemExit(main())
```

Three things the implementer must not "tidy":

1. **`REGISTRY` is a module-level name**, so `monkeypatch.setattr(cli, "REGISTRY", ...)` reaches what `main` reads. `main` must read the module global, never re-import it inside the function.
2. **The `run_refresh` import stays inside the refresh branch** — see the module docstring.
3. **`"ok         "` carries eleven characters** so it aligns with `"UNREACHABLE"`. The test asserts `"ok          copernicus_phy"` — eleven plus the separating space. Count them rather than eyeballing; if the assertion and the format disagree, fix the format, and say in the report which way you resolved it.

Exit codes: `0` success, `1` a probe found something unreachable, `2` argparse usage error (`parser.error` raises `SystemExit(2)` and writes to stderr, which is what `test_a_refresh_without_a_year_range_is_refused` reads).

- [ ] **Step 4: Run tests to verify they pass**

Run: `micromamba run -n shiny python -m pytest tests/test_refresh_cli.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/refresh_layers.py tests/test_refresh_cli.py
git commit -m "feat(refresh): add the refresh_layers CLI with a probe mode"
```

- [ ] **Step 6: SWAP proof — the two report lines**

Both report lines carry the layer name, so deleting one is not enough to prove the test reads the *status*. Swap the `ok` and `UNREACHABLE` prefixes in `format_probe_report`. `test_the_report_names_every_unreachable_layer` must go red on *both* assertions. Restore, re-run green. Record both outputs.

- [ ] **Step 7: DELETE proof — the nonzero exit**

Make `main` return `0` unconditionally in probe mode. `test_an_unreachable_layer_makes_the_probe_exit_nonzero` must go red while `test_an_all_reachable_probe_exits_zero` stays green — that asymmetry is what proves the test discriminates rather than merely running. Restore, re-run green. Record both outputs.

---

### Task 5: The deposit stub

**Files:**
- Create: `src/seagarden_dst/refresh/deposit.py`
- Test: `tests/test_refresh_deposit.py`

**Interfaces:**
- Consumes: `seagarden_dst.artifact.manifest.{Manifest, Archive}`, `tests/refresh_builders.py:manifest()`
- Produces:
  - `Depositor` — a `@runtime_checkable` Protocol with `deposit(artifact: Path, manifest: Path) -> str` returning a DOI
  - `record_doi(manifest: Manifest, doi: str) -> Manifest` — flips every `pending` layer to `deposited`, re-validating

- [ ] **Step 1: Note the builder's archive state**

`refresh_builders.manifest()` produces all five layers with `archive.status == "pending"` — checked while writing this plan, not assumed. The tests below rely on it. If that has changed by the time you run them, set up the `pending` state explicitly in the test — adjust the *setup*, never the assertion.

- [ ] **Step 2: Write the failing tests (clause 9)**

```python
# tests/test_refresh_deposit.py
import pytest

from refresh_builders import manifest as build_manifest

from seagarden_dst.artifact.manifest import Manifest
from seagarden_dst.refresh.deposit import Depositor, record_doi

_DOI = "10.5281/zenodo.9999999"


class StubDepositor:
    """C§9: no Zenodo deposit is performed. The path is exercised, not the service."""

    def deposit(self, artifact, manifest):
        return _DOI


def test_the_stub_satisfies_the_depositor_protocol():
    assert isinstance(StubDepositor(), Depositor)


def test_recording_a_doi_flips_pending_layers_to_deposited():
    before = build_manifest()
    assert all(layer.archive.status == "pending" for layer in before.layers)
    after = record_doi(before, StubDepositor().deposit("forcing.nc", "manifest.json"))
    assert all(layer.archive.status == "deposited" for layer in after.layers)
    assert all(layer.archive.zenodo_doi == _DOI for layer in after.layers)


def test_the_flipped_manifest_still_validates():
    # model_copy does not re-run validators, so record_doi must re-validate or it
    # can emit a manifest that skipped every C§4.4 rule.
    after = record_doi(build_manifest(), _DOI)
    Manifest.model_validate(after.model_dump())


def test_a_forbidden_layer_is_not_flipped():
    # C§6.1's last row: a layer marked forbidden is the mis-marking hazard, and a
    # deposit must not launder it into `deposited`.
    before = build_manifest()
    before.layers[0].archive.status = "forbidden"
    before.layers[0].archive.zenodo_doi = None
    after = record_doi(before, _DOI)
    assert after.layers[0].archive.status == "forbidden"
    assert after.layers[0].archive.zenodo_doi is None


def test_an_empty_doi_is_refused():
    with pytest.raises(ValueError, match="deposit returned no DOI"):
        record_doi(build_manifest(), "")
```

- [ ] **Step 3: Run to verify it fails**

Run: `micromamba run -n shiny python -m pytest tests/test_refresh_deposit.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'seagarden_dst.refresh.deposit'`

- [ ] **Step 4: Write `deposit.py`**

```python
"""Recording a Zenodo deposit back into the manifest (C§8.1, C§9).

**No deposit is performed here.** C§9 puts the deposit itself outside package C: a
human runs it, following the runbook. What this module owns is the half that can be
tested — the shape of a depositor, and what recording its DOI does to the manifest.

The sequence C§8.1 fixes, and the reason the two manifests differ:

    build  → every layer `archive.status: pending`, no DOI exists yet
    deposit → Zenodo returns a DOI
    record → the DOI goes back into the COMMITTED manifest, flipping those
             layers to `deposited`

So the deposited copy is a snapshot of the moment before the DOI existed, and the
committed manifest is authoritative for provenance. `artifact_sha256` is unaffected
throughout — it covers the artifact, and the artifact does not change.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from seagarden_dst.artifact.manifest import Manifest


@runtime_checkable
class Depositor(Protocol):
    """Whatever puts the pair somewhere permanent and returns its DOI."""

    def deposit(self, artifact: Path, manifest: Path) -> str: ...


def record_doi(manifest: Manifest, doi: str) -> Manifest:
    """Flip every `pending` layer to `deposited`, carrying `doi`.

    Only `pending` layers move. A `forbidden` layer is the mis-marking hazard of
    C§6.1's last row, and laundering it into `deposited` on the strength of a deposit
    it was never part of is exactly the unmarked provenance this design exists to
    prevent. A `deposited` layer already has its own DOI and keeps it.
    """
    if not doi or not doi.strip():
        raise ValueError(
            "deposit returned no DOI, so there is nothing to record; a layer flipped "
            "to 'deposited' without one would claim an archive that does not exist"
        )

    payload = manifest.model_dump()
    for layer in payload["layers"]:
        if layer["archive"]["status"] == "pending":
            layer["archive"]["status"] = "deposited"
            layer["archive"]["zenodo_doi"] = doi

    # Rebuilt through the validators, not `model_copy(update=)`, which does not re-run
    # them. Emitting a manifest that skipped C§4.4 is the one thing this package must
    # never do — and `Archive` itself requires a DOI for `deposited`, so the flip is
    # checked rather than trusted.
    return Manifest.model_validate(payload)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `micromamba run -n shiny python -m pytest tests/test_refresh_deposit.py -v`
Expected: 5 passed

- [ ] **Step 6: Commit**

```bash
git add src/seagarden_dst/refresh/deposit.py tests/test_refresh_deposit.py
git commit -m "feat(refresh): add the deposit protocol and DOI recording"
```

- [ ] **Step 7: DELETE proof — the status filter**

Make `record_doi` flip every layer regardless of status. `test_a_forbidden_layer_is_not_flipped` must go red. Restore, re-run green. Record both outputs.

- [ ] **Step 8: DELETE proof — the re-validation**

Replace the `Manifest.model_validate(payload)` return with `Manifest.model_construct(**payload)`, which builds the model while skipping every validator.

Expect this one **not** to go red on its own: `test_the_flipped_manifest_still_validates` calls `model_validate` itself, so it re-validates what `record_doi` failed to. That means the test does not discriminate, and the honest response is to add the test that does — flip a layer to `deposited` while clearing its `zenodo_doi`, and show that the un-revalidated path returns it happily while the validated path raises `Archive`'s "requires a zenodo_doi". Add that test, confirm it goes red under `model_construct` and green under `model_validate`, then restore. Record every output, including the fact that the original test stayed green — a mutation that changes nothing is a finding about the test, not a clean bill of health.

---

### Task 6: The scheduled probe workflow

**Files:**
- Create: `.github/workflows/source-probe.yml`
- Test: `tests/test_refresh_cli.py` (extend)

**Interfaces:**
- Consumes: `scripts/refresh_layers.py --probe` (Task 4)
- Produces: a workflow that runs monthly and on `workflow_dispatch`, and blocks no pull request

- [ ] **Step 1: Write the failing test**

Append to `tests/test_refresh_cli.py`:

```python
from pathlib import Path

import yaml

_WORKFLOWS = Path(__file__).resolve().parent.parent / ".github" / "workflows"
_PROBE = _WORKFLOWS / "source-probe.yml"


def _workflow():
    # PyYAML parses the unquoted key `on` as the boolean True (the Norway problem),
    # so the triggers live under the True key, not under "on".
    return yaml.safe_load(_PROBE.read_text(encoding="utf-8"))


def test_the_probe_workflow_is_scheduled_and_dispatchable():
    triggers = _workflow()[True]
    assert "schedule" in triggers
    assert "workflow_dispatch" in triggers


def test_the_probe_workflow_blocks_no_pull_request():
    # C§8.2: gating merges on a third-party service would make every PR hostage
    # to Copernicus.
    triggers = _workflow()[True]
    assert "pull_request" not in triggers
    assert "push" not in triggers


def test_the_probe_workflow_is_a_separate_file_from_ci():
    assert _PROBE.exists()
    assert (_WORKFLOWS / "ci.yml").exists()


def test_the_probe_workflow_runs_the_probe_flag():
    steps = _workflow()["jobs"]["probe"]["steps"]
    assert any("--probe" in str(step.get("run", "")) for step in steps)
```

The `True` key is not a guess: checked against this environment's PyYAML, `yaml.safe_load("on:\n  schedule: []\n")` returns a dict whose only key is the boolean `True`. Do not "fix" it to `"on"`.

- [ ] **Step 2: Run to verify it fails**

Run: `micromamba run -n shiny python -m pytest tests/test_refresh_cli.py -v -k workflow`
Expected: FAIL — `FileNotFoundError` on `source-probe.yml`

- [ ] **Step 3: Write the workflow**

Read `.github/workflows/ci.yml` first and match its conventions — runner image, Python setup action and version, and install command. If `ci.yml` installs with a single line, follow it rather than inventing a second pattern.

```yaml
name: source-probe

# Separate from ci.yml on purpose (C§8.2): a dead upstream source turns this job
# red and blocks no pull request. Gating merges on the continued existence of a
# third-party service would make every PR hostage to Copernicus.
on:
  schedule:
    - cron: "0 6 1 * *"   # 06:00 UTC on the first of each month
  workflow_dispatch:

jobs:
  probe:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      # ... Python setup and install, matched to ci.yml ...
      - name: Probe every registered source
        env:
          COPERNICUSMARINE_SERVICE_USERNAME: ${{ secrets.COPERNICUSMARINE_SERVICE_USERNAME }}
          COPERNICUSMARINE_SERVICE_PASSWORD: ${{ secrets.COPERNICUSMARINE_SERVICE_PASSWORD }}
        run: python -m scripts.refresh_layers --probe
```

The credential is the **institutional** Copernicus account (C§8.1), held as a repository secret. The workflow must not fall back to a personal one, and must not print the credential.

- [ ] **Step 4: Run tests to verify they pass**

Run: `micromamba run -n shiny python -m pytest tests/test_refresh_cli.py -v`
Expected: 11 passed

- [ ] **Step 5: Run the whole suite and the linter**

```bash
micromamba run -n shiny python -m pytest -q
micromamba run -n shiny python -m pytest -q -m spatial
micromamba run -n shiny ruff check .
```
Expected: all green. Record the counts in the report.

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/source-probe.yml tests/test_refresh_cli.py
git commit -m "ci: add the monthly source-probe workflow, separate from ci.yml"
```

- [ ] **Step 7: DELETE proof — the trigger separation**

Add `pull_request:` to the workflow's triggers. `test_the_probe_workflow_blocks_no_pull_request` must go red. Restore, re-run green. Record both outputs.

---

## Done-When Coverage

| Clause | Task | How it is proven |
|---|---|---|
| 1 — builds artifact and manifest for a named year range | 3, 4 | `test_a_successful_refresh_writes_a_loadable_pair`, parser tests |
| 5 — interrupted refresh leaves previous pair valid | 3 | `test_an_interrupted_refresh_leaves_the_previous_pair_valid` |
| 6 — `--probe` reports reachability, scheduled separately | 4, 6 | CLI exit-code tests + workflow trigger tests |
| 9 — deposit path exercised against a stub | 5 | `test_recording_a_doi_flips_pending_layers_to_deposited` |
| 11 — `valid` is the coverage intersection | 2 | `test_valid_is_the_intersection_of_two_disagreeing_masks` |

Clauses 2, 3, 4, 8, 10 and 12 were discharged by package C-a and their tests must stay green.

Clause 7 — the runbook followed end to end by someone who did not write it — **cannot be discharged by an implementer**; it is a human act. C-b writes no runbook: `docs/runbooks/annual-refresh.md` (C§8.1) belongs to C-c, when the transfer volumes and runtimes it must carry are measurable rather than estimated.

## Out of Scope

The five real layer implementations (C-c), the EMODnet regrid with `rioxarray`/`rasterio`, the free-disk precheck (C§6.1 — it needs the real transfer volumes to name a requirement), and the annual-refresh runbook.
