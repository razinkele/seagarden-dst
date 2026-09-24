# Changelog

SeaGarden Decision Support Tool — Interreg South Baltic **SeaGarden**
(STHB.02.02-IP.01-0006/25), Activity A2.3, Deliverable D2.2. Licence EUPL-1.2.

This file records what changed and, as importantly, **what each version can and cannot
yet be trusted to say**. Every release states its own limits, because a decision-support
tool whose caveats live only in conversation is one whose caveats get lost.

---

## [Unreleased]

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

Changes land here, not in the published sections below. When you cut the next
release, bump the two literals in `pyproject.toml` and `src/seagarden_dst/__init__.py` and
open a section for it — `tests/test_version.py` asserts the literals agree with each other
and with a matching heading here, but it cannot tell you that a merged change went
unreleased.

---

## [0.10.0] — 2026-09-23

**The app reads the artifact when one is present, and says so.**

513 tests (474 at 0.9.0): 406 in the default selection, 107 needing the `spatial` extra. CI
on Python 3.11 and 3.13 across two install states.

The release that makes the first real refresh matter: once an artifact sits where
`SEAGARDEN_DATA_DIR` points, the tool runs on it and the banner names the source, the year
and the build date. Until that refresh runs, the app is 0.9.0's app with a reason in the
banner. Nothing about what the tool computes has changed on the placeholder.

### Added

- **The app reads the forcing artifact when one is present** (package E-a). The source is
  chosen once per session in the core (`gridded.select_forcing`), never raises, and names
  every way of falling back; the Site panel and the report say which source, which year
  and which build date. Sites whose sub-region has no coordinate stay on the placeholder
  with a note. Nothing about what the tool computes has changed; with no artifact the app
  is today's app with a reason in the banner.

### Changed

- The query year now reaches the growth model. A species whose cultivation window needs a
  year the artifact does not carry is excluded with the reader's own reason
  (`ForcingUnavailable`), never a crash; a plain error from a source still fails loudly.

### Known limits

- Each session loads its own copy of the artifact (about 170 MB for the Baltic pair), and
  a session's start blocks on its checksum verification and its `xarray` load. A
  process-wide cache waited on the D-a follow-up (D§9 item 3); the follow-up landed as
  D-a2 (see Unreleased), and the cache remains a separate design.
- The eutropy nutrient-scenario path was not usable together with the artifact in this
  release (fixed by D-a2, see Unreleased): the reader's cell lookup keyed on the
  `SiteConditions` object's Python id, and the scenario builds a replaced
  `SiteConditions` the reader has never seen, so the eutropy path raises through the
  reader rather than returning a caveat (recorded in the D-a design, D§9).
- Those of 0.9.0 stand: the grid check has never met real Copernicus coordinates, and the
  map and placeholder caveats remain.

---

## [0.9.0] — 2026-09-22

**The refresh refuses a full disk before it starts.**

474 tests (465 at 0.8.0): 375 in the default selection, 99 needing the `spatial` extra. CI on
Python 3.11 and 3.13 across two install states.

One change, released on its own because the first real refresh is about to run on the
server and this is the guard that keeps it from failing at 80% of a 30 GB transfer.
Nothing on screen changes; the app still runs on placeholder conditions and says so.

### Fixed

- **The refresh refuses to start on insufficient free disk** (C§6.1), closing 0.8.0's
  known gap: less than 2 GB in the workdir or 200 MB in the target, summed when both sit
  on one filesystem, exits 1 with one line naming the directory, the need and the have.
  Nothing is downloaded first.

### Known limits

- Those of 0.8.0 stand, less the free-disk gap: no artifact is wired in, the grid check has
  never met real Copernicus coordinates, and the map and placeholder caveats remain.

---

## [0.8.0] — 2026-09-22

**The refresh registry is complete, and the refresh has a runbook.**

465 tests (413 at 0.7.0): 366 in the default selection, 99 needing the `spatial` extra. CI on
Python 3.11 and 3.13 across two install states.

A data-layer release with nothing new on screen. The tool still runs on placeholder
conditions and says so; what changes is that the refresh tooling can now build a complete
artifact, and that somebody who is not its author can run it. No real artifact has been
built yet: that is the first run the runbook describes, and it happens on the server, by
hand, after this release is deployed.

