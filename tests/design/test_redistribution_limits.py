"""What the limits on moment redistribution read: eps_t, x_u/d and the EN delta.

ACI 318-19 / CIRSOC 201-25 §6.6.5 allow redistribution only where the net
tensile strain eps_t is at least 0.0075, and at most 1000*eps_t percent (20 %).
EN 1992-1-1 §5.5(4) bounds the ratio delta by the neutral axis,
delta >= k_1 + k_2*x_u/d. Both are read on the section as reinforced, every bar
at the stress its strain gives it. Each expected value below is worked out by
hand from the section, not read back from mento.
"""

import math

import pytest

from mento import (
    Concrete_ACI_318_19,
    Concrete_CIRSOC_201_25,
    Concrete_EN_1992_2004,
    Forces,
    Node,
    RectangularBeam,
    SteelBar,
)
from mento import GPa, MPa, cm, kNm, mm
from mento.codes.EN_1992_2004_beam import _compression_zone_limits_EN_1992_2004
from mento.design_results import FlexureCheck, FlexureFaceCheck, envelope_flexure_face
from mento.slab import Footing

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")


def _bar(d_b: float) -> float:
    """Area of one bar of diameter ``d_b`` mm, in mm²."""
    return math.pi * d_b**2 / 4


def _checked(beam: RectangularBeam, M: float) -> FlexureCheck:
    """The flexure result of one combination with moment ``M`` kN·m."""
    Node(section=beam, forces=[Forces(label="C1", M_y=M * kNm)]).check_flexure()
    return beam.flexure_checks[0]


# ---------------------------------------------------------------------------
# eps_t -- ACI 318-19 and CIRSOC 201-25
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("concrete_class", [Concrete_ACI_318_19, Concrete_CIRSOC_201_25])
def test_epsilon_t_of_a_singly_reinforced_face_matches_the_hand_calculation(concrete_class: type) -> None:
    # 20x50, cover 25 to an Ø8 stirrup, 3Ø16 bottom: one layer, so d_t = d.
    concrete = concrete_class(name="H25", f_c=25 * MPa)
    beam = RectangularBeam(
        label="V1",
        concrete=concrete,
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=20 * cm,
        height=50 * cm,
        c_c=25 * mm,
    )
    beam.set_transverse_rebar(n_stirrups=1, d_b=8 * mm, s_l=20 * cm)
    beam.set_longitudinal_rebar_bot(n1=3, d_b1=16 * mm)
    beam.set_longitudinal_rebar_top(n1=0, d_b1=0 * mm)

    check = _checked(beam, 60)

    d_t = 500 - 25 - 8 - 16 / 2
    A_s = 3 * _bar(16)
    a = A_s * 420 / (0.85 * 25 * 200)
    c = a / 0.85  # beta_1 = 0.85 up to 28 MPa
    epsilon_t = 0.003 * (d_t - c) / c
    assert epsilon_t == pytest.approx(0.01663, abs=1e-5)
    assert check.bottom.epsilon_t == pytest.approx(epsilon_t, rel=1e-9)
    # The top carries no steel, and EN's ratio is not this code's.
    assert check.top.epsilon_t is None
    assert check.bottom.x_u_d is None and check.top.x_u_d is None


def test_epsilon_t_of_an_over_reinforced_face_is_the_strain_compatibility_one() -> None:
    # 20x40 with 4Ø25 and no top steel: past A_s_max, the steel stays elastic,
    # and c is the root of 0.85*f_c*b*beta_1*c = A_s*E_s*0.003*(d - c)/c.
    beam = RectangularBeam(
        label="V2",
        concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=20 * cm,
        height=40 * cm,
        c_c=25 * mm,
    )
    beam.set_transverse_rebar(n_stirrups=1, d_b=8 * mm, s_l=15 * cm)
    beam.set_longitudinal_rebar_bot(n1=4, d_b1=25 * mm)
    beam.set_longitudinal_rebar_top(n1=0, d_b1=0 * mm)

    check = _checked(beam, 150)

    assert beam.steel_bar.E_s == 200 * GPa
    d = 400 - 25 - 8 - 25 / 2
    A_s = 4 * _bar(25)
    k = 0.85 * 25 * 200 * 0.85
    T = A_s * 200_000 * 0.003
    c = (-T + math.sqrt(T**2 + 4 * k * T * d)) / (2 * k)
    epsilon_t = 0.003 * (d - c) / c
    assert epsilon_t < 420 / 200_000  # the steel has not yielded
    assert check.bottom.epsilon_t == pytest.approx(epsilon_t, rel=1e-6)
    # Below 0.0075: §6.6.5 allows this face no redistribution.
    assert check.bottom.epsilon_t < 0.0075


