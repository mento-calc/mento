"""Drawing of a beam cross-section.

The section drawing used to live on ``RectangularBeam`` itself, which made the
element class part matplotlib. Phase 3 of the architecture roadmap moves it
here; ``beam.plot()`` stays as a one-line delegation, so nothing calling it
changes.

These are module functions taking the beam, the same shape the design-code
modules use. They still write ``_fig`` and ``_ax`` back onto it, because that
is what the notebook views and the Word reports pick the figure up from.

A beam is drawn from its public ``detailing_geometry``: its calculated steel
at supported cage corners, with supplementary mounting steel shown separately.
An unsuccessful layout falls back to labelled calculation geometry. Helpers
take the axes and the geometry, not the beam. A slab strip, which the geometry
gives no bars, keeps the drawing it always had.
"""

from __future__ import annotations

import math
import textwrap
from dataclasses import replace
from typing import TYPE_CHECKING, Dict, List, Optional, Sequence, Tuple, cast

import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.patches import Circle, FancyBboxPatch, Polygon, Rectangle
from matplotlib.transforms import Bbox

from mento.bar_sizes import bar_designation, is_us_customary
from mento.cage_detailing import CageDetailingError
from mento.design_results import (
    GRID,
    format_transverse_rebar,
    placed_bars,
)
from mento.i18n import translate
from mento.precompute import DISPLAY
from mento.results import CUSTOM_COLORS
from mento.section_geometry import BarPosition, Crosstie, SectionGeometry
from mento.units import Quantity, ureg

if TYPE_CHECKING:
    from matplotlib.axes import Axes
    from matplotlib.text import Text

    from mento.beam import RectangularBeam
    from mento.settings import BeamSettings


def _axes(beam: "RectangularBeam") -> "Axes":
    """The axes currently being drawn on.

    Typed ``Optional`` on the section because a section that was never plotted
    has none; every helper here runs inside :func:`plot_beam_section`, which
    creates them first.
    """
    return cast("Axes", beam._ax)


def _settings(beam: "RectangularBeam") -> "BeamSettings":
    """The beam's settings, which ``__post_init__`` always fills in."""
    return cast("BeamSettings", beam.settings)


def _plot_rebar_layer(
    self: "RectangularBeam",
    width_cm: float,
    height_cm: float,
    c_c_cm: float,
    stirrup_d_b_cm: float,
    layers_spacing_cm: float,
    n1: float,
    d_b1: Quantity,
    n2: float,
    d_b2: Quantity,
    max_db: Quantity,
    is_bottom: bool = True,
    is_second_layer: bool = False,
) -> None:
    """
    Helper method to plot a single layer of rebars.
    """
    # A slab strip carries width / s bars, which need not be a whole number
    # (mento.slab._bars_at_spacing); what is drawn is the whole bars that
    # cover the strip. A beam's count is whole already.
    n1, n2 = placed_bars(n1), placed_bars(n2)

    # Calculate y-position based on layer and bottom/top
    y_base = c_c_cm + stirrup_d_b_cm if is_bottom else height_cm - c_c_cm - stirrup_d_b_cm

    if is_second_layer:
        y_base += (
            layers_spacing_cm + max_db.to("cm").magnitude
            if is_bottom
            else -layers_spacing_cm - max_db.to("cm").magnitude
        )

    # Plot side bars (position 1 or 3)
    if n1 > 0:
        diameter_cm = d_b1.to("cm").magnitude
        radius_cm = diameter_cm / 2.0

        # nominal vertical center before corner correction
        y_center_nominal = y_base + radius_cm if is_bottom else y_base - radius_cm

        # width available between inner faces of stirrup legs, for this bar diameter
        clear_span = width_cm - 2 * (c_c_cm + stirrup_d_b_cm + radius_cm)

        # corner offset depends on stirrup diameter (controls bend radius)
        corner_offset = 0.43 * stirrup_d_b_cm  # tune factor if needed

        for i in range(n1):
            # even if n1 == 1, just center it
            if n1 == 1:
                x_nominal = width_cm / 2.0
            else:
                x_nominal = c_c_cm + stirrup_d_b_cm + radius_cm + i * (clear_span / (n1 - 1))

            # default: no shift
            x_shift = 0.0
            y_shift = 0.0

            # leftmost bar
            if i == 0:
                x_shift = corner_offset  # push inward (to the right)
                y_shift = corner_offset if is_bottom else -corner_offset
            # rightmost bar
            elif i == n1 - 1:
                x_shift = -corner_offset  # push inward (to the left)
                y_shift = corner_offset if is_bottom else -corner_offset

            x_plot = x_nominal + x_shift
            y_plot = y_center_nominal + y_shift

            circle = Circle(
                (x_plot, y_plot),
                radius_cm,
                color=CUSTOM_COLORS["dark_gray"],
                fill=True,
            )
            _axes(self).add_patch(circle)

    # ---------------------------------
    # Plot intermediate bars (group n2)
    # ---------------------------------
    if n2 > 0:
        diameter_cm = d_b2.to("cm").magnitude
        radius_cm = diameter_cm / 2.0

        y_center_nominal = y_base + radius_cm if is_bottom else y_base - radius_cm

        clear_span = width_cm - 2 * (c_c_cm + stirrup_d_b_cm + radius_cm)

        for i in range(n2):
            x_nominal = c_c_cm + stirrup_d_b_cm + radius_cm + (i + 1) * (clear_span / (n2 + 1))

            # intermediate bars: no special offset
            x_plot = x_nominal
            y_plot = y_center_nominal

            circle = Circle(
                (x_plot, y_plot),
                radius_cm,
                color=CUSTOM_COLORS["dark_gray"],
                fill=True,
            )
            _axes(self).add_patch(circle)


