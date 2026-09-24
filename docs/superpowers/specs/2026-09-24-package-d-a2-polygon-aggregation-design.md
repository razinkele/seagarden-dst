# Package D-a2 — Polygon Aggregation and the Cell Handle

**Status:** design, 2026-09-24. Binding authority above it:
`docs/superpowers/specs/2026-09-13-dst-data-layer-design.md` (§6.2, §7, §8 row D),
`docs/superpowers/specs/2026-09-17-package-d-a-artifact-reader-design.md` (D§2, D§4, D§9)
and `docs/superpowers/specs/2026-09-22-package-e-a-forcing-selection-design.md` (E§1,
E§10 item 3). This is the "D-a follow-up between E-a and E-b" that E§1 names.

## 1 What this package is, and what it is not

D§9 recorded two claims the artifact reader made and did not implement, and one defect
found on the way out of E-a. This package closes all three, and nothing else:

1. **D§4's multi-cell aggregation.** `gridded.GriddedForcing._point_of` reduces a
   `POLYGON` to the mean of its vertices and labels every reading `CONTAINING_CELL`.
   `Aggregation.UNWEIGHTED_MEAN` is defined and never produced. After this package a
   polygon spanning cells is read as the unweighted mean over its valid cells, labelled
   as such, with the valid fraction on the reading.
2. **The `id()`-keyed cell map (D§9 item 3).** `reading_at` remembers which cell produced
   a `SiteConditions` in `_site_cells[id(conditions)]`. `eutropy_adapter` builds a
   *replaced* `SiteConditions` the reader has never seen, so on an artifact-backed
   session a nutrient scenario makes `daily_forcing` raise and every ODE species is
   excluded with the reader's error text. After this package the cells travel on the
   object, so `dataclasses.replace` preserves them and the side table is gone.
3. **D§2's withdrawn empty-geometry convention (D§9 item 2)** still stands in the
   `SiteQuery` docstring. The docstring is corrected; the reader's behaviour (raise) is
   unchanged.

Two decisions taken with the user on 2026-09-24:

| Question | Decision | Why |
|---|---|---|
| A multi-cell polygon with some valid cells but an invalid cell under its centroid: block or assess? | **Block**, `CELL_INVALID` with the distance, the fraction still reported. | §6.2 rule (1) — the containing cell decides coverage — and §7 row 2 key off it. D-b sets the fraction threshold; relaxing "is there data here" to "is there data somewhere in here" before any threshold exists would be the unmarked fallback §7 forbids. |
| A per-process reader cache, now that the id() hazard is gone? | **Out.** | E§10 item 3 says the fix *gates* a cache, not that this package includes one. A shared reader raises thread-safety and invalidation questions (a refresh replacing the pair under a running server) that deserve their own design. |

## 2 The cell handle

**`GriddedConditions`, a frozen dataclass subclass of `SiteConditions`, declared in
`gridded.py`.** It adds one field:

```python
@dataclass(frozen=True)
class GriddedConditions(SiteConditions):
    #: The (row, col) artifact cells these conditions were aggregated over, in the
    #: order they were averaged. One cell for CONTAINING_CELL; two or more for
    #: UNWEIGHTED_MEAN. A reader-specific index, which is why it is not on the core type.
    cells: tuple[tuple[int, int], ...] = ()
```

Why a subclass, and why here:

- `dataclasses.replace` on a subclass instance returns the same subclass with every
  field, `cells` included, so the eutropy path stops being a stranger to the reader.
- `SiteConditions.__post_init__`'s finiteness check filters on `numbers.Real`, so a tuple
  passes through untouched; the guard is inherited, not re-implemented.
- `SiteContext.conditions` is typed `SiteConditions | None` and holds a subclass instance
  without change. `daily_forcing(site, window, year)` keeps its signature, so
  `PlaceholderForcing`, `growth.py`, `api._assess_one` and the app's fake sources are
  untouched.
