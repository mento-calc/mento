"""EN 1992-1-1: the areas of the doubly reinforced branch, once M passes M_lim.

Past M_lim the moment the concrete cannot take is a steel couple on the lever
arm d - d'. Its tension steel works at f_yd, its compression steel at the f_sd
plane sections give it at the ductility limit. The tension area used to be
sized at f_sd as well, so once d' >= x_u,lim made f_sd negative it fell as the
moment grew, went negative, and A_s_req hid it behind A_s_min (#203).

These tests pin what the areas say now: never negative, A_s_calc rising with
M and never below A_s1_lim, A_s_req never below A_s_calc, and an infinite
compression area where no compression steel can close the couple.
"""

import math
import warnings

import pytest

from mento.codes.EN_1992_2004_beam import (
    _calculate_flexural_reinforcement_EN_1992_2004,
    _compression_zone_limits_EN_1992_2004,
    _simple_determine_nominal_moment_EN_1992_2004,
)
from mento.codes.en_1992_2004.equations import flexure as en_flexure
from mento.forces import Forces
from mento.material import Concrete_EN_1992_2004, SteelBar
from mento.precompute import section_floats
from mento.settings import BeamSettings
from mento.slab import Footing, OneWaySlab
from mento.units import cm, kN, kNm, mm, MPa


def _footing(c_c, height=25 * cm):  # type: ignore[no-untyped-def]
    """The footing of the issue: 100 cm wide, C25, B500S, Ø20 only.

    Allowed two layers, which is what holds it to Ø20: kept to one, a design
    goes up the catalogue instead.
    """
    settings = BeamSettings(unit_system="metric")
    settings.minimum_longitudinal_diameter = 20 * mm
    settings.max_longitudinal_diameter = 20 * mm
    return Footing(
        concrete=Concrete_EN_1992_2004(name="C25", f_c=25 * MPa),
        steel_bar=SteelBar(name="B500S", f_y=500 * MPa),
        c_c=c_c,
        width=100 * cm,
        height=height,
        settings=settings,
        max_layers=2,
    )


def _check(section, M):  # type: ignore[no-untyped-def]
    forces = [Forces(label="M", M_y=M, V_z=0 * kN)]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return section.flexure_check_results(forces)[0]


def _design_and_check(section, M):  # type: ignore[no-untyped-def]
    forces = [Forces(label="M", M_y=M, V_z=0 * kN)]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        section.design(forces)
    return _check(section, M)


def _cm2(area) -> float:  # type: ignore[no-untyped-def]
    return float(area.to("cm**2").magnitude)


def _limits(section) -> tuple[float, float, float]:  # type: ignore[no-untyped-def]
    """(d, d', x_u,lim) of the bottom face in tension, in mm."""
    sec = section_floats(section)
    x_u_lim, _ = _compression_zone_limits_EN_1992_2004(section, sec.d_bot)
    return sec.d_bot, sec.c_mec_top, x_u_lim


def _M_lim(section) -> float:  # type: ignore[no-untyped-def]
    """M_lim of the bottom face in tension, in kN·m."""
    sec = section_floats(section)
    concrete = section.concrete
    f_cd = concrete.alpha_cc * sec.f_c / concrete.gamma_c
    _, x_eff_lim = _compression_zone_limits_EN_1992_2004(section, sec.d_bot)
    return en_flexure.limit_moment(concrete._eta_factor(), f_cd, sec.width, x_eff_lim, sec.d_bot) / 1e6


def _A_s1_lim(section) -> float:  # type: ignore[no-untyped-def]
    """The tension steel that carries M_lim, bottom face in tension, in mm²."""
    sec = section_floats(section)
    _, x_eff_lim = _compression_zone_limits_EN_1992_2004(section, sec.d_bot)
    f_yd = sec.f_y / section.steel_bar.gamma_s
    return en_flexure.reinforcement_for_moment(_M_lim(section) * 1e6, en_flexure.lever_arm(sec.d_bot, x_eff_lim), f_yd)


# ---------------------------------------------------------------------------
# The rows of the issue
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("c_c", "M", "A_s_calc"),
    [
        # c_c 70 mm: d' sits past x_u,lim, so no compression steel helps and the
        # section fails; the tension area still says what the couple would need.
        # Before: 10.81, 5.21, -3.18 and -101.07 cm².
        (70, 100, 16.07),
        (70, 110, 18.37),
        (70, 125, 21.82),
        (70, 300, 62.07),
    ],
)
def test_the_rows_of_the_issue(c_c: int, M: int, A_s_calc: float) -> None:
    footing = _footing(c_c * mm)
    check = _design_and_check(footing, M * kNm)
    d, d_prime, x_u_lim = _limits(footing)
    assert d_prime >= x_u_lim, "the case is meant to put the compression steel past the limit neutral axis"
    assert _cm2(check.bottom.A_s_calc) == pytest.approx(A_s_calc, abs=0.01)
    assert _cm2(check.bottom.A_s_req) == pytest.approx(max(A_s_calc, _cm2(check.bottom.A_s_min)), abs=0.01)
    # No compression steel at that depth is compressed at the ductility limit.
    assert math.isinf(_cm2(check.top.A_s_req)) and _cm2(check.top.A_s_req) > 0


