"""Catalogue panel - choose what to grow, how, and at what scale.

The species and method catalogues come from `params/`, which is data rather than
code, so adding a species is a YAML file and not a release.
"""

from __future__ import annotations

from shiny import module, reactive, render, ui

from seagarden_dst import SCALES, default_parameters

from ._widgets import window_label

PARAMS = default_parameters()
SPECIES_CHOICES = {k: v.common_name for k, v in PARAMS.species.items()}
AF_SPECIES = [k for k, v in PARAMS.species.items() if v.in_application_form]


@module.ui
def catalogue_ui() -> ui.Tag:
    return ui.layout_sidebar(
        ui.sidebar(
            ui.input_checkbox_group(
                "species",
                "Species",
                choices=SPECIES_CHOICES,
                selected=list(SPECIES_CHOICES),
            ),
            ui.input_select(
                "scale", "Scale", choices=list(SCALES), selected="community farm (0.1 ha)"
            ),
            ui.input_action_link(
                "only_af", "Select only the species named in the Application Form"
            ),
            width=340,
        ),
        ui.card(ui.card_header("Species"), ui.output_ui("species_table")),
        ui.card(ui.card_header("Cultivation methods"), ui.output_ui("method_table")),
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

    @output
    @render.ui
    def species_table():
        rows = []
        for species in PARAMS.species.values():
            named = "yes" if species.in_application_form else "no"
            window = window_label(species.cultivation_window)
            rows.append(
                ui.tags.tr(
                    ui.tags.td(ui.tags.b(species.common_name)),
                    ui.tags.td(ui.tags.em(species.scientific_name)),
                    ui.tags.td(species.group),
                    ui.tags.td(named),
                    ui.tags.td(window),
                )
            )
        return ui.TagList(
            ui.tags.table(
                ui.tags.thead(
                    ui.tags.tr(
                        *[
                            ui.tags.th(h, style="text-align:left;padding-right:1rem;")
                            for h in ("Species", "Scientific name", "Group",
                                      "In the AF", "Cultivation window")
                        ]
                    )
                ),
                ui.tags.tbody(*rows),
                style="width:100%;font-size:.92em;",
            ),
            ui.p(
                ui.tags.small(
                    "Only Ulva and blue mussel are named in the Application Form. Fucus "
                    "carries the OLAMUR low-salinity evidence, Chorda is what KU will "
                    "actually cultivate in Lithuania (decision D1), and sugar kelp is "
                    "carried for the Danish site and as the worked contraindication."
                )
            ),
        )

    @output
    @render.ui
    def method_table():
        rows = [
            ui.tags.tr(
                ui.tags.td(ui.tags.b(m.name)),
                ui.tags.td(m.anchoring_unit),
                ui.tags.td(m.cultivation_unit),
                ui.tags.td(f"{m.min_depth_m:g}-{m.max_depth_m:g} m"),
                ui.tags.td(f"{m.max_significant_wave_m:g} m"),
                ui.tags.td(f"{m.area_m2_per_unit:g} m²"),
            )
            for m in PARAMS.methods.values()
        ]
        return ui.TagList(
            ui.tags.table(
                ui.tags.thead(
                    ui.tags.tr(
                        *[
                            ui.tags.th(h, style="text-align:left;padding-right:1rem;")
                            for h in ("Method", "Anchoring", "Cultivation",
                                      "Depth", "Max wave", "Unit area")
                        ]
                    )
                ),
                ui.tags.tbody(*rows),
                style="width:100%;font-size:.92em;",
            ),
            ui.p(
                ui.tags.small(
                    "Costs and labour are deliberately empty. They are filled from WP3's "
                    "actual procurement records - the viability figures are only "
                    "defensible if the coefficients are what the project really paid."
                )
            ),
        )
