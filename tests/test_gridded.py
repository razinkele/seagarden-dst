import pathlib

import pytest

pytest.importorskip("xarray")
import numpy as np  # noqa: E402

from seagarden_dst.forcing import Aggregation, Coverage, SiteQuery  # noqa: E402
from seagarden_dst.gridded import GriddedForcing  # noqa: E402

pytestmark = pytest.mark.spatial

FIXTURE = "tests/fixtures/data"


def _point(lat, lon):
    return f"POINT ({lon} {lat})"


@pytest.fixture
def reader():
    return GriddedForcing.from_directory(FIXTURE)


def test_a_valid_cell_returns_conditions(reader):
    # Cell [1,1] of the fixture is valid.
    lats, lons = reader.latitudes, reader.longitudes
    reading = reader.reading_at(SiteQuery(_point(lats[1], lons[1]), year=2024))
    assert reading.coverage is Coverage.VALID
    assert reading.conditions is not None
    assert reading.from_artifact is True
    assert reading.aggregation is Aggregation.CONTAINING_CELL


def test_an_invalid_cell_blocks_without_raising(reader):
    """The fixture's invalid cell holds FINITE values — `valid[0,0]` is False but the
    data there is `rng.random(...)`. A reader inferring validity from NaN returns
    conditions for it. This test fails for that reader and passes for one that reads
    the mask."""
    lats, lons = reader.latitudes, reader.longitudes
    reading = reader.reading_at(SiteQuery(_point(lats[0], lons[0]), year=2024))
    assert reading.coverage is Coverage.CELL_INVALID
    assert reading.conditions is None


def test_the_distance_to_the_nearest_valid_cell_is_reported(reader):
    """§6.2 requires it: at native resolution it is 0.75-1.28 km across all six regions,
    and it is the quantity a siting user can actually judge."""
    lats, lons = reader.latitudes, reader.longitudes
    reading = reader.reading_at(SiteQuery(_point(lats[0], lons[0]), year=2024))
    assert reading.nearest_valid_km is not None
    assert 0.0 < reading.nearest_valid_km < 10.0


def test_a_year_the_artifact_lacks_blocks_and_never_substitutes(reader):
    """§6.2/§7: never silently substitutes another year. The fixture carries 2024-2025."""
    lats, lons = reader.latitudes, reader.longitudes
    reading = reader.reading_at(SiteQuery(_point(lats[1], lons[1]), year=2019))
    assert reading.coverage is Coverage.YEAR_ABSENT
    assert reading.conditions is None
    assert reading.year == 2019


def test_a_land_cell_with_nan_blocks_rather_than_raising(tmp_path):
    """The committed fixture has no NaN, so this builds one. `SiteConditions` raises on
    a non-finite field, so a reader that constructs before checking coverage turns a
    real land cell into a ValueError where §7 requires a visible block."""
    import shutil

    import xarray as xr

    shutil.copytree(FIXTURE, tmp_path / "data")
    artifact = tmp_path / "data" / "forcing.nc"
    ds = xr.open_dataset(artifact, engine="h5netcdf").load()
    ds.close()
    for name in ("temp_c", "salinity_psu", "depth_mean_m"):
        ds[name].values[..., 0, 0] = np.float32("nan")
    ds.to_netcdf(artifact, engine="h5netcdf", mode="w")

    _restamp(tmp_path / "data")
    reader = GriddedForcing.from_directory(tmp_path / "data")
    lats, lons = reader.latitudes, reader.longitudes
    reading = reader.reading_at(SiteQuery(_point(lats[0], lons[0]), year=2024))
    assert reading.coverage is Coverage.CELL_INVALID
    assert reading.conditions is None


def test_the_reader_refuses_an_unrecognised_schema_version(tmp_path):
    """§7: refuse, fall back, say why — never read an artifact whose shape you do not
    know."""
    import json
    import shutil

    shutil.copytree(FIXTURE, tmp_path / "data")
    manifest_path = tmp_path / "data" / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["artifact_schema_version"] = 99
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    _restamp(tmp_path / "data")
    with pytest.raises(ValueError, match="artifact_schema_version"):
        GriddedForcing.from_directory(tmp_path / "data")


def _restamp(directory):
    """Recompute the manifest's sha after a test mutates the artifact.

    `load_pair(target_dir)` takes no opt-out: it refuses a torn pair on the sha256 that
    links artifact to manifest, which is package C-a's atomicity guarantee and not
    something a test should be able to switch off. So a test that edits the NetCDF
    restamps the manifest, exactly as `write_pair` does.
    """
    import json

    from seagarden_dst.artifact.pair import sha256_of

    directory = pathlib.Path(directory)
    manifest_path = directory / "manifest.json"
    artifact = directory / "forcing.nc"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["artifact_sha256"] = sha256_of(artifact)
    payload["artifact_bytes"] = artifact.stat().st_size
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")


def test_daily_forcing_comes_from_the_monthly_fields_not_a_sinusoid(reader):
    """§6.2: monthly fields REPLACE the sinusoid rather than feeding it."""
    lats, lons = reader.latitudes, reader.longitudes
    site = reader.reading_at(SiteQuery(_point(lats[1], lons[1]), year=2024)).conditions
    days, par, temp, din = reader.daily_forcing(site, (4, 9), 2024)
    assert len(days) == len(temp) == len(par) == len(din)
    assert np.isfinite(temp).all()


