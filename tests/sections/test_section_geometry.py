"""The public geometry of a section: legs, cage and bars where the checks assume them.

Every position here is the model a check already uses, so most tests tie the
geometry back to the check itself -- the leg spacing, the clear spacing of the
bars, the centroid behind the effective depth -- rather than to numbers of
their own.
"""

import pytest

import mento
from mento import (
    Concrete_ACI_318_19,
    Concrete_CIRSOC_201_25,
    Footing,
    Forces,
    Node,
    OneWaySlab,
    RectangularBeam,
    ShearWall,
    SteelBar,
)
from mento.section_geometry import (
    BarPosition,
    SectionGeometry,
    _cage,
    build_section_geometry,
    _group_order,
)
from mento.shear_wall import NotABeamError
from mento.units import MPa, cm, inch, kN, kNm, ksi, m, mm

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")


def _cm(values: object) -> list[float]:
    return [round(v.to("cm").magnitude, 4) for v in values]  # type: ignore[attr-defined]


def _beam(
    width_cm: float = 40, height_cm: float = 60, c_c: object = 25 * mm, concrete: object = None
) -> RectangularBeam:
    return RectangularBeam(
        label="G",
        concrete=concrete or Concrete_ACI_318_19(name="H25", f_c=25 * MPa),  # type: ignore[arg-type]
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=width_cm * cm,
        height=height_cm * cm,
        c_c=c_c,  # type: ignore[arg-type]
    )


@pytest.fixture(scope="module")
def wide_cirsoc_beam() -> RectangularBeam:
    """The wide CIRSOC beam: CIRSOC 201-25 H-25, 150x150, c_c 30 mm, Mu 5000 kNm, Vu 5000 kN."""
    beam = _beam(150, 150, 30 * mm, Concrete_CIRSOC_201_25(name="H-25", f_c=25 * MPa))
    Node(section=beam, forces=[Forces(label="C1", M_y=5000 * kNm, V_z=5000 * kN)]).design()
    return beam


# ---------------------------------------------------------------------------
# The 150x150 CIRSOC beam
# ---------------------------------------------------------------------------


def test_the_wide_cirsoc_legs_and_cage(wide_cirsoc_beam: RectangularBeam) -> None:
    geometry = wide_cirsoc_beam.section_geometry
    assert isinstance(geometry, SectionGeometry)
    assert geometry.s_w.to("cm").magnitude == pytest.approx(15.8667, abs=1e-4)
    assert _cm(geometry.leg_x) == [3.6, 19.4667, 35.3333, 51.2, 67.0667, 82.9333, 98.8, 114.6667, 130.5333, 146.4]
    assert len(geometry.leg_x) == wide_cirsoc_beam.reinforcement.transverse.n_legs == 10

    stirrups = geometry.stirrups
    assert [s.legs for s in stirrups] == [(0, 9)]
    assert [s.perimeter for s in stirrups] == [True]
    assert _cm([stirrups[0].x_left, stirrups[0].x_right]) == [3.6, 146.4]
    assert {(_cm([s.y_bottom])[0], _cm([s.y_top])[0]) for s in stirrups} == {(3.6, 146.4)}
    # The outer line of the perimeter stirrup is the cover: c_c to b - c_c.
    d = geometry.stirrup_d_b.to("cm").magnitude
    assert stirrups[0].x_left.to("cm").magnitude - d / 2 == pytest.approx(3.0)
    assert stirrups[0].x_right.to("cm").magnitude + d / 2 == pytest.approx(147.0)
    assert [tie.leg for tie in geometry.crossties] == list(range(1, 9))
    assert geometry.arrangement("en") == "perimeter stirrup + 8 open legs"
    assert geometry.arrangement("es") == "estribo perimetral + 8 patas abiertas"


