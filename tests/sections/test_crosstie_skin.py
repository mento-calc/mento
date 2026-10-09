"""Un choque de piel con la cola de una traba conserva el diagnóstico de piel."""

from dataclasses import replace

import pytest

from mento import Concrete_ACI_318_19, Forces, RectangularBeam, SteelBar
from mento.cage_detailing import CageDetailingError
from mento.crosstie_detailing import finalize_crossties, hook_points
from mento.units import MPa, cm, kN, kNm, mm


def test_skin_hook_collision_is_skin_error_not_base_cage_failure():
    b = RectangularBeam(
        concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN420", f_y=420 * MPa),
        width=80 * cm,
        height=60 * cm,
        c_c=30 * mm,
    )
    b.set_longitudinal_rebar_bot(n1=7, d_b1=25 * mm)
    b.set_longitudinal_rebar_top(n1=3, d_b1=25 * mm)
    b.set_transverse_rebar(legs=7, d_b=10 * mm, s_l=15 * cm)
    b.check([Forces(M_y=100 * kNm, V_z=80 * kN)])
    # Aislar el choque; fuerzas reales cubiertas por test_crosstie_detailing.
    b._compression_faces = {"bot"}
    g = b.detailing_geometry
    assert g.mounting_bars
    path = hook_points(g.crossties[0], g.stirrup_d_b)[0]
    x, y = ((path[-2][i] + path[-1][i]) / 2 for i in range(2))
    clash = replace(g.bars[0], x=x * mm, y=y * mm, face="left", layer=0)
    with pytest.raises(CageDetailingError) as caught:
        finalize_crossties(replace(g, skin_bars=(clash,)))
    assert caught.value.reason == "skin"
    assert finalize_crossties(g).mounting_bars == g.mounting_bars