def _format_rebar_layer_text(
    self: "RectangularBeam",
    n1: int,
    d_b1: Quantity,
    n2: int,
    d_b2: Quantity,
) -> str:
    """
    Devuelve un string tipo '2Ø16+3Ø10' a partir de n1, d1, n2, d2.
    Si un grupo tiene n=0, no se incluye.
    Diámetros en mm.

    En slab:
        - Siempre combina en un único grupo: '5Ø12'.
    En beam:
        - Si n1 y n2 tienen el mismo diámetro, combina: '4Ø16'.
        - Si son distintos, deja el formato '2Ø16+3Ø10'.
    """

    mode = getattr(self, "mode", "beam")
    imperial = self.concrete.is_imperial

    def mark(d_b: Quantity) -> str:
        # A bar is its diameter in mm in SI and its ASTM size in US customary.
        return bar_designation(d_b) if imperial else f"Ø{d_b.to('mm').magnitude:.0f}"

    # -------------------------------
    # MODO SLAB: siempre combinar
    # -------------------------------
    if mode == "slab":
        total_bars = n1 + n2
        if total_bars == 0:
            return ""

        # Tomar el diámetro "no nulo"
        if n1 > 0 and d_b1 is not None:
            d_b = d_b1
        elif n2 > 0 and d_b2 is not None:
            d_b = d_b2
        else:
            return ""  # por seguridad

        return f"{total_bars}{mark(d_b)}"

    # -------------------------------
    # MODO BEAM
    # -------------------------------
    # Si n1 y n2 tienen el mismo diámetro y ambos > 0 → combinar
    if n1 > 0 and n2 > 0 and d_b1 is not None and d_b2 is not None:
        # Igualdad con una pequeña tolerancia
        if abs(d_b1.to("mm").magnitude - d_b2.to("mm").magnitude) < 1e-6:
            total_bars = n1 + n2
            return f"{total_bars}{mark(d_b1)}"

    # Caso general: como lo tenías antes
    parts: list[str] = []

    if n1 > 0 and d_b1 is not None:
        parts.append(f"{n1}{mark(d_b1)}")

    if n2 > 0 and d_b2 is not None:
        parts.append(f"{n2}{mark(d_b2)}")

    return "+".join(parts) if parts else ""


def _annotate_rebar_layer_text(
    self: "RectangularBeam",
    width_cm: float,
    height_cm: float,
    c_c_cm: float,
    stirrup_d_b_cm: float,
    layers_spacing_cm: float,
    n1: float,
    d_b1: Quantity,
    n2: float,
    d_b2: Quantity,
    max_db: Quantity,
    is_bottom: bool = True,
    is_second_layer: bool = False,
) -> None:
    """
    Escribe a la derecha de la sección la leyenda de armadura para un layer.
    Ejemplo: '2Ø16+3Ø10'.
    """

    # The whole bars the drawing shows; see _plot_rebar_layer.
    text = _format_rebar_layer_text(self, placed_bars(n1), d_b1, placed_bars(n2), d_b2)
    if not text:
        return  # nada que mostrar

    # misma lógica de y_base que en _plot_rebar_layer
    y_base = c_c_cm + stirrup_d_b_cm if is_bottom else height_cm - c_c_cm - stirrup_d_b_cm

    if is_second_layer:
        shift = layers_spacing_cm + max_db.to("cm").magnitude
        y_base = y_base + shift if is_bottom else y_base - shift

    # posición vertical aproximada del centro del layer
    rep_db_cm = max_db.to("cm").magnitude
    y_center = y_base + rep_db_cm / 2.0 if is_bottom else y_base - rep_db_cm / 2.0

    # posición horizontal del texto (a la derecha de la sección)
    x_text = width_cm + 0.1 * width_cm

    _axes(self).text(
        x_text,
        y_center,
        text,
        ha="left",
        va="center",
        color=CUSTOM_COLORS["dark_gray"],
        # fontsize=10,
    )


