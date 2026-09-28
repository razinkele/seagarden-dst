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
