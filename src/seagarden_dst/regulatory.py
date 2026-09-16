"""Regulatory and permitting records - specification section 9.

Package G of the data-layer design. This module is the *schema* and nothing else.
The content it describes does not exist yet and is not borrowable: it is produced
in-project by GMU's A2.2 external legal expertise (EUR 5,500, M12) across Denmark,
Germany, Poland and Lithuania, then tested against reality by WP3 A3.1, which runs
actual permitting in all four from day one.

Why a schema before there is anything to put in it. Whether that expertise arrives
as structured records or as four PDFs depends on whether a shape exists to hand the
lawyers beforehand. Shipping the schema plus one worked example makes the failure
mode "a schema revised at M12" instead of "a transcription project at M12".

Two invariants this module exists to hold:

1. **An absent record blocks.** Four jurisdictions, zero records today. A missing
   record must read as *not assessable*, never as *no restrictions*. `assess_legal`
   in `suitability.py` already returns UNKNOWN for an absent layer; package F2 wires
   the populated case. Nothing here may make "no record" look permissive.

2. **An illustrative record can never be served as a real one.** The example below is
   structurally complete so the shape can be reviewed, and obviously synthetic so it
   cannot be mistaken for legal guidance. The type enforces the pairing: jurisdiction
   EXAMPLE if and only if `illustrative` is true.

Staleness (section 9.3): regulation drifts, and the durability commitment to 2034
makes this the module most likely to go quietly wrong. Every record carries a
`verified_on` date, the tool displays it, and past `STALENESS_YEARS` the tool says so
on the record rather than presenting it as current. `today` is always a parameter -
never `date.today()` inside the model - so the test suite does not turn red on a
calendar boundary that has nothing to do with the code.
"""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

# params/ lives beside the repository root, not inside the package: it is data the
# project curates and republishes under the open-data commitment, not code. Same
# reasoning, and the same location, as `params.DEFAULT_PARAM_ROOT`.
DEFAULT_REGULATORY_ROOT = Path(__file__).resolve().parents[2] / "params" / "regulatory"

# The four jurisdictions of the Application Form. WP3 A3.1 runs permitting in each.
JURISDICTIONS: tuple[str, ...] = ("DK", "DE", "PL", "LT")

# Section 9.3: "When a record is more than two years old the tool says so."
STALENESS_YEARS = 2

Jurisdiction = Literal["DK", "DE", "PL", "LT", "EXAMPLE"]


def _years_before(today: date, years: int) -> date:
    """`today` shifted back whole years, without a leap-day crash.

    29 February has no counterpart in a non-leap year, so it folds to the 28th. A
    one-day approximation once every four years is the right trade against either a
    `dateutil` dependency (the core keeps four) or a 365.25-day drift that would make
    the boundary unpredictable.
    """
    try:
        return today.replace(year=today.year - years)
    except ValueError:
        return today.replace(year=today.year - years, day=28)


class CompetentAuthority(BaseModel):
    """Who decides what, and how to reach them - section 9.1."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, description="Authority as it is formally named")
    decides: str = Field(min_length=1, description="Which decision this body owns")
    contact_route: str = Field(
        min_length=1, description="How an applicant actually reaches it: portal, office, e-mail"
    )


class PermitType(BaseModel):
    """A permit, by activity and scale - section 9.1.

    `exempt_below` is called out separately from the prose because section 9.2 names
    it the single most valuable fact for the Start door: the answer to "do we even
    need a permit for something this small".
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    activity: str = Field(min_length=1, description="What the permit covers")
    exempt_below: str | None = Field(
        default=None,
        description=(
            "Threshold below which the activity is exempt or follows a simplified "
            "route, stated with its unit. None means no threshold exists - which is "
            "NOT the same as 'not yet checked', recorded as an explicit note instead."
        ),
    )
    issuing_authority: str = Field(min_length=1, description="Must match a CompetentAuthority name")


