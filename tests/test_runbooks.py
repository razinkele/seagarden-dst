"""The runbooks are deliverables (C§8.1, deploy §7), so their required content is
checked the way the workflows are: a document that lost its volume figure is one
somebody abandons halfway."""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_REFRESH = _ROOT / "docs" / "runbooks" / "annual-refresh.md"


def _text() -> str:
    return _REFRESH.read_text(encoding="utf-8")


def test_the_refresh_runbook_exists():
    assert _REFRESH.exists()


@pytest.mark.parametrize(
    "required",
    [
        "institutional",              # the credential rule (C§8.1)
        "30.5 GB",                    # on the wire, revised by C§13.7
        "~170 MB",                    # on disk
        "SEAGARDEN_DATA_DIR",         # where the service reads (C§13.6)
        "~/seagarden-data/forcing",   # outside the serving checkout (C§13.6)
        "--start-year",
        "2016",                       # C§1 fixes the baseline at 2016-2025
        "--end-year 2025",
        "--probe",
        "sha256",                     # how to verify
        "pending",                    # the committed vs deposited manifest sequence
        "Zenodo",
        "LAT",                        # the bathymetry datum (C§13.2)
        "check_grid",                 # the convention to confirm on the first run (C§13.3)
    ],
)
def test_the_refresh_runbook_carries_what_C8_1_lists(required):
    assert required in _text(), f"annual-refresh.md no longer mentions {required!r}"


def test_the_refresh_runbook_names_every_C6_1_failure_mode():
    spec = (_ROOT / "docs/superpowers/specs/2026-09-15-package-c-refresh-tooling-design.md")
    section = spec.read_text(encoding="utf-8").split("### C§6.1 Failure modes")[1].split(
        "## C§7"
    )[0]
    rows = [
        line.strip()
        for line in section.splitlines()
        if line.strip().startswith("|")
    ]
    conditions = []
    for row in rows:
        cells = [c.strip() for c in row.strip("|").split("|")]
        if not cells:
            continue
        first = cells[0]
        if first in ("Condition", "") or set(first) <= {"-"}:
            continue
        conditions.append(first.strip("*"))
    assert conditions, "C§6.1 lost its table of failure modes; update this test"
    text = _text()
    missing = [c for c in conditions if c not in text]
    assert not missing, f"runbook does not name these C§6.1 failure modes: {missing}"


_FENCED_BLOCK = re.compile(r"```[^\n]*\n(.*?)```", re.S)
_IMPORT_LINE = re.compile(r"from seagarden_dst\.(\w+) import ([\w, ]+)")


def test_every_import_in_a_fenced_command_names_a_real_module_attribute():
    """A runbook command that imports a name the module does not have is unrunnable.
    This is what would have caught the old `GriddedForcing.open(...)` claim: `open`
    is not an attribute of `GriddedForcing`, even though `GriddedForcing` itself is a
    real import from `seagarden_dst.gridded`."""
    text = _text()
    checked_any = False
    for block in _FENCED_BLOCK.findall(text):
        for module_name, names in _IMPORT_LINE.findall(block):
            module = importlib.import_module(f"seagarden_dst.{module_name}")
            imported = [n.strip() for n in names.split(",") if n.strip()]
            for name in imported:
                checked_any = True
                assert hasattr(module, name), (
                    f"runbook imports `{name}` from seagarden_dst.{module_name}, "
                    "which has no such attribute"
                )
                # Also check every `Name.attr` access in the same block, so a command
                # that imports a real name but then calls a nonexistent method on it
                # (e.g. `GriddedForcing.open(...)`) is caught too.
                target = getattr(module, name)
                for attr in re.findall(rf"\b{re.escape(name)}\.(\w+)", block):
                    assert hasattr(target, attr), (
                        f"runbook calls `{name}.{attr}`, but {name} has no such "
                        "attribute"
                    )
    assert checked_any, "no `from seagarden_dst...` import found in any fenced block"
