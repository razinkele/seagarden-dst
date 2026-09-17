"""`copernicus_phy` — salinity and temperature from the monthly PHY reanalysis (C§3.2).

The simplest of the four: two source variables, two artifact variables, a rename and
a reshape. Both are linear in their source, so the monthly product is correct for
them — see C§3.4 for the one variable where that is false.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from seagarden_dst.artifact.manifest import LayerProvenance
from seagarden_dst.refresh.layer import ProbeResult, YearRange
from seagarden_dst.refresh.sources import cmems
from seagarden_dst.refresh.sources.reachability import url_reachable

if TYPE_CHECKING:  # pragma: no cover - typing only
    import xarray as xr

    from seagarden_dst.artifact.grid import GridSpec

DATASET_ID = "cmems_mod_bal_phy_my_P1M-m"
PRODUCT_ID = "BALTICSEA_MULTIYEAR_PHY_003_011"
SOURCE_URL = cmems.product_url(PRODUCT_ID)

# source variable -> artifact variable. No unit conversion: `so` is numerically psu
# and `thetao` is degrees Celsius (package B's provenance table).
_RENAMES = {"so": "salinity_psu", "thetao": "temp_c"}


class CopernicusPhy:
    """One layer, one dataset (C§5)."""

    name = "copernicus_phy"

    def __init__(
        self,
        opener: cmems.DatasetOpener | None = None,
        reachability_opener: Callable[..., object] | None = None,
    ) -> None:
        self._opener = opener
        self._reachability_opener = reachability_opener
        # R1: set by `build`, read by `baseline_years`. None until then, and
        # `baseline_years` refuses rather than guessing.
        self._years: YearRange | None = None

    def probe(self) -> ProbeResult:
        reachable, detail = url_reachable(SOURCE_URL, opener=self._reachability_opener)
        return ProbeResult(
            name=self.name,
            status="ok" if reachable else "unreachable",
            reachable=reachable,
            detail=detail,
        )

    def build(self, grid: GridSpec, years: YearRange, workdir: Path) -> xr.Dataset:
        import xarray as xr

        self._years = years
        source = cmems.open_window(
            DATASET_ID, list(_RENAMES), grid, years, opener=self._opener
        )
        return xr.Dataset(
            {
                artifact_name: cmems.to_yearly(cmems.drop_depth(source[source_name]))
                for source_name, artifact_name in _RENAMES.items()
            }
        )

    def provenance(self) -> LayerProvenance:
        return cmems.copernicus_provenance(
            name=self.name,
            product_id=PRODUCT_ID,
            dataset_id=DATASET_ID,
            # The PHY reanalysis's catalogue version, checked 15 September 2026
            # (C§11.1). Per-layer, not shared: the wave product is at 202411.
            version="202303",
            variables=["salinity_psu", "temp_c"],
        )

    def baseline_years(self) -> dict[str, list[int]]:
        if self._years is None:
            raise RuntimeError(
                f"{self.name}.baseline_years() called before build(): this layer's "
                "window IS the requested year range, which it only learns from "
                "build(). Returning a guess here would put a window in the manifest "
                "that no data backs (R1)"
            )
        window = self._years.years()
        return {"salinity_psu": list(window), "temp_c": list(window)}
