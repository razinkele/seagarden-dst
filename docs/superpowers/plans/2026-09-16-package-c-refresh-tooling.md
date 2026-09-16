# Package C — Refresh Tooling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the tooling that produces the forcing artifact package D reads — a NetCDF4 file of per-year monthly Baltic fields, an attested provenance manifest, an archive route, a runbook, a source-probe job and a committed test fixture.

**Architecture:** A thin layer-plugin package under `src/seagarden_dst/refresh/`, with `scripts/refresh_layers.py` as a CLI entry point. Each source is one module satisfying a three-method `Layer` protocol (`probe`, `build`, `provenance`); a driver merges them onto one grid, computes a single `valid` mask, and writes artifact and manifest as a checksum-linked pair. Nothing in `refresh/` may be imported by the model core — that isolation is what keeps the `spatial` extra build-time only.

**Tech Stack:** Python 3.11+, xarray + h5netcdf/netCDF4, `copernicusmarine` 2.4, rioxarray/rasterio for the EMODnet regrid, Pydantic v2 for the manifest, pytest.

**Spec:** `docs/superpowers/specs/2026-09-15-package-c-refresh-tooling-design.md` (read it — this plan argues from it and does not restate its reasoning)

## Global Constraints

- **Python `>=3.11`.** CI runs 3.11 and 3.13; both must pass.
- **Nothing in `src/seagarden_dst/refresh/` may be imported by any core module** (`forcing`, `growth`, `suitability`, `nutrients`, `shellfish`, `api`, `params`, `scenarios`, `contracts`, `calibration`). Task 6 adds the test that enforces it.
- **Grid is native, not coarsened:** 0.016666° lat × 0.027777° lon, extent 53.5–60.0 N, 9.5–27.0 E, 390 × 630 = 245,700 cells. Coarsening land-masks Tagalaht — see spec C§3.1.
- **Format is NetCDF4 + zlib complevel 4**, float32, fixed filenames `forcing.nc` and `manifest.json`, located via `$SEAGARDEN_DATA_DIR` defaulting to `data/`.
- **Baselines:** forcing `2016–2025`; waves `2023–2025`. Ten years carried, **nine usable for wrapping windows**.
- **`ARTIFACT_SCHEMA_VERSION = 1`.**
- **Every number in a docstring or comment must be one you measured**, not one you expect. This repository has spent three packages removing figures that were true when written.
- Run the suite with `micromamba run -n shiny python -m pytest -q` and lint with `micromamba run -n shiny ruff check .`. Do **not** create a venv.
- Commit after every task. Never commit `data/`, only `tests/fixtures/data/`.

---

## File Structure

| Path | Responsibility |
|---|---|
| `src/seagarden_dst/refresh/__init__.py` | Package marker; re-exports `build_artifact`, `probe_all` |
| `src/seagarden_dst/refresh/manifest.py` | Pydantic models: `GridSpec`, `ArchiveState`, `LayerProvenance`, `Derivation`, `AbsentField`, `Manifest` |
| `src/seagarden_dst/refresh/grid.py` | `BALTIC_GRID` constant and axis construction |
| `src/seagarden_dst/refresh/writer.py` | sha256, atomic pair write, verified read |
| `src/seagarden_dst/refresh/layers/base.py` | `Layer` protocol, `ProbeResult` |
| `src/seagarden_dst/refresh/layers/__init__.py` | `REGISTRY` — the single source list |
| `src/seagarden_dst/refresh/layers/copernicus_phy.py` | salinity, temperature |
| `src/seagarden_dst/refresh/layers/copernicus_bgc.py` | DIN, DIP, and k from **daily** `zsd` |
| `src/seagarden_dst/refresh/layers/copernicus_wav.py` | streamed monthly p95 of hourly `VHM0` |
| `src/seagarden_dst/refresh/layers/emodnet_bathy.py` | depth mean and min |
| `src/seagarden_dst/refresh/driver.py` | build all, merge, `valid` intersection, write |
| `src/seagarden_dst/refresh/fixture.py` | synthetic fixture generation |
| `src/seagarden_dst/refresh/zenodo.py` | deposit and DOI recording |
| `scripts/refresh_layers.py` | CLI: `--probe`, `--fixture`, `--years` |
| `tests/test_refresh_manifest.py` | manifest model rules — **this is §9's provenance test** |
| `tests/test_refresh_writer.py` | atomicity, checksum, torn pair |
| `tests/test_refresh_driver.py` | merge and `valid` intersection, with stub layers |
| `tests/test_refresh_fixture.py` | the committed fixture loads and verifies |
| `tests/test_refresh_isolation.py` | no core module imports `refresh/` |
| `tests/fixtures/data/forcing.nc`, `manifest.json` | committed fixture |
| `docs/runbooks/annual-refresh.md` | the runbook |
| `.github/workflows/source-probe.yml` | scheduled probe |

---

### Task 1: Manifest models

The blocking finding from the spec review lives here: a layer at build time has **no DOI** and is **not** `forbidden`, so the two-state rule cannot be satisfied. Three states, and `pending` is the honest one.

**Files:**
- Create: `src/seagarden_dst/refresh/__init__.py`, `src/seagarden_dst/refresh/manifest.py`
- Test: `tests/test_refresh_manifest.py`

**Interfaces:**
- Produces: `ARTIFACT_SCHEMA_VERSION: int`, `GridSpec`, `ArchiveState`, `LayerProvenance`, `Derivation`, `AbsentField`, `Manifest` — all Pydantic v2 `BaseModel` with `extra="forbid"`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_refresh_manifest.py`:

```python
"""Manifest rules. This module IS the design's section 9 provenance test.

A layer that cannot say where it came from must fail at load, not mid-analysis -
the principle params.py already follows for species parameters.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from seagarden_dst.refresh.manifest import ArchiveState, LayerProvenance


def _layer(**overrides):
    base = dict(
        name="copernicus_phy",
        source="Copernicus Marine Service",
        product_id="BALTICSEA_MULTIYEAR_PHY_003_011",
        dataset_id="cmems_mod_bal_phy_my_P1M-m",
        version="202303",
        retrieved_on="2026-09-16T00:00:00Z",
        licence="CMEMS licence",
        redistribution="allowed",
        variables=["so", "thetao"],
        statistic="monthly mean",
        archive={"status": "pending", "source_url": "https://marine.copernicus.eu/",
                 "unblocked_by": "first Zenodo deposit"},
    )
    base.update(overrides)
    return base


def test_pending_is_a_valid_archive_state():
    """The state every layer of a first real refresh is in.

    Without it the validator cannot be satisfied by anything package C produces: no
    DOI exists before the deposit, and these layers are genuinely redistributable, so
    'forbidden' would be a lie.
    """
    layer = LayerProvenance(**_layer())
    assert layer.archive.status == "pending"


def test_pending_without_a_source_url_is_rejected():
    with pytest.raises(ValidationError, match="source_url"):
        ArchiveState(status="pending", unblocked_by="first deposit")


def test_pending_without_unblocked_by_is_rejected():
    with pytest.raises(ValidationError, match="unblocked_by"):
        ArchiveState(status="pending", source_url="https://example.invalid/")


def test_deposited_requires_a_doi():
    with pytest.raises(ValidationError, match="zenodo_doi"):
        ArchiveState(status="deposited")


def test_forbidden_requires_a_source_url():
    with pytest.raises(ValidationError, match="source_url"):
        ArchiveState(status="forbidden")


def test_an_unknown_archive_state_is_rejected():
    with pytest.raises(ValidationError):
        ArchiveState(status="probably-fine", source_url="https://example.invalid/")


def test_a_redistributable_layer_may_not_claim_the_forbidden_marker():
    """The marker is not an escape hatch for clearing the validator.

    Marking a redistributable layer 'forbidden' would pass every other check while
    misdescribing the layer - the exact mis-marked provenance this design exists to
    prevent.
    """
    with pytest.raises(ValidationError, match="redistribution"):
        LayerProvenance(**_layer(
            redistribution="allowed",
            archive={"status": "forbidden", "source_url": "https://example.invalid/"},
        ))


def test_a_non_redistributable_layer_must_carry_the_marker():
    with pytest.raises(ValidationError, match="redistribution"):
        LayerProvenance(**_layer(
            redistribution="forbidden",
            archive={"status": "pending", "source_url": "https://example.invalid/",
                     "unblocked_by": "x"},
        ))


def test_unknown_fields_are_refused():
    with pytest.raises(ValidationError):
        LayerProvenance(**_layer(notes="free text nobody validates"))
```

- [ ] **Step 2: Run it and watch it fail**

```bash
micromamba run -n shiny python -m pytest tests/test_refresh_manifest.py -q
```

Expected: collection error, `ModuleNotFoundError: No module named 'seagarden_dst.refresh'`.

- [ ] **Step 3: Create the package and the models**

Create `src/seagarden_dst/refresh/__init__.py`:

```python
"""Build-time refresh tooling. NOT imported by the model core.

Everything here runs once a year, writes an artifact, and exits. The tool then reads
that artifact with no network, no credentials and no service call - which is what keeps
it alive on no maintenance budget. `tests/test_refresh_isolation.py` enforces the
direction of that dependency.
"""
```

Create `src/seagarden_dst/refresh/manifest.py`:

```python
"""The provenance manifest, as models rather than as a convention.

Design section 6.3's rules are model validators, so a layer that cannot say where it
came from fails at load rather than mid-analysis - the principle params.py already
follows for species parameters.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

#: Bumped whenever the artifact's shape changes. Package D refuses an unrecognised
#: version and falls back to the placeholder rather than guessing.
ARTIFACT_SCHEMA_VERSION = 1


class GridSpec(BaseModel):
    """The target grid, recorded so a reader never infers it from the data."""

    model_config = ConfigDict(extra="forbid")

    crs: str = "EPSG:4326"
    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float
    lat_step: float
    lon_step: float
    n_lat: int
    n_lon: int


class ArchiveState(BaseModel):
    """Where this layer's bytes are durable, or why they are not yet.

    Three states, not two. Design section 6.3 required either a DOI or a
    `redistribution: forbidden` marker - but at build time no DOI exists, because the
    deposit happens afterwards, and these layers are redistributable, so the marker
    would be a lie. `pending` is the honest third state.
    """

    model_config = ConfigDict(extra="forbid")

    status: Literal["deposited", "forbidden", "pending"]
    zenodo_doi: str | None = None
    source_url: str | None = None
    unblocked_by: str | None = Field(
        default=None, description="What has to happen for this to become 'deposited'."
    )

    @model_validator(mode="after")
    def _each_state_carries_what_it_claims(self) -> ArchiveState:
        if self.status == "deposited" and not self.zenodo_doi:
            raise ValueError("archive status 'deposited' requires zenodo_doi")
        if self.status == "forbidden" and not self.source_url:
            raise ValueError("archive status 'forbidden' requires source_url")
        if self.status == "pending":
            if not self.source_url:
                raise ValueError("archive status 'pending' requires source_url")
            if not self.unblocked_by:
                raise ValueError("archive status 'pending' requires unblocked_by")
        return self


class LayerProvenance(BaseModel):
    """One source layer, and everything needed to fetch it again or cite it."""

    model_config = ConfigDict(extra="forbid")

    name: str
    source: str
    product_id: str
    dataset_id: str
    version: str
    retrieved_on: datetime
    licence: str
    redistribution: Literal["allowed", "forbidden"]
    variables: list[str]
    statistic: str
    archive: ArchiveState

    @model_validator(mode="after")
    def _archive_state_matches_redistribution(self) -> LayerProvenance:
        """The marker is not an escape hatch.

        Marking a redistributable layer 'forbidden' would clear every other check while
        misdescribing the layer. That is the mis-marked provenance this design exists to
        prevent, so the two fields must agree.
        """
        if self.redistribution == "forbidden" and self.archive.status != "forbidden":
            raise ValueError(
                f"{self.name}: redistribution='forbidden' requires archive status "
                f"'forbidden', not {self.archive.status!r}"
            )
        if self.redistribution == "allowed" and self.archive.status == "forbidden":
            raise ValueError(
                f"{self.name}: redistribution='allowed' cannot carry the 'forbidden' "
                "archive marker"
            )
        return self


class Derivation(BaseModel):
    """A field computed from a source variable rather than read from it."""

    model_config = ConfigDict(extra="forbid")

    field: str
    from_variable: str
    relation: str
    note: str | None = None


class AbsentField(BaseModel):
    """A SiteConditions field with no source, recorded so the tool can say so.

    Design section 7 requires the tool to display that surface_par is a placeholder.
    Recording it here means the UI reads data rather than carrying a hardcoded caveat
    that drifts out of step with reality.
    """

    model_config = ConfigDict(extra="forbid")

    field: str
    reason: str
    unblocked_by: str


