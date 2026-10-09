"""Structural wall equations — EN 1992-1-1:2004, §6.2.3 and §9.6.

What a wall adds to the shear equations of :mod:`.shear`: the coefficient on
the compression chord the strut of Eq. (6.9) leans on, and the detailing rules
of §9.6 for the distributed reinforcement. The resistances themselves --
Eqs. (6.2.a), (6.2.b), (6.8) and (6.9) -- are the beam's, with the horizontal
bars acting as shear reinforcement at alpha = 90 deg, and are not repeated
here.

Pure functions of floats; see the package docstring for the unit convention.
Areas per unit length of wall are mm²/mm. The ratios below are the values
EN 1992-1-1 recommends; a National Annex may change them.

Scope: §9.6 covers walls whose length is at least four times their thickness
(§5.3.1(7)) and in which the reinforcement is taken into account in the
strength analysis (§9.6.1(1)). Seismic walls are EN 1998-1 and are not
covered.
"""

from __future__ import annotations

__all__ = [
    "MIN_LENGTH_TO_THICKNESS",
    "MIN_VERTICAL_RATIO",
    "MAX_VERTICAL_RATIO",
    "MIN_HORIZONTAL_RATIO",
    "HORIZONTAL_TO_VERTICAL",
    "MAX_HORIZONTAL_SPACING",
    "compression_chord_coefficient",
    "min_vertical_reinforcement",
    "max_vertical_reinforcement",
    "min_horizontal_reinforcement",
    "max_vertical_spacing",
]

#: §5.3.1(7): a wall is a member whose length is at least four times its
#: thickness; a shorter one is a column, detailed by §9.5 instead.
MIN_LENGTH_TO_THICKNESS = 4.0

#: §9.6.2(1): the vertical reinforcement lies between A_s,vmin = 0.002 A_c and
#: A_s,vmax = 0.04 A_c (recommended values; 0.04 outside lap locations).
MIN_VERTICAL_RATIO = 0.002
MAX_VERTICAL_RATIO = 0.04

#: §9.6.3(1): A_s,hmin is 25 % of the vertical reinforcement or 0.001 A_c,
#: whichever is greater (recommended values).
MIN_HORIZONTAL_RATIO = 0.001
HORIZONTAL_TO_VERTICAL = 0.25

#: §9.6.3(2): the spacing between two adjacent horizontal bars, in mm.
MAX_HORIZONTAL_SPACING = 400.0


def compression_chord_coefficient(sigma_c0: float, f_cd: float) -> float:
    """alpha_cw of Eq. (6.9), as mento reads it for a wall — EN 1992-1-1 §6.2.3(3), Note 3.

    The Note recommends 1 for non-prestressed structures, and for a member
    under axial compression (1 + sigma_cp/f_cd) up to 0.25 f_cd, 1.25 up to
    0.5 f_cd, and 2.5 (1 - sigma_cp/f_cd) up to f_cd. A wall carries the
    compression of the storeys above without being prestressed, so mento
    keeps the branch that lowers the strut and drops the two that raise it:

        alpha_cw = min(1, 2.5 (1 - sigma_c0/f_cd)), floored at 0.

    That is 1 for any wall under half of f_cd -- every ordinary wall -- and
    the reduction where the chord is nearly crushed by the axial load alone.
    A conservative reading, not the clause's own values.

    Args:
        sigma_c0: Mean axial stress N_Ed/A_c, positive in compression (MPa).
            Not capped at 0.2 f_cd: that cap belongs to sigma_cp of §6.2.2(1).
        f_cd: Design compressive strength of the concrete (MPa).

    Returns:
        alpha_cw, between 0 and 1.
    """
    return max(min(1.0, 2.5 * (1 - sigma_c0 / f_cd)), 0.0)


def min_vertical_reinforcement(t: float) -> float:
    """A_s,vmin per unit length of wall — EN 1992-1-1 §9.6.2(1).

    Args:
        t: Wall thickness (mm).

    Returns:
        0.002 * t (mm²/mm), both faces together. §9.6.2(2) puts half of it on
        each face where it governs.
    """
    return MIN_VERTICAL_RATIO * t


def max_vertical_reinforcement(t: float) -> float:
    """A_s,vmax per unit length of wall — EN 1992-1-1 §9.6.2(1).

    Args:
        t: Wall thickness (mm).

    Returns:
        0.04 * t (mm²/mm), both faces together, outside lap locations.
    """
    return MAX_VERTICAL_RATIO * t


def min_horizontal_reinforcement(A_sv: float, t: float) -> float:
    """A_s,hmin per unit height of wall — EN 1992-1-1 §9.6.3(1).

    Written on the vertical reinforcement the wall carries, not on its
    minimum: a heavier vertical mesh asks for a heavier horizontal one.

    Args:
        A_sv: Vertical reinforcement per unit length of wall, both faces (mm²/mm).
        t: Wall thickness (mm).

    Returns:
        max(0.25 * A_sv, 0.001 * t) (mm²/mm), both faces together.
    """
    return max(HORIZONTAL_TO_VERTICAL * A_sv, MIN_HORIZONTAL_RATIO * t)


def max_vertical_spacing(t: float) -> float:
    """Largest distance between two adjacent vertical bars — EN 1992-1-1 §9.6.2(3).

    Args:
        t: Wall thickness (mm).

    Returns:
        min(3 * t, 400) (mm).
    """
    return min(3 * t, 400.0)
