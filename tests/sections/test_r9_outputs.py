"""Salidas coherentes con ramas propuestas e ingresadas."""

import pytest
from mento import set_language
from mento.design_results import format_transverse_rebar
from mento.plots.sections import _cage_lines
from mento.reports.views import verification_table
from tests.sections.test_r9_search import subject
from tests.sections.test_mixed_cage import beam
from mento.units import mm, cm


@pytest.mark.parametrize("language", ["es", "en"])
def test_added_legs_are_pending_and_visible(language):
    b = subject()
    before = b.shear_design
    try:
        set_language(language)
        g = b.detailing_geometry
        warning = next(w for w in b.warnings if w.code == "transverse_legs_added_for_compression_support")
        assert warning.values["input_legs"] == 3 and warning.values["placed_legs"] == 4
        assert "3" in warning.message and "4" in warning.message
        assert b.verification_status["detailing"] == "pending"
        assert verification_table(b)["Status"][1] in ("Pendiente", "Pending")
        assert _cage_lines(b, g)[0].startswith("3 ")
        assert any("A_v" in line for line in _cage_lines(b, g))
        data = g.to_dict("mm")
        assert data["input_legs"] == 3 and data["placed_legs"] == 4
        assert data["calculation_s_w"] == pytest.approx(265)
        assert b.shear_design == before
        b.set_transverse_rebar(legs=4, d_b=10 * mm, s_l=15 * cm)
        from mento import Forces
        from mento.units import kNm, kN

        b.check([Forces(M_y=-1500 * kNm, V_z=80 * kN)])
        assert not any(w.code == "transverse_legs_added_for_compression_support" for w in b.warnings)
        assert b.verification_status["detailing"] == "passed"
    finally:
        set_language("en")


def test_open_leg_notice_is_informative_and_tables_do_not_count_closed_equivalents():
    b = beam(7)
    assert any(w.code == "open_leg_anchorage_outside_model" for w in b.warnings)
    assert b.verification_status["detailing"] == "passed"
    assert "ns" not in b._shear_reinforcement["Variable"]
    assert not any(w.code == "open_leg_anchorage_outside_model" for w in beam(2).warnings)


def test_public_formatter_preserves_integer_odd_legs():
    assert format_transverse_rebar("stirrups", 3.5, "Ø10", "15", "12").startswith("7 legs")
    with pytest.raises(ValueError):
        format_transverse_rebar("stirrups", 3.2, "Ø10", "15", "12")


@pytest.mark.parametrize("language", ["es", "en"])
def test_word_names_entered_and_proposed_legs(monkeypatch, language):
    from mento.results import DocumentBuilder

    b = subject()
    captured = {}
    monkeypatch.setattr(DocumentBuilder, "save", lambda self, filename: captured.update(doc=self.doc))
    try:
        set_language(language)
        b.shear_results_detailed_doc()
        cells = [c.text for table in captured["doc"].tables for row in table.rows for c in row.cells]
        assert any("A_v" in t and "3" in t and "4" in t for t in cells)
        assert any(t in ("Pending", "Pendiente") for t in cells)
    finally:
        set_language("en")
