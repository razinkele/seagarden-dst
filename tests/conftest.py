"""Shared pytest configuration.

Registers `--snapshot-update`, used by `test_golden_snapshot.py` to regenerate the
golden files instead of asserting against them. `tests/` is a `testpaths` entry
(pyproject.toml), so this conftest is picked up before argument parsing and the flag
is available on every invocation, not just when the golden test module is selected.
"""

from __future__ import annotations


def pytest_addoption(parser):
    parser.addoption(
        "--snapshot-update",
        action="store_true",
        default=False,
        help="Regenerate golden files instead of asserting against them.",
    )
