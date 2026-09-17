"""`copernicus_wav` — the monthly p95 of hourly significant wave height (C§3.2).

Three things make this layer the odd one out.

**It ignores the year range it is handed.** C§3.2 fixes the p95 window at 2023-2025,
so `build` requests those years whatever it is asked for, and `baseline_years`
declares them. `significant_wave_m` has no `year` dim, so the driver cannot read the
window off the data and accepts the declaration as stated — the case R2 exists for.

**Its shape is monthly, not yearly**: `(month, latitude, longitude)`. The p95 is
collapsed over the whole window, so there is no year axis left.

**It is the expensive one.** ~25.8 GB of hourly `VHM0` crosses the wire, against
~0.59 GB for every monthly variable combined. The reduction runs against the lazy
Dataset `open_window` returns (R2) so those hours are never written to disk; a
`subset`-to-file route would need 25.8 GB of free space that this project's machines
do not have.
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

DATASET_ID = "cmems_mod_bal_wav_my_PT1H-i"
PRODUCT_ID = "BALTICSEA_MULTIYEAR_WAV_003_015"
SOURCE_URL = "https://data.marine.copernicus.eu/product/BALTICSEA_MULTIYEAR_WAV_003_015"

# Fixed by C§3.2, not by the caller. See the module docstring.
WAVE_BASELINE_YEARS: list[int] = [2023, 2024, 2025]
P95 = 0.95


class CopernicusWav:
    """One layer, one dataset (C§5). The only layer with a window of its own."""

    name = "copernicus_wav"

    def __init__(
        self,
        opener: cmems.DatasetOpener | None = None,
        reachability_opener: Callable[..., object] | None = None,
    ) -> None:
        self._opener = opener
        self._reachability_opener = reachability_opener

    def probe(self) -> ProbeResult:
        reachable, detail = url_reachable(SOURCE_URL, opener=self._reachability_opener)
        return ProbeResult(name=self.name, reachable=reachable, detail=detail)

    def build(self, grid: GridSpec, years: YearRange, workdir: Path) -> xr.Dataset:
        import xarray as xr

        # `years` is deliberately unused: the window is this layer's own (C§3.2).
        del years
        own_window = YearRange(start=WAVE_BASELINE_YEARS[0], end=WAVE_BASELINE_YEARS[-1])
        source = cmems.open_window(
            DATASET_ID, ["VHM0"], grid, own_window, opener=self._opener, surface=False
        )
        hourly = source["VHM0"]

        # quantile needs the reduced axis in one chunk; on a lazy dask-backed array
        # that is a rechunk, not a load, so the hours still never land on disk.
        if hourly.chunks is not None:
            hourly = hourly.chunk({"time": -1})

        p95 = hourly.groupby("time.month").quantile(P95, dim="time")
        # groupby().quantile() attaches a scalar `quantile` coord. check_shapes looks
        # at dims, so it would pass — and the coord would ship in the artifact as an
        # unexplained 0.95 that no manifest field accounts for.
        p95 = p95.drop_vars("quantile", errors="ignore")

        return xr.Dataset(
            {"significant_wave_m": p95.transpose("month", "latitude", "longitude")}
        )

    def provenance(self) -> LayerProvenance:
        return LayerProvenance(
            name=self.name,
            source="Copernicus Marine Service",
            product_id=PRODUCT_ID,
            dataset_id=DATASET_ID,
            # NOT 202303. The wave product is at its own catalogue version, checked
            # on 15 September 2026 (C§11.1's table); physics and biogeochemistry are
            # at 202303 because they are different products, not because the four
            # layers share a version. This field is per-layer for exactly this case.
            version="202411",
            retrieved_on=datetime.now(UTC),
            licence="Copernicus Marine Service licence",
            redistribution="allowed",
            source_url=SOURCE_URL,
            archive=Archive(
                status="pending",
                source_url=SOURCE_URL,
                unblocked_by="Zenodo deposit of the built artifact; C§1 puts it outside package C",
            ),
            variables=["significant_wave_m"],
        )

    def baseline_years(self) -> dict[str, list[int]]:
        # No build() guard here, and that is not an oversight: this window is a
        # constant of the design, not a function of the request, so this layer CAN
        # answer before building (the property C-b's handoff wanted of all of them).
        return {"significant_wave_m": list(WAVE_BASELINE_YEARS)}
