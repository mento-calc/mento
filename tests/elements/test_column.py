"""RectangularColumn and CircularColumn: the shear of a column section in each direction.

The plan is docs/architecture/column-shear-roadmap.md, Phase B. The expected
values are worked by hand in each docstring; the equivalence tests hold the
column to RectangularBeam on the same rectangle, which is what the roadmap
asks for the clauses the two share.
"""

import math
from typing import Any, Iterator

import pytest

import mento
from mento import (
    CircularColumn,
    ColumnShearCheck,
    Concrete_ACI_318_19,
    Concrete_CIRSOC_201_25,
    Concrete_EN_1992_2004,
    DesignNotRunError,
    Forces,
    Node,
    RectangularBeam,
    RectangularColumn,
    SteelBar,
)
from mento.i18n import ES
from mento.units import MPa, cm, inch, kip, kN, kNm, ksi, mm, psi

STEEL = SteelBar(name="ADN 420", f_y=420 * MPa)


@pytest.fixture(autouse=True)
def english() -> Iterator[None]:
    mento.set_language("en")
    yield
    mento.set_language("en")


def _column(concrete: Any = None, width: Any = 30 * cm, height: Any = 50 * cm) -> RectangularColumn:
    column = RectangularColumn(
        label="C1",
        concrete=concrete or Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
        steel_bar=STEEL,
        width=width,
        height=height,
        c_c=25 * mm,
    )
    column.set_longitudinal_rebar(d_b_corner=20 * mm, n_width=1, d_b_width=16 * mm, n_height=2, d_b_height=16 * mm)
    return column


def _z(checks: tuple[ColumnShearCheck, ...]) -> ColumnShearCheck:
    return next(check for check in checks if check.direction == "z")


def _y(checks: tuple[ColumnShearCheck, ...]) -> ColumnShearCheck:
    return next(check for check in checks if check.direction == "y")


# ---------------------------------------------------------------------------
# The same numbers as the beam where the clauses are the same
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("concrete_class", [Concrete_ACI_318_19, Concrete_CIRSOC_201_25], ids=["ACI", "CIRSOC"])
@pytest.mark.parametrize("N_kN", [300.0, 0.0, -300.0], ids=["compression", "no-axial", "tension"])
@pytest.mark.parametrize("V_kN", [50.0, 150.0, 400.0])
@pytest.mark.parametrize("ties", [True, False], ids=["ties", "bare"])
def test_the_z_direction_is_the_beam_of_the_same_rectangle(
    concrete_class: type, N_kN: float, V_kN: float, ties: bool
) -> None:
    """V_z of a 30x50 column, the corners Ø20 and one Ø16 between them on the
    faces of length width, is the shear of a 30x50 beam with 2Ø20 + 1Ø16 on
    each face and the same tie: V_c with N_u/(6·A_g), V_s, the section limit
    and the spacing rows of Table 9.7.6.2.2 that Table 10.7.6.5.2 sends to.
    The area asked for is compared past both thresholds, where the column's
    §10.6.2.1 and the beam's §9.6.3.1 agree on requiring it."""
    concrete = concrete_class(name="H25", f_c=25 * MPa)
    column = _column(concrete)
    beam = RectangularBeam(label="B", concrete=concrete, steel_bar=STEEL, width=30 * cm, height=50 * cm, c_c=25 * mm)
    beam.set_longitudinal_rebar_bot(2, 20 * mm, 1, 16 * mm)
    beam.set_longitudinal_rebar_top(2, 20 * mm, 1, 16 * mm)
    if ties:
        column.set_ties(d_b=10 * mm, s=20 * cm)
        beam.set_transverse_rebar(d_b=10 * mm, s_l=20 * cm, legs=2)
    else:
        # The beam assumes a starting stirrup in its depth; the column with no
        # ties has none, so the beam is told so to stand for it.
        beam.set_transverse_rebar(0, 0 * mm, 0 * cm)
    force = Forces(label="U", N_x=N_kN * kN, V_z=V_kN * kN)

    (on_beam,) = beam.shear_check_results([force])
    on_column = _z(column.shear_check_results([force]))

    assert on_column.V_concrete.to("kN").magnitude == pytest.approx(on_beam.V_concrete.to("kN").magnitude, rel=1e-9)
    assert on_column.V_capacity.to("kN").magnitude == pytest.approx(on_beam.V_capacity.to("kN").magnitude, rel=1e-9)
    assert on_column.DCR == pytest.approx(on_beam.DCR, rel=1e-9)
    if V_kN >= 150 and ties:
        assert on_column.reinforcement_required
        assert on_column.A_v_req.to("cm**2/m").magnitude == pytest.approx(
            on_beam.A_v_req.to("cm**2/m").magnitude, rel=1e-9
        )
        assert on_column.s_max_l.to("cm").magnitude == pytest.approx(on_beam.s_max_l_table.to("cm").magnitude)
        assert on_column.s_max_w.to("cm").magnitude == pytest.approx(on_beam.s_max_w.to("cm").magnitude)


