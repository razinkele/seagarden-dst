# Package D-a2 — Polygon Aggregation and the Cell Handle

**Status:** design, 2026-09-24. Binding authority above it:
`docs/superpowers/specs/2026-09-13-dst-data-layer-design.md` (§6.2, §7, §8 row D),
`docs/superpowers/specs/2026-09-17-package-d-a-artifact-reader-design.md` (D§2, D§4, D§9)
and `docs/superpowers/specs/2026-09-22-package-e-a-forcing-selection-design.md` (E§1,
E§10 item 3). This is the "D-a follow-up between E-a and E-b" that E§1 names.

## 1 What this package is, and what it is not

D§9 recorded two claims the artifact reader made and did not implement, and one defect
found on the way out of E-a. This package closes all three, plus the one gap (§3.6)
that closing the third exposes, and nothing else:

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

Closing the crash exposes a second gap, which this package also owns (§3.6): the
gridded daily series read DIN from the artifact's monthly field and never from the
site, so a nutrient scenario would have reached the annual fields and the report's
caveat but not the term that drives macroalgal growth.

Four decisions taken with the user on 2026-09-24:

| Question | Decision | Why |
|---|---|---|
| A multi-cell polygon with some valid cells but an invalid cell under its centroid: block or assess? | **Block**, `CELL_INVALID` with the distance, the fraction still reported. | §6.2 rule (1) — the containing cell decides coverage — and §7 row 2 key off it. D-b sets the fraction threshold; relaxing "is there data here" to "is there data somewhere in here" before any threshold exists would be the unmarked fallback §7 forbids. |
| A per-process reader cache, now that the id() hazard is gone? | **Out.** | E§10 item 3 says the fix *gates* a cache, not that this package includes one. A shared reader raises thread-safety and invalidation questions (a refresh replacing the pair under a running server) that deserve their own design. |
| How does a nutrient scenario reach the gridded daily series? | **Scale the cell-mean monthly DIN by `site.din_umol_l` ÷ the cell-mean annual DIN** (§3.6). | The same *shape* of mechanism as the placeholder, which multiplies a seasonal factor by the site value (`forcing.py`, `din = site.din_umol_l * (1.0 - 0.55 * season)`). Keeps the seasonal drawdown the artifact exists to carry; a flat replacement would discard it, and leaving it out would make the report's "nutrients were overridden by a scenario" false for the growth model. |
| What does `din_umol_l` *mean* on the artifact path? Today it carries three meanings: the placeholder's series peaks at the site value (its annual mean is ≈ 0.725 × `din_umol_l`), `_conditions_at` sets it to the 12-month mean, and the EUTROPY adapter says its Nemunas tables are **summer-month** DIN. | **The 12-month mean, documented.** The adapter's docstring is amended to say a scenario's `din_umol_l` is taken as an annual mean and that the MARBEFES summer-month tables need converting before use. The placeholder's peak semantics is recorded as a known asymmetry, owner **D1** (re-parameterisation against real forcing). | Smallest honest change: nothing about the placeholder moves, the ratio stays 1.0 for an unmodified site with no branch, and the number the growth model integrates has a stated meaning. Scaling to a summer mean instead would need a "was it replaced" flag; deferring would leave the meaning unstated while the model integrates it. |

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
`select_forcing`'s existing `ImportError` row — whose reason text is widened from
"(xarray/h5netcdf)" to "(xarray/h5netcdf/shapely)" — and imported function-locally
wherever WKT is parsed. A module-level `import shapely` turns the `[app,dev]` CI job red
at collection, the failure D§2 recounts from 2026-09-17. `tests/test_select_forcing.py`
gains a default-selection sibling of its existing "without the spatial stack" test that
blanks `sys.modules["shapely"]` alone, since shapely is installed in every environment
this project runs tests in and a grep (done-when 3) is not a test.

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

