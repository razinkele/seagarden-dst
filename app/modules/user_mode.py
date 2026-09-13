"""User mode - the four entry points of specification section 4.

The specification describes "one engine, four doors". Implemented as a mode selector
over a single workflow rather than four parallel copies of it: the door sets
vocabulary and defaults, never capability (design rule 1), so a community user who
wants the nitrogen figure still gets it.

The taxonomy is KU's hypothesis. Decision D9: validate it against the A2.2 stakeholder
findings (D2.1, M12) before building it out further.
"""

from __future__ import annotations

from shiny import module, reactive, render, ui

MODES: dict[str, dict] = {
    "plan": {
        "title": "Plan",
        "audience": "Authorities, spatial planners",
        "question": "Where could regenerative farming go here, and what would it achieve?",
        "scale": "community farm (1 ha)",
        "register": "aggregate",
    },
    "farm": {
        "title": "Farm",
        "audience": "Farmers, SMEs, operators",
        "question": "Can I farm this spot, what should I grow, and what will I get?",
        "scale": "community farm (0.1 ha)",
        "register": "operational",
    },
    "start": {
        "title": "Start",
        "audience": "Communities, NGOs, citizen science",
        "question": "Could we run a small sea garden here, and what would it take?",
        "scale": "mini-farm kit",
        "register": "plain",
    },
    "explore": {
        "title": "Explore",
        "audience": "Researchers, students, consultants",
        "question": "What do the models say, and how confident are they?",
        "scale": "community farm (0.1 ha)",
        "register": "technical",
    },
}

CHOICES = {k: f"{v['title']} - {v['audience']}" for k, v in MODES.items()}


@module.ui
def user_mode_ui() -> ui.TagList:
    return ui.TagList(
        ui.input_select("mode", "I am here as", choices=CHOICES, selected="farm"),
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
        return ui.help_text(ui.tags.em(MODES[state.user_mode.get()]["question"]))
