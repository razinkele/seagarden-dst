"""`copernicus_bgc` — nutrients from the monthly BGC reanalysis (C§3.2).

**This layer emits two variables and claims one.** `din_umol_l = no3 + nh4` is
assembled from more than one source variable, so C§4.1 makes it a `Derivation` —
and C§4.4 then forbids it from appearing in any layer's `variables`, because a
variable claimed by both a layer and a derivation is claimed twice. `dip_umol_l` is
a straight passthrough of `po4` and is claimed here in the ordinary way.

Do not "fix" the asymmetry by adding `din_umol_l` to `variables`: the manifest's
every-variable-claimed-exactly-once validator will reject the result.

No unit conversion: `no3`, `nh4` and `po4` are mmol m-3, which is micromol/L.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from seagarden_dst.artifact.manifest import Archive, LayerProvenance
from seagarden_dst.refresh.layer import ProbeResult, YearRange
from seagarden_dst.refresh.sources import cmems
from seagarden_dst.refresh.sources.reachability import url_reachable

if TYPE_CHECKING:  # pragma: no cover - typing only
    import xarray as xr

    from seagarden_dst.artifact.grid import GridSpec

DATASET_ID = "cmems_mod_bal_bgc_my_P1M-m"
PRODUCT_ID = "BALTICSEA_MULTIYEAR_BGC_003_012"
SOURCE_URL = "https://data.marine.copernicus.eu/product/BALTICSEA_MULTIYEAR_BGC_003_012"

_SOURCE_VARIABLES = ["no3", "nh4", "po4"]

# What this layer BUILDS. What it CLAIMS is `_CLAIMED` — they differ on purpose.
_PRODUCED = ["din_umol_l", "dip_umol_l"]
_CLAIMED = ["dip_umol_l"]


class CopernicusBgc:
    """One layer, one dataset (C§5)."""

    name = "copernicus_bgc"

    def __init__(
        self,
        opener: cmems.DatasetOpener | None = None,
        reachability_opener: Callable[..., object] | None = None,
    ) -> None:
        self._opener = opener
        self._reachability_opener = reachability_opener
        self._years: YearRange | None = None

    def probe(self) -> ProbeResult:
        reachable, detail = url_reachable(SOURCE_URL, opener=self._reachability_opener)
        return ProbeResult(name=self.name, reachable=reachable, detail=detail)

    def build(self, grid: GridSpec, years: YearRange, workdir: Path) -> xr.Dataset:
        import xarray as xr

        self._years = years
        source = cmems.open_window(
            DATASET_ID, _SOURCE_VARIABLES, grid, years, opener=self._opener
        )
        no3 = cmems.drop_depth(source["no3"])
        nh4 = cmems.drop_depth(source["nh4"])
        po4 = cmems.drop_depth(source["po4"])
        return xr.Dataset(
            {
                "din_umol_l": cmems.to_yearly(no3 + nh4),
                "dip_umol_l": cmems.to_yearly(po4),
            }
        )

    def provenance(self) -> LayerProvenance:
        return LayerProvenance(
            name=self.name,
            source="Copernicus Marine Service",
            product_id=PRODUCT_ID,
            dataset_id=DATASET_ID,
            version="202303",
            retrieved_on=datetime.now(UTC),
            licence="Copernicus Marine Service licence",
            redistribution="allowed",
            source_url=SOURCE_URL,
            archive=Archive(
                status="pending",
                source_url=SOURCE_URL,
                unblocked_by="Zenodo deposit of the built artifact; C§1 puts it outside package C",
            ),
            variables=list(_CLAIMED),
        )

    def baseline_years(self) -> dict[str, list[int]]:
        if self._years is None:
            raise RuntimeError(
                f"{self.name}.baseline_years() called before build(): this layer's "
                "window IS the requested year range, which it only learns from "
                "build() (R1)"
            )
        window = self._years.years()
        # Keyed on what is PRODUCED, not on what is claimed: the driver resolves
        # baselines against the merged dataset's data_vars, and `din_umol_l` is one
        # of them even though a Derivation claims it.
        return {name: list(window) for name in _PRODUCED}