class SpatialExclusion(BaseModel):
    """A hard spatial exclusion - section 9.1.

    Consumed directly by section 5.2's `legal_permissibility` term, which is a MINIMUM
    across constraint classes rather than a weighted index, precisely so that a fatal
    exclusion cannot be averaged away by good water. Each exclusion therefore has to
    be traceable to a named legal instrument - package F2's done-when requires it.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, description="The excluded zone or designation")
    legal_basis: str = Field(
        min_length=1, description="The named act, regulation or designation it rests on"
    )
    absolute: bool = Field(
        default=True,
        description=(
            "True where no derogation exists. False where the activity is possible "
            "subject to conditions, which the procedural sequence then carries."
        ),
    )


class ProceduralStep(BaseModel):
    """One step of the permitting sequence - section 9.1."""

    model_config = ConfigDict(extra="forbid")

    order: int = Field(ge=1, description="Position in the sequence, 1-based")
    step: str = Field(min_length=1)
    typical_duration_days: int | None = Field(
        default=None, ge=0, description="Observed typical duration; None where unknown"
    )
    required_documents: list[str] = Field(default_factory=list)
    consultation: str | None = Field(
        default=None, description="Consultation obligation attaching to this step, if any"
    )


class AssessmentTrigger(BaseModel):
    """An environmental-assessment threshold - section 9.1."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["EIA", "SEA", "Natura2000"] = Field(description="Assessment regime")
    threshold: str = Field(
        min_length=1, description="What triggers it, with its unit where numeric"
    )
    note: str | None = None


class PolicyHook(BaseModel):
    """How the activity relates to a standing policy instrument - section 9.1."""

    model_config = ConfigDict(extra="forbid")

    instrument: Literal["HELCOM-BSAP", "WFD", "MSFD", "MSP"] = Field(
        description="HELCOM Baltic Sea Action Plan, Water Framework Directive, "
        "Marine Strategy Framework Directive, or the national Maritime Spatial Plan"
    )
    relation: str = Field(min_length=1, description="The hook, stated plainly")


class RegulatoryRecord(BaseModel):
    """One jurisdiction's permitting picture - section 9.1.

    A structured record rather than prose, so that section 9.2 can serve three
    different doors from one source: the full procedural map for Plan, a polygon
    checklist for Farm, and the exemption threshold for Start.
    """

    model_config = ConfigDict(extra="forbid")

    jurisdiction: Jurisdiction
    verified_on: date = Field(
        description="When a human last checked this record against the law in force"
    )
    illustrative: bool = Field(
        default=False,
        description=(
            "True only for the committed EXAMPLE record. Mirrors the "
            "`b_max_basis: assumed_from_anchor` idiom: the file says what it is, so "
            "nothing downstream has to infer it."
        ),
    )
    source_note: str = Field(
        min_length=1, description="Who compiled this record and from what"
    )

    authorities: list[CompetentAuthority] = Field(default_factory=list)
    permits: list[PermitType] = Field(default_factory=list)
    exclusions: list[SpatialExclusion] = Field(default_factory=list)
    procedure: list[ProceduralStep] = Field(default_factory=list)
    assessment_triggers: list[AssessmentTrigger] = Field(default_factory=list)
    policy_hooks: list[PolicyHook] = Field(default_factory=list)

    @model_validator(mode="after")
    def _illustrative_iff_example(self) -> RegulatoryRecord:
        """EXAMPLE if and only if illustrative.

        Both directions matter. A real jurisdiction marked illustrative would be
        served to users behind a "not real" banner and ignored; an EXAMPLE record
        NOT marked illustrative would be served as though it were law. The second is
        the one that must never happen, so the type refuses both.
        """
        is_example = self.jurisdiction == "EXAMPLE"
        if is_example != self.illustrative:
            raise ValueError(
                "jurisdiction EXAMPLE and illustrative=True must be set together "
                f"(jurisdiction={self.jurisdiction!r}, illustrative={self.illustrative})"
            )
        return self

    @model_validator(mode="after")
    def _permits_name_a_known_authority(self) -> RegulatoryRecord:
        """A permit may not be issued by a body the record does not list.

        Cheap to enforce here, and it turns a transcription slip at M12 into a load
        error rather than a dangling reference the Farm door renders as a blank.
        """
        known = {a.name for a in self.authorities}
        unknown = sorted({p.issuing_authority for p in self.permits} - known)
        if unknown:
            raise ValueError(
                f"permit issuing_authority not listed in authorities: {unknown}"
            )
        return self

    def is_stale(self, today: date) -> bool:
        """Has this record gone more than `STALENESS_YEARS` without verification?"""
        return self.verified_on < _years_before(today, STALENESS_YEARS)

    def staleness_note(self, today: date) -> str:
        """The line section 9.3 requires the tool to display on every record.

        Always states the verification date - a fresh record still has to show one,
        because "when was this checked" is the question a permitting authority asks
        first. Adds the warning only once the record is actually stale.
        """
        shown = self.verified_on.isoformat()
        if self.is_stale(today):
            return (
                f"Verified on {shown}, more than {STALENESS_YEARS} years ago. "
                "Regulation may have changed since; re-check before relying on this."
            )
        return f"Verified on {shown}."