def test_two_years_give_different_series(reader):
    """The whole reason `daily_forcing` takes a year: collapsing years into one
    climatology costs -57% to +179% in final biomass (§6.2). One site per year, because
    a site carries the year it was read for (spec §3.6)."""
    lats, lons = reader.latitudes, reader.longitudes
    site_2024 = reader.reading_at(SiteQuery(_point(lats[1], lons[1]), year=2024)).conditions
    site_2025 = reader.reading_at(SiteQuery(_point(lats[1], lons[1]), year=2025)).conditions
    _, _, temp_2024, _ = reader.daily_forcing(site_2024, (4, 9), 2024)
    _, _, temp_2025, _ = reader.daily_forcing(site_2025, (4, 9), 2025)
    assert not np.allclose(temp_2024, temp_2025)


def test_a_replaced_conditions_object_still_finds_its_cell(reader):
    """Spec §2 / D§9 item 3. `eutropy_adapter` builds a *replaced* SiteConditions; the
    id()-keyed side table has never seen it and raises. Cells on the object survive
    `dataclasses.replace`."""
    from dataclasses import replace

    lats, lons = reader.latitudes, reader.longitudes
    site = reader.reading_at(SiteQuery(_point(lats[1], lons[1]), year=2024)).conditions
    forced = replace(site, din_umol_l=5.0, dip_umol_l=0.5)
    days, par, temp, din = reader.daily_forcing(forced, (4, 9), 2024)
    assert np.isfinite(din).all() and len(din) == len(days)


def test_a_plain_site_conditions_is_refused_by_daily_forcing(reader):
    """The refusal names what is needed, not an instance identity (spec §2)."""
    from dataclasses import fields

    from seagarden_dst.forcing import SiteConditions

    lats, lons = reader.latitudes, reader.longitudes
    site = reader.reading_at(SiteQuery(_point(lats[1], lons[1]), year=2024)).conditions
    plain = SiteConditions(**{f.name: getattr(site, f.name) for f in fields(SiteConditions)})
    with pytest.raises(ValueError, match="needs a GriddedConditions"):
        reader.daily_forcing(plain, (4, 9), 2024)


def test_a_site_read_for_one_year_refuses_a_series_for_another(reader):
    """Spec §3.6: rescaling 2025's field to 2024's annual mean would substitute a year."""
    lats, lons = reader.latitudes, reader.longitudes
    site = reader.reading_at(SiteQuery(_point(lats[1], lons[1]), year=2024)).conditions
    with pytest.raises(ValueError, match="same year"):
        reader.daily_forcing(site, (4, 9), 2025)


def test_a_wrapping_window_takes_january_from_the_following_year(reader):
    """§6.2's year boundary. A window that wraps past December must take January from
    Y+1, not from the same year's January twelve months earlier."""
    lats, lons = reader.latitudes, reader.longitudes
    site = reader.reading_at(SiteQuery(_point(lats[1], lons[1]), year=2024)).conditions
    _, _, wrapped, _ = reader.daily_forcing(site, (11, 2), 2024)
    assert np.isfinite(wrapped).all()


def test_a_wrapping_window_blocks_when_the_following_year_is_absent(reader):
    """The fixture carries 2024-2025, so a window wrapping out of 2025 has no Y+1."""
    lats, lons = reader.latitudes, reader.longitudes
    site = reader.reading_at(SiteQuery(_point(lats[1], lons[1]), year=2025)).conditions
    with pytest.raises(ValueError, match="wrapping window needs"):
        reader.daily_forcing(site, (11, 2), 2025)


def _open_fixture_dataset():
    import xarray as xr

    ds = xr.open_dataset(f"{FIXTURE}/forcing.nc", engine="h5netcdf").load()
    ds.close()
    return ds


def test_a_point_read_equals_the_direct_single_cell_computation(reader):
    """Spec §3.4: for one cell the cell-mean is the identity and the month reduction is
    today's call, so every field is EXACTLY what a direct float64 computation gives."""
    ds = _open_fixture_dataset()
    lats, lons = reader.latitudes, reader.longitudes
    reading = reader.reading_at(SiteQuery(_point(lats[1], lons[1]), year=2024))
    c = reading.conditions
    assert reading.aggregation is Aggregation.CONTAINING_CELL
    assert reading.valid_fraction is None
    assert c.cells == ((1, 1),) and c.year == 2024

    yi = list(int(y) for y in ds["year"].values).index(2024)

    def monthly(name):
        return np.asarray(ds[name].values[yi, :, 1, 1], dtype=float)

    assert c.salinity_psu == float(np.mean(monthly("salinity_psu")))
    assert c.mean_temp_c == float(np.mean(monthly("temp_c")))
    assert c.summer_temp_c == float(np.max(monthly("temp_c")))
    assert c.winter_temp_c == float(np.min(monthly("temp_c")))
    assert c.din_umol_l == float(np.mean(monthly("din_umol_l")))
    assert c.dip_umol_l == float(np.mean(monthly("dip_umol_l")))
    assert c.light_attenuation_k == float(np.mean(monthly("light_attenuation_k")))
    wave = np.asarray(ds["significant_wave_m"].values[:, 1, 1], dtype=float)
    assert c.significant_wave_m == float(np.mean(wave))
    assert c.depth_m == float(ds["depth_mean_m"].values[1, 1])


@pytest.mark.parametrize(
    "wkt",
    ["", "garbage", "POLYGON EMPTY", "MULTIPOLYGON (((20 54, 20.1 54, 20.1 54.1, 20 54)))"],
)
def test_unusable_geometry_raises_a_value_error_naming_the_wkt(reader, wkt):
    """Regression guard, not a discriminator: today's regex already raises. With
    shapely underneath, GEOSException is NOT a ValueError and POLYGON EMPTY parses,
    so this is what forces the wrapping (spec §3.1)."""
    with pytest.raises(ValueError, match="could not parse site geometry WKT"):
        reader.reading_at(SiteQuery(wkt, year=2024))
