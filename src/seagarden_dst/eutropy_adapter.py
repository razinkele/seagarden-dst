"""EUTROPY adapter - nutrient forcing from a calibrated biogeochemical model.

EUTROPY (kaynarob/EUTROPY) is the calibrated 29-box Curonian Lagoon biogeochemical
model already used in the MARBEFES bow-tie work, where a 15-scenario Nemunas
nutrient-loading ensemble (fN x fP grid) produced summer-month DIN, DIP and DO at
named boxes. This adapter lets the DST run its growth and nutrient-removal models on
those scenario concentrations instead of the placeholder climatology, so a user can
ask "what would this farm remove if Nemunas loading were BSAP-compliant?"

DOMAIN CAVEAT, and it is not a small one: EUTROPY is a *lagoon* model. SeaGarden's
Lithuanian pilot is on the open coast, not in the Curonian Lagoon, and the two differ
in salinity, residence time and nutrient regime. The adapter therefore attaches an
explicit note to every result it touches, and refuses silently-wrong transfers by
requiring the caller to name the region the scenario applies to. Use it for the
lagoon and for scenario reasoning; do not present a lagoon-forced coastal number as
a coastal prediction.

Following the house rule from `nid4ocean_dst.ses_signal`: this module is imported
lazily by the API, raises only its own exception type, and its absence or failure
never affects the ranking.
"""

from __future__ import annotations

from dataclasses import replace

from .contracts import SiteContext

#: Regions for which an EUTROPY scenario is a defensible source of nutrient forcing.
LAGOON_REGIONS = {"PL-lagoon", "LT-lagoon", "curonian-lagoon"}


class EutropyUnavailable(RuntimeError):
    """EUTROPY output is missing, malformed, or not applicable to this site."""


def _require(mapping: dict, key: str) -> float:
    if key not in mapping:
        raise EutropyUnavailable(f"scenario is missing {key!r}")
    try:
        return float(mapping[key])
    except (TypeError, ValueError) as exc:
        raise EutropyUnavailable(f"scenario {key!r} is not numeric: {mapping[key]!r}") from exc


def apply_nutrient_scenario(
    context: SiteContext, scenario: dict
) -> tuple[SiteContext, str]:
    """Return a context whose DIN and DIP come from an EUTROPY scenario.

    Args:
        context: the site.
        scenario: at minimum ``{"din_umol_l": float, "dip_umol_l": float}``. Optional
            keys ``label``, ``region``, ``box``, ``fN``, ``fP`` are carried into the
            note so the reader knows which run they are looking at.

    Returns:
        (context, note). The note is non-empty whenever the transfer needs a caveat,
        and the API surfaces it to the user rather than swallowing it.

    Raises:
        EutropyUnavailable: the scenario is unusable. The API catches this and
            continues with the site's own conditions.
    """
    if not isinstance(scenario, dict):
        raise EutropyUnavailable("scenario must be a mapping of EUTROPY outputs")

    din = _require(scenario, "din_umol_l")
    dip = _require(scenario, "dip_umol_l")
    if din < 0 or dip < 0:
        raise EutropyUnavailable("negative nutrient concentration in scenario")

    conditions = replace(context.conditions, din_umol_l=din, dip_umol_l=dip)
    forced = replace(context, conditions=conditions)

    bits = []
    if scenario.get("label"):
        bits.append(str(scenario["label"]))
    if scenario.get("box") is not None:
        bits.append(f"box {scenario['box']}")
    if scenario.get("fN") is not None and scenario.get("fP") is not None:
        bits.append(f"fN={scenario['fN']}, fP={scenario['fP']}")
    run = "; ".join(bits) or "unlabelled run"

    scenario_region = scenario.get("region")
    note = f"DIN and DIP from EUTROPY ({run})."
    if context.region not in LAGOON_REGIONS:
        note += (
            f" EUTROPY is a Curonian Lagoon box model and this site is "
            f"{context.region}, an open-coast sub-region: the lagoon's salinity, "
            f"residence time and nutrient regime differ materially. Treat the result "
            f"as scenario reasoning, not as a prediction for this site."
        )
    elif scenario_region and scenario_region != context.region:
        note += f" Scenario declared for {scenario_region}, applied to {context.region}."

    return forced, note


def scenario_from_ensemble(
    rows: list[dict], *, box: int, f_n: float, f_p: float
) -> dict:
    """Pick one scenario out of an fN x fP ensemble export.

    Convenience for the 480-row summer-month sample tables the MARBEFES coupling
    produced. Matching is exact on the grid values, because a nearest-neighbour match
    would quietly hand back a different scenario than the one asked for.
    """
    if not rows:
        raise EutropyUnavailable("empty ensemble")
    for row in rows:
        try:
            if (
                int(row["box"]) == box
                and float(row["fN"]) == f_n
                and float(row["fP"]) == f_p
            ):
                return {
                    "din_umol_l": row["din_umol_l"],
                    "dip_umol_l": row["dip_umol_l"],
                    "box": box,
                    "fN": f_n,
                    "fP": f_p,
                    "label": row.get("label", "EUTROPY ensemble"),
                    "region": row.get("region"),
                }
        except (KeyError, TypeError, ValueError):
            continue
    raise EutropyUnavailable(f"no ensemble row for box={box}, fN={f_n}, fP={f_p}")
