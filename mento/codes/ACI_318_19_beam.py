"""Shear and flexure of a rectangular beam — ACI 318-19, and CIRSOC 201-25 with it.

CIRSOC 201-25 is the Argentine adoption of ACI 318-19 and keeps its article
numbering, so a clause written here as ``ACI 318-19 §9.6.3.1 / CIRSOC 201-25
§9.6.3.1`` is the same clause in both books. The registry gives the two codes
the same hooks, and whatever the two actually print differently arrives as a
datum of the registry entry — never as a comparison against the code's title
(see ``mento/codes/registry.py`` and ADR-0002).

Where the printed text does differ, the difference is stated at the point of
use on a ``CIRSOC 201-25 §x differs`` line. Those lines document the codes, not
this module's behaviour: reading them next to the code is what shows whether
the two still agree.
"""

from mento.units import Quantity
from typing import TYPE_CHECKING, Optional, cast
import warnings
# from devtools import debug

from mento.codes.flexure_design import _FaceDemand, _run_flexure_design
from mento.codes.aci_318_19.equations import flexure as flexure_eq
from mento.codes.check_state import (
    CompressionSupport,
    FlexureCheckState,
    ShearCheckState,
    apply_shear_state,
    to_display,
    new_flexure_state,
    new_shear_state,
)
from mento.codes.aci_318_19.equations import shear as shear_eq
from mento.codes.registry import design_code
from mento.material import Concrete_ACI_318_19
from mento.precompute import CANONICAL, refresh_section_floats, section_floats
from mento.rebar import max_stirrup_spacing_ACI_318_19
from mento.units import inch, kNm, lbf
from mento.forces import Forces


if TYPE_CHECKING:
    from ..beam import RectangularBeam  # Import Beam for type checking only

# Composite units built once; `N * mm` is a pint Unit multiplication, not free.

#: The phi*Mn floor a zero-capacity face is reported with, so the DCR is a large
#: number rather than a division by zero. 0.01 kNm, in each system's own units.
_MOMENT_FLOOR = {False: 0.01e6, True: (0.01 * kNm).to(lbf * inch).magnitude}


def _initialize_variables_ACI_318_19(self: "RectangularBeam", M_y: Quantity) -> None:
    """Split the demand by face and pick the steel that is in tension.

    Which face carries tension is a matter of the sign of M_y, not of any
    clause; what the clauses do fix is what the tension steel is then used
    for. A_s_tension is the A_s of rho_w = A_s/(b_w*d) in ACI 318-19
    Table 22.5.5.1 / CIRSOC 201-25 Tabla 22.5.5.1, which R22.5.5.1 / C 22.5.5.1
    allow to be taken as the bars lying beyond two thirds of the overall depth
    from the extreme compression fibre — this reads the whole face instead,
    which is the usual reading for a rectangular beam. f_yt is the shear value
    of :func:`_calculate_f_yt_aci`.
    """
    if isinstance(self.concrete, Concrete_ACI_318_19):
        self._M_u = M_y
        if self._M_u > 0 * kNm:
            self._M_u_bot = self._M_u
            self._M_u_top = 0 * kNm
        else:
            self._M_u_bot = 0 * kNm
            self._M_u_top = self._M_u
        self.f_yt = to_display(_calculate_f_yt_aci(self), "stress", self.concrete.is_imperial)
        # Consider bottom or top tension reinforcement
        self._A_s_tension = self._A_s_bot if self._M_u >= 0 * kNm else self._A_s_top


##########################################################
# SHEAR CHECK AND DESIGN
##########################################################


def _calculate_shear_reinforcement_aci(self: "RectangularBeam", st: ShearCheckState) -> None:
    """Shear carried by the stirrups, reduced.

    V_s = A_v*f_yt*d/s — ACI 318-19 §22.5.8.5.3, Eq. (22.5.8.5.3) / CIRSOC
    201-25 §22.5.8.5.3, ec. (22.5.8.5.3). phi_v = 0.75 for shear, ACI 318-19
    Table 21.2.1(b) / CIRSOC 201-25 Tabla 21.2.1(b).
    """
    sec = section_floats(self)
    # Shear contribution of reinforcement. A_v is an area per unit length, so it
    # carries the dimension of a length.
    V_s = shear_eq.shear_strength_of_reinforcement(sec.A_v, st.f_yt, sec.d_shear)
    st.phi_V_s = self.concrete.phi_v * V_s  # Reduced shear contribution of reinforcement


def _calculate_effective_shear_area_aci(self: "RectangularBeam", st: ShearCheckState) -> None:
    """Effective shear area, longitudinal ratio and size effect factor.

    A_cv = b_w*d and rho_w = A_s/(b_w*d) are the notation Table 22.5.5.1 uses
    — ACI 318-19 Ch. 2 and Table 22.5.5.1 / CIRSOC 201-25 Cap. 2 y Tabla
    22.5.5.1. lambda_s is ACI 318-19 Eq. (22.5.5.1.3) / CIRSOC 201-25
    ec. (22.5.5.1.3), the same expression in both.
    """
    sec = section_floats(self)
    st.A_cv = sec.width * sec.d_shear  # Effective shear area
    st.rho_w = st.A_s_tension / st.A_cv  # Longitudinal reinforcement ratio
    st.lambda_s = shear_eq.size_effect_factor(sec.d_shear, is_imperial=sec.is_imperial)


def _calculate_concrete_shear_strength_aci(self: "RectangularBeam", st: ShearCheckState) -> None:
    """V_c, the shear the concrete carries on its own.

    ACI 318-19 Table 22.5.5.1 / CIRSOC 201-25 Tabla 22.5.5.1 — the same three
    rows and the same coefficients in both books — together with §22.5.5.1.1
    (V_c not greater than 0.42*lambda*sqrt(f'c)*b_w*d), §22.5.5.1.2 (the axial
    term N_u/(6*A_g) capped at 0.05*f'c) and note 2 of the table (V_c never
    negative). Which row applies is the criteria column, A_v against A_v,min
    of Table 9.6.3.4 — ACI 318-19 R22.5.5.1 / CIRSOC 201-25 C 22.5.5.1.

    ACI 318-19 §22.5.3.1 /
    CIRSOC 201-25 art. 22.5.3.1 cap sqrt(f'c) at 8.3 MPa (100 psi) for V_c, and
    §22.5.3.2 lifts the cap for beams and joists carrying the minimum web
    reinforcement of Table 9.6.3.4. Slabs retain the cap even with that minimum.
    Both the table value
    and the §22.5.5.1.1 ceiling are V_c, so both are capped.
    """
    sec = section_floats(self)
    # Axial stress influence
    st.sigma_Nu = shear_eq.axial_stress_influence(st.N_u, sec.A_x, sec.f_c)
    # Table 22.5.5.1 uses the defined minimum, even where demand waives it.
    has_min_rebar = _carries_minimum_stirrups_aci(self)

    if not has_min_rebar and not sec.is_imperial and st.A_s_tension == 0.0:
        warnings.warn(
            "Longitudinal rebar As cannot be zero if A_v is less than A_v_min.",
            UserWarning,
        )

    st.k_c_min, st.V_c = _concrete_shear_strength_aci(self, st, has_min_rebar=has_min_rebar)
    st.phi_V_c = self.concrete.phi_v * st.V_c


def _carries_minimum_stirrups_aci(self: "RectangularBeam") -> bool:
    """Whether the section holds the A_v,min of Table 9.6.3.4: the criteria column of Table 22.5.5.1."""
    return bool(section_floats(self).A_v >= _minimum_shear_reinforcement_aci(self))


def _concrete_shear_strength_aci(
    self: "RectangularBeam", st: ShearCheckState, *, has_min_rebar: bool
) -> tuple[float, float]:
    """``(k_c, V_c)`` of Table 22.5.5.1 for the row ``has_min_rebar`` selects.

    Rows (a)/(b) with A_v >= A_v,min, row (c) without; the ceiling of
    §22.5.5.1.1 and the cap on sqrt(f'c) of §22.5.3.1, lifted by §22.5.3.2
    for a beam carrying the minimum, go with the row. Split from
    :func:`_calculate_concrete_shear_strength_aci` so the same table can be
    read for a section other than the one as it is: the section limit asks
    what V_c becomes once the minimum stirrups are in.
    """
    sec = section_floats(self)
    k_c = shear_eq.concrete_shear_stress(
        sec.f_c,
        self.concrete.lambda_factor,
        st.rho_w,
        st.sigma_Nu,
        st.lambda_s,
        has_min_rebar=has_min_rebar,
        allow_high_strength=not self._stirrups_optional,
        is_imperial=sec.is_imperial,
    )
    # Maximum concrete shear strength
    V_cmax = (
        shear_eq.max_concrete_shear_stress(
            sec.f_c,
            self.concrete.lambda_factor,
            has_min_rebar=has_min_rebar,
            allow_high_strength=not self._stirrups_optional,
            is_imperial=sec.is_imperial,
        )
        * st.A_cv
    )
    return k_c, min(V_cmax, max(0.0, k_c * st.A_cv))


