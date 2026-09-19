"""EMODnet Bathymetry: the fifth layer, and the only non-Copernicus one (C§13).

Elevation, not depth, arrives from the service: metres relative to LAT, negative
below the surface, land carried as zero or positive. Depth is `-elevation`, a pixel is
wet when `elevation < 0`, and every reduction here runs over wet pixels only, so a
cell with no wet pixel comes out NaN and `compute_valid` (C§3.5) refuses it.

**Nothing here imports rasterio or xarray at module scope** (see registry.py for why).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:  # pragma: no cover - typing only
    from seagarden_dst.artifact.grid import GridSpec


class GridAccumulator:
    """Bin pixels by the artifact cell containing their centre; reduce over wet ones.

    `GridSpec.lats()`/`lons()` are LOWER cell edges (their docstrings say so), so cell
    `i` spans `[lat_min + i*step, lat_min + (i+1)*step)`. A block reshape cannot do
    this: the lon step is 26.67 EMODnet pixels (C§13.3).
    """

    def __init__(self, grid: GridSpec) -> None:
        self._grid = grid
        shape = (grid.n_lat, grid.n_lon)
        self._sum = np.zeros(shape, dtype="float64")
        self._count = np.zeros(shape, dtype="int64")
        self._max_elevation = np.full(shape, -np.inf, dtype="float64")

    def add(self, elevation: np.ndarray, pixel_lats: np.ndarray, pixel_lons: np.ndarray) -> None:
        grid = self._grid
        elevation = np.asarray(elevation, dtype="float64")
        rows = np.floor((np.asarray(pixel_lats) - grid.lat_min) / grid.lat_step).astype(int)
        cols = np.floor((np.asarray(pixel_lons) - grid.lon_min) / grid.lon_step).astype(int)
        row_ok = (rows >= 0) & (rows < grid.n_lat)
        col_ok = (cols >= 0) & (cols < grid.n_lon)
        wet = elevation < 0  # NaN < 0 is False, so nil pixels drop out here too
        keep = wet & row_ok[:, None] & col_ok[None, :]
        if not keep.any():
            return
        r = np.broadcast_to(rows[:, None], elevation.shape)[keep]
        c = np.broadcast_to(cols[None, :], elevation.shape)[keep]
        values = elevation[keep]
        np.add.at(self._sum, (r, c), -values)
        np.add.at(self._count, (r, c), 1)
        np.maximum.at(self._max_elevation, (r, c), values)

    def finish(self) -> tuple[np.ndarray, np.ndarray]:
        """`(depth_mean_m, depth_min_m)`, NaN where no wet pixel fell in the cell."""
        has = self._count > 0
        mean = np.full(self._sum.shape, np.nan, dtype="float64")
        minimum = np.full(self._sum.shape, np.nan, dtype="float64")
        mean[has] = self._sum[has] / self._count[has]
        minimum[has] = -self._max_elevation[has]
        return mean, minimum
