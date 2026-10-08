"""Bar selection for the distributed mesh of a structural wall, shared by the codes.

A design code decides what one direction of the mesh has to provide -- a
reinforcement ratio and a largest spacing -- and which bars it may be built
from. Turning that into a bar and a spacing is the same search whatever the
code, so it lives here once, the way :mod:`mento.codes.flexure_design` holds
the flexure engine the beam codes share. Private: an element reaches it only
through a code's ``design_shear_wall`` hook.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from mento.units import Quantity, cm, inch

if TYPE_CHECKING:
    from mento.shear_wall import ShearWall


def select_wall_mesh(
    wall: "ShearWall",
    rho_req: float,
    s_max: Quantity,
    bar_list: list,
    cap: Quantity,
) -> tuple:
    """
    Pick (d_b, s) for one wall mesh direction.

    Two-tier search:
      1. Apply the 80/20 scoring functional to the bars up to ``cap``, the
         crack-control cap. Return the best-scoring capped candidate.
      2. Only if no capped bar yields a valid candidate, retry on the full
         ``bar_list``.

    The cap, the tiering and the spacing grid are mento design criteria: no
    code this serves constrains the bar diameter of a wall mesh. ACI 318-19
    §11.6/§11.7 and CIRSOC 201-25 §11.6/§11.7 limit ρ and s; EN 1992-1-1
    §9.6.2/§9.6.3 limit the areas and s. The code limits enter through
    ``rho_req`` and ``s_max``, which the caller has already derived, and the
    catalogue through ``bar_list``.

    Scoring functional (per candidate (d_b, s)):
        rho_provided   = n_curtains · A_b / (t · s)   (mesh on both faces, E.F.)
        ratio_score    = rho_req / rho_provided       ∈ (0, 1]  (minimise steel)
        diameter_score = d_min / d_b                  ∈ (0, 1]  (prefer small bar)
        score          = 0.80 * ratio_score + 0.20 * diameter_score
    `d_min` is the smallest bar in the tier being scored. The functional thus
    prefers the lowest reinforcement ratio (least steel) and, for near-equal
    ratios, the smaller diameter. Ties are broken toward the smaller diameter.

    Spacing grid: 2.5 cm multiples floored to whole cm (metric) / integer
    inches (imperial), with a practical floor of 5 cm / 2 in.
    """
    t = wall.thickness
    n_c = wall._n_curtains  # mesh on both faces (E.F.)
    metric = wall.concrete.unit_system == "metric"
    step = 2.5 * cm if metric else 1.0 * inch
    s_floor = 5.0 * cm if metric else 2.0 * inch
    unit = 1 * cm if metric else 1 * inch

    # Build the spacing grid up to s_max
    grid: list = []
    k = 2
    while True:
        s = math.floor((k * step).to(unit.units).magnitude) * unit
        if s > s_max:
            break
        if s >= s_floor:
            grid.append(s)
        k += 1

    def _best(candidate_bars: list[Quantity]) -> tuple[tuple[float, float], Quantity, Quantity] | None:
        best = None  # ((score, -d_b_mm), d_b, s)
        d_min = min(candidate_bars)  # smallest bar in this tier
        for d_b in candidate_bars:
            A_b = math.pi / 4 * d_b**2
            feasible = [s for s in grid if (n_c * A_b / (t * s)).to("").magnitude >= rho_req]
            if not feasible:
                continue
            s = min(max(feasible), s_max)
            rho_prov = (n_c * A_b / (t * s)).to("").magnitude
            ratio_score = rho_req / rho_prov
            diameter_score = (d_min / d_b).to("").magnitude
            score = 0.80 * ratio_score + 0.20 * diameter_score
            key = (score, -d_b.to("mm").magnitude)  # tie-break: smaller bar
            if best is None or key > best[0]:
                best = (key, d_b, s)
        return best

    capped = [b for b in bar_list if b <= cap]
    result = (_best(capped) if capped else None) or _best(bar_list)  # tier 1, then fallback
    if result is None:
        raise ValueError(
            f"No standard bar can satisfy ρ ≥ {rho_req:.5f} with spacing in [{s_floor:.0f~P}, {s_max:.0f~P}]."
        )
    return result[1], result[2]
