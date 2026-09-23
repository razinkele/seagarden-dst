# Package E-a — Forcing Selection: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The app runs on the forcing artifact when one is present and readable, on the placeholder otherwise, and always says which, with the year and build date.

**Architecture:** A `ForcingChoice` record and a `region_query` helper in `forcing.py` (core, no spatial stack); a never-raising `select_forcing` in `gridded.py` that names every way of falling back; a `source_note` on `SiteContext` for sites that fall back while the session runs on the artifact; the app choosing once per session, committing sites through `from_reading` when it can, passing the chosen source to `assess_site`, and a banner and report line that take the choice.

**Tech Stack:** Python 3.11+, dataclasses, Shiny for Python, pytest; xarray/h5netcdf only behind the existing lazy import in `gridded.py`.

**Spec:** `docs/superpowers/specs/2026-09-22-package-e-a-forcing-selection-design.md` (E§2 decisions, E§3 components, E§6 tests, E§8 done-when). Above it: the data-layer design §7 and the D-a design D§2–D§6, D§9.

## Global Constraints

- **Nothing under `app/` or in `forcing.py`/`contracts.py` imports xarray, rasterio or `shiny_deckgl` at module scope.** `gridded.py` keeps its lazy `import xarray` inside `from_directory`; `select_forcing` may import nothing new at module scope. The guard tests `test_no_app_module_imports_shiny_deckgl_at_module_scope` and `test_no_core_module_imports_refresh` stay green.
- **Tests that open the fixture are marked `@pytest.mark.spatial` and live under `tests/`.** CI's `[app,dev]` job has no xarray and the spatial job does not collect `app/tests`. Default-selection tests use fakes.
- **The banner property the smoke test already pins holds:** the word "placeholder" appears in the placeholder banner and never in the artifact banner.
- `select_forcing` **never raises**. Reason strings are exactly the table in Task 2; each has a test with `match=` on a fragment unique to its row.
- The placeholder's query year is `2024` (today's `from_region` default), named once as `PLACEHOLDER_YEAR`.
- "Use this site" remains the only commit; the choice is per session and is not reset by stale-assessment invalidation.
- Local runs: `MKL_THREADING_LAYER=SEQUENTIAL` on every Python invocation; `GDAL_DATA=C:\Users\arturas.baziukas\micromamba\envs\shiny\Library\share\gdal` for spatial tests; `-p no:cacheprovider`; ruff clean at line length 100; use `tmp_path`.
- Test discrimination standard: negative tests assert `match=` on a fragment unique to the rule; record actual pytest output, never "verified"; commit implementation before mutation proofs.
- Never `git add` anything under `.superpowers/`.

## Shipped interfaces this plan consumes — read, not remembered

| Thing | Fact |
|---|---|
| `SiteQuery` (`forcing.py:209`) | frozen: `geometry_wkt: str`, `year: int`, `region: str | None = None` |
| `SiteReading` (`forcing.py:223`) | `conditions, coverage, year, aggregation, nearest_valid_km=None, from_artifact=False, stale_months=None` |
| `SiteCoordinate` (`forcing.py:159`) | frozen: `lat, lon, provenance, depth_m=None, checked_on=None, note=""` |
| `SITE_COORDINATES` (`forcing.py:262`) | `dict[str, SiteCoordinate]`; has `DK-belt, DE-coastal, PL-coastal, PL-lagoon, LT-lagoon`; lacks `EE-coastal, LT-coastal` |
| `PlaceholderForcing`, `DEFAULT_FORCING` (`forcing.py:615`, `:642`) | `reading_at` raises `KeyError` for an unknown region, never blocks |
| `ForcingSource` protocol (`forcing.py:596`) | `reading_at(query)`, `daily_forcing(site, window, year)` |
| `GriddedForcing` (`gridded.py:48`) | `__init__(manifest, dataset)`; `self._manifest`, `self._years: list[int]`; `from_directory(directory)` does `import xarray`, `load_pair`, schema check raising `ValueError`, opens with h5netcdf |
| `artifact_directory()` (`gridded.py:44`) | `Path(os.environ.get("SEAGARDEN_DATA_DIR", "data/forcing"))` |
| `load_pair` (`artifact/pair.py:56`) | reads `manifest.json` (`FileNotFoundError` when absent), raises `ValueError("artifact_sha256 mismatch ...")` on a torn pair |
| `Manifest.built_on` (`manifest.py:141`) | `datetime` |
| `ARTIFACT_SCHEMA_VERSION` (`artifact/manifest.py`) | the supported version |
| `SiteContext` (`contracts.py:31`) | mutable dataclass; fields `region, conditions, geometry_wkt="", label="", confidence="low", activities, protection, coverage, nearest_valid_km, from_artifact=False`; `from_region(region, *, label, forcing=DEFAULT_FORCING, year=2024)`; `from_reading(reading, *, label, geometry_wkt)` |
| `SiteAssessment.to_dict()` (`contracts.py:174`) | nests `"site"` from the context |
| `AppState` (`app/state.py`) | `_DEFAULTS` dict is the single source of truth; `test_state_defaults_match_the_single_source_of_truth` reads it |
| `app/app.py` `server()` | `data_source_slot()` computes `from_artifact` and calls `data_source_banner(from_artifact=...)` |
| `app/modules/site.py:_set_site` | `state.context.set(SiteContext.from_region(region, label=label))` |
| `app/modules/results.py:run_assessment(state)` | calls `assess_site(context, species=, methods=, scale=, eutropy=, bowtie=)`; never passes `forcing=` |
| `app/modules/report.py` | `render_report(assessment)`, `_data_source_line(from_artifact)`, `_data_source_caveat(from_artifact)`; `report_server` renders `render_report(state.assessment.get())` |
| `app/modules/_widgets.py:data_source_banner(*, from_artifact)` | the boolean form this plan replaces |
| `app/tests/test_app_smoke.py` | `_Value`, `_FakeState` (no `forcing` attribute yet); `test_the_banner_names_what_the_tool_is_running_on` |
| Fixture | `tests/fixtures/data`: 3×3 grid at 54.0–54.05 N, 20.0–20.083 E, years `[2024, 2025]`, cell `[0,0]` invalid, `[1,1]` valid |

