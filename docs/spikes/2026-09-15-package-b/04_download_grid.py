"""Resolution + format sweep: one variable, one month, whole South Baltic footprint.

Size for the FULL artifact is computed from this measurement, not by downloading it.
Package B is a measurement; rehearsing package C's full refresh would be the wrong cost.

Footprint is the four pilots plus context - the same extent the website's coastline
GeoJSON uses (8-23 E, 53-58 N), not the whole Baltic model domain, because the tool
assesses South Baltic sites.
"""
import copernicusmarine as cm
from pathlib import Path

OUT = Path(__file__).parent / "data"
OUT.mkdir(exist_ok=True)

WEST, EAST, SOUTH, NORTH = 8.0, 23.0, 53.0, 58.0

JOBS = [
    ("grid_phy_month", "cmems_mod_bal_phy_my_P1M-m", ["thetao", "so"],
     "2024-07-01T00:00:00", "2024-07-31T23:59:59", 0.0, 3.0),
    ("grid_static",    "cmems_mod_bal_phy_my_static", ["deptho", "mask"],
     None, None, 0.0, 3.0),
]

for name, ds_id, variables, t0, t1, dmin, dmax in JOBS:
    target = OUT / f"{name}.nc"
    if target.exists():
        print(f"{name}: present ({target.stat().st_size/1024/1024:.2f} MB), skipping", flush=True)
        continue
    print(f"--- {name} <- {ds_id} ---", flush=True)
    kw = dict(
        dataset_id=ds_id, variables=variables,
        minimum_longitude=WEST, maximum_longitude=EAST,
        minimum_latitude=SOUTH, maximum_latitude=NORTH,
        minimum_depth=dmin, maximum_depth=dmax,
        output_filename=target.name, output_directory=str(OUT), overwrite=True,
    )
    if t0:
        kw.update(start_datetime=t0, end_datetime=t1)
    cm.subset(**kw)
    print(f"{name}: {target.stat().st_size/1024/1024:.2f} MB", flush=True)

print("\nGRID DOWNLOADS COMPLETE", flush=True)
for f in sorted(OUT.glob("grid_*.nc")):
    print(f"  {f.name:20s} {f.stat().st_size/1024/1024:8.2f} MB")