def test_epsilon_t_of_a_shallow_section_counts_the_opposite_bars_that_pull() -> None:
    # A 14 cm slab strip under ACI, 7Ø12 bottom and 7Ø20 top, below A_s_max:
    # the top bars lie below the neutral axis and pull, so eps_t drops below
    # the 0.0075 that §6.6.5 asks for. Equilibrium, with the displaced
    # concrete deducted from the top bars as mento's strain compatibility does:
    # 0.85*f_c*b*beta_1*c + A_s'*(E_s*0.003*(c - d')/c - 0.85*f_c) = A_s*f_y.
    beam = RectangularBeam(
        label="L1",
        concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=100 * cm,
        height=14 * cm,
        c_c=25 * mm,
    )
    beam.set_transverse_rebar(n_stirrups=1, d_b=8 * mm, s_l=10 * cm)
    beam.set_longitudinal_rebar_bot(n1=7, d_b1=12 * mm)
    beam.set_longitudinal_rebar_top(n1=7, d_b1=20 * mm)

    check = _checked(beam, 20)

    d = 140 - 25 - 8 - 12 / 2
    d_prime = 25 + 8 + 20 / 2
    A_s, A_s_prime = 7 * _bar(12), 7 * _bar(20)
    k = 0.85 * 25 * 1000 * 0.85
    E_eps = 200_000 * 0.003
    B = A_s_prime * E_eps - A_s_prime * 0.85 * 25 - A_s * 420
    c = (-B + math.sqrt(B**2 + 4 * k * A_s_prime * E_eps * d_prime)) / (2 * k)
    assert -420 / 200_000 < (c - d_prime) / c * 0.003 < 0  # the top bars pull, elastic
    assert (d - c) / c * 0.003 > 420 / 200_000  # the bottom bars yield
    epsilon_t = 0.003 * (d - c) / c
    assert check.bottom.epsilon_t == pytest.approx(epsilon_t, rel=1e-6)
    assert check.bottom.epsilon_t < 0.0075
    # The singly reinforced c = a/beta_1 would have read well past it.
    c_singly = A_s * 420 / (0.85 * 25 * 1000 * 0.85)
    assert 0.003 * (d - c_singly) / c_singly > 0.0075


def test_flexure_design_carries_epsilon_t_of_the_governing_combination() -> None:
    beam = RectangularBeam(
        label="V3",
        concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=20 * cm,
        height=60 * cm,
        c_c=25 * mm,
    )
    forces = [Forces(label="C1", M_y=120 * kNm), Forces(label="C2", M_y=-80 * kNm)]
    Node(section=beam, forces=forces).design()

    design = beam.flexure_design
    for face in ("bottom", "top"):
        governing = max(beam.flexure_checks, key=lambda check: getattr(check, face).DCR)
        assert getattr(design, face).epsilon_t == getattr(governing, face).epsilon_t
        assert getattr(design, face).epsilon_t is not None
        assert getattr(design, face).x_u_d is None
    # Each face's strain is its own: the less reinforced face strains more.
    A_s_bot = design.bottom.A_s.to("mm**2").magnitude
    A_s_top = design.top.A_s.to("mm**2").magnitude
    assert (design.bottom.epsilon_t > design.top.epsilon_t) == (A_s_bot < A_s_top)


