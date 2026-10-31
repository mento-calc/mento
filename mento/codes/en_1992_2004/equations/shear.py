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
    "compression_chord_coefficient",
    "design_tensile_strength",
    "uncracked_shear_resistance_circle",
    "CIRCULAR_LINK_EFFICIENCY_CAP",
    "circle_flexural_tension",
    "circular_link_efficiency",
    "spiral_efficiency",
    "circular_equivalent_web_width",
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


def compression_chord_coefficient(sigma_cp: float, f_cd: float) -> float:
    """alpha_cw under axial compression — EN 1992-1-1 §6.2.3(3), Note 3, Expression (6.11aN).

    The recommended values: 1 + sigma_cp/f_cd up to 0.25·f_cd, 1.25 up to
    0.5·f_cd, 2.5·(1 - sigma_cp/f_cd) up to f_cd. The Note gives 1 "for
    non-prestressed structures" before these; mento's column applies them to
    its axial load by default, and the beam does not (#210).

    Args:
        sigma_cp: Mean compressive stress in the concrete due to the design
            axial force, positive in compression (MPa). Not the capped stress
            of :func:`axial_stress`.
        f_cd: Design compressive strength of the concrete (MPa).

    Returns:
        alpha_cw: 1 with no compression; 0 at or past f_cd, where the strut
        has nothing left.
    """
    if sigma_cp <= 0:
        return 1.0
    if sigma_cp <= 0.25 * f_cd:
        return 1 + sigma_cp / f_cd
    if sigma_cp <= 0.5 * f_cd:
        return 1.25
    return max(2.5 * (1 - sigma_cp / f_cd), 0.0)


def design_tensile_strength(f_ctm: float, gamma_c: float) -> float:
    """Design tensile strength f_ctd — EN 1992-1-1 §3.1.6(2), Expression (3.16).

    f_ctd = α_ct·f_ctk,0.05/γ_c with the recommended α_ct = 1 and
    f_ctk,0.05 = 0.7·f_ctm of Table 3.1.

    Args:
        f_ctm: Mean axial tensile strength of the concrete (MPa).
        gamma_c: Partial factor for concrete.

    Returns:
        f_ctd (MPa).
    """
    return 0.7 * f_ctm / gamma_c


def uncracked_shear_resistance_circle(r: float, f_ctd: float, sigma_cp: float) -> float:
    """V_Rd,c of a circle — EN 1992-1-1 §6.2.2(2), Expression (6.4), as Orr et al. (2010) write it, Eq. (17).

    Expression (6.4) limits the principal tensile stress of a section
    uncracked in bending, V_Rd,c = I·b_w/S·√(f_ctd² + α_l·σ_cp·f_ctd). For a
    circle of radius r at its centroid, I·b_w/S = (πr⁴/4)(2r)/(2r³/3) = 3πr²/4,
    and α_l = 1 with no prestress (Orr, Darby, Ibell, Denton and Shave,
    "Shear design of circular concrete sections using the Eurocode 2 truss
    model", The Structural Engineer 88(23-24), 2010, §3.5). Like Expression
    (6.4) it holds only where the section is uncracked in bending
    (:func:`circle_flexural_tension`): on a cracked circle with little axial
    load it gives about twice what Expression (6.2.a) does.

    Args:
        r: Radius of the section (mm).
        f_ctd: Design tensile strength from :func:`design_tensile_strength` (MPa).
        sigma_cp: Mean axial stress N_Ed/A_c, positive in compression (MPa).

    Returns:
        V_Rd,c (N); zero once tension takes the root below zero.
    """
    root = f_ctd**2 + sigma_cp * f_ctd
    return 3 * math.pi * r**2 / 4 * math.sqrt(root) if root > 0 else 0.0


def _arc(u: float) -> float:
    """The integral of √(1 - u²): (u·√(1 - u²) + asin u)/2."""
    u = max(-1.0, min(1.0, u))
    return (u * math.sqrt(1 - u * u) + math.asin(u)) / 2


