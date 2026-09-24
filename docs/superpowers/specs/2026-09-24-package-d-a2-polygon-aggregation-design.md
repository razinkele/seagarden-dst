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
   session a nutrient scenario makes `daily_forcing` raise a plain `ValueError`.
   D§9 item 3 recorded that `assess_site` contained this as an exclusion; since
   `d3ed04b` only `ForcingUnavailable` excludes a species, so today the eutropy path
   **crashes `assess_site`** for any species that reaches the growth model. After this
   package the cells travel on the object, so `dataclasses.replace` preserves them and
   the side table is gone.
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
    #: The (row, col) artifact cells these conditions were averaged over, as plain
    #: Python ints, row-major. Exactly one cell under CONTAINING_CELL; two or more
    #: under UNWEIGHTED_MEAN (§3.2 labels by the number of VALID cells). A
    #: reader-specific index, which is why it is not on the core type.
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
shapely lives in the `spatial` extra, and `tests/test_gridded_isolation.py` already names
it among the imports only this file may make. Nothing outside `gridded.py` imports it.

**Import scope: function-local, never module-level.** `gridded.py` keeps xarray under
`TYPE_CHECKING` and imports it inside `from_directory` because `app/app.py` imports
`select_forcing` at module scope and `tests/test_select_forcing.py` runs in the default
selection on an install with no spatial extra. shapely follows the same rule: imported
inside `from_directory` beside xarray, so a missing shapely surfaces through
`select_forcing`'s existing `ImportError` row, and imported function-locally wherever
WKT is parsed. A module-level `import shapely` turns the `[app,dev]` CI job red at
collection, the failure D§2 recounts from 2026-09-17.

Accepted geometries: a non-empty `POINT` or `POLYGON`. Anything else raises
`ValueError(f"could not parse site geometry WKT {wkt!r}")`, as today. That guarantee does
not come free from shapely: `from_wkt("")` and `from_wkt("garbage")` raise
`shapely.errors.GEOSException`, which is a `ShapelyError`, **not** a `ValueError`; and
`from_wkt("POLYGON EMPTY")` succeeds and returns an empty geometry whose centroid has no
coordinates. So the parser wraps: `except shapely.errors.ShapelyError as exc: raise
ValueError(...) from exc`, and rejects `geom.is_empty` and any geometry type other than
`Point`/`Polygon` with the same `ValueError`.

### 3.2 Cell selection

Two sets are computed for a polygon: **inside**, the cells whose centres
`shapely.contains_xy` places in the polygon; and the **anchor**, the cell nearest the
polygon's centroid (`_nearest_index`, the same per-axis argmin a POINT uses). The anchor
decides coverage (§3.3). The label is decided by the number of **valid** cells that will
be averaged, never by the number of cells inside — so a one-tuple never carries the
`UNWEIGHTED_MEAN` label.

| Geometry | Inside | Valid inside | `aggregation` | `cells` | `valid_fraction` |
|---|---|---|---|---|---|
| POINT | — | — | `CONTAINING_CELL` | `(anchor,)` | `None` |
| POLYGON | 0 or 1 | — | `CONTAINING_CELL` | `(anchor,)` | `None` |
| POLYGON | ≥ 2 | 0 or 1 | `CONTAINING_CELL` | `(anchor,)` | valid inside ÷ inside |
| POLYGON | ≥ 2 | ≥ 2 | `UNWEIGHTED_MEAN` | the valid cells among those inside, row-major | valid inside ÷ inside |

Rows 3 and 4 apply only once the anchor has passed §3.3; a blocked reading carries
`aggregation=CONTAINING_CELL` (the anchor decided it), `conditions=None`, and, when
inside ≥ 2, the fraction. A concave polygon whose centroid-nearest cell is not itself
inside still uses that cell as the anchor for coverage; if the anchor is valid and ≥ 2
inside cells are valid, the average is over the inside cells only (the anchor is not
added). This case is stated so the plan does not guess it; it is not tested, because
the 3×3 fixture cannot express a concave polygon that spans it.

A farm-scale polygon at native resolution is 59× narrower than a cell (§6.2), so it
usually contains no centre at all; the anchor is then the containing cell and the label
is true.

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

Two consequences, stated so they are not rediscovered:

- **PAR is derived from the averaged `light_attenuation_k`**, because `daily_forcing`
  computes it as `site.par_at_depth()` and the site carries the cell-mean *k*. The mean
  of per-cell `exp(-k_i z)` is not `exp(-mean(k) z)`; on the fixture the two differ by
  about 0.35 %. This is field-mean-first applied consistently, not a defect, and test 6
  therefore checks `temp` and `din` (where `np.interp` is linear in its values) and
  not `par`.
- **Cast to float64 before any reduction.** The artifact stores float32; today's
  `_conditions_at` casts each slice to float64 before `np.mean`. A month-mean taken in
  float32 over cells would not be exact, so the new code casts first, and for a single
  cell the two orders then coincide: `CONTAINING_CELL` readings are byte-identical to
  today's. Cell indices are cast to plain `int` so `cells == ((1, 1),)` holds by value
  and no numpy scalar type leaks into the field.

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
  five points reach the reader, all inside the Baltic domain, so the hazard is
  unreachable; E-b's drawn geometry makes it reachable. **Owner: E-b**, recorded there
  when its design is written.

