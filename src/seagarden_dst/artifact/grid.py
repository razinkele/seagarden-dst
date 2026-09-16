"""The artifact grid, defined once (C§3.1)."""

from __future__ import annotations

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

# Copernicus Baltic native resolution. NOT a choice: package B established that
# coarsening to ~4 km land-masks the cell containing Tagalaht, the only published
# anchor the parameterisation has.
_LAT_STEP = 0.016666
_LON_STEP = 0.027777


class GridSpec(BaseModel):
    """The target grid. Widening the extent is a change here plus a refresh."""

    model_config = ConfigDict(extra="forbid")

    crs: str
    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float
    lat_step: float = Field(gt=0)
    lon_step: float = Field(gt=0)
    n_lat: int = Field(gt=0)
    n_lon: int = Field(gt=0)

    @model_validator(mode="after")
    def _check_extent_is_not_inverted(self) -> GridSpec:
        if self.lat_max <= self.lat_min:
            raise ValueError(f"lat_max {self.lat_max} must exceed lat_min {self.lat_min}")
        if self.lon_max <= self.lon_min:
            raise ValueError(f"lon_max {self.lon_max} must exceed lon_min {self.lon_min}")
        # Check that the extent implied by origin, step, and count matches the declared max
        # within one step tolerance (needed because step constants are truncated decimals).
        implied_lat_max = self.lat_min + self.n_lat * self.lat_step
        if abs(implied_lat_max - self.lat_max) > self.lat_step:
            raise ValueError(
                f"lat grid extent is incoherent: lat_min + n_lat*lat_step = "
                f"{implied_lat_max} differs from lat_max {self.lat_max} by more than one step"
            )
        implied_lon_max = self.lon_min + self.n_lon * self.lon_step
        if abs(implied_lon_max - self.lon_max) > self.lon_step:
            raise ValueError(
                f"lon grid extent is incoherent: lon_min + n_lon*lon_step = "
                f"{implied_lon_max} differs from lon_max {self.lon_max} by more than one step"
            )
        return self

    @classmethod
    def baltic(cls) -> GridSpec:
        """The shipped extent. Excludes the Gulfs of Bothnia and Finland (C§3.1)."""
        return cls(
            crs="EPSG:4326",
            lat_min=53.5, lat_max=60.0, lon_min=9.5, lon_max=27.0,
            lat_step=_LAT_STEP, lon_step=_LON_STEP,
            n_lat=390, n_lon=630,
        )

    def lats(self) -> np.ndarray:
        """Latitude coordinates for each grid cell.

        Returns the LOWER CELL EDGE of each cell (the southern boundary).
        The last value is one full step below lat_max by construction, since lat_max
        is the outer edge of the final cell, not a coordinate present in the array.
        """
        return self.lat_min + np.arange(self.n_lat, dtype="float64") * self.lat_step

    def lons(self) -> np.ndarray:
        """Longitude coordinates for each grid cell.

        Returns the LOWER CELL EDGE of each cell (the western boundary).
        The last value is one full step below lon_max by construction, since lon_max
        is the outer edge of the final cell, not a coordinate present in the array.
        """
        return self.lon_min + np.arange(self.n_lon, dtype="float64") * self.lon_step
