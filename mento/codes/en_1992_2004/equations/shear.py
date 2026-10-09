"""Shear equations — EN 1992-1-1:2004, §6.2 and §9.2.2.

Pure functions of floats; see the package docstring for the unit convention
(N, mm, MPa) and for how the code's recommended values are handled.
"""

from __future__ import annotations

import math

__all__ = [
    "K_1",
    "size_effect_factor",
    "axial_stress",
    "min_shear_reinforcement_ratio",
    "shear_resistance_without_reinforcement",
    "min_shear_resistance_without_reinforcement",
    "strut_strength_reduction_factor",
    "lever_arm",
    "max_shear_resistance",
    "strut_angle",
    "required_shear_reinforcement",
    "shear_reinforcement_resistance",
    "max_stirrup_spacing",
]

#: Coefficient on the axial stress term of Eqs. (6.2.a) and (6.2.b), EN
#: 1992-1-1 §6.2.2(1). 0.15 is the recommended value; a National Annex may
#: change it.
K_1 = 0.15


def size_effect_factor(d: float) -> float:
    """Size effect factor k — EN 1992-1-1 §6.2.2(1), Eq. (6.2.a).

    Args:
        d: Effective depth for shear (mm).

    Returns:
        k = 1 + sqrt(200/d), capped at 2.0 by the clause. The cap is part of the
        equation, not a guard: k rewards shallow members for the aggregate
        interlock that a deep member loses, and EN stops the reward at 2.
    """
    return min(1 + math.sqrt(200 / d), 2.0)


def axial_stress(N_Ed: float, A_c: float, f_cd: float) -> float:
    """Axial stress sigma_cp = N_Ed/A_c — EN 1992-1-1 §6.2.2(1).

    Args:
        N_Ed: Axial force, positive in compression (N).
        A_c: Gross concrete cross-sectional area (mm²).
        f_cd: Design compressive strength of the concrete (MPa).

    Returns:
        The axial stress used in Eqs. (6.2.a)/(6.2.b) (MPa), capped at
        0.2*f_cd by the clause.
    """
    return min(N_Ed / A_c, 0.2 * f_cd)


def min_shear_reinforcement_ratio(f_ck: float, f_ywk: float) -> float:
    """Minimum shear reinforcement ratio rho_w,min — EN 1992-1-1 §9.2.2(5), Eq. (9.5N).

    Args:
        f_ck: Characteristic concrete cylinder strength (MPa).
        f_ywk: Characteristic yield strength of the shear reinforcement (MPa).

    Returns:
        rho_w,min, dimensionless. The area follows from its definition in
        §9.2.2(5): A_sw/s = rho_w,min * b_w * sin(alpha).
    """
    return 0.08 * math.sqrt(f_ck) / f_ywk


def shear_resistance_without_reinforcement(
    f_ck: float,
    gamma_c: float,
    k: float,
    rho_l: float,
    sigma_cp: float,
    b_w: float,
    d: float,
) -> float:
    """Shear resistance of a member without shear reinforcement — EN 1992-1-1 §6.2.2(1), Eq. (6.2.a).

    ``C_Rd,c`` is taken as the recommended 0.18/gamma_c of §6.2.2(1).

    Args:
        f_ck: Characteristic concrete cylinder strength (MPa).
        gamma_c: Partial safety factor for concrete.
        k: Size effect factor from :func:`size_effect_factor`.
        rho_l: Longitudinal tension reinforcement ratio A_sl/(b_w*d), which the
            clause caps at 0.02 — the cap belongs to the caller, which knows
            which face is in tension.
        sigma_cp: Axial stress from :func:`axial_stress` (MPa).
        b_w: Smallest web width in the tension zone (mm).
        d: Effective depth (mm).

    Returns:
        V_Rd,c (N). Eq. (6.2.a) is a lower bound only above the floor of
        Eq. (6.2.b); see :func:`min_shear_resistance_without_reinforcement`.
    """
    C_Rd_c = 0.18 / gamma_c
    return (C_Rd_c * k * (100 * rho_l * f_ck) ** (1 / 3) + K_1 * sigma_cp) * b_w * d


def min_shear_resistance_without_reinforcement(
    f_ck: float,
    k: float,
    sigma_cp: float,
    b_w: float,
    d: float,
) -> float:
    """Floor on V_Rd,c — EN 1992-1-1 §6.2.2(1), Eq. (6.2.b) with v_min from Eq. (6.3N).

    Eq. (6.2.a) scales with rho_l**(1/3) and so collapses towards zero in a
    lightly reinforced member; Eq. (6.2.b) is the floor that stops it, using
    the recommended v_min = 0.035*k**(3/2)*sqrt(f_ck).

    Args:
        f_ck: Characteristic concrete cylinder strength (MPa).
        k: Size effect factor from :func:`size_effect_factor`.
        sigma_cp: Axial stress from :func:`axial_stress` (MPa).
        b_w: Smallest web width in the tension zone (mm).
        d: Effective depth (mm).

    Returns:
        The minimum V_Rd,c (N).
    """
    v_min = 0.035 * k ** (3 / 2) * math.sqrt(f_ck)
    return (v_min + K_1 * sigma_cp) * b_w * d