def test_the_y_direction_is_the_beam_turned() -> None:
    """V_y reads the column turned: a 50x30 beam with 2Ø20 + 2Ø16 on each face."""
    column = _column()
    column.set_ties(d_b=10 * mm, s=20 * cm)
    beam = RectangularBeam(
        label="B", concrete=column.concrete, steel_bar=STEEL, width=50 * cm, height=30 * cm, c_c=25 * mm
    )
    beam.set_longitudinal_rebar_bot(2, 20 * mm, 2, 16 * mm)
    beam.set_longitudinal_rebar_top(2, 20 * mm, 2, 16 * mm)
    beam.set_transverse_rebar(d_b=10 * mm, s_l=20 * cm, legs=2)

    (on_beam,) = beam.shear_check_results([Forces(label="U", N_x=200 * kN, V_z=180 * kN)])
    on_column = _y(column.shear_check_results([Forces(label="U", N_x=200 * kN, V_y=180 * kN)]))

    assert on_column.DCR == pytest.approx(on_beam.DCR, rel=1e-9)
    assert on_column.A_v_req.to("cm**2/m").magnitude == pytest.approx(on_beam.A_v_req.to("cm**2/m").magnitude)


# ---------------------------------------------------------------------------
# By hand
# ---------------------------------------------------------------------------


def test_a_compressed_rectangle_with_two_diameters_of_leg_by_hand() -> None:
    """30x50, H25, cover 25 mm, Ø20 corners and 1Ø16 between them on the faces
    of length 30; tie Ø10 every 20 cm with one Ø6 crosstie on those faces.
    N_u = 300 kN, V_z = 150 kN.

    V_z: b_w = 300, far face 2Ø20 + 1Ø16, A_s = 628.3 + 201.1 = 829.4 mm²,
    centroid (628.3·10 + 201.1·8)/829.4 = 9.52 mm, d = 500 - 25 - 10 - 9.52 =
    455.5 mm. The legs: the tie's two sides and the Ø6, A_v = (2·78.54 +
    28.27)/200 = 0.927 mm²/mm, past A_v,min = 0.35/420·300 = 0.25 (Table
    9.6.3.4), so Table 22.5.5.1(a): v_c = 0.17·5 + 300000/(6·150000) =
    1.183 MPa, ØVc = 0.75·1.183·300·455.5 = 121.3 kN. 150 kN > 0.5·ØVc: shear
    reinforcement required (§10.6.2.1). V_s,req = (150 - 121.3)/0.75 = 38.3 kN,
    A_v,req = max(38.3e3/(420·455.5), 0.25) = 0.25 mm²/mm = 2.50 cm²/m.
    ØVn = 0.75·(161.7 + 0.927·420·455.5) = 254.3 kN.
    """
    column = _column()
    column.set_ties(d_b=10 * mm, s=20 * cm, crossties_width=1, d_b_crosstie=6 * mm)
    check = _z(column.shear_check_results([Forces(label="U", N_x=300 * kN, V_z=150 * kN)]))

    A_s = 2 * math.pi * 20**2 / 4 + math.pi * 16**2 / 4
    d = 500 - 25 - 10 - (2 * math.pi * 20**2 / 4 * 10 + math.pi * 16**2 / 4 * 8) / A_s
    A_v = (2 * math.pi * 10**2 / 4 + math.pi * 6**2 / 4) / 200
    V_c = (0.17 * 5 + 300e3 / (6 * 300 * 500)) * 300 * d
    assert check.d.to("mm").magnitude == pytest.approx(d)
    assert check.A_v.to("cm**2/m").magnitude == pytest.approx(A_v * 10)
    assert check.V_concrete.to("kN").magnitude == pytest.approx(0.75 * V_c / 1e3)
    assert check.reinforcement_required
    assert check.A_v_req.to("cm**2/m").magnitude == pytest.approx(0.35 / 420 * 300 * 10)
    assert check.V_capacity.to("kN").magnitude == pytest.approx(0.75 * (V_c + A_v * 420 * d) / 1e3)
    assert check.DCR == pytest.approx(150e3 / (0.75 * (V_c + A_v * 420 * d)))


def test_a_compressed_column_needs_no_shear_reinforcement_below_half_phi_V_c() -> None:
    """§10.6.2.1 against §9.6.3.1. The column of the test above with a tie Ø8
    every 25 cm (A_v = 0.402 mm²/mm, past A_v,min = 0.25: Table 22.5.5.1(a)),
    d = 500 - 25 - 8 - 9.52 = 457.5 mm, under N_u = 300 kN, V_z = 55 kN:
    ØVc = 0.75·1.183·300·457.5 = 121.8 kN and 0.5·ØVc = 60.9 kN, so the column
    asks for no shear reinforcement. A beam of the same rectangle is held to
    φ·0.083·√f'c·b_w·d = 0.75·0.083·5·300·457.5 = 42.7 kN, which ignores the
    axial load, and asks it for A_v,min."""
    column = _column()
    column.set_ties(d_b=8 * mm, s=25 * cm)
    beam = RectangularBeam(
        label="B", concrete=column.concrete, steel_bar=STEEL, width=30 * cm, height=50 * cm, c_c=25 * mm
    )
    beam.set_longitudinal_rebar_bot(2, 20 * mm, 1, 16 * mm)
    beam.set_longitudinal_rebar_top(2, 20 * mm, 1, 16 * mm)
    beam.set_transverse_rebar(d_b=8 * mm, s_l=25 * cm, legs=2)
    force = Forces(label="U", N_x=300 * kN, V_z=55 * kN)

    check = _z(column.shear_check_results([force]))
    (on_beam,) = beam.shear_check_results([force])

    assert not check.reinforcement_required
    assert check.A_v_req.magnitude == 0 and check.A_v_min.magnitude == 0
    assert check.s_max_l is None and check.s_max_w is None
    assert on_beam.A_v_req.magnitude > 0
    assert column.warnings == ()


