"""ShearWallSummary: a list of walls read from a sections table and a forces table, keyed by (Level, Label)."""

import math
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from mento import (
    Concrete_ACI_318_19,
    Forces,
    MPa,
    Node,
    ShearWall,
    ShearWallSummary,
    SteelBar,
    cm,
    kN,
    ksi,
    m,
    mm,
    psi,
    split_single_table,
)
from mento.results import DocumentBuilder
from mento.summary_tables import SummaryInputError, SummaryInputWarning
from tests.reports.summary_data import WALL_UNITS, wall_forces, walls

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")


@pytest.fixture
def concrete() -> Concrete_ACI_318_19:
    return Concrete_ACI_318_19(name="H25", f_c=25 * MPa)


#: The 16 combinations of the four walls of the 1.4.0 test table: (Level, Label, Nx, Vz, My).
_COMBINATIONS = [
    ("Level 1", "M1", 0, 264, -172),
    ("Level 1", "M1", 0, 138, -90),
    ("Level 1", "M1", 0, 123, -81),
    ("Level 1", "M1", -301, 152, -234),
    ("Level 2", "M1", -150, 32.3, 143),
    ("Level 2", "M1", 55.5, 163, -278),
    ("Level 2", "M1", 282, 19, 159),
    ("Level 2", "M1", -4.5, 88.15, -97),
    ("Level 1", "M2", -240, 61.2, -38),
    ("Level 1", "M2", -163, 29, 60),
    ("Level 1", "M2", -17, 47, -39),
    ("Level 1", "M2", 332, 21, 46.13),
    ("Level 2", "M2", -150, 32.3, 143),
    ("Level 2", "M2", 55.5, 163, -278),
    ("Level 2", "M2", -163, 29, 60),
    ("Level 2", "M2", 55.5, 163, -278),
]


def _forces() -> pd.DataFrame:
    return wall_forces(
        [
            {"Level": level, "Label": label, "Comb.": f"ELU {i % 4 + 1}", "Nx": n, "Vz": v, "My": mm_}
            for i, (level, label, n, v, mm_) in enumerate(_COMBINATIONS)
        ]
    )


@pytest.fixture
def sample_tables() -> tuple:
    """Four walls, Ø8/20 + Ø12/15 each face, four combinations each."""
    sections = walls(
        [
            {"Level": "Level 1", "Label": "M1"},
            {"Level": "Level 2", "Label": "M1"},
            {"Level": "Level 1", "Label": "M2", "lw": 2.0},
            {"Level": "Level 2", "Label": "M2", "lw": 2.0},
        ],
        dbh=8,
        sh=20,
        dbv=12,
        sv=15,
    )
    return sections, _forces()


@pytest.fixture
def summary(concrete: Any, steel: SteelBar, sample_tables: tuple) -> ShearWallSummary:
    return ShearWallSummary(concrete, steel, *sample_tables)


@pytest.fixture
def bare_tables() -> tuple:
    """(Level 1, M1) and (Level 2, M1) with no mesh, two combinations each."""
    sections = walls([{"Level": "Level 1", "Label": "M1"}, {"Level": "Level 2", "Label": "M1"}])
    rows = wall_forces(
        [
            {"Level": "Level 1", "Label": "M1", "Comb.": "ELU 1", "Vz": 264, "My": -172},
            {"Level": "Level 1", "Label": "M1", "Comb.": "ELU 2", "Nx": -301, "Vz": 152, "My": -234},
            {"Level": "Level 2", "Label": "M1", "Comb.": "ELU 1", "Nx": -150, "Vz": 32.3, "My": 143},
            {"Level": "Level 2", "Label": "M1", "Comb.": "ELU 2", "Nx": 55.5, "Vz": 163, "My": -278},
        ]
    )
    return sections, rows


# ------------------------------------------------------------------
# Reading
# ------------------------------------------------------------------


def test_one_node_per_wall_keyed_by_level_and_label(summary: ShearWallSummary) -> None:
    assert len(summary.nodes) == 4
    assert (
        summary.wall_keys
        == summary.labels
        == [("Level 1", "M1"), ("Level 2", "M1"), ("Level 1", "M2"), ("Level 2", "M2")]
    )
    assert [len(node.forces) for node in summary.nodes] == [4, 4, 4, 4]
    wall = summary.nodes[2].section
    assert (wall.level, wall.label, wall.length) == ("Level 1", "M2", 2.0 * m)
    assert wall.thickness.to("cm").magnitude == pytest.approx(20)
    assert wall.mesh.horizontal.d_b.to("mm").magnitude == 8
    assert wall.mesh.vertical.s.to("cm").magnitude == 15


