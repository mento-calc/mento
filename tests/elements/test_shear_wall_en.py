"""
Tests for ShearWall — EN 1992-1-1:2004 in-plane shear, §6.2 with the detailing of §9.6.

Reference calculation (the default case of the Calcpad sheet
"HOR_Tabiques_Cortante_EN_1992-1-1_2004_v1"; a reproduction, so these are
regression tests, not published examples):

    l_w = 4.0 m, t = 0.20 m, C25/30, B500S, gamma_c = 1.5, gamma_s = 1.15
    f_cd = 25/1.5 = 16.667 MPa (alpha_cc = 1 for shear), f_ywd = 500/1.15 = 434.78 MPa
    A_c = 0.80 m², d = 0.8 l_w = 3200 mm, z = 0.9 d = 2880 mm
    k = 1 + sqrt(200/3200) = 1.25

    No end bars declared, rho_l = 0, so Eq. (6.2.b) gives V_Rd,c:
    v_min = 0.035 x 1.25^1.5 x sqrt(25) = 0.24457 MPa
    V_Rd,c = 0.24457 x 200 x 3200 = 156.52 kN

    nu_1 = 0.6 (1 - 25/250) = 0.54, alpha_cw = 1
    V_Rd,max(cot 2.5) = 200 x 2880 x 0.54 x 16.667 / (2.5 + 0.4) = 1787.59 kN
    V_Rd,max(45°)     = 200 x 2880 x 0.54 x 16.667 / 2           = 2592.00 kN

    Mesh 2xØ8/200 horizontal, 2xØ12/200 vertical:
    A_sh = 2 x 50.27/200 = 0.5027 mm²/mm (5.03 cm²/m)
    A_sv = 2 x 113.10/200 = 1.1310 mm²/mm (11.31 cm²/m)

    V_Ed = 1200 kN > V_Rd,c, and <= V_Rd,max(cot 2.5) -> cot(theta) = 2.5
    V_Rd,s = 0.5027 x 2880 x 434.78 x 2.5 = 1573.53 kN = V_Rd -> DCR = 0.7626
    A_sh,str = 1 200 000 / (2880 x 434.78 x 2.5) = 0.3833 mm²/mm (3.83 cm²/m)
    A_sh,w   = 0.08 sqrt(25)/500 x 200 = 0.16 mm²/mm (1.60 cm²/m)
    A_sh,min = max(0.25 x 1.1310, 0.001 x 200) = 0.2827 mm²/mm (2.83 cm²/m)
    A_sv,min = 0.002 x 200 = 0.40 mm²/mm (4.00 cm²/m), A_sv,max = 8.00 mm²/mm
"""

import math
from pathlib import Path

import pandas as pd
import pytest

from mento import set_language
from mento.codes.EN_1992_2004_wall import _check_shear_EN_1992_2004_wall
from mento.forces import Forces
from mento.material import Concrete_ACI_318_19, Concrete_EN_1992_2004, SteelBar
from mento.node import Node
from mento.shear_wall import ShearWall
from mento.shear_wall_summary import ShearWallSummary
from mento.summary_tables import split_single_table
from mento.units import MPa, cm, kN, m, mm

V_RD_C = 156_524.76  # N
V_RD_MAX_FLAT = 1_787_586.2  # N, cot(theta) = 2.5
V_RD_MAX_45 = 2_592_000.0  # N


def _wall(length=4.0 * m, thickness=20 * cm, label="W1") -> ShearWall:
    return ShearWall(
        label=label,
        concrete=Concrete_EN_1992_2004(name="C25/30", f_c=25 * MPa),
        steel_bar=SteelBar(name="B500S", f_y=500 * MPa),
        c_c=25 * mm,
        thickness=thickness,
        length=length,
        height=3 * m,
    )


