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
`tests/test_cultivation_window.py` 10, `src/seagarden_dst/forcing.py` 7,
`src/seagarden_dst/contracts.py` 2, `src/seagarden_dst/growth.py` 1. Two thirds of it is
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

`seagarden_dst/gridded.py` is new and holds `GriddedForcing`. **It is the only module in
`src/` that imports xarray**, and a test asserts exactly that, in the shape
`tests/test_refresh_isolation.py` already uses for `refresh/`.

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

### `daily_forcing`

Monthly fields **replace** the sinusoid rather than feeding it (§6.2), interpolated
linearly on day-of-year. A window that wraps past December takes January from year **Y+1**,
and **blocks when Y+1 is absent** — never wrapping back to the same year's January, which
would silently pair a late-season month with an early-season one from twelve months
earlier.

`surface_par` remains a placeholder constant whatever the source: §6.1 establishes that no
integrated Baltic product carries PAR in any form, so the artifact records it in `absent`
and the reader does not invent it.

### The NaN defect

C§3.5 assigns this to package D. Verified in the current code: if `depth_m` reaches
`api.select_method` as NaN, every `m.min_depth_m <= conditions.depth_m <= m.max_depth_m`
comparison is false, `workable` is empty, and `pool = workable or candidates` falls
through to returning a method anyway. `suitability.assess_physical` then evaluates
`not (min <= nan <= max)`, which is `True`, and returns a confident **UNSUITABLE**:
*"Depth nan m is outside the workable window"* — a definitive negative verdict
manufactured from missing data.

The unassessable path prevents this structurally, since `conditions is None` returns
early. **Both functions also gain an explicit guard**, so a NaN arriving by any other
route is loud rather than confident. Structural prevention plus a check, because a
structural argument is exactly the kind that quietly stops being true — this package's own
`join="exact"` and `.git/HEAD` defects were both of that shape.

---

## D§7 Done-when

The four the data-layer row requires:

1. A polygon query **aggregates over the polygon's cells**, not a single point.
2. A requested year the artifact lacks **blocks**, and never substitutes another.
3. A wrapping window takes January from **Y+1**, and blocks when Y+1 is absent.
4. An unassessable site returns `UNKNOWN` and **never a verdict**.

Four more the architecture needs:

5. `gridded.py` is the **only** module under `src/` that imports xarray, asserted by an
   AST scan over the whole tree — not over the one file somebody was thinking about.
6. `PlaceholderForcing` satisfies the widened protocol, and the app still works with no
   artifact present.
7. The distance to the nearest valid cell is reported, and is plausible: §6.2 measured
   0.75–1.28 km across all six regions at native resolution.
8. A NaN depth cannot produce a confident `UNSUITABLE`, proven by removing the guard and
   watching the test fail for that reason.

And the visibility §7 demands, which is the point of the mechanism:

9. The app shows a banner naming what the tool is running on, and Results and Report
   distinguish **unassessed** from **unsuitable**. A flag nothing displays is invisible
   degradation with extra steps.

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
