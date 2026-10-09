"""Structured warnings: the detailing limits a section does not meet.

The detailed reports mark these with a ❌ in their limit tables and a line of
text. A program reading a design needs them as data, so every check and design
also records them here::

    node.design()
    for warning in node.warnings:
        print(warning.code, warning.message, warning.values)

``code`` is stable -- compare against it, not against the message. ``message``
is written in the language set with :func:`mento.set_language` at the time the
warnings are read. ``values`` carries the numbers the message quotes, as pint
quantities.

A warning does not change a DCR. The DCR measures strength; these are the
limits around it -- minimum and maximum steel, spacing, bar fit -- which a
section can miss while still carrying its load, or meet while failing to.

Codes
-----
``As_below_min``
    A face carries less steel than its minimum, and the 4/3 relief of
    ACI 318-19 §9.6.1.3 / CIRSOC 201-25 §9.6.1.3 does not cover it. Its
    ``values`` carry ``A_s_min`` as the clause writes it -- the number
    ``flexure_design.<face>.A_s_min`` and the report's As,min column also
    carry -- and ``A_s_min_eff``, the one left after that relief, which is
    the one the face is short of and the one the message quotes. Where
    there is no relief (EN 1992-1-1, a slab, a footing) the two are equal.
``As_above_max``
    A face carries more steel than its maximum: under EN 1992-1-1, either
    face past the 4 % of §9.2.1.1(3).
``not_tension_controlled``
    Under ACI 318-19 and CIRSOC 201-25, the tension face is past the
    tension-controlled limit with the compression steel it has,
    ``A_s_max_eff``, which §9.3.3.1 (§7.3.3.1 for a one-way slab) does not
    allow. The section does not comply even where its DCR is below 1 -- the
    capacity already carries the lower phi of the strain it reaches -- and
    the flexure results say so with ``admissible`` / ``complies``. ``values``
    carries ``clause``, the article as text.
``clear_spacing_below_min``
    The clear distance between the bars of a beam face is below the minimum
    of ACI 318-19 / CIRSOC 201-25 §25.2.1: the bar diameter and the 25 mm /
    1 in. of the settings.
``clear_spacing_below_vibrator``
    The clear distance between the top bars of a beam meets §25.2.1 but
    leaves no room for the vibrator (``BeamSettings.vibrator_size``), so the
    concrete cannot be consolidated. Site practice rather than a clause, and
    a design never leaves it: what a check of bars set by hand reports.
``bar_spacing_below_min`` / ``bar_spacing_exceeds_max``
    The same for a slab, which is detailed centre to centre: the spacing of
    the layer nearest the face against the code's limits. A beam raises
    ``bar_spacing_exceeds_max`` too, on the face a combination puts in
    tension: the bars nearest it, centre to centre, against the crack-control
    cap of ACI 318-19 / CIRSOC 201-25 §24.3.2 that §9.7.2.2 sends them to.
``bars_do_not_fit``
    The bars on a face leave no clear space between them, or a design found no
    layout that fits the width -- which holds until the face is given bars by
    hand, since those are the spacing check's to judge.
``As_below_required``
    A design found no layout that fits the section and carries the moment, so
    it left the closest it found, and the section has to grow. It quotes the
    area the face was asked for and the one it was given, and stays while the
    design's results last: bars set by hand drop it. Only a face whose DCR is
    past 1 carries it; one that
    carries its moment but is not tension-controlled gets
    ``not_tension_controlled`` instead.
``section_too_small_for_moment``
    The same verdict for the section as a whole, with the numbers that
    decide it: no layout that fits the width -- the vibrator's gap between
    the top bars included -- and keeps within the code's limits on the
    reinforcement (tension-controlled under ACI 318-19 / CIRSOC 201-25
    §9.3.3.1, the 4 % of EN 1992-1-1 §9.2.1.1(3)) carries the moment. A
    design trades neither for strength. ``values`` carries ``M``, the moment
    of the combination and face furthest past DCR 1, and ``M_capacity``, what
    the layout the design kept carries there. No face or combination label;
    it goes with ``As_below_required`` and lasts as long.
``stirrups_required``
    The section has no stirrups, and a combination asks for shear
    reinforcement -- beyond what the concrete carries, or the code minimum.
``Av_below_min``
    The stirrups provide less than the minimum shear reinforcement.
``stirrup_spacing_exceeds_max``
    The stirrups are further apart than the code allows, along the member or
    across its width. ``values`` carries ``direction``, ``"l"`` (along) or
    ``"w"`` (across).

    There is no code for the stirrup diameter: neither ACI 318-19, CIRSOC
    201-25 nor EN 1992-1-1 states a minimum for a stirrup placed for shear
    alone, and the 10 mm (6 mm under CIRSOC) the shear catalogue starts at
    is a preference, not a clause. The minimum §9.7.6.4.2 does state is for
    the stirrups laterally supporting compression bars, a limit of its own.
``shear_exceeds_section_limit``
    The shear exceeds the most the section can carry however it is
    reinforced: under ACI 318-19 / CIRSOC 201-25 the Eq. (22.5.1.2) limit
    with the V_c of Table 22.5.5.1 for a section carrying A_v,min, under
    EN 1992-1-1 V_Rd,max of Eq. (6.9) at θ = 45°. Both are read the same with
    or without stirrups, so the warning means the section has to grow; a
    section that is only short of stirrups gets ``stirrups_required`` or
    ``Av_below_min`` instead. A wall reports it against ØVn,max of §11.5.4.2,
    or against V_Rd,max of Eq. (6.9) at θ = 45° under EN 1992-1-1.
``mesh_ratio_below_min``
    A wall mesh gives less than its direction asks for: the horizontal one
    below the ρt the shear needs (never below its minimum), the vertical one
    below ρl,min of ACI 318-19 / CIRSOC 201-25 §11.6.2, or below the
    0.002 A_c of EN 1992-1-1 §9.6.2(1). ``values`` carries ``direction``,
    ``"h"`` or ``"v"``.
``mesh_ratio_above_max``
    The vertical mesh of a wall gives more than its code allows: under
    EN 1992-1-1 §9.6.2(1), 0.04 A_c outside lap locations. ACI 318-19 and
    CIRSOC 201-25 state no such limit for a wall in Chapter 11.
    ``values`` carries ``direction``, always ``"v"``.
``mesh_spacing_exceeds_max``
    The bars of a wall mesh are further apart than the code allows. Under
    ACI 318-19 / CIRSOC 201-25 §11.7.2.1 (vertical) and §11.7.3.1
    (horizontal): the lesser of 3h and 450 mm (18 in.), and lw/3 and lw/5
    where shear reinforcement is required for in-plane strength, read as
    Vu > φVc for the combination. Under EN 1992-1-1: the lesser of 3t and
    400 mm for the vertical bars (§9.6.2(3)), 400 mm for the horizontal ones
    (§9.6.3(2)). ``values`` carries ``direction``, ``"h"`` or ``"v"``, and
    ``clause``, the clause the limit comes from, as text.
``stirrup_spacing_exceeds_compression_support``
    The section relies on compression steel and its stirrups are further
    apart than ACI 318-19 / CIRSOC 201-25 §9.7.6.4.3 allow the stirrups that
    brace it: the least of 16 d_b of the compression bar, 48 d_b of the
    stirrup and the least dimension of the beam. ``values`` names the bar it
    was read on, ``d_b_comp``, the thinnest on the face.
``stirrup_diameter_below_compression_support``
    The same section's stirrup is thinner than ACI 318-19 §9.7.6.4.2 /
    CIRSOC 201-25 Tabla 9.7.6.4.2 require to brace its thickest compression
    bar, ``d_b_comp``. Both come from the faces the last flexure check found
    a combination relying on as compression steel, so they need one to have
    run; they carry no combination label.
``stirrups_required_for_compression_support``
    A beam that relies on compression steel carries no stirrups at all.
    §9.7.6.4.1 of both codes asks for transverse reinforcement wherever
    compression reinforcement is required, whatever the shear, so the
    warning holds under any Vu. It quotes the smallest stirrup §9.7.6.4.2
    allows for the thickest compression bar, ``d_b_comp``, and the spacing
    §9.7.6.4.3 gives that stirrup, ``s_max``. No combination label, as
    above. A one-way slab is not held to it.

    §9.7.6.4.4 is checked separately by ``compression_detailing`` on the
    modelled first row: corner and alternate-bar support, and two-sided
    clear distances. Second-row support and differing CIRSOC
    limit outcomes remain explicitly pending, rather than silently passing.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Dict, List, Mapping, Optional, Tuple

from mento.bar_sizes import bar_designation, is_us_customary
from mento.codes.check_state import to_display
from mento.codes.registry import design_code
from mento.i18n import translate
from mento.precompute import DISPLAY
from mento.units import Quantity, inch, mm

if TYPE_CHECKING:
    from mento.beam import RectangularBeam
    from mento.forces import Forces
    from mento.wall_results import WallMesh, WallShearCheck


@dataclass(frozen=True)
class DesignWarning:
    """One detailing limit the section does not meet.

    ``code`` is the stable identifier (``"stirrup_spacing_exceeds_max"``);
    ``message`` the text, in the language set with :func:`mento.set_language`;
    ``values`` the numbers the message quotes, by name (``s``, ``s_max``,
    ``A_s``, ``A_s_min`` ...), as quantities -- and, for a limit read in one
    direction, that ``direction``, which the message words in the language
    of the day and the values keep as a code. ``face`` is ``"bottom"`` or
    ``"top"`` for a longitudinal warning and ``None`` otherwise, and
    ``combinations`` holds the labels of the load combinations the limit is
    missed under -- empty for a limit of the section alone, such as the bar
    spacing or the stirrup diameter.
    """

    code: str
    message: str
    values: Mapping[str, Any] = field(default_factory=dict)
    face: Optional[str] = None
    combinations: Tuple[str, ...] = ()

    def __str__(self) -> str:
        return self.message


@dataclass
class _Raw:
    """A warning as the check found it, before it is worded.

    Kept apart from :class:`DesignWarning` so the message is written when it
    is read, in the language in force then, and so the same limit missed under
    several combinations collapses into one warning.
    """

    code: str
    values: Dict[str, Any]
    face: Optional[str] = None
    combination: Optional[str] = None
    #: How far past its limit this occurrence is; of the same limit missed under
    #: several combinations, the furthest is the one reported.
    severity: float = 0.0


#: The English wording of each code; the text is also the key of the Spanish
#: catalog in :mod:`mento.i18n`. ``{face}`` is filled with the translated face.
_MESSAGES: Dict[str, str] = {
    "transverse_legs_added_for_compression_support": "Detailing proposes {placed_legs} legs instead of {input_legs}: {pieces}. Enter the proposed legs to confirm; A_v still uses {input_legs}.",
    "open_leg_anchorage_outside_model": "Open-leg hooks and anchorage are outside this sectional model; verify them separately.",
    "crosstie_alternation_required": "135°/90° crossties: alternate the 90° ends along the member; seismic detailing not verified.",
    "cage_detailing_infeasible": "The base cage cannot be detailed: {reason}",
    "cage_detailing_pending": "The base cage cannot yet be verified: {reason}",
    "compression_detailing_en_pending": "EN compression-bar support (§9.2.1.2(3), 15φ) is not verified by Mento.",
    "compression_detailing_failed": "Required compression-bar support fails (§9.7.6.4.4): {reason}.",
    "compression_detailing_pending": "Required compression-bar support is not fully verified (§9.7.6.4.4): {reason}.",
    "As_below_min": (
        "Steel on the {face}: A_s = {A_s} is below the minimum it has to meet, A_s,min,eff = {A_s_min_eff}."
    ),
    "As_above_max": "Steel on the {face}: A_s = {A_s} exceeds the maximum A_s,max = {A_s_max}.",
    "not_tension_controlled": (
        "The section is not tension-controlled (§{clause}): A_s = {A_s} on the {face} exceeds "
        "A_s,max = {A_s_max}. It does not comply, even where its capacity covers the moment."
    ),
    "clear_spacing_below_min": "Clear spacing between the bars on the {face}: {s} is below the minimum {s_min}.",
    "bar_spacing_below_min": "Bar spacing on the {face}: {s} is below the minimum {s_min}.",
    "bar_spacing_exceeds_max": "Bar spacing on the {face}: {s} exceeds the maximum {s_max}.",
    "bars_do_not_fit": "The bars on the {face} do not fit in the width of the section.",
    "As_below_required": (
        "Steel on the {face}: no layout that fits the section carries the moment "
        "(A_s,req = {A_s_req}); the design left A_s = {A_s}. Enlarge the section."
    ),
    "section_too_small_for_moment": (
        "No layout that fits the section, with room for the vibrator between the top bars, and keeps within "
        "the code's limits on the reinforcement carries M = {M}: the closest one carries {M_capacity}. "
        "Enlarge the section."
    ),
    "clear_spacing_below_vibrator": (
        "Clear spacing between the bars on the {face}: {s} leaves no room for the vibrator, {s_min}. "
        "The concrete cannot be consolidated."
    ),
    "stirrups_required": "The section has no stirrups and requires shear reinforcement A_v = {A_v_req}.",
    "force_component_not_checked": (
        "{component} = {value} is given but not checked: this element reads only N_x, V_z and M_y."
    ),
    "Av_below_min": "The stirrups provide A_v = {A_v}, below the minimum A_v,min = {A_v_min}.",
    "stirrup_spacing_exceeds_max_l": "Stirrup spacing along the member: {s} exceeds the maximum {s_max}.",
    "stirrup_spacing_exceeds_max_w": "Stirrup leg spacing across the width: {s} exceeds the maximum {s_max}.",
    "shear_exceeds_section_limit": "Shear V = {V} exceeds the most the section can carry, {V_max}: enlarge the section.",
    "mesh_ratio_below_min_h": "Horizontal wall mesh: ρt = {rho} is below the required ρt = {rho_min}.",
    "mesh_ratio_below_min_v": "Vertical wall mesh: ρl = {rho} is below the minimum ρl,min = {rho_min}.",
    "mesh_ratio_above_max_v": "Vertical wall mesh: ρl = {rho} exceeds the maximum ρl,max = {rho_max}.",
    "mesh_spacing_exceeds_max_h": "Horizontal wall mesh spacing: {s} exceeds the maximum {s_max} ({clause}).",
    "mesh_spacing_exceeds_max_v": "Vertical wall mesh spacing: {s} exceeds the maximum {s_max} ({clause}).",
    "stirrup_spacing_exceeds_compression_support": (
        "Stirrup spacing along the member: {s} exceeds the {s_max} that lateral support of the "
        "{d_b_comp} compression bars allows (16 d_b, 48 d_b of the stirrup, least dimension of the beam)."
    ),
    "stirrup_diameter_below_compression_support": (
        "Stirrup diameter {d_b} is below the minimum {d_b_min} that lateral support of "
        "{d_b_comp} compression bars requires."
    ),
    "stirrups_required_for_compression_support": (
        "The section relies on {d_b_comp} compression bars and has no stirrups to brace them: "
        "closed stirrups of at least {d_b_min} at no more than {s_max} are required."
    ),
}

_FACES = {"bottom": "bottom face", "top": "top face"}


def _format(value: Any, digits: int = 3) -> str:
    """A value as the messages print it, to ``digits`` significant figures.

    Everything a warning quotes is a quantity -- an area, a spacing, a force --
    so there is one format, and pint's ``~P`` writes the unit with it. A
    reinforcement ratio is the exception, a bare number.
    """
    if not isinstance(value, Quantity):
        return f"{value:.{digits}g}"
    return f"{value:.{digits}g~P}"


def _fields(values: Mapping[str, Any]) -> Dict[str, str]:
    """The values of one message, printed so that the message reads true.

    Three significant figures, or as many more as it takes for two values
    that differ to print differently: a spacing of 13.00 cm against a limit
    of 12.95 cm printed as "13 cm exceeds the maximum 13 cm" at three. The
    triggers already leave out a value equal to its limit, so a message
    always has a difference to show.
    """
    items = list(values.items())
    for digits in range(3, 10):
        fields = {name: _format(value, digits) for name, value in items}
        # pint answers ``!=`` across units, and against a bare number, with
        # True rather than an error, so the pairs need no sorting by kind.
        if all(
            fields[a] != fields[b]
            for i, (a, first) in enumerate(items)
            for b, second in items[i + 1 :]
            if first != second
        ):
            break
    # A bar is named, not measured: "#6" in US customary, and a compression bar
    # "Ø16 mm" in SI, the symbol travelling with the value so that one template
    # serves both.
    for name, value in items:
        if not (name.startswith("d_b") and isinstance(value, Quantity)):
            continue
        if is_us_customary(value):
            fields[name] = bar_designation(value)
        elif name == "d_b_comp":
            fields[name] = f"Ø{fields[name]}"
    return fields


def _q(value: float, kind: str, beam: "RectangularBeam") -> Quantity:
    """A float of a check state back as a quantity in the section's display units."""
    return to_display(value, kind, beam.concrete.is_imperial)


