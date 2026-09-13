# Design — from prototype to the real data layer

*SeaGarden DST, Activity A2.3. Written 13 September 2026 (≈M4).*

Companion to `SeaGarden_DST_functional_specification_v0.1.md`, which this does not
replace. The functional specification says what the tool does and why; this says how
the next block of engineering gets built, and in what order. Where the two disagree,
the functional specification wins and this document is wrong.

---

## 1. What this covers, and what it does not

The prototype runs end to end on `forcing.PLACEHOLDER_SITES` — invented conditions,
plausible to an order of magnitude and measurements of nothing. Every number the tool
displays inherits from them. Replacing that is the largest single piece of unblocked
work, and it is the one that makes the rest of the tool mean anything.

**In scope:** the data layer (§6 of the specification), the map and polygon drawing
(§5.1), the spatial exclusion layers that feed the suitability verdict (§5.2), the
refresh tooling the durability clause obliges, and the regulatory record schema (§9.1)
as an empty structure awaiting GMU's content.

**Out of scope, deliberately:**

- §8's risk and viability modules. Decisions D5 and D6 are open until M18, and §14
  names these as the first things cut if effort runs short. Planning them now is
  planning work that probably will not happen. One timeboxed spike, described in §7
  below, produces the evidence those decisions need — so they get made on findings
  rather than on whatever effort remains.
- Registration and usage logging (§10). Decision D4 is due M18 and the registration
  model materially changes the design; the schema work is cheap enough to do after.
- Promoting parameters to tier A. That needs A3.4 pilot data, which begins arriving
  at M12 and is a data change rather than a software change by construction.

**Timing.** We are at roughly M4. The prototype belongs to the specification's Phase 1
(M12–18), so this work is running ahead of the delivery plan rather than behind it.
That slack is the reason the plan below can afford a spike and a golden-file snapshot;
it is not a reason to widen scope.

---

## 2. The central premise: no live service at runtime

The Application Form commits the Lead Partner to keeping the tool online for five
years after project end, to May 2034, with no maintenance budget. §14 already names
the matching risk: *"scraper and external-service dependencies break — silent failures
years later."*

A tool that queries Copernicus when a user draws a polygon has a dependency on an API
contract, a credential, and an organisation's continued existence, for ten years,
with nobody funded to watch any of them. So the data layer splits in two, and the
split is the most important decision in this document.

**Build time — run once a year, by hand, on a developer machine.**
`scripts/refresh_layers.py` pulls from Copernicus, EMODnet, HELCOM and EEA, extracts
seasonal climatologies onto a single Baltic grid, and writes one compact artifact plus
a provenance manifest. This is the only code that needs `rioxarray`, `rasterio` or
`geopandas`, and they stay confined to the `spatial` extra.

**Runtime — reads the artifact and nothing else.** No network. No credentials. No
service call. The core keeps its four dependencies.

The consequence worth stating: the tool is only ever as current as its last refresh,
and it must say so. That is why staleness is a displayed property of a result rather
than a fact in a log, matching §9.3's treatment of regulatory records.

---

## 3. The forcing seam

`forcing.py` today has no seam — `daily_forcing()` is a module-level function over a
hard-coded dictionary. It gains one:

```
ForcingSource (Protocol)
├── PlaceholderForcing    the current PLACEHOLDER_SITES, retained for tests and fallback
└── GriddedForcing        the climatology artifact, queried by polygon
```

`SiteConditions` and the shape of `daily_forcing()`'s return do not change. That
narrowness is what the specification already claims for this interface, and it is what
keeps `growth`, `shellfish`, `nutrients` and `suitability` untouched by this work.

### 3.1 Calendar-day indexing, and the defect it retires

The placeholder generator computes its nutrient drawdown as
`np.linspace(1.0, 0.45, days.size)` — indexed by position in the cultivation window
rather than by date. Nitrogen is therefore a property of the question asked rather than
of the site: on 1 April at DK-belt the current code returns 3.15, 3.61 or 5.00 µmol N/L
according to which species' window was requested. This is recorded as a strict `xfail`
in `tests/test_cultivation_window.py`.

Real climatologies are indexed by calendar day by construction, so `GriddedForcing`
cannot reproduce the defect. The seam work re-indexes `PlaceholderForcing` the same
way, and the `xfail` flips to a passing test.

This is why the defect is not fixed as a separate task. Any seasonal shape invented for
the placeholder would be a modelling choice with no source, and it would be discarded
the moment real data arrived.

### 3.2 The cost: the Tagalaht anchor moves

`test_fucus_reaches_the_tagalaht_reference_range` guards the only published anchor the
SE Baltic parameterisation has — 4800–5200 g DW/m² per 6 m² cage over an April–October
cycle, from OLAMUR D3.2. `mu_max` was tuned to hit it.

Changing the nitrogen every macroalga sees will move that result. So the seam package
carries an explicit re-tune of `mu_max` against the published range.

This is the one place in the plan where a coefficient is fitted to make a test pass.
It is legitimate here and nowhere else, because the anchor is the measurement and the
coefficient is the free parameter. The direction of the dependency matters: we are
fitting a parameter to an observation, not adjusting an observation to a parameter.
Any other test that moves during this work is a regression, not a re-tune.

---

## 4. The artifact

Deliberately unspecified in this document: **grid resolution and file format.** Your
machine has ~100 GB free and 16 GB of RAM, and a pan-Baltic monthly climatology across
seven variables is not obviously small. Guessing the resolution and discovering the
size afterwards is the expensive order. Package B in §6 answers it by measurement, at
two or three candidate resolutions, before packages C and D commit to anything.

What is fixed regardless:

- **One artifact, not a directory of rasters.** `.gitignore` already excludes
  `*.tif`, `*.nc` and `data/rasters/`; the artifact is a build output, reproducible
  from the refresh script, and is not committed.
