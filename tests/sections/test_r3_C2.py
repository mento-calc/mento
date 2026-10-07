import pytest
from mento import Concrete_EN_1992_2004, Forces, RectangularBeam, SteelBar, MPa, cm, mm, kN, kNm


def en_beam():
    b = RectangularBeam(
        label="EN",
        concrete=Concrete_EN_1992_2004(name="C25", f_c=25 * MPa),
        steel_bar=SteelBar(name="B500", f_y=500 * MPa),
        width=30 * cm,
        height=40 * cm,
        c_c=30 * mm,
    )
    b.set_longitudinal_rebar_bot(n1=4, d_b1=25 * mm)
    b.set_longitudinal_rebar_top(n1=2, d_b1=16 * mm)
    b.set_transverse_rebar(1, 8 * mm, 25 * cm)
    return b


@pytest.mark.parametrize("negative", [False, True])
def test_en_credited_compression_steel_is_pending(negative):
    b = en_beam()
    if negative:
        b.set_longitudinal_rebar_top(n1=4, d_b1=25 * mm)
        b.set_longitudinal_rebar_bot(n1=2, d_b1=16 * mm)
    f = [Forces(M_y=(-150 if negative else 150) * kNm, V_z=50 * kN)]
    b.check_flexure(f)
    b.check_shear(f)
    assert b._compression_faces == ({"bot"} if negative else {"top"})
    assert b.verification_status["resistance"] == "passed"
    assert b.verification_status["detailing"] == "pending"
    if hasattr(b, "compression_detailing"):
        assert b.compression_detailing.status == "pending"
        assert "15φ" in b.compression_detailing.reason


def test_en_singly_reinforced_has_no_compression_requirement():
    b = en_beam()
    b.set_longitudinal_rebar_bot(n1=2, d_b1=16 * mm)
    b.check_flexure([Forces(M_y=10 * kNm)])
    assert b._compression_faces == set()
