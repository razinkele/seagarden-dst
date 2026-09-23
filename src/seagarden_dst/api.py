"""Top-level DST core API consumed by the Shiny UI.

One entry point, `assess_site`, exactly as in `nid4ocean_dst.api`. The UI calls this
and renders what comes back; it never reaches into `growth`, `shellfish` or
`suitability` directly.

Optional engines (EUTROPY for nutrient forcing, bowtiepy for eutrophication pressure)
follow the house rule established by `ses_signal`: they are passed in, they are tried
inside a try/except, and their absence or failure NEVER affects the ranking. A tool
that falls over because an optional sibling package is missing is worse than one that
says "not computed".
"""

from __future__ import annotations

from .bowtie_adapter import BowtieUnavailable, eutrophication_pressure
from .calibration import Tier
from .contracts import SiteAssessment, SiteContext, SpeciesOption
from .eutropy_adapter import EutropyUnavailable, apply_nutrient_scenario
from .forcing import (
    DEFAULT_FORCING,
    PLACEHOLDER_YEAR,
    ForcingSource,
    ForcingUnavailable,
    SiteConditions,
)
from .growth import contraindication, harvest_biomass
from .nutrients import from_harvest
from .params import MethodParams, ParameterSet, SpeciesParams, default_parameters
from .scenarios import SCALES
from .shellfish import harvest as shellfish_harvest
from .suitability import assess


def select_method(
    species: SpeciesParams,
    params: ParameterSet,
    conditions: SiteConditions,
    area_m2: float,
) -> MethodParams | None:
    """Pick a sensible default cultivation method for this species, site and scale.

    Taking simply the first method that suits the group is wrong twice over: it
    ignores the water depth, and it ignores the scale being asked about. Both showed
    up immediately in use - every macroalga defaulted to the 6 m2 mini-farm kit and
    then failed on depth at a 12 m site, so the whole ranking read "unsuitable" for a
    reason that was an artefact of the default rather than a fact about the place.

    The rule, in order:
      1. the method must suit the species group;
      2. prefer methods whose depth window contains the site depth;
      3. among those, prefer the largest unit that still fits inside the requested
         area, so a 0.1 ha farm is not modelled as a citizen-science kit;
      4. if nothing fits the area, take the smallest unit rather than nothing.

    The user can always override per species - this only decides the default.
    """
    candidates = [m for m in params.methods.values() if species.group in m.suits_groups]
    if not candidates:
        return None

    workable = [
        m for m in candidates if m.min_depth_m <= conditions.depth_m <= m.max_depth_m
    ]
    pool = workable or candidates

    fits = [m for m in pool if m.area_m2_per_unit <= area_m2]
    if fits:
        return max(fits, key=lambda m: m.area_m2_per_unit)
    return min(pool, key=lambda m: m.area_m2_per_unit)


def _assess_one(
    context: SiteContext,
    species: SpeciesParams,
    method: MethodParams,
    area_m2: float,
    forcing: ForcingSource = DEFAULT_FORCING,
    year: int = PLACEHOLDER_YEAR,
) -> SpeciesOption:
    suitability = assess(context.conditions, species, method, forcing=forcing, year=year)

    if species.group == "shellfish":
        harvest = shellfish_harvest(
            species, context.conditions, area_ha=area_m2 / 10_000.0
        ).fresh_weight
    else:
        harvest = harvest_biomass(
            species, context.conditions, area_m2, forcing=forcing, year=year
        )

    removal = from_harvest(species, harvest) if harvest.calibration.is_reportable else None

    return SpeciesOption(
        species_key=species.key,
        species_name=species.common_name,
        method_key=method.key,
        method_name=method.name,
        area_m2=area_m2,
        verdict=suitability.verdict.value,
        binding_constraint=suitability.explain(),
        tier=harvest.calibration.tier,
        harvest=harvest,
        nitrogen=None if removal is None else removal.nitrogen,
        phosphorus=None if removal is None else removal.phosphorus,
        carbon=None if removal is None else removal.carbon,
        constraints=[(c.name, c.verdict.value, c.reason) for c in suitability.constraints],
    )


