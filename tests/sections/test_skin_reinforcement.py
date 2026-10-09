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
    SkinServiceCase,
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


@pytest.mark.parametrize("height,required", [(899, False), (900, False), (901, True)])
def test_metric_strict_depth_boundary(height, required):
    b = beam(height * mm)
    b.check_flexure([Forces(M_y=100 * kNm)])
    assert (b.skin_reinforcement.status == "required") == required
    assert bool(b.detailing_geometry.skin_bars) == required


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
    b = beam()
    b.check_flexure([Forces(M_y=m * kNm) for m in moments])
    original = b.section_geometry
    reinforcement, flexure = b.reinforcement, b.flexure_design
    r = b.skin_reinforcement
    g = b.detailing_geometry
    assert r.tension_faces == faces
    assert r.s_max.to("mm").magnitude == pytest.approx(285)  # side cover 30+8
    assert len(g.skin_bars) == 2 * r.n_per_side
    for side in ("left", "right"):
        ys = sorted(x.y.to("mm").magnitude for x in g.skin_bars if x.face == side)
        assert len(ys) == len(set(ys))
        if faces == ("bottom",):
            assert ys == pytest.approx([324, 600])
        elif faces == ("top",):
            assert ys == pytest.approx([600, 876])
        else:
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


def test_en_zero_moment_stays_pending_and_pure_axial_is_unsupported():
    from mento.units import kN

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
    b.check_flexure([Forces(N_x=100 * kN, M_y=0 * kNm)])
    assert b.skin_reinforcement.status == "unsupported"
    assert b.skin_reinforcement.pending_reason == "axial"
    assert "skin_en_axial_unsupported" in [w.code for w in b.warnings]


def test_diameter_is_configurable_and_not_a_code_minimum():
    b = beam()
    b.settings.skin_bar_diameter = 8 * mm
    b.check_flexure([Forces(M_y=100 * kNm)])
    assert all(bar.d_b.to("mm").magnitude == 8 for bar in b.detailing_geometry.skin_bars)
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
    b = beam(cover=80 * mm, width=50 * cm)
    b.check_flexure([Forces(M_y=100 * kNm)])
    assert b.skin_reinforcement.s_max.to("mm").magnitude == pytest.approx(160)
    assert b.skin_reinforcement.n_per_side == 4
    assert b.detailing_geometry.skin_bars
    b = beam(cover=110 * mm, width=50 * cm)
    b.check_flexure([Forces(M_y=100 * kNm)])
    assert b.skin_reinforcement.n_per_side == 6
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
    ys = [bar.y.to(mm).magnitude for bar in b.detailing_geometry.skin_bars if bar.face == "left"]
    assert ys == pytest.approx([275, 437.5, 600])
    assert b.reinforcement == before


def test_aci_ground_cover_can_have_a_feasible_uniform_skin_grid():
    b = beam(height=100 * cm, cover=75 * mm, width=60 * cm, concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa))
    b.set_transverse_rebar(1, 12 * mm, 20 * cm)
    b.set_longitudinal_rebar_bot(n1=4, d_b1=25 * mm)
    b.check_flexure([Forces(M_y=100 * kNm)])
    ys = [bar.y.to(mm).magnitude for bar in b.detailing_geometry.skin_bars if bar.face == "left"]
    assert ys == pytest.approx([233, 366.5, 500])


def test_en_requires_service_inputs():
    b = beam(concrete=Concrete_EN_1992_2004(name="C25", f_c=25 * MPa))
    b.check_flexure([Forces(M_y=100 * kNm)])
    assert b.skin_reinforcement.status == "pending"
    assert b.skin_reinforcement.pending_reason == "service"
    assert not b.detailing_geometry.skin_bars


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


def service_cases(b, axes=None, stress=400 * MPa):
    axes = {"bottom": 240 * mm, "top": 240 * mm} if axes is None else axes
    b.set_skin_service_cases([SkinServiceCase(f"SLS-{face}", face, stress, axis) for face, axis in axes.items()])


def en_beam(height=1200 * mm, fy=500 * MPa):
    b = beam(
        height=height, concrete=Concrete_EN_1992_2004(name="C25", f_c=25 * MPa), steel=SteelBar(name="B500", f_y=fy)
    )
    service_cases(b)
    return b


@pytest.mark.parametrize("height,required", [(999, False), (1000, True), (1001, True)])
def test_en_inclusive_one_metre_boundary(height, required):
    b = en_beam(height * mm)
    b.check_flexure([Forces(M_y=100 * kNm)])
    assert (b.skin_reinforcement.status == "required") == required
    assert bool(b.detailing_geometry.skin_bars) == required


@pytest.mark.parametrize("height, rows, gap", [(1000, 1, 356), (1200, 2, 304)])
def test_en_keeps_its_distribution_and_warns_with_the_actual_zone_intervals(height, rows, gap):
    b = en_beam(height * mm)
    b.check_flexure([Forces(M_y=100 * kNm)])
    before = b.skin_reinforcement
    geometry = b.detailing_geometry
    assert before.n_per_side == rows
    assert len(geometry.skin_bars) == 2 * rows
    try:
        for language in ("en", "es"):
            set_language(language)
            warning = next(w for w in b.warnings if w.code == "skin_distribution_review")
            assert warning.face is None
            assert warning.values["cases"] == 1
            assert warning.values["rows"] == rows
            assert warning.values["gap"].to("mm").magnitude == pytest.approx(gap)
            assert ("not an additional code" if language == "en" else "no un límite normativo") in warning.message
            assert b.skin_reinforcement == before
            assert b.detailing_geometry == geometry
            fig = plot_quietly(b)
            labels = [text.get_text() for text in fig.axes[0].texts]
            # The review is the warning above; the drawing only labels the skin it proposes.
            skin = f"{rows}Ø10 per side (skin)" if language == "en" else f"{rows}Ø10 por lateral (piel)"
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
    # Main sigma=400 -> skin sigma=200 -> Table7.2N phi*=25mm.
    # Conservative web-as-tie interpretation: 300mm width and actual skin
    # centroid 43mm from the side. Hand-evaluated Eq. (7.7N), not the old
    # bending-depth interpretation (34.55mm).
    assert r.diameter_max.to("mm").magnitude == pytest.approx(19.28351, abs=0.0001)
    assert r.n_per_side == 2
    assert r.area_per_side >= r.area_min_per_side
    assert r.s_max is None  # EN diameter route does NOT invent a spacing cap.
    ys = [bar.y.to("mm").magnitude for bar in b.detailing_geometry.skin_bars if bar.face == "left"]
    assert ys == pytest.approx([352, 656])  # evenly between tension layer48 and NA960.
    assert r.spacing.to("mm").magnitude == pytest.approx(304)


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


