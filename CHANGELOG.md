# Changelog

SeaGarden Decision Support Tool — Interreg South Baltic **SeaGarden**
(STHB.02.02-IP.01-0006/25), Activity A2.3, Deliverable D2.2. Licence EUPL-1.2.

This file records what changed and, as importantly, **what each version can and cannot
yet be trusted to say**. Every release states its own limits, because a decision-support
tool whose caveats live only in conversation is one whose caveats get lost.

---

## [0.2.0] — 2026-09-16

**Intermediate release for WP2 partners.** A checkpoint, not a milestone deliverable:
the analytical core is real and tested, and the data layer that would make its numbers
site-specific is designed but **not yet built**.

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

Every number the tool returns carries a **calibration tier** (A fitted / B literature /
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
  the `ForcingSource` boundary, so every future source — including package C's — inherits it
  rather than having to remember it. The error names the region and the per-array finite
  counts, because that is the part that would have saved the two minutes.

### Known limitations

| Limitation | Consequence | What unblocks it |
|---|---|---|
| Site conditions are placeholders | Rankings are structurally correct, numerically indicative | Package C implementation |
| **Surface PAR is a permanent placeholder** | Light-limited growth carries an unsourced input | **Nothing in the current layer set** — no integrated Baltic product carries PAR in any form |
| Significant wave height is a placeholder | The exposure test in `assess_physical` is unsourced | Package C's wave layer (~26 GB transfer, the most likely thing to be cut) |
| *Saccharina* yield misses its own anchor | Returns 3446 g DW/m² against a published 4800–5200 | `mu_max` has never been fitted to the anchor; deciding what is fitted is open |
| NaN depth produces a confident UNSUITABLE | A definitive negative verdict manufactured from missing data | Package D; recorded and owned, reachable once a real artifact is read |
| *Chorda filum* coefficients are assumed | Tier C in every region | A3.4 harvest data |

### What we need from partners

Four decisions are blocking, and none can be resolved by writing more code:

1. **Salinity fork** (spec §7.2) — open since 13 September.
2. **Carrying capacity** (spec §2.3).
3. **Per-species salinity ranges** — review of the bounds now enforced.
4. **Regulatory content** for four jurisdictions — GMU A2.2, due M12. The schema is ready.

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
