import math
from dataclasses import replace
from mento.units import Quantity
from typing import TYPE_CHECKING, Tuple, cast

# from devtools import debug


from mento.codes.en_1992_2004.equations import flexure as flexure_eq
from mento.codes.check_state import (
    to_display,
    ENFlexureCheckState,
    ENShearCheckState,
    apply_en_shear_state,
    new_en_flexure_state,
    new_en_shear_state,
)
from mento.codes.en_1992_2004.equations import shear as shear_eq
from mento.codes.flexure_design import _FaceDemand, _run_flexure_design
from mento.material import Concrete_EN_1992_2004
from mento.precompute import section_floats
from mento.rebar import max_stirrup_spacing_EN_1992_2004
from mento.units import MPa, mm, kNm, N
from mento.forces import Forces


if TYPE_CHECKING:
    from ..beam import RectangularBeam  # Import Beam for type checking only

# Prebuilt unit objects for the boundary conversions of ADR-0005. The equation
# layer works in N, mm, mm², MPa and N·mm; these are the only units crossing
# into and out of it, and building them once keeps the conversion off the hot
# path (`.to(_mm2)`, never `.to("mm**2")`).
_mm2 = mm**2
_Nmm = N * mm

#: Stands in for a resistance of exactly zero when the DCR is formed, so that a
#: face with no reinforcement on it reports a ratio far above 1 -- which is what
#: it is -- instead of dividing by zero. ACI keeps the same floor, at the same
#: 0.01 kNm; a resistance that small is already indistinguishable from none.
_MOMENT_FLOOR = 0.01e6  # N·mm; EN is metric only


def _initialize_variables_EN_1992_2004(self: "RectangularBeam") -> None:
    """
    Initialize variables for EN 1992-2004 design code.
    """
    if isinstance(self.concrete, Concrete_EN_1992_2004):
        self._f_ywd = self._f_ywk / self.steel_bar.gamma_s
        alpha_cc_shear = 1  # Take this as 1.00 for shear design and not 0.85, as in Eurocode Applied.
        self._f_cd_shear = alpha_cc_shear * self.concrete.f_ck / self.concrete.gamma_c
        # Flexure concrete resistance with a alpha_cc reduction
        self._f_cd = self.concrete.f_cd


##########################################################
# SHEAR CHECK AND DESIGN
##########################################################


def _initialize_shear_variables_EN_1992_2004(self: "RectangularBeam", st: ENShearCheckState, force: Forces) -> None:
    """
    Initialize variables for EN 1992-2004 design code.
    """
    if isinstance(self.concrete, Concrete_EN_1992_2004):
        sec = section_floats(self)
        # Set the initial variables
        st.N_Ed = force._N_x.to(N).magnitude
        st.V_Ed_1 = abs(force._V_z.to(N).magnitude)  # Same magnitude at support and at d
        st.V_Ed_2 = st.V_Ed_1

        # Minimum shear reinforcement calculation. Eq. (9.5N) gives the ratio;
        # §9.2.2(5) defines it as A_sw/(s*b_w*sin(alpha)), hence the geometry here.
        # §6.2.1(4) waives that minimum in members where the load can redistribute
        # transversally -- slabs are the example the clause names -- so there it is
        # zero and V_Rd,c alone decides whether stirrups are needed at all.
        if self._stirrups_optional:
            st.A_v_min = 0.0
        else:
            rho_min = shear_eq.min_shear_reinforcement_ratio(
                sec.f_c,
                self._f_ywk.to(MPa).magnitude,
            )
            st.A_v_min = rho_min * sec.width * math.sin(self._alpha)

        # Consider bottom or top tension reinforcement
        st.A_s_tension = sec.A_s_bot if force._M_y >= 0 * kNm else sec.A_s_top
        # _A_p is a placeholder for prestressing steel, always zero for now, and
        # is initialized too late to belong in the section's float view.
        A_p = self._A_p.to(_mm2).magnitude
        rho_l = min((st.A_s_tension + A_p) / (sec.width * sec.d_shear), 0.02)
        if force._M_y >= 0 * kNm:
            st.rho_l_bot = rho_l
        else:
            st.rho_l_top = rho_l

        # Shear calculation for sections without rebar
        st.k_value = shear_eq.size_effect_factor(sec.d_shear)

        # Positive of compression
        st.sigma_cp = shear_eq.axial_stress(st.N_Ed, sec.A_x, st.f_cd_shear)


