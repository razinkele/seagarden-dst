# Design — from prototype to the real data layer

*SeaGarden DST, Activity A2.3. Written 13 September 2026 (≈M4). **Revision 4**, same
day, after three rounds of multi-agent review. §11 records what changed and why. Round 3
judged the substance settled and recommended targeted edits rather than a fourth rewrite;
this revision is those edits, plus §8.1's traceability pass. No further review round is
planned — the next step is the implementation plan.*

Companion to `SeaGarden_DST_functional_specification_v0.1.md`. That document says what
the tool does and why; this says how the next block of engineering gets built, and in
what order. Where the two disagree the specification wins and this document is wrong —
**except** where §2 records a deliberate fork, which is a decision to take rather than a
defect to patch.

**Reference convention:** `spec §N` means the functional specification. A bare `§N`
means this document.

---

## 1. What this covers, and what it does not

The prototype runs end to end on `forcing.PLACEHOLDER_SITES` — invented conditions,
plausible to an order of magnitude and measurements of nothing. Every number the tool
displays inherits from them. Replacing that is the largest unblocked piece of work, and
the one that makes the rest of the tool mean anything.

**In scope:** the data layer (spec §6), the map and polygon drawing (spec §5.1), the
human-use and exclusion vectors (spec §5.1, spec §5.2), the refresh tooling the durability
clause obliges, the regulatory record schema (spec §9.1) as an empty structure, and a
package of modelling corrections (§3).

**Ordering claim, stated precisely.** §3's corrections must land before the golden-file
snapshot and before package A. The data-layer chain B → C → D is independent of them
and can run in parallel. Revision 2 said the corrections precede *everything*; that
overstated it and contradicted §8's own table.

**Out of scope, deliberately:**

- Spec §8's risk and viability modules. Decisions D5 and D6 are open until M18 (D6 is
  due M20), and spec §14 names these as the first things cut. §10's spike produces the
  evidence those decisions need.
- Registration and usage logging (spec §10). Decision D4 is due M18. **But** package E
  must leave the instrumentation seam in place — see its "done when".
- Promoting parameters to tier A. Needs A3.4 data from M12; a data change by
  construction.
- The spec §5.4 scenario comparison panel. `scenarios.compare()` exists in the core with
  no UI caller. Deferred, and recorded as a README stub row by package A0 — revision 2
  claimed it was already recorded there, and it was not.

**Timing, stated honestly.** We are at ≈M4. A2.3 formally runs M12–30, so this work sits
in months booked against A2.1 and A2.2, whose deliverables come first. That is borrowed
time, not slack. The consequence: this plan must survive interruption, which is why §8
carries effort figures and §4.1 makes the refresh reproducible by someone who is not its
author.

---

## 2. Three decisions to take before package A0

In three places the specification and the implementation describe *different models*.
Each needs a recorded decision; in at least one, amending the specification is the
honest resolution.

**Owner: KU (A2.3 lead). Due: before A0 starts.** If OLAMUR D3.2 and D2.3 cannot be
obtained in time, the fallback for each is stated below — none of these blocks
indefinitely.

### 2.1 Fork — elemental accounting

Spec §7.2 line 245: *"Nitrogen and phosphorus reserves tracked via Redfield ratio;
carbon fixed at 32% of dry weight."* The word *Redfield* appears exactly once in the
repository, in that sentence. `GrowthTrajectory` carries one state variable, and
`nutrients.from_harvest` applies flat tissue fractions after the fact.

