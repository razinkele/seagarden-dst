"""Catalogue panel - choose what to grow, how, and at what scale.

The species and method catalogues come from `params/`, which is data rather than
code, so adding a species is a YAML file and not a release.
"""

from __future__ import annotations

from shiny import module, reactive, render, ui

from app.i18n import Translator
from seagarden_dst import DEFAULT_SCALE, SCALE_LABELS, default_parameters

from ._widgets import window_label

PARAMS = default_parameters()
AF_SPECIES = [k for k, v in PARAMS.species.items() if v.in_application_form]


def species_choices(tr: Translator) -> dict[str, str]:
    return {k: tr.species_name(k) for k in PARAMS.species}


def scale_choices(tr: Translator) -> dict[str, str]:
    return {k: tr.render(v) for k, v in SCALE_LABELS.items()}


@module.ui
def catalogue_ui(tr: Translator) -> ui.TagList:
    # `ui.layout_sidebar` returns a `CardItem`, which only tagifies nested inside a
    # `ui.card()` or a page - wrapped in `ui.TagList` so this panel also renders
    # standalone (the pure-render tests call it directly, outside `app_shell`).
    return ui.TagList(ui.layout_sidebar(
        ui.sidebar(
            ui.input_checkbox_group(
                "species",
                tr("app.catalogue.species"),
                choices=species_choices(tr),
                selected=list(PARAMS.species),
            ),
            ui.input_select(
                "scale",
                tr("app.catalogue.scale"),
                choices=scale_choices(tr),
                selected=DEFAULT_SCALE,
            ),
            ui.input_action_link("only_af", tr("app.catalogue.only_af")),
            width=340,
        ),
        ui.card(ui.card_header(tr("app.catalogue.species")), ui.output_ui("species_table")),
        ui.card(ui.card_header(tr("app.catalogue.methods")), ui.output_ui("method_table")),
    ))


def species_table(tr: Translator) -> ui.TagList:
    rows = []
    for key, species in PARAMS.species.items():
        named = tr("app.catalogue.yes" if species.in_application_form else "app.catalogue.no")
        rows.append(
            ui.tags.tr(
                ui.tags.td(ui.tags.b(tr.species_name(key))),
                ui.tags.td(ui.tags.em(species.scientific_name)),
                ui.tags.td(tr.group_label(species.group)),
                ui.tags.td(named),
                ui.tags.td(window_label(species.cultivation_window, tr)),
            )
        )
    headers = ("species", "scientific", "group", "in_af", "window")
    return ui.TagList(
        ui.tags.table(
            ui.tags.thead(
                ui.tags.tr(
                    *[
                        ui.tags.th(
                            tr(f"app.catalogue.col.{h}"),
                            style="text-align:left;padding-right:1rem;",
                        )
                        for h in headers
                    ]
                )
            ),
            ui.tags.tbody(*rows),
            style="width:100%;font-size:.92em;",
        ),
        ui.p(ui.tags.small(tr("app.catalogue.species_note"))),
    )


def method_table(tr: Translator) -> ui.TagList:
    rows = [
        ui.tags.tr(
            ui.tags.td(ui.tags.b(tr.method_name(key))),
            ui.tags.td(tr.method_field(key, "anchoring_unit")),
            ui.tags.td(tr.method_field(key, "cultivation_unit")),
            ui.tags.td(f"{m.min_depth_m:g}-{m.max_depth_m:g} m"),
            ui.tags.td(f"{m.max_significant_wave_m:g} m"),
            ui.tags.td(f"{m.area_m2_per_unit:g} m²"),
        )
        for key, m in PARAMS.methods.items()
    ]
    headers = ("method", "anchoring", "cultivation", "depth", "max_wave", "unit_area")
    return ui.TagList(
        ui.tags.table(
            ui.tags.thead(
                ui.tags.tr(
                    *[
                        ui.tags.th(
                            tr(f"app.catalogue.col.{h}"),
                            style="text-align:left;padding-right:1rem;",
                        )
                        for h in headers
                    ]
                )
            ),
            ui.tags.tbody(*rows),
            style="width:100%;font-size:.92em;",
        ),
        ui.p(ui.tags.small(tr("app.catalogue.methods_note"))),
    )


@module.server
def catalogue_server(input, output, session, state) -> None:  # noqa: A002
    @reactive.effect
    @reactive.event(input.species, ignore_none=False)
    def _sync_species():
        state.selected_species.set(list(input.species() or []))

    @reactive.effect
    @reactive.event(input.scale)
    def _sync_scale():
        state.scale.set(input.scale())

    @reactive.effect
    @reactive.event(state.scale)
    def _scale_from_mode():
        # The door's default scale (user_mode) must be reflected in the control, or the
        # sidebar and the panel disagree about what is being assessed.
        if input.scale() != state.scale.get():
            ui.update_select("scale", selected=state.scale.get())

    @reactive.effect
    @reactive.event(input.only_af)
    def _select_af():
        ui.update_checkbox_group("species", selected=AF_SPECIES)

    # Bound by explicit `id=`, not by function name: the pure functions above are
    # also named `species_table`/`method_table` (the interface names them so), and a
    # nested function definition of the same name would shadow them in this closure
    # (Python resolves the reference to itself, not the module-level pure function).
    @output(id="species_table")
    @render.ui
    def _species_table():
        return species_table(state.translator())

    @output(id="method_table")
    @render.ui
    def _method_table():
        return method_table(state.translator())