# ---------------------------------------------------------------------------
# x_u/d -- EN 1992-1-1
# ---------------------------------------------------------------------------


def _en_beam(delta: float = 0.85, f_ck: float = 25) -> RectangularBeam:
    beam = RectangularBeam(
        label="EN",
        concrete=Concrete_EN_1992_2004(name=f"C{f_ck:g}", f_c=f_ck * MPa, delta=delta),
        steel_bar=SteelBar(name="B500S", f_y=500 * MPa),
        width=20 * cm,
        height=60 * cm,
        c_c=26 * mm,
    )
    beam.set_transverse_rebar(n_stirrups=1, d_b=8 * mm, s_l=20 * cm)
    return beam


#: f_yd and f_cd of B500S on C25/30, alpha_cc = 0.85, eta = 1, lambda = 0.8.
F_YD = 500 / 1.15
F_CD = 0.85 * 25 / 1.5


def test_x_u_d_of_a_singly_reinforced_face_matches_the_hand_calculation() -> None:
    beam = _en_beam()
    beam.set_longitudinal_rebar_bot(n1=4, d_b1=16 * mm)
    beam.set_longitudinal_rebar_top(n1=0, d_b1=0 * mm)

    check = _checked(beam, 100)

    d = 600 - 26 - 8 - 16 / 2
    x_eff = 4 * _bar(16) * F_YD / (1.0 * F_CD * 200)
    x_u_d = x_eff / 0.8 / d
    assert x_u_d == pytest.approx(0.2765, abs=1e-4)
    assert check.bottom.x_u_d == pytest.approx(x_u_d, rel=1e-9)
    assert check.top.x_u_d is None
    assert check.bottom.epsilon_t is None and check.top.epsilon_t is None


def _elastic_opposite_root(k: float, A_s_prime: float, T: float, d_prime: float, E_eps: float) -> float:
    """Root of k*x² + (A_s'*E_s*eps_cu - T)*x - A_s'*E_s*eps_cu*d' = 0.

    Horizontal equilibrium with the tension steel yielded (force ``T``) and
    the opposite bars elastic, ``sigma' = E_s*eps_cu*(x - d')/x`` -- the same
    expression whether they push (x > d') or pull (x < d').
    """
    B = A_s_prime * E_eps - T
    return (-B + math.sqrt(B**2 + 4 * k * A_s_prime * E_eps * d_prime)) / (2 * k)


def test_x_u_d_with_compression_steel_that_yields_is_the_net_tension_over_the_block() -> None:
    # 4Ø25 bottom asks for a block past x_eff,lim; the 4Ø20 on top yield and
    # take their share, so x_u = (A_s - A_s')*f_yd / (eta*f_cd*b*lambda).
    beam = _en_beam()
    beam.set_longitudinal_rebar_bot(n1=4, d_b1=25 * mm)
    beam.set_longitudinal_rebar_top(n1=4, d_b1=20 * mm)

    check = _checked(beam, 300)

    d = 600 - 26 - 8 - 25 / 2
    d_prime = 26 + 8 + 20 / 2
    x_u = (4 * _bar(25) - 4 * _bar(20)) * F_YD / (F_CD * 200 * 0.8)
    assert (x_u - d_prime) / x_u * 0.0035 > F_YD / 200_000  # the top steel yields
    assert (d - x_u) / x_u * 0.0035 > F_YD / 200_000  # and so does the bottom
    assert x_u / d == pytest.approx(0.2450, abs=1e-4)  # below x_u,lim/d = 0.328
    assert check.bottom.x_u_d == pytest.approx(x_u / d, rel=1e-9)


