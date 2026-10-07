"""OneWaySlabSummary: a list of one-way slab strips read from a sections table and a forces table."""

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
    OneWaySlab,
    OneWaySlabSummary,
    SteelBar,
    cm,
    ft,
    inch,
    kip,
    kN,
    kNm,
    ksi,
    mm,
    psi,
)
from mento.results import FAIL_MARK, PASS_MARK, VERDICT_COLUMN, DocumentBuilder
from mento.summary_tables import SummaryInputError, SummaryInputWarning
from tests.reports.summary_data import GEOMETRY_UNITS, SLAB_UNITS, beams, forces, slabs

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")


@pytest.fixture
def concrete() -> Concrete_ACI_318_19:
    return Concrete_ACI_318_19(name="H25", f_c=25 * MPa)


@pytest.fixture
def two_slabs() -> tuple:
    """L1 (20 cm, no bars) under a sagging and a hogging combination; L2 (15 cm) with Ø10/20 below."""
    sections = slabs([{"Label": "L1", "h": 20, "cc": 25}, {"Label": "L2", "cc": 25, "db1_bot": 10, "s1_bot": 20}])
    rows = forces(
        [
            {"Label": "L1", "Comb.": "1.2D+1.6L", "Vz": 30, "My": 30},
            {"Label": "L1", "Comb.": "1.4D", "Vz": -40, "My": -45},
            {"Label": "L2", "Comb.": "1.2D+1.6L", "Vz": 20, "My": 15},
        ]
    )
    return sections, rows


def _one_slab(shear: float, moment: float = 20) -> tuple:
    """An ACI 100x15 strip, cc 20 mm, with no bars, under one combination."""
    return slabs([{"Label": "L1"}], units=GEOMETRY_UNITS), forces(
        [{"Label": "L1", "Comb.": "C1", "Vz": shear, "My": moment}]
    )


def test_one_row_per_slab_with_both_faces(concrete: Any, steel: SteelBar, two_slabs: tuple) -> None:
    summary = OneWaySlabSummary(concrete, steel, *two_slabs)
    assert [type(node.section) for node in summary.nodes] == [OneWaySlab, OneWaySlab]
    assert summary.labels == ["L1", "L2"]
    assert len(summary.nodes[0].forces) == 2
    layer = summary.nodes[1].section.reinforcement.bottom.layers[0]
    assert (layer.d_b, layer.s.to("cm").magnitude) == (10 * mm, pytest.approx(20))
    assert not summary.nodes[1].section.reinforcement.top.layers


def test_a_slab_is_designed_for_its_envelope_as_a_hand_built_node_is(
    concrete: Any, steel: SteelBar, two_slabs: tuple
) -> None:
    summary = OneWaySlabSummary(concrete, steel, *two_slabs)
    designed = summary.design().iloc[1]

    slab = OneWaySlab(label="L1", concrete=concrete, steel_bar=steel, width=100 * cm, height=20 * cm, c_c=25 * mm)
    Node(
        slab, [Forces(label="1.2D+1.6L", V_z=30 * kN, M_y=30 * kNm), Forces(label="1.4D", V_z=-40 * kN, M_y=-45 * kNm)]
    ).design()
    bottom, top = slab.reinforcement.bottom.layers[0], slab.reinforcement.top.layers[0]
    assert (designed["db1_bot"], designed["s1_bot"]) == (bottom.d_b.to("mm").magnitude, bottom.s.to("cm").magnitude)
    assert (designed["db1_top"], designed["s1_top"]) == (top.d_b.to("mm").magnitude, top.s.to("cm").magnitude)


