# Package B spike scripts — 2026-09-15

Throwaway measurement code, committed so the numbers in
[`../../2026-09-15-package-b-measurements.md`](../../2026-09-15-package-b-measurements.md)
can be reproduced. **This is not production code** and nothing in the package imports it.

Run in order; each writes into a `data/` directory beside itself. Needs the `spatial`
extra and a Copernicus Marine login (`copernicusmarine login`).

| Script | What it produces |
|---|---|
| `01_inspect.py` | Variable lists, grids and time extents for five datasets. No download. |
| `02_download_cell.py` | One cell, one year, daily + monthly, for the first section-10.2 run |
| `04_download_grid.py` | South Baltic footprint, one month + static mask, for the size sweep |
| `05_valid_cells.py` | Land-sea check on the four pilots; valid-cell fractions by radius and resolution |
| `06_download_sites.py` | Daily + monthly at each pilot's nearest sea cell |
| `07_format_sweep.py` | Bytes per 2-D field at three resolutions × NetCDF/Zarr |
| `08_sites_daily_vs_monthly.py` | The section-10.2 comparison across all four sites |

Two bugs were found and fixed *in these scripts* while running them, both of a kind
package D will have to avoid:

- `02`/`03` selected the nearest cell by coordinate, which is a **land** cell at every
  pilot, giving an all-NaN series that makes `solve_ivp` spin rather than raise.
- `08` initially took `np.where(valid)[0][0]`, which is the south-west corner of the
  box rather than the nearest valid cell — it put the Danish site in a brackish fjord
  (11.9 psu, DIN to 805 µmol/L) instead of near the Great Belt.

## Notes on this copy

These scripts ran from a working directory, not from a checkout, and two details of
that survive here:

- `03` is referenced in the bug note above but was never committed; only the seven
  scripts in the table above exist. What it did is recorded only in its effect on `02`.
- `05_valid_cells.py` reads `pilots.yaml` from the **website** repository, and assumes
  it is checked out as `seagarden/` beside this one. That is deliberate: the finding was
  that the *published* pilot coordinates are land cells, so the script has to read the
  published file rather than a copy kept here.

Paths were made checkout-relative when the scripts landed; they resolved to the same
files on the machine that produced the numbers. Nothing else about their behaviour
changed — see the two commits on this branch for the exact difference.
