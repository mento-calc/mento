"""Supported corners, additional steel, and preservation of calculated steel."""

import math

import matplotlib.pyplot as plt
import pytest
from matplotlib.patches import FancyBboxPatch

from mento import (
    Concrete_ACI_318_19,
    Concrete_CIRSOC_201_25,
    Concrete_EN_1992_2004,
    Forces,
    Node,
    RectangularBeam,
    SteelBar,
    set_language,
)
from mento.cage_detailing import CageDetailingError
from mento.section_geometry import SectionGeometry
from mento.units import MPa, cm, ft, inch, kip, kN, kNm, ksi, mm, psi


def _beam(width: float = 60, height: float = 60) -> RectangularBeam:
    return RectangularBeam(
        label="Detail",
        concrete=Concrete_CIRSOC_201_25(name="H25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN420", f_y=420 * MPa),
        width=width * cm,
        height=height * cm,
        c_c=30 * mm,
    )


def _mm(value: object) -> float:
    return float(value.to("mm").magnitude)  # type: ignore[attr-defined]


def test_unsupported_bend_diameter_preserves_calculation_geometry_and_plot():
    beam = _beam()
    beam.set_transverse_rebar(1, 40 * mm, 15 * cm)
    assert beam.section_geometry.stirrup_d_b == 40 * mm
    with pytest.raises(CageDetailingError) as raised:
        beam.detailing_geometry
    assert raised.value.reason == "unsupported_bend"
    with pytest.warns(UserWarning, match="Cage detailing is not feasible"):
        figure = beam.plot(show=False)
    plt.close(figure)


def _assert_supported(geometry: SectionGeometry) -> None:
    all_bars = geometry.bars + geometry.mounting_bars
    for stirrup in geometry.stirrups:
        for face, branch in (("bottom", stirrup.y_bottom), ("top", stirrup.y_top)):
            for leg, side in ((stirrup.x_left, 1), (stirrup.x_right, -1)):
                candidates = [bar for bar in all_bars if bar.face == face and bar.layer == 1]
                assert any(
                    _mm(bar.x - leg)
                    == pytest.approx(
                        side
                        * max(
                            (_mm(geometry.stirrup_bend_inner_diameter) + _mm(geometry.stirrup_d_b)) / 2,
                            (_mm(bar.d_b) + _mm(geometry.stirrup_d_b)) / 2,
                        )
                    )
                    and abs(_mm(bar.y - branch)) == pytest.approx((_mm(geometry.stirrup_d_b) + _mm(bar.d_b)) / 2)
                    for bar in candidates
                )
    for index, bar in enumerate(all_bars):
        for other in all_bars[index + 1 :]:
            clear = math.hypot(_mm(bar.x - other.x), _mm(bar.y - other.y)) - (_mm(bar.d_b) + _mm(other.d_b)) / 2
            assert clear >= 25 - 1e-8


@pytest.mark.parametrize("width, bottom, top, stirrups", [(60, 8, 6, 2), (100, 10, 8, 3)])
def test_existing_bars_support_every_corner(width: int, bottom: int, top: int, stirrups: int) -> None:
    beam = _beam(width)
    beam.set_longitudinal_rebar_bot(n1=bottom, d_b1=20 * mm)
    beam.set_longitudinal_rebar_top(n1=top, d_b1=16 * mm)
    beam.set_transverse_rebar(stirrups, 8 * mm, 20 * cm)
    before = beam.section_geometry
    detail = beam.detailing_geometry
    _assert_supported(detail)
    assert detail.mounting_bars == ()
    assert detail.leg_x == before.leg_x
    assert detail.stirrups == before.stirrups
    assert [(bar.d_b, bar.y, bar.group) for bar in detail.bars] == [(bar.d_b, bar.y, bar.group) for bar in before.bars]
    assert beam.section_geometry == before


