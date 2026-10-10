"""A supported cage, without crediting mounting steel in the resistance.

The calculation geometry stays available as ``section_geometry``. Detailing
keeps its stirrup legs and the resistant bars' counts and sizes. Their
horizontal positions change, and the bars at the corners of a closed stirrup
seat in its bend (``section_geometry.seated_corner``), a few millimetres
deeper in than the calculation places them; the layer behind follows them.
The other bars keep their calculated depth. A separate collection
records any supplementary mounting bars, including a missing upper face.

A cage that cannot accommodate its bars is rejected, rather than drawn with
unsupported corners or overlapping bars. This checks a cross-section layout,
including the modelled crosstie hooks, not development lengths, seismic
detailing, longitudinal execution or a bar bending schedule.

Crack-control centre-spacing limits come from the registered code (ACI 318-19
/ CIRSOC 201-25 §24.3.2, Table 24.3.2); the positioning search and mounting-bar
diameter are Mento choices. Rounded corners use the registered code mandrel rule
documented in SectionGeometry, with its diameter and code limits.
"""

from __future__ import annotations

import math
from time import perf_counter
from dataclasses import replace
from typing import TYPE_CHECKING, Sequence

from mento.codes.registry import design_code
from mento.design_results import DesignNotRunError
from mento.section_geometry import (
    BarPosition,
    SectionGeometry,
    build_section_geometry,
    corner_setback,
    seated_corner,
)
from mento.units import Quantity, mm

if TYPE_CHECKING:
    from mento.beam import RectangularBeam


class CageDetailingError(ValueError):
    """The given bars and stirrups cannot form the supported layout."""

    def __init__(self, message: str, *, reason: str = "layout") -> None:
        super().__init__(message)
        self.reason = reason


def _mm(value: Quantity) -> float:
    return float(value.to(mm).magnitude)