class Manifest(BaseModel):
    """What the artifact is, where every number in it came from, and what is missing."""

    model_config = ConfigDict(extra="forbid")

    artifact_schema_version: int
    built_on: datetime
    artifact_filename: str
    artifact_sha256: str
    artifact_bytes: int
    synthetic: bool = False
    grid: GridSpec
    #: Per variable, not per artifact - waves use a different baseline from forcing,
    #: and a static layer carries an empty list.
    baselines: dict[str, list[int]]
    layers: list[LayerProvenance]
    derived: list[Derivation] = []
    absent: list[AbsentField] = []

    @model_validator(mode="after")
    def _schema_version_is_recognised(self) -> Manifest:
        if self.artifact_schema_version != ARTIFACT_SCHEMA_VERSION:
            raise ValueError(
                f"artifact_schema_version {self.artifact_schema_version} is not "
                f"{ARTIFACT_SCHEMA_VERSION}; refuse rather than guess the shape"
            )
        return self

    @model_validator(mode="after")
    def _at_least_one_layer(self) -> Manifest:
        if not self.layers:
            raise ValueError("a manifest with no layers attests to nothing")
        return self
```

- [ ] **Step 4: Run the tests**

```bash
micromamba run -n shiny python -m pytest tests/test_refresh_manifest.py -q
micromamba run -n shiny ruff check .
```

Expected: 9 passed, ruff clean.

- [ ] **Step 5: Commit**

```bash
git add src/seagarden_dst/refresh/ tests/test_refresh_manifest.py
git commit -m "Package C: the provenance manifest as models, with three archive states

A layer that cannot say where it came from now fails at load. Three archive
states rather than two: no DOI exists at build time and these layers are
redistributable, so 'forbidden' would be a lie - 'pending' is the honest
state, and it requires a source_url and an unblocked_by note. The marker is
not an escape hatch: redistribution and archive status must agree."
```

---

### Task 2: The atomic pair writer

Section 6.3 asks for artifact and manifest "written atomically as a pair". No filesystem provides that. This task builds what one does.

**Files:**
- Create: `src/seagarden_dst/refresh/writer.py`
- Test: `tests/test_refresh_writer.py`

**Interfaces:**
- Consumes: `Manifest`, `ARTIFACT_SCHEMA_VERSION` from Task 1.
- Produces: `ARTIFACT_NAME: str`, `MANIFEST_NAME: str`, `data_dir() -> Path`, `sha256_of(path: Path) -> str`, `write_pair(ds, manifest_fields: dict, directory: Path) -> Manifest`, `load_verified(directory: Path) -> tuple[Manifest, Path]`, `ArtifactMismatch(Exception)`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_refresh_writer.py`:

```python
"""Artifact and manifest are a pair, and a torn pair must be refused."""

from __future__ import annotations

import json

import pytest
import xarray as xr
import numpy as np

from seagarden_dst.refresh.manifest import ARTIFACT_SCHEMA_VERSION
from seagarden_dst.refresh.writer import (
    ARTIFACT_NAME,
    MANIFEST_NAME,
    ArtifactMismatch,
    load_verified,
    sha256_of,
    write_pair,
)


def _tiny_dataset():
    return xr.Dataset(
        {"salinity_psu": (("latitude", "longitude"), np.full((2, 2), 7.0, dtype="float32"))},
        coords={"latitude": [55.0, 55.1], "longitude": [20.0, 20.1]},
    )


def _fields():
    return dict(
        artifact_schema_version=ARTIFACT_SCHEMA_VERSION,
        built_on="2026-09-16T00:00:00Z",
        artifact_filename=ARTIFACT_NAME,
        synthetic=True,
        grid=dict(lat_min=55.0, lat_max=55.1, lon_min=20.0, lon_max=20.1,
                  lat_step=0.1, lon_step=0.1, n_lat=2, n_lon=2),
        baselines={"salinity_psu": [2024]},
        layers=[dict(
            name="stub", source="stub", product_id="P", dataset_id="D", version="1",
            retrieved_on="2026-09-16T00:00:00Z", licence="none",
            redistribution="allowed", variables=["salinity_psu"],
            statistic="monthly mean",
            archive={"status": "pending", "source_url": "https://example.invalid/",
                     "unblocked_by": "first deposit"},
        )],
    )


def test_write_pair_then_load_verified_round_trips(tmp_path):
    manifest = write_pair(_tiny_dataset(), _fields(), tmp_path)
    loaded, artifact = load_verified(tmp_path)
    assert loaded.artifact_sha256 == manifest.artifact_sha256
    assert artifact.name == ARTIFACT_NAME
    assert loaded.artifact_bytes == artifact.stat().st_size


def test_the_manifest_records_the_artifacts_checksum(tmp_path):
    manifest = write_pair(_tiny_dataset(), _fields(), tmp_path)
    assert manifest.artifact_sha256 == sha256_of(tmp_path / ARTIFACT_NAME)


def test_a_torn_pair_is_refused_rather_than_read(tmp_path):
    """The failure mode the manifest-last ordering exists to make detectable.

    Simulated by replacing the artifact after the pair was written, which is what an
    interrupt between the two renames leaves behind: a live artifact the manifest on
    disk does not describe.
    """
    write_pair(_tiny_dataset(), _fields(), tmp_path)
    other = _tiny_dataset()
    other["salinity_psu"] += 1.0
    other.to_netcdf(tmp_path / ARTIFACT_NAME)

    with pytest.raises(ArtifactMismatch, match="checksum"):
        load_verified(tmp_path)


def test_nothing_is_written_when_the_manifest_is_invalid(tmp_path):
    """A part-way failure must leave the directory untouched, not half-built."""
    bad = _fields()
    bad["layers"] = []  # a manifest with no layers attests to nothing

    with pytest.raises(Exception):
        write_pair(_tiny_dataset(), bad, tmp_path)

    assert not (tmp_path / ARTIFACT_NAME).exists()
    assert not (tmp_path / MANIFEST_NAME).exists()
    assert list(tmp_path.iterdir()) == []


def test_an_existing_pair_survives_a_failed_rebuild(tmp_path):
    """Section 7: a refresh that fails part-way leaves the previous pair valid."""
    first = write_pair(_tiny_dataset(), _fields(), tmp_path)

    bad = _fields()
    bad["layers"] = []
    with pytest.raises(Exception):
        write_pair(_tiny_dataset(), bad, tmp_path)

    loaded, _ = load_verified(tmp_path)
    assert loaded.artifact_sha256 == first.artifact_sha256


def test_the_manifest_is_readable_json(tmp_path):
    write_pair(_tiny_dataset(), _fields(), tmp_path)
    payload = json.loads((tmp_path / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert payload["artifact_filename"] == ARTIFACT_NAME
    assert payload["layers"][0]["archive"]["status"] == "pending"
```

- [ ] **Step 2: Run it and watch it fail**

```bash
micromamba run -n shiny python -m pytest tests/test_refresh_writer.py -q
```

Expected: `ModuleNotFoundError: No module named 'seagarden_dst.refresh.writer'`.

- [ ] **Step 3: Write the writer**

Create `src/seagarden_dst/refresh/writer.py`:

```python
"""Writing the pair, and refusing to read a torn one.

Design section 6.3 asks for the artifact and manifest to be "written atomically as a
pair". No filesystem provides that: os.replace is atomic per file, there is no two-file
equivalent, and on Windows there is no directory-swap trick either. Implemented
literally the requirement cannot be met; implemented loosely it silently is not.

What a filesystem does provide, and what this module implements: the manifest carries
the artifact's sha256, both are written to temp names on the SAME filesystem, and the
manifest is renamed LAST. Between the two renames the old manifest's checksum no longer
matches the artifact on disk, so a reader refuses rather than reading new data under old
provenance. The exposure is one rename and the failure is loud.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import xarray as xr

from .manifest import Manifest

ARTIFACT_NAME = "forcing.nc"
MANIFEST_NAME = "manifest.json"

#: zlib level 4 - package B measured NetCDF4+zlib4 smaller than Zarr at every
#: resolution and temporal combination it tried.
_ENCODING_BASE = {"zlib": True, "complevel": 4, "dtype": "float32"}


class ArtifactMismatch(RuntimeError):
    """The manifest does not describe the artifact sitting beside it."""


def data_dir() -> Path:
    """Where the artifact lives. $SEAGARDEN_DATA_DIR, else ./data."""
    return Path(os.environ.get("SEAGARDEN_DATA_DIR", "data"))


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _fsync(path: Path) -> None:
    with open(path, "rb") as handle:
        os.fsync(handle.fileno())


def write_pair(ds: xr.Dataset, manifest_fields: dict, directory: Path) -> Manifest:
    """Write artifact and manifest so that a reader can never see a crossed pair.

    `manifest_fields` carries everything except artifact_sha256 and artifact_bytes,
    which only exist once the artifact is on disk.

    Raises before touching anything live if the manifest does not validate, so a failed
    build leaves the previous pair intact.
    """
    directory.mkdir(parents=True, exist_ok=True)
    tmp_artifact = directory / (ARTIFACT_NAME + ".tmp")
    tmp_manifest = directory / (MANIFEST_NAME + ".tmp")

    try:
        encoding = {name: dict(_ENCODING_BASE) for name in ds.data_vars}
        ds.to_netcdf(tmp_artifact, engine="h5netcdf", encoding=encoding)
        _fsync(tmp_artifact)

        manifest = Manifest(
            artifact_sha256=sha256_of(tmp_artifact),
            artifact_bytes=tmp_artifact.stat().st_size,
            **manifest_fields,
        )
        tmp_manifest.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
        _fsync(tmp_manifest)
    except BaseException:
        tmp_artifact.unlink(missing_ok=True)
        tmp_manifest.unlink(missing_ok=True)
        raise

    # Artifact first, manifest last. Reversed, a new manifest over an old artifact
    # would look internally consistent while attesting to data that is not there.
    os.replace(tmp_artifact, directory / ARTIFACT_NAME)
    os.replace(tmp_manifest, directory / MANIFEST_NAME)
    return manifest


def load_verified(directory: Path) -> tuple[Manifest, Path]:
    """Load the manifest and prove it describes the artifact beside it."""
    manifest_path = directory / MANIFEST_NAME
    artifact_path = directory / ARTIFACT_NAME
    if not manifest_path.exists():
        raise FileNotFoundError(f"no manifest at {manifest_path}")
    if not artifact_path.exists():
        raise FileNotFoundError(f"no artifact at {artifact_path}")

    manifest = Manifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    actual = sha256_of(artifact_path)
    if actual != manifest.artifact_sha256:
        raise ArtifactMismatch(
            f"artifact checksum {actual} does not match the manifest's "
            f"{manifest.artifact_sha256}: the pair is torn, refuse rather than read it"
        )
    return manifest, artifact_path
```

- [ ] **Step 4: Run the tests**

```bash
micromamba run -n shiny python -m pytest tests/test_refresh_writer.py -q
micromamba run -n shiny ruff check .
```

Expected: 6 passed. If `h5netcdf` is missing, install the spatial extra first:
`micromamba run -n shiny pip install -e ".[spatial]"`.

- [ ] **Step 5: Commit**

```bash
git add src/seagarden_dst/refresh/writer.py tests/test_refresh_writer.py
git commit -m "Package C: the atomic pair write that a filesystem can actually provide

Section 6.3's 'written atomically as a pair' has no filesystem equivalent.
The manifest carries the artifact's sha256, both go to temp names on the same
filesystem, and the manifest is renamed last - so a torn pair is detected and
refused rather than read as new data under old provenance. A build that fails
validation leaves the previous pair untouched."
```

---

### Task 3: Grid and the layer protocol

**Files:**
- Create: `src/seagarden_dst/refresh/grid.py`, `src/seagarden_dst/refresh/layers/__init__.py`, `src/seagarden_dst/refresh/layers/base.py`
- Test: `tests/test_refresh_driver.py` (created here, extended in Task 4)

**Interfaces:**
- Consumes: `GridSpec` from Task 1.
- Produces: `BALTIC_GRID: GridSpec`, `axes(grid) -> tuple[np.ndarray, np.ndarray]`, `Layer` protocol with `name: str`, `probe() -> ProbeResult`, `build(grid, workdir) -> xr.Dataset`, `provenance() -> LayerProvenance`; `ProbeResult(name, reachable, detail)`; `REGISTRY: list[Layer]`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_refresh_driver.py`:

```python
"""The grid, the seam every source implements, and the registry."""

from __future__ import annotations

import numpy as np
import xarray as xr

from seagarden_dst.refresh.grid import BALTIC_GRID, axes
from seagarden_dst.refresh.layers.base import Layer, ProbeResult