@pytest.mark.filterwarnings("ignore::UserWarning")
def test_ten_leg_design_adds_upper_mounting_steel_without_mutating_results() -> None:
    beam = _beam(150, 150)
    Node(section=beam, forces=[Forces(M_y=5000 * kNm, V_z=5000 * kN)]).design()
    before = beam.section_geometry
    reinforcement, flexure, shear = beam.reinforcement, beam.flexure_design, beam.shear_design
    detail = beam.detailing_geometry
    _assert_supported(detail)
    assert len(detail.bars) == len(before.bars) == 12
    assert len(detail.mounting_bars) == 10
    assert {bar.face for bar in detail.mounting_bars} == {"top"}
    assert [_mm(bar.d_b) for bar in detail.mounting_bars] == pytest.approx([10] * 10)
    assert detail.bars_on("top") == ()  # Mounting is not resistant steel.
    assert beam.reinforcement == reinforcement
    assert beam.flexure_design == flexure
    assert beam.shear_design == shear
    assert beam.section_geometry == before
    assert len(detail.to_dict("in")["mounting_bars"]) == 10
    assert detail.to_dict("mm")["mounting_bars"][0]["d_b"] == pytest.approx(10)


def test_mounting_steel_fills_both_faces_and_retains_a_single_resistant_bar() -> None:
    beam = _beam()
    beam.set_longitudinal_rebar_bot(n1=1, d_b1=20 * mm)
    beam.set_longitudinal_rebar_top(n1=0, d_b1=0 * mm)
    beam.set_transverse_rebar(2, 8 * mm, 20 * cm)
    detail = beam.detailing_geometry
    _assert_supported(detail)
    assert len(detail.bars) == 1
    assert _mm(detail.bars[0].x) == pytest.approx(_mm(beam.width / 2))
    assert len(detail.mounting_bars) == 8


def test_two_layers_keep_their_vertical_centroid_and_bar_groups() -> None:
    beam = _beam(30)
    beam.set_longitudinal_rebar_bot(n1=2, d_b1=25 * mm, n2=2, d_b2=20 * mm, n3=3, d_b3=20 * mm)
    beam.set_longitudinal_rebar_top(n1=2, d_b1=16 * mm, n3=2, d_b3=12 * mm)
    beam.set_transverse_rebar(1, 8 * mm, 20 * cm)
    original = beam.section_geometry
    detail = beam.detailing_geometry
    _assert_supported(detail)
    for face in ("bottom", "top"):
        assert detail.bars_on(face, 2) == original.bars_on(face, 2)
        assert [(bar.d_b, bar.y, bar.group) for bar in detail.bars_on(face)] == [
            (bar.d_b, bar.y, bar.group) for bar in original.bars_on(face)
        ]


@pytest.mark.filterwarnings("ignore::UserWarning")
def test_imperial_design_uses_number_three_mounting_bars() -> None:
    beam = RectangularBeam(
        label="US",
        concrete=Concrete_ACI_318_19(name="4000", f_c=4000 * psi),
        steel_bar=SteelBar(name="Gr60", f_y=60 * ksi),
        width=12 * inch,
        height=24 * inch,
        c_c=1.5 * inch,
    )
    Node(section=beam, forces=[Forces(M_y=120 * kip * ft, V_z=40 * kip)]).design()
    detail = beam.detailing_geometry
    _assert_supported(detail)
    assert len(detail.mounting_bars) == 2
    assert detail.mounting_bars[0].d_b.to("in").magnitude == pytest.approx(3 / 8)
    assert detail.mounting_bars[0].x.units == detail.width.units


def test_impossible_cage_is_rejected_and_plot_is_explicitly_a_calculation_model() -> None:
    beam = _beam(20, 30)
    beam.set_longitudinal_rebar_bot(n1=2, d_b1=16 * mm)
    beam.set_transverse_rebar(2, 10 * mm, 15 * cm)
    with pytest.raises(CageDetailingError):
        _ = beam.detailing_geometry
    set_language("es")
    try:
        with pytest.warns(UserWarning, match="Cage detailing is not feasible"):
            figure = beam.plot()
        assert any("jaula no detallable" in text.get_text() for text in figure.axes[0].texts)
        assert not [patch for patch in figure.axes[0].patches if patch.get_gid() == "mounting_bar"]
        plt.close(figure)
    finally:
        set_language("en")