- It stays out of the core type because a cell index means nothing to the placeholder
  or to any consumer; putting it on `SiteConditions` would leak a reader's internals into
  a type the whole model shares. A protocol change (passing the reading to
  `daily_forcing`) was the third option and touches five modules for no extra benefit.

`_cell_for_site(site)` becomes: `isinstance(site, GriddedConditions)` and `site.cells`
non-empty and every `(row, col)` inside this reader's grid shape; otherwise the same
`ValueError("daily_forcing needs a SiteConditions object produced by this GriddedForcing
instance")` as today. `_site_cells` and the constructor comment about it are deleted.

## 3 Aggregation

### 3.1 Geometry

`gridded.py` parses WKT with `shapely.from_wkt`, replacing the regex and the vertex-mean.
shapely lives in the `spatial` extra, which this module already requires for xarray, and
`tests/test_gridded_isolation.py` already names shapely among the imports only this file
may make. Nothing outside `gridded.py` imports it.

Accepted geometries: `POINT` and `POLYGON`. Anything else — an empty string, a
`MULTIPOLYGON`, unparseable text — raises `ValueError` naming the WKT, as today.

### 3.2 Cell selection

| Geometry | Cells inside | Anchor cell | `aggregation` | `cells` | `valid_fraction` |
|---|---|---|---|---|---|
| POINT | — | nearest centre to the point | `CONTAINING_CELL` | `(anchor,)` | `None` |
| POLYGON | 0 or 1 centre inside | nearest centre to the polygon's centroid | `CONTAINING_CELL` | `(anchor,)` | `None` |
| POLYGON | ≥ 2 centres inside | nearest centre to the polygon's centroid | `UNWEIGHTED_MEAN` | the valid cells among those inside, row-major | valid inside ÷ inside |

"Inside" is `shapely.contains_xy` over the grid of cell centres. A farm-scale polygon at
native resolution is 59× narrower than a cell (§6.2), so it usually contains no centre
at all; the centroid's nearest cell is then the containing cell and the label is true.

### 3.3 Coverage, in order

1. `query.year` not in the artifact → `YEAR_ABSENT`, `conditions=None`. Unchanged.
2. The anchor cell's `valid` is false → `CELL_INVALID`, `conditions=None`,
   `nearest_valid_km` from the anchor. On the multi-cell path `valid_fraction` is still
   set, so a caller can see how much of the polygon had data. Read from `valid` by
   value, never inferred from NaN, as today.
3. Otherwise `VALID`, with `conditions` a `GriddedConditions` over `cells`.

### 3.4 The order of averaging, fixed here

**Average each field across the cells first; derive everything else from the averaged
field.** Concretely, for cells *C*:

- the five per-year monthly fields: for each month, the mean over *C* of that month's
  value; then `salinity_psu`, `mean_temp_c`, `din_umol_l`, `dip_umol_l`,
  `light_attenuation_k` are the mean over months of the cell-mean, `summer_temp_c` the
  max over months of the cell-mean, `winter_temp_c` the min;
- `significant_wave_m`: the cell-mean of each month's p95, then the mean over months;
- `depth_m`: the cell-mean of `depth_mean_m`;
- `daily_forcing`: `_interpolated_monthly` takes the cell-mean of each month before
  interpolating on day-of-year.

Field-mean-first is the only order under which a reading labelled `UNWEIGHTED_MEAN` and
the daily series that grows the crop describe the same site. The alternative — annual
statistics per cell, then averaged — would make `summer_temp_c` the mean of per-cell
maxima while the daily series ran on the cell-mean field, and the two would disagree.
For a single cell the two orders coincide, so `CONTAINING_CELL` readings are
byte-identical to today's.

`surface_par` remains `PLACEHOLDER_SURFACE_PAR` (C§3.3). `region` is the query's.

### 3.5 `SiteReading.valid_fraction`

```python
#: On a polygon read over two or more cells: valid cells ÷ cells whose centres lie
#: inside the polygon. None on a point or single-cell read. Surfaced with no threshold;
#: §6.2 (3) leaves the threshold to package D-b.
valid_fraction: float | None = None
```

