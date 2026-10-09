"""Public, read-only view of the reinforcement produced by a check or a design.

The element classes keep their results in private attributes (``_A_s_bot``,
``_stirrup_s_l`` and so on). Those are implementation details and their names
and units can change. The dataclasses in this module are the supported way to
read a result from code::

    node.design()

    beam.flexure_design.bottom.A_s        # provided bottom steel area
    beam.flexure_design.bottom.A_s_req    # what the design required
    beam.shear_design.s_l                 # stirrup spacing

Every quantity is returned as a pint ``Quantity`` in the unit system of the
section's concrete, so a value can be converted with ``.to()`` as usual.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Integral
from typing import TYPE_CHECKING, Any, Optional, Sequence, Tuple, cast

from mento.bar_sizes import bar_designation, is_us_customary
from mento.codes.check_state import to_display
from mento.codes.registry import design_code
from mento.design_warnings import steel_above_maximum
from mento.i18n import checked_language, translate
from mento.precompute import DISPLAY
from mento.units import Quantity, ureg

if TYPE_CHECKING:
    from mento.beam import RectangularBeam


class DesignNotRunError(RuntimeError):
    """Raised when results are read before a check or design has been run."""


def _transverse_stirrup_count(n_stirrups: Optional[int], n_legs: Optional[int]) -> float:
    """Resolve legacy stirrup input and explicit legs without changing their meaning."""
    for name, value in (("n_stirrups", n_stirrups), ("n_legs", n_legs)):
        if value is not None:
            if isinstance(value, bool) or not isinstance(value, Integral):
                raise TypeError(f"{name} must be an integer.")
            if value < 0:
                raise ValueError(f"{name} must be non-negative.")
    if n_legs is not None:
        if n_legs == 1:
            raise ValueError("legs/n_legs: At least two legs are needed for the perimeter stirrup.")
        if n_stirrups is not None and n_legs != 2 * n_stirrups:
            raise ValueError("n_legs must equal 2 * n_stirrups when both are provided.")
        return n_legs / 2
    return 0 if n_stirrups is None else int(n_stirrups)


def spacing_separator(imperial: bool) -> str:
    """What stands between a bar and its spacing: ``Ø12/17cm``, but ``#4@12 in``.

    A slash after a US bar size would read as a fraction -- ``#3/4 in`` is
    three quarters of an inch -- so US customary writes the spacing with ``@``,
    as its drawings do.
    """
    return "@" if imperial else "/"


def bar_mark(d_b: Quantity) -> str:
    """A bar as the result dataclasses write it: ``Ø16 mm``, or its ASTM size, ``#6``.

    The dataclasses carry no unit system, so the unit of the diameter, in the
    display units of the section it came from, is what decides.
    """
    return bar_designation(d_b) if is_us_customary(d_b) else f"Ø{d_b:.4g~P}"


def format_longitudinal_rebar(n: float, bar: str, s: Optional[str] = None, *, imperial: bool = False) -> str:
    """Label one layer of longitudinal bars in the notation of its element.

    A beam is detailed as a number of bars of a diameter, so the count leads:
    ``4Ø16``, ``4#5``. A slab is one bar repeated at a spacing across the strip,
    and the count that falls out of it -- ``width / s``, not a whole number --
    says nothing about how it is drawn, so the spacing takes its place:
    ``Ø12/17cm``, ``#4@12 in`` -- the same notation its grid of stirrups is
    written in.

    Takes the bar and the spacing already written -- ``bar`` with its symbol,
    ``Ø16`` or ``#5`` -- so each caller keeps its own precision and units while
    the shape of the label is decided in one place. The count is the
    exception, a bare number: a whole one reads whole whatever its type, since
    a count entered as ``2.0`` is still two bars, not "2.0Ø16".
    """
    if s is None:
        count = int(n) if float(n).is_integer() else n
        return f"{count}{bar}"
    return f"{bar}{spacing_separator(imperial)}{s}"


def placed_bars(n: float) -> int:
    """The whole bars a count of ``n`` bars per strip is laid out with: ``ceil(n)``.

    A count that is whole but arrives a hair above it, through the division
    ``width / s``, stays whole: 100/20 is five bars, not six.
    """
    return math.ceil(n - 1e-9)


@dataclass(frozen=True)
class RebarLayer:
    """One layer of longitudinal bars: ``n`` bars of diameter ``d_b``.

    ``s`` is the centre-to-centre spacing the layer was detailed with, and is
    ``None`` on a section that is detailed by a bar count instead -- a beam.
    On a beam ``n`` is a whole number of bars. On a slab strip it is
    ``width / s``, the bars per strip the spacing gives, and need not be
    whole: a metre of Ø10/15 carries 6.67 of them, 5.24 cm², which is what
    every metre of that slab carries, and what its strength is computed with.
    The area is ``n`` bar areas either way.

    ``n_placed`` is the whole number of bars that lay the layer out across
    the strip: 7 for that Ø10/15 in a metre, placed at 15 cm, the last bar a
    little past the metre. On a beam it is ``n``.
    """

    n: float
    d_b: Quantity
    s: Optional[Quantity] = None

    @property
    def A_s(self) -> Quantity:
        """Steel area of this layer."""
        return self.n * (self.d_b**2) * math.pi / 4

    @property
    def n_placed(self) -> int:
        """The whole bars that lay this layer out: ``ceil(n)``, ``n`` on a beam."""
        return placed_bars(self.n)

    def __str__(self) -> str:
        return format_longitudinal_rebar(
            self.n,
            bar_mark(self.d_b),
            None if self.s is None else f"{self.s:.4g~P}",
            imperial=is_us_customary(self.d_b),
        )


@dataclass(frozen=True)
class RebarOption:
    """One longitudinal layout a flexure design found for a face.

    ``layers`` holds the bar groups that carry bars, in the order of the
    search's ``n_1``..``n_4`` / ``d_b1``..``d_b4``: the first two are the layer
    nearest the face, the other two the layer behind it -- the same
    :class:`RebarLayer` the applied reinforcement is read as.

    ``functional`` is the score the search ranks layouts by, lower being
    better: it weighs the area against the fewest bars, the spread of
    diameters and the use of a second layer. It is ``None`` for a layout the
    search did not score -- a footing mat, which is chosen afterwards and as a
    whole.

    ``section_DCR`` is the worst demand-capacity ratio of the finished
    section with this layout on its face and the other face as applied --
    flexure and shear, both faces, every combination the design was run
    for. It is the section's, not the face's: ``flexure_design.top.DCR`` is
    the top face's ratio, while ``flexure_design.top.options[0].section_DCR``
    may be the bottom's, or the shear's. The bars set the depth the shear
    is read at too, so a layout that sits deeper lowers the section's shear
    limit and can tighten its stirrup spacing limit. An alternative is only
    offered when that ratio is at most 1, the
    bars fit beside the stirrups the design finished with, the section keeps
    within the code's limits on its reinforcement, and its stirrups within
    theirs -- the compression bars the layout relies on included; the applied
    layout carries its own, whatever it is. ``None`` on an option that has
    not been verified.
    """

    layers: Tuple[RebarLayer, ...]
    A_s: Quantity
    functional: Optional[float] = None
    section_DCR: Optional[float] = None

    @property
    def n_bars(self) -> float:
        """Total number of bars across every layer of this layout.

        Whole on a beam; on a slab strip the bars per strip its spacings give,
        which need not be (see :class:`RebarLayer`).
        """
        return sum(layer.n for layer in self.layers)

    @property
    def n_bars_placed(self) -> int:
        """The whole bars that lay out every layer: see :attr:`RebarLayer.n_placed`."""
        return sum(layer.n_placed for layer in self.layers)

    def __str__(self) -> str:
        if not self.layers:
            return "no reinforcement"
        return " + ".join(str(layer) for layer in self.layers)


@dataclass(frozen=True)
class FlexureFaceCheck:
    """What a single load combination demanded of one face.

    ``M_capacity`` is the design moment resistance the ``DCR`` was formed
    from -- ``ØMn`` under ACI 318-19 and CIRSOC 201-25, ``MRd`` under
    EN 1992-1-1. One neutral name for every code: the symbol belongs to the
    presentation layer, which already names it per code. A face carrying only
    minimum reinforcement against no demand still reports it, which is what
    the ratio alone cannot tell.

    ``A_s_req`` is the steel to detail: what the moment asks for or the
    minimum, whichever is larger. ``A_s_calc`` is the first of those alone,
    before the minimum -- zero with no moment. An anchorage scaled by
    ``A_s,nec / A_s,prov`` reads it, because a face governed by its minimum
    carries little of the stress that minimum is sized for.

    ``A_s_min`` is the minimum as the clause writes it. ``A_s_min_eff`` is the
    one the face has to meet: under ACI 318-19 and CIRSOC 201-25 the relief of
    §9.6.1.3 lets 4/3 of ``A_s_calc`` stand in for it when that is less, so a
    face below ``A_s_min`` but not below ``A_s_min_eff`` complies. EN
    1992-1-1 has no such relief, and there the two are the same. Compare the
    steel provided against ``A_s_min_eff``.

    ``A_s_max`` and ``A_s_max_eff`` are the same pair at the other end. Under
    ACI 318-19 and CIRSOC 201-25 ``A_s_max`` is the tension steel that keeps a
    singly reinforced face tension-controlled, and ``A_s_max_eff`` the same
    limit with the compression steel the opposite face carries,
    ``A_s_max + A_s'*f_s'/f_y``: past it the face is no longer
    tension-controlled, which §9.3.3.1 does not allow a beam, and its capacity
    takes the phi of the strain it reaches. Under EN 1992-1-1 the maximum is
    the 4 % of §9.2.1.1(3), which compression steel does not extend, and the
    two are the same.

    ``admissible`` is False when the face carries more steel than that
    maximum allows: under ACI 318-19 and CIRSOC 201-25 the section is then
    not tension-controlled, which §9.3.3.1 (§7.3.3.1 for a one-way slab)
    does not allow, and under EN 1992-1-1 it is past the 4 %. A face that is
    not admissible does not comply even where its ``DCR`` is below 1:
    ``complies`` reads both. The warning that goes with it is
    ``not_tension_controlled`` (ACI 318-19 / CIRSOC 201-25) or
    ``As_above_max`` (EN 1992-1-1).

    A field is ``None`` when the design code did not set it for this
    combination; enveloping skips those rather than treating them as zero.
    """

    A_s_req: Optional[Quantity]
    A_s_min: Optional[Quantity]
    A_s_max: Optional[Quantity]
    DCR: float
    M_capacity: Optional[Quantity] = None
    A_s_calc: Optional[Quantity] = None
    A_s_min_eff: Optional[Quantity] = None
    A_s_max_eff: Optional[Quantity] = None
    admissible: bool = True

    @property
    def complies(self) -> bool:
        """The face carries its moment (``DCR <= 1``) and is within its maximum steel."""
        return self.DCR <= 1.0 and self.admissible


@dataclass(frozen=True)
class FlexureCheck:
    """The flexure result of one load combination, on both faces."""

    label: str
    bottom: FlexureFaceCheck
    top: FlexureFaceCheck
    # Demand metadata, not a claim that flexure includes axial interaction.
    has_axial_force: bool = False

    @property
    def complies(self) -> bool:
        """Both faces comply under this combination."""
        return self.bottom.complies and self.top.complies


@dataclass(frozen=True)
class ShearCheck:
    """The shear result of one load combination.

    ``V_capacity`` is the design shear resistance the ``DCR`` was formed from
    -- ``ØVn``, capped by ``ØVmax``, under ACI 318-19 and CIRSOC 201-25;
    ``VRd`` under EN 1992-1-1. See :class:`FlexureFaceCheck` for the naming.

    ``label`` is the name of the load combination, not a description of the
    stirrups: that is :meth:`ShearDesign.notation`.

    The spacing limits of this combination. ``s_max_l_table``
    and ``s_max_w`` are the limits along the member and across its width
    that ACI 318-19 / CIRSOC 201-25 Table 9.7.6.2.2 set -- Expressions (9.6N)
    and (9.8N) under EN 1992-1-1, the first with mento's own 400 mm cap. The
    along-length one carries ``_table`` in its name because it is not always
    the limit the stirrups are held to: §9.7.6.4.3 can cap it further on a
    section that relies on compression bars, a limit of the section rather
    than of one combination, which :attr:`ShearDesign.s_max_l` folds in.
    ``V_s_req`` is the nominal shear the stirrups must carry, ``V_s_threshold``
    the ``0.33·√f'c·bw·d`` (``4·√f'c·bw·d`` in psi) past which the table
    halves its limits, and ``spacing_halved`` whether this combination passed
    it. Each is ``None`` where the code has no such quantity (those three
    under EN 1992-1-1) or the check set no limit (EN with no stirrups).
    """

    label: str
    A_v_req: Optional[Quantity]
    A_v_min: Optional[Quantity]
    DCR: float
    V_capacity: Optional[Quantity] = None
    V_s_req: Optional[Quantity] = None
    V_s_threshold: Optional[Quantity] = None
    spacing_halved: Optional[bool] = None
    s_max_l_table: Optional[Quantity] = None
    s_max_w: Optional[Quantity] = None


def _worst(values: Sequence[Optional[Quantity]]) -> Optional[Quantity]:
    """Largest of the values that are present, or None if none of them are."""
    present = [value for value in values if value is not None]
    return max(present) if present else None


def _least(values: Sequence[Optional[Quantity]]) -> Optional[Quantity]:
    """Smallest of the values that are present, or None if none of them are.

    The envelope of a limit the steel must stay under is its tightest value.
    """
    present = [value for value in values if value is not None]
    return min(present) if present else None


def _governing(pairs: Sequence[Tuple[float, Optional[Quantity]]]) -> Optional[Quantity]:
    """The capacity of the combination that governs, or None if none reported one.

    ``pairs`` are ``(DCR, capacity)``, one per combination. The envelope's DCR
    is the largest of them, and its capacity has to be the resistance that DCR
    was formed from, so that ``demand / DCR`` gives it back on the envelope as
    it does on each combination. That matters because a capacity is not always
    the section's alone: under ACI 318-19 the shear resistance moves with the
    combination, through the axial load and the face in tension that enter
    ``V_c``. Among combinations tied on DCR -- every one of them, when nothing
    is demanded -- the smallest capacity is the safe reading.
    """
    present = [(dcr, capacity) for dcr, capacity in pairs if capacity is not None]
    if not present:
        return None
    return min(present, key=lambda pair: (-pair[0], pair[1]))[1]


def envelope_flexure_face(checks: Sequence[FlexureCheck], face: str) -> FlexureFaceCheck:
    """Worst demand on one face across every combination checked.

    A pure function of the results: the governing combination differs per
    quantity and per face, so each one is enveloped independently -- except
    the capacity, which follows the DCR so the two stay the ratio they were.
    ``face`` is ``"bottom"`` or ``"top"``.
    """
    faces = [getattr(check, face) for check in checks]
    return FlexureFaceCheck(
        A_s_req=_worst([f.A_s_req for f in faces]),
        A_s_min=_worst([f.A_s_min for f in faces]),
        A_s_max=_worst([f.A_s_max for f in faces]),
        DCR=max([f.DCR for f in faces], default=0.0),
        M_capacity=_governing([(f.DCR, f.M_capacity) for f in faces]),
        A_s_calc=_worst([f.A_s_calc for f in faces]),
        A_s_min_eff=_worst([f.A_s_min_eff for f in faces]),
        A_s_max_eff=_least([f.A_s_max_eff for f in faces]),
        admissible=all(f.admissible for f in faces),
    )


def _largest_demand(checks: Sequence[ShearCheck]) -> Optional[ShearCheck]:
    """The combination that asks the stirrups for the most shear, or None if none set ``V_s_req``."""
    present = [check for check in checks if check.V_s_req is not None]
    if not present:
        return None
    return max(present, key=lambda check: cast(Quantity, check.V_s_req))


def _any_halved(checks: Sequence[ShearCheck]) -> Optional[bool]:
    """Whether some combination took the halved row of Table 9.7.6.2.2; None if none recorded a row."""
    rows = [check.spacing_halved for check in checks if check.spacing_halved is not None]
    return any(rows) if rows else None


def envelope_shear(checks: Sequence[ShearCheck]) -> ShearCheck:
    """Worst shear demand across every combination checked.

    The spacing limits are the tightest of any combination, which is what the
    warnings hold each one to. The fields that say why agree with them:
    ``V_s_req`` is the largest of any combination, ``V_s_threshold`` is the
    one that same combination was compared with, and ``spacing_halved`` is
    True when any combination took the halved row of Table 9.7.6.2.2 -- the
    row the tightest limits come from. So the envelope reads as one
    combination would: halved exactly when ``V_s_req`` is past
    ``V_s_threshold``. ``V_capacity`` follows the governing DCR, as on
    :func:`envelope_flexure_face`.
    """
    demand = _largest_demand(checks)
    return ShearCheck(
        label="envelope",
        A_v_req=_worst([c.A_v_req for c in checks]),
        A_v_min=_worst([c.A_v_min for c in checks]),
        DCR=max([c.DCR for c in checks], default=0.0),
        V_capacity=_governing([(c.DCR, c.V_capacity) for c in checks]),
        V_s_req=None if demand is None else demand.V_s_req,
        V_s_threshold=None if demand is None else demand.V_s_threshold,
        spacing_halved=_any_halved(checks),
        s_max_l_table=_least([c.s_max_l_table for c in checks]),
        s_max_w=_least([c.s_max_w for c in checks]),
    )


def capture_flexure_check(beam: RectangularBeam, label: str, state: Any, has_axial_force: bool = False) -> FlexureCheck:
    """The flexure result of the combination just run.

    Reads the ``state`` the design code returned, so nothing has to have been
    written to the beam: the result is a value of the check, not a reading of
    the section afterwards.
    """
    imperial = beam.concrete.is_imperial
    over = steel_above_maximum(beam, state)

    def face(suffix: str) -> FlexureFaceCheck:
        A_s_req, A_s_min, A_s_max, M_capacity, A_s_calc, A_s_min_eff, A_s_max_eff = state.face_quantities(
            suffix, imperial
        )
        return FlexureFaceCheck(
            A_s_req=A_s_req,
            A_s_min=A_s_min,
            A_s_max=A_s_max,
            DCR=float(getattr(state, f"DCR_{suffix}")),
            M_capacity=M_capacity,
            A_s_calc=A_s_calc,
            A_s_min_eff=A_s_min_eff,
            A_s_max_eff=A_s_max_eff,
            admissible=suffix not in over,
        )

    return FlexureCheck(label=label, bottom=face("bot"), top=face("top"), has_axial_force=has_axial_force)


def capture_shear_check(beam: RectangularBeam, label: str, state: Any) -> ShearCheck:
    """The shear result of the combination just run.

    Reads the ``state`` the design code returned; see
    :func:`capture_flexure_check`.
    """
    imperial = beam.concrete.is_imperial
    A_v_req, A_v_min = state.shear_reinforcement_quantities(imperial)
    V_s_req, V_s_threshold, spacing_halved, s_max_l_table, s_max_w = state.spacing_quantities(imperial)
    return ShearCheck(
        label=label,
        A_v_req=A_v_req,
        A_v_min=A_v_min,
        DCR=float(state.DCR),
        V_capacity=state.shear_capacity_quantity(imperial),
        V_s_req=V_s_req,
        V_s_threshold=V_s_threshold,
        spacing_halved=spacing_halved,
        s_max_l_table=s_max_l_table,
        s_max_w=s_max_w,
    )


@dataclass(frozen=True)
class FaceReinforcement:
    """The longitudinal bars a section carries on one face.

    This is *configuration*, not a result: it says what is detailed on the
    section right now, whether that came from a design, from
    ``set_longitudinal_rebar_bot``, or from the constructor defaults. It is
    therefore readable at any time, unlike :class:`FlexureFaceDesign`, which
    also carries what a check demanded and so needs a check to have run.
    """

    layers: Tuple[RebarLayer, ...]
    A_s: Quantity

    @property
    def n_bars(self) -> float:
        """Total number of bars across every layer of this face.

        Whole on a beam; on a slab strip the bars per strip its spacings give,
        which need not be (see :class:`RebarLayer`).
        """
        return sum(layer.n for layer in self.layers)

    @property
    def n_bars_placed(self) -> int:
        """The whole bars that lay out every layer: see :attr:`RebarLayer.n_placed`."""
        return sum(layer.n_placed for layer in self.layers)

    def __str__(self) -> str:
        if not self.layers:
            return "no reinforcement"
        return " + ".join(str(layer) for layer in self.layers)


#: How a section carries its transverse reinforcement. A beam carries closed
#: stirrups; a slab strip carries a grid of legs, with no cage to count.
STIRRUPS = "stirrups"
GRID = "grid"


def format_transverse_rebar(
    layout: str,
    n_stirrups: float,
    bar: str,
    s_l: str,
    s_w: str,
    *,
    n_legs: Optional[int] = None,
    s_max_w: Optional[str] = None,
    language: Optional[str] = "en",
    separator: str = " · ",
    imperial: bool = False,
) -> str:
    """Label the transverse reinforcement in the notation of its element.

    A beam is a cage of closed stirrups, and what the shear check counts is
    its legs, so the legs lead, then the bar and the spacing along the
    length, then the spacing of the legs across the width -- which is what
    ``s_max_w`` limits, and is printed after it when given:
    ``10 legs Ø12 mm @ 14 cm · 15.87 cm between legs (max 20 cm)``. ``n_legs``
    defaults to two per stirrup. A slab strip has no cage -- the same bar sits
    on a grid -- so what identifies it is the diameter once and a spacing each
    way, longitudinal first: ``Ø10/15cm×20cm``. The diameter is not repeated:
    both directions are the same bar.

    Takes the numbers already formatted, so each caller keeps its own precision
    and units while the shape of the label is decided in one place. The words
    are looked up in the catalog of ``language`` (English by default, the
    language of the moment with ``None``; see :mod:`mento.i18n`), and
    ``separator`` joins the two halves of a beam's label -- a line break
    splits it in two for a drawing. An explicit ``language`` without a
    catalog raises ``ValueError``, as :func:`mento.set_language` does.
    """
    checked_language(language)
    if n_stirrups == 0:
        return translate("no stirrups", language)
    d_b = bar.removeprefix("Ø")
    bar = bar if bar.startswith(("Ø", "#")) else f"Ø{bar}"
    if layout == GRID:
        return f"{bar}{spacing_separator(imperial)}{s_l}×{s_w}"
    raw_legs = 2 * n_stirrups if n_legs is None else n_legs
    if not math.isfinite(raw_legs) or raw_legs != int(raw_legs) or raw_legs < 2:
        raise ValueError("The transverse count must represent an integer number of legs >= 2.")
    legs = int(raw_legs)
    text = translate("{n_legs} legs Ø{d_b} @ {s_l}", language, n_legs=legs, d_b=d_b.removeprefix("Ø"), s_l=s_l).replace(
        "Ø#", "#"
    )
    text += separator + translate("{s_w} between legs", language, s_w=s_w)
    if s_max_w is not None:
        text += " " + translate("(max {s_max_w})", language, s_max_w=s_max_w)
    return text


def _is_imperial_length(value: Quantity) -> bool:
    """Whether a spacing is in US customary units (inches or feet)."""
    return value.units in (ureg.inch, ureg.foot)


def transverse_notation(
    layout: str,
    n_stirrups: float,
    d_b: Quantity,
    s_l: Quantity,
    s_w: Quantity,
    s_max_w: Optional[Quantity] = None,
    language: Optional[str] = None,
    *,
    separator: str = " · ",
    compact: bool = False,
    imperial: Optional[bool] = None,
) -> str:
    """The notation of a transverse reinforcement given as quantities.

    What :meth:`TransverseReinforcement.notation` and its siblings print. The
    spacings across the width are shown in the unit of ``s_l``, so a beam
    built in millimetres and designed in centimetres reads in one unit;
    ``d_b`` keeps its own. Numbers take mento's ``.4g`` format with a dot.

    ``compact`` is the form for a narrow column: bare numbers, the bar in mm
    and the spacing in cm -- ASTM sizes and inches when ``imperial`` is True -- and neither
    the spacing across the width nor its maximum: ``10 legs Ø12/14`` on a
    beam, ``Ø10/8×16`` on a slab strip. The numbers carry no unit, so the
    caller says which system they are in: pass the section's
    (``beam.concrete.is_imperial``), or the system of the table they sit in.
    With ``imperial`` left as ``None`` the compact form follows the unit of
    ``s_l``: ASTM sizes and inches when it is in inches or feet, mm and cm otherwise.

    ``language`` is the catalog the words come from, the current one with
    ``None``; an explicit code without a catalog raises ``ValueError``, as
    :func:`mento.set_language` does.
    """
    checked_language(language)
    if imperial is None:
        imperial = _is_imperial_length(s_l)
    if compact:
        if n_stirrups == 0:
            return translate("no stirrups", language)
        d_unit, s_unit = ("inch", "inch") if imperial else ("mm", "cm")
        d_shown = bar_designation(d_b) if imperial else f"{d_b.to(d_unit).magnitude:.4g}"
        s_shown = f"{s_l.to(s_unit).magnitude:.4g}"
        if layout == GRID:
            return f"{d_shown if imperial else f'Ø{d_shown}'}{spacing_separator(imperial)}{s_shown}×{s_w.to(s_unit).magnitude:.4g}"
        return (
            translate(
                "{n_legs} legs Ø{d_b}/{s_l}",
                language,
                n_legs=int(2 * n_stirrups),
                d_b=d_shown.removeprefix("Ø"),
                s_l=s_shown,
            )
            .replace("Ø#", "#")
            .replace("/", "@" if imperial else "/")
        )
    if layout == GRID:
        # The grid is written as it always was, each spacing in its own unit.
        s_w_shown = f"{s_w:.4g~P}"
        max_shown = None
    else:
        s_w_shown = f"{s_w.to(s_l.units):.4g~P}"
        max_shown = None if s_max_w is None else f"{s_max_w.to(s_l.units):.4g~P}"
    return format_transverse_rebar(
        layout,
        n_stirrups,
        bar_designation(d_b) if imperial else f"{d_b:.4g~P}",
        f"{s_l:.4g~P}",
        s_w_shown,
        n_legs=int(2 * n_stirrups),
        s_max_w=max_shown,
        language=language,
        separator=separator,
        imperial=imperial,
    )


def cage_legs(n_legs: int) -> Tuple[Tuple[Tuple[int, int], ...], Tuple[int, ...]]:
    """Base seccional: un cerrado perimetral y las restantes patas abiertas.

    El detallador propone trabas con ganchos cuando la sujeción por compresión
    las necesita. Esta función, sin fuerzas ni barras, no acredita esa sujeción.
    """
    if isinstance(n_legs, bool) or not isinstance(n_legs, Integral):
        raise TypeError("n_legs must be an integer.")
    if n_legs < 0 or n_legs == 1:
        raise ValueError("legs/n_legs: At least two legs are needed for the perimeter stirrup.")
    if n_legs == 0:
        return (), ()
    return ((0, n_legs - 1),), tuple(range(1, n_legs - 1))


def describe_stirrup_cage(n_legs: int, language: Optional[str] = None) -> str:
    """The cage of :func:`cage_legs` in words, for whoever details it.

    Base layout: one perimeter stirrup and the remaining open legs.
    The force-dependent transverse pieces are described by SectionGeometry.
    A single leg cannot form the mandatory perimeter. In the language of the moment unless
    ``language`` says otherwise; an explicit code without a catalog raises
    ``ValueError``, as :func:`mento.set_language` does.
    """
    checked_language(language)
    if n_legs <= 0:
        return translate("no stirrups", language)
    stirrups, crossties = cage_legs(n_legs)
    parts = []
    if len(stirrups) == 1 and not crossties:
        return translate("single perimeter stirrup", language)
    if stirrups:
        parts.append(translate("perimeter stirrup", language))
    if crossties:
        parts.append(
            translate("1 open leg", language)
            if len(crossties) == 1
            else translate("{n} open legs", language, n=len(crossties))
        )
    return " + ".join(parts)


def _transverse_arrangement(layout: str, n_stirrups: float, language: Optional[str] = None) -> str:
    """The cage of a beam's stirrups in words; empty on a slab strip, which has no cage."""
    checked_language(language)
    if layout == GRID:
        return ""
    return describe_stirrup_cage(int(2 * n_stirrups), language)


