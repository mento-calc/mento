"""Language of the detailed reports.

The tests that matter most here are the coverage ones: they run real checks and
assert the Spanish catalog carries every label the report builders emit, so a
label added to ``mento/codes`` without a translation fails the suite instead of
silently printing English inside a Spanish report.

Assert a translated string as ``ES["<english>"]``, never as a Spanish literal.
The wording of the catalog is data an engineer is expected to revise — pinning
it here would turn every terminology fix into a broken test. What these tests
own is that the string is *translated*, not how it reads.
"""

import ast
import re
from pathlib import Path
from typing import Any, Dict, Generator, List, Set

import pandas as pd
import pytest

from mento import design_warnings, i18n
from mento.beam import RectangularBeam
from mento.beam_summary import BeamSummary
from mento.codes.registry import design_code
from mento.forces import Forces
from mento.i18n import (
    ES,
    available_languages,
    get_language,
    set_language,
    translate,
    translate_dataframe,
    translate_table,
)
from mento.material import (
    Concrete_ACI_318_19,
    Concrete_CIRSOC_201_25,
    Concrete_EN_1992_2004,
    SteelBar,
)
from mento.node import Node
from mento.results import DocumentBuilder, TablePrinter
from mento.shear_wall import ShearWall
from mento.shear_wall_summary import ShearWallSummary
from mento.slab_summary import OneWaySlabSummary
from mento.summary_tables import split_single_table
from mento.slab import OneWaySlab
from mento.units import MPa, cm, kN, kNm, m, mm
from tests.reports.summary_data import forces, slabs


@pytest.fixture(autouse=True)
def restore_language() -> Generator[None, None, None]:
    """Language is package-wide state; never let it leak into another test."""
    previous = get_language()
    yield
    set_language(previous)


# ---------------------------------------------------------------------------
# set_language / get_language
# ---------------------------------------------------------------------------


class TestLanguageSelection:
    def test_default_is_english(self) -> None:
        assert get_language() == "en"

    def test_set_language_switches(self) -> None:
        set_language("es")
        assert get_language() == "es"

    def test_unknown_language_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown language"):
            set_language("fr")

    def test_unknown_language_leaves_current_one(self) -> None:
        set_language("es")
        with pytest.raises(ValueError):
            set_language("de")
        assert get_language() == "es"

    def test_available_languages(self) -> None:
        assert available_languages() == ("en", "es")


# ---------------------------------------------------------------------------
# translate
# ---------------------------------------------------------------------------


class TestTranslate:
    def test_translates_known_string(self) -> None:
        assert translate("Section height", "es") == "Altura de la sección"

    def test_unknown_string_falls_back_to_input(self) -> None:
        assert translate("Torsional constant", "es") == "Torsional constant"

    def test_english_returns_input(self) -> None:
        assert translate("Section height", "en") == "Section height"

    def test_uses_current_language_when_not_given(self) -> None:
        set_language("es")
        assert translate("Section height") == "Altura de la sección"

    def test_fills_placeholders(self) -> None:
        assert translate("Beam {label} shear check", "es", label="V12") == "Verificación a corte de viga V12"

    def test_fills_placeholders_in_english(self) -> None:
        assert translate("Beam {label} shear check", "en", label="V12") == "Beam V12 shear check"


# ---------------------------------------------------------------------------
# translate_table / translate_dataframe
# ---------------------------------------------------------------------------


def _table() -> Dict[str, List[Any]]:
    return {
        "Materials": ["Section height", "Concrete strength"],
        "Variable": ["h", "fc"],
        "Value": [50.0, 25.0],
        "Unit": ["cm", "MPa"],
    }


