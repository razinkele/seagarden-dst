# Package D-a2 — Polygon Aggregation and the Cell Handle: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The artifact reader reads a polygon as the unweighted mean over its valid cells, labelled as such with the valid fraction on the reading; the cells travel on the conditions object so a nutrient scenario no longer crashes an artifact-backed assessment; and the daily DIN series honours the site's annual value.

**Architecture:** A frozen `GriddedConditions(SiteConditions)` subclass in `gridded.py` carries `cells` and `year`, replacing the `id()`-keyed side table. One helper, `_cell_mean_monthly`, is the only reader of the per-year monthly fields, so annual statistics, the daily series and the §3.6 DIN denominator share one float64 path. WKT is parsed by shapely, function-locally; a polygon's inside set and centroid-anchor decide the label and the coverage. Nothing under `app/` changes.

**Tech Stack:** Python 3.11/3.13, dataclasses (`kw_only`), numpy, xarray + h5netcdf and shapely 2.x behind the existing lazy imports in `gridded.py`, pytest with the `spatial` mark.

**Spec:** `docs/superpowers/specs/2026-09-24-package-d-a2-polygon-aggregation-design.md` (§1 four decisions, §2 handle, §3.1–§3.6 aggregation, §5 tests 1–12, §6 done-when 1–8, §7 amendments). Above it: data-layer design §6.2, §7, §8; D-a design D§2, D§4, D§9; E-a design E§1, E§9, E§10.

## Global Constraints