def test_the_two_layer_section_of_the_issue() -> None:
    """c_c 30 mm, 9 + 9 Ø20 on each face: d' = 62.5 mm, a millimetre past x_u,lim = 61.5 mm.

    The areas were -1294.51 cm², with A_s_req = A_s_min, and the issue's design
    passed this layout at DCR 0.965 (0.891 once the tension area was sized at
    f_yd). The top bars are not compressed at the ductility limit, so the
    resistance credits them nothing and the section saturates at M_lim.
    """
    footing = _footing(30 * mm)
    footing.set_longitudinal_rebar_top(n1=9, d_b1=20 * mm, n3=9, d_b3=20 * mm)
    footing.set_longitudinal_rebar_bot(n1=9, d_b1=20 * mm, n3=9, d_b3=20 * mm)
    check = _check(footing, 300 * kNm)
    d, d_prime, x_u_lim = _limits(footing)
    assert d_prime == pytest.approx(62.5) and x_u_lim == pytest.approx(61.5)
    assert _cm2(check.bottom.A_s_calc) == pytest.approx(50.34, abs=0.01)
    assert _cm2(check.bottom.A_s_req) == pytest.approx(50.34, abs=0.01)
    assert math.isinf(_cm2(check.top.A_s_req)) and _cm2(check.top.A_s_req) > 0
    assert check.bottom.M_capacity.to("kN*m").magnitude == pytest.approx(_M_lim(footing), rel=1e-9)
    assert check.bottom.DCR == pytest.approx(300 / _M_lim(footing), rel=1e-9)


def test_the_design_of_the_issue_says_the_section_is_short() -> None:
    """c_c 30 mm at 300 kN·m: one layer a face, d' = 40 mm < x_u,lim, and still short.

    The two-layer layout the design used to pass on has no compression steel
    the resistance credits; the best it finds, the 9 Ø20 that fit in the span,
    carries 300/1.37 kN·m, and it says so.
    """
    footing = _footing(30 * mm)
    check = _design_and_check(footing, 300 * kNm)
    _, d_prime, x_u_lim = _limits(footing)
    assert d_prime < x_u_lim
    assert check.bottom.DCR == pytest.approx(1.372, abs=1e-3)
    assert {"As_below_required", "section_too_small_for_moment"} <= {w.code for w in footing.warnings}


def test_A_s_calc_is_the_tension_steel_at_which_M_Rd_reaches_M() -> None:
    """With compression steel enough for the couple, the check carries M exactly at A_s_calc.

    c_c 20 mm, 4Ø20 on top at d' = 30 mm, above x_u,lim = 72.2 mm, so f_sd > 0
    and 12.57 cm² covers the 6.91 cm² the couple asks for at 210 kN·m. The
    8Ø20 bottom (25.13 cm²) is 0.18 cm² short of A_s_calc and fails at DCR
    1.007; the 9Ø20 has more and passes. Sizing and resistance read the
    couple the same way, on both sides.
    """
    footing = _footing(20 * mm)
    footing.set_longitudinal_rebar_top(n1=4, d_b1=20 * mm)
    for n in (8, 9):
        footing.set_longitudinal_rebar_bot(n1=n, d_b1=20 * mm)
        check = _check(footing, 210 * kNm)
        d, d_prime, x_u_lim = _limits(footing)
        assert d_prime < x_u_lim
        A_s_calc = float(check.bottom.A_s_calc.to("mm**2").magnitude)
        assert (check.bottom.DCR <= 1.0) == (section_floats(footing).A_s_bot >= A_s_calc) == (n == 9)
        A_s_top = section_floats(footing).A_s_top
        M_Rd = _simple_determine_nominal_moment_EN_1992_2004(footing, A_s_calc, d, A_s_top, d_prime)
        assert M_Rd / 1e6 == pytest.approx(210, rel=1e-9)


