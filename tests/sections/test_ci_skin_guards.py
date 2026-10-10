"""Rechazos seccionales de piel: no omitir entradas ni aprobar geometría inválida."""

from dataclasses import replace
from types import SimpleNamespace

import pytest

import mento.skin_reinforcement as skin
from mento import Forces, SkinServiceCase
from mento.cage_detailing import CageDetailingError
from mento.units import MPa, cm, kNm, mm
from tests.sections.test_skin_reinforcement import beam


@pytest.fixture
def checked():
    b = beam()
    b.check_flexure([Forces(M_y=100 * kNm)])
    return b


@pytest.mark.parametrize("label,face", [("", "bottom"), ("   ", "top"), ("SLS", "left")])
def test_invalid_service_identity_is_rejected(label, face):
    with pytest.raises(ValueError, match="non-empty label|tension_face"):
        SkinServiceCase(label, face, 200 * MPa, 200 * mm)


def test_unmodelled_code_is_unsupported_not_exempt(checked, monkeypatch):
    monkeypatch.setattr(skin, "design_code", lambda _: SimpleNamespace(skin_reinforcement_threshold=None))
    assert skin.skin_requirement(checked).status == "unsupported"


def test_nonpositive_spacing_cap_reports_skin_error(checked, monkeypatch):
    code = SimpleNamespace(
        skin_reinforcement_threshold=lambda _: 900 * mm,
        skin_threshold_inclusive=False,
        skin_diameter_cap=None,
        max_skin_bar_spacing=lambda *_: 0 * mm,
    )
    monkeypatch.setattr(skin, "design_code", lambda _: code)
    with pytest.raises(CageDetailingError, match="No positive skin-bar spacing") as error:
        skin.skin_requirement(checked)
    assert error.value.reason == "skin"


def test_missing_layers_anchor_the_skin_at_the_stirrup(checked, monkeypatch):
    """No bars: both anchors at 30 + 8 + 10 = 48 mm from the faces, the same rows as the Ø20 layers give."""
    g = checked.section_geometry
    monkeypatch.setattr(type(checked), "section_geometry", property(lambda _: replace(g, bars=())))
    req = skin.skin_requirement(checked)
    assert req.status == "required"
    assert [y.to(mm).magnitude for y in req.rows] == pytest.approx([324, 600, 876])


@pytest.mark.parametrize(
    "bottom,message",
    [
        # Layer at 1000 mm, above the neutral axis at 1200 - 0.4 * 1200 = 720 mm.
        (1000, "neutral axis must lie above the tension layer"),
        # Layer at 1160 mm, above the top layer at 1152 mm: nothing left between them.
        (1160, "no height between its layers"),
    ],
)
def test_tension_anchor_must_lie_below_the_neutral_axis_and_the_top_layer(checked, monkeypatch, bottom, message):
    g = checked.section_geometry
    bars = tuple(replace(b, y=bottom * mm) if b.face == "bottom" else b for b in g.bars)
    monkeypatch.setattr(type(checked), "section_geometry", property(lambda _: replace(g, bars=bars)))
    with pytest.raises(CageDetailingError, match=message) as error:
        skin.skin_requirement(checked)
    assert error.value.reason == "skin"


def test_manual_not_applicable_preserves_scope(checked):
    checked.set_skin_rebar(10 * mm, 2, "total")
    req = skin._manual_skin_requirement(checked, skin.SkinReinforcementRequirement("not_applicable"))
    assert req.manual and req.status == "not_applicable" and not req.rows


def test_manual_layout_without_main_bars_uses_cover_boundaries(checked, monkeypatch):
    checked.set_skin_rebar(10 * mm, 2, "total")
    g = checked.section_geometry
    monkeypatch.setattr(type(checked), "section_geometry", property(lambda _: replace(g, bars=())))
    req = skin._manual_skin_requirement(checked, skin.SkinReinforcementRequirement("not_required"))
    inset = (checked.c_c + checked._stirrup_d_b + 5 * mm).to(mm).magnitude
    span = checked.height.to(mm).magnitude - 2 * inset
    assert [y.to(mm).magnitude for y in req.rows] == pytest.approx([inset + span / 3, inset + 2 * span / 3])


def test_manual_zone_with_reversed_anchors_is_failed(checked, monkeypatch):
    checked.set_skin_rebar(10 * mm, 0, "total")
    g = checked.section_geometry
    bars = tuple(replace(b, y=(1000 if b.face == "bottom" else 200) * mm) for b in g.bars)
    monkeypatch.setattr(type(checked), "section_geometry", property(lambda _: replace(g, bars=bars)))
    req = skin._manual_skin_requirement(checked, skin.SkinReinforcementRequirement("not_required"))
    assert "No height is available for the supplied skin zone." in req.failures


def test_manual_diameter_limit_failure_does_not_redesign_user_input(checked):
    checked.set_skin_rebar(10 * mm, 2, "total")
    req = skin._manual_skin_requirement(checked, skin.SkinReinforcementRequirement("required", diameter_max=8 * mm))
    assert "The supplied skin diameter exceeds the supported EN diameter limit." in req.failures
    assert req.d_b == 10 * mm and req.n_per_side == 2


def test_zero_manual_count_adds_no_bars():
    b = beam(height=50 * cm)
    b.set_skin_rebar(10 * mm, 0, "total")
    g = b.section_geometry
    assert skin.add_skin_bars(b, g) is g


def test_lateral_bars_cannot_be_added_to_a_narrow_section(checked):
    with pytest.raises(CageDetailingError, match="section width") as error:
        skin.add_skin_bars(checked, replace(checked.section_geometry, width=20 * mm))
    assert error.value.reason == "skin"


@pytest.mark.parametrize("fault", ["cover", "collision"])
def test_supplied_rows_cannot_violate_cover_or_main_bar_clearance(checked, monkeypatch, fault):
    g = checked.section_geometry
    req = checked.skin_reinforcement
    row = 0 * mm if fault == "cover" else g.bars_on("bottom", 1)[0].y
    monkeypatch.setattr(skin, "skin_requirement", lambda _: replace(req, rows=(row,)))
    with pytest.raises(CageDetailingError, match="cover|clear spacing") as error:
        skin.add_skin_bars(checked, g)
    assert error.value.reason == "skin"
