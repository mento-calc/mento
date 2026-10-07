"""Decisiones de entrega: alias, estados independientes y alcance axial."""

import math

import pandas as pd
import pytest

from mento import (
    Concrete_ACI_318_19,
    Concrete_EN_1992_2004,
    Footing,
    Forces,
    RectangularBeam,
    SteelBar,
    MPa,
    cm,
    kN,
    kNm,
    mm,
)
from mento.i18n import get_language, set_language
from mento.verification import normalize_leg_column


def make_beam():
    return RectangularBeam(
        label="Entrega",
        concrete=Concrete_ACI_318_19(name="H30", f_c=30 * MPa),
        steel_bar=SteelBar(name="ADN420", f_y=420 * MPa),
        width=40 * cm,
        height=60 * cm,
        c_c=25 * mm,
    )


def test_legs_preferred_with_compatible_alias():
    beam = make_beam()
    beam.set_transverse_rebar(legs=4, n_legs=4, d_b=8 * mm, s_l=15 * cm)
    assert beam.reinforcement.transverse.n_legs == 4
    assert beam.reinforcement.transverse.n_stirrups == 2
    assert beam._A_v.to("mm**2/mm").magnitude == pytest.approx(4 * math.pi * 8**2 / 4 / 150)


@pytest.mark.parametrize(
    "options", [{"legs": 7}, {"legs": True}, {"legs": 4, "n_legs": 6}, {"legs": 4, "n_stirrups": 1}]
)
def test_unsupported_or_conflicting_legs_do_not_change_beam(options):
    beam = make_beam()
    original = beam.reinforcement
    with pytest.raises((ValueError, TypeError)):
        beam.set_transverse_rebar(d_b=8 * mm, s_l=15 * cm, **options)
    assert beam.reinforcement == original


def test_legs_table_normalizes_without_changing_caller():
    original = pd.DataFrame({"legs": ["", 4], "ns": ["", 2]})
    output = normalize_leg_column(original)
    assert output.loc[1, "n_legs"] == 4
    assert output.loc[1, "legs"] == 4
    assert "n_legs" not in original


@pytest.mark.parametrize(
    "frame",
    [
        pd.DataFrame({"legs": ["", 7]}),
        pd.DataFrame({"legs": ["", 4], "n_legs": ["", 6]}),
        pd.DataFrame({"legs": ["mm", 4]}),
    ],
)
def test_invalid_legs_table_is_rejected(frame):
    with pytest.raises(ValueError):
        normalize_leg_column(frame)


def test_unchecked_section_has_two_pending_states():
    assert make_beam().verification_status == {"resistance": "pending", "detailing": "pending"}


def test_resistance_does_not_approve_failed_detailing():
    beam = make_beam()
    beam.set_transverse_rebar(legs=2, d_b=10 * mm, s_l=100 * cm)
    force = Forces(M_y=10 * kNm, V_z=1 * kN)
    beam.check_flexure([force])
    beam.check_shear([force])
    assert max(c.DCR for c in beam.shear_checks) < 1
    assert beam.verification_status["resistance"] == "passed"
    assert beam.verification_status["detailing"] == "failed"


@pytest.mark.parametrize(
    "operation",
    [
        "check_flexure",
        "check_shear",
        "flexure_check_results",
        "shear_check_results",
        "design_flexure",
        "design_shear",
        "design",
    ],
)
@pytest.mark.parametrize("axial", [-1, 1])
def test_en_footing_axial_is_rejected_before_modifying_reinforcement(operation, axial):
    beam = Footing(
        label="Z",
        concrete=Concrete_EN_1992_2004(name="C30", f_c=30 * MPa),
        steel_bar=SteelBar(name="B500", f_y=500 * MPa),
        width=100 * cm,
        height=50 * cm,
        c_c=50 * mm,
    )
    before = beam.reinforcement
    with pytest.raises(NotImplementedError, match="axial force"):
        getattr(beam, operation)([Forces(M_y=10 * kNm, N_x=axial * kN)])
    assert beam.reinforcement == before


def test_en_footing_axial_rejection_is_explained_in_spanish():
    language = get_language()
    try:
        set_language("es")
        beam = Footing(
            label="Z",
            concrete=Concrete_EN_1992_2004(name="C30", f_c=30 * MPa),
            steel_bar=SteelBar(name="B500", f_y=500 * MPa),
            width=100 * cm,
            height=50 * cm,
            c_c=50 * mm,
        )
        with pytest.raises(NotImplementedError, match="Todavía no se admite esfuerzo axial"):
            beam.check_flexure([Forces(N_x=1 * kN)])
    finally:
        set_language(language)


@pytest.mark.parametrize("operation", ["check_flexure", "check_shear", "flexure_check_results", "shear_check_results"])
def test_en_axial_rejection_checks_the_whole_list_before_replacing_results(operation):
    footing = Footing(
        label="Z",
        concrete=Concrete_EN_1992_2004(name="C30", f_c=30 * MPa),
        steel_bar=SteelBar(name="B500", f_y=500 * MPa),
        width=100 * cm,
        height=50 * cm,
        c_c=50 * mm,
    )
    accepted = Forces(label="Anterior", M_y=10 * kNm, V_z=1 * kN)
    getattr(footing, operation)([accepted])
    before = footing.flexure_checks, footing.shear_checks, footing.reinforcement
    with pytest.raises(NotImplementedError):
        getattr(footing, operation)([Forces(label="Parcial", M_y=20 * kNm), Forces(label="No soportada", N_x=1 * kN)])
    assert (footing.flexure_checks, footing.shear_checks, footing.reinforcement) == before
