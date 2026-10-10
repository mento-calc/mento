"""Explicit legs preserve legacy calculations and survive summary Excel round trips."""

import pytest

from mento import (
    Concrete_ACI_318_19,
    Concrete_CIRSOC_201_25,
    Concrete_EN_1992_2004,
    Forces,
    RectangularBeam,
    SteelBar,
)
from mento.units import MPa, cm, inch, kN, mm


def beam(concrete_type=Concrete_ACI_318_19):
    return RectangularBeam(
        concrete=concrete_type(name="C25", f_c=25 * MPa),
        steel_bar=SteelBar(name="S420", f_y=420 * MPa),
        width=40 * cm,
        height=60 * cm,
        c_c=25 * mm,
    )


@pytest.mark.parametrize("concrete_type", [Concrete_ACI_318_19, Concrete_CIRSOC_201_25, Concrete_EN_1992_2004])
@pytest.mark.parametrize("diameter,spacing", [(8 * mm, 20 * cm), (0.375 * inch, 8 * inch)])
def test_leg_input_matches_legacy_shear_and_geometry(concrete_type, diameter, spacing):
    old, new = beam(concrete_type), beam(concrete_type)
    old.set_transverse_rebar(2, diameter, spacing)
    new.set_transverse_rebar(n_legs=4, d_b=diameter, s_l=spacing)
    assert new.reinforcement.transverse == old.reinforcement.transverse
    assert new.section_geometry == old.section_geometry
    force = Forces(V_z=100 * kN)
    old.check_shear([force])
    new.check_shear([force])
    assert new.shear_checks == old.shear_checks


@pytest.mark.parametrize("legs,error", [(1, ValueError), (-2, ValueError), (4.5, TypeError), (True, TypeError)])
def test_bad_leg_input_keeps_previous_reinforcement(legs, error):
    b = beam()
    b.set_transverse_rebar(2, 8 * mm, 20 * cm)
    before = b.reinforcement
    with pytest.raises(error, match="n_legs"):
        b.set_transverse_rebar(n_legs=legs, d_b=8 * mm, s_l=20 * cm)
    assert b.reinforcement == before


def test_conflicting_leg_input_rejects_explicit_zero_and_preserves_state():
    b = beam()
    b.set_transverse_rebar(n_stirrups=2, n_legs=4, d_b=8 * mm, s_l=20 * cm)
    before = b.reinforcement
    with pytest.raises(ValueError, match="equal"):
        b.set_transverse_rebar(n_stirrups=0, n_legs=4, d_b=8 * mm, s_l=20 * cm)
    assert b.reinforcement == before
    b.set_transverse_rebar(n_legs=0)
    assert b.reinforcement.transverse.n_legs == 0