def test_slab_design_is_node_design(concrete: Any, steel: SteelBar, capsys: pytest.CaptureFixture[str]) -> None:
    """ACI 100x15, My 20 kN·m, Vu 50 kN: Ø10/14 and DCRv 0.98 without stirrups, as a hand-built slab.

    Designing the flexure alone gave Ø12/25, DCRv 1.058 and ``stirrups_required``,
    after printing that the design was completed.
    """
    summary = OneWaySlabSummary(concrete, steel, *_one_slab(50))
    row = summary.design().iloc[1]
    assert "completed" in capsys.readouterr().out

    slab = OneWaySlab(label="L1", concrete=concrete, steel_bar=steel, width=100 * cm, height=15 * cm, c_c=20 * mm)
    Node(slab, [Forces(V_z=50 * kN, M_y=20 * kNm)]).design()
    assert slab._stirrup_n == 0
    assert (row["db1_bot"], row["s1_bot"]) == (10, 14)
    check = summary.check().iloc[1]
    assert check["DCRv"] == pytest.approx(0.98, abs=5e-4)
    assert check[VERDICT_COLUMN] == PASS_MARK
    assert "Av" not in summary.check().columns


def test_a_slab_that_needs_shear_reinforcement_is_named(
    concrete: Any, steel: SteelBar, capsys: pytest.CaptureFixture[str]
) -> None:
    """Vu 55 kN: ``Node.design()`` puts stirrups on Ø10/14, which a slab of the table does not carry.

    The layers stay, the stirrups go, ``design()`` names the slab instead of
    saying it completed, and ``check()`` fails it: DCRv 1.078, ``stirrups_required``.
    """
    summary = OneWaySlabSummary(concrete, steel, *_one_slab(55))
    with pytest.warns(SummaryInputWarning) as caught:
        row = summary.design().iloc[1]
    assert [w.message.code for w in caught] == ["shear_reinforcement_required"]
    out = capsys.readouterr().out
    assert "completed" not in out
    assert "⚠ Slabs designed. 'L1': Vu > φVc" in out

    assert (row["db1_bot"], row["s1_bot"]) == (10, 14)
    assert summary.nodes[0].section._stirrup_n == 0
    check = summary.check().iloc[1]
    assert (check["DCRv"], check[VERDICT_COLUMN], check["Warnings"]) == (1.078, FAIL_MARK, "stirrups_required")


@pytest.mark.parametrize(
    ("moment", "top", "bottom", "dcr", "warnings", "verdict"),
    [
        (-90, "Ø16/7", "Ø10/3", 0.877, "bar_spacing_below_min (bottom)", FAIL_MARK),
        (-110, "Ø16/6", "Ø20/4", 0.952, "bar_spacing_below_min (bottom)", FAIL_MARK),
        (-60, "Ø16/12", "Ø10/25", 0.943, "-", PASS_MARK),
    ],
)
def test_a_hogging_slab_reads_back_as_designed(
    concrete: Any,
    steel: SteelBar,
    tmp_path: Path,
    moment: float,
    top: str,
    bottom: str,
    dcr: float,
    warnings: str,
    verdict: str,
) -> None:
    """100x15, cc 25, hogging only: the bottom layer ``Node.design()`` places comes back from the file.

    Written one face per row, it was lost: -90 kN·m checked at 0.877 in
    memory and 1.27 after export and import, -110 at 0.952 and 1.515. The
    first two fail on the minimum spacing of their bottom layer, which a
    design can leave (Ø10/3 is what the compression it needs takes).
    """
    sections = slabs([{"Label": "L"}], units=GEOMETRY_UNITS, cc=25)
    summary = OneWaySlabSummary(
        concrete, steel, sections, forces([{"Label": "L", "Comb.": "C", "Vz": 30, "My": moment}])
    )
    summary.design()
    before = summary.check()
    row = before.iloc[1]
    assert (row["As,top"], row["As,bot"], row["DCRb,top"], row["Warnings"], row[VERDICT_COLUMN]) == (
        top,
        bottom,
        dcr,
        warnings,
        verdict,
    )
    summary.export_design(tmp_path / "slabs.xlsx")
    summary.import_design(tmp_path / "slabs.xlsx")
    assert summary.check().equals(before)


