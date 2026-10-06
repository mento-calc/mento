"""
Tests for ShearWall — ACI 318-19 Section 11 shear check and design.

Reference calculation (metric):
    lw=4.0 m, t=0.25 m, hw=3.5 m, f'c=25 MPa, fy=420 MPa
    hw/lw = 0.875 ≤ 1.5  →  α_c = 0.25
    Acv = 1.0 m²

    Distributed mesh is on both faces (E.F.): ρ = 2·Ab/(t·s).

    Ø12@200 mm E.F.:  ρt = 2×113.097/(250×200) = 0.004524
    Vc  = 0.25 × 5 × 1.0 MPa·m² = 1 250 kN
    Vs  = 0.004524 × 420 × 1.0 MPa·m² ≈ 1 900 kN
    Vn  = 3 150 kN,  Vn,max = 3 300 kN
    φVn = 2 362.5 kN,  φVn,max = 2 475 kN
    Vu=1 200 kN → DCR = 1 200/2 362.5 ≈ 0.508

    Ø12@150 mm E.F.:  ρt = 2×113.097/(250×150) = 0.006032  (≥ 0.0025 → passes)
    s_h,max = min(4000/5, 3×250, 450) = 450 mm
    s_v,max = min(4000/3, 3×250, 450) = 450 mm
"""

import math

import pytest

from mento.forces import Forces
from mento.material import Concrete_ACI_318_19, Concrete_EN_1992_2004, SteelBar
from mento.shear_wall import ShearWall
from mento.units import MPa, cm, inch, kip, kN, ksi, m, mm, psi


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def wall_metric() -> ShearWall:
    concrete = Concrete_ACI_318_19(name="C25", f_c=25 * MPa)
    steel = SteelBar(name="ADN420", f_y=420 * MPa)
    return ShearWall(
        label="W1",
        concrete=concrete,
        steel_bar=steel,
        thickness=25 * cm,
        length=4.0 * m,
        height=3.5 * m,
        c_c=20 * mm,
    )


@pytest.fixture
def wall_high_hw() -> ShearWall:
    """hw/lw = 9/4 = 2.25 ≥ 2.0  →  α_c = 0.17."""
    concrete = Concrete_ACI_318_19(name="C25", f_c=25 * MPa)
    steel = SteelBar(name="ADN420", f_y=420 * MPa)
    return ShearWall(
        label="W_high",
        concrete=concrete,
        steel_bar=steel,
        thickness=25 * cm,
        length=4.0 * m,
        height=9.0 * m,
        c_c=20 * mm,
    )


@pytest.fixture
def wall_interp() -> ShearWall:
    """hw/lw = 7/4 = 1.75 (between 1.5 and 2.0)  →  α_c = 0.21."""
    concrete = Concrete_ACI_318_19(name="C25", f_c=25 * MPa)
    steel = SteelBar(name="ADN420", f_y=420 * MPa)
    return ShearWall(
        label="W_interp",
        concrete=concrete,
        steel_bar=steel,
        thickness=25 * cm,
        length=4.0 * m,
        height=7.0 * m,
        c_c=20 * mm,
    )


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------


class TestShearWallInit:
    def test_mode_is_shear_wall(self, wall_metric: ShearWall) -> None:
        assert wall_metric.mode == "shear_wall"

    def test_rho_t_starts_zero(self, wall_metric: ShearWall) -> None:
        assert wall_metric._rho_t.to("").magnitude == pytest.approx(0.0)

    def test_set_horizontal_rebar_updates_rho_t(self, wall_metric: ShearWall) -> None:
        # Mesh on both faces (E.F.): ρt = 2·Ab/(t·s)
        wall_metric.set_horizontal_rebar(d_b=12 * mm, s=200 * mm)
        expected = 2 * (math.pi / 4 * 12**2) / (250 * 200)  # mm²/(mm·mm)
        assert wall_metric._rho_t.to("").magnitude == pytest.approx(expected, rel=1e-4)

    def test_set_vertical_rebar_updates_rho_l(self, wall_metric: ShearWall) -> None:
        # Mesh on both faces (E.F.): ρl = 2·Ab/(t·s)
        wall_metric.set_vertical_rebar(d_b=12 * mm, s=150 * mm)
        expected = 2 * (math.pi / 4 * 12**2) / (250 * 150)
        assert wall_metric._rho_l.to("").magnitude == pytest.approx(expected, rel=1e-4)

    def test_zero_spacing_clears_rebar_ratios(self, wall_metric: ShearWall) -> None:
        wall_metric.set_horizontal_rebar(d_b=12 * mm, s=200 * mm)
        wall_metric.set_vertical_rebar(d_b=12 * mm, s=150 * mm)

        # Clearing the mesh must not divide by the zero spacing
        wall_metric.set_horizontal_rebar(d_b=0 * mm, s=0 * mm)
        wall_metric.set_vertical_rebar(d_b=0 * mm, s=0 * mm)

        assert wall_metric._rho_t.to("").magnitude == 0
        assert wall_metric._rho_l.to("").magnitude == 0


# ---------------------------------------------------------------------------
# α_c
# ---------------------------------------------------------------------------


class TestAlphaC:
    def test_alpha_c_low_hw_lw(self, wall_metric: ShearWall) -> None:
        wall_metric.set_horizontal_rebar(d_b=12 * mm, s=200 * mm)
        wall_metric.check_shear([Forces(V_z=500 * kN)])
        assert wall_metric._hw_lw == pytest.approx(0.875, rel=1e-4)
        assert wall_metric._alpha_c == pytest.approx(0.25, rel=1e-4)

    def test_alpha_c_high_hw_lw(self, wall_high_hw: ShearWall) -> None:
        wall_high_hw.set_horizontal_rebar(d_b=12 * mm, s=200 * mm)
        wall_high_hw.check_shear([Forces(V_z=500 * kN)])
        assert wall_high_hw._alpha_c == pytest.approx(0.17, rel=1e-4)

    def test_alpha_c_interpolated(self, wall_interp: ShearWall) -> None:
        wall_interp.set_horizontal_rebar(d_b=12 * mm, s=200 * mm)
        wall_interp.check_shear([Forces(V_z=500 * kN)])
        # hw/lw=1.75 → t=0.5  → α_c = 0.25 + 0.5*(0.17-0.25) = 0.21
        assert wall_interp._alpha_c == pytest.approx(0.21, rel=1e-4)


# ---------------------------------------------------------------------------
# Shear strength
# ---------------------------------------------------------------------------