def test_a_circle_in_tension_by_hand() -> None:
    """Ø50, H25, 8Ø20, hoop Ø10 every 15 cm, N_u = -500 kN, V = 200 kN.

    §22.5.2.2: b_w = 500, d = 400 mm. A_g = π·500²/4 = 196 350 mm². The bars
    past the centre line, (8 - 1)//2 = 3Ø20, A_s = 942.5 mm². The hoop is two
    legs: A_v = 2·78.54/150 = 1.047 mm²/mm, past A_v,min = 0.35/420·500 = 0.417.
    Table 22.5.5.1(a): 0.17·5 - 500000/(6·196350) = 0.425 MPa; (b): 0.66 ·
    (942.5/200000)^(1/3)·5 - 0.424 = 0.129 MPa. ØVc = 0.75·0.425·500·400 =
    63.8 kN, the same in both directions.
    """
    column = CircularColumn(
        label="C2",
        concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
        steel_bar=STEEL,
        diameter=50 * cm,
        c_c=30 * mm,
    )
    column.set_longitudinal_rebar(n=8, d_b=20 * mm)
    column.set_hoops(d_b=10 * mm, s=15 * cm)
    checks = column.shear_check_results([Forces(label="T", N_x=-500 * kN, V_y=200 * kN, V_z=200 * kN)])

    v_c = 0.17 * 5 - 500e3 / (6 * math.pi * 500**2 / 4)
    for check in checks:
        assert check.b_w.to("mm").magnitude == pytest.approx(500)
        assert check.d.to("mm").magnitude == pytest.approx(400)
        assert check.A_v.to("cm**2/m").magnitude == pytest.approx(2 * math.pi * 10**2 / 4 / 150 * 10)
        assert check.V_concrete.to("kN").magnitude == pytest.approx(0.75 * v_c * 500 * 400 / 1e3)
        assert check.s_w is None and check.s_max_w is None
        assert math.isfinite(check.DCR)


def test_a_column_keeps_the_cap_on_the_root_of_f_c() -> None:
    """§22.5.3.1 caps √f'c at 8.3 MPa for V_c and §22.5.3.2 lifts it for beams
    and joists only. A 30x50 column of H80 with ties past A_v,min, N = 0:
    v_c = 0.17·8.3 (Table 22.5.5.1(a)), not 0.17·√80."""
    column = _column(Concrete_ACI_318_19(name="H80", f_c=80 * MPa))
    column.set_ties(d_b=10 * mm, s=10 * cm)
    check = _z(column.shear_check_results([Forces(label="U", V_z=100 * kN)]))
    d = check.d.to("mm").magnitude
    assert check.V_concrete.to("kN").magnitude == pytest.approx(0.75 * 0.17 * 8.3 * 300 * d / 1e3)


def test_the_cirsoc_column_takes_its_own_spacing_caps() -> None:
    """Table 10.7.6.5.2 is Table 9.7.6.2.2: d/2 along, capped at 600 mm (ACI
    318-19) or 400 mm (CIRSOC 201-25). A 100x100 column has d/2 near 475 mm."""
    force = Forces(label="U", V_z=1500 * kN)
    caps = []
    for concrete in (Concrete_ACI_318_19(name="H25", f_c=25 * MPa), Concrete_CIRSOC_201_25(name="H25", f_c=25 * MPa)):
        column = _column(concrete, width=100 * cm, height=100 * cm)
        column.set_ties(d_b=12 * mm, s=15 * cm)
        caps.append(_z(column.shear_check_results([force])).s_max_l.to("mm").magnitude)
    d = 1000 - 25 - 12 - (2 * 400 * 10 + 256 * 8) / (2 * 400 + 256)
    assert caps[0] == pytest.approx(d / 2)
    assert caps[1] == pytest.approx(400)


def test_the_legs_across_are_the_tie_and_the_crossties_at_their_bars() -> None:
    """V_y of the 30x50 reads the faces of length 50: two Ø16 between the Ø20
    corners, their centres at ±(250 - 25 - 10 - 10)/3 = ±68.3 mm, and one
    crosstie on the second of them. The tie's sides at ±(250 - 25 - 5) =
    ±220 mm, so the legs stand at -220, 68.3 and 220: the widest gap 288.3 mm.
    With two crossties it is 220 - 68.3 = 151.7 mm."""
    column = _column()
    column.set_ties(d_b=10 * mm, s=20 * cm, crossties_height=1)
    one = _y(column.shear_check_results([Forces(label="U", V_y=10 * kN)])).s_w
    column.set_ties(d_b=10 * mm, s=20 * cm, crossties_height=2)
    two = _y(column.shear_check_results([Forces(label="U", V_y=10 * kN)])).s_w
    bar = 205 / 3
    assert one.to("mm").magnitude == pytest.approx(220 + bar)
    assert two.to("mm").magnitude == pytest.approx(220 - bar)


