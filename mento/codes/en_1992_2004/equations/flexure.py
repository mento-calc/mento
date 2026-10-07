"""Flexure equations — EN 1992-1-1:2004, §3.1.7, §5.5, §6.1 and §9.2.1.

Pure functions of floats; see the package docstring for the unit convention
(N, mm, mm², MPa, N·mm).

Everything here is written on the *equivalent rectangular stress block* of
§3.1.7(3): a uniform eta*f_cd acting over a depth ``x_eff = lambda * x_u``,
where ``x_u`` is the neutral axis. The two depths are never interchangeable —
§5.5(4) bounds the neutral axis, §3.1.7(3) supplies the block — so each
function states which one it takes.
"""

from __future__ import annotations

import math

__all__ = [
    "min_reinforcement_ratio",
    "foundation_min_reinforcement_ratio",
    "crack_control_coefficient_k",
    "crack_control_min_reinforcement",
    "max_reinforcement_ratio",
    "neutral_axis_depth_limit_ratio",
    "limit_moment",
    "compression_block_depth_for_moment",
    "lever_arm",
    "reinforcement_for_moment",
    "compression_steel_stress",
    "compression_block_depth_for_steel",
    "moment_resistance_singly_reinforced",
    "moment_resistance_doubly_reinforced",
]


def min_reinforcement_ratio(f_ctm: float, f_yk: float) -> float:
    """Minimum tension reinforcement ratio — EN 1992-1-1 §9.2.1.1(1), Eq. (9.1N).

    Args:
        f_ctm: Mean axial tensile strength of the concrete (MPa).
        f_yk: Characteristic yield strength of the reinforcement (MPa).

    Returns:
        A_s,min/(b_t*d), dimensionless: the larger of 0.26*f_ctm/f_yk and the
        absolute floor of 0.0013 the clause also imposes.
    """
    return max(0.26 * f_ctm / f_yk, 0.0013)


def foundation_min_reinforcement_ratio(f_yk: float) -> float:
    """Geometric minimum for a foundation, per direction — EHE-08 Tabla 42.3.5, note (1).

    This is an adopted detailing practice, not an EN 1992-1-1 requirement
    or an exemption from its strength and crack-control checks. EN §9.8.1(3)
    refers to minimum reinforcement in pile caps, and §9.8.2.1(1) specifies
    anchorage and a minimum bar diameter (8 mm recommended). Neither
    supplies the two geometric ratios used here. The numbers are EHE-08's,
    Tabla 42.3.5: a slab carries 2.0 per mille (f_y = 400 MPa) or 1.8 per
    mille (500 MPa) of the GROSS section, and note (1) gives footings and
    foundation slabs half of it in each direction, on the bottom face. mento
    applies that under EN as detailing practice, on ``b*h`` rather than on
    the effective depth.

    Args:
        f_yk: Characteristic yield strength of the reinforcement (MPa).

    Returns:
        A_s,min/(b*h), dimensionless: 1.0 per mille at f_yk = 400 MPa and
        0.9 per mille at f_yk = 500 MPa, the two grades the rule is tabulated
        for. Linear interpolation and holding the value flat outside those
        grades are Mento choices, not prescriptions of EHE-08 Table 42.3.5.
    """
    ratio_400, ratio_500 = 0.0010, 0.0009
    if f_yk <= 400.0:
        return ratio_400
    if f_yk >= 500.0:
        return ratio_500
    return ratio_400 + (f_yk - 400.0) * (ratio_500 - ratio_400) / (500.0 - 400.0)


def crack_control_coefficient_k(h: float) -> float:
    """Coefficient k of the crack-control minimum — EN 1992-1-1 §7.3.2(2).

    Accounts for the non-uniform self-equilibrating stresses that relieve the
    tension a thick section has to carry: the deeper the member, the more of
    the restraint is taken by them and the less by the reinforcement.

    Args:
        h: Overall depth of the section (mm); for a flange or web the clause
            takes the smaller of the width and the height instead.

    Returns:
        k, dimensionless: 1.0 for h <= 300 mm, 0.65 for h >= 800 mm, linear in
        between and saturated at both ends.
    """
    if h <= 300.0:
        return 1.0
    if h >= 800.0:
        return 0.65
    return 1.0 + (h - 300.0) * (0.65 - 1.0) / (800.0 - 300.0)


def crack_control_min_reinforcement(k_c: float, k: float, f_ct_eff: float, A_ct: float, sigma_s: float) -> float:
    """Minimum reinforcement for crack control — EN 1992-1-1 §7.3.2(2), Eq. (7.1).

    ``A_s,min * sigma_s = k_c * k * f_ct,eff * A_ct``: enough steel to carry,
    without breaking, the tension the concrete releases at the instant it
    cracks.

    Args:
        k_c: Stress distribution coefficient — 0.4 for a rectangular section in
            pure bending, 1.0 in pure tension.
        k: Coefficient from :func:`crack_control_coefficient_k`.
        f_ct_eff: Tensile strength of the concrete at the moment cracking is
            expected, taken as f_ctm (MPa).
        A_ct: Area of concrete in the tension zone just before the first crack
            forms (mm²).
        sigma_s: Stress permitted in the reinforcement immediately after
            cracking (MPa).

    Returns:
        A_s,min (mm²).
    """
    return k_c * k * f_ct_eff * A_ct / sigma_s