class TestTranslateTable:
    def test_translates_headers_and_label_column(self) -> None:
        out = translate_table(_table(), "es")
        assert list(out) == ["Materiales", "Variable", "Valor", "Unidad"]
        assert out["Materiales"] == ["Altura de la sección", "Resistencia del hormigón"]

    def test_leaves_values_and_units_alone(self) -> None:
        out = translate_table(_table(), "es")
        assert out["Valor"] == [50.0, 25.0]
        assert out["Unidad"] == ["cm", "MPa"]

    def test_does_not_mutate_the_input(self) -> None:
        data = _table()
        translate_table(data, "es")
        assert data == _table()

    def test_empty_table(self) -> None:
        assert translate_table({}, "es") == {}

    def test_non_string_labels_survive(self) -> None:
        out = translate_table({"Check": [1, None, "Section height"]}, "es")
        assert out["Verificación"] == [1, None, "Altura de la sección"]


class TestTranslateDataframe:
    def test_translates_headers_and_label_column(self) -> None:
        out = translate_dataframe(pd.DataFrame(_table()), "es")
        assert list(out.columns) == ["Materiales", "Variable", "Valor", "Unidad"]
        assert list(out["Materiales"]) == ["Altura de la sección", "Resistencia del hormigón"]

    def test_does_not_mutate_the_input(self) -> None:
        df = pd.DataFrame(_table())
        translate_dataframe(df, "es")
        assert list(df.columns) == ["Materials", "Variable", "Value", "Unit"]
        assert list(df["Materials"]) == ["Section height", "Concrete strength"]

    def test_empty_dataframe(self) -> None:
        df = pd.DataFrame()
        assert translate_dataframe(df, "es").empty


# ---------------------------------------------------------------------------
# Presentation classes
# ---------------------------------------------------------------------------


class TestPresentationClasses:
    def test_table_printer_defaults_to_english(self) -> None:
        assert TablePrinter("MATERIALS").title == "MATERIALS"

    def test_table_printer_translates_title(self) -> None:
        assert TablePrinter("MATERIALS", "es").title == ES["MATERIALS"]

    def test_table_printer_prints_spanish(self, capsys: pytest.CaptureFixture) -> None:
        TablePrinter("MATERIALS", "es").print_table_data(_table(), headers="keys")
        out = capsys.readouterr().out
        assert ES["Section height"] in out
        assert "Section height" not in out

    def test_table_printer_prints_english_by_default(self, capsys: pytest.CaptureFixture) -> None:
        TablePrinter("MATERIALS").print_table_data(_table(), headers="keys")
        assert "Section height" in capsys.readouterr().out

    def test_document_builder_defaults_to_english(self) -> None:
        builder = DocumentBuilder(title="Concrete beam shear check")
        builder.add_heading("Materials", level=2)
        assert builder.doc.paragraphs[-1].text == "Materials"

    def test_document_builder_translates_heading(self) -> None:
        builder = DocumentBuilder(title="Concrete beam shear check", language="es")
        builder.add_heading("Materials", level=2)
        assert builder.doc.paragraphs[-1].text == "Materiales"

    def test_document_builder_fills_heading_placeholders(self) -> None:
        builder = DocumentBuilder(title="Concrete beam shear check", language="es")
        builder.add_heading("Beam {label} shear check", level=1, label="V12")
        assert builder.doc.paragraphs[-1].text == "Verificación a corte de viga V12"

    def test_document_builder_translates_table(self) -> None:
        builder = DocumentBuilder(title="Concrete beam shear check", language="es")
        builder.add_table_data(pd.DataFrame(_table()))
        table = builder.doc.tables[-1]
        assert table.cell(0, 0).text == "Materiales"
        assert table.cell(1, 0).text == "Altura de la sección"

    def test_document_builder_table_untouched_in_english(self) -> None:
        builder = DocumentBuilder(title="Concrete beam shear check")
        builder.add_table_data(pd.DataFrame(_table()))
        table = builder.doc.tables[-1]
        assert table.cell(0, 0).text == "Materials"
        assert table.cell(1, 0).text == "Section height"


# ---------------------------------------------------------------------------
# Catalog coverage against the real reports
# ---------------------------------------------------------------------------

STEEL = SteelBar(name="ADN 420", f_y=420 * MPa)


