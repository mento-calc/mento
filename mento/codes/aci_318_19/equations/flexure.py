"""Flexure equations — ACI 318-19, Chapters 9, 21 and 22.

CIRSOC 201-25 reprints these chapters under the same numbering, so every
function below carries both citations. One thing the two codes print
differently reaches this module, and it arrives as an argument rather than
written in: the cap on f_y inside §9.6.1.2 (ACI 550 MPa / 80,000 psi against
CIRSOC 500 MPa), which the caller reads off the code's registry entry.

Pure functions of floats; see the package docstring for the unit convention.
Areas are mm² (or in²) and moments N·mm (or lb·in), consistent with the stress
and length units of the system in use.
"""

from __future__ import annotations

import math

__all__ = [
    "max_reinforcement_ratio",
    "min_reinforcement_ratio",
    "shrinkage_and_temperature_ratio",
    "max_bar_spacing_crack_control",
    "neutral_axis_at_ductility_limit",
    "compression_steel_net_stress",
    "flexural_resistance_factor",
    "singly_reinforced_discriminant",
    "tension_steel_for_moment",
    "neutral_axis_depth",
    "nominal_moment_singly_reinforced",
    "nominal_moment_doubly_reinforced",
    "nominal_moment_strain_compatibility",
    "net_tensile_strain",
    "flexure_strength_reduction_factor",
]


def max_reinforcement_ratio(f_c: float, f_y: float, beta_1: float, epsilon_c: float, epsilon_y: float) -> float:
    """Maximum tension reinforcement ratio rho_max — ACI 318-19 §9.3.3.1 / CIRSOC 201-25 §9.3.3.1.

    The ductility limit: the largest ratio that still leaves the section
    tension-controlled. A nonprestressed beam has to be tension-controlled per
    Table 21.2.2 of both codes (a slab too, by ACI 318-19 §7.3.3.1 / CIRSOC
    201-25 §7.3.3), and that table puts the limit at eps_t = eps_ty + 0.003.
    With eps_cu = 0.003 (§22.2.2.1 in both) and linear strains (§22.2.1.2 in
    both), c/d = eps_cu/(eps_cu + eps_t), so the denominator below is
    eps_y + 2*eps_c — which is the sum, not eps_t itself. Form taken from the
    CRSI Design Guide, Beam Theory p. 6-3.

    Args:
        f_c: Specified concrete compressive strength (MPa, or psi).
        f_y: Specified steel yield strength, same unit as ``f_c``.
        beta_1: Stress block factor, ACI 318-19 Table 22.2.2.4.3 / CIRSOC
            201-25 Tabla 22.2.2.4.3.
        epsilon_c: Concrete crushing strain (0.003 in ACI).
        epsilon_y: Steel yield strain.

    Returns:
        rho_max, dimensionless.
    """
    return 0.85 * beta_1 * f_c / f_y * (epsilon_c / (epsilon_y + epsilon_c * 2))


