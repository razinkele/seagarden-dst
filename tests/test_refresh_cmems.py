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


def test_to_yearly_keeps_twelve_months_when_one_is_missing_from_every_year():
    """The docstring's NaN guarantee, in the case `unstack` alone does not deliver.

    `unstack` fills only the cartesian product of the (year, month) pairs it
    OBSERVED. A month absent from some years arrives as NaN; a month absent from
    EVERY year never enters the month index, and the axis comes back eleven long.
    `check_shapes` compares dim names, not lengths, so nothing downstream notices.

    Two years here, not one, so the failure cannot be blamed on a degenerate span.
    """
    from seagarden_dst.refresh.sources import cmems

    source = _monthly_dataset([2024, 2025])["so"]
    without_june = source.sel(time=source["time"].dt.month != 6)
    assert len(without_june["time"]) == 22  # the gap really is in both years

    reshaped = cmems.to_yearly(without_june)

    assert list(reshaped["month"].values) == list(range(1, 13))
    assert bool(reshaped.isel(month=5).isnull().all())  # June, the hole, as NaN
    assert not bool(reshaped.isel(month=4).isnull().any())  # May, intact


def test_to_yearly_does_not_invent_a_year_the_source_never_carried():
    """The deliberate asymmetry: months are reindexed, years are not.

    A missing year must stay missing so `resolve_baselines` can refuse it. An
    all-NaN year would satisfy that guard and then collapse `valid` through
    `_coverage_of`'s `.all()` — a quiet empty artifact in place of a loud refusal.
    """
    from seagarden_dst.refresh.sources import cmems

    source = _monthly_dataset([2024, 2025, 2026])["so"]
    without_2025 = source.sel(time=source["time"].dt.year != 2025)

    reshaped = cmems.to_yearly(without_2025)

    assert list(reshaped["year"].values) == [2024, 2026]


def test_drop_depth_refuses_a_depth_axis_with_more_than_one_level():
    """A two-level 0-1 m window must raise, not silently keep element zero."""
    import xarray as xr

    from seagarden_dst.refresh.sources import cmems

    grid = _tiny_grid()
    two_levels = xr.DataArray(
        np.zeros((2, 1, 3, 3), dtype="float32"),
        dims=("depth", "time", "latitude", "longitude"),
        coords={"depth": [0.5, 0.9], "latitude": grid.lats(), "longitude": grid.lons()},
    )

    with pytest.raises(ValueError, match="expected exactly 1"):
        cmems.drop_depth(two_levels)


def test_drop_depth_still_removes_a_single_level_axis():
    """The ordinary case the guard must not disturb."""
    import xarray as xr

    from seagarden_dst.refresh.sources import cmems

    grid = _tiny_grid()
    one_level = xr.DataArray(
        np.zeros((1, 3, 3), dtype="float32"),
        dims=("depth", "latitude", "longitude"),
        coords={"depth": [0.5], "latitude": grid.lats(), "longitude": grid.lons()},
    )

    dropped = cmems.drop_depth(one_level)

    assert "depth" not in dropped.dims
    assert "depth" not in dropped.coords


# --- the coordinate convention, confirmed against real data on 2026-09-24 ---------------


def _centre_labelled_dataset(years: list[int], jitter: float = 0.0):
    """What Copernicus actually returns: cell CENTRES, half a step above GridSpec's
    lower edges, and (between products) not bit-identical - the wave grid differs
    from the physics grid in the fifth decimal."""
    grid = _tiny_grid()
    data = _monthly_dataset(years)
    return data.assign_coords(
        latitude=grid.lats() + grid.lat_step / 2 + jitter,
        longitude=grid.lons() + grid.lon_step / 2 - jitter,
    )


def test_open_window_snaps_centre_labelled_coordinates_onto_the_grid():
    """The first real refresh (2026-09-24) died in `xr.merge(join="exact")`: every
    Copernicus layer came back labelled by cell centre (53.50829 for the cell GridSpec
    labels 53.5), and the physics and wave grids differed from each other by ~2e-5
    degrees. Same cells, different labels. `open_window` relabels with the GridSpec's
    own coordinates so the layers exact-join with each other and with EMODnet."""
    import numpy as np

    from seagarden_dst.refresh.sources import cmems

    grid = _tiny_grid()
    opened = cmems.open_window(
        "ds-id", ["so"], grid, YearRange(start=2024, end=2024),
        opener=lambda **kwargs: _centre_labelled_dataset([2024], jitter=2e-5),
    )
    assert np.array_equal(opened["latitude"].values, grid.lats())
    assert np.array_equal(opened["longitude"].values, grid.lons())


def test_open_window_leaves_edge_labelled_coordinates_bit_identical():
    """Fixtures built straight from GridSpec (every driver test) still pass through
    unchanged - the snap is a relabel of the same cells, not a shift."""
    import numpy as np

    from seagarden_dst.refresh.sources import cmems

    grid = _tiny_grid()
    opened = cmems.open_window(
        "ds-id", ["so"], grid, YearRange(start=2024, end=2024),
        opener=lambda **kwargs: _monthly_dataset([2024]),
    )
    assert np.array_equal(opened["latitude"].values, grid.lats())
    assert np.array_equal(opened["longitude"].values, grid.lons())


def test_open_window_refuses_a_window_that_is_not_the_grid():
    """A whole-step offset is a different set of cells, never relabelled; a wrong
    size likewise. Both name the axis so the log says which product moved."""
    from seagarden_dst.refresh.sources import cmems

    grid = _tiny_grid()
    shifted = _monthly_dataset([2024]).assign_coords(latitude=grid.lats() + grid.lat_step)
    with pytest.raises(cmems.GridMismatch, match="latitude"):
        cmems.open_window(
            "ds-id", ["so"], grid, YearRange(start=2024, end=2024),
            opener=lambda **kwargs: shifted,
        )

    short = _monthly_dataset([2024]).isel(longitude=slice(0, 2))
    with pytest.raises(cmems.GridMismatch, match="longitude"):
        cmems.open_window(
            "ds-id", ["so"], grid, YearRange(start=2024, end=2024),
            opener=lambda **kwargs: short,
        )
