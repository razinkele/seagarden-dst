"""The four Copernicus layers' transforms, claims and window rules (C§3.2, C§4.4)."""

from __future__ import annotations

import numpy as np
import pytest

from seagarden_dst.artifact.grid import GridSpec
from seagarden_dst.refresh.layer import YearRange

pytestmark = pytest.mark.spatial


def tiny_grid() -> GridSpec:
    return GridSpec(
        crs="EPSG:4326",
        lat_min=54.0, lat_max=54.05, lon_min=10.0, lon_max=10.09,
        lat_step=0.016666, lon_step=0.027777,
        n_lat=3, n_lon=3,
    )


def monthly_source(variables: dict[str, float], years: list[int]):
    """A monthly-frequency Dataset shaped like a CMEMS surface request."""
    import pandas as pd
    import xarray as xr

    times = pd.date_range(f"{years[0]}-01-01", f"{years[-1]}-12-01", freq="MS")
    grid = tiny_grid()
    return xr.Dataset(
        {
            name: (
                ("time", "latitude", "longitude"),
                np.full((len(times), 3, 3), value, dtype="float32"),
            )
            for name, value in variables.items()
        },
        coords={"time": times, "latitude": grid.lats(), "longitude": grid.lons()},
    )


def test_phy_emits_salinity_and_temperature_at_the_yearly_shape(tmp_path):
    from seagarden_dst.refresh.sources.phy import CopernicusPhy

    layer = CopernicusPhy(
        opener=lambda **kw: monthly_source({"so": 7.0, "thetao": 12.0}, [2024, 2025])
    )
    built = layer.build(tiny_grid(), YearRange(start=2024, end=2025), tmp_path)

    assert set(built.data_vars) == {"salinity_psu", "temp_c"}
    for name in built.data_vars:
        assert tuple(built[name].dims) == ("year", "month", "latitude", "longitude")
    assert float(built["salinity_psu"].isel(year=0, month=0, latitude=0, longitude=0)) == 7.0


def test_phy_claims_exactly_what_it_produces():
    from seagarden_dst.refresh.sources.phy import CopernicusPhy

    assert CopernicusPhy().provenance().variables == ["salinity_psu", "temp_c"]


def test_phy_baseline_window_is_the_requested_range(tmp_path):
    from seagarden_dst.refresh.sources.phy import CopernicusPhy

    layer = CopernicusPhy(
        opener=lambda **kw: monthly_source({"so": 7.0, "thetao": 12.0}, [2024, 2025])
    )
    layer.build(tiny_grid(), YearRange(start=2024, end=2025), tmp_path)

    assert layer.baseline_years() == {"salinity_psu": [2024, 2025], "temp_c": [2024, 2025]}


def test_phy_refuses_to_state_a_window_it_has_not_built():
    """R1: the ordering the driver happens to use is enforced, not assumed."""
    from seagarden_dst.refresh.sources.phy import CopernicusPhy

    with pytest.raises(RuntimeError, match="before build"):
        CopernicusPhy().baseline_years()


def test_phy_provenance_is_pending_with_a_source_url_and_an_unblocked_by():
    from seagarden_dst.refresh.sources.phy import CopernicusPhy

    archive = CopernicusPhy().provenance().archive
    assert archive.status == "pending"
    assert archive.source_url
    assert archive.unblocked_by


def test_bgc_sums_nitrate_and_ammonium_into_din(tmp_path):
    from seagarden_dst.refresh.sources.bgc import CopernicusBgc

    layer = CopernicusBgc(
        opener=lambda **kw: monthly_source({"no3": 4.0, "nh4": 1.5, "po4": 0.8}, [2024])
    )
    built = layer.build(tiny_grid(), YearRange(start=2024, end=2024), tmp_path)

    assert set(built.data_vars) == {"din_umol_l", "dip_umol_l"}
    assert float(built["din_umol_l"].isel(year=0, month=0, latitude=0, longitude=0)) == 5.5
    # approx, not ==: float32 0.8 reads back as 0.800000011920929. 5.5 and 7.0 are
    # exactly representable; 0.8 is not.
    assert float(
        built["dip_umol_l"].isel(year=0, month=0, latitude=0, longitude=0)
    ) == pytest.approx(0.8)


