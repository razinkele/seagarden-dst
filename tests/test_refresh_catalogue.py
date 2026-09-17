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
from seagarden_dst.refresh.sources.catalogue import dataset_status


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


class _FakeDatasetNotFound(Exception):
    """Stands in for copernicusmarine.DatasetNotFound, matched by name (see
    catalogue._is_dataset_not_found). The real class is asserted separately,
    under the spatial marker."""


# `_is_dataset_not_found` matches `type(error).__name__ == "DatasetNotFound"`, not
# `isinstance` against an imported class — that is the whole point of the fix. A
# fake whose class is literally named `_FakeDatasetNotFound` would not exercise
# that match at all; renaming it here makes this fake behave, for the purpose of
# the by-name check, exactly like the real `copernicusmarine.DatasetNotFound` would.
_FakeDatasetNotFound.__name__ = "DatasetNotFound"


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
    def describe(**kwargs: object) -> None:
        raise _FakeDatasetNotFound("cmems_gone")

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


@pytest.mark.spatial
def test_the_real_dataset_not_found_class_is_classified_as_absent():
    """Name-matching would silently report `unreachable` if copernicusmarine
    renamed the class. This pins the real one; it runs where the extra is installed."""
    from copernicusmarine import DatasetNotFound

    def describe(**kwargs: object) -> None:
        raise DatasetNotFound("cmems_gone")

    status, _ = dataset_status("cmems_gone", "202303", describe=describe)
    assert status == "absent"


def test_the_dataset_id_asked_for_is_the_one_passed_through():
    """A probe that asked about the wrong dataset would report a live catalogue for
    a layer whose data had gone — green for the wrong reason."""
    seen: dict[str, object] = {}

    def describe(**kwargs: object) -> _FakeCatalogue:
        seen.update(kwargs)
        return _FakeCatalogue(["202303"])

    dataset_status("cmems_mod_bal_bgc_my_P1D-m", "202303", describe=describe)
    assert seen["dataset_id"] == "cmems_mod_bal_bgc_my_P1D-m"


def test_no_catalogue_or_layer_module_imports_copernicusmarine_or_xarray_at_module_scope():
    """A module-scope import of either package would break collection of the whole
    default suite, which runs `-m 'not spatial'` — and `-m` deselects AFTER
    collection, so the marker would not save it. CI's default job installs neither
    package at all.

    Modelled on `app/tests/test_app_smoke.py::
    test_no_app_module_imports_shiny_deckgl_at_module_scope`, which scans for the
    same failure mode against `shiny_deckgl`.
    """
    import ast
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1] / "src" / "seagarden_dst" / "refresh"
    targets = [root / "sources" / "catalogue.py", root / "layer.py"]
    offenders = []
    for path in targets:
        for node in ast.parse(path.read_text(encoding="utf-8")).body:  # top level only
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            for n in names:
                top = n.split(".")[0]
                if top in ("copernicusmarine", "xarray"):
                    offenders.append(f"{path}:{node.lineno}:{top}")
    assert not offenders, f"copernicusmarine/xarray imported at module scope: {offenders}"


def test_dataset_status_classifies_without_copernicusmarine_installed(monkeypatch):
    """This is the test that would have caught the round-1 defect: `dataset_status`
    imported `copernicusmarine.DatasetNotFound` unconditionally in its body, so every
    call — including calls through the injected `describe` fake — required
    copernicusmarine to be importable. CI's default job installs no spatial extra
    and runs this unmarked file with a bare `pytest -q`, so that import redenned
    five tests there while staying green in a `shiny`-environment run locally.

    No `importlib.reload` here: `dataset_status` must work with `copernicusmarine`
    absent from `sys.modules` on an ordinary call, not only immediately after a
    forced re-execution of the module.
    """
    import sys

    monkeypatch.setitem(sys.modules, "copernicusmarine", None)

    def describe_not_found(**kwargs: object) -> None:
        raise _FakeDatasetNotFound("cmems_gone")

    status, _ = dataset_status("cmems_gone", "202303", describe=describe_not_found)
    assert status == "absent"

    def describe_broken(**kwargs: object) -> None:
        raise OSError("name resolution failed")

    status, _ = dataset_status("cmems_x", "202303", describe=describe_broken)
    assert status == "unreachable"
