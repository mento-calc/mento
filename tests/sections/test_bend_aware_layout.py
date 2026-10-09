"""The design layout and the cage hold the bars clear of the same stirrup bends.

A bar thinner than the stirrup's mandrel cannot sit in the square corner of the
inner faces: at the depth the checks place it, tangent to the horizontal
branch, it has to clear the arc, which puts its centre at the end of the bend.
The rebar search, the clear spacing the checks report, the calculation
geometry and ``beam.detailing_geometry`` all use that one rule
(``section_geometry.corner_setback``), so a layout the design accepts is one
the cage can hold, and the other way round.
"""

import itertools
import warnings

import pytest

from mento import Concrete_ACI_318_19, Forces, Node, RectangularBeam, SteelBar
from mento.cage_detailing import CageDetailingError
from mento.rebar import Rebar
from mento.section_geometry import corner_setback
from mento.units import MPa, cm, kN, kNm, mm

#: The warnings that say the bars of a face do not fit its width.
SPACING = {"clear_spacing_below_min", "clear_spacing_below_vibrator", "bars_do_not_fit", "bar_spacing_exceeds_max"}


def _beam(width: float, height: float = 40) -> RectangularBeam:
    return RectangularBeam(
        label="V9a",
        concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=width * cm,
        height=height * cm,
        c_c=25 * mm,
    )


def _mm(value: object) -> float:
    return float(value.to("mm").magnitude)  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "bend, d_bar, depth, setback",
    [
        (40, 16, 8, 12.0),  # layer 1: (40 - 16)/2
        (40, 40, 20, 0.0),  # the bar fills the bend
        (40, 50, 25, 0.0),  # thicker than the bend: it rests on both branches
        (40, 10, 25, 0.0),  # above the arc: the side branch is straight there
        (40, 10, 15, 20 - 200**0.5 - 5),  # partly up the arc
    ],
)
def test_the_corner_setback(bend: float, d_bar: float, depth: float, setback: float) -> None:
    assert corner_setback(bend, d_bar, depth) == pytest.approx(setback)


def test_v9a_three_d16_on_top_fit_neither_the_check_nor_the_cage() -> None:
    """ACI 20x40, c_c 25 mm, 1eØ10, 3Ø16 on top under -60 kN·m.

    130 mm between the legs; the Ø10 bends on a 40 mm mandrel, which holds
    each Ø16 corner bar (40 - 16)/2 = 12 mm off its leg: (130 - 24 - 48)/2 =
    29 mm between the bars, short of the vibrator's 30 mm. The check says so
    and the cage cannot be detailed, for the same reason. Before, the check
    read 41 mm and passed while the cage refused.
    """
    beam = _beam(20)
    beam.set_transverse_rebar(1, 10 * mm, 17 * cm)
    beam.set_longitudinal_rebar_top(3, 16 * mm)
    beam.set_longitudinal_rebar_bot(2, 8 * mm)
    node = Node(beam, [Forces(label="apoyo", V_z=80 * kN, M_y=-60 * kNm)])
    node.check()

    codes = {(w.code, w.face) for w in node.warnings}
    assert ("clear_spacing_below_vibrator", "top") in codes
    assert ("cage_detailing_infeasible", None) in codes
    assert _mm(beam._available_s_top) == pytest.approx(29.0)
    assert [_mm(bar.x) for bar in beam.section_geometry.bars_on("top")] == pytest.approx([55.0, 100.0, 145.0])
    with pytest.raises(CageDetailingError):
        beam.detailing_geometry


@pytest.mark.parametrize(
    "width, stirrup, top",
    [(20, 8, (3, 16)), (20, 10, (3, 12)), (25, 10, (3, 16))],
    ids=["Ø8 stirrup", "3Ø12", "25 cm web"],
)
def test_v9a_variants_that_fit_put_the_corner_bars_where_the_cage_does(
    width: float, stirrup: float, top: tuple[int, float]
) -> None:
    beam = _beam(width)
    beam.set_transverse_rebar(1, stirrup * mm, 17 * cm)
    beam.set_longitudinal_rebar_top(top[0], top[1] * mm)
    beam.set_longitudinal_rebar_bot(2, 8 * mm)
    node = Node(beam, [Forces(label="apoyo", V_z=80 * kN, M_y=-60 * kNm)])
    node.check()

    assert not {w.code for w in node.warnings} & (SPACING | {"cage_detailing_infeasible"})
    calculation = beam.section_geometry.bars_on("top", 1)
    detail = beam.detailing_geometry.bars_on("top", 1)
    assert [_mm(bar.x) for bar in detail] == pytest.approx([_mm(bar.x) for bar in calculation])


def test_v9a_designed_fits_its_cage() -> None:
    beam = _beam(20)
    node = Node(beam, [Forces(label="apoyo", V_z=80 * kN, M_y=-60 * kNm)])
    node.design()

    assert node.warnings == ()
    assert beam.verification_status == {"resistance": "passed", "detailing": "passed"}
    beam.detailing_geometry  # does not raise


def test_the_search_reads_the_clear_spacing_the_check_reports() -> None:
    """20x50, c_c 30 mm, Ø8: the search's 2Ø16 + 1Ø12 are 32 mm apart, as the check reads them."""
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
    assert _mm(best["clear_spacing"]) == pytest.approx(_mm(model)) == pytest.approx(32.0)


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