@dataclass(frozen=True)
class TransverseReinforcement:
    """The transverse reinforcement a section carries, as configured.

    ``s_l`` is the spacing along the length and ``s_w`` the spacing across the
    width. On a beam the second is not detailed but implied -- it is where the
    legs of the cage fall -- while on a slab strip both are chosen, which is
    what ``layout`` distinguishes.
    """

    n_stirrups: float
    d_b: Quantity
    s_l: Quantity
    A_v: Quantity
    s_w: Quantity
    layout: str = STIRRUPS

    @property
    def n_legs(self) -> int:
        """Number of stirrup legs crossing the shear plane."""
        return int(self.n_stirrups * 2)

    def notation(
        self,
        language: Optional[str] = None,
        *,
        separator: str = " · ",
        compact: bool = False,
        imperial: Optional[bool] = None,
    ) -> str:
        """The stirrups in the notation of the element, in ``language`` (the current one by default).

        The configuration carries no limit, so no maximum is printed.
        See :func:`transverse_notation` for ``separator``, ``compact`` and ``imperial``.
        """
        return transverse_notation(
            self.layout,
            self.n_stirrups,
            self.d_b,
            self.s_l,
            self.s_w,
            None,
            language,
            separator=separator,
            compact=compact,
            imperial=imperial,
        )

    def arrangement(self, language: Optional[str] = None) -> str:
        """Base cage layout without force-dependent transverse pieces; read detailing_geometry.arrangement() for the actual pieces. Empty on a slab."""
        return _transverse_arrangement(self.layout, self.n_stirrups, language)

    def __str__(self) -> str:
        """Always English, like the ``str()`` of every result of this module; :meth:`notation` follows the language."""
        return self.notation(language="en")