@pytest.mark.parametrize("diameter", [0 * mm, -12 * mm, math.nan * mm, 6 * mm])
def test_invalid_mounting_diameter_is_rejected(diameter: object) -> None:
    beam = _beam()
    beam.set_transverse_rebar(1, 8 * mm, 20 * cm)
    beam.settings.mounting_bar_diameter = diameter  # type: ignore[union-attr]
    with pytest.raises(ValueError, match="mounting_bar_diameter"):
        _ = beam.detailing_geometry
    with pytest.warns(UserWarning, match="mounting_bar_diameter"):
        figure = beam.plot(show=False)
    plt.close(figure)


def test_no_stirrups_has_no_added_mounting_steel() -> None:
    beam = _beam()
    beam.set_longitudinal_rebar_bot(n1=3, d_b1=20 * mm)
    assert beam.detailing_geometry == beam.section_geometry


def test_mounting_bars_do_not_disguise_excessive_resistant_bar_spacing() -> None:
    beam = _beam(100)
    beam.set_longitudinal_rebar_bot(n1=2, d_b1=20 * mm)
    beam.set_longitudinal_rebar_top(n1=0, d_b1=0 * mm)
    beam.set_transverse_rebar(3, 8 * mm, 20 * cm)
    Node(section=beam, forces=[Forces(M_y=100 * kNm)]).check_flexure()
    with pytest.raises(CageDetailingError, match="mounting steel cannot replace"):
        _ = beam.detailing_geometry


@pytest.mark.filterwarnings("ignore::UserWarning")
def test_compression_face_does_not_take_the_tension_spacing_cap() -> None:
    beam = _beam(100)
    beam.set_longitudinal_rebar_bot(n1=10, d_b1=20 * mm)
    beam.set_longitudinal_rebar_top(n1=2, d_b1=16 * mm)
    beam.set_transverse_rebar(3, 8 * mm, 20 * cm)
    Node(section=beam, forces=[Forces(M_y=100 * kNm, V_z=100 * kN)]).check()
    assert beam.flexure_design.top.DCR == 0
    detail = beam.detailing_geometry
    _assert_supported(detail)
    assert len(detail.mounting_bars) == 4
    assert {bar.face for bar in detail.mounting_bars} == {"top"}


def test_three_upper_bars_with_four_legs_add_one_mounting_bar() -> None:
    beam = _beam(50)
    beam.set_longitudinal_rebar_bot(n1=7, d_b1=20 * mm)
    beam.set_longitudinal_rebar_top(n1=3, d_b1=16 * mm)
    beam.set_transverse_rebar(2, 8 * mm, 20 * cm)
    Node(
        section=beam,
        forces=[Forces(M_y=100 * kNm, V_z=100 * kN), Forces(M_y=-80 * kNm, V_z=100 * kN)],
    ).check()
    original = beam.section_geometry
    detail = beam.detailing_geometry
    _assert_supported(detail)
    assert len(detail.bars_on("bottom")) == 7
    assert len(detail.bars_on("top")) == 3
    assert len(detail.mounting_bars) == 1
    assert detail.mounting_bars[0].face == "top"
    assert _mm(detail.mounting_bars[0].d_b) == pytest.approx(10)
    assert beam.section_geometry == original


@pytest.mark.parametrize("language", ["en", "es"])
def test_unchecked_cage_does_not_guess_tension_faces_and_labels_spacing_pending(language: str) -> None:
    beam = _beam()
    beam.set_longitudinal_rebar_bot(n1=2, d_b1=20 * mm)
    beam.set_longitudinal_rebar_top(n1=2, d_b1=16 * mm)
    beam.set_transverse_rebar(2, 8 * mm, 20 * cm)
    original = beam.section_geometry
    detail = beam.detailing_geometry
    _assert_supported(detail)
    assert len(detail.mounting_bars) == 4
    assert beam.section_geometry == original
    set_language(language)
    try:
        figure = beam.plot()
        texts = [text.get_text() for text in figure.axes[0].texts]
        expected = (
            "Separación por tracción pendiente · sin verificación de flexión"
            if language == "es"
            else "Tension-bar spacing pending · no flexure verification"
        )
        assert expected in texts
        assert not any("calculation model only" in text.lower() or "jaula no detallable" in text for text in texts)
        plt.close(figure)
    finally:
        set_language("en")
    Node(section=beam, forces=[Forces(label="Positive", M_y=100 * kNm)]).check_flexure()
    spacing = [warning for warning in beam.warnings if warning.code == "bar_spacing_exceeds_max"]
    assert len(spacing) == 1
    assert spacing[0].face == "bottom"
    with pytest.raises(CageDetailingError, match="mounting steel cannot replace"):
        _ = beam.detailing_geometry


