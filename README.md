# SeaGarden Decision Support Tool

[![CI](https://github.com/razinkele/seagarden-dst/actions/workflows/ci.yml/badge.svg)](https://github.com/razinkele/seagarden-dst/actions/workflows/ci.yml)

Prototype for **Deliverable D2.2** — *Decision-Support Tool prototype and functional
specification* — of the Interreg South Baltic project **SeaGarden**
(STHB.02.02-IP.01-0006/25), Activity A2.3, led by Klaipėda University.

Design: `SeaGarden_DST_functional_specification_v0.1.md`, in this folder.
Evidence base: `SeaGarden_DST_proposal_extract.md` (what the Application Form commits
to) and `../Relevant projects/OLAMUR-solutions-for-SeaGarden.md` (what can be borrowed
rather than built).

---

## Run it

```bash
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[app,dev]"
pytest                                            # 143 passed
shiny run app.app                                 # http://127.0.0.1:8000
```

**`shiny run app.app`, not `shiny run app/app.py`** — the file form puts `app/` on
`sys.path` and breaks `from app.modules... import`. Same convention as the NiD4OCEAN
DST; `pyproject.toml` sets `pythonpath = ["src", "."]` so both packages resolve from
the repository root.

Everything runs on the **placeholder site conditions** in `seagarden_dst.forcing`.
Nothing the prototype displays is a measurement.

Deploying a release to the live instance at **https://laguna.ku.lt/seagarden-dst/** is
[`docs/runbooks/deploy.md`](docs/runbooks/deploy.md) — written for somebody who is not its
author, because the Application Form commits us to keeping this online to May 2034.

## Built on the NiD4OCEAN DST architecture

This is deliberately the same shape as `razinkele/nid4ocean-dst`, because that shape
has already been through a full deliverable cycle and the patterns in it were paid
for once already:

| Pattern | Where it came from | Why it is here |
|---|---|---|
| Pure analytical core, single `assess_site()` entry | `nid4ocean_dst.api` | The UI renders one result object and never reaches into the models |
| `contracts.py` — `SiteContext` in, assessment out, `to_dict()` on everything exported | `nid4ocean_dst.contracts` | Report and JSON export cannot drift from what the screen shows |
| App shell with `t()` i18n seam, About / Help / Feedback modals, version read from the package | `app/shell.py` | A hand-copied version number drifts silently, and the About box is where a reader checks what they are looking at |
| `AppState` with `_DEFAULTS` as single source of truth | `app/state.py` | `__init__` and `defaults()` cannot disagree |
| **Stale-assessment invalidation** on any input change | `app/app.py` | The failure it prevents: one site's numbers under another site's label, in the downloaded report |
| Optional engines that degrade, never fail | `nid4ocean_dst.ses_signal` | A tool that falls over because a sibling package is missing is worse than one that says "not computed" |
| Two readings shown **beside** each other, never merged | NiD4OCEAN's SES pair | Here: nutrient removal and eutrophication pressure |

## Layout

```
app/                      Shiny application — run as `shiny run app.app`
  app.py                  wiring, Assess, stale-assessment invalidation
  shell.py                branding, sidebar, About/Help/Feedback, t() seam
  state.py                per-session reactive state
  modules/                one *_ui / *_server pair per panel
    user_mode.py          the four doors of specification §4
    site.py               where — sub-region picker (becomes the map)
    catalogue.py          what — species, method, scale
    results.py            ranking, and the single call site for assess_site()
    report.py             text and JSON export, caveats attached
    _widgets.py           tier badges, verdict pills, sidebar headline
  tests/                  application smoke tests
src/seagarden_dst/        analytical core — no Shiny imports
  api.py                  assess_site() — the only entry point the UI uses
  contracts.py            SiteContext, SpeciesOption, SiteAssessment
  calibration.py          calibration tiers that travel with every number (§7.4)
  params.py               YAML parameter sets, pydantic-validated (§3.2)
  forcing.py              site conditions and seasonal forcing (§6) — STUBBED
  growth.py               macroalgal growth, OLAMUR D3.2 formulation (§7.2)
  shellfish.py            salinity-banded yield, conservative carbon (§7.3)
  nutrients.py            N, P and C removal from harvest (§7)
  suitability.py          minimum-of-constraints siting verdict (§5.2)
  scenarios.py            method and scale comparison (§5.4)
  eutropy_adapter.py      optional: nutrient forcing from EUTROPY
  bowtie_adapter.py       optional: eutrophication pressure from bowtiepy
params/                   the parameter files — data, not code
tests/                    core test suite
```

The dependency direction is one-way: `app/` imports `seagarden_dst`, never the
reverse. The models stay usable from a notebook, a batch script, or another KU MRI
model chain.

## Reusing the KU MRI estate

Two optional engines, both wired as adapters that the core tries and survives without.

**EUTROPY** (`kaynarob/EUTROPY`) — the calibrated 29-box Curonian Lagoon
biogeochemical model. `eutropy_adapter.apply_nutrient_scenario()` swaps the site's DIN
and DIP for a scenario's, so a user can ask what a farm would remove under
BSAP-compliant Nemunas loading. `scenario_from_ensemble()` picks one run out of an
fN × fP grid export, matching **exactly** — a nearest-neighbour match would quietly
hand back a different scenario than the one asked for.

**bowtiepy** (`razinkele/bowtiepy`) — the MARBEFES Bayesian bow-tie.
`bowtie_adapter.eutrophication_pressure()` normalises a top-event marginal into
pressure context. Nutrient removal is worth more where pressure is higher — a farm
removing 40 kg N is the same farm either way, but in a water body at high risk that
removal is *mitigation*, and at low risk it is *maintenance*. So the bow-tie is
reported **beside** the ranking and never folded into it: a yield weighted by a risk
probability is neither a yield nor a risk, and nobody could say what it meant.

**Both carry a domain caveat, on the result rather than in a log.** EUTROPY is a
lagoon model and the Lithuanian pilot is open coast; the published bow-tie is
parameterised for the Curonian Lagoon. Applied outside those domains they are scenario
reasoning, and the adapters say so in the text the user reads.

```bash
pip install -e ".[engines]"     # optional; the app works fine without it
```

## Three things to understand before changing anything

**1. Coefficients live in `params/`, never in code.** WP3 A3.4 pilot data arrives
M12–30 and the D2.2 prototype is due M24, so the prototype necessarily runs on
literature priors and is re-parameterised afterwards. That recalibration must be a
*data* change, not a software release.

**2. Numbers do not travel without their provenance.** Every public model function
returns a `Quantity` carrying a `Calibration` — tier A (fitted to SeaGarden pilot
data), B (extrapolated from elsewhere in the Baltic), C (literature prior), or D
(contraindicated). Tier C values are widened into order-of-magnitude bands before
display, and `_widgets.quantity()` renders the tier badge inside the same element as
the number, because a footnote is where a caveat goes to die.

The canonical tier D case is sugar kelp in Lithuania: OLAMUR's salinity scaling
returns a small positive yield, while their own Estonian pilot found outright
cultivation failure at 5.5–6.5 psu. The tool excludes it and shows the finding.

**3. Suitability is a minimum, not a weighted index.** A weighted composite lets a
site with a fatal legal exclusion score "moderately suitable" because the water is
good. Where a constraint class fails, the tool names it — and an absent regulatory
layer returns `UNKNOWN`, which *blocks* the verdict rather than silently passing it.

## What is stubbed, and what unblocks it

| Stub | Where | Unblocked by |
|---|---|---|
| Site conditions | `forcing.PLACEHOLDER_SITES` | The curated Copernicus/EMODnet/HELCOM layers (§6); `pip install -e ".[spatial]"`. One site has now been checked against real data: at Tagalaht the placeholder DIN is **5.3× high** (5.5 against a measured 1.05 µmol/L) and attenuation **2.0× high** (0.4 against 0.198), while salinity is good. Values deliberately left uncorrected — replacing them is the data layer's job, not a hand-patch. `docs/2026-09-15-package-b-measurements.md` |
| **Surface PAR — permanently, not pending** | `SiteConditions.surface_par` | **Nothing.** Package B established the Copernicus Baltic BGC reanalysis has no PAR variable, so unlike every other row here this one does not resolve when the data layer lands. It stays a placeholder constant, and the design requires the tool to display that fact rather than bury it. A source outside the current layer set would be needed. `docs/2026-09-15-package-b-measurements.md` §5 |
| Light attenuation | `SiteConditions.light_attenuation_k`, default `0.4` | Source found, not yet wired: Secchi depth (`zsd`) via Poole–Atkins, k ≈ 1.7/z_SD — a **derived** quantity, not a measured layer, which affects the tier a result inherits. Package D wires it. Measured 0.198 at Tagalaht against the 0.4 default. `docs/2026-09-15-package-b-measurements.md` §5 |
| Map and polygon drawing | `modules/site.py` | Same, plus `shinywidgets` + `ipyleaflet` |
| Regulatory layer — **content** | `params/regulatory/`, empty but for the worked example | GMU's A2.2 external legal expertise, four jurisdictions, M12. The **schema** now exists (`regulatory.RegulatoryRecord`, spec §9.1) with a committed `EXAMPLE` record, so the M12 hand-off is a record set to fill rather than a transcription project. `suitability.assess_legal` still returns UNKNOWN without a layer — an absent record blocks, it never reads as "no restrictions" |
| Registration and usage logging | absent | §10; decision D4 due M18 |
| Method costs and labour | `params/methods.yaml`, all `null` | WP3 procurement records |
| *Chorda filum* growth parameters | `params/species/chorda_filum.yaml` | A3.4 harvest data. Decision D1 is taken — Chorda **ships** — but the coefficients are a structural analogue of Fucus, assumed rather than fitted, and tier C in every region. `test_chorda_ships_but_stays_uncalibrated` enforces that |
| Seasonal nutrient forcing | `forcing.daily_forcing` sinusoid | The §6 per-year monthly fields — **not** a climatology: package B measured that averaging years away costs −57% to +179% in final biomass, against ≤+17.4% for monthly resolution itself. DIN is now indexed by calendar day - `din_umol_l * (1 - 0.55 * season)`, highest in winter and lowest at midsummer - so two species at one site agree on the same date to within the 365.25-day phase residual (~1.8e-03 relative). The shape is still **assumed, not sourced**, and package D replaces it wholesale. Re-indexing lowered every ODE yield (*Fucus* at EE-coastal -18.8%, *Ulva* -55.1%, *Chorda* -43.5%) and flipped four growth-viability verdicts; `mu_max` has never been fitted to the anchor, and `b_max` is set from the anchor's own upper bound, so the anchor is not an independent check either |
| Scenario comparison panel (spec §5.4) | `scenarios.compare()` exists in the core; no UI caller anywhere in `app/` | Deferred past the data-layer work (`docs/superpowers/specs/2026-09-13-dst-data-layer-design.md` §8) |
| Human-use conflict screening (spec §5.1) | `SiteContext.activities` and `.protection` exist, defined in `contracts.py`; read nowhere | The EMODnet/HELCOM human-use vectors (§6) |
| SeaGarden branding | `app/shell.py` | WP4's Communication folder |

## Testing

```bash
pytest                     # core + app smoke, 153 passed
ruff check .
```

`pyproject.toml` declares an `engines` marker and deselects it by default, but **no test
carries it yet** — `pytest -m engines` collects nothing. The adapters are covered by the
default run, which exercises their unavailable path. Note also that the `engines` extra
installs `bowtiepy` only: EUTROPY is consumed as exported dicts by `eutropy_adapter` and is
not a package you can install.

CI runs both on every push and pull request, on Python 3.11 and 3.13, with the
optional engines absent — so the run also proves that the adapters degrade rather
than fail. `.github/workflows/ci.yml`.

Tests worth knowing about:

- `test_fucus_reaches_the_tagalaht_reference_range` — a loose guard on the only
  published anchor the SE Baltic parameterisation has: 4800–5200 g DW/m² per 6 m² cage
  over an April–October cycle (OLAMUR D3.2). **The model does not currently meet it.**
  It returns 2797 g DW/m², and the test asserts 2500–5200 — a floor 48% below the
  published minimum. `mu_max` has never been fitted to the anchor; it carries its
  initial value. `b_max` is set from the anchor's own upper bound, so the range is not
  an independent check either. Re-sourcing the anchor and deciding what, if anything,
  is fitted to it is package A0 of
  `docs/superpowers/specs/2026-09-13-dst-data-layer-design.md`. Commit `6d36187`'s
  message says fixing the forcing "moves the Tagalaht anchor that mu_max was tuned to
  hit" and cites a 3.61 umol N/L figure; both are superseded — that commit message is
  published history and cannot be corrected, but `mu_max` has never been fitted to the
  anchor (above), and the corrected account, including the retired figure, lives in
  `forcing.py`'s docstring, `tests/test_cultivation_window.py`, and
  `docs/superpowers/specs/2026-09-13-dst-data-layer-design.md` §3.1.
- `test_pressure_is_never_folded_into_the_ranking` — the beside-never-merged rule, in
  executable form.
- `test_bad_eutropy_input_does_not_break_the_assessment` — an unusable optional engine
  must leave the ranking identical and report the failure.
- `test_no_south_baltic_species_claims_local_calibration` — expected to be *updated*,
  not deleted, when the first parameter set is promoted to tier A.
- `test_report_carries_the_site_label_and_the_caveats` — the report is where a caveat
  gets lost, so it is asserted.
- `test_nutrient_forcing_is_a_property_of_the_site_not_the_query` — carried a strict
  `xfail` until calendar-day indexing landed, so the finding could not quietly
  evaporate. It now passes and guards the property instead, at `rel=1e-2`: the
  seasonal term's 365.25-day period against a whole-365-day step across the wrap
  leaves a ~1.8e-03 residual that no amount of correctness removes.

## Licence and durability

EUPL-1.2 (`LICENCE.md`). The Application Form commits the Lead Partner to keeping the
tool online, on KU MRI servers, with open-access source and data layers, **for at
least five years after project end — to May 2034**, with no maintenance budget. That
is why the core has four dependencies, why there is no database server, and why every
optional engine is optional.
