# tests/test_refresh_driver.py
import pytest
from pydantic import ValidationError

pytest.importorskip("xarray")
import numpy as np  # noqa: E402
import xarray as xr  # noqa: E402
from refresh_fakes import FakeLayer  # noqa: E402

from seagarden_dst.artifact.pair import load_pair  # noqa: E402
from seagarden_dst.refresh.driver import (  # noqa: E402
    RefreshFailed,
    _declared_windows,
    check_grid,
    resolve_baselines,
    run_refresh,
)
from seagarden_dst.refresh.layer import YearRange  # noqa: E402

pytestmark = pytest.mark.spatial


def _yearly(name, years):
    return xr.Dataset(
        {name: (("year", "latitude"), np.ones((len(years), 2), dtype="float32"))},
        coords={"year": years, "latitude": [55.0, 55.5]},
    )


def test_resolve_baselines_takes_years_off_the_data_when_there_is_a_year_dim():
    ds = _yearly("temp_c", [2024, 2025])
    assert resolve_baselines(ds, {"temp_c": [2024, 2025]}) == {"temp_c": [2024, 2025]}


def test_a_declared_window_survives_a_variable_with_no_year_dimension():
    # THE trap (C§4.4, tests/test_refresh_manifest.py). `significant_wave_m` is a
    # monthly p95 over 2023-2025: no year dim, non-empty window. A dimensional rule
    # writes [] here and the manifest then contradicts the spec and the fixture.
    ds = xr.Dataset(
        {"significant_wave_m": (("month", "latitude"), np.ones((12, 2), dtype="float32"))},
        coords={"month": list(range(1, 13)), "latitude": [55.0, 55.5]},
    )
    resolved = resolve_baselines(ds, {"significant_wave_m": [2023, 2024, 2025]})
    assert resolved["significant_wave_m"] == [2023, 2024, 2025]


def test_a_static_field_keeps_its_empty_window():
    ds = xr.Dataset(
        {"depth_min_m": (("latitude",), np.ones(2, dtype="float32"))},
        coords={"latitude": [55.0, 55.5]},
    )
    resolved = resolve_baselines(ds, {"depth_min_m": []})
    assert "depth_min_m" in resolved  # present, not omitted — C§4.4 tells them apart
    assert resolved["depth_min_m"] == []


def test_a_declaration_disagreeing_with_the_data_is_refused():
    ds = _yearly("temp_c", [2024, 2025])
    with pytest.raises(RefreshFailed, match="declared baseline for 'temp_c'"):
        resolve_baselines(ds, {"temp_c": [2016, 2017]})


def test_an_undeclared_window_is_refused_rather_than_defaulted():
    ds = xr.Dataset(
        {"depth_min_m": (("latitude",), np.ones(2, dtype="float32"))},
        coords={"latitude": [55.0, 55.5]},
    )
    with pytest.raises(RefreshFailed, match="no layer declared a baseline window"):
        resolve_baselines(ds, {})


def test_one_failing_layer_fails_the_whole_refresh(tmp_path, small_grid):
    # C§6.1 row 1.
    layers = [
        FakeLayer("copernicus_phy", ["temp_c"]),
        FakeLayer("emodnet_bathy", ["depth_mean_m"], shape="static", fail_on_build=True),
    ]
    with pytest.raises(RefreshFailed, match="layer 'emodnet_bathy' failed to build"):
        run_refresh(
            layers,
            grid=small_grid,
            years=YearRange(start=2024, end=2024),
            target_dir=tmp_path / "out",
            workdir=tmp_path / "work",
        )


def test_a_failing_layer_writes_no_partial_artifact(tmp_path, small_grid):
    target = tmp_path / "out"
    layers = [
        FakeLayer("copernicus_phy", ["temp_c"]),
        FakeLayer("emodnet_bathy", ["depth_mean_m"], shape="static", fail_on_build=True),
    ]
    with pytest.raises(RefreshFailed):
        run_refresh(
            layers,
            grid=small_grid,
            years=YearRange(start=2024, end=2024),
            target_dir=target,
            workdir=tmp_path / "work",
        )
    assert not (target / "forcing.nc").exists()
    assert not (target / "manifest.json").exists()