## File structure

| File | Responsibility |
|---|---|
| `src/seagarden_dst/forcing.py` | **Modify.** `PLACEHOLDER_YEAR`, `ForcingChoice`, `placeholder_choice()`, `SiteCoordinate.as_wkt()`, `region_query()` |
| `src/seagarden_dst/artifact/pair.py` | **Modify.** `TornPair(ValueError)` raised on checksum mismatch |
| `src/seagarden_dst/gridded.py` | **Modify.** `UnrecognisedSchema(ValueError)`, `GriddedForcing.years`, `select_forcing()` |
| `src/seagarden_dst/contracts.py` | **Modify.** `SiteContext.source_note`; `from_region` default year uses `PLACEHOLDER_YEAR` |
| `app/modules/_widgets.py` | **Modify.** `data_source_banner(choice, context=None)` |
| `app/modules/report.py` | **Modify.** `render_report(assessment, choice=None)`; data-source line and caveat from the choice |
| `app/state.py` | **Modify.** `forcing` reactive value |
| `app/app.py` | **Modify.** fill `state.forcing` once; banner from the choice |
| `app/modules/site.py` | **Modify.** `build_site_context(region, label, choice)`; `_set_site` uses it |
| `app/modules/results.py` | **Modify.** `forcing_for(context, choice)`; `run_assessment` passes `forcing=` |
| `tests/test_forcing_choice.py` | **Create.** Default selection: record, helpers, `region_query`, `as_wkt` |
| `tests/test_select_forcing.py` | **Create.** Spatial: the reason table against the fixture; default: the no-xarray row |
| `app/tests/test_app_smoke.py` | **Modify.** banner, `_FakeState.forcing`, `build_site_context`, `forcing_for`, state default |
| `README.md`, `CHANGELOG.md` | **Modify.** stub row, Unreleased |

---

### Task 1: `ForcingChoice`, `region_query`, `as_wkt` (core, no spatial stack)

**Files:**
- Modify: `src/seagarden_dst/forcing.py`
- Modify: `src/seagarden_dst/contracts.py` (the `from_region` default year only)
- Test: `tests/test_forcing_choice.py`

**Interfaces:**
- Produces:
  - `PLACEHOLDER_YEAR: int = 2024`
  - `@dataclass(frozen=True) class ForcingChoice: source: ForcingSource; kind: Literal["artifact", "placeholder"]; reason: str; year: int; built_on: datetime | None; directory: Path | None` with `@property is_artifact -> bool`
  - `placeholder_choice(reason: str, directory: Path | None = None) -> ForcingChoice`
  - `SiteCoordinate.as_wkt(self) -> str` → `f"POINT ({lon} {lat})"`
  - `region_query(region: str, year: int) -> SiteQuery | None`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_forcing_choice.py
"""The record naming what the tool runs on, and the region-to-query helper (E§3.1, E§3.3)."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from seagarden_dst.forcing import (
    DEFAULT_FORCING,
    PLACEHOLDER_YEAR,
    SITE_COORDINATES,
    ForcingChoice,
    SiteQuery,
    placeholder_choice,
    region_query,
)


def test_the_placeholder_year_is_the_scaffolds_fixed_year():
    assert PLACEHOLDER_YEAR == 2024


def test_a_placeholder_choice_carries_its_reason_and_no_build_date():
    choice = placeholder_choice("no artifact at data/forcing", Path("data/forcing"))
    assert choice.kind == "placeholder" and choice.is_artifact is False
    assert choice.source is DEFAULT_FORCING
    assert choice.reason == "no artifact at data/forcing"
    assert choice.year == PLACEHOLDER_YEAR
    assert choice.built_on is None
    assert choice.directory == Path("data/forcing")


def test_the_choice_is_frozen():
    choice = placeholder_choice("x")
    with pytest.raises(dataclasses.FrozenInstanceError):
        choice.kind = "artifact"  # type: ignore[misc]


def test_an_artifact_choice_has_no_reason():
    with pytest.raises(ValueError, match="artifact choice carries no reason"):
        ForcingChoice(
            source=DEFAULT_FORCING, kind="artifact", reason="why?", year=2025,
            built_on=None, directory=None,
        )


def test_a_placeholder_choice_must_say_why():
    with pytest.raises(ValueError, match="placeholder choice must say why"):
        ForcingChoice(
            source=DEFAULT_FORCING, kind="placeholder", reason="", year=2024,
            built_on=None, directory=None,
        )


def test_a_coordinate_renders_as_wkt_lon_then_lat():
    assert SITE_COORDINATES["LT-lagoon"].as_wkt() == (
        f"POINT ({SITE_COORDINATES['LT-lagoon'].lon} {SITE_COORDINATES['LT-lagoon'].lat})"
    )


def test_a_region_with_a_coordinate_becomes_a_point_query_carrying_the_region():
    query = region_query("LT-lagoon", 2025)
    assert query == SiteQuery(
        geometry_wkt=SITE_COORDINATES["LT-lagoon"].as_wkt(), year=2025, region="LT-lagoon"
    )


@pytest.mark.parametrize("region", ["LT-coastal", "EE-coastal"])
def test_a_region_without_a_coordinate_yields_none_not_an_empty_geometry(region):
    assert region not in SITE_COORDINATES
    assert region_query(region, 2025) is None


def test_from_region_defaults_to_the_placeholder_year():
    import inspect

    from seagarden_dst import SiteContext

    assert inspect.signature(SiteContext.from_region).parameters["year"].default == PLACEHOLDER_YEAR
```

- [ ] **Step 2: Run to verify they fail**

Run: `MKL_THREADING_LAYER=SEQUENTIAL python -m pytest tests/test_forcing_choice.py -q -p no:cacheprovider`
Expected: collection error `ImportError: cannot import name 'PLACEHOLDER_YEAR'`.

- [ ] **Step 3: Implement**

In `forcing.py`, add to the imports `from datetime import date, datetime`, `from pathlib import Path`, `from typing import Literal, Protocol, runtime_checkable`. After `SiteCoordinate`'s `is_sited` property:

```python
    def as_wkt(self) -> str:
        """`POINT (lon lat)`: WKT's axis order, which is the opposite of the human habit."""
        return f"POINT ({self.lon} {self.lat})"