# ---------------------------------------------------------------------------
# Properties over a sweep that crosses M_lim
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("c_c", [20, 30, 50, 70])
def test_areas_over_a_sweep_across_M_lim(c_c: int) -> None:
    """Never negative, A_s_calc non-decreasing, A_s_req >= A_s_calc >= A_s1_lim past M_lim."""
    footing = _footing(c_c * mm)
    footing.set_longitudinal_rebar_bot(n1=5, d_b1=20 * mm)
    footing.set_longitudinal_rebar_top(n1=5, d_b1=20 * mm)
    M_lim = _M_lim(footing)
    A_s1_lim = _A_s1_lim(footing) / 100  # cm²
    previous = 0.0
    for step in range(1, 41):
        M = M_lim * step / 10  # 0.1 M_lim to 4 M_lim
        check = _check(footing, M * kNm)
        calc, req, req_top = (_cm2(a) for a in (check.bottom.A_s_calc, check.bottom.A_s_req, check.top.A_s_req))
        assert calc >= 0 and req >= 0 and req_top >= 0
        assert req >= calc
        assert calc >= previous
        if step > 10:
            assert calc >= A_s1_lim
        previous = calc


def test_the_sweep_puts_d_prime_on_both_sides_of_x_u_lim() -> None:
    """The covers of the sweep above are chosen so that it covers both branches."""
    sides = set()
    for c_c in (20, 30, 50, 70):
        footing = _footing(c_c * mm)
        footing.set_longitudinal_rebar_bot(n1=5, d_b1=20 * mm)
        footing.set_longitudinal_rebar_top(n1=5, d_b1=20 * mm)
        _, d_prime, x_u_lim = _limits(footing)
        sides.add(d_prime < x_u_lim)
    assert sides == {True, False}


def test_compression_steel_inside_the_limit_is_sized_at_its_own_stress() -> None:
    """d' < x_u,lim: the compression area is the couple at f_sd, the tension one at f_yd."""
    footing = _footing(20 * mm)
    footing.set_longitudinal_rebar_bot(n1=5, d_b1=20 * mm)
    footing.set_longitudinal_rebar_top(n1=5, d_b1=20 * mm)
    d, d_prime, x_u_lim = _limits(footing)
    assert d_prime < x_u_lim
    sec = section_floats(footing)
    f_yd = sec.f_y / footing.steel_bar.gamma_s
    f_sd = en_flexure.compression_steel_stress(x_u_lim, d_prime, footing.concrete.epsilon_cu2, sec.E_s, f_yd)
    M = 2 * _M_lim(footing) * 1e6
    _, _, _, A_s2, A_s_calc = _calculate_flexural_reinforcement_EN_1992_2004(footing, M, d, d_prime)
    excess = M - _M_lim(footing) * 1e6
    assert A_s2 == pytest.approx(excess / ((d - d_prime) * f_sd))
    assert A_s_calc == pytest.approx(_A_s1_lim(footing) + excess / ((d - d_prime) * f_yd))


# ---------------------------------------------------------------------------
# Degenerate depths
# ---------------------------------------------------------------------------


def test_compression_steel_past_the_limit_has_no_finite_area() -> None:
    footing = _footing(70 * mm)
    footing.set_longitudinal_rebar_bot(n1=5, d_b1=20 * mm)
    footing.set_longitudinal_rebar_top(n1=5, d_b1=20 * mm)
    d, d_prime, x_u_lim = _limits(footing)
    assert d_prime > x_u_lim
    _, _, A_s1, A_s2, A_s_calc = _calculate_flexural_reinforcement_EN_1992_2004(
        footing, 2 * _M_lim(footing) * 1e6, d, d_prime
    )
    assert math.isinf(A_s2) and A_s2 > 0
    assert math.isfinite(A_s_calc) and A_s1 >= A_s_calc > 0


def test_a_couple_with_no_lever_arm_has_no_finite_area() -> None:
    """d' >= d: the design probes such layouts in thin sections; it used to divide by zero."""
    footing = _footing(70 * mm)
    d, _, _ = _limits(footing)
    _, _, A_s1, A_s2, A_s_calc = _calculate_flexural_reinforcement_EN_1992_2004(
        footing, 10 * _M_lim(footing) * 1e6, d, d
    )
    assert math.isinf(A_s_calc) and math.isinf(A_s1) and math.isinf(A_s2)


@pytest.mark.parametrize("cls", [OneWaySlab, Footing])
def test_a_thin_strip_with_deep_cover_is_designed(cls) -> None:  # type: ignore[no-untyped-def]
    """15 cm with 70 mm cover raised ZeroDivisionError in the design; now it says it is short."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # a footing this thin warns that it is
        strip = cls(
            concrete=Concrete_EN_1992_2004(name="C25", f_c=25 * MPa),
            steel_bar=SteelBar(name="B500S", f_y=500 * MPa),
            width=100 * cm,
            height=15 * cm,
            c_c=70 * mm,
        )
    check = _design_and_check(strip, 60 * kNm)
    assert check.bottom.DCR > 1.0
    assert "section_too_small_for_moment" in {w.code for w in strip.warnings}
