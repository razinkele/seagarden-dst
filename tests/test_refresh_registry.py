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