def _calculate_max_shear_capacity_aci(self: "RectangularBeam", st: ShearCheckState) -> None:
    """Maximum total shear capacity (V_max), and the limit of the section itself.

    V_u <= phi*(V_c + 0.66*sqrt(f'c)*b_w*d), the section-size limit of
    ACI 318-19 §22.5.1.2, Eq. (22.5.1.2) / CIRSOC 201-25 §22.5.1.2,
    ec. (22.5.1.2); 8*sqrt(f'c)*b_w*d in psi. phi_v = 0.75, ACI 318-19
    Table 21.2.1(b) / CIRSOC 201-25 Tabla 21.2.1(b).

    ``phi_V_max`` reads the V_c of the section as it is, which is what the
    report prints beside V_u. That V_c is not fixed by the dimensions alone:
    Table 22.5.5.1 moves from row (c) to rows (a)/(b) once A_v >= A_v,min,
    and §22.5.3.2 lifts the cap on sqrt(f'c) with it, so a section short of
    the minimum has a lower phi*V_max than the same section with the
    stirrups §9.6.3.1 requires of it anyway. ``section_shear_limit`` is the
    limit with those stirrups in -- the most the section can carry however
    it is reinforced, the one number that says the section has to grow --
    and coincides with ``phi_V_max`` once the section carries A_v,min. A
    20x60 with 2Ø12 and no stirrups under 320 kN was told to enlarge the
    section at phi*V_max = 309 kN when 2eØ10/10 on it carries the load at
    DCR 0.92: its limit is 354 kN.
    """
    sec = section_floats(self)
    increment = (
        shear_eq.shear_stress_capacity_increment(sec.f_c, self.concrete.lambda_factor, is_imperial=sec.is_imperial)
        * st.A_cv
    )
    st.phi_V_max = self.concrete.phi_v * (st.V_c + increment)
    st.max_shear_ok = st.V_u <= st.phi_V_max
    if _carries_minimum_stirrups_aci(self):
        V_c_reinforced = st.V_c
    else:
        _, V_c_reinforced = _concrete_shear_strength_aci(self, st, has_min_rebar=True)
    st.section_shear_limit = self.concrete.phi_v * (V_c_reinforced + increment)


def _minimum_shear_reinforcement_aci(self: "RectangularBeam") -> float:
    """Defined A_v,min/s, ACI 318-19 / CIRSOC 201-25 Table 9.6.3.4."""
    sec = section_floats(self)
    return shear_eq.min_shear_reinforcement_ratio(
        sec.f_c, _calculate_f_yt_aci(self), sec.width, is_imperial=sec.is_imperial
    )


def _calculate_A_v_min_ACI(self: "RectangularBeam", st: ShearCheckState, f_c: float) -> None:
    """A_v,min/s for the section.

    The amount is ACI 318-19 Table 9.6.3.4 / CIRSOC 201-25 Tabla 9.6.3.4 — the
    same expression in both books: the greater of 0.062*sqrt(f'c)*b_w/f_yt and
    0.35*b_w/f_yt (0.75*sqrt(f'c)*b_w/f_yt and 50*b_w/f_yt in psi). Whether it
    has to be there at all is a different clause: §9.6.3.1 for a beam,
    §7.6.3.1 for a one-way slab. See
    :func:`_check_minimum_reinforcement_requirement_aci`.
    """
    st.A_v_min = _minimum_shear_reinforcement_aci(self)


def _calculate_f_yt_aci(self: "RectangularBeam") -> float:
    """Yield strength usable for shear reinforcement, f_yt.

    ACI 318-19 §22.5.3.3 sends this to Table 20.2.2.4(a): 420 MPa (60,000 psi)
    for stirrups, ties and hoops. CIRSOC 201-25 §22.5.3.3 differs in where it
    sends the reader — §20.2.1.3 and Tablas 20.2.1-20.2.2, the characteristic
    strengths of the steels it admits — but its C 22.5.3.3 gives the same
    420 MPa, and for the same reason: keeping the diagonal cracks narrow.
    """
    sec = section_floats(self)
    return shear_eq.max_yield_strength_for_shear(sec.f_y, is_imperial=sec.is_imperial)


def _check_minimum_reinforcement_requirement_aci(self: "RectangularBeam", st: ShearCheckState) -> None:
    """Required minimum, ACI 318-19 / CIRSOC 201-25 §9.6.3.1 and §7.6.3.

    A slab or a shallow beam (Table 9.6.3.1) requires the table minimum only
    above phi*Vc. Other beam exemptions need inputs Mento does not model.
    Vc must already have been calculated from the reinforcement provided.
    """
    sec = section_floats(self)
    # Demand below which ACI 318-19 §9.6.3.1 / CIRSOC 201-25 §9.6.3.1 waive
    # shear reinforcement.
    coefficient = design_code(self.concrete).requires("min_shear_reinforcement_coefficient")(self.concrete)
    V_threshold = (
        self.concrete.phi_v
        * shear_eq.min_shear_reinforcement_threshold_stress(
            sec.f_c, self.concrete.lambda_factor, coefficient=coefficient, is_imperial=sec.is_imperial
        )
        * st.A_cv
    )

    shallow_limit = 10.0 if sec.is_imperial else 250.0
    if self._stirrups_optional or sec.height <= shallow_limit:
        V_threshold = st.phi_V_c
    if st.V_u <= V_threshold:
        st.A_v_req = 0.0
        st.A_v_min = 0.0
    else:
        _calculate_A_v_min_ACI(self, st, sec.f_c)


def _calculate_V_s_req(self: "RectangularBeam", st: ShearCheckState) -> None:
    """Stirrup area the demand asks for.

    V_n = V_c + V_s — ACI 318-19 §22.5.1.1, Eq. (22.5.1.1) / CIRSOC 201-25
    §22.5.1.1, ec. (22.5.1.1) — with phi*V_n >= V_u of ACI 318-19 §9.5.1.1(b) /
    CIRSOC 201-25 §9.5.1.1(b), inverted through V_s = A_v*f_yt*d/s of
    §22.5.8.5.3 in both codes.
    """
    sec = section_floats(self)
    # Nominal shear the stirrups must carry: phi*(Vc + Vs) >= Vu -> Vs,req = (Vu - phi*Vc)/phi.
    st.V_s_req = max((st.V_u - st.phi_V_c) / self.concrete.phi_v, 0.0)
    st.A_v_req = max(st.V_s_req / (st.f_yt * sec.d_shear), st.A_v_min)


def _calculate_total_shear_strength_aci(self: "RectangularBeam", st: ShearCheckState) -> None:
    """phi*V_n of the section as reinforced, and the demand-capacity ratio.

    phi*V_n = phi*(V_c + V_s) — ACI 318-19 §22.5.1.1 / CIRSOC 201-25 §22.5.1.1
    — checked against V_u per ACI 318-19 §9.5.1.1(b) / CIRSOC 201-25
    §9.5.1.1(b), and never above the phi*V_max of §22.5.1.2 in either code.
    """
    sec = section_floats(self)
    st.phi_V_n = self.concrete.phi_v * (st.V_c + sec.A_v * st.f_yt * sec.d_shear)
    V_d_max = min(st.phi_V_n, st.phi_V_max)
    if V_d_max == 0:
        # No stirrups AND no longitudinal steel on the tension face. V_c in
        # Table 22.5.5.1 scales with rho_w**(1/3), so it collapses to zero
        # and the section has no shear capacity at all -- which is what the
        # warning in _calculate_concrete_shear_strength_aci flags. Report an
        # infinite DCR rather than dividing by zero: check_shear must not
        # raise because a section is insufficient. Mirrors the guard in the
        # wall module and the phi*Mn floor in the flexure check.
        st.DCR = float("inf")
    else:
        st.DCR = abs(st.V_u / V_d_max)


def _calculate_rebar_spacing_aci(self: "RectangularBeam", st: ShearCheckState) -> None:
    """Maximum spacing of the stirrup legs, along the member and across it.

    ACI 318-19 Table 9.7.6.2.2 / CIRSOC 201-25 Tabla 9.7.6.2.2: d/2 and d while
    the required V_s stays at or under 0.33*sqrt(f'c)*b_w*d, d/4 and d/2 past
    it (4*sqrt(f'c)*b_w*d in psi; no lambda in the table of either code).

    CIRSOC 201-25 Tabla 9.7.6.2.2 differs in the absolute caps that go with
    those fractions: 400 mm and 200 mm, where ACI 318-19 prints 600 mm and
    300 mm (24 in. and 12 in.). They are a datum of each code's registry entry
    (``stirrup_spacing_caps``), which is what
    :func:`~mento.rebar.max_stirrup_spacing_ACI_318_19` passes down.
    """
    sec = section_floats(self)
    st.stirrup_s_w = sec.stirrup_s_w
    (
        st.stirrup_s_max_l,
        st.stirrup_s_max_w,
    ) = max_stirrup_spacing_ACI_318_19(self, st.V_s_req, st.A_cv)
    # Which row of the table that was, from the same floats, so the public
    # result and the report can say it without comparing again.
    st.V_s_threshold = shear_eq.stirrup_spacing_threshold(sec.f_c, st.A_cv, is_imperial=sec.is_imperial)
    st.spacing_halved = shear_eq.stirrup_spacing_halved(st.V_s_req, sec.f_c, st.A_cv, is_imperial=sec.is_imperial)


