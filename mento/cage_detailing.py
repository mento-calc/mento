"""A supported cage, without crediting mounting steel in the resistance.

The calculation geometry stays available as ``section_geometry``. Detailing
keeps its stirrup legs and the resistant bars' counts, sizes and vertical
coordinates. Only their horizontal positions change. A separate collection
records any supplementary mounting bars, including a missing upper face.

A cage that cannot accommodate its bars is rejected, rather than drawn with
unsupported corners or overlapping bars. This checks a cross-section layout,
not development lengths, hooks, seismic detailing or a bar bending schedule.
"""

from __future__ import annotations

import math
from time import perf_counter
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
    corners: list[tuple[float, int, float]],
    mounting: BarPosition,
    clear: float,
    max_gap: float,
    d_st: float,
    bend_radius: float,
    compression_required: bool = False,
) -> tuple[list[BarPosition], list[BarPosition]]:
    """Place an ordered row at the cage corners, spreading spare bars between them.

    With enough resistant bars, a small dynamic program chooses which ones
    support the corners. Each interval must fit the complete bar chain, with
    its minimum clear distances and maximum centre distance. With fewer bars,
    mounting bars fill the remaining corners. A lone resistant bar stays at
    mid-width, between the mounting bars.
    """
    n, count = len(row), len(corners)
    diameters = {id(bar): _mm(bar.d_b) for bar in (*row, mounting)}
    row_x = {id(bar): _mm(bar.x) for bar in row}

    def x_at(corner: int, bar: BarPosition) -> float:
        leg, side, corner_radius = corners[corner]
        # Tangent to the horizontal branch and clear of its rounded bend.
        return leg + side * max(corner_radius, (d_st + diameters[id(bar)]) / 2)

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
                        "The required compression bars cannot be supported by the selected closed stirrups.",
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


def build_cage_detailing(beam: RectangularBeam, *, include_skin: bool = True) -> SectionGeometry:
    """Reutilizar una búsqueda por estado; piel y estados comparten la misma jaula."""
    base = build_section_geometry(beam)
    key = repr((base, vars(beam.settings), beam._flexure_checked,
                sorted(beam._compression_faces), beam.flexure_checks))
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
    return geometry


