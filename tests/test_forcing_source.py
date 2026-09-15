"""The seam the data layer substitutes into.

`GriddedForcing` will implement this protocol in package D. Nothing in shellfish,
nutrients or suitability may reach for the placeholder dictionary directly; growth,
suitability, the api and scenarios modules all take their forcing through the
protocol, with the concrete default injected at each one's own boundary rather than
imported once and passed down implicitly.
"""

from __future__ import annotations

import numpy as np
import pytest

from seagarden_dst import PLACEHOLDER_SITES, SiteContext, assess_site, default_parameters
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
    """A narrow, real check, not a proof of the dependency direction in general.

    A module that imported `PLACEHOLDER_SITES` directly would fail this. It would
    not catch indirect access (a helper re-exporting the dict, or a string built at
    runtime), so this complements rather than replaces reviewing that these modules'
    call sites take their conditions through `ForcingSource` alone.
    """
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


def test_assess_site_threads_an_injected_forcing_source_to_the_model():
    """Fix round 1: the public entry point, not just `harvest_biomass` directly.

    Before this test, `SiteContext.from_region(region, forcing=stub)` worked - the
    site anchors came from `stub` - but `assess_site` had no `forcing` parameter at
    all, so the seasonal series driving the growth model still came from
    `DEFAULT_FORCING`'s invented sinusoid. That produces a result half derived from
    the injected source and half from the placeholder, with nothing in
    `SiteAssessment.caveats` marking the mismatch - unmarked, not merely wrong.

    Passing succeeds either way; the two assertions on `stub` are what would catch a
    regression where `forcing` is accepted but silently dropped somewhere in
    `assess_site -> _assess_one -> suitability.assess -> assess_growth ->
    harvest_biomass` or `-> harvest_biomass` directly.
    """

    class RecordingForcing:
        conditions_calls = 0
        forcing_calls = 0

        def conditions_for(self, region):
            type(self).conditions_calls += 1
            return DEFAULT_FORCING.conditions_for(region)

        def daily_forcing(self, site, window):
            type(self).forcing_calls += 1
            days = np.arange(1.0, 101.0)
            return days, np.full(100, 200.0), np.full(100, 12.0), np.full(100, 5.0)

    baseline = assess_site(SiteContext.from_region("EE-coastal"), species=["fucus_vesiculosus"])

    stub = RecordingForcing()
    ctx = SiteContext.from_region("EE-coastal", forcing=stub)
    result = assess_site(ctx, species=["fucus_vesiculosus"], forcing=stub)

    assert stub.conditions_calls == 1, "SiteContext.from_region never consulted the stub"
    # Exactly two: the growth-viability constraint (assess -> assess_growth ->
    # harvest_biomass) and the headline harvest (the direct harvest_biomass call in
    # _assess_one). A weaker ">= 1" would still pass if either link dropped
    # `forcing=forcing`, leaving that one number silently mixed with the placeholder.
    assert stub.forcing_calls == 2, "not every consumer of the seasonal series saw the stub"
    assert result.best is not None and baseline.best is not None
    assert result.best.harvest.value != baseline.best.harvest.value, (
        "the injected seasonal series must move the number, not just be accepted and ignored"
    )


def test_compare_threads_an_injected_forcing_source():
    """`compare()` is the outermost public entry on the scenarios side, exactly as
    `assess_site` is on the api side - a call path the coordinator's finding did not
    name but that has the identical hazard: a `Scenario` built from real conditions
    plus an un-threaded `compare()` would still season the harvest with the
    placeholder. `evaluate()` alone is not enough - `compare()` must accept and
    forward the same `forcing` too.
    """
    from seagarden_dst import Scenario, compare

    class RecordingForcing:
        forcing_calls = 0

        def conditions_for(self, region):
            return DEFAULT_FORCING.conditions_for(region)

        def daily_forcing(self, site, window):
            type(self).forcing_calls += 1
            days = np.arange(1.0, 101.0)
            return days, np.full(100, 200.0), np.full(100, 12.0), np.full(100, 5.0)

    params = default_parameters()
    scenario = Scenario(
        label="x",
        species=params.species["fucus_vesiculosus"],
        method=params.methods["mini_farm_kit"],
        site=PLACEHOLDER_SITES["EE-coastal"],
        area_m2=6.0,
    )

    stub = RecordingForcing()
    compare([scenario], forcing=stub)

    # Same two consumers as assess_site's chain: assess -> assess_growth ->
    # harvest_biomass, and evaluate's own headline harvest_biomass call.
    assert stub.forcing_calls == 2, "compare() did not forward forcing to evaluate()"
