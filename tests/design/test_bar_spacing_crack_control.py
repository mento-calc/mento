"""The crack-control cap on bar spacing: ACI 318-19 / CIRSOC 201-25 §24.3.2.

§7.7.2.2 (one-way slabs) and §9.7.2.2 (beams) send the bars closest to the
tension face to Table 24.3.2: s <= min(380*(280/f_s) - 2.5*c_c, 300*(280/f_s)),
with f_s = (2/3)*f_y permitted by §24.3.2.1. mento used to apply the 3h and
450 mm of §7.7.2.3 alone to slabs, and nothing to beams. Every number below is
worked by hand in its docstring.
"""

import pytest

import mento
from mento import (
    Concrete_ACI_318_19,
    Concrete_CIRSOC_201_25,
    Concrete_EN_1992_2004,
    Forces,
    Node,
    OneWaySlab,
    RectangularBeam,
    SteelBar,
)
from mento.slab import Footing
from mento.units import MPa, cm, inch, kN, kNm, kip, ksi, mm

ADN_420 = SteelBar(name="ADN 420", f_y=420 * MPa)


def _slab(concrete, height, steel=ADN_420, c_c=25 * mm):  # type: ignore[no-untyped-def]
    return OneWaySlab(label="L1", concrete=concrete, steel_bar=steel, width=100 * cm, height=height, c_c=c_c)


def _beam(concrete, width, steel=ADN_420, c_c=25 * mm):  # type: ignore[no-untyped-def]
    return RectangularBeam(label="V1", concrete=concrete, steel_bar=steel, width=width, height=50 * cm, c_c=c_c)


# ---------------------------------------------------------------------------
# Slabs: the cap enters the design limit beside §7.7.2.3
# ---------------------------------------------------------------------------


def test_an_aci_slab_is_held_to_300_mm_by_table_24_3_2() -> None:
    """A 12 cm ACI slab under 7.5 kN·m, f'c 25, f_y 420, c_c 25 mm.

    §7.7.2.3 allows min(3h, 450) = 360 mm. §7.7.2.2 sends the bars to Table
    24.3.2 with f_s = (2/3)*420 = 280 MPa and c_c = 25 mm (no stirrup):
    min(380*1 - 62.5, 300*1) = min(317.5, 300) = 300 mm. The three Ø10 the
    search picks for the 2.26 cm² required would sit at floor(100/3) = 33 cm,
    inside the 36 cm of §7.7.2.3 and past the 30 cm of §24.3.2, so the strip
    is detailed Ø10/30: 3.33 bars, 2.62 cm².
    """
    slab = _slab(Concrete_ACI_318_19(name="H25", f_c=25 * MPa), 12 * cm)
    Node(section=slab, forces=Forces(label="C1", M_y=7.5 * kNm)).design()

    assert slab._max_bar_spacing().to("mm").magnitude == pytest.approx(300.0)
    layer = slab.reinforcement.bottom.layers[0]
    assert (layer.d_b, layer.s.to("cm").magnitude) == (10 * mm, 30)
    assert slab.reinforcement.bottom.A_s.to("cm**2").magnitude == pytest.approx(2.62, abs=5e-3)
    assert slab.reinforcement.bottom.A_s >= slab.flexure_design.bottom.A_s_req
    assert slab.warnings == ()


@pytest.mark.parametrize(
    ("f_y", "c_c", "expected_mm"),
    [
        # 380*(280/280) - 2.5*40 = 280 against 300: the cover term governs.
        (420 * MPa, 40 * mm, 280.0),
        # f_s = (2/3)*500 = 333.3: 380*0.84 - 2.5*25 = 256.7 against 300*0.84 = 252.
        (500 * MPa, 25 * mm, 252.0),
    ],
    ids=["deep_cover", "stronger_steel"],
)
def test_the_slab_cap_follows_the_cover_and_the_steel_grade(f_y, c_c, expected_mm) -> None:  # type: ignore[no-untyped-def]
    """A 25 cm ACI slab: 3h = 750 and 450 mm never bind; §24.3.2 does."""
    slab = _slab(Concrete_ACI_318_19(name="H25", f_c=25 * MPa), 25 * cm, SteelBar(name="S", f_y=f_y), c_c)

    assert slab._max_bar_spacing().to("mm").magnitude == pytest.approx(expected_mm, abs=0.05)


