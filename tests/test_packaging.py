"""The parameter files must reach an installed package, not just a checkout.

`params/` deliberately sits beside the repository root rather than inside the package:
it is data the project curates and republishes under the open-data commitment, not code
(see the comment at `params.DEFAULT_PARAM_ROOT`). The consequence, found in review of
0.2.0, is that nothing put it in a distribution: `[tool.setuptools.packages.find]`
looks only under `src/`, so a wheel carried no YAML at all and
`Path(__file__).resolve().parents[2] / "params"` resolved above site-packages.
`pip install seagarden-dst` produced a package that could not load its own parameters,
and only the documented editable install happened to work -- which is why CI, which
installs with -e, never caught it.

The fix keeps the repository layout and maps `params/` into the wheel at build time.
These tests guard the mapping, because the failure is invisible from a checkout: every
path works here whether or not the packaging is right.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PARAMS = REPO / "params"
DATA_PACKAGE = "seagarden_dst.paramdata"


def _pyproject() -> dict:
    with (REPO / "pyproject.toml").open("rb") as fh:
        return tomllib.load(fh)


def test_the_params_tree_is_mapped_into_the_distribution():
    """Without this mapping the wheel contains no parameter files at all."""
    package_dir = _pyproject()["tool"]["setuptools"]["package-dir"]
    assert package_dir.get(DATA_PACKAGE) == "params", (
        "params/ is not mapped into the distribution; a wheel would ship without it"
    )


def test_the_data_package_is_declared_so_setuptools_emits_it():
    """An explicit list, not `find:`: the tree is outside src/ and has no __init__.py,
    so automatic discovery would never pick it up."""
    packages = _pyproject()["tool"]["setuptools"]["packages"]
    assert DATA_PACKAGE in packages, "the data package is mapped but never declared"
    assert "seagarden_dst" in packages, "the code package must still be declared"


def test_every_committed_yaml_is_covered_by_a_package_data_glob():
    """The globs must cover the real tree, at whatever depth it grows to.

    `params/` is two levels deep today (`species/`, `regulatory/`). A third level added
    later would be silently dropped from the wheel while every checkout kept working,
    which is precisely how the original defect stayed invisible.
    """
    import fnmatch

    globs = _pyproject()["tool"]["setuptools"]["package-data"][DATA_PACKAGE]
    uncovered = []
    for path in sorted(PARAMS.rglob("*.yaml")):
        rel = path.relative_to(PARAMS).as_posix()
        if not any(fnmatch.fnmatch(rel, pattern) for pattern in globs):
            uncovered.append(rel)
    assert not uncovered, f"not shipped by any package-data glob: {uncovered}"


def test_the_loader_prefers_the_packaged_copy_when_there_is_one():
    """In a checkout the packaged directory is absent, so the checkout path is used.

    Asserting the resolution rule rather than the value keeps this meaningful in both
    installed and checked-out states.
    """
    from seagarden_dst import params

    packaged = Path(params.__file__).resolve().parent / "paramdata"
    if packaged.is_dir():
        assert params.DEFAULT_PARAM_ROOT == packaged
    else:
        assert params.DEFAULT_PARAM_ROOT == REPO / "params"
    assert (params.DEFAULT_PARAM_ROOT / "assessment.yaml").is_file()


def test_the_core_package_does_not_import_pandas_at_module_level():
    """A core install must import. pandas is in the `app` extra, not `dependencies`.

    Found by installing the wheel into a clean environment: `import seagarden_dst`
    raised ModuleNotFoundError: No module named 'pandas', because __init__ imports api,
    api imports scenarios, and scenarios imported pandas at module scope. pyproject says
    of the app extra "The core needs none of these" and lists the core as numpy, scipy,
    pydantic and pyyaml — so the dependency declaration was right and the import was
    wrong.

    Source inspection rather than a subprocess, following
    test_forcing_source.test_no_model_module_imports_a_concrete_source: it cannot catch
    an indirect import, so it complements rather than replaces installing the wheel.
    """
    import inspect

    from seagarden_dst import scenarios

    for line in inspect.getsource(scenarios).splitlines():
        stripped = line.strip()
        if stripped.startswith(("import pandas", "from pandas")):
            assert line.startswith((" ", "\t")), (
                "pandas must be imported inside the function that needs it, not at "
                "module level: it is an `app` extra and the core must import without it"
            )
