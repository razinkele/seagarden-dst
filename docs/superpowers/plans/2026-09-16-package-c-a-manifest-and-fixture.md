# Package C-a — manifest, writer and fixture — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the provenance manifest — its Pydantic models, its four completeness validators, the atomic artifact/manifest writer, and a committed synthetic fixture that exercises every schema rule.

**Architecture:** A new `src/seagarden_dst/refresh/` package holding `grid.py`, `manifest.py` and `writer.py`. Nothing in it is imported by the model core, and it imports nothing from the core — the boundary is asserted in both directions by a test. The fixture is *generated* by a committed script using the same writer and manifest code a production refresh uses, never hand-written.

**Tech Stack:** Python 3.11+, Pydantic v2, xarray + h5netcdf (NetCDF4), pytest.

**Spec:** `docs/superpowers/specs/2026-09-15-package-c-refresh-tooling-design.md` (revision 3, merged). Read it alongside this plan. Where the two disagree, the spec wins and this plan is wrong.

## Scope

This is **C-a of three**. It delivers C§3.1, C§4 and C§6, and discharges done-when clauses **2, 3, 4, 10 and 12**. It does **not** implement the `Layer` protocol, the `REGISTRY`, the driver, `--probe`, the deposit stub or any real data source — those are C-b (clauses 1, 5, 6, 9, 11) and C-c (clause 7). Do not write them here, even where an interface obviously anticipates them.

## Global Constraints

- **Python floor 3.11**; CI tests 3.11 and 3.13. Do not use syntax newer than 3.11.
- **`extra="forbid"` on every Pydantic model**, matching `src/seagarden_dst/params.py`.
- **`artifact_schema_version = 1`.** No negotiation mechanism; an unrecognised value is refused.
- **Nine artifact variables, exactly:** `salinity_psu`, `temp_c`, `din_umol_l`, `dip_umol_l`, `light_attenuation_k`, `significant_wave_m`, `depth_mean_m`, `depth_min_m`, `valid`.
- **All fields are float32 except `valid`, which is bool.** C§3.2: a float32 `valid` holding 0.0/1.0 can never be NaN, so a reader applying the is-NaN test would find every cell valid everywhere, silently.
- **Grid:** 53.5–60.0 N, 9.5–27.0 E; steps 0.016666° lat × 0.027777° lon; CRS `EPSG:4326`; 390 × 630 cells.
- **Import boundary, both directions:** no module under `src/seagarden_dst/` outside `refresh/` may import `refresh`, and nothing in `refresh/` may import from the model core **except `seagarden_dst.artifact`**, which is the shared schema both sides are supposed to agree on. C§10 clause 8 states the first; the second is what actually keeps the `spatial` extra confined. The exception is narrow and load-bearing: `artifact/` depends only on pydantic, stdlib and numpy, so importing it drags nothing from the extra into the core or the core into the refresh environment — and without it `write_pair` could not take a `Manifest`.
- **The fixture is generated, never edited by hand.** C§7 requires it be written by the same code as a production refresh.
- Commit after every task. Run `pytest -q` before every commit.

## Two spec ambiguities this plan resolves

Both are recorded here rather than decided silently in code. If you disagree, raise it before implementing — do not quietly pick the other branch.

**1. What `valid`'s `Derivation.inputs` names.** C§3.5 says `valid` is "the intersection of all contributing layers' coverage" and C§4.1 says its `inputs` "span every contributing layer". Read literally that includes `copernicus_bgc_light` — and if it does, **C§7's positive orphan-layer test passes for the wrong reason.** That test exists to prove `copernicus_bgc_light`, whose `variables` is empty, is reachable *via `light_attenuation_k`'s `Derivation`*. If `valid` also named it, the layer would be reachable anyway and the test would still pass with `light_attenuation_k`'s derivation deleted entirely.

**Decision: `valid.inputs` names the four layers that contribute an independent coverage mask** — `copernicus_phy`, `copernicus_bgc`, `copernicus_wav`, `emodnet_bathy` — and **not** `copernicus_bgc_light`, which reads the same BGC grid as `copernicus_bgc` and so contributes no coverage of its own. This keeps C§7's orphan test testing what it claims to. Flag it as a candidate C§4.1 clarification when C-a is reviewed.

**2. `version` and `retrieved_on` on a synthetic fixture.** The spec gives no guidance. **Decision:** `version: "synthetic"` and `retrieved_on` fixed at `2026-01-01T00:00:00Z`, not build time. A build-time value changes the committed fixture's bytes on every regeneration, which breaks any committed-checksum assertion for no reason.

---

## File structure

**RULING (recorded during the final fix wave, 2026-09-16): `seagarden_dst.artifact`
shipped as `seagarden_dst.refresh`.** Every task brief below silently implemented
the file structure and "Why `artifact/` is not under `refresh/`" argument that
follow using `refresh/` in place of `artifact/`, and no ruling was recorded at the
time. The ~24 references to `seagarden_dst.artifact.*` in this document (the table
below, the task briefs, the code fences) are stale; they are not rewritten here —
one note is clearer than 24 mechanical edits, and the actual shipped code is the
source of truth for exact module paths. The ruling: `refresh/` keeps everything
for C-a. C§4.3 names `seagarden_dst/refresh/manifest.py` explicitly, and splitting
the schema into a new core-side package at the end of a long branch is a large,
untested refactor that belongs to a design decision, not a cleanup at the end of
C-a. The consequence is real: package D cannot import `Manifest` or `load_pair`
without either importing `refresh/` (which `test_no_core_module_imports_refresh`
forbids) or re-homing the pydantic-only half of this design into a new core-side
package later. That is unresolved here and is left for C-b or D to settle — see
`src/seagarden_dst/refresh/manifest.py`'s module docstring for the same note kept
beside the code.

| File | Responsibility |
|---|---|
| `src/seagarden_dst/artifact/__init__.py` | Package marker. Re-exports `GridSpec`, `Manifest`, `sha256_of`, `load_pair`. |
| `src/seagarden_dst/artifact/grid.py` | `GridSpec` — the grid definition, in one place (C§3.1). |
| `src/seagarden_dst/artifact/manifest.py` | All manifest models and the four C§4.4 validators. |
| `src/seagarden_dst/artifact/pair.py` | `sha256_of` and `load_pair` — the READ side of C§6. |
| `src/seagarden_dst/refresh/__init__.py` | Package marker. Exports nothing from the core. |
| `src/seagarden_dst/refresh/writer.py` | `write_pair` — the WRITE side, and the only part needing xarray. |

**Why `artifact/` is not under `refresh/`.** An earlier revision of this plan put the
manifest models and the whole writer under `refresh/`, which cannot work alongside Task 6.
C§4.3 requires that "D and C1 validate the same way C wrote it", and C§6.1 rows 3-4 put the
checksum refusal in the **reader** — so package D must import `Manifest`, `sha256_of` and
`load_pair`. Task 6's `test_no_core_module_imports_refresh` forbids exactly that, so D's
first commit would have had to turn the test red or keep a second copy of the schema, and a
second copy is how the manifest and the reader drift apart. That is the class of defect this
whole design exists to prevent.

