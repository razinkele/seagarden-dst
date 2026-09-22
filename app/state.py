"""Shared per-session reactive state."""

from __future__ import annotations

from shiny import reactive

_DEFAULTS = {
    "user_mode": "farm",          # which of the four doors - see modules/user_mode.py
    "context": None,              # SiteContext | None
    "site_label": "",
    "selected_species": [],
    "method_overrides": {},       # species_key -> method_key
    "scale": "community farm (0.1 ha)",
    "assessment": None,           # SiteAssessment | None
    "eutropy_scenario": None,     # dict | None, optional nutrient forcing
    "bowtie_inference": None,     # dict | None, optional pressure context
    "forcing": None,              # ForcingChoice | None; set once per session by server(),
                                   # never reset
}


class AppState:
    """One instance per session.

    `_DEFAULTS` is the single source of truth so `__init__` and `defaults()` cannot
    drift apart - the same arrangement as the NiD4OCEAN DST.
    """

    def __init__(self) -> None:
        self.user_mode: reactive.Value[str] = reactive.Value(_DEFAULTS["user_mode"])
        self.context: reactive.Value = reactive.Value(_DEFAULTS["context"])
        self.site_label: reactive.Value[str] = reactive.Value(_DEFAULTS["site_label"])
        self.selected_species: reactive.Value = reactive.Value(
            list(_DEFAULTS["selected_species"])
        )
        self.method_overrides: reactive.Value = reactive.Value(
            dict(_DEFAULTS["method_overrides"])
        )
        self.scale: reactive.Value[str] = reactive.Value(_DEFAULTS["scale"])
        self.assessment: reactive.Value = reactive.Value(_DEFAULTS["assessment"])
        self.eutropy_scenario: reactive.Value = reactive.Value(
            _DEFAULTS["eutropy_scenario"]
        )
        self.bowtie_inference: reactive.Value = reactive.Value(
            _DEFAULTS["bowtie_inference"]
        )
        self.forcing: reactive.Value = reactive.Value(_DEFAULTS["forcing"])

    @staticmethod
    def defaults() -> dict:
        return dict(_DEFAULTS)