def test_a_cirsoc_slab_reads_the_same_300_mm_twice() -> None:
    """CIRSOC 201-25 art. 7.7.2.3 already prints 300 mm; Tabla 24.3.2 agrees for
    ADN 420 with 25 mm of cover, and takes over below it: with 40 mm the
    cover term gives 380 - 100 = 280 mm."""
    concrete = Concrete_CIRSOC_201_25(name="H25", f_c=25 * MPa)
    assert _slab(concrete, 25 * cm)._max_bar_spacing().to("mm").magnitude == pytest.approx(300.0)
    assert _slab(concrete, 25 * cm, c_c=40 * mm)._max_bar_spacing().to("mm").magnitude == pytest.approx(280.0)


def test_an_en_slab_keeps_its_own_limit() -> None:
    """EN 1992-1-1 controls cracking through §7.3.3, not through Table 24.3.2:
    a 25 cm slab keeps the 400 mm of §9.3.1.1(3)."""
    slab = _slab(Concrete_EN_1992_2004(name="C25", f_c=25 * MPa), 25 * cm, SteelBar(name="B500S", f_y=500 * MPa))

    assert slab._max_bar_spacing().to("mm").magnitude == pytest.approx(400.0)


def test_a_slab_spread_past_table_24_3_2_is_warned() -> None:
    """A 20 cm ACI slab with Ø16 every 40 cm carries 5.03 cm²/m, and the slab
    between the bars is bare: 400 mm is inside min(3h, 450) = 450 mm and past
    the 300 mm of §24.3.2, so the check says so and the report marks it."""
    slab = _slab(Concrete_ACI_318_19(name="H25", f_c=25 * MPa), 20 * cm)
    slab.set_slab_longitudinal_rebar_bot(d_b1=16 * mm, s_b1=40 * cm)
    Node(section=slab, forces=Forces(label="C1", M_y=20 * kNm)).check_flexure()

    found = {w.code: w for w in slab.warnings}
    assert "bar_spacing_exceeds_max" in found
    assert found["bar_spacing_exceeds_max"].face == "bottom"
    assert found["bar_spacing_exceeds_max"].values["s_max"].to("mm").magnitude == pytest.approx(300.0)
    rows = slab._data_min_max_flexure
    assert rows["Check"][3] == "Bar spacing bottom"
    assert rows["Max."][3] == pytest.approx(300.0)
    assert rows["Ok?"][3] == "❌"
    # A slab's spacing row carries the cap already: no rows are added.
    assert len(rows["Check"]) == 4


def test_a_footing_takes_the_cap_with_its_own_cover() -> None:
    """§13.3.2.1 sends a one-way footing to Chapter 7, and §7.7.2.2 to Table
    24.3.2 with the footing's cover: 50 mm gives 380 - 125 = 255 mm, tighter
    than the 300 mm practice put on a mat. EN 1992-1-1 keeps the 300 mm."""
    aci = Footing(
        label="Z1",
        concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
        steel_bar=ADN_420,
        width=100 * cm,
        height=60 * cm,
        c_c=50 * mm,
    )
    en = Footing(
        label="Z1",
        concrete=Concrete_EN_1992_2004(name="C25", f_c=25 * MPa),
        steel_bar=SteelBar(name="B500S", f_y=500 * MPa),
        width=100 * cm,
        height=60 * cm,
        c_c=50 * mm,
    )

    assert aci._max_bar_spacing().to("mm").magnitude == pytest.approx(255.0)
    assert en._max_bar_spacing().to("mm").magnitude == pytest.approx(300.0)


# ---------------------------------------------------------------------------
# Beams: the tension face is checked, and the report gets the rows
# ---------------------------------------------------------------------------