def test_en_reversal_disjoint_zones_each_receive_minimum_area():
    b = en_beam()
    service_cases(b, {"bottom": 800 * mm, "top": 800 * mm})
    b.check_flexure([Forces(M_y=100 * kNm), Forces(M_y=-80 * kNm)])
    r = b.skin_reinforcement
    ys = [bar.y.to("mm").magnitude for bar in b.detailing_geometry.skin_bars if bar.face == "left"]
    abar = math.pi * 10**2 / 4
    for low, high in [(48, 400), (800, 1152)]:
        assert sum(low <= y <= high for y in ys) * abar >= r.area_min_per_side.to("mm**2").magnitude


@pytest.mark.parametrize(
    "field,value",
    [
        ("skin_service_steel_stress", 400),
        ("skin_service_steel_stress", 0 * MPa),
        ("skin_service_steel_stress", 501 * MPa),
        ("skin_service_steel_stress", float("nan") * MPa),
        ("skin_service_neutral_axis", 0 * mm),
        ("skin_service_neutral_axis", 1200 * mm),
        ("skin_service_neutral_axis", 1190 * mm),
        ("skin_crack_width", 0.25 * mm),
    ],
)
def test_en_rejects_invalid_or_inconsistent_service_inputs(field, value):
    b = en_beam()
    with pytest.raises(ValueError):
        if field == "skin_service_steel_stress":
            service_cases(b, stress=value)
        elif field == "skin_service_neutral_axis":
            service_cases(b, {"bottom": value, "top": value})
        else:
            setattr(b.settings, field, value)
        b.check_flexure([Forces(M_y=100 * kNm)])
        _ = b.skin_reinforcement


def test_en_rounds_service_stress_up_and_applies_crack_width_selection():
    b = en_beam(fy=600 * MPa)
    service_cases(b, stress=600 * MPa)  # skin300 -> conservative table320.
    b.settings.skin_crack_width = 0.2 * mm
    b.check_flexure([Forces(M_y=100 * kNm)])
    with pytest.raises(CageDetailingError, match="diameter"):
        _ = b.detailing_geometry
    b.settings.skin_bar_diameter = 8 * mm
    with pytest.raises(CageDetailingError, match="diameter"):
        _ = b.detailing_geometry


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
    assert b.skin_reinforcement.status == "not_required"
    assert "skin_en_surface_pending" in [w.code for w in b.warnings]


def test_en_pending_service_is_visible_and_bilingual():
    b = en_beam()
    b.set_skin_service_cases([])
    b.check_flexure([Forces(M_y=100 * kNm)])
    set_language("es")
    try:
        warning = next(w for w in b.warnings if w.code == "skin_en_service_pending")
        assert "servicio" in warning.message
        fig = plot_quietly(b)
        assert not any("faltan datos de servicio" in t.get_text() for t in fig.axes[0].texts)
        assert not any(p.get_gid() == "skin_bar" for p in fig.axes[0].patches)
        plt.close(fig)
    finally:
        set_language("en")


@pytest.mark.parametrize(
    "moments,axes,expected",
    [
        ([100], {"bottom": 240 * mm}, [352, 656]),
        ([-100], {"top": 320 * mm}, [320 + 832 / 3, 320 + 2 * 832 / 3]),
    ],
)
def test_en_service_axes_can_differ_by_bending_sign(moments, axes, expected):
    b = en_beam()
    service_cases(b, axes)
    b.check_flexure([Forces(M_y=m * kNm) for m in moments])
    ys = [bar.y.to("mm").magnitude for bar in b.detailing_geometry.skin_bars if bar.face == "left"]
    assert ys == pytest.approx(expected)


def test_en_service_axes_must_cover_both_checked_signs():
    b = en_beam()
    service_cases(b, {"bottom": 240 * mm})
    b.check_flexure([Forces(M_y=100 * kNm), Forces(M_y=-80 * kNm)])
    assert b.skin_reinforcement.status == "pending"
    assert b.skin_reinforcement.pending_reason == "service"
    assert not b.detailing_geometry.skin_bars


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
    service_cases(b)
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


def test_skin_stirrup_collision_keeps_the_base_cage_mounting():
    from mento.cage_detailing import build_cage_detailing

    b = beam(
        height=100 * cm,
        width=60 * cm,
        concrete=Concrete_EN_1992_2004(name="C25", f_c=25 * MPa),
        steel=SteelBar(name="B500", f_y=500 * MPa),
    )
    b.set_longitudinal_rebar_top(n1=0, d_b1=0 * mm)
    b.set_transverse_rebar(1, 20 * mm, 20 * cm)
    b.check_flexure([Forces(M_y=100 * kNm)])
    b.set_skin_service_cases([SkinServiceCase("SLS", "bottom", 400 * MPa, 800 * mm)])
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
