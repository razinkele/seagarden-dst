"""The four Copernicus layers' transforms, claims and window rules (C§3.2, C§4.4)."""

from __future__ import annotations

from pathlib import Path

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


def test_bgc_refuses_to_state_a_window_it_has_not_built():
    """R1, for `copernicus_bgc`. Modelled on phy's — the guard is per-layer code.

    Before this existed, deleting the guard from all three yearly layers reddened
    exactly one test. A guard only two-thirds defended is a guard that can be
    removed from the other third without anything noticing.
    """
    from seagarden_dst.refresh.sources.bgc import CopernicusBgc

    with pytest.raises(RuntimeError, match="before build"):
        CopernicusBgc().baseline_years()


def test_light_refuses_to_state_a_window_it_has_not_built():
    """R1, for `copernicus_bgc_light`. See the note on the bgc case above."""
    from seagarden_dst.refresh.sources.bgc_light import CopernicusBgcLight

    with pytest.raises(RuntimeError, match="before build"):
        CopernicusBgcLight().baseline_years()


def test_phy_stays_lazy_when_handed_a_chunked_source():
    """R2's headline claim: the reduction never forces a compute.

    R2 exists so ~25.8 GB of hourly `VHM0` never lands on disk, and that rests
    entirely on the pipeline staying lazy end to end — `open_dataset` returns a
    dask-backed Dataset, and every transform between it and the writer must return
    one too. No test handed any layer a chunked array, so an `.compute()`, a
    `.values`, or any eager helper slipped into the chain would have been invisible
    here and fatal against the real product.

    `phy` rather than `wav`: it exercises `drop_depth` -> `to_yearly` (including the
    `reindex` that now lives there), which is the path three of the four layers take.
    """
    from seagarden_dst.refresh.sources.phy import CopernicusPhy

    chunked = monthly_source({"so": 7.0, "thetao": 12.0}, [2024, 2025]).chunk({"time": 12})
    assert chunked["so"].chunks is not None  # the fixture really is dask-backed

    built = CopernicusPhy(opener=lambda **kw: chunked).build(
        tiny_grid(), YearRange(start=2024, end=2025), Path("unused")
    )

    for name in built.data_vars:
        assert built[name].chunks is not None, (
            f"{name} came back as a materialised array: something in the chain "
            "forced a compute, which against the real hourly product means 25.8 GB "
            "in memory (R2)"
        )


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


WAVE_BASELINE = [2023, 2024, 2025]


def hourly_wave_source(values: list[float], year: int = 2024):
    """An hourly VHM0 Dataset over January only, to keep the test small."""
    import pandas as pd
    import xarray as xr

    times = pd.date_range(f"{year}-01-01", f"{year}-01-31 23:00", freq="h")
    grid = tiny_grid()
    column = np.resize(np.asarray(values, dtype="float32"), len(times))
    data = np.repeat(np.repeat(column[:, None, None], 3, axis=1), 3, axis=2)
    return xr.Dataset(
        {"VHM0": (("time", "latitude", "longitude"), data)},
        coords={"time": times, "latitude": grid.lats(), "longitude": grid.lons()},
    )


def test_wav_reduces_hourly_waves_to_a_monthly_p95(tmp_path):
    from seagarden_dst.refresh.sources.wav import CopernicusWav

    hours = list(np.linspace(0.0, 10.0, 100))
    layer = CopernicusWav(opener=lambda **kw: hourly_wave_source(hours))
    built = layer.build(tiny_grid(), YearRange(start=2024, end=2024), tmp_path)

    assert set(built.data_vars) == {"significant_wave_m"}
    assert tuple(built["significant_wave_m"].dims) == ("month", "latitude", "longitude")
    january = float(built["significant_wave_m"].isel(month=0, latitude=0, longitude=0))
    assert january == pytest.approx(np.quantile(np.resize(hours, 31 * 24), 0.95), rel=1e-3)


def test_wav_carries_no_quantile_coordinate_into_the_artifact(tmp_path):
    """groupby().quantile() leaves a scalar `quantile` coord that must not ship."""
    from seagarden_dst.refresh.sources.wav import CopernicusWav

    layer = CopernicusWav(opener=lambda **kw: hourly_wave_source([1.0, 2.0]))
    built = layer.build(tiny_grid(), YearRange(start=2024, end=2024), tmp_path)

    assert "quantile" not in built.coords
    assert "quantile" not in built["significant_wave_m"].coords


