"""Trabas seccionales ACI/CIRSOC: §25.3.5 y Tabla 25.3.2.

Propuesta de 135°/90°, con ambos órdenes seccionales y alternancia requerida.
No es una comprobación sísmica ni de ejecución longitudinal del elemento.
EN conserva su verificación de sujeción pendiente.
"""

from __future__ import annotations

import math
from dataclasses import replace
from typing import TYPE_CHECKING

from mento.units import Quantity, inch, mm

if TYPE_CHECKING:
    from mento.section_geometry import BarPosition, Crosstie, SectionGeometry


def hook_rule(code: str, imperial: bool, diameter: Quantity) -> tuple[Quantity, Quantity] | None:
    """Mandril y cola de 135°; no extrapolar tamaños fuera de Tabla 25.3.2."""
    d = float(diameter.to(mm).magnitude)
    if code not in ("ACI 318-19", "CIRSOC 201-25") or not math.isfinite(d):
        return None
    if imperial and code == "ACI 318-19":
        if not 9.525 - 1e-6 <= d <= 25.4 + 1e-6:
            return None
        factor = 4 if d <= 15.875 + 1e-6 else 6
        minimum = 3 * inch
    else:
        if not (10 <= d <= 16 or 20 <= d <= 25):
            return None
        factor = 4 if d <= 16 else 6
        minimum = 75 * mm
    return factor * diameter, max(6 * diameter, minimum)


def hook_curves(tie: Crosstie, diameter: Quantity) -> tuple[tuple[tuple[float, float], float, int], ...]:
    """Centros, radio y sentido vertical de los dos dobleces, en mm."""
    if tie.bend_inner_diameter is None:
        return ()
    radius = float((tie.bend_inner_diameter + diameter).to(mm).magnitude) / 2
    x = float(tie.x.to(mm).magnitude) + tie.side * radius
    return (
        ((x, float(tie.y_bottom.to(mm).magnitude) + radius), radius, 1),
        ((x, float(tie.y_top.to(mm).magnitude) - radius), radius, -1),
    )


def hook_points(tie: Crosstie, diameter: Quantity) -> tuple[tuple[tuple[float, float], ...], ...]:
    """Dos arcos de 135° y sus colas tangentes hacia el interior, para dibujar."""
    if tie.extension is None:
        return ()
    extension = float(tie.extension.to(mm).magnitude)
    paths = []
    for ((x, y), radius, sign), angle in zip(hook_curves(tie, diameter), tie.hooks):
        points = tuple(
            (x + tie.side * radius * math.cos(math.radians(a)), y + sign * radius * math.sin(math.radians(a)))
            for a in range(180, 181 + angle, 5)
        )
        theta = math.radians(180 + angle)
        paths.append(
            points
            + (
                (
                    points[-1][0] - tie.side * extension * math.sin(theta),
                    points[-1][1] + sign * extension * math.cos(theta),
                ),
            )
        )
    return tuple(paths)


def hook_distance(bar: BarPosition, tie: Crosstie, diameter: Quantity) -> float:
    """Distancia exacta del centro de barra a los arcos y colas, sin muestreo."""
    distances = []
    assert tie.extension is not None
    extension = float(tie.extension.to(mm).magnitude)
    for ((x, y), radius, sign), hook in zip(hook_curves(tie, diameter), tie.hooks):
        u = (float(bar.x.to(mm).magnitude) - x) * tie.side
        v = (float(bar.y.to(mm).magnitude) - y) * sign
        angle = math.degrees(math.atan2(v, u)) % 360
        theta = math.radians(180 + hook)
        ex, ey = radius * math.cos(theta), radius * math.sin(theta)
        tx, ty = -math.sin(theta), math.cos(theta)
        arc = (
            abs(math.hypot(u, v) - radius)
            if 180 <= angle <= 180 + hook
            else min(math.hypot(u + radius, v), math.hypot(u - ex, v - ey))
        )
        projection = max(0.0, min(extension, (u - ex) * tx + (v - ey) * ty))
        tail = math.hypot(u - ex - projection * tx, v - ey - projection * ty)
        distances.append(min(arc, tail))
    return min(distances, default=math.inf)


