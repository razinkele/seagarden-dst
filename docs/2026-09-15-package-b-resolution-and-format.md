# Package B — resolution, format, and whether monthly is enough

Measurement note for the data-layer design (`specs/2026-09-13-dst-data-layer-design.md`,
package B). Everything below is measured against the Copernicus Baltic reanalysis on
2026-09-15. The measurement scripts are committed beside this note in
`spikes/2026-09-15-package-b/`, so every number here is reproducible.

**Headline: size does not constrain the resolution choice, and monthly forcing is not
safely sufficient. But the most consequential finding was not on B's list — all four
pilot coordinates are land cells, and the obvious workaround is biased.**

---

## 1. What the reanalysis actually provides

| Purpose | Dataset | Grid |
|---|---|---|
| Physics — `so`, `thetao` | `cmems_mod_bal_phy_my_P1D-m` / `_P1M-m` | 774 × 763, 1/60° × 1/36° |
| BGC — `no3`, `nh4`, `po4`, `zsd` | `cmems_mod_bal_bgc_my_P1D-m` / `_P1M-m` | same |
| Static — `deptho`, `mask` | `cmems_mod_bal_phy_my_static` | same |

Native resolution is **1.86 km (lat) × 1.75 km (lon) at 55.5 °N**, 1993-01-01 to
2026-05-31 daily. DIN is `no3 + nh4`; Copernicus reports `mmol m⁻³`, which is µmol/L
exactly, so no conversion is needed.

### Two of section 6.1's stated sources do not exist in this product

- **`kd490` is absent.** Section 6.1 lists it as the source for `light_attenuation_k`.
  The BGC reanalysis carries **`zsd` (Secchi depth)** instead. Kd is derivable from
  Secchi, but that is a *different claim* requiring its own citation and its own error
  budget — it is not the same as having the layer.
- **PAR is absent entirely.** There is no `surface_par` equivalent anywhere in the five
  datasets inspected. Section 6.1 already flagged both as "two growth-model inputs with
  no source"; this note answers the open question as **not from this product**.

Consequence: both remain placeholder constants unless a different product supplies them.
Section 6.1's own instruction applies — section 7 must then display that fact the way
staleness is displayed, not bury it.

**`deptho` also makes EMODnet Bathymetry optional.** Section 6.1 routes `depth_m` through
EMODnet; the Copernicus static file already carries bathymetry and a land-sea mask on the
identical grid, which removes a second external source and a regridding step.

---

## 2. The finding that was not on the list: every pilot coordinate is a land cell

`data/pilots.yaml` in the website repo gives four pilot coordinates. **All four snap to
land cells in the Copernicus model**, so a naive nearest-cell lookup returns an all-NaN
series for every one of them.

| Pilot | Published coordinate | Nearest sea cell | What the coordinate actually is |
|---|---|---|---|
| Denmark | 55.4592, 10.5631 | 3.57 km away | ~6 km inland from Kerteminde, on Funen |
| Germany | 54.0924, 12.0991 | **11.04 km away** | Rostock city, up the Warnow |
| Poland | 54.5189, 18.5305 | 2.59 km away | Gdynia city |
| Lithuania | 55.7033, 21.1443 | 3.24 km away | Klaipėda city |

They are **town markers for the website map**, which is entirely correct for that purpose
and unusable as assessment coordinates. The mask was verified against six ground-truth
points (three open-sea basins returning plausible depths — Bornholm 97 m, Baltic Proper
69 m, Arkona 47 m — and three inland points returning NaN) before this was believed.

This failed **silently and expensively**. Feeding an all-NaN forcing series to
`solve_ivp` does not raise: it spins on a NaN derivative until the step size underflows.
The first run of the section 10.2 comparison ran for over two minutes at 101% CPU
producing nothing, and looked like a stiff-ODE performance problem rather than a data
problem. **Package D must validate the forcing series before integrating**, and
`GriddedForcing` needs the valid-fraction test as a precondition, not a diagnostic.

