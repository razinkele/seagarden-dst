"""Results panel, and the one place an assessment is run.

`run_assessment(state)` is the single call site for `seagarden_dst.assess_site`, so
the app has exactly one path from inputs to numbers - the same arrangement as
`trait_sensitivity.run_assessment` in the NiD4OCEAN DST.
"""

from __future__ import annotations

from shiny import module, render, ui

from seagarden_dst import assess_site, removal_framing
from seagarden_dst.forcing import DEFAULT_FORCING, ForcingChoice

from ._widgets import calibration_legend, quantity, verdict_pill


def forcing_for(context, choice: ForcingChoice):
    """The source to assess with: the session's choice, unless this site fell back.

    A context with a `source_note` was built on the placeholder because the reader has
    nothing for it (no coordinate), so its daily series must come from the placeholder
    too, or the growth model integrates one source's seasons over another's conditions.
    """
    return DEFAULT_FORCING if context.source_note else choice.source


def run_assessment(state) -> None:
    """Run the core against current state and store the result. Never raises."""
    context = state.context.get()
    if context is None:
        state.assessment.set(None)
        return
    species = state.selected_species.get() or None
    state.assessment.set(
        assess_site(
            context,
            species=species,
            methods=state.method_overrides.get(),
            scale=state.scale.get(),
            eutropy=state.eutropy_scenario.get(),
            bowtie=state.bowtie_inference.get(),
            forcing=forcing_for(context, state.forcing.get()),
            year=state.forcing.get().year,
        )
    )


@module.ui
def results_ui() -> ui.Tag:
    return ui.TagList(
        ui.card(ui.card_header("Ranked options"), ui.output_ui("ranking")),
        ui.card(ui.card_header("Excluded"), ui.output_ui("excluded")),
        ui.card(ui.card_header("Pressure context"), ui.output_ui("pressure")),
        calibration_legend(),
    )


@module.server
def results_server(input, output, session, state) -> None:  # noqa: A002
    @output
    @render.ui
    def ranking():
        assessment = state.assessment.get()
        if assessment is None:
            return ui.p("Pick a site, then click Assess.", style="opacity:.7;")
        if assessment.unassessable:
            return ui.p(
                "This site is unassessed because the data layer could not provide "
                "conditions. See the report for the coverage reason.",
                style="opacity:.7;",
            )
        if not assessment.ranked:
            return ui.p("No species could be assessed at this site.")

        head = ui.tags.tr(
            *[
                ui.tags.th(h, style="text-align:left;padding:.3rem 1rem .3rem 0;")
                for h in ("Option", "Verdict", "Harvest", "Nitrogen", "Phosphorus", "Carbon")
            ]
        )
        rows = []
        for option in assessment.ranked:
            rows.append(
                ui.tags.tr(
                    ui.tags.td(
                        ui.tags.b(option.species_name),
                        ui.tags.br(),
                        ui.tags.small(option.method_name, style="opacity:.7;"),
                    ),
                    ui.tags.td(verdict_pill(option.verdict)),
                    ui.tags.td(quantity(option.harvest)),
                    ui.tags.td(quantity(option.nitrogen)),
                    ui.tags.td(quantity(option.phosphorus)),
                    ui.tags.td(quantity(option.carbon)),
                    style="border-top:1px solid rgba(128,128,128,.25);",
                )
            )
            rows.append(
                ui.tags.tr(
                    ui.tags.td(
                        ui.tags.details(
                            ui.tags.summary(
                                ui.tags.small(option.binding_constraint or "All constraints pass")
                            ),
                            ui.tags.ul(
                                *[
                                    ui.tags.li(
                                        ui.tags.small(f"{name}: {verdict} - {reason}")
                                    )
                                    for name, verdict, reason in option.constraints
                                ]
                            ),
                        ),
                        colspan="6",
                        style="padding-bottom:.5rem;",
                    )
                )
            )

        caveats = assessment.caveats
        return ui.TagList(
            ui.tags.table(
                ui.tags.thead(head), ui.tags.tbody(*rows), style="width:100%;"
            ),
            *(
                [
                    ui.tags.div(
                        ui.tags.b("Caveats"),
                        ui.tags.ul(*[ui.tags.li(f"{k}: {v}") for k, v in caveats.items()]),
                        style="margin-top:.75rem;font-size:.9em;",
                    )
                ]
                if caveats
                else []
            ),
        )

    @output
    @render.ui
    def excluded():
        assessment = state.assessment.get()
        if assessment is None:
            return ui.p("-", style="opacity:.7;")
        if not assessment.excluded:
            return ui.p("Nothing excluded at this site.", style="opacity:.7;")
        # Exclusions are shown with their reason, not silently dropped: "why can't I
        # grow kelp here" is one of the questions the tool exists to answer.
        return ui.tags.ul(
            *[
                ui.tags.li(ui.tags.b(key), ": ", reason)
                for key, reason in assessment.excluded.items()
            ]
        )

    @output
    @render.ui
    def pressure():
        assessment = state.assessment.get()
        if assessment is None:
            return ui.p("-", style="opacity:.7;")
        if not assessment.pressure:
            return ui.p(
                assessment.pressure_note
                or "No bow-tie inference supplied. Nutrient removal is reported on its "
                   "own terms.",
                style="opacity:.7;",
            )
        items = [
            ui.tags.li(f"P(top event {state_}) = {p:.3f}")
            for state_, p in assessment.pressure.items()
        ]
        return ui.TagList(
            ui.tags.ul(*items),
            ui.p(removal_framing(assessment.pressure)),
            ui.p(ui.tags.small(assessment.pressure_note)),
        )
