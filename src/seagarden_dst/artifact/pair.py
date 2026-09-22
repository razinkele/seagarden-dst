"""Reading the artifact/manifest pair, and anchoring what the manifest claims (C§6).

This is the READ side, and it is core-importable on purpose: C§6.1 rows 3-4 put the
checksum refusal in the reader, and C§4.3 says D and C1 validate the same way C wrote
it. `write_pair` needs an `xr.Dataset` and stays in `refresh/`; nothing here needs
more than hashlib, json and pydantic.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .manifest import Manifest

_MANIFEST = "manifest.json"
_CHUNK = 1024 * 1024


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for block in iter(lambda: fh.read(_CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def check_declaration(manifest: Manifest, actual: set[str]) -> None:
    """Check `Manifest.variables` against what the artifact really carries.

    `Manifest.variables` is the reference set every C§4.4 rule resolves against, so
    nothing INSIDE the manifest can check it: drop a variable from both `variables`
    and `layers[].variables` and every rule still passes while the artifact on disk
    still holds it. That is the silent drop C§11.1 says those rules exist to prevent,
    and a review of this design demonstrated it by loading such a manifest clean.

    So the caller holding the real artifact supplies `actual` — `data_vars` for a
    NetCDF, table names for a GeoPackage. Package C's driver calls this before
    writing; package D calls it after loading. Same function, both directions, which
    is what C§4.3 means by validating the same way.
    """
    declared = set(manifest.variables)
    if declared == actual:
        return
    missing = sorted(declared - actual)
    extra = sorted(actual - declared)
    raise ValueError(
        "the manifest's variable declaration does not match the artifact: "
        f"declared-but-absent={missing} present-but-undeclared={extra}. "
        "Every C§4.4 rule resolves against `variables`, so a wrong declaration "
        "makes all of them agree with each other and with nothing else."
    )


class TornPair(ValueError):
    """The manifest does not describe the artifact beside it (C§6)."""


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
        raise TornPair(
            f"artifact_sha256 mismatch for {artifact}: the manifest says "
            f"{manifest.artifact_sha256}, the file is {actual}. Refusing to read the "
            "artifact under a manifest that does not describe it — re-run the refresh."
        )
    return manifest, artifact
