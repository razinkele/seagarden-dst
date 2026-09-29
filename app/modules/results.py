"""Results panel, and the one place an assessment is run.

`run_assessment(state)` is the single call site for `seagarden_dst.assess_site`, so
the app has exactly one path from inputs to numbers - the same arrangement as
`trait_sensitivity.run_assessment` in the NiD4OCEAN DST.
"""

from __future__ import annotations

from shiny import module, render, ui

from app.i18n import Translator
from seagarden_dst import CAVEAT_LABELS, Verdict, assess_site, removal_framing
from seagarden_dst.forcing import DEFAULT_FORCING, ForcingChoice

from ._widgets import calibration_legend, quantity, verdict_pill


def forcing_for(context, choice: ForcingChoice):
    """The source to assess with: the session's choice, unless this site fell back.

    A context with a `source_note` was built on the placeholder because the reader has
    nothing for it (no coordinate), so its daily series must come from the placeholder
    too, or the growth model integrates one source's seasons over another's conditions.

    `choice` is never `None` here: `server()` sets `state.forcing` once per session,
    before any assessment can run, so `run_assessment` always calls this with a real
    `ForcingChoice`.
    """
    return DEFAULT_FORCING if context.source_note is not None else choice.source


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
def results_ui(tr: Translator) -> ui.Tag:
    return ui.TagList(
        ui.card(ui.card_header(tr("app.results.ranked")), ui.output_ui("ranking")),
        ui.card(ui.card_header(tr("app.results.excluded")), ui.output_ui("excluded")),
        ui.card(ui.card_header(tr("app.results.pressure")), ui.output_ui("pressure")),
        calibration_legend(tr),
    )


def render_ranking(assessment, tr: Translator) -> ui.Tag:
    if assessment is None:
        return ui.p(tr("app.results.pick_site"), style="opacity:.7;")
    if assessment.unassessable:
        return ui.p(tr("app.results.unassessed"), style="opacity:.7;")
    if not assessment.ranked:
        return ui.p(tr("app.results.none"))

    columns = ("option", "verdict", "harvest", "nitrogen", "phosphorus", "carbon")
    head = ui.tags.tr(
        *[
            ui.tags.th(
                tr(f"app.results.col.{c}"), style="text-align:left;padding:.3rem 1rem .3rem 0;"
            )
            for c in columns
        ]
    )
    rows = []
    for option in assessment.ranked:
        rows.append(
            ui.tags.tr(
                ui.tags.td(
                    ui.tags.b(tr.species_name(option.species_key)),
                    ui.tags.br(),
                    ui.tags.small(tr.method_name(option.method_key), style="opacity:.7;"),
                ),
                ui.tags.td(verdict_pill(option.verdict, tr)),
                ui.tags.td(quantity(option.harvest, tr)),
                ui.tags.td(quantity(option.nitrogen, tr)),
                ui.tags.td(quantity(option.phosphorus, tr)),
                ui.tags.td(quantity(option.carbon, tr)),
                style="border-top:1px solid rgba(128,128,128,.25);",
            )
        )
        rows.append(
            ui.tags.tr(
                ui.tags.td(
                    ui.tags.details(
                        ui.tags.summary(ui.tags.small(tr.render(option.binding_constraint))),
                        ui.tags.ul(
                            *[
                                ui.tags.li(
                                    ui.tags.small(
                                        tr(
                                            "app.results.constraint_line",
                                            name=name, verdict=Verdict(verdict).label,
                                            reason=reason,
                                        )
                                    )
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
    caveat_block = (
        [
            ui.tags.div(
                ui.tags.b(tr("app.results.caveats")),
                ui.tags.ul(
                    *[
                        ui.tags.li(
                            tr("app.results.caveat_line", label=CAVEAT_LABELS.get(k, k), text=v)
                        )
                        for k, v in caveats.items()
                    ]
                ),
                style="margin-top:.75rem;font-size:.9em;",
            )
        ]
        if caveats
        else []
    )
    return ui.TagList(
        ui.tags.table(ui.tags.thead(head), ui.tags.tbody(*rows), style="width:100%;"),
        *caveat_block,
    )


def render_excluded(assessment, tr: Translator) -> ui.Tag:
    if assessment is None:
        return ui.p(tr("app.results.dash"), style="opacity:.7;")
    if not assessment.excluded:
        return ui.p(tr("app.results.nothing_excluded"), style="opacity:.7;")
    # Exclusions are shown with their reason, not silently dropped: "why can't I
    # grow kelp here" is one of the questions the tool exists to answer.
    return ui.tags.ul(
        *[
            # The raw species key, as before: the excluded dict is keyed by identifier and
            # English never showed the common name here, so the seam must not either.
            ui.tags.li(ui.tags.b(key), ": ", tr.render(reason))
            for key, reason in assessment.excluded.items()
        ]
    )


def render_pressure(assessment, tr: Translator) -> ui.Tag:
    if assessment is None:
        return ui.p(tr("app.results.dash"), style="opacity:.7;")
    if not assessment.pressure:
        note = assessment.pressure_note
        return ui.p(
            tr.render(note) if note is not None else tr("app.results.no_bowtie"),
            style="opacity:.7;",
        )
    items = [
        ui.tags.li(tr("app.results.p_top", state=state_, p=f"{p:.3f}"))
        for state_, p in assessment.pressure.items()
    ]
    framing = removal_framing(assessment.pressure)
    return ui.TagList(
        ui.tags.ul(*items),
        ui.p(tr.render(framing) if framing is not None else ""),
        ui.p(
            ui.tags.small(
                tr.render(assessment.pressure_note) if assessment.pressure_note else ""
            )
        ),
    )


@module.server
def results_server(input, output, session, state) -> None:  # noqa: A002
    @output
    @render.ui
    def ranking():
        return render_ranking(state.assessment.get(), state.translator())

    @output
    @render.ui
    def excluded():
        return render_excluded(state.assessment.get(), state.translator())

    @output
    @render.ui
    def pressure():
        return render_pressure(state.assessment.get(), state.translator())
