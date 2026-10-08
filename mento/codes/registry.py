"""What a design code has to provide, and which ones provide it.

Every element used to dispatch by comparing ``concrete.design_code`` against a
string literal -- in :mod:`mento.beam`, :mod:`mento.shear_wall`,
:mod:`mento.rebar` and the summaries -- so adding a code meant finding and
editing each of those chains, and forgetting one failed silently at runtime
rather than at import.

A code declares itself here instead. :class:`DesignCode` is the whole contract:
if a new code fills one in and registers it, every element picks it up, and
``tests/test_architecture_boundaries.py`` fails the build if an element ever
grows a string comparison again.

The hooks are plain functions rather than methods on a class, matching how
``codes/`` is already written (ADR-0002): the code modules hold free functions
typed as ``self: RectangularBeam``, and a registry of them adds no indirection
that has to be stepped through when reading a check.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Dict, Tuple, Type

from mento.precompute import unit_label

if TYPE_CHECKING:
    from mento.material import Concrete


@dataclass(frozen=True)
class DesignCode:
    """One design code's metadata and the hooks the elements call.

    ``materials`` lists the concrete classes the code accepts; it is what makes
    a mismatch between a section's concrete and its code detectable rather than
    an obscure failure deep in a check.
    """

    title: str
    year: int
    materials: Tuple[Type["Concrete"], ...]

    #: Verification. Each returns the check state for one combination.
    check_shear: Callable[..., Any]
    check_flexure: Callable[..., Any]
    #: Copy a state back onto the element, for the report tables (ADR-0001).
    apply_shear_state: Callable[..., None]
    apply_flexure_state: Callable[..., None]
    #: Sizing. Each mutates the element, which is the point of a design.
    design_shear: Callable[..., None]
    design_flexure: Callable[..., None]
    #: Bar selection: the catalogue and the detailing rules differ per code.
    transverse_rebar: Callable[..., Any]
    longitudinal_rebar: Callable[..., Any]
    #: The zeroed result attributes this code's report tables expect to read.
    initialize_attributes: Callable[..., None]
    #: Shear on a wall. Not every code has one; see :func:`requires`.
    check_shear_wall: Callable[..., Any] | None = None
    apply_wall_shear_state: Callable[..., None] | None = None
    design_shear_wall: Callable[..., None] | None = None

    #: Two-way shear at a slab-column connection. Optional for the same reason
    #: the wall hooks are: a code that has no punching implementation should say
    #: so by name through :func:`requires`, not fail somewhere inside a check.
    #: ``design_punching`` sizes the shear reinforcement and is Phase 4.
    check_punching: Callable[..., Any] | None = None
    design_punching: Callable[..., None] | None = None

    #: Presentation the code owns: the symbols it names its quantities with and
    #: the unit rows of its summary tables. Not a calculation, but it is
    #: per-code, so a new code must be able to supply it without editing a
    #: report module either. A unit row maps each column to the *kind* of
    #: quantity it holds (``"area"``, ``"moment"``, ... -- the keys of
    #: :data:`mento.precompute.DISPLAY`; ``""`` for none), so one table serves
    #: both unit systems: :func:`units_row` writes it out for either.
    flexure_symbols: Dict[str, str] = field(default_factory=dict)
    units_row_shear: Dict[str, str] = field(default_factory=dict)
    units_row_flexure: Dict[str, str] = field(default_factory=dict)
    #: What this code calls the demands and capacities in a multi-beam summary.
    #: ACI says Mu / ØMn / ØVn where EN says MEd / MRd / VRd, and the summaries
    #: have to name their columns one way or the other.
    #: Keys: moment_demand, shear_demand, shear_demand_source, axial_demand,
    #: moment_capacity_top, moment_capacity_bot, shear_capacity.
    summary_columns: Dict[str, str] = field(default_factory=dict)
    #: The moment capacities off a checked beam, already keyed by column name.
    capacity_columns: Callable[..., Dict[str, float]] | None = None
    #: Shear symbols for the one-line markdown summary, and the row its capacity
    #: sits on in this code's detail table.
    shear_symbols: Dict[str, Any] = field(default_factory=dict)
    #: Summary columns this code does not report, dropped from the Word tables.
    summary_drop_columns: Tuple[str, ...] = ()
    #: Smallest stirrup bar this code's detailing rules allow. Only the codes
    #: whose report tables quote it need to supply one. Where a code does state
    #: one -- ACI 318-19 §9.7.6.4.2 / CIRSOC 201-25 §9.7.6.4.2, Tabla 9.7.6.4.2,
    #: which differ: a No. 10 bar against 6 to 12 mm graded by longitudinal bar
    #: size -- it applies to the stirrups supporting compression reinforcement,
    #: not to every stirrup. That graded clause is ``min_stirrup_for_compression_bar``.
    min_stirrup_diameter: Callable[..., Any] | None = None
    #: The smallest stirrup this code lets laterally support a compression bar
    #: of a given diameter, ``(concrete, d_b_long) -> Quantity``: ACI 318-19
    #: §9.7.6.4.2, a No. 10 up to a No. 32 bar and a No. 13 above (No. 3 and
    #: No. 4 in the in-lb edition), against CIRSOC 201-25 Tabla 9.7.6.4.2,
    #: 6, 8, 10 and 12 mm as the bar passes 16, 25 and 32 mm. They differ, so
    #: each registers its own. ``None`` where the code states none.
    min_stirrup_for_compression_bar: Callable[..., Any] | None = None
    #: What the stirrups of a doubly reinforced section owe its compression
    #: bars -- ACI 318-19 / CIRSOC 201-25 §9.7.6.4: the spacing cap of
    #: §9.7.6.4.3 and the stirrup size of §9.7.6.4.2 -- or ``None`` when
    #: nothing on the section acts as compression steel.
    #: ``(beam, d_b_stirrup) -> CompressionSupport | None``. Read by the shear
    #: design, which caps the bars and the spacing it may choose, and by the
    #: shear warnings. ``None`` for a code with no such clause here: EN 1992-1-1
    #: has its own, §9.2.1.2(3), which is not implemented.
    stirrup_compression_support: Callable[..., Any] | None = None
    #: Absolute caps of Table 9.7.6.2.2 on the spacing of stirrup legs, as
    #: ``(under the Vs threshold, over it)``; they bound the spacing both along
    #: the member and across its width. Codes sharing the table differ only in
    #: these two numbers: ACI 318-19 Table 9.7.6.2.2 gives 600/300 mm
    #: (24/12 in.) and CIRSOC 201-25 Tabla 9.7.6.2.2 gives 400/200 mm.
    stirrup_spacing_caps: Callable[..., Any] | None = None
    #: Cap on f_y in A_s,min: ACI 318-19 §9.6.1.2 (550 MPa / 80 ksi)
    #: and CIRSOC 201-25 §9.6.1.2 (500 MPa).
    flexural_min_fy_cap: Callable[..., Any] | None = None
    #: Coefficient of the beam minimum-shear-reinforcement threshold,
    #: ACI 318-19 / CIRSOC 201-25 §9.6.3.1.
    min_shear_reinforcement_coefficient: Callable[..., Any] | None = None
    #: Stress divisor in alpha_c under net axial tension, Eq. (11.5.4.4).
    wall_axial_tension_divisor: Callable[..., Any] | None = None
    #: The clause each direction of a wall mesh takes its largest spacing
    #: from, as the spacing warning quotes it: ``{"h": ..., "v": ...}``.
    #: ACI 318-19 / CIRSOC 201-25 §11.7.3.1 and §11.7.2.1, with the lw/5 and
    #: lw/3 that enter where shear reinforcement is required; EN 1992-1-1
    #: §9.6.3(2) and §9.6.2(3). Text, not a calculation: the limits
    #: themselves come with the check.
    wall_mesh_spacing_clauses: Dict[str, str] = field(default_factory=dict)
    #: What this code calls the columns of a multi-wall summary, as
    #: ``summary_columns`` does for beams. Keys: rho_h, rho_v (the ratios of
    #: the mesh), shear_demand, shear_capacity.
    wall_summary_columns: Dict[str, str] = field(default_factory=dict)
    #: Largest centre-to-centre spacing this code allows between the flexural
    #: bars of a slab -- ACI 318-19 §7.7.2.3 / CIRSOC 201-25 art. 7.7.2.3, which
    #: differ in their absolute term, 450 mm (18 in.) against 300 mm, and so
    #: register a hook each rather than sharing one. ``None`` for a code that
    #: states none, which is read as no limit rather than as an error: a spacing
    #: rule a code does not have is not a rule an element can fail.
    max_bar_spacing_slab: Callable[..., Any] | None = None
    #: Smallest centre-to-centre spacing this code asks for between the
    #: flexural bars of a slab, over and above the clear distance of
    #: ACI 318-19 §25.2.1 / CIRSOC 201-25 §25.2.1 the settings already impose.
    #: ``None`` where the code states none.
    min_bar_spacing_slab: Callable[..., Any] | None = None
    #: Largest centre-to-centre spacing this code allows between the bars
    #: nearest the tension face of a beam or a one-way slab, for crack
    #: control: ACI 318-19 §24.3.2 / CIRSOC 201-25 art. 24.3.2, reached
    #: through §9.7.2.2 and §7.7.2.2 of both. Takes the section, since the
    #: limit depends on its steel grade and on the cover to those bars. A slab
    #: folds it into its own spacing limit beside §7.7.2.3; a beam is held to
    #: it on the face a combination puts in tension. ``None`` for a code that
    #: controls cracking some other way (EN 1992-1-1 §7.3.3), which is read as
    #: no limit of this kind rather than as an error.
    max_bar_spacing_tension: Callable[..., Any] | None = None
    #: Thinnest *overall* section this code allows for a member bearing on the
    #: ground. ``None`` for a code that instead writes its limit on the
    #: effective depth, which is a different quantity and has its own hook
    #: below. Read as advice, not as a limit: a thinner footing is reported and
    #: still designed, because the thickness is the engineer's to choose.
    min_thickness_on_soil: Callable[..., Any] | None = None
    #: Smallest *effective depth of the bottom reinforcement* this code allows
    #: for a member bearing on the ground -- ACI 318-19 §13.3.1.2 /
    #: CIRSOC 201-25 art. 13.3.1.2, the same clause in both: at least 150 mm
    #: (6 in.). The clause is written on ``d`` and not on the overall
    #: thickness, so a code that states it fills this in rather than
    #: ``min_thickness_on_soil``. ``None`` where the code states none. Advice
    #: on the same terms as the hook above.
    min_effective_depth_on_soil: Callable[..., Any] | None = None
    #: What the flexural A_s,max of this code limits. ``True`` where it is the
    #: ductility limit of the tension steel -- ACI 318-19 / CIRSOC 201-25
    #: §9.3.3.1, a beam tension-controlled per Table 21.2.2 -- which only the
    #: face in tension is held to and which compression steel on the other
    #: face extends. ``False`` where it caps the bars of either face whatever
    #: they do -- EN 1992-1-1 §9.2.1.1(3), "tension or compression
    #: reinforcement". Read by the warnings and the report tables.
    max_steel_is_ductility_limit: bool = False
    #: Does ``face`` of a beam, in tension, keep within the limits this code
    #: puts on its reinforcement with the layout the section carries?
    #: ``(beam, face) -> bool``. Strength alone does not say it: ACI 318-19 /
    #: CIRSOC 201-25 §9.3.3.1 hold a beam tension-controlled, past which the
    #: capacity only drops through phi and may still reach the moment; EN
    #: 1992-1-1 §9.2.1.1(3) caps either face at A_s,max, and bars past it add
    #: resistance a design must not rely on. What a design's own verification
    #: and the alternatives it offers are held to. ``None`` where the code
    #: states no such limit, read as every layout admissible.
    flexure_admissible: Callable[..., bool] | None = None

    def requires(self, hook: str) -> Callable[..., Any]:
        """The hook, or a clear error naming the code that lacks it."""
        value = getattr(self, hook)
        if value is None:
            raise NotImplementedError(f"{hook.replace('_', ' ')} is not implemented for design code: {self.title}")
        return value


_REGISTRY: Dict[str, DesignCode] = {}
_DISCOVERED = False


def _discover() -> None:
    """Import every ``mento/codes/<code>/code.py``, which registers itself.

    Discovery rather than a hand-maintained list, so adding a code is adding a
    subpackage and nothing else -- the exit criterion of the roadmap's Phase 4.

    Lazy, and deliberately so: the code modules import ``mento.rebar``, which
    reaches back into ``codes/`` for its equations. Importing them from this
    module at import time would rebuild the cycle that emptying
    ``codes/__init__.py`` removed. By the time anything asks for a code, both
    ends of that chain are already imported.
    """
    global _DISCOVERED
    if _DISCOVERED:
        return
    _DISCOVERED = True  # set first: a code module importing this one must not recurse
    import importlib
    import pkgutil

    import mento.codes

    for module in pkgutil.iter_modules(mento.codes.__path__):
        if module.ispkg:
            importlib.import_module(f"mento.codes.{module.name}.code")


def register(code: DesignCode) -> DesignCode:
    """Add a code to the registry, keyed by the title elements dispatch on."""
    if code.title in _REGISTRY:
        raise ValueError(f"design code already registered: {code.title}")
    _REGISTRY[code.title] = code
    return code


def design_code(concrete: "Concrete") -> DesignCode:
    """The registered code for this concrete."""
    _discover()
    try:
        return _REGISTRY[concrete.design_code]
    except KeyError:
        raise NotImplementedError(
            f"unknown design code: {concrete.design_code}. Registered: {', '.join(sorted(_REGISTRY)) or 'none'}"
        ) from None


def registered_codes() -> Tuple[str, ...]:
    """Every registered code's title, for diagnostics and tests."""
    _discover()
    return tuple(sorted(_REGISTRY))


def units_row(kinds: Dict[str, str], imperial: bool) -> Dict[str, str]:
    """A code's unit row written out: ``{"As": "cm²"}``, or ``{"As": "in²"}`` in US customary."""
    return {column: unit_label(kind, imperial) for column, kind in kinds.items()}
