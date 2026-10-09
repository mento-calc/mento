"""Two-way (punching) shear equations of ACI 318-19 and CIRSOC 201-25.

CIRSOC 201-25 reprints Chapter 22.6 and §8.4 under the same numbering, and the
two codes share the punching checker. One thing they print differently reaches
this module, and only one: the (b) and (c) expressions of Table 22.6.5.2, noted
in :func:`concrete_shear_stress`. When that table is implemented its
coefficients have to arrive as data from the code's registry entry, the way
``stirrup_spacing_caps`` already does — never from a comparison against a
design-code string, which ``tests/test_architecture_boundaries.py`` forbids.

**Not implemented yet.** This module is the shape of Phase 2, not its content:
every function below is the signature its clause asks for, with the units each
argument is expected in, and a body that raises. The formulas are being
recreated from a validated Calcpad sheet and land one at a time, each with the
worked example that checks it.

Per ADR-0005 these are free functions over plain floats. Two unit systems, one
per set of published coefficients:

- metric — N, mm, MPa (= N/mm²), N·mm
- imperial — lb, in, psi, lb·in

ACI publishes separately rounded coefficients for the two (``0.33√f'c`` in MPa
against ``4√f'c`` in psi), so a function whose coefficients differ takes an
``imperial: bool`` and works in either. The unit *system* is a parameter; the
units within it are fixed and stated per argument.

Geometry — where the critical section runs, how long it is, and where its
centroid sits once an opening or a free edge has clipped it — is not here. It
belongs to the element, which hands this module a length and a section modulus
already computed; see :mod:`mento.punching`.
"""

from __future__ import annotations

_NOT_YET = "ACI 318-19 punching equations are not implemented yet (Phase 2 of docs/architecture/punching-roadmap.md)."


def critical_section_offset(d: float) -> float:
    """Distance from the column face to the critical section, ACI 318-19 §22.6.4.1 / CIRSOC 201-25 §22.6.4.1.

    Identical in both codes: the perimeter b_0 is placed so that it is a minimum
    but need not come closer than d/2 to the column, the loaded area, or a
    change of thickness. §22.6.4.1.1 (straight sides for a square or rectangular
    column) and §22.6.4.1.2 (a circular column taken as an equivalent square)
    are also the same in both.

    Args:
        d: effective depth [mm | in].

    Returns:
        The offset [mm | in]. Half the effective depth, in either unit system.
    """
    raise NotImplementedError(_NOT_YET)


def size_effect_factor(d: float, imperial: bool = False) -> float:
    """λ_s, the size effect factor, ACI 318-19 Eq. (22.5.5.1.3) / CIRSOC 201-25 ec. (22.5.5.1.3).

    The same factor one-way shear uses, reached from note [i] of Table 22.6.5.2
    in both codes, and identical in both — cap included. One-way shear already
    implements it in
    :func:`mento.codes.aci_318_19.equations.shear.size_effect_factor`; this stub
    should reuse it rather than grow a second copy.

    Not covered here: §22.6.6.2 of both codes *permits* λ_s = 1.0 when the slab
    carries stirrups or smooth headed studs meeting its conditions (a) or (b),
    the stirrup one being A_v/s >= 0.17*sqrt(f_c)*b_0/f_yt.

    Args:
        d: effective depth [mm | in].
        imperial: work in (lb, in, psi) instead of (N, mm, MPa).

    Returns:
        λ_s, dimensionless and not greater than 1.0.
    """
    raise NotImplementedError(_NOT_YET)


def location_factor(position: str) -> float:
    """α_s, the factor for the column's position in the slab, ACI 318-19 §22.6.5.3 / CIRSOC 201-25 §22.6.5.3.

    40 for interior columns, 30 for edge columns and 20 for corner columns — the
    same three numbers in both codes. ACI 318-19 R22.6.5.3 and CIRSOC 201-25
    C 22.6.5.3 both add what the labels mean: a critical section with the slab
    continuous on four, three and two sides respectively, which is a property of
    the geometry rather than a free choice.

    Args:
        position: ``"interior"``, ``"edge"`` or ``"corner"``.

    Returns:
        α_s, dimensionless.
    """
    raise NotImplementedError(_NOT_YET)