def _shown(values: Dict[str, Any], beam: "RectangularBeam") -> Dict[str, Any]:
    """The values in the units the detailed reports print them in.

    Chosen by name: ``A_s*`` is an area, ``A_v*`` an area per length, ``s*`` a
    spacing, ``d_b*`` a bar diameter, ``V*`` a force. Anything else is left as
    it is.
    """
    units = DISPLAY[beam.concrete.is_imperial]
    kinds: Tuple[Tuple[str, Any], ...] = (
        ("A_s", units["area"]),
        ("A_v", units["per_length"]),
        ("d_b", inch if beam.concrete.is_imperial else mm),
        ("s", units["length"]),
        ("V", units["force"]),
    )
    shown = {}
    for name, value in values.items():
        unit = next((unit for prefix, unit in kinds if name.startswith(prefix)), None)
        shown[name] = value.to(unit) if isinstance(value, Quantity) and unit is not None else value
    return shown


def _with_units(raw: _Raw, beam: "RectangularBeam") -> _Raw:
    raw.values = _shown(raw.values, beam)
    return raw


def _face_name(suffix: str) -> str:
    return "bottom" if suffix in ("bot", "b") else "top"


def combination_label(label: Optional[str], position: int) -> str:
    """The name a warning files a combination under.

    The force's own label where it has one; ``#n``, its position among the
    forces checked, where it has none (``Forces.label`` defaults to
    ``None``). A limit missed under a combination then always names it, so
    that an empty ``combinations`` means what it says -- a limit of the
    section alone -- and not "a combination with no label", which it also
    used to mean.
    """
    return label if label is not None else f"#{position}"