def _supported_layer(
    row: tuple[BarPosition, ...],
    corners: Sequence[tuple[float, ...]],
    mounting: BarPosition,
    clear: float,
    max_gap: float,
    d_st: float,
    bend_radius: float,
    compression_required: bool = False,
    inner_y: float | None = None,
) -> tuple[list[BarPosition], list[BarPosition], float]:
    """Place an ordered row at the cage corners, spreading spare bars between them.

    With enough resistant bars, a small dynamic program chooses which ones
    support the corners. Each interval must fit the complete bar chain, with
    its minimum clear distances and maximum centre distance. With fewer bars,
    mounting bars fill the remaining corners. A lone resistant bar stays at
    mid-width, between the mounting bars.

    A corner of a closed stirrup (``seated``) holds its bar seated in the
    bend (:func:`~mento.section_geometry.seated_corner`), a little further
    in than the depth the checks place the row at; a crosstie holds it
    against the horizontal branch. The third value returned is how far the
    deepest seated bar sank, for the layer behind to follow. ``inner_y`` is
    the inner face of the horizontal branch, in mm: every bar's depth is set
    from it, so a cage built again from this one puts the bars back in the
    same place.
    """
    n, count = len(row), len(corners)
    diameters = {id(bar): _mm(bar.d_b) for bar in (*row, mounting)}
    row_x = {id(bar): _mm(bar.x) for bar in row}

    def inset(corner: int, bar: BarPosition) -> float:
        """From the inner face of the leg to the centre of the bar at ``corner``."""
        corner_radius = corners[corner][2]
        seated = len(corners[corner]) > 3 and corners[corner][3]
        d_b = diameters[id(bar)]
        bend = 2 * corner_radius - d_st
        if seated:
            # Seated in the bend: the rule the rebar search and the checks
            # lay the row out with (section_geometry.end_setback).
            return seated_corner(bend, d_b)
        # A crosstie: tangent to the horizontal branch and clear of the hook.
        return d_b / 2 + corner_setback(bend, d_b, d_b / 2)

    def x_at(corner: int, bar: BarPosition) -> float:
        leg, side = corners[corner][:2]
        return leg + side * (d_st / 2 + inset(corner, bar))

    def steps(items: list[BarPosition]) -> list[float]:
        return [(diameters[id(a)] + diameters[id(b)]) / 2 + clear for a, b in zip(items, items[1:])]

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
                    if compression_required:
                        braced = (
                            [corners[corner - 1][2] > 0] + [False] * (index - previous - 1) + [corners[corner][2] > 0]
                        )
                        if any(not left and not right for left, right in zip(braced, braced[1:])):
                            continue  # La regla existente de barras alternadas.
                    span = x_at(corner, row[index]) - x_at(corner - 1, row[previous])
                    if not fits(list(row[previous : index + 1]), span):
                        continue
                    cost = states[corner - 1, previous][0] + (x_at(corner, row[index]) - row_x[id(row[index])]) ** 2
                    if cost < best[0]:
                        best = cost, previous
                if best[1] >= 0:
                    states[corner, index] = best
        if (count - 1, n - 1) not in states:
            if compression_required:
                try:
                    _supported_layer(row, corners, mounting, clear, max_gap, d_st, bend_radius, False)
                except CageDetailingError:
                    pass
                else:
                    raise CageDetailingError(
                        "The required compression bars cannot be supported by the selected transverse pieces.",
                        reason="compression_support",
                    )
            raise CageDetailingError(
                "The resistant bars cannot fit between the stirrup corners with the required spacing."
            )
        index = n - 1
        for corner in reversed(range(count)):
            assigned[corner] = index
            index = states[corner, index][1]
    elif n >= 2:
        available = (
            [i for i, corner in enumerate(corners) if corner[2] > 0] if compression_required else list(range(count))
        )
        if len(available) < n:
            available = list(range(count))
        assigned = {available[round(index * (len(available) - 1) / (n - 1))]: index for index in range(n)}

    # An ordered chain with a fixed bar at every corner.
    chain: list[tuple[BarPosition, bool]] = []
    fixed: list[tuple[int, float]] = []
    # How far each corner bar sinks below the depth of the row, into its bend.
    sinks: dict[int, float] = {}
    for corner in range(count):
        row_index = assigned.get(corner)
        bar = mounting if row_index is None else row[row_index]
        chain.append((bar, row_index is None))
        fixed.append((len(chain) - 1, x_at(corner, bar)))
        if len(corners[corner]) > 3 and corners[corner][3]:
            sinks[len(chain) - 1] = inset(corner, bar) - diameters[id(bar)] / 2
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
    unit = _geometry_unit(mounting.x)
    for index, (bar, added) in enumerate(chain):
        inward = 1 if bar.face == "bottom" else -1
        y = bar.y
        if inner_y is not None:
            y = (inner_y + inward * (diameters[id(bar)] / 2 + sinks.get(index, 0.0))) * unit
        positioned = replace(bar, x=positions[index] * unit, y=y)
        (supplementary if added else resistant).append(positioned)
    return resistant, supplementary, max(sinks.values(), default=0.0)


def _geometry_unit(length: Quantity) -> Quantity:
    """One millimetre in the geometry's display unit."""
    return (length * 0 + 1 * length.units) / float((1 * length.units).to(mm).magnitude)


def build_cage_detailing(beam: RectangularBeam, *, include_skin: bool = True) -> SectionGeometry:
    """Reutilizar una búsqueda por estado; piel y estados comparten la misma jaula."""
    base = build_section_geometry(beam)
    key = repr((base, vars(beam.settings), beam._flexure_checked, sorted(beam._compression_faces), beam.flexure_checks))
    cache: dict[str, SectionGeometry | CageDetailingError] = getattr(beam, "_cage_detail_cache", {})
    if key not in cache:
        cache = {}
        try:
            cache[key] = _search_cage_detailing(beam, include_skin=False)
        except CageDetailingError as error:
            cache[key] = error
        setattr(beam, "_cage_detail_cache", cache)
    result = cache[key]
    if isinstance(result, CageDetailingError):
        raise result
    if not include_skin:
        return result
    return _complete_skin_detail(beam, result)


