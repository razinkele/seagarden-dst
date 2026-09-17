# Package C-c2 — The Catalogue Probe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the monthly probe's stdlib HTTP HEAD against a product landing page with `copernicusmarine.describe(dataset_id=...)`, so the job detects a retired `dataset_id` and a drifted provenance `version` — the two events it exists to catch and currently cannot see.

**Architecture:** One new module, `refresh/sources/catalogue.py`, wraps `describe()` behind an injected callable and classifies the outcome into four states. `cmems.py` gains a shared `catalogue_probe()` so the four layers keep a one-line `probe()` instead of four copy-pasted bodies — the copy-paste shape that produced C-c1's `version="202303"` bug. `reachability.py` and its tests are deleted rather than left as tested-but-uncalled code. `ProbeResult` gains a `status` field so "retired dataset", "version drift" and "network down" stop sharing one boolean.

**Tech Stack:** Python 3.11, `copernicusmarine>=2.4` (installed: 2.4.0), pydantic v2, pytest, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-15-package-c-refresh-tooling-design.md` — C§8.2 is the binding section; C§11.1 supplies the `(dataset_id, version)` table.

## Global Constraints

- **`describe()` takes no credential and must be given none.** C§8.2: "`describe()` accepts no `username`, `password` or `credentials_file` — `get()` and `subset()` accept all three". The two `COPERNICUSMARINE_SERVICE_*` secrets in `source-probe.yml` are read by nothing and are struck in Task 3.
- **Nothing in `refresh/layer.py`, `refresh/registry.py`, `refresh/sources/catalogue.py` or `refresh/sources/cmems.py` may import `copernicusmarine` or `xarray` at module scope.** The reason has changed but the rule has not: the probe job now *does* install `[spatial]`, so the old rationale (bare install) is dead, but the default test suite runs `-m 'not engines and not e2e and not spatial'` and `-m` deselects *after* collection — a module-scope import therefore breaks collection regardless of markers. Import inside the function that needs it.
- **The probe blocks no pull request.** C§8.2: `source-probe.yml` stays separate from `ci.yml`, `schedule` + `workflow_dispatch` only, never `push` or `pull_request`.
- **No test in this plan touches the network.** Every test drives `describe` through the injected seam. C§8.2 makes the monthly job the live test; a networked CI test would make every run hostage to Copernicus, which is the thing the workflow separation exists to prevent.
- **One dead source must not fail the job for the other four.** `probe()` returns a `ProbeResult`; it never raises.
- **The recorded `(dataset_id, version)` pairs are C§11.1's and are not editable by this package:** `copernicus_phy` / `cmems_mod_bal_phy_my_P1M-m` / `202303`; `copernicus_bgc` / `cmems_mod_bal_bgc_my_P1M-m` / `202303`; `copernicus_bgc_light` / `cmems_mod_bal_bgc_my_P1D-m` / `202303`; `copernicus_wav` / `cmems_mod_bal_wav_my_PT1H-i` / `202411`.
- **`emodnet_bathy` stays unregistered and `check_registered_names` stays `<=`.** It is not in this package. `registry.py`'s docstring currently claims "C-c2's first task tightens it to equality" — that claim is wrong and Task 3 corrects it; tightening before the layer exists reddens the suite at import, because `set(LAYER_NAMES) - set(REGISTRY)` is `{'emodnet_bathy'}`.
- Run tests with `micromamba run -n shiny python -m pytest`. Never create a virtualenv.

## Empirical findings this plan rests on

Run against the live catalogue with `copernicusmarine` 2.4.0 on 2026-09-17. **Do not re-derive these by reading the library source; they were established by execution and the plan's code depends on them.**

1. `describe(dataset_id=...)` **raises `DatasetNotFound` for an unknown id even though `raise_on_error` defaults to `False`.** The flag governs bulk catalogue parsing, not the targeted lookup. Reading the signature gives the wrong answer here.
2. `DatasetNotFound` is importable as **`copernicusmarine.DatasetNotFound`** (it lives in `copernicusmarine.catalogue_parser.models`).
3. `describe()` returns a `CopernicusMarineCatalogue`; versions are reached as `catalogue.products[*].datasets[*].versions[*].label`.
4. **No credential was supplied and every call succeeded.**
5. All four recorded versions match the live catalogue today, and `show_all_versions` changes nothing — each dataset serves exactly one version.

## File Structure

| File | Responsibility |
|---|---|
| `src/seagarden_dst/refresh/sources/catalogue.py` | **New.** `dataset_status()` — ask the catalogue about one `dataset_id`, classify into four states, never raise. The only module that knows `describe()`'s return shape. |
| `src/seagarden_dst/refresh/sources/cmems.py` | **Modify.** Add `catalogue_probe()`, the one place a `ProbeResult` is assembled for a Copernicus layer. Rewrite the module docstring's dead R3 rationale. |
| `src/seagarden_dst/refresh/layer.py` | **Modify.** `ProbeResult` gains `status`, with a validator forbidding `status`/`reachable` disagreement. |
| `src/seagarden_dst/refresh/sources/{phy,bgc,bgc_light,wav}.py` | **Modify.** `probe()` delegates to `cmems.catalogue_probe`; constructor parameter `reachability_opener` becomes `describe`. |
| `src/seagarden_dst/refresh/sources/reachability.py` | **Delete.** Its last caller goes in Task 2. Recover with `git show 3a57b1b:src/seagarden_dst/refresh/sources/reachability.py` if the EMODnet probe wants it — but that probe is a WCS `GetCapabilities` parse, not a HEAD, so it likely will not. |
| `tests/test_refresh_reachability.py` | **Delete**, replaced by `tests/test_refresh_catalogue.py`. |
| `tests/test_refresh_catalogue.py` | **New.** `dataset_status()` unit tests plus the four layers' `probe()` through the seam. Unmarked — no spatial import on this path. |
| `.github/workflows/source-probe.yml` | **Modify.** Drop two secrets, install `.[spatial]`. |
| `tests/test_refresh_cli.py` | **Modify.** Invert `test_the_probe_workflow_installs_without_the_spatial_extra`; add a test that the struck secrets are gone. |
| `scripts/refresh_layers.py` | **Modify.** `format_probe_report` prints the `status`, so a version drift does not report as "UNREACHABLE". |
| `pyproject.toml` | **Modify.** Correct the stale `spatial` extra comment claiming `REGISTRY` is empty. |

---

### Task 1: The catalogue seam

**Files:**
- Create: `src/seagarden_dst/refresh/sources/catalogue.py`
- Modify: `src/seagarden_dst/refresh/layer.py` (the `ProbeResult` class, around line 43)
- Modify: `src/seagarden_dst/refresh/sources/{phy,bgc,bgc_light,wav}.py` — **the `ProbeResult(...)` construction ONLY** (Step 6). The `probe()` mechanism stays a HEAD until Task 2.
- Modify: `tests/refresh_fakes.py`, `tests/test_refresh_layer.py` — same, the construction only
- Test: `tests/test_refresh_catalogue.py`

**Interfaces:**
- Consumes: `ProbeResult` from `seagarden_dst.refresh.layer` (extended in this task).
- Produces:
  - `ProbeStatus = Literal["ok", "absent", "version_drift", "unreachable"]` in `seagarden_dst.refresh.layer`
  - `ProbeResult(name: str, status: ProbeStatus, reachable: bool, detail: str)` — `reachable` must equal `status == "ok"`
  - `DescribeCallable` protocol in `catalogue.py`: `__call__(**kwargs: Any) -> Any`
  - `dataset_status(dataset_id: str, expected_version: str, *, describe: DescribeCallable | None = None) -> tuple[ProbeStatus, str]`

- [ ] **Step 1: Write the failing test for `ProbeResult`'s consistency validator**

Create `tests/test_refresh_catalogue.py`:

```python
"""The catalogue probe (C§8.2).

Unmarked, and deliberately not in `test_refresh_sources.py`, which is marked
`spatial`. The probe path must work wherever the monthly job runs, and these tests
drive `describe` through an injected callable, so nothing here needs the scientific
stack or the network.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from seagarden_dst.refresh.layer import ProbeResult


def test_a_probe_result_may_not_claim_ok_while_unreachable():
    """`status` and `reachable` are two views of one fact; they may not disagree.

    Without this, a helper that set `status="version_drift"` but left
    `reachable=True` would report green in the CLI and red in the detail string,
    and the monthly job would pass while telling you it had failed.
    """
    with pytest.raises(ValidationError, match="reachable=True contradicts status"):
        ProbeResult(
            name="copernicus_phy",
            status="version_drift",
            reachable=True,
            detail="anything",
        )


def test_a_probe_result_may_not_claim_unreachable_while_ok():
    with pytest.raises(ValidationError, match="reachable=False contradicts status"):
        ProbeResult(
            name="copernicus_phy", status="ok", reachable=False, detail="anything"
        )


def test_a_consistent_probe_result_is_accepted():
    result = ProbeResult(
        name="copernicus_phy", status="ok", reachable=True, detail="version 202303"
    )
    assert result.reachable is True
    assert result.status == "ok"
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `micromamba run -n shiny python -m pytest tests/test_refresh_catalogue.py -v`
Expected: FAIL — `ProbeResult` has `extra="forbid"`, so passing `status` raises `ValidationError` about an unexpected field, not about the contradiction. Both raises-tests fail on the `match=` and the third fails outright.

- [ ] **Step 3: Extend `ProbeResult` in `src/seagarden_dst/refresh/layer.py`**

Add `Literal` to the `typing` import line, then replace the `ProbeResult` class:

```python
ProbeStatus = Literal["ok", "absent", "version_drift", "unreachable"]


class ProbeResult(BaseModel):
    """One layer's answer to 'do you still exist, at the version we publish?' (C§8.2).

    `reachable` was the whole answer while the probe was an HTTP HEAD: the page
    loaded or it did not. The catalogue probe distinguishes three failures that a
    single boolean flattened into one, and the operator reading a red monthly job
    needs to tell them apart — a retired `dataset_id` is a data-availability
    emergency, a drifted version is a manifest correction, and a network error is
    something to retry.

    `reachable` is kept rather than derived so that C-b's callers and
    `format_probe_report` keep working, and the validator below makes the redundancy
    safe: the two fields cannot disagree.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    status: ProbeStatus
    reachable: bool
    detail: str

    @model_validator(mode="after")
    def _check_status_agrees_with_reachable(self) -> ProbeResult:
        expected = self.status == "ok"
        if self.reachable != expected:
            raise ValueError(
                f"reachable={self.reachable} contradicts status={self.status!r}: "
                f"reachable must be {expected} when status is {self.status!r}. The "
                "two fields are one fact; a result that disagrees with itself would "
                "print green and read red"
            )
        return self
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `micromamba run -n shiny python -m pytest tests/test_refresh_catalogue.py -v`
Expected: 3 passed.

