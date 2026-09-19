"""EMODnet Bathymetry: reduction, tiling, probe and build (C§13)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from seagarden_dst.artifact.grid import GridSpec


def tiny_grid() -> GridSpec:
    """Three cells by two, on the real steps, so the lon step is NOT a whole number of
    pixels (C§13.3)."""
    return GridSpec(
        crs="EPSG:4326",
        lat_min=55.0, lat_max=55.05, lon_min=21.0, lon_max=21.0555,
        lat_step=0.016666, lon_step=0.027777, n_lat=3, n_lon=2,
    )


# --- GridAccumulator: C§13.3 ------------------------------------------------------


def test_depth_is_minus_elevation_averaged_over_wet_pixels():
    from seagarden_dst.refresh.sources.emodnet import GridAccumulator

    grid = tiny_grid()
    acc = GridAccumulator(grid)
    # Two pixels, both inside cell (0, 0): -10 m and -20 m.
    elevation = np.array([[-10.0, -20.0]])
    acc.add(elevation, pixel_lats=np.array([55.001]), pixel_lons=np.array([21.001, 21.010]))
    mean, minimum = acc.finish()
    assert mean[0, 0] == pytest.approx(15.0)
    assert minimum[0, 0] == pytest.approx(10.0), "depth_min is the SHALLOWEST wet depth"


def test_land_and_nan_pixels_are_not_wet_and_do_not_count():
    from seagarden_dst.refresh.sources.emodnet import GridAccumulator

    acc = GridAccumulator(tiny_grid())
    elevation = np.array([[-8.0, 0.0, 3.5, np.nan]])
    acc.add(elevation, np.array([55.001]), np.array([21.001, 21.002, 21.003, 21.004]))
    mean, minimum = acc.finish()
    assert mean[0, 0] == pytest.approx(8.0)
    assert minimum[0, 0] == pytest.approx(8.0)


def test_a_cell_with_no_wet_pixel_is_nan_so_valid_will_refuse_it():
    from seagarden_dst.refresh.sources.emodnet import GridAccumulator

    acc = GridAccumulator(tiny_grid())
    acc.add(np.array([[2.0, 0.0]]), np.array([55.001]), np.array([21.001, 21.002]))
    mean, minimum = acc.finish()
    assert np.isnan(mean[0, 0]) and np.isnan(minimum[0, 0])
    assert np.isnan(mean).all(), "untouched cells are NaN, not zero"


def test_pixels_bin_by_the_cell_containing_their_centre_with_lower_edge_coordinates():
    from seagarden_dst.refresh.sources.emodnet import GridAccumulator

    grid = tiny_grid()
    acc = GridAccumulator(grid)
    # One pixel per cell, placed just above each lower edge; lon step is 26.67 px so a
    # block reshape would misplace these, centre-binning must not.
    lats = grid.lats() + 0.0005
    lons = grid.lons() + 0.0005
    elevation = -np.arange(1, 7, dtype=float).reshape(3, 2)  # -1 .. -6
    acc.add(elevation, lats, lons)
    mean, _ = acc.finish()
    np.testing.assert_allclose(mean, np.arange(1, 7, dtype=float).reshape(3, 2))


def test_pixels_outside_the_grid_extent_are_dropped():
    from seagarden_dst.refresh.sources.emodnet import GridAccumulator

    grid = tiny_grid()
    acc = GridAccumulator(grid)
    lats = np.array([54.99, 55.001, 55.06])       # below, inside, above
    lons = np.array([20.99, 21.001, 21.06])       # left, inside, right
    acc.add(np.full((3, 3), -5.0), lats, lons)
    mean, _ = acc.finish()
    assert mean[0, 0] == pytest.approx(5.0)
    assert np.isnan(np.delete(mean.ravel(), 0)).all()


def test_accumulation_across_tiles_is_the_same_as_one_array():
    from seagarden_dst.refresh.sources.emodnet import GridAccumulator

    grid = tiny_grid()
    lats = np.array([55.001, 55.002])
    lons = np.array([21.001, 21.002])
    whole = GridAccumulator(grid)
    whole.add(np.array([[-1.0, -2.0], [-3.0, -4.0]]), lats, lons)
    split = GridAccumulator(grid)
    split.add(np.array([[-1.0, -2.0]]), lats[:1], lons)
    split.add(np.array([[-3.0, -4.0]]), lats[1:], lons)
    for a, b in zip(whole.finish(), split.finish(), strict=True):
        np.testing.assert_allclose(a, b, equal_nan=True)


# --- Tiles and fetching: C§13.4 -------------------------------------------------------


def test_the_baltic_extent_is_126_whole_degree_tiles():
    from seagarden_dst.refresh.sources.emodnet import Tile, tiles_for

    tiles = tiles_for(GridSpec.baltic())
    assert len(tiles) == 7 * 18
    assert tiles[0] == Tile(lat0=53.0, lat1=54.0, lon0=9.0, lon1=10.0)
    assert tiles[-1] == Tile(lat0=59.0, lat1=60.0, lon0=26.0, lon1=27.0)


def test_a_tile_request_pins_the_dated_coverage_and_asks_for_geotiff():
    from seagarden_dst.refresh.sources.emodnet import COVERAGE_ID, Tile, wcs_url

    url = wcs_url(Tile(55.0, 56.0, 20.0, 21.0))
    assert COVERAGE_ID == "emodnet__mean_2022"
    assert f"COVERAGEID={COVERAGE_ID}" in url
    assert "SUBSET=Lat(55.0,56.0)" in url and "SUBSET=Long(20.0,21.0)" in url
    assert "FORMAT=image/tiff" in url
    assert "emodnet__mean&" not in url, "the undated alias drifts silently (C§13.1)"


def test_fetch_tiles_skips_tiles_already_on_disk(tmp_path):
    from seagarden_dst.refresh.sources.emodnet import Tile, fetch_tiles, tile_path

    tiles = [Tile(55.0, 56.0, 20.0, 21.0), Tile(55.0, 56.0, 21.0, 22.0)]
    tile_path(tmp_path, tiles[0]).parent.mkdir(parents=True)
    tile_path(tmp_path, tiles[0]).write_bytes(b"cached")
    fetched: list[str] = []

    def fake_fetcher(url: str, destination: Path) -> None:
        fetched.append(url)
        destination.write_bytes(b"new")

    paths = fetch_tiles(tiles, tmp_path, fake_fetcher)
    assert len(fetched) == 1 and "Long(21.0,22.0)" in fetched[0]
    assert [p.read_bytes() for p in paths] == [b"cached", b"new"]


def test_a_tile_the_fetcher_cannot_deliver_aborts_the_build(tmp_path):
    from seagarden_dst.refresh.sources.emodnet import Tile, TileFetchFailed, fetch_tiles

    def dead(url: str, destination: Path) -> None:
        raise OSError("connection reset")

    with pytest.raises(TileFetchFailed, match="Long\\(20.0,21.0\\)"):
        fetch_tiles([Tile(55.0, 56.0, 20.0, 21.0)], tmp_path, dead)


@pytest.mark.spatial
def test_read_tile_returns_elevation_and_pixel_centres(tmp_path):
    import rasterio
    from rasterio.transform import from_origin

    from seagarden_dst.refresh.sources.emodnet import read_tile

    # 4 x 4 pixels of 0.25 deg over 55-56 N, 20-21 E, row 0 at the TOP (north).
    data = np.arange(16, dtype="float32").reshape(4, 4) - 20.0
    path = tmp_path / "t.tif"
    with rasterio.open(
        path, "w", driver="GTiff", height=4, width=4, count=1, dtype="float32",
        crs="EPSG:4326", transform=from_origin(20.0, 56.0, 0.25, 0.25),
    ) as dst:
        dst.write(data, 1)

    elevation, lats, lons = read_tile(path)
    np.testing.assert_array_equal(elevation, data)
    np.testing.assert_allclose(lats, [55.875, 55.625, 55.375, 55.125])
    np.testing.assert_allclose(lons, [20.125, 20.375, 20.625, 20.875])


# --- Probe: C§13.4 --------------------------------------------------------------------

_CAPS = b"""<?xml version="1.0"?>
<wcs:Capabilities xmlns:wcs="http://www.opengis.net/wcs/2.0">
  <wcs:Contents>
    <wcs:CoverageSummary><wcs:CoverageId>emodnet__mean</wcs:CoverageId></wcs:CoverageSummary>
    <wcs:CoverageSummary><wcs:CoverageId>emodnet__mean_2022</wcs:CoverageId></wcs:CoverageSummary>
  </wcs:Contents>
