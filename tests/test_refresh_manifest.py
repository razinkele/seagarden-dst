import numpy as np
import pytest
from pydantic import ValidationError
from refresh_builders import (
    baselines as _baselines,
)
from refresh_builders import (
    layer as _layer,
)
from refresh_builders import (
    layers as _layers,
)
from refresh_builders import (
    manifest as _manifest,
)

from seagarden_dst.refresh.grid import GridSpec
from seagarden_dst.refresh.manifest import ARTIFACT_VARIABLES, Archive


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
    """Latitude max below min is a typo.

    match= is unique to the inversion branch: the coherence check raises
    ValueError on this same malformed input too (implied_lat_max is even
    further from a negative lat_max), so a bare pytest.raises(ValueError)
    would pass even with the inversion check deleted.
    """
    with pytest.raises(ValidationError, match="must exceed lat_min"):
        GridSpec(
            crs="EPSG:4326", lat_min=60.0, lat_max=53.5, lon_min=9.5, lon_max=27.0,
            lat_step=0.016666, lon_step=0.027777, n_lat=390, n_lon=630,
        )


def test_grid_rejects_lon_inverted():
    """Longitude max below min is a typo. See test_grid_rejects_lat_inverted."""
    with pytest.raises(ValidationError, match="must exceed lon_min"):
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
    """Extent implied by origin, step and count must match declared max (coherence check).

    match= is tightened to "lat grid extent is incoherent" (not the bare word
    "incoherent", which is a substring of BOTH the lat and lon incoherence
    messages): this case only breaks lat_max, so only the lat message must fire.
    """
    with pytest.raises(ValidationError, match="lat grid extent is incoherent"):
        GridSpec(
            crs="EPSG:4326", lat_min=53.5, lat_max=100.0, lon_min=9.5, lon_max=27.0,
            lat_step=0.016666, lon_step=0.027777, n_lat=390, n_lon=630,
        )


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


def test_the_reference_manifest_validates():
    assert set(_manifest().baselines) == ARTIFACT_VARIABLES


def test_a_variable_claimed_by_nobody_is_rejected():
    layers = _layers()
    layers[0].variables = ["salinity_psu"]          # drops temp_c
    with pytest.raises(ValidationError, match="claimed by no"):
        _manifest(layers=layers)


def test_a_variable_claimed_by_two_layers_is_rejected():
    layers = _layers()
    layers[1].variables = ["din_umol_l", "dip_umol_l", "temp_c"]
    with pytest.raises(ValidationError, match="claimed more than once"):
        _manifest(layers=layers)


def test_a_variable_claimed_by_a_layer_and_a_derivation_is_rejected():
    """Not covered by the two-layers case: the rule is stated over the *union*."""
    layers = _layers()
    layers[2].variables = ["light_attenuation_k"]
    with pytest.raises(ValidationError, match="claimed more than once"):
        _manifest(layers=layers)


def test_a_missing_baseline_key_is_rejected():
    b = _baselines()
    del b["depth_mean_m"]
    with pytest.raises(ValidationError, match="baselines"):
        _manifest(baselines=b)


def test_an_empty_baseline_is_accepted_and_is_not_omission():
    """[] means no baseline window applies. The two states must be told apart."""
    assert _manifest().baselines["valid"] == []


def test_an_extra_baseline_key_is_rejected():
    b = _baselines()
    b["surface_par"] = list(range(2016, 2026))
    with pytest.raises(ValidationError, match="baselines"):
        _manifest(baselines=b)


def test_the_wave_baseline_is_not_empty_despite_having_no_year_dimension():
    """C§4.4: the criterion is 'no baseline window', not 'no year dimension'.

    An implementer applying the dimensional test literally would write [] here
    and assert that no window applies to the one variable C§4.1 cites as the
    whole reason baselines is a mapping.
    """
    assert _manifest().baselines["significant_wave_m"] == [2023, 2024, 2025]


def test_a_duplicate_dataset_id_is_rejected():
    """The copy-paste that splits a layer and forgets to change dataset_id."""
    layers = _layers()
    layers[2].dataset_id = "cmems_mod_bal_bgc_my_P1M-m"   # the monthly product
    with pytest.raises(ValidationError, match="dataset_id"):
        _manifest(layers=layers)


def test_an_orphan_layer_is_rejected():
    """A sixth layer with empty `variables` that no derivation names.

    Constructed by ADDING a layer, not by deleting `light_attenuation_k`'s
    derivation. That obvious construction does not work: dropping the derivation
    also unclaims `light_attenuation_k`, so `_check_every_variable_is_claimed_
    exactly_once` — defined earlier, and `model_validator(mode="after")` runs in
    definition order with the first raise winning — fires instead, with a message
    containing no "reachable". The test would fail, and the natural repair
    (loosening `match=`) would leave C§4.4's fourth rule with no case that
    discriminates it, which is what done-when clause 12 forbids.

    Adding an unreferenced layer violates rule 4 and nothing else: the claim union
    is unchanged, `baselines` is unchanged, and the dataset_id is new.
    """
    layers = _layers()
    layers.append(_layer(
        name="copernicus_orphan",
        dataset_id="cmems_mod_bal_orphan_my_P1M-m",
        variables=[],
    ))
    with pytest.raises(ValidationError, match="reachable"):
        _manifest(layers=layers)


def test_the_empty_variables_layer_is_accepted_when_a_derivation_names_it():
    """The positive case: the rule must not simply outlaw the empty list."""
    m = _manifest()
    assert m.layers[2].variables == []
    assert any(i.layer == "copernicus_bgc_light" for d in m.derived for i in d.inputs)


def test_an_unrecognised_schema_version_is_refused():
    with pytest.raises(ValidationError, match="artifact_schema_version"):
        _manifest(artifact_schema_version=2)
