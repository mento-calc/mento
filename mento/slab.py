from __future__ import annotations
from typing import Any, Callable, ClassVar, TYPE_CHECKING, cast
from dataclasses import dataclass, field
import math
import warnings

from mento.beam import RectangularBeam
from mento.design_results import RebarLayer
from mento.codes.registry import design_code
from mento.units import m, mm, cm, inch

#: Area unit the mat search works in, built once.
_MM2 = mm**2

if TYPE_CHECKING:
    from pandas import DataFrame
    from mento.forces import Forces
    from mento.units import Quantity


def _bars_at_spacing(spacing: Quantity, width: Quantity) -> float:
    """How many bars a strip of ``width`` carries at a centre-to-centre ``spacing``.

    ``width / spacing``, and not a whole number. A strip is a slice of a slab
    that goes on past both of its edges, so what it carries is the bars per
    metre the spacing gives, and its steel is that many bar areas: a metre of
    Ø10/12 carries 8.33 bars, 6.54 cm². Rounding the count up credited it
    with 9 bars, 7.07 cm², 8 % more than the spacing puts in any metre --
    which let a face designed to its minimum fall short of it with no
    warning, and overstated its capacity by as much. (Nor is 9 what an
    isolated metre holds: nine bars at 12 cm span 96 cm centre to centre,
    and a metre has 95 between its covers.)

    The one place the count-from-spacing rule of a strip lives, so that a
    spacing chosen for a given number of bars can be checked against the count
    it produces. A :class:`Footing` is not a strip -- it ends at its edges and
    is built with whole bars -- and counts with :func:`_whole_bars_in_span`.
    """
    if spacing == 0 * mm:
        return 0.0  # no spacing, no bars
    return float((width / spacing).to("dimensionless").magnitude)


def _whole_bars_in_span(span: float, spacing: float) -> int:
    """How many bars fit in ``span`` at a centre-to-centre ``spacing``, in the same unit.

    One at the start of the span and one more every ``spacing`` that fits, and
    never fewer than two. The tolerance keeps a whole division whole: the
    lengths arrive through unit conversions, and 4 can come out a hair under 4.
    """
    return max(math.floor(span / spacing + 1e-9) + 1, 2)


