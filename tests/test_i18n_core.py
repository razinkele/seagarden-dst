"""Every core prose site returns a Message whose English is what it said before (I§5.1)."""

from __future__ import annotations

import dataclasses

from seagarden_dst import PLACEHOLDER_SITES, Tier, default_parameters
from seagarden_dst.calibration import Calibration, Quantity
from seagarden_dst.growth import contraindication
from seagarden_dst.i18n import Message, core_catalogue
from seagarden_dst.params import SpeciesParams


def test_tier_label_and_presentation_are_messages_with_the_old_english():
    assert isinstance(Tier.C.label, Message)
    assert str(Tier.C.label) == "Literature prior"
    assert str(Tier.D.presentation) == "finding shown in place of the number"


def test_calibration_caveats_render_as_before():
    c = Calibration(tier=Tier.C, region="LT-coastal", source="OLAMUR D3.2")
    assert str(c.caveat()) == (
        "Indicative only - literature prior (OLAMUR D3.2), no local validation."
    )
    b = Calibration(tier=Tier.B, region="LT-coastal", source="S", calibrated_on="Tagalaht")
    assert str(b.caveat()) == "Extrapolated - parameters calibrated on Tagalaht (S)."
    b2 = Calibration(tier=Tier.B, region="LT-coastal", source="S")
    assert str(b2.caveat()) == (
        "Extrapolated - parameters calibrated on elsewhere in the Baltic (S)."
    )
    a = Calibration(tier=Tier.A, region="LT-coastal", source="S")
    assert str(a.caveat()) == "Calibrated on LT-coastal pilot data (S)."
    d = Calibration(tier=Tier.D, region="x", source="S")
    assert str(d.caveat()) == "Contraindicated for this region."


def test_a_yaml_note_becomes_a_literal_and_survives_untranslated():
    d = Calibration(tier=Tier.D, region="x", source="S", note="Fails below 16 psu.")
    caveat = d.caveat()
    assert caveat.key == "literal" and str(caveat) == "Fails below 16 psu."
    assert core_catalogue("de").render(caveat) == "Fails below 16 psu."


def test_quantity_str_is_unchanged():
    c = Calibration(tier=Tier.C, region="r", source="S")
    assert str(Quantity(3.0, "kg DW", c)) == "3 kg DW [C]"
    assert str(Quantity(3.0, "kg DW", c, low=1.0, high=9.0)) == "1-9 kg DW [C]"
    d = Calibration(tier=Tier.D, region="r", source="S", note="no")
    assert str(Quantity(0.0, "kg DW", d)) == "not applicable - no"


def test_contraindication_note_is_a_message_saying_what_it_said():
    kelp = default_parameters().species["saccharina_latissima"]
    site = dataclasses.replace(PLACEHOLDER_SITES["LT-lagoon"], salinity_psu=2.0)
    calibration = contraindication(kelp, site)
    assert calibration is not None and isinstance(calibration.note, Message)
    text = str(calibration.note)
    assert text.startswith("Below ") and text.endswith("Treat as not cultivable here.")
    assert "observed" in text or "assumed" in text


def test_the_default_calibration_statement_is_a_message():
    # Every real species file carries a "default" calibration entry, so the
    # generic fallback in params.py:calibration_for is otherwise unreachable
    # through default_parameters(); strip the entries to force that path.
    kelp = default_parameters().species["saccharina_latissima"]
    no_calibration = SpeciesParams(**{**kelp.model_dump(), "calibration": []})
    fallback = no_calibration.calibration_for("nowhere")
    assert isinstance(fallback.note, Message)
    assert str(fallback.note) == "No calibration statement for this region."


def test_constraints_and_explanations_are_messages_saying_what_they_said():
    from seagarden_dst import SiteContext, assess_site

    result = assess_site(SiteContext.from_region("LT-coastal"))
    option = result.ranked[0]
    assert isinstance(option.binding_constraint, Message)
    for name, verdict, reason in option.constraints:
        assert isinstance(name, Message) and isinstance(reason, Message)
        assert verdict in {"suitable", "marginal", "unsuitable", "unknown"}
    names = {str(c[0]) for c in option.constraints}
    assert names == {
        "Physical feasibility", "Environmental tolerance", "Growth viability",
        "Legal permissibility",
    }
    legal = next(c for c in option.constraints if str(c[0]) == "Legal permissibility")
    assert str(legal[2]).startswith("No regulatory record loaded")
    assert str(option.binding_constraint).startswith("Legal permissibility: ")


def test_caveats_excluded_and_pressure_note_are_messages():
    from seagarden_dst import CAVEAT_LABELS, SiteContext, assess_site

    result = assess_site(
        SiteContext.from_region("LT-coastal"),
        eutropy={"nonsense": True},
        bowtie={"Catastrophe": 1.0},
    )
    assert all(isinstance(v, Message) for v in result.caveats.values())
    assert all(isinstance(v, Message) for v in result.excluded.values())
    assert isinstance(result.pressure_note, Message)
    assert str(result.caveats["nutrient_forcing"]).startswith("EUTROPY forcing not applied: ")
    assert str(CAVEAT_LABELS["nutrient_forcing"]) == "nutrient forcing"
    assert "failed" in str(result.excluded["saccharina_latissima"]).lower()


def test_pressure_note_without_a_bowtie_is_none_not_an_empty_message():
    from seagarden_dst import SiteContext, assess_site

    assert assess_site(SiteContext.from_region("LT-coastal")).pressure_note is None


def test_scale_labels_and_verdict_labels_are_messages():
    from seagarden_dst import SCALE_LABELS, Verdict

    assert str(SCALE_LABELS["community_farm_0_1_ha"]) == "community farm (0.1 ha)"
    assert isinstance(Verdict.SUITABLE.label, Message)
    assert str(Verdict.UNSUITABLE.label) == "unsuitable"


def test_the_adapter_notes_compose_from_keyed_sentences():
    from seagarden_dst import SiteContext, assess_site

    bowtie = {"Low": 0.2, "Moderate": 0.3, "High": 0.5}
    lagoon = assess_site(SiteContext.from_region("LT-lagoon"), bowtie=bowtie)
    note = str(lagoon.pressure_note)
    assert note.startswith("Eutrophication pressure from the MARBEFES bow-tie (bow-tie scenario).")
    assert note.endswith("neither a yield nor a risk.")
    assert "parameterised for the Curonian Lagoon" not in note  # in domain
    coast = assess_site(SiteContext.from_region("LT-coastal"), bowtie=bowtie)
    assert "this site is LT-coastal" in str(coast.pressure_note)