- [ ] **Step 5: Prove the validator is load-bearing (DELETE proof)**

Comment out the `raise ValueError(...)` statement inside `_check_status_agrees_with_reachable` and run the same three tests.
Expected: the two `pytest.raises` tests go RED with `DID NOT RAISE`, and the third still passes. If either raises-test still passes, the validator is not what made it raise — stop and find what did.
Restore the `raise` and re-run: 3 passed. Record both outputs in the report.

- [ ] **Step 6: Fix EVERY existing `ProbeResult` construction, so this task ends green**

Adding a required field breaks every existing caller. There are six, and all six are fixed here — **this task must not hand Task 2 a red suite**, because a task whose deliverable is a broken test run cannot be reviewed on its own.

In `tests/refresh_fakes.py:67` and `tests/test_refresh_layer.py:20`, add `status="ok"` wherever `reachable=True` and `status="unreachable"` wherever `reachable=False`.

In all four of `src/seagarden_dst/refresh/sources/{phy,bgc,bgc_light,wav}.py`, the `probe()` body still HEADs a URL — that is Task 2's to replace, **not yours**. Change only the construction, from:

```python
        return ProbeResult(name=self.name, reachable=reachable, detail=detail)
```

to:

```python
        return ProbeResult(
            name=self.name,
            status="ok" if reachable else "unreachable",
            reachable=reachable,
            detail=detail,
        )
```

