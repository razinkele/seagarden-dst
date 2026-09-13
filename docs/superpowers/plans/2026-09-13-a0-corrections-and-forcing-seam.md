# A0 Corrections and the Forcing Seam — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the tool's numbers mean what the documents say they mean, then put forcing behind a seam indexed by calendar day — so the data layer can replace it without touching the models.

**Architecture:** Two packages from the design, in order. **A0** corrects four modelling defects that would otherwise be frozen as the baseline by the golden-file snapshot: tier D leaking through the number-producing path, four species with no lower salinity bound, *Fucus* running on kelp stoichiometry, and Saccharina's salinity factor applied to the growth rate rather than the published yield model. A golden-file snapshot then goes in. **A** introduces the `ForcingSource` protocol, re-indexes the placeholder nutrient field by calendar day, and resets the Tagalaht test bound that this necessarily moves.

**Tech Stack:** Python ≥3.11, numpy, scipy, pydantic v2, pyyaml. Tests with pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-13-dst-data-layer-design.md` (revision 4) and `SeaGarden_DST_functional_specification_v0.1.md`. Read both — the plan argues from them.

**Scope note:** This plan covers packages **A0** and **A** only. Packages B, C, C1, D, D1, E, F1, F2 and G get their own plans; B is a measurement spike whose results reshape C and D, so planning those in task detail now would be inventing.

## Global Constraints

- **Python environment:** micromamba env `shiny`. There is no global Python. Run everything as `micromamba run -n shiny <cmd>`. Never create a venv.
- **Runtime dependencies stay at four:** numpy, scipy, pydantic, pyyaml. Nothing added by this plan.
- **Coefficients live in `params/`, never in code** (design §3.4, spec §1 premise). A magic number in a `.py` file is a defect.
- **Every public model function returns a `Quantity` carrying a `Calibration`** (spec §7.4). Numbers do not travel without provenance.
- **Suitability is a minimum of constraints, never a weighted index** (spec §5.2). An absent input blocks the verdict; it never passes it.
- **Tier D means "a local finding contradicts the model"** (spec §7.4). Extrapolation is tier B or C. Do not widen tier D.
- **CI never touches the network.** Line length 100, `ruff check .` must pass (`select = ["E","F","I","UP","B"]`).
- **The full suite must be green at the end of every task** except where a task explicitly says which assertion it is changing and why.
- Run the suite with `micromamba run -n shiny python -m pytest -q`. It is 85 passed, 1 xfailed at the start of this plan.

---

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `src/seagarden_dst/growth.py` | Tier resolution via `contraindication()`; the salinity-indexed yield model | 1, 4 |
| `src/seagarden_dst/shellfish.py` | Same tier resolution for the banded model | 1 |
| `params/species/*.yaml` | `tolerance_floor_psu`, `demonstrated_salinity_range`, `dry_matter`, `anchors`, corrected *Fucus* fractions | 2, 3, 4, 5 |
| `src/seagarden_dst/params.py` | Schema for the new fields; `upper_temp_decline_c` | 2, 4, 6 |
| `params/assessment.yaml` | **New.** The three thresholds now in Python defaults | 6 |
| `src/seagarden_dst/suitability.py` | Reads thresholds from `params/`; corrected floor message | 6 |
| `src/seagarden_dst/forcing.py` | `ForcingSource` protocol, `PlaceholderForcing`, calendar-day DIN | 9, 10 |
| `tests/test_tier_d_enforcement.py` | **New.** The leak, at the layer that produces the number | 1 |
| `tests/test_salinity_yield_model.py` | **New.** The published OLAMUR form | 4 |
| `tests/test_golden_snapshot.py` | **New.** The regression net | 8 |
| `tests/test_forcing_source.py` | **New.** The seam | 9, 10 |

---

## Task 1: Tier D resolved at the layer that produces the number

The design's §3.2 defect. `contraindication()` knows sugar kelp is contraindicated below 16 psu; `harvest_biomass()` never asks it, resolving the tier from the per-region registry instead. Three of the five placeholder sites below the floor therefore report a positive tier-C harvest — including EE-coastal, which is Tagalaht, where OLAMUR observed the cultivation failure this whole mechanism exists to represent.

**Files:**
- Modify: `src/seagarden_dst/growth.py:141-158` (`harvest_biomass`)
- Modify: `src/seagarden_dst/shellfish.py:60` (`harvest`)
- Test: `tests/test_tier_d_enforcement.py` (create)

**Interfaces:**
- Consumes: `contraindication(species, site) -> Calibration | None` (already exists, `growth.py:161`)
- Produces: no signature changes. `harvest_biomass` and `shellfish.harvest` return non-reportable `Quantity` objects for any contraindicated pairing.

- [ ] **Step 1: Write the failing test**

Create `tests/test_tier_d_enforcement.py`:

```python
"""Tier D must be enforced where the number is produced, not only where it is orchestrated.

`api.assess_site()` consults `contraindication()` and excludes correctly, so the Shiny
app was never affected. `harvest_biomass()` did not, and it is the function the README
invites notebook and batch users to call. The rule was right; the enforcement was at the
wrong layer.
"""

from __future__ import annotations

import pytest

from seagarden_dst import PLACEHOLDER_SITES, default_parameters
from seagarden_dst.calibration import Tier
from seagarden_dst.growth import contraindication, harvest_biomass


@pytest.fixture(scope="module")
def params():
    return default_parameters()


def _below_floor(species):
    """Placeholder sites where this species' salinity floor is breached."""
    floor = species.salinity.tolerance_floor_psu if species.salinity else None
    if floor is None:
        return []
    return [s for s in PLACEHOLDER_SITES.values() if s.salinity_psu < floor]


def test_nothing_is_reportable_below_its_salinity_floor(params):
    """The leak, in executable form. Sugar kelp reported 4.52-40.7 kg DW at DE-coastal."""
    kelp = params.species["saccharina_latissima"]
    sites = _below_floor(kelp)
    assert len(sites) == 5, "expected five placeholder sites below the 16 psu floor"

    for site in sites:
        harvest = harvest_biomass(kelp, site, area_m2=1000.0)
        assert not harvest.calibration.is_reportable, (
            f"{site.region} at {site.salinity_psu} psu reported {harvest.value:.1f} kg DW "
            "for a species contraindicated at that salinity"
        )
        assert harvest.calibration.tier is Tier.D
        assert harvest.value == 0.0


def test_the_dynamic_rule_and_the_produced_tier_agree(params):
    """Whenever contraindication() says D, the number-producing path must say D too.

    These were two disconnected mechanisms: a static per-region registry and a dynamic
    salinity rule. This asserts they can no longer disagree.
    """
    for species in params.species.values():
        for site in PLACEHOLDER_SITES.values():
            contra = contraindication(species, site)
            if contra is None:
                continue
            if species.group == "macroalga":
                quantity = harvest_biomass(species, site, area_m2=1000.0)
            else:
                from seagarden_dst.shellfish import harvest

                quantity = harvest(species, site, area_ha=0.1).fresh_weight
            assert quantity.calibration.tier is Tier.D, (
                f"{species.key} at {site.region}: contraindication() says D, "
                f"the harvest path says {quantity.calibration.tier.value}"
            )
```

- [ ] **Step 2: Run it and watch it fail**

```bash
micromamba run -n shiny python -m pytest tests/test_tier_d_enforcement.py -q
```

Expected: both tests FAIL. The first reports EE-coastal (6.0 psu), PL-coastal (7.5) and DE-coastal (11.0) returning reportable values.

- [ ] **Step 3: Resolve the tier through `contraindication()` in `growth.harvest_biomass`**

In `src/seagarden_dst/growth.py`, replace the opening of `harvest_biomass`:

```python
def harvest_biomass(
    species: SpeciesParams,
    site: SiteConditions,
    area_m2: float,
) -> Quantity:
    """Harvested dry biomass over one cultivation cycle, in kg DW.

    Returns a Quantity so the calibration tier travels with the number. A
    contraindicated combination (tier D) returns a zero-valued Quantity whose
    calibration is not reportable - callers must show the note, not the number.

    The tier is resolved through `contraindication()` rather than through
    `calibration_for()` so that the dynamic salinity rule and the per-region registry
    cannot disagree. Enforcing it here rather than only in `api.assess_site` is
    deliberate: this is the function that produces the number.
    """
    contra = contraindication(species, site)
    if contra is not None:
        return Quantity(value=0.0, unit="kg DW", calibration=contra)

    calibration = species.calibration_for(site.region)
    trajectory = simulate(species, site)
    kg = trajectory.final_biomass * area_m2 / 1000.0
    return Quantity(value=kg, unit="kg DW", calibration=calibration)
```

`contraindication` is defined below `harvest_biomass` in the same module, which is fine — it is resolved at call time, not at definition time.

- [ ] **Step 4: Do the same in `shellfish.harvest`**

Open `src/seagarden_dst/shellfish.py` and read `harvest()` in full before editing. Add the same guard as the first statement of the function body, after the docstring, returning a `ShellfishHarvest` whose every `Quantity` carries `contra` as its calibration and `0.0` as its value. Match the construction already used in that function for the reportable path — do not invent a different shape.

- [ ] **Step 5: Run the new tests**

```bash
micromamba run -n shiny python -m pytest tests/test_tier_d_enforcement.py -q
```

Expected: 2 passed.

- [ ] **Step 6: Run the whole suite**

```bash
micromamba run -n shiny python -m pytest -q && micromamba run -n shiny ruff check .
```

Expected: 87 passed, 1 xfailed. **If any existing test fails, stop.** A pre-existing test that asserts a reportable sugar-kelp number at a sub-floor site is itself the defect; report it rather than editing it.

- [ ] **Step 7: Commit**

```bash
git add tests/test_tier_d_enforcement.py src/seagarden_dst/growth.py src/seagarden_dst/shellfish.py
git commit -m "Resolve tier D where the number is produced, not only where it is orchestrated

contraindication() knew sugar kelp was contraindicated below 16 psu.
harvest_biomass() never asked it, resolving the tier from the per-region
registry, which listed only LT-coastal and PL-lagoon. Three of the five
placeholder sites below the floor therefore reported a positive tier C
harvest: EE-coastal 1.4-12.6, PL-coastal 2.15-19.4 and DE-coastal
4.52-40.7 kg DW. EE-coastal is Tagalaht, where OLAMUR observed the
cultivation failure this mechanism exists to represent.

api.assess_site() did consult contraindication(), so the application was
never affected. The leak was in the library path the README invites
notebook and batch use of. The rule was right and its enforcement was at
the wrong layer."
```

---

## Task 2: A salinity floor for every species, and a note that does not overclaim

Only Saccharina carries `tolerance_floor_psu`. The other four are unbounded below, so the tool returns confident yields at 2.0 psu in the Szczecin Lagoon where none is cultivable. And once four more species get floors, `contraindication()`'s note — *"cultivation failure has been observed at this salinity"* — starts asserting a finding nobody made.

Design §3.3 is emphatic about what this is **not**: `demonstrated_salinity_range` records provenance and widens the displayed band. It is **not** a tier D trigger. Tier D is a contradicting local finding (spec §7.4); extrapolation is tier B or C.

**Files:**
- Modify: `src/seagarden_dst/params.py` (`SalinityResponse`, `ShellfishYield`)
- Modify: `src/seagarden_dst/growth.py` (`contraindication`'s note)
- Modify: `params/species/fucus_vesiculosus.yaml`, `ulva.yaml`, `chorda_filum.yaml`, `mytilus.yaml`
- Test: `tests/test_tier_d_enforcement.py` (extend)

**Interfaces:**
- Consumes: `SalinityResponse.tolerance_floor_psu` (exists), `Calibration` (exists)
- Produces: `SalinityResponse.floor_basis: Literal["observed", "assumed"]`, `SalinityResponse.demonstrated_salinity_range: tuple[float, float] | None`, `ShellfishYield.tolerance_floor_psu: float | None` and the same two fields

- [ ] **Step 1: Write the failing test**

Append to `tests/test_tier_d_enforcement.py`:

```python
def test_every_species_has_a_lower_salinity_bound(params):
    """The Szczecin Lagoon is 2.0 psu. Nothing shipped is cultivable there."""
    lagoon = PLACEHOLDER_SITES["PL-lagoon"]
    for species in params.species.values():
        contra = contraindication(species, lagoon)
        assert contra is not None, (
            f"{species.key} returns a confident yield at {lagoon.salinity_psu} psu"
        )


def test_an_assumed_floor_does_not_claim_an_observation(params):
    """`contraindication()` said 'cultivation failure has been observed at this salinity'
    for every species below its floor. For four of five that asserts a finding nobody
    made. Chorda is the test case: its coefficients are a structural analogue of Fucus
    and nothing about it has been observed anywhere."""
    chorda = params.species["chorda_filum"]
    lagoon = PLACEHOLDER_SITES["PL-lagoon"]

    assert chorda.salinity is not None
    assert chorda.salinity.floor_basis == "assumed"

    note = (contraindication(chorda, lagoon).note or "").lower()
    assert "observed" not in note
    assert "assumed" in note

    kelp = params.species["saccharina_latissima"]
    assert kelp.salinity.floor_basis == "observed"
    assert "observed" in (contraindication(kelp, lagoon).note or "").lower()
```

- [ ] **Step 2: Run it and watch it fail**

```bash
micromamba run -n shiny python -m pytest tests/test_tier_d_enforcement.py -q
```

Expected: both new tests FAIL — the first because *Fucus*, *Ulva*, *Chorda* and *Mytilus* have no floor; the second on `floor_basis` not existing.

- [ ] **Step 3: Add the schema fields**

In `src/seagarden_dst/params.py`, add to `SalinityResponse` (and the same three to `ShellfishYield`):

```python
    floor_basis: Literal["observed", "assumed"] = Field(
        default="assumed",
        description=(
            "Whether tolerance_floor_psu rests on an observed cultivation failure or is "
            "assumed. Governs what contraindication() is allowed to tell the user: only "
            "an observed floor may be reported as a finding (specification 7.4, tier D)."
        ),
    )
    demonstrated_salinity_range: tuple[float, float] | None = Field(
        default=None,
        description=(
            "Salinity range the parameters were actually established in. Provenance that "
            "widens the displayed band; NOT a tier D trigger - extrapolation beyond it is "
            "tier B or C per specification 7.4."
        ),
    )
```

Add `from typing import Literal` to the imports if it is not already there.

- [ ] **Step 4: Make the note honest about its basis**

In `src/seagarden_dst/growth.py`, in `contraindication()`, replace the constructed note:

```python
        observed = species.salinity.floor_basis == "observed"
        if observed:
            detail = (
                f"cultivation failure has been observed at this salinity"
            )
        else:
            detail = (
                f"the floor is assumed, not observed - no cultivation trial at this "
                f"salinity is known to us"
            )
        return Calibration(
            tier=Tier.D,
            region=site.region,
            source=calibration.source,
            note=(
                f"Below {species.salinity.tolerance_floor_psu:g} psu the model returns a "
                f"positive yield, but {detail}. Treat as not cultivable here."
            ),
        )
```

- [ ] **Step 5: Give the four species their floors**

Edit each YAML. Every floor that is not read off a published trial gets `floor_basis: assumed` and a comment naming what it rests on, in the style `chorda_filum.yaml` already uses for its growth coefficients.

`params/species/fucus_vesiculosus.yaml`, under `salinity:`:

```yaml
  tolerance_floor_psu: 4.0
  floor_basis: assumed          # Fucus vesiculosus persists into the Bothnian Bay at
                                # 3-4 psu but with sharply reduced growth. No cultivation
                                # trial below 4 psu is known to us. Refine against A3.4.
  demonstrated_salinity_range: [5.5, 6.5]   # OLAMUR Tagalaht pilot
```

`params/species/ulva.yaml`:

```yaml
  tolerance_floor_psu: 2.5
  floor_basis: assumed          # Ulva is broadly euryhaline; 2.5 psu is a conservative
                                # placeholder, not a demonstrated limit. Refine against A3.4.
  demonstrated_salinity_range: [5.0, 20.0]
```

`params/species/chorda_filum.yaml`:

```yaml
  tolerance_floor_psu: 4.0
  floor_basis: assumed          # Assumed from Fucus, like every other Chorda coefficient
                                # in this file. Nothing here is fitted. See D1 in the
                                # specification's open decisions.
  demonstrated_salinity_range: null
```

`params/species/mytilus.yaml`, under `shellfish_yield:`:

```yaml
  tolerance_floor_psu: 4.0
  floor_basis: assumed          # Mytilus trossulus persists to ~4 psu with strongly
                                # reduced shell growth; mitigation culture below 16 psu
                                # is already the banded model's low band. Refine against A3.4.
  demonstrated_salinity_range: [6.0, 18.0]
```

If any of these species has `salinity: applies: false`, set `applies: true` — the response now carries a floor whether or not a scaling factor applies. Check `SalinityResponse.factor()` returns 1.0 when no scaling coefficients are set; if it does not, make it do so, because a floor must not silently introduce a yield scaling.

- [ ] **Step 6: Run the tests**

```bash
micromamba run -n shiny python -m pytest tests/test_tier_d_enforcement.py -q
micromamba run -n shiny python -m pytest -q
```

Expected: the new tests pass. **`test_every_macroalga_runs_in_every_region` will now exercise contraindicated pairings** — it asserts `harvest.value >= 0.0`, which a zero-valued tier D Quantity satisfies, so it should still pass. If it does not, read it before changing it.

- [ ] **Step 7: Commit**

```bash
git add src/seagarden_dst/params.py src/seagarden_dst/growth.py params/species/ tests/test_tier_d_enforcement.py
git commit -m "Give every species a lower salinity bound, and stop claiming observations

Only Saccharina had tolerance_floor_psu, so the tool returned confident
yields for the other four at 2.0 psu in the Szczecin Lagoon, where none is
cultivable.

Adding four more floors made contraindication()'s note dishonest: it said
'cultivation failure has been observed at this salinity' for every species
below its floor, and for four of five that asserts a finding nobody made.
floor_basis now distinguishes observed from assumed and the note follows it.
Chorda is the case that matters: its coefficients are a structural analogue
of Fucus and nothing about it has been observed anywhere.

demonstrated_salinity_range is provenance, not a trigger. Specification 7.4
defines tier D as a local finding contradicting the model; extrapolation
beyond a demonstrated range is tier B or C, and conflating the two would make
Fucus 'not cultivable' everywhere except Tagalaht, including LT-coastal."
```

---

## Task 3: *Fucus* stops running on kelp stoichiometry

Design §2.1. *Fucus*'s elemental block is byte-identical to Saccharina's — `nitrogen: 0.010`, `phosphorus: 0.0017`, `carbon: 0.32` — which `../Relevant projects/OLAMUR-solutions-for-SeaGarden.md` §3 labels explicitly *"Kelp DM → 1% N, 0.17% P, 32% C"*. *Chorda* and *Ulva* each carry their own values, Ulva's with a comment noting its N is markedly higher than kelp. Nitrogen removed is compliance item 7 and the ranking's sort key.

**Files:**
- Modify: `params/species/fucus_vesiculosus.yaml`
- Modify: `SeaGarden_DST_functional_specification_v0.1.md` §7.2
- Test: `tests/test_params.py` (extend)

**Interfaces:** none changed. Data only.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_params.py`:

```python
def test_fucus_does_not_silently_carry_kelp_stoichiometry():
    """Fucus's elemental fractions were byte-identical to Saccharina's, which OLAMUR
    labels 'Kelp DM'. Either they are sourced to Fucus, or they say they are assumed."""
    params = default_parameters()
    fucus = params.species["fucus_vesiculosus"]
    kelp = params.species["saccharina_latissima"]

    identical = (
        fucus.elemental.nitrogen == kelp.elemental.nitrogen
        and fucus.elemental.phosphorus == kelp.elemental.phosphorus
        and fucus.elemental.carbon == kelp.elemental.carbon
    )
    assert not identical, (
        "Fucus is running on kelp stoichiometry. Re-source the fractions, or mark them "
        "assumed_from and say so."
    )
```

- [ ] **Step 2: Run it and watch it fail**

```bash
micromamba run -n shiny python -m pytest tests/test_params.py::test_fucus_does_not_silently_carry_kelp_stoichiometry -q
```

Expected: FAIL.

- [ ] **Step 3: Re-source the fractions**

Edit `params/species/fucus_vesiculosus.yaml`:

```yaml
elemental:
  basis: dry_weight
  nitrogen: 0.020         # Fucus vesiculosus tissue N, 1.5-2.5% DW in Baltic literature;
                          # 2.0% taken as the mid-range. NOT the kelp value this file
                          # previously carried (1.0%, OLAMUR D2.3 "Kelp DM"), which was
                          # copied across and never marked. Refine against A3.4.
  phosphorus: 0.0020      # Same provenance caveat as nitrogen.
  carbon: 0.31            # Fucus is slightly lower in C than kelp; 31% DW.
```

If you can obtain a citable *Fucus vesiculosus* stoichiometry source, use its values and cite it here instead of the mid-range. Either way the comment must say which.

- [ ] **Step 4: Amend the specification's §7.2**

The specification says *"Nitrogen and phosphorus reserves tracked via Redfield ratio; carbon fixed at 32% of dry weight."* The word *Redfield* appears exactly once in the repository, in that sentence. The model has one state variable and applies flat tissue fractions post hoc — there is no reserve pool. Redfield is a plankton ratio and is wrong for macroalgae regardless.

Replace that bullet in `SeaGarden_DST_functional_specification_v0.1.md` §7.2 with:

```markdown
- Nitrogen, phosphorus and carbon are fixed tissue fractions applied to harvested dry
  weight, per species, from macroalgal stoichiometry — not Redfield, which is a plankton
  ratio. There is no internal nutrient reserve pool; the growth model carries a single
  state variable. Introducing a quota model is a structural change and is not scheduled.
```

- [ ] **Step 5: Record the remaining anchor gap where it will be seen**

Append to `params/species/fucus_vesiculosus.yaml`'s `notes:` block:

```yaml
  The nitrogen arm of the Tagalaht anchor does not reconcile. Computing every arm from
  the published dry weight gives P 49-53 g against a published 15-120 g (inside), C
  9.22-9.98 kg against 10-13 kg (marginally below), and N against a published 1.4-3.4 kg
  that is several times higher than these fractions produce. A single basis error would
  move all three arms together and does not explain this pattern. Correcting the kelp
  fractions above narrows the nitrogen gap but does not close it. Treat the published
  N figure as unreconciled until it is re-sourced from OLAMUR D3.2 with its basis stated.
```

- [ ] **Step 6: Run everything**

```bash
micromamba run -n shiny python -m pytest -q && micromamba run -n shiny ruff check .
```

Expected: green. Nitrogen values change, so any test asserting an absolute nitrogen figure will move — read it before touching it, and if it encodes a published anchor, report rather than edit.

- [ ] **Step 7: Commit**

```bash
git add params/species/fucus_vesiculosus.yaml tests/test_params.py SeaGarden_DST_functional_specification_v0.1.md
git commit -m "Fucus stops running on kelp stoichiometry; specification drops Redfield

Fucus's elemental block was byte-identical to Saccharina's - 1.0% N, 0.17% P,
32% C - which OLAMUR labels 'Kelp DM'. Chorda and Ulva each carry their own
values, Ulva's with a comment noting its N is markedly higher than kelp. Fucus
had been copied from kelp and never marked. Nitrogen removed is compliance
item 7 and the ranking's sort key.

Specification 7.2 claimed nutrient reserves tracked via Redfield ratio. The
word appears once in the repository, in that sentence; the model has one state
variable and applies flat fractions post hoc, and Redfield is a plankton ratio
and wrong for macroalgae either way. The specification now describes what is
implemented.

The nitrogen arm of the Tagalaht anchor still does not reconcile and the
Fucus file now says so."
```

---

## Task 4: Saccharina uses OLAMUR's published yield model, not the ODE

Design §2.2, resolved from a source already in the repository. Three places in the code and documents say the salinity factor scales a maximum yield; `growth.py:113` multiplies it into the ODE's specific growth rate. `../Relevant projects/OLAMUR-solutions-for-SeaGarden.md` §3 records what D2.3 actually did:

> *"Sugar kelp: modelled purely as a function of salinity — `f_salinity = 1 (S≥25); 1+(S−25)/18 (16≤S<25); S/32 (S<16)`, multiplied by a max yield of 18.4 t-FW/ha from Danish >16 psu sites."*

There is **no growth ODE for Saccharina** in the published model. At DK-belt, `f(18) × 18.4 = 0.611 × 18.4 = 11.24 t FW/ha`. This makes `max_yield_t_fw_ha` the model rather than dead data, and it is the largest numeric move in the plan — which is why it lands before the snapshot.

**Files:**
- Modify: `src/seagarden_dst/params.py` (`SpeciesParams.yield_model`, `ElementalFractions.dry_matter` for macroalgae)
- Modify: `src/seagarden_dst/growth.py` (`salinity_indexed_yield`, dispatch in `harvest_biomass`)
- Modify: `params/species/saccharina_latissima.yaml` and the three other macroalgae
- Test: `tests/test_salinity_yield_model.py` (create)

**Interfaces:**
- Consumes: `SalinityResponse.factor(psu) -> float` (exists), `Quantity`, `Calibration`
- Produces: `growth.salinity_indexed_yield(species, site) -> Quantity` in `t FW/ha`; `SpeciesParams.yield_model: Literal["ode", "salinity_indexed"]` defaulting to `"ode"`

- [ ] **Step 1: Write the failing test**

Create `tests/test_salinity_yield_model.py`:

```python
"""Saccharina follows OLAMUR D2.3's published form, which is not an ODE.

The salinity factor scales a maximum yield of 18.4 t FW/ha from Danish sites above
16 psu. The repository previously multiplied that factor into the growth rate of a
logistic ODE instead, which is a different model: at DK-belt the two differ by a factor
of 3.8, and a third reading (scaling b_max) differs from the second by 49%.
"""

from __future__ import annotations

import pytest

from seagarden_dst import PLACEHOLDER_SITES, default_parameters
from seagarden_dst.growth import harvest_biomass, salinity_indexed_yield


@pytest.fixture(scope="module")
def params():
    return default_parameters()


def test_the_published_form_reproduces_at_the_danish_pilot(params):
    """f(18) x 18.4 = 0.611 x 18.4 = 11.24 t FW/ha."""
    kelp = params.species["saccharina_latissima"]
    site = PLACEHOLDER_SITES["DK-belt"]

    factor = kelp.salinity.factor(site.salinity_psu)
    assert factor == pytest.approx(1.0 + (18.0 - 25.0) / 18.0, rel=1e-9)

    yield_fw = salinity_indexed_yield(kelp, site)
    assert yield_fw.unit == "t FW/ha"
    assert yield_fw.value == pytest.approx(11.24, abs=0.01)


def test_max_yield_is_no_longer_dead_data(params):
    """The parameter was declared, loaded and read by nothing."""
    kelp = params.species["saccharina_latissima"]
    site = PLACEHOLDER_SITES["DK-belt"]
    unscaled = salinity_indexed_yield(kelp, PLACEHOLDER_SITES["DK-belt"])
    assert unscaled.value < kelp.max_yield_t_fw_ha
    assert unscaled.value == pytest.approx(
        kelp.salinity.factor(site.salinity_psu) * kelp.max_yield_t_fw_ha, rel=1e-9
    )


def test_harvest_biomass_dispatches_on_the_yield_model(params):
    """Saccharina goes through the published form; the other three keep the ODE."""
    assert params.species["saccharina_latissima"].yield_model == "salinity_indexed"
    for key in ("fucus_vesiculosus", "ulva", "chorda_filum"):
        assert params.species[key].yield_model == "ode"

    kelp = params.species["saccharina_latissima"]
    site = PLACEHOLDER_SITES["DK-belt"]
    # 1 ha, so kg DW = t FW/ha * dry_matter * 1000
    harvest = harvest_biomass(kelp, site, area_m2=10_000.0)
    expected_kg = 11.24 * kelp.elemental.dry_matter * 1000.0
    assert harvest.value == pytest.approx(expected_kg, rel=1e-3)


def test_the_contraindication_rule_still_wins(params):
    """The published form returns a positive number below 16 psu. Tier D still suppresses
    it - the finding beats the formula, which is the whole point of specification 5.3."""
    kelp = params.species["saccharina_latissima"]
    harvest = harvest_biomass(kelp, PLACEHOLDER_SITES["EE-coastal"], area_m2=10_000.0)
    assert not harvest.calibration.is_reportable
    assert harvest.value == 0.0
```

- [ ] **Step 2: Run it and watch it fail**

```bash
micromamba run -n shiny python -m pytest tests/test_salinity_yield_model.py -q
```

Expected: FAIL on `ImportError: cannot import name 'salinity_indexed_yield'`.

- [ ] **Step 3: Add the schema fields**

In `src/seagarden_dst/params.py`, add to `SpeciesParams`:

```python
    yield_model: Literal["ode", "salinity_indexed"] = Field(
        default="ode",
        description=(
            "Which model produces the harvest. 'ode' is the OLAMUR D3.2 growth "
            "formulation (specification 7.2). 'salinity_indexed' is D2.3's published "
            "form for Saccharina - f_salinity multiplied by max_yield_t_fw_ha, with no "
            "ODE at all."
        ),
    )
```

Add `dry_matter` to `ElementalFractions` if it is not already there for the dry-weight basis (mussel already carries one under a fresh-weight basis — read that field before adding, and reuse it rather than creating a second name).

Add a model validator: `yield_model == "salinity_indexed"` requires both `max_yield_t_fw_ha` and `elemental.dry_matter` to be set. A model that cannot produce a number must fail at load, not mid-analysis.

- [ ] **Step 4: Implement the published form**

In `src/seagarden_dst/growth.py`, add above `harvest_biomass`:

```python
def salinity_indexed_yield(species: SpeciesParams, site: SiteConditions) -> Quantity:
    """OLAMUR D2.3's published Saccharina model: f_salinity x a maximum yield.

    There is no growth ODE in the published form - yield is a function of salinity
    alone, anchored on 18.4 t FW/ha from Danish sites above 16 psu. Returns t FW/ha so
    the figure can be checked directly against the published anchor without passing
    through a dry-matter conversion.
    """
    if species.salinity is None or species.max_yield_t_fw_ha is None:
        raise ValueError(f"{species.key} has no salinity-indexed yield model")

    factor = species.salinity.factor(site.salinity_psu)
    return Quantity(
        value=factor * species.max_yield_t_fw_ha,
        unit="t FW/ha",
        calibration=species.calibration_for(site.region),
    )
```

Then dispatch inside `harvest_biomass`, after the contraindication guard and before `simulate`:

```python
    calibration = species.calibration_for(site.region)

    if species.yield_model == "salinity_indexed":
        fresh_t_per_ha = salinity_indexed_yield(species, site).value
        kg = fresh_t_per_ha * species.elemental.dry_matter * 1000.0 * (area_m2 / 10_000.0)
        return Quantity(value=kg, unit="kg DW", calibration=calibration)

    trajectory = simulate(species, site)
    kg = trajectory.final_biomass * area_m2 / 1000.0
    return Quantity(value=kg, unit="kg DW", calibration=calibration)
```

- [ ] **Step 5: Set the parameters**

`params/species/saccharina_latissima.yaml`:

```yaml
yield_model: salinity_indexed   # OLAMUR D2.3's published form. The growth: block below
                                # is retained for reference and is NOT used to produce
                                # the harvest for this species.
```

and under `elemental:`:

```yaml
  dry_matter: 0.10        # ASSUMED. Saccharina DM is typically 10-12% of fresh weight;
                          # OLAMUR publishes a dry-matter figure for mussels but not for
                          # kelp. Only affects the DW conversion, not the 18.4 t FW/ha
                          # anchor the model is checked against. Refine against A3.4.
```

Add `dry_matter` to the other three macroalgae too — spec §7.1 commits the tool to a `t FW ha⁻¹` output and it cannot be produced without one. Mark each `ASSUMED` with its range, as above.

Also change the DK-belt calibration entry from `tier: B` to `tier: C`: no coefficient in the file is fitted to Danish data, and a published yield figure from Danish sites is a literature prior, not a local calibration. Update its `note:` to say so.

- [ ] **Step 6: Run the tests**

```bash
micromamba run -n shiny python -m pytest tests/test_salinity_yield_model.py -q
micromamba run -n shiny python -m pytest -q
```

Expected: the new file passes. **`test_sugar_kelp_is_fine_in_the_danish_belt` asserts only `> 0.0` and should still pass.** `test_the_january_stand_in_understated_the_harvest` no longer exists. If `test_the_autumn_deployment_window_ships` or the trajectory test in `tests/test_cultivation_window.py` fails, that is expected — Saccharina no longer runs the ODE, so a test asserting its trajectory is now testing a model the species does not use. Convert it to assert on *Fucus* instead and note the change in the commit.

- [ ] **Step 7: Commit**

```bash
git add src/seagarden_dst/params.py src/seagarden_dst/growth.py params/species/ tests/
git commit -m "Saccharina follows OLAMUR D2.3's published yield model, not the ODE

Three places said the salinity factor scales a maximum yield; growth.py
multiplied it into the ODE's specific growth rate. The source was already in
this repository: OLAMUR models sugar kelp purely as a function of salinity,
multiplied by a max yield of 18.4 t FW/ha from Danish sites above 16 psu.
There is no growth ODE for this species in the published form.

At DK-belt the readings differed by a factor of 5.6: 36.90 g DW/m2 with the
factor in the rate, 140.13 post-multiplying the harvest, 208.55 scaling
b_max, against a published 11.24 t FW/ha. max_yield_t_fw_ha was declared,
loaded and read by nothing; it is now the model.

The contraindication rule still wins below 16 psu - the finding beats the
formula, which is what specification 5.3 is for.

DK-belt moves from tier B to C: no coefficient in the file is fitted to
Danish data, and a published yield figure from Danish sites is a literature
prior, not a local calibration."
```

---

## Task 5: The Tagalaht anchor becomes data, and `b_max` stops being circular

Design §3.1. The anchor lives in prose in two documents and in a test docstring. `b_max: 5200.0` is set from *the anchor's own upper bound*, so the model cannot overshoot the range it is validated against — the check is circular. This task does **not** fit anything; fitting waits for package D1 and real forcing.

**Files:**
- Modify: `params/species/fucus_vesiculosus.yaml`
- Modify: `src/seagarden_dst/params.py` (`anchors` schema)
- Test: `tests/test_params.py` (extend)

**Interfaces:**
- Produces: `SpeciesParams.anchors: list[Anchor] | None`, where `Anchor` carries `quantity`, `low`, `high`, `unit`, `basis`, `source`, `cycle`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_params.py`:

```python
def test_the_tagalaht_anchor_is_data_with_a_stated_basis():
    """The only published anchor the SE Baltic parameterisation has lived in prose in two
    documents and a test docstring, with its basis unstated - which is why the nitrogen
    arm could be out by several times without anyone being able to say against what."""
    fucus = default_parameters().species["fucus_vesiculosus"]
    assert fucus.anchors, "Fucus carries no anchors block"

    quantities = {a.quantity for a in fucus.anchors}
    assert {"dry_weight", "carbon", "nitrogen", "phosphorus"} <= quantities

    for anchor in fucus.anchors:
        assert anchor.basis, f"{anchor.quantity} anchor has no stated basis"
        assert anchor.source
        assert anchor.low <= anchor.high


def test_b_max_is_not_read_off_the_anchor_it_is_validated_against():
    """b_max = 5200 was the anchor's own upper bound, so the model could not overshoot
    the range it is checked against. Either it is independently sourced, or it says it
    is assumed - silence is what made the circularity invisible."""
    fucus = default_parameters().species["fucus_vesiculosus"]
    anchor = next(a for a in fucus.anchors if a.quantity == "dry_weight")
    if fucus.growth.b_max == anchor.high:
        assert fucus.growth.b_max_basis == "assumed_from_anchor", (
            "b_max equals the anchor's upper bound and does not say so"
        )
```

- [ ] **Step 2: Run it and watch it fail**

```bash
micromamba run -n shiny python -m pytest tests/test_params.py -q -k anchor
```

Expected: FAIL — no `anchors` attribute.

- [ ] **Step 3: Add the schema**

In `src/seagarden_dst/params.py`:

```python
class Anchor(BaseModel):
    """A published measurement the parameterisation is checked against.

    Anchors are data rather than prose because the basis is what makes them usable: a
    figure quoted per cage means something different from the same figure per square
    metre, and the Tagalaht nitrogen arm could not be reconciled precisely because
    nobody had written the basis down.
    """

    quantity: Literal["dry_weight", "carbon", "nitrogen", "phosphorus"]
    low: float
    high: float
    unit: str
    basis: str = Field(description="Per cage or per m2, DW or FW, cage area, cycle length")
    source: str
    reconciles: bool = Field(
        default=True,
        description="False where the model cannot currently reproduce this arm.",
    )
```

Add `anchors: list[Anchor] | None = None` and `b_max_basis: str | None` (on `GrowthParams`).

- [ ] **Step 4: Record what is actually known**

In `params/species/fucus_vesiculosus.yaml`:

```yaml
anchors:
  # From specification 7.2 and ../Relevant projects/OLAMUR-solutions-for-SeaGarden.md:19.
  # The basis below is TRANSCRIBED FROM THOSE SUMMARIES, not read from OLAMUR D3.2
  # itself. Re-source from D3.2 and correct if it differs - the nitrogen arm in
  # particular does not reconcile and the basis is the first suspect.
  - quantity: dry_weight
    low: 4800.0
    high: 5200.0
    unit: g DW/m2
    basis: per 6 m2 cage, April-October cycle
    source: OLAMUR D3.2, Tagalaht Bay
  - quantity: carbon
    low: 10.0
    high: 13.0
    unit: kg C
    basis: per 6 m2 cage, April-October cycle
    source: OLAMUR D3.2, Tagalaht Bay
    reconciles: false        # model gives 9.22-9.98 kg, marginally below
  - quantity: nitrogen
    low: 1.4
    high: 3.4
    unit: kg N
    basis: per 6 m2 cage, April-October cycle
    source: OLAMUR D3.2, Tagalaht Bay
    reconciles: false        # model is several times below; see notes
  - quantity: phosphorus
    low: 15.0
    high: 120.0
    unit: g P
    basis: per 6 m2 cage, April-October cycle
    source: OLAMUR D3.2, Tagalaht Bay
```

and under `growth:`:

```yaml
  b_max: 5200.0
  b_max_basis: assumed_from_anchor   # This is the anchor's own upper bound, so the model
                                     # cannot overshoot the range it is validated
                                     # against. Re-source from A3.2 as-built line
                                     # loading, or from a standing-stock ceiling in the
                                     # Fucus literature. Until then the dry-weight anchor
                                     # is not an independent check.
```

- [ ] **Step 5: Run and commit**

```bash
micromamba run -n shiny python -m pytest -q && micromamba run -n shiny ruff check .
git add params/species/fucus_vesiculosus.yaml src/seagarden_dst/params.py tests/test_params.py
git commit -m "The Tagalaht anchor becomes data; b_max declares its circularity

The only published anchor the SE Baltic parameterisation has lived in prose
in two documents and a test docstring, with its basis unstated - which is why
the nitrogen arm could be several times out without anyone being able to say
against what. It is now an anchors: block with the basis, the source and a
reconciles flag per arm. Carbon and nitrogen are marked as not reconciling.

b_max was 5200, the anchor's own upper bound, so the model could not
overshoot the range it is validated against. It now says so. Nothing is
fitted here - that waits for package D1 and real forcing."
```

---

## Task 6: The three assessment thresholds move to `params/`

Design §3.4. `0.35`, `0.5` and the supra-optimal decline width decide suitability verdicts from Python defaults, against the specification's own rule that coefficients live in `params/`. One binds tightly: Ulva's shipped yields are 0.461–0.771 kg DW/m² against a 0.5 floor. Blue mussel is routed round both by `suitability.py:150` because it is shellfish.

The values do not change. This is a relocation, and the test is that the numbers are identical.

**Files:**
- Create: `params/assessment.yaml`
- Modify: `src/seagarden_dst/params.py` (`AssessmentParams`, loader)
- Modify: `src/seagarden_dst/suitability.py:127,143,199`
- Modify: `src/seagarden_dst/growth.py:56` (`f_temperature`'s hard-coded `3.0`)
- Test: `tests/test_params.py` (extend)

**Interfaces:**
- Produces: `ParameterSet.assessment: AssessmentParams` with `salinity_factor_floor: float`, `yield_floor_kg_dw_per_m2: float`; `GrowthParams.upper_temp_decline_c: float`

- [ ] **Step 1: Write the failing test**

```python
def test_assessment_thresholds_are_data_not_code():
    """Specification 1's premise is that coefficients live in params/. These three decide
    suitability verdicts and lived in Python defaults."""
    import inspect

    from seagarden_dst import suitability

    source = inspect.getsource(suitability)
    assert "0.35" not in source, "salinity factor floor still hard-coded"
    assert "= 0.5" not in source, "yield floor still hard-coded"

    assessment = default_parameters().assessment
    assert assessment.salinity_factor_floor == 0.35
    assert assessment.yield_floor_kg_dw_per_m2 == 0.5


def test_the_yield_floor_message_does_not_claim_the_user_set_it():
    """Specification 5.2 says the floor is user-set. No user can set it. Until package E
    plumbs a control, the text must say 'default' rather than 'set for this assessment'."""
    import inspect

    from seagarden_dst import suitability

    assert "set for this assessment" not in inspect.getsource(suitability)
```

- [ ] **Step 2: Run it and watch it fail**

```bash
micromamba run -n shiny python -m pytest tests/test_params.py -q -k assessment
```

- [ ] **Step 3: Create `params/assessment.yaml`**

```yaml
# Thresholds that decide a suitability verdict.
#
# These lived as Python defaults, against specification section 1's premise that
# coefficients are data. They are ASSUMED - no source fits any of them - and they are
# consequential: Ulva's shipped yields are 0.461-0.771 kg DW/m2 against the 0.5 floor,
# so the floor decides the verdict for one of the two Application-Form macroalgae at
# every placeholder site. Blue mussel is routed round both by the banded yield model.

salinity_factor_floor: 0.35        # ASSUMED. Below this fraction of unscaled yield the
                                   # environment constraint reads MARGINAL.
yield_floor_kg_dw_per_m2: 0.5      # ASSUMED. Specification 5.2 calls this user-set;
                                   # no control exists yet. Package E, decision D4.
```

- [ ] **Step 4: Load it and use it**

Add `AssessmentParams` to `params.py`, load `params/assessment.yaml` in `default_parameters()` alongside the species and methods, and expose it as `ParameterSet.assessment`. Follow the loading pattern already used for `methods.yaml` exactly — do not introduce a second way of reading YAML.

Change the three call sites in `suitability.py` to take their values from the loaded parameters rather than from function defaults, and change the message at `suitability.py:166-167` from `"floor set for this assessment"` to `"default floor"`.

Add `upper_temp_decline_c: float = 3.0` to `GrowthParams`, add it to each species YAML with an `# ASSUMED` comment, and replace the literal `3.0` in `f_temperature`'s `np.exp(-((excess / 3.0) ** 2))` with the parameter, threaded through from `simulate`.

- [ ] **Step 5: Prove it is a pure relocation**

```bash
micromamba run -n shiny python -m pytest -q
```

Expected: **every test passes unchanged.** The values are identical, so no verdict and no number may move. If anything moves, the relocation is not faithful — find the difference before proceeding.

- [ ] **Step 6: Commit**

```bash
git add params/assessment.yaml src/seagarden_dst/ tests/test_params.py
git commit -m "Assessment thresholds move from Python defaults to params/

0.35, 0.5 and the supra-optimal temperature decline width decide suitability
verdicts and lived as function defaults, against specification section 1's
premise that coefficients are data and recalibration is a data change rather
than a release.

One of them binds tightly: Ulva's shipped yields are 0.461-0.771 kg DW/m2
against the 0.5 floor, so it decides the verdict for one of the two
Application-Form macroalgae at every placeholder site. All three are marked
ASSUMED, because no source fits any of them.

The values are unchanged and the suite passes unmodified, which is the proof
that this is a relocation and not a change.

The growth-viability message no longer says the floor was 'set for this
assessment'. Specification 5.2 calls it user-set; no control exists, and
package E carries it."
```

---

## Task 7: The false sentences, the stale figure, and the missing stub rows

Four sentences in the repository assert a `mu_max` re-tune that never happened, and a fourth figure — `3.61 µmol N/L` — is not producible by any shipped species: it came from the January–June stand-in window retired on 13 Sep 2026, and was written into `forcing.py`'s docstring by the same commit that retired it.

**Files:**
- Modify: `README.md:146` and its Testing section, `src/seagarden_dst/forcing.py:167-170`, `tests/test_cultivation_window.py:140`
- Modify: `SeaGarden_DST_functional_specification_v0.1.md` §14 (key-person row)

- [ ] **Step 1: Find them all**

```bash
grep -rn "re-tune\|retune\|3\.61" README.md src/ tests/ params/ SeaGarden_DST_functional_specification_v0.1.md | grep -v pycache
```

Expected: three `re-tune` claims and the `3.61` occurrences. The design document is allowed to contain both — it discusses them.

- [ ] **Step 2: Correct each**

- `README.md:146` and `forcing.py:170`: *"Fixing it moves the Tagalaht anchor, so the `mu_max` re-tune goes with it"* → *"Fixing it moves the modelled yields; `mu_max` has never been fitted to the anchor, and the fit itself is package D1's."*
- `tests/test_cultivation_window.py:140`: the same claim inside the strict `xfail` reason → the same correction.
- Every `3.61` outside the design document → the correct pair. On 1 April at DK-belt the shipped windows give **3.15** (Saccharina, Oct–Jun) and **5.00** (*Fucus* and *Chorda*, April starts). Two values, not three.
- README Testing section: add one line recording that commit `6d36187`'s message contains both the re-tune claim and the `3.61` figure, is published history and cannot be amended, and is superseded.

- [ ] **Step 3: Add the two missing README stub rows**

Into the "What is stubbed, and what unblocks it" table:

```markdown
| Scenario comparison panel (§5.4) | `scenarios.compare()` has no UI caller | A comparison module in `app/modules/`; deferred past the data-layer work |
| Human-use conflict screening (§5.1) | `SiteContext.activities` / `.protection` unused | EMODnet/HELCOM vectors — design packages C1 and F1 |
```

- [ ] **Step 4: Add the key-person row to the specification's §14**

```markdown
| The annual data refresh is one person's manual task | The data layer silently ages, then the tool ships numbers nobody can date | Refresh runbook written for a stranger (design §4.1); credential held institutionally; each refresh archived under a DOI so the layer survives the script; scheduled source-probe that fails loudly |
```

- [ ] **Step 5: Verify and commit**

```bash
grep -rn "re-tune\|retune\|3\.61" README.md src/ tests/ params/ | grep -v pycache
```

Expected: no output.

```bash
micromamba run -n shiny python -m pytest -q
git add -A
git commit -m "Correct four false claims and a figure that no longer exists

Three sentences asserted a mu_max re-tune that never happened - mu_max
carries its initial value and the model has never met the Tagalaht range.
The fourth, in commit 6d36187's message, is published history and can only
be recorded as superseded.

3.61 umol N/L is not producible by any shipped species. It came from the
January-June stand-in window retired on 13 September 2026, and was written
into forcing.py's docstring by the same commit that retired it, from which
it propagated into two revisions of the design. On 1 April at DK-belt the
shipped windows give 3.15 and 5.00 - two values, not three. A measured
number belongs in a test, not in prose.

Two capabilities that look delivered are added to the README's stub table,
and specification 14 gains the key-person row the refresh design requires."
```

---

## Task 8: The golden-file snapshot

The regression net for everything that follows. It goes in **after** A0 and **before** A: putting it first, as an earlier revision of the design did, would have frozen tasks 1–6's defects as the project's definition of correct.

**Files:**
- Create: `tests/test_golden_snapshot.py`, `tests/golden/assessments.json`

- [ ] **Step 1: Write the snapshot test**

```python
"""The regression net.

Captures assess_site() and scenarios.compare() for every site and species, so that a
change which moves a number has to say so in a diff. Every package after this one
should produce an empty diff here unless its plan says otherwise - package A is the
one that says otherwise.

To regenerate deliberately: micromamba run -n shiny python -m pytest \\
    tests/test_golden_snapshot.py --snapshot-update
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from seagarden_dst import PLACEHOLDER_SITES, SiteContext, assess_site

GOLDEN = Path(__file__).parent / "golden" / "assessments.json"


def _capture() -> dict:
    out = {}
    for region in sorted(PLACEHOLDER_SITES):
        result = assess_site(SiteContext.from_region(region))
        out[region] = {
            "excluded": {k: v for k, v in sorted(result.excluded.items())},
            "ranked": [
                {
                    "species": option.species_key,
                    "harvest": round(option.harvest.value, 6),
                    "tier": option.harvest.calibration.tier.value,
                    "nitrogen": round(option.nitrogen_value, 6),
                }
                for option in result.ranked
            ],
        }
    return out


def test_assessments_match_the_golden_file(pytestconfig):
    current = _capture()
    if pytestconfig.getoption("--snapshot-update", default=False):
        GOLDEN.parent.mkdir(exist_ok=True)
        GOLDEN.write_text(json.dumps(current, indent=2, sort_keys=True), encoding="utf-8")
        pytest.skip("golden file regenerated")

    assert GOLDEN.exists(), "run with --snapshot-update to create the golden file"
    expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert current == expected, (
        "An assessment moved. If deliberate, explain the diff in the commit message and "
        "regenerate with --snapshot-update. If not, you have found a regression."
    )
```

Register the flag in `tests/conftest.py` (create it if absent):

```python
def pytest_addoption(parser):
    parser.addoption(
        "--snapshot-update",
        action="store_true",
        default=False,
        help="Regenerate golden files instead of asserting against them.",
    )
```

Adjust the captured fields to whatever `SpeciesOption` actually exposes — read `src/seagarden_dst/contracts.py` first and use the real attribute names.

- [ ] **Step 2: Generate the baseline**

```bash
micromamba run -n shiny python -m pytest tests/test_golden_snapshot.py --snapshot-update -q
micromamba run -n shiny python -m pytest tests/test_golden_snapshot.py -q
```

Expected: skipped, then passed.

- [ ] **Step 3: Read the golden file before committing it**

```bash
cat tests/golden/assessments.json
```

Every sub-floor site must show sugar kelp in `excluded`, not in `ranked`. If it does not, tasks 1–2 did not land and the snapshot would freeze the leak. **Stop and report.**

- [ ] **Step 4: Commit**

```bash
git add tests/test_golden_snapshot.py tests/golden/ tests/conftest.py
git commit -m "Golden-file snapshot of every assessment, taken after A0

The regression net for the data-layer work. A change that moves a number now
has to say so in a diff.

Taken after A0 and not before it, deliberately: an earlier revision of the
design put it first and declared any later movement a regression, which would
have frozen the tier D leak, the kelp stoichiometry and the salinity model
as the project's own definition of correct."
```

---

## Task 9: The `ForcingSource` seam

Package A, first half. `daily_forcing()` is a module-level function over a hard-coded dictionary. The data layer needs to substitute a gridded implementation without any model importing it.

**Files:**
- Modify: `src/seagarden_dst/forcing.py`
- Modify: `src/seagarden_dst/growth.py:104`, `src/seagarden_dst/contracts.py:56,60`, `src/seagarden_dst/__init__.py`
- Test: `tests/test_forcing_source.py` (create)

**Interfaces:**
- Produces: `ForcingSource` Protocol with `conditions_for(region: str) -> SiteConditions` and `daily_forcing(site, window) -> tuple[np.ndarray, ...]`; `PlaceholderForcing` implementing it; `DEFAULT_FORCING: ForcingSource`

- [ ] **Step 1: Write the failing test**

```python
"""The seam the data layer substitutes into.

`GriddedForcing` will implement this protocol in package D. Nothing in growth,
shellfish, nutrients or suitability may import a concrete forcing implementation.
"""

from __future__ import annotations

import numpy as np

from seagarden_dst.forcing import DEFAULT_FORCING, ForcingSource, PlaceholderForcing


def test_placeholder_satisfies_the_protocol():
    assert isinstance(PlaceholderForcing(), ForcingSource)


def test_the_default_source_is_the_placeholder():
    assert isinstance(DEFAULT_FORCING, PlaceholderForcing)


def test_a_stub_source_can_be_substituted():
    """The point of the seam: a source the core has never heard of must work."""

    class FlatForcing:
        def conditions_for(self, region):
            return DEFAULT_FORCING.conditions_for(region)

        def daily_forcing(self, site, window):
            days = np.arange(1.0, 101.0)
            return days, np.full(100, 200.0), np.full(100, 12.0), np.full(100, 5.0)

    assert isinstance(FlatForcing(), ForcingSource)


def test_no_model_module_imports_a_concrete_source():
    """The dependency direction is the whole point."""
    import inspect

    from seagarden_dst import nutrients, shellfish, suitability

    for module in (shellfish, nutrients, suitability):
        source = inspect.getsource(module)
        assert "PLACEHOLDER_SITES" not in source, f"{module.__name__} reaches for the stub"
```

- [ ] **Step 2: Run it and watch it fail**

```bash
micromamba run -n shiny python -m pytest tests/test_forcing_source.py -q
```

- [ ] **Step 3: Add the protocol**

In `src/seagarden_dst/forcing.py`:

```python
from typing import Protocol, runtime_checkable


@runtime_checkable
class ForcingSource(Protocol):
    """Where site conditions and seasonal forcing come from.

    The interface is deliberately narrow - two methods - because swapping the
    placeholder for the section 6 data layer must touch nothing in growth, shellfish,
    nutrients or suitability.
    """

    def conditions_for(self, region: str) -> SiteConditions: ...

    def daily_forcing(
        self, site: SiteConditions, window: tuple[int, int]
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]: ...


class PlaceholderForcing:
    """The scaffold's invented conditions. Not measurements - see PLACEHOLDER_SITES."""

    def conditions_for(self, region: str) -> SiteConditions:
        return PLACEHOLDER_SITES[region]

    def daily_forcing(self, site, window):
        return daily_forcing(site, window)


DEFAULT_FORCING: ForcingSource = PlaceholderForcing()
```

Keep the module-level `daily_forcing` function: `PlaceholderForcing` delegates to it, and package D replaces the class rather than the function.

- [ ] **Step 4: Migrate the four call sites**

`growth.py:104`, `contracts.py:56`, `contracts.py:60`, and the re-export in `__init__.py`. Each takes its forcing from an injected `ForcingSource` defaulting to `DEFAULT_FORCING` rather than importing the module function directly. **Name all four in the commit message** — the design requires it.

- [ ] **Step 5: Run everything**

```bash
micromamba run -n shiny python -m pytest -q && micromamba run -n shiny ruff check .
```

Expected: all green **including the golden snapshot** — this task is structural and must move no number. If the snapshot diffs, the refactor is not faithful.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "Introduce the ForcingSource seam

daily_forcing() was a module-level function over a hard-coded dictionary,
so the section 6 data layer had nothing to substitute into. ForcingSource is
a two-method protocol; PlaceholderForcing implements it over the existing
invented conditions; GriddedForcing implements it in package D.

Four call sites migrated: growth.py:104, contracts.py:56, contracts.py:60,
and the re-export in __init__.py.

The golden snapshot is unchanged, which is the proof that this moved no
number."
```

---

## Task 10: Calendar-day nutrients, and the test bound this moves

Package A, second half, and the one task in this plan that deliberately moves numbers.

The placeholder computes its drawdown as `np.linspace(1.0, 0.45, days.size)` — indexed by position in the cultivation window rather than by date. Nitrogen is a property of the question asked: on 1 April at DK-belt the code returns 3.15 for Saccharina's window and 5.00 for the April starts, a 59% spread on the same day at the same site.

**This lowers every ODE yield**, because within any shipped window the season term never reaches zero: April–October spans 0.450–0.891 rather than 0.450–1.000. Measured: *Fucus* at EE-coastal **3446 → 2797 g DW/m²**, below the hard `assert 3000.0`; *Ulva* −55%; *Chorda* −43%; four growth-viability verdicts flip. So this task resets that bound, in the same commit, with the new value stated.

**Files:**
- Modify: `src/seagarden_dst/forcing.py` (`daily_forcing`)
- Modify: `tests/test_growth.py:65-73`, `tests/test_cultivation_window.py` (the xfail)
- Modify: `tests/golden/assessments.json` (regenerated, diff explained)

- [ ] **Step 1: Make the xfail the target**

`tests/test_cultivation_window.py::test_nutrient_forcing_is_a_property_of_the_site_not_the_query` is a **strict** xfail. When this task lands it XPASSes and the suite fails until the marker is removed — which is the design. Remove the `@pytest.mark.xfail` decorator and its reason as part of Step 3, not before.

- [ ] **Step 2: Re-index by calendar day**

In `daily_forcing`, replace the drawdown:

```python
    # Nutrients by calendar day, not by position in the window. The previous
    # `np.linspace(1.0, 0.45, days.size)` spread a fixed drawdown across however many
    # days the window contained, so nitrogen was a property of the question asked: on
    # 1 April at DK-belt it returned 3.15 for an Oct-Jun window and 5.00 for an April
    # start. Highest in winter and lowest at midsummer is the Baltic pattern - winter
    # accumulation, spring-bloom drawdown.
    #
    # ASSUMED, not sourced, and replaced wholesale by the section 6 climatologies.
    # Note it is NOT amplitude-preserving within a window: the season term reaches 0
    # only at midwinter, so April-October spans 0.450-0.891 of din_umol_l rather than
    # 0.450-1.000. That is why this change lowers every ODE yield.
    din = site.din_umol_l * (1.0 - 0.55 * season)
```

- [ ] **Step 3: Retire the xfail and reset the anchor bound**

Remove the `xfail` marker. Then in `tests/test_growth.py`:

```python
def test_fucus_reaches_the_tagalaht_reference_range(params):
    """A loose guard on the only published anchor the parameterisation has.

    The model does not meet it. With calendar-day nutrient forcing Fucus returns
    2797 g DW/m2 against a published 4800-5200 (params/species/fucus_vesiculosus.yaml,
    anchors:). mu_max has never been fitted to the anchor, and b_max is set from the
    anchor's own upper bound, so the range is not an independent check either.

    The bound below is a regression guard around the current value, NOT the published
    range. Package D1 attempts the fit against real forcing and narrows it - or
    documents the failure. Do not narrow it here.
    """
    fucus = params.species["fucus_vesiculosus"]
    trajectory = simulate(fucus, PLACEHOLDER_SITES["EE-coastal"])
    assert 2500.0 <= trajectory.final_biomass <= 5200.0, (
        f"Final biomass {trajectory.final_biomass:.0f} g DW/m2 is outside the regression "
        "guard. This is not the published range - see the docstring and package D1."
    )
```

- [ ] **Step 4: Run, and read the snapshot diff before regenerating**

```bash
micromamba run -n shiny python -m pytest -q
micromamba run -n shiny python -m pytest tests/test_golden_snapshot.py --snapshot-update -q
git diff tests/golden/assessments.json
```

**Read the whole diff.** Every macroalgal harvest should fall; Saccharina should not move at all, because task 4 took it off the ODE. Four growth-viability verdicts should flip, one of them *Ulva* at LT-coastal. If anything else moved — a tier, an exclusion, a shellfish number — that is a regression and not this change. Stop and investigate.

- [ ] **Step 5: Commit, with the diff explained**

```bash
git add -A
git commit -m "Index the placeholder nutrient field by calendar day

The drawdown was np.linspace(1.0, 0.45, days.size) - spread across however
many days the window contained - so nitrogen was a property of the question
asked rather than of the site. On 1 April at DK-belt the same site returned
3.15 umol N/L for sugar kelp's Oct-Jun window and 5.00 for the April starts,
a 59% spread on one day. The strict xfail that recorded this is retired here;
it XPASSes and would fail the suite otherwise, which was its purpose.

This lowers every ODE yield and the design says why: the formula is not
amplitude-preserving within a window, because the season term reaches zero
only at midwinter, so April-October spans 0.450-0.891 rather than
0.450-1.000. Fucus at EE-coastal falls 3446 to 2797 g DW/m2, Ulva -55%,
Chorda -43%, and four growth-viability verdicts flip including Ulva at
LT-coastal. Saccharina does not move - it no longer runs the ODE.

The Tagalaht guard is reset to 2500-5200 and its docstring now says plainly
that this is a regression guard around the current value and not the
published range. Package D1 attempts the fit against real forcing.

The golden snapshot is regenerated and its diff is the above."
```

---

## Self-Review

**Spec coverage.** Against design §8.1's traceability table, the rows this plan owns: §3.2 tier D → task 1; §3.3 floors → task 2; §2.1 elemental fork → task 3; §2.2 salinity relocation → task 4; §3.1 anchors and `b_max` → task 5; §3.4 thresholds → task 6; §3.1 false sentences and README rows, §4.1 key-person row → task 7; §9 snapshot → task 8; §5 four call sites → task 9; §5.1 DIN shape and anchor bound → task 10. A0 clause (12), the DK-belt tier re-examination, lands in task 4 step 5.

**Not covered here, by design:** §2.3 carrying capacity is a decision with no package until it is taken; §3.3's `demonstrated_salinity_range` judgements are a scientific review per species rather than an automated check — task 2 records them and a human signs them off; A0 clause (5)'s `t FW/ha` test is task 4's `test_the_published_form_reproduces_at_the_danish_pilot`.

**Placeholders:** none. Every code step carries the code. Where a step says "read the existing pattern first" — task 1 step 4, task 6 step 4, task 8 step 1 — that is because the file's existing shape governs and inventing a second shape would be the defect.

**Type consistency:** `salinity_indexed_yield` returns `Quantity` in `t FW/ha` (tasks 4, and asserted in 4). `floor_basis` is `Literal["observed","assumed"]` in tasks 2 and used in 2. `anchors` is `list[Anchor]` in task 5 and read in task 5's tests and task 10's docstring. `ForcingSource` has exactly `conditions_for` and `daily_forcing` in tasks 9 and 10.

**One ordering constraint that must not be broken:** tasks 1–7 all precede task 8, and task 10 follows it. Task 4 is the largest numeric move and *must* be inside the snapshot baseline; task 10 is the only movement outside it and carries its own explained diff.