### The obvious workaround is biased, which matters more

Snapping to the nearest sea cell is what any implementation would do. It systematically
selects the **shallowest, most enclosed, most river-influenced** water available, because
that is what lies closest to a town:

| Site | Model depth at nearest sea cell | Median DIN | Salinity | Character |
|---|---|---|---|---|
| DK | **3.1 m** | 112 µmol/L | 12.3 psu | Kerteminde Fjord — eutrophic, enclosed |
| DE | — | 8 µmol/L | 10.6 psu | Warnow mouth |
| PL | 7.6 m | 6.8 µmol/L | 6.5 psu | open coast — the only realistic one |
| LT | 4.1 m | 36 µmol/L | **3.5 psu** | Curonian Lagoon, across the spit |

The Lithuanian cell is near-fresh and hypernutrified by the Nemunas; the Danish cell is
3 m deep. Neither is where a farm goes. **Nearest-cell snapping is not merely imprecise,
it is biased toward the least representative water in the domain**, and every number in
section 4 below inherits that bias.

---

## 3. Valid-cell fractions — evidence for the 60% threshold

Section 6.2 sets a minimum valid fraction of 60% and says plainly the number is assumed.
Fraction of non-land cells in a buffer round each published pilot coordinate:

| Pilot | r = 1 km | r = 2 km | r = 5 km |
|---|---|---|---|
| Denmark | 0% | 0% | 20.8% |
| Germany | 0% | 0% | 0% |
| Poland | 0% | 0% | 29.2% |
| Lithuania | 0% | 0% | 25.0% |

At native resolution a 1 km buffer contains **one cell**, so the fraction is 0% or 100%
with nothing in between — the threshold cannot discriminate at that scale. The
distribution only becomes informative at r ≥ 5 km, where all four sit at **0–29%**,
far below 60%.

**The 60% threshold is doing the right thing here**: it rejects all four published
coordinates, which is correct, because they are on land. What this measurement *cannot*
do is calibrate the threshold, because none of these are real farm sites. **Recommend
retaining 60% as the working value and re-measuring once genuine siting polygons exist**
— the number should be set against sites someone would actually farm, not against town
centres. Note also that the threshold interacts with resolution: at 7.4 km a 5 km buffer
samples one or two cells, so the fraction is near-binary again.

---

## 4. Is monthly forcing sufficient for the biology?

Section 10.2 asks for this measurement explicitly, and gives the reason: the growth model
has one state variable and no nutrient reserve pool, so it cannot buffer short-term
variability.

Method: `simulate()` driven twice over the same cultivation window from the same cell,
once with daily reanalysis and once with monthly means interpolated back to daily
(linear on day-of-year, wrapping at the year boundary per section 6.2). 2024, surface
level, four sites × four macroalgae.

**PAR is held identical in both arms.** Section 10.2 asks for daily-vs-monthly "DIN and
PAR", but Copernicus has no PAR (section 1), so it cannot vary. Holding it fixed isolates
the variable actually under test; it also means this measurement says nothing about PAR
smoothing.

| Site | *Chorda* | *Fucus* | *Ulva* | (*Saccharina* is tier-D blocked at all four) |
|---|---|---|---|---|
| DK | +0.28% | −2.22% | −6.70% | |
| DE | +3.03% | +14.97% | −3.96% | |
| PL | **+68.53%** | +21.45% | +12.20% | |
| LT | *blocked* | *blocked* | −6.93% | |

**Across reportable species × sites (n = 10): mean |Δ| 14.0%, maximum 68.5%.**

### What this does and does not establish

**Monthly forcing is not safely sufficient.** A 68% difference in final biomass is far
beyond any reasonable tolerance for a tool that reports yields to prospective farmers.
Even the mean of 14% exceeds the ~2% phase residual the calendar-day indexing work was
concerned with.