def concrete_shear_stress(
    f_c: float,
    beta: float,
    alpha_s: float,
    d: float,
    b_0: float,
    lambda_s: float,
    lambda_factor: float = 1.0,
    imperial: bool = False,
) -> float:
    """v_c, the two-way concrete shear stress, ACI 318-19 Table 22.6.5.2 / CIRSOC 201-25 Tabla 22.6.5.2.

    The least of the three expressions in the table governs. Row (a) is
    ``0.33*λ_s*λ*sqrt(f_c)`` (``4*λ_s*λ*sqrt(f_c)`` in psi) in both codes.

    CIRSOC 201-25 Tabla 22.6.5.2 differs in how it prints (b) and (c). It keeps
    the factored form of the in-lb edition, ``0.17*(1 + 2/β)*λ_s*λ*sqrt(f_c)``
    and ``0.083*(2 + α_s*d/b_0)*λ_s*λ*sqrt(f_c)``, where ACI 318-19 SI rounds
    the two terms separately into ``(0.17 + 0.33/β)*λ_s*λ*sqrt(f_c)`` and
    ``(0.17 + 0.083*α_s*d/b_0)*λ_s*λ*sqrt(f_c)``. (The ACI in-lb edition prints
    ``(2 + 4/β)`` and ``(2 + α_s*d/b_0)``, which is what CIRSOC converted.) The
    gap is small — 0.34/β against 0.33/β, and 0.166 against 0.17 — but it is
    real, so these coefficients are the per-code datum this module needs from
    the registry.

    The datum has to be scoped to Table 22.6.5.2 alone, not to some general "new
    form or old form" flag, because ACI 318-19 SI is not consistent with itself:
    its own Table 22.6.6.1 prints the factored ``0.17*(1 + 2/β)`` and
    ``0.083*(2 + α_s*d/b_0)``, exactly as CIRSOC 201-25 does in both tables. So
    Table 22.6.6.1 is identical in the two codes and needs no datum at all.

    Not applied by the signature: §22.6.3.1 of both codes limits sqrt(f_c) to
    8.3 MPa (100 psi) for two-way v_c, so the implementation takes
    ``min(sqrt(f_c), 8.3)`` — in this table and in Table 22.6.6.1 alike.

    Args:
        f_c: concrete compressive strength [MPa | psi].
        beta: ratio of the long to the short side of the column, dimensionless.
        alpha_s: the location factor of :func:`location_factor`.
        d: effective depth [mm | in].
        b_0: length of the critical perimeter [mm | in].
        lambda_s: the size effect factor of :func:`size_effect_factor`.
        lambda_factor: λ, the lightweight concrete factor of §19.2.4 in both
            codes (§19.2.4.3: λ = 1.0 for normalweight concrete, the only case
            mento supports).
        imperial: work in (lb, in, psi) instead of (N, mm, MPa).

    Returns:
        v_c [MPa | psi].
    """
    raise NotImplementedError(_NOT_YET)


def moment_fraction_by_flexure(b_1: float, b_2: float) -> float:
    """γ_f, the moment fraction carried in flexure, ACI 318-19 Eq. (8.4.2.2.2) / CIRSOC 201-25 ec. (8.4.2.2.2).

    ``γ_f = 1 / (1 + (2/3)*sqrt(b_1/b_2))``, the same in both codes. The clause
    is §8.4.2.2.2.

    Two neighbouring clauses, also identical in both codes, are not covered
    here: Table 8.4.2.2.3 gives the effective slab width b_slab that γ_f*M_sc has
    to be resisted within, and Table 8.4.2.2.4 allows γ_f to be increased in the
    cases it lists, with γ_v following from the modified value.

    Args:
        b_1: width of the critical section measured in the direction of the span
            the moment acts in [mm | in].
        b_2: width of the critical section measured perpendicular to it [mm | in].

    Returns:
        γ_f, dimensionless.
    """
    raise NotImplementedError(_NOT_YET)


def moment_fraction_by_shear(gamma_f: float) -> float:
    """γ_v, the moment fraction carried in shear, ACI 318-19 Eq. (8.4.4.2.2) / CIRSOC 201-25 ec. (8.4.4.2.2).

    ``γ_v = 1 − γ_f``, identical in both codes. Both apply it at the centroid of
    the critical section, which is what makes the lever arms of
    :func:`shear_stress` centroidal rather than measured from the column.

    Args:
        gamma_f: the flexural fraction of :func:`moment_fraction_by_flexure`.

    Returns:
        γ_v = 1 − γ_f, dimensionless.
    """
    raise NotImplementedError(_NOT_YET)


def shear_stress(
    V_u: float,
    b_0: float,
    d: float,
    gamma_v_x: float,
    M_sc_x: float,
    c_x: float,
    J_c_x: float,
    gamma_v_y: float,
    M_sc_y: float,
    c_y: float,
    J_c_y: float,
) -> float:
    """v_u, the factored shear stress at the critical point, ACI 318-19 §8.4.4.2.3 / CIRSOC 201-25 §8.4.4.2.3.

    The direct stress plus the contribution of each unbalanced moment, evaluated
    at the point of the critical section farthest from its centroid.

    The clause itself only says, in both codes, that the stress varies linearly
    about the centroid; the closed form lives in the commentary — ACI 318-19
    R8.4.4.2.3 and CIRSOC 201-25 C 8.4.4.2.3 — as
    ``v_u,AB = v_uv + γ_v*M_sc*c_AB/J_c`` and ``v_u,CD = v_uv − γ_v*M_sc*c_CD/J_c``.

    CIRSOC 201-25 C 8.4.4.2.3 differs, and wrongly: it prints a minus sign in
    *both* expressions, so its v_u,AB contradicts its own Figura C 8.4.4.2.3,
    where AB is the face the moment adds to. Follow the ACI sign; do not copy
    the CIRSOC one. J_c for an interior column is given in the same commentary
    of both codes.

    Args:
        V_u: factored shear transferred to the slab [N | lb] — the ``V_z`` of
            the load combination, see ``docs/source/user_guide/local_axes.rst``.
            Referred, like M_sc, to the centroidal axis c-c of the critical
            section.
        b_0: length of the critical perimeter [mm | in].
        d: effective depth [mm | in].
        gamma_v_x: γ_v for the moment about x, from :func:`moment_fraction_by_shear`.
        M_sc_x: unbalanced moment transferred about x [N·mm | lb·in].
        c_x: distance from the centroid of the critical section to the point
            being checked, measured along x [mm | in].
        J_c_x: the section property analogous to a polar moment of inertia,
            about x [mm⁴ | in⁴].
        gamma_v_y: γ_v for the moment about y.
        M_sc_y: unbalanced moment transferred about y [N·mm | lb·in].
        c_y: distance to the point being checked, along y [mm | in].
        J_c_y: the section property about y [mm⁴ | in⁴].

    Returns:
        v_u [MPa | psi].
    """
    raise NotImplementedError(_NOT_YET)
