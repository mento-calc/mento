"""Column sections, checked for shear in each direction.

:class:`RectangularColumn` and :class:`CircularColumn` describe a column's
section -- its shape, its longitudinal bars and its ties -- and check its shear
in both directions with the axial load of each combination. Flexure with axial
load is not here yet: the plan is ``docs/architecture/column-shear-roadmap.md``.

The axes are those of ``docs/source/user_guide/local_axes.rst``: the column
runs along x, ``width`` is measured along y and ``height`` along z. ``V_z``
acts across ``height``, so its section is ``width`` wide and its far face is a
face of length ``width``; ``V_y`` is the same turned. A circle reads the same
section both ways.

The punching ``Column`` of :mod:`mento.column` is a different thing: where a
column stands in a slab, for two-way shear.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Literal, Optional, Tuple

from mento.codes.registry import design_code
from mento.column_results import ColumnShearCheck
from mento.design_results import DesignNotRunError
from mento.forces import Forces
from mento.precompute import CANONICAL
from mento.section import Section
from mento.units import Quantity, mm

if TYPE_CHECKING:
    from mento.design_warnings import DesignWarning

Direction = Literal["y", "z"]
#: The shears a column is checked for, in the order its results come.
DIRECTIONS: Tuple[Direction, Direction] = ("y", "z")

_ROADMAP = "docs/architecture/column-shear-roadmap.md"


def _length_mm(name: str, value: Any, *, allow_zero: bool = False) -> float:
    """``value`` in millimetres, refused unless it is a finite, positive length (or zero, if allowed)."""
    if not isinstance(value, Quantity) or not value.check("[length]"):
        raise TypeError(f"{name} must be a length Quantity.")
    magnitude = float(value.to(mm).magnitude)
    if not math.isfinite(magnitude) or magnitude < 0 or (magnitude == 0 and not allow_zero):
        raise ValueError(f"{name} must be {'zero or more' if allow_zero else 'greater than zero'}.")
    return magnitude


def _count(name: str, value: Any) -> int:
    """A count of bars or crossties: a whole number, zero or more."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer.")
    if value < 0:
        raise ValueError(f"{name} must be zero or more.")
    return value


def _bar_area(d_b: float) -> float:
    return math.pi * d_b**2 / 4


def held(n: int, k: int) -> List[int]:
    """Which of the ``n`` bars between the corners of a face ``k`` crossties hold, as indices.

    Spread along the face as evenly as the bars allow: one crosstie holds the
    middle bar, ``n`` crossties hold every bar. ``k`` may not exceed ``n``.
    """
    return [round((i + 1) * (n + 1) / (k + 1)) - 1 for i in range(k)]


@dataclass(frozen=True)
class ColumnShearSection:
    """One direction of a column as its shear check reads it, in floats.

    In the units the design code writes its coefficients for (N, mm, MPa, or
    lb, in, psi -- ``mento.precompute.CANONICAL``), converted once per section
    and direction rather than once per combination (ADR-0005).

    ``b_w`` and ``d`` are the web and the effective depth of ACI 318-19
    §22.5: in a rectangle the side across the shear and the depth to the
    centroid of the bars of the far face; in a circle ``b_w = D`` and
    ``d = 0.8·D``, §22.5.2.2. ``A_s`` is the tension steel of ρ_w, ``A_g`` the
    gross area of the axial term. ``A_v`` is the area of the legs that cross
    the shear, per length; ``s_l`` the tie spacing along the column and ``s_w``
    the largest distance between adjacent legs across it -- zero where there
    are no ties, and ``s_w`` zero in a circle. ``circular`` says which shape
    it is, for a code whose rules differ by shape.
    """

    direction: Direction
    is_imperial: bool
    b_w: float
    d: float
    A_g: float
    A_s: float
    A_v: float
    s_l: float
    s_w: float
    f_c: float
    f_y: float
    circular: bool = False
    #: A circle under EN 1992-1-1 (Orr et al., 2010): the radius to the links'
    #: centreline, the depth to the tension chord, the lever arm, and the pitch
    #: of a spiral (0 for hoops). Zero for a rectangle, which does not read them.
    r_sv: float = 0.0
    d_truss: float = 0.0
    z_truss: float = 0.0
    pitch: float = 0.0


