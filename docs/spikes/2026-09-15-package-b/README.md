# Package B spike scripts — 2026-09-15

Throwaway measurement code, committed so the numbers in
[`../../2026-09-15-package-b-resolution-and-format.md`](../../2026-09-15-package-b-resolution-and-format.md)
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
