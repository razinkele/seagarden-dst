"""Whether a source still answers, using the standard library only (C§8.2, R4).

The monthly probe workflow installs the BARE package — `.github/workflows/
source-probe.yml` runs `pip install -e .` with no `[spatial]` extra — so nothing on
the probe path may import `copernicusmarine` or `xarray`. A reachability check that
needed the scientific stack would depend on the very thing it exists to avoid
needing, and would report a broken environment as a broken catalogue.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from collections.abc import Callable

# Long enough for a slow catalogue, short enough that five dead sources do not hang
# a monthly job past its timeout.
DEFAULT_TIMEOUT: float = 30.0


def url_reachable(
    url: str,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    opener: Callable[..., object] | None = None,
) -> tuple[bool, str]:
    """Ask whether `url` answers. Returns `(reachable, detail)`, never raises.

    `opener` is the injection seam: tests pass a callable, production gets
    `urllib.request.urlopen`. A probe that raised would turn one dead source into a
    failed job reporting nothing about the other four.
    """
    open_url = opener if opener is not None else urllib.request.urlopen
    request = urllib.request.Request(url, method="HEAD")
    try:
        with open_url(request, timeout=timeout) as response:  # type: ignore[union-attr]
            status = getattr(response, "status", None)
    except urllib.error.HTTPError as error:
        return False, f"HTTP {error.code}"
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        return False, f"unreachable: {error}"

    if status is not None and 200 <= int(status) < 400:
        return True, f"HTTP {status}"
    return False, f"HTTP {status}"
