"""The provenance manifest (C§4).

Every rule the design states as prose is a validator here, so a manifest that
would mislead a reader fails at load rather than mid-analysis — the principle
`params._check_salinity_indexed_is_computable` and `params.Anchor` already follow.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

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
    def _check_state_is_complete(self) -> Archive:
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
