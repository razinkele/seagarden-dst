"""The refresh entry point (C§5, C§8.2).

Two modes and no third: a full refresh for a named year range, and `--probe`, which
asks only whether each source still exists. `--probe` is what the monthly workflow
runs, so nothing on that path may import xarray — the probe job installs no spatial
extra, and a module-scope import would make a reachability check depend on the
scientific stack it exists to avoid needing.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

# In the `shiny` development environment, `seagarden_dst` has no editable install
# (`pip show seagarden_dst` finds nothing there) — pytest resolves it via
# pyproject's `pythonpath = ["src", "."]`, but a plain script run with
# `python -m` or `python scripts/refresh_layers.py` gets no such help, so this puts
# `src/` (and, for the same reason, `tests/`) on `sys.path` itself. CI's
# `pip install -e ".[spatial,dev]"` DOES install the package, so this block is
# development-environment insurance, not a repository-wide fact — do not "clean
# this up" by removing it and relying on an install that CI has but this
# environment does not.
_ROOT = Path(__file__).resolve().parent.parent
_SRC_DIR = _ROOT / "src"
_TESTS_DIR = _ROOT / "tests"
for _p in (_SRC_DIR, _TESTS_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from seagarden_dst.refresh.layer import Layer, ProbeResult, YearRange  # noqa: E402
from seagarden_dst.refresh.registry import REGISTRY  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="refresh_layers",
        description="Build the SeaGarden forcing artifact, or probe its sources.",
    )
    parser.add_argument(
        "--probe",
        action="store_true",
        help="report per-layer reachability and exit; performs no bulk transfer",
    )
    parser.add_argument("--start-year", type=int, help="first year of the refresh")
    parser.add_argument("--end-year", type=int, help="last year, inclusive")
    parser.add_argument(
        "--target",
        type=Path,
        default=Path("data/forcing"),
        help="directory receiving the artifact/manifest pair",
    )
    parser.add_argument(
        "--workdir",
        type=Path,
        default=Path(".refresh-work"),
        help="scratch space for layer builds",
    )
    return parser


def probe_all(layers: Sequence[Layer]) -> list[ProbeResult]:
    """Probe every layer. One result per layer, in the order given."""
    return [layer.probe() for layer in layers]


def format_probe_report(results: Sequence[ProbeResult]) -> str:
    """One line per layer, status first so a red job is readable at a glance."""
    lines = []
    for result in results:
        status = "ok" if result.reachable else "UNREACHABLE"
        lines.append(f"{status:<11} {result.name}  {result.detail}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.probe:
        if not REGISTRY:
            print(
                "no layers are registered, so this probe checked nothing. Exiting "
                "non-zero rather than reporting green: a check that cannot fail is "
                "worse than no check, because it looks like one."
            )
            return 1
        results = probe_all(list(REGISTRY.values()))
        print(format_probe_report(results))
        unreachable = [r.name for r in results if not r.reachable]
        if unreachable:
            print(f"\n{len(unreachable)} source(s) unreachable: {unreachable}")
            return 1
        return 0

    if args.start_year is None or args.end_year is None:
        parser.error("--start-year and --end-year are required for a refresh")

    # Imported here, not at module scope: the probe path must stay free of xarray.
    from seagarden_dst.artifact.grid import GridSpec
    from seagarden_dst.refresh.driver import run_refresh

    artifact, manifest = run_refresh(
        list(REGISTRY.values()),
        grid=GridSpec.baltic(),
        years=YearRange(start=args.start_year, end=args.end_year),
        target_dir=args.target,
        workdir=args.workdir,
    )
    print(f"wrote {artifact}\nwrote {manifest}")
    return 0


if __name__ == "__main__":  # pragma: no cover - entry point
    raise SystemExit(main())