def test_the_shipped_grid_is_native_resolution_over_the_stated_extent():
    """Package B: coarsening land-masks Tagalaht, the only published anchor there is."""
    assert BALTIC_GRID.lat_min == 53.5 and BALTIC_GRID.lat_max == 60.0
    assert BALTIC_GRID.lon_min == 9.5 and BALTIC_GRID.lon_max == 27.0
    assert BALTIC_GRID.n_lat == 390 and BALTIC_GRID.n_lon == 630
    assert BALTIC_GRID.n_lat * BALTIC_GRID.n_lon == 245_700


def test_axes_match_the_declared_shape():
    lat, lon = axes(BALTIC_GRID)
    assert lat.size == BALTIC_GRID.n_lat
    assert lon.size == BALTIC_GRID.n_lon
    assert np.isclose(lat[1] - lat[0], BALTIC_GRID.lat_step)


def test_a_stub_satisfies_the_layer_protocol():
    """The point of the seam: a source the driver has never heard of must work."""

    class StubLayer:
        name = "stub"

        def probe(self):
            return ProbeResult(name="stub", reachable=True, detail="ok")

        def build(self, grid, workdir):
            return xr.Dataset()

        def provenance(self):
            raise NotImplementedError

    assert isinstance(StubLayer(), Layer)
```

- [ ] **Step 2: Run it and watch it fail**

```bash
micromamba run -n shiny python -m pytest tests/test_refresh_driver.py -q
```

Expected: `ModuleNotFoundError: No module named 'seagarden_dst.refresh.grid'`.

- [ ] **Step 3: Write the grid and the protocol**

Create `src/seagarden_dst/refresh/grid.py`:

```python
"""The target grid, in one place so widening the extent is one edit.

Native Copernicus resolution, NOT coarsened: package B measured that coarsening to
about 4 km land-masks the cell containing Tagalaht, the only published anchor the
parameterisation has, and PL-lagoon with it. The anchor forces the grid.

The extent covers all six placeholder regions and EXCLUDES the Gulf of Bothnia and the
Gulf of Finland - a scope choice, not a limit of the method.
"""

from __future__ import annotations

import numpy as np

from .manifest import GridSpec

BALTIC_GRID = GridSpec(
    crs="EPSG:4326",
    lat_min=53.5,
    lat_max=60.0,
    lon_min=9.5,
    lon_max=27.0,
    lat_step=0.016666,
    lon_step=0.027777,
    n_lat=390,
    n_lon=630,
)


def axes(grid: GridSpec) -> tuple[np.ndarray, np.ndarray]:
    """The latitude and longitude cell centres, as float64 for coordinate exactness."""
    lat = grid.lat_min + np.arange(grid.n_lat, dtype="float64") * grid.lat_step
    lon = grid.lon_min + np.arange(grid.n_lon, dtype="float64") * grid.lon_step
    return lat, lon
```

Create `src/seagarden_dst/refresh/layers/base.py`:

```python
"""The seam each source implements.

build() is ONE method, not fetch() then normalise(). The obvious split breaks on waves:
about 26 GB cannot be fetched and then normalised, it has to be reduced while streaming,
one month-of-year at a time. Forcing that through a fetch/normalise seam would contort
every other layer to accommodate the one that cannot use it. Each layer decides
internally whether it streams; the driver sees only a dataset.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

import xarray as xr

from ..manifest import GridSpec, LayerProvenance


@dataclass(frozen=True)
class ProbeResult:
    """Does this source still exist and answer? Metadata only, never bulk transfer."""

    name: str
    reachable: bool
    detail: str


@runtime_checkable
class Layer(Protocol):
    name: str

    def probe(self) -> ProbeResult: ...

    def build(self, grid: GridSpec, workdir: Path) -> xr.Dataset: ...

    def provenance(self) -> LayerProvenance: ...
```

Create `src/seagarden_dst/refresh/layers/__init__.py`:

```python
"""The registry - the source list exists here and nowhere else.

The driver and the source-probe job both read it, so a layer cannot be added to one
and forgotten in the other.
"""

from __future__ import annotations

from .base import Layer, ProbeResult

#: Populated as each layer lands. Kept as a function rather than a module-level list so
#: importing the registry never imports copernicusmarine.
def registry() -> list[Layer]:
    from .copernicus_bgc import CopernicusBGC
    from .copernicus_phy import CopernicusPHY
    from .copernicus_wav import CopernicusWAV
    from .emodnet_bathy import EMODnetBathymetry

    return [CopernicusPHY(), CopernicusBGC(), CopernicusWAV(), EMODnetBathymetry()]


__all__ = ["Layer", "ProbeResult", "registry"]
```

> **Note for the implementer:** `registry()` will fail to import until Tasks 7–10 land. That is intentional and no test calls it before Task 10.

- [ ] **Step 4: Run the tests**

```bash
micromamba run -n shiny python -m pytest tests/test_refresh_driver.py -q
micromamba run -n shiny ruff check .
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/seagarden_dst/refresh/grid.py src/seagarden_dst/refresh/layers/ tests/test_refresh_driver.py
git commit -m "Package C: the target grid and the Layer seam

Grid is native resolution over 53.5-60.0N, 9.5-27.0E - 245,700 cells - because
package B measured that coarsening land-masks Tagalaht. build() is one method
rather than fetch-then-normalise, because the wave layer must reduce while
streaming and the other three should not be contorted to match it."
```

---

### Task 4: The driver, and the single validity field

The artifact has **two** validity masks — Copernicus land-masking at 2 km and EMODnet coverage at ~115 m — and they disagree at the coastline, which is where every farm is. This task makes the disagreement explicit.

**Files:**
- Create: `src/seagarden_dst/refresh/driver.py`
- Modify: `tests/test_refresh_driver.py`

**Interfaces:**
- Consumes: `BALTIC_GRID`, `axes`, `Layer` (Task 3); `write_pair`, `data_dir` (Task 2); manifest models (Task 1).
- Produces: `merge_layers(datasets: list[xr.Dataset]) -> xr.Dataset`, `add_valid_field(ds: xr.Dataset, contributing: list[str]) -> xr.Dataset`, `build_artifact(layers, grid, years, wave_years, directory, workdir, *, synthetic=False) -> Manifest`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_refresh_driver.py`:

```python
from seagarden_dst.refresh.driver import add_valid_field, merge_layers


def _grid_da(values, name):
    return xr.DataArray(
        np.array(values, dtype="float32"),
        dims=("latitude", "longitude"),
        coords={"latitude": [55.0, 55.1], "longitude": [20.0, 20.1]},
        name=name,
    )


def test_merge_layers_joins_on_the_shared_grid():
    a = _grid_da([[7.0, 7.1], [7.2, 7.3]], "salinity_psu").to_dataset()
    b = _grid_da([[9.0, 9.1], [9.2, 9.3]], "depth_mean_m").to_dataset()
    merged = merge_layers([a, b])
    assert set(merged.data_vars) == {"salinity_psu", "depth_mean_m"}
    assert merged.sizes == {"latitude": 2, "longitude": 2}


def test_valid_is_the_intersection_of_disagreeing_masks():
    """Two sources, two masks, and they disagree at the coastline.

    Copernicus land-masking is on the 2 km model grid; EMODnet bathymetry coverage is an
    independent product at about 115 m. A cell can be wet in one and absent in the
    other. Without an explicit intersection, a downstream reader picks whichever
    variable it happened to look at - and a NaN depth reaching api.select_method turns
    into a confident UNSUITABLE verdict rather than UNKNOWN.
    """
    nan = float("nan")
    forcing = _grid_da([[7.0, 7.1], [nan, 7.3]], "salinity_psu").to_dataset()
    depth = _grid_da([[9.0, nan], [9.2, 9.3]], "depth_mean_m").to_dataset()

    merged = add_valid_field(merge_layers([forcing, depth]),
                             ["salinity_psu", "depth_mean_m"])

    assert merged["valid"].dtype == bool
    assert merged["valid"].values.tolist() == [[True, False], [False, True]]
    assert merged["valid"].attrs["contributing"] == "salinity_psu,depth_mean_m"


def test_valid_is_false_wherever_any_contributing_layer_is_absent():
    nan = float("nan")
    a = _grid_da([[1.0, 1.0], [1.0, 1.0]], "salinity_psu").to_dataset()
    b = _grid_da([[nan, nan], [nan, nan]], "depth_mean_m").to_dataset()
    merged = add_valid_field(merge_layers([a, b]), ["salinity_psu", "depth_mean_m"])
    assert not merged["valid"].values.any()
```

- [ ] **Step 2: Run it and watch it fail**

```bash
micromamba run -n shiny python -m pytest tests/test_refresh_driver.py -q
```

Expected: `ImportError: cannot import name 'add_valid_field'`.

- [ ] **Step 3: Write the driver**

Create `src/seagarden_dst/refresh/driver.py`:

```python
"""Build every layer, merge onto one grid, attest the result, write the pair.

A single layer failing takes the whole refresh with it. A missing variable quietly
defaulting is the unmarked-provenance hazard this project has removed elsewhere, and it
would be worse here because the manifest would attest to a completeness the artifact
lacks.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import xarray as xr

from .grid import BALTIC_GRID
from .manifest import ARTIFACT_SCHEMA_VERSION, AbsentField, Derivation, GridSpec, Manifest
from .writer import ARTIFACT_NAME, write_pair

#: Fields with no source in any integrated product. Recorded in the manifest so section
#: 7's display requirement reads from data rather than a hardcoded caveat that drifts.
ABSENT_FIELDS = [
    AbsentField(
        field="surface_par",
        reason=(
            "No integrated product carries PAR in any form. The Copernicus Baltic BGC "
            "reanalysis has no PAR variable and no kd490."
        ),
        unblocked_by="a PAR source outside the current layer set",
    )
]

DERIVED_FIELDS = [
    Derivation(
        field="light_attenuation_k",
        from_variable="zsd",
        relation="k = 1.7 / z_SD (Poole-Atkins)",
        note=(
            "Computed from DAILY zsd and then averaged over the month. k is non-linear "
            "in its source, so mean(1.7/z_daily) is not 1.7/mean(z_monthly); by Jensen's "
            "inequality the monthly-input route runs systematically low, which "
            "over-estimates PAR at depth and biases growth optimistic."
        ),
    )
]


def merge_layers(datasets: list[xr.Dataset]) -> xr.Dataset:
    """Join every layer's variables onto the shared grid."""
    if not datasets:
        raise ValueError("no layers produced a dataset; refuse rather than write an empty artifact")
    return xr.merge(datasets, join="exact", combine_attrs="drop_conflicts")


def add_valid_field(ds: xr.Dataset, contributing: list[str]) -> xr.Dataset:
    """One explicit validity mask, because the sources disagree at the coastline.

    Copernicus land-masking and EMODnet coverage are independent products at different
    resolutions. Rather than let a reader infer validity from whichever variable it
    looked at, the intersection is written once and named.
    """
    missing = [name for name in contributing if name not in ds.data_vars]
    if missing:
        raise KeyError(f"cannot build the valid mask: {missing} absent from the artifact")

    valid = None
    for name in contributing:
        here = ds[name].notnull()
        # Collapse any non-spatial dimensions: a cell is valid only if it has data
        # for every year and month, not merely for one of them.
        extra = [d for d in here.dims if d not in ("latitude", "longitude")]
        if extra:
            here = here.all(dim=extra)
        valid = here if valid is None else (valid & here)

    valid.attrs["contributing"] = ",".join(contributing)
    valid.attrs["long_name"] = "cell has data in every contributing layer"
    out = ds.copy()
    out["valid"] = valid
    return out


def build_artifact(
    layers,
    grid: GridSpec,
    years: list[int],
    wave_years: list[int],
    directory: Path,
    workdir: Path,
    *,
    synthetic: bool = False,
) -> Manifest:
    """Run every layer, merge, attest and write. All or nothing."""
    datasets = []
    provenances = []
    for layer in layers:
        datasets.append(layer.build(grid, workdir))
        provenances.append(layer.provenance())

    merged = add_valid_field(
        merge_layers(datasets),
        ["salinity_psu", "depth_mean_m"],
    )

    baselines = {
        "salinity_psu": years,
        "temp_c": years,
        "din_umol_l": years,
        "dip_umol_l": years,
        "light_attenuation_k": years,
        "significant_wave_m": wave_years,
        # Static layers carry an empty list - they have no years, and omitting the key
        # would be indistinguishable from forgetting it.
        "depth_mean_m": [],
        "depth_min_m": [],
    }

    return write_pair(
        merged,
        dict(
            artifact_schema_version=ARTIFACT_SCHEMA_VERSION,
            built_on=datetime.now(timezone.utc),
            artifact_filename=ARTIFACT_NAME,
            synthetic=synthetic,
            grid=grid,
            baselines=baselines,
            layers=provenances,
            derived=DERIVED_FIELDS,
            absent=ABSENT_FIELDS,
        ),
        directory,
    )