@dataclass(frozen=True)
class SectionReinforcement:
    """Every bar a section carries: both faces plus the stirrups."""

    bottom: FaceReinforcement
    top: FaceReinforcement
    transverse: TransverseReinforcement

    def __str__(self) -> str:
        return f"bottom: {self.bottom} / top: {self.top} / stirrups: {self.transverse}"


@dataclass(frozen=True)
class FlexureFaceDesign:
    """Longitudinal reinforcement on one face of the section.

    ``layers`` only contains the layers that actually carry bars, so an
    empty tuple means no reinforcement was placed on this face.

    ``A_s`` is what the section carries. ``A_s_req``, ``A_s_min``, ``A_s_max``
    and ``DCR`` are the envelope over every load combination that was checked,
    so ``DCR`` is the one of the combination that governs this face.

    ``A_s_req`` is the steel to detail, never below ``A_s_min_eff``. ``A_s_calc``
    is what the moment alone asked for, before that minimum -- the envelope of
    the same over the combinations, so the governing one's. Choose bars from
    the first; scale an anchorage by ``A_s,nec / A_s,prov`` from the second,
    since a face governed by its minimum carries little of the stress the
    minimum is sized for.

    ``A_s_min`` is the minimum as the clause writes it, and ``A_s_min_eff``
    the one the face has to meet, after the relief of ACI 318-19 / CIRSOC
    201-25 §9.6.1.3 -- see :class:`FlexureFaceCheck`. A designed face can sit
    below ``A_s_min`` and still comply; it cannot sit below ``A_s_min_eff``.
    ``A_s_max_eff`` is the same at the top end: the tension steel the face can
    carry and stay tension-controlled with the compression steel opposite it.
    A face above ``A_s_max`` and below ``A_s_max_eff`` is doubly reinforced
    and complies.

    ``options`` are the layouts the last design found for this face, best
    first; ``options[0]`` is the one applied. The rest were each built on
    the finished section -- the stirrups the design ended with, the other
    face as applied -- and kept only if the section carries both moments
    and the shear with it, within the code's limits on its reinforcement and
    its stirrups; each carries the ``section_DCR`` it was kept at -- the
    section's worst ratio, not this face's ``DCR``. A footing offers none:
    its mat is chosen as a whole, module and both bars together, and no row
    of the per-face search is that mat with one thing changed. Empty when the face was not
    designed, or when its bars were changed by hand after the design.

    ``M_capacity`` is the design moment resistance of the face as reinforced
    -- ``ØMn`` under ACI 318-19 and CIRSOC 201-25, ``MRd`` under EN 1992-1-1
    -- as the governing combination saw it, so it is the resistance ``DCR``
    was formed from.

    ``admissible`` is False when some combination found the face past its
    maximum steel, and ``complies`` reads it with ``DCR`` -- see
    :class:`FlexureFaceCheck`. A design never accepts a face that does not
    comply; it ends on one only when no layout does, and warns.
    """

    layers: Tuple[RebarLayer, ...]
    A_s: Quantity
    A_s_req: Quantity
    A_s_calc: Quantity
    A_s_min: Quantity
    A_s_min_eff: Quantity
    A_s_max: Quantity
    A_s_max_eff: Quantity
    DCR: float
    M_capacity: Quantity
    options: Tuple[RebarOption, ...] = ()
    admissible: bool = True

    @property
    def complies(self) -> bool:
        """The face carries its moment (``DCR <= 1``) and is within its maximum steel."""
        return self.DCR <= 1.0 and self.admissible

    @property
    def n_bars(self) -> float:
        """Total number of bars across every layer of this face.

        Whole on a beam; on a slab strip the bars per strip its spacings give,
        which need not be (see :class:`RebarLayer`).
        """
        return sum(layer.n for layer in self.layers)

    @property
    def n_bars_placed(self) -> int:
        """The whole bars that lay out every layer: see :attr:`RebarLayer.n_placed`."""
        return sum(layer.n_placed for layer in self.layers)

    def __str__(self) -> str:
        if not self.layers:
            return "no reinforcement"
        return " + ".join(str(layer) for layer in self.layers)