The split follows the dependency, not the package name: `grid.py`, `manifest.py` and
`pair.py` need only pydantic, stdlib and numpy, so nothing forced them under an extra they
do not use. `write_pair` takes an `xr.Dataset` and stays where the xarray dependency is.
| `scripts/make_fixture.py` | Generates the committed fixture using the above. |
| `tests/fixtures/data/forcing.nc`, `manifest.json` | The committed fixture. |
| `tests/test_refresh_manifest.py` | C§7's in-memory validator cases. |
| `tests/test_refresh_fixture.py` | C§7's committed-fixture and checksum cases. |
| `tests/test_refresh_isolation.py` | The import boundary, both directions. |

---

### Task 1: `GridSpec`

**Files:**
- Create: `src/seagarden_dst/refresh/__init__.py`, `src/seagarden_dst/artifact/grid.py`
- Test: `tests/test_refresh_manifest.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `GridSpec(crs: str, lat_min: float, lat_max: float, lon_min: float, lon_max: float, lat_step: float, lon_step: float, n_lat: int, n_lon: int)`, with classmethod `GridSpec.baltic() -> GridSpec` and methods `lats() -> np.ndarray`, `lons() -> np.ndarray`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_refresh_manifest.py
import pytest

from seagarden_dst.artifact.grid import GridSpec


def test_baltic_grid_matches_the_shipped_extent():
    """C§3.1: 53.5-60.0 N, 9.5-27.0 E on the Copernicus native grid."""
    g = GridSpec.baltic()
    assert (g.lat_min, g.lat_max) == (53.5, 60.0)
    assert (g.lon_min, g.lon_max) == (9.5, 27.0)
    assert g.crs == "EPSG:4326"
    assert (g.n_lat, g.n_lon) == (390, 630)
    assert len(g.lats()) == 390
    assert len(g.lons()) == 630


def test_grid_rejects_an_inverted_extent():
    """A max below its min is a typo that would otherwise yield an empty grid."""
    with pytest.raises(ValueError):
        GridSpec(
            crs="EPSG:4326", lat_min=60.0, lat_max=53.5, lon_min=9.5, lon_max=27.0,
            lat_step=0.016666, lon_step=0.027777, n_lat=390, n_lon=630,
        )
```

- [ ] **Step 2: Run it and watch it fail**

Run: `pytest tests/test_refresh_manifest.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'seagarden_dst.refresh'`

- [ ] **Step 3: Implement**

```python
# src/seagarden_dst/refresh/__init__.py
"""Package C refresh tooling.

Build-time only. Nothing here may be imported by the model core, and nothing here
may import from it — `tests/test_refresh_isolation.py` asserts both directions.
That boundary is what keeps the `spatial` extra out of the runtime install, which
is what keeps the tool reconstructible to 2034 (design section 4).
"""
```

```python
# src/seagarden_dst/artifact/grid.py
"""The artifact grid, defined once (C§3.1)."""

from __future__ import annotations

import numpy as np
from pydantic import BaseModel, ConfigDict, model_validator

# Copernicus Baltic native resolution. NOT a choice: package B established that
# coarsening to ~4 km land-masks the cell containing Tagalaht, the only published
# anchor the parameterisation has.
_LAT_STEP = 0.016666
_LON_STEP = 0.027777


class GridSpec(BaseModel):
    """The target grid. Widening the extent is a change here plus a refresh."""

    model_config = ConfigDict(extra="forbid")

    crs: str
    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float
    lat_step: float
    lon_step: float
    n_lat: int
    n_lon: int

    @model_validator(mode="after")
    def _check_extent_is_not_inverted(self) -> "GridSpec":
        if self.lat_max <= self.lat_min:
            raise ValueError(f"lat_max {self.lat_max} must exceed lat_min {self.lat_min}")
        if self.lon_max <= self.lon_min:
            raise ValueError(f"lon_max {self.lon_max} must exceed lon_min {self.lon_min}")
        return self

    @classmethod
    def baltic(cls) -> "GridSpec":
        """The shipped extent. Excludes the Gulfs of Bothnia and Finland (C§3.1)."""
        return cls(
            crs="EPSG:4326",
            lat_min=53.5, lat_max=60.0, lon_min=9.5, lon_max=27.0,
            lat_step=_LAT_STEP, lon_step=_LON_STEP,
            n_lat=390, n_lon=630,
        )

    def lats(self) -> np.ndarray:
        return self.lat_min + np.arange(self.n_lat, dtype="float64") * self.lat_step

    def lons(self) -> np.ndarray:
        return self.lon_min + np.arange(self.n_lon, dtype="float64") * self.lon_step
```

- [ ] **Step 4: Run it and watch it pass**

Run: `pytest tests/test_refresh_manifest.py -q`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add src/seagarden_dst/refresh/ tests/test_refresh_manifest.py
git commit -m "The artifact grid, defined in one place"
```

---

### Task 2: Provenance records and the archive state

**Files:**
- Create: `src/seagarden_dst/artifact/manifest.py`
- Modify: `tests/test_refresh_manifest.py`

**Interfaces:**
- Consumes: `GridSpec` from Task 1.
- Produces:
  - `Archive(status: Literal["deposited","forbidden","pending"], zenodo_doi: str | None = None, source_url: str | None = None, unblocked_by: str | None = None)`
  - `LayerProvenance(name: str, source: str, product_id: str, dataset_id: str, version: str, retrieved_on: datetime, licence: str, redistribution: Literal["allowed","forbidden"], source_url: str, archive: Archive, variables: list[str])`
  - `DerivationInput(layer: str, variable: str)`
  - `Derivation(field: str, relation: str, inputs: list[DerivationInput])`
  - `AbsentField(field: str, reason: str, unblocked_by: str)`

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_refresh_manifest.py
from datetime import datetime, timezone

from seagarden_dst.artifact.manifest import Archive, LayerProvenance


def _layer(**over):
    """A valid layer record. Override one field per negative case."""
    base = dict(
        name="copernicus_phy",
        source="Copernicus Marine Service",
        product_id="BALTICSEA_MULTIYEAR_PHY_003_011",
        dataset_id="cmems_mod_bal_phy_my_P1M-m",
        version="202303",
        retrieved_on=datetime(2026, 1, 1, tzinfo=timezone.utc),
        licence="Copernicus Marine Service licence",
        redistribution="allowed",
        source_url="https://data.marine.copernicus.eu/",
        archive=Archive(
            status="pending",
            source_url="https://data.marine.copernicus.eu/",
            unblocked_by="the Zenodo deposit is outside package C (C1)",
        ),
        variables=["salinity_psu", "temp_c"],
    )
    base.update(over)
    return LayerProvenance(**base)


def test_pending_with_a_url_and_a_note_is_accepted():
    """C§4.1: pending is the state every layer of a first real refresh is in."""
    assert _layer().archive.status == "pending"


def test_deposited_needs_a_doi():
    with pytest.raises(ValueError):
        Archive(status="deposited")


def test_forbidden_needs_a_source_url():
    with pytest.raises(ValueError):
        Archive(status="forbidden")


def test_pending_without_a_source_url_is_rejected():
    with pytest.raises(ValueError):
        Archive(status="pending", unblocked_by="a note")


def test_pending_without_an_unblocked_by_note_is_rejected():
    """An incomplete pending records a gap without saying what closes it."""
    with pytest.raises(ValueError):
        Archive(status="pending", source_url="https://example.invalid/")


def test_an_unknown_archive_status_is_rejected():
    """The validator accepts exactly three states and nothing else."""
    with pytest.raises(ValueError):
        Archive(status="archived", source_url="https://example.invalid/")


def test_a_layer_with_no_archive_state_is_rejected():
    """C§7's FIRST archive case, and clause 10's third negative test.

    `archive` is a required field with no default, so a layer without one fails
    at load. Easy to leave untested because the other five cases all exercise a
    malformed archive rather than an absent one — and without it, a later
    refactor giving `archive` a `None` default would pass the whole suite while
    making every layer's provenance optional.
    """
    with pytest.raises(ValueError):
        _layer(archive=None)
```