**But this is an upper bound, and a soft one.** Every cell measured is biased toward high
variability by the snapping problem of section 2. A genuine offshore farm site would see
smoother nutrient forcing and a smaller delta. The single realistic cell (PL, 7.6 m, open
coast, median DIN 6.8 µmol/L) nonetheless shows +68.5% for *Chorda* — the largest in the
set — so "it is only the enclosed cells" is **not** supported by this data.

Worth stating plainly: *Chorda*'s parameters are a structural analogue of *Fucus*, assumed
rather than fitted, tier C in every region. Its sensitivity to forcing resolution is
therefore a property of an assumed parameter set. The *Fucus* and *Ulva* numbers
(−6.7% to +21.5%) are the more defensible half of this result.

---

## 5. Artifact size and format

Measured on the South Baltic footprint (8–23 °E, 53–58 °N; 300 × 503 cells at native
resolution), float32, real data. Extrapolation model, stated so it can be disagreed with:
7 monthly variables × 12 bands + 3 static bands = **87 two-dimensional fields**.

| Resolution | Cells | NetCDF4 (zlib-5) | Zarr | Full artifact (NetCDF) | % of Zenodo 50 GB |
|---|---|---|---|---|---|
| 1.86 km (native) | 300 × 503 | 178.5 KB/field | 220.9 KB/field | **15.2 MB** | 0.030% |
| 3.71 km (×2) | 150 × 251 | 60.7 KB/field | 64.0 KB/field | 5.2 MB | 0.010% |
| 7.42 km (×4) | 75 × 125 | 27.7 KB/field | 22.5 KB/field | 2.4 MB | 0.005% |

**Size does not constrain the choice.** The design doc treats Zenodo's 50 GB per-file
limit as a bound on the resolution decision; the full artifact at native resolution is
**15 MB**, three orders of magnitude below it. The constraint is real but not binding,
and the resolution decision is therefore free to rest on the valid-cell fractions.

### Decisions

**Resolution: native, 1.86 km.** Nothing argues for coarsening. Size is irrelevant at this
scale, and section 2 shows the sites of interest are close enough to shore that every
coarsening step makes the land-sea discrimination worse — at 7.4 km a 5 km buffer is one
or two cells.

**Format: NetCDF4 with zlib.** Smaller than Zarr at both resolutions that matter (15.2 vs
18.8 MB at native), and — the decisive point — it is **one file**. Zarr is a directory
tree, which must be zipped to archive under a DOI, which means the archived artifact is
not the artifact the tool reads. For a deposit meant to be retrievable in 2034 by someone
who is not us, one self-describing file beats a directory that needs reassembly. Zarr's
chunked partial reads would matter at 50 GB; they do not at 15 MB.

**Cost to state: package D adds one runtime dependency.** The core's four packages
(numpy, scipy, pydantic, pyyaml) do not include a NetCDF reader. `netCDF4` or `h5netcdf`
must join them — modest, but it is a change to the premise that the runtime is four
packages, and it belongs in D's PR description rather than being discovered there.

---

## 6. What this note does not settle

- **The valid-fraction threshold** cannot be calibrated without real siting polygons.
- **PAR and Kd** have no source. `zsd` → Kd needs a named relation and its error budget.
- **The daily/monthly delta** is measured at biased cells; it should be re-measured once
  real farm coordinates exist. The decision it supports (do not assume monthly is safe)
  is robust to that bias, since the bias inflates rather than conceals the effect.
- **Waves** were not pulled. `cmems_mod_bal_wav_my_PT1H-i` is hourly, so the monthly-95th-
  percentile and annual-maximum statistics of section 6.1 are a much heavier extraction
  than anything measured here, and belong in package C's sizing.
- **Redistribution rights** (section 10.2's first assumption) were not checked.

## 7. Recommendation to the project, outside package B

The four pilot coordinates in `data/pilots.yaml` should either gain a companion field
carrying an actual marine siting coordinate, or the DST must never consume them. As they
stand they are correct for a map and wrong for an assessment, and nothing in either
repository currently records that distinction.
