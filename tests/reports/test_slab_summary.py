"""OneWaySlabSummary: the beam summary's workflow on a list of one-way slab strips."""

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
    inch,
    kip,
    ft,
    kN,
    kNm,
    ksi,
    mm,
    psi,
)
from mento.results import FAIL_MARK, PASS_MARK, VERDICT_COLUMN

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")

_UNITS = {
    "Label": "",
    "Comb.": "",
    "b": "cm",
    "h": "cm",
    "cc": "mm",
    "Nx": "kN",
    "Vz": "kN",
    "My": "kNm",
    "db1": "mm",
    "s1": "cm",
    "db3": "mm",
    "s3": "cm",
}


def _slab_rows(rows: list[dict[str, Any]], units: dict[str, str] = _UNITS) -> pd.DataFrame:
    """A slab list from rows given as dicts: the unit row first, a metre strip 20 cm thick by default."""
    defaults = {column: 0 for column in units}
    return pd.DataFrame([units] + [{**defaults, "b": 100, "h": 20, "cc": 25, **row} for row in rows])


@pytest.fixture
def concrete() -> Concrete_ACI_318_19:
    return Concrete_ACI_318_19(name="H25", f_c=25 * MPa)


@pytest.fixture
def two_slabs() -> pd.DataFrame:
    """L1 under a sagging and a hogging combination, then L2 on its own row with its bars given."""
    return _slab_rows(
        [
            {"Label": "L1", "Comb.": "1.2D+1.6L", "Vz": 30, "My": 30},
            {"Label": "L1", "Comb.": "1.4D", "Vz": -40, "My": -45},
            {"Label": "L2", "Comb.": "1.2D+1.6L", "h": 15, "Vz": 20, "My": 15, "db1": 10, "s1": 20},
        ]
    )


def test_rows_that_share_a_label_are_one_slab(concrete: Any, steel: SteelBar, two_slabs: pd.DataFrame) -> None:
    summary = OneWaySlabSummary(concrete, steel, two_slabs)

    assert [type(node.section) for node in summary.nodes] == [OneWaySlab, OneWaySlab]
    assert [node.section.label for node in summary.nodes] == ["L1", "L2"]
    assert len(summary.nodes[0].get_forces_list()) == 2
    assert summary.slab_list is summary.beam_list


def test_bars_are_read_as_a_diameter_and_a_spacing(concrete: Any, steel: SteelBar, two_slabs: pd.DataFrame) -> None:
    slab = OneWaySlabSummary(concrete, steel, two_slabs).nodes[1].section
    layer = slab.reinforcement.bottom.layers[0]

    assert layer.d_b == 10 * mm
    assert layer.s.to("cm").magnitude == pytest.approx(20)
    assert not slab.reinforcement.top.layers


def test_a_slab_is_designed_for_its_envelope_as_a_hand_built_node_is(
    concrete: Any, steel: SteelBar, two_slabs: pd.DataFrame
) -> None:
    designed = OneWaySlabSummary(concrete, steel, two_slabs).design()

    slab = OneWaySlab(label="L1", concrete=concrete, steel_bar=steel, width=100 * cm, height=20 * cm, c_c=25 * mm)
    node = Node(
        section=slab,
        forces=[
            Forces(label="1.2D+1.6L", V_z=30 * kN, M_y=30 * kNm),
            Forces(label="1.4D", V_z=-40 * kN, M_y=-45 * kNm),
        ],
    )
    node.design_flexure()
    bottom, top = slab.reinforcement.bottom.layers[0], slab.reinforcement.top.layers[0]

    sagging, hogging = designed.iloc[0], designed.iloc[1]
    assert (sagging["db1"], sagging["s1"]) == (bottom.d_b, bottom.s)
    assert (hogging["db1"], hogging["s1"]) == (top.d_b, top.s)


