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
    # b has no cases of its own: it is checked with the assumed x = 0.4 * 1200 = 480 mm, not a's 240 / 320 mm.
    assert b.skin_reinforcement.status == "required"
    assert b.skin_service_cases == ()
    assert [z.combination for z in a.skin_reinforcement.check_zones] == ["frequent+", "frequent-"]
    assert [z.upper.to("mm").magnitude for z in a.skin_reinforcement.check_zones][0] == pytest.approx(960)
    assert [z.combination for z in b.skin_reinforcement.check_zones] == ["", ""]
    assert [z.upper.to("mm").magnitude for z in b.skin_reinforcement.check_zones][0] == pytest.approx(720)
    assert "skin_en_service_assumed" in [w.code for w in b.warnings]
    assert "skin_en_service_assumed" not in [w.code for w in a.warnings]


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
    # The discarded case no longer sets the zone: the assumed x = 0.4 * 1200 = 480 mm does (upper 720 mm).
    req = b.skin_reinforcement
    assert req.status == "required"
    assert req.pending_reason is None
    assert [(z.tension_face, z.combination) for z in req.check_zones] == [("bottom", "")]
    assert req.check_zones[0].upper.to("mm").magnitude == pytest.approx(720)
    assert "skin_en_service_assumed" in [w.code for w in b.warnings]


def test_readonly_recheck_does_not_discard_external_service_cases():
    b = section()
    b.set_skin_service_cases(cases())
    before = b.skin_service_cases
    b.check_flexure([Forces(M_y=90 * kNm), Forces(M_y=-70 * kNm)])
    assert b.skin_service_cases == before


def test_each_service_case_sets_the_zone_of_its_face():
    """frequent+ (bottom, x = 240): zone 48..960; frequent- (top, x = 320): zone 320..1152; no review warning."""
    b = section()
    b.set_skin_service_cases(cases())
    req = b.skin_reinforcement
    assert [
        (z.tension_face, z.combination, z.lower.to("mm").magnitude, z.upper.to("mm").magnitude) for z in req.check_zones
    ] == [
        ("bottom", "frequent+", pytest.approx(48), pytest.approx(960)),
        ("top", "frequent-", pytest.approx(320), pytest.approx(1152)),
    ]
    assert req.distribution_reviews == ()
    assert "skin_distribution_review" not in [w.code for w in b.warnings]


def test_each_service_pair_is_checked_including_multiple_cases_on_one_face():
    """rare+ (bottom, x = 800 mm, 450 MPa) adds a zone 48..400 mm holding only the row at 324 mm: one bar
    has to give 92.3 mm², so Ø12; and its stress caps the diameter at 16 * fct / 2.9 * 300 / (8 * 44) = 12.06 mm."""
    b = section()
    supplied = cases() + [SkinServiceCase("rare+", "bottom", 450 * MPa, 800 * mm)]
    b.set_skin_service_cases(supplied)
    req = b.skin_reinforcement
    assert {z.combination for z in req.check_zones} == {c.label for c in supplied}
    assert req.d_b == 12 * mm
    fct = 0.3 * 25 ** (2 / 3)
    assert req.diameter_max.to("mm").magnitude == pytest.approx(16 * fct / 2.9 * 300 / (8 * 44))


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
