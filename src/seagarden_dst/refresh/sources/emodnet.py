"""EMODnet Bathymetry: the fifth layer, and the only non-Copernicus one (C§13).

Elevation, not depth, arrives from the service: metres relative to LAT, negative
below the surface, land carried as zero or positive. Depth is `-elevation`, a pixel is
wet when `elevation < 0`, and every reduction here runs over wet pixels only, so a
cell with no wet pixel comes out NaN and `compute_valid` (C§3.5) refuses it.

**Nothing here imports rasterio or xarray at module scope** (see registry.py for why).
"""

from __future__ import annotations

import gzip
import http.client
import math
import os
import time
import urllib.request
import xml.etree.ElementTree as ET
import zlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

import numpy as np

from seagarden_dst.artifact.manifest import Archive, LayerProvenance
from seagarden_dst.refresh.layer import ProbeResult
from seagarden_dst.refresh.sources.cmems import ARCHIVE_UNBLOCKED_BY

if TYPE_CHECKING:  # pragma: no cover - typing only
    import xarray as xr

    from seagarden_dst.artifact.grid import GridSpec
    from seagarden_dst.refresh.layer import YearRange


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
SOURCE = "EMODnet Bathymetry"
PRODUCT_ID = "EMODnet DTM 2022"
LICENCE = "EMODnet Bathymetry licence (CC BY 4.0)"
SOURCE_URL = "https://emodnet.ec.europa.eu/en/bathymetry"
VARIABLES = ["depth_mean_m", "depth_min_m"]
_RETRIES = 3

# Failure modes a flaky network or a misbehaving proxy can produce partway through a
# read; all are treated as transport failures, retried by fetch_tiles and reported as
# `unreachable` by probe_coverage rather than propagating raw.
_TRANSPORT_ERRORS: tuple[type[BaseException], ...] = (
    OSError,
    http.client.HTTPException,
    EOFError,
    zlib.error,
)


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


_TIFF_MAGIC = (b"II*\x00", b"MM\x00*")


def _is_tiff(path: Path) -> bool:
    """Whether `path` starts with a TIFF byte-order magic number (little- or big-endian)."""
    with path.open("rb") as f:
        header = f.read(4)
    return header in _TIFF_MAGIC


def _finish_download(url: str, partial: Path, destination: Path) -> None:
    """Rename a completed download into place, but only if it is actually a TIFF.

    Protects against exactly two things: a crash partway through the write (the
    `.part` file never becomes `destination`) and a non-TIFF body arriving with an
    HTTP 200 — an OWS ExceptionReport or an HTML error page — which would otherwise
    be renamed into the cache and trusted forever by `fetch_tiles`'s
    `if not path.exists()` check. Nothing else is validated here.
    """
    if not _is_tiff(partial):
        header = partial.read_bytes()[:16]
        partial.unlink(missing_ok=True)
        raise OSError(f"{url} returned a non-TIFF body ({header!r})")
    os.replace(partial, destination)


def _default_fetcher(url: str, destination: Path) -> None:
    """urllib, to a temp file, then an atomic rename, so a torn download is never cached."""
    partial = destination.with_suffix(".part")
    with urllib.request.urlopen(url, timeout=120) as response, partial.open("wb") as out:
        while chunk := response.read(1 << 20):
            out.write(chunk)
    _finish_download(url, partial, destination)


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
                except _TRANSPORT_ERRORS as exc:
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
        if src.nodata is not None:
            elevation[elevation == src.nodata] = np.nan
        transform = src.transform
        rows = np.arange(src.height)
        cols = np.arange(src.width)
        lons = transform.c + (cols + 0.5) * transform.a
        lats = transform.f + (rows + 0.5) * transform.e  # e is negative: north at row 0
    return elevation, lats, lons


class CapabilitiesReader(Protocol):
    def __call__(self) -> bytes: ...


def _decode_body(body: bytes, content_encoding: str | None) -> bytes:
    if content_encoding and "gzip" in content_encoding.lower():
        return gzip.decompress(body)
    return body


_MAX_CAPABILITIES_BYTES = 8 << 20  # the live document is ~8 KB; anything near this is not it


