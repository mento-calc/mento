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
import warnings
from typing import TYPE_CHECKING, Dict, List, Optional, Sequence, Tuple, cast

import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.patches import Circle, FancyBboxPatch, Rectangle
from matplotlib.transforms import Bbox

from mento.bar_sizes import bar_designation, is_us_customary
from mento.cage_detailing import CageDetailingError
from mento.codes.registry import design_code
from mento.design_results import (
    GRID,
    DesignNotRunError,
    ShearDesign,
    TransverseReinforcement,
    format_transverse_rebar,
    placed_bars,
)
from mento.i18n import get_language, translate
from mento.precompute import DISPLAY
from mento.results import CUSTOM_COLORS
from mento.section_geometry import BarPosition, Crosstie, SectionGeometry
from mento.units import Quantity

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


def _add_crosstie(ax: "Axes", tie: Crosstie, db_cm: float) -> None:
    """Rama recta y, si están modelados, arcos y colas tangentes de los ganchos.

    ``gid="crosstie"`` identifica el tramo recto. Los ángulos manuales sin
    mandril ni cola conservan sus marcas gráficas, sin crédito de sujeción.
    """
    x, y_bottom, y_top = _cm(tie.x), _cm(tie.y_bottom), _cm(tie.y_top)
    modelled = tie.bend_inner_diameter is not None and tie.extension is not None
    if modelled:
        assert tie.bend_inner_diameter is not None
        radius = (_cm(tie.bend_inner_diameter) + db_cm) / 2
        y_bottom += radius
        y_top -= radius
    leg = Rectangle(
        (x - db_cm / 2, y_bottom - db_cm / 2),
        db_cm,
        y_top - y_bottom + db_cm,
        facecolor=CUSTOM_COLORS["dark_blue"],
        edgecolor=CUSTOM_COLORS["dark_blue"],
        gid="crosstie",
    )
    ax.add_patch(leg)
    if modelled:
        from mento.crosstie_detailing import hook_points
        from mento.units import cm

        for path in hook_points(tie, db_cm * cm):
            ax.plot(
                [x / 10 for x, _ in path],
                [y / 10 for _, y in path],
                color=CUSTOM_COLORS["dark_blue"],
                linewidth=db_cm,
                gid="crosstie_hook",
            )
        return
    stub = 4 * db_cm
    for (y_end, sign), angle in zip(((y_bottom, 1), (y_top, -1)), tie.hooks):
        radians = math.radians(180 - angle)
        ax.plot(
            [x, x + stub * math.sin(radians)],
            [y_end, y_end + sign * stub * math.cos(radians)],
            color=CUSTOM_COLORS["dark_blue"],
            linewidth=db_cm,
            gid="crosstie_hook",
        )


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
        _add_crosstie(ax, tie, d)


def _plot_bars(ax: "Axes", geometry: SectionGeometry) -> None:
    """Resistant steel in gray; supplementary mounting bars in orange."""
    for bar in (*geometry.bars, *geometry.mounting_bars, *geometry.skin_bars):
        mounting = bar in geometry.mounting_bars
        skin = bar in geometry.skin_bars
        ax.add_patch(
            Circle(
                (_cm(bar.x), _cm(bar.y)),
                _cm(bar.d_b) / 2.0,
                color="#228877" if skin else CUSTOM_COLORS["mounting"] if mounting else CUSTOM_COLORS["dark_gray"],
                fill=not mounting,
                gid="skin_bar" if skin else "mounting_bar" if mounting else "resistant_bar",
            )
        )


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
                color=CUSTOM_COLORS["mounting"],
            )
            labels.append((label, anchor))
    return labels


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


#: Line pitch of the stirrup text under the section, in points.
_LINE_PT = 14.0


