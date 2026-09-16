"""Valid-cell fractions for the four pilots, at native resolution and coarsenings.

Design section 6.2 sets a minimum valid fraction of 60% and says plainly that the
number is ASSUMED, not sourced, and that package B reports the distribution so it can
be set on evidence. This is that measurement.

Coarsening convention, stated because it is a choice: a coarse cell's valid fraction
is the MEAN of the native land-sea mask within it, and the coarse cell counts as sea
when that mean is >= 0.5 (majority water). Any other convention shifts the numbers.
"""
from __future__ import annotations

import numpy as np
import xarray as xr
import yaml
from pathlib import Path

DATA = Path(__file__).parent / "data"
PILOTS = yaml.safe_load(open("/home/razinka/seagarden/data/pilots.yaml"))

ds = xr.open_dataset(DATA / "grid_static.nc")
mask = ds["mask"].isel(depth=0) if "depth" in ds["mask"].dims else ds["mask"]
depth = ds["deptho"].isel(depth=0) if "depth" in ds["deptho"].dims else ds["deptho"]
lat, lon = mask["latitude"].values, mask["longitude"].values
M = mask.values.astype(float)            # 1 = sea, 0 = land

dlat = float(abs(lat[1] - lat[0]))
dlon = float(abs(lon[1] - lon[0]))
KM_PER_DEG_LAT = 111.32


def km_per_deg_lon(at_lat: float) -> float:
    return KM_PER_DEG_LAT * np.cos(np.radians(at_lat))


print("=" * 78)
print(f"Native grid: dlat={dlat:.5f} deg ({dlat*KM_PER_DEG_LAT:.2f} km), "
      f"dlon={dlon:.5f} deg ({dlon*km_per_deg_lon(55.5):.2f} km at 55.5N)")
print(f"Footprint:   {lat.min():.2f}..{lat.max():.2f} N, {lon.min():.2f}..{lon.max():.2f} E "
      f"({M.shape[0]} x {M.shape[1]} cells)")
print(f"Sea cells:   {int(np.nansum(M)):,} of {M.size:,} ({100*np.nansum(M)/M.size:.1f}%)")
print("=" * 78)

# --- 1. Does each pilot's own coordinate land on a sea cell? ---
print("\n1. THE PUBLISHED PILOT COORDINATE, AT NATIVE RESOLUTION\n")
print(f"{'pilot':12s} {'lat':>8s} {'lon':>8s} {'cell':>10s} {'depth_m':>9s}  nearest sea cell")
print("-" * 78)
sea_i, sea_j = np.where(M >= 0.5)
for p in PILOTS:
    plat, plon = float(p["lat"]), float(p["lng"])
    i = int(np.abs(lat - plat).argmin())
    j = int(np.abs(lon - plon).argmin())
    is_sea = M[i, j] >= 0.5
    d = float(depth.values[i, j]) if is_sea else float("nan")

    # great-circle-ish distance to every sea cell, in km
    dy = (lat[sea_i] - plat) * KM_PER_DEG_LAT
    dx = (lon[sea_j] - plon) * km_per_deg_lon(plat)
    dist = np.hypot(dx, dy)
    k = int(dist.argmin())
    nearest_km = float(dist[k])

    verdict = "SEA" if is_sea else "LAND"
    note = "on the cell itself" if is_sea else (
        f"{nearest_km:5.2f} km away at {lat[sea_i[k]]:.4f},{lon[sea_j[k]]:.4f}")
    print(f"{p['country']:12s} {plat:8.4f} {plon:8.4f} {verdict:>10s} "
          f"{d:9.2f}  {note}")

# --- 2. Valid-cell fraction in a buffer, at three resolutions ---
print("\n\n2. VALID-CELL FRACTION IN A BUFFER ROUND EACH PILOT\n")
print("   Fraction of cells that are sea. Threshold under test: 60% (section 6.2).")
FACTORS = [1, 2, 4]
RADII_KM = [1.0, 2.0, 5.0]

header = f"{'pilot':12s} {'radius':>7s}"
for f in FACTORS:
    header += f" {f'{dlat*KM_PER_DEG_LAT*f:.1f}km':>9s}"
print(header)
print("-" * 78)

results = {}
for p in PILOTS:
    plat, plon = float(p["lat"]), float(p["lng"])
    for r_km in RADII_KM:
        row = f"{p['country']:12s} {r_km:6.1f}k"
        for f in FACTORS:
            # coarsen the native mask by f, trimming the remainder
            ny, nx = (M.shape[0] // f) * f, (M.shape[1] // f) * f
            Mc = M[:ny, :nx].reshape(ny // f, f, nx // f, f).mean(axis=(1, 3))
            latc = lat[:ny].reshape(-1, f).mean(axis=1)
            lonc = lon[:nx].reshape(-1, f).mean(axis=1)

            dy = (latc[:, None] - plat) * KM_PER_DEG_LAT
            dx = (lonc[None, :] - plon) * km_per_deg_lon(plat)
            within = np.hypot(dx, dy) <= r_km
            if not within.any():                 # radius smaller than one coarse cell
                i = int(np.abs(latc - plat).argmin())
                j = int(np.abs(lonc - plon).argmin())
                within = np.zeros_like(Mc, dtype=bool)
                within[i, j] = True
            frac = float((Mc[within] >= 0.5).mean())
            results[(p["country"], r_km, f)] = (frac, int(within.sum()))
            row += f" {frac:8.1%}"
        print(row)

print("\n   cells sampled per (pilot, radius, resolution):")
for p in PILOTS:
    for r_km in RADII_KM:
        counts = [results[(p["country"], r_km, f)][1] for f in FACTORS]
        print(f"   {p['country']:12s} r={r_km:4.1f}km  " +
              "  ".join(f"{dlat*KM_PER_DEG_LAT*f:.1f}km:{c:3d}" for f, c in zip(FACTORS, counts)))