class TestShearStrength:
    def test_Vc(self, wall_metric: ShearWall) -> None:
        wall_metric.set_horizontal_rebar(d_b=12 * mm, s=200 * mm)
        wall_metric.check_shear([Forces(V_z=1200 * kN)])
        # Vc = 0.25 × 1.0 × √25 MPa × 1.0 m² = 1 250 kN
        assert wall_metric._V_c_wall.to("kN").magnitude == pytest.approx(1250.0, rel=1e-3)

    def test_phi_Vc(self, wall_metric: ShearWall) -> None:
        wall_metric.set_horizontal_rebar(d_b=12 * mm, s=200 * mm)
        wall_metric.check_shear([Forces(V_z=1200 * kN)])
        assert (wall_metric.concrete.phi_v * wall_metric._V_c_wall).to("kN").magnitude == pytest.approx(937.5, rel=1e-3)

    def test_phi_Vn(self, wall_metric: ShearWall) -> None:
        # Ø12@200 E.F.: Vs ≈ 1900 kN → Vn ≈ 3150 kN → φVn ≈ 2362.5 kN
        wall_metric.set_horizontal_rebar(d_b=12 * mm, s=200 * mm)
        wall_metric.check_shear([Forces(V_z=1200 * kN)])
        assert wall_metric._phi_V_n_wall.to("kN").magnitude == pytest.approx(2362.5, rel=1e-2)

    def test_phi_Vn_max(self, wall_metric: ShearWall) -> None:
        wall_metric.set_horizontal_rebar(d_b=12 * mm, s=200 * mm)
        wall_metric.check_shear([Forces(V_z=1200 * kN)])
        assert wall_metric._phi_V_n_max_wall.to("kN").magnitude == pytest.approx(2475.0, rel=1e-2)

    def test_DCR(self, wall_metric: ShearWall) -> None:
        wall_metric.set_horizontal_rebar(d_b=12 * mm, s=200 * mm)
        result = wall_metric.check_shear([Forces(V_z=1200 * kN)])
        # data row is index 1 (index 0 is units row)
        dcr = float(result.iloc[1]["DCR"])
        assert dcr == pytest.approx(1200.0 / 2362.5, rel=1e-2)

    def test_Vu_le_phi_Vn(self, wall_metric: ShearWall) -> None:
        wall_metric.set_horizontal_rebar(d_b=12 * mm, s=200 * mm)
        result = wall_metric.check_shear([Forces(V_z=1200 * kN)])
        assert result.iloc[1]["Vu≤ØVn"] is True

    def test_Vu_le_phi_Vn_max(self, wall_metric: ShearWall) -> None:
        wall_metric.set_horizontal_rebar(d_b=12 * mm, s=200 * mm)
        result = wall_metric.check_shear([Forces(V_z=1200 * kN)])
        assert result.iloc[1]["Vu≤ØVn,max"] is True


# ---------------------------------------------------------------------------
# Minimum reinforcement
# ---------------------------------------------------------------------------


class TestMinReinforcement:
    def test_rho_t_min_is_0025(self, wall_metric: ShearWall) -> None:
        wall_metric.set_horizontal_rebar(d_b=12 * mm, s=200 * mm)
        wall_metric.check_shear([Forces(V_z=500 * kN)])
        assert wall_metric._rho_t_min.to("").magnitude == pytest.approx(0.0025, rel=1e-4)

    def test_rho_l_min_is_0025_when_hw_lw_gt2(self, wall_high_hw: ShearWall) -> None:
        # hw/lw=2.25 > 2.0 → ρl,min = 0.0025 regardless of ρt
        wall_high_hw.set_horizontal_rebar(d_b=16 * mm, s=100 * mm)
        wall_high_hw.set_vertical_rebar(d_b=12 * mm, s=200 * mm)
        wall_high_hw.check_shear([Forces(V_z=500 * kN)])
        assert wall_high_hw._rho_l_min.to("").magnitude == pytest.approx(0.0025, rel=1e-4)

    def test_rho_l_min_interpolated_per_11_6_2(self, wall_metric: ShearWall) -> None:
        """ACI 318-19 / CIRSOC 201-25 §11.6.2(a): Eq. (11.6.2) with the ρt provided, capped by ρt,req.

        Ø16/10 E.F. gives ρt = 2·201.06/(250·100) = 0.016085; Vu = 2000 kN
        needs ρt,req = (2000/0.75/1.0 − 0.25·5)/420 = 0.0033730 > 0.0025, so
        the interpolation bites: 0.0025 + 0.5·(2.5 − 0.875)·(0.016085 − 0.0025)
        = 0.013538, and ρl need not exceed the 0.0033730 required for strength.
        """
        wall_metric.set_horizontal_rebar(d_b=16 * mm, s=100 * mm)
        wall_metric.set_vertical_rebar(d_b=12 * mm, s=200 * mm)
        wall_metric.check_shear([Forces(V_z=2000 * kN)])
        rho_t = wall_metric._rho_t.to("").magnitude
        rho_t_req = wall_metric._rho_t_req.to("").magnitude
        assert rho_t_req == pytest.approx(0.0033730, abs=1e-6)
        r_hw = max(0.5, min(wall_metric._hw_lw, 2.5))
        equation = 0.0025 + 0.5 * (2.5 - r_hw) * (rho_t - 0.0025)
        assert equation == pytest.approx(0.013538, abs=1e-5)
        assert wall_metric._rho_l_min.to("").magnitude == pytest.approx(min(equation, rho_t_req), rel=1e-6)
        assert wall_metric._rho_l_min.to("").magnitude == pytest.approx(0.0033730, abs=1e-6)

    def test_rho_l_min_reads_the_horizontal_mesh_provided(self, wall_metric: ShearWall) -> None:
        """A heavier horizontal mesh than the shear needs asks for more vertical steel.

        ACI 318-19 / CIRSOC 201-25 §11.6.2(a), by hand for the reference wall
        (hw/lw = 0.875, αc = 0.25, Acv = 1.0 m²) under Vu = 2000 kN:
            ρt,req = (2000/0.75/1.0 − 1.25)/420 = 0.0033730
            Ø12/15 E.F.: ρt = 2·113.10/(250·150) = 0.0060319
            Eq. (11.6.2) = 0.0025 + 0.8125·(0.0060319 − 0.0025) = 0.0053697
            ρl,min = max(0.0025, min(0.0053697, 0.0033730)) = 0.0033730
            Ø10/19 E.F.: ρl = 2·78.54/(250·190) = 0.0033069 < ρl,min
        Fed the required ratio instead, the equation gave 0.0032093 and the
        mesh passed.
        """
        wall_metric.set_horizontal_rebar(d_b=12 * mm, s=15 * cm)
        wall_metric.set_vertical_rebar(d_b=10 * mm, s=19 * cm)
        check = wall_metric.shear_check_results([Forces(label="U1", V_z=2000 * kN)])[0]
        assert check.rho_t == pytest.approx(0.0060319, abs=1e-6)
        assert check.rho_t_req == pytest.approx(0.0033730, abs=1e-6)
        assert check.rho_l == pytest.approx(0.0033069, abs=1e-6)
        assert check.rho_l_min == pytest.approx(0.0033730, abs=1e-6)

        vertical = [w for w in wall_metric.warnings if w.code == "mesh_ratio_below_min"]
        assert len(vertical) == 1 and "Vertical" in vertical[0].message
        assert vertical[0].values["rho_min"] == pytest.approx(0.00337, abs=1e-5)

        wall_metric.check_shear([Forces(label="U1", V_z=2000 * kN)])
        assert wall_metric._data_min_max_wall["Ok?"][1] == "❌"

    def test_rho_t_below_min_flagged(self, wall_metric: ShearWall) -> None:
        # Ø12@400 E.F. → ρt = 2×113.097/(250×400) = 0.002262 < 0.0025 → ❌
        wall_metric.set_horizontal_rebar(d_b=12 * mm, s=400 * mm)
        wall_metric.set_vertical_rebar(d_b=12 * mm, s=400 * mm)
        wall_metric.check_shear([Forces(V_z=500 * kN)])
        assert wall_metric._data_min_max_wall["Ok?"][0] == "❌"

    def test_rho_t_above_min_passes(self, wall_metric: ShearWall) -> None:
        # Ø12@150 E.F. → ρt = 2×113.097/(250×150) ≈ 0.006032 > 0.0025 → ✅
        wall_metric.set_horizontal_rebar(d_b=12 * mm, s=150 * mm)
        wall_metric.set_vertical_rebar(d_b=12 * mm, s=150 * mm)
        wall_metric.check_shear([Forces(V_z=500 * kN)])
        assert wall_metric._data_min_max_wall["Ok?"][0] == "✅"


