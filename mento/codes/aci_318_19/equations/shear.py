"""One-way shear equations — ACI 318-19, Chapter 22.5 and Table 9.6.3.4.

CIRSOC 201-25 reprints the same chapter under the same numbering, so every
function below carries both citations. Only two things the two codes print
differently reach this module, and each is noted where it arises: the
coefficient of §9.6.3.1 (CIRSOC 0.085 against ACI 0.083) and the absolute caps
of Table 9.7.6.2.2, which arrive as arguments from the code's registry entry.
The §22.5.3.1 ceiling on sqrt(f'c) is *not* one of them — 8.3 MPa in both books
— so :func:`sqrt_f_c_for_shear` holds it as a constant rather than as a hook.

Pure functions of floats; see the package docstring for the unit convention and
for why the SI and US customary coefficients are both spelled out instead of
one being converted into the other.
"""

from __future__ import annotations

import math

__all__ = [
    "size_effect_factor",
    "axial_stress_influence",
    "sqrt_f_c_for_shear",
    "concrete_shear_stress",
    "max_concrete_shear_stress",
    "shear_stress_capacity_increment",
    "min_shear_reinforcement_threshold_stress",
    "max_yield_strength_for_shear",
    "min_shear_reinforcement_ratio",
    "shear_strength_of_reinforcement",
    "max_stirrup_spacing",
    "max_stirrup_spacing_for_compression_support",
    "min_stirrup_diameter_for_compression_support",
    "min_stirrup_diameter_for_compression_support_cirsoc",
]


def size_effect_factor(d: float, *, is_imperial: bool = False) -> float:
    """Size effect factor lambda_s — ACI 318-19 Eq. (22.5.5.1.3) / CIRSOC 201-25 ec. (22.5.5.1.3).

    Identical in both codes, cap included.

    Args:
        d: Effective depth for shear (mm, or in when ``is_imperial``).

    Returns:
        lambda_s, capped at 1.0.

    The cap is part of the equation, not a guard: the factor exists to reduce
    V_c in deep members, so without it a shallow member (d below 250 mm / 10 in)
    would get lambda_s > 1 and an inflated V_c — the opposite of its purpose.
    """
    if is_imperial:
        return min(math.sqrt(2 / (1 + d / 10)), 1.0)
    return min(math.sqrt(2 / (1 + 0.004 * d)), 1.0)


def axial_stress_influence(N_u: float, A_g: float, f_c: float) -> float:
    """Axial stress term sigma_Nu = N_u / (6*A_g) — ACI 318-19 §22.5.5.1.2 / CIRSOC 201-25 §22.5.5.1.2.

    The term itself is the N_u/6A_g column of ACI 318-19 Table 22.5.5.1 /
    CIRSOC 201-25 Tabla 22.5.5.1, whose note 1 fixes the sign convention below;
    the cap on it is the clause in the summary line. Both codes print it the
    same way.

    Args:
        N_u: Factored axial force, positive in compression (N, or lb) — note 1
            of the table in both codes: positive for compression, negative for
            tension.
        A_g: Gross section area (mm², or in²).
        f_c: Specified concrete compressive strength (MPa, or psi).

    Returns:
        The axial contribution to shear stress, capped at 0.05*f_c by the
        clause. Same expression in both unit systems.
    """
    return min(N_u / (6 * A_g), 0.05 * f_c)


#: Ceiling on sqrt(f'c) for one-way V_c — ACI 318-19 §22.5.3.1 / CIRSOC 201-25
#: art. 22.5.3.1, 8.3 MPa and 100 psi, the same two numbers in both books.
#: 8.3 MPa is reached at f'c = 68.9 MPa and 100 psi at f'c = 10,000 psi, so
#: below those strengths neither cap binds and nothing changes.
_SQRT_F_C_CAP_SI = 8.3
_SQRT_F_C_CAP_IMPERIAL = 100.0