### Added

- **The fifth layer, `emodnet_bathy`** (package C-d): EMODnet's 2022 DTM, fetched as 1°
  tiles over WCS with a resumable cache, reduced onto the artifact grid as the mean and
  shallowest wet depth per cell, referenced to LAT. A refresh now produces every variable
  the manifest requires, and the registry guard is tightened to equality.
- **The annual-refresh runbook**, `docs/runbooks/annual-refresh.md`, with volumes,
  runtimes, the institutional-credential rule, and where the artifact lives on laguna.

### Changed

- Spec C§13 records a measured spike against the live EMODnet service and fixes the
  layer's decisions: dated coverage, depth = −elevation referenced to LAT, wet =
  elevation < 0, centre-binned mean and shallowest-wet min per cell, a resumable tile loop,
  a `GetCapabilities` probe.
- The reader's default data directory is `data/forcing`, matching the CLI's `--target`,
  and `SEAGARDEN_DATA_DIR` names the directory that holds the pair.

### Known limits

- **No artifact is wired in.** The app constructs the placeholder source until the first
  refresh has run and the service is pointed at it (runbook §10).
- The CLI does not yet refuse to start on insufficient free disk (C§6.1); the runbook tells
  the operator to check by hand.
- The artifact grid check has never met real Copernicus coordinates. The runbook says what
  to do if the first run fails there.
- The map limits of 0.5.0 and the placeholder caveats of 0.6.0 stand.

---

## [0.7.0] — 2026-09-19

**The app wears the SeaGarden brand.**

319 tests in the default selection (314 at 0.6.0), 94 needing the `spatial` extra. CI on
Python 3.11 and 3.13 across two install states.

A presentation release. Nothing about what the tool computes or claims has changed; every
number, tier and caveat is the one 0.6.0 produced, and the app still runs on placeholder
conditions and says so.

### Changed

- **The app wears the SeaGarden brand**, in the NiD4OCEAN DST's design language: a
  navy bar with the circular icon mark and a lime you-are-here underline, a lime Assess
  button, glass cards, navy table headers, and the full SeaGarden | Interreg South
  Baltic | EU lockup on a white strip under the sidebar, because the programme's
  communication rules require it to be visible and it cannot sit on the dark bar. All
  of it is one stylesheet (`app/www/seagarden.css`) inlined into the page; the tier
  badges and verdict pills now take their colours from it by class instead of carrying
  their own hex, and a smoke test refuses any inline colour under `app/`.

### Known limits

- Those of 0.6.0 stand: no artifact is wired in, and the map limits of 0.5.0 remain.
- The basemap and the two web fonts are fetched at runtime; offline, the page falls back
  to system fonts and the map to an empty frame.

---

## [0.6.0] — 2026-09-19

**The tool can read a forcing artifact, and can say when it cannot assess a site.**

408 tests (235 at 0.5.0): 314 in the default selection, 94 needing the `spatial` extra.
CI on Python 3.11 and 3.13 across two install states.

Package D-a lands the reader the map was waiting for. Nothing you see in the app changes
its numbers yet: the app still runs on the placeholder conditions, and now **says so** on
the Site panel and in the report. What changes is that a site can, for the first time, be
*unassessed* rather than forced to a verdict — and that the four Copernicus layers the
refresh tooling will fetch are registered (package C-c1) and watched for retirement and
version drift (package C-c2).

### Added

- **A reading vocabulary in `forcing.py`** — `SiteReading`, `Coverage`, `Aggregation`,
  `SiteQuery` — plain records the model core and the app can both import without
  xarray. Coverage is read from the artifact's `valid` field, **never inferred from
  NaN**: the committed fixture's invalid cell holds finite values, so a NaN-inferring
  reader would have returned conditions for a land cell.
- **`GriddedForcing` in `gridded.py`**, the reader for the artifact package C builds. It
  aggregates over a polygon, blocks by year, wraps windows across the year boundary, and
  builds the daily series from the monthly fields per year. It is **the only module
  outside `refresh/` that imports xarray**, and a test asserts that; the core and the app
  import cleanly on an install with no `spatial` extra.
