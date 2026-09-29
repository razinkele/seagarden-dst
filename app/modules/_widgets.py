"""Small shared renderers, every one of them a function of the session's Translator.

The important one is `tier_badge`: the calibration tier must be rendered inside the
same visual element as the number it qualifies (specification 7.4 and the risk
register row "users read tier-C numbers as measurements"). Putting it in a footnote
is the failure mode this function exists to prevent.
"""

from __future__ import annotations

from shiny import ui

from app.i18n import Translator
from seagarden_dst import SiteAssessment, SiteContext, Tier, Verdict
from seagarden_dst.calibration import Quantity, for_display
from seagarden_dst.forcing import Coverage, ForcingChoice

# Colours live in app/www/seagarden.css under these class names, so the badge follows
# the theme's tokens rather than carrying its own hex.
_VERDICTS = frozenset({"suitable", "marginal", "unsuitable", "unknown"})


def tier_badge(tier: Tier, tr: Translator) -> ui.Tag:
    return ui.tags.span(
        tier.value,
        title=tr("app.tier.badge_title", label=tier.label, presentation=tier.presentation),
        class_=f"sg-tier sg-tier-{tier.value.lower()}",
    )


def quantity(q: Quantity | None, tr: Translator) -> ui.Tag:
    """A number and its tier, inseparable."""
    if q is None:
        return ui.tags.span(tr("app.quantity.none"))
    shown = for_display(q)
    if not shown.calibration.is_reportable:
        return ui.tags.span(tr.render(shown.calibration.caveat()), class_="sg-caveat")
    if shown.low is not None and shown.high is not None:
        text = tr(
            "app.quantity.range", low=f"{shown.low:.3g}", high=f"{shown.high:.3g}", unit=shown.unit
        )
    else:
        text = tr("app.quantity.value", value=f"{shown.value:.3g}", unit=shown.unit)
    return ui.tags.span(text, tier_badge(shown.calibration.tier, tr))


def verdict_pill(verdict: str, tr: Translator) -> ui.Tag:
    kind = verdict if verdict in _VERDICTS else "unknown"
    shown = tr.render(Verdict(verdict).label) if verdict in _VERDICTS else verdict
    return ui.tags.span(shown, class_=f"sg-verdict sg-verdict-{kind}")


def headline_for(assessment: SiteAssessment, tr: Translator) -> tuple[str, str]:
    """(css class, sentence) for the sidebar status.

    Sign- and tier-aware: never announces a "best option" when nothing is reportable
    or everything is unsuitable, which is the equivalent of the NiD4OCEAN headline
    guard against a false "top" when all net contributions are non-positive.
    """
    if assessment.unassessable:
        return "warn", tr("app.headline.unassessed", reason=_unassessable_reason(assessment, tr))
    if not assessment.ranked:
        return "muted", tr("app.headline.none")
    if not assessment.any_reportable:
        return "warn", tr("app.headline.nothing_reportable")
    best = assessment.best
    if best is None:
        return "warn", tr("app.headline.none_suitable")
    suffix_key = (
        "app.headline.priors_suffix"
        if assessment.lowest_tier is Tier.C
        else "app.headline.no_suffix"
    )
    return "ok", tr(
        "app.headline.best",
        species=tr.species_name(best.species_key),
        verdict=Verdict(best.verdict).label,
        suffix=tr(suffix_key),
    )


def _unassessable_reason(assessment: SiteAssessment, tr: Translator) -> str:
    if assessment.coverage is Coverage.CELL_INVALID:
        distance = (
            tr("app.unassessable.nearest", km=f"{assessment.nearest_valid_km:.2f}")
            if assessment.nearest_valid_km is not None
            else tr("app.unassessable.no_distance")
        )
        return tr("app.unassessable.cell_invalid", distance=distance)
    if assessment.coverage is Coverage.YEAR_ABSENT:
        return tr("app.unassessable.year_absent")
    return tr("app.unassessable.no_conditions")


def artifact_source_text(choice: ForcingChoice, tr: Translator) -> str:
    """The artifact data-source sentence, minus its trailing period.

    Shared by `data_source_banner` here and `report._data_source_line`, so the
    banner and the downloadable report cannot drift on the wording that names the
    query year and the artifact's build date.
    """
    built = (
        choice.built_on.strftime("%Y-%m-%d") if choice.built_on else tr("app.source.unknown_date")
    )
    return tr("app.source.artifact", year=str(choice.year), built=built)


def data_source_banner(
    choice: ForcingChoice, context: SiteContext | None, tr: Translator
) -> str:
    """Sentence naming what the app is running on, and why if it is not the artifact.

    `choice.reason` is an operator diagnostic and stays English inside the keyed
    sentence (spec I§7).
    """
    if choice.is_artifact:
        text = tr("app.banner.artifact", source=artifact_source_text(choice, tr))
    else:
        text = tr("app.banner.placeholder", reason=choice.reason)
    if context is not None and context.source_note is not None:
        text += tr("app.banner.this_site", note=context.source_note)
    return text


def calibration_legend(tr: Translator) -> ui.Tag:
    return ui.card(
        ui.card_header(tr("app.legend.title")),
        ui.tags.ul(
            *[
                ui.tags.li(tier_badge(tier, tr), tr(f"app.legend.{tier.value}"))
                for tier in (Tier.A, Tier.B, Tier.C, Tier.D)
            ],
            style="list-style:none;padding-left:0;",
        ),
        ui.p(ui.tags.small(tr("app.legend.note"))),
    )


def window_label(window: tuple[int, int], tr: Translator) -> str:
    """Render a cultivation window as months.

    "months 10-6" reads as a typo. A window whose end month precedes its start month
    wraps the year boundary, and saying so is the difference between a user reading a
    backwards range and reading an over-winter deployment.
    """
    start, end = window
    span = tr("app.window.span", start=tr(f"app.month.{start}"), end=tr(f"app.month.{end}"))
    return tr("app.window.over_winter", span=span) if end < start else span