def sqrt_f_c_for_shear(f_c: float, *, has_min_rebar: bool, is_imperial: bool = False) -> float:
    """sqrt(f'c) as V_c may use it — ACI 318-19 §22.5.3.1 and §22.5.3.2 / CIRSOC 201-25 art. 22.5.3.1 y 22.5.3.2.

    Both codes print the same limit and the same exception. §22.5.3.1: the value
    of sqrt(f'c) used to calculate V_c, V_ci and V_cw for one-way shear shall
    not exceed 8.3 MPa (100 psi) unless 22.5.3.2 allows it. §22.5.3.2 allows it
    "for reinforced or prestressed concrete beams and concrete joist
    construction having minimum web reinforcement in accordance with 9.6.3.4 or
    9.6.4.2". The reason is in the commentary of both books — ACI 318-19
    R22.5.3.1 / CIRSOC 201-25 C 22.5.3.1: there are few tests above 70 MPa, and
    R22.5.3.2 / C 22.5.3.2 add that the minimum transverse reinforcement is what
    offsets the loss of reserve shear strength as f'c grows.

    The limit is on the root, not on f'c: sqrt(f_c) is replaced by 8.3, which is
    not the same as evaluating the expression at f'c = 68.9 MPa, because the
    other f'c-dependent terms of the calling clause keep their own value.

    Args:
        f_c: Specified concrete compressive strength (MPa, or psi).
        has_min_rebar: True when A_v >= A_v,min of Table 9.6.3.4 — mento's name
            for the minimum web reinforcement §22.5.3.2 asks for, and the same
            condition as rows (a)/(b) of Table 22.5.5.1, restricted here to
            beams and joists. True lifts the cap.

    Returns:
        sqrt(f'c), capped at 8.3 (100 in psi) unless the exception applies
        (sqrt(MPa), or sqrt(psi)).

    §22.5.3.2 is written for beams and joists, not for slabs or footings: a
    member that is neither may not lift the cap even if it carries stirrups.
    The caller combines the provided minimum with the member's eligibility.

    Two neighbouring terms are deliberately left uncapped, because neither is
    V_c: the 0.66*sqrt(f'c) of §22.5.1.2 (:func:`shear_stress_capacity_increment`),
    which bounds V_s, and the 0.062*sqrt(f'c) of Table 9.6.3.4
    (:func:`min_shear_reinforcement_ratio`), which sizes A_v,min. Two-way shear
    has its own ceiling, the same 8.3 MPa in §22.6.3.1 of both codes, and it
    belongs to the punching module.
    """
    root = math.sqrt(f_c)
    if has_min_rebar:
        return root
    return min(root, _SQRT_F_C_CAP_IMPERIAL if is_imperial else _SQRT_F_C_CAP_SI)


def concrete_shear_stress(
    f_c: float,
    lambda_factor: float,
    rho_w: float,
    sigma_Nu: float,
    lambda_s: float,
    *,
    has_min_rebar: bool,
    allow_high_strength: bool = True,
    is_imperial: bool = False,
) -> float:
    """Concrete shear stress v_c — ACI 318-19 Table 22.5.5.1 / CIRSOC 201-25 Tabla 22.5.5.1.

    Both codes print the same three expressions and the same two notes; CIRSOC
    labels the (a)/(b) choice "Cualquiera de los dos" where ACI reads "Either of".

    The root is not math.sqrt(f_c) but :func:`sqrt_f_c_for_shear`: §22.5.3.1 of
    both codes caps it at 8.3 MPa (100 psi) for V_c. The exception requires
    both minimum web reinforcement and an eligible member (beam or joist).

    Args:
        f_c: Specified concrete compressive strength (MPa, or psi).
        lambda_factor: Lightweight concrete factor lambda.
        rho_w: Longitudinal tension reinforcement ratio A_s / (b_w*d).
        sigma_Nu: Axial stress term from :func:`axial_stress_influence`.
        lambda_s: Size effect factor from :func:`size_effect_factor`.
        has_min_rebar: True when A_v >= A_v_min, which selects rows (a)/(b) of
            the table; False selects row (c), where the size effect factor
            applies because there are no stirrups to control the crack. The
            A_v,min meant is the one *defined* in Table 9.6.3.4 of both codes
            (ACI 318-19 R22.5.5.1 / CIRSOC 201-25 C 22.5.5.1).
        allow_high_strength: Whether the member is eligible for §22.5.3.2.
            False for slabs and footings, including those with shear reinforcement.

    Returns:
        The shear stress carried by the concrete (MPa, or psi). Note 2 of the
        table in both codes adds that V_c is never taken below zero, which the
        caller applies.
    """
    sqrt_f_c = sqrt_f_c_for_shear(f_c, has_min_rebar=has_min_rebar and allow_high_strength, is_imperial=is_imperial)

    if not has_min_rebar:
        # Table 22.5.5.1(c) / Tabla 22.5.5.1(c)
        coeff = 8 if is_imperial else 0.66
        return coeff * lambda_s * lambda_factor * rho_w ** (1 / 3) * sqrt_f_c + sigma_Nu

    # Rows (a) and (b): the member may take whichever is larger.
    coeff_a = 2 if is_imperial else 0.17
    coeff_b = 8 if is_imperial else 0.66
    return max(
        coeff_a * lambda_factor * sqrt_f_c + sigma_Nu,
        coeff_b * lambda_factor * rho_w ** (1 / 3) * sqrt_f_c + sigma_Nu,
    )