def _annotate_stirrups_text(
    self: "RectangularBeam",
    width_cm: float,
    height_cm: float,
) -> None:
    """
    Escribe la leyenda de la grilla de una losa a la derecha, a media altura.
    Ejemplo: 'Ø10/8×15'. Una viga escribe la suya con :func:`_annotate_cage_text`.
    """
    if self._stirrup_n == 0:
        return  # nothing to show

    transverse = self.reinforcement.transverse
    # Bare magnitudes, as the drawing has always shown them: mm for the bar,
    # cm for the spacings, no unit suffix. The shape of the label is the
    # element's, which is what format_transverse_rebar decides.
    imperial = self.concrete.is_imperial
    length = DISPLAY[imperial]["length"]
    bar = bar_designation(self._stirrup_d_b) if imperial else f"Ø{self._stirrup_d_b.to('mm').magnitude:.0f}"
    text = format_transverse_rebar(
        transverse.layout,
        transverse.n_stirrups,
        bar,
        f"{self._stirrup_s_l.to(length).magnitude:.0f}",
        f"{transverse.s_w.to(length).magnitude:.0f}",
        imperial=imperial,
    )

    x_text = width_cm + 0.1 * width_cm
    y_text = height_cm / 2.0

    _axes(self).text(
        x_text,
        y_text,
        text,
        ha="left",
        va="center",
        color=CUSTOM_COLORS["dark_gray"],
        # fontsize=10,
    )


def _cm(value: Quantity) -> float:
    """A length of the geometry in the centimetres the drawing is made in."""
    return float(value.to("cm").magnitude)


def _add_rounded_stirrup(
    ax: "Axes",
    x0: float,
    y0: float,
    width: float,
    height: float,
    db_cm: float,
    bend_cm: float,
    facecolor: str,
) -> None:
    """
    Add one closed stirrup with rounded corners and thickness db_cm.

    All dimensions in cm. (x0, y0) is the bottom-left of the OUTER stirrup
    line, and ``bend_cm`` the inside diameter of its bends.

    A stirrup narrower than its two bends -- an inner stirrup whose legs sit
    closer than ``bend_cm + db_cm`` apart -- cannot take that bend. It is drawn
    as the hairpin it would be, each radius capped at half the width of its
    line, instead of letting the rounding overrun the straight segments.
    """
    inner_width = width - 2 * db_cm
    inner_height = height - 2 * db_cm
    inner_radius = max(0.0, min(bend_cm / 2, inner_width / 2, inner_height / 2))
    outer_radius = min(inner_radius + db_cm, width / 2, height / 2)

    outer = FancyBboxPatch(
        (x0, y0),
        width,
        height,
        boxstyle=f"Round, pad=0, rounding_size={outer_radius}",
        edgecolor=CUSTOM_COLORS["dark_blue"],
        facecolor="white",
        linewidth=db_cm,  # thickness of the steel
    )
    ax.add_patch(outer)

    inner = FancyBboxPatch(
        (x0 + db_cm, y0 + db_cm),
        inner_width,
        inner_height,
        boxstyle=f"Round, pad=0, rounding_size={inner_radius}",
        edgecolor=CUSTOM_COLORS["dark_blue"],
        facecolor=facecolor,
        linewidth=1,
    )
    ax.add_patch(inner)


def _band(ax: "Axes", path: Sequence[Tuple[float, float]], db_cm: float, gid: str) -> None:
    """Draw a bar along its centreline ``path`` (cm) as the stirrups are drawn: two lines, a bar apart."""
    half = db_cm / 2
    left, right = [], []
    for i, (x, y) in enumerate(path):
        x0, y0 = path[max(i - 1, 0)]
        x1, y1 = path[min(i + 1, len(path) - 1)]
        dx, dy = x1 - x0, y1 - y0
        length = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / length, dx / length
        left.append((x + half * nx, y + half * ny))
        right.append((x - half * nx, y - half * ny))
    ax.add_patch(
        Polygon(
            left + right[::-1],
            closed=True,
            facecolor="white",
            edgecolor=CUSTOM_COLORS["dark_blue"],
            linewidth=1.0,
            gid=gid,
        )
    )


def _arc(cx: float, cy: float, radius: float, start: float, stop: float, side: int) -> List[Tuple[float, float]]:
    """Points of an arc in degrees from ``start`` to ``stop``, mirrored across x when ``side`` is -1."""
    steps = max(2, int(abs(stop - start) / 5) + 1)
    return [
        (
            cx + side * radius * math.cos(math.radians(start + (stop - start) * k / (steps - 1))),
            cy + radius * math.sin(math.radians(start + (stop - start) * k / (steps - 1))),
        )
        for k in range(steps)
    ]


def _engaged_bar(tie: Crosstie, geometry: SectionGeometry, face: str) -> Optional[BarPosition]:
    """The bar of ``face`` the crosstie wraps: the one at its leg, if there is one there."""
    candidates = [bar for bar in (*geometry.bars, *geometry.mounting_bars) if bar.face == face and bar.layer == 1]
    if not candidates:
        return None
    bar = min(candidates, key=lambda b: abs(_cm(b.x) - _cm(tie.x)))
    return bar if abs(_cm(bar.x) - _cm(tie.x)) <= 2 * _cm(bar.d_b) + 2 * _cm(geometry.stirrup_d_b) else None