def test_a_second_refresh_failing_leaves_the_first_pair_intact(
    tmp_path, small_grid, nine_variable_layers
):
    # C§6.1 row 2 as the DRIVER can reach it: nothing live is touched because the
    # failure happens before write_pair is called at all. (The os.replace window
    # between steps 5 and 6 is the writer's, and C-a proved it there.)
    target = tmp_path / "out"
    years = YearRange(start=2024, end=2024)
    run_refresh(
        nine_variable_layers, grid=small_grid, years=years,
        target_dir=target, workdir=tmp_path / "w1",
    )
    first, _ = load_pair(target)

    failing = [
        *nine_variable_layers[:-1],
        FakeLayer(
            "emodnet_bathy", ["depth_mean_m", "depth_min_m"],
            shape="static", fail_on_build=True,
        ),
    ]
    with pytest.raises(RefreshFailed):
        run_refresh(
            failing, grid=small_grid, years=years,
            target_dir=target, workdir=tmp_path / "w2",
        )

    second, artifact = load_pair(target)
    assert second.artifact_sha256 == first.artifact_sha256
    assert artifact.exists()


def test_a_successful_refresh_writes_a_loadable_pair(
    tmp_path, small_grid, nine_variable_layers
):
    # C§10 clause 1.
    target = tmp_path / "out"
    run_refresh(
        nine_variable_layers,
        grid=small_grid,
        years=YearRange(start=2024, end=2025),
        target_dir=target,
        workdir=tmp_path / "work",
    )
    manifest, artifact = load_pair(target)
    assert artifact.exists()
    assert set(manifest.variables) == {
        "salinity_psu", "temp_c", "din_umol_l", "dip_umol_l", "light_attenuation_k",
        "significant_wave_m", "depth_mean_m", "depth_min_m", "valid",
    }


def test_the_three_baseline_shapes_come_out_different(
    tmp_path, small_grid, nine_variable_layers
):
    # The driver-level twin of tests/test_refresh_manifest.py's wave-baseline test.
    # One assertion per shape, so the three-way divergence is pinned in one place:
    # a requested span, a fixed sub-window, and an empty one.
    target = tmp_path / "out"
    run_refresh(
        nine_variable_layers,
        grid=small_grid,
        years=YearRange(start=2024, end=2025),
        target_dir=target,
        workdir=tmp_path / "work",
    )
    manifest, _ = load_pair(target)
    assert manifest.baselines["temp_c"] == [2024, 2025]
    assert manifest.baselines["significant_wave_m"] == [2023, 2024, 2025]
    assert manifest.baselines["depth_mean_m"] == []


def test_the_requested_year_range_reaches_the_layers(
    tmp_path, small_grid, nine_variable_layers
):
    # R1 / clause 1: "for a NAMED year range". Without this, build() could ignore
    # `years` entirely and every other test would still pass.
    target = tmp_path / "out"
    run_refresh(
        nine_variable_layers,
        grid=small_grid,
        years=YearRange(start=2016, end=2018),
        target_dir=target,
        workdir=tmp_path / "work",
    )
    manifest, _ = load_pair(target)
    assert manifest.baselines["temp_c"] == [2016, 2017, 2018]
    # ...and the wave window is NOT the requested span, because C§3.2 fixes it.
    assert manifest.baselines["significant_wave_m"] == [2023, 2024, 2025]


def test_a_short_form_coordinate_layer_is_refused_before_anything_is_written(
    tmp_path, small_grid, nine_variable_layers
):
    # Proves MERGE's per-layer guard is reached from the driver and nothing is written.
    # This is NOT the R7 proof — see the next test for that.
    bad = FakeLayer(
        "copernicus_phy",
        ["salinity_psu", "temp_c"],
        data={
            "salinity_psu": (("lat", "lon"), np.ones((3, 3), dtype="float32")),
            "temp_c": (("lat", "lon"), np.ones((3, 3), dtype="float32")),
        },
    )
    target = tmp_path / "out"
    with pytest.raises(ValueError, match="lacks the spatial dims"):
        run_refresh(
            [bad, *nine_variable_layers[1:]],
            grid=small_grid,
            years=YearRange(start=2024, end=2024),
            target_dir=target,
            workdir=tmp_path / "work",
        )
    assert not (target / "forcing.nc").exists()


