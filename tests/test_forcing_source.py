"""The seam the data layer substitutes into.

`GriddedForcing` will implement this protocol in package D. Nothing in shellfish,
nutrients or suitability may reach for the placeholder dictionary; growth takes its
forcing through the protocol, with the concrete default injected at the boundary.
"""

from __future__ import annotations

import numpy as np
import pytest

from seagarden_dst import PLACEHOLDER_SITES, SiteContext, default_parameters
from seagarden_dst.forcing import DEFAULT_FORCING, ForcingSource, PlaceholderForcing
from seagarden_dst.growth import harvest_biomass


def test_placeholder_satisfies_the_protocol():
    assert isinstance(PlaceholderForcing(), ForcingSource)


def test_the_default_source_is_the_placeholder():
    assert isinstance(DEFAULT_FORCING, PlaceholderForcing)


def test_a_stub_source_can_be_substituted():
    """The point of the seam: a source the core has never heard of must work."""

    class FlatForcing:
        def conditions_for(self, region):
            return DEFAULT_FORCING.conditions_for(region)

        def daily_forcing(self, site, window):
            days = np.arange(1.0, 101.0)
            return days, np.full(100, 200.0), np.full(100, 12.0), np.full(100, 5.0)

    assert isinstance(FlatForcing(), ForcingSource)


def test_no_model_module_imports_a_concrete_source():
    """The dependency direction is the whole point."""
    import inspect

    from seagarden_dst import nutrients, shellfish, suitability

    for module in (shellfish, nutrients, suitability):
        source = inspect.getsource(module)
        assert "PLACEHOLDER_SITES" not in source, f"{module.__name__} reaches for the stub"


def test_an_injected_source_reaches_the_model_through_harvest_biomass():
    """Correction 1: `harvest_biomass` is the call site that makes the seam reachable.

    A stub the core has never heard of must both be called exactly once (proving the
    injection landed, not just that a default ran unnoticed) and must move the number
    (proving it is actually driving `growth.simulate`, not merely accepted and ignored).
    """

    class RecordingForcing:
        calls = 0

        def conditions_for(self, region):
            return DEFAULT_FORCING.conditions_for(region)

        def daily_forcing(self, site, window):
            type(self).calls += 1
            days = np.arange(1.0, 101.0)
            return days, np.full(100, 200.0), np.full(100, 12.0), np.full(100, 5.0)

    params = default_parameters()
    fucus = params.species["fucus_vesiculosus"]
    site = PLACEHOLDER_SITES["EE-coastal"]

    baseline = harvest_biomass(fucus, site, area_m2=100.0)

    stub = RecordingForcing()
    injected = harvest_biomass(fucus, site, area_m2=100.0, forcing=stub)

    assert stub.calls == 1
    assert injected.value != baseline.value


def test_an_injected_source_reaches_site_context_from_region():
    """Correction 2: `SiteContext.from_region` takes its forcing through the protocol."""

    sentinel = DEFAULT_FORCING.conditions_for("LT-coastal")

    class SentinelForcing:
        def conditions_for(self, region):
            return sentinel

        def daily_forcing(self, site, window):
            raise AssertionError("not needed for this test")

    context = SiteContext.from_region("LT-coastal", forcing=SentinelForcing())
    assert context.conditions is sentinel


def test_unknown_region_still_raises_key_error_through_the_placeholder():
    with pytest.raises(KeyError, match="No placeholder conditions"):
        PlaceholderForcing().conditions_for("XX-nowhere")