```

> **Note:** `datetime.now(timezone.utc)` is fine here — this is production code, not a workflow script.

- [ ] **Step 4: Run the tests**

```bash
micromamba run -n shiny python -m pytest tests/test_refresh_driver.py -q
micromamba run -n shiny ruff check .
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/seagarden_dst/refresh/driver.py tests/test_refresh_driver.py
git commit -m "Package C: the driver, and one explicit validity mask

The artifact has two validity masks - Copernicus land-masking at 2 km and
EMODnet coverage at ~115 m - and they disagree at the coastline, where every
farm is. The driver writes their intersection as an explicit 'valid' field
rather than letting a reader infer validity from whichever variable it looked
at. A cell is valid only where every contributing layer has data for every
year and month."
```

---

### Task 5: The synthetic fixture, and section 9's provenance test

**Files:**
- Create: `src/seagarden_dst/refresh/fixture.py`, `tests/test_refresh_fixture.py`
- Create (generated, committed): `tests/fixtures/data/forcing.nc`, `tests/fixtures/data/manifest.json`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: `build_artifact`, `add_valid_field` (Task 4); `load_verified` (Task 2).
- Produces: `FIXTURE_DIR: Path`, `synthetic_dataset(n_lat=3, n_lon=3, years=(2024, 2025)) -> xr.Dataset`, `write_fixture(directory: Path) -> Manifest`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_refresh_fixture.py`:

```python
"""The committed fixture, and the provenance test that runs against it.

Synthetic values, real structure. Committing real Copernicus values would raise a
redistribution question package C should not answer implicitly, and regenerating a
real fixture would need network and credentials - which makes it the kind of artifact
that rots.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from seagarden_dst.refresh.writer import ArtifactMismatch, load_verified

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "data"


def test_the_committed_fixture_loads_and_verifies():
    """Section 9's provenance test. Every rule in manifest.py runs here."""
    manifest, artifact = load_verified(FIXTURE_DIR)
    assert manifest.synthetic is True
    assert artifact.exists()


def test_every_fixture_layer_declares_where_it_came_from():
    manifest, _ = load_verified(FIXTURE_DIR)
    assert manifest.layers, "a manifest with no layers attests to nothing"
    for layer in manifest.layers:
        assert layer.dataset_id and layer.version and layer.licence
        assert layer.archive.status in {"deposited", "forbidden", "pending"}


def test_the_fixture_is_in_the_state_a_first_real_refresh_produces():
    """Pending, not an invented DOI.

    A fixture carrying a fake DOI would test a state package C never reaches: no
    deposit happens inside C, so every layer of a first refresh is 'pending'.
    """
    manifest, _ = load_verified(FIXTURE_DIR)
    assert all(layer.archive.status == "pending" for layer in manifest.layers)
    assert all(layer.archive.source_url for layer in manifest.layers)
    assert all(layer.archive.unblocked_by for layer in manifest.layers)


def test_the_fixture_records_surface_par_as_absent():
    manifest, _ = load_verified(FIXTURE_DIR)
    assert [a.field for a in manifest.absent] == ["surface_par"]


def test_the_fixture_records_the_attenuation_derivation():
    manifest, _ = load_verified(FIXTURE_DIR)
    derived = {d.field: d for d in manifest.derived}
    assert "light_attenuation_k" in derived
    assert derived["light_attenuation_k"].from_variable == "zsd"


def test_static_layers_carry_an_empty_baseline_not_a_missing_key():
    manifest, _ = load_verified(FIXTURE_DIR)
    assert manifest.baselines["depth_mean_m"] == []
    assert manifest.baselines["significant_wave_m"] != manifest.baselines["salinity_psu"]


def test_a_tampered_fixture_is_refused(tmp_path):
    import shutil

    shutil.copy(FIXTURE_DIR / "manifest.json", tmp_path / "manifest.json")
    shutil.copy(FIXTURE_DIR / "forcing.nc", tmp_path / "forcing.nc")
    with open(tmp_path / "forcing.nc", "ab") as handle:
        handle.write(b"\x00")

    with pytest.raises(ArtifactMismatch):
        load_verified(tmp_path)
```

- [ ] **Step 2: Run it and watch it fail**

```bash
micromamba run -n shiny python -m pytest tests/test_refresh_fixture.py -q
```

Expected: `FileNotFoundError: no manifest at .../tests/fixtures/data/manifest.json`.

- [ ] **Step 3: Write the fixture generator**

Create `src/seagarden_dst/refresh/fixture.py`:

```python
"""A small artifact with real structure and invented values.

Written by the SAME writer and manifest code as a production refresh, so the fixture
cannot drift from the thing it stands in for. Its layers are 'pending', which is the
state a first real refresh produces - a fixture carrying a fake DOI would test a state
package C never reaches.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import xarray as xr

from .driver import ABSENT_FIELDS, DERIVED_FIELDS, add_valid_field
from .manifest import ARTIFACT_SCHEMA_VERSION, ArchiveState, GridSpec, LayerProvenance, Manifest
from .writer import ARTIFACT_NAME, write_pair

FIXTURE_GRID = GridSpec(
    lat_min=58.5, lat_max=58.6, lon_min=22.3, lon_max=22.4,
    lat_step=0.05, lon_step=0.05, n_lat=3, n_lon=3,
)
FIXTURE_YEARS = [2024, 2025]
FIXTURE_WAVE_YEARS = [2025]

_PENDING = ArchiveState(
    status="pending",
    source_url="https://marine.copernicus.eu/",
    unblocked_by="the first Zenodo deposit, performed by hand per the refresh runbook",
)


def synthetic_dataset() -> xr.Dataset:
    """Every variable at its correct shape, with values that are obviously invented."""
    lat = FIXTURE_GRID.lat_min + np.arange(3) * FIXTURE_GRID.lat_step
    lon = FIXTURE_GRID.lon_min + np.arange(3) * FIXTURE_GRID.lon_step
    coords = {"year": FIXTURE_YEARS, "month": list(range(1, 13)),
              "latitude": lat, "longitude": lon}
    shape = (len(FIXTURE_YEARS), 12, 3, 3)

    def field(value):
        return (("year", "month", "latitude", "longitude"),
                np.full(shape, value, dtype="float32"))

    ds = xr.Dataset(
        {
            "salinity_psu": field(6.3),
            "temp_c": field(9.4),
            "din_umol_l": field(1.0),
            "dip_umol_l": field(0.4),
            "light_attenuation_k": field(0.2),
            "significant_wave_m": (("month", "latitude", "longitude"),
                                   np.full((12, 3, 3), 0.9, dtype="float32")),
            "depth_mean_m": (("latitude", "longitude"),
                             np.full((3, 3), 8.0, dtype="float32")),
            "depth_min_m": (("latitude", "longitude"),
                            np.full((3, 3), 5.0, dtype="float32")),
        },
        coords=coords,
    )
    # One land cell, so the valid mask in the fixture is not trivially all-True.
    ds["depth_mean_m"][0, 0] = np.nan
    ds["depth_min_m"][0, 0] = np.nan
    return ds


def _layer(name, product_id, dataset_id, version, variables, statistic):
    return LayerProvenance(
        name=name,
        source="Copernicus Marine Service" if name.startswith("copernicus") else "EMODnet",
        product_id=product_id,
        dataset_id=dataset_id,
        version=version,
        retrieved_on=datetime(2026, 9, 16, tzinfo=timezone.utc),
        licence="CMEMS licence" if name.startswith("copernicus") else "EMODnet licence",
        redistribution="allowed",
        variables=variables,
        statistic=statistic,
        archive=_PENDING,
    )


def write_fixture(directory: Path) -> Manifest:
    ds = add_valid_field(synthetic_dataset(), ["salinity_psu", "depth_mean_m"])
    return write_pair(
        ds,
        dict(
            artifact_schema_version=ARTIFACT_SCHEMA_VERSION,
            built_on=datetime(2026, 9, 16, tzinfo=timezone.utc),
            artifact_filename=ARTIFACT_NAME,
            synthetic=True,
            grid=FIXTURE_GRID,
            baselines={
                "salinity_psu": FIXTURE_YEARS, "temp_c": FIXTURE_YEARS,
                "din_umol_l": FIXTURE_YEARS, "dip_umol_l": FIXTURE_YEARS,
                "light_attenuation_k": FIXTURE_YEARS,
                "significant_wave_m": FIXTURE_WAVE_YEARS,
                "depth_mean_m": [], "depth_min_m": [],
            },
            layers=[
                _layer("copernicus_phy", "BALTICSEA_MULTIYEAR_PHY_003_011",
                       "cmems_mod_bal_phy_my_P1M-m", "202303",
                       ["so", "thetao"], "monthly mean"),
                _layer("copernicus_bgc", "BALTICSEA_MULTIYEAR_BGC_003_012",
                       "cmems_mod_bal_bgc_my_P1M-m", "202303",
                       ["no3", "nh4", "po4"], "monthly mean"),
                _layer("copernicus_wav", "BALTICSEA_MULTIYEAR_WAV_003_015",
                       "cmems_mod_bal_wav_my_PT1H-i", "202411",
                       ["VHM0"], "monthly 95th percentile of hourly values"),
                _layer("emodnet_bathy", "EMODnet Bathymetry DTM",
                       "emodnet_bathymetry_dtm", "2024",
                       ["elevation"], "mean and minimum per target cell"),
            ],
            derived=DERIVED_FIELDS,
            absent=ABSENT_FIELDS,
        ),
        directory,
    )
```

- [ ] **Step 4: Allow the fixture past .gitignore, then generate it**

Add to `.gitignore`, directly after the `*.zarr/` line:

```gitignore

# ...except the committed test fixture, which section 6.3 requires to have a path.
# It is synthetic - a 3x3-cell, 2-year artifact with real structure and invented
# values - so committing it raises no redistribution question.
!tests/fixtures/data/forcing.nc
```

Then:

```bash
micromamba run -n shiny python -c "from pathlib import Path; import sys; sys.path.insert(0, 'src'); from seagarden_dst.refresh.fixture import write_fixture; d = Path('tests/fixtures/data'); d.mkdir(parents=True, exist_ok=True); m = write_fixture(d); print(m.artifact_sha256, m.artifact_bytes)"
git check-ignore -v tests/fixtures/data/forcing.nc || echo "NOT ignored - good"
```

- [ ] **Step 5: Run the tests**

```bash
micromamba run -n shiny python -m pytest tests/test_refresh_fixture.py -q
micromamba run -n shiny ruff check .
```

Expected: 7 passed.

- [ ] **Step 6: Commit**

```bash
git add src/seagarden_dst/refresh/fixture.py tests/test_refresh_fixture.py .gitignore tests/fixtures/data/forcing.nc tests/fixtures/data/manifest.json
git commit -m "Package C: the committed fixture, and section 9's provenance test

Synthetic values, real structure, written by the same writer and manifest code
as a production refresh. Real Copernicus values would raise a redistribution
question package C should not answer implicitly, and a real fixture would need
network and credentials to regenerate, which makes it the kind of artifact that
rots. Its layers are 'pending' rather than carrying an invented DOI, because
that is the state a first real refresh produces."
```

---

### Task 6: The CLI, the isolation test, and the second CI job

**Files:**
- Create: `scripts/refresh_layers.py`, `tests/test_refresh_isolation.py`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: `registry` (Task 3), `build_artifact` (Task 4), `write_fixture` (Task 5).
- Produces: CLI `--probe`, `--fixture`, `--years START END`, `--wave-years START END`, `--out DIR`.

- [ ] **Step 1: Write the failing isolation test**

Create `tests/test_refresh_isolation.py`:

