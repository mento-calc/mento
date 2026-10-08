"""Compression requirement, alternate bars, two-sided clear gaps and scope."""

from dataclasses import replace

import matplotlib.pyplot as plt
import pytest

from mento import Concrete_ACI_318_19, Concrete_CIRSOC_201_25, Forces, RectangularBeam, SteelBar
from mento.compression_detailing import check_compression_detailing
from mento.units import MPa, cm, inch, kNm, ksi, mm, psi


def beam(code=Concrete_ACI_318_19, width=60):
    b = RectangularBeam(
        label="Compression",
        concrete=code(name="C25", f_c=25 * MPa),
        steel_bar=SteelBar(name="420", f_y=420 * MPa),
        width=width * cm,
        height=60 * cm,
        c_c=30 * mm,
    )
    b.set_longitudinal_rebar_bot(n1=4, d_b1=20 * mm)
    b.set_longitudinal_rebar_top(n1=5, d_b1=16 * mm)
    b.set_transverse_rebar(1, 10 * mm, 20 * cm)
    return b


def face_geometry(b, xs, supported):
    """Explicit closed-rectangle corners and bar chain for clause boundaries."""
    from mento.section_geometry import BarPosition, ClosedStirrup

    g = b.section_geometry
    # Ø16 bar + Ø10 stirrup: corner offset 25 mm (4*d_st bend).
    bars = tuple(BarPosition(x * mm, 547 * mm, 16 * mm, "top", 1, 1) for x in xs)
    stirrups = tuple(
        ClosedStirrup((0, 1), (xs[i] - 25) * mm, (xs[j] + 25) * mm, 35 * mm, 560 * mm, k == 0)
        for k, (i, j) in enumerate(supported)
    )
    return replace(
        g, bars=bars, mounting_bars=(), stirrups=stirrups, stirrup_bend_inner_diameter=40 * mm, stirrup_d_b=10 * mm
    )


def test_present_top_bars_do_not_activate_compression_support():
    b = beam()
    assert b.compression_detailing.status == "pending"
    b.check_flexure([Forces(M_y=10 * kNm)])
    assert b._compression_faces == set()
    assert b.compression_detailing.status == "not_required"
    assert not any(w.code.startswith("compression_detailing") for w in b.warnings)


def test_alternate_required_bars_need_additional_closed_corners():
    b = beam()
    b._compression_faces = {"top"}  # Isolate geometry; scope is tested separately.
    g = face_geometry(b, [60, 140, 220, 300, 380], [(0, 4)])
    failed = check_compression_detailing(b, g)
    assert failed.status == "failed"
    assert "alternate_bars_unbraced" in failed.faces[0].reasons
    g = face_geometry(b, [60, 140, 220, 300, 380], [(0, 4), (2, 4)])
    assert check_compression_detailing(b, g).status == "passed"


@pytest.mark.parametrize("gap,expected", [(150, "passed"), (150.01, "failed")])
def test_aci_clear_distance_includes_bar_radii_and_checks_both_sides(gap, expected):
    b = beam()
    b._compression_faces = {"top"}
    g = face_geometry(b, [60, 100, 100 + 16 + gap], [(0, 2)])
    result = check_compression_detailing(b, g)
    assert result.status == expected
    assert result.faces[0].maximum_clear_distance.to("mm").magnitude == pytest.approx(gap)


def test_cirsoc_disagreement_is_pending_and_exposes_both_limits():
    b = beam(Concrete_CIRSOC_201_25)
    b._compression_faces = {"top"}
    g = face_geometry(b, [60, 210, 360], [(0, 2)])
    # Ø8: corner offset20, vertical offset12; exact corner positions retained.
    bars = tuple(replace(bar, y=548 * mm) for bar in g.bars)
    stirrups = tuple(replace(s, x_left=40 * mm, x_right=380 * mm) for s in g.stirrups)
    g = replace(g, bars=bars, stirrups=stirrups, stirrup_d_b=8 * mm, stirrup_bend_inner_diameter=32 * mm)
    result = check_compression_detailing(b, g)
    assert result.status == "pending"
    assert tuple(limit.to("mm").magnitude for limit in result.faces[0].limits) == (120, 150)
    assert result.faces[0].maximum_clear_distance == 134 * mm
    assert result.faces[0].reasons == ("cirsoc_limit_interpretation",)


def test_second_row_cannot_be_silently_certified_by_first_row_support():
    b = beam()
    b._compression_faces = {"top"}
    g = face_geometry(b, [60, 160], [(0, 1)])
    second = replace(g.bars[0], x=110 * mm, y=500 * mm, layer=2)
    result = check_compression_detailing(b, replace(g, bars=g.bars + (second,)))
    assert result.status == "pending"
    assert "second_row_support_not_modelled" in result.faces[0].reasons


def test_missing_stirrups_fails_even_with_zero_shear():
    b = beam()
    b._compression_faces = {"top"}
    assert check_compression_detailing(b, replace(b.section_geometry, stirrups=())).status == "failed"


def test_aci_imperial_limit_is_six_inches_not_150_mm():
    b = RectangularBeam(
        label="US",
        concrete=Concrete_ACI_318_19(name="4000", f_c=4000 * psi),
        steel_bar=SteelBar(name="60", f_y=60 * ksi),
        width=24 * inch,
        height=24 * inch,
        c_c=1.5 * inch,
    )
    b._compression_faces = {"top"}
    g = face_geometry(b, [60, 160, 327], [(0, 2)])
    result = check_compression_detailing(b, g)
    assert result.status == "passed"  # 151 mm < 6 in, but >150 mm.
    assert result.faces[0].limits == (6 * inch,)


def test_required_faces_follow_real_positive_negative_and_reversal_checks():
    b = beam(width=30)
    b.set_longitudinal_rebar_bot(n1=4, d_b1=25 * mm)
    b.set_longitudinal_rebar_top(n1=4, d_b1=25 * mm)
    for moments, faces in (([600], {"top"}), ([-600], {"bot"}), ([600, -600], {"top", "bot"})):
        b.check_flexure([Forces(M_y=m * kNm) for m in moments])
        assert b._compression_faces == faces
        assert b.compression_detailing.status in ("failed", "pending")
        assert any(w.code.startswith("compression_detailing") for w in b.warnings)


def test_plot_labels_required_compression_support_without_mutating_strength():
    b = beam()
    b._compression_faces = {"top"}
    before = b.reinforcement
    fig = b.plot(show=False)
    assert b.compression_detailing.status == "passed"
    assert any("proposed legs; A_v uses" in t.get_text() for t in fig.axes[0].texts)
    assert b.reinforcement == before
    plt.close(fig)


def test_a_required_bar_outside_the_closed_perimeter_fails():
    b = beam()
    b._compression_faces = {"top"}
    g = face_geometry(b, [60, 160], [(0, 1)])
    g = replace(g, bars=g.bars + (replace(g.bars[0], x=10 * mm, layer=2),))
    result = check_compression_detailing(b, g)
    assert result.status == "failed"
    assert "bar_outside_closed_stirrup" in result.faces[0].reasons


def test_warning_status_and_reason_are_localized():
    from mento import set_language

    b = beam()
    b._compression_faces = {"top"}
    b.set_transverse_rebar(0, 0 * mm, 0 * cm)
    # Setting reinforcement resets results; identify required face afterwards.
    b._compression_faces = {"top"}
    try:
        set_language("es")
        warning = next(w for w in b.warnings if w.code == "compression_detailing_failed")
        assert "no tiene estribos cerrados" in warning.message
    finally:
        set_language("en")
