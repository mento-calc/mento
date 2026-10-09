from __future__ import annotations

from typing import TYPE_CHECKING

from mento.units import Quantity

from mento.codes.aci_318_19.equations import shear as shear_eq
from mento.codes.aci_318_19.equations import wall as wall_eq
from mento.codes.check_state import WallShearCheckState, apply_wall_shear_state, new_wall_shear_state
from mento.codes.registry import design_code
from mento.codes.wall_mesh_design import select_wall_mesh
from mento.material import Concrete_ACI_318_19
from mento.units import MPa, kN, kip, mm, psi, inch, dimensionless
from mento.forces import Forces

if TYPE_CHECKING:
    from mento.shear_wall import ShearWall


##########################################################
# WALL MESH BAR CATALOGUE
##########################################################

# Standard reinforcing bar diameters for wall distributed mesh design.
# Neither code fixes a minimum bar diameter for a wall mesh: ACI 318-19 §11.6 /
# CIRSOC 201-25 §11.6 limit the ratios and ACI 318-19 §11.7 / CIRSOC 201-25 §11.7
# limit the spacing, nothing more. Every catalogue below is therefore a mento
# design criterion, not a code requirement.
# ACI 318-19 uses the same catalogue for both mesh directions. In metric these
# are nominal metric sizes, not the ASTM bars of ACI 318-19 Appendix B
# (No. 10 = 9.5 mm, No. 13 = 12.7 mm, No. 16 = 15.9 mm...).
_ACI_WALL_BARS_METRIC = [10 * mm, 12 * mm, 16 * mm, 20 * mm, 25 * mm]
_ACI_WALL_BARS_IMPERIAL = [
    0.375 * inch,  # #3
    0.5 * inch,  # #4
    0.625 * inch,  # #5
    0.75 * inch,  # #6
    0.875 * inch,  # #7
    1.0 * inch,  # #8
]
# CIRSOC 201-25 (metric only) reuses the ACI shear provisions and takes its
# sizes from CIRSOC 201-25 Table 20.2.1 (ADN 420: 6-8-10-12-16-20-25-32-40 mm).
# The Ø6 mm floor for the transverse mesh and the Ø10 mm floor for the vertical
# one are mento criteria — CIRSOC 201-25 Chapter 11 requires neither.
_CIRSOC_WALL_BARS_TRANSVERSE = [6 * mm, 8 * mm, 10 * mm, 12 * mm, 16 * mm, 20 * mm, 25 * mm]
_CIRSOC_WALL_BARS_VERTICAL = [10 * mm, 12 * mm, 16 * mm, 20 * mm, 25 * mm]

# Crack-control cap — the selector (mento.codes.wall_mesh_design) scores bars
# at/below this first; larger bars are used only as a fallback when nothing
# capped can meet the demand.
# A mento criterion as well: neither ACI 318-19 §11.7 nor CIRSOC 201-25 §11.7
# caps the bar diameter of a wall mesh.
_WALL_BAR_CAP_METRIC = 12 * mm
_WALL_BAR_CAP_IMPERIAL = 0.5 * inch  # #4


##########################################################
# HELPERS
##########################################################


def _wall_units(self: "ShearWall") -> tuple[Quantity, Quantity]:
    """(stress, length) units for the wall's unit system."""
    return (psi, inch) if self.concrete.is_imperial else (MPa, mm)


def _wall_force_unit(self: "ShearWall") -> Quantity:
    """The force unit of the wall's unit system: kip, or kN.

    Every force the check leaves on the state is converted to it, so the
    public results and the compatibility attributes read in the section's
    own system -- the promise of :mod:`mento.wall_results`, and what the
    beam's ``ShearCheck`` does. ``new_wall_shear_state`` zeroes the state in
    the same unit.
    """
    return kip if self.concrete.is_imperial else kN


