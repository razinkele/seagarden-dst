"""The app-side Translator and the language chooser (spec I§5.2-I§5.4, I§6)."""

from __future__ import annotations

from app.i18n import (
    LANGUAGE_NAMES,
    Translator,
    catalogue_status,
    enabled_languages,
    language_for,
)
from seagarden_dst import Tier, default_parameters
from seagarden_dst.calibration import Calibration, Quantity
from seagarden_dst.i18n import LANGUAGES, Message, msg


def test_app_keys_and_core_keys_render_through_one_translator():
    tr = Translator.for_language("en")
    assert tr("app.shell.assess") == "Assess"
    assert tr.render(msg("calibration.tier.C.label")) == "Literature prior"
    assert tr.render(Message.literal("Raft")) == "Raft"


def test_species_and_method_names_fall_back_to_the_yaml_english():
    tr = Translator.for_language("en")
    params = default_parameters()
    assert tr.species_name("ulva") == params.species["ulva"].common_name
    assert tr.method_name("raft") == "Raft"
    assert tr.method_field("raft", "anchoring_unit") == "multi-point mooring"
    assert tr.group_label("macroalga") == "macroalga"
    assert tr.confidence_label("low") == "low"


def test_quantity_text_matches_the_core_str():
    tr = Translator.for_language("en")
    c = Calibration(tier=Tier.C, region="r", source="S")
    q = Quantity(3.0, "kg DW", c, low=1.0, high=9.0)
    assert tr.quantity(q) == str(q) == "1-9 kg DW [C]"
    d = Calibration(tier=Tier.D, region="r", source="S", note="no")
    assert tr.quantity(Quantity(0.0, "kg DW", d)) == "not applicable - no"


def test_a_sidecar_translates_yaml_text_and_literals_carrying_it(tmp_path):
    (tmp_path / "params").mkdir()
    (tmp_path / "params" / "xx.yaml").write_text(
        "language: xx\nstatus: machine-draft\ntranslated_by: t\nmessages:\n"
        "  params.methods.raft.name: 'FLOSS'\n"
        "  params.species.ulva.common_name: 'MEERSALAT'\n"
        "  params.group.macroalga: 'MAKROALGE'\n",
        encoding="utf-8",
    )
    tr = Translator.load(
        "xx", core_root=None, app_root=None, params_root=tmp_path / "params"
    )
    assert tr.method_name("raft") == "FLOSS"
    assert tr.species_name("ulva") == "MEERSALAT"
    assert tr.group_label("macroalga") == "MAKROALGE"
    # A literal carrying the English YAML text resolves through the text index.
    inner = msg("suitability.physical.unsupported_group", method=Message.literal("Raft"), group="x")
    assert tr.render(inner) == "FLOSS does not support x cultivation."
    assert tr.render(Message.literal("  Raft ")) == "FLOSS"  # whitespace-normalised


def test_pseudo_translator_marks_every_value():
    xx = Translator.pseudo()
    assert xx.language == "xx"
    assert xx("app.shell.assess") == "⟦app.shell.assess⟧"
    assert xx.render(msg("calibration.tier.C.label")) == "⟦calibration.tier.C.label⟧"
    assert xx.species_name("ulva") == "⟦params.species.ulva.common_name⟧"
    assert xx.render(Message.literal("Raft")) == "⟦params.methods.raft.name⟧"


def test_language_for_prefers_query_then_header_then_english():
    enabled = ("en", "de", "pl")
    assert language_for("?lang=de", None, enabled) == "de"
    assert language_for("?x=1&lang=pl&y=2", "de", enabled) == "pl"
    assert language_for("?lang=DE", None, enabled) == "de"
    assert language_for("", "pl-PL,pl;q=0.9,en;q=0.8", enabled) == "pl"
    assert language_for("", "sv-SE,sv;q=0.9,de;q=0.5", enabled) == "de"
    assert language_for("?lang=sv", "sv", enabled) == "en"  # exists, not enabled
    assert language_for("?lang=zz", "zz", enabled) == "en"
    assert language_for("?lang=", None, enabled) == "en"
    assert language_for("garbage", "garbage;;q=", enabled) == "en"
    assert language_for("", None, ("en",)) == "en"


def test_enabled_languages_is_english_plus_reviewed_unless_drafts_are_shown():
    def status(language: str) -> str | None:
        return {"de": "reviewed", "pl": "machine-draft", "da": None}.get(language)

    assert enabled_languages(env={}, status=status) == ("en", "de")
    assert enabled_languages(env={"SEAGARDEN_SHOW_DRAFT_LANGUAGES": "1"}, status=status) == (
        "en", "de", "pl",
    )
    assert enabled_languages(env={"SEAGARDEN_LANGUAGES": "en,pl,de"}, status=status) == (
        "en", "de",
    )
    assert enabled_languages(
        env={"SEAGARDEN_LANGUAGES": "pl", "SEAGARDEN_SHOW_DRAFT_LANGUAGES": "1"}, status=status
    ) == ("en", "pl")


def test_in_i_a_only_english_is_enabled_on_disk():
    """No non-English catalogue ships in I-a; package I-b adds them."""
    assert enabled_languages(env={}) == ("en",)
    assert catalogue_status("en") == "reference"
    assert catalogue_status("de") is None


def test_language_names_cover_the_six_languages_as_endonyms():
    assert set(LANGUAGE_NAMES) == set(LANGUAGES)
    assert LANGUAGE_NAMES["lt"] == "Lietuvių" and LANGUAGE_NAMES["en"] == "English"


