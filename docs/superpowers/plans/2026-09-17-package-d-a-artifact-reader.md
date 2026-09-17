# Package D-a — Artifact Reader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the tool able to read a real forcing artifact — answering a polygon-and-year query, deciding coverage, and representing a site whose conditions are unknown — without breaking the placeholder it still runs on.

**Architecture:** A vocabulary of plain records in `forcing.py` (importable by the core and the app), a single xarray-bound reader in `gridded.py`, and a widened `ForcingSource` protocol both implementations satisfy. Everything is proven against the committed fixture package C-a ships; no network, no credential, no real artifact.

**Tech Stack:** Python 3.11+, xarray + h5netcdf (the `spatial` extra), numpy, Shiny for Python, pytest.

**Spec:** `docs/superpowers/specs/2026-09-17-package-d-a-artifact-reader-design.md`
(binding authority above it: `docs/superpowers/specs/2026-09-13-dst-data-layer-design.md`)

## Global Constraints

- **`gridded.py` is the only module OUTSIDE `refresh/` that imports xarray.** Five `refresh/` modules already import it, one at runtime (`merge.py:85`) — that is build-time tooling and is walled off by `test_no_core_module_imports_refresh`. A `src/`-wide assertion would fail the day it is written.
- **The model core and the app must work with no `spatial` extra.** CI's `[app,dev]` job is that install. A module-scope `import xarray` in anything the core or `app/tests` imports turns it red at collection, because `-m` deselects *after* collection.
- **Coverage is read from the `valid` field, never inferred from NaN.** The committed fixture's invalid cell (`valid[0,0] = False`) holds *finite* random values, so a NaN-inferring reader returns conditions for it.
- **Decide coverage before constructing `SiteConditions`.** It raises on any non-finite field (`numbers.Real`, fixed in `3f0bc35`), so building first turns a real land cell into a `ValueError` where §7 requires a visible block.
- **Tier C is a floor, not a ceiling.** `contraindication()`'s salinity branch never gates on region; a site below a species' floor is tier D whatever its region. Never skip or downgrade it for `region=None`.
- `pytest` `addopts` is `-m 'not engines and not e2e and not spatial'`. Any command running a `spatial`-marked module needs `-m spatial` or it reports success having run nothing.
- ruff: `line-length = 100`, `target-version = "py311"`. Repo is ruff-clean and stays so.
- **Test discrimination standard:** every negative test asserts `match=` on a fragment unique to its rule; each guard gets a DELETE proof that goes red *for the right reason*; record actual pytest output, never the word "verified"; commit implementation before running mutation proofs.
- Never `git add` anything under `.superpowers/`.

## Shipped interfaces this plan consumes — read, not remembered

| Thing | Fact |
|---|---|
| `SiteConditions` | frozen dataclass; fields `region, salinity_psu, mean_temp_c, summer_temp_c, winter_temp_c, surface_par, din_umol_l, dip_umol_l, depth_m, significant_wave_m, light_attenuation_k=0.4, cultivation_depth_m=1.5`; `__post_init__` raises on any non-finite `numbers.Real` |
| `SiteContext` (`contracts.py`) | `region: str`, `conditions: SiteConditions`, `geometry_wkt: str = ""`, `label`, `confidence`, `activities`, `protection`; `from_region(region, *, label, forcing)` at line 51 |
| `ForcingSource` | `conditions_for(region)`, `daily_forcing(site, window)`; `DEFAULT_FORCING = PlaceholderForcing()` at `forcing.py:555` |
| Callers to migrate | `contracts.py:51`, `growth.py:102`, `growth.py:198`, `api.py:72`, `api.py:105` |
| `load_pair(dir)` | returns `(Manifest, Path)` — does **not** open the NetCDF |
| Committed fixture | `tests/fixtures/data/`; 3×3 grid; `year=[2024, 2025]`; `month` 1–12; all float32; `valid[0,0]=False` with finite values there; `significant_wave_m` has **no** year dim |
| `calibration_for(region)` | falls back to the `"default"` entry → tier C with the region named; **safe with `None`** |
| `contraindication(species, site)` | returns `Calibration(tier=Tier.D, ...)` when `salinity_psu < floor`; `is_reportable` is False for tier D |

---

### Task 1: The vocabulary

**Files:**
- Modify: `src/seagarden_dst/forcing.py` (add beside `SiteCoordinate`)
- Test: `tests/test_site_reading.py` (create)

**Interfaces:**
- Consumes: `SiteConditions` (existing)
- Produces: `Coverage`, `Aggregation`, `SiteQuery`, `SiteReading`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_site_reading.py
"""The vocabulary D-a adds to `forcing.py`.

These types are read by the model core and by the app, so they must stay pure
pydantic/stdlib/numpy — no xarray, no shapely. `tests/test_gridded_isolation.py`
asserts that; these tests are about behaviour.
"""

import pytest

from seagarden_dst.forcing import (
    Aggregation,
    Coverage,
    PLACEHOLDER_SITES,
    SiteQuery,
    SiteReading,
)


def test_a_valid_reading_carries_its_conditions():
    reading = SiteReading(
        conditions=PLACEHOLDER_SITES["LT-coastal"],
        coverage=Coverage.VALID,
        year=2024,
        aggregation=Aggregation.CONTAINING_CELL,
    )
    assert reading.conditions is not None
    assert reading.coverage is Coverage.VALID


def test_a_blocked_reading_carries_the_reason_and_the_distance():
    """A bare `SiteConditions | None` says nothing about WHY, and §6.2 requires the
    distance to the nearest valid cell to be surfaced. That is the whole reason this
    record exists rather than an Optional."""
    reading = SiteReading(
        conditions=None,
        coverage=Coverage.CELL_INVALID,
        year=2024,
        aggregation=Aggregation.CONTAINING_CELL,
        nearest_valid_km=1.12,
    )
    assert reading.conditions is None
    assert reading.coverage is Coverage.CELL_INVALID
    assert reading.nearest_valid_km == pytest.approx(1.12)


def test_a_reading_says_whether_it_came_from_an_artifact():
    """§7's first row requires a banner naming what the tool is running on. The banner
    reads this, rather than the app guessing from which object it holds."""
    placeholder = SiteReading(
        conditions=PLACEHOLDER_SITES["LT-coastal"], coverage=Coverage.VALID,
        year=2024, aggregation=Aggregation.CONTAINING_CELL,
    )
    assert placeholder.from_artifact is False