def test_a_slab_is_designed_without_stirrups(concrete: Any, steel: SteelBar, two_slabs: pd.DataFrame) -> None:
    summary = OneWaySlabSummary(concrete, steel, two_slabs)
    designed = summary.design()

    assert not {"ns", "dbs", "sl"} & set(designed.columns)
    for node in summary.nodes:
        assert node.section.reinforcement.transverse.n_stirrups == 0
    assert list(summary.check()["Av"][1:]) == ["-", "-"]


def test_the_check_gives_one_row_per_slab_with_its_layers(
    concrete: Any, steel: SteelBar, two_slabs: pd.DataFrame
) -> None:
    summary = OneWaySlabSummary(concrete, steel, two_slabs)
    summary.design()
    result = summary.check()

    assert result.columns[0] == "Slab"
    assert list(result["Slab"][1:]) == ["L1", "L2"]
    l1 = result.iloc[1]
    assert l1["Mu"] == -45.0
    assert l1["As,bot"].startswith("Ø") and "/" in l1["As,bot"]
    assert l1["As,top"].startswith("Ø")
    assert list(result[VERDICT_COLUMN][1:]) == [PASS_MARK, PASS_MARK]


def test_a_slab_too_thin_for_its_shear_fails(concrete: Any, steel: SteelBar) -> None:
    """No stirrups are designed: the concrete alone has to carry the shear."""
    rows = _slab_rows([{"Label": "L1", "Comb.": "U", "h": 12, "Vz": 150, "My": 10}])
    summary = OneWaySlabSummary(concrete, steel, rows)
    summary.design()

    assert summary.check()[VERDICT_COLUMN][1] == FAIL_MARK


def test_a_designed_slab_reads_back_as_the_same_slab(
    concrete: Any, steel: SteelBar, two_slabs: pd.DataFrame, tmp_path: Path
) -> None:
    summary = OneWaySlabSummary(concrete, steel, two_slabs)
    summary.design()
    before = summary.check()
    path = tmp_path / "slabs.xlsx"
    summary.export_design(str(path))
    summary.import_design(str(path))

    pd.testing.assert_frame_equal(summary.check(), before)


def test_the_file_holds_each_number_in_its_columns_unit(concrete: Any, steel: SteelBar, tmp_path: Path) -> None:
    """A spacing in a column declared in mm is written in mm, whatever unit the design computed it in."""
    rows = _slab_rows([{"Label": "L1", "Comb.": "U", "Vz": 30, "My": 30}], units={**_UNITS, "s1": "mm", "s3": "mm"})
    summary = OneWaySlabSummary(concrete, steel, rows)
    designed = summary.design()
    path = tmp_path / "slabs.xlsx"
    summary.export_design(str(path))

    written = pd.read_excel(path).iloc[1]
    assert written["s1"] == pytest.approx(designed.iloc[0]["s1"].to("mm").magnitude)


def test_a_layer_needs_both_a_diameter_and_a_spacing(concrete: Any, steel: SteelBar) -> None:
    rows = _slab_rows([{"Label": "L1", "Comb.": "U", "Vz": 30, "My": 30, "db1": 12}])
    with pytest.raises(ValueError, match="Slab 'L1'.*diameter and a spacing"):
        OneWaySlabSummary(concrete, steel, rows)


def test_rows_of_a_slab_that_give_different_bars_raise(concrete: Any, steel: SteelBar) -> None:
    rows = _slab_rows(
        [
            {"Label": "L1", "Comb.": "A", "My": 30, "db1": 12, "s1": 15},
            {"Label": "L1", "Comb.": "B", "My": 20, "db1": 12, "s1": 20},
        ]
    )
    with pytest.raises(ValueError, match="Slab 'L1'.*bottom bars"):
        OneWaySlabSummary(concrete, steel, rows)