def _calculate_f_yt_wall(self: "ShearWall") -> Quantity:
    """Cap fyt at 420 MPa (metric) / 60 ksi (imperial) for the ρt·fyt term of Eq. (11.5.4.3).

    Neither code caps fyt for the distributed mesh of an ordinary wall in
    Chapter 11 itself; both send the steel properties to Chapter 20
    (ACI 318-19 §11.2.1.2 / CIRSOC 201-25 §11.2.1.2), and mento borrows the
    beam's shear cap from there.

    ACI 318-19 §20.2.2.4, Table 20.2.2.4(a), usage "Shear", application
    "Stirrups, ties, hoops": 420 MPa (60,000 psi) for deformed bars, 550 MPa
    for welded deformed wire reinforcement. The 690 MPa row of that usage is
    for special structural walls under Chapter 18, which are out of scope.

    CIRSOC 201-25 differs: it prints no cap table. §20.2.1.3 makes the design
    value the characteristic yield of Tables 20.2.1 and 20.2.2 — 420 MPa for
    ADN 420 bars, but 500 MPa for the ATR 500 N wire and AM 500 N welded mesh
    a wall mesh may be built from, and §20.2.1.4 admits 500 MPa deformed bars
    once the matching IRAM standard is written.

    420 MPa is therefore a deliberate criterion rather than a clause, and it
    is conservative under both codes for a welded-wire mesh. It follows the
    reasoning of ACI R20.2.2.4 / CIRSOC C 22.5.3.3: capping fy and fyt at
    420 MPa is what keeps the diagonal crack widths under control. Lifting it
    would have to arrive as a registry datum, never as a design_code
    comparison.
    """
    stress_unit, _ = _wall_units(self)
    return (
        shear_eq.max_yield_strength_for_shear(
            self.steel_bar.f_y.to(stress_unit).magnitude, is_imperial=self.concrete.is_imperial
        )
        * stress_unit
    )


def _calculate_alpha_c(self: "ShearWall", st: WallShearCheckState) -> float:
    """α_c from hw/lw — ACI 318-19 §11.5.4.3 / CIRSOC 201-25 §11.5.4.3.

    α_c is defined under Eq. (11.5.4.3) itself, not in a clause of its own:
    0.25 for hw/lw ≤ 1.5, 0.17 for hw/lw ≥ 2.0, linear in between. Those are
    the SI numbers that CIRSOC 201-25 and ACI 318-19 (SI) both print; ACI
    318-19 (in-lb) prints 3 and 2 for the same ratios, which is what
    ``wall_eq.alpha_c`` returns when ``is_imperial``.

    §11.5.4.4 replaces that α_c when the wall carries net axial tension:

        ACI 318-19 (SI)     α_c = 0.17(1 + Nu/(3.45·Ag)) ≥ 0.0
        ACI 318-19 (in-lb)  α_c = 2   (1 + Nu/(500 ·Ag)) ≥ 0.0
        CIRSOC 201-25       α_c = 0.17(1 + Nu/(3.5 ·Ag)) ≥ 0.0

    with Nu negative in tension. The divisor arrives from the code registry.

    Stores hw/lw as a side effect on st.hw_lw.
    """
    hw_lw = (self.height / self.length).to("").magnitude
    st.hw_lw = hw_lw
    if st.N_u.magnitude < 0:
        stress, length = _wall_units(self)
        divisor = design_code(self.concrete).requires("wall_axial_tension_divisor")(self.concrete)
        return wall_eq.alpha_c_in_tension(
            st.N_u.to(stress * length**2).magnitude,
            st.Acv.to(length**2).magnitude,
            divisor.to(stress).magnitude,
            is_imperial=self.concrete.is_imperial,
        )
    return wall_eq.alpha_c(hw_lw, is_imperial=self.concrete.is_imperial)


def _calculate_wall_Acv(self: "ShearWall", st: WallShearCheckState) -> None:
    """Acv = lw × t — ACI 318-19 Ch. 2 (notation) / CIRSOC 201-25 Ch. 2.

    The gross concrete area bounded by the web thickness and the length of the
    section in the direction of the shear considered — h·lw, not h·d.

    That is why the §11.5.4.2 cap reads 0.66 and not 0.83: both commentaries
    say the coefficient was *reduced* precisely because the effective shear
    area was enlarged from h·d to h·lw. Taking Acv as h·d with the 0.66 of the
    current codes would therefore be wrong twice over. The two commentaries
    differ only in the edition they compare against — ACI R11.5.4.2 against
    ACI 318M-14, CIRSOC C 11.5.4.2 against CIRSOC 201-2005.
    """
    st.Acv = self.length * self.thickness