`"unreachable"` and not `"absent"` is correct here: a HEAD genuinely cannot tell the two apart, which is the whole reason Task 2 replaces it. Do not invent a richer mapping from a mechanism that has no such information.

Run `micromamba run -n shiny python -m pytest` and confirm every construction the failures named is fixed.

- [ ] **Step 7: Write the failing tests for `dataset_status`**

Append to `tests/test_refresh_catalogue.py`:

```python
from seagarden_dst.refresh.sources.catalogue import dataset_status


class _FakeVersion:
    def __init__(self, label: str) -> None:
        self.label = label


class _FakeDataset:
    def __init__(self, labels: list[str]) -> None:
        self.versions = [_FakeVersion(label) for label in labels]


class _FakeProduct:
    def __init__(self, labels: list[str]) -> None:
        self.datasets = [_FakeDataset(labels)]


class _FakeCatalogue:
    """Mimics `CopernicusMarineCatalogue`: products -> datasets -> versions[].label.

    Built by hand rather than with a mock so the shape assertion is explicit. If
    copernicusmarine changes this nesting, `dataset_status` breaks against the real
    service while these tests stay green — which is why the monthly job exercises
    the real call. There is no way to have both offline tests and live shape
    verification in one test; C§8.2 chose the monthly job for the latter.
    """

    def __init__(self, labels: list[str]) -> None:
        self.products = [_FakeProduct(labels)]


def _describe_returning(labels: list[str]):
    def describe(**kwargs: object) -> _FakeCatalogue:
        return _FakeCatalogue(labels)

    return describe


def test_a_served_version_matching_the_manifest_is_ok():
    status, detail = dataset_status(
        "cmems_mod_bal_phy_my_P1M-m",
        "202303",
        describe=_describe_returning(["202303"]),
    )
    assert status == "ok"
    assert "202303" in detail


def test_a_retired_dataset_id_is_absent_not_unreachable():
    """The event the monthly job exists to catch (C§8.2).

    An HTML landing page returns 200 long after the dataset behind it is retired;
    `describe()` raises `DatasetNotFound`. This must classify as `absent`, distinct
    from `unreachable`, because the two demand different responses: a retired
    dataset needs a new source, a network error needs a retry.
    """
    from copernicusmarine import DatasetNotFound

    def describe(**kwargs: object) -> None:
        raise DatasetNotFound("cmems_gone")

    status, detail = dataset_status("cmems_gone", "202303", describe=describe)
    assert status == "absent"
    assert "cmems_gone" in detail


def test_a_version_the_catalogue_no_longer_serves_is_drift():
    """C§8.2: 'is the provenance we publish still true'.

    This is the check that would have caught C-c1's wav.py recording 202303 where
    C§11.1 says 202411, on the first monthly run, with nobody re-reading the
    catalogue table.
    """
    status, detail = dataset_status(
        "cmems_mod_bal_wav_my_PT1H-i",
        "202303",
        describe=_describe_returning(["202411"]),
    )
    assert status == "version_drift"
    assert "202303" in detail
    assert "202411" in detail


def test_a_network_failure_is_reported_not_raised():
    """One dead source must not fail the job for the other four (C§8.2)."""

    def describe(**kwargs: object) -> None:
        raise OSError("name resolution failed")

    status, detail = dataset_status("cmems_x", "202303", describe=describe)
    assert status == "unreachable"
    assert "name resolution failed" in detail


def test_the_dataset_id_asked_for_is_the_one_passed_through():
    """A probe that asked about the wrong dataset would report a live catalogue for
    a layer whose data had gone — green for the wrong reason."""
    seen: dict[str, object] = {}

    def describe(**kwargs: object) -> _FakeCatalogue:
        seen.update(kwargs)
        return _FakeCatalogue(["202303"])

    dataset_status("cmems_mod_bal_bgc_my_P1D-m", "202303", describe=describe)
    assert seen["dataset_id"] == "cmems_mod_bal_bgc_my_P1D-m"


def test_the_module_imports_without_the_spatial_stack(monkeypatch):
    """A module-scope `import copernicusmarine` would break collection of the whole
    default suite, which runs `-m 'not spatial'` — and `-m` deselects AFTER
    collection, so the marker would not save it."""
    import importlib
    import sys

    monkeypatch.setitem(sys.modules, "xarray", None)
    monkeypatch.setitem(sys.modules, "copernicusmarine", None)

    import seagarden_dst.refresh.sources.catalogue as module

    importlib.reload(module)
    assert module.dataset_status is not None
```

- [ ] **Step 8: Run them to verify they fail**

Run: `micromamba run -n shiny python -m pytest tests/test_refresh_catalogue.py -v`
Expected: collection error — `ModuleNotFoundError: No module named 'seagarden_dst.refresh.sources.catalogue'`.

- [ ] **Step 9: Write `src/seagarden_dst/refresh/sources/catalogue.py`**