def _wide_beam() -> RectangularBeam:
    """60x50 ACI beam, c_c 25 mm, Ø10 stirrups, 2Ø25 bottom and 2Ø12 top.

    Between the stirrup legs there are 600 - 2*(25 + 10) = 530 mm. Bottom:
    530 - 2*25 = 480 mm clear, 505 mm centre to centre. Top: 530 - 24 = 506
    clear, 518 centre to centre. The cap, with 35 mm from the bars to either
    face: 380*(280/280) - 2.5*35 = 292.5 mm against 300, so 292.5 mm.
    """
    beam = _beam(Concrete_ACI_318_19(name="H25", f_c=25 * MPa), 60 * cm)
    beam.set_longitudinal_rebar_bot(n1=2, d_b1=25 * mm)
    beam.set_longitudinal_rebar_top(n1=2, d_b1=12 * mm)
    beam.set_transverse_rebar(n_stirrups=1, d_b=10 * mm, s_l=20 * cm)
    return beam


def test_a_beam_face_in_tension_is_held_to_table_24_3_2() -> None:
    beam = _wide_beam()
    node = Node(section=beam, forces=[Forces(label="pos", M_y=150 * kNm)])
    node.check_flexure()

    found = {w.code: w for w in node.warnings}
    assert "bar_spacing_exceeds_max" in found
    warning = found["bar_spacing_exceeds_max"]
    assert warning.face == "bottom"
    assert warning.combinations == ("pos",)
    assert warning.values["s"].to("mm").magnitude == pytest.approx(505.0)
    assert warning.values["s_max"].to("mm").magnitude == pytest.approx(292.5)
    assert warning.message == "Bar spacing on the bottom face: 50.5 cm exceeds the maximum 29.2 cm."


def test_the_cap_is_checked_on_the_face_the_combination_pulls() -> None:
    """The top bars of the same beam are compression steel under the positive
    moment and tension steel under the negative one; only the second holds
    them to §24.3.2. (The 2Ø12 are also below the top minimum there.)"""
    beam = _wide_beam()
    node = Node(section=beam, forces=[Forces(label="pos", M_y=150 * kNm), Forces(label="neg", M_y=-40 * kNm)])
    node.check_flexure()

    spacing = [(w.face, w.combinations) for w in node.warnings if w.code == "bar_spacing_exceeds_max"]
    assert spacing == [("bottom", ("pos",)), ("top", ("neg",))]


def test_the_report_of_a_beam_gets_the_two_rows() -> None:
    """Printed on both faces, checked on the tension face, like A_s,max."""
    beam = _wide_beam()
    Node(section=beam, forces=[Forces(label="pos", M_y=150 * kNm)]).check_flexure()

    rows = beam._data_min_max_flexure
    assert rows["Check"][4:] == ["Maximum spacing top", "Maximum spacing bottom"]
    assert rows["Unit"][4:] == ["mm", "mm"]
    assert rows["Value"][4:] == [pytest.approx(518.0), pytest.approx(505.0)]
    assert rows["Min."][4:] == ["", ""]
    assert rows["Max."][4:] == [pytest.approx(292.5), pytest.approx(292.5)]
    assert rows["Ok?"][4:] == ["✅", "❌"]
    assert beam._all_flexure_checks_passed is False
    # The other rows are what they were.
    assert rows["Check"][:4] == [
        "Min/Max As rebar top",
        "Minimum spacing top",
        "Min/Max As rebar bottom",
        "Minimum spacing bottom",
    ]


def test_the_rows_read_in_spanish() -> None:
    from mento.i18n import translate_table

    beam = _wide_beam()
    Node(section=beam, forces=[Forces(label="pos", M_y=150 * kNm)]).check_flexure()
    mento.set_language("es")
    try:
        table = translate_table(beam._data_min_max_flexure)
    finally:
        mento.set_language("en")

    assert table["Verificación"][4:] == ["Separación máxima superior", "Separación máxima inferior"]


