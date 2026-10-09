"""Entrada manual de piel: cantidad exacta, zonas, estados y acero no resistente."""

import math

import matplotlib.pyplot as plt
import pandas as pd
import pytest

from mento import BeamSummary, CageDetailingError, Forces, set_language
from mento.beam_summary import SKIN_COLUMNS
from mento.units import MPa, cm, inch, kN, kNm, mm
from tests.reports.summary_data import BEAM_UNITS, beams, forces
from tests.sections.test_skin_reinforcement import beam, en_beam


@pytest.mark.parametrize(
    "position,count,moments,expected",
    [
        ("bottom", 2, [100], [324, 600]),
        ("top", 2, [-100], [600, 876]),
        ("total", 3, [100, -80], [324, 600, 876]),
    ],
)
def test_manual_count_is_preserved_and_checked(position, count, moments, expected):
    b = beam()
    b.check([Forces(M_y=m * kNm, V_z=10 * kN) for m in moments])
    before = b.section_geometry.to_dict("mm"), b.reinforcement, b.flexure_checks, b.shear_checks
    b.set_skin_rebar(db_piel=10 * mm, cant_piel_cara=count, posicion=position)
    req = b.skin_reinforcement
    assert req.manual and req.n_per_side == count and not req.failures
    assert [y.to(mm).magnitude for y in req.rows] == pytest.approx(expected)
    assert b.skin_verification_status == "passed"
    assert b.verification_status["detailing"] == "passed"
    assert len(b.detailing_geometry.skin_bars) == 2 * count
    assert (b.section_geometry.to_dict("mm"), b.reinforcement, b.flexure_checks, b.shear_checks) == before
    fig = b.plot(show=False)
    assert sum(p.get_gid() == "skin_bar" for p in fig.axes[0].patches) == 2 * count
    plt.close(fig)


@pytest.mark.parametrize("position,count", [("top", 2), ("total", 1), ("bottom", 0), ("total", 100), ("total", 10**9)])
def test_manual_defect_is_failed_without_redesign(position, count):
    b = beam()
    b.check([Forces(M_y=100 * kNm, V_z=10 * kN)])
    b.set_skin_rebar(10 * mm, count, position)
    assert b.skin_rebar.cant_piel_cara == count
    assert b.skin_verification_status == "failed"
    assert b.verification_status["detailing"] == "failed"
    assert any(w.code in ("skin_reinforcement_failed", "skin_detailing_infeasible") for w in b.warnings)
    if b.skin_reinforcement.rows:
        assert len(b.detailing_geometry.skin_bars) == 2 * count
    else:
        with pytest.raises(CageDetailingError):
            b.detailing_geometry


def test_auto_required_skin_is_not_a_failed_detail():
    b = beam()
    b.check([Forces(M_y=100 * kNm, V_z=10 * kN)])
    assert b.skin_reinforcement.status == "required"
    assert b.skin_verification_status == "passed"
    assert b.verification_status["detailing"] == "passed"


@pytest.mark.parametrize(
    "diameter,count,position",
    [
        (0 * mm, 2, "total"),
        (-10 * mm, 2, "total"),
        (math.nan * mm, 2, "total"),
        (10 * MPa, 2, "total"),
        (10 * mm, True, "total"),
        (10 * mm, 1.5, "total"),
        (10 * mm, -1, "total"),
        (10 * mm, 2, "left"),
        (6 * mm, 2, "total"),
    ],
)
def test_invalid_input_does_not_replace_previous_manual_skin(diameter, count, position):
    b = beam()
    b.set_skin_rebar(10 * mm, 3, "total")
    original = b.skin_rebar
    with pytest.raises(ValueError):
        b.set_skin_rebar(diameter, count, position)
    assert b.skin_rebar == original


def test_manual_input_is_independent_and_can_be_cleared():
    b = beam()
    b.check_flexure([Forces(M_y=100 * kNm)])
    diameter = 10 * mm
    original_setting = b.settings.skin_bar_diameter
    b.set_skin_rebar(diameter, 3, "total")
    diameter.ito(inch)
    readback = b.skin_rebar
    readback.db_piel.ito(inch)
    assert b.skin_rebar.db_piel.units == (1 * mm).units
    assert b.settings.skin_bar_diameter == original_setting
    b.clear_skin_rebar()
    assert b.skin_rebar is None
    assert not b.skin_reinforcement.manual
    assert b.skin_reinforcement.n_per_side == 2