def test_a_us_customary_column_reports_in_kip_and_inches() -> None:
    concrete = Concrete_ACI_318_19(name="C4000", f_c=4000 * psi)
    column = RectangularColumn(
        label="C",
        concrete=concrete,
        steel_bar=SteelBar(name="G60", f_y=60 * ksi),
        width=16 * inch,
        height=24 * inch,
        c_c=1.5 * inch,
    )
    column.set_longitudinal_rebar(d_b_corner=1 * inch, n_width=1, n_height=2)
    column.set_ties(d_b=0.5 * inch, s=6 * inch)
    check = _z(column.shear_check_results([Forces(label="U", N_x=100 * kip, V_z=60 * kip)]))
    assert check.V_capacity.units == (1 * kip).units
    assert check.d.to("inch").magnitude == pytest.approx(24 - 1.5 - 0.5 - 0.5)
    assert 0 < check.DCR < 1


# ---------------------------------------------------------------------------
# EN 1992-1-1
# ---------------------------------------------------------------------------

EN_STEEL = SteelBar(name="B500S", f_y=500 * MPa)


def _en_column(**kwargs: Any) -> RectangularColumn:
    column = RectangularColumn(
        label="C1",
        concrete=Concrete_EN_1992_2004(name="C30", f_c=30 * MPa),
        steel_bar=EN_STEEL,
        width=30 * cm,
        height=50 * cm,
        c_c=25 * mm,
        **kwargs,
    )
    column.set_longitudinal_rebar(d_b_corner=20 * mm, n_width=1, d_b_width=16 * mm)
    return column


@pytest.mark.parametrize("N_kN", [500.0, 0.0, -300.0], ids=["compression", "no-axial", "tension"])
@pytest.mark.parametrize("V_kN", [40.0, 150.0, 600.0])
@pytest.mark.parametrize("ties", [True, False], ids=["ties", "bare"])
def test_the_en_z_direction_is_the_beam_of_the_same_rectangle(N_kN: float, V_kN: float, ties: bool) -> None:
    """V_z of the EN column against the EN beam of the same rectangle: V_Rd,c
    with σ_cp, the truss at the angle the demand fixes, V_Rd,max, the DCR, and
    the spacings of §9.2.2(6), (8) where shear reinforcement is required. The
    area asked for is compared past V_Rd,c and the §9.2.2(5) minimum the beam
    keeps (2.63 cm²/m on this one), which a column does not. α_cw = 1 on both:
    the beam does not read Expression (6.11aN)."""
    column = _en_column(alpha_cw_from_axial_load=False)
    beam = RectangularBeam(
        label="B", concrete=column.concrete, steel_bar=EN_STEEL, width=30 * cm, height=50 * cm, c_c=25 * mm
    )
    beam.set_longitudinal_rebar_bot(2, 20 * mm, 1, 16 * mm)
    beam.set_longitudinal_rebar_top(2, 20 * mm, 1, 16 * mm)
    if ties:
        column.set_ties(d_b=10 * mm, s=20 * cm)
        beam.set_transverse_rebar(d_b=10 * mm, s_l=20 * cm, legs=2)
    else:
        beam.set_transverse_rebar(0, 0 * mm, 0 * cm)
    force = Forces(label="U", N_x=N_kN * kN, V_z=V_kN * kN)

    (on_beam,) = beam.shear_check_results([force])
    on_column = _z(column.shear_check_results([force]))

    assert on_column.V_concrete.to("kN").magnitude == pytest.approx(on_beam.V_concrete.to("kN").magnitude, rel=1e-9)
    assert on_column.V_capacity.to("kN").magnitude == pytest.approx(on_beam.V_capacity.to("kN").magnitude, rel=1e-9)
    assert on_column.DCR == pytest.approx(on_beam.DCR, rel=1e-9)
    if V_kN >= 150:
        assert on_column.reinforcement_required
        assert on_column.A_v_req.to("cm**2/m").magnitude == pytest.approx(
            on_beam.A_v_req.to("cm**2/m").magnitude, rel=1e-9
        )
    if V_kN >= 150 and ties:
        assert on_column.s_max_l.to("cm").magnitude == pytest.approx(on_beam.s_max_l_table.to("cm").magnitude)