def _stirrup_compression_support_ACI_318_19(
    self: "RectangularBeam", d_b_stirrup: Quantity
) -> Optional[CompressionSupport]:
    """The stirrups the section owes its compression bars — ACI 318-19 §9.7.6.4 / CIRSOC 201-25 §9.7.6.4.

    §9.7.6.4.1 of both codes asks for lateral support of the longitudinal
    compression reinforcement, wherever it is required, by closed stirrups
    per §9.7.6.4.2 through §9.7.6.4.4. This reads the first two: the size of
    §9.7.6.4.2 and the spacing of §9.7.6.4.3. The geometric check of
    §9.7.6.4.4 is separate: ``RectangularBeam.compression_detailing`` reads
    the modelled first-row corner supports and the clear distance on both
    sides; second rows and crosstie anchorage remain pending.
    Which bars are
    compression reinforcement is the flexure check's to say: a combination
    that needs compression steel to carry its moment (``doubly_reinforced``),
    or whose tension steel is admissible only through it (past A_s,max,
    within A_s,max,eff: the report's "D.R."), relies on the face opposite its
    tension face (``RectangularBeam._compression_face_of``), and the last flexure check
    or design leaves those faces in ``_compression_faces``. A face with no
    bars on it is nothing to support. ``None`` when no face qualifies -- the
    ordinary singly reinforced beam, whose stirrups are for shear alone.

    ``None`` as well for a one-way slab (and a footing, which is one), whatever
    its compression steel: §9.7.6.4 is a beam provision, and ACI 318-19
    §7.7.5.1 / CIRSOC 201-25 §7.7.5 send the transverse reinforcement of a
    one-way slab to §9.7.6.2 alone. The element that may be built with no
    stirrups (``_stirrups_optional``) is the one the clause does not reach.

    Two readings, both on the conservative side, where the codes do not say:
    with bars of more than one diameter on a face, 16 d_b of §9.7.6.4.3(a)
    is read on the thinnest, which buckles first, and the stirrup size on
    the thickest, since §9.7.6.4.2 / Tabla 9.7.6.4.2 climb with the bar.
    Which size that is differs between the two codes and comes from the
    registry (``min_stirrup_for_compression_bar``).
    """
    if self._stirrups_optional:
        return None
    sec = section_floats(self)
    length = CANONICAL[sec.is_imperial]["length"]
    reinforcement = self.reinforcement
    diameters = []
    faces = []
    for face, bars in (("bot", reinforcement.bottom), ("top", reinforcement.top)):
        if face in self._compression_faces and bars.layers:
            faces.append(face)
            diameters.extend(layer.d_b for layer in bars.layers)
    if not faces:
        return None
    thinnest, thickest = min(diameters), max(diameters)
    s_max = shear_eq.max_stirrup_spacing_for_compression_support(
        thinnest.to(length).magnitude, d_b_stirrup.to(length).magnitude, min(sec.width, sec.height)
    )
    minimum_for = design_code(self.concrete).requires("min_stirrup_for_compression_bar")
    return CompressionSupport(
        s_max=to_display(s_max, "length", sec.is_imperial),
        d_b_min=minimum_for(self.concrete, thickest),
        d_b_comp_spacing=thinnest,
        d_b_comp_diameter=thickest,
        faces=tuple(faces),
    )


def _check_shear_ACI_318_19(self: "RectangularBeam", force: Forces) -> ShearCheckState:
    """Run the ACI shear check for one combination and return what it found.

    One-way shear of ACI 318-19 Ch. 22.5 with Table 9.6.3.4 and Table 9.7.6.2.2
    — and of CIRSOC 201-25, same chapter and same tables, since the dispatcher
    routes both codes here. Where the two print different numbers, the helper
    that reads them says so.

    Nothing is written to the section: the result is a value. The reporting path
    copies it back through :func:`~mento.codes.check_state.apply_shear_state`,
    which is the compatibility layer for the report tables; the values-only path
    does not, so a loop over many sections leaves every one untouched.
    """
    # No isinstance guard: the dispatcher on the element only routes ACI and
    # CIRSOC sections here, and a guard that can never fail is dead code.
    sec = section_floats(self)
    canonical = CANONICAL[sec.is_imperial]
    st = new_shear_state(self)

    # Demand, and the two material values the check needs. The moments belong to
    # the flexure check, so they are deliberately not touched here.
    st.N_u = force._N_x.to(canonical["force"]).magnitude
    st.V_u = abs(force._V_z.to(canonical["force"]).magnitude)
    st.f_yt = _calculate_f_yt_aci(self)
    st.A_s_tension = sec.A_s_bot if force._M_y >= 0 * kNm else sec.A_s_top

    # Minimum shear reinforcement calculation
    _calculate_A_v_min_ACI(self, st, sec.f_c)
    if self._stirrup_n > 0:
        # Shear reinforcement calculations
        _calculate_shear_reinforcement_aci(self, st)
    # A section with no stirrups assigned keeps the diameter the settings
    # assume, exactly as the flexure check does, so d_shear is the same number
    # in both. Dropping the layer here used to make a flexure check report
    # differently depending on whether shear had run first. Once a design
    # decides there are no stirrups it assigns a zero diameter, and both
    # checks follow it.

    # Effective shear area and longitudinal reinforcement ratio
    _calculate_effective_shear_area_aci(self, st)

    # Concrete shear strength calculation
    _calculate_concrete_shear_strength_aci(self, st)

    # Decide the required minimum using the capacity of the provided section.
    _check_minimum_reinforcement_requirement_aci(self, st)

    # Maximum total shear capacity
    _calculate_max_shear_capacity_aci(self, st)

    # Calculate required shear reinforcement
    _calculate_V_s_req(self, st)

    # Total shear strength
    _calculate_total_shear_strength_aci(self, st)

    # Rebar spacing checks
    _calculate_rebar_spacing_aci(self, st)

    return st


def _design_shear_ACI_318_19(self: "RectangularBeam", force: Forces) -> None:
    """Size the shear reinforcement for one combination.

    Unlike the check, designing is *meant* to change the section — it assigns
    the stirrups. It runs the same helpers over a state and then applies it,
    so the two paths cannot drift apart.
    """
    # Set the initial variables
    _initialize_variables_ACI_318_19(self, force.M_y)
    sec = section_floats(self)
    canonical = CANONICAL[sec.is_imperial]
    st = new_shear_state(self)
    st.N_u = force._N_x.to(canonical["force"]).magnitude
    st.V_u = abs(force._V_z.to(canonical["force"]).magnitude)
    st.f_yt = _calculate_f_yt_aci(self)
    st.A_s_tension = self._A_s_tension.to(canonical["area"]).magnitude
    # Minimum shear reinforcement calculation
    _calculate_A_v_min_ACI(self, st, sec.f_c)
    # Consider that the beam has minimum reinforcement. Designing *is* meant to
    # change the section, so the float view is rebuilt from it.
    self._A_v = to_display(0.0 if self._stirrups_optional else st.A_v_min, "per_length", sec.is_imperial)
    sec = refresh_section_floats(self)
    # Effective shear area and longitudinal reinforcement ratio
    _calculate_effective_shear_area_aci(self, st)
    # Concrete shear strength calculation
    _calculate_concrete_shear_strength_aci(self, st)
    # Maximum total shear capacity
    _calculate_max_shear_capacity_aci(self, st)
    # Check if minimum reinforcement is required
    _check_minimum_reinforcement_requirement_aci(self, st)
    # Calculate required shear reinforcement
    _calculate_V_s_req(self, st)
    # ACI 318-19 §9.6.3.1 / CIRSOC 201-25 §9.6.3.1 waive A_v,min below their
    # threshold and the check reports that faithfully, but designing does not
    # follow the waiver down: a beam is built with stirrups over its whole
    # length, so the cage asked of the designer never drops below
    # Table 9.6.3.4. That floor is this studio's criterion, not a requirement
    # of either code. Without it a lightly loaded beam
    # came back under the minimum -- 1eO6/28cm = 2.02 cm2/m on a 30x60 against
    # the 2.50 cm2/m the table asks for. Slabs keep the demand-based minimum.
    if not self._stirrups_optional:
        _calculate_A_v_min_ACI(self, st, sec.f_c)
        st.A_v_req = max(st.A_v_req, st.A_v_min)
    apply_shear_state(self, st)
    # Update spacing of longitudinal reinforcement calculation
    self._update_longitudinal_rebar_attributes()

    return None