def strut_strength_reduction_factor(f_ck: float) -> float:
    """Strength reduction factor for concrete cracked in shear, nu_1 — EN 1992-1-1 §6.2.3(3), Note 1.

    Note 1 adopts nu from §6.2.2(6), Eq. (6.6N). The alternative values
    in §6.2.3(3), Note 2, Eqs. (6.10.aN)/(6.10.bN), are not used here.

    Args:
        f_ck: Characteristic concrete cylinder strength (MPa).

    Returns:
        nu = 0.6*(1 - f_ck/250), dimensionless.
    """
    return 0.6 * (1 - f_ck / 250)


def lever_arm(d: float) -> float:
    """Inner lever arm z — EN 1992-1-1 §6.2.3(1).

    Args:
        d: Effective depth (mm).

    Returns:
        z = 0.9*d (mm), the approximation the clause allows for a member
        without axial force and with vertical shear reinforcement.
    """
    return 0.9 * d


def max_shear_resistance(alpha_cw: float, b_w: float, z: float, nu_1: float, f_cd: float, theta: float) -> float:
    """Strut crushing resistance V_Rd,max — EN 1992-1-1 §6.2.3(3), Eq. (6.9).

    Args:
        alpha_cw: Coefficient for the state of stress in the compression chord
            (1.0 for a non-prestressed member).
        b_w: Smallest web width between tension and compression chords (mm).
        z: Inner lever arm from :func:`lever_arm` (mm).
        nu_1: Strength reduction factor from
            :func:`strut_strength_reduction_factor`.
        f_cd: Design compressive strength of the concrete (MPa).
        theta: Strut inclination (radians). §6.2.3(2) limits it to
            21.8 deg <= theta <= 45 deg, i.e. 1 <= cot(theta) <= 2.5.

    Returns:
        V_Rd,max (N). The denominator cot(theta) + tan(theta) is smallest — so
        the resistance is largest — at theta = 45 deg.
    """
    return alpha_cw * b_w * z * nu_1 * f_cd / (1 / math.tan(theta) + math.tan(theta))


def strut_angle(V_Ed: float, V_Rd_max_45: float) -> float:
    """Strut inclination that just carries V_Ed — EN 1992-1-1 §6.2.3(3), Eq. (6.9), inverted.

    At theta = 45 deg the denominator of Eq. (6.9) is 2, so
    V_Rd,max(theta) = V_Rd,max(45 deg) * sin(2*theta) and the demand fixes the
    angle as theta = asin(V_Ed/V_Rd,max(45 deg))/2.

    Args:
        V_Ed: Design shear force (N).
        V_Rd_max_45: V_Rd,max evaluated at theta = 45 deg (N), from
            :func:`max_shear_resistance`.

    Returns:
        theta (radians), the shallowest strut that still crushes at V_Ed. Only
        meaningful while V_Ed <= V_Rd_max_45; choosing the branch is the
        caller's job.
    """
    return 0.5 * math.asin(V_Ed / V_Rd_max_45)


def required_shear_reinforcement(V_Ed: float, z: float, f_ywd: float, cot_theta: float) -> float:
    """Shear reinforcement required for V_Ed — EN 1992-1-1 §6.2.3(3), Eq. (6.8), solved for A_sw/s.

    Args:
        V_Ed: Design shear force (N).
        z: Inner lever arm (mm).
        f_ywd: Design yield strength of the shear reinforcement (MPa).
        cot_theta: Cotangent of the strut inclination.

    Returns:
        A_sw/s (mm²/mm). The §9.2.2(5) minimum is not applied here; the caller
        takes the larger of the two.
    """
    return V_Ed / (z * f_ywd * cot_theta)


def max_stirrup_spacing(d: float, alpha: float) -> tuple[float, float]:
    """Maximum stirrup spacing along and across the member — EN 1992-1-1 §9.2.2(6) and (8).

    Args:
        d: Effective depth for shear (mm).
        alpha: Inclination of the shear reinforcement (radians); vertical
            stirrups are pi/2, for which the longitudinal limit is 0.75*d.

    Returns:
        ``(s_max_l, s_max_w)`` in mm, each capped: 400 mm along the member
        (mento's own cap; Expression (9.6N) has none), 600 mm across it
        (Expression (9.8N)).
    """
    s_max_l = min(0.75 * d * (1 + 1 / math.tan(alpha)), 400.0)
    s_max_w = min(0.75 * d, 600.0)
    return s_max_l, s_max_w


def shear_reinforcement_resistance(A_sw_s: float, z: float, f_ywd: float, cot_theta: float) -> float:
    """Shear carried by vertical stirrups V_Rd,s — EN 1992-1-1 §6.2.3(3), Eq. (6.8).

    Args:
        A_sw_s: Shear reinforcement area per unit length A_sw/s (mm²/mm).
        z: Inner lever arm (mm).
        f_ywd: Design yield strength of the shear reinforcement (MPa).
        cot_theta: Cotangent of the strut inclination.

    Returns:
        V_Rd,s (N).
    """
    return A_sw_s * z * f_ywd * cot_theta