def _crosstie_path(tie: Crosstie, geometry: SectionGeometry, db_cm: float, bend_cm: float) -> List[Tuple[float, float]]:
    """The centreline of a crosstie, in cm: a 90° leg around the bottom bar, the leg, a 135° hook around the top one.

    ACI 318-19 §25.3.5: a crosstie engages a longitudinal bar at each end, with
    a 135° hook at one and a 90° one at the other, each with an extension of
    6 d_b (Table 25.3.2). Each bend is drawn tight around the bar it wraps,
    in the plane of the stirrup's branch, and the leg runs tangent to both;
    where no bar sits at the leg the bend takes the stirrups' mandrel, inside
    the branch. A crosstie the detailing modelled keeps its own bends.
    """
    side = _tie_side(tie, geometry)
    if tie.bend_inner_diameter is not None and tie.extension is not None:
        from mento.crosstie_detailing import hook_points
        from mento.units import cm

        hooked_bottom, hooked_top = hook_points(tie, db_cm * cm)
        return [(px / 10, py / 10) for px, py in (*hooked_bottom[::-1], *hooked_top)]
    mandrel = (bend_cm + db_cm) / 2
    extension = 6 * db_cm
    ends: List[Tuple[Optional[float], float, float]] = []
    for face, y_branch in (("bottom", _cm(tie.y_bottom)), ("top", _cm(tie.y_top))):
        bar = _engaged_bar(tie, geometry, face)
        if bar is None:
            ends.append((None, mandrel, y_branch + mandrel if face == "bottom" else y_branch - mandrel))
        else:
            ends.append((_cm(bar.x), (_cm(bar.d_b) + db_cm) / 2, _cm(bar.y)))
    (x_bottom, r_bottom, y_bottom), (x_top, r_top, y_top) = ends
    # The leg is where the check puts it; _align_bars_to_ties draws the bars it wraps beside it.
    x_leg = _cm(tie.x)
    bottom = _arc(x_leg + side * r_bottom, y_bottom, r_bottom, 270, 180, side)
    bottom.insert(0, (x_leg + side * (r_bottom + extension), y_bottom - r_bottom))
    top = _arc(x_leg + side * r_top, y_top, r_top, 180, 45, side)
    tail = math.radians(45)
    end = top[-1]
    top.append((end[0] + side * extension * math.sin(tail), end[1] - extension * math.cos(tail)))
    return bottom + top


def _tie_side(tie: Crosstie, geometry: SectionGeometry) -> int:
    """The side a crosstie's hooks open to: where the bar it wraps sits, so that bar moves least."""
    for face in ("bottom", "top"):
        bar = _engaged_bar(tie, geometry, face)
        if bar is not None and not math.isclose(_cm(bar.x), _cm(tie.x)):
            return 1 if _cm(bar.x) > _cm(tie.x) else -1
    return 1 if tie.side >= 0 else -1


def _align_bars_to_ties(geometry: SectionGeometry) -> SectionGeometry:
    """The geometry with the bars each crosstie engages drawn beside its leg.

    The leg is where the shear check puts it; the bar it wraps at the bottom
    and the one at the top are drawn with their edge on it, so the leg runs
    tangent to both and each hook closes around its bar. The hooks open to
    the side the bar already sits on (:func:`_tie_side`), so the shift is at
    most about a bar diameter, and it is only of the drawing.
    """
    d_st = _cm(geometry.stirrup_d_b)
    moved: Dict[int, BarPosition] = {}
    for tie in geometry.crossties:
        if tie.bend_inner_diameter is not None and tie.extension is not None:
            continue  # A crosstie the detailing modelled keeps its bars where it put them.
        side = _tie_side(tie, geometry)
        for face in ("bottom", "top"):
            bar = _engaged_bar(tie, geometry, face)
            if bar is None:
                continue
            x = _cm(tie.x) + side * (_cm(bar.d_b) + d_st) / 2
            moved[id(bar)] = replace(bar, x=(x * ureg.cm).to(bar.x.units))
    if not moved:
        return geometry
    return replace(
        geometry,
        bars=tuple(moved.get(id(bar), bar) for bar in geometry.bars),
        mounting_bars=tuple(moved.get(id(bar), bar) for bar in geometry.mounting_bars),
    )


def _add_crosstie(ax: "Axes", tie: Crosstie, geometry: SectionGeometry, db_cm: float, bend_cm: float) -> None:
    """One crosstie, drawn as the stirrups are, with its hooks."""
    _band(ax, _crosstie_path(tie, geometry, db_cm, bend_cm), db_cm, "crosstie")


def _plot_stirrups_in_section(ax: "Axes", geometry: SectionGeometry) -> None:
    """Draw every closed stirrup and crosstie of the cage, at the legs the check assumes.

    Each stirrup is drawn on the centrelines of its legs and branches, so its
    outer line sits half a bar outside them: the perimeter stirrup's outer
    line is the cover. No stirrup is drawn on a section that has none.
    """
    d = _cm(geometry.stirrup_d_b)
    bend = _cm(geometry.stirrup_bend_inner_diameter)
    for stirrup in geometry.stirrups:
        x_left, x_right = _cm(stirrup.x_left), _cm(stirrup.x_right)
        y_bottom, y_top = _cm(stirrup.y_bottom), _cm(stirrup.y_top)
        _add_rounded_stirrup(
            ax,
            x0=x_left - d / 2,
            y0=y_bottom - d / 2,
            width=x_right - x_left + d,
            height=y_top - y_bottom + d,
            db_cm=d,
            bend_cm=bend,
            facecolor=CUSTOM_COLORS["light_gray"],
        )
    for tie in geometry.crossties:
        _add_crosstie(ax, tie, geometry, d, bend)