# ---------------------------------------------------------------------------
# What a flexure check leaves
# ---------------------------------------------------------------------------


def steel_above_maximum(beam: "RectangularBeam", state: Any) -> Dict[str, Tuple[Quantity, Quantity]]:
    """The faces one flexure combination finds past their maximum steel, with ``(A_s, limit)``.

    Which maximum, and on which face, is the code's. Where it is the
    ductility limit of the tension steel (ACI 318-19 / CIRSOC 201-25
    §9.3.3.1, §7.3.3.1 for a one-way slab) only the face the combination
    puts in tension is held to it -- the bars a negative moment asks for on
    the bottom are compression steel, and a combination with no moment pulls
    neither face -- and the limit is ``A_s_max_eff``, which the compression
    steel opposite extends: a doubly reinforced face is judged by the strain
    it reaches, not excused. Past it the section is not tension-controlled,
    which those clauses do not allow, so it does not comply whatever its
    DCR. Where the maximum caps any bars (EN 1992-1-1 §9.2.1.1(3)) both
    faces are read against it.

    Keyed ``"bot"`` / ``"top"``. The warnings and the ``admissible`` flag of
    the flexure results both read it, so the two never disagree.
    """
    ductility_limit = design_code(beam.concrete).max_steel_is_ductility_limit
    doubly = bool(getattr(state, "doubly_reinforced", False))
    M = getattr(state, "M_u", getattr(state, "M_Ed", 0.0))
    tension_face = "bot" if M > 0 else "top" if M < 0 else None
    over: Dict[str, Tuple[Quantity, Quantity]] = {}
    for suffix in ("bot", "top"):
        A_s: Quantity = getattr(beam, f"_A_s_{suffix}")
        if ductility_limit:
            limit = getattr(state, f"A_s_max_eff_{suffix}")
            applies = suffix == tension_face
        else:
            limit = getattr(state, f"A_s_max_{suffix}")
            applies = not doubly
        A_s_max = _q(limit, "area", beam).to(A_s.units)
        if applies and A_s_max.magnitude > 0 and A_s > A_s_max and not math.isclose(A_s.magnitude, A_s_max.magnitude):
            over[suffix] = (A_s, A_s_max)
    return over