Against the published Tagalaht figures, computing every arm from the same published dry
weight — a fraction-consistency check against OLAMUR's own numbers, not a run of
`simulate()`. (That is a different question, `Anchor.reconciles`, answered per-arm in the
YAML's `anchors:` block; the two need not agree, and today they do not.) The table below
is kept in step with the `notes:` block in `params/species/fucus_vesiculosus.yaml`, which
carries this arithmetic on both the kelp fractions Fucus originally shipped with and the
Fucus-specific fractions that replaced them:

| arm | previously (kelp fractions, byte-copied from Saccharina) | now shipped (Fucus-specific, assumed) | published (spec §7.2) | verdict |
|---|---|---|---|---|
| phosphorus | 49.0–53.0 g | 57.6–62.4 g | 15–120 g | inside, both ways |
| carbon | 9.22–9.98 kg | 8.93–9.67 kg | 10–13 kg | still marginally below |
| nitrogen | 0.288–0.312 kg | 0.576–0.624 kg | 1.4–3.4 kg | narrows from **4.5–11× low** to **2.3–5.5× low** |

**Revision 2 concluded the published figure was misread on the wrong basis. That
conclusion does not survive its own arithmetic**: a basis error is a single
multiplicative factor and would move all four arms together. This pattern — one inside,
one marginal, one out by an order of magnitude — cannot be produced by any single
factor. So re-sourcing the anchor (§3.1) may *not* resolve it, and the nitrogen
discrepancy has to be recorded as unexplained until it is.

**Part of the gap is now explained, and it is a defect rather than a basis error.**
*Fucus*'s elemental block is **byte-identical to Saccharina's** — `nitrogen: 0.010`,
`phosphorus: 0.0017`, `carbon: 0.32` — which
`../Relevant projects/OLAMUR-solutions-for-SeaGarden.md` §3 labels explicitly as *"Kelp
DM → 1% N, 0.17% P, 32% C"*. *Chorda* and *Ulva* each carry their own values, Ulva's with
a comment noting its N is markedly higher than kelp. So *Fucus* is silently running on
kelp's stoichiometry. Published *Fucus vesiculosus* tissue N is roughly 1.5–2.5% of dry
weight; at 2% the nitrogen arm doubles to ≈0.6 kg and the gap narrows from 4.5–11× to
about 2.3–5.5×. It does not close, so the anchor still needs re-sourcing — but "do not
change the fractions", which revision 3 recommended, was wrong.

**Recommendation:** (a) re-source *Fucus*'s three fractions from *Fucus* literature, or
mark them explicitly `assumed: kelp values, not Fucus` as Chorda's coefficients are
marked; (b) amend spec §7.2 to describe what is implemented — fixed tissue fractions on
harvested dry weight, **not** Redfield, which is a plankton ratio and wrong for
macroalgae; (c) record whatever gap remains in the Fucus YAML where it will be seen.

**Fallback if D3.2 is unobtainable:** do (a) and (b) anyway — neither depends on it —
mark the nitrogen arm "unreconciled, published figure not verifiable at source", and do
not assert the N number as validated anywhere.

**Why it matters:** nitrogen removed is compliance item 7, and
`SpeciesOption.nitrogen_value` is the ranking's sort key.

### 2.2 Fork — where the salinity function acts

Three places say the factor scales a maximum yield: spec §7.2, `params.py`'s
`SalinityResponse` docstring (*"Piecewise salinity scaling of maximum yield"*), and the
string the user reads at `suitability.py:131`. One disagrees: `growth.py:113` multiplies
it into the ODE's specific growth rate.

**"Move it to the yield" is not one model but two, and revision 2 named only one.**
Measured at DK-belt (factor 0.611 at 18 psu):

| reading | Saccharina final biomass |
|---|---|
| current — factor in the growth **rate** | 36.90 g DW/m² |
| factor post-multiplies the **harvest** | 140.13 g DW/m² |
| factor scales **`b_max`** | 208.55 g DW/m² |

The last two diverge by 49% because the trajectory peaks at 229 against `b_max` 2000, so
the logistic term barely binds and scaling the ceiling does almost nothing until it
does. The three readings span a factor of 5.6.

**Resolved — the source is already in the repository, and none of the three readings is
it.** `../Relevant projects/OLAMUR-solutions-for-SeaGarden.md` §3 records D2.3's actual
implementation:

> *"Sugar kelp: modelled purely as a function of salinity — `f_salinity = 1 (S≥25);
> 1+(S−25)/18 (16≤S<25); S/32 (S<16)`, multiplied by a max yield of 18.4 t-FW/ha from
> Danish >16 psu sites."*

OLAMUR runs **no growth ODE for Saccharina at all.** It is a direct salinity-indexed
yield model. So there is a fourth reading, and it is the published one:

| reading | Saccharina at DK-belt |
|---|---|
| current — factor in the growth **rate** | 36.90 g DW/m² ≈ 3.1–3.7 t FW/ha |
| post-multiply the **harvest** | 140.13 g DW/m² ≈ 11.7–14.0 t FW/ha |
| scale **`b_max`** | 208.55 g DW/m² |
| **OLAMUR D2.3 as published** | **f(18) × 18.4 = 0.611 × 18.4 = 11.24 t FW/ha** |

**Decision, and it is a fork from spec §7.2 rather than an implementation of it.**
Saccharina's yield comes from `f_salinity × max_yield_t_fw_ha`, not from the ODE. That
makes `max_yield_t_fw_ha: 18.4` the model rather than dead data, and it means the ODE is
not used for this species — which is coherent with spec §5.3's treatment of Saccharina as
the worked tier D case rather than a species the tool models in detail.

The post-multiply reading lands within 4% of the published figure, so either is
defensible in practice; but the published one is what the source says, needs no
justification, and makes the 18.4 parameter checkable. **Recommendation: implement the
published form for Saccharina**, and note in spec §7.2 that the ODE governs the other
three macroalgae.

**The DK-belt entry should move from tier B to C regardless**, because no coefficient in
the file is fitted to Danish data — a published yield figure from Danish sites is a
literature prior, not a local calibration. That re-examination is part of A0.

**Consequences to carry:** no macroalga file has `dry_matter`, so spec §7.1's committed
`t FW ha⁻¹` output cannot be produced and `max_yield_t_fw_ha: 18.4` cannot be checked
inside the tool. Adding `dry_matter` to all four macroalga files and a test against 18.4
are part of A0, not aspirations.

### 2.3 Decision — carrying capacity and RCO116

"Carrying capacity" is named verbatim in the RCO116 definition and spec §2 row 1 claims
it discharged. No source in spec §6, no field on `SiteConditions`, no model and no
package produces it.

**Recommendation:** record it as a new decision in spec §11. Either add a tier-C proxy —
HELCOM assessment products are already in spec §6's nutrient row, with HELCOM PLC
waterborne inputs as the load side — plus a `SiteConditions` field, **which package B's
measurement window has now closed on**: B has run against §6.1's table as it stood, so a
field added now is unmeasured and either C re-measures for it or it ships untested; or
record which named proxy
discharges the item and agree it with the LP before D2.2. Either way spec §2 row 1 must
point at what produces it.

**One caution, because the word is doing two jobs.** A HELCOM eutrophication-status class
is not carrying capacity for extractive culture — for a mussel or seaweed farm the sign is
inverted, since high nutrient status raises the yield and the nutrient-removal benefit
rather than limiting the activity. Shipping eutrophication status under the label
"carrying capacity" would re-display AF item 1 under item 4's name. If a proxy is adopted
it must be labelled as what it is (nutrient status, or assimilative capacity for the water
body) and the RCO116 claim in spec §2 written to match, not the other way round.

`params.py`'s existing `carrying_capacity` is a cultivation-unit term and is not this.

---

## 3. Package A0 — corrections that must precede the snapshot

Revision 1 put the golden-file snapshot first and declared any later test movement a
regression, which would have frozen the defects below as the project's own definition of
correct.

### 3.1 The Tagalaht anchor is not hit, and was never fitted

```
simulate(fucus, PLACEHOLDER_SITES["EE-coastal"])  →  3446 g DW/m²
published anchor (spec §7.2, OLAMUR D3.2)         →  4800–5200 g DW/m²
tests/test_growth.py:69 asserts                   →  3000.0 ≤ x ≤ 5200.0
```

The model has never met the published range; the test's floor is 37% below it under a
docstring citing it; `mu_max: 0.090` has carried its initial value since the first
commit. The upper bound is unreachable by construction because the same file sets
`b_max: 5200.0 # upper Tagalaht reference harvest` — **the carrying capacity is read off
the anchor the model is validated against**, so the anchor is not an independent check.

Fitting is possible but ill-posed: `mu_max` 0.09→0.50 moves 3446→4776; 0.8 gives 4911;
5.0 gives 5146. The logistic is pinned against its own ceiling, so the parameter is
barely identifiable. Fitting one lumped coefficient in a nine-parameter product against
a single published range is a scaling convention, not a calibration.

**A0 fits nothing.** It does this:

1. **Re-source all four Tagalaht figures** from OLAMUR D3.2 with the basis stated — per
   cage or per m², dry or fresh, cage area, number of cages, cycle length — recorded as
   an `anchors:` block in `params/species/fucus_vesiculosus.yaml` so they are data, not
   prose. §2.1's nitrogen gap is resolved here or recorded as unexplained.
2. **Set `b_max` from an independent source.** Candidates, in preference order: measured
   line loading from A3.2's as-built system design; a standing-stock ceiling from the
   *Fucus* literature; failing both, keep 5200 but mark it `assumed: derived from the
   anchor` so the circularity is visible in the data rather than hidden in it.
3. **Correct the surviving false sentences.** The README's Testing section and revision 1
   of this document were corrected in commit `dcad5b3`. Three remain, all written on
   13 Sep 2026 and all asserting a re-tune that never happened:
   - `README.md:146` — "Fixing it moves the Tagalaht anchor, so the `mu_max` re-tune goes with it"
   - `src/seagarden_dst/forcing.py:170` — "so the mu_max re-tune belongs to the same change"
   - `tests/test_cultivation_window.py:140` — the same claim inside the strict xfail reason

   Commit `6d36187`'s message is published history and cannot be amended; the README's
   Testing section records that it is superseded.
4. **Correct the stale 3.61 figure** wherever it appears (`forcing.py`, the xfail reason,
   this document) — see §5.1.
5. **Guard the anchor as a set** — dry weight, carbon and phosphorus per cage, with
   nitrogen asserted only once §2.1 is resolved. Carbon currently fails the set guard
   (8.93–9.67 against 10–13 kg, fraction consistency against the published dry weight —
   §2.1), so "assert the arms that reconcile" is today true of phosphorus alone, and A0
   must say so rather than implying three clean arms.

Any actual re-parameterisation moves to package D1, *after* the forcing it would be
fitted against is real.

**`tests/test_growth.py:69` is not touched by A0.** Narrowing 3000–5200 toward the
published range only makes sense once the anchor is re-sourced and the fit attempted, so
the assertion moves in D1. Until then its docstring is amended to state that the bound is
looser than the range it cites and why.

### 3.2 Tier D leaks through the number-producing path

`contraindication()` correctly returns tier D for any species below its
`tolerance_floor_psu`. `harvest_biomass()` never calls it — it resolves the tier from
`calibration_for(site.region)`, and the Saccharina file lists tier D only for
`LT-coastal` and `PL-lagoon`.

**Five placeholder sites sit below the 16 psu floor. Three of them leak.** Measured at
`area_m2=1000` (the 0.1 ha default), rendered through `for_display`, whose tier-C banding
is ÷3 / ×3:

| site | salinity | what `harvest_biomass` reports |
|---|---|---|
| PL-lagoon | 2.0 psu | suppressed, tier D — correct |
| EE-coastal | 6.0 psu | **"1.4–12.6 kg DW [C]"** |
| LT-coastal | 7.0 psu | suppressed, tier D — correct |
| PL-coastal | 7.5 psu | **"2.15–19.4 kg DW [C]"** |
| **DE-coastal** | **11.0 psu** | **"4.52–40.7 kg DW [C]"** — the largest leak |

EE-coastal is Tagalaht, the site where OLAMUR observed cultivation failure and the case
the specification, README and species file all present as the worked example of tier D.

**Scope, accurately:** `api.assess_site()` consults `contraindication()` and excludes
sugar kelp correctly, so the Shiny app does not show this. The leak is in
`harvest_biomass()` and therefore `scenarios.compare()` — which the README invites
notebook use of. It is a defence-in-depth failure: the rule is enforced at one layer and
not at the layer that produces the number.

**Fix:** `harvest_biomass` and `shellfish.harvest` resolve tier through
`contraindication()`, so the dynamic rule is the single source of truth and the registry
need not enumerate regions. Test: nothing is reportable at any placeholder site below its
floor.

### 3.3 Four of five species have no lower salinity bound

Only Saccharina carries `tolerance_floor_psu`. *Fucus*, *Ulva*, *Chorda* and blue mussel
are unbounded below, so the tool returns confident yields at 2.0 psu in the Szczecin
Lagoon, where none is cultivable.

**Revision 2 got the remedy wrong and it is corrected here.** It proposed making
"outside the demonstrated salinity range" a tier D trigger. That contradicts spec §7.4,
which this document says wins: tier D is *"a local finding contradicts the model"*; tier
B is *"fitted elsewhere in the Baltic at comparable salinity"*; tier C is *"published
parameters, no local validation"*. Extrapolation is B or C — it is not a contradicting
finding. Applied literally, the rule would make *Fucus* tier D at LT-coastal (7.0 psu),
PL-coastal, DE-coastal and DK-belt — everywhere except Tagalaht, including the project's
own primary site — and would break the passing
`test_harvest_carries_its_calibration`, which asserts tier C for exactly that pairing.

**Two distinct mechanisms, kept distinct:**

| trigger | tier | basis |
|---|---|---|
| Below `tolerance_floor_psu` — a floor — observed or assumed — of cultivation failure | **D** | spec §7.4's own definition |
| Outside `demonstrated_salinity_range` — extrapolation | **B or C**, with the distance from the demonstrated range named in the note | spec §7.4 rows B and C |

Anything short of tier D puts a confident-looking number back at 2.0 psu, which is the
defect section 3.3 exists to remove, and a siting tool should fail safe; the
observed/assumed distinction is carried in the note the user reads, not in the tier.

A0 therefore adds `tolerance_floor_psu` to all five species (and to `ShellfishYield`),
sourced where possible and flagged assumed where not, as Chorda's coefficients are; and
adds `demonstrated_salinity_range` as *provenance that widens the displayed band*, never
as a tier D trigger. The specification's tier D row (§7.4) has since been amended to
name the floor mechanism explicitly; the table above now matches it.

### 3.4 Assessment thresholds are hard-coded against the spec's own rule

`0.35`, `0.5` and the supra-optimal temperature decline width decide suitability verdicts
from Python defaults, contradicting the rule that coefficients live in `params/`.

One of them binds tightly: Ulva's shipped yields are 0.461–0.771 kg DW/m² across the
placeholder sites against a 0.5 floor. Revision 2 said this affected "both Application
Form species" — it does not. Blue mussel is routed around both thresholds by
`suitability.py:150` because it is shellfish, which is itself worth recording.

**Fix:** move them to `params/assessment.yaml` with sources or an explicit "assumed"
marker; add `upper_temp_decline_c` to `GrowthParams`. Landing this in A0 means the moved
constants are baked into the snapshot baseline rather than appearing as a diff later.
Revision 2 claimed the snapshot would show a no-op diff — impossible once the snapshot
moved behind A0, and the claim is withdrawn. The check that it is behaviour-preserving is
that the values are identical, asserted in A0's done-when.

---

## 4. The central premise: no live service at runtime

The Application Form commits the Lead Partner to keeping the tool online to May 2034 with
no maintenance budget. Spec §14 names the matching risk: *"scraper and external-service
dependencies break — silent failures years later."*

A tool that queries Copernicus when a user draws a polygon depends on an API contract, a
credential and an organisation's continued existence, for a decade, with nobody funded to
watch any of them. So the layer splits.

**Build time — once a year.** `scripts/refresh_layers.py` pulls from Copernicus, EMODnet,
HELCOM and EEA, extracts **per-year monthly fields** (§6.2, not a single climatology) onto
one Baltic grid at native ~2 km, writes one NetCDF4 artifact plus a provenance manifest. Only this code needs `rioxarray`, `rasterio` or `geopandas`, confined
to the `spatial` extra.

**Runtime — reads the artifact and nothing else.** No network, no credentials, no service
call. The core keeps its four dependencies.

### 4.1 Making the annual refresh survive its author

Revision 1 made the refresh a manual act by one unfunded person, with the layer's only
copy an uncommitted build output — placing the open-**data** half of the durability
commitment on a script that may not run in 2031. Three changes, all zero recurring cost,
all inside package C:

1. **Archive each refresh under a DOI.** Artifact plus manifest to Zenodo — free,
   permanent, citable — the DOI recorded in the committed manifest. This discharges the
   open-data commitment independently of whether the script still runs. *Constraint to
   check in C:* Zenodo's standard per-file limit is 50 GB, which package B's resolution
   decision must respect; and a layer that forbids redistribution cannot be archived at
   all, which is why §9's provenance test accepts a marker in its place.
2. **A refresh runbook as a named deliverable**, written for someone who is not its
   author, including how the Copernicus credential is held — institutional, never
   personal.
3. **A scheduled source-probe job**, separate from PR CI, which only asks whether each
   source still exists and answers, and may fail loudly without blocking anything.

Add a key-person row to spec §14.

---

## 5. The forcing seam

`forcing.py` has no seam today — `daily_forcing()` is a module-level function over a
hard-coded dictionary. It gains one:

```
ForcingSource (Protocol)
├── PlaceholderForcing    today's PLACEHOLDER_SITES, retained for tests and fallback
└── GriddedForcing        the forcing artifact, queried by polygon and year
```

Revision 1 claimed `SiteConditions` does not change and no downstream module is touched.
Both were wrong:

- Spec §5.1's human-use output and spec §5.2's terms need fields `SiteConditions` lacks.
  Package D adds them; the downstream touch is part of D's effort.
- The refactor's call-site count was wrong in both directions, and the corrected set is
  what package A's done-when requires the PR to name. `contracts.py:56` and `:60`
  collapse to **one** edit — a two-method protocol has no membership operation, so the
  guard and the lookup both become `forcing.conditions_for(region)`. Against that,
  `growth.py` needs **two** edits, not one: `simulate()` *and* `harvest_biomass()`,
  because `assess_site` reaches the ODE only through the latter, so threading the
  former alone leaves a seam nothing can reach. With the additive re-export in
  `__init__.py` that is five, documented in `14d3d4c`. A sixth requirement emerged in
  review and is documented in `fed2e19`: the public entry points must accept and
  forward a `ForcingSource` too — `api.assess_site`, `api._assess_one`,
  `suitability.assess`, `suitability.assess_growth`, `scenarios.evaluate` and
  `scenarios.compare` — or a caller can build a `SiteContext` from real anchors and
  still have the seasonal series come from the placeholder, with nothing in
  `SiteAssessment.caveats` marking the mismatch.

### 5.1 Calendar-day indexing, and the defect it retires

The placeholder computes its drawdown as `np.linspace(1.0, 0.45, days.size)` — indexed by
position in the window rather than by date. Nitrogen is therefore a property of the
question asked: **on 1 April at DK-belt the code returns 3.15 µmol N/L for sugar kelp's
Oct–Jun window and 5.00 for the April-start windows of *Fucus* and *Chorda*** — a 59%
spread on the same day at the same site. Recorded as a strict `xfail` in
`tests/test_cultivation_window.py`.

*(A third figure, 3.61, appears in `forcing.py`'s docstring, in the xfail's reason, in
commit `6d36187` and in revisions 1–2 of this document. It is stale: it came from the
January–June stand-in window retired in that same commit, and no shipped species can
produce it. A0 item 4 corrects it.)*

Real climatologies are indexed by calendar day by construction, so `GriddedForcing` cannot
reproduce the defect, and re-indexing `PlaceholderForcing` retires it.

**The placeholder's seasonal shape is itself a choice, and it is fixed here** rather than
left to the implementer — because whatever is fitted afterwards is fitted to whichever
shape they picked:

```
din(day) = site.din_umol_l * (1.0 - 0.55 * season(day))
```

`season(day)` is the existing solstice-centred term, 1 at midsummer and 0 at midwinter.
It puts nitrogen highest in winter and lowest at midsummer, which is the observed Baltic
pattern (winter accumulation, spring-bloom drawdown) and the direction the old code had
backwards for wrapping windows. It is a placeholder, **assumed rather than sourced**, and
package D replaces it wholesale.

**It is not amplitude-preserving, and it lowers the yield of every window that stops
short of midwinter.** Revisions 3 and earlier claimed it preserved the existing
1.0 → 0.45 amplitude exactly. It does so only over a full year: the season term reaches
0 only at midwinter, so *Fucus*'s April–October window spans 0.450–0.891 rather than
0.450–1.000. Revision 4 then overcorrected to "it lowers **every** yield", which is also
false — sugar kelp's Oct–June window *does* reach midwinter (season span 0.000–1.000), so
its ODE trajectory **rises** 0.0–2.3%. That is invisible in the shipped numbers only
because §2.2 took *Saccharina* off the ODE; its reported harvest is bit-identical either
way. Measured consequences at package A, all at EE-coastal (the percentages are
site-specific — *Ulva* is −53.9% at DK-belt and −42.3% at LT-coastal):

| | before | after | |
|---|---|---|---|
| *Fucus* at EE-coastal | 3446.33 g DW/m² | **2797.31** | −18.8% |
| *Ulva* at EE-coastal | 461.43 | 207.33 | −55.1% |
| *Chorda* at EE-coastal | 482.05 | 272.13 | −43.5% |
| *Saccharina* at DK-belt (ODE only) | 36.90 | 37.75 | **+2.3%** |

2797.31 is **below the hard `assert 3000.0` in
`tests/test_growth.py::test_fucus_reaches_the_tagalaht_reference_range`**, and four
growth-viability verdicts flip suitable → marginal: *Chorda* and *Ulva* at DK-belt and at
LT-coastal. **Package A therefore resets that bound in the same pull request**, downward
to 2500.0 and with the new value stated in the test's docstring alongside the published
range it still does not meet. §3.1's rule that A0 does not touch the assertion stands; A
does, because A is what moves it. Without this the suite is red for the whole B → C → D
stretch with a standing instruction not to fix it.

**One further correction to this section's own premise.** It states the defect is
"recorded as a strict `xfail`" and package A's plan assumed that marker would XPASS when
the formula landed. It does not: the season term has period 365.25 while the test steps a
whole 365 days across the wrap, leaving a phase residual of 1.722e-03 relative
(worst case 1.765e-03 over the Apr–Jun overlap) against `pytest.approx`'s default
`rel=1e-6`. Retiring the marker and widening the tolerance to `rel=1e-2` is therefore one
edit. The test keeps its teeth by a factor of 37 — under the old drawdown the same
comparison differed by 37.1%. The period must **not** be changed to 365.0 to force
exactness: that term also drives temperature and PAR, so it would move every yield above.

---

## 6. The artifact

**Package B has now decided both, by measurement.** Revision 2 asserted the format was
settled here and then named none; it was B's, together with resolution. B is complete and
its measurements are in `docs/2026-09-15-package-b-measurements.md`, which this
section has been amended against. **Grid resolution is native ~2 km** (0.016666° lat ×
0.027777° lon) and **format is NetCDF4 + zlib complevel 4**, smaller than Zarr at all six
resolution × temporal combinations measured and a single file, which §6.3's atomic pair
write wants.

Resolution is not a trade-off against size. Coarsening to ~4 km land-masks the cell
containing **Tagalaht** — the only published anchor the parameterisation has — and
PL-lagoon with it. The anchor forces the grid, and the largest candidate artifact is
50.7 MB, so nothing argues for coarsening anyway.

Everything else is fixed here, because four of the eleven packages in §8 could not otherwise
have their first failing test written.

### 6.1 Variables, and the statistic for each

| `SiteConditions` field | Source layer | Spatial statistic | Temporal statistic |
|---|---|---|---|
| `salinity_psu` | Copernicus Baltic reanalysis | mean over polygon | monthly mean |
| `mean/summer/winter_temp_c` | Copernicus Baltic reanalysis | mean | monthly mean |
| `din_umol_l`, `dip_umol_l` | Copernicus BGC + HELCOM | mean | monthly mean |
| `surface_par` | **none — no source exists** | — | — |
| `light_attenuation_k` | Copernicus BGC `zsd`, **derived** via Poole–Atkins k ≈ 1.7/z_SD | mean | monthly mean |
| `depth_m` | EMODnet Bathymetry | mean, with min reported | static |
| `significant_wave_m` | Copernicus Baltic wave hindcast, **hourly `PT1H-i`** — not the ready-made climatology | mean | **monthly 95th percentile + annual maximum** |

**PAR and light attenuation are absent from spec §6's layer table** — two growth-model
inputs with no source. Revision 4 made that contingent on `kd490` proving unusable.
**Package B measured it, and the contingency is now half live.**
`BALTICSEA_MULTIYEAR_BGC_003_012` has no `kd490` and no PAR variable of any kind; its
variables are `chl`, `nh4`, `no3`, `nppv`, `o2`, `o2b`, `ph`, `po4`, `spco2`, `zsd`.

- `light_attenuation_k` **is** recoverable, from a variable this document never named:
  `zsd` is Secchi depth, and Poole–Atkins gives k ≈ 1.7/z_SD. At Tagalaht that yields
  0.152–0.336 m⁻¹, mean 0.198, against the placeholder default of 0.4. It must be carried
  as a **derived** quantity with the relation named in the manifest, not as a measured
  layer — the distinction matters for the tier the result inherits.
- `surface_par` **has no source.** It remains a placeholder constant after D, and §7 must
  display that the way staleness is displayed, not bury it. This is now a commitment, not
  a contingency.

**Depth is a dimension §6.1 never specified**, and the reanalysis is 3-D with 56 levels.
Package B used the **surface level, 0.50 m**, and D should do the same unless a
cultivation-depth mean is argued for separately.

**Waves get a percentile, not a mean**, because the same artifact feeds
`assess_physical`'s exposure test against a structural design limit, where a mean is wrong
in the permissive direction. Revisions 1–5 left this as "either split the field or document
which it is", which is not a specification: `SiteConditions.significant_wave_m` is **one
`float`**, and `suitability.py:107` compares it directly to `method.max_significant_wave_m`.
A row asking for two statistics into one field cannot be implemented as written.

**Decided here, and reversible:** `significant_wave_m` carries the **monthly 95th
percentile** — the statistic `assess_physical` must consume, because the comparison is
against a structural design limit and a mean fails permissively. The **annual maximum
becomes a second field**, `significant_wave_max_m`, which package D adds to
`SiteConditions` alongside its other extensions and which no verdict consumes until a rule
is written for it. `methods.yaml`'s `max_significant_wave_m` must be re-checked against the
95th percentile, since its present values were set against an unstated statistic.

**"One extra band costs nothing" was wrong, and package B priced it.** The wave product
ships a ready-made 2 km monthly climatology (`cmems_mod_bal_wav_my_2km-climatology_P1M-m`,
`VHM0`, 12 steps) — but as a **mean**, which is the statistic this paragraph rejects. A
95th percentile requires the hourly `PT1H-i` dataset, a far larger pull than the existence
of the climatology suggests. **Package C must price this separately**; it was outside B's
scope and is not yet measured.

### 6.2 Aggregation and coverage

- **Coverage is decided by the containing cell, not by a valid fraction.** Revision 4 set
  a **minimum valid fraction of 60%** of the polygon's cells non-land and non-NaN, marked
  it assumed, and asked package B to set it on evidence. B's finding is that the
  *statistic* is wrong, not merely the number, and it is withdrawn:
  - It is **degenerate at farm scale**. A 0.1 ha community farm is 31.6 m square against a
    native cell of 1.85 × 1.69 km — **59× wider** — so every farm polygon lies inside one
    cell and its valid fraction can only be 0% or 100%. The rule presumes a polygon
    spanning many cells; the tool's own default scale never produces one.
  - At a scale where it *is* well posed it **rejects the anchor**. Over a 5 km siting-region
    window at native resolution, EE-coastal's valid fraction is **36.7%** — so a 60%
    minimum puts Tagalaht, the one site the model is calibrated against, outside coverage.

  **The replacement, which package D implements:** (1) the polygon's containing cell must
  be valid — this is what "is there data here" means at farm scale; (2) **distance to the
  nearest valid cell** is computed and surfaced, which at native resolution is 0.75–1.28 km
  across all six regions and is a quantity a siting user can judge; (3) a valid-fraction
  rule returns only for polygons genuinely spanning multiple cells, with its threshold set
  once package E's drawn geometry produces them. §7 row 2 keys off (1).
- **The six placeholder regions have no geometry**, so B invented coordinates to measure
  against and recorded them in `docs/2026-09-15-package-b-measurements.md`. Any
  polygon-level threshold set before package E is set against invented shapes.
- **Monthly fields replace the sinusoid** in `daily_forcing` rather than feeding it;
  interpolation is linear on day-of-year, wrapping at the year boundary, which the window
  work already supports.
- **Per-year monthly fields, not one climatology — and this is a change.** Earlier
  revisions assumed the artifact held a single 12-month climatology. §10.2's own
  measurement refutes that: monthly *resolution* costs at most +17.4% in final biomass, but
  collapsing 2023–2025 into one climatology costs **−57% to +179%**, because interannual
  variability swamps the resolution effect by an order of magnitude. A single climatology
  returns *Fucus* 152.61 g DW/m² for every year against real values of 54.74, 290.41 and
  67.84. The artifact therefore carries **one monthly field per year**, and
  `GriddedForcing.daily_forcing` **takes a year** — an interface change package D owns, and
  a reason for `artifact_schema_version` (§6.3) to exist. At native resolution three years
  is 50.7 MB against 16.5 MB for a climatology, so size does not argue against it.
- **The year boundary, for a window that wraps.** Per-year fields make "wrapping at the
  year boundary" ambiguous in a way a single climatology never was: for *Saccharina*'s
  Oct–Jun window opened on year Y, January comes from **year Y+1**, not from Y. The
  day-of-year axis runs past 365 (package A already does this) and the field it indexes
  changes with it. A same-year cycle — reusing Y's own January after Y's December — would
  reintroduce exactly the averaging-away of interannual variation that the measurement
  above rejects, on the one window where it matters most. **If Y+1 is not in the artifact,
  the query blocks** (`UNKNOWN`, §7) rather than falling back to Y or to a mean of
  available years. That makes the last year the artifact carries unusable for wrapping
  windows, which is correct and must be visible rather than silently papered over.
- **Which years the artifact carries is package C's decision**, not settled here. B used
  the last three full calendar years (2023–2025) because three is enough to expose the
  interannual spread; it is not a recommendation for the production baseline. What B does
  establish is that averaging years away is not available.
- **The spatial-averaging method is a port, not a re-invention.** OLAMUR's `terra`
  salinity-weighting step is the reference; spec §14 already carries the risk and the
  obligation to validate the port before numbers reach a user. It is a named sub-item of
  package D with that validation as its done-when.

### 6.3 Locator, versioning, atomicity

- Artifact and manifest are found via `SEAGARDEN_DATA_DIR`, defaulting to `data/`, with
  fixed filenames.
- The manifest carries `artifact_schema_version` and `built_on` alongside per-layer
  provenance. An unrecognised version is refused and degrades visibly (§7 row 6).
- Manifest and artifact are written **atomically as a pair**.
- Per layer, committed: source, product identifier, version, retrieval date, licence,
  redistribution terms, and **either** a Zenodo DOI **or** an explicit
  `redistribution: forbidden` marker with a source URL. A layer carrying neither fails
  §9's provenance test. A marked layer is referenced-not-mirrored and logged as a
  durability risk in spec §14.
- The test fixture has a committed path with a `.gitignore` exception.

### 6.4 Exclusion and human-use vectors are separate — and split in two

Their own GeoPackage: different cadence, licences and consumers. Revision 1 then routed
them into `suitability.assess_legal`. The specification reserves `legal_permissibility`
for spec §9's hard legal exclusions from GMU's records; spec §5.1's human-use conflicts
are a *separate* output (`overlap / adjacent / clear`, governing layer named), which
revision 1 left with no owner.

Package F splits accordingly (§8). Shipping density must never produce a legal verdict.

---

## 7. Failure modes

Each degrades visibly, never fails, and never silently substitutes.

| Condition | Behaviour |
|---|---|
| Forcing artifact absent | Fall back to `PlaceholderForcing` with a banner naming what the tool is running on |
| Polygon's containing cell not valid (§6.2) | `UNKNOWN`, which **blocks** the verdict, with the distance to the nearest valid cell reported |
| Artifact does not carry the requested year (§6.2) | `UNKNOWN` and blocks; never silently substitutes another year |
| `surface_par` consumed | Always a placeholder constant — §6.1 has no source — displayed the way staleness is |
| Polygon outside every calibration domain | `SiteConditions` with `region=None`; every quantity forced to tier C, the polygon's coordinates named |
| Artifact older than 18 months | Staleness note on the result, the mechanism of spec §9.3's "verified on" dates |
| Refresh fails part-way | Writes nothing; previous artifact and manifest stay valid as a pair |
| Artifact schema version unrecognised | Refuse, fall back to `PlaceholderForcing`, say why |
| Spec §9 regulatory record set absent | `assess_legal` returns `UNKNOWN` and blocks, even with the human-use GeoPackage present |

**The mechanism.** There is today no representation for a site whose conditions are
unknown. `SiteContext.conditions` becomes `SiteConditions | None` and `assess_site`
returns early with an explicit `unassessable` flag; the UI reads that flag to distinguish
"unsuitable" from "unassessed". **Delivered by package D**, asserted in D's done-when —
revision 2 introduced this mechanism and gave it to no package at all.

The rule underneath: **an absent input produces a blocked verdict, not a permissive one.**
A weighted index would let good water outvote a missing legal layer; spec §5.2's
minimum-of-constraints form makes that impossible, and these fallbacks must not
reintroduce it.

A consequence worth stating: with `assess_legal` returning `UNKNOWN` for every
jurisdiction until M12, **every current verdict is UNKNOWN**. The legal layer is on the
critical path for AF item 2's "maps of suitable sites", and no data-layer work moves that.

---

## 8. Work packages

Effort is indicative, totalling **7.0 PM across eleven packages**. It is drawn against
spec §13's ~14.5 PM for the DST, itself funded from WP2 line 2.1 (€51,250) alongside KU's
share of A2.1, A2.2, A2.4 and A2.5. Because §1's months are booked to A2.1/A2.2, these
are a forward charge against A2.3's rows rather than a draw on them today.

**The data-layer row is over-subscribed.** B + C + C1 + D's non-port share come to 2.5 PM
against spec §13's 2 PM "data layer" row; the "terra port" row (0.5 PM) is exactly met by
D's port sub-item. With A0 (0.8), F2 (0.3) and G (0.1) having no row at all, **the spec
§13 amendment to propose is 1.7 PM**. Revision 3 said these rows were exhausted "in full"
and understated the overrun; the convention everywhere else in this document is to
surface rather than absorb, and this row is now surfaced.

| # | Package | Delivers | Depends on | Effort | Done when |
|---|---|---|---|---|---|
| **A0** | Modelling corrections (§3) | §2's three decisions recorded; anchors re-sourced; `b_max` re-based or marked assumed; tier D via `contraindication()`; floors + demonstrated ranges for all five species; thresholds to `params/`; `dry_matter` on four macroalgae; **the §2.2 salinity relocation**; **spec §7.2 amended per §2.1**; **the DK-belt tier re-examined**; **`Fucus` elemental fractions re-sourced**; four false sentences corrected; two README stub rows added | §2 decisions | 0.8 PM *(no spec §13 row — propose amendment)* | Fourteen clauses, each a test or a diff: (1) nothing reportable below any floor; (2) `anchors:` block present with basis stated; (3) `b_max` sourced or marked `assumed`; (4) `0.35`/`0.5`/decline width absent from `.py`, identical values in `params/assessment.yaml`; (5) `dry_matter` on all four macroalgae; (6) grep for "re-tune" and "3.61" returns nothing outside this document; (7) *Fucus* still tier C at LT-coastal; (8) README stub table has the two new rows; (9) `growth.py` no longer multiplies `salinity_factor` into `rate`, and Saccharina at DK-belt returns **11.24 t FW/ha** (= 0.611 × 18.4) per §2.2; (10) spec §7.2's Redfield sentence amended and the nitrogen gap recorded in the Fucus YAML; (11) *Fucus* elemental fractions no longer byte-identical to Saccharina's, or explicitly marked assumed-from-kelp; (12) the DK-belt calibration tier re-examined and the outcome recorded; (13) spec §14 carries a key-person row for the annual refresh; (14) `contraindication()`'s note distinguishes an observed floor from an assumed one — *Chorda* is the test case |
| **A** | Forcing seam | `ForcingSource`; `PlaceholderForcing`; calendar-day indexing per §5.1; the `xfail` retired | A0 | 0.3 PM *(spec §13 "model core")* | Four call sites named in the PR; snapshot diff explained line by line |
| **B** | Resolution + format spike — **COMPLETE**, `docs/2026-09-15-package-b-measurements.md` | Artifact size at 3 resolutions × 2 formats × 2 temporal designs; valid-cell and nearest-cell measurements; daily-vs-monthly forcing comparison (§10.2). Decided: native ~2 km, NetCDF4+zlib4, per-year monthly | — | 0.3 PM *(spec §13 "data layer")* | **Met.** Note committed with sizes, the daily/monthly delta, a coverage statistic set on evidence, and four decisions — three of which amended this document |
| **C** | Refresh tooling | `refresh_layers.py`; manifest; Zenodo archive; runbook; source-probe job; test fixture | B | 1.0 PM *(spec §13 "data layer")* | Provenance test passes against the committed fixture; runbook followed end-to-end by someone else |
| **D** | `GriddedForcing` | Artifact read; **polygon-and-year query**; aggregation per §6; `terra` port; calibration-domain layer; `SiteConditions` extensions incl. `significant_wave_max_m`; **re-validation of `methods.yaml`'s `max_significant_wave_m` against the 95th percentile**; `conditions: SiteConditions \| None` + `unassessable`; **the §6.2 coverage rule and the §10.2 verdict-sensitivity measurement B could not make** | **A**, B, C | 1.5 PM *(spec §13 "data layer" + "terra port")* | One fewer README stub row; port validated against Tagalaht and Maar et al.; a test that an unassessable site returns UNKNOWN and never a verdict. **Plus, because revision 5 added behaviour the package A protocol does not express:** a test that a polygon query aggregates over the polygon's cells rather than a single point; a test that a requested year the artifact lacks **blocks** rather than substituting another; a test that a wrapping window takes January from year Y+1 (§6.2) and blocks when Y+1 is absent; **a recorded re-validation of every `methods.yaml` `max_significant_wave_m` against the monthly 95th percentile, with each value either confirmed against a named structural source or marked assumed** - the present values were set against an unstated statistic, so adopting a defined one without re-checking them silently changes what the exposure test means; and every caller migrated wherever the signature changes. **The package A seam is deliberately unchanged until D** - `conditions_for(region)` / `daily_forcing(site, window)` carry no polygon and no year, so D must extend it rather than merely implement it, and these tests are what prevent D satisfying the old protocol while proving none of the new behaviour |
| **D1** | Re-parameterisation | The fit deferred from A0, against real forcing; `test_growth.py:69` narrowed toward the published range | D | 0.5 PM *(spec §13 "calibration")* | Anchor met with the fitted parameters named, **or** the failure documented as a finding with the identifiability argument of §3.1 restated against real data |
| **E** | Map and polygon drawing | `shinywidgets` + `ipyleaflet`; drawn geometry into the report; spec §10 instrumentation seam left in place | D | 1.5 PM *(spec §13 "siting module")* | One fewer README stub row; seam present though unwired |
| **C1** | Human-use vector build | The EMODnet/HELCOM/EEA GeoPackage of §6.4 — a second output of the refresh tooling, same manifest and DOI treatment | C | 0.2 PM *(spec §13 "data layer")* | GeoPackage present with per-layer provenance; provenance test covers it |
| **F1** | Human-use overlay | `assess_conflicts()` → overlap/adjacent/clear per named layer into `SiteContext.activities`/`.protection`. **Descriptive only; feeds no verdict** | **C1** | 0.5 PM *(spec §13 "siting module")* | `activities` populated for a **committed fixture polygon** (no placeholder site has geometry); test that it changes no verdict; the human-use README stub row removed |
| **F2** | Hard legal exclusions | `assess_legal` per jurisdiction, each exclusion traceable to a named record and its "verified on" date | **G** + GMU M12 content | 0.3 PM *(no spec §13 row)* | Absent record set still blocks with the GeoPackage present |
| **G** | Regulatory record schema | Pydantic model per spec §9.1; empty record set; staleness display | — | 0.1 PM *(no spec §13 row)* | Schema plus one worked example record round-tripping in a test |

**Critical path: §2 decisions → A0 → A → D → E**, with B → C feeding D in parallel.
`GriddedForcing` implements the protocol package A creates, so D cannot precede A —
revision 3 claimed B → C → D ran independently of A0/A, and that was false at D. D1
branches off D and is not on the critical path. F1 and G are independent and absorb interruption. F2 cannot start
before M12 whatever happens — revision 1 listed its dependency as C; it is G.

**Why G stays early despite having no content.** GMU's €5,500 of legal expertise lands at
M12 across four jurisdictions. Whether it arrives as structured records or four PDFs
depends on whether a schema exists to hand them beforehand. Review challenged whether a
schema written before seeing legal content survives contact with it — fair, and the
mitigation is that G ships the schema *and one worked example*, so the failure mode is a
schema revised at M12 rather than a transcription project.

---

## 8.1 Traceability — every scoped item, decision and correction has an owner

Three review rounds found the same defect class each time: something scoped in §1,
decided in §2 or corrected in §3 that no §8 row's *Delivers* or *done-when* owned. Each
rewrite fixed what the reviewer pointed at and the pointer moved. This table is the fix —
it is checked before the implementation plan is written, and again whenever a row changes.

| Where it is stated | Package that owns it | Checked by |
|---|---|---|
| §1 — data layer in scope | D | done-when: one fewer stub row |
| §1 — map and polygon drawing | E | done-when: one fewer stub row |
| §1 — human-use and exclusion vectors | C1 (build), F1 (consume), F2 (legal verdict) | F1 fixture-polygon test; F2 blocking test |
| §1 — refresh tooling | C | provenance test against fixture; runbook followed by someone else |
| §1 — regulatory record schema | G | worked example round-trips |
| §1 — spec §5.4 panel deferred, recorded as a stub row | A0 | clause (8) |
| §1 — spec §10 instrumentation seam | E | done-when: seam present though unwired |
| §2.1 — elemental accounting fork | A0 | clauses (10), (11) |
| §2.2 — salinity relocation | A0 | clause (9): 11.24 t FW/ha at DK-belt |
| §2.2 — DK-belt tier re-examined | A0 | clause (12) |
| §2.3 — carrying capacity | **decision only; no package until taken** | spec §11 entry, then §6.1's table before B |
| §3.1 — anchors re-sourced, `b_max` re-based | A0 | clauses (2), (3) |
| §3.1 — four false sentences corrected | A0 | clause (6) |
| §3.1 — anchor guarded as a set | A0 | clause (2) records basis; assertions land with D1 |
| §3.2 — tier D via `contraindication()` | A0 | clause (1) |
| §3.3 — floors and demonstrated ranges | A0 | clause (1) floors; **ranges judged at review, no automated clause** |
| §3.4 — thresholds to `params/` | A0 | clause (4) |
| §5 — four call sites migrated | A | done-when: named in the PR |
| §5.1 — DIN shape; anchor bound reset | A | done-when: bound reset with the new value in the docstring |
| §6.2 — valid-cell threshold on evidence | B | measurement note |
| §6.3 — locator, schema version, atomicity | D (read side), C (write side) | unrecognised-version fallback test |
| §7 — `SiteConditions \| None` + `unassessable` | D | done-when: unassessable returns UNKNOWN |
| §4.1 — Zenodo archive, runbook, source-probe | C | provenance test requires DOI or marker |
| §4.1 — key-person row in spec §14 | **A0** | clause: spec §14 has the row |
| §10.2 — daily-vs-monthly measured | B | measurement note |
| §6.1 — wave statistic fixed to the 95th percentile, annual max to its own field | D | `significant_wave_max_m` present; `assess_physical` reads the percentile |
| §6.1 — `methods.yaml` wave limits re-validated against that statistic | D | each `max_significant_wave_m` confirmed against a named source or marked assumed |
| §6.2 — per-year fields, and January from Y+1 for a wrapping window | D | boundary test; missing-year block test |

**Two rows are deliberately unowned and say so:** §2.3's carrying capacity, which cannot
be scheduled before the decision is taken; and §3.3's demonstrated ranges, which are a
scientific judgement per species and are reviewed rather than asserted by a test. Every
other line has a package and a check.

**One known tension to resolve in D, not now.** §7 row 3 forces tier C for a polygon
outside every calibration domain, while §3.2 makes `contraindication()` the sole source of
tier D. For a 2 psu sugar-kelp polygon with `region=None` those two rules disagree.
`contraindication()` wins — a salinity finding does not stop applying because the polygon
is unlocatable — and D's done-when carries the test.

**One wording fix that belongs with it.** `contraindication()` currently returns the note
*"cultivation failure has been observed at this salinity"* for **any** species below its
floor. Once §3.3 gives assumed floors to four more species, that sentence asserts a
finding nobody made. A0 makes the note conditional on whether the floor is observed or
assumed; *Chorda* is the test case.

---

## 9. Testing

The existing 85 tests are the regression net. Four rules specific to this work:

**The golden-file snapshot goes in after A0, not before A.** It captures `assess_site()`
**and** `scenarios.compare()` for every site × species. Revision 1 put it first, which
would have frozen §3's defects as the definition of correct. A's diff is then explained
line by line; every other package's diff should be empty unless the package says
otherwise.

**CI never touches the network.** The refresh tooling is tested against a committed
fixture; the download path is exercised by hand at refresh time. §4.1's source-probe job
is separate, scheduled and non-blocking.

**Provenance is asserted, not trusted.** A test fails if any manifest layer lacks a
licence, a retrieval date or redistribution terms; or lacks **both** a Zenodo DOI and an
explicit `redistribution: forbidden` marker with a source URL.

**Anchors are guarded as sets** — dry weight, carbon and phosphorus per cage together, so
a stoichiometrically impossible combination fails rather than passing on the one arm
anybody checked. Nitrogen joins once §2.1 is resolved.

---

## 10. The spec §8 decision spike, and assumptions

### 10.1 The spike

Decisions D5 (risk modules, M18) and D6 (viability boundary, M20) are open, and spec §14
names them first to be cut. The failure mode is that they are cut by attrition — effort
runs out, nobody decides, and the tool ships without them by default.

One timeboxed spike before M18: for alien species risk, whether a usable pathway dataset
exists for the four jurisdictions at all; for viability, whether OLAMUR D6.2/D6.3 have
published anything borrowable. Output is a recommendation, not code. Anything built is
labelled throwaway.

### 10.2 Assumptions, stated so they can be contradicted

- Copernicus Baltic reanalysis, EMODnet Bathymetry and EMODnet Human Activities are
  redistributable compatibly with the open-data commitment. If not, that layer becomes
  referenced-not-mirrored under §6.3's marker and spec §14's durability risk grows.
- **Monthly climatology is sufficient for the biology — MEASURED, and the answer is half
  no.** This was the assumption; package B ran it and it splits in two.
  **Monthly resolution is sufficient:** daily versus that year's own monthly means costs at
  most **+17.4%** in final biomass (*Ulva* 2024), typically under 10%.
  **A multi-year climatology is not:** daily versus a 2023–2025 climatology costs **−57% to
  +179%**. The assumption held for the half it was really making a claim about and failed
  for the half nobody examined, which is why §6.2 now specifies per-year monthly fields.
  It would certainly not hold for spec §8.3's weather-window module, which is out of scope.
  Related, and now demonstrated rather than argued: the model has one state variable and no
  nutrient reserve pool, so it cannot buffer variability — which is why the measurement was
  worth its cost. Measured at the Tagalaht cell, three species, three years;
  `docs/2026-09-15-package-b-measurements.md` §1.
- The four doors of spec §4 survive D2.1's findings at M12. If D9 resolves against them,
  package E's UI changes but the data layer does not.
- Nobody is waiting on this. If a partner deadline needs a demo sooner, §8's ordering is
  the first thing to revisit.

---

## 11. Revision history

**Revision 4 → 5.** The first revision driven by measurement rather than review. Package B
ran, and three of this document's claims did not survive contact with the data. Revision 5
is targeted edits, not a rewrite:

- **§10.2's central assumption was half wrong.** Monthly *resolution* is sufficient
  (≤ +17.4% in final biomass); a multi-year *climatology* is not (−57% to +179%).
  Interannual variability swamps the resolution effect by an order of magnitude. §6.2 now
  specifies **per-year monthly fields** and `GriddedForcing` takes a year — an interface
  change package D inherits.
- **§6.2's 60% valid-cell threshold was malformed, not merely unsourced.** It is degenerate
  at farm scale (a 0.1 ha farm is 59× narrower than a native cell, so the fraction is 0% or
  100%) and at a well-posed scale it rejects Tagalaht at 36.7%. Withdrawn and replaced by
  containing-cell validity plus distance to the nearest valid cell.
- **§6.1 sourced two variables from a product that does not contain them.** The Baltic BGC
  reanalysis has no `kd490` and no PAR. `light_attenuation_k` is recoverable as a *derived*
  quantity from `zsd` via Poole–Atkins; `surface_par` has no source at all and is now
  committed to remaining a placeholder constant that §7 must display. §6.1 also gained the
  depth choice it never specified, and the wave percentile was re-priced: the ready-made
  climatology is a mean, and the percentile needs the hourly product.
- **Resolution and format are decided**: native ~2 km, NetCDF4 + zlib complevel 4. The
  resolution is forced by the anchor rather than chosen — coarsening land-masks Tagalaht.

Three further items, from review of revision 5 itself, where the revision exposed a
contradiction rather than created one:

- **The wave row could not be implemented as written.** §6.1 asked for two statistics into
  `SiteConditions.significant_wave_m`, which is one `float` that `suitability.py:107`
  compares directly to a design limit. Decided: the field carries the **monthly 95th
  percentile**, and the annual maximum becomes `significant_wave_max_m`, added by D and
  consumed by no verdict until a rule exists. Reversible, but not leavable as an either/or.
- **Per-year fields made the year boundary ambiguous**, where a single climatology never
  was. *Saccharina*'s Oct–Jun window takes January from **Y+1**, and blocks when Y+1 is not
  in the artifact rather than falling back to Y — which makes the artifact's last year
  unusable for wrapping windows, correctly and visibly.
- **Package D's done-when now tests the behaviour revision 5 added.** The package A seam
  carries no polygon and no year, so D could have satisfied the protocol while proving none
  of it. D must now show polygon aggregation, a missing requested year blocking, and the
  Y+1 boundary rule.

Recorded but not resolved: with real forcing *Fucus* returns 54.7–290.4 g DW/m² against a
published 4800–5200. Measured with `surface_par` still a placeholder, at one cell and one
depth level, so it is an observation for **package D1** to explain, not a finding against
the parameterisation. All measurements and their provenance are in `docs/2026-09-15-package-b-measurements.md`.

**Revision 1 → 2.** Reviewed by 13 agents across six dimensions, each finding
adversarially verified; 27 survived, 17 refuted. Revision 2 added package A0 and moved
the snapshot behind it; recorded the two model forks as decisions; split package F;
gave the open-data commitment a Zenodo route; specified interfaces; added effort figures;
and corrected the false claim that `mu_max` had been tuned to the Tagalaht anchor.

**Revision 3 → 4.** Round 3 found 9 prior findings still open and 14 new ones surviving
an adversarial refuter briefed to be harsh (8 refuted) — down from 55, and every
quantitative claim in revision 3 was independently recomputed and reproduced exactly. Its
verdict: *converging on the numbers, churning on the bookkeeping*, with one recurring
defect class — something scoped in §1, decided in §2 or corrected in §3 that no §8 row
owned. Revision 4 is targeted edits, not a rewrite:

- **§2.2 is resolved, and none of the three readings was right.** OLAMUR D2.3's actual
  implementation is recorded in a file already in this repository: `f_salinity × 18.4 t
  FW/ha`, a direct salinity-indexed yield model with **no growth ODE for Saccharina at
  all**. The published figure at DK-belt is 11.24 t FW/ha. This is a fork from spec §7.2
  rather than an implementation of it, and it makes `max_yield_t_fw_ha` the model instead
  of dead data.
- **§2.1's recommendation was wrong.** *Fucus*'s elemental fractions are byte-identical to
  Saccharina's, which OLAMUR labels "Kelp DM". *Fucus* is silently running on kelp
  stoichiometry; at a literature 2% N the nitrogen arm doubles and the gap narrows from
  4.5–11× to ~2.3–5.5×. "Do not change the fractions" is replaced by "re-source them or
  mark them assumed-from-kelp".
- **§5.1's DIN formula is not amplitude-preserving and lowers every yield.** Measured:
  *Fucus* 3446 → 2797 g DW/m², below the hard `assert 3000.0`; *Ulva* −55%; *Chorda* −43%;
  four growth-viability verdicts flip. Package A now resets that bound in the same PR —
  without which the suite is red for the whole B → C → D stretch under a standing
  instruction not to fix it.
- **Package D depends on A**, since `GriddedForcing` implements the protocol A creates.
  Revision 3's claim that B → C → D ran independently was false at D.
- **The human-use GeoPackage had no producer.** New package C1 builds it; F1 consumes it
  and is tested against a committed fixture polygon, since no placeholder site has
  geometry.
- **A0 gained the salinity relocation and six more done-when clauses**, from eight to
  fourteen. It is the package that most needs watching: it is now large.
- **§8.1 added** — a traceability table mapping every §1 scope item, §2 decision and §3
  correction to a package and a check, with the two deliberately unowned rows named as
  such. This is the fix for the defect class, not another pass over the prose.
- **Budget corrected:** 7.0 PM across eleven packages; the data-layer row is
  over-subscribed by 0.5 PM and the amendment to propose is 1.7 PM, not 1.3.
- **A caution on §2.3:** a HELCOM eutrophication-status class is not carrying capacity for
  extractive culture — the sign is inverted — and must not be shipped under that label.

**Revision 2 → 3.** Revision 2 was itself reviewed — a coverage pass over all 27 findings
plus a fresh-eyes hunt for defects the revision introduced, adversarially refuted. Only 6
of 27 were fully addressed and 55 new defects survived. The substantive corrections:

- **§3.3 was wrong and contradicted the governing document.** Making out-of-range
  extrapolation a tier D trigger contradicts spec §7.4 (tier D is *a local finding
  contradicting the model*), would have made *Fucus* tier D everywhere but Tagalaht
  including the project's primary site, and would have broken a passing test. The hard
  floor and the extrapolation marker are now two distinct mechanisms.
- **§2.2 treated "move it to the yield" as one model.** It is two, diverging by 49%
  (140.13 vs 208.55 g DW/m²); with the current rate-based reading the three span a factor
  of 5.6. All three are now stated and one is recommended with a reason.
- **§2.1's diagnosis did not survive its own arithmetic.** A basis error moves all four
  anchor arms together; the measured pattern (P inside, C marginal, N 4.5–11× low) cannot
  be produced by one factor. The hypothesis is withdrawn and the gap recorded as
  unexplained.
- **§3.2 was mis-scoped in both directions.** Five sites sit below the floor, not three,
  and three leak — including DE-coastal at 11.0 psu, the largest leak, which revision 2
  omitted entirely.
- **The 3.61 µmol N/L figure is stale.** No shipped species can produce it; it came from
  the January–June stand-in retired on 13 Sep 2026. It was written into `forcing.py`'s
  docstring by the same commit that fixed the defect the docstring describes.
- **Three false "re-tune" sentences survive in the repository** and are now named
  individually for A0, along with the fact that commit `6d36187`'s message is immutable.
- **Mechanisms with no owner given one:** `SiteConditions | None` and `unassessable` go to
  package D; artifact format goes to package B, which revision 2 left specified nowhere.
- **A0's done-when went from two clauses to eight**, so A0 can no longer be declared done
  with most of its work outstanding.
- **§9's provenance test contradicted §6.3's referenced-not-mirrored provision.** The test
  now accepts a marker in place of a DOI.
- **Cross-references corrected throughout** — revision 2 inserted two sections and
  renumbered by +1 — and a `spec §N` / `§N` convention adopted.
- **Effort, dependencies and thresholds made honest:** 6.6 PM total; E does not wait for
  D1; every package annotated against a spec §13 row or flagged as lacking one; the 60%
  valid-cell fraction and the placeholder DIN shape both marked assumed, with B tasked to
  put evidence under the first.

Two findings the reviewers were clean on, recorded because a clean result is a result:
spec §5.2's minimum-of-constraints rule is correctly implemented and §7's fallbacks do not
reintroduce averaging; and the multiplicative `f(I)·f(T)·f(N)` composition is a defensible
inheritance from OLAMUR D3.2 — the problem is coefficient identifiability, not the
functional form.