def test_warnings_fail_the_verdict(concrete: Any, steel: SteelBar) -> None:
    """Ø6/25 is below the 0.0018·Ag minimum and Ø12/40 past the 3h / 450 mm spacing: both pass their DCR and fail."""
    sections = slabs([{"Label": "thin", "db1_bot": 6, "s1_bot": 25}, {"Label": "sparse", "db1_bot": 12, "s1_bot": 40}])
    rows = forces(
        [{"Label": "thin", "Comb.": "C", "Vz": 20, "My": 4}, {"Label": "sparse", "Comb.": "C", "Vz": 20, "My": 10}]
    )
    table = OneWaySlabSummary(concrete, steel, sections, rows).check()
    thin, sparse = table.iloc[1], table.iloc[2]
    assert (thin["DCRb,bot"], thin["Warnings"], thin[VERDICT_COLUMN]) == (0.743, "As_below_min (bottom)", FAIL_MARK)
    assert (sparse["DCRb,bot"], sparse["Warnings"], sparse[VERDICT_COLUMN]) == (
        0.772,
        "bar_spacing_exceeds_max (bottom)",
        FAIL_MARK,
    )


def test_slab_shear_capacity_by_hand(concrete: Any, steel: SteelBar) -> None:
    """φVc of a strip without stirrups, ACI 318-19 Table 22.5.5.1(c), worked by hand.

    100x15, cc 20, Ø10/20 at the bottom: d = 150 - 20 - 5 = 125 mm, λs =
    min(1, √(2 / (1 + 0.004·125))) = 1, ρw = 5 · 78.54 / (1000 · 125) =
    0.0031416, so φVc = 0.75 · 0.66 · 1 · ρw^(1/3) · √25 · 1000 · 125 = 45.32 kN.
    """
    sections = slabs([{"Label": "L", "db1_bot": 10, "s1_bot": 20}])
    summary = OneWaySlabSummary(concrete, steel, sections, forces([{"Label": "L", "Comb.": "C", "Vz": 20, "My": 10}]))
    rho = 5 * math.pi / 4 * 10**2 / (1000 * 125)
    by_hand = 0.75 * 0.66 * 1 * rho ** (1 / 3) * math.sqrt(25) * 1000 * 125 / 1000
    assert summary.shear_results(index="L").iloc[1]["ØVc"] == pytest.approx(by_hand, abs=0.01)


def test_slab_table_validation(concrete: Any, steel: SteelBar) -> None:
    """A layer given in part, a negative spacing or diameter: named errors."""
    cases = [
        ({"s1_bot": 20}, "incomplete_group", "s1_bot is given without db1_bot"),
        ({"db1_bot": 12}, "incomplete_group", "db1_bot is given without s1_bot"),
        ({"db1_bot": 12, "s1_bot": -20}, "negative_value", "s1_bot of 'L1' is -20"),
        ({"db1_bot": -12, "s1_bot": 20}, "negative_value", "db1_bot of 'L1' is -12"),
    ]
    for row, code, text in cases:
        with pytest.raises(SummaryInputError) as raised:
            OneWaySlabSummary(concrete, steel, slabs([{"Label": "L1", **row}]), forces([]))
        assert raised.value.code == code
        assert text in str(raised.value)
    with pytest.raises(SummaryInputError) as raised:
        OneWaySlabSummary(concrete, steel, beams([{"Label": "V1"}]), forces([]))
    assert raised.value.code == "wrong_element"
    assert "beam" in str(raised.value)


def test_stirrup_columns_in_a_slab_raise(concrete: Any, steel: SteelBar) -> None:
    sections = slabs([{"Label": "L1", "legs": 2, "dbs": 8, "sl": 20}])
    with pytest.raises(SummaryInputError) as raised:
        OneWaySlabSummary(concrete, steel, sections, forces([]))
    assert raised.value.code == "stirrups_in_slab"
    assert "'legs', 'dbs', 'sl'" in str(raised.value)


def test_forces_are_those_of_the_strip(concrete: Any, steel: SteelBar) -> None:
    """The forces of a strip of width b, in kN and kNm: a force per metre is no unit the table reads."""
    sections = slabs([{"Label": "L1", "b": 50, "db1_bot": 10, "s1_bot": 20}])
    units = {"Label": "", "Comb.": "", "Nx": "kN", "Vz": "kN/m", "My": "kNm"}
    with pytest.raises(SummaryInputError) as raised:
        OneWaySlabSummary(concrete, steel, sections, forces([{"Label": "L1", "Comb.": "C", "Vz": 30, "My": 12}], units))
    assert raised.value.code == "wrong_unit" and "'kN/m'" in str(raised.value)