```python
"""Whether a dataset still exists, at the version the manifest publishes (C§8.2).

This replaces an HTTP HEAD against a product landing page, which could not see
either event the monthly job exists to catch. A landing page returns 200 long after
the `dataset_id` behind it is retired, and it says nothing at all about versions.

**`describe()` needs no credential.** It accepts no `username`, `password` or
`credentials_file` — `get()` and `subset()` accept all three — and reads no cached
credential file. The catalogue is public. `source-probe.yml` passed two Copernicus
secrets until C-c2 struck them; nothing had ever read them.

**`copernicusmarine` is imported inside the call, not at module scope.** The probe
job installs `[spatial]` as of C-c2, so the old reason (a bare install) is gone —
but the default test suite runs `-m 'not spatial'`, and `-m` deselects after
collection, so a module-scope import here would break collection of every test in
the repository.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:  # pragma: no cover - typing only
    from seagarden_dst.refresh.layer import ProbeStatus


class DescribeCallable(Protocol):
    """What `dataset_status` calls. The injection seam every test uses."""

    def __call__(self, **kwargs: Any) -> Any: ...


def _default_describe() -> DescribeCallable:
    """Resolve the real `describe`, importing inside the call."""
    import copernicusmarine

    return copernicusmarine.describe


def _served_versions(catalogue: Any) -> list[str]:
    """Flatten `products -> datasets -> versions[].label`.

    A `dataset_id` lookup returns one product holding one dataset, but the nesting
    is read generically so a catalogue that answers with more does not silently
    report only the first.
    """
    return [
        version.label
        for product in catalogue.products
        for dataset in product.datasets
        for version in dataset.versions
    ]


def dataset_status(
    dataset_id: str,
    expected_version: str,
    *,
    describe: DescribeCallable | None = None,
) -> tuple[ProbeStatus, str]:
    """Ask the catalogue about one dataset. Returns `(status, detail)`, never raises.

    Four outcomes, deliberately distinct — the operator reading a red monthly job
    needs to tell a retired dataset (find a new source) from a drifted version
    (correct the manifest) from a network error (retry):

    - `ok` — the dataset exists and serves `expected_version`.
    - `absent` — `DatasetNotFound`. The dataset id no longer resolves.
    - `version_drift` — the dataset exists but no longer serves the version the
      manifest publishes. The provenance we ship has stopped being true.
    - `unreachable` — anything else, network included.

    Membership rather than latest-equality: C§8.2 asks 'is the provenance we publish
    still true', and a dataset that serves 202303 alongside a newer 202501 is still
    serving what the manifest recorded. A probe demanding the newest would go red on
    every reprocessing, which is an upgrade decision for a human, not a fault.
    """
    call = describe if describe is not None else _default_describe()

    # Imported inside the function for the reason in the module docstring. A bare
    # `except Exception` would also catch it, but naming it is what lets `absent`
    # and `unreachable` be different answers.
    from copernicusmarine import DatasetNotFound

    try:
        catalogue = call(dataset_id=dataset_id, disable_progress_bar=True)
    except DatasetNotFound as error:
        return "absent", f"dataset absent from catalogue: {dataset_id} ({error})"
    except Exception as error:  # noqa: BLE001 - one dead source must not fail the job
        return "unreachable", f"unreachable: {error}"

    served = _served_versions(catalogue)
    if expected_version in served:
        return "ok", f"{dataset_id} serves version {expected_version}"
    return (
        "version_drift",
        f"{dataset_id} no longer serves the version the manifest records: "
        f"manifest says {expected_version}, catalogue serves {served}",
    )
```

- [ ] **Step 10: Run the tests to verify they pass**

Run: `micromamba run -n shiny python -m pytest tests/test_refresh_catalogue.py -v`
Expected: 9 passed.

- [ ] **Step 11: Prove the drift branch is load-bearing (DELETE proof)**

Change the final `return` of `dataset_status` to `return "ok", "…"` (keeping the same detail string) and re-run.
Expected: `test_a_version_the_catalogue_no_longer_serves_is_drift` goes RED on `assert status == "version_drift"`, and no other test changes. If any other test also goes red, the tests are coupled — say so in the report.
Restore and re-run: 9 passed.

- [ ] **Step 12: Prove `absent` and `unreachable` are separately defended (SWAP proof)**

These two branches return sibling strings and are the pair most likely to be conflated. Swap them: make the `DatasetNotFound` handler return `"unreachable", ...` and the `Exception` handler return `"absent", ...`.
Expected: `test_a_retired_dataset_id_is_absent_not_unreachable` AND `test_a_network_failure_is_reported_not_raised` both go RED. If only one does, the other is asserting something both branches satisfy — fix that test before restoring.
Restore and re-run: 9 passed.

- [ ] **Step 13: Run the whole default suite and ruff**

Run:
```
micromamba run -n shiny python -m pytest
micromamba run -n shiny python -m pytest -m spatial
micromamba run -n shiny python -m ruff check .
```
Expected: **all three green.** `tests/test_refresh_reachability.py` still passes — Step 6 kept the four layers' HEAD probe working while widening only the construction. If anything is red here, do not hand it on; this task's deliverable is a green suite plus the new seam. Record the three counts verbatim; do not write "verified".

- [ ] **Step 14: Commit**

```bash
git add -A src tests
git commit -m "Add the catalogue probe seam and a four-state ProbeResult

An HTTP HEAD against a product landing page cannot see either event the
monthly job exists to catch: the page returns 200 long after the dataset
behind it is retired, and it says nothing about versions. dataset_status()
asks copernicusmarine.describe(dataset_id=...) instead and classifies the
answer into ok / absent / version_drift / unreachable.

describe() raises DatasetNotFound for an unknown id even though
raise_on_error defaults to False -- the flag governs bulk catalogue parsing,
not the targeted lookup. Verified by running it, because reading the
signature gives the opposite answer.

ProbeResult keeps reachable for C-b's callers and gains status, with a
validator forbidding the two from disagreeing: a result that printed green
and read red would be worse than either.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Wire the four layers, delete the HEAD probe

**Files:**
- Modify: `src/seagarden_dst/refresh/sources/cmems.py` (module docstring; add `catalogue_probe`)
- Modify: `src/seagarden_dst/refresh/sources/phy.py`, `bgc.py`, `bgc_light.py`, `wav.py`
- Delete: `src/seagarden_dst/refresh/sources/reachability.py`
- Delete: `tests/test_refresh_reachability.py`
- Test: `tests/test_refresh_catalogue.py` (append)

**Interfaces:**
- Consumes: `dataset_status(dataset_id, expected_version, *, describe=None) -> tuple[ProbeStatus, str]` and `DescribeCallable` from `seagarden_dst.refresh.sources.catalogue`; `ProbeResult(name, status, reachable, detail)` from `seagarden_dst.refresh.layer`.
- Produces: `cmems.catalogue_probe(name: str, dataset_id: str, version: str, *, describe: DescribeCallable | None = None) -> ProbeResult`. Each of the four layer classes accepts `describe: DescribeCallable | None = None` as its second constructor keyword, replacing `reachability_opener`. Each layer module gains a `VERSION: str` module constant.

- [ ] **Step 1: Write the failing tests for the four layers' `probe()`**

Append to `tests/test_refresh_catalogue.py`:

```python
# --- The four real layers, through the `describe` seam ---------------------------
#
# Every layer takes a `describe` for exactly this: proving C§8.2's probe path
# offline, with no network and no credential. The predecessor of these tests caught
# nothing for a whole package, because the `reachability_opener` parameter appeared
# in no test at all.