def test_reversed_moment_activates_spacing_check_on_the_upper_face() -> None:
    beam = _beam()
    beam.set_longitudinal_rebar_bot(n1=7, d_b1=20 * mm)
    beam.set_longitudinal_rebar_top(n1=2, d_b1=16 * mm)
    beam.set_transverse_rebar(2, 8 * mm, 20 * cm)
    node = Node(section=beam, forces=[Forces(label="Positive", M_y=100 * kNm)])
    node.check_flexure()
    _assert_supported(beam.detailing_geometry)
    assert not [warning for warning in node.warnings if warning.code == "bar_spacing_exceeds_max"]
    figure = beam.plot()
    assert not any("spacing pending" in text.get_text() for text in figure.axes[0].texts)
    plt.close(figure)
    Node(
        section=beam,
        forces=[Forces(label="Positive", M_y=100 * kNm), Forces(label="Negative", M_y=-40 * kNm)],
    ).check_flexure()
    spacing = [warning for warning in beam.warnings if warning.code == "bar_spacing_exceeds_max"]
    assert len(spacing) == 1
    assert spacing[0].face == "top"
    with pytest.raises(CageDetailingError, match="mounting steel cannot replace"):
        _ = beam.detailing_geometry


def test_single_tension_bar_is_checked_against_face_width_despite_mounting_supports() -> None:
    beam = _beam()
    beam.set_longitudinal_rebar_bot(n1=1, d_b1=25 * mm)
    beam.set_transverse_rebar(2, 8 * mm, 20 * cm)
    _assert_supported(beam.detailing_geometry)
    Node(section=beam, forces=[Forces(M_y=50 * kNm)]).check_flexure()
    assert any(warning.code == "bar_spacing_exceeds_max" for warning in beam.warnings)
    with pytest.raises(CageDetailingError, match="mounting steel cannot replace"):
        _ = beam.detailing_geometry


@pytest.mark.parametrize("face", ["bottom", "top"])
def test_vibrator_clearance_is_required_on_the_upper_face_only(face: str) -> None:
    beam = RectangularBeam(
        label="V101",
        concrete=Concrete_ACI_318_19(name="C25", f_c=25 * MPa),
        steel_bar=SteelBar(name="S420", f_y=420 * MPa),
        width=20 * cm,
        height=50 * cm,
        c_c=25 * mm,
    )
    getattr(beam, f"set_longitudinal_rebar_{'bot' if face == 'bottom' else 'top'}")(
        n1=2, d_b1=20 * mm, n2=1, d_b2=16 * mm
    )
    beam.set_transverse_rebar(1, 10 * mm, 15 * cm)
    original = beam.section_geometry
    if face == "top":
        with pytest.raises(CageDetailingError, match="required spacing"):
            _ = beam.detailing_geometry
    else:
        detail = beam.detailing_geometry
        _assert_supported(detail)
        row = detail.bars_on("bottom", 1)
        gaps = [_mm(right.x - left.x) - (_mm(left.d_b) + _mm(right.d_b)) / 2 for left, right in zip(row, row[1:])]
        assert min(gaps) >= 25
        assert min(gaps) < 30
    assert beam.section_geometry == original


