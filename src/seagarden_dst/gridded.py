"""Read the forcing artifact package C builds (§6).

**The only module outside `refresh/` that imports xarray.** The model core and the app
must both work on an install with no `spatial` extra — CI's `[app,dev]` job is that
install — so `artifact/` was built pydantic+stdlib+numpy only and `load_pair` returns
`(Manifest, Path)` rather than an opened dataset, leaving the open to whoever has xarray.
That is this module. `tests/test_gridded_isolation.py` asserts it.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from seagarden_dst.artifact.manifest import ARTIFACT_SCHEMA_VERSION, Manifest
from seagarden_dst.artifact.pair import TornPair, load_pair
from seagarden_dst.forcing import (
    PLACEHOLDER_SURFACE_PAR,
    Aggregation,
    Coverage,
    ForcingChoice,
    ForcingUnavailable,
    SiteConditions,
    SiteQuery,
    SiteReading,
    day_of_year,
    placeholder_choice,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    import xarray as xr

#: §6.3's locator. The env var and this default both name the directory that holds the
#: artifact/manifest pair, matching the refresh CLI's own `--target` default.
_DATA_DIR_ENV = "SEAGARDEN_DATA_DIR"
_DEFAULT_DATA_DIR = Path("data/forcing")

_EARTH_RADIUS_KM = 6371.0


def artifact_directory() -> Path:
    """Where the artifact/manifest pair lives (§6.3)."""
    return Path(os.environ.get(_DATA_DIR_ENV, _DEFAULT_DATA_DIR))


class UnrecognisedSchema(ValueError):
    """The artifact's schema version is not the one this build reads (§7)."""

    def __init__(self, message: str, *, found: int) -> None:
        super().__init__(message)
        self.found = found


@dataclass(frozen=True, kw_only=True)
class GriddedConditions(SiteConditions):
    """`SiteConditions` that remember which artifact cells they were averaged over.

    A reader-specific index, which is why it is a subclass here and not a field on the
    core type. `dataclasses.replace` returns this subclass with both fields intact, so a
    nutrient scenario's replaced conditions still find their cells (D§9 item 3).
    """

    #: The (row, col) artifact cells these conditions were averaged over, as plain
    #: Python ints, row-major. Exactly one cell under CONTAINING_CELL; two or more
    #: under UNWEIGHTED_MEAN (spec §3.2 labels by the number of VALID cells).
    cells: tuple[tuple[int, int], ...]
    #: The artifact year these annual means were taken for. `daily_forcing` refuses a
    #: `year` that differs (spec §3.6): the DIN ratio is only exactly 1.0 against the
    #: year the site was read for, and rescaling another year's field to this year's
    #: mean would be the silent substitution §6.2 forbids.
    year: int