# TODO: Delete this method since is not used

# def _calculate_phi_ACI_318_19(self: "RectangularBeam", epsilon_most_strained: float) -> float:
#     """
#     Calculates the strength reduction factor (φ) for flexural design
#     based on ACI 318-19.
#     It is used for columns; for beams, it is not required since beams
#     are always designed to be tension-controlled, with φ=0.9.

#     Parameters:
#         epsilon_most_strained (float): Strain in the most strained steel fiber.

#     Returns:
#         float: The strength reduction factor (φ), ranging from 0.65 to 0.9.

#     Description:
#         - φ = 0.65 if ε_most_strained ≤ ε_y (yield strain).
#         - φ transitions linearly from 0.65 to 0.9 if ε_y < ε_most_strained ≤ ε_y + ε_c
#         (concrete crushing strain).
#         - φ = 0.9 if ε_most_strained > ε_y + ε_c.
#     """
#     # Retrieve concrete crushing strain (ε_c)
#     epsilon_c = self.concrete.get_properties()["epsilon_c"]

#     # Calculate φ based on ε_most_strained
#     if epsilon_most_strained <= self.steel_bar.epsilon_y:
#         return 0.65
#     elif epsilon_most_strained <= self.steel_bar.epsilon_y + epsilon_c:
#         return (0.9 - 0.65) * (epsilon_most_strained - self.steel_bar.epsilon_y) / epsilon_c + 0.65
#     else:
#         return 0.9


##########################################################
# FLEXURE CHECK AND DESIGN
##########################################################


def _maximum_flexural_reinforcement_ratio_ACI_318_19(self: "RectangularBeam") -> float:
    """
    Calculates the maximum flexural reinforcement ratio (ρ_max) according to
    ACI 318-19, and to CIRSOC 201-25, which prints the same clauses.

    Returns:
        float: The maximum reinforcement ratio (ρ_max) for the section.

    Description:
        This function determines the maximum reinforcement ratio (ρ_max) that
        keeps the section ductile. A beam must be tension-controlled —
        ACI 318-19 §9.3.3.1 / CIRSOC 201-25 §9.3.3.1 — which Table 21.2.2 of
        both codes defines as ε_t >= ε_ty + 0.003. With
        the ε_cu = 0.003 of §22.2.2.1 and the strain compatibility of
        §22.2.1.2, that limit turns into ρ_max, using β1 of
        Table 22.2.2.4.3 and the 0.85*f'c block of §22.2.2.4.1 — all of them
        the same article numbers in both codes.

        CIRSOC 201-25 §9.3.3.1 differs by one symbol: it applies the rule to a
        beam with Pu <= 0.10*f'c*Ag, where ACI 318-19 writes the same limit
        strictly, Pu < 0.10*f'c*Ag. Nothing here reads it — the flexure path
        carries no axial load, so every section it sees is at Pu = 0 — but the
        clause is not word for word the same in the two books.

    """
    # Cast the concrete object to the specific ACI subclass
    concrete_aci = cast("Concrete_ACI_318_19", self.concrete)
    sec = section_floats(self)

    return flexure_eq.max_reinforcement_ratio(
        sec.f_c,
        sec.f_y,
        concrete_aci.beta_1,
        concrete_aci._epsilon_c,
        self.steel_bar.epsilon_y,
    )


def _c_neutral_axis_at_ductility_limit_ACI_318_19(self: "RectangularBeam", d: float) -> float:
    """
    Neutral axis depth at the tension-controlled boundary.

    The boundary is eps_t = eps_ty + 0.003 — ACI 318-19 Table 21.2.2 /
    CIRSOC 201-25 Tabla 21.2.2, the same table in both. With eps_cu = 0.003
    (§22.2.2.1) and strain compatibility (§22.2.1.2), c/d = eps_cu /
    (eps_cu + eps_t) gives:
        c_t = 0.003 * d / (eps_y + 0.006)

    Sections with c < c_t are ductile (tension-controlled); with c > c_t are
    over-reinforced (brittle failure).
    """
    return flexure_eq.neutral_axis_at_ductility_limit(d, self.steel_bar.epsilon_y)


def _f_s_prime_net_at_ductility_limit_ACI_318_19(self: "RectangularBeam", d: float, d_prime: float) -> float:
    """
    Effective compression-steel stress at the ductility limit, corrected for
    displaced concrete.

    Strain compatibility and the equivalent stress block of ACI 318-19
    §22.2.1.2 and §22.2.2.4.1 / CIRSOC 201-25 §22.2.1.2 and §22.2.2.4.1; the
    ductility limit itself is Table 21.2.2 of both. Deducting the displaced
    concrete is standard practice rather than a clause of either code.

    Evaluated at c_t (neutral axis at the ductility limit):
        eps_s' = (c_t - d') / c_t * eps_cu
        f_s'   = min(eps_s' * E_s, f_y)
        f_s'_net = f_s' - 0.85 * f_c

    The `- 0.85 * f_c` accounts for the concrete displaced by the bar: that
    volume was already contributing to equilibrium via the 0.85·f_c·a·b
    block, so it cannot be counted twice.
    """
    sec = section_floats(self)
    c_t = _c_neutral_axis_at_ductility_limit_ACI_318_19(self, d)
    return flexure_eq.compression_steel_net_stress(d_prime, c_t, sec.E_s, sec.f_y, sec.f_c)


def _extended_tension_cap_ACI_318_19(
    self: "RectangularBeam", A_s_max: float, A_s_comp: float, d: float, d_prime: float
) -> float:
    """Tension steel a face can carry and stay tension-controlled, given the
    compression steel on the opposite face.

    ACI 318-19 §9.3.3.1 with Table 21.2.2 / CIRSOC 201-25 §9.3.3.1 with
    Tabla 21.2.2: past A_s_max the excess tension is balanced by the
    compression steel, at the stress it reaches at the ductility limit,
        A_s_max_total = A_s_max + A_s' * f_s'_net / f_y

    It is the same boundary :func:`_nominal_moment_face_ACI_318_19` reads off
    the strain: a face carries no more than this exactly when eps_t reaches
    eps_ty + 0.003. A compression bar too close to the neutral axis to carry
    more than the concrete it displaces (f_s'_net <= 0) extends nothing.
    """
    f_s_prima_net = _f_s_prime_net_at_ductility_limit_ACI_318_19(self, d, d_prime)
    return A_s_max + A_s_comp * max(f_s_prima_net, 0.0) / section_floats(self).f_y


def _nominal_moment_face_ACI_318_19(
    self: "RectangularBeam", A_s: float, A_s_max: float, d: float, A_s_prime: float, d_prime: float
) -> tuple[float, float]:
    """``(M_n, phi)`` of one face, with ``A_s`` in tension and ``A_s_prime`` opposite.

    Up to A_s_max the section is tension-controlled on its tension steel alone
    and the closed form stands, with phi = 0.90 -- ACI 318-19 Table 21.2.2 /
    CIRSOC 201-25 Tabla 21.2.2. Past it the moment comes from strain
    compatibility with every bar at the stress its strain gives it, and phi
    from the strain the tension steel actually reaches, through the same
    table. While the compression steel keeps eps_t at eps_ty + 0.003 or more
    that is the doubly reinforced value at phi = 0.90; beyond, the section is
    no longer tension-controlled -- which §9.3.3.1 of both codes does not allow
    a beam, and the check reports -- and its strength is the one it has.

    Nothing is capped. The tension steel used to be cut back to
    A_s_max + A_s'*f_s'/f_y and kept at phi = 0.90, which credited an
    over-reinforced section with more than it carries: 213.4 kN·m for a
    25x40 section whose strain compatibility gives 196.2.
    """
    sec = section_floats(self)
    concrete_aci = cast("Concrete_ACI_318_19", self.concrete)
    if A_s <= A_s_max:
        return _determine_nominal_moment_simple_reinf_ACI_318_19(self, A_s, d), concrete_aci._phi_t
    M_n, c = flexure_eq.nominal_moment_strain_compatibility(
        A_s,
        A_s_prime,
        sec.f_y,
        sec.f_c,
        sec.width,
        d,
        d_prime,
        concrete_aci._beta_1,
        concrete_aci._epsilon_c,
        sec.E_s,
    )
    epsilon_t = flexure_eq.net_tensile_strain(c, d, concrete_aci._epsilon_c)
    phi = flexure_eq.flexure_strength_reduction_factor(epsilon_t, self.steel_bar.epsilon_y)
    return M_n, min(phi, concrete_aci._phi_t)


