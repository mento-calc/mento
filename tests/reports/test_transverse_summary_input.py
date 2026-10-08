"""Explicit leg counts work through the PR180 hooks without affecting slabs."""

import math

import pandas as pd
import pytest
from docx import Document

from mento import BeamSummary, Concrete_ACI_318_19, MPa, OneWaySlabSummary, SteelBar, mm


def beam_table():
    units = {
        "Label": "",
        "Comb.": "",
        "b": "cm",
        "h": "cm",
        "cc": "mm",
        "Nx": "kN",
        "Vz": "kN",
        "My": "kNm",
        "n_legs": "",
        "dbs": "mm",
        "sl": "cm",
    }
    for n in range(1, 5):
        units[f"n{n}"] = ""
        units[f"db{n}"] = "mm"
    row = {c: 0 for c in units}
    row.update(Label="V1", **{"Comb.": "ULS"}, b=30, h=50, cc=30, Vz=50, My=40, n_legs=4, dbs=8, sl=20, n1=4, db1=20)
    return pd.DataFrame([units, row])


def materials():
    return Concrete_ACI_318_19(name="C25", f_c=25 * MPa), SteelBar(name="ADN420", f_y=420 * MPa)


def test_leg_input_excel_and_current_word(tmp_path, monkeypatch):
    table = beam_table()
    concrete, steel = materials()
    summary = BeamSummary(concrete, steel, table)
    assert "ns" not in table.columns  # The caller's frame is unchanged.
    assert summary.nodes[0].section.reinforcement.transverse.n_legs == 4
    assert summary.nodes[0].section._A_v.to(mm**2 / mm).magnitude == pytest.approx(4 * math.pi * 8**2 / 4 / 200)
    summary.design()
    assert summary.design_data.iloc[0]["n_legs"] == 2 * summary.design_data.iloc[0]["ns"]
    path = tmp_path / "legs.xlsx"
    summary.export_design(str(path))
    imported = BeamSummary(concrete, steel, pd.read_excel(path))
    assert imported.nodes[0].section.reinforcement.transverse == summary.nodes[0].section.reinforcement.transverse
    monkeypatch.chdir(tmp_path)
    summary.results_detailed_doc()
    documents = list(tmp_path.glob("*.docx"))
    assert len(documents) == 1
    contents = " ".join(
        cell.text for table in Document(documents[0]).tables for row in table.rows for cell in row.cells
    )
    assert "V1" in contents


@pytest.mark.parametrize(
    "column,value",
    [
        ("n_legs", 3),
        ("n_legs", 2.5),
        ("n_legs", -2),
        ("n_legs", True),
        ("n_legs", "oops"),
        ("n_legs", float("inf")),
        ("ns", 1.5),
        ("ns", True),
    ],
)
def test_rejects_invalid_counts_before_numeric_coercion(column, value):
    table = beam_table().astype(object)
    if column == "ns":
        table = table.rename(columns={"n_legs": "ns"})
    table.loc[1, column] = value
    with pytest.raises(ValueError, match="count|even"):
        BeamSummary(*materials(), table)


def test_rejects_conflicting_counts_and_count_units():
    table = beam_table()
    table["ns"] = ["", 1]
    with pytest.raises(ValueError, match="different reinforcement"):
        BeamSummary(*materials(), table)
    table = beam_table()
    table.loc[0, "n_legs"] = "mm"
    with pytest.raises(ValueError, match="dimensionless"):
        BeamSummary(*materials(), table)


def test_slab_does_not_require_transverse_columns():
    units = {
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
    row = {c: 0 for c in units}
    row.update(Label="L1", **{"Comb.": "ULS"}, b=100, h=20, cc=25, My=10, db1=10, s1=15)
    slab = OneWaySlabSummary(*materials(), pd.DataFrame([units, row]))
    assert slab.nodes[0].section.reinforcement.transverse.n_legs == 0


@pytest.mark.parametrize("count_column", ["legs", "n_legs", "ns"])
def test_export_has_one_editable_leg_count(tmp_path, count_column):
    table = beam_table().rename(columns={"n_legs": count_column})
    if count_column == "ns":
        table.loc[1, "ns"] = 2
    concrete, steel = materials()
    summary = BeamSummary(concrete, steel, table)
    summary.design()
    path = tmp_path / "editable_legs.xlsx"
    summary.export_design(str(path))
    exported = pd.read_excel(path).fillna("")
    assert "legs" in exported and "ns" not in exported and "n_legs" not in exported
    assert exported.loc[0, "legs"] == ""
    exported.loc[1, "legs"] = 6
    exported.to_excel(path, index=False)
    summary.import_design(str(path))
    assert summary.nodes[0].section.reinforcement.transverse.n_legs == 6