@pytest.fixture
def wall() -> ShearWall:
    """The Calcpad wall with its default mesh: 2xØ8/200 horizontal, 2xØ12/200 vertical."""
    w = _wall()
    w.set_horizontal_rebar(d_b=8 * mm, s=200 * mm)
    w.set_vertical_rebar(d_b=12 * mm, s=200 * mm)
    return w


# ---------------------------------------------------------------------------
# The check, against the hand calculation above
# ---------------------------------------------------------------------------


class TestCalcpadCase:
    """Reference: Calcpad "HOR_Tabiques_Cortante_EN_1992-1-1_2004_v1", default inputs."""

    def test_section(self, wall: ShearWall) -> None:
        st = _check_shear_EN_1992_2004_wall(wall, Forces(V_z=1200 * kN))
        assert st.A_c == pytest.approx(800_000)
        assert st.d == pytest.approx(3200)
        assert st.z == pytest.approx(2880)
        assert st.k_value == pytest.approx(1.25)
        assert st.f_cd == pytest.approx(16.6667, rel=1e-4)
        assert st.f_ywd == pytest.approx(434.783, rel=1e-5)

    def test_concrete_resistance_is_the_floor_of_eq_6_2b(self, wall: ShearWall) -> None:
        st = _check_shear_EN_1992_2004_wall(wall, Forces(V_z=1200 * kN))
        assert st.rho_l == 0.0
        assert st.V_Rd_c == pytest.approx(V_RD_C, rel=1e-6)

    def test_strut(self, wall: ShearWall) -> None:
        st = _check_shear_EN_1992_2004_wall(wall, Forces(V_z=1200 * kN))
        assert st.alpha_cw == 1.0
        assert st.nu_1 == pytest.approx(0.54)
        assert st.cot_theta == pytest.approx(2.5)
        assert st.V_Rd_max == pytest.approx(V_RD_MAX_FLAT, rel=1e-6)
        assert st.section_shear_limit == pytest.approx(V_RD_MAX_45, rel=1e-9)
        assert st.max_shear_ok

    def test_truss_and_dcr(self, wall: ShearWall) -> None:
        st = _check_shear_EN_1992_2004_wall(wall, Forces(V_z=1200 * kN))
        assert st.V_Rd_s == pytest.approx(1_573_528, rel=1e-6)
        assert st.V_Rd == pytest.approx(st.V_Rd_s)
        assert st.DCR == pytest.approx(1200 / 1573.528, rel=1e-6)

    def test_reinforcement_required(self, wall: ShearWall) -> None:
        st = _check_shear_EN_1992_2004_wall(wall, Forces(V_z=1200 * kN))
        assert st.A_sh == pytest.approx(0.50265, rel=1e-4)
        assert st.A_sv == pytest.approx(1.13097, rel=1e-4)
        assert st.A_sh_str == pytest.approx(0.38333, rel=1e-4)
        assert st.A_sh_w == pytest.approx(0.16)
        assert st.A_sh_min == pytest.approx(0.28274, rel=1e-4)
        assert st.A_sh_req == pytest.approx(st.A_sh_str)
        assert st.A_sv_min == pytest.approx(0.4)
        assert st.A_sv_max == pytest.approx(8.0)
        assert st.s_h_max == 400.0
        assert st.s_v_max == 400.0

    def test_public_result(self, wall: ShearWall) -> None:
        (check,) = wall.shear_check_results([Forces(label="E", V_z=1200 * kN)])
        assert check.V_u.to("kN").magnitude == pytest.approx(1200)
        assert check.V_capacity.to("kN").magnitude == pytest.approx(1573.53, abs=0.01)
        assert check.V_max.to("kN").magnitude == pytest.approx(2592.0)
        assert check.rho_t_req == pytest.approx(0.38333 / 200, rel=1e-4)
        assert check.rho_t_min == pytest.approx(0.28274 / 200, rel=1e-4)
        assert check.rho_l_min == pytest.approx(0.002)
        assert check.rho_l_max == pytest.approx(0.04)
        assert check.s_h_max.to("mm").magnitude == 400
        assert check.DCR == pytest.approx(0.76262, rel=1e-4)
        assert wall.warnings == ()


