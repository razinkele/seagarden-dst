"""Read the forcing artifact package C builds (§6).

**The only module outside `refresh/` that imports xarray.** The model core and the app
must both work on an install with no `spatial` extra — CI's `[app,dev]` job is that
install — so `artifact/` was built pydantic+stdlib+numpy only and `load_pair` returns
`(Manifest, Path)` rather than an opened dataset, leaving the open to whoever has xarray.
That is this module. `tests/test_gridded_isolation.py` asserts it.
"""

from __future__ import annotations

import math
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from seagarden_dst.artifact.manifest import ARTIFACT_SCHEMA_VERSION, Manifest
from seagarden_dst.artifact.pair import load_pair
from seagarden_dst.forcing import (
    PLACEHOLDER_SURFACE_PAR,
    Aggregation,
    Coverage,
    SiteConditions,
    SiteQuery,
    SiteReading,
    day_of_year,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    import xarray as xr

#: §6.3's locator. Nothing read this before package D-a; the refresh CLI writes to its
#: own `--target`, defaulting to `data/forcing`.
_DATA_DIR_ENV = "SEAGARDEN_DATA_DIR"
_DEFAULT_DATA_DIR = Path("data")

_POINT = re.compile(r"POINT\s*\(\s*([-\d.]+)\s+([-\d.]+)\s*\)", re.IGNORECASE)
_EARTH_RADIUS_KM = 6371.0


def artifact_directory() -> Path:
    """Where the artifact/manifest pair lives (§6.3)."""
    return Path(os.environ.get(_DATA_DIR_ENV, _DEFAULT_DATA_DIR))


class GriddedForcing:
    """Site conditions read from the artifact, for a polygon and a year."""

    def __init__(self, manifest: Manifest, dataset: xr.Dataset) -> None:
        self._manifest = manifest
        self._ds = dataset
        self.latitudes = np.asarray(dataset["latitude"].values, dtype=float)
        self.longitudes = np.asarray(dataset["longitude"].values, dtype=float)
        self._years = [int(y) for y in np.asarray(dataset["year"].values)]
        # `SiteConditions` deliberately carries no position. Remember the object this
        # reader produced so the daily series uses the same cell rather than trying to
        # reverse-engineer a location from annual means.
        self._site_cells: dict[int, tuple[int, int]] = {}

    @classmethod
    def from_directory(cls, directory) -> GriddedForcing:
        import xarray as xr

        # `load_pair` refuses a torn pair on the sha256 linking artifact to manifest.
        # There is deliberately no opt-out: that is C-a's atomicity guarantee.
        manifest, artifact = load_pair(Path(directory))
        if manifest.artifact_schema_version != ARTIFACT_SCHEMA_VERSION:
            raise ValueError(
                f"unrecognised artifact_schema_version "
                f"{manifest.artifact_schema_version}: this build reads version "
                f"{ARTIFACT_SCHEMA_VERSION}. Refusing rather than reading an artifact "
                "whose shape is not known (§7)."
            )
        return cls(manifest, xr.open_dataset(artifact, engine="h5netcdf").load())

    def reading_at(self, query: SiteQuery) -> SiteReading:
        lat, lon = self._point_of(query)
        row, col = self._nearest_index(lat, lon)

        if query.year not in self._years:
            # Never substitutes another year (§6.2): interannual spread is the dominant
            # term, so a neighbouring year is a different answer, not an approximation.
            return SiteReading(
                conditions=None,
                coverage=Coverage.YEAR_ABSENT,
                year=query.year,
                aggregation=Aggregation.CONTAINING_CELL,
                from_artifact=True,
            )

        # The `valid` field, by value. NEVER inferred from NaN: the committed fixture's
        # invalid cell holds finite numbers, so a NaN test would call it assessable.
        if not bool(self._ds["valid"].values[row, col]):
            return SiteReading(
                conditions=None,
                coverage=Coverage.CELL_INVALID,
                year=query.year,
                aggregation=Aggregation.CONTAINING_CELL,
                nearest_valid_km=self._nearest_valid_km(row, col),
                from_artifact=True,
            )

        conditions = self._conditions_at(row, col, query.year, query.region)
        self._site_cells[id(conditions)] = (row, col)
        return SiteReading(
            conditions=conditions,
            coverage=Coverage.VALID,
            year=query.year,
            aggregation=Aggregation.CONTAINING_CELL,
            from_artifact=True,
        )

    def daily_forcing(
        self, site: SiteConditions, window: tuple[int, int], year: int
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        row, col = self._cell_for_site(site)
        start, end = window
        first = day_of_year(start, 1)
        last = day_of_year(end, 28)
        wraps = last < first
        if wraps:
            next_year = year + 1
            if next_year not in self._years:
                raise ValueError(
                    f"wrapping window needs {year} and {next_year}, but the artifact "
                    f"carries {self._years}"
                )
            last += 365

        if year not in self._years:
            raise ValueError(f"artifact does not carry year {year}; available years {self._years}")

        days = np.arange(first, last + 1, dtype=float)
        month_years: list[tuple[int, int, int]] = []
        if wraps:
            month_years.extend((month, year, day_of_year(month)) for month in range(start, 13))
            month_years.extend(
                (month, year + 1, day_of_year(month) + 365) for month in range(1, end + 1)
            )
        else:
            month_years.extend((month, year, day_of_year(month)) for month in range(start, end + 1))

        temp = self._interpolated_monthly("temp_c", row, col, month_years, days)
        din = self._interpolated_monthly("din_umol_l", row, col, month_years, days)

        # The artifact carries no PAR (C§3.3), so only the seasonal shape matches the
        # placeholder; the magnitude remains the site's invented placeholder value.
        season = 0.5 * (1.0 + np.cos(2.0 * np.pi * (days - 172.0) / 365.25))
        par = site.par_at_depth() * (0.25 + 0.75 * season)
        return days, par, temp, din

    def _point_of(self, query: SiteQuery) -> tuple[float, float]:
        match = _POINT.fullmatch(query.geometry_wkt.strip())
        if match:
            lon, lat = (float(match.group(1)), float(match.group(2)))
            return lat, lon

        text = query.geometry_wkt.strip()
        if text.upper().startswith("POLYGON"):
            numbers = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", text)]
            if len(numbers) >= 6 and len(numbers) % 2 == 0:
                points = list(zip(numbers[0::2], numbers[1::2], strict=True))
                if points[0] == points[-1]:
                    points = points[:-1]
                lon = sum(p[0] for p in points) / len(points)
                lat = sum(p[1] for p in points) / len(points)
                return lat, lon

        raise ValueError(f"could not parse site geometry WKT {query.geometry_wkt!r}")

    def _nearest_index(self, lat: float, lon: float) -> tuple[int, int]:
        row = int(np.abs(self.latitudes - lat).argmin())
        col = int(np.abs(self.longitudes - lon).argmin())
        return row, col

    def _nearest_valid_km(self, row: int, col: int) -> float | None:
        valid = np.asarray(self._ds["valid"].values, dtype=bool)
        rows, cols = np.where(valid)
        if rows.size == 0:
            return None

        lat = float(self.latitudes[row])
        lon = float(self.longitudes[col])
        distances = [
            _haversine_km(lat, lon, float(self.latitudes[r]), float(self.longitudes[c]))
            for r, c in zip(rows, cols, strict=True)
        ]
        return float(min(distances))

    def _cell_for_site(self, site: SiteConditions) -> tuple[int, int]:
        try:
            return self._site_cells[id(site)]
        except KeyError as exc:
            raise ValueError(
                "daily_forcing needs a SiteConditions object produced by this "
                "GriddedForcing instance"
            ) from exc

    def _interpolated_monthly(
        self,
        name: str,
        row: int,
        col: int,
        month_years: list[tuple[int, int, int]],
        days: np.ndarray,
    ) -> np.ndarray:
        x = np.asarray([day for _, _, day in month_years], dtype=float)
        values = np.asarray(
            [
                self._ds[name].values[self._years.index(year), month - 1, row, col]
                for month, year, _ in month_years
            ],
            dtype=float,
        )
        return np.interp(days, x, values)

    def _conditions_at(self, row: int, col: int, year: int, region: str | None) -> SiteConditions:
        year_index = self._years.index(year)

        def monthly(name: str) -> np.ndarray:
            return np.asarray(self._ds[name].values[year_index, :, row, col], dtype=float)

        temp = monthly("temp_c")
        salinity = monthly("salinity_psu")
        din = monthly("din_umol_l")
        dip = monthly("dip_umol_l")
        attenuation = monthly("light_attenuation_k")
        wave = np.asarray(self._ds["significant_wave_m"].values[:, row, col], dtype=float)

        return SiteConditions(
            region=region,
            salinity_psu=float(np.mean(salinity)),
            mean_temp_c=float(np.mean(temp)),
            summer_temp_c=float(np.max(temp)),
            winter_temp_c=float(np.min(temp)),
            # The artifact deliberately records `surface_par` as absent (C§3.3), so
            # this remains a placeholder constant even for artifact-backed conditions.
            surface_par=PLACEHOLDER_SURFACE_PAR,
            din_umol_l=float(np.mean(din)),
            dip_umol_l=float(np.mean(dip)),
            depth_m=float(self._ds["depth_mean_m"].values[row, col]),
            significant_wave_m=float(np.mean(wave)),
            light_attenuation_k=float(np.mean(attenuation)),
        )


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    r_lat1 = math.radians(lat1)
    r_lat2 = math.radians(lat2)
    a = (
        math.sin(d_lat / 2.0) ** 2
        + math.cos(r_lat1) * math.cos(r_lat2) * math.sin(d_lon / 2.0) ** 2
    )
    return _EARTH_RADIUS_KM * 2.0 * math.asin(math.sqrt(a))