def max_reinforcement_ratio() -> float:
    """Maximum reinforcement ratio — EN 1992-1-1 §9.2.1.1(3).

    Returns:
        A_s,max/A_c = 0.04, the recommended value for a section outside lap
        locations. It takes no argument because the clause is a flat limit,
        not a formula.
    """
    return 0.04


def neutral_axis_depth_limit_ratio(
    f_ck: float,
    delta: float,
    k_1: float,
    k_2: float,
    k_3: float,
    k_4: float,
) -> float:
    """Neutral axis depth limit x_u/d — EN 1992-1-1 §5.5(4), Eqs. (5.10a)/(5.10b).

    The redistribution limit is ``(delta - k_1)/k_2`` (``k_3``/``k_4``
    above C50/60), from the cited expressions. Mento additionally caps the
    result at 0.45 as a design choice; §5.5(4) does not prescribe that cap.
    The 0.45/0.35 limits in §5.6.3(2) concern yielding hinges with a rotation
    check and are not implemented by this helper. Both limits used here are
    written on the NEUTRAL AXIS, so
    the result must be multiplied by ``lambda`` before it can be used as a
    stress block depth.

    Args:
        f_ck: Characteristic concrete cylinder strength (MPa); selects which
            pair of k coefficients applies.
        delta: Ratio of the redistributed moment to the elastic moment.
        k_1: Coefficient of Eq. (5.10a), recommended 0.44.
        k_2: Coefficient of Eq. (5.10a), recommended 1.25*(0.6 + 0.0014/eps_cu2).
        k_3: Coefficient of Eq. (5.10b), recommended 0.54.
        k_4: Coefficient of Eq. (5.10b), recommended 1.25*(0.6 + 0.0014/eps_cu2).

    Returns:
        xi_lim = x_u/d at the limit, dimensionless.
    """
    if f_ck <= 50:
        xi_lim = (delta - k_1) / k_2
    else:
        xi_lim = (delta - k_3) / k_4
    return min(xi_lim, 0.45)


def limit_moment(eta: float, f_cd: float, b: float, x_eff_lim: float, d: float) -> float:
    """Moment the concrete alone can balance at the ductility limit — EN 1992-1-1 §3.1.7(3).

    The compression resultant of the rectangular block, ``eta*f_cd*b*x_eff``,
    acting at the lever arm ``d - x_eff/2``, evaluated at the deepest block
    §5.5(4) allows. Above this moment the section needs compression
    reinforcement.

    Args:
        eta: Effective strength factor of §3.1.7(3).
        f_cd: Design compressive strength of the concrete (MPa).
        b: Section width (mm).
        x_eff_lim: Stress BLOCK depth at the limit, lambda*x_u,lim (mm).
        d: Effective depth of the tension reinforcement (mm).

    Returns:
        M_lim (N·mm).
    """
    return eta * f_cd * b * x_eff_lim * (d - 0.5 * x_eff_lim)


def compression_block_depth_for_moment(M_Ed: float, b: float, d: float, eta: float, f_cd: float) -> float:
    """Stress block depth that balances a moment — EN 1992-1-1 §3.1.7(3), §6.1.

    Inverts ``M = eta*f_cd*b*x_eff*(d - x_eff/2)`` for ``x_eff``. The relative
    moment ``K = M/(b*d²*eta*f_cd)`` makes the inversion a quadratic whose
    lower root is ``x_eff = d*(1 - sqrt(1 - 2K))``. Because the inversion is on
    the block equation, the result is ALREADY ``lambda*x_u``: lambda must not
    be applied to it again.

    Args:
        M_Ed: Design moment, positive (N·mm).
        b: Section width (mm).
        d: Effective depth (mm).
        eta: Effective strength factor of §3.1.7(3).
        f_cd: Design compressive strength of the concrete (MPa).

    Returns:
        x_eff (mm). Only valid while K <= 0.5, i.e. while the section is
        singly reinforced; the caller checks M_Ed against
        :func:`limit_moment` first.
    """
    K_value = M_Ed / (b * d**2 * eta * f_cd)
    return d * (1 - math.sqrt(1 - 2 * K_value))


