# Package B — resolution, format and the monthly-climatology premise

**Status:** measurement note, package B's done-when (§8 of
`docs/superpowers/specs/2026-09-13-dst-data-layer-design.md`). Measured 15 September 2026.

Package B was scoped as a spike: decide grid resolution and file format *by measurement*,
report valid-cell fractions so §6.2's 60% threshold is set on evidence, and run §10.2's
daily-versus-monthly comparison. All four are below. Three of them contradict the design.

The scripts and the downloaded data were throwaway and have been deleted; every number
here is reproducible from the dataset identifiers and parameters recorded at the end.

---

## Decisions

| Question | Decision | Why |
|---|---|---|
| **Grid resolution** | **Native, ~2 km** (0.016666° lat × 0.027777° lon) | Not a preference. Coarsening to ~4 km land-masks the cell containing **Tagalaht**, the only published anchor the parameterisation has, and PL-lagoon with it. |
| **File format** | **NetCDF4 + zlib, complevel 4** | Smaller than Zarr at every resolution × temporal combination measured. One file, which §6.3's atomic manifest/artifact pair write wants. Zarr's consolidated metadata is not in the Zarr v3 spec and warns on write. |
| **Temporal structure** | **Per-year monthly fields, not one climatology** | §10.2's own measurement refutes the climatology premise — see below. |
| **§6.2 valid-cell threshold** | **Replace the 60% rule** with "containing cell valid" plus "distance to nearest valid cell" | The 60% rule is degenerate at farm scale and would reject Tagalaht at every resolution. |

---

## 1. The monthly-climatology premise is half right (§10.2)

§10.2 assumed "monthly climatology is sufficient for the biology — measured, not assumed",
and asked for `simulate()` driven with daily and with monthly-mean DIN and PAR from one
Copernicus cell. Done at the Tagalaht cell (58.5249 N, 22.2910 E), 2023–2025, through the
`ForcingSource` seam package A created. Temperature and surface PAR were held identical
across variants so the delta isolates DIN and light attenuation.

Final biomass, g DW/m²:

| species | year | daily | monthly-of-year | 3-yr climatology | (a) monthly/daily | (b) clim/daily |
|---|---|---|---|---|---|---|
| *Fucus* | 2023 | 54.74 | 55.69 | 152.61 | +1.73% | **+178.79%** |
| *Fucus* | 2024 | 290.41 | 320.54 | 152.61 | +10.37% | **−47.45%** |
| *Fucus* | 2025 | 67.84 | 72.97 | 152.61 | +7.57% | **+124.97%** |
| *Ulva* | 2023 | 2.11 | 2.15 | 3.72 | +1.89% | +76.06% |
| *Ulva* | 2024 | 5.27 | 6.19 | 3.72 | **+17.44%** | −29.40% |
| *Ulva* | 2025 | 2.58 | 2.72 | 3.72 | +5.64% | +44.28% |
| *Chorda* | 2023 | 7.57 | 7.50 | 16.91 | −0.91% | +123.28% |
| *Chorda* | 2024 | 39.12 | 42.04 | 16.91 | +7.47% | −56.78% |
| *Chorda* | 2025 | 6.48 | 7.10 | 16.91 | +9.48% | **+160.81%** |

**(a) Monthly temporal resolution is sufficient.** Worst case +17.4%, typically under 10%.
The design's choice of monthly means survives its own test.

**(b) A multi-year climatology is not.** −57% to +179%. Interannual variability swamps the
resolution effect by an order of magnitude. A single 12-month climatology returns 152.61
g DW/m² for *Fucus* in every year, against real values of 54.74, 290.41 and 67.84.

§6.2's "monthly fields replace the sinusoid in `daily_forcing`" stands. What does not stand
is collapsing years into one climatology: the artifact must carry per-year monthly fields,
and `GriddedForcing` must take a year. Otherwise every result inherits an error bar larger
than any other term in the model — while looking like a measurement.

This does not price the alternative away: per-year monthly for three years at native
resolution is 50.7 MB.

---

## 2. Artifact size — 3 resolutions × 2 formats × 2 temporal designs

Baltic box 9.5–27.0 E, 53.5–60.0 N, covering all six placeholder regions. Five fields:
`salinity_psu`, `temp_c`, `din_umol_l`, `dip_umol_l`, `light_attenuation_k`, all float32.
Coarsening is `xarray.coarsen(...).mean()` with `boundary="trim"`. Zarr chunked one chunk
per 2-D field; NetCDF4 zlib complevel 4. "Uncompressed" is n_values × 4 bytes.

