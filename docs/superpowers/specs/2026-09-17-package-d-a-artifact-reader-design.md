# Package D-a — the artifact reader, the query, and the unassessable path

SeaGarden Decision Support Tool — Interreg South Baltic **SeaGarden**
(STHB.02.02-IP.01-0006/25), Activity A2.3, Deliverable D2.2. Licence EUPL-1.2.

**Status:** design, 2026-09-17. Elaborates the `D` row of
`docs/superpowers/specs/2026-09-13-dst-data-layer-design.md`, which remains the binding
authority; where this document and that one disagree, that one wins and this one is
wrong.

---

## D§1 What this package is, and what it is not

The data-layer design gives package D one table row carrying four separable concerns: an
artifact reader, a ported spatial-weighting method, a data re-validation, and an
interface migration. They have different risk profiles and different done-whens, so D is
split the way package C was.

**D-a — this package.** Read the artifact, answer a polygon-and-year query, decide
coverage, and give the tool a representation for a site whose conditions are unknown.

**D-b — deferred, and deliberately.** OLAMUR's `terra` salinity-weighting port (§6.1's
"a port, not a re-invention") and the valid-fraction threshold. Both are deferred on the
argument §6.2 already used to defer the threshold: **neither does any work until a
polygon spans more than one cell**, and at the tool's own default scale none does. A
0.1 ha community farm is 31.6 m square against a native cell of 1.85 × 1.69 km — 59×
wider — so every farm polygon lies inside one cell. Multi-cell polygons arrive with
package E's drawn geometry; the port's own done-when is a validation against Tagalaht and
Maar et al., and validating a spatial average against geometry nobody has drawn measures
the invented shapes rather than the method.

**D-c — deferred.** The re-validation of every `methods.yaml` `max_significant_wave_m`
against the monthly 95th percentile. A measurement task whose output is a record, not
code, and which the data-layer row already describes completely.

**Nothing here is measured.** D-a makes the tool able to read a real artifact. Until
package C-c registers its layers and a refresh runs, there is no real artifact to read,
and the tool continues on `PlaceholderForcing` — visibly, which is D-a's job to make true.

---

## D§2 The vocabulary

Three enums and two records, all in `seagarden_dst/forcing.py` beside `SiteConditions`,
`SiteProvenance` and `SiteCoordinate`, which they are siblings of. **Pure
pydantic/stdlib/numpy**: every one of them is read by the model core and by the app, and
neither may require the `spatial` extra.

```python
class Coverage(StrEnum):
    VALID        = "valid"         # the containing cell has data
    CELL_INVALID = "cell_invalid"  # §6.2: blocks, with the distance reported
    YEAR_ABSENT  = "year_absent"   # §6.2: blocks, never substitutes another year


class Aggregation(StrEnum):
    CONTAINING_CELL   = "containing_cell"    # farm scale — the normal case
    UNWEIGHTED_MEAN   = "unweighted_mean"    # provisional, multi-cell — see D§4
    SALINITY_WEIGHTED = "salinity_weighted"  # package D-b, the Maar et al. port


@dataclass(frozen=True)
class SiteQuery:
    geometry_wkt: str   # a POINT or POLYGON; "" means "use the region's coordinate"
    year: int
    region: str | None = None


@dataclass(frozen=True)
class SiteReading:
    conditions: SiteConditions | None
    coverage: Coverage
    year: int
    aggregation: Aggregation
    nearest_valid_km: float | None = None
    from_artifact: bool = False
    stale_months: int | None = None
```

**Geometry is WKT because `SiteContext.geometry_wkt` already is.** `shapely` lives in the
`spatial` extra, so a `shapely` geometry in this vocabulary would drag that extra into the
model core — the failure this project shipped on 2026-09-17 when `app/modules/site.py`
imported a conda-only package at module scope and turned CI red at collection. A WKT
string is a plain string. `gridded.py` parses it; nothing else needs to.

**`SiteReading` exists for the same reason `SiteCoordinate` does.** That type makes
`lat, lon = coordinate` raise, because "a coordinate that travels without saying where it
came from gets promoted to a fact". Conditions that travel without their coverage status
are promoted to *assessable* in exactly the same way, and the promotion is silent: a
`SiteConditions | None` return tells a caller nothing about **why** it is `None` or how
far away data is, and §6.2 requires the distance to be surfaced. One record carries the
answer and the caveat together, and a caller that wants the numbers has to hold the
reason too.

