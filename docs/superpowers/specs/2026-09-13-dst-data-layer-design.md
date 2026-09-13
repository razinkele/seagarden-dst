# Design — from prototype to the real data layer

*SeaGarden DST, Activity A2.3. Written 13 September 2026 (≈M4). Revision 2, same day,
after a multi-agent review of revision 1 — see §11 for what changed and why.*

Companion to `SeaGarden_DST_functional_specification_v0.1.md`, which this does not
replace. The functional specification says what the tool does and why; this says how
the next block of engineering gets built, and in what order. Where the two disagree,
the functional specification wins and this document is wrong — **except** where §2
below records a deliberate fork, which is a decision to be taken rather than a defect
to be patched.

---

## 1. What this covers, and what it does not

The prototype runs end to end on `forcing.PLACEHOLDER_SITES` — invented conditions,
plausible to an order of magnitude and measurements of nothing. Every number the tool
displays inherits from them. Replacing that is the largest single piece of unblocked
work, and it is the one that makes the rest of the tool mean anything.

**In scope:** the data layer (§6 of the specification), the map and polygon drawing
(§5.1), the human-use and exclusion vectors (§5.1 and §5.2), the refresh tooling the
durability clause obliges, the regulatory record schema (§9.1) as an empty structure
awaiting GMU's content, and — added in revision 2 — a package of modelling corrections
that must land before any of it (§3).

**Out of scope, deliberately:**

- §8's risk and viability modules. Decisions D5 and D6 are open until M18, and §14
  names these as the first things cut if effort runs short. One timeboxed spike (§8)
  produces the evidence those decisions need, so they get made on findings rather than
  on whatever effort remains.
- Registration and usage logging (§10). Decision D4 is due M18. **But** package E must
  leave the instrumentation seam in place — see §7, package E's "done when".
- Promoting parameters to tier A. That needs A3.4 pilot data from M12, and is a data
  change rather than a software change by construction.
- The §5.4 scenario comparison panel. `scenarios.compare()` exists in the core and has
  no UI caller. It is deferred past this block of work and recorded as a README stub
  row rather than left to look delivered.

**Timing, stated honestly.** We are at roughly M4. A2.3 formally runs M12–30, so this
work is being done in months booked against A2.1 and A2.2. That is not slack; it is
borrowed time, and the A2.1/A2.2 deliverables come first. The consequence for this
plan is that it must survive interruption — which is why §7 carries effort figures and
§2.3 makes the refresh reproducible by someone who is not its author.

---

## 2. Three decisions to take before building

Revision 1 planned around the code as it stands. Review found that in three places the
specification and the implementation describe *different models*. These are not bugs
to patch quietly — each needs a recorded decision, and in at least one case amending
the specification is the honest resolution.

All three must be settled before package A0 (§3), because A0's regression snapshot
freezes whatever is true at that moment as the project's definition of correct.

### 2.1 Fork — elemental accounting

Specification §7.2 line 245: *"Nitrogen and phosphorus reserves tracked via Redfield
ratio; carbon fixed at 32% of dry weight."* The word *Redfield* appears exactly once in
the repository, in that sentence. `GrowthTrajectory` carries one state variable, and
`nutrients.from_harvest` applies flat tissue fractions after the fact
(`nitrogen: 0.010`).

Against the published Tagalaht figures the shipped fractions give 0.29–0.31 kg N per
cage where §7.2 reports 1.4–3.4 kg. That gap needs 4.7–11% N by dry weight, which is
implausible for *Fucus* — literature values are 1–2.5%. **So the most likely
explanation is not that the fractions are wrong but that the published figure is being
read on the wrong basis** (per cage vs per m², dry vs fresh, one cage vs the set).
That is why §3.1 re-sources the anchor before anything is fitted to it.

**Recommendation:** amend §7.2 to describe what is implemented — fixed tissue
fractions applied to harvested dry weight, sourced from macroalgal stoichiometry
(Atkinson & Smith-type, *not* Redfield, which is a plankton ratio and wrong for
macroalgae) — and do not touch the fractions until the anchor's basis is known.
Implementing a reserve pool is a structural change to the growth model and belongs to
a later re-parameterisation, if at all.