def _beam(concrete: Any, label: str) -> RectangularBeam:
    beam = RectangularBeam(
        label=label,
        concrete=concrete,
        steel_bar=STEEL,
        width=20 * cm,
        height=50 * cm,
        c_c=25 * mm,
    )
    Node(
        section=beam,
        forces=[
            Forces(label="C1", V_z=100 * kN, M_y=150 * kNm),
            Forces(label="C2", V_z=80 * kN, M_y=-100 * kNm),
        ],
    ).design()
    return beam


def _slab() -> OneWaySlab:
    slab = OneWaySlab(
        label="S1",
        concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
        steel_bar=STEEL,
        width=100 * cm,
        height=20 * cm,
        c_c=25 * mm,
    )
    Node(section=slab, forces=[Forces(label="C1", V_z=40 * kN, M_y=30 * kNm)]).design()
    return slab


def _wall() -> ShearWall:
    wall = ShearWall(
        label="W1",
        concrete=Concrete_ACI_318_19(name="C25", f_c=25 * MPa),
        steel_bar=STEEL,
        thickness=25 * cm,
        length=4.0 * m,
        height=3.5 * m,
        c_c=20 * mm,
    )
    wall.set_horizontal_rebar(d_b=10 * mm, s=20 * cm)
    wall.set_vertical_rebar(d_b=10 * mm, s=20 * cm)
    wall.check_shear([Forces(label="C1", V_z=500 * kN)])
    return wall


def _rendered_strings(monkeypatch: pytest.MonkeyPatch, render: Any) -> Set[str]:
    """Every string ``render`` would put in front of a user.

    Stands in for TablePrinter and DocumentBuilder so nothing is printed or
    written to disk, and records the headers, row labels, headings and
    paragraphs the report asked for.
    """
    found: Set[str] = set()

    def record(data: Dict[str, List[Any]]) -> None:
        columns = list(data)
        found.update(str(c) for c in columns)
        if columns:
            found.update(v for v in data[columns[0]] if isinstance(v, str) and v.strip())

    def tp_init(self: Any, title: str = None, language: str = "en") -> None:  # type: ignore[assignment]
        if title:
            found.add(title)

    def tp_print(self: Any, data: Dict[str, List[Any]], **kwargs: Any) -> None:
        record(data)

    document_init = DocumentBuilder.__init__

    def db_init(self: Any, title: str, font_name: str = "Lato", font_size: int = 9, language: str = "en") -> None:
        # The real one, so the builder has a document: the summary reports
        # measure their column widths against the page. Nothing reaches disk --
        # `save` is stubbed out below.
        document_init(self, title, font_name, font_size, language)
        found.add(title)

    def db_heading(self: Any, text: str, level: int, font_size: float = 10, **fields: Any) -> None:
        found.add(text)

    def db_text(self: Any, text: str, **fields: Any) -> None:
        found.add(text)

    def db_table(self: Any, df: pd.DataFrame, *args: Any, **kwargs: Any) -> None:
        record({str(c): list(df[c]) for c in df.columns})

    monkeypatch.setattr(TablePrinter, "__init__", tp_init)
    monkeypatch.setattr(TablePrinter, "print_table_data", tp_print)
    monkeypatch.setattr(TablePrinter, "print_table_min_max", tp_print)
    monkeypatch.setattr(DocumentBuilder, "__init__", db_init)
    monkeypatch.setattr(DocumentBuilder, "add_heading", db_heading)
    monkeypatch.setattr(DocumentBuilder, "add_text", db_text)
    monkeypatch.setattr(DocumentBuilder, "add_table_data", db_table)
    monkeypatch.setattr(DocumentBuilder, "add_table_dcr", db_table)
    monkeypatch.setattr(DocumentBuilder, "add_table_min_max", db_table)
    monkeypatch.setattr(DocumentBuilder, "add_table_status", db_table)
    monkeypatch.setattr(DocumentBuilder, "save", lambda self, filename: None)

    render()
    return found