@dataclass
class ColumnSection(Section):
    """What both column shapes share: checking the shear and keeping its results.

    Not built directly: :class:`RectangularColumn` or :class:`CircularColumn`.
    Any change to the bars or the ties drops the results of the last check,
    which described the section as it was.

    ``alpha_cw_from_axial_load`` is read under EN 1992-1-1 only. ``True``,
    the default, takes α_cw of Expression (6.11aN) in V_Rd,max with the
    compression of each combination, N_Ed/A_c: up to 1.25 under moderate
    compression, below 1 past 0.6·f_cd, where the axial load alone has used
    up most of the strut (#210, roadmap D4). ``False`` keeps α_cw = 1, the
    value §6.2.3(3) Note 3 gives "for non-prestressed structures", at every
    compression.
    """

    alpha_cw_from_axial_load: bool = field(default=True, kw_only=True)

    def __post_init__(self) -> None:
        super().__post_init__()
        self._tie_d_b: float = 0.0
        self._tie_s: float = 0.0
        self._shear_sections: Dict[str, ColumnShearSection] = {}
        self._shear_checks: Optional[Tuple[ColumnShearCheck, ...]] = None
        self._checked_forces: Tuple[Forces, ...] = ()

    def _drop_results(self) -> None:
        self._shear_sections = {}
        self._shear_checks = None
        self._checked_forces = ()

    def _set_tie(self, d_b: Any, s: Any) -> bool:
        """Store the tie's bar and spacing, in mm; ``False`` for the all-zero input that clears them."""
        d_b_mm = _length_mm("d_b", d_b, allow_zero=True)
        s_mm = _length_mm("s", s, allow_zero=True)
        if d_b_mm == 0 and s_mm == 0:
            self._tie_d_b, self._tie_s = 0.0, 0.0
            return False
        if d_b_mm == 0 or s_mm == 0:
            raise ValueError("d_b and s must both be greater than zero, or both zero to remove the ties.")
        self._tie_d_b, self._tie_s = d_b_mm, s_mm
        return True

    # What each shape answers --------------------------------------------------

    def _build_shear_section(self, direction: Direction) -> ColumnShearSection:
        raise NotImplementedError

    def _floats(self) -> Tuple[bool, float, float, float, float]:
        """``(imperial, mm, c_c, f_c, f_y)``: the unit system and what every shape converts the same way.

        ``mm`` is one millimetre in the canonical length, the factor the bars
        and ties, kept in millimetres, are scaled by.
        """
        imperial = self.concrete.is_imperial
        canonical = CANONICAL[imperial]
        return (
            imperial,
            float((1 * mm).to(canonical["length"]).magnitude),
            float(self.c_c.to(canonical["length"]).magnitude),
            float(self.concrete.f_c.to(canonical["stress"]).magnitude),
            float(self.steel_bar.f_y.to(canonical["stress"]).magnitude),
        )

    def shear_section(self, direction: Direction) -> ColumnShearSection:
        """The section the shear check of ``direction`` reads, built once until the section changes."""
        if direction not in DIRECTIONS:
            raise ValueError(f"direction must be 'y' or 'z', got {direction!r}.")
        section = self._shear_sections.get(direction)
        if section is None:
            section = self._build_shear_section(direction)
            self._shear_sections[direction] = section
        return section

    # Checks -------------------------------------------------------------------

    def shear_check_results(self, forces: List[Forces]) -> Tuple[ColumnShearCheck, ...]:
        """Check the shear of every combination in both directions, as values.

        One :class:`~mento.column_results.ColumnShearCheck` per combination and
        direction, ``y`` then ``z``. Builds no report and words no warning:
        :attr:`warnings` does that when it is read.
        """
        code = design_code(self.concrete)
        if code.check_column_shear is None:
            raise NotImplementedError(f"The shear of a column is not implemented for {code.title} yet: see {_ROADMAP}.")
        results = tuple(code.check_column_shear(self, force, direction) for force in forces for direction in DIRECTIONS)
        self._shear_checks = results
        self._checked_forces = tuple(forces)
        return results

    def check(self, forces: List[Forces]) -> None:
        """Check the section for ``forces``: shear in both directions, what a column checks today."""
        self.shear_check_results(forces)

    def check_shear(self, forces: List[Forces]) -> None:
        """Check the shear of ``forces`` in both directions; the results are :attr:`shear_checks`."""
        self.shear_check_results(forces)

    def design(self, forces: List[Forces]) -> None:
        raise NotImplementedError(
            f"mento checks the ties of a column but does not design them yet; set them with set_ties() (see {_ROADMAP})."
        )

    def design_shear(self, forces: List[Forces]) -> None:
        self.design(forces)

    def check_flexure(self, forces: List[Forces]) -> None:
        raise NotImplementedError(
            f"A column's flexure with axial load is not in mento yet; this element checks shear (see {_ROADMAP})."
        )

    def design_flexure(self, forces: List[Forces]) -> None:
        self.check_flexure(forces)

    @property
    def shear_checks(self) -> Tuple[ColumnShearCheck, ...]:
        """The results of the last check, one per combination and direction."""
        if self._shear_checks is None:
            raise DesignNotRunError("Run check() or shear_check_results() before reading the shear checks.")
        return self._shear_checks

    @property
    def warnings(self) -> Tuple["DesignWarning", ...]:
        """The limits the ties miss under the last check, as data; empty before any check.

        Worded when read, in the language set with :func:`mento.set_language`.
        """
        if self._shear_checks is None:
            return ()
        from mento.design_warnings import collect, column_shear_warnings

        return collect(column_shear_warnings(self, self._shear_checks, self._checked_forces))

    # Reports ------------------------------------------------------------------
    # The presentation is imported when asked for, so that checking a column --
    # in a loop over a building -- loads neither IPython nor python-docx.

    @property
    def data(self) -> None:
        """The column's inputs in one line of Markdown (Jupyter)."""
        from mento.reports.columns import column_data

        column_data(self)

    @property
    def results(self) -> None:
        """The governing combination, one line per direction (Jupyter)."""
        from mento.reports.columns import column_shear_results

        column_shear_results(self)

    def shear_results_detailed(self, force: Optional[Forces] = None) -> None:
        """Print the shear of one combination, both directions: the governing one, or ``force``."""
        from mento.reports.columns import column_shear_results_detailed

        column_shear_results_detailed(self, force)

    def shear_results_detailed_doc(self, force: Optional[Forces] = None) -> None:
        """Save the same as a Word document in the working directory."""
        from mento.reports.columns import column_shear_results_detailed_doc

        column_shear_results_detailed_doc(self, force)

    def flexure_results_detailed(self, force: Optional[Forces] = None) -> None:
        self.check_flexure([])

    def flexure_results_detailed_doc(self, force: Optional[Forces] = None) -> None:
        self.check_flexure([])