def _check_size(body: bytes) -> bytes:
    """`body`, unchanged, if it is within `_MAX_CAPABILITIES_BYTES`; otherwise `OSError`.

    Called both on the wire body (bounds a compressed bomb before decompression) and
    again on the decoded body (bounds what decompression expanded it to).
    """
    if len(body) > _MAX_CAPABILITIES_BYTES:
        raise OSError(
            f"GetCapabilities exceeded {_MAX_CAPABILITIES_BYTES} bytes; refusing to parse"
        )
    return body


def _default_capabilities() -> bytes:
    url = f"{WCS_URL}?SERVICE=WCS&VERSION=2.0.1&REQUEST=GetCapabilities"
    with urllib.request.urlopen(url, timeout=60) as response:
        body = _check_size(response.read(_MAX_CAPABILITIES_BYTES + 1))
    return _check_size(_decode_body(body, response.headers.get("Content-Encoding")))


def coverage_ids(xml: bytes) -> set[str]:
    """Every `CoverageId` in a capabilities document, whatever prefix the server used.

    `Element.iter()` does not honour the `{*}` wildcard (only `find`/`findall` do), so
    this uses `findall` with a `.//` search rather than the `iter` form.
    """
    root = ET.fromstring(xml)
    return {el.text.strip() for el in root.findall(".//{*}CoverageId") if el.text}


def probe_coverage(
    name: str, *, capabilities: CapabilitiesReader | None = None
) -> ProbeResult:
    """`ok` when the dated coverage is listed; `absent` when it is not; `unreachable`
    when the service cannot be asked. The version IS the coverage id, so drift is
    absence and there is no `version_drift` here (C§13.4)."""
    read = capabilities if capabilities is not None else _default_capabilities
    try:
        listed = coverage_ids(read())
    except (*_TRANSPORT_ERRORS, ET.ParseError) as exc:
        return ProbeResult(
            name=name, status="unreachable", reachable=False,
            detail=f"GetCapabilities failed: {exc}",
        )
    if COVERAGE_ID in listed:
        return ProbeResult(
            name=name, status="ok", reachable=True,
            detail=f"{COVERAGE_ID} listed by {WCS_URL}",
        )
    return ProbeResult(
        name=name, status="absent", reachable=False,
        detail=f"{COVERAGE_ID} is no longer listed; the service lists {sorted(listed)}",
    )


class EmodnetBathy:
    """One layer, one dataset: the 2022 DTM, reduced onto the artifact grid (C§13)."""

    name = "emodnet_bathy"

    def __init__(
        self,
        fetcher: TileFetcher | None = None,
        capabilities: CapabilitiesReader | None = None,
    ) -> None:
        self._fetcher = fetcher
        self._capabilities = capabilities

    def probe(self) -> ProbeResult:
        return probe_coverage(self.name, capabilities=self._capabilities)

    def build(self, grid: GridSpec, years: YearRange, workdir: Path) -> xr.Dataset:
        """Static: `years` is accepted for the protocol and ignored (C§13.5)."""
        import xarray as xr

        del years
        accumulator = GridAccumulator(grid)
        for path in fetch_tiles(tiles_for(grid), Path(workdir), self._fetcher):
            elevation, lats, lons = read_tile(path)
            accumulator.add(elevation, lats, lons)
        mean, minimum = accumulator.finish()
        dims = ("latitude", "longitude")
        return xr.Dataset(
            {
                "depth_mean_m": (dims, mean.astype("float32")),
                "depth_min_m": (dims, minimum.astype("float32")),
            },
            coords={"latitude": grid.lats(), "longitude": grid.lons()},
        )

    def provenance(self) -> LayerProvenance:
        return LayerProvenance(
            name=self.name,
            source=SOURCE,
            product_id=PRODUCT_ID,
            dataset_id=COVERAGE_ID,
            version=VERSION,
            retrieved_on=datetime.now(UTC),
            licence=LICENCE,
            redistribution="allowed",
            source_url=SOURCE_URL,
            archive=Archive(
                status="pending", source_url=SOURCE_URL, unblocked_by=ARCHIVE_UNBLOCKED_BY
            ),
            variables=list(VARIABLES),
        )

    def baseline_years(self) -> dict[str, list[int]]:
        return {name: [] for name in VARIABLES}
