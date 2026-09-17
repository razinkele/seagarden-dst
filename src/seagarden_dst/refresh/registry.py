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
from seagarden_dst.refresh.sources.phy import CopernicusPhy
from seagarden_dst.refresh.sources.wav import CopernicusWav

# `emodnet_bathy` is not yet implemented and is deliberately absent — it needs a
# spike before it can be planned (C§12 calls its fetch and probe the
# least-specified part of the design). Until it lands, a refresh built from this
# registry produces seven of the nine variables and the manifest's
# every-variable-claimed-exactly-once validator will refuse it — which is correct:
# an artifact missing its depth fields should not be writable.
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
    itself went unchecked. It matters more once `emodnet_bathy` registers and the
    comparison tightens to equality.

    A `raise`, not an `assert`: module-scope asserts vanish under `python -O`, and a
    guard that disappears under an optimisation flag is a guard that cannot fail.

    The comparison is `<=` and not `==` only because `emodnet_bathy` is still to
    come. An earlier version of this docstring said C-c2's FIRST task tightens it to
    equality. That was wrong twice over: C-c2 is the catalogue probe and does not
    add a layer at all, and tightening before `emodnet_bathy` exists would raise at
    import, because `set(LAYER_NAMES) - set(REGISTRY)` is `{'emodnet_bathy'}` — the
    whole suite would go red at collection. The tightening belongs in the SAME
    commit that registers the layer, never before it.
    """
    unknown = sorted(set(registry) - set(names))
    if unknown:
        raise RuntimeError(f"registered layers {unknown} are not named in LAYER_NAMES (C§5)")


check_registered_names(REGISTRY, LAYER_NAMES)
