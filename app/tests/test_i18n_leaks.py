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

from app.i18n import LANGUAGE_NAMES, LANGUAGES, Translator, enabled_languages
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
#: Pruned to what `test_every_allowlist_entry_is_needed` (below) actually matches, not
#: aspirational (inherited item 7): measured with `shiny_deckgl` both hidden and
#: present, 38 raw entries (including the whole `*PARAMS.methods` spread - a method's
#: raw key never appears, only `tr.method_name(...)`'s translated text does) never
#: matched either way and are gone; none matched only with the map. A future entry that
#: test names as unused is dead weight, not insurance - remove it, don't keep it "just
#: in case".
_RAW_ALLOWED_TOKENS = {
    # units and symbols (I§7)
    "psu", "m", "kg", "DW", "FW", "N", "P", "C", "°C", "µmol/L",
    "µmol", "photons/m²/s", "m²", "/", "(", ")", "[", "]",
    "|", ":", ";", ",", ".", "*",
    # tiers, verdict identifiers (CSS class text never shows; the value does in the badge)
    # - "C" is already listed above as the carbon unit symbol
    "A", "B", "D",
    # brand and programme proper nouns
    "Sea", "Garden", "DST",
    # bow-tie states are engine data
    *TOP_EVENT_STATES,
    # language endonyms in the menu
    *LANGUAGE_NAMES.values(),
    # identifiers that are legitimately shown raw
    *REGIONS, *PARAMS.species,
    # Latin names, word by word - an abbreviation like "Mytilus spp." splits into
    # "Mytilus" and "spp.", the latter with its trailing dot; normalised below the
    # same way a found token is, or "spp." (kept) would never match "spp" (stripped).
    *{w for s in PARAMS.species.values() for w in s.scientific_name.split()},
    # the About modal's {repo_name} - the bare repository host+path, no scheme, so the
    # URL regex above (which requires "https?://") does not consume it
    "github.com/razinkele/seagarden-dst",
    # site labels the tests themselves pass in (DATA, not catalogue prose)
    "Melnrage", "Off-grid",
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
#: translated one is required. Unlike every other allowance here, it is not stripped
#: per chunk any more (that hid it from every render, not only the one place it
#: belongs). The rule, explicit rather than relying on none of its words happening to
#: be allowlisted (I-b review): the whole page (`_whole_page`) and each draft report
#: (`_report`, Task 2) must carry it exactly once - checked there, then removed before
#: the rest of that render is scanned - and `_leaks` itself asserts, for every render it
#: is handed, that the banner is not present: trivially true for the page/report texts
#: it has already been stripped from, and a real check for everything else.
ENGLISH_DRAFT_BANNER = Translator.for_language("en")("app.shell.draft_banner")

#: Pre-existing defect, pinned byte-for-byte by tests/golden/reports/case-unassessable.txt
#: (inherited item 12, deferred to a later package): an unassessable site has no region,
#: and `render_report` formats `None` into the sentence anyway. Blanked out as the one
#: exact pseudo-rendered line it produces, not as a bare "None" anywhere, so a real leak
#: that happens to say "None" is still caught.
_SUBREGION_NONE_LINE = "⟦app.report.subregion⟧ None"

#: Which normalised `ALLOWED_TOKENS` entries `_leaks` has actually matched, across
#: however many renders it has scanned since the last `.clear()`. The only reader is
#: `test_every_allowlist_entry_is_needed`, which clears this first so its own scan is
#: what it measures.
_MATCHED_TOKENS: set[str] = set()


def _leaks(text: str) -> list[str]:
    out = []
    # Explicit, not merely a side effect of no banner word being allowlisted (I-b
    # review): the whole page and each draft report have already had their one
    # required occurrence stripped by `_whole_page`/`_report` before reaching here, so
    # this is trivially satisfied for them; every other render must never contain the
    # banner sentence at all.
    if ENGLISH_DRAFT_BANNER in text:
        out.append(f"the English draft banner leaked outside the page/report: {text[:80]!r}")
    for chunk in text.split("\n"):
        body = chunk.strip()
        if body == _SUBREGION_NONE_LINE or body in FRAMEWORK_STRINGS:
            continue
        stripped = chunk
        for pattern in (MARKER, URL, DATE, VERSION, NUMBER):
            stripped = pattern.sub(" ", stripped)
        for token in stripped.split():
            normalised = token.strip(_STRIP)
            if normalised in ALLOWED_TOKENS:
                _MATCHED_TOKENS.add(normalised)
                continue
            if not re.search(r"[A-Za-z]", token):
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


def _whole_page() -> str:
    """The whole page's text, in `xx`. `enabled=LANGUAGES` so the language menu is
    exercised for all six endonyms, not only whichever the deployment happens to have
    reviewed today (with no override, `build_ui`'s own default `enabled_languages()`
    is English alone, and the other five would never be reached here).

    The bilingual draft banner (I§6) is required to appear exactly once - checked here -
    and removed after checking, so `_leaks` scans the rest of the page like any other
    render. A draft report's own banner is the same rule, applied by `_report` below;
    no other render may contain the banner text at all (see `ENGLISH_DRAFT_BANNER`
    above, and `_leaks`, which checks that for every render).
    """
    from app.app import build_ui

    text = _html_text(build_ui("xx", enabled=LANGUAGES))
    assert text.count(ENGLISH_DRAFT_BANNER) == 1, (
        "the bilingual draft banner (I§6) must appear exactly once on the page"
    )
    return text.replace(ENGLISH_DRAFT_BANNER, " ", 1)


def _report(text: str) -> str:
    """A `render_report` result in the draft pseudo-locale (Task 2, I§6): the bilingual
    banner is required to appear exactly once, as its first line - checked here - and
    removed after checking, the same way `_whole_page` handles the page's own banner.
    Every render this test suite scans that is not the whole page or a report goes
    straight to `_leaks`, which asserts the banner is not there at all."""
    assert text.count(ENGLISH_DRAFT_BANNER) == 1, (
        "a draft report must carry the English draft banner exactly once"
    )
    return text.replace(ENGLISH_DRAFT_BANNER, " ", 1)


def _region_renders(region: str) -> list[str]:
    """Every render `test_6_every_render_has_no_untranslated_text` scans for one region."""
    # Local import: `app.app` instantiates `App(app_ui, server)` at module scope, so
    # importing it at this file's top level would pay that cost for every test here,
    # not only this one - the same reason `_whole_page` above imports `build_ui` locally.
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
        _report(render_report(assessment, _artifact_choice(), today=date(2026, 9, 28), tr=XX)),
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
    return rendered


def _empty_and_unassessable_renders() -> list[str]:
    """Every render `test_6_the_empty_and_unassessable_states_have_no_untranslated_text`
    scans: no assessment at all, and a site whose coverage blocks one."""
    from seagarden_dst.api import assess_site
    from seagarden_dst.forcing import Aggregation, Coverage, SiteReading

    blocked = SiteReading(
        conditions=None, coverage=Coverage.CELL_INVALID, year=2024,
        aggregation=Aggregation.CONTAINING_CELL, nearest_valid_km=1.1, from_artifact=True,
    )
    unassessable = assess_site(SiteContext.from_reading(blocked, label="Off-grid"))
    return [
        _html_text(render_ranking(None, XX)), _html_text(render_excluded(None, XX)),
        _html_text(render_pressure(None, XX)),
        _report(render_report(None, today=date(2026, 9, 28), tr=XX)),
        _html_text(render_ranking(unassessable, XX)),
        headline_for(unassessable, XX)[1],
        _report(render_report(unassessable, _artifact_choice(), today=date(2026, 9, 28), tr=XX)),
    ]


def _all_renders() -> list[str]:
    """Every render the leak tests below perform, in one list: the whole page, every
    per-region render, and the empty and unassessable states - built from the same
    helpers those tests call, so `test_every_allowlist_entry_is_needed` sees exactly
    what they see."""
    out = [_whole_page()]
    for region in sorted(PLACEHOLDER_SITES):
        out.extend(_region_renders(region))
    out.extend(_empty_and_unassessable_renders())
    return out


def test_6_the_whole_page_has_no_untranslated_text():
    leaks = _leaks(_whole_page())
    assert not leaks, "\n".join(leaks)


@pytest.mark.parametrize("region", sorted(PLACEHOLDER_SITES))
def test_6_every_render_has_no_untranslated_text(region):
    rendered = _region_renders(region)
    # The scenario really took the unlabelled-run path and reached the renders; a
    # scan that never sees the EUTROPY note would pass while proving nothing about it.
    assert any("⟦adapters.eutropy.unlabelled_run⟧" in text for text in rendered)
    leaks = [leak for text in rendered for leak in _leaks(text)]
    assert not leaks, "\n".join(leaks)


def test_6_the_empty_and_unassessable_states_have_no_untranslated_text():
    leaks = [leak for text in _empty_and_unassessable_renders() for leak in _leaks(text)]
    assert not leaks, "\n".join(leaks)


def test_every_allowlist_entry_is_needed(monkeypatch):
    """Measured with `shiny_deckgl` hidden, the same install CI has (`app/tests/
    test_app_smoke.py::test_the_site_panel_renders_without_shiny_deckgl`): an allowlist
    entry nothing ever matches is dead weight that hides a real leak behind a false
    sense of coverage (inherited item 7)."""
    import sys

    monkeypatch.setitem(sys.modules, "shiny_deckgl", None)
    _MATCHED_TOKENS.clear()
    for text in _all_renders():
        _leaks(text)
    dead = ALLOWED_TOKENS - _MATCHED_TOKENS
    assert not dead, f"unused allowlist entries: {sorted(dead)}"


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


def test_8_a_draft_language_renders_under_the_switch():
    """The first rendered page in a real second language: shown only with the switch,
    translated, and bannered in both languages."""
    import html as htmllib

    from app.app import build_ui
    from app.i18n import enabled_languages, english, language_for

    shown = enabled_languages(env={"SEAGARDEN_SHOW_DRAFT_LANGUAGES": "1"})
    assert "de" in shown and language_for("?lang=de", None, shown) == "de"
    de = Translator.for_language("de")
    assert de.is_draft
    page = htmllib.unescape(str(build_ui("de", enabled=shown)))
    assert 'lang="de"' in page
    assert de("app.shell.assess") != english()("app.shell.assess")
    assert de("app.shell.assess") in page
    assert de("app.shell.draft_banner") in page
    assert english()("app.shell.draft_banner") in page


def test_8_a_draft_language_report_opens_with_the_bilingual_draft_line():
    """The same for the report a user downloads: a placeholder site rendered in German
    starts with the draft line in both languages and ends on the translated footer."""
    from app.i18n import english
    from seagarden_dst.api import assess_site

    de = Translator.for_language("de")
    assessment = assess_site(SiteContext.from_region("DE-coastal", label="Rostock"))
    text = render_report(assessment, today=date(2026, 9, 28), tr=de)
    banner = f"{de('app.shell.draft_banner')} {english()('app.shell.draft_banner')}"
    assert text.startswith(banner + "\n")
    assert de("app.report.source.placeholder_bare") in text  # a placeholder site
    assert de("app.report.footer") != english()("app.report.footer")
    assert de("app.report.footer") in text
    assert english()("app.report.footer") not in text