@dataclass(frozen=True)
class FlexureDesign:
    """Longitudinal reinforcement of the whole section."""

    bottom: FlexureFaceDesign
    top: FlexureFaceDesign

    @property
    def DCR(self) -> float:
        """Governing demand-to-capacity ratio of the two faces."""
        return max(self.bottom.DCR, self.top.DCR)

    @property
    def complies(self) -> bool:
        """Both faces comply: see :attr:`FlexureFaceDesign.complies`."""
        return self.bottom.complies and self.top.complies

    def __str__(self) -> str:
        return f"bottom: {self.bottom} / top: {self.top}"


@dataclass(frozen=True)
class StirrupOption:
    """One transverse layout a shear design found.

    The fields read as those of :class:`ShearDesign`, with one difference in
    the limits: ``s_max_l`` means the same on both -- the along-length limit
    the stirrups are held to, Table 9.7.6.2.2 and §9.7.6.4.3 together -- but
    an option carries no ``s_max_l_table`` / ``s_max_l_support`` split, and
    its two limits are the ones the search read at the depth this option's
    own stirrup gives the section (``None`` where the search
    recorded none). ``functional`` says how
    much steel the option adds: the excess of ``A_v`` over what the section
    asks for with this stirrup on it, ``A_v / A_v_req - 1``, plus one for
    every stirrup beyond the fewest any option needs.

    ``section_DCR`` is the worst demand-capacity ratio of the finished
    section built with this option -- shear and flexure, both faces, every
    combination the design was run for -- so it need not be the shear's:
    ``shear_design.DCR`` is. A stirrup is not only shear: a heavier one sits the
    bars deeper, which lowers the effective depth and with it the section's
    shear limit and its moment capacity. An alternative is only offered when
    that ratio is at most 1 and the section misses no limit with it; the
    applied layout carries its own, whatever it is.
    """

    n_stirrups: float
    d_b: Quantity
    s_l: Quantity
    s_w: Quantity
    A_v: Quantity
    functional: float
    layout: str = STIRRUPS
    section_DCR: Optional[float] = None
    s_max_l: Optional[Quantity] = None
    s_max_w: Optional[Quantity] = None

    @property
    def n_legs(self) -> int:
        """Number of stirrup legs crossing the shear plane."""
        return int(self.n_stirrups * 2)

    def notation(
        self,
        language: Optional[str] = None,
        *,
        separator: str = " · ",
        compact: bool = False,
        imperial: Optional[bool] = None,
    ) -> str:
        """The stirrups in the notation of the element, in ``language`` (the current one by default).

        Ends with the maximum spacing of the legs, ``s_max_w``, when there is one.
        See :func:`transverse_notation` for ``separator``, ``compact`` and ``imperial``.
        """
        return transverse_notation(
            self.layout,
            self.n_stirrups,
            self.d_b,
            self.s_l,
            self.s_w,
            self.s_max_w,
            language,
            separator=separator,
            compact=compact,
            imperial=imperial,
        )

    def arrangement(self, language: Optional[str] = None) -> str:
        """Base cage layout without force-dependent transverse pieces; read detailing_geometry.arrangement() for the actual pieces. Empty on a slab."""
        return _transverse_arrangement(self.layout, self.n_stirrups, language)

    def __str__(self) -> str:
        """Always English, like the ``str()`` of every result of this module; :meth:`notation` follows the language."""
        return self.notation(language="en")


