"""Small shared renderers.

The important one is `tier_badge`: the calibration tier must be rendered inside the
same visual element as the number it qualifies (specification 7.4 and the risk
register row "users read tier-C numbers as measurements"). Putting it in a footnote
is the failure mode this function exists to prevent.
"""

from __future__ import annotations

from shiny import ui

from seagarden_dst import SiteAssessment, Tier
from seagarden_dst.calibration import Quantity, for_display

_TIER_COLOUR = {
    Tier.A: ("#1a7f37", "#e6f4ea"),
    Tier.B: ("#0969da", "#e8f1fb"),
    Tier.C: ("#9a6700", "#fdf3d8"),
    Tier.D: ("#a40e26", "#fbe9ec"),
}

_VERDICT_COLOUR = {
    "suitable": "#1a7f37",
    "marginal": "#9a6700",
    "unsuitable": "#a40e26",
    "unknown": "#57606a",
}


def tier_badge(tier: Tier) -> ui.Tag:
    fg, bg = _TIER_COLOUR[tier]
    return ui.tags.span(
        tier.value,
        title=f"{tier.label} - {tier.presentation}",
        style=(
            f"display:inline-block;min-width:1.1rem;text-align:center;margin-left:.4rem;"
            f"padding:0 .3rem;border-radius:.25rem;font-size:.75em;font-weight:700;"
            f"color:{fg};background:{bg};"
        ),
    )


def quantity(q: Quantity | None) -> ui.Tag:
    """A number and its tier, inseparable."""
    if q is None:
        return ui.tags.span("-")
    shown = for_display(q)
    if not shown.calibration.is_reportable:
        return ui.tags.span(shown.calibration.caveat(), style="color:#a40e26;")
    if shown.low is not None and shown.high is not None:
        text = f"{shown.low:.3g}-{shown.high:.3g} {shown.unit}"
    else:
        text = f"{shown.value:.3g} {shown.unit}"
    return ui.tags.span(text, tier_badge(shown.calibration.tier))


def verdict_pill(verdict: str) -> ui.Tag:
    colour = _VERDICT_COLOUR.get(verdict, "#57606a")
    return ui.tags.span(
        verdict,
        style=(
            f"display:inline-block;padding:.05rem .45rem;border-radius:1rem;"
            f"border:1px solid {colour};color:{colour};font-size:.8em;"
        ),
    )


def headline_for(assessment: SiteAssessment) -> tuple[str, str]:
    """(css class, sentence) for the sidebar status.

    Sign- and tier-aware: never announces a "best option" when nothing is reportable
    or everything is unsuitable, which is the equivalent of the NiD4OCEAN headline
    guard against a false "top" when all net contributions are non-positive.
    """
    if not assessment.ranked:
        return "muted", "No species could be assessed at this site."
    if not assessment.any_reportable:
        return "warn", "Nothing reportable here - every option is contraindicated."
    best = assessment.best
    if best is None:
        return "warn", "No option is currently suitable; see Results for the constraints."
    tier = assessment.lowest_tier
    suffix = " (literature priors)" if tier is Tier.C else ""
    return "ok", f"Best option: {best.species_name}, {best.verdict}{suffix}."


def calibration_legend() -> ui.Tag:
    return ui.card(
        ui.card_header("Calibration tiers"),
        ui.tags.ul(
            ui.tags.li(tier_badge(Tier.A), " fitted to SeaGarden pilot data"),
            ui.tags.li(tier_badge(Tier.B), " fitted elsewhere in the Baltic"),
            ui.tags.li(tier_badge(Tier.C), " literature prior, no local validation"),
            ui.tags.li(tier_badge(Tier.D), " contraindicated - a finding contradicts the model"),
            style="list-style:none;padding-left:0;",
        ),
        ui.p(
            ui.tags.small(
                "Before WP3 pilot data arrives (M12-30), essentially every South Baltic "
                "result is tier C. Read those as indicative bands, not estimates."
            )
        ),
    )
