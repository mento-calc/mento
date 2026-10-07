"""Explicit legs preserve legacy calculations and survive summary Excel round trips."""

import pandas as pd
import pytest

from mento import (
    BeamSummary,
    Concrete_ACI_318_19,
    Concrete_CIRSOC_201_25,
    Concrete_EN_1992_2004,
    Forces,
    RectangularBeam,
    SteelBar,
)
from mento.i18n import get_language, set_language
from mento.units import MPa, cm, inch, kN, mm


def beam(concrete_type=Concrete_ACI_318_19):
    return RectangularBeam(
        concrete=concrete_type(name="C25", f_c=25 * MPa),
        steel_bar=SteelBar(name="S420", f_y=420 * MPa),
        width=40 * cm,
        height=60 * cm,
        c_c=25 * mm,
    )


def table():
    return pd.DataFrame(
        {
            "Label": ["", "B1"],
            "Comb.": ["", "ULS"],
            "b": ["cm", 40],
            "h": ["cm", 60],
            "cc": ["mm", 25],
            "Nx": ["kN", 0],
            "Vz": ["kN", 100],
            "My": ["kNm", 40],
            "ns": ["", 2],
            "dbs": ["mm", 8],
            "sl": ["cm", 20],
            "n1": ["", 4],
            "db1": ["mm", 16],
            "n2": ["", 0],
            "db2": ["mm", 0],
            "n3": ["", 0],
            "db3": ["mm", 0],
            "n4": ["", 0],
            "db4": ["mm", 0],
        }
    )


@pytest.mark.parametrize("concrete_type", [Concrete_ACI_318_19, Concrete_CIRSOC_201_25, Concrete_EN_1992_2004])
@pytest.mark.parametrize("diameter,spacing", [(8 * mm, 20 * cm), (0.375 * inch, 8 * inch)])
def test_leg_input_matches_legacy_shear_and_geometry(concrete_type, diameter, spacing):
    old, new = beam(concrete_type), beam(concrete_type)
    old.set_transverse_rebar(2, diameter, spacing)
    new.set_transverse_rebar(n_legs=4, d_b=diameter, s_l=spacing)
    assert new.reinforcement.transverse == old.reinforcement.transverse
    assert new.section_geometry == old.section_geometry
    force = Forces(V_z=100 * kN)
    old.check_shear([force])
    new.check_shear([force])
    assert new.shear_checks == old.shear_checks


@pytest.mark.parametrize("legs,error", [(3, ValueError), (-2, ValueError), (4.5, TypeError), (True, TypeError)])
def test_bad_leg_input_keeps_previous_reinforcement(legs, error):
    b = beam()
    b.set_transverse_rebar(2, 8 * mm, 20 * cm)
    before = b.reinforcement
    with pytest.raises(error, match="n_legs"):
        b.set_transverse_rebar(n_legs=legs, d_b=8 * mm, s_l=20 * cm)
    assert b.reinforcement == before


def test_conflicting_leg_input_rejects_explicit_zero_and_preserves_state():
    b = beam()
    b.set_transverse_rebar(n_stirrups=2, n_legs=4, d_b=8 * mm, s_l=20 * cm)
    before = b.reinforcement
    with pytest.raises(ValueError, match="equal"):
        b.set_transverse_rebar(n_stirrups=0, n_legs=4, d_b=8 * mm, s_l=20 * cm)
    assert b.reinforcement == before
    b.set_transverse_rebar(n_legs=0)
    assert b.reinforcement.transverse.n_legs == 0


@pytest.mark.parametrize("convention", ["legacy", "legs", "both", "blank_legacy"])
def test_summary_design_and_excel_preserve_count_convention(tmp_path, convention):
    frame = table()
    if convention == "legs":
        frame = frame.rename(columns={"ns": "n_legs"})
        frame.loc[1, "n_legs"] = 4
    elif convention in ("both", "blank_legacy"):
        frame["n_legs"] = ["", 4]
        if convention == "blank_legacy":
            frame.loc[1, "ns"] = None
    b = beam()
    summary = BeamSummary(b.concrete, b.steel_bar, frame)
    assert summary.nodes[0].section.reinforcement.transverse.n_legs == 4
    result = summary.design()
    count = summary.nodes[0].section.reinforcement.transverse.n_legs
    if "n_legs" in frame:
        assert result.loc[0, "n_legs"] == count
    if "ns" in frame:
        assert result.loc[0, "ns"] * 2 == count
    path = tmp_path / "legs.xlsx"
    summary.export_design(str(path))
    saved = pd.read_excel(path)
    assert list(saved.columns) == list(frame.columns)
    rebuilt = BeamSummary(b.concrete, b.steel_bar, saved)
    assert rebuilt.nodes[0].section.reinforcement.transverse.n_legs == count
    summary.import_design(str(path))
    assert summary.nodes[0].section.reinforcement.transverse.n_legs == count


@pytest.mark.parametrize("legs", [3, 4.5, -2, True, "typo"])
def test_summary_rejects_invalid_counts_instead_of_coercing_them(legs):
    frame = table().rename(columns={"ns": "n_legs"})
    frame.loc[1, "n_legs"] = legs
    b = beam()
    with pytest.raises((TypeError, ValueError), match="n_legs"):
        BeamSummary(b.concrete, b.steel_bar, frame)


def test_summary_rejects_conflicting_counts():
    frame = table()
    frame["n_legs"] = ["", 2]
    b = beam()
    with pytest.raises(ValueError, match="equal"):
        BeamSummary(b.concrete, b.steel_bar, frame)


@pytest.mark.parametrize("language", ["en", "es"])
@pytest.mark.parametrize("convention", ["legacy", "legs", "blank_legacy", "blank_legs"])
def test_summary_word_reports_normalized_legs_without_changing_input(tmp_path, monkeypatch, language, convention):
    from docx import Document

    frame = table()
    if convention == "legs":
        frame = frame.rename(columns={"ns": "n_legs"})
        frame.loc[1, "n_legs"] = 4
    elif convention in ("blank_legacy", "blank_legs"):
        frame["n_legs"] = ["", 4]
        frame.loc[1, "ns" if convention == "blank_legacy" else "n_legs"] = None
    original = frame.copy(deep=True)
    b = beam()
    summary = BeamSummary(b.concrete, b.steel_bar, frame)
    processed = summary.data.copy(deep=True)
    monkeypatch.chdir(tmp_path)
    previous_language = get_language()
    try:
        set_language(language)
        summary.results_detailed_doc()
    finally:
        set_language(previous_language)
    paths = list(tmp_path.glob("*.docx"))
    assert len(paths) == 1
    document = Document(paths[0])
    data_table = next(t for t in document.tables if "n_legs" in [c.text for c in t.rows[0].cells])
    header = [c.text for c in data_table.rows[0].cells]
    assert "ns" not in header
    assert data_table.rows[1].cells[header.index("n_legs")].text == ""
    assert data_table.rows[2].cells[header.index("n_legs")].text == "4"
    assert data_table.rows[1].cells[header.index("dbs")].text == "mm"
    assert data_table.rows[2].cells[header.index("dbs")].text == "8"
    pd.testing.assert_frame_equal(frame, original)
    pd.testing.assert_frame_equal(summary.data, processed)
