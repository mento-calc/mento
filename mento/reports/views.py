"""Notebook and console views of a beam check.

The same job as :mod:`mento.reports.documents` — turn the tables a check left
on the beam into something a person reads — rendered to Markdown and a terminal
instead of to a Word file. Keeping both out of the element class is the point:
the medium is a presentation choice, not part of the beam.

The properties on ``RectangularBeam`` (``data``, ``results``,
``flexure_results``, ...) delegate here.
"""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Any, Dict, Optional, cast

from IPython.display import Markdown, display

from mento.codes.registry import design_code
from mento.design_results import GRID, STIRRUPS, format_transverse_rebar, transverse_layout
from mento.i18n import get_language, translate
from mento.precompute import DISPLAY
from mento.results import Formatter, TablePrinter
from mento.units import cm

if TYPE_CHECKING:
    from mento.beam import RectangularBeam
    from mento.forces import Forces


def _show(markdown: str) -> None:
    """Render Markdown in a notebook.

    Wrapped once because IPython ships no type information, so every call site
    would otherwise need the same suppression.
    """
    display(Markdown(markdown))  # type: ignore[no-untyped-call]


def _details(value: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """The detail tables of a combination, once a check is known to have run.

    Each caller checks ``_shear_checked`` / ``_flexure_checked`` and returns
    early first, so by this point the limiting case exists.
    """
    return cast("Dict[str, Any]", value)


def data(self: "RectangularBeam") -> None:
    type = self.mode.capitalize()
    length = DISPLAY[self.concrete.is_imperial]["length"]
    markdown_content = (
        f"{type} {self.label}, $b$={self.width.to(length)}"
        f", $h$={self.height.to(length)}, $c_{{c}}$={self.c_c.to(length)}, \
                        Concrete {self.concrete.name}, Rebar {self.steel_bar.name}."
    )
    self._md_data = markdown_content
    # Display the combined content
    _show(markdown_content)

    return None


def flexure_results(self: "RectangularBeam") -> None:
    if not self._flexure_checked:
        warnings.warn(
            "Flexural design has not been performed yet. Call _check_flexure() or design_flexure() first.",
            UserWarning,
        )
        self._md_flexure_results = "Flexural results are not available."
        return None
    # Check if limiting case details exist
    top_details = self._limiting_case_flexure_top_details or {}
    bot_details = self._limiting_case_flexure_bot_details or {}
    # Use limiting case results
    top_result_data = top_details.get("flexure_capacity_top")
    bot_result_data = bot_details.get("flexure_capacity_bot")

    checks_pass_top = top_details.get("checks_pass")
    checks_pass_bot = bot_details.get("checks_pass")
    warning_top = "⚠️ Some checks failed, see detailed results." if not checks_pass_top else ""
    warning_bot = "⚠️ Some checks failed, see detailed results." if not checks_pass_bot else ""

    # Pending for approval
    # all_checks_top = top_details.get('flexure_check')
    # all_checks_bot = bot_details.get('flexure_check')
    # all_checks = all_checks_top and all_checks_bot

    # Formatter instance for DCR formatting
    markdown_content = ""
    formatter = Formatter()
    symbols = self._flexure_symbols
    md_demand = symbols["md_demand"]
    md_capacity = symbols["md_capacity"]

    # Handle top result data
    if top_result_data:
        top_rebar_1 = top_result_data["Value"][0]
        top_rebar_2 = top_result_data["Value"][1]
        area_top = top_result_data["Value"][7]
        Mu_top = _details(self._limiting_case_flexure_top_details)["forces"]["Value"][0]
        Mn_top = top_result_data["Value"][9]
        DCR_top = top_result_data["Value"][10]

        rebar_top = f"{top_rebar_1}" + (f" ++ {top_rebar_2}" if top_rebar_2 != "-" else "")
        # The units come with the table the values were read from.
        area_unit = top_result_data["Unit"][7]
        moment_unit = top_result_data["Unit"][9]
        formatted_DCR_top = formatter.DCR(DCR_top)

        markdown_content += (
            f"Top longitudinal rebar: {rebar_top}, $A_{{s,top}}$ = {area_top} {area_unit}, "
            f"${md_demand}$ = {Mu_top} {moment_unit}, "
            f"${md_capacity}$ = {Mn_top} {moment_unit} → {formatted_DCR_top} {warning_top}\n\n"
        )
    else:
        markdown_content += "No top moment to check.\n\n"

    # Handle bottom result data
    if bot_result_data:
        bot_rebar_1 = bot_result_data["Value"][0]
        bot_rebar_2 = bot_result_data["Value"][1]
        area_bot = bot_result_data["Value"][7]
        Mu_bot = _details(self._limiting_case_flexure_bot_details)["forces"]["Value"][1]
        Mn_bot = bot_result_data["Value"][9]
        DCR_bot = bot_result_data["Value"][10]

        rebar_bot = f"{bot_rebar_1}" + (f" ++ {bot_rebar_2}" if bot_rebar_2 != "-" else "")
        # The units come with the table the values were read from.
        area_unit = bot_result_data["Unit"][7]
        moment_unit = bot_result_data["Unit"][9]
        formatted_DCR_bot = formatter.DCR(DCR_bot)

        markdown_content += (
            f"Bottom longitudinal rebar: {rebar_bot}, $A_{{s,bot}}$ = {area_bot} {area_unit}, "
            f"${md_demand}$ = {Mu_bot} {moment_unit}, "
            f"${md_capacity}$ = {Mn_bot} {moment_unit} → {formatted_DCR_bot} {warning_bot}"
        )
    else:
        markdown_content += "No bottom moment to check."

    # markdown_content += 'Beam flexure checks PASS ✔️' if all_checks else "Beam flexure checks FAIL ❌"

    self._md_flexure_results = markdown_content
    _show(markdown_content)


def _transverse_label(self: "RectangularBeam", reinforcement: Dict[str, Any], imperial: bool) -> str:
    """The stirrups of the shear line, read off the rows of the detail table.

    The three rows are the ones ``_transverse_rebar_rows`` writes, and they are
    not the same three on every element: a beam reads count, diameter and
    spacing, a slab strip diameter and a spacing each way. Reading them by
    position alone once took a slab's Ø10 for ten stirrups.
    """
    values, units = reinforcement["Value"], reinforcement["Unit"]
    if transverse_layout(self) == GRID:
        diameter, s_l, s_w = values[:3]
        unit = units[1]
        # The table writes a US bar by its size already, "#3".
        bar = diameter if imperial else f"Ø{diameter:g}"
        # SI writes the unit once, "Ø10/21×43 cm"; after a US spacing each
        # direction carries its own, "#3@8 in×12 in", as the dataclasses do.
        if imperial:
            return format_transverse_rebar(GRID, 1, bar, f"{s_l:g} {unit}", f"{s_w:g} {unit}", imperial=True)
        return f"{format_transverse_rebar(GRID, 1, bar, f'{s_l:g}', f'{s_w:g}')} {unit}"
    count, diameter, spacing = values[:3]
    bar = diameter if imperial else f"Ø{diameter}"
    return f"{format_transverse_rebar(STIRRUPS, int(count), bar, str(spacing), '', imperial=imperial)} {units[2]}"


def shear_results(self: "RectangularBeam") -> None:
    if not self._shear_checked:
        warnings.warn(
            "Shear design has not been performed yet. Call check_shear() or design_shear() first.",
            UserWarning,
        )
        self._md_shear_results = "Shear results are not available."
        return None

    # Check if limiting case details exist
    shear_details = self._limiting_case_shear_details or {}
    # Use limiting case results
    limiting_reinforcement = shear_details.get("shear_reinforcement")
    limiting_forces = shear_details.get("forces")
    limiting_shear_concrete = shear_details.get("shear_concrete")
    checks_pass = shear_details.get("checks_pass")
    markdown_content = ""
    if shear_details:
        # Create FUFormatter instance and format FU value
        formatter = Formatter()
        formatted_DCR = formatter.DCR(_details(limiting_shear_concrete)["Value"][-1])
        reinforcement = _details(limiting_reinforcement)
        imperial = self.concrete.is_imperial
        if self._A_v == 0 * cm:
            rebar_v = "not assigned"
        else:
            rebar_v = _transverse_label(self, reinforcement, imperial)
        # Limitng cases checks
        warning = "⚠️ Some checks failed, see detailed results." if not checks_pass else ""
        # Each code names these quantities its own way, and puts its capacity
        # on a different row of its own detail table.
        symbols = design_code(self.concrete).shear_symbols
        capacity = _details(limiting_shear_concrete)["Value"][symbols["capacity_row"]]
        force_unit = _details(limiting_forces)["Unit"][1]
        markdown_content = (
            f"Shear reinforcing {rebar_v}, ${symbols['reinforcement']}$"
            f"={reinforcement['Value'][6]} {reinforcement['Unit'][6]}"
            f", ${symbols['demand']}$={_details(limiting_forces)['Value'][1]} {force_unit}"
            f", ${symbols['capacity']}$={capacity} {force_unit} → {formatted_DCR} {warning}"
        )
    else:
        markdown_content += "No shear to check."
    self._md_shear_results = markdown_content
    _show(markdown_content)

    return None


def results(self: "RectangularBeam") -> None:
    """
    Ensure that properties, flexure results, and shear results are available and display them.
    Handles cases where flexure or shear results are not yet available.
    """
    # The section line always leads. This used to be guarded on a
    # `_md_properties` attribute that nothing ever set, so the guard was always
    # true and the call always ran; it is written plainly now.
    self.data
    if self._flexure_checked:
        self.flexure_results  # This will generate _md_flexure_results
    if self._shear_checked:
        self.shear_results  # This will generate _md_shear_results
    return None


def _report_text(self: "RectangularBeam") -> Dict[str, str]:
    """Report wording of this element, so a slab is not reported as a beam.

    ``ShearWall`` overrides the detailed report methods with its own wording,
    so only the beam and the slab are covered here. The strings double as the
    keys of the language catalog in :mod:`mento.i18n`.
    """
    if self.mode == "slab":
        return {
            "flexure_banner": "===== SLAB FLEXURE DETAILED RESULTS =====",
            "shear_banner": "===== SLAB SHEAR DETAILED RESULTS =====",
            "flexure_doc_title": "Concrete slab flexure check",
            "shear_doc_title": "Concrete slab shear check",
            "flexure_heading": "Slab {label} flexure check",
            "shear_heading": "Slab {label} shear check",
        }
    return {
        "flexure_banner": "===== BEAM FLEXURE DETAILED RESULTS =====",
        "shear_banner": "===== BEAM SHEAR DETAILED RESULTS =====",
        "flexure_doc_title": "Concrete beam flexure check",
        "shear_doc_title": "Concrete beam shear check",
        "flexure_heading": "Beam {label} flexure check",
        "shear_heading": "Beam {label} shear check",
    }


def _report_file_name(self: "RectangularBeam", heading_key: str) -> str:
    """Name of the Word file of a report.

    Built from the English heading whatever the report language is, so a
    project keeps one naming scheme.
    """
    heading = self._report_text[heading_key].format(label=self.label)
    return f"{heading} {self.concrete.design_code}.docx"


def flexure_results_detailed(self: "RectangularBeam", force: Optional[Forces] = None) -> None:
    """
    Displays detailed flexure results.

    Parameters
    ----------
    forces : Forces, optional
        The specific Forces object to display results for. If None, displays results for the limiting case.
    Returns
    -------
    None
    """
    if not self._flexure_checked:
        warnings.warn(
            "Flexural check has not been performed yet. Call _check_flexure or design_flexure first.",
            UserWarning,
        )
        self._md_flexure_results = "Flexure results are not available."
        return None

    # Determine which results to display (limiting case by default)
    if force:
        if force.id not in self._flexure_results_detailed_list:
            raise ValueError(f"No results found for Forces object with ID {force.id}.")
        result_data = self._flexure_results_detailed_list[force.id]
        top_result_data = result_data["flexure_capacity_top"]
        bot_result_data = result_data["flexure_capacity_bot"]
        forces_result = result_data["forces"]
        min_max_result = result_data["min_max"]
    else:
        if self._limiting_case_flexure_top_details is None:
            raise ValueError("Top limiting case details are not available.")
        if self._limiting_case_flexure_bot_details is None:
            raise ValueError("Bottom limiting case details are not available.")
        # Use the worst-case top and bottom scenarios
        top_result_data = _details(self._limiting_case_flexure_top_details)["flexure_capacity_top"]
        bot_result_data = _details(self._limiting_case_flexure_bot_details)["flexure_capacity_bot"]
        forces_result = {
            "Design forces": [
                "Top max moment",
                "Bottom max moment",
            ],
            "Variable": [
                self._flexure_symbols["demand_top"],
                self._flexure_symbols["demand_bot"],
            ],
            "Value": [
                round(_details(self._limiting_case_flexure_top_details)["forces"]["Value"][0], 2),
                round(_details(self._limiting_case_flexure_bot_details)["forces"]["Value"][1], 2),
            ],
            "Unit": [
                _details(self._limiting_case_flexure_top_details)["forces"]["Unit"][0],
                _details(self._limiting_case_flexure_bot_details)["forces"]["Unit"][1],
            ],
        }
        min_max_result = {
            "Check": [
                "Min/Max As rebar top",
                "Minimum spacing top",
                "Min/Max As rebar bottom",
                "Minimum spacing bottom",
            ],
            "Unit": [
                *_details(self._limiting_case_flexure_top_details)["min_max"]["Unit"][:2],
                *_details(self._limiting_case_flexure_bot_details)["min_max"]["Unit"][2:4],
            ],
            "Value": [
                round(
                    _details(self._limiting_case_flexure_top_details)["min_max"]["Value"][0],
                    2,
                ),  # Top limiting case As
                round(
                    _details(self._limiting_case_flexure_top_details)["min_max"]["Value"][1],
                    2,
                ),  # Top limiting case spacing
                round(
                    _details(self._limiting_case_flexure_bot_details)["min_max"]["Value"][2],
                    2,
                ),  # Bottom limiting case As
                round(
                    _details(self._limiting_case_flexure_bot_details)["min_max"]["Value"][3],
                    2,
                ),  # Bottom limiting case spacing
            ],
            "Min.": [
                round(
                    _details(self._limiting_case_flexure_top_details)["min_max"]["Min."][0], 2
                ),  # Top limiting case As_min
                _details(self._limiting_case_flexure_top_details)["min_max"]["Min."][
                    1
                ],  # Top limiting case spacing min
                round(
                    _details(self._limiting_case_flexure_bot_details)["min_max"]["Min."][2], 2
                ),  # Bottom limiting case As_min
                _details(self._limiting_case_flexure_bot_details)["min_max"]["Min."][
                    3
                ],  # Bottom limiting case spacing min
            ],
            "Max.": [
                round(
                    _details(self._limiting_case_flexure_top_details)["min_max"]["Max."][0], 2
                ),  # Top limiting case As_max
                "",  # No max constraint for spacing
                round(
                    _details(self._limiting_case_flexure_bot_details)["min_max"]["Max."][2], 2
                ),  # Bottom limiting case As_max
                "",  # No max constraint for spacing
            ],
            "Ok?": [
                _details(self._limiting_case_flexure_top_details)["min_max"]["Ok?"][0],  # Top As check
                _details(self._limiting_case_flexure_top_details)["min_max"]["Ok?"][1],  # Top spacing check
                _details(self._limiting_case_flexure_bot_details)["min_max"]["Ok?"][2],  # Bottom As check
                _details(self._limiting_case_flexure_bot_details)["min_max"]["Ok?"][3],  # Bottom spacing check
            ],
        }

    # Create TablePrinter instances for detailed display
    language = get_language()
    print(translate(self._report_text["flexure_banner"], language))
    materials_printer = TablePrinter("MATERIALS", language)
    materials_printer.print_table_data(self._materials_flexure, headers="keys")

    geometry_printer = TablePrinter("GEOMETRY", language)
    geometry_printer.print_table_data(self._geometry_flexure, headers="keys")

    forces_printer = TablePrinter("FORCES", language)
    forces_printer.print_table_data(forces_result, headers="keys")

    min_max_printer = TablePrinter("MAX AND MIN LIMIT CHECKS", language)
    min_max_printer.print_table_data(min_max_result, headers="keys")

    capacity_printer = TablePrinter("FLEXURAL CAPACITY - TOP", language)
    capacity_printer.print_table_data(top_result_data, headers="keys")
    capacity_printer = TablePrinter("FLEXURAL CAPACITY - BOTTOM", language)
    capacity_printer.print_table_data(bot_result_data, headers="keys")


def shear_results_detailed(self: "RectangularBeam", force: Optional[Forces] = None) -> None:
    """
    Displays detailed shear results.

    Parameters
    ----------
    forces : Forces, optional
        The specific Forces object to display results for. If None, displays results for the limiting case.
    Returns
    -------
    None
    """
    if not self._shear_checked:
        warnings.warn(
            "Shear check has not been performed yet. Call check_shear or design_shear first.",
            UserWarning,
        )
        self._md_shear_results = "Shear results are not available."
        return None
    # Determine which results to display (limiting case by default)
    if force:
        force_id = force.id
        if force_id not in self._shear_results_detailed_list:
            raise ValueError(f"No results found for Forces object with ID {force_id}.")
        result_data = self._shear_results_detailed_list[force_id]
    else:
        # Default to limiting case
        result_data = _details(self._limiting_case_shear_details)

    # Create a TablePrinter instance and display tables
    language = get_language()
    print(translate(self._report_text["shear_banner"], language))
    materials_printer = TablePrinter("MATERIALS", language)
    materials_printer.print_table_data(self._materials_shear, headers="keys")
    geometry_printer = TablePrinter("GEOMETRY", language)
    geometry_printer.print_table_data(self._geometry_shear, headers="keys")
    forces_printer = TablePrinter("FORCES", language)
    forces_printer.print_table_data(result_data["forces"], headers="keys")
    steel_printer = TablePrinter("SHEAR STRENGTH", language)
    steel_printer.print_table_data(result_data["shear_reinforcement"], headers="keys")
    min_max_printer = TablePrinter("MAX AND MIN LIMIT CHECKS", language)
    min_max_printer.print_table_data(result_data["min_max"], headers="keys")
    concrete_printer = TablePrinter("CONCRETE STRENGTH", language)
    concrete_printer.print_table_data(result_data["shear_concrete"], headers="keys")
    TablePrinter("Resistance and detailing", language).print_table_data(verification_table(self), headers="keys")


def verification_table(beam: "RectangularBeam") -> Dict[str, Any]:
    """Resumen visible; no reemplaza los DCR ni vuelve opcional el detallado."""
    from mento.verification import status_text

    state = beam.verification_status
    return {
        "Verification": ["Resistance", "Detailing (modelled checks)"],
        "Status": [status_text(state["resistance"]), status_text(state["detailing"])],
    }
