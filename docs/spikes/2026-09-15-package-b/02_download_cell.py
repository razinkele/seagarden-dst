"""§10.2: one Copernicus cell, one year, daily AND monthly. Small by construction.

Lithuanian pilot (55.7033 N, 21.1443 E) - KU's own site, and the one whose species
(Chorda filum) is tier C everywhere, so the forcing question matters most there.
"""
from pathlib import Path

import copernicusmarine as cm

OUT = Path(__file__).parent / "data"
OUT.mkdir(exist_ok=True)

LAT, LON = 55.7033, 21.1443
PAD = 0.05                      # a few native cells either way; we pick nearest later
YEAR = "2024"                   # last complete year well inside the reanalysis
DEPTH_MAX = 3.0                 # top levels; cultivation_depth_m defaults to 1.5

JOBS = [
    ("phy_daily",   "cmems_mod_bal_phy_my_P1D-m", ["thetao", "so"]),
    ("phy_monthly", "cmems_mod_bal_phy_my_P1M-m", ["thetao", "so"]),
    ("bgc_daily",   "cmems_mod_bal_bgc_my_P1D-m", ["no3", "nh4", "po4", "zsd"]),
    ("bgc_monthly", "cmems_mod_bal_bgc_my_P1M-m", ["no3", "nh4", "po4", "zsd"]),
]

for name, ds_id, variables in JOBS:
    target = OUT / f"{name}.nc"
    if target.exists():
        print(f"{name}: already present ({target.stat().st_size/1024:.0f} KB), skipping")
        continue
    print(f"--- {name} <- {ds_id} ---", flush=True)
    cm.subset(
        dataset_id=ds_id,
        variables=variables,
        minimum_longitude=LON - PAD, maximum_longitude=LON + PAD,
        minimum_latitude=LAT - PAD,  maximum_latitude=LAT + PAD,
        start_datetime=f"{YEAR}-01-01T00:00:00",
        end_datetime=f"{YEAR}-12-31T23:59:59",
        minimum_depth=0.0, maximum_depth=DEPTH_MAX,
        output_filename=target.name,
        output_directory=str(OUT),
        overwrite=True,
    )
    print(f"{name}: {target.stat().st_size/1024:.1f} KB", flush=True)

print("\nALL DOWNLOADS COMPLETE")
for f in sorted(OUT.glob("*.nc")):
    print(f"  {f.name:16s} {f.stat().st_size/1024:8.1f} KB")