def flexure_warnings(beam: "RectangularBeam", label: str, state: Any) -> List[_Raw]:
    """The steel-area limits one flexure combination finds on each face.

    Mirrors the limit rows of the detailed report: a face below its minimum
    warns unless the 4/3 relief of ACI 318-19 §9.6.1.3 covers it, and a face
    above its maximum warns (:func:`steel_above_maximum`) -- as
    ``not_tension_controlled`` under ACI 318-19 / CIRSOC 201-25, whose
    maximum is the tension-controlled limit, and as ``As_above_max`` under
    EN 1992-1-1.
    """
    found: List[_Raw] = []
    ductility_limit = design_code(beam.concrete).max_steel_is_ductility_limit
    over = steel_above_maximum(beam, state)
    M = getattr(state, "M_u", getattr(state, "M_Ed", 0.0))
    tension_face = "bot" if M > 0 else "top" if M < 0 else None
    for suffix in ("bot", "top"):
        A_s: Quantity = getattr(beam, f"_A_s_{suffix}")
        # The minimum as the clause writes it, and the one the face has to
        # meet, relief of §9.6.1.3 included; a code with no relief
        # (EN 1992-1-1) has no second number and leaves it at A_s_min. The
        # two go out under their own names: ``flexure_design.<face>.A_s_min``
        # and the report's As,min column carry the clause value, so the
        # warning cannot file the relieved one under the same name.
        A_s_min = _q(getattr(state, f"A_s_min_{suffix}"), "area", beam).to(A_s.units)
        A_s_min_eff = _q(getattr(state, f"A_s_min_eff_{suffix}", getattr(state, f"A_s_min_{suffix}")), "area", beam)
        A_s_min_eff = A_s_min_eff.to(A_s.units)
        if A_s < A_s_min_eff and not math.isclose(A_s.magnitude, A_s_min_eff.magnitude):
            found.append(
                _Raw(
                    "As_below_min",
                    {"A_s": A_s, "A_s_min": A_s_min, "A_s_min_eff": A_s_min_eff},
                    _face_name(suffix),
                    label,
                    severity=float((A_s_min_eff - A_s).magnitude),
                )
            )
        if suffix in over:
            A_s_max = over[suffix][1]
            # The clause the tension-controlled limit comes from travels with
            # the warning as text: §9.3.3.1 for a beam, §7.3.3.1 for a slab.
            code, values = (
                ("not_tension_controlled", {"A_s": A_s, "A_s_max": A_s_max, "clause": beam._tension_controlled_clause})
                if ductility_limit
                else ("As_above_max", {"A_s": A_s, "A_s_max": A_s_max})
            )
            found.append(_Raw(code, values, _face_name(suffix), label, severity=float((A_s - A_s_max).magnitude)))
    # The bars nearest the tension face of a beam against the crack-control
    # cap of ACI 318-19 / CIRSOC 201-25 §24.3.2, which §9.7.2.2 sends them to:
    # the spacing the report prints (:meth:`RectangularBeam._tension_bar_spacing`),
    # on the face this combination pulls. A slab carries that cap inside the
    # spacing limit :func:`spacing_warnings` reads, and a code without it
    # (EN 1992-1-1) has no row.
    if tension_face is not None:
        row = beam._tension_bar_spacing("b" if tension_face == "bot" else "t")
        if row is not None:
            s, s_max = row[0], row[1].to(row[0].units)
            if s > s_max and not math.isclose(s.magnitude, s_max.magnitude):
                found.append(
                    _Raw(
                        "bar_spacing_exceeds_max",
                        {"s": s, "s_max": s_max},
                        _face_name(tension_face),
                        label,
                        severity=float((s - s_max).magnitude),
                    )
                )
    return [_with_units(raw, beam) for raw in found]