def _shear_without_rebar_EN_1992_2004(self: "RectangularBeam", st: ENShearCheckState) -> float:
    st.theta = 0
    if isinstance(self.concrete, Concrete_EN_1992_2004):
        # Total shear capacity without rebar: Eq. (6.2.a), floored by Eq. (6.2.b).
        sec = section_floats(self)
        # Only the current force's tension face is populated in this state.
        # The section's _M_Ed may belong to an earlier flexure combination.
        rho_l = st.rho_l_bot + st.rho_l_top
        V_Rd_c_min = shear_eq.min_shear_resistance_without_reinforcement(
            sec.f_c, st.k_value, st.sigma_cp, sec.width, sec.d_shear
        )
        V_Rd_c = shear_eq.shear_resistance_without_reinforcement(
            sec.f_c,
            self.concrete.gamma_c,
            st.k_value,
            rho_l,
            st.sigma_cp,
            sec.width,
            sec.d_shear,
        )
    return max(0.0, V_Rd_c_min, V_Rd_c)


def _calculate_max_shear_strength_EN_1992_2004(self: "RectangularBeam", st: ENShearCheckState) -> None:
    """
    Calculate the maximum shear strength (V_Rd_max) and the corresponding strut angle (θ).
    """
    if isinstance(self.concrete, Concrete_EN_1992_2004):
        alpha_cw = 1.0  # Non-prestressed members or members subject to tensile stress due to axial force
        sec = section_floats(self)
        nu_1 = shear_eq.strut_strength_reduction_factor(sec.f_c)
        b_w = sec.width
        f_cd = st.f_cd_shear
        z = shear_eq.lever_arm(sec.d_shear)
        st.z = z  # Lever arm

        # The θ angle is limited between 21.8° ≤ θ ≤ 45° (1 ≤ cot(θ) ≤ 2.5)
        # Check the minimum strut angle θ = 21.8° (cot(θ) = 2.5)
        theta_min: float = math.radians(21.8)
        cot_theta_min: float = 1 / math.tan(theta_min)
        V_Rd_max_min_angle = shear_eq.max_shear_resistance(alpha_cw, b_w, z, nu_1, f_cd, theta_min)
        # The maximum strut angle θ = 45° (cot(θ) = 1.0), where cot θ + tan θ
        # is least and Eq. (6.9) is largest: the most the section can carry
        # however it is reinforced, §6.2.1(6). Kept apart from V_Rd_max,
        # which is the strut at the angle the demand fixes.
        theta_max: float = math.radians(45)
        V_Rd_max_max_angle = shear_eq.max_shear_resistance(alpha_cw, b_w, z, nu_1, f_cd, theta_max)
        st.section_shear_limit = V_Rd_max_max_angle

        if st.V_Ed_1 <= V_Rd_max_min_angle:
            # If within the minimum angle
            st.theta = theta_min
            st.cot_theta = cot_theta_min
            st.V_Rd_max = V_Rd_max_min_angle
            st.max_shear_ok = True
        else:
            if st.V_Ed_1 > V_Rd_max_max_angle:
                st.theta = theta_max
                st.cot_theta = 1 / math.tan(st.theta)
                st.V_Rd_max = V_Rd_max_max_angle
                st.max_shear_ok = False
            else:
                st.max_shear_ok = True
                # Determine the angle θ of the strut based on the shear force
                st.theta = shear_eq.strut_angle(st.V_Ed_1, V_Rd_max_max_angle)
                st.cot_theta = 1 / math.tan(st.theta)
                st.V_Rd_max = shear_eq.max_shear_resistance(alpha_cw, b_w, z, nu_1, f_cd, st.theta)


def _calculate_required_shear_reinforcement_EN_1992_2004(self: "RectangularBeam", st: ENShearCheckState) -> None:
    """
    Calculate the required shear reinforcement area (A_v_req).
    """
    sec = section_floats(self)
    z = st.z
    f_ywd = st.f_ywd
    # Calculate the required shear reinforcement area
    st.A_v_req = max(
        # Required area based on shear force, as an area per unit length
        shear_eq.required_shear_reinforcement(st.V_Ed_2, z, f_ywd, st.cot_theta),
        st.A_v_min,  # Minimum required area
    )
    st.V_Rd_s = shear_eq.shear_reinforcement_resistance(sec.A_v, z, f_ywd, st.cot_theta)
    st.V_s_req = st.V_Rd_s
    # Eq. (6.8)/(6.9): adding stirrups cannot exceed the concrete-strut limit.
    st.V_Rd = min(st.V_Rd_s, st.V_Rd_max)