</wcs:Capabilities>"""


def test_coverage_ids_are_read_regardless_of_namespace_prefix():
    from seagarden_dst.refresh.sources.emodnet import coverage_ids

    assert coverage_ids(_CAPS) == {"emodnet__mean", "emodnet__mean_2022"}


def test_the_probe_is_ok_when_the_dated_coverage_is_listed():
    from seagarden_dst.refresh.sources.emodnet import probe_coverage

    result = probe_coverage("emodnet_bathy", capabilities=lambda: _CAPS)
    assert result.status == "ok" and result.reachable is True


def test_the_probe_reports_absent_when_the_service_answers_without_the_coverage():
    from seagarden_dst.refresh.sources.emodnet import probe_coverage

    gone = _CAPS.replace(b"emodnet__mean_2022", b"emodnet__mean_2024")
    result = probe_coverage("emodnet_bathy", capabilities=lambda: gone)
    assert result.status == "absent" and result.reachable is False
    assert "emodnet__mean_2022" in result.detail


def test_the_probe_reports_unreachable_on_a_transport_failure():
    from seagarden_dst.refresh.sources.emodnet import probe_coverage

    def dead() -> bytes:
        raise OSError("name resolution failed")

    result = probe_coverage("emodnet_bathy", capabilities=dead)
    assert result.status == "unreachable" and result.reachable is False
    assert "name resolution failed" in result.detail


def test_gzipped_capabilities_are_decompressed():
    """The live server gzips XML without being asked (C§13.1)."""
    import gzip

    from seagarden_dst.refresh.sources.emodnet import _decode_body

    assert _decode_body(gzip.compress(_CAPS), "gzip") == _CAPS
    assert _decode_body(_CAPS, None) == _CAPS


# --- Fix review findings: nodata, tile-body validation, exceptions, size cap --------


@pytest.mark.spatial
def test_read_tile_maps_the_nodata_sentinel_to_nan(tmp_path):
    import rasterio
    from rasterio.transform import from_origin

    from seagarden_dst.refresh.sources.emodnet import read_tile

    data = np.array(
        [[-1.0, -2.0], [-9999.0, -4.0]],
        dtype="float32",
    )
    path = tmp_path / "nodata.tif"
    with rasterio.open(
        path, "w", driver="GTiff", height=2, width=2, count=1, dtype="float32",
        crs="EPSG:4326", transform=from_origin(20.0, 56.0, 0.5, 0.5),
        nodata=-9999.0,
    ) as dst:
        dst.write(data, 1)

    elevation, _, _ = read_tile(path)
    assert np.isnan(elevation[1, 0])
    np.testing.assert_allclose(elevation[0, 0], -1.0)
    np.testing.assert_allclose(elevation[0, 1], -2.0)
    np.testing.assert_allclose(elevation[1, 1], -4.0)


def test_is_tiff_recognises_the_two_tiff_magic_numbers_and_rejects_others(tmp_path):
    from seagarden_dst.refresh.sources.emodnet import _is_tiff

    little = tmp_path / "little.tif"
    little.write_bytes(b"II*\x00rest-of-file")
    assert _is_tiff(little) is True

    big = tmp_path / "big.tif"
    big.write_bytes(b"MM\x00*rest-of-file")
    assert _is_tiff(big) is True

    xml_body = tmp_path / "body.part"
    xml_body.write_bytes(b"<?xml version='1.0'?><ows:ExceptionReport/>")
    assert _is_tiff(xml_body) is False


def test_finish_download_renames_a_tiff_partial_into_place(tmp_path):
    from seagarden_dst.refresh.sources.emodnet import _finish_download

    partial = tmp_path / "t.part"
    partial.write_bytes(b"II*\x00rest-of-tiff-bytes")
    destination = tmp_path / "t.tif"

    _finish_download("http://example.test/wcs", partial, destination)

    assert destination.read_bytes() == b"II*\x00rest-of-tiff-bytes"
    assert not partial.exists()


def test_finish_download_rejects_a_non_tiff_body_and_cleans_up(tmp_path):
    from seagarden_dst.refresh.sources.emodnet import _finish_download

    partial = tmp_path / "t.part"
    partial.write_bytes(b"<ows:ExceptionReport/>")
    destination = tmp_path / "t.tif"

    with pytest.raises(OSError, match="non-TIFF"):
        _finish_download("http://example.test/wcs", partial, destination)

    assert not destination.exists()
    assert not partial.exists()


def test_fetch_tiles_retries_and_aborts_on_an_incomplete_read(tmp_path):
    import http.client

    from seagarden_dst.refresh.sources.emodnet import Tile, TileFetchFailed, fetch_tiles

    def dead(url: str, destination: Path) -> None:
        raise http.client.IncompleteRead(b"")

    with pytest.raises(TileFetchFailed, match="Long\\(20.0,21.0\\)"):
        fetch_tiles([Tile(55.0, 56.0, 20.0, 21.0)], tmp_path, dead)


def test_the_probe_reports_unreachable_on_an_incomplete_read():
    import http.client

    from seagarden_dst.refresh.sources.emodnet import probe_coverage

    def dead() -> bytes:
        raise http.client.IncompleteRead(b"")

    result = probe_coverage("emodnet_bathy", capabilities=dead)
    assert result.status == "unreachable" and result.reachable is False


def test_check_size_passes_small_bodies_through_and_rejects_oversized_ones():
    from seagarden_dst.refresh.sources.emodnet import _MAX_CAPABILITIES_BYTES, _check_size

    small = b"x" * 10
    assert _check_size(small) == small

    oversized = b"x" * (_MAX_CAPABILITIES_BYTES + 1)
    with pytest.raises(OSError, match="exceeded"):
        _check_size(oversized)
