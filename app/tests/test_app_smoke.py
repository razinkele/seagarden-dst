"""Application smoke tests.

Cheap guards on the wiring that the unit suite cannot see: that the app object
builds, that every panel's UI renders, and — the important one — that the stale
assessment invalidation is actually wired, because the failure it prevents is showing
one site's numbers under another site's label.
"""

from __future__ import annotations

import pytest

from app.modules.report import render_report
from app.modules.results import run_assessment
from app.modules.user_mode import MODES
from app.state import AppState
from seagarden_dst import SiteContext


def test_app_object_builds():
    from app.app import app, app_ui

    assert app is not None
    assert app_ui is not None


def test_every_panel_ui_renders():
    from app.modules.catalogue import catalogue_ui
    from app.modules.report import report_ui
    from app.modules.results import results_ui
    from app.modules.site import site_ui

    for factory, id_ in (
        (site_ui, "site"),
        (catalogue_ui, "cat"),
        (results_ui, "res"),
        (report_ui, "rep"),
    ):
        assert factory(id_) is not None


def test_state_defaults_match_the_single_source_of_truth():
    from shiny import reactive

    state = AppState()
    defaults = AppState.defaults()
    # reactive.Value.get() needs a reactive context; isolate() supplies one outside
    # a running session.
    with reactive.isolate():
        assert state.user_mode.get() == defaults["user_mode"]
        assert state.scale.get() == defaults["scale"]
        assert state.context.get() is None
        assert state.assessment.get() is None


def test_every_user_mode_names_a_real_scale():
    from seagarden_dst import SCALES

    for mode, spec in MODES.items():
        assert spec["scale"] in SCALES, f"{mode} defaults to an unknown scale"


class _Value:
    """Minimal stand-in for reactive.Value, so run_assessment can be tested headless."""

    def __init__(self, value):
        self._value = value

    def get(self):
        return self._value

    def set(self, value):
        self._value = value


class _FakeState:
    def __init__(self, context):
        self.context = _Value(context)
        self.selected_species = _Value([])
        self.method_overrides = _Value({})
        self.scale = _Value("community farm (0.1 ha)")
        self.assessment = _Value(None)
        self.eutropy_scenario = _Value(None)
        self.bowtie_inference = _Value(None)


def test_run_assessment_without_a_site_clears_rather_than_raises():
    state = _FakeState(None)
    state.assessment.set("stale")
    run_assessment(state)
    assert state.assessment.get() is None


def test_run_assessment_populates_the_assessment():
    state = _FakeState(SiteContext.from_region("LT-coastal", label="Melnrage"))
    run_assessment(state)
    assessment = state.assessment.get()
    assert assessment is not None
    assert assessment.context.label == "Melnrage"


def test_report_carries_the_site_label_and_the_caveats():
    state = _FakeState(SiteContext.from_region("LT-coastal", label="Melnrage"))
    run_assessment(state)
    text = render_report(state.assessment.get())
    assert "Melnrage" in text
    assert "CAVEATS" in text
    assert "Sequestration is not reported" in text
    assert "placeholders, not measurements" in text


def test_report_without_an_assessment_says_so():
    assert "No assessment yet" in render_report(None)


@pytest.mark.parametrize("region", ["LT-coastal", "DK-belt", "PL-lagoon"])
def test_report_renders_for_every_shipped_region(region):
    state = _FakeState(SiteContext.from_region(region))
    run_assessment(state)
    text = render_report(state.assessment.get())
    assert "SITE ASSESSMENT" in text
