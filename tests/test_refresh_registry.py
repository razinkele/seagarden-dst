"""What is registered, and that registering it did not poison the probe path."""

from __future__ import annotations

import pytest

from seagarden_dst.refresh.layer import LAYER_NAMES, Layer
from seagarden_dst.refresh.registry import REGISTRY, check_registered_names


def test_the_four_copernicus_layers_are_registered():
    assert set(REGISTRY) == {
        "copernicus_phy",
        "copernicus_bgc",
        "copernicus_bgc_light",
        "copernicus_wav",
    }


def test_every_registered_name_is_one_C5_names():
    """C-c2 tightens this to equality once emodnet_bathy lands."""
    assert set(REGISTRY) <= set(LAYER_NAMES)


def test_an_unnamed_layer_in_the_registry_is_refused():
    """The import-time guard, now reachable from a test (C§5).

    `check_registered_names` runs at module scope over the real registry, where it
    passes. This calls the same function with a registry C§5 does not name, which is
    the only way to see it fire — and the reason it is a function at all.
    """
    with pytest.raises(RuntimeError, match="not named in LAYER_NAMES"):
        check_registered_names({"not_a_layer_C5_names": object()}, LAYER_NAMES)  # type: ignore[dict-item]


def test_the_real_registry_passes_the_same_guard_the_import_runs():
    check_registered_names(REGISTRY, LAYER_NAMES)


def test_every_registered_key_matches_its_layers_own_name():
    for key, layer in REGISTRY.items():
        assert layer.name == key


def test_every_registered_layer_satisfies_the_protocol():
    for layer in REGISTRY.values():
        assert isinstance(layer, Layer)


# C§11.1's table, checked against the live Copernicus catalogue on 15 September 2026.
# `layer name -> (dataset_id, version)`. The wave product sits at a DIFFERENT version
# from physics and biogeochemistry - that is expected (they are different products),
# and it is exactly why `version` is a per-layer field rather than a per-artifact one.
# Re-check against the catalogue before changing a value here: a drift nobody noticed
# is a manifest attesting a version the data did not come from.
C11_1_CATALOGUE: dict[str, tuple[str, str]] = {
    "copernicus_phy": ("cmems_mod_bal_phy_my_P1M-m", "202303"),
    "copernicus_bgc": ("cmems_mod_bal_bgc_my_P1M-m", "202303"),
    "copernicus_bgc_light": ("cmems_mod_bal_bgc_my_P1D-m", "202303"),
    "copernicus_wav": ("cmems_mod_bal_wav_my_PT1H-i", "202411"),
}


def test_every_layer_records_the_dataset_and_version_C11_1_checked():
    """The provenance strings themselves, not merely their shape (C§11.1).

    Unmarked on purpose: `provenance()` is pure pydantic and touches no spatial
    stack, so this belongs in the default selection where a drifted string is
    cheapest to catch. The PAIRING matters as much as either value —
    `copernicus_bgc` and `copernicus_bgc_light` share a product and a version and
    differ only in `dataset_id` (`P1M-m` vs `P1D-m`), so asserting the two fields
    together is what tells them apart.
    """
    recorded = {
        name: (layer.provenance().dataset_id, layer.provenance().version)
        for name, layer in REGISTRY.items()
    }
    assert recorded == C11_1_CATALOGUE


def test_the_catalogue_table_covers_exactly_the_registered_layers():
    """A fifth layer, or a removed one, reddens the table rather than slipping past."""
    assert set(REGISTRY) == set(C11_1_CATALOGUE)


# The R3 module-scope-import guard lives once, parametrised, at
# tests/test_refresh_catalogue.py::test_no_refresh_module_imports_the_spatial_stack_at_module_scope
# (it covers registry.py, layer.py, and every module under sources/).
