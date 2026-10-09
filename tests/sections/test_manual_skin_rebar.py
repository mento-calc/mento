"""Entrada manual de piel: cantidad exacta, zonas, estados y acero no resistente."""

import math

import matplotlib.pyplot as plt
import pandas as pd
import pytest

from mento import BeamSummary, CageDetailingError, Forces, set_language
from mento.units import MPa, cm, inch, kN, kNm, mm
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
    # Back to the automatic layout: ceil((1152 - 48) / 285) - 1 = 3 rows per side.
    assert b.skin_reinforcement.n_per_side == 3


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


@pytest.mark.parametrize("count,expected", [(3, "passed"), (1, "failed")])
def test_en_manual_without_service_inputs_is_checked_with_the_assumptions(count, expected):
    """Sin datos SLS: x = 0.4 * 1200 = 480 mm, zona 48..720 mm; Eq. (7.1) pide 92.3 mm² por lateral.

    3 Ø10 en 324, 600, 876 mm: dos en la zona, 157 mm²; huecos 276, 276, 120 mm <= 280 mm. Pasa.
    1 Ø10 en 600 mm: 78.5 mm², no alcanza.
    """
    b = en_beam()
    b.set_longitudinal_rebar_bot(n1=4, d_b1=20 * mm)  # Invalidar los datos SLS previos.
    b.check_flexure([Forces(M_y=100 * kNm)])
    b.set_skin_rebar(10 * mm, count, "total")
    assert b.skin_service_cases == ()
    req = b.skin_reinforcement
    assert req.status == "required" and req.manual
    assert req.check_zones[0].upper.to(mm).magnitude == pytest.approx(720)
    assert b.skin_verification_status == expected
    if expected == "failed":
        assert any("area" in failure for failure in req.failures)
    codes = [w.code for w in b.warnings]
    assert "skin_en_service_assumed" in codes
    assert "skin_en_service_pending" not in codes


def test_en_manual_zone_must_cover_the_required_tension_face():
    b = en_beam()
    b.check_flexure([Forces(M_y=100 * kNm)])
    b.set_skin_rebar(10 * mm, 2, "top")
    assert b.skin_verification_status == "failed"
    assert any("bottom tension zone" in reason for reason in b.skin_reinforcement.failures)


def test_manual_skin_is_drawn_even_when_not_required():
    # Below 60 cm mento lays out no skin of its own.
    b = beam(height=55 * cm)
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


def manual_table():
    units = {
        "Label": "",
        "Comb.": "",
        "b": "cm",
        "h": "cm",
        "cc": "mm",
        "Nx": "kN",
        "Vz": "kN",
        "My": "kNm",
        "ns": "",
        "dbs": "mm",
        "sl": "cm",
        "db_piel": "mm",
        "cant_piel_cara": "",
        "posicion": "",
    }
    for i in range(1, 5):
        units[f"n{i}"] = ""
        units[f"db{i}"] = "mm"
    row = {key: 0 for key in units}
    row.update(
        Label="Manual",
        b=30,
        h=120,
        cc=30,
        Nx=0,
        Vz=10,
        My=100,
        ns=1,
        dbs=8,
        sl=20,
        db_piel=10,
        cant_piel_cara=2,
        posicion="bottom",
        n1=4,
        db1=20,
    )
    row["Comb."] = "C1"
    return pd.DataFrame([units, row])


def test_summary_excel_keeps_manual_skin_input(tmp_path):
    materials = beam()
    summary = BeamSummary(materials.concrete, materials.steel_bar, manual_table())
    b = summary.nodes[0].section
    assert b.skin_rebar.cant_piel_cara == 2 and b.skin_rebar.posicion == "bottom"
    summary.design_data = summary.data.copy()
    path = tmp_path / "manual_skin.xlsx"
    summary.export_design(str(path))
    summary.import_design(str(path))
    assert summary.nodes[0].section.skin_rebar == b.skin_rebar


def test_summary_skin_belongs_to_the_beam_of_its_rows():
    """Rows that share a Label are one beam: the skin given on one row is the beam's."""
    materials = beam()
    table = manual_table()
    second = table.iloc[1].copy()
    second["Comb."], second["My"] = "C2", -80
    second["db_piel"], second["cant_piel_cara"], second["posicion"] = "", "", ""
    table = pd.concat([table, second.to_frame().T], ignore_index=True)
    summary = BeamSummary(materials.concrete, materials.steel_bar, table)
    assert len(summary.nodes) == 1
    skin = summary.nodes[0].section.skin_rebar
    assert skin.cant_piel_cara == 2 and skin.posicion == "bottom"

    table.loc[2, ["db_piel", "cant_piel_cara", "posicion"]] = [10, 3, "bottom"]
    with pytest.raises(ValueError, match="different skin reinforcement"):
        BeamSummary(materials.concrete, materials.steel_bar, table)


