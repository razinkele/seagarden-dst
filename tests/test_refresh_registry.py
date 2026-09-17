"""What is registered, and that registering it did not poison the probe path."""

from __future__ import annotations

from seagarden_dst.refresh.layer import LAYER_NAMES, Layer
from seagarden_dst.refresh.registry import REGISTRY


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


def test_no_module_on_the_probe_path_imports_the_spatial_stack_at_module_scope():
    """R3: the probe job installs the bare package, so these imports must stay clean.

    Parsed with `ast` rather than imported or subprocessed, following
    `tests/test_refresh_isolation.py` - importing the module to see what it imports
    is the coupling under test, and a subprocess cannot resolve `seagarden_dst` in
    the development environment, where there is no editable install (see the
    comment at the top of `scripts/refresh_layers.py`). The AST walk asks the
    precise question R3 asks: is the import at MODULE scope, or inside a method?
    """
    import ast
    from pathlib import Path

    forbidden = {"xarray", "copernicusmarine"}
    refresh_dir = Path(__file__).resolve().parent.parent / "src" / "seagarden_dst" / "refresh"
    probe_path = [refresh_dir / "registry.py", *sorted((refresh_dir / "sources").glob("*.py"))]

    offenders: list[str] = []
    for module_path in probe_path:
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
        # Only the module body - an import inside a FunctionDef is what R3 allows.
        for node in tree.body:
            if isinstance(node, ast.Import):
                names = {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                names = {(node.module or "").split(".")[0]}
            else:
                continue
            for name in sorted(names & forbidden):
                offenders.append(f"{module_path.name}:{node.lineno} imports {name}")

    assert offenders == [], (
        "module-scope spatial imports on the probe path: " + "; ".join(offenders)
        + ". The probe job installs no spatial extra and would crash on import (R3)"
    )