```

After `SITE_COORDINATES` (so it can reference it) and after `SiteQuery` is defined, add:

```python
def region_query(region: str, year: int) -> SiteQuery | None:
    """A POINT query for a region with a coordinate; None for one without.

    None, not an empty geometry: D§9 withdrew the "empty means the region's
    coordinate" convention, and the reader refuses an empty string. The caller
    decides what a None means (E§2: that site stays on the placeholder).
    """
    coordinate = SITE_COORDINATES.get(region)
    if coordinate is None:
        return None
    return SiteQuery(geometry_wkt=coordinate.as_wkt(), year=year, region=region)
```

Immediately after `DEFAULT_FORCING`:

```python
#: The scaffold has one invented seasonal cycle, not one per year; this is the year
#: it answers to, and the query year the app uses when it runs on the placeholder.
PLACEHOLDER_YEAR = 2024


@dataclass(frozen=True)
class ForcingChoice:
    """What the tool is running on this session, and why (E§3.1).

    `kind` and `reason` are what the banner shows. A silent fallback is the failure
    §7 forbids, so a placeholder choice must say why and an artifact choice may not
    carry a reason that would read as one.
    """

    source: ForcingSource
    kind: Literal["artifact", "placeholder"]
    reason: str
    year: int
    built_on: datetime | None
    directory: Path | None

    def __post_init__(self) -> None:
        if self.kind == "artifact" and self.reason:
            raise ValueError("an artifact choice carries no reason; the reason is for fallbacks")
        if self.kind == "placeholder" and not self.reason:
            raise ValueError("a placeholder choice must say why the artifact was not used")

    @property
    def is_artifact(self) -> bool:
        return self.kind == "artifact"


def placeholder_choice(reason: str, directory: Path | None = None) -> ForcingChoice:
    return ForcingChoice(
        source=DEFAULT_FORCING, kind="placeholder", reason=reason,
        year=PLACEHOLDER_YEAR, built_on=None, directory=directory,
    )