def assess_site(
    context: SiteContext,
    *,
    forcing: ForcingSource = DEFAULT_FORCING,
    year: int = PLACEHOLDER_YEAR,
    params: ParameterSet | None = None,
    species: list[str] | None = None,
    methods: dict[str, str] | None = None,
    scale: str = "community farm (0.1 ha)",
    eutropy: dict | None = None,
    bowtie: dict | None = None,
) -> SiteAssessment:
    """Assess one site across the selected species.

    Args:
        context: the site. Its `conditions` may already come from an injected
            `ForcingSource` via `SiteContext.from_region(..., forcing=...)` — that
            only supplies the site anchors, not the seasonal series consumed below,
            which is why this function takes its own `forcing`.
        forcing: seasonal forcing source for the growth model; defaults to the
            scaffold's placeholder. Pass the same source used to build `context` so
            a result is never derived from real anchors and an invented season at
            once.
        year: the query year, threaded to `simulate()` via `harvest_biomass()` and
            `suitability.assess()`. Defaults to the scaffold's placeholder year,
            which `PlaceholderForcing.daily_forcing` ignores. A species whose
            cultivation window wraps the year boundary needs `year + 1` too
            (`gridded.GriddedForcing.daily_forcing`); when the source raises
            `ValueError` because it cannot cover that window, the species is
            excluded with that message rather than the whole assessment failing.
        params: parameter set; defaults to the shipped one.
        species: species keys to consider; defaults to all.
        methods: optional species_key -> method_key overrides.
        scale: a key of `scenarios.SCALES`.
        eutropy: optional EUTROPY scenario output. When supplied, the site's nutrient
            forcing is replaced by the scenario's — see `eutropy_adapter`.
        bowtie: optional bow-tie inference result. When supplied, its top-event
            probabilities are reported beside the ranking as pressure context.

    Never raises on an optional engine. Domain and calibration caveats travel on the
    result, not in a log nobody reads.
    """
    # §7: a site whose conditions are unknown must block rather than score. Returning a
    # verdict here would be a definitive negative manufactured from missing data, which
    # is the failure the whole unassessable mechanism exists to prevent.
    if context.conditions is None:
        return SiteAssessment(
            context=context,
            ranked=[],
            unassessable=True,
            coverage=context.coverage,
            nearest_valid_km=context.nearest_valid_km,
        )

    params = params or default_parameters()
    keys = list(species or params.species)
    methods = dict(methods or {})
    if scale not in SCALES:
        raise KeyError(f"Unknown scale {scale!r}; expected one of {list(SCALES)}")
    area_m2 = SCALES[scale]

    # Optional nutrient forcing. Applied BEFORE anything is assessed, so every option
    # in the ranking sees the same water.
    working = context
    caveats: dict[str, str] = {}
    if eutropy is not None:
        try:
            working, note = apply_nutrient_scenario(context, eutropy)
            if note:
                caveats["nutrient forcing"] = note
        except EutropyUnavailable as exc:
            caveats["nutrient forcing"] = f"EUTROPY forcing not applied: {exc}"

    excluded: dict[str, str] = {}
    options: list[SpeciesOption] = []

    for key in keys:
        species_params = params.species.get(key)
        if species_params is None:
            excluded[key] = "No parameter file for this species."
            continue

        method_key = methods.get(key)
        method = (
            params.methods.get(method_key)
            if method_key
            else select_method(species_params, params, working.conditions, area_m2)
        )
        if method is None:
            excluded[key] = "No cultivation method in the catalogue suits this species."
            continue

        # Contraindication is an exclusion, not a low score. A tier D pairing is kept
        # visible with its reason rather than ranked last and scrolled past.
        contra = contraindication(species_params, working.conditions)
        if contra is not None:
            excluded[key] = contra.note or "Contraindicated at this site."
            continue

        try:
            options.append(
                _assess_one(working, species_params, method, area_m2, forcing=forcing, year=year)
            )
        except ForcingUnavailable as exc:
            # The reader's own message (a window past a year the artifact does not
            # carry) IS the reason - not a second summary of it. Only this species is
            # excluded; the rest of the loop proceeds. Deliberately NOT a bare
            # ValueError: a missing growth parameter or a bug in a source is a defect
            # that must fail loudly, not appear as a quietly excluded species.
            excluded[key] = str(exc)
            continue

    ranked = sorted(options, key=lambda o: o.nitrogen_value, reverse=True)
    best = next((o for o in ranked if o.is_reportable and o.verdict != "unsuitable"), None)

    pressure: dict[str, float] = {}
    pressure_note = ""
    if bowtie is not None:
        try:
            pressure, pressure_note = eutrophication_pressure(working, bowtie)
        except BowtieUnavailable as exc:
            pressure_note = str(exc)

    if working.conditions is not context.conditions:
        caveats.setdefault(
            "site conditions",
            "Nutrient concentrations were overridden by a scenario; other conditions "
            "are unchanged.",
        )
    weakest = None
    tiers = [o.tier for o in ranked if o.is_reportable]
    if tiers:
        order = [Tier.A, Tier.B, Tier.C]
        weakest = max(tiers, key=lambda t: order.index(t) if t in order else 99)
    if weakest is Tier.C:
        caveats.setdefault(
            "calibration",
            "At least one option rests on literature priors with no local validation. "
            "Read the harvest figures as indicative bands.",
        )

    return SiteAssessment(
        context=working,
        ranked=ranked,
        best=best,
        excluded=excluded,
        caveats=caveats,
        pressure=pressure,
        pressure_note=pressure_note,
    )
