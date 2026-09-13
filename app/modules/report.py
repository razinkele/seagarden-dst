"""Report panel - the assessment as text, with its caveats attached.

The report carries the site label and the caveats, because a table of numbers that
outlives the screen it was read on is exactly where a caveat gets lost.
"""

from __future__ import annotations

import json
from datetime import date

from shiny import module, render, ui

from seagarden_dst import __version__
from seagarden_dst.calibration import for_display


def render_report(assessment) -> str:
    if assessment is None:
        return "No assessment yet. Pick a site and click Assess."

    context = assessment.context
    lines = [
        "SEAGARDEN DECISION SUPPORT TOOL - SITE ASSESSMENT",
        "=" * 52,
        "",
        f"Site:        {context.label or context.region}",
        f"Sub-region:  {context.region}",
        f"Conditions:  salinity {context.conditions.salinity_psu:g} psu, "
        f"DIN {context.conditions.din_umol_l:g} umol/L, "
        f"depth {context.conditions.depth_m:g} m",
        f"Data confidence: {context.confidence}",
        f"Generated:   {date.today().isoformat()} - core v{__version__}",
        "",
        "RANKED OPTIONS",
        "-" * 52,
    ]

    if not assessment.ranked:
        lines.append("No species could be assessed at this site.")
    for option in assessment.ranked:
        harvest = for_display(option.harvest)
        lines += [
            "",
            f"{option.species_name} - {option.method_name} "
            f"({option.area_m2 / 10_000:.4g} ha)",
            f"  Verdict:   {option.verdict}",
            f"  Binding:   {option.binding_constraint}",
            f"  Harvest:   {harvest}",
        ]
        if option.nitrogen is not None:
            lines += [
                f"  Nitrogen:  {for_display(option.nitrogen)}",
                f"  Phosphorus:{for_display(option.phosphorus)}",
                f"  Carbon:    {for_display(option.carbon)}",
            ]
        lines.append(f"  Calibration: {option.tier.label} - {option.tier.presentation}")

    if assessment.excluded:
        lines += ["", "EXCLUDED", "-" * 52]
        lines += [f"- {k}: {v}" for k, v in assessment.excluded.items()]

    if assessment.pressure:
        lines += ["", "PRESSURE CONTEXT", "-" * 52]
        lines += [f"- P(top event {s}) = {p:.3f}" for s, p in assessment.pressure.items()]
        if assessment.pressure_note:
            lines.append(f"  {assessment.pressure_note}")

    lines += ["", "CAVEATS", "-" * 52]
    for key, value in assessment.caveats.items():
        lines.append(f"- {key}: {value}")
    lines += [
        "- Carbon is reported as carbon in harvested biomass only. Sequestration is "
        "not reported: calcification releases CO2, so a sequestration claim would "
        "depend on shell being removed from the water and kept out of it.",
        "- Site conditions in this prototype are placeholders, not measurements.",
        "- Legal permissibility is unassessed until the regulatory records exist "
        "(A2.2, M12). An unknown legal status blocks the verdict rather than passing it.",
        "",
        "Prototype output. Indicative only; not a basis for permitting or consent.",
    ]
    return "\n".join(lines)


@module.ui
def report_ui() -> ui.Tag:
    return ui.TagList(
        ui.card(
            ui.card_header("Assessment report"),
            ui.download_button("download_txt", "Download report (.txt)", class_="btn-sm"),
            ui.download_button("download_json", "Download data (.json)", class_="btn-sm"),
            ui.output_code("report_text"),
        ),
    )


@module.server
def report_server(input, output, session, state) -> None:  # noqa: A002
    @output
    @render.code
    def report_text():
        return render_report(state.assessment.get())

    @render.download(filename=lambda: f"seagarden-dst-{date.today().isoformat()}.txt")
    def download_txt():
        yield render_report(state.assessment.get())

    @render.download(filename=lambda: f"seagarden-dst-{date.today().isoformat()}.json")
    def download_json():
        assessment = state.assessment.get()
        payload = {} if assessment is None else assessment.to_dict()
        yield json.dumps(payload, indent=2, default=str)
