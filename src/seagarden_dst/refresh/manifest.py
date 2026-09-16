"""The provenance manifest (C§4).

Every rule the design states as prose is a validator here, so a manifest that
would mislead a reader fails at load rather than mid-analysis — the principle
`params._check_salinity_indexed_is_computable` and `params.Anchor` already follow.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from seagarden_dst.refresh.grid import GridSpec

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


# The nine variables the artifact carries (C§3.2). `surface_par` is deliberately
# absent and is recorded in `absent`, not here.
ARTIFACT_VARIABLES: frozenset[str] = frozenset({
    "salinity_psu", "temp_c", "din_umol_l", "dip_umol_l", "light_attenuation_k",
    "significant_wave_m", "depth_mean_m", "depth_min_m", "valid",
})


class Manifest(BaseModel):
    """The artifact's provenance, beside it and validated with it."""

    model_config = ConfigDict(extra="forbid")

    artifact_schema_version: int
    built_on: datetime
    artifact_filename: str
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_bytes: int = Field(gt=0)
    synthetic: bool
    grid: GridSpec
    baselines: dict[str, list[int]]
    layers: list[LayerProvenance]
    derived: list[Derivation]
    absent: list[AbsentField]

    @model_validator(mode="after")
    def _check_schema_version(self) -> Manifest:
        if self.artifact_schema_version != ARTIFACT_SCHEMA_VERSION:
            raise ValueError(
                f"artifact_schema_version {self.artifact_schema_version} is not "
                f"{ARTIFACT_SCHEMA_VERSION}; refusing rather than guessing the shape"
            )
        return self

    @model_validator(mode="after")
    def _check_every_variable_is_claimed_exactly_once(self) -> Manifest:
        claims: dict[str, list[str]] = {}
        for layer in self.layers:
            for name in layer.variables:
                claims.setdefault(name, []).append(f"layer {layer.name}")
        for d in self.derived:
            claims.setdefault(d.field, []).append(f"derivation {d.field}")

        twice = {name: who for name, who in claims.items() if len(who) > 1}
        if twice:
            raise ValueError(
                "these variables are claimed more than once, so the manifest cannot "
                f"say which source produced them: {twice}"
            )
        unclaimed = ARTIFACT_VARIABLES - set(claims)
        if unclaimed:
            raise ValueError(
                "these artifact variables are claimed by no layer and no derivation, "
                f"so they sit in the artifact with nothing behind them: {sorted(unclaimed)}"
            )
        extra = set(claims) - ARTIFACT_VARIABLES
        if extra:
            raise ValueError(f"claimed variables the artifact does not carry: {sorted(extra)}")
        return self

    @model_validator(mode="after")
    def _check_baseline_keys_are_exactly_the_claimed_set(self) -> Manifest:
        keys = set(self.baselines)
        if keys != set(ARTIFACT_VARIABLES):
            raise ValueError(
                "baselines keys must be exactly the artifact's variables — a variable "
                "with no entry is one whose temporal coverage the manifest does not "
                f"state. missing={sorted(ARTIFACT_VARIABLES - keys)} "
                f"extra={sorted(keys - ARTIFACT_VARIABLES)}"
            )
        return self

    @model_validator(mode="after")
    def _check_dataset_ids_are_unique(self) -> Manifest:
        seen: dict[str, str] = {}
        for layer in self.layers:
            if layer.dataset_id in seen:
                raise ValueError(
                    f"layers {seen[layer.dataset_id]!r} and {layer.name!r} share "
                    f"dataset_id {layer.dataset_id!r}; one layer means one dataset"
                )
            seen[layer.dataset_id] = layer.name
        return self

    @model_validator(mode="after")
    def _check_every_layer_is_reachable(self) -> Manifest:
        named = {i.layer for d in self.derived for i in d.inputs}
        orphans = [
            layer.name for layer in self.layers
            if not layer.variables and layer.name not in named
        ]
        if orphans:
            raise ValueError(
                "these layers are reachable from nothing — no variable claim and no "
                "derivation input names them, so the manifest attests a source nothing "
                f"uses, or uses a source it never attests: {orphans}"
            )
        unknown = named - {layer.name for layer in self.layers}
        if unknown:
            raise ValueError(
                f"derivation inputs name layers that do not exist: {sorted(unknown)}"
            )
        return self