- [ ] **Step 2: Run them and watch them fail**

Run: `pytest tests/test_refresh_manifest.py -q`
Expected: FAIL — `ImportError: cannot import name 'Archive'`

- [ ] **Step 3: Implement**

```python
# src/seagarden_dst/artifact/manifest.py
"""The provenance manifest (C§4).

Every rule the design states as prose is a validator here, so a manifest that
would mislead a reader fails at load rather than mid-analysis — the principle
`params._check_salinity_indexed_is_computable` and `params.Anchor` already follow.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from seagarden_dst.artifact.grid import GridSpec

ARTIFACT_SCHEMA_VERSION = 1


class Archive(BaseModel):
    """Where the layer's bytes are archived, or honestly why they are not yet.

    Three states and no fourth. `pending` exists because C§1 puts the Zenodo
    deposit outside package C: at manifest-construction time no layer has a DOI,
    and all five layers are genuinely redistributable, so `forbidden` would be a
    lie told to clear a validator — precisely the mis-marked provenance this
    design exists to prevent.
    """

    model_config = ConfigDict(extra="forbid")

    status: Literal["deposited", "forbidden", "pending"]
    zenodo_doi: str | None = None
    source_url: str | None = None
    unblocked_by: str | None = None

    @model_validator(mode="after")
    def _check_state_is_complete(self) -> "Archive":
        if self.status == "deposited" and not self.zenodo_doi:
            raise ValueError("archive.status 'deposited' requires a zenodo_doi")
        if self.status == "forbidden" and not self.source_url:
            raise ValueError("archive.status 'forbidden' requires a source_url")
        if self.status == "pending":
            if not self.source_url:
                raise ValueError("archive.status 'pending' requires a source_url")
            if not self.unblocked_by:
                raise ValueError(
                    "archive.status 'pending' requires an unblocked_by note: an "
                    "incomplete pending records a gap without saying what closes it"
                )
        return self


class LayerProvenance(BaseModel):
    """One record per *dataset*, not per source service (C§4.1).

    `name` is the REGISTRY key, carried on the record because
    `derived[].inputs[].layer` resolves against it — without it that reference
    names a table with no key column.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    source: str
    product_id: str
    dataset_id: str
    version: str
    retrieved_on: datetime
    licence: str
    redistribution: Literal["allowed", "forbidden"]
    source_url: str
    archive: Archive
    variables: list[str]


class DerivationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    layer: str
    variable: str


class Derivation(BaseModel):
    """A computed field, and what it was computed from.

    A computed field has no single raw source, so it cannot be an entry in some
    layer's `variables`; it is claimed here instead (C§4.4).
    """

    model_config = ConfigDict(extra="forbid")

    field: str
    relation: str
    inputs: list[DerivationInput]


class AbsentField(BaseModel):
    """A field the artifact deliberately does not carry (C§4.2).

    Today it has one entry, `surface_par`. Machine-readable so the UI reads the
    manifest instead of carrying a hardcoded caveat that can drift.
    """

    model_config = ConfigDict(extra="forbid")

    field: str
    reason: str
    unblocked_by: str
```

- [ ] **Step 4: Run them and watch them pass**

Run: `pytest tests/test_refresh_manifest.py -q`
Expected: 9 passed (2 from Task 1, 7 here)

- [ ] **Step 5: Commit**

```bash
git add src/seagarden_dst/artifact/manifest.py tests/test_refresh_manifest.py
git commit -m "Provenance records, and a third honest archive state"
```

---

### Task 3: The manifest, and the four rules that keep it honest

**Files:**
- Modify: `src/seagarden_dst/artifact/manifest.py`, `tests/test_refresh_manifest.py`

**Interfaces:**
- Consumes: Task 2's models, Task 1's `GridSpec`.
- Produces: `ARTIFACT_VARIABLES: frozenset[str]` and `Manifest(artifact_schema_version: int, built_on: datetime, artifact_filename: str, artifact_sha256: str, artifact_bytes: int, synthetic: bool, grid: GridSpec, baselines: dict[str, list[int]], layers: list[LayerProvenance], derived: list[Derivation], absent: list[AbsentField])`.

**The four rules (C§4.4), each with a C§7 case that fails without it:**

1. Every artifact variable is claimed **exactly once** across `⋃ layers[].variables` and `⋃ derived[].field`.
2. `baselines` keys are **exactly** that claimed set — not a subset, not a superset.
3. `dataset_id` is **unique** across `layers`.
4. Every layer is **reachable**: it claims a variable, or a `derived[].inputs[].layer` names it.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_refresh_manifest.py
from seagarden_dst.artifact.manifest import (
    ARTIFACT_VARIABLES,
    AbsentField,
    Derivation,
    DerivationInput,
    Manifest,
)

_YEARS = list(range(2016, 2026))
_COVERAGE_LAYERS = ("copernicus_phy", "copernicus_bgc", "copernicus_wav", "emodnet_bathy")


def _layers():
    return [
        _layer(name="copernicus_phy", dataset_id="cmems_mod_bal_phy_my_P1M-m",
               variables=["salinity_psu", "temp_c"]),
        _layer(name="copernicus_bgc", dataset_id="cmems_mod_bal_bgc_my_P1M-m",
               variables=["din_umol_l", "dip_umol_l"]),
        # Empty `variables` is expected, not a gap: its only output is derived.
        _layer(name="copernicus_bgc_light", dataset_id="cmems_mod_bal_bgc_my_P1D-m",
               variables=[]),
        _layer(name="copernicus_wav", dataset_id="cmems_mod_bal_wav_my_PT1H-i",
               variables=["significant_wave_m"]),
        _layer(name="emodnet_bathy", dataset_id="emodnet_bathymetry_2024",
               variables=["depth_mean_m", "depth_min_m"]),
    ]


def _derived():
    return [
        Derivation(
            field="light_attenuation_k",
            relation="Poole-Atkins k = 1.7/z_SD, computed daily then averaged monthly",
            inputs=[DerivationInput(layer="copernicus_bgc_light", variable="zsd")],
        ),
        Derivation(
            field="valid",
            relation="intersection of contributing layer coverage",
            inputs=[DerivationInput(layer=n, variable="coverage") for n in _COVERAGE_LAYERS],
        ),
    ]


def _baselines():
    return {
        "salinity_psu": _YEARS, "temp_c": _YEARS, "din_umol_l": _YEARS,
        "dip_umol_l": _YEARS, "light_attenuation_k": _YEARS,
        "significant_wave_m": [2023, 2024, 2025],
        "depth_mean_m": [], "depth_min_m": [], "valid": [],
    }


