# Package C — refresh tooling

**Status:** design, awaiting review. Package C of
`docs/superpowers/specs/2026-09-13-dst-data-layer-design.md` §8. Written 15 September 2026,
against that document at revision 5 and against package B's measurements in
`docs/2026-09-15-package-b-measurements.md`.

**Reference convention** is inherited: `spec §N` means the functional specification,
a bare `§N` means the data-layer design, and `C§N` means a section of this document.

Package C delivers the tooling that builds the forcing artifact package D reads: the
refresh script, the provenance manifest, the archive route, the runbook, the source-probe
job and the test fixture. It does not read the artifact — that is D — and it does not build
the human-use vectors — that is C1, which reuses this document's manifest machinery.

---

## C§1 Decisions taken before design

Five choices were settled with the repository owner before this design was written. They
are recorded here because each one closes off alternatives the design would otherwise have
to keep open.

| Decision | Choice | Why |
|---|---|---|
| **Does C deposit to Zenodo?** | **No.** The step is implemented and documented; the manifest carries the DOI field; a human runs the first real deposit. | A Zenodo DOI is permanent, public and published under the project's name, and needs institutional credentials. Everything C does stays reversible. |
| **Baseline years** | **2016–2025**, the last ten full calendar years. ~170 MB on disk (590 MB uncompressed, at B's measured 3.5× NetCDF4+zlib4 ratio). | B measured interannual spread as the dominant term (−57% to +179%). Three years cannot characterise that; a decade can. Recent enough that Baltic warming and falling nutrient loads do not make early years unrepresentative of a siting decision taken now. |
| **Waves** | **Monthly 95th percentile from a three-year sub-baseline** (2023–2025), streamed. `significant_wave_max_m` deferred. | The hourly product costs ~8.6 GB per year of transfer against ~0.42 GB/year for every other layer combined (C§3.4, C§8.1). A p95 is not a tail statistic — three years gives ~2,200 hourly values per cell per month — so the extra seven years buy stability it does not need. The annual maximum *is* a tail statistic, which is why it is deferred rather than computed badly. |
| **Sources** | **Copernicus + EMODnet Bathymetry.** HELCOM dropped. | Copernicus BGC already carries `no3`, `nh4` and `po4`, which is everything `din_umol_l` and `dip_umol_l` need, so HELCOM would be provenance burden for no added field. EMODnet earns its integration: see C§2. |
| **Architecture** | **Thin layer-plugin package**, not a linear script and not a config-driven engine. | C§5. |

---

## C§2 Why EMODnet, and not the reanalysis bathymetry

Copernicus ships model bathymetry on the same 2 km grid, which would make depth free. It is
rejected, and the reason is specific rather than general.

`depth_m` is not a descriptive field. `api.select_method` gates on it:

```python
m for m in candidates if m.min_depth_m <= conditions.depth_m <= m.max_depth_m
```

`params/methods.yaml` sets those bounds at 2, 3, 4, 5 and 6 m minimum. A 2 km cell mean
near shore will commonly read 10–15 m where the actual site is 5 m, so model bathymetry
would mis-gate **which cultivation methods a site is offered** precisely where the
thresholds cluster. EMODnet Bathymetry is ~115 m.

`depth_min_m` is carried alongside `depth_mean_m` because §6.1 asks for "mean, with min
reported", and because the minimum is the number that matters for a structure with draft.

---

## C§3 The artifact

One NetCDF4 file, fixed name `forcing.nc`, in `$SEAGARDEN_DATA_DIR` (default `data/`),
written with zlib complevel 4 — package B's format decision.

### C§3.1 Extent

**53.5–60.0 N, 9.5–27.0 E**, on the Copernicus native grid (0.016666° lat × 0.027777° lon,
≈1.85 × 1.69 km), giving 390 × 630 = 245,700 cells.

This is package B's measurement box, and it covers all six placeholder regions. **It
excludes the Gulf of Bothnia and the Gulf of Finland.** That is a scope choice, not a
limit of the method: SeaGarden's pilots are south and central Baltic, and the full product
extent would be ~2.4× the cells and ~400 MB on disk rather than ~170 MB. The grid definition lives
in one `GridSpec` (C§5), so widening it is a one-line change plus a refresh.

Native resolution is **not** a choice — B established that coarsening to ~4 km land-masks
the cell containing Tagalaht, the only published anchor the parameterisation has.

### C§3.2 Variables

**The variables do not all share a shape.** This is a direct consequence of C§1's wave
decision and it propagates into the manifest (C§4) and into D's reader.

| variable | dims | source | statistic |
|---|---|---|---|
| `salinity_psu` | year, month, lat, lon | `so` | monthly mean |
| `temp_c` | year, month, lat, lon | `thetao` | monthly mean |
| `din_umol_l` | year, month, lat, lon | `no3` + `nh4` | monthly mean |
| `dip_umol_l` | year, month, lat, lon | `po4` | monthly mean |
| `light_attenuation_k` | year, month, lat, lon | **daily** `zsd`, **derived** | monthly mean of *daily* 1.7/z_SD — see C§3.4 |
| `significant_wave_m` | **month, lat, lon** | hourly `VHM0` | **monthly p95**, 2023–2025 |
| `depth_mean_m` | **lat, lon** | EMODnet | mean per cell |
| `depth_min_m` | **lat, lon** | EMODnet | min per cell |

Coordinates: `year` (2016–2025), `month` (1–12), `latitude`, `longitude`. CRS EPSG:4326,
recorded as a variable attribute and in the manifest.

The **Copernicus fields are taken at the surface level, 0.50 m** — the shallowest of the
reanalysis's 56 levels, the choice package B made and §6.1 now records. That is a
*model level*, and has nothing to do with `depth_mean_m`/`depth_min_m`, which are seabed
bathymetry from EMODnet. All fields are float32; land and out-of-domain cells are NaN,
which is the validity mask D reads for §6.2's containing-cell rule — but see C§3.5, because
there is more than one of them.

`light_attenuation_k` is stored **derived rather than raw**: the artifact carries k, not
`zsd`, with the Poole–Atkins relation named in the manifest. Storing the derivation rather
than the input is deliberate — it keeps D from re-implementing the relation, and it means
the tier a result inherits can be read off the manifest.

### C§3.3 `surface_par` is absent, on purpose

The artifact carries **no** `surface_par` field. Package B established that no integrated
product has PAR in any form. Writing a fabricated or interpolated field would produce
exactly the failure this project has spent three packages removing: a number that looks
sourced and is not.

`GriddedForcing` supplies the placeholder constant and marks it, and the manifest records
the absence in machine-readable form (C§4.2) so §7's display requirement reads from data
rather than from a hardcoded caveat that can drift.

---

### C§3.4 Why light attenuation needs the daily product, and what it costs

This is the one variable whose source product is fixed by the *shape* of its statistic
rather than by convenience, and getting it wrong biases the model in a direction this
project has consistently refused.

k is a **non-linear** function of the source: k = 1.7/z_SD. Averaging does not commute
through it. Taking monthly `zsd` from `cmems_mod_bal_bgc_my_P1M-m` and computing
1.7/mean(z) is **not** mean(1.7/z), and by Jensen's inequality — 1/x being convex for
x > 0 — the monthly-input route is systematically **lower**. A lower k means less
attenuation, so **more** PAR at cultivation depth, so an **optimistic** growth bias. It
would be a silent one: the field would look correct and carry no marker.

So the BGC layer pulls **daily** `zsd` from `cmems_mod_bal_bgc_my_P1D-m`, computes k per
day, and averages k over the month. Every other variable is linear in its source, so
monthly-mean inputs are correct for them and the monthly product is used.

This was established by re-reading package B's own pull: B computed 0.198 at Tagalaht from
`cmems_mod_bal_bgc_my_P1D-m`, the daily product, so B's figure is sound and it was this
document that first named the wrong product.

**It costs transfer, and the runbook figures in C§8.1 include it:** daily `zsd` over ten
years is ~0.36 GB/year, ~3.6 GB in total, against ~0.59 GB for every monthly variable
combined. It does not change the artifact size, which stores monthly k either way.

### C§3.5 One validity field, because the sources disagree at the coastline

An earlier draft of this section said "land and out-of-domain cells are NaN, which is the
validity mask" as though there were one. There are two, and they disagree exactly where it
matters.

Copernicus land-masking is on the 2 km model grid; EMODnet bathymetry coverage is an
independent product at ~115 m. A cell can be wet in one and absent in the other, and the
disagreement is concentrated at the coastline — which is where every farm is.

**The driver therefore writes an explicit `valid` boolean field**, the intersection of all
contributing layers' coverage, and D reads that rather than inferring validity from
whichever variable it happened to look at. The manifest records which layers the
intersection covers.

**This is not defensive tidiness.** Verified in the current code: if `depth_m` reaches
`api.select_method` as NaN, every `m.min_depth_m <= conditions.depth_m <= m.max_depth_m`
comparison is false, `workable` is empty, and `pool = workable or candidates` falls through
to returning a method anyway. `suitability.assess_physical` then evaluates
`not (min <= nan <= max)`, which is `True`, and returns a confident **`UNSUITABLE`**:
*"Depth nan m is outside the workable window"*. A definitive negative verdict manufactured
from missing data — precisely what §7 exists to prevent, and it becomes reachable the moment
D reads a real artifact.

Writing a single `valid` field is C's half of the fix. **The NaN-handling defect in
`select_method`/`assess_physical` is package D's half**, and C§11 records it as an
amendment so it is owned rather than noticed.

## C§4 The manifest

`manifest.json`, beside the artifact, same directory, fixed name.

### C§4.1 Shape

```
artifact_schema_version : int          refused by D if unrecognised (§7)
built_on                : datetime     ISO 8601, UTC
artifact_filename       : str
artifact_sha256         : str          C§6's atomicity mechanism
artifact_bytes          : int
synthetic               : bool         true only for the test fixture (C§7)
grid                    : GridSpec     crs, bounds, steps, n_lat, n_lon
baselines               : {name: [years]}   per-variable, not per-artifact
layers                  : [LayerProvenance]
derived                 : [Derivation]
absent                  : [AbsentField]
```

`LayerProvenance` carries what §6.3 requires: `source`, `product_id`, `dataset_id`,
`version`, `retrieved_on`, `licence`, `redistribution` (`allowed` | `forbidden`),
`source_url`, and an **archive state** (below). §6.3's rule, stated once and not
paraphrased anywhere else in this document: a layer must carry **either a `zenodo_doi`, or
an explicit `redistribution: forbidden` marker with a `source_url`**. A layer carrying
neither fails §9's provenance test.

**That rule as written cannot be satisfied by anything package C produces, and this design
had to resolve it rather than restate it.** C§1 puts the Zenodo deposit outside package C,
so at manifest-construction time no layer has a DOI. All four layers are genuinely
redistributable, so `redistribution: forbidden` is not a truthful alternative — and setting
it to clear the validator would be precisely the mis-marked provenance this whole design
exists to prevent. Under the rule as written, C§6 step 4 fails on **every real refresh**,
and it would fail after the wave pull rather than before it.

The resolution is a third **named, honest** state rather than a weakened rule:

```
archive: {status: "deposited",  zenodo_doi: "10.5281/zenodo.NNNNNNN"}
archive: {status: "forbidden",  source_url: "https://..."}      # referenced-not-mirrored
archive: {status: "pending",    source_url: "https://...", unblocked_by: "..."}
```

`pending` means *built, not yet deposited* — the state every layer of a first real refresh
is in. It requires a `source_url` and an `unblocked_by` note, structurally mirroring
C§4.2's `absent` block, so the gap is recorded in the artifact rather than papered over.
The validator accepts exactly these three and nothing else; a layer with no archive state,
or `pending` with no `source_url`, still fails at load. §7 gains a display row (C§11): an
artifact whose layers are `pending` is usable but **says so**, the same way `surface_par`
does.

`baselines` is a mapping rather than a single field because C§1 gave waves a different
baseline from the forcing variables. A single `baseline_years` at artifact level would be
a lie about one of them.

### C§4.2 Two additions beyond §6.3

**`artifact_sha256`.** Not decoration — it is what makes the artifact/manifest pair
verifiable, and it is what turns §6.3's unimplementable "written atomically as a pair" into
something a filesystem can actually provide. See C§6.

**`absent`.** A list of `{field, reason, unblocked_by}`. Today it has one entry,
`surface_par`. §7 requires the tool to display that PAR is a placeholder; making that
machine-readable means the UI reads the manifest instead of carrying a hardcoded caveat.
A0 spent two commits removing caveats that had drifted out of step with the code; this is
the cheap structural fix for that class of defect.

### C§4.3 The manifest is a Pydantic model

`seagarden_dst/refresh/manifest.py` defines the models with `extra="forbid"`, matching
`params.py`. §6.3's provenance rules are `model_validator`s, so a layer carrying neither a
valid archive state — `deposited` with a DOI, `forbidden` with a URL, or `pending` with a
URL and an `unblocked_by` note (C§4.1) — **fails at load**, not mid-analysis; the principle
`_check_salinity_indexed_is_computable` and the `Anchor` range validator already follow.

This makes §9's provenance test a model-load rather than a list of ad-hoc assertions, and
it means D and C1 validate the same way C wrote it.

---

## C§5 The layer protocol

`src/seagarden_dst/refresh/` — importable and testable — with `scripts/refresh_layers.py`
as the thin CLI entry point §6 names. **Nothing in `refresh/` may be imported by the
model core**, which keeps the `spatial` extra confined as §4 requires; a test asserts it.

```python
@runtime_checkable
class Layer(Protocol):
    name: str
    def probe(self) -> ProbeResult: ...
    def build(self, grid: GridSpec, workdir: Path) -> xr.Dataset: ...
    def provenance(self) -> LayerProvenance: ...
```

**`build()` is one method, not `fetch()` then `normalise()`.** The obvious split breaks on
waves: 26 GB cannot be fetched and then normalised, it has to be reduced while streaming,
one month-of-year at a time, with peak disk ~1 GB. Forcing that through a fetch/normalise
seam would contort every other layer to accommodate the one that cannot use it. Each layer
decides internally whether it streams; the driver sees only a dataset.

Four implementations — `copernicus_phy`, `copernicus_bgc`, `copernicus_wav`,
`emodnet_bathy` — and a `REGISTRY` that the driver and the probe job both read, so the
source list exists in exactly one place.

The driver: build each layer, merge onto `GridSpec`, validate the result against the
expected variable set and shapes, then write the pair (C§6). Regridding EMODnet's ~115 m
grid onto the 2 km grid is an aggregation, not an interpolation — mean and min per target
cell — and is the one place where `rioxarray`/`rasterio` are needed.

### C§5.1 Why not the alternatives

**A linear script** is genuinely simpler for something run once a year, and was seriously
considered. It was rejected because the probe job would duplicate the source list and C1
would either copy the manifest writer or retrofit this seam anyway — paying the same cost
later, with a migration on top.

**A config-driven engine** fits this project's "coefficients are data" instinct, but the
per-layer statistics genuinely differ — mean over polygon, monthly p95 over hourly, mean
and min for depth — and encoding that in YAML produces a worse-documented version of
Python. Speculative generality.

---

## C§6 Atomicity, and what it can actually mean

**§6.3 asks for the artifact and manifest to be "written atomically as a pair". No
filesystem provides that.** `os.replace` is atomic per file; there is no two-file
equivalent, and on Windows there is no directory-swap trick either. Implemented literally,
the requirement cannot be met; implemented loosely, it silently is not met.

The workable equivalent, and what this design specifies:

1. Build everything in a temp directory **on the same filesystem** as the target — a
   rename across filesystems is a copy, and not atomic.
2. Artifact → `forcing.nc.tmp`, fsync.
3. sha256 of the artifact.
4. Manifest, carrying that sha → `manifest.json.tmp`, fsync.
5. `os.replace` the artifact.
6. `os.replace` the manifest — **last**.

Between 5 and 6 the *old* manifest's sha no longer matches the artifact on disk, so a
reader validating the checksum **refuses** rather than reading new data under old
provenance. The exposure is one rename, and the failure is loud rather than silent — which
is the behaviour §7 row 1 already specifies, now reached by a mechanism that exists.

Manifest-last rather than artifact-last is deliberate: a new manifest over an old artifact
would look internally consistent while attesting to data that is not there.

### C§6.1 Failure modes

| Condition | Behaviour |
|---|---|
| Any layer fails | **The whole refresh fails.** No partial artifact is written. |
| Refresh interrupted before step 5 | Nothing live is touched; previous pair stays valid. |
| Interrupted between 5 and 6 | sha mismatch on next read → refuse, fall back to `PlaceholderForcing` with a banner (§7). Re-running the refresh repairs it. |
| `artifact_sha256` mismatch | Refuse and say why. Never read the artifact anyway. |
| Unrecognised `artifact_schema_version` | Refuse, fall back, say why (§7 row 6). |
| Insufficient free disk | Refuse **before** starting, naming the requirement. |
| Layer built but not yet deposited | Manifest records `archive.status: pending` with a `source_url`. Valid, loadable, and **visibly incomplete** (§7). Not an error — it is the state of every layer of a first refresh. |
| A layer marked `forbidden` that is in fact redistributable | Not detectable by the validator, and the reason `pending` exists: without it, clearing the check by mis-marking a layer is the path of least resistance. |

A single layer failing takes the whole refresh with it because a missing variable quietly
defaulting is the unmarked-provenance hazard A0 spent two commits removing — and it would
be worse here, because the manifest would attest to a completeness the artifact lacks.

**Free-disk check before starting** is not defensive padding: the wave stream peaks around
1 GB of working space and the machine this is developed on has ~38 GB free. Failing at 80%
through a 26 GB transfer is the expensive failure.

---

## C§7 Fixture and provenance test

The fixture is **synthetic-valued but structurally real**: a 3 × 3-cell, 2-year artifact
carrying every variable at its correct shape, written by the *same* writer and manifest
code as a production refresh, with `synthetic: true` set in the manifest.

Its layers carry **`archive.status: pending`**, not an invented DOI. That is the state a
real first refresh produces, so the fixture exercises the path production actually takes;
a fixture carrying a fake DOI would test a state package C never reaches.

Synthetic rather than a real subset, for two reasons. Committing real Copernicus values to
a public repository raises a redistribution question that C should not answer implicitly;
and regenerating a real fixture would need network and credentials, which makes it the kind
of artifact that rots. Synthetic values dodge both while still exercising every schema rule.

Committed at `tests/fixtures/data/forcing.nc` and `manifest.json`. `.gitignore` currently
excludes `*.nc` and `*.zarr/`, so this needs the exception §6.3 anticipated:

```gitignore
!tests/fixtures/data/*.nc
```

Tests:

- The committed manifest loads against the Pydantic model — this **is** §9's provenance
  test, and it fails on any layer without one of the three archive states of C§4.1.
- The committed artifact's sha256 matches its manifest.
- A layer with neither DOI nor marker is rejected (negative test, constructed in-memory).
- A mismatched sha is refused.
- `refresh/` is not imported by any core module.

---

## C§8 Runbook and probe job

### C§8.1 The runbook

`docs/runbooks/annual-refresh.md`, written for someone who is not its author — §4.1's
deliverable, and the one whose done-when is that **somebody else follows it end to end**.

It must carry: prerequisites, including that the Copernicus credential is **institutional,
never personal**, and where it is held; environment setup; the command; **expected transfer
volume** — ~170 MB of forcing on disk, but **~30 GB crossing the wire**: ~0.59 GB of
monthly fields, ~3.6 GB of daily `zsd` (C§3.4), ~25.8 GB of hourly waves — **and runtime**; free-disk requirement; what success
looks like; how to verify (provenance test plus checksum); how to deposit artifact and
manifest to Zenodo and record the DOI back into the committed manifest; what each failure
mode in C§6.1 means and what to do about it; and who to contact.

It must also state plainly that **the deposited manifest and the committed manifest differ**.
The DOI exists only after the deposit, so the sequence is: build (every layer
`archive.status: pending`) → deposit artifact and manifest → record the returned DOI back
into the committed manifest, flipping those layers to `deposited`. The committed manifest is
authoritative for provenance; the deposited copy is a snapshot of the moment before the DOI
existed. `artifact_sha256` is unaffected — it covers the artifact, which does not change.

The volumes and timings are not decoration. A runbook that does not say "this will move 26
GB and take hours" is one somebody abandons halfway, which is the key-person risk §4.1 and
spec §14 exist to mitigate.

### C§8.2 The probe job

`.github/workflows/source-probe.yml` — **a separate workflow from `ci.yml`**, scheduled
monthly plus `workflow_dispatch`, running `refresh_layers.py --probe`.

`probe()` asks only whether each source still exists and answers: catalogue metadata calls,
no bulk transfer. It needs the Copernicus credential as a repository secret, which the
runbook records as institutional.

Separate from `ci.yml` so that a dead upstream source turns that job red and **blocks no
pull request** — §4.1's "may fail loudly without blocking anything". Gating merges on the
continued existence of a third-party service would make every PR hostage to Copernicus.

---

## C§9 What package C does not do

- **No Zenodo deposit is performed.** Implemented and documented; a human runs it.
- **No `GriddedForcing`, no artifact reading, no aggregation over polygons** — package D.
- **No human-use or exclusion vectors** — package C1, which reuses C§4's manifest models
  and C§6's writer for a GeoPackage.
- **No `significant_wave_max_m`** — deferred as a genuine tail statistic; the field is
  defined in §6.1 and added to `SiteConditions` by D, consumed by no verdict.
- **No `methods.yaml` wave-limit re-validation** — owned by D per §8.1.
- **No HELCOM integration** — dropped as redundant (C§1).

---

## C§10 Done-when, against §8

§8's row reads: *"Provenance test passes against the committed fixture; runbook followed
end-to-end by someone else."* Both stand. Expanded, so the row is checkable:

1. `refresh_layers.py` builds the artifact and manifest for a named year range.
2. The committed fixture loads and its manifest validates — §9's provenance test.
3. A layer with no valid archive state is rejected, proven by a negative test (C§4.1).
4. Artifact and manifest are checksum-linked, and a torn pair is refused.
5. An interrupted refresh leaves the previous pair valid, proven by a test.
6. `--probe` reports per-layer reachability and is wired to a scheduled workflow separate
   from `ci.yml`.
7. The runbook exists, carries volumes, runtimes and the institutional-credential rule, and
   **has been followed end to end by someone who did not write it**. This one cannot be
   discharged by the implementer, and it is the row most likely to be quietly skipped.
8. No core module imports `refresh/`.
9. **The deposit path is exercised.** The deposit function runs against a stub returning a
   synthetic DOI, and a test proves that recording it flips the affected layers from
   `pending` to `deposited` and that the manifest still validates. Without this clause the
   deliverable discharging the open-data half of the durability commitment has no check that
   can fail — which was true of this design until review caught it.
10. **A `pending` manifest validates and a mis-stated one does not.** Positive test: every
    layer `pending` with a `source_url` loads. Negative tests: `pending` without a
    `source_url`, and a layer with no archive state at all, both fail at load.
11. **The `valid` field is the intersection** of contributing layer coverage, proven by a
    test with two deliberately disagreeing masks (C§3.5).

---

## C§11 Amendments this design requires

To be made when this design is accepted, not silently assumed:

- **§6.1** — remove HELCOM from the nutrient row, or record why it is listed and unused.
  Record that `depth_m` resolves to `depth_mean_m` and `depth_min_m`.
- **§6.2** — record the shipped extent (53.5–60.0 N, 9.5–27.0 E) and that it excludes the
  Gulfs of Bothnia and Finland.
- **§6.3** — replace "written atomically as a pair" with the checksum-and-manifest-last
  mechanism of C§6, which is what a filesystem can deliver.
- **§7** — a display row for an artifact whose layers are `archive.status: pending`:
  usable, but it says so, the way `surface_par` does.
- **§8** — C1's row should name the manifest models it reuses.
- **§8.1** — traceability rows for the extent choice, the wave sub-baseline, the `absent`
  block, the `pending` archive state, the `valid` field, and the daily-`zsd` requirement.
  The "§4.1 — Zenodo archive" row's *Checked by* cell must widen beyond the fixture
  provenance test to name C§10 clause 9, since that row currently claims a check that
  cannot fail.
- **Package D gains two items it does not have.** (1) The NaN-depth defect of C§3.5:
  `select_method`'s `pool = workable or candidates` plus `assess_physical`'s
  `not (min <= nan <= max)` turn missing depth into a confident `UNSUITABLE`. D must read
  the `valid` field and return `UNKNOWN`, never a verdict, for an invalid cell. (2) The
  **temperature mapping**: the artifact carries one `temp_c`, while `SiteConditions` needs
  `mean_temp_c`, `summer_temp_c` and `winter_temp_c`. D owns the derivation and must name
  the month definitions it uses; §6.1 should record it, exactly as C§11 already asks it to
  record `depth_m` resolving to `depth_mean_m`/`depth_min_m`.
- **`pyproject.toml` and `.github/workflows/ci.yml`** — neither is touched by this design
  and both must be. The `spatial` extra carries no netCDF engine, so **nothing in the repo
  can currently read the fixture C commits**, and `copernicusmarine` appears in no extra.
  C§10 clause 8 (no core module imports `refresh/`) is only meaningful in an install
  *without* `spatial`, while C§7's fixture tests need one *with* it — two install states,
  so a second CI job or skip markers.
- **§6.2's year-boundary rule makes the effective baseline nine years, not ten.** A wrapping
  window opened in year Y takes January from Y+1, and blocks when Y+1 is absent, so 2025
  cannot open a *Saccharina* Oct–Jun window in a 2016–2025 artifact. C§1's "last ten full
  calendar years" is correct about what the artifact *carries* and misleading about what is
  *usable* for wrapping windows. Either state it, or carry 2016–2026 once 2026 completes.

## C§12 Risks

- **The 26 GB wave stream is the largest single cost in the package**, and it is the part
  most likely to be cut under time pressure. If it is cut, `significant_wave_m` stays a
  placeholder and `assess_physical`'s exposure test stays unsourced — which must then be
  displayed, not assumed.
- **EMODnet Bathymetry is a second integration with a different service model** from
  Copernicus and no equivalent Python client. Its fetch and its `probe()` are the least
  specified part of this design and the most likely to need rework once attempted.
- **The runbook's done-when depends on a second person.** Nothing in the implementation can
  discharge it, and it is the deliverable that most directly addresses spec §14's
  key-person risk.
- **The wave layer's dataset is still unnamed.** C commits to hourly `VHM0`, but package B
  only read catalogue metadata for `BALTICSEA_MULTIYEAR_WAV_003_015`. B established that
  PHY and BGC involve no `_myint_` interim product, so their provenance is uniform; **nobody
  has established that for the hourly dataset over 2023–2025**, the most recent years, where
  an interim split is most likely. A layer split across `_my_` and `_myint_` cannot be
  described by one `LayerProvenance` with one `dataset_id` and one `version` — so this is a
  schema question, not only a sourcing one, and it should be settled before implementation.
- **`baselines` cannot express a layer with no years.** `depth_mean_m` and `depth_min_m` are
  static. Their entry is either absent or an empty list, and this design does not say which.
  Pick one in the plan.
- **`artifact_schema_version` starts at 1 with no negotiation mechanism.** If D and C
  disagree about the shape, the failure is a refusal to load — loud, but total. That is the
  intended trade, recorded so it is not a surprise.