def test_canonical_aci_design_has_a_supported_drawing() -> None:
    beam = RectangularBeam(
        label="V101",
        concrete=Concrete_ACI_318_19(name="C25", f_c=25 * MPa),
        steel_bar=SteelBar(name="S420", f_y=420 * MPa),
        width=20 * cm,
        height=50 * cm,
        c_c=25 * mm,
    )
    Node(
        section=beam,
        forces=[
            Forces(label="1.2D+1.6L", M_y=120 * kNm, V_z=150 * kN),
            Forces(label="neg", M_y=-80 * kNm, V_z=90 * kN, N_x=20 * kN),
        ],
    ).design()
    original = beam.section_geometry
    _assert_supported(beam.detailing_geometry)
    assert beam.section_geometry == original
    figure = beam.plot()
    try:
        texts = [text.get_text().lower() for text in figure.axes[0].texts]
        assert not any("calculation model only" in text or "jaula no detallable" in text for text in texts)
    finally:
        plt.close(figure)


@pytest.mark.parametrize(
    "concrete_type,factor", [(Concrete_ACI_318_19, 6), (Concrete_CIRSOC_201_25, 6), (Concrete_EN_1992_2004, 7)]
)
def test_manual_large_stirrup_uses_its_code_mandrel_in_geometry_and_detail(concrete_type, factor) -> None:
    beam = RectangularBeam(
        concrete=concrete_type(name="C25", f_c=25 * MPa),
        steel_bar=SteelBar(name="S420", f_y=420 * MPa),
        width=80 * cm,
        height=80 * cm,
        c_c=30 * mm,
    )
    beam.set_longitudinal_rebar_bot(n1=2, d_b1=25 * mm)
    beam.set_longitudinal_rebar_top(n1=2, d_b1=25 * mm)
    beam.set_transverse_rebar(1, 20 * mm, 15 * cm)
    original = beam.section_geometry
    assert original.to_dict("mm")["stirrup_bend_inner_diameter"] == pytest.approx(factor * 20)
    detail = beam.detailing_geometry
    _assert_supported(detail)
    assert beam.section_geometry == original


def test_large_inner_stirrup_that_cannot_be_bent_is_not_drawn_as_a_hairpin() -> None:
    beam = _beam(100, 100)
    beam.set_longitudinal_rebar_bot(n1=8, d_b1=25 * mm)
    beam.set_transverse_rebar(4, 20 * mm, 15 * cm)
    with pytest.raises(CageDetailingError, match="too narrow") as caught:
        _ = beam.detailing_geometry
    assert caught.value.reason == "bend"
    with pytest.warns(UserWarning, match="too narrow"):
        figure = beam.plot()
    try:
        assert not any(isinstance(patch, FancyBboxPatch) for patch in figure.axes[0].patches)
        assert any(
            "not feasible" in text.get_text() or "jaula no detallable" in text.get_text()
            for text in figure.axes[0].texts
        )
    finally:
        plt.close(figure)


def test_imperial_detail_default_export_keeps_inches_and_mounting_bars() -> None:
    beam = RectangularBeam(
        concrete=Concrete_ACI_318_19(name="4000", f_c=4000 * psi),
        steel_bar=SteelBar(name="Gr60", f_y=60 * ksi),
        width=12 * inch,
        height=24 * inch,
        c_c=1.5 * inch,
    )
    beam.set_longitudinal_rebar_bot(n1=2, d_b1=0.75 * inch)
    beam.set_longitudinal_rebar_top(n1=0, d_b1=0 * mm)
    beam.set_transverse_rebar(1, 0.375 * inch, 8 * inch)
    data = beam.detailing_geometry.to_dict()
    assert data["unit"] == "in"
    assert data["width"] == pytest.approx(12)
    assert data["mounting_bars"][0]["d_b"] == pytest.approx(0.375)
    assert beam.section_geometry.to_dict("cm")["width"] == pytest.approx(30.48)
    figure = beam.plot()
    try:
        mounting = [p for p in figure.axes[0].patches if p.get_gid() == "mounting_bar"]
        resistant = [p for p in figure.axes[0].patches if p.get_gid() == "resistant_bar"]
        assert mounting and resistant
        assert all(not p.get_fill() for p in mounting)
        assert all(p.get_fill() for p in resistant)
    finally:
        plt.close(figure)