def _layer_classes():
    """The four classes, imported lazily so a collection error names the layer."""
    from seagarden_dst.refresh.sources.bgc import CopernicusBgc
    from seagarden_dst.refresh.sources.bgc_light import CopernicusBgcLight
    from seagarden_dst.refresh.sources.phy import CopernicusPhy
    from seagarden_dst.refresh.sources.wav import CopernicusWav

    return {
        "copernicus_phy": CopernicusPhy,
        "copernicus_bgc": CopernicusBgc,
        "copernicus_bgc_light": CopernicusBgcLight,
        "copernicus_wav": CopernicusWav,
    }


# C§11.1, copied verbatim. Written out here rather than read from provenance()
# because a test that derived its expectation from the code under test would pass
# for any pair of values, including the wrong one C-c1 shipped.
_C11_1 = {
    "copernicus_phy": ("cmems_mod_bal_phy_my_P1M-m", "202303"),
    "copernicus_bgc": ("cmems_mod_bal_bgc_my_P1M-m", "202303"),
    "copernicus_bgc_light": ("cmems_mod_bal_bgc_my_P1D-m", "202303"),
    "copernicus_wav": ("cmems_mod_bal_wav_my_PT1H-i", "202411"),
}


@pytest.mark.parametrize("layer_name", sorted(_C11_1))
def test_each_layer_probes_its_own_dataset_at_its_own_version(layer_name):
    """C§8.2: the probe must ask about the DATASET, not the product page.

    `copernicus_bgc` and `copernicus_bgc_light` read different datasets from the
    same product, so their landing pages are byte-identical and the old HEAD probe
    could not tell them apart. Their dataset ids differ, and this asserts each layer
    asks about its own.
    """
    expected_id, expected_version = _C11_1[layer_name]
    seen: dict[str, object] = {}

    def describe(**kwargs: object) -> _FakeCatalogue:
        seen.update(kwargs)
        return _FakeCatalogue([expected_version])

    result = _layer_classes()[layer_name](describe=describe).probe()

    assert result.name == layer_name
    assert result.status == "ok"
    assert result.reachable is True
    assert seen["dataset_id"] == expected_id


@pytest.mark.parametrize("layer_name", sorted(_C11_1))
def test_each_layer_reports_drift_against_the_version_it_publishes(layer_name):
    """The check that would have caught C-c1's wav.py on the first monthly run.

    The catalogue is made to serve a version no layer records, so every layer must
    report drift naming its own recorded value. A layer that hard-coded someone
    else's version would name the wrong number here.
    """
    _, expected_version = _C11_1[layer_name]
    describe = _describe_returning(["999999"])

    result = _layer_classes()[layer_name](describe=describe).probe()

    assert result.status == "version_drift"
    assert result.reachable is False
    assert expected_version in result.detail
    assert "999999" in result.detail


@pytest.mark.parametrize("layer_name", sorted(_C11_1))
def test_a_layer_whose_catalogue_is_down_reports_it_rather_than_raising(layer_name):
    """One dead source must not fail the job for the other four (C§8.2)."""

    def describe(**kwargs: object) -> None:
        raise OSError("name resolution failed")

    result = _layer_classes()[layer_name](describe=describe).probe()

    assert result.name == layer_name
    assert result.status == "unreachable"
    assert result.reachable is False


def test_the_probed_version_is_the_one_the_manifest_publishes():
    """The probe and `provenance()` must read the SAME version.

    If `probe()` checked a literal while `provenance()` recorded another, the job
    would verify a version the manifest does not publish — green while shipping a
    false provenance, which is the exact failure mode C-c1 hit.
    """
    for layer_name, (expected_id, expected_version) in _C11_1.items():
        layer = _layer_classes()[layer_name]()
        record = layer.provenance()
        assert record.dataset_id == expected_id
        assert record.version == expected_version
```

- [ ] **Step 2: Run them to verify they fail**

Run: `micromamba run -n shiny python -m pytest tests/test_refresh_catalogue.py -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'describe'` on every parametrised case.

- [ ] **Step 3: Add `catalogue_probe` to `src/seagarden_dst/refresh/sources/cmems.py`**

Add the imports `from seagarden_dst.refresh.layer import ProbeResult` and `from seagarden_dst.refresh.sources.catalogue import DescribeCallable, dataset_status` at module scope — both are xarray-free and copernicusmarine-free. Then append:

```python
def catalogue_probe(
    name: str,
    dataset_id: str,
    version: str,
    *,
    describe: DescribeCallable | None = None,
) -> ProbeResult:
    """Assemble one layer's `ProbeResult` from a catalogue lookup (C§8.2).

    The one place a Copernicus `ProbeResult` is built. Before this, all four layers
    carried an identical three-line `probe()` — the same copy-paste shape that let
    `wav.py` ship `version="202303"` where C§11.1 says `202411`, because the one
    field that legitimately differs travelled with the block that was duplicated.
    """
    status, detail = dataset_status(dataset_id, version, describe=describe)
    return ProbeResult(
        name=name, status=status, reachable=status == "ok", detail=detail
    )