def spacing_warnings(beam: "RectangularBeam") -> List[_Raw]:
    """The bar-spacing limits of the section itself, whatever the forces.

    Uses the same rows as the detailed report
    (:func:`mento.reports.tables._bar_spacing_row`): the clear distance of a
    beam face against its minimum, the centre-to-centre spacing of a slab
    against both of its limits.
    """
    from mento.reports.tables import _bar_spacing_row

    settings = beam.settings
    assert settings is not None
    found: List[_Raw] = []
    for face, suffix in (("t", "top"), ("b", "bot")):
        name = _face_name(suffix)
        layers = beam.reinforcement.top.layers if face == "t" else beam.reinforcement.bottom.layers
        if not layers:
            continue
        d_b_max = max(layer.d_b for layer in layers)
        is_slab = getattr(beam, f"_s_b1_{face}", None) is not None
        # The clear distance of §25.2.1 (ACI 318-19 / CIRSOC 201-25): the bar
        # and 25 mm / 1 in. A beam reports the vibrator's gap between its top
        # bars apart, ``clear_spacing_below_vibrator``: site practice, not a
        # clause, though a design holds the top to it all the same. A slab,
        # detailed centre to centre, keeps the two in one minimum.
        minimum = max(settings.clear_spacing, d_b_max)
        vibrator = settings.vibrator_size if face == "t" else None
        if vibrator is not None and is_slab:
            minimum = max(minimum, vibrator)
        _label, value, s_min, s_max = _bar_spacing_row(beam, face, minimum)
        if not is_slab and value.magnitude <= 0 and sum(layer.n for layer in layers) > 1:
            found.append(_Raw("bars_do_not_fit", {"s": value}, name))
            continue
        # A beam layer with one bar has no pair to measure: what the row
        # carries for it is the room beside the bar, not a distance between
        # bars, and there is no minimum for it to miss.
        measurable = is_slab or bars_side_by_side(beam, face)
        if (
            measurable
            and s_min is not None
            and value < s_min
            and not math.isclose(value.magnitude, s_min.to(value.units).magnitude)
        ):
            code = "bar_spacing_below_min" if is_slab else "clear_spacing_below_min"
            found.append(_Raw(code, {"s": value, "s_min": s_min}, name))
        elif (
            measurable
            and s_min is not None
            and vibrator is not None
            and not is_slab
            and value < vibrator
            and not math.isclose(value.magnitude, vibrator.to(value.units).magnitude)
        ):
            found.append(_Raw("clear_spacing_below_vibrator", {"s": value, "s_min": vibrator}, name))
        if s_max is not None and value > s_max and not math.isclose(value.magnitude, s_max.to(value.units).magnitude):
            found.append(_Raw("bar_spacing_exceeds_max", {"s": value, "s_max": s_max}, name))
    for face in sorted(getattr(beam, "_infeasible_faces", ())):
        name = _face_name(face)
        if not any(raw.code == "bars_do_not_fit" and raw.face == name for raw in found):
            found.append(_Raw("bars_do_not_fit", {}, name))
    return [_with_units(raw, beam) for raw in found]


def bars_side_by_side(beam: "RectangularBeam", face: str) -> bool:
    """Whether some layer of the face holds two bars, so a clear spacing exists.

    Groups 1 and 2 share the layer nearest the face, groups 3 and 4 the one
    behind it; one bar in each layer sits above the other, not beside it.
    ``face`` is ``"b"`` or ``"t"``.
    """
    nearest = getattr(beam, f"_n1_{face}") + getattr(beam, f"_n2_{face}")
    behind = getattr(beam, f"_n3_{face}") + getattr(beam, f"_n4_{face}")
    return max(nearest, behind) >= 2


