"""Build every layer, merge, and write the pair (C§5, C§6).

The driver holds the real Dataset, which makes it the only place that can anchor the
manifest against what was actually built. It does not call `check_declaration` —
`write_pair` already does (R3) — but it does check SHAPES, which nothing else can
(R7), and it resolves each variable's baseline window against the data (R2).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from seagarden_dst.artifact.grid import GridSpec
from seagarden_dst.artifact.manifest import (
    ARTIFACT_SCHEMA_VERSION,
    AbsentField,
    Derivation,
    Manifest,
)
from seagarden_dst.refresh.layer import COVERAGE_LAYERS, Layer, YearRange
from seagarden_dst.refresh.merge import merge_layers
from seagarden_dst.refresh.shapes import check_shapes
from seagarden_dst.refresh.variables import ARTIFACT_VARIABLES
from seagarden_dst.refresh.writer import write_pair

if TYPE_CHECKING:  # pragma: no cover - typing only
    import xarray as xr


class RefreshFailed(RuntimeError):
    """Any layer failing takes the whole refresh with it (C§6.1 row 1)."""


def resolve_baselines(
    dataset: xr.Dataset, declared: dict[str, list[int]]
) -> dict[str, list[int]]:
    """Each variable's baseline window, declared by its layer and checked (R2).

    The criterion C§4.4 states is "no baseline WINDOW applies", not "no year
    dimension". `significant_wave_m` is where those diverge: a monthly p95 with no
    `year` dim and a 2023-2025 window. A dimensional rule writes `[]` there and
    contradicts the spec, the committed fixture, and a test named for the mistake.

    So the layer declares, and where the data carries a `year` coord we check the
    declaration against it. Keys come from `dataset.data_vars`, which keeps
    `set(baselines) == set(data_vars)` and lets the manifest's baselines-keys rule
    catch a produced-but-undeclared variable.
    """
    resolved: dict[str, list[int]] = {}
    for name, variable in dataset.data_vars.items():
        key = str(name)
        if "year" in variable.dims:
            from_data = [int(year) for year in variable["year"].values]
            if key in declared and list(declared[key]) != from_data:
                raise RefreshFailed(
                    f"declared baseline for '{key}' is {list(declared[key])} but the "
                    f"built data carries {from_data}; the manifest would attest a "
                    "window the artifact does not hold"
                )
            resolved[key] = from_data
            continue
        if key not in declared:
            raise RefreshFailed(
                f"no layer declared a baseline window for '{key}', and it has no year "
                "dimension to read one from; an unstated window is not an empty one "
                "(C§4.4) — `significant_wave_m` is exactly this case"
            )
        resolved[key] = list(declared[key])
    return resolved


def derivations() -> list[Derivation]:
    """The three derived fields (C§4.1), defined once and imported by the tests (R4).

    `din_umol_l` is here rather than claimed by `copernicus_bgc` because C§4.1's test
    is MULTI-SOURCE, not "computed": one source variable plus a statistic stays a raw
    claim, more than one needs a named relation. No unit conversion — package B
    verified no3 and nh4 arrive in mmol m-3, which is umol L-1.
    """
    return [
        Derivation(
            field="light_attenuation_k",
            relation=(
                "Poole-Atkins k = 1.7/z_SD over daily zsd, computed daily then "
                "averaged monthly"
            ),
            input_layers=["copernicus_bgc_light"],
        ),
        Derivation(
            field="valid",
            relation="intersection of contributing layer coverage",
            input_layers=list(COVERAGE_LAYERS),
        ),
        Derivation(
            field="din_umol_l",
            relation=(
                "din_umol_l = no3 + nh4: sum of dissolved inorganic nitrogen "
                "species, no unit conversion"
            ),
            input_layers=["copernicus_bgc"],
        ),
    ]


def _absent_fields() -> list[AbsentField]:
    """What the artifact deliberately does not carry (C§3.3, C§4.2)."""
    return [
        AbsentField(
            field="surface_par",
            reason="no integrated Baltic product carries PAR in any form",
            unblocked_by="a source outside the current layer set",
        )
    ]


def check_grid(dataset: xr.Dataset, grid: GridSpec) -> None:
    """The merged data sits on the grid the manifest is about to attest.

    Nothing else checks this. `xr.merge(join="exact")` catches layers disagreeing WITH
    EACH OTHER; `check_shapes` sees dim names and order; `check_declaration` sees
    variable names. A layer set that agrees internally and is uniformly wrong — the
    four Copernicus layers share one source grid, so a cell-centre/cell-edge offset
    shifts all of them together — would otherwise write a manifest attesting an extent
    the artifact does not have. That is the wave-baseline trap on the spatial axis.
    """
    import numpy as np

    expected = {"latitude": grid.lats(), "longitude": grid.lons()}
    for dim, axis in expected.items():
        size = dataset.sizes.get(dim)
        if size != len(axis):
            raise RefreshFailed(
                f"the merged data does not sit on the grid the manifest attests: "
                f"'{dim}' has {size} points, the GridSpec declares {len(axis)}"
            )
        if not np.allclose(dataset[dim].values, axis):
            raise RefreshFailed(
                f"the merged data does not sit on the grid the manifest attests: "
                f"'{dim}' coordinates differ from the GridSpec's, so the artifact "
                "covers a different extent than the manifest claims"
            )


def _build_all(
    layers: Sequence[Layer], grid: GridSpec, years: YearRange, workdir: Path
) -> dict[str, xr.Dataset]:
    built: dict[str, xr.Dataset] = {}
    for layer in layers:
        try:
            built[layer.name] = layer.build(grid, years, workdir)
        except Exception as error:  # noqa: BLE001 - re-raised with the layer named
            raise RefreshFailed(
                f"layer '{layer.name}' failed to build, so the whole refresh fails: "
                f"{error}. A missing variable quietly defaulting would leave the "
                "manifest attesting to a completeness the artifact lacks"
            ) from error
    return built


def _declared_windows(layers: Sequence[Layer]) -> dict[str, list[int]]:
    """Merge every layer's declaration, refusing a variable two layers claim."""
    declared: dict[str, list[int]] = {}
    for layer in layers:
        for name, window in layer.baseline_years().items():
            if name in declared:
                raise RefreshFailed(
                    f"two layers declared a baseline window for '{name}'; one "
                    "variable, one producing layer (C§5)"
                )
            declared[name] = list(window)
    # `valid` is the driver's own, computed in merge_layers, so no layer declares it.
    declared["valid"] = []
    return declared


def run_refresh(
    layers: Sequence[Layer],
    grid: GridSpec,
    years: YearRange,
    target_dir: Path,
    workdir: Path,
    *,
    synthetic: bool = False,
) -> tuple[Path, Path]:
    """Run a full refresh for `years` and write the pair (C§10 clause 1)."""
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)

    built = _build_all(layers, grid, years, workdir)
    merged = merge_layers(built)
    check_shapes(merged)  # R7 - names are check_declaration's job, shapes are ours
    check_grid(merged, grid)  # and the extent is nobody else's at all

    manifest = Manifest(
        artifact_schema_version=ARTIFACT_SCHEMA_VERSION,
        built_on=datetime.now(UTC),
        artifact_filename="forcing.nc",
        artifact_sha256="0" * 64,  # stamped by write_pair over the real bytes
        artifact_bytes=1,
        synthetic=synthetic,
        grid=grid,
        variables=sorted(ARTIFACT_VARIABLES),
        baselines=resolve_baselines(merged, _declared_windows(layers)),
        layers=[layer.provenance() for layer in layers],
        derived=derivations(),
        absent=_absent_fields(),
    )
    return write_pair(merged, manifest, Path(target_dir))