- **The unassessable path.** `SiteContext` may now hold no conditions, and `assess_site`
  returns an assessment that is blocked, not ranked, with the coverage reason and the
  distance to the nearest valid cell when there is one. The results panel and the report
  tell *unassessed* (no data here) from *unsuitable* (data says no). A site with no
  region is still tier D when it sits below a species' salinity floor — tier C is a floor,
  not a ceiling.
- **A data-source banner** on the Site panel and a matching line and caveat in the
  report, naming whether conditions came from the gridded artifact or from placeholders.
- **The four Copernicus layers** (`copernicus_phy`, `copernicus_bgc`,
  `copernicus_bgc_light`, `copernicus_wav`) registered in the refresh tooling, with an
  injectable client seam.
- **The catalogue probe** (`refresh/sources/catalogue.py`), asking the Copernicus
  catalogue whether each `dataset_id` still exists at the version the manifest
  publishes, with a four-state `ProbeResult`. It replaces an HTTP HEAD against the
  product landing page, which returns 200 long after the dataset behind it is retired
  and says nothing about versions. It needs no credential; the probe workflow drops the
  two secrets nothing had ever read and installs the `spatial` extra instead.
- `.github/copilot-instructions.md`, corrected to the micromamba environment and the
  current module set.

### Changed

- **`ForcingSource` widens** to `reading_at(query)` and a year-aware `daily_forcing`;
  the placeholder implements both, so every existing caller runs unchanged.
- The spec corpus received dated amendments for 35 claims that had gone stale against
  the code; `docs/superpowers/specs/` is again the authority it claims to be.

### Fixed

- The non-finite guard on `SiteConditions` missed `float32`, the one dtype the artifact
  actually carries.
- The map no longer requires the conda-only `shiny_deckgl` at import time, so the
  `[app,dev]` CI job and any install without it start cleanly.

### Known limits

- **The app is not yet wired to an artifact.** `GriddedForcing` is proven against the
  committed 3×3 fixture only; no real artifact exists, and the app constructs the
  placeholder source. Every result is still a literature prior on placeholder
  conditions, and the banner says so.
- The map limits of 0.5.0 stand: no polygon drawing, two sub-regions without a position,
  basemap tiles from a CDN.

---

## [0.5.0] — 2026-09-17

**The Site panel becomes a map.**

235 tests (228 at 0.4.0), of which 55 need the `spatial` extra. CI on Python 3.11 and
3.13 across two install states.

The first release since 0.2.0 that changes something you can see. It shows **where** a
sub-region is; it does not change **what** its numbers are. Conditions remain the
placeholder constants they have been since the prototype began — plausible
order-of-magnitude values, not measurements, not read from the position on the map, and
every result derived from them is still a literature prior.

### Added

- **A map of the sited sub-regions**, over `shiny_deckgl` — the deck.gl/MapLibre bridge
  adopted at 0.4.0 and until now unused by anything. Five markers on a South Baltic
  basemap, one per sub-region that has a coordinate.
- **Provenance on every marker**, in colour, legend and tooltip. `SiteProvenance` exists
  because a coordinate that travels without saying where it came from gets promoted to a
  fact, and a pin on a map is the most *this was surveyed* presentation available. Of
  the five: **LT-lagoon is `sited`** — a position somebody chose and confirmed;
  **DK-belt, DE-coastal and PL-coastal are `snapped`** to the nearest modelled cell,
  because the published pilot coordinates are land cells in the Copernicus mask;
  **PL-lagoon is `indicative`** of the water body, a representative cell nobody gave. A
  marker that showed position without provenance would undo the type.
- **A position note under the map**, naming the selected sub-region's coordinate, its
  provenance, and what a result computed there is allowed to claim to be about.

### Changed

- **The sub-region selector stays, and still lists all seven.** `SITE_COORDINATES` omits
  a region entirely where nobody has chosen a cell — absent rather than `None`, so no
  caller can index a coordinate-shaped default and get a wrong answer. **EE-coastal and
  LT-coastal therefore have conditions and no position**, and a map-only picker would
  have stranded them. They are reachable from the selector, which says so.