def _complete_skin_detail(beam: RectangularBeam, geometry: SectionGeometry) -> SectionGeometry:
    """En PR174 no hay piel; la rama piel completa y comprueba esta misma jaula."""
    return _build_candidate(beam, geometry, include_skin=True)


def _search_cage_detailing(beam: RectangularBeam, *, include_skin: bool = False) -> SectionGeometry:
    """Un perimetral cerrado y trabas 135°/90° en todas las ramas interiores.

    §25.3.5 exige abrazar barras periféricas y alternar los extremos de 90°.
    Se comprueban ambos órdenes seccionales. La ejecución longitudinal y el
    detallado sísmico quedan fuera del modelo. EN conserva su estado pendiente.
    Las ramas propuestas no cambian A_v ni la resistencia ingresada.
    """
    from mento.compression_detailing import check_compression_detailing
    from mento.crosstie_detailing import hook_rule
    from mento.section_geometry import Crosstie

    base = build_section_geometry(beam)
    if base.stirrups:
        base = replace(base, input_legs=len(base.leg_x), calculation_s_w=base.s_w)
    if not base.stirrups or not beam._compression_faces or beam.concrete.design_code == "EN 1992-2004":
        return _build_candidate(beam, base, include_skin=include_skin)
    settings = beam.settings
    assert settings is not None
    diameter = settings.mounting_bar_diameter
    if not math.isfinite(_mm(diameter)) or _mm(diameter) <= 0:
        raise CageDetailingError("mounting_bar_diameter must be positive and finite.", reason="mounting")
    if diameter < settings.minimum_longitudinal_diameter:
        raise CageDetailingError("mounting_bar_diameter is below minimum_longitudinal_diameter.", reason="mounting")
    requested = len(base.leg_x)
    outer = base.stirrups[0]
    minimum_d = min([_mm(diameter)] + [_mm(bar.d_b) for bar in base.bars if bar.layer == 1])
    minimum_step = max(_mm(settings.clear_spacing), _mm(settings.vibrator_size), minimum_d) + minimum_d
    physical_max = int(_mm(outer.x_right - outer.x_left) / minimum_step) + 1
    if requested > physical_max:
        raise CageDetailingError("The legs cannot accommodate their supporting bars with the required spacing.")
    rule = hook_rule(beam.concrete.design_code, beam.concrete.unit_system == "imperial", base.stirrup_d_b)
    best = None
    last_error = None
    deadline = perf_counter() + 2.0
    for total in range(requested, physical_max + 1):
        if perf_counter() > deadline:
            raise CageDetailingError(
                "Compression support search exceeded its time budget.", reason="compression_support_search"
            )
        spacing: Quantity = (outer.x_right - outer.x_left) / (total - 1)
        xs: tuple[Quantity, ...] = tuple(outer.x_left + i * spacing for i in range(total))
        ties = []
        for i in range(1, total - 1):
            extension = None if rule is None else rule[1]
            if extension is not None and _mm(base.stirrup_d_b) > (
                15.875 if beam.concrete.unit_system == "imperial" else 16
            ):
                extension = max(extension, 12 * base.stirrup_d_b)
            ties.append(
                Crosstie(
                    i,
                    xs[i],
                    outer.y_bottom,
                    outer.y_top,
                    hooks=() if rule is None else (135, 90),
                    bend_inner_diameter=None if rule is None else rule[0],
                    extension=extension,
                    side=1 if xs[i] <= base.width / 2 else -1,
                    alternate_hooks=True,
                )
            )
        trial = replace(
            base, leg_x=xs, s_w=spacing, stirrups=(replace(outer, legs=(0, total - 1)),), crossties=tuple(ties)
        )
        try:
            detail = _build_candidate(beam, trial, include_skin=include_skin)
        except CageDetailingError as error:
            last_error = error
            continue
        result = check_compression_detailing(beam, detail)
        if result.status in ("passed", "pending"):
            return detail
        if best is None:
            best = detail
    if best is not None:
        return best
    assert last_error is not None
    raise last_error


