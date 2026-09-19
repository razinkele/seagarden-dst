# tests/test_refresh_cli.py
from pathlib import Path

import pytest
import yaml
from refresh_fakes import FakeLayer

from scripts.refresh_layers import build_parser, format_probe_report, main, probe_all


def test_the_parser_reads_an_inclusive_year_range():
    args = build_parser().parse_args(["--start-year", "2016", "--end-year", "2025"])
    assert (args.start_year, args.end_year) == (2016, 2025)


def test_probe_mode_needs_no_year_range():
    assert build_parser().parse_args(["--probe"]).probe is True


def test_probe_all_reports_one_result_per_layer():
    layers = [
        FakeLayer("copernicus_phy", ["temp_c"]),
        FakeLayer("emodnet_bathy", ["depth_mean_m"], reachable=False),
    ]
    assert [(r.name, r.reachable) for r in probe_all(layers)] == [
        ("copernicus_phy", True),
        ("emodnet_bathy", False),
    ]


def test_the_report_marks_the_unreachable_layer_and_not_the_reachable_one():
    layers = [
        FakeLayer("copernicus_phy", ["temp_c"]),
        FakeLayer("emodnet_bathy", ["depth_mean_m"], reachable=False),
    ]
    report = format_probe_report(probe_all(layers))
    reachable_line = next(ln for ln in report.splitlines() if "copernicus_phy" in ln)
    unreachable_line = next(ln for ln in report.splitlines() if "emodnet_bathy" in ln)
    assert reachable_line.startswith("ok")
    assert unreachable_line.startswith("UNREACHABLE")


def test_an_unreachable_layer_makes_the_probe_exit_nonzero(monkeypatch):
    # C§8.2: the job turns red so a dead upstream is loud — and it lives outside
    # ci.yml so that redness blocks no pull request.
    import scripts.refresh_layers as cli

    monkeypatch.setattr(
        cli,
        "REGISTRY",
        {"emodnet_bathy": FakeLayer("emodnet_bathy", ["depth_mean_m"], reachable=False)},
    )
    assert main(["--probe"]) == 1


def test_an_all_reachable_probe_exits_zero(monkeypatch):
    import scripts.refresh_layers as cli

    monkeypatch.setattr(
        cli, "REGISTRY", {"copernicus_phy": FakeLayer("copernicus_phy", ["temp_c"])}
    )
    assert main(["--probe"]) == 0


def test_an_empty_registry_does_not_probe_green(monkeypatch):
    # The C-b REGISTRY ships empty (C-c fills it). A monthly job reporting nothing and
    # exiting 0 is a check that cannot fail — worse than no check, because it looks
    # like one.
    import scripts.refresh_layers as cli

    monkeypatch.setattr(cli, "REGISTRY", {})
    assert main(["--probe"]) == 1


def test_a_refresh_with_an_empty_registry_returns_one_rather_than_raising(tmp_path, monkeypatch):
    # M6: the empty-REGISTRY guard covered `--probe` but not the refresh branch,
    # which mkdir'd `workdir` and then died with an uncaught
    # `ValueError: no coverage layer was built`. Unmarked (no xarray import on this
    # path): the guard must return before the refresh branch's lazy xarray import.
    import scripts.refresh_layers as cli

    monkeypatch.setattr(cli, "REGISTRY", {})
    workdir = tmp_path / "work"
    code = cli.main(
        [
            "--start-year", "2024", "--end-year", "2024",
            "--target", str(tmp_path / "out"), "--workdir", str(workdir),
        ]
    )
    assert code == 1
    assert not workdir.exists()


def test_a_refresh_without_a_year_range_is_refused(capsys):
    with pytest.raises(SystemExit):
        main([])
    assert "--start-year and --end-year are required" in capsys.readouterr().err