def _manifest(**over):
    base = dict(
        artifact_schema_version=1,
        built_on=datetime(2026, 1, 1, tzinfo=timezone.utc),
        artifact_filename="forcing.nc",
        artifact_sha256="0" * 64,
        artifact_bytes=1,
        synthetic=True,
        grid=GridSpec.baltic(),
        baselines=_baselines(),
        layers=_layers(),
        derived=_derived(),
        absent=[AbsentField(
            field="surface_par",
            reason="no integrated Baltic product carries PAR in any form",
            unblocked_by="a source outside the current layer set",
        )],
    )
    base.update(over)
    return Manifest(**base)


def test_the_reference_manifest_validates():
    assert set(_manifest().baselines) == ARTIFACT_VARIABLES


def test_a_variable_claimed_by_nobody_is_rejected():
    layers = _layers()
    layers[0].variables = ["salinity_psu"]          # drops temp_c
    with pytest.raises(ValueError, match="claimed by no"):
        _manifest(layers=layers)


def test_a_variable_claimed_by_two_layers_is_rejected():
    layers = _layers()
    layers[1].variables = ["din_umol_l", "dip_umol_l", "temp_c"]
    with pytest.raises(ValueError, match="claimed more than once"):
        _manifest(layers=layers)


def test_a_variable_claimed_by_a_layer_and_a_derivation_is_rejected():
    """Not covered by the two-layers case: the rule is stated over the *union*."""
    layers = _layers()
    layers[2].variables = ["light_attenuation_k"]
    with pytest.raises(ValueError, match="claimed more than once"):
        _manifest(layers=layers)


def test_a_missing_baseline_key_is_rejected():
    b = _baselines()
    del b["depth_mean_m"]
    with pytest.raises(ValueError, match="baselines"):
        _manifest(baselines=b)


def test_an_empty_baseline_is_accepted_and_is_not_omission():
    """[] means no baseline window applies. The two states must be told apart."""
    assert _manifest().baselines["valid"] == []


def test_an_extra_baseline_key_is_rejected():
    b = _baselines()
    b["surface_par"] = _YEARS
    with pytest.raises(ValueError, match="baselines"):
        _manifest(baselines=b)


def test_the_wave_baseline_is_not_empty_despite_having_no_year_dimension():
    """C§4.4: the criterion is 'no baseline window', not 'no year dimension'.

    An implementer applying the dimensional test literally would write [] here
    and assert that no window applies to the one variable C§4.1 cites as the
    whole reason baselines is a mapping.
    """
    assert _manifest().baselines["significant_wave_m"] == [2023, 2024, 2025]


def test_a_duplicate_dataset_id_is_rejected():
    """The copy-paste that splits a layer and forgets to change dataset_id."""
    layers = _layers()
    layers[2].dataset_id = "cmems_mod_bal_bgc_my_P1M-m"   # the monthly product
    with pytest.raises(ValueError, match="dataset_id"):
        _manifest(layers=layers)


def test_an_orphan_layer_is_rejected():
    """A sixth layer with empty `variables` that no derivation names.

    Constructed by ADDING a layer, not by deleting `light_attenuation_k`'s
    derivation. That obvious construction does not work: dropping the derivation
    also unclaims `light_attenuation_k`, so `_check_every_variable_is_claimed_
    exactly_once` — defined earlier, and `model_validator(mode="after")` runs in
    definition order with the first raise winning — fires instead, with a message
    containing no "reachable". The test would fail, and the natural repair
    (loosening `match=`) would leave C§4.4's fourth rule with no case that
    discriminates it, which is what done-when clause 12 forbids.

    Adding an unreferenced layer violates rule 4 and nothing else: the claim union
    is unchanged, `baselines` is unchanged, and the dataset_id is new.
    """
    layers = _layers()
    layers.append(_layer(
        name="copernicus_orphan",
        dataset_id="cmems_mod_bal_orphan_my_P1M-m",
        variables=[],
    ))
    with pytest.raises(ValueError, match="reachable"):
        _manifest(layers=layers)


def test_the_empty_variables_layer_is_accepted_when_a_derivation_names_it():
    """The positive case: the rule must not simply outlaw the empty list."""
    m = _manifest()
    assert m.layers[2].variables == []
    assert any(i.layer == "copernicus_bgc_light" for d in m.derived for i in d.inputs)


def test_an_unrecognised_schema_version_is_refused():
    with pytest.raises(ValueError, match="artifact_schema_version"):
        _manifest(artifact_schema_version=2)
```

- [ ] **Step 2: Run them and watch them fail**

Run: `pytest tests/test_refresh_manifest.py -q`
Expected: FAIL — `ImportError: cannot import name 'ARTIFACT_VARIABLES'`

- [ ] **Step 3: Implement — append to `manifest.py`**

```python
# The nine variables the artifact carries (C§3.2). `surface_par` is deliberately
# absent and is recorded in `absent`, not here.
ARTIFACT_VARIABLES: frozenset[str] = frozenset({
    "salinity_psu", "temp_c", "din_umol_l", "dip_umol_l", "light_attenuation_k",
    "significant_wave_m", "depth_mean_m", "depth_min_m", "valid",
})


class Manifest(BaseModel):
    """The artifact's provenance, beside it and validated with it."""

    model_config = ConfigDict(extra="forbid")

    artifact_schema_version: int
    built_on: datetime
    artifact_filename: str
    artifact_sha256: str
    artifact_bytes: int
    synthetic: bool
    grid: GridSpec
    baselines: dict[str, list[int]]
    layers: list[LayerProvenance]
    derived: list[Derivation]
    absent: list[AbsentField]

    @model_validator(mode="after")
    def _check_schema_version(self) -> "Manifest":
        if self.artifact_schema_version != ARTIFACT_SCHEMA_VERSION:
            raise ValueError(
                f"artifact_schema_version {self.artifact_schema_version} is not "
                f"{ARTIFACT_SCHEMA_VERSION}; refusing rather than guessing the shape"
            )
        return self

    @model_validator(mode="after")
    def _check_every_variable_is_claimed_exactly_once(self) -> "Manifest":
        claims: dict[str, list[str]] = {}
        for layer in self.layers:
            for name in layer.variables:
                claims.setdefault(name, []).append(f"layer {layer.name}")
        for d in self.derived:
            claims.setdefault(d.field, []).append(f"derivation {d.field}")

        twice = {name: who for name, who in claims.items() if len(who) > 1}
        if twice:
            raise ValueError(
                "these variables are claimed more than once, so the manifest cannot "
                f"say which source produced them: {twice}"
            )
        unclaimed = ARTIFACT_VARIABLES - set(claims)
        if unclaimed:
            raise ValueError(
                "these artifact variables are claimed by no layer and no derivation, "
                f"so they sit in the artifact with nothing behind them: {sorted(unclaimed)}"
            )
        extra = set(claims) - ARTIFACT_VARIABLES
        if extra:
            raise ValueError(f"claimed variables the artifact does not carry: {sorted(extra)}")
        return self

    @model_validator(mode="after")
    def _check_baseline_keys_are_exactly_the_claimed_set(self) -> "Manifest":
        keys = set(self.baselines)
        if keys != set(ARTIFACT_VARIABLES):
            raise ValueError(
                "baselines keys must be exactly the artifact's variables — a variable "
                "with no entry is one whose temporal coverage the manifest does not "
                f"state. missing={sorted(ARTIFACT_VARIABLES - keys)} "
                f"extra={sorted(keys - ARTIFACT_VARIABLES)}"
            )
        return self

    @model_validator(mode="after")
    def _check_dataset_ids_are_unique(self) -> "Manifest":
        seen: dict[str, str] = {}
        for layer in self.layers:
            if layer.dataset_id in seen:
                raise ValueError(
                    f"layers {seen[layer.dataset_id]!r} and {layer.name!r} share "
                    f"dataset_id {layer.dataset_id!r}; one layer means one dataset"
                )
            seen[layer.dataset_id] = layer.name
        return self

    @model_validator(mode="after")
    def _check_every_layer_is_reachable(self) -> "Manifest":
        named = {i.layer for d in self.derived for i in d.inputs}
        orphans = [
            layer.name for layer in self.layers
            if not layer.variables and layer.name not in named
        ]
        if orphans:
            raise ValueError(
                "these layers are reachable from nothing — no variable claim and no "
                "derivation input names them, so the manifest attests a source nothing "
                f"uses, or uses a source it never attests: {orphans}"
            )
        unknown = named - {layer.name for layer in self.layers}
        if unknown:
            raise ValueError(
                f"derivation inputs name layers that do not exist: {sorted(unknown)}"
            )
        return self
