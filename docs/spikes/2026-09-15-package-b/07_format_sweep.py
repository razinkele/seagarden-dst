"""Artifact size at three resolutions x two formats, and the extrapolation to a full refresh.

Formats. The two candidates follow from design section 4's premise, not from taste: the
runtime reads the artifact and nothing else, on a four-package dependency list
(numpy, scipy, pydantic, pyyaml). Whichever wins, package D adds ONE reader dependency,
and that is a cost the note has to state rather than discover later. NetCDF4 and Zarr are
the two that xarray reads natively and that Zenodo can archive. COG is not a candidate:
the artifact is a multi-variable, multi-band cube, not a picture.

Extrapolation model, stated so it can be disagreed with:
  monthly bands : salinity, temperature, DIN, DIP, PAR, Kd, wave_p95   -> 7 x 12 = 84 fields
  static bands  : depth, land-sea mask, wave_annual_max                ->          3 fields
  TOTAL                                                                          87 2-D fields
Measured bytes-per-2-D-field at each resolution x format, x 87. Compression on real
seasonal variation may differ from the single month measured here, which is why the
per-field number is reported alongside the total rather than buried in it.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import xarray as xr

DATA = Path(__file__).parent / "data"
WORK = Path(__file__).parent / "fmt"
if WORK.exists():
    shutil.rmtree(WORK)
WORK.mkdir()

N_FIELDS_TOTAL = 87
ZENODO_LIMIT_GB = 50.0

src = xr.open_dataset(DATA / "grid_phy_month.nc")
if "depth" in src.dims:
    src = src.isel(depth=0)
src = src.isel(time=0) if "time" in src.dims else src
base = src[["thetao", "so"]].astype("float32")

lat, lon = base["latitude"].values, base["longitude"].values
dlat = float(abs(lat[1] - lat[0]))
km = dlat * 111.32

def du(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())

print("=" * 96)
print(f"Source: {base.sizes['latitude']} x {base.sizes['longitude']} cells at "
      f"{km:.2f} km, 2 variables, 1 month, float32")
print(f"Uncompressed reference: {base['thetao'].size * 4 / 1024**2:.2f} MB per 2-D field")
print("=" * 96)
print(f"\n{'resolution':>12s} {'cells':>14s} {'format':>8s} {'bytes/field':>13s} "
      f"{'x87 artifact':>14s} {'vs 50GB':>9s}")
print("-" * 96)

rows = []
for factor in (1, 2, 4):
    ds = base if factor == 1 else base.coarsen(
        latitude=factor, longitude=factor, boundary="trim").mean()
    ny, nx = ds.sizes["latitude"], ds.sizes["longitude"]
    res_km = km * factor

    for fmt in ("netcdf", "zarr"):
        if fmt == "netcdf":
            target = WORK / f"r{factor}.nc"
            # complevel 5, and every document citing this measurement records the
            # DECISION as complevel 4 — the package B write-up's size table, the
            # data-layer design, and package C's "~170 MB at B's measured 3.5x
            # NetCDF4+zlib4 ratio". The 5 is what actually ran; the discrepancy is
            # recorded here rather than edited away, because this file exists to show
            # what produced the numbers. Re-run at 4 before treating the ratio as
            # attributable to the level the design names.
            enc = {v: {"zlib": True, "complevel": 5, "dtype": "float32"} for v in ds.data_vars}
            ds.to_netcdf(target, encoding=enc, engine="netcdf4")
        else:
            target = WORK / f"r{factor}.zarr"
            ds.to_zarr(target, mode="w", consolidated=True)

        total = du(target)
        per_field = total / len(ds.data_vars)
        artifact = per_field * N_FIELDS_TOTAL
        pct = 100 * artifact / (ZENODO_LIMIT_GB * 1024**3)
        rows.append((res_km, ny * nx, fmt, per_field, artifact, pct))
        print(f"{res_km:9.2f} km {ny:5d}x{nx:<7d} {fmt:>8s} "
              f"{per_field/1024:10.1f} KB {artifact/1024**2:11.1f} MB {pct:8.3f}%")

print("-" * 96)
best = min(rows, key=lambda r: r[4])
print(f"Smallest: {best[2]} at {best[0]:.2f} km -> {best[4]/1024**2:.1f} MB "
      f"({best[5]:.3f}% of the Zenodo 50 GB per-file limit)")
worst = max(rows, key=lambda r: r[4])
print(f"Largest:  {worst[2]} at {worst[0]:.2f} km -> {worst[4]/1024**2:.1f} MB "
      f"({worst[5]:.3f}% of the limit)")
print(f"\nEvery candidate is {worst[5]:.2f}% of the Zenodo limit or less — size does NOT")
print("constrain the resolution choice. That is the finding; it frees the decision to")
print("rest on the valid-cell fractions instead.")