def _report_all(section: Any, flexure: bool = True) -> None:
    if flexure:
        section.flexure_results_detailed()
        section.flexure_results_detailed_doc()
    section.shear_results_detailed()
    section.shear_results_detailed_doc()


CASES = [
    pytest.param(lambda: _beam(Concrete_ACI_318_19(name="H25", f_c=25 * MPa), "B1"), True, id="beam-ACI"),
    pytest.param(lambda: _beam(Concrete_CIRSOC_201_25(name="H25", f_c=25 * MPa), "B2"), True, id="beam-CIRSOC"),
    pytest.param(lambda: _beam(Concrete_EN_1992_2004(name="C25", f_c=25 * MPa), "B3"), True, id="beam-EN"),
    pytest.param(_slab, True, id="slab"),
    pytest.param(_wall, False, id="shear-wall"),
]


class TestCatalogCoverage:
    @pytest.mark.parametrize("build,flexure", CASES)
    def test_spanish_catalog_covers_every_report_string(
        self, build: Any, flexure: bool, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        section = build()
        strings = _rendered_strings(monkeypatch, lambda: _report_all(section, flexure))
        missing = sorted(s for s in strings if s not in ES)
        assert not missing, f"No Spanish translation for: {missing}"

    def test_the_harness_actually_sees_the_report(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Guard against a silently empty coverage test."""
        section = _beam(Concrete_ACI_318_19(name="H25", f_c=25 * MPa), "B1")
        strings = _rendered_strings(monkeypatch, lambda: _report_all(section))
        assert "Section height" in strings
        assert len(strings) > 50

    def test_catalog_has_no_untranslated_entries(self) -> None:
        """An entry mapping to itself is a leftover, unless the word is the same
        in both languages — which has to be declared here on purpose."""
        same_in_both = {"Variable"}
        assert [k for k, v in ES.items() if k == v and k not in same_in_both] == []


def _detailing_error_messages() -> List[ast.expr]:
    """The message argument of every ``CageDetailingError(...)`` in mento, as written in the source."""
    found: List[ast.expr] = []
    for path in sorted(Path(i18n.__file__).parent.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "CageDetailingError" and node.args:
                found.append(node.args[0])
    return found


class TestWarningReasonCoverage:
    """A cage or skin warning quotes, as its ``{reason}``, the text of the
    ``CageDetailingError`` that stopped the detailing. One added without a
    translation fails here instead of leaving English inside a Spanish warning."""

    def test_every_warning_template_is_in_the_catalog(self) -> None:
        texts = [*design_warnings._MESSAGES.values(), *design_warnings._COMPRESSION_REASONS.values()]
        assert sorted(s for s in texts if s not in ES) == []

    def test_every_detailing_error_text_is_in_the_catalog(self) -> None:
        literals = {m.value for m in _detailing_error_messages() if isinstance(m, ast.Constant)}
        assert len(literals) > 30, "the scan saw no errors"
        assert sorted(s for s in literals if s not in ES) == []

    def test_every_built_detailing_error_text_is_in_the_catalog(self) -> None:
        """An f-string is in the catalog as the texts it can produce, so one of its
        entries has to fit it. The exception quotes the label the user gave a
        service case, which no catalog can hold, and stays English."""
        quotes_user_text = {"Skin service case {}: steel stress exceeds f_yk."}
        built = [m for m in _detailing_error_messages() if isinstance(m, ast.JoinedStr)]
        assert built, "the scan saw no f-strings"
        missing = []
        for message in built:
            parts = [v.value if isinstance(v, ast.Constant) else None for v in message.values]
            shape = "".join("{}" if part is None else part for part in parts)
            pattern = "".join(".+" if part is None else re.escape(part) for part in parts)
            if shape not in quotes_user_text and not any(re.fullmatch(pattern, key) for key in ES):
                missing.append(shape)
        assert missing == []

    def test_the_bend_table_error_is_in_the_catalog(self) -> None:
        """The one reason that starts as a ``ValueError`` of a code's bend hook and is passed on."""
        concrete = Concrete_ACI_318_19(name="H25", f_c=25 * MPa)
        with pytest.raises(ValueError) as error:
            design_code(concrete).stirrup_bend_inner_diameter(concrete, 60 * mm)
        assert str(error.value) in ES

    def test_a_cage_warning_words_its_reason_in_spanish(self) -> None:
        """A 12 cm web cannot take the bends of a Ø12 stirrup: the reason follows the language."""
        beam = RectangularBeam(
            label="B1",
            concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
            steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
            width=12 * cm,
            height=100 * cm,
            c_c=40 * mm,
        )
        beam.set_transverse_rebar(n_stirrups=1, d_b=12 * mm, s_l=15 * cm)
        beam.set_longitudinal_rebar_bot(n1=2, d_b1=16 * mm)
        beam.set_longitudinal_rebar_top(n1=2, d_b1=12 * mm)
        node = Node(section=beam, forces=[Forces(label="U", V_z=50 * kN, M_y=60 * kNm)])
        node.check()
        reason = "The stirrup is too narrow for its required bends."

        def message() -> str:
            return next(w.message for w in node.warnings if w.code == "cage_detailing_infeasible")

        assert message().endswith(reason)
        set_language("es")
        assert message() == ES["The base cage cannot be detailed: {reason}"].format(reason=ES[reason])

    def test_no_warning_names_an_attribute_of_the_api(self) -> None:
        """A message is read by whoever reads the report, who has no ``beam`` to look into."""
        texts = [*design_warnings._MESSAGES.values(), *(ES[s] for s in design_warnings._MESSAGES.values())]
        assert [s for s in texts if "detailing_geometry" in s or "section_geometry" in s] == []


# ---------------------------------------------------------------------------
# End to end
# ---------------------------------------------------------------------------


class TestEndToEnd:
    def test_console_report_is_spanish(self, capsys: pytest.CaptureFixture) -> None:
        beam = _beam(Concrete_CIRSOC_201_25(name="H25", f_c=25 * MPa), "V12")
        capsys.readouterr()
        set_language("es")
        beam.shear_results_detailed()
        out = capsys.readouterr().out
        assert ES["===== BEAM SHEAR DETAILED RESULTS ====="] in out
        assert ES["Concrete strength"] in out
        assert ES["Demand Capacity Ratio"] in out
        assert "Concrete strength" not in out
        assert "Demand Capacity Ratio" not in out

    def test_console_report_is_english_by_default(self, capsys: pytest.CaptureFixture) -> None:
        beam = _beam(Concrete_CIRSOC_201_25(name="H25", f_c=25 * MPa), "V12")
        capsys.readouterr()
        beam.shear_results_detailed()
        out = capsys.readouterr().out
        assert "Concrete strength" in out
        assert ES["Concrete strength"] not in out

    def test_word_report_is_spanish(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
        beam = _beam(Concrete_CIRSOC_201_25(name="H25", f_c=25 * MPa), "V12")
        saved: Dict[str, Any] = {}
        monkeypatch.setattr(
            DocumentBuilder, "save", lambda self, filename: saved.update(doc=self.doc, filename=filename)
        )
        set_language("es")
        beam.shear_results_detailed_doc()

        text = "\n".join(p.text for p in saved["doc"].paragraphs)
        text += "\n" + "\n".join(c.text for t in saved["doc"].tables for r in t.rows for c in r.cells)
        assert ES["Beam {label} shear check"].format(label="V12") in text
        assert "Generado con mento" in text
        assert ES["Concrete strength"] in text
        assert "Concrete strength" not in text

    def test_word_file_name_stays_english(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """File names are not translated, so a project keeps one naming scheme."""
        beam = _beam(Concrete_CIRSOC_201_25(name="H25", f_c=25 * MPa), "V12")
        saved: Dict[str, Any] = {}
        monkeypatch.setattr(DocumentBuilder, "save", lambda self, filename: saved.update(filename=filename))
        set_language("es")
        beam.shear_results_detailed_doc()
        assert saved["filename"] == "Beam V12 shear check CIRSOC 201-25.docx"

    def test_slab_inherits_the_language(self, capsys: pytest.CaptureFixture) -> None:
        slab = _slab()
        capsys.readouterr()
        set_language("es")
        slab.flexure_results_detailed()
        assert ES["Section height"] in capsys.readouterr().out

    def test_slab_is_reported_as_a_slab(self, capsys: pytest.CaptureFixture) -> None:
        """A one-way slab must not be titled as a beam in either language."""
        slab = _slab()
        capsys.readouterr()
        slab.flexure_results_detailed()
        assert "===== SLAB FLEXURE DETAILED RESULTS =====" in capsys.readouterr().out

        set_language("es")
        slab.shear_results_detailed()
        out = capsys.readouterr().out
        assert ES["===== SLAB SHEAR DETAILED RESULTS ====="] in out
        assert "VIGA" not in out

    def test_slab_word_report_is_titled_as_a_slab(self, monkeypatch: pytest.MonkeyPatch) -> None:
        slab = _slab()
        saved: Dict[str, Any] = {}
        monkeypatch.setattr(
            DocumentBuilder, "save", lambda self, filename: saved.update(doc=self.doc, filename=filename)
        )
        slab.flexure_results_detailed_doc()
        assert saved["filename"] == "Slab S1 flexure check ACI 318-19.docx"
        assert "Slab S1 flexure check" in "\n".join(p.text for p in saved["doc"].paragraphs)

        set_language("es")
        slab.flexure_results_detailed_doc()
        assert saved["filename"] == "Slab S1 flexure check ACI 318-19.docx"
        expected = ES["Slab {label} flexure check"].format(label="S1")
        assert expected in "\n".join(p.text for p in saved["doc"].paragraphs)

    def test_beam_is_still_reported_as_a_beam(self, capsys: pytest.CaptureFixture) -> None:
        beam = _beam(Concrete_ACI_318_19(name="H25", f_c=25 * MPa), "B1")
        capsys.readouterr()
        beam.flexure_results_detailed()
        assert "===== BEAM FLEXURE DETAILED RESULTS =====" in capsys.readouterr().out

    def test_flexure_forces_header_matches_the_shear_one(self, capsys: pytest.CaptureFixture) -> None:
        """Both detailed tables spell the forces header the same way."""
        beam = _beam(Concrete_ACI_318_19(name="H25", f_c=25 * MPa), "B1")
        capsys.readouterr()
        beam.flexure_results_detailed()
        out = capsys.readouterr().out
        assert "Design forces" in out
        assert "Design_forces" not in out

    def test_shear_wall_report_is_spanish(self, capsys: pytest.CaptureFixture) -> None:
        wall = _wall()
        capsys.readouterr()
        set_language("es")
        wall.shear_results_detailed()
        out = capsys.readouterr().out
        assert "RESULTADOS DETALLADOS DE TABIQUE" in out
        assert "Espesor del tabique" in out
        assert "Wall thickness" not in out

    def test_summary_reports_stay_english(self) -> None:
        """Summaries are out of scope; they must not pick the language up."""
        set_language("es")
        assert DocumentBuilder(title="Beam Summary Analysis", font_size=8).language == i18n.DEFAULT_LANGUAGE


# ---------------------------------------------------------------------------
# Summaries
# ---------------------------------------------------------------------------
#
# `BeamSummary` and `ShearWallSummary` return DataFrames rather than printing,
# so they translate on the way out instead of going through `TablePrinter`.
# Only the columns holding words are translated: the symbol columns are
# variable names, and a report that renamed `Av` would be reporting something
# else.


def _beam_summary() -> BeamSummary:
    data = {
        "Label": ["", "V101", "V102"],
        "Comb.": ["", "ELU 1", "ELU 2"],
        "b": ["cm", 20, 20],
        "h": ["cm", 50, 50],
        "cc": ["mm", 25, 25],
        "Nx": ["kN", 0, 0],
        "Vz": ["kN", 20, 50],
        "My": ["kNm", 30, -35],
        "ns": ["", 1.0, 1.0],
        "dbs": ["mm", 6, 6],
        "sl": ["cm", 20, 20],
        "n1": ["", 2.0, 2.0],
        "db1": ["mm", 12, 12],
        "n2": ["", 1.0, 1.0],
        "db2": ["mm", 10, 16],
        "n3": ["", 2.0, 2.0],
        "db3": ["mm", 12, 12],
        "n4": ["", 0, 0],
        "db4": ["mm", 0, 0],
    }
    return BeamSummary(
        Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
        SteelBar(name="ADN 420", f_y=420 * MPa),
        *split_single_table(pd.DataFrame(data), "beam"),
    )


def _wall_summary() -> ShearWallSummary:
    data = {
        "Level": ["", "Level 1", "Level 1"],
        "Label": ["", "M1", "M1"],
        "Comb.": ["", "ELU 1", "ELU 2"],
        "t": ["cm", 20, 20],
        "lw": ["m", 3.0, 3.0],
        "hw": ["m", 3.0, 3.0],
        "cc": ["mm", 25, 25],
        "Nx": ["kN", 0, -301],
        "Vz": ["kN", 264, 152],
        "My": ["kNm", -172, -234],
        "dbh": ["mm", 0, 0],
        "sh": ["cm", 0, 0],
        "dbv": ["mm", 0, 0],
        "sv": ["cm", 0, 0],
    }
    summary = ShearWallSummary(
        Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
        SteelBar(name="ADN 420", f_y=420 * MPa),
        *split_single_table(pd.DataFrame(data), "wall"),
    )
    summary.design()
    return summary


def _slab_summary(with_warnings: bool) -> OneWaySlabSummary:
    """Two strips, designed; ``with_warnings`` gives one a layer past its maximum spacing afterwards."""
    sections = slabs([{"Label": "L1"}, {"Label": "L2"}], units={"Label": "", "b": "cm", "h": "cm", "cc": "mm"})
    rows = forces(
        [{"Label": "L1", "Comb.": "C", "Vz": 20, "My": 15}, {"Label": "L2", "Comb.": "C", "Vz": 20, "My": -12}]
    )
    summary = OneWaySlabSummary(
        Concrete_ACI_318_19(name="H25", f_c=25 * MPa), SteelBar(name="ADN 420", f_y=420 * MPa), sections, rows
    )
    summary.design()
    if with_warnings:
        summary.nodes[0].section.set_slab_longitudinal_rebar_bot(d_b1=12 * mm, s_b1=40 * cm)
    return summary


class TestSummaryTables:
    def test_beam_check_headers_are_translated(self) -> None:
        set_language("es")
        columns = list(_beam_summary().check().columns)
        assert ES["Beam"] in columns
        assert ES["Ok?"] in columns
        assert "Beam" not in columns

    def test_beam_check_keeps_variable_names(self) -> None:
        """`Av` and `DCRv` name quantities, not prose: they read the same in both."""
        set_language("es")
        columns = list(_beam_summary().check().columns)
        for symbol in ("b×h", "As,top", "As,bot", "Av", "DCRv"):
            assert symbol in columns

    def test_flexure_results_translate_the_position_column(self) -> None:
        """The header and its values: a row reading "Top" under "Posición" is
        the half-translated output this covers."""
        set_language("es")
        df = _beam_summary().flexure_results()
        assert ES["Position"] in df.columns
        positions = set(df[ES["Position"]])
        assert ES["Top"] in positions
        assert ES["Bottom"] in positions
        assert "Top" not in positions

    def test_shear_results_are_translated(self) -> None:
        set_language("es")
        columns = list(_beam_summary().shear_results().columns)
        assert ES["Label"] in columns
        assert "Label" not in columns

    def test_wall_check_is_translated(self) -> None:
        set_language("es")
        columns = list(_wall_summary().check().columns)
        assert ES["Level"] in columns
        assert ES["Status"] in columns
        assert "Status" not in columns

    def test_english_is_unchanged(self) -> None:
        """The default output is the one every existing notebook reads."""
        columns = list(_beam_summary().check().columns)
        assert "Beam" in columns
        assert "Ok?" in columns


def _rendered_prose(monkeypatch: pytest.MonkeyPatch, render: Any) -> Set[str]:
    """The headings and paragraphs ``render`` writes, in English.

    Narrower than :func:`_rendered_strings`, which also records table headers:
    a summary table's headers are mostly symbols -- `Av`, `My`, `DCR` -- and
    those are deliberately the same in every language. What has to be
    translated, and what a new report line is likely to forget, is the prose.
    The tables are left to run for real, so the document is built the way it
    would be for a user; only ``save`` is stubbed out.
    """
    found: Set[str] = set()
    heading, text = DocumentBuilder.add_heading, DocumentBuilder.add_text

    def db_heading(self: Any, text_: str, level: int, font_size: float = 10, **fields: Any) -> None:
        found.add(text_)
        heading(self, text_, level, font_size, **fields)

    def db_text(self: Any, text_: str, **fields: Any) -> None:
        found.add(text_)
        text(self, text_, **fields)

    monkeypatch.setattr(DocumentBuilder, "add_heading", db_heading)
    monkeypatch.setattr(DocumentBuilder, "add_text", db_text)
    monkeypatch.setattr(DocumentBuilder, "save", lambda self, filename: None)

    render()
    return found


class TestSummaryCatalogCoverage:
    """Same guard as :class:`TestCatalogCoverage`, for the summary reports: a
    heading added without a translation fails here instead of printing English
    inside a Spanish document."""

    def test_beam_summary_doc(self, monkeypatch: pytest.MonkeyPatch) -> None:
        summary = _beam_summary()
        prose = _rendered_prose(monkeypatch, lambda: summary.results_detailed_doc(index=1))
        assert "Beam Summary Analysis" in prose, "the harness saw no report"
        assert sorted(s for s in prose if s not in ES) == []

    @pytest.mark.parametrize("with_warnings", [True, False])
    def test_slab_summary_doc(self, monkeypatch: pytest.MonkeyPatch, with_warnings: bool) -> None:
        summary = _slab_summary(with_warnings)
        prose = _rendered_prose(monkeypatch, lambda: summary.results_detailed_doc(index=1))
        assert "Slab Summary Analysis" in prose, "the harness saw no report"
        assert sorted(s for s in prose if s not in ES) == []

    def test_wall_summary_doc(self, monkeypatch: pytest.MonkeyPatch) -> None:
        summary = _wall_summary()
        prose = _rendered_prose(monkeypatch, lambda: summary.results_detailed_doc(index=1))
        assert "Shear Wall Summary Analysis" in prose, "the harness saw no report"
        assert sorted(s for s in prose if s not in ES) == []

    def test_the_summary_document_renders_in_spanish(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """End to end: the headings reach the document translated, and the
        status column still finds itself once the table is translated."""
        saved: Dict[str, Any] = {}
        monkeypatch.setattr(
            DocumentBuilder, "save", lambda self, filename: saved.update(doc=self.doc, filename=filename)
        )
        set_language("es")
        _beam_summary().results_detailed_doc(index=1)

        text = "\n".join(p.text for p in saved["doc"].paragraphs)
        assert ES["Beam Summary Analysis"] in text
        assert ES["Design Check Summary"] in text
        assert "Design Check Summary" not in text
        assert saved["filename"] == "Beam_Summary_ACI 318-19.docx"


def test_legacy_stirrup_mark_remains_available_without_driving_notation() -> None:
    previous = i18n.get_language()
    try:
        for language, mark in (("en", "s"), ("es", "e")):
            i18n.set_language(language)
            assert i18n.stirrup_mark() == mark
    finally:
        i18n.set_language(previous)
