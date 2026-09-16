"""Daily+monthly for the nearest SEA cell to each of the four pilots.

The Lithuanian result alone is not a basis for a decision: its nearest sea cell sits in
the Curonian Lagoon (3.5 psu, DIN to 230 umol/L), which is the most variable water in
the footprint. Measuring all four separates "monthly smoothing loses information" from
"this particular cell is a river plume".
"""
from pathlib import Path

import copernicusmarine as cm

OUT = Path(__file__).parent / "data"
OUT.mkdir(exist_ok=True)
PAD, YEAR, DMAX = 0.04, "2024", 3.0

# nearest sea cell to each published pilot coordinate, from 05_valid_cells.py
SITES = {
    "DK": (55.4749, 10.5137),
    "DE": (54.1916, 12.0971),
    "PL": (54.5249, 18.5692),
    "LT": (55.6916, 21.0970),
}
DATASETS = [
    ("phy_daily",   "cmems_mod_bal_phy_my_P1D-m", ["thetao", "so"]),
    ("phy_monthly", "cmems_mod_bal_phy_my_P1M-m", ["thetao", "so"]),
    ("bgc_daily",   "cmems_mod_bal_bgc_my_P1D-m", ["no3", "nh4", "po4", "zsd"]),
    ("bgc_monthly", "cmems_mod_bal_bgc_my_P1M-m", ["no3", "nh4", "po4", "zsd"]),
]

for code, (lat, lon) in SITES.items():
    for name, ds_id, variables in DATASETS:
        target = OUT / f"{code}_{name}.nc"
        if target.exists():
            print(f"{target.name}: present, skipping", flush=True)
            continue
        cm.subset(
            dataset_id=ds_id, variables=variables,
            minimum_longitude=lon - PAD, maximum_longitude=lon + PAD,
            minimum_latitude=lat - PAD,  maximum_latitude=lat + PAD,
            start_datetime=f"{YEAR}-01-01T00:00:00", end_datetime=f"{YEAR}-12-31T23:59:59",
            minimum_depth=0.0, maximum_depth=DMAX,
            output_filename=target.name, output_directory=str(OUT), overwrite=True,
        )
        print(f"{target.name}: {target.stat().st_size/1024:.0f} KB", flush=True)

print("\nSITE DOWNLOADS COMPLETE", flush=True)