def _plot_bars(ax: "Axes", geometry: SectionGeometry) -> None:
    """Every longitudinal bar, resistant and mounting alike in dark gray; skin bars in green."""
    for bar in (*geometry.bars, *geometry.mounting_bars, *geometry.skin_bars):
        mounting = bar in geometry.mounting_bars
        skin = bar in geometry.skin_bars
        ax.add_patch(
            Circle(
                (_cm(bar.x), _cm(bar.y)),
                _cm(bar.d_b) / 2.0,
                color="#228877" if skin else CUSTOM_COLORS["dark_gray"],
                gid="skin_bar" if skin else "mounting_bar" if mounting else "resistant_bar",
            )
        )


def _with_mounting(self: "RectangularBeam", geometry: SectionGeometry) -> SectionGeometry:
    """The geometry with mounting bars in the corners of any face of the cage that has no bar.

    The detailing places them itself; a drawing that falls back to the
    calculation geometry has none, and a face of stirrups with nothing to
    hold them is not how a cage is built. The bars are ``mounting_bar_diameter``
    (8 mm, No. 3 in US customary units) and, like the detailing's, carry no strength.
    """
    perimeter = next((stirrup for stirrup in geometry.stirrups if stirrup.perimeter), None)
    diameter = _settings(self).mounting_bar_diameter
    # A diameter the detailing rejects (beam.warnings says why) is not drawn either.
    valid = isinstance(diameter, Quantity) and diameter.check("[length]") and math.isfinite(diameter.magnitude)
    if perimeter is None or not valid or diameter < _settings(self).minimum_longitudinal_diameter:
        return geometry
    unit = geometry.width.units
    d_st = _cm(geometry.stirrup_d_b)
    d_m = _cm(_settings(self).mounting_bar_diameter)
    r_in = _cm(geometry.stirrup_bend_inner_diameter) / 2
    # A bar in the corner of the bend, on its inner surface, or against both straight branches.
    inset = d_st / 2 + (r_in - (r_in - d_m / 2) / math.sqrt(2) if r_in > d_m / 2 else d_m / 2)
    added = []
    for face in ("bottom", "top"):
        if any(bar.face == face for bar in (*geometry.bars, *geometry.mounting_bars)):
            continue
        y = _cm(perimeter.y_bottom) + inset if face == "bottom" else _cm(perimeter.y_top) - inset
        for x in (_cm(perimeter.x_left) + inset, _cm(perimeter.x_right) - inset):
            added.append(
                BarPosition(
                    x=(x * ureg.cm).to(unit),
                    y=(y * ureg.cm).to(unit),
                    d_b=_settings(self).mounting_bar_diameter,
                    face=face,
                    layer=1,
                    group=0,
                )
            )
    if not added:
        return geometry
    return replace(geometry, mounting_bars=(*geometry.mounting_bars, *added))


def steel_ratio(self: "RectangularBeam", geometry: Optional[SectionGeometry] = None) -> Quantity:
    """The steel of the section per volume of concrete, in kg/m³ (lb/yd³ in US customary units).

    The longitudinal bars -- resistant, mounting and skin -- by their area, and
    the stirrups by the length of each piece over their spacing along the
    member: a closed stirrup by its centreline perimeter plus two 135° hook
    extensions of 6 d_b (at least 75 mm, ACI 318-19 Table 25.3.2), a crosstie
    or open leg by its height plus two of 6 d_b. Steel weighs 7850 kg/m³.
    """
    geometry = self.section_geometry if geometry is None else geometry
    area_c = _cm(geometry.width) * _cm(geometry.height)
    longitudinal = sum(
        math.pi * _cm(bar.d_b) ** 2 / 4 for bar in (*geometry.bars, *geometry.mounting_bars, *geometry.skin_bars)
    )
    transverse = 0.0
    if geometry.stirrups or geometry.crossties:
        d = _cm(geometry.stirrup_d_b)
        s_l = _cm(self._stirrup_s_l)
        hook = max(6 * d, 7.5)
        length = sum(
            2 * (_cm(st.x_right) - _cm(st.x_left) + _cm(st.y_top) - _cm(st.y_bottom)) + 2 * hook
            for st in geometry.stirrups
        )
        length += sum(_cm(tie.y_top) - _cm(tie.y_bottom) + 2 * 6 * d for tie in geometry.crossties)
        if s_l > 0:
            transverse = math.pi * d**2 / 4 * length / s_l
    ratio: Quantity = (longitudinal + transverse) / area_c * 7850 * ureg.kg / ureg.m**3
    return ratio.to("lb/yd**3") if self.concrete.is_imperial else ratio


def _layer_text(bars: Tuple[BarPosition, ...], imperial: bool = False) -> str:
    """``2Ø16+3Ø10`` for the bars of one layer, from their groups; one group when they share a diameter."""
    groups: Dict[int, List[BarPosition]] = {}
    for bar in bars:
        groups.setdefault(bar.group, []).append(bar)
    counts = [(len(members), members[0].d_b) for _, members in sorted(groups.items())]
    if len(counts) == 2 and counts[0][1] == counts[1][1]:
        counts = [(counts[0][0] + counts[1][0], counts[0][1])]
    return "+".join(f"{n}{bar_designation(d)}" if imperial else f"{n}Ø{d.to('mm').magnitude:.0f}" for n, d in counts)


