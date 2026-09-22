"""The free-disk refusal of C§6.1: refuse BEFORE starting, naming the requirement.

Failing at 80% through a 30 GB transfer is the expensive failure; a refusal that
names the path, what it needs and what it has is the cheap one. The disk-usage
function is injected so these tests fill no disks.
"""

from __future__ import annotations

import os
from collections import namedtuple
from pathlib import Path

import pytest

from seagarden_dst.refresh.driver import (
    TARGET_MIN_BYTES,
    WORKDIR_MIN_BYTES,
    RefreshFailed,
    check_free_disk,
)

_GB = 1 << 30
_MB = 1 << 20
_Usage = namedtuple("_Usage", "total used free")


def _usage_by_path(free: dict[Path, int]):
    """A `shutil.disk_usage` stand-in reporting `free[path]` for each path asked."""

    def disk_usage(path):
        return _Usage(total=10 * _GB, used=0, free=free[Path(path)])

    return disk_usage


def _device_by_path(devices: dict[Path, int]):
    """A `device_of` stand-in: which filesystem each path sits on."""

    def device_of(path):
        return devices[Path(path)]

    return device_of


def test_the_thresholds_are_the_runbooks_figures():
    assert WORKDIR_MIN_BYTES == 2 * _GB
    assert TARGET_MIN_BYTES == 200 * _MB


def test_enough_space_on_separate_filesystems_passes(tmp_path):
    work, target = tmp_path / "work", tmp_path / "target"
    work.mkdir()
    target.mkdir()
    check_free_disk(
        work, target,
        disk_usage=_usage_by_path({work: 3 * _GB, target: 300 * _MB}),
        device_of=_device_by_path({work: 1, target: 2}),
    )


def test_a_short_workdir_is_refused_naming_the_path_and_the_requirement(tmp_path):
    work, target = tmp_path / "work", tmp_path / "target"
    work.mkdir()
    target.mkdir()
    with pytest.raises(RefreshFailed, match=r"work.*needs 2\.0 GB.*has 1\.5 GB") as excinfo:
        check_free_disk(
            work, target,
            disk_usage=_usage_by_path({work: int(1.5 * _GB), target: 300 * _MB}),
            device_of=_device_by_path({work: 1, target: 2}),
        )
    assert "before starting" in str(excinfo.value)


def test_a_short_target_is_refused_naming_200_mb(tmp_path):
    work, target = tmp_path / "work", tmp_path / "target"
    work.mkdir()
    target.mkdir()
    with pytest.raises(RefreshFailed, match=r"target.*needs 200 MB.*has 50 MB"):
        check_free_disk(
            work, target,
            disk_usage=_usage_by_path({work: 3 * _GB, target: 50 * _MB}),
            device_of=_device_by_path({work: 1, target: 2}),
        )


def test_the_same_filesystem_must_hold_both_requirements_together(tmp_path):
    """2.1 GB free passes each check alone and still runs out mid-transfer."""
    work, target = tmp_path / "work", tmp_path / "target"
    work.mkdir()
    target.mkdir()
    free = {work: int(2.1 * _GB), target: int(2.1 * _GB)}
    with pytest.raises(RefreshFailed, match=r"same filesystem.*needs 2\.2 GB.*has 2\.1 GB"):
        check_free_disk(
            work, target,
            disk_usage=_usage_by_path(free),
            device_of=_device_by_path({work: 7, target: 7}),
        )


def test_a_directory_that_does_not_exist_yet_is_measured_at_its_nearest_ancestor(tmp_path):
    """The CLI creates workdir and target itself, so the check runs before they exist."""
    work, target = tmp_path / "not" / "yet" / "work", tmp_path / "target"
    asked: list[Path] = []

    def disk_usage(path):
        asked.append(Path(path))
        return _Usage(total=10 * _GB, used=0, free=5 * _GB)

    check_free_disk(work, target, disk_usage=disk_usage, device_of=lambda p: 1)
    # One filesystem, so one measurement, taken at the ancestor that exists.
    assert asked == [tmp_path.resolve()], "measured at the nearest existing ancestor"


def test_the_default_device_function_reads_the_filesystem(tmp_path):
    """`device_of` defaults to `os.stat(...).st_dev`, so the same-filesystem branch
    is what runs in production, not only in the test that injects it."""
    from seagarden_dst.refresh.driver import _device_of

    assert _device_of(tmp_path) == os.stat(tmp_path).st_dev


def test_run_refresh_refuses_on_disk_before_building_any_layer(tmp_path, monkeypatch):
    """The check sits in `run_refresh`, so every caller gets it, and it runs before
    `_build_all` touches a single layer."""
    import seagarden_dst.refresh.driver as driver

    monkeypatch.setattr(
        driver, "check_free_disk",
        lambda *a, **k: (_ for _ in ()).throw(RefreshFailed("no space, before starting")),
    )
    built: list[str] = []
    monkeypatch.setattr(driver, "_build_all", lambda *a, **k: built.append("built"))
    with pytest.raises(RefreshFailed, match="before starting"):
        driver.run_refresh(
            [], grid=None, years=None, target_dir=tmp_path / "t", workdir=tmp_path / "w"
        )
    assert built == []


def test_the_cli_turns_a_refusal_into_exit_one_with_the_message_on_stderr(
    tmp_path, monkeypatch, capsys
):
    from refresh_fakes import FakeLayer

    import scripts.refresh_layers as cli
    from seagarden_dst.refresh.layer import LAYER_NAMES

    monkeypatch.setattr(cli, "REGISTRY", {n: FakeLayer(n, []) for n in LAYER_NAMES})

    def refuse(*a, **k):
        raise RefreshFailed("workdir X: needs 2.0 GB free before starting, has 0.5 GB")

    import seagarden_dst.refresh.driver as driver

    monkeypatch.setattr(driver, "run_refresh", refuse)
    code = cli.main(
        ["--start-year", "2024", "--end-year", "2024",
         "--target", str(tmp_path / "t"), "--workdir", str(tmp_path / "w")]
    )
    err = capsys.readouterr().err
    assert code == 1
    assert "needs 2.0 GB free before starting" in err
    assert "Traceback" not in err