def _stirrups_a_bare_section_needs_EN_1992_2004(self: "RectangularBeam", st: ENShearCheckState) -> None:
    """A_v,req, and the section limit, of a section that carries no stirrups.

    EN 1992-1-1 §6.2.1(3): where V_Ed <= V_Rd,c no calculated shear
    reinforcement is necessary, and (4) asks for the minimum of §9.2.2 all
    the same -- zero where the member may omit it, which the initialisation
    already settled in ``A_v_min``. §6.2.1(5): where V_Ed > V_Rd,c, enough
    that V_Ed <= V_Rd, which is the truss of §6.2.3 at the angle the demand
    asks for -- what the section will be checked with once it has stirrups,
    and what ``stirrups_required`` has to quote. The check used to quote the
    minimum whatever the shear, so a bare section under 300 kN was asked for
    the same 2.4 cm²/m as one under 30 kN.

    The strut limit of §6.2.1(6) does not depend on the stirrups either:
    a bare section that stays under V_Rd,max at 45° is short of stirrups,
    not of concrete, so ``shear_exceeds_section_limit`` reads that limit and
    not V_Rd,c, which is what it used to be handed.

    The truss is read on a copy of the state: what the report prints for a
    bare section -- no strut angle, V_Rd = V_Rd,c -- describes the section as
    it is and stays as it is.
    """
    truss = replace(st)
    _calculate_max_shear_strength_EN_1992_2004(self, truss)
    st.section_shear_limit = truss.section_shear_limit
    if st.V_Ed_2 <= st.V_Rd_c:
        st.A_v_req = st.A_v_min
        return
    st.A_v_req = max(
        shear_eq.required_shear_reinforcement(st.V_Ed_2, truss.z, st.f_ywd, truss.cot_theta),
        st.A_v_min,
    )


def _check_shear_EN_1992_2004(self: "RectangularBeam", force: Forces) -> ENShearCheckState:
    """Run the EN shear check for one combination and return what it found.

    Nothing is written to the section; see the ACI counterpart for the split
    between this and the reporting path.
    """
    st = new_en_shear_state(self)
    concrete = cast("Concrete_EN_1992_2004", self.concrete)

    # The material values the shear check needs. _f_cd belongs to flexure as
    # well, so it is carried rather than written.
    f_ck = section_floats(self).f_c
    st.f_ywd = self._f_ywk.to(MPa).magnitude / self.steel_bar.gamma_s
    alpha_cc_shear = 1  # Take this as 1.00 for shear design and not 0.85, as in Eurocode Applied.
    st.f_cd_shear = alpha_cc_shear * f_ck / concrete.gamma_c
    st.f_cd = concrete.alpha_cc * f_ck / concrete.gamma_c

    _initialize_shear_variables_EN_1992_2004(self, st, force)

    if self._stirrup_n == 0:
        # The assumed stirrup diameter stays: see the note in the ACI check.
        st.V_Rd_c = _shear_without_rebar_EN_1992_2004(self, st)
        # The stirrups the demand needs: the minimum of §9.2.2 under V_Rd,c
        # (§6.2.1(3)-(4)), the truss of §6.2.3 past it (§6.2.1(5)).
        _stirrups_a_bare_section_needs_EN_1992_2004(self, st)
        # The capacity of the section as it is: the concrete alone.
        st.V_Rd = st.V_Rd_c
        st.V_Rd_max = st.V_Rd
        st.max_shear_ok = st.V_Ed_1 <= st.V_Rd_max
    else:
        # The provided stirrup area per unit length is what the section already
        # carries; the setter computed it from the same geometry.
        _calculate_max_shear_strength_EN_1992_2004(self, st)
        _calculate_required_shear_reinforcement_EN_1992_2004(self, st)

        # Rebar spacing checks
        st.stirrup_s_w = section_floats(self).stirrup_s_w
        (
            st.stirrup_s_max_l,
            st.stirrup_s_max_w,
        ) = max_stirrup_spacing_EN_1992_2004(self, self._alpha)

    st.DCR = st.V_Ed_2 / st.V_Rd if st.V_Rd > 0 else float("inf")
    return st


def _design_shear_EN_1992_2004(self: "RectangularBeam", force: Forces) -> None:
    """Size the shear reinforcement. Designing is meant to change the section,
    so this runs the same helpers over a state and then applies it."""
    if isinstance(self.concrete, Concrete_EN_1992_2004):
        # Initialize all the code related variables
        _initialize_variables_EN_1992_2004(self)
        # Split bottom and top moments. Designing changes the section, so the
        # moment split is applied rather than kept local.
        flexure_st = new_en_flexure_state(self)
        _split_top_bot_moment(self, flexure_st, force)
        self._M_Ed, self._M_Ed_bot, self._M_Ed_top = (
            to_display(flexure_st.M_Ed, "moment", False),
            to_display(flexure_st.M_Ed_bot, "moment", False),
            to_display(flexure_st.M_Ed_top, "moment", False),
        )
        st = new_en_shear_state(self)
        st.f_ywd = self._f_ywd.to(MPa).magnitude
        st.f_cd_shear = self._f_cd_shear.to(MPa).magnitude
        st.f_cd = self._f_cd.to(MPa).magnitude
        _initialize_shear_variables_EN_1992_2004(self, st, force)

        if self._stirrups_optional:
            # §6.2.2(1): a member that needs no minimum stirrups needs none at all
            # while V_Ed stays within V_Rd,c. Sizing from the truss model regardless
            # would hand a slab a cage for a shear its concrete already carries.
            st.V_Rd_c = _shear_without_rebar_EN_1992_2004(self, st)
            if st.V_Ed_2 <= st.V_Rd_c:
                st.A_v_req = 0.0
                st.V_s_req = 0.0
                st.V_Rd = st.V_Rd_c
                st.V_Rd_max = st.V_Rd
                st.max_shear_ok = st.V_Ed_1 <= st.V_Rd_max
                apply_en_shear_state(self, st)
                return None

        # Calculate maximum shear strength
        _calculate_max_shear_strength_EN_1992_2004(self, st)
        # Calculate required shear reinforcement area
        _calculate_required_shear_reinforcement_EN_1992_2004(self, st)
        apply_en_shear_state(self, st)

        return None