def min_reinforcement_ratio(
    f_c: float, f_y: float, f_y_cap: float | None = None, *, is_imperial: bool = False
) -> float:
    """Minimum flexural reinforcement ratio rho_min — ACI 318-19 §9.6.1.2 / CIRSOC 201-25 §9.6.1.2.

    Expressions (a) and (b) are the same in both codes: 0.25*sqrt(f_c)/f_y and
    1.4/f_y in SI, 3*sqrt(f_c)/f_y and 200/f_y in psi.

    Both clauses also cap the f_y that may be put into them, and that cap is
    where they differ: "The value of fy shall be limited to a maximum of
    550 MPa" (ACI 318-19 §9.6.1.2; "80,000 psi" in the in-lb edition) against
    "El valor de fy debe limitarse a un máximo de 500 MPa" (CIRSOC 201-25
    §9.6.1.2). What it caps is the value entering the formula, not the steel
    the section is designed with, and since f_y is in the denominator of both
    expressions the cap only ever raises rho_min — ignoring it is
    unconservative. Which of the two numbers applies is a datum of the design
    code, so it arrives as ``f_y_cap``, the way the absolute spacing caps of
    Table 9.7.6.2.2 reach :func:`shear.max_stirrup_spacing`. Neither cap is
    reached by the ADN 420 of ordinary practice.

    Args:
        f_c: Specified concrete compressive strength (MPa, or psi).
        f_y: Specified steel yield strength, same unit as ``f_c``.
        f_y_cap: Largest f_y this code lets into the formula, same unit as
            ``f_y``: 550 MPa (80,000 psi) under ACI 318-19, 500 MPa under
            CIRSOC 201-25. Omitted, it defaults to the ACI cap in the selected
            unit system, preserving the two-argument equation interface.

    Returns:
        rho_min, dimensionless. The clause is the larger of a sqrt(f_c) term
        and a floor that governs at low concrete strengths.
    """
    cap = (80000.0 if is_imperial else 550.0) if f_y_cap is None else f_y_cap
    f_y_eff = min(f_y, cap)
    if is_imperial:
        return max(3 * math.sqrt(f_c) / f_y_eff, 200 / f_y_eff)
    return max(0.25 * math.sqrt(f_c) / f_y_eff, 1.4 / f_y_eff)


def shrinkage_and_temperature_ratio() -> float:
    """Slab minimum and shrinkage and temperature ratio — ACI 318-19 §7.6.1.1 and §24.4.3.2 / CIRSOC 201-25 §7.6.1 and §24.4.3.2.

    The minimum of a one-way slab and of a member on the ground, written on
    the GROSS section ``b*h`` rather than on the effective depth the flexural
    minimum of §9.6.1.2 uses. A slab reaches it directly; a one-way shallow
    foundation through §13.3.2.1, which sends it to Chapters 7 and 9 (two-way:
    §13.3.3.1 → §8.6.1.1, the same 0.0018*A_g). CIRSOC 201-25 prints the same
    chain: §13.3.2.1 → §7.6.1 (an unnumbered paragraph, "As,min de 0,0018Ag")
    and §13.3.3.1 → §8.6.1.1.

    One flat ratio for every f_y. The 0.0018*420/f_y (60,000/f_y psi) with a
    0.0014 floor is Table 7.6.1.1 / Table 24.4.3.2 of ACI 318-14, which neither
    code carries any more -- ACI 318-19 R24.4.3.2 records that the reduction
    for f_y over 420 MPa was withdrawn because a stronger steel gives no
    benefit for crack control.

    Returns:
        A_s,min/(b*h), dimensionless: 0.0018.
    """
    return 0.0018


def max_bar_spacing_crack_control(f_s: float, c_c: float, *, is_imperial: bool = False) -> float:
    """Maximum spacing of the bars nearest the tension face — ACI 318-19 Table 24.3.2 / CIRSOC 201-25 Tabla 24.3.2.

    The crack-control limit §24.3.2 puts on the bonded reinforcement closest
    to the tension face of a nonprestressed one-way slab or beam, which
    §7.7.2.2 (slabs) and §9.7.2.2 (beams) send there in both codes. For
    deformed bars or wires, the lesser of::

        380 * (280 / f_s) - 2.5 * c_c        and        300 * (280 / f_s)     [mm, MPa]
        15 * (40,000 / f_s) - 2.5 * c_c      and        12 * (40,000 / f_s)   [in, psi]

    Read off the printed table: ACI 318-19 SI p. 460 (PDF 462), in-lb p. 460 (PDF 462);
    CIRSOC 201-25 Cap. 24-435. The rows for prestressed reinforcement are not
    carried, since mento designs none.

    Args:
        f_s: Stress in the bars nearest the tension face at service loads
            (MPa, or psi). §24.3.2.1 lets it be taken as (2/3)*f_y in place
            of a calculation from the unfactored moment, which is what a
            caller with factored loads only can do: 280 MPa (40,000 psi) for
            Grade 420 (60).
        c_c: Least distance from the surface of those bars to the tension
            face (mm, or in): the clear cover to the stirrup plus the stirrup.
        is_imperial: Whether ``f_s`` and ``c_c`` are in psi and inches.

    Returns:
        s_max (mm, or in). With Grade 420 steel and 25 mm of cover to the
        bars, 380 - 62.5 = 317.5 against 300: the second term governs, and
        every slab and beam of that grade is held to 300 mm unless its cover
        passes 32 mm.
    """
    if is_imperial:
        return min(15.0 * (40_000.0 / f_s) - 2.5 * c_c, 12.0 * (40_000.0 / f_s))
    return min(380.0 * (280.0 / f_s) - 2.5 * c_c, 300.0 * (280.0 / f_s))


