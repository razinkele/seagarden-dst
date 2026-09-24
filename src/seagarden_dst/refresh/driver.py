"""Build every layer, merge, and write the pair (C§5, C§6).

The driver holds the real Dataset, which makes it the only place that can anchor the
manifest against what was actually built. It does not call `check_declaration` —
`write_pair` already does (R3) — but it does check SHAPES, which nothing else can
(R7), and it resolves each variable's baseline window against the data (R2).
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable, Sequence
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


# The runbook's figures (annual-refresh.md §2): the wave stream peaks around 1 GB of
# working space and the EMODnet tile cache adds ~530 MB; the pair on disk is ~170 MB.
WORKDIR_MIN_BYTES = 2 * (1 << 30)
TARGET_MIN_BYTES = 200 * (1 << 20)


def _nearest_existing(path: Path) -> Path:
    """The CLI creates workdir and target itself, so measure where they will land."""
    path = Path(path).resolve()
    while not path.exists():
        path = path.parent
    return path


def _device_of(path: Path) -> int:
    return os.stat(path).st_dev


def _human(n: int) -> str:
    return f"{n / (1 << 30):.1f} GB" if n >= (1 << 30) else f"{n // (1 << 20)} MB"


def check_free_disk(
    workdir: Path,
    target_dir: Path,
    *,
    disk_usage: Callable[[Path], object] = shutil.disk_usage,
    device_of: Callable[[Path], int] = _device_of,
) -> None:
    """Refuse BEFORE starting when the disk cannot hold the refresh (C§6.1).

    Failing at 80% through a 30 GB transfer is the expensive failure; this is the
    cheap one, and it names the path, what it needs and what it has. When both
    directories sit on one filesystem the requirements are summed: 2.1 GB free
    passes each check alone and still runs out mid-transfer.
    """
    work_at = _nearest_existing(workdir)
    target_at = _nearest_existing(target_dir)
    shortfalls: list[str] = []
    if device_of(work_at) == device_of(target_at):
        need = WORKDIR_MIN_BYTES + TARGET_MIN_BYTES
        have = disk_usage(work_at).free
        if have < need:
            shortfalls.append(
                f"workdir {workdir} and target {target_dir} share the same filesystem "
                f"({work_at}): needs {_human(need)} free before starting, has {_human(have)}"
            )
    else:
        for label, asked, at, need in (
            ("workdir", workdir, work_at, WORKDIR_MIN_BYTES),
            ("target", target_dir, target_at, TARGET_MIN_BYTES),
        ):
            have = disk_usage(at).free
            if have < need:
                shortfalls.append(
                    f"{label} {asked} (on {at}): needs {_human(need)} free before "
                    f"starting, has {_human(have)}"
                )
    if shortfalls:
        raise RefreshFailed(
            "insufficient free disk, refusing before the download (C§6.1): "
            + "; ".join(shortfalls)
        )


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

    The "an unstated window is an error" rule (C§4.4) applies to every variable, not
    only the ones without a `year` dim — a variable WITH a year dim and no
    declaration is not a variable with a window to read off the data unchecked, it is
    an undeclared window like any other. So the declared-or-refused check runs
    first, before the year-dim branch, rather than being buried inside the `else`.
    """
    resolved: dict[str, list[int]] = {}
    for name, variable in dataset.data_vars.items():
        key = str(name)
        if key not in declared:
            raise RefreshFailed(
                f"no layer declared a baseline window for '{key}'; an unstated "
                "window is not an empty one (C§4.4) — `significant_wave_m` is "
                "exactly this case, and a year dim does not exempt a variable from "
                "declaring its window either"
            )
        if "year" in variable.dims:
            from_data = [int(year) for year in variable["year"].values]
            if list(declared[key]) != from_data:
                raise RefreshFailed(
                    f"declared baseline for '{key}' is {list(declared[key])} but the "
                    f"built data carries {from_data}; the manifest would attest a "
                    "window the artifact does not hold"
                )
            resolved[key] = from_data
            continue
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
    # This must run AFTER the duplicate-claim loop but must not let a layer that DID
    # declare `valid` be silently overwritten here — that would defeat the
    # one-variable-one-layer guard three lines up for this one name.
    if "valid" in declared:
        raise RefreshFailed(
            "a layer declared a baseline window for 'valid', but `valid` is computed "
            "by the driver in merge_layers; no layer may claim it (C§5)"
        )
    declared["valid"] = []
    return declared


#: dask worker threads for the whole refresh. The default threaded scheduler runs one
#: chunk per core - 28 on laguna, which also serves the app - and run 2 of the first
#: real refresh (2026-09-24) was OOM-killed there. Four keeps the in-flight chunks of
#: every layer to a few GB whatever the host's core count.
REFRESH_WORKERS = 4


def bound_dask_workers() -> None:
    """Pin dask to `REFRESH_WORKERS` threads, process-wide, for this refresh.

    Imported inside the call: dask arrives with the `spatial` extra (via xarray and
    copernicusmarine) and nothing in this module may import it at module scope. An
    install without dask has no lazy arrays to bound, so there is nothing to do.
    """
    try:
        import dask
    except ImportError:  # pragma: no cover - the spatial extra always brings dask
        return
    dask.config.set(scheduler="threads", num_workers=REFRESH_WORKERS)


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
    check_free_disk(Path(workdir), Path(target_dir))  # before any layer, any mkdir
    bound_dask_workers()  # before any layer opens a lazy source
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