@dataclass(frozen=True)
class ShearDesign:
    """Transverse reinforcement of the section.

    ``n_stirrups`` is the legacy two-leg equivalent, not the number of closed pieces; ``n_legs`` counts the legs crossing
    the shear plane, which is what enters the ``A_v`` calculation.

    ``A_v_req``, ``A_v_min`` and ``DCR`` are the envelope over every load
    combination that was checked, so ``DCR`` is the governing one.

    ``V_capacity`` is the design shear resistance of the section as reinforced
    -- ``ØVn``, capped by ``ØVmax``, under ACI 318-19 and CIRSOC 201-25;
    ``VRd`` under EN 1992-1-1 -- as the governing combination saw it, so it is
    the resistance ``DCR`` was formed from. Under ACI it can differ between
    combinations: ``V_c`` moves with the axial load and with which face is in
    tension. The per-combination results carry each one's own.

    ``options`` are the stirrup layouts the last design found: ``options[0]``
    is the one applied, and the rest are one layout per other bar diameter
    the code offers, lighter and heavier alike, in order of diameter -- each
    the widest spacing with the fewest legs that covers the demand read at
    the depth that bar gives the section. Only the ones the finished section
    passes with are kept, shear and flexure, so a drawing can take any of
    them for the bar at hand; each carries its ``section_DCR``, the worst of
    the section built with it, flexure included -- not always this result's
    ``DCR``, which is the shear's. Empty when the stirrups were not
    designed, or were changed by hand afterwards.

    The spacing limits are envelopes over every combination
    checked, the tightest of each -- what the warnings hold the stirrups to:

    - ``s_max_w``: the limit across the width, on the legs -- ACI 318-19 /
      CIRSOC 201-25 Table 9.7.6.2.2, Expression (9.8N) under EN 1992-1-1.
    - ``s_max_l_table``: the limit along the member of that same table --
      Expression (9.6N) under EN 1992-1-1, with the 400 mm cap that is
      mento's own, not the code's.
    - ``s_max_l_support``: the cap of §9.7.6.4.3 on the stirrups that brace
      compression bars -- the least of 16 d_b of the bar, 48 d_b of the
      stirrup and the least dimension of the beam -- or ``None`` when the
      code has no such clause or the section relies on no compression bars.
    - ``s_max_l``: the along-length limit the stirrups are held to, the
      least of the two above.

    Each is ``None`` where there is none: EN 1992-1-1 sets no limit on a
    section without stirrups. ``s_w`` reads against ``s_max_w`` and ``s_l``
    against ``s_max_l``. The threshold and the row of Table 9.7.6.2.2 that
    set them are on each :class:`ShearCheck`.
    """

    n_stirrups: float
    d_b: Quantity
    s_l: Quantity
    A_v: Quantity
    A_v_req: Quantity
    A_v_min: Quantity
    DCR: float
    V_capacity: Quantity
    s_w: Quantity
    layout: str = STIRRUPS
    options: Tuple[StirrupOption, ...] = ()
    s_max_l: Optional[Quantity] = None
    s_max_w: Optional[Quantity] = None
    s_max_l_table: Optional[Quantity] = None
    s_max_l_support: Optional[Quantity] = None

    @property
    def n_legs(self) -> int:
        """Number of stirrup legs crossing the shear plane."""
        return int(self.n_stirrups * 2)

    def notation(
        self,
        language: Optional[str] = None,
        *,
        separator: str = " · ",
        compact: bool = False,
        imperial: Optional[bool] = None,
    ) -> str:
        """The stirrups in the notation of the element, in ``language`` (the current one by default).

        Ends with the maximum spacing of the legs, ``s_max_w``, when there is one.
        See :func:`transverse_notation` for ``separator``, ``compact`` and ``imperial``.
        """
        return transverse_notation(
            self.layout,
            self.n_stirrups,
            self.d_b,
            self.s_l,
            self.s_w,
            self.s_max_w,
            language,
            separator=separator,
            compact=compact,
            imperial=imperial,
        )

    def arrangement(self, language: Optional[str] = None) -> str:
        """Base cage layout without force-dependent transverse pieces; read detailing_geometry.arrangement() for the actual pieces. Empty on a slab."""
        return _transverse_arrangement(self.layout, self.n_stirrups, language)

    def __str__(self) -> str:
        """Always English, like the ``str()`` of every result of this module; :meth:`notation` follows the language."""
        return self.notation(language="en")