def test_bgc_claims_dip_only_because_din_is_claimed_by_a_derivation():
    """C§4.4: a computed field cannot also be claimed by a layer, or it is claimed twice."""
    from seagarden_dst.refresh.sources.bgc import CopernicusBgc

    assert CopernicusBgc().provenance().variables == ["dip_umol_l"]


def test_bgc_declares_a_window_for_both_variables_it_produces(tmp_path):
    """The driver resolves baselines over merged data_vars, not over claims."""
    from seagarden_dst.refresh.sources.bgc import CopernicusBgc

    layer = CopernicusBgc(
        opener=lambda **kw: monthly_source({"no3": 4.0, "nh4": 1.5, "po4": 0.8}, [2024])
    )
    layer.build(tiny_grid(), YearRange(start=2024, end=2024), tmp_path)

    assert layer.baseline_years() == {"din_umol_l": [2024], "dip_umol_l": [2024]}


def daily_zsd_source(values_by_day: list[float], year: int = 2024):
    """A daily-frequency zsd Dataset. `values_by_day` repeats to fill the year."""
    import pandas as pd
    import xarray as xr

    times = pd.date_range(f"{year}-01-01", f"{year}-12-31", freq="D")
    grid = tiny_grid()
    column = np.resize(np.asarray(values_by_day, dtype="float32"), len(times))
    data = np.repeat(np.repeat(column[:, None, None], 3, axis=1), 3, axis=2)
    return xr.Dataset(
        {"zsd": (("time", "latitude", "longitude"), data)},
        coords={"time": times, "latitude": grid.lats(), "longitude": grid.lons()},
    )


def test_light_averages_k_over_days_rather_than_inverting_the_monthly_mean(tmp_path):
    """C§3.4 and Jensen: mean(1.7/z) != 1.7/mean(z), and the difference is the bug.

    This test FAILS if the derivation is moved to the monthly product or reordered
    to 1.7/mean(z). With z alternating 2 and 8, the two routes differ by ~28%.
    """
    from seagarden_dst.refresh.sources.bgc_light import CopernicusBgcLight

    layer = CopernicusBgcLight(opener=lambda **kw: daily_zsd_source([2.0, 8.0]))
    built = layer.build(tiny_grid(), YearRange(start=2024, end=2024), tmp_path)

    computed = float(built["light_attenuation_k"].isel(year=0, month=0, latitude=0, longitude=0))

    # Derive both expectations from the ACTUAL January the source builder produced.
    # January has 31 days, so [2.0, 8.0] repeating gives 16 twos and 15 eights - NOT
    # a balanced pair. Hard-coding mean([1.7/2, 1.7/8]) = 0.53125 would be wrong by
    # 1.9% against a CORRECT implementation, and the obvious way to make that green
    # is to reorder the division - which is the bug this test exists to catch.
    january = np.resize(np.asarray([2.0, 8.0], dtype="float32"), 366)[:31]
    correct = float(np.mean(1.7 / january))     # 0.5415
    wrong = 1.7 / float(np.mean(january))       # 0.3467

    assert computed == pytest.approx(correct, rel=1e-4)
    assert computed != pytest.approx(wrong, rel=1e-2)


def test_light_emits_only_k_at_the_yearly_shape(tmp_path):
    from seagarden_dst.refresh.sources.bgc_light import CopernicusBgcLight

    layer = CopernicusBgcLight(opener=lambda **kw: daily_zsd_source([3.0]))
    built = layer.build(tiny_grid(), YearRange(start=2024, end=2024), tmp_path)

    assert set(built.data_vars) == {"light_attenuation_k"}
    assert tuple(built["light_attenuation_k"].dims) == ("year", "month", "latitude", "longitude")


def test_light_claims_nothing_at_all():
    """C§5: its only output is derived, so its `variables` is empty BY DESIGN."""
    from seagarden_dst.refresh.sources.bgc_light import CopernicusBgcLight

    assert CopernicusBgcLight().provenance().variables == []


def test_light_reads_the_daily_dataset_not_the_monthly_one():
    from seagarden_dst.refresh.sources.bgc_light import CopernicusBgcLight

    assert CopernicusBgcLight().provenance().dataset_id.endswith("P1D-m")