def test_the_file_holds_each_number_in_its_columns_unit(concrete: Any, steel: SteelBar, tmp_path: Path) -> None:
    """A spacing in a column declared in mm is written in mm, whatever unit the design computed it in."""
    units = {**SLAB_UNITS, "s1_bot": "mm", "s3_bot": "mm"}
    summary = OneWaySlabSummary(
        concrete,
        steel,
        slabs([{"Label": "L1"}], units=units),
        forces([{"Label": "L1", "Comb.": "U", "Vz": 30, "My": 30}]),
    )
    designed = summary.design()
    summary.export_design(tmp_path / "slabs.xlsx")
    written = pd.read_excel(tmp_path / "slabs.xlsx", sheet_name="Sections").iloc[1]
    assert written["s1_bot"] == designed.iloc[1]["s1_bot"] == summary.nodes[0].section._s_b1_b.to("mm").magnitude


def test_a_us_customary_list_is_written_in_its_units() -> None:
    concrete = Concrete_ACI_318_19(name="4000 psi", f_c=4000 * psi)
    steel = SteelBar(name="Grade 60", f_y=60 * ksi)
    units = {"Label": "", "b": "in", "h": "in", "cc": "in", "db1_bot": "in", "s1_bot": "in"}
    sections = slabs([{"Label": "S1", "b": 12, "h": 8, "cc": 0.75, "db1_bot": 0.5, "s1_bot": 8}], units=units)
    rows = forces(
        [{"Label": "S1", "Comb.": "U", "Vz": 3, "My": 6}],
        {"Label": "", "Comb.": "", "Nx": "kip", "Vz": "kip", "My": "kip·ft"},
    )
    summary = OneWaySlabSummary(concrete, steel, sections, rows)
    result = summary.check()
    assert summary.nodes[0].section.width == 12 * inch
    assert result["As,bot"][1] == "#4@8"
    assert summary.nodes[0].forces[0].M_y.to(kip * ft).magnitude == pytest.approx(6)
    assert summary.sections_table.iloc[0]["db1_top"] == "in"  # the default of a US customary list


@pytest.mark.parametrize("face", ["bot", "top"])
def test_from_nodes_and_excel_preserve_a_lone_second_layer(concrete, steel, tmp_path, face):
    slab = OneWaySlab(label="L1", concrete=concrete, steel_bar=steel, width=100 * cm, height=25 * cm, c_c=20 * mm)
    setter = slab.set_slab_longitudinal_rebar_bot if face == "bot" else slab.set_slab_longitudinal_rebar_top
    setter(d_b1=0 * mm, s_b1=0 * mm, d_b3=12 * mm, s_b3=18 * cm)
    node = Node(slab, [Forces(label="C", M_y=(30 if face == "bot" else -30) * kNm)])
    summary = OneWaySlabSummary.from_nodes(concrete, steel, [node], units={f"s3_{face}": "mm"})
    row = summary.sections_table.iloc[1]
    assert [row[f"db1_{face}"], row[f"s1_{face}"], row[f"db3_{face}"], row[f"s3_{face}"]] == [0, 0, 12, 180]
    source_depth = slab._d_bot if face == "bot" else slab._d_top
    path = tmp_path / "second_only.xlsx"
    summary.export_design(str(path))
    imported = OneWaySlabSummary.from_excel(concrete, steel, str(path))
    rebuilt = imported.nodes[0].section
    assert (rebuilt._d_bot if face == "bot" else rebuilt._d_top) == source_depth
    node.check()
    imported.check()
    assert rebuilt.flexure_checks == slab.flexure_checks


