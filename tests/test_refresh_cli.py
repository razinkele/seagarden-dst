# tests/test_refresh_cli.py
import pytest
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
