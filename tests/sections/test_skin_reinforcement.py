"""Code boundaries, sign envelopes, actual spacing, supplementary steel and fit."""

import math
import warnings

import matplotlib.pyplot as plt
import pytest

from mento import (
    BeamSettings,
    CageDetailingError,
    Concrete_ACI_318_19,
    Concrete_CIRSOC_201_25,
    Concrete_EN_1992_2004,
    Forces,
    RectangularBeam,
    SteelBar,
    set_language,
)
from mento.units import MPa, cm, inch, kNm, ksi, mm, psi


def beam(height=120 * cm, concrete=None, cover=30 * mm, width=30 * cm, steel=None):
    b = RectangularBeam(
        label="Skin",
        concrete=concrete or Concrete_CIRSOC_201_25(name="H25", f_c=25 * MPa),
        steel_bar=steel or SteelBar(name="ADN420", f_y=420 * MPa),
        width=width,
        height=height,
        c_c=cover,
    )
    b.set_longitudinal_rebar_bot(n1=4, d_b1=20 * mm)
    b.set_longitudinal_rebar_top(n1=4, d_b1=20 * mm)
    b.set_transverse_rebar(1, 8 * mm, 20 * cm)
    return b


def plot_quietly(b):
    """The drawing, failing on any UserWarning: what is pending or unsupported lives in beam.warnings."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        return b.plot(show=False)


def zones(r):
    """The check zones as (face, lower mm, upper mm), rounded to 1e-6 mm."""
    return [
        (z.tension_face, round(z.lower.to("mm").magnitude, 6), round(z.upper.to("mm").magnitude, 6))
        for z in r.check_zones
    ]


@pytest.mark.parametrize("height,required", [(899, False), (900, False), (901, True)])
def test_metric_strict_depth_boundary(height, required):
    """CIRSOC requires skin only above 900 mm; at 900 mm and below, from 60 cm, mento proposes it and draws it too."""
    b = beam(height * mm)
    b.check_flexure([Forces(M_y=100 * kNm)])
    assert b.skin_reinforcement.status == ("required" if required else "proposed")
    assert b.detailing_geometry.skin_bars


@pytest.mark.parametrize("height,required", [(36, False), (36.01, True)])
def test_imperial_boundary_and_number_three(height, required):
    b = RectangularBeam(
        label="US",
        concrete=Concrete_ACI_318_19(name="4000", f_c=4000 * psi),
        steel_bar=SteelBar(name="60", f_y=60 * ksi),
        width=12 * inch,
        height=height * inch,
        c_c=1.5 * inch,
    )
    b.set_longitudinal_rebar_bot(n1=4, d_b1=0.75 * inch)
    b.set_longitudinal_rebar_top(n1=4, d_b1=0.75 * inch)
    b.set_transverse_rebar(1, 0.375 * inch, 8 * inch)
    b.check_flexure([Forces(M_y=100 * kNm)])
    r = b.skin_reinforcement
    assert (r.status == "required") == required
    if required:
        assert r.d_b.to("in").magnitude == pytest.approx(0.375)
        assert r.s_max.to("in").magnitude == pytest.approx(15 - 2.5 * 1.875)
        assert b.detailing_geometry.skin_bars


@pytest.mark.parametrize("moments,faces", [([100], ("bottom",)), ([-100], ("top",)), ([100, -80], ("bottom", "top"))])
def test_each_tension_half_and_reversal_envelope(moments, faces):
    """The rows span the whole height whatever face is in tension; only the check zones follow the sign.

    Layers Ø20 at 30 + 8 + 10 = 48 mm and 1200 - 48 = 1152 mm; s_max = 380 - 2.5 * 38 = 285 mm;
    n = ceil(1104 / 285) - 1 = 3 rows at 48 + 276 i. From 1 m the area of Eq. (7.1) is
    0.2 * 0.30 * 25^(2/3) * 300 * 1200 / 2 / 420 / 2 = 109.9 mm² per side; two rows fall in each
    zone (bottom 48..720, top 480..1152, x = 0.4 h), so Ø8 (100.5 mm²) falls short and Ø10 is used.
    """
    b = beam()
    b.check_flexure([Forces(M_y=m * kNm) for m in moments])
    original = b.section_geometry
    reinforcement, flexure = b.reinforcement, b.flexure_design
    r = b.skin_reinforcement
    g = b.detailing_geometry
    assert r.tension_faces == faces
    assert r.s_max.to("mm").magnitude == pytest.approx(285)  # side cover 30+8
    assert r.n_per_side == 3
    assert r.d_b == 10 * mm
    expected = {"bottom": (48, 720), "top": (480, 1152)}
    assert zones(r) == [(face, *expected[face]) for face in faces]
    assert len(g.skin_bars) == 2 * r.n_per_side
    for side in ("left", "right"):
        ys = sorted(x.y.to("mm").magnitude for x in g.skin_bars if x.face == side)
        assert len(ys) == len(set(ys))
        assert ys == pytest.approx([324, 600, 876])
        assert all(y2 - y1 <= r.s_max.to("mm").magnitude for y1, y2 in zip(ys, ys[1:]))
    assert b.section_geometry == original
    assert not original.skin_bars
    assert b.reinforcement == reinforcement
    assert b.flexure_design == flexure
    assert len(g.bars_on("bottom")) == 4
    exported = g.to_dict("in")["skin_bars"]
    assert exported[0]["d_b"] == pytest.approx(10 / 25.4)


def test_unchecked_deep_beam_and_zero_moment():
    b = beam()
    assert b.skin_reinforcement.status == "pending"
    assert not b.detailing_geometry.skin_bars
    set_language("es")
    fig = plot_quietly(b)
    # Pending skin is a warning of the beam; the drawing writes no note about it.
    assert "skin_reinforcement_pending" in [w.code for w in b.warnings]
    assert not any("Armadura de piel pendiente" in text.get_text() for text in fig.axes[0].texts)
    assert not any(p.get_gid() == "skin_bar" for p in fig.axes[0].patches)
    plt.close(fig)
    set_language("en")
    b.check_flexure([Forces(M_y=0 * kNm)])
    assert b.skin_reinforcement.status == "pending"
    assert b.skin_reinforcement.pending_reason == "no_tension_case"
    assert "skin_tension_case_pending" in [w.code for w in b.warnings]
    assert not b.detailing_geometry.skin_bars


def test_en_zero_moment_stays_pending():
    b = en_beam()
    b.check_flexure([Forces(M_y=0 * kNm)])
    assert b.skin_reinforcement.status == "pending"
    assert b.skin_reinforcement.pending_reason == "no_tension_case"
    assert "skin_tension_case_pending" in [w.code for w in b.warnings]
    fig = plot_quietly(b)
    assert not any("no tension case identified" in text.get_text() for text in fig.axes[0].texts)
    assert not any("no flexure verification" in text.get_text() for text in fig.axes[0].texts)
    assert not any(p.get_gid() == "skin_bar" for p in fig.axes[0].patches)
    plt.close(fig)


def test_en_pure_axial_is_unsupported():
    from mento.units import kN

    b = en_beam()
    b.check_flexure([Forces(N_x=100 * kN, M_y=0 * kNm)])
    assert b.skin_reinforcement.status == "unsupported"
    assert b.skin_reinforcement.pending_reason == "axial"
    assert "skin_en_axial_unsupported" in [w.code for w in b.warnings]


def test_diameter_is_configurable_and_not_a_code_minimum():
    """Below 1 m the skin is the smallest catalogue bar from skin_bar_diameter: Ø8 on a 30 cm web by default, Ø10 at 10 mm."""
    b = beam(height=80 * cm)
    b.check_flexure([Forces(M_y=100 * kNm)])
    assert {bar.d_b.to("mm").magnitude for bar in b.detailing_geometry.skin_bars} == {8}
    b.settings.skin_bar_diameter = 10 * mm
    assert {bar.d_b.to("mm").magnitude for bar in b.detailing_geometry.skin_bars} == {10}
    assert BeamSettings().skin_bar_diameter == 8 * mm
    assert BeamSettings(unit_system="imperial").skin_bar_diameter == 0.375 * inch


@pytest.mark.parametrize("diameter", [0 * mm, math.nan * mm, 7 * mm, 10])
def test_invalid_skin_preference_is_rejected_with_labelled_plot_fallback(diameter):
    """The plot falls back to the base cage with no skin; the invalid input is reported in beam.warnings."""
    b = beam()
    b.settings.skin_bar_diameter = diameter
    b.check_flexure([Forces(M_y=100 * kNm)])
    with pytest.raises(CageDetailingError):
        _ = b.detailing_geometry
    fig = plot_quietly(b)
    assert "skin_detailing_invalid" in [w.code for w in b.warnings]
    assert not any(p.get_gid() == "skin_bar" for p in fig.axes[0].patches)
    assert not any("Skin proposal not shown" in t.get_text() for t in fig.axes[0].texts)
    plt.close(fig)


def test_invalid_skin_keeps_valid_mounting_steel_in_the_plot():
    b = beam(width=60 * cm)
    b.set_longitudinal_rebar_top(n1=0, d_b1=0 * mm)
    b.check_flexure([Forces(M_y=100 * kNm)])
    b.settings.skin_bar_diameter = 0 * mm
    fig = plot_quietly(b)
    assert "skin_detailing_invalid" in [w.code for w in b.warnings]
    assert any(p.get_gid() == "mounting_bar" for p in fig.axes[0].patches)
    assert "2Ø8 (mounting)" in [t.get_text() for t in fig.axes[0].texts]
    assert not any(p.get_gid() == "skin_bar" for p in fig.axes[0].patches)
    assert not any("Calculation model only" in t.get_text() for t in fig.axes[0].texts)
    plt.close(fig)


def test_a_base_cage_failure_is_not_reported_as_a_skin_failure():
    b = beam(width=60 * cm)
    b.set_transverse_rebar(1, 40 * mm, 20 * cm)
    b.check_flexure([Forces(M_y=100 * kNm)])
    codes = [warning.code for warning in b.warnings]
    assert "cage_detailing_pending" in codes
    assert "skin_detailing_infeasible" not in codes


def test_skin_cap_uses_actual_side_cover_without_rejecting_feasible_high_cover():
    """c_c 80: s_max = 380 - 2.5 * 88 = 160 mm; layers at 98 and 1102 mm, n = ceil(1004 / 160) - 1 = 6.

    c_c 110: s_max = 380 - 2.5 * 118 = 85 mm; layers at 128 and 1072 mm, n = ceil(944 / 85) - 1 = 11.
    """
    b = beam(cover=80 * mm, width=50 * cm)
    b.check_flexure([Forces(M_y=100 * kNm)])
    assert b.skin_reinforcement.s_max.to("mm").magnitude == pytest.approx(160)
    assert b.skin_reinforcement.n_per_side == 6
    assert b.skin_reinforcement.spacing.to("mm").magnitude == pytest.approx(1004 / 7)
    assert b.detailing_geometry.skin_bars
    b = beam(cover=110 * mm, width=50 * cm)
    b.check_flexure([Forces(M_y=100 * kNm)])
    assert b.skin_reinforcement.s_max.to("mm").magnitude == pytest.approx(85)
    assert b.skin_reinforcement.n_per_side == 11
    assert b.skin_reinforcement.spacing.to("mm").magnitude == pytest.approx(944 / 12)
    assert b.detailing_geometry.skin_bars


def test_no_stirrups_still_supplies_skin_and_leaves_shear_unchanged():
    b = beam()
    b.set_transverse_rebar()
    b.check_flexure([Forces(M_y=100 * kNm)])
    g = b.detailing_geometry
    assert not g.stirrups
    assert g.skin_bars
    assert not g.mounting_bars


def test_plot_has_separate_skin_artists_and_notation():
    b = beam()
    b.check_flexure([Forces(M_y=100 * kNm), Forces(M_y=-80 * kNm)])
    fig = b.plot()
    assert len([p for p in fig.axes[0].patches if p.get_gid() == "skin_bar"]) == 6
    assert len([p for p in fig.axes[0].patches if p.get_gid() == "resistant_bar"]) == 8
    texts = [t.get_text() for t in fig.axes[0].texts]
    # One label on the right, beside the skin bars; no "Skin: ... · s=..." line under the section.
    assert "3Ø10 per side (skin)" in texts
    assert not any(t.startswith("Skin:") for t in texts)
    plt.close(fig)


def test_skin_grid_starts_after_the_lateral_second_layer_instead_of_clashing_with_it():
    b = beam(cover=40 * mm, width=40 * cm, steel=SteelBar(name="ADN500", f_y=500 * MPa))
    b.set_transverse_rebar(1, 10 * mm, 20 * cm)
    b.set_longitudinal_rebar_bot(n1=4, d_b1=25 * mm, n3=2, d_b3=25 * mm)
    b.check_flexure([Forces(M_y=100 * kNm)])
    before = b.reinforcement
    # Layer 1 Ø25 at 40 + 10 + 12.5 = 62.5 mm, layer 2 a 25 mm gap and a bar above: 112.5 mm.
    assert [bar.y.to(mm).magnitude for bar in b.section_geometry.bars_on("bottom", layer=2)] == pytest.approx(
        [112.5, 112.5]
    )
    # Top Ø20 at 1200 - 60 = 1140 mm; fs = 2/3 * 500, s_max = 380 * 280 / fs - 2.5 * 50 = 194.2 mm,
    # n = ceil(1027.5 / 194.2) - 1 = 5 rows, 1027.5 / 6 = 171.25 mm apart, from the second layer up.
    ys = [bar.y.to(mm).magnitude for bar in b.detailing_geometry.skin_bars if bar.face == "left"]
    assert ys == pytest.approx([112.5 + 171.25 * i for i in range(1, 6)])
    assert b.reinforcement == before


def test_aci_ground_cover_can_have_a_feasible_uniform_skin_grid():
    """s_max = 380 - 2.5 * (75 + 12) = 162.5 mm; layers at 75 + 12 + 12.5 = 99.5 and 1000 - 97 = 903 mm.

    n = ceil(803.5 / 162.5) - 1 = 4 rows, 160.7 mm apart. Area of Eq. (7.1) at 1 m:
    0.2 * 2.565 * 600 * 1000 / 2 / 420 / 2 = 183.2 mm²; three rows below 600 mm (x = 0.4 h):
    Ø8 gives 150.8 mm², Ø10 235.6 mm².
    """
    b = beam(height=100 * cm, cover=75 * mm, width=60 * cm, concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa))
    b.set_transverse_rebar(1, 12 * mm, 20 * cm)
    b.set_longitudinal_rebar_bot(n1=4, d_b1=25 * mm)
    b.check_flexure([Forces(M_y=100 * kNm)])
    assert b.skin_reinforcement.status == "required"
    assert b.skin_reinforcement.d_b == 10 * mm
    ys = [bar.y.to(mm).magnitude for bar in b.detailing_geometry.skin_bars if bar.face == "left"]
    assert ys == pytest.approx([99.5 + 803.5 / 5 * i for i in range(1, 5)])


def test_en_without_service_inputs_uses_mento_assumptions():
    """The service data is mento's: x = 0.4 h and sigma_s = 0.6 f_yk, with no notice of its own.

    Rows: skin_bar_spacing 280 mm, n = ceil(1104 / 280) - 1 = 3 at 324, 600, 876 mm. Zone 48..720 mm
    holds two; Eq. (7.1) gives 0.2 * 2.565 * 300 * 1200 / 2 / 420 / 2 = 109.9 mm², so Ø10.
    Cap: 0.6 * 420 = 252 MPa, half 126 -> phi* = 32 mm (Table 7.2N, 0.3 mm); the web as a tie
    governs, 32 * fct / 2.9 * 300 / (8 * (38 + 5)) = 24.68 mm.
    """
    b = beam(concrete=Concrete_EN_1992_2004(name="C25", f_c=25 * MPa))
    b.check_flexure([Forces(M_y=100 * kNm)])
    r = b.skin_reinforcement
    assert r.status == "required"
    assert r.pending_reason is None
    assert r.n_per_side == 3 and r.d_b == 10 * mm
    assert [y.to("mm").magnitude for y in r.rows] == pytest.approx([324, 600, 876])
    assert zones(r) == [("bottom", 48, 720)]
    fct = 0.3 * 25 ** (2 / 3)
    assert r.area_min_per_side.to("mm**2").magnitude == pytest.approx(0.4 * 0.5 * fct * 300 * 1200 / 2 / 420 / 2)
    assert r.diameter_max.to("mm").magnitude == pytest.approx(32 * fct / 2.9 * 300 / (8 * 43))
    assert len(b.detailing_geometry.skin_bars) == 6
    assert not any("service" in w.code for w in b.warnings)


def test_recheck_and_rebar_change_do_not_keep_old_tension_faces():
    b = beam()
    b.check_flexure([Forces(M_y=100 * kNm), Forces(M_y=-80 * kNm)])
    b.check_flexure([Forces(M_y=-80 * kNm)])
    assert b.skin_reinforcement.tension_faces == ("top",)
    b.set_longitudinal_rebar_bot(n1=3, d_b1=20 * mm)
    assert b.skin_reinforcement.status == "pending"


def test_requirement_is_reported_beside_strength_and_in_spanish():
    b = beam()
    assert "skin_reinforcement_pending" in [w.code for w in b.warnings]
    b.check_flexure([Forces(M_y=100 * kNm)])
    assert b.flexure_design.DCR < 1
    set_language("es")
    warning = next(w for w in b.warnings if w.code == "skin_reinforcement_required")
    assert "ambos laterales" in warning.message
    assert warning.values["s_max"].to("mm").magnitude == pytest.approx(285)
    set_language("en")


@pytest.mark.parametrize("height,required", [(900, False), (901, True)])
def test_aci_metric_edition_depth_boundary(height, required):
    b = beam(height * mm, concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa))
    b.check_flexure([Forces(M_y=100 * kNm)])
    assert (b.skin_reinforcement.status == "required") == required


def test_empty_force_list_does_not_establish_a_tension_face():
    b = beam()
    b.flexure_check_results([])
    assert b.skin_reinforcement.status == "pending"


def test_cirsoc_skin_equation_is_si_with_imperial_length_inputs():
    b = beam(height=48 * inch, cover=1.5 * inch)
    b.check_flexure([Forces(M_y=100 * kNm)])
    assert b.skin_reinforcement.threshold.to("mm").magnitude == 900
    assert b.skin_reinforcement.s_max.to("mm").magnitude == pytest.approx(380 - 2.5 * (38.1 + 8))


def en_beam(height=1200 * mm, fy=500 * MPa):
    return beam(
        height=height, concrete=Concrete_EN_1992_2004(name="C25", f_c=25 * MPa), steel=SteelBar(name="B500", f_y=fy)
    )


@pytest.mark.parametrize("height,required", [(999, False), (1000, True), (1001, True)])
def test_en_inclusive_one_metre_boundary(height, required):
    """EN requires skin from 1 m inclusive; just below, mento still proposes and draws it."""
    b = en_beam(height * mm)
    b.check_flexure([Forces(M_y=100 * kNm)])
    assert b.skin_reinforcement.status == ("required" if required else "proposed")
    assert b.detailing_geometry.skin_bars


@pytest.mark.parametrize("height, rows, pitch", [(1000, 3, 226), (1200, 3, 276)])
def test_en_automatic_layout_spans_the_height_without_a_distribution_review(height, rows, pitch):
    """Layers at 48 mm and h - 48 mm, skin_bar_spacing 280 mm: n = ceil((h - 96) / 280) - 1.

    h = 1000: n = ceil(904 / 280) - 1 = 3, 904 / 4 = 226 mm apart; h = 1200: ceil(1104 / 280) - 1 = 3, 276 mm.
    Eq. (7.1): 0.2 * 2.565 * 300 * h / 2 / 500 / 2 = 76.9 / 92.3 mm², met by the three Ø8 (150.8 mm²)
    inside the zone up to h - 240 mm; Ø8 is within the cap 25 * fct / 2.9 * 300 / (8 * 42) = 19.7 mm.
    """
    b = en_beam(height * mm)
    b.check_flexure([Forces(M_y=100 * kNm)])
    before = b.skin_reinforcement
    geometry = b.detailing_geometry
    assert before.n_per_side == rows
    assert before.d_b == 8 * mm
    assert before.spacing.to("mm").magnitude == pytest.approx(pitch)
    assert [y.to("mm").magnitude for y in before.rows] == pytest.approx([48 + pitch * i for i in range(1, rows + 1)])
    assert before.distribution_reviews == ()
    assert len(geometry.skin_bars) == 2 * rows
    try:
        for language in ("en", "es"):
            set_language(language)
            assert "skin_distribution_review" not in [w.code for w in b.warnings]
            assert b.skin_reinforcement == before
            assert b.detailing_geometry == geometry
            fig = plot_quietly(b)
            labels = [text.get_text() for text in fig.axes[0].texts]
            # The drawing only labels the skin it proposes.
            skin = f"{rows}Ø8 per side (skin)" if language == "en" else f"{rows}Ø8 por lateral (piel)"
            assert skin in labels
            assert not any(("Review skin" if language == "en" else "Revisar piel") in text for text in labels)
            assert not any(
                ("crack width is not calculated" if language == "en" else "no se calcula el ancho de fisura") in text
                for text in labels
            )
            plt.close(fig)
    finally:
        set_language("en")


def test_en_minimum_and_diameter_route_use_characteristic_strength_and_half_service_stress():
    b = en_beam()
    b.check_flexure([Forces(M_y=100 * kNm)])
    r = b.skin_reinforcement
    fct = 0.3 * 25 ** (2 / 3)
    assert r.area_min_per_side.to("mm**2").magnitude == pytest.approx(0.4 * 0.5 * fct * 300 * 1200 / 2 / 500 / 2)
    # Main sigma = 0.6 * 500 = 300 -> skin sigma = 150 -> Table 7.2N phi* = 32 mm.
    # Conservative web-as-tie interpretation: 300mm width and actual skin
    # centroid 30+8+4 = 42mm from the side (the Ø8 chosen). Hand-evaluated
    # Eq. (7.7N), not the bending-depth interpretation.
    assert r.diameter_max.to("mm").magnitude == pytest.approx(32 * fct / 2.9 * 300 / (8 * 42))
    assert r.diameter_max.to("mm").magnitude == pytest.approx(25.27058, abs=0.0001)
    assert r.d_b == 8 * mm
    assert r.n_per_side == 3
    assert r.area_per_side >= r.area_min_per_side
    # EN prints no spacing: mento's skin_bar_spacing sets the count.
    assert r.s_max == b.settings.skin_bar_spacing == 280 * mm
    ys = [bar.y.to("mm").magnitude for bar in b.detailing_geometry.skin_bars if bar.face == "left"]
    assert ys == pytest.approx([324, 600, 876])  # evenly between the layers at 48 and 1152 mm.
    assert r.spacing.to("mm").magnitude == pytest.approx(276)


@pytest.mark.parametrize("moments", [[100], [-100], [100, -80]])
def test_en_sign_envelope_preserves_resistant_model(moments):
    b = en_beam()
    b.check_flexure([Forces(M_y=m * kNm) for m in moments])
    original, checks, resistant = b.section_geometry, b.flexure_checks, b.reinforcement
    r = b.skin_reinforcement
    g = b.detailing_geometry
    assert len(g.skin_bars) == 2 * r.n_per_side
    assert b.section_geometry == original and not original.skin_bars
    assert b.flexure_checks == checks and b.reinforcement == resistant
    assert len({round(bar.y.to("mm").magnitude, 8) for bar in g.skin_bars}) == r.n_per_side


def test_en_reversal_zones_each_receive_minimum_area():
    """x = 0.4 * 1200 = 480 mm both ways: zones 48..720 and 480..1152 mm hold two of the rows 324, 600, 876 each.

    Two bars per zone have to give 92.3 mm²: Ø8 (100.5) does.
    """
    b = en_beam()
    b.check_flexure([Forces(M_y=100 * kNm), Forces(M_y=-80 * kNm)])
    r = b.skin_reinforcement
    assert r.d_b == 8 * mm
    assert zones(r) == [("bottom", 48, 720), ("top", 480, 1152)]
    ys = [bar.y.to("mm").magnitude for bar in b.detailing_geometry.skin_bars if bar.face == "left"]
    assert ys == pytest.approx([324, 600, 876])
    abar = math.pi * 8**2 / 4
    for low, high in [(48, 720), (480, 1152)]:
        assert sum(low <= y <= high for y in ys) == 2
        assert sum(low <= y <= high for y in ys) * abar >= r.area_min_per_side.to("mm**2").magnitude


def test_en_rejects_a_crack_width_outside_table_7_2n():
    b = en_beam()
    b.settings.skin_crack_width = 0.25 * mm
    b.check_flexure([Forces(M_y=100 * kNm)])
    with pytest.raises(ValueError, match="skin_crack_width must be 0.2, 0.3 or 0.4 mm"):
        _ = b.skin_reinforcement


@pytest.mark.parametrize("crack_width, phi_star", [(0.3, 25), (0.2, 16)])
def test_en_rounds_service_stress_up_and_applies_crack_width_selection(crack_width, phi_star):
    """f_yk = 600: sigma_s = 0.6 * 600 = 360, half 180, read in the 200 MPa row of Table 7.2N, not interpolated."""
    b = en_beam(fy=600 * MPa)
    b.settings.skin_crack_width = crack_width * mm
    b.check_flexure([Forces(M_y=100 * kNm)])
    r = b.skin_reinforcement
    fct = 0.3 * 25 ** (2 / 3)
    assert r.d_b == 8 * mm
    assert r.diameter_max.to("mm").magnitude == pytest.approx(phi_star * fct / 2.9 * 300 / (8 * 42))


def test_en_axial_envelope_is_explicitly_unsupported_and_can_be_rechecked():
    from mento.units import kN

    b = en_beam()
    b.check_flexure([Forces(M_y=100 * kNm, N_x=10 * kN), Forces(M_y=-80 * kNm)])
    assert b.skin_reinforcement.status == "unsupported"
    assert "skin_en_axial_unsupported" in [w.code for w in b.warnings]
    assert not b.detailing_geometry.skin_bars
    b.check_flexure([Forces(M_y=100 * kNm)])
    assert b.skin_reinforcement.status == "required"


def test_en_annex_j_cover_warning_is_independent_of_one_metre_threshold():
    b = beam(height=800 * mm, width=500 * mm, cover=80 * mm, concrete=Concrete_EN_1992_2004(name="C25", f_c=25 * MPa))
    # 80 cm: mento's criterion waits for flexure, then proposes skin; EN itself requires none below 1 m.
    assert b.skin_reinforcement.status == "pending"
    assert b.skin_reinforcement.threshold == 1000 * mm
    assert "skin_en_surface_pending" in [w.code for w in b.warnings]
    b.check_flexure([Forces(M_y=100 * kNm)])
    assert b.skin_reinforcement.status == "proposed"
    codes = [w.code for w in b.warnings]
    assert "skin_en_surface_pending" in codes
    assert "skin_en_required" not in codes


def test_en_service_assumption_raises_no_notice_and_is_not_written_on_the_drawing():
    b = en_beam()
    b.check_flexure([Forces(M_y=100 * kNm)])
    assert not any("service" in w.code for w in b.warnings)
    assert not hasattr(b, "set_skin_service_cases")
    fig = plot_quietly(b)
    assert not any("assum" in t.get_text() for t in fig.axes[0].texts)
    # The skin is laid out and drawn with the assumptions: 3 rows per side.
    assert sum(p.get_gid() == "skin_bar" for p in fig.axes[0].patches) == 6
    plt.close(fig)


@pytest.mark.parametrize("moments,zone", [([100], ("bottom", 48, 720)), ([-100], ("top", 480, 1152))])
def test_en_check_zone_follows_the_bending_sign(moments, zone):
    """The zone runs from the tension layer to the assumed axis, x = 0.4 * 1200 = 480 mm from the compression face."""
    b = en_beam()
    b.check_flexure([Forces(M_y=m * kNm) for m in moments])
    r = b.skin_reinforcement
    assert zones(r) == [zone]
    ys = [bar.y.to("mm").magnitude for bar in b.detailing_geometry.skin_bars if bar.face == "left"]
    assert ys == pytest.approx([324, 600, 876])


def test_en_readonly_check_retains_axial_scope_without_mutating_section():
    from mento.units import kN

    b = en_beam()
    b.flexure_check_results([Forces(M_y=100 * kNm, N_x=10 * kN)])
    assert b.flexure_checks[0].has_axial_force
    assert b.skin_reinforcement.status == "unsupported"


def test_en_slab_strip_does_not_take_beam_surface_warnings():
    from mento import OneWaySlab

    b = OneWaySlab(
        label="Slab",
        concrete=Concrete_EN_1992_2004(name="C25", f_c=25 * MPa),
        steel_bar=SteelBar(name="B500", f_y=500 * MPa),
        width=1000 * mm,
        height=800 * mm,
        c_c=80 * mm,
    )
    assert b.skin_reinforcement.status == "not_applicable"
    assert "skin_en_surface_pending" not in [w.code for w in b.warnings]


def test_en_annex_j_is_not_hidden_by_invalid_skin_inputs_and_keeps_the_cause():
    b = en_beam()
    b.c_c = 80 * mm
    b.settings.skin_crack_width = 0.25 * mm
    b.check_flexure([Forces(M_y=100 * kNm)])
    warnings = {w.code: w for w in b.warnings}
    assert "skin_en_surface_pending" in warnings
    assert "skin_detailing_invalid" in warnings
    assert "skin_crack_width" in warnings["skin_detailing_invalid"].values["reason"]


def test_en_annex_j_uses_cover_outside_the_links_not_the_sum_with_their_diameter():
    b = beam(height=800 * mm, width=50 * cm, cover=68 * mm, concrete=Concrete_EN_1992_2004(name="C25", f_c=25 * MPa))
    assert "skin_en_surface_pending" not in [w.code for w in b.warnings]


def test_en_axial_case_has_an_explicit_unsupported_plot_caption():
    """The unsupported axial case is explicit in beam.warnings; the drawing shows no skin and no caption."""
    from mento.units import kN

    b = en_beam()
    b.check_flexure([Forces(M_y=100 * kNm, N_x=10 * kN)])
    assert b.skin_reinforcement.status == "unsupported"
    assert "skin_en_axial_unsupported" in [w.code for w in b.warnings]
    fig = plot_quietly(b)
    assert not any("Skin not checked" in t.get_text() for t in fig.axes[0].texts)
    assert not any(p.get_gid() == "skin_bar" for p in fig.axes[0].patches)
    plt.close(fig)


def test_skin_collision_keeps_the_base_cage_mounting():
    """skin_bar_spacing 30 mm packs ceil(680 / 30) - 1 = 22 rows 29.6 mm apart (layers at 60 and 740 mm),
    closer than a Ø10 and the 30 mm vibrator: the skin is infeasible, the base cage and its mounting are not."""
    from mento.cage_detailing import build_cage_detailing

    b = beam(
        height=80 * cm,
        width=60 * cm,
        concrete=Concrete_EN_1992_2004(name="C25", f_c=25 * MPa),
        steel=SteelBar(name="B500", f_y=500 * MPa),
    )
    b.set_longitudinal_rebar_top(n1=0, d_b1=0 * mm)
    b.set_transverse_rebar(1, 20 * mm, 20 * cm)
    b.check_flexure([Forces(M_y=100 * kNm)])
    b.settings.skin_bar_spacing = 30 * mm
    assert b.skin_reinforcement.n_per_side == 22
    base = build_cage_detailing(b, include_skin=False)
    assert len(base.mounting_bars) == 2
    with pytest.raises(CageDetailingError) as raised:
        b.detailing_geometry
    assert raised.value.reason == "skin"
    codes = [w.code for w in b.warnings]
    assert "skin_detailing_infeasible" in codes
    assert "cage_detailing_infeasible" not in codes
    fig = plot_quietly(b)
    assert sum(p.get_gid() == "mounting_bar" for p in fig.axes[0].patches) == 2
    assert not any(p.get_gid() == "skin_bar" for p in fig.axes[0].patches)
    plt.close(fig)


@pytest.mark.parametrize("height", [80, 120])
def test_base_cage_warning_does_not_depend_on_required_skin(height):
    b = beam(height=height * cm)
    b.set_transverse_rebar(1, 40 * mm, 20 * cm)
    b.check_flexure([Forces(M_y=100 * kNm)])
    assert "cage_detailing_pending" in [w.code for w in b.warnings]


@pytest.mark.parametrize("cover,diameter,pending", [(70, 32, False), (71, 32, True), (70, 40, True)])
def test_en_surface_review_strict_thresholds(cover, diameter, pending):
    from mento.codes.en_1992_2004.skin import warnings as en_warnings

    b = beam(height=80 * cm, cover=cover * mm, concrete=Concrete_EN_1992_2004(name="C25", f_c=25 * MPa))
    b.set_longitudinal_rebar_bot(n1=2, d_b1=diameter * mm)
    codes = [w.code for w in en_warnings(b, None)]
    assert ("skin_en_surface_pending" in codes) is pending


def test_invalid_skin_settings_do_not_hide_a_base_cage_failure():
    b = beam()
    b.set_transverse_rebar(1, 40 * mm, 20 * cm)
    b.check_flexure([Forces(M_y=100 * kNm)])
    b.settings.skin_bar_diameter = 0 * mm
    codes = [w.code for w in b.warnings]
    assert "skin_detailing_invalid" in codes
    assert "cage_detailing_pending" in codes


# ---------------------------------------------------------------------------
# mento's skin criterion: the agreed table of rows per side and diameters
# ---------------------------------------------------------------------------

CRITERION_WIDTHS = (20, 30, 40, 50, 60, 100)

#: h (cm) -> (status, rows per side, diameter (mm) for each of CRITERION_WIDTHS); None: no skin.
EN_CRITERION = {
    50: None,
    60: ("proposed", 1, (8, 8, 8, 10, 10, 10)),
    80: ("proposed", 2, (8, 8, 8, 10, 10, 10)),
    100: ("required", 3, (8, 8, 10, 10, 12, 16)),
    120: ("required", 3, (8, 10, 10, 12, 12, 16)),
}
ACI_CRITERION = {
    60: ("proposed", 1, (8, 8, 8, 10, 10, 10)),
    90: ("proposed", 2, (8, 8, 8, 10, 10, 10)),
    100: ("required", 3, (8, 10, 10, 12, 12, 16)),
    120: ("required", 3, (8, 10, 12, 12, 16, 20)),
}


def en_materials():
    return Concrete_EN_1992_2004(name="C30/37", f_c=30 * MPa), SteelBar(name="B500S", f_y=500 * MPa)


def aci_materials():
    return Concrete_ACI_318_19(name="H30", f_c=30 * MPa), SteelBar(name="ADN 420", f_y=420 * MPa)


def designed(materials, width_cm, height_cm, settings=None):
    """A beam designed for M = 2.0 MPa * b * h^2, V = 0.3 M (kN with M in kN·m), c_c = 30 mm."""
    from mento import Node
    from mento.units import kN

    concrete, steel = materials
    b = RectangularBeam(
        label="T",
        concrete=concrete,
        steel_bar=steel,
        width=width_cm * cm,
        height=height_cm * cm,
        c_c=30 * mm,
        settings=settings,
    )
    moment = 2.0 * (width_cm / 100) * (height_cm / 100) ** 2 * 1000
    Node(section=b, forces=[Forces(label="U", M_y=moment * kNm, V_z=0.3 * moment * kN)]).design()
    return b


def _criterion_cases(table):
    return [pytest.param(h, b, row, id=f"{h}x{b}") for h, row in table.items() for b in CRITERION_WIDTHS]


def _assert_criterion(b, row, width):
    r = b.skin_reinforcement
    # The rows of the requirement, not detailing_geometry: some of these designed cages (ACI 20 cm webs,
    # 60x100) fail the base cage detailing, with or without skin; drawn skin is pinned elsewhere.
    if row is None:
        assert r.status == "not_required"
        assert r.n_per_side == 0
        assert r.rows == ()
        return
    status, rows, diameters = row
    assert r.status == status
    assert r.n_per_side == rows
    assert len(r.rows) == rows
    assert r.d_b == diameters[CRITERION_WIDTHS.index(width)] * mm


@pytest.mark.parametrize("height,width,row", _criterion_cases(EN_CRITERION))
def test_criterion_table_en(height, width, row):
    """EN 1992-1-1, C30/37 and B500S.

    Layers sit about 50 mm inside each face; skin_bar_spacing 280 mm gives the rows,
    n = ceil(span / 280) - 1: 1 at 60 cm (span ~500), 2 at 80 cm (~700), 3 at 1 and 1.2 m.
    Below 1 m Ø8 up to a 40 cm web, Ø10 above. From 1 m Eq. (7.1) with f_ctm = 0.30 * 30^(2/3) = 2.896:
    100x60 gives 0.2 * 2.896 * 600 * 1000 / 2 / 500 / 2 = 173.8 mm² per side over the two rows
    below 600 mm (x = 0.4 h): Ø10 157 mm² falls short, Ø12 226 mm² is enough. Status: required from 1 m.
    """
    _assert_criterion(designed(en_materials(), width, height), row, width)


@pytest.mark.parametrize("height,width,row", _criterion_cases(ACI_CRITERION))
def test_criterion_table_aci(height, width, row):
    """ACI 318-19, f'c = 30 MPa and f_y = 420 MPa: required only above 90 cm (§9.7.2.3), proposed from 60 cm.

    The cap is §24.3.2, 380 - 2.5 * (30 + stirrup) ~ 285 mm, so the counts match EN's.
    From 1 m Eq. (7.1) reads f_y = 420: 120x100 needs 0.2 * 2.896 * 1000 * 1200 / 2 / 420 / 2 = 413.8 mm²
    from the two rows below 720 mm; Ø16 gives 402 mm², Ø20 628 mm².
    """
    _assert_criterion(designed(aci_materials(), width, height), row, width)


@pytest.mark.parametrize("materials,width,height", [(en_materials, 40, 120), (aci_materials, 30, 100)])
def test_criterion_rows_span_the_whole_height(materials, width, height):
    """Rows between the inner bottom and top layers, equally spaced, the end gaps included, within the cap.

    A face with no bars (the designed top, only mounting steel) anchors at c_c + stirrup + 10 mm.
    """
    b = designed(materials(), width, height)
    r = b.skin_reinforcement
    geometry = b.section_geometry
    inset = (b.c_c + b._stirrup_d_b).to("mm").magnitude + 10

    def inner(face):
        second = geometry.bars_on(face, layer=2)
        bars = second if len(second) >= 2 else geometry.bars_on(face, layer=1)
        levels = [bar.y.to("mm").magnitude for bar in bars]
        if not levels:
            return inset if face == "bottom" else b.height.to("mm").magnitude - inset
        return max(levels) if face == "bottom" else min(levels)

    low, high = inner("bottom"), inner("top")
    rows = [y.to("mm").magnitude for y in r.rows]
    pitch = (high - low) / (r.n_per_side + 1)
    assert low < rows[0] and rows[-1] < high
    gaps = [upper - lower for lower, upper in zip([low, *rows], [*rows, high])]
    assert gaps == pytest.approx([pitch] * (len(rows) + 1))
    assert r.spacing.to("mm").magnitude == pytest.approx(pitch)
    assert pitch <= r.s_max.to("mm").magnitude
    # One fewer row would leave a gap over the cap: the count is the smallest that meets it.
    assert (high - low) / r.n_per_side > r.s_max.to("mm").magnitude
    for side in ("left", "right"):
        drawn = sorted(bar.y.to("mm").magnitude for bar in b.detailing_geometry.skin_bars if bar.face == side)
        assert drawn == pytest.approx(rows)


def test_criterion_en_assumed_service_sets_the_zone_and_the_stress():
    """en_beam, 30x120, C25, B500, M = 100 kN·m: Eq. (7.1) 0.2 * 2.565 * 300 * 1200 / 2 / 500 / 2 = 92.3 mm².

    x = 0.4 * 1200 = 480, zone 48..720 holds rows 324 and 600, Ø8 (100.5 mm²) suffices;
    sigma_s = 0.6 * 500 = 300, half 150 -> phi* = 32 mm, cap 32 * fct / 2.9 * 300 / (8 * 42).
    """
    fct = 0.3 * 25 ** (2 / 3)
    b = en_beam()
    b.check_flexure([Forces(M_y=100 * kNm)])
    r = b.skin_reinforcement
    assert zones(r) == [("bottom", 48, 720)]
    assert r.d_b == 8 * mm
    assert r.diameter_max.to("mm").magnitude == pytest.approx(32 * fct / 2.9 * 300 / (8 * 42))
    assert [y.to("mm").magnitude for y in r.rows] == pytest.approx([324, 600, 876])


@pytest.mark.parametrize("height,laid_out", [(23, False), (24, True)])
def test_criterion_imperial_starts_at_24_inches(height, laid_out):
    """Layers at 1.5 + 0.375 + 0.375 = 2.25 in from each face; §24.3.2 cap 15 - 2.5 * 1.875 = 10.31 in.

    24 in: span 19.5 in, n = ceil(19.5 / 10.31) - 1 = 1 row, at mid-height, No. 3 on a 12 in web.
    """
    b = RectangularBeam(
        label="US",
        concrete=Concrete_ACI_318_19(name="4000", f_c=4000 * psi),
        steel_bar=SteelBar(name="60", f_y=60 * ksi),
        width=12 * inch,
        height=height * inch,
        c_c=1.5 * inch,
    )
    b.set_longitudinal_rebar_bot(n1=4, d_b1=0.75 * inch)
    b.set_longitudinal_rebar_top(n1=4, d_b1=0.75 * inch)
    b.set_transverse_rebar(1, 0.375 * inch, 8 * inch)
    b.check_flexure([Forces(M_y=100 * kNm)])
    r = b.skin_reinforcement
    if not laid_out:
        assert r.status == "not_required"
        assert not b.detailing_geometry.skin_bars
        return
    assert r.status == "proposed"
    assert r.n_per_side == 1
    assert r.d_b.to("in").magnitude == pytest.approx(0.375)
    assert [y.to("in").magnitude for y in r.rows] == pytest.approx([12])
    assert len(b.detailing_geometry.skin_bars) == 2


@pytest.mark.parametrize("height,default", [(80, 8), (120, 10)])
def test_criterion_skin_bar_diameter_raises_the_smallest_diameter(height, default):
    """EN 30 cm web: Ø8 at 80 cm, Ø10 at 120 cm by default (the table); from 12 mm both take Ø12."""
    assert designed(en_materials(), 30, height).skin_reinforcement.d_b == default * mm
    b = designed(en_materials(), 30, height, BeamSettings(skin_bar_diameter=12 * mm))
    assert b.skin_reinforcement.d_b == 12 * mm
    assert [bar.d_b.to("mm").magnitude for bar in b.detailing_geometry.skin_bars] == pytest.approx(
        [12] * 2 * b.skin_reinforcement.n_per_side
    )
