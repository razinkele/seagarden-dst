"""SeaGarden DST Shiny app entry point (wired).

Run from the REPO ROOT as a dotted module:

    shiny run app.app

NOT `shiny run app/app.py` - that puts app/ on sys.path and breaks `from app.* import`.
Same convention as the NiD4OCEAN DST, and `pyproject.toml` sets
`pythonpath = ["src", "."]` so both `seagarden_dst` and `app` resolve from the root.

The UI is a FUNCTION OF THE REQUEST (package I): `app_ui(request)` picks the language
from `?lang=` or `Accept-Language` through `language_for`, the same function the server
uses on the websocket side, so the page and its renders cannot disagree.
"""

from __future__ import annotations

from collections.abc import Sequence

from shiny import App, reactive, render, ui
from starlette.requests import Request

from app.i18n import Translator, enabled_languages, language_for
from app.modules._widgets import data_source_banner, headline_for
from app.modules.catalogue import catalogue_server, catalogue_ui
from app.modules.report import report_server, report_ui
from app.modules.results import results_server, results_ui, run_assessment
from app.modules.site import site_server, site_ui
from app.modules.user_mode import user_mode_server, user_mode_ui
from app.shell import about_modal, app_shell, feedback_modal, help_modal
from app.state import AppState
from seagarden_dst import SCALE_LABELS
from seagarden_dst.gridded import select_forcing


def build_ui(language: str, *, enabled: Sequence[str] | None = None) -> ui.Tag:
    """The whole page in one language. `app_ui` and the tests call this.

    `enabled` is the language menu; `app_ui` passes the set it already chose the
    language from, so one page load runs the gate once. Left out (the tests calling
    `build_ui(lang)`), it is the deployment's own `enabled_languages()`, read now.
    """
    tr = Translator.pseudo() if language == "xx" else Translator.for_language(language)
    return app_shell(
        tr,
        ui.nav_panel(tr("app.nav.site"), site_ui("site", tr)),
        ui.nav_panel(tr("app.nav.catalogue"), catalogue_ui("cat", tr)),
        ui.nav_panel(tr("app.nav.results"), results_ui("res", tr)),
        ui.nav_panel(tr("app.nav.report"), report_ui("rep", tr)),
        enabled=enabled_languages() if enabled is None else enabled,
    )


def app_ui(request: Request) -> ui.Tag:
    enabled = enabled_languages()
    language = language_for(request.url.query, request.headers.get("accept-language"), enabled)
    return build_ui(language, enabled=enabled)


def scale_sentence(*, label: str, count: int, scale_key: str, tr: Translator) -> str:
    """The 'site ready' sentence. `scale_key` is state; the user reads its label."""
    return tr(
        "app.status.site_ready", label=label, n=str(count), scale=SCALE_LABELS[scale_key]
    )


def server(input, output, session):  # noqa: A002 - Shiny's signature
    state = AppState()
    state.forcing.set(select_forcing())

    @reactive.calc
    def translator() -> Translator:
        # `.clientdata_url_search` is set by shiny.js from window.location.search on
        # connect; the header comes from the websocket handshake. Same chooser as the
        # page, same enabled set, so a render never speaks a different language than
        # the chrome around it.
        query = session.input[".clientdata_url_search"]()
        accept = session.http_conn.headers.get("accept-language")
        return Translator.for_language(language_for(query, accept, enabled_languages()))

    state.translator = translator

    user_mode_server("um", state=state)
    site_server("site", state=state)
    catalogue_server("cat", state=state)
    results_server("res", state=state)
    report_server("rep", state=state)

    @render.ui
    def user_mode_slot():
        return user_mode_ui("um", state.translator())

    @render.ui
    def status_slot():
        tr = state.translator()
        context = state.context.get()
        assessment = state.assessment.get()
        if context is None:
            return ui.p(tr("app.status.no_site"))
        if assessment is None:
            species = state.selected_species.get()
            count = len(species) if species else 0
            return ui.p(
                scale_sentence(
                    label=state.site_label.get(), count=count, scale_key=state.scale.get(), tr=tr
                )
            )
        _cls, text = headline_for(assessment, tr)
        return ui.p(text)

    @render.ui
    def data_source_slot():
        choice = state.forcing.get()
        assessment = state.assessment.get()
        context = assessment.context if assessment is not None else state.context.get()
        return ui.p(data_source_banner(choice, context, state.translator()))

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
        ui.modal_show(about_modal(state.translator()))

    @reactive.effect
    @reactive.event(input.help)
    def _show_help():
        ui.modal_show(help_modal(state.translator()))

    @reactive.effect
    @reactive.event(input.feedback)
    def _show_feedback():
        ui.modal_show(feedback_modal(state.translator()))


app = App(app_ui, server)