def test_a_transposed_variable_is_refused_before_anything_is_written(
    tmp_path, small_grid, nine_variable_layers
):
    # R7 proper. Both dims are spelled correctly, so merge_layers' per-layer guard
    # passes and `valid` still comes out (latitude, longitude). Only check_shapes can
    # see that THIS variable has them the wrong way round.
    bad = FakeLayer(
        "emodnet_bathy",
        ["depth_mean_m", "depth_min_m"],
        shape="static",
        data={
            "depth_mean_m": (("longitude", "latitude"), np.ones((3, 3), dtype="float32")),
            "depth_min_m": (("latitude", "longitude"), np.ones((3, 3), dtype="float32")),
        },
    )
    target = tmp_path / "out"
    with pytest.raises(ValueError, match="expected dims"):
        run_refresh(
            [*nine_variable_layers[:-1], bad],
            grid=small_grid,
            years=YearRange(start=2024, end=2024),
            target_dir=target,
            workdir=tmp_path / "work",
        )
    assert not (target / "forcing.nc").exists()


def test_two_layers_declaring_one_variable_are_refused():
    # C§5: one variable, one producing layer. Called directly rather than through
    # run_refresh: with the guard deleted, a two-layer set falls through to C§4.4's
    # claimed-exactly-once ValidationError at Manifest(...), so an end-to-end version
    # would go red with the wrong exception instead of DID NOT RAISE.
    # No build() needed: the guard fires on the variable NAME, and an unbuilt fake
    # declares an empty window for each variable it would produce.
    layers = [
        FakeLayer("copernicus_phy", ["temp_c"]),
        FakeLayer("copernicus_bgc", ["temp_c"]),
    ]
    with pytest.raises(RefreshFailed, match="two layers declared"):
        _declared_windows(layers)


def test_a_layer_set_on_the_wrong_grid_is_refused(tmp_path, small_grid):
    # Nothing else catches this. xr.merge(join="exact") only catches layers
    # disagreeing WITH EACH OTHER; check_shapes sees dim names and order;
    # check_declaration sees variable names. A layer set that agrees internally and is
    # uniformly wrong writes a manifest attesting an extent the artifact lacks — the
    # wave-baseline trap again, on the spatial axis.
    wrong = xr.Dataset(
        {"depth_mean_m": (("latitude", "longitude"), np.ones((2, 2), dtype="float32"))},
        coords={"latitude": [55.0, 55.5], "longitude": [20.0, 20.5]},
    )
    with pytest.raises(RefreshFailed, match="does not sit on the grid"):
        check_grid(wrong, small_grid)


def test_the_right_grid_passes_the_attestation_check(small_grid):
    ok = xr.Dataset(
        {
            "depth_mean_m": (
                ("latitude", "longitude"),
                np.ones((small_grid.n_lat, small_grid.n_lon), dtype="float32"),
            )
        },
        coords={"latitude": small_grid.lats(), "longitude": small_grid.lons()},
    )
    check_grid(ok, small_grid)


def test_a_partial_layer_set_cannot_produce_a_manifest(tmp_path, small_grid):
    # A driver that built one layer still declares all nine variables, so C§4.4's
    # claimed-exactly-once rule fires at manifest construction. The manifest refuses
    # to describe an artifact nobody built.
    layers = [FakeLayer("copernicus_phy", ["salinity_psu", "temp_c"])]
    with pytest.raises(ValidationError) as caught:
        run_refresh(
            layers,
            grid=small_grid,
            years=YearRange(start=2024, end=2024),
            target_dir=tmp_path / "out",
            workdir=tmp_path / "work",
        )
    assert "dip_umol_l" in str(caught.value)  # name the unclaimed, not merely "raised"