```python
"""The dependency direction is the whole point.

Everything under refresh/ is build-time only. If a core module imported it, the tool
would need the spatial extra at runtime - and the premise that it still runs in 2034,
with no network and no credentials, would be gone.
"""

from __future__ import annotations

import ast
import pathlib

CORE = [
    "api", "calibration", "contracts", "forcing", "growth", "nutrients",
    "params", "scenarios", "shellfish", "suitability",
]
SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "seagarden_dst"


def _imported_names(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{a.name}" for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level:
            names.update(a.name for a in node.names)
    return names


def test_no_core_module_imports_the_refresh_package():
    offenders = []
    for name in CORE:
        path = SRC / f"{name}.py"
        assert path.exists(), f"{path} missing - update CORE in this test"
        for imported in _imported_names(path):
            if "refresh" in imported:
                offenders.append(f"{name}.py imports {imported}")
    assert not offenders, "core modules must not import refresh/: " + "; ".join(offenders)


def test_no_core_module_imports_a_spatial_only_dependency():
    """A subtler version of the same rule: the extras must stay build-time."""
    spatial_only = {"xarray", "rioxarray", "rasterio", "geopandas", "copernicusmarine",
                    "h5netcdf", "netCDF4", "zarr", "dask"}
    offenders = []
    for name in CORE:
        for imported in _imported_names(SRC / f"{name}.py"):
            root = imported.split(".")[0]
            if root in spatial_only:
                offenders.append(f"{name}.py imports {imported}")
    assert not offenders, "core must not import spatial deps: " + "; ".join(offenders)
```

- [ ] **Step 2: Run it**

```bash
micromamba run -n shiny python -m pytest tests/test_refresh_isolation.py -q
```

Expected: 2 passed immediately. This is a characterisation test — it pins behaviour that is currently correct, and its value is that nothing else would catch a regression.

- [ ] **Step 3: Write the CLI**

Create `scripts/refresh_layers.py`:

```python
"""Build the forcing artifact, or ask whether its sources still exist.

Run once a year. See docs/runbooks/annual-refresh.md - which carries the transfer
volumes and the institutional-credential rule, and is the thing a second person follows.

    python scripts/refresh_layers.py --probe
    python scripts/refresh_layers.py --fixture
    python scripts/refresh_layers.py --years 2016 2025 --wave-years 2023 2025
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seagarden_dst.refresh.driver import build_artifact  # noqa: E402
from seagarden_dst.refresh.grid import BALTIC_GRID  # noqa: E402
from seagarden_dst.refresh.layers import registry  # noqa: E402
from seagarden_dst.refresh.writer import data_dir  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", action="store_true",
                        help="ask whether each source still exists; no bulk transfer")
    parser.add_argument("--fixture", action="store_true",
                        help="regenerate the committed synthetic test fixture")
    parser.add_argument("--years", nargs=2, type=int, metavar=("START", "END"),
                        default=[2016, 2025])
    parser.add_argument("--wave-years", nargs=2, type=int, metavar=("START", "END"),
                        default=[2023, 2025])
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    if args.probe:
        failures = 0
        for layer in registry():
            result = layer.probe()
            print(f"{'ok  ' if result.reachable else 'FAIL'} {result.name}: {result.detail}")
            failures += 0 if result.reachable else 1
        return 1 if failures else 0

    if args.fixture:
        from seagarden_dst.refresh.fixture import write_fixture

        target = args.out or Path("tests/fixtures/data")
        manifest = write_fixture(target)
        print(f"fixture written to {target}: {manifest.artifact_bytes} bytes")
        return 0

    years = list(range(args.years[0], args.years[1] + 1))
    wave_years = list(range(args.wave_years[0], args.wave_years[1] + 1))
    target = args.out or data_dir()
    with tempfile.TemporaryDirectory(dir=target.parent if target.exists() else None) as tmp:
        manifest = build_artifact(
            registry(), BALTIC_GRID, years, wave_years, target, Path(tmp),
        )
    print(f"{target}: {manifest.artifact_bytes} bytes, sha256 {manifest.artifact_sha256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Add the second CI job**

The existing job installs `.[app,dev]` and **must keep doing so** — that install is what makes the isolation test meaningful. Add a second job for the refresh tests. In `.github/workflows/ci.yml`, after the existing `test` job, add:

```yaml
  refresh:
    name: refresh tooling (spatial extra)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - uses: actions/setup-python@v6
        with:
          python-version: "3.13"
      - name: Install
        # The spatial extra is build-time only, so the core job deliberately does NOT
        # install it - that is what makes tests/test_refresh_isolation.py meaningful.
        # These tests need it, hence a second job rather than a wider install.
        run: pip install -e ".[spatial,dev]"
      - name: Tests
        run: pytest tests/test_refresh_manifest.py tests/test_refresh_writer.py tests/test_refresh_driver.py tests/test_refresh_fixture.py -q
```

- [ ] **Step 5: Verify locally and commit**

```bash
micromamba run -n shiny python scripts/refresh_layers.py --fixture --out /tmp/fx
micromamba run -n shiny python -m pytest -q
micromamba run -n shiny ruff check .
git add scripts/refresh_layers.py tests/test_refresh_isolation.py .github/workflows/ci.yml
git commit -m "Package C: the CLI, the isolation test, and a second CI job

The core job keeps installing .[app,dev] rather than widening it, because that
narrow install is precisely what makes the isolation test meaningful - the
refresh tests get their own job with .[spatial,dev]. The isolation test checks
both that no core module imports refresh/ and that none imports a spatial-only
dependency directly."
```

---

### Task 7: The Copernicus physics layer

**Files:**
- Create: `src/seagarden_dst/refresh/layers/copernicus_phy.py`
- Test: `tests/test_refresh_layers_offline.py`

**Interfaces:**
- Consumes: `Layer`, `ProbeResult` (Task 3); `LayerProvenance`, `ArchiveState` (Task 1).
- Produces: `CopernicusPHY` with `DATASET_ID = "cmems_mod_bal_phy_my_P1M-m"`, `VERSION = "202303"`; module function `monthly_by_year(ds, years) -> xr.Dataset` reused by Task 8.

- [ ] **Step 1: Write the failing test**

Create `tests/test_refresh_layers_offline.py`:

```python
"""Layer behaviour that can be tested without the network.

The reshape from a flat time axis into (year, month) is where an off-by-one would
silently mis-date every field, so it is tested against a hand-built array.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import xarray as xr

from seagarden_dst.refresh.layers.copernicus_phy import CopernicusPHY, monthly_by_year


def _monthly_stack(years):
    times = pd.date_range(f"{years[0]}-01-01", f"{years[-1]}-12-01", freq="MS")
    values = np.arange(times.size, dtype="float32").reshape(times.size, 1, 1)
    return xr.Dataset(
        {"so": (("time", "latitude", "longitude"), values)},
        coords={"time": times, "latitude": [55.0], "longitude": [20.0]},
    )


def test_monthly_by_year_splits_time_into_year_and_month():
    reshaped = monthly_by_year(_monthly_stack([2024, 2025]), [2024, 2025])
    assert reshaped.sizes["year"] == 2
    assert reshaped.sizes["month"] == 12
    assert reshaped["year"].values.tolist() == [2024, 2025]
    assert reshaped["month"].values.tolist() == list(range(1, 13))


def test_monthly_by_year_keeps_each_value_on_its_own_date():
    """January 2025 is the 13th month of a 2024-2025 stack, value 12."""
    reshaped = monthly_by_year(_monthly_stack([2024, 2025]), [2024, 2025])
    assert float(reshaped["so"].sel(year=2025, month=1).squeeze()) == 12.0
    assert float(reshaped["so"].sel(year=2024, month=1).squeeze()) == 0.0


def test_the_phy_layer_declares_the_dataset_package_b_verified():
    layer = CopernicusPHY()
    prov = layer.provenance()
    assert prov.dataset_id == "cmems_mod_bal_phy_my_P1M-m"
    assert prov.version == "202303"
    assert prov.archive.status == "pending"
    assert set(prov.variables) == {"so", "thetao"}
```

- [ ] **Step 2: Run it and watch it fail**

```bash
micromamba run -n shiny python -m pytest tests/test_refresh_layers_offline.py -q
```

Expected: `ModuleNotFoundError: ...copernicus_phy`.

- [ ] **Step 3: Write the layer**

Create `src/seagarden_dst/refresh/layers/copernicus_phy.py`:

```python
"""Salinity and temperature, monthly means at the surface level.

Dataset and version confirmed against the live catalogue on 15 September 2026:
cmems_mod_bal_phy_my_P1M-m at version 202303, covering 1993-01-01 to 2026-05-31, with
no _myint_ interim variant - so the 2016-2025 baseline sits inside one dataset at one
version and a single LayerProvenance describes it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import xarray as xr

from ..manifest import ArchiveState, GridSpec, LayerProvenance
from .base import ProbeResult

PRODUCT_ID = "BALTICSEA_MULTIYEAR_PHY_003_011"
DATASET_ID = "cmems_mod_bal_phy_my_P1M-m"
VERSION = "202303"
VARIABLES = ["so", "thetao"]
#: Shallowest of the reanalysis's 56 levels. This is a MODEL level and has nothing to
#: do with depth_mean_m/depth_min_m, which are seabed bathymetry from EMODnet.
SURFACE_MAX_DEPTH_M = 1.0


def monthly_by_year(ds: xr.Dataset, years: list[int]) -> xr.Dataset:
    """Reshape a flat monthly time axis into (year, month).

    Kept as a module function because the BGC layer needs exactly the same reshape and
    two implementations of it could disagree about which month a value belongs to.
    """
    out = ds.assign_coords(
        year=("time", ds["time"].dt.year.values),
        month=("time", ds["time"].dt.month.values),
    )
    out = out.set_index(time=["year", "month"]).unstack("time")
    out = out.reindex(year=years, month=list(range(1, 13)))
    return out.transpose("year", "month", "latitude", "longitude", missing_dims="ignore")


class CopernicusPHY:
    name = "copernicus_phy"

    def probe(self) -> ProbeResult:
        import copernicusmarine as cm

        try:
            cm.describe(dataset_id=DATASET_ID)
        except Exception as exc:  # noqa: BLE001 - the probe reports, never raises
            return ProbeResult(self.name, False, f"{type(exc).__name__}: {exc}")
        return ProbeResult(self.name, True, f"{DATASET_ID} reachable")

    def build(self, grid: GridSpec, workdir: Path) -> xr.Dataset:
        import copernicusmarine as cm

        years = list(range(2016, 2026))
        target = workdir / "phy_monthly.nc"
        cm.subset(
            dataset_id=DATASET_ID,
            variables=VARIABLES,
            minimum_longitude=grid.lon_min, maximum_longitude=grid.lon_max,
            minimum_latitude=grid.lat_min, maximum_latitude=grid.lat_max,
            start_datetime=f"{years[0]}-01-01", end_datetime=f"{years[-1]}-12-31",
            minimum_depth=0.0, maximum_depth=SURFACE_MAX_DEPTH_M,
            output_directory=str(workdir), output_filename=target.name,
            overwrite=True, disable_progress_bar=True,
        )
        raw = xr.open_dataset(target).isel(depth=0, drop=True)
        shaped = monthly_by_year(raw, years)
        return xr.Dataset(
            {
                "salinity_psu": shaped["so"].astype("float32"),
                "temp_c": shaped["thetao"].astype("float32"),
            }
        )

    def provenance(self) -> LayerProvenance:
        return LayerProvenance(
            name=self.name,
            source="Copernicus Marine Service",
            product_id=PRODUCT_ID,
            dataset_id=DATASET_ID,
            version=VERSION,
            retrieved_on=datetime.now(timezone.utc),
            licence="Copernicus Marine Service licence",
            redistribution="allowed",
            variables=VARIABLES,
            statistic="monthly mean at the surface level (0.50 m)",
            archive=ArchiveState(
                status="pending",
                source_url="https://marine.copernicus.eu/",
                unblocked_by="the first Zenodo deposit, performed by hand per the runbook",
            ),
        )
```

- [ ] **Step 4: Run the tests and commit**

```bash
micromamba run -n shiny python -m pytest tests/test_refresh_layers_offline.py -q
micromamba run -n shiny ruff check .
git add src/seagarden_dst/refresh/layers/copernicus_phy.py tests/test_refresh_layers_offline.py
git commit -m "Package C: the Copernicus physics layer

Salinity and temperature as monthly means at the surface level, from
cmems_mod_bal_phy_my_P1M-m version 202303 - confirmed against the live
catalogue, with no _myint_ variant, so the 2016-2025 baseline sits inside one
dataset at one version. The (year, month) reshape is a shared module function
because the BGC layer needs the identical reshape and two copies could disagree
about which month a value belongs to."
```

---

### Task 8: The Copernicus biogeochemistry layer, and the Jensen correction

This is the one layer whose source product is fixed by the **shape** of its statistic.

**Files:**
- Create: `src/seagarden_dst/refresh/layers/copernicus_bgc.py`
- Modify: `tests/test_refresh_layers_offline.py`

**Interfaces:**
- Consumes: `monthly_by_year` (Task 7).
- Produces: `CopernicusBGC`; `attenuation_from_daily_zsd(daily_zsd: xr.DataArray, years) -> xr.DataArray`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_refresh_layers_offline.py`:

```python
from seagarden_dst.refresh.layers.copernicus_bgc import (
    CopernicusBGC,
    attenuation_from_daily_zsd,
)


def _daily_zsd(values, year=2024):
    times = pd.date_range(f"{year}-01-01", periods=len(values), freq="D")
    return xr.DataArray(
        np.array(values, dtype="float32").reshape(len(values), 1, 1),
        dims=("time", "latitude", "longitude"),
        coords={"time": times, "latitude": [55.0], "longitude": [20.0]},
        name="zsd",
    )


def test_attenuation_averages_k_not_secchi_depth():
    """k = 1.7/z is non-linear, so the order of operations changes the answer.

    Two days at 2 m and 10 m Secchi depth. Averaging k gives (0.85 + 0.17)/2 = 0.51.
    Averaging z first gives 1.7/6 = 0.283 - 44% lower, which means less attenuation,
    more PAR at depth, and an optimistic growth bias. By Jensen's inequality the
    monthly-input route is ALWAYS the lower of the two, so the error is directional.
    """
    k = attenuation_from_daily_zsd(_daily_zsd([2.0, 10.0]), [2024])
    got = float(k.sel(year=2024, month=1).squeeze())
    assert got == pytest.approx(0.51, rel=1e-3)
    assert got > 1.7 / 6.0


def test_attenuation_is_monthly_and_per_year():
    values = [4.0] * 366  # 2024 is a leap year
    k = attenuation_from_daily_zsd(_daily_zsd(values), [2024])
    assert k.sizes["year"] == 1 and k.sizes["month"] == 12
    assert float(k.sel(year=2024, month=6).squeeze()) == pytest.approx(0.425)


def test_the_bgc_layer_declares_both_datasets_it_reads():
    """Monthly for nutrients, DAILY for zsd - the two cannot be the same product."""
    prov = CopernicusBGC().provenance()
    assert prov.dataset_id == "cmems_mod_bal_bgc_my_P1M-m"
    assert "cmems_mod_bal_bgc_my_P1D-m" in prov.statistic
    assert set(prov.variables) == {"no3", "nh4", "po4", "zsd"}
```

Add `import pytest` to the test module's imports if it is not already there.

- [ ] **Step 2: Run it and watch it fail**

```bash
micromamba run -n shiny python -m pytest tests/test_refresh_layers_offline.py -q
```

Expected: `ModuleNotFoundError: ...copernicus_bgc`.

- [ ] **Step 3: Write the layer**

Create `src/seagarden_dst/refresh/layers/copernicus_bgc.py`:

```python
"""Nutrients, and light attenuation derived from DAILY Secchi depth.

DIN = no3 + nh4 and DIP = po4 are linear in their sources, so monthly-mean inputs are
correct for them and the monthly product is used.

light_attenuation_k is NOT linear: k = 1.7/z_SD. Averaging does not commute through it,
and by Jensen's inequality - 1/x being convex for x > 0 - computing 1.7/mean(z_monthly)
is systematically LOWER than mean(1.7/z_daily). Lower k means less attenuation, so more
PAR at cultivation depth, so an optimistic growth bias, and a silent one: the field
would look correct and carry no marker. So this layer pulls DAILY zsd, computes k per
day, and averages k over the month.

Package B computed 0.198 at Tagalaht from cmems_mod_bal_bgc_my_P1D-m, the daily product,
so B's figure is sound. The cost is about 0.36 GB/year of transfer, 3.6 GB over the
baseline; the artifact is unchanged in size because it stores monthly k either way.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import xarray as xr

from ..manifest import ArchiveState, GridSpec, LayerProvenance
from .base import ProbeResult
from .copernicus_phy import monthly_by_year

PRODUCT_ID = "BALTICSEA_MULTIYEAR_BGC_003_012"
MONTHLY_DATASET_ID = "cmems_mod_bal_bgc_my_P1M-m"
DAILY_DATASET_ID = "cmems_mod_bal_bgc_my_P1D-m"
VERSION = "202303"
NUTRIENT_VARIABLES = ["no3", "nh4", "po4"]
#: Poole-Atkins. Recorded in the manifest's `derived` block, not only here.
POOLE_ATKINS = 1.7
SURFACE_MAX_DEPTH_M = 1.0


def attenuation_from_daily_zsd(daily_zsd: xr.DataArray, years: list[int]) -> xr.DataArray:
    """k per day, then the monthly mean of k. Never the other way round."""
    k = POOLE_ATKINS / daily_zsd
    k = k.assign_coords(
        year=("time", k["time"].dt.year.values),
        month=("time", k["time"].dt.month.values),
    )
    monthly = k.groupby("time.year").map(lambda g: g.groupby("time.month").mean("time"))
    return monthly.reindex(year=years, month=list(range(1, 13))).astype("float32")


class CopernicusBGC:
    name = "copernicus_bgc"

    def probe(self) -> ProbeResult:
        import copernicusmarine as cm

        for dataset_id in (MONTHLY_DATASET_ID, DAILY_DATASET_ID):
            try:
                cm.describe(dataset_id=dataset_id)
            except Exception as exc:  # noqa: BLE001
                return ProbeResult(self.name, False, f"{dataset_id}: {type(exc).__name__}")
        return ProbeResult(self.name, True, f"{MONTHLY_DATASET_ID} and {DAILY_DATASET_ID} reachable")

    def build(self, grid: GridSpec, workdir: Path) -> xr.Dataset:
        import copernicusmarine as cm

        years = list(range(2016, 2026))
        box = dict(
            minimum_longitude=grid.lon_min, maximum_longitude=grid.lon_max,
            minimum_latitude=grid.lat_min, maximum_latitude=grid.lat_max,
            start_datetime=f"{years[0]}-01-01", end_datetime=f"{years[-1]}-12-31",
            minimum_depth=0.0, maximum_depth=SURFACE_MAX_DEPTH_M,
            output_directory=str(workdir), overwrite=True, disable_progress_bar=True,
        )

        cm.subset(dataset_id=MONTHLY_DATASET_ID, variables=NUTRIENT_VARIABLES,
                  output_filename="bgc_monthly.nc", **box)
        monthly = xr.open_dataset(workdir / "bgc_monthly.nc").isel(depth=0, drop=True)
        shaped = monthly_by_year(monthly, years)

        # The expensive half, and the reason it is a separate pull: ~0.36 GB/year.
        cm.subset(dataset_id=DAILY_DATASET_ID, variables=["zsd"],
                  output_filename="bgc_daily_zsd.nc", **box)
        daily = xr.open_dataset(workdir / "bgc_daily_zsd.nc").isel(depth=0, drop=True)

        return xr.Dataset(
            {
                "din_umol_l": (shaped["no3"] + shaped["nh4"]).astype("float32"),
                "dip_umol_l": shaped["po4"].astype("float32"),
                "light_attenuation_k": attenuation_from_daily_zsd(daily["zsd"], years),
            }
        )

    def provenance(self) -> LayerProvenance:
        return LayerProvenance(
            name=self.name,
            source="Copernicus Marine Service",
            product_id=PRODUCT_ID,
            dataset_id=MONTHLY_DATASET_ID,
            version=VERSION,
            retrieved_on=datetime.now(timezone.utc),
            licence="Copernicus Marine Service licence",
            redistribution="allowed",
            variables=NUTRIENT_VARIABLES + ["zsd"],
            statistic=(
                "monthly mean of no3+nh4 and po4 from cmems_mod_bal_bgc_my_P1M-m; "
                "light_attenuation_k as the monthly mean of daily 1.7/zsd from "
                "cmems_mod_bal_bgc_my_P1D-m, because k is non-linear in zsd"
            ),
            archive=ArchiveState(
                status="pending",
                source_url="https://marine.copernicus.eu/",
                unblocked_by="the first Zenodo deposit, performed by hand per the runbook",
            ),
        )
```

- [ ] **Step 4: Run the tests and commit**

```bash
micromamba run -n shiny python -m pytest tests/test_refresh_layers_offline.py -q
micromamba run -n shiny ruff check .
git add src/seagarden_dst/refresh/layers/copernicus_bgc.py tests/test_refresh_layers_offline.py
git commit -m "Package C: nutrients, and light attenuation from DAILY Secchi depth

k = 1.7/z_SD is non-linear, so averaging does not commute through it: by
Jensen's inequality 1.7/mean(z_monthly) is systematically lower than
mean(1.7/z_daily). Lower k means less attenuation, more PAR at depth, and an
optimistic growth bias - silent, because the field would look correct. So the
layer pulls daily zsd and averages k rather than z. Package B computed 0.198 at
Tagalaht from the daily product, so B's figure is sound. Costs ~3.6 GB over the
baseline and does not change the artifact's size."
```

---

### Task 9: The wave layer, streamed

The only layer that cannot fetch-then-normalise: ~26 GB of hourly data reduced to 12 monthly percentiles at ~1 GB peak disk.

**Files:**
- Create: `src/seagarden_dst/refresh/layers/copernicus_wav.py`
- Modify: `tests/test_refresh_layers_offline.py`

**Interfaces:**
- Produces: `CopernicusWAV`; `p95_of_month(values: xr.DataArray) -> xr.DataArray`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_refresh_layers_offline.py`:

```python
from seagarden_dst.refresh.layers.copernicus_wav import CopernicusWAV, p95_of_month


def test_p95_is_the_95th_percentile_over_time_not_the_mean():
    """A mean is wrong in the permissive direction for a structural design limit."""
    hours = pd.date_range("2024-01-01", periods=100, freq="h")
    values = np.arange(100, dtype="float32").reshape(100, 1, 1)
    da = xr.DataArray(values, dims=("time", "latitude", "longitude"),
                      coords={"time": hours, "latitude": [55.0], "longitude": [20.0]})
    got = float(p95_of_month(da).squeeze())
    assert got == pytest.approx(94.05, rel=1e-3)
    assert got > float(da.mean())


def test_the_wave_layer_declares_the_hourly_dataset():
    """Not the ready-made climatology: that is a MEAN, the statistic 6.1 rejects."""
    prov = CopernicusWAV().provenance()
    assert prov.dataset_id == "cmems_mod_bal_wav_my_PT1H-i"
    assert prov.version == "202411"
    assert "climatology" not in prov.dataset_id
    assert "95th percentile" in prov.statistic
```

- [ ] **Step 2: Run it and watch it fail**

Expected: `ModuleNotFoundError: ...copernicus_wav`.

- [ ] **Step 3: Write the layer**

Create `src/seagarden_dst/refresh/layers/copernicus_wav.py`:

```python
"""Significant wave height as a monthly 95th percentile, streamed.

Section 6.1 requires a percentile rather than a mean because the same artifact feeds
assess_physical's exposure test against a structural design limit, where a mean fails in
the permissive direction. The product ships a ready-made 2 km monthly climatology - but
as a MEAN, which is the statistic that requirement rejects, so it cannot be used.

That forces the hourly dataset, which is ~8.6 GB per year over this grid. The whole
baseline cannot be downloaded and then reduced, so this layer streams: one month-of-year
at a time across the wave baseline, accumulate, discard. Peak working disk is about
1 GB rather than about 26 GB, which matters on a developer machine.

A p95 is not a tail statistic, which is why a three-year wave baseline is adequate:
three years gives roughly 2,200 hourly values per cell per month. The ANNUAL MAXIMUM is
a tail statistic, which is exactly why it is deferred rather than computed badly.

Dataset confirmed against the live catalogue on 15 September 2026:
cmems_mod_bal_wav_my_PT1H-i at version 202411, covering 1980-01-01 to 2026-07-01, with
no _myint_ variant. Note the version differs from the physics and biogeochemistry
products (202303) - which is why `version` is per layer and not per artifact.
"""

from __future__ import annotations

import calendar
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import xarray as xr

from ..manifest import ArchiveState, GridSpec, LayerProvenance
from .base import ProbeResult

PRODUCT_ID = "BALTICSEA_MULTIYEAR_WAV_003_015"
DATASET_ID = "cmems_mod_bal_wav_my_PT1H-i"
VERSION = "202411"
VARIABLE = "VHM0"
WAVE_YEARS = [2023, 2024, 2025]
PERCENTILE = 0.95


def p95_of_month(values: xr.DataArray) -> xr.DataArray:
    """The 95th percentile over the time axis, per cell."""
    return values.quantile(PERCENTILE, dim="time", skipna=True).drop_vars(
        "quantile"
    ).astype("float32")