def test_an_en_rectangle_by_hand() -> None:
    """30x50, C30, B500S, cover 25 mm, Ø20 corners and 1Ø16 between them on the
    faces of length 30, tie Ø10 every 20 cm; N_Ed = 500 kN, V_z = 150 kN.

    d = 500 - 25 - 10 - 9.52 = 455.5 mm; k = 1 + √(200/455.5) = 1.663;
    ρ_l = 829.4/(300·455.5) = 0.00607; f_cd = 30/1.5 = 20 MPa (α_cc = 1 for
    shear); σ_cp = 500000/150000 = 3.33 MPa, under 0.2·f_cd = 4. Expression
    (6.2.a): (0.12·1.663·(100·0.00607·30)^(1/3) + 0.15·3.33)·300·455.5 =
    140.0 kN, above the (6.2.b) floor. 150 kN > V_Rd,c: shear reinforcement
    required (§6.2.1(3)). z = 0.9·d = 409.9 mm, ν1 = 0.6·(1 - 30/250) = 0.528,
    V_Rd,max at cot θ = 2.5: 300·409.9·0.528·20/2.9 = 447.8 kN, so θ = 21.8°.
    A_sw/s,req = 150000/(409.9·434.8·2.5) = 0.337 mm²/mm, with no §9.2.2(5)
    minimum. V_Rd,s = 0.785·409.9·434.8·2.5 = 349.9 kN, under V_Rd,max.
    α_cw = 1 + 3.33/20 = 1.167 by Expression (6.11aN), on V_Rd,max.
    """
    column = _en_column()
    column.set_ties(d_b=10 * mm, s=20 * cm)
    check = _z(column.shear_check_results([Forces(label="U", N_x=500 * kN, V_z=150 * kN)]))

    A_s = 2 * math.pi * 20**2 / 4 + math.pi * 16**2 / 4
    d = 500 - 25 - 10 - (2 * math.pi * 20**2 / 4 * 10 + math.pi * 16**2 / 4 * 8) / A_s
    k = 1 + math.sqrt(200 / d)
    V_Rd_c = (0.18 / 1.5 * k * (100 * A_s / (300 * d) * 30) ** (1 / 3) + 0.15 * 500e3 / 150e3) * 300 * d
    z, f_ywd = 0.9 * d, 500 / 1.15
    cot = 1 / math.tan(math.radians(21.8))  # the 2.5 of §6.2.3(2), as mento takes θ = 21.8°
    A_v = 2 * math.pi * 10**2 / 4 / 200
    assert check.V_concrete.to("kN").magnitude == pytest.approx(V_Rd_c / 1e3)
    assert check.reinforcement_required
    assert check.A_v_min.magnitude == 0
    assert check.A_v_req.to("cm**2/m").magnitude == pytest.approx(150e3 / (z * f_ywd * cot) * 10)
    assert check.V_capacity.to("kN").magnitude == pytest.approx(A_v * z * f_ywd * cot / 1e3)
    alpha_cw = 1 + 500e3 / 150e3 / 20
    assert check.V_max.to("kN").magnitude == pytest.approx(alpha_cw * 300 * z * 0.528 * 20 / 2 / 1e3)
    assert check.s_max_l.to("mm").magnitude == pytest.approx(0.75 * d)


def test_an_en_column_under_v_rd_c_asks_for_no_minimum() -> None:
    """§6.2.1(4) asks a beam for the minimum of §9.2.2 under V_Rd,c; a column's
    ties are §9.5.3, detailing. The column of the test above under 40 kN."""
    column = _en_column()
    column.set_ties(d_b=6 * mm, s=30 * cm)
    check = _z(column.shear_check_results([Forces(label="U", N_x=500 * kN, V_z=40 * kN)]))
    assert not check.reinforcement_required
    assert check.A_v_req.magnitude == 0 and check.s_max_l is None
    assert column.warnings == ()


@pytest.mark.parametrize(
    ("N_kN", "alpha_cw"),
    [
        (500.0, 1 + 500e3 / 150e3 / 20),  # σ_cp = 3.33 MPa, under 0.25·f_cd = 5: 1 + σ_cp/f_cd
        (1200.0, 1.25),  # σ_cp = 8 MPa, between 0.25·f_cd and 0.5·f_cd
        (1650.0, 2.5 * (1 - 11 / 20)),  # σ_cp = 11 MPa, past 0.5·f_cd: 1.125, still above 1
        (2100.0, 2.5 * (1 - 14 / 20)),  # σ_cp = 14 MPa, past 0.6·f_cd: 0.75
        (-300.0, 1.0),  # tension
    ],
    ids=["first-branch", "plateau", "above-1", "below-1", "tension"],
)
def test_alpha_cw_follows_expression_6_11an_unless_turned_off(N_kN: float, alpha_cw: float) -> None:
    """Expression (6.11aN) by default (#210), with σ_cp = N_Ed/A_c on the
    150000 mm² of the column and f_cd = 20 MPa: V_Rd,max is α_cw times the one
    of ``alpha_cw_from_axial_load=False``, which keeps α_cw = 1. ``V_max`` is
    V_Rd,max at θ = 45°, so the ratio is α_cw alone."""
    force = [Forces(label="U", N_x=N_kN * kN, V_z=600 * kN)]
    default, off = _en_column(), _en_column(alpha_cw_from_axial_load=False)
    for column in (default, off):
        column.set_ties(d_b=10 * mm, s=20 * cm)
    ratio = _z(default.shear_check_results(force)).V_max / _z(off.shear_check_results(force)).V_max
    assert ratio.to("").magnitude == pytest.approx(alpha_cw)


def _en_circle(gamma_c: float = 1.5) -> CircularColumn:
    column = CircularColumn(
        label="C2",
        concrete=Concrete_EN_1992_2004(name="C30", f_c=30 * MPa, gamma_c=gamma_c),
        steel_bar=EN_STEEL,
        diameter=50 * cm,
        c_c=30 * mm,
    )
    column.set_longitudinal_rebar(n=8, d_b=20 * mm)
    column.set_hoops(d_b=10 * mm, s=15 * cm)
    return column


#: Ø50, cover 30, hoop Ø10, 8Ø20: r = 250, r_s = 250 - 30 - 10 - 10 = 200,
#: r_sv = 250 - 30 - 5 = 215, and by default d = r + 2·r_s/π, z = 0.77·d.
_R, _R_SV = 250.0, 215.0
_D_TRUSS = _R + 2 * 200 / math.pi
_Z_TRUSS = 0.77 * _D_TRUSS
_F_CTD = 0.7 * 0.3 * 30 ** (2 / 3) / 1.5
_F_YWD = 500 / 1.15
_COT = 1 / math.tan(math.radians(21.8))