def neutral_axis_at_ductility_limit(d: float, epsilon_y: float) -> float:
    """Neutral axis depth at the tension-controlled boundary — ACI 318-19 Table 21.2.2 / CIRSOC 201-25 Tabla 21.2.2.

    The limit is eps_t = eps_ty + 0.003 in both codes, so with eps_cu = 0.003
    (§22.2.2.1 in both) strain compatibility (§22.2.1.2 in both,
    c/d = eps_cu / (eps_cu + eps_t)) gives
    c_t = 0.003*d / (0.003 + eps_y + 0.003) = 0.003*d / (eps_y + 0.006).

    Args:
        d: Effective depth of the tension reinforcement (mm, or in).
        epsilon_y: Steel yield strain.

    Returns:
        c_t (mm, or in). A section with c < c_t is tension-controlled.
    """
    return 0.003 * d / (epsilon_y + 0.006)


def compression_steel_net_stress(d_prime: float, c_t: float, E_s: float, f_y: float, f_c: float) -> float:
    """Compression steel stress at the ductility limit, net of displaced concrete.

    ACI 318-19 §22.2.1.2 / CIRSOC 201-25 §22.2.1.2 (strains proportional to the
    distance from the neutral axis) with the equivalent rectangular stress block
    of ACI 318-19 §22.2.2.4.1 / CIRSOC 201-25 §22.2.2.4.1, and the bar stress
    capped at f_y by ACI 318-19 §20.2.2.1 / CIRSOC 201-25 §20.2.2.1. The same
    three clauses in both codes.

        eps_s' = (c_t - d')/c_t * 0.003
        f_s'   = min(eps_s'*E_s, f_y)
        net    = f_s' - 0.85*f_c

    The subtraction accounts for the concrete the bar displaces: that volume is
    already carrying 0.85*f_c inside the rectangular block, so counting the full
    bar stress would count it twice.

    Args:
        d_prime: Depth to the compression reinforcement (mm, or in).
        c_t: Neutral axis at the ductility limit, from
            :func:`neutral_axis_at_ductility_limit` (mm, or in).
        E_s: Steel modulus of elasticity (MPa, or psi).
        f_y: Steel yield strength (MPa, or psi).
        f_c: Concrete compressive strength (MPa, or psi).

    Returns:
        The net compression steel stress (MPa, or psi).
    """
    f_s_prime = min(0.003 * E_s * (1 - d_prime / c_t), f_y)
    return f_s_prime - 0.85 * f_c


def flexural_resistance_factor(M_u: float, phi: float, b: float, d: float) -> float:
    """Required flexural resistance R_n = M_u/(phi*b*d²) — ACI 318-19 §22.3.1.1 / CIRSOC 201-25 §22.3.1.1.

    Not a published formula: the textbook rearrangement of phi*M_n >= M_u under
    the §22.2 assumptions, which both codes share. Cited so the derivation can
    be traced, not because either code prints it.

    Args:
        M_u: Factored moment, positive (N·mm, or lb·in).
        phi: Strength reduction factor for flexure.
        b: Section width (mm, or in).
        d: Effective depth (mm, or in).

    Returns:
        R_n as a stress (MPa, or psi).
    """
    return M_u / (phi * b * d**2)


