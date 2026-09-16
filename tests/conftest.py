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

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--snapshot-update",
        action="store_true",
        default=False,
        help="Regenerate golden files instead of asserting against them.",
    )


@pytest.fixture
def reference_manifest():
    """The Task 3 reference manifest, shared by every test module that needs one.

    Just `refresh_builders.manifest()` — the builder itself lives in
    `tests/refresh_builders.py` and is not duplicated here.

    `refresh_builders` is imported here, inside the fixture body, rather than at
    module level: this conftest is collected for every pytest run in the repo, and
    a module-level import would pull `refresh_builders` -> `refresh.manifest` ->
    `refresh.grid` -> numpy/pydantic into every test module's collection, whether
    or not it needs a refresh fixture.
    """
    import refresh_builders

    return refresh_builders.manifest()


@pytest.fixture
def tiny_dataset():
    """A 3x3-cell, 2-year dataset carrying all nine variables at C§3.2 shapes.

    Coordinates come from `refresh_builders.fixture_grid()` (via `.lats()`/
    `.lons()`), not from an independent `np.linspace` over round bounds: the
    `reference_manifest` fixture's grid describes this same fixture grid, so the
    dataset and the manifest agree on WHERE the cells are.

    They do NOT agree on WHEN: `reference_manifest` (Task 3's rule-exercising
    manifest) carries baselines spanning 2016-2025, while this dataset — like the
    committed fixture — only carries `[2024, 2025]`. No test in this suite reads
    `reference_manifest`'s baseline years against this dataset's `year`
    coordinate (`test_the_baselines_describe_the_artifact_not_production` in
    `tests/test_refresh_fixture.py` checks that alignment against the FIXTURE's
    own manifest, built by `scripts/make_fixture.py` from the same years as its
    own dataset, not against this one). Making the two genuinely agree here would
    mean changing `reference_manifest`'s baselines, which is a Task 3 design
    choice (and would break `test_the_wave_baseline_is_not_empty_despite_having_
    no_year_dimension`'s deliberately-divergent wave baseline), not a docstring fix.

    The dataset itself is `refresh_builders.dataset(grid, years)` — shared with
    `scripts/make_fixture.py`'s fixture generator so the two synthetic datasets in
    this repository are not independently-maintained copies of the same thing.
    """
    import refresh_builders

    grid = refresh_builders.fixture_grid()
    return refresh_builders.dataset(grid, [2024, 2025])