def _minimum_flexural_reinforcement_ratio_ACI_318_19(self: "RectangularBeam", M_u: float) -> float:
    """
    Calculates the minimum flexural reinforcement ratio of ACI 318-19 §9.6.1.2
    / CIRSOC 201-25 §9.6.1.2, based on the factored moment, M_u.

    This method determines the minimum amount of tensile reinforcement
    (in terms of a reinforcement ratio) that should be provided in a
    reinforced concrete section: the larger of 0.25*sqrt(f'c)/f_y and 1.4/f_y,
    (a) and (b) of §9.6.1.2 in both codes. If the factored
    moment M_u is zero, it means there is no flexural demand, and hence
    no minimum flexural reinforcement is required (the ratio is zero) —
    ACI 318-19 §9.6.1.1 / CIRSOC 201-25 §9.6.1.1 ask for A_s,min only where
    the analysis requires tension reinforcement.
    If M_u is not zero, the method checks the unit system (metric or imperial)
    and computes the required minimum ratio accordingly. These calculations
    depend on the compressive strength of the concrete (f_c) and the yield
    strength of the reinforcing steel (f_y).

    CIRSOC 201-25 §9.6.1.2 differs in one number: the f_y that goes into the
    formula is capped at 500 MPa, where ACI 318-19 caps it at 550 MPa
    (80,000 psi). Which of the two applies is a datum of the code's registry
    entry (``flexural_min_fy_cap``), read here and handed to the equation. The
    cap raises A_s,min, so it only bites above those values; with the ADN 420
    of ordinary Argentine practice neither is reached.

    Parameters
    ----------
    M_u : Quantity
        The factored moment for the section where the minimum flexural
        reinforcement ratio is required. The unit should be consistent with
        the chosen system (e.g., kNm in metric).

    Returns
    -------
    Quantity
        The minimum flexural reinforcement ratio (dimensionless).

    Notes
    -----
    - If M_u = 0, it indicates no moment demand, thus no minimum flexural
    reinforcement is required (resulting in a zero ratio).
    - For M_u > 0, the minimum ratio is determined using formulas involving
    the square root of f_c and the value of f_y, in accordance with
    §9.6.1.2 of both codes.
    - The result is a dimensionless ratio representing the minimum area
    of steel to the area of the concrete section.

    References
    ----------
    ACI Committee 318. "Building Code Requirements for Structural Concrete
    (ACI 318-19) and Commentary", American Concrete Institute, 2019.
    INTI-CIRSOC. "Reglamento Argentino de Estructuras de Hormigón
    CIRSOC 201-25", 2025.
    """
    if M_u == 0:
        return 0.0

    sec = section_floats(self)
    f_y_cap = design_code(self.concrete).requires("flexural_min_fy_cap")(self.concrete)
    return flexure_eq.min_reinforcement_ratio(
        sec.f_c,
        sec.f_y,
        f_y_cap.to(CANONICAL[sec.is_imperial]["stress"]).magnitude,
        is_imperial=sec.is_imperial,
    )


def _slab_minimum_applies(self: "RectangularBeam") -> bool:
    """Whether the element takes the slab minimum 0.0018*Ag rather than the beam one.

    A one-way slab is designed under Chapter 7, whose minimum is §7.6.1.1 of
    ACI 318-19 / §7.6.1 of CIRSOC 201-25, and a member on the ground reaches the
    same clause through §13.3.2.1. Only a beam takes §9.6.1.2 -- and with it the
    4/3 relief of §9.6.1.3, which relieves that clause and no other.
    """
    return self.support == "soil" or getattr(self, "mode", "beam") == "slab"


def _minimum_flexural_reinforcement_area_ACI_318_19(self: "RectangularBeam", M_u: float, d: float) -> float:
    """A_s,min on the tension face, for the kind of element this is.

    Two different clauses, and which one applies is a property of the element,
    not of the moment:

    * A beam gets the flexural minimum of ACI 318-19 §9.6.1.2 /
      CIRSOC 201-25 §9.6.1.2, ``rho_min * b * d``, sized so the cracked section
      can still carry the moment that cracked it.
    * A one-way slab is designed under Chapter 7, whose minimum is the same
      ACI 318-19 §7.6.1.1 / CIRSOC 201-25 §7.6.1 described next: 0.0018*Ag on
      the gross section. It is a flexural minimum, and it belongs to the
      tension face: R7.6.1.1 / C 7.6.1 place it "as close as practicable to
      the face of the concrete in tension due to applied loads", against the
      shrinkage and temperature steel of §24.4.3.2, which shares its ratio
      but runs perpendicular to the flexural bars (§24.4.1) and may be split
      between the faces. So a face nothing puts in tension has no minimum:
      with no moment the answer is zero on both faces, as it is for a beam,
      and not 0.0018*Ag on each of them (0.0036*Ag on a slab whose one
      combination is shear alone, and a warning on a face the design left
      bare because nothing pulled it).
    * A member supported on the ground is designed under Chapter 13:
      ACI 318-19 §13.3.2.1 / CIRSOC 201-25 §13.3.2.1 send a one-way shallow
      foundation to Chapters 7 and 9, and it is Chapter 7's slab minimum that
      answers there — ACI 318-19 §7.6.1.1 / CIRSOC 201-25 §7.6.1, which the
      Argentine code prints as an unnumbered paragraph under that heading:
      A_s,min = 0.0018*Ag in both. That is the same ratio as the shrinkage and
      temperature reinforcement of §24.4.3.2, which is the equation this branch
      calls, and it is written on the gross section ``b * h``, so ``d`` does
      not enter it. A two-way isolated footing goes to Chapter 8 instead
      (§13.3.3.1 → §8.6.1.1), which reads "0.0018*Ag, or as defined in
      8.6.1.2" -- the minimum over the two-way shear critical section of
      Eq. (8.6.1.2), not implemented here: it gets the flat 0.0018*Ag.

    Neither §9.6.1.1(b) nor §13.3.1.2 is the source of this: §9.6.1.1 is a
    single sentence with no items in either code, and §13.3.1.2 is the rule
    that the effective depth of the bottom reinforcement be at least 150 mm.

    Args:
        M_u: Factored moment on the face (N·mm, or lb·in). Only its being zero
            matters: with no moment there is no flexural minimum to satisfy,
            on a slab as on a beam.
        d: Effective depth of the tension reinforcement (mm, or in).

    Returns:
        A_s,min (mm², or in²).
    """
    sec = section_floats(self)
    if _slab_minimum_applies(self):
        if M_u == 0:
            return 0.0
        rho_st = flexure_eq.shrinkage_and_temperature_ratio()
        return rho_st * sec.width * sec.height
    return _minimum_flexural_reinforcement_ratio_ACI_318_19(self, M_u) * d * sec.width


def _geometric_minimum_ACI_318_19(self: "RectangularBeam") -> float:
    """1.8‰ of the gross section, b*h (mm², or in²): this studio's floor, not a clause.

    The design adopts it where the codes ask for no minimum and a member still
    needs its bottom steel -- no moment, or a 4/3 relief that would leave less
    -- and the check holds a bottom face with no moment to it.
    """
    sec = section_floats(self)
    return (1.8 / 1000) * sec.width * sec.height