def singly_reinforced_discriminant(R_n: float, f_c: float) -> float:
    """Term under the root of the singly reinforced solution — ACI 318-19 §22.2 / CIRSOC 201-25 §22.2.

    Part of the same textbook inversion as :func:`tension_steel_for_moment`,
    resting on the §22.2 assumptions, which both codes print alike.

    Args:
        R_n: Required flexural resistance from :func:`flexural_resistance_factor`.
        f_c: Concrete compressive strength, same unit as ``R_n``.

    Returns:
        ``1 - 2*R_n/(0.85*f_c)``. Negative means the demand exceeds what the
        section can carry with tension steel alone, and the caller must fall
        back to a doubly reinforced solution or report the section as
        insufficient — that decision is orchestration, not this equation.
    """
    return 1 - 2 * R_n / (0.85 * f_c)


def tension_steel_for_moment(R_n: float, f_c: float, f_y: float, b: float, d: float) -> float:
    """Tension steel required for a moment — ACI 318-19 §22.2 / CIRSOC 201-25 §22.2, singly reinforced.

    Inverts the rectangular stress block of ACI 318-19 §22.2.2.4.1 / CIRSOC
    201-25 §22.2.2.4.1 for A_s — a derivation, not a published formula, and the
    same one under either code. Only valid when
    :func:`singly_reinforced_discriminant` is non-negative.

    Args:
        R_n: Required flexural resistance (MPa, or psi).
        f_c: Concrete compressive strength (MPa, or psi).
        f_y: Steel yield strength (MPa, or psi).
        b: Section width (mm, or in).
        d: Effective depth (mm, or in).

    Returns:
        A_s (mm², or in²).
    """
    return 0.85 * f_c * b * d / f_y * (1 - math.sqrt(singly_reinforced_discriminant(R_n, f_c)))


def neutral_axis_depth(A_s: float, f_y: float, f_c: float, b: float, beta_1: float) -> float:
    """Neutral axis depth from equilibrium — ACI 318-19 §22.2.2.4.1 / CIRSOC 201-25 §22.2.2.4.1.

    From 0.85*f_c*(beta_1*c)*b = A_s*f_y, with a = beta_1*c. Both codes print
    the same stress block: 0.85*f_c uniform over a depth a.

    Args:
        A_s: Tension reinforcement area (mm², or in²).
        f_y: Steel yield strength (MPa, or psi).
        f_c: Concrete compressive strength (MPa, or psi).
        b: Section width (mm, or in).
        beta_1: Stress block factor.

    Returns:
        c (mm, or in).
    """
    return A_s * f_y / (0.85 * f_c * b * beta_1)


def nominal_moment_singly_reinforced(A_s: float, f_y: float, f_c: float, b: float, d: float) -> float:
    """Nominal moment of a singly reinforced section — ACI 318-19 §22.3.1.1 / CIRSOC 201-25 §22.3.1.1.

    Force equilibrium 0.85*f_c*a*b = A_s*f_y over the rectangular stress block
    of §22.2.2.4.1 in both codes fixes the depth a = A_s*f_y/(0.85*f_c*b); the
    lever arm is then d - a/2. Valid only while A_s does not exceed the maximum
    that keeps the section tension-controlled (Table 21.2.2 in both codes), for
    which see :func:`max_reinforcement_ratio`.

    Args:
        A_s: Tension reinforcement area (mm², or in²).
        f_y: Steel yield strength (MPa, or psi).
        f_c: Concrete compressive strength (MPa, or psi).
        b: Section width (mm, or in).
        d: Effective depth (mm, or in).

    Returns:
        M_n (N·mm, or lb·in).
    """
    a = A_s * f_y / (0.85 * f_c * b)
    return A_s * f_y * (d - a / 2)


