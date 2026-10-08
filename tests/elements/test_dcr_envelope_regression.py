"""La envolvente histórica debe coincidir con los resultados por combinación."""

import pytest
from mento import Concrete_ACI_318_19, RectangularBeam, SteelBar, Forces
from mento.units import MPa, cm, mm, kNm


@pytest.mark.parametrize("reverse", [False, True])
def test_legacy_face_dcr_keeps_the_maximum_in_any_order(reverse):
    beam = RectangularBeam(
        label="Envelope",
        concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
        steel_bar=SteelBar(name="420", f_y=420 * MPa),
        width=40 * cm,
        height=60 * cm,
        c_c=30 * mm,
    )
    beam.set_longitudinal_rebar_bot(n1=7, d_b1=20 * mm)
    beam.set_longitudinal_rebar_top(n1=3, d_b1=16 * mm)
    forces = [Forces(label=str(moment), M_y=moment * kNm) for moment in (120, 30, -80, -20)]
    if reverse:
        forces.reverse()
    results = beam.check_flexure(forces)
    assert len(results) == 5
    assert len(beam.flexure_checks) == 4
    for face, suffix in (("bottom", "bot"), ("top", "top")):
        expected = max(getattr(check, face).DCR for check in beam.flexure_checks)
        assert getattr(beam, "_DCRb_" + suffix) == pytest.approx(expected)
        assert getattr(beam, "_max_dcr_" + suffix) == pytest.approx(expected)
