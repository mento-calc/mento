"""Word reports for a beam check.

The document assembly used to live on ``RectangularBeam``. Phase 3 of the
architecture roadmap moves it here; the beam keeps one-line delegating methods,
so ``beam.shear_results_detailed_doc()`` still works.

These read the report tables that :mod:`mento.reports.tables` leaves on the beam
and hand them to :class:`~mento.results.DocumentBuilder`.
"""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Any, Dict, Optional, cast

import pandas as pd

from mento._version import __version__ as MENTO_VERSION
from mento.i18n import get_language
from mento.results import DocumentBuilder

if TYPE_CHECKING:
    from mento.beam import RectangularBeam
    from mento.forces import Forces


def flexure_report_doc(self: "RectangularBeam", force: Optional[Forces] = None) -> None:
    """
    Prints detailed flexure results in Word.

    Parameters
    ----------
    forces : Forces, optional
        The specific Forces object to display results for. If None, displays results for the limiting case.
    """
    if not self._flexure_checked:
        warnings.warn(
            "Flexural check has not been performed yet. Call _check_flexure or design_flexure first.",
            UserWarning,
        )
        self._md_flexure_results = "Flexural results are not available."
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
        top_result_data = self._limiting_case_flexure_top_details["flexure_capacity_top"]
        bot_result_data = self._limiting_case_flexure_bot_details["flexure_capacity_bot"]
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
                round(self._limiting_case_flexure_top_details["forces"]["Value"][0], 2),
                round(self._limiting_case_flexure_bot_details["forces"]["Value"][1], 2),
            ],
            "Unit": [
                self._limiting_case_flexure_top_details["forces"]["Unit"][0],
                self._limiting_case_flexure_bot_details["forces"]["Unit"][1],
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
                *self._limiting_case_flexure_top_details["min_max"]["Unit"][:2],
                *self._limiting_case_flexure_bot_details["min_max"]["Unit"][2:4],
            ],
            "Value": [
                round(
                    self._limiting_case_flexure_top_details["min_max"]["Value"][0],
                    2,
                ),  # Top limiting case As
                round(
                    self._limiting_case_flexure_top_details["min_max"]["Value"][1],
                    2,
                ),  # Top limiting case spacing
                round(
                    self._limiting_case_flexure_bot_details["min_max"]["Value"][2],
                    2,
                ),  # Bottom limiting case As
                round(
                    self._limiting_case_flexure_bot_details["min_max"]["Value"][3],
                    2,
                ),  # Bottom limiting case spacing
            ],
            "Min.": [
                round(self._limiting_case_flexure_top_details["min_max"]["Min."][0], 2),  # Top limiting case As_min
                self._limiting_case_flexure_top_details["min_max"]["Min."][1],  # Top limiting case spacing min
                round(self._limiting_case_flexure_bot_details["min_max"]["Min."][2], 2),  # Bottom limiting case As_min
                self._limiting_case_flexure_bot_details["min_max"]["Min."][3],  # Bottom limiting case spacing min
            ],
            "Max.": [
                round(self._limiting_case_flexure_top_details["min_max"]["Max."][0], 2),  # Top limiting case As_max
                "",  # No max constraint for spacing
                round(self._limiting_case_flexure_bot_details["min_max"]["Max."][2], 2),  # Bottom limiting case As_max
                "",  # No max constraint for spacing
            ],
            "Ok?": [
                self._limiting_case_flexure_top_details["min_max"]["Ok?"][0],  # Top As check
                self._limiting_case_flexure_top_details["min_max"]["Ok?"][1],  # Top spacing check
                self._limiting_case_flexure_bot_details["min_max"]["Ok?"][2],  # Bottom As check
                self._limiting_case_flexure_bot_details["min_max"]["Ok?"][3],  # Bottom spacing check
            ],
        }

    # Convert output Dicts into DataFrames
    df_materials = pd.DataFrame(self._materials_flexure)
    df_geometry = pd.DataFrame(self._geometry_flexure)
    df_forces = pd.DataFrame(forces_result)
    df_data_min_max = pd.DataFrame(min_max_result)
    df_flexure_capacity_top = pd.DataFrame(top_result_data)
    df_flexure_capacity_bottom = pd.DataFrame(bot_result_data)

    # Create a document builder instance
    doc_builder = DocumentBuilder(title=self._report_text["flexure_doc_title"], language=get_language())

    # Add first section and table
    doc_builder.add_heading(self._report_text["flexure_heading"], level=1, label=self.label)
    doc_builder.add_text(
        "Made with mento {version}. Design code: {design_code}",
        version=MENTO_VERSION,
        design_code=self.concrete.design_code,
    )
    doc_builder.add_heading("Section Data", level=2)
    doc_builder.add_table_data(df_materials)
    doc_builder.add_table_data(df_geometry)
    doc_builder.add_table_data(df_forces)

    # Add third section for limit checks
    doc_builder.add_heading("Limit checks", level=2)
    doc_builder.add_table_min_max(df_data_min_max)

    # Add second section for flexural checks
    doc_builder.add_heading("Flexural Capacity Top", level=2)
    doc_builder.add_table_dcr(df_flexure_capacity_top)
    doc_builder.add_heading("Flexural Capacity Bottom", level=2)
    doc_builder.add_table_dcr(df_flexure_capacity_bottom)

    # Save the Word doc
    doc_builder.save(self._report_file_name("flexure_heading"))


def shear_report_doc(self: "RectangularBeam", force: Optional[Forces] = None) -> None:
    """
    Prints detailed shear results in Word.

    Parameters
    ----------
    forces : Forces, optional
        The specific Forces object to display results for. If None, displays results for the limiting case.
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
        result_data: Dict[str, Any] = self._shear_results_detailed_list[force_id]
    else:
        # Default to limiting case
        # The early return above guarantees a check has run, so a limiting case exists.
        result_data = cast("Dict[str, Any]", self._limiting_case_shear_details)

    # Convert output Dicts into DataFrames
    df_materials = pd.DataFrame(self._materials_shear)
    df_geometry = pd.DataFrame(self._geometry_shear)
    df_forces = pd.DataFrame(result_data["forces"])
    df_shear_reinforcement = pd.DataFrame(result_data["shear_reinforcement"])
    df_data_min_max = pd.DataFrame(result_data["min_max"])
    df_shear_concrete = pd.DataFrame(result_data["shear_concrete"])

    # Create a document builder instance
    doc_builder = DocumentBuilder(title=self._report_text["shear_doc_title"], language=get_language())

    # Add first section and table
    doc_builder.add_heading(self._report_text["shear_heading"], level=1, label=self.label)
    doc_builder.add_text(
        "Made with mento {version}. Design code: {design_code}",
        version=MENTO_VERSION,
        design_code=self.concrete.design_code,
    )
    doc_builder.add_heading("Section Data", level=2)
    doc_builder.add_table_data(df_materials)
    doc_builder.add_table_data(df_geometry)
    doc_builder.add_table_data(df_forces)

    # Add second section and another table (can use different data)
    doc_builder.add_heading("Limit checks", level=2)
    doc_builder.add_table_min_max(df_data_min_max)
    doc_builder.add_heading("Strength Checks", level=2)
    doc_builder.add_table_data(df_shear_reinforcement)
    doc_builder.add_table_dcr(df_shear_concrete)

    from mento.reports.views import verification_table

    doc_builder.add_heading("Resistance and detailing", level=2)
    doc_builder.add_table_data(pd.DataFrame(verification_table(self)))

    # Save the Word doc
    doc_builder.save(self._report_file_name("shear_heading"))