```

In `contracts.py`, import `PLACEHOLDER_YEAR` from `seagarden_dst.forcing` and change `from_region`'s `year: int = 2024` to `year: int = PLACEHOLDER_YEAR`.

- [ ] **Step 4: Run to verify they pass; run the default suite; ruff**

Run: `MKL_THREADING_LAYER=SEQUENTIAL python -m pytest tests/test_forcing_choice.py -q -p no:cacheprovider` → 10 passed. Then the full default suite and `python -m ruff check .`.

- [ ] **Step 5: Commit**

```bash
git add src/seagarden_dst/forcing.py src/seagarden_dst/contracts.py tests/test_forcing_choice.py
git commit -m "feat(forcing): ForcingChoice names what the tool runs on; region_query turns a marker into a POINT (E§3.1, E§3.3)"
```

---

### Task 2: `select_forcing`, the reason table, and typed refusals

**Files:**
- Modify: `src/seagarden_dst/artifact/pair.py`, `src/seagarden_dst/gridded.py`
- Test: `tests/test_select_forcing.py`

**Interfaces:**
- Produces:
  - `class TornPair(ValueError)` in `pair.py`; `load_pair` raises it on a sha mismatch (message unchanged)
  - `class UnrecognisedSchema(ValueError)` in `gridded.py`; `from_directory` raises it (message unchanged)
  - `GriddedForcing.years -> list[int]` (sorted copy of the year coordinate)
  - `select_forcing(directory: Path | None = None) -> ForcingChoice`

Reason table (exact strings; `{d}` is the directory as given):

| Row | `reason` |
|---|---|
| no manifest | `no artifact at {d}` |
| torn pair | `artifact at {d} failed its checksum; refusing to read it` |
| schema | `artifact at {d} has schema version {found}; this build reads {ARTIFACT_SCHEMA_VERSION}` |
| no spatial stack | `this install has no spatial extra (xarray/h5netcdf), so the artifact at {d} cannot be read` |
| anything else | `could not open the artifact at {d}: {ExcType}: {exc}` |

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_select_forcing.py
"""select_forcing never raises, and every fallback names its reason (E§3.2)."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

from seagarden_dst.artifact.manifest import ARTIFACT_SCHEMA_VERSION
from seagarden_dst.forcing import PLACEHOLDER_YEAR

FIXTURE = Path("tests/fixtures/data")


# --- default selection: needs no xarray ------------------------------------------------


def test_a_missing_directory_falls_back_naming_it(tmp_path):
    from seagarden_dst.gridded import select_forcing

    missing = tmp_path / "nowhere"
    choice = select_forcing(missing)
    assert choice.kind == "placeholder"
    assert choice.reason == f"no artifact at {missing}"
    assert choice.year == PLACEHOLDER_YEAR and choice.directory == missing


def test_without_the_spatial_stack_the_reason_names_the_extra(tmp_path, monkeypatch):
    from seagarden_dst.gridded import select_forcing

    # A manifest is present, so only the import can fail. Setting the module to None
    # makes `import xarray` raise ImportError, which is what a pip-only install does.
    shutil.copytree(FIXTURE, tmp_path / "data")
    monkeypatch.setitem(sys.modules, "xarray", None)
    choice = select_forcing(tmp_path / "data")
    assert choice.kind == "placeholder"
    assert choice.reason.startswith("this install has no spatial extra")
    assert str(tmp_path / "data") in choice.reason


def test_select_forcing_defaults_to_the_locator(monkeypatch, tmp_path):
    from seagarden_dst.gridded import select_forcing

    monkeypatch.setenv("SEAGARDEN_DATA_DIR", str(tmp_path / "elsewhere"))
    choice = select_forcing()
    assert choice.directory == tmp_path / "elsewhere"
    assert choice.reason == f"no artifact at {tmp_path / 'elsewhere'}"


# --- spatial: the fixture ---------------------------------------------------------------


@pytest.mark.spatial
def test_the_fixture_is_chosen_as_the_artifact_with_its_latest_year():
    pytest.importorskip("xarray")
    from seagarden_dst.gridded import GriddedForcing, select_forcing

    choice = select_forcing(FIXTURE)
    assert choice.kind == "artifact" and choice.is_artifact
    assert choice.reason == ""
    assert choice.year == 2025
    assert isinstance(choice.source, GriddedForcing)
    assert choice.source.years == [2024, 2025]
    manifest = json.loads((FIXTURE / "manifest.json").read_text(encoding="utf-8"))
    assert choice.built_on.isoformat().startswith(manifest["built_on"][:19])
    assert choice.directory == FIXTURE


@pytest.mark.spatial
def test_a_torn_pair_falls_back_naming_the_checksum(tmp_path):
    pytest.importorskip("xarray")
    from seagarden_dst.artifact.pair import TornPair, load_pair
    from seagarden_dst.gridded import select_forcing

    shutil.copytree(FIXTURE, tmp_path / "data")
    artifact = tmp_path / "data" / "forcing.nc"
    data = bytearray(artifact.read_bytes())
    data[-1] ^= 0xFF
    artifact.write_bytes(bytes(data))
    with pytest.raises(TornPair):
        load_pair(tmp_path / "data")
    choice = select_forcing(tmp_path / "data")
    assert choice.kind == "placeholder"
    assert choice.reason == f"artifact at {tmp_path / 'data'} failed its checksum; refusing to read it"


@pytest.mark.spatial
def test_an_unrecognised_schema_falls_back_naming_both_versions(tmp_path):
    pytest.importorskip("xarray")
    from seagarden_dst.gridded import UnrecognisedSchema, select_forcing

    shutil.copytree(FIXTURE, tmp_path / "data")
    manifest_path = tmp_path / "data" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifact_schema_version"] = 99
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert issubclass(UnrecognisedSchema, ValueError)
    choice = select_forcing(tmp_path / "data")
    assert choice.kind == "placeholder"
    assert choice.reason == (
        f"artifact at {tmp_path / 'data'} has schema version 99; "
        f"this build reads {ARTIFACT_SCHEMA_VERSION}"
    )


@pytest.mark.spatial
def test_any_other_failure_is_named_not_swallowed(tmp_path, monkeypatch):
    pytest.importorskip("xarray")
    from seagarden_dst import gridded

    shutil.copytree(FIXTURE, tmp_path / "data")

    def boom(cls, directory):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(gridded.GriddedForcing, "from_directory", classmethod(boom))
    choice = gridded.select_forcing(tmp_path / "data")
    assert choice.kind == "placeholder"
    assert choice.reason == (
        f"could not open the artifact at {tmp_path / 'data'}: RuntimeError: disk on fire"
    )


@pytest.mark.spatial
def test_a_point_in_the_fixture_reads_from_the_artifact_through_the_choice():
    pytest.importorskip("xarray")
    from seagarden_dst import SiteContext
    from seagarden_dst.forcing import SiteQuery
    from seagarden_dst.gridded import select_forcing

    choice = select_forcing(FIXTURE)
    reader = choice.source
    lat, lon = reader.latitudes[1], reader.longitudes[1]  # the valid cell
    reading = reader.reading_at(SiteQuery(f"POINT ({lon} {lat})", year=choice.year))
    assert reading.from_artifact is True
    context = SiteContext.from_reading(reading, label="fixture cell")
    assert context.from_artifact is True
    assert context.source_note == ""
```

Note the last test needs `source_note` from Task 3; it will fail on `AttributeError` until then. Write it now, expect it red through Task 2, green after Task 3, and say so in the report.

Also note the schema-version test: `Manifest.model_validate` may reject `99` if the field is constrained. Check `manifest.py`; if it is a `Literal`, write the bad manifest with a value the model accepts but `from_directory` refuses, or, if every accepted value is the current one, change the test to monkeypatch `gridded.ARTIFACT_SCHEMA_VERSION` to `2` so the fixture's `1` is "unrecognised", and adjust the expected string accordingly (`has schema version 1; this build reads 2`).

- [ ] **Step 2: Run to verify they fail**