def test_x_u_d_with_too_little_compression_steel_is_past_the_limit() -> None:
    # The bars round the tension steel past what 2Ø12 balance: M_Rd gains
    # nothing from the excess, but the neutral axis still goes down.
    beam = _en_beam()
    beam.set_longitudinal_rebar_bot(n1=4, d_b1=25 * mm)
    beam.set_longitudinal_rebar_top(n1=2, d_b1=12 * mm)

    check = _checked(beam, 300)

    d = 600 - 26 - 8 - 25 / 2
    d_prime = 26 + 8 + 12 / 2
    x_u = (4 * _bar(25) - 2 * _bar(12)) * F_YD / (F_CD * 200 * 0.8)
    assert (x_u - d_prime) / x_u * 0.0035 > F_YD / 200_000
    assert (d - x_u) / x_u * 0.0035 > F_YD / 200_000
    assert x_u / d > (0.85 - 0.44) / 1.25
    assert check.bottom.x_u_d == pytest.approx(x_u / d, rel=1e-9)


@pytest.mark.parametrize("delta", [0.70, 0.85, 1.0])
def test_x_u_d_is_the_sections_whatever_the_delta(delta: float) -> None:
    # 30x20 with 4Ø16 bottom and 4Ø25 top: the top bars sit just above the
    # neutral axis, elastic, past x_u,lim for delta = 0.7. The ratio is the
    # section's, not the design's, so delta does not move it.
    beam = _en_beam(delta=delta)
    beam.width, beam.height = 30 * cm, 20 * cm
    beam.set_longitudinal_rebar_bot(n1=4, d_b1=16 * mm)
    beam.set_longitudinal_rebar_top(n1=4, d_b1=25 * mm)

    check = _checked(beam, 30)

    d = 200 - 26 - 8 - 16 / 2
    d_prime = 26 + 8 + 25 / 2
    x_u = _elastic_opposite_root(F_CD * 300 * 0.8, 4 * _bar(25), 4 * _bar(16) * F_YD, d_prime, 200_000 * 0.0035)
    assert 0 < (x_u - d_prime) / x_u * 0.0035 < F_YD / 200_000  # compressed, elastic
    assert (d - x_u) / x_u * 0.0035 > F_YD / 200_000
    assert check.bottom.x_u_d == pytest.approx(x_u / d, rel=1e-9)


def test_x_u_d_of_a_shallow_section_counts_the_opposite_bars_that_pull() -> None:
    # A 14 cm slab strip, 7Ø12 bottom and 7Ø20 top: the top bars lie below the
    # neutral axis, in tension, and deepen it.
    beam = _en_beam()
    beam.width, beam.height = 100 * cm, 14 * cm
    beam.set_longitudinal_rebar_bot(n1=7, d_b1=12 * mm)
    beam.set_longitudinal_rebar_top(n1=7, d_b1=20 * mm)

    check = _checked(beam, 20)

    d = 140 - 26 - 8 - 12 / 2
    d_prime = 26 + 8 + 20 / 2
    x_u = _elastic_opposite_root(F_CD * 1000 * 0.8, 7 * _bar(20), 7 * _bar(12) * F_YD, d_prime, 200_000 * 0.0035)
    assert -F_YD / 200_000 < (x_u - d_prime) / x_u * 0.0035 < 0  # pulling, elastic
    assert (d - x_u) / x_u * 0.0035 > F_YD / 200_000
    assert check.bottom.x_u_d == pytest.approx(x_u / d, rel=1e-9)
    # Leaving the top bars out would read a shallower axis.
    assert check.bottom.x_u_d > 7 * _bar(12) * F_YD / (F_CD * 1000 * 0.8) / d


def test_flexure_design_carries_x_u_d_of_the_governing_combination() -> None:
    beam = _en_beam()
    forces = [Forces(label="C1", M_y=150 * kNm), Forces(label="C2", M_y=-90 * kNm)]
    Node(section=beam, forces=forces).design()

    design = beam.flexure_design
    for face in ("bottom", "top"):
        governing = max(beam.flexure_checks, key=lambda check: getattr(check, face).DCR)
        assert getattr(design, face).x_u_d == getattr(governing, face).x_u_d
        assert getattr(design, face).x_u_d is not None
        assert getattr(design, face).epsilon_t is None


