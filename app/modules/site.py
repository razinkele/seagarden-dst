"""Site panel - choose where.

A map of the sub-regions that have a position, over the deck.gl/MapLibre bridge, plus
the selector the map cannot replace. Conditions are still `forcing.PLACEHOLDER_SITES`
and the `SiteContext` contract is unchanged, so this module remains the only one that
has to change when the curated layers of specification section 6 arrive.

**Two sub-regions have no coordinate and are reachable only from the selector.**
`SITE_COORDINATES` records position separately from conditions and omits the key
entirely where nobody has chosen a cell - absent rather than None, so no caller can
index a coordinate-shaped default and get a wrong answer. A map alone would therefore
make EE-coastal and LT-coastal unreachable, which is why the selector stays and lists
all seven.

**Every marker carries its provenance.** `SiteProvenance` exists because "a coordinate
that travels without saying where it came from gets promoted to a fact", and a pin on a
map is the most promoting presentation there is: it looks surveyed. Colour, legend and
tooltip all name the provenance, and a snapped or indicative cell says so on the marker
rather than in a caption somebody can miss.
"""

from __future__ import annotations

from shiny import module, reactive, render, ui

from app.i18n import Translator, english
from seagarden_dst import REGIONS, SiteContext
from seagarden_dst.contracts import SOURCE_NOTE_NO_POSITION
from seagarden_dst.forcing import SITE_COORDINATES, ForcingChoice, SiteProvenance, region_query

#: `shiny_deckgl` ships on a conda channel and is NOT a pip dependency (see the comment
#: in `pyproject.toml`'s spatial extra), so an install that followed only the pip
#: instructions will not have it — CI is exactly that install. Imported lazily and
#: degraded rather than required, which is the same treatment the optional sibling
#: engines get: the panel loses its map and keeps its selector, and never fails.
#:
#: A module-scope import here turns CI's `[app,dev]` job red, because `app/tests`
#: imports this module and collection happens before any marker can deselect anything.

#: The map element's bare id. `MapWidget` resolves the Shiny module namespace itself,
#: so the same raw id used in the ui and server halves refers to one element.
_MAP_ID = "sitemap"

#: Centred on the South Baltic so all five positioned sub-regions are in frame at once,
#: from the Great Belt in the west to the Curonian Lagoon in the east.
_BALTIC_VIEW = {"longitude": 16.0, "latitude": 54.9, "zoom": 5.1}

#: RGBA per provenance. Colour is the only channel encoding confidence - marker size is
#: deliberately uniform, because a larger dot for a better-known site reads as a bigger
#: site rather than a better-known one.
_PROVENANCE_COLOUR: dict[SiteProvenance, list[int]] = {
    SiteProvenance.SITED: [17, 122, 101, 235],       # deep teal - somebody confirmed it
    SiteProvenance.SNAPPED: [202, 138, 4, 225],      # amber - moved from what was given
    SiteProvenance.INDICATIVE: [113, 128, 150, 195],  # slate - nobody gave it
}


def site_markers(tr: Translator) -> list[dict]:
    """One marker per sub-region that has a coordinate, richest provenance last.

    Returned as plain dicts so the deck.gl accessors can read them and so this is
    testable without a browser. Sorted so SITED draws over SNAPPED over INDICATIVE
    where markers overlap - the better-known position should not be hidden by a
    representative one.
    """
    order = {
        SiteProvenance.INDICATIVE: 0,
        SiteProvenance.SNAPPED: 1,
        SiteProvenance.SITED: 2,
    }
    markers = []
    for region, coordinate in SITE_COORDINATES.items():
        # Attribute access, never `lat, lon = coordinate`: SiteCoordinate makes
        # unpacking raise precisely so the provenance cannot be dropped in transit.
        markers.append(
            {
                "position": [coordinate.lon, coordinate.lat],
                "region": region,
                "name": tr.render(REGIONS[region]),
                "provenance": coordinate.provenance.value,
                "provenance_label": tr.render(coordinate.provenance.label),
                "presentation": tr.render(coordinate.provenance.presentation),
                "depth": (
                    tr("app.site.depth_unknown")
                    if coordinate.depth_m is None
                    else f"{coordinate.depth_m:g} m"
                ),
                "colour": _PROVENANCE_COLOUR[coordinate.provenance],
            }
        )
    markers.sort(key=lambda m: order[SiteProvenance(m["provenance"])])
    return markers


def regions_without_a_position() -> list[str]:
    """Sub-regions that have conditions but no coordinate, so the map cannot offer them."""
    return sorted(set(REGIONS) - set(SITE_COORDINATES))