def test_from_nodes_writes_a_slab(concrete: Any, steel: SteelBar) -> None:
    slab = OneWaySlab(label="L1", concrete=concrete, steel_bar=steel, width=100 * cm, height=15 * cm, c_c=20 * mm)
    slab.set_slab_longitudinal_rebar_bot(d_b1=10 * mm, s_b1=15 * cm, d_b3=8 * mm, s_b3=30 * cm)
    node = Node(slab, [Forces(label="C", V_z=20 * kN, M_y=12 * kNm)])
    summary = OneWaySlabSummary.from_nodes(concrete, steel, [node])
    node.check()
    summary.check()
    assert summary.results[0].warnings == node.warnings
    assert summary.nodes[0].section.flexure_checks == slab.flexure_checks
    assert list(summary.sections_table.iloc[1][["db1_bot", "s1_bot", "db3_bot", "s3_bot"]]) == [10, 15, 8, 30]

    stirruped = OneWaySlab(label="L2", concrete=concrete, steel_bar=steel, width=100 * cm, height=15 * cm, c_c=20 * mm)
    stirruped.set_slab_transverse_rebar(8 * mm, 20 * cm, 20 * cm)
    with pytest.raises(SummaryInputError) as raised:
        OneWaySlabSummary.from_nodes(concrete, steel, [Node(stirruped, [])])
    assert raised.value.code == "node_not_representable" and "stirrups" in str(raised.value)
    from mento import Footing

    footing = Footing(label="F1", concrete=concrete, steel_bar=steel, width=100 * cm, height=50 * cm, c_c=50 * mm)
    with pytest.raises(SummaryInputError, match="Footing"):
        OneWaySlabSummary.from_nodes(concrete, steel, [Node(footing, [])])


def test_the_word_report_names_slabs(
    concrete: Any, steel: SteelBar, two_slabs: tuple, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    summary = OneWaySlabSummary(concrete, steel, *two_slabs)
    summary.design()
    summary.results_detailed_doc()

    import docx

    document = docx.Document(str(tmp_path / "Slab_Summary_ACI 318-19.docx"))
    headings = [p.text for p in document.paragraphs if p.style.name.startswith("Heading")]
    assert "Slab Summary Analysis" in headings
    assert "Slab L1 flexure check" in headings


def test_the_check_of_a_slab_has_no_stirrup_column(
    concrete: Any, steel: SteelBar, two_slabs: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    summary = OneWaySlabSummary(concrete, steel, *two_slabs)
    summary.design()
    table = summary.check()
    assert list(table.columns[:4]) == ["Slab", "b×h", "As,top", "As,bot"]
    assert "Av" not in table.columns
    capacities = summary.check(capacity_check=True)
    assert "Av,real" not in capacities.columns and "As,bot,real" in capacities.columns
    monkeypatch.setattr(DocumentBuilder, "save", lambda *_: None)
    summary.results_detailed_doc(index="L2")


def test_the_report_shows_a_slabs_spacing_against_its_maximum(
    concrete: Any, steel: SteelBar, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ø12/40 is past the 300 mm of §7.7.2.3: the limit row says so, as the slab's own report does.

    The summary report wrote the four rows of a beam by hand: "Minimum spacing
    bottom 400 ≥ 37 ❌", the maximum that fails it dropped.
    """
    sections = slabs([{"Label": "sparse", "db1_bot": 12, "s1_bot": 40}])
    summary = OneWaySlabSummary(
        concrete, steel, sections, forces([{"Label": "sparse", "Comb.": "C", "Vz": 20, "My": 10}])
    )
    documents: list = []
    monkeypatch.setattr(DocumentBuilder, "save", lambda self, *_: documents.append(self.doc))
    summary.results_detailed_doc()
    limits = next(t for t in documents[0].tables if t.rows[0].cells[0].text == "Check")
    rows = {row.cells[0].text: [cell.text for cell in row.cells[1:]] for row in limits.rows[1:]}
    unit, value, minimum, maximum, verdict = rows["Bar spacing bottom"]
    assert (unit, float(value), float(minimum), float(maximum), verdict) == ("mm", 400, 37, 300, FAIL_MARK)
    assert "Minimum spacing bottom" not in rows