def _calculate_wall_shear_strength(
    self: "ShearWall",
    st: WallShearCheckState,
    concrete: Concrete_ACI_318_19,
) -> None:
    """
    ACI 318-19 §11.5.4.3 / CIRSOC 201-25 §11.5.4.3, Eq. (11.5.4.3):
        Vc      = α_c × λ × √f'c × Acv
        Vs      = ρt × fyt × Acv
        Vn      = Vc + Vs

    ACI 318-19 §11.5.4.2 / CIRSOC 201-25 §11.5.4.2 — the diagonal-compression
    cap, printed without λ in both codes:
        Vn,max  = 0.66 × √f'c × Acv  (metric)
                  8    × √f'c × Acv  (imperial)
    ``wall_eq.max_shear_stress`` still takes λ; no numeric effect while λ = 1,
    but the factor is not in the clause and the signature is due a fix.

    φ = 0.75 per ACI 318-19 Table 21.2.1(b) / CIRSOC 201-25 Table 21.2.1(b).

    The forces are stored in the wall's own force unit (kip, or kN): the
    public results promise the section's unit system.
    """
    lam = concrete.lambda_factor
    phi_v = concrete.phi_v
    is_imperial = concrete.is_imperial
    stress_unit, _ = _wall_units(self)
    force_unit = _wall_force_unit(self)
    f_c_mag = concrete.f_c.to(stress_unit).magnitude

    Vc = wall_eq.concrete_shear_stress(f_c_mag, st.alpha_c, lam) * stress_unit * st.Acv
    Vn_max = wall_eq.max_shear_stress(f_c_mag, lam, is_imperial=is_imperial) * stress_unit * st.Acv
    Vs = (
        wall_eq.reinforcement_shear_stress(float(self._rho_t), st.f_yt_wall.to(stress_unit).magnitude)
        * stress_unit
        * st.Acv
    )
    Vn = Vc + Vs

    st.V_c_wall = Vc.to(force_unit)  # type:ignore
    st.V_s_wall = Vs.to(force_unit)  # type:ignore
    st.V_n_wall = Vn.to(force_unit)  # type:ignore
    st.V_n_max = Vn_max.to(force_unit)  # type:ignore
    st.phi_V_n_wall = (phi_v * min(Vn, Vn_max)).to(force_unit)  # type:ignore
    st.phi_V_n_max_wall = (phi_v * Vn_max).to(force_unit)  # type:ignore


def _calculate_rho_min_wall(self: "ShearWall", st: WallShearCheckState) -> None:
    """
    ACI 318-19 §11.6.2 / CIRSOC 201-25 §11.6.2:
        ρt_min = 0.0025 (horizontal, always)                  — §11.6.2(b)
        ρl_min = max(0.0025, min(ρl_eq, ρt,req))  (vertical)  — §11.6.2(a)

    Eq. (11.6.2), the same in both codes, with the ρt the wall PROVIDES:
        ρl ≥ 0.0025 + 0.5·(2.5 − hw/lw)·(ρt − 0.0025)

    The hw/lw ratio is clamped to [0.5, 2.5]:
      - hw/lw ≥ 2.5 → ρl_eq = 0.0025 (only minimum vertical)
      - hw/lw ≤ 0.5 → ρl_eq = ρt (vertical equals horizontal)

    and ρl need not exceed the ρt required for strength by §11.5.4.3, which
    is why the equation takes the provided ratio: with the required one the
    ceiling could never bind. See ``wall_eq.min_vertical_reinforcement_ratio``
    for the reading. A wall whose horizontal mesh is heavier than its shear
    needs therefore asks for a heavier vertical mesh as well.

    The low-shear branch is not implemented: §11.6.2 always governs here,
    which is conservative. It is ACI 318-19 §11.6.1 with Table 11.6.1 /
    CIRSOC 201-25 §11.6.1 with Table 11.6.1, and it relaxes both minima where

        in-plane Vu ≤ 0.04·φ·α_c·λ·√f'c·Acv   (ACI SI and CIRSOC)
        in-plane Vu ≤ 0.5 ·φ·α_c·λ·√f'c·Acv   (ACI in-lb)

    so the threshold coefficient would be a registry datum too. The table
    itself carries the same ratios in both codes (0.0012/0.0020 and
    0.0015/0.0025 cast-in-place, 0.0010 precast); only the way it names the
    bar sizes differs — ACI "No. 16" and "MW200 or MD200" against CIRSOC
    "16 mm".
    """
    st.rho_t_min = wall_eq.MIN_REINFORCEMENT_RATIO * dimensionless
    st.rho_l_min = (
        wall_eq.min_vertical_reinforcement_ratio(float(st.hw_lw), float(self._rho_t), float(st.rho_t_req))
        * dimensionless
    )


