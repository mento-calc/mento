"""A supported cage, without crediting mounting steel in the resistance.

The calculation geometry stays available as ``section_geometry``. Detailing
keeps its stirrup legs and the resistant bars' counts, sizes and vertical
coordinates. Only their horizontal positions change. A separate collection
records any supplementary mounting bars, including a missing upper face.

A cage that cannot accommodate its bars is rejected, rather than drawn with
unsupported corners or overlapping bars. This checks a cross-section layout,
not development lengths, hooks, seismic detailing or a bar bending schedule.

Crack-control centre-spacing limits come from the registered code (ACI 318-19
/ CIRSOC 201-25 §24.3.2, Table 24.3.2); the positioning search and mounting-bar
diameter are Mento choices. Rounded corners use the registered code mandrel rule
documented in SectionGeometry, with its diameter and code limits.
"""

from __future__ import annotations

import math
from dataclasses import replace
from typing import TYPE_CHECKING

from mento.codes.registry import design_code
from mento.design_results import DesignNotRunError
from mento.section_geometry import BarPosition, SectionGeometry, build_section_geometry
from mento.units import Quantity

if TYPE_CHECKING:
    from mento.beam import RectangularBeam


class CageDetailingError(ValueError):
    """The given bars and stirrups cannot form the supported layout."""

    def __init__(self, message: str, *, reason: str = "layout") -> None:
        super().__init__(message)
        self.reason = reason


def _mm(value: Quantity) -> float:
    return float(value.to("mm").magnitude)


def _supported_layer(
    row: tuple[BarPosition, ...],
    corners: list[tuple[float, int]],
    mounting: BarPosition,
    clear: float,
    max_gap: float,
    d_st: float,
    bend_radius: float,
) -> tuple[list[BarPosition], list[BarPosition]]:
    """Place an ordered row at the cage corners, spreading spare bars between them.

    With enough resistant bars, a small dynamic program chooses which ones
    support the corners. Each interval must fit the complete bar chain, with
    its minimum clear distances and maximum centre distance. With fewer bars,
    mounting bars fill the remaining corners. A lone resistant bar stays at
    mid-width, between the mounting bars.
    """
    n, count = len(row), len(corners)

    def x_at(corner: int, bar: BarPosition) -> float:
        leg, side = corners[corner]
        # Tangent to the horizontal branch and clear of its rounded bend.
        return leg + side * max(bend_radius, (d_st + _mm(bar.d_b)) / 2)

    def steps(items: list[BarPosition]) -> list[float]:
        return [(_mm(a.d_b) + _mm(b.d_b)) / 2 + clear for a, b in zip(items, items[1:])]

    def fits(items: list[BarPosition], span: float) -> bool:
        distances = steps(items)
        return (
            all(distance <= max_gap + 1e-8 for distance in distances)
            and sum(distances) <= span + 1e-8
            and span <= len(distances) * max_gap + 1e-8
        )

    assigned: dict[int, int] = {}
    if n >= count:
        # (corner, row index) -> (cost, preceding row index).
        states: dict[tuple[int, int], tuple[float, int]] = {(0, 0): (0.0, -1)}
        for corner in range(1, count):
            candidates = [n - 1] if corner == count - 1 else range(corner, n - (count - corner - 1))
            for index in candidates:
                best = (math.inf, -1)
                for previous in range(corner - 1, index):
                    if (corner - 1, previous) not in states:
                        continue
                    span = x_at(corner, row[index]) - x_at(corner - 1, row[previous])
                    if not fits(list(row[previous : index + 1]), span):
                        continue
                    cost = states[corner - 1, previous][0] + (x_at(corner, row[index]) - _mm(row[index].x)) ** 2
                    if cost < best[0]:
                        best = cost, previous
                if best[1] >= 0:
                    states[corner, index] = best
        if (count - 1, n - 1) not in states:
            raise CageDetailingError(
                "The resistant bars cannot fit between the stirrup corners with the required spacing."
            )
        index = n - 1
        for corner in reversed(range(count)):
            assigned[corner] = index
            index = states[corner, index][1]
    elif n >= 2:
        assigned = {round(index * (count - 1) / (n - 1)): index for index in range(n)}

    # An ordered chain with a fixed bar at every corner.
    chain: list[tuple[BarPosition, bool]] = []
    fixed: list[tuple[int, float]] = []
    for corner in range(count):
        row_index = assigned.get(corner)
        bar = mounting if row_index is None else row[row_index]
        chain.append((bar, row_index is None))
        fixed.append((len(chain) - 1, x_at(corner, bar)))
        if corner + 1 < count and n >= count:
            assert row_index is not None
            chain.extend((item, False) for item in row[row_index + 1 : assigned[corner + 1]])
        elif n == 1 and corner + 1 < count:
            if corners[corner][0] < _mm(row[0].x) <= corners[corner + 1][0]:
                chain.append((row[0], False))

    positions: dict[int, float] = dict(fixed)
    for (left, x_left), (right, x_right) in zip(fixed, fixed[1:]):
        items = [bar for bar, _ in chain[left : right + 1]]
        span = x_right - x_left
        if not fits(items, span):
            raise CageDetailingError(
                "The cage corners are too close, or too far apart, for the bars and spacing limits."
            )
        distances = steps(items)
        # Water-fill the slack without exceeding any centre-distance cap.
        remaining = span - sum(distances)
        active = set(range(len(distances)))
        while remaining > 1e-8 and active:
            share = remaining / len(active)
            for gap in tuple(active):
                extra = min(share, max_gap - distances[gap])
                distances[gap] += extra
                remaining -= extra
                if distances[gap] >= max_gap - 1e-8:
                    active.remove(gap)
        x = x_left
        for offset, distance in enumerate(distances, start=1):
            x += distance
            positions[left + offset] = x

    resistant: list[BarPosition] = []
    supplementary: list[BarPosition] = []
    for index, (bar, added) in enumerate(chain):
        positioned = replace(bar, x=positions[index] * _geometry_unit(mounting.x))
        (supplementary if added else resistant).append(positioned)
    return resistant, supplementary


