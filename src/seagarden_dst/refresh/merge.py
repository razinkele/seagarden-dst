"""Merging layers, and the one field the driver computes rather than fetches (C§3.5).

Copernicus land-masking sits on the 2 km model grid; EMODnet bathymetry is an
independent ~115 m product. A cell can be wet in one and absent in the other, and the
disagreement concentrates at the coastline — which is where every farm is. So the
driver writes an explicit `valid`, and package D reads that rather than inferring
validity from whichever variable it happened to look at.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from seagarden_dst.refresh.layer import COVERAGE_LAYERS
from seagarden_dst.refresh.shapes import SPATIAL_DIMS

if TYPE_CHECKING:  # pragma: no cover - typing only
    import xarray as xr


def _coverage_of(dataset: xr.Dataset) -> xr.DataArray:
    """A 2-D mask: cells where every variable is present across every other dim.

    `.all()` rather than `.any()` (R5) — a cell wet in some months and absent in
    others is not coverage a farm verdict should rest on. Failing small fails safe.

    The three real shapes all reduce to (latitude, longitude): the 4-D reanalysis
    fields, the month-only wave field, and the static bathymetry.
    """
    if not dataset.data_vars:
        raise ValueError(
            "a layer built no variables, so its coverage is undefined; an empty "
            "dataset here is a bug in the layer, not an empty intersection"
        )
    masks = []
    for name, variable in dataset.data_vars.items():
        missing = [d for d in SPATIAL_DIMS if d not in variable.dims]
        if missing:
            raise ValueError(
                f"variable '{name}' lacks the spatial dims {missing}: it has "
                f"{list(variable.dims)}. Coverage reduces over every NON-spatial dim, "
                "so a mis-named coordinate would collapse `valid` to a scalar that "
                "check_declaration cannot see, because it compares names only"
            )
        masks.append(
            variable.notnull().all(dim=[d for d in variable.dims if d not in SPATIAL_DIMS])
        )
    covered = masks[0]
    for mask in masks[1:]:
        covered = covered & mask
    return covered


def compute_valid(per_layer: dict[str, xr.Dataset]) -> xr.DataArray:
    """The intersection of contributing layer coverage (C§3.5, C§10 clause 11).

    Taken over `COVERAGE_LAYERS` only. The manifest records that same list as the
    `valid` derivation's `input_layers`, so the two cannot disagree.
    """
    contributing = [name for name in COVERAGE_LAYERS if name in per_layer]
    if not contributing:
        raise ValueError(
            "no coverage layer was built, so `valid` would be an intersection over "
            "nothing and every cell would read as valid; expected at least one of "
            f"{list(COVERAGE_LAYERS)}"
        )
    valid = _coverage_of(per_layer[contributing[0]])
    for name in contributing[1:]:
        valid = valid & _coverage_of(per_layer[name])
    return valid.rename("valid")


def merge_layers(per_layer: dict[str, xr.Dataset]) -> xr.Dataset:
    """Merge every layer onto one dataset and attach `valid`.

    `combine_attrs="drop_conflicts"`, deliberately, and neither of the two obvious
    alternatives. `"drop"` would strip the CRS that C§3.2 records as a VARIABLE
    attribute, surfacing only when package D read the artifact and found no CRS to
    trust. `"no_conflicts"` raises `MergeError` the moment two layers carry different
    DATASET-level attrs — and EMODnet and CMEMS do not share a `source`, so the first
    real refresh would have died at the merge. `drop_conflicts` drops the conflicting
    dataset-level attrs and leaves every variable's own attrs intact, which is the
    behaviour both requirements point at.
    """
    import xarray as xr

    merged = xr.merge(list(per_layer.values()), join="exact", combine_attrs="drop_conflicts")
    return merged.assign(valid=compute_valid(per_layer))
