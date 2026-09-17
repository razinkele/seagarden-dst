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

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:  # pragma: no cover - typing only
    import xarray as xr

    from seagarden_dst.artifact.grid import GridSpec
    from seagarden_dst.refresh.layer import YearRange

# The surface model level, 0.50 m, is the shallowest of the reanalysis's 56 (C§3.2).
# Requested as a window rather than a point because the level's exact centre is a
# product detail; 0-1 m selects it and nothing below it.
SURFACE_MIN_DEPTH: float = 0.0
SURFACE_MAX_DEPTH: float = 1.0


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
    """
    split = data.assign_coords(
        year=data["time"].dt.year, month=data["time"].dt.month
    ).set_index(time=["year", "month"])
    return split.unstack("time").transpose("year", "month", "latitude", "longitude")


def drop_depth(data: xr.DataArray) -> xr.DataArray:
    """Remove the singleton depth axis a surface request still carries."""
    if "depth" in data.dims:
        data = data.isel(depth=0, drop=True)
    elif "depth" in data.coords:
        data = data.drop_vars("depth")
    return data