##########################################################
# FLEXURE CHECK AND DESIGN
##########################################################


def _min_max_flexural_reinforcement_ratio_EN_1992_2004(
    self: "RectangularBeam",
) -> Tuple[float, float]:
    """
    Initialize variables for EN 1992-2004 design code.
    """
    if isinstance(self.concrete, Concrete_EN_1992_2004):
        # Calculate the minimum tensile reinforcement ratio
        rho_min = flexure_eq.min_reinforcement_ratio(
            self.concrete.f_ctm.to(MPa).magnitude,
            self.steel_bar.f_y.to(MPa).magnitude,
        )
        # Set the maximum tensile reinforcement ratio
        rho_max = flexure_eq.max_reinforcement_ratio()

        # # For positive moments (tension in the bottom), set minimum reinforcement accordingly.
        # if force._M_y > 0 * kNm:
        #     rho_min_top = 0 * dimensionless
        #     rho_min_bot = rho_min
        # else:
        #     rho_min_top = rho_min
        #     rho_min_bot = 0 * dimensionless

        # Calculate minimum and maximum bottom reinforcement areas
        # self._A_s_min_bot = rho_min_bot * self._d_bot * self._width
        # self._A_s_max_bot = rho_max * self._d_bot * self._width

    return rho_min, rho_max


#: Stress distribution coefficient k_c of EN 1992-1-1 §7.3.2(2) for a
#: rectangular section in pure bending. The clause's other value, 1.0, is for
#: pure tension, which is not a state a section designed here is in.
_K_C_BENDING = 0.4


def _maximum_flexural_reinforcement_area_EN_1992_2004(self: "RectangularBeam") -> float:
    """A_s,max of either face -- EN 1992-1-1 §9.2.1.1(3).

    "The cross-sectional area of tension or compression reinforcement should
    not exceed As,max outside lap locations", with 0,04 Ac the recommended
    value, and Ac is the cross-sectional area of the concrete (§1.6): b*h
    for a rectangle, the same for both faces. mento used to write it on
    b*d, about 10 % tighter than the clause and a different limit on each
    face.

    Returns:
        A_s,max (mm²).
    """
    _, rho_max = _min_max_flexural_reinforcement_ratio_EN_1992_2004(self)
    sec = section_floats(self)
    return rho_max * sec.width * sec.height


def _minimum_flexural_reinforcement_area_EN_1992_2004(self: "RectangularBeam", d: float) -> float:
    """A_s,min on the tension face, for the way this element is supported.

    A member spanning between supports gets the non-fragility minimum of
    §9.2.1.1, ``rho_min * b_t * d``.

    For support="soil", Mento instead adopts the larger of two minima. This
    is a modelling choice, not a general EN exemption from §9.2.1.1 or an
    assertion that soil support prevents brittle failure:

    * the halved geometric minimum of a foundation, on the gross section --
      EHE-08:2008 §42.3.5, Table 42.3.5, note (1), adopted practice under EN; and
    * the crack-control minimum of §7.3.2(2), which sizes the steel that has to
      carry the tension the concrete releases at the instant it cracks.

    The second governs the THIN footings, not the thick ones: it is written on
    ``A_ct = b*h/2``, so its ratio goes with ``k/2``, and ``k`` decays from 1.00
    to 0.65 between 300 and 800 mm of depth. The geometric minimum takes over
    once it has -- around h = 640 mm for C25 with B500S.

    Only a face in tension is asked for this. The caller splits the two faces by
    which one the moment puts in tension, and a face that is not in tension is
    given no minimum at all rather than a smaller one: whether a footing carries
    steel on that face is not a question a single section can answer.

    Args:
        d: Effective depth of the tension reinforcement (mm).

    Returns:
        A_s,min (mm²).
    """
    sec = section_floats(self)
    if self.support != "soil":
        rho_min, _ = _min_max_flexural_reinforcement_ratio_EN_1992_2004(self)
        return rho_min * d * sec.width

    concrete_en = cast("Concrete_EN_1992_2004", self.concrete)
    A_s_geometric = flexure_eq.foundation_min_reinforcement_ratio(sec.f_y) * sec.width * sec.height
    A_s_crack = flexure_eq.crack_control_min_reinforcement(
        _K_C_BENDING,
        flexure_eq.crack_control_coefficient_k(sec.height),
        concrete_en.f_ctm.to(MPa).magnitude,
        # The tension zone just before the first crack: the section is still
        # uncracked there, so the neutral axis sits at mid-depth and half of a
        # rectangle is in tension.
        sec.width * sec.height / 2,
        # The stress permitted in the bars right after cracking, taken at the
        # design yield strength.
        sec.f_y / self.steel_bar.gamma_s,
    )
    return max(A_s_geometric, A_s_crack)