```

- [ ] **Step 4: Run them and watch them pass**

Run: `pytest tests/test_refresh_manifest.py -q`
Expected: 21 passed (9 from Tasks 1-2, 12 here)

- [ ] **Step 5: Commit**

```bash
git add src/seagarden_dst/artifact/manifest.py tests/test_refresh_manifest.py
git commit -m "Four rules so nothing slips between the provenance records"
```

---

### Task 4: The atomic pair writer

**Files:**
- Create: `src/seagarden_dst/refresh/writer.py`
- Create: `tests/test_refresh_fixture.py`
- Modify: `tests/conftest.py`

**Interfaces:**
- Consumes: `Manifest` from Task 3.
- Produces: `write_pair(dataset: xr.Dataset, manifest: Manifest, target_dir: Path) -> tuple[Path, Path]` in `refresh/writer.py`; and, in `artifact/pair.py`, `sha256_of(path: Path) -> str` and `load_pair(target_dir: Path) -> tuple[Manifest, Path]`, which raises `ValueError` on a checksum mismatch.
- **`sha256_of` and `load_pair` go in `artifact/pair.py`, not in the writer.** They are the
  read side: C§6.1 rows 3-4 put the checksum refusal in the reader, and package D is the
  reader. Neither needs xarray — `sha256_of` is hashlib over bytes and `load_pair` parses
  JSON into `Manifest` and returns the artifact's path without opening it. Leaving them
  beside `write_pair` would put them behind Task 6's import boundary, where D cannot reach
  them.

C§6's sequence is an ordering, not a suggestion: temp dir on the **same filesystem**; artifact → `.tmp` + fsync; sha256; manifest carrying that sha → `.tmp` + fsync; `os.replace` the artifact; `os.replace` the manifest **last**.

- [ ] **Step 1: Add the two shared fixtures to `tests/conftest.py`**

```python
# append to tests/conftest.py
import pytest


@pytest.fixture
def tiny_dataset():
    """A 3x3-cell, 2-year dataset carrying all nine variables at C§3.2 shapes.

    float32 everywhere except `valid`, which is bool — a float32 `valid` holding
    0.0/1.0 can never be NaN, so a reader applying the is-NaN test would find
    every cell valid, everywhere, silently.
    """
    import numpy as np
    import xarray as xr

    rng = np.random.default_rng(20260916)
    years, months, n = [2024, 2025], list(range(1, 13)), 3
    lat = np.linspace(54.0, 54.1, n)
    lon = np.linspace(20.0, 20.1, n)
    four_d = ("year", "month", "latitude", "longitude")

    def f4():
        return (four_d, rng.random((len(years), len(months), n, n)).astype("float32"))

    valid = np.ones((n, n), dtype=bool)
    valid[0, 0] = False          # at least one invalid cell, so the field is exercised

    return xr.Dataset(
        {
            "salinity_psu": f4(), "temp_c": f4(), "din_umol_l": f4(),
            "dip_umol_l": f4(), "light_attenuation_k": f4(),
            "significant_wave_m": (("month", "latitude", "longitude"),
                                   rng.random((len(months), n, n)).astype("float32")),
            "depth_mean_m": (("latitude", "longitude"),
                             rng.random((n, n)).astype("float32")),
            "depth_min_m": (("latitude", "longitude"),
                            rng.random((n, n)).astype("float32")),
            "valid": (("latitude", "longitude"), valid),
        },
        coords={"year": years, "month": months, "latitude": lat, "longitude": lon},
    )
```

`reference_manifest` is the `_manifest()` builder from Task 3. Move that builder and its `_layer`, `_layers`, `_derived`, `_baselines` helpers into `tests/conftest.py` as a `reference_manifest` fixture so both test modules share one definition, and import them in `tests/test_refresh_manifest.py` rather than duplicating. Duplicating the builder is how the two copies drift.

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_refresh_fixture.py
import json

import pytest

# `pytestmark` below deselects this module from the default run — but `-m` filters
# AFTER collection, and collection imports the module. In the `.[app,dev]` install
# the xarray import two lines down raises ModuleNotFoundError at COLLECTION, which
# no marker can reach, taking both CI legs red on every pull request. That is the
# exact outcome C§11 says the mechanism must avoid, so the marker alone does not
# implement it. `importorskip` turns the ImportError into a clean module-level skip.
#
# It must come BEFORE the writer import: `writer.py` imports xarray at module level
# too, so skipping only this module's own xarray import would not help.
pytest.importorskip("xarray")

import xarray as xr  # noqa: E402

from seagarden_dst.refresh.writer import (  # noqa: E402
    load_pair,
    sha256_of,
    write_pair,
)

pytestmark = pytest.mark.spatial


def test_the_written_pair_round_trips(tmp_path, reference_manifest, tiny_dataset):
    artifact, manifest_path = write_pair(tiny_dataset, reference_manifest, tmp_path)
    assert artifact.name == "forcing.nc"
    assert manifest_path.name == "manifest.json"
    loaded, artifact_path = load_pair(tmp_path)
    assert loaded.artifact_sha256 == sha256_of(artifact_path)
    assert loaded.artifact_bytes == artifact_path.stat().st_size


def test_a_torn_pair_is_refused(tmp_path, reference_manifest, tiny_dataset):
    """Interrupted between C§6 steps 5 and 6: new artifact, old manifest."""
    _, manifest_path = write_pair(tiny_dataset, reference_manifest, tmp_path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["artifact_sha256"] = "1" * 64
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="sha256"):
        load_pair(tmp_path)


def test_an_interrupted_write_leaves_the_previous_pair_intact(
    tmp_path, reference_manifest, tiny_dataset
):
    """C§6.1 row 2: nothing live is touched before step 5."""
    write_pair(tiny_dataset, reference_manifest, tmp_path)
    first, _ = load_pair(tmp_path)

    broken = tiny_dataset.copy()
    broken["salinity_psu"] = broken["salinity_psu"] * 2

    class _Boom(Exception):
        pass

    def _explode(*_a, **_k):
        raise _Boom("layer failed mid-build")

    with pytest.raises(_Boom):
        write_pair(broken, reference_manifest, tmp_path, _hook=_explode)

    again, _ = load_pair(tmp_path)
    assert again.artifact_sha256 == first.artifact_sha256
```