def test_an_en_circle_uncracked_in_bending_takes_expression_6_4() -> None:
    """N_Ed = 1000 kN and no moment: M/W - N/A_c = -5.09 MPa, under f_ctd =
    1.35 MPa, so §6.2.2(2) admits Expression (6.4), Orr's Eq. (17):
    V_Rd,c = 3π·250²/4·√(1.35² + 5.09·1.35) = 434.6 kN, past V_Ed = 250 kN."""
    check = _z(_en_circle().shear_check_results([Forces(label="U", N_x=1000 * kN, V_z=250 * kN)]))
    sigma = 1000e3 / (math.pi * _R**2)
    expected = 3 * math.pi * _R**2 / 4 * math.sqrt(_F_CTD**2 + sigma * _F_CTD)
    assert check.V_concrete.to("kN").magnitude == pytest.approx(expected / 1e3)
    assert not check.reinforcement_required


def test_an_uncased_pile_reads_the_gamma_c_of_its_concrete() -> None:
    """A bored pile cast without a casing takes k_f·γ_c = 1.1·1.5 = 1.65
    (§2.4.2.5(2), #214). The circle of the test above: f_ctd and so Expression
    (6.4) read it, and V_Rd,max = ν1·f_cd·... falls by 1.5/1.65."""
    force = [Forces(label="U", N_x=1000 * kN, V_z=250 * kN)]
    cased, pile = _z(_en_circle().shear_check_results(force)), _z(_en_circle(1.65).shear_check_results(force))
    sigma, f_ctd = 1000e3 / (math.pi * _R**2), _F_CTD * 1.5 / 1.65
    expected = 3 * math.pi * _R**2 / 4 * math.sqrt(f_ctd**2 + sigma * f_ctd)
    assert pile.V_concrete.to("kN").magnitude == pytest.approx(expected / 1e3)
    assert (pile.V_max / cased.V_max).to("").magnitude == pytest.approx(1.5 / 1.65)


def test_an_en_circle_cracked_in_bending_takes_the_truss_of_orr() -> None:
    """N_Ed = 1000 kN, M_y = 200 kNm: M/W - N/A_c = 16.3 - 5.09 = 11.2 MPa,
    past f_ctd, so the circle is cracked and V_Rd,c is Expression (6.2.a) on
    the equivalent rectangle: B_w = min(2√(c(2r - c)), 2√(e(2r_sv - e))) with
    c = d - z and e = r + r_sv - d (Orr's Eqs. (10)-(13)), σ_cp capped at
    0.2·f_cd = 4 MPa. V_Ed = 250 kN asks for links: λ1 by Eq. (6) passes 0.85
    here, so 0.85, and A_sw/s = V_Ed/(0.85·z·f_ywd·cot θ)."""
    check = _z(_en_circle().shear_check_results([Forces(label="U", N_x=1000 * kN, M_y=200 * kNm, V_z=250 * kN)]))
    d, z = _D_TRUSS, _Z_TRUSS
    c, e = d - z, _R + _R_SV - d
    B_w = min(2 * math.sqrt(c * (2 * _R - c)), 2 * math.sqrt(e * (2 * _R_SV - e)))
    rho_l = 3 * math.pi * 20**2 / 4 / (B_w * d)
    k = 1 + math.sqrt(200 / d)
    V_Rd_c = (0.12 * k * (100 * rho_l * 30) ** (1 / 3) + 0.15 * 4.0) * B_w * d
    assert check.b_w.to("mm").magnitude == pytest.approx(B_w)
    assert check.d.to("mm").magnitude == pytest.approx(d)
    assert check.V_concrete.to("kN").magnitude == pytest.approx(V_Rd_c / 1e3)
    assert check.reinforcement_required
    assert check.A_v_req.to("mm**2/mm").magnitude == pytest.approx(250e3 / (0.85 * z * _F_YWD * _COT))
    A_v = 2 * math.pi * 10**2 / 4 / 150
    assert check.V_capacity.to("kN").magnitude == pytest.approx(0.85 * A_v * z * _F_YWD * _COT / 1e3)
    assert check.s_max_l.to("mm").magnitude == pytest.approx(0.75 * d)


def test_the_lever_arm_of_an_analysis_replaces_the_default() -> None:
    """d = 450, z = 400 mm from a sectional analysis: z_0 = d - r = 200 mm and
    Eq. (6) gives λ1 = 0.826, under 0.85, which the truss then takes."""
    column = _en_circle()
    column.set_lever_arm(d=450 * mm, z=400 * mm)
    check = _z(column.shear_check_results([Forces(label="U", M_y=100 * kNm, V_z=150 * kN)]))
    from mento.codes.en_1992_2004.equations.shear import circular_link_efficiency

    lambda_1 = circular_link_efficiency(200.0, 400.0, _R_SV)
    assert lambda_1 == pytest.approx(0.826, abs=0.001)
    assert check.d.to("mm").magnitude == pytest.approx(450)
    assert check.A_v_req.to("mm**2/mm").magnitude == pytest.approx(150e3 / (lambda_1 * 400 * _F_YWD * _COT))
    column.set_lever_arm()
    assert _z(column.shear_check_results([Forces(label="U", V_z=150 * kN)])).d.to("mm").magnitude == pytest.approx(
        _D_TRUSS
    )


