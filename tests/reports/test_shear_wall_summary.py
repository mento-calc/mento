"""Tests for ShearWallSummary class."""

import math
import os

import pandas as pd
import pytest

from mento import Concrete_ACI_318_19, MPa, ShearWallSummary, SteelBar, ksi, psi
from mento.units import cm, mm


def test_export_converts_design_to_declared_units(tmp_path, concrete, sample_df):
    summary = ShearWallSummary(concrete, SteelBar(name="ADN420", f_y=420 * MPa), sample_df)
    summary.design_data = summary.data.copy()
    # The design may produce cm while the original table declares mm.
    summary.design_data["cc"] = 2.5 * cm
    path = tmp_path / "mixed_units.xlsx"
    summary.export_design(str(path))
    exported = pd.read_excel(path)
    assert exported.iloc[0]["cc"] == "mm"
    assert exported.iloc[1:]["cc"].astype(float).tolist() == [25.0] * (len(exported) - 1)
    assert summary.design_data.iloc[0]["cc"] == 25 * mm
    imported = ShearWallSummary(concrete, summary.steel_bar, exported)
    assert imported.data.iloc[0]["cc"] == 25 * mm


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture
def concrete():
    return Concrete_ACI_318_19(name="H25", f_c=25 * MPa)


@pytest.fixture
def sample_df():
    """DataFrame with 4 walls: (Level 1, M1), (Level 2, M1), (Level 1, M2), (Level 2, M2)."""
    data = {
        "Level": [
            "",
            "Level 1",
            "Level 1",
            "Level 1",
            "Level 1",
            "Level 2",
            "Level 2",
            "Level 2",
            "Level 2",
            "Level 1",
            "Level 1",
            "Level 1",
            "Level 1",
            "Level 2",
            "Level 2",
            "Level 2",
            "Level 2",
        ],
        "Label": ["", "M1", "M1", "M1", "M1", "M1", "M1", "M1", "M1", "M2", "M2", "M2", "M2", "M2", "M2", "M2", "M2"],
        "Comb.": [
            "",
            "ELU 1",
            "ELU 2",
            "ELU 3",
            "ELU 4",
            "ELU 1",
            "ELU 2",
            "ELU 3",
            "ELU 4",
            "ELU 1",
            "ELU 2",
            "ELU 3",
            "ELU 4",
            "ELU 1",
            "ELU 2",
            "ELU 3",
            "ELU 4",
        ],
        "t": ["cm", 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20],
        "lw": ["m", 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0],
        "hw": ["m", 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0],
        "cc": ["mm", 25, 25, 25, 25, 25, 25, 25, 25, 25, 25, 25, 25, 25, 25, 25, 25],
        "Nx": ["kN", 0, 0, 0, -301, -150, 55.5, 282, -4.5, -240, -163, -17, 332, -150, 55.5, -163, 55.5],
        "Vz": ["kN", 264, 138, 123, 152, 32.3, 163, 19, 88.15, 61.2, 29, 47, 21, 32.3, 163, 29, 163],
        "My": ["kNm", -172, -90, -81, -234, 143, -278, 159, -97, -38, 60, -39, 46.13, 143, -278, 60, -278],
        "dbh": ["mm", 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8],
        "sh": ["cm", 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20],
        "dbv": ["mm", 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12],
        "sv": ["cm", 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15],
    }
    return pd.DataFrame(data)


@pytest.fixture
def sample_df_no_rebar():
    """Same as sample_df but with no rebar assigned."""
    data = {
        "Level": ["", "Level 1", "Level 1", "Level 2", "Level 2"],
        "Label": ["", "M1", "M1", "M1", "M1"],
        "Comb.": ["", "ELU 1", "ELU 2", "ELU 1", "ELU 2"],
        "t": ["cm", 20, 20, 20, 20],
        "lw": ["m", 3.0, 3.0, 3.0, 3.0],
        "hw": ["m", 3.0, 3.0, 3.0, 3.0],
        "cc": ["mm", 25, 25, 25, 25],
        "Nx": ["kN", 0, -301, -150, 55.5],
        "Vz": ["kN", 264, 152, 32.3, 163],
        "My": ["kNm", -172, -234, 143, -278],
        "dbh": ["mm", 0, 0, 0, 0],
        "sh": ["cm", 0, 0, 0, 0],
        "dbv": ["mm", 0, 0, 0, 0],
        "sv": ["cm", 0, 0, 0, 0],
    }
    return pd.DataFrame(data)


