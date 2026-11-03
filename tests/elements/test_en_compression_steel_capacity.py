"""EN 1992-1-1: the resistance credits compression steel at the stress its strain gives it.

Past the ductility limit the neutral axis is held at x_u,lim, the concrete
gives M_lim, and the tension steel past A_s,lim pairs with the steel on the
compression face. That steel used to be credited at f_yd whatever its depth.
A bar at or below x_u,lim is not compressed there, though, and one just above
it is barely compressed. The sizing already read them at the strain-compatible
f_sd (§6.1(2), §3.2.7(2)), so the check passed layouts the sizing could not
produce, sometimes above what strain compatibility gives the section at all.

These tests pin the resistance against that model, against the sizing, and
against an independent strain-compatibility solution that has no ductility
limit and so is an upper bound for it.
"""

import warnings

import pytest

from mento.codes.EN_1992_2004_beam import (
    _calculate_flexural_reinforcement_EN_1992_2004,
    _compression_zone_limits_EN_1992_2004,
    _simple_determine_nominal_moment_EN_1992_2004,
)
from mento.codes.en_1992_2004.equations import flexure as en_flexure
from mento.beam import RectangularBeam
from mento.forces import Forces
from mento.material import Concrete_EN_1992_2004, SteelBar
from mento.node import Node
from mento.precompute import section_floats
from mento.settings import BeamSettings
from mento.slab import Footing
from mento.units import cm, kN, kNm, mm, MPa