def _compression_zone_limits_EN_1992_2004(self: "RectangularBeam", d: float) -> Tuple[float, float]:
    """Compression zone at the ductility limit, as (neutral axis, block depth).

    Both limits used by Mento are written on the NEUTRAL AXIS ratio
    ``x_u/d``: the redistribution limit of EN 1992-1-1:2004 §5.5(4),
    Eqs. (5.10a)/(5.10b), and an additional Mento design cap of 0.45.
    The fixed cap is not prescribed by §5.5(4). The equivalent
    rectangular stress block of 3.1.7(3) is ``lambda`` times shallower than the
    neutral axis, so the conversion happens once, here, and every caller gets
    both depths already in the right units.

    Returns
    -------
    (x_u_lim, x_eff_lim)
        Neutral axis depth and equivalent rectangular block depth at the limit.
    """
    concrete_en = cast("Concrete_EN_1992_2004", self.concrete)
    lambda_ = concrete_en._lambda_factor()
    xi_lim = flexure_eq.neutral_axis_depth_limit_ratio(  # x_u/d
        section_floats(self).f_c,
        concrete_en._delta,
        concrete_en._k_1,
        concrete_en._k_2,
        concrete_en._k_3,
        concrete_en._k_4,
    )
    x_u_lim = xi_lim * d
    return x_u_lim, lambda_ * x_u_lim


def _calculate_flexural_reinforcement_EN_1992_2004(
    self: "RectangularBeam", M_Ed: float, d: float, d_prima: float
) -> tuple[float, float, float, float, float]:
    """
    Calculate the required top and bottom reinforcement areas for bending.

    Returns ``(A_s_min, A_s_max, A_s1, A_s2, A_s_calc)``. ``A_s1`` is the
    tension steel to detail, never below the minimum; ``A_s_calc`` is the steel
    the moment alone asks for, before that minimum -- zero with no moment, and
    ``A_s1_lim + A_s2`` once compression steel is needed. An anchorage scaled by
    ``A_s,nec / A_s,prov`` reads the second, since a face governed by its
    minimum carries little of the stress the minimum is sized for.
    """
    # ADR-0005 boundary: convert once, compute in floats (N, mm, MPa, N·mm),
    # re-apply units on the way out.
    sec = section_floats(self)
    b = sec.width
    d_mm = d
    A_s_min = _minimum_flexural_reinforcement_area_EN_1992_2004(self, d_mm)
    A_s_max = _maximum_flexural_reinforcement_area_EN_1992_2004(self)

    # Constants and material properties
    if isinstance(self.concrete, Concrete_EN_1992_2004):
        eta = self.concrete._eta_factor()  # Factor for concrete strength (EN 1992-1-1)
        # Derived from the concrete rather than read off the beam: it is a
        # material property, so a check has no reason to have stored it first.
        f_cd = self.concrete.alpha_cc * sec.f_c / self.concrete.gamma_c
        # Define f_yd
        f_yd = sec.f_y / self.steel_bar.gamma_s

        # Compression zone at the ductility limit (EC2 5.5(4) and the 0.45 cap)
        x_u_lim, x_eff_lim = _compression_zone_limits_EN_1992_2004(self, d)
        # Limit moment for compressive reinforcement
        M = M_Ed
        M_lim = flexure_eq.limit_moment(eta, f_cd, b, x_eff_lim, d_mm)

        # Check if compressive reinforcement is required
        if M <= M_lim:
            # No compressive reinforcement required. Inverting
            # M = eta*f_cd*b*x_eff*(d - 0.5*x_eff) already yields lambda*x, so
            # lambda must NOT be applied again to the lever arm below.
            x_eff = flexure_eq.compression_block_depth_for_moment(M, b, d_mm, eta, f_cd)

            # Area the moment asks for, and the tensile reinforcement to
            # detail: that or the minimum, whichever is larger
            A_s_calc = flexure_eq.reinforcement_for_moment(M, flexure_eq.lever_arm(d_mm, x_eff), f_yd)
            A_s1 = max(A_s_calc, A_s_min)
            # No compressive reinforcement required
            A_s2 = 0.0

        else:
            # Compressive reinforcement is required
            self._doubly_reinforced = True
            d_prime = d_prima
            # Limit tensile reinforcement area
            A_s1_lim = flexure_eq.reinforcement_for_moment(M_lim, flexure_eq.lever_arm(d_mm, x_eff_lim), f_yd)

            # Compressive reinforcement stress, from the strain at the neutral
            # axis at the plastic limit (EC2 §5.5)
            f_sd = flexure_eq.compression_steel_stress(
                x_u_lim,
                d_prime,
                self.concrete.epsilon_cu2,
                sec.E_s,
                f_yd,
            )

            # Extra moment to take with top reinforcement, on the lever arm
            # (d - d') of the compression steel couple
            A_s2 = flexure_eq.reinforcement_for_moment(M - M_lim, d_mm - d_prime, f_sd)

            # Required tensile reinforcement area: the couple, or the minimum
            A_s_calc = A_s1_lim + A_s2
            A_s1 = max(A_s_calc, A_s_min)

    return A_s_min, A_s_max, A_s1, A_s2, A_s_calc