def shortfall_warnings(beam: "RectangularBeam") -> List[_Raw]:
    """The faces the last design could not bring up to what they need.

    The design records, per face, the area it asked for and the one it left.
    Bars or stirrups changed by hand afterwards are a different section, and
    the setters drop the record with the rest of the design's results.

    Only a face that is short of its moment is reported: one whose DCR, the
    worst over the combinations checked, is past 1. A face at or below it
    is not short of anything the warning could name -- the compression face
    of a doubly reinforced section, whose A_s,req is the compression steel
    the other face would need and could reach hundreds of cm², or a face
    that carries its moment but is not tension-controlled, which
    ``not_tension_controlled`` reports.
    """
    found: List[_Raw] = []
    checks = getattr(beam, "_flexure_checks", ())
    for suffix, (needed, _placed) in sorted(getattr(beam, "_short_faces", {}).items()):
        A_s: Quantity = getattr(beam, f"_A_s_{suffix}")
        if checks and max(getattr(check, _face_name(suffix)).DCR for check in checks) <= 1.0:
            continue
        found.append(_Raw("As_below_required", {"A_s": A_s, "A_s_req": needed.to(A_s.units)}, _face_name(suffix)))
    # The section as a whole: the design is limited by what fits and what the
    # code allows, not by the steel it could have asked for, so it quotes the
    # moment and the most the layout it kept carries -- of the face and
    # combination furthest past DCR 1.
    worst: Optional[Any] = None
    for check in checks if found else ():
        for face in (check.bottom, check.top):
            if face.DCR > 1.0 and face.M_capacity is not None and (worst is None or face.DCR > worst.DCR):
                worst = face
    if worst is not None:
        M_capacity: Quantity = worst.M_capacity
        values = {"M": worst.DCR * M_capacity, "M_capacity": M_capacity}
        found.append(_Raw("section_too_small_for_moment", values, None, severity=worst.DCR))
    return [_with_units(raw, beam) for raw in found]


# ---------------------------------------------------------------------------
# What a shear check leaves
# ---------------------------------------------------------------------------


def shear_warnings(beam: "RectangularBeam", label: str, state: Any) -> List[_Raw]:
    """The transverse-reinforcement limits one shear combination finds.

    Mirrors the limit rows of the detailed report -- spacing along and across,
    the minimum area and, where the code states one, the minimum diameter --
    and adds the ones a section without stirrups or with too small a web runs
    into.
    """
    found: List[_Raw] = []
    A_v: Quantity = beam._A_v
    A_v_min = _q(state.A_v_min, "per_length", beam).to(A_v.units)
    A_v_req = _q(state.A_v_req, "per_length", beam).to(A_v.units)

    # Against the limit of the section itself, not the ``max_shear_ok`` of the
    # report row: that row reads the section as it is, and both codes give a
    # section short of stirrups a lower ceiling than the same section with
    # them -- ACI 318-19 Table 22.5.5.1 raises V_c once A_v >= A_v,min, and a
    # bare EN section is checked against V_Rd,c. Only past the limit with
    # stirrups in is "enlarge the section" the advice; short of it the advice
    # is the stirrups, which ``stirrups_required`` and ``Av_below_min`` give.
    V = _q(state.V_u if hasattr(state, "V_u") else state.V_Ed_1, "force", beam)
    V_limit = _q(state.section_shear_limit, "force", beam).to(V.units)
    if V > V_limit and not math.isclose(V.magnitude, V_limit.magnitude):
        found.append(
            _Raw(
                "shear_exceeds_section_limit",
                {"V": V, "V_max": V_limit},
                None,
                label,
                severity=float((V - V_limit).magnitude),
            )
        )

    support_hook = design_code(beam.concrete).stirrup_compression_support
    if int(beam._stirrup_n) == 0 or A_v.magnitude == 0:
        if A_v_req.magnitude > 0:
            found.append(
                _Raw(
                    "stirrups_required",
                    {"A_v_req": A_v_req, "A_v_min": A_v_min},
                    None,
                    label,
                    severity=float(A_v_req.magnitude),
                )
            )
        # ACI 318-19 / CIRSOC 201-25 §9.7.6.4.1: transverse reinforcement
        # wherever longitudinal compression reinforcement is required,
        # whatever the shear -- so a bare doubly reinforced beam misses the
        # clause even where the concrete carries Vu. Quoted with the smallest
        # stirrup §9.7.6.4.2 allows, the one whose 48 d_b §9.7.6.4.3 reads. A
        # slab strip is not held to it: the hook answers None for one, since
        # the clause is the beams' (§7.7.5.1 sends a one-way slab to §9.7.6.2).
        if support_hook is not None:
            support = support_hook(beam, beam._stirrup_d_b)
            if support is not None:
                support = support_hook(beam, support.d_b_min)
                values = {"d_b_comp": support.d_b_comp_diameter, "d_b_min": support.d_b_min, "s_max": support.s_max}
                found.append(_Raw("stirrups_required_for_compression_support", values, None))
        return [_with_units(raw, beam) for raw in found]

    if A_v < A_v_min and not math.isclose(A_v.magnitude, A_v_min.magnitude):
        found.append(
            _Raw(
                "Av_below_min",
                {"A_v": A_v, "A_v_min": A_v_min},
                None,
                label,
                severity=float((A_v_min - A_v).magnitude),
            )
        )

    s_l: Quantity = beam._stirrup_s_l
    s_w: Quantity = beam._leg_spacing_across_width()
    s_max_l = _q(state.stirrup_s_max_l, "length", beam).to(s_l.units)
    s_max_w = _q(state.stirrup_s_max_w, "length", beam).to(s_l.units)
    for direction, s, s_max in (("l", s_l, s_max_l), ("w", s_w.to(s_l.units), s_max_w)):
        if s_max.magnitude > 0 and s > s_max and not math.isclose(s.magnitude, s_max.magnitude):
            found.append(
                _Raw(
                    "stirrup_spacing_exceeds_max",
                    {"s": s, "s_max": s_max, "direction": direction},
                    None,
                    label,
                    severity=float((s - s_max).magnitude),
                )
            )

    # No minimum diameter for shear alone: neither code states one for a
    # stirrup placed for shear only. The registry's ``min_stirrup_diameter``
    # is the bottom of the code's catalogue -- a design preference the report
    # row quotes. ACI 318-19 §9.7.6.4.2 / CIRSOC 201-25 §9.7.6.4.2 size only
    # the stirrups of §9.7.6.4.1, those laterally supporting compression bars:
    # a limit of its own, read next.

    # A doubly reinforced section's stirrups also brace its compression bars,
    # and ACI 318-19 / CIRSOC 201-25 §9.7.6.4 size and space them for that.
    # Which bars those are is the flexure check's finding, not this
    # combination's, so both limits are read off the section: no label.
    support = None if support_hook is None else support_hook(beam, beam._stirrup_d_b)
    if support is not None:
        s_support = support.s_max.to(s_l.units)
        if s_l > s_support and not math.isclose(s_l.magnitude, s_support.magnitude):
            values = {"s": s_l, "s_max": s_support, "d_b_comp": support.d_b_comp_spacing}
            found.append(_Raw("stirrup_spacing_exceeds_compression_support", values, None))
        d_b_support: Quantity = support.d_b_min.to(beam._stirrup_d_b.units)
        if beam._stirrup_d_b < d_b_support and not math.isclose(beam._stirrup_d_b.magnitude, d_b_support.magnitude):
            values = {"d_b": beam._stirrup_d_b, "d_b_min": d_b_support, "d_b_comp": support.d_b_comp_diameter}
            found.append(_Raw("stirrup_diameter_below_compression_support", values, None))
    return [_with_units(raw, beam) for raw in found]