def test_a_partial_wall_mesh_raises(concrete: Any, steel: SteelBar) -> None:
    for row, given, missing in (({"dbh": 10}, "dbh", "sh"), ({"sh": 20}, "sh", "dbh"), ({"sv": 20}, "sv", "dbv")):
        with pytest.raises(SummaryInputError) as raised:
            ShearWallSummary(concrete, steel, walls([{"Label": "M1", **row}]), wall_forces([]))
        assert raised.value.code == "incomplete_group"
        assert f"{given} is given without {missing}" in str(raised.value)


def test_a_wall_with_no_level_is_shown_blank(concrete: Any, steel: SteelBar, monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty Level is "", in check() and in the Word report, never "nan"; an empty Label is an error."""
    sections = walls([{"Level": "", "Label": "M1", "dbh": 10, "sh": 30, "dbv": 10, "sv": 30}])
    summary = ShearWallSummary(
        concrete, steel, sections, wall_forces([{"Level": "", "Label": "M1", "Comb.": "C", "Vz": 100}])
    )
    table = summary.check()
    assert table.iloc[1]["Level"] == ""
    texts: list = []
    monkeypatch.setattr(
        DocumentBuilder,
        "save",
        lambda self, *_: texts.extend(c.text for t in self.doc.tables for r in t.rows for c in r.cells),
    )
    summary.results_detailed_doc()
    assert "nan" not in texts
    with pytest.raises(SummaryInputError) as raised:
        ShearWallSummary(concrete, steel, walls([{"Label": ""}]), wall_forces([]))
    assert raised.value.code == "missing_label"
    assert "Row 3 (1st data row) of the sections table" in str(raised.value)


# ------------------------------------------------------------------
# Check
# ------------------------------------------------------------------


def test_check_gives_one_row_per_wall(summary: ShearWallSummary) -> None:
    table = summary.check()
    assert len(table) == 5
    assert list(table.columns) == [
        "Level",
        "Label",
        "t",
        "lw",
        "hw",
        "Horiz. (each face)",
        "Vert. (each face)",
        "ρt",
        "ρl",
        "Comb.",
        "Vu",
        "Nu",
        "ØVn",
        "DCR",
        "Warnings",
        "Status",
    ]
    for _, row in table.iloc[1:].iterrows():
        assert 0 < row["DCR"] < 1
        assert row["Status"] == "✅"
    first = table.iloc[1]
    assert (first["Comb."], first["Vu"], first["Nu"]) == ("ELU 1", 264.0, 0.0)
    assert first["DCR"] == pytest.approx(264 / first["ØVn"], abs=1e-3)


def test_the_governing_combination_is_the_largest_dcr_not_the_largest_shear(concrete: Any, steel: SteelBar) -> None:
    """A tension lowers αc (ACI 318-19 §11.5.4.3): the row names the combination of largest DCR, with its N."""
    sections = walls([{"Label": "W1", "dbh": 10, "sh": 30, "dbv": 10, "sv": 30}])
    rows = wall_forces(
        [
            {"Label": "W1", "Comb.": "C1", "Vz": 300, "Nx": 100},
            {"Label": "W1", "Comb.": "C2", "Vz": 300, "Nx": -900},
        ]
    )
    summary = ShearWallSummary(concrete, steel, sections, rows)
    row = summary.check().iloc[1]
    record = summary.results[0]
    assert record.shear is not None
    assert row["Comb."] == ", ".join(record.shear.combinations)
    assert row["Nu"] == round(record.shear.axial.to("kN").magnitude, 1)
    assert row["DCR"] == round(max(c.DCR for c in summary.nodes[0].section.shear_checks), 3)


def _two_combination_wall(
    shears: tuple, s_h: float = 15, d_b_h: float = 12, s_v: float = 20, d_b_v: float = 10
) -> tuple:
    """One wall, 25x400 cm, hw 3.5 m, cc 20 mm, the mesh on each face, under two shears in the order given."""
    sections = walls(
        [{"Level": "L1", "Label": "W1"}], t=25, lw=4.0, hw=3.5, cc=20, dbh=d_b_h, sh=s_h, dbv=d_b_v, sv=s_v
    )
    rows = wall_forces(
        [
            {"Level": "L1", "Label": "W1", "Comb.": "F1", "Vz": shears[0]},
            {"Level": "L1", "Label": "W1", "Comb.": "F2", "Vz": shears[1]},
        ]
    )
    return sections, rows


@pytest.mark.parametrize("shears", [(2400, 1000), (1000, 2400)])
def test_status_fails_when_any_combination_misses_a_limit(concrete: Any, steel: SteelBar, shears: tuple) -> None:
    """ρl,min is missed under Vu = 2400 kN (ACI 318-19 §11.6.2(a), worked in the 1.4.0 tests): ❌ in either order."""
    summary = ShearWallSummary(concrete, steel, *_two_combination_wall(shears))
    row = summary.check().iloc[1]
    assert row["DCR"] == pytest.approx(0.970, abs=1e-3)
    assert row["Comb."] == "F1" if shears[0] == 2400 else "F2"
    assert (row["Status"], row["Warnings"]) == ("❌", "mesh_ratio_below_min (v)")
    assert [w.code for w in summary.warnings[("L1", "W1")]] == ["mesh_ratio_below_min"]


def test_status_passes_when_every_combination_does(concrete: Any, steel: SteelBar) -> None:
    row = ShearWallSummary(concrete, steel, *_two_combination_wall((1000, 800))).check().iloc[1]
    assert (row["DCR"], row["Status"], row["Warnings"]) == (pytest.approx(0.404, abs=1e-3), "✅", "-")


def test_status_fails_on_a_spacing_the_code_does_not_allow(concrete: Any, steel: SteelBar) -> None:
    """Ø20/50 each face: s = 500 mm past the 450 mm of §11.7.3.1, DCR 0.202: ❌."""
    summary = ShearWallSummary(concrete, steel, *_two_combination_wall((500, 400), s_h=50, d_b_h=20))
    row = summary.check().iloc[1]
    assert (row["DCR"], row["Status"], row["Warnings"]) == (
        pytest.approx(0.202, abs=1e-3),
        "❌",
        "mesh_spacing_exceeds_max (h)",
    )


def test_a_wall_at_its_section_limit_passes_whatever_the_rounding(concrete: Any, steel: SteelBar) -> None:
    """Vu = ØVn,max = 2475 kN, computed apart (2475.0000000000005): ✅, the pass threshold shared with beams."""
    V_u = 0.75 * (0.66 * math.sqrt(25.0) * 250.0 * 4000.0) * 1e-3
    assert V_u > 2475.0
    summary = ShearWallSummary(concrete, steel, *_two_combination_wall((V_u, 1000), 10, 10, 15, 12))
    row = summary.check().iloc[1]
    assert summary.results[0].shear.DCR > 1.0
    assert summary.results[0].warnings == ()
    assert row["Status"] == "✅"
    over = ShearWallSummary(concrete, steel, *_two_combination_wall((2476, 1000), 10, 10, 15, 12))
    assert over.check().iloc[1]["Status"] == "❌"
    assert [w.code for w in over.results[0].warnings] == ["shear_exceeds_section_limit"]


def test_unreinforced_walls_have_a_row(concrete: Any, steel: SteelBar, bare_tables: tuple) -> None:
    """A wall with no mesh no longer stops the check of the others: it is "no reinforcement: run design()"."""
    sections, rows = bare_tables
    sections = walls(
        [
            {"Level": "Level 1", "Label": "M1"},
            {"Level": "Level 2", "Label": "M1", "dbh": 10, "sh": 30, "dbv": 10, "sv": 30},
        ]
    )
    summary = ShearWallSummary(concrete, steel, sections, rows)
    table = summary.check()
    assert table.iloc[1]["Status"] == "no reinforcement: run design()"
    assert math.isnan(table.iloc[1]["DCR"]) and table.iloc[1]["Horiz. (each face)"] == "-"
    assert table.iloc[2]["Status"] == "✅"
    with pytest.raises(ValueError, match="no capacity check"):
        summary.check(capacity_check=True)


def test_a_wall_with_no_forces_has_its_row(concrete: Any, steel: SteelBar) -> None:
    sections = walls([{"Label": "M1", "dbh": 10, "sh": 30, "dbv": 10, "sv": 30}, {"Label": "M2"}])
    with pytest.warns(SummaryInputWarning):
        summary = ShearWallSummary(concrete, steel, sections, wall_forces([{"Label": "M1", "Comb.": "C", "Vz": 50}]))
    table = summary.check()
    assert table.iloc[2]["Status"] == "no forces"
    summary.design()
    assert summary.sections_table.iloc[2]["dbh"] == 0  # left as given


# ------------------------------------------------------------------
# Design and the file
# ------------------------------------------------------------------


def test_design_fills_the_mesh_and_passes(concrete: Any, steel: SteelBar, bare_tables: tuple) -> None:
    summary = ShearWallSummary(concrete, steel, *bare_tables)
    designed = summary.design()
    assert list(designed.columns[:3]) == ["Level", "Label", "t"]
    for node in summary.nodes:
        mesh = node.section.mesh
        assert mesh.horizontal.has_bars and mesh.vertical.has_bars
    assert all(status == "✅" for status in summary.check()["Status"][1:])


@pytest.mark.parametrize(
    ("bar_unit", "spacing_unit"),
    [("mm", "mm"), ("mm", "cm"), ("cm", "m"), ("mm", "m")],
)
def test_the_wall_mesh_keeps_its_units(
    concrete: Any, steel: SteelBar, tmp_path: Path, bar_unit: str, spacing_unit: str
) -> None:
    """H25, ADN 420, 20 cm x 3 m x 3 m, cc 25 mm, Vz 264 kN, My -172 kN·m: Ø10/30 and DCR 0.25.

    Designed under columns in mm/mm it read back as Ø10/3, DCR 0.178: ten
    times the steel, on the unsafe side.
    """
    units = {**WALL_UNITS, "dbh": bar_unit, "dbv": bar_unit, "sh": spacing_unit, "sv": spacing_unit}
    summary = ShearWallSummary(
        concrete,
        steel,
        walls([{"Label": "M1"}], units=units),
        wall_forces([{"Label": "M1", "Comb.": "C1", "Vz": 264, "My": -172}]),
    )
    summary.design()
    before = summary.check().iloc[1]
    path = tmp_path / "walls.xlsx"
    summary.export_design(path)
    summary.import_design(path)
    after = summary.check().iloc[1]
    assert before["Horiz. (each face)"] == after["Horiz. (each face)"] == "Ø10/30"
    assert before["Vert. (each face)"] == after["Vert. (each face)"] == "Ø10/30"
    assert before["DCR"] == after["DCR"] == 0.25


def test_round_trip_is_exact(summary: ShearWallSummary, tmp_path: Path, concrete: Any, steel: SteelBar) -> None:
    path = tmp_path / "walls.xlsx"
    summary.to_excel(path)
    back = ShearWallSummary.from_excel(concrete, steel, path)
    for ours, theirs in zip(summary.tables(), back.tables()):
        pd.testing.assert_frame_equal(ours, theirs, check_dtype=False)
    summary.design()
    check = summary.check()
    summary.to_excel(path)
    back = ShearWallSummary.from_excel(concrete, steel, path)
    assert back.check().equals(check) and back.results == summary.results


def test_shear_results(summary: ShearWallSummary) -> None:
    assert len(summary.shear_results()) == 17
    single = summary.shear_results(index=1)
    assert len(single) == 5 and "DCR" in single.columns
    assert summary.shear_results(index=("Level 2", "M2")).iloc[1]["Vu"] == 32.3
    with pytest.raises(IndexError):
        summary.shear_results(index=99)
    with pytest.raises(IndexError):
        summary.shear_results(index=0)


def test_from_nodes_takes_the_level_of_the_wall(concrete: Any, steel: SteelBar) -> None:
    wall = ShearWall(
        label="M7",
        level="P3",
        concrete=concrete,
        steel_bar=steel,
        c_c=25 * mm,
        thickness=20 * cm,
        length=3 * m,
        height=3 * m,
    )
    wall.set_horizontal_rebar(d_b=10 * mm, s=20 * cm)
    wall.set_vertical_rebar(d_b=10 * mm, s=20 * cm)
    node = Node(wall, [Forces(label="E", V_z=400 * kN, N_x=200 * kN)])
    summary = ShearWallSummary.from_nodes(concrete, steel, [node])
    assert summary.labels == [("P3", "M7")]
    node.check()
    summary.check()
    assert summary.results[0].warnings == node.warnings
    assert summary.nodes[0].section.shear_checks == wall.shear_checks
    with pytest.raises(SummaryInputError):
        ShearWallSummary.from_nodes(
            concrete,
            steel,
            [
                Node(
                    ShearWall(
                        label="X",
                        concrete=concrete,
                        steel_bar=SteelBar(name="B500", f_y=500 * MPa),
                        c_c=25 * mm,
                        thickness=20 * cm,
                        length=3 * m,
                        height=3 * m,
                    ),
                    [],
                )
            ],
        )


def test_split_single_table_of_walls(concrete: Any, steel: SteelBar) -> None:
    """One section per (Level, Label), with the first row's geometry and mesh; every row a combination."""
    old = pd.DataFrame(
        {
            "Level": ["", "L1", "L1", "L2", ""],
            "Label": ["", "M1", "M1", "M1", None],
            "Comb.": ["", "A", "B", "A", "A"],
            "t": ["cm", 20, 20, 20, 20],
            "lw": ["m", 3, 3, 3, 2],
            "hw": ["m", 3, 3, 3, 3],
            "cc": ["mm", 25, 25, 25, 25],
            "Nx": ["kN", 0, 10, 0, 0],
            "Vz": ["kN", 200, 100, 50, 20],
            "My": ["kNm", 0, 0, 0, 0],
            "dbh": ["mm", 10, 0, 8, 0],
            "sh": ["cm", 20, 0, 20, 0],
            "dbv": ["mm", 10, 0, 8, 0],
            "sv": ["cm", 20, 0, 20, 0],
        }
    )
    with pytest.warns(SummaryInputWarning) as caught:
        sections, rows = split_single_table(old, "wall")
    assert caught[0].message.code == "labels_renamed"
    summary = ShearWallSummary(concrete, steel, sections, rows)
    assert summary.labels == [("L1", "M1"), ("L2", "M1"), ("", "row-4")]
    assert [len(node.forces) for node in summary.nodes] == [2, 1, 1]
    assert summary.nodes[0].section.mesh.horizontal.d_b == 10 * mm
    with pytest.raises(ValueError, match="different values of 'lw'"):
        split_single_table(old.assign(lw=["m", 3, 4, 3, 2]), "wall")


def test_an_imperial_summary_reads_and_prints_in_its_own_units() -> None:
    """ACI 318-19 in-lb wall, 10 in x 12 ft, hw 10 ft, f'c 4000 psi, Grade 60, #4 @ 8 in each face, Vu 100 kip.

    By hand (§11.5.4.3, §11.5.4.2): Vc = 3·√4000·1440 = 273.2 kip, Vs =
    0.0049087·60000·1440 = 424.1 kip, ØVn = 0.75·697.3 = 523.0 kip, DCR 0.191.
    """
    concrete_imp = Concrete_ACI_318_19(name="C4000", f_c=4000 * psi)
    steel_imp = SteelBar(name="G60", f_y=60 * ksi)
    units = {
        "Level": "",
        "Label": "",
        "t": "in",
        "lw": "ft",
        "hw": "ft",
        "cc": "in",
        "dbh": "in",
        "sh": "in",
        "dbv": "in",
        "sv": "in",
    }
    sections = walls(
        [{"Label": "W1", "t": 10, "lw": 12, "hw": 10, "cc": 1.5, "dbh": 0.5, "sh": 8, "dbv": 0.5, "sv": 8}], units=units
    )
    rows = wall_forces(
        [{"Label": "W1", "Comb.": "U1", "Vz": 100}],
        {"Level": "", "Label": "", "Comb.": "", "Nx": "kip", "Vz": "kip", "My": "kipft"},
    )
    table = ShearWallSummary(concrete_imp, steel_imp, sections, rows).check()
    units_row, row = table.iloc[0], table.iloc[1]
    assert (units_row["t"], units_row["lw"], units_row["hw"], units_row["Vu"]) == ("in", "ft", "ft", "kip")
    assert (units_row["Horiz. (each face)"], units_row["Vert. (each face)"]) == ("in", "in")
    assert (row["t"], row["lw"], row["hw"]) == (10, 12, 10)
    assert (row["Horiz. (each face)"], row["Vert. (each face)"]) == ("#4@8", "#4@8")
    assert row["Vu"] == pytest.approx(100.0)
    assert row["ØVn"] == pytest.approx(523.0, abs=0.1)
    assert row["DCR"] == pytest.approx(0.191, abs=1e-3)
    assert row["Status"] == "✅"


def test_results_detailed_doc(summary: ShearWallSummary, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    summary.results_detailed_doc(index=("Level 1", "M2"))
    assert (tmp_path / "Shear_Wall_Summary_ACI 318-19.docx").exists()
    with pytest.raises(IndexError):
        summary.results_detailed_doc(index=99)