# ---------------------------------------------------------------------------
# Spacing limits
# ---------------------------------------------------------------------------


class TestSpacingLimits:
    def test_s_h_max_metric(self, wall_metric: ShearWall) -> None:
        # min(4000/5, 3×250, 450) = min(800, 750, 450) = 450 mm
        wall_metric.set_horizontal_rebar(d_b=12 * mm, s=200 * mm)
        wall_metric.check_shear([Forces(V_z=500 * kN)])
        assert wall_metric._s_h_max.to("mm").magnitude == pytest.approx(450.0, rel=1e-4)

    def test_s_v_max_metric(self, wall_metric: ShearWall) -> None:
        # min(4000/3, 3×250, 450) = min(1333, 750, 450) = 450 mm
        wall_metric.set_horizontal_rebar(d_b=12 * mm, s=200 * mm)
        wall_metric.check_shear([Forces(V_z=500 * kN)])
        assert wall_metric._s_v_max.to("mm").magnitude == pytest.approx(450.0, rel=1e-4)

    def test_spacing_ok_flag_when_within_limit(self, wall_metric: ShearWall) -> None:
        wall_metric.set_horizontal_rebar(d_b=12 * mm, s=200 * mm)
        wall_metric.set_vertical_rebar(d_b=12 * mm, s=200 * mm)
        wall_metric.check_shear([Forces(V_z=500 * kN)])
        # s_h=200 ≤ 450 → ✅
        assert wall_metric._data_min_max_wall["Ok?"][2] == "✅"
        assert wall_metric._data_min_max_wall["Ok?"][3] == "✅"

    def test_spacing_fail_flag_when_exceeds_limit(self) -> None:
        concrete = Concrete_ACI_318_19(name="C25", f_c=25 * MPa)
        steel = SteelBar(name="ADN420", f_y=420 * MPa)
        # Small wall: lw=500 mm, t=150 mm → s_h,max = min(100, 450, 450) = 100 mm
        wall = ShearWall(
            label="W_small",
            concrete=concrete,
            steel_bar=steel,
            thickness=150 * mm,
            length=500 * mm,
            height=3000 * mm,
            c_c=20 * mm,
        )
        wall.set_horizontal_rebar(d_b=12 * mm, s=200 * mm)  # 200 > s_h,max
        wall.set_vertical_rebar(d_b=12 * mm, s=200 * mm)
        wall.check_shear([Forces(V_z=100 * kN)])
        assert wall._data_min_max_wall["Ok?"][2] == "❌"


# ---------------------------------------------------------------------------
# DataFrame output
# ---------------------------------------------------------------------------


class TestDataFrameOutput:
    def test_result_columns(self, wall_metric: ShearWall) -> None:
        wall_metric.set_horizontal_rebar(d_b=12 * mm, s=200 * mm)
        result = wall_metric.check_shear([Forces(V_z=1200 * kN)])
        expected_cols = [
            "Label",
            "Comb.",
            "ρt,min",
            "ρt,req",
            "ρt",
            "ρl,min",
            "ρl",
            "Vu",
            "ØVc",
            "ØVs",
            "ØVn",
            "ØVn,max",
            "Vu≤ØVn,max",
            "Vu≤ØVn",
            "DCR",
        ]
        assert list(result.columns) == expected_cols

    def test_result_two_rows_for_one_force(self, wall_metric: ShearWall) -> None:
        # Row 0 = units header, row 1 = data
        wall_metric.set_horizontal_rebar(d_b=12 * mm, s=200 * mm)
        result = wall_metric.check_shear([Forces(V_z=1200 * kN)])
        assert len(result) == 2

    def test_units_row_has_kN(self, wall_metric: ShearWall) -> None:
        wall_metric.set_horizontal_rebar(d_b=12 * mm, s=200 * mm)
        result = wall_metric.check_shear([Forces(V_z=500 * kN)])
        assert result.iloc[0]["Vu"] == "kN"

    def test_shear_checked_flag_set(self, wall_metric: ShearWall) -> None:
        wall_metric.set_horizontal_rebar(d_b=12 * mm, s=200 * mm)
        wall_metric.check_shear([Forces(V_z=500 * kN)])
        assert wall_metric._shear_checked is True
        assert wall_metric._shear_wall_checked is True


# ---------------------------------------------------------------------------
# Multiple forces
# ---------------------------------------------------------------------------


class TestMultipleForces:
    def test_three_rows_for_two_forces(self, wall_metric: ShearWall) -> None:
        wall_metric.set_horizontal_rebar(d_b=12 * mm, s=150 * mm)
        wall_metric.set_vertical_rebar(d_b=12 * mm, s=150 * mm)
        f1 = Forces(label="C1", V_z=500 * kN)
        f2 = Forces(label="C2", V_z=1500 * kN)
        result = wall_metric.check_shear([f1, f2])
        assert len(result) == 3  # units row + 2 data rows

    def test_limiting_case_has_highest_dcr(self, wall_metric: ShearWall) -> None:
        wall_metric.set_horizontal_rebar(d_b=12 * mm, s=150 * mm)
        wall_metric.set_vertical_rebar(d_b=12 * mm, s=150 * mm)
        f1 = Forces(label="C1", V_z=500 * kN)
        f2 = Forces(label="C2", V_z=1500 * kN)
        result = wall_metric.check_shear([f1, f2])
        data = result.iloc[1:]  # skip units row
        data_dcr = data["DCR"].astype(float)
        assert data_dcr.idxmax() == data.index[-1]  # C2 is the worst case


# ---------------------------------------------------------------------------
# Design
# ---------------------------------------------------------------------------