def max_concrete_shear_stress(
    f_c: float,
    lambda_factor: float,
    *,
    has_min_rebar: bool = False,
    allow_high_strength: bool = True,
    is_imperial: bool = False,
) -> float:
    """Upper limit on the concrete shear stress — ACI 318-19 §22.5.5.1.1 / CIRSOC 201-25 §22.5.5.1.1.

    V_c shall not be taken greater than 0.42*lambda*sqrt(f_c)*b_w*d
    (5*lambda*sqrt(f_c)*b_w*d in psi) — the same coefficient in both codes.

    This is still a calculation of V_c, so its root is the one §22.5.3.1 caps;
    see :func:`sqrt_f_c_for_shear`. Capping it lowers the ceiling as well as the
    table value, which is the conservative reading and the one the clause asks
    for: both are V_c.

    Args:
        f_c: Specified concrete compressive strength (MPa, or psi).
        lambda_factor: Lightweight concrete factor lambda.
        has_min_rebar: True when A_v >= A_v,min of Table 9.6.3.4, which lifts
            the §22.5.3.1 cap through §22.5.3.2. Defaults to False, the capped
            reading, so a caller that does not know stays on the safe side.
        allow_high_strength: Whether the member is eligible for §22.5.3.2.
            False for slabs and footings, including those with shear reinforcement.

    Returns:
        The largest v_c the table may produce (MPa, or psi).
    """
    coeff = 5 if is_imperial else 0.42
    return (
        coeff
        * lambda_factor
        * sqrt_f_c_for_shear(f_c, has_min_rebar=has_min_rebar and allow_high_strength, is_imperial=is_imperial)
    )


def shear_stress_capacity_increment(f_c: float, lambda_factor: float, *, is_imperial: bool = False) -> float:
    """Largest stress the stirrups may add to V_c — ACI 318-19 Eq. (22.5.1.2) / CIRSOC 201-25 ec. (22.5.1.2).

    Both codes write it as V_u <= phi*(V_c + 0.66*sqrt(f_c)*b_w*d)
    (8*sqrt(f_c)*b_w*d in psi), with no lambda in the equation: the
    ``lambda_factor`` below is mento's, and it changes nothing while
    lambda = 1, the only value mento supports today.

    Args:
        f_c: Specified concrete compressive strength (MPa, or psi).
        lambda_factor: Lightweight concrete factor lambda.

    Returns:
        The stress that, times A_cv, bounds V_s and therefore caps the total
        shear the section may be designed for (MPa, or psi).
    """
    coeff = 8 if is_imperial else 0.66
    return coeff * lambda_factor * math.sqrt(f_c)


def min_shear_reinforcement_threshold_stress(
    f_c: float, lambda_factor: float, *, coefficient: float | None = None, is_imperial: bool = False
) -> float:
    """Stress below which no shear reinforcement is required — ACI 318-19 §9.6.3.1 / CIRSOC 201-25 §9.6.3.1.

    CIRSOC 201-25 §9.6.3.1 differs: it prints the threshold as
    V_u > phi*lambda*0.085*sqrt(f_c)*b_w*d, against the 0.083 of ACI 318-19
    (SI). The caller supplies the coefficient from the code registry. Without
    one, this ACI equation defaults to 0.083 (1.0 in psi).

    Both codes exempt the beams of their Table 9.6.3.1 (h <= 250 mm among
    them), where A_v,min is required only once V_u > phi*V_c; that exemption is
    the caller's, not this function's.

    Args:
        f_c: Specified concrete compressive strength (MPa, or psi).
        lambda_factor: Lightweight concrete factor lambda.
        coefficient: Code-specific coefficient, in the selected unit system.

    Returns:
        The stress to compare V_u/(phi_v*A_cv) against (MPa, or psi). Below it,
        the clause waives A_v_min only; required shear strength remains a separate check.
    """
    coeff = (1 if is_imperial else 0.083) if coefficient is None else coefficient
    return coeff * lambda_factor * math.sqrt(f_c)