def _calculate_flexural_reinforcement_ACI_318_19(
    self: "RectangularBeam", M_u: float, d: float, d_prima: float
) -> tuple[float, float, float, float, float, bool, bool, float]:
    """
    Calculates the flexural reinforcement for a given factored moment according to ACI 318-19,
    and to CIRSOC 201-25, which prints the same clauses: §9.6.1.1 to §9.6.1.3 for the minimum,
    §9.3.3.1 with Table 21.2.2 for the ductility cap, Ch. 22.2 for the equilibrium.

    This function computes the required reinforcement areas (minimum, maximum, and final) and
    the compression reinforcement (if required) for a given factored moment. The moment M_u must
    always be provided as a positive value. For a positive moment, pass 'd' as the effective depth
    of the tensile reinforcement and 'd_prima' as the effective depth of the compression reinforcement.
    For a negative moment, reverse the roles of 'd' and 'd_prima'.

    Parameters:
        M_u (Quantity): The factored moment (always a positive value).
        d (float): Effective depth of the tensile reinforcement.
        d_prima (float): Effective depth of the compression reinforcement.

    Returns:
        tuple: A tuple containing:
            - A_s_min (Quantity): Minimum reinforcement area required by the code.
            - A_s_max (Quantity): Maximum reinforcement area allowed by the code.
            - A_s_final (Quantity): Final reinforcement area adopted for the tensile zone.
            - A_s_comp (Quantity): Compression reinforcement area (if required).
            - c_d (float): Ratio of the calculated neutral axis depth to the effective depth (c/d).
            - A_s_bool: Boolean indicating if 4/3*A_s_calc is adopted instead of A_s_min
            - doubly: True when compression reinforcement was required. Returned
              rather than written, so a check does not mark the section.
            - A_s_calc: The steel the moment alone asks for, before any minimum
              or the 4/3 rule -- zero with no moment, and the tension steel of
              the couple when compression reinforcement is required. What an
              anchorage scaled by A_s,nec / A_s,prov has to read, since a face
              governed by its minimum carries little of the stress the minimum
              is sized for.
    """
    concrete_aci = cast("Concrete_ACI_318_19", self.concrete)
    sec = section_floats(self)
    b = sec.width
    f_c_mag = sec.f_c
    f_y_mag = sec.f_y

    # Determine minimum and maximum reinforcement areas
    A_s_min = _minimum_flexural_reinforcement_area_ACI_318_19(self, M_u, d)
    rho_max = _maximum_flexural_reinforcement_ratio_ACI_318_19(
        self,
    )
    A_s_max = rho_max * d * b

    # Calculate required reinforcement based on the nominal moment capacity
    R_n = flexure_eq.flexural_resistance_factor(M_u, concrete_aci._phi_t, b, d)
    # Verify if the value under the square root is negative
    # A negative discriminant means no tension steel alone reaches the moment,
    # however much of it: the section needs compression steel. A_s_max stands
    # in for A_s_calc until the couple below replaces it -- it used to stay,
    # and since it is not greater than A_s_max the couple never ran, so the
    # face reported A_s_max as its requirement and no compression steel.
    beyond_singly = flexure_eq.singly_reinforced_discriminant(R_n, f_c_mag) < 0
    if beyond_singly:
        A_s_calc = A_s_max
    else:
        A_s_calc = flexure_eq.tension_steel_for_moment(R_n, f_c_mag, f_y_mag, b, d)

    # Calculate the neutral axis depth based on equilibrium: 0.85 * f_c * c * beta_1 * b = A_s * f_y
    c = flexure_eq.neutral_axis_depth(A_s_calc, f_y_mag, f_c_mag, b, concrete_aci._beta_1)

    # Helper function to clean near-zero values
    def clean_zero(value: float, tolerance: float = 1e-6) -> float:
        return 0.0 if abs(value) < tolerance else value

    c_d = clean_zero(c / d)

    A_s_final = 0.0
    doubly = False

    A_s_bool = False

    # 1.8‰ of the gross section: a geometric floor of this studio's own, not a
    # requirement of either code. ACI 318-19 §9.6.1.1 / CIRSOC 201-25 §9.6.1.1
    # ask for A_s,min only where the analysis calls for tension steel, and the
    # 4/3 relief of §9.6.1.3 carries no floor in either book. On a beam it
    # only ever enters through the 4/3 rule or with no moment (Case 0); on a
    # slab it is the same number as the minimum of §7.6.1.1, and only enters
    # with no moment.
    A_s_geo_min = _geometric_minimum_ACI_318_19(self)

    if M_u == 0:
        # Case 0:
        # No flexural demand (e.g. a shear-only load combination). Neither code
        # requires flexural minimum steel here -- ACI 318-19 §9.6.1.1 /
        # CIRSOC 201-25 §9.6.1.1 for a beam, and §7.6.1.1 / §7.6.1 for a slab,
        # whose minimum belongs to the face in tension (R7.6.1.1 / C 7.6.1) --
        # so A_s_min is zero, but leaving A_s = 0 is not a buildable layout:
        # the section still needs detailing steel, and rho_w = 0 collapses V_c
        # to zero in the shear provisions (Table 22.5.5.1). Adopt the
        # geometric minimum, which is this studio's criterion. Slabs included:
        # a strip designed for shear alone is still given its 1.8‰, and the
        # check reports a zero minimum against it.
        A_s_final = A_s_geo_min
    elif _slab_minimum_applies(self):
        # Case S:
        # A_s_min above is already the 0.0018*Ag of ACI 318-19 §7.6.1.1 /
        # CIRSOC 201-25 §7.6.1, the ratio §24.4.3.2 writes for shrinkage and
        # temperature, on the gross section -- the minimum of a one-way slab,
        # and the one Chapter 13 sends a member on the ground to (§13.3.2.1 in
        # both). The 4/3 relief of
        # §9.6.1.3 belongs to the clause it relieves, §9.6.1.2, which is a
        # beam clause and not the one governing here, so the minimum stands as
        # written.
        A_s_final = max(A_s_calc, A_s_min)
    elif A_s_calc >= A_s_min:
        # Case 1:
        # The required steel already exceeds the §9.6.1.2 minimum.
        # Do not apply the 4/3 rule, as it would increase steel unnecessarily.
        A_s_final = A_s_calc
    else:
        # Case 2:
        # The required steel is less than the §9.6.1.2 minimum, so the relief
        # of ACI 318-19 §9.6.1.3 / CIRSOC 201-25 §9.6.1.3 is on the table:
        # As one third greater than the analysis asks for excuses §9.6.1.1 and
        # §9.6.1.2. Evaluate whether 4/3 * A_s_calc is less steel than A_s_min.
        A_s_4_3 = (4 * A_s_calc) / 3

        if A_s_4_3 < A_s_min:
            # The 4/3 rule is potentially beneficial → check the geometric minimum
            if A_s_4_3 >= A_s_geo_min:
                # 4/3 * A_s_calc satisfies the geometric minimum → adopt it
                A_s_final = A_s_4_3
                A_s_bool = True
            else:
                # 4/3 * A_s_calc is lower than 1.8‰ of (b·h) → enforce the
                # geometric minimum. Neither code asks for this: §9.6.1.3 puts
                # no floor under the 4/3 rule.
                A_s_final = A_s_geo_min
                # A_s_bool remains False (4/3 rule not effectively used)
        else:
            # 4/3 * A_s_calc is not smaller than A_s_min → use the §9.6.1.2 minimum
            A_s_final = A_s_min

    A_s_final = clean_zero(A_s_final)

    # Determine if compression reinforcement is required
    if A_s_final <= A_s_max and not beyond_singly:
        A_s_comp = 0.0
    else:
        doubly = True
        # Beyond A_s_max the moment is carried as a couple, at the ductility
        # limit of ACI 318-19 Table 21.2.2 / CIRSOC 201-25 Tabla 21.2.2 with
        # the equilibrium of Ch. 22.2 in both. Same limit as A_s_max above:
        # with the fixed eps_c = 0.003 of §22.2.2.1, eps_y + 2*eps_c is exactly
        # the eps_y + 0.006 this branch used to spell out on its own, so one
        # function covers both.
        rho = flexure_eq.max_reinforcement_ratio(
            f_c_mag, f_y_mag, concrete_aci._beta_1, concrete_aci._epsilon_c, self.steel_bar.epsilon_y
        )
        # Whitney block depth at the ductility limit (exact, not approximated):
        #     a_max = beta_1 * c_t
        # This replaces the textbook shortcut d - 0.59 * rho * fy * d / fc,
        # which relies on 0.59 ≈ 1/1.7 and drops ~0.3% of precision.
        c_t = _c_neutral_axis_at_ductility_limit_ACI_318_19(self, d)
        c_d = clean_zero(c_t / d)
        a_max = concrete_aci._beta_1 * c_t
        M_n_t = rho * f_y_mag * (d - a_max / 2) * b * d
        M_n_prima = M_u / concrete_aci._phi_t - M_n_t
        f_s_prima_net = _f_s_prime_net_at_ductility_limit_ACI_318_19(self, d, d_prima)
        if f_s_prima_net > 0:
            A_s_comp = M_n_prima / (f_s_prima_net * (d - d_prima))
            A_s_final = rho * b * d + A_s_comp * f_s_prima_net / f_y_mag
        else:
            # The compression bar sits too close to the neutral axis to carry
            # more than the concrete it displaces: no amount of it extends the
            # section, and the division above turned negative (-39 cm² on a
            # shallow section). The most the face can take and stay
            # tension-controlled is A_s_max, and that is what it is asked for;
            # the moment it cannot reach is the check's to report.
            A_s_comp = 0.0
            A_s_final = rho * b * d
        # Beyond the ductility limit the moment is carried as a couple, and the
        # tension steel of that couple is what the moment asks for.
        A_s_calc = A_s_final

    return A_s_min, A_s_max, A_s_final, A_s_comp, c_d, A_s_bool, doubly, clean_zero(A_s_calc)


def _determine_nominal_moment_simple_reinf_ACI_318_19(self: "RectangularBeam", A_s: float, d: float) -> float:
    """
    Determines the nominal moment for a simply reinforced section according to ACI 318-19,
    and to CIRSOC 201-25, which prints the same clauses.

    This formula is used ONLY when the provided reinforcement area (A_s) is less than or equal to A_s_max.

    The equivalent rectangular stress block of ACI 318-19 §22.2.2.4.1 and Table 22.2.2.4.3 /
    CIRSOC 201-25 §22.2.2.4.1 and Tabla 22.2.2.4.3, with the strength requirement of §9.5.1.1(a)
    in both, the steel taken at f_y once it yields (§20.2.2.1 in both) and the tensile strength
    of the concrete neglected (§22.2.2.2 in both).

    The equilibrium of forces is assumed (compression equals tension):
        0.85 * f_c * a * b = A_s * f_y
    which implies:
        a = (A_s * f_y) / (0.85 * f_c * b)

    Parameters:
        A_s (Quantity): The area of reinforcement.
        d (Quantity): The effective depth of the section.

    Returns:
        Quantity: The nominal moment (M_n) calculated as A_s * f_y * (d - a/2).
    """
    sec = section_floats(self)
    return flexure_eq.nominal_moment_singly_reinforced(A_s, sec.f_y, sec.f_c, sec.width, d)


