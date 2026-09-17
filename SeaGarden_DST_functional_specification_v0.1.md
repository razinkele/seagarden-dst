# SeaGarden Decision Support Tool — Functional Specification

**Working draft v0.1 — towards Deliverable D2.2, "Decision-Support Tool prototype and functional specification (digital format)"**

| | |
|---|---|
| Project | SeaGarden — Regenerative Marine Farming in the South Baltic Area (STHB.02.02-IP.01-0006/25) |
| Deliverable | D2.2, due M24 (reporting period April–September 2028) |
| Activity | A2.3, M12–30, **led by Klaipėda University**, all partners except IBW PAN |
| Output | Output 2 of 3, RCO116 "Jointly developed solutions" — *Decision-support toolbox in regenerative seafarming (online tool)* |
| Author | Klaipėda University, Marine Research Institute |
| Date | 13 September 2026 |
| Status | Internal working draft. Not yet circulated to WP2 partners. |
| Revision | 13 September 2026 — implementation language changed from R to Python (§3.2). Consequential changes in §8.1–8.3, §13, §14. Decision **D1 resolved**: *Chorda filum* ships in v1 on assumed analogue parameters (§5.3, §11). See also "Amendments since v0.1" below for corrections recorded after this revision line was last written. |

*This draft combines the Application Form mandate (see `SeaGarden_DST_proposal_extract.md`) with the reusable assets identified in the OLAMUR review (see `OLAMUR-solutions-for-SeaGarden.md`). Wherever the two disagree, the Application Form governs and the disagreement is recorded in §11.*

---

## Amendments since v0.1

This section was added on 17 September 2026, after a repository audit found that several §3.2 "Stack" claims and one §5.1 claim had been overtaken by decisions made after this document's 13 September 2026 text was written. **The original text below is left exactly as written** — a partner comparing this copy against v0.1 will find no sentence quietly changed. Each affected row/bullet carries a marker (**[Amendment N]**) pointing back here.

