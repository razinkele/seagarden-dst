"""The one place the source list lives (C§5).

Both the driver and the probe job read this, so a layer added here appears in the
refresh and in the monthly reachability check without being registered twice.

**Nothing here may import xarray or copernicusmarine at module scope.** The probe
workflow installs the bare package (`pip install -e .`, no `[spatial]` extra), so
this module and everything it imports must load without them. The layer modules
honour that by importing inside their methods; do not add a convenience import here
that breaks it.
"""

from __future__ import annotations

from seagarden_dst.refresh.layer import LAYER_NAMES, Layer
from seagarden_dst.refresh.sources.bgc import CopernicusBgc
from seagarden_dst.refresh.sources.bgc_light import CopernicusBgcLight
from seagarden_dst.refresh.sources.phy import CopernicusPhy
from seagarden_dst.refresh.sources.wav import CopernicusWav

# `emodnet_bathy` is package C-c2 and is deliberately absent. Until it lands, a
# refresh built from this registry produces seven of the nine variables and the
# manifest's every-variable-claimed-exactly-once validator will refuse it — which is
# correct: an artifact missing its depth fields should not be writable.
REGISTRY: dict[str, Layer] = {
    layer.name: layer
    for layer in (
        CopernicusPhy(),
        CopernicusBgc(),
        CopernicusBgcLight(),
        CopernicusWav(),
    )
}

def check_registered_names(registry: dict[str, Layer], names: tuple[str, ...]) -> None:
    """Refuse a registry holding a layer C§5 does not name.

    A function rather than a bare `if` at module scope so that a test can call it
    with a bad registry and watch it fire. The guard was previously inline and
    unreachable from any test: nothing could construct the failing case without
    monkeypatching a module constant and re-importing, so the argument it makes for
    itself went unchecked. It matters more at C-c2, where the comparison tightens.

    A `raise`, not an `assert`: module-scope asserts vanish under `python -O`, and a
    guard that disappears under an optimisation flag is a guard that cannot fail.

    The comparison is `<=` and not `==` only because `emodnet_bathy` is still to
    come; C-c2's first task tightens it to equality, at which point a registered
    layer C§5 does not name, OR a named layer nobody registered, fails at import.
    """
    unknown = sorted(set(registry) - set(names))
    if unknown:
        raise RuntimeError(f"registered layers {unknown} are not named in LAYER_NAMES (C§5)")


check_registered_names(REGISTRY, LAYER_NAMES)