def map_is_available() -> bool:
    """Whether `shiny_deckgl` is importable in this install.

    False on a pip-only install, including CI. The panel then shows the selector and a
    note saying what is missing and how to get it, rather than an empty frame.
    """
    try:
        import shiny_deckgl  # noqa: F401
    except ImportError:
        return False
    return True


def build_site_context(region: str, label: str, choice: ForcingChoice) -> SiteContext:
    """What 'Use this site' commits (E§3.5).

    Through the reader when the session runs on the artifact and the region has a
    coordinate; otherwise through the placeholder as before, with a note when that is
    a fallback rather than the session's normal state. A blocked reading keeps the
    region it was asked for: the cell may be unknown, the sub-region is not.

    `choice` is never `None` here: `server()` sets `state.forcing` before any render
    or click handler can run, so every caller of this function already holds a
    real `ForcingChoice`.
    """
    query = region_query(region, choice.year) if choice.is_artifact else None
    if query is None:
        context = SiteContext.from_region(region, label=label)
        if choice.is_artifact:
            context.source_note = SOURCE_NOTE_NO_POSITION
        return context
    context = SiteContext.from_reading(
        choice.source.reading_at(query), label=label, geometry_wkt=query.geometry_wkt
    )
    if context.region is None:
        context.region = region
    return context


def _widget(tr: Translator):
    from shiny_deckgl import MapWidget

    return MapWidget(
        _MAP_ID,
        view_state=_BALTIC_VIEW,
        tooltip={
            # The doubled braces are deck.gl's runtime template, not Python's.
            "html": (
                f"<b>{{name}}</b><br/>{{provenance_label}}<br/>"
                f"{tr('app.site.tooltip_depth')} {{depth}}<br/><i>{{presentation}}</i>"
            ),
            "style": {
                "backgroundColor": "#1b2430",
                "color": "#f2f5f8",
                "fontSize": "0.78rem",
                "padding": "6px 8px",
                "borderRadius": "4px",
                "maxWidth": "260px",
            },
        },
    )


def _legend(tr: Translator) -> ui.Tag:
    swatches = []
    for provenance in (SiteProvenance.SITED, SiteProvenance.SNAPPED, SiteProvenance.INDICATIVE):
        r, g, b, _a = _PROVENANCE_COLOUR[provenance]
        swatches.append(
            ui.tags.span(
                ui.tags.span(
                    style=(
                        f"display:inline-block;width:.6rem;height:.6rem;border-radius:50%;"
                        f"background:rgb({r},{g},{b});margin-right:.35rem;"
                    )
                ),
                ui.tags.small(tr.render(provenance.label)),
                style="margin-right:1.1rem;white-space:nowrap;",
            )
        )
    return ui.div(*swatches, style="margin-top:.5rem;")


def absent_regions_note(tr: Translator) -> str:
    absent = regions_without_a_position()
    if not absent:
        return ""
    names = tr("app.site.and").join(tr.render(REGIONS[r]) for r in absent)
    key = "app.site.help_absent_one" if len(absent) == 1 else "app.site.help_absent_many"
    return tr(key, regions=names)


def render_position_note(region: str, tr: Translator) -> ui.Tag:
    coordinate = SITE_COORDINATES.get(region)
    if coordinate is None:
        return ui.p(ui.tags.small(tr("app.site.no_position", region=REGIONS[region])))
    return ui.p(
        ui.tags.small(
            tr(
                "app.site.position",
                lat=f"{coordinate.lat:.4f}", lon=f"{coordinate.lon:.4f}",
                provenance=tr.render(coordinate.provenance.label).lower(),
                presentation=coordinate.provenance.presentation,
            )
        )
    )


def render_conditions(region: str, tr: Translator) -> ui.TagList:
    c = SiteContext.from_region(region).conditions
    rows = [
        (tr("app.site.cond.salinity"), f"{c.salinity_psu:g} psu"),
        (tr("app.site.cond.mean_temp"), f"{c.mean_temp_c:g} °C"),
        (tr("app.site.cond.summer_winter"), f"{c.summer_temp_c:g} / {c.winter_temp_c:g} °C"),
        (tr("app.site.cond.din"), f"{c.din_umol_l:g} µmol/L"),
        (tr("app.site.cond.dip"), f"{c.dip_umol_l:g} µmol/L"),
        (tr("app.site.cond.depth"), f"{c.depth_m:g} m"),
        (tr("app.site.cond.wave"), f"{c.significant_wave_m:g} m"),
        (tr("app.site.cond.par"), f"{c.par_at_depth():.0f} µmol photons/m²/s"),
    ]
    return ui.TagList(
        ui.tags.table(
            ui.tags.tbody(
                *[
                    ui.tags.tr(
                        ui.tags.td(k, style="padding:.15rem .9rem .15rem 0;opacity:.75;"),
                        ui.tags.td(v, style="padding:.15rem 0;font-variant-numeric:tabular-nums;"),
                    )
                    for k, v in rows
                ]
            ),
            style="width:100%;",
        ),
        ui.p(
            ui.tags.small(
                tr("app.site.confidence_line", confidence=tr.confidence_label("low"), region=region)
            )
        ),
    )