- **Clicking a marker moves the selector; it does not commit the site.** `Use this site`
  remains the only action that commits, so a stray click while panning cannot change
  which site an assessment is about. The panel's contract with the model core is
  byte-identical to the selector-only version.

### Known limits

- The map is **not** package E. There is no polygon drawing, no curated layers beneath
  it, and no geometry carried into the report. Those need the artifact reader (package
  D) to have something to read.
- Two of seven sub-regions cannot be chosen on the map, as above.
- The basemap is fetched from CARTO's CDN at runtime. The tool's offline-by-2034
  premise covers the analytical core and the forcing artifact, not the basemap tiles:
  with no network the panel degrades to an empty frame and the selector still works.

---

## [0.4.0] — 2026-09-17

**The refresh tooling gets its driver — and still cannot fetch anything.**

228 tests (198 at 0.3.0), of which 55 need the `spatial` extra. CI on Python 3.11 and 3.13
across two install states.

**What this release does NOT change: anything the tool displays.** Package C-b builds the
machinery that will assemble the forcing artifact, but not the five layers that supply its
data — those are package C-c. `REGISTRY` ships empty, so `scripts/refresh_layers.py` with a
year range exits 1 without writing a file. Every site condition the app shows is still the
placeholder constant it was at 0.3.0, with the same caveats: the Tagalaht DIN placeholder
remains 5.3× the measured value and attenuation 2.0× measured, and `surface_par` remains
permanently absent rather than pending.

### Added

- **Package C-b — the layer protocol, the driver and the probe.** A five-member `Layer`
  protocol (`name`, `probe`, `build`, `provenance`, `baseline_years`) that the five real
  layers will implement; a `REGISTRY` both the driver and the probe job read, so the source
  list exists in exactly one place; and `run_refresh`, which builds each layer, merges them,
  resolves every variable's baseline window, and writes the artifact/manifest pair through
  the C-a writer. Proven end to end against synthetic layers, so no test makes a network
  call and none needs a credential.
- **An explicit `valid` field**, computed as the intersection of contributing layer
  coverage. Copernicus land-masking sits on the 2 km model grid and EMODnet bathymetry is an
  independent ~115 m product; they disagree exactly at the coastline, which is where every
  farm is. Package D will read this field rather than infer validity from whichever variable
  it happened to look at.
- **`refresh_layers.py --probe`** and `.github/workflows/source-probe.yml`, a monthly job
  deliberately separate from `ci.yml` so a dead upstream source turns that job red and
  blocks no pull request.
- **The deposit path**, exercised against a stub returning a synthetic DOI: recording it
  flips the affected layers from `pending` to `deposited` and the manifest still validates.
  No deposit is performed — a human runs that, and the runbook for it is package C-c's.
- **Three ordered guards on the way to disk**, each catching what the others cannot: a layer
  whose variables lack the artifact's spatial dimensions, a variable whose dimensions are
  individually plausible but wrong for it, and a layer set that is internally consistent and
  uniformly on the wrong grid. The manifest's own checksum and completeness rules cannot see
  a wrong *shape*, only a wrong *name*.

### Changed

- **The map library is now `shiny_deckgl`**, the project maintainer's Shiny-for-Python to
  deck.gl/MapLibre bridge, replacing `shinywidgets` + `ipyleaflet` for package E's map and
  polygon drawing. It is **not** a pip dependency: it ships on the `razinka` conda channel
  and every install path here is pip, so it is recorded as an environment prerequisite
  (`micromamba install -n shiny -c razinka shiny-deckgl`) in the README and the deploy
  runbook. Nothing imports it yet; `modules/site.py` is still the sub-region picker.

### Known limits

- `source-probe.yml` **exits 1 until package C-c registers the layers.** That is the
  empty-registry guard working as designed: a monthly check that passes while checking
  nothing is worse than no check at all. The first scheduled run will be red, and that is
  the expected state, not a regression.
- GitHub disables scheduled workflows after 60 days without repository activity. On a
  deliverable with no maintenance budget that means the probe job can stop firing silently —
  recorded in the workflow and in the C-c handoff notes, but not yet mitigated.