Default: `... tests/test_select_forcing.py -q` → the three default tests fail with `ImportError: cannot import name 'select_forcing'`. Spatial: `... -m spatial tests/test_select_forcing.py` → the same, plus `TornPair`/`UnrecognisedSchema` import errors.

- [ ] **Step 3: Implement**

`pair.py`: add `class TornPair(ValueError): """The manifest does not describe the artifact beside it (C§6)."""` above `load_pair`, and change the `raise ValueError(` in the mismatch branch to `raise TornPair(`.

`gridded.py`: imports gain `from datetime import datetime` (if not present) and `from seagarden_dst.artifact.pair import TornPair, load_pair`; from `seagarden_dst.forcing` import also `ForcingChoice, placeholder_choice`. Add:

```python
class UnrecognisedSchema(ValueError):
    """The artifact's schema version is not the one this build reads (§7)."""
```

and in `from_directory` change `raise ValueError(` to `raise UnrecognisedSchema(`. Add to the class:

```python
    @property
    def years(self) -> list[int]:
        """The years the artifact carries, ascending."""
        return sorted(self._years)
```

Add at module level, after the class:

```python
def select_forcing(directory: Path | None = None) -> ForcingChoice:
    """Choose what the tool runs on this session (E§3.2). Never raises.

    Every way of falling back yields the placeholder with a reason that names the
    directory, so the banner can say why. The manifest's presence is checked before
    the import so a pip-only install with no artifact reports the missing artifact,
    which is the more useful of its two problems.
    """
    directory = Path(directory) if directory is not None else artifact_directory()
    if not (directory / "manifest.json").exists():
        return placeholder_choice(f"no artifact at {directory}", directory)
    try:
        reader = GriddedForcing.from_directory(directory)
    except ImportError:
        return placeholder_choice(
            f"this install has no spatial extra (xarray/h5netcdf), so the artifact at "
            f"{directory} cannot be read",
            directory,
        )
    except TornPair:
        return placeholder_choice(
            f"artifact at {directory} failed its checksum; refusing to read it", directory
        )
    except UnrecognisedSchema as exc:
        found = _schema_version_in(exc)
        return placeholder_choice(
            f"artifact at {directory} has schema version {found}; this build reads "
            f"{ARTIFACT_SCHEMA_VERSION}",
            directory,
        )
    except Exception as exc:  # noqa: BLE001 - named in the reason, never swallowed
        return placeholder_choice(
            f"could not open the artifact at {directory}: {type(exc).__name__}: {exc}",
            directory,
        )
    return ForcingChoice(
        source=reader, kind="artifact", reason="", year=reader.years[-1],
        built_on=reader._manifest.built_on, directory=directory,
    )
```

For `_schema_version_in`, prefer giving `UnrecognisedSchema` a `found: int` attribute set at raise time (`raise UnrecognisedSchema(found=manifest.artifact_schema_version, message=...)` with a small `__init__`) over parsing the message; then `found = exc.found`. Either way, no regex on prose.

- [ ] **Step 4: Run both selections; ruff; commit**

Default: 3 passed. Spatial: 5 passed, 1 failed (`source_note`, expected until Task 3). Full default suite green; existing `tests/test_gridded.py::test_the_reader_refuses_an_unrecognised_schema_version` and `tests/test_refresh_fixture.py::test_a_torn_pair_is_refused` still pass because both new classes subclass `ValueError`.

```bash
git add src/seagarden_dst/artifact/pair.py src/seagarden_dst/gridded.py tests/test_select_forcing.py
git commit -m "feat(gridded): select_forcing chooses the artifact or the placeholder and names why (E§3.2)"
```

---

### Task 3: `source_note`, the banner, and the report line from the choice

**Files:**
- Modify: `src/seagarden_dst/contracts.py`, `app/modules/_widgets.py`, `app/modules/report.py`
- Test: `app/tests/test_app_smoke.py`, `tests/test_forcing_choice.py`

**Interfaces:**
- Produces:
  - `SiteContext.source_note: str = ""` (after `from_artifact`); `to_dict()` carries it via `asdict`
  - `SOURCE_NOTE_NO_POSITION = "no confirmed position; conditions are the sub-region placeholder"` in `contracts.py`
  - `data_source_banner(choice: ForcingChoice, context: SiteContext | None = None) -> str`
  - `render_report(assessment, choice: ForcingChoice | None = None) -> str`; `_data_source_line(choice, context)`, `_data_source_caveat(choice, context)`