Rows 3 and 4 apply only once the anchor has passed §3.3; a blocked reading — either
`YEAR_ABSENT` or `CELL_INVALID` — carries `aggregation=CONTAINING_CELL` (the anchor
decided it), `conditions=None`, and, when inside ≥ 2, the fraction (`valid` has no year
axis, so it is computable under both blocks and one rule serves). A concave polygon
whose centroid-nearest cell is not itself inside still uses that cell as the anchor for
coverage; if the anchor is valid and ≥ 2 inside cells are valid, the average is over
the inside cells only (the anchor is not added). Test 10 pins this on a U-shaped polygon.

A farm-scale polygon at native resolution is 59× narrower than a cell (§6.2), so it
usually contains no centre at all; the anchor is then the containing cell and the label
is true.

### 3.3 Coverage, in order

1. `query.year` not in the artifact → `YEAR_ABSENT`, `conditions=None`. Unchanged.
2. The anchor cell's `valid` is false → `CELL_INVALID`, `conditions=None`,
   `nearest_valid_km` from the anchor. Read from `valid` by value, never inferred from
   NaN, as today. Under both blocks, when inside ≥ 2, `valid_fraction` is still set so a
   caller can see how much of the polygon had data.
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
- **Cast to float64 before any reduction, through one helper, by construction.** The
  artifact stores float32; today `_conditions_at` casts with `np.asarray(...,
  dtype=float)` while `_interpolated_monthly` reads float32 scalars into a list — two
  routes, and a denominator taken by the second route gives a ratio of
  0.9999999547944994, not 1.0 (§3.6). So the new code has exactly one reader of the
  per-year monthly fields:

      _cell_mean_monthly(name, year, cells) -> np.ndarray   # shape (12,), float64

  which takes the `(12, n_cells)` block, casts to float64, and returns
  `np.mean(block, axis=1)`. `_conditions_at` derives every annual statistic from its
  output (`np.mean`, `np.max`, `np.min` over the 12 values); `daily_forcing` takes both
  its series values and its §3.6 denominator from it; the wave and depth fields use
  the same cast-then-`np.mean(axis=…)` shape. For one cell the cell-mean is the
  identity on a float64 vector and the month reduction is the call today's code makes,
  so `CONTAINING_CELL` readings are bit-identical to today's and test 2 may assert
  exact equality. Multi-cell values depend on numpy's summation order, so tests 3, 7
  and 10 assert with `np.allclose` at `rtol=1e-12`, not `==`. Cell indices are cast to
  plain `int` for hashing and serialisation hygiene (a numpy scalar compares equal but
  is not a Python int).

`surface_par` remains `PLACEHOLDER_SURFACE_PAR` (C§3.3). `region` is the query's.

### 3.5 `SiteReading.valid_fraction`

```python
#: On a POLYGON read with two or more cell centres inside it: valid cells ÷ cells
#: inside, whatever `aggregation` says and whether or not coverage blocked. None on a
#: POINT read, or on a POLYGON with fewer than two centres inside. Surfaced with no
#: threshold; §6.2 (3) leaves the threshold to package D-b.
valid_fraction: float | None = None
```

Not threaded to `SiteContext` or the UI. Until E-b draws, nothing in the app can produce
a polygon, and a field nobody can populate is a field nobody can test.

### 3.6 The daily DIN honours the site's annual value

`daily_forcing` builds its DIN series as: the cell-mean monthly `din_umol_l` for the
months the window needs (Y, and Y+1 for a wrapping window, exactly as today), multiplied
by one ratio

    ratio = site.din_umol_l / mean over the 12 months of year Y of the cell-mean din_umol_l

before interpolation. Temperature is not scaled; nothing else in the series changes.

- **For an unmodified site the ratio is exactly 1.0**, because `site.din_umol_l` and
  the denominator are both `np.mean` of the same `_cell_mean_monthly` output (§3.4),
  and `x / x == 1.0` in IEEE arithmetic for finite non-zero `x`. Multiplying by 1.0 is
  the identity, so every existing series is bit-identical and test 2's exact equality
  still holds. There is no `isinstance`/"was it replaced" branch: the contract is that
  the 12-month mean of the scaled monthly field for year Y equals `site.din_umol_l`.
  (The *series* mean over a window is not that number — `np.interp` between mid-month
  knots over a partial year does not preserve it — and is not claimed.)
