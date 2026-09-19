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
    climatology costs -57% to +179% in final biomass (§6.2)."""
    lats, lons = reader.latitudes, reader.longitudes
    site = reader.reading_at(SiteQuery(_point(lats[1], lons[1]), year=2024)).conditions
    _, _, temp_2024, _ = reader.daily_forcing(site, (4, 9), 2024)
    _, _, temp_2025, _ = reader.daily_forcing(site, (4, 9), 2025)
    assert not np.allclose(temp_2024, temp_2025)


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