`write_pair` therefore needs a keyword-only `_hook=None` called immediately **before** the first `os.replace`, so the interruption can be injected without patching `os`. Name it as a test seam in its docstring; a seam nobody can see is one somebody removes.

- [ ] **Step 3: Run them and watch them fail**

Run: `pytest tests/test_refresh_fixture.py -q -m spatial`
Expected: FAIL — `ModuleNotFoundError: No module named 'seagarden_dst.refresh.writer'`

- [ ] **Step 4: Implement**

```python
# src/seagarden_dst/refresh/writer.py
"""Writing the artifact and manifest as a verifiable pair (C§6).

Section 6.3 asks for the two to be "written atomically as a pair". No filesystem
provides that: `os.replace` is atomic per file, there is no two-file equivalent,
and on Windows there is no directory-swap trick either. What a filesystem *can*
deliver is a checksum link plus an ordering, so a torn pair is refused rather
than read.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Callable  # not typing.Callable: ruff UP035
from pathlib import Path

import xarray as xr

from seagarden_dst.artifact.manifest import Manifest

_ARTIFACT = "forcing.nc"
_MANIFEST = "manifest.json"
_CHUNK = 1024 * 1024


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for block in iter(lambda: fh.read(_CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def _fsync(path: Path) -> None:
    # "rb+", not "rb": on Windows os.fsync maps to _commit()/FlushFileBuffers,
    # which needs write access, and a read-only handle raises
    # OSError [Errno 9] Bad file descriptor. Verified on the development machine.
    with path.open("rb+") as fh:
        os.fsync(fh.fileno())


def write_pair(
    dataset: xr.Dataset,
    manifest: Manifest,
    target_dir: Path,
    *,
    _hook: Callable[[], None] | None = None,
) -> tuple[Path, Path]:
    """Write the pair, manifest last. Returns (artifact_path, manifest_path).

    `_hook` is a test seam, called immediately before the first `os.replace` so
    a test can interrupt the write at the one moment that matters (C§6.1 row 2).
    It is not part of the production call.
    """
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    # Temp dir inside the target: a rename across filesystems is a copy, and not
    # atomic. TemporaryDirectory cleans up the partial write on any exception.
    with tempfile.TemporaryDirectory(dir=target_dir) as tmp:
        tmp_dir = Path(tmp)
        tmp_artifact = tmp_dir / (_ARTIFACT + ".tmp")

        encoding = {name: {"zlib": True, "complevel": 4} for name in dataset.data_vars}
        dataset.to_netcdf(tmp_artifact, engine="h5netcdf", encoding=encoding)
        _fsync(tmp_artifact)

        stamped = manifest.model_copy(update={
            "artifact_filename": _ARTIFACT,
            "artifact_sha256": sha256_of(tmp_artifact),
            "artifact_bytes": tmp_artifact.stat().st_size,
        })
        # model_copy does not re-run validators, and a manifest that skipped them
        # is the one thing this module must never emit.
        stamped = Manifest.model_validate(stamped.model_dump())

        tmp_manifest = tmp_dir / (_MANIFEST + ".tmp")
        tmp_manifest.write_text(stamped.model_dump_json(indent=2), encoding="utf-8")
        _fsync(tmp_manifest)

        if _hook is not None:
            _hook()

        artifact = target_dir / _ARTIFACT
        manifest_path = target_dir / _MANIFEST
        os.replace(tmp_artifact, artifact)       # step 5
        os.replace(tmp_manifest, manifest_path)  # step 6 — last, deliberately

    return artifact, manifest_path


def load_pair(target_dir: Path) -> tuple[Manifest, Path]:
    """Load the manifest and verify it describes the artifact beside it.

    Refuses on mismatch and never reads the artifact anyway: between C§6's steps
    5 and 6 the old manifest's sha no longer matches, and reading new data under
    old provenance is the failure the checksum exists to make loud.
    """
    target_dir = Path(target_dir)
    manifest_path = target_dir / _MANIFEST
    manifest = Manifest.model_validate(
        json.loads(manifest_path.read_text(encoding="utf-8"))
    )
    artifact = target_dir / manifest.artifact_filename

    actual = sha256_of(artifact)
    if actual != manifest.artifact_sha256:
        raise ValueError(
            f"artifact_sha256 mismatch for {artifact}: the manifest says "
            f"{manifest.artifact_sha256}, the file is {actual}. Refusing to read the "
            "artifact under a manifest that does not describe it — re-run the refresh."
        )
    return manifest, artifact
```

- [ ] **Step 5: Run them and watch them pass**