- Done-when clauses 1, 6, 9 and 11 of the package C design are discharged. Clause 5 is
  deliberately not claimed here: package C-a already proved the interrupted-write window
  against the writer's test seam, and the driver adds no uncovered surface. Clause 7 — the
  annual-refresh runbook followed end to end by someone who did not write it — cannot be
  discharged by any implementer and remains open.

---

## [0.3.0] — 2026-09-16

**The refresh tooling gets its foundations, and five of seven sites get a position.**
Still a prototype: the artifact these tools build has not been built yet, so nothing the
tool displays is a measurement of the site you selected. 198 tests (143 at 0.2.0), CI on
Python 3.11 and 3.13 across two install states.

### Added

- **Package C-a — the provenance manifest and its writer**, split across two packages so
  the boundary holds. `seagarden_dst.artifact` carries the schema and the reader —
  `GridSpec`, the manifest models, `load_pair`, `sha256_of` — and depends only on pydantic,
  stdlib and numpy, so package D can import it without dragging in the `spatial` extra.
  `seagarden_dst.refresh` carries the build-time writer and may import `artifact` but
  nothing else from the core. A
  `GridSpec` fixing the artifact grid, Pydantic manifest models whose rules fail at load
  rather than mid-analysis, and an atomic artifact/manifest writer. Four completeness
  validators enforce that every artifact variable is claimed exactly once, that `baselines`
  keys are exactly that claimed set, that `dataset_id` is unique across layers, and that
  every layer is reachable. Each was verified by mutation: neutralise any one and at least
  one test goes red.
- **A committed synthetic fixture** (`tests/fixtures/data/`), 3x3 cells and two years,
  written by the same code a production refresh uses. Its layers carry
  `archive.status: pending` — the state a first real refresh produces — not an invented DOI.
- **Atomicity that a filesystem can actually provide.** The spec asked for the artifact and
  manifest to be "written atomically as a pair"; no filesystem offers that. The artifact is
  replaced first and the manifest last, linked by a sha256, so an interrupted publication is
  **refused on the next read** rather than silently serving new data under old provenance.
- **Site coordinates, with how well each is known** (`forcing.SITE_COORDINATES`). Five of the
  seven regions now carry a position: `LT-lagoon` SITED, `DK-belt`, `DE-coastal` and
  `PL-coastal` SNAPPED to a model cell, `PL-lagoon` INDICATIVE. `LT-coastal` and `EE-coastal`
  have none yet. The type is deliberately not a `(lat, lon)` tuple — unpacking let a consumer
  take the numbers and drop the provenance, so `lat, lon = coordinate` now raises.
- **A deploy runbook** (`docs/runbooks/deploy.md`) for the laguna.ku.lt instance: preflight,
  update, verification and rollback, written for somebody who is not its author.
- **An import boundary that is enforced, not intended.** `refresh/` is build-time only;
  tests assert in both directions, recursively, across `src/` and `app/`, resolving relative
  imports. The one hole — a dynamic `importlib` import — is documented rather than hidden.

### Changed

- **`din_umol_l` is now a `Derivation`, not a raw field.** It is `no3 + nh4`, and nothing in
  a `LayerProvenance` could say so. A reader holding the artifact could not tell nitrate from
  nitrate-plus-ammonium, and package B measured surface DIN at 1.047 µmol/L at Tagalaht,
  where the ammonium share is not a rounding difference.
- `params/` now ships inside the built wheel. A `pip install` previously produced a package
  that could not load its own parameter files; only editable installs were ever exercised.
- `import seagarden_dst` no longer requires pandas. The core declares four dependencies and
  `scenarios.py` imported pandas at module scope, which made that declaration false.

### Fixed

- **Nine factual claims in the 0.2.0 release notes and README were wrong and are corrected.**
  The calibration tier glossary had B and C swapped — a partner reading it would have taken a
  value for one tier better calibrated than it is. The anchor-miss row named the wrong species
  and a superseded figure: *Fucus* misses, not *Saccharina*, which never runs the ODE at all.
