"""One-way shear of a column section — EN 1992-1-1 §6.2, with the column's §9.5.3.

The checker of ADR-0002 for a column, the counterpart of
:mod:`mento.codes.ACI_318_19_column`: it reads the section's float view once,
calls the float equations of :mod:`mento.codes.en_1992_2004.equations.shear`
and returns a :class:`~mento.column_results.ColumnShearCheck`.

The resistance is the beam's -- V_Rd,c of Expressions (6.2.a)/(6.2.b) with
σ_cp, the truss of §6.2.3 at the strut angle the demand fixes, V_Rd,max of
Expression (6.9) -- and on the same rectangle it gives the numbers of
:mod:`mento.codes.EN_1992_2004_beam` (``tests/elements/test_column.py``).
What differs is what a column is asked for:

* Shear reinforcement is required where V_Ed > V_Rd,c (§6.2.1(3)). Below it,
  §6.2.1(4) asks for the minimum of §9.2.2, which is the beams'; a column's
  transverse reinforcement is §9.5.3, a detailing rule this check does not
  read. So there is no A_v,min, and A_v,req is the truss's alone.
* Where it is required, the spacings of §9.2.2(6) and (8), as for a beam.
* α_cw is Expression (6.11aN) with the combination's axial compression,
  N_Ed/A_c, unless the column turns it off (``alpha_cw_from_axial_load``;
  #210, roadmap D4). The beam keeps α_cw = 1.

A circle has no clause in EN 1992-1-1. It is checked by Orr, Darby, Ibell,
Denton and Shave, "Shear design of circular concrete sections using the
Eurocode 2 truss model", The Structural Engineer 88(23-24), 2010 (roadmap D3):
the truss of Expression (6.8) on the lever arm z between the chords times
the share λ1·λ2 of a circular link or spiral that crosses the shear (Eqs.
(6), (9), (18)), λ1 no more than the 0.85 of their Eq. (7) and §4.1,
and V_Rd,max of Expression (6.9) on the web of their equivalent rectangle
(Eqs. (10)-(14)). d and z are the section's (``CircularColumn.set_lever_arm``)
or, by default, the neutral axis at the centre and z = 0.77·d. V_Rd,c follows
§6.2.2(2): Expression (6.4) -- Orr's Eq. (17) -- where the combination's
flexural tension, M/W - N/A_c with M the resultant of M_y and M_z, stays
within f_ctd; Expressions (6.2.a)/(6.2.b) on the equivalent rectangle where it
does not. Eq. (17) on a cracked circle doubles V_Rd,c at low axial load, which
§6.2.2(2) does not allow.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, Optional, cast

from mento.codes.check_state import _scaled_to_display
from mento.codes.en_1992_2004.equations import shear as shear_eq
from mento.column_results import ColumnShearCheck
from mento.units import MPa, N, mm

if TYPE_CHECKING:
    from mento.column_section import ColumnSection, Direction
    from mento.forces import Forces
    from mento.material import Concrete_EN_1992_2004

#: The strut angles §6.2.3(2) allows with the recommended limits: 1 <= cot θ <= 2.5.
_THETA_MIN = math.radians(21.8)
_THETA_MAX = math.radians(45)


def check_column_shear_EN_1992_2004(
    column: "ColumnSection", force: "Forces", direction: "Direction"
) -> ColumnShearCheck:
    """The shear of one combination in one direction of a column.

    V_Rd = V_Rd,c while V_Ed <= V_Rd,c, or the larger of it and the truss
    the ties make (§6.2.1(3)); past it the truss alone, V_Rd,s capped by
    V_Rd,max (§6.2.1(5), Expressions (6.8) and (6.9)). The DCR is V_Ed over
    V_Rd, infinite where V_Rd is zero.
    """
    sec = column.shear_section(direction)
    concrete = cast("Concrete_EN_1992_2004", column.concrete)
    N_Ed = float(force._N_x.to(N).magnitude)
    V = force._V_y if direction == "y" else force._V_z
    V_Ed = abs(float(V.to(N).magnitude))

    # α_cc = 1 for shear, as the beam takes it.
    f_cd = sec.f_c / concrete.gamma_c
    f_ywd = sec.f_y / column.steel_bar.gamma_s
    if sec.circular:
        # Orr et al. (2010): the truss on d and z of the tension chord, the
        # links' share λ1·λ2 and the web of the equivalent rectangle.
        r = sec.b_w / 2
        d, z = sec.d_truss, sec.z_truss
        b_w = shear_eq.circular_equivalent_web_width(r, sec.r_sv, d, z)
        lambda_1 = min(shear_eq.circular_link_efficiency(d - r, z, sec.r_sv), shear_eq.CIRCULAR_LINK_EFFICIENCY_CAP)
        share = lambda_1 * shear_eq.spiral_efficiency(sec.pitch, sec.r_sv)
        # V_Rd,c by the state §6.2.2(2) asks about: Expression (6.4) (Orr's
        # Eq. (17)) where the flexural tension stays within f_ctd, the cracked
        # Expressions (6.2.a)/(6.2.b) on the equivalent rectangle where it does not.
        f_ctd = shear_eq.design_tensile_strength(float(concrete.f_ctm.to(MPa).magnitude), concrete.gamma_c)
        M_Ed = math.hypot(float(force._M_y.to(N * mm).magnitude), float(force._M_z.to(N * mm).magnitude))
        if shear_eq.circle_flexural_tension(M_Ed, N_Ed, r) <= f_ctd:
            V_Rd_c = shear_eq.uncracked_shear_resistance_circle(r, f_ctd, N_Ed / sec.A_g)
        else:
            V_Rd_c = _cracked_V_Rd_c(sec.f_c, concrete.gamma_c, sec.A_s, N_Ed, sec.A_g, f_cd, b_w, d)
    else:
        d, b_w, share = sec.d, sec.b_w, 1.0
        V_Rd_c = _cracked_V_Rd_c(sec.f_c, concrete.gamma_c, sec.A_s, N_Ed, sec.A_g, f_cd, b_w, d)
        z = shear_eq.lever_arm(d)
    required = V_Ed > V_Rd_c

    alpha_cw = 1.0
    if column.alpha_cw_from_axial_load:
        alpha_cw = shear_eq.compression_chord_coefficient(N_Ed / sec.A_g, f_cd)
    nu_1 = shear_eq.strut_strength_reduction_factor(sec.f_c)
    V_Rd_max_45 = shear_eq.max_shear_resistance(alpha_cw, b_w, z, nu_1, f_cd, _THETA_MAX)
    V_Rd_max_flat = shear_eq.max_shear_resistance(alpha_cw, b_w, z, nu_1, f_cd, _THETA_MIN)
    if V_Ed <= V_Rd_max_flat:
        theta = _THETA_MIN
    elif V_Ed > V_Rd_max_45:
        theta = _THETA_MAX
    else:
        theta = shear_eq.strut_angle(V_Ed, V_Rd_max_45)
    cot_theta = 1 / math.tan(theta)
    V_Rd_max = shear_eq.max_shear_resistance(alpha_cw, b_w, z, nu_1, f_cd, theta)

    # A share of the links below 1 asks for as much more area as it takes away.
    A_v_req = shear_eq.required_shear_reinforcement(V_Ed, z, f_ywd, cot_theta) / share if required else 0.0
    if sec.A_v > 0:
        truss = min(share * shear_eq.shear_reinforcement_resistance(sec.A_v, z, f_ywd, cot_theta), V_Rd_max)
        V_Rd = truss if required else max(V_Rd_c, truss)
    else:
        V_Rd = V_Rd_c
    DCR = V_Ed / V_Rd if V_Rd > 0 else float("inf")

    s_max_l: Optional[float] = None
    s_max_w: Optional[float] = None
    if required:
        s_max_l, s_max_w = shear_eq.max_stirrup_spacing(d, math.pi / 2)

    return ColumnShearCheck(
        label=force.label,
        direction=direction,
        N_demand=_q(N_Ed, "force"),
        V_demand=_q(V_Ed, "force"),
        b_w=_q(b_w, "length"),
        d=_q(d, "length"),
        V_concrete=_q(V_Rd_c, "force"),
        reinforcement_required=required,
        A_v=_q(sec.A_v, "per_length"),
        A_v_req=_q(A_v_req, "per_length"),
        A_v_min=_q(0.0, "per_length"),
        V_capacity=_q(V_Rd, "force"),
        V_max=_q(V_Rd_max_45, "force"),
        DCR=DCR,
        s_l=_length_or_none(sec.s_l),
        s_w=_length_or_none(sec.s_w),
        s_max_l=_length_or_none(s_max_l),
        s_max_w=_length_or_none(s_max_w) if sec.s_w else None,
        spacing_halved=None,
    )


def _cracked_V_Rd_c(
    f_ck: float, gamma_c: float, A_s: float, N_Ed: float, A_c: float, f_cd: float, b_w: float, d: float
) -> float:
    """V_Rd,c of Expressions (6.2.a)/(6.2.b), never negative: ρ_l capped at 0.02, σ_cp at 0.2·f_cd."""
    k = shear_eq.size_effect_factor(d)
    rho_l = min(A_s / (b_w * d), 0.02)
    sigma_cp = shear_eq.axial_stress(N_Ed, A_c, f_cd)
    return max(
        0.0,
        shear_eq.min_shear_resistance_without_reinforcement(f_ck, k, sigma_cp, b_w, d),
        shear_eq.shear_resistance_without_reinforcement(f_ck, gamma_c, k, rho_l, sigma_cp, b_w, d),
    )


def _q(value: float, kind: str) -> Any:
    """A float in N and mm as the quantity the result carries; EN 1992-1-1 is metric."""
    return _scaled_to_display(value, kind, False)


def _length_or_none(value: Optional[float]) -> Any:
    """A spacing as a quantity, or ``None`` where there is none."""
    return _scaled_to_display(value, "length", False) if value else None