```

- [ ] **Step 4: Rewrite the dead rationale in `cmems.py`'s module docstring**

Replace the paragraph beginning **"Nothing spatial is imported at module scope (R3)."** with:

```
**Nothing spatial is imported at module scope (R3).** The reason changed in C-c2
and the rule did not. It used to be that the probe job installed the bare package;
it now installs `[spatial]`, because `describe()` lives there. What still forbids a
module-scope import is the test suite: `addopts` runs `-m 'not spatial'`, and `-m`
deselects AFTER collection, so a module-scope `import copernicusmarine` here would
break collection of every test in the repository regardless of markers.
`import copernicusmarine` therefore lives inside `_default_opener` and inside
`catalogue.dataset_status`, and `xarray` appears only under `TYPE_CHECKING`.
```

- [ ] **Step 5: Switch the four layers**

In each of `phy.py`, `bgc.py`, `bgc_light.py`, `wav.py`:

1. Delete the line `from seagarden_dst.refresh.sources.reachability import url_reachable`.
2. Add `from seagarden_dst.refresh.sources.catalogue import DescribeCallable` to the imports.
3. In `__init__`, replace the parameter `reachability_opener: Callable[..., object] | None = None` with `describe: DescribeCallable | None = None`, and the body line `self._reachability_opener = reachability_opener` with `self._describe = describe`.
4. Replace the two-line `probe()` body with:

```python
    def probe(self) -> ProbeResult:
        return cmems.catalogue_probe(
            self.name, DATASET_ID, VERSION, describe=self._describe
        )
```

5. Each module already holds `DATASET_ID` and `PRODUCT_ID` as module constants but passes its version as a literal to `cmems.copernicus_provenance(...)`. Hoist it to a module constant `VERSION` beside `DATASET_ID`, and pass `version=VERSION` in the `provenance()` call. The values are C§11.1's: `"202303"` for `phy`, `bgc` and `bgc_light`; `"202411"` for `wav`. **This hoist is what makes the probe and the manifest read the same string by construction** — the property `test_the_probed_version_is_the_one_the_manifest_publishes` checks.
6. If `Callable` is left unused in a module's imports after step 3, remove it. `ruff` will name the file if you miss one.
7. `SOURCE_URL` is still used by `provenance()` — keep it. Only its use inside `probe()` goes.

- [ ] **Step 6: Run the new tests to verify they pass**

Run: `micromamba run -n shiny python -m pytest tests/test_refresh_catalogue.py -v`
Expected: 22 passed.

- [ ] **Step 7: Delete the HEAD probe and its tests**

```bash
git rm src/seagarden_dst/refresh/sources/reachability.py tests/test_refresh_reachability.py
```

Deleted rather than kept: after Step 5 nothing calls `url_reachable`, and a tested-but-uncalled module reports green forever while defending nothing. The EMODnet probe is a WCS `GetCapabilities` parse, not a HEAD, so it is unlikely to want this; if it does, `git show 3a57b1b:src/seagarden_dst/refresh/sources/reachability.py` recovers it.

- [ ] **Step 8: Confirm nothing still references the deleted module**

Search the tree for `url_reachable` and `reachability` under `src/`, `tests/` and `scripts/`.
Expected: no hits. Hits inside `.claude/worktrees/` belong to another session's worktree — **do not touch them.**

- [ ] **Step 9: Run the whole suite and ruff**

Run:
```
micromamba run -n shiny python -m pytest
micromamba run -n shiny python -m pytest -m spatial
micromamba run -n shiny python -m ruff check .
```
Expected: all green. The default count drops by the 7 deleted reachability tests and rises by the 22 new ones. Record the actual numbers; do not write "verified".

- [ ] **Step 10: Prove the layers are individually defended (DELETE proof)**

In `phy.py` ONLY, change `VERSION` to `"202411"` (wav's value) and run `micromamba run -n shiny python -m pytest tests/test_refresh_catalogue.py -v`.
Expected: `test_each_layer_probes_its_own_dataset_at_its_own_version[copernicus_phy]`, `test_each_layer_reports_drift_against_the_version_it_publishes[copernicus_phy]` and `test_the_probed_version_is_the_one_the_manifest_publishes` go RED; **the other three layers' parametrised cases stay GREEN.** If a change to `phy.py` reddens `bgc`'s case, the parametrisation is not isolating layers.
Restore and re-run. Record both outputs.

- [ ] **Step 11: Commit**

```bash
git add -A src tests
git commit -m "Probe the dataset, not the product page

All four layers carried an identical three-line probe() that HEADed a
product landing page. That could not distinguish copernicus_bgc from
copernicus_bgc_light -- same product, byte-identical page, different
datasets -- and returned 200 for a retired dataset_id, the event the
monthly job exists to catch.

Each layer now asks the catalogue about its own DATASET_ID at its own
VERSION, through one shared cmems.catalogue_probe(). The version is hoisted
to a module constant that probe() and provenance() both read, so the string
the job verifies and the string the manifest publishes are the same by
construction -- the property C-c1's 202303/202411 bug violated.

reachability.py and its tests are deleted rather than left uncalled. Recover
with git show 3a57b1b:src/seagarden_dst/refresh/sources/reachability.py.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: The workflow, the CLI report, and three stale claims

**Files:**
- Modify: `.github/workflows/source-probe.yml`
- Modify: `tests/test_refresh_cli.py:174-180`
- Modify: `scripts/refresh_layers.py:66-72`
- Modify: `src/seagarden_dst/refresh/registry.py` (module docstring and `check_registered_names` docstring)
- Modify: `pyproject.toml` (the `spatial` extra comment)

