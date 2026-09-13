"""SeaGarden DST Shiny app entry point (wired).

Run from the REPO ROOT as a dotted module:

    shiny run app.app

NOT `shiny run app/app.py` - that puts app/ on sys.path and breaks `from app.* import`.
Same convention as the NiD4OCEAN DST, and `pyproject.toml` sets
`pythonpath = ["src", "."]` so both `seagarden_dst` and `app` resolve from the root.
"""

from __future__ import annotations

from shiny import App, reactive, render, ui

from app.modules._widgets import headline_for
from app.modules.catalogue import catalogue_server, catalogue_ui
from app.modules.report import report_server, report_ui
from app.modules.results import results_server, results_ui, run_assessment
from app.modules.site import site_server, site_ui
from app.modules.user_mode import user_mode_server, user_mode_ui
from app.shell import about_modal, app_shell, feedback_modal, help_modal, t
from app.state import AppState

app_ui = app_shell(
    ui.nav_panel("Site", site_ui("site")),
    ui.nav_panel("Catalogue", catalogue_ui("cat")),
    ui.nav_panel("Results", results_ui("res")),
    ui.nav_panel("Report", report_ui("rep")),
)


def server(input, output, session):  # noqa: A002 - Shiny's signature
    state = AppState()

    user_mode_server("um", state=state)
    site_server("site", state=state)
    catalogue_server("cat", state=state)
    results_server("res", state=state)
    report_server("rep", state=state)

    @render.ui
    def user_mode_slot():
        return user_mode_ui("um")

    @render.ui
    def status_slot():
        context = state.context.get()
        assessment = state.assessment.get()
        if context is None:
            return ui.p(t("No site selected. Open Site and choose one."))
        if assessment is None:
            species = state.selected_species.get()
            count = len(species) if species else 0
            # t() takes a STATIC template; interpolate AFTER the lookup.
            return ui.p(
                t("Site ready: {label}. {n} species selected at {scale}. Click Assess.").format(
                    label=state.site_label.get(), n=count, scale=state.scale.get()
                )
            )
        _cls, text = headline_for(assessment)
        return ui.p(text)

    @reactive.effect
    @reactive.event(input.assess)
    def _on_assess():
        run_assessment(state)

    # CRITICAL: invalidate a stale assessment the moment the site, species, scale or
    # optional forcing changes, so Results and the DOWNLOADED REPORT can never show
    # one site's numbers under another site's label. Everything returns to its
    # placeholder until the user clicks Assess again.
    @reactive.effect
    @reactive.event(
        state.context,
        state.selected_species,
        state.scale,
        state.method_overrides,
        state.eutropy_scenario,
        state.bowtie_inference,
        ignore_init=True,
    )
    def _invalidate_stale_assessment():
        state.assessment.set(None)

    @reactive.effect
    @reactive.event(input.about)
    def _show_about():
        ui.modal_show(about_modal())

    @reactive.effect
    @reactive.event(input.help)
    def _show_help():
        ui.modal_show(help_modal())

    @reactive.effect
    @reactive.event(input.feedback)
    def _show_feedback():
        ui.modal_show(feedback_modal())


app = App(app_ui, server)
