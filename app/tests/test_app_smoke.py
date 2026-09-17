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


# --- Site map -------------------------------------------------------------------

def test_every_positioned_region_gets_a_marker_and_no_other_does():
    """The map offers exactly the sub-regions that have a coordinate.

    Not all seven: `SITE_COORDINATES` omits a region entirely where nobody has chosen
    a cell, so a marker for one would be a position invented by the UI.
    """
    from app.modules.site import site_markers
    from seagarden_dst.forcing import SITE_COORDINATES

    marked = {m["region"] for m in site_markers()}
    assert marked == set(SITE_COORDINATES)


def test_the_regions_without_a_position_are_still_reachable():
    """A map-only picker would strand them; the selector lists all seven."""
    from app.modules.site import regions_without_a_position
    from seagarden_dst import REGIONS

    absent = regions_without_a_position()
    assert absent, "expected at least one region with conditions but no coordinate"
    assert set(absent) <= set(REGIONS)
    assert set(absent).isdisjoint({m["region"] for m in _markers()})


def test_every_marker_states_its_provenance():
    """`SiteProvenance` exists so a coordinate cannot travel without saying where it
    came from, and a map pin is the most 'this was surveyed' presentation there is."""
    from seagarden_dst.forcing import SITE_COORDINATES

    for marker in _markers():
        coordinate = SITE_COORDINATES[marker["region"]]
        assert marker["provenance"] == coordinate.provenance.value
        assert marker["provenance_label"] == coordinate.provenance.label
        assert marker["presentation"] == coordinate.provenance.presentation


def test_marker_positions_are_lon_lat_and_match_the_coordinate():
    """deck.gl wants [lon, lat]; the human habit is lat/lon. Swapping them puts every
    Baltic site in Somalia, which looks like a map bug rather than a data bug."""
    from seagarden_dst.forcing import SITE_COORDINATES

    for marker in _markers():
        coordinate = SITE_COORDINATES[marker["region"]]
        lon, lat = marker["position"]
        assert (lon, lat) == (coordinate.lon, coordinate.lat)
        assert 9.0 < lon < 30.0, "longitude outside the Baltic"
        assert 53.0 < lat < 60.0, "latitude outside the Baltic"


def test_the_three_provenances_are_visually_distinguishable():
    from app.modules.site import _PROVENANCE_COLOUR

    colours = [tuple(c[:3]) for c in _PROVENANCE_COLOUR.values()]
    assert len(set(colours)) == len(colours), "two provenances share a colour"


def test_better_known_positions_draw_last():
    """Where markers overlap, a confirmed position must not be hidden by a
    representative one."""
    from seagarden_dst.forcing import SiteProvenance

    rank = {
        SiteProvenance.INDICATIVE.value: 0,
        SiteProvenance.SNAPPED.value: 1,
        SiteProvenance.SITED.value: 2,
    }
    order = [rank[m["provenance"]] for m in _markers()]
    assert order == sorted(order)


def test_a_click_payload_without_a_region_moves_nothing():
    """The pick payload's shape is not a contract this repository controls, so a miss
    must leave the selector alone rather than raise inside a reactive effect."""
    from app.modules.site import _region_from_click

    assert _region_from_click(None) is None
    assert _region_from_click({}) is None
    assert _region_from_click({"object": {}}) is None
    assert _region_from_click({"object": {"region": "LT-lagoon"}}) == "LT-lagoon"
    assert _region_from_click({"region": "PL-coastal"}) == "PL-coastal"


def _markers():
    from app.modules.site import site_markers

    return site_markers()


def test_the_site_panel_renders_without_shiny_deckgl(monkeypatch):
    """CI installs with pip and `shiny_deckgl` ships on a conda channel, so the panel
    has to build without it. Setting the module to None in sys.modules makes `import
    shiny_deckgl` raise ImportError, which is what a pip-only install does."""
    import sys

    import app.modules.site as site

    monkeypatch.setitem(sys.modules, "shiny_deckgl", None)
    assert site.map_is_available() is False
    assert site.site_ui("site") is not None


def test_no_app_module_imports_shiny_deckgl_at_module_scope():
    """A module-scope import anywhere under app/ turns CI's [app,dev] job red, because
    app/tests imports these modules and collection happens before any marker can
    deselect anything.

    Scans the whole tree on purpose. The first version of this guard scanned only
    modules/site.py, which is the file I was thinking about — and app/shell.py had the
    same import, so CI stayed red and the test stayed green. A guard scoped to one file
    defends one file, not the property.
    """
    import ast
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    offenders = []
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        for node in ast.parse(path.read_text(encoding="utf-8")).body:  # top level only
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            if any(n.split(".")[0] == "shiny_deckgl" for n in names):
                offenders.append(f"{path.relative_to(root)}:{node.lineno}")
    assert not offenders, f"shiny_deckgl imported at module scope: {offenders}"


