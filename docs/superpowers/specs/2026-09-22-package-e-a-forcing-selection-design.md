# Package E-a — Forcing Selection: the Reader Wired into the App

**Status:** design, 2026-09-22. Binding authority above it:
`docs/superpowers/specs/2026-09-13-dst-data-layer-design.md` (§5, §6.2, §7, §8 row E) and
`docs/superpowers/specs/2026-09-17-package-d-a-artifact-reader-design.md` (D§2–D§6).

## E§1 What this package is, and what it is not

Package E's row in the data-layer design carries three separable concerns: wiring the
artifact reader into the app, drawing polygons on the map, and carrying drawn geometry
into the report. They have different risk profiles, so E is split the way C and D were:

- **E-a — this package.** The app runs on the forcing artifact when one is present and
  readable, and on the placeholder otherwise, and always says which. No drawing, no
  polygon aggregation, no user interface for years.
- **D-a follow-up — between E-a and E-b.** The polygon aggregation D§4 specifies and the
  reader does not implement (see the dated amendment in the D-a design). Drawn geometry is
  exactly what produces multi-cell polygons, so it lands before drawing does.
- **E-b — after.** Polygon drawing with `shiny_deckgl`'s draw mode, a GeoJSON-to-WKT
  converter, geometry in the text report, and spec §10's instrumentation seam as a named
  no-op hook.

E-a is useful the moment the first real refresh lands on the server, and it is testable
today against the committed 3×3 fixture, which is why it goes first.

## E§2 Decisions taken with the user (2026-09-22)

| Question | Decision | Why |
|---|---|---|
| Which year does the app query? | **The latest year the artifact carries** for the yearly fields, shown beside the data-source banner. No selector. | The spec's per-year design forbids averaging years away (package B measured −57% to +179% in final biomass). A selector is UI and a new stale-assessment trigger nobody has asked for. |
| Where is the source chosen? | **In the core**, once per session, and threaded through the app. | CI's `[app,dev]` job has no xarray and the spatial job does not collect `app/tests`, so anything that opens the fixture must live under `tests/` with the spatial mark. Hidden global state (replacing the module default) would not be per session and would not survive a second worker. |
| What happens to a region with no coordinate? | **It stays on the placeholder for that site**, with a note on the context and in the banner. | EE-coastal and LT-coastal have conditions but no position; a map-only path would strand them, and a silent placeholder would be the unmarked fallback §7 forbids. |

## E§3 Components

### E§3.1 `ForcingChoice` (`forcing.py`)

A frozen record naming what the tool is running on:

```python
@dataclass(frozen=True)
class ForcingChoice:
    source: ForcingSource           # the reader, or the placeholder
    kind: Literal["artifact", "placeholder"]
    reason: str                     # why the placeholder; "" when kind == "artifact"
    year: int                       # the query year: the artifact's latest, or the placeholder's fixed year
    built_on: datetime | None       # manifest.built_on; None for the placeholder
    directory: Path | None          # where the pair was looked for
```

`kind` and `reason` are what the banner shows. `built_on` is shown too, display only:
§7's 18-month staleness rule is out of E-a's scope and recorded as such in E§7.

### E§3.2 `select_forcing` (`gridded.py`)

```python
def select_forcing(directory: Path | None = None) -> ForcingChoice: ...
```

Tries `GriddedForcing.from_directory(directory or artifact_directory())`. **It never
raises.** Each way of failing yields the placeholder with a distinct, one-sentence reason:

| Failure | `reason` names |
|---|---|
| no `manifest.json` in the directory | the directory, and that no artifact is there |
| `load_pair` refuses a torn pair (sha mismatch) | the directory and "checksum mismatch; refusing to read it" |
| unrecognised `artifact_schema_version` | the version found and the one supported |
| `ImportError` of the spatial stack (xarray/h5netcdf) | that the install has no `spatial` extra |
| any other exception from opening | the exception's class and message, so a new failure is named rather than swallowed as "placeholder" |

On success `kind == "artifact"`, `year` is the reader's last year, `built_on` is the
manifest's. The reader gains a read-only `years` property (the sorted year coordinate) so
`select_forcing` and tests do not reach into a private attribute.

### E§3.3 Region to query (`forcing.py`)

`SiteCoordinate.as_wkt() -> str` renders `POINT (lon lat)`. A module function:

```python
def region_query(region: str, year: int) -> SiteQuery | None: ...
```

returns a POINT query carrying `region=region` for a region in `SITE_COORDINATES`, and
`None` for a region with conditions but no coordinate. The reader keeps treating an
empty geometry as an error (D-a's "" convention was never implemented; the amendment
records it); the app never sends one.

### E§3.4 The context (`contracts.py`)

`SiteContext` gains `source_note: str = ""`: one sentence set only when a site fell back
to the placeholder while the session's choice was the artifact ("no confirmed position;
conditions are the sub-region placeholder"). Empty otherwise. `to_dict()` carries it.

### E§3.5 The app

- `app/state.py`: `AppState.forcing: reactive.Value[ForcingChoice]`, filled once in
  `server()` from `select_forcing()`. `_DEFAULTS` gains nothing: the choice is not user
  state and is not reset by the stale-assessment invalidation.
- `app/modules/site.py`, on **Use this site**: with `choice.kind == "artifact"` and
  `region_query(region, choice.year)` not `None`, the context is
  `SiteContext.from_reading(choice.source.reading_at(query), label=label)`; otherwise
  `SiteContext.from_region(region, label=label)` on the placeholder as today, with
  `source_note` set when the session's choice was the artifact. **Use this site remains
  the only commit.** Blocked readings (invalid cell, absent year) flow through the
  unassessable path D-a built; E-a adds no new outcome.