def _annotate_layers(ax: "Axes", geometry: SectionGeometry) -> List[Tuple["Text", float]]:
    """Write each layer's bars to the right of the section, at the height the bars are drawn.

    Returns each label with the height it belongs at -- the middle of the band
    its bars occupy -- so :func:`_fit_texts` can move labels that would print
    over one another apart, and back to that height when they have room.
    """
    x_text = 1.1 * _cm(geometry.width)
    labels: List[Tuple["Text", float]] = []
    for face in ("bottom", "top"):
        for layer in (1, 2):
            bars = geometry.bars_on(face, layer)
            if not bars:
                continue
            # The middle of the band the layer's bars occupy.
            low = min(_cm(bar.y) - _cm(bar.d_b) / 2 for bar in bars)
            high = max(_cm(bar.y) + _cm(bar.d_b) / 2 for bar in bars)
            anchor = (low + high) / 2
            label = ax.text(
                x_text,
                anchor,
                _layer_text(bars, is_us_customary(geometry.width)),
                ha="left",
                va="center",
                color=CUSTOM_COLORS["dark_gray"],
            )
            labels.append((label, anchor))
        mounting = tuple(bar for bar in geometry.mounting_bars if bar.face == face)
        if mounting:
            anchor = sum(_cm(bar.y) for bar in mounting) / len(mounting)
            suffix = translate("mounting")
            label = ax.text(
                x_text,
                anchor,
                f"{_layer_text(mounting, is_us_customary(geometry.width))} ({suffix})",
                ha="left",
                va="center",
                color=CUSTOM_COLORS["dark_gray"],
            )
            labels.append((label, anchor))
    skin = tuple(bar for bar in geometry.skin_bars if bar.face == "left")
    if skin:
        anchor = sum(_cm(bar.y) for bar in skin) / len(skin)
        label = ax.text(
            x_text,
            anchor,
            translate("{bars} per side (skin)", bars=_layer_text(skin, is_us_customary(geometry.width))),
            ha="left",
            va="center",
            color=CUSTOM_COLORS["dark_gray"],
        )
        labels.append((label, anchor))
    return labels


def _annotate_stirrups(ax: "Axes", self: "RectangularBeam", geometry: SectionGeometry) -> List[Tuple["Text", float]]:
    """The stirrups, legs first (``2 legs Ø10 mm @ 22 cm``), to the right of the section at mid-height."""
    if not geometry.stirrups:
        return []
    anchor = _cm(geometry.height) / 2
    label = ax.text(
        1.1 * _cm(geometry.width),
        anchor,
        self.reinforcement.transverse.notation(),
        ha="left",
        va="center",
        color=CUSTOM_COLORS["dark_gray"],
        gid="stirrup_text",
    )
    return [(label, anchor)]


def _spread(anchors: Sequence[float], pitch: float) -> List[float]:
    """Positions for ``anchors`` (ascending), in their order, each as near its anchor as ``pitch`` apart allows.

    Labels that would come closer than ``pitch`` are merged into a group,
    centred on the mean of their anchors and laid out ``pitch`` apart; groups
    merge again until none overlaps the next. Labels with room stay at their
    anchors.
    """
    groups: List[List[float]] = [[anchor] for anchor in anchors]

    def placed(group: List[float]) -> List[float]:
        start = sum(group) / len(group) - pitch * (len(group) - 1) / 2
        return [start + k * pitch for k in range(len(group))]

    merged = True
    while merged:
        merged = False
        for j in range(len(groups) - 1):
            if placed(groups[j])[-1] + pitch > placed(groups[j + 1])[0] + 1e-9:
                groups[j : j + 2] = [groups[j] + groups[j + 1]]
                merged = True
                break
    return [y for group in groups for y in placed(group)]


def _separate_labels(ax: "Axes", labels: Sequence[Tuple["Text", float]]) -> None:
    """Move the layer labels apart where two would print over one another, at the current scale."""
    if len(labels) < 2:
        return
    to_points = 72.0 / cast(Figure, ax.figure).dpi
    ordered = sorted(labels, key=lambda pair: pair[1])
    anchors = [ax.transData.transform((0.0, anchor))[1] * to_points for _, anchor in ordered]
    pitch = max(label.get_window_extent().height for label, _ in ordered) * to_points + 1.0
    inverse = ax.transData.inverted()
    for (label, _), y_points in zip(ordered, _spread(anchors, pitch)):
        label.set_y(inverse.transform((0.0, y_points / to_points))[1])