def test_a_spiral_asks_for_more_than_hoops_by_its_pitch() -> None:
    """λ2 = ((p/(2π·r_sv))² + 1)^-0.5 with p = 150 mm, r_sv = 215 mm: 0.9939."""
    force = [Forces(label="U", M_y=200 * kNm, V_z=250 * kN)]
    hoops, spiral = _en_circle(), _en_circle()
    spiral.set_hoops(d_b=10 * mm, s=15 * cm, spiral=True)
    ratio = _z(spiral.shear_check_results(force)).A_v_req / _z(hoops.shear_check_results(force)).A_v_req
    assert ratio.to("").magnitude == pytest.approx(((150 / (2 * math.pi * _R_SV)) ** 2 + 1) ** 0.5)


def test_the_lever_arm_is_validated_and_aci_does_not_read_it() -> None:
    column = _en_circle()
    with pytest.raises(ValueError, match="both"):
        column.set_lever_arm(d=40 * cm)
    with pytest.raises(ValueError, match="shorter"):
        column.set_lever_arm(d=40 * cm, z=45 * cm)
    aci = CircularColumn(
        label="C",
        concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
        steel_bar=STEEL,
        diameter=50 * cm,
        c_c=30 * mm,
    )
    aci.set_longitudinal_rebar(n=8, d_b=20 * mm)
    aci.set_hoops(d_b=10 * mm, s=15 * cm)
    before = _z(aci.shear_check_results([Forces(label="U", V_z=100 * kN)]))
    aci.set_lever_arm(d=45 * cm, z=40 * cm)
    after = _z(aci.shear_check_results([Forces(label="U", V_z=100 * kN)]))
    assert after.d == before.d and after.DCR == before.DCR


# ---------------------------------------------------------------------------
# The element
# ---------------------------------------------------------------------------


def test_the_node_checks_both_directions_of_every_combination() -> None:
    column = _column()
    column.set_ties(d_b=10 * mm, s=15 * cm)
    forces = [Forces(label="A", N_x=100 * kN, V_y=40 * kN, V_z=80 * kN), Forces(label="B", N_x=50 * kN, V_z=20 * kN)]
    Node(column, forces).check()
    assert [(c.label, c.direction) for c in column.shear_checks] == [("A", "y"), ("A", "z"), ("B", "y"), ("B", "z")]
    assert column.shear_checks[0].V_demand.to("kN").magnitude == pytest.approx(40)


def test_results_are_dropped_with_the_ties_they_described() -> None:
    column = _column()
    column.set_ties(d_b=10 * mm, s=15 * cm)
    with pytest.raises(DesignNotRunError):
        column.shear_checks
    column.check([Forces(label="A", V_z=80 * kN)])
    assert column.shear_checks
    column.set_ties(d_b=8 * mm, s=15 * cm)
    with pytest.raises(DesignNotRunError):
        column.shear_checks
    assert column.warnings == ()


def test_what_the_column_does_not_do_says_so() -> None:
    column = _column()
    column.set_ties(d_b=10 * mm, s=15 * cm)
    force = [Forces(label="A", V_z=80 * kN)]
    for call in (column.design, column.design_shear, column.check_flexure, column.design_flexure):
        with pytest.raises(NotImplementedError, match="column-shear-roadmap"):
            call(force)


@pytest.mark.parametrize(
    "build, message",
    [
        (lambda c: c.set_ties(d_b=10 * mm, s=15 * cm, crossties_width=2), "crossties_width"),
        (lambda c: c.set_ties(d_b=0 * mm, s=0 * cm, crossties_height=1), "perimeter tie"),
        (lambda c: c.set_ties(d_b=10 * mm, s=0 * cm), "both"),
    ],
    ids=["more crossties than bars", "crossties without a tie", "a tie with no spacing"],
)
def test_impossible_ties_are_refused(build: Any, message: str) -> None:
    column = _column()
    with pytest.raises(ValueError, match=message):
        build(column)
        column.shear_check_results([Forces(label="A", V_z=80 * kN)])


def test_a_column_without_bars_is_refused() -> None:
    column = RectangularColumn(
        label="C",
        concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
        steel_bar=STEEL,
        width=30 * cm,
        height=30 * cm,
        c_c=25 * mm,
    )
    with pytest.raises(ValueError, match="longitudinal bars"):
        column.shear_check_results([Forces(label="A", V_z=80 * kN)])


# ---------------------------------------------------------------------------
# Warnings
# ---------------------------------------------------------------------------


def test_the_ties_a_shear_needs_are_warned_per_direction() -> None:
    """The 30x50 with a bare Ø6 tie every 30 cm under N = 0, V_y = 120 kN:
    reinforcement required, its area short, its spacing past d/2 and its legs
    past d across; V_z = 0 asks nothing. The moment is not checked."""
    column = _column()
    column.set_ties(d_b=6 * mm, s=30 * cm)
    column.check([Forces(label="U", V_y=120 * kN, M_y=40 * kNm)])
    codes = {(w.code, w.values.get("direction")) for w in column.warnings}
    assert codes == {
        ("column_ties_below_required", "y"),
        ("column_tie_spacing_exceeds_max", "y"),
        ("column_leg_spacing_exceeds_max", "y"),
        ("column_force_component_not_checked", None),
    }
    shortfall = next(w for w in column.warnings if w.code == "column_ties_below_required")
    assert shortfall.message.startswith("Ties for V_y")
    assert shortfall.combinations == ("U",)
    mento.set_language("es")
    assert next(w for w in column.warnings if w.code == "column_ties_below_required").message.startswith(
        "Estribos para V_y"
    )


