import pytest
import pandas as pd
from mento import Concrete_ACI_318_19, SteelBar, MPa, set_language
from mento.beam_summary import BeamSummary
from mento.results import DocumentBuilder


@pytest.mark.parametrize("grouped", [False, True])
def test_word_rechecks_real_forces_after_capacity_check(monkeypatch, grouped):
    data = pd.DataFrame(
        {
            "Label": ["", "V1", "V2"],
            "Comb.": ["", "C1", "C2"],
            "b": ["cm", 30, 30],
            "h": ["cm", 50, 50],
            "cc": ["mm", 25, 25],
            "Nx": ["kN", 0, 0],
            "Vz": ["kN", 10, 10],
            "My": ["kNm", 10, 400],
            "ns": ["", 1, 1],
            "dbs": ["mm", 10, 10],
            "sl": ["cm", 15, 15],
            "n1": ["", 2, 2],
            "db1": ["mm", 12, 12],
            "n2": ["", 0, 0],
            "db2": ["mm", 0, 0],
            "n3": ["", 2, 2],
            "db3": ["mm", 12, 12],
            "n4": ["", 0, 0],
            "db4": ["mm", 0, 0],
        }
    )
    if grouped:
        extra = data.iloc[[2]].copy()
        extra["Comb."] = "C3"
        extra["My"] = 350
        data = pd.concat([data, extra], ignore_index=True)
    summary = BeamSummary(
        concrete=Concrete_ACI_318_19(name="C25", f_c=25 * MPa),
        steel_bar=SteelBar(name="420", f_y=420 * MPa),
        beam_list=data,
    )
    summary.check()
    assert summary.nodes[1].section.verification_status["resistance"] == "failed"
    summary.check(capacity_check=True)
    assert summary.nodes[1].section.verification_status["resistance"] == "passed"
    docs = []
    monkeypatch.setattr(DocumentBuilder, "save", lambda self, *_: docs.append(self.doc))
    try:
        set_language("es")
        summary.results_detailed_doc(index=1)
        tables = [[[c.text for c in row.cells] for row in t.rows] for t in docs[0].tables]
        table = next(t for t in tables if any(c in ("Resistance", "Resistencia") for c in t[0]))
        row = next(row for row in table if row[0] == "V2")
        assert row[1] == "No cumple"
        assert row[2] == "No cumple"
        section = summary.nodes[1].section
        assert len(section.flexure_checks) == (2 if grouped else 1)
        assert len(section.shear_checks) == (2 if grouped else 1)
    finally:
        set_language("en")