class TestDesignShear:
    def test_design_returns_dataframe(self, wall_metric: ShearWall) -> None:
        wall_metric.set_horizontal_rebar(d_b=12 * mm, s=200 * mm)
        wall_metric.set_vertical_rebar(d_b=12 * mm, s=200 * mm)
        result = wall_metric.design_shear([Forces(V_z=500 * kN)])
        import pandas as pd

        assert isinstance(result, pd.DataFrame)

    def test_rho_t_req_at_least_rho_t_min(self, wall_metric: ShearWall) -> None:
        wall_metric.design_shear([Forces(V_z=200 * kN)])
        assert wall_metric._rho_t_req.to("").magnitude >= 0.0025 - 1e-9

    def test_design_assigns_mesh(self, wall_metric: ShearWall) -> None:
        """design_shear must select and apply a valid mesh in both directions."""
        wall_metric.design_shear([Forces(V_z=1200 * kN)])
        assert wall_metric._s_h.magnitude > 0
        assert wall_metric._s_v.magnitude > 0
        assert wall_metric._rho_t.to("").magnitude >= wall_metric._rho_t_req.to("").magnitude - 1e-9
        assert wall_metric._rho_l.to("").magnitude >= wall_metric._rho_l_min.to("").magnitude - 1e-9
        assert wall_metric._s_h <= wall_metric._s_h_max
        assert wall_metric._s_v <= wall_metric._s_v_max

    def test_design_respects_bar_cap(self, wall_metric: ShearWall) -> None:
        """A low-demand wall should stay at or below the Ø12 mm crack-control cap."""
        wall_metric.design_shear([Forces(V_z=600 * kN)])
        assert wall_metric._d_b_h <= 12 * mm
        assert wall_metric._d_b_v <= 12 * mm

    def test_design_spacing_on_grid(self, wall_metric: ShearWall) -> None:
        """Selected spacings are integer centimetres on the 2.5 cm-derived grid."""
        wall_metric.design_shear([Forces(V_z=900 * kN)])
        for s in (wall_metric._s_h, wall_metric._s_v):
            s_cm = s.to("cm").magnitude
            assert abs(s_cm - round(s_cm)) < 1e-6  # whole centimetres
            assert s_cm >= 5.0  # practical floor

    def test_design_worst_case_across_forces(self, wall_metric: ShearWall) -> None:
        """The designed mesh must satisfy the most demanding combination."""
        result = wall_metric.design_shear([Forces(label="c1", V_z=400 * kN), Forces(label="c2", V_z=1300 * kN)])
        assert result["DCR"].iloc[1:].astype(float).max() <= 1.0

    def test_design_sizes_the_vertical_mesh_to_the_horizontal_one_applied(self, wall_metric: ShearWall) -> None:
        """The design reads ρl,min of §11.6.2(a) off the horizontal mesh it just chose.

        Reference wall, Vu = 2000 kN, by hand:
            ρt,req = 0.0033730 → Ø10/17 E.F. (ρt = 2·78.54/(250·170) = 0.0036960;
            the 80/20 functional scores it 0.930 against 0.912 for Ø12/25)
            Eq. (11.6.2) = 0.0025 + 0.8125·(0.0036960 − 0.0025) = 0.0034718
            ρl,min = max(0.0025, min(0.0034718, 0.0033730)) = 0.0033730 → Ø10/17 E.F.
            ØVn = 0.75·(1250 + 0.0036960·420·1000) = 2101.7 kN, DCR = 0.952
        With the required ratio in the equation, ρl,min was 0.0032093 and the
        vertical mesh came out Ø12/27 E.F. (ρl = 0.0033510), short of the
        clause by 2.6 %.
        """
        wall_metric.design_shear([Forces(label="U1", V_z=2000 * kN)])
        design = wall_metric.shear_design
        assert str(design.mesh) == "horizontal: 2×Ø10 mm/17 cm / vertical: 2×Ø10 mm/17 cm"
        assert design.rho_t_req == pytest.approx(0.0033730, abs=1e-6)
        assert design.rho_l_min == pytest.approx(0.0033730, abs=1e-6)
        assert design.mesh.vertical.rho == pytest.approx(0.0036960, abs=1e-6)
        assert design.V_capacity.to("kN").magnitude == pytest.approx(2101.7, abs=0.1)
        assert design.DCR == pytest.approx(0.952, abs=1e-3)
        assert wall_metric.warnings == ()

    def test_design_cirsoc_allows_6mm_transverse(self) -> None:
        """CIRSOC vertical mesh stays ≥ Ø10 mm; transverse may use Ø6 mm."""
        from mento.material import Concrete_CIRSOC_201_25

        conc = Concrete_CIRSOC_201_25(name="H25", f_c=25 * MPa)
        steel = SteelBar(name="ADN420", f_y=420 * MPa)
        wall = ShearWall(
            label="WC",
            concrete=conc,
            steel_bar=steel,
            thickness=20 * cm,
            length=3.0 * m,
            height=2.5 * m,
            c_c=20 * mm,
        )
        wall.design_shear([Forces(V_z=150 * kN)])
        assert wall._d_b_v >= 10 * mm  # CIRSOC vertical minimum
        assert wall._d_b_h >= 6 * mm  # CIRSOC transverse minimum

    def test_design_empty_forces_raises(self, wall_metric: ShearWall) -> None:
        with pytest.raises(ValueError):
            wall_metric.design_shear([])

    def test_design_cirsoc_reference_wall(self) -> None:
        """CIRSOC 201-25 reference wall — full design + check.

        Shear Wall W1: lw=400 cm, t=20 cm, hw=350 cm, c_c=2 cm,
        Concrete C25, Rebar ADN 420.
        Expected design (Vu = 800 kN):
            Horizontal rebar:        Ø8/20 cm E.F.  → ρt = 0.00251
            Minimum vertical rebar:  Ø10/30 cm E.F. → ρl = 0.00262
            φVn = 1383.35 kN  →  DCR = 0.578
        """
        from mento.material import Concrete_CIRSOC_201_25

        concrete = Concrete_CIRSOC_201_25(name="C25", f_c=25 * MPa)
        steel = SteelBar(name="ADN 420", f_y=420 * MPa)
        wall = ShearWall(
            label="W1",
            concrete=concrete,
            steel_bar=steel,
            thickness=20 * cm,
            length=400 * cm,
            height=350 * cm,
            c_c=2 * cm,
        )
        wall.design_shear([Forces(V_z=800 * kN)])

        # Horizontal (transverse) mesh
        assert wall._d_b_h.to("mm").magnitude == pytest.approx(8.0)
        assert wall._s_h.to("cm").magnitude == pytest.approx(20.0)
        assert wall._rho_t.to("").magnitude == pytest.approx(0.00251, abs=1e-5)

        # Minimum vertical mesh
        assert wall._d_b_v.to("mm").magnitude == pytest.approx(10.0)
        assert wall._s_v.to("cm").magnitude == pytest.approx(30.0)
        assert wall._rho_l.to("").magnitude == pytest.approx(0.00262, abs=1e-5)

        # Capacity and demand-capacity ratio
        assert wall._phi_V_n_wall.to("kN").magnitude == pytest.approx(1383.35, rel=1e-3)
        assert wall._DCRv_wall == pytest.approx(0.578, abs=1e-3)


