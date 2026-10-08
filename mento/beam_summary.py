from typing import Any, List, Dict, Optional
from pandas import DataFrame
import pandas as pd
import copy
import math
from collections import OrderedDict

from mento.material import (
    Concrete,
    SteelBar,
)
from mento.verification import normalize_leg_column
from mento.forces import Forces
from mento.beam import RectangularBeam
from mento.design_results import _transverse_stirrup_count
from mento.codes.registry import design_code
from mento.i18n import translate, translate_dataframe
from mento.precompute import shown, unit_label
from mento.results import FAIL_MARK, PASS_MARK, VERDICT_COLUMN
from mento import mm, cm, kN, MPa, m, inch, ft, kNm, kip, psi, ksi
from mento.units import Quantity
from mento.node import Node
from mento.reports.summaries import beam_summary_doc


#: Summary-table columns that hold words rather than a number, a symbol or a
#: check mark. ``translate_dataframe`` already covers the first column -- the
#: element label -- but "Position" sits in the middle of the flexure table and
#: would otherwise print "Top"/"Bottom" in an otherwise translated row.
_WORD_COLUMNS = ("Position",)


def _section_dimension(length: Quantity, imperial: bool) -> Any:
    """A width or height for the summary table: whole where it is whole, else to two decimals."""
    value = shown(length, "length", imperial, 2)
    return int(value) if float(value).is_integer() else value


def _translated(df: DataFrame) -> DataFrame:
    """A summary table in the language reports are currently rendered in.

    Only the columns holding words are touched. The symbol columns -- ``b``,
    ``As,bot``, ``Mu``, ``DCRv`` -- are variable names, and units and
    numbers read the same in every language, so they are left alone. The
    ``Av`` cells of :meth:`BeamSummary.check` hold the compact stirrup
    notation (``10 legs Ø12/14``), which is written in the current language
    when the row is built, so it needs nothing here.
    """
    out = df.copy()
    for column in _WORD_COLUMNS:
        if column in out.columns:
            out[column] = [translate(value) if isinstance(value, str) else value for value in out[column]]
    return translate_dataframe(out)