def _simple_determine_nominal_moment_EN_1992_2004(
    self: "RectangularBeam",
    A_s: float,
    d: float,
    A_s_prime: float,
    d_prime: float,
) -> float:
    """
    Design bending resistance M_Rd of a rectangular section.

    The reinforcement on the compression face is only part of the resisting
    couple when the section *needs* it to be in equilibrium, i.e. when the
    compression block required to balance the tension steel exceeds the
    ductility limit ``x_eff_lim``. Below that limit the concrete alone balances
    the tension steel: any bar on the compression face is then an erection or
    detailing bar, it is ignored (safe side), and the lever arm stays the singly
    reinforced one. Only above the limit does the concrete saturate at
    ``M_lim`` and the excess tension steel pair with the compression steel,
    which is what changes the lever arm to ``d - d'``.

    This mirrors :func:`_calculate_flexural_reinforcement_EN_1992_2004`, which
    sizes the tension steel with exactly the same criterion, so that a layout
    coming out of ``design_flexure`` is verified by ``check_flexure`` under the
    same mechanical model.

    For reference see Jimenez Montoya 16 Ed. P 213.
    """
    # Constants and material properties
    if isinstance(self.concrete, Concrete_EN_1992_2004):
        sec = section_floats(self)
        f_yd = sec.f_y / self.steel_bar.gamma_s
        f_cd = self.concrete.alpha_cc * sec.f_c / self.concrete.gamma_c
        eta = self.concrete._eta_factor()  # Factor for concrete strength
        b = sec.width
        d_mm = d
        A_s_mm2 = A_s

        # Depth of the equivalent rectangular block that balances the whole
        # tension steel, assuming the section is singly reinforced.
        x_eff = flexure_eq.compression_block_depth_for_steel(A_s_mm2, f_yd, eta, f_cd, b)

        # Ductility limit -- same criterion as the reinforcement sizing routine.
        _, x_eff_lim = _compression_zone_limits_EN_1992_2004(self, d)

        if x_eff <= x_eff_lim:
            # Singly reinforced: A_s_prime is not required for equilibrium.
            M_Rd = flexure_eq.moment_resistance_singly_reinforced(A_s_mm2, f_yd, d_mm, x_eff)
        else:
            # Doubly reinforced: the concrete contribution saturates at the
            # ductility limit and the excess tension steel is balanced by the
            # compression reinforcement, with lever arm (d - d').
            M_Rd = flexure_eq.moment_resistance_doubly_reinforced(
                A_s_mm2, A_s_prime, f_yd, eta, f_cd, b, d_mm, d_prime, x_eff_lim
            )
    return M_Rd


def _determine_nominal_moment_EN_1992_2004(self: "RectangularBeam", st: ENFlexureCheckState, force: Forces) -> None:
    """
    Determines the nominal moment for a given section with both top and bottom reinforcement,
    calculating the nominal moment for both positive and negative moment scenarios.

    For positive moments, the tension is in the bottom reinforcement.
    For negative moments, the tension is in the top reinforcement.

    Parameters:
        force (Forces): An object containing the forces acting on the section, including the moment M_y.

    Returns:
        None
    """
    # For positive moments (tension in the bottom), set minimum reinforcement
    # accordingly. The minimum is asked for as an area rather than a ratio: the
    # rules that apply to a member on the ground are written on the gross
    # section, so there is no single ratio both cases can be expressed in.
    sec = section_floats(self)
    tension_at_bottom = force._M_y > 0 * kNm

    # Calculate minimum and maximum bottom reinforcement areas
    st.A_s_min_bot = _minimum_flexural_reinforcement_area_EN_1992_2004(self, sec.d_bot) if tension_at_bottom else 0.0
    st.A_s_max_bot = _maximum_flexural_reinforcement_area_EN_1992_2004(self)
    # Determine the nominal moment for positive moments
    st.M_Rd_bot = _simple_determine_nominal_moment_EN_1992_2004(
        self, sec.A_s_bot, sec.d_bot, sec.A_s_top, sec.c_mec_top
    )
    # Determine capacity for negative moment (tension at the top). Only a
    # negative moment puts the top in tension, so only then does it take a
    # minimum: with no moment the bottom keeps its own (the positive branch of
    # the check), and a top that nothing pulls is not held to one.
    tension_at_top = force._M_y < 0 * kNm
    st.A_s_min_top = _minimum_flexural_reinforcement_area_EN_1992_2004(self, sec.d_top) if tension_at_top else 0.0
    st.A_s_max_top = st.A_s_max_bot
    st.M_Rd_top = _simple_determine_nominal_moment_EN_1992_2004(
        self, sec.A_s_top, sec.d_top, sec.A_s_bot, sec.c_mec_bot
    )
    return None