- **`gridded.py` imports xarray and shapely only inside functions.** `import xarray` and `import shapely` sit together inside `from_directory` **before `load_pair`** (E§10 item 4); wherever WKT is parsed, shapely is imported inside that function. `grep -n "^import shapely\|^from shapely" src/seagarden_dst/gridded.py` must return nothing. `app/app.py` imports `select_forcing` at module scope on installs with no spatial extra.
- **Nothing outside `gridded.py` and `refresh/` imports xarray, rioxarray or shapely** — `tests/test_gridded_isolation.py` asserts it.
- **Tests that open the fixture carry `@pytest.mark.spatial` and live under `tests/`** (CI's `[app,dev]` job has no xarray; `pyproject.toml` `addopts` deselects `spatial` by default). The one new default-selection test lives in `tests/test_select_forcing.py`.
- **Single-cell readings are bit-identical to today's** (spec §3.4): every per-year monthly field is read through `_cell_mean_monthly` (float64 cast, then `np.mean(block, axis=1)`); annual statistics are `np.mean`/`np.max`/`np.min` over its 12 values. Multi-cell assertions use `np.allclose(..., rtol=1e-12)`; single-cell assertions may use `==`.
- **Only `ForcingUnavailable` excludes a species** (`d3ed04b`). Every new reader refusal in this package is a plain `ValueError` and must fail loudly.
- **`daily_forcing(site, window, year)` keeps its signature.** `PlaceholderForcing`, `growth.py`, `api._assess_one` and the app's fake sources are untouched.
- **Polygon coordinates in tests are the spec's, verbatim** (§5). Do not invent new ones; three review cycles verified these against the fixture.
- **Local runs:** every Python invocation is `MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python ...` (the env's MKL crashes pytest at collection otherwise); pass `-p no:cacheprovider`; ruff at line length 100 (`micromamba run -n shiny ruff check src tests app`); use `tmp_path` for every mutated fixture.
- **Test discrimination standard:** negative tests use `match=` on a fragment unique to the rule; record actual pytest output in the ledger, never the word "verified"; commit before moving on.
- **The working tree is shared with other sessions.** Never stash; never leave work uncommitted between tasks. Never `git add` anything under `.superpowers/`.
- Branch: `package-d-a2-polygon-aggregation` (already exists, holds the spec).

## Shipped interfaces this plan consumes — read, not remembered

| Thing | Fact |
|---|---|
| `SiteConditions` (`forcing.py:38`) | `@dataclass(frozen=True)`; fields `region, salinity_psu, mean_temp_c, summer_temp_c, winter_temp_c, surface_par, din_umol_l, dip_umol_l, depth_m, significant_wave_m, light_attenuation_k=0.4, cultivation_depth_m=1.5`; `__post_init__` refuses non-finite `numbers.Real` fields (a tuple passes); `par_at_depth()` |
| `SiteQuery` (`forcing.py:215`) | frozen: `geometry_wkt: str, year: int, region: str | None = None`; docstring still says an empty string means the region's coordinate (spec done-when 4 removes that sentence) |
| `SiteReading` (`forcing.py:229`) | frozen: `conditions, coverage, year, aggregation, nearest_valid_km=None, from_artifact=False, stale_months=None`; every construction in the codebase is keyword |
| `Coverage`, `Aggregation` (`forcing.py:188`, `:202`) | `VALID/CELL_INVALID/YEAR_ABSENT`; `CONTAINING_CELL/UNWEIGHTED_MEAN/SALINITY_WEIGHTED` |
| `ForcingUnavailable` (`forcing.py:613`) | `ValueError` subclass; the only exception `api.assess_site` turns into an exclusion (`api.py:214-221`) |
| `PLACEHOLDER_SURFACE_PAR`, `day_of_year`, `placeholder_choice`, `ForcingChoice` | already imported by `gridded.py` |
| `GriddedForcing` (`gridded.py:61`) | `__init__(manifest, dataset)` sets `latitudes`, `longitudes` (float arrays), `_years: list[int]`, `_site_cells` (to delete); `from_directory` imports xarray then `load_pair`; `reading_at(query)`; `daily_forcing(site, window, year) -> (days, par, temp, din)`; `_point_of` (regex + vertex mean; to delete); `_nearest_index(lat, lon) -> (int, int)` per-axis argmin; `_nearest_valid_km(row, col)`; `_cell_for_site(site)`; `_interpolated_monthly(name, row, col, month_years, days)`; `_conditions_at(row, col, year, region)` |
| `select_forcing` (`gridded.py:277`) | `except ImportError:` reason `f"this install has no spatial extra (xarray/h5netcdf), so the artifact at {directory} cannot be read"`; `tests/test_select_forcing.py:39` asserts `startswith("this install has no spatial extra")` |
| Artifact variables | `salinity_psu, temp_c, din_umol_l, dip_umol_l, light_attenuation_k` dims `(year, month, latitude, longitude)`; `significant_wave_m` `(month, latitude, longitude)`; `depth_mean_m, depth_min_m, valid` `(latitude, longitude)`; all data float32 |
| Fixture `tests/fixtures/data` | lats `[54.0, 54.016666, 54.033332]`, lons `[20.0, 20.027777, 20.055554]`, years `[2024, 2025]`, `valid` False only at `[0,0]`; every data field `rng.random` in [0, 1); DIN minimum 0.0073 |
| `tests/test_gridded.py` | `FIXTURE = "tests/fixtures/data"`, `_point(lat, lon)`, `reader` fixture, `_restamp(directory)` (recomputes the manifest sha after a mutation); `test_two_years_give_different_series` reads 2024 and asks for 2025 (to rewrite) |
| `SiteContext.from_reading(reading, *, label="", geometry_wkt="")` (`contracts.py:98`) | holds `conditions: SiteConditions | None`; a subclass instance is fine |
| `api.assess_site(context, *, forcing=DEFAULT_FORCING, year=PLACEHOLDER_YEAR, params=None, species=None, methods=None, scale=..., eutropy=None, bowtie=None) -> SiteAssessment` | `SiteAssessment.excluded: dict[str, str]`; docstring (`api.py:134-140`) still says a plain `ValueError` excludes — false since `d3ed04b` |
| `eutropy_adapter.apply_nutrient_scenario(context, scenario) -> (SiteContext, str)` (`:46`) | does `replace(context.conditions, din_umol_l=din, dip_umol_l=dip)`; module docstring (`:1-20`) says the ensemble produced **summer-month** DIN |
| Species floors (`params/species/*.yaml`, `tolerance_floor_psu`) | chorda 4.0, fucus 4.0, mytilus 4.0, saccharina 16.0, ulva 2.5 — the fixture's 0–1 psu contraindicates all five; +7 psu lifts all but Saccharina |
| `CHANGELOG.md` | `## [Unreleased]` says "Nothing yet."; the 0.10.0 "Known limits" has two paragraphs (per-session load / process-wide cache waits on D§9 item 3; eutropy path raises through the reader) |
| D-a design | ends with `## D§9 Amendment, 2026-09-22 — two D§2/D§4 claims the reader does not implement`, items 1–3 |
| Data-layer design §8 | one row `| **E** | Map and polygon drawing | ... | D | 1.5 PM ... | One fewer README stub row; seam present though unwired |` at line 767; no E-a/E-b/D-a2 rows |

## File structure

| File | Responsibility in this package |
|---|---|
| `src/seagarden_dst/gridded.py` | `GriddedConditions`; `_cell_mean_monthly`; shapely parsing (`_geometry_of`) and cell selection (`_select_cells`); `reading_at` with the §3.2 table; `daily_forcing` over cells with the §3.6 ratio; `_cell_for_site(site, year)`; wider ImportError reason |
| `src/seagarden_dst/forcing.py` | `SiteReading.valid_fraction`; `SiteQuery` docstring |
| `src/seagarden_dst/eutropy_adapter.py`, `src/seagarden_dst/api.py` | docstrings only |
| `tests/test_gridded.py` | tests 1–8, 10–12 and the rewritten two-years test |
| `tests/test_select_forcing.py` | the shapely-absent default-selection test |
| Docs | D-a design D§9 resolution note; data-layer §8 row split; CHANGELOG `[Unreleased]` |

---

### Task 1: The cell handle — `GriddedConditions` replaces the id()-keyed map

**Files:**
- Modify: `src/seagarden_dst/gridded.py` (class after `UnrecognisedSchema`; `__init__`, `reading_at`, `daily_forcing`, `_cell_for_site`, `_conditions_at`)
- Test: `tests/test_gridded.py`

**Interfaces:**
- Consumes: `SiteConditions`, `SiteQuery`, `SiteReading`, `Aggregation`, `Coverage` from `forcing.py`.
- Produces: `GriddedConditions(SiteConditions)` with `cells: tuple[tuple[int, int], ...]` and `year: int`, keyword-only; `GriddedForcing._cell_for_site(site, year) -> tuple[tuple[int, int], ...]`; `reading_at` returns conditions of that type with `cells == ((row, col),)` and `year == query.year`. Task 2 generalises the reads over `cells`; until then `daily_forcing` and `_conditions_at` use `cells[0]`.

- [ ] **Step 1: Write the failing tests (spec tests 1 and 12, and the rewritten two-years test)**

Append to `tests/test_gridded.py`:

```python
def test_a_replaced_conditions_object_still_finds_its_cell(reader):
    """Spec §2 / D§9 item 3. `eutropy_adapter` builds a *replaced* SiteConditions; the
    id()-keyed side table has never seen it and raises. Cells on the object survive
    `dataclasses.replace`."""
    from dataclasses import replace

    lats, lons = reader.latitudes, reader.longitudes
    site = reader.reading_at(SiteQuery(_point(lats[1], lons[1]), year=2024)).conditions
    forced = replace(site, din_umol_l=5.0, dip_umol_l=0.5)
    days, par, temp, din = reader.daily_forcing(forced, (4, 9), 2024)
    assert np.isfinite(din).all() and len(din) == len(days)


def test_a_plain_site_conditions_is_refused_by_daily_forcing(reader):
    """The refusal names what is needed, not an instance identity (spec §2)."""
    from dataclasses import fields

    from seagarden_dst.forcing import SiteConditions

    lats, lons = reader.latitudes, reader.longitudes
    site = reader.reading_at(SiteQuery(_point(lats[1], lons[1]), year=2024)).conditions
    plain = SiteConditions(**{f.name: getattr(site, f.name) for f in fields(SiteConditions)})
    with pytest.raises(ValueError, match="needs a GriddedConditions"):
        reader.daily_forcing(plain, (4, 9), 2024)


def test_a_site_read_for_one_year_refuses_a_series_for_another(reader):
    """Spec §3.6: rescaling 2025's field to 2024's annual mean would substitute a year."""
    lats, lons = reader.latitudes, reader.longitudes
    site = reader.reading_at(SiteQuery(_point(lats[1], lons[1]), year=2024)).conditions
    with pytest.raises(ValueError, match="same year"):
        reader.daily_forcing(site, (4, 9), 2025)
```

Replace the existing `test_two_years_give_different_series` body with:

```python
def test_two_years_give_different_series(reader):
    """The whole reason `daily_forcing` takes a year: collapsing years into one
    climatology costs -57% to +179% in final biomass (§6.2). One site per year, because
    a site carries the year it was read for (spec §3.6)."""
    lats, lons = reader.latitudes, reader.longitudes
    site_2024 = reader.reading_at(SiteQuery(_point(lats[1], lons[1]), year=2024)).conditions
    site_2025 = reader.reading_at(SiteQuery(_point(lats[1], lons[1]), year=2025)).conditions
    _, _, temp_2024, _ = reader.daily_forcing(site_2024, (4, 9), 2024)
    _, _, temp_2025, _ = reader.daily_forcing(site_2025, (4, 9), 2025)
    assert not np.allclose(temp_2024, temp_2025)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest -p no:cacheprovider -m spatial tests/test_gridded.py -q -k "replaced or plain_site or one_year"`
Expected: 3 FAIL — the first with `ValueError: daily_forcing needs a SiteConditions object produced by this GriddedForcing instance`, the second because the raised message does not match "needs a GriddedConditions", the third because no error is raised.

- [ ] **Step 3: Implement the handle**

In `src/seagarden_dst/gridded.py`, add `from dataclasses import dataclass` to the imports, then after `class UnrecognisedSchema` insert:

```python
@dataclass(frozen=True, kw_only=True)
class GriddedConditions(SiteConditions):
    """`SiteConditions` that remember which artifact cells they were averaged over.

    A reader-specific index, which is why it is a subclass here and not a field on the
    core type. `dataclasses.replace` returns this subclass with both fields intact, so a
    nutrient scenario's replaced conditions still find their cells (D§9 item 3).
    """

    #: The (row, col) artifact cells these conditions were averaged over, as plain
    #: Python ints, row-major. Exactly one cell under CONTAINING_CELL; two or more
    #: under UNWEIGHTED_MEAN (spec §3.2 labels by the number of VALID cells).
    cells: tuple[tuple[int, int], ...]
    #: The artifact year these annual means were taken for. `daily_forcing` refuses a
    #: `year` that differs (spec §3.6): the DIN ratio is only exactly 1.0 against the
    #: year the site was read for, and rescaling another year's field to this year's
    #: mean would be the silent substitution §6.2 forbids.
    year: int
```

In `GriddedForcing.__init__`, delete the `_site_cells` line and the three comment lines above it.

In `reading_at`, replace

```python
        conditions = self._conditions_at(row, col, query.year, query.region)
        self._site_cells[id(conditions)] = (row, col)
```

with

```python
        conditions = self._conditions_at(((row, col),), query.year, query.region)
```

In `daily_forcing`, replace `row, col = self._cell_for_site(site)` with

```python
        cells = self._cell_for_site(site, year)
        row, col = cells[0]
```

Replace `_cell_for_site` entirely:

```python
    def _cell_for_site(self, site: SiteConditions, year: int) -> tuple[tuple[int, int], ...]:
        """The cells a reader-produced site was averaged over, for the same year.

        A handle from a different reader over a same-shape grid is accepted by design
        (tests hold the fixture reader and a tmp copy; the app holds one reader per
        session), so the check is on shape and year, not identity.
        """
        n_lat, n_lon = self.latitudes.size, self.longitudes.size
        usable = (
            isinstance(site, GriddedConditions)
            and len(site.cells) > 0
            and all(0 <= r < n_lat and 0 <= c < n_lon for r, c in site.cells)
            and site.year == year
        )
        if not usable:
            raise ValueError(
                "daily_forcing needs a GriddedConditions produced by a GriddedForcing "
                "over this grid, for the same year"
            )
        return site.cells
```

Change `_conditions_at`'s signature and body head to take cells (Task 2 makes it truly multi-cell; here it reads the first):

```python
    def _conditions_at(
        self, cells: tuple[tuple[int, int], ...], year: int, region: str | None
    ) -> GriddedConditions:
        row, col = cells[0]
        year_index = self._years.index(year)
```

and change its `return SiteConditions(` to `return GriddedConditions(` adding, as the last two keyword arguments, `cells=cells,` and `year=year,`.

- [ ] **Step 4: Run the whole spatial reader file**

Run: `MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest -p no:cacheprovider -m spatial tests/test_gridded.py -q`
Expected: all PASS (13 tests: the 10 existing incl. the rewritten one, plus 3 new).

- [ ] **Step 5: Confirm the side table is gone and the default selection still imports `gridded`**

Run: `grep -n _site_cells src/seagarden_dst/gridded.py` → expected: no output.
Run: `MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest -p no:cacheprovider -q tests/test_select_forcing.py tests/test_gridded_isolation.py tests/test_assess_with_artifact.py`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/seagarden_dst/gridded.py tests/test_gridded.py
git commit -m "feat(gridded): GriddedConditions carries its cells and year; the id()-keyed map is gone

A replaced SiteConditions (the eutropy path) now finds its cell, because the
cells travel on the object and survive dataclasses.replace. daily_forcing
refuses a plain SiteConditions, and a site read for one year asked for
another's series (spec D-a2 §2, §3.6).

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: One reader of the monthly fields — `_cell_mean_monthly`, multi-cell `_conditions_at` and `daily_forcing`

**Files:**
- Modify: `src/seagarden_dst/gridded.py` (`_interpolated_monthly`, `_conditions_at`, `daily_forcing`; new `_cell_mean_monthly`)
- Test: `tests/test_gridded.py`

**Interfaces:**
- Consumes: `GriddedConditions.cells`, `_cell_for_site(site, year)` from Task 1.
- Produces: `GriddedForcing._cell_mean_monthly(name: str, year: int, cells: tuple[tuple[int, int], ...]) -> np.ndarray` of shape `(12,)`, float64; `_conditions_at(cells, year, region)` averaging over all of `cells`; `daily_forcing` averaging over all of `site.cells`. Task 4's polygon path and Task 5's ratio depend on this being the only route to the monthly fields.

- [ ] **Step 1: Write the failing test (spec test 2: single-cell reads are bit-identical to a direct computation)**

Append to `tests/test_gridded.py`:

```python
def _open_fixture_dataset():
    import xarray as xr

    ds = xr.open_dataset(f"{FIXTURE}/forcing.nc", engine="h5netcdf").load()
    ds.close()
    return ds


def test_a_point_read_equals_the_direct_single_cell_computation(reader):
    """Spec §3.4: for one cell the cell-mean is the identity and the month reduction is
    today's call, so every field is EXACTLY what a direct float64 computation gives."""
    ds = _open_fixture_dataset()
    lats, lons = reader.latitudes, reader.longitudes
    reading = reader.reading_at(SiteQuery(_point(lats[1], lons[1]), year=2024))
    c = reading.conditions
    assert reading.aggregation is Aggregation.CONTAINING_CELL
    assert reading.valid_fraction is None
    assert c.cells == ((1, 1),) and c.year == 2024

    yi = list(int(y) for y in ds["year"].values).index(2024)

    def monthly(name):
        return np.asarray(ds[name].values[yi, :, 1, 1], dtype=float)

    assert c.salinity_psu == float(np.mean(monthly("salinity_psu")))
    assert c.mean_temp_c == float(np.mean(monthly("temp_c")))
    assert c.summer_temp_c == float(np.max(monthly("temp_c")))
    assert c.winter_temp_c == float(np.min(monthly("temp_c")))
    assert c.din_umol_l == float(np.mean(monthly("din_umol_l")))
    assert c.dip_umol_l == float(np.mean(monthly("dip_umol_l")))
    assert c.light_attenuation_k == float(np.mean(monthly("light_attenuation_k")))
    wave = np.asarray(ds["significant_wave_m"].values[:, 1, 1], dtype=float)
    assert c.significant_wave_m == float(np.mean(wave))
    assert c.depth_m == float(ds["depth_mean_m"].values[1, 1])
```

`valid_fraction` does not exist on `SiteReading` yet; add it now so this test can be written once. In `src/seagarden_dst/forcing.py`, after `stale_months: int | None = None` in `SiteReading`, add:

```python
    #: On a POLYGON read with two or more cell coordinates inside it: valid cells ÷
    #: cells inside, whatever `aggregation` says and whether or not coverage blocked.
    #: None on a POINT read, or on a POLYGON with fewer than two inside. Surfaced with
    #: no threshold; §6.2 (3) leaves the threshold to package D-b.
    valid_fraction: float | None = None
```

- [ ] **Step 2: Run it to verify it passes on the single-cell path (this test is a regression pin, not a discriminator — say so in the ledger)**

Run: `MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest -p no:cacheprovider -m spatial tests/test_gridded.py -q -k direct_single_cell`
Expected: PASS. (It must still pass after Step 3, which is the point: the refactor may not move a single bit.)

- [ ] **Step 3: Implement the helper and route every monthly read through it**

In `gridded.py`, add to `GriddedForcing`:

```python
    def _cell_mean_monthly(
        self, name: str, year: int, cells: tuple[tuple[int, int], ...]
    ) -> np.ndarray:
        """The 12 monthly values of a per-year field, averaged over `cells`, float64.

        The ONLY reader of the per-year monthly fields (spec §3.4). Cast to float64
        before any reduction, then `np.mean` over the cell axis: for one cell that is
        the identity on a float64 vector, so single-cell readings are bit-identical to
        a direct computation; and because `_conditions_at` and `daily_forcing` both
        come here, the §3.6 ratio is exactly 1.0 for an unmodified site.
        """
        rows = [r for r, _ in cells]
        cols = [c for _, c in cells]
        year_index = self._years.index(year)
        block = np.asarray(self._ds[name].values[year_index][:, rows, cols], dtype=float)
        return np.mean(block, axis=1)
```

Replace `_interpolated_monthly` with:

```python
    def _interpolated_monthly(
        self,
        name: str,
        cells: tuple[tuple[int, int], ...],
        month_years: list[tuple[int, int, int]],
        days: np.ndarray,
        scale: float = 1.0,
    ) -> np.ndarray:
        by_year = {
            year: self._cell_mean_monthly(name, year, cells)
            for year in {year for _, year, _ in month_years}
        }
        x = np.asarray([day for _, _, day in month_years], dtype=float)
        values = np.asarray([by_year[year][month - 1] for month, year, _ in month_years])
        return np.interp(days, x, values * scale)
```

In `daily_forcing`, replace `row, col = cells[0]` (Task 1) by nothing — delete that line — and change the two calls to

```python
        temp = self._interpolated_monthly("temp_c", cells, month_years, days)
        din = self._interpolated_monthly("din_umol_l", cells, month_years, days)
```

(Task 5 adds the `scale=` argument on the DIN call.)

Replace `_conditions_at` with:

```python
    def _conditions_at(
        self, cells: tuple[tuple[int, int], ...], year: int, region: str | None
    ) -> GriddedConditions:
        """Annual statistics over `cells`, field-mean-first (spec §3.4)."""
        temp = self._cell_mean_monthly("temp_c", year, cells)
        salinity = self._cell_mean_monthly("salinity_psu", year, cells)
        din = self._cell_mean_monthly("din_umol_l", year, cells)
        dip = self._cell_mean_monthly("dip_umol_l", year, cells)
        attenuation = self._cell_mean_monthly("light_attenuation_k", year, cells)
        rows = [r for r, _ in cells]
        cols = [c for _, c in cells]
        wave = np.mean(
            np.asarray(self._ds["significant_wave_m"].values[:, rows, cols], dtype=float), axis=1
        )
        depth = np.mean(np.asarray(self._ds["depth_mean_m"].values[rows, cols], dtype=float))

        return GriddedConditions(
            region=region,
            salinity_psu=float(np.mean(salinity)),
            mean_temp_c=float(np.mean(temp)),
            summer_temp_c=float(np.max(temp)),
            winter_temp_c=float(np.min(temp)),
            # The artifact deliberately records `surface_par` as absent (C§3.3), so
            # this remains a placeholder constant even for artifact-backed conditions.
            surface_par=PLACEHOLDER_SURFACE_PAR,
            din_umol_l=float(np.mean(din)),
            dip_umol_l=float(np.mean(dip)),
            depth_m=float(depth),
            significant_wave_m=float(np.mean(wave)),
            light_attenuation_k=float(np.mean(attenuation)),
            cells=cells,
            year=year,
        )
```

- [ ] **Step 4: Run the reader file**

Run: `MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest -p no:cacheprovider -m spatial tests/test_gridded.py -q`
Expected: all PASS, including `direct_single_cell` unchanged (bit-identity held).

- [ ] **Step 5: Commit**

```bash
git add src/seagarden_dst/gridded.py src/seagarden_dst/forcing.py tests/test_gridded.py
git commit -m "refactor(gridded): one reader of the monthly fields, averaged over the site's cells

_cell_mean_monthly is the only route to the per-year fields: float64 first,
then the cell mean, then the annual statistic or the daily interpolation.
Single-cell readings are pinned bit-identical to a direct computation.
SiteReading gains valid_fraction (spec D-a2 §3.4, §3.5).

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: WKT through shapely, wrapped to `ValueError`; the ImportError row names shapely

**Files:**
- Modify: `src/seagarden_dst/gridded.py` (`from_directory`, `select_forcing`'s ImportError reason, new `_geometry_of`, `_point_of` deleted)
- Test: `tests/test_gridded.py` (spec test 9), `tests/test_select_forcing.py` (the shapely-absent sibling)

**Interfaces:**
- Consumes: nothing new.
- Produces: `GriddedForcing._geometry_of(wkt: str)` returning a non-empty shapely `Point` or `Polygon`, raising `ValueError(f"could not parse site geometry WKT {wkt!r}")` otherwise. Task 4 builds cell selection on it. `reading_at` temporarily uses `_geometry_of` for the point/centroid only (Task 4 adds the inside set).

- [ ] **Step 1: Write the failing default-selection test**

In `tests/test_select_forcing.py`, after `test_without_the_spatial_stack_the_reason_names_the_extra`, add:

```python
def test_without_shapely_alone_the_reason_still_names_the_extra(tmp_path, monkeypatch):
    """shapely is imported inside `from_directory` beside xarray, before `load_pair`
    (spec D-a2 §3.1); a missing shapely is the same 'no spatial extra' row."""
    from seagarden_dst.gridded import select_forcing

    shutil.copytree(FIXTURE, tmp_path / "data")
    monkeypatch.setitem(sys.modules, "shapely", None)
    choice = select_forcing(tmp_path / "data")
    assert choice.kind == "placeholder"
    assert choice.reason.startswith("this install has no spatial extra (xarray/h5netcdf/shapely)")
    assert str(tmp_path / "data") in choice.reason
```

And append to `tests/test_gridded.py`:

```python
@pytest.mark.parametrize(
    "wkt",
    ["", "garbage", "POLYGON EMPTY", "MULTIPOLYGON (((20 54, 20.1 54, 20.1 54.1, 20 54)))"],
)
def test_unusable_geometry_raises_a_value_error_naming_the_wkt(reader, wkt):
    """Regression guard, not a discriminator: today's regex already raises. With
    shapely underneath, GEOSException is NOT a ValueError and POLYGON EMPTY parses,
    so this is what forces the wrapping (spec §3.1)."""
    with pytest.raises(ValueError, match="could not parse site geometry WKT"):
        reader.reading_at(SiteQuery(wkt, year=2024))
```

- [ ] **Step 2: Run to verify the select_forcing test fails and the parametrised guard passes today**

Run: `MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest -p no:cacheprovider -q tests/test_select_forcing.py -k shapely_alone`
Expected: FAIL — with shapely blanked but not imported by the reader, the fixture is read and `choice.kind == "artifact"` (or, if the environment lacks xarray, the reason lacks "/shapely").
Run: `MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest -p no:cacheprovider -m spatial tests/test_gridded.py -q -k unusable_geometry`
Expected: 4 PASS (record in the ledger that this is the pre-change baseline).

- [ ] **Step 3: Implement**

In `from_directory`, change the import line to

```python
        import shapely  # noqa: F401 - imported here so a missing extra is reported first
        import xarray as xr
```

(both before `manifest, artifact = load_pair(Path(directory))`).

In `select_forcing`'s `except ImportError:` branch, change the reason to

```python
            f"this install has no spatial extra (xarray/h5netcdf/shapely), so the artifact "
            f"at {directory} cannot be read",
```

Delete `_POINT = re.compile(...)` and `import re`. Replace `_point_of` with:

```python
    def _geometry_of(self, wkt: str):
        """A non-empty shapely Point or Polygon, or ValueError naming the WKT.

        shapely's own failures are not ValueErrors (`GEOSException` is a
        `ShapelyError`), and `POLYGON EMPTY` parses to an empty geometry with no
        centroid, so both are wrapped here (spec §3.1).
        """
        import shapely
        from shapely.errors import ShapelyError

        try:
            geom = shapely.from_wkt(wkt)
        except ShapelyError as exc:
            raise ValueError(f"could not parse site geometry WKT {wkt!r}") from exc
        if geom is None or geom.is_empty or geom.geom_type not in ("Point", "Polygon"):
            raise ValueError(f"could not parse site geometry WKT {wkt!r}")
        return geom
```

In `reading_at`, replace `lat, lon = self._point_of(query)` with

```python
        geom = self._geometry_of(query.geometry_wkt)
        point = geom if geom.geom_type == "Point" else geom.centroid
        lat, lon = point.y, point.x
```

- [ ] **Step 4: Run both files**

Run: `MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest -p no:cacheprovider -q tests/test_select_forcing.py && MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest -p no:cacheprovider -m spatial tests/test_gridded.py tests/test_select_forcing.py -q`
Expected: all PASS.
Run: `grep -n "^import shapely\|^from shapely\|^import re$\|_POINT" src/seagarden_dst/gridded.py` → expected: no output.

- [ ] **Step 5: Commit**

```bash
git add src/seagarden_dst/gridded.py tests/test_gridded.py tests/test_select_forcing.py
git commit -m "feat(gridded): WKT through shapely, wrapped to ValueError; a missing shapely names the extra

Function-local imports only; shapely is imported beside xarray before load_pair
so a bare install reports the extra, not a torn pair (spec D-a2 §3.1).

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: Cell selection and aggregation — the §3.2 table in `reading_at`

**Files:**
- Modify: `src/seagarden_dst/gridded.py` (`reading_at`; new `_select_cells`)
- Test: `tests/test_gridded.py` (spec tests 3, 4, 5, 6, 7, 10)

**Interfaces:**
- Consumes: `_geometry_of` (Task 3), `_conditions_at(cells, year, region)` and `_cell_mean_monthly` (Task 2), `SiteReading.valid_fraction` (Task 2).
- Produces: `_select_cells(query) -> tuple[tuple[int, int], tuple[tuple[int, int], ...] | None]` = `(anchor, inside)`, `inside` `None` for a POINT; `reading_at` populating `aggregation`, `cells`, `valid_fraction` per spec §3.2/§3.3.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_gridded.py`:

```python
# Spec §5 polygons, verbatim. WKT is (lon lat). Three review cycles verified every
# inside set, centroid and anchor against the fixture by script; do not invent others.
NINE_CELLS = "POLYGON ((19.99 53.99, 20.07 53.99, 20.07 54.05, 19.99 54.05, 19.99 53.99))"
TRIANGLE_ON_INVALID = "POLYGON ((19.995 53.995, 20.035 53.995, 19.995 54.025, 19.995 53.995))"
SUB_CELL_NEAR_11 = (
    "POLYGON ((20.038 54.020, 20.043 54.020, 20.043 54.025, 20.038 54.025, 20.038 54.020))"
)
TWO_CELLS_ONE_VALID = "POLYGON ((19.99 53.99, 20.04 53.99, 20.04 54.008, 19.99 54.008, 19.99 53.99))"
U_SHAPE = (
    "POLYGON ((19.99 53.99, 20.07 53.99, 20.07 54.05, 20.045 54.05, 20.045 54.008, "
    "20.015 54.008, 20.015 54.05, 19.99 54.05, 19.99 53.99))"
)


def test_a_polygon_over_nine_cells_is_the_unweighted_mean_of_the_eight_valid_ones(reader):
    """Spec test 3. Centroid (20.03, 54.02) -> anchor [1,1], valid."""
    ds = _open_fixture_dataset()
    reading = reader.reading_at(SiteQuery(NINE_CELLS, year=2024))
    assert reading.coverage is Coverage.VALID
    assert reading.aggregation is Aggregation.UNWEIGHTED_MEAN
    assert reading.valid_fraction == pytest.approx(8 / 9)
    cells = reading.conditions.cells
    assert len(cells) == 8 and (0, 0) not in cells
    yi = list(int(y) for y in ds["year"].values).index(2024)
    rows = [r for r, _ in cells]
    cols = [c for _, c in cells]
    block = np.asarray(ds["salinity_psu"].values[yi][:, rows, cols], dtype=float)
    assert np.allclose(reading.conditions.salinity_psu, np.mean(block), rtol=1e-12)


def test_a_polygon_whose_anchor_is_invalid_blocks_and_still_reports_the_fraction(reader):
    """Spec test 4, decision 1: the containing cell decides coverage (§6.2 rule 1)."""
    reading = reader.reading_at(SiteQuery(TRIANGLE_ON_INVALID, year=2024))
    assert reading.coverage is Coverage.CELL_INVALID
    assert reading.conditions is None
    assert reading.nearest_valid_km is not None and reading.nearest_valid_km > 0.0
    assert reading.valid_fraction == pytest.approx(2 / 3)
    assert reading.aggregation is Aggregation.CONTAINING_CELL


def test_a_sub_cell_polygon_between_coordinates_is_its_anchor_cell(reader):
    """Spec test 5: no coordinate inside -> the centroid's nearest cell, no fraction."""
    reading = reader.reading_at(SiteQuery(SUB_CELL_NEAR_11, year=2024))
    assert reading.coverage is Coverage.VALID
    assert reading.aggregation is Aggregation.CONTAINING_CELL
    assert reading.valid_fraction is None
    assert reading.conditions.cells == ((1, 1),)


def test_the_label_follows_the_valid_count_not_the_inside_count(reader):
    """Spec test 6, §3.2 row 3: two inside, one valid -> CONTAINING_CELL over the anchor,
    fraction still reported."""
    reading = reader.reading_at(SiteQuery(TWO_CELLS_ONE_VALID, year=2024))
    assert reading.coverage is Coverage.VALID
    assert reading.aggregation is Aggregation.CONTAINING_CELL
    assert reading.conditions.cells == ((0, 1),)
    assert reading.valid_fraction == pytest.approx(0.5)


def test_a_concave_polygon_anchors_outside_its_own_inside_set(reader):
    """Spec test 10. The notch excludes [1,1] and [2,1]; the centroid still lands
    nearest [1,1], which decides coverage but is not averaged. On this fixture the
    area centroid (lat 54.0168) and the old vertex mean (54.0245) both anchor [1,1],
    so the centroid method itself is not pinned here (spec §5, recorded)."""
    reading = reader.reading_at(SiteQuery(U_SHAPE, year=2024))
    assert reading.coverage is Coverage.VALID
    assert reading.aggregation is Aggregation.UNWEIGHTED_MEAN
    assert reading.valid_fraction == pytest.approx(6 / 7)
    assert reading.conditions.cells == ((0, 1), (0, 2), (1, 0), (1, 2), (2, 0), (2, 2))


def test_a_multi_cell_daily_series_is_the_mean_of_the_single_cell_series(reader):
    """Spec test 7, field-mean-first: temp and din over the polygon equal the elementwise
    mean of the eight single-cell series. par is derived from the averaged k and is
    NOT compared (§3.4). All reads and series for 2024."""
    lats, lons = reader.latitudes, reader.longitudes
    poly = reader.reading_at(SiteQuery(NINE_CELLS, year=2024)).conditions
    _, _, temp_poly, din_poly = reader.daily_forcing(poly, (4, 9), 2024)
    temps, dins = [], []
    for r, c in poly.cells:
        one = reader.reading_at(SiteQuery(_point(lats[r], lons[c]), year=2024)).conditions
        _, _, t, d = reader.daily_forcing(one, (4, 9), 2024)
        temps.append(t)
        dins.append(d)
    assert np.allclose(temp_poly, np.mean(temps, axis=0), rtol=1e-12)
    assert np.allclose(din_poly, np.mean(dins, axis=0), rtol=1e-12)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest -p no:cacheprovider -m spatial tests/test_gridded.py -q -k "nine_cells or anchor_is_invalid or sub_cell or valid_count or concave or multi_cell_daily"`
Expected: 5 FAIL, 1 PASS. Nine-cells fails on `aggregation is UNWEIGHTED_MEAN` (today the centroid reads one cell); anchor-invalid fails on `valid_fraction == 2/3` (today `None`); valid-count fails on `valid_fraction == 0.5`; concave fails on `aggregation`; multi-cell-daily fails on the `temp_poly` comparison (one cell against the mean of eight). The sub-cell test **passes today** — the centroid already anchors `[1,1]` and `valid_fraction` defaults to `None` — so record it in the ledger as a regression guard that must stay green after Step 3, not as a discriminator.

- [ ] **Step 3: Implement cell selection and the table**

Add to `GriddedForcing`:

```python
    def _select_cells(
        self, query: SiteQuery
    ) -> tuple[tuple[int, int], tuple[tuple[int, int], ...] | None]:
        """(anchor, inside): the cell that decides coverage, and for a polygon the cells
        whose coordinate values it contains (spec §3.2).

        "Inside" uses the cell's coordinate value (`latitudes[row]`, `longitudes[col]`),
        the location this reader already assigns each cell — NOT the value plus half a
        step. The anchor is the cell nearest the polygon's area centroid, by the same
        per-axis argmin a POINT uses.
        """
        import shapely

        geom = self._geometry_of(query.geometry_wkt)
        if geom.geom_type == "Point":
            return self._nearest_index(geom.y, geom.x), None
        centroid = geom.centroid
        anchor = self._nearest_index(centroid.y, centroid.x)
        lon_grid, lat_grid = np.meshgrid(self.longitudes, self.latitudes)
        mask = shapely.contains_xy(geom, lon_grid, lat_grid)
        rows, cols = np.nonzero(mask)
        inside = tuple((int(r), int(c)) for r, c in zip(rows, cols, strict=True))
        return anchor, inside
```

Replace `reading_at` entirely:

```python
    def reading_at(self, query: SiteQuery) -> SiteReading:
        anchor, inside = self._select_cells(query)
        row, col = anchor
        valid = np.asarray(self._ds["valid"].values, dtype=bool)

        # The fraction is computable under every outcome (`valid` has no year axis), so
        # one rule serves: set it whenever two or more cells lie inside (spec §3.2).
        valid_inside: tuple[tuple[int, int], ...] = ()
        fraction: float | None = None
        if inside is not None and len(inside) >= 2:
            valid_inside = tuple(cell for cell in inside if valid[cell])
            fraction = len(valid_inside) / len(inside)

        if query.year not in self._years:
            # Never substitutes another year (§6.2): interannual spread is the dominant
            # term, so a neighbouring year is a different answer, not an approximation.
            return SiteReading(
                conditions=None,
                coverage=Coverage.YEAR_ABSENT,
                year=query.year,
                aggregation=Aggregation.CONTAINING_CELL,
                from_artifact=True,
                valid_fraction=fraction,
            )

        # The anchor decides coverage (§6.2 rule 1; decision 1 of the D-a2 design). The
        # `valid` field, by value. NEVER inferred from NaN: the committed fixture's
        # invalid cell holds finite numbers, so a NaN test would call it assessable.
        if not bool(valid[row, col]):
            return SiteReading(
                conditions=None,
                coverage=Coverage.CELL_INVALID,
                year=query.year,
                aggregation=Aggregation.CONTAINING_CELL,
                nearest_valid_km=self._nearest_valid_km(row, col),
                from_artifact=True,
                valid_fraction=fraction,
            )

        # The label follows the number of VALID cells averaged, never the inside count,
        # so a one-tuple never carries UNWEIGHTED_MEAN. The anchor is not added to a
        # multi-cell average it does not belong to (a concave polygon).
        if len(valid_inside) >= 2:
            cells, aggregation = valid_inside, Aggregation.UNWEIGHTED_MEAN
        else:
            cells, aggregation = (anchor,), Aggregation.CONTAINING_CELL

        conditions = self._conditions_at(cells, query.year, query.region)
        return SiteReading(
            conditions=conditions,
            coverage=Coverage.VALID,
            year=query.year,
            aggregation=aggregation,
            from_artifact=True,
            valid_fraction=fraction,
        )
```

- [ ] **Step 4: Run the reader file**

Run: `MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest -p no:cacheprovider -m spatial tests/test_gridded.py -q`
Expected: all PASS (the direct-single-cell pin included: a POINT still reads one cell).

- [ ] **Step 5: Commit**

```bash
git add src/seagarden_dst/gridded.py tests/test_gridded.py
git commit -m "feat(gridded): a polygon reads as the unweighted mean over its valid cells

Inside set by shapely.contains_xy over the cell coordinates; the centroid's
nearest cell decides coverage; the label follows the valid-cell count; the
valid fraction rides on the reading with no threshold (spec D-a2 §3.2, §3.3).

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: The daily DIN honours the site's annual value (§3.6)

**Files:**
- Modify: `src/seagarden_dst/gridded.py` (`daily_forcing`)
- Test: `tests/test_gridded.py` (spec test 11)

**Interfaces:**
- Consumes: `_cell_mean_monthly`, `_interpolated_monthly(..., scale=)` (Task 2), `_cell_for_site(site, year)` (Task 1).
- Produces: `daily_forcing` whose `din` series is the cell-mean monthly field × `site.din_umol_l / mean(_cell_mean_monthly("din_umol_l", year, cells))`. Task 6's end-to-end test relies on it.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_gridded.py`:

```python
def test_the_daily_din_scales_with_the_sites_annual_value_and_is_untouched_otherwise(reader):
    """Spec §3.6 / test 11. A replaced annual DIN scales the monthly field by one ratio;
    temp does not move. For an unmodified site the ratio is EXACTLY 1.0, so the series
    is array_equal to what today's per-cell interpolation gives."""
    from dataclasses import replace

    ds = _open_fixture_dataset()
    lats, lons = reader.latitudes, reader.longitudes
    site = reader.reading_at(SiteQuery(_point(lats[1], lons[1]), year=2024)).conditions
    days, _, temp, din = reader.daily_forcing(site, (4, 9), 2024)

    doubled = replace(site, din_umol_l=2.0 * site.din_umol_l)
    _, _, temp_2, din_2 = reader.daily_forcing(doubled, (4, 9), 2024)
    assert np.allclose(din_2, 2.0 * din, rtol=1e-12)
    assert np.array_equal(temp_2, temp)

    # Today's route, reproduced: float32 scalars per month, cast, interpolated.
    from seagarden_dst.forcing import day_of_year

    yi = list(int(y) for y in ds["year"].values).index(2024)
    x = np.asarray([day_of_year(m) for m in range(4, 10)], dtype=float)  # mid-month knots
    values = np.asarray(
        [ds["din_umol_l"].values[yi, m - 1, 1, 1] for m in range(4, 10)], dtype=float
    )
    assert np.array_equal(din, np.interp(days, x, values))
```

- [ ] **Step 2: Run it to verify it fails**

Run: `MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest -p no:cacheprovider -m spatial tests/test_gridded.py -q -k scales_with_the_sites_annual`
Expected: FAIL on `np.allclose(din_2, 2.0 * din)` (the series ignores the site value today).

- [ ] **Step 3: Implement the ratio**

In `daily_forcing`, replace

```python
        din = self._interpolated_monthly("din_umol_l", cells, month_years, days)
```

with

```python
        # §3.6: the series' 12-month mean for `year` is the site's annual DIN. For an
        # unmodified site numerator and denominator are the same np.mean of the same
        # _cell_mean_monthly output, so the ratio is exactly 1.0 and nothing moves; a
        # nutrient scenario that replaced `din_umol_l` scales the seasonal shape.
        annual_din = float(np.mean(self._cell_mean_monthly("din_umol_l", year, cells)))
        if annual_din == 0.0:
            # A masking or unit defect, not a measurement: fail loudly (d3ed04b's rule),
            # never ForcingUnavailable, which would quietly exclude the species.
            raise ValueError(
                f"artifact DIN for {year} averages zero over cells {cells}; refusing to "
                "scale a series against it"
            )
        din = self._interpolated_monthly(
            "din_umol_l", cells, month_years, days, scale=site.din_umol_l / annual_din
        )
```

- [ ] **Step 4: Run the reader file**

Run: `MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest -p no:cacheprovider -m spatial tests/test_gridded.py -q`
Expected: all PASS, including the `array_equal` pin of the unmodified series and the Task 4 multi-cell daily test.

- [ ] **Step 5: Commit**

```bash
git add src/seagarden_dst/gridded.py tests/test_gridded.py
git commit -m "feat(gridded): the daily DIN honours the site's annual value

The cell-mean monthly field is scaled by site.din_umol_l over the year's
cell-mean annual DIN, so a nutrient scenario reaches the artifact-backed
growth model with the seasonal shape kept; ratio exactly 1.0 otherwise
(spec D-a2 §3.6, decisions 3 and 4).

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: End-to-end — a nutrient scenario on an artifact session returns; the two stale docstrings

**Files:**
- Modify: `src/seagarden_dst/api.py:134-140` (docstring), `src/seagarden_dst/eutropy_adapter.py:1-20` and `:46-63` (docstrings)
- Test: `tests/test_gridded.py` (spec test 8)

**Interfaces:**
- Consumes: everything from Tasks 1–5; `api.assess_site`, `SiteContext.from_reading`, `_restamp`.
- Produces: nothing new in code; the documented meaning of `din_umol_l` on the artifact path.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_gridded.py`:

```python
def test_a_nutrient_scenario_on_an_artifact_session_returns_rather_than_raising(tmp_path):
    """Spec test 8 - D§9 item 3 at the level a user meets it. The committed fixture's
    salinity is random in [0, 1) psu and contraindicates every species before any
    growth model runs, so this builds a +7 psu copy. Saccharina (floor 16 psu) stays
    excluded on it BY DESIGN - do not 'fix' that. The defect is the crash."""
    import shutil

    import xarray as xr

    from seagarden_dst.api import assess_site
    from seagarden_dst.contracts import SiteContext

    shutil.copytree(FIXTURE, tmp_path / "data")
    artifact = tmp_path / "data" / "forcing.nc"
    ds = xr.open_dataset(artifact, engine="h5netcdf").load()
    ds.close()
    ds["salinity_psu"].values[...] += np.float32(7.0)
    ds.to_netcdf(artifact, engine="h5netcdf", mode="w")
    _restamp(tmp_path / "data")

    reader = GriddedForcing.from_directory(tmp_path / "data")
    lats, lons = reader.latitudes, reader.longitudes
    query = SiteQuery(_point(lats[1], lons[1]), year=2024)
    context = SiteContext.from_reading(
        reader.reading_at(query), label="fixture", geometry_wkt=query.geometry_wkt
    )
    assessment = assess_site(
        context, forcing=reader, year=2024, eutropy={"din_umol_l": 5.0, "dip_umol_l": 0.5}
    )
    assert not any("GriddedForcing" in why for why in assessment.excluded.values())
    assert "saccharina_latissima" in assessment.excluded
    assert "psu" in assessment.excluded["saccharina_latissima"]
```

- [ ] **Step 2: Run it to verify it passes now (Tasks 1 and 5 already fixed the path) and record the pre-Task-1 failure from the ledger**

Run: `MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest -p no:cacheprovider -m spatial tests/test_gridded.py -q -k nutrient_scenario_on_an_artifact`
Expected: PASS. To prove it discriminates, run it once against `main`'s reader: `git stash` is forbidden (shared tree), so instead check out the file: `git show main:src/seagarden_dst/gridded.py > /tmp/gridded_main.py` is also not what we want — use this instead:

```bash
git worktree add ../dst-main-check main
cd ../dst-main-check && cp "../DST/tests/test_gridded.py" tests/test_gridded.py
MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest -p no:cacheprovider -m spatial tests/test_gridded.py -q -k nutrient_scenario_on_an_artifact
cd ../DST && git worktree remove --force ../dst-main-check
```

Expected in the worktree: FAIL with `ValueError: daily_forcing needs a SiteConditions object produced by this GriddedForcing instance`. Record that output in the ledger.

- [ ] **Step 3: Correct the two docstrings**

In `src/seagarden_dst/api.py`, replace the `year:` paragraph's last two sentences

```
            (`gridded.GriddedForcing.daily_forcing`); when the source raises
            `ValueError` because it cannot cover that window, the species is
            excluded with that message rather than the whole assessment failing.
```

with

```
            (`gridded.GriddedForcing.daily_forcing`); when the source raises
            `ForcingUnavailable` because it cannot cover that window, the species
            is excluded with that message rather than the whole assessment failing.
            Any other `ValueError` from a source is a defect and propagates.
```

In `src/seagarden_dst/eutropy_adapter.py`, after the module docstring's first paragraph (ending "...Nemunas loading were BSAP-compliant?\"") add a paragraph:

```
WHAT THE NUMBERS MEAN. A scenario's ``din_umol_l`` and ``dip_umol_l`` are taken as
ANNUAL MEANS. On the artifact path (`gridded.GriddedForcing`) the site's
``din_umol_l`` is the 12-month mean of the monthly field, and `daily_forcing` scales
that field so its 12-month mean equals the scenario's value (D-a2 design §3.6). The
ensemble tables `scenario_from_ensemble` reads are SUMMER-MONTH concentrations and
must be converted to an annual mean before they are passed in; this module does not
do that conversion. The placeholder's series peaks at ``din_umol_l`` instead (its
annual mean is about 0.725 x the value), a known asymmetry owned by package D1.
```

In `apply_nutrient_scenario`'s docstring, change the `scenario:` line to

```
        scenario: at minimum ``{"din_umol_l": float, "dip_umol_l": float}``, both
            annual means (see the module docstring). Optional
```

- [ ] **Step 4: Run ruff and the affected suites**

Run: `micromamba run -n shiny ruff check src tests app && MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest -p no:cacheprovider -q tests/test_assess_with_artifact.py tests/test_api.py`
Expected: ruff clean; tests PASS. (There is no dedicated eutropy test file; the adapter is exercised through `tests/test_api.py`. If that file is absent, run the whole default selection instead: `... -m pytest -p no:cacheprovider -q`.)

- [ ] **Step 5: Commit**

```bash
git add tests/test_gridded.py src/seagarden_dst/api.py src/seagarden_dst/eutropy_adapter.py
git commit -m "test(gridded): a nutrient scenario on an artifact session returns; docstrings say what DIN means

assess_site no longer claims a plain ValueError excludes a species (false
since d3ed04b); the adapter states scenario DIN/DIP are annual means and that
the summer-month ensemble tables need converting first (spec D-a2 §3.6, §6.8).

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: Documentation — `SiteQuery` docstring, D§9 resolution, §8 row split, CHANGELOG

**Files:**
- Modify: `src/seagarden_dst/forcing.py:215-222`; `docs/superpowers/specs/2026-09-17-package-d-a-artifact-reader-design.md` (append after D§9); `docs/superpowers/specs/2026-09-13-dst-data-layer-design.md:767` (row E); `CHANGELOG.md` `[Unreleased]` and the 0.10.0 known-limits paragraphs.

**Interfaces:** none; docs only.

- [ ] **Step 1: `SiteQuery` docstring**

Replace the docstring in `forcing.py`'s `SiteQuery` with:

```python
    """Where and when to read.

    `geometry_wkt` is a WKT string, not a `shapely` geometry: shapely lives in the
    `spatial` extra and this type is read by the model core. A non-empty POINT or
    POLYGON; the reader refuses anything else. (An earlier draft let an empty string
    mean "the region's coordinate"; D§9 item 2 withdrew that - the app resolves a
    region to a POINT through `region_query` and the reader never consults the
    placeholder's coordinate table.)
    """
```

Run: `grep -n "use the region's coordinate" src/seagarden_dst/forcing.py` → expected: no output.

- [ ] **Step 2: D-a design resolution note**

Append to `docs/superpowers/specs/2026-09-17-package-d-a-artifact-reader-design.md`:

```markdown

### D§9 resolution, 2026-09-24 — package D-a2

All three items above are closed by
`docs/superpowers/specs/2026-09-24-package-d-a2-polygon-aggregation-design.md`:

1. **Aggregation** — a polygon is read as the unweighted mean over the valid cells
   whose coordinate values it contains, labelled `UNWEIGHTED_MEAN`, with
   `SiteReading.valid_fraction` surfaced and no threshold (D-a2 §3.2–§3.5).
2. **The empty-geometry convention** — withdrawn as recorded; the `SiteQuery`
   docstring no longer promises it.
3. **The id()-keyed cell map** — replaced by `gridded.GriddedConditions`, a frozen
   subclass carrying `cells` and `year`, which survives `dataclasses.replace`. One
   correction to item 3's stated symptom: since `d3ed04b` (before D-a2) only
   `ForcingUnavailable` excluded a species, so the eutropy path did not surface as an
   exclusion but **crashed `assess_site`** with the reader's `ValueError`. The
   per-process cache this item gated stays out of D-a2 by decision (D-a2 §1).
```

- [ ] **Step 3: Data-layer §8 row split**

In `docs/superpowers/specs/2026-09-13-dst-data-layer-design.md`, replace the single row at line 767 (the one beginning `| **E** | Map and polygon drawing |`) with three rows:

```markdown
| **E-a** | Forcing selection — **COMPLETE** (v0.10.0, `docs/superpowers/specs/2026-09-22-package-e-a-forcing-selection-design.md`) | The app reads the artifact when one is present and readable, the placeholder otherwise, and always says which, with the year and build date; no drawing, no polygon aggregation | D | 0.3 PM *(spec §13 "siting module", drawn from E's 1.5)* | E§8's seven clauses — met |
| **D-a2** | Polygon aggregation and the cell handle (`docs/superpowers/specs/2026-09-24-package-d-a2-polygon-aggregation-design.md`) — the D-a follow-up between E-a and E-b | Unweighted mean over a polygon's valid cells with the valid fraction on the reading (no threshold, D-b's); the cells and year carried on the conditions object so a nutrient scenario survives `dataclasses.replace`; the daily DIN honours the site's annual value | E-a | 0.2 PM *(spec §13 "data layer")* | D-a2 §6's eight clauses |
| **E-b** | Map and polygon drawing | `shiny_deckgl` (deck.gl/MapLibre bridge for Shiny for Python, `DrawMode` covers the polygon draw) — a **conda prerequisite from the `razinka` channel, not a pip dependency**, because every install path here is pip and it is not on PyPI; a GeoJSON-to-WKT converter; drawn geometry into the report; spec §10 instrumentation seam left in place as a named no-op hook. **Also owns:** a guard for a query far outside the artifact grid — today `GriddedForcing._nearest_index` returns the nearest edge cell for a point 500 km away with no complaint, unreachable while only `SITE_COORDINATES`' five points reach the reader, reachable the moment geometry is drawn (D-a2 §4) | D-a2 | 1.0 PM *(spec §13 "siting module")* | One fewer README stub row; seam present though unwired; a drawn polygon far outside the grid blocks with a reason rather than reading an edge cell |
```

Then in the same file, in the paragraph beginning `**Critical path:`, change `A0 → A → D → E` to `A0 → A → D → E-a → D-a2 → E-b`. `## 11. Revision history` is newest-first prose, its latest entry the paragraph beginning `**Revision 4 → 5.**` (line ~912). Insert directly above it:

```markdown
**Revision 5 → 6 (2026-09-24).** One targeted edit: §8's row E is split into E-a
(complete, v0.10.0), D-a2 (polygon aggregation and the cell handle) and E-b (drawing),
as E§9 of the E-a design required on 2026-09-22 and no package applied; E-b gains the
out-of-grid guard that D-a2 §4 found and could not own. The critical path names the
three. No other section changes.

```

- [ ] **Step 4: CHANGELOG**

Replace `[Unreleased]`'s `Nothing yet.` paragraph with:

```markdown
### Added

- **A polygon is read as the unweighted mean over its valid cells** (package D-a2,
  `docs/superpowers/specs/2026-09-24-package-d-a2-polygon-aggregation-design.md`). The
  reader parses WKT with shapely (function-locally, so a pip-only install still imports
  it), takes the cells whose coordinate values lie inside the polygon, lets the cell
  under the polygon's centroid decide coverage, and labels the reading
  `UNWEIGHTED_MEAN` only when two or more valid cells were averaged. The valid fraction
  rides on the reading with no threshold; the threshold and the salinity-weighted port
  remain package D-b's. Nothing in the app can draw a polygon until E-b, so no user-
  visible number changes.

### Fixed

- **A nutrient scenario on an artifact-backed session crashed the assessment.** The
  reader remembered a site's cell by the Python id of its `SiteConditions`, and the
  eutropy adapter's replaced copy was a stranger to it; since 0.10.0 narrowed exclusion
  to `ForcingUnavailable`, that raised out of `assess_site`. The cells and year now
  travel on a `GriddedConditions` subclass that survives `dataclasses.replace`.
- **The scenario now reaches the growth model on the artifact path.** The daily DIN
  series is the artifact's monthly field scaled so its 12-month mean equals the site's
  annual value — exactly 1.0 for an unmodified site, so no existing series moves.

### Changed

- A site read for one year refuses to produce another year's daily series; the app never
  asked for that, and the tests that did now read one site per year.
- An artifact year whose DIN averages exactly zero over a site's cells is refused as a
  data defect rather than grown on as a nitrogen-free sea.

### Known limits

- **`din_umol_l` means two things.** On the artifact path it is the 12-month mean; the
  placeholder's series *peaks* at it (annual mean about 0.725 × the value), so the same
  scenario dict means somewhat different water on the two sources. The EUTROPY adapter
  documents that scenario values are annual means and that its summer-month ensemble
  tables need converting first. Owner: D1, where the placeholder's nutrient shape is
  re-fitted against real forcing.
- The per-session artifact load of 0.10.0 stands. The id() hazard that blocked a
  process-wide cache is gone; the cache stays out pending its own design (thread safety,
  and a refresh replacing the pair under a running server).
```

In the 0.10.0 `### Known limits`, change the first paragraph's last sentence to `A process-wide cache waited on the D-a follow-up (D§9 item 3); the follow-up landed as D-a2 (see Unreleased), and the cache remains a separate design.` and the second paragraph's opening to `The eutropy nutrient-scenario path was not usable together with the artifact in this release (fixed by D-a2, see Unreleased): the reader's cell lookup keyed on ...`.

- [ ] **Step 5: Version test and full default suite**

Run: `MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest -p no:cacheprovider -q`
Expected: all PASS (the changelog heading test only checks released sections; `[Unreleased]` is free-form). Record the count.

- [ ] **Step 6: Commit**

```bash
git add src/seagarden_dst/forcing.py docs/superpowers/specs/2026-09-17-package-d-a-artifact-reader-design.md docs/superpowers/specs/2026-09-13-dst-data-layer-design.md CHANGELOG.md
git commit -m "docs: D-a2 resolves D§9; §8 row E split into E-a, D-a2, E-b; changelog

SiteQuery no longer promises the withdrawn empty-string convention. The
data-layer design's row split, owed since E§9 (2026-09-22), is applied; E-b
owns the out-of-grid guard. Unreleased names the aggregation, the crash it
closes, the DIN scaling and the din_umol_l asymmetry owned by D1.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 8: Done-when verification (controller)

**Files:** none modified unless a check fails.

- [ ] **Step 1: The eight done-when clauses, each as a command with recorded output**

```bash
# 1. spatial + default + ruff
MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest -p no:cacheprovider -m spatial tests/ -q
MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest -p no:cacheprovider -q
micromamba run -n shiny ruff check src tests app
# 2. UNWEIGHTED_MEAN is produced (test 3 exists and passes)
MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest -p no:cacheprovider -m spatial tests/test_gridded.py -q -k nine_cells
# 3. greps
grep -rn _site_cells src/ ; grep -n "^import shapely\|^from shapely" src/seagarden_dst/gridded.py
# 4.
grep -n "use the region's coordinate" src/seagarden_dst/forcing.py
# 5.
grep -n "D§9 resolution, 2026-09-24" docs/superpowers/specs/2026-09-17-package-d-a-artifact-reader-design.md
# 6.
grep -n "^| \*\*E-a\*\*\|^| \*\*D-a2\*\*\|^| \*\*E-b\*\*" docs/superpowers/specs/2026-09-13-dst-data-layer-design.md
# 7.
grep -n "D-a2\|0.725" CHANGELOG.md | head
# 8.
grep -n "ANNUAL MEANS" src/seagarden_dst/eutropy_adapter.py ; grep -n "Any other .ValueError. from a source" src/seagarden_dst/api.py
```

Expected: 1 all PASS, ruff clean; 2 PASS; 3 no output for both; 4 no output; 5, 6, 7, 8 each print at least one matching line (6 prints three).

- [ ] **Step 2: Test-count bookkeeping for the next release**

Run: `MKL_THREADING_LAYER=SEQUENTIAL micromamba run -n shiny python -m pytest -p no:cacheprovider -q --co -m spatial tests/ | tail -1` and the same without `-m spatial`; note both counts in the ledger for the release that will cite them (0.10.0 was 406 default + 107 spatial).

- [ ] **Step 3: Nothing left uncommitted**

Run: `git status --short` → expected: no output. If anything is listed, it belongs to a task above — commit it there, never leave it.

---

## Self-review

**Spec coverage.** §2 handle → Task 1. §3.1 shapely, wrapping, import scope, ImportError text, default-selection sibling → Task 3. §3.2/§3.3 table and coverage order → Task 4. §3.4 one helper, field-mean-first, bit-identity → Task 2 (pin) + Task 4 (multi-cell daily test 7). §3.5 `valid_fraction` → Task 2 (field) + Task 4 (set). §3.6 ratio, year refusal, zero guard, adapter docstring → Tasks 1 (year), 5 (ratio, zero), 6 (docstrings). §4 out-of-grid → Task 7 row E-b. §5 tests: 1, 12 → Task 1; 2 → Task 2; 9 → Task 3; 3, 4, 5, 6, 7, 10 → Task 4; 11 → Task 5; 8 → Task 6; the rewritten two-years test → Task 1. §6 done-when 1–8 → Task 8 checks each. §7 amendments → Tasks 6 and 7.

**Placeholder scan.** No TBD/TODO; every code step shows the code; Task 6 Step 2's discrimination proof uses a throwaway worktree because `git stash` is forbidden on the shared tree.

**Type consistency.** `_cell_for_site(site, year)` returns `site.cells` (Task 1) and is consumed as `cells` in `daily_forcing` (Tasks 1, 2, 5). `_conditions_at(cells, year, region)` (Task 1 signature, Task 2 body, Task 4 caller). `_interpolated_monthly(name, cells, month_years, days, scale=1.0)` (Task 2) and the `scale=` call (Task 5). `_select_cells` returns `(anchor, inside)` with `inside is None` for a POINT (Task 4). `SiteReading.valid_fraction` added in Task 2, populated in Task 4, asserted in Tasks 2 and 4. `GriddedConditions.cells` and `.year` (Task 1) asserted in Tasks 2 and 4.
