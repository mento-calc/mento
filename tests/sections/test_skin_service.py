"""The service data of the skin is mento's assumption: sigma_s = 0.6 f_yk and x = 0.4 h, with no input for it."""

import pytest

import mento
from mento import (
    Concrete_ACI_318_19,
    Concrete_EN_1992_2004,
    Forces,
    NotABeamError,
    RectangularBeam,
    ShearWall,
    SteelBar,
)
from mento.codes.en_1992_2004.skin import ASSUMED_SERVICE_STRESS
from mento.skin_reinforcement import ASSUMED_NEUTRAL_AXIS
from mento.units import MPa, cm, kNm, mm


def section():
    b = RectangularBeam(
        label="S",
        concrete=Concrete_EN_1992_2004(name="C25", f_c=25 * MPa),
        steel_bar=SteelBar(name="B500", f_y=500 * MPa),
        width=30 * cm,
        height=120 * cm,
        c_c=30 * mm,
    )
    b.set_longitudinal_rebar_bot(n1=4, d_b1=20 * mm)
    b.set_longitudinal_rebar_top(n1=4, d_b1=20 * mm)
    b.set_transverse_rebar(1, 8 * mm, 20 * cm)
    b.check_flexure([Forces(M_y=100 * kNm), Forces(M_y=-80 * kNm)])
    return b


def test_the_assumptions_are_the_documented_ones():
    assert (ASSUMED_SERVICE_STRESS, ASSUMED_NEUTRAL_AXIS) == (0.6, 0.4)


def test_each_tension_zone_ends_at_the_assumed_neutral_axis():
    """30x120 under +100 / -80 kN·m: x = 0.4 * 1200 = 480 mm, so the zones are 48..720 and 480..1152 mm."""
    req = section().skin_reinforcement
    assert req.status == "required"
    assert [(z.tension_face, z.lower.to("mm").magnitude, z.upper.to("mm").magnitude) for z in req.check_zones] == [
        ("bottom", pytest.approx(48), pytest.approx(720)),
        ("top", pytest.approx(480), pytest.approx(1152)),
    ]


def test_the_diameter_cap_reads_the_assumed_stress():
    """0.6 * 500 = 300 MPa, half 150 -> phi* = 32 mm (Table 7.2N, 0.3 mm); the web as a tie: 300 / (8 * 42)."""
    req = section().skin_reinforcement
    fct = 0.3 * 25 ** (2 / 3)
    assert req.d_b == 8 * mm
    assert req.diameter_max.to("mm").magnitude == pytest.approx(32 * fct / 2.9 * 300 / (8 * 42))


def test_there_is_no_input_for_service_cases_and_no_notice_about_them():
    b = section()
    assert not hasattr(mento, "SkinServiceCase")
    assert not hasattr(b, "set_skin_service_cases") and not hasattr(b, "skin_service_cases")
    assert not any("service" in w.code for w in b.warnings)


def test_wall_does_not_publish_beam_skin_results():
    wall = ShearWall(
        label="W",
        concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN420", f_y=420 * MPa),
        thickness=25 * cm,
        length=400 * cm,
        height=350 * cm,
        c_c=20 * mm,
    )
    assert not hasattr(wall, "skin_reinforcement")
    with pytest.raises(NotABeamError):
        wall.skin_reinforcement