**Why it matters:** nitrogen removed is compliance item 7, and
`SpeciesOption.nitrogen_value` is the sort key for the entire ranking. This fork
decides the tool's headline output and its ordering.

### 2.2 Fork — where the salinity function acts

Three places in the repository say the salinity factor scales a maximum yield:
specification §7.2, `params.py`'s own `SalinityResponse` docstring (*"Piecewise
salinity scaling of maximum yield"*), and the text the user reads in
`suitability.py:131` (*"Salinity 18 psu scales maximum yield to X%"*). One place
disagrees: `growth.py:113` multiplies it into the ODE's specific growth rate.

At DK-belt the two readings give 36.9 against 140.1 g DW/m² — a factor of 3.8 at the
project's own Danish pilot site. `max_yield_t_fw_ha: 18.4` is declared in the schema
and in the Saccharina file, loaded, and read by nothing.

**Recommendation:** move the factor to the yield, not the rate. Three documents
already state that intent and only the code dissents; and a salinity factor multiplying
a *rate* in a logistic ODE with a constant loss term is a different and harder-to-defend
model — it makes low salinity slow growth rather than cap it. Confirm against OLAMUR
D2.3's own implementation before committing, and state the answer in §7.2.

**Consequences to carry:** no macroalga parameter file has `dry_matter`, so §7.1's
committed `t FW ha⁻¹` output cannot currently be produced and the 18.4 anchor cannot be
checked inside the tool. Adding `dry_matter` to every macroalga file is part of the
same change. Re-examine the DK-belt tier B entry at the same time: if no coefficient in
the file is fitted to Danish data, it is tier C.

### 2.3 Decision — carrying capacity and RCO116

"Carrying capacity" appears verbatim in the RCO116 output-indicator definition, and
specification §2 row 1 claims it discharged. No data source in §6, no field on
`SiteConditions`, no model and no work package produces it. Revision 1 then froze the
interface that would have to carry it.

**Recommendation:** take it as a new §11 decision rather than leaving it asserted.
Either add a tier-C proxy — HELCOM assessment products are already in §6's nutrient
row and carry eutrophication-status indicators usable as assimilative capacity, with
HELCOM PLC waterborne inputs as the load side — and a corresponding `SiteConditions`
field before package B fixes the variable list; or record explicitly which named proxy
discharges the item and agree it with the LP before D2.2. Either way §2 row 1 must
point at whatever actually produces it.

Note also that `params.py`'s existing `carrying_capacity` is a cultivation-unit term
and is not this.

---

## 3. Package A0 — corrections that must precede the snapshot

Revision 1 put the golden-file snapshot before package A and stated that any test
moving afterwards is a regression. Review's sharpest structural finding is that this
would **freeze three defects as the project's own baseline**. So a new package goes
first.

### 3.1 The Tagalaht anchor is not hit, and was never fitted

Revision 1 said *"`mu_max` was tuned to hit it"*, repeating the README. Measured:

```
simulate(fucus, PLACEHOLDER_SITES["EE-coastal"])  →  3446 g DW/m²
published anchor (spec §7.2, OLAMUR D3.2)         →  4800–5200 g DW/m²
tests/test_growth.py:69 asserts                   →  3000.0 ≤ x ≤ 5200.0
```

The model has never met the published range; the test's floor is 37% below it under a
docstring citing it; and `git log -p params/species/fucus_vesiculosus.yaml` shows
`mu_max: 0.090` introduced at the initial commit and never changed. The upper bound is
unreachable by construction because the same file sets `b_max: 5200.0 # upper Tagalaht
reference harvest` — **the carrying capacity is read off the anchor the model is
validated against**, so the anchor is not an independent check.

Fitting is possible but ill-posed: `mu_max` 0.09→0.50 moves 3446→4776, 0.8 lands at
4911, and 5.0 gives 5146 — the logistic is pinned against its own ceiling, so the
parameter is barely identifiable. Fitting one lumped coefficient in a nine-parameter
product against a single published range is a scaling convention, not a calibration,
and the design must not call it one.

**A0 therefore does not fit anything.** It does this instead:

1. **Re-source all four Tagalaht figures** from OLAMUR D3.2 with the basis stated —
   per cage or per m², dry or fresh weight, cage area, number of cages, cycle length —
   and record them as an explicit `anchors:` block in
   `params/species/fucus_vesiculosus.yaml`, so they are data rather than prose. §2.1's
   nitrogen discrepancy is resolved here or recorded as unreconciled.
