"""External SLS results must describe one current section, not shared preferences."""

from dataclasses import FrozenInstanceError

import pytest

from mento import (
    BeamSettings,
    Concrete_ACI_318_19,
    Concrete_EN_1992_2004,
    Forces,
    NotABeamError,
    RectangularBeam,
    ShearWall,
    SkinServiceCase,
    SteelBar,
)
from mento.units import MPa, cm, kNm, mm


def section(settings=None):
    b = RectangularBeam(
        label="S",
        concrete=Concrete_EN_1992_2004(name="C25", f_c=25 * MPa),
        steel_bar=SteelBar(name="B500", f_y=500 * MPa),
        width=30 * cm,
        height=120 * cm,
        c_c=30 * mm,
        settings=settings,
    )
    b.set_longitudinal_rebar_bot(n1=4, d_b1=20 * mm)
    b.set_longitudinal_rebar_top(n1=4, d_b1=20 * mm)
    b.set_transverse_rebar(1, 8 * mm, 20 * cm)
    b.check_flexure([Forces(M_y=100 * kNm), Forces(M_y=-80 * kNm)])
    return b


def cases():
    return [
        SkinServiceCase("frequent+", "bottom", 400 * MPa, 240 * mm),
        SkinServiceCase("frequent-", "top", 300 * MPa, 320 * mm),
    ]


def test_service_cases_accept_a_one_pass_iterable_without_losing_inputs():
    b = section()
    expected = cases()
    b.set_skin_service_cases(case for case in expected)
    assert b.skin_service_cases == tuple(expected)
    assert b.skin_reinforcement.status == "required"


def test_shared_preferences_do_not_share_service_cases():
    settings = BeamSettings()
    a, b = section(settings), section(settings)
    a.set_skin_service_cases(cases())
    assert a.settings is b.settings
    assert a.skin_reinforcement.status == "required"
    assert b.skin_reinforcement.status == "pending"
    assert b.skin_service_cases == ()


def test_service_quantities_are_copied_in_and_out():
    b = section()
    supplied = cases()
    b.set_skin_service_cases(supplied)
    supplied[0].steel_stress.ito("kPa")
    supplied.clear()
    exported = b.skin_service_cases
    assert str(exported[0].steel_stress.units) == "MPa"
    exported[0].steel_stress.ito("kPa")
    assert str(b.skin_service_cases[0].steel_stress.units) == "MPa"
    with pytest.raises(FrozenInstanceError):
        exported[0].label = "changed"


@pytest.mark.parametrize("change", ["bottom", "top", "stirrups", "design"])
def test_reinforcement_changes_invalidate_service_results_even_inside_design(change):
    b = section()
    b.set_skin_service_cases(cases())
    if change == "bottom":
        b.set_longitudinal_rebar_bot(n1=3, d_b1=20 * mm)
    elif change == "top":
        b.set_longitudinal_rebar_top(n1=3, d_b1=20 * mm)
    elif change == "stirrups":
        b.set_transverse_rebar(1, 10 * mm, 20 * cm)
    else:
        b.design([Forces(M_y=100 * kNm)])
    b.check_flexure([Forces(M_y=100 * kNm)])
    assert b.skin_service_cases == ()
    assert b.skin_reinforcement.status == "pending"
    assert b.skin_reinforcement.pending_reason == "service"


def test_readonly_recheck_does_not_discard_external_service_cases():
    b = section()
    b.set_skin_service_cases(cases())
    before = b.skin_service_cases
    b.check_flexure([Forces(M_y=90 * kNm), Forces(M_y=-70 * kNm)])
    assert b.skin_service_cases == before


def test_each_service_pair_is_checked_including_multiple_cases_on_one_face():
    b = section()
    supplied = cases() + [SkinServiceCase("rare+", "bottom", 450 * MPa, 800 * mm)]
    b.set_skin_service_cases(supplied)
    req = b.skin_reinforcement
    assert {r.combination for r in req.distribution_reviews} == {c.label for c in supplied}
    assert all(r.rows_per_side >= 2 for r in req.distribution_reviews)
    warnings = [w for w in b.warnings if w.code == "skin_distribution_review"]
    assert len(warnings) == 1
    assert set(warnings[0].combinations) == {c.label for c in supplied}


def test_duplicate_service_case_is_rejected():
    b = section()
    with pytest.raises(ValueError, match="Duplicate"):
        b.set_skin_service_cases([cases()[0], cases()[0]])


def test_material_change_does_not_reuse_service_reference():
    b = section()
    b.set_skin_service_cases(cases())
    b.steel_bar = SteelBar(name="B400", f_y=400 * MPa)
    assert b.skin_service_cases == ()


def test_wall_does_not_publish_beam_skin_results_or_service_inputs():
    wall = ShearWall(
        label="W",
        concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN420", f_y=420 * MPa),
        thickness=25 * cm,
        length=400 * cm,
        height=350 * cm,
        c_c=20 * mm,
    )
    for name in ("skin_reinforcement", "skin_service_cases"):
        assert not hasattr(wall, name)
        assert getattr(wall, name, None) is None
        with pytest.raises(NotABeamError):
            getattr(wall, name)
    with pytest.raises(NotABeamError):
        wall.set_skin_service_cases(cases())
