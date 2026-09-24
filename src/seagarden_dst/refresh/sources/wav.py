"""`copernicus_wav` — the monthly p95 of hourly significant wave height (C§3.2).

Four things make this layer the odd one out.

Within this package **R2 means the lazy-open rule** — the seam returns an
`xr.Dataset`, never a `Path`. The previous package used the same label for its
baselines-declared-and-cross-checked rule; that one is named here rather than
numbered, to keep the two apart.

**It ignores the year range it is handed.** C§3.2 fixes the p95 window at 2023-2025,
so `build` requests those years whatever it is asked for, and `baseline_years`
declares them. `significant_wave_m` has no `year` dim, so the driver cannot read the
window off the data and accepts the declaration as stated — the case the
declared-baselines rule (C§4.4) exists for.

**Its shape is monthly, not yearly**: `(month, latitude, longitude)`. The p95 is
collapsed over the whole window, so there is no year axis left.

**It has no pre-`build()` guard on `baseline_years()`, and that is this layer being
RIGHT, not this layer being lax.** Its window is a constant of the design, so it can
answer at any time — which is the property C-b's handoff wanted of every layer. The
other three raise instead because their window genuinely *is* the requested range,
which they learn only from `build()`; the guard makes that dependency loud rather
than letting them return a guess. That is a compromise forced on them by
`baseline_years()` taking no argument, not a virtue to spread. A future package must
not add the guard here "for symmetry" — it would be symmetry with a workaround.

**It is the expensive one.** ~25.8 GB of hourly `VHM0` crosses the wire, against
~0.59 GB for every monthly variable combined. The reduction runs against the lazy
Dataset `open_window` returns (R2) so those hours are never written to disk; a
`subset`-to-file route would need 25.8 GB of free space that this project's machines
do not have.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from seagarden_dst.artifact.manifest import LayerProvenance
from seagarden_dst.refresh.layer import ProbeResult, YearRange
from seagarden_dst.refresh.sources import cmems
from seagarden_dst.refresh.sources.catalogue import DescribeCallable

if TYPE_CHECKING:  # pragma: no cover - typing only
    import xarray as xr

    from seagarden_dst.artifact.grid import GridSpec

DATASET_ID = "cmems_mod_bal_wav_my_PT1H-i"
PRODUCT_ID = "BALTICSEA_MULTIYEAR_WAV_003_015"
# NOT 202303. The wave product is at its own catalogue version, checked on
# 15 September 2026 (C§11.1's table); physics and biogeochemistry are at 202303
# because they are different products, not because the four layers share a version.
VERSION = "202411"

# Fixed by C§3.2, not by the caller. See the module docstring.
WAVE_BASELINE_YEARS: list[int] = [2023, 2024, 2025]
P95 = 0.95

#: Rows of latitude per dask chunk when the source is lazy. Run 2 of the first real
#: refresh (2026-09-24) was OOM-killed at 30.7 GB resident because the layer rechunked
#: the 25.9 GB hourly source to ONE chunk before the quantile. One calendar month over
#: three years is ~2.15 GB at full extent; 39-row bands (of 390) make that ~215 MB a
#: chunk, and with the driver's four workers the whole layer stays under a few GB.
LATITUDE_BAND_ROWS = 39


class CopernicusWav:
    """One layer, one dataset (C§5). The only layer with a window of its own."""

    name = "copernicus_wav"

    def __init__(
        self,
        opener: cmems.DatasetOpener | None = None,
        describe: DescribeCallable | None = None,
    ) -> None:
        self._opener = opener
        self._describe = describe

    def probe(self) -> ProbeResult:
        return cmems.catalogue_probe(
            self.name, DATASET_ID, VERSION, describe=self._describe
        )

    def build(self, grid: GridSpec, years: YearRange, workdir: Path) -> xr.Dataset:
        import xarray as xr

        # `years` is deliberately unused: the window is this layer's own (C§3.2).
        del years
        own_window = YearRange(start=WAVE_BASELINE_YEARS[0], end=WAVE_BASELINE_YEARS[-1])
        source = cmems.open_window(
            DATASET_ID, ["VHM0"], grid, own_window, opener=self._opener, surface=False
        )
        hourly = source["VHM0"]

        # Month by month, never the whole window at once. quantile needs the reduced
        # axis in one chunk, and an earlier version rechunked the ENTIRE hourly array
        # to one chunk - 25.9 GB - which the kernel OOM-killed on the first real run.
        # One calendar month's hours (all three years) in latitude bands is the same
        # arithmetic per cell with a bounded footprint, and on a lazy source it is
        # still a rechunk, not a load: the hours never land on disk (R2).
        months = sorted({int(m) for m in hourly["time"].dt.month.values})
        per_month = []
        for month in months:
            hours = hourly.sel(time=hourly["time"].dt.month == month)
            if hours.chunks is not None:
                hours = hours.chunk(
                    {"time": -1, "latitude": LATITUDE_BAND_ROWS, "longitude": -1}
                )
            # quantile() attaches a scalar `quantile` coord. check_shapes looks at
            # dims, so it would pass - and the coord would ship in the artifact as an
            # unexplained 0.95 that no manifest field accounts for.
            per_month.append(
                hours.quantile(P95, dim="time").drop_vars("quantile", errors="ignore")
            )
        p95 = xr.concat(per_month, dim=xr.DataArray(months, dims="month", name="month"))

        return xr.Dataset(
            {"significant_wave_m": p95.transpose("month", "latitude", "longitude")}
        )

    def provenance(self) -> LayerProvenance:
        return cmems.copernicus_provenance(
            name=self.name,
            product_id=PRODUCT_ID,
            dataset_id=DATASET_ID,
            version=VERSION,
            variables=["significant_wave_m"],
        )

    def baseline_years(self) -> dict[str, list[int]]:
        # No build() guard here, and that is not an oversight: this window is a
        # constant of the design, not a function of the request, so this layer CAN
        # answer before building (the property C-b's handoff wanted of all of them).
        # See the module docstring: the three yearly layers' guard is the compromise,
        # not this. Do not add one here for symmetry.
        return {"significant_wave_m": list(WAVE_BASELINE_YEARS)}
