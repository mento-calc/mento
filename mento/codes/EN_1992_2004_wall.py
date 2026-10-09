"""In-plane shear of a structural wall — EN 1992-1-1:2004, §6.2 and §9.6.

The resistances are the beam's: V_Rd,c of Eqs. (6.2.a)/(6.2.b), the truss of
Eq. (6.8) with the horizontal bars as shear reinforcement at alpha = 90 deg,
and the strut of Eq. (6.9), with 1 <= cot(theta) <= 2.5 (§6.2.3(2)). What a
wall changes is the section they are written on and the reinforcement rules
around them:

1. **d and z.** A beam reads d off its bars; a wall has none at a fixed depth,
   so d = 0.8 l_w, a design assumption EN 1992-1-1 does not give, and
   z = 0.9 d of §6.2.3(1). The beam's own d would be l_w less the cover, some
   20 % deeper.
2. **rho_l of Eq. (6.2.a)** is the tension reinforcement at the end of the
   wall, which a :class:`~mento.shear_wall.ShearWall` does not declare. It is
   taken as zero, so the floor of Eq. (6.2.b) gives V_Rd,c -- conservative,
   and what a wall's end bars give in most cases anyway.
3. **alpha_cw** keeps the reduction of §6.2.3(3) Note 3 for a chord nearly
   crushed by the axial load, and none of the increases; see
   :func:`~mento.codes.en_1992_2004.equations.wall.compression_chord_coefficient`.
4. **The minimum shear reinforcement** of Eq. (9.5N) is a beam's (§9.2.2). A
   wall has the minima of §9.6, and asks for rho_w,min on top of them only
   once V_Ed passes V_Rd,c and the truss carries the shear -- conservative,
   since §9.6 does not ask for it at all.
5. **The minima depend the other way round from ACI 318-19.** A_s,hmin of
   §9.6.3(1) is a quarter of the vertical reinforcement the wall carries, so
   the design places the vertical mesh first and the horizontal one after it.

V_Rd follows the convention of the EN beam: under V_Rd,c the concrete carries
the shear and the wall resists the larger of V_Rd,c and its truss (§6.2.1(3));
past it the horizontal bars carry all of it, V_Rd = V_Rd,s capped by the strut
(§6.2.1(5)). A wall with no horizontal bars resists V_Rd,c.

Out of scope: the additional tensile force of Eq. (6.18) in the vertical
reinforcement, flexure and axial design, out-of-plane shear, the links of
§9.6.4 and seismic walls (EN 1998-1).
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from mento.codes.check_state import ENWallShearCheckState, new_en_wall_shear_state
from mento.codes.en_1992_2004.equations import shear as shear_eq
from mento.codes.en_1992_2004.equations import wall as wall_eq
from mento.codes.wall_mesh_design import select_wall_mesh
from mento.forces import Forces
from mento.material import Concrete_EN_1992_2004
from mento.units import MPa, N, mm

if TYPE_CHECKING:
    from mento.shear_wall import ShearWall


#: d = 0.8 l_w: the effective depth for in-plane shear. EN 1992-1-1 gives none
#: for a wall, whose vertical bars are spread over its length rather than
#: grouped at a depth; 0.8 l_w is the usual design assumption, and the one
#: ACI 318 itself prescribed for wall shear up to its 2011 edition.
EFFECTIVE_DEPTH_RATIO = 0.8

#: alpha_cc for the shear resistances, as the EN beam takes it: 1.00, not the
#: alpha_cc of §3.1.6(1) the concrete carries for flexure.
_ALPHA_CC_SHEAR = 1.0

#: The flattest strut §6.2.3(2) allows, cot(theta) = 2.5, and the steepest, 45 deg.
_THETA_MIN = math.atan(1 / 2.5)
_THETA_MAX = math.pi / 4

##########################################################
# WALL MESH BAR CATALOGUE
##########################################################

#: EN 1992-1-1 §9.6 limits the areas and the spacing of a wall's mesh and no
#: bar diameter, so the catalogue is a mento criterion: that of CIRSOC 201-25,
#: Ø6 mm and up for the horizontal mesh, Ø10 mm and up for the vertical one.
#: The Ø10 floor is above the 8 mm EN 1992-1-1 §9.5.2(1) recommends for the
#: longitudinal bars of a column, the nearest rule the code has.
_EN_WALL_BARS_HORIZONTAL = [6 * mm, 8 * mm, 10 * mm, 12 * mm, 16 * mm, 20 * mm, 25 * mm]
_EN_WALL_BARS_VERTICAL = [10 * mm, 12 * mm, 16 * mm, 20 * mm, 25 * mm]

#: Crack-control cap: the selector scores bars up to Ø12 first, as for ACI
#: 318-19 and CIRSOC 201-25. A mento criterion as well.
_EN_WALL_BAR_CAP = 12 * mm


##########################################################
# CHECK
##########################################################


def _strut(st: ENWallShearCheckState, f_ck: float) -> None:
    """theta, V_Rd,max and the section limit — EN 1992-1-1 §6.2.3(2)-(3), Eq. (6.9).

    The flattest strut that still carries V_Ed: cot(theta) = 2.5 while
    V_Rd,max there covers it, the angle at which Eq. (6.9) equals V_Ed up to
    45 deg, and 45 deg past that, where the wall fails by the strut whatever
    its reinforcement.
    """
    st.alpha_cw = wall_eq.compression_chord_coefficient(st.N_Ed / st.A_c, st.f_cd)
    st.nu_1 = shear_eq.strut_strength_reduction_factor(f_ck)
    V_max_flat = shear_eq.max_shear_resistance(st.alpha_cw, st.t, st.z, st.nu_1, st.f_cd, _THETA_MIN)
    V_max_steep = shear_eq.max_shear_resistance(st.alpha_cw, st.t, st.z, st.nu_1, st.f_cd, _THETA_MAX)
    st.section_shear_limit = V_max_steep
    if st.V_Ed <= V_max_flat:
        st.theta = _THETA_MIN
    elif st.V_Ed <= V_max_steep:
        st.theta = shear_eq.strut_angle(st.V_Ed, V_max_steep)
    else:
        st.theta = _THETA_MAX
    st.cot_theta = 1 / math.tan(st.theta)
    st.V_Rd_max = shear_eq.max_shear_resistance(st.alpha_cw, st.t, st.z, st.nu_1, st.f_cd, st.theta)
    st.max_shear_ok = st.V_Ed <= V_max_steep


def _check_shear_EN_1992_2004_wall(self: "ShearWall", force: Forces) -> ENWallShearCheckState:
    """In-plane shear of a wall under one combination, EN 1992-1-1 §6.2 and §9.6.

    Calculation only: the result is returned as a value, and only the
    reporting path copies it back onto the wall, as for the EN beam. See the
    module docstring for what differs from the beam's check.
    """
    if not isinstance(self.concrete, Concrete_EN_1992_2004):
        raise TypeError("EN 1992-1-1 wall shear check requires Concrete_EN_1992_2004.")
    concrete = self.concrete
    st = new_en_wall_shear_state()

    # Materials, at the boundary (ADR-0005): N, mm, MPa from here on.
    f_ck = concrete.f_ck.to(MPa).magnitude
    f_ywk = self.steel_bar.f_y.to(MPa).magnitude
    st.f_cd = _ALPHA_CC_SHEAR * f_ck / concrete.gamma_c
    st.f_ywd = f_ywk / self.steel_bar.gamma_s

    # Demand: V_Ed in the plane of the wall, N_Ed positive in compression.
    st.V_Ed = abs(force._V_z.to(N).magnitude)
    st.N_Ed = force._N_x.to(N).magnitude

    # Section: A_c = l_w t, d = 0.8 l_w, z = 0.9 d (§6.2.3(1)).
    st.t = self.thickness.to(mm).magnitude
    l_w = self.length.to(mm).magnitude
    st.length_ratio = l_w / st.t
    st.A_c = l_w * st.t
    st.d = EFFECTIVE_DEPTH_RATIO * l_w
    st.z = shear_eq.lever_arm(st.d)

    # V_Rd,c, Eqs. (6.2.a)/(6.2.b), with no end bars declared: rho_l = 0.
    st.k_value = shear_eq.size_effect_factor(st.d)
    st.rho_l = 0.0
    st.sigma_cp = shear_eq.axial_stress(st.N_Ed, st.A_c, st.f_cd)
    st.V_Rd_c = max(
        0.0,
        shear_eq.min_shear_resistance_without_reinforcement(f_ck, st.k_value, st.sigma_cp, st.t, st.d),
        shear_eq.shear_resistance_without_reinforcement(
            f_ck, concrete.gamma_c, st.k_value, st.rho_l, st.sigma_cp, st.t, st.d
        ),
    )

    # The strut, Eq. (6.9), at the angle the demand fixes.
    _strut(st, f_ck)

    # The truss of the horizontal bars, Eq. (6.8), and V_Rd as the EN beam
    # forms it: the larger of V_Rd,c and the truss under V_Rd,c (§6.2.1(3)),
    # the truss alone past it (§6.2.1(5)), capped by the strut.
    st.A_sh = float(self._rho_t) * st.t
    st.A_sv = float(self._rho_l) * st.t
    st.V_Rd_s = shear_eq.shear_reinforcement_resistance(st.A_sh, st.z, st.f_ywd, st.cot_theta)
    if st.A_sh == 0:
        st.V_Rd = st.V_Rd_c
    else:
        truss = min(st.V_Rd_s, st.V_Rd_max)
        st.V_Rd = max(st.V_Rd_c, truss) if st.V_Ed <= st.V_Rd_c else truss

    # What the horizontal bars have to provide: the truss and rho_w,min of
    # Eq. (9.5N) once V_Ed passes V_Rd,c, never less than A_s,hmin of §9.6.3(1).
    st.rho_w_min = shear_eq.min_shear_reinforcement_ratio(f_ck, f_ywk)
    if st.V_Ed > st.V_Rd_c:
        st.A_sh_str = shear_eq.required_shear_reinforcement(st.V_Ed, st.z, st.f_ywd, st.cot_theta)
        st.A_sh_w = st.rho_w_min * st.t
    st.A_sh_min = wall_eq.min_horizontal_reinforcement(st.A_sv, st.t)
    st.A_sh_req = max(st.A_sh_str, st.A_sh_w, st.A_sh_min)

    # The vertical mesh, §9.6.2(1), and the spacing of both, §9.6.2(3) / §9.6.3(2).
    st.A_sv_min = wall_eq.min_vertical_reinforcement(st.t)
    st.A_sv_max = wall_eq.max_vertical_reinforcement(st.t)
    st.s_v_max = wall_eq.max_vertical_spacing(st.t)
    st.s_h_max = wall_eq.MAX_HORIZONTAL_SPACING

    st.DCR = st.V_Ed / st.V_Rd if st.V_Rd > 0 else float("inf")
    return st


##########################################################
# DESIGN
##########################################################


def _design_shear_EN_1992_2004_wall(self: "ShearWall", forces: list) -> None:
    """Wall mesh design per EN 1992-1-1 §6.2 and §9.6, over every combination.

      1. The vertical mesh, at A_s,vmin of §9.6.2(1) and the spacing of
         §9.6.2(3). Shear asks nothing more of it; flexure and axial design
         are not implemented.
      2. The horizontal mesh, at the largest A_sh,req of the combinations with
         that vertical mesh in place -- A_s,hmin of §9.6.3(1) reads the
         vertical reinforcement provided, which is why it goes second -- and
         the spacing of §9.6.3(2).

    The strut angle, V_Rd,c and the truss demand do not depend on the mesh,
    so one pass settles both directions, and the design gives the same mesh
    every time it runs.
    """
    if not forces:
        raise ValueError("Wall shear design requires at least one Forces object.")

    t = self.thickness.to(mm).magnitude
    s_v_max = wall_eq.max_vertical_spacing(t) * mm
    d_b_v, s_v = select_wall_mesh(self, wall_eq.MIN_VERTICAL_RATIO, s_v_max, _EN_WALL_BARS_VERTICAL, _EN_WALL_BAR_CAP)
    self.set_vertical_rebar(d_b_v, s_v)

    A_sh_req = max(_check_shear_EN_1992_2004_wall(self, force).A_sh_req for force in forces)
    s_h_max = wall_eq.MAX_HORIZONTAL_SPACING * mm
    d_b_h, s_h = select_wall_mesh(self, A_sh_req / t, s_h_max, _EN_WALL_BARS_HORIZONTAL, _EN_WALL_BAR_CAP)
    self.set_horizontal_rebar(d_b_h, s_h)