@pytest.fixture
def summary(concrete, steel, sample_df):
    return ShearWallSummary(concrete=concrete, steel_bar=steel, wall_list=sample_df)


# ------------------------------------------------------------------
# Init / Grouping
# ------------------------------------------------------------------


class TestShearWallSummaryInit:
    def test_correct_number_of_nodes(self, summary):
        assert len(summary.nodes) == 4

    def test_wall_keys(self, summary):
        assert summary.wall_keys == [
            ("Level 1", "M1"),
            ("Level 2", "M1"),
            ("Level 1", "M2"),
            ("Level 2", "M2"),
        ]

    def test_forces_per_node(self, summary):
        for node in summary.nodes:
            assert len(node.forces) == 4

    def test_wall_level_attribute(self, summary):
        wall_0 = summary.nodes[0].section
        assert wall_0.level == "Level 1"
        wall_1 = summary.nodes[1].section
        assert wall_1.level == "Level 2"

    def test_wall_label_attribute(self, summary):
        wall_0 = summary.nodes[0].section
        assert wall_0.label == "M1"
        wall_2 = summary.nodes[2].section
        assert wall_2.label == "M2"

    def test_wall_geometry(self, summary):
        wall = summary.nodes[0].section
        assert wall.thickness.to("cm").magnitude == pytest.approx(20)
        assert wall.length.to("m").magnitude == pytest.approx(3.0)
        assert wall.height.to("m").magnitude == pytest.approx(3.0)

    def test_rebar_set(self, summary):
        wall = summary.nodes[0].section
        assert wall._d_b_h.to("mm").magnitude == pytest.approx(8)
        assert wall._s_h.to("cm").magnitude == pytest.approx(20)
        assert wall._d_b_v.to("mm").magnitude == pytest.approx(12)
        assert wall._s_v.to("cm").magnitude == pytest.approx(15)

    def test_no_rebar_walls(self, concrete, steel, sample_df_no_rebar):
        s = ShearWallSummary(concrete=concrete, steel_bar=steel, wall_list=sample_df_no_rebar)
        wall = s.nodes[0].section
        assert wall._d_b_h.magnitude == 0  # type: ignore
        assert wall._d_b_v.magnitude == 0  # type: ignore


# ------------------------------------------------------------------
# Input validation
# ------------------------------------------------------------------


class TestShearWallSummaryValidation:
    def test_invalid_units(self, concrete: Concrete_ACI_318_19, steel: SteelBar):
        data = {
            "Level": [""],
            "Label": [""],
            "Comb.": [""],
            "t": ["parsecs"],
            "lw": ["m"],
            "hw": ["m"],
            "cc": ["mm"],
            "Nx": ["kN"],
            "Vz": ["kN"],
            "My": ["kNm"],
            "dbh": ["mm"],
            "sh": ["cm"],
            "dbv": ["mm"],
            "sv": ["cm"],
        }
        df = pd.DataFrame(data)
        with pytest.raises(ValueError, match="Invalid unit"):
            ShearWallSummary(concrete=concrete, steel_bar=steel, wall_list=df)

    def test_geometry_mismatch_raises(self, concrete: Concrete_ACI_318_19, steel: SteelBar):
        data = {
            "Level": ["", "Level 1", "Level 1"],
            "Label": ["", "M1", "M1"],
            "Comb.": ["", "ELU 1", "ELU 2"],
            "t": ["cm", 20, 25],  # mismatch!
            "lw": ["m", 3.0, 3.0],
            "hw": ["m", 3.0, 3.0],
            "cc": ["mm", 25, 25],
            "Nx": ["kN", 0, 0],
            "Vz": ["kN", 264, 138],
            "My": ["kNm", -172, -90],
            "dbh": ["mm", 8, 8],
            "sh": ["cm", 20, 20],
            "dbv": ["mm", 12, 12],
            "sv": ["cm", 15, 15],
        }
        df = pd.DataFrame(data)
        with pytest.raises(ValueError, match="Geometry mismatch"):
            ShearWallSummary(concrete=concrete, steel_bar=steel, wall_list=df)