Run: `pytest tests/test_refresh_fixture.py -q -m spatial`
Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add src/seagarden_dst/refresh/writer.py tests/test_refresh_fixture.py tests/conftest.py
git commit -m "What atomicity can actually mean for two files"
```

---

### Task 5: The fixture, generated rather than written

**Files:**
- Create: `scripts/make_fixture.py`
- Create: `tests/fixtures/data/forcing.nc`, `tests/fixtures/data/manifest.json`
- Modify: `.gitignore`, `tests/test_refresh_fixture.py`

**Interfaces:**
- Consumes: Tasks 1–4.
- Produces: `build_fixture(target_dir: Path) -> tuple[Path, Path]`, importable so a test can rebuild into `tmp_path` and compare.

C§7: synthetic-valued but structurally real — 3×3 cells, 2 years, every variable at its correct shape, written by the *same* writer and manifest code as a production refresh, `synthetic: true`, five layer records, `archive.status: pending` throughout, `[]` baselines for all three static fields.

**Structural decisions the script must make, all fixed here.** If you find yourself making a structural choice not on this list, stop — it belongs in this plan, not in the script.

- The grid is a 3×3 `GridSpec` built directly, **not** `GridSpec.baltic()`. Its bounds are
  **derived from the steps** rather than chosen independently: `lat_min=54.0`,
  `lon_min=20.0`, the production steps `lat_step=0.016666` and `lon_step=0.027777`,
  `n_lat=n_lon=3`, so `lat_max=54.0 + 3*0.016666 = 54.049998` and
  `lon_max=20.0 + 3*0.027777 = 20.083331`. `crs="EPSG:4326"`.
  **Do not pick round bounds.** Three cells at the production steps span 0.050 and 0.083,
  not 0.1, and `GridSpec` validates only inversion — so a `lat_max=54.1` would produce a
  committed manifest whose steps, cell counts and bounds cannot all be true at once. C§7
  requires the fixture to be *structurally real*, and D or C1 reconstructing cell centres
  from those steps would land on different cells than the artifact carries.
- **`tiny_dataset`'s coordinates must come from the same `GridSpec`**, via `grid.lats()` and
  `grid.lons()` — not from an independent `np.linspace`. Task 4's fixture uses `linspace`
  over round bounds, which gives a 0.05 spacing in both axes and matches neither production
  step; update it when you write the generator so the two agree by construction.
- Years are `[2024, 2025]`; months `1..12`.
- Values come from `numpy.random.default_rng(20260916)` — a fixed seed, so a rebuild is byte-comparable.
- `valid` has `[0, 0]` set `False`; every other cell `True`.
- `synthetic=True`, `artifact_schema_version=1`, `built_on=2026-01-01T00:00:00Z`.
- Every layer: `version="synthetic"`, `retrieved_on=2026-01-01T00:00:00Z`, `archive.status="pending"` with a real `source_url` and an `unblocked_by` of `"the Zenodo deposit is outside package C (C1)"`.
- The five layers, their `dataset_id`s and their `variables` are exactly Task 3's `_layers()`; the two derivations exactly Task 3's `_derived()`; the baselines exactly Task 3's `_baselines()` **except** that the year lists are `[2024, 2025]` for the five annual variables and `[2024, 2025]` for `significant_wave_m` — the fixture is two years, and its baselines must describe the fixture, not production.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_refresh_fixture.py
from pathlib import Path

from seagarden_dst.artifact.manifest import ARTIFACT_VARIABLES

FIXTURE = Path(__file__).parent / "fixtures" / "data"


def test_the_committed_fixture_loads_and_its_checksum_matches():
    """This IS section 9's provenance test."""
    manifest, _ = load_pair(FIXTURE)
    assert manifest.synthetic is True
    assert len(manifest.layers) == 5
    assert {layer.archive.status for layer in manifest.layers} == {"pending"}
    assert set(manifest.baselines) == ARTIFACT_VARIABLES


def test_the_fixture_carries_every_variable_at_its_shape():
    _, artifact = load_pair(FIXTURE)
    with xr.open_dataset(artifact, engine="h5netcdf") as ds:
        assert set(ds.data_vars) == set(ARTIFACT_VARIABLES)
        assert ds["salinity_psu"].dims == ("year", "month", "latitude", "longitude")
        assert ds["significant_wave_m"].dims == ("month", "latitude", "longitude")
        assert ds["depth_mean_m"].dims == ("latitude", "longitude")
        assert ds["salinity_psu"].dtype == "float32"
        assert ds["valid"].dtype == bool


def test_the_three_static_fields_carry_an_empty_baseline():
    manifest, _ = load_pair(FIXTURE)
    for name in ("depth_mean_m", "depth_min_m", "valid"):
        assert manifest.baselines[name] == []
    # And the one that is NOT the dimensional test: significant_wave_m has no
    # year dimension but does have a baseline window (C§4.4).
    assert manifest.baselines["significant_wave_m"] != []


def test_the_fixture_can_be_rebuilt_from_its_script(tmp_path):
    """C§7: written by the same writer and manifest code as a production refresh.

    Compares STRUCTURE, not bytes. h5netcdf stamps `_NCProperties` into every
    file with its own version and those of hdf5 and h5py — measured on the
    development machine as `version=2,h5netcdf=1.8.1,hdf5=1.14.6,h5py=3.15.1`.
    Two builds are byte-identical on one machine with one set of versions, and
    differ across the 3.11 and 3.13 CI legs or after any dependency bump. A
    sha comparison would be green locally and red in CI for a reason that has
    nothing to do with the fixture, which is worse than no test.
    """
    from scripts.make_fixture import build_fixture

    build_fixture(tmp_path)
    committed, committed_artifact = load_pair(FIXTURE)
    rebuilt, rebuilt_artifact = load_pair(tmp_path)

    skip = {"artifact_sha256", "artifact_bytes"}
    assert rebuilt.model_dump(exclude=skip) == committed.model_dump(exclude=skip)
    with (
        xr.open_dataset(committed_artifact, engine="h5netcdf") as a,
        xr.open_dataset(rebuilt_artifact, engine="h5netcdf") as b,
    ):
        xr.testing.assert_identical(a, b)
```

- [ ] **Step 2: Run them and watch them fail**

Run: `pytest tests/test_refresh_fixture.py -q -m spatial`
Expected: FAIL — `tests/fixtures/data/manifest.json` does not exist

- [ ] **Step 3: Write the generator and run it**

Write `scripts/make_fixture.py` exposing `build_fixture(target_dir: Path) -> tuple[Path, Path]`, making exactly the structural decisions listed above and calling `write_pair`. Give it a `if __name__ == "__main__":` block that builds into `tests/fixtures/data/`.

Add the `.gitignore` exception C§7 anticipates, directly beneath the existing `*.nc` rule so the pair is read together:

```gitignore
!tests/fixtures/data/*.nc
```

Run it as a **module**, from the repository root:

```bash
micromamba run -n shiny python -m scripts.make_fixture
```

`python scripts/make_fixture.py` puts `scripts/` on `sys.path` instead of the repository
root, so `import seagarden_dst` resolves only by accident of the editable install. `-m`
keeps the root on the path, which is also what makes Task 5's
`from scripts.make_fixture import build_fixture` work under pytest's
`pythonpath = ["src", "."]`.

- [ ] **Step 4: Run them and watch them pass**

Run: `pytest tests/test_refresh_fixture.py -q -m spatial`
Expected: 7 passed

Confirm the artifact is actually tracked — `.gitignore` exceptions fail silently:

```bash
git add tests/fixtures/data/forcing.nc
git ls-files --error-unmatch tests/fixtures/data/forcing.nc
```

Expected: the path echoed, exit 0. **Do not use `git check-ignore -v` for this.** With `-v`
it reports the *matching* pattern — including a negated one — and exits **0**, so a correctly
un-ignored file looks exactly like a failure. Only the bare `git check-ignore` exits 1 on a
non-ignored path, and `git ls-files --error-unmatch` answers the question actually being
asked, which is whether git is tracking the file.

- [ ] **Step 5: Commit**

```bash
git add scripts/make_fixture.py tests/fixtures/data/ tests/test_refresh_fixture.py .gitignore
git commit -m "A fixture built by the code it tests"
```

---

### Task 6: The import boundary, in both directions

**Files:**
- Create: `tests/test_refresh_isolation.py`

**Interfaces:** consumes nothing, produces nothing. This task exists so C§10 clause 8 fails when it should.

- [ ] **Step 1: Write the test**

```python
# tests/test_refresh_isolation.py
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
```

- [ ] **Step 2: Run it, then prove it can fail**

Run: `pytest tests/test_refresh_isolation.py -q`
Expected: 2 passed — it guards a property that already holds.

**A test that has never been red is not evidence.** Temporarily add `from seagarden_dst import api` to `artifact/grid.py`, re-run, confirm `test_refresh_imports_nothing_from_the_core` fails and names `grid.py`, then remove the line and re-run to green.

- [ ] **Step 3: Commit**

```bash
git add tests/test_refresh_isolation.py
git commit -m "The refresh boundary holds in both directions"
```

---

### Task 7: Two install states, so two CI jobs

**Files:**
- Modify: `pyproject.toml`, `.github/workflows/ci.yml`

C§11: the existing job installs `.[app,dev]` and proves the isolation; a new job installs `.[spatial,dev]` and runs the refresh tests. **A second job alone is not sufficient** — `testpaths` means the existing job still *collects* the fixture tests, which import `xarray`, failing at collection rather than skipping and taking both matrix legs red on every pull request. The marker and the job are two halves of one mechanism.

- [ ] **Step 1: Add the marker, the default deselection, and the direct dependency**

In `[tool.pytest.ini_options]`, add to `markers`:

```toml
  "spatial: needs the spatial extra (xarray, netCDF); deselected by default — run with -m spatial",
```

and extend `addopts`:

```toml
addopts = "-m 'not engines and not e2e and not spatial'"
```

