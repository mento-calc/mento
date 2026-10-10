from __future__ import annotations
from contextlib import contextmanager
from typing import Any, Callable, Dict, Iterator, List, Optional, TYPE_CHECKING, Tuple
import math
import pandas as pd
import numpy as np

from mento.codes.aci_318_19.equations import shear as aci_shear_eq
from mento.codes.en_1992_2004.equations import shear as en_shear_eq
from mento.codes.registry import design_code
from mento.precompute import CANONICAL, DISPLAY, section_floats
from mento.section_geometry import end_setback, stirrup_bend_inner_diameter
from mento.units import mm, cm, inch
from mento.bar_sizes import ASTM_BAR_DIAMETERS, bar_designation, bar_diameter

__all__ = ["Rebar", "bar_designation", "bar_diameter"]

if TYPE_CHECKING:
    from mento.beam import RectangularBeam
    from mento.units import Quantity
    from pandas import DataFrame

# `cm**2` raises a pint Unit to a power, which is far from free. The rebar search
# builds one area Quantity per candidate it keeps, so the unit is built once here
# instead of on every call.
_CM2 = cm**2

#: What the section asks of its stirrups, ``(A_v_req, V_s_req)``, read off the
#: section as it is when called. The transverse search calls it once per bar
#: diameter, with that diameter on the section, so the demand is the one the
#: effective depth of that diameter gives.
_ShearDemand = Callable[[], Tuple["Quantity", "Quantity"]]


def max_stirrup_spacing_ACI_318_19(beam: RectangularBeam, V_s_req: float, A_cv: float) -> Tuple[float, float]:
    """Stirrup spacing limits for a beam — ACI 318-19 Table 9.7.6.2.2 / CIRSOC 201-25 Tabla 9.7.6.2.2.

    Both codes reach the table from §9.7.6.2.2.

    ``V_s_req`` is the nominal shear the stirrups must carry, (Vu − φVc)/φ, as
    the check computes it in ``_calculate_V_s_req``. The absolute caps come from
    the code's registry entry: ACI 318-19 and CIRSOC 201-25 share the table --
    the same threshold 0.33*sqrt(f'c)*bw*d and the same d/2, d, d/4, d/2 -- but
    CIRSOC 201-25 Tabla 9.7.6.2.2 differs in the two absolute caps, 400/200 mm
    against ACI's 600/300 mm (24/12 in.).

    Only the rows of the table are applied. Where the beam carries compression
    reinforcement, ACI 318-19 §9.7.6.4.3 / CIRSOC 201-25 §9.7.6.4.3 -- the same
    text in both -- also cap the spacing at the least of 16 d_b of the
    longitudinal bar, 48 d_b of the stirrup and the least dimension of the
    beam, and that limit is not imposed here.

    Floats in the beam's own unit system, in and out: the shear check runs
    entirely in floats, so a pint signature here would put the boundary back in
    the middle of it. :meth:`Rebar.calculate_max_spacing_ACI_318_19` wraps this
    for the design path, which still speaks pint.

    A module-level function rather than a ``Rebar`` method because it needs
    nothing from the bar catalogue: building a whole ``Rebar`` for it cost more
    than the check it serves.
    """
    sec = section_floats(beam)
    length = CANONICAL[sec.is_imperial]["length"]
    cap_low, cap_high = design_code(beam.concrete).requires("stirrup_spacing_caps")(beam.concrete)
    return aci_shear_eq.max_stirrup_spacing(
        V_s_req,
        sec.f_c,
        A_cv,
        sec.d_shear,
        cap_low.to(length).magnitude,
        cap_high.to(length).magnitude,
        is_imperial=sec.is_imperial,
    )


def max_stirrup_spacing_EN_1992_2004(beam: RectangularBeam, alpha: float) -> Tuple[float, float]:
    """Stirrup spacing limits of EN 1992-1-1 §9.2.2(6) and (8), for a beam.

    Floats in mm, in and out, for the same reason as the ACI counterpart.
    :meth:`Rebar.calculate_max_spacing_EN_1992_2004` wraps it for the design
    path, which still speaks pint.
    """
    return en_shear_eq.max_stirrup_spacing(section_floats(beam).d_shear, alpha)


def leg_count(beam: Any) -> int:
    """The stirrup legs of a section across its width: 0 when it carries none."""
    if getattr(beam, "_stirrups_optional", False) or not beam._stirrup_n:
        return 0
    return int(round(2 * float(beam._stirrup_n)))


class RebarDesignInfeasibleError(Exception):
    """Raised when no valid rebar combination fits the section geometry and
    the code-imposed limits (A_s_req, A_s_max, bar diameter, spacing, layers).

    Typical trigger: very narrow sections combined with high A_s_req (small
    b + high fy or high Mu). Callers should catch this and either fall back
    to "best-effort" behavior or surface the infeasibility to the user.
    """