def transverse_layout(beam: RectangularBeam) -> str:
    """Which notation the section's transverse reinforcement is written in."""
    return GRID if getattr(beam, "mode", "beam") == "slab" else STIRRUPS


def _layers(beam: RectangularBeam, face: str) -> Tuple[RebarLayer, ...]:
    """Collect the non-empty rebar layers of one face ("b" for bottom, "t" for top)."""
    layers = []
    for index in (1, 2, 3, 4):
        n = getattr(beam, f"_n{index}_{face}", 0)
        d_b: Optional[Quantity] = getattr(beam, f"_d_b{index}_{face}", None)
        # Only a section detailed by a spacing carries one; a beam has no such
        # attribute and its layers keep reading as a number of bars.
        s: Optional[Quantity] = getattr(beam, f"_s_b{index}_{face}", None)
        if s is not None and s.magnitude == 0:
            s = None
        if n and d_b is not None and d_b.magnitude > 0:
            # As the section counts them: whole on a beam, width / s on a slab.
            # A beam's setters store the count as given, so a 2.0 from a
            # spreadsheet is made the 2 bars it is.
            layers.append(RebarLayer(n=n if s is not None else int(n), d_b=d_b, s=s))
    return tuple(layers)


def _face(beam: RectangularBeam, face: str) -> FlexureFaceDesign:
    suffix = "bot" if face == "b" else "top"
    # _A_s_bot is set when the section is built, so it always carries the area
    # unit of this beam and can seed the values a check may not have produced.
    zero: Quantity = 0 * beam._A_s_bot.units
    # Envelope over every combination that was checked, computed here rather than
    # accumulated during the loop: the beam's private attributes only describe the
    # combination that ran last, which is not necessarily the one that governs.
    worst = envelope_flexure_face(getattr(beam, "_flexure_checks", ()), "bottom" if face == "b" else "top")

    # A_s is the reinforcement the section carries, not a per-combination result.
    A_s: Optional[Quantity] = getattr(beam, f"_A_s_{suffix}", None)
    # Nothing checked means nothing to divide by; a zero moment in the display
    # unit of this section keeps the field a quantity either way.
    no_capacity: Quantity = to_display(0.0, "moment", beam.concrete.is_imperial)

    return FlexureFaceDesign(
        layers=_layers(beam, face),
        A_s=zero if A_s is None else A_s,
        A_s_req=zero if worst.A_s_req is None else worst.A_s_req,
        A_s_calc=zero if worst.A_s_calc is None else worst.A_s_calc,
        A_s_min=zero if worst.A_s_min is None else worst.A_s_min,
        A_s_min_eff=zero if worst.A_s_min_eff is None else worst.A_s_min_eff,
        A_s_max=zero if worst.A_s_max is None else worst.A_s_max,
        A_s_max_eff=zero if worst.A_s_max_eff is None else worst.A_s_max_eff,
        DCR=worst.DCR,
        M_capacity=no_capacity if worst.M_capacity is None else worst.M_capacity,
        options=_current_flexure_options(beam, face),
        admissible=worst.admissible,
    )