In the `spatial` extra, declare the NetCDF engine directly rather than inheriting it through `copernicusmarine`. C§11 leaves this to the plan; take the explicit side — relying on a transitive dependency for a first-class capability is what breaks quietly on a version bump:

```toml
  "h5netcdf>=1.4",   # NetCDF4 engine. Declared directly, not inherited via copernicusmarine.
```

**Add both new packages to `[tool.setuptools] packages`.** That list has been explicit
since `9ca82ac`, not `find:`, so a subpackage that is created but not listed is absent from
every built wheel:

```toml
packages = [
  "seagarden_dst",
  "seagarden_dst.artifact",   # Manifest + GridSpec + the reader: package D imports these
  "seagarden_dst.refresh",
  "seagarden_dst.paramdata",
]
```

This is the same defect `tests/test_packaging.py` was written for one release earlier — the
wheel carried no parameter YAML at all, and only the editable install CI uses hid it. Add an
assertion there in the same step, so the next subpackage cannot repeat it:

```python
def test_every_source_subpackage_is_declared():
    """A subpackage created but not listed is missing from every wheel, and the
    editable install CI uses cannot see the difference."""
    declared = set(_pyproject()["tool"]["setuptools"]["packages"])
    src = REPO / "src" / "seagarden_dst"
    found = {
        f"seagarden_dst.{d.name}"
        for d in src.iterdir()
        if d.is_dir() and (d / "__init__.py").is_file()
    }
    assert found <= declared, f"not in [tool.setuptools] packages: {sorted(found - declared)}"
```

- [ ] **Step 2: Verify the default run excludes the spatial tests**

Run: `pytest -q`
Expected: the pre-existing count — **153 on `main` at `9ca82ac`**, and re-measure rather than trusting that number, it moved 120 → 137 → 143 → 153 in three days — plus Tasks 1–3 and Task 6, and **none** of the `spatial`-marked ones. There must be no collection error mentioning `xarray`.

- [ ] **Step 3: Add the second CI job**

```yaml
  # C§10 clause 8 is only meaningful in an install WITHOUT `spatial`, while C§7's
  # fixture tests need one WITH it. Two requirements pulling opposite ways, so two
  # jobs: the `test` job above proves the isolation, this one reads the fixture.
  spatial:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.11", "3.13"]
    steps:
      - uses: actions/checkout@v5
      - uses: actions/setup-python@v6
        with:
          python-version: ${{ matrix.python-version }}
          cache: pip
          cache-dependency-path: pyproject.toml

      # `,dev` is not optional: `spatial` declares no test runner, so
      # `pip install -e ".[spatial]"` then `pytest` fails with "command not found"
      # — installing everything needed to read the fixture and nothing to test it.
      - name: Install
        run: |
          python -m pip install --upgrade pip
          pip install -e ".[spatial,dev]"

      - name: Refresh tests
        run: pytest -q -m spatial
```

- [ ] **Step 4: Run both selections locally**

Run: `pytest -q` then `pytest -q -m spatial`
Expected: both green. Run `ruff check .` too.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .github/workflows/ci.yml
git commit -m "Two install states, so two CI jobs and a marker"
```

---

## Review record

A four-lens adversarial review of this plan raised 31 findings; 19 survived refutation and
collapsed to 10 distinct defects, all fixed above. Recorded because the defects are more
interesting than the fixes, and because two of them are patterns worth watching for in C-b
and C-c.

**Three were blocking.** Two were found independently by three or four lenses.

1. **A pytest marker cannot stop a collection-time import.** C§11 prescribes "a `spatial`
   marker deselected by default" as the mechanism that keeps the `.[app,dev]` job from
   collecting the fixture tests. The plan implemented exactly that — and it does not work:
   `-m` filters *after* collection, and collection imports the module. Verified empirically:
   a marked module whose import fails yields `Interrupted: 1 error during collection`, not a
   skip. `pytest.importorskip` before the import is what actually implements C§11's
   requirement; the marker only implements its *wording*.
2. **The orphan-layer test could never reach the validator it named.** It built the orphan by
   deleting `light_attenuation_k`'s derivation, which also unclaims that variable — so the
   claimed-exactly-once validator, defined earlier, fired first with a message containing no
   "reachable". The natural repair (loosen `match=`) would have left C§4.4's fourth rule with
   no discriminating case, which is precisely what done-when clause 12 forbids.
3. **`_fsync` opened the file read-only.** On Windows `os.fsync` maps to `FlushFileBuffers`
   and needs write access; verified on the development machine as
   `OSError [Errno 9] Bad file descriptor`. Every `write_pair` call would have raised before
   reaching the interruption hook, so all of Task 4 and the whole of Task 5 were dead.

**The pattern in 1 and 2** is a check that looks like it proves more than it does: a marker
that appears to prevent a failure it cannot reach, and a test that appears to guard a rule it
never triggers. When writing C-b, ask of every new validator: *if I deleted this, which test
goes red?* If the answer is "one that would also go red for another reason", the rule is
untested.

**One refutation worth keeping.** A lens argued the fixture's boolean `valid` could not
survive NetCDF, which has no native bool type. Measured instead: h5netcdf round-trips
`dtype == bool` correctly. The concern was real and the conclusion was wrong, which is why
findings are verified rather than applied.

## Self-review

**Spec coverage.** C§3.1 → Task 1. C§3.2's variable set and dtypes → Task 3 (`ARTIFACT_VARIABLES`) and Tasks 4–5 (shapes, bool `valid`). C§4.1 → Tasks 2–3. C§4.2 (`artifact_sha256`, `absent`) → Tasks 3–4. C§4.3 (`extra="forbid"`, validators at load) → Tasks 2–3. C§4.4's four rules → Task 3, one negative test each. C§6 and C§6.1's checksum rows → Task 4. C§7's fixture and its test list → Tasks 3–5. C§10 clause 8 → Task 6. C§11's CI bullet, including the `h5netcdf` question it defers to the plan → Task 7.

**Deliberately out of scope,** each named in Scope so it is not mistaken for a gap: clauses 1, 5, 6, 9, 11 (C-b) and 7 (C-c). Clause 8's *test* lands here in Task 6; the driver it will eventually guard is C-b's.

**Interface consistency.** `GridSpec` (Task 1) is consumed by `Manifest.grid` (Task 3) and the fixture (Task 5). `Archive`, `LayerProvenance`, `Derivation`, `DerivationInput`, `AbsentField` (Task 2) are consumed by `Manifest` (Task 3). `Manifest` is consumed by `write_pair`/`load_pair` (Task 4) and by every fixture test (Task 5). `sha256_of` is used by Task 4's tests and by `write_pair` itself. `ARTIFACT_VARIABLES` is defined in Task 3 and used in Tasks 3 and 5. No name appears in a later task that an earlier one does not define.

**One deliberate duplication to watch.** Task 3 defines the reference manifest builder in the test module; Task 4 step 1 moves it into `conftest.py` and has Task 3's module import it. If you execute Task 3 and stop, the builder is in the wrong place — that is expected mid-plan, not a defect, but do not leave it there.

**Known soft spot.** Task 5 specifies the generator's structure exhaustively but does not give its 60 lines of `np.linspace` verbatim, because the synthetic values are arbitrary and writing them into a plan adds no information. Every structural decision is pinned in the list above it.