def _annotate_cage_text(ax: "Axes", lines: Sequence[str]) -> None:
    """The stirrup text, one artist per line, under the section, below its width.

    ``lines`` are the two lines of the notation and the arrangement of the
    cage. They start at the left face of the section, one line under the
    width dimension, and are stacked a fixed pitch in points apart, so they
    read the same at any section size. Under the section they are clear of
    the layer labels on its right, however shallow the section is; the
    limits of the drawing are then widened to take them (:func:`_fit_texts`).
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
            gid="stirrup_text",
        )
        offset += _LINE_PT * (line.count("\n") + 1) + 2.0


def _cage_lines(self: "RectangularBeam", geometry: Optional[SectionGeometry] = None) -> List[str]:
    """The stirrup text of a beam: its notation on two lines and the cage, in the current language.

    The notation of the last shear check, with the limit the legs were held
    to, when one has run on the section as it is; the configuration otherwise.
    """
    if self._stirrup_n == 0:
        return []
    geometry = self.section_geometry if geometry is None else geometry
    transverse = self.reinforcement.transverse
    source: ShearDesign | TransverseReinforcement
    try:
        source = self.shear_design
    except DesignNotRunError:
        source = transverse
    # Encabezar con la armadura verificada, nunca con acero extra de propuesta.
    notation = source.notation(separator="\n")
    lines = [*notation.split("\n"), geometry.arrangement()]
    if len(geometry.leg_x) != transverse.n_legs:
        lines.append(
            translate(
                "{placed} proposed legs; A_v uses {entered}. Compression support: {status}.",
                placed=len(geometry.leg_x),
                entered=transverse.n_legs,
                status=translate(self.compression_detailing.status),
            )
        )
    if any(t.alternate_hooks and t.extension is not None for t in geometry.crossties):
        lines.append(
            translate("135°/90° crossties: alternate the 90° ends along the member; seismic detailing not verified.")
        )
    if any(t.extension is None for t in geometry.crossties):
        lines.append(
            translate("Open-leg hooks and anchorage are outside this sectional model; verify them separately.")
        )
    return lines


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
    every stirrup of the cage at the legs the shear check assumes, resistant
    bars at supported cage corners, supplementary mounting bars in orange,
    the label of each layer on the
    right, and the stirrup text in three lines under the section -- the legs,
    bar and spacing; the spacing of the legs across the width with its
    maximum; and the arrangement of the cage. The limits are then widened
    until every text fits inside the figure at its default size. A slab
    strip keeps the drawing it always had. If no supported layout is found,
    a warning and a figure caption explicitly identify calculation geometry.
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
                warnings.warn(
                    f"Cage detailing is not feasible: {str(base_error).rstrip('.')}. Showing calculation geometry only.",
                    UserWarning,
                    stacklevel=2,
                )
            warnings.warn(
                f"Skin detailing is not feasible: {str(error).rstrip('.')}. Showing the available base geometry without skin steel.",
                UserWarning,
                stacklevel=2,
            )
        else:
            warnings.warn(
                f"Cage detailing is not feasible: {str(error).rstrip('.')}. Showing calculation geometry only.",
                UserWarning,
                stacklevel=2,
            )
    if geometry.layout != GRID and (detail_error is None or detail_error.reason != "bend"):
        _plot_stirrups_in_section(ax, geometry)

    # Set plot limits with some padding
    padding = max(width_cm, height_cm) * 0.2
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
        labels = _annotate_layers(ax, geometry)
        lines = _cage_lines(self, geometry)
        if geometry.mounting_bars:
            lines.append(
                "Montaje en naranja · sin aporte resistente"
                if get_language() == "es"
                else "Orange: mounting steel · excluded from resistance"
            )
        if geometry.skin_bars:
            skin = self.skin_reinforcement
            assert skin.spacing is not None
            unit = "inch" if self.concrete.is_imperial else "cm"
            notation = _layer_text(tuple(b for b in geometry.skin_bars if b.face == "left"), self.concrete.is_imperial)
            lines.append(
                f"Piel: {notation} por lateral · s={skin.spacing.to(unit):.3g~P} · sin aporte resistente"
                if get_language() == "es"
                else f"Skin: {notation} per side · s={skin.spacing.to(unit):.3g~P} · excluded from resistance"
            )
            # All service cases remain in the requirement and warnings; keep
            # the figure readable by labelling the largest interval per face.
            for face in dict.fromkeys(review.tension_face for review in skin.distribution_reviews):
                review = max(
                    (r for r in skin.distribution_reviews if r.tension_face == face), key=lambda r: r.maximum_interval
                )
                lines.append(
                    translate(
                        "Review skin ({face}): {rows} rows · max interval {gap}",
                        face=translate(face.capitalize()),
                        rows=review.rows_per_side,
                        gap=f"{review.maximum_interval.to(unit):.3g~P}",
                    )
                )
            if skin.distribution_reviews:
                lines.append(translate("Informative review · crack width is not calculated"))
        try:
            pending_requirement = self.skin_reinforcement
            if pending_requirement.manual and pending_requirement.failures:
                lines.append(
                    translate(
                        "Supplied skin does not comply: {reason}",
                        reason="; ".join(translate(reason) for reason in pending_requirement.failures),
                    )
                )
            skin_pending = pending_requirement.status == "pending"
            skin_unsupported = pending_requirement.status == "unsupported"
            service_pending = pending_requirement.pending_reason == "service"
            tension_case_pending = pending_requirement.pending_reason == "no_tension_case"
        except CageDetailingError:
            skin_pending = False
            skin_unsupported = False
            service_pending = False
            tension_case_pending = False
        if skin_unsupported:
            lines.append(translate("Skin not checked · unsupported design case"))
        elif skin_pending and tension_case_pending:
            lines.append(
                "Armadura de piel pendiente · sin caso de tracción identificado"
                if get_language() == "es"
                else "Skin reinforcement pending · no tension case identified"
            )
        elif skin_pending and service_pending:
            lines.append(
                "Piel EN pendiente · faltan datos de servicio"
                if get_language() == "es"
                else "EN skin pending · service inputs missing"
            )
        elif skin_pending:
            lines.append(
                "Armadura de piel pendiente · sin verificación de flexión"
                if get_language() == "es"
                else "Skin reinforcement pending · no flexure verification"
            )
        if detail_error:
            lines.append(
                translate("Skin proposal not shown · skin detailing not feasible")
                if detail_error.reason == "skin"
                else translate("Calculation model only · cage detailing not feasible")
            )
        if geometry.stirrups and design_code(self.concrete).max_bar_spacing_tension is not None:
            try:
                self.flexure_design
            except DesignNotRunError:
                lines.append(translate("Tension-bar spacing pending · no flexure verification"))
        compression = self.compression_detailing
        if compression.status in ("failed", "pending") and compression.reason != "flexure_not_checked":
            lines.append(translate("Required compression-bar support: {status}", status=translate(compression.status)))
            warnings.warn("Required compression-bar support: " + compression.status, UserWarning, stacklevel=2)
        _annotate_cage_text(ax, lines)
    _fit_texts(ax, labels)

    # Store the section figure
    self._fig = fig

    if show:
        plt.show()

    # # Close the figure so notebooks don't auto-display it twice
    plt.close(fig)

    return fig
