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


def test_a_refresh_without_a_year_range_is_refused(capsys):
    with pytest.raises(SystemExit):
        main([])
    assert "--start-year and --end-year are required" in capsys.readouterr().err


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


def test_the_probe_workflow_installs_without_the_spatial_extra():
    # The probe path is deliberately xarray-free (C§8.2: catalogue metadata only).
    # Installing the spatial extra here would make a reachability check depend on the
    # scientific stack it exists to avoid needing.
    steps = _workflow()["jobs"]["probe"]["steps"]
    installs = " ".join(str(step.get("run", "")) for step in steps)
    assert "spatial" not in installs
