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

from seagarden_dst.refresh.manifest import Manifest

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
    # "rb+", not "rb": on Windows os.fsync needs a handle opened for write access,
    # and a read-only handle raises OSError [Errno 9] Bad file descriptor. Measured
    # on the development machine — do not weaken this back to "rb".
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

    `_hook` is a test seam only, not a production parameter: it is called
    immediately before the first `os.replace` so a test can interrupt the write
    at the one moment that matters (C§6.1 row 2) without patching `os` itself.
    """
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    # Temp dir inside the target: a rename across filesystems is a copy, not atomic,
    # so the scratch space must be on the same filesystem as the destination.
    # TemporaryDirectory also cleans up a partial write on any exception.
    with tempfile.TemporaryDirectory(dir=target_dir) as tmp:
        tmp_dir = Path(tmp)
        tmp_artifact = tmp_dir / (_ARTIFACT + ".tmp")

        encoding = {name: {"zlib": True, "complevel": 4} for name in dataset.data_vars}
        dataset.to_netcdf(tmp_artifact, engine="h5netcdf", encoding=encoding)
        _fsync(tmp_artifact)

        stamped = manifest.model_copy(
            update={
                "artifact_filename": _ARTIFACT,
                "artifact_sha256": sha256_of(tmp_artifact),
                "artifact_bytes": tmp_artifact.stat().st_size,
            }
        )
        # model_copy does not re-run validators, and emitting a manifest that
        # skipped them is the one thing this module must never do.
        stamped = Manifest.model_validate(stamped.model_dump())

        tmp_manifest = tmp_dir / (_MANIFEST + ".tmp")
        tmp_manifest.write_text(stamped.model_dump_json(indent=2), encoding="utf-8")
        _fsync(tmp_manifest)

        if _hook is not None:
            _hook()

        artifact = target_dir / _ARTIFACT
        manifest_path = target_dir / _MANIFEST
        os.replace(tmp_artifact, artifact)  # step 5
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
    manifest = Manifest.model_validate(json.loads(manifest_path.read_text(encoding="utf-8")))
    artifact = target_dir / manifest.artifact_filename

    actual = sha256_of(artifact)
    if actual != manifest.artifact_sha256:
        raise ValueError(
            f"artifact_sha256 mismatch for {artifact}: the manifest says "
            f"{manifest.artifact_sha256}, the file is {actual}. Refusing to read the "
            "artifact under a manifest that does not describe it — re-run the refresh."
        )
    return manifest, artifact