class TestBranches:
    def test_under_the_concrete_resistance_no_truss_is_asked_for(self, wall: ShearWall) -> None:
        # §6.2.1(3): V_Ed <= V_Rd,c, so neither the truss nor rho_w,min; §9.6.3 governs.
        st = _check_shear_EN_1992_2004_wall(wall, Forces(V_z=100 * kN))
        assert st.A_sh_str == 0.0
        assert st.A_sh_w == 0.0
        assert st.A_sh_req == pytest.approx(st.A_sh_min)
        # The wall resists the larger of V_Rd,c and its truss.
        assert st.V_Rd == pytest.approx(max(V_RD_C, st.V_Rd_s))
        assert st.DCR == pytest.approx(100_000 / st.V_Rd)

    def test_rho_w_min_governs_a_light_truss(self) -> None:
        # Just past V_Rd,c: the truss asks for less than rho_w,min x t = 0.16 mm²/mm.
        w = _wall()
        w.set_vertical_rebar(d_b=10 * mm, s=400 * mm)  # A_sv = 0.39 -> A_sh,min = 0.2
        st = _check_shear_EN_1992_2004_wall(w, Forces(V_z=200 * kN))
        assert st.A_sh_str == pytest.approx(200_000 / (2880 * 500 / 1.15 * 2.5))
        assert st.A_sh_str < st.A_sh_w == pytest.approx(0.16)
        assert st.A_sh_req == pytest.approx(0.2)  # A_sh,min still larger

    def test_the_strut_angle_follows_the_demand(self, wall: ShearWall) -> None:
        # V_Rd,max(cot 2.5) < 2200 kN < V_Rd,max(45°): Eq. (6.9) solved for theta.
        st = _check_shear_EN_1992_2004_wall(wall, Forces(V_z=2200 * kN))
        theta = 0.5 * math.asin(2200 / 2592)
        assert st.theta == pytest.approx(theta)
        assert 1 < st.cot_theta < 2.5
        assert st.V_Rd_max == pytest.approx(2_200_000, rel=1e-9)
        assert st.max_shear_ok

    def test_past_the_strut_the_wall_fails_whatever_its_mesh(self, wall: ShearWall) -> None:
        st = _check_shear_EN_1992_2004_wall(wall, Forces(V_z=3000 * kN))
        assert st.theta == pytest.approx(math.pi / 4)
        assert not st.max_shear_ok
        assert st.V_Rd == pytest.approx(min(st.V_Rd_s, V_RD_MAX_45))
        wall.shear_check_results([Forces(label="E", V_z=3000 * kN)])
        (warning,) = [w for w in wall.warnings if w.code == "shear_exceeds_section_limit"]
        assert warning.values["V_max"].to("kN").magnitude == pytest.approx(2592.0)

    def test_compression_raises_the_concrete_resistance(self, wall: ShearWall) -> None:
        # sigma_cp = 2000/0.8 = 2.5 MPa < 0.2 f_cd = 3.33 MPa
        st = _check_shear_EN_1992_2004_wall(wall, Forces(V_z=100 * kN, N_x=2000 * kN))
        assert st.sigma_cp == pytest.approx(2.5)
        assert st.V_Rd_c == pytest.approx((0.244570 + 0.15 * 2.5) * 200 * 3200, rel=1e-5)
        assert st.alpha_cw == 1.0

    def test_high_compression_is_capped_and_reduces_the_strut(self, wall: ShearWall) -> None:
        # sigma_c0 = 12000/0.8 = 15 MPa: sigma_cp capped at 0.2 f_cd, alpha_cw = 2.5 (1 - 15/16.667) = 0.25
        st = _check_shear_EN_1992_2004_wall(wall, Forces(V_z=100 * kN, N_x=12_000 * kN))
        assert st.sigma_cp == pytest.approx(0.2 * 25 / 1.5)
        assert st.alpha_cw == pytest.approx(0.25)
        assert st.section_shear_limit == pytest.approx(0.25 * V_RD_MAX_45)

    def test_tension_lowers_the_concrete_resistance(self, wall: ShearWall) -> None:
        # sigma_cp = -1000/0.8 = -1.25 MPa
        st = _check_shear_EN_1992_2004_wall(wall, Forces(V_z=100 * kN, N_x=-1000 * kN))
        assert st.sigma_cp == pytest.approx(-1.25)
        assert st.V_Rd_c == pytest.approx((0.244570 - 0.15 * 1.25) * 200 * 3200, rel=1e-5)
        assert st.alpha_cw == 1.0

    def test_a_wall_with_no_horizontal_mesh_resists_with_its_concrete(self) -> None:
        w = _wall()
        st = _check_shear_EN_1992_2004_wall(w, Forces(V_z=300 * kN))
        assert st.V_Rd_s == 0.0
        assert st.V_Rd == pytest.approx(V_RD_C, rel=1e-6)
        assert st.DCR == pytest.approx(300_000 / V_RD_C, rel=1e-6)

    def test_the_shear_sign_does_not_matter(self, wall: ShearWall) -> None:
        a = _check_shear_EN_1992_2004_wall(wall, Forces(V_z=1200 * kN))
        b = _check_shear_EN_1992_2004_wall(wall, Forces(V_z=-1200 * kN))
        assert a.DCR == pytest.approx(b.DCR)

    def test_the_check_rejects_another_codes_concrete(self) -> None:
        w = ShearWall(
            label="W",
            concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
            steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
            c_c=25 * mm,
            thickness=20 * cm,
            length=4 * m,
            height=3 * m,
        )
        with pytest.raises(TypeError):
            _check_shear_EN_1992_2004_wall(w, Forces(V_z=100 * kN))

    def test_the_wall_height_does_not_enter(self, wall: ShearWall) -> None:
        tall = _wall()
        tall.height = 30 * m
        tall.set_horizontal_rebar(d_b=8 * mm, s=200 * mm)
        tall.set_vertical_rebar(d_b=12 * mm, s=200 * mm)
        f = Forces(V_z=1200 * kN)
        assert _check_shear_EN_1992_2004_wall(tall, f).DCR == _check_shear_EN_1992_2004_wall(wall, f).DCR

    def test_a_thin_wall_takes_3t_as_its_vertical_spacing(self) -> None:
        st = _check_shear_EN_1992_2004_wall(_wall(thickness=12 * cm), Forces(V_z=100 * kN))
        assert st.s_v_max == pytest.approx(360)