@module.ui
def site_ui(tr: Translator) -> ui.TagList:
    # `ui.layout_sidebar` returns a `CardItem`, which only tagifies nested inside a
    # `ui.card()` or a page - wrapped in `ui.TagList` so this panel also renders
    # standalone (the pure-render tests call it directly, outside `app_shell`).
    return ui.TagList(ui.layout_sidebar(
        ui.sidebar(
            ui.input_select(
                "region",
                tr("app.site.region"),
                choices={k: tr.render(v) for k, v in REGIONS.items()},
                selected="LT-coastal",
            ),
            ui.help_text(tr("app.site.help") + absent_regions_note(tr)),
            ui.input_text(
                "label", tr("app.site.label"), placeholder=tr("app.site.label_placeholder")
            ),
            ui.input_action_button("set_site", tr("app.site.use"), class_="btn-outline-primary"),
            width=340,
        ),
        ui.card(
            ui.card_header(tr("app.site.where")),
            *(
                (_widget(tr).ui(height="420px"), _legend(tr))
                if map_is_available()
                else (ui.markdown(tr("app.site.no_map")),)
            ),
            ui.output_ui("position_note"),
        ),
        ui.card(ui.card_header(tr("app.site.conditions")), ui.output_ui("conditions")),
        ui.card(
            ui.card_header(tr("app.site.provenance_card")),
            ui.markdown(tr("app.site.provenance_body")),
        ),
    ))


@module.server
def site_server(input, output, session, state) -> None:  # noqa: A002
    # `widget` is built once, synchronously, here - not inside a reactive effect: the
    # `_select_clicked_region` decorator below reads `widget.click_input_id` at
    # definition time, so the widget must already exist when this function body runs.
    # That is also before the session's language is known (the Translator reactive.calc
    # needs a reactive context to evaluate), so the tooltip template is fixed in
    # English for the session's lifetime - a known limit of the deck.gl bridge, not a
    # translation gap: every OTHER string this module renders follows `state.translator()`.
    widget = _widget(english()) if map_is_available() else None

    @reactive.effect
    async def _draw_markers():
        if widget is None:
            return
        from shiny_deckgl import scatterplot_layer

        await widget.update(
            session,
            [
                scatterplot_layer(
                    "sites",
                    data=site_markers(state.translator()),
                    getPosition="@@=d.position",
                    getFillColor="@@=d.colour",
                    radiusMinPixels=7,
                    radiusMaxPixels=13,
                    getRadius=2600,
                    stroked=True,
                    getLineColor=[255, 255, 255, 220],
                    lineWidthMinPixels=1.5,
                )
            ],
        )

    if widget is not None:
        # Registered only when there is a map to click. The decorator evaluates
        # `widget.click_input_id` at definition time, so this cannot be a no-op guard
        # inside the body.
        @reactive.effect
        @reactive.event(input[widget.click_input_id], ignore_init=True)
        def _select_clicked_region():
            """Clicking a marker moves the selector; it does not commit the site.

            Committing on click would set a site from a single stray click on a map the
            user was panning. `Use this site` stays the one action that commits, which
            is also what keeps this panel's contract identical to the selector-only
            version.
            """
            payload = input[widget.click_input_id]()
            region = _region_from_click(payload)
            if region in REGIONS:
                ui.update_select("region", selected=region)

    @reactive.effect
    @reactive.event(input.set_site, ignore_init=True)
    # ignore_init: an action-button event fires once at startup, which would commit
    # a site the user never chose and put the app straight into 'Site ready'.
    def _set_site():
        region = input.region()
        label = (input.label() or "").strip() or state.translator().render(REGIONS[region])
        state.context.set(build_site_context(region, label, state.forcing.get()))
        state.site_label.set(label)

    @output
    @render.ui
    def position_note():
        return render_position_note(input.region(), state.translator())

    @output
    @render.ui
    def conditions():
        return render_conditions(input.region(), state.translator())


def _region_from_click(payload: object) -> str | None:
    """Pull the region out of a deck.gl pick payload, tolerating its shape.

    The bridge delivers the picked datum, but which key it sits under is not part of
    any contract this repository controls, so a miss returns None and the selector
    simply does not move - never an exception into a reactive effect, and never a
    silently wrong region.
    """
    if not isinstance(payload, dict):
        return None
    for candidate in (payload, payload.get("object"), payload.get("datum")):
        if isinstance(candidate, dict):
            region = candidate.get("region")
            if isinstance(region, str):
                return region
    return None
