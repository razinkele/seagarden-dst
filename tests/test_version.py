"""The version is written in two files, so it can disagree with itself.

`pyproject.toml` declares it for the installer and `seagarden_dst.__version__`
declares it for the About box, which `app/shell.py` reads rather than hand-copying
precisely because a copied version drifts silently. That reasoning stops one file
short: the two literals themselves are a hand-copy, and a release bumps both by hand.
This is the guard for that, and it is also what pins CHANGELOG.md to the release it
claims to describe.
"""

import tomllib
from pathlib import Path

import pytest

from seagarden_dst import __version__

_ROOT = Path(__file__).resolve().parents[1]


def _pyproject_version() -> str:
    with (_ROOT / "pyproject.toml").open("rb") as fh:
        return tomllib.load(fh)["project"]["version"]


def test_package_version_matches_pyproject():
    assert __version__ == _pyproject_version()


def test_changelog_documents_the_current_version():
    """A release whose CHANGELOG does not mention it is a release nobody can read.

    Development versions are exempt: `0.3.0.dev0` describes work in progress, and
    requiring an entry for it would mean writing the notes before the work.
    """
    if ".dev" in __version__:
        pytest.skip(f"{__version__} is a development version")
    changelog = (_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## [{__version__}]" in changelog
