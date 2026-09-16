# Changelog

SeaGarden Decision Support Tool — Interreg South Baltic **SeaGarden**
(STHB.02.02-IP.01-0006/25), Activity A2.3, Deliverable D2.2. Licence EUPL-1.2.

This file records what changed and, as importantly, **what each version can and cannot
yet be trusted to say**. Every release states its own limits, because a decision-support
tool whose caveats live only in conversation is one whose caveats get lost.

---

## [Unreleased]

Nothing yet. Changes land here, not in the published sections below. When you cut the next
release, bump the two literals in `pyproject.toml` and `src/seagarden_dst/__init__.py` and
open a section for it — `tests/test_version.py` asserts the literals agree with each other
and with a matching heading here, but it cannot tell you that a merged change went
unreleased.

---

## [0.3.0] — 2026-09-16

**The refresh tooling gets its foundations, and five of seven sites get a position.**
Still a prototype: the artifact these tools build has not been built yet, so nothing the
tool displays is a measurement of the site you selected. 196 tests (143 at 0.2.0), CI on
Python 3.11 and 3.13 across two install states.

### Added

- **Package C-a — the provenance manifest and its writer** (`seagarden_dst.refresh`). A
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
— it does not build the artifact. Two gaps are recorded for the next package: package D
cannot reach `Manifest` or `load_pair` without crossing an import boundary its own test
forbids, and nothing validates `source`/`product_id` across layers, so a real refresh could
attribute five datasets to one product and pass every validator.

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