def _split_top_bot_moment(self: "RectangularBeam", st: ENFlexureCheckState, force: Forces) -> None:
    st.M_Ed = force._M_y.to(_Nmm).magnitude
    if st.M_Ed > 0:
        st.M_Ed_bot = st.M_Ed
        st.M_Ed_top = 0.0
    else:
        st.M_Ed_bot = 0.0
        st.M_Ed_top = st.M_Ed


# ─────────────────────────────────────────────────────────────────────────────
# Flexural design — EN 1992-2004 hooks for the shared driver
# ─────────────────────────────────────────────────────────────────────────────
# The design *strategy* -- Picard loop on the mechanical covers, discrete rebar
# selection, face reconciliation, cycle detection and final capacity
# verification -- lives in `mento.codes.flexure_design` and is shared with
# ACI 318-19. Only the two hooks below are EN-specific.


def _flexure_capacity_EN_1992_2004(self: "RectangularBeam", face: str, M_demand: Quantity) -> Quantity:
    """M_Rd of the layout currently applied to the section, on `face`.

    Recomputed rather than read from cached state so that the centroid of the
    layout just applied is taken into account.
    """
    M_abs = abs(M_demand)
    probe_force = Forces(M_y=(M_abs if face == "bot" else -M_abs))
    st = new_en_flexure_state(self)
    _determine_nominal_moment_EN_1992_2004(self, st, probe_force)
    # The design wants the capacity on the beam too; a check never comes here.
    self._M_Rd_bot = to_display(st.M_Rd_bot, "moment", False)
    self._M_Rd_top = to_display(st.M_Rd_top, "moment", False)
    self._A_s_min_bot = to_display(st.A_s_min_bot, "area", False)
    self._A_s_max_bot = to_display(st.A_s_max_bot, "area", False)
    return self._M_Rd_bot if face == "bot" else self._M_Rd_top


def _flexure_within_maximum_EN_1992_2004(self: "RectangularBeam") -> bool:
    """Does neither face carry more than A_s,max?

    EN 1992-1-1 §9.2.1.1(3): "The cross-sectional area of tension or
    compression reinforcement should not exceed A_s,max" -- either face,
    whichever does what, so the face in tension does not matter. Held against
    the same 0.04*b*h the check reports the limit as
    (:func:`_maximum_flexural_reinforcement_area_EN_1992_2004`). A design that
    reached the moment past it would hand back a section the check warns about.
    """
    sec = section_floats(self)
    A_s_max = _maximum_flexural_reinforcement_area_EN_1992_2004(self)
    return max(sec.A_s_bot, sec.A_s_top) <= A_s_max * (1 + 1e-9)


def _flexure_admissible_EN_1992_2004(self: "RectangularBeam", face: str) -> bool:
    """The registry's ``flexure_admissible`` hook: :func:`_flexure_within_maximum_EN_1992_2004`.

    ``face`` does not enter, because EN 1992-1-1 §9.2.1.1(3) caps the bars of
    either face whatever they do; the hook takes it so that every code answers
    the same question in the same shape.
    """
    return _flexure_within_maximum_EN_1992_2004(self)


def _required_areas_EN_1992_2004(
    self: "RectangularBeam", face: str, M: Quantity, d: Quantity, d_prime: Quantity
) -> _FaceDemand:
    """Steel required by EN 1992-2004 on `face` for the moment `M`."""
    # The design sizes bars, so it wants the minimum folded in, not A_s_calc.
    A_s_min, A_s_max, A_s1, A_s2, _A_s_calc = _calculate_flexural_reinforcement_EN_1992_2004(
        self, M.to(_Nmm).magnitude, d.to(mm).magnitude, d_prime.to(mm).magnitude
    )
    # The design path speaks pint on both sides; only the calculation is floats.
    A_s_min, A_s_max, A_s1, A_s2 = (
        to_display(A_s_min, "area", False),
        to_display(A_s_max, "area", False),
        to_display(A_s1, "area", False),
        to_display(A_s2, "area", False),
    )
    if face == "bot":
        self._A_s_min_bot, self._A_s_max_bot = A_s_min, A_s_max
    else:
        self._A_s_min_top, self._A_s_max_top = A_s_min, A_s_max
    return _FaceDemand(A_s_min, A_s_max, A_s1, A_s2)


