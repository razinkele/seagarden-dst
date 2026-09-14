"""Shared pytest configuration.

Registers `--snapshot-update`, used by `test_golden_snapshot.py` to regenerate the
golden files instead of asserting against them. pytest collects conftests along the
invocation path and rootdir ancestry before argument parsing finishes, regardless of
`testpaths` - `testpaths` only comes into play when a run is given no positional path
arguments to derive that walk from. Either way this conftest is found first, so the
flag is available whether pytest is invoked bare (falls back to `testpaths`) or with
an explicit path such as `pytest tests/test_golden_snapshot.py --snapshot-update`.
"""

from __future__ import annotations


def pytest_addoption(parser):
    parser.addoption(
        "--snapshot-update",
        action="store_true",
        default=False,
        help="Regenerate golden files instead of asserting against them.",
    )
