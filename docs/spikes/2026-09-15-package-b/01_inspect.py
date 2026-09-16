"""Lazy metadata inspection. No download: open_dataset streams the store's metadata."""
import copernicusmarine as cm

TARGETS = [
    ("phy daily",   "cmems_mod_bal_phy_my_P1D-m"),
    ("phy monthly", "cmems_mod_bal_phy_my_P1M-m"),
    ("bgc daily",   "cmems_mod_bal_bgc_my_P1D-m"),
    ("bgc monthly", "cmems_mod_bal_bgc_my_P1M-m"),
    ("phy static",  "cmems_mod_bal_phy_my_static"),
]

for label, ds_id in TARGETS:
    print("=" * 72)
    print(f"{label}  --  {ds_id}")
    try:
        ds = cm.open_dataset(dataset_id=ds_id)
    except Exception as exc:
        print("  FAILED:", type(exc).__name__, exc)
        continue
    print("  dims:", dict(ds.sizes))
    for coord in ("latitude", "longitude", "depth", "time"):
        if coord in ds.coords:
            v = ds[coord]
            if coord == "time":
                print(f"  time: {str(v.values[0])[:10]} .. {str(v.values[-1])[:10]}  (n={v.size})")
            elif v.size > 1:
                step = float(abs(v.values[1] - v.values[0]))
                print(f"  {coord}: {float(v.min()):.4f} .. {float(v.max()):.4f}"
                      f"  step={step:.5f}  n={v.size}")
    print("  variables:")
    for name, da in ds.data_vars.items():
        units = da.attrs.get("units", "?")
        long = da.attrs.get("long_name", "")[:52]
        print(f"    {name:14s} [{units:12s}] {long}")