**Interfaces:**
- Consumes: `ProbeResult.status` from Task 1; the layer `probe()` behaviour from Task 2.
- Produces: no new Python interfaces. `format_probe_report` output gains the status word.

- [ ] **Step 1: Write the failing workflow tests**

Replace `test_the_probe_workflow_installs_without_the_spatial_extra` in `tests/test_refresh_cli.py` with:

```python
def test_the_probe_workflow_installs_the_spatial_extra():
    """C§8.2 inverts as of C-c2: the probe now needs `copernicusmarine`.

    It asserts on the install COMMAND, not on the word appearing anywhere in the
    step, because a comment mentioning the spatial extra would satisfy a substring
    test while the job installed the bare package and died on the import.
    """
    steps = _workflow()["jobs"]["probe"]["steps"]
    installs = [
        line.strip()
        for step in steps
        for line in str(step.get("run", "")).splitlines()
        if line.strip().startswith("pip install")
    ]
    assert installs, "the probe job runs no pip install at all"
    assert any("[spatial]" in line for line in installs), installs


def test_the_probe_workflow_passes_no_copernicus_credential():
    """C§8.2: `describe()` accepts no credential and reads no cached one.

    The two secrets this job used to pass were read by nothing. They looked
    justified because the spec asked for them, and the spec looked confirmed
    because the job passed them -- neither wrong when checked against the other.
    Verified by running describe() with no credential against the live catalogue.
    """
    workflow = (_WORKFLOWS / "source-probe.yml").read_text(encoding="utf-8")
    assert "COPERNICUSMARINE_SERVICE_USERNAME" not in workflow
    assert "COPERNICUSMARINE_SERVICE_PASSWORD" not in workflow
```

- [ ] **Step 2: Run them to verify they fail**

Run: `micromamba run -n shiny python -m pytest tests/test_refresh_cli.py -v -k "spatial_extra or credential"`
Expected: both FAIL — the workflow installs `pip install -e .` with no extra and still passes both secrets.

- [ ] **Step 3: Edit `.github/workflows/source-probe.yml`**

Replace the `Install` and `Probe every registered source` steps with:

```yaml
      - name: Install
        # WITH the spatial extra, as of C-c2. probe() calls
        # copernicusmarine.describe(dataset_id=...), which lives there. Until C-c2
        # this job installed the bare package and asserted it did so, because the
        # probe was a stdlib HTTP HEAD -- which returned 200 for a retired dataset
        # and could not see a version at all.
        run: |
          python -m pip install --upgrade pip
          pip install -e ".[spatial]"
      - name: Probe every registered source
        # No credential. describe() accepts no username, password or
        # credentials_file -- get() and subset() accept all three -- and reads no
        # cached credential file. The catalogue is public. Two Copernicus secrets
        # were passed here until C-c2 and were read by nothing (C§8.2).
        run: python -m scripts.refresh_layers --probe
```

Leave the `on:` block and everything above `Install` untouched.

- [ ] **Step 4: Run the workflow tests to verify they pass**

Run: `micromamba run -n shiny python -m pytest tests/test_refresh_cli.py -v`
Expected: all pass, including the untouched `test_the_probe_workflow_blocks_no_pull_request` and `test_ci_does_not_run_the_probe`.

- [ ] **Step 5: Write the failing test for the report**

Add to `tests/test_refresh_cli.py`:

```python
def test_a_version_drift_is_not_reported_as_unreachable():
    """Three failures shared one word before C-c2. They need different responses:
    a retired dataset needs a new source, a drift needs a manifest correction."""
    from scripts.refresh_layers import format_probe_report
    from seagarden_dst.refresh.layer import ProbeResult

    report = format_probe_report(
        [
            ProbeResult(
                name="copernicus_wav",
                status="version_drift",
                reachable=False,
                detail="manifest says 202303, catalogue serves ['202411']",
            )
        ]
    )

    assert "VERSION_DRIFT" in report
    assert "UNREACHABLE" not in report
```

Run: `micromamba run -n shiny python -m pytest tests/test_refresh_cli.py::test_a_version_drift_is_not_reported_as_unreachable -v`
Expected: FAIL on `assert "VERSION_DRIFT" in report` — the current `format_probe_report` prints the literal `UNREACHABLE` for anything not `reachable`. Record the failure before Step 6.

- [ ] **Step 6: Make the CLI report the status**

In `scripts/refresh_layers.py`, replace `format_probe_report`:

```python
def format_probe_report(results: Sequence[ProbeResult]) -> str:
    """One line per layer, status first so a red job is readable at a glance.

    The status word is `ProbeResult.status`, not a boolean rendering. A drifted
    version is a real failure but printing it as "UNREACHABLE" would send whoever
    reads the monthly job hunting a network fault instead of correcting a manifest.
    """
    lines = []
    for result in results:
        status = "ok" if result.reachable else result.status.upper()
        lines.append(f"{status:<14} {result.name}  {result.detail}")
    return "\n".join(lines)
```

Run the same test again. Expected: PASS.

- [ ] **Step 7: Correct the false claim in `registry.py`**

In `check_registered_names`'s docstring, replace the final paragraph:

```
    The comparison is `<=` and not `==` only because `emodnet_bathy` is still to
    come; C-c2's first task tightens it to equality, at which point a registered
    layer C§5 does not name, OR a named layer nobody registered, fails at import.
```

with:

```
    The comparison is `<=` and not `==` only because `emodnet_bathy` is still to
    come. An earlier version of this docstring said C-c2's FIRST task tightens it to
    equality. That was wrong twice over: C-c2 is the catalogue probe and does not
    add a layer at all, and tightening before `emodnet_bathy` exists would raise at
    import, because `set(LAYER_NAMES) - set(REGISTRY)` is `{'emodnet_bathy'}` — the
    whole suite would go red at collection. The tightening belongs in the SAME
    commit that registers the layer, never before it.
```