2. **Set `b_max` from an independent source** — measured line loading or a standing
   stock ceiling — not from the anchor's upper end.
3. **Correct the three false sentences**: design §3.2 of revision 1, the README's
   Testing section, and the claim in commit `6d36187`.
4. **Guard the anchor as a stoichiometrically coherent set**, adding assertions on C
   and P per cage alongside dry weight, rather than on biomass alone.

Any actual re-parameterisation moves to package D1 (§7), *after* the forcing it would
be fitted against is real. Fitting coefficients to placeholder water and then refitting
them to real water is work done twice, and the first fit would silently become the
baseline the second is judged against.

### 3.2 Tier D leaks through the number-producing path

`contraindication()` correctly returns tier D for any species below its
`tolerance_floor_psu`. `harvest_biomass()` never calls it — it resolves the tier from
`calibration_for(site.region)`, and the Saccharina file lists tier D only for
`LT-coastal` and `PL-lagoon`. Measured:

| site | salinity | what `harvest_biomass` reports |
|---|---|---|
| LT-coastal | 7.0 psu | suppressed, tier D — correct |
| PL-lagoon | 2.0 psu | suppressed, tier D — correct |
| **EE-coastal** | **6.0 psu** | **"1.4–12.6 kg DW [C]"** |
| **PL-coastal** | **7.5 psu** | **"2.15–19.4 kg DW [C]"** |

EE-coastal is Tagalaht — the exact site where OLAMUR observed cultivation failure, and
the case the specification, the README and the species file all present as the worked
example of tier D.

