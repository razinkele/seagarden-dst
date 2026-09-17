"""The probe path, which must work with the bare package installed (R4)."""

from __future__ import annotations

import urllib.error

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


def test_the_module_imports_without_the_spatial_stack(monkeypatch):
    """R3/R4: nothing on the probe path may need xarray or copernicusmarine."""
    import sys

    monkeypatch.setitem(sys.modules, "xarray", None)
    monkeypatch.setitem(sys.modules, "copernicusmarine", None)
    import importlib

    import seagarden_dst.refresh.sources.reachability as module

    importlib.reload(module)  # would raise if either import were at module scope
    assert module.url_reachable is not None