# ------------------------------------------------------------------
# Check
# ------------------------------------------------------------------


class TestShearWallSummaryCheck:
    def test_check_returns_correct_rows(self, summary):
        df = summary.check()
        # 1 units row + 4 wall rows
        assert len(df) == 5

    def test_check_has_dcr_column(self, summary):
        df = summary.check()
        assert "DCR" in df.columns

    def test_check_has_status_column(self, summary):
        df = summary.check()
        assert "Status" in df.columns
        # All should pass for this input
        statuses = df["Status"].iloc[1:].tolist()
        assert all(s == "✅" for s in statuses)

    def test_check_dcr_values(self, summary):
        df = summary.check()
        dcr_values = df["DCR"].iloc[1:].tolist()
        for dcr in dcr_values:
            assert 0 < dcr < 1

    def test_check_raises_without_rebar(self, concrete, steel, sample_df_no_rebar):
        s = ShearWallSummary(concrete=concrete, steel_bar=steel, wall_list=sample_df_no_rebar)
        with pytest.raises(ValueError, match="no horizontal rebar"):
            s.check()


def _two_combination_wall(shears, s_h=15, d_b_h=12, s_v=20, d_b_v=10):
    """One wall, 25×400 cm, hw 3.5 m, Ø12/15 + Ø10/20 E.F., with two shear rows in the order given."""
    data = {
        "Level": ["", "L1", "L1"],
        "Label": ["", "W1", "W1"],
        "Comb.": ["", "F1", "F2"],
        "t": ["cm", 25, 25],
        "lw": ["m", 4.0, 4.0],
        "hw": ["m", 3.5, 3.5],
        "cc": ["mm", 20, 20],
        "Nx": ["kN", 0, 0],
        "Vz": ["kN", shears[0], shears[1]],
        "My": ["kNm", 0, 0],
        "dbh": ["mm", d_b_h, d_b_h],
        "sh": ["cm", s_h, s_h],
        "dbv": ["mm", d_b_v, d_b_v],
        "sv": ["cm", s_v, s_v],
    }
    return pd.DataFrame(data)


