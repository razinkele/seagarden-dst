"""Package C's own variable set (C§3.2).

NOT in `artifact/`. C§4.3 has package D and package C1 importing the same manifest
models, and C1's GeoPackage carries human-use and exclusion vectors — none of the nine
below. Nine forcing-variable names in that shared module would make every C1 manifest
unloadable, so the manifest resolves its rules against `Manifest.variables` instead and
this constant stays on the write side, where the driver asserts the artifact it just
built against it.
"""

from __future__ import annotations

# The nine variables the artifact carries (C§3.2). `surface_par` is deliberately
# absent and is recorded in `absent`, not here.
ARTIFACT_VARIABLES: frozenset[str] = frozenset({
    "salinity_psu", "temp_c", "din_umol_l", "dip_umol_l", "light_attenuation_k",
    "significant_wave_m", "depth_mean_m", "depth_min_m", "valid",
})
