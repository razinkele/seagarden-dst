"""The one place the source list lives (C§5).

Both the driver and the probe job read this, so a layer added in C-c appears in the
refresh and in the monthly reachability check without being registered twice.
"""

from __future__ import annotations

from seagarden_dst.refresh.layer import Layer

# Empty until package C-c implements the five layers. The driver and the CLI are
# written against the mapping, not against its contents, which is what lets both be
# proven against synthetic layers before a single Copernicus call exists.
#
# An EMPTY registry is not a valid state for the probe job: see the guard in
# scripts/refresh_layers.py, which refuses rather than reporting nothing green.
REGISTRY: dict[str, Layer] = {}