def _designed_en(delta: float, width: float, height: float, M: float) -> RectangularBeam:
    """A C25/B500 section, cover 25 mm, designed for one moment ``M`` kN·m and ``delta``."""
    beam = RectangularBeam(
        label="D",
        concrete=Concrete_EN_1992_2004(name="C25", f_c=25 * MPa, delta=delta),
        steel_bar=SteelBar(name="B500", f_y=500 * MPa),
        width=width * cm,
        height=height * cm,
        c_c=25 * mm,
    )
    Node(section=beam, forces=[Forces(label="C1", M_y=M * kNm)]).design()
    return beam


def test_a_section_designed_for_delta_allows_that_delta() -> None:
    # The review's example: 25x50, +180 kN·m, delta = 0.85. The design used to
    # round the bottom up to 1257 mm² over 157 mm² on top, x_u/d = 0.368
    # against (0.85 - 0.44)/1.25 = 0.328: the redistribution it was designed
    # for was not one its bars allow.
    beam = _designed_en(0.85, 25, 50, 180)

    bottom = beam.flexure_design.bottom
    assert bottom.DCR <= 1.0
    assert bottom.x_u_d is not None
    assert 0.44 + 1.25 * bottom.x_u_d <= 0.85 * (1 + 1e-9)


def _past_delta(beam: RectangularBeam) -> dict:
    """The ``x_u_above_redistribution_limit`` warnings of a section, by face."""
    return {w.face: w for w in beam.warnings if w.code == "x_u_above_redistribution_limit"}


@pytest.mark.parametrize("delta", [0.70, 0.85])
@pytest.mark.parametrize(("width", "height"), [(25, 50), (40, 30)])
@pytest.mark.parametrize("M", [60, 180, 300, 420, -60, -180, -300, -420])
def test_a_designed_face_allows_its_delta_or_says_it_does_not(
    delta: float, width: float, height: float, M: float
) -> None:
    # The sections the review swept. A design that carries the moment ends
    # with x_u/d <= (delta - k_1)/k_2, so delta >= k_1 + k_2*x_u/d holds for
    # the delta it was designed for. One that cannot -- too small for the
    # moment, or for that delta -- says so on the face, with the delta the
    # section does allow. Never past it in silence.
    beam = _designed_en(delta, width, height, M)

    name = "bottom" if M > 0 else "top"
    face = getattr(beam.flexure_design, name)
    limit = (delta - 0.44) / 1.25
    assert face.x_u_d is not None
    warned = _past_delta(beam)
    if face.x_u_d <= limit * (1 + 1e-9):
        assert name not in warned
    else:
        assert warned[name].values["x_u_d"] == pytest.approx(face.x_u_d)
        assert warned[name].values["x_u_d_max"] == pytest.approx(limit)
        assert warned[name].values["delta_min"] == pytest.approx(0.44 + 1.25 * face.x_u_d)
    if face.DCR <= 1.0 and abs(M) <= 300:
        # Every one of these closes within its delta: 25x50 and 40x30 have
        # room for the compression steel it takes.
        assert name not in warned


def test_a_section_that_cannot_allow_its_delta_carries_the_moment_and_says_so() -> None:
    # C20, 30x20, +6.2 kN·m, delta = 0.70. The two stirrups want a bar at
    # each leg, and 4Ø10 already put x_u/d at 0.306 against 0.208; bars on
    # top, below x_u,lim, pull instead of pushing. The design keeps the bars
    # the moment asks for, adds no top steel for nothing, and says which delta
    # the section allows.
    beam = RectangularBeam(
        label="S",
        concrete=Concrete_EN_1992_2004(name="C20", f_c=20 * MPa, delta=0.70),
        steel_bar=SteelBar(name="B500", f_y=500 * MPa),
        width=30 * cm,
        height=20 * cm,
        c_c=25 * mm,
    )
    Node(section=beam, forces=[Forces(label="C1", M_y=6.2 * kNm)]).design()

    bottom = beam.flexure_design.bottom
    assert bottom.DCR <= 1.0
    assert beam.flexure_design.top.A_s.magnitude == 0
    warning = _past_delta(beam)["bottom"]
    assert warning.values["x_u_d"] == pytest.approx(bottom.x_u_d)
    assert warning.values["delta"] == 0.70
    assert warning.values["delta_min"] > 0.70
    assert "delta" in warning.message
    # Bars set by hand are the user's section: the design's verdict goes.
    beam.set_longitudinal_rebar_bot(n1=2, d_b1=10 * mm)
    assert not _past_delta(beam)


