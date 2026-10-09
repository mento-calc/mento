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
from mento.reports.summaries import BEAM_REPORT, beam_summary_doc


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


_GEOMETRY_COLUMNS = ("b", "h", "cc")
_STIRRUP_COLUMNS = ("ns", "dbs", "sl")
_LONGITUDINAL_COLUMNS = ("n1", "db1", "n2", "db2", "n3", "db3", "n4", "db4")


def _is_unlabelled(label: Any) -> bool:
    """A row with no beam label: it is a beam of its own rather than one of a group."""
    return bool(pd.isna(label)) or str(label).strip() == ""


def _declared(
    rows: List[pd.Series], columns: tuple[str, ...], label: Any, what: str, element: str = "Beam"
) -> Optional[tuple]:
    """The reinforcement the rows of a beam give in ``columns``, or None if none gives any.

    A row gives it when any of its reinforcement columns is not zero. This
    also lets the section validate an incomplete declaration, or read a slab's
    second layer when the first is empty. Rows that give it must agree: a beam
    has one set of stirrups and one set of bars per face, however many
    combinations it carries.
    """
    if not columns:
        return None
    given = [tuple(row[column] for column in columns) for row in rows if any(row[column] != 0 for column in columns)]
    if not given:
        return None
    if any(values != given[0] for values in given[1:]):
        raise ValueError(
            f"{element} {label!r}: its rows give different {what}; give them once, or the same on every row."
        )
    return given[0]


def _in_unit(value: Any, unit: Any) -> Any:
    """A cell of the design as the file holds it: a bare number in its column's unit."""
    if not hasattr(value, "magnitude"):
        return value
    return value.to(unit).magnitude if unit is not None else value.magnitude


def _peak(values: Any) -> Any:
    """The demand of largest magnitude among the combinations, with its sign."""
    return max(values, key=abs)


def _face_columns(result: Any) -> Dict[str, Any]:
    """The input columns ``n1``-``db4`` of one designed face."""
    columns: Dict[str, Any] = {"n1": result["n_1"], "db1": result["d_b1"]}
    for layer in (2, 3, 4):
        columns[f"n{layer}"] = result[f"n_{layer}"]
        columns[f"db{layer}"] = result[f"d_b{layer}"] if result[f"d_b{layer}"] is not None else 0
    return columns