# ---------------------------------------------------------------------------
# What a wall shear check leaves
# ---------------------------------------------------------------------------


def wall_warnings(wall: "RectangularBeam", mesh: "WallMesh", checks: Tuple["WallShearCheck", ...]) -> List[_Raw]:
    """The mesh limits a wall misses, over every combination checked.

    Mirrors the limit rows of the wall report: each ratio against what its
    direction asks for, the vertical one against its maximum where the code
    states one, each spacing against its maximum, and the shear against the
    most the section can carry. A mesh with a zero spacing has no bars, so its
    spacing is not a limit it misses; its ratio is. The spacing warning quotes
    the clause its limit comes from, which is the code's.
    """
    clauses = design_code(wall.concrete).wall_mesh_spacing_clauses
    found: List[_Raw] = []
    for position, check in enumerate(checks, 1):
        label = combination_label(check.label, position)
        for direction, provided, required in (
            ("h", mesh.horizontal, check.rho_t_req),
            ("v", mesh.vertical, check.rho_l_min),
        ):
            if provided.rho < required and not math.isclose(provided.rho, required, rel_tol=1e-9):
                values = {"direction": direction, "rho": round(provided.rho, 5), "rho_min": round(required, 5)}
                found.append(_Raw("mesh_ratio_below_min", values, None, label, required - provided.rho))
        rho_max = check.rho_l_max
        if rho_max is not None and mesh.vertical.rho > rho_max and not math.isclose(mesh.vertical.rho, rho_max):
            values = {"direction": "v", "rho": round(mesh.vertical.rho, 5), "rho_max": round(rho_max, 5)}
            found.append(_Raw("mesh_ratio_above_max", values, None, None, mesh.vertical.rho - rho_max))
        for direction, provided, s_max in (
            ("h", mesh.horizontal, check.s_h_max),
            ("v", mesh.vertical, check.s_v_max),
        ):
            s_max = s_max.to(provided.s.units)
            if provided.has_bars and provided.s > s_max and not math.isclose(provided.s.magnitude, s_max.magnitude):
                values = {"direction": direction, "s": provided.s, "s_max": s_max, "clause": clauses.get(direction, "")}
                found.append(
                    _Raw("mesh_spacing_exceeds_max", values, None, None, float((provided.s - s_max).magnitude))
                )
        # As for a beam: a V_u that differs from ØVn,max by rounding alone --
        # the limit worked out apart and passed in -- is at the limit, not past it.
        V_max = check.V_max.to(check.V_u.units)
        if check.V_u > V_max and not math.isclose(check.V_u.magnitude, V_max.magnitude):
            values = {"V": check.V_u, "V_max": check.V_max}
            severity = float((check.V_u - V_max).magnitude)
            found.append(_Raw("shear_exceeds_section_limit", values, None, label, severity))
    return [_with_units(raw, wall) for raw in found]


# ---------------------------------------------------------------------------
# Wording
# ---------------------------------------------------------------------------


#: The components of a Forces that no check of a beam, slab, footing or wall reads.
_UNREAD_COMPONENTS = ("V_y", "M_x", "M_z")