| temporal | resolution | cells | uncompressed | **NetCDF4+zlib4** | Zarr |
|---|---|---|---|---|---|
| climatology, 12 months | ~2 km | 245,700 | 59.0 MB | **16.5 MB** | 20.5 MB |
| climatology, 12 months | ~4 km | 61,425 | 14.7 MB | **4.8 MB** | 5.5 MB |
| climatology, 12 months | ~8 km | 15,229 | 3.7 MB | **1.4 MB** | 1.5 MB |
| per-year, 36 months | ~2 km | 245,700 | 176.9 MB | **50.7 MB** | 61.8 MB |
| per-year, 36 months | ~4 km | 61,425 | 44.2 MB | **14.4 MB** | 16.5 MB |
| per-year, 36 months | ~8 km | 15,229 | 11.0 MB | **4.2 MB** | 4.5 MB |

Compression ratio 2.6–3.6× for NetCDF4, 2.5–2.9× for Zarr. NetCDF4 wins at every point.

**Size does not constrain this decision.** The largest variant — the one §10.2's result
requires, at the resolution the anchor requires — is 50.7 MB. Well inside Zenodo's limits,
and small enough that §6.3's atomic pair write is unproblematic. There is no size argument
for coarsening, which is fortunate, because §3 below says coarsening is not available.

---

## 3. Resolution is forced by the anchor, not chosen

Valid = non-NaN in the surface salinity field. Coarsened validity is the mean of the
native mask thresholded at 0.5. The six regions have **no geometry** — placeholder sites
carry none — so these coordinates were invented for this measurement and are recorded so
the numbers can be reproduced or disputed:

`LT-coastal` 55.70 N 21.00 E · `PL-coastal` 54.60 N 18.60 E · `PL-lagoon` 54.40 N 19.60 E ·
`DE-coastal` 54.30 N 12.00 E · `DK-belt` 55.40 N 10.80 E · `EE-coastal` 58.52 N 22.30 E

| region | ~2 km cell valid | ~4 km | ~8 km | 5 km valid fraction @ ~2 km |
|---|---|---|---|---|
| LT-coastal | yes | yes | yes | 100.0% |
| PL-coastal | yes | yes | yes | 93.3% |
| PL-lagoon | yes | **no** | yes | 83.3% |
| DE-coastal | yes | yes | yes | 100.0% |
| DK-belt | yes | yes | yes | 83.3% |
| **EE-coastal (Tagalaht)** | yes | **no** | **no** | **36.7%** |

Tagalaht is a narrow bay on Saaremaa. At ~4 km its containing cell is land; at ~8 km it is
still land. **The only site with a published anchor disappears from the artifact if the
grid is coarsened at all.** PL-lagoon fails at ~4 km for the same reason and reappears at
~8 km, which is not a reprieve — it is the mask coarsening past the lagoon entirely.

Native resolution is therefore not a trade-off against size. It is a requirement.

---

## 4. §6.2's 60% threshold is malformed, and would reject the anchor

Two separate problems.

**It is degenerate at farm scale.** A 0.1 ha community farm is 31.6 m square. The native
cell is ~1.85 × 1.69 km — **59× wider than the farm**. Every farm polygon lies inside one
cell, so its fraction of valid cells is 0% or 100%, and no threshold between them means
anything. §6.2's rule presumes a polygon spanning many cells; the tool's own default scale
does not produce one.

**At a scale where it is well-posed, it rejects Tagalaht.** Over a 5 km siting-region
window at native resolution the valid fraction at EE-coastal is **36.7%**, against §6.2's
assumed 60% minimum. The threshold as written puts the one site the model is calibrated
against outside coverage. The value was marked "assumed, not sourced" and package B was
asked to set it on evidence; the evidence says the *statistic* is wrong, not just the
number.

**Proposed replacement**, for package D to implement:

1. The polygon's containing cell must be valid. This is the real question at farm scale,
   and it is what "is there data here" actually means.
2. Report **distance to the nearest valid cell** and surface it. At native resolution this
   is 0.75–1.28 km across all six regions — a quantity a siting user can judge.
3. Keep a valid-fraction rule only for polygons genuinely spanning multiple cells, and set
   its threshold once such polygons exist. Package E's drawn geometry is what produces
   them.

