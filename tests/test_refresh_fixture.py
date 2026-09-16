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
