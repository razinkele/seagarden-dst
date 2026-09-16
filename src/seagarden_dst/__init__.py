"""SeaGarden Decision Support Tool - analytical core (A2.3 / D2.2).

Interreg South Baltic project STHB.02.02-IP.01-0006/25.
Lead partner: Klaipeda University, Marine Research Institute.

Structured after `nid4ocean_dst`: a pure analytical core with a single `assess_site`
entry point, UI- and IO-agnostic contracts, and optional engines that degrade quietly
rather than taking the tool down with them. The Shiny app in `app/` depends on this
package; this package knows nothing about the app.

    contracts    SiteContext in, SiteAssessment out
    api          assess_site() - the only entry point the UI uses
    calibration  calibration tiers that travel with every number (spec 7.4)
    params       YAML parameter sets, pydantic-validated (spec 3.2)
    forcing      site conditions and seasonal forcing (spec 6) - STUBBED, behind
                 the ForcingSource seam the data layer substitutes into
    growth       macroalgal growth, OLAMUR D3.2 formulation (spec 7.2)
    shellfish    salinity-banded yield, conservative carbon accounting (spec 7.3)
    nutrients    N, P and C removal from harvest (spec 7)
    suitability  minimum-of-constraints siting verdict (spec 5.2)
    scenarios    method and scale comparison (spec 5.4)

Optional engines, both from the KU MRI estate, both beside the ranking and never
merged into it:

    eutropy_adapter  nutrient forcing from the calibrated EUTROPY box model
    bowtie_adapter   eutrophication pressure from the MARBEFES bowtiepy network
"""

from .api import assess_site
from .bowtie_adapter import BowtieUnavailable, removal_framing
from .calibration import Calibration, Quantity, Tier
from .contracts import SiteAssessment, SiteContext, SpeciesOption
from .eutropy_adapter import EutropyUnavailable
from .forcing import (
    DEFAULT_FORCING,
    PLACEHOLDER_SITES,
    REGIONS,
    SITE_COORDINATES,
    ForcingSource,
    SiteConditions,
    SiteCoordinate,
    SiteProvenance,
)
from .params import ParameterSet, SpeciesParams, default_parameters, load_parameters
from .regulatory import (
    JURISDICTIONS,
    RegulatoryRecord,
    RegulatoryRegistry,
    default_registry,
    load_regulatory_records,
)
from .scenarios import SCALES, Scenario, compare, evaluate
from .suitability import Suitability, Verdict, assess

__version__ = "0.3.0"

__all__ = [
    "DEFAULT_FORCING",
    "JURISDICTIONS",
    "PLACEHOLDER_SITES",
    "REGIONS",
    "SCALES",
    "BowtieUnavailable",
    "Calibration",
    "EutropyUnavailable",
    "ForcingSource",
    "ParameterSet",
    "Quantity",
    "RegulatoryRecord",
    "RegulatoryRegistry",
    "Scenario",
    "SiteAssessment",
    "SiteConditions",
    "SiteCoordinate",
    "SiteProvenance",
    "SITE_COORDINATES",
    "SiteContext",
    "SpeciesOption",
    "SpeciesParams",
    "Suitability",
    "Tier",
    "Verdict",
    "assess",
    "assess_site",
    "compare",
    "default_parameters",
    "default_registry",
    "evaluate",
    "load_parameters",
    "load_regulatory_records",
    "removal_framing",
]