- **A provenance manifest alongside it, which is committed.** Per layer: source,
  product identifier, version, retrieval date, licence, and redistribution terms.
  §6 commits the project to open *data layers*, not only open code, so a layer whose
  licence forbids redistribution must be visibly identified as referenced-not-mirrored
  and logged as a durability risk.
- **Monthly resolution.** The models consume seasonal climatology, not weather. Daily
  fields would multiply the size for precision the biology does not use.

### 4.1 Exclusion vectors are separate

MPAs, Natura 2000 sites, cables, wind farms, dredging areas and shipping density go in
their own GeoPackage, not the climatology artifact. Different refresh cadence,
different licence terms, different consumer — `suitability.assess_legal`, not
`forcing`. Merging them would couple two things that change on different clocks.

---

## 5. Failure modes

Every one follows the pattern the codebase already uses for its optional engines:
degrade visibly, never fail, and never silently substitute.

| Condition | Behaviour |
|---|---|
| Climatology artifact absent | Fall back to `PlaceholderForcing` with a banner naming what the tool is running on. The app runs; the user is not misled |
| Polygon outside grid coverage | `UNKNOWN`, which **blocks** the suitability verdict, exactly as an absent regulatory layer does. Never a silent default to a neighbouring cell |
| Artifact older than 18 months | Staleness note attached to the result, the same mechanism as §9.3's "verified on" dates |
| Refresh script fails part-way | Writes nothing. The previous artifact stays valid. There is no such thing as a half-written climatology |
| Exclusion GeoPackage absent | `legal_permissibility` returns `UNKNOWN` and blocks, which is the existing contract |

The rule underneath all five: **an absent input produces a blocked verdict, not a
permissive one.** A weighted index would let good water outvote a missing legal layer.
§5.2's minimum-of-constraints form is what makes that impossible, and these fallbacks
must not reintroduce it through the back door.

---

## 6. Work packages

| # | Package | Delivers | Depends on |
|---|---|---|---|
| **A** | Forcing seam | `ForcingSource` protocol; `PlaceholderForcing`; calendar-day indexing; `mu_max` re-tune; the `xfail` retired | — |
| **B** | Size spike | Measured artifact size at 2–3 resolutions; a resolution and format recommendation | — |
| **C** | Refresh tooling | `scripts/refresh_layers.py`; provenance manifest; licence records; fixture for tests | B |
| **D** | `GriddedForcing` | Artifact read; polygon query; aggregation to `SiteConditions`; the fallback chain of §5 | B, C |
| **E** | Map and polygon drawing | `shinywidgets` + `ipyleaflet` in `modules/site.py`; draw, assess, and the drawn geometry carried into the report | D |
| **F** | Exclusion layers | GeoPackage; `assess_legal` implemented against it; `UNKNOWN` genuinely blocking | C |
| **G** | Regulatory record schema | Pydantic model per §9.1; empty record set; "verified on" staleness display | — |

**Critical path: B → C → D → E.** A, G and the spike of §7 are independent of it. A
runs first anyway, because everything downstream is written against the seam it
creates and doing it later means writing twice.

**G is scheduled early despite having no content.** GMU's €5,500 of external legal
expertise lands at M12 across four jurisdictions. Whether that arrives as structured
records or as four PDFs depends entirely on whether a schema exists to hand them
beforehand. Half a day now; a transcription project at M12 otherwise.

---

## 7. The §8 decision spike

Decisions D5 (risk modules) and D6 (viability boundary) are due M18. §14 says these
are the first items cut. The failure mode is that they are cut by attrition — effort
runs out, nobody decides, and the tool ships without them by default.

One timeboxed spike, before M18, produces what the decisions need: for alien species
risk, whether a usable pathway dataset exists for the four jurisdictions at all; for
viability, whether OLAMUR D6.2/D6.3 have published anything borrowable. Its output is a
recommendation, not code. Anything built is labelled throwaway.

---

## 8. Testing

The existing 85 tests are the regression net. Three rules specific to this work:

**A golden-file snapshot goes in before package A.** Capture today's `assess_site()`
output for every site × species, commit it, and make A's diff reviewable. A is the one
package that will legitimately move numbers, so the movement must be visible in a diff
rather than discovered later. Every other package's snapshot diff should be empty.

**CI never touches the network.** The refresh tooling is tested against a committed
fixture of a few grid cells; the download path is exercised by hand at refresh time.
A CI job depending on an external service is a build that breaks years from now for
reasons nobody is left to diagnose — the same argument as §2, applied to the test
suite.

**Provenance is asserted, not trusted.** A test fails if any layer in the manifest
lacks a licence, a retrieval date, or redistribution terms. Under the durability
clause an undocumented layer is a legal problem, not an untidiness.

**Done, per package:** tests pass, `ruff` clean, CI green, and the README's "What is
stubbed" table has one fewer row. That table is the tool's own account of what it
cannot yet do, and shortening it honestly is the progress metric that matters.

---

## 9. What this design assumes

Stated so they can be contradicted:

- Copernicus Baltic reanalysis, EMODnet Bathymetry and EMODnet Human Activities are
  redistributable under terms compatible with the open-data commitment. If any are
  not, that layer becomes referenced-not-mirrored and §14's durability risk grows.
- Monthly climatology is sufficient for the biology. True for the growth formulation
  in §7.2; it would not be for the weather-window module in §8.3, which is out of
  scope here and would need its own forcing.
- The four doors of §4 survive D2.1's stakeholder findings at M12. If D9 resolves
  against them, package E's UI changes but the data layer does not.
- Nobody is waiting on this. If a partner deadline or a WP2 meeting needs a demo
  sooner, the ordering in §6 is the thing to revisit first.