def _design_flexure_EN_1992_2004(self: "RectangularBeam", max_M_y_bot: Quantity, max_M_y_top: Quantity) -> None:
    """Design the longitudinal reinforcement of a beam per EN 1992-2004.

    Thin wrapper: everything that is not an EN equation lives in
    ``mento.codes.flexure_design``.
    """
    _initialize_variables_EN_1992_2004(self)

    def _required(face: str, M: Quantity, d: Quantity, d_prime: Quantity) -> _FaceDemand:
        return _required_areas_EN_1992_2004(self, face, M, d, d_prime)

    def _capacity(face: str, M: Quantity) -> Quantity:
        return _flexure_capacity_EN_1992_2004(self, face, M)

    def _admissible(face: str) -> bool:
        return _flexure_within_maximum_EN_1992_2004(self)

    _run_flexure_design(self, max_M_y_bot, max_M_y_top, _required, _capacity, _admissible)


def _check_flexure_EN_1992_2004(self: "RectangularBeam", force: Forces) -> ENFlexureCheckState:
    """Check the flexural capacity per EN 1992-1-1 and return what it found.

    Nothing is written to the section; only the reporting path copies the
    result back. See the ACI counterpart for the same split.
    """
    st = new_en_flexure_state(self)
    concrete = cast("Concrete_EN_1992_2004", self.concrete)

    # The material values this check needs, carried rather than written.
    sec = section_floats(self)
    st.f_ywd = self._f_ywk.to(MPa).magnitude / self.steel_bar.gamma_s
    st.f_cd_shear = sec.f_c / concrete.gamma_c
    st.f_cd = concrete.alpha_cc * sec.f_c / concrete.gamma_c

    # Split bottom and top moments
    _split_top_bot_moment(self, st, force)

    # Calculate the nominal moments for both top and bottom reinforcement.
    _determine_nominal_moment_EN_1992_2004(self, st, force)
    if st.M_Ed >= 0:
        # For positive moments, calculate the reinforcement requirements for the bottom tension side.
        (
            st.A_s_min_bot,
            st.A_s_max_bot,
            st.A_s_req_bot,
            st.A_s_req_top,
            st.A_s_calc_bot,
        ) = _calculate_flexural_reinforcement_EN_1992_2004(self, st.M_Ed_bot, sec.d_bot, sec.c_mec_top)
        st.c_d_top = 0
        # Calculate the design capacity ratio for the bottom side.
        if st.M_Rd_bot == 0:
            st.M_Rd_bot = _MOMENT_FLOOR
        # Unrounded: a design 0.05 % short read 1.000 and passed. The reports
        # round when they print.
        st.DCR_bot = st.M_Ed_bot / st.M_Rd_bot
        st.DCR_top = 0
    else:
        # For negative moments, calculate the reinforcement requirements for the top tension side.
        (
            st.A_s_min_top,
            st.A_s_max_top,
            st.A_s_req_top,
            st.A_s_req_bot,
            st.A_s_calc_top,
        ) = _calculate_flexural_reinforcement_EN_1992_2004(self, abs(st.M_Ed_top), sec.d_top, sec.c_mec_bot)
        st.c_d_bot = 0
        # Calculate the design capacity ratio for the top side.
        if st.M_Rd_top == 0:
            st.M_Rd_top = _MOMENT_FLOOR
        st.DCR_top = -st.M_Ed_top / st.M_Rd_top
        st.DCR_bot = 0

    # Determine the maximum detailing cover dimensions for top and bottom.
    st.d_b_max_top = max(self._d_b1_t, self._d_b2_t, self._d_b3_t, self._d_b4_t).to(mm).magnitude
    st.d_b_max_bot = max(self._d_b1_b, self._d_b2_b, self._d_b3_b, self._d_b4_b).to(mm).magnitude

    # Calculate the longitudinal reinforcement ratios for both sides.
    # rho_l = A_sl/(b_w*d) of EN 1992-1-1 §6.2.2(1), reported per face: each one
    # takes its OWN steel against its OWN effective depth. The top ratio used to
    # be fed with A_s_bot, so the top flexure table printed a ratio that did not
    # belong to the A_s it was printed next to. Unlike the shear state, these are
    # not capped at 0.02: they are reported, not fed to Eq. (6.2.a).
    st.rho_l_bot = sec.A_s_bot / (sec.d_bot * sec.width)
    st.rho_l_top = sec.A_s_top / (sec.d_top * sec.width)

    return st


##########################################################
# RESULTS
##########################################################