class RegulatoryRegistry(BaseModel):
    """The record set, and an honest account of what is missing from it.

    Today this is empty for all four jurisdictions. `missing()` is the method that
    makes that legible rather than implicit, and `for_jurisdiction` returns None
    rather than raising, because "no record" is the expected state until M12 and not
    an error.
    """

    model_config = ConfigDict(extra="forbid")

    records: dict[str, RegulatoryRecord] = Field(default_factory=dict)

    def for_jurisdiction(self, code: str) -> RegulatoryRecord | None:
        """The record for a real jurisdiction, or None where none has been compiled.

        Never returns the illustrative example: it is keyed under EXAMPLE, which is
        not one of `JURISDICTIONS`, so a caller asking for "LT" cannot receive it
        even by accident.
        """
        if code not in JURISDICTIONS:
            return None
        return self.records.get(code)

    def missing(self) -> tuple[str, ...]:
        """Jurisdictions with no record. All four, until GMU's A2.2 content lands."""
        return tuple(j for j in JURISDICTIONS if j not in self.records)

    def example(self) -> RegulatoryRecord | None:
        """The committed worked example, if one is present."""
        return self.records.get("EXAMPLE")

    def coverage_note(self) -> str:
        """One line for section 9.2 to show wherever a legal verdict is absent."""
        missing = self.missing()
        if not missing:
            return "Regulatory records loaded for all four jurisdictions."
        return (
            f"No regulatory record for: {', '.join(missing)}. Legal permissibility "
            "cannot be assessed - this is not a finding that the site is clear. "
            "Records are produced by A2.2 (M12) and tested by WP3 A3.1."
        )


def load_regulatory_records(root: Path | None = None) -> RegulatoryRegistry:
    """Load every `*.yaml` under `params/regulatory/`, keyed by jurisdiction.

    A missing directory yields an empty registry rather than an error: the empty
    state is the correct one today, and the tool must start in it.
    """
    root = root or DEFAULT_REGULATORY_ROOT
    records: dict[str, RegulatoryRecord] = {}
    if not root.is_dir():
        return RegulatoryRegistry(records=records)

    for path in sorted(root.glob("*.yaml")):
        with path.open(encoding="utf-8") as fh:
            record = RegulatoryRecord(**yaml.safe_load(fh))
        if record.jurisdiction in records:
            raise ValueError(f"duplicate regulatory record for {record.jurisdiction}: {path}")
        records[record.jurisdiction] = record
    return RegulatoryRegistry(records=records)


@lru_cache(maxsize=1)
def default_registry() -> RegulatoryRegistry:
    """The registry as shipped. Cached, like `params.default_parameters`."""
    return load_regulatory_records()
