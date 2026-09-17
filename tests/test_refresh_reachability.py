"""The probe path, which must work with the bare package installed (R4)."""

from __future__ import annotations

import urllib.error

import pytest

from seagarden_dst.refresh.sources.reachability import url_reachable


class _FakeResponse:
    def __init__(self, status: int) -> None:
        self.status = status

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def test_a_200_is_reachable():
    reachable, detail = url_reachable(
        "https://example.invalid/x",
        opener=lambda *a, **k: _FakeResponse(200),
    )
    assert reachable is True
    assert "200" in detail


def test_a_404_is_not_reachable_and_says_so():
    def raise_404(*args: object, **kwargs: object) -> None:
        raise urllib.error.HTTPError("https://example.invalid/x", 404, "Not Found", {}, None)

    reachable, detail = url_reachable("https://example.invalid/x", opener=raise_404)
    assert reachable is False
    assert "404" in detail


def test_a_network_failure_is_reported_not_raised():
    def raise_urlerror(*args: object, **kwargs: object) -> None:
        raise urllib.error.URLError("name resolution failed")

    reachable, detail = url_reachable("https://example.invalid/x", opener=raise_urlerror)
    assert reachable is False
    assert "unreachable" in detail


# --- The four real layers' probe(), through the reachability_opener seam ---------
#
# Every layer class takes a `reachability_opener` for exactly this: proving C§8.2's
# probe path offline, with no network and no credential. Until these tests existed
# the parameter appeared in no test at all, so a wrong `SOURCE_URL`, a `ProbeResult`
# carrying the wrong `name`, or an exception escaping `probe()` were all invisible.
#
# Unmarked, and in this file rather than in `test_refresh_sources.py`, because the
# probe path must work with the BARE package installed (R3/R4) —
# `test_refresh_sources.py` is marked `spatial` and would not run where the probe
# does. `probe()` itself touches neither xarray nor copernicusmarine.


def _layer_classes():
    """The four classes, imported lazily so a collection error names the layer."""
    from seagarden_dst.refresh.sources.bgc import CopernicusBgc
    from seagarden_dst.refresh.sources.bgc_light import CopernicusBgcLight
    from seagarden_dst.refresh.sources.phy import CopernicusPhy
    from seagarden_dst.refresh.sources.wav import CopernicusWav

    return {
        "copernicus_phy": CopernicusPhy,
        "copernicus_bgc": CopernicusBgc,
        "copernicus_bgc_light": CopernicusBgcLight,
        "copernicus_wav": CopernicusWav,
    }


def _probe_with_a_recording_opener(layer_class):
    """Probe one layer, returning `(result, requested_url)`.

    `url_reachable` wraps the URL in a `urllib.request.Request` before handing it to
    the opener, so the fake reads `.full_url` rather than a bare string — asserting
    on a positional string would pass for the wrong reason.
    """
    seen: list[str] = []

    def recording_opener(request, **kwargs):
        seen.append(request.full_url)
        return _FakeResponse(200)

    layer = layer_class(reachability_opener=recording_opener)
    return layer.probe(), seen[0]


@pytest.mark.parametrize("layer_name", sorted(_layer_classes()))
def test_each_layer_probes_its_own_product_and_names_itself(layer_name):
    """C§8.2: the result must identify the layer, and the URL must be its product.

    A `ProbeResult` carrying another layer's `name` would misattribute a dead source
    in the monthly report, and a `SOURCE_URL` pointing at the wrong product would
    report a live catalogue for a layer whose data had gone.
    """
    layer_class = _layer_classes()[layer_name]
    result, url = _probe_with_a_recording_opener(layer_class)

    assert result.name == layer_name
    assert result.reachable is True
    # PRODUCT_ID, not DATASET_ID: the probe HEADs the product landing page.
    import importlib

    module = importlib.import_module(layer_class.__module__)
    assert module.PRODUCT_ID in url


@pytest.mark.parametrize("layer_name", sorted(_layer_classes()))
def test_a_layer_whose_source_is_unreachable_reports_it_rather_than_raising(layer_name):
    """One dead source must not fail the job for the other four (C§8.2).

    `urllib.error.URLError` and not some arbitrary exception: `url_reachable`
    catches an ENUMERATED set (`HTTPError`, `URLError`, `TimeoutError`, `OSError`),
    not everything. Widening that set is out of scope for this wave, so this test
    asserts the contract as written rather than the one it might be mistaken for.
    """
    layer_class = _layer_classes()[layer_name]

    def raise_urlerror(*args: object, **kwargs: object) -> None:
        raise urllib.error.URLError("name resolution failed")

    result = layer_class(reachability_opener=raise_urlerror).probe()

    assert result.name == layer_name
    assert result.reachable is False
    assert "unreachable" in result.detail


def test_the_module_imports_without_the_spatial_stack(monkeypatch):
    """R3/R4: nothing on the probe path may need xarray or copernicusmarine."""
    import sys

    monkeypatch.setitem(sys.modules, "xarray", None)
    monkeypatch.setitem(sys.modules, "copernicusmarine", None)
    import importlib

    import seagarden_dst.refresh.sources.reachability as module

    importlib.reload(module)  # would raise if either import were at module scope
    assert module.url_reachable is not None
