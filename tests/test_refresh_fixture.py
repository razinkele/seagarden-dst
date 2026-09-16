import json
import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from seagarden_dst.refresh.manifest import ARTIFACT_VARIABLES
from seagarden_dst.refresh.writer import load_pair, sha256_of, write_pair

# `pytestmark` below deselects this module from the default run — but `-m` filters
# AFTER collection, and collection imports the module. `writer.py` no longer imports
# xarray at module scope (I1 / C§11), so the `seagarden_dst.refresh.writer` import
# above is safe in the `.[app,dev]` install with no `spatial` extra. This module's
# own tests still call `xr.open_dataset`/`xr.testing.assert_identical` directly and
# `write_pair` needs a real `xr.Dataset` argument at call time, so THIS module still
# needs xarray installed — `importorskip` turns a missing extra into a clean
# module-level skip instead of a collection-time ModuleNotFoundError that no marker
# can reach, which is the exact outcome C§11 says the mechanism must avoid.
xr = pytest.importorskip("xarray")

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


def test_the_five_layers_carry_distinct_truthful_provenance():
    """C§4.4 constrains `dataset_id` uniqueness and the claim union but says
    nothing about `source`/`product_id` — a real gap this test closes for the
    committed fixture, where a wrong-but-valid manifest would otherwise sit as
    package D and C1's first example (found in review: all five layers had
    inherited `layer()`'s Copernicus-physics `source`/`product_id` defaults,
    so EMODnet bathymetry attested a Copernicus product).
    """
    manifest, _ = load_pair(FIXTURE)
    product_ids = [layer.product_id for layer in manifest.layers]
    assert len(set(product_ids)) == len(product_ids), (
        f"layer product_ids are not distinct: {product_ids}"
    )
    bathy = next(layer for layer in manifest.layers if layer.name == "emodnet_bathy")
    assert bathy.source != "Copernicus Marine Service"
    assert "emodnet" in bathy.source.lower()


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


def test_the_committed_manifests_baseline_keys_are_in_deterministic_order(tmp_path):
    """`_fixture_manifest` must build `baselines` from `sorted(ARTIFACT_VARIABLES)`,
    not by iterating the `frozenset` directly: iteration order over a set is not
    stable across separate Python processes under hash randomization, so a
    correct, identical-input regeneration could still produce a differently-
    ordered (but equal-valued) `baselines` block, and `git diff` on a routine
    regeneration would never be empty even when nothing has changed.

    This asserts the determinism property on the GENERATOR's own output — calling
    `build_fixture` directly and reading back the `manifest.json` it just wrote —
    rather than only on the file already committed to the repo. That distinction
    matters: replacing `sorted(ARTIFACT_VARIABLES)` with the bare frozenset in
    `scripts/make_fixture.py` leaves the *committed* file untouched (nothing
    regenerates it as part of the suite), so a test that reads only the committed
    file would stay green after the guard it is meant to protect was deleted. The
    committed-file assertion is kept too, alongside the generator one: it is the
    cheaper, complementary claim that the file actually checked in was produced by
    a generator under this guard, not hand-edited into sorted order once and then
    left to drift.

    `tmp_path` gives `build_fixture` its own directory so this asserts on
    `manifest.json`'s key order alone, with zero coupling to `artifact_sha256`,
    `artifact_bytes`, or the `.nc` file's bytes.
    """
    from scripts.make_fixture import build_fixture

    build_fixture(tmp_path)
    generated = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert list(generated["baselines"]) == sorted(ARTIFACT_VARIABLES)

    committed = json.loads((FIXTURE / "manifest.json").read_text(encoding="utf-8"))
    assert list(committed["baselines"]) == sorted(ARTIFACT_VARIABLES)