def unread_force_warnings(force: "Forces", label: str) -> List[_Raw]:
    """The components ``force`` gives that the check passes over, one per component.

    A beam is checked for ``N_x``, ``V_z`` and ``M_y``. ``V_y``, ``M_z`` and the
    torsion ``M_x`` are there for the full demand of a section; given to a beam
    they are not wrong, but nothing verifies them, and a DCR below 1 would
    otherwise read as if it did.
    """
    found: List[_Raw] = []
    for name in _UNREAD_COMPONENTS:
        value = getattr(force, name)
        if value.magnitude != 0:
            found.append(
                _Raw(
                    "force_component_not_checked",
                    {"component": name, "value": value},
                    None,
                    label,
                    severity=abs(float(value.magnitude)),
                )
            )
    return found


def collect(raws: List[_Raw]) -> Tuple[DesignWarning, ...]:
    """Collapse the raw findings into one worded warning per limit and face.

    The same limit missed under several combinations is one warning, with the
    values of the combination that misses it by most and the labels of all of
    them.
    """
    groups: Dict[Tuple[str, Optional[str], Optional[str], Optional[str]], List[_Raw]] = {}
    for raw in raws:
        # A force component is a limit of its own, as a direction is.
        key = (raw.code, raw.face, raw.values.get("direction"), raw.values.get("component"))
        groups.setdefault(key, []).append(raw)

    warnings: List[DesignWarning] = []
    for (code, face, direction, _component), group in groups.items():
        worst = max(group, key=lambda raw: raw.severity)
        labels = tuple(dict.fromkeys(raw.combination for raw in group if raw.combination is not None))
        # The direction picks the template and stays in the values, where a
        # program reads it; it is a word, not a number to print.
        values = dict(worst.values)
        template = _MESSAGES[f"{code}_{direction}" if direction else code]
        # A text value (the clause a limit comes from) is quoted as it is, in
        # the language of the day where it carries words.
        fields = _fields({n: v for n, v in values.items() if n != "direction" and not isinstance(v, str)})
        fields.update({n: translate(v) for n, v in values.items() if n != "direction" and isinstance(v, str)})
        if face is not None:
            fields["face"] = translate(_FACES[face])
        warnings.append(
            DesignWarning(
                code=code,
                message=translate(template, **fields),
                values=MappingProxyType(values),
                face=face,
                combinations=labels,
            )
        )
    return tuple(warnings)


def compression_detailing_warnings(beam: "RectangularBeam") -> List[_Raw]:
    """Required compression bars: modelled §9.7.6.4.4 failures or pending checks."""
    result = beam.compression_detailing
    if result.status not in ("failed", "pending"):
        return []
    if beam.concrete.design_code == "EN 1992-2004":
        return [_Raw("compression_detailing_en_pending", {})]
    if result.reason == "flexure_not_checked":
        return []  # Existing plot caption says verification is pending.
    if not result.faces:
        return [
            _Raw(
                "compression_detailing_pending" if result.status == "pending" else "compression_detailing_failed",
                {"reason": translate(_COMPRESSION_REASONS.get(result.reason, result.reason)).rstrip(".")},
            )
        ]
    return [
        _Raw(
            "compression_detailing_" + item.status,
            {
                "reason": "; ".join(translate(_COMPRESSION_REASONS[reason]) for reason in item.reasons),
                "distance": item.maximum_clear_distance,
            },
            face=item.face,
        )
        for item in result.faces
        if item.status in ("failed", "pending")
    ]


_COMPRESSION_REASONS = {
    "corner_bar_unbraced": "A corner bar is not braced by a stirrup corner",
    "alternate_bars_unbraced": "Two successive compression bars lack corner support",
    "bar_outside_closed_stirrup": "A required compression bar lies outside the closed stirrup",
    "clear_distance_exceeded": "The clear distance on a side exceeds the permitted limit",
    "cirsoc_limit_interpretation": "The 15 d_be and 150 mm limits give different outcomes; interpretation pending",
    "second_row_support_not_modelled": "Second-row compression support requires a separate detail",
    "crosstie_anchorage_not_verified": "Crosstie anchorage is not verified",
    "crosstie_hook_rule_not_modelled": "The crosstie hook size is outside the supported model",
    "first_row_missing": "The required first compression row is missing",
    "closed_stirrups_missing": "Required compression steel has no closed stirrups",
    "unsupported_bend": "The stirrup bend is outside the supported model",
}


def cage_detailing_warnings(beam: "RectangularBeam") -> List[_Raw]:
    """Diagnóstico geométrico, separado de los cálculos resistentes."""
    from mento.cage_detailing import CageDetailingError, build_cage_detailing

    if beam._stirrups_optional or not beam._stirrup_n:
        return []
    try:
        build_cage_detailing(beam)
    except CageDetailingError as error:
        code = (
            "cage_detailing_pending"
            if error.reason in ("unsupported_bend", "compression_support_search")
            else "cage_detailing_infeasible"
        )
        return [_Raw(code, {"reason": str(error)})]
    return []


def transverse_proposal_warnings(beam: "RectangularBeam") -> List[_Raw]:
    """La propuesta de jaula no modifica la entrada ni aprueba ramas no confirmadas."""
    from mento.cage_detailing import CageDetailingError, build_cage_detailing

    if beam._stirrups_optional or not beam._stirrup_n:
        return []
    try:
        geometry = build_cage_detailing(beam, include_skin=False)
    except CageDetailingError:
        return []
    result = []
    entered = int(2 * beam._stirrup_n)
    placed = len(geometry.leg_x)
    if placed != entered:
        result.append(
            _Raw(
                "transverse_legs_added_for_compression_support",
                {"input_legs": entered, "placed_legs": placed, "pieces": geometry.arrangement()},
            )
        )
    if any(t.extension is not None and t.alternate_hooks for t in geometry.crossties):
        result.append(_Raw("crosstie_alternation_required", {}))
    if any(t.extension is None for t in geometry.crossties):
        result.append(_Raw("open_leg_anchorage_outside_model", {}))
    return result