def _fit_texts(ax: "Axes", labels: Sequence[Tuple["Text", float]] = (), margin_pt: float = 3.0) -> None:
    """Keep every text of the drawing inside the axes, and the layer labels off one another.

    The texts are sized in points and the section in cm, so how much room they
    take depends on the scale, which the limits set. Each round separates the
    layer labels at the current scale and, if some text still reaches past
    the axes, widens the limits to take it; with the aspect fixed that
    shrinks the scale, so a few rounds settle it. The drawing then fits the
    figure at its default size, with no ``bbox_inches="tight"`` needed.
    """
    for _ in range(32):
        ax.apply_aspect()
        _separate_labels(ax, labels)
        extents = [text.get_window_extent() for text in ax.texts if text.get_text()]
        pad = margin_pt * cast(Figure, ax.figure).dpi / 72.0
        union = Bbox.union(extents)
        need = Bbox.from_extents(union.x0 - pad, union.y0 - pad, union.x1 + pad, union.y1 + pad)
        box = ax.get_window_extent()
        if box.x0 <= need.x0 and box.y0 <= need.y0 and need.x1 <= box.x1 and need.y1 <= box.y1:
            return
        (x0, y0), (x1, y1) = ax.transData.inverted().transform([(need.x0, need.y0), (need.x1, need.y1)])
        (x_min, x_max), (y_min, y_max) = ax.get_xlim(), ax.get_ylim()
        ax.set_xlim(min(x_min, x0), max(x_max, x1))
        ax.set_ylim(min(y_min, y0), max(y_max, y1))


def _crop_figure(fig: Figure, ax: "Axes") -> None:
    """Shrink the figure to the drawing, at the scale it was fitted at.

    With the aspect fixed the axes keep the shape of the drawing and leave the
    rest of the figure blank; the figure takes the size of the axes instead,
    and the axes all of it, so no margin is left around the section.
    """
    ax.apply_aspect()
    box = ax.get_position()
    width, height = fig.get_size_inches()
    fig.set_size_inches(width * box.width, height * box.height)
    ax.set_position((0.0, 0.0, 1.0, 1.0))


#: Line pitch of the stirrup text under the section, in points.
_LINE_PT = 14.0


def _annotate_cage_text(ax: "Axes", lines: Sequence[str], gid: str = "steel_ratio") -> None:
    """Text under the section, one artist per line, below its width: the steel ratio of a beam.

    The lines start at the left face of the section, one line under the
    width dimension, and are stacked a fixed pitch in points apart, so they
    read the same at any section size; the limits of the drawing are then
    widened to take them (:func:`_fit_texts`).
    """
    y_anchor = 0.0
    offset = 34.0
    for line in lines:
        line = textwrap.fill(line, width=58, break_long_words=False)
        ax.annotate(
            line,
            xy=(0.0, y_anchor),
            xytext=(0, -offset),
            textcoords="offset points",
            ha="left",
            va="top",
            color=CUSTOM_COLORS["dark_gray"],
            gid=gid,
        )
        offset += _LINE_PT * (line.count("\n") + 1) + 2.0


#: How far the dimension lines and their text sit off the section, in cm.
_DIM_OFFSET_CM = 2.5
_TEXT_OFFSET_CM = _DIM_OFFSET_CM + 2


def _dimensions(self: "RectangularBeam", width_cm: float, height_cm: float) -> None:
    """The width and height of the section, with their arrows."""
    dim_offset = _DIM_OFFSET_CM
    # Add width dimension
    _axes(self).annotate(
        "",  # No text here, text is added separately
        xy=(0, -dim_offset),  # Start of arrow (left side)
        xytext=(width_cm, -dim_offset),  # End of arrow (right side)
        arrowprops={
            "arrowstyle": "<->",
            "lw": 1,
            "color": CUSTOM_COLORS["dark_blue"],
        },
    )
    if self.concrete.unit_system == "imperial":
        # Example: format to 2 decimal places, then use pint's compact (~P) format
        width = "{:.0f~P}".format(self.width.to("inch"))
        height = "{:.0f~P}".format(self.height.to("inch"))
    else:
        width = "{:.0f~P}".format(self.width.to("cm"))
        height = "{:.0f~P}".format(self.height.to("cm"))
    # Add width dimension text below the arrow
    _axes(self).annotate(
        width,
        xy=(width_cm / 2, 0),
        xytext=(0, -20),
        textcoords="offset points",
        ha="center",
        va="top",
        color=CUSTOM_COLORS["dark_gray"],
    )

    # Add height dimension
    _axes(self).annotate(
        "",  # No text here, text is added separately
        xy=(-dim_offset, 0),  # Start of arrow (bottom)
        xytext=(-dim_offset, height_cm),  # End of arrow (top)
        arrowprops={
            "arrowstyle": "<->",
            "lw": 1,
            "color": CUSTOM_COLORS["dark_blue"],
        },
    )
    # Add height dimension text to the left of the arrow
    _axes(self).annotate(
        height,
        xy=(0, height_cm / 2),
        xytext=(-24, 0),
        textcoords="offset points",
        ha="right",
        va="center",
        color=CUSTOM_COLORS["dark_gray"],
        rotation=90,  # Rotate text vertically
    )