@dataclass
class OneWaySlab(RectangularBeam):
    """
    One-way slab section. Inherits all flexure and shear checks from RectangularBeam,
    but uses bar diameters + spacing instead of number of bars for longitudinal reinforcement.

    Inheriting the checks is what the codes themselves do: ACI 318-19 §7.5.3.1
    / CIRSOC 201-25 §7.5.3.1 send the shear strength of a one-way slab to
    Chapter 22.5, the same chapter a beam is checked against, and ACI 318-19
    §7.7.5.1 / CIRSOC 201-25 §7.7.5 send its transverse reinforcement to
    §9.7.6.2. What is particular to a slab is the detailing: the bar spacing of
    ACI 318-19 §7.7.2.3 / CIRSOC 201-25 §7.7.2.3 (see :meth:`_max_bar_spacing`)
    and the minimum flexural reinforcement, which ACI 318-19 §7.6.1.1 /
    CIRSOC 201-25 §7.6.1 put at 0.0018*Ag on the gross section in both codes,
    with none of the 4/3 relief of §9.6.1.3, which relieves the beam minimum of
    §9.6.1.2 and no other (see ``_minimum_flexural_reinforcement_area_ACI_318_19``
    in ``codes/ACI_318_19_beam.py`` and the theory page *One-way slab*).
    """

    #: ACI 318-19 / CIRSOC 201-25 §7.3.3.1 holds a nonprestressed slab to a
    #: tension-controlled section, as §9.3.3.1 does a beam.
    _tension_controlled_clause = "7.3.3.1"

    def __post_init__(self) -> None:
        super().__post_init__()

        self.mode = "slab"

        self._stirrup_d_b = 0 * mm
        self._stirrup_s_l = 0 * mm
        self._A_v = 0 * mm**2 / m

        # Allow slabs to place as many bars as minimum spacing permits
        self.settings.max_bars_per_layer = max(self.settings.max_bars_per_layer, 200)
        # ... and no more than the code's own minimum spacing permits, which is
        # the only way that limit can be enforced: the rebar search chooses a
        # bar count, and the spacing is what that count implies. Capping the
        # count is capping the spacing from below.
        minimum = self._min_bar_spacing()
        if minimum is not None:
            self.settings.max_bars_per_layer = max(1, int(self.width / minimum))
        # Force same diameter for all bars within a layer
        self.settings.max_diameter_diff = 0 * self.settings.max_diameter_diff

        self._initialize_longitudinal_rebar_attributes()

    def _initialize_longitudinal_rebar_attributes(self) -> None:
        """Initialize all rebar-related attributes with default values."""

        # Unit system default starter rebar for initial effective height
        # In this case is 0 mm since the slab might not have bottom or top rebar
        if self.concrete.unit_system == "metric":
            self._n1_b, self._d_b1_b = 0, 0 * mm
            self._n1_t, self._d_b1_t = 0, 0 * mm
        else:
            self._n1_b, self._d_b1_b = 0, 0 * inch
            self._n1_t, self._d_b1_t = 0, 0 * inch

        # Bottom rebar defaults (diameter and spacing)
        self._s_b1_b = 0 * mm
        self._d_b2_b, self._s_b2_b = 0 * mm, 0 * mm
        self._d_b3_b, self._s_b3_b = 0 * mm, 0 * mm
        self._d_b4_b, self._s_b4_b = 0 * mm, 0 * mm
        self._n2_b = 0  # No position 2 in slabs
        self._n4_b = 0  # No position 4 in slabs

        # Top rebar defaults (diameter and spacing)
        self._s_b1_t = 0 * mm
        self._d_b2_t, self._s_b2_t = 0 * mm, 0 * mm
        self._d_b3_t, self._s_b3_t = 0 * mm, 0 * mm
        self._d_b4_t, self._s_b4_t = 0 * mm, 0 * mm
        self._n2_t = 0  # No position 2 in slabs
        self._n4_t = 0  # No position 4 in slabs

        # Update dependent attributes
        self._calculate_longitudinal_rebars()
        self._update_longitudinal_rebar_attributes()

    def set_slab_transverse_rebar(
        self,
        d_b: Quantity = 0 * mm,
        s_long: Quantity = 0 * cm,
        s_trans: Quantity = 0 * cm,
    ) -> None:
        """Sets the transverse rebar in the slab section.

        A zero diameter or a zero spacing in either direction means no stirrups,
        which clears the transverse reinforcement.
        """
        self._stirrup_s_l = s_long
        if d_b == 0 * mm or s_long == 0 * cm or s_trans == 0 * cm:
            # No stirrups: same state as a section without transverse rebar
            self._A_v = 0 * mm**2 / m
            self._stirrup_n = 0
            self._stirrup_d_b = 0 * mm
            self._stirrup_s_w = 0 * mm
        else:
            n_legs_per_unit_width = self.width / s_trans
            A_db = (d_b**2) * math.pi / 4  # Area of one stirrup leg per unit width
            self._A_v = A_db * n_legs_per_unit_width / s_long  # Legs area per unit length
            self._stirrup_d_b = d_b
            self._stirrup_s_w = s_trans
            # Both shear checks read _stirrup_n to decide whether the section
            # carries shear reinforcement at all, and the drawings read it as a
            # number of stirrups. Leaving it at zero was why a slab given
            # transverse rebar was still checked as if it had none. A strip has
            # no closed stirrup to count -- the legs at s_trans need not divide
            # into it a whole number of times -- so this is the equivalent
            # number of rows; _A_v above is what the capacity is computed from.
            self._stirrup_n = max(1, round(n_legs_per_unit_width.to("dimensionless").magnitude / 2))

        # Update effective heights
        self._update_effective_heights()
        self._drop_results()

    def _design_start_stirrup(self) -> Quantity:
        """A slab strip starts a design with no stirrups, the way it is built."""
        return self._zero_diameter()

    def _option_layers(self, design: Any) -> tuple[RebarLayer, ...]:
        """The layers a row of the search would put on a face of the strip.

        A slab spreads each layer of the row over the strip as one diameter at
        a spacing -- :meth:`_apply_longitudinal_design` -- so an option reads
        the way the applied layout does: the bar count the spacing gives, the
        diameter, and the spacing.
        """
        layers = []
        for first, second in ((1, 2), (3, 4)):
            d_b, spacing = self._layer_from_design(design, first, second)
            if d_b.magnitude > 0 and spacing.magnitude > 0:
                layers.append(RebarLayer(n=self._bars_in_layer(spacing), d_b=d_b, s=spacing))
        return tuple(layers)

    def _bars_in_layer(self, spacing: Quantity) -> float:
        """How many bars a layer at ``spacing`` puts on this section, as the steel is counted."""
        return _bars_at_spacing(spacing, self.width)

    def _exact_spacing_for_bars(self, n: int) -> Quantity:
        """The widest spacing that still puts ``n`` bars on this section."""
        return self.width / n

    def _leg_spacing_across_width(self) -> Quantity:
        """The transverse spacing the strip was detailed with.

        A beam derives this from the geometry of its stirrup cage. A slab does
        not have one: the legs sit on a grid, and how far apart they are across
        the strip is chosen, not implied. Deriving it the beam's way put the
        legs of a designed slab at a spacing it had never been given.
        """
        return self._stirrup_s_w

    def _apply_transverse_design(self, design: Any) -> None:
        """A slab is detailed by a spacing in each direction, not by a stirrup count."""
        self.set_slab_transverse_rebar(
            d_b=design["d_b"],
            s_long=design["s_l"],
            s_trans=design["s_w"],
        )

    def _zero_diameter(self) -> Quantity:
        """A bar diameter of zero, in the length unit of this slab."""
        return 0 * mm if self.concrete.unit_system == "metric" else 0 * inch

    def _max_bar_spacing(self) -> Quantity | None:
        """The largest spacing the design code allows between the flexural bars.

        ACI 318-19 §7.7.2.3 / CIRSOC 201-25 art. 7.7.2.3 and EN 1992-1-1
        9.3.1.1(3) all cap it as a multiple of the thickness, which is what
        keeps a slab from being detailed as a handful of widely spaced bars
        that happen to add up to the area. A code that states no such limit
        returns ``None``.

        What the three do not share is the absolute term beside that multiple:
        450 mm (18 in.) in ACI 318-19 §7.7.2.3, 300 mm in CIRSOC 201-25
        art. 7.7.2.3, 400 mm in EN 1992-1-1 9.3.1.1(3). Each code registers its
        own hook, so the number is the one the section's code prints; see
        ``mento.codes.aci_318_19.code._max_bar_spacing_slab`` and
        ``_max_bar_spacing_slab_cirsoc``.

        ACI 318-19 and CIRSOC 201-25 put a second cap beside that one, and it
        is the one that governs the ordinary slab: §7.7.2.2 sends the bars
        nearest the tension face to Table 24.3.2, the crack-control limit of
        §24.3.2 -- 300 mm with ADN 420 or Grade 60 and (2/3)*f_y, less with a
        stronger steel or a deeper cover (hook ``max_bar_spacing_tension``).
        Without it a 12 cm ACI slab under 7.5 kN·m was detailed Ø10/34: inside
        the 3h = 36 cm of §7.7.2.3 and past the 300 mm of §24.3.2. The two are
        taken together here, and on both faces: §24.3.2 is written on the
        tension face, but which face that is changes with the combination,
        and a slab is detailed once. Where a face is never in tension the
        cap costs nothing on the strips it decides -- a face that light is
        governed by its minimum area, which asks closer bars anyway.
        """
        code = design_code(self.concrete)
        limits = [hook(self) for hook in (code.max_bar_spacing_slab, code.max_bar_spacing_tension) if hook is not None]
        return None if not limits else cast("Quantity", min(limits))

    def _min_bar_spacing(self) -> Quantity | None:
        """The smallest spacing the design code asks for between the flexural bars.

        Distinct from the clear distance of ACI 318-19 §25.2.1 /
        CIRSOC 201-25 §25.2.1, carried in :class:`~mento.settings.BeamSettings`,
        which every section has and which is about fitting a bar and a vibrator
        between two others. This is a detailing floor for a member cast on the
        ground, which neither code states; only a footing has one, and a slab
        spanning between supports returns ``None``.
        """
        limit = design_code(self.concrete).min_bar_spacing_slab
        return None if limit is None else cast("Quantity | None", limit(self))

    def _spacing_for_bars(self, n: int) -> Quantity:
        """The spacing that puts at least ``n`` bars on the strip, as it would be drawn.

        The exact answer is ``width / n``, which is rarely a number anyone
        details to, so it is rounded to the whole centimetre (inch) -- and
        down, never up. The search chose ``n`` bars for the steel they add up
        to, and a strip at spacing ``s`` carries ``width / s`` of them (see
        :func:`_bars_at_spacing`): any spacing past ``width / n`` carries
        fewer, and so less steel than the search chose. Rounding up did just
        that -- 7 Ø10 in a metre became Ø10/15, 6.67 bars, and a face designed
        to its minimum came out 3 % below it -- while the count was rounded up
        as well, so nothing showed. Rounding down only ever adds steel, and by
        less than one bar in the strip. The result is then capped at what the
        code allows between the bars of a slab, which only ever asks for more
        of them.
        """
        if n <= 0:
            return 0 * cm
        unit = cm if self.concrete.unit_system == "metric" else inch
        exact = self._exact_spacing_for_bars(n).to(unit).magnitude
        # A whole answer is kept whole: the division arrives through unit
        # conversions, and 25 can come out a hair under 25. The floor is only
        # ever below one unit at a spacing where the bars would overlap, which
        # the search never asks for.
        spacing = max(math.floor(exact + 1e-9), 1) * unit
        limit = self._max_bar_spacing()
        if limit is not None:
            # The area the search asked for is not the only thing the layout has
            # to satisfy: bars far enough apart leave the slab between them
            # unreinforced whatever they add up to. Capping the spacing only
            # ever adds bars, so the area is still covered.
            spacing = min(spacing, math.floor(limit.to(unit).magnitude) * unit)
        return spacing

    def _layer_from_design(self, design: Any, first: int, second: int) -> tuple[Quantity, Quantity]:
        """The diameter and spacing of the layer a design gives as two bar groups."""
        n_first = int(design.get(f"n_{first}", 0) or 0)
        n_second = int(design.get(f"n_{second}", 0) or 0)
        # A slab is searched with max_diameter_diff = 0, so a layer only ever
        # comes back with one diameter: whichever group carries the bars.
        d_b = design.get(f"d_b{first}") if n_first > 0 else design.get(f"d_b{second}")
        if d_b is None or d_b.magnitude == 0:
            return self._zero_diameter(), 0 * cm
        return d_b, self._spacing_for_bars(n_first + n_second)

    def _apply_longitudinal_design(self, design: Any, face: str) -> None:
        """Apply a design given in bar counts to a face, as a spacing per layer.

        The rebar search is the beam's -- a slab is not worth a second one --
        and it answers with groups of bars: ``n_1`` and ``n_2`` are the layer
        nearest the face, ``n_3`` and ``n_4`` the one behind it. A slab is not
        detailed that way; it is a diameter repeated at a spacing. So each
        layer is spread over the strip here, and the spacings are what the slab
        stores. Applying the design the beam's way left the bars split across
        two groups that are really one layer, and left the spacings -- the only
        thing a slab is drawn with -- empty.
        """
        d_b1, s_b1 = self._layer_from_design(design, 1, 2)
        d_b3, s_b3 = self._layer_from_design(design, 3, 4)
        setattr(self, f"_d_b1_{face}", d_b1)
        setattr(self, f"_s_b1_{face}", s_b1)
        setattr(self, f"_d_b3_{face}", d_b3)
        setattr(self, f"_s_b3_{face}", s_b3)
        self._calculate_longitudinal_rebars()
        self._update_longitudinal_rebar_attributes()

    def _apply_longitudinal_design_bot(self, design: Any) -> None:
        """See :meth:`_apply_longitudinal_design`."""
        self._apply_longitudinal_design(design, "b")

    def _apply_longitudinal_design_top(self, design: Any) -> None:
        """See :meth:`_apply_longitudinal_design`."""
        self._apply_longitudinal_design(design, "t")

    def _clear_top_longitudinal(self) -> None:
        """Clear the top face, its spacings included.

        A beam clears a face by zeroing the bar counts. On a slab those counts
        are derived from the spacings, so a spacing left behind would put the
        bars back the next time any layer is recalculated.
        """
        self._d_b1_t, self._s_b1_t = self._zero_diameter(), 0 * cm
        self._d_b3_t, self._s_b3_t = self._zero_diameter(), 0 * cm
        self._calculate_longitudinal_rebars()
        self._update_longitudinal_rebar_attributes()

    def set_slab_longitudinal_rebar_bot(
        self,
        d_b1: Quantity = 0 * mm,
        s_b1: Quantity = 0 * mm,
        d_b3: Quantity = 0 * mm,
        s_b3: Quantity = 0 * mm,
    ) -> None:
        """Update the bottom rebar configuration and recalculate attributes.

        Args:
            d_b1: Diameter of position 1 bottom rebar (default: 0 mm).
            s_b1: Spacing of position 1 bottom rebar (default: 0 mm).
            d_b3: Diameter of position 3 bottom rebar (default: 0 mm).
            s_b3: Spacing of position 3 bottom rebar (default: 0 mm).
        """
        self._d_b1_b = d_b1 if d_b1 != 0 * mm else self._d_b1_b
        self._s_b1_b = s_b1 if s_b1 != 0 * mm else self._s_b1_b
        self._d_b3_b = d_b3 if d_b3 != 0 * mm else self._d_b3_b
        self._s_b3_b = s_b3 if s_b3 != 0 * mm else self._s_b3_b
        self._face_set_by_hand("bot")
        self._calculate_longitudinal_rebars()
        self._update_longitudinal_rebar_attributes()
        self._drop_results()

    def set_slab_longitudinal_rebar_top(
        self,
        d_b1: Quantity = 0 * mm,
        s_b1: Quantity = 0 * mm,
        d_b3: Quantity = 0 * mm,
        s_b3: Quantity = 0 * mm,
    ) -> None:
        """Update the top rebar configuration and recalculate attributes.

        Args:
            d_b1: Diameter of position 1 top rebar (default: 0 mm).
            s_b1: Spacing of position 1 top rebar (default: 0 mm).
            d_b3: Diameter of position 3 top rebar (default: 0 mm).
            s_b3: Spacing of position 3 top rebar (default: 0 mm).

        """
        self._d_b1_t = d_b1 if d_b1 != 0 * mm else self._d_b1_t
        self._s_b1_t = s_b1 if s_b1 != 0 * mm else self._s_b1_t
        self._d_b3_t = d_b3 if d_b3 != 0 * mm else self._d_b3_t
        self._s_b3_t = s_b3 if s_b3 != 0 * mm else self._s_b3_t
        self._face_set_by_hand("top")
        self._calculate_longitudinal_rebars()
        self._update_longitudinal_rebar_attributes()
        self._drop_results()

    def _calculate_longitudinal_rebars(self) -> None:
        """The bars each layer puts on the section, from its spacing.

        On a strip, bars per strip, ``width / s``, not a whole number -- see
        :func:`_bars_at_spacing`. The beam's area and centroid then follow from
        these counts as they do from a beam's, so the steel of the strip is
        the bar area times the bars per metre, which is what a slab carries. A
        footing counts whole bars instead: :meth:`Footing._bars_in_layer`.
        """

        # --- BOTTOM REBAR ---
        self._n1_b = self._bars_in_layer(self._s_b1_b)
        self._n3_b = self._bars_in_layer(self._s_b3_b)

        # --- TOP REBAR ---
        self._n1_t = self._bars_in_layer(self._s_b1_t)
        self._n3_t = self._bars_in_layer(self._s_b3_t)