def test_a_beam_narrow_enough_passes_and_gets_no_warning() -> None:
    """20x50 with 2Ø16: 200 - 2*(25 + 10) - 2*16 = 98 mm clear, 114 mm centre
    to centre, well inside 292.5 mm."""
    beam = _beam(Concrete_ACI_318_19(name="H25", f_c=25 * MPa), 20 * cm)
    beam.set_longitudinal_rebar_bot(n1=2, d_b1=16 * mm)
    beam.set_transverse_rebar(n_stirrups=1, d_b=10 * mm, s_l=20 * cm)
    Node(section=beam, forces=[Forces(label="pos", M_y=60 * kNm)]).check_flexure()

    rows = beam._data_min_max_flexure
    assert rows["Value"][5] == pytest.approx(114.0)
    assert rows["Ok?"][5] == "✅"
    assert "bar_spacing_exceeds_max" not in {w.code for w in beam.warnings}


def test_a_single_bar_is_measured_by_the_width_of_the_face() -> None:
    """§24.3.3: with one bar nearest the tension face, the width of that face
    shall not exceed s. A 40 cm beam with 1Ø25 and a Ø8 stirrup: 400 mm
    against 380 - 2.5*33 = 297.5 mm; a 25 cm beam, 250 mm, passes."""
    for width, expected in ((40 * cm, ("bottom",)), (25 * cm, ())):
        beam = _beam(Concrete_ACI_318_19(name="H25", f_c=25 * MPa), width)
        beam.set_longitudinal_rebar_bot(n1=1, d_b1=25 * mm)
        beam.set_transverse_rebar(n_stirrups=1, d_b=8 * mm, s_l=20 * cm)
        Node(section=beam, forces=[Forces(label="pos", M_y=50 * kNm)]).check_flexure()

        found = [w for w in beam.warnings if w.code == "bar_spacing_exceeds_max"]
        assert tuple(w.face for w in found) == expected
        if found:
            assert found[0].values["s"] == width
            assert found[0].values["s_max"].to("mm").magnitude == pytest.approx(297.5)


def test_a_mixed_layer_is_read_at_its_larger_bar() -> None:
    """50x50, Ø10 stirrups, 2Ø20 + 1Ø16 in one layer: 430 - 40 - 16 = 374 mm
    over two gaps, 187 mm clear; the centres of a Ø20 and the Ø16 sit
    187 + 18 = 205 mm apart, and the row takes 187 + 20 = 207 mm, the safe
    side of the pair. Inside 292.5 either way."""
    beam = _beam(Concrete_ACI_318_19(name="H25", f_c=25 * MPa), 50 * cm)
    beam.set_longitudinal_rebar_bot(n1=2, d_b1=20 * mm, n2=1, d_b2=16 * mm)
    beam.set_transverse_rebar(n_stirrups=1, d_b=10 * mm, s_l=20 * cm)
    Node(section=beam, forces=[Forces(label="pos", M_y=100 * kNm)]).check_flexure()

    assert beam._data_min_max_flexure["Value"][5] == pytest.approx(207.0)
    assert "bar_spacing_exceeds_max" not in {w.code for w in beam.warnings}


def test_an_imperial_beam_reads_the_in_lb_table() -> None:
    """24x24 in, 1.5 in cover, #3 stirrups, 2 No. 8: between the legs
    24 - 2*(1.5 + 0.375) = 20.25 in, 18.25 in clear, 19.25 in centre to
    centre. Grade 60, f_s = 40 ksi, 1.875 in to the face: min(15 - 4.69, 12)
    = 10.31 in."""
    beam = RectangularBeam(
        label="V1",
        concrete=Concrete_ACI_318_19(name="C4", f_c=4 * ksi),
        steel_bar=SteelBar(name="G60", f_y=60 * ksi),
        width=24 * inch,
        height=24 * inch,
        c_c=1.5 * inch,
    )
    beam.set_longitudinal_rebar_bot(n1=2, d_b1=1 * inch)
    beam.set_transverse_rebar(n_stirrups=1, d_b=0.375 * inch, s_l=8 * inch)
    Node(section=beam, forces=[Forces(label="pos", M_y=100 * kip * inch * 12)]).check_flexure()

    found = {w.code: w for w in beam.warnings}
    assert found["bar_spacing_exceeds_max"].values["s"].to("inch").magnitude == pytest.approx(19.25)
    assert found["bar_spacing_exceeds_max"].values["s_max"].to("inch").magnitude == pytest.approx(10.3125)