class BeamSummary:
    """Check and design a list of beams read from a table, one row per load combination.

    Rows that share a ``Label`` are one beam; see :meth:`convert_to_nodes`.
    :class:`~mento.slab_summary.OneWaySlabSummary` reads a list of one-way slabs
    the same way, overriding the hooks below: the section a row becomes, the
    columns that hold its reinforcement and how a design writes them back.
    """

    #: First column of ``check()``: what each row of it is.
    _ELEMENT_COLUMN = "Beam"
    #: The columns that give the bars of one face, and the transverse steel.
    _FACE_COLUMNS: tuple[str, ...] = _LONGITUDINAL_COLUMNS
    _TRANSVERSE_COLUMNS: tuple[str, ...] = _STIRRUP_COLUMNS
    #: What the Word report calls the list and which input columns it prints.
    _REPORT = BEAM_REPORT

    def __init__(self, concrete: Concrete, steel_bar: SteelBar, beam_list: DataFrame) -> None:
        self.concrete: Concrete = concrete
        self.steel_bar: SteelBar = steel_bar
        self.beam_list: DataFrame = beam_list
        self.units_row: List[str] = []
        self.data: DataFrame = None
        self.nodes: List[Node] = []
        #: Positions in :attr:`data` of the rows of each node, in node order.
        self._node_rows: List[List[int]] = []
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

        # Validate counts before numeric coercion can hide fractions or typos.
        # A summary of an element with no stirrups (OneWaySlabSummary) has no
        # count columns, and must not be asked for them.
        count_columns = [col for col in ("ns", "n_legs") if col in data.columns]
        if self._TRANSVERSE_COLUMNS and not count_columns:
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
            data[col] = pd.to_numeric(data[col], errors="coerce").fillna(0)
        # Fill absent paired values from the explicit input; never reinterpret ns.
        for col in count_columns:
            data[col] = counts if col == "ns" else [2 * count for count in counts]
        # Convert specific columns to int and others to float
        columns_to_int = ["n_legs", "n1", "n2", "n3", "n4"]
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
        # The stirrup columns the nodes read: closed stirrups, whichever count was given.
        if self._TRANSVERSE_COLUMNS and "ns" not in data.columns:
            data["ns"] = counts

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
        """Build one node per beam from the rows of :attr:`data`.

        The rows that share a ``Label`` are one beam under several load
        combinations: one section, one node carrying every combination, so
        ``check()`` and ``design()`` work on the envelope, as a
        :class:`~mento.node.Node` built by hand does. A row with no label is a
        beam of its own.

        The rows of a beam must agree on ``b``, ``h`` and ``cc``. The bars on a
        row describe the face its moment puts in tension -- the bottom for
        ``My >= 0``, the top otherwise -- and the stirrups the whole beam; a
        row may leave them at zero, but the rows that give them must give the
        same ones. Anything else raises a ``ValueError`` naming the beam.
        """
        self.nodes = []
        self._node_rows = []
        rows = [row for _, row in self.data.reset_index(drop=True).iterrows()]
        by_label: Dict[Any, List[int]] = {}
        for position, row in enumerate(rows):
            label = row["Label"]
            if _is_unlabelled(label):
                self._node_rows.append([position])
            elif label in by_label:
                by_label[label].append(position)
            else:
                by_label[label] = [position]
                self._node_rows.append(by_label[label])

        for positions in self._node_rows:
            self.nodes.append(self._beam_node([rows[position] for position in positions]))

    def _beam_node(self, rows: List[pd.Series]) -> Node:
        """The node of one beam, from the rows that describe it."""
        first = rows[0]
        label = first["Label"]
        for column in _GEOMETRY_COLUMNS:
            if any(row[column] != first[column] for row in rows[1:]):
                raise ValueError(f"{self._ELEMENT_COLUMN} {label!r}: its rows give different values of {column!r}.")

        section = self._new_section(first)

        element = self._ELEMENT_COLUMN
        transverse = _declared(rows, self._TRANSVERSE_COLUMNS, label, "stirrups", element)
        if transverse is not None:
            self._set_transverse(section, transverse)

        bottom_rows = [row for row in rows if row["My"] >= 0 * kNm]
        top_rows = [row for row in rows if row["My"] < 0 * kNm]
        for face, face_rows in (("bottom", bottom_rows), ("top", top_rows)):
            bars = _declared(face_rows, self._FACE_COLUMNS, label, f"{face} bars", element)
            if bars is not None:
                self._set_face(section, face, bars)

        forces = [Forces(label=row["Comb."], M_y=row["My"], N_x=row["Nx"], V_z=row["Vz"]) for row in rows]
        return Node(section=section, forces=forces)

    # ------------------------------------------------------------
    # The section of a row and its reinforcement: what a summary of
    # another element (OneWaySlabSummary) overrides.
    # ------------------------------------------------------------

    def _new_section(self, row: pd.Series) -> RectangularBeam:
        """The section of a beam, from the first of its rows."""
        return RectangularBeam(
            label=row["Label"],
            concrete=self.concrete,
            steel_bar=self.steel_bar,
            width=row["b"],
            height=row["h"],
            c_c=row["cc"],
        )

    def _set_transverse(self, section: RectangularBeam, values: tuple) -> None:
        n_stirrups, d_b, s_l = values
        section.set_transverse_rebar(legs=int(2 * n_stirrups), d_b=d_b, s_l=s_l)

    def _set_face(self, section: RectangularBeam, face: str, values: tuple) -> None:
        setter = section.set_longitudinal_rebar_bot if face == "bottom" else section.set_longitudinal_rebar_top
        setter(*values)

    def _designed(self, node: Node) -> tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
        """Design a beam for its combinations: the input columns of each face, and of its stirrups."""
        beam: RectangularBeam = node.section  # type: ignore
        node.design_flexure()
        faces = {
            "bottom": _face_columns(beam.flexure_design_results_bot),
            "top": _face_columns(beam.flexure_design_results_top),
        }
        node.design_shear()
        shear_row = beam.shear_design_results.iloc[0]  # take best row
        transverse = {"ns": int(shear_row["n_stir"]), "dbs": shear_row["d_b"], "sl": shear_row["s_l"]}
        for column in ("n_legs", "legs"):
            if column in self.data.columns:
                transverse[column] = 2 * int(shear_row["n_stir"])
        return faces, transverse

    def _rebar_labels(self, section: RectangularBeam) -> tuple[str, str, str]:
        """The top bars, the bottom bars and the stirrups, as ``check()`` writes them."""

        def face(n1: Any, d1: Any, n2: Any, d2: Any, n3: Any, d3: Any, n4: Any, d4: Any) -> str:
            if n1 == 0:
                return "-"
            text = section._format_longitudinal_rebar_string(n1, d1, n2, d2)
            if n3 != 0:
                text += f" ++ {section._format_longitudinal_rebar_string(n3, d3, n4, d4)}"
            return text

        b = section
        top = face(b._n1_t, b._d_b1_t, b._n2_t, b._d_b2_t, b._n3_t, b._d_b3_t, b._n4_t, b._d_b4_t)
        bottom = face(b._n1_b, b._d_b1_b, b._n2_b, b._d_b2_b, b._n3_b, b._d_b3_b, b._n4_b, b._d_b4_b)
        if section._stirrup_n == 0:
            return top, bottom, "-"
        imperial = section.concrete.is_imperial
        return top, bottom, section.reinforcement.transverse.notation(compact=True, imperial=imperial)

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
            rebar_f_top, rebar_f_bot, rebar_v = self._rebar_labels(beam)

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
                    self._ELEMENT_COLUMN: beam.label,
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
                    self._ELEMENT_COLUMN: "",
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
                # A beam carries every combination of its rows: the summary
                # gives the envelope -- the largest demand of each kind, with
                # its sign, and the largest DCR of each face and of shear.
                dcr_top = max(check.top.DCR for check in beam.flexure_checks)
                dcr_bot = max(check.bottom.DCR for check in beam.flexure_checks)
                dcr_v = max(check.DCR for check in beam.shear_checks)
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
                        self._ELEMENT_COLUMN: beam.label,
                        "b": _section_dimension(beam.width, imperial),
                        "h": _section_dimension(beam.height, imperial),
                        "As,top": rebar_f_top,
                        "As,bot": rebar_f_bot,
                        "Av": rebar_v,
                        cols["moment_demand"]: round(_peak(flexure_results[cols["moment_demand"]]), 1),
                        cols["shear_demand"]: round(_peak(shear_results[cols["shear_demand_source"]]), 1),
                        cols["axial_demand"]: round(_peak(shear_results[cols["axial_demand"]]), 1),
                        "DCRb,top": round(dcr_top, 3),
                        "DCRb,bot": round(dcr_bot, 3),
                        "DCRv": max(shear_results["DCR"]),
                    }
                )
                units_row = pd.DataFrame(
                    [
                        OrderedDict(
                            {
                                self._ELEMENT_COLUMN: "",
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
                dcr_values = [dcr_top, dcr_bot, dcr_v]
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
        with the suggested designs for shear and flexure. Each beam is designed
        for the envelope of its rows, and every row of it gets the same
        stirrups and the bars of the face its moment puts in tension.

        Returns
        -------
        DataFrame
            A copy of the beam summary with designed reinforcement filled in.
        """

        # Copy the processed data to avoid overwriting self.data
        design_df = self.data.reset_index(drop=True).copy()

        for node, positions in zip(self.nodes, self._node_rows):
            # For the envelope of the beam's combinations. Each row takes the
            # bars of the face its moment puts in tension, so every row of a
            # beam reads back as the same section.
            faces, transverse = self._designed(node)
            for i in positions:
                face = "bottom" if design_df.loc[i, "My"].magnitude >= 0 else "top"
                for column, value in {**faces[face], **transverse}.items():
                    design_df.loc[i, column] = value

        # store for export
        self.design_data = design_df

        print(f"✅ {self._ELEMENT_COLUMN} design completed for every element of the summary.")
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

        # Each number in the unit its column declares: a design writes back
        # quantities in whatever unit mento computed them in (a slab spacing
        # in mm under a column in cm), and the file holds bare numbers.
        df_numeric = self.design_data.copy()
        for col, unit_str in zip(df_numeric.columns, self.units_row):
            unit = self.get_unit_variable(unit_str) if unit_str else None
            df_numeric[col] = df_numeric[col].apply(lambda x, u=unit: _in_unit(x, u))
        # Recombine units + data before exporting
        df_export = pd.concat(
            [
                pd.DataFrame([self.units_row], columns=self.beam_list.columns),
                df_numeric,
            ],
            ignore_index=True,
        )
        # Una única cantidad editable: las piezas cerradas no son ns=legs/2.
        # A slab has no stirrups, and no count to write.
        if "n_legs" in df_export.columns or "ns" in df_export.columns:
            if "n_legs" in df_export.columns:
                canonical = df_export["n_legs"].copy()
            else:
                canonical = df_export["ns"].copy()
                canonical.iloc[1:] = pd.to_numeric(canonical.iloc[1:]) * 2
            canonical.iloc[0] = ""
            df_export = df_export.drop(columns=[col for col in ("ns", "n_legs", "legs") if col in df_export.columns])
            df_export["legs"] = canonical
        df_export.to_excel(path, index=False)
        print(f"✅ {self._ELEMENT_COLUMN} design exported to {path}")

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
        print(f"✅ {self._ELEMENT_COLUMN} design imported and summary data updated.")

    def results_detailed_doc(self, index: int = 1) -> None:
        """Export detailed results for one beam, plus summary tables for all, to Word.

        The assembly lives in :mod:`mento.reports.summaries`.

        Parameters
        ----------
        index : int
            1-based index of the beam to show detailed results for (default: 1)
        """
        beam_summary_doc(self, index)