**`stale_months`** carries §7's "artifact older than 18 months" note rather than a
separate call, for the same reason.

---

## D§3 The seam, and what migrating it costs

Package A froze this deliberately, and the data-layer row says so: *"The package A seam is
deliberately unchanged until D — `conditions_for(region)` / `daily_forcing(site, window)`
carry no polygon and no year, so D must extend it rather than merely implement it."*

```python
@runtime_checkable
class ForcingSource(Protocol):
    def reading_at(self, query: SiteQuery) -> SiteReading: ...

    def daily_forcing(
        self, site: SiteConditions, window: tuple[int, int], year: int
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]: ...
```

**`conditions_for(region)` becomes `reading_at(query)`.** The calibration domain is now
*derived* from position rather than passed in, because §7 requires a polygon outside every
calibration domain to yield `region=None` with every quantity forced to tier C — which the
caller cannot know before the lookup. `SiteQuery.region` remains as an optional hint for
the placeholder path, where a region is all there is.

**`daily_forcing` takes a year**, because §6.2's measurement refutes the climatology: a
single 12-month climatology returns *Fucus* 152.61 g DW/m² for every year against real
values of 54.74, 290.41 and 67.84 — collapsing 2023–2025 costs −57% to +179%, an order of
magnitude more than the +17.4% that monthly resolution buys.

### Migration

- `SiteContext.conditions` becomes `SiteConditions | None` — §7 names this mechanism and
  gives it to package D explicitly.
- `SiteContext.region` becomes `str | None`, for §7's outside-every-domain row.
- `assess_site` returns early with an `unassessable` flag when `conditions is None`, and
  the flag reaches the UI.
- `PlaceholderForcing` implements the widened protocol, returning `from_artifact=False`,
  `CONTAINING_CELL`, `VALID`. It has no artifact and therefore never blocks; its
  conditions are invented and say so through the existing calibration tiers.
- Every caller of the two old methods migrates. The data-layer row requires this
  explicitly, to prevent D "satisfying the old protocol while proving none of the new
  behaviour".

**The migration surface, counted rather than estimated** (occurrences of
`conditions_for` or `daily_forcing`): `tests/test_forcing_source.py` 19,
`tests/test_cultivation_window.py` 10, `src/seagarden_dst/forcing.py` 8,
`src/seagarden_dst/contracts.py` 2, `src/seagarden_dst/growth.py` 1, and
`src/seagarden_dst/params.py` 1 — that last one a docstring reference to
`forcing.daily_forcing`, which a signature change makes wrong without breaking a test. Two thirds of it is
test code, which is the good case: those tests are what stop the widened protocol being
satisfied without the new behaviour being proven. `api.py` holds `DEFAULT_FORCING` and
passes `forcing: ForcingSource` into both `assess_site` and its sibling at `api.py:72`,
so the default construction is one place, not many.

---

## D§4 Aggregation, and an honest provisional

At farm scale the polygon lies inside one cell and the answer is that cell —
`CONTAINING_CELL`, which §6.2 says **is** what "is there data here" means at this scale.

For a polygon genuinely spanning cells, D-a takes the **unweighted mean over the
polygon's valid cells** and records `UNWEIGHTED_MEAN` on the reading. This is a
provisional method, not the port: §6.1 requires the spatial average to be a port of
OLAMUR's `terra` salinity-weighting step, and D-b does that with its Tagalaht validation.

Recording the method on the reading is what makes the provisional acceptable. A result
computed by the provisional route says so, the way a calibration tier says what a number
rests on, so D-b replaces a named method rather than silently changing what every
multi-cell result meant. **The plumbing does not change when the port lands** — only which
branch `Aggregation` reports.

---

## D§5 Module boundary

`seagarden_dst/gridded.py` is new and holds `GriddedForcing`. **It is the only module
outside `refresh/` that imports xarray**, and a test asserts exactly that, in the shape
`tests/test_refresh_isolation.py` already uses.

