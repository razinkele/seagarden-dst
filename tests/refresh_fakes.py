"""Synthetic `Layer` implementations for driver tests (R6).

These live in `tests/` and never in `refresh/`: a fake in production code is a test
seam nobody can see. They exist so every driver clause — merge, `valid`, baselines,
shapes, fail-on-any-layer — is provable with no network and no credential.

**xarray is imported inside `build`, not at module scope.** `-m` deselects after
collection, so a module-scope import here would break collection of the unmarked CLI
tests that import `FakeLayer` for its `probe()`, and turn CI's `[app,dev]` job red.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from seagarden_dst.artifact.grid import GridSpec
from seagarden_dst.artifact.manifest import Archive, LayerProvenance
from seagarden_dst.refresh.layer import ProbeResult, YearRange

if TYPE_CHECKING:  # pragma: no cover - typing only
    import xarray as xr


class LayerBuildFailed(RuntimeError):
    """Raised by a `FakeLayer` told to fail, so the driver's C§6.1 row 1 has a case."""


class FakeLayer:
    """A `Layer` that returns data handed to it instead of fetching any.

    `shape` picks one of C§3.2's three:
      "yearly"  -> (year, month, latitude, longitude)  the five reanalysis fields
      "monthly" -> (month, latitude, longitude)        significant_wave_m
      "static"  -> (latitude, longitude)               the bathymetry fields
    """

    def __init__(
        self,
        name: str,
        variables: list[str],
        *,
        claims: list[str] | None = None,
        shape: str = "yearly",
        window: list[int] | None = None,
        data: dict[str, tuple] | None = None,
        fail_on_build: bool = False,
        reachable: bool = True,
        dataset_id: str | None = None,
    ) -> None:
        self.name = name
        self._variables = variables
        # What the layer CLAIMS, which is not always what it produces: `copernicus_bgc`
        # produces din_umol_l but a Derivation claims it, and `copernicus_bgc_light`
        # claims nothing at all (C§5). Defaults to the produced set.
        self._claims = list(variables) if claims is None else list(claims)
        self._shape = shape
        self._window = window
        self._data = data
        self._fail_on_build = fail_on_build
        self._reachable = reachable
        self._dataset_id = dataset_id or f"{name}-dataset"
        self._last_years: list[int] = []

    def probe(self) -> ProbeResult:
        return ProbeResult(
            name=self.name,
            status="ok" if self._reachable else "unreachable",
            reachable=self._reachable,
            detail="catalogue responded" if self._reachable else "catalogue 404",
        )

    def build(self, grid: GridSpec, years: YearRange, workdir: Path) -> xr.Dataset:
        import numpy as np
        import xarray as xr

        if self._fail_on_build:
            raise LayerBuildFailed(f"layer {self.name} could not build")
        self._last_years = years.years()
        if self._data is not None:
            return xr.Dataset(self._data)

        lat, lon = grid.lats(), grid.lons()
        months = list(range(1, 13))
        if self._shape == "static":
            dims = ("latitude", "longitude")
            sizes = (grid.n_lat, grid.n_lon)
            coords = {"latitude": lat, "longitude": lon}
        elif self._shape == "monthly":
            dims = ("month", "latitude", "longitude")
            sizes = (12, grid.n_lat, grid.n_lon)
            coords = {"month": months, "latitude": lat, "longitude": lon}
        else:
            dims = ("year", "month", "latitude", "longitude")
            sizes = (len(self._last_years), 12, grid.n_lat, grid.n_lon)
            coords = {
                "year": self._last_years,
                "month": months,
                "latitude": lat,
                "longitude": lon,
            }
        return xr.Dataset(
            {name: (dims, np.ones(sizes, dtype="float32")) for name in self._variables},
            coords=coords,
        )

    def baseline_years(self) -> dict[str, list[int]]:
        """What window each produced variable rests on (R2).

        Static fields get `[]`; a fake with an explicit `window` reports it whatever
        was asked for — which is how the wave layer's fixed 2023-2025 is modelled.

        **Order-dependent, unlike a real layer.** Without a `window`, this reports
        `self._last_years`, which only `build()` sets. `run_refresh` calls `_build_all`
        before `_declared_windows`, so it is populated in time — but do not reorder
        those two, or every yearly variable declares an empty window and then
        "disagrees with the data". A real layer knows its window without building.
        """
        if self._window is not None:
            return {name: list(self._window) for name in self._variables}
        if self._shape == "static":
            return {name: [] for name in self._variables}
        return {name: list(self._last_years) for name in self._variables}

    def provenance(self) -> LayerProvenance:
        return LayerProvenance(
            name=self.name,
            source="Fake",
            product_id=f"{self.name}-product",
            dataset_id=self._dataset_id,
            version="1.0",
            retrieved_on=datetime(2026, 1, 1, tzinfo=UTC),
            licence="CC-BY-4.0",
            redistribution="allowed",
            source_url=f"https://example.invalid/{self.name}",
            archive=Archive(
                status="pending",
                source_url=f"https://example.invalid/{self.name}",
                unblocked_by="the Zenodo deposit in C§8.1",
            ),
            variables=list(self._claims),
        )