Not threaded to `SiteContext` or the UI. Until E-b draws, nothing in the app can produce
a polygon, and a field nobody can populate is a field nobody can test.

## 4 What D-a2 does not do

- **No fraction threshold, no salinity weighting** — D-b, with its Tagalaht validation.
- **No per-process cache** — decided out (§1).
- **No drawing, no GeoJSON, no UI change** — E-b. `app/` is untouched.
- **No guard against a query far outside the grid.** `_nearest_index` returns the nearest
  edge cell for a point 500 km away, with no complaint. Today only `SITE_COORDINATES`'
  seven points reach the reader, all inside the Baltic domain, so the hazard is
  unreachable; E-b's drawn geometry makes it reachable. **Owner: E-b**, recorded there
  when its design is written.

## 5 Testing

All new tests carry the `spatial` mark and live under `tests/`, because CI's `[app,dev]`
job has no xarray. The committed 3×3 fixture (latitudes 54.000/54.017/54.033,
longitudes 20.000/20.028/20.056, years 2024–2025, only `[0,0]` invalid) supports every
case without modification.

`tests/test_gridded.py`:

1. **The discriminating test, written first.** `replace(reading.conditions,
   din_umol_l=…, dip_umol_l=…)` then `daily_forcing` returns a finite series. Fails today
   with "produced by this GriddedForcing instance". A plain `SiteConditions` still raises
   that message.
2. A POINT read is unchanged: `CONTAINING_CELL`, `valid_fraction is None`,
   `conditions.cells == ((1, 1),)`, and the numbers equal today's.
3. A polygon enclosing all nine centres: `UNWEIGHTED_MEAN`, `valid_fraction == 8/9`,
   `cells` has eight entries without `(0, 0)`, `salinity_psu` equals the mean over those
   eight cells computed directly from the dataset.
4. A polygon enclosing `[0,0]`, `[0,1]`, `[1,0]` with its centroid nearest `[0,0]`:
   `CELL_INVALID`, `nearest_valid_km > 0`, `valid_fraction == 2/3`, `conditions is None`.
5. A polygon smaller than a cell, placed between centres: `CONTAINING_CELL`,
   `valid_fraction is None`, one cell.
6. `daily_forcing` for the nine-centre polygon equals the elementwise mean of the eight
   single-cell series — field-mean-first, pinned.
7. Unparseable WKT, an empty string and a `MULTIPOLYGON` each raise `ValueError`.

`tests/test_assess_with_artifact.py`:

8. `assess_site` with a EUTROPY nutrient scenario against a fixture-backed context
   excludes no species for a reader reason; the ODE species assess. This is the D§9
   item 3 symptom at the level a user meets it.

Existing guards that must pass unchanged: `test_gridded_isolation.py`, the app's
module-scope import tests, and every test in `test_gridded.py` today.

## 6 Done-when

1. Tests 1–8 above pass under `pytest -m spatial tests/`; the default selection and ruff
   are clean.
2. `Aggregation.UNWEIGHTED_MEAN` is produced by `reading_at` (test 3), not merely defined.
3. `grep -n _site_cells src/` returns nothing.
4. `SiteQuery`'s docstring no longer promises the empty-string convention.
5. The D-a design carries a dated note that D§9 items 1, 2 and 3 are resolved by this
   package, naming the file.
6. The data-layer design §8 carries the row split E§9 asked for and this package did not
   find: E-a (done, E§8), D-a2 (this section), E-b (E§1's third bullet), each with its
   done-when or a pointer to it.
7. CHANGELOG `[Unreleased]` names the change and the eutropy defect it closes.

## 7 Amendments this design requires

- **D-a design** (`2026-09-17-package-d-a-artifact-reader-design.md`): a dated resolution
  note under D§9.
- **Data-layer design §8**: the row split. Not a new obligation — E§9 recorded it on
  2026-09-22 and it was never applied.
- **`forcing.py`**: `SiteQuery` docstring; `SiteReading.valid_fraction`.