def nominal_moment_doubly_reinforced(
    A_s: float,
    A_s_prime: float,
    f_y: float,
    f_c: float,
    b: float,
    d: float,
    d_prime: float,
    beta_1: float,
    epsilon_c: float,
    epsilon_y: float,
    E_s: float,
) -> float:
    """Nominal moment with compression reinforcement — ACI 318-19 §22.3.1.1 / CIRSOC 201-25 §22.3.1.1.

    Two cases, decided by whether the compression steel yields. The assumptions
    behind both are §22.2 of either code: linear strains (§22.2.1.2), the
    rectangular stress block (§22.2.2.4.1) and f_s = E_s*eps_s capped at f_y
    (§20.2.2.1). Nothing here differs between the two codes.

    Equilibrium carries the displaced-concrete correction throughout: the
    compression bar sits inside the 0.85*f_c*a*b block, so its effective
    contribution is (f_y - 0.85*f_c), not f_y.

    First the neutral axis is solved assuming the compression steel yields::

        c = (A_s*f_y - A_s'*(f_y - 0.85*f_c)) / (0.85*f_c*b*beta_1)

    If the resulting strain reaches eps_y the assumption holds. Otherwise c is
    re-solved from the quadratic that keeps the compression steel elastic,
    A*c² + B*c + C = 0 with A = 0.85*f_c*b*beta_1,
    B = A_s'*(eps_c*E_s - 0.85*f_c) - A_s*f_y and C = -d'*A_s'*eps_c*E_s.

    Args:
        A_s: Tension reinforcement area (mm², or in²).
        A_s_prime: Compression reinforcement area (mm², or in²).
        f_y: Steel yield strength (MPa, or psi).
        f_c: Concrete compressive strength (MPa, or psi).
        b: Section width (mm, or in).
        d: Effective depth of the tension steel (mm, or in).
        d_prime: Depth to the compression steel (mm, or in).
        beta_1: Stress block factor.
        epsilon_c: Concrete crushing strain.
        epsilon_y: Steel yield strain.
        E_s: Steel modulus of elasticity (MPa, or psi).

    Returns:
        M_n (N·mm, or lb·in).
    """
    # Step 1: assume the compression steel yields and solve for the neutral axis.
    c_assumed = (A_s * f_y - A_s_prime * (f_y - 0.85 * f_c)) / (0.85 * f_c * b * beta_1)

    # A zero neutral axis happens when top and bottom steel are equal; the
    # compression steel is then certainly not yielding.
    epsilon_s = (c_assumed - d_prime) / c_assumed * epsilon_c if c_assumed > 0 else 0

    # Step 2: if the assumed strain reaches yield, the assumption stands.
    if epsilon_s >= epsilon_y:
        a_assumed = c_assumed * beta_1
        return 0.85 * f_c * a_assumed * b * (d - a_assumed / 2) + A_s_prime * (f_y - 0.85 * f_c) * (d - d_prime)

    # Otherwise re-solve with the compression steel still elastic.
    A = 0.85 * f_c * b * beta_1
    B = A_s_prime * (epsilon_c * E_s - 0.85 * f_c) - A_s * f_y
    C = -d_prime * A_s_prime * epsilon_c * E_s

    c = (-B + math.sqrt(B**2 - 4 * A * C)) / (2 * A)
    a = c * beta_1

    f_s_prime_net = (c - d_prime) / c * epsilon_c * E_s - 0.85 * f_c

    # Part of the tension steel is balanced by the net compression steel force.
    A_s_2 = A_s_prime * f_s_prime_net / f_y
    A_s_1 = A_s - A_s_2

    return A_s_1 * f_y * (d - a / 2) + A_s_prime * f_s_prime_net * (d - d_prime)


