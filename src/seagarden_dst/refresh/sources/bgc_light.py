"""`copernicus_bgc_light` — light attenuation from DAILY Secchi depth (C§3.4).

**The order of operations is the whole point of this module.** k = 1.7/z_SD is
non-linear, and averaging does not commute through it. By Jensen's inequality, with
1/x convex for x > 0, computing 1.7/mean(z) gives a systematically LOWER k than
mean(1.7/z) — less attenuation, more light at cultivation depth, an optimistic
growth bias carrying no marker that anything went wrong.

So: open the DAILY product, compute k per day, then average k over the month. Never
the monthly product, and never the division after the mean.

It is its own layer rather than part of `copernicus_bgc` because it reads its own
dataset, and one layer describes one dataset (C§5). Its `variables` is EMPTY: the
only thing it produces is claimed by a `Derivation` (C§4.4). Populating it would
claim `light_attenuation_k` twice and fail the manifest.
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

DATASET_ID = "cmems_mod_bal_bgc_my_P1D-m"
PRODUCT_ID = "BALTICSEA_MULTIYEAR_BGC_003_012"
SOURCE_URL = cmems.product_url(PRODUCT_ID)

# Poole-Atkins. Named here once so the manifest's `relation` and the code agree.
POOLE_ATKINS_COEFFICIENT = 1.7


class CopernicusBgcLight:
    """One layer, one dataset (C§5). Claims nothing; a Derivation claims its output."""

    name = "copernicus_bgc_light"

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
        source = cmems.open_window(DATASET_ID, ["zsd"], grid, years, opener=self._opener)
        zsd = cmems.drop_depth(source["zsd"])

        # Daily k first. This line and the next must not be swapped (C§3.4).
        daily_k = POOLE_ATKINS_COEFFICIENT / zsd
        monthly_k = daily_k.resample(time="MS").mean()

        return xr.Dataset({"light_attenuation_k": cmems.to_yearly(monthly_k)})

    def provenance(self) -> LayerProvenance:
        return cmems.copernicus_provenance(
            name=self.name,
            product_id=PRODUCT_ID,
            # The DAILY dataset, not the monthly one it shares a product with. This
            # is the split C§11.1 records: same product, same version, two datasets.
            dataset_id=DATASET_ID,
            # The BGC reanalysis's catalogue version, checked 15 September 2026
            # (C§11.1). Per-layer, not shared: the wave product is at 202411.
            version="202303",
            # EMPTY BY DESIGN (C§4.4). See the module docstring before changing this.
            variables=[],
        )

    def baseline_years(self) -> dict[str, list[int]]:
        if self._years is None:
            raise RuntimeError(
                f"{self.name}.baseline_years() called before build(): this layer's "
                "window IS the requested year range, which it only learns from "
                "build() (R1)"
            )
        return {"light_attenuation_k": list(self._years.years())}