class TestShearWallSummaryStatusSpansEveryCombination:
    @pytest.mark.parametrize("shears", [(2400, 1000), (1000, 2400)])
    def test_status_fails_when_any_combination_misses_a_limit(self, concrete, steel, shears):
        """A wall that misses ρl,min under one combination is ❌ whichever row comes last.

        ACI 318-19 §11.6.2(a), by hand (hw/lw = 0.875, αc = 0.25, Acv = 1.0 m²):
            Ø12/15 E.F.: ρt = 0.0060319; Ø10/20 E.F.: ρl = 2·78.54/(250·200) = 0.0031416
            Vu = 2400 kN: ρt,req = (2400/0.75 − 1250)/(420·1000) = 0.0046429
                Eq. (11.6.2) = 0.0025 + 0.8125·(0.0060319 − 0.0025) = 0.0053697
                ρl,min = min(0.0053697, 0.0046429) = 0.0046429 > ρl  → missed
                ØVn = 0.75·min(1250 + 2533.4, 3300) = 2475 kN, DCR = 0.970
            Vu = 1000 kN: ρt,req = 0.0025 → ρl,min = 0.0025 ≤ ρl  → met, DCR 0.404
        The summary used to read the pass flag of the last combination checked,
        so the (2400, 1000) order came out ✅ at DCR 0.97.
        """
        summary = ShearWallSummary(concrete=concrete, steel_bar=steel, wall_list=_two_combination_wall(shears))
        row = summary.check().iloc[1]
        assert row["DCR"] == pytest.approx(0.970, abs=1e-3)
        assert row["Status"] == "❌"
        wall = summary.nodes[0].section
        assert [w.code for w in wall.warnings] == ["mesh_ratio_below_min"]

    def test_status_passes_when_every_combination_does(self, concrete, steel):
        """The same wall under shears both combinations carry with ρl,min = 0.0025 is ✅."""
        summary = ShearWallSummary(concrete=concrete, steel_bar=steel, wall_list=_two_combination_wall((1000, 800)))
        row = summary.check().iloc[1]
        assert row["DCR"] == pytest.approx(0.404, abs=1e-3)
        assert row["Status"] == "✅"

    def test_status_fails_on_a_spacing_the_code_does_not_allow(self, concrete, steel):
        """A mesh past the 450 mm cap of ACI 318-19 §11.7.3.1 is ❌ however low its DCR.

        Ø20/50 E.F.: ρt = 2·314.16/(250·500) = 0.0050265 ≥ 0.0025, but s = 500 mm >
        s_h,max = min(4000/5, 3·250, 450) = 450 mm. Vu = 500 kN gives DCR = 500/2475 = 0.202.
        The old flag left the spacing rows out, so this wall was ✅.
        """
        wall_list = _two_combination_wall((500, 400), s_h=50, d_b_h=20)
        summary = ShearWallSummary(concrete=concrete, steel_bar=steel, wall_list=wall_list)
        row = summary.check().iloc[1]
        assert row["DCR"] == pytest.approx(0.202, abs=1e-3)
        assert row["Status"] == "❌"
        wall = summary.nodes[0].section
        assert [w.code for w in wall.warnings] == ["mesh_spacing_exceeds_max"]

    def test_a_wall_at_its_section_limit_passes_whatever_the_rounding(self, concrete, steel):
        """Vu = ØVn,max worked out apart, as a program feeding the summary would: ✅, no warning.

        ACI 318-19 §11.5.4.2, Acv = 250·4000 = 1.0e6 mm²: ØVn,max =
        0.75·0.66·√25·Acv = 2475 kN, which in floating point comes out
        2475.0000000000005 kN. Ø10/10 E.F. (ρt = 2·78.54/(250·100) = 0.0062832)
        carry 0.75·(1250 + 2638.9) = 2916.7 kN, capped at 2475; ρt,req =
        (3300 − 1250)/(420·1000) = 0.0048810, and Ø12/15 E.F. (ρl = 0.0060319)
        meet ρl,min = min(0.0025 + 0.8125·(0.0062832 − 0.0025), 0.0048810) =
        0.0048810. The DCR is 1 but for the last bit, 1.0000000000000002. The
        wall trigger compared V_u > V_max bare, where the beam's ignores a
        difference ``math.isclose`` calls none, so the wall raised
        ``shear_exceeds_section_limit`` and the summary's ``DCR <= 1`` made it ❌
        (both already in PR #164).
        """
        V_u = 0.75 * (0.66 * math.sqrt(25.0) * 250.0 * 4000.0) * 1e-3
        assert V_u > 2475.0
        wall_list = _two_combination_wall((V_u, 1000), s_h=10, d_b_h=10, s_v=15, d_b_v=12)
        summary = ShearWallSummary(concrete=concrete, steel_bar=steel, wall_list=wall_list)
        row = summary.check().iloc[1]
        wall = summary.nodes[0].section
        assert max(check.DCR for check in wall.shear_checks) > 1.0
        assert wall.warnings == ()
        assert row["Status"] == "✅"
        # Past the limit by more than rounding still fails, and says why.
        over = ShearWallSummary(
            concrete=concrete, steel_bar=steel, wall_list=_two_combination_wall((2476, 1000), 10, 10, 15, 12)
        )
        assert over.check().iloc[1]["Status"] == "❌"
        assert [w.code for w in over.nodes[0].section.warnings] == ["shear_exceeds_section_limit"]


# ------------------------------------------------------------------
# Design
# ------------------------------------------------------------------