The scope matters, and an earlier draft of this section got it wrong by claiming
`gridded.py` would be the only xarray importer in `src/` at all. Five modules under
`src/seagarden_dst/refresh/` already reference xarray — `driver.py:30`, `layer.py:18`,
`merge.py:18` and `:85`, `shapes.py:15`, `writer.py:27` — and `merge.py:85` is a real
runtime `import xarray as xr` inside `merge_layers`, not a `TYPE_CHECKING` guard. That is
correct and intended: `refresh/` is build-time tooling, already walled off from the core by
`test_no_core_module_imports_refresh`.

The property D-a actually needs is therefore about the **core**, not about `src/`: outside
`refresh/`, exactly one module is xarray-bound, and it is `gridded.py`. A test scoped to
`src/` would fail the day it was written.

This is not tidiness. The model core (`growth`, `shellfish`, `nutrients`, `suitability`)
and the app must both work on an install with no `spatial` extra — CI's `[app,dev]` job is
that install. `artifact/` was built pydantic+stdlib+numpy only for this reason, and
`artifact.pair.load_pair` deliberately returns `(Manifest, Path)` rather than an opened
dataset, leaving the open to whoever has xarray.

`GriddedForcing` is constructed only by whoever has an artifact; the core sees
`SiteReading` and never the reader.

---

## D§6 Behaviour

### Selection and fallback

The app constructs `GriddedForcing` when `SEAGARDEN_DATA_DIR` (default `data/`) holds a
pair that loads; otherwise `PlaceholderForcing`. "Loads" reuses package C-a: `load_pair`
refuses a torn pair on the sha256 that links artifact to manifest, and an unrecognised
`artifact_schema_version` is refused too. **Every refusal falls back and says why** —
§7's "degrades visibly, never fails, never silently substitutes".

### The three query outcomes

| Condition | `SiteReading` | Verdict |
|---|---|---|
| Containing cell valid | `VALID`, conditions present | proceeds |
| Containing cell not valid (§6.2) | `CELL_INVALID`, `conditions=None`, `nearest_valid_km` set | `UNKNOWN`, **blocks** |
| Artifact lacks the year (§6.2) | `YEAR_ABSENT`, `conditions=None` | `UNKNOWN`, **blocks** |
| Outside every calibration domain (§7) | `VALID`, conditions with `region=None`, all tier C | **proceeds**, tier C |

The last row is deliberately not a coverage failure. There is data; it simply falls
outside a calibration domain, which §7 handles by forcing tier C rather than blocking.

**But "all tier C" is wrong, and getting it wrong here would suppress the one verdict this
tool exists to surface.** §7's force-tier-C rule and §3.2's contraindication rule disagree
for a site that is both unlocatable and below a species' salinity floor — a 2 psu
sugar-kelp polygon with `region=None`. The data-layer design settled it at §8.1:
*"`contraindication()` wins — a salinity finding does not stop applying because the polygon
is unlocatable — and D's done-when carries the test."*

The code already behaves that way. `growth.contraindication()` resolves the floor through
`species.salinity_floor()` and returns `Calibration(tier=Tier.D, ...)` whenever
`site.salinity_psu < floor_psu`; **that branch never gates on region**. It is called
unconditionally from `suitability.py:128`, `growth.py:181`, `growth.py:214` and
`shellfish.py:86`, and `Calibration.is_reportable` is False for tier D
(`calibration.py:67-69`), so the number is suppressed in favour of the note.

So the row means: **tier C is the floor, not the ceiling.** Being outside every calibration
domain stops a result claiming better than tier C; it does not stop `contraindication()`
making it tier D. An implementer who writes the outside-every-domain test as "every
quantity comes back tier C" will see it fail against correct code, and the natural repair —
special-casing `region=None` so contraindication is skipped — deletes the OLAMUR finding
for exactly the unlocated polygons where the salinity evidence still applies.

One implementation note this raises: `species.calibration_for(region)` is called with
`site.region`, and D-a introduces `region=None`. Check what that call does with `None`
before relying on it; if it raises, the reader must resolve a default calibration rather
than pass `None` through.

### `daily_forcing`

Monthly fields **replace** the sinusoid rather than feeding it (§6.2), interpolated
linearly on day-of-year. A window that wraps past December takes January from year **Y+1**,
and **blocks when Y+1 is absent** — never wrapping back to the same year's January, which
would silently pair a late-season month with an early-season one from twelve months
earlier.