def _calculate_spacing_limits_wall(self: "ShearWall", st: WallShearCheckState) -> None:
    """
    Spacing limits for a cast-in-place wall, the same numbers in both codes.

    Horizontal (transverse reinforcement) — ACI 318-19 §11.7.3.1 /
    CIRSOC 201-25 §11.7.3.1:
        s_h,max = min(lw/5, 3t, 450 mm / 18 in)
    Vertical (longitudinal bars) — ACI 318-19 §11.7.2.1 /
    CIRSOC 201-25 §11.7.2.1:
        s_v,max = min(lw/3, 3t, 450 mm / 18 in)

    Both codes impose the lw/5 and lw/3 terms only where shear reinforcement is
    required for in-plane strength, which is read as the concrete alone not
    carrying the combination, Vu > φVc: an ACI 20x100 wall under 100 kN,
    below φVc = 127.5 kN, is held to 3t and 450 mm and not to lw/5 = 20 cm.
    Needs ``st.V_u`` and ``st.V_c_wall`` set. The precast limits — §11.7.2.2
    and §11.7.3.2 in both — are looser and are not offered here.
    """
    is_imperial = self.concrete.is_imperial
    _, length_unit = _wall_units(self)
    lw = self.length.to(length_unit).magnitude
    t = self.thickness.to(length_unit).magnitude
    phi_V_c = self.concrete.phi_v * st.V_c_wall  # type: ignore[attr-defined]
    required = bool(st.V_u > phi_V_c)

    st.s_h_max = (
        wall_eq.max_horizontal_spacing(lw, t, is_imperial=is_imperial, shear_reinforcement_required=required)
        * length_unit
    )
    st.s_v_max = (
        wall_eq.max_vertical_spacing(lw, t, is_imperial=is_imperial, shear_reinforcement_required=required)
        * length_unit
    )


##########################################################
# MAIN CHECK FUNCTION
##########################################################


def _check_shear_ACI_318_19_wall(self: "ShearWall", force: Forces) -> WallShearCheckState:
    """
    ACI 318-19 Chapter 11 / CIRSOC 201-25 Chapter 11 shear check for a
    structural wall.

    Scope: ordinary structural walls only. Special structural walls are out of
    scope and the two codes send them to different places — ACI 318-19 §11.1.2
    to Chapter 18 (§18.10), CIRSOC 201-25 §11.1.2 (and C 11.5.4.1) to
    INPRES-CIRSOC 103 Parte II-2026. Out-of-plane shear (§11.5.5.1 → §22.5 in
    both) is not covered here either, nor is the strut-and-tie alternative
    that §11.5.4.1 of both codes permits for hw/lw < 2 (Chapter 23): mento
    always takes the §11.5.4.2-§11.5.4.4 route, which that clause allows for
    any wall.

    Calculation only: the result is returned as a value, and only the reporting
    path copies it back onto the wall. See the beam's shear check for the same
    split.
    """
    if not isinstance(self.concrete, Concrete_ACI_318_19):
        raise TypeError("ACI 318-19 wall shear check requires Concrete_ACI_318_19.")

    concrete = self.concrete
    st = new_wall_shear_state(self)

    # 1. Demand, in the wall's own force unit
    force_unit = _wall_force_unit(self)
    st.V_u = abs(force._V_z.to(force_unit))
    st.N_u = force._N_x.to(force_unit)

    # 2. Geometry: Acv = lw × t
    _calculate_wall_Acv(self, st)

    # 3. Material: fyt cap
    st.f_yt_wall = _calculate_f_yt_wall(self)

    # 4. α_c based on hw/lw (also sets st.hw_lw)
    st.alpha_c = _calculate_alpha_c(self, st)

    # 5. Shear strength components
    _calculate_wall_shear_strength(self, st, concrete)

    # 6. Spacing limits
    _calculate_spacing_limits_wall(self, st)

    # 7. Required ρt for design
    phi_v = concrete.phi_v
    f_c = concrete.f_c
    lam = concrete.lambda_factor

    stress_unit, _ = _wall_units(self)
    Vc_intensity = wall_eq.concrete_shear_stress(f_c.to(stress_unit).magnitude, st.alpha_c, lam) * stress_unit

    st.rho_t_min = wall_eq.MIN_REINFORCEMENT_RATIO * dimensionless
    rho_t_req_raw = ((st.V_u / phi_v) / st.Acv - Vc_intensity) / st.f_yt_wall
    rho_t_req_raw = rho_t_req_raw.to("")
    st.rho_t_req = max(rho_t_req_raw, st.rho_t_min)

    # 8. Minimum reinforcement ratios (ρl,min reads the ρt provided, capped by ρt,req — §11.6.2(a))
    _calculate_rho_min_wall(self, st)

    # 9. DCR
    phi_Vn_eff = min(st.phi_V_n_wall, st.phi_V_n_max_wall)
    if phi_Vn_eff.magnitude == 0:  # pragma: no cover - defensive: Vc > 0 for valid concrete
        st.DCR = float("inf")
    else:
        st.DCR = float((st.V_u / phi_Vn_eff).to("").magnitude)

    return st


##########################################################
# DESIGN FUNCTION
##########################################################


