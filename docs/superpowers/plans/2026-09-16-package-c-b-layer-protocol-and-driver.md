# Package C-b: Layer Protocol, Driver and Probe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the orchestration half of package C — the `Layer` protocol, the `REGISTRY`, the refresh driver that merges layers into the artifact pair, the `--probe` CLI and its scheduled workflow, and the deposit stub — all provable without a single network call.

**Architecture:** C-a delivered the *data* half: `GridSpec`, `Manifest`, `write_pair`, `check_declaration`. C-b delivers the *control* half that drives them. The five real layer implementations are **out of scope** (they are C-c); C-b defines the protocol they must satisfy and proves the driver against synthetic `FakeLayer` implementations living in `tests/`. This is what makes C-b independently testable: every clause it discharges is provable offline, and C-c becomes five isolated, individually-reviewable implementations of an interface that already has a green driver behind it.

**Tech Stack:** Python 3.11+, Pydantic v2, xarray + h5netcdf (the `spatial` extra), pytest, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-15-package-c-refresh-tooling-design.md`

## Read This First: The Three Shapes And The Two Coordinate Names

A multi-agent review of this plan's first draft found three blocking defects, all from one root cause: reasoning from the spec's prose and the Pydantic models without reading the **shipped tests**. Those tests encode traps the prose does not. Before writing any code, read:

- `tests/test_refresh_manifest.py` — especially `test_the_wave_baseline_is_not_empty_despite_having_no_year_dimension`
- `tests/test_refresh_fixture.py` — the committed fixture's real dims
- `tests/refresh_builders.py` and `scripts/make_fixture.py`

**The artifact has three variable shapes, not two** (spec C§3.2):

| Variable | Dims | Baseline window |
|---|---|---|
| `salinity_psu`, `temp_c`, `din_umol_l`, `dip_umol_l`, `light_attenuation_k` | `year, month, latitude, longitude` | 2016–2025 |
| `significant_wave_m` | **`month, latitude, longitude`** — no `year` | **2023–2025** |
| `depth_mean_m`, `depth_min_m`, `valid` | `latitude, longitude` | `[]` |

**`significant_wave_m` is the trap.** It has no `year` dimension *and* a non-empty baseline, because it is a monthly p95 computed over 2023–2025 and then collapsed. Any rule of the form "no `year` dim → `[]`" is wrong, and `tests/test_refresh_manifest.py` contains a test named for exactly that mistake, whose docstring reads: *"the criterion is 'no baseline window', not 'no year dimension'. An implementer applying the dimensional test literally would write `[]` here."* `scripts/make_fixture.py:59` says the same in a comment and names the three static fields explicitly rather than deriving them.

**The coordinates are `latitude` and `longitude`, spelled out.** The spec's C§3.2 table abbreviates them to "lat, lon" in its dims column, but the line directly beneath it fixes the real names, and `tests/refresh_builders.py:56` and `tests/test_refresh_fixture.py` both use the long form. Code that reduces "over every non-spatial dim" while looking for `lat`/`lon` treats *every* dim as non-spatial, collapses `valid` to a 0-d scalar, and passes `check_declaration` — which compares variable **names** only and cannot see a shape. That failure is silent all the way to disk.

## Global Constraints

- **Nothing in `refresh/` may be imported by the model core** (C§5). `tests/test_refresh_isolation.py` already asserts this — it must stay green.
- **`addopts = "-m 'not engines and not e2e and not spatial'"`** is set in `pyproject.toml:124`. A bare `pytest tests/test_refresh_merge.py -v` therefore **deselects every test in that module** and reports success having run nothing. Every command in this plan that runs a `spatial`-marked module passes `-m spatial` explicitly. A DELETE proof run without it proves nothing.
- Modules importing `xarray` at **module scope** cannot be imported by an unmarked test, because `-m` deselects *after* collection. CI's `[app,dev]` job installs no spatial extra, so a collection-time `import xarray` turns it red. `tests/refresh_fakes.py` therefore imports xarray **inside** `build()`.
- Tests touching xarray carry `pytest.mark.spatial` **and** `pytest.importorskip`.
- Pydantic models use `model_config = ConfigDict(extra="forbid")`.
- `ARTIFACT_SCHEMA_VERSION = 1`; the nine artifact variables are `seagarden_dst.refresh.variables.ARTIFACT_VARIABLES`.
- **ruff**: `line-length = 100`, `target-version = "py311"`. Import `Sequence` from `collections.abc`, never `typing` (UP035). The repo is currently ruff-clean and must stay so.
- **Test discrimination standard (in force for every task):**
  - Every negative test asserts `match=` on a fragment **unique to the rule under test**.
  - **DELETE proof:** for each guard, neutralise it, show the test goes red *for the right reason*, restore, show green. Record actual pytest output, never the word "verified".
  - **SWAP proof:** wherever two sibling messages share a matched substring, swap the bodies — *both* tests must go red.
  - Commit the implementation **before** running mutation proofs.
- Never `git add` anything under `.superpowers/`.
- No network call and no credential read in any test.

## Rulings

These resolve gaps between C§5 (written before C-a shipped) and the code that actually exists. Binding on implementers.

**R1 — `Layer.build` takes the year range.** C§5 shows `build(self, grid, workdir)`, but clause 1 requires a refresh "for a named year range". The protocol reads `build(self, grid: GridSpec, years: YearRange, workdir: Path) -> xr.Dataset`. A layer may legitimately **ignore** `years`: the wave layer's window is fixed at 2023–2025 by C§3.2 regardless of what is asked. That is not a contradiction — `years` is the requested span, and each layer reports what it actually used via R2.

**R2 — baselines are DECLARED by the layer and CROSS-CHECKED against the built data.** *(Rewritten: the first draft derived them from the data alone, which is the dimensional test C§4.4 forbids by name.)* The protocol gains a fifth member, `baseline_years() -> dict[str, list[int]]`. The driver still iterates `dataset.data_vars`, so `set(baselines) == set(merged.data_vars)` holds, but it *resolves* each entry: where the data carries a `year` coord, the declaration must agree with it or the refresh fails; where it does not, the declaration stands. An unstated window is an error, never an empty one. This keeps the anti-drift property — a declaration disagreeing with the artifact is caught — while being able to express `significant_wave_m: [2023, 2024, 2025]` on a variable with no `year` dim. *Cost if wrong:* a fifth protocol member the five C-c layers must each implement.

**R3 — the driver does NOT call `check_declaration`.** `write_pair` already calls it (`src/seagarden_dst/refresh/writer.py:57`). The driver populates `Manifest.variables` from `ARTIFACT_VARIABLES` and lets the writer enforce.

> **Ordering note.** Because R2 keys `baselines` off `dataset.data_vars`, the manifest's `_check_baseline_keys_are_exactly_the_artifact_variables` compares that key set against `variables` and fires at `Manifest(...)` construction — **before** `write_pair`. So `check_declaration` is unreachable-as-failing from `run_refresh`. It remains package D's check on the *read* side. Do not write a driver test expecting its message.
>
> `check_declaration` compares **names only**. It cannot see a wrong shape, which is why R7 exists.

**R4 — shared definitions live in `refresh/`, imported by the test builders.** `COVERAGE_LAYERS` and the three `Derivation` records were each defined twice — once in the driver and once in `tests/refresh_builders.py`. One definition, imported by both, or `valid`'s attestation drifts from what the driver computed. *Cost if wrong:* the manifest attests an intersection that was never taken.

**R5 — a layer covers a cell only if every variable it contributes is non-null there, across every non-spatial dim.** Spatial dims are `("latitude", "longitude")`. `.all()` rather than `.any()`: a cell wet in some months and absent in others is not coverage a farm verdict should rest on. Verified against all three real shapes — 4-D, 3-D and static all reduce to a 2-D `(latitude, longitude)` mask.

**R6 — fakes live in `tests/`, never in `refresh/`**, and import xarray lazily so unmarked test modules can import them.

**R7 — the driver validates shapes, not just names.** C§5 says "validate the result against the expected variable set **and shapes**". `check_declaration` covers the set; nothing covered shapes, and the `lat`/`lon` defect proved the gap is reachable. The driver asserts each variable's dims against C§3.2's table before writing. *Cost if wrong:* a real layer emitting a transposed or mis-named grid ships silently.

---

## File Structure

| File | Responsibility |
|---|---|
| `src/seagarden_dst/refresh/layer.py` (create) | `YearRange`, `ProbeResult`, the `Layer` Protocol, `LAYER_NAMES`, `COVERAGE_LAYERS`. No xarray at runtime. |
| `src/seagarden_dst/refresh/shapes.py` (create) | `EXPECTED_DIMS`, `SPATIAL_DIMS`, `check_shapes`. The C§3.2 table, once. |
| `src/seagarden_dst/refresh/registry.py` (create) | `REGISTRY`. The source list, in one place. |
| `src/seagarden_dst/refresh/merge.py` (create) | `compute_valid`, `merge_layers`. |
| `src/seagarden_dst/refresh/driver.py` (create) | `resolve_baselines`, `derivations`, `run_refresh`. |
| `src/seagarden_dst/refresh/deposit.py` (create) | `Depositor` protocol, `record_doi`. |
| `scripts/refresh_layers.py` (create) | Thin CLI: year range, `--probe`, `--target`. |
| `.github/workflows/source-probe.yml` (create) | Monthly + `workflow_dispatch`, separate from `ci.yml`. |
| `tests/refresh_fakes.py` (create) | `FakeLayer`. Test-only, lazy xarray import. |
| `tests/refresh_builders.py` (modify) | Import `COVERAGE_LAYERS` and `derivations()` instead of redefining them (R4). |
| `tests/test_refresh_layer.py`, `test_refresh_shapes.py`, `test_refresh_merge.py`, `test_refresh_driver.py`, `test_refresh_cli.py`, `test_refresh_deposit.py` (create) | One test module per unit. |

---

### Task 1: The layer protocol, the shape table, the registry, and the fakes

**Files:**
- Create: `src/seagarden_dst/refresh/layer.py`, `shapes.py`, `registry.py`, `tests/refresh_fakes.py`
- Modify: `tests/refresh_builders.py:25` (replace `_COVERAGE_LAYERS` with an import — R4)
- Test: `tests/test_refresh_layer.py`, `tests/test_refresh_shapes.py`

**Interfaces:**
- Consumes: `seagarden_dst.artifact.grid.GridSpec`, `seagarden_dst.artifact.manifest.{LayerProvenance, Archive}`
- Produces:
  - `YearRange(start: int, end: int)` with `.years() -> list[int]`; rejects `end < start`
  - `ProbeResult(name: str, reachable: bool, detail: str)`
  - `Layer` — `@runtime_checkable` Protocol with **five** members: `name: str`, `probe()`, `build(grid, years, workdir)`, `provenance()`, `baseline_years() -> dict[str, list[int]]`
  - `LAYER_NAMES: tuple[str, ...]` (five), `COVERAGE_LAYERS: tuple[str, ...]` (four)
  - `SPATIAL_DIMS: tuple[str, str]`, `EXPECTED_DIMS: dict[str, tuple[str, ...]]`, `check_shapes(dataset) -> None`
  - `REGISTRY: dict[str, Layer]` (empty in C-b — C-c fills it)
  - `tests/refresh_fakes.py`: `FakeLayer(name, variables, *, claims=None, shape="yearly", window=None, data=None, fail_on_build=False, reachable=True, dataset_id=None)`; `LayerBuildFailed`

**Why `claims` is separate from `variables`:** a layer's `LayerProvenance.variables` is what it *claims*; the dataset it builds is what it *produces*. They differ deliberately. `tests/refresh_builders.py:24` has `copernicus_bgc` claiming only `["dip_umol_l"]` while `din_umol_l` is claimed by a `Derivation`, and `copernicus_bgc_light` claims `[]` while producing `light_attenuation_k`. Conflating them double-claims `din_umol_l` and trips C§4.4's claimed-exactly-once validator — the rule working, not a bug to route around.

- [ ] **Step 1: Write the failing tests for `YearRange`, `ProbeResult` and the layer name tuples**

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


def test_probe_result_carries_its_detail():
    result = ProbeResult(name="copernicus_phy", reachable=True, detail="catalogue responded")
    assert result.detail == "catalogue responded"
    assert (result.name, result.reachable) == ("copernicus_phy", True)


def test_the_five_layer_names_are_exactly_the_spec_s_five():
    assert LAYER_NAMES == (
        "copernicus_phy",
        "copernicus_bgc",
        "copernicus_bgc_light",
        "copernicus_wav",
        "emodnet_bathy",
    )


def test_coverage_layers_are_the_four_that_contribute_independent_coverage():
    # Pinned exactly, not merely as a subset: `valid`'s Derivation attests THIS list,
    # so a change here silently changes what the manifest claims (R4).
    assert COVERAGE_LAYERS == (
        "copernicus_phy",
        "copernicus_bgc",
        "copernicus_wav",
        "emodnet_bathy",
    )
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

    Five members, not C§5's four. `build` takes the year range (R1) because a refresh
    is named by its span, and `baseline_years` exists (R2) because the window a
    variable rests on cannot be read off its dimensions: `significant_wave_m` has no
    `year` dim and a 2023-2025 window, which is the case C§4.4 calls out by name.

    A layer may ignore the `years` it is given — the wave window is fixed by C§3.2 —
    but it must then say so through `baseline_years`.
    """

    name: str

    def probe(self) -> ProbeResult: ...

    def build(self, grid: GridSpec, years: YearRange, workdir: Path) -> xr.Dataset: ...

    def provenance(self) -> LayerProvenance: ...

    def baseline_years(self) -> dict[str, list[int]]: ...


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
# the BGC footprint, so it adds no independent constraint (R4).
COVERAGE_LAYERS: tuple[str, ...] = (
    "copernicus_phy",
    "copernicus_bgc",
    "copernicus_wav",
    "emodnet_bathy",
)
```