Also replace the module docstring's paragraph about the bare install, which C-c2 falsifies:

```
**Nothing here may import xarray or copernicusmarine at module scope.** As of C-c2
the probe workflow installs `[spatial]`, so the old reason — a bare `pip install -e
.` — no longer holds. The rule does: the default test suite runs `-m 'not spatial'`
and `-m` deselects AFTER collection, so a module-scope import here would break
collection of every test in the repository. The layer modules honour this by
importing inside their methods; do not add a convenience import here that breaks it.
```

- [ ] **Step 8: Correct the stale `spatial` extra comment in `pyproject.toml`**

Replace the sentence beginning `The CLI and its driver exist as of 0.4.0 (package C-b); the five layers that feed them are package C-c, so` and ending `rather than building anything.` with:

```
# The CLI and its driver exist as of 0.4.0 (package C-b). Four of the five layers
# landed with package C-c1 — `emodnet_bathy` is the outstanding one — so a refresh
# run still exits 1, now because the manifest's every-variable-claimed-exactly-once
# validator refuses an artifact missing its depth fields, not because REGISTRY is
# empty.
```

- [ ] **Step 9: Run everything**

Run:
```
micromamba run -n shiny python -m pytest
micromamba run -n shiny python -m pytest -m spatial
micromamba run -n shiny python -m ruff check .
```
Expected: all green. Record the three counts verbatim.

- [ ] **Step 10: Verify the workflow YAML still parses the way the tests read it**

`on:` is unquoted in this file and PyYAML parses it as the boolean `True`, which is why `tests/test_refresh_cli.py` indexes `_workflow()[True]`. Confirm the edit did not disturb it:

Run: `micromamba run -n shiny python -m pytest tests/test_refresh_cli.py -v -k "scheduled or blocks_no"`
Expected: PASS. If these fail with a `KeyError: True`, the `on:` block was altered — restore it.

- [ ] **Step 11: Commit**

```bash
git add -A .github tests scripts src pyproject.toml
git commit -m "Install the spatial extra in the probe job, drop two unread secrets

The probe needs copernicusmarine.describe() as of C-c2, so source-probe.yml
installs .[spatial] and the test that asserted the opposite inverts. It
asserts on the pip command rather than the word appearing in the step, so a
comment mentioning the extra cannot satisfy it.

The two COPERNICUSMARINE_SERVICE_* secrets are struck. describe() accepts no
credential and reads no cached one; verified by calling it against the live
catalogue with none supplied. They looked justified because C8.2 asked for
them and C8.2 looked confirmed because the workflow passed them -- neither
wrong when checked against the other, which is why the check had to be a run
and not a read.

format_probe_report prints the status word, so a drifted version stops
reporting as UNREACHABLE and sending the reader after a network fault.

Three stale claims corrected: registry.py's 'C-c2's first task tightens it to
equality' (C-c2 adds no layer, and tightening before emodnet_bathy exists
reddens the suite at import), registry.py's bare-install rationale, and
pyproject.toml's 'REGISTRY is still empty'.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## What this plan does not do

- **`emodnet_bathy` is not in it.** C§12 calls its fetch and its `probe()` "the least specified part of this design and the most likely to need rework once attempted". It needs a spike — access path (WCS `GetCapabilities`/`GetCoverage` vs DTM tile download), payload size over the Baltic bbox, the elevation sign and vertical datum, land exclusion before the min/mean reduction, and the regrid onto the `GridSpec` — and then a spec subsection, before any plan can contain real code for it.
- **`check_registered_names` is not tightened to equality.** It tightens in the commit that registers `emodnet_bathy`, not before.
- **No live-network test is added.** C§8.2 makes the monthly job the live test.
- **`ProbeResult.reachable` is not removed** in favour of `status` alone. C-b's callers read it; the validator makes keeping both safe.

## Self-Review

**Spec coverage (C§8.2, clause by clause):**

| C§8.2 requirement | Task |
|---|---|
| Separate workflow, monthly + `workflow_dispatch`, runs `--probe` | already true; guarded by untouched tests, re-run in Task 3 Step 10 |
| `describe(dataset_id=...)` per layer | Task 1 (seam), Task 2 (all four layers) |
| Needs no credential; the secret is struck | Task 3 Steps 1–3 |
| A landing page cannot see a retired `dataset_id`; `describe()` raises `DatasetNotFound` | Task 1 Step 7 `test_a_retired_dataset_id_is_absent_not_unreachable` |
| Distinguishes datasets sharing a page | Task 2 Step 1 `test_each_layer_probes_its_own_dataset_at_its_own_version` |
| Returns the version, so the probe checks the published provenance | Task 2 Step 1 `test_each_layer_reports_drift_against_the_version_it_publishes` |
| The job must install `[spatial]` once real layers land | Task 3 Step 3 |
| `test_the_probe_workflow_installs_without_the_spatial_extra` inverts | Task 3 Step 1 |
| Blocks no pull request | unchanged; Task 3 Step 10 re-checks |

**Placeholder scan:** none. Every code step carries the code; every command is runnable as written.

**Type consistency:** `dataset_status` returns `tuple[ProbeStatus, str]` in Task 1 and is consumed as such by `catalogue_probe` in Task 2. `DescribeCallable` is defined in Task 1 Step 9 and imported by name in Task 2 Steps 3 and 5. `ProbeStatus` is defined in Task 1 Step 3 and used in Task 1 Step 9's `TYPE_CHECKING` import. The constructor keyword is `describe` in Task 2 Step 5 and in every test in Task 2 Step 1. `VERSION` is introduced in Task 2 Step 5 and referenced by the `probe()` body in the same step.

**One risk recorded:** `_FakeCatalogue` mimics `products -> datasets -> versions[].label`, established by running 2.4.0 on 2026-09-17. If copernicusmarine changes that nesting, `_served_versions` breaks against the real service while these tests stay green. No offline test can cover that; the monthly job is what catches it, which is the trade C§8.2 already chose.
