"""The regression net.

Captures assess_site() and scenarios.compare() for every site and species, so that a
change which moves a number has to say so in a diff. Every package after this one
should produce an empty diff here unless its plan says otherwise - package A is the
one that says otherwise.

Two halves live in one golden file, tests/golden/assessments.json, under the keys
"assess_site" and "scenarios":

- "assess_site" captures what api.assess_site() returns for every placeholder site:
  which species are excluded and why, and the ranked options' species key, harvest
  value, unit, calibration tier and nitrogen removal, plus the full constraints list
  (physical feasibility, environmental tolerance, growth viability, legal
  permissibility - name, verdict, reason for each). It does NOT capture Verdict or
  Binding constraint as the UI renders them, nor the tier-C display banding.

- "scenarios" captures scenarios.compare() for every placeholder site, across every
  species for which api.select_method() finds a workable default method at the
  "community farm (0.1 ha)" scale. This is the only half that captures Verdict,
  Binding constraint and the tier-C display banding, so it is what would catch a
  future threshold change or a for_display() regression that the assess_site half
  cannot see. It is a COARSER net than the assess_site half: every numeric cell is a
  string at three significant figures via str(for_display(q)) - a tier C harvest
  reads like "202-1.82e+03 kg DW [C]", not a point value - and Calibration is
  tier.label ("Literature prior"), not tier.value ("C").

  scenarios.default_scenarios() is NOT used here even though it exists for exactly
  this purpose: it hands every macroalga the 6 m2 mini-farm kit regardless of site
  depth, which reads every LT-coastal-style site as "unsuitable" for a reason that is
  an artefact of the default method rather than a fact about the site (see
  api.select_method's docstring). It also has no scenario-count escape hatch of its
  own - scenarios.compare() defaults to a 4-scenario comparison panel and five
  species ship, so compare(default_scenarios(...)) raises ValueError. select_method()
  is used directly instead, with limit=None passed to compare().

To regenerate deliberately:
    micromamba run -n shiny python -m pytest \\
        tests/test_golden_snapshot.py --snapshot-update
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from seagarden_dst import (
    PLACEHOLDER_SITES,
    SCALES,
    Scenario,
    SiteContext,
    assess_site,
    compare,
    default_parameters,
)
from seagarden_dst.api import select_method

GOLDEN = Path(__file__).parent / "golden" / "assessments.json"

#: Scale used for the scenarios half. Matches assess_site()'s own default scale, so
#: the two halves describe the same hardware.
SCALE = "community farm (0.1 ha)"


def _capture_assess_site() -> dict:
    out = {}
    for region in sorted(PLACEHOLDER_SITES):
        result = assess_site(SiteContext.from_region(region))
        out[region] = {
            "excluded": dict(sorted(result.excluded.items())),
            "ranked": [
                {
                    "species": option.species_key,
                    "harvest": round(option.harvest.value, 6),
                    "unit": option.harvest.unit,
                    "tier": option.harvest.calibration.tier.value,
                    "nitrogen": round(option.nitrogen_value, 6),
                    "constraints": [list(c) for c in option.constraints],
                }
                for option in result.ranked
            ],
        }
    return out


def _capture_scenarios() -> dict:
    """Scenario comparison for every site, across every species that selects a method.

    Runs scenarios.compare(limit=None) rather than the 4-scenario default panel,
    because five species ship and the panel raises past four. `label=key` keeps
    labels stable if a common_name is ever edited. `Scenario.site` takes the raw
    `SiteConditions` from PLACEHOLDER_SITES, not the `SiteContext` that assess_site
    takes - the two capture functions build their site objects differently on
    purpose, matching what each underlying call actually accepts.
    """
    params = default_parameters()
    area = SCALES[SCALE]
    out = {}
    for region in sorted(PLACEHOLDER_SITES):
        site = PLACEHOLDER_SITES[region]
        scens = []
        for key in sorted(params.species):
            sp = params.species[key]
            method = select_method(sp, params, site, area)
            if method is None:
                continue
            scens.append(
                Scenario(label=key, species=sp, method=method, site=site, area_m2=area)
            )
        out[region] = compare(scens, limit=None).to_dict(orient="records")
    return out


def _capture() -> dict:
    return {"assess_site": _capture_assess_site(), "scenarios": _capture_scenarios()}


def test_assessments_match_the_golden_file(pytestconfig):
    current = _capture()
    if pytestconfig.getoption("--snapshot-update", default=False):
        GOLDEN.parent.mkdir(exist_ok=True)
        GOLDEN.write_text(json.dumps(current, indent=2, sort_keys=True), encoding="utf-8")
        pytest.skip("golden file regenerated")

    assert GOLDEN.exists(), "run with --snapshot-update to create the golden file"
    expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert current == expected, (
        "An assessment or scenario comparison moved. If deliberate, explain the diff "
        "in the commit message and regenerate with --snapshot-update. If not, you "
        "have found a regression."
    )
