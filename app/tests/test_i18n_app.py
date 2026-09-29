"""The app-side Translator and the language chooser (spec I§5.2-I§5.4, I§6)."""

from __future__ import annotations

import pytest

from app.i18n import (
    LANGUAGE_NAMES,
    Translator,
    catalogue_status,
    enabled_languages,
    english,
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


def test_a_malformed_app_value_is_a_value_error_naming_key_and_language(tmp_path):
    (tmp_path / "xx.yaml").write_text(
        "language: xx\nstatus: machine-draft\ntranslated_by: t\nmessages:\n"
        "  app.shell.assess: 'Bewerten {'\n",
        encoding="utf-8",
    )
    tr = Translator.load("xx", core_root=None, app_root=tmp_path, params_root=None)
    with pytest.raises(ValueError, match=r"'app\.shell\.assess' in 'xx' is not a valid template"):
        tr("app.shell.assess")
    # A placeholder the caller does not supply stays a KeyError, as before.
    with pytest.raises(KeyError, match=r"'app\.report\.option' in 'en'"):
        Translator.for_language("en")("app.report.option", species="S")


def test_pseudo_translator_marks_every_value():
    xx = Translator.pseudo()
    assert xx.language == "xx"
    assert xx("app.shell.assess") == "⟦app.shell.assess⟧"
    assert xx.render(msg("calibration.tier.C.label")) == "⟦calibration.tier.C.label⟧"
    assert xx.species_name("ulva") == "⟦params.species.ulva.common_name⟧"
    assert xx.render(Message.literal("Raft")) == "⟦params.methods.raft.name⟧"
    # A key whose English template carries placeholders keeps them: `app.report.option`
    # is `"{species} - {method} ({ha} ha)"` in English, so the pseudo value is the bare
    # marker plus one `{name}` per placeholder, names sorted (`ha`, `method`, `species`)
    # for determinism - so a caller's own (untranslated) parameter still shows up in the
    # rendered text instead of being discarded by a template with no `{...}` of its own.
    assert (
        xx("app.report.option", species="S", method="M", ha="1")
        == "⟦app.report.option⟧ 1 M S"
    )


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
    # The switch fails closed: only 1/true/yes/on, in any case and stripped, show drafts.
    # (It used to treat anything but ""/0/false/no as on, so "False" showed them.)
    for off in ("", "0", " 0 ", "false", "False", "FALSE", "no", "No", "off", "yes please"):
        shown = enabled_languages(env={"SEAGARDEN_SHOW_DRAFT_LANGUAGES": off}, status=status)
        assert shown == ("en", "de"), f"{off!r} showed drafts"
    for on in ("1", "true", "TRUE", " True ", "yes", "on", "ON"):
        shown = enabled_languages(env={"SEAGARDEN_SHOW_DRAFT_LANGUAGES": on}, status=status)
        assert shown == ("en", "de", "pl"), f"{on!r} hid drafts"


def test_with_the_draft_switch_off_only_reviewed_languages_are_enabled():
    """Holds whatever is on disk: a draft never shows without the switch."""
    enabled = enabled_languages(env={})
    assert enabled[0] == "en"
    assert all(catalogue_status(language) == "reviewed" for language in enabled[1:])
    assert catalogue_status("en") == "reference"
    assert catalogue_status("xx") is None


def test_catalogue_status_is_read_once_per_process_and_root(tmp_path):
    """The gate runs on every page load, so the three files are read once, not per
    request; the roots are part of the cache key, so another tree is another entry.
    Two throwaway trees, so nothing here depends on which catalogues ship."""

    def tree(name: str, header: str) -> dict:
        roots = {}
        for owner in ("core", "app", "params"):
            root = tmp_path / name / owner
            root.mkdir(parents=True)
            (root / "de.yaml").write_text(header + "messages: {}\n", encoding="utf-8")
            roots[f"{owner}_root"] = root
        return roots

    reviewed = tree(
        "reviewed",
        "language: de\nstatus: reviewed\ntranslated_by: t\nreviewed_by: r\n"
        "reviewed_on: 2026-09-28\n",
    )
    draft = tree("draft", "language: de\nstatus: machine-draft\ntranslated_by: t\n")
    assert catalogue_status("de", **reviewed) == "reviewed"
    hits = catalogue_status.cache_info().hits
    assert catalogue_status("de", **reviewed) == "reviewed"
    assert catalogue_status.cache_info().hits == hits + 1
    assert catalogue_status("de", **draft) == "machine-draft"


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


def _request(query: bytes, accept: bytes | None):
    from starlette.requests import Request

    headers = [(b"accept-language", accept)] if accept else []
    return Request({
        "type": "http", "method": "GET", "scheme": "http", "path": "/",
        "query_string": query, "headers": headers, "server": ("test", 80),
    })


def test_app_ui_takes_a_request_and_reads_lang_from_it():
    from app.app import app_ui
    from app.i18n import language_for

    expected = language_for("?lang=de", "de", enabled_languages())
    assert f'lang="{expected}"' in str(app_ui(_request(b"lang=de", b"de")))
    assert 'lang="en"' in str(app_ui(_request(b"lang=zz", b"zz")))  # never a language
    assert 'lang="en"' in str(app_ui(_request(b"", None)))


def test_build_ui_draws_the_menu_from_the_enabled_set_it_is_given(monkeypatch):
    import app.app as entry

    html = str(entry.build_ui("en", enabled=("en", "de")))
    assert 'href="?lang=de"' in html and "Deutsch" in html
    # Left out, it is the deployment's own set, read at call time rather than at import.
    monkeypatch.setattr(entry, "enabled_languages", lambda: ("en", "pl"))
    html = str(entry.build_ui("en"))
    assert 'href="?lang=pl"' in html and 'href="?lang=de"' not in html


def test_app_ui_runs_the_gate_once_and_builds_the_menu_from_that_set(monkeypatch):
    """The page's language and its menu come from one `enabled_languages()` call."""
    import app.app as entry

    calls = []

    def gate():
        calls.append(None)
        return ("en", "de")

    monkeypatch.setattr(entry, "enabled_languages", gate)
    html = str(entry.app_ui(_request(b"", b"de")))
    assert len(calls) == 1
    assert 'lang="de"' in html and 'href="?lang=en"' in html


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
    # `headline_for` passes `species=tr.species_name(...)` into the keyed template, and
    # `Translator.pseudo()` now keeps that template's placeholders (I-a review round 1),
    # so the rendered sentence is the marker followed by its (still pseudo-marked)
    # parameters, not the bare marker alone - hence `startswith`, not `==`, and a second
    # assertion that the species name actually made it into the text.
    assert headline_for(assessment, xx)[1].startswith("⟦app.headline.best⟧")
    assert "⟦params.species." in headline_for(assessment, xx)[1]
    assert data_source_banner(state.forcing.get(), None, xx).startswith("⟦app.banner.artifact⟧")
    for tag in (
        render_ranking(assessment, xx), render_pressure(assessment, xx),
        render_conditions("LT-coastal", xx), render_position_note("LT-coastal", xx),
    ):
        assert "⟦app." in str(tag)
    assert "⟦params.species." in str(render_ranking(assessment, xx))
    # `render_excluded` shows the raw species key, not a translated name (results.py
    # keeps the exclusion identifier literal by design), and here the only excluded
    # entry's reason is a core-level literal Message carrying params sidecar text - so
    # its pseudo-marked key is `params.*`, not `app.*`. Still routed through `tr`.
    assert "⟦params." in str(render_excluded(assessment, xx))
    text = render_report(assessment, state.forcing.get(), today=date(2026, 9, 28), tr=xx)
    lines = text.splitlines()
    # `xx` is a draft, so line 0 is the bilingual banner (Task 2, I§6) and the report
    # itself - unchanged otherwise - starts one line later.
    assert lines[0] == "⟦app.shell.draft_banner⟧ " + english()("app.shell.draft_banner")
    assert lines[1] == "⟦app.report.heading⟧"
    # `Translator.pseudo()` keeps every marked template's own placeholders: the pseudo
    # value for a core/app key is `⟦key⟧` plus one ` {name}` per placeholder of its
    # English template, names sorted (`app/i18n.py::_pseudo_mark_templates`). A species
    # name or tier label passed as a PARAM into `app.report.option` /
    # `app.report.calibration` is therefore no longer discarded by the outer template -
    # it is formatted into the line, itself still pseudo-marked (`⟦params.species...⟧`,
    # `⟦calibration.tier...⟧`) because `Translator.__call__` renders a `Message` param
    # through this same Translator before formatting. This is the actual proof that
    # species/tier routing goes through `tr`: an untranslated (raw English) parameter
    # would show up here as plain text instead of a marker, which is exactly what the
    # pseudo-locale leak test (Task 8) checks for.
    assert "⟦params.species." in text and "⟦calibration.tier." in text


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


def test_the_position_note_names_its_provenance_through_its_own_key():
    """Lower-casing a translated label mangles German nouns, so the note reads
    `app.site.provenance_inline.<provenance>` - in English exactly the lower-cased
    legend label it replaced, so the English note is unchanged (I-a final review)."""
    from app.modules.site import render_position_note
    from seagarden_dst.forcing import SITE_COORDINATES, SiteProvenance

    en = Translator.for_language("en")
    for provenance in SiteProvenance:
        inline = en(f"app.site.provenance_inline.{provenance.value}")
        assert inline == str(provenance.label).lower()
    xx = Translator.pseudo()
    for region, coordinate in SITE_COORDINATES.items():
        note = str(render_position_note(region, en))
        inline = str(coordinate.provenance.label).lower()
        assert f"{coordinate.lat:.4f}, {coordinate.lon:.4f} - {inline}. A result here" in note
        marker = f"⟦app.site.provenance_inline.{coordinate.provenance.value}⟧"
        assert marker in str(render_position_note(region, xx))


# --- Task 2 (I-b): the gate fails safe; draft downloads say they are drafts -----------


def test_a_broken_catalogue_disables_its_language_and_never_the_site(tmp_path, caplog):
    """Inherited item 5: one malformed header used to 500 every page, English included."""
    import logging

    roots = {}
    for owner in ("core", "app", "params"):
        root = tmp_path / owner
        root.mkdir()
        # `reviewed` without reviewer fields: Catalogue.load raises ValueError
        (root / "de.yaml").write_text(
            "language: de\nstatus: reviewed\nmessages:\n  a.b: x\n", encoding="utf-8"
        )
        roots[owner] = root

    def status(language):
        return catalogue_status(
            language, core_root=roots["core"], app_root=roots["app"], params_root=roots["params"]
        )

    with caplog.at_level(logging.WARNING, logger="app.i18n"):
        enabled = enabled_languages(env={"SEAGARDEN_SHOW_DRAFT_LANGUAGES": "1"}, status=status)
    assert enabled == ("en",)
    assert "de" in caplog.text


def test_a_broken_catalogues_warning_is_logged_once_across_repeated_calls(
    tmp_path, caplog, monkeypatch
):
    """I-b review (Important 2): the test above proves one call logs a warning; it
    would still pass if a regression logged on every call instead of once per distinct
    message. This calls the gate twice against the same broken catalogue and pins that
    only one warning record is emitted.

    Isolation: the dedup set (`app.i18n._logged_catalogue_errors`) is module-level and
    process-wide, so this test resets it via `monkeypatch` rather than relying on this
    test's `tmp_path`-embedded error message being distinct from every other test's -
    that holds for a `ValueError` (whose text includes the failing file's path) but not
    for the bare `AttributeError`s the next two tests trigger, whose text is the same
    generic Python message regardless of which file caused it.
    """
    import logging

    import app.i18n as app_i18n

    monkeypatch.setattr(app_i18n, "_logged_catalogue_errors", set())

    roots = {}
    for owner in ("core", "app", "params"):
        root = tmp_path / owner
        root.mkdir()
        (root / "de.yaml").write_text(
            "language: de\nstatus: reviewed\nmessages:\n  a.b: x\n", encoding="utf-8"
        )
        roots[owner] = root

    def status(language):
        return catalogue_status(
            language, core_root=roots["core"], app_root=roots["app"], params_root=roots["params"]
        )

    with caplog.at_level(logging.WARNING, logger="app.i18n"):
        enabled_languages(env={"SEAGARDEN_SHOW_DRAFT_LANGUAGES": "1"}, status=status)
        enabled_languages(env={"SEAGARDEN_SHOW_DRAFT_LANGUAGES": "1"}, status=status)
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "ValueError" in caplog.text  # the log line names the exception type too


def test_a_catalogue_whose_top_level_is_a_list_disables_its_language_not_the_site(
    tmp_path, caplog, monkeypatch
):
    """I-b review (Critical 1): `Catalogue.load` calls `data.get("language")` on
    whatever `yaml.safe_load` returns. A file whose top level is a YAML list, not a
    mapping, raises `AttributeError` - outside the original `(OSError, ValueError,
    yaml.YAMLError)` tuple, which let this one raise out of `enabled_languages` and
    take the whole site down, not just `de`. See the isolation note on the test above
    for why the dedup set is reset here too."""
    import logging

    import app.i18n as app_i18n

    monkeypatch.setattr(app_i18n, "_logged_catalogue_errors", set())

    roots = {}
    for owner in ("core", "app", "params"):
        root = tmp_path / owner
        root.mkdir()
        (root / "de.yaml").write_text("- a\n- b\n", encoding="utf-8")
        roots[owner] = root

    def status(language):
        return catalogue_status(
            language, core_root=roots["core"], app_root=roots["app"], params_root=roots["params"]
        )

    with caplog.at_level(logging.WARNING, logger="app.i18n"):
        enabled = enabled_languages(env={"SEAGARDEN_SHOW_DRAFT_LANGUAGES": "1"}, status=status)
    assert enabled == ("en",)
    assert "de" in caplog.text
    assert "AttributeError" in caplog.text


def test_a_catalogue_whose_messages_are_not_a_mapping_disables_its_language(
    tmp_path, caplog, monkeypatch
):
    """I-b review (Critical 1): a `messages:` value that YAML parses as anything but a
    mapping fails one level deeper in `Catalogue.load` (`.items()` on a string) - also
    an `AttributeError` outside the original tuple, also just a disabled language."""
    import logging

    import app.i18n as app_i18n

    monkeypatch.setattr(app_i18n, "_logged_catalogue_errors", set())

    roots = {}
    for owner in ("core", "app", "params"):
        root = tmp_path / owner
        root.mkdir()
        (root / "de.yaml").write_text(
            "language: de\nstatus: machine-draft\ntranslated_by: t\nmessages: nope\n",
            encoding="utf-8",
        )
        roots[owner] = root

    def status(language):
        return catalogue_status(
            language, core_root=roots["core"], app_root=roots["app"], params_root=roots["params"]
        )

    with caplog.at_level(logging.WARNING, logger="app.i18n"):
        enabled = enabled_languages(env={"SEAGARDEN_SHOW_DRAFT_LANGUAGES": "1"}, status=status)
    assert enabled == ("en",)
    assert "de" in caplog.text
    assert "AttributeError" in caplog.text


def test_a_draft_report_says_so_in_both_languages_and_english_does_not():
    from datetime import date

    from app.modules.report import render_report

    today = date(2026, 9, 29)
    draft = render_report(None, today=today, tr=Translator.pseudo())
    assert draft.splitlines()[0] == (
        "⟦app.shell.draft_banner⟧ " + english()("app.shell.draft_banner")
    )
    assert render_report(None, today=today, tr=english()) == english()("app.report.none")


def test_the_json_export_names_its_language_and_draft_status():
    import json

    from app.modules.report import export_json

    assert json.loads(export_json(None, english())) == {"language": "en", "draft": False}
    marked = json.loads(export_json(None, Translator.pseudo()))
    assert marked["language"] == "xx" and marked["draft"] is True


def test_the_json_export_of_a_real_assessment_keeps_every_to_dict_key():
    import json

    from app.modules.report import export_json

    state = _assessed_state()
    assessment = state.assessment.get()
    payload = json.loads(export_json(assessment, english()))
    assert payload["language"] == "en" and payload["draft"] is False
    # Every key `to_dict()` emits is still there, beside the two new ones - nothing
    # dropped, nothing extra.
    assert set(payload) == {"language", "draft", *assessment.to_dict()}
