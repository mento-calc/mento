"""The design layout and the cage hold the bars clear of the same stirrup bends.

A bar thinner than the stirrup's mandrel cannot sit in the square corner of the
inner faces. Built, it seats in the bend, on its 45° bisector, touching the arc
(``section_geometry.seated_corner``). The rebar search, the clear spacing the
checks report, the calculation geometry and ``beam.detailing_geometry`` all
lay the corner bars out at that distance from the leg, so a layout the design
accepts is one the cage can hold, and the other way round.

The depth is not moved: the checks keep the corner bar ``d_b/2`` from the
branch, a few millimetres closer to the face than it is built. Only the cage
draws it where it sits.
"""

import itertools
import math
import warnings

import pytest

from mento import Concrete_ACI_318_19, Forces, Node, RectangularBeam, SteelBar
from mento.cage_detailing import CageDetailingError
from mento.rebar import Rebar
from mento.section_geometry import corner_setback, end_setback, seated_corner
from mento.units import MPa, cm, kN, kNm, mm

#: The warnings that say the bars of a face do not fit its width.
SPACING = {"clear_spacing_below_min", "clear_spacing_below_vibrator", "bars_do_not_fit", "bar_spacing_exceeds_max"}

#: A Ø16 seated in the 40 mm bend of a Ø10 stirrup: 20 - 12/√2 from each inner face.
SEAT = 20 - 12 / math.sqrt(2)


def _beam(width: float, height: float = 40) -> RectangularBeam:
    return RectangularBeam(
        label="V9a",
        concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=width * cm,
        height=height * cm,
        c_c=25 * mm,
    )


def _v9a(width: float = 20) -> tuple[RectangularBeam, Node]:
    beam = _beam(width)
    beam.set_transverse_rebar(1, 10 * mm, 17 * cm)
    beam.set_longitudinal_rebar_top(3, 16 * mm)
    beam.set_longitudinal_rebar_bot(2, 8 * mm)
    node = Node(beam, [Forces(label="apoyo", V_z=80 * kN, M_y=-60 * kNm)])
    node.check()
    return beam, node


def _mm(value: object) -> float:
    return float(value.to("mm").magnitude)  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "bend, d_bar, seat",
    [
        (40, 16, SEAT),  # 11.51 mm
        (32, 16, 16 - 8 / math.sqrt(2)),
        (40, 40, 20.0),  # the bar fills the bend
        (40, 50, 25.0),  # thicker than the bend: it rests on both straight branches
    ],
)
def test_the_seated_corner(bend: float, d_bar: float, seat: float) -> None:
    assert seated_corner(bend, d_bar) == pytest.approx(seat)
    # The layer nearest the face is laid out at it.
    assert end_setback(bend, d_bar) == pytest.approx(seat - d_bar / 2)


@pytest.mark.parametrize(
    "bend, d_bar, depth, setback",
    [
        (40, 10, 25, 0.0),  # a layer behind, below the arc: the side branch is straight there
        (40, 10, 15, 20 - 200**0.5 - 5),  # partly up the arc, at its own depth
    ],
)
def test_a_layer_behind_keeps_its_depth_and_clears_the_bend(
    bend: float, d_bar: float, depth: float, setback: float
) -> None:
    assert corner_setback(bend, d_bar, depth) == pytest.approx(setback)
    assert end_setback(bend, d_bar, depth - d_bar / 2) == pytest.approx(setback)


