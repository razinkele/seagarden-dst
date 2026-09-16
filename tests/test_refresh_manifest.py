from datetime import UTC, datetime

import numpy as np
import pytest
from pydantic import ValidationError

from seagarden_dst.refresh.grid import GridSpec
from seagarden_dst.refresh.manifest import Archive, LayerProvenance


def test_baltic_grid_matches_the_shipped_extent():
    """C§3.1: 53.5-60.0 N, 9.5-27.0 E on the Copernicus native grid."""
    g = GridSpec.baltic()
    assert (g.lat_min, g.lat_max) == (53.5, 60.0)
    assert (g.lon_min, g.lon_max) == (9.5, 27.0)
    assert g.crs == "EPSG:4326"
    assert (g.n_lat, g.n_lon) == (390, 630)

    # Check array lengths
    lats = g.lats()
    lons = g.lons()
    assert len(lats) == 390
    assert len(lons) == 630

    # Check array values: first element, stepping, and constant difference
    assert lats[0] == g.lat_min
    assert lons[0] == g.lon_min
    lat_diffs = np.diff(lats)
    lon_diffs = np.diff(lons)
    assert np.allclose(lat_diffs, g.lat_step)
    assert np.allclose(lon_diffs, g.lon_step)


def test_grid_rejects_lat_inverted():
    """Latitude max below min is a typo."""
    with pytest.raises(ValueError):
        GridSpec(
            crs="EPSG:4326", lat_min=60.0, lat_max=53.5, lon_min=9.5, lon_max=27.0,
            lat_step=0.016666, lon_step=0.027777, n_lat=390, n_lon=630,
        )


def test_grid_rejects_lon_inverted():
    """Longitude max below min is a typo."""
    with pytest.raises(ValueError):
        GridSpec(
            crs="EPSG:4326", lat_min=53.5, lat_max=60.0, lon_min=27.0, lon_max=9.5,
            lat_step=0.016666, lon_step=0.027777, n_lat=390, n_lon=630,
        )


def test_grid_rejects_non_positive_lat_step():
    """Latitude step must be positive (Field(gt=0) constraint)."""
    with pytest.raises(ValidationError, match="greater than 0"):
        GridSpec(
            crs="EPSG:4326", lat_min=53.5, lat_max=60.0, lon_min=9.5, lon_max=27.0,
            lat_step=-0.016666, lon_step=0.027777, n_lat=390, n_lon=630,
        )


def test_grid_rejects_non_positive_lon_step():
    """Longitude step must be positive (Field(gt=0) constraint)."""
    with pytest.raises(ValidationError, match="greater than 0"):
        GridSpec(
            crs="EPSG:4326", lat_min=53.5, lat_max=60.0, lon_min=9.5, lon_max=27.0,
            lat_step=0.016666, lon_step=-0.027777, n_lat=390, n_lon=630,
        )


def test_grid_rejects_non_positive_n_lat():
    """Number of latitude cells must be positive (Field(gt=0) constraint)."""
    with pytest.raises(ValidationError, match="greater than 0"):
        GridSpec(
            crs="EPSG:4326", lat_min=53.5, lat_max=60.0, lon_min=9.5, lon_max=27.0,
            lat_step=0.016666, lon_step=0.027777, n_lat=0, n_lon=630,
        )


def test_grid_rejects_non_positive_n_lon():
    """Number of longitude cells must be positive (Field(gt=0) constraint)."""
    with pytest.raises(ValidationError, match="greater than 0"):
        GridSpec(
            crs="EPSG:4326", lat_min=53.5, lat_max=60.0, lon_min=9.5, lon_max=27.0,
            lat_step=0.016666, lon_step=0.027777, n_lat=390, n_lon=0,
        )


def test_grid_rejects_incoherent_extent():
    """Extent implied by origin, step and count must match declared max (coherence check)."""
    with pytest.raises(ValidationError, match="incoherent"):
        GridSpec(
            crs="EPSG:4326", lat_min=53.5, lat_max=100.0, lon_min=9.5, lon_max=27.0,
            lat_step=0.016666, lon_step=0.027777, n_lat=390, n_lon=630,
        )


def _layer(**over):
    """A valid layer record. Override one field per negative case."""
    base = dict(
        name="copernicus_phy",
        source="Copernicus Marine Service",
        product_id="BALTICSEA_MULTIYEAR_PHY_003_011",
        dataset_id="cmems_mod_bal_phy_my_P1M-m",
        version="202303",
        retrieved_on=datetime(2026, 1, 1, tzinfo=UTC),
        licence="Copernicus Marine Service licence",
        redistribution="allowed",
        source_url="https://data.marine.copernicus.eu/",
        archive=Archive(
            status="pending",
            source_url="https://data.marine.copernicus.eu/",
            unblocked_by="the Zenodo deposit is outside package C (C1)",
        ),
        variables=["salinity_psu", "temp_c"],
    )
    base.update(over)
    return LayerProvenance(**base)


def test_pending_with_a_url_and_a_note_is_accepted():
    """C§4.1: pending is the state every layer of a first real refresh is in."""
    assert _layer().archive.status == "pending"


def test_deposited_needs_a_doi():
    with pytest.raises(ValidationError, match="requires a zenodo_doi"):
        Archive(status="deposited")


def test_forbidden_needs_a_source_url():
    with pytest.raises(ValidationError, match="'forbidden' requires a source_url"):
        Archive(status="forbidden")


def test_pending_without_a_source_url_is_rejected():
    with pytest.raises(ValidationError, match="'pending' requires a source_url"):
        Archive(status="pending", unblocked_by="a note")


def test_pending_without_an_unblocked_by_note_is_rejected():
    """An incomplete pending records a gap without saying what closes it."""
    with pytest.raises(ValidationError, match="requires an unblocked_by note"):
        Archive(status="pending", source_url="https://example.invalid/")


def test_an_unknown_archive_status_is_rejected():
    """The validator accepts exactly three states and nothing else.

    This fails at pydantic FIELD-level validation on the `Literal`, before
    `_check_state_is_complete` ever runs, so we match pydantic's own literal-
    mismatch wording rather than one of our validator's messages.
    """
    with pytest.raises(
        ValidationError, match="Input should be 'deposited', 'forbidden' or 'pending'"
    ):
        Archive(status="archived", source_url="https://example.invalid/")


def test_a_layer_with_no_archive_state_is_rejected():
    """C§7's FIRST archive case, and clause 10's third negative test.

    `archive` is a required field with no default, so a layer without one fails
    at load. Easy to leave untested because the other five cases all exercise a
    malformed archive rather than an absent one — and without it, a later
    refactor giving `archive` a `None` default would pass the whole suite while
    making every layer's provenance optional.

    This fails at pydantic FIELD-level validation (archive is required / must
    be an Archive instance), before our model_validator runs.
    """
    with pytest.raises(ValidationError, match="valid dictionary or instance of Archive"):
        _layer(archive=None)