def _determine_nominal_moment_double_reinf_ACI_318_19(
    self: "RectangularBeam",
    A_s: float,
    d: float,
    d_prime: float,
    A_s_prime: float,
) -> float:
    """
    Determines the nominal moment for a doubly reinforced beam section according to ACI 318-19,
    and to CIRSOC 201-25, which prints the same clauses.

    This method is used only when the beam has reinforcement exceeding the maximum limit
    and includes compression reinforcement.

    Same stress block and strain compatibility as the singly reinforced case — ACI 318-19
    §22.2.1.2, §22.2.2.4.1 and Table 22.2.2.4.3 / CIRSOC 201-25 §22.2.1.2, §22.2.2.4.1 and
    Tabla 22.2.2.4.3 — with the compression steel taken at whatever stress its strain gives it,
    never above f_y (§20.2.2.1 in both).

    Equilibrium is assumed (Compression = Tension):
        C_total = Concrete compression (Cc) + Compression reinforcement (Cs)
        Tension (T) = A_s * f_y

    Initially, it is assumed that the compression reinforcement yields (i.e., f_s_prime = f_y),
    so the equilibrium equation becomes:
        0.85 * f_c * a * b + A_s_prime * f_y = A_s * f_y

    Parameters:
        A_s (Quantity): Area of the tensile reinforcement.
        d (Quantity): Effective depth of the beam section.
        d_prime (Quantity): Effective depth (cover) to the compression reinforcement.
        A_s_prime (Quantity): Area of the compression reinforcement.

    Returns:
        Quantity: The nominal moment (M_n) of the doubly reinforced section.
    """
    concrete_aci = cast("Concrete_ACI_318_19", self.concrete)
    sec = section_floats(self)

    return flexure_eq.nominal_moment_doubly_reinforced(
        A_s,
        A_s_prime,
        sec.f_y,
        sec.f_c,
        sec.width,
        d,
        d_prime,
        concrete_aci._beta_1,
        concrete_aci._epsilon_c,
        self.steel_bar._epsilon_y,
        sec.E_s,
    )


def _determine_nominal_moment_ACI_318_19(self: "RectangularBeam", st: FlexureCheckState, force: Forces) -> None:
    """
    Determines the nominal moment for a given section with both top and bottom reinforcement,
    calculating the nominal moment for both positive and negative moment scenarios.

    For positive moments, the tension is in the bottom reinforcement.
    For negative moments, the tension is in the top reinforcement.

    Flexural strength of ACI 318-19 Ch. 22.2 / CIRSOC 201-25 Cap. 22.2, reduced by the
    phi of ACI 318-19 Table 21.2.2 / CIRSOC 201-25 Tabla 21.2.2 for the strain the
    tension steel reaches: 0.90 while the section is tension-controlled, less past
    it (see :func:`_nominal_moment_face_ACI_318_19`). Past it the section also
    misses §9.3.3.1 of both codes, which the check reports against
    ``A_s_max_eff``, set here per face.

    Parameters:
        force (Forces): An object containing the forces acting on the section, including the moment M_y.

    Returns:
        None
    """

    sec = section_floats(self)
    # Calculate minimum and maximum reinforcement ratios
    M_u = force._M_y.magnitude
    rho_max = _maximum_flexural_reinforcement_ratio_ACI_318_19(self)

    # For positive moments (tension in the bottom), set minimum reinforcement
    # accordingly. The minimum is asked for as an area rather than a ratio: the
    # clause that applies to a member on the ground is written on the gross
    # section, so there is no single ratio both cases can be expressed in.
    tension_at_bottom = force._M_y > 0 * kNm

    # Calculate minimum and maximum bottom reinforcement areas
    st.A_s_min_bot = _minimum_flexural_reinforcement_area_ACI_318_19(self, M_u, sec.d_bot) if tension_at_bottom else 0.0
    st.A_s_max_bot = rho_max * sec.d_bot * sec.width

    # Positive moment: the bottom steel in tension, the top steel opposite.
    M_n_positive, phi_positive = _nominal_moment_face_ACI_318_19(
        self, sec.A_s_bot, st.A_s_max_bot, sec.d_bot, sec.A_s_top, sec.c_mec_top
    )

    # Determine capacity for negative moment (tension at the top)
    st.A_s_min_top = 0.0 if tension_at_bottom else _minimum_flexural_reinforcement_area_ACI_318_19(self, M_u, sec.d_top)
    st.A_s_max_top = rho_max * sec.d_top * sec.width

    # Negative moment: the mirror, with no top steel carrying nothing.
    if sec.A_s_top == 0:
        M_n_negative, phi_negative = 0.0, 0.0
    else:
        M_n_negative, phi_negative = _nominal_moment_face_ACI_318_19(
            self, sec.A_s_top, st.A_s_max_top, sec.d_top, sec.A_s_bot, sec.c_mec_bot
        )

    # The tension steel each face can carry and stay tension-controlled, with
    # the steel of the opposite face as it is: the limit §9.3.3.1 holds a beam
    # to once it has compression steel. A section property, read the same
    # under every combination.
    st.A_s_max_eff_bot = _extended_tension_cap_ACI_318_19(self, st.A_s_max_bot, sec.A_s_top, sec.d_bot, sec.c_mec_top)
    st.A_s_max_eff_top = _extended_tension_cap_ACI_318_19(self, st.A_s_max_top, sec.A_s_bot, sec.d_top, sec.c_mec_bot)

    st.phi_M_n_bot = phi_positive * M_n_positive
    st.phi_M_n_top = phi_negative * M_n_negative

    return None


def _effective_minimum_ACI_318_19(self: "RectangularBeam", A_s_min: float, A_s_calc: float) -> float:
    """The minimum steel a face has to carry, relief included.

    ACI 318-19 §9.6.1.3 / CIRSOC 201-25 §9.6.1.3 waive §9.6.1.1 and §9.6.1.2
    when the steel provided is at least one third more than the analysis asks
    for, so a face meets its minimum with A_s,min or with 4/3 of A_s_calc,
    whichever is less. What is compared against this is the steel provided,
    which is why the flag of the requirement -- A_s_bool, "4/3 was adopted as
    the area to detail" -- cannot stand in for it: a layout checked by hand can
    fall short of 4/3 A_s_calc while the flag is set.

    A one-way slab, and a member on the ground through §13.3.2.1, take the
    minimum of §7.6.1.1, which §9.6.1.3 does not relieve, so there the minimum
    stands as written.
    The 1.8‰ floor the design adds is this studio's criterion, not a limit of
    either code, and is not part of it.
    """
    if _slab_minimum_applies(self):
        return A_s_min
    return min(A_s_min, 4 * A_s_calc / 3)