def test_the_wide_cirsoc_bars(wide_cirsoc_beam: RectangularBeam) -> None:
    geometry = wide_cirsoc_beam.section_geometry
    bottom = geometry.bars_on("bottom")
    # The Ø12 stirrup bends on a 48 mm mandrel; a Ø32 seated in it sits
    # 24 - 8/√2 = 18.34 mm off the inner face of the leg: 3 + 1.2 + 1.834.
    assert _cm([b.x for b in bottom]) == [
        6.0343,
        18.5735,
        31.1127,
        43.652,
        56.1912,
        68.7304,
        81.2696,
        93.8088,
        106.348,
        118.8873,
        131.4265,
        143.9657,
    ]
    assert {round(b.y.to("cm").magnitude, 6) for b in bottom} == {5.8}
    assert [b.group for b in bottom] == [1] + [2] * 10 + [1]
    assert geometry.bars_on("top") == ()
    # The last bar's face, seated in the bend: 150 - 3 - 1.2 - (1.834 - 1.6).
    assert bottom[-1].x.to("cm").magnitude + 1.6 == pytest.approx(145.5657, abs=1e-4)
    # The honest picture PR 2 fixes: the legs are not tied to the bars.
    nearest = [min(abs(x - b.x).to("cm").magnitude for b in bottom) for x in geometry.leg_x]
    assert [round(v, 3) for v in nearest] == [2.434, 0.893, 4.221, 4.991, 1.664, 1.664, 4.991, 4.221, 0.893, 2.434]


def test_aci_variant_of_the_wide_cirsoc_beam() -> None:
    beam = _beam(150, 150, 30 * mm)
    Node(section=beam, forces=[Forces(label="C1", M_y=5000 * kNm, V_z=5000 * kN)]).design()
    geometry = beam.section_geometry
    assert _cm(geometry.leg_x) == [3.8, 32.28, 60.76, 89.24, 117.72, 146.2]
    assert [s.legs for s in geometry.stirrups] == [(0, 5)]
    assert geometry.arrangement("en") == "perimeter stirrup + 4 open legs"


# ---------------------------------------------------------------------------
# Invariants tied to the check
# ---------------------------------------------------------------------------


def _centroid_from_face(bars: tuple[BarPosition, ...], face: str, height_cm: float) -> float:
    areas = [b.d_b.to("cm").magnitude ** 2 for b in bars]
    ys = [b.y.to("cm").magnitude if face == "bottom" else height_cm - b.y.to("cm").magnitude for b in bars]
    return sum(a * y for a, y in zip(areas, ys)) / sum(areas)


def _check_invariants(beam: RectangularBeam) -> None:
    geometry = beam.section_geometry
    width = beam.width.to("cm").magnitude
    height = beam.height.to("cm").magnitude
    c_c = beam.c_c.to("cm").magnitude
    d_st = beam._stirrup_d_b.to("cm").magnitude
    assert geometry.stirrup_d_b.to("cm").magnitude == pytest.approx(d_st)

    legs = [x.to("cm").magnitude for x in geometry.leg_x]
    if legs:
        assert legs[0] == pytest.approx(c_c + d_st / 2)
        assert legs[-1] == pytest.approx(width - c_c - d_st / 2)
        gaps = [b - a for a, b in zip(legs, legs[1:])]
        assert gaps == pytest.approx([beam._leg_spacing_across_width().to("cm").magnitude] * len(gaps))

    for face, suffix in (("bottom", "b"), ("top", "t")):
        bars = geometry.bars_on(face)
        for bar in bars:
            radius = bar.d_b.to("cm").magnitude / 2
            assert bar.x.to("cm").magnitude - radius >= c_c + d_st - 1e-9
            assert bar.x.to("cm").magnitude + radius <= width - c_c - d_st + 1e-9
        layer_1 = max(getattr(beam, f"_d_b1_{suffix}"), getattr(beam, f"_d_b2_{suffix}"))
        offsets = {1: None, 2: layer_1 + beam.settings.layers_spacing}
        for layer, (a, b) in ((1, (1, 2)), (2, (3, 4))):
            row = geometry.bars_on(face, layer)
            n_a, n_b = getattr(beam, f"_n{a}_{suffix}"), getattr(beam, f"_n{b}_{suffix}")
            if len(row) >= 2 and len(row) == n_a + n_b:
                clear = [
                    (q.x - p.x).to("cm").magnitude - (p.d_b + q.d_b).to("cm").magnitude / 2
                    for p, q in zip(row, row[1:])
                ]
                model = beam._layer_clear_spacing(
                    n_a, getattr(beam, f"_d_b{a}_{suffix}"), n_b, getattr(beam, f"_d_b{b}_{suffix}"), offsets[layer]
                )
                assert clear == pytest.approx([model.to("cm").magnitude] * len(clear), rel=1e-12)
        if bars:
            c_mec = getattr(beam, f"_c_mec_{'bot' if face == 'bottom' else 'top'}").to("cm").magnitude
            d = getattr(beam, f"_d_{'bot' if face == 'bottom' else 'top'}").to("cm").magnitude
            assert _centroid_from_face(bars, face, height) == pytest.approx(c_mec, rel=1e-12)
            assert height - _centroid_from_face(bars, face, height) == pytest.approx(d, rel=1e-12)