- **The denominator is Y's annual mean, not the window's**, because on the artifact
  path `din_umol_l` *is* the 12-month mean (§1, decision 4) and a scenario value is
  taken as one. The `eutropy_adapter` module and `apply_nutrient_scenario` docstrings
  are amended in this package to say so, and to say that the MARBEFES ensemble's
  summer-month tables (`scenario_from_ensemble`) must be converted to an annual mean
  before they are passed in — a conversion this package does not perform. The
  placeholder's series still *peaks* at `din_umol_l` (its annual mean is about 0.725 ×
  the value), so the same scenario dict means somewhat different water on the two
  sources; recorded in the CHANGELOG as a known asymmetry owned by D1, which is where
  the placeholder's nutrient shape is re-fitted against real forcing. The Y+1 months of
  a wrapping window are scaled by the same ratio.
- **A zero annual mean in the artifact is a data defect**, not a domain refusal: raise
  `ValueError` naming the cells. Not `ForcingUnavailable`, because that would quietly
  exclude the species (`d3ed04b`'s rule). This is a deliberate change from today, where
  an all-zero DIN year returns a finite zero series and grows nothing; a cell reporting
  no nitrogen for twelve months is a masking or unit defect, not a measurement. A
  non-finite mean needs no guard: `SiteConditions.__post_init__` already refuses it at
  construction from the same block. The committed fixture's DIN minimum is 0.0073, so
  the zero branch is stated, not tested.
- The report's existing caveat ("Nutrient concentrations were overridden by a
  scenario; other conditions are unchanged", `api.py`) becomes true on an artifact
  session without a wording change.

## 4 What D-a2 does not do

- **No fraction threshold, no salinity weighting** — D-b, with its Tagalaht validation.
- **No per-process cache** — decided out (§1).
- **No drawing, no GeoJSON, no UI change** — E-b. `app/` is untouched.
- **No guard against a query far outside the grid.** `_nearest_index` returns the nearest
  edge cell for a point 500 km away, with no complaint. Today only `SITE_COORDINATES`'
  five points reach the reader, all inside the Baltic domain, so the hazard is
  unreachable; E-b's drawn geometry makes it reachable. **Owner: E-b**, written into
  E-b's row of the data-layer design §8 by this package (done-when 6), not left for a
  document that does not yet exist.

## 5 Testing

All new tests carry the `spatial` mark and live in `tests/test_gridded.py`, because
CI's `[app,dev]` job has no xarray and `tests/test_assess_with_artifact.py` is, by its
own docstring, a default-selection file that never opens the fixture. The committed
3×3 fixture — latitudes 54.000/54.0167/54.0333, longitudes 20.000/20.0278/20.0556, years
2024–2025, only `[0,0]` invalid — supports tests 1–7 without modification. **Its data
fields are `rng.random` in [0, 1)**, salinity included, so every shipped species is
contraindicated on it (`tolerance_floor_psu` is 2.5 psu or more) and nothing reaches
`daily_forcing` through `assess_site`; test 8 therefore builds a copy.

Polygons are given as WKT `(lon lat)` pairs. Three review cycles verified each one's
inside set, centroid and anchor against the fixture by script (`shapely.contains_xy`
over the centres, per-axis argmin for the anchor); the plan uses these coordinates,
not new ones.

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
   "GriddedForcing". One contraindication entry **is** expected: at 7–8 psu
   *Saccharina* (floor 16 psu) stays excluded with its floor note, and the plan must not
   "fix" that. Whether any species is *reportable* on random forcing is not asserted;
   the defect is the crash.
9. Regression guard, not a discriminator (today's regex already raises): `""`,
   `"garbage"`, `"POLYGON EMPTY"` and a `MULTIPOLYGON` each raise `ValueError` whose
   message names the WKT. With shapely underneath, this is what forces the wrapping in
   §3.1.
10. `POLYGON ((19.99 53.99, 20.07 53.99, 20.07 54.05, 20.045 54.05, 20.045 54.008,
    20.015 54.008, 20.015 54.05, 19.99 54.05, 19.99 53.99))`, a U shape whose notch
    (lon 20.015–20.045, lat 54.008–54.05) excludes both `[1,1]` and `[2,1]`: seven
    centres inside, centroid (20.030, 54.017) → anchor `[1,1]`, valid and **not**
    inside: `UNWEIGHTED_MEAN`, `valid_fraction == 6/7`, and `cells` is exactly
    `((0, 1), (0, 2), (1, 0), (1, 2), (2, 0), (2, 2))`. The one case that exercises the
    anchor rule, the label rule and the anchor's exclusion from `cells` at once.
11. **§3.6, pinned.** From a POINT read at `[1,1]` for 2024, `replace(conditions,
    din_umol_l=2.0 * conditions.din_umol_l)`; the `din` series from `daily_forcing`
    over `(4, 9)` is `np.allclose` to twice the unmodified series (`rtol=1e-12`), and
    the `temp` series is unchanged. A second assertion on the *unmodified* site: its
    `din` series is `array_equal` to the one today's code returns (computed in the
    test the way today's `_interpolated_monthly` does), pinning the ratio's exact 1.0.

Existing guards that must pass unchanged: `test_gridded_isolation.py`, the app's
module-scope import tests, `tests/test_select_forcing.py` in the default selection (no
spatial extra), and every test in `test_gridded.py` today.

## 6 Done-when

1. Tests 1–11 above pass under `pytest -m spatial tests/`; the default selection (which
   must still import `gridded` without shapely or xarray, and now tests the shapely
   half of that) and ruff are clean.
2. `Aggregation.UNWEIGHTED_MEAN` is produced by `reading_at` (test 3), not merely defined.
3. `grep -n _site_cells src/` returns nothing, and `grep -n "^import shapely\|^from
   shapely" src/seagarden_dst/gridded.py` returns nothing.
4. `SiteQuery`'s docstring no longer promises the empty-string convention.
5. The D-a design carries a dated note that D§9 items 1, 2 and 3 are resolved by this
   package, naming the file, and correcting item 3's symptom: since `d3ed04b` the eutropy
   path crashed `assess_site` rather than excluding species.
6. The data-layer design §8 carries the row split E§9 asked for and this package did not
   find: E-a (done, E§8), D-a2 (this section), E-b (E§1's third bullet), each with its
   done-when or a pointer to it; E-b's row also carries the out-of-grid guard of §4 as
   an owned item.
7. CHANGELOG `[Unreleased]` names the change, the crash it closes and the §3.6 DIN
   scaling (a scenario now reaches the artifact-backed growth model), records the
   placeholder-peak versus artifact-mean asymmetry of `din_umol_l` as a known limit
   owned by D1, and says the
   id() hazard 0.10.0's known-limit paragraph cites is gone while the per-process cache
   stays out pending its own design — so that paragraph no longer reads as still
   blocked.

## 7 Amendments this design requires

- **D-a design** (`2026-09-17-package-d-a-artifact-reader-design.md`): a dated resolution
  note under D§9.
- **Data-layer design §8**: the row split. Not a new obligation — E§9 recorded it on
  2026-09-22 and it was never applied. E-b's row gains the out-of-grid guard (§4).
- **`forcing.py`**: `SiteQuery` docstring; `SiteReading.valid_fraction`.
- **`eutropy_adapter.py`**: module and `apply_nutrient_scenario` docstrings state that
  `din_umol_l`/`dip_umol_l` are annual means on the artifact path and that the
  summer-month ensemble tables need converting first (§3.6). No behaviour change.