@pytest.mark.parametrize(
    "column,value", [("cant_piel_cara", 2.5), ("cant_piel_cara", True), ("db_piel", "oops"), ("posicion", "left")]
)
def test_summary_rejects_manual_typos_before_numeric_coercion(column, value):
    table = manual_table()
    table.loc[1, column] = value
    materials = beam()
    with pytest.raises(ValueError):
        BeamSummary(materials.concrete, materials.steel_bar, table)


def test_summary_blank_skin_cells_keep_auto_and_partial_columns_are_rejected():
    materials = beam()
    data = manual_table()
    for col in ("db_piel", "cant_piel_cara", "posicion"):
        data.loc[1, col] = ""
    summary = BeamSummary(materials.concrete, materials.steel_bar, data)
    assert summary.nodes[0].section.skin_rebar is None
    with pytest.raises(ValueError, match="together"):
        BeamSummary(materials.concrete, materials.steel_bar, data.drop(columns="posicion"))


def test_summary_word_reports_insufficient_manual_skin(monkeypatch):
    from mento.results import DocumentBuilder

    materials = beam()
    table = manual_table()
    table.loc[1, "cant_piel_cara"] = 1
    summary = BeamSummary(materials.concrete, materials.steel_bar, table)
    summary.check(capacity_check=True)
    documents = []
    monkeypatch.setattr(DocumentBuilder, "save", lambda self, *_: documents.append(self.doc))
    try:
        set_language("es")
        summary.results_detailed_doc()
        rows = [[c.text for c in row.cells] for t in documents[0].tables for row in t.rows]
        assert any(row[0] == "Manual" and len(row) == 4 and row[2] == "No cumple" for row in rows)
        assert summary.nodes[0].section.skin_verification_status == "failed"
    finally:
        set_language("en")


@pytest.mark.parametrize("automatic", [("", "", ""), (0, 0, ""), (None, 0, None)])
def test_mixed_manual_automatic_excel_roundtrip(tmp_path, automatic):
    materials = beam()
    table = manual_table()
    auto = table.iloc[1].copy()
    auto["Label"] = "Auto"
    for column, value in zip(("db_piel", "cant_piel_cara", "posicion"), automatic):
        auto[column] = value
    table = pd.concat([table, pd.DataFrame([auto])], ignore_index=True)
    summary = BeamSummary(materials.concrete, materials.steel_bar, table)
    manual = summary.nodes[0].section.skin_rebar
    summary.design()
    first, second = tmp_path / "first.xlsx", tmp_path / "second.xlsx"
    summary.export_design(str(first))
    summary.import_design(str(first))
    assert summary.nodes[0].section.skin_rebar == manual
    assert summary.nodes[1].section.skin_rebar is None
    summary.design_data = summary.data.copy()
    summary.export_design(str(second))
    pd.testing.assert_frame_equal(pd.read_excel(first), pd.read_excel(second))


@pytest.mark.parametrize("raw, normalized", [("Bottom", "bottom"), (" total", "total")])
def test_summary_normalizes_manual_skin_position(raw, normalized):
    table = manual_table()
    table.loc[1, "posicion"] = raw
    table.loc[0, "db_piel"] = "cm"
    table.loc[1, "db_piel"] = 1
    materials = beam()
    result = BeamSummary(materials.concrete, materials.steel_bar, table)
    assert result.nodes[0].section.skin_rebar.posicion == normalized
    assert result.nodes[0].section.skin_rebar.db_piel.to("mm").magnitude == 10


def test_unused_skin_columns_need_no_diameter_unit():
    table = manual_table()
    table.loc[0, "db_piel"] = ""
    table.loc[1, ["db_piel", "cant_piel_cara", "posicion"]] = [0, 0, ""]
    materials = beam()
    assert BeamSummary(materials.concrete, materials.steel_bar, table).nodes[0].section.skin_rebar is None


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
        texts = [t.get_text() for t in fig.axes[0].texts]
        assert "2Ø10 por lateral (piel)" in texts
        # The non-conformity is a warning of the beam, not a caption of the drawing.
        assert not any("NO CUMPLE" in t for t in texts)
        assert any(w.code == "skin_reinforcement_failed" for w in b.warnings)
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