@pytest.mark.parametrize("count,expected", [(6, "passed"), (1, "failed")])
def test_en_manual_area_is_checked_per_service_zone(count, expected):
    b = en_beam()
    b.check_flexure([Forces(M_y=100 * kNm), Forces(M_y=-80 * kNm)])
    b.set_skin_rebar(10 * mm, count, "total")
    assert b.skin_verification_status == expected
    assert b.skin_reinforcement.n_per_side == count
    if expected == "failed":
        assert any("area" in failure for failure in b.skin_reinforcement.failures)
    else:
        assert len(b.detailing_geometry.skin_bars) == 2 * count


def test_en_manual_missing_service_inputs_remains_pending():
    b = en_beam()
    b.set_longitudinal_rebar_bot(n1=4, d_b1=20 * mm)  # Invalidar los datos SLS previos.
    b.check_flexure([Forces(M_y=100 * kNm)])
    b.set_skin_rebar(10 * mm, 3, "total")
    assert b.skin_verification_status == "pending"
    assert any(w.code == "skin_en_service_pending" for w in b.warnings)


def test_en_manual_zone_must_cover_the_required_tension_face():
    b = en_beam()
    b.check_flexure([Forces(M_y=100 * kNm)])
    b.set_skin_rebar(10 * mm, 2, "top")
    assert b.skin_verification_status == "failed"
    assert any("bottom tension zone" in reason for reason in b.skin_reinforcement.failures)


def test_manual_skin_is_drawn_even_when_not_required():
    b = beam(height=60 * cm)
    b.set_skin_rebar(10 * mm, 2, "total")
    assert b.skin_reinforcement.status == "not_required"
    assert len(b.detailing_geometry.skin_bars) == 4
    assert b.skin_verification_status == "passed"


def test_skin_without_stirrups_is_drawn_and_checked():
    b = beam()
    b.set_transverse_rebar(0, 0 * mm, 0 * cm)
    b.check_flexure([Forces(M_y=100 * kNm)])
    b.set_skin_rebar(10 * mm, 3, "total")
    assert b.skin_verification_status == "passed"
    assert len(b.detailing_geometry.skin_bars) == 6


def test_skin_is_not_passed_when_detailing_omits_the_bars(monkeypatch):
    b = beam()
    b.check_flexure([Forces(M_y=100 * kNm)])
    b.set_skin_rebar(10 * mm, 3, "total")
    monkeypatch.setattr(type(b), "detailing_geometry", property(lambda self: self.section_geometry))
    assert b.skin_verification_status == "pending"
    assert any(w.code == "skin_detailing_pending" for w in b.warnings)


def test_manual_failure_reason_is_localized():
    b = beam()
    b.check_flexure([Forces(M_y=100 * kNm)])
    b.set_skin_rebar(10 * mm, 2, "top")
    try:
        set_language("es")
        message = next(w.message for w in b.warnings if w.code == "skin_reinforcement_failed")
        assert "zona inferior traccionada" in message
    finally:
        set_language("en")


SKIN_UNITS = {**BEAM_UNITS, "db_piel": "mm", "cant_piel_cara": "", "posicion": ""}


def manual_tables(**skin):
    """A CIRSOC 30x120 beam with Ø10 manual skin, two per side at the bottom: the two tables of BeamSummary."""
    row = {"Label": "Manual", "n1_bot": 4, "db1_bot": 20, "db_piel": 10, "cant_piel_cara": 2, "posicion": "bottom"}
    sections = beams([{**row, **skin}], units=SKIN_UNITS, b=30, h=120, cc=30, legs=2, dbs=8, sl=20)
    return sections, forces([{"Label": "Manual", "Comb.": "C1", "Vz": 10, "My": 100}])


def test_summary_excel_keeps_manual_skin_input(tmp_path):
    materials = beam()
    summary = BeamSummary(materials.concrete, materials.steel_bar, *manual_tables())
    b = summary.nodes[0].section
    assert b.skin_rebar.cant_piel_cara == 2 and b.skin_rebar.posicion == "bottom"
    path = tmp_path / "manual_skin.xlsx"
    summary.to_excel(path)
    assert list(pd.read_excel(path, sheet_name="Sections").iloc[1][list(SKIN_COLUMNS)]) == [10, 2, "bottom"]
    summary.import_design(path)
    assert summary.nodes[0].section.skin_rebar == b.skin_rebar


@pytest.mark.parametrize(
    "column,value", [("cant_piel_cara", 2.5), ("cant_piel_cara", True), ("db_piel", "oops"), ("posicion", "left")]
)
def test_summary_rejects_manual_typos(column, value):
    materials = beam()
    with pytest.raises(ValueError):
        BeamSummary(materials.concrete, materials.steel_bar, *manual_tables(**{column: value}))