@pytest.mark.parametrize(
    "concrete_type,diameter,bend",
    [
        (Concrete_ACI_318_19, 16 * mm, 64 * mm),
        (Concrete_ACI_318_19, 25.4 * mm, 152.4 * mm),
        (Concrete_CIRSOC_201_25, 25 * mm, 150 * mm),
        (Concrete_EN_1992_2004, 16 * mm, 64 * mm),
        (Concrete_EN_1992_2004, 32 * mm, 224 * mm),
    ],
)
def test_bend_table_boundary_values(concrete_type, diameter, bend) -> None:
    """Tabulated mandrel-size cases; hook lengths and EN Eq. 8.1 are outside this check."""
    beam = RectangularBeam(
        concrete=concrete_type(name="C25", f_c=25 * MPa),
        steel_bar=SteelBar(name="S420", f_y=420 * MPa),
        width=80 * cm,
        height=80 * cm,
        c_c=30 * mm,
    )
    beam.set_transverse_rebar(1, diameter, 15 * cm)
    assert _mm(beam.section_geometry.stirrup_bend_inner_diameter) == pytest.approx(_mm(bend))


@pytest.mark.parametrize("concrete_type", [Concrete_ACI_318_19, Concrete_CIRSOC_201_25])
def test_transverse_bars_beyond_the_bend_table_are_rejected(concrete_type) -> None:
    beam = RectangularBeam(
        concrete=concrete_type(name="C25", f_c=25 * MPa),
        steel_bar=SteelBar(name="S420", f_y=420 * MPa),
        width=80 * cm,
        height=80 * cm,
        c_c=30 * mm,
    )
    beam.set_transverse_rebar(1, 32 * mm, 15 * cm)
    with pytest.raises(ValueError, match="bend table"):
        _ = beam.detailing_geometry
    assert beam.section_geometry.stirrup_d_b == 32 * mm


def test_unsupported_bend_export_marks_the_placeholder():
    wide_cirsoc_beam = _beam()
    wide_cirsoc_beam.set_transverse_rebar(1, 32 * mm, 20 * cm)
    geometry = wide_cirsoc_beam.section_geometry
    assert geometry.bend_supported is False
    exported = geometry.to_dict("mm")
    assert exported["bend_supported"] is False
    assert exported["stirrup_bend_inner_diameter"] == pytest.approx(128)


@pytest.mark.parametrize("diameter", [0 * mm, -12 * mm, math.nan * mm, 6 * mm])
def test_invalid_mounting_is_reported_without_breaking_verification(diameter):
    beam = _beam()
    beam.set_transverse_rebar(1, 8 * mm, 15 * cm)
    beam.settings.mounting_bar_diameter = diameter
    original = beam.section_geometry.to_dict("mm")
    with pytest.raises(CageDetailingError, match="mounting_bar_diameter") as error:
        beam.detailing_geometry
    assert error.value.reason == "mounting"
    assert beam.verification_status["detailing"] == "failed"
    warning = next(w for w in beam.warnings if w.code == "cage_detailing_infeasible")
    assert "mounting_bar_diameter" in warning.message
    assert beam.section_geometry.to_dict("mm") == original


def test_out_of_table_bend_is_pending_with_explicit_diagnostic():
    beam = _beam()
    beam.set_longitudinal_rebar_bot(n1=6, d_b1=20 * mm)
    beam.set_longitudinal_rebar_top(n1=6, d_b1=20 * mm)
    beam.set_transverse_rebar(1, 40 * mm, 15 * cm)
    warnings = beam.warnings
    warning = next(w for w in warnings if w.code == "cage_detailing_pending")
    assert warning.values["reason"]
    assert not any(w.code == "cage_detailing_infeasible" for w in warnings)
    assert beam.verification_status["detailing"] == "pending"


def test_supported_bend_that_does_not_fit_remains_a_failure():
    beam = _beam(100, 100)
    beam.set_longitudinal_rebar_bot(n1=8, d_b1=25 * mm)
    beam.set_transverse_rebar(4, 20 * mm, 15 * cm)
    with pytest.raises(CageDetailingError, match="too narrow") as error:
        beam.detailing_geometry
    assert error.value.reason == "bend"
    assert "cage_detailing_infeasible" in [w.code for w in beam.warnings]
    assert beam.verification_status["detailing"] == "failed"