# ---------------------------------------------------------------------------
# Design
# ---------------------------------------------------------------------------


class TestDesign:
    def test_the_calcpad_wall(self) -> None:
        # Vertical first: rho = 0.002 at s <= 400 mm, Ø10 the smallest bar -> Ø10/37.
        # Horizontal: A_sh,req = A_sh,str = 3.83 cm²/m (A_sh,min = max(0.25 x 4.25, 2.0) = 2.0) -> Ø8/25.
        w = _wall()
        w.design([Forces(label="E", V_z=1200 * kN)])
        assert w.mesh.vertical.d_b == 10 * mm
        assert w.mesh.vertical.s.to("cm").magnitude == pytest.approx(37)
        assert w.mesh.horizontal.d_b == 8 * mm
        assert w.mesh.horizontal.s.to("cm").magnitude == pytest.approx(25)
        design = w.shear_design
        assert design.DCR == pytest.approx(1200 / (0.402124 * 2880 * 434.7826 * 2.5 / 1000), rel=1e-4)
        assert design.DCR <= 1
        assert w.warnings == ()

    def test_low_shear_designs_to_the_minima(self) -> None:
        # V_Ed <= V_Rd,c: A_sh,req = A_sh,min = 0.001 t = 2 cm²/m -> Ø6/27 (rho = 0.00105).
        w = _wall()
        w.design([Forces(V_z=100 * kN)])
        assert w.mesh.horizontal.d_b == 6 * mm
        assert w.mesh.horizontal.rho >= 0.001
        assert w.mesh.vertical.rho >= 0.002
        assert w.warnings == ()

    def test_the_catalogue_floors(self) -> None:
        # CIRSOC's: Ø6 and up horizontal, Ø10 and up vertical.
        from mento.codes import EN_1992_2004_wall as en_wall

        assert min(en_wall._EN_WALL_BARS_HORIZONTAL) == 6 * mm
        assert min(en_wall._EN_WALL_BARS_VERTICAL) == 10 * mm

    def test_the_design_meets_every_limit_it_checks(self) -> None:
        w = _wall(length=6 * m, thickness=30 * cm)
        forces = [Forces(label="1", V_z=900 * kN), Forces(label="2", V_z=2400 * kN, N_x=-500 * kN)]
        w.design(forces)
        for check in w.shear_checks:
            assert check.DCR <= 1
            assert check.mesh.horizontal.rho >= check.rho_t_req - 1e-12
            assert check.mesh.vertical.rho >= check.rho_l_min - 1e-12
            assert check.mesh.horizontal.s <= check.s_h_max
            assert check.mesh.vertical.s <= check.s_v_max
        assert w.warnings == ()

    def test_the_design_takes_the_worst_combination(self) -> None:
        alone = _wall()
        alone.design([Forces(V_z=1800 * kN)])
        both = _wall()
        both.design([Forces(V_z=200 * kN), Forces(V_z=1800 * kN)])
        assert both.mesh == alone.mesh

    def test_designing_twice_gives_the_same_mesh(self) -> None:
        w = _wall()
        forces = [Forces(V_z=1500 * kN)]
        w.design(forces)
        first = w.mesh
        w.design(forces)
        assert w.mesh == first

    def test_design_needs_forces(self) -> None:
        from mento.codes.EN_1992_2004_wall import _design_shear_EN_1992_2004_wall

        with pytest.raises(ValueError):
            _design_shear_EN_1992_2004_wall(_wall(), [])

    def test_through_a_node(self) -> None:
        w = _wall()
        node = Node(section=w, forces=[Forces(label="E", V_z=1200 * kN)])
        node.design()
        assert w.shear_design.DCR <= 1
        assert node.warnings == ()