---

## 5. Two §6.1 source claims are wrong

§6.1's layer table sources `surface_par` from "Copernicus BGC" and `light_attenuation_k`
from "Copernicus BGC `kd490`".

**`BALTICSEA_MULTIYEAR_BGC_003_012` contains neither.** Its variables are `chl`, `nh4`,
`no3`, `nppv`, `o2`, `o2b`, `ph`, `po4`, `spco2`, `zsd`. There is no `kd490`, and no PAR
variable of any kind.

- **`light_attenuation_k` is salvageable from a different variable.** `zsd` is Secchi
  depth; Poole–Atkins gives k ≈ 1.7 / z_SD. At Tagalaht this yields k = 0.152–0.336 m⁻¹,
  mean 0.198, against the placeholder default of 0.4. Defensible — but it should be
  recorded as a *derived* quantity with that relation named, not as a measured layer.
- **`surface_par` has no source in these products.** §6.1's own note anticipated this: "if
  `kd490` proves unusable, both remain placeholder constants after D, and §7 must then
  display that fact the way staleness is displayed, not bury it." Half that contingency is
  now live. PAR stays a placeholder constant and must be displayed as one.

**Waves need re-scoping too.** `BALTICSEA_MULTIYEAR_WAV_003_015` ships a ready-made 2 km
monthly climatology (`cmems_mod_bal_wav_my_2km-climatology_P1M-m`, `VHM0`, 12 time steps)
— but as a **mean**, and §6.1 requires a 95th percentile precisely because "a mean is
wrong in the permissive direction" for the exposure test. The percentile requires the
hourly `PT1H-i` dataset, a far larger pull than the existence of the climatology suggests.
Package C should price this separately. It was outside B's scope and is not measured here.

---

## 6. A flag for D1, not a package B finding

Driven with real Tagalaht forcing, *Fucus* returns **54.7–290.4 g DW/m²** depending on the
year, against the published anchor of 4800–5200 and the placeholder's 2797. Two inputs
differ from the placeholder by large factors in opposite directions: real DIN averages
**1.047 µmol/L** against the placeholder's 5.5, while real k averages **0.198** against
0.4 — the water is clearer but far poorer in nitrogen.

Stated as an observation, not a conclusion. It was measured with surface PAR still at its
placeholder constant, at one cell, at the surface layer. Package A0 already established
that `mu_max` has never been fitted to the anchor and that `b_max` is set from the anchor's
own upper bound. Whether this gap is a parameterisation failure or an artefact of those
caveats is **package D1's question** — and D1 now has reason to expect the fit to be hard.

---

## Provenance

| | |
|---|---|
| Products | `BALTICSEA_MULTIYEAR_PHY_003_011`, `BALTICSEA_MULTIYEAR_BGC_003_012`, `BALTICSEA_MULTIYEAR_WAV_003_015` |
| Datasets | `cmems_mod_bal_phy_my_P1M-m`, `cmems_mod_bal_bgc_my_P1M-m`, `cmems_mod_bal_phy_my_P1D-m`, `cmems_mod_bal_bgc_my_P1D-m` |
| Dataset version | `202303` |
| Full coverage | 1993-01-01 to 2026-05-31 |
| Baseline used | **2023, 2024, 2025** — the last three full calendar years. No `_myint_` interim product was involved; all datasets are the main `_my_` reanalysis, so provenance is uniform. |
| Depth | Surface level only, 0.50 m. §6.1 does not specify a depth and the reanalysis is 3-D with 56 levels. This choice was made here and should be recorded in §6.1. |
| Grid | 0.016666° lat × 0.027777° lon = 1.85 km × 1.69 km at 56.75 N |
| Units | `no3`, `nh4`, `po4` in mmol m⁻³ = µmol L⁻¹, matching `din_umol_l` directly. DIN = `no3` + `nh4`. `so` numerically psu. `thetao` °C. |
| Client | `copernicusmarine` 2.4.0, xarray 2025.11.0, zarr 3.1.6 |
| Download volume | 205 MB, deleted after measurement |

## What package B did not do

No `GriddedForcing`, no aggregation code, no manifest — those are packages C and D. The
`terra` port validation of §6.2 is untouched and remains D's. Wave percentiles are
unmeasured. The `CellForcing` stub written for §10.2 was throwaway and is not committed.