def test_the_three_coverage_states_are_distinct():
    assert len({Coverage.VALID, Coverage.CELL_INVALID, Coverage.YEAR_ABSENT}) == 3


def test_the_provisional_aggregation_is_nameable():
    """D-b replaces the method, not the plumbing. A result computed the provisional way
    has to say so, the way a calibration tier says what a number rests on."""
    assert Aggregation.UNWEIGHTED_MEAN.value == "unweighted_mean"
    assert Aggregation.SALINITY_WEIGHTED.value == "salinity_weighted"


def test_a_query_carries_geometry_as_wkt_not_a_shapely_object():
    """`shapely` is in the `spatial` extra. A shapely geometry here would drag that
    extra into the model core, which is the failure this repository shipped on
    2026-09-17 with a conda-only import at module scope."""
    query = SiteQuery(geometry_wkt="POINT (21.13 55.67)", year=2024)
    assert isinstance(query.geometry_wkt, str)
    assert query.region is None


def test_a_query_may_name_a_region_instead_of_a_geometry():
    """The placeholder path has a region and no position."""
    query = SiteQuery(geometry_wkt="", year=2024, region="LT-coastal")
    assert query.region == "LT-coastal"
```

- [ ] **Step 2: Run to verify it fails**

Run: `micromamba run -n shiny python -m pytest tests/test_site_reading.py -v`
Expected: FAIL — `ImportError: cannot import name 'Aggregation'`

- [ ] **Step 3: Add the vocabulary to `forcing.py`**

Place it immediately after `SiteCoordinate`, before `SITE_COORDINATES`.

```python
class Coverage(StrEnum):
    """Whether the artifact has data for a query, and if not, why not (§6.2).

    Read from the artifact's `valid` field, NEVER inferred from NaN. C§3.5 added that
    field precisely because inferring validity from NaN is unreliable, and the committed
    fixture proves it: its invalid cell holds finite values, so a NaN-inferring reader
    would return conditions for a cell the mask excludes.
    """

    VALID = "valid"
    CELL_INVALID = "cell_invalid"   # blocks; the distance to the nearest valid cell is reported
    YEAR_ABSENT = "year_absent"     # blocks; never substitutes another year


class Aggregation(StrEnum):
    """How a reading's numbers were produced from the cells under the polygon.

    Recorded on the reading so package D-b replaces a NAMED method rather than silently
    changing what every multi-cell result meant.
    """

    CONTAINING_CELL = "containing_cell"      # farm scale - the normal case (§6.2)
    UNWEIGHTED_MEAN = "unweighted_mean"      # provisional, multi-cell - package D-a
    SALINITY_WEIGHTED = "salinity_weighted"  # the Maar et al. port - package D-b


@dataclass(frozen=True)
class SiteQuery:
    """Where and when to read.

    `geometry_wkt` is a WKT string, not a `shapely` geometry: shapely lives in the
    `spatial` extra and this type is read by the model core. An empty string means
    "use the region's coordinate", which is the placeholder path.
    """

    geometry_wkt: str
    year: int
    region: str | None = None


@dataclass(frozen=True)
class SiteReading:
    """Conditions, and everything a caller needs to know about how far to trust them.

    Deliberately not `SiteConditions | None`. A bare `None` says nothing about why it is
    None or how far away data is, and §6.2 requires the distance to be surfaced — the
    same reasoning that makes `SiteCoordinate` refuse to be unpacked.
    """

    conditions: SiteConditions | None
    coverage: Coverage
    year: int
    aggregation: Aggregation
    #: Great-circle distance to the nearest valid cell, km. Set when coverage blocks.
    nearest_valid_km: float | None = None
    #: False for the placeholder. §7's banner reads this rather than guessing.
    from_artifact: bool = False
    #: Age of the artifact in months, for §7's 18-month staleness note.
    stale_months: int | None = None

    @property
    def is_assessable(self) -> bool:
        return self.conditions is not None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `micromamba run -n shiny python -m pytest tests/test_site_reading.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add src/seagarden_dst/forcing.py tests/test_site_reading.py
git commit -m "feat(forcing): add the D-a reading vocabulary"
```

---

### Task 2: The widened protocol, and the placeholder that satisfies it

**Files:**
- Modify: `src/seagarden_dst/forcing.py` (`ForcingSource`, `PlaceholderForcing`, `daily_forcing`)
- Test: `tests/test_site_reading.py` (extend)

**Interfaces:**
- Consumes: Task 1's vocabulary
- Produces: `ForcingSource.reading_at(query) -> SiteReading`; `ForcingSource.daily_forcing(site, window, year)`; `PlaceholderForcing` satisfying both

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_site_reading.py`:

```python
def test_the_placeholder_satisfies_the_widened_protocol():
    from seagarden_dst.forcing import ForcingSource, PlaceholderForcing

    assert isinstance(PlaceholderForcing(), ForcingSource)


def test_the_placeholder_answers_a_region_query():
    from seagarden_dst.forcing import PlaceholderForcing

    reading = PlaceholderForcing().reading_at(
        SiteQuery(geometry_wkt="", year=2024, region="LT-coastal")
    )
    assert reading.coverage is Coverage.VALID
    assert reading.aggregation is Aggregation.CONTAINING_CELL
    assert reading.from_artifact is False
    assert reading.conditions is PLACEHOLDER_SITES["LT-coastal"]


def test_the_placeholder_never_blocks():
    """It has no artifact, so it has no coverage to be missing. Its conditions are
    invented and say so through the calibration tiers, not through Coverage."""
    from seagarden_dst.forcing import PlaceholderForcing

    for region in PLACEHOLDER_SITES:
        reading = PlaceholderForcing().reading_at(
            SiteQuery(geometry_wkt="", year=2024, region=region)
        )
        assert reading.is_assessable


def test_an_unknown_region_still_raises_from_the_placeholder():
    """`conditions_for` raised KeyError for an unknown region and callers rely on it.
    Widening the protocol must not turn that into a silent blocked reading, which would
    hide a typo as a coverage failure."""
    from seagarden_dst.forcing import PlaceholderForcing

    with pytest.raises(KeyError, match="No placeholder conditions"):
        PlaceholderForcing().reading_at(
            SiteQuery(geometry_wkt="", year=2024, region="XX-nowhere")
        )