def _plot_grid_section(self: "RectangularBeam", width_cm: float, height_cm: float) -> None:
    """A slab strip's bars and grid label, drawn as they always were.

    A strip is detailed by spacing and has no cage, so its geometry publishes
    no bars (see :mod:`mento.section_geometry`); it keeps the whole bars that
    cover the strip and its ``Ø10/8×15`` label.
    """
    c_c_cm: float = self.c_c.to("cm").magnitude
    stirrup_d_b_cm: float = self._stirrup_d_b.to("cm").magnitude
    layers_spacing_cm: float = _settings(self).layers_spacing.to("cm").magnitude
    faces = (
        (
            True,
            (self._n1_b, self._d_b1_b, self._n2_b, self._d_b2_b),
            (self._n3_b, self._d_b3_b, self._n4_b, self._d_b4_b),
        ),
        (
            False,
            (self._n1_t, self._d_b1_t, self._n2_t, self._d_b2_t),
            (self._n3_t, self._d_b3_t, self._n4_t, self._d_b4_t),
        ),
    )
    for is_bottom, first, second in faces:
        for layer, second_layer in ((first, False), (second, True)):
            _plot_rebar_layer(
                self,
                width_cm,
                height_cm,
                c_c_cm,
                stirrup_d_b_cm,
                layers_spacing_cm,
                *layer,
                max_db=first[1],
                is_bottom=is_bottom,
                is_second_layer=second_layer,
            )
    for is_bottom, first, second in faces:
        for layer, second_layer in ((first, False), (second, True)):
            _annotate_rebar_layer_text(
                self,
                width_cm,
                height_cm,
                c_c_cm,
                stirrup_d_b_cm,
                layers_spacing_cm,
                *layer,
                max_db=first[1],
                is_bottom=is_bottom,
                is_second_layer=second_layer,
            )
    _annotate_stirrups_text(self, width_cm, height_cm)


def plot_beam_section(self: "RectangularBeam", show: bool = False) -> Figure:
    """
    Plots the rectangular section with a dark gray border, light gray hatch, and dimensions.

    A beam is drawn from its :attr:`~mento.beam.RectangularBeam.detailing_geometry`:
    every stirrup of the cage at the legs the shear check assumes, crossties
    with their 90° and 135° hooks around the bars they hold, and the
    longitudinal bars -- resistant and mounting alike in dark gray, skin bars
    in green. On the right, the label of each layer, the skin per side and
    the stirrups (``2 legs Ø10 mm @ 22 cm``); under the section, the steel
    ratio in kg/m³ (lb/yd³ in US customary units, :func:`steel_ratio`). A
    face of the cage with no bars gets mounting bars at its corners. The
    limits are widened until every text fits, and the figure is cropped to
    the drawing. A slab strip keeps the drawing it always had.

    Nothing that still needs checking is written on the drawing, and the
    drawing warns nothing: a cage that cannot be detailed is drawn as the
    calculation assumes it, and that and every pending check of the cage
    and the skin are read in :attr:`~mento.beam.RectangularBeam.warnings`.
    """

    # Convert dimensions to consistent units (cm)
    width_cm: float = self.width.to("cm").magnitude
    height_cm: float = self.height.to("cm").magnitude

    # Create figure and axis
    fig, self._ax = plt.subplots()
    ax = _axes(self)

    # Create a rectangle patch for the section
    rect = Rectangle(
        (0, 0),
        width_cm,
        height_cm,
        linewidth=1.3,
        edgecolor=CUSTOM_COLORS["dark_gray"],
        facecolor=CUSTOM_COLORS["light_gray"],
    )
    ax.add_patch(rect)

    # A layout the detailing cannot build is drawn as the calculation assumes it,
    # and said in beam.warnings, not on the drawing.
    detail_error = None
    try:
        geometry = self.detailing_geometry
    except CageDetailingError as error:
        geometry = self.section_geometry
        detail_error = error
        if error.reason == "skin":
            from mento.cage_detailing import build_cage_detailing

            try:
                geometry = build_cage_detailing(self, include_skin=False)
            except CageDetailingError as base_error:
                detail_error = base_error
    if geometry.layout != GRID:
        geometry = _align_bars_to_ties(_with_mounting(self, geometry))
    if geometry.layout != GRID and (detail_error is None or detail_error.reason != "bend"):
        _plot_stirrups_in_section(ax, geometry)

    # Room for the dimension lines; the texts widen the limits as they need (_fit_texts).
    padding = _DIM_OFFSET_CM + 1.0
    ax.set_xlim(-padding, width_cm + padding)
    ax.set_ylim(-padding, height_cm + padding)

    _dimensions(self, width_cm, height_cm)

    # Set aspect of the plot to be equal
    ax.set_aspect("equal")
    # Remove axes for better visualization
    ax.axis("off")

    labels: List[Tuple["Text", float]] = []
    if geometry.layout == GRID:
        _plot_grid_section(self, width_cm, height_cm)
    else:
        _plot_bars(ax, geometry)
        labels = _annotate_layers(ax, geometry) + _annotate_stirrups(ax, self, geometry)
        unit = "lb/yd³" if self.concrete.is_imperial else "kg/m³"
        ratio = steel_ratio(self, geometry)
        _annotate_cage_text(ax, [translate("Steel: {ratio}", ratio=f"{ratio.magnitude:.0f} {unit}")])
    _fit_texts(ax, labels)
    _crop_figure(fig, ax)

    # Store the section figure
    self._fig = fig

    if show:
        plt.show()

    # # Close the figure so notebooks don't auto-display it twice
    plt.close(fig)

    return fig