class GriddedForcing:
    """Site conditions read from the artifact, for a polygon and a year."""

    def __init__(self, manifest: Manifest, dataset: xr.Dataset) -> None:
        self._manifest = manifest
        self._ds = dataset
        self.latitudes = np.asarray(dataset["latitude"].values, dtype=float)
        self.longitudes = np.asarray(dataset["longitude"].values, dtype=float)
        self._years = [int(y) for y in np.asarray(dataset["year"].values)]

    @classmethod
    def from_directory(cls, directory) -> GriddedForcing:
        import shapely  # noqa: F401 - imported here so a missing extra is reported first
        import xarray as xr

        # `load_pair` refuses a torn pair on the sha256 linking artifact to manifest.
        # There is deliberately no opt-out: that is C-a's atomicity guarantee.
        manifest, artifact = load_pair(Path(directory))
        if manifest.artifact_schema_version != ARTIFACT_SCHEMA_VERSION:
            raise UnrecognisedSchema(
                f"unrecognised artifact_schema_version "
                f"{manifest.artifact_schema_version}: this build reads version "
                f"{ARTIFACT_SCHEMA_VERSION}. Refusing rather than reading an artifact "
                "whose shape is not known (§7).",
                found=manifest.artifact_schema_version,
            )
        return cls(manifest, xr.open_dataset(artifact, engine="h5netcdf").load())

    @property
    def years(self) -> list[int]:
        """The years the artifact carries, ascending."""
        return sorted(self._years)

    @property
    def built_on(self):
        """When the artifact was built - `select_forcing` reads this, not `_manifest`,
        so a reader's own build date is not an implementation detail its caller must
        reach past a leading underscore for."""
        return self._manifest.built_on

    def reading_at(self, query: SiteQuery) -> SiteReading:
        geom = self._geometry_of(query.geometry_wkt)
        point = geom if geom.geom_type == "Point" else geom.centroid
        lat, lon = point.y, point.x
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

        conditions = self._conditions_at(((row, col),), query.year, query.region)
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
        cells = self._cell_for_site(site, year)
        start, end = window
        first = day_of_year(start, 1)
        last = day_of_year(end, 28)
        wraps = last < first
        if wraps:
            next_year = year + 1
            if next_year not in self._years:
                raise ForcingUnavailable(
                    f"wrapping window needs {year} and {next_year}, but the artifact "
                    f"carries {self._years}"
                )
            last += 365

        if year not in self._years:
            raise ForcingUnavailable(
                f"artifact does not carry year {year}; available years {self._years}"
            )

        days = np.arange(first, last + 1, dtype=float)
        month_years: list[tuple[int, int, int]] = []
        if wraps:
            month_years.extend((month, year, day_of_year(month)) for month in range(start, 13))
            month_years.extend(
                (month, year + 1, day_of_year(month) + 365) for month in range(1, end + 1)
            )
        else:
            month_years.extend((month, year, day_of_year(month)) for month in range(start, end + 1))

        temp = self._interpolated_monthly("temp_c", cells, month_years, days)
        din = self._interpolated_monthly("din_umol_l", cells, month_years, days)

        # The artifact carries no PAR (C§3.3), so only the seasonal shape matches the
        # placeholder; the magnitude remains the site's invented placeholder value.
        season = 0.5 * (1.0 + np.cos(2.0 * np.pi * (days - 172.0) / 365.25))
        par = site.par_at_depth() * (0.25 + 0.75 * season)
        return days, par, temp, din

    def _geometry_of(self, wkt: str):
        """A non-empty shapely Point or Polygon, or ValueError naming the WKT.

        shapely's own failures are not ValueErrors (`GEOSException` is a
        `ShapelyError`), and `POLYGON EMPTY` parses to an empty geometry with no
        centroid, so both are wrapped here (spec §3.1).
        """
        import shapely
        from shapely.errors import ShapelyError

        try:
            geom = shapely.from_wkt(wkt)
        except ShapelyError as exc:
            raise ValueError(f"could not parse site geometry WKT {wkt!r}") from exc
        if geom is None or geom.is_empty or geom.geom_type not in ("Point", "Polygon"):
            raise ValueError(f"could not parse site geometry WKT {wkt!r}")
        return geom

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

    def _cell_for_site(self, site: SiteConditions, year: int) -> tuple[tuple[int, int], ...]:
        """The cells a reader-produced site was averaged over, for the same year.

        A handle from a different reader over a same-shape grid is accepted by design
        (tests hold the fixture reader and a tmp copy; the app holds one reader per
        session), so the check is on shape and year, not identity.
        """
        n_lat, n_lon = self.latitudes.size, self.longitudes.size
        usable = (
            isinstance(site, GriddedConditions)
            and len(site.cells) > 0
            and all(0 <= r < n_lat and 0 <= c < n_lon for r, c in site.cells)
            and site.year == year
        )
        if not usable:
            raise ValueError(
                "daily_forcing needs a GriddedConditions produced by a GriddedForcing "
                "over this grid, for the same year"
            )
        return site.cells

    def _cell_mean_monthly(
        self, name: str, year: int, cells: tuple[tuple[int, int], ...]
    ) -> np.ndarray:
        """The 12 monthly values of a per-year field, averaged over `cells`, float64.

        The ONLY reader of the per-year monthly fields (spec §3.4). Cast to float64
        before any reduction, then `np.mean` over the cell axis: for one cell that is
        the identity on a float64 vector, so single-cell readings are bit-identical to
        a direct computation; and because `_conditions_at` and `daily_forcing` both
        come here, the §3.6 ratio is exactly 1.0 for an unmodified site.
        """
        rows = [r for r, _ in cells]
        cols = [c for _, c in cells]
        year_index = self._years.index(year)
        block = np.asarray(self._ds[name].values[year_index][:, rows, cols], dtype=float)
        return np.mean(block, axis=1)

    def _interpolated_monthly(
        self,
        name: str,
        cells: tuple[tuple[int, int], ...],
        month_years: list[tuple[int, int, int]],
        days: np.ndarray,
        scale: float = 1.0,
    ) -> np.ndarray:
        by_year = {
            year: self._cell_mean_monthly(name, year, cells)
            for year in {year for _, year, _ in month_years}
        }
        x = np.asarray([day for _, _, day in month_years], dtype=float)
        values = np.asarray([by_year[year][month - 1] for month, year, _ in month_years])
        return np.interp(days, x, values * scale)

    def _conditions_at(
        self, cells: tuple[tuple[int, int], ...], year: int, region: str | None
    ) -> GriddedConditions:
        """Annual statistics over `cells`, field-mean-first (spec §3.4)."""
        temp = self._cell_mean_monthly("temp_c", year, cells)
        salinity = self._cell_mean_monthly("salinity_psu", year, cells)
        din = self._cell_mean_monthly("din_umol_l", year, cells)
        dip = self._cell_mean_monthly("dip_umol_l", year, cells)
        attenuation = self._cell_mean_monthly("light_attenuation_k", year, cells)
        rows = [r for r, _ in cells]
        cols = [c for _, c in cells]
        wave = np.mean(
            np.asarray(self._ds["significant_wave_m"].values[:, rows, cols], dtype=float), axis=1
        )
        depth = np.mean(np.asarray(self._ds["depth_mean_m"].values[rows, cols], dtype=float))

        return GriddedConditions(
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
            depth_m=float(depth),
            significant_wave_m=float(np.mean(wave)),
            light_attenuation_k=float(np.mean(attenuation)),
            cells=cells,
            year=year,
        )


