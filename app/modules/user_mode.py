"""User mode - the four entry points of specification section 4.

The specification describes "one engine, four doors". Implemented as a mode selector
over a single workflow rather than four parallel copies of it: the door sets
vocabulary and defaults, never capability (design rule 1), so a community user who
wants the nitrogen figure still gets it.

The taxonomy is KU's hypothesis. Decision D9: validate it against the A2.2 stakeholder
findings (D2.1, M12) before building it out further.

`MODES` holds identifiers only; the words a door uses are catalogue keys
`app.mode.<door>.{title,audience,question}` (package I).
"""

from __future__ import annotations

from shiny import module, reactive, render, ui

from app.i18n import Translator

MODES: dict[str, dict] = {
    "plan": {"scale": "community_farm_1_ha", "register": "aggregate"},
    "farm": {"scale": "community_farm_0_1_ha", "register": "operational"},
    "start": {"scale": "mini_farm_kit", "register": "plain"},
    "explore": {"scale": "community_farm_0_1_ha", "register": "technical"},
}


def mode_choices(tr: Translator) -> dict[str, str]:
    return {
        key: tr(
            "app.mode.choice",
            title=tr(f"app.mode.{key}.title"), audience=tr(f"app.mode.{key}.audience"),
        )
        for key in MODES
    }


def mode_question_tag(mode: str, tr: Translator) -> ui.Tag:
    """Pure: the door's question. Named `_tag` because the render function below must be
    called `mode_question` - Shiny binds an output by its function's name."""
    return ui.help_text(ui.tags.em(tr(f"app.mode.{mode}.question")))


@module.ui
def user_mode_ui(tr: Translator) -> ui.TagList:
    return ui.TagList(
        ui.input_select("mode", tr("app.mode.label"), choices=mode_choices(tr), selected="farm"),
        ui.output_ui("mode_question"),
    )


@module.server
def user_mode_server(input, output, session, state) -> None:  # noqa: A002
    @reactive.effect
    @reactive.event(input.mode)
    def _sync_mode():
        mode = input.mode()
        state.user_mode.set(mode)
        # The door sets the DEFAULT scale. It does not lock it: the user can still
        # change scale in Catalogue, because the door governs vocabulary, not capability.
        state.scale.set(MODES[mode]["scale"])

    @output
    @render.ui
    def mode_question():
        return mode_question_tag(state.user_mode.get(), state.translator())