def _footing() -> Footing:
    """100x15 cm, C25, B500S, c_c 50 mm: Ø25/10 cm bottom, Ø20/10 cm top."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # thinner than the 250 mm of a footing on soil
        footing = Footing(
            concrete=Concrete_EN_1992_2004(name="C25", f_c=25 * MPa),
            steel_bar=SteelBar(name="B500S", f_y=500 * MPa),
            c_c=50 * mm,
            width=100 * cm,
            height=15 * cm,
            settings=BeamSettings(unit_system="metric"),
        )
    footing.set_slab_longitudinal_rebar_bot(d_b1=25 * mm, s_b1=10 * cm)
    footing.set_slab_longitudinal_rebar_top(d_b1=20 * mm, s_b1=10 * cm)
    return footing


def _beam() -> RectangularBeam:
    """15x30 cm, C30, B420, c_c 25 mm: 2Ø25 + 2Ø20 bottom, 2Ø25 top."""
    beam = RectangularBeam(
        label="V",
        concrete=Concrete_EN_1992_2004(name="C30", f_c=30 * MPa),
        steel_bar=SteelBar(name="B420", f_y=420 * MPa),
        width=15 * cm,
        height=30 * cm,
        c_c=25 * mm,
    )
    beam.set_longitudinal_rebar_bot(2, 25 * mm, 2, 20 * mm)
    beam.set_longitudinal_rebar_top(2, 25 * mm)
    return beam


def _materials(section) -> dict:  # type: ignore[no-untyped-def]
    sec = section_floats(section)
    concrete = section.concrete
    return {
        "b": sec.width,
        "f_cd": concrete.alpha_cc * sec.f_c / concrete.gamma_c,
        "f_yd": sec.f_y / section.steel_bar.gamma_s,
        "eta": concrete._eta_factor(),
        "lam": concrete._lambda_factor(),
        "eps_cu": concrete.epsilon_cu2,
        "E_s": sec.E_s,
    }


def _M_Rd_bot(section) -> float:  # type: ignore[no-untyped-def]
    """M_Rd with the bottom in tension, in kN·m."""
    sec = section_floats(section)
    return (
        _simple_determine_nominal_moment_EN_1992_2004(section, sec.A_s_bot, sec.d_bot, sec.A_s_top, sec.c_mec_top) / 1e6
    )


def _strain_compatibility(p: dict, A_s: float, d: float, A_s_prime: float, d_prime: float) -> float:
    """M_Rd with no ductility limit, in N·mm: the neutral axis that balances every bar.

    Written apart from mento: the rectangular block of §3.1.7(3), plane
    sections (§6.1(2)) and the bilinear steel of §3.2.7(2), both faces at
    the stress their strain gives them, tension or compression.
    """

    def stress(eps: float) -> float:
        return max(-p["f_yd"], min(p["f_yd"], eps * p["E_s"]))

    def forces(x: float) -> tuple[float, float, float]:
        C_c = p["eta"] * p["f_cd"] * p["b"] * p["lam"] * x
        C_s = A_s_prime * stress(p["eps_cu"] * (x - d_prime) / x)
        T = A_s * stress(p["eps_cu"] * (d - x) / x)
        return C_c, C_s, T

    lo, hi = 1e-6, 10 * d
    for _ in range(200):
        x = 0.5 * (lo + hi)
        C_c, C_s, T = forces(x)
        lo, hi = (lo, x) if C_c + C_s > T else (x, hi)
    C_c, C_s, _ = forces(x)
    return C_c * (d - p["lam"] * x / 2) + C_s * (d - d_prime)


def test_compression_bars_below_the_neutral_axis_add_nothing() -> None:
    """d' = 60 mm, x_u,lim = 0.328*87.5 = 28.7 mm: the top bars are in tension at the limit.

    M_Rd used to be M_lim plus the top bars at f_yd, 62.29 kN·m with ten bars
    a face, and passed 60 kN·m at DCR 0.963. Strain compatibility, with no
    ductility limit at all, gives this layout its 9 whole bars a face at
    51.6 kN·m: the old value was above anything the section can carry. Now the
    section saturates at M_lim, exactly as it does with no top bars.
    """
    footing = _footing()
    sec = section_floats(footing)
    x_u_lim, x_eff_lim = _compression_zone_limits_EN_1992_2004(footing, sec.d_bot)
    assert sec.c_mec_top > x_u_lim

    p = _materials(footing)
    M_lim = en_flexure.limit_moment(p["eta"], p["f_cd"], p["b"], x_eff_lim, sec.d_bot) / 1e6
    assert _M_Rd_bot(footing) == pytest.approx(M_lim, rel=1e-12)
    assert _M_Rd_bot(footing) == pytest.approx(24.73, abs=0.01)
    no_top = _simple_determine_nominal_moment_EN_1992_2004(footing, sec.A_s_bot, sec.d_bot, 0.0, sec.c_mec_top) / 1e6
    assert _M_Rd_bot(footing) == pytest.approx(no_top, rel=1e-12)

    upper = _strain_compatibility(p, sec.A_s_bot, sec.d_bot, sec.A_s_top, sec.c_mec_top) / 1e6
    assert upper == pytest.approx(51.6, abs=0.1)

    node = Node(section=footing, forces=[Forces(label="M", M_y=60 * kNm, V_z=0 * kN)])
    node.check_flexure()
    assert footing.flexure_checks[0].bottom.DCR == pytest.approx(60 / M_lim, rel=1e-9)
    assert not footing.flexure_checks[0].bottom.complies
    # The resistance credits no compression steel, so no face is recorded as one.
    assert footing._compression_faces == set()


def test_compression_steel_short_of_yield_is_credited_at_its_strain() -> None:
    """d'/x_u,lim = 45.5/83.8 = 0.54 > 1 - eps_yd/eps_cu2 = 0.48: the top bars do not yield.

    f_sd' = 0.0035*(1 - 0.543)*200000 = 320 MPa against f_yd = 365 MPa. The
    2Ø25 on top balance 314 kN of the 417 kN that the bottom steel past
    A_s,lim pulls, so M_Rd drops from 113.23 to 103.89 kN·m. Strain
    compatibility gives the layout 123.6 kN·m.
    """
    beam = _beam()
    sec = section_floats(beam)
    p = _materials(beam)
    x_u_lim, x_eff_lim = _compression_zone_limits_EN_1992_2004(beam, sec.d_bot)
    f_sd = en_flexure.compression_steel_stress(x_u_lim, sec.c_mec_top, p["eps_cu"], p["E_s"], p["f_yd"])
    assert 0 < f_sd < p["f_yd"]
    assert f_sd == pytest.approx(319.9, abs=0.1)

    A_s_lim = p["eta"] * p["f_cd"] * p["b"] * x_eff_lim / p["f_yd"]
    M_lim = A_s_lim * p["f_yd"] * (sec.d_bot - x_eff_lim / 2)
    couple = min((sec.A_s_bot - A_s_lim) * p["f_yd"], sec.A_s_top * f_sd)
    assert couple == pytest.approx(sec.A_s_top * f_sd, rel=1e-12)  # the top bars bind
    expected = (M_lim + couple * (sec.d_bot - sec.c_mec_top)) / 1e6
    assert _M_Rd_bot(beam) == pytest.approx(expected, rel=1e-12)
    assert _M_Rd_bot(beam) == pytest.approx(103.89, abs=0.01)
    assert _M_Rd_bot(beam) <= _strain_compatibility(p, sec.A_s_bot, sec.d_bot, sec.A_s_top, sec.c_mec_top) / 1e6

    node = Node(section=beam, forces=[Forces(label="M", M_y=80 * kNm, V_z=0 * kN)])
    node.check_flexure()
    assert beam._compression_faces == {"top"}


@pytest.mark.parametrize("M_kNm", [80.0, 95.0, 110.0])
def test_the_areas_the_sizing_asks_for_carry_exactly_the_moment(M_kNm: float) -> None:
    """Sizing and resistance read the compression steel at the same f_sd', so they invert each other.

    On the 15x30 beam, d' = 45.5 mm and f_sd' = 320 MPa < f_yd: with the
    tension and compression areas the sizing returns, M_Rd is M. It used to
    be more, since the check took the same bars at f_yd.
    """
    beam = _beam()
    sec = section_floats(beam)
    M = M_kNm * 1e6
    _, _, A_s1, A_s2, A_s_calc = _calculate_flexural_reinforcement_EN_1992_2004(beam, M, sec.d_bot, sec.c_mec_top)
    assert A_s2 > 0 and A_s1 == A_s_calc  # doubly reinforced, above the minimum
    M_Rd = _simple_determine_nominal_moment_EN_1992_2004(beam, A_s1, sec.d_bot, A_s2, sec.c_mec_top)
    assert M_Rd == pytest.approx(M, rel=1e-9)


def test_M_Rd_falls_continuously_to_M_lim_as_the_compression_steel_reaches_the_neutral_axis() -> None:
    """Deeper compression bars have a shorter arm and less strain: M_Rd never rises with d'.

    It reaches M_lim at d' = x_u,lim, where f_sd' = 0, and stays there below
    it. The old resistance kept the bars at f_yd down to the neutral axis
    and then dropped them nowhere: it stayed above M_lim for any d' < d.
    """
    footing = _footing()
    sec = section_floats(footing)
    p = _materials(footing)
    x_u_lim, x_eff_lim = _compression_zone_limits_EN_1992_2004(footing, sec.d_bot)
    M_lim = en_flexure.limit_moment(p["eta"], p["f_cd"], p["b"], x_eff_lim, sec.d_bot)
    depths = [5.0 + 0.5 * i for i in range(int((sec.d_bot - 5.0) / 0.5))]
    values = [
        _simple_determine_nominal_moment_EN_1992_2004(footing, sec.A_s_bot, sec.d_bot, sec.A_s_top, d_prime)
        for d_prime in depths
    ]
    assert all(later <= earlier * (1 + 1e-12) for earlier, later in zip(values, values[1:]))
    for d_prime, value in zip(depths, values):
        if d_prime >= x_u_lim:
            assert value == pytest.approx(M_lim, rel=1e-12)
    just_above = _simple_determine_nominal_moment_EN_1992_2004(
        footing, sec.A_s_bot, sec.d_bot, sec.A_s_top, x_u_lim * (1 - 1e-9)
    )
    assert just_above == pytest.approx(M_lim, rel=1e-6)


def test_M_Rd_never_exceeds_strain_compatibility() -> None:
    """Over d' on both sides of x_u,lim and A_s' from none to twice A_s.

    Strain compatibility with no ductility limit is the most the section
    carries, so a resistance that holds the neutral axis at x_u,lim must not
    exceed it. It may by a fraction of a percent: the rectangular block
    leaves out the concrete the compression bars displace. Where those bars
    sit inside the block and below its centroid, the block's own lever arm
    overstates theirs, and the singly reinforced branch, which ignores them,
    shows the same excess. The old resistance exceeded it by up to ~80 %
    on this grid, wherever the compression bars sat at or below the neutral
    axis.
    """
    footing = _footing()
    p = _materials(footing)
    worst = 0.0
    for d in (90.0, 150.0, 250.0):
        x_u_lim, _ = _compression_zone_limits_EN_1992_2004(footing, d)
        for d_prime_ratio in (0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.7, 0.9):
            d_prime = d_prime_ratio * d
            for rho in (0.005, 0.01, 0.02, 0.03, 0.04):
                A_s = rho * p["b"] * d
                for ratio in (0.0, 0.25, 0.5, 1.0, 2.0):
                    M_Rd = _simple_determine_nominal_moment_EN_1992_2004(footing, A_s, d, ratio * A_s, d_prime)
                    upper = _strain_compatibility(p, A_s, d, ratio * A_s, d_prime)
                    worst = max(worst, M_Rd / upper)
        assert any(r * d > x_u_lim for r in (0.5, 0.7, 0.9))  # some of the bars sit below x_u,lim
    assert worst <= 1.01


def test_a_design_short_of_compression_steel_says_so() -> None:
    """15x30, C30, B420 at 93.7 kN·m: the web fits no more than 2Ø25 on top.

    The sizing asks for 11.16 cm² there at f_sd' = 288 MPa, and 2Ø25 is 9.82.
    The design keeps the layout that comes closest, DCR 1.086. It used to
    pass at 0.931, with the top bars at f_yd. Now it says it is short. The
    shortfall is on the compression face, whose own DCR is 0, and the
    warning used to be held back for that reason.
    """
    beam = RectangularBeam(
        label="V",
        concrete=Concrete_EN_1992_2004(name="C30", f_c=30 * MPa),
        steel_bar=SteelBar(name="B420", f_y=420 * MPa),
        width=15 * cm,
        height=30 * cm,
        c_c=25 * mm,
    )
    node = Node(section=beam, forces=[Forces(label="M", M_y=93.7 * kNm)])
    node.design_flexure()
    node.check_flexure()

    bottom = beam.flexure_checks[0].bottom
    assert bottom.DCR > 1
    codes = {warning.code for warning in node.warnings}
    assert {"As_below_required", "section_too_small_for_moment"} <= codes
    (short,) = [warning for warning in node.warnings if warning.code == "As_below_required"]
    assert short.face == "top"
    assert short.values["A_s"] < short.values["A_s_req"]
