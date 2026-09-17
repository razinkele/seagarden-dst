"""The C§3.2 variable table, in one place, and the check that enforces it.

`artifact.pair.check_declaration` compares variable NAMES and cannot see a shape. A
layer that emitted `("lat", "lon")` instead of `("latitude", "longitude")` would pass
every name check, collapse the `valid` intersection to a 0-d scalar, and write that to
disk without a word. C§5 asks the driver to validate "the expected variable set AND
shapes"; this module is the second half (R7).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    import xarray as xr

# Spelled out. The spec's C§3.2 dims column abbreviates; its coordinates line does not,
# and neither do tests/refresh_builders.py or the committed fixture.
SPATIAL_DIMS: tuple[str, str] = ("latitude", "longitude")

_YEARLY = ("year", "month", "latitude", "longitude")
_MONTHLY = ("month", "latitude", "longitude")
_STATIC = ("latitude", "longitude")

# Three shapes, not two (C§3.2). `significant_wave_m` is monthly-only because it is a
# p95 collapsed over its 2023-2025 window, and `valid` is static because it is a mask.
EXPECTED_DIMS: dict[str, tuple[str, ...]] = {
    "salinity_psu": _YEARLY,
    "temp_c": _YEARLY,
    "din_umol_l": _YEARLY,
    "dip_umol_l": _YEARLY,
    "light_attenuation_k": _YEARLY,
    "significant_wave_m": _MONTHLY,
    "depth_mean_m": _STATIC,
    "depth_min_m": _STATIC,
    "valid": _STATIC,
}


def check_shapes(dataset: xr.Dataset) -> None:
    """Every variable carries the dims C§3.2 gives it, in that order."""
    for name, variable in dataset.data_vars.items():
        expected = EXPECTED_DIMS.get(str(name))
        if expected is None:
            raise ValueError(
                f"variable '{name}' has no declared shape in C§3.2, so nothing here "
                "can say whether what was built is right; add it to EXPECTED_DIMS or "
                "stop building it"
            )
        if tuple(variable.dims) != expected:
            raise ValueError(
                f"variable '{name}' has dims {tuple(variable.dims)}, expected dims "
                f"{expected}. check_declaration compares names only, so a wrong shape "
                "reaches disk silently unless it is caught here"
            )