- `app/modules/results.py`: `run_assessment` passes `forcing=choice.source` to
  `assess_site`, so the daily forcing the growth model integrates comes from the same
  source as the conditions. The one exception is a context that fell back to the
  placeholder (`source_note` set): `assess_site` reads the daily series for the context's
  region through the source it is given, and the reader has no series for a region
  without a coordinate, so `run_assessment` passes the placeholder for that context. One
  rule, in one place, with both branches tested.
- `app/modules/_widgets.py`: `data_source_banner(choice, context=None) -> str`, replacing
  the boolean form. Artifact: "Data source: gridded forcing artifact, conditions for
  2025, built 2026-09-22." Placeholder: "Data source: placeholder conditions — plausible
  order-of-magnitude values, not measurements (no artifact at data/forcing)." With a
  context whose `source_note` is set, the note is appended. `report.py`'s data-source line
  and caveat take the same inputs.

## E§4 Data flow

```
session start:  select_forcing()  ->  state.forcing            (once)
Use this site:  region -> region_query -> reading_at -> SiteContext.from_reading
                                        \-> None  -> SiteContext.from_region (placeholder) + source_note
Assess:         assess_site(context, forcing=choice.source | placeholder if source_note)
Display:        banner(choice, context); report line(choice, context)
```

## E§5 Errors and edge cases

- `select_forcing` never raises; every fallback names its reason and the banner shows it.
- A marker region whose artifact cell is invalid becomes an unassessable site, displayed
  as such (§7 row 2, already built).
- The artifact lacks the latest year for some field: cannot happen by construction, the
  year is taken from the artifact's own coordinate. A future artifact with a partial last
  year is a refresh-side problem (C§4.4's baselines validator).
- The fixture's 3×3 grid near 54.0 N, 20.0 E contains no shipped marker. Tests that need
  a site inside it use a test-only coordinate; nothing shipped changes.

## E§6 Testing

**Core, `spatial` mark, against `tests/fixtures/data`:**
- `select_forcing(fixture_dir)` returns `kind == "artifact"`, `year == 2025`, `built_on`
  equal to the manifest's, `directory` the fixture path.
- A missing directory, a torn pair (copy the fixture, flip one byte of the artifact), and
  a manifest with `artifact_schema_version: 99` each return the placeholder with the
  reason table's wording; `match=` on a fragment unique to each row.
- `GriddedForcing.years == [2024, 2025]`.
- A POINT query inside the fixture through `select_forcing(...).source.reading_at` gives
  `from_artifact=True`; `SiteContext.from_reading` of it has `from_artifact=True` and an
  empty `source_note`.

**Core, default selection:**
- `ForcingChoice` is frozen and carries the six fields.
- `region_query` returns a POINT with `region` set for `LT-lagoon`, and `None` for
  `LT-coastal`; `SiteCoordinate.as_wkt()` renders lon then lat.
- `select_forcing` with the spatial stack absent (`sys.modules["xarray"] = None`) returns
  the placeholder naming the `spatial` extra.
- `data_source_banner` for both kinds, and with a `source_note`.
- The rule in `run_assessment`: a context with `source_note` set is assessed with the
  placeholder even when the choice is the artifact; a context without one gets the
  choice's source. Both through the `_FakeState` pattern the smoke tests already use.

**App smoke (`app/tests`, no spatial stack):**
- The app builds; with no artifact directory the banner reads placeholder and names the
  directory; `state.forcing` is a placeholder choice.
- A fake artifact choice injected into `state.forcing` flips the banner text and the
  report's data-source line.

**Manual:** `SEAGARDEN_DATA_DIR=tests/fixtures/data shiny run app.app`, a test coordinate
inside the fixture (via a monkeypatched `SITE_COORDINATES` in a scratch script, not a
shipped change), assess, screenshot the banner.

## E§7 What E-a does not do

- **No polygon aggregation** — the D-a follow-up.
- **No drawing, no GeoJSON, no geometry in the text report** — E-b.
- **No year selector, no climatology.**
- **No staleness rule.** `built_on` is displayed; §7's 18-month threshold is not enforced.
- **No change to `select_method`, `assess_physical`, or any verdict logic.**

## E§8 Done-when

1. With `SEAGARDEN_DATA_DIR` pointed at the fixture, a site inside its grid assesses from
   the artifact, `from_artifact=True` reaches the assessment, the banner says so and shows
   the year and build date.
2. Without an artifact, the app's rendered banner and report differ from today's only by
   the reason in parentheses; every existing smoke test passes unchanged except the banner
   test, which gains the choice argument.
3. A region without a coordinate assesses from the placeholder with `source_note` set and
   shown, while the session's choice stays the artifact.
4. `select_forcing` has a test per row of the reason table.
5. `run_assessment`'s source rule has both branches tested.
6. Nothing under `app/` imports xarray, rasterio or `shiny_deckgl` at module scope
   (existing guard tests).
7. README's "Site conditions" stub row records that the artifact path exists and what
   still gates it (a real artifact on the server).

## E§9 Amendments this design requires

- **D-a design**: dated amendment recording that D§4's unweighted-mean aggregation and
  D§2's empty-geometry-means-region convention are not implemented in `gridded.py`
  (added 2026-09-22 alongside this document).
- **Data-layer design §8**: E's row splits into E-a, the D-a follow-up, and E-b, with
  E-a's done-when as E§8 above.
