"""Section 10.2 at all four pilots' nearest sea cells."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import xarray as xr

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))
from seagarden_dst.forcing import SiteConditions, day_of_year  # noqa: E402
from seagarden_dst.growth import contraindication, simulate  # noqa: E402
from seagarden_dst.params import default_parameters  # noqa: E402

DATA = Path(__file__).parent / "data"
SITES = {"DK": (55.4749, 10.5137), "DE": (54.1916, 12.0971),
         "PL": (54.5249, 18.5692), "LT": (55.6916, 21.0970)}


def surface_cell(ds, probe, target):
    """NEAREST valid cell to `target`, not the first one in array order.

    `np.where(valid)` returns indices in row-major order, so taking ii[0], jj[0]
    silently selects the south-west corner of the box. At the Danish site that put the
    cell in a brackish fjord (11.93 psu, DIN to 805 umol/L) rather than the Great Belt.
    """
    if "depth" in ds.dims:
        ds = ds.isel(depth=0)
    lat, lon = ds["latitude"].values, ds["longitude"].values
    valid = ~np.isnan(ds[probe].values).all(axis=0)
    ii, jj = np.where(valid)
    if not len(ii):
        return None
    tlat, tlon = target
    dy = (lat[ii] - tlat) * 111.32
    dx = (lon[jj] - tlon) * 111.32 * np.cos(np.radians(tlat))
    k = int(np.hypot(dx, dy).argmin())
    return ds.isel(latitude=int(ii[k]), longitude=int(jj[k]))


def periodic_interp(q, xp, fp, period=366.0):
    qq = np.mod(q - 1.0, period) + 1.0
    xs = np.concatenate(([xp[-1] - period], xp, [xp[0] + period]))
    fs = np.concatenate(([fp[-1]], fp, [fp[0]]))
    return np.interp(qq, xs, fs)


params = default_parameters()
print(f"{'site':4s} {'salinity':>9s} {'meanT':>6s} {'DIN mean':>9s} {'DIN range':>15s}  cell")
print("-" * 78)
site_objs, series = {}, {}
for code in SITES:
    pd_ = surface_cell(xr.open_dataset(DATA / f"{code}_phy_daily.nc"), "thetao", SITES[code])
    pm_ = surface_cell(xr.open_dataset(DATA / f"{code}_phy_monthly.nc"), "thetao", SITES[code])
    bd_ = surface_cell(xr.open_dataset(DATA / f"{code}_bgc_daily.nc"), "no3", SITES[code])
    bm_ = surface_cell(xr.open_dataset(DATA / f"{code}_bgc_monthly.nc"), "no3", SITES[code])
    if any(x is None for x in (pd_, pm_, bd_, bm_)):
        print(f"{code}: no valid cell in box")
        continue

    din_d = (bd_["no3"] + bd_["nh4"]).values
    din_m = (bm_["no3"] + bm_["nh4"]).values
    t_d, t_m = pd_["thetao"].values, pm_["thetao"].values
    sal = pd_["so"].values
    doy_pd = pd_["time"].dt.dayofyear.values.astype(float)
    doy_pm = pm_["time"].dt.dayofyear.values.astype(float)
    doy_bd = bd_["time"].dt.dayofyear.values.astype(float)
    doy_bm = bm_["time"].dt.dayofyear.values.astype(float)

    summer = float(np.nanmean(t_d[(doy_pd >= 172) & (doy_pd <= 264)]))
    winter = float(np.nanmean(t_d[(doy_pd <= 79) | (doy_pd >= 355)]))
    s = SiteConditions(
        region=code, salinity_psu=float(np.nanmean(sal)),
        mean_temp_c=float(np.nanmean(t_d)), summer_temp_c=summer, winter_temp_c=winter,
        surface_par=200.0, din_umol_l=float(np.nanmean(din_d)),
        dip_umol_l=float(np.nanmean(bd_["po4"].values)), depth_m=10.0,
        significant_wave_m=0.6, light_attenuation_k=0.4)
    site_objs[code] = s
    series[code] = (doy_pd, t_d, doy_pm, t_m, doy_bd, din_d, doy_bm, din_m)
    print(f"{code:4s} {s.salinity_psu:8.2f} {s.mean_temp_c:6.2f} {s.din_umol_l:8.2f} "
          f"{np.nanmin(din_d):6.1f}..{np.nanmax(din_d):6.1f}  "
          f"{float(pd_.latitude):.4f},{float(pd_.longitude):.4f}")


class Arm:
    def __init__(self, code, arm): self.code, self.arm = code, arm
    def conditions_for(self, region): return site_objs[self.code]
    def daily_forcing(self, s, window):
        doy_pd, t_d, doy_pm, t_m, doy_bd, din_d, doy_bm, din_m = series[self.code]
        a, b = window
        first, last = day_of_year(a, 1), day_of_year(b, 28)
        if last < first:
            last += 365
        days = np.arange(first, last + 1, dtype=float)
        season = 0.5 * (1.0 + np.cos(2.0 * np.pi * (days - 172.0) / 365.25))
        par = s.par_at_depth() * (0.25 + 0.75 * season)     # identical in both arms
        if self.arm == "daily":
            return (days, par,
                    periodic_interp(days, doy_pd, t_d),
                    periodic_interp(days, doy_bd, din_d))
        return (days, par,
                periodic_interp(days, doy_pm, t_m),
                periodic_interp(days, doy_bm, din_m))


print(f"\n{'site':4s} {'species':22s} {'daily':>11s} {'monthly':>11s} {'rel':>9s}  reportable?")
print("-" * 80)
all_rel = []
for code, s in site_objs.items():
    for key, sp in sorted(params.species.items()):
        if sp.growth is None:
            continue
        bd = simulate(sp, s, forcing=Arm(code, "daily")).biomass[-1]
        bm = simulate(sp, s, forcing=Arm(code, "monthly")).biomass[-1]
        rel = (bm - bd) / bd if bd else float("nan")
        ci = contraindication(sp, s)
        detail = ci[:28] if isinstance(ci, str) else str(ci)[:28]
        blocked = "BLOCKED: " + detail if ci else "reportable"
        if not ci:
            all_rel.append(abs(rel))
        print(f"{code:4s} {key:22s} {bd:9.1f} g {bm:9.1f} g {rel:+8.2%}  {blocked}")

print("-" * 80)
if all_rel:
    print(f"Across REPORTABLE species/sites only (n={len(all_rel)}): "
          f"mean |rel| {np.mean(all_rel):.2%}, max {np.max(all_rel):.2%}")
else:
    print("No species is reportable at any pilot's nearest sea cell — "
          "every one is below its salinity floor.")
