"""Where the bars and the stirrup legs of a section are, as data.

The shear and flexure checks never place a bar or a leg: they reason with a
clear distance between bars, an effective depth, and a spacing of the legs
across the width. This module turns that model into positions, so that a
drawing -- mento's own ``beam.plot()`` or any other -- can show the section the
check assumed without deriving anything again::

    geometry = beam.section_geometry
    geometry.leg_x            # centrelines of the stirrup legs, left to right
    geometry.stirrups         # the closed stirrups, perimeter first
    geometry.bars_on("bottom", layer=1)

Each position is the check's own model, and a test ties each one to it:

- **Legs**: ``n_legs = 2·n_stirrups`` legs spread evenly between the centres
  of the outermost pair, ``x_i = c_c + d_st/2 + i·s_w`` with
  ``s_w = (b - 2·c_c - d_st)/(n_legs - 1)`` -- the ``s_w`` the check holds to
  Table 9.7.6.2.2 (Expression (9.8N) under EN 1992-1-1).
- **Cage**: one perimeter closed stirrup on the outermost legs and the
  remaining open legs. The detailing layer proposes 135°/90° crossties
  when required compression-bar support needs them. Leg indices in
  :attr:`ClosedStirrup.legs` count from 0 (see
  :func:`mento.design_results.cage_legs`).
- **Bars**: each layer spread evenly between the inner faces of the outer
  legs, one clear distance apart -- the clear spacing the check reads
  (``_layer_clear_spacing``) -- with the first bar's face at ``c_c + d_st``
  and the last at ``b - c_c - d_st``; a layer of one bar at mid-width. The
  groups of a layer (``n1``/``n2``, ``n3``/``n4``) alternate symmetrically:
  the ``n1`` bars at the ends, the ``n2`` bars in between. Layer 1 sits at
  ``c_c + d_st + d/2`` from its face, layer 2 at
  ``c_c + d_st + max(d_b1, d_b2) + layers_spacing + d/2``, the offsets the
  effective depth is computed with.

The legs are not tied to the bars: the check does not do that either, so an
inner leg may sit where no bar is. That is the model, shown honestly.

A slab strip (``OneWaySlab``, ``Footing``) is detailed by spacings, not by a
count of bars in a cage: its bars per strip are ``width / s`` and need not be
whole, and it has no cage. Its geometry publishes the section, the cover, the
stirrup diameter and ``s_w``, with no bars and no legs, rather than positions
that would contradict its own ``Ø10/14`` label.

Calculation layer: no drawing library is imported here. The section is read
once through its float view (ADR-0005) and the lengths are wrapped into pint
on the way out, in the display unit of the section (cm, or in).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence, Tuple

from mento.codes.registry import design_code
from mento.design_results import GRID, cage_legs, describe_stirrup_cage, transverse_layout
from mento.i18n import checked_language
from mento.precompute import CANONICAL, DISPLAY, section_floats
from mento.units import Quantity, ureg

if TYPE_CHECKING:
    from mento.beam import RectangularBeam


@dataclass(frozen=True)
class BarPosition:
    """One longitudinal bar: its centre and its diameter.

    Skin bars use face="left"/"right" and layer=group=0.
    ``x`` is measured from the left face of the section and ``y`` from its
    bottom face. ``face`` is ``"bottom"`` or ``"top"``; ``layer`` is 1 for the
    layer nearest that face and 2 for the one behind it; ``group`` is the
    ``n1``..``n4`` / ``d_b1``..``d_b4`` the bar was set with.
    """

    x: Quantity
    y: Quantity
    d_b: Quantity
    face: str
    layer: int
    group: int


@dataclass(frozen=True)
class ClosedStirrup:
    """One closed stirrup, by the centrelines of its branches.

    ``legs`` are the 0-based indices, into :attr:`SectionGeometry.leg_x`, of
    its left and right legs. ``perimeter`` is True for the one that spans the
    whole section.
    """

    legs: Tuple[int, int]
    x_left: Quantity
    x_right: Quantity
    y_bottom: Quantity
    y_top: Quantity
    perimeter: bool


@dataclass(frozen=True)
class Crosstie:
    """Geometry container for a manually supplied tie.

    Plain open legs have no compression-support credit. Hook angles alone
    are drawing data. A generated crosstie additionally records mandrel,
    extension, engaged peripheral bars and required longitudinal alternation.
    """

    leg: int
    x: Quantity
    y_bottom: Quantity
    y_top: Quantity
    hooks: Tuple[int, ...] = ()
    # Propuesta seccional de traba; ángulos solos siguen siendo datos gráficos.
    bend_inner_diameter: Optional[Quantity] = None
    extension: Optional[Quantity] = None
    side: int = 1
    engaged_bars: Tuple[BarPosition, ...] = ()
    alternate_hooks: bool = False


@dataclass(frozen=True)
class SectionGeometry:
    """The section as the checks assume it, with every length a quantity.

    The origin is the bottom-left corner of the section, ``x`` across the
    width and ``y`` up. Lengths are in the display unit of the section: cm,
    or in on a US customary one.

    ``layout`` is how the section carries its transverse reinforcement, as
    :func:`mento.design_results.transverse_layout` says:
    ``"stirrups"`` (:data:`~mento.design_results.STIRRUPS`) for a beam's cage
    of closed stirrups, ``"grid"`` (:data:`~mento.design_results.GRID`) for a
    slab strip, which publishes no legs and no bars.

    ``stirrup_d_b`` is the stirrup the effective depth and the clear space of
    the bars are computed with -- also on a section with no stirrups placed,
    which still reserves the diameter it starts from -- so ``c_c +
    stirrup_d_b`` is where the check puts the faces of the bars.
    ``stirrup_bend_inner_diameter`` is the inside diameter the drawing bends
    the stirrups with, supplied by the registered code: ACI/CIRSOC Table
    25.3.2 (4 or 6 diameters), EN §8.3(2) Table 8.1N (4 or 7). It does not
    verify anchorage, hooks or concrete failure at bends (EN Eq. 8.1).
    ``bend_supported=False`` marks a non-normative 4*d_st calculation
    placeholder, also exported by ``to_dict()``.
    ``s_w`` is the spacing of the legs across the width the
    shear check reads.

    ``leg_x`` holds the centrelines of the legs of the cage, left to right,
    and ``len(leg_x)`` is the number of legs drawn; the shear model's count is
    ``beam.reinforcement.transverse.n_legs`` -- calculation geometry matches that count; detailing can propose extra closed legs, while a
    slab strip, which has no cage, publishes none (see the module docstring).
    ``stirrups`` come perimeter first, and ``bars`` bottom layer 1, bottom
    layer 2, top layer 1, top layer 2, each left to right.

    ``mounting_bars`` is empty in calculation geometry. ``detailing_geometry``
    supplies supplementary corner supports there, separate from ``bars`` and
    excluded from ``bars_on()`` and the calculated reinforcement areas.
    """

    width: Quantity
    height: Quantity
    c_c: Quantity
    layout: str
    stirrup_d_b: Quantity
    stirrup_bend_inner_diameter: Quantity
    s_w: Quantity
    leg_x: Tuple[Quantity, ...]
    stirrups: Tuple[ClosedStirrup, ...]
    crossties: Tuple[Crosstie, ...]
    bars: Tuple[BarPosition, ...]
    # Supplementary steel supplied by beam.detailing_geometry, never counted
    # in bars_on(), the resistant steel areas or the moment resistance.
    mounting_bars: Tuple[BarPosition, ...] = ()
    # False marks a 4*d_st calculation placeholder, not a code mandrel.
    bend_supported: bool = True
    # En la propuesta pueden agregarse ramas, sin alterar la geometría de cálculo.
    input_legs: Optional[int] = None
    calculation_s_w: Optional[Quantity] = None
    # Supplementary longitudinal skin steel; face=left/right, layer=group=0.
    # Excluded from bars_on() and all calculated steel areas/capacities.
    skin_bars: Tuple[BarPosition, ...] = ()

    def arrangement(self, language: Optional[str] = None) -> str:
        """The cage in words (see :func:`mento.design_results.describe_stirrup_cage`); empty on a slab strip."""
        checked_language(language)
        if self.layout == GRID:
            return ""
        from mento.i18n import translate

        if not self.stirrups:
            return describe_stirrup_cage(0, language)
        if len(self.stirrups) == 1 and not self.crossties:
            return translate("single perimeter stirrup", language)
        parts = [translate("perimeter stirrup", language)]
        inner = len(self.stirrups) - 1
        if inner:
            parts.append(
                translate("1 inner stirrup", language)
                if inner == 1
                else translate("{n} inner stirrups", language, n=inner)
            )
        if self.crossties:
            modelled = sum(t.extension is not None for t in self.crossties)
            for count, singular, plural in (
                (modelled, "1 crosstie", "{n} crossties"),
                (len(self.crossties) - modelled, "1 open leg", "{n} open legs"),
            ):
                if count:
                    parts.append(translate(singular, language) if count == 1 else translate(plural, language, n=count))
        return " + ".join(parts)

    def bars_on(self, face: str, layer: Optional[int] = None) -> Tuple[BarPosition, ...]:
        """The bars on ``face`` (``"bottom"`` or ``"top"``), of one ``layer`` or of both."""
        return tuple(bar for bar in self.bars if bar.face == face and (layer is None or bar.layer == layer))

    def to_dict(self, unit: Optional[str] = None) -> Dict[str, Any]:
        """The geometry as plain floats in ``unit``, for a consumer that does not speak pint.

        ``input_legs`` and ``calculation_s_w`` identify the unchanged calculation;
        ``placed_legs`` and ``s_w`` describe this geometry, possibly a proposal.
        The keys are the field names, each length a float in ``unit``, plus
        ``"unit"`` (the unit given) and ``"layout"`` (``"stirrups"`` or
        ``"grid"``). ``stirrups``, ``crossties`` and ``bars`` are lists of
        dicts with the fields of :class:`ClosedStirrup`, :class:`Crosstie` and
        :class:`BarPosition`; leg indices count from 0, as in ``leg_x``. No
        text depends on the language: the words are :meth:`arrangement`'s.
        With no unit supplied, lengths use the section's display unit (cm or in).
        """
        if unit is None:
            unit = f"{self.width.units:~}"

        def f(value: Quantity) -> float:
            return float(value.to(unit).magnitude)

        return {
            "unit": unit,
            "layout": self.layout,
            "width": f(self.width),
            "height": f(self.height),
            "c_c": f(self.c_c),
            "stirrup_d_b": f(self.stirrup_d_b),
            "stirrup_bend_inner_diameter": f(self.stirrup_bend_inner_diameter),
            "bend_supported": self.bend_supported,
            "s_w": f(self.s_w),
            "input_legs": len(self.leg_x) if self.input_legs is None else self.input_legs,
            "placed_legs": len(self.leg_x),
            "calculation_s_w": f(self.s_w if self.calculation_s_w is None else self.calculation_s_w),
            "leg_x": [f(x) for x in self.leg_x],
            "stirrups": [
                {
                    "legs": list(stirrup.legs),
                    "x_left": f(stirrup.x_left),
                    "x_right": f(stirrup.x_right),
                    "y_bottom": f(stirrup.y_bottom),
                    "y_top": f(stirrup.y_top),
                    "perimeter": stirrup.perimeter,
                }
                for stirrup in self.stirrups
            ],
            "crossties": [
                {
                    "leg": tie.leg,
                    "x": f(tie.x),
                    "y_bottom": f(tie.y_bottom),
                    "y_top": f(tie.y_top),
                    "hooks": list(tie.hooks),
                    "bend_inner_diameter": None if tie.bend_inner_diameter is None else f(tie.bend_inner_diameter),
                    "extension": None if tie.extension is None else f(tie.extension),
                    "side": tie.side,
                    "alternate_hooks": tie.alternate_hooks,
                    "engaged_bars": [
                        {"face": bar.face, "layer": bar.layer, "x": f(bar.x), "y": f(bar.y), "d_b": f(bar.d_b)}
                        for bar in tie.engaged_bars
                    ],
                }
                for tie in self.crossties
            ],
            "bars": [
                {
                    "x": f(bar.x),
                    "y": f(bar.y),
                    "d_b": f(bar.d_b),
                    "face": bar.face,
                    "layer": bar.layer,
                    "group": bar.group,
                }
                for bar in self.bars
            ],
            "mounting_bars": [
                {
                    "x": f(bar.x),
                    "y": f(bar.y),
                    "d_b": f(bar.d_b),
                    "face": bar.face,
                    "layer": bar.layer,
                    "group": bar.group,
                }
                for bar in self.mounting_bars
            ],
            "skin_bars": [
                {
                    "x": f(bar.x),
                    "y": f(bar.y),
                    "d_b": f(bar.d_b),
                    "face": bar.face,
                    "layer": bar.layer,
                    "group": bar.group,
                }
                for bar in self.skin_bars
            ],
        }


def _cage(
    leg_x: Sequence[float], y_bottom: float, y_top: float
) -> Tuple[List[Tuple[Tuple[int, int], float, float, float, float, bool]], List[Tuple[int, float, float, float]]]:
    """The closed stirrups and crossties of legs at ``leg_x``, in floats.

    ``([(legs, x_left, x_right, y_bottom, y_top, perimeter)], [(leg, x, y_bottom, y_top)])``,
    from :func:`mento.design_results.cage_legs`: the perimeter stirrup first,
    every one of them the full height between ``y_bottom`` and ``y_top``.
    """
    stirrups, crossties = cage_legs(len(leg_x))
    closed = [
        (pair, leg_x[pair[0]], leg_x[pair[1]], y_bottom, y_top, index == 0) for index, pair in enumerate(stirrups)
    ]
    ties = [(leg, leg_x[leg], y_bottom, y_top) for leg in crossties]
    return closed, ties


def _group_order(n_a: int, n_b: int) -> List[int]:
    """The order of the bars of a layer across the width, as 1 (group a) and 2 (group b).

    Symmetric wherever the counts allow: the ``n_a`` bars at the ends -- they
    are the corner bars of every design -- and the ``n_b`` bars between them;
    an odd ``n_a`` puts its last bar at mid-layer. Only an odd ``n_a`` with an
    odd ``n_b`` cannot be symmetric, by one bar.
    """
    half_b, rest_b = n_b // 2, n_b - n_b // 2
    if n_a >= 2:
        k = (n_a - 2) // 2
        middle = [2] * n_b if n_a % 2 == 0 else [2] * half_b + [1] + [2] * rest_b
        return [1] + [1] * k + middle + [1] * k + [1]
    if n_a == 1:
        return [2] * half_b + [1] + [2] * rest_b
    return [2] * n_b


def _layer_x(width: float, inner: float, n_a: int, d_a: float, n_b: int, d_b: float) -> List[Tuple[int, float, float]]:
    """``(group, x, d)`` of every bar of one layer, in the check's clear-spacing model.

    ``inner`` is ``c_c + d_st``, where the first bar's face sits. A group with
    bars but no diameter keeps its slots in the spread, as the clear spacing
    counts them, and yields no bar.
    """
    total = n_a + n_b
    if total == 0:
        return []
    if total == 1:
        group, d = (1, d_a) if n_a == 1 else (2, d_b)
        return [(group, width / 2, d)]
    gap = (width - 2 * inner - n_a * d_a - n_b * d_b) / (total - 1)
    bars = []
    x = inner
    for group in _group_order(n_a, n_b):
        d = d_a if group == 1 else d_b
        bars.append((group, x + d / 2, d))
        x += d + gap
    return bars


def build_section_geometry(beam: RectangularBeam) -> SectionGeometry:
    """The geometry of ``beam`` as it is reinforced now. See the module docstring."""
    sec = section_floats(beam)
    imperial = sec.is_imperial
    canonical = CANONICAL[imperial]["length"]
    display = DISPLAY[imperial]["length"]
    factor = (1.0 * canonical).to(display).magnitude

    def q(value: float) -> Quantity:
        wrapped: Quantity = ureg.Quantity(value * factor, display)
        return wrapped

    layout = transverse_layout(beam)
    b, h, c_c, d_st = sec.width, sec.height, sec.c_c, sec.stirrup_d_b
    y_bottom, y_top = c_c + d_st / 2, h - c_c - d_st / 2

    leg_x: List[float] = []
    bars: List[BarPosition] = []
    if layout != GRID:
        if sec.stirrup_n > 0:
            leg_x = [c_c + d_st / 2 + i * sec.stirrup_s_w for i in range(int(2 * sec.stirrup_n))]
        bars = _beam_bars(beam, b, h, c_c + d_st, canonical, q)

    closed, ties = _cage(leg_x, y_bottom, y_top)
    bend_hook = design_code(beam.concrete).stirrup_bend_inner_diameter
    bend_supported = layout != GRID and bend_hook is not None
    try:
        bend = q(4 * d_st) if layout == GRID or bend_hook is None else bend_hook(beam.concrete, q(d_st))
    except ValueError:
        # Calculation geometry remains available outside the supported bend table.
        # The detailing builder independently rejects unsupported diameters.
        bend = q(4 * d_st)
        bend_supported = False
    return SectionGeometry(
        width=q(b),
        height=q(h),
        c_c=q(c_c),
        layout=layout,
        stirrup_d_b=q(d_st),
        stirrup_bend_inner_diameter=bend,
        bend_supported=bend_supported,
        s_w=q(sec.stirrup_s_w),
        leg_x=tuple(q(x) for x in leg_x),
        stirrups=tuple(
            ClosedStirrup(legs=legs, x_left=q(x_l), x_right=q(x_r), y_bottom=q(y_b), y_top=q(y_t), perimeter=p)
            for legs, x_l, x_r, y_b, y_t, p in closed
        ),
        crossties=tuple(Crosstie(leg=leg, x=q(x), y_bottom=q(y_b), y_top=q(y_t)) for leg, x, y_b, y_t in ties),
        bars=tuple(bars),
    )


def _beam_bars(beam: RectangularBeam, b: float, h: float, inner: float, canonical: Any, q: Any) -> List[BarPosition]:
    """Every bar of a beam, bottom then top, layer 1 then layer 2, left to right."""

    def diameter(value: Any) -> float:
        return 0.0 if value is None else float(value.to(canonical).magnitude)

    layers_spacing = diameter(beam.settings.layers_spacing)  # type: ignore[union-attr]
    bars: List[BarPosition] = []
    for face, suffix in (("bottom", "b"), ("top", "t")):
        n = [int(getattr(beam, f"_n{g}_{suffix}")) for g in (1, 2, 3, 4)]
        d = [diameter(getattr(beam, f"_d_b{g}_{suffix}")) for g in (1, 2, 3, 4)]
        # The offsets of the effective depth: layer 2 sits behind the larger
        # bar of layer 1 and the spacing between layers.
        offsets = (inner, inner + max(d[0], d[1]) + layers_spacing)
        for layer, (a, c) in ((1, (0, 1)), (2, (2, 3))):
            for group, x, d_bar in _layer_x(b, inner, n[a], d[a], n[c], d[c]):
                if d_bar <= 0:
                    continue
                y = offsets[layer - 1] + d_bar / 2
                bars.append(
                    BarPosition(
                        x=q(x),
                        y=q(y if face == "bottom" else h - y),
                        d_b=q(d_bar),
                        face=face,
                        layer=layer,
                        group=(a if group == 1 else c) + 1,
                    )
                )
    return bars
