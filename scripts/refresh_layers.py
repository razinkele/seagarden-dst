"""The refresh entry point (C§5, C§8.2).

Two modes and no third: a full refresh for a named year range, and `--probe`, which
asks only whether each source still exists. `--probe` is what the monthly workflow
runs. As of C-c2 that job installs the `[spatial]` extra — `describe()` lives there
— so the old reason for keeping xarray off this path is gone; the rule stays because
the default test suite runs `-m 'not spatial'`, and `-m` deselects AFTER collection,
so a module-scope import here would break collection repository-wide.
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
# `src/` on `sys.path` itself. CI's `pip install -e ".[spatial,dev]"` DOES install
# the package, so this block is development-environment insurance, not a
# repository-wide fact — do not "clean this up" by removing it and relying on an
# install that CI has but this environment does not.
_ROOT = Path(__file__).resolve().parent.parent
_SRC_DIR = _ROOT / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from seagarden_dst.refresh.layer import LAYER_NAMES, Layer, ProbeResult, YearRange  # noqa: E402
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
    """One line per layer, status first so a red job is readable at a glance.

    The status word is `ProbeResult.status`, not a boolean rendering. A drifted
    version is a real failure but printing it as "UNREACHABLE" would send whoever
    reads the monthly job hunting a network fault instead of correcting a manifest.
    """
    lines = []
    for result in results:
        status = "ok" if result.reachable else result.status.upper()
        lines.append(f"{status:<14} {result.name}  {result.detail}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.probe and (args.start_year is None or args.end_year is None):
        parser.error("--start-year and --end-year are required for a refresh")

    # The C-b REGISTRY ships empty (C-c fills it). Hoisted above the `--probe`
    # branch so it covers the refresh branch too: without this, an empty REGISTRY
    # let the refresh branch mkdir `workdir` and then die on an uncaught
    # `ValueError: no coverage layer was built` instead of failing loud and clean.
    if not REGISTRY:
        print(
            "no layers are registered, so this run did nothing. Exiting non-zero "
            "rather than reporting green: a check that cannot fail is worse than "
            "no check, because it looks like one."
        )
        return 1

    if args.probe:
        results = probe_all(list(REGISTRY.values()))
        print(format_probe_report(results))
        failed = [(r.name, r.status) for r in results if not r.reachable]
        if failed:
            print(
                f"\n{len(failed)} source(s) failed: "
                + ", ".join(f"{n} ({s})" for n, s in failed)
            )
            return 1
        return 0

    # The refresh branch only: a REGISTRY missing any of the C§5 layer names passes
    # the empty-registry guard above, so without this check a refresh would open real
    # Copernicus and EMODnet sources, pull data over the wire, and only then die deep
    # inside `compute_valid` or manifest validation because `valid`'s derivation names
    # a layer that is not registered. Refusing here trades an expensive failure for a
    # cheap one. `--probe` stays permissive: reporting on whichever sources are
    # reachable is useful even if a layer were ever missing from the registry.
    missing = sorted(set(LAYER_NAMES) - set(REGISTRY))
    if missing:
        parser.error(
            f"cannot refresh: {', '.join(missing)} "
            f"{'is' if len(missing) == 1 else 'are'} named in C§5 but not "
            "registered, so the artifact would be missing variables the manifest "
            "must claim. Refusing before the download rather than after it."
        )

    # Imported here, not at module scope: the probe path must stay free of xarray.
    from seagarden_dst.artifact.grid import GridSpec
    from seagarden_dst.refresh import driver

    try:
        artifact, manifest = driver.run_refresh(
            list(REGISTRY.values()),
            grid=GridSpec.baltic(),
            years=YearRange(start=args.start_year, end=args.end_year),
            target_dir=args.target,
            workdir=args.workdir,
        )
    except driver.RefreshFailed as exc:
        # C§6.1: refuse and say why. A refusal is an outcome the runbook documents,
        # not a crash, so it reaches the operator as one line, not a traceback.
        print(f"refresh refused: {exc}", file=sys.stderr)
        return 1
    print(f"wrote {artifact}\nwrote {manifest}")
    return 0


if __name__ == "__main__":  # pragma: no cover - entry point
    raise SystemExit(main())