#: The largest share of a circular link mento credits: the 0.85 of Orr et al.
#: (2010), Eq. (7), which their §4.1 finds λ1 does not pass on the sections they
#: analysed. Eq. (6) passes it when the chords sit low, as the default d of a
#: neutral axis at the centre puts them.
CIRCULAR_LINK_EFFICIENCY_CAP = 0.85


def circle_flexural_tension(M_Ed: float, N_Ed: float, r: float) -> float:
    """Largest flexural tensile stress of a circle — EN 1992-1-1 §6.2.2(2), the condition on Expression (6.4).

    σ = M/W - N/A_c with W = πr³/4 and A_c = πr², tension positive. Expression
    (6.4) applies only where it stays within f_ctk,0.05/γ_c.

    Args:
        M_Ed: Design moment, the resultant of both axes for a circle (N·mm).
        N_Ed: Design axial force, positive in compression (N).
        r: Radius of the section (mm).

    Returns:
        The tensile stress at the extreme fibre (MPa); negative when the whole section is compressed.
    """
    return M_Ed / (math.pi * r**3 / 4) - N_Ed / (math.pi * r**2)


def circular_link_efficiency(z_0: float, z: float, r_sv: float) -> float:
    """λ1, the share of a circular link that carries shear — EN 1992-1-1 §6.2.3, Expression (6.8), after Orr et al. (2010).

    A closed circular link crosses the shear plane at an angle, so only a
    component of its force resists the shear. Orr et al., Eq. (6), after
    Turmo et al. (2009): λ1 = ∫₀¹ √(1 - ((z_0 - z·X)/r_sv)²) dX, integrated
    here in closed form. With z = 0.8·D, r_sv = 0.45·D and the chords
    equidistant from the centre (z_0 = z/2) it is the 0.85 of their Eq. (7).

    Args:
        z_0: Distance from the centroid of the tension forces to the centre of the section (mm).
        z: Lever arm (mm).
        r_sv: Radius to the centreline of the links (mm).

    Returns:
        λ1, dimensionless, at most 1.
    """
    return r_sv / z * (_arc(z_0 / r_sv) - _arc((z_0 - z) / r_sv))


def spiral_efficiency(pitch: float, r_sv: float) -> float:
    """λ2, the share of a spiral's force across the section — EN 1992-1-1 §6.2.3, after Orr et al. (2010), Eq. (9).

    λ2 = ((p/(2π·r_sv))² + 1)^-0.5: a spiral's force leans along the member
    by its pitch. 1 for closed links (p = 0).

    Args:
        pitch: Pitch of the spiral (mm); 0 for closed links.
        r_sv: Radius to the centreline of the links (mm).

    Returns:
        λ2, dimensionless.
    """
    return ((pitch / (2 * math.pi * r_sv)) ** 2 + 1) ** -0.5


def circular_equivalent_web_width(r: float, r_sv: float, d: float, z: float) -> float:
    """B_w of the strut of a circle — EN 1992-1-1 §6.2.3(3), Expression (6.9), after Orr et al. (2010), Eqs. (10)-(14).

    The web of the equivalent rectangle is the smaller of the section's width
    at the centroid of the compression chord, B_w,c = 2√(c(2r - c)) with
    c = d - z, and the width inside the links at the centroid of the
    tension, B_w,t = 2√(e(2r_sv - e)) with e = (D + 2r_sv)/2 - d.

    Args:
        r: Radius of the section (mm).
        r_sv: Radius to the centreline of the links (mm).
        d: Depth from the extreme compression fibre to the tension chord (mm).
        z: Lever arm (mm).

    Returns:
        B_w (mm).
    """
    c = d - z
    e = r + r_sv - d
    B_w_c = 2 * math.sqrt(max(c * (2 * r - c), 0.0))
    B_w_t = 2 * math.sqrt(max(e * (2 * r_sv - e), 0.0))
    return min(B_w_c, B_w_t)


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