def test_the_invariants_hold_on_the_wide_cirsoc_beam(wide_cirsoc_beam: RectangularBeam) -> None:
    _check_invariants(wide_cirsoc_beam)


@pytest.mark.parametrize(
    "bottom, top, stirrups",
    [
        ({"n1": 2, "d_b1": 20 * mm, "n2": 3, "d_b2": 16 * mm}, {"n1": 2, "d_b1": 12 * mm}, (1, 10 * mm, 15 * cm)),
        (
            {"n1": 2, "d_b1": 16 * mm, "n2": 2, "d_b2": 25 * mm, "n3": 2, "d_b3": 12 * mm, "n4": 1, "d_b4": 20 * mm},
            {"n1": 3, "d_b1": 16 * mm, "n2": 2, "d_b2": 10 * mm, "n3": 2, "d_b3": 10 * mm},
            (2, 8 * mm, 12 * cm),
        ),
        ({"n1": 1, "d_b1": 16 * mm}, {"n1": 2, "d_b1": 10 * mm}, (3, 6 * mm, 10 * cm)),
    ],
)
def test_the_invariants_hold_on_mixed_layers(bottom: dict, top: dict, stirrups: tuple) -> None:  # type: ignore[type-arg]
    beam = _beam(40, 60)
    beam.set_transverse_rebar(*stirrups)
    beam.set_longitudinal_rebar_bot(**bottom)
    beam.set_longitudinal_rebar_top(**top)
    _check_invariants(beam)


def test_a_beam_never_given_stirrups_still_reserves_the_starter_diameter() -> None:
    """The effective depth and the clear space keep the 8 mm starter: so does the geometry.

    Its bend too: a Ø16 seated on a 32 mm mandrel sits 16 - 8/√2 = 10.34 mm off the leg, 2.34 mm past its radius.
    """
    beam = _beam(30, 50)
    beam.set_longitudinal_rebar_bot(n1=3, d_b1=16 * mm)
    geometry = beam.section_geometry
    assert beam._stirrup_n == 0
    assert geometry.stirrup_d_b.to("mm").magnitude == pytest.approx(8)
    assert geometry.leg_x == () and geometry.stirrups == ()
    bottom = geometry.bars_on("bottom")
    seat = 16 - 8 / 2**0.5 - 8
    assert (bottom[0].x - bottom[0].d_b / 2).to("mm").magnitude == pytest.approx(25 + 8 + seat)
    assert (bottom[-1].x + bottom[-1].d_b / 2).to("mm").magnitude == pytest.approx(300 - 25 - 8 - seat)
    assert geometry.arrangement("en") == "no stirrups"
    _check_invariants(beam)

    beam.set_longitudinal_rebar_bot(n1=1, d_b1=16 * mm)
    (single,) = beam.section_geometry.bars_on("bottom")
    assert single.x.to("cm").magnitude == pytest.approx(15.0)
    assert single.y.to("mm").magnitude == pytest.approx(25 + 8 + 8)


# ---------------------------------------------------------------------------
# Order of the groups in a layer
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "n_a, n_b, order",
    [
        (2, 10, [1] + [2] * 10 + [1]),
        (3, 2, [1, 2, 1, 2, 1]),
        (4, 3, [1, 1, 2, 2, 2, 1, 1]),
        (5, 2, [1, 1, 2, 1, 2, 1, 1]),
        (1, 4, [2, 2, 1, 2, 2]),
        (1, 3, [2, 1, 2, 2]),
        (0, 4, [2, 2, 2, 2]),
        (2, 0, [1, 1]),
        (0, 0, []),
    ],
)
def test_group_order(n_a: int, n_b: int, order: list[int]) -> None:
    assert _group_order(n_a, n_b) == order