class Rebar:
    def __init__(self, beam: RectangularBeam):
        """
        Initializes the Rebar object with the associated beam and settings.
        """

        self.mode = getattr(beam, "mode", "beam")  # "beam" or "slab"

        self.beam = beam
        self._long_combos_df: DataFrame = pd.DataFrame()
        self._trans_combos_df: DataFrame = pd.DataFrame()
        # Precompute spacing limits as floats in mm
        self._clear_limit_mm = self.beam.settings.clear_spacing.to("mm").magnitude
        self._vibrator_mm = self.beam.settings.vibrator_size.to("mm").magnitude
        self._clear_spacing = self.beam.settings.clear_spacing.to("mm")
        # The most the code lets the bars nearest a tension face sit apart,
        # centre to centre: the crack-control cap of ACI 318-19 / CIRSOC
        # 201-25 §24.3.2, which §9.7.2.2 sends a beam to (hook
        # ``max_bar_spacing_tension``; None for a code without it). A beam's
        # search holds its layouts to it on a face some load pulls
        # (:meth:`longitudinal_rebar` lifts it off one nothing does); a slab
        # strip applies it afterwards, through the spacing it is written back
        # as (``OneWaySlab._spacing_for_bars``), since the layer this search
        # lays out between the stirrup legs is not how a strip carries its bars.
        limit = design_code(self.beam.concrete).max_bar_spacing_tension
        self._tension_cap_mm: float | None = None if limit is None else limit(self.beam).to("mm").magnitude
        self._max_centre_mm: float | None = self._tension_cap_mm
        # Unit system default rebar.
        #
        # The metric list is the bar sizes of CIRSOC 201-25 §20.2.1.3,
        # Tabla 20.2.1 (ADN 420: 6, 8, 10, 12, 16, 20, 25, 32 and 40 mm), with
        # the 40 mm left out. It is used for ACI 318-19 in metric units too,
        # where the bars are not the ASTM sizes ACI is written around: a metric
        # ACI design therefore details bars of the local catalogue, which is
        # what a drawing in this region can call for.
        if self.beam.concrete.unit_system == "metric":
            self.rebar_diameters = [
                6 * mm,
                8 * mm,
                10 * mm,
                12 * mm,
                16 * mm,
                20 * mm,
                25 * mm,
                32 * mm,
            ]
            self.rebar_areas = {d: (math.pi * d**2) / 4 for d in self.rebar_diameters}
        else:
            # The ASTM A615 sizes #3 to #14, which the reports write as "#6".
            self.rebar_diameters = list(ASTM_BAR_DIAMETERS.values())
            rebar_areas_list = [(d**2 * np.pi / 4) for d in self.rebar_diameters]
            self.rebar_areas = dict(zip(self.rebar_diameters, rebar_areas_list))

    @property
    def longitudinal_rebar_design(self) -> DataFrame:
        if self._long_combos_df.empty:
            raise RebarDesignInfeasibleError(
                "No valid longitudinal rebar combination found — the required "
                "steel area cannot be fit in the section given the geometry "
                "(width, max diameter, layers, spacing limits)."
            )
        return self._long_combos_df.iloc[0]

    @property
    def transverse_rebar_design(self) -> DataFrame:
        if self._trans_combos_df.empty:
            raise RebarDesignInfeasibleError(
                "No valid transverse rebar combination found — no bar the code "
                "allows, at any spacing within its limits, provides the required "
                "A_v. The section is too shallow for the shear it carries."
            )
        return self._trans_combos_df.iloc[0]

    ##########################################################
    # TRANSVERSE REBAR DESIGN
    ##########################################################

    def calculate_max_spacing_ACI_318_19(self, V_s_req: Quantity, A_cv: Quantity) -> Tuple[Quantity, Quantity]:
        """
        Calculate the maximum allowable spacing across the length and width of the beam
        based on design requirements.

        Parameters
        ----------
        V_s_req : float
            Nominal shear the stirrups must carry, (Vu − φVc)/φ.
        A_cv : float
            Effective shear area of the concrete section.

        Returns
        -------
        tuple
            (s_max_l, s_max_w): The maximum spacing across the length and width of the beam.
        """

        sec = section_floats(self.beam)
        canonical = CANONICAL[sec.is_imperial]
        display = DISPLAY[sec.is_imperial]
        s_max_l, s_max_w = max_stirrup_spacing_ACI_318_19(
            self.beam,
            V_s_req.to(canonical["force"]).magnitude,
            A_cv.to(canonical["area"]).magnitude,
        )
        return (
            (s_max_l * canonical["length"]).to(display["length"]),
            (s_max_w * canonical["length"]).to(display["length"]),
        )

    def calculate_max_spacing_EN_1992_2004(self, alpha: float) -> Tuple[Quantity, Quantity]:
        """
        Calculate the maximum allowable spacing across the length and width of the beam
        based on design requirements for EN 1992-2004.

        Parameters
        ----------
        alpha: stirrups angle

        Returns
        -------
        tuple
            (s_max_l, s_max_w): The maximum spacing along the length and width of the beam.
        """
        s_max_l, s_max_w = max_stirrup_spacing_EN_1992_2004(self.beam, alpha)
        return (s_max_l * mm).to(cm), (s_max_w * mm).to(cm)

    def transverse_rebar_ACI_318_19(self, V_s_req: Quantity) -> Any:
        """Stirrup sizes and spacing limits offered to the search, ACI 318-19.

        The floor of 10 mm (a #3 bar) is catalogue practice, not a clause:
        ACI 318-19 §9.7.6.4.2 / CIRSOC 201-25 §9.7.6.4.2 only fix a minimum
        stirrup diameter where the stirrups laterally support compression
        reinforcement (§9.7.6.4.1 in both), and neither code states one for a
        stirrup placed purely for shear. The spacing limits are those of
        ACI 318-19 Table 9.7.6.2.2 / CIRSOC 201-25 Tabla 9.7.6.2.2.
        """
        if self.beam.concrete.unit_system == "metric":
            valid_diameters = self.rebar_diameters[2:5]  # Minimum 10 mm
        else:
            valid_diameters = self.rebar_diameters[0:3]

        A_cv = self.beam.width * self.beam._d_shear
        s_max_l, s_max_w = self.calculate_max_spacing_ACI_318_19(V_s_req, A_cv)

        return valid_diameters, s_max_l, s_max_w

    def transverse_rebar_CIRSOC_201_25(self, V_s_req: Quantity) -> Any:
        """Stirrup sizes and spacing limits offered to the search, CIRSOC 201-25.

        The sizes are the smallest four of CIRSOC 201-25 §20.2.1.3,
        Tabla 20.2.1. Both bounds are practice: the 6 mm floor is the bottom of
        that catalogue -- CIRSOC 201-25 §9.7.6.4.2, Tabla 9.7.6.4.2 grades a
        minimum from 6 to 12 mm, but only for the stirrups that support
        compression reinforcement (§9.7.6.4.1) -- and the 12 mm ceiling is a
        detailing preference, not a limit either code prints. The spacing
        limits are those of CIRSOC 201-25 Tabla 9.7.6.2.2, which is why the
        ACI helper is called: the two tables differ only in their absolute
        caps, and those arrive from the registry.
        """
        valid_diameters = self.rebar_diameters[0:4]  # Minimum 6 mm, maximum 12 mm

        A_cv = self.beam.width * self.beam._d_shear
        s_max_l, s_max_w = self.calculate_max_spacing_ACI_318_19(V_s_req, A_cv)

        return valid_diameters, s_max_l, s_max_w

    def transverse_rebar_EN_1992_2004(self, alpha: float) -> Any:
        valid_diameters = self.rebar_diameters[0:4]  # Minimum 6 mm, maximum 12 mm

        s_max_l, s_max_w = self.calculate_max_spacing_EN_1992_2004(alpha)

        return valid_diameters, s_max_l, s_max_w

    def min_legs_along_width(self, d_b: Quantity, s_max_w: Quantity) -> int:
        """
        Smallest even number of stirrup legs whose transverse spacing fits within ``s_max_w``.

        The legs are spread evenly across the section, so the ``n_legs - 1`` gaps between
        them have to cover the distance separating the centres of the outermost pair,
        ``width - 2 * c_c - d_b``. ACI 318-19 Table 9.7.6.2.2 (column "Across width") /
        CIRSOC 201-25 Tabla 9.7.6.2.2 ("A través del ancho") and EN 1992-1-1 9.2.2(8)
        all cap that gap, which is what forces a wide section to carry more than the two legs
        of a single stirrup regardless of how much area the shear demand asks for.

        Parameters
        ----------
        d_b : Quantity
            Diameter of the stirrup bar being tried.
        s_max_w : Quantity
            Maximum spacing allowed across the width of the beam.

        Returns
        -------
        int
            Number of legs, always even and never below 2.
        """
        outer_span = self.beam.width - 2 * self.beam.c_c - d_b
        if outer_span <= 0 * cm or s_max_w <= 0 * cm:
            return 2
        # The tolerance keeps a span that divides exactly from rounding up a whole gap.
        n_gaps = math.ceil((outer_span / s_max_w).to("dimensionless").magnitude - 1e-9)
        n_legs = max(2, n_gaps + 1)
        # Legs come in pairs, one closed stirrup each.
        return n_legs + (n_legs % 2)

    def transverse_rebar(
        self,
        A_v_req: Quantity,
        V_s_req: Quantity,
        alpha: float,
        demand: Optional[_ShearDemand] = None,
    ) -> DataFrame:
        """Select the transverse reinforcement that covers ``A_v_req``.

        A beam and a slab strip are reinforced differently, so they are searched
        differently. A beam carries closed stirrups, so the free variables are
        the bar diameter, the number of legs across the width and the spacing
        along the length. A slab strip carries a grid of legs, and both spacings
        are free -- the parameterisation
        :meth:`~mento.slab.OneWaySlab.set_slab_transverse_rebar` already takes.

        Args:
            A_v_req: Required area of transverse reinforcement per unit length.
            V_s_req: Shear the reinforcement must carry, which sets the spacing
                limits.
            alpha: Inclination of the shear reinforcement, for EN.
            demand: Reads ``(A_v_req, V_s_req)`` off the section as it is when
                called. Given, each bar diameter is sized against the demand the
                section has with that bar on it -- see
                :meth:`_transverse_rebar_beam` for why. Left out, the two values
                above stand for every diameter.

        Returns:
            Every valid combination, best first; ``transverse_rebar_design``
            reads the first row.
        """
        if self.mode == "slab":
            return self._transverse_rebar_slab(A_v_req, V_s_req, alpha, demand)
        return self._transverse_rebar_beam(A_v_req, V_s_req, alpha, demand)

    def _transverse_rebar_beam(
        self,
        A_v_req: Quantity,
        V_s_req: Quantity,
        alpha: float,
        demand: Optional[_ShearDemand] = None,
    ) -> DataFrame:
        """Closed stirrups: (d_b, n_legs, s_l), the legs spread across the width.

        Every diameter is tried against the section it would make. The demand
        and the spacing limits are both written on the effective depth, and a
        heavier stirrup sits the bars deeper: at the depth of its own diameter
        a candidate needs a little more ``A_v`` and, when ``V_s,req`` crosses
        the threshold of ACI 318-19 Table 9.7.6.2.2 / CIRSOC 201-25
        Tabla 9.7.6.2.2 there, half the spacing. Reading the limits off
        whatever diameter the section held before is what let a first design
        detail 28 cm against a limit the finished beam puts at 27.95 cm; reading
        the demand off it is what let the design of a 30x40 CIRSOC beam
        trade Ø8 and Ø10 back and forth and apply 1eØ10/15 against a limit of
        8.9 cm. Each row is therefore sized at its own depth, and the row the
        design applies passes its own check by construction. That includes
        what the section's compression bars ask of the stirrups (ACI 318-19 /
        CIRSOC 201-25 §9.7.6.4): whether the section relies on them moves
        with the depth too, so the diameter floor and the spacing cap are
        read after the demand of each diameter, which the beam's ``demand``
        reads with its compression steel.

        For each diameter the search keeps the widest spacing, with the fewest
        legs, that covers the ``A_v_req`` of that diameter. The rows are then
        ranked by :meth:`_rank_stirrup_options`.
        """

        # Prepare the list for valid combinations
        valid_combinations = []

        # Get code specific limitations
        code = design_code(self.beam.concrete)

        # Iterate through available diameters
        for d_b in code.transverse_rebar(self, V_s_req, alpha)[0]:
            A_v_req_d, V_s_req_d = self._demand_for(d_b, A_v_req, V_s_req, demand)
            if not self._supports_compression(d_b):
                continue
            s_max_l, s_max_w = self._spacing_limits_for(d_b, V_s_req_d, alpha)
            # Start from the fewest legs that keep the transverse spacing within s_max_w,
            # rather than from a single stirrup: on a wide section two legs never comply.
            n_legs = self.min_legs_along_width(d_b, s_max_w)

            # Start with maximum allowed spacing s_max_l
            if self.beam.concrete.unit_system == "metric":
                s_l: Quantity = math.floor(s_max_l.to("cm").magnitude) * cm
            else:
                s_l = math.floor(s_max_l.to("inch").magnitude) * inch

            while True:
                # Calculate spacing based on current legs
                n_stirrups = math.ceil(n_legs / 2)  # Number of stirrups based on number of legs
                n_legs_actual = n_stirrups * 2  # Ensure legs are even
                # n_legs - 1 gaps span the distance between the outermost leg centres,
                # with the candidate diameter rather than the one on the section.
                s_w = (self.beam.width - 2 * self.beam.c_c - d_b) / (n_legs_actual - 1)

                A_db = self.rebar_areas[d_b]  # Area of a stirrup bar
                A_vs = n_legs_actual * A_db  # Area of vertical stirrups
                A_v: Quantity = A_vs / s_l  # Area of vertical stirrups per unit length

                # Store the valid combination if spacing is also valid
                if self.beam.concrete.unit_system == "metric":
                    # Check if the calculated A_v meets or exceeds the required A_v, and
                    # that the legs are close enough together across the width.
                    if A_v >= A_v_req_d and s_w <= s_max_w:
                        valid_combinations.append(
                            {
                                "n_stir": int(n_stirrups),
                                "d_b": d_b,
                                "s_l": s_l.to("cm"),  # spacing along length
                                "s_w": s_w.to("cm"),  # spacing along width
                                "A_v": A_v.to("cm**2/m"),
                                "A_v_req": A_v_req_d.to("cm**2/m"),
                                "s_max_l": s_max_l.to("cm"),
                                "s_max_w": s_max_w.to("cm"),
                            }
                        )
                        # Stop checking larger diameters
                        break

                    # If A_v is insufficient, reduce s_l by 1 cm
                    s_l -= 1 * cm
                    # If s_l becomes less than 5 cm, increase the number of legs by 2 and reset s_l to s_max_l
                    if s_l < 5 * cm:  # If spacing is less than 5 cm, increase 1 stirrup
                        n_legs += 2
                        s_l = math.floor(s_max_l.to("cm").magnitude) * cm  # Reset s_l to the max allowed spacing
                else:
                    # Check if the calculated A_v meets or exceeds the required A_v, and
                    # that the legs are close enough together across the width.
                    if A_v >= A_v_req_d and s_w <= s_max_w:
                        valid_combinations.append(
                            {
                                "n_stir": int(n_stirrups),
                                "d_b": d_b,
                                "s_l": s_l.to("inch"),  # spacing along length
                                "s_w": s_w.to("inch"),  # spacing along width
                                "A_v": A_v.to("inch**2/ft"),
                                "A_v_req": A_v_req_d.to("inch**2/ft"),
                                "s_max_l": s_max_l.to("inch"),
                                "s_max_w": s_max_w.to("inch"),
                            }
                        )
                        # Stop checking larger diameters
                        break

                    # If A_v is insufficient, reduce s_l by 1 inch
                    s_l -= 1 * inch
                    # If s_l becomes less than 2 inch, increase the number of legs by 2 and reset s_l to s_max_l
                    if s_l < 2 * inch:  # If spacing is less than 2 inch, increase 1 stirrup
                        n_legs += 2
                        s_l = math.floor(s_max_l.to("inch").magnitude) * inch  # Reset s_l to the max allowed spacing

        df_combinations = self._rank_stirrup_options(valid_combinations, A_v_req)
        self._trans_combos_df = df_combinations
        return df_combinations

    @staticmethod
    def _stirrup_excess(A_v: List[Quantity], A_v_req: List[Quantity]) -> List[float]:
        """How far each ``A_v`` overshoots its own requirement, as a fraction of it.

        One requirement per layout, because the demand is read at the depth of
        each layout's own stirrup. With nothing required the lightest option is
        the reference instead, so the numbers still say how much steel each one
        adds.
        """
        lightest = min(A_v)
        return [
            float((a / (req if req.magnitude > 0 else lightest)).to("dimensionless").magnitude) - 1
            for a, req in zip(A_v, A_v_req)
        ]

    def _rank_stirrup_options(self, combinations: List[Dict[str, Any]], A_v_req: Quantity) -> DataFrame:
        """Rank the stirrup layouts, the one to build first.

        One layout per bar diameter -- the widest spacing, with the fewest
        legs, that covers the ``A_v_req`` read at that diameter's depth -- and
        they are ordered as they always were: fewest stirrups first, least
        steel among those. The first row is the one the design applies.

        Each row also carries a ``functional``: the excess of ``A_v`` over the
        row's own ``A_v_req`` as a fraction of it, plus one for every stirrup
        beyond the fewest any layout needs. It says how much steel a layout adds
        over what its section asks for, which is what makes the alternatives
        comparable; it does not decide the order. A row that carries no
        ``A_v_req`` of its own is measured against the ``A_v_req`` given.
        """
        if not combinations:
            return pd.DataFrame(combinations)

        excess = self._stirrup_excess(
            [row["A_v"] for row in combinations], [row.get("A_v_req", A_v_req) for row in combinations]
        )
        n_min = min(row["n_stir"] for row in combinations)
        for row, over in zip(combinations, excess):
            row["functional"] = over + (row["n_stir"] - n_min)

        df = pd.DataFrame(combinations)
        # Sort combinations by the total rebar area required (ascending)
        # Sort by 'A_v' first, then by 'n_stir' to prioritize fewer bars
        df.sort_values(by=["n_stir", "A_v"], inplace=True)
        df.reset_index(drop=True, inplace=True)
        return df

    @contextmanager
    def _stirrup_of(self, d_b: Quantity) -> Iterator[None]:
        """The section with a stirrup of diameter ``d_b`` on it, for the duration.

        Only the diameter moves -- it is what sets the effective depth -- and
        it is put back afterwards, so a search leaves the section as it found
        it whatever it tried.
        """
        d_b_before = self.beam._stirrup_d_b
        try:
            self.beam._stirrup_d_b = d_b
            self.beam._update_effective_heights()
            yield
        finally:
            self.beam._stirrup_d_b = d_b_before
            self.beam._update_effective_heights()

    def _demand_for(
        self,
        d_b: Quantity,
        A_v_req: Quantity,
        V_s_req: Quantity,
        demand: Optional[_ShearDemand],
    ) -> Tuple[Quantity, Quantity]:
        """``(A_v_req, V_s_req)`` of the section carrying stirrups of diameter ``d_b``.

        The demand is written on the effective depth as much as the spacing
        limits are: ``A_v,req = V_s,req / (f_yt d)`` grows as a heavier stirrup
        lowers ``d``, and the ``V_s,req`` read there decides which row of the
        spacing table applies. Read at the diameter being tried, so that the
        layout kept for it is the one its own section asks for. Without a
        ``demand`` to read, the values the caller fixed stand.
        """
        if demand is None:
            return A_v_req, V_s_req
        with self._stirrup_of(d_b):
            return demand()

    def _spacing_limits_for(self, d_b: Quantity, V_s_req: Quantity, alpha: float) -> Tuple[Quantity, Quantity]:
        """The code's spacing limits for a section carrying stirrups of diameter ``d_b``.

        Both limits are written on the effective depth, and the effective depth
        moves with the stirrup diameter. A beam starts from the diameter its
        settings assume, 2 mm off the 10 mm it usually settles on -- enough to
        put a spacing past the limit; a slab starts from no stirrup at
        all, so assigning a 10 mm bar takes a whole centimetre off ``d`` and with
        it off ``s_max_l``. Evaluating the limits against the diameter actually
        being tried is what keeps the chosen spacing inside the limit the
        finished section is later checked against.
        """
        with self._stirrup_of(d_b):
            _, s_max_l, s_max_w = design_code(self.beam.concrete).transverse_rebar(self, V_s_req, alpha)
        support = self._compression_support(d_b)
        if support is not None:
            # The stirrups of a doubly reinforced section also brace its
            # compression bars: ACI 318-19 / CIRSOC 201-25 §9.7.6.4.3 cap the
            # spacing at the least of 16 d_b of the bar, 48 d_b of the stirrup
            # and the least dimension of the beam, beside Table 9.7.6.2.2.
            s_max_l = min(s_max_l, support.s_max.to(s_max_l.units))
        return s_max_l, s_max_w

    def _compression_support(self, d_b: Quantity) -> Any:
        """What the section's compression bars ask of a stirrup of diameter ``d_b``, if anything.

        The code's ``stirrup_compression_support`` -- ``None`` for a code
        with no such clause, and ``None`` from a code that has one when no
        face of the section acts as compression steel.
        """
        hook = design_code(self.beam.concrete).stirrup_compression_support
        return None if hook is None else hook(self.beam, d_b)

    def _supports_compression(self, d_b: Quantity) -> bool:
        """Whether a stirrup of diameter ``d_b`` is thick enough for the compression bars it braces.

        ACI 318-19 §9.7.6.4.2 / CIRSOC 201-25 Tabla 9.7.6.4.2, read with the
        compression steel the section relies on as the demand last left it
        -- for a beam, at the depth ``d_b`` itself gives the bars, since
        :meth:`_demand_for` reads the demand with that stirrup on.
        """
        support = self._compression_support(d_b)
        return support is None or d_b >= support.d_b_min

    def _transverse_rebar_slab(
        self,
        A_v_req: Quantity,
        V_s_req: Quantity,
        alpha: float,
        demand: Optional[_ShearDemand] = None,
    ) -> DataFrame:
        """A grid of legs: (d_b, s_l, s_w), with both spacings free.

        The limits a slab strip is held to are the beam ones: ACI 318-19
        §7.7.5.1 / CIRSOC 201-25 §7.7.5 both send the transverse reinforcement
        of a one-way slab to §9.7.6.2, so the spacing comes from
        ACI 318-19 Table 9.7.6.2.2 / CIRSOC 201-25 Tabla 9.7.6.2.2 exactly as
        it does for a beam.

        A slab strip is a metre cut out of a wider member, so its legs are not
        the two faces of a stirrup cage the way a beam's are: the transverse
        spacing is a free variable and the strip catches whatever number of legs
        that spacing gives -- 6.7 of them at 15 cm across a metre. The beam
        search cannot say that. It spreads an even number of legs between the
        outermost bar centres, so a wide strip starts from far more legs than
        the shear asks for and never comes back down.

        With ``A_v = A_db * (width / s_w) / s_l``, the least steel that still
        covers ``A_v_req`` is the largest product ``s_l * s_w`` that both limits
        allow, so that is what the loop below maximises, on the whole-unit grid
        the two spacings are detailed on.

        The spacing limits usually bind long before ``A_v_req`` does: a shallow
        slab has ``s_max_l = d/2``, which can put the provided ``A_v`` well above
        what the shear demands however the search is written. That is the
        detailing rule speaking, not slack left in the search.
        """
        metric = self.beam.concrete.unit_system == "metric"
        unit = cm if metric else inch
        # The floors the beam search stops at: closer than this no bar can be
        # placed, let alone vibrated around.
        s_min = 5 if metric else 2
        area_unit = "cm**2/m" if metric else "inch**2/ft"
        width = self.beam.width

        # The whole catalogue: the stirrup floor of §9.7.6.4.2 is the beams'
        # (a slab's transverse reinforcement goes to §9.7.6.2 alone).
        valid_diameters = design_code(self.beam.concrete).transverse_rebar(self, V_s_req, alpha)[0]

        valid_combinations = []
        for d_b in valid_diameters:
            # As in the beam search: what the strip asks for moves with the
            # depth the bar being tried gives it, and a slab starts a design
            # with no stirrup at all.
            A_v_req_d, V_s_req_d = self._demand_for(d_b, A_v_req, V_s_req, demand)
            s_max_l, s_max_w = self._spacing_limits_for(d_b, V_s_req_d, alpha)
            # Whole units, so the spacing is one a drawing can carry. The strip
            # caps the transverse spacing as well: a leg spacing wider than the
            # strip would put less than one leg in it.
            s_l_max = int(math.floor(s_max_l.to(unit).magnitude))
            s_w_max = int(math.floor(min(s_max_w, width).to(unit).magnitude))
            # High shear halves both limits, and half of a shallow slab's d is
            # already tighter than the floor. The limit wins when the two
            # disagree, exactly as the beam search ends up doing: its floor only
            # adds legs, it never stops the spacing going below it. One whole
            # unit is the hard floor, so that a limit rounding down to nothing
            # leaves an empty search rather than a division by zero.
            s_l_lo = max(1, min(s_min, s_l_max))
            s_w_lo = max(1, min(s_min, s_w_max))

            A_db = self.rebar_areas[d_b]
            # A_v >= A_v_req_d  <=>  s_l * s_w <= A_db * width / A_v_req_d.
            if A_v_req_d > 0 * A_v_req_d.units:
                product_max = (A_db * width / A_v_req_d).to(unit**2).magnitude
            else:
                product_max = math.inf

            best: Tuple[int, int] | None = None
            for s_l in range(s_l_max, s_l_lo - 1, -1):
                s_w = s_w_max if math.isinf(product_max) else min(s_w_max, int(product_max // s_l))
                if s_w < s_w_lo:
                    continue
                # Descending s_l with a strict comparison keeps the widest
                # longitudinal spacing among the products that tie.
                if best is None or s_l * s_w > best[0] * best[1]:
                    best = (s_l, s_w)
            if best is None:
                continue

            s_l_q, s_w_q = best[0] * unit, best[1] * unit
            n_legs = (width / s_w_q).to("dimensionless").magnitude
            valid_combinations.append(
                {
                    # A slab has no closed stirrup to count. This is the
                    # equivalent number of rows across the width, which is what
                    # the section stores the reinforcement as; A_v is computed
                    # from the spacing itself and is the value that governs.
                    "n_stir": max(1, round(n_legs / 2)),
                    "d_b": d_b,
                    "s_l": s_l_q,
                    "s_w": s_w_q,
                    "A_v": (A_db * n_legs / s_l_q).to(area_unit),
                    "A_v_req": A_v_req_d.to(area_unit),
                    "s_max_l": s_max_l.to(unit),
                    "s_max_w": s_max_w.to(unit),
                }
            )

        df_combinations = pd.DataFrame(valid_combinations)
        if not df_combinations.empty:
            # Least steel first. Unlike a beam, a slab gains nothing from a
            # heavier bar: the spacing limits already fix how close the legs go.
            # The functional is the excess alone, which ranks the same way.
            df_combinations["functional"] = self._stirrup_excess(
                list(df_combinations["A_v"]), list(df_combinations["A_v_req"])
            )
            df_combinations.sort_values(by=["A_v", "s_l"], ascending=[True, False], inplace=True)
            df_combinations.reset_index(drop=True, inplace=True)
        self._trans_combos_df = df_combinations
        return df_combinations

    ##########################################################
    # LONGITUDINAL REBAR DESIGN
    ##########################################################

    def longitudinal_rebar_ACI_318_19(
        self,
        A_s_req: Quantity,
        A_s_max: Quantity | None = None,
        mech_cover: Quantity | None = None,
    ) -> DataFrame:
        """
        Computes the required longitudinal reinforcement based on ACI 318-19,
        and on CIRSOC 201-25 with it: the layout rules the search applies are
        printed the same way in both codes.

        What it lays out is the flexural reinforcement only. ACI 318-19 §9.7.2.3
        / CIRSOC 201-25 §9.7.2.3, identical in both, also ask for skin
        reinforcement on each side face of a beam deeper than 900 mm, within
        h/2 of the tension face and at the spacing of §24.3.2; that is not
        generated here: beam.detailing_geometry supplies a separate proposal
        through beam.skin_reinforcement, without crediting its steel in strength.

        Args:
            A_s_req: Required longitudinal rebar area.
            A_s_max: Optional maximum allowable longitudinal rebar area. If not
                provided, the limit defaults to ``10 * A_s_req``.

        Returns:
            A DataFrame containing the best combinations of rebar details. If no
            combination satisfies ``A_s_req``, returns the combination with the
            maximum possible area.
        """
        self.A_s_req = A_s_req
        self.original_mech_cover = mech_cover
        effective_width = self.beam.width - 2 * (self.beam.c_c + self.beam._stirrup_d_b)

        # --- Early exit: no steel required -------------------------------------
        if A_s_req.to("cm**2").magnitude == 0:
            df = pd.DataFrame(
                [
                    {
                        "n_1": 0,
                        "d_b1": 0 * mm,
                        "n_2": 0,
                        "d_b2": None,
                        "n_3": 0,
                        "d_b3": None,
                        "n_4": 0,
                        "d_b4": None,
                        "total_as": 0 * cm**2,
                        "total_bars": 0,
                        "clear_spacing": self.beam.settings.clear_spacing.to("mm"),
                    }
                ]
            )
            self._long_combos_df = df
            return df

        # Variables to track the combinations
        valid_combinations = []
        best_fallback_combination = None  # To store the best fallback design
        max_fallback_cm2 = 0.0  # To track the maximum area in fallback cases
        # Create a list of rebar diameters that are equal to or greater than the minimum diameter.
        # Practice, not a clause: neither ACI 318-19 nor CIRSOC 201-25 states a
        # minimum diameter for the longitudinal reinforcement of a beam.
        if self.beam.concrete.unit_system == "metric":
            self.min_long_rebar = 10 * mm
        else:
            self.min_long_rebar = 3 * inch / 8

        # Filter valid rebar diameters based on the minimum longitudinal diameter per design code and beam settings
        valid_rebar_diameters = [
            d
            for d in self.rebar_diameters
            if d >= self.min_long_rebar
            and d >= self.beam.settings.minimum_longitudinal_diameter
            and d <= self.beam.settings.max_longitudinal_diameter
        ]

        # --- Float view of the search space ------------------------------------
        # The loops below evaluate tens of thousands of candidate layouts. Running
        # that arithmetic on pint Quantities was the dominant cost of the whole
        # flexure design, so units are stripped once here and re-applied only to
        # the handful of combinations actually kept (ADR-0005). Areas are in cm²
        # and diameters in mm throughout this block.
        areas_cm2 = [self.rebar_areas[d].to("cm**2").magnitude for d in valid_rebar_diameters]
        diams_mm = [d.to("mm").magnitude for d in valid_rebar_diameters]
        A_s_req_cm2 = A_s_req.to("cm**2").magnitude
        eff_width_mm = effective_width.to("mm").magnitude
        max_diam_diff_mm = self.beam.settings.max_diameter_diff.to("mm").magnitude
        max_bars = self.beam.settings.max_bars_per_layer
        layers_spacing_mm = self.beam.settings.layers_spacing.to("mm").magnitude
        # The end bars sit clear of the stirrup's bends, as the check and the
        # cage put them (section_geometry.end_setback): a layer is laid out
        # in the width left between them. Layer 1 always ends in its n1 = 2
        # bars, layer 2 in its n3 = 2. None on a slab strip, which has no cage.
        bend = stirrup_bend_inner_diameter(self.beam)[0] if self.mode != "slab" else None
        bend_mm = None if bend is None else float(bend.to("mm").magnitude)

        def layer_width_mm(d_end_mm: float, offset_mm: float) -> float:
            if bend_mm is None:
                return eff_width_mm
            return eff_width_mm - 2 * end_setback(bend_mm, d_end_mm, offset_mm)

        # n1 is fixed at 2, and A_s_req > 0 is guaranteed by the early exit above,
        # so both area limits are loop-invariant and are computed once.
        n1 = 2
        skip_limit_cm2 = 10 * A_s_req_cm2
        if A_s_max is not None:
            skip_limit_cm2 = min(skip_limit_cm2, A_s_max.to("cm**2").magnitude)
        max_limit_cm2 = max(skip_limit_cm2, n1 * self.rebar_areas[self.min_long_rebar].to("cm**2").magnitude)

        # The loops reach the same layout many times: a group with no bars has no
        # diameter, so every d_b2..d_b4 it is paired with yields the same row.
        # Only the first is kept. The key holds bar counts and indices into
        # valid_rebar_diameters, never Quantities: hashing a Quantity converts it
        # to base units, which made the old drop_duplicates on the DataFrame the
        # largest single cost of the flexure design.
        seen_layouts: set[tuple[int, ...]] = set()

        def keep_layout(
            i1: int, n2: int, i2: int, n3: int, i3: int, n4: int, i4: int, total_as_cm2: float, clear_mm: float
        ) -> None:
            key = (i1, n2, i2 if n2 > 0 else -1, n3, i3 if n3 > 0 else -1, n4, i4 if n4 > 0 else -1)
            if key in seen_layouts:
                return
            seen_layouts.add(key)
            d = valid_rebar_diameters
            valid_combinations.append(
                self._long_combo(n1, d[i1], n2, d[i2], n3, d[i3], n4, d[i4], total_as_cm2, clear_mm)
            )

        # valid_rebar_diameters is ascending, so "every diameter <= d_bN" is a
        # prefix of it and the nested loops can walk indices instead of
        # re-filtering the list with a pint comparison on each pass.
        for i1 in range(len(valid_rebar_diameters)):
            area1, d1_mm = areas_cm2[i1], diams_mm[i1]
            width1_mm = layer_width_mm(d1_mm, 0.0)
            for i2 in range(i1 + 1):
                area2, d2_mm = areas_cm2[i2], diams_mm[i2]

                # Quick upper-bound check for this diameter pair.
                # Max for layer 1 (n1 fixed, n2 up to max_bars); layer 2 can at
                # best mirror it, for both beam and slab mode.
                A_layer1_max = 2 * area1 + max_bars * area2  # n1=2 fixed
                A_total_max = 2 * A_layer1_max

                # If even the maximum possible As with these diameters
                # is less than required, skip all n2/n3/n4 loops.
                if A_total_max < min(A_s_req_cm2, skip_limit_cm2):
                    continue

                for i3 in range(i2 + 1):
                    area3, d3_mm = areas_cm2[i3], diams_mm[i3]
                    # Layer 2 sits behind the larger bar of layer 1, d_b1.
                    width2_mm = layer_width_mm(d3_mm, d1_mm + layers_spacing_mm)
                    for i4 in range(i3 + 1):
                        area4, d4_mm = areas_cm2[i4], diams_mm[i4]

                        # Condition 5: no two bar diameters may differ by more
                        # than max_diameter_diff. The four are in descending
                        # order here, so the widest pair is (d_b1, d_b4).
                        if d1_mm - d4_mm > max_diam_diff_mm:
                            continue

                        d_b1 = valid_rebar_diameters[i1]
                        d_b2 = valid_rebar_diameters[i2]
                        d_b3 = valid_rebar_diameters[i3]
                        d_b4 = valid_rebar_diameters[i4]

                        # Iterate over possible numbers of bars in each group
                        for n2 in range(0, max_bars + 1):  # n2 can be 0 or more
                            if n1 + n2 > max_bars:
                                continue  # Skip if the total bars in layer 1 exceed the limit
                            if n1 + n2 < getattr(self, "_min_layer_bars", 0):
                                continue  # A leg of the stirrups would hold no bar

                            clear_mm = self._layer_clear_spacing_mm(n1, n2, d1_mm, d2_mm, width1_mm)
                            if clear_mm is None:
                                continue
                            self._clear_spacing = clear_mm * mm

                            # Calculate area for layer 1
                            A_s_layer_1 = n1 * area1 + (n2 * area2 if n2 > 0 else 0.0)

                            if A_s_layer_1 > max_limit_cm2:
                                break  # further n2 will only increase area

                            # Check if total area from layer 1 is enough for required A_s
                            # And also less than the maximum limit
                            if A_s_layer_1 >= A_s_req_cm2 and A_s_layer_1 <= max_limit_cm2:
                                # Only consider layer 1 — no bars in layer 2
                                keep_layout(i1, n2, i2, 0, i3, 0, i4, A_s_layer_1, clear_mm)
                            else:
                                # Track the combination with the maximum possible area (fallback)
                                if A_s_layer_1 > max_fallback_cm2 and A_s_layer_1 <= max_limit_cm2:
                                    max_fallback_cm2 = A_s_layer_1
                                    best_fallback_combination = self._long_combo(
                                        n1, d_b1, n2, d_b2, 0, None, 0, None, A_s_layer_1, clear_mm
                                    )

                            # =============================================================
                            # --- Layer 2 combinations (beam vs slab logic) ---
                            # =============================================================

                            if self.mode == "slab":
                                # ---------------------------------------------------------
                                # In slab mode:
                                #  - Only two cases are considered:
                                #       (1) one single layer
                                #       (2) second layer identical to the first (mirror)
                                #  - n3 = n1, n4 = n2 when a second layer exists
                                # ---------------------------------------------------------
                                for has_second_layer in [False, True]:
                                    if not has_second_layer:
                                        n3, n4 = 0, 0
                                    else:
                                        n3, n4 = n1, n2

                                    # --- Compute total reinforcement in layer 2 ------------
                                    A_s_layer_2 = n3 * area3 + (n4 * area4 if n4 > 0 else 0.0)

                                    # --- Compute total reinforcement and evaluate -----------
                                    total_as = A_s_layer_1 + A_s_layer_2
                                    if total_as >= A_s_req_cm2 and total_as <= max_limit_cm2:
                                        keep_layout(i1, n2, i2, n3, i3, n4, i4, total_as, clear_mm)
                                    else:
                                        # Track fallback combination with maximum As
                                        if total_as > max_fallback_cm2 and total_as <= max_limit_cm2:
                                            max_fallback_cm2 = total_as
                                            best_fallback_combination = self._long_combo(
                                                n1, d_b1, n2, d_b2, n3, d_b3, n4, d_b4, total_as, clear_mm
                                            )

                            else:
                                # ---------------------------------------------------------
                                # Normal beam logic (original)
                                # ---------------------------------------------------------
                                for n3 in [0, 2]:
                                    for n4 in range(0, self.beam.settings.max_bars_per_layer + 1):
                                        # Ensure layer 2 bars are not more than layer 1 bars
                                        if n3 + n4 > n1 + n2:
                                            continue
                                        if n3 == 0 and n4 > 0:
                                            continue
                                        # Fewer, thinner bars than layer 1, so only the bends
                                        # can leave layer 2 tighter: the check reads the
                                        # tighter of the two against the face's minimum.
                                        if n3 > 0 and width2_mm < width1_mm:
                                            clear2_mm = (width2_mm - n3 * d3_mm - n4 * d4_mm) / (n3 + n4 - 1)
                                            limit2_mm = max(self._clear_limit_mm, self._vibrator_mm, d1_mm)
                                            if clear2_mm < limit2_mm and not math.isclose(clear2_mm, limit2_mm):
                                                continue
                                        A_s_layer_2 = n3 * area3 + (n4 * area4 if n4 > 0 else 0.0)

                                        total_as = A_s_layer_1 + A_s_layer_2
                                        if total_as >= A_s_req_cm2 and total_as <= max_limit_cm2:
                                            keep_layout(i1, n2, i2, n3, i3, n4, i4, total_as, clear_mm)
                                        else:
                                            if total_as > max_fallback_cm2 and total_as <= max_limit_cm2:
                                                max_fallback_cm2 = total_as
                                                best_fallback_combination = self._long_combo(
                                                    n1, d_b1, n2, d_b2, n3, d_b3, n4, d_b4, total_as, clear_mm
                                                )

        # Convert valid combinations to DataFrame (already free of repeated layouts)
        df = pd.DataFrame(valid_combinations)

        # If no valid combinations satisfy A_s_req, use the best fallback combination
        if df.empty and best_fallback_combination is not None:
            df = pd.DataFrame([best_fallback_combination])

        # Only calculate penalties if we have valid combinations
        if not df.empty:
            modified_df = self._calculate_penalties_long_rebar(df)
            # Sort by 'Functional' to sort by the best options
            modified_df.sort_values(by=["functional"], inplace=True)
            modified_df.reset_index(drop=True, inplace=True)
            self._long_combos_df = modified_df
            return modified_df.head(10)
        else:
            # Return empty DataFrame with expected structure if no combinations found
            self._long_combos_df = df
            return df

    def longitudinal_rebar_EN_1992_2004(
        self,
        A_s_req: Quantity,
        A_s_max: Quantity | None = None,
        mech_cover: Quantity | None = None,
    ) -> None:
        # The bar-selection strategy (fit the area with the fewest, most uniform
        # bars that still respect spacing and layer limits) is geometry, not code
        # provisions, so EN reuses the ACI selector. Only the areas fed into it
        # come from EN 1992-2004.
        self.longitudinal_rebar_ACI_318_19(A_s_req, A_s_max, mech_cover)

    def _layer_clear_spacing_mm(
        self,
        n1: int,
        n2: int,
        d1_mm: float,
        d2_mm: float,
        eff_width_mm: float,
    ) -> float | None:
        """
        Clear spacing between the bars of one layer, in mm.

        The clause is ACI 318-19 §25.2.1 / CIRSOC 201-25 §25.2.1, the same text
        in both: at least the greatest of 25 mm (1 in.), d_b and (4/3)*d_agg.
        Of those three the aggregate term is missing, because the section does
        not carry a maximum aggregate size; the vibrator size folded in beside
        them is site practice and not part of the clause, and it is zero on the
        bottom face (see :meth:`longitudinal_rebar`).

        Everything is a plain float: this runs inside the innermost loop of the
        longitudinal rebar search, where pint arithmetic dominated the cost.

        Parameters:
            n1 (int): Number of bars in the first group of the layer.
            n2 (int): Number of bars in the second group of the layer.
            d1_mm (float): Diameter of the first group of bars, in mm.
            d2_mm (float): Diameter of the second group of bars, in mm.
            eff_width_mm (float): Width available for bar placement, in mm.

        Returns:
            float | None: The clear spacing in mm, or None when it falls below
            the design limits (clear spacing, vibrator size, largest diameter).
        """
        clear_mm = (eff_width_mm - (n1 * d1_mm + n2 * d2_mm)) / (n1 + n2 - 1)

        # Determine the maximum clear spacing limit; the first two terms are
        # precomputed in __init__.
        max_clear_spacing_mm = max(self._clear_limit_mm, self._vibrator_mm, d1_mm, d2_mm)

        # The effective width arrives through unit conversions, so a spacing
        # that meets the limit exactly can come out a hair short of it:
        # 12 cm - 2*(25 mm + 8 mm) is 53.99999999999999 mm, which left two
        # Ø12 bars 29.999999999999993 mm apart against a 30 mm limit.
        if clear_mm < max_clear_spacing_mm and not math.isclose(clear_mm, max_clear_spacing_mm):
            return None
        # ... and, on a beam, no further apart than the crack-control cap of
        # ACI 318-19 / CIRSOC 201-25 §24.3.2 allows the bars nearest the
        # tension face: adjacent centres sit one clear distance and the larger
        # bar apart. Without this a wide web was laid out with two bars half
        # a metre apart, and the check that followed failed it.
        if self.mode != "slab" and self._max_centre_mm is not None:
            centre_mm = clear_mm + max(d1_mm, d2_mm)
            if centre_mm > self._max_centre_mm and not math.isclose(centre_mm, self._max_centre_mm):
                return None
        return clear_mm

    def _long_combo(
        self,
        n1: int,
        d_b1: Quantity,
        n2: int,
        d_b2: Quantity | None,
        n3: int,
        d_b3: Quantity | None,
        n4: int,
        d_b4: Quantity | None,
        total_as_cm2: float,
        clear_mm: float,
    ) -> Dict[str, Any]:
        """
        Builds one row of the longitudinal rebar combination table.

        This is where the search loop's floats become Quantities again: it runs
        once per candidate kept, not once per candidate evaluated. A group's
        diameter is reported as None when the group holds no bars.
        """
        return {
            "n_1": n1,
            "d_b1": d_b1,
            "n_2": n2,
            "d_b2": d_b2 if n2 > 0 else None,
            "n_3": n3,
            "d_b3": d_b3 if n3 > 0 else None,
            "n_4": n4,
            "d_b4": d_b4 if n4 > 0 else None,
            "total_as": total_as_cm2 * _CM2,
            "total_bars": n1 + n2 + n3 + n4,
            "clear_spacing": clear_mm * mm,
        }

    def _calculate_penalties_long_rebar(
        self,
        df: pd.DataFrame,
        alpha: float = 3.5,
        beta: float = 0.30,
        gamma: float = 0.25,
        delta: float = 1,
        epsilon: float = 0,  # No penalty for beams, just slabs
    ) -> pd.DataFrame:
        """
        Calculate penalties for rebar configurations and add them as columns to the DataFrame.

        Args:
            df (pd.DataFrame): The input DataFrame containing rebar configurations.
            alpha (float): Weight for the number of bars penalty.
            beta (float): Weight for the diameter difference penalty.
            gamma (float): Weight for the layer penalty.

        Returns:
            pd.DataFrame: The modified DataFrame with penalty columns and the final functional.
        """

        # Adjust penalty weights depending on element type
        if getattr(self, "mode", "beam") == "slab":
            # Slabs prefer many small bars → penalize large diameters and spacing more
            alpha *= 0.8  # reduce area weight (slabs have smaller demand differences)
            beta *= 0.1  # stronger sensitivity to number of bars
            gamma *= 0.5  # less penalty for multi-diameter use
            delta *= 0.5  # allow two layers if needed
            epsilon = 0.75  # strong penalty on large bar sizes

        # Calculate minimum bars and minimum area of steel
        min_bars = df["total_bars"].min()
        min_as = df["total_as"].min()

        # These penalties were computed with df.apply(axis=1), which builds a
        # Series for every row; on the few hundred candidates a design produces
        # that machinery, not the arithmetic, was the cost. The columns are
        # pulled out as plain lists once and scored in a single pass.
        groups = list(
            zip(
                df["n_1"].tolist(),
                df["d_b1"].tolist(),
                df["n_2"].tolist(),
                df["d_b2"].tolist(),
                df["n_3"].tolist(),
                df["d_b3"].tolist(),
                df["n_4"].tolist(),
                df["d_b4"].tolist(),
            )
        )

        diameter_penalties = []
        layer_penalties = []
        max_d_per_row = []
        min_d = None
        for n_1, d_1, n_2, d_2, n_3, d_3, n_4, d_4 in groups:
            # One entry per bar, so the spread below is weighted by bar count.
            diameters = []
            if n_1 > 0:
                diameters.extend([d_1.magnitude] * n_1)
            if n_2 > 0:
                diameters.extend([d_2.magnitude] * n_2)
            if n_3 > 0:
                diameters.extend([d_3.magnitude] * n_3)
            if n_4 > 0:
                diameters.extend([d_4.magnitude] * n_4)

            # Penalty for variation in bar diameters
            diameter_penalties.append(np.std(diameters) if diameters else 0.0)
            # Penalty for using a second layer of reinforcement
            layer_penalties.append(1 if (n_3 > 0 or n_4 > 0) else 0)

            # Every row reaching this point has n_1 == 2, so `diameters` is
            # never empty (the A_s_req == 0 case returns before scoring).
            max_d_per_row.append(max(diameters))
            row_min = min(diameters)
            min_d = row_min if min_d is None else min(min_d, row_min)

        # Calculate penalties and add them as columns
        min_as_mag = min_as.magnitude
        df["area_penalty"] = [alpha * q.magnitude / min_as_mag for q in df["total_as"]]
        # Prefer moderate bar counts, where very high or very low will be penalized
        df["bars_penalty"] = beta * ((df["total_bars"] - min_bars) / min_bars) ** 2
        df["diameter_penalty"] = [gamma * p for p in diameter_penalties]
        df["layer_penalty"] = [delta * p for p in layer_penalties]

        # Diameter size penalty, for very large or very small
        df["diameter_size_penalty"] = [epsilon * (d / min_d - 1) for d in max_d_per_row]

        # Slab penalty for large spacing. A preference, not a limit: the limit
        # is ACI 318-19 §7.7.2.3 / CIRSOC 201-25 §7.7.2.3 and it is enforced on
        # the chosen layout, not scored here. This 300 mm is applied to both
        # codes and coincides with what CIRSOC 201-25 §7.7.2.3 prints only by
        # chance.
        if getattr(self, "mode", "beam") == "slab":
            max_spacing_allowed = 300  # mm
            df["spacing_penalty"] = [
                (
                    0.0
                    if s.magnitude <= max_spacing_allowed
                    else (s.magnitude - max_spacing_allowed) / max_spacing_allowed
                )
                for s in df["clear_spacing"]
            ]
        else:
            df["spacing_penalty"] = 0

        # Calculate the final functional
        df["functional"] = (
            df["area_penalty"]
            + df["bars_penalty"]
            + df["diameter_penalty"]
            + df["layer_penalty"]
            + df["diameter_size_penalty"]
            + df["spacing_penalty"]
        )

        return df

    def longitudinal_rebar(
        self,
        A_s_req: Quantity,
        A_s_max: Quantity | None = None,
        mech_cover: Quantity | None = None,
        face: str | None = None,
        tension: bool = True,
    ) -> Dict[str, Any]:
        """
        Selects the appropriate longitudinal rebar method based on the design
        code.

        Args:
            A_s_req: Required longitudinal rebar area.
            A_s_max: Optional maximum allowable longitudinal rebar area.
            mech_cover: Optional mechanical cover to the bar centroid, used as
                the starting geometry for the layer layout.
            face: ``"bot"`` or ``"top"``, the face being laid out. The vibrator
                goes in from the top, so its size only sets the clear spacing
                of the top bars -- the rule the check and the warnings apply.
                ``None`` keeps it on whatever face this is, the safe side for a
                caller that does not say.
            tension: whether some load puts this face in tension. The
                crack-control cap of §24.3.2 is on the bars nearest a tension
                face (§9.7.2.2), and the check and ``bar_spacing_exceeds_max``
                read it there only; a face that is only ever compressed --
                the compression steel of a doubly reinforced beam -- is laid
                out without it. Held to it, two bars across a 40 cm web were
                too far apart, and a compression face with no room for a
                third was left bare. ``True`` keeps the cap, as before, for a
                caller that does not say.
        """
        vibrator = self.beam.settings.vibrator_size.to("mm").magnitude
        self._vibrator_mm = 0.0 if face == "bot" else vibrator
        self._max_centre_mm = self._tension_cap_mm if tension else None
        # Every stirrup leg holds a bar of the tension face: the first layer
        # carries at least as many bars as the section has legs. A face only
        # ever in compression is held by mounting bars where it has none.
        self._min_layer_bars = leg_count(self.beam) if tension and self.mode != "slab" else 0
        return design_code(self.beam.concrete).longitudinal_rebar(self, A_s_req, A_s_max, mech_cover)