class CopernicusWAV:
    name = "copernicus_wav"

    def probe(self) -> ProbeResult:
        import copernicusmarine as cm

        try:
            cm.describe(dataset_id=DATASET_ID)
        except Exception as exc:  # noqa: BLE001
            return ProbeResult(self.name, False, f"{type(exc).__name__}: {exc}")
        return ProbeResult(self.name, True, f"{DATASET_ID} reachable")

    def build(self, grid: GridSpec, workdir: Path) -> xr.Dataset:
        """One month-of-year at a time, across every wave-baseline year."""
        import copernicusmarine as cm

        per_month = []
        for month in range(1, 13):
            chunks = []
            for year in WAVE_YEARS:
                last_day = calendar.monthrange(year, month)[1]
                name = f"wav_{year}_{month:02d}.nc"
                cm.subset(
                    dataset_id=DATASET_ID, variables=[VARIABLE],
                    minimum_longitude=grid.lon_min, maximum_longitude=grid.lon_max,
                    minimum_latitude=grid.lat_min, maximum_latitude=grid.lat_max,
                    start_datetime=f"{year}-{month:02d}-01",
                    end_datetime=f"{year}-{month:02d}-{last_day} 23:00:00",
                    output_directory=str(workdir), output_filename=name,
                    overwrite=True, disable_progress_bar=True,
                )
                chunks.append(xr.open_dataset(workdir / name)[VARIABLE].load())
                (workdir / name).unlink()  # discard as we go: peak disk, not total
            stacked = xr.concat(chunks, dim="time")
            per_month.append(p95_of_month(stacked).expand_dims(month=[month]))
            del chunks, stacked

        combined = xr.concat(per_month, dim="month")
        return xr.Dataset({"significant_wave_m": combined})

    def provenance(self) -> LayerProvenance:
        return LayerProvenance(
            name=self.name,
            source="Copernicus Marine Service",
            product_id=PRODUCT_ID,
            dataset_id=DATASET_ID,
            version=VERSION,
            retrieved_on=datetime.now(timezone.utc),
            licence="Copernicus Marine Service licence",
            redistribution="allowed",
            variables=[VARIABLE],
            statistic=(
                f"monthly 95th percentile of hourly {VARIABLE} over "
                f"{WAVE_YEARS[0]}-{WAVE_YEARS[-1]}; NOT the product's ready-made "
                "climatology, which is a mean"
            ),
            archive=ArchiveState(
                status="pending",
                source_url="https://marine.copernicus.eu/",
                unblocked_by="the first Zenodo deposit, performed by hand per the runbook",
            ),
        )
```

- [ ] **Step 4: Run the tests and commit**

```bash
micromamba run -n shiny python -m pytest tests/test_refresh_layers_offline.py -q
micromamba run -n shiny ruff check .
git add src/seagarden_dst/refresh/layers/copernicus_wav.py tests/test_refresh_layers_offline.py
git commit -m "Package C: wave exposure as a streamed monthly 95th percentile

The ready-made 2 km climatology is a mean, which is the statistic section 6.1
rejects for a structural design limit, so the hourly dataset is unavoidable -
about 26 GB over the wave baseline. The layer streams one month-of-year at a
time and discards each chunk, so peak working disk is about 1 GB rather than
26 GB. The wave product is at version 202411 against 202303 for physics and
biogeochemistry, which is why version is per layer."
```

---

### Task 10: The EMODnet bathymetry layer

The least-specified layer in the design, and the one most likely to need rework once attempted — it has no CMEMS-style client.

**Files:**
- Create: `src/seagarden_dst/refresh/layers/emodnet_bathy.py`
- Modify: `tests/test_refresh_layers_offline.py`

**Interfaces:**
- Produces: `EMODnetBathymetry`; `aggregate_to_grid(elevation: xr.DataArray, grid: GridSpec) -> xr.Dataset` returning `depth_mean_m` and `depth_min_m`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_refresh_layers_offline.py`:

```python
from seagarden_dst.refresh.layers.emodnet_bathy import EMODnetBathymetry, aggregate_to_grid
from seagarden_dst.refresh.manifest import GridSpec


def test_aggregation_reports_both_mean_and_minimum_depth():
    """Section 6.1 asks for 'mean, with min reported'.

    The minimum is the number that matters for a structure with draft, and depth is a
    hard gate in api.select_method with method bounds at 2-6 m, so a cell's mean alone
    would mis-gate near shore.
    """
    fine = xr.DataArray(
        np.array([[-4.0, -6.0], [-8.0, -10.0]], dtype="float32"),
        dims=("latitude", "longitude"),
        coords={"latitude": [55.00, 55.01], "longitude": [20.00, 20.01]},
    )
    grid = GridSpec(lat_min=55.0, lat_max=55.02, lon_min=20.0, lon_max=20.02,
                    lat_step=0.02, lon_step=0.02, n_lat=1, n_lon=1)
    out = aggregate_to_grid(fine, grid)
    assert float(out["depth_mean_m"].squeeze()) == pytest.approx(7.0)
    assert float(out["depth_min_m"].squeeze()) == pytest.approx(4.0)


def test_elevation_is_converted_to_positive_depth():
    """EMODnet ships elevation: negative below sea level. depth_m is positive down."""
    fine = xr.DataArray(
        np.array([[-12.0]], dtype="float32"),
        dims=("latitude", "longitude"),
        coords={"latitude": [55.0], "longitude": [20.0]},
    )
    grid = GridSpec(lat_min=55.0, lat_max=55.02, lon_min=20.0, lon_max=20.02,
                    lat_step=0.02, lon_step=0.02, n_lat=1, n_lon=1)
    out = aggregate_to_grid(fine, grid)
    assert float(out["depth_mean_m"].squeeze()) == pytest.approx(12.0)


def test_land_cells_become_nan_not_negative_depth():
    """Above sea level is not a shallow farm site; it is not a site at all."""
    fine = xr.DataArray(
        np.array([[5.0]], dtype="float32"),
        dims=("latitude", "longitude"),
        coords={"latitude": [55.0], "longitude": [20.0]},
    )
    grid = GridSpec(lat_min=55.0, lat_max=55.02, lon_min=20.0, lon_max=20.02,
                    lat_step=0.02, lon_step=0.02, n_lat=1, n_lon=1)
    out = aggregate_to_grid(fine, grid)
    assert np.isnan(float(out["depth_mean_m"].squeeze()))
```

- [ ] **Step 2: Run it and watch it fail**

Expected: `ModuleNotFoundError: ...emodnet_bathy`.

- [ ] **Step 3: Write the layer**

Create `src/seagarden_dst/refresh/layers/emodnet_bathy.py`:

```python
"""Seabed depth, aggregated from EMODnet's ~115 m grid to the 2 km target grid.

Why not the Copernicus model bathymetry, which is already on the target grid and would
be free: depth_m is a hard gate in api.select_method, and params/methods.yaml sets the
bounds at 2, 3, 4, 5 and 6 m minimum. A 2 km cell mean near shore commonly reads 10-15 m
where the actual site is 5 m, so model bathymetry would mis-gate WHICH cultivation
methods a site is offered, precisely where the thresholds cluster.

This is the least-specified layer in the design: EMODnet has no CMEMS-style Python
client, no catalogue of the same shape, and no version string of the same form. The
download below uses the public DTM tile service; if that interface has changed, fix the
fetch and leave aggregate_to_grid alone - the aggregation is the part that carries the
science and it is tested offline.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import xarray as xr

from ..grid import axes
from ..manifest import ArchiveState, GridSpec, LayerProvenance
from .base import ProbeResult

PRODUCT_ID = "EMODnet Bathymetry DTM"
DATASET_ID = "emodnet_bathymetry_dtm"
#: EMODnet releases the DTM by year rather than by a version string. Update on refresh.
VERSION = "2024"
SOURCE_URL = "https://emodnet.ec.europa.eu/en/bathymetry"
WCS_ENDPOINT = "https://ows.emodnet-bathymetry.eu/wcs"


def aggregate_to_grid(elevation: xr.DataArray, grid: GridSpec) -> xr.Dataset:
    """Fine elevation to coarse depth: mean and minimum per target cell.

    EMODnet ships ELEVATION - negative below sea level - and SiteConditions wants depth
    positive downwards, so the sign is flipped. Cells at or above sea level become NaN:
    land is not a shallow site, it is not a site.
    """
    depth = (-elevation).where(elevation < 0.0)
    lat, lon = axes(grid)
    lat_edges = np.append(lat - grid.lat_step / 2.0, lat[-1] + grid.lat_step / 2.0)
    lon_edges = np.append(lon - grid.lon_step / 2.0, lon[-1] + grid.lon_step / 2.0)

    binned = depth.groupby_bins("latitude", lat_edges, labels=lat).groupby_bins(
        "longitude", lon_edges, labels=lon
    )
    mean = binned.mean().rename({"latitude_bins": "latitude", "longitude_bins": "longitude"})
    minimum = binned.min().rename({"latitude_bins": "latitude", "longitude_bins": "longitude"})
    return xr.Dataset(
        {
            "depth_mean_m": mean.astype("float32"),
            "depth_min_m": minimum.astype("float32"),
        }
    )


class EMODnetBathymetry:
    name = "emodnet_bathy"

    def probe(self) -> ProbeResult:
        import urllib.request

        url = f"{WCS_ENDPOINT}?service=WCS&version=2.0.1&request=GetCapabilities"
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                ok = response.status == 200
            return ProbeResult(self.name, ok, f"WCS GetCapabilities returned {response.status}")
        except Exception as exc:  # noqa: BLE001
            return ProbeResult(self.name, False, f"{type(exc).__name__}: {exc}")

    def build(self, grid: GridSpec, workdir: Path) -> xr.Dataset:
        import urllib.request

        target = workdir / "emodnet_dtm.tif"
        url = (
            f"{WCS_ENDPOINT}?service=WCS&version=2.0.1&request=GetCoverage"
            "&coverageId=emodnet__mean&format=image/tiff"
            f"&subset=Lat({grid.lat_min},{grid.lat_max})"
            f"&subset=Long({grid.lon_min},{grid.lon_max})"
        )
        urllib.request.urlretrieve(url, target)

        import rioxarray  # noqa: F401 - registers the .rio accessor

        raster = xr.open_dataarray(target, engine="rasterio").squeeze(drop=True)
        raster = raster.rename({"y": "latitude", "x": "longitude"})
        return aggregate_to_grid(raster, grid)

    def provenance(self) -> LayerProvenance:
        return LayerProvenance(
            name=self.name,
            source="EMODnet Bathymetry",
            product_id=PRODUCT_ID,
            dataset_id=DATASET_ID,
            version=VERSION,
            retrieved_on=datetime.now(timezone.utc),
            licence="EMODnet Bathymetry licence (CC-BY)",
            redistribution="allowed",
            variables=["elevation"],
            statistic="mean and minimum depth per target cell, from ~115 m source",
            archive=ArchiveState(
                status="pending",
                source_url=SOURCE_URL,
                unblocked_by="the first Zenodo deposit, performed by hand per the runbook",
            ),
        )
```

- [ ] **Step 4: Run the whole suite and commit**

```bash
micromamba run -n shiny python -m pytest -q
micromamba run -n shiny ruff check .
git add src/seagarden_dst/refresh/layers/emodnet_bathy.py tests/test_refresh_layers_offline.py
git commit -m "Package C: seabed depth from EMODnet, aggregated to the target grid

Model bathymetry would be free and already on the grid, and is rejected: depth
is a hard gate in select_method with method bounds at 2-6 m, and a 2 km cell
mean near shore reads 10-15 m where the site is 5 m, so it would mis-gate which
methods a site is offered. Elevation is flipped to positive depth and land
becomes NaN rather than a negative depth. The aggregation is tested offline
because it carries the science; the WCS fetch is the part most likely to need
rework."
```

---

### Task 11: The Zenodo deposit path

The deliverable that discharges the open-data half of the durability commitment. Until review, it had **no check that could fail**.

**Files:**
- Create: `src/seagarden_dst/refresh/zenodo.py`, `tests/test_refresh_zenodo.py`

**Interfaces:**
- Consumes: `Manifest`, `ArchiveState` (Task 1); `load_verified` (Task 2).
- Produces: `deposit(directory: Path, *, client) -> str` returning a DOI; `record_doi(directory: Path, doi: str) -> Manifest`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_refresh_zenodo.py`:

```python
"""The deposit path, exercised against a stub.

No real deposit happens in package C - a DOI is permanent, public and published under
the project's name, so a human runs the first one. What is tested here is that the code
which records the returned DOI actually works, because until review this deliverable had
no check that could fail.
"""

from __future__ import annotations

import pytest

from seagarden_dst.refresh.fixture import write_fixture
from seagarden_dst.refresh.writer import load_verified
from seagarden_dst.refresh.zenodo import record_doi


