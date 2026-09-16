import json
import os

import pytest
from pydantic import ValidationError

# `pytestmark` below deselects this module from the default run — but `-m` filters
# AFTER collection, and collection imports the module. In the `.[app,dev]` install
# the xarray import below would raise ModuleNotFoundError at COLLECTION, which no
# marker can reach, taking both CI legs red on every pull request. That is the
# exact outcome C§11 says the mechanism must avoid, so the marker alone does not
# implement it. `importorskip` turns the ImportError into a clean module-level skip.
#
# It must come BEFORE the writer import: `writer.py` imports xarray at module level
# too, so skipping only this module's own xarray import would not help — the name
# is bound here (not a bare `importorskip` call) precisely so nothing downstream
# needs its own `import xarray as xr` that re-triggers the same failure.
xr = pytest.importorskip("xarray")

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
    with pytest.raises(ValueError, match="artifact_sha256 mismatch"):
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

    with pytest.raises(_Boom, match="mid-build"):
        write_pair(broken, reference_manifest, tmp_path, _hook=_explode)

    again, _ = load_pair(tmp_path)
    assert again.artifact_sha256 == first.artifact_sha256


def test_the_artifact_is_replaced_before_the_manifest(
    tmp_path, reference_manifest, tiny_dataset, monkeypatch
):
    """C§6 step 5 before step 6: swapping the two `os.replace` calls must go red.

    None of the other tests distinguish ordering: `_hook` fires before *either*
    replace, the torn-pair test corrupts the manifest by hand after a normal
    write, and the round trip only checks the end state. This records the
    actual sequence of `os.replace` destination basenames.
    """
    calls: list[str] = []
    real_replace = os.replace

    def _recording_replace(src, dst):
        calls.append(os.path.basename(dst))
        return real_replace(src, dst)

    monkeypatch.setattr("seagarden_dst.refresh.writer.os.replace", _recording_replace)

    write_pair(tiny_dataset, reference_manifest, tmp_path)

    assert calls == ["forcing.nc", "manifest.json"]


def test_a_malformed_sha_is_refused_before_it_reaches_disk(
    tmp_path, reference_manifest, tiny_dataset, monkeypatch
):
    """`write_pair` re-validates the stamped manifest via `Manifest.model_validate`
    because `model_copy(update=)` does not re-run validators. That call has
    something to catch only because `artifact_sha256` is now constrained to
    64 lowercase hex characters (manifest.py); this drives a malformed digest
    through the stamping path and asserts it is rejected rather than written.
    """
    monkeypatch.setattr(
        "seagarden_dst.refresh.writer.sha256_of", lambda _path: "not-a-sha"
    )

    with pytest.raises(ValidationError, match="artifact_sha256"):
        write_pair(tiny_dataset, reference_manifest, tmp_path)

    assert not (tmp_path / "forcing.nc").exists()
    assert not (tmp_path / "manifest.json").exists()


from pathlib import Path  # noqa: E402

from seagarden_dst.refresh.manifest import ARTIFACT_VARIABLES  # noqa: E402

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


def test_the_baselines_describe_the_artifact_not_production():
    """C§6/C§4.4: a manifest attesting coverage the artifact does not have is
    the exact failure this design exists to prevent. Every non-empty baseline
    must match the artifact's actual `year` coordinate.
    """
    manifest, artifact = load_pair(FIXTURE)
    with xr.open_dataset(artifact, engine="h5netcdf") as ds:
        actual_years = sorted(int(y) for y in ds["year"].values)
    for name, years in manifest.baselines.items():
        if years:
            assert sorted(years) == actual_years, (
                f"baseline for {name!r} is {years} but the artifact's years are "
                f"{actual_years}"
            )


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
