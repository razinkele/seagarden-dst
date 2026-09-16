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