def max_yield_strength_for_shear(f_y: float, *, is_imperial: bool = False) -> float:
    """Yield strength usable for shear reinforcement — ACI 318-19 §22.5.3.3 / CIRSOC 201-25 §22.5.3.3.

    The clause that caps f_y and f_yt for V_s is the same number in both codes,
    but each sends somewhere different for the value. ACI 318-19 §22.5.3.3
    sends to Table 20.2.2.4(a), whose "Shear — stirrups, ties, hoops" row reads
    420 MPa (60,000 psi) for bars and 550 MPa (80,000 psi) for welded deformed
    wire reinforcement. CIRSOC 201-25 §22.5.3.3 sends to §20.2.1.3 instead
    (Tablas 20.2.1 and 20.2.2, the Argentine steels), and its commentary
    C 22.5.3.3 gives the same 420 MPa, for control of diagonal crack width.

    The 420 below is applied to every reinforcement type, which is the
    conservative reading of the ACI table: mento does not model welded deformed
    wire. Two-way shear reaches the same cap through §22.6.3.2 of both codes
    (CIRSOC's C 22.6.3.2 again states 420 MPa).

    Args:
        f_y: Specified yield strength of the reinforcement (MPa, or psi).

    Returns:
        f_yt, capped at 420 MPa / 60,000 psi.
    """
    cap = 60_000.0 if is_imperial else 420.0
    return min(f_y, cap)


def min_shear_reinforcement_ratio(f_c: float, f_yt: float, b_w: float, *, is_imperial: bool = False) -> float:
    """Minimum shear reinforcement A_v,min / s — ACI 318-19 Table 9.6.3.4 / CIRSOC 201-25 Tabla 9.6.3.4.

    Rows (a) and (b), nonprestressed: the same two expressions in both codes.

    Args:
        f_c: Specified concrete compressive strength (MPa, or psi).
        f_yt: Yield strength used for shear, from
            :func:`max_yield_strength_for_shear` (MPa, or psi).
        b_w: Web width (mm, or in).

    Returns:
        Reinforcement area per unit length along the member — mm²/mm, which is
        a length, or in²/in.
    """
    if is_imperial:
        return max(0.75 * math.sqrt(f_c) / f_yt, 50 / f_yt) * b_w
    return max(0.062 * math.sqrt(f_c) / f_yt, 0.35 / f_yt) * b_w


def max_stirrup_spacing(
    V_s_req: float,
    f_c: float,
    A_cv: float,
    d: float,
    cap_low: float,
    cap_high: float,
    *,
    is_imperial: bool = False,
) -> tuple[float, float]:
    """Maximum stirrup spacing along and across — ACI 318-19 Table 9.7.6.2.2 / CIRSOC 201-25 Tabla 9.7.6.2.2.

    Once the shear the stirrups carry passes the table's threshold,
    0.33·√f'c·bw·d (4·√f'c·bw·d in psi), the spacing limits halve, because a
    wider crack needs more legs crossing it. The threshold is on the NOMINAL
    required Vs = (Vu − φVc)/φ, and it carries no λ: the table has none. Both
    codes print the same threshold and the same d/2, d, d/4 and d/2 limits;
    the clause that sends here is §9.7.6.2.2 in both.

    The absolute caps are the one thing the codes sharing this table state
    differently (ACI 318-19: 600/300 mm, 24/12 in.; CIRSOC 201-25: 400/200 mm),
    so they come in as arguments, from the code's registry entry.

    Args:
        V_s_req: Nominal shear the stirrups must carry, (Vu − φVc)/φ (N, or lb).
        f_c: Specified concrete compressive strength (MPa, or psi).
        A_cv: Effective shear area bw·d (mm², or in²).
        d: Effective depth for shear (mm, or in).
        cap_low: Absolute cap while Vs,req is under the threshold (mm, or in).
        cap_high: Absolute cap once Vs,req passes it (mm, or in).

    Returns:
        ``(s_max_l, s_max_w)`` — the limits along the member and across its
        width (mm, or in).
    """
    threshold_coeff = 4 if is_imperial else 0.33

    if V_s_req <= threshold_coeff * math.sqrt(f_c) * A_cv:
        return min(d / 2, cap_low), min(d, cap_low)
    return min(d / 4, cap_high), min(d / 2, cap_high)


def shear_strength_of_reinforcement(A_v: float, f_yt: float, d: float) -> float:
    """Shear carried by the stirrups, A_v*f_yt*d/s — ACI 318-19 Eq. (22.5.8.5.3) / CIRSOC 201-25 ec. (22.5.8.5.3).

    Identical in both codes. The V_n = V_c + V_s it feeds is §22.5.1.1 in both.

    Args:
        A_v: Stirrup area per unit length A_v/s (mm²/mm, or in²/in).
        f_yt: Yield strength used for shear (MPa, or psi).
        d: Effective depth for shear (mm, or in).

    Returns:
        V_s (N, or lb). Same expression in both unit systems.
    """
    return A_v * f_yt * d