class TestShearWallSummaryDesign:
    def test_design_returns_dataframe(self, concrete, steel, sample_df_no_rebar):
        s = ShearWallSummary(concrete=concrete, steel_bar=steel, wall_list=sample_df_no_rebar)
        result = s.design()
        assert isinstance(result, pd.DataFrame)

    def test_design_fills_rebar(self, concrete, steel, sample_df_no_rebar):
        s = ShearWallSummary(concrete=concrete, steel_bar=steel, wall_list=sample_df_no_rebar)
        s.design()
        wall = s.nodes[0].section
        assert wall._d_b_h.to("mm").magnitude > 0  # type: ignore
        assert wall._s_h.to("cm").magnitude > 0  # type: ignore
        assert wall._d_b_v.to("mm").magnitude > 0  # type: ignore
        assert wall._s_v.to("cm").magnitude > 0  # type: ignore

    def test_design_sets_design_data(self, concrete, steel, sample_df_no_rebar):
        s = ShearWallSummary(concrete=concrete, steel_bar=steel, wall_list=sample_df_no_rebar)
        s.design()
        assert hasattr(s, "design_data")

    def test_check_after_design_passes(self, concrete, steel, sample_df_no_rebar):
        s = ShearWallSummary(concrete=concrete, steel_bar=steel, wall_list=sample_df_no_rebar)
        s.design()
        df = s.check()
        statuses = df["Status"].iloc[1:].tolist()
        assert all(s == "✅" for s in statuses)


# ------------------------------------------------------------------
# Shear results
# ------------------------------------------------------------------


class TestShearWallSummaryShearResults:
    def test_shear_results_all(self, summary):
        df = summary.shear_results()
        # 1 units row + 16 data rows (4 walls × 4 combos)
        assert len(df) == 17

    def test_shear_results_single(self, summary):
        df = summary.shear_results(index=1)
        # 1 units row + 4 combos for wall 1
        assert len(df) == 5

    def test_shear_results_index_out_of_range(self, summary):
        with pytest.raises(IndexError):
            summary.shear_results(index=99)

    def test_shear_results_index_zero(self, summary):
        with pytest.raises(IndexError):
            summary.shear_results(index=0)

    def test_shear_results_has_dcr(self, summary):
        df = summary.shear_results(index=1)
        assert "DCR" in df.columns


# ------------------------------------------------------------------
# Export / Import
# ------------------------------------------------------------------


class TestShearWallSummaryExportImport:
    def test_export_without_design_raises(self, summary):
        with pytest.raises(AttributeError, match="No design data"):
            summary.export_design("test.xlsx")

    def test_export_import_roundtrip(self, concrete, steel, sample_df_no_rebar, tmp_path):
        s = ShearWallSummary(concrete=concrete, steel_bar=steel, wall_list=sample_df_no_rebar)
        s.design()

        path = str(tmp_path / "walls.xlsx")
        s.export_design(path)
        assert os.path.exists(path)

        s.import_design(path)
        assert len(s.nodes) == 2  # 2 walls: (Level 1, M1) and (Level 2, M1)

    def test_reimport_check_matches(self, concrete, steel, sample_df_no_rebar, tmp_path):
        s = ShearWallSummary(concrete=concrete, steel_bar=steel, wall_list=sample_df_no_rebar)
        s.design()
        check_before = s.check()

        path = str(tmp_path / "walls.xlsx")
        s.export_design(path)
        s.import_design(path)
        check_after = s.check()

        dcr_before = check_before["DCR"].iloc[1:].tolist()
        dcr_after = check_after["DCR"].iloc[1:].tolist()
        for a, b in zip(dcr_before, dcr_after):
            assert abs(a - b) < 0.01


# ------------------------------------------------------------------
# Word export
# ------------------------------------------------------------------