class BeamSummary:
    def __init__(self, concrete: Concrete, steel_bar: SteelBar, beam_list: DataFrame) -> None:
        self.concrete: Concrete = concrete
        self.steel_bar: SteelBar = steel_bar
        self.beam_list: DataFrame = beam_list
        self.units_row: List[str] = []
        self.data: DataFrame = None
        self.nodes: List[Node] = []
        self._beam_summary: List = []
        self.check_and_process_input()
        self.convert_to_nodes()

    def check_and_process_input(self) -> None:
        self.beam_list = normalize_leg_column(self.beam_list)
        # Separate the header, units, and data
        self.units_row = self.beam_list.iloc[0].tolist()  # Second row (units)
        data = self.beam_list.iloc[1:].copy()  # Data rows (after removing the units row)

        # Convert NaN in units to "dimensionless"
        self.units_row = ["" if pd.isna(unit) else unit for unit in self.units_row]

        # Validate the units row
        self.validate_units(self.units_row)

        skin_columns = {"db_piel", "cant_piel_cara", "posicion"}
        if skin_columns.intersection(data.columns):
            if not skin_columns.issubset(data.columns):
                raise ValueError("Manual skin input requires db_piel, cant_piel_cara and posicion together.")
            for col in ("cant_piel_cara", "posicion"):
                if self.units_row[data.columns.get_loc(col)] != "":
                    raise ValueError(f"{col} must have a blank units cell.")
            skin_unit = self.get_unit_variable(self.units_row[data.columns.get_loc("db_piel")])
            from mento.skin_reinforcement import ManualSkinRebar

            for index, row in data.iterrows():
                values = [row[col] for col in ("db_piel", "cant_piel_cara", "posicion")]
                if all(pd.isna(value) or value == "" for value in values):
                    continue  # Sin entrada manual en esta viga: mantener diseño automático.
                raw_count = row["cant_piel_cara"]
                try:
                    count = float(raw_count)
                    diameter = float(row["db_piel"])
                except (TypeError, ValueError) as error:
                    raise ValueError(f"Invalid manual skin input (row {index}).") from error
                if (
                    pd.api.types.is_bool(raw_count)
                    or pd.api.types.is_bool(row["db_piel"])
                    or not math.isfinite(count)
                    or count != int(count)
                ):
                    raise ValueError(f"cant_piel_cara must be a finite integer (row {index}).")
                ManualSkinRebar(diameter * skin_unit, int(count), row["posicion"])

        # Validate counts before numeric coercion can hide fractions or typos.
        count_columns = [col for col in ("ns", "n_legs") if col in data.columns]
        if not count_columns:
            raise ValueError("BeamSummary requires 'n_legs' or legacy 'ns'.")
        for col in count_columns:
            if self.units_row[data.columns.get_loc(col)] != "":
                raise ValueError(f"{col} is a count and must have a blank units cell.")
        counts = []
        for index, row in data.iterrows():
            supplied: Dict[str, Optional[int]] = {}
            for col, name in (("ns", "n_stirrups"), ("n_legs", "n_legs")):
                value = row.get(col)
                if pd.isna(value) or value == "":
                    supplied[name] = None
                    continue
                if pd.api.types.is_bool(value):
                    raise TypeError(f"{col} must be an integer (row {index}).")
                try:
                    number = pd.to_numeric(value, errors="raise")
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"{col} must be an integer (row {index}).") from exc
                if not math.isfinite(number) or number != int(number):
                    raise ValueError(f"{col} must be a finite integer (row {index}).")
                supplied[name] = int(number)
            counts.append(_transverse_stirrup_count(supplied["n_stirrups"], supplied["n_legs"]))

        # Convert NaN to 0 in the data rows.
        # Assign per-column by label (replaces the column, including its dtype)
        # rather than via `.iloc[:, 2:] =`, which writes in place and preserves
        # the existing dtype. Under pandas 3.0, all-empty columns (e.g. a
        # forces-only summary with no rebar yet) are inferred as the new `str`
        # dtype, and writing floats into them in place raises a TypeError.
        for col in data.columns[2:]:
            if col == "posicion":
                data[col] = data[col].fillna("")
            else:
                data[col] = pd.to_numeric(data[col], errors="coerce").fillna(0)
        # Fill absent paired values from the explicit input; never reinterpret ns.
        for col in count_columns:
            data[col] = counts if col == "ns" else [2 * count for count in counts]
        # Convert specific columns to int and others to float
        columns_to_int = ["ns", "n_legs", "n1", "n2", "n3", "n4"]
        for col in columns_to_int:
            if col in data.columns:
                data[col] = data[col].astype(int)

        # Apply units to the corresponding columns, skipping the first column.
        # Assign by column label (replaces the column with an object dtype
        # holding pint Quantities) instead of `.iloc[:, i] =`, which writes in
        # place and, under pandas 3.0, raises when storing Quantity objects in
        # a numeric (int/float) column.
        for i in range(1, len(self.units_row)):  # Start from the second column (index 1)
            unit_str = self.units_row[i]
            if unit_str != "":
                unit = self.get_unit_variable(unit_str)
                col = data.columns[i]
                data[col] = data[col].apply(lambda x: x * unit)

        if "legs" in data.columns:
            data["legs"] = data["n_legs"]

        # Store the processed data
        self.data = data
        # print("Processed Data: Ok")

    def validate_units(self, units_row: List) -> None:
        # A US customary list gives its forces in kip and its moments in kip·ft,
        # the units the summary writes back ("kipft" as ShearWallSummary reads it).
        valid_units = {
            "m",
            "mm",
            "cm",
            "in",
            "inch",
            "ft",
            "kN",
            "kNm",
            "MPa",
            "kip",
            "kip·ft",
            "kipft",
            "psi",
            "ksi",
            "",
        }
        for unit_str in units_row:
            if unit_str and unit_str not in valid_units:
                raise ValueError(f"Invalid unit '{unit_str}' detected. Allowed units: {valid_units}")
        # print("Processed Units: Ok")

    def get_unit_variable(self, unit_str: str) -> Dict:
        # Map strings to actual unit variables (predefined in the script)
        unit_map = {
            "mm": mm,
            "cm": cm,
            "m": m,
            "in": inch,
            "inch": inch,
            "ft": ft,
            "kN": kN,
            "kNm": kNm,
            "MPa": MPa,
            "kip": kip,
            "kip·ft": kip * ft,
            "kipft": kip * ft,
            "psi": psi,
            "ksi": ksi,
        }
        if unit_str in unit_map:
            return unit_map[unit_str]
        else:
            raise ValueError(f"Unit '{unit_str}' is not recognized.")

    def convert_to_nodes(self) -> None:
        self.nodes = []

        for index, row in self.data.iterrows():
            # Extract forces for each row
            M_y = row["My"]
            N_x = row["Nx"]  # Positive for compression
            V_z = row["Vz"]
            comb = row["Comb."]

            # Ensure these are pint.Quantity objects with correct units
            forces = Forces(label=comb, M_y=M_y, N_x=N_x, V_z=V_z)

            # Extract geometric properties of the beam (width and height)
            width = row["b"]
            height = row["h"]
            c_c = row["cc"]

            # Create a rectangular concrete beam using the extracted values
            beam = RectangularBeam(
                label=row["Label"],
                concrete=self.concrete,
                steel_bar=self.steel_bar,
                width=width,
                height=height,
                c_c=c_c,
            )
            # Set transverse rebar (stirrups) for the beam
            n_stirrups = _transverse_stirrup_count(row.get("ns"), row.get("n_legs"))
            d_b = row["dbs"]  # Diameter of rebar (mm)
            s_l = row["sl"]  # Spacing of stirrups (cm)

            if n_stirrups != 0:
                beam.set_transverse_rebar(n_stirrups=n_stirrups, d_b=d_b, s_l=s_l)

            # Set longitudinal rebar at the bottom if n1 is not 0
            n1 = row["n1"]
            d_b1 = row["db1"]  # Diameter in mm
            n2 = row["n2"]
            d_b2 = row["db2"]  # Diameter in mm
            n3 = row["n3"]
            d_b3 = row["db3"]  # Diameter in mm
            n4 = row["n4"]
            d_b4 = row["db4"]  # Diameter in mm
            if n1 != 0:
                if M_y >= 0 * kNm:
                    beam.set_longitudinal_rebar_bot(n1, d_b1, n2, d_b2, n3, d_b3, n4, d_b4)
                else:
                    beam.set_longitudinal_rebar_top(n1, d_b1, n2, d_b2, n3, d_b3, n4, d_b4)
            # Create a Node for each pair of beam and forces
            if row.get("posicion", ""):
                beam.set_skin_rebar(row["db_piel"], int(row["cant_piel_cara"]), row["posicion"])
            node = Node(section=beam, forces=forces)

            # Store the section and its corresponding forces
            self.nodes.append(node)

    def section_data(self) -> DataFrame:
        """Sección física completa, ambas caras y recubrimiento en mm/in."""
        imperial = self.concrete.is_imperial
        cover = "in" if imperial else "mm"
        units = {
            "Label": "",
            "b": unit_label("length", imperial),
            "h": unit_label("length", imperial),
            "cc": cover,
            "As,bot": "",
            "As,top": "",
            "Av": "",
        }
        rows = []
        for node in self.nodes:
            section = node.section
            rebar = section.reinforcement
            rows.append(
                {
                    "Label": section.label,
                    "b": _section_dimension(section.width, imperial),
                    "h": _section_dimension(section.height, imperial),
                    "cc": round(section.c_c.to(cover).magnitude, 2),
                    "As,bot": str(rebar.bottom) if rebar.bottom.n_bars else "-",
                    "As,top": str(rebar.top) if rebar.top.n_bars else "-",
                    "Av": rebar.transverse.notation() if rebar.transverse.n_stirrups else "-",
                }
            )
        return DataFrame([units, *rows])

    def check(self, capacity_check: bool = False) -> DataFrame:
        """
        Perform a check on all beams in the summary.

        Parameters
        ----------
        capacity_check : bool, optional
            If True, resets all forces in the node to zero to perform a capacity check.
            Otherwise, uses the forces currently assigned to the node.

        Returns
        -------
        DataFrame
            A DataFrame with the results of the check.
        """

        results_list = []
        for node in self.nodes:
            beam: RectangularBeam = node.section  # type: ignore
            original_forces = [copy.deepcopy(force) for force in node.get_forces_list()]

            imperial = beam.concrete.is_imperial
            rebar_v = (
                "-" if beam._stirrup_n == 0 else beam.reinforcement.transverse.notation(compact=True, imperial=imperial)
            )
            rebar_f_top = (
                "-"
                if beam._n1_t == 0
                else (
                    f"{beam._format_longitudinal_rebar_string(beam._n1_t, beam._d_b1_t, beam._n2_t, beam._d_b2_t)}"
                    + (
                        f" ++ {beam._format_longitudinal_rebar_string(beam._n3_t, beam._d_b3_t, beam._n4_t, beam._d_b4_t)}"
                        if beam._n3_t != 0
                        else ""
                    )
                )
            )
            rebar_f_bot = (
                "-"
                if beam._n1_b == 0
                else (
                    f"{beam._format_longitudinal_rebar_string(beam._n1_b, beam._d_b1_b, beam._n2_b, beam._d_b2_b)}"
                    + (
                        f" ++ {beam._format_longitudinal_rebar_string(beam._n3_b, beam._d_b3_b, beam._n4_b, beam._d_b4_b)}"
                        if beam._n3_b != 0
                        else ""
                    )
                )
            )

            if capacity_check:
                # Remove all forces assignments
                node.clear_forces()
                # Create empty force
                empty_force = Forces()
                node.add_forces(empty_force)
                # Perform the shear check
                shear_results = node.check_shear()
                node.check_flexure()
                # Common data
                common_data = {
                    "Beam": beam.label,
                    "b": _section_dimension(beam.width, imperial),
                    "h": _section_dimension(beam.height, imperial),
                    "As,top": rebar_f_top,
                    "As,bot": rebar_f_bot,
                    "Av": rebar_v,
                    "As,top,real": shown(beam._A_s_top, "area", imperial, 1 if not imperial else 2),
                    "As,bot,real": shown(beam._A_s_bot, "area", imperial, 1 if not imperial else 2),
                    "Av,real": round(shear_results["Av"][1], 1 if not imperial else 2),
                }

                common_units = {
                    "Beam": "",
                    "b": unit_label("length", imperial),
                    "h": unit_label("length", imperial),
                    "As,top": "",
                    "As,bot": "",
                    "Av": "",
                    "As,top,real": unit_label("area", imperial),
                    "As,bot,real": unit_label("area", imperial),
                    "Av,real": unit_label("per_length", imperial),
                }

                # Code-specific data: the column names are the code's own.
                code = design_code(self.concrete)
                cols = code.summary_columns
                capacities = code.requires("capacity_columns")(beam)
                code_specific_data = {**capacities, cols["shear_capacity"]: shear_results[cols["shear_capacity"]][1]}
                code_specific_units = {
                    cols["moment_capacity_top"]: unit_label("moment", imperial),
                    cols["moment_capacity_bot"]: unit_label("moment", imperial),
                    cols["shear_capacity"]: unit_label("force", imperial),
                }

                # Merge data dictionaries
                merged_data = {**common_data, **code_specific_data}
                results_dict = merged_data

                # Merge units dictionaries
                merged_units = {**common_units, **code_specific_units}
                units_row = pd.DataFrame([OrderedDict({**merged_units})])

                # Restore the original forces after capacity check
                node.clear_forces()
                node.add_forces(original_forces)
            else:
                # Perform the shear check
                shear_results = node.check_shear().iloc[1:].reset_index(drop=True)  # Skip the first row (units)
                flexure_results = node.check_flexure().iloc[1:].reset_index(drop=True)  # Skip the first row (units)
                # One row per beam, in the order the report prints it: what
                # the section is, what it carries, what it was checked for,
                # how close it came, and whether it passed. The required areas
                # and the capacities are not repeated here -- `flexure_results`
                # and `shear_results` report those per combination, which is
                # where they mean something.
                code = design_code(self.concrete)
                cols = code.summary_columns
                results_dict = OrderedDict(
                    {
                        "Beam": beam.label,
                        "b": _section_dimension(beam.width, imperial),
                        "h": _section_dimension(beam.height, imperial),
                        "As,top": rebar_f_top,
                        "As,bot": rebar_f_bot,
                        "Av": rebar_v,
                        cols["moment_demand"]: round(flexure_results[cols["moment_demand"]][0], 1),
                        cols["shear_demand"]: round(shear_results[cols["shear_demand_source"]][0], 1),
                        cols["axial_demand"]: round(shear_results[cols["axial_demand"]][0], 1),
                        "DCRb,top": round(beam._DCRb_top, 3),
                        "DCRb,bot": round(beam._DCRb_bot, 3),
                        "DCRv": shear_results["DCR"][0],
                    }
                )
                units_row = pd.DataFrame(
                    [
                        OrderedDict(
                            {
                                "Beam": "",
                                "b": unit_label("length", imperial),
                                "h": unit_label("length", imperial),
                                "As,top": "",
                                "As,bot": "",
                                "Av": "",
                                cols["moment_demand"]: unit_label("moment", imperial),
                                cols["shear_demand"]: unit_label("force", imperial),
                                cols["axial_demand"]: unit_label("force", imperial),
                                "DCRb,top": "",
                                "DCRb,bot": "",
                                "DCRv": "",
                                VERDICT_COLUMN: "",
                            }
                        )
                    ]
                )

                # Determine status from the values themselves, not from the
                # rounded ones the table shows: a DCR of 0.997 reads as 1.00 at
                # two decimals, and comparing that against 1 would report a
                # section that passes as one that fails.
                dcr_values = [beam._DCRb_top, beam._DCRb_bot, beam._DCRv]
                all_dcrs_ok = all(v < 1 for v in dcr_values)
                # A face past its maximum steel fails whatever its DCR: under
                # ACI 318-19 / CIRSOC 201-25 it is not tension-controlled (§9.3.3.1).
                admissible = all(
                    check.bottom.admissible and check.top.admissible for check in getattr(beam, "_flexure_checks", ())
                )
                results_dict[VERDICT_COLUMN] = PASS_MARK if all_dcrs_ok and admissible else FAIL_MARK

            # Add the results to the list
            results_list.append(results_dict)

        # Convert results list into a DataFrame
        results_df = pd.DataFrame(results_list)

        # Combine the units row with the results DataFrame
        final_df = pd.concat([units_row, results_df], ignore_index=True)
        return _translated(final_df)

    def design(self) -> DataFrame:
        """
        Run design for all beams in the summary.
        Fills in the rebar columns (n1–n4, db1–db4, ns/n_legs, dbs, sl)
        with the suggested designs for shear and flexure.

        Returns
        -------
        DataFrame
            A copy of the beam summary with designed reinforcement filled in.
        """

        # Copy the processed data to avoid overwriting self.data
        design_df = self.data.copy()
        design_df = self.data.reset_index(drop=True).copy()

        for i, node in enumerate(self.nodes):
            beam: RectangularBeam = node.section  # type: ignore
            forces = node.forces[0]

            # --- FLEXURE DESIGN ---
            node.design_flexure()
            if forces.M_y.magnitude >= 0:  # tension at bottom face
                flex_result = beam.flexure_design_results_bot
                # print(beam.flexure_design_results_bot)
                design_df.loc[i, "n1"] = flex_result["n_1"]
                design_df.loc[i, "db1"] = flex_result["d_b1"]
                design_df.loc[i, "n2"] = flex_result["n_2"]
                design_df.loc[i, "db2"] = flex_result["d_b2"] if flex_result["d_b2"] is not None else 0
                design_df.loc[i, "n3"] = flex_result["n_3"]
                design_df.loc[i, "db3"] = flex_result["d_b3"] if flex_result["d_b3"] is not None else 0
                design_df.loc[i, "n4"] = flex_result["n_4"]
                design_df.loc[i, "db4"] = flex_result["d_b4"] if flex_result["d_b4"] is not None else 0
            else:  # tension at top face
                flex_result = beam.flexure_design_results_top
                design_df.loc[i, "n1"] = flex_result["n_1"]
                design_df.loc[i, "db1"] = flex_result["d_b1"]
                design_df.loc[i, "n2"] = flex_result["n_2"]
                design_df.loc[i, "db2"] = flex_result["d_b2"] if flex_result["d_b2"] is not None else 0
                design_df.loc[i, "n3"] = flex_result["n_3"]
                design_df.loc[i, "db3"] = flex_result["d_b3"] if flex_result["d_b3"] is not None else 0
                design_df.loc[i, "n4"] = flex_result["n_4"]
                design_df.loc[i, "db4"] = flex_result["d_b4"] if flex_result["d_b4"] is not None else 0

            # --- SHEAR DESIGN ---
            node.design_shear()
            shear_row = beam.shear_design_results.iloc[0]  # take best row
            if "ns" in design_df.columns:
                design_df.loc[i, "ns"] = int(shear_row["n_stir"])
            if "n_legs" in design_df.columns:
                design_df.loc[i, "n_legs"] = 2 * int(shear_row["n_stir"])
            if "legs" in design_df.columns:
                design_df.loc[i, "legs"] = 2 * int(shear_row["n_stir"])
            design_df.loc[i, "dbs"] = shear_row["d_b"]
            design_df.loc[i, "sl"] = shear_row["s_l"]

        # store for export
        self.design_data = design_df

        print("✅ Beam design completed for all beams in Summary.")
        return design_df

    def shear_results(self, index: Optional[int] = None, capacity_check: bool = False) -> DataFrame:
        """
        Get shear results for one or all beams.
        Includes a units row only once at the top.
        """
        if index is not None:
            if index - 1 >= len(self.nodes):
                raise IndexError(f"Index {index} is out of range for the beam list.")
            node = self.nodes[max(index - 1, 0)]
            df = self._process_beam_for_check(node, "shear", capacity_check)
            units_row = node.section._get_units_row_shear()  # type: ignore
            df_all = pd.concat([units_row, df], ignore_index=True)
        else:
            # For all nodes, only include the units row once
            results = []
            units_row_added = False
            for item in self.nodes:
                df = self._process_beam_for_check(item, "shear", capacity_check)
                if not units_row_added:
                    units_row = item.section._get_units_row_shear()  # type: ignore
                    results.append(units_row)
                    units_row_added = True
                results.append(df)

            df_all = pd.concat(results, ignore_index=True)

        # Separate the units row (first row) from the data
        units_row = df_all.iloc[[0]]  # DataFrame with 1 row
        data_rows = df_all.iloc[1:].copy()

        # Recombine units + data
        df_final = pd.concat([units_row, data_rows], ignore_index=True)
        return _translated(df_final)

    def flexure_results(self, index: Optional[int] = None, capacity_check: bool = False) -> DataFrame:
        """
        Get flexure results for one or all beams.
        Includes a units row only once at the top.
        """
        if index is not None:
            if index - 1 >= len(self.nodes):
                raise IndexError(f"Index {index} is out of range for the beam list.")
            node = self.nodes[max(index - 1, 0)]
            df = self._process_beam_for_check(node, "flexure", capacity_check)
            units_row = node.section._get_units_row_flexure()  # type: ignore
            df_all = pd.concat([units_row, df], ignore_index=True)
        else:
            # For all nodes, only include the units row once
            results = []
            units_row_added = False
            for item in self.nodes:
                df = self._process_beam_for_check(item, "flexure", capacity_check)
                if not units_row_added:
                    units_row = item.section._get_units_row_flexure()  # type: ignore
                    results.append(units_row)
                    units_row_added = True
                results.append(df)

            df_all = pd.concat(results, ignore_index=True)

        # Separate the units row (first row) from the data
        units_row = df_all.iloc[[0]]  # DataFrame with 1 row
        data_rows = df_all.iloc[1:].copy()

        # Recombine units + data
        df_final = pd.concat([units_row, data_rows], ignore_index=True)
        return _translated(df_final)

    def _process_beam_for_check(self, node: Node, check_type: str, capacity_check: bool) -> DataFrame:
        """
        Shared method to process beam for either shear or flexure checks.

        :param node: Node object to check
        :param check_type: Either 'shear' or 'flexure'
        :param capacity_check: If True, performs capacity check (resets forces)
        :return: Results DataFrame
        """
        original_forces = [copy.deepcopy(force) for force in node.get_forces_list()]

        if capacity_check:
            node.clear_forces()
            node.add_forces(Forces())  # Add empty force

        # Run the appropriate check
        if check_type == "shear":
            results = node.check_shear().iloc[1:].reset_index(drop=True)
        elif check_type == "flexure":
            results = node.check_flexure().iloc[1:].reset_index(drop=True)
        else:
            raise ValueError("check_type must be either 'shear' or 'flexure'")

        # Add code-specific capacity columns after a capacity flexure check
        if capacity_check and check_type == "flexure":
            beam: RectangularBeam = node.section  # type: ignore
            # `results` is a DataFrame: each capacity becomes its own column,
            # named the way the active code names it.
            for column, value in design_code(self.concrete).requires("capacity_columns")(beam).items():
                results[column] = value

        # Restore original forces if we did a capacity check
        if capacity_check:
            node.clear_forces()
            node.add_forces(original_forces)
        return results

    # ------------------------------------------------------------
    # EXCEL I/O HELPERS FOR DESIGN / CHECK WORKFLOW
    # ------------------------------------------------------------

    def export_design(self, path: str) -> None:
        """
        Export current beam list (including units row) to Excel.
        Typically used after design() to create an editable file.

        Parameters
        ----------
        path : str
            Path to the Excel file to create.
        """
        if not hasattr(self, "design_data"):
            raise AttributeError("No design data found. Run .design() before exporting.")

        df_numeric = self.design_data.copy()
        for col in df_numeric.columns:
            df_numeric[col] = df_numeric[col].apply(lambda x: x.magnitude if hasattr(x, "magnitude") else x)
        # Recombine units + data before exporting
        df_export = pd.concat(
            [
                pd.DataFrame([self.units_row], columns=self.beam_list.columns),
                df_numeric,
            ],
            ignore_index=True,
        )
        df_export.to_excel(path, index=False)
        print(f"✅ Beam design exported to {path}")

    def import_design(self, path: str) -> None:
        """
        Import an Excel file containing edited or designed rebar information.
        Updates self.beam_list, reprocesses units, and rebuilds nodes.

        Parameters
        ----------
        path : str
            Path to the Excel file to import.
        """
        beam_df = pd.read_excel(path)

        # Replace the original beam_list and re-process input
        self.beam_list = beam_df
        self.check_and_process_input()
        self.convert_to_nodes()
        print("✅ Beam design imported and summary data updated.")

    def results_detailed_doc(self, index: int = 1) -> None:
        """Export detailed results for one beam, plus summary tables for all, to Word.

        The assembly lives in :mod:`mento.reports.summaries`.

        Parameters
        ----------
        index : int
            1-based index of the beam to show detailed results for (default: 1)
        """
        beam_summary_doc(self, index)