def _design_shear_wall_core(
    self: "ShearWall",
    forces: list,
    transverse_bars: list,
    vertical_bars: list,
) -> None:
    """
    Worst-case wall mesh design across all force combinations.

      1. Run the shear check for every force; track the worst-case ρt,req.
      2. Select and apply the horizontal mesh (ρt,req / s_h,max).
      3. Derive ρl,min per ACI 318-19 §11.6.2(a) / CIRSOC 201-25 §11.6.2(a):
         Eq. (11.6.2) with the ρt that mesh provides, capped by the worst-case
         ρt,req. The mesh has to be chosen first because the equation reads
         the ratio provided, not the one required.
      4. Select and apply the vertical mesh (ρl,min / s_v,max). The vertical
         mesh is ALWAYS the code minimum — no flexure design in Phase 0.
    """
    if not forces:
        raise ValueError("Wall shear design requires at least one Forces object.")

    max_rho_t_req = 0.0
    state = None
    # The spacing limits move with the combination (lw/5 and lw/3 only where
    # Vu > φVc), so the mesh takes the tightest of them.
    s_h_max = s_v_max = None
    for force in forces:
        state = _check_shear_ACI_318_19_wall(self, force)
        max_rho_t_req = max(max_rho_t_req, state.rho_t_req.to("").magnitude)
        s_h_max = state.s_h_max if s_h_max is None else min(s_h_max, state.s_h_max)
        s_v_max = state.s_v_max if s_v_max is None else min(s_v_max, state.s_v_max)
    # Designing is meant to change the wall, so the last state is applied.
    assert state is not None  # the empty-forces case raised above
    apply_wall_shear_state(self, state)

    cap = _WALL_BAR_CAP_METRIC if self.concrete.unit_system == "metric" else _WALL_BAR_CAP_IMPERIAL
    d_b_h, s_h = select_wall_mesh(self, max_rho_t_req, s_h_max, transverse_bars, cap)
    self.set_horizontal_rebar(d_b_h, s_h)

    # ρl,min of §11.6.2(a) with the ρt the mesh just applied provides. The
    # ceiling min(·, ρt,req) is monotonic in ρt,req, so the envelope over the
    # combinations is the value at the worst-case ρt,req; hw/lw is geometry only.
    max_rho_l_min = wall_eq.min_vertical_reinforcement_ratio(state.hw_lw, float(self._rho_t), max_rho_t_req)

    d_b_v, s_v = select_wall_mesh(self, max_rho_l_min, s_v_max, vertical_bars, cap)
    self.set_vertical_rebar(d_b_v, s_v)


def _design_shear_ACI_318_19_wall(self: "ShearWall", forces: list) -> None:
    """Wall mesh design per ACI 318-19 Chapter 11.

    Also serves CIRSOC 201-25, whose in-plane shear clauses carry the same
    numbers as the ACI ones used here: §11.5.4.2 (0.66√f'c·Acv), Eq. (11.5.4.3)
    with its α_c, §11.6.2 with Eq. (11.6.2), Table 11.6.1, §11.7.2.1/§11.7.3.1
    (3h, 450 mm, lw/3 and lw/5), §11.7.2.3 (two curtains above 250 mm) and
    Table 11.3.1.1 are identical.

    For net axial tension, §11.5.4.4 uses a divisor of 3.5·Ag in CIRSOC
    against ACI's 3.45·Ag, supplied through the registry. Special structural
    walls remain outside this check: §11.1.2 sends them to ACI Chapter 18
    or INPRES-CIRSOC 103 Parte II-2026.

    (Table 11.6.1 and §11.7.5.1 also name bar sizes differently — ACI "No. 16",
    CIRSOC "16 mm" — but that is designation, not value.) So the design is the
    same calculation under both codes.

    The only thing selected by design code here is the bar catalogue, and that
    is a mento criterion rather than a code requirement (see the catalogue
    comments above) — mirroring how ``rebar.py`` keeps the CIRSOC beam logic in
    one place. It belongs in the registry, like ``stirrup_spacing_caps``; until
    it moves there this branch stays, and it is the reason this module is not
    covered by the design-code-string ban of tests/test_architecture_boundaries.
    """
    if self.concrete.design_code == "CIRSOC 201-25":
        transverse_bars = _CIRSOC_WALL_BARS_TRANSVERSE
        vertical_bars = _CIRSOC_WALL_BARS_VERTICAL
    elif self.concrete.unit_system == "metric":
        transverse_bars = vertical_bars = _ACI_WALL_BARS_METRIC
    else:
        transverse_bars = vertical_bars = _ACI_WALL_BARS_IMPERIAL
    _design_shear_wall_core(self, forces, transverse_bars=transverse_bars, vertical_bars=vertical_bars)