- **A non-finite forcing series is refused before the solver sees it.** `solve_ivp` does not
  error on a non-finite derivative — it shrinks the step until it underflows, so a series
  drawn from a land cell consumed minutes of CPU and read as a performance problem.

### Known limitations

Unchanged from 0.2.0 and still the honest summary: site conditions are placeholders; surface
PAR is a **permanent** placeholder, not a pending one; significant wave height is unsourced;
*Fucus* misses its published anchor. Package C-a builds the tooling for the forcing artifact
— it does not build the artifact. One gap is recorded for the next package: nothing
validates `source`/`product_id` across layers, so a real refresh could attribute five
datasets to one Copernicus product and pass every validator. The four completeness rules
constrain `dataset_id` uniqueness and the claim union and say nothing about attribution.

---

## [0.2.0]` heading,
all of which stays true. Bump the two literals and open a new section when you cut the
next release.

---

## [0.2.0] — 2026-09-16

**Intermediate release for WP2 partners.** A checkpoint, not a milestone deliverable:
the analytical core is real and tested, and the data layer that would make its numbers
site-specific is designed but **not yet built**.

### Dependencies

`copernicusmarine>=2.4` is now declared in the `spatial` extra, which is this release's
only dependency change. `netCDF4` and `zarr` join it, because the package B spike scripts
shipped below write with both and `copernicusmarine`'s transitive `h5netcdf` only reads.

### What this release is

The analytical core, the Shiny application, a regulatory record schema, and the design
for the forcing data layer. 143 tests, CI on Python 3.11 and 3.13, `ruff` clean.

### What it is not

**Nothing the tool currently displays is a measurement of the site you selected.** Site
conditions come from `forcing.PLACEHOLDER_SITES` — hand-set constants, not data. Package
B measured one of them against the real products: at Tagalaht the placeholder DIN is
**5.3× too high** and light attenuation **2.0× too high**, while salinity is good. Those
values were deliberately **left uncorrected**, because replacing them is the data layer's
job and a hand-patch would produce a number that looks sourced and is not.

Every number the tool returns carries a **calibration tier** (A fitted locally / B fitted
elsewhere in the Baltic /
C analogue / D contraindicated) and the interface renders the tier badge in the same
element as the value, so a tier cannot be separated from the figure it qualifies.

### Added

- **Regulatory record schema** (`seagarden_dst.regulatory`, `params/regulatory/`) with a
  committed worked example. GMU's A2.2 legal expertise at M12 now has a record set to
  fill rather than a transcription project to start. `assess_legal` returns UNKNOWN
  without a layer — **an absent record blocks; it never reads as "no restrictions"**.
- **`ForcingSource` seam** threaded through every public entry point, so the placeholder
  constants can be swapped for a real artifact without touching the models.
- **Package C design** (`docs/superpowers/specs/2026-09-15-package-c-refresh-tooling-design.md`,
  revision 3): the annual refresh tooling — layer-per-dataset architecture, a provenance
  manifest, atomic artifact/manifest publication via checksum, a runbook written for
  someone who is not its author, and a probe job. **Design only. No refresh code ships in
  this release.**
- **Package B measurements** (`docs/2026-09-15-package-b-measurements.md`): what the
  Copernicus and EMODnet products actually contain, at what resolution and in what
  format, replacing two assumptions the design had been carrying.
- **Package B spike scripts** (`docs/spikes/2026-09-15-package-b/`): the measurement code
  that produced those numbers, committed verbatim rather than tidied, so the figures in the
  write-up can be reproduced rather than taken on trust. Nothing in the package imports it.
- Golden-file snapshots of every assessment, so a silent change in any number fails CI.
- A guard on the version itself (`tests/test_version.py`): `pyproject.toml` and
  `seagarden_dst.__version__` are two hand-maintained literals and a release bumps both, so
  a test now fails if they disagree or if this file does not mention the version being
  released.

### Changed

- Assessment thresholds moved out of Python defaults into `params/` — coefficients are
  data, and a threshold buried in a function signature is not reviewable by the people
  whose expertise it encodes.
- *Saccharina latissima* now follows OLAMUR D2.3's **published** yield model rather than
  a locally written ODE.
- The Tagalaht anchor became data rather than a constant, and `b_max` now declares the
  circularity in how it is set.