# ---------------------------------------------------------------------------
# Warnings
# ---------------------------------------------------------------------------


def _codes(wall: ShearWall) -> set:
    return {w.code for w in wall.warnings}


class TestWarnings:
    def test_vertical_mesh_above_the_maximum(self) -> None:
        w = _wall()
        w.set_horizontal_rebar(d_b=8 * mm, s=200 * mm)
        w.set_vertical_rebar(d_b=25 * mm, s=50 * mm)  # rho = 2 x 490.9/(200 x 50) = 0.098
        w.shear_check_results([Forces(V_z=100 * kN)])
        (warning,) = [x for x in w.warnings if x.code == "mesh_ratio_above_max"]
        assert warning.values["rho_max"] == pytest.approx(0.04)
        assert warning.message == "Vertical wall mesh: ρl = 0.0982 exceeds the maximum ρl,max = 0.04."

    def test_vertical_mesh_below_the_minimum(self) -> None:
        w = _wall()
        w.set_horizontal_rebar(d_b=8 * mm, s=200 * mm)
        w.set_vertical_rebar(d_b=8 * mm, s=400 * mm)  # rho = 0.00126 < 0.002
        w.shear_check_results([Forces(V_z=100 * kN)])
        assert "mesh_ratio_below_min" in _codes(w)

    def test_the_spacing_warnings_quote_the_eurocode(self) -> None:
        w = _wall()
        w.set_horizontal_rebar(d_b=12 * mm, s=450 * mm)
        w.set_vertical_rebar(d_b=16 * mm, s=450 * mm)
        w.shear_check_results([Forces(V_z=100 * kN)])
        messages = {x.values["direction"]: x.message for x in w.warnings if x.code == "mesh_spacing_exceeds_max"}
        assert messages["h"] == "Horizontal wall mesh spacing: 45 cm exceeds the maximum 40 cm (§9.6.3(2))."
        assert messages["v"] == "Vertical wall mesh spacing: 45 cm exceeds the maximum 40 cm (§9.6.2(3))."

    def test_the_spacing_warnings_in_spanish(self) -> None:
        w = _wall()
        w.set_horizontal_rebar(d_b=12 * mm, s=450 * mm)
        w.set_vertical_rebar(d_b=16 * mm, s=200 * mm)
        w.shear_check_results([Forces(V_z=100 * kN)])
        set_language("es")
        try:
            (warning,) = [x for x in w.warnings if x.code == "mesh_spacing_exceeds_max"]
            assert warning.message == (
                "Separación de la malla horizontal del muro: 45 cm supera la máxima 40 cm (§9.6.3(2))."
            )
        finally:
            set_language("en")

    def test_an_aci_wall_names_no_vertical_maximum(self) -> None:
        w = ShearWall(
            label="W",
            concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
            steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
            c_c=25 * mm,
            thickness=20 * cm,
            length=4 * m,
            height=3 * m,
        )
        w.set_horizontal_rebar(d_b=10 * mm, s=200 * mm)
        w.set_vertical_rebar(d_b=25 * mm, s=50 * mm)
        (check,) = w.shear_check_results([Forces(V_z=100 * kN)])
        assert check.rho_l_max is None
        assert "mesh_ratio_above_max" not in _codes(w)


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