# ---------------------------------------------------------------------------
# Imperial unit system
# ---------------------------------------------------------------------------


@pytest.fixture
def wall_imperial() -> ShearWall:
    concrete = Concrete_ACI_318_19(name="C4", f_c=4000 * psi)
    steel = SteelBar(name="G60", f_y=60 * ksi)
    return ShearWall(
        label="WI",
        concrete=concrete,
        steel_bar=steel,
        thickness=10 * inch,
        length=160 * inch,
        height=120 * inch,
        c_c=1 * inch,
    )


class TestImperialWall:
    def test_imperial_check_units_row(self, wall_imperial: ShearWall) -> None:
        wall_imperial.set_horizontal_rebar(d_b=0.5 * inch, s=12 * inch)
        result = wall_imperial.check_shear([Forces(V_z=100 * kip)])
        assert result.iloc[0]["Vu"] == "kip"

    def test_imperial_alpha_c(self, wall_imperial: ShearWall) -> None:
        # hw/lw = 120/160 = 0.75 ≤ 1.5 → α_c = 3.0 (imperial)
        wall_imperial.set_horizontal_rebar(d_b=0.5 * inch, s=12 * inch)
        wall_imperial.check_shear([Forces(V_z=100 * kip)])
        assert wall_imperial._alpha_c == pytest.approx(3.0, rel=1e-4)

    def test_imperial_design(self, wall_imperial: ShearWall) -> None:
        wall_imperial.design_shear([Forces(V_z=120 * kip)])
        assert wall_imperial._s_h.magnitude > 0
        assert wall_imperial._s_v.magnitude > 0
        assert wall_imperial._rho_t.to("").magnitude >= wall_imperial._rho_t_req.to("").magnitude - 1e-9

    def test_imperial_results_are_in_kip(self, wall_imperial: ShearWall) -> None:
        """The public results and the detail table read in the wall's own unit system.

        ACI 318-19 §11.5.4.2 and Eq. (11.5.4.3) in in-lb, by hand:
            Acv = 10·160 = 1600 in², hw/lw = 0.75 → αc = 3
            Vc = 3·√4000·1600 = 303 579 lb = 303.58 kip
            #4 @ 12 in E.F.: ρt = 2·0.19635/(10·12) = 0.0032725
            Vs = 0.0032725·60 000·1600 = 314 159 lb = 314.16 kip
            Vn,max = 8·√4000·1600 = 809 543 lb = 809.54 kip
            ØVn = 0.75·(303.58 + 314.16) = 463.30 kip, ØVn,max = 607.16 kip
            Vu = 100 kip → DCR = 0.2158
        The check used to store every force in kN, so V_capacity read 2060.8 kN
        and the detail table printed 2060.8 under a "kip" label.
        """
        wall_imperial.set_horizontal_rebar(d_b=0.5 * inch, s=12 * inch)
        wall_imperial.set_vertical_rebar(d_b=0.5 * inch, s=12 * inch)
        check = wall_imperial.shear_check_results([Forces(label="U1", V_z=100 * kip)])[0]
        assert check.V_u.units == kip and check.V_capacity.units == kip and check.V_max.units == kip
        assert check.V_u.magnitude == pytest.approx(100.0)
        assert check.V_capacity.magnitude == pytest.approx(463.30, abs=0.01)
        assert check.V_max.magnitude == pytest.approx(607.16, abs=0.01)
        assert check.DCR == pytest.approx(0.2158, abs=1e-4)
        assert check.s_h_max.units == inch

        wall_imperial.check_shear([Forces(label="U1", V_z=100 * kip)])
        assert wall_imperial._V_c_wall.units == kip
        strength = wall_imperial._shear_capacity_wall
        assert strength["Unit"][:4] == ["kip"] * 4
        assert strength["Value"][:4] == pytest.approx([227.68, 235.62, 463.30, 607.16], abs=0.01)
        assert wall_imperial.shear_design.V_capacity.units == kip


# ---------------------------------------------------------------------------
# Reporting, display, plot, and error paths (coverage)
# ---------------------------------------------------------------------------