def nominal_moment_strain_compatibility(
    A_s: float,
    A_s_prime: float,
    f_y: float,
    f_c: float,
    b: float,
    d: float,
    d_prime: float,
    beta_1: float,
    epsilon_c: float,
    E_s: float,
) -> tuple[float, float]:
    """Nominal moment and neutral axis by strain compatibility — ACI 318-19 §22.2 / CIRSOC 201-25 §22.2.

    The general solution the two closed forms above are special cases of,
    written for a section that may be past the tension-controlled limit: every
    bar is taken at the stress its strain gives it -- linear strains with
    eps_cu at the extreme fibre (§22.2.1.2, §22.2.2.1), f_s = E_s*eps_s capped
    at f_y (§20.2.2.1) -- so the tension steel need not yield, and nothing is
    capped. The same clauses in both codes.

    The neutral axis is the root of the force balance

        0.85*f_c*b*beta_1*c + A_s'*(f_s' - 0.85*f_c) = A_s*f_s

    with the displaced-concrete correction on the compression bar that
    :func:`nominal_moment_doubly_reinforced` applies. Every term moves one way
    with c -- the concrete and the compression bar carry more, the tension bar
    less -- so the root is unique, and it lies between 0 and d, where the
    tension bar carries nothing. It is found by bisection, to a tolerance far
    below anything a detail can hold.

    Args:
        A_s: Tension reinforcement area (mm², or in²).
        A_s_prime: Compression reinforcement area (mm², or in²); 0 for none.
        f_y: Steel yield strength (MPa, or psi).
        f_c: Concrete compressive strength (MPa, or psi).
        b: Section width (mm, or in).
        d: Effective depth of the tension steel (mm, or in).
        d_prime: Depth to the compression steel (mm, or in).
        beta_1: Stress block factor.
        epsilon_c: Concrete crushing strain.
        E_s: Steel modulus of elasticity (MPa, or psi).

    Returns:
        ``(M_n, c)``: the nominal moment about the tension steel (N·mm, or
        lb·in) and the neutral axis depth (mm, or in).
    """

    def _forces(c: float) -> tuple[float, float, float]:
        a = beta_1 * c
        C_c = 0.85 * f_c * a * b
        f_s_prime = max(-f_y, min(f_y, E_s * epsilon_c * (c - d_prime) / c))
        C_s = A_s_prime * (f_s_prime - 0.85 * f_c)
        f_s = max(-f_y, min(f_y, E_s * epsilon_c * (d - c) / c))
        return C_c, C_s, A_s * f_s

    lo, hi = d * 1e-9, d
    for _ in range(100):
        c = 0.5 * (lo + hi)
        C_c, C_s, T = _forces(c)
        if C_c + C_s > T:
            hi = c
        else:
            lo = c
    c = 0.5 * (lo + hi)
    C_c, C_s, _ = _forces(c)
    a = beta_1 * c
    return C_c * (d - a / 2) + C_s * (d - d_prime), c


def net_tensile_strain(c: float, d: float, epsilon_c: float) -> float:
    """Net tensile strain in the tension steel — ACI 318-19 §21.2.2 / CIRSOC 201-25 §21.2.2.

    From linear strains (§22.2.1.2 in both): eps_t = eps_cu*(d - c)/c. The
    clause reads it at the extreme layer of tension steel, d_t; read at the
    centroid d, as here, it is never larger, so the classification it gives
    is on the safe side for a face in more than one layer.

    Args:
        c: Neutral axis depth (mm, or in).
        d: Depth at which the strain is read (mm, or in).
        epsilon_c: Concrete crushing strain.

    Returns:
        eps_t, dimensionless; positive in tension.
    """
    return epsilon_c * (d - c) / c


def flexure_strength_reduction_factor(epsilon_t: float, epsilon_ty: float) -> float:
    """phi for moment — ACI 318-19 Table 21.2.2 / CIRSOC 201-25 Tabla 21.2.2.

    0.90 for a tension-controlled section (eps_t >= eps_ty + 0.003), 0.65 for a
    compression-controlled one (eps_t <= eps_ty), and linear in between. The
    0.65 is the "other" transverse reinforcement row, the one a beam with
    stirrups falls in; the spiral row (0.75) does not apply to a beam. Both
    codes print the same table.

    Args:
        epsilon_t: Net tensile strain, from :func:`net_tensile_strain`.
        epsilon_ty: Yield strain of the tension steel, f_y/E_s.

    Returns:
        phi, dimensionless.
    """
    phi = 0.65 + 0.25 * (epsilon_t - epsilon_ty) / 0.003
    return max(0.65, min(0.90, phi))
