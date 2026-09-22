"""select_forcing never raises, and every fallback names its reason (E§3.2)."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

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
    assert choice.reason == (
        f"artifact at {tmp_path / 'data'} failed its checksum; refusing to read it"
    )


@pytest.mark.spatial
def test_an_unrecognised_schema_falls_back_naming_both_versions(tmp_path, monkeypatch):
    pytest.importorskip("xarray")
    from seagarden_dst import gridded
    from seagarden_dst.gridded import UnrecognisedSchema, select_forcing

    shutil.copytree(FIXTURE, tmp_path / "data")
    # Manifest.model_validate itself enforces artifact_schema_version == the manifest
    # module's own ARTIFACT_SCHEMA_VERSION (currently 1), so a manifest written with
    # 99 never reaches GriddedForcing.from_directory's own check - it is rejected one
    # layer up, inside load_pair. The fixture's manifest already carries the current
    # version (1); monkeypatching gridded.ARTIFACT_SCHEMA_VERSION to 2 makes that
    # accepted "1" the one this build no longer reads, which is the alternative the
    # task brief names for exactly this situation.
    monkeypatch.setattr(gridded, "ARTIFACT_SCHEMA_VERSION", 2)
    assert issubclass(UnrecognisedSchema, ValueError)
    choice = select_forcing(tmp_path / "data")
    assert choice.kind == "placeholder"
    assert choice.reason == (
        f"artifact at {tmp_path / 'data'} has schema version 1; this build reads 2"
    )


@pytest.mark.spatial
def test_a_newer_schema_in_a_real_manifest_is_named_before_the_model_refuses_it(tmp_path):
    """A manifest from a newer pipeline carries an `artifact_schema_version` the
    installed `Manifest` model itself rejects (`_check_schema_version`), before
    `GriddedForcing.from_directory`'s own check ever runs - so without this guard the
    real-file case falls into `select_forcing`'s catch-all and reports a multi-line
    pydantic dump instead of naming the version, which is what the monkeypatch-based
    `test_an_unrecognised_schema_falls_back_naming_both_versions` above cannot exercise."""
    pytest.importorskip("xarray")
    from seagarden_dst.artifact.manifest import ARTIFACT_SCHEMA_VERSION
    from seagarden_dst.gridded import select_forcing

    shutil.copytree(FIXTURE, tmp_path / "data")
    manifest_path = tmp_path / "data" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifact_schema_version"] = 99
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    choice = select_forcing(tmp_path / "data")
    assert choice.kind == "placeholder"
    assert choice.reason == (
        f"artifact at {tmp_path / 'data'} has schema version 99; this build reads "
        f"{ARTIFACT_SCHEMA_VERSION}"
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