def test_a_us_customary_list_is_written_in_its_units() -> None:
    concrete = Concrete_ACI_318_19(name="4000 psi", f_c=4000 * psi)
    steel = SteelBar(name="Grade 60", f_y=60 * ksi)
    units = {**_UNITS, "b": "in", "h": "in", "cc": "in", "Nx": "kip", "Vz": "kip", "My": "kip·ft"}
    units |= {"db1": "in", "s1": "in", "db3": "in", "s3": "in"}
    rows = pd.DataFrame(
        [units]
        + [
            {**{column: 0 for column in units}, "Label": "S1", "Comb.": "U", "b": 12, "h": 8, "cc": 0.75}
            | {"Vz": 3, "My": 6, "db1": 0.5, "s1": 8}
        ]
    )
    summary = OneWaySlabSummary(concrete, steel, rows)
    result = summary.check()

    assert summary.nodes[0].section.width == 12 * inch
    assert result["As,bot"][1] == "#4@8"
    assert summary.nodes[0].get_forces_list()[0].M_y.to(kip * ft).magnitude == pytest.approx(6)


def test_the_word_report_names_slabs(
    concrete: Any, steel: SteelBar, two_slabs: pd.DataFrame, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    summary = OneWaySlabSummary(concrete, steel, two_slabs)
    summary.design()
    summary.results_detailed_doc()

    import docx

    document = docx.Document(str(tmp_path / "Slab_Summary_ACI 318-19.docx"))
    headings = [paragraph.text for paragraph in document.paragraphs if paragraph.style.name.startswith("Heading")]
    assert "Slab Summary Analysis" in headings
    assert "Slab L1 flexure check" in headings
    assert "Slab Data" in headings


def _one_slab(shear: float, moment: float = 20) -> pd.DataFrame:
    """An ACI 100x15 strip, cc 20 mm, with no bars, under one combination."""
    return _slab_rows([{"Label": "L1", "Comb.": "C1", "b": 100, "h": 15, "cc": 20, "Vz": shear, "My": moment}])


def test_slab_design_is_node_design(concrete: Any, steel: SteelBar, capsys: pytest.CaptureFixture[str]) -> None:
    """ACI 100x15, My 20 kN·m, Vu 50 kN: Ø10/14 and DCRv 0.98, as a hand-built slab designs it.

    Designing the flexure alone gave Ø12/25, DCRv 1.058 and ``stirrups_required``,
    after printing that the design was completed.
    """
    summary = OneWaySlabSummary(concrete, steel, _one_slab(50))
    row = summary.design().iloc[0]

    slab = OneWaySlab(label="L1", concrete=concrete, steel_bar=steel, width=100 * cm, height=15 * cm, c_c=20 * mm)
    Node(slab, [Forces(V_z=50 * kN, M_y=20 * kNm)]).design()
    assert slab._stirrup_n == 0
    assert (row["db1"], row["s1"]) == (slab._d_b1_b, slab._s_b1_b) == (10 * mm, 14 * cm)
    check = summary.check().iloc[1]
    assert check["DCRv"] == pytest.approx(0.98, abs=5e-4)
    assert check[VERDICT_COLUMN] == PASS_MARK
    assert "completed" in capsys.readouterr().out


def test_a_slab_that_needs_shear_reinforcement_is_named(
    concrete: Any, steel: SteelBar, capsys: pytest.CaptureFixture[str]
) -> None:
    """Vu 55 kN: ``Node.design()`` puts stirrups on Ø10/14, which a slab of the table does not carry.

    The layers stay, the stirrups go, ``design()`` names the slab instead of
    saying it completed, and ``check()`` fails it: DCRv 1.078, ``stirrups_required``.
    """
    summary = OneWaySlabSummary(concrete, steel, _one_slab(55))
    row = summary.design().iloc[0]
    out = capsys.readouterr().out
    assert "completed" not in out
    assert "L1: Vu > φVc" in out

    assert (row["db1"], row["s1"]) == (10 * mm, 14 * cm)
    assert summary.nodes[0].section._stirrup_n == 0
    check = summary.check().iloc[1]
    assert check["DCRv"] == 1.078
    assert check[VERDICT_COLUMN] == FAIL_MARK
    assert [w.code for w in summary.nodes[0].warnings] == ["stirrups_required"]