def test_an_en_beam_has_no_such_row() -> None:
    """EN 1992-1-1 controls cracking through §7.3.3; mento holds it to no
    §24.3.2, so the same 60 cm beam adds no rows and no warning."""
    beam = _beam(Concrete_EN_1992_2004(name="C25", f_c=25 * MPa), 60 * cm, SteelBar(name="B500S", f_y=500 * MPa))
    beam.set_longitudinal_rebar_bot(n1=2, d_b1=25 * mm)
    beam.set_transverse_rebar(n_stirrups=1, d_b=10 * mm, s_l=20 * cm)
    Node(section=beam, forces=[Forces(label="pos", M_y=150 * kNm)]).check_flexure()

    assert len(beam._data_min_max_flexure["Check"]) == 4
    assert "bar_spacing_exceeds_max" not in {w.code for w in beam.warnings}


def test_a_designed_wide_beam_keeps_its_bars_within_table_24_3_2() -> None:
    """The bar search holds a beam's layer to the cap while it lays it out.

    A 40x50 ACI beam under 80 kN·m is held to A_s,min of §9.6.1.2,
    max(0.25*sqrt(25), 1.4)/420*400*457.7 = 6.10 cm². 2Ø20 = 6.28 cm² carry
    it, but between the legs of the Ø10 stirrup the design ends with, 400 -
    2*(25 + 10) = 330 mm, the two bars sit 290 mm clear and 310 mm centre to
    centre, past the 292.5 mm of Table 24.3.2 (f_s = (2/3)*420 = 280 MPa,
    c_c = 35 mm to the bar: min(380 - 87.5, 300)). PR #164 laid it out so,
    and so does the search without the cap -- the check then warns
    ``bar_spacing_exceeds_max``. With the cap the same area goes in as
    2Ø16 + 2Ø12 in one layer: (330 - 2*16 - 2*12)/3 = 91.3 mm clear, 107.3 mm
    centre to centre, and the design passes its own check with nothing to
    warn about.
    """
    beam = _beam(Concrete_ACI_318_19(name="H25", f_c=25 * MPa), 40 * cm)
    Node(section=beam, forces=[Forces(label="C1", M_y=80 * kNm)]).design()

    assert str(beam.reinforcement.bottom) == "2Ø16 mm + 2Ø12 mm"
    assert beam.warnings == ()
    assert beam.reinforcement.transverse.d_b == 10 * mm
    assert beam.reinforcement.bottom.A_s.to("cm**2").magnitude == pytest.approx(6.28, abs=5e-3)
    rows = beam._data_min_max_flexure
    assert rows["Check"][-1] == "Maximum spacing bottom"
    assert rows["Value"][-1] == pytest.approx(107.33, abs=0.01)
    assert rows["Ok?"][-1] == "✅"


def test_a_designed_beam_reports_the_spacing_of_its_tension_bars() -> None:
    """The flexure check of a design adds the ``Maximum spacing`` row of the face in tension.

    A 60x50 ACI beam under 150 kN·m and 50 kN comes out as 3Ø20 with two
    Ø10 stirrups -- PR #164 designed it so as well, the cap has nothing to
    change here: 600 - 2*(25 + 10) = 530 mm between the legs, (530 - 60)/2 =
    235 mm clear and 255 mm centre to centre, inside 292.5.
    """
    beam = _beam(Concrete_ACI_318_19(name="H25", f_c=25 * MPa), 60 * cm)
    Node(section=beam, forces=[Forces(label="C1", M_y=150 * kNm, V_z=50 * kN)]).design()

    assert beam.reinforcement.bottom.n_bars == 3
    assert beam.reinforcement.transverse.d_b == 10 * mm
    rows = beam._data_min_max_flexure
    assert rows["Check"][-1] == "Maximum spacing bottom"
    assert rows["Value"][-1] == pytest.approx(255.0)
    assert rows["Ok?"][-1] == "✅"
    assert "bar_spacing_exceeds_max" not in {
        w.code for w in beam.warnings
    }  # El cálculo cumple; la heurística de jaula se informa aparte.


