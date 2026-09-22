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
from seagarden_dst.forcing import placeholder_choice


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
        self.forcing = _Value(placeholder_choice("test: no artifact"))


def _artifact_choice():
    from datetime import UTC, datetime

    from seagarden_dst.forcing import DEFAULT_FORCING, ForcingChoice

    return ForcingChoice(
        source=DEFAULT_FORCING, kind="artifact", reason="", year=2025,
        built_on=datetime(2026, 9, 22, tzinfo=UTC), directory=None,
    )


def test_state_carries_the_forcing_choice_unset_until_the_session_chooses():
    from shiny import reactive

    state = AppState()
    with reactive.isolate():
        assert state.forcing.get() is None
    assert AppState.defaults()["forcing"] is None


def test_a_region_with_a_coordinate_commits_through_the_readers_reading():
    from app.modules.site import build_site_context
    from seagarden_dst.forcing import (
        DEFAULT_FORCING,
        Aggregation,
        Coverage,
        ForcingChoice,
        SiteQuery,
        SiteReading,
    )

    seen: list[SiteQuery] = []

    class _Reader:
        def reading_at(self, query):
            seen.append(query)
            return SiteReading(
                conditions=DEFAULT_FORCING.reading_at(
                    SiteQuery("", year=2024, region="LT-lagoon")
                ).conditions,
                coverage=Coverage.VALID, year=query.year,
                aggregation=Aggregation.CONTAINING_CELL, from_artifact=True,
            )

        def daily_forcing(self, site, window, year):
            return DEFAULT_FORCING.daily_forcing(site, window, year)

    choice = ForcingChoice(
        source=_Reader(), kind="artifact", reason="", year=2025, built_on=None, directory=None
    )
    context = build_site_context("LT-lagoon", "Curonian", choice)
    assert seen and seen[0].region == "LT-lagoon" and seen[0].year == 2025
    assert seen[0].geometry_wkt.startswith("POINT (")
    assert context.from_artifact is True and context.source_note == ""
    assert context.label == "Curonian" and context.region == "LT-lagoon"


def test_a_region_without_a_coordinate_stays_on_the_placeholder_with_a_note():
    from app.modules.site import build_site_context
    from seagarden_dst.contracts import SOURCE_NOTE_NO_POSITION

    context = build_site_context("LT-coastal", "Melnrage", _artifact_choice())
    assert context.from_artifact is False
    assert context.source_note == SOURCE_NOTE_NO_POSITION
    assert context.region == "LT-coastal"


def test_on_the_placeholder_a_site_commits_as_today_with_no_note():
    from app.modules.site import build_site_context

    context = build_site_context("LT-lagoon", "Curonian", placeholder_choice("no artifact"))
    assert context.from_artifact is False and context.source_note == ""


def test_a_blocked_reading_keeps_the_region_it_was_asked_for():
    from app.modules.site import build_site_context
    from seagarden_dst.forcing import Aggregation, Coverage, ForcingChoice, SiteReading

    class _Blocked:
        def reading_at(self, query):
            return SiteReading(
                conditions=None, coverage=Coverage.CELL_INVALID, year=query.year,
                aggregation=Aggregation.CONTAINING_CELL, nearest_valid_km=2.5,
                from_artifact=True,
            )

        def daily_forcing(self, site, window, year):
            raise AssertionError("not called")

    choice = ForcingChoice(
        source=_Blocked(), kind="artifact", reason="", year=2025, built_on=None, directory=None
    )
    context = build_site_context("LT-lagoon", "Curonian", choice)
    assert context.conditions is None and context.coverage is Coverage.CELL_INVALID
    assert context.region == "LT-lagoon", "the region is known even when the cell is not"


def test_the_assessment_uses_the_chosen_source_unless_the_site_fell_back():
    from app.modules.results import forcing_for
    from seagarden_dst.contracts import SOURCE_NOTE_NO_POSITION
    from seagarden_dst.forcing import DEFAULT_FORCING

    choice = _artifact_choice()
    on_artifact = SiteContext.from_region("LT-lagoon")
    assert forcing_for(on_artifact, choice) is choice.source
    fell_back = SiteContext.from_region("LT-coastal")
    fell_back.source_note = SOURCE_NOTE_NO_POSITION
    assert forcing_for(fell_back, choice) is DEFAULT_FORCING


def test_run_assessment_passes_the_source_through(monkeypatch):
    import app.modules.results as results

    captured = {}

    def fake_assess(context, **kwargs):
        captured.update(kwargs)
        raise RuntimeError("stop here")

    monkeypatch.setattr(results, "assess_site", fake_assess)
    state = _FakeState(SiteContext.from_region("LT-lagoon", label="Curonian"))
    with pytest.raises(RuntimeError, match="stop here"):
        results.run_assessment(state)
    assert captured["forcing"] is state.forcing.get().source


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


