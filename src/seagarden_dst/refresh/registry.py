"""The one place the source list lives (C§5).

Both the driver and the probe job read this, so a layer added here appears in the
refresh and in the monthly catalogue probe without being registered twice.

**Nothing here may import xarray or copernicusmarine at module scope.** As of C-c2
the probe workflow installs `[spatial]`, so the old reason — a bare `pip install -e
.` — no longer holds. The rule does: the default test suite runs `-m 'not spatial'`
and `-m` deselects AFTER collection, so a module-scope import here would break
collection of every test in the repository. The layer modules honour this by
importing inside their methods; do not add a convenience import here that breaks it.
"""

from __future__ import annotations

from seagarden_dst.refresh.layer import LAYER_NAMES, Layer
from seagarden_dst.refresh.sources.bgc import CopernicusBgc
from seagarden_dst.refresh.sources.bgc_light import CopernicusBgcLight
from seagarden_dst.refresh.sources.emodnet import EmodnetBathy
from seagarden_dst.refresh.sources.phy import CopernicusPhy
from seagarden_dst.refresh.sources.wav import CopernicusWav

REGISTRY: dict[str, Layer] = {
    layer.name: layer
    for layer in (
        CopernicusPhy(),
        CopernicusBgc(),
        CopernicusBgcLight(),
        CopernicusWav(),
        EmodnetBathy(),
    )
}


def check_registered_names(registry: dict[str, Layer], names: tuple[str, ...]) -> None:
    """Refuse a registry holding a layer C§5 does not name.

    A function rather than a bare `if` at module scope so that a test can call it
    with a bad registry and watch it fire. The guard was previously inline and
    unreachable from any test: nothing could construct the failing case without
    monkeypatching a module constant and re-importing, so the argument it makes for
    itself went unchecked. It matters more now that `emodnet_bathy` is registered
    and the comparison is equality.

    A `raise`, not an `assert`: module-scope asserts vanish under `python -O`, and a
    guard that disappears under an optimisation flag is a guard that cannot fail.

    The comparison is equality, as of C-d: `emodnet_bathy` is now registered, so a
    registry short a name (a layer removed) is exactly as wrong as a registry
    holding a name C§5 does not know, and both must raise before a refresh starts.
    """
    unknown = sorted(set(registry) - set(names))
    missing = sorted(set(names) - set(registry))
    if unknown or missing:
        raise RuntimeError(
            f"registry and LAYER_NAMES disagree: not named {unknown}, not registered "
            f"{missing} (C§5, tightened to equality with emodnet_bathy per C§13.5)"
        )


check_registered_names(REGISTRY, LAYER_NAMES)