def test_the_search_cap_leaves_a_compression_face_alone() -> None:
    """§9.7.2.2 sends the bars nearest the tension face to Table 24.3.2, not the compression bars.

    A 40x80 CIRSOC beam, H30, c_c = 40 mm, under 1196.5 kN·m of positive
    moment only: the top face is never pulled. At the depth of the Ø8
    starter stirrup the bottom takes 11Ø25 = 54.00 cm², past A_s,max =
    53.88 cm² of §9.3.3.1, and two Ø10 on top lift it to A_s,max,eff =
    55.36 cm² (A_s,max + A's*f's/f_y). Between the legs of the Ø8, 400 -
    2*(40 + 8) = 304 mm, those two bars sit 294 mm centre to centre, past
    the 260 mm the cap would allow a tension face (f_s = 280 MPa, c_c =
    48 mm to the bar: min(380 - 120, 300)). The search held the compression
    face to it too, found no two bars within 10 times the 0.12 cm² asked
    for, and left the top bare: ``bars_do_not_fit`` on top and
    ``As_below_required`` below. Now the top gets its 2Ø10 and the design
    ends clean on 1eØ6/16 (see
    ``test_compression_bars_that_make_the_tension_steel_admissible_are_braced``):
    308 mm between the Ø6 legs, the two Ø10 298 mm apart against a 265 mm
    cap (c_c = 46 mm to the bar), which the report prints on the top face
    without holding it there, since no combination pulls that face.
    """
    beam = RectangularBeam(
        label="V1",
        concrete=Concrete_CIRSOC_201_25(name="H30", f_c=30 * MPa),
        steel_bar=ADN_420,
        width=40 * cm,
        height=80 * cm,
        c_c=40 * mm,
    )
    Node(section=beam, forces=[Forces(label="C1", M_y=1196.5 * kNm)]).design()

    assert str(beam.reinforcement.top) == "2Ø10 mm"
    assert beam.warnings == ()
    assert beam.reinforcement.transverse.d_b == 6 * mm
    assert beam.reinforcement.bottom.A_s.to("cm**2").magnitude == pytest.approx(54.00, abs=5e-3)
    (check,) = beam.flexure_check_results([Forces(label="C1", M_y=1196.5 * kNm)])
    assert check.bottom.DCR == pytest.approx(0.965, abs=5e-4)
    rows = beam._data_min_max_flexure
    assert rows["Check"][4:] == ["Maximum spacing top", "Maximum spacing bottom"]
    assert rows["Value"][4] == pytest.approx(298.0)
    assert rows["Max."][4] == pytest.approx(265.0)
    assert rows["Ok?"][4] == "✅"


def test_the_search_cap_leaves_a_slab_strip_to_its_own_spacing() -> None:
    """A strip is not laid out between stirrup legs, so the search does not
    hold it to the cap: the 12 cm slab of the first test still gets the three
    Ø10 the area asks for, and the spacing the strip is written back as is
    what applies the 300 mm (Ø10/30, not the five bars a 300 mm centre-to-
    centre layout between the covers would take)."""
    slab = _slab(Concrete_ACI_318_19(name="H25", f_c=25 * MPa), 12 * cm)
    Node(section=slab, forces=Forces(label="C1", M_y=7.5 * kNm)).design()

    row = slab.flexure_design_results_bot
    assert int(row["n_1"]) + int(row["n_2"]) == 3
    assert slab.reinforcement.bottom.layers[0].s.to("cm").magnitude == 30


def test_a_bare_face_has_no_row() -> None:
    """A beam whose top was cleared has nothing nearest that face to measure."""
    beam = _wide_beam()
    beam.set_longitudinal_rebar_top(n1=0, d_b1=0 * mm)
    Node(section=beam, forces=[Forces(label="pos", M_y=150 * kNm)]).check_flexure()

    assert beam._data_min_max_flexure["Check"][4:] == ["Maximum spacing bottom"]