def test_an_unassessable_assessment_reads_as_unassessed_not_unsuitable():
    """§7's point. 'We did not look' and 'we looked and it is bad' are different
    answers, and only one of them should stop somebody siting a farm there."""
    from app.modules._widgets import headline_for
    from seagarden_dst import SiteContext
    from seagarden_dst.api import assess_site
    from seagarden_dst.forcing import Aggregation, Coverage, SiteReading

    blocked = SiteReading(
        conditions=None, coverage=Coverage.CELL_INVALID, year=2024,
        aggregation=Aggregation.CONTAINING_CELL, nearest_valid_km=1.1,
        from_artifact=True,
    )
    result = assess_site(SiteContext.from_reading(blocked, label="Off-grid"))
    _cls, text = headline_for(result)
    assert "unassess" in text.lower()
    assert "unsuitable" not in text.lower()


def test_the_banner_names_what_the_tool_is_running_on():
    """§7 row 1: fall back to PlaceholderForcing WITH A BANNER naming the source. A
    silent fallback is the failure — the user cannot tell measurements from inventions."""
    from app.modules._widgets import data_source_banner
    from seagarden_dst.forcing import placeholder_choice

    placeholder = data_source_banner(placeholder_choice("no artifact at data/forcing"))
    assert "placeholder" in placeholder.lower()
    assert "(no artifact at data/forcing)" in placeholder
    artifact = data_source_banner(_artifact_choice())
    assert "placeholder" not in artifact.lower()
    assert "conditions for 2025" in artifact and "built 2026-09-22" in artifact


def test_the_banner_appends_a_sites_own_fallback_note():
    from app.modules._widgets import data_source_banner
    from seagarden_dst import SiteContext

    context = SiteContext.from_region("LT-coastal", label="Melnrage")
    context.source_note = "no confirmed position; conditions are the sub-region placeholder"
    text = data_source_banner(_artifact_choice(), context)
    assert text.endswith(
        "This site: no confirmed position; conditions are the sub-region placeholder."
    )


def test_the_report_line_takes_the_choice_and_falls_back_to_the_context_without_one():
    from app.modules.report import render_report
    from seagarden_dst.forcing import placeholder_choice

    state = _FakeState(SiteContext.from_region("LT-coastal", label="Melnrage"))
    run_assessment(state)
    with_choice = render_report(state.assessment.get(), placeholder_choice("no artifact at x"))
    assert "Data source: placeholder conditions (no artifact at x)" in with_choice
    without = render_report(state.assessment.get())
    assert "Data source: placeholder conditions" in without


def test_source_note_reaches_the_json_export():
    state = _FakeState(SiteContext.from_region("LT-coastal", label="Melnrage"))
    state.context.get().source_note = (
        "no confirmed position; conditions are the sub-region placeholder"
    )
    run_assessment(state)
    site = state.assessment.get().to_dict()["site"]
    assert site["source_note"].startswith("no confirmed position")



# --- Brand theme ------------------------------------------------------------------


def _page_html() -> str:
    from app.app import app_ui

    return str(app_ui)


def test_the_brand_stylesheet_is_inlined_into_the_page():
    """Inlined, not linked: the app runs behind a sub-path proxy and offline, and a
    stylesheet that 404s degrades silently to stock Bootstrap."""
    html = _page_html()
    assert "--sg-navy" in html, "brand tokens missing: the stylesheet is not inlined"
    assert "seagarden.css" not in html, "the stylesheet is linked, not inlined"


def test_the_navbar_brand_carries_the_icon_mark():
    html = _page_html()
    assert 'class="sg-logo"' in html
    assert "data:image/png;base64," in html, "the icon is not inlined"


def test_the_funding_lockup_is_shown():
    """Interreg's communication rules: the programme logo and the EU co-funding
    statement must be visible on every digital product. The lockup is dark-on-white,
    so it lives on a white strip, not in the navy bar."""
    html = _page_html()
    assert 'class="sg-funding"' in html
    assert "Interreg South Baltic" in html and "European Union" in html


def test_tier_and_verdict_widgets_are_styled_by_class_not_inline_colour():
    """The semantic colours belong to the stylesheet's tokens. An inline hex on the
    badge cannot follow the theme, and this is the badge users read the tier from."""
    from app.modules._widgets import tier_badge, verdict_pill
    from seagarden_dst import Tier

    badge = str(tier_badge(Tier.D))
    assert 'class="sg-tier sg-tier-d"' in badge
    assert "style=" not in badge
    pill = str(verdict_pill("unsuitable"))
    assert 'class="sg-verdict sg-verdict-unsuitable"' in pill
    assert "style=" not in pill


def test_no_app_module_hard_codes_a_colour_in_an_inline_style():
    """Colours live in app/www/seagarden.css. A hex literal in a `style=` attribute is
    a colour the theme cannot reach."""
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parents[1]
    offenders = []
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts or path.parts[-2] == "tests":
            continue
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"#[0-9a-fA-F]{3,8}\b", line) and "style" in line:
                offenders.append(f"{path.relative_to(root)}:{i}")
    assert not offenders, f"inline colours: {offenders}"
