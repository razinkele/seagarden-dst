"""The one seam between the layers and Copernicus (R2)."""

from __future__ import annotations

import numpy as np
import pytest

from seagarden_dst.artifact.grid import GridSpec
from seagarden_dst.refresh.layer import YearRange

pytestmark = pytest.mark.spatial


def _tiny_grid() -> GridSpec:
    """A 3x3 grid, the fixture's shape (C§7)."""
    return GridSpec(
        crs="EPSG:4326",
        lat_min=54.0, lat_max=54.05, lon_min=10.0, lon_max=10.09,
        lat_step=0.016666, lon_step=0.027777,
        n_lat=3, n_lon=3,
    )


def _monthly_dataset(years: list[int], value: float = 1.0):
    import pandas as pd
    import xarray as xr

    times = pd.date_range(f"{years[0]}-01-01", f"{years[-1]}-12-01", freq="MS")
    grid = _tiny_grid()
    data = np.full((len(times), 3, 3), value, dtype="float32")
    return xr.Dataset(
        {"so": (("time", "latitude", "longitude"), data)},
        coords={"time": times, "latitude": grid.lats(), "longitude": grid.lons()},
    )


def test_open_window_passes_the_grid_extent_and_the_surface_depth():
    from seagarden_dst.refresh.sources import cmems

    seen: dict[str, object] = {}

    def fake_opener(**kwargs: object):
        seen.update(kwargs)
        return _monthly_dataset([2024])

    cmems.open_window(
        "ds-id", ["so"], _tiny_grid(), YearRange(start=2024, end=2024), opener=fake_opener
    )

    assert seen["dataset_id"] == "ds-id"
    assert seen["variables"] == ["so"]
    assert seen["minimum_latitude"] == 54.0
    assert seen["maximum_longitude"] == 10.09
    assert seen["minimum_depth"] == cmems.SURFACE_MIN_DEPTH
    assert seen["maximum_depth"] == cmems.SURFACE_MAX_DEPTH
    assert seen["start_datetime"].startswith("2024-01-01")
    assert seen["end_datetime"].startswith("2024-12-31")


def test_open_window_omits_depth_when_the_product_has_no_depth_axis():
    """The wave product is 2-D; asking it for a depth window is an error."""
    from seagarden_dst.refresh.sources import cmems

    seen: dict[str, object] = {}

    def fake_opener(**kwargs: object):
        seen.update(kwargs)
        return _monthly_dataset([2024])

    cmems.open_window(
        "wav", ["VHM0"], _tiny_grid(), YearRange(start=2024, end=2024),
        opener=fake_opener, surface=False,
    )

    assert "minimum_depth" not in seen
    assert "maximum_depth" not in seen


def test_to_yearly_splits_time_into_year_and_month_in_that_order():
    from seagarden_dst.refresh.sources import cmems

    reshaped = cmems.to_yearly(_monthly_dataset([2024, 2025])["so"])

    assert tuple(reshaped.dims) == ("year", "month", "latitude", "longitude")
    assert list(reshaped["year"].values) == [2024, 2025]
    assert list(reshaped["month"].values) == list(range(1, 13))