**Scope it accurately:** `api.assess_site()` consults `contraindication()` and excludes
sugar kelp correctly at all three low-salinity sites, so the Shiny app does not show
this. The leak is in `harvest_biomass()` and therefore `scenarios.compare()` — which
the README explicitly invites ("usable from a notebook, a batch script, or another KU
MRI model chain"). It is a defence-in-depth failure: the rule is enforced at one layer
and not at the layer that produces the number.

**Fix:** `harvest_biomass` and `shellfish.harvest` resolve tier through
`contraindication()`, making the dynamic rule the single source of truth so the YAML
registry need not enumerate every region. Test: no species is reportable at any
placeholder site below its `tolerance_floor_psu`.

### 3.3 Four of five species have no lower salinity bound

Only Saccharina carries `tolerance_floor_psu`. *Fucus*, *Ulva*, *Chorda* and blue
mussel are modelled as unbounded below, so the tool returns confident yields at 2.0 psu
in the Szczecin Lagoon, where none is cultivable.

**Fix:** every species gets a `tolerance_floor_psu` and a `demonstrated_salinity_range`
recording where its parameters were actually established; `ShellfishYield` gains the
same field; `contraindication()` and `assess_environment` consult both, so
"outside the range the parameters were demonstrated in" becomes an explicit tier D
trigger rather than a silent extrapolation. Add that trigger to §7.4's tier table.

Chorda's floor is flagged assumed, like the rest of its coefficients.

### 3.4 Assessment thresholds are hard-coded against the spec's own rule

`0.35`, `0.5` and the supra-optimal temperature decline width decide suitability
verdicts from Python defaults, contradicting the specification's rule that coefficients
live in `params/`. One sits within 20% of the shipped yields for both
Application-Form species.

**Fix:** move them to `params/assessment.yaml` with sources or an explicit "assumed"
marker; add `upper_temp_decline_c` to `GrowthParams`. This lands in A0 so the snapshot
records it as a no-op diff.

---

## 4. The central premise: no live service at runtime

The Application Form commits the Lead Partner to keeping the tool online for five years
after project end, to May 2034, with no maintenance budget. §14 already names the
matching risk: *"scraper and external-service dependencies break — silent failures
years later."*

A tool that queries Copernicus when a user draws a polygon depends on an API contract,
a credential, and an organisation's continued existence, for a decade, with nobody
funded to watch any of them. So the data layer splits in two.

**Build time — once a year.** `scripts/refresh_layers.py` pulls from Copernicus,
EMODnet, HELCOM and EEA, extracts seasonal climatologies onto one Baltic grid, and
writes one artifact plus a provenance manifest. Only this code needs `rioxarray`,
`rasterio` or `geopandas`, and they stay confined to the `spatial` extra.

**Runtime — reads the artifact and nothing else.** No network, no credentials, no
service call. The core keeps its four dependencies.

### 4.1 Making the annual refresh survive its author

Revision 1 made the refresh a manual act by one unfunded person, with the layer's only
copy an uncommitted build output. That places the open-**data** half of the durability
commitment on a script that may not run in 2031. Three changes, all at zero recurring
cost, all inside package C:

1. **Archive each refresh under a DOI.** Artifact plus manifest to Zenodo — free,
   permanent, citable — with the DOI recorded in the committed manifest. This
   discharges the open-data commitment independently of whether the script still runs,
   and gives the tool a rebuildable input if a source changes. It is also the answer to
   "the artifact is a build output and is not committed", which revision 1 left open.
2. **A refresh runbook as a named deliverable of C**, written for someone who is not
   its author, including how the Copernicus credential is held — institutional, never
   personal.
3. **A scheduled source-probe job**, separate from PR CI: it only asks whether each
   source still exists and still answers, and is allowed to fail loudly without
   blocking anything. PR CI still never touches the network (§9).

Add a key-person row to §14 of the specification.

---

## 5. The forcing seam

`forcing.py` today has no seam — `daily_forcing()` is a module-level function over a
hard-coded dictionary. It gains one:

```
ForcingSource (Protocol)
├── PlaceholderForcing    today's PLACEHOLDER_SITES, retained for tests and fallback
└── GriddedForcing        the climatology artifact, queried by polygon
```

Revision 1 claimed `SiteConditions` does not change and that no downstream module is
touched. That was wrong in two ways, both now admitted:

- §5.1's human-use conflict output and §5.2's terms need fields `SiteConditions` does
  not have. Package D adds them, and the downstream touch is part of D's effort.
- The refactor changes four call sites. They are listed in package A's "done when".

### 5.1 Calendar-day indexing, and the defect it retires

The placeholder computes its nutrient drawdown as `np.linspace(1.0, 0.45, days.size)`
— indexed by position in the cultivation window rather than by date. Nitrogen is
therefore a property of the question asked: on 1 April at DK-belt the current code
returns 3.15, 3.61 or 5.00 µmol N/L according to which species' window was requested.
Recorded as a strict `xfail` in `tests/test_cultivation_window.py`.

Real climatologies are indexed by calendar day by construction, so `GriddedForcing`
cannot reproduce the defect, and re-indexing `PlaceholderForcing` the same way retires
it.

**The placeholder's seasonal shape is itself a choice, and revision 1 hid it.** §3.1 of
revision 1 argued that no seasonal shape should be invented — but re-indexing *forces*
one. So it is fixed here rather than left to the implementer:

```
din(day) = site.din_umol_l * (1.0 - 0.55 * season(day))
```

where `season(day)` is the existing solstice-centred term. This preserves the current
1.0 → 0.45 amplitude, makes nitrogen highest at midwinter and lowest at midsummer
(which is the Baltic pattern, and the direction the old code had backwards for wrapping
windows), and is a pure re-indexing of what is already there rather than a new model.
It is a placeholder and is replaced wholesale by package D.

---

## 6. The artifact

**Deliberately unspecified: grid resolution.** ~100 GB free and 16 GB RAM, and a
pan-Baltic monthly climatology is not obviously small. Package B answers it by
measurement at two or three candidate resolutions before C and D commit.

**No longer unspecified — revision 1 deferred too much.** Format, locator, variables,
statistics and aggregation are fixed here, because four of seven packages could not
have their first failing test written without them.

### 6.1 Variables, and the statistic for each

| `SiteConditions` field | Source layer | Spatial statistic | Temporal statistic |
|---|---|---|---|
| `salinity_psu` | Copernicus Baltic reanalysis | mean over polygon | monthly mean |
| `mean/summer/winter_temp_c` | Copernicus Baltic reanalysis | mean | monthly mean |
| `din_umol_l`, `dip_umol_l` | Copernicus BGC + HELCOM | mean | monthly mean |
| `surface_par` | Copernicus BGC | mean | monthly mean |
| `light_attenuation_k` | Copernicus BGC `kd490` | mean | monthly mean |
| `depth_m` | EMODnet Bathymetry | **mean, with min reported** | static |
| `significant_wave_m` | Copernicus Baltic wave hindcast | mean | **monthly 95th percentile, plus annual maximum** |

Two of these were unsourced in revision 1 — **PAR and light attenuation**, both growth
model inputs absent from the specification's §6 layer table. If `kd490` proves
unusable, both remain placeholder constants after D, and §7's failure table must then
display that fact the way staleness is displayed, not bury it.

**Waves get a percentile, not a mean**, because the same artifact feeds
`assess_physical`'s exposure test against a structural design limit, where a monthly
mean is the wrong statistic and wrong in the permissive direction. One extra band costs
nothing. Either split `significant_wave_m` into operational and extreme fields or
document which it is, and re-check `methods.yaml`'s `max_significant_wave_m` values
against the same statistic.

### 6.2 Aggregation and coverage

- **Minimum valid fraction:** if fewer than 60% of the polygon's cells are valid
  (non-land, non-NaN), the polygon is outside coverage — §7 row 2.
- **Monthly fields replace the sinusoid** in `daily_forcing` rather than feeding it;
  interpolation between monthly values is linear on day-of-year, wrapping at the year
  boundary, which the window work already supports.
- **The spatial-averaging method is a port, not a re-invention.** OLAMUR's `terra`
  salinity-weighting step is the reference; §14 already carries the risk and the
  obligation to validate the port before the numbers reach a user. It is a named
  sub-item of package D with that validation as its definition of done.

### 6.3 Locator, versioning, atomicity

- Artifact and manifest are found via `SEAGARDEN_DATA_DIR`, defaulting to `data/`, with
  fixed filenames.
- The manifest carries `artifact_schema_version` and `built_on` alongside the per-layer
  provenance. An unrecognised version is refused and degrades visibly — §7 row 6.
- Manifest and artifact are written **atomically as a pair**. There is no such thing as
  a half-written climatology.
- Per layer, committed: source, product identifier, version, retrieval date, licence,
  redistribution terms, and the Zenodo DOI of the archived copy. A layer whose licence
  forbids redistribution is visibly marked referenced-not-mirrored and logged as a
  durability risk.
- The test fixture has a committed path with a `.gitignore` exception.

### 6.4 Exclusion and human-use vectors are separate — and split in two

They go in their own GeoPackage: different cadence, different licences, different
consumers. Revision 1 then made a substantive error, routing them into
`suitability.assess_legal`. The specification reserves `legal_permissibility` for §9's
hard legal exclusions from GMU's jurisdiction records; §5.1's human-use conflicts are a
*separate* output (`overlap / adjacent / clear`, governing layer named), which revision
1 left with no owner at all.

Package F therefore splits — see §7. Shipping density must never produce a legal
verdict.

---

## 7. Failure modes

Every one degrades visibly, never fails, and never silently substitutes.

| Condition | Behaviour |
|---|---|
| Climatology artifact absent | Fall back to `PlaceholderForcing` with a banner naming what the tool is running on |
| Polygon coverage below 60% valid cells | `UNKNOWN`, which **blocks** the verdict. Never a silent default to a neighbouring cell |
| Polygon outside every calibration domain | `SiteConditions` returned with `region=None`; every quantity forced to tier C with the polygon's coordinates named |
| Artifact older than 18 months | Staleness note on the result, the mechanism of §9.3's "verified on" dates |
| Refresh fails part-way | Writes nothing. The previous artifact and manifest stay valid as a pair |
| **Artifact schema version unrecognised** | Refuse the artifact, fall back to `PlaceholderForcing`, say why — the same visible degradation as absence |
| §9 regulatory record set absent | `assess_legal` returns `UNKNOWN` and blocks, even when the human-use GeoPackage is present |

**The mechanism, which revision 1 left unexpressible.** There is today no
representation for a site whose conditions are unknown. `SiteContext.conditions`
becomes `SiteConditions | None`, and `assess_site` returns early with an explicit
`unassessable` flag; the UI reads that flag to distinguish "unsuitable" from
"unassessed". Asserted in §9's rules.

The rule underneath all of them: **an absent input produces a blocked verdict, not a
permissive one.** A weighted index would let good water outvote a missing legal layer;
§5.2's minimum-of-constraints form makes that impossible, and these fallbacks must not
reintroduce it through the back door.

A consequence worth stating plainly: with `assess_legal` returning `UNKNOWN` for every
jurisdiction until M12, **every current verdict is UNKNOWN**. The legal layer is on the
critical path for AF item 2's "maps of suitable sites", and no amount of data-layer
work moves that.

---

## 8. Work packages

Effort is indicative and drawn against §13's ~14.5 PM, which also funds four other
activities. Where a package has no §13 row, that is stated — it is an amendment to
propose, not a cost to absorb silently.

| # | Package | Delivers | Depends on | Effort | Done when |
|---|---|---|---|---|---|
| **A0** | Modelling corrections (§3) | Tier D through `contraindication()`; salinity floors for all five species; thresholds into `params/`; anchors re-sourced as data; §2's forks resolved | §2 decisions | 0.5 PM *(no §13 row — propose amendment)* | Tier-D test passes at every site below floor; `anchors:` block present with stated basis |
| **A** | Forcing seam | `ForcingSource`; `PlaceholderForcing`; calendar-day indexing per §5.1; the `xfail` retired | A0 | 0.3 PM *(§13 "model core")* | Four call sites migrated and named in the PR; snapshot diff explained line by line |
| **B** | Size + resolution spike | Artifact size at 2–3 resolutions; **and** a daily-vs-monthly forcing comparison (§10 assumption 2) | — | 0.2 PM | A committed measurement note in `docs/` with sizes, the daily/monthly delta, and a decision |
| **C** | Refresh tooling | `refresh_layers.py`; manifest; Zenodo archive; runbook; source-probe job; test fixture | B | 1.0 PM *(§13 "data layer")* | Provenance test passes against the committed fixture; runbook followed by someone else |
| **D** | `GriddedForcing` | Artifact read; polygon query; aggregation per §6; `terra` port; calibration-domain layer; `SiteConditions` extensions | B, C | 1.5 PM *(§13 "data layer" + "terra port")* | One fewer README stub row; port validated against Tagalaht and Maar et al. |
| **D1** | Re-parameterisation | The fit deferred from A0, against real forcing | D | 0.5 PM *(§13 "calibration")* | Anchor met, or the failure to meet it documented as a finding |
| **E** | Map and polygon drawing | `shinywidgets` + `ipyleaflet`; drawn geometry carried into the report; §10 instrumentation seam left in place | D | 1.5 PM *(§13 "siting module")* | One fewer README stub row; seam present though unwired |
| **F1** | Human-use overlay | `assess_conflicts()` → overlap/adjacent/clear per named layer, populating `SiteContext.activities`/`.protection`. **Descriptive only; feeds no verdict** | — | 0.5 PM | One fewer README stub row; test that it changes no verdict |
| **F2** | Hard legal exclusions | `assess_legal` returning a verdict per jurisdiction, each exclusion traceable to a named record and its "verified on" date | **G** + GMU M12 content | 0.5 PM | Absent record set still blocks, with the GeoPackage present |
| **G** | Regulatory record schema | Pydantic model per §9.1; empty record set; staleness display | — | 0.1 PM *(no §13 row)* | Schema plus one worked example record round-tripping in a test |

**Critical path: §2 decisions → A0 → A, and B → C → D → D1 → E.** F1 and G are
independent and can absorb interruption. F2 cannot start before M12 whatever happens —
revision 1 had its dependency wrong, listing C where it should be G.

**Why G stays early despite having no content.** GMU's €5,500 of external legal
expertise lands at M12 across four jurisdictions. Whether it arrives as structured
records or as four PDFs depends on whether a schema exists to hand them beforehand.
Review challenged whether a schema written before seeing legal content survives contact
with it — a fair challenge, and the mitigation is that G ships the schema *and one
worked example*, so the failure mode is a schema revised at M12 rather than a
transcription project.

---

## 9. Testing

The existing 85 tests are the regression net. Four rules specific to this work:

**The golden-file snapshot goes in after A0, not before A.** It captures
`assess_site()` **and** `scenarios.compare()` for every site × species. Revision 1 put
it first, which would have frozen §3's three defects as the definition of correct. A's
diff must then be explained line by line; every other package's snapshot diff should be
empty unless the package says otherwise.

**CI never touches the network.** The refresh tooling is tested against a committed
fixture of a few grid cells; the download path is exercised by hand at refresh time.
The source-probe job of §4.1 is separate, scheduled, and non-blocking. A PR CI job
depending on an external service is a build that breaks years from now for reasons
nobody is left to diagnose.

**Provenance is asserted, not trusted.** A test fails if any layer in the manifest
lacks a licence, a retrieval date, redistribution terms, or a DOI. Under the durability
clause an undocumented layer is a legal problem, not an untidiness.

**Anchors are guarded as sets.** Dry weight, carbon, nitrogen and phosphorus per cage,
together, so a stoichiometrically impossible combination fails rather than passing on
the one arm anybody checked.

---

## 10. The §8 decision spike

Decisions D5 (risk modules) and D6 (viability boundary) are due M18, and §14 names them
first to be cut. The failure mode is that they are cut by attrition — effort runs out,
nobody decides, and the tool ships without them by default.

One timeboxed spike before M18 produces what the decisions need: for alien species
risk, whether a usable pathway dataset exists for the four jurisdictions at all; for
viability, whether OLAMUR D6.2/D6.3 have published anything borrowable. Output is a
recommendation, not code. Anything built is labelled throwaway.

---

## 11. Assumptions, and what revision 2 changed

### 11.1 Assumptions, stated so they can be contradicted

- Copernicus Baltic reanalysis, EMODnet Bathymetry and EMODnet Human Activities are
  redistributable compatibly with the open-data commitment. If not, that layer becomes
  referenced-not-mirrored and §14's durability risk grows.
- **Monthly climatology is sufficient for the biology — now tested, not assumed.**
  Package B measures it: one Copernicus cell at daily resolution, `simulate()` driven
  by daily and by monthly-mean DIN and PAR, the difference in final biomass reported.
  It would certainly *not* hold for §8.3's weather-window module, which is out of
  scope and needs its own forcing. Note the related structural point: the model has one
  state variable and no nutrient reserve pool, so it cannot buffer short-term nutrient
  variability — which is precisely why the measurement is worth its cost.
- The four doors of §4 survive D2.1's findings at M12. If D9 resolves against them,
  package E's UI changes but the data layer does not.
- Nobody is waiting on this. If a partner deadline needs a demo sooner, §8's ordering
  is the first thing to revisit.

### 11.2 What changed from revision 1

Revision 1 was reviewed by thirteen agents across six dimensions, each finding then
adversarially verified; 27 survived, 17 were refuted. The substantive changes:

- **A false premise removed.** Revision 1 built package A on "`mu_max` was tuned to hit
  the Tagalaht anchor". It was not, the model returns 3446 against a published
  4800–5200, and the test guards a band 37% wider at the bottom. §3.1.
- **Package A0 added, and the snapshot moved behind it**, so three defects are not
  frozen as the baseline.
- **The tier-D leak found and scoped** — real in the library path, not in the app. §3.2.
- **Two forks recorded as decisions** rather than patched silently. §2.
- **Package F split into F1/F2**, correcting revision 1's routing of human-use vectors
  into the legal term, and its dependency from C to G.
- **The open-data commitment given an actual route** — Zenodo DOI per refresh — rather
  than resting on an uncommitted build output.
- **Interfaces specified enough to write a failing test from**: variables and their
  statistics, aggregation and coverage rules, locator, schema version, atomicity, and
  the `SiteConditions | None` mechanism that makes "unassessed" expressible.
- **Effort figures added**, including two packages with no §13 row, flagged as
  amendments to propose rather than costs to absorb.
- **The placeholder DIN shape written down** instead of left to the implementer, since
  anything fitted afterwards is fitted to whichever shape they chose.
- **"Slack" corrected to "borrowed time"** — this work sits in months booked to A2.1
  and A2.2.

Two findings the reviewers were clean on, recorded because a clean result is a result:
§5.2's minimum-of-constraints rule is correctly implemented and §7's fallbacks do not
reintroduce averaging; and the multiplicative `f(I)·f(T)·f(N)` composition is a
defensible inheritance from OLAMUR D3.2 — the problem is coefficient identifiability,
not the functional form.