def _current_flexure_options(beam: RectangularBeam, face: str) -> Tuple[RebarOption, ...]:
    """The options of the last design of one face, if its layout is still on it.

    A design stores its options with the layout it applied first. Bars set by
    hand afterwards make them describe a section that is no longer there, so
    they are only reported while the first one is what the face carries.
    """
    options: Tuple[RebarOption, ...] = getattr(beam, f"_flexure_options_{face}", ())
    if not options or options[0].layers != _layers(beam, face):
        return ()
    return options


def _current_shear_options(beam: RectangularBeam) -> Tuple[StirrupOption, ...]:
    """The stirrup options of the last design, if its layout is still applied."""
    options: Tuple[StirrupOption, ...] = getattr(beam, "_shear_options", ())
    if not options:
        return ()
    first = options[0]
    if (
        first.n_stirrups != beam._stirrup_n
        or not math.isclose(first.d_b.to("mm").magnitude, beam._stirrup_d_b.to("mm").magnitude)
        or not math.isclose(first.s_l.to("mm").magnitude, beam._stirrup_s_l.to("mm").magnitude)
    ):
        return ()
    return options


def build_reinforcement(beam: RectangularBeam) -> SectionReinforcement:
    """Build the public view of the reinforcement ``beam`` currently carries.

    Never raises: a section always has *some* reinforcement state, even if that
    state is "none". This is what separates it from the design results, which
    only exist once a check has run.
    """
    # These are set when the section is built, so they always exist.
    return SectionReinforcement(
        bottom=FaceReinforcement(layers=_layers(beam, "b"), A_s=beam._A_s_bot),
        top=FaceReinforcement(layers=_layers(beam, "t"), A_s=beam._A_s_top),
        transverse=TransverseReinforcement(
            n_stirrups=beam._stirrup_n,
            d_b=beam._stirrup_d_b,
            s_l=beam._stirrup_s_l,
            A_v=beam._A_v,
            s_w=beam._leg_spacing_across_width(),
            layout=transverse_layout(beam),
        ),
    )