def test_daily_forcing_takes_a_year():
    """§6.2: the artifact carries one monthly field per year, so the series depends on
    which year is asked for. The placeholder ignores it — it has one invented year —
    but the signature has to carry it or `GriddedForcing` cannot satisfy the protocol."""
    from seagarden_dst.forcing import PlaceholderForcing

    days, par, temp, din = PlaceholderForcing().daily_forcing(
        PLACEHOLDER_SITES["LT-coastal"], (4, 9), 2024
    )
    assert len(days) == len(par) == len(temp) == len(din)
```

- [ ] **Step 2: Run to verify it fails**

Run: `micromamba run -n shiny python -m pytest tests/test_site_reading.py -v`
Expected: FAIL — `AttributeError: 'PlaceholderForcing' object has no attribute 'reading_at'`

- [ ] **Step 3: Widen the protocol and the placeholder**

Replace the `ForcingSource` protocol and `PlaceholderForcing` with:

```python
@runtime_checkable
class ForcingSource(Protocol):
    """Where site conditions and seasonal forcing come from.

    Widened by package D-a. `conditions_for(region)` became `reading_at(query)` because
    §7 requires a polygon outside every calibration domain to yield `region=None`, which
    the caller cannot know before the lookup; and `daily_forcing` gained a year because
    §6.2's measurement refutes the climatology — collapsing 2023-2025 into one costs
    -57% to +179% against the +17.4% monthly resolution buys.
    """

    def reading_at(self, query: SiteQuery) -> SiteReading: ...

    def daily_forcing(
        self, site: SiteConditions, window: tuple[int, int], year: int
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]: ...


