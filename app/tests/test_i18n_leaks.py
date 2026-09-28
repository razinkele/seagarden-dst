"""Spec I§8 test 6 (the pseudo-locale leak test) and test 8 (the gate).

Every text node of every render under language `xx` must be a `⟦key⟧` marker, a
number, a unit, a Latin name, an identifier or an allowlisted proper noun. Anything
else is a sentence that bypassed the seam - whether or not it ever entered a
catalogue, which is why this is stronger than checking the English values are absent.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime
from html.parser import HTMLParser

import pytest

from app.i18n import LANGUAGE_NAMES, Translator, enabled_languages
from app.modules._widgets import calibration_legend, data_source_banner, headline_for
from app.modules.catalogue import method_table, species_table
from app.modules.report import render_report
from app.modules.results import render_excluded, render_pressure, render_ranking, run_assessment
from app.modules.site import _legend, render_conditions, render_position_note, site_markers
from app.modules.user_mode import mode_question_tag, user_mode_ui
from app.shell import about_modal, feedback_modal, help_modal
from app.tests.test_app_smoke import _FakeState
from seagarden_dst import PLACEHOLDER_SITES, REGIONS, SiteContext, default_parameters
from seagarden_dst.bowtie_adapter import TOP_EVENT_STATES
from seagarden_dst.forcing import DEFAULT_FORCING, ForcingChoice

XX = Translator.pseudo()
PARAMS = default_parameters()

MARKER = re.compile(r"⟦[^⟧]*⟧")
NUMBER = re.compile(r"[-+]?\d[\d.,]*(?:e[-+]?\d+)?%?")
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
VERSION = re.compile(r"v\d[\w.]*|v\*")
URL = re.compile(r"https?://\S+|\S+@\S+\.\w+|mailto:\S+")
#: Shared with `_leaks`' token lookup below, so an allowlist entry and the token found
#: in rendered text are normalised the same way. Without this, an entry that itself
#: ends in one of these characters (an abbreviation like "spp.") never matches the
#: token `_leaks` looks up, which has already had the same trailing punctuation
#: stripped - see `_RAW_ALLOWED_TOKENS`'s Latin names, word by word, below.
_STRIP = "().,;:[]*|"
_RAW_ALLOWED_TOKENS = {
    # units and symbols (I§7)
    "psu", "m", "ha", "kg", "t", "DW", "FW", "N", "P", "C", "CO2", "km", "°C", "µmol/L",
    "umol/L", "µmol", "photons/m²/s", "m²", "m2", "/", "-", "–", "—", "·", "=", "(", ")", "[", "]",
    "|", ":", ";", ",", ".", "×", "x", "%", "&", "✓", "*",
    # tiers, verdict identifiers (CSS class text never shows; the value does in the badge)
    # - "C" is already listed above as the carbon unit symbol
    "A", "B", "D",
    # brand and programme proper nouns
    "Sea", "Garden", "SeaGarden", "DST", "Interreg", "South", "Baltic", "European", "Union",
    "KU", "MRI", "OLAMUR", "EUTROPY", "MARBEFES", "WP2", "WP3", "A2.3", "D2.2",
    "STHB.02.02-IP.01-0006/25",
    # bow-tie states are engine data
    *TOP_EVENT_STATES,
    # language endonyms in the menu
    *LANGUAGE_NAMES.values(),
    # identifiers that are legitimately shown raw
    *REGIONS, *PARAMS.species, *PARAMS.methods,
    # Latin names, word by word - an abbreviation like "Mytilus spp." splits into
    # "Mytilus" and "spp.", the latter with its trailing dot; normalised below the
    # same way a found token is, or "spp." (kept) would never match "spp" (stripped).
    *{w for s in PARAMS.species.values() for w in s.scientific_name.split()},
    # the About modal's {repo_name} - the bare repository host+path, no scheme, so the
    # URL regex above (which requires "https?://") does not consume it
    "github.com/razinkele/seagarden-dst",
    # site labels the tests themselves pass in (DATA, not catalogue prose)
    "Melnrage", "Off-grid",
    # pre-existing defect, pinned byte-for-byte by tests/golden/reports/case-unassessable.txt:
    # render_report prints "Sub-region:  None" for a site with no conditions and thus no
    # region. Package I-a must keep English identical, so this stays allowlisted until a
    # deliberate golden update fixes it.
    "None",
}
ALLOWED_TOKENS = {token.strip(_STRIP) for token in _RAW_ALLOWED_TOKENS}


class _Text(HTMLParser):
    """Collects text nodes plus the attributes a user can read."""

    def __init__(self):
        super().__init__()
        self.chunks: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("style", "script"):
            self._skip += 1
        for name, value in attrs:
            if name in ("title", "alt", "placeholder", "aria-label") and value:
                self.chunks.append(value)

    def handle_endtag(self, tag):
        if tag in ("style", "script"):
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self.chunks.append(data)


#: The one permitted category of English under `xx`: text the FRAMEWORK emits, not us.
#: Each entry names its origin. Verified against the actual render, not guessed: our
#: `ui.modal()` calls always carry their own footer button (`tr("app.shell.close")`),
#: so shiny never gets a chance to emit its own default close control here, and no
#: "Close" string appears anywhere in the rendered surfaces this test covers.
FRAMEWORK_STRINGS = {
    "Toggle navigation",  # Bootstrap navbar toggler aria-label (app_shell's navbar)
    "Toggle sidebar",     # bslib collapse-toggle title (the shell sidebar and each
                           # panel's own ui.layout_sidebar in site_ui/catalogue_ui)
}
#: The draft banner is bilingual BY DESIGN (I§6): the English sentence beside the
#: translated one is required, so it is stripped before the leak scan, exactly once.
ENGLISH_DRAFT_BANNER = Translator.for_language("en")("app.shell.draft_banner")


def _leaks(text: str) -> list[str]:
    out = []
    for chunk in text.split("\n"):
        stripped = chunk.replace(ENGLISH_DRAFT_BANNER, " ")
        if stripped.strip() in FRAMEWORK_STRINGS:
            continue
        for pattern in (MARKER, URL, DATE, VERSION, NUMBER):
            stripped = pattern.sub(" ", stripped)
        for token in stripped.split():
            if token.strip(_STRIP) in ALLOWED_TOKENS or not re.search(r"[A-Za-z]", token):
                continue
            out.append(f"{token!r} in {chunk.strip()[:80]!r}")
    return out


def _html_text(tag) -> str:
    parser = _Text()
    parser.feed(str(tag))
    return "\n".join(c for c in parser.chunks if c.strip())


def _text_values(obj: object) -> list[str]:
    """Every message's own rendered `"text"` in a JSON export, collected recursively
    (I§8.6) - never a value that merely sits inside a `"params"` dict, which is DATA
    (I§5.1), not prose read by the seam. `Message.literal(text)` stores its payload as
    `params={"text": text}` - the RAW English source, not the rendered marker - so a
    walk that does not exempt `"params"` would flag that raw text as a leak even
    though the very same message's own `"text"` field (checked here) is correctly
    translated or marked. Structural keys, identifiers and stable-English fields such
    as `species_name`/`method_name` are never named `"text"`, so they are never
    visited in the first place.
    """
    if isinstance(obj, dict):
        out = [v for k, v in obj.items() if k == "text" and isinstance(v, str)]
        for k, v in obj.items():
            if k not in ("text", "params"):
                out.extend(_text_values(v))
        return out
    if isinstance(obj, list):
        return [v for item in obj for v in _text_values(item)]
    return []


def _artifact_choice() -> ForcingChoice:
    # An artifact-kind choice with no reason: `reason` is an operator diagnostic that
    # stays English by design (I§7), so it is exercised separately below.
    return ForcingChoice(
        source=DEFAULT_FORCING, kind="artifact", reason="", year=2025,
        built_on=datetime(2026, 9, 22, tzinfo=UTC), directory=None,
    )


def _assessment(region: str):
    state = _FakeState(SiteContext.from_region(region, label="Melnrage"))
    state.forcing.set(_artifact_choice())
    state.bowtie_inference.set({"Low": 0.2, "Moderate": 0.3, "High": 0.5})
    # A EUTROPY scenario with NO label and no box, so the adapter's note takes its
    # unlabelled-run path - the one word in `adapters.eutropy.*` the core authors itself
    # rather than copying from the scenario. The caveat reaches the ranking, the report
    # and the JSON below, so every `adapters.eutropy.*` key renders under `xx`.
    state.eutropy_scenario.set({"din_umol_l": 30.0, "dip_umol_l": 1.9})
    run_assessment(state)
    return state.assessment.get()


def test_6_the_whole_page_has_no_untranslated_text():
    from app.app import build_ui

    leaks = _leaks(_html_text(build_ui("xx")))
    assert not leaks, "\n".join(leaks)


@pytest.mark.parametrize("region", sorted(PLACEHOLDER_SITES))
def test_6_every_render_has_no_untranslated_text(region):
    # Local import: `app.app` instantiates `App(app_ui, server)` at module scope, so
    # importing it at this file's top level would pay that cost for every test here,
    # not only this one - the same reason `test_6_the_whole_page_has_no_untranslated_text`
    # below imports `build_ui` locally instead.
    from app.app import scale_sentence

    assessment = _assessment(region)
    rendered = [
        _html_text(render_ranking(assessment, XX)),
        _html_text(render_excluded(assessment, XX)),
        _html_text(render_pressure(assessment, XX)),
        _html_text(render_conditions(region, XX)),
        _html_text(render_position_note(region, XX)),
        _html_text(calibration_legend(XX)),
        _html_text(mode_question_tag("farm", XX)),
        # The user-mode selector: served into the sidebar through `ui.output_ui`
        # (`user_mode_slot`), so the whole-page scan never sees its label or choices.
        _html_text(user_mode_ui("um", XX)),
        headline_for(assessment, XX)[1],
        data_source_banner(_artifact_choice(), assessment.context, XX),
        render_report(assessment, _artifact_choice(), today=date(2026, 9, 28), tr=XX),
        # The catalogue panel's two tables: `ui.output_ui`-served, so the whole-page
        # scan below never sees them (I§5.2 names the species table's yes/no and the
        # month words as exactly what this test exists to find).
        _html_text(species_table(XX)),
        _html_text(method_table(XX)),
        # The site map's legend: part of the Site panel, but only reachable on the
        # page when `shiny_deckgl` is installed, which CI lacks - rendered directly.
        _html_text(_legend(XX)),
        # The sidebar's "site ready" sentence, never otherwise pseudo-rendered.
        scale_sentence(label="Melnrage", count=3, scale_key="community_farm_0_1_ha", tr=XX),
    ]
    for modal in (about_modal, help_modal, feedback_modal):
        rendered.append(_html_text(modal(XX)))
    skip = ("position", "colour", "region", "provenance")
    for marker in site_markers(XX):
        rendered.append(" ".join(str(v) for k, v in marker.items() if k not in skip))
    # The JSON download (report.py, `to_dict(render=tr.render)`, spec I§8.6): only the
    # values under "text" keys are prose a user reads; see `_text_values`.
    payload = json.loads(json.dumps(assessment.to_dict(render=XX.render), default=str))
    rendered.extend(_text_values(payload))
    # The scenario really took the unlabelled-run path and reached the renders; a
    # scan that never sees the EUTROPY note would pass while proving nothing about it.
    assert any("⟦adapters.eutropy.unlabelled_run⟧" in text for text in rendered)
    leaks = [leak for text in rendered for leak in _leaks(text)]
    assert not leaks, "\n".join(leaks)


def test_6_the_empty_and_unassessable_states_have_no_untranslated_text():
    from seagarden_dst.api import assess_site
    from seagarden_dst.forcing import Aggregation, Coverage, SiteReading

    blocked = SiteReading(
        conditions=None, coverage=Coverage.CELL_INVALID, year=2024,
        aggregation=Aggregation.CONTAINING_CELL, nearest_valid_km=1.1, from_artifact=True,
    )
    unassessable = assess_site(SiteContext.from_reading(blocked, label="Off-grid"))
    texts = [
        _html_text(render_ranking(None, XX)), _html_text(render_excluded(None, XX)),
        _html_text(render_pressure(None, XX)),
        render_report(None, today=date(2026, 9, 28), tr=XX),
        _html_text(render_ranking(unassessable, XX)),
        headline_for(unassessable, XX)[1],
        render_report(unassessable, _artifact_choice(), today=date(2026, 9, 28), tr=XX),
    ]
    leaks = [leak for text in texts for leak in _leaks(text)]
    assert not leaks, "\n".join(leaks)


def test_the_placeholder_reason_is_the_only_english_in_the_placeholder_banner():
    from seagarden_dst.forcing import placeholder_choice

    banner = data_source_banner(placeholder_choice("REASON-TOKEN"), None, XX)
    # I§7: `reason` is an operator diagnostic and stays English inside the keyed
    # sentence; REASON-TOKEN is the only English word here, so it is the only thing
    # standing outside the marker.
    assert banner == "⟦app.banner.placeholder⟧ REASON-TOKEN", banner


def test_8_a_draft_language_is_hidden_unless_the_deployment_shows_drafts():
    def status(language):
        return {"de": "machine-draft"}.get(language)

    from app.i18n import language_for

    hidden = enabled_languages(env={}, status=status)
    assert "de" not in hidden
    assert language_for("?lang=de", "de", hidden) == "en"
    shown = enabled_languages(env={"SEAGARDEN_SHOW_DRAFT_LANGUAGES": "1"}, status=status)
    assert "de" in shown and language_for("?lang=de", None, shown) == "de"