@dataclass
class Footing(OneWaySlab):
    """A spread footing or raft: a one-way slab bearing directly on the ground.

    Everything about it is a :class:`OneWaySlab` -- the same flexure and shear
    checks, the same reinforcement given as diameter and spacing -- and, under
    ACI 318-19 and CIRSOC 201-25, the same minimum longitudinal reinforcement,
    reached by another road. Under EN 1992-1-1 the minimum is where they differ.

    A beam is given a minimum sized to keep it from failing the instant it
    cracks. A member on the ground cannot fail that way, because the soil goes
    on carrying it, so the codes send a footing somewhere else for its minimum:

    * ACI 318-19 §13.3.2.1 sends a one-way shallow foundation to Chapters 7
      and 9, and it is Chapter 7 that applies: §7.6.1.1 asks for
      As,min = 0.0018*Ag on the gross section, with none of the 4/3 relief
      §9.6.1.3 gives a beam. That is the same ratio as the shrinkage and
      temperature reinforcement of §24.4.3.2. A footing spanning two ways goes
      by §13.3.3.1 to Chapter 8, and §8.6.1.1 reads "0.0018*Ag, or as defined
      in 8.6.1.2": the second is the minimum over the two-way shear critical
      section around a column, Eq. (8.6.1.2), which is not implemented here --
      a two-way footing gets the flat 0.0018*Ag.
      CIRSOC 201-25 prints the same chain: §13.3.2.1 → §7.6.1 (the ratio sits
      in an unnumbered paragraph there), §13.3.3.1 → §8.6.1.1, §24.4.3.2.
    * Under EN 1992-1-1, the larger of the halved geometric minimum of a
      foundation (EHE-08 Tabla 42.3.5, note (1): EN prints none) and the
      crack-control minimum of §7.3.2(2). The second governs
      the thin footings, not the thick ones: its ratio goes with k/2, and k
      decays from 1.00 to 0.65 between 300 and 800 mm of depth.

    Both are returned already resolved to the largest applicable minimum, so a
    caller designs a footing and takes the answer as it comes.

    Example::

        footing = Footing(
            label="Z1", concrete=concrete, steel_bar=steel,
            width=1 * m, height=60 * cm, c_c=50 * mm,
        )
        Node(section=footing, forces=[Forces(M_y=120 * kNm)]).design()

    It is also detailed differently, which the same ``support`` tells the codes:
    the bars are kept between 100 and 300 mm apart -- practice under ACI 318-19,
    while under CIRSOC 201-25 the upper figure is its own art. 7.7.2.3, which
    caps every slab at 300 mm and not only one on the ground (art. 8.7.2.2
    repeats it for a footing spanning two ways, reached by art. 13.3.3.1) -- and a
    footing thinner than its code allows says so when it is built: ACI 318-19
    §13.3.1.2 / CIRSOC 201-25 art. 13.3.1.2 ask that the bottom reinforcement
    be left at least 150 mm (6 in.) of effective depth, and EN practice asks
    250 mm overall. And because a footing is placed as a single mat rather than
    as two independently detailed faces, a design ends with both faces set out
    at one spacing -- see :meth:`_finalize_longitudinal_design`.

    And it counts its bars differently from a strip, because it does not go on
    past its edges: ``width`` is the whole footing, and the steel is the whole
    bars that fit in it. They lie in

        ``span = width - 2 * edge_cover - 2 * bend_clearance``

    so at a spacing ``s`` a layer has ``n = max(floor(span / s) + 1, 2)`` bars,
    and ``A_s = n * A_b`` is what the capacity and the ``DCR`` are computed with
    and what ``layer.n`` reads. A footing 130 cm wide with 5 cm of side cover
    has a span of 112 cm, so Ø12/28 is 5 bars, 5.65 cm². The moment is the one
    of that whole width.

    Args:
        edge_cover: The real cover at the sides of the footing, which the bars
            have to stay inside. Defaults to ``c_c``. Give it apart when ``c_c``
            is not a cover but a way of reaching a depth: with the top layer
            resting on the bottom one, ``c_c = cover + Ø`` gives
            ``d = h - cover - 1.5 Ø`` and says nothing about the sides.
        bend_clearance: What the first bar of a layer keeps from that cover, per
            side, to stay clear of the bend of the bars running across it.
            Defaults to 4 cm, 1.5 in. in imperial units.

    Note:
        A `Footing` designs the section, not the foundation. It says nothing
        about the soil below it -- bearing pressure, punching (see
        :class:`~mento.punching.PunchingSlab`), sliding and overturning are not
        part of a section design.
    """

    #: What makes it a footing, and the only thing the design codes read.
    support: ClassVar[str] = "soil"

    # Both resolved in __post_init__, so they read as lengths from then on.
    edge_cover: Quantity = field(default=cast("Quantity", None), kw_only=True)
    bend_clearance: Quantity = field(default=cast("Quantity", None), kw_only=True)

    #: The thinnest bar a footing mat is detailed with, whatever the catalogue
    #: holds below it. Practice rather than code: a mesh finer than this is not
    #: what goes down over the ground, and the search below would otherwise
    #: reach for it to shave the lightly loaded face.
    _MIN_MAT_DIAMETER = 10 * mm

    def __post_init__(self) -> None:
        if self.edge_cover is None:
            self.edge_cover = self.c_c
        if self.bend_clearance is None:
            self.bend_clearance = 4 * cm if self.concrete.unit_system == "metric" else 1.5 * inch
        super().__post_init__()
        # The slab caps the count the search may ask for at width / s_min, its
        # own count at that spacing. A footing counts in its span.
        minimum = self._min_bar_spacing()
        if minimum is not None:
            self.settings.max_bars_per_layer = self._bars_in_layer(minimum)
        if self.concrete.unit_system == "metric":
            self.settings.minimum_longitudinal_diameter = max(
                self.settings.minimum_longitudinal_diameter, self._MIN_MAT_DIAMETER
            )
        self._warn_if_thinner_than_the_code_allows()

    def _bar_span(self) -> Quantity:
        """The width the bars of a layer lie in, first bar to last."""
        return self.width - 2 * self.edge_cover - 2 * self.bend_clearance

    def _bars_in_layer(self, spacing: Quantity) -> int:
        """The whole bars a layer at ``spacing`` has: see :func:`_whole_bars_in_span`."""
        if spacing.magnitude == 0:
            return 0  # no spacing, no bars
        return _whole_bars_in_span(self._bar_span().to(mm).magnitude, spacing.to(mm).magnitude)

    def _exact_spacing_for_bars(self, n: int) -> Quantity:
        """``n`` bars lie in the span with ``n - 1`` spacings between them, and never fewer than two bars."""
        return self._bar_span() / (max(n, 2) - 1)

    #: The layers a mat is placed in, as (diameter attribute, spacing attribute).
    _MAT_LAYERS = (("_d_b1_b", "_s_b1_b"), ("_d_b3_b", "_s_b3_b"), ("_d_b1_t", "_s_b1_t"), ("_d_b3_t", "_s_b3_t"))

    #: How many candidate mats are verified before falling back. They are tried
    #: lightest first, so the first is almost always the answer; the budget only
    #: bounds the cost when the lightest ones do not verify.
    _MAT_CANDIDATES = 12

    def _record_longitudinal_options(self, face: str, design: Any, table: Any) -> None:
        """A footing offers no alternatives: its mat is chosen as a whole.

        The rows the search ranks for one face are layouts of that face
        alone, and the mat that replaces them is chosen for both faces at
        once -- one module, the top at ``s`` or ``2s``, a bar each -- after
        the faces were designed (:meth:`_finalize_longitudinal_design`). No
        row is the mat with one thing changed, so none is an alternative to
        it: offered as they came, 509 of 540 footings ended with a mat first
        and unrelated per-face rows after it, some of which fail when built.
        Only what the footing carries is reported, with its ``DCR``.
        """
        super()._record_longitudinal_options(face, design, None)

    def _finalize_longitudinal_design(
        self,
        A_req_bot: Quantity,
        A_req_top: Quantity,
        resists: Callable[[], bool],
    ) -> None:
        """Detail both faces as one mat, at the least steel that still covers them.

        A footing is not built as two independently detailed faces. The bars go
        down as one grid: the bottom is placed, the top is placed over it, and
        the two are tied. The module has to be one number, and on a drawing the
        top sits either at the bottom spacing or at exactly twice it, so that
        one top bar lands on every second bottom bar.

        Reconciling the two spacings the design arrived at is not enough. The
        face governed by the minimum is detailed as many thin bars, which comes
        out closer than the few thick bars the loaded face needs, so simply
        taking the smaller of the two often closes the *loaded* face up and buys
        steel nobody asked for -- about 18% (EN) and 12% (ACI) more than the two
        faces actually need, measured across footings 1 to 4 m wide.

        So the mat is chosen rather than reconciled: over the spacings the code
        allows and the bars the catalogue holds, the lightest combination of
        module and two diameters -- with the top at ``s`` or ``2s`` -- that
        covers what each face requires, counted in the whole bars the section
        will have (:meth:`_bars_in_layer`). That lands about 7% (EN) and 6%
        (ACI) over the two faces' own requirement.

        Every candidate is verified before it is kept, because the choice feeds
        back into itself: a thicker bar sits deeper, which lowers the effective
        depth and raises the area the face needed in the first place. Anything
        that fails to resist the moments is passed over, and if nothing within
        the budget verifies, the design falls back to reconciling the two
        spacings it had already proved.

        Args:
            A_req_bot: Steel the bottom face has to carry, minimum included.
            A_req_top: The same for the top; zero when it carries none.
            resists: Whether the layout now on the section resists both design
                moments.
        """
        snapshot = [(name, getattr(self, name)) for pair in self._MAT_LAYERS for name in pair]
        for spacing, diameter in self._mat_candidates(A_req_bot, A_req_top):
            self._apply_mat(spacing, diameter)
            if resists():
                return

        for name, value in snapshot:
            setattr(self, name, value)
        self._calculate_longitudinal_rebars()
        self._update_longitudinal_rebar_attributes()
        self._match_spacings_downward()

    def _mat_candidates(self, A_req_bot: Quantity, A_req_top: Quantity) -> Any:
        """The mats worth trying, lightest first, as (spacings, diameters)."""
        needed_bot = A_req_bot.to(_MM2).magnitude if A_req_bot is not None else 0.0
        needed_top = A_req_top.to(_MM2).magnitude if A_req_top is not None else 0.0
        if needed_bot <= 0 and needed_top <= 0:
            return

        limit_max = self._max_bar_spacing()
        if limit_max is None:
            return  # a code that caps nothing gives the search no space to work in
        limit_min = self._min_bar_spacing()

        span = self._bar_span().to(mm).magnitude
        clear = self.settings.clear_spacing.to(mm).magnitude
        # The unit a spacing is drawn in, so the module is one a detailer writes.
        step = 10.0 if self.concrete.unit_system == "metric" else 25.4
        s_lo = step if limit_min is None else limit_min.to(mm).magnitude
        # Past the span two bars no longer lie that far apart, however far the
        # code would let them.
        s_hi = min(limit_max.to(mm).magnitude, span)

        rebar = self._create_rebar_designer()
        bars = [
            (d.to(mm).magnitude, rebar.rebar_areas[d].to(_MM2).magnitude)
            for d in rebar.rebar_diameters
            if self.settings.minimum_longitudinal_diameter <= d <= self.settings.max_longitudinal_diameter
        ]

        def grid(spacing: float, needed: float) -> Any:
            """The lightest bar that covers ``needed`` at ``spacing``, or None."""
            if needed <= 0:
                return (0.0, 0.0)
            # The bars the section will count at this spacing (_bars_in_layer).
            n = _whole_bars_in_span(span, spacing)
            covering = [(n * area, d) for d, area in bars if spacing - d >= clear and n * area >= needed]
            return min(covering) if covering else None

        found = []
        for k in range(math.ceil(s_lo / step), math.floor(s_hi / step + 1e-9) + 1):
            s_bot = k * step
            bottom = grid(s_bot, needed_bot)
            if bottom is None:
                continue
            for factor in (1, 2):
                s_top = s_bot * factor
                if s_top > s_hi:
                    continue
                top = grid(s_top, needed_top)
                if top is None:
                    continue
                # Lightest first; among equals the wider module, which is the
                # cheaper mat to place for the same steel.
                found.append((bottom[0] + top[0], -s_bot, (s_bot, s_top), (bottom[1], top[1])))

        for _, _, spacing, diameter in sorted(found)[: self._MAT_CANDIDATES]:
            yield spacing, diameter

    def _apply_mat(self, spacing: Any, diameter: Any) -> None:
        """Place a single-layer grid on each face, clearing any second layer."""
        s_bot, s_top = spacing
        d_bot, d_top = diameter
        # A face that needs no steel gets no grid at all -- not a spacing with a
        # zero bar on it, which reads as a grid everywhere it is reported and
        # would put a row of nothing on the drawing.
        s_bot = s_bot if d_bot > 0 else 0.0
        s_top = s_top if d_top > 0 else 0.0
        self._d_b1_b, self._s_b1_b = d_bot * mm, s_bot * mm
        self._d_b1_t, self._s_b1_t = d_top * mm, s_top * mm
        self._d_b3_b, self._s_b3_b = self._zero_diameter(), 0 * cm
        self._d_b3_t, self._s_b3_t = self._zero_diameter(), 0 * cm
        self._calculate_longitudinal_rebars()
        self._update_longitudinal_rebar_attributes()

    def _match_spacings_downward(self) -> None:
        """Fallback: reconcile the spacings the design arrived at, taking the
        smaller of the two.

        Safe by construction -- a closer spacing never counts fewer whole bars,
        so it only ever adds them to the face that had the wider spacing -- and
        needs no verification for that reason, which is what makes it the thing
        to fall back to when no searched mat verifies.
        """
        placed = [
            (diameter, spacing)
            for diameter, spacing in self._MAT_LAYERS
            if getattr(self, diameter).magnitude > 0 and getattr(self, spacing).magnitude > 0
        ]
        if len(placed) < 2:
            return  # one grid, or none: nothing to reconcile

        module = min(getattr(self, spacing) for _, spacing in placed)
        if all(getattr(self, spacing) == module for _, spacing in placed):
            return  # already one mat

        for _, spacing in placed:
            setattr(self, spacing, module)
        self._calculate_longitudinal_rebars()
        self._update_longitudinal_rebar_attributes()

    def _effective_depth_of_the_thinnest_mat(self) -> Quantity:
        """The most effective depth this section can be given, before it is designed.

        ``_d_bot`` is only known once the bars are placed, and the check below
        runs when the section is built. The thinnest bar the settings allow is
        the one whose centroid sits closest to the bottom face, so it leaves the
        most depth: if even that mat falls short of the code's minimum, every
        mat the design can reach falls short too, and the section is reported
        once instead of once per bar the search tries.

        Built the way ``_update_longitudinal_rebar_attributes`` builds
        ``_d_bot``: the overall depth less the cover, the transverse bar --
        zero on a mat -- and the distance from the face of the longitudinal bar
        to its centroid.
        """
        return cast(
            "Quantity",
            self.height - self.c_c - self._stirrup_d_b - self.settings.minimum_longitudinal_diameter / 2,
        )

    def check_flexure(self, forces: list[Forces]) -> DataFrame:
        self._warn_if_thinner_than_the_code_allows(use_actual_depth=True)
        return super().check_flexure(forces)

    def check_shear(self, forces: list[Forces]) -> DataFrame:
        self._warn_if_thinner_than_the_code_allows(use_actual_depth=True)
        return super().check_shear(forces)

    def _warn_if_thinner_than_the_code_allows(self, *, use_actual_depth: bool = False) -> None:
        """Say so when the section is thinner than a footing is built.

        Two limits, and a code states one or the other:

        * ACI 318-19 §13.3.1.2 / CIRSOC 201-25 art. 13.3.1.2, the same in both:
          the overall depth shall be selected such that the effective depth of
          the bottom reinforcement is at least 150 mm (6 in.). It is a limit on
          ``d``, so what is measured against it is the depth the mat will have
          -- estimated at construction, actual at check/design completion --
          and not the overall thickness. On a footing the two are far apart, because the
          cover against the ground is 75 mm under ACI 318-19 Table 20.5.1.3.1
          and 55 to 60 mm under CIRSOC 201-25 Tabla 20.5.1.3.1.
        * EN 1992-1-1 states neither, and its hook answers with the overall
          thickness below which a footing is not detailed in practice. That one
          is compared against ``h`` directly.

        A warning and not an error: the thickness is the engineer's to choose,
        and the design that follows is still the right design for the section
        it was given. Raising would refuse to answer a question that has an
        answer.
        """
        code = design_code(self.concrete)
        if use_actual_depth and code.min_effective_depth_on_soil is None:
            return  # The overall-thickness advisory was already given at construction.
        measured = (
            (code.min_thickness_on_soil, self.height, "is", "thick"),
            (
                code.min_effective_depth_on_soil,
                self._d_bot if use_actual_depth else self._effective_depth_of_the_thinnest_mat(),
                "leaves",
                "of effective depth to the bottom bars",
            ),
        )
        for hook, value, verb, what in measured:
            if hook is None:
                continue  # a limit this code does not state is not one to warn about
            limit = cast("Quantity", hook(self.concrete))
            if value >= limit:
                continue
            label = f" {self.label}" if self.label else ""
            warnings.warn(
                f"Footing{label} {verb} {value:.4g~P} {what}, below the "
                f"{limit:.4g~P} {self.concrete.design_code} asks of a footing on soil. "
                "It is designed as given.",
                UserWarning,
                stacklevel=3,
            )