def _geometry_unit(length: Quantity) -> Quantity:
    """One millimetre in the geometry's display unit."""
    return (length * 0 + 1 * length.units) / float((1 * length.units).to("mm").magnitude)


def build_cage_detailing(beam: RectangularBeam) -> SectionGeometry:
    """Return a supported cross-section; raise if its spacing cannot be achieved.

    This does not mutate the beam or include mounting bars in its resistance.
    ``bars`` remain the resistant bars; ``mounting_bars`` are additional steel.
    """
    from mento.skin_reinforcement import add_skin_bars

    geometry = build_section_geometry(beam)
    if not geometry.stirrups:
        return add_skin_bars(beam, geometry)
    settings = beam.settings
    assert settings is not None
    diameter = settings.mounting_bar_diameter
    if not math.isfinite(_mm(diameter)) or _mm(diameter) <= 0:
        raise ValueError("mounting_bar_diameter must be positive and finite.")
    if diameter < settings.minimum_longitudinal_diameter:
        raise ValueError("mounting_bar_diameter is below minimum_longitudinal_diameter.")
    d_st = _mm(geometry.stirrup_d_b)
    if design_code(beam.concrete).stirrup_bend_inner_diameter is None:
        raise CageDetailingError("This code has no supported stirrup-bend rule.", reason="bend")
    bend_radius = (_mm(geometry.stirrup_bend_inner_diameter) + d_st) / 2
    for stirrup in geometry.stirrups:
        if min(_mm(stirrup.x_right - stirrup.x_left), _mm(stirrup.y_top - stirrup.y_bottom)) / 2 < bend_radius - 1e-8:
            raise CageDetailingError("The stirrup is too narrow for its required bends.", reason="bend")
    corners = sorted(
        (x, side) for stirrup in geometry.stirrups for x, side in ((_mm(stirrup.x_left), 1), (_mm(stirrup.x_right), -1))
    )
    hook = design_code(beam.concrete).max_bar_spacing_tension
    max_gap = math.inf if hook is None else _mm(hook(beam))
    try:
        flexure = beam.flexure_design
        tension_faces = {face for face in ("bottom", "top") if getattr(flexure, face).DCR > 0}
    except DesignNotRunError:
        # Without flexure results, the tension face is unknown. The layout
        # checks fit only; plot() explicitly marks the spacing check pending.
        tension_faces = set()
    bars, mounting_bars = [], []
    for face in ("bottom", "top"):
        row = geometry.bars_on(face, 1)
        y = geometry.c_c + geometry.stirrup_d_b + diameter / 2
        mounting = BarPosition(
            geometry.width / 2,
            y if face == "bottom" else geometry.height - y,
            diameter.to(geometry.width.units),
            face,
            1,
            0,
        )
        # Match the rebar selector: the vibrator enters through the upper face.
        clear = max(_mm(settings.clear_spacing), _mm(diameter), *(_mm(b.d_b) for b in row))
        if face == "top":
            clear = max(clear, _mm(settings.vibrator_size))
        # Mounting bars cannot disguise excessive spacing of resistant steel.
        # A face with no resistant steel has no tension-spacing cap to apply.
        face_cap = max_gap if face in tension_faces else math.inf
        packing_cap = face_cap if len(row) >= len(corners) else math.inf
        resistant, added = _supported_layer(row, corners, mounting, clear, packing_cap, d_st, bend_radius)
        spacing = (
            _mm(geometry.width)
            if len(resistant) == 1
            else max((_mm(right.x - left.x) for left, right in zip(resistant, resistant[1:])), default=0.0)
        )
        if spacing > face_cap + 1e-8:
            raise CageDetailingError(
                "The resistant bars exceed their maximum centre spacing; mounting steel cannot replace them."
            )
        bars.extend(resistant)
        bars.extend(geometry.bars_on(face, 2))
        mounting_bars.extend(added)

    # Retained second layers must also fit; added mounting bars may not clash
    # with bars of the opposite face or a second layer.
    geometry = add_skin_bars(beam, replace(geometry, bars=tuple(bars), mounting_bars=tuple(mounting_bars)))
    all_bars = bars + mounting_bars + list(geometry.skin_bars)
    for index, bar in enumerate(all_bars):
        radius = _mm(bar.d_b) / 2
        if not radius <= _mm(bar.y) <= _mm(geometry.height) - radius:
            raise CageDetailingError("The supported bars do not fit within the section height.")
        for stirrup in geometry.stirrups:
            half_w = _mm(stirrup.x_right - stirrup.x_left) / 2
            half_h = _mm(stirrup.y_top - stirrup.y_bottom) / 2
            bend = bend_radius
            if min(half_w, half_h) < bend - 1e-8:
                raise CageDetailingError("The stirrup is too narrow for its required bends.", reason="bend")
            dx = abs(_mm(bar.x - (stirrup.x_left + stirrup.x_right) / 2)) - (half_w - bend)
            dy = abs(_mm(bar.y - (stirrup.y_bottom + stirrup.y_top) / 2)) - (half_h - bend)
            distance_to_line = abs(math.hypot(max(dx, 0), max(dy, 0)) + min(max(dx, dy), 0) - bend)
            if distance_to_line < radius + d_st / 2 - 1e-8:
                raise CageDetailingError("A longitudinal bar would intersect a stirrup branch or bend.")
        for other in all_bars[index + 1 :]:
            distance = math.hypot(_mm(bar.x - other.x), _mm(bar.y - other.y))
            required = (_mm(bar.d_b) + _mm(other.d_b)) / 2 + _mm(settings.clear_spacing)
            if distance < required - 1e-8:
                raise CageDetailingError(
                    "The supported cage leaves insufficient clear spacing between longitudinal bars."
                )
    return geometry