def test_summary_blank_skin_cells_keep_auto_and_a_position_needs_its_diameter():
    materials = beam()
    summary = BeamSummary(
        materials.concrete, materials.steel_bar, *manual_tables(db_piel=0, cant_piel_cara=0, posicion="")
    )
    assert summary.nodes[0].section.skin_rebar is None
    # No section uses manual skin, and the table gave the columns: they are written back, empty.
    assert list(summary.sections_table.iloc[1][list(SKIN_COLUMNS)]) == [0, 0, ""]
    with pytest.raises(ValueError, match="db_piel"):
        BeamSummary(materials.concrete, materials.steel_bar, *manual_tables(db_piel=0))


def test_summary_word_reports_insufficient_manual_skin(monkeypatch):
    from mento.results import DocumentBuilder

    materials = beam()
    summary = BeamSummary(materials.concrete, materials.steel_bar, *manual_tables(cant_piel_cara=1))
    summary.check()
    documents = []
    monkeypatch.setattr(DocumentBuilder, "save", lambda self, *_: documents.append(self.doc))
    try:
        set_language("es")
        summary.results_detailed_doc()
        assert summary.nodes[0].section.skin_verification_status == "failed"
        rows = [[c.text for c in row.cells] for t in documents[0].tables for row in t.rows]
        assert any(row[0] == "Manual" and "piel" in " ".join(row).lower() for row in rows)
    finally:
        set_language("en")


def test_mixed_manual_and_automatic_skin_roundtrip(tmp_path):
    materials = beam()
    sections, rows = manual_tables()
    auto = sections.iloc[1].copy()
    auto["Label"], auto["db_piel"], auto["cant_piel_cara"], auto["posicion"] = "Auto", 0, 0, ""
    sections = pd.concat([sections, pd.DataFrame([auto])], ignore_index=True)
    rows = pd.concat([rows, rows.iloc[[1]].assign(Label="Auto")], ignore_index=True)
    summary = BeamSummary(materials.concrete, materials.steel_bar, sections, rows)
    manual = summary.nodes[0].section.skin_rebar
    summary.design()
    first, second = tmp_path / "first.xlsx", tmp_path / "second.xlsx"
    summary.to_excel(first)
    summary.import_design(first)
    assert summary.nodes[0].section.skin_rebar == manual
    assert summary.nodes[1].section.skin_rebar is None
    summary.to_excel(second)
    for sheet in ("Sections", "Forces"):
        pd.testing.assert_frame_equal(pd.read_excel(first, sheet_name=sheet), pd.read_excel(second, sheet_name=sheet))


@pytest.mark.parametrize("raw, normalized", [("Bottom", "bottom"), (" total", "total")])
def test_summary_normalizes_manual_skin_position(raw, normalized):
    sections, rows = manual_tables(posicion=raw, db_piel=1)
    sections.loc[0, "db_piel"] = "cm"
    materials = beam()
    result = BeamSummary(materials.concrete, materials.steel_bar, sections, rows)
    assert result.nodes[0].section.skin_rebar.posicion == normalized
    assert result.nodes[0].section.skin_rebar.db_piel.to("mm").magnitude == 10


def test_a_table_without_skin_columns_writes_none():
    materials = beam()
    sections, rows = manual_tables()
    summary = BeamSummary(materials.concrete, materials.steel_bar, sections.drop(columns=list(SKIN_COLUMNS)), rows)
    assert summary.nodes[0].section.skin_rebar is None
    assert not set(SKIN_COLUMNS) & set(summary.sections_table.columns)


def test_nonconforming_but_fitting_manual_skin_is_drawn():
    b = beam()
    b.check_flexure([Forces(M_y=100 * kNm)])
    b.set_skin_rebar(10 * mm, 2, "top")
    assert b.skin_verification_status == "failed"
    assert len(b.detailing_geometry.skin_bars) == 4
    try:
        set_language("es")
        fig = b.plot(show=False)
        assert sum(p.get_gid() == "skin_bar" for p in fig.axes[0].patches) == 4
        assert any("NO CUMPLE" in t.get_text() for t in fig.axes[0].texts)
        plt.close(fig)
    finally:
        set_language("en")


def test_unsupported_en_axial_preserves_manual_geometry_but_not_approval():
    b = en_beam()
    b.check_flexure([Forces(M_y=100 * kNm, N_x=50 * kN)])
    b.set_skin_rebar(10 * mm, 3, "total")
    assert b.skin_verification_status == "pending"
    assert len(b.detailing_geometry.skin_bars) == 6
    assert any(w.code == "skin_en_axial_unsupported" for w in b.warnings)
    b.set_skin_rebar(10 * mm, 100, "total")
    assert b.skin_verification_status == "failed"