## 5 Testing

All new tests carry the `spatial` mark and live in `tests/test_gridded.py`, because
CI's `[app,dev]` job has no xarray and `tests/test_assess_with_artifact.py` is, by its
own docstring, a default-selection file that never opens the fixture. The committed
3×3 fixture — latitudes 54.000/54.0167/54.0333, longitudes 20.000/20.0278/20.0556, years
2024–2025, only `[0,0]` invalid — supports tests 1–7 without modification. **Its data
fields are `rng.random` in [0, 1)**, salinity included, so every shipped species is
contraindicated on it (`tolerance_floor_psu` is 2.5 psu or more) and nothing reaches
`daily_forcing` through `assess_site`; test 8 therefore builds a copy.

Polygons are given as WKT `(lon lat)` pairs. The reviewer of this design verified each
one's inside set and anchor against the fixture; the plan uses these coordinates, not
new ones.

1. **The discriminating test, written first.** `replace(reading.conditions,
   din_umol_l=…, dip_umol_l=…)` then `daily_forcing` returns a finite series. Fails today
   with "produced by this GriddedForcing instance". A plain `SiteConditions` with the same
   numbers still raises that message.
2. A POINT read at centre `[1,1]` is unchanged: `CONTAINING_CELL`, `valid_fraction is
   None`, `conditions.cells == ((1, 1),)`, and every field equals the value computed
   directly from the dataset the way today's `_conditions_at` computes it.
3. `POLYGON ((19.99 53.99, 20.07 53.99, 20.07 54.05, 19.99 54.05, 19.99 53.99))`
   encloses all nine centres; centroid (20.03, 54.02) → anchor `[1,1]`:
   `UNWEIGHTED_MEAN`, `valid_fraction == 8/9`, `cells` has eight entries without
   `(0, 0)`, `salinity_psu` equals the mean over those eight cells computed directly from
   the dataset in float64.
4. `POLYGON ((19.995 53.995, 20.035 53.995, 19.995 54.025, 19.995 53.995))` encloses
   exactly `[0,0]`, `[0,1]`, `[1,0]`; centroid (20.008, 54.005) → anchor `[0,0]`:
   `CELL_INVALID`, `nearest_valid_km > 0`, `valid_fraction == 2/3`,
   `aggregation is CONTAINING_CELL`, `conditions is None`.
5. `POLYGON ((20.038 54.020, 20.043 54.020, 20.043 54.025, 20.038 54.025, 20.038
   54.020))`, smaller than a cell with no centre inside; anchor `[1,1]`:
   `CONTAINING_CELL`, `valid_fraction is None`, `cells == ((1, 1),)`. (A sub-cell square
   at 20.010–20.015 × 54.005–54.010 would anchor on `[0,0]` and block, which is why
   the coordinates are pinned.)
6. `POLYGON ((19.99 53.99, 20.04 53.99, 20.04 54.008, 19.99 54.008, 19.99 53.99))`
   encloses `[0,0]` and `[0,1]`; centroid (20.015, 53.999) → anchor `[0,1]`, valid: one
   valid cell inside → `CONTAINING_CELL`, `cells == ((0, 1),)`, `valid_fraction == 0.5`.
   Pins §3.2 row 3, the case where the label follows the valid count.
7. `daily_forcing` for test 3's polygon: `temp` and `din` equal the elementwise mean of
   the eight single-cell series (field-mean-first, pinned); `par` is not compared
   (§3.4).
8. **The D§9 item 3 symptom at the level a user meets it.** Copy the fixture to
   `tmp_path`, add 7.0 to `salinity_psu`, `_restamp` it (as
   `test_a_land_cell_with_nan_blocks_rather_than_raising` does), build a `SiteContext`
   from a POINT read at `[1,1]`, and call `assess_site(context, forcing=reader,
   year=2024, eutropy={"din_umol_l": 5.0, "dip_umol_l": 0.5})`. It **returns** — today
   it raises `ValueError` out of the reader — and `excluded` holds no entry containing
   "GriddedForcing". Whether any species is *reportable* on random forcing is not
   asserted; the defect is the crash.
9. Regression guard, not a discriminator (today's regex already raises): `""`,
   `"garbage"`, `"POLYGON EMPTY"` and a `MULTIPOLYGON` each raise `ValueError` whose
   message names the WKT. With shapely underneath, this is what forces the wrapping in
   §3.1.

Existing guards that must pass unchanged: `test_gridded_isolation.py`, the app's
module-scope import tests, `tests/test_select_forcing.py` in the default selection (no
spatial extra), and every test in `test_gridded.py` today.

## 6 Done-when

1. Tests 1–9 above pass under `pytest -m spatial tests/`; the default selection (which
   must still import `gridded` without shapely or xarray) and ruff are clean.
2. `Aggregation.UNWEIGHTED_MEAN` is produced by `reading_at` (test 3), not merely defined.
3. `grep -n _site_cells src/` returns nothing, and `grep -n "^import shapely\|^from
   shapely" src/seagarden_dst/gridded.py` returns nothing.
4. `SiteQuery`'s docstring no longer promises the empty-string convention.
5. The D-a design carries a dated note that D§9 items 1, 2 and 3 are resolved by this
   package, naming the file, and correcting item 3's symptom: since `d3ed04b` the eutropy
   path crashed `assess_site` rather than excluding species.
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