def build_flexure_design(beam: RectangularBeam) -> FlexureDesign:
    """Build the public flexure result of ``beam``.

    Raises:
        DesignNotRunError: if no flexure check or design has been run yet.
    """
    if not getattr(beam, "_flexure_checked", False):
        raise DesignNotRunError(
            "No flexure results yet. Run node.design() or node.check_flexure() before reading flexure_design."
        )
    return FlexureDesign(bottom=_face(beam, "b"), top=_face(beam, "t"))


def build_shear_design(beam: RectangularBeam) -> ShearDesign:
    """Build the public shear result of ``beam``.

    Raises:
        DesignNotRunError: if no shear check or design has been run yet.
    """
    if not getattr(beam, "_shear_checked", False):
        raise DesignNotRunError(
            "No shear results yet. Run node.design() or node.check_shear() before reading shear_design."
        )
    A_v: Quantity = beam._A_v
    zero: Quantity = 0 * A_v.units
    # As in _face: the private attributes describe the combination that ran last,
    # so the envelope is taken over the results of every combination checked.
    worst = envelope_shear(getattr(beam, "_shear_checks", ()))
    no_capacity: Quantity = to_display(0.0, "force", beam.concrete.is_imperial)
    s_max_l_support = _compression_support_spacing(beam)

    return ShearDesign(
        n_stirrups=beam._stirrup_n,
        d_b=beam._stirrup_d_b,
        s_l=beam._stirrup_s_l,
        A_v=A_v,
        A_v_req=zero if worst.A_v_req is None else worst.A_v_req,
        A_v_min=zero if worst.A_v_min is None else worst.A_v_min,
        DCR=worst.DCR,
        V_capacity=no_capacity if worst.V_capacity is None else worst.V_capacity,
        s_w=beam._leg_spacing_across_width(),
        layout=transverse_layout(beam),
        options=_current_shear_options(beam),
        s_max_l=_least([worst.s_max_l_table, s_max_l_support]),
        s_max_w=worst.s_max_w,
        s_max_l_table=worst.s_max_l_table,
        s_max_l_support=s_max_l_support,
    )


def _compression_support_spacing(beam: RectangularBeam) -> Optional[Quantity]:
    """The §9.7.6.4.3 cap on the stirrup spacing, or None where it does not apply.

    ACI 318-19 / CIRSOC 201-25 §9.7.6.4.3, through the code's
    ``stirrup_compression_support`` with the stirrup the section carries --
    the same call the warnings make. ``None`` for a code without the clause
    (EN 1992-1-1) and for a section that relies on no compression bars.
    """
    hook = design_code(beam.concrete).stirrup_compression_support
    support = None if hook is None else hook(beam, beam._stirrup_d_b)
    if support is None:
        return None
    s_max: Quantity = support.s_max.to(DISPLAY[beam.concrete.is_imperial]["length"])
    return s_max
