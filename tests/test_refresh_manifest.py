import pytest

from seagarden_dst.refresh.grid import GridSpec


def test_baltic_grid_matches_the_shipped_extent():
    """C§3.1: 53.5-60.0 N, 9.5-27.0 E on the Copernicus native grid."""
    g = GridSpec.baltic()
    assert (g.lat_min, g.lat_max) == (53.5, 60.0)
    assert (g.lon_min, g.lon_max) == (9.5, 27.0)
    assert g.crs == "EPSG:4326"
    assert (g.n_lat, g.n_lon) == (390, 630)
    assert len(g.lats()) == 390
    assert len(g.lons()) == 630


def test_grid_rejects_an_inverted_extent():
    """A max below its min is a typo that would otherwise yield an empty grid."""
    with pytest.raises(ValueError):
        GridSpec(
            crs="EPSG:4326", lat_min=60.0, lat_max=53.5, lon_min=9.5, lon_max=27.0,
            lat_step=0.016666, lon_step=0.027777, n_lat=390, n_lon=630,
        )