@dataclass
class RectangularColumn(ColumnSection):
    """A rectangular column section, ``width`` along y and ``height`` along z.

    The bars: one in each corner and, between the corners, ``n_width`` bars on
    each face of length ``width`` and ``n_height`` on each face of length
    ``height``. The ties: a perimeter tie, plus crossties that may be thinner
    -- ``crossties_width`` hold bars of the faces of length ``width``, span the
    height and carry ``V_z``; ``crossties_height`` hold bars of the faces of
    length ``height`` and carry ``V_y``::

        column = RectangularColumn(label="C1", concrete=concrete, steel_bar=steel,
                                   width=30 * cm, height=50 * cm, c_c=25 * mm)
        column.set_longitudinal_rebar(d_b_corner=20 * mm, n_width=1, n_height=2, d_b_height=16 * mm)
        column.set_ties(d_b=10 * mm, s=15 * cm, crossties_height=1, d_b_crosstie=8 * mm)
        Node(column, forces).check()
    """

    width: Quantity = field(kw_only=True)
    height: Quantity = field(kw_only=True)

    def __post_init__(self) -> None:
        width = _length_mm("width", self.width)
        height = _length_mm("height", self.height)
        super().__post_init__()
        if self.c_c.to(mm).magnitude >= min(width, height) / 2:
            raise ValueError("c_c must be less than half of the smallest section dimension.")
        self._d_b_corner: float = 0.0
        self._n_width: int = 0
        self._d_b_width: float = 0.0
        self._n_height: int = 0
        self._d_b_height: float = 0.0
        self._crossties_width: int = 0
        self._crossties_height: int = 0
        self._d_b_crosstie: float = 0.0

    @property
    def A_x(self) -> Quantity:
        """Gross area of the section."""
        return (self.width * self.height).to("cm**2")

    def set_longitudinal_rebar(
        self,
        d_b_corner: Quantity,
        n_width: int = 0,
        d_b_width: Optional[Quantity] = None,
        n_height: int = 0,
        d_b_height: Optional[Quantity] = None,
    ) -> None:
        """Set the bars: four corners of ``d_b_corner`` and the bars between them on each face.

        ``n_width`` bars of ``d_b_width`` on each face of length ``width``, and
        ``n_height`` of ``d_b_height`` on each face of length ``height``; each
        diameter defaults to the corner's.
        """
        corner = _length_mm("d_b_corner", d_b_corner)
        n_w, n_h = _count("n_width", n_width), _count("n_height", n_height)
        d_w = corner if d_b_width is None else _length_mm("d_b_width", d_b_width)
        d_h = corner if d_b_height is None else _length_mm("d_b_height", d_b_height)
        self._d_b_corner, self._n_width, self._d_b_width, self._n_height, self._d_b_height = corner, n_w, d_w, n_h, d_h
        self._drop_results()

    def set_ties(
        self,
        d_b: Quantity,
        s: Quantity,
        *,
        crossties_width: int = 0,
        crossties_height: int = 0,
        d_b_crosstie: Optional[Quantity] = None,
    ) -> None:
        """Set the ties: a perimeter tie of ``d_b`` every ``s``, and the crossties inside it.

        Each crosstie is one leg, of ``d_b_crosstie`` (the tie's own bar by
        default, and thinner if given), counted in the shear it crosses:
        ``crossties_width`` in ``V_z``, ``crossties_height`` in ``V_y``. Whether a
        thin crosstie is thick enough to brace its bar is a detailing rule,
        not a shear one, and is not read here. ``d_b`` and ``s`` both zero
        remove the ties.
        """
        has_ties = self._set_tie(d_b, s)
        c_w, c_h = _count("crossties_width", crossties_width), _count("crossties_height", crossties_height)
        if not has_ties and (c_w or c_h):
            raise ValueError("Crossties need a perimeter tie: give d_b and s.")
        crosstie = self._tie_d_b if d_b_crosstie is None else _length_mm("d_b_crosstie", d_b_crosstie)
        self._crossties_width, self._crossties_height, self._d_b_crosstie = c_w, c_h, crosstie
        self._drop_results()

    def _build_shear_section(self, direction: Direction) -> ColumnShearSection:
        if self._d_b_corner == 0:
            raise ValueError("Set the longitudinal bars first: d and ρ_w of the shear come from them.")
        imperial, one_mm, c, f_c, f_y = self._floats()
        length = CANONICAL[imperial]["length"]
        width, height = float(self.width.to(length).magnitude), float(self.height.to(length).magnitude)
        if direction == "z":
            b_w, depth, n, d_face, crossties, name = (
                width,
                height,
                self._n_width,
                self._d_b_width,
                self._crossties_width,
                "width",
            )
        else:
            b_w, depth, n, d_face, crossties, name = (
                height,
                width,
                self._n_height,
                self._d_b_height,
                self._crossties_height,
                "height",
            )
        if crossties > n:
            raise ValueError(
                f"{crossties} crossties_{name} hold bars of the faces of length {name}, "
                f"which have {n} bars between the corners."
            )
        tie, corner, face, crosstie = (
            v * one_mm for v in (self._tie_d_b, self._d_b_corner, d_face, self._d_b_crosstie)
        )
        # The far face: its two corners and the bars between them, centred
        # where they touch the tie, as RectangularBeam places a layer.
        A_corner, A_face = _bar_area(corner), _bar_area(face)
        A_s = 2 * A_corner + n * A_face
        centroid = (2 * A_corner * corner / 2 + n * A_face * face / 2) / A_s
        d = depth - c - tie - centroid
        A_v = s_l = s_w = 0.0
        if self._tie_s > 0:
            s_l = self._tie_s * one_mm
            A_v = (2 * _bar_area(tie) + crossties * _bar_area(crosstie)) / s_l
            # The legs across b_w: the tie's two sides, and each crosstie at
            # the bar it holds, the bars spread evenly between the corners.
            edge = b_w / 2 - c - tie / 2
            first = b_w / 2 - c - tie - corner / 2
            bars = [-first + (k + 1) * 2 * first / (n + 1) for k in range(n)]
            legs = sorted([-edge, edge] + [bars[k] for k in held(n, crossties)])
            s_w = max(b - a for a, b in zip(legs, legs[1:]))
        return ColumnShearSection(direction, imperial, b_w, d, width * height, A_s, A_v, s_l, s_w, f_c, f_y)


