import pytest

pytest.importorskip("xarray")
import numpy as np  # noqa: E402
import xarray as xr  # noqa: E402

from seagarden_dst.refresh.merge import compute_valid, merge_layers  # noqa: E402

pytestmark = pytest.mark.spatial

_LAT = [55.0, 55.5]
_LON = [20.0, 20.5]
_COORDS = {"latitude": _LAT, "longitude": _LON}
_MONTHS = list(range(1, 13))


def _static(name, values):
    return xr.Dataset(
        {name: (("latitude", "longitude"), np.array(values, dtype="float32"))}, coords=_COORDS
    )


def _static_two(a_name, a_values, b_name, b_values):
    return xr.Dataset(
        {
            a_name: (("latitude", "longitude"), np.array(a_values, dtype="float32")),
            b_name: (("latitude", "longitude"), np.array(b_values, dtype="float32")),
        },
        coords=_COORDS,
    )


def test_coverage_intersects_the_variables_within_one_layer():
    # Every real coverage layer carries two variables (EXPECTED_DIMS in shapes.py):
    # copernicus_phy has salinity_psu + temp_c, copernicus_bgc has din_umol_l +
    # dip_umol_l, emodnet_bathy has depth_mean_m + depth_min_m. `covered = covered &
    # mask` must intersect them: a last-wins bug or an `|` bug would let one variable's
    # gap paper over the other's, silently widening `valid`.
    phy = _static_two(
        "salinity_psu",
        [[1.0, np.nan], [1.0, 1.0]],
        "temp_c",
        [[1.0, 1.0], [np.nan, 1.0]],
    )
    valid = compute_valid({"copernicus_phy": phy})
    assert valid.dims == ("latitude", "longitude")
    np.testing.assert_array_equal(valid.values, np.array([[True, False], [False, True]]))


def test_valid_is_the_intersection_of_two_disagreeing_masks():
    # C§10 clause 11. Copernicus says the top row is wet; EMODnet says the left
    # column is. They agree only on the top-left cell — the coastline case C§3.5
    # exists for.
    phy = _static("temp_c", [[1.0, 2.0], [np.nan, np.nan]])
    bathy = _static("depth_mean_m", [[3.0, np.nan], [4.0, np.nan]])
    valid = compute_valid({"copernicus_phy": phy, "emodnet_bathy": bathy})
    assert valid.dims == ("latitude", "longitude")
    np.testing.assert_array_equal(valid.values, np.array([[True, False], [False, False]]))


def test_coverage_reduces_the_real_four_dimensional_shape_to_two():
    # The defect a `lat`/`lon` spatial-dim tuple produces is a 0-d scalar, silently.
    a = np.ones((2, 12, 2, 2), dtype="float32")
    # ONE cell in ONE month of ONE year, not the whole non-spatial slice. A whole-slice
    # NaN makes `.all()` and `.any()` return the same mask, so the R5 mutation in Step 6
    # could not redden this test — measured, not assumed.
    a[0, 3, 0, 1] = np.nan
    phy = xr.Dataset(
        {"temp_c": (("year", "month", "latitude", "longitude"), a)},
        coords={"year": [2024, 2025], "month": _MONTHS, **_COORDS},
    )
    valid = compute_valid({"copernicus_phy": phy})
    assert valid.dims == ("latitude", "longitude")
    assert valid.shape == (2, 2)
    np.testing.assert_array_equal(valid.values, np.array([[True, False], [True, True]]))


def test_coverage_reduces_the_month_only_wave_shape_to_two():
    a = np.ones((12, 2, 2), dtype="float32")
    a[3, 1, 1] = np.nan  # absent in one month only
    wav = xr.Dataset(
        {"significant_wave_m": (("month", "latitude", "longitude"), a)},
        coords={"month": _MONTHS, **_COORDS},
    )
    valid = compute_valid({"copernicus_wav": wav})
    assert valid.dims == ("latitude", "longitude")
    # R5: `.all()`, not `.any()` — absent in one month is not coverage.
    np.testing.assert_array_equal(valid.values, np.array([[True, True], [True, False]]))


def test_the_light_layer_does_not_narrow_the_intersection():
    # `copernicus_bgc_light` is outside COVERAGE_LAYERS (R4): an all-NaN light layer
    # must leave `valid` untouched, or the manifest's four-layer attestation would
    # describe a five-layer intersection.
    phy = _static("temp_c", [[1.0, 1.0], [1.0, 1.0]])
    light = _static("light_attenuation_k", [[np.nan, np.nan], [np.nan, np.nan]])
    valid = compute_valid({"copernicus_phy": phy, "copernicus_bgc_light": light})
    assert valid.values.all()


def test_merge_carries_valid_with_the_right_values_and_dtype():
    phy = _static("temp_c", [[1.0, 2.0], [3.0, np.nan]])
    bathy = _static("depth_mean_m", [[5.0, 6.0], [7.0, 8.0]])
    merged = merge_layers({"copernicus_phy": phy, "emodnet_bathy": bathy})
    assert set(merged.data_vars) == {"temp_c", "depth_mean_m", "valid"}
    assert merged["valid"].dtype == np.dtype("bool")
    # Values, not just presence: otherwise merge could attach any mask and pass.
    np.testing.assert_array_equal(
        merged["valid"].values, np.array([[True, True], [True, False]])
    )


def test_merge_preserves_variable_attributes():
    # C§3.2 records CRS as a variable attribute. combine_attrs="drop" would strip it
    # and nothing downstream would notice until package D read the artifact.
    phy = _static("temp_c", [[1.0, 1.0], [1.0, 1.0]])
    phy["temp_c"].attrs["crs"] = "EPSG:4326"
    merged = merge_layers({"copernicus_phy": phy})
    assert merged["temp_c"].attrs["crs"] == "EPSG:4326"


def test_merge_tolerates_layers_with_different_dataset_attributes():
    # Real layers carry different DATASET-level attrs — EMODnet and CMEMS do not share
    # a `source`. combine_attrs="no_conflicts" raises MergeError on exactly that, which
    # would have made the first real refresh fail at the merge. Measured against this
    # environment's xarray, not assumed.
    phy = _static("temp_c", [[1.0, 1.0], [1.0, 1.0]])
    phy.attrs["source"] = "CMEMS"
    bathy = _static("depth_mean_m", [[1.0, 1.0], [1.0, 1.0]])
    bathy.attrs["source"] = "EMODnet"
    merged = merge_layers({"copernicus_phy": phy, "emodnet_bathy": bathy})
    assert set(merged.data_vars) == {"temp_c", "depth_mean_m", "valid"}


def test_compute_valid_refuses_when_no_coverage_layer_is_present():
    light = _static("light_attenuation_k", [[1.0, 1.0], [1.0, 1.0]])
    with pytest.raises(ValueError, match="no coverage layer was built"):
        compute_valid({"copernicus_bgc_light": light})


def test_compute_valid_refuses_a_layer_that_built_nothing():
    empty = xr.Dataset(coords=_COORDS)
    with pytest.raises(ValueError, match="built no variables"):
        compute_valid({"copernicus_phy": empty})


def test_compute_valid_refuses_a_variable_missing_a_spatial_dim():
    # Renaming SPATIAL_DIMS alone is not enough: a C-c layer emitting the short form
    # must be refused, not silently reduced to a scalar.
    bad = xr.Dataset(
        {"temp_c": (("lat", "lon"), np.ones((2, 2), dtype="float32"))},
        coords={"lat": _LAT, "lon": _LON},
    )
    with pytest.raises(ValueError, match="lacks the spatial dims"):
        compute_valid({"copernicus_phy": bad})
