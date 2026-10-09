"""Punching shear equations of EN 1992-1-1:2004 §6.4.

**Not implemented yet.** This module is the shape of Phase 5, not its content:
every function below is the signature its clause asks for, with the units each
argument is expected in, and a body that raises. The formulas are being
recreated from a validated Calcpad sheet and land one at a time, each with the
worked example that checks it.

Per ADR-0005 these are free functions over plain floats, in N, mm, MPa
(= N/mm²) and N·mm. Unlike ACI 318-19, EN publishes one set of coefficients, so
no function here takes an ``imperial`` flag.

Geometry — where the control perimeter runs, how long it is, and what an
opening or a free edge removes from it — is not here; it belongs to the element
(see :mod:`mento.punching`), which hands this module lengths already computed.

The one thing to carry over from Phase 1: ``v_Rd,c`` reads ρ_l, so a slab whose
reinforcement was never declared cannot be checked to this code. The checker
refuses rather than passing ρ = 0, which would collapse the resistance to
``v_min`` and read as a pass.
"""

from __future__ import annotations

_NOT_YET = "EN 1992-1-1 punching equations are not implemented yet (Phase 5 of docs/architecture/punching-roadmap.md)."


def control_perimeter_offset(d: float) -> float:
    """Distance from the column face to the basic control perimeter u_1, EN 1992-1-1 §6.4.2(1).

    Args:
        d: mean effective depth [mm].

    Returns:
        The offset [mm]. Twice the effective depth, against ACI's d/2.
    """
    raise NotImplementedError(_NOT_YET)


def mean_effective_depth(d_y: float, d_z: float) -> float:
    """d_eff, the mean of the two orthogonal effective depths, EN 1992-1-1 §6.4.2(1), Eq. (6.32).

    Args:
        d_y: effective depth of the reinforcement in y [mm].
        d_z: effective depth of the reinforcement in z [mm].

    Returns:
        d_eff [mm].
    """
    raise NotImplementedError(_NOT_YET)


def size_effect_factor(d: float) -> float:
    """k, the size effect factor, EN 1992-1-1 §6.4.4(1).

    Args:
        d: mean effective depth [mm].

    Returns:
        k, dimensionless and not greater than 2.0.
    """
    raise NotImplementedError(_NOT_YET)


def reinforcement_ratio(rho_y: float, rho_z: float) -> float:
    """ρ_l, the bonded tension reinforcement ratio, EN 1992-1-1 §6.4.4(1).

    The geometric mean of the two orthogonal ratios, each measured over a slab
    width of the column width plus 3·d each side, and capped at 0.02.

    Args:
        rho_y: reinforcement ratio in y, dimensionless.
        rho_z: reinforcement ratio in z, dimensionless.

    Returns:
        ρ_l, dimensionless.
    """
    raise NotImplementedError(_NOT_YET)


def min_shear_stress(k: float, f_ck: float) -> float:
    """v_min, the floor under the concrete resistance, EN 1992-1-1 §6.4.4(1).

    Args:
        k: the size effect factor of :func:`size_effect_factor`.
        f_ck: characteristic cylinder strength [MPa].

    Returns:
        v_min [MPa].
    """
    raise NotImplementedError(_NOT_YET)


def concrete_shear_stress(
    k: float,
    rho_l: float,
    f_ck: float,
    sigma_cp: float = 0.0,
    gamma_c: float = 1.5,
) -> float:
    """v_Rd,c, the punching resistance without reinforcement, EN 1992-1-1 §6.4.4(1), Eq. (6.47).

    Not less than ``v_min + k_1·σ_cp``; see :func:`min_shear_stress`.

    Args:
        k: the size effect factor of :func:`size_effect_factor`.
        rho_l: the reinforcement ratio of :func:`reinforcement_ratio`.
        f_ck: characteristic cylinder strength [MPa].
        sigma_cp: mean concrete normal stress from prestress or axial load [MPa].
        gamma_c: partial factor for concrete, dimensionless.

    Returns:
        v_Rd,c [MPa].
    """
    raise NotImplementedError(_NOT_YET)


def eccentricity_factor(
    position: str,
    M_Ed_y: float,
    M_Ed_z: float,
    V_Ed: float,
    u_1: float,
    W_1_y: float,
    W_1_z: float,
) -> float:
    """β, the factor for eccentric load transfer, EN 1992-1-1 §6.4.3, eqs. (6.39)–(6.46).

    The expression differs with the column's position — internal, edge or corner
    — which is why the position is an argument rather than something the caller
    branches on.

    Args:
        position: ``"interior"``, ``"edge"`` or ``"corner"``.
        M_Ed_y: design moment transferred about y [N·mm].
        M_Ed_z: design moment transferred about z [N·mm].
        V_Ed: design shear transferred to the slab [N].
        u_1: length of the basic control perimeter [mm].
        W_1_y: the perimeter's distribution modulus for the moment about y [mm²].
        W_1_z: the same, about z [mm²].

    Returns:
        β, dimensionless and not less than 1.0.
    """
    raise NotImplementedError(_NOT_YET)


def design_shear_stress(V_Ed: float, beta: float, u: float, d: float) -> float:
    """v_Ed, the design shear stress on a perimeter, EN 1992-1-1 §6.4.3(3), Eq. (6.38).

    Args:
        V_Ed: design shear transferred to the slab [N] — the ``V_z`` of the
            load combination, see ``docs/source/user_guide/local_axes.rst``.
        beta: the eccentricity factor of :func:`eccentricity_factor`.
        u: length of the perimeter being checked [mm].
        d: mean effective depth [mm].

    Returns:
        v_Ed [MPa].
    """
    raise NotImplementedError(_NOT_YET)


def max_shear_stress(f_ck: float, gamma_c: float = 1.5) -> float:
    """v_Rd,max, the crushing limit at the column perimeter u_0, EN 1992-1-1 §6.4.5(3).

    Args:
        f_ck: characteristic cylinder strength [MPa].
        gamma_c: partial factor for concrete, dimensionless.

    Returns:
        v_Rd,max [MPa].
    """
    raise NotImplementedError(_NOT_YET)