- [ ] **Step 4: Write the failing test for the shape table**

```python
# tests/test_refresh_shapes.py
import pytest

pytest.importorskip("xarray")
import numpy as np  # noqa: E402
import xarray as xr  # noqa: E402

from seagarden_dst.refresh.shapes import EXPECTED_DIMS, SPATIAL_DIMS, check_shapes  # noqa: E402

pytestmark = pytest.mark.spatial


def test_the_spatial_dims_are_spelled_out():
    # The spec's C§3.2 dims column abbreviates to "lat, lon"; the line beneath it and
    # the committed fixture both use the long form. Code that reduces over every
    # NON-spatial dim while looking for the short form collapses `valid` to a scalar.
    assert SPATIAL_DIMS == ("latitude", "longitude")


def test_the_three_shapes_are_all_represented():
    assert EXPECTED_DIMS["temp_c"] == ("year", "month", "latitude", "longitude")
    assert EXPECTED_DIMS["significant_wave_m"] == ("month", "latitude", "longitude")
    assert EXPECTED_DIMS["depth_mean_m"] == ("latitude", "longitude")
    assert EXPECTED_DIMS["valid"] == ("latitude", "longitude")


def _ds(name, dims, sizes):
    return xr.Dataset({name: (dims, np.ones(sizes, dtype="float32"))})


def test_check_shapes_accepts_the_declared_shape():
    check_shapes(_ds("depth_mean_m", ("latitude", "longitude"), (2, 2)))


def test_check_shapes_rejects_a_short_form_coordinate_name():
    # The exact defect this function exists to catch.
    with pytest.raises(ValueError, match="expected dims"):
        check_shapes(_ds("depth_mean_m", ("lat", "lon"), (2, 2)))


def test_check_shapes_rejects_a_transposed_variable():
    with pytest.raises(ValueError, match="expected dims"):
        check_shapes(_ds("depth_mean_m", ("longitude", "latitude"), (2, 2)))


def test_check_shapes_rejects_a_variable_it_has_never_heard_of():
    with pytest.raises(ValueError, match="no declared shape"):
        check_shapes(_ds("surface_par", ("latitude", "longitude"), (2, 2)))


def test_check_shapes_rejects_a_wave_field_that_grew_a_year_dimension():
    # The wave layer collapses year into a 2023-2025 p95. A year dim here means the
    # collapse did not happen, and its baseline would then be read off the data.
    with pytest.raises(ValueError, match="expected dims"):
        check_shapes(
            _ds("significant_wave_m", ("year", "month", "latitude", "longitude"), (2, 12, 2, 2))
        )
```

- [ ] **Step 5: Write `shapes.py`**

```python
"""The C§3.2 variable table, in one place, and the check that enforces it.

`artifact.pair.check_declaration` compares variable NAMES and cannot see a shape. A
layer that emitted `("lat", "lon")` instead of `("latitude", "longitude")` would pass
every name check, collapse the `valid` intersection to a 0-d scalar, and write that to
disk without a word. C§5 asks the driver to validate "the expected variable set AND
shapes"; this module is the second half (R7).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    import xarray as xr

# Spelled out. The spec's C§3.2 dims column abbreviates; its coordinates line does not,
# and neither do tests/refresh_builders.py or the committed fixture.
SPATIAL_DIMS: tuple[str, str] = ("latitude", "longitude")

_YEARLY = ("year", "month", "latitude", "longitude")
_MONTHLY = ("month", "latitude", "longitude")
_STATIC = ("latitude", "longitude")

# Three shapes, not two (C§3.2). `significant_wave_m` is monthly-only because it is a
# p95 collapsed over its 2023-2025 window, and `valid` is static because it is a mask.
EXPECTED_DIMS: dict[str, tuple[str, ...]] = {
    "salinity_psu": _YEARLY,
    "temp_c": _YEARLY,
    "din_umol_l": _YEARLY,
    "dip_umol_l": _YEARLY,
    "light_attenuation_k": _YEARLY,
    "significant_wave_m": _MONTHLY,
    "depth_mean_m": _STATIC,
    "depth_min_m": _STATIC,
    "valid": _STATIC,
}


def check_shapes(dataset: xr.Dataset) -> None:
    """Every variable carries the dims C§3.2 gives it, in that order."""
    for name, variable in dataset.data_vars.items():
        expected = EXPECTED_DIMS.get(str(name))
        if expected is None:
            raise ValueError(
                f"variable '{name}' has no declared shape in C§3.2, so nothing here "
                "can say whether what was built is right; add it to EXPECTED_DIMS or "
                "stop building it"
            )
        if tuple(variable.dims) != expected:
            raise ValueError(
                f"variable '{name}' has dims {tuple(variable.dims)}, expected dims "
                f"{expected}. check_declaration compares names only, so a wrong shape "
                "reaches disk silently unless it is caught here"
            )
```

- [ ] **Step 6: Run both test modules**

```bash
micromamba run -n shiny python -m pytest tests/test_refresh_layer.py -v
micromamba run -n shiny python -m pytest tests/test_refresh_shapes.py -v -m spatial
```
Expected: 6 passed, then 7 passed. **The `-m spatial` is mandatory** — `addopts` deselects the marker by default, so without it pytest reports success having run nothing.

- [ ] **Step 7: Write `registry.py`**

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
#
# An EMPTY registry is not a valid state for the probe job: see the guard in
# scripts/refresh_layers.py, which refuses rather than reporting nothing green.
REGISTRY: dict[str, Layer] = {}
```

- [ ] **Step 8: Write `tests/refresh_fakes.py`**

```python
"""Synthetic `Layer` implementations for driver tests (R6).

These live in `tests/` and never in `refresh/`: a fake in production code is a test
seam nobody can see. They exist so every driver clause — merge, `valid`, baselines,
shapes, fail-on-any-layer — is provable with no network and no credential.

**xarray is imported inside `build`, not at module scope.** `-m` deselects after
collection, so a module-scope import here would break collection of the unmarked CLI
tests that import `FakeLayer` for its `probe()`, and turn CI's `[app,dev]` job red.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from seagarden_dst.artifact.grid import GridSpec
from seagarden_dst.artifact.manifest import Archive, LayerProvenance
from seagarden_dst.refresh.layer import ProbeResult, YearRange

if TYPE_CHECKING:  # pragma: no cover - typing only
    import xarray as xr


class LayerBuildFailed(RuntimeError):
    """Raised by a `FakeLayer` told to fail, so the driver's C§6.1 row 1 has a case."""


