"""Report panel - the assessment as text, with its caveats attached.

The report carries the site label and the caveats, because a table of numbers that
outlives the screen it was read on is exactly where a caveat gets lost.

`today` is a parameter for the same reason `regulatory.py` makes it one: the test suite
must not turn red on a calendar boundary. `tr` defaults to English so the core-style
call `render_report(assessment, today=...)` still reads as it always did.
"""

from __future__ import annotations

import json
from datetime import date

from shiny import module, render, ui

from app.i18n import Translator, english
from seagarden_dst import CAVEAT_LABELS, Verdict, __version__
from seagarden_dst.calibration import for_display
from seagarden_dst.forcing import Coverage, ForcingChoice

from ._widgets import artifact_source_text


def render_report(
    assessment, choice: ForcingChoice | None = None, *, today: date, tr: Translator | None = None
) -> str:
    tr = tr or english()
    body = _report_body(assessment, choice, today=today, tr=tr)
    if tr.is_draft:
        banner = f"{tr('app.shell.draft_banner')} {english()('app.shell.draft_banner')}"
        return f"{banner}\n{body}"
    return body


def _report_body(
    assessment, choice: ForcingChoice | None, *, today: date, tr: Translator
) -> str:
    if assessment is None:
        return tr("app.report.none")

    context = assessment.context
    if context.conditions is None:
        conditions_line = tr("app.report.conditions_unavailable")
    else:
        c = context.conditions
        conditions_line = tr(
            "app.report.conditions",
            salinity=f"{c.salinity_psu:g}", din=f"{c.din_umol_l:g}", depth=f"{c.depth_m:g}",
        )
    lines = [
        tr("app.report.heading"),
        "=" * 52,
        "",
        tr("app.report.site", site=context.label or context.region),
        tr("app.report.subregion", region=context.region),
        conditions_line,
        tr("app.report.confidence", confidence=tr.confidence_label(context.confidence)),
        _data_source_line(choice, context, tr),
        tr("app.report.generated", date=today.isoformat(), version=__version__),
        "",
        tr("app.report.ranked"),
        "-" * 52,
    ]

    if assessment.unassessable:
        lines.append(tr("app.report.unassessed", reason=_unassessed_reason(assessment, tr)))
    elif not assessment.ranked:
        lines.append(tr("app.report.none_assessed"))
    for option in assessment.ranked:
        lines += [
            "",
            tr(
                "app.report.option",
                species=tr.species_name(option.species_key),
                method=tr.method_name(option.method_key),
                ha=f"{option.area_m2 / 10_000:.4g}",
            ),
            tr("app.report.verdict", verdict=Verdict(option.verdict).label),
            tr("app.report.binding", binding=option.binding_constraint),
            tr("app.report.harvest", harvest=tr.quantity(for_display(option.harvest))),
        ]
        if option.nitrogen is not None:
            lines += [
                tr("app.report.nitrogen", value=tr.quantity(for_display(option.nitrogen))),
                tr("app.report.phosphorus", value=tr.quantity(for_display(option.phosphorus))),
                tr("app.report.carbon", value=tr.quantity(for_display(option.carbon))),
            ]
        lines.append(
            tr(
                "app.report.calibration",
                label=option.tier.label, presentation=option.tier.presentation,
            )
        )

    if assessment.excluded:
        lines += ["", tr("app.report.excluded"), "-" * 52]
        lines += [
            tr("app.report.excluded_line", key=k, reason=v) for k, v in assessment.excluded.items()
        ]

    if assessment.pressure:
        lines += ["", tr("app.report.pressure"), "-" * 52]
        lines += [
            tr("app.report.p_top", state=s, p=f"{p:.3f}") for s, p in assessment.pressure.items()
        ]
        if assessment.pressure_note is not None:
            lines.append(tr("app.report.pressure_note", note=assessment.pressure_note))

    lines += ["", tr("app.report.caveats"), "-" * 52]
    for key, value in assessment.caveats.items():
        lines.append(tr("app.report.caveat_line", label=CAVEAT_LABELS.get(key, key), text=value))
    lines += [
        tr("app.report.carbon_caveat"),
        _data_source_caveat(choice, context, tr),
        tr("app.report.legal_caveat"),
        "",
        tr("app.report.footer"),
    ]
    return "\n".join(lines)


def _unassessed_reason(assessment, tr: Translator) -> str:
    if assessment.coverage is Coverage.CELL_INVALID:
        if assessment.nearest_valid_km is not None:
            return tr(
                "app.report.unassessed.cell_invalid_near", km=f"{assessment.nearest_valid_km:.2f}"
            )
        return tr("app.report.unassessed.cell_invalid")
    if assessment.coverage is Coverage.YEAR_ABSENT:
        return tr("app.report.unassessed.year_absent")
    return tr("app.report.unassessed.no_conditions")


def _data_source_line(choice: ForcingChoice | None, context, tr: Translator) -> str:
    if choice is not None:
        if choice.is_artifact:
            text = tr("app.report.source.artifact", source=artifact_source_text(choice, tr))
        else:
            text = tr("app.report.source.placeholder_reason", reason=choice.reason)
    elif context.from_artifact:
        text = tr("app.report.source.artifact_bare")
    else:
        text = tr("app.report.source.placeholder_bare")
    if context.source_note is not None:
        text += tr("app.report.source.this_site", note=context.source_note)
    return text


def _data_source_caveat(choice: ForcingChoice | None, context, tr: Translator) -> str:
    on_artifact = choice.is_artifact if choice is not None else context.from_artifact
    text = tr("app.report.caveat.artifact" if on_artifact else "app.report.caveat.placeholder")
    if context.source_note is not None:
        text += tr("app.report.caveat.this_site", note=context.source_note)
    return text


def export_json(assessment, tr: Translator) -> str:
    """The JSON download's payload: every key `assessment.to_dict()` emits, plus the
    language it was rendered in and whether that language is a draft (I§6) - so the
    file says, on its own, what it is, without a reader having to notice which of five
    machine-draft languages it came out in. With no assessment, just those two keys.

    The markers come first, so they head the file; `to_dict()` never emits either key
    (`test_to_dict_never_emits_a_key_the_json_export_writes_itself`), so its spread
    below cannot overwrite them."""
    payload = {
        "language": tr.language,
        "draft": tr.is_draft,
        **(assessment.to_dict(render=tr.render) if assessment is not None else {}),
    }
    return json.dumps(payload, indent=2, default=str)


@module.ui
def report_ui(tr: Translator) -> ui.Tag:
    return ui.TagList(
        ui.card(
            ui.card_header(tr("app.report.title")),
            ui.download_button("download_txt", tr("app.report.download_txt"), class_="btn-sm"),
            ui.download_button("download_json", tr("app.report.download_json"), class_="btn-sm"),
            ui.output_code("report_text"),
        ),
    )


@module.server
def report_server(input, output, session, state) -> None:  # noqa: A002
    @output
    @render.code
    def report_text():
        return render_report(
            state.assessment.get(), state.forcing.get(), today=date.today(), tr=state.translator()
        )

    @render.download(filename=lambda: f"seagarden-dst-{date.today().isoformat()}.txt")
    def download_txt():
        yield render_report(
            state.assessment.get(), state.forcing.get(), today=date.today(), tr=state.translator()
        )

    @render.download(filename=lambda: f"seagarden-dst-{date.today().isoformat()}.json")
    def download_json():
        yield export_json(state.assessment.get(), state.translator())
