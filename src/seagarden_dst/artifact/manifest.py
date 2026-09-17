"""The provenance manifest (C§4).

Every rule the design states as prose is a validator here, so a manifest that
would mislead a reader fails at load rather than mid-analysis — the principle
`params._check_salinity_indexed_is_computable` and `params.Anchor` already follow.

C§4.3 names these models as what package D and C1 are meant to validate against, and
**this package is the core-side home that makes that possible**. `seagarden_dst.artifact`
depends on pydantic, stdlib and numpy only, so package D imports `Manifest`, `sha256_of`
and `load_pair` directly — without pulling in `refresh/` or the `spatial` extra.

Three tests hold that boundary open, in `tests/test_refresh_isolation.py`:
`test_no_core_module_imports_refresh` keeps the build-time half out of the core;
`test_refresh_imports_nothing_from_the_core_except_the_shared_schema` names
`seagarden_dst.artifact` (`_SHARED`, line 120) as the one permitted crossing; and
`test_the_shared_schema_imports_nothing_that_needs_the_spatial_extra` is what keeps this
package importable by a core that has no xarray.

*Superseded note, 2026-09-17:* this docstring previously said the `artifact` package "was
not built — everything shipped here, under `refresh/`, instead", and that how D reached
`Manifest` across the boundary was unresolved. Commit `b886481` built it, which is the
package this file now sits in; `refresh/writer.py`, `layer.py`, `driver.py` and
`deposit.py` all import from it. Nothing is left for C-b or D to re-home.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from seagarden_dst.artifact.grid import GridSpec

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
    `derived[].input_layers` resolves against it — without it that reference
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


class Derivation(BaseModel):
    """A computed field, the layers it drew on, and the relation (C§4.1).

    A computed field has no single raw source, so it cannot be an entry in some
    layer's `variables`; it is claimed here instead (C§4.4).

    `input_layers` names `LayerProvenance.name` values — the one namespace this
    manifest can close. Source variable names live in `relation`, as prose, and
    nowhere else. That is a deliberate retreat from a structured {layer, variable}
    pair: this repository has a download-verified source-variable inventory for ONE
    of the five layers, so the structured field would promise a referential
    integrity no validator could keep, and four records of unchecked assertion
    wearing the costume of a foreign key are worse than prose — prose does not claim
    to have been checked. `relation` must therefore name every source variable it
    reads, spelled as the source dataset spells it.
    """

    model_config = ConfigDict(extra="forbid")

    field: str
    relation: str = Field(min_length=1)
    input_layers: list[str] = Field(min_length=1)


class AbsentField(BaseModel):
    """A field the artifact deliberately does not carry (C§4.2).

    Today it has one entry, `surface_par`. Machine-readable so the UI reads the
    manifest instead of carrying a hardcoded caveat that can drift.
    """

    model_config = ConfigDict(extra="forbid")

    field: str
    reason: str
    unblocked_by: str




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
    #: What the artifact carries — the reference set every C§4.4 rule resolves
    #: against. A manifest FIELD rather than a constant in this module because
    #: C§4.3 has package D and package C1 importing these same models, and C1's
    #: GeoPackage carries human-use and exclusion vectors, none of the nine forcing
    #: names; a hardcoded list here would make every C1 manifest unloadable. Package
    #: C keeps its own list in `refresh/variables.py`, where the driver asserts it.
    #:
    #: NOT self-checking. Drop a variable from both this and `layers[].variables` and
    #: every rule below still passes while the artifact holds it — the silent drop
    #: C§11.1 says those rules exist to prevent. `artifact.pair.check_declaration`
    #: anchors it against the real artifact, on write and on read alike.
    variables: list[str] = Field(min_length=1)
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
        declared = set(self.variables)
        unclaimed = declared - set(claims)
        if unclaimed:
            raise ValueError(
                "these artifact variables are claimed by no layer and no derivation, "
                f"so they sit in the artifact with nothing behind them: {sorted(unclaimed)}"
            )
        extra = set(claims) - declared
        if extra:
            raise ValueError(f"claimed variables the artifact does not carry: {sorted(extra)}")
        return self

    @model_validator(mode="after")
    def _check_baseline_keys_are_exactly_the_artifact_variables(self) -> Manifest:
        # Compared against `self.variables`, not the claim set built in the
        # validator above — equivalent today only because
        # `_check_every_variable_is_claimed_exactly_once` already forces the claim
        # set to equal it (rule 1); a manifest that failed here without also failing
        # there would mean that invariant broke.
        #
        # `variables` is the artifact's own declaration, so it is not self-checking:
        # `artifact.pair.check_declaration` anchors it against the real artifact.
        keys = set(self.baselines)
        if keys != set(self.variables):
            raise ValueError(
                "baselines keys must be exactly the artifact's variables — a variable "
                "with no entry is one whose temporal coverage the manifest does not "
                f"state. missing={sorted(set(self.variables) - keys)} "
                f"extra={sorted(keys - set(self.variables))}"
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
        named = {name for d in self.derived for name in d.input_layers}
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