def _build_candidate(beam: RectangularBeam, geometry: SectionGeometry, *, include_skin: bool = True) -> SectionGeometry:
    """Return a supported cross-section; raise if its spacing cannot be achieved.

    This does not mutate the beam or include mounting bars in its resistance.
    ``bars`` remain the resistant bars; ``mounting_bars`` are additional steel.
    """
    from mento.skin_reinforcement import add_skin_bars

    if not geometry.stirrups:
        return add_skin_bars(beam, geometry) if include_skin else geometry
    settings = beam.settings
    assert settings is not None
    diameter = settings.mounting_bar_diameter
    if not math.isfinite(_mm(diameter)) or _mm(diameter) <= 0:
        raise CageDetailingError("mounting_bar_diameter must be positive and finite.", reason="mounting")
    if diameter < settings.minimum_longitudinal_diameter:
        raise CageDetailingError("mounting_bar_diameter is below minimum_longitudinal_diameter.", reason="mounting")
    d_st = _mm(geometry.stirrup_d_b)
    bend_hook = design_code(beam.concrete).stirrup_bend_inner_diameter
    if bend_hook is None:
        raise CageDetailingError("This code has no supported stirrup-bend rule.", reason="unsupported_bend")
    try:
        bend_hook(beam.concrete, geometry.stirrup_d_b)
    except ValueError as error:
        raise CageDetailingError(str(error), reason="unsupported_bend") from error
    bend_radius = (_mm(geometry.stirrup_bend_inner_diameter) + d_st) / 2
    for stirrup in geometry.stirrups:
        if min(_mm(stirrup.x_right - stirrup.x_left), _mm(stirrup.y_top - stirrup.y_bottom)) / 2 < bend_radius - 1e-8:
            raise CageDetailingError("The stirrup is too narrow for its required bends.", reason="bend")
    corners = sorted(
        [
            (x, side, bend_radius, True)
            for stirrup in geometry.stirrups
            for x, side in ((_mm(stirrup.x_left), 1), (_mm(stirrup.x_right), -1))
        ]
        + [
            (
                _mm(tie.x),
                tie.side
                if tie.bend_inner_diameter is not None
                else (1 if _mm(tie.x) <= _mm(geometry.width) / 2 else -1),
                0.0 if tie.bend_inner_diameter is None else (_mm(tie.bend_inner_diameter) + d_st) / 2,
                False,
            )
            for tie in geometry.crossties
        ]
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
        compressed = (
            "bot" if face == "bottom" else "top"
        ) in beam._compression_faces and beam.concrete.design_code in ("ACI 318-19", "CIRSOC 201-25")
        if any(t.alternate_hooks and t.bend_inner_diameter is None for t in geometry.crossties):
            compressed = False  # Tamaño de traba no modelado: conservar propuesta, verificación pendiente.
        face_y = _mm(geometry.c_c + geometry.stirrup_d_b)
        inner_y = face_y if face == "bottom" else _mm(geometry.height) - face_y
        inward = 1 if face == "bottom" else -1
        # How far the row already sat in its bends: a cage built again from
        # this one moves the layer behind only by what is left.
        seated = max((inward * (_mm(bar.y) - inner_y) - _mm(bar.d_b) / 2 for bar in row), default=0.0)
        resistant, added, sink = _supported_layer(
            row, corners, mounting, clear, packing_cap, d_st, bend_radius, compressed, inner_y
        )
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
        second = geometry.bars_on(face, 2)
        # La capa 2 conserva cota y acero; alinear con la capa 1 evita atravesar
        # una rama vertical en el modelo de cálculo uniformemente espaciado.
        crosses = any(abs(_mm(bar.x - x)) < (_mm(bar.d_b) + d_st) / 2 - 1e-8 for bar in second for x in geometry.leg_x)
        if crosses and len(second) <= len(resistant):
            indices = [round(i * (len(resistant) - 1) / max(1, len(second) - 1)) for i in range(len(second))]
            second = tuple(replace(bar, x=resistant[index].x) for bar, index in zip(second, indices))
        # The layer behind hangs from the corner bars, so it sinks with them
        # and keeps the clear distance between layers.
        if abs(sink - max(seated, 0.0)) > 1e-9:
            shift: Quantity = inward * (sink - max(seated, 0.0)) * _geometry_unit(mounting.x)
            second = tuple(replace(bar, y=bar.y + shift) for bar in second)
        bars.extend(second)
        mounting_bars.extend(added)

    # Retained second layers must also fit; added mounting bars may not clash
    # with bars of the opposite face or a second layer.
    geometry = replace(geometry, bars=tuple(bars), mounting_bars=tuple(mounting_bars))
    if include_skin:
        geometry = add_skin_bars(beam, geometry)
    all_bars = bars + mounting_bars + list(geometry.skin_bars)
    skin_ids = {id(bar) for bar in geometry.skin_bars}
    # Converted once: the loops below read them for every bar and every pair.
    height = _mm(geometry.height)
    clear_spacing = _mm(settings.clear_spacing)
    diameters = [_mm(bar.d_b) for bar in all_bars]
    # The centre of each stirrup and its half sides, less the bend.
    extents = [
        (
            (stirrup.x_left + stirrup.x_right) / 2,
            (stirrup.y_bottom + stirrup.y_top) / 2,
            _mm(stirrup.x_right - stirrup.x_left) / 2 - bend_radius,
            _mm(stirrup.y_top - stirrup.y_bottom) / 2 - bend_radius,
        )
        for stirrup in geometry.stirrups
    ]
    for index, bar in enumerate(all_bars):
        radius = diameters[index] / 2
        if not radius <= _mm(bar.y) <= height - radius:
            raise CageDetailingError(
                "The supported bars do not fit within the section height.",
                reason="skin" if id(bar) in skin_ids else "layout",
            )
        for centre_x, centre_y, straight_w, straight_h in extents:
            dx = abs(_mm(bar.x - centre_x)) - straight_w
            dy = abs(_mm(bar.y - centre_y)) - straight_h
            distance_to_line = abs(math.hypot(max(dx, 0), max(dy, 0)) + min(max(dx, dy), 0) - bend_radius)
            if distance_to_line < radius + d_st / 2 - 1e-8:
                raise CageDetailingError(
                    "A longitudinal bar would intersect a stirrup branch or bend.",
                    reason="skin" if id(bar) in skin_ids else "layout",
                )
        for tie in geometry.crossties:
            # Tramo recto de la rama; los ganchos modelados se comprueban al final.
            dx = abs(_mm(bar.x - tie.x))
            dy = max(_mm(tie.y_bottom - bar.y), _mm(bar.y - tie.y_top), 0.0)
            if math.hypot(dx, dy) < radius + d_st / 2 - 1e-8:
                raise CageDetailingError(
                    "A longitudinal bar would intersect an open leg.",
                    reason="skin" if id(bar) in skin_ids else "layout",
                )
        for other, other_d in zip(all_bars[index + 1 :], diameters[index + 1 :]):
            distance = math.hypot(_mm(bar.x - other.x), _mm(bar.y - other.y))
            required = (diameters[index] + other_d) / 2 + clear_spacing
            if distance < required - 1e-8:
                raise CageDetailingError(
                    "The supported cage leaves insufficient clear spacing between longitudinal bars.",
                    reason="skin" if id(bar) in skin_ids or id(other) in skin_ids else "layout",
                )
    from mento.crosstie_detailing import finalize_crossties

    return finalize_crossties(geometry)
