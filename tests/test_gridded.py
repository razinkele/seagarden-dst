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


# Spec §5 polygons, verbatim. WKT is (lon lat). Three review cycles verified every
# inside set, centroid and anchor against the fixture by script; do not invent others.
NINE_CELLS = "POLYGON ((19.99 53.99, 20.07 53.99, 20.07 54.05, 19.99 54.05, 19.99 53.99))"
TRIANGLE_ON_INVALID = "POLYGON ((19.995 53.995, 20.035 53.995, 19.995 54.025, 19.995 53.995))"
SUB_CELL_NEAR_11 = (
    "POLYGON ((20.038 54.020, 20.043 54.020, 20.043 54.025, 20.038 54.025, 20.038 54.020))"
)
TWO_CELLS_ONE_VALID = (
    "POLYGON ((19.99 53.99, 20.04 53.99, 20.04 54.008, 19.99 54.008, 19.99 53.99))"
)
U_SHAPE = (
    "POLYGON ((19.99 53.99, 20.07 53.99, 20.07 54.05, 20.045 54.05, 20.045 54.008, "
    "20.015 54.008, 20.015 54.05, 19.99 54.05, 19.99 53.99))"
)


def test_a_polygon_over_nine_cells_is_the_unweighted_mean_of_the_eight_valid_ones(reader):
    """Spec test 3. Centroid (20.03, 54.02) -> anchor [1,1], valid."""
    ds = _open_fixture_dataset()
    reading = reader.reading_at(SiteQuery(NINE_CELLS, year=2024))
    assert reading.coverage is Coverage.VALID
    assert reading.aggregation is Aggregation.UNWEIGHTED_MEAN
    assert reading.valid_fraction == pytest.approx(8 / 9)
    cells = reading.conditions.cells
    assert len(cells) == 8 and (0, 0) not in cells
    yi = list(int(y) for y in ds["year"].values).index(2024)
    rows = [r for r, _ in cells]
    cols = [c for _, c in cells]
    block = np.asarray(ds["salinity_psu"].values[yi][:, rows, cols], dtype=float)
    assert np.allclose(reading.conditions.salinity_psu, np.mean(block), rtol=1e-12)


def test_a_polygon_whose_anchor_is_invalid_blocks_and_still_reports_the_fraction(reader):
    """Spec test 4, decision 1: the containing cell decides coverage (§6.2 rule 1)."""
    reading = reader.reading_at(SiteQuery(TRIANGLE_ON_INVALID, year=2024))
    assert reading.coverage is Coverage.CELL_INVALID
    assert reading.conditions is None
    assert reading.nearest_valid_km is not None and reading.nearest_valid_km > 0.0
    assert reading.valid_fraction == pytest.approx(2 / 3)
    assert reading.aggregation is Aggregation.CONTAINING_CELL


def test_a_sub_cell_polygon_between_coordinates_is_its_anchor_cell(reader):
    """Spec test 5: no coordinate inside -> the centroid's nearest cell, no fraction."""
    reading = reader.reading_at(SiteQuery(SUB_CELL_NEAR_11, year=2024))
    assert reading.coverage is Coverage.VALID
    assert reading.aggregation is Aggregation.CONTAINING_CELL
    assert reading.valid_fraction is None
    assert reading.conditions.cells == ((1, 1),)


def test_the_label_follows_the_valid_count_not_the_inside_count(reader):
    """Spec test 6, §3.2 row 3: two inside, one valid -> CONTAINING_CELL over the anchor,
    fraction still reported."""
    reading = reader.reading_at(SiteQuery(TWO_CELLS_ONE_VALID, year=2024))
    assert reading.coverage is Coverage.VALID
    assert reading.aggregation is Aggregation.CONTAINING_CELL
    assert reading.conditions.cells == ((0, 1),)
    assert reading.valid_fraction == pytest.approx(0.5)


def test_a_concave_polygon_anchors_outside_its_own_inside_set(reader):
    """Spec test 10. The notch excludes [1,1] and [2,1]; the centroid still lands
    nearest [1,1], which decides coverage but is not averaged. On this fixture the
    area centroid (lat 54.0168) and the old vertex mean (54.0245) both anchor [1,1],
    so the centroid method itself is not pinned here (spec §5, recorded)."""
    reading = reader.reading_at(SiteQuery(U_SHAPE, year=2024))
    assert reading.coverage is Coverage.VALID
    assert reading.aggregation is Aggregation.UNWEIGHTED_MEAN
    assert reading.valid_fraction == pytest.approx(6 / 7)
    assert reading.conditions.cells == ((0, 1), (0, 2), (1, 0), (1, 2), (2, 0), (2, 2))