def test_recording_a_doi_flips_every_pending_layer_to_deposited(tmp_path):
    write_fixture(tmp_path)
    before, _ = load_verified(tmp_path)
    assert all(layer.archive.status == "pending" for layer in before.layers)

    after = record_doi(tmp_path, "10.5281/zenodo.1234567")

    assert all(layer.archive.status == "deposited" for layer in after.layers)
    assert all(layer.archive.zenodo_doi == "10.5281/zenodo.1234567" for layer in after.layers)


def test_the_manifest_still_validates_and_still_matches_the_artifact(tmp_path):
    """Recording a DOI rewrites the manifest but must not disturb the pair."""
    write_fixture(tmp_path)
    before, _ = load_verified(tmp_path)
    record_doi(tmp_path, "10.5281/zenodo.1234567")
    after, _ = load_verified(tmp_path)
    assert after.artifact_sha256 == before.artifact_sha256


def test_a_forbidden_layer_is_left_alone(tmp_path):
    """A referenced-not-mirrored layer was never deposited, so it has no DOI to gain."""
    write_fixture(tmp_path)
    manifest, _ = load_verified(tmp_path)
    path = tmp_path / "manifest.json"
    payload = manifest.model_dump(mode="json")
    payload["layers"][0]["redistribution"] = "forbidden"
    payload["layers"][0]["archive"] = {"status": "forbidden",
                                       "source_url": "https://example.invalid/"}
    import json
    path.write_text(json.dumps(payload), encoding="utf-8")

    after = record_doi(tmp_path, "10.5281/zenodo.1234567")
    assert after.layers[0].archive.status == "forbidden"
    assert after.layers[0].archive.zenodo_doi is None
    assert all(layer.archive.status == "deposited" for layer in after.layers[1:])


def test_recording_an_empty_doi_is_refused(tmp_path):
    write_fixture(tmp_path)
    with pytest.raises(ValueError, match="doi"):
        record_doi(tmp_path, "")
```

- [ ] **Step 2: Run it and watch it fail**

Expected: `ModuleNotFoundError: ...zenodo`.

- [ ] **Step 3: Write the module**

Create `src/seagarden_dst/refresh/zenodo.py`:

```python
"""Archiving a refresh under a DOI, and recording it.

Package C does NOT perform a deposit. A DOI is permanent, public and published under the
project's name, and needs institutional credentials - so a human runs the first one,
following docs/runbooks/annual-refresh.md. What lives here is the code that path needs,
and a recording step that is tested.

The sequence, which the runbook repeats: build (every layer 'pending') -> deposit
artifact and manifest -> record the returned DOI back into the committed manifest,
flipping those layers to 'deposited'. The deposited manifest and the committed manifest
therefore DIFFER by the DOI field; the committed one is authoritative for provenance.
artifact_sha256 is unaffected, because the artifact does not change.
"""

from __future__ import annotations

from pathlib import Path

from .manifest import ArchiveState, Manifest
from .writer import MANIFEST_NAME, load_verified

ZENODO_FILE_LIMIT_BYTES = 50 * 1024**3  # 50 GB standard per-file limit


def record_doi(directory: Path, doi: str) -> Manifest:
    """Flip every 'pending' layer to 'deposited' under `doi`, and rewrite the manifest.

    Layers marked 'forbidden' are referenced-not-mirrored: they were never deposited, so
    they have no DOI to gain and are left untouched.
    """
    if not doi.strip():
        raise ValueError("refusing to record an empty doi")

    manifest, _ = load_verified(directory)
    updated = []
    for layer in manifest.layers:
        if layer.archive.status == "pending":
            layer = layer.model_copy(
                update={
                    "archive": ArchiveState(
                        status="deposited",
                        zenodo_doi=doi,
                        source_url=layer.archive.source_url,
                    )
                }
            )
        updated.append(layer)

    rewritten = manifest.model_copy(update={"layers": updated})
    (directory / MANIFEST_NAME).write_text(
        rewritten.model_dump_json(indent=2), encoding="utf-8"
    )
    return rewritten


def check_size_fits_zenodo(artifact_bytes: int) -> None:
    """Section 4.1 asked package B's resolution decision to respect this limit.

    Package B measured the largest candidate artifact at 50.7 MB, three orders of
    magnitude inside the limit, so this can only fire if the extent or the baseline grows
    enormously - which is exactly when nobody would be checking.
    """
    if artifact_bytes > ZENODO_FILE_LIMIT_BYTES:
        raise ValueError(
            f"artifact is {artifact_bytes / 1024**3:.1f} GB, above Zenodo's "
            f"{ZENODO_FILE_LIMIT_BYTES / 1024**3:.0f} GB per-file limit"
        )
```

- [ ] **Step 4: Run the tests and commit**

```bash
micromamba run -n shiny python -m pytest tests/test_refresh_zenodo.py -q
micromamba run -n shiny ruff check .
git add src/seagarden_dst/refresh/zenodo.py tests/test_refresh_zenodo.py
git commit -m "Package C: the deposit path, with a check that can fail

Package C performs no deposit - a DOI is permanent, public and under the
project's name, so a human runs the first one. But until review this
deliverable had no test at all, which is the repository's most-repeated defect
class. Recording a DOI now flips pending layers to deposited, leaves
referenced-not-mirrored layers alone, and is proven not to disturb the
artifact/manifest checksum pairing."
```

---

### Task 12: The runbook and the source-probe job

`§8`'s done-when includes the one clause the implementer **cannot discharge**: the runbook followed end to end by somebody else.

**Files:**
- Create: `docs/runbooks/annual-refresh.md`, `.github/workflows/source-probe.yml`

- [ ] **Step 1: Write the runbook**

Create `docs/runbooks/annual-refresh.md`. It must contain, at minimum, these sections with these facts — measured values, not estimates:

```markdown
# Annual refresh runbook

For whoever is doing this, which is probably not the person who wrote it.

## Before you start

- **Credential:** a Copernicus Marine account. It MUST be the institutional account,
  never a personal one — an annual refresh that depends on one person's login stops
  working when that person changes role. Where it is held: <FILL IN: the institutional
  password store>. Log in once with `copernicusmarine login`.
- **Disk:** at least 5 GB free. The wave stream discards as it goes, so peak working
  space is about 1 GB, but leave headroom.
- **Time and data:** about **30 GB crosses the wire** — roughly 0.59 GB of monthly
  fields, 3.6 GB of daily Secchi depth, and 25.8 GB of hourly waves. Budget several
  hours on a normal connection. The artifact that results is about **170 MB on disk**.

## Run it

    micromamba run -n shiny pip install -e ".[spatial]"
    micromamba run -n shiny python scripts/refresh_layers.py --years 2016 2025 --wave-years 2023 2025

## Check it worked

    micromamba run -n shiny python -m pytest tests/test_refresh_fixture.py -q

Then confirm the new pair verifies:

    micromamba run -n shiny python -c "from pathlib import Path; from seagarden_dst.refresh.writer import load_verified; m,a = load_verified(Path('data')); print(m.artifact_bytes, m.artifact_sha256)"

## Deposit it, and record the DOI

The build leaves every layer `archive.status: pending`. That is correct and expected —
no DOI exists until the deposit happens.

1. Upload `data/forcing.nc` and `data/manifest.json` to Zenodo under the institutional
   account.
2. Publish, and copy the DOI.
3. Record it: `python -c "from pathlib import Path; from seagarden_dst.refresh.zenodo import record_doi; record_doi(Path('data'), '10.5281/zenodo.XXXXXXX')"`
4. Commit the updated `manifest.json`.

**The deposited manifest and the committed manifest differ by the DOI field.** The
committed one is authoritative for provenance; the deposited copy is a snapshot of the
moment before the DOI existed. `artifact_sha256` is unaffected — the artifact did not
change.

## What the baseline gives you

Ten years are carried, **nine are usable for wrapping windows**. A window opened in year
Y takes January from Y+1 and blocks when Y+1 is absent, so 2025 cannot open a sugar kelp
Oct–Jun window in a 2016–2025 artifact. That is correct behaviour, not a bug: the design
chose blocking over silently substituting another year.

## When it fails

| What you see | What it means | What to do |
|---|---|---|
| A layer raises during build | The whole refresh fails by design; no partial artifact is written | Fix the layer, re-run. The previous pair is still valid. |
| `ArtifactMismatch` on read | The pair is torn — an interrupt between the two renames | Re-run the refresh; it repairs itself |
| `artifact_schema_version ... is not 1` | The artifact and the code disagree about shape | Do not edit the manifest. Rebuild with matching code |
| Probe job red | An upstream source moved or died | See the job log; it blocks no pull request |

## Who to contact

<FILL IN: names and roles>
```

> **Note for the implementer:** the two `<FILL IN>` markers are the only places in this
> plan where a placeholder is correct — they need facts only the institution has. Ask
> before shipping the runbook; do not invent them.

- [ ] **Step 2: Write the probe workflow**

Create `.github/workflows/source-probe.yml`:

```yaml
name: source probe

# Separate from ci.yml on purpose. This asks whether third-party sources still exist;
# it must be able to go red without blocking a single pull request. Gating merges on the
# continued existence of Copernicus would make every PR hostage to someone else's uptime.
on:
  schedule:
    - cron: "0 6 1 * *"   # 06:00 UTC on the 1st of each month
  workflow_dispatch:

jobs:
  probe:
    name: are the sources still there
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - uses: actions/setup-python@v6
        with:
          python-version: "3.13"
      - name: Install
        run: pip install -e ".[spatial]"
      - name: Probe
        env:
          COPERNICUSMARINE_SERVICE_USERNAME: ${{ secrets.CMEMS_USERNAME }}
          COPERNICUSMARINE_SERVICE_PASSWORD: ${{ secrets.CMEMS_PASSWORD }}
        # Metadata calls only - no bulk transfer.
        run: python scripts/refresh_layers.py --probe
```

- [ ] **Step 3: Verify and commit**

```bash
micromamba run -n shiny python -m pytest -q
micromamba run -n shiny ruff check .
git add docs/runbooks/annual-refresh.md .github/workflows/source-probe.yml
git commit -m "Package C: the refresh runbook and the source-probe job

The runbook carries the transfer volumes (~30 GB) and runtime, because a
runbook that does not say so is one somebody abandons halfway - which is the
key-person risk section 4.1 exists to mitigate. It also states that the
deposited and committed manifests differ by the DOI field, and that ten years
carried gives nine usable for wrapping windows.

The probe job is a separate workflow from ci.yml so a dead upstream source can
go red without blocking a pull request."
```

- [ ] **Step 4: The clause nobody can self-certify**

Hand the runbook to somebody who did not write it and have them follow it end to end.
This is §8's done-when and it is the only one the implementer cannot discharge. Record
the outcome — including anything they had to ask about — in the pull request.

---

## Self-Review

**Spec coverage.** C§1 decisions → Tasks 7–10 (baselines, sources) and Task 11 (no deposit). C§2 EMODnet rationale → Task 10. C§3.1 extent and resolution → Task 3. C§3.2 variables and shapes → Tasks 7–10, assembled in Task 4. C§3.3 `surface_par` absent → Task 4's `ABSENT_FIELDS`, asserted in Task 5. C§3.4 daily `zsd` → Task 8. C§3.5 single `valid` field → Task 4. C§4 manifest → Task 1. C§4.2 `absent` block → Tasks 4 and 5. C§4.3 Pydantic → Task 1. C§5 layer protocol → Task 3. C§6 atomicity → Task 2. C§6.1 failure modes → Tasks 2 and 12's table. C§7 fixture → Task 5. C§8.1 runbook → Task 12. C§8.2 probe → Tasks 6 and 12. C§10 done-when clauses 1–11 → Tasks 5, 6, 11, 12. C§11.1 dataset versions → Tasks 7–9.

**Not covered, deliberately:** C§11's amendments to the *governing* design document are documentation edits, not implementation, and belong in the pull request rather than a task. Package D's two inherited items (the NaN-depth defect, the temperature mapping) are D's.

**Placeholder scan:** two `<FILL IN>` markers in the runbook, flagged inline as the only correct placeholders — they need institutional facts. No others.

**Type consistency:** `GridSpec` is the Pydantic model from Task 1 throughout, including `BALTIC_GRID` and `FIXTURE_GRID`. `Layer.build(grid, workdir)` matches every implementation. `monthly_by_year(ds, years)` defined in Task 7, imported by Task 8. `add_valid_field(ds, contributing)` defined in Task 4, used in Task 5. `write_pair(ds, manifest_fields, directory)` defined in Task 2, used in Tasks 4 and 5. `load_verified(directory) -> (Manifest, Path)` defined in Task 2, used in Tasks 5 and 11.

**One risk carried forward:** Task 10's WCS fetch is the least-verified code in this plan — EMODnet has no client of the shape the Copernicus layers use. Its aggregation is tested offline precisely so that a broken fetch can be fixed without touching the part that carries the science.