def test_delta_one_redistributes_nothing_and_never_warns() -> None:
    # C60, 30x20, +74.4 kN·m. Above C50 the limit at delta = 1, (1 - k_3)/k_4 =
    # 0.339, sits below what the section reaches, 0.389; with nothing
    # redistributed there is no limit to hold the bars to, and no delta to
    # name -- the warning used to ask for delta >= 1.07.
    beam = RectangularBeam(
        label="S",
        concrete=Concrete_EN_1992_2004(name="C60", f_c=60 * MPa, delta=1.0),
        steel_bar=SteelBar(name="B500", f_y=500 * MPa),
        width=30 * cm,
        height=20 * cm,
        c_c=25 * mm,
    )
    Node(section=beam, forces=[Forces(label="C1", M_y=74.4 * kNm)]).design()

    assert beam.flexure_design.bottom.x_u_d is not None
    assert not _past_delta(beam)


def test_delta_min_above_c50_reads_eq_5_10b() -> None:
    # C70, 15x30, +47.4 kN·m, delta = 0.80: the bars that carry it are past
    # (0.80 - k_3)/k_4, and the warning names k_3 + k_4*x_u/d.
    # eps_cu2 = 2.6 + 35*((90 - 70)/100)**4 per mil, k_3 = 0.54.
    beam = RectangularBeam(
        label="S",
        concrete=Concrete_EN_1992_2004(name="C70", f_c=70 * MPa, delta=0.80),
        steel_bar=SteelBar(name="B500", f_y=500 * MPa),
        width=15 * cm,
        height=30 * cm,
        c_c=25 * mm,
    )
    Node(section=beam, forces=[Forces(label="C1", M_y=47.4 * kNm)]).design()

    k_4 = 1.25 * (0.6 + 0.0014 / ((2.6 + 35 * 0.2**4) * 1e-3))
    assert k_4 == pytest.approx(1.409, abs=1e-3)
    warning = _past_delta(beam)["bottom"]
    x_u_d = beam.flexure_design.bottom.x_u_d
    assert warning.values["x_u_d_max"] == pytest.approx((0.80 - 0.54) / k_4)
    assert warning.values["delta_min"] == pytest.approx(0.54 + k_4 * x_u_d)


def test_a_footing_that_cannot_allow_its_delta_keeps_its_steel() -> None:
    # A footing mat is chosen whole, lightest first. Holding it to delta = 0.70
    # as hard as to A_s,max left both faces bare under +112.4 / -70.3 kN·m.
    footing = Footing(
        label="F",
        concrete=Concrete_EN_1992_2004(name="C25", f_c=25 * MPa, delta=0.70),
        steel_bar=SteelBar(name="B500", f_y=500 * MPa),
        width=100 * cm,
        height=30 * cm,
        c_c=50 * mm,
    )
    forces = [Forces(label="C1", M_y=112.4 * kNm), Forces(label="C2", M_y=-70.3 * kNm)]
    Node(section=footing, forces=forces).design()

    design = footing.flexure_design
    assert design.bottom.A_s.magnitude > 0 and design.top.A_s.magnitude > 0
    assert design.DCR <= 1.0
    for name in _past_delta(footing):
        assert getattr(design, name).x_u_d > (0.70 - 0.44) / 1.25


# ---------------------------------------------------------------------------
# delta -- EN 1992-1-1 §5.5(4)
# ---------------------------------------------------------------------------


def test_delta_defaults_to_085() -> None:
    assert Concrete_EN_1992_2004(name="C25", f_c=25 * MPa).delta == 0.85


@pytest.mark.parametrize("delta", [0.69, 1.01])
def test_delta_outside_k5_and_one_is_rejected(delta: float) -> None:
    with pytest.raises(ValueError, match="delta"):
        Concrete_EN_1992_2004(name="C25", f_c=25 * MPa, delta=delta)


