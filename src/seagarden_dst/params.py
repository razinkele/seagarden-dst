"""Parameter sets, loaded from YAML and validated with pydantic.

Specification section 3.2: coefficients live in version-controlled YAML so that the
M24->M30 recalibration against WP3 A3.4 pilot data is a *data* change, not a software
release. Nothing in this package may hard-code a rate coefficient.

Pydantic validates at load time so a malformed parameter file fails immediately rather
than halfway through an analysis a user is watching.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

from .calibration import Calibration, Tier

# params/ lives beside the repository root, not inside the package: it is data the
# project curates and republishes under the open-data commitment, not code.
DEFAULT_PARAM_ROOT = Path(__file__).resolve().parents[2] / "params"


class GrowthParams(BaseModel):
    """Macroalgal growth coefficients - specification section 7.2.

    Multiplicative formulation adapted from OLAMUR D3.2, which re-parameterised a
    Saccharina framework for Fucus after sugar kelp failed at low salinity in
    Tagalaht Bay (5.5-6.5 psu).

        dB/dt = mu_max * f(I) * f(T) * f(N) * B - losses(B)
    """

    mu_max: float = Field(gt=0, description="Maximum specific growth rate, 1/day")
    i_k: float = Field(gt=0, description="Saturating irradiance, umol photons/m2/s")
    arrhenius_temp: float = Field(
        gt=0, description="Arrhenius temperature T_A, K (DEB-style correction)"
    )
    ref_temp_c: float = Field(description="Reference temperature for T_A, degrees C")
    upper_temp_c: float | None = Field(
        default=None, description="Temperature above which growth declines, degrees C"
    )
    upper_temp_decline_c: float = Field(
        default=3.0,
        gt=0,
        description=(
            "Width, degrees C, of the Gaussian decline above upper_temp_c. ASSUMED - "
            "no source fits this value."
        ),
    )
    k_nitrate: float = Field(
        gt=0, description="Half-saturation constant for nitrate, Holling type II, umol N/L"
    )
    loss_rate: float = Field(ge=0, description="Linear loss (erosion, mortality), 1/day")
    b_initial: float = Field(gt=0, description="Seeded biomass, g DW/m2")
    b_max: float | None = Field(
        default=None, description="Carrying capacity of the cultivation unit, g DW/m2"
    )
    b_max_basis: str | None = Field(
        default=None,
        description=(
            "Where b_max comes from. 'assumed_from_anchor' means it is the "
            "validation anchor's own upper bound, so the model cannot overshoot the "
            "range it is checked against - not an independent source."
        ),
    )


class SalinityResponse(BaseModel):
    """Piecewise salinity scaling of maximum yield.

    From OLAMUR D2.3 / Maar et al. 2023, for Saccharina:

        f = 1                  for S >= 25
        f = 1 + (S - 25)/18    for 16 <= S < 25
        f = S/32               for S < 16

    Note that OLAMUR found *no* salinity term was needed for Fucus once the growth
    model was calibrated for Baltic conditions - salinity was not limiting for Fucus
    once adapted. Species whose growth is salinity-insensitive set `applies: false`,
    and the tool states that explicitly on its methods page, because users expect a
    salinity term and its absence otherwise looks like an omission.
    """

    applies: bool = True
    upper_psu: float = 25.0
    lower_psu: float = 16.0
    upper_divisor: float = 18.0
    lower_divisor: float = 32.0
    tolerance_floor_psu: float | None = Field(
        default=None,
        description="Salinity below which cultivation is contraindicated (tier D), psu",
    )
    floor_basis: Literal["observed", "assumed"] = Field(
        default="assumed",
        description=(
            "Whether tolerance_floor_psu rests on an observed cultivation failure or is "
            "assumed. Governs what contraindication() is allowed to tell the user: only "
            "an observed floor may be reported as a finding (specification 7.4, tier D)."
        ),
    )
    demonstrated_salinity_range: tuple[float, float] | None = Field(
        default=None,
        description=(
            "Salinity range the parameters were actually established in. Provenance that "
            "widens the displayed band; NOT a tier D trigger - extrapolation beyond it is "
            "tier B or C per specification 7.4."
        ),
    )

    def factor(self, salinity_psu: float) -> float:
        if not self.applies:
            return 1.0
        if salinity_psu >= self.upper_psu:
            return 1.0
        if salinity_psu >= self.lower_psu:
            return 1.0 + (salinity_psu - self.upper_psu) / self.upper_divisor
        return max(salinity_psu / self.lower_divisor, 0.0)


class ElementalFractions(BaseModel):
    """Elemental composition used for nutrient-removal accounting.

    Macroalgae are expressed on dry weight, shellfish on fresh weight, following the
    convention of the sources (OLAMUR D2.3): kelp DM -> 1% N, 0.17% P, 32% C;
    mussel FW -> 10.3% DM, 1.45% N, 0.083% P, 4.61% shell C.
    """

    basis: str = Field(pattern="^(dry_weight|fresh_weight)$")
    nitrogen: float = Field(ge=0, le=1, description="Mass fraction N")
    phosphorus: float = Field(ge=0, le=1, description="Mass fraction P")
    carbon: float = Field(ge=0, le=1, description="Mass fraction C")
    dry_matter: float | None = Field(
        default=None,
        ge=0,
        le=1,
        description=(
            "DM fraction of FW. Shellfish carry it on a fresh-weight elemental basis; "
            "a salinity-indexed macroalga carries it too, to convert its published "
            "t FW/ha yield into the kg DW its elemental basis expects."
        ),
    )


class ShellfishYield(BaseModel):
    """Salinity-banded harvest model - OLAMUR D2.3 / Maar et al. 2023.

    Mitigation culture below the salinity threshold yields *more* per hectare than
    commercial culture above it, because density is optimised for nutrient removal
    rather than individual size, and the product is not food-grade. In the SE Baltic
    mitigation culture is the intended mode, not a degraded version of commercial.
    """

    threshold_psu: float = 16.0
    commercial_t_fw_ha_yr: tuple[float, float] = (16.0, 18.0)
    mitigation_t_fw_ha_yr: tuple[float, float] = (20.0, 33.0)
    density_coefficient: float = Field(
        default=1269.0, description="rho = coefficient * m_bio^(1/3)"
    )
    commercial_density_divisor: float = Field(
        default=3.15, description="Commercial density is this factor lower than mitigation"
    )
    tolerance_floor_psu: float | None = Field(
        default=None,
        description="Salinity below which cultivation is contraindicated (tier D), psu",
    )
    floor_basis: Literal["observed", "assumed"] = Field(
        default="assumed",
        description=(
            "Whether tolerance_floor_psu rests on an observed cultivation failure or is "
            "assumed. Governs what contraindication() is allowed to tell the user: only "
            "an observed floor may be reported as a finding (specification 7.4, tier D)."
        ),
    )
    demonstrated_salinity_range: tuple[float, float] | None = Field(
        default=None,
        description=(
            "Salinity range the parameters were actually established in. Provenance that "
            "widens the displayed band; NOT a tier D trigger - extrapolation beyond it is "
            "tier B or C per specification 7.4."
        ),
    )


class CalibrationEntry(BaseModel):
    """Per-region calibration status of this parameter set."""

    region: str
    tier: Tier
    source: str
    calibrated_on: str | None = None
    note: str | None = None

    def to_calibration(self) -> Calibration:
        return Calibration(
            tier=self.tier,
            region=self.region,
            source=self.source,
            calibrated_on=self.calibrated_on,
            note=self.note,
        )


class Anchor(BaseModel):
    """A published measurement the parameterisation is checked against.

    Anchors are data rather than prose because the basis is what makes them usable: a
    figure quoted per cage means something different from the same figure per square
    metre, and the Tagalaht nitrogen arm could not be reconciled precisely because
    nobody had written the basis down.
    """

    quantity: Literal["dry_weight", "carbon", "nitrogen", "phosphorus"]
    low: float
    high: float
    unit: str
    basis: str = Field(description="Per cage or per m2, DW or FW, cage area, cycle length")
    source: str
    reconciles: bool = Field(
        default=True,
        description="False where the model cannot currently reproduce this arm.",
    )


class SpeciesParams(BaseModel):
    """One species parameter set."""

    key: str
    scientific_name: str
    common_name: str
    group: str = Field(pattern="^(macroalga|shellfish)$")
    in_application_form: bool = Field(
        description="Whether the AF names this species. Governs decision D1."
    )
    cultivation_window: tuple[int, int] = Field(
        description=(
            "Deployment and harvest month, inclusive, 1-12. An end month earlier than "
            "the start month wraps the year boundary - sugar kelp goes out in autumn "
            "and comes in the following early summer."
        )
    )
    growth: GrowthParams | None = None
    salinity: SalinityResponse | None = None
    shellfish_yield: ShellfishYield | None = None
    elemental: ElementalFractions
    max_yield_t_fw_ha: float | None = Field(
        default=None, description="Reference maximum yield before salinity scaling"
    )
    yield_model: Literal["ode", "salinity_indexed"] = Field(
        default="ode",
        description=(
            "Which model produces the harvest. 'ode' is the OLAMUR D3.2 growth "
            "formulation (specification 7.2). 'salinity_indexed' is D2.3's published "
            "form for Saccharina - f_salinity multiplied by max_yield_t_fw_ha, with no "
            "ODE at all."
        ),
    )
    calibration: list[CalibrationEntry]
    anchors: list[Anchor] | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _check_salinity_indexed_is_computable(self) -> SpeciesParams:
        """A model that cannot produce a number must fail at load, not mid-analysis."""
        if self.yield_model == "salinity_indexed":
            if self.max_yield_t_fw_ha is None:
                raise ValueError(
                    "yield_model='salinity_indexed' requires max_yield_t_fw_ha to be set"
                )
            if self.elemental.dry_matter is None:
                raise ValueError(
                    "yield_model='salinity_indexed' requires elemental.dry_matter to be set"
                )
        return self

    @field_validator("cultivation_window")
    @classmethod
    def _check_window(cls, v: tuple[int, int]) -> tuple[int, int]:
        start, end = v
        if not (1 <= start <= 12 and 1 <= end <= 12):
            raise ValueError("cultivation_window months must be in 1-12")
        # A window that wraps the year boundary is legal - `forcing.daily_forcing`
        # runs the day axis past 365 for it. A single month is not: once wrapping is
        # allowed, (6, 6) could mean no days or every day, and the parameter file
        # should not carry a value whose meaning has to be guessed.
        if start == end:
            raise ValueError("cultivation_window must span at least two months")
        return v

    def calibration_for(self, region: str) -> Calibration:
        """Resolve the calibration status for a region, falling back to a literature prior.

        An unknown region is never silently treated as calibrated: the fallback is
        tier C with the region named, which is the honest default for LT and PL
        before the A3.4 data arrives.
        """
        for entry in self.calibration:
            if entry.region == region:
                return entry.to_calibration()
        for entry in self.calibration:
            if entry.region == "default":
                base = entry.to_calibration()
                return Calibration(
                    tier=base.tier,
                    region=region,
                    source=base.source,
                    calibrated_on=base.calibrated_on,
                    note=base.note,
                )
        return Calibration(
            tier=Tier.C,
            region=region,
            source="unspecified",
            note="No calibration statement for this region.",
        )

    def salinity_floor(self) -> tuple[float, str] | None:
        """The salinity below which this species is contraindicated, and whether that
        floor is observed or assumed. Resolved in one place because two parallel
        resolution rules are how tier D came to leak in the first place."""
        if self.salinity is not None and self.salinity.tolerance_floor_psu is not None:
            return self.salinity.tolerance_floor_psu, self.salinity.floor_basis
        if (
            self.shellfish_yield is not None
            and self.shellfish_yield.tolerance_floor_psu is not None
        ):
            return self.shellfish_yield.tolerance_floor_psu, self.shellfish_yield.floor_basis
        return None


class MethodParams(BaseModel):
    """A cultivation method from the WP3 A3.2 system taxonomy.

    The SeaGarden system is an anchoring unit (float, buoy/line) plus a cultivation
    unit (floating or sinking lines, rafts, mussel socks). Costs are placeholders
    until WP3 procurement is known - specification section 8.4 makes the viability
    module defensible only because its coefficients come from what the project
    actually pays.
    """

    key: str
    name: str
    anchoring_unit: str
    cultivation_unit: str
    suits_groups: list[str]
    min_depth_m: float
    max_depth_m: float
    max_significant_wave_m: float
    area_m2_per_unit: float
    capital_cost_eur_per_unit: float | None = None
    deployment_person_days: float | None = None
    harvest_person_days: float | None = None
    source: str = "placeholder - to be replaced with WP3 procurement figures"


class AssessmentParams(BaseModel):
    """Thresholds that decide a suitability verdict - specification section 5.2.

    Both fields are ASSUMED - no source fits either of them. See
    `params/assessment.yaml` for what each one binds and how tightly.
    """

    salinity_factor_floor: float = 0.35
    yield_floor_kg_dw_per_m2: float = 0.5


class ParameterSet(BaseModel):
    """Everything loaded from params/."""

    species: dict[str, SpeciesParams]
    methods: dict[str, MethodParams]
    assessment: AssessmentParams

    def species_for_group(self, group: str) -> list[SpeciesParams]:
        return [s for s in self.species.values() if s.group == group]


def load_parameters(root: Path | str | None = None) -> ParameterSet:
    """Load and validate every parameter file under `root`."""
    base = Path(root) if root is not None else DEFAULT_PARAM_ROOT
    species_dir = base / "species"
    if not species_dir.is_dir():
        raise FileNotFoundError(f"No species parameter directory at {species_dir}")

    species: dict[str, SpeciesParams] = {}
    for path in sorted(species_dir.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        parsed = SpeciesParams.model_validate(raw)
        if parsed.key in species:
            raise ValueError(f"Duplicate species key {parsed.key!r} in {path}")
        species[parsed.key] = parsed

    methods_path = base / "methods.yaml"
    methods: dict[str, MethodParams] = {}
    if methods_path.is_file():
        raw_methods = yaml.safe_load(methods_path.read_text(encoding="utf-8")) or {}
        for entry in raw_methods.get("methods", []):
            parsed_method = MethodParams.model_validate(entry)
            methods[parsed_method.key] = parsed_method

    assessment_path = base / "assessment.yaml"
    assessment_raw = yaml.safe_load(assessment_path.read_text(encoding="utf-8"))
    assessment = AssessmentParams.model_validate(assessment_raw)

    return ParameterSet(species=species, methods=methods, assessment=assessment)


@lru_cache(maxsize=1)
def default_parameters() -> ParameterSet:
    """Cached load of the shipped parameter set."""
    return load_parameters()
