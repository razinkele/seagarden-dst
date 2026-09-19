"""EMODnet Bathymetry: the fifth layer, and the only non-Copernicus one (C§13).

Elevation, not depth, arrives from the service: metres relative to LAT, negative
below the surface, land carried as zero or positive. Depth is `-elevation`, a pixel is
wet when `elevation < 0`, and every reduction here runs over wet pixels only, so a
cell with no wet pixel comes out NaN and `compute_valid` (C§3.5) refuses it.

**Nothing here imports rasterio or xarray at module scope** (see registry.py for why).
"""

from __future__ import annotations

import math
import os
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

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


COVERAGE_ID = "emodnet__mean_2022"
VERSION = "2022"
WCS_URL = "https://ows.emodnet-bathymetry.eu/wcs"
_RETRIES = 3


class TileFetchFailed(RuntimeError):
    """A tile could not be fetched after the retries. Partial data is not data (C§6.1)."""


@dataclass(frozen=True)
class Tile:
    lat0: float
    lat1: float
    lon0: float
    lon1: float


def tiles_for(grid: GridSpec) -> list[Tile]:
    """Whole-degree tiles covering the extent, south-west first, row-major."""
    lat_start, lat_stop = math.floor(grid.lat_min), math.ceil(grid.lat_max)
    lon_start, lon_stop = math.floor(grid.lon_min), math.ceil(grid.lon_max)
    return [
        Tile(float(lat), float(lat + 1), float(lon), float(lon + 1))
        for lat in range(lat_start, lat_stop)
        for lon in range(lon_start, lon_stop)
    ]


def wcs_url(tile: Tile) -> str:
    return (
        f"{WCS_URL}?SERVICE=WCS&VERSION=2.0.1&REQUEST=GetCoverage"
        f"&COVERAGEID={COVERAGE_ID}"
        f"&SUBSET=Lat({tile.lat0},{tile.lat1})&SUBSET=Long({tile.lon0},{tile.lon1})"
        f"&FORMAT=image/tiff"
    )


def tile_path(workdir: Path, tile: Tile) -> Path:
    return Path(workdir) / "emodnet" / f"{tile.lat0}_{tile.lon0}.tif"


class TileFetcher(Protocol):
    def __call__(self, url: str, destination: Path) -> None: ...


def _default_fetcher(url: str, destination: Path) -> None:
    """urllib, to a temp file, then an atomic rename, so a torn download is never cached."""
    partial = destination.with_suffix(".part")
    with urllib.request.urlopen(url, timeout=120) as response, partial.open("wb") as out:
        while chunk := response.read(1 << 20):
            out.write(chunk)
    os.replace(partial, destination)


def fetch_tiles(
    tiles: list[Tile], workdir: Path, fetcher: TileFetcher | None = None
) -> list[Path]:
    """Every tile on disk, fetching the missing ones; an existing file is trusted (C§13.4)."""
    fetch = fetcher if fetcher is not None else _default_fetcher
    paths: list[Path] = []
    for tile in tiles:
        path = tile_path(workdir, tile)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            url = wcs_url(tile)
            for attempt in range(1, _RETRIES + 1):
                try:
                    fetch(url, path)
                    break
                except OSError as exc:
                    if attempt == _RETRIES:
                        raise TileFetchFailed(
                            f"tile {url} failed {_RETRIES} times ({exc}); refusing to build "
                            "from partial bathymetry (C§6.1)"
                        ) from exc
                    time.sleep(2.0 * attempt)
        paths.append(path)
    return paths


def read_tile(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """`(elevation, pixel_lats, pixel_lons)`, coordinates at pixel CENTRES."""
    import rasterio  # lazy: the spatial extra (see module docstring)

    with rasterio.open(path) as src:
        elevation = src.read(1).astype("float64")
        transform = src.transform
        rows = np.arange(src.height)
        cols = np.arange(src.width)
        lons = transform.c + (cols + 0.5) * transform.a
        lats = transform.f + (rows + 0.5) * transform.e  # e is negative: north at row 0
    return elevation, lats, lons