def test_mixed_diameters_follow_the_models_single_clear_gap() -> None:
    """ACI 30x50, c_c 25 mm, Ø10 stirrup, bottom 2Ø20 + 3Ø16: gap (230 - 2·2.93 - 40 - 48)/4 = 34.04 mm.

    A Ø20 seated in the 40 mm bend of the Ø10 sits 20 - 10/√2 = 12.93 mm off the leg, 2.93 mm past its radius.
    """
    beam = _beam(30, 50)
    beam.set_transverse_rebar(1, 10 * mm, 15 * cm)
    beam.set_longitudinal_rebar_bot(n1=2, d_b1=20 * mm, n2=3, d_b2=16 * mm)
    bottom = beam.section_geometry.bars_on("bottom", layer=1)
    assert [round(b.x.to("mm").magnitude, 6) for b in bottom] == [47.928932, 99.964466, 150.0, 200.035534, 252.071068]
    assert [b.group for b in bottom] == [1, 2, 2, 2, 1]


def test_a_group_with_no_diameter_keeps_its_slot_and_draws_no_bar() -> None:
    """``n2=1`` with no ``d_b2`` is counted by the clear spacing; the other bars stay where the check puts them."""
    beam = _beam(20, 50)
    beam.set_longitudinal_rebar_bot(n1=2, d_b1=16 * mm, n2=1)
    bottom = beam.section_geometry.bars_on("bottom")
    assert len(bottom) == 2
    gap = beam._layer_clear_spacing(2, 16 * mm, 1, 0 * mm).to("mm").magnitude
    assert (bottom[1].x - bottom[0].x).to("mm").magnitude == pytest.approx(2 * gap + 16)


def test_bars_on_a_face_and_a_layer() -> None:
    """The second layer sits behind the larger bar of the first."""
    beam = _beam(40, 60)
    beam.set_transverse_rebar(1, 10 * mm, 15 * cm)
    beam.set_longitudinal_rebar_bot(n1=2, d_b1=16 * mm, n2=1, d_b2=25 * mm, n3=2, d_b3=12 * mm)
    geometry = beam.section_geometry
    assert len(geometry.bars_on("bottom")) == 5
    assert len(geometry.bars_on("bottom", 1)) == 3
    second = geometry.bars_on("bottom", 2)
    assert [b.group for b in second] == [3, 3]
    spacing = beam.settings.layers_spacing.to("mm").magnitude  # type: ignore[union-attr]
    assert second[0].y.to("mm").magnitude == pytest.approx(25 + 10 + 25 + spacing + 6)
    top = geometry.bars_on("top", 1)
    assert top[0].y.to("mm").magnitude == pytest.approx(600 - 25 - 10 - top[0].d_b.to("mm").magnitude / 2)


# ---------------------------------------------------------------------------
# Crossties, slabs, units, export
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("count", [1])
def test_the_cage_helper_rejects_one_leg(count) -> None:
    with pytest.raises(ValueError, match="At least two"):
        _cage([float(x) for x in range(count)], 0.5, 9.5)


def test_an_open_leg_has_no_invented_hooks() -> None:
    from mento.section_geometry import Crosstie

    tie = Crosstie(leg=7, x=10 * cm, y_bottom=1 * cm, y_top=9 * cm)
    assert tie.hooks == ()


@pytest.mark.parametrize("element", [OneWaySlab, Footing])
def test_a_slab_strip_publishes_no_bars_and_no_legs(element: type) -> None:
    slab = element(
        label="S",
        concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=100 * cm,
        height=40 * cm,
        c_c=50 * mm,
    )
    slab.set_slab_longitudinal_rebar_bot(d_b1=12 * mm, s_b1=15 * cm)
    slab.set_slab_transverse_rebar(d_b=10 * mm, s_long=10 * cm, s_trans=20 * cm)
    geometry = slab.section_geometry
    assert geometry.layout == "grid"
    assert geometry.bars == () and geometry.leg_x == () and geometry.stirrups == ()
    assert geometry.width.to("cm").magnitude == pytest.approx(100)
    assert geometry.s_w.to("cm").magnitude == pytest.approx(20)
    assert geometry.arrangement() == ""
    assert slab.reinforcement.transverse.n_legs > 0