def tie_supports(bar: BarPosition, tie: Crosstie, geometry: SectionGeometry, code: str, imperial: bool) -> bool:
    """Crédito seccional solo si ambos extremos abrazan barras reales."""
    rule = hook_rule(code, imperial, geometry.stirrup_d_b)
    if rule is None or tie.hooks not in ((135, 135), (135, 90), (90, 135)) or tie.side not in (-1, 1):
        return False
    bend, extension = rule
    if 90 in tie.hooks:
        if not tie.alternate_hooks:
            return False
        limit = 15.875 if imperial and code == "ACI 318-19" else 16.0
        if float(geometry.stirrup_d_b.to(mm).magnitude) > limit + 1e-6:
            extension = max(extension, 12 * geometry.stirrup_d_b)
    if tie.bend_inner_diameter is None or tie.extension is None:
        return False
    if not all(
        math.isfinite(float(v.to(mm).magnitude))
        for v in (tie.bend_inner_diameter, tie.extension, tie.x, tie.y_bottom, tie.y_top)
    ):
        return False
    if tie.bend_inner_diameter < bend or tie.extension < extension or len(tie.engaged_bars) != 2:
        return False
    actual = geometry.bars + geometry.mounting_bars
    curves = hook_curves(tie, geometry.stirrup_d_b)
    if float((tie.y_top - tie.y_bottom).to(mm).magnitude) < 2 * curves[0][1]:
        return False
    for face, engaged, ((x, y), radius, _) in zip(("bottom", "top"), tie.engaged_bars, curves):
        if engaged not in actual or engaged.layer != 1 or engaged.face != face:
            return False
        offset = math.hypot(float(engaged.x.to(mm).magnitude) - x, float(engaged.y.to(mm).magnitude) - y)
        if (
            offset + float(engaged.d_b.to(mm).magnitude) / 2
            > radius - float(geometry.stirrup_d_b.to(mm).magnitude) / 2 + 1e-6
        ):
            return False
    return bar in tie.engaged_bars


def finalize_crossties(geometry: SectionGeometry) -> SectionGeometry:
    """Abrazar barras reales; verificar colas, recubrimiento y ambos órdenes 135/90.

    La alternancia longitudinal queda como requisito explícito de ejecución.
    No se valida aquí un detalle sísmico ni interferencias entre planos de acero.
    """
    from mento.cage_detailing import CageDetailingError

    diameter = geometry.stirrup_d_b
    half = float(diameter.to(mm).magnitude) / 2
    actual = geometry.bars + geometry.mounting_bars
    completed = []
    skin_bars = getattr(geometry, "skin_bars", ())
    for tie in geometry.crossties:
        if tie.bend_inner_diameter is None or tie.extension is None:
            completed.append(tie)
            continue
        curves = hook_curves(tie, diameter)
        if float((tie.y_top - tie.y_bottom).to(mm).magnitude) < 2 * curves[0][1]:
            raise CageDetailingError("The crosstie bends do not fit within the section height.", reason="bend")
        engaged = []
        for face, ((x, y), radius, _) in zip(("bottom", "top"), curves):
            found = [
                bar
                for bar in actual
                if bar.face == face
                and bar.layer == 1
                and math.hypot(float(bar.x.to(mm).magnitude) - x, float(bar.y.to(mm).magnitude) - y)
                + float(bar.d_b.to(mm).magnitude) / 2
                <= radius - half + 1e-6
            ]
            if len(found) != 1:
                raise CageDetailingError("Each crosstie end must engage one peripheral longitudinal bar.")
            engaged.append(found[0])
        tie = replace(tie, engaged_bars=tuple(engaged))
        phases = (tie, replace(tie, hooks=tuple(reversed(tie.hooks)))) if tie.alternate_hooks else (tie,)
        for phase in phases:
            # En estos arcos de 90/135°, los extremos y 270° incluyen los extremos
            # de coordenadas; el muestreo de 5° incluye ese ángulo exactamente.
            for path in hook_points(phase, diameter):
                for x, y in path:
                    cover = float(geometry.c_c.to(mm).magnitude) + half
                    if not (
                        cover - 1e-6 <= x <= float(geometry.width.to(mm).magnitude) - cover + 1e-6
                        and cover - 1e-6 <= y <= float(geometry.height.to(mm).magnitude) - cover + 1e-6
                    ):
                        raise CageDetailingError("A crosstie hook or tail violates the section cover.")
            for bar in actual + skin_bars:
                if hook_distance(bar, phase, diameter) < float(bar.d_b.to(mm).magnitude) / 2 + half - 1e-6:
                    raise CageDetailingError(
                        "A longitudinal bar would intersect a crosstie hook or tail.",
                        reason="skin" if bar in skin_bars else "layout",
                    )
        completed.append(tie)
    return replace(geometry, crossties=tuple(completed))
