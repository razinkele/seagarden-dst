"""The Message value and the catalogue (spec I§4). Core only; no Shiny."""

from __future__ import annotations

import json

import pytest
import yaml

from seagarden_dst.i18n import (
    CORE_LOCALES,
    DEFAULT_LANGUAGE,
    LANGUAGES,
    Catalogue,
    Message,
    core_catalogue,
    msg,
    placeholders,
)


def test_str_of_a_message_is_its_english_text():
    assert str(msg("calibration.tier.A.label")) == "Locally calibrated"


def test_params_are_interpolated_and_nested_messages_render_in_place():
    inner = msg("suitability.class.legal")
    outer = msg("suitability.explain.binding", name=inner, reason="because")
    assert str(outer) == "Legal permissibility: because"


def test_a_literal_renders_as_its_own_text_in_every_language():
    lit = Message.literal("Raft")
    assert lit.key == "literal"
    assert str(lit) == "Raft"
    assert core_catalogue("de").render(lit) == "Raft"


def test_join_renders_its_parts_separated():
    joined = Message.join(msg("suitability.explain.none"), Message.literal("Also this."))
    assert str(joined) == "No assessment performed. Also this."
    assert Message.join().key == "_join" and str(Message.join()) == ""


def test_equality_is_structural():
    assert msg("a.b", x=1) == msg("a.b", x=1)
    assert msg("a.b", x=1) != msg("a.b", x=2)


def test_printing_a_results_caveats_reads_as_english(capsys):
    """I§11.5, the spec's own command: `print(assess_site(...).caveats)` shows readable
    English from a core-only install - the notebook promise holds. A dict prints its
    values with `repr()`, so this is `Message.__repr__`'s job, not `__str__`'s."""
    from seagarden_dst import SiteContext, assess_site

    caveats = assess_site(SiteContext.from_region("LT-coastal")).caveats
    assert caveats, "the spec's example needs a caveat to print"
    print(caveats)
    printed = capsys.readouterr().out
    for message in caveats.values():
        english = str(message)
        assert " " in english and english != message.key, "a sentence, not a key"
        assert repr(english) in printed and repr(message.key) in printed
    assert "params=" not in printed, "the bare dataclass repr is back"


def test_repr_falls_back_to_structure_when_the_message_cannot_render():
    class Unformattable:
        def __format__(self, spec):
            raise ValueError("cannot format")

        def __repr__(self):
            return "Unformattable()"

    # No English entry: KeyError inside, structure outside.
    assert repr(msg("no.such.key", x=1)) == "Message(key='no.such.key', params={'x': 1})"
    # A render that fails with ValueError.
    broken = msg("suitability.explain.binding", name=Unformattable(), reason="r")
    assert repr(broken) == (
        "Message(key='suitability.explain.binding', "
        "params={'name': Unformattable(), 'reason': 'r'})"
    )
    # A broken nested message: the outer falls back and the inner shows its own structure.
    nested = msg("suitability.explain.binding", name=msg("no.such.key"), reason="r")
    assert "Message(key='no.such.key', params={})" in repr(nested)


def test_a_message_takes_a_format_spec_like_its_english_text():
    m = msg("calibration.tier.A.label")
    assert format(m, ">20") == format("Locally calibrated", ">20")
    assert f"[{m:<20}]" == "[Locally calibrated  ]"
    assert f"{m}" == "Locally calibrated"


def test_placeholders_reads_a_template_the_way_str_format_does():
    assert placeholders("{a} and {b}") == {"a", "b"}
    assert placeholders("{{a}} and {b}") == {"b"}  # doubled braces are literal text
    with pytest.raises(ValueError):
        placeholders("{a} m}")


def test_to_dict_carries_key_params_and_rendered_text():
    m = msg("suitability.explain.binding", name=msg("suitability.class.legal"), reason="r")
    d = m.to_dict()
    assert d == {
        "key": "suitability.explain.binding",
        "params": {"name": "Legal permissibility", "reason": "r"},
        "text": "Legal permissibility: r",
    }
    json.dumps(d)  # must be serialisable as-is
    upper = m.to_dict(render=lambda message: str(message).upper())
    assert upper["text"] == "LEGAL PERMISSIBILITY: R"


def test_a_missing_english_key_is_a_defect_named_in_the_error():
    with pytest.raises(KeyError, match="no.such.key"):
        str(msg("no.such.key"))


def test_a_missing_key_in_another_language_falls_back_to_english(tmp_path):
    (tmp_path / "en.yaml").write_text(
        "language: en\nstatus: reference\nmessages:\n  a.b: 'hello {x}'\n  a.c: 'only english'\n",
        encoding="utf-8",
    )
    (tmp_path / "xx.yaml").write_text(
        "language: xx\nstatus: machine-draft\ntranslated_by: test\nmessages:\n  a.b: 'hallo {x}'\n",
        encoding="utf-8",
    )
    en = Catalogue.load("en", tmp_path)
    xx = Catalogue.load("xx", tmp_path, fallback=en)
    assert xx.render(msg("a.b", x=1)) == "hallo 1"
    assert xx.render(msg("a.c")) == "only english"
    assert xx.status == "machine-draft" and xx.reviewed_by is None


def test_a_reviewed_catalogue_must_name_its_reviewer(tmp_path):
    (tmp_path / "xx.yaml").write_text(
        "language: xx\nstatus: reviewed\nmessages:\n  a.b: x\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="reviewed_by"):
        Catalogue.load("xx", tmp_path)


def test_a_brace_in_a_value_that_is_not_a_param_names_key_and_language(tmp_path):
    (tmp_path / "en.yaml").write_text(
        "language: en\nstatus: reference\nmessages:\n  a.b: 'oops {typo}'\n", encoding="utf-8"
    )
    with pytest.raises(KeyError, match=r"a\.b.*en.*typo"):
        Catalogue.load("en", tmp_path).render(msg("a.b"))


def test_an_unbalanced_brace_is_a_value_error_naming_key_and_language(tmp_path):
    (tmp_path / "en.yaml").write_text(
        "language: en\nstatus: reference\nmessages:\n  a.b: 'depth {x} m}'\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match=r"'a\.b' in 'en' is not a valid template"):
        Catalogue.load("en", tmp_path).render(msg("a.b", x="3"))


def test_the_english_core_catalogue_is_the_reference():
    en = core_catalogue(DEFAULT_LANGUAGE)
    assert en.status == "reference"
    assert (CORE_LOCALES / "en.yaml").is_file()
    assert "calibration.tier.D.presentation" in en.keys()


def test_languages_are_the_six_the_spec_names():
    assert LANGUAGES == ("en", "de", "pl", "da", "lt", "sv")


def test_a_non_english_core_catalogue_without_a_file_is_english_with_that_language_code():
    """Package I-b adds the files. Until then `core_catalogue("de")` must not raise: the
    app may be asked for German by a browser header before any German exists."""
    de = core_catalogue("de")
    assert de.language == "de"
    assert de.render(msg("calibration.tier.A.label")) == "Locally calibrated"


def test_core_catalogue_reuses_the_cached_english_catalogue():
    assert core_catalogue("de").fallback is core_catalogue("en")


def test_every_core_yaml_parses_with_the_required_header():
    for path in sorted(CORE_LOCALES.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert data["language"] == path.stem
        assert data["status"] in {"reference", "machine-draft", "reviewed"}
        assert isinstance(data["messages"], dict) and data["messages"]