- Seasonal nutrient forcing is indexed by **calendar day**, making forcing a property of
  the site rather than of the query.
- Every species carries an explicit lower salinity bound, and none claims an observation
  it does not have.

### Fixed

- Cultivation windows that **wrap the year boundary** (*Saccharina*'s real October–June
  deployment) were previously mishandled.
- Tier-D provenance is now enforced where the number is produced, not only where it is
  orchestrated.
- **A non-finite forcing series is now rejected before the solver sees it.** A series drawn
  from a land cell raised nothing: `solve_ivp` does not error on a non-finite derivative, it
  shrinks the step until it underflows, so the run consumed two minutes of CPU producing
  nothing and read as a performance problem rather than a data problem. The guard sits at
  `growth.simulate`, which is a consumer of the seam rather than the seam itself — the
  first version of this note claimed every source inherited it, which was wrong. The error
  names the region and the per-array finite counts, because that is the part that would
  have saved the two minutes.
- **Non-finite site conditions are refused at construction.** The series guard above closed
  the ODE path only. *Saccharina latissima* uses the `salinity_indexed` yield model, so
  `harvest_biomass` never calls `simulate` for it and never reached that guard: a land
  cell's NaN conditions produced a harvest of `nan` kg DW carried at a **reportable** tier,
  which the interface renders as a number with a calibration badge, while the tolerance
  constraints reported *suitable* because every comparison against NaN is False. A land
  cell read as an assessable site — a false positive, and worse than the hang the first
  guard was written for. `SiteConditions.__post_init__` now rejects any non-finite field.
  That is inherited by every consumer for real: a frozen dataclass cannot be constructed
  or `dataclasses.replace`d into an invalid state, so `contraindication`, both yield
  models and package D's `GriddedForcing` are all covered without calling anything.

### Known limitations

| Limitation | Consequence | What unblocks it |
|---|---|---|
| Site conditions are placeholders | Ordering is by nitrogen removed, whose *Fucus* fraction is itself marked ASSUMED — so the ranking is not independent of the softest number in the model | Package **D** wires the artifact into `SiteConditions`; C only builds it |
| **Surface PAR is a permanent placeholder** | Light-limited growth carries an unsourced input | **Nothing in the current layer set** — no integrated Baltic product carries PAR in any form |
| Significant wave height is a placeholder | The exposure test in `assess_physical` is unsourced | Package C's wave layer (~26 GB transfer, the most likely thing to be cut), then package **D** to read it |
| *Fucus* yield misses its own anchor | Returns 2797 g DW/m² against a published 4800–5200 | `mu_max` has never been fitted to the anchor; deciding what is fitted is open |
| NaN depth produces a confident UNSUITABLE | A definitive negative verdict manufactured from missing data | Package D; recorded and owned, reachable once a real artifact is read |
| *Chorda filum* coefficients are assumed | Tier C in every region | A3.4 harvest data |

### What we need from partners

Four decisions are blocking, and none can be resolved by writing more code:

1. **Salinity fork** (spec §7.2) — open since 13 September.
2. **Carrying capacity** (data-layer design §2.3, *not* the functional spec — §2 there is
   the compliance matrix and has no subsections).
3. **Per-species salinity ranges** — review of the bounds now enforced.
4. **Regulatory content** for four jurisdictions — GMU A2.2, due M12. The schema is ready;
   the wiring is not. `suitability.assess_legal` returns UNKNOWN for an absent layer and
   raises `NotImplementedError` for any populated one, so records arriving at M12 need
   package F2 before they can reach a verdict.

### Verification

`pytest` — 143 passed. CI green on 3.11 and 3.13. Every design decision in this release
has a commit message stating what was measured or refuted, and design revisions record
the claims they retire rather than silently replacing them.

---

## Before 0.2.0

**No version was released before this one.** The package declared `0.2.0.dev0` from its
first commit (`ac55608`, 13 September 2026 — analytical core, Shiny application, 76
tests, CI), so there is no 0.1.0 to point at and this file does not invent one. That
prototype was built on the NiD4OCEAN DST architecture, which had already been through a
full deliverable cycle.