class TestReports:
    def test_check_table_in_eurocode_notation(self, wall: ShearWall) -> None:
        table = wall.check_shear([Forces(label="E", V_z=1200 * kN)])
        assert list(table.columns) == [
            "Label",
            "Comb.",
            "Ash,min",
            "Ash,req",
            "Ash",
            "Asv,min",
            "Asv",
            "NEd",
            "VEd",
            "VRd,c",
            "VRd,s",
            "VRd",
            "VRd,max",
            "VEd≤VRd,max",
            "VEd≤VRd",
            "DCR",
        ]
        units, row = table.iloc[0], table.iloc[1]
        assert units["Ash"] == "cm²/m" and units["VRd"] == "kN"
        assert row["Ash,req"] == pytest.approx(3.83)
        assert row["Ash,min"] == pytest.approx(2.83)
        assert row["Ash"] == pytest.approx(5.03)
        assert row["Asv,min"] == pytest.approx(4.0)
        assert row["VRd,c"] == pytest.approx(156.52)
        assert row["VRd,s"] == pytest.approx(1573.53)
        assert row["VRd,max"] == pytest.approx(1787.59)
        assert row["DCR"] == pytest.approx(0.763)
        assert bool(row["VEd≤VRd"]) and bool(row["VEd≤VRd,max"])

    def test_detail_tables(self, wall: ShearWall, capsys: pytest.CaptureFixture) -> None:
        wall.check_shear([Forces(label="E", V_z=1200 * kN)])
        wall.shear_results_detailed()
        out = capsys.readouterr().out
        for text in ("fck", "fywd", "Lever arm", "αcw", "VRd,c", "Ash,str", "Length to thickness ratio", "DCR"):
            assert text in out
        assert wall._all_wall_shear_checks_passed

    def test_a_short_wall_is_flagged(self) -> None:
        # l_w / t = 0.6 / 0.2 = 3 < 4: a column under §5.3.1(7).
        w = _wall(length=0.6 * m)
        w.set_horizontal_rebar(d_b=8 * mm, s=200 * mm)
        w.set_vertical_rebar(d_b=12 * mm, s=200 * mm)
        w.check_shear([Forces(V_z=10 * kN)])
        limits = w._data_min_max_wall
        row = limits["Check"].index("Length to thickness ratio")
        assert limits["Value"][row] == pytest.approx(3.0)
        assert limits["Ok?"][row] == "❌"
        assert not w._all_wall_shear_checks_passed

    def test_markdown_summary(self, wall: ShearWall) -> None:
        wall.check_shear([Forces(label="E", V_z=1200 * kN)])
        wall.shear_results
        md = wall._md_shear_results
        assert "$\\rho_h$=0.00251" in md
        assert "$\\rho_v$=0.00565" in md
        assert "$V_{Ed}$=1200.0 kN" in md
        assert "$V_{Rd}$=1573.53 kN" in md

    def test_word_document(self, wall: ShearWall, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        wall.check_shear([Forces(label="E", V_z=1200 * kN)])
        wall.shear_results_detailed_doc()
        assert (tmp_path / "Shear Wall W1 shear check EN 1992-2004.docx").exists()

    def test_a_code_with_wall_hooks_but_no_wall_tables_says_so(self, wall: ShearWall) -> None:
        """Registering the hooks is not writing the tables, as for a beam: the error names what is missing."""
        import dataclasses

        from mento.codes.registry import _REGISTRY, design_code, register

        invented = dataclasses.replace(design_code(wall.concrete), title="NBR 6118-2023")
        register(invented)
        try:
            wall.concrete.design_code = invented.title
            # The check itself runs: the hooks are EN's.
            assert wall.shear_check_results([Forces(V_z=1200 * kN)])[0].DCR == pytest.approx(0.7626, rel=1e-4)
            with pytest.raises(NotImplementedError, match="no wall report tables for design code: NBR 6118-2023"):
                wall.check_shear([Forces(V_z=1200 * kN)])
        finally:
            _REGISTRY.pop(invented.title, None)


# ---------------------------------------------------------------------------
# Summary of several walls
# ---------------------------------------------------------------------------


def _wall_list() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Level": ["", "L1", "L1", "L2"],
            "Label": ["", "M1", "M1", "M2"],
            "Comb.": ["", "ULS 1", "ULS 2", "ULS 1"],
            "t": ["cm", 20, 20, 20],
            "lw": ["m", 4.0, 4.0, 2.0],
            "hw": ["m", 3.0, 3.0, 3.0],
            "cc": ["mm", 25, 25, 25],
            "Nx": ["kN", 0, -300, 50],
            "Vz": ["kN", 1200, 600, 300],
            "My": ["kNm", 0, 0, 0],
            "dbh": ["mm", 8, 8, 0],
            "sh": ["cm", 20, 20, 0],
            "dbv": ["mm", 12, 12, 0],
            "sv": ["cm", 20, 20, 0],
        }
    )


class TestSummary:
    def test_design_then_check(self) -> None:
        summary = ShearWallSummary(
            Concrete_EN_1992_2004(name="C25/30", f_c=25 * MPa),
            SteelBar(name="B500S", f_y=500 * MPa),
            *split_single_table(_wall_list(), "wall"),
        )
        summary.design()
        table = summary.check()
        assert {"ρh", "ρv", "VEd", "NEd", "VRd"} <= set(table.columns)
        assert "ØVn" not in table.columns
        assert list(table["Status"].iloc[1:]) == ["✅", "✅"]
        first = table.iloc[1]
        assert first["VEd"] == pytest.approx(1200.0)

    def test_check_columns_carry_units(self) -> None:
        summary = ShearWallSummary(
            Concrete_EN_1992_2004(name="C25/30", f_c=25 * MPa),
            SteelBar(name="B500S", f_y=500 * MPa),
            *split_single_table(_wall_list(), "wall"),
        )
        summary.design()
        units = summary.check().iloc[0]
        assert units["VEd"] == "kN" and units["VRd"] == "kN"
