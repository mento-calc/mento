"""ASTM bar sizes: the number a US drawing calls a bar by, and back.

A US customary report writes a bar as its ASTM A615 size, ``#6``, not as its
diameter, the way a metric one writes ``Ø16``. The sizes are the imperial bar
catalogue :class:`mento.rebar.Rebar` designs with, so the table lives here once,
in a module that depends on nothing but the units: the rebar search, the report
tables, the drawings and mento-web all read the same one.

Public through :mod:`mento.rebar` and the package root::

    from mento import bar_designation, bar_diameter
    bar_designation(0.75 * inch)   # "#6"
    bar_diameter(6)                # 0.75 inch
"""

from __future__ import annotations

import math
from typing import Dict

from mento.units import Quantity, inch

#: ASTM A615 bar size -> nominal diameter. #3 to #8 are n/8 in; the larger
#: sizes are the diameters of the round bar whose area is a whole square inch
#: figure, as the standard lists them.
ASTM_BAR_DIAMETERS: Dict[int, Quantity] = {
    3: 3 * inch / 8,
    4: 4 * inch / 8,
    5: 5 * inch / 8,
    6: 6 * inch / 8,
    7: 7 * inch / 8,
    8: 8 * inch / 8,
    9: 1.128 * inch,
    10: 1.27 * inch,
    11: 1.41 * inch,
    14: 1.693 * inch,
}

# Half a thousandth of an inch: far below the gap between two sizes (0.125 in),
# far above what a diameter picks up converted from millimetres and back.
_TOLERANCE_IN = 5e-4


def bar_designation(d_b: Quantity) -> str:
    """The ASTM size of a bar, ``"#6"``; a diameter that is no ASTM bar as ``Ø0.70"``.

    Never raises for a length: a bar entered by hand at a diameter the standard
    does not list is still written, by its diameter in inches, so a report shows
    what was placed rather than failing on it.
    """
    inches = float(d_b.to(inch).magnitude)
    for number, diameter in ASTM_BAR_DIAMETERS.items():
        if math.isclose(inches, float(diameter.magnitude), abs_tol=_TOLERANCE_IN):
            return f"#{number}"
    return f'Ø{inches:.2f}"'


def bar_diameter(number: int) -> Quantity:
    """The nominal diameter of ASTM bar ``#number``: ``bar_diameter(6)`` is 0.75 in.

    Raises:
        ValueError: if ``number`` is not an ASTM A615 size.
    """
    try:
        return ASTM_BAR_DIAMETERS[number]
    except KeyError:
        sizes = ", ".join(f"#{n}" for n in ASTM_BAR_DIAMETERS)
        raise ValueError(f"#{number} is not an ASTM A615 bar size. Sizes: {sizes}.") from None


def is_us_customary(length: Quantity) -> bool:
    """Whether a length the section stored for display is in inches.

    The public result dataclasses carry no unit system of their own; their
    lengths are in the display units of the section they came from, so the
    unit is what tells a ``RebarLayer`` whether it is a ``#6`` or a ``Ø16``.
    """
    return bool(length.units == inch)