def test_a_shear_past_the_section_is_warned() -> None:
    column = _column()
    column.set_ties(d_b=12 * mm, s=10 * cm)
    column.check([Forces(label="U", V_z=900 * kN)])
    limit = next(w for w in column.warnings if w.code == "column_shear_exceeds_section_limit")
    assert limit.values["direction"] == "z"
    assert limit.values["V"].to("kN").magnitude == pytest.approx(900)


def test_every_column_message_is_in_the_spanish_catalog() -> None:
    from mento.design_warnings import _MESSAGES

    assert [m for code, m in _MESSAGES.items() if code.startswith("column_") and m not in ES] == []


# ---------------------------------------------------------------------------
# Inputs refused, and what each entry point does
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "build, error, message",
    [
        (lambda c: c.set_longitudinal_rebar(d_b_corner=20), TypeError, "length Quantity"),
        (lambda c: c.set_longitudinal_rebar(d_b_corner=-20 * mm), ValueError, "greater than zero"),
        (lambda c: c.set_ties(d_b=-1 * mm, s=10 * cm), ValueError, "zero or more"),
        (lambda c: c.set_longitudinal_rebar(d_b_corner=20 * mm, n_width=1.5), TypeError, "integer"),
        (lambda c: c.set_longitudinal_rebar(d_b_corner=20 * mm, n_width=True), TypeError, "integer"),
        (lambda c: c.set_longitudinal_rebar(d_b_corner=20 * mm, n_width=-1), ValueError, "zero or more"),
        (lambda c: c.shear_section("x"), ValueError, "direction"),
    ],
    ids=[
        "not a length",
        "negative bar",
        "negative tie",
        "fractional count",
        "bool count",
        "negative count",
        "bad direction",
    ],
)
def test_bad_inputs_are_refused(build: Any, error: type, message: str) -> None:
    with pytest.raises(error, match=message):
        build(_column())


def test_a_cover_past_half_the_section_is_refused() -> None:
    concrete = Concrete_ACI_318_19(name="H25", f_c=25 * MPa)
    with pytest.raises(ValueError, match="half of the smallest"):
        RectangularColumn(label="C", concrete=concrete, steel_bar=STEEL, width=20 * cm, height=50 * cm, c_c=10 * cm)
    with pytest.raises(ValueError, match="half of the diameter"):
        CircularColumn(label="C", concrete=concrete, steel_bar=STEEL, diameter=20 * cm, c_c=10 * cm)


def test_a_circle_needs_its_bars() -> None:
    column = CircularColumn(
        label="C",
        concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
        steel_bar=STEEL,
        diameter=40 * cm,
        c_c=30 * mm,
    )
    with pytest.raises(ValueError, match="greater than zero"):
        column.set_longitudinal_rebar(n=0, d_b=20 * mm)
    with pytest.raises(ValueError, match="longitudinal bars"):
        column.shear_check_results([Forces(label="A", V_z=10 * kN)])


def test_the_gross_areas() -> None:
    assert _column().A_x.to("cm**2").magnitude == pytest.approx(1500)
    circle = CircularColumn(
        label="C",
        concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
        steel_bar=STEEL,
        diameter=40 * cm,
        c_c=30 * mm,
    )
    assert circle.A_x.to("cm**2").magnitude == pytest.approx(math.pi * 40**2 / 4)


def test_check_shear_is_the_check() -> None:
    column = _column()
    column.set_ties(d_b=10 * mm, s=15 * cm)
    column.check_shear([Forces(label="A", V_z=80 * kN)])
    assert [c.direction for c in column.shear_checks] == ["y", "z"]


def test_a_code_without_column_shear_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    """A code registered without ``check_column_shear`` names itself and the roadmap."""
    import dataclasses

    import mento.column_section
    from mento.codes.registry import design_code

    column = _column()
    bare = dataclasses.replace(design_code(column.concrete), title="A code", check_column_shear=None)
    monkeypatch.setattr(mento.column_section, "design_code", lambda concrete: bare)
    with pytest.raises(NotImplementedError, match="A code yet: see docs/architecture/column-shear-roadmap.md"):
        column.shear_check_results([Forces(label="A", V_z=80 * kN)])


def test_the_base_section_is_not_built_directly() -> None:
    from mento.column_section import ColumnSection

    base = ColumnSection(concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa), steel_bar=STEEL, c_c=25 * mm)
    with pytest.raises(NotImplementedError):
        base.shear_section("z")


def test_past_v_rd_max_at_45_the_strut_stays_at_45_degrees() -> None:
    """V_Ed past V_Rd,max(45°) = 300·409.9·0.528·20/2 = 649.5 kN: θ = 45° and V_Rd is the strut's."""
    column = _en_column()
    column.set_ties(d_b=12 * mm, s=5 * cm)
    check = _z(column.shear_check_results([Forces(label="U", V_z=900 * kN)]))
    assert check.V_capacity == check.V_max
    assert check.DCR > 1