def test_v9a_three_d16_on_top_fit_the_check_and_the_cage() -> None:
    """ACI 20x40, c_c 25 mm, 1eØ10, 3Ø16 on top under -60 kN·m.

    130 mm between the legs; a Ø16 seated in the 40 mm bend of the Ø10 sits
    11.51 mm off each inner face, 3.51 mm past its radius: (130 - 2*3.51 -
    48)/2 = 37.49 mm between the bars, room for the vibrator's 30. Laid out at
    the end of the bend (12 mm) it was 29 mm and failed; in the square corner
    it read 41 mm while the cage refused it.
    """
    beam, node = _v9a()

    assert not {w.code for w in node.warnings} & (SPACING | {"cage_detailing_infeasible"})
    assert beam.verification_status == {"resistance": "passed", "detailing": "passed"}
    assert _mm(beam._available_s_top) == pytest.approx((130 - 2 * (SEAT - 8) - 48) / 2)  # 37.49
    calculation = beam.section_geometry.bars_on("top")
    detail = beam.detailing_geometry.bars_on("top")
    xs = [35 + SEAT, 100.0, 165 - SEAT]
    assert [_mm(bar.x) for bar in calculation] == pytest.approx(xs)
    assert [_mm(bar.x) for bar in detail] == pytest.approx(xs)


def test_v9a_keeps_its_depth_and_the_cage_seats_the_corner_bars() -> None:
    """The checks read d = 400 - 25 - 10 - 8 = 357 mm; the corner bars are built 3.51 mm deeper in."""
    beam, _ = _v9a()

    assert [_mm(bar.y) for bar in beam.section_geometry.bars_on("top")] == pytest.approx([357.0] * 3)
    assert _mm(beam._c_mec_top) == pytest.approx(25 + 10 + 8)
    detail = beam.detailing_geometry.bars_on("top")
    assert [_mm(bar.y) for bar in detail] == pytest.approx([365 - SEAT, 357.0, 365 - SEAT])
    # Seated, the corner bar touches the bend and does not cut into it: its
    # centre is 20 - 8 = 12 mm from the centre of the arc at (55, 345).
    corner = detail[0]
    assert math.hypot(_mm(corner.x) - 55, _mm(corner.y) - 345) == pytest.approx(12.0)


def test_v9a_in_an_18_cm_web_fits_neither_the_check_nor_the_cage() -> None:
    """110 mm between the legs: (110 - 2*3.51 - 48)/2 = 27.5 mm, short of the vibrator on both."""
    beam, node = _v9a(18)

    codes = {(w.code, w.face) for w in node.warnings}
    assert ("clear_spacing_below_vibrator", "top") in codes
    assert ("cage_detailing_infeasible", None) in codes
    assert _mm(beam._available_s_top) == pytest.approx(27.49, abs=0.01)
    with pytest.raises(CageDetailingError):
        beam.detailing_geometry


def test_v9a_designed_fits_its_cage() -> None:
    beam = _beam(20)
    node = Node(beam, [Forces(label="apoyo", V_z=80 * kN, M_y=-60 * kNm)])
    node.design()

    assert node.warnings == ()
    assert beam.verification_status == {"resistance": "passed", "detailing": "passed"}
    beam.detailing_geometry  # does not raise