class TestShearWallReporting:
    # --- unsupported design code ----------------------------------------
    def _en_wall(self) -> ShearWall:
        concrete = Concrete_EN_1992_2004(name="C25", f_c=25 * MPa)
        steel = SteelBar(name="ADN420", f_y=420 * MPa)
        return ShearWall(
            label="WE",
            concrete=concrete,
            steel_bar=steel,
            thickness=20 * cm,
            length=4.0 * m,
            height=3.5 * m,
            c_c=20 * mm,
        )

    def test_check_shear_unsupported_code_raises(self) -> None:
        with pytest.raises(NotImplementedError):
            self._en_wall().check_shear([Forces(V_z=100 * kN)])

    def test_design_shear_unsupported_code_raises(self) -> None:
        with pytest.raises(NotImplementedError):
            self._en_wall().design_shear([Forces(V_z=100 * kN)])

    # --- check()/design() wrappers --------------------------------------
    def test_check_wrapper(self, wall_metric: ShearWall) -> None:
        wall_metric.set_horizontal_rebar(d_b=12 * mm, s=200 * mm)
        assert wall_metric.check([Forces(V_z=500 * kN)]) is None
        assert wall_metric._shear_wall_checked is True

    def test_design_wrapper(self, wall_metric: ShearWall) -> None:
        assert wall_metric.design([Forces(V_z=500 * kN)]) is None
        assert wall_metric._s_h.magnitude > 0

    # --- flexure stubs ---------------------------------------------------
    def test_flexure_methods_raise(self, wall_metric: ShearWall) -> None:
        f = Forces(V_z=1 * kN)
        with pytest.raises(NotImplementedError):
            wall_metric.check_flexure([f])
        with pytest.raises(NotImplementedError):
            wall_metric.design_flexure([f])
        with pytest.raises(NotImplementedError):
            wall_metric.flexure_results_detailed()
        with pytest.raises(NotImplementedError):
            wall_metric.flexure_results_detailed_doc()

    # --- data / shear_results / results ---------------------------------
    def test_data_property(self, wall_metric: ShearWall) -> None:
        assert wall_metric.data is None
        assert "Shear Wall" in wall_metric._md_data

    def test_shear_results_not_checked(self, wall_metric: ShearWall) -> None:
        assert wall_metric.shear_results is None
        assert wall_metric._md_shear_results == "Shear results are not available."

    def test_shear_results_after_check(self, wall_metric: ShearWall) -> None:
        wall_metric.set_horizontal_rebar(d_b=12 * mm, s=200 * mm)
        wall_metric.set_vertical_rebar(d_b=12 * mm, s=200 * mm)
        wall_metric.check_shear([Forces(V_z=800 * kN)])
        assert wall_metric.shear_results is None
        assert "Horizontal rebar" in wall_metric._md_shear_results
        assert "E.F." in wall_metric._md_shear_results

    def test_shear_results_no_rebar_assigned(self, wall_metric: ShearWall) -> None:
        wall_metric.check_shear([Forces(V_z=200 * kN)])
        wall_metric.shear_results
        assert "not assigned" in wall_metric._md_shear_results

    def test_shear_results_no_capacity_branch(self, wall_metric: ShearWall) -> None:
        # White-box: checked flag set but no limiting-case details available.
        wall_metric._shear_wall_checked = True
        wall_metric._limiting_case_shear_details = None
        assert wall_metric.shear_results is None
        assert wall_metric._md_shear_results == "No shear to check."

    def test_results_property(self, wall_metric: ShearWall) -> None:
        wall_metric.set_horizontal_rebar(d_b=12 * mm, s=200 * mm)
        wall_metric.set_vertical_rebar(d_b=12 * mm, s=200 * mm)
        wall_metric.check_shear([Forces(V_z=800 * kN)])
        assert wall_metric.results is None

    # --- detailed results ------------------------------------------------
    def test_shear_results_detailed_not_checked(self, wall_metric: ShearWall) -> None:
        assert wall_metric.shear_results_detailed() is None

    def test_shear_results_detailed_limiting(self, wall_metric: ShearWall, capsys) -> None:
        wall_metric.set_horizontal_rebar(d_b=12 * mm, s=200 * mm)
        wall_metric.set_vertical_rebar(d_b=12 * mm, s=200 * mm)
        wall_metric.check_shear([Forces(V_z=800 * kN)])
        wall_metric.shear_results_detailed()
        assert "SHEAR WALL DETAILED RESULTS" in capsys.readouterr().out

    def test_shear_results_detailed_specific_force(self, wall_metric: ShearWall) -> None:
        wall_metric.set_horizontal_rebar(d_b=12 * mm, s=200 * mm)
        wall_metric.set_vertical_rebar(d_b=12 * mm, s=200 * mm)
        f = Forces(V_z=800 * kN)
        wall_metric.check_shear([f])
        wall_metric.shear_results_detailed(f)  # explicit force

    def test_shear_results_detailed_bad_force_raises(self, wall_metric: ShearWall) -> None:
        wall_metric.set_horizontal_rebar(d_b=12 * mm, s=200 * mm)
        wall_metric.check_shear([Forces(V_z=800 * kN)])
        with pytest.raises(ValueError):
            wall_metric.shear_results_detailed(Forces(V_z=1 * kN))

    def test_shear_results_detailed_doc(self, wall_metric: ShearWall, tmp_path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        wall_metric.set_horizontal_rebar(d_b=12 * mm, s=200 * mm)
        wall_metric.set_vertical_rebar(d_b=12 * mm, s=200 * mm)
        wall_metric.check_shear([Forces(V_z=800 * kN)])
        wall_metric.shear_results_detailed_doc()
        assert any(p.suffix == ".docx" for p in tmp_path.iterdir())

    def test_shear_results_detailed_doc_not_checked(self, wall_metric: ShearWall) -> None:
        assert wall_metric.shear_results_detailed_doc() is None

    def test_shear_results_detailed_doc_specific_force(self, wall_metric: ShearWall, tmp_path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        wall_metric.set_horizontal_rebar(d_b=12 * mm, s=200 * mm)
        wall_metric.set_vertical_rebar(d_b=12 * mm, s=200 * mm)
        f = Forces(V_z=800 * kN)
        wall_metric.check_shear([f])
        wall_metric.shear_results_detailed_doc(f)
        assert any(p.suffix == ".docx" for p in tmp_path.iterdir())

    def test_shear_results_detailed_doc_bad_force_raises(self, wall_metric: ShearWall) -> None:
        wall_metric.set_horizontal_rebar(d_b=12 * mm, s=200 * mm)
        wall_metric.check_shear([Forces(V_z=800 * kN)])
        with pytest.raises(ValueError):
            wall_metric.shear_results_detailed_doc(Forces(V_z=1 * kN))

    # --- plot ------------------------------------------------------------
    def test_plot_with_rebar(self, wall_metric: ShearWall) -> None:
        wall_metric.set_horizontal_rebar(d_b=12 * mm, s=200 * mm)
        wall_metric.set_vertical_rebar(d_b=10 * mm, s=300 * mm)
        fig = wall_metric.plot()
        assert fig is not None

    def test_plot_without_rebar(self, wall_metric: ShearWall) -> None:
        import warnings

        # show=True also exercises the plt.show() branch; under the Agg
        # backend it emits a harmless "non-interactive" warning we silence.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            fig = wall_metric.plot(show=True)
        assert fig is not None


# ---------------------------------------------------------------------------
# Code-function guards (white-box)
# ---------------------------------------------------------------------------


class TestWallCodeGuards:
    def test_check_function_rejects_non_aci_concrete(self) -> None:
        from mento.codes.ACI_318_19_wall import _check_shear_ACI_318_19_wall

        concrete = Concrete_EN_1992_2004(name="C25", f_c=25 * MPa)
        steel = SteelBar(name="ADN420", f_y=420 * MPa)
        wall = ShearWall(
            label="WE",
            concrete=concrete,
            steel_bar=steel,
            thickness=20 * cm,
            length=4.0 * m,
            height=3.5 * m,
            c_c=20 * mm,
        )
        with pytest.raises(TypeError):
            _check_shear_ACI_318_19_wall(wall, Forces(V_z=100 * kN))

    def test_design_core_empty_forces_raises(self, wall_metric: ShearWall) -> None:
        from mento.codes.ACI_318_19_wall import _ACI_WALL_BARS_METRIC, _design_shear_wall_core

        with pytest.raises(ValueError):
            _design_shear_wall_core(wall_metric, [], _ACI_WALL_BARS_METRIC, _ACI_WALL_BARS_METRIC)

    def test_design_no_bar_fits_raises(self) -> None:
        # Very short wall → s_h,max < 5 cm practical floor → empty grid → ValueError.
        concrete = Concrete_ACI_318_19(name="C25", f_c=25 * MPa)
        steel = SteelBar(name="ADN420", f_y=420 * MPa)
        wall = ShearWall(
            label="WT",
            concrete=concrete,
            steel_bar=steel,
            thickness=10 * cm,
            length=20 * cm,
            height=200 * cm,
            c_c=20 * mm,
        )
        with pytest.raises(ValueError):
            wall.design_shear([Forces(V_z=50 * kN)])


# ---------------------------------------------------------------------------
# Public results: the mesh and the shear results as dataclasses
# ---------------------------------------------------------------------------


def test_mesh_reads_the_bars_set_on_the_wall(wall_metric: ShearWall) -> None:
    wall_metric.set_horizontal_rebar(d_b=12 * mm, s=20 * cm)
    wall_metric.set_vertical_rebar(d_b=10 * mm, s=25 * cm)
    mesh = wall_metric.mesh
    assert mesh.horizontal.d_b == 12 * mm and mesh.horizontal.s == 20 * cm
    assert mesh.vertical.d_b == 10 * mm and mesh.vertical.s == 25 * cm
    assert mesh.horizontal.rho == pytest.approx(0.004524, rel=1e-3)
    assert mesh.horizontal.A_s.to("cm**2/m").magnitude == pytest.approx(2 * 1.131 / 0.20, rel=1e-3)
    assert str(mesh.horizontal) == "2×Ø12 mm/20 cm"


def test_mesh_without_bars(wall_metric: ShearWall) -> None:
    mesh = wall_metric.mesh
    assert not mesh.horizontal.has_bars
    assert mesh.horizontal.A_s.magnitude == 0
    assert str(mesh.vertical) == "no reinforcement"


def test_shear_results_are_the_wall_ones(wall_metric: ShearWall) -> None:
    # The reference case of this module: Ø12/20 E.F., Vu = 1200 kN, DCR ≈ 0.508.
    wall_metric.set_horizontal_rebar(d_b=12 * mm, s=20 * cm)
    wall_metric.set_vertical_rebar(d_b=12 * mm, s=20 * cm)
    forces = [Forces(label="U1", V_z=1200 * kN), Forces(label="U2", V_z=600 * kN)]
    table = wall_metric.check_shear(forces)

    checks = wall_metric.shear_checks
    assert [c.label for c in checks] == ["U1", "U2"]
    assert checks[0].DCR == pytest.approx(table["DCR"].iloc[1], abs=1e-3)
    assert checks[0].DCR == pytest.approx(0.508, abs=1e-3)
    assert checks[0].V_capacity.to("kN").magnitude == pytest.approx(2362.5, rel=1e-3)
    assert checks[0].V_max.to("kN").magnitude == pytest.approx(2475, rel=1e-3)
    assert checks[0].s_h_max == 450 * mm

    design = wall_metric.shear_design
    assert design.DCR == pytest.approx(checks[0].DCR)
    assert design.V_capacity == checks[0].V_capacity
    assert design.mesh == wall_metric.mesh
    assert wall_metric.warnings == ()


def test_shear_check_results_matches_check_shear(wall_metric: ShearWall) -> None:
    wall_metric.set_horizontal_rebar(d_b=12 * mm, s=20 * cm)
    wall_metric.set_vertical_rebar(d_b=12 * mm, s=20 * cm)
    forces = [Forces(label="U1", V_z=1200 * kN)]
    fast = wall_metric.shear_check_results(forces)
    wall_metric.check_shear(forces)
    assert fast == wall_metric.shear_checks


def test_designed_wall_reports_its_mesh(wall_metric: ShearWall) -> None:
    wall_metric.design_shear([Forces(label="U1", V_z=1200 * kN)])
    design = wall_metric.shear_design
    assert design.mesh.horizontal.has_bars and design.mesh.vertical.has_bars
    assert design.mesh.horizontal.rho >= design.rho_t_req
    assert design.mesh.vertical.rho >= design.rho_l_min
    assert design.DCR <= 1
    assert wall_metric.warnings == ()


def test_shear_design_before_a_check_raises(wall_metric: ShearWall) -> None:
    from mento.design_results import DesignNotRunError

    with pytest.raises(DesignNotRunError):
        wall_metric.shear_design


def test_shear_results_carry_the_mesh_they_were_checked_with(wall_metric: ShearWall) -> None:
    """A design never pairs the mesh the wall carries now with the DCR of another.

    Reference wall under Vu = 2200 kN, by hand:
        ρt,req = (2200/0.75 − 1250)/(420·1000) = 0.0040079 → Ø10/15 E.F.
        (ρt = 2·78.54/(250·150) = 0.0041888; scores 0.965 against 0.946 for Ø12/22)
        ØVn = 0.75·(1250 + 0.0041888·420·1000) = 2257.0 kN, DCR = 2200/2257.0 = 0.975
    Ø6/45 E.F. set by hand afterwards: ρt = 2·28.27/(250·450) = 0.00050265,
        ØVn = 0.75·(1250 + 211.1) = 1095.8 kN, DCR = 2.008.
    The design read before the change used to print the new mesh next to the
    old 0.975.
    """
    from mento.design_results import DesignNotRunError

    forces = [Forces(label="U1", V_z=2200 * kN)]
    wall_metric.design_shear(forces)
    designed = wall_metric.shear_design
    assert str(designed.mesh.horizontal) == "2×Ø10 mm/15 cm"
    assert designed.DCR == pytest.approx(0.975, abs=1e-3)
    assert designed.V_capacity.to("kN").magnitude == pytest.approx(2257.0, abs=0.1)
    assert wall_metric.shear_checks[0].mesh == designed.mesh == wall_metric.mesh

    wall_metric.set_horizontal_rebar(d_b=6 * mm, s=45 * cm)
    assert wall_metric.mesh != designed.mesh
    assert wall_metric.shear_checks == ()
    assert wall_metric.warnings == ()
    with pytest.raises(DesignNotRunError, match="mesh the wall carries"):
        wall_metric.shear_design
    # The result read earlier is a value: it still describes the mesh it was formed with.
    assert str(designed.mesh.horizontal) == "2×Ø10 mm/15 cm" and designed.DCR == pytest.approx(0.975, abs=1e-3)

    wall_metric.check_shear(forces)
    rechecked = wall_metric.shear_design
    assert rechecked.mesh == wall_metric.mesh
    assert str(rechecked.mesh.horizontal) == "2×Ø6 mm/45 cm"
    assert rechecked.DCR == pytest.approx(2.008, abs=1e-3)
    assert rechecked.V_capacity.to("kN").magnitude == pytest.approx(1095.8, abs=0.1)
    assert {w.code for w in wall_metric.warnings} == {"mesh_ratio_below_min"}


def test_the_markdown_summary_drops_the_check_of_a_mesh_changed_by_hand(wall_metric: ShearWall) -> None:
    """``shear_results`` follows ``shear_design``: no summary of a mesh nobody checked.

    Reference wall with Ø10/15 E.F. both ways under Vu = 2000 kN, by hand
    (ACI 318-19 §11.5.4.3, hw/lw = 0.875 → αc = 0.25):
        ρt = 2·78.54/(250·150) = 0.0041888
        ØVn = 0.75·(0.25·√25·250·4000 + 0.0041888·420·250·4000) = 0.75·(1250 + 1759.3) = 2257.0 kN
        DCR = 2000/2257.0 = 0.886
    Ø6/45 E.F. set by hand afterwards: ρt = 2·28.27/(250·450) = 0.00050265,
        ØVn = 0.75·(1250 + 211.1) = 1095.8 kN, DCR = 2000/1095.8 = 1.825.
    The summary used to print "Horizontal rebar: Ø6/45 cm E.F., ρt=0.00419 …
    DCR=0.89": the mesh the wall carries beside the ratio and the DCR of the one
    checked, while ``shear_design`` already raised.
    """
    wall_metric.set_horizontal_rebar(d_b=10 * mm, s=15 * cm)
    wall_metric.set_vertical_rebar(d_b=10 * mm, s=15 * cm)
    forces = [Forces(label="U1", V_z=2000 * kN)]
    wall_metric.check_shear(forces)
    wall_metric.shear_results
    assert "Ø10/15 cm E.F., $\\rho_t$=0.00419" in wall_metric._md_shear_results
    assert "$\\phi V_n$=2256.97 kN" in wall_metric._md_shear_results

    wall_metric.set_horizontal_rebar(d_b=6 * mm, s=45 * cm)
    assert wall_metric.shear_results is None
    assert wall_metric._md_shear_results == "Shear results are not available."
    wall_metric._md_shear_results = ""
    assert wall_metric.results is None
    assert wall_metric._md_shear_results == ""  # `results` shows the wall data alone

    wall_metric.check_shear(forces)
    wall_metric.shear_results
    assert "Ø6/45 cm E.F., $\\rho_t$=0.0005" in wall_metric._md_shear_results
    assert "$\\phi V_n$=1095.84 kN" in wall_metric._md_shear_results


@pytest.mark.parametrize("setter", ["set_horizontal_rebar", "set_vertical_rebar"])
def test_a_mesh_set_by_hand_drops_the_results_of_the_previous_one(wall_metric: ShearWall, setter: str) -> None:
    from mento.design_results import DesignNotRunError

    wall_metric.set_horizontal_rebar(d_b=12 * mm, s=20 * cm)
    wall_metric.set_vertical_rebar(d_b=12 * mm, s=20 * cm)
    wall_metric.shear_check_results([Forces(label="U1", V_z=1200 * kN)])
    assert len(wall_metric.shear_checks) == 1

    getattr(wall_metric, setter)(d_b=10 * mm, s=25 * cm)
    assert wall_metric.shear_checks == ()
    with pytest.raises(DesignNotRunError):
        wall_metric.shear_design


def test_the_mesh_prints_both_directions(wall_metric: ShearWall) -> None:
    wall_metric.set_horizontal_rebar(d_b=12 * mm, s=20 * cm)
    wall_metric.set_vertical_rebar(d_b=10 * mm, s=25 * cm)

    assert str(wall_metric.mesh) == "horizontal: 2×Ø12 mm/20 cm / vertical: 2×Ø10 mm/25 cm"


def test_the_shear_design_prints_its_mesh(wall_metric: ShearWall) -> None:
    """A wall is identified by the mesh it carries, so the design reads as that mesh."""
    wall_metric.design_shear([Forces(label="U1", V_z=1200 * kN)])
    design = wall_metric.shear_design

    assert str(design) == str(design.mesh)
    assert str(design).startswith("horizontal: ")


@pytest.mark.parametrize("name", ["reinforcement", "flexure_design", "flexure_checks"])
def test_beam_results_are_not_offered_on_a_wall(wall_metric: ShearWall, name: str) -> None:
    """The member is missing the way an attribute is, and still a NotImplementedError.

    ``hasattr`` used to raise on a wall, which broke any loop over mixed beams
    and walls that asked for the member before reading it.
    """
    from mento.shear_wall import NotABeamError

    with pytest.raises(NotABeamError, match="mesh") as excinfo:
        getattr(wall_metric, name)
    assert isinstance(excinfo.value, AttributeError)
    assert isinstance(excinfo.value, NotImplementedError)
    assert not hasattr(wall_metric, name)
    assert getattr(wall_metric, name, None) is None


def test_flexure_check_results_is_not_offered_on_a_wall(wall_metric: ShearWall) -> None:
    """The values-only flexure entry point is a method, so the guard needs a call."""
    from mento.shear_wall import NotABeamError

    with pytest.raises(NotABeamError, match="mesh"):
        wall_metric.flexure_check_results([Forces(label="U1", V_z=1200 * kN)])
    with pytest.raises(NotImplementedError):
        wall_metric.flexure_check_results([Forces(label="U1", V_z=1200 * kN)])


def test_a_loop_over_beams_and_walls_can_ask_for_the_member(wall_metric: ShearWall) -> None:
    """What a generic caller does: read the beam result where there is one, the mesh where there is not."""
    from mento.beam import RectangularBeam

    beam = RectangularBeam(
        label="B1",
        concrete=wall_metric.concrete,
        steel_bar=wall_metric.steel_bar,
        width=20 * cm,
        height=50 * cm,
        c_c=25 * mm,
    )
    described = [
        str(reinforcement)
        if (reinforcement := getattr(section, "reinforcement", None)) is not None
        else str(section.mesh)
        for section in (beam, wall_metric)
    ]
    assert described[0].startswith("bottom: ")
    assert described[1] == "horizontal: no reinforcement / vertical: no reinforcement"


def test_wall_warnings(wall_metric: ShearWall) -> None:
    wall_metric.set_horizontal_rebar(d_b=6 * mm, s=50 * cm)  # thin and past s_h,max = 450 mm
    wall_metric.set_vertical_rebar(d_b=12 * mm, s=20 * cm)
    wall_metric.shear_check_results([Forces(label="U1", V_z=3000 * kN)])
    found = {(w.code, w.values.get("rho_min") is not None) for w in wall_metric.warnings}
    assert ("mesh_ratio_below_min", True) in found
    assert ("mesh_spacing_exceeds_max", False) in found
    assert ("shear_exceeds_section_limit", False) in found
    spacing = next(w for w in wall_metric.warnings if w.code == "mesh_spacing_exceeds_max")
    assert "Horizontal" in spacing.message


def test_the_beam_shear_attributes_read_the_walls_own_values() -> None:
    """Issue #171: ``wall.V_c`` and ``wall.f_yt`` stayed at the zeros a beam starts with.

    A ShearWall inherits them from RectangularBeam, whose shear check fills
    them; the wall's check (§11.5.4) fills its own. A 20 cm x 3 m wall, H25,
    ADN 420: V_c = alpha_c*lambda*sqrt(f'c)*Acv = 0.25*5*0.2*3 m² = 750 kN, and
    f_yt is the 420 MPa of the mesh. They now read those, in the wall's units.
    """
    wall = ShearWall(
        label="W",
        concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        c_c=25 * mm,
        thickness=20 * cm,
        length=3 * m,
        height=3 * m,
    )
    assert wall.V_c.magnitude == 0
    wall.design([Forces(label="E", V_z=400 * kN)])
    assert wall.V_c.to(kN).magnitude == pytest.approx(750.0)
    assert wall.f_yt.to(MPa).magnitude == pytest.approx(420.0)
    assert wall.V_c == wall._V_c_wall

    imperial = ShearWall(
        label="W",
        concrete=Concrete_ACI_318_19(name="4000", f_c=4000 * psi),
        steel_bar=SteelBar(name="Gr60", f_y=60 * ksi),
        c_c=1 * inch,
        thickness=8 * inch,
        length=120 * inch,
        height=120 * inch,
    )
    imperial.design([Forces(label="E", V_z=150 * kip)])
    assert imperial.V_c.units == kip
    assert imperial.V_c.magnitude > 0
    assert imperial.f_yt.to(ksi).magnitude == pytest.approx(60.0)