def test_a_refresh_with_a_layer_missing_refuses_before_the_download(monkeypatch, capsys):
    """The guard stays: if a layer is ever unregistered again, a refresh must refuse
    before opening a single Copernicus dataset over the wire."""
    import scripts.refresh_layers as cli

    monkeypatch.setattr(
        cli,
        "REGISTRY",
        {
            "copernicus_phy": FakeLayer("copernicus_phy", ["temp_c"]),
            "copernicus_bgc": FakeLayer("copernicus_bgc", ["din_umol_l"]),
            "copernicus_bgc_light": FakeLayer("copernicus_bgc_light", []),
            "copernicus_wav": FakeLayer("copernicus_wav", ["significant_wave_m"]),
        },
    )
    with pytest.raises(SystemExit) as excinfo:
        main(["--start-year", "2024", "--end-year", "2024"])
    assert excinfo.value.code != 0
    assert "emodnet_bathy" in capsys.readouterr().err


def test_probe_reports_whatever_is_registered_even_when_a_layer_is_missing(monkeypatch):
    # --probe stays permissive while the registry is incomplete: reporting on four
    # reachable sources is still useful even though a refresh would refuse.
    import scripts.refresh_layers as cli

    registry = {
        "copernicus_phy": FakeLayer("copernicus_phy", ["temp_c"]),
        "copernicus_bgc": FakeLayer("copernicus_bgc", ["din_umol_l"]),
        "copernicus_bgc_light": FakeLayer("copernicus_bgc_light", []),
        "copernicus_wav": FakeLayer("copernicus_wav", ["significant_wave_m"]),
    }
    monkeypatch.setattr(cli, "REGISTRY", registry)
    assert main(["--probe"]) == 0


_WORKFLOWS = Path(__file__).resolve().parent.parent / ".github" / "workflows"
_PROBE = _WORKFLOWS / "source-probe.yml"


def _workflow():
    # PyYAML parses the unquoted key `on` as the boolean True (the Norway problem),
    # so the triggers live under the True key. Checked against this environment's
    # PyYAML: yaml.safe_load("on:\n  schedule: []\n") has the single key True.
    # Do not "fix" this to the string "on".
    return yaml.safe_load(_PROBE.read_text(encoding="utf-8"))


def test_the_probe_workflow_is_scheduled_and_dispatchable():
    triggers = _workflow()[True]
    assert "schedule" in triggers
    assert "workflow_dispatch" in triggers


def test_the_probe_workflow_blocks_no_pull_request():
    # C§8.2: gating merges on a third-party service would make every PR hostage to
    # Copernicus.
    triggers = _workflow()[True]
    assert "pull_request" not in triggers
    assert "push" not in triggers


def test_ci_does_not_run_the_probe():
    # The separation that matters is behavioural, not two files existing: ci.yml must
    # not invoke the probe, or the separation is cosmetic.
    assert "--probe" not in (_WORKFLOWS / "ci.yml").read_text(encoding="utf-8")


def test_the_probe_workflow_runs_the_probe_flag():
    steps = _workflow()["jobs"]["probe"]["steps"]
    assert any("--probe" in str(step.get("run", "")) for step in steps)


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


def test_the_probe_summary_names_each_failure_by_its_status(monkeypatch, capsys):
    """format_probe_report distinguishes absent / version_drift / unreachable; the
    summary line under it collapsed them all back into "unreachable" — the conflation
    Step 6 removed, re-introduced one line later. A reader of a red monthly job
    would go hunting a network fault to fix a manifest."""
    from scripts import refresh_layers
    from seagarden_dst.refresh.layer import ProbeResult

    class _Drifted:
        name = "copernicus_wav"

        def probe(self):
            return ProbeResult(
                name=self.name, status="version_drift", reachable=False,
                detail="manifest says 202303, catalogue serves ['202411']",
            )

    monkeypatch.setattr(refresh_layers, "REGISTRY", {"copernicus_wav": _Drifted()})
    code = refresh_layers.main(["--probe"])
    out = capsys.readouterr().out

    assert code != 0
    summary = out.strip().splitlines()[-1]
    assert "version_drift" in summary
    assert "unreachable" not in summary


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