def max_stirrup_spacing_for_compression_support(d_b_long: float, d_b_stirrup: float, least_dimension: float) -> float:
    """Spacing cap of the stirrups that support compression bars — ACI 318-19 §9.7.6.4.3 / CIRSOC 201-25 §9.7.6.4.3.

    The least of (a) 16 d_b of the longitudinal reinforcement, (b) 48 d_b of
    the transverse reinforcement and (c) the least dimension of the beam: the
    same three items in both codes ("16db de barra longitudinal, 48dbe de
    barra o alambre transversal, la menor dimensión de la viga", CIRSOC
    201-25 Cap. 9 p. 179). §9.7.6.4.1 of both asks for it throughout the
    distance where longitudinal compression reinforcement is required, so it
    binds only a section whose flexure relies on compression steel; the
    Table 9.7.6.2.2 limits of :func:`max_stirrup_spacing` apply beside it.

    Args:
        d_b_long: Diameter of the compression bar the stirrup supports (mm, or in).
        d_b_stirrup: Diameter of the stirrup (mm, or in).
        least_dimension: Least dimension of the beam, min(b, h) (mm, or in).

    Returns:
        The spacing cap (mm, or in). Same expression in both unit systems.
    """
    return min(16 * d_b_long, 48 * d_b_stirrup, least_dimension)


#: ACI 318-19 §9.7.6.4.2 in the bars of each edition, as (largest longitudinal
#: bar the smaller stirrup serves, that stirrup, the stirrup above it). SI:
#: No. 32 (32.3 mm) -> No. 10 (9.5 mm), else No. 13 (12.7 mm). in-lb: No. 10
#: (1.27 in) -> No. 3 (0.375 in), else No. 4 (0.5 in).
_ACI_COMPRESSION_SUPPORT_STIRRUP = {False: (32.3, 9.5, 12.7), True: (1.27, 0.375, 0.5)}

#: CIRSOC 201-25 Tabla 9.7.6.4.2, as (largest longitudinal bar of the row,
#: stirrup), in mm; the row past the last is 12 mm.
_CIRSOC_COMPRESSION_SUPPORT_STIRRUP = ((16.0, 6.0), (25.0, 8.0), (32.0, 10.0))


def min_stirrup_diameter_for_compression_support(d_b_long: float, *, is_imperial: bool = False) -> float:
    """Smallest stirrup that may laterally support a compression bar — ACI 318-19 §9.7.6.4.2.

    (a) No. 10 for longitudinal bars No. 32 and smaller, (b) No. 13 for
    No. 36 and larger and for bundled bars; the in-lb edition prints No. 3
    for No. 10 and smaller and No. 4 for No. 11 and larger. Read on the
    nominal diameters: 9.5 mm (0.375 in) up to a 32.3 mm (1.27 in) bar,
    12.7 mm (0.5 in) past it. Bundled bars are not modelled. CIRSOC 201-25
    §9.7.6.4.2 grades the minimum with its Tabla 9.7.6.4.2 instead, so it
    has its own function.

    Args:
        d_b_long: Diameter of the compression bar (mm, or in).

    Returns:
        The smallest stirrup diameter (mm, or in).
    """
    largest_small, stirrup_small, stirrup_large = _ACI_COMPRESSION_SUPPORT_STIRRUP[is_imperial]
    return stirrup_small if d_b_long <= largest_small else stirrup_large


def min_stirrup_diameter_for_compression_support_cirsoc(d_b_long: float) -> float:
    """Smallest stirrup that may support a compression bar — CIRSOC 201-25 §9.7.6.4.2, Tabla 9.7.6.4.2.

    Read off the printed table (Cap. 9 p. 178): 6 mm for db <= 16 mm, 8 mm
    for 16 < db <= 25 mm, 10 mm for 25 < db <= 32 mm, 12 mm for db > 32 mm
    and for bundled bars. Metric only, as the code is; bundled bars are not
    modelled. ACI 318-19 §9.7.6.4.2 has two steps in place of four:
    :func:`min_stirrup_diameter_for_compression_support`.

    Args:
        d_b_long: Diameter of the compression bar (mm).

    Returns:
        The smallest stirrup diameter (mm).
    """
    for largest, stirrup in _CIRSOC_COMPRESSION_SUPPORT_STIRRUP:
        if d_b_long <= largest:
            return stirrup
    return 12.0