Banner text, exactly:
- artifact: `Data source: gridded forcing artifact, conditions for {year}, built {built_on:%Y-%m-%d}.`
- placeholder: `Data source: placeholder conditions — plausible order-of-magnitude values, not measurements ({reason}).`
- with a context whose `source_note` is set, append ` This site: {source_note}.`
- `choice=None` in `render_report` means "unknown": the line falls back to the old boolean wording from `context.from_artifact`, so callers that predate E-a (the smoke tests' `render_report(assessment)`) keep working.

- [ ] **Step 1: Write the failing tests**

In `app/tests/test_app_smoke.py`, replace `test_the_banner_names_what_the_tool_is_running_on` with:

```python
def _artifact_choice():
    from datetime import UTC, datetime

    from seagarden_dst.forcing import DEFAULT_FORCING, ForcingChoice

    return ForcingChoice(
        source=DEFAULT_FORCING, kind="artifact", reason="", year=2025,
        built_on=datetime(2026, 9, 22, tzinfo=UTC), directory=None,
    )


def test_the_banner_names_what_the_tool_is_running_on():
    """§7 row 1: fall back to PlaceholderForcing WITH A BANNER naming the source. A
    silent fallback is the failure — the user cannot tell measurements from inventions."""
    from seagarden_dst.forcing import placeholder_choice
    from app.modules._widgets import data_source_banner

    placeholder = data_source_banner(placeholder_choice("no artifact at data/forcing"))
    assert "placeholder" in placeholder.lower()
    assert "(no artifact at data/forcing)" in placeholder
    artifact = data_source_banner(_artifact_choice())
    assert "placeholder" not in artifact.lower()
    assert "conditions for 2025" in artifact and "built 2026-09-22" in artifact


def test_the_banner_appends_a_sites_own_fallback_note():
    from app.modules._widgets import data_source_banner
    from seagarden_dst import SiteContext

    context = SiteContext.from_region("LT-coastal", label="Melnrage")
    context.source_note = "no confirmed position; conditions are the sub-region placeholder"
    text = data_source_banner(_artifact_choice(), context)
    assert text.endswith("This site: no confirmed position; conditions are the sub-region placeholder.")


def test_the_report_line_takes_the_choice_and_falls_back_to_the_context_without_one():
    from app.modules.report import render_report
    from seagarden_dst.forcing import placeholder_choice

    state = _FakeState(SiteContext.from_region("LT-coastal", label="Melnrage"))
    run_assessment(state)
    with_choice = render_report(state.assessment.get(), placeholder_choice("no artifact at x"))
    assert "Data source: placeholder conditions (no artifact at x)" in with_choice
    without = render_report(state.assessment.get())
    assert "Data source: placeholder conditions" in without


def test_source_note_reaches_the_json_export():
    state = _FakeState(SiteContext.from_region("LT-coastal", label="Melnrage"))
    state.context.get().source_note = "no confirmed position; conditions are the sub-region placeholder"
    run_assessment(state)
    assert state.assessment.get().to_dict()["site"]["source_note"].startswith("no confirmed position")
```

In `tests/test_forcing_choice.py` add:

```python
def test_a_context_carries_an_empty_source_note_by_default():
    from seagarden_dst import SiteContext
    from seagarden_dst.contracts import SOURCE_NOTE_NO_POSITION

    context = SiteContext.from_region("LT-lagoon")
    assert context.source_note == ""
    assert SOURCE_NOTE_NO_POSITION == "no confirmed position; conditions are the sub-region placeholder"
```

- [ ] **Step 2: Run to verify they fail**

Expected: `TypeError` on the banner's new positional argument; `AttributeError: source_note`; `ImportError` for `SOURCE_NOTE_NO_POSITION`.

- [ ] **Step 3: Implement**

`contracts.py`: after `from_artifact: bool = False` add `source_note: str = ""` with a docstring line ("why this site is on the placeholder while the session runs on the artifact; empty otherwise"); add the module constant `SOURCE_NOTE_NO_POSITION`.

`_widgets.py`:

```python
def data_source_banner(choice: ForcingChoice, context: SiteContext | None = None) -> str:
    """Sentence naming what the app is running on, and why if it is not the artifact."""
    if choice.is_artifact:
        built = choice.built_on.strftime("%Y-%m-%d") if choice.built_on else "unknown date"
        text = (
            f"Data source: gridded forcing artifact, conditions for {choice.year}, "
            f"built {built}."
        )
    else:
        text = (
            "Data source: placeholder conditions — plausible order-of-magnitude values, "
            f"not measurements ({choice.reason})."
        )
    if context is not None and context.source_note:
        text += f" This site: {context.source_note}."
    return text
```

`report.py`: `render_report(assessment, choice=None)`; `_data_source_line(choice, context)` returns `"Data source: gridded forcing artifact, conditions for {year}, built {date}"` / `"Data source: placeholder conditions ({reason})"` when a choice is given, else the two old strings from `context.from_artifact`; append `" — this site: {source_note}"` when set. `_data_source_caveat` likewise takes `(choice, context)` and keeps its two sentences, appending the note. Update the two call sites in `render_report`.

- [ ] **Step 4: Run app tests, both new test files, the default suite; ruff; commit**

The Task 2 spatial test `test_a_point_in_the_fixture_reads_from_the_artifact_through_the_choice` now passes; run `-m spatial tests/test_select_forcing.py` and record it.

```bash
git add src/seagarden_dst/contracts.py app/modules/_widgets.py app/modules/report.py app/tests/test_app_smoke.py tests/test_forcing_choice.py
git commit -m "feat(app): the banner and the report name the source, the year, the build date, and a site's own fallback (E§3.4, E§3.5)"
```

---

### Task 4: The app chooses once, commits through the reader, and assesses with the chosen source

**Files:**
- Modify: `app/state.py`, `app/app.py`, `app/modules/site.py`, `app/modules/results.py`
- Test: `app/tests/test_app_smoke.py`

**Interfaces:**
- Produces:
  - `AppState.forcing: reactive.Value` initialised from `_DEFAULTS["forcing"]`, which is `None`; `server()` sets it once to `select_forcing()`
  - `site.build_site_context(region: str, label: str, choice: ForcingChoice) -> SiteContext`
  - `results.forcing_for(context: SiteContext, choice: ForcingChoice) -> ForcingSource`

- [ ] **Step 1: Write the failing tests**

Update `_FakeState.__init__` to add `self.forcing = _Value(placeholder_choice("test: no artifact"))` (import `placeholder_choice` at the top of the module from `seagarden_dst.forcing`). Add:

```python
def test_state_carries_the_forcing_choice_unset_until_the_session_chooses():
    from shiny import reactive

    state = AppState()
    with reactive.isolate():
        assert state.forcing.get() is None
    assert AppState.defaults()["forcing"] is None


def test_a_region_with_a_coordinate_commits_through_the_readers_reading():
    from app.modules.site import build_site_context
    from seagarden_dst.forcing import (
        DEFAULT_FORCING, Aggregation, Coverage, ForcingChoice, SiteReading, SiteQuery,
    )

    seen: list[SiteQuery] = []

    class _Reader:
        def reading_at(self, query):
            seen.append(query)
            return SiteReading(
                conditions=DEFAULT_FORCING.reading_at(
                    SiteQuery("", year=2024, region="LT-lagoon")
                ).conditions,
                coverage=Coverage.VALID, year=query.year,
                aggregation=Aggregation.CONTAINING_CELL, from_artifact=True,
            )

        def daily_forcing(self, site, window, year):
            return DEFAULT_FORCING.daily_forcing(site, window, year)

    choice = ForcingChoice(
        source=_Reader(), kind="artifact", reason="", year=2025, built_on=None, directory=None
    )
    context = build_site_context("LT-lagoon", "Curonian", choice)
    assert seen and seen[0].region == "LT-lagoon" and seen[0].year == 2025
    assert seen[0].geometry_wkt.startswith("POINT (")
    assert context.from_artifact is True and context.source_note == ""
    assert context.label == "Curonian" and context.region == "LT-lagoon"


def test_a_region_without_a_coordinate_stays_on_the_placeholder_with_a_note():
    from app.modules.site import build_site_context
    from seagarden_dst.contracts import SOURCE_NOTE_NO_POSITION

    context = build_site_context("LT-coastal", "Melnrage", _artifact_choice())
    assert context.from_artifact is False
    assert context.source_note == SOURCE_NOTE_NO_POSITION
    assert context.region == "LT-coastal"


def test_on_the_placeholder_a_site_commits_as_today_with_no_note():
    from app.modules.site import build_site_context
    from seagarden_dst.forcing import placeholder_choice

    context = build_site_context("LT-lagoon", "Curonian", placeholder_choice("no artifact"))
    assert context.from_artifact is False and context.source_note == ""


def test_a_blocked_reading_keeps_the_region_it_was_asked_for():
    from app.modules.site import build_site_context
    from seagarden_dst.forcing import Aggregation, Coverage, ForcingChoice, SiteReading

    class _Blocked:
        def reading_at(self, query):
            return SiteReading(
                conditions=None, coverage=Coverage.CELL_INVALID, year=query.year,
                aggregation=Aggregation.CONTAINING_CELL, nearest_valid_km=2.5,
                from_artifact=True,
            )

        def daily_forcing(self, site, window, year):
            raise AssertionError("not called")

    choice = ForcingChoice(
        source=_Blocked(), kind="artifact", reason="", year=2025, built_on=None, directory=None
    )
    context = build_site_context("LT-lagoon", "Curonian", choice)
    assert context.conditions is None and context.coverage is Coverage.CELL_INVALID
    assert context.region == "LT-lagoon", "the region is known even when the cell is not"


def test_the_assessment_uses_the_chosen_source_unless_the_site_fell_back():
    from app.modules.results import forcing_for
    from seagarden_dst.contracts import SOURCE_NOTE_NO_POSITION
    from seagarden_dst.forcing import DEFAULT_FORCING

    choice = _artifact_choice()
    on_artifact = SiteContext.from_region("LT-lagoon")
    assert forcing_for(on_artifact, choice) is choice.source
    fell_back = SiteContext.from_region("LT-coastal")
    fell_back.source_note = SOURCE_NOTE_NO_POSITION
    assert forcing_for(fell_back, choice) is DEFAULT_FORCING


def test_run_assessment_passes_the_source_through(monkeypatch):
    import app.modules.results as results

    captured = {}

    def fake_assess(context, **kwargs):
        captured.update(kwargs)
        raise RuntimeError("stop here")

    monkeypatch.setattr(results, "assess_site", fake_assess)
    state = _FakeState(SiteContext.from_region("LT-lagoon", label="Curonian"))
    with pytest.raises(RuntimeError, match="stop here"):
        results.run_assessment(state)
    assert captured["forcing"] is state.forcing.get().source
```

`_artifact_choice()` is the helper Task 3 added to the smoke tests; in this test it is built on `DEFAULT_FORCING`, which is fine for `forcing_for` since only identity is checked.

- [ ] **Step 2: Run to verify they fail**

Expected: `AttributeError: 'AppState' object has no attribute 'forcing'`, `ImportError: cannot import name 'build_site_context'`, `cannot import name 'forcing_for'`, and the pass-through test failing on `KeyError: 'forcing'`.

- [ ] **Step 3: Implement**

`app/state.py`: `_DEFAULTS["forcing"] = None` with the comment `# ForcingChoice | None; set once per session by server(), never reset`; `self.forcing: reactive.Value = reactive.Value(_DEFAULTS["forcing"])`.

`app/app.py`: import `select_forcing` from `seagarden_dst.gridded` (module scope is fine: `gridded.py` imports no spatial stack at module scope; confirm with the guard test). In `server()`, right after `state = AppState()`: `state.forcing.set(select_forcing())`. Replace `data_source_slot` with:

```python
    @render.ui
    def data_source_slot():
        choice = state.forcing.get()
        assessment = state.assessment.get()
        context = assessment.context if assessment is not None else state.context.get()
        return ui.p(data_source_banner(choice, context))
```

Also, any place that reads `state.assessment` for the report: `report_server` renders `render_report(state.assessment.get(), state.forcing.get())`, and the `.txt` download does the same (find both call sites in `report.py`).

`app/modules/site.py`: import `SOURCE_NOTE_NO_POSITION` from `seagarden_dst.contracts` and `ForcingChoice, region_query` from `seagarden_dst.forcing`. Add at module level:

```python
def build_site_context(region: str, label: str, choice: ForcingChoice) -> SiteContext:
    """What 'Use this site' commits (E§3.5).

    Through the reader when the session runs on the artifact and the region has a
    coordinate; otherwise through the placeholder as before, with a note when that is
    a fallback rather than the session's normal state. A blocked reading keeps the
    region it was asked for: the cell may be unknown, the sub-region is not.
    """
    query = region_query(region, choice.year) if choice.is_artifact else None
    if query is None:
        context = SiteContext.from_region(region, label=label)
        if choice.is_artifact:
            context.source_note = SOURCE_NOTE_NO_POSITION
        return context
    context = SiteContext.from_reading(choice.source.reading_at(query), label=label)
    if context.region is None:
        context.region = region
    return context
```

and in `_set_site`: `state.context.set(build_site_context(region, label, state.forcing.get()))`.

`app/modules/results.py`: import `DEFAULT_FORCING` and `ForcingChoice`; add

```python
def forcing_for(context, choice: ForcingChoice):
    """The source to assess with: the session's choice, unless this site fell back.

    A context with a `source_note` was built on the placeholder because the reader has
    nothing for it (no coordinate), so its daily series must come from the placeholder
    too, or the growth model integrates one source's seasons over another's conditions.
    """
    return DEFAULT_FORCING if context.source_note else choice.source
```

and pass `forcing=forcing_for(context, state.forcing.get())` in `run_assessment`.

- [ ] **Step 4: Run app tests and the default suite; ruff; commit**

Also run `app/tests/test_app_smoke.py::test_no_app_module_imports_shiny_deckgl_at_module_scope` and `tests/test_refresh_isolation.py` (the core-vs-refresh guard) explicitly.

```bash
git add app/state.py app/app.py app/modules/site.py app/modules/results.py app/tests/test_app_smoke.py
git commit -m "feat(app): choose the forcing once per session, commit sites through the reader, assess with the chosen source (E§3.5, E§4)"
```

---

### Task 5: README stub row and the changelog

**Files:**
- Modify: `README.md` (the "Site conditions" row of "What is stubbed"), `CHANGELOG.md` (`[Unreleased]`)

- [ ] **Step 1: Edit**

README row: keep the row; replace its "Unblocked by" text's opening with: "The app now reads the artifact when `SEAGARDEN_DATA_DIR` (default `data/forcing`) holds a valid pair, and says so in the Site panel; what still gates real conditions is the first refresh on the server (`docs/runbooks/annual-refresh.md`). Until then: placeholder, with the reason shown." Keep the Tagalaht measurement sentences that follow.

CHANGELOG `[Unreleased]`, replacing "Nothing yet.":

```markdown
### Added

- **The app reads the forcing artifact when one is present** (package E-a). The source is
  chosen once per session in the core (`gridded.select_forcing`), never raises, and names
  every way of falling back; the Site panel and the report say which source, which year
  and which build date. Sites whose sub-region has no coordinate stay on the placeholder
  with a note. Nothing about what the tool computes has changed; with no artifact the app
  is today's app with a reason in the banner.
```

- [ ] **Step 2: Run the default suite (the version test reads the changelog); commit**

```bash
git add README.md CHANGELOG.md
git commit -m "docs: the app reads the artifact when one is present; say so in the README and changelog"
```

---

### Task 6: Manual check against the fixture (controller)

Not a subagent task. The controller launches the app with `SEAGARDEN_DATA_DIR=tests/fixtures/data` and, in a scratch script that monkeypatches `SITE_COORDINATES["LT-lagoon"]` to a coordinate inside the fixture's valid cell (54.0167 N, 20.0278 E), assesses that site and screenshots the banner reading "gridded forcing artifact, conditions for 2025". Then relaunches without the variable and confirms the placeholder banner names `data/forcing`. Screenshots go to `.playwright-mcp/` (git-ignored). Findings, if any, become a fix wave.

---

## Self-review

**Spec coverage.** E§3.1 → Task 1. E§3.2 and the reason table → Task 2. E§3.3 → Task 1. E§3.4 → Task 3. E§3.5 (state, site, results, banner, report) → Tasks 3–4. E§4 flow → Task 4. E§5 edge cases: invalid cell → Task 4's blocked-reading test plus the existing unassessable path; no shipped marker in the fixture → Task 6 uses a scratch coordinate. E§6 tests → Tasks 1–4 as listed. E§8 clauses: 1 → Task 2's point test plus Task 6; 2 → Task 3's banner tests and the unchanged smoke tests; 3 → Task 4; 4 → Task 2; 5 → Task 4; 6 → the existing guard tests, run in Task 4; 7 → Task 5.

**Placeholders.** None; every step has its code. Task 2 flags one uncertainty (whether the manifest model accepts `99`) with both resolutions written out.

**Type consistency.** `ForcingChoice(source, kind, reason, year, built_on, directory)` in Tasks 1–4; `placeholder_choice(reason, directory=None)` in Tasks 1–4; `region_query(region, year)` in Tasks 1 and 4; `select_forcing(directory=None)` in Tasks 2 and 4; `data_source_banner(choice, context=None)` in Tasks 3–4; `render_report(assessment, choice=None)` in Tasks 3–4; `build_site_context(region, label, choice)` and `forcing_for(context, choice)` in Task 4.

**Known risk, carried openly.** `from_reading` on a blocked reading sets `region=None`; Task 4 restores the asked-for region on the context. That is a small departure from D-a's "polygon outside every domain gets `region=None`", justified because here the region is known by construction; E-b's drawn polygons will not pass a region and keep D-a's behaviour.
