"""Shared builders for the refresh-package test suite.

NOT a conftest fixture: several tests call these with per-case overrides
(`manifest(layers=...)`), which a pytest fixture cannot support (a fixture is
neither importable nor callable with arguments). pytest puts `tests/` on
`sys.path` because it has no `__init__.py`, so `from refresh_builders import
...` works from any test module in this directory.
"""

from __future__ import annotations

from datetime import UTC, datetime

from seagarden_dst.refresh.grid import GridSpec
from seagarden_dst.refresh.manifest import (
    AbsentField,
    Archive,
    Derivation,
    DerivationInput,
    LayerProvenance,
    Manifest,
)

_YEARS = list(range(2016, 2026))
_COVERAGE_LAYERS = ("copernicus_phy", "copernicus_bgc", "copernicus_wav", "emodnet_bathy")


def fixture_grid() -> GridSpec:
    """A 3x3 grid, internally coherent, built directly (not GridSpec.baltic()).

    Tasks 4 and 5 pair this manifest with a 3x3 artifact, so the grid must
    describe that artifact rather than the full 390x630 shipped extent.
    """
    lat_min = 54.0
    lon_min = 20.0
    lat_step = 0.016666
    lon_step = 0.027777
    n_lat = 3
    n_lon = 3
    return GridSpec(
        crs="EPSG:4326",
        lat_min=lat_min,
        lat_max=lat_min + n_lat * lat_step,
        lon_min=lon_min,
        lon_max=lon_min + n_lon * lon_step,
        lat_step=lat_step,
        lon_step=lon_step,
        n_lat=n_lat,
        n_lon=n_lon,
    )


def layer(**over) -> LayerProvenance:
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


def layers() -> list[LayerProvenance]:
    """Five layers, each carrying ITS OWN `source`/`product_id`, not `layer()`'s
    Copernicus-physics defaults inherited unchanged (a real defect this design
    exists to prevent — see C§4.4 and C§11.1).

    `product_id` values not stated by the design spec
    (`docs/superpowers/specs/2026-09-15-package-c-refresh-tooling-design.md`,
    C§11.1's table gives `dataset_id` and `version` per layer but no
    `product_id`) are deliberately spelled `FIXTURE_PLACEHOLDER_...` rather than
    invented to look like a real Copernicus product code — inventing a
    plausible-looking id would be exactly the "attest a source it never
    verified" failure C§4.4 exists to catch, just moved one field over.
    `copernicus_phy`'s `BALTICSEA_MULTIYEAR_PHY_003_011` is the one exception:
    it is `layer()`'s own default and is the real CMEMS product for that
    dataset family.
    """
    return [
        layer(name="copernicus_phy", dataset_id="cmems_mod_bal_phy_my_P1M-m",
              variables=["salinity_psu", "temp_c"]),
        layer(name="copernicus_bgc", dataset_id="cmems_mod_bal_bgc_my_P1M-m",
              product_id="FIXTURE_PLACEHOLDER_BGC_PRODUCT_ID",
              variables=["din_umol_l", "dip_umol_l"]),
        # Empty `variables` is expected, not a gap: its only output is derived.
        layer(name="copernicus_bgc_light", dataset_id="cmems_mod_bal_bgc_my_P1D-m",
              product_id="FIXTURE_PLACEHOLDER_BGC_LIGHT_PRODUCT_ID",
              variables=[]),
        layer(name="copernicus_wav", dataset_id="cmems_mod_bal_wav_my_PT1H-i",
              product_id="FIXTURE_PLACEHOLDER_WAV_PRODUCT_ID",
              variables=["significant_wave_m"]),
        layer(
            name="emodnet_bathy", dataset_id="emodnet_bathymetry_2024",
            source="EMODnet Bathymetry",
            product_id="FIXTURE_PLACEHOLDER_EMODNET_BATHY_PRODUCT_ID",
            licence="EMODnet Bathymetry licence",
            source_url="https://emodnet.ec.europa.eu/en/bathymetry",
            archive=Archive(
                status="pending",
                source_url="https://emodnet.ec.europa.eu/en/bathymetry",
                unblocked_by="the Zenodo deposit is outside package C (C1)",
            ),
            variables=["depth_mean_m", "depth_min_m"],
        ),
    ]


def derived() -> list[Derivation]:
    return [
        Derivation(
            field="light_attenuation_k",
            relation="Poole-Atkins k = 1.7/z_SD, computed daily then averaged monthly",
            inputs=[DerivationInput(layer="copernicus_bgc_light", variable="zsd")],
        ),
        Derivation(
            field="valid",
            relation="intersection of contributing layer coverage",
            inputs=[DerivationInput(layer=n, variable="coverage") for n in _COVERAGE_LAYERS],
        ),
    ]


def baselines() -> dict[str, list[int]]:
    return {
        "salinity_psu": _YEARS, "temp_c": _YEARS, "din_umol_l": _YEARS,
        "dip_umol_l": _YEARS, "light_attenuation_k": _YEARS,
        "significant_wave_m": [2023, 2024, 2025],
        "depth_mean_m": [], "depth_min_m": [], "valid": [],
    }


def manifest(**over) -> Manifest:
    base = dict(
        artifact_schema_version=1,
        built_on=datetime(2026, 1, 1, tzinfo=UTC),
        artifact_filename="forcing.nc",
        artifact_sha256="0" * 64,
        artifact_bytes=1,
        synthetic=True,
        grid=fixture_grid(),
        baselines=baselines(),
        layers=layers(),
        derived=derived(),
        absent=[AbsentField(
            field="surface_par",
            reason="no integrated Baltic product carries PAR in any form",
            unblocked_by="a source outside the current layer set",
        )],
    )
    base.update(over)
    return Manifest(**base)