@dataclass
class CircularColumn(ColumnSection):
    """A circular column section of ``diameter``, with ``n`` bars round it and hoops or a spiral.

    Under ACI 318-19 and CIRSOC 201-25 it is checked as §22.5.2.2 allows,
    ``b_w = D`` and ``d = 0.8·D``, with the gross area of the circle in the
    axial term. A hoop crosses the shear twice, so it counts as two legs. The
    tension steel of ρ_w is the bars past the centre line, ``(n - 1) // 2`` of
    them -- no more than the circle has on one side, whatever way it is
    turned.

    EN 1992-1-1 has no clause for a circle; it is checked by the truss of
    Orr et al. (2010), which needs the depth ``d`` to the tension chord and
    the lever arm ``z``. They come from a sectional analysis of each
    combination, which mento does not run yet: by default ``d`` puts the
    neutral axis at the centre, so the tension chord is the centroid of the
    bars of one half, ``r + 2·r_s/π``, and ``z = 0.77·d``, the mean Orr et al.
    found over 38 of Clarke's tests. :meth:`set_lever_arm` takes the ones of
    an analysis instead::

        column = CircularColumn(label="C2", concrete=concrete, steel_bar=steel, diameter=50 * cm, c_c=30 * mm)
        column.set_longitudinal_rebar(n=8, d_b=20 * mm)
        column.set_hoops(d_b=10 * mm, s=15 * cm)
    """

    diameter: Quantity = field(kw_only=True)

    def __post_init__(self) -> None:
        diameter = _length_mm("diameter", self.diameter)
        super().__post_init__()
        if self.c_c.to(mm).magnitude >= diameter / 2:
            raise ValueError("c_c must be less than half of the diameter.")
        self._n_bars: int = 0
        self._d_b: float = 0.0
        self._spiral: bool = False
        self._lever_arm: Optional[Tuple[float, float]] = None

    @property
    def A_x(self) -> Quantity:
        """Gross area of the section."""
        return (math.pi * self.diameter**2 / 4).to("cm**2")

    def set_longitudinal_rebar(self, n: int, d_b: Quantity) -> None:
        """Set the ``n`` bars of ``d_b`` round the section."""
        if _count("n", n) == 0:
            raise ValueError("n must be greater than zero.")
        self._n_bars, self._d_b = n, _length_mm("d_b", d_b)
        self._drop_results()

    def set_hoops(self, d_b: Quantity, s: Quantity, *, spiral: bool = False) -> None:
        """Set circular hoops of ``d_b`` every ``s``, or a spiral of pitch ``s``; both zero remove them.

        A spiral leans along the column by its pitch, which EN 1992-1-1, by Orr
        et al. (2010), reads as a smaller share of its force across the
        section (λ2); ACI 318-19 counts it as hoops.
        """
        self._set_tie(d_b, s)
        self._spiral = bool(spiral)
        self._drop_results()

    def set_lever_arm(self, d: Optional[Quantity] = None, z: Optional[Quantity] = None) -> None:
        """Set the depth to the tension chord and the lever arm EN 1992-1-1 checks a circle with.

        From a sectional analysis of the column under the moment that governs,
        which Orr et al. (2010) recommend applying along the member: the
        largest compression chord, and so the smallest ``z``, is the safe side.
        Both ``None`` go back to the default of the class docstring. ACI 318-19
        does not read them: it takes ``d = 0.8·D``.
        """
        if d is None and z is None:
            self._lever_arm = None
        else:
            if d is None or z is None:
                raise ValueError("Give both d and z, or neither.")
            d_mm, z_mm = _length_mm("d", d), _length_mm("z", z)
            if not z_mm < d_mm <= self.diameter.to(mm).magnitude:
                raise ValueError("The lever arm must be shorter than d, and d no deeper than the diameter.")
            self._lever_arm = (d_mm, z_mm)
        self._drop_results()

    def _build_shear_section(self, direction: Direction) -> ColumnShearSection:
        if self._n_bars == 0:
            raise ValueError("Set the longitudinal bars first: ρ_w of the shear comes from them.")
        imperial, one_mm, c, f_c, f_y = self._floats()
        D = float(self.diameter.to(CANONICAL[imperial]["length"]).magnitude)
        A_s = (self._n_bars - 1) // 2 * _bar_area(self._d_b * one_mm)
        hoop, bar = self._tie_d_b * one_mm, self._d_b * one_mm
        A_v = s_l = 0.0
        if self._tie_s > 0:
            s_l = self._tie_s * one_mm
            A_v = 2 * _bar_area(hoop) / s_l
        r = D / 2
        r_sv = r - c - hoop / 2
        if self._lever_arm is None:
            d_truss = r + 2 * (r - c - hoop - bar / 2) / math.pi
            z_truss = 0.77 * d_truss
        else:
            d_truss, z_truss = (value * one_mm for value in self._lever_arm)
        return ColumnShearSection(
            direction,
            imperial,
            D,
            0.8 * D,
            math.pi * D**2 / 4,
            A_s,
            A_v,
            s_l,
            0.0,
            f_c,
            f_y,
            circular=True,
            r_sv=r_sv,
            d_truss=d_truss,
            z_truss=z_truss,
            pitch=s_l if self._spiral else 0.0,
        )