@pytest.mark.parametrize("element", [OneWaySlab, Footing])
def test_grid_bars_are_not_restricted_by_stirrup_bend_limits(element: type) -> None:
    slab = element(
        label="S32",
        concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=100 * cm,
        height=40 * cm,
        c_c=50 * mm,
    )
    slab.set_slab_transverse_rebar(d_b=32 * mm, s_long=15 * cm, s_trans=20 * cm)
    assert slab.section_geometry.layout == "grid"
    assert slab.section_geometry.stirrups == ()


def test_an_imperial_section_is_in_inches() -> None:
    beam = RectangularBeam(
        label="I",
        concrete=Concrete_ACI_318_19(name="C4", f_c=4 * ksi),
        steel_bar=SteelBar(name="G60", f_y=60 * ksi),
        width=12 * inch,
        height=24 * inch,
        c_c=1.5 * inch,
    )
    beam.set_transverse_rebar(n_stirrups=1, d_b=0.375 * inch, s_l=6 * inch)
    beam.set_longitudinal_rebar_bot(n1=3, d_b1=0.75 * inch)
    geometry = beam.section_geometry
    assert str(geometry.width.units) == str((1 * inch).units)
    assert geometry.leg_x[0].magnitude == pytest.approx(1.5 + 0.1875)
    assert geometry.leg_x[-1].magnitude == pytest.approx(12 - 1.5 - 0.1875)
    # A #3 bends on a 1.5 in mandrel: a #6 seated in it sits 0.75 - 0.375/√2 off the leg.
    assert geometry.bars[0].x.magnitude == pytest.approx(1.5 + 0.375 + 0.75 - 0.375 / 2**0.5)
    _check_invariants(beam)


def test_to_dict_gives_plain_floats(wide_cirsoc_beam: RectangularBeam) -> None:
    data = wide_cirsoc_beam.section_geometry.to_dict("cm")
    assert data["unit"] == "cm" and data["layout"] == "stirrups"
    assert data["width"] == pytest.approx(150.0)
    assert data["stirrup_bend_inner_diameter"] == pytest.approx(4.8)
    assert data["leg_x"][1] == pytest.approx(19.4667, abs=1e-4)
    assert data["stirrups"][0] == {
        "legs": [0, 9],
        "x_left": pytest.approx(3.6),
        "x_right": pytest.approx(146.4),
        "y_bottom": pytest.approx(3.6),
        "y_top": pytest.approx(146.4),
        "perimeter": True,
    }
    assert [tie["leg"] for tie in data["crossties"]] == list(range(1, 9))
    assert data["bars"][0] == {
        "x": pytest.approx(6.0343, abs=1e-4),
        "y": pytest.approx(5.8),
        "d_b": pytest.approx(3.2),
        "face": "bottom",
        "layer": 1,
        "group": 1,
    }
    assert all(isinstance(v, float) for v in data["leg_x"])
    assert wide_cirsoc_beam.section_geometry.to_dict("mm")["width"] == pytest.approx(1500.0)


def test_to_dict_carries_a_crosstie() -> None:
    from mento.section_geometry import Crosstie

    geometry = build_section_geometry(_beam())
    with_tie = SectionGeometry(
        **{**geometry.__dict__, "crossties": (Crosstie(leg=1, x=10 * cm, y_bottom=3 * cm, y_top=57 * cm),)}
    )
    assert with_tie.to_dict("cm")["crossties"] == [
        {
            "leg": 1,
            "x": 10.0,
            "y_bottom": 3.0,
            "y_top": 57.0,
            "hooks": [],
            "bend_inner_diameter": None,
            "extension": None,
            "side": 1,
            "alternate_hooks": False,
            "engaged_bars": [],
        }
    ]


def test_a_wall_has_no_section_geometry() -> None:
    wall = ShearWall(
        label="W",
        concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        thickness=20 * cm,
        length=3 * m,
        height=3 * m,
        c_c=25 * mm,
    )
    with pytest.raises(NotABeamError):
        wall.section_geometry


def test_the_geometry_is_exported() -> None:
    assert mento.SectionGeometry.__name__ == "SectionGeometry"
    assert "SectionGeometry" in mento.__all__