class TestShearWallSummaryDoc:
    def test_results_detailed_doc(self, summary, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        summary.results_detailed_doc(index=1)
        expected_file = tmp_path / f"Shear_Wall_Summary_{summary.concrete.design_code}.docx"
        assert expected_file.exists()

    def test_results_detailed_doc_index_out_of_range(self, summary):
        with pytest.raises(IndexError):
            summary.results_detailed_doc(index=99)


# ------------------------------------------------------------------
# Level attribute
# ------------------------------------------------------------------


class TestShearWallLevel:
    def test_level_stored_on_wall(self, summary):
        for i, node in enumerate(summary.nodes):
            wall = node.section
            expected_level = summary.wall_keys[i][0]
            assert wall.level == expected_level


# ------------------------------------------------------------------
# Coverage: unrecognized unit (line 70)
# ------------------------------------------------------------------


class TestShearWallSummaryGetUnitVariable:
    def test_unrecognized_unit_raises(self, concrete, steel):
        data = {
            "Level": ["", "Level 1"],
            "Label": ["", "M1"],
            "Comb.": ["", "ELU 1"],
            "t": ["furlongs", 20],
            "lw": ["m", 3.0],
            "hw": ["m", 3.0],
            "cc": ["mm", 25],
            "Nx": ["kN", 0],
            "Vz": ["kN", 264],
            "My": ["kNm", -172],
            "dbh": ["mm", 8],
            "sh": ["cm", 20],
            "dbv": ["mm", 12],
            "sv": ["cm", 15],
        }
        df = pd.DataFrame(data)
        with pytest.raises(ValueError, match="Invalid unit"):
            ShearWallSummary(concrete=concrete, steel_bar=steel, wall_list=df)

    def test_get_unit_variable_unrecognized(self, summary):
        with pytest.raises(ValueError, match="not recognized"):
            summary.get_unit_variable("parsecs")


# ------------------------------------------------------------------
# Coverage: missing vertical rebar only (line 162)
# ------------------------------------------------------------------


class TestShearWallSummaryCheckVerticalMissing:
    def test_check_raises_missing_vertical_rebar(self, concrete, steel):
        data = {
            "Level": ["", "Level 1"],
            "Label": ["", "M1"],
            "Comb.": ["", "ELU 1"],
            "t": ["cm", 20],
            "lw": ["m", 3.0],
            "hw": ["m", 3.0],
            "cc": ["mm", 25],
            "Nx": ["kN", 0],
            "Vz": ["kN", 264],
            "My": ["kNm", -172],
            "dbh": ["mm", 8],
            "sh": ["cm", 20],
            "dbv": ["mm", 0],
            "sv": ["cm", 0],
        }
        df = pd.DataFrame(data)
        s = ShearWallSummary(concrete=concrete, steel_bar=steel, wall_list=df)
        with pytest.raises(ValueError, match="no vertical rebar"):
            s.check()


# ------------------------------------------------------------------
# Coverage: imperial unit branch (line 205)
# ------------------------------------------------------------------


class TestShearWallSummaryImperial:
    def test_check_imperial_units(self):
        concrete_imp = Concrete_ACI_318_19(name="C4000", f_c=4000 * psi)
        steel_imp = SteelBar(name="G60", f_y=60 * ksi)
        data = {
            "Level": ["", "Level 1"],
            "Label": ["", "W1"],
            "Comb.": ["", "ELU 1"],
            "t": ["inch", 10],
            "lw": ["ft", 12],
            "hw": ["ft", 10],
            "cc": ["inch", 1.5],
            "Nx": ["kN", 0],
            "Vz": ["kN", 200],
            "My": ["kNm", 0],
            "dbh": ["inch", 0.5],
            "sh": ["inch", 8],
            "dbv": ["inch", 0.5],
            "sv": ["inch", 8],
        }
        df = pd.DataFrame(data)
        s = ShearWallSummary(concrete=concrete_imp, steel_bar=steel_imp, wall_list=df)
        check_df = s.check()
        # Units row should show "kip" for imperial
        assert check_df["Vu,max"].iloc[0] == "kip"
        assert check_df["ØVn"].iloc[0] == "kip"

    def test_an_imperial_summary_reads_and_prints_in_its_own_units(self):
        """ACI 318-19 in-lb wall, 10 in × 12 ft, hw 10 ft, f'c 4000 psi, Grade 60, #4 @ 8 in E.F.

        By hand (§11.5.4.3, §11.5.4.2): hw/lw = 0.83, αc = 3; Acv = 10·144 =
        1440 in²; Vc = 3·√4000·1440 = 273.2 kip; ρt = 2·0.19635/(10·8) =
        0.0049087, Vs = 0.0049087·60000·1440 = 424.1 kip; ØVn = 0.75·697.3 =
        523.0 kip, under ØVn,max = 0.75·8·√4000·1440 = 546.4 kip. Vu = 100 kip,
        DCR = 0.191.

        The table printed the forces in kip and everything else in metric: t
        25 "cm", lw 3.66 and hw 3.05 "m", and the mesh as "Ø13/20" -- 12.7 mm
        and 20.32 cm rounded to a bar and a spacing nobody placed -- and the
        input took no force in kip, so an imperial wall had its shears typed in
        kN (PR #164 already did). It now prints t in in, lw and hw in ft, the
        mesh in in, and reads "kip" / "kipft".
        """
        concrete_imp = Concrete_ACI_318_19(name="C4000", f_c=4000 * psi)
        steel_imp = SteelBar(name="G60", f_y=60 * ksi)
        data = {
            "Level": ["", "Level 1"],
            "Label": ["", "W1"],
            "Comb.": ["", "U1"],
            "t": ["in", 10],
            "lw": ["ft", 12],
            "hw": ["ft", 10],
            "cc": ["in", 1.5],
            "Nx": ["kip", 0],
            "Vz": ["kip", 100],
            "My": ["kipft", 0],
            "dbh": ["in", 0.5],
            "sh": ["in", 8],
            "dbv": ["in", 0.5],
            "sv": ["in", 8],
        }
        summary = ShearWallSummary(concrete=concrete_imp, steel_bar=steel_imp, wall_list=pd.DataFrame(data))
        table = summary.check()
        units, row = table.iloc[0], table.iloc[1]

        assert (units["t"], units["lw"], units["hw"]) == ("in", "ft", "ft")
        assert (units["Horiz."], units["Vert."]) == ("in", "in")
        assert (row["t"], row["lw"], row["hw"]) == (10, 12, 10)
        assert (row["Horiz."], row["Vert."]) == ("#4@8", "#4@8")
        assert row["Vu,max"] == pytest.approx(100.0)
        assert row["ØVn"] == pytest.approx(523.0, abs=0.1)
        assert row["DCR"] == pytest.approx(0.191, abs=1e-3)
        assert row["Status"] == "✅"


# ------------------------------------------------------------------
# The mesh of a wall given across its rows
# ------------------------------------------------------------------


def _wall_rows(rows):
    """A wall list from rows given as dicts: the unit row first, a 20 cm × 3 m × 3 m wall by default."""
    units = {
        "Level": "",
        "Label": "",
        "Comb.": "",
        "t": "cm",
        "lw": "m",
        "hw": "m",
        "cc": "mm",
        "Nx": "kN",
        "Vz": "kN",
        "My": "kNm",
        "dbh": "mm",
        "sh": "cm",
        "dbv": "mm",
        "sv": "cm",
    }
    defaults = {column: 0 for column in units}
    base = {"Level": "Level 1", "t": 20, "lw": 3.0, "hw": 3.0, "cc": 25}
    return pd.DataFrame([units] + [{**defaults, **base, **row} for row in rows])


def test_a_mesh_given_on_one_row_holds_for_the_whole_wall(concrete, steel):
    """It used to be read off the first row only, so a mesh given on a later one was lost."""
    rows = _wall_rows(
        [
            {"Label": "M1", "Comb.": "ELU 1", "Vz": 100},
            {"Label": "M1", "Comb.": "ELU 2", "Vz": 150, "dbh": 10, "sh": 20, "dbv": 12, "sv": 15},
        ]
    )
    summary = ShearWallSummary(concrete, steel, rows)

    assert len(summary.nodes) == 1
    wall = summary.nodes[0].section
    assert wall.mesh.horizontal.d_b.to("mm").magnitude == 10
    assert wall.mesh.vertical.s.to("cm").magnitude == 15


def test_rows_of_a_wall_that_give_different_meshes_raise(concrete, steel):
    rows = _wall_rows(
        [
            {"Label": "M1", "Comb.": "ELU 1", "Vz": 100, "dbh": 10, "sh": 20, "dbv": 12, "sv": 15},
            {"Label": "M1", "Comb.": "ELU 2", "Vz": 150, "dbh": 10, "sh": 25, "dbv": 12, "sv": 15},
        ]
    )
    with pytest.raises(ValueError, match="Wall 'Level 1 - M1'.*horizontal mesh"):
        ShearWallSummary(concrete, steel, rows)


def test_rows_with_no_wall_label_stay_walls_of_their_own(concrete, steel):
    rows = _wall_rows(
        [
            {"Label": "", "Comb.": "ELU 1", "Vz": 100, "lw": 3.0},
            {"Label": "", "Comb.": "ELU 2", "Vz": 150, "lw": 2.0},
        ]
    )
    summary = ShearWallSummary(concrete, steel, rows)
    designed = summary.design()

    assert len(summary.nodes) == 2
    assert len(designed) == 2