def test_the_search_reads_the_clear_spacing_the_check_reports() -> None:
    """20x50, c_c 30 mm, Ø8: 124 mm between the legs; the search's 2Ø16 + 1Ø12, seated 2.34 mm off them, read alike."""
    beam = RectangularBeam(
        label="V",
        concrete=Concrete_ACI_318_19(name="H30", f_c=30 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=20 * cm,
        height=50 * cm,
        c_c=30 * mm,
    )
    beam.set_transverse_rebar(1, 8 * mm, 15 * cm)
    rebar = Rebar(beam)
    rebar.longitudinal_rebar_ACI_318_19(A_s_req=5 * cm**2)
    best = rebar.longitudinal_rebar_design

    model = beam._layer_clear_spacing(best["n_1"], best["d_b1"], best["n_2"], best["d_b2"])
    seat = 16 - 8 / math.sqrt(2) - 8
    expected = (124 - 2 * seat - 2 * 16 - 12) / 2
    assert _mm(best["clear_spacing"]) == pytest.approx(_mm(model)) == pytest.approx(expected)


def test_the_check_and_the_cage_agree_on_what_fits() -> None:
    """Over a grid of single-stirrup sections, a face the check passes is one the cage holds.

    Webs of 15 to 25 cm, stirrups Ø6 to Ø12, two to four bars of Ø12 to Ø20 on
    the face the moment pulls or compresses. Before the bends were laid out,
    30 of these 216 disagreed: the check passed bars the cage could not place.
    """
    disagree = []
    for width, stirrup, n, d_b, sign in itertools.product(
        (15, 20, 25), (6, 8, 10, 12), (2, 3, 4), (12, 16, 20), (1, -1)
    ):
        beam = _beam(width, 50)
        beam.set_transverse_rebar(1, stirrup * mm, 15 * cm)
        beam.set_longitudinal_rebar_top(n, d_b * mm)
        beam.set_longitudinal_rebar_bot(2, 12 * mm)
        node = Node(beam, [Forces(label="f", V_z=50 * kN, M_y=sign * 40 * kNm)])
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            node.check()
        spacing = bool({w.code for w in node.warnings} & SPACING)
        try:
            beam.detailing_geometry
            cage = True
        except CageDetailingError:
            cage = False
        if spacing == cage:
            disagree.append((width, stirrup, n, d_b, sign))
    assert disagree == []


def test_the_search_holds_a_second_layer_to_its_own_bends() -> None:
    """EN 19.5x60, 1eØ25 (175 mm bend), layers 10 mm apart, Ø10 bars only.

    Layer 1: two Ø10 seated in the bend, (87.5 - 5)(1 - 1/√2) = 24.16 mm past
    their radius: 95 - 2*24.16 - 20 = 26.7 mm apart. Layer 2 sits 20 mm behind
    the branch, still inside the arc, and clears it 27.51 mm off the leg: 17.7 mm
    apart, short of the 25 mm the check asks for. (Only a layer spacing below the
    25 mm of §25.2.2 and a heavy stirrup reach this.) The search does not offer
    the second layer, and the check and the cage refuse it alike.
    """
    from mento import BeamSettings, Concrete_EN_1992_2004

    def beam() -> RectangularBeam:
        section = RectangularBeam(
            label="V",
            concrete=Concrete_EN_1992_2004(name="C25", f_c=25 * MPa),
            steel_bar=SteelBar(name="B500S", f_y=500 * MPa),
            width=19.5 * cm,
            height=60 * cm,
            c_c=25 * mm,
            settings=BeamSettings(layers_spacing=10 * mm, max_longitudinal_diameter=10 * mm),
        )
        section.set_transverse_rebar(1, 25 * mm, 20 * cm)
        return section

    rebar = Rebar(beam())
    rebar.longitudinal_rebar(3.0 * cm**2, None, None, "bot")
    best = rebar.longitudinal_rebar_design
    assert (best["n_1"], best["n_3"]) == (2, 0)
    assert _mm(best["clear_spacing"]) == pytest.approx(26.67, abs=0.01)

    checked = beam()
    checked.set_longitudinal_rebar_bot(n1=2, d_b1=10 * mm, n3=2, d_b3=10 * mm)
    assert _mm(checked._available_s_bot) == pytest.approx(17.7, abs=0.05)
    codes = {w.code for w in checked.warnings}
    assert {"clear_spacing_below_min", "cage_detailing_infeasible"} <= codes


def test_a_code_with_no_mandrel_rule_lays_out_on_the_placeholder(monkeypatch: pytest.MonkeyPatch) -> None:
    """With no bend hook the section lays its bars out on the 4·d_st placeholder, flagged as not a code rule."""
    from dataclasses import replace

    import mento.section_geometry as geometry
    from mento.codes.registry import design_code

    beam, _ = _v9a()
    code = replace(design_code(beam.concrete), stirrup_bend_inner_diameter=None)
    monkeypatch.setattr(geometry, "design_code", lambda concrete: code)

    bend, supported = geometry.stirrup_bend_inner_diameter(beam)
    assert (_mm(bend), supported) == (pytest.approx(40.0), False)