# --- Task 6: the shell and the entry point build per request, in a language -----------


def test_the_page_builds_in_english_and_in_the_pseudo_locale():
    from app.app import build_ui

    en = str(build_ui("en"))
    assert 'lang="en"' in en and ">Assess<" in en
    xx = str(build_ui("xx"))
    assert 'lang="xx"' in xx and "⟦app.shell.assess⟧" in xx and ">Assess<" not in xx


def test_app_ui_takes_a_request_and_reads_lang_from_it():
    from starlette.requests import Request

    from app.app import app_ui

    def request(query: bytes, accept: bytes | None) -> Request:
        headers = [(b"accept-language", accept)] if accept else []
        return Request({
            "type": "http", "method": "GET", "scheme": "http", "path": "/",
            "query_string": query, "headers": headers, "server": ("test", 80),
        })

    assert 'lang="en"' in str(app_ui(request(b"lang=de", b"de")))  # de not enabled in I-a
    assert 'lang="en"' in str(app_ui(request(b"", None)))


def test_the_language_menu_lists_enabled_languages_as_relative_links():
    from app.shell import language_menu

    html = str(language_menu(Translator.for_language("en"), ("en", "de")))
    assert 'href="?lang=de"' in html and "Deutsch" in html
    assert 'href="?lang=en"' not in html, "the current language is marked, not linked"
    assert "English" in html


def test_a_draft_language_shows_the_bilingual_banner_and_english_does_not():
    from app.shell import draft_banner

    assert draft_banner(Translator.for_language("en")) is None
    banner = str(draft_banner(Translator.pseudo()))
    assert "⟦app.shell.draft_banner⟧" in banner
    assert "Machine translation, not yet reviewed." in banner


def test_state_carries_a_translator_slot_unset_until_the_session_sets_it():
    from app.state import AppState

    assert AppState.defaults()["translator"] is None


# --- Task 7: the five panels render through `tr`, as pure functions -------------------


def _assessed_state(region: str = "LT-coastal"):
    from app.modules.results import run_assessment
    from app.tests.test_app_smoke import _FakeState
    from seagarden_dst import SiteContext

    state = _FakeState(SiteContext.from_region(region, label="Melnrage"))
    run_assessment(state)
    return state


def test_every_panel_factory_takes_a_translator():
    from app.modules.catalogue import catalogue_ui
    from app.modules.report import report_ui
    from app.modules.results import results_ui
    from app.modules.site import site_ui
    from app.modules.user_mode import user_mode_ui

    xx = Translator.pseudo()
    for factory, id_ in (
        (site_ui, "site"), (catalogue_ui, "cat"), (results_ui, "res"), (report_ui, "rep"),
        (user_mode_ui, "um"),
    ):
        html = str(factory(id_, xx))
        assert "⟦app." in html, f"{factory.__name__} rendered nothing from the catalogue"


def test_the_pure_renderers_speak_the_translators_language():
    from datetime import date

    from app.modules._widgets import data_source_banner, headline_for
    from app.modules.report import render_report
    from app.modules.results import render_excluded, render_pressure, render_ranking
    from app.modules.site import render_conditions, render_position_note

    state = _assessed_state()
    xx = Translator.pseudo()
    assessment = state.assessment.get()
    assert "⟦app.headline.best⟧" == headline_for(assessment, xx)[1]
    assert "⟦app.banner.artifact⟧" == data_source_banner(state.forcing.get(), None, xx)
    for tag in (
        render_ranking(assessment, xx), render_pressure(assessment, xx),
        render_conditions("LT-coastal", xx), render_position_note("LT-coastal", xx),
    ):
        assert "⟦app." in str(tag)
    # `render_excluded` shows the raw species key, not a translated name (results.py
    # keeps the exclusion identifier literal by design), and here the only excluded
    # entry's reason is a core-level literal Message carrying params sidecar text - so
    # its pseudo-marked key is `params.*`, not `app.*`. Still routed through `tr`.
    assert "⟦params." in str(render_excluded(assessment, xx))
    text = render_report(assessment, state.forcing.get(), today=date(2026, 9, 28), tr=xx)
    assert text.splitlines()[0] == "⟦app.report.heading⟧"
    # Pseudo mode masks every app-key value to exactly `⟦key⟧` with no interpolation
    # (Translator.pseudo's contract: "every value is ⟦key⟧" - see test above), so a
    # species name or tier label passed as a PARAM into `app.report.option` /
    # `app.report.calibration` is computed (via tr.species_name / tr.render) and then
    # discarded by that outer masked template, same as `app.headline.best`'s params
    # above. What pseudo mode CAN show is that both keyed lines executed and appear.
    assert "⟦app.report.option⟧" in text and "⟦app.report.calibration⟧" in text


def test_english_renderers_are_unchanged_from_before_the_seam():
    """The pure functions in English say exactly what the closures said."""
    from app.modules._widgets import data_source_banner, headline_for, window_label
    from seagarden_dst.forcing import placeholder_choice

    en = Translator.for_language("en")
    state = _assessed_state()
    assert headline_for(state.assessment.get(), en)[1].startswith("Best option: ")
    banner = data_source_banner(placeholder_choice("no artifact at data/forcing"), None, en)
    assert banner.startswith("Data source: placeholder conditions — plausible")
    assert window_label((10, 6), en) == "Oct–Jun (over winter)"
    assert window_label((4, 10), en) == "Apr–Oct"