def select_forcing(directory: Path | None = None) -> ForcingChoice:
    """Choose what the tool runs on this session (E§3.2). Never raises.

    Every way of falling back yields the placeholder with a reason that names the
    directory, so the banner can say why. The manifest's presence is checked before
    the import so a pip-only install with no artifact reports the missing artifact,
    which is the more useful of its two problems.
    """
    directory = Path(directory) if directory is not None else artifact_directory()
    manifest_path = directory / "manifest.json"
    if not manifest_path.exists():
        return placeholder_choice(f"no artifact at {directory}", directory)

    # `Manifest`'s own validator (`_check_schema_version`) refuses a foreign
    # `artifact_schema_version` before `GriddedForcing.from_directory` ever raises
    # `UnrecognisedSchema` - so a manifest from a newer pipeline would otherwise fall
    # into the catch-all below and report a multi-line pydantic dump instead of naming
    # the version. Read the raw JSON first and short-circuit on that one field; anything
    # that does not parse, or lacks the field, falls through to `from_directory` so the
    # existing rows (missing file, torn pair, any other failure) handle it as before.
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raw = None
    if isinstance(raw, dict):
        found = raw.get("artifact_schema_version")
        if isinstance(found, str) and found.isdigit():
            found = int(found)
        if isinstance(found, int) and found != ARTIFACT_SCHEMA_VERSION:
            return placeholder_choice(
                f"artifact at {directory} has schema version {found}; this build reads "
                f"{ARTIFACT_SCHEMA_VERSION}",
                directory,
            )

    try:
        reader = GriddedForcing.from_directory(directory)
    except ImportError:
        return placeholder_choice(
            f"this install has no spatial extra (xarray/h5netcdf/shapely), so the artifact "
            f"at {directory} cannot be read",
            directory,
        )
    except TornPair:
        return placeholder_choice(
            f"artifact at {directory} failed its checksum; refusing to read it", directory
        )
    except UnrecognisedSchema as exc:
        return placeholder_choice(
            f"artifact at {directory} has schema version {exc.found}; this build reads "
            f"{ARTIFACT_SCHEMA_VERSION}",
            directory,
        )
    except Exception as exc:  # noqa: BLE001 - named in the reason, never swallowed
        # Only the first line: a multi-line exception message (a traceback-shaped
        # str, or a pydantic ValidationError's own multi-line dump) would otherwise
        # spill past the sentence the banner shows.
        detail = str(exc).splitlines()[0] if str(exc) else ""
        return placeholder_choice(
            f"could not open the artifact at {directory}: {type(exc).__name__}: {detail}",
            directory,
        )
    return ForcingChoice(
        source=reader, kind="artifact", reason="", year=reader.years[-1],
        built_on=reader.built_on, directory=directory,
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
