import pytest

pytest.importorskip("xarray")
import numpy as np  # noqa: E402
import xarray as xr  # noqa: E402

from seagarden_dst.refresh.shapes import EXPECTED_DIMS, SPATIAL_DIMS, check_shapes  # noqa: E402

pytestmark = pytest.mark.spatial


def test_the_spatial_dims_are_spelled_out():
    # The spec's C§3.2 dims column abbreviates to "lat, lon"; the line beneath it and
    # the committed fixture both use the long form. Code that reduces over every
    # NON-spatial dim while looking for the short form collapses `valid` to a scalar.
    assert SPATIAL_DIMS == ("latitude", "longitude")


def test_the_three_shapes_are_all_represented():
    assert EXPECTED_DIMS["temp_c"] == ("year", "month", "latitude", "longitude")
    assert EXPECTED_DIMS["significant_wave_m"] == ("month", "latitude", "longitude")
    assert EXPECTED_DIMS["depth_mean_m"] == ("latitude", "longitude")
    assert EXPECTED_DIMS["valid"] == ("latitude", "longitude")


def _ds(name, dims, sizes):
    return xr.Dataset({name: (dims, np.ones(sizes, dtype="float32"))})


def test_check_shapes_accepts_the_declared_shape():
    check_shapes(_ds("depth_mean_m", ("latitude", "longitude"), (2, 2)))


def test_check_shapes_rejects_a_short_form_coordinate_name():
    # The exact defect this function exists to catch.
    with pytest.raises(ValueError, match="expected dims"):
        check_shapes(_ds("depth_mean_m", ("lat", "lon"), (2, 2)))


def test_check_shapes_rejects_a_transposed_variable():
    with pytest.raises(ValueError, match="expected dims"):
        check_shapes(_ds("depth_mean_m", ("longitude", "latitude"), (2, 2)))


def test_check_shapes_rejects_a_variable_it_has_never_heard_of():
    with pytest.raises(ValueError, match="no declared shape"):
        check_shapes(_ds("surface_par", ("latitude", "longitude"), (2, 2)))


def test_check_shapes_rejects_a_wave_field_that_grew_a_year_dimension():
    # The wave layer collapses year into a 2023-2025 p95. A year dim here means the
    # collapse did not happen, and its baseline would then be read off the data.
    with pytest.raises(ValueError, match="expected dims"):
        check_shapes(
            _ds("significant_wave_m", ("year", "month", "latitude", "longitude"), (2, 12, 2, 2))
        )