def _search_cage_detailing(beam: RectangularBeam, *, include_skin: bool = False) -> SectionGeometry:
    """Un cerrado perimetral, cerrados por compresión y restantes patas abiertas.

    La cantidad ingresada es el mínimo por corte. La sujeción puede añadir
    ramas al detalle, sin modificar ni acreditar el acero resistente ingresado. Se busca la
    menor cantidad de cerrados interiores que cumpla la comprobación seccional
    ya implementada. Si ninguna disposición modelada cumple, se conserva un
    resultado fallido/pendiente; nunca se acredita una pata abierta como traba.
    No se verifican ganchos, empalmes ni detallado sísmico.
    """
    from itertools import combinations, chain
    from mento.compression_detailing import check_compression_detailing
    from mento.section_geometry import ClosedStirrup

    base = build_section_geometry(beam)
    base = replace(base, input_legs=len(base.leg_x), calculation_s_w=base.s_w)
    if not base.stirrups or not beam._compression_faces:
        return _build_candidate(beam, base, include_skin=include_skin)
    requested = len(base.leg_x)
    # Las ramas de corte ingresadas son un mínimo. Si falta sujeción, se
    # agregan piezas cerradas en el detalle, sin acreditar su acero en A_v.
    extra_limit = 2 * max(
        (len(base.bars_on("bottom" if face == "bot" else "top", 1)) for face in beam._compression_faces), default=0
    )
    settings = beam.settings
    assert settings is not None
    diameter = settings.mounting_bar_diameter
    if not math.isfinite(_mm(diameter)) or _mm(diameter) <= 0:
        raise CageDetailingError("mounting_bar_diameter must be positive and finite.", reason="mounting")
    if diameter < settings.minimum_longitudinal_diameter:
        raise CageDetailingError("mounting_bar_diameter is below minimum_longitudinal_diameter.", reason="mounting")
    minimum_d = min([_mm(settings.mounting_bar_diameter)] + [_mm(bar.d_b) for bar in base.bars if bar.layer == 1])
    minimum_step = max(_mm(settings.clear_spacing), _mm(settings.vibrator_size), minimum_d) + minimum_d
    physical_max = int(_mm(base.stirrups[0].x_right - base.stirrups[0].x_left) / minimum_step) + 1
    if requested > physical_max:
        raise CageDetailingError("The legs cannot accommodate their supporting bars with the required spacing.")
    extra_limit = min(extra_limit, max(0, physical_max - requested))
    best = None
    last_error = None
    attempts = 0
    deadline = perf_counter() + 2.0
    for total in range(requested, requested + extra_limit + 1):
        outer = base.stirrups[0]
        spacing = (outer.x_right - outer.x_left) / (total - 1)
        xs = tuple(outer.x_left + i * spacing for i in range(total))
        from mento.section_geometry import Crosstie

        current = replace(
            base,
            leg_x=xs,
            s_w=spacing,
            stirrups=(replace(outer, legs=(0, total - 1)),),
            crossties=tuple(Crosstie(i, xs[i], outer.y_bottom, outer.y_top) for i in range(1, total - 1)),
        )
        inner = list(range(1, total - 1))
        for count in range(len(inner) // 2 + 1):
            # Las ramas agregadas deben pertenecer a cerrados, no a nuevas
            # patas libres. Solo agregar acero necesario para la sujeción.
            if total > requested and 2 * count < total - requested:
                continue
            # Simétricos primero, antes de recortar el presupuesto.
            mirrors = [(i, total - 1 - i) for i in inner if i < total - 1 - i]
            symmetric = (tuple(sorted(i for pair in chosen for i in pair))
                         for chosen in combinations(mirrors, count))
            seen: set[tuple[int, ...]] = set()
            for indices in chain(symmetric, combinations(inner, 2 * count)):
                if indices in seen:
                    continue
                seen.add(indices)
                if attempts >= 2048 or perf_counter() >= deadline:
                    raise CageDetailingError(
                        "Compression-support search stopped at its candidate/time limit; no verified cage was found.",
                        reason="compression_support_search",
                    )
                attempts += 1
                pairs = list(zip(indices[::2], indices[1::2]))
                closed = current.stirrups + tuple(
                    ClosedStirrup(pair, xs[pair[0]], xs[pair[1]], outer.y_bottom, outer.y_top, False) for pair in pairs
                )
                trial = replace(
                    current, stirrups=closed, crossties=tuple(t for t in current.crossties if t.leg not in indices)
                )
                try:
                    detail = _build_candidate(beam, trial, include_skin=include_skin)
                except CageDetailingError as error:
                    last_error = error
                    continue
                result = check_compression_detailing(beam, detail)
                if result.status == "passed":
                    return detail
                # No agregar ramas para cubrir una verificación fuera de alcance
                # (EN o segunda fila): esa verificación permanece pendiente.
                if result.status == "pending":
                    return detail
                if best is None:
                    best = detail
        if beam.concrete.design_code == "EN 1992-2004":
            break
    if best is not None:
        return best
    assert last_error is not None
    raise last_error


def _build_candidate(beam: RectangularBeam, geometry: SectionGeometry, *, include_skin: bool = True) -> SectionGeometry:
    """Return a supported cross-section; raise if its spacing cannot be achieved.

    This does not mutate the beam or include mounting bars in its resistance.
    ``bars`` remain the resistant bars; ``mounting_bars`` are additional steel.
    """
    if not geometry.stirrups:
        return geometry
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
            (x, side, bend_radius)
            for stirrup in geometry.stirrups
            for x, side in ((_mm(stirrup.x_left), 1), (_mm(stirrup.x_right), -1))
        ]
        + [(_mm(tie.x), 1 if _mm(tie.x) <= _mm(geometry.width) / 2 else -1, 0.0) for tie in geometry.crossties]
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
        resistant, added = _supported_layer(row, corners, mounting, clear, packing_cap, d_st, bend_radius, compressed)
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
    all_bars = bars + mounting_bars
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
        for tie in geometry.crossties:
            # La pata abierta se representa por su tramo recto. No se inventan
            # ganchos y no se la acredita como sujeción de acero comprimido.
            dx = abs(_mm(bar.x - tie.x))
            dy = max(_mm(tie.y_bottom - bar.y), _mm(bar.y - tie.y_top), 0.0)
            if math.hypot(dx, dy) < radius + d_st / 2 - 1e-8:
                raise CageDetailingError("A longitudinal bar would intersect an open leg.", reason="layout")
        for other in all_bars[index + 1 :]:
            distance = math.hypot(_mm(bar.x - other.x), _mm(bar.y - other.y))
            required = (_mm(bar.d_b) + _mm(other.d_b)) / 2 + _mm(settings.clear_spacing)
            if distance < required - 1e-8:
                raise CageDetailingError(
                    "The supported cage leaves insufficient clear spacing between longitudinal bars."
                )
    return replace(geometry, bars=tuple(bars), mounting_bars=tuple(mounting_bars))
