"""The one seam between the refresh layers and Copernicus Marine (C§5, R2, R3).

Two rules hold this module together.

**It opens, it does not download (R2).** `copernicusmarine.open_dataset` returns a
lazy, ARCO-backed Dataset; `copernicusmarine.subset` writes a file. `copernicus_wav`
reduces ~25.8 GB of hourly `VHM0` to a monthly p95, and the lazy route never lands
those hours on disk. Package B used `subset` because it was measuring file sizes;
that is not what a refresh needs.

**Nothing spatial is imported at module scope (R3).** `registry.py` imports the layer
modules, which import this one, and `registry.py` is imported by the probe job after
`pip install -e .` with no `[spatial]` extra. `import copernicusmarine` therefore
lives inside `_default_opener`, and `xarray` appears only under `TYPE_CHECKING`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol

from seagarden_dst.artifact.manifest import Archive, LayerProvenance

if TYPE_CHECKING:  # pragma: no cover - typing only
    import xarray as xr

    from seagarden_dst.artifact.grid import GridSpec
    from seagarden_dst.refresh.layer import YearRange

# The surface model level, 0.50 m, is the shallowest of the reanalysis's 56 (C§3.2).
# Requested as a window rather than a point because the level's exact centre is a
# product detail; 0-1 m selects it and nothing below it.
SURFACE_MIN_DEPTH: float = 0.0
SURFACE_MAX_DEPTH: float = 1.0

# The strings every Copernicus layer shares verbatim. Named once here because
# duplicated VALUES are where drift lives in this package: the wave layer shipped
# the wrong `version` for exactly one reason — the provenance block was copy-pasted
# across four modules and the one field that legitimately differs came along with it.
COPERNICUS_SOURCE = "Copernicus Marine Service"
COPERNICUS_LICENCE = "Copernicus Marine Service licence"
COPERNICUS_PRODUCT_BASE = "https://data.marine.copernicus.eu/product"
# `pending` until the built artifact is deposited; C§1 puts that outside package C.
ARCHIVE_UNBLOCKED_BY = "Zenodo deposit of the built artifact; C§1 puts it outside package C"


def product_url(product_id: str) -> str:
    """The catalogue landing page for a product.

    Derived rather than written out per layer so the URL a layer's `probe()` HEADs
    and the URL its provenance records cannot drift apart — they are the same string
    by construction.
    """
    return f"{COPERNICUS_PRODUCT_BASE}/{product_id}"


def copernicus_provenance(
    *,
    name: str,
    product_id: str,
    dataset_id: str,
    version: str,
    variables: list[str],
) -> LayerProvenance:
    """Assemble a `LayerProvenance` from the shared strings plus the per-layer ones.

    **Only the genuinely-shared values live in here.** `version`, `dataset_id`,
    `product_id`, `name` and `variables` stay explicit arguments because C§11.1
    requires them to be per-layer: the wave product is at `202411` while physics and
    biogeochemistry are at `202303`, and `copernicus_bgc` and `copernicus_bgc_light`
    share a product but read different datasets. Absorbing any of those into a shared
    default would rebuild the copy-paste hazard this function exists to remove.

    This is a helper, not a base class. `Layer` is a `Protocol` because C§5 chose
    structural typing over inheritance, and the fifth layer — `emodnet_bathy` —
    shares none of this: not `open_window`, not the depth handling, not these
    strings, not even the host its probe hits.
    """
    url = product_url(product_id)
    return LayerProvenance(
        name=name,
        source=COPERNICUS_SOURCE,
        product_id=product_id,
        dataset_id=dataset_id,
        version=version,
        retrieved_on=datetime.now(UTC),
        licence=COPERNICUS_LICENCE,
        redistribution="allowed",
        source_url=url,
        archive=Archive(status="pending", source_url=url, unblocked_by=ARCHIVE_UNBLOCKED_BY),
        variables=list(variables),
    )


class DatasetOpener(Protocol):
    """What `open_window` calls. The injection seam every layer test uses."""

    def __call__(self, **kwargs: Any) -> xr.Dataset: ...


def _default_opener() -> DatasetOpener:
    """Resolve the real opener, importing inside the call (R3)."""
    import copernicusmarine

    return copernicusmarine.open_dataset


def open_window(
    dataset_id: str,
    variables: list[str],
    grid: GridSpec,
    years: YearRange,
    *,
    opener: DatasetOpener | None = None,
    surface: bool = True,
) -> xr.Dataset:
    """Open `variables` from `dataset_id` over the grid extent and year span.

    `surface=False` for products with no depth axis — the wave product is 2-D, and
    handing it a depth window is an error rather than a no-op.
    """
    open_dataset = opener if opener is not None else _default_opener()
    request: dict[str, Any] = {
        "dataset_id": dataset_id,
        "variables": list(variables),
        "minimum_longitude": grid.lon_min,
        "maximum_longitude": grid.lon_max,
        "minimum_latitude": grid.lat_min,
        "maximum_latitude": grid.lat_max,
        "start_datetime": f"{years.start}-01-01T00:00:00",
        "end_datetime": f"{years.end}-12-31T23:59:59",
    }
    if surface:
        request["minimum_depth"] = SURFACE_MIN_DEPTH
        request["maximum_depth"] = SURFACE_MAX_DEPTH
    return open_dataset(**request)


def to_yearly(data: xr.DataArray) -> xr.DataArray:
    """Reshape a monthly `time` series into C§3.2's yearly shape.

    `(time, latitude, longitude)` -> `(year, month, latitude, longitude)`. Splitting
    the time axis rather than grouping twice keeps every (year, month) cell present,
    including months a source happens to be missing — those arrive as NaN, which is
    the validity signal D reads, instead of vanishing and shortening the axis.

    **`unstack` alone does not deliver that guarantee, which is why the reindex is
    here.** It fills only the cartesian product of the values it OBSERVED, so a month
    missing from *some* years arrives as NaN, but a month missing from *every* year
    in the span never enters the month index at all and the axis silently comes back
    eleven long. `check_shapes` compares dim NAMES, not lengths, so it accepts that.
    Reindexing onto 1-12 makes the promise the docstring makes.

    **`year` is deliberately NOT reindexed, and the asymmetry is the point.** A month
    has a fixed, known domain — there are twelve, always — so a missing one is a hole
    to mark. A year does not: the span is whatever the caller asked for, and a source
    year that is simply absent is caught upstream by `resolve_baselines`
    (`driver.py`), which refuses loudly because the declared window and the built data
    disagree. Reindexing `year` here would manufacture an all-NaN year that satisfies
    that guard and then collapses `valid` through `_coverage_of`'s `.all()` — a quiet
    empty artifact in place of a loud refusal. Do not "fix" the asymmetry.
    """
    split = data.assign_coords(
        year=data["time"].dt.year, month=data["time"].dt.month
    ).set_index(time=["year", "month"])
    unstacked = split.unstack("time").reindex(month=list(range(1, 13)))
    return unstacked.transpose("year", "month", "latitude", "longitude")


def drop_depth(data: xr.DataArray) -> xr.DataArray:
    """Remove the singleton depth axis a surface request still carries.

    **It refuses a depth axis with more than one level rather than taking the first.**
    The 0-1 m window is meant to select exactly one model level, the 0.50 m surface
    one. If a product ever returns two levels inside that band — a reprocessing that
    adds a level, or a catalogue change — silently keeping element zero would halve
    the data and emit a surface field that is really a single arbitrary level, with
    nothing in the artifact or the manifest recording that a choice was made. The
    right answer is then a deliberate reduction (a mean, or a narrower window), which
    is a decision for a human, so this raises and says which levels it saw.
    """
    if "depth" in data.dims:
        levels = int(data.sizes["depth"])
        if levels != 1:
            values = list(data["depth"].values) if "depth" in data.coords else "unknown"
            raise ValueError(
                f"depth axis has {levels} levels, expected exactly 1: the "
                f"{SURFACE_MIN_DEPTH}-{SURFACE_MAX_DEPTH} m window is meant to select "
                f"the single surface model level, and it returned {values}. Taking "
                "element zero would silently drop the rest and ship one arbitrary "
                "level as 'surface' — choose the reduction explicitly instead"
            )
        data = data.isel(depth=0, drop=True)
    elif "depth" in data.coords:
        data = data.drop_vars("depth")
    return data