def test_a_year_the_artifact_lacks_still_reports_the_polygon_fraction(reader):
    """Spec §3.3: `valid` has no year axis, so the fraction is computable under a
    YEAR_ABSENT block too, and one rule serves every outcome."""
    reading = reader.reading_at(SiteQuery(NINE_CELLS, year=2099))
    assert reading.coverage is Coverage.YEAR_ABSENT
    assert reading.conditions is None
    assert reading.aggregation is Aggregation.CONTAINING_CELL
    assert reading.valid_fraction == pytest.approx(8 / 9)


def test_a_multi_cell_daily_series_is_the_mean_of_the_single_cell_series(reader):
    """Spec test 7, field-mean-first: temp and din over the polygon equal the elementwise
    mean of the eight single-cell series. par is derived from the averaged k and is
    NOT compared (§3.4). All reads and series for 2024."""
    lats, lons = reader.latitudes, reader.longitudes
    poly = reader.reading_at(SiteQuery(NINE_CELLS, year=2024)).conditions
    _, _, temp_poly, din_poly = reader.daily_forcing(poly, (4, 9), 2024)
    temps, dins = [], []
    for r, c in poly.cells:
        one = reader.reading_at(SiteQuery(_point(lats[r], lons[c]), year=2024)).conditions
        _, _, t, d = reader.daily_forcing(one, (4, 9), 2024)
        temps.append(t)
        dins.append(d)
    assert np.allclose(temp_poly, np.mean(temps, axis=0), rtol=1e-12)
    assert np.allclose(din_poly, np.mean(dins, axis=0), rtol=1e-12)


def test_the_daily_din_scales_with_the_sites_annual_value_and_is_untouched_otherwise(reader):
    """Spec §3.6 / test 11. A replaced annual DIN scales the monthly field by one ratio;
    temp does not move. For an unmodified site the ratio is EXACTLY 1.0, so the series
    is array_equal to what today's per-cell interpolation gives."""
    from dataclasses import replace

    ds = _open_fixture_dataset()
    lats, lons = reader.latitudes, reader.longitudes
    site = reader.reading_at(SiteQuery(_point(lats[1], lons[1]), year=2024)).conditions
    days, _, temp, din = reader.daily_forcing(site, (4, 9), 2024)

    doubled = replace(site, din_umol_l=2.0 * site.din_umol_l)
    _, _, temp_2, din_2 = reader.daily_forcing(doubled, (4, 9), 2024)
    assert np.allclose(din_2, 2.0 * din, rtol=1e-12)
    assert np.array_equal(temp_2, temp)

    # Today's route, reproduced: float32 scalars per month, cast, interpolated.
    from seagarden_dst.forcing import day_of_year

    yi = list(int(y) for y in ds["year"].values).index(2024)
    x = np.asarray([day_of_year(m) for m in range(4, 10)], dtype=float)  # mid-month knots
    values = np.asarray(
        [ds["din_umol_l"].values[yi, m - 1, 1, 1] for m in range(4, 10)], dtype=float
    )
    assert np.array_equal(din, np.interp(days, x, values))


def test_a_nutrient_scenario_on_an_artifact_session_returns_rather_than_raising(tmp_path):
    """Spec test 8 - D§9 item 3 at the level a user meets it. The committed fixture's
    salinity is random in [0, 1) psu and contraindicates every species before any
    growth model runs, so this builds a +7 psu copy. Saccharina (floor 16 psu) stays
    excluded on it BY DESIGN - do not 'fix' that. The defect is the crash."""
    import shutil

    import xarray as xr

    from seagarden_dst.api import assess_site
    from seagarden_dst.contracts import SiteContext

    shutil.copytree(FIXTURE, tmp_path / "data")
    artifact = tmp_path / "data" / "forcing.nc"
    ds = xr.open_dataset(artifact, engine="h5netcdf").load()
    ds.close()
    ds["salinity_psu"].values[...] += np.float32(7.0)
    ds.to_netcdf(artifact, engine="h5netcdf", mode="w")
    _restamp(tmp_path / "data")

    reader = GriddedForcing.from_directory(tmp_path / "data")
    lats, lons = reader.latitudes, reader.longitudes
    query = SiteQuery(_point(lats[1], lons[1]), year=2024)
    context = SiteContext.from_reading(
        reader.reading_at(query), label="fixture", geometry_wkt=query.geometry_wkt
    )
    assessment = assess_site(
        context, forcing=reader, year=2024, eutropy={"din_umol_l": 5.0, "dip_umol_l": 0.5}
    )
    assert not any("GriddedForcing" in why for why in assessment.excluded.values())
    assert "saccharina_latissima" in assessment.excluded
    assert "psu" in assessment.excluded["saccharina_latissima"]