`surface_par` remains a placeholder constant whatever the source: §6.1 establishes that no
integrated Baltic product carries PAR in any form, so the artifact records it in `absent`
and the reader does not invent it.

### The NaN defect is already fixed, and that inverts the requirement

C§3.5 assigns package D a NaN-handling defect in `select_method`/`assess_physical`: a NaN
`depth_m` makes every tolerance comparison false, `pool = workable or candidates` returns
a method anyway, and `assess_physical` evaluates `not (min <= nan <= max)` as `True`,
producing a confident **UNSUITABLE** manufactured from missing data.

**That description was half stale, and this section said so wrongly once before.** The
history is worth keeping, because the claim has flipped three times and the reason it kept
flipping is instructive.

Commit `6de3b0f` put a finite-value check in `SiteConditions.__post_init__`. An earlier
draft of this section concluded the defect was therefore unreachable and the requirement
inverted. **That was wrong**: the guard filtered with `isinstance(value, (int, float))`,
and while `np.float64` subclasses Python's `float`, **`np.float32` does not** — and every
variable in the artifact is float32 (C§3.2). So the guard was blind to precisely the dtype
its own docstring is about: *"A land cell in a gridded product gives NaN for every
variable."* Reading a land cell would have constructed a `SiteConditions` holding
`np.float32('nan')` and the confident-`UNSUITABLE` path would have run exactly as C§3.5
describes.

Commit `3f0bc35` fixed it — `numbers.Real`, which numpy's scalar types register with, so
both widths are caught — with a delete proof and tests for both dtypes. **The guard is now
real**, and adding further guards to `select_method` and `assess_physical` would be dead
code that looks load-bearing.

**So the requirement for D-a is about coverage, not about NaN.** Two facts set it:

1. **The `valid` field is the authority, not NaN-detection.** C§3.5 introduced an explicit
   boolean field precisely because inferring validity from NaN is unreliable, and the
   committed fixture proves the point: its invalid cell (`valid[0,0] = False`) holds
   *finite* random values, because the fixture is synthetic. A reader that inferred
   invalidity from NaN would return conditions for that cell. `GriddedForcing` reads
   `valid` by value and never infers.
2. **Coverage is decided before construction.** `SiteConditions` raises on a non-finite
   field, so a reader that builds first and checks later turns a real land cell — where
   C§3.2 says the float32 fields *are* NaN — into a `ValueError`, which is a crash where
   §7 requires a visible block.

The two together are the requirement: consult `valid`, return `CELL_INVALID` with
`conditions=None` when it is false, and never attempt construction from a cell the mask
has already excluded.

---

## D§7 Done-when

The four the data-layer row requires:

1. A polygon query **aggregates over the polygon's cells**, not a single point.
2. A requested year the artifact lacks **blocks**, and never substitutes another.
3. A wrapping window takes January from **Y+1**, and blocks when Y+1 is absent.
4. An unassessable site returns `UNKNOWN` and **never a verdict**.

Four more the architecture needs:

5. `gridded.py` is the **only** module outside `refresh/` that imports xarray, asserted
   by an AST scan over the whole tree — not over the one file somebody was thinking about.
   Scoped to the core, not to `src/`: five `refresh/` modules already import xarray, one of
   them at runtime, and a `src/`-wide assertion would fail the day it was written.
6. `PlaceholderForcing` satisfies the widened protocol, and the app still works with no
   artifact present.
7. The distance to the nearest valid cell is reported, and is plausible: §6.2 measured
   0.75–1.28 km across all six regions at native resolution.
8. A query whose containing cell is marked invalid **blocks and does not raise**, and
   blocks on the `valid` field rather than on NaN. Two tests, because the committed fixture
   can only prove one of them: (a) against the fixture, whose invalid cell holds *finite*
   values, a query there returns `CELL_INVALID` with `conditions=None` — which fails if the
   reader infers validity from NaN instead of reading the mask; (b) against a small
   in-memory dataset carrying `np.float32('nan')` at the invalid cell, the same query
   blocks rather than raising `ValueError` from `SiteConditions`. Proven by removing the
   `valid` pre-check: (a) goes red by returning conditions, (b) by raising.

And the visibility §7 demands, which is the point of the mechanism:

9. The app shows a banner naming what the tool is running on, and Results and Report
   distinguish **unassessed** from **unsuitable**. A flag nothing displays is invisible
   degradation with extra steps.

10. **A site outside every calibration domain that is below a species' salinity floor
    still returns tier D, not tier C.** §8.1 of the data-layer design resolves the
    §7-versus-§3.2 tension this way — "`contraindication()` wins ... and D's done-when
    carries the test" — and this is that clause. The canonical case: *Saccharina* at
    2 psu with `region=None` must yield tier D, `is_reportable` False, and the note in
    place of the number. Proven by the repair that would break it: skip or downgrade
    `contraindication()` when `region is None` and watch this test go red while an
    "everything is tier C" test goes green.

Everything runs against the **committed fixture** package C-a already ships — 3 × 3 cells,
two years, every variable at its real shape, written by the same writer as a production
refresh. D-a needs no network, no credential and no real artifact.

---

## D§8 What D-a does not do

- **No `terra` port, no salinity weighting, no valid-fraction threshold** — package D-b,
  after package E produces multi-cell polygons.
- **No `methods.yaml` wave re-validation** — package D-c.
- **No polygon drawing** — package E. `SiteQuery` accepts WKT; nothing in the tool
  produces a polygon yet, and the map shipped at v0.5.0 produces points.
- **No human-use or protection overlay** — packages C1 and F1.
- **No re-parameterisation against real forcing** — package D1, which D-a unblocks.

---

## D§9 Amendment, 2026-09-22 — two D§2/D§4 claims the reader does not implement

Found while orienting package E, and recorded here so they are owned rather than
noticed:

1. **D§4's multi-cell aggregation is not implemented.** `gridded.GriddedForcing._point_of`
   reduces any `POLYGON` WKT to the mean of its vertex coordinates and every reading
   reports `Aggregation.CONTAINING_CELL`; `Aggregation.UNWEIGHTED_MEAN` is defined and
   never produced, and `tests/test_gridded.py` holds no polygon query. At farm scale the
   centroid pick is the containing cell and the label is true; for a polygon genuinely
   spanning cells the label is wrong. **Owner:** the D-a follow-up between packages E-a
   and E-b (`docs/superpowers/specs/2026-09-22-package-e-a-forcing-selection-design.md`
   E§1): point-in-polygon over cell centres, mean over the valid cells, the valid fraction
   surfaced on the reading with no threshold (§6.2 leaves the threshold to D-b).
2. **D§2's "an empty `geometry_wkt` means the region's coordinate" is not implemented.**
   `_point_of` raises `ValueError` on an empty string. Package E-a resolves regions to
   POINT queries in the app through `forcing.region_query`, and the reader keeps refusing
   an empty geometry; the convention is withdrawn rather than implemented, because the
   reader should not depend on the placeholder's coordinate table.
3. **`GriddedForcing._site_cells` keys on `id(conditions)`, not on anything the
   `SiteConditions` itself carries.** `reading_at` remembers which (row, col) produced
   a given `SiteConditions` object by its Python id, so `daily_forcing` can look the
   cell back up without re-deriving a coordinate from annual means. `eutropy_adapter`
   builds a *replaced* `SiteConditions` (via `dataclasses.replace`, to apply a nutrient
   scenario) that the reader has never seen and therefore holds no cell for, so the
   eutropy path raises `_cell_for_site`'s "daily_forcing needs a SiteConditions object
   produced by this GriddedForcing instance" through the reader - not a domain refusal
   with a caveat, an exception. Found while applying the final whole-branch review to
   package E-a (2026-09-23): `api.assess_site`'s new per-species exclusion (E§10 item 1
   of the E-a design) happens to catch this `ValueError` too, so it now surfaces as
   every ODE species being excluded with that message rather than crashing the
   assessment - a containment, not a fix. **Owner:** the D-a follow-up already named in
   item 1 above: carry the (row, col) on the reading itself, or on a wrapper around
   `SiteConditions`, rather than keying a side table on object identity. This also
   gates a per-process (rather than per-session) `GriddedForcing` cache: a shared
   instance across sessions makes the id-collision risk (a garbage-collected
   `SiteConditions` whose id is reused for an unrelated one) a real hazard rather
   than a currently-unexercised one.