class FakeLayer:
    """A `Layer` that returns data handed to it instead of fetching any.

    `shape` picks one of C§3.2's three:
      "yearly"  -> (year, month, latitude, longitude)  the five reanalysis fields
      "monthly" -> (month, latitude, longitude)        significant_wave_m
      "static"  -> (latitude, longitude)               the bathymetry fields
    """

    def __init__(
        self,
        name: str,
        variables: list[str],
        *,
        claims: list[str] | None = None,
        shape: str = "yearly",
        window: list[int] | None = None,
        data: dict[str, tuple] | None = None,
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
        self._shape = shape
        self._window = window
        self._data = data
        self._fail_on_build = fail_on_build
        self._reachable = reachable
        self._dataset_id = dataset_id or f"{name}-dataset"
        self._last_years: list[int] = []

    def probe(self) -> ProbeResult:
        return ProbeResult(
            name=self.name,
            reachable=self._reachable,
            detail="catalogue responded" if self._reachable else "catalogue 404",
        )

    def build(self, grid: GridSpec, years: YearRange, workdir: Path) -> xr.Dataset:
        import numpy as np
        import xarray as xr

        if self._fail_on_build:
            raise LayerBuildFailed(f"layer {self.name} could not build")
        self._last_years = years.years()
        if self._data is not None:
            return xr.Dataset(self._data)

        lat, lon = grid.lats(), grid.lons()
        months = list(range(1, 13))
        if self._shape == "static":
            dims = ("latitude", "longitude")
            sizes = (grid.n_lat, grid.n_lon)
            coords = {"latitude": lat, "longitude": lon}
        elif self._shape == "monthly":
            dims = ("month", "latitude", "longitude")
            sizes = (12, grid.n_lat, grid.n_lon)
            coords = {"month": months, "latitude": lat, "longitude": lon}
        else:
            dims = ("year", "month", "latitude", "longitude")
            sizes = (len(self._last_years), 12, grid.n_lat, grid.n_lon)
            coords = {
                "year": self._last_years,
                "month": months,
                "latitude": lat,
                "longitude": lon,
            }
        return xr.Dataset(
            {name: (dims, np.ones(sizes, dtype="float32")) for name in self._variables},
            coords=coords,
        )

    def baseline_years(self) -> dict[str, list[int]]:
        """What window each produced variable rests on (R2).

        Static fields get `[]`; a fake with an explicit `window` reports it whatever
        was asked for — which is how the wave layer's fixed 2023-2025 is modelled.

        **Order-dependent, unlike a real layer.** Without a `window`, this reports
        `self._last_years`, which only `build()` sets. `run_refresh` calls `_build_all`
        before `_declared_windows`, so it is populated in time — but do not reorder
        those two, or every yearly variable declares an empty window and then
        "disagrees with the data". A real layer knows its window without building.
        """
        if self._window is not None:
            return {name: list(self._window) for name in self._variables}
        if self._shape == "static":
            return {name: [] for name in self._variables}
        return {name: list(self._last_years) for name in self._variables}

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

- [ ] **Step 9: Prove `FakeLayer` satisfies the Protocol, and that importing it needs no xarray**

Append to `tests/test_refresh_layer.py` (this module is **unmarked** — that is the point):

```python
def test_fake_layer_satisfies_the_runtime_checkable_protocol():
    from refresh_fakes import FakeLayer

    from seagarden_dst.refresh.layer import Layer

    assert isinstance(FakeLayer("copernicus_phy", ["temp_c"]), Layer)


def test_importing_the_fakes_does_not_import_xarray():
    # A module-scope `import xarray` in refresh_fakes would break collection of every
    # unmarked module that imports FakeLayer, turning CI's [app,dev] job red. `-m`
    # deselects AFTER collection, so a marker cannot save it.
    import pathlib
    import subprocess
    import sys

    root = pathlib.Path(__file__).resolve().parent.parent
    env = {
        **__import__("os").environ,
        "PYTHONPATH": f"{root / 'src'}{__import__('os').pathsep}{root / 'tests'}",
    }
    result = subprocess.run(
        [sys.executable, "-c", "import refresh_fakes, sys; print('xarray' in sys.modules)"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.stdout.strip() == "False", result.stderr
```

Run: `micromamba run -n shiny python -m pytest tests/test_refresh_layer.py -v`
Expected: 8 passed

- [ ] **Step 10: Remove the duplicated coverage tuple (R4)**

In `tests/refresh_builders.py`, delete the `_COVERAGE_LAYERS = (...)` assignment at line 25 and import the single definition:

```python
from seagarden_dst.refresh.layer import COVERAGE_LAYERS as _COVERAGE_LAYERS
```

Run the whole suite both ways:
```bash
micromamba run -n shiny python -m pytest -q
micromamba run -n shiny python -m pytest -q -m spatial
micromamba run -n shiny ruff check .
```
Expected: **unchanged from the Step 9 run** — the 198 passed / 12 deselected baseline plus this task's 8 unmarked layer tests and 7 spatial shape tests, so 206 passed / 19 deselected, then 19 passed. Ruff clean. What this step proves is that swapping the tuple for an import changed *nothing*; phrase it that way rather than chasing an absolute number, so adding a test to Task 1 later does not silently invalidate it. If any test changes behaviour, the two tuples had already drifted — report it, do not paper over it.

- [ ] **Step 11: Commit**

```bash
git add src/seagarden_dst/refresh/layer.py src/seagarden_dst/refresh/shapes.py src/seagarden_dst/refresh/registry.py tests/refresh_fakes.py tests/test_refresh_layer.py tests/test_refresh_shapes.py tests/refresh_builders.py
git commit -m "feat(refresh): add the layer protocol, the C3.2 shape table and test fakes"
```

- [ ] **Step 12: DELETE proof — the `YearRange` guard**

Comment out the body of `_check_end_does_not_precede_start` (leave `return self`). Run `micromamba run -n shiny python -m pytest tests/test_refresh_layer.py -v`. `test_year_range_rejects_an_end_before_its_start` must fail with `DID NOT RAISE`. Restore, re-run green. Paste both outputs into the report.

- [ ] **Step 13: DELETE proof and SWAP proof — the shape check**

Neutralise the `tuple(variable.dims) != expected` branch in `check_shapes` (make it `if False:`). Run with `-m spatial`. Three tests must go red: the short-form, the transposed, and the wave-grew-a-year-dim cases. Restore, re-run green.

Then the **SWAP proof**: `check_shapes` raises two messages that both name a variable. Swap the bodies of the `expected is None` and the dims-mismatch branches. `test_check_shapes_rejects_a_variable_it_has_never_heard_of` and the three dims tests must all go red. Restore, re-run green. Record every output.

---

### Task 2: The `valid` intersection and the merge

**Files:**
- Create: `src/seagarden_dst/refresh/merge.py`
- Test: `tests/test_refresh_merge.py`

**Interfaces:**
- Consumes: `COVERAGE_LAYERS` (Task 1), `SPATIAL_DIMS` (Task 1)
- Produces:
  - `compute_valid(per_layer: dict[str, xr.Dataset]) -> xr.DataArray` — a 2-D `(latitude, longitude)` bool array named `valid`
  - `merge_layers(per_layer: dict[str, xr.Dataset]) -> xr.Dataset` — the merged dataset carrying `valid`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_refresh_merge.py
import pytest

pytest.importorskip("xarray")
import numpy as np  # noqa: E402
import xarray as xr  # noqa: E402

from seagarden_dst.refresh.merge import compute_valid, merge_layers  # noqa: E402

pytestmark = pytest.mark.spatial

_LAT = [55.0, 55.5]
_LON = [20.0, 20.5]
_COORDS = {"latitude": _LAT, "longitude": _LON}
_MONTHS = list(range(1, 13))


def _static(name, values):
    return xr.Dataset(
        {name: (("latitude", "longitude"), np.array(values, dtype="float32"))}, coords=_COORDS
    )


def test_valid_is_the_intersection_of_two_disagreeing_masks():
    # C§10 clause 11. Copernicus says the top row is wet; EMODnet says the left
    # column is. They agree only on the top-left cell — the coastline case C§3.5
    # exists for.
    phy = _static("temp_c", [[1.0, 2.0], [np.nan, np.nan]])
    bathy = _static("depth_mean_m", [[3.0, np.nan], [4.0, np.nan]])
    valid = compute_valid({"copernicus_phy": phy, "emodnet_bathy": bathy})
    assert valid.dims == ("latitude", "longitude")
    np.testing.assert_array_equal(valid.values, np.array([[True, False], [False, False]]))


def test_coverage_reduces_the_real_four_dimensional_shape_to_two():
    # The defect a `lat`/`lon` spatial-dim tuple produces is a 0-d scalar, silently.
    a = np.ones((2, 12, 2, 2), dtype="float32")
    # ONE cell in ONE month of ONE year, not the whole non-spatial slice. A whole-slice
    # NaN makes `.all()` and `.any()` return the same mask, so the R5 mutation in Step 6
    # could not redden this test — measured, not assumed.
    a[0, 3, 0, 1] = np.nan
    phy = xr.Dataset(
        {"temp_c": (("year", "month", "latitude", "longitude"), a)},
        coords={"year": [2024, 2025], "month": _MONTHS, **_COORDS},
    )
    valid = compute_valid({"copernicus_phy": phy})
    assert valid.dims == ("latitude", "longitude")
    assert valid.shape == (2, 2)
    np.testing.assert_array_equal(valid.values, np.array([[True, False], [True, True]]))


def test_coverage_reduces_the_month_only_wave_shape_to_two():
    a = np.ones((12, 2, 2), dtype="float32")
    a[3, 1, 1] = np.nan  # absent in one month only
    wav = xr.Dataset(
        {"significant_wave_m": (("month", "latitude", "longitude"), a)},
        coords={"month": _MONTHS, **_COORDS},
    )
    valid = compute_valid({"copernicus_wav": wav})
    assert valid.dims == ("latitude", "longitude")
    # R5: `.all()`, not `.any()` — absent in one month is not coverage.
    np.testing.assert_array_equal(valid.values, np.array([[True, True], [True, False]]))


def test_the_light_layer_does_not_narrow_the_intersection():
    # `copernicus_bgc_light` is outside COVERAGE_LAYERS (R4): an all-NaN light layer
    # must leave `valid` untouched, or the manifest's four-layer attestation would
    # describe a five-layer intersection.
    phy = _static("temp_c", [[1.0, 1.0], [1.0, 1.0]])
    light = _static("light_attenuation_k", [[np.nan, np.nan], [np.nan, np.nan]])
    valid = compute_valid({"copernicus_phy": phy, "copernicus_bgc_light": light})
    assert valid.values.all()


def test_merge_carries_valid_with_the_right_values_and_dtype():
    phy = _static("temp_c", [[1.0, 2.0], [3.0, np.nan]])
    bathy = _static("depth_mean_m", [[5.0, 6.0], [7.0, 8.0]])
    merged = merge_layers({"copernicus_phy": phy, "emodnet_bathy": bathy})
    assert set(merged.data_vars) == {"temp_c", "depth_mean_m", "valid"}
    assert merged["valid"].dtype == np.dtype("bool")
    # Values, not just presence: otherwise merge could attach any mask and pass.
    np.testing.assert_array_equal(
        merged["valid"].values, np.array([[True, True], [True, False]])
    )


def test_merge_preserves_variable_attributes():
    # C§3.2 records CRS as a variable attribute. combine_attrs="drop" would strip it
    # and nothing downstream would notice until package D read the artifact.
    phy = _static("temp_c", [[1.0, 1.0], [1.0, 1.0]])
    phy["temp_c"].attrs["crs"] = "EPSG:4326"
    merged = merge_layers({"copernicus_phy": phy})
    assert merged["temp_c"].attrs["crs"] == "EPSG:4326"


def test_merge_tolerates_layers_with_different_dataset_attributes():
    # Real layers carry different DATASET-level attrs — EMODnet and CMEMS do not share
    # a `source`. combine_attrs="no_conflicts" raises MergeError on exactly that, which
    # would have made the first real refresh fail at the merge. Measured against this
    # environment's xarray, not assumed.
    phy = _static("temp_c", [[1.0, 1.0], [1.0, 1.0]])
    phy.attrs["source"] = "CMEMS"
    bathy = _static("depth_mean_m", [[1.0, 1.0], [1.0, 1.0]])
    bathy.attrs["source"] = "EMODnet"
    merged = merge_layers({"copernicus_phy": phy, "emodnet_bathy": bathy})
    assert set(merged.data_vars) == {"temp_c", "depth_mean_m", "valid"}


def test_compute_valid_refuses_when_no_coverage_layer_is_present():
    light = _static("light_attenuation_k", [[1.0, 1.0], [1.0, 1.0]])
    with pytest.raises(ValueError, match="no coverage layer was built"):
        compute_valid({"copernicus_bgc_light": light})


def test_compute_valid_refuses_a_layer_that_built_nothing():
    empty = xr.Dataset(coords=_COORDS)
    with pytest.raises(ValueError, match="built no variables"):
        compute_valid({"copernicus_phy": empty})


def test_compute_valid_refuses_a_variable_missing_a_spatial_dim():
    # Renaming SPATIAL_DIMS alone is not enough: a C-c layer emitting the short form
    # must be refused, not silently reduced to a scalar.
    bad = xr.Dataset(
        {"temp_c": (("lat", "lon"), np.ones((2, 2), dtype="float32"))},
        coords={"lat": _LAT, "lon": _LON},
    )
    with pytest.raises(ValueError, match="lacks the spatial dims"):
        compute_valid({"copernicus_phy": bad})
```

- [ ] **Step 2: Run to verify it fails**

Run: `micromamba run -n shiny python -m pytest tests/test_refresh_merge.py -v -m spatial`
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
from seagarden_dst.refresh.shapes import SPATIAL_DIMS

if TYPE_CHECKING:  # pragma: no cover - typing only
    import xarray as xr


def _coverage_of(dataset: xr.Dataset) -> xr.DataArray:
    """A 2-D mask: cells where every variable is present across every other dim.

    `.all()` rather than `.any()` (R5) — a cell wet in some months and absent in
    others is not coverage a farm verdict should rest on. Failing small fails safe.

    The three real shapes all reduce to (latitude, longitude): the 4-D reanalysis
    fields, the month-only wave field, and the static bathymetry.
    """
    if not dataset.data_vars:
        raise ValueError(
            "a layer built no variables, so its coverage is undefined; an empty "
            "dataset here is a bug in the layer, not an empty intersection"
        )
    masks = []
    for name, variable in dataset.data_vars.items():
        missing = [d for d in SPATIAL_DIMS if d not in variable.dims]
        if missing:
            raise ValueError(
                f"variable '{name}' lacks the spatial dims {missing}: it has "
                f"{list(variable.dims)}. Coverage reduces over every NON-spatial dim, "
                "so a mis-named coordinate would collapse `valid` to a scalar that "
                "check_declaration cannot see, because it compares names only"
            )
        masks.append(
            variable.notnull().all(dim=[d for d in variable.dims if d not in SPATIAL_DIMS])
        )
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
    """Merge every layer onto one dataset and attach `valid`.

    `combine_attrs="drop_conflicts"`, deliberately, and neither of the two obvious
    alternatives. `"drop"` would strip the CRS that C§3.2 records as a VARIABLE
    attribute, surfacing only when package D read the artifact and found no CRS to
    trust. `"no_conflicts"` raises `MergeError` the moment two layers carry different
    DATASET-level attrs — and EMODnet and CMEMS do not share a `source`, so the first
    real refresh would have died at the merge. `drop_conflicts` drops the conflicting
    dataset-level attrs and leaves every variable's own attrs intact, which is the
    behaviour both requirements point at.
    """
    import xarray as xr

    merged = xr.merge(list(per_layer.values()), join="exact", combine_attrs="drop_conflicts")
    return merged.assign(valid=compute_valid(per_layer))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `micromamba run -n shiny python -m pytest tests/test_refresh_merge.py -v -m spatial`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add src/seagarden_dst/refresh/merge.py tests/test_refresh_merge.py
git commit -m "feat(refresh): compute the valid mask as a layer-coverage intersection"
```

- [ ] **Step 6: DELETE proof — the `.all()` reduction**

Change `.all(` to `.any(` in `_coverage_of`. Run with `-m spatial`. `test_coverage_reduces_the_real_four_dimensional_shape_to_two` and `test_coverage_reduces_the_month_only_wave_shape_to_two` must both go red on the array comparison. Restore, re-run green.

- [ ] **Step 7: DELETE proof — the `COVERAGE_LAYERS` filter**

Replace `contributing = [name for name in COVERAGE_LAYERS if name in per_layer]` with `contributing = list(per_layer)`. `test_the_light_layer_does_not_narrow_the_intersection` and `test_compute_valid_refuses_when_no_coverage_layer_is_present` must both go red. Restore, re-run green. This is the mutation proving R4 is load-bearing.

- [ ] **Step 8: DELETE proof and SWAP proof — the spatial-dim guard**

Delete the `missing` check. `test_compute_valid_refuses_a_variable_missing_a_spatial_dim` must go red — and note in the report whether it fails with `DID NOT RAISE` or with a *different* error, because a bare reduction over all dims yields a scalar and the later `&` may still succeed. That distinction is the whole point of the guard.

Then the **SWAP proof**: `_coverage_of` raises two messages, both describing a layer's data. Swap the bodies of the empty-dataset branch and the missing-spatial-dims branch. `test_compute_valid_refuses_a_layer_that_built_nothing` and `test_compute_valid_refuses_a_variable_missing_a_spatial_dim` must both go red. Restore, re-run green. Record every output.

- [ ] **Step 9: DELETE proof — the attribute policy, both directions**

This one guard has to satisfy two opposing requirements, so prove both.

Change `combine_attrs="drop_conflicts"` to `"drop"`: `test_merge_preserves_variable_attributes` must go red with a `KeyError`. Restore.

Then change it to `"no_conflicts"`: `test_merge_tolerates_layers_with_different_dataset_attributes` must go red with `MergeError`, while `test_merge_preserves_variable_attributes` stays **green**. That asymmetry is the point — it shows the two tests pin opposite edges of the same decision, and that `drop_conflicts` is the only setting between them. Restore, re-run green. Record all three outputs.

---

### Task 3: The driver

**Files:**
- Create: `src/seagarden_dst/refresh/driver.py`
- Modify: `tests/conftest.py` (two fixtures), `tests/refresh_builders.py` (import `derivations()` — R4)
- Test: `tests/test_refresh_driver.py`

**Interfaces:**
- Consumes: `merge_layers` (Task 2), `check_shapes` (Task 1), `Layer`/`YearRange`/`COVERAGE_LAYERS` (Task 1), `ARTIFACT_VARIABLES`, `write_pair`, `Manifest`/`Derivation`/`AbsentField`/`ARTIFACT_SCHEMA_VERSION`, `GridSpec`
- Produces:
  - `resolve_baselines(dataset: xr.Dataset, declared: dict[str, list[int]]) -> dict[str, list[int]]` (R2)
  - `derivations() -> list[Derivation]` — the canonical three, imported by the test builders (R4)
  - `run_refresh(layers, grid, years, target_dir, workdir, *, synthetic=False) -> tuple[Path, Path]`
  - `RefreshFailed(RuntimeError)`

- [ ] **Step 1: Add the fixtures to `tests/conftest.py`**

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
    """Five fakes between them producing `ARTIFACT_VARIABLES` minus `valid`.

    `valid` is absent on purpose: the driver computes it, so a fake supplying it
    would hide a driver that had stopped.

    The `claims` arguments mirror tests/refresh_builders.py exactly — `din_umol_l`
    and `light_attenuation_k` are claimed by Derivations, not by the layers producing
    them, so claiming them here too trips C§4.4's claimed-exactly-once validator.

    The `shape`/`window` arguments mirror C§3.2. `copernicus_wav` is the case that
    matters: month-only dims AND a fixed 2023-2025 window, whatever years are asked
    for. A fake that let it grow a `year` dim would hide the exact defect a
    dimensional baseline rule produces.
    """
    from refresh_fakes import FakeLayer

    return [
        FakeLayer("copernicus_phy", ["salinity_psu", "temp_c"]),
        FakeLayer("copernicus_bgc", ["din_umol_l", "dip_umol_l"], claims=["dip_umol_l"]),
        FakeLayer("copernicus_bgc_light", ["light_attenuation_k"], claims=[]),
        FakeLayer(
            "copernicus_wav",
            ["significant_wave_m"],
            shape="monthly",
            window=[2023, 2024, 2025],
        ),
        FakeLayer("emodnet_bathy", ["depth_mean_m", "depth_min_m"], shape="static"),
    ]
```

Verify `small_grid`'s numbers satisfy `GridSpec`'s validators and that `lats()`/`lons()` return arrays of length 3 — read `src/seagarden_dst/artifact/grid.py` and compute it. If they do not, adjust the bounds; never weaken the validator.

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_refresh_driver.py
import pytest
from pydantic import ValidationError

pytest.importorskip("xarray")
import numpy as np  # noqa: E402
import xarray as xr  # noqa: E402
from refresh_fakes import FakeLayer  # noqa: E402

from seagarden_dst.artifact.pair import load_pair  # noqa: E402
from seagarden_dst.refresh.driver import (  # noqa: E402
    RefreshFailed,
    _declared_windows,
    check_grid,
    resolve_baselines,
    run_refresh,
)
from seagarden_dst.refresh.layer import YearRange  # noqa: E402

pytestmark = pytest.mark.spatial


def _yearly(name, years):
    return xr.Dataset(
        {name: (("year", "latitude"), np.ones((len(years), 2), dtype="float32"))},
        coords={"year": years, "latitude": [55.0, 55.5]},
    )


def test_resolve_baselines_takes_years_off_the_data_when_there_is_a_year_dim():
    ds = _yearly("temp_c", [2024, 2025])
    assert resolve_baselines(ds, {"temp_c": [2024, 2025]}) == {"temp_c": [2024, 2025]}


def test_a_declared_window_survives_a_variable_with_no_year_dimension():
    # THE trap (C§4.4, tests/test_refresh_manifest.py). `significant_wave_m` is a
    # monthly p95 over 2023-2025: no year dim, non-empty window. A dimensional rule
    # writes [] here and the manifest then contradicts the spec and the fixture.
    ds = xr.Dataset(
        {"significant_wave_m": (("month", "latitude"), np.ones((12, 2), dtype="float32"))},
        coords={"month": list(range(1, 13)), "latitude": [55.0, 55.5]},
    )
    resolved = resolve_baselines(ds, {"significant_wave_m": [2023, 2024, 2025]})
    assert resolved["significant_wave_m"] == [2023, 2024, 2025]


def test_a_static_field_keeps_its_empty_window():
    ds = xr.Dataset(
        {"depth_min_m": (("latitude",), np.ones(2, dtype="float32"))},
        coords={"latitude": [55.0, 55.5]},
    )
    resolved = resolve_baselines(ds, {"depth_min_m": []})
    assert "depth_min_m" in resolved  # present, not omitted — C§4.4 tells them apart
    assert resolved["depth_min_m"] == []


def test_a_declaration_disagreeing_with_the_data_is_refused():
    ds = _yearly("temp_c", [2024, 2025])
    with pytest.raises(RefreshFailed, match="declared baseline for 'temp_c'"):
        resolve_baselines(ds, {"temp_c": [2016, 2017]})


def test_an_undeclared_window_is_refused_rather_than_defaulted():
    ds = xr.Dataset(
        {"depth_min_m": (("latitude",), np.ones(2, dtype="float32"))},
        coords={"latitude": [55.0, 55.5]},
    )
    with pytest.raises(RefreshFailed, match="no layer declared a baseline window"):
        resolve_baselines(ds, {})


def test_one_failing_layer_fails_the_whole_refresh(tmp_path, small_grid):
    # C§6.1 row 1.
    layers = [
        FakeLayer("copernicus_phy", ["temp_c"]),
        FakeLayer("emodnet_bathy", ["depth_mean_m"], shape="static", fail_on_build=True),
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
        FakeLayer("emodnet_bathy", ["depth_mean_m"], shape="static", fail_on_build=True),
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


def test_a_second_refresh_failing_leaves_the_first_pair_intact(
    tmp_path, small_grid, nine_variable_layers
):
    # C§6.1 row 2 as the DRIVER can reach it: nothing live is touched because the
    # failure happens before write_pair is called at all. (The os.replace window
    # between steps 5 and 6 is the writer's, and C-a proved it there.)
    target = tmp_path / "out"
    years = YearRange(start=2024, end=2024)
    run_refresh(
        nine_variable_layers, grid=small_grid, years=years,
        target_dir=target, workdir=tmp_path / "w1",
    )
    first, _ = load_pair(target)

    failing = [
        *nine_variable_layers[:-1],
        FakeLayer(
            "emodnet_bathy", ["depth_mean_m", "depth_min_m"],
            shape="static", fail_on_build=True,
        ),
    ]
    with pytest.raises(RefreshFailed):
        run_refresh(
            failing, grid=small_grid, years=years,
            target_dir=target, workdir=tmp_path / "w2",
        )

    second, artifact = load_pair(target)
    assert second.artifact_sha256 == first.artifact_sha256
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
        "salinity_psu", "temp_c", "din_umol_l", "dip_umol_l", "light_attenuation_k",
        "significant_wave_m", "depth_mean_m", "depth_min_m", "valid",
    }


def test_the_three_baseline_shapes_come_out_different(
    tmp_path, small_grid, nine_variable_layers
):
    # The driver-level twin of tests/test_refresh_manifest.py's wave-baseline test.
    # One assertion per shape, so the three-way divergence is pinned in one place:
    # a requested span, a fixed sub-window, and an empty one.
    target = tmp_path / "out"
    run_refresh(
        nine_variable_layers,
        grid=small_grid,
        years=YearRange(start=2024, end=2025),
        target_dir=target,
        workdir=tmp_path / "work",
    )
    manifest, _ = load_pair(target)
    assert manifest.baselines["temp_c"] == [2024, 2025]
    assert manifest.baselines["significant_wave_m"] == [2023, 2024, 2025]
    assert manifest.baselines["depth_mean_m"] == []


def test_the_requested_year_range_reaches_the_layers(
    tmp_path, small_grid, nine_variable_layers
):
    # R1 / clause 1: "for a NAMED year range". Without this, build() could ignore
    # `years` entirely and every other test would still pass.
    target = tmp_path / "out"
    run_refresh(
        nine_variable_layers,
        grid=small_grid,
        years=YearRange(start=2016, end=2018),
        target_dir=target,
        workdir=tmp_path / "work",
    )
    manifest, _ = load_pair(target)
    assert manifest.baselines["temp_c"] == [2016, 2017, 2018]
    # ...and the wave window is NOT the requested span, because C§3.2 fixes it.
    assert manifest.baselines["significant_wave_m"] == [2023, 2024, 2025]


def test_a_short_form_coordinate_layer_is_refused_before_anything_is_written(
    tmp_path, small_grid, nine_variable_layers
):
    # Proves MERGE's per-layer guard is reached from the driver and nothing is written.
    # This is NOT the R7 proof — see the next test for that.
    bad = FakeLayer(
        "copernicus_phy",
        ["salinity_psu", "temp_c"],
        data={
            "salinity_psu": (("lat", "lon"), np.ones((3, 3), dtype="float32")),
            "temp_c": (("lat", "lon"), np.ones((3, 3), dtype="float32")),
        },
    )
    target = tmp_path / "out"
    with pytest.raises(ValueError, match="lacks the spatial dims"):
        run_refresh(
            [bad, *nine_variable_layers[1:]],
            grid=small_grid,
            years=YearRange(start=2024, end=2024),
            target_dir=target,
            workdir=tmp_path / "work",
        )
    assert not (target / "forcing.nc").exists()


def test_a_transposed_variable_is_refused_before_anything_is_written(
    tmp_path, small_grid, nine_variable_layers
):
    # R7 proper. Both dims are spelled correctly, so merge_layers' per-layer guard
    # passes and `valid` still comes out (latitude, longitude). Only check_shapes can
    # see that THIS variable has them the wrong way round.
    bad = FakeLayer(
        "emodnet_bathy",
        ["depth_mean_m", "depth_min_m"],
        shape="static",
        data={
            "depth_mean_m": (("longitude", "latitude"), np.ones((3, 3), dtype="float32")),
            "depth_min_m": (("latitude", "longitude"), np.ones((3, 3), dtype="float32")),
        },
    )
    target = tmp_path / "out"
    with pytest.raises(ValueError, match="expected dims"):
        run_refresh(
            [*nine_variable_layers[:-1], bad],
            grid=small_grid,
            years=YearRange(start=2024, end=2024),
            target_dir=target,
            workdir=tmp_path / "work",
        )
    assert not (target / "forcing.nc").exists()


def test_two_layers_declaring_one_variable_are_refused():
    # C§5: one variable, one producing layer. Called directly rather than through
    # run_refresh: with the guard deleted, a two-layer set falls through to C§4.4's
    # claimed-exactly-once ValidationError at Manifest(...), so an end-to-end version
    # would go red with the wrong exception instead of DID NOT RAISE.
    # No build() needed: the guard fires on the variable NAME, and an unbuilt fake
    # declares an empty window for each variable it would produce.
    layers = [
        FakeLayer("copernicus_phy", ["temp_c"]),
        FakeLayer("copernicus_bgc", ["temp_c"]),
    ]
    with pytest.raises(RefreshFailed, match="two layers declared"):
        _declared_windows(layers)


def test_a_layer_set_on_the_wrong_grid_is_refused(tmp_path, small_grid):
    # Nothing else catches this. xr.merge(join="exact") only catches layers
    # disagreeing WITH EACH OTHER; check_shapes sees dim names and order;
    # check_declaration sees variable names. A layer set that agrees internally and is
    # uniformly wrong writes a manifest attesting an extent the artifact lacks — the
    # wave-baseline trap again, on the spatial axis.
    wrong = xr.Dataset(
        {"depth_mean_m": (("latitude", "longitude"), np.ones((2, 2), dtype="float32"))},
        coords={"latitude": [55.0, 55.5], "longitude": [20.0, 20.5]},
    )
    with pytest.raises(RefreshFailed, match="does not sit on the grid"):
        check_grid(wrong, small_grid)


def test_the_right_grid_passes_the_attestation_check(small_grid):
    ok = xr.Dataset(
        {
            "depth_mean_m": (
                ("latitude", "longitude"),
                np.ones((small_grid.n_lat, small_grid.n_lon), dtype="float32"),
            )
        },
        coords={"latitude": small_grid.lats(), "longitude": small_grid.lons()},
    )
    check_grid(ok, small_grid)


def test_a_partial_layer_set_cannot_produce_a_manifest(tmp_path, small_grid):
    # A driver that built one layer still declares all nine variables, so C§4.4's
    # claimed-exactly-once rule fires at manifest construction. The manifest refuses
    # to describe an artifact nobody built.
    layers = [FakeLayer("copernicus_phy", ["salinity_psu", "temp_c"])]
    with pytest.raises(ValidationError) as caught:
        run_refresh(
            layers,
            grid=small_grid,
            years=YearRange(start=2024, end=2024),
            target_dir=tmp_path / "out",
            workdir=tmp_path / "work",
        )
    assert "dip_umol_l" in str(caught.value)  # name the unclaimed, not merely "raised"
```

- [ ] **Step 3: Run to verify it fails**

Run: `micromamba run -n shiny python -m pytest tests/test_refresh_driver.py -v -m spatial`
Expected: FAIL — `ModuleNotFoundError: No module named 'seagarden_dst.refresh.driver'`

- [ ] **Step 4: Write `driver.py`**

```python
"""Build every layer, merge, and write the pair (C§5, C§6).

The driver holds the real Dataset, which makes it the only place that can anchor the
manifest against what was actually built. It does not call `check_declaration` —
`write_pair` already does (R3) — but it does check SHAPES, which nothing else can
(R7), and it resolves each variable's baseline window against the data (R2).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from seagarden_dst.artifact.grid import GridSpec
from seagarden_dst.artifact.manifest import (
    ARTIFACT_SCHEMA_VERSION,
    AbsentField,
    Derivation,
    Manifest,
)
from seagarden_dst.refresh.layer import COVERAGE_LAYERS, Layer, YearRange
from seagarden_dst.refresh.merge import merge_layers
from seagarden_dst.refresh.shapes import check_shapes
from seagarden_dst.refresh.variables import ARTIFACT_VARIABLES
from seagarden_dst.refresh.writer import write_pair

if TYPE_CHECKING:  # pragma: no cover - typing only
    import xarray as xr


class RefreshFailed(RuntimeError):
    """Any layer failing takes the whole refresh with it (C§6.1 row 1)."""


def resolve_baselines(
    dataset: xr.Dataset, declared: dict[str, list[int]]
) -> dict[str, list[int]]:
    """Each variable's baseline window, declared by its layer and checked (R2).

    The criterion C§4.4 states is "no baseline WINDOW applies", not "no year
    dimension". `significant_wave_m` is where those diverge: a monthly p95 with no
    `year` dim and a 2023-2025 window. A dimensional rule writes `[]` there and
    contradicts the spec, the committed fixture, and a test named for the mistake.

    So the layer declares, and where the data carries a `year` coord we check the
    declaration against it. Keys come from `dataset.data_vars`, which keeps
    `set(baselines) == set(data_vars)` and lets the manifest's baselines-keys rule
    catch a produced-but-undeclared variable.
    """
    resolved: dict[str, list[int]] = {}
    for name, variable in dataset.data_vars.items():
        key = str(name)
        if "year" in variable.dims:
            from_data = [int(year) for year in variable["year"].values]
            if key in declared and list(declared[key]) != from_data:
                raise RefreshFailed(
                    f"declared baseline for '{key}' is {list(declared[key])} but the "
                    f"built data carries {from_data}; the manifest would attest a "
                    "window the artifact does not hold"
                )
            resolved[key] = from_data
            continue
        if key not in declared:
            raise RefreshFailed(
                f"no layer declared a baseline window for '{key}', and it has no year "
                "dimension to read one from; an unstated window is not an empty one "
                "(C§4.4) — `significant_wave_m` is exactly this case"
            )
        resolved[key] = list(declared[key])
    return resolved


def derivations() -> list[Derivation]:
    """The three derived fields (C§4.1), defined once and imported by the tests (R4).

    `din_umol_l` is here rather than claimed by `copernicus_bgc` because C§4.1's test
    is MULTI-SOURCE, not "computed": one source variable plus a statistic stays a raw
    claim, more than one needs a named relation. No unit conversion — package B
    verified no3 and nh4 arrive in mmol m-3, which is umol L-1.
    """
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


def _absent_fields() -> list[AbsentField]:
    """What the artifact deliberately does not carry (C§3.3, C§4.2)."""
    return [
        AbsentField(
            field="surface_par",
            reason="no integrated Baltic product carries PAR in any form",
            unblocked_by="a source outside the current layer set",
        )
    ]


def check_grid(dataset: xr.Dataset, grid: GridSpec) -> None:
    """The merged data sits on the grid the manifest is about to attest.

    Nothing else checks this. `xr.merge(join="exact")` catches layers disagreeing WITH
    EACH OTHER; `check_shapes` sees dim names and order; `check_declaration` sees
    variable names. A layer set that agrees internally and is uniformly wrong — the
    four Copernicus layers share one source grid, so a cell-centre/cell-edge offset
    shifts all of them together — would otherwise write a manifest attesting an extent
    the artifact does not have. That is the wave-baseline trap on the spatial axis.
    """
    import numpy as np

    expected = {"latitude": grid.lats(), "longitude": grid.lons()}
    for dim, axis in expected.items():
        size = dataset.sizes.get(dim)
        if size != len(axis):
            raise RefreshFailed(
                f"the merged data does not sit on the grid the manifest attests: "
                f"'{dim}' has {size} points, the GridSpec declares {len(axis)}"
            )
        if dim in dataset.coords and not np.allclose(dataset[dim].values, axis):
            raise RefreshFailed(
                f"the merged data does not sit on the grid the manifest attests: "
                f"'{dim}' coordinates differ from the GridSpec's, so the artifact "
                "covers a different extent than the manifest claims"
            )


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
                "manifest attesting to a completeness the artifact lacks"
            ) from error
    return built


def _declared_windows(layers: Sequence[Layer]) -> dict[str, list[int]]:
    """Merge every layer's declaration, refusing a variable two layers claim."""
    declared: dict[str, list[int]] = {}
    for layer in layers:
        for name, window in layer.baseline_years().items():
            if name in declared:
                raise RefreshFailed(
                    f"two layers declared a baseline window for '{name}'; one "
                    "variable, one producing layer (C§5)"
                )
            declared[name] = list(window)
    # `valid` is the driver's own, computed in merge_layers, so no layer declares it.
    declared["valid"] = []
    return declared


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
    check_shapes(merged)  # R7 - names are check_declaration's job, shapes are ours
    check_grid(merged, grid)  # and the extent is nobody else's at all

    manifest = Manifest(
        artifact_schema_version=ARTIFACT_SCHEMA_VERSION,
        built_on=datetime.now(UTC),
        artifact_filename="forcing.nc",
        artifact_sha256="0" * 64,  # stamped by write_pair over the real bytes
        artifact_bytes=1,
        synthetic=synthetic,
        grid=grid,
        variables=sorted(ARTIFACT_VARIABLES),
        baselines=resolve_baselines(merged, _declared_windows(layers)),
        layers=[layer.provenance() for layer in layers],
        derived=derivations(),
        absent=_absent_fields(),
    )
    return write_pair(merged, manifest, Path(target_dir))
```

**The three guards catch three different things, and each has its own test.** The ordering inside `run_refresh` matters:

| Guard | Catches | Its test |
|---|---|---|
| `merge_layers` → `_coverage_of` | a layer whose variable has no `latitude`/`longitude` at all — the short-form case | `test_a_short_form_coordinate_layer_is_refused_before_anything_is_written` |
| `check_shapes` | dims individually plausible but wrong for *that variable* — transposed, or a wave field that kept its `year` | `test_a_transposed_variable_is_refused_before_anything_is_written` |
| `check_grid` | every dim spelled and ordered right, on the wrong extent | `test_a_layer_set_on_the_wrong_grid_is_refused` |

Merge runs first, so the short-form case never reaches `check_shapes`. That is why the two tests match different fragments: `"lacks the spatial dims"` is merge's, `"expected dims"` is `check_shapes`'s, and `"does not sit on the grid"` is `check_grid`'s. Each fragment is unique to its guard on the driver path.

- [ ] **Step 5: Remove the duplicated derivations (R4)**

In `tests/refresh_builders.py`, replace the body of `derived()` with a call to the canonical definition:

```python
from seagarden_dst.refresh.driver import derivations


def derived() -> list[Derivation]:
    return derivations()
```

**Also delete the `COVERAGE_LAYERS` import Task 1 Step 10 added.** Once `derived()` stops building the `valid` record itself, `_COVERAGE_LAYERS` has no remaining use in that module and ruff fails it as F401 — an unused import that Task 1 needed and Task 3 orphans. Confirm with `ruff check tests/refresh_builders.py` before committing; if some other function still uses it, keep it and say so.

Move the existing explanatory comment about `din_umol_l` into `driver.derivations()`'s docstring if it is not already there, rather than deleting it.

**Watch for an import cycle:** `refresh_builders` is a test helper, and `driver` imports xarray only under `TYPE_CHECKING`, so importing it from an unmarked test module is safe. Confirm `pytest -q` (no marker) still collects.

- [ ] **Step 6: Run tests to verify they pass**

```bash
micromamba run -n shiny python -m pytest tests/test_refresh_driver.py -v -m spatial
micromamba run -n shiny python -m pytest -q
micromamba run -n shiny python -m pytest -q -m spatial
```
Expected: 17 passed, then the full suite green both ways. (Seventeen is this module as written in Step 2; Task 4 Step 4 appends two more CLI-path tests and takes it to 19.)

- [ ] **Step 7: Commit**

```bash
git add src/seagarden_dst/refresh/driver.py tests/test_refresh_driver.py tests/conftest.py tests/refresh_builders.py
git commit -m "feat(refresh): add the driver that builds, merges and writes the pair"
```

- [ ] **Step 8: DELETE proof — fail-on-any-layer**

Replace the `raise RefreshFailed(...)` in `_build_all` with `continue`. Run with `-m spatial`. `test_one_failing_layer_fails_the_whole_refresh` and `test_a_failing_layer_writes_no_partial_artifact` must both go red; `test_a_second_refresh_failing_leaves_the_first_pair_intact` will also go red, and the report must say so — a mutation reddening more tests than predicted is a fact about the suite worth recording.

- [ ] **Step 9: DELETE proof — the baseline declaration branch (the trap)**

The most important proof in this plan. Replace the `if key not in declared: raise` / `resolved[key] = list(declared[key])` block with `resolved[key] = []` — i.e. reinstate the dimensional rule this plan was rewritten to remove.

Expected red: `test_a_declared_window_survives_a_variable_with_no_year_dimension` on `[] != [2023, 2024, 2025]`, `test_the_three_baseline_shapes_come_out_different`, `test_the_requested_year_range_reaches_the_layers`, and `test_an_undeclared_window_is_refused_rather_than_defaulted`. `test_a_static_field_keeps_its_empty_window` must stay **green** — that asymmetry proves the tests distinguish "empty window" from "no window stated". Restore, re-run green. Record every output.

- [ ] **Step 10: DELETE proof — the disagreement guard**

Delete the `if key in declared and list(declared[key]) != from_data:` branch. `test_a_declaration_disagreeing_with_the_data_is_refused` must go red with `DID NOT RAISE`. Restore, re-run green.

**No SWAP proof is owed here**, and the reason is worth stating so nobody adds one later. The global standard triggers a swap only where two sibling messages share a *matched substring*; these do not. One test matches `declared baseline for 'temp_c'`, the other matches `no layer declared a baseline window`, and neither fragment occurs in the other message. The bodies are not exchangeable in any case: the disagreement message interpolates `list(declared[key])`, which raises `KeyError` inside the `key not in declared` branch — so a swap would go red on a crash rather than on a mismatched fragment, which is the "red for the wrong reason" the standard forbids.

- [ ] **Step 11: DELETE proof — `check_shapes` in the driver**

Delete the `check_shapes(merged)` line. Run with `-m spatial`.

`test_a_transposed_variable_is_refused_before_anything_is_written` must go red with `DID NOT RAISE` — a transposed variable survives `xr.merge(join="exact")` and `_coverage_of`, so nothing else refuses it and the artifact would reach disk. `test_a_short_form_coordinate_layer_is_refused_before_anything_is_written` must stay **green**, because `merge_layers` refuses that one first. That asymmetry is what separates the two guards. Restore, re-run green.

- [ ] **Step 12: DELETE proof — the grid attestation**

Delete the `check_grid(merged, grid)` line. `test_a_layer_set_on_the_wrong_grid_is_refused` calls `check_grid` directly, so it stays green — say so in the report, then add the end-to-end case that does go red: a `nine_variable_layers` set built against a *different* `GridSpec` than the one passed to `run_refresh`, asserting no artifact is written. Restore, re-run green.

Then the **SWAP proof**: `check_grid` raises two messages sharing the fragment `does not sit on the grid the manifest attests`, which is exactly what both tests would match. Swap the two trailing clauses (the point-count one and the coordinate one). The size test and a coordinate test must each go red. If you have only the size test, write the coordinate one first — a shared matched substring with only one test behind it is the gap a SWAP proof exists to find.

- [ ] **Step 13: DELETE proof — the duplicate-declaration guard**

Delete the `if name in declared:` branch in `_declared_windows`. `test_two_layers_declaring_one_variable_are_refused` must go red with `DID NOT RAISE`. Restore, re-run green.

---

### Task 4: The CLI

**Files:**
- Create: `scripts/refresh_layers.py`
- Test: `tests/test_refresh_cli.py`, plus one `spatial` test appended to `tests/test_refresh_driver.py`

**Interfaces:**
- Consumes: `REGISTRY`, `run_refresh` (Task 3), `YearRange`/`ProbeResult` (Task 1)
- Produces: `build_parser()`, `probe_all(layers)`, `format_probe_report(results)`, `main(argv=None) -> int`

This module and its tests are **unmarked** — they must import without xarray, which is why `refresh_fakes` defers its import and why `run_refresh` is imported inside the refresh branch.

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
    assert build_parser().parse_args(["--probe"]).probe is True


def test_probe_all_reports_one_result_per_layer():
    layers = [
        FakeLayer("copernicus_phy", ["temp_c"]),
        FakeLayer("emodnet_bathy", ["depth_mean_m"], reachable=False),
    ]
    assert [(r.name, r.reachable) for r in probe_all(layers)] == [
        ("copernicus_phy", True),
        ("emodnet_bathy", False),
    ]


def test_the_report_marks_the_unreachable_layer_and_not_the_reachable_one():
    layers = [
        FakeLayer("copernicus_phy", ["temp_c"]),
        FakeLayer("emodnet_bathy", ["depth_mean_m"], reachable=False),
    ]
    report = format_probe_report(probe_all(layers))
    reachable_line = next(ln for ln in report.splitlines() if "copernicus_phy" in ln)
    unreachable_line = next(ln for ln in report.splitlines() if "emodnet_bathy" in ln)
    assert reachable_line.startswith("ok")
    assert unreachable_line.startswith("UNREACHABLE")


def test_an_unreachable_layer_makes_the_probe_exit_nonzero(monkeypatch):
    # C§8.2: the job turns red so a dead upstream is loud — and it lives outside
    # ci.yml so that redness blocks no pull request.
    import scripts.refresh_layers as cli

    monkeypatch.setattr(
        cli,
        "REGISTRY",
        {"emodnet_bathy": FakeLayer("emodnet_bathy", ["depth_mean_m"], reachable=False)},
    )
    assert main(["--probe"]) == 1


def test_an_all_reachable_probe_exits_zero(monkeypatch):
    import scripts.refresh_layers as cli

    monkeypatch.setattr(
        cli, "REGISTRY", {"copernicus_phy": FakeLayer("copernicus_phy", ["temp_c"])}
    )
    assert main(["--probe"]) == 0


def test_an_empty_registry_does_not_probe_green(monkeypatch):
    # The C-b REGISTRY ships empty (C-c fills it). A monthly job reporting nothing and
    # exiting 0 is a check that cannot fail — worse than no check, because it looks
    # like one.
    import scripts.refresh_layers as cli

    monkeypatch.setattr(cli, "REGISTRY", {})
    assert main(["--probe"]) == 1


def test_a_refresh_without_a_year_range_is_refused(capsys):
    with pytest.raises(SystemExit):
        main([])
    assert "--start-year and --end-year are required" in capsys.readouterr().err
```

- [ ] **Step 2: Run to verify it fails**

Run: `micromamba run -n shiny python -m pytest tests/test_refresh_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.refresh_layers'`

- [ ] **Step 3: Write `scripts/refresh_layers.py`**

Read `scripts/make_fixture.py` first and copy its `sys.path` preamble verbatim, comment included — the same development-environment reason applies. It goes where the marker sits below. The imports that follow the preamble need `# noqa: E402`, exactly as `make_fixture.py` does.

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
from collections.abc import Sequence
from pathlib import Path

# ... sys.path preamble copied from scripts/make_fixture.py ...

from seagarden_dst.refresh.layer import Layer, ProbeResult, YearRange  # noqa: E402
from seagarden_dst.refresh.registry import REGISTRY  # noqa: E402


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
        "--target", type=Path, default=Path("data/forcing"),
        help="directory receiving the artifact/manifest pair",
    )
    parser.add_argument(
        "--workdir", type=Path, default=Path(".refresh-work"),
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
        status = "ok" if result.reachable else "UNREACHABLE"
        lines.append(f"{status:<11} {result.name}  {result.detail}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.probe:
        if not REGISTRY:
            print(
                "no layers are registered, so this probe checked nothing. Exiting "
                "non-zero rather than reporting green: a check that cannot fail is "
                "worse than no check, because it looks like one."
            )
            return 1
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

Two things not to "tidy":

1. **`REGISTRY` is a module-level name**, so `monkeypatch.setattr(cli, "REGISTRY", ...)` reaches what `main` reads. `main` must read the module global, never re-import it inside the function.
2. **The `run_refresh` import stays inside the refresh branch.** Moving it to the top turns CI's `[app,dev]` job red.

`f"{status:<11}"` left-pads to the width of `"UNREACHABLE"`, so the tests assert with `startswith` rather than counting spaces.

- [ ] **Step 4: Add the refresh-branch test**

This one is `spatial` — the only test exercising `main`'s refresh path and `GridSpec.baltic()`. Append it to `tests/test_refresh_driver.py`, so the CLI module stays unmarked:

```python
def test_the_cli_refresh_branch_builds_a_pair(
    tmp_path, small_grid, nine_variable_layers, monkeypatch
):
    # Clause 1 end to end: the CLI is the entry point C§5 names, and without this its
    # refresh branch is never executed by any test.
    #
    # `baltic` is patched to the small grid on purpose. Measured, not guessed: the real
    # extent is 390 x 630 = 245,700 cells, so all nine variables over two years is
    # ~126 MB resident, 2-3x that transiently inside to_netcdf, and a ~100 MB file
    # written on every run. That is not a unit test. The patch is what keeps it one.
    import scripts.refresh_layers as cli

    from seagarden_dst.artifact.grid import GridSpec

    monkeypatch.setattr(GridSpec, "baltic", classmethod(lambda cls: small_grid))
    monkeypatch.setattr(cli, "REGISTRY", {ly.name: ly for ly in nine_variable_layers})
    target = tmp_path / "out"
    code = cli.main(
        [
            "--start-year", "2024", "--end-year", "2025",
            "--target", str(target), "--workdir", str(tmp_path / "work"),
        ]
    )
    assert code == 0
    assert (target / "forcing.nc").exists()
    assert (target / "manifest.json").exists()


def test_the_cli_takes_its_extent_from_the_baltic_grid_alone(monkeypatch):
    # The patch in the test above would hide a CLI that stopped calling `baltic`, so
    # pin the property that makes the patch safe: there is no grid option, therefore
    # `GridSpec.baltic()` is the only extent the refresh branch can possibly use.
    import scripts.refresh_layers as cli

    from seagarden_dst.artifact.grid import GridSpec

    assert not any(action.dest == "grid" for action in cli.build_parser()._actions)

    called = []
    monkeypatch.setattr(GridSpec, "baltic", classmethod(lambda cls: called.append(cls) or None))
    monkeypatch.setattr(cli, "REGISTRY", {"copernicus_phy": FakeLayer("copernicus_phy", ["temp_c"])})
    with pytest.raises(Exception):  # noqa: B017 - it fails downstream on a None grid
        cli.main(["--start-year", "2024", "--end-year", "2024"])
    assert called, "the refresh branch never asked for the Baltic grid"
```

This second test is deliberately crude — it proves only that the refresh branch *reaches* `GridSpec.baltic()`, by making that call record itself and letting the run fail immediately afterwards. If it turns out fragile, drop the monkeypatch half and keep the no-grid-option assertion, which is the load-bearing part. Say which you kept in the report.

- [ ] **Step 5: Run tests to verify they pass**

```bash
micromamba run -n shiny python -m pytest tests/test_refresh_cli.py -v
micromamba run -n shiny python -m pytest tests/test_refresh_driver.py -v -m spatial
```
Expected: 8 passed (the CLI module), then 19 passed (the driver module: 17 from Task 3 plus the two added here)

- [ ] **Step 6: Commit**

```bash
git add scripts/refresh_layers.py tests/test_refresh_cli.py tests/test_refresh_driver.py
git commit -m "feat(refresh): add the refresh_layers CLI with a probe mode"
```

- [ ] **Step 7: SWAP proof — the two report statuses**

Both report lines carry the layer name, so deleting one does not prove the test reads the *status*. Swap `"ok"` and `"UNREACHABLE"` in `format_probe_report`. `test_the_report_marks_the_unreachable_layer_and_not_the_reachable_one` must go red on both `startswith` assertions. Restore, re-run green.

- [ ] **Step 8: DELETE proof — the nonzero exit and the empty-registry guard**

First make `main` return `0` unconditionally in probe mode: `test_an_unreachable_layer_makes_the_probe_exit_nonzero` and `test_an_empty_registry_does_not_probe_green` must go red while `test_an_all_reachable_probe_exits_zero` stays green — the asymmetry is the discrimination. Restore.

Then delete the `if not REGISTRY:` guard alone: only `test_an_empty_registry_does_not_probe_green` must go red. Restore, re-run green. Record every output.

---

### Task 5: The deposit stub

**Files:**
- Create: `src/seagarden_dst/refresh/deposit.py`
- Test: `tests/test_refresh_deposit.py`

**Interfaces:**
- Consumes: `Manifest`/`Archive`, `tests/refresh_builders.py:manifest()`
- Produces: `Depositor` Protocol with `deposit(artifact: Path, manifest: Path) -> str`; `record_doi(manifest: Manifest, doi: str) -> Manifest`

`refresh_builders.manifest()` produces all five layers with `archive.status == "pending"` — checked while writing this plan. If that has changed, set the state up explicitly in the test; adjust the *setup*, never the assertion.

- [ ] **Step 1: Write the failing tests (clause 9)**

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


def test_a_whitespace_doi_is_refused():
    with pytest.raises(ValueError, match="deposit returned no DOI"):
        record_doi(build_manifest(), "   ")


def test_a_flip_that_would_break_the_archive_contract_is_caught():
    # The discriminating test for re-validation: `deposited` requires a zenodo_doi
    # (Archive._check_state_is_complete). If record_doi skipped the validators it
    # would happily emit a `deposited` layer with none.
    after = record_doi(build_manifest(), _DOI)
    after.layers[0].archive.zenodo_doi = None
    with pytest.raises(ValueError, match="requires a zenodo_doi"):
        Manifest.model_validate(after.model_dump())
```

- [ ] **Step 2: Run to verify it fails**

Run: `micromamba run -n shiny python -m pytest tests/test_refresh_deposit.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'seagarden_dst.refresh.deposit'`

- [ ] **Step 3: Write `deposit.py`**

```python
"""Recording a Zenodo deposit back into the manifest (C§8.1, C§9).

**No deposit is performed here.** C§9 puts the deposit itself outside package C: a
human runs it, following the runbook. What this module owns is the half that can be
tested — the shape of a depositor, and what recording its DOI does to the manifest.

The sequence C§8.1 fixes, and why the two manifests differ:

    build   -> every layer `archive.status: pending`, no DOI exists yet
    deposit -> Zenodo returns a DOI
    record  -> the DOI goes back into the COMMITTED manifest, flipping those
               layers to `deposited`

The deposited copy is a snapshot of the moment before the DOI existed; the committed
manifest is authoritative for provenance. `artifact_sha256` is unaffected throughout —
it covers the artifact, and the artifact does not change.
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
    it was never part of is exactly the unmarked provenance this design prevents. A
    `deposited` layer already has its own DOI and keeps it.
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

    # Rebuilt through the validators, not model_copy(update=), which does not re-run
    # them. Emitting a manifest that skipped C§4.4 is the one thing this package must
    # never do — and `Archive` itself requires a DOI for `deposited`, so the flip is
    # checked rather than trusted.
    return Manifest.model_validate(payload)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `micromamba run -n shiny python -m pytest tests/test_refresh_deposit.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add src/seagarden_dst/refresh/deposit.py tests/test_refresh_deposit.py
git commit -m "feat(refresh): add the deposit protocol and DOI recording"
```

- [ ] **Step 6: DELETE proof — the status filter**

Make `record_doi` flip every layer regardless of status. `test_a_forbidden_layer_is_not_flipped` must go red. Restore, re-run green.

- [ ] **Step 7: DELETE proof — the empty-DOI guard**

Delete the `if not doi or not doi.strip():` branch. `test_an_empty_doi_is_refused` and `test_a_whitespace_doi_is_refused` must both go red. Note *how* they fail — if a downstream validator raises with a different message, the `match=` is doing real work; if they fail with `DID NOT RAISE`, the guard is the only thing there. Restore, re-run green.

- [ ] **Step 8: DELETE proof — the re-validation**

Use a mutation that isolates validator-skipping *without* collateral damage. **Not** `Manifest.model_construct(**payload)`: that leaves `layers` as plain dicts, so three tests die with `AttributeError: 'dict' object has no attribute 'archive'` — collateral that proves nothing about re-validation. Instead, mutate to a copy that keeps real models and simply never re-runs the validators:

```python
    copy = manifest.model_copy(deep=True)
    for layer in copy.layers:
        if layer.archive.status == "pending":
            layer.archive.status = "deposited"
            layer.archive.zenodo_doi = doi
    return copy
```

`Manifest.model_config` sets only `extra="forbid"`, so `validate_assignment` is off and those assignments are unchecked.

Expect `test_the_flipped_manifest_still_validates` **not** to go red — it re-validates what `record_doi` failed to, so it does not discriminate. `test_a_flip_that_would_break_the_archive_contract_is_caught` is the one that does. Confirm how each behaves, and say plainly in the report which moved and which did not: a mutation that changes nothing is a finding about the test, not a clean bill of health. Restore, re-run green.

---

### Task 6: The scheduled probe workflow

**Files:**
- Create: `.github/workflows/source-probe.yml`
- Test: `tests/test_refresh_cli.py` (extend)

**Interfaces:**
- Consumes: `scripts/refresh_layers.py --probe` (Task 4)
- Produces: a workflow that runs monthly and on `workflow_dispatch`, and blocks no pull request

`pyyaml>=6.0` is already a core dependency (`pyproject.toml:19`), so no new install is needed.

- [ ] **Step 1: Write the failing test**

Add `yaml` and `Path` to the imports at the **top** of `tests/test_refresh_cli.py` — they belong in this task, not Task 4, because Task 4 has no use for them and ruff would fail that task's commit on two unused imports:

```python
from pathlib import Path

import pytest
import yaml
from refresh_fakes import FakeLayer

from scripts.refresh_layers import build_parser, format_probe_report, main, probe_all
```

Then append the tests:

```python
_WORKFLOWS = Path(__file__).resolve().parent.parent / ".github" / "workflows"
_PROBE = _WORKFLOWS / "source-probe.yml"


def _workflow():
    # PyYAML parses the unquoted key `on` as the boolean True (the Norway problem),
    # so the triggers live under the True key. Checked against this environment's
    # PyYAML: yaml.safe_load("on:\n  schedule: []\n") has the single key True.
    # Do not "fix" this to the string "on".
    return yaml.safe_load(_PROBE.read_text(encoding="utf-8"))


def test_the_probe_workflow_is_scheduled_and_dispatchable():
    triggers = _workflow()[True]
    assert "schedule" in triggers
    assert "workflow_dispatch" in triggers


def test_the_probe_workflow_blocks_no_pull_request():
    # C§8.2: gating merges on a third-party service would make every PR hostage to
    # Copernicus.
    triggers = _workflow()[True]
    assert "pull_request" not in triggers
    assert "push" not in triggers


def test_ci_does_not_run_the_probe():
    # The separation that matters is behavioural, not two files existing: ci.yml must
    # not invoke the probe, or the separation is cosmetic.
    assert "--probe" not in (_WORKFLOWS / "ci.yml").read_text(encoding="utf-8")


def test_the_probe_workflow_runs_the_probe_flag():
    steps = _workflow()["jobs"]["probe"]["steps"]
    assert any("--probe" in str(step.get("run", "")) for step in steps)


def test_the_probe_workflow_installs_without_the_spatial_extra():
    # The probe path is deliberately xarray-free (C§8.2: catalogue metadata only).
    # Installing the spatial extra here would make a reachability check depend on the
    # scientific stack it exists to avoid needing.
    steps = _workflow()["jobs"]["probe"]["steps"]
    installs = " ".join(str(step.get("run", "")) for step in steps)
    assert "spatial" not in installs
```

- [ ] **Step 2: Run to verify it fails**

Run: `micromamba run -n shiny python -m pytest tests/test_refresh_cli.py -v -k workflow`
Expected: FAIL — `FileNotFoundError` on `source-probe.yml`

- [ ] **Step 3: Write the workflow**

Read `.github/workflows/ci.yml` and match its runner image and `actions/setup-python` version. The install line below is deliberately **not** `ci.yml`'s: the probe needs the package and nothing else.

```yaml
name: source-probe

# Separate from ci.yml on purpose (C§8.2): a dead upstream source turns this job red
# and blocks no pull request. Gating merges on the continued existence of a
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
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install
        # No extras. probe() makes catalogue metadata calls only, and the CLI's probe
        # path imports no xarray, so the spatial stack would be dead weight here.
        run: |
          python -m pip install --upgrade pip
          pip install -e .
      - name: Probe every registered source
        env:
          COPERNICUSMARINE_SERVICE_USERNAME: ${{ secrets.COPERNICUSMARINE_SERVICE_USERNAME }}
          COPERNICUSMARINE_SERVICE_PASSWORD: ${{ secrets.COPERNICUSMARINE_SERVICE_PASSWORD }}
        run: python -m scripts.refresh_layers --probe
```

The credential is the **institutional** Copernicus account (C§8.1), held as a repository secret. The workflow must not fall back to a personal one and must not print it.

**Known and intended:** with C-b's empty `REGISTRY` this job exits 1 until C-c registers the layers. That is the empty-registry guard doing its job — a monthly check that passes while checking nothing would be worse. Record it in the task report and in the C-c handoff so the first red run is expected rather than alarming.

- [ ] **Step 4: Run tests to verify they pass**

Run: `micromamba run -n shiny python -m pytest tests/test_refresh_cli.py -v`
Expected: 13 passed

- [ ] **Step 5: Run everything**

```bash
micromamba run -n shiny python -m pytest -q
micromamba run -n shiny python -m pytest -q -m spatial
micromamba run -n shiny ruff check .
```
Expected: all green. Record the counts. If ruff flags the new code, fix the code — the repo was clean before this branch.

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/source-probe.yml tests/test_refresh_cli.py
git commit -m "ci: add the monthly source-probe workflow, separate from ci.yml"
```

- [ ] **Step 7: DELETE proof — the trigger separation**

Add `pull_request:` to the workflow's triggers. `test_the_probe_workflow_blocks_no_pull_request` must go red. Restore, re-run green.

- [ ] **Step 8: DELETE proof — the no-extras install**

Change the install line to `pip install -e ".[spatial]"`. `test_the_probe_workflow_installs_without_the_spatial_extra` must go red. Restore, re-run green.

---

## Done-When Coverage

| Clause | Task | How it is proven |
|---|---|---|
| 1 — builds artifact and manifest for a named year range | 3, 4 | `test_a_successful_refresh_writes_a_loadable_pair`, `test_the_requested_year_range_reaches_the_layers`, `test_the_cli_refresh_branch_builds_a_pair` |
| 6 — `--probe` reports reachability, scheduled separately | 4, 6 | CLI exit-code tests (including the empty registry) + workflow trigger and install tests |
| 9 — deposit path exercised against a stub | 5 | `test_recording_a_doi_flips_pending_layers_to_deposited`, `test_a_flip_that_would_break_the_archive_contract_is_caught` |
| 11 — `valid` is the coverage intersection | 2 | `test_valid_is_the_intersection_of_two_disagreeing_masks`, plus the 4-D and month-only reduction tests |

**Clause 5 is NOT claimed by C-b.** "An interrupted refresh leaves the previous pair valid" is about the `os.replace` window between C§6's steps 5 and 6, and C-a already discharged it against `write_pair`'s `_hook` seam. The driver cannot reach that window: it fails before `write_pair` is called at all. `test_a_second_refresh_failing_leaves_the_first_pair_intact` is named for what it actually proves — a failed *rebuild* does not disturb the pair on disk — and is deliberately not presented as clause 5.

Clauses 2, 3, 4, 8, 10 and 12 were discharged by C-a and their tests must stay green.

Clause 7 — the runbook followed end to end by someone who did not write it — **cannot be discharged by an implementer**; it is a human act. C-b writes no runbook: `docs/runbooks/annual-refresh.md` (C§8.1) belongs to C-c, when the transfer volumes it must quote are measurable rather than estimated.

## Out of Scope

The five real layer implementations (C-c), the EMODnet regrid with `rioxarray`/`rasterio`, the free-disk precheck (C§6.1 — it needs real transfer volumes to name a requirement), and the annual-refresh runbook.

## Handoff Notes For C-c

- `REGISTRY` ships empty, so `source-probe.yml` exits 1 until C-c fills it. Expected, not a regression.
- Each of the five layers implements **five** protocol members. `baseline_years()` is the one C§5 does not mention: `copernicus_wav` returns `{"significant_wave_m": [2023, 2024, 2025]}` regardless of the requested range, and `emodnet_bathy` returns `[]` for both depth fields.
- `EXPECTED_DIMS` in `refresh/shapes.py` is the contract each layer's output is checked against. A layer emitting `lat`/`lon` is refused at the merge; a transposed one at `check_shapes`; one on the wrong extent at `check_grid`.
- `merge_layers` uses `combine_attrs="drop_conflicts"`, so layers may carry different **dataset-level** attrs — they will, since EMODnet and CMEMS do not share a `source` — while each variable keeps its own attrs, including the CRS C§3.2 requires. Do not "tighten" this to `no_conflicts`: it raises `MergeError` on the first real pair of layers.
- Unlike `FakeLayer`, a real layer must know its baseline window without having built anything: `baseline_years()` is called after `build()` today, but nothing should depend on that.
- The free-disk precheck and the annual-refresh runbook are C-c's, and both need the real transfer volumes (~30 GB across the wire per C§8.1).