- **[Amendment 1] — 17 September 2026, §3.2 Application/Spatial rows.** The map stack changed from `shinywidgets` + `ipyleaflet` to `shiny_deckgl` (KU MRI's own Shiny-for-Python to deck.gl/MapLibre bridge, github.com/razinkele/shiny_deckgl), per `pyproject.toml`'s `spatial` extra comment and `CHANGELOG.md` 0.5.0. `shiny_deckgl` is **not a pip dependency** — it is distributed only on the `razinka` conda channel and is installed as an environment prerequisite (`micromamba install -n shiny -c razinka shiny-deckgl`), documented in `README.md` and `docs/runbooks/deploy.md`. Nothing in the shipped app imports `ipyleaflet` or `shinywidgets` any longer. The map module (`app/modules/site.py`) renders the deck.gl map (`MapWidget`, `scatterplot_layer`) when `shiny_deckgl` is importable, and degrades to a sub-region selector with an explanatory note when it is not (`app/modules/site.py:93-176`); `app/shell.py` loads the deck.gl/MapLibre page assets the same way.
- **[Amendment 2] — verified 17 September 2026, §3.2 Dependencies/Deployment rows.** As things stand, there is no committed lockfile (`git ls-files` has no lock-format file) and no Docker packaging (`git ls-files` has no Dockerfile or compose file). The live deployment is a shared micromamba environment at `/opt/micromamba/envs/shiny` on `laguna.ku.lt`, an editable `pip install -e ".[app]"`, a `seagarden-dst.service` systemd unit on `127.0.0.1:8140`, and an nginx location include — see `docs/runbooks/deploy.md`. Conda is also a prerequisite for the map library (Amendment 1), so "no conda" no longer holds for the app as installed, even though the core package itself remains pip-only. The lockfile and container packaging described in the original row are not yet delivered; §12's delivery plan lists "deployment automation" under phase 3 (M24–30), which is the closest existing commitment to close this gap, though it does not name a lockfile or Docker specifically.
- **[Amendment 3] — verified 17 September 2026, §3.2 Model core row.** The shipped core dependency set is `numpy`, `scipy`, `pydantic`, `pyyaml` (`pyproject.toml`) — not `pandas`. `pandas` is deliberately kept out of the core and lives in the `app` extra (used for scenario comparison tables); `tests/test_packaging.py::test_the_core_package_does_not_import_pandas_at_module_level` fails the build if the core imports it at module level. `pydantic`, present in the original Parameters row, is also part of the core dependency list, not a separate add-on.
- **[Amendment 4] — verified 17 September 2026, §3.2 Raster storage row.** The shipped data-layer artifact is a single NetCDF4 file (`forcing.nc`, written with `to_netcdf(engine="h5netcdf")`, principally dimensioned `(year, month, latitude, longitude)` — one forcing variable, `significant_wave_m`, is monthly-only with no `year` dimension — checksum-paired with a JSON manifest) — not cloud-optimised GeoTIFF. `rasterio`/`rioxarray` sit in the `spatial` extra used at build time for source ingest and reprojection, not for serving the runtime artifact, which is read with `xarray`/`h5netcdf`. The format was decided by measurement in package B (`docs/2026-09-15-package-b-measurements.md`), after this document's stack table was written.
- **[Amendment 5] — verified 17 September 2026, §5.1 first "Environmental summary" bullet.** No integrated Baltic data product carries photosynthetically active radiation (PAR) in any form; package B established this. PAR is therefore **not** one of the measured climatology layers the §6 data layer delivers — the data-layer manifest records `surface_par` as an explicitly *absent* field, and the tool falls back to a fixed placeholder constant that must be displayed as a placeholder (the same way staleness is displayed), never presented as a measurement alongside the other five quantities.

---

## 1. Purpose and design premise

The SeaGarden DST is an open, web-based tool that helps four distinct audiences decide **where** a community-scale regenerative marine farm can go in the South Baltic, **what** to grow there, **how much nutrient it will remove**, and **what it takes to get permission and keep it running**.

Three premises shape every decision below.

**Premise 1 — There is no development budget.** All twelve WP2 budget lines are staff, in-kind, or two external items unrelated to software (§ proposal extract, §4). The tool is therefore *assembled*, not written: from OLAMUR's published models and modules, from KU MRI's existing DST codebases, and from open pan-Baltic data services. Any design that implies commissioned development, a licensed component, or a recurring subscription is out of scope by construction.

**Premise 2 — It must outlive the project by five years.** The durability clause commits KU MRI to hosting until May 2034 with open-access source and data. That argues for the smallest viable stack: no exotic dependencies, no service that needs a paid account, and a deployment a single person can rebuild from a repository in an afternoon.

**Premise 3 — The South Baltic is the part of the Baltic nobody has calibrated.** OLAMUR's ODSS draws its growth-model training data from Estonia, Finland, Sweden, Denmark and Germany. Lithuania and Poland are not calibration sources. Every number the tool produces for the SE Baltic before SeaGarden's own pilot data arrives is an extrapolation, and the tool must say so on the face of the result rather than in a footnote. This is treated as a first-class design requirement, not a caveat — see §7.

---

## 2. Compliance matrix

Every function the Application Form commits to, and where this specification discharges it.

| # | AF commitment | Source | Spec section |
|---|---|---|---|
| 1 | Display local environmental and hydrographic data — nutrient loads, salinity, water temperature, carrying capacity | Output 2 definition | §6 Data layer, §5 Siting |
| 2 | Provide maps of suitable sites for regenerative aquaculture (seaweed, mussels) | Output 2 definition | §5 Siting and farm planning |
| 3 | Help users compare farming methods and scales | Output 2 definition | §5.4 Scenario comparison |
| 4 | User and context-sensitive entry-point system, customised guidance per user category | Output 2 definition | §4 Users and entry points |
| 5 | Align with nutrient-reduction and sustainable-water-use policy | Output 2 definition | §9 Regulatory layer |
| 6 | Species choice | A2.3 title | §5.3, §7.2 |
| 7 | Ecosystem-service and nutrient-removal modelling | A2.3, D2.2 | §7 Growth, yield and nutrient removal |
| 8 | Procedural and regulatory guidance | A2.3, D2.2 | §9 Regulatory and permitting layer |
| 9 | User-friendly, transferable, supports harmonised planning across the South Baltic | A2.3 | §3 Architecture, §4 |
| 10 | Co-developed through iterative partner and stakeholder input | A2.3 | §12 Delivery plan |
| 11 | Confirmed (e-registered) use by organisations | RCR measurement method | §10 Registration and indicator evidence |
| 12 | Online, LP-maintained ≥5 years, open-source code and data, KU MRI hosting | Durability clause | §3.4, §13 |

Items 4, 8 and 11 have **no precedent in OLAMUR** and are the genuinely new work. Items 1, 2, 3, 6 and 7 are largely assembly.

---

## 3. Architecture

### 3.1 Shape

A single web application over a **stateless model core**, with a thin persistence layer for registered users and saved scenarios.

```
                   ┌─────────────────────────────────────────┐
                   │  Entry-point router (§4)                │
                   │  authority │ farmer │ community │ research│
                   └───────────────┬─────────────────────────┘
                                   │
      ┌────────────────┬───────────┴────────┬──────────────────┐
      │                │                    │                  │
┌─────▼──────┐  ┌──────▼───────┐  ┌─────────▼──────┐  ┌────────▼───────┐
│ M1 Siting  │  │ M2 Growth &  │  │ M3 Risk        │  │ M4 Viability   │
│ & planning │  │ nutrient     │  │ (optional, §8) │  │ (§8.4)         │
│    (§5)    │  │ removal (§7) │  │                │  │                │
└─────┬──────┘  └──────┬───────┘  └────────┬───────┘  └────────┬───────┘
      │                │                    │                  │
      └────────────────┴─────────┬──────────┴──────────────────┘
                                 │
                   ┌─────────────▼──────────────┐
                   │ Model core: parameter sets │
                   │ + calibration registry(§7.4)│
                   └─────────────┬──────────────┘
                                 │
                   ┌─────────────▼──────────────┐
                   │ Data layer (§6): rasters,  │
                   │ vectors, regulatory tables │
                   └────────────────────────────┘
```

### 3.2 Stack

| Layer | Choice | Why |
|---|---|---|
| Application | **Shiny for Python** (`shiny`, `shinywidgets`) **[Amendment 1]** | Python is KU MRI's working language for this class of tool — pymarxan, the HELCOM WMS viewer, bowtiepy, the EUTROPY/OSMOPY chain — so the DST is maintainable by the same people and reusable from the same workflows. Shiny's reactive model suits a tool whose outputs all recompute from a drawn polygon and a few selectors. |
| Spatial | `rioxarray` / `xarray` (rasters), `geopandas` / `shapely` (vectors), `pyproj`, `ipyleaflet` via `shinywidgets` (map and polygon drawing) **[Amendment 1]** | Covers everything §5 needs — zonal statistics, overlay, reprojection, interactive draw — with no service dependency. |
| Model core | Pip-installable package `seagarden_dst` (`numpy`, `scipy`, `pandas`) **[Amendment 3]** | Pure functions, no UI imports. Testable with `pytest`, callable from a notebook or a batch script, and importable into other KU MRI model chains. |
| Parameters | YAML parameter sets validated by `pydantic` models, version-controlled | Coefficients swappable without touching code — essential for the M24→M30 recalibration (§7.4). Pydantic catches a malformed parameter file at load rather than mid-analysis. |
| Persistence | SQLite via `sqlite3` (registrations, saved scenarios) | No database server to maintain for a decade. |
| Raster storage | Cloud-optimised GeoTIFF, pre-clipped to the South Baltic, read with `rasterio`/`rioxarray` **[Amendment 4]** | No PostGIS, no tile server. |
| Deployment | Docker image, `uvicorn` ASGI server, nginx reverse proxy, KU MRI server **[Amendment 2]** | One `docker compose up` rebuild. Sits alongside the existing laguna.ku.lt tooling. |
| Dependencies | `pyproject.toml` with a committed lockfile; no conda **[Amendment 2]** | A decade-old environment has to be reconstructible from the repository alone. |
| Repository | Public Git, **EUPL-1.2** | Discharges the open-source commitment; EUPL is the EC-recommended licence and is copyleft-compatible with the partners' institutional policies. |

**On the language choice.** OLAMUR's published modelling is R — boosted regression trees via `gbm`/`dismo`, and Maar et al.'s salinity-weighting and spatial-averaging code written against `terra`. Choosing Python therefore costs a re-implementation of that spatial-weighting step (`terra` → `rioxarray`/`xarray`) and, if BRT fitting is ever needed, a switch to `sklearn.GradientBoostingRegressor`, which OLAMUR's own documentation names as the direct equivalent. That cost is modest and bounded: the substance being borrowed from D3.2 is a **set of equations, not a codebase**, and equations port without loss (§7.2 integrates them with `scipy.integrate.solve_ivp`).

Against that, Python wins on three counts that matter more over ten years. It matches KU MRI's existing estate and maintainer skills. It makes OLAMUR's D5.2 service tools **native rather than foreign** — the alien-species wrapper is Python and Selenium, SIN1D is pure Python on `py-pde`, and the EWS/OOP NetCDF pipelines are `xarray` work — which measurably improves the case for §8. And a single-language codebase with one lockfile is the cheapest thing to keep alive on an unfunded maintenance commitment.

A bilingual stack — R for models, Python for the application — is explicitly rejected. One language, one maintainer skill set, for ten years.

### 3.3 What is deliberately excluded

- No user-uploaded bathymetry or environmental data. Fixed, curated layers only.
- No hydrodynamic modelling in the tool. Where circulation matters (carrying capacity, Szczecin Lagoon), the tool consumes pre-computed fields, it does not solve them.
- No real-time data feeds in v1. Copernicus climatologies are updated on a manual annual cycle.
- No mobile app. Responsive web only.

### 3.4 Hosting

The durability clause places the tool on **KU MRI servers**; WP4 places it in the **EUCC-D SeaGarden Knowledge Hub**. These are reconciled as: the Hub carries a **descriptive landing page and a deep link**, the application itself runs at a stable KU MRI URL under KU's control. Embedding by iframe is rejected — it makes the five-year commitment hostage to a platform KU does not administer. *This requires EUCC-D's agreement; see §11, decision D3.*

---

## 4. Users and entry points

The "user and context-sensitive entry point system" is a contractual commitment (compliance item 4) with no precedent to copy. The design: **one engine, four doors.** Each door presents a different question, a different default scale, and a different output register. None of them hides the underlying numbers — the researcher view is always one click away.

| Door | Who | Opening question | Default scale | Primary output |
|---|---|---|---|---|
| **Plan** | National and local authorities, spatial planners | *"Where in this area could regenerative farming go, and what would it achieve?"* | Sub-basin to coastal stretch | Suitability map, conflict layers, aggregate nutrient-removal potential, policy-alignment summary |
| **Farm** | Farmers, SMEs, aquaculture operators | *"Can I farm at this spot, what should I grow, and what will I get out of it?"* | Single polygon, 0.1–10 ha | Yield and nutrient-removal estimate by species, method comparison, permitting checklist |
| **Start** | Coastal communities, NGOs, citizen-science groups | *"Could we run a small sea garden here, and what would it take?"* | Mini-farm unit, ~6–100 m² | Plain-language feasibility verdict, kit specification, seasonal calendar, who to ask for permission |
| **Explore** | Researchers, students, consultants | *"What do the models actually say, and how confident are they?"* | Arbitrary | Full parameter transparency, model provenance, downloadable results, calibration status |

Design rules for the entry points:

1. **The door sets vocabulary, not capability.** A community user who wants the nitrogen figure in kg N per harvest gets it; they simply are not shown it first.
2. **Every quantitative output carries its calibration tier** (§7.4) in the same visual element as the number itself.
3. **The Start door never returns a bare "no".** An unsuitable site returns the binding constraint and, where one exists, the nearest suitable alternative.
4. **No door requires registration to use.** Registration (§10) is for saving scenarios and for organisational attribution, never a gate.

The entry-point taxonomy must be validated in A2.2's stakeholder work (D2.1, M12) before it is built — it is currently KU's hypothesis, not a finding.

---

## 5. Module 1 — Siting and farm planning

Discharges compliance items 1, 2, 3, 6, 9. The functional analogue is OLAMUR's ODSS "Plan your FARM" (gis.sea.ee/odss), and this module is deliberately specified to be *recognisable* to anyone who has used it.

### 5.1 Draw and assess

The user draws or uploads a polygon, or picks a point with a radius. The tool returns, for that geometry:

- **Environmental summary** — salinity, sea surface temperature, DIN and DIP concentration, photosynthetically active radiation, depth, and significant wave height, each as a seasonal climatology with range (§6). **[Amendment 5]**
- **Physical screening** — depth within the workable window for the selected cultivation method; exposure classified from wave climatology; distance to shore and to the nearest landing point.
- **Human-use conflicts** — shipping lanes and traffic density, offshore wind farm areas and cables, MPAs and Natura 2000 sites, military areas, dredging and dumping grounds, designated fairways, existing aquaculture, bathing waters. Each returned as *overlap / adjacent / clear*, with the governing layer named.
- **Suitability verdict per species** — from §7, with calibration tier.

### 5.2 Suitability classification

Suitability is computed as the **minimum** across constraint classes, never an averaged index:

```
suitability(site, species, method) = min(
    physical_feasibility,     # depth, exposure, substrate for anchoring
    environmental_tolerance,  # salinity, temperature, light at depth
    growth_viability,         # predicted yield above a user-set floor
    legal_permissibility      # hard exclusions from §9
)
```

A weighted composite index is explicitly rejected. Averaging lets a site with a fatal legal exclusion score "moderately suitable" because the water is nice, which is precisely the failure mode a permitting authority cannot tolerate. Where a class fails, the tool names it.

### 5.3 Species

| Species | Status in SeaGarden | Model basis |
|---|---|---|
| *Ulva* spp. | Named in AF A3.4 as the target green alga; LT and DE pilots monitor its growth conditions | ODSS has an *Ulva* growth model; re-parameterised on A3.4 data from M24 |
| *Fucus vesiculosus* | Not in the AF; OLAMUR's documented low-salinity success | Direct adaptation of OLAMUR D3.2 (§7.2) |
| *Chorda filum* | KU's own field and sporification protocols; the realistic LT candidate. **Ships in v1** (decision D1) | **No published model.** Structural analogue of the Fucus formulation, coefficients assumed rather than fitted, tier C in every region until A3.4 |
| Blue mussel (*Mytilus* spp.) | "Mussels" named throughout the AF; mitigation culture is the relevant mode below 16 psu | Maar et al. 2023 salinity-banded harvest model; Vaher et al. 2024 decoupled shell growth for carbon |
| *Saccharina latissima* | Included for completeness and for the DK Great Belt site | ODSS model; **the tool must actively report that it fails below ~16 psu** rather than quietly returning a small number |

The sugar kelp case is the clearest illustration of why calibration tiers matter: OLAMUR's salinity scaling predicts under 25% of North Sea yield at Lithuanian salinities, and their own pilot found outright cultivation failure. A number and a finding disagree; the tool shows both.

### 5.4 Scenario comparison

Compliance item 3 — "compare farming methods *and scales*" — is met by a side-by-side scenario panel, up to four scenarios, varying:

- **Method**: the SeaGarden system taxonomy from WP3 A3.2 — anchoring unit (float, buoy/line) × cultivation unit (floating lines, sinking lines, rafts, mussel socks), plus the modular pontoon configurations built by KU and Alles Alge, and PP5's combined seaweed-and-shellfish platform.
- **Scale**: mini-farm unit (the A3.5 kit, ~6 m²) → community farm (0.1–1 ha) → small commercial (1–10 ha).
- **Species and polyculture**: single species or seaweed-plus-mussel combinations.

Each scenario returns predicted harvest biomass, N and P removed, carbon in harvested biomass, and — where §8.4 is in scope — indicative cost and labour.

---

## 6. Data layer

All layers pan-Baltic or better, all free, all redistributable.

| Layer | Source | Cadence |
|---|---|---|
| Salinity, temperature, currents | Copernicus Marine Service Baltic Sea reanalysis and analysis products | Annual refresh, seasonal climatologies |
| Nutrients (DIN, DIP), chlorophyll | Copernicus Baltic biogeochemistry; HELCOM assessment products | Annual |
| Bathymetry | EMODnet Bathymetry | On release |
| Waves | Copernicus Baltic wave hindcast | Annual |
| Shipping density, cables, wind farms, dredging | EMODnet Human Activities | Annual |
| MPAs, Natura 2000, HELCOM MPAs | EEA / HELCOM | Annual |
| Water body status, bathing waters | WFD reporting via EEA | Annual |
| National permitting geometries | Compiled in-project from A2.2 legal expertise | Once, M12; reviewed M24 |
| SeaGarden pilot observations | WP3 A3.4 | Rolling M12–30 |

Redistribution terms for each layer are recorded in the repository alongside the data, since the durability clause commits the project to open **data layers**, not only code. Any layer whose licence forbids redistribution is referenced by service call, not mirrored — and that dependency is logged as a durability risk (§14).

**Lithuanian and Polish waters** are covered spatially by all of the above. The gap is not coverage; it is *calibration* of the biological models (§7.4).

---

## 7. Module 2 — Growth, yield and nutrient removal

Discharges compliance items 1, 6, 7. This is the scientific core and the part most directly inherited from OLAMUR.

### 7.1 Structure

For a given site, species, method, scale and cultivation season, the module returns:

- harvested biomass (g DW m⁻², t FW ha⁻¹)
- nitrogen removed (kg N)
- phosphorus removed (kg P)
- carbon in harvested biomass (kg C)
- the growth trajectory over the season, for inspection in the Explore door

### 7.2 Macroalgal growth — adapted from OLAMUR D3.2

OLAMUR re-parameterised a *Saccharina* framework for *Fucus* after sugar kelp failed at low salinity in Tagalaht Bay (5.5–6.5 psu, essentially the SE Baltic range). The formulation is multiplicative:

```
dB/dt = μ_max · f(I) · f(T) · f(N) · B  −  losses(B)
```

- **f(I)** — irradiance, quantum-yield term
- **f(T)** — temperature, Arrhenius-type, DEB-style
- **f(N)** — nitrate limitation, Holling type II
- **No explicit salinity term.** OLAMUR found none was needed once the model was calibrated for Baltic conditions: salinity was not limiting for *Fucus* once adapted. This is an important and slightly counter-intuitive inheritance and should be stated explicitly in the tool's methods page, because users will expect a salinity term and its absence looks like an omission.
- Nitrogen, phosphorus and carbon are fixed tissue fractions applied to harvested dry
  weight, per species, from macroalgal stoichiometry — not Redfield, which is a plankton
  ratio. There is no internal nutrient reserve pool; the growth model carries a single
  state variable. Introducing a quota model is a structural change and is not scheduled.

Implementation: the seasonal trajectory is integrated with `scipy.integrate.solve_ivp` over the cultivation window, driven by the site's forcing climatology (§6) resampled to daily steps. All rate coefficients come from the parameter YAML (§7.4), never from the code.

Reference yields for validation, from Tagalaht Bay over an April–October cycle, per 6 m² cage: 4,800–5,200 g DW m⁻²; ≈10–13 kg C; 1.4–3.4 kg N; 15–120 g P.

For *Saccharina*, the module additionally carries OLAMUR's salinity scaling on maximum yield:

```
f_salinity = 1                   for S ≥ 25
           = 1 + (S − 25)/18     for 16 ≤ S < 25
           = S/32                for S < 16
```

applied to a maximum of 18.4 t FW ha⁻¹ from Danish sites above 16 psu.

### 7.3 Mussels

- Salinity-banded harvest model from OLAMUR D2.3 / Maar et al. 2023: **commercial culture** above 16 psu at 16–18 t FW ha⁻¹ yr⁻¹; **mitigation culture** below 16 psu at up to 33 t FW ha⁻¹ yr⁻¹ — higher per unit area because density is optimised for nutrient removal rather than individual size, and the product is not food-grade. The SE Baltic sits squarely in the mitigation band, and the tool should present that as the *intended* mode there, not as a degraded version of commercial culture.
- Elemental fractions applied directly: mussel FW → 10.3% DM, 1.45% N, 0.083% P, 4.61% shell C. Biomass-density scaling ρ = 1269 · m_bio^(1/3), with commercial density set 3.15× lower than mitigation density.
- **Carbon accounting convention.** Shellfish carbon capture is contested: calcification releases CO₂, so sequestration depends on the shell being physically removed from the water. Following Maar et al.'s deliberately conservative choice, the tool reports **carbon in harvested biomass only** and does not report sequestration. The Explore door explains why. Vaher et al. 2024's decoupled shell-growth DEB result — that low-salinity mussels, being small and shell-heavy, are carbon-efficient *per unit biomass* even though total yield is low — is presented as an efficiency framing, which is the honest and locally relevant one, and never converted into a sequestration claim.
- IMTA planning heuristic, available in the Plan and Farm doors: an 8 ha mussel farm offsets the N and P emissions of a standard finfish farm; 0.8 ha suffices for phosphorus alone with low-P feed pellets.

### 7.4 Calibration registry — the mechanism that makes §1 Premise 3 real

Every (species × region × parameter set) combination carries a tier, stored in the parameter YAML and surfaced in the UI beside every number derived from it.

| Tier | Meaning | Visual treatment |
|---|---|---|
| **A — Locally calibrated** | Fitted to SeaGarden pilot data from this sub-region | Value with confidence interval |
| **B — Regionally extrapolated** | Fitted elsewhere in the Baltic at comparable salinity; ODSS-style transfer | Value as a range, with the calibration region named |
| **C — Literature prior** | Published parameters, no local validation; the default for LT and PL before M24 | Order-of-magnitude band, explicitly labelled indicative |
| **D — Contraindicated** | A local finding contradicts the model (e.g. *Saccharina* below 16 psu), or the site lies below a salinity floor beneath which the parameters are not defensible | Finding shown in place of the number; for a floor, the floor and whether it is observed or assumed |

Anything short of tier D puts a confident-looking number back at 2.0 psu, which is the defect the floors exist to remove; a siting tool should fail safe, and the observed/assumed distinction lives in the note the user reads, not in the tier.

At the M24 prototype, essentially all SE Baltic cells are tier **C**. The M24–30 window promotes what A3.4 supports to tier **A**. Because tiers live in the parameter files rather than the code, that promotion is a data change, not a release — which is what makes the compressed schedule in §12 feasible.

---

## 8. Module 3 — Risk, and Module 4 — Viability

Both modules sit **outside the Application Form's mandate**. They are specified here because you asked for them in scope, but they are governed by an explicit rule: *implemented only where reuse is close to free, and never at the expense of compliance items 1–12.*

### 8.1 Alien species risk (ASR)

Direct reuse of OLAMUR D5.2's Python + Selenium wrapper around the **AquaNIS** non-indigenous species database (HELCOM/OSPAR coverage). API shape: `AquaNISbrooker.scan_introduction_list(species=…, location=…)`. On a Python stack this drops straight into the model core as a dependency — no bridge, no port. Value is high for the permitting conversation, since introduction risk is a standard objection to new cultivation. *Caveat: a Selenium-driven scraper is a durability liability — it breaks when AquaNIS changes its pages, and it drags a browser binary into the Docker image. Wrap it behind a cached local snapshot refreshed manually, so a broken scraper degrades to stale data rather than a broken tool, and keep the scraper itself out of the runtime image.*

**Recommendation: in scope.**

### 8.2 Disease propagation risk (DPR)

OLAMUR D5.2's open SIN (susceptible–infected–transmission vector) spatial epidemic model for sessile marine crops: SIN1D in pure Python (`py-pde`), SIN2D in Fortran 90 with `f2py` bindings. Ships with a relevant pathogen list for *Fucus* and kelps — *Pseudoalteromonas piscicida*, *Laminariocolax*, *Laminarionema*.

**Recommendation, revised for the Python stack: take SIN1D and the pathogen list, leave SIN2D.** `py-pde` is a pure-Python dependency that installs from PyPI and pins cleanly, so the one-dimensional model is now cheap enough to justify — which it was not when the application was to be written in R. SIN2D is a different proposition: a Fortran 90 extension built through `f2py` needs a compiler in the build chain and is the component most likely to break on a future Python or NumPy release, which is exactly the kind of liability an unfunded ten-year commitment cannot carry. Take the pathogen list either way — *Pseudoalteromonas piscicida*, *Laminariocolax*, *Laminarionema* — and mirror it into the Technical Toolkit as a qualitative risk note.

### 8.3 Event warning and operation planning (EWS/OOP)

CMEMS-plus-national-weather pipelines producing storm and bloom warnings and weather-window calculators, documented step by step (CDO/NetCDF) in D5.2's appendix. The NetCDF processing described there is ordinary `xarray` work on this stack, and reuses the same wave and wind climatologies §6 already loads.

**Recommendation: implement the weather-window calculator only, from climatology, not forecasts.** "In an average year, how many workable days does this site offer in the deployment and harvest windows?" is a planning question the DST can answer permanently and cheaply. Live storm warnings are an operational service with an operational maintenance burden and a liability profile, and they belong outside this tool.

### 8.4 Viability — the community and business door

The weakest-founded module, and the one to be most disciplined about.

The AF gives the DST only "compare farming methods and scales" on the economic side; financing options are explicitly GMU's territory in the Technical Toolkit (A2.5, €12,000 external including financial assessment). OLAMUR offers nothing: **D6.2 (LCA) and D6.3 (market-entry scenarios) remain unpublished** as of September 2026 and may not arrive before SeaGarden needs them.

Scope accordingly:

- **In scope:** a transparent, parameter-driven cost and effort calculator — capital cost of the chosen kit or system, deployment and harvest labour in person-days, consumables, expected harvest mass — with every coefficient user-editable and sourced from WP3's actual procurement (the pontoons, lines, anchors, buoys and kits the project really buys, at the prices it really pays). This is defensible because it is bookkeeping over project-observed costs.
- **In scope:** nutrient-removal value expressed in physical units, and, optionally, against published nutrient-abatement cost benchmarks, clearly labelled as a comparison rather than a revenue.
- **Out of scope:** life-cycle assessment, market price forecasting, business-model recommendation, and any claim about profitability. These need D6.2/D6.3 or equivalent, and asserting them without that evidence would be the least credible thing in an otherwise well-founded tool.

If OLAMUR publishes D6.2 and D6.3 before M24, revisit. Maar et al. 2023 (*Communications Earth & Environment* 4:447, DOI 10.1038/s43247-023-01116-6) is the peer-reviewed stand-in for the sustainability-goals framing in the meantime.

---

## 9. Regulatory and permitting layer

Discharges compliance items 5 and 8. This content does not exist yet and is not borrowable — it is produced in-project by GMU's A2.2 external legal expertise (€5,500) covering national laws and regulations, and tested against reality by WP3 A3.1, which runs actual permitting in DK, DE, PL and LT from day one.

### 9.1 Structure

For each of the four jurisdictions, a structured record rather than prose:

- **Competent authorities** — who decides what, with contact routes
- **Permit types** by activity and scale, including any threshold below which a mini-farm is exempt or simplified — the single most valuable fact for the Start door
- **Hard spatial exclusions** — consumed directly by §5.2's `legal_permissibility` term
- **Procedural sequence** — steps, typical durations, required documents, consultation obligations
- **Environmental assessment triggers** — EIA/SEA thresholds, Natura 2000 appropriate assessment
- **Policy hooks** — how the activity relates to the HELCOM Baltic Sea Action Plan, WFD water body objectives, MSFD descriptors, and the national Maritime Spatial Plan

### 9.2 Presentation

The Plan door gets the full procedural map; the Farm door gets a personalised checklist for the drawn polygon; the Start door gets the answer to "do we even need a permit for something this small, and who do we ask?"

### 9.3 Maintenance

Regulation drifts, and the five-year durability commitment turns this into the module most likely to go quietly wrong. Each record carries a "verified on" date and the tool displays it. When a record is more than two years old the tool says so on the record rather than silently presenting it as current.

---

## 10. Registration and result-indicator evidence

The RCR measurement method requires *"confirmed (e-registered) use of the DS Toolbox by organisations involved in the Baltic Sea restoration"*. Nothing in the work plan or budget provides for this, so it is specified minimally and built early.

- **Open by default.** All analytical functions work without an account. Registration is never a gate (§4, rule 4).
- **Organisational registration** unlocks saved scenarios, named exports and a workspace. Fields: organisation name, country, sector, contact e-mail, and a consent statement. Nothing more — the data collected is the evidence needed and not one field beyond it.
- **Evidence artefact.** A quarterly report: registered organisations by country and sector, scenarios saved, exports generated. This is what the project shows the JS against the RCR target of 3.
- **GDPR.** Personal data is limited to a contact e-mail under explicit consent, with a published retention period and deletion on request. The Programme's 2022 personal-data-processing principles apply, and EUCC-D, as the partner with the Hub and the communications role, should review the notice.
- Anonymous aggregate usage counting (page views, analyses run) uses a self-hosted, cookie-free counter — no third-party analytics, which would import both a dependency and a consent problem.

**Decision needed by M18** so that registration exists at first public exposure rather than being retrofitted (§11, D4).

---

## 11. Open decisions

| # | Decision | Options | Owner | By |
|---|---|---|---|---|
| ~~**D1**~~ | ~~Species list for v1~~ | **Resolved 13 Sep 2026.** All five ship: *Ulva* and blue mussel (named in the AF), *Fucus* (the OLAMUR-grounded low-salinity evidence), *Saccharina* (the DK site, and the worked tier D case), and ***Chorda filum* on assumed analogue parameters** — it is what KU will actually cultivate in Lithuania, and a tool that omits the local candidate is less useful than one that carries it honestly labelled. Condition: Chorda stays tier C in every region until its coefficients are fitted to A3.4 harvest data. Enforced by test, not by convention. | KU | done |
| **D2** | Is the prototype at M24 publicly reachable, or internal? | Public beta · partner-only · staged | WP2, GMU + KU | M15 |
| **D3** | Hosting split KU MRI vs EUCC-D Hub | Deep link from Hub (proposed, §3.4) · iframe embed · mirror | KU + EUCC-D | M18 |
| **D4** | Registration model | As specified §10 · lighter (e-mail only) · none, and renegotiate the RCR evidence | KU + LP management | M18 |
| **D5** | Risk modules in or out | ASR only (proposed) · ASR + weather window · none | KU | M18 |
| **D6** | Viability module boundary | Cost calculator only (proposed, §8.4) · extend if OLAMUR D6.2/D6.3 publish | KU + GMU (A2.5 interface) | M20 |
| **D7** | PP4 (IBW PAN) role | Formally outside A2.2/A2.3 per the AF, yet holds the Szczecin Lagoon pilot and €55k of WP3 staff. Consultee? Co-author of the lagoon parameterisation? | WP2 lead + LP | M12 |
| **D8** | Licence | EUPL-1.2 (proposed) · MIT · CC-BY-4.0 for data | KU legal | M18 |
| **D9** | Entry-point taxonomy | Validate the four doors (§4) against D2.1 findings before building | KU, from GMU's A2.2 output | M12 |

---

## 12. Delivery plan

A2.3 runs M12–30. D2.2 lands at M24. Output 2 must be a maintained public service. The plan below inserts the hardening phase that the work plan leaves implicit — the gap GMU flagged in the kick-off as *"Prototype vs. working online solution?"*

| Phase | Months | Work | Gate |
|---|---|---|---|
| **0 — Inputs** | M1–12 | A2.1 best-practice review, A2.2 stakeholder mapping and legal expertise → **D2.1 (M12)**. This specification matures against those findings; D7 and D9 resolved (D1 already taken). | Spec v1.0 accepted by WP2 partners |
| **1 — Foundation** | M12–18 | Data layer assembled (§6); model core packaged with OLAMUR-derived parameters at tier C; siting module skeleton. D2–D5, D8 resolved. | Internal demo, running end-to-end on literature priors |
| **2 — Build** | M18–24 | Growth and nutrient modules (§7); entry-point routing (§4); regulatory records for four jurisdictions (§9); registration (§10). First stakeholder test at EUCC-D's local meetings (WP2 line 2.3). | **D2.2 delivered M24** — prototype plus this specification, final |
| **3 — Calibrate and harden** | M24–30 | Promote parameters to tier A as A3.4 data arrives; second stakeholder round; accessibility, performance, documentation; deployment automation; the repository made public. | **Feature freeze M30** |
| **4 — Publish and hand over** | M30–36 | Output 2 live at the stable KU MRI URL; Hub landing page and deep link (A4.3/A4.5); training material linkage to A2.4; maintenance runbook written. | Output 2 reported; RCR evidence from §10 |
| **5 — Durability** | to May 2034 | Annual data refresh; regulatory re-verification (§9.3); dependency updates. | — |

The critical dependency is **A3.4 pilot data reaching the model team early enough to matter**. Data arriving after M28 cannot be absorbed before the freeze. A quarterly data handover from WP3 to A2.3, agreed at the next WP2 meeting, is the cheapest possible insurance.

---

## 13. Effort and cost

No development budget exists (§1). Indicative KU effort, drawn against WP2 line 2.1 (€51,250, which also covers KU's share of A2.1, A2.2, A2.4 and A2.5):

| Work | Person-months |
|---|---|
| Architecture, model core, calibration registry | 4 |
| Porting OLAMUR's `terra` spatial-weighting step to `rioxarray`/`xarray` | 0.5 |
| Data layer assembly and annual refresh tooling | 2 |
| Siting module and UI | 3 |
| Entry points, registration, documentation | 2 |
| Calibration and validation against A3.4 | 2 |
| Deployment, hardening, handover | 1 |
| **Total** | **≈14.5** |

Partner contributions come from their own WP2 staff lines: GMU on regulatory content and best-practice synthesis, EUCC-D on the community door and the two local validation meetings, Kerteminde Seafarm and Alles Alge on method and scale realism.

Recurring cost after project end: server capacity within KU MRI's existing estate, plus roughly 5 person-days per year for the data refresh and regulatory re-verification. That figure should be stated explicitly to KU MRI management before the durability commitment is confirmed, because it is the commitment nobody has yet been asked to fund.

---

## 14. Risks

| Risk | Effect | Mitigation |
|---|---|---|
| No development budget, effort under-estimated | Prototype slips past M24 | Assembly-not-construction discipline; scope items 8.1–8.4 are the first to be cut |
| A3.4 data arrives after M28 | SE Baltic outputs stay at tier C at launch | Quarterly WP3→A2.3 data handover; calibration as a data change, not a release |
| Chorda has no growth model and no literature parameters | Headline LT species is the least modelled | Structural analogue from *Fucus*, tier C, explicit; fit from pilot data in phase 3 |
| Five-year hosting is unfunded | Tool dies quietly after the project | Minimal stack; costed maintenance figure (§13) put to KU MRI management before commitment |
| The annual data-layer refresh is a manual act by one unfunded person, with the layer's only copy a build output | That person leaves; the refresh lapses and the data-durability commitment fails quietly | Runbook written for a successor, not its author; Copernicus credential held institutionally, not personally; each refresh archived under a DOI so the data survives the script; scheduled source-probe checks each source still answers and is allowed to fail loudly |
| Scraper and external-service dependencies break | Silent failures years later | Cached snapshots; degrade to stale, never to broken; Selenium kept out of the runtime image |
| OLAMUR's published spatial code is R; the DST is Python | Re-implementation of the salinity-weighting and spatial-averaging step, with a risk of silent numerical divergence | Port once, early (§13, 0.5 PM); validate against the Tagalaht reference yields in §7.2 and against Maar et al.'s published figures before the numbers reach any user |
| Regulatory records go stale | Tool misleads users on permitting | "Verified on" dates displayed; two-year staleness warning (§9.3) |
| Users read tier-C numbers as measurements | Over-confident siting decisions, reputational damage | Calibration tier rendered inside the number's own visual element, not in a footnote |
| Overlap with the Technical Toolkit (A2.5) and training (A2.4) | Duplicated effort, confused users | Explicit boundary: DST computes, Toolkit instructs, training explains; each links to the others |

---

## References

- OLAMUR (Horizon Europe 101094065) deliverables D2.3, D3.2, D5.2; ODSS geoportal, gis.sea.ee/odss
- Maar, M. et al. (2023). Multi-use of offshore wind farms with low-trophic aquaculture can help achieve global sustainability goals. *Communications Earth & Environment*, 4, 447. https://doi.org/10.1038/s43247-023-01116-6
- Vaher, A. et al. (2024), decoupled shell-growth DEB formulation, as cited in OLAMUR D2.3
- SeaGarden Application Form STHB.02.02-IP.01-0006/25, version 3 in force (2026-06-12); Supplementary Application Form; Clarification Document (2026-06-09)
- `OLAMUR-solutions-for-SeaGarden.md`; `SeaGarden_DST_proposal_extract.md`
