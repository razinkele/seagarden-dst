"""Bow-tie adapter - eutrophication pressure context from bowtiepy.

bowtiepy (razinkele/bowtiepy) builds a pgmpy Bayesian network over the MARBEFES
bow-tie for Curonian Lagoon eutrophication, with a LINE/AGG parent-divorcing
architecture, CPTs filled from ratings or from EUTROPY samples, and do-calculus
barrier ranking. Published scenario inference gives P(top event High) = 0.472 at
current Nemunas loading against 0.252 under a BSAP-compliant scenario.

WHY THE DST WANTS IT. Nutrient removal is worth more where eutrophication pressure
is higher. A farm that removes 40 kg N is the same farm either way, but the *decision*
it supports is not: in a water body already at high risk of the top event, removal is
mitigation; in one at low risk it is maintenance. So the bow-tie enters this tool as
CONTEXT REPORTED BESIDE the ranking - never as a multiplier on it. Folding a risk
probability into a yield figure would produce a number that is neither a yield nor a
risk, and nobody could say what it meant.

That "beside, never merged" rule is taken directly from how `nid4ocean_dst.api`
carries its two social-ecological readings: shown side by side, never combined.

DOMAIN CAVEAT: like EUTROPY, the published bow-tie is parameterised for the Curonian
Lagoon. Applying it to an open-coast or Polish site is scenario reasoning, and the
adapter says so on the result.
"""

from __future__ import annotations

from .contracts import SiteContext

#: Regions the published Curonian Lagoon bow-tie speaks for directly.
LAGOON_REGIONS = {"PL-lagoon", "LT-lagoon", "curonian-lagoon"}

#: States of the top event, as used in the MARBEFES bow-tie.
TOP_EVENT_STATES = ("Low", "Moderate", "High")


class BowtieUnavailable(RuntimeError):
    """bowtiepy output is missing, malformed, or not applicable to this site."""


def eutrophication_pressure(
    context: SiteContext, inference: dict
) -> tuple[dict[str, float], str]:
    """Normalise a bow-tie inference result into pressure context for the UI.

    Args:
        context: the site.
        inference: the top-event marginal, either as
            ``{"Low": .., "Moderate": .., "High": ..}`` or wrapped as
            ``{"top_event": {...}, "label": "...", "region": "..."}``.

    Returns:
        (probabilities, note). Probabilities are normalised to sum to 1.

    Raises:
        BowtieUnavailable: the result is unusable. The API catches this and reports
            the note instead, leaving the ranking untouched.
    """
    if not isinstance(inference, dict):
        raise BowtieUnavailable("bow-tie inference must be a mapping")

    marginal = inference.get("top_event", inference)
    if not isinstance(marginal, dict):
        raise BowtieUnavailable("bow-tie result has no top-event marginal")

    values: dict[str, float] = {}
    for state in TOP_EVENT_STATES:
        if state not in marginal:
            continue
        try:
            values[state] = float(marginal[state])
        except (TypeError, ValueError) as exc:
            raise BowtieUnavailable(f"top-event state {state!r} is not numeric") from exc

    if not values:
        raise BowtieUnavailable(
            "top-event marginal names none of " + ", ".join(TOP_EVENT_STATES)
        )
    if any(v < 0 for v in values.values()):
        raise BowtieUnavailable("negative probability in top-event marginal")

    total = sum(values.values())
    if total <= 0:
        raise BowtieUnavailable("top-event marginal sums to zero")
    values = {k: v / total for k, v in values.items()}

    label = inference.get("label") or "bow-tie scenario"
    note = f"Eutrophication pressure from the MARBEFES bow-tie ({label})."
    if context.region not in LAGOON_REGIONS:
        note += (
            f" The published bow-tie is parameterised for the Curonian Lagoon; this "
            f"site is {context.region}. Read it as pressure context for the decision, "
            f"not as a risk estimate for this water body."
        )
    note += (
        " Reported beside the ranking and never folded into it: a yield weighted by a "
        "risk probability is neither a yield nor a risk."
    )
    return values, note


def removal_framing(pressure: dict[str, float], high_threshold: float = 0.4) -> str:
    """One sentence putting nutrient removal in the context of the pressure.

    This is the only place the two are allowed to meet, and they meet in prose where
    a reader can see the reasoning, not in arithmetic where they cannot.
    """
    if not pressure:
        return ""
    high = pressure.get("High", 0.0)
    if high >= high_threshold:
        return (
            f"P(top event High) = {high:.2f}. At this pressure, removal by farming is "
            f"mitigation of an active problem, and the case for scale is stronger."
        )
    return (
        f"P(top event High) = {high:.2f}. At this pressure, removal by farming is "
        f"maintenance rather than mitigation; the ecological case rests less on "
        f"nutrient figures and more on habitat and community outcomes."
    )