def _check_flexure_ACI_318_19(self: "RectangularBeam", force: Forces) -> FlexureCheckState:
    """
    Checks the flexural capacity of the section according to ACI 318-19 guidelines,
    and to CIRSOC 201-25, which the dispatcher routes here as well.

    The criterion is phi*M_n >= M_u — ACI 318-19 §9.5.1.1(a) / CIRSOC 201-25
    §9.5.1.1(a) — reported as the DCR M_u / (phi*M_n) on each face.

    Computes the nominal moments for both faces, the required reinforcement
    areas and the design capacity ratios, and returns them. Nothing is written
    to the section; only the reporting path copies the result back, which is
    what lets a caller check many sections without per-call cleanup.

    Parameters:
        force (Forces): The force acting on the section, which must include a single moment value.
    """
    st = new_flexure_state(self)

    # The demand, split by face, and the two material values the check needs.
    sec = section_floats(self)
    moment_unit = CANONICAL[sec.is_imperial]["moment"]
    st.M_u = force._M_y.to(moment_unit).magnitude
    if st.M_u > 0:
        st.M_u_bot = st.M_u
        st.M_u_top = 0.0
    else:
        st.M_u_bot = 0.0
        st.M_u_top = st.M_u
    st.f_yt = _calculate_f_yt_aci(self)
    st.A_s_tension = sec.A_s_bot if st.M_u >= 0 else sec.A_s_top

    # Calculate the nominal moments for both top and bottom reinforcement.
    _determine_nominal_moment_ACI_318_19(self, st, force)

    if st.M_u >= 0:
        # For positive moments, calculate the reinforcement requirements for the bottom tension side.
        (
            st.A_s_min_bot,
            st.A_s_max_bot,
            st.A_s_req_bot,
            st.A_s_req_top,
            st.c_d_bot,
            st.A_s_bool_bot,
            st.doubly_reinforced,
            st.A_s_calc_bot,
        ) = _calculate_flexural_reinforcement_ACI_318_19(
            self,
            st.M_u_bot,
            sec.d_bot,
            sec.c_mec_top,
        )
        st.c_d_top = 0
        # Calculate the design capacity ratio for the bottom side.
        if st.phi_M_n_bot == 0:
            st.phi_M_n_bot = _MOMENT_FLOOR[sec.is_imperial]
        st.DCR_bot = st.M_u_bot / st.phi_M_n_bot
        st.DCR_top = 0
    else:
        # For negative moments, calculate the reinforcement requirements for the top tension side.
        (
            st.A_s_min_top,
            st.A_s_max_top,
            st.A_s_req_top,
            st.A_s_req_bot,
            st.c_d_top,
            st.A_s_bool_top,
            st.doubly_reinforced,
            st.A_s_calc_top,
        ) = _calculate_flexural_reinforcement_ACI_318_19(
            self,
            abs(st.M_u_top),
            sec.d_top,
            sec.c_mec_bot,
        )
        st.c_d_bot = 0
        # Calculate the design capacity ratio for the top side.
        if st.phi_M_n_top == 0:
            st.phi_M_n_top = _MOMENT_FLOOR[sec.is_imperial]
        st.DCR_top = -st.M_u_top / st.phi_M_n_top
        st.DCR_bot = 0

    st.A_s_min_eff_bot = _effective_minimum_ACI_318_19(self, st.A_s_min_bot, st.A_s_calc_bot)
    st.A_s_min_eff_top = _effective_minimum_ACI_318_19(self, st.A_s_min_top, st.A_s_calc_top)
    if st.M_u == 0:
        # No moment: neither code asks for a flexural minimum, but a member
        # always carries its bottom steel, and the design gives it the 1.8‰
        # of the gross section (Case 0 of _calculate_flexural_reinforcement).
        # The check holds the bottom to the same floor, with no 4/3 relief --
        # there is no A_s_calc to relieve it against -- so a bare bottom is
        # warned; the top, which nothing pulls, keeps no minimum.
        st.A_s_min_bot = st.A_s_min_eff_bot = _geometric_minimum_ACI_318_19(self)

    # Determine the maximum detailing cover dimensions for top and bottom.
    length_unit = CANONICAL[sec.is_imperial]["length"]
    st.d_b_max_top = max(self._d_b1_t, self._d_b2_t, self._d_b3_t, self._d_b4_t).to(length_unit).magnitude
    st.d_b_max_bot = max(self._d_b1_b, self._d_b2_b, self._d_b3_b, self._d_b4_b).to(length_unit).magnitude

    # Calculate the longitudinal reinforcement ratios for both sides.
    # rho = A_s / (b*d): ACI 318-19 Ch. 2, 2.2 ("ratio of A_s to bd") and
    # CIRSOC 201-25 Cap. 2 ("cuantia de la armadura traccionada, no tesa;
    # relacion entre A_s y el area b.d") define it identically. Each face takes
    # its OWN steel against its OWN effective depth: the top ratio used to be
    # fed with A_s_bot, so the top flexure table printed a ratio that did not
    # belong to the A_s it was printed next to.
    st.rho_l_bot = sec.A_s_bot / (sec.d_bot * sec.width)
    st.rho_l_top = sec.A_s_top / (sec.d_top * sec.width)

    return st


def _flexure_capacity_ACI_318_19(self: "RectangularBeam", face: str, M_demand: Quantity) -> Quantity:
    """phi*Mn of the layout currently applied to the section, on `face`.

    phi = 0.90, the tension-controlled value of ACI 318-19 Table 21.2.2 /
    CIRSOC 201-25 Tabla 21.2.2.

    Recomputed rather than read from cached state so that the centroid of the
    layout just applied is taken into account.
    """
    M_abs = abs(M_demand)
    probe_force = Forces(M_y=(M_abs if face == "bot" else -M_abs))
    st = new_flexure_state(self)
    _determine_nominal_moment_ACI_318_19(self, st, probe_force)
    # The design wants the capacity on the beam too, so the probe's moments are
    # applied; a check never comes through here. Back in pint, because the
    # design path and the report tables both read these.
    imperial = self.concrete.is_imperial
    self._phi_M_n_bot = to_display(st.phi_M_n_bot, "moment", imperial)
    self._phi_M_n_top = to_display(st.phi_M_n_top, "moment", imperial)
    self._A_s_min_bot = to_display(st.A_s_min_bot, "area", imperial)
    self._A_s_max_bot = to_display(st.A_s_max_bot, "area", imperial)
    return self._phi_M_n_bot if face == "bot" else self._phi_M_n_top


def _flexure_ductile_ACI_318_19(self: "RectangularBeam", face: str) -> bool:
    """Is ``face``, in tension, tension-controlled with the layout on the section?

    ACI 318-19 §9.3.3.1 / CIRSOC 201-25 §9.3.3.1: a beam has to be
    tension-controlled, eps_t >= eps_ty + 0.003 (Table 21.2.2 in both). With the
    compression steel the other face carries, that is the face's tension steel
    against ``A_s_max + A_s'*f_s'/f_y`` -- the limit the check reports as
    ``A_s_max_eff``. A design that reached the moment past it would hand back
    a section the check marks as not complying.
    """
    sec = section_floats(self)
    rho_max = _maximum_flexural_reinforcement_ratio_ACI_318_19(self)
    if face == "bot":
        A_s, d, A_s_prime, d_prime = sec.A_s_bot, sec.d_bot, sec.A_s_top, sec.c_mec_top
    else:
        A_s, d, A_s_prime, d_prime = sec.A_s_top, sec.d_top, sec.A_s_bot, sec.c_mec_bot
    limit = _extended_tension_cap_ACI_318_19(self, rho_max * d * sec.width, A_s_prime, d, d_prime)
    return A_s <= limit * (1 + 1e-9)


def _required_areas_ACI_318_19(
    self: "RectangularBeam", face: str, M: Quantity, d: Quantity, d_prime: Quantity
) -> _FaceDemand:
    """Steel required by ACI 318-19 — or CIRSOC 201-25 — on `face` for the moment `M`.

    The code-specific extras that do not belong in `_FaceDemand` (the c/d ratio
    and the flag for the 4/3 rule of §9.6.1.3, the same article in both codes)
    are stored on the beam for the results tables.
    """
    sec = section_floats(self)
    imperial = sec.is_imperial
    canonical = CANONICAL[imperial]
    (
        A_s_min,
        A_s_max,
        A_s_tension,
        A_s_compression,
        c_d,
        A_s_bool,
        doubly,
        _A_s_calc,  # the design sizes bars, so it wants the minimum folded in
    ) = _calculate_flexural_reinforcement_ACI_318_19(
        self,
        M.to(canonical["moment"]).magnitude,
        d.to(canonical["length"]).magnitude,
        d_prime.to(canonical["length"]).magnitude,
    )
    # The design path speaks pint on both sides of this, so the areas come back
    # wrapped; only the calculation between them is in floats.
    A_s_min, A_s_max, A_s_tension, A_s_compression = (
        to_display(A_s_min, "area", imperial),
        to_display(A_s_max, "area", imperial),
        to_display(A_s_tension, "area", imperial),
        to_display(A_s_compression, "area", imperial),
    )
    self._doubly_reinforced = self._doubly_reinforced or doubly
    if face == "bot":
        self._A_s_min_bot, self._A_s_max_bot = A_s_min, A_s_max
        self._c_d_bot, self._A_s_bool_bot = c_d, A_s_bool
    else:
        self._A_s_min_top, self._A_s_max_top = A_s_min, A_s_max
        self._c_d_top, self._A_s_bool_top = c_d, A_s_bool
    # Past A_s_max each unit of tension steel needs f_y / f_s' of compression
    # steel to keep the section tension-controlled. A compression bar too close
    # to the neutral axis to carry stress extends nothing.
    f_s_prime_net = _f_s_prime_net_at_ductility_limit_ACI_318_19(
        self, d.to(canonical["length"]).magnitude, d_prime.to(canonical["length"]).magnitude
    )
    ratio = sec.f_y / f_s_prime_net if f_s_prime_net > 0 else None
    return _FaceDemand(A_s_min, A_s_max, A_s_tension, A_s_compression, ratio)


def _design_flexure_ACI_318_19(self: "RectangularBeam", max_M_y_bot: Quantity, max_M_y_top: Quantity) -> None:
    """Design the longitudinal reinforcement of a beam per ACI 318-19 — or CIRSOC 201-25.

    Thin wrapper: everything that is not an ACI equation lives in
    ``mento.codes.flexure_design``. The two codes share every clause this path
    reads, so the same wrapper serves both.
    """

    def _required(face: str, M: Quantity, d: Quantity, d_prime: Quantity) -> _FaceDemand:
        return _required_areas_ACI_318_19(self, face, M, d, d_prime)

    def _capacity(face: str, M: Quantity) -> Quantity:
        return _flexure_capacity_ACI_318_19(self, face, M)

    def _admissible(face: str) -> bool:
        return _flexure_ductile_ACI_318_19(self, face)

    _run_flexure_design(self, max_M_y_bot, max_M_y_top, _required, _capacity, _admissible)


##########################################################
# RESULTS
##########################################################