@pytest.mark.parametrize(
    ("delta", "xi_lim"),
    [
        (0.70, (0.70 - 0.44) / 1.25),  # k_5, the most redistribution: 0.208
        (0.85, (0.85 - 0.44) / 1.25),  # 0.328
        (1.00, (1.00 - 0.44) / 1.25),  # none: 0.448, just under the 0.45 cap
    ],
)
def test_delta_moves_the_limit_as_eq_5_10a_says(delta: float, xi_lim: float) -> None:
    beam = _en_beam(delta=delta)
    x_u_lim, x_eff_lim = _compression_zone_limits_EN_1992_2004(beam, 560.0)
    assert x_u_lim / 560.0 == pytest.approx(xi_lim, rel=1e-12)
    assert x_eff_lim == pytest.approx(0.8 * x_u_lim, rel=1e-12)


def test_delta_moves_the_limit_as_eq_5_10b_says_above_c50() -> None:
    # C60/75: eps_cu2 = 2.6 + 35*((90 - 60)/100)**4 per mil, k_3 = 0.54.
    epsilon_cu2 = (2.6 + 35 * 0.3**4) * 1e-3
    k_4 = 1.25 * (0.6 + 0.0014 / epsilon_cu2)
    for delta in (0.75, 0.9):
        beam = _en_beam(delta=delta, f_ck=60)
        x_u_lim, _ = _compression_zone_limits_EN_1992_2004(beam, 560.0)
        assert x_u_lim / 560.0 == pytest.approx((delta - 0.54) / k_4, rel=1e-12)


def test_a_smaller_delta_lowers_the_resistance_of_a_doubly_reinforced_face() -> None:
    capacities = []
    ratios = []
    for delta in (1.0, 0.85, 0.7):
        beam = _en_beam(delta=delta)
        beam.set_longitudinal_rebar_bot(n1=4, d_b1=25 * mm)
        beam.set_longitudinal_rebar_top(n1=2, d_b1=12 * mm)
        check = _checked(beam, 300)
        assert check.bottom.M_capacity is not None
        capacities.append(check.bottom.M_capacity.to("kN*m").magnitude)
        ratios.append(check.bottom.x_u_d)
    assert capacities[0] > capacities[1] > capacities[2]
    # With too little compression steel the neutral axis is the section's, not delta's.
    assert ratios[0] == pytest.approx(ratios[1]) == pytest.approx(ratios[2])


# ---------------------------------------------------------------------------
# Envelope
# ---------------------------------------------------------------------------


def _face(DCR: float, epsilon_t: float | None = None, x_u_d: float | None = None) -> FlexureFaceCheck:
    return FlexureFaceCheck(A_s_req=None, A_s_min=None, A_s_max=None, DCR=DCR, epsilon_t=epsilon_t, x_u_d=x_u_d)


def _combination(bottom: FlexureFaceCheck) -> FlexureCheck:
    return FlexureCheck(label="C", bottom=bottom, top=_face(0.0))


def test_envelope_takes_the_ratios_of_the_governing_combination() -> None:
    checks = [
        _combination(_face(0.4, epsilon_t=0.004, x_u_d=0.5)),
        _combination(_face(0.9, epsilon_t=0.012, x_u_d=0.2)),
    ]
    bottom = envelope_flexure_face(checks, "bottom")
    assert bottom.epsilon_t == 0.012
    assert bottom.x_u_d == 0.2
    assert envelope_flexure_face(checks, "top").epsilon_t is None


def test_envelope_reads_ties_on_the_safe_side() -> None:
    checks = [
        _combination(_face(0.0, epsilon_t=0.012, x_u_d=0.2)),
        _combination(_face(0.0, epsilon_t=0.010, x_u_d=0.3)),
    ]
    bottom = envelope_flexure_face(checks, "bottom")
    assert bottom.epsilon_t == 0.010
    assert bottom.x_u_d == 0.3
