"""Word reports for a summary of many elements.

The document assembly used to live on ``BeamSummary`` and ``ShearWallSummary``.
Phase 3 of the architecture roadmap moves it here; the summaries keep a
one-line ``results_detailed_doc`` delegation, so nothing calling them changes.

These are module functions taking the summary, the same shape the design-code
modules use. Sharing one namespace, they are named after the element family
rather than after the method.

Every report ends with the same tables for all the sections, in the order a
reader checks them: what each section is (its sections table), what it carries
(the forces table, "Solicitaciones" in Spanish), the results of every
combination, the verdict of each section and, last, every warning worded in
full, with the face and the combinations it is read on.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, cast

import pandas as pd
from docx.shared import Cm

from mento._version import __version__ as MENTO_VERSION
from mento.codes.registry import design_code
from mento.i18n import get_language, translate
from mento.results import VERDICT_COLUMN, DocumentBuilder

if TYPE_CHECKING:
    from mento.beam import RectangularBeam
    from mento.shear_wall import ShearWall
    from mento.summary_base import _FlexuralSummary, _TwoTableSummary
    from mento.shear_wall_summary import ShearWallSummary


#: The all-sections tables are much wider than the running text, so they are
#: set a point smaller to keep every column on the page.
SUMMARY_FONT_SIZE = 7

#: How a beam's or a slab's forces table is read: the sign conventions of mento
#: (see the local axes guide), printed under the table.
FLEXURE_FORCES_NOTE = (
    "Nx > 0 is compression and enters the shear check only; My > 0 puts the bottom face in tension; "
    "Vz is taken in magnitude."
)

#: The same for walls, whose summary checks the in-plane shear alone.
WALL_FORCES_NOTE = (
    "Nx > 0 is compression; Vz is the in-plane shear, taken in magnitude. My is not used: the summary "
    "checks the in-plane shear only."
)


@dataclass(frozen=True)
class SummaryReport:
    """What the Word report of a summary calls its elements.

    The strings are the English keys of the i18n catalogue; the report
    translates them into the language it is written in. Every table of the
    report is sized to its content (:meth:`DocumentBuilder.content_widths`),
    so the report holds no column widths of its own.
    """

    title: str
    intro: str
    all_heading: str
    sections_heading: str
    file_prefix: str
    #: The line under the forces table: the sign conventions it is read with.
    forces_note: str


BEAM_REPORT = SummaryReport(
    title="Beam Summary Analysis",
    intro="This report presents the detailed results for the first beam of the summary, followed by summary tables for all beams.",
    all_heading="Summary - All Beams",
    sections_heading="Beam Sections",
    file_prefix="Beam_Summary",
    forces_note=FLEXURE_FORCES_NOTE,
)

SLAB_REPORT = SummaryReport(
    title="Slab Summary Analysis",
    intro="This report presents the detailed results for the first slab of the summary, followed by summary tables for all slabs.",
    all_heading="Summary - All Slabs",
    sections_heading="Slab Sections",
    file_prefix="Slab_Summary",
    forces_note=FLEXURE_FORCES_NOTE,
)

WALL_REPORT = SummaryReport(
    title="Shear Wall Summary Analysis",
    intro="This report presents the detailed results for the first wall of the summary, followed by summary tables for all walls.",
    all_heading="Summary - All Walls",
    sections_heading="Wall Sections",
    file_prefix="Shear_Wall_Summary",
    forces_note=WALL_FORCES_NOTE,
)

#: Widths for the two per-combination summaries, one entry per column, set
#: against the rendered document rather than computed. Both design codes leave
#: the same three capacity ticks out of these tables, so both end up the same
#: shape -- ten columns and twelve -- and one list each serves them. If a code
#: ever drops a different set, `add_table` warns that its list fell short
#: rather than quietly repeating the last width.
FLEXURE_SUMMARY_WIDTHS = [
    Cm(2),
    Cm(4),
    Cm(1.3),
    Cm(1.2),
    Cm(1.6),
    Cm(1.6),
    Cm(1.2),
    Cm(1.2),
    Cm(1.2),
    Cm(1),
]

SHEAR_SUMMARY_WIDTHS = [
    Cm(2),
    Cm(4),
    Cm(1.2),
    Cm(1.2),
    Cm(1.1),
    Cm(1.2),
    Cm(1.2),
    Cm(1.2),
    Cm(1.2),
    Cm(1.2),
    Cm(1.4),
    Cm(1),
]

#: What the Warnings table says when no section misses anything.
NO_WARNINGS = "No section misses a detailing limit."


def _without_dropped_columns(self: "_FlexuralSummary", df: pd.DataFrame) -> pd.DataFrame:
    """Drop the columns the active design code keeps out of its Word summary."""
    dropped = design_code(self.concrete).summary_drop_columns
    return df.drop(columns=[column for column in dropped if column in df.columns])


def _details(value: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """The detail tables a check leaves on the element.

    Typed ``Optional`` on the element because one that was never checked has
    none; both functions here run the checks before reading them.
    """
    return cast(Dict[str, Any], value)


def _limit_rows(top: Dict[str, Any], bottom: Dict[str, Any]) -> Dict[str, List[Any]]:
    """The flexure limit rows of the selected section: each face's rows from the combination that governs that face.

    Read off the section's own limit table, labels and limits included, so the
    summary report shows what the section's detailed report shows: a slab's
    "Bar spacing" against its maximum (ACI 318-19 §7.7.2.3), a beam's
    "Minimum spacing" against the clear distance, and the §24.3.2 "Maximum
    spacing" rows of a code that has them. Written out by hand, the rows were
    the four of a beam, and a slab at Ø12/40 read "Minimum spacing bottom
    400 ≥ 37 ❌", its maximum dropped. Numbers are rounded to two decimals.
    """
    rows: Dict[str, List[Any]] = {column: [] for column in top["min_max"]}
    for i, check in enumerate(top["min_max"]["Check"]):
        source = top if str(check).endswith("top") else bottom
        for column in rows:
            value = source["min_max"][column][i]
            rows[column].append(round(value, 2) if isinstance(value, float) else value)
    return rows


def _blank_missing(df: pd.DataFrame) -> pd.DataFrame:
    """A check table for print: a demand or a DCR that does not exist reads ``-``, not ``nan``.

    A face no combination puts in tension has no governing demand, and a
    section that was not checked no DCR; the frame keeps them as NaN, so its
    DCR columns stay numeric, and the document writes a dash.
    """
    out = df.astype(object)
    return out.map(lambda value: "-" if isinstance(value, float) and math.isnan(value) else value)


def _warnings_table(self: "_TwoTableSummary") -> Optional[pd.DataFrame]:
    """One row per warning of the last ``check()``, worded in full, and one per section it did not check.

    ``Face`` is the face a longitudinal warning is read on; ``Comb.`` the
    combinations the limit is missed under (none for a limit of the section
    alone, such as a bar spacing). ``None`` when there is nothing to list.
    """
    from mento.summary_base import STATUS_TEXT

    level = self._show_level()
    rows: List[Dict[str, Any]] = []
    for record in self.results:
        where: Dict[str, Any] = {"Level": record.level} if level else {}
        where["Label"] = record.label
        if record.passes is None:
            rows.append({**where, "Face": "-", "Comb.": "-", "Message": translate(STATUS_TEXT[record.status])})
            continue
        for warning in record.warnings:
            face = translate(warning.face.capitalize()) if warning.face else "-"
            combinations = ", ".join(warning.combinations) or "-"
            rows.append({**where, "Face": face, "Comb.": combinations, "Message": warning.message})
    if not rows:
        return None
    return pd.DataFrame(rows)


def _all_sections(
    self: "_TwoTableSummary",
    doc_builder: DocumentBuilder,
    per_combination: Callable[[DocumentBuilder], None],
    status_column: str,
) -> None:
    """The tables of every section: what it is, what it carries, its results, its verdict and its warnings."""
    report = self._REPORT
    doc_builder.add_heading(report.all_heading, level=2)

    doc_builder.add_heading(report.sections_heading, level=3)
    sections = self._sections_overview()
    doc_builder.add_table_data(
        sections, column_widths=doc_builder.content_widths(sections), font_size=SUMMARY_FONT_SIZE
    )

    # The forces table as the file holds it, with its unit row: what each
    # section was checked for, per combination.
    doc_builder.add_heading("Forces", level=3)
    forces = self.forces_table
    doc_builder.add_table_data(forces, column_widths=doc_builder.content_widths(forces), font_size=SUMMARY_FONT_SIZE)
    doc_builder.add_text(report.forces_note)

    per_combination(doc_builder)

    # Printed as `check()` returns it, so the notebook and the report show the
    # same summary, warnings and verdict included.
    doc_builder.add_heading("Design Check Summary", level=3)
    check = _blank_missing(self.check())
    doc_builder.add_table_status(
        check,
        column_widths=doc_builder.content_widths(check),
        status_column=status_column,
        font_size=SUMMARY_FONT_SIZE,
    )

    doc_builder.add_heading("Warnings", level=3)
    warnings = _warnings_table(self)
    if warnings is None:
        doc_builder.add_text(NO_WARNINGS)
    else:
        doc_builder.add_table_data(
            warnings, column_widths=doc_builder.content_widths(warnings), font_size=SUMMARY_FONT_SIZE
        )


def _document(self: "_TwoTableSummary") -> DocumentBuilder:
    """A report with its title, the version and code it was made with, and its introduction."""
    report = self._REPORT
    doc_builder = DocumentBuilder(title=report.title, font_size=8, language=get_language())
    doc_builder.add_heading(report.title, level=1)
    doc_builder.add_text(
        "Made with mento {version}. Design code: {design_code}",
        version=MENTO_VERSION,
        design_code=self.concrete.design_code,
    )
    doc_builder.add_text(report.intro)
    return doc_builder


def _save(self: "_TwoTableSummary", doc_builder: DocumentBuilder) -> None:
    filename = f"{self._REPORT.file_prefix}_{self.concrete.design_code}.docx"
    doc_builder.save(filename)
    print(f"✅ Results exported to {filename}")


def beam_summary_doc(self: "_FlexuralSummary", index: Any = 1) -> None:
    """Write the Word report of a beam or slab summary.

    The detailed flexure and shear of one section (``index``: its 1-based
    position in the sections table, or its label), then the tables of all.
    """
    node = self._node_with_forces(index)
    beam: RectangularBeam = node.section  # type: ignore

    # Run checks if not already done
    node.check_flexure()
    node.check_shear()

    doc_builder = _document(self)

    # --- DETAILED FLEXURE RESULTS FOR SELECTED BEAM ---
    doc_builder.add_heading(beam._report_text["flexure_heading"], level=2, label=beam.label)

    # Build dataframes same as flexure_results_detailed_doc
    top_details = _details(beam._limiting_case_flexure_top_details)
    bot_details = _details(beam._limiting_case_flexure_bot_details)
    top_result_data = top_details["flexure_capacity_top"]
    bot_result_data = bot_details["flexure_capacity_bot"]
    forces_result = {
        "Design forces": ["Top max moment", "Bottom max moment"],
        "Variable": [
            beam._flexure_symbols["demand_top"],
            beam._flexure_symbols["demand_bot"],
        ],
        "Value": [
            round(top_details["forces"]["Value"][0], 2),
            round(bot_details["forces"]["Value"][1], 2),
        ],
        "Unit": [top_details["forces"]["Unit"][0], bot_details["forces"]["Unit"][1]],
    }
    min_max_result = _limit_rows(top_details, bot_details)

    df_flex_materials = pd.DataFrame(beam._materials_flexure)
    df_flex_geometry = pd.DataFrame(beam._geometry_flexure)
    df_flex_forces = pd.DataFrame(forces_result)
    df_flex_min_max = pd.DataFrame(min_max_result)
    df_flex_capacity_top = pd.DataFrame(top_result_data)
    df_flex_capacity_bot = pd.DataFrame(bot_result_data)

    doc_builder.add_heading("Section Data", level=3)
    doc_builder.add_table_data(df_flex_materials)
    doc_builder.add_table_data(df_flex_geometry)
    doc_builder.add_table_data(df_flex_forces)
    doc_builder.add_heading("Limit checks", level=3)
    doc_builder.add_table_min_max(df_flex_min_max)
    doc_builder.add_heading("Flexural Capacity Top", level=3)
    doc_builder.add_table_dcr(df_flex_capacity_top)
    doc_builder.add_heading("Flexural Capacity Bottom", level=3)
    doc_builder.add_table_dcr(df_flex_capacity_bot)

    # --- DETAILED SHEAR RESULTS FOR SELECTED BEAM ---
    doc_builder.add_heading(beam._report_text["shear_heading"], level=2, label=beam.label)

    result_data = _details(beam._limiting_case_shear_details)
    df_shear_materials = pd.DataFrame(beam._materials_shear)
    df_shear_geometry = pd.DataFrame(beam._geometry_shear)
    df_shear_forces = pd.DataFrame(result_data["forces"])
    df_shear_reinforcement = pd.DataFrame(result_data["shear_reinforcement"])
    df_shear_min_max = pd.DataFrame(result_data["min_max"])
    df_shear_concrete = pd.DataFrame(result_data["shear_concrete"])

    doc_builder.add_heading("Section Data", level=3)
    doc_builder.add_table_data(df_shear_materials)
    doc_builder.add_table_data(df_shear_geometry)
    doc_builder.add_table_data(df_shear_forces)
    doc_builder.add_heading("Limit checks", level=3)
    doc_builder.add_table_min_max(df_shear_min_max)
    doc_builder.add_heading("Strength Checks", level=3)
    doc_builder.add_table_data(df_shear_reinforcement)
    doc_builder.add_table_dcr(df_shear_concrete)

    # --- SUMMARY TABLES FOR ALL SECTIONS ---
    def per_combination(builder: DocumentBuilder) -> None:
        # The label and the combination name are the only columns holding
        # words; the rest hold a number each and share what is left. Shared
        # rather than listed because the column count is the code's: each code
        # drops a different set of columns below.
        builder.add_heading("Flexure Results", level=3)
        df_flex_all = _without_dropped_columns(self, self.flexure_results(capacity_check=False))
        builder.add_table_data(df_flex_all, column_widths=FLEXURE_SUMMARY_WIDTHS, font_size=SUMMARY_FONT_SIZE)

        builder.add_heading("Shear Results", level=3)
        df_shear_all = _without_dropped_columns(self, self.shear_results(capacity_check=False))
        builder.add_table_data(df_shear_all, column_widths=SHEAR_SUMMARY_WIDTHS, font_size=SUMMARY_FONT_SIZE)

    _all_sections(self, doc_builder, per_combination, VERDICT_COLUMN)
    _save(self, doc_builder)


def wall_summary_doc(self: "ShearWallSummary", index: Any = 1) -> None:
    """Write the Word report of a wall summary: the detailed shear of one wall, then the tables of all."""
    node = self._node_with_forces(index)
    wall: ShearWall = node.section  # type: ignore

    node.check_shear()

    doc_builder = _document(self)

    # --- DETAILED RESULTS FOR SELECTED WALL ---
    # The placeholder is `storey`, not `level`: `level` is add_heading's own
    # argument for the heading depth.
    doc_builder.add_heading("Wall {storey} - {label} shear check", level=2, storey=wall.level, label=wall.label)

    result_data = _details(wall._limiting_case_shear_details)
    df_materials = pd.DataFrame(wall._materials_shear_wall)
    df_geometry = pd.DataFrame(wall._geometry_shear_wall)
    df_forces = pd.DataFrame(result_data["forces"])
    df_min_max = pd.DataFrame(result_data["min_max"])
    df_capacity = pd.DataFrame(result_data["shear_capacity"])

    doc_builder.add_heading("Section Data", level=3)
    doc_builder.add_table_data(df_materials)
    doc_builder.add_table_data(df_geometry)
    doc_builder.add_table_data(df_forces)
    doc_builder.add_heading("Limit checks", level=3)
    doc_builder.add_table_min_max(df_min_max)
    doc_builder.add_heading("Strength Checks", level=3)
    doc_builder.add_table_dcr(df_capacity)

    # --- SUMMARY TABLES FOR ALL WALLS ---
    def per_combination(builder: DocumentBuilder) -> None:
        builder.add_heading("Shear Results", level=3)
        df_shear_all = self.shear_results()
        cols_to_drop = [c for c in ["Vu≤ØVn,max", "Vu≤ØVn"] if c in df_shear_all.columns]
        df_shear_all = df_shear_all.drop(columns=cols_to_drop)
        builder.add_table_data(
            df_shear_all, column_widths=builder.content_widths(df_shear_all), font_size=SUMMARY_FONT_SIZE
        )

    _all_sections(self, doc_builder, per_combination, "Status")
    _save(self, doc_builder)