class PlaceholderForcing:
    """The scaffold's invented conditions. Not measurements - see PLACEHOLDER_SITES."""

    def reading_at(self, query: SiteQuery) -> SiteReading:
        region = query.region
        if region is None or region not in PLACEHOLDER_SITES:
            raise KeyError(f"No placeholder conditions for region {region!r}")
        # Never blocks: there is no artifact, so there is no coverage to be missing.
        # That these numbers are invented is carried by the calibration tiers, not here.
        return SiteReading(
            conditions=PLACEHOLDER_SITES[region],
            coverage=Coverage.VALID,
            year=query.year,
            aggregation=Aggregation.CONTAINING_CELL,
            from_artifact=False,
        )

    def daily_forcing(
        self, site: SiteConditions, window: tuple[int, int], year: int
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        # `year` is ignored: the placeholder has one invented seasonal cycle, not one
        # per year. The parameter exists so GriddedForcing can satisfy the protocol.
        return daily_forcing(site, window)
```

Leave the module-level `daily_forcing(site, window)` function unchanged — it is the sinusoid, and `GriddedForcing` replaces it with monthly fields rather than extending it.

- [ ] **Step 4: Run tests to verify they pass**

Run: `micromamba run -n shiny python -m pytest tests/test_site_reading.py -v`
Expected: 13 passed

- [ ] **Step 5: Commit**

```bash
git add src/seagarden_dst/forcing.py tests/test_site_reading.py
git commit -m "feat(forcing): widen ForcingSource to reading_at and a year-aware daily_forcing"
```

- [ ] **Step 6: DELETE proof — the unknown-region guard**

Remove the `if region is None or region not in PLACEHOLDER_SITES: raise` from `reading_at`. `test_an_unknown_region_still_raises_from_the_placeholder` must go red with `DID NOT RAISE` — not with a `KeyError` from the dict lookup below, which would mean the test cannot tell the guard from the dict. Record the actual output, restore, re-run green.

---

### Task 3: Migrate the callers, and add the unassessable path

**Files:**
- Modify: `src/seagarden_dst/contracts.py` (`SiteContext`, `from_region` at line 51)
- Modify: `src/seagarden_dst/api.py` (lines 72, 105; `assess_site`)
- Modify: `src/seagarden_dst/growth.py` (lines 102, 198)
- Modify: `tests/test_forcing_source.py`, `tests/test_cultivation_window.py`
- Test: `tests/test_unassessable.py` (create)

**Interfaces:**
- Consumes: Task 2's protocol
- Produces: `SiteContext.conditions: SiteConditions | None`, `SiteContext.region: str | None`, `SiteContext.from_reading(reading, *, label)`, `assess_site` returning an `unassessable` result

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_unassessable.py
"""§7's mechanism: a site whose conditions are unknown must block, not score.

"There is today no representation for a site whose conditions are unknown.
`SiteContext.conditions` becomes `SiteConditions | None` and `assess_site` returns early
with an explicit `unassessable` flag; the UI reads that flag to distinguish 'unsuitable'
from 'unassessed'." — data-layer design §7, which assigns this to package D.
"""

import pytest

from seagarden_dst import SiteContext
from seagarden_dst.api import assess_site
from seagarden_dst.forcing import Aggregation, Coverage, SiteReading


def _blocked(coverage=Coverage.CELL_INVALID, km=1.12):
    return SiteReading(
        conditions=None, coverage=coverage, year=2024,
        aggregation=Aggregation.CONTAINING_CELL, nearest_valid_km=km,
        from_artifact=True,
    )


def test_a_context_can_hold_no_conditions():
    context = SiteContext.from_reading(_blocked(), label="Off-grid polygon")
    assert context.conditions is None


def test_an_unassessable_site_returns_unassessable_and_never_a_verdict():
    """The failure this exists to prevent is a definitive negative manufactured from
    missing data — an UNSUITABLE that means 'we did not look'."""
    context = SiteContext.from_reading(_blocked(), label="Off-grid polygon")
    result = assess_site(context)
    assert result.unassessable is True
    assert result.ranked == []


def test_the_reason_and_distance_survive_into_the_result():
    """§6.2 requires the distance to the nearest valid cell to be reported, and §7 makes
    the block visible. A flag with no reason cannot be displayed usefully."""
    context = SiteContext.from_reading(_blocked(km=0.75), label="Off-grid polygon")
    result = assess_site(context)
    assert result.coverage is Coverage.CELL_INVALID
    assert result.nearest_valid_km == pytest.approx(0.75)


def test_a_missing_year_blocks_the_same_way():
    context = SiteContext.from_reading(
        _blocked(coverage=Coverage.YEAR_ABSENT, km=None), label="2019 query"
    )
    result = assess_site(context)
    assert result.unassessable is True
    assert result.coverage is Coverage.YEAR_ABSENT


def test_an_assessable_site_is_not_flagged():
    """The flag must discriminate, not be always-on."""
    context = SiteContext.from_region("LT-coastal")
    result = assess_site(context)
    assert result.unassessable is False
    assert result.ranked
```

- [ ] **Step 2: Run to verify it fails**

Run: `micromamba run -n shiny python -m pytest tests/test_unassessable.py -v`
Expected: FAIL — `AttributeError: type object 'SiteContext' has no attribute 'from_reading'`

- [ ] **Step 3: Migrate `SiteContext`**

In `contracts.py`: change `region: str` to `region: str | None` and `conditions: SiteConditions` to `conditions: SiteConditions | None`, extend the `conditions` docstring line to say a `None` means the data layer could not answer, and add beside `from_region`:

```python
    @classmethod
    def from_reading(
        cls, reading: SiteReading, *, label: str = "", geometry_wkt: str = ""
    ) -> SiteContext:
        """Build a context from a `SiteReading`, blocked or not.

        `from_region` remains for the placeholder path, where a region is all there is.
        This is the path package D's reader uses, and it is the one that can carry a
        context with no conditions — §7's mechanism for a site that must not score.
        """
        return cls(
            region=reading.conditions.region if reading.conditions else None,
            conditions=reading.conditions,
            label=label,
            geometry_wkt=geometry_wkt,
            confidence="low",
            coverage=reading.coverage,
            nearest_valid_km=reading.nearest_valid_km,
        )
```

Add `coverage` and `nearest_valid_km` fields to `SiteContext` with defaults (`Coverage.VALID`, `None`) so `from_region` keeps working unchanged.

Update `from_region` to build through `forcing.reading_at(SiteQuery(geometry_wkt="", year=..., region=region))`. Give `from_region` a `year: int = 2024` keyword so it can form the query; note in its docstring that the placeholder ignores the year.

- [ ] **Step 4: Add the early return to `assess_site`**

In `api.py`, as the first statement of `assess_site`'s body:

```python
    # §7: a site whose conditions are unknown must block rather than score. Returning a
    # verdict here would be a definitive negative manufactured from missing data, which
    # is the failure the whole unassessable mechanism exists to prevent.
    if context.conditions is None:
        return SiteAssessment(
            context=context,
            ranked=[],
            unassessable=True,
            coverage=context.coverage,
            nearest_valid_km=context.nearest_valid_km,
        )
```

Add `unassessable: bool = False`, `coverage: Coverage = Coverage.VALID` and `nearest_valid_km: float | None = None` to `SiteAssessment` (`contracts.py:105`), whose existing fields are `context`, `ranked`, `best`, `excluded`, `caveats`, `pressure`, `pressure_note`. Append the three; do not reorder the existing ones.

- [ ] **Step 5: Migrate the remaining callers**

`growth.py:102` and `growth.py:198`, and `api.py:72`, take `forcing: ForcingSource` and call `daily_forcing(site, window)`. Add the year. Where the caller has no year, thread one from the context — `SiteContext` gains no year field; pass `reading.year` where available, else the module default `2024`, and say so in a comment rather than inventing a field.

Then fix the tests that call the old surface: `tests/test_forcing_source.py` (19 occurrences) and `tests/test_cultivation_window.py` (10). These are mechanical — add the `year` argument, and replace `conditions_for(region)` with `reading_at(SiteQuery(geometry_wkt="", year=2024, region=region)).conditions`.

- [ ] **Step 6: Run the whole suite**

```bash
micromamba run -n shiny python -m pytest -q
micromamba run -n shiny ruff check .
```
Expected: all green. The pre-existing count was 239 before this branch; you will have added tests and changed none of the assertions, so the count rises and nothing falls.

- [ ] **Step 7: Commit**

```bash
git add src/seagarden_dst/contracts.py src/seagarden_dst/api.py src/seagarden_dst/growth.py tests/
git commit -m "feat(core): SiteContext may hold no conditions, and assess_site blocks when it does"
```

- [ ] **Step 8: DELETE proof — the early return**

Remove the `if context.conditions is None:` block from `assess_site`. `test_an_unassessable_site_returns_unassessable_and_never_a_verdict` must go red — and record HOW. If it fails with an `AttributeError` from something reaching into `None`, say so: that is red for a crash, not for a verdict, and it means the test proves less than it claims. Restore, re-run green.

---

### Task 3b: Tier C is a floor, not a ceiling

**Files:**
- Test: `tests/test_unlocatable_contraindication.py` (create)
- Modify: nothing expected — see Step 3

**Interfaces:**
- Consumes: `SiteContext.from_reading` (Task 3), `growth.contraindication`, `calibration.Tier`
- Produces: nothing; this task exists to pin behaviour the reader must not "repair"

**Why this is its own task.** §7 says a polygon outside every calibration domain gets
`region=None` and every quantity forced to tier C. §3.2's contraindication rule says a
site below a species' salinity floor is tier D. For a 2 psu sugar-kelp polygon with
`region=None` these disagree, and the data-layer design §8.1 settled it: *"`contraindication()`
wins — a salinity finding does not stop applying because the polygon is unlocatable — and
D's done-when carries the test."* This is that test. Without it, an implementer who writes
the outside-every-domain case as "everything comes back tier C" sees it fail against
correct code, and the natural repair — skipping `contraindication()` when `region is None` —
deletes the OLAMUR finding for exactly the unlocated polygons where the salinity evidence
still applies. That is the one verdict this tool exists to surface.

- [ ] **Step 1: Write the test**

```python
# tests/test_unlocatable_contraindication.py
"""A site can be unlocatable and still be contraindicated.

§7 forces tier C outside every calibration domain; §3.2 forces tier D below a species'
salinity floor. §8.1 of the data-layer design resolves the overlap in favour of
contraindication. Tier C is the floor a result cannot rise above, not a ceiling that
stops it falling further.
"""

import dataclasses

from seagarden_dst.calibration import Tier
from seagarden_dst.forcing import PLACEHOLDER_SITES
from seagarden_dst.growth import contraindication
from seagarden_dst.params import default_parameters


def _sugar_kelp():
    # `default_parameters()` is the loader; `load_parameters(root)` is its rooted form.
    # There is no `load_params`.
    return default_parameters().species["saccharina_latissima"]


def test_a_below_floor_site_with_no_region_is_still_tier_d():
    """The canonical case: OLAMUR found outright cultivation failure at 5.5-6.5 psu
    while the salinity scaling returns a small positive yield. Losing the region must
    not lose the finding."""
    site = dataclasses.replace(
        PLACEHOLDER_SITES["LT-lagoon"], region=None, salinity_psu=2.0
    )
    calibration = contraindication(_sugar_kelp(), site)
    assert calibration is not None
    assert calibration.tier is Tier.D


def test_the_number_is_suppressed_in_favour_of_the_note():
    site = dataclasses.replace(
        PLACEHOLDER_SITES["LT-lagoon"], region=None, salinity_psu=2.0
    )
    calibration = contraindication(_sugar_kelp(), site)
    assert calibration.is_reportable is False
    assert calibration.caveat()


def test_an_above_floor_site_with_no_region_is_not_contraindicated():
    """The discriminating half: if this also returned tier D the first test would pass
    for a reason that has nothing to do with salinity."""
    site = dataclasses.replace(
        PLACEHOLDER_SITES["LT-coastal"], region=None, salinity_psu=25.0
    )
    assert contraindication(_sugar_kelp(), site) is None
```

- [ ] **Step 2: Run it**

Run: `micromamba run -n shiny python -m pytest tests/test_unlocatable_contraindication.py -v`
Expected: **PASS, with no production change.** `contraindication()`'s salinity branch
resolves the floor through `species.salinity_floor()` and never consults `site.region`, so
the behaviour is already correct and this test pins it.

**If it fails, stop and report.** A failure means either `SiteConditions` rejects
`region=None` (in which case Task 3's migration is incomplete and must come first), or
the salinity branch does gate on region after all (in which case the spec's §8.1 ruling
and the code disagree, which is a finding for your human partner and not something to fix
by editing the test).

- [ ] **Step 3: Commit**

```bash
git add tests/test_unlocatable_contraindication.py
git commit -m "test: an unlocatable site below the salinity floor is still tier D"
```

- [ ] **Step 4: DELETE proof**

In `growth.contraindication`, guard the salinity branch with `if site.region is not None:`
— the exact repair an implementer would reach for. `test_a_below_floor_site_with_no_region_is_still_tier_d`
must go red, and `test_an_above_floor_site_with_no_region_is_not_contraindicated` must stay
green. Restore, re-run green. Record both.

---

### Task 4: `gridded.py` — the reader and its coverage decision

**Files:**
- Create: `src/seagarden_dst/gridded.py`
- Test: `tests/test_gridded.py` (create), `tests/test_gridded_isolation.py` (create)

**Interfaces:**
- Consumes: Task 1 vocabulary, `artifact.pair.load_pair`, `artifact.manifest.Manifest`
- Produces: `GriddedForcing.from_directory(path) -> GriddedForcing`, `GriddedForcing.reading_at(query)`, `artifact_directory() -> Path`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_gridded.py
import pytest

pytest.importorskip("xarray")
import numpy as np  # noqa: E402

from seagarden_dst.forcing import Aggregation, Coverage, SiteQuery  # noqa: E402
from seagarden_dst.gridded import GriddedForcing  # noqa: E402

pytestmark = pytest.mark.spatial

FIXTURE = "tests/fixtures/data"


def _point(lat, lon):
    return f"POINT ({lon} {lat})"


@pytest.fixture
def reader():
    return GriddedForcing.from_directory(FIXTURE)


def test_a_valid_cell_returns_conditions(reader):
    # Cell [1,1] of the fixture is valid.
    lats, lons = reader.latitudes, reader.longitudes
    reading = reader.reading_at(SiteQuery(_point(lats[1], lons[1]), year=2024))
    assert reading.coverage is Coverage.VALID
    assert reading.conditions is not None
    assert reading.from_artifact is True
    assert reading.aggregation is Aggregation.CONTAINING_CELL


def test_an_invalid_cell_blocks_without_raising(reader):
    """The fixture's invalid cell holds FINITE values — `valid[0,0]` is False but the
    data there is `rng.random(...)`. A reader inferring validity from NaN returns
    conditions for it. This test fails for that reader and passes for one that reads
    the mask."""
    lats, lons = reader.latitudes, reader.longitudes
    reading = reader.reading_at(SiteQuery(_point(lats[0], lons[0]), year=2024))
    assert reading.coverage is Coverage.CELL_INVALID
    assert reading.conditions is None


def test_the_distance_to_the_nearest_valid_cell_is_reported(reader):
    """§6.2 requires it: at native resolution it is 0.75-1.28 km across all six regions,
    and it is the quantity a siting user can actually judge."""
    lats, lons = reader.latitudes, reader.longitudes
    reading = reader.reading_at(SiteQuery(_point(lats[0], lons[0]), year=2024))
    assert reading.nearest_valid_km is not None
    assert 0.0 < reading.nearest_valid_km < 10.0


def test_a_year_the_artifact_lacks_blocks_and_never_substitutes(reader):
    """§6.2/§7: never silently substitutes another year. The fixture carries 2024-2025."""
    lats, lons = reader.latitudes, reader.longitudes
    reading = reader.reading_at(SiteQuery(_point(lats[1], lons[1]), year=2019))
    assert reading.coverage is Coverage.YEAR_ABSENT
    assert reading.conditions is None
    assert reading.year == 2019


def test_a_land_cell_with_nan_blocks_rather_than_raising(tmp_path):
    """The committed fixture has no NaN, so this builds one. `SiteConditions` raises on
    a non-finite field, so a reader that constructs before checking coverage turns a
    real land cell into a ValueError where §7 requires a visible block."""
    import shutil

    import xarray as xr

    shutil.copytree(FIXTURE, tmp_path / "data")
    artifact = tmp_path / "data" / "forcing.nc"
    ds = xr.open_dataset(artifact, engine="h5netcdf").load()
    ds.close()
    for name in ("temp_c", "salinity_psu", "depth_mean_m"):
        ds[name].values[..., 0, 0] = np.float32("nan")
    ds.to_netcdf(artifact, engine="h5netcdf", mode="w")

    _restamp(tmp_path / "data")
    reader = GriddedForcing.from_directory(tmp_path / "data")
    lats, lons = reader.latitudes, reader.longitudes
    reading = reader.reading_at(SiteQuery(_point(lats[0], lons[0]), year=2024))
    assert reading.coverage is Coverage.CELL_INVALID
    assert reading.conditions is None


def test_the_reader_refuses_an_unrecognised_schema_version(tmp_path):
    """§7: refuse, fall back, say why — never read an artifact whose shape you do not
    know."""
    import json
    import shutil

    shutil.copytree(FIXTURE, tmp_path / "data")
    manifest_path = tmp_path / "data" / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["artifact_schema_version"] = 99
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    _restamp(tmp_path / "data")
    with pytest.raises(ValueError, match="artifact_schema_version"):
        GriddedForcing.from_directory(tmp_path / "data")


def _restamp(directory):
    """Recompute the manifest's sha after a test mutates the artifact.

    `load_pair(target_dir)` takes no opt-out: it refuses a torn pair on the sha256 that
    links artifact to manifest, which is package C-a's atomicity guarantee and not
    something a test should be able to switch off. So a test that edits the NetCDF
    restamps the manifest, exactly as `write_pair` does.
    """
    import json

    from seagarden_dst.artifact.pair import sha256_of

    directory = pathlib.Path(directory)
    manifest_path = directory / "manifest.json"
    artifact = directory / "forcing.nc"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["artifact_sha256"] = sha256_of(artifact)
    payload["artifact_bytes"] = artifact.stat().st_size
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
```

```python
# tests/test_gridded_isolation.py
"""`gridded.py` is the only module outside `refresh/` that imports xarray.

Scoped to the core, NOT to `src/`: five `refresh/` modules already import it, one at
runtime (`merge.py:85`), and that is correct — `refresh/` is build-time tooling walled
off by `test_no_core_module_imports_refresh`. A `src/`-wide assertion would fail the day
it was written, which is how the first draft of the D-a design had it.
"""

import ast
import pathlib


def test_only_gridded_imports_xarray_outside_refresh():
    root = pathlib.Path(__file__).resolve().parents[1] / "src" / "seagarden_dst"
    offenders = []
    for path in sorted(root.rglob("*.py")):
        if "refresh" in path.parts or path.name == "gridded.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            if any(n.split(".")[0] in {"xarray", "rioxarray", "shapely"} for n in names):
                offenders.append(f"{path.name}:{node.lineno}")
    assert not offenders, f"spatial-extra imports outside refresh/ and gridded.py: {offenders}"
```

- [ ] **Step 2: Run to verify they fail**

```bash
micromamba run -n shiny python -m pytest tests/test_gridded.py -v -m spatial
micromamba run -n shiny python -m pytest tests/test_gridded_isolation.py -v
```
Expected: the first FAILs with `ModuleNotFoundError: No module named 'seagarden_dst.gridded'`; the second PASSES already (nothing imports xarray outside `refresh/` yet) — that is fine, it is a guard against regression, and Task 4 is what makes it meaningful.

- [ ] **Step 3: Write `gridded.py`**

```python
"""Read the forcing artifact package C builds (§6).

**The only module outside `refresh/` that imports xarray.** The model core and the app
must both work on an install with no `spatial` extra — CI's `[app,dev]` job is that
install — so `artifact/` was built pydantic+stdlib+numpy only and `load_pair` returns
`(Manifest, Path)` rather than an opened dataset, leaving the open to whoever has xarray.
That is this module. `tests/test_gridded_isolation.py` asserts it.
"""

from __future__ import annotations

import math
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from seagarden_dst.artifact.manifest import ARTIFACT_SCHEMA_VERSION, Manifest
from seagarden_dst.artifact.pair import load_pair
from seagarden_dst.forcing import (
    Aggregation,
    Coverage,
    SiteConditions,
    SiteQuery,
    SiteReading,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    import xarray as xr

#: §6.3's locator. Nothing read this before package D-a; the refresh CLI writes to its
#: own `--target`, defaulting to `data/forcing`.
_DATA_DIR_ENV = "SEAGARDEN_DATA_DIR"
_DEFAULT_DATA_DIR = Path("data")

_POINT = re.compile(r"POINT\s*\(\s*([-\d.]+)\s+([-\d.]+)\s*\)", re.IGNORECASE)
_EARTH_RADIUS_KM = 6371.0


def artifact_directory() -> Path:
    """Where the artifact/manifest pair lives (§6.3)."""
    return Path(os.environ.get(_DATA_DIR_ENV, _DEFAULT_DATA_DIR))


class GriddedForcing:
    """Site conditions read from the artifact, for a polygon and a year."""

    def __init__(self, manifest: Manifest, dataset: xr.Dataset) -> None:
        self._manifest = manifest
        self._ds = dataset
        self.latitudes = np.asarray(dataset["latitude"].values, dtype=float)
        self.longitudes = np.asarray(dataset["longitude"].values, dtype=float)
        self._years = [int(y) for y in np.asarray(dataset["year"].values)]

    @classmethod
    def from_directory(cls, directory) -> GriddedForcing:
        import xarray as xr

        # `load_pair` refuses a torn pair on the sha256 linking artifact to manifest.
        # There is deliberately no opt-out: that is C-a's atomicity guarantee.
        manifest, artifact = load_pair(Path(directory))
        if manifest.artifact_schema_version != ARTIFACT_SCHEMA_VERSION:
            raise ValueError(
                f"unrecognised artifact_schema_version "
                f"{manifest.artifact_schema_version}: this build reads version "
                f"{ARTIFACT_SCHEMA_VERSION}. Refusing rather than reading an artifact "
                "whose shape is not known (§7)."
            )
        return cls(manifest, xr.open_dataset(artifact, engine="h5netcdf").load())

    def reading_at(self, query: SiteQuery) -> SiteReading:
        lat, lon = self._point_of(query)
        row, col = self._nearest_index(lat, lon)

        if query.year not in self._years:
            # Never substitutes another year (§6.2): interannual spread is the dominant
            # term, so a neighbouring year is a different answer, not an approximation.
            return SiteReading(
                conditions=None, coverage=Coverage.YEAR_ABSENT, year=query.year,
                aggregation=Aggregation.CONTAINING_CELL, from_artifact=True,
            )

        # The `valid` field, by value. NEVER inferred from NaN: the committed fixture's
        # invalid cell holds finite numbers, so a NaN test would call it assessable.
        if not bool(self._ds["valid"].values[row, col]):
            return SiteReading(
                conditions=None, coverage=Coverage.CELL_INVALID, year=query.year,
                aggregation=Aggregation.CONTAINING_CELL,
                nearest_valid_km=self._nearest_valid_km(row, col),
                from_artifact=True,
            )

        return SiteReading(
            conditions=self._conditions_at(row, col, query.year, query.region),
            coverage=Coverage.VALID, year=query.year,
            aggregation=Aggregation.CONTAINING_CELL, from_artifact=True,
        )
```

The implementer completes `_point_of`, `_nearest_index`, `_nearest_valid_km` and `_conditions_at`. Requirements for each, so none is invented:

- **`_point_of(query)`** — parse `POINT (lon lat)` from `query.geometry_wkt` with `_POINT`; for a `POLYGON`, take the centroid of its ring coordinates (plain arithmetic; do not import shapely). Raise `ValueError` naming the unparsed string if neither matches.
- **`_nearest_index(lat, lon)`** — `int(np.abs(self.latitudes - lat).argmin())` and the same for longitude. This is the containing cell at this resolution.
- **`_nearest_valid_km(row, col)`** — over every cell where `valid` is True, compute the great-circle distance from the query cell's centre and return the minimum, in km, using `_EARTH_RADIUS_KM` and the haversine formula. Return `None` if no cell is valid.
- **`_conditions_at(row, col, year, region)`** — build a `SiteConditions`. `float(...)` every value out of the array: they are float32, and while `SiteConditions` now catches non-finite float32 (`3f0bc35`), passing Python floats keeps the record's types honest. `surface_par` is NOT in the artifact (C§3.3) — use `PLACEHOLDER_SURFACE_PAR` from `forcing.py` and leave a comment saying the artifact records its absence deliberately. `significant_wave_m` has **no year dimension** — index it by month only. Take the annual mean over months for `mean_temp_c`, the max for `summer_temp_c`, the min for `winter_temp_c`. `region` is `query.region`, which may be `None`.

- [ ] **Step 4: Run tests to verify they pass**

```bash
micromamba run -n shiny python -m pytest tests/test_gridded.py -v -m spatial
micromamba run -n shiny python -m pytest tests/test_gridded_isolation.py -v
```
Expected: 6 passed, then 1 passed.

- [ ] **Step 5: Commit**

```bash
git add src/seagarden_dst/gridded.py tests/test_gridded.py tests/test_gridded_isolation.py
git commit -m "feat(gridded): read the artifact, decide coverage from the valid field"
```

- [ ] **Step 6: DELETE proof — the `valid` check**

Replace `if not bool(self._ds["valid"].values[row, col]):` with a NaN test —
`if not np.isfinite(self._ds["temp_c"].values[0, 0, row, col]):`. Against the committed
fixture, `test_an_invalid_cell_blocks_without_raising` must go **red**, because that
cell's values are finite. Against the NaN fixture built in
`test_a_land_cell_with_nan_blocks_rather_than_raising` it stays green. That asymmetry is
the proof that reading the mask is not the same as testing for NaN. Restore, re-run green.

- [ ] **Step 7: DELETE proof — the year check**

Remove the `if query.year not in self._years:` block. `test_a_year_the_artifact_lacks_blocks_and_never_substitutes` must go red, and record how: an `IndexError` from indexing a missing year is a different failure from silently returning year 2024's data, and only the second is the one §6.2 forbids. Say which you saw. Restore, re-run green.

---

### Task 5: `daily_forcing` from the monthly fields

**Files:**
- Modify: `src/seagarden_dst/gridded.py`
- Test: `tests/test_gridded.py` (extend)

**Interfaces:**
- Consumes: Task 4's `GriddedForcing`
- Produces: `GriddedForcing.daily_forcing(site, window, year)`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_gridded.py`:

```python
def test_daily_forcing_comes_from_the_monthly_fields_not_a_sinusoid(reader):
    """§6.2: monthly fields REPLACE the sinusoid rather than feeding it."""
    lats, lons = reader.latitudes, reader.longitudes
    site = reader.reading_at(SiteQuery(_point(lats[1], lons[1]), year=2024)).conditions
    days, par, temp, din = reader.daily_forcing(site, (4, 9), 2024)
    assert len(days) == len(temp) == len(par) == len(din)
    assert np.isfinite(temp).all()


def test_two_years_give_different_series(reader):
    """The whole reason `daily_forcing` takes a year: collapsing years into one
    climatology costs -57% to +179% in final biomass (§6.2)."""
    lats, lons = reader.latitudes, reader.longitudes
    site = reader.reading_at(SiteQuery(_point(lats[1], lons[1]), year=2024)).conditions
    _, _, temp_2024, _ = reader.daily_forcing(site, (4, 9), 2024)
    _, _, temp_2025, _ = reader.daily_forcing(site, (4, 9), 2025)
    assert not np.allclose(temp_2024, temp_2025)


def test_a_wrapping_window_takes_january_from_the_following_year(reader):
    """§6.2's year boundary. A window that wraps past December must take January from
    Y+1, not from the same year's January twelve months earlier."""
    lats, lons = reader.latitudes, reader.longitudes
    site = reader.reading_at(SiteQuery(_point(lats[1], lons[1]), year=2024)).conditions
    _, _, wrapped, _ = reader.daily_forcing(site, (11, 2), 2024)
    assert np.isfinite(wrapped).all()


def test_a_wrapping_window_blocks_when_the_following_year_is_absent(reader):
    """The fixture carries 2024-2025, so a window wrapping out of 2025 has no Y+1."""
    lats, lons = reader.latitudes, reader.longitudes
    site = reader.reading_at(SiteQuery(_point(lats[1], lons[1]), year=2025)).conditions
    with pytest.raises(ValueError, match="wrapping window needs"):
        reader.daily_forcing(site, (11, 2), 2025)
```

- [ ] **Step 2: Run to verify it fails**

Run: `micromamba run -n shiny python -m pytest tests/test_gridded.py -v -m spatial`
Expected: FAIL — `AttributeError: 'GriddedForcing' object has no attribute 'daily_forcing'`

- [ ] **Step 3: Implement `daily_forcing`**

Add to `GriddedForcing`. The requirements, so nothing is invented:

- Signature `daily_forcing(self, site, window, year)`, matching `ForcingSource`.
- Build the day axis exactly as `forcing.daily_forcing` does — `day_of_year(start, 1)` to `day_of_year(end, 28)`, adding 365 when `last < first`. Import `day_of_year` from `forcing`; do not re-derive it.
- Interpolate **linearly on day-of-year** between monthly values, each month's value placed at its mid-month day. Use `np.interp`.
- A window that wraps past December takes the wrapped months from **year + 1**. If `year + 1` is not in `self._years`, raise `ValueError` whose message contains `wrapping window needs` and names both years. Never wrap back to the same year's January.
- `par` comes from `site.par_at_depth()` scaled by the same seasonal shape the placeholder uses, because the artifact carries no PAR (C§3.3) — the daily series is as invented as the constant, and a comment must say so.
- `din` comes from the artifact's `din_umol_l`; `temp` from `temp_c`.
- The cell is the one the `site` came from. Store `(row, col)` on the reading path, or re-derive it — say which you chose and why in the module.

- [ ] **Step 4: Run tests to verify they pass**

Run: `micromamba run -n shiny python -m pytest tests/test_gridded.py -v -m spatial`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add src/seagarden_dst/gridded.py tests/test_gridded.py
git commit -m "feat(gridded): build the daily series from the monthly fields, per year"
```

- [ ] **Step 6: DELETE proof — the wrap-to-next-year rule**

Change the wrap to take January from the **same** year instead of `year + 1`.
`test_a_wrapping_window_blocks_when_the_following_year_is_absent` must go red with
`DID NOT RAISE`, and `test_a_wrapping_window_takes_january_from_the_following_year`
should still pass — which tells you that test alone does not discriminate, and the
blocking test is carrying the proof. Record both outcomes. Restore, re-run green.

---

### Task 6: Make the degradation visible

**Files:**
- Modify: `app/modules/results.py`, `app/modules/report.py`, `app/shell.py` or `app/app.py` (the banner)
- Test: `app/tests/test_app_smoke.py` (extend)

**Interfaces:**
- Consumes: Task 3's `unassessable`, `coverage`, `nearest_valid_km` on the assessment
- Produces: a banner naming the data source; Results and Report distinguishing unassessed from unsuitable

- [ ] **Step 1: Write the failing tests**

Append to `app/tests/test_app_smoke.py`:

```python
def test_an_unassessable_assessment_reads_as_unassessed_not_unsuitable():
    """§7's point. 'We did not look' and 'we looked and it is bad' are different
    answers, and only one of them should stop somebody siting a farm there."""
    from app.modules._widgets import headline_for
    from seagarden_dst import SiteContext
    from seagarden_dst.api import assess_site
    from seagarden_dst.forcing import Aggregation, Coverage, SiteReading

    blocked = SiteReading(
        conditions=None, coverage=Coverage.CELL_INVALID, year=2024,
        aggregation=Aggregation.CONTAINING_CELL, nearest_valid_km=1.1,
        from_artifact=True,
    )
    result = assess_site(SiteContext.from_reading(blocked, label="Off-grid"))
    _cls, text = headline_for(result)
    assert "unassess" in text.lower()
    assert "unsuitable" not in text.lower()


def test_the_banner_names_what_the_tool_is_running_on():
    """§7 row 1: fall back to PlaceholderForcing WITH A BANNER naming the source. A
    silent fallback is the failure — the user cannot tell measurements from inventions."""
    from app.modules._widgets import data_source_banner

    assert "placeholder" in data_source_banner(from_artifact=False).lower()
    assert "placeholder" not in data_source_banner(from_artifact=True).lower()
```

- [ ] **Step 2: Run to verify it fails**

Run: `micromamba run -n shiny python -m pytest app/tests -q`
Expected: FAIL — `ImportError: cannot import name 'data_source_banner'`

- [ ] **Step 3: Implement**

Add `data_source_banner(*, from_artifact: bool) -> str` to `app/modules/_widgets.py`, returning a sentence naming the source — for the placeholder, that the numbers are plausible order-of-magnitude values and not measurements; for the artifact, which year and which artifact build date, read from the manifest.

Extend `headline_for` so an `unassessable` assessment returns an "unassessed" headline naming the reason (`Coverage.CELL_INVALID` → no data at this cell, with `nearest_valid_km`; `Coverage.YEAR_ABSENT` → the artifact does not carry that year). Read the existing `headline_for` and match its `(css_class, text)` shape.

Render the banner in the app's sidebar beside `status_slot`, and carry the unassessed reason into the report text in `app/modules/report.py`.

- [ ] **Step 4: Run the whole suite**

```bash
micromamba run -n shiny python -m pytest -q
micromamba run -n shiny python -m pytest -q -m spatial
micromamba run -n shiny ruff check .
```
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add app/ tests/
git commit -m "feat(app): show the data source, and tell unassessed from unsuitable"
```

- [ ] **Step 6: DELETE proof — the unassessed branch**

Make `headline_for` ignore the `unassessable` flag and fall through to its normal path.
`test_an_unassessable_assessment_reads_as_unassessed_not_unsuitable` must go red. Record
what the headline said instead — if it read as a verdict, that is the failure §7 exists to
prevent, and worth quoting in the report. Restore, re-run green.

---

## Done-When Coverage

| Spec clause | Task | Proven by |
|---|---|---|
| 1 — polygon query aggregates over cells | 4 | `_point_of` centroid + `test_a_valid_cell_returns_conditions` (multi-cell aggregation is D-b) |
| 2 — absent year blocks, never substitutes | 4 | `test_a_year_the_artifact_lacks_blocks_and_never_substitutes` |
| 3 — wrapping window takes January from Y+1, blocks without it | 5 | `test_a_wrapping_window_blocks_when_the_following_year_is_absent` |
| 4 — unassessable returns UNKNOWN, never a verdict | 3 | `test_an_unassessable_site_returns_unassessable_and_never_a_verdict` |
| 5 — `gridded.py` the only xarray importer outside `refresh/` | 4 | `tests/test_gridded_isolation.py` |
| 6 — `PlaceholderForcing` satisfies the widened protocol | 2 | `test_the_placeholder_satisfies_the_widened_protocol` |
| 7 — distance to nearest valid cell reported and plausible | 4 | `test_the_distance_to_the_nearest_valid_cell_is_reported` |
| 8 — invalid cell blocks, on `valid` not NaN, and does not raise | 4 | both cell tests + the Step 6 mutation asymmetry |
| 9 — degradation is visible | 6 | both app tests |
| 10 — below-floor site outside every domain is tier D, not tier C | 3b | `test_a_below_floor_site_with_no_region_is_still_tier_d` |

## Out of Scope

The `terra` salinity-weighting port and the valid-fraction threshold (D-b, after package
E); the `methods.yaml` wave re-validation (D-c); polygon drawing (E); human-use overlay
(C1, F1); re-parameterisation against real forcing (D1, which this unblocks).