def test_wav_window_is_fixed_and_ignores_the_requested_range(tmp_path):
    """C§3.2 fixes the p95 window at 2023-2025; R2 is the case this was written for."""
    from seagarden_dst.refresh.sources.wav import CopernicusWav

    layer = CopernicusWav(opener=lambda **kw: hourly_wave_source([1.0, 2.0]))
    layer.build(tiny_grid(), YearRange(start=2016, end=2025), tmp_path)

    assert layer.baseline_years() == {"significant_wave_m": WAVE_BASELINE}


def test_wav_asks_for_its_own_window_not_the_requested_one(tmp_path):
    """Both ends of the fixed window, against a requested range sharing NEITHER.

    The requested range is 2016-2022 on purpose. An earlier version asked for
    2016-2025, which shares its END year with the fixed 2023-2025 window — so the
    `end_datetime` assertion passed even for a layer that simply echoed `years.end`,
    and only the start assertion discriminated. With 2022 as the requested end, both
    assertions fail against an echoing implementation.
    """
    from seagarden_dst.refresh.sources.wav import CopernicusWav

    seen: dict[str, object] = {}

    def fake_opener(**kwargs: object):
        seen.update(kwargs)
        return hourly_wave_source([1.0, 2.0])

    CopernicusWav(opener=fake_opener).build(
        tiny_grid(), YearRange(start=2016, end=2022), tmp_path
    )

    assert seen["start_datetime"].startswith("2023-01-01")
    assert seen["end_datetime"].startswith("2025-12-31")
    assert "minimum_depth" not in seen  # the wave product is 2-D


def test_wav_can_state_its_window_before_any_build():
    """The positive half of the wav ruling: no R1 guard, because none is needed.

    `wav.py` argues that it has no pre-`build()` guard because its window is a
    constant of the design rather than a function of the request. Nothing proved
    the claim's operative half — that calling `baseline_years()` on a fresh instance
    actually SUCCEEDS. A guard added here "for symmetry" with the three yearly
    layers would redden this test, which is precisely the point.
    """
    from seagarden_dst.refresh.sources.wav import CopernicusWav

    assert CopernicusWav().baseline_years() == {"significant_wave_m": WAVE_BASELINE}


def test_wav_claims_the_variable_it_produces():
    from seagarden_dst.refresh.sources.wav import CopernicusWav

    assert CopernicusWav().provenance().variables == ["significant_wave_m"]


def test_wav_reduces_month_by_month_in_latitude_bands_when_the_source_is_lazy(
    tmp_path, monkeypatch
):
    """Run 2 of the first real refresh (2026-09-24) was OOM-killed at 30.7 GB resident:
    the layer rechunked the 25.9 GB hourly source to ONE chunk before the quantile.
    Month by month, in latitude bands, the numbers are the same and no chunk is ever
    the whole array. The product's own chunking is 200 hours over the full extent."""
    from seagarden_dst.refresh.sources import wav
    from seagarden_dst.refresh.sources.wav import CopernicusWav

    monkeypatch.setattr(wav, "LATITUDE_BAND_ROWS", 2)
    hours = list(np.linspace(0.0, 10.0, 100))
    eager_source = hourly_wave_source(hours)
    lazy_source = eager_source.chunk({"time": 200, "latitude": -1, "longitude": -1})

    lazy = CopernicusWav(opener=lambda **kw: lazy_source).build(
        tiny_grid(), YearRange(start=2024, end=2024), tmp_path
    )["significant_wave_m"]
    eager = CopernicusWav(opener=lambda **kw: eager_source).build(
        tiny_grid(), YearRange(start=2024, end=2024), tmp_path
    )["significant_wave_m"]

    assert lazy.chunks is not None, "the writer computes it chunk by chunk; not loaded here"
    assert max(lazy.chunks[lazy.dims.index("latitude")]) <= 2
    assert tuple(lazy.dims) == ("month", "latitude", "longitude")
    np.testing.assert_allclose(lazy.values, eager.values)
