import pytest

from seagarden_dst.refresh.layer import COVERAGE_LAYERS, LAYER_NAMES, ProbeResult, YearRange


def test_year_range_enumerates_inclusively():
    assert YearRange(start=2023, end=2025).years() == [2023, 2024, 2025]


def test_year_range_of_one_year_is_that_year():
    assert YearRange(start=2024, end=2024).years() == [2024]


def test_year_range_rejects_an_end_before_its_start():
    with pytest.raises(ValueError, match="end year 2020 precedes start year 2025"):
        YearRange(start=2025, end=2020)


def test_probe_result_carries_its_detail():
    result = ProbeResult(
        name="copernicus_phy", status="ok", reachable=True, detail="catalogue responded"
    )
    assert result.detail == "catalogue responded"
    assert (result.name, result.reachable) == ("copernicus_phy", True)


def test_the_five_layer_names_are_exactly_the_spec_s_five():
    assert LAYER_NAMES == (
        "copernicus_phy",
        "copernicus_bgc",
        "copernicus_bgc_light",
        "copernicus_wav",
        "emodnet_bathy",
    )


def test_coverage_layers_are_the_four_that_contribute_independent_coverage():
    # Pinned exactly, not merely as a subset: `valid`'s Derivation attests THIS list,
    # so a change here silently changes what the manifest claims (R4).
    assert COVERAGE_LAYERS == (
        "copernicus_phy",
        "copernicus_bgc",
        "copernicus_wav",
        "emodnet_bathy",
    )
    assert "copernicus_bgc_light" not in COVERAGE_LAYERS


def test_fake_layer_satisfies_the_runtime_checkable_protocol():
    from refresh_fakes import FakeLayer

    from seagarden_dst.refresh.layer import Layer

    assert isinstance(FakeLayer("copernicus_phy", ["temp_c"]), Layer)


def test_importing_the_fakes_does_not_import_xarray():
    # A module-scope `import xarray` in refresh_fakes would break collection of every
    # unmarked module that imports FakeLayer, turning CI's [app,dev] job red. `-m`
    # deselects AFTER collection, so a marker cannot save it.
    import pathlib
    import subprocess
    import sys

    root = pathlib.Path(__file__).resolve().parent.parent
    env = {
        **__import__("os").environ,
        "PYTHONPATH": f"{root / 'src'}{__import__('os').pathsep}{root / 'tests'}",
    }
    result = subprocess.run(
        [sys.executable, "-c", "import refresh_fakes, sys; print('xarray' in sys.modules)"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.stdout.strip() == "False", result.stderr