def lever_arm(d: float, x_eff: float) -> float:
    """Inner lever arm of the rectangular block — EN 1992-1-1 §3.1.7(3).

    Args:
        d: Depth of the reinforcement the arm is measured to (mm).
        x_eff: Stress block depth (mm).

    Returns:
        z = d - x_eff/2 (mm), the distance from the reinforcement to the
        centroid of the uniform compression block.
    """
    return d - 0.5 * x_eff


def reinforcement_for_moment(M: float, z: float, f_sd: float) -> float:
    """Reinforcement needed to carry a moment on a lever arm — EN 1992-1-1 §6.1.

    Args:
        M: Moment to be carried by this couple (N·mm).
        z: Lever arm of the couple (mm) — ``d - x_eff/2`` for the concrete
            couple, ``d - d'`` for the compression steel couple.
        f_sd: Design stress in that reinforcement (MPa).

    Returns:
        The steel area (mm²).
    """
    return M / (z * f_sd)


def compression_steel_stress(x_u: float, d_prime: float, epsilon_cu2: float, E_s: float, f_yd: float) -> float:
    """Stress reached by the compression reinforcement — EN 1992-1-1 §6.1, §3.2.7(2).

    Plane sections (§6.1(2)) give the strain from the neutral axis:
    ``eps_s' = (x_u - d')/x_u * eps_cu2``. The bilinear steel diagram of
    §3.2.7(2) then caps the stress at f_yd.

    Args:
        x_u: NEUTRAL AXIS depth, not the block depth (mm).
        d_prime: Depth from the compression face to the compression steel (mm).
        epsilon_cu2: Ultimate concrete strain of Table 3.1.
        E_s: Modulus of elasticity of the reinforcement (MPa).
        f_yd: Design yield strength of the reinforcement (MPa).

    Returns:
        f_sd' (MPa).
    """
    epsilon_s2 = (x_u - d_prime) / x_u * epsilon_cu2
    return min(epsilon_s2 * E_s, f_yd)


def compression_block_depth_for_steel(A_s: float, f_yd: float, eta: float, f_cd: float, b: float) -> float:
    """Stress block depth that balances the tension steel — EN 1992-1-1 §6.1.

    Horizontal equilibrium ``eta*f_cd*b*x_eff = A_s*f_yd``, assuming the
    tension steel yields and the section is singly reinforced.

    Args:
        A_s: Tension reinforcement area (mm²).
        f_yd: Design yield strength of the reinforcement (MPa).
        eta: Effective strength factor of §3.1.7(3).
        f_cd: Design compressive strength of the concrete (MPa).
        b: Section width (mm).

    Returns:
        x_eff (mm).
    """
    return A_s * f_yd / (eta * f_cd * b)


def moment_resistance_singly_reinforced(A_s: float, f_yd: float, d: float, x_eff: float) -> float:
    """Design bending resistance, singly reinforced — EN 1992-1-1 §6.1.

    Args:
        A_s: Tension reinforcement area (mm²).
        f_yd: Design yield strength of the reinforcement (MPa).
        d: Effective depth (mm).
        x_eff: Stress block depth from
            :func:`compression_block_depth_for_steel` (mm).

    Returns:
        M_Rd (N·mm), the tension force on its lever arm.
    """
    return A_s * f_yd * lever_arm(d, x_eff)


def moment_resistance_doubly_reinforced(
    A_s: float,
    A_s_prime: float,
    f_yd: float,
    eta: float,
    f_cd: float,
    b: float,
    d: float,
    d_prime: float,
    x_eff_lim: float,
) -> float:
    """Design bending resistance with compression reinforcement — EN 1992-1-1 §6.1, §5.5(4).

    Used only once the block the tension steel would need exceeds the ductility
    limit. The concrete contribution then saturates at the limit block, and the
    tension steel beyond ``A_s,lim`` is balanced by whatever compression steel
    is actually there, on the lever arm ``d - d'``.

    At ``x_eff = x_eff_lim`` this returns exactly the M_lim of
    :func:`limit_moment`, so the resistance is continuous across the branch.

    Args:
        A_s: Tension reinforcement area (mm²).
        A_s_prime: Compression reinforcement area (mm²).
        f_yd: Design yield strength of the reinforcement (MPa).
        eta: Effective strength factor of §3.1.7(3).
        f_cd: Design compressive strength of the concrete (MPa).
        b: Section width (mm).
        d: Effective depth of the tension steel (mm).
        d_prime: Depth to the compression steel (mm).
        x_eff_lim: Stress BLOCK depth at the ductility limit (mm).

    Returns:
        M_Rd (N·mm).
    """
    A_s_lim = eta * f_cd * b * x_eff_lim / f_yd
    M_lim = A_s_lim * f_yd * lever_arm(d, x_eff_lim)
    # The couple can only develop up to the steel actually on the compression
    # face; extra tension steel beyond that is simply not usable.
    A_s_couple = min(A_s - A_s_lim, A_s_prime)
    return M_lim + A_s_couple * f_yd * (d - d_prime)
