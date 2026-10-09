from __future__ import annotations

import math
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from pandas import DataFrame

from mento import MPa, cm, ft, inch, kip, kN, kNm, m, mm
from mento.bar_sizes import bar_designation
from mento.beam_summary import _declared, _is_unlabelled
from mento.codes.registry import design_code
from mento.design_results import spacing_separator
from mento.forces import Forces
from mento.i18n import translate_dataframe
from mento.material import Concrete, SteelBar
from mento.node import Node
from mento.precompute import shown
from mento.reports.summaries import wall_summary_doc
from mento.shear_wall import ShearWall


def _wall_passes(wall: ShearWall) -> bool:
    """Whether the wall carries every combination of its last check and misses no limit.

    Read off the public results rather than the report's flag, which holds the
    combination that ran last. The warnings cover the mesh ratios, the spacing
    and the section limit of the wall's code -- §11.6.2, §11.7 and §11.5.4.2
    of ACI 318-19 / CIRSOC 201-25, §9.6.2, §9.6.3 and Eq. (6.9) of EN
    1992-1-1 -- each over every combination; the DCR covers the strength of
    each one, with the tolerance the warnings use: a wall at exactly ØVn,max
    can come out at DCR 1.0000000000000002, and that is 1.
    """
    return all(check.DCR <= 1 or math.isclose(check.DCR, 1.0) for check in wall.shear_checks) and not wall.warnings


def _mesh_label(d_b: Any, s: Any, imperial: bool) -> str:
    """One direction of the mesh as the summary table writes it: ``Ø10/15`` (mm/cm), ``#4@8`` (in).

    In the units the section is detailed in: an imperial bar printed in mm and
    cm rounds #4 @ 8 in to "Ø13/20", a bar and a spacing nobody placed. A US
    bar is its ASTM size, and its spacing follows an ``@``, as on a drawing.
    """
    if imperial:
        return f"{bar_designation(d_b)}{spacing_separator(True)}{s.to('inch').magnitude:.4g}"
    return f"Ø{d_b.to('mm').magnitude:.0f}/{s.to('cm').magnitude:.0f}"


class ShearWallSummary:
    def __init__(self, concrete: Concrete, steel_bar: SteelBar, wall_list: DataFrame) -> None:
        self.concrete: Concrete = concrete
        self.steel_bar: SteelBar = steel_bar
        self.wall_list: DataFrame = wall_list
        self.units_row: List[str] = []
        self.data: DataFrame = DataFrame()
        self.nodes: List[Node] = []
        self.wall_keys: List[Tuple[str, str]] = []
        #: Positions in :attr:`data` of the rows of each node, in node order.
        self._node_rows: List[List[int]] = []
        self.check_and_process_input()
        self.convert_to_walls()

    # ------------------------------------------------------------------
    # Input processing
    # ------------------------------------------------------------------

    def check_and_process_input(self) -> None:
        self.units_row = self.wall_list.iloc[0].tolist()
        data = self.wall_list.iloc[1:].copy()

        self.units_row = ["" if pd.isna(unit) else unit for unit in self.units_row]
        self.validate_units(self.units_row)

        # Columns 3 onward are numeric (after Level, Label, Comb.)
        data.iloc[:, 3:] = data.iloc[:, 3:].astype(float).fillna(0)

        for i in range(1, len(self.units_row)):
            unit_str = self.units_row[i]
            if unit_str != "":
                unit = self.get_unit_variable(unit_str)
                if isinstance(data.iloc[:, i], pd.Series):
                    data.iloc[:, i] = data.iloc[:, i].apply(lambda x, u=unit: x * u)

        self.data = data

    def validate_units(self, units_row: List[str]) -> None:
        # Forces in kip and moments in kip·ft ("kipft") for an imperial wall,
        # whose results come back in kip.
        valid_units = {"m", "mm", "cm", "in", "inch", "ft", "kN", "kNm", "kip", "kipft", ""}
        for unit_str in units_row:
            if unit_str and unit_str not in valid_units:
                raise ValueError(f"Invalid unit '{unit_str}' detected. Allowed units: {valid_units}")

    def get_unit_variable(self, unit_str: str) -> Any:
        unit_map: Dict[str, Any] = {
            "mm": mm,
            "cm": cm,
            "m": m,
            "in": inch,
            "inch": inch,
            "ft": ft,
            "kN": kN,
            "kNm": kNm,
            "kip": kip,
            "kipft": kip * ft,
            "MPa": MPa,
        }
        if unit_str in unit_map:
            return unit_map[unit_str]
        raise ValueError(f"Unit '{unit_str}' is not recognized.")

    # ------------------------------------------------------------------
    # Grouping rows → walls + nodes
    # ------------------------------------------------------------------

    def convert_to_walls(self) -> None:
        """Build one node per wall from the rows of :attr:`data`.

        The rows that share ``Level`` and ``Label`` are one wall under several
        load combinations, checked and designed for their envelope. A row with
        no label is a wall of its own. The rows of a wall must agree on ``t``,
        ``lw``, ``hw`` and ``cc``; the mesh may be given on one row only, but
        rows that give a direction of it must give the same one. Anything else
        raises a ``ValueError`` naming the wall.
        """
        self.nodes = []
        self.wall_keys = []
        self._node_rows = []
        rows = [row for _, row in self.data.reset_index(drop=True).iterrows()]
        by_key: Dict[Tuple[str, str], List[int]] = {}
        for position, row in enumerate(rows):
            key = (str(row["Level"]), str(row["Label"]))
            if _is_unlabelled(row["Label"]):
                self._node_rows.append([position])
                self.wall_keys.append(key)
            elif key in by_key:
                by_key[key].append(position)
            else:
                by_key[key] = [position]
                self._node_rows.append(by_key[key])
                self.wall_keys.append(key)

        for key, positions in zip(self.wall_keys, self._node_rows):
            self.nodes.append(self._wall_node(key, [rows[position] for position in positions]))

    def _wall_node(self, key: Tuple[str, str], rows: List["pd.Series[Any]"]) -> Node:
        """The node of one wall, from the rows that describe it."""
        first = rows[0]
        for row in rows[1:]:
            self._validate_geometry_consistency(first, row, key)

        wall = ShearWall(
            level=key[0],
            label=key[1],
            concrete=self.concrete,
            steel_bar=self.steel_bar,
            thickness=first["t"],
            length=first["lw"],
            height=first["hw"],
            c_c=first["cc"],
        )

        name = f"{key[0]} - {key[1]}"
        horizontal = _declared(rows, ("dbh", "sh"), name, "horizontal mesh", "Wall")
        if horizontal is not None and horizontal[1].magnitude != 0:
            wall.set_horizontal_rebar(d_b=horizontal[0], s=horizontal[1])
        vertical = _declared(rows, ("dbv", "sv"), name, "vertical mesh", "Wall")
        if vertical is not None and vertical[1].magnitude != 0:
            wall.set_vertical_rebar(d_b=vertical[0], s=vertical[1])

        forces = [Forces(label=row["Comb."], N_x=row["Nx"], V_z=row["Vz"], M_y=row["My"]) for row in rows]
        return Node(section=wall, forces=forces)

    def _validate_geometry_consistency(self, first: Any, row: "pd.Series[Any]", key: Tuple[str, str]) -> None:
        for col in ("t", "lw", "hw", "cc"):
            val_first = first[col]
            val_row = row[col]
            if abs(val_first.magnitude - val_row.magnitude) > 1e-6:
                raise ValueError(
                    f"Geometry mismatch for wall {key}: '{col}' differs between rows "
                    f"({val_first} vs {val_row}). All rows in the same (Level, Label) "
                    f"group must have identical geometry."
                )

    # ------------------------------------------------------------------
    # Check
    # ------------------------------------------------------------------

    def check(self) -> DataFrame:
        """One row per wall: its geometry, its mesh, the governing combination and the status.

        Written in the unit system of the concrete: t in cm, lw and hw in m,
        the mesh in mm/cm and the forces in kN for a metric wall; t in in, lw
        and hw in ft, the mesh in in and the forces in kip for an imperial one.
        """
        results_list = []
        imperial = self.concrete.unit_system != "metric"
        # What the code calls the ratios, the demand and the capacity: ρt / Vu / ØVn
        # under ACI 318-19 and CIRSOC 201-25, ρh / VEd / VRd under EN 1992-1-1.
        names = design_code(self.concrete).wall_summary_columns
        rho_h, rho_v = names["rho_h"], names["rho_v"]
        demand, capacity = names["shear_demand"], names["shear_capacity"]

        for node in self.nodes:
            wall: ShearWall = node.section  # type: ignore

            if wall._d_b_h.magnitude == 0 or wall._s_h.magnitude == 0:
                raise ValueError(
                    f"Wall '{wall.level} - {wall.label}' has no horizontal rebar assigned. "
                    f"All walls must have rebar for check(). "
                    f"Either run design() first or provide rebar in the input."
                )
            if wall._d_b_v.magnitude == 0 or wall._s_v.magnitude == 0:
                raise ValueError(
                    f"Wall '{wall.level} - {wall.label}' has no vertical rebar assigned. "
                    f"All walls must have rebar for check(). "
                    f"Either run design() first or provide rebar in the input."
                )

            node.check_shear()

            # The combination with the largest DCR, read off the public results
            # rather than the check table, whose columns are named per code.
            limiting = max(wall.shear_checks, key=lambda check: check.DCR)

            rebar_h = _mesh_label(wall._d_b_h, wall._s_h, imperial)
            rebar_v = _mesh_label(wall._d_b_v, wall._s_v, imperial)
            if imperial:
                t = round(wall.thickness.to("inch").magnitude, 2)
                lw = round(wall.length.to("ft").magnitude, 2)
                hw = round(wall.height.to("ft").magnitude, 2)
            else:
                t = int(wall.thickness.to("cm").magnitude)
                lw = round(wall.length.to("m").magnitude, 2)
                hw = round(wall.height.to("m").magnitude, 2)

            # The status is the AND over every combination: the strength of each
            # one and no limit missed under any of them. `wall.warnings` already
            # spans the combinations -- ρl,min in particular changes with the
            # shear, so a wall can miss it under the governing combination and
            # meet it under the last one checked.
            status = "✅" if _wall_passes(wall) else "❌"

            results_dict = OrderedDict(
                {
                    "Level": wall.level,
                    "Label": wall.label,
                    "t": t,
                    "lw": lw,
                    "hw": hw,
                    "Horiz.": rebar_h,
                    "Vert.": rebar_v,
                    rho_h: round(float(wall._rho_t.magnitude), 5),
                    rho_v: round(float(wall._rho_l.magnitude), 5),
                    demand: round(shown(limiting.V_u, "force", imperial, 2), 1),
                    capacity: round(shown(limiting.V_capacity, "force", imperial, 2), 1),
                    "DCR": round(limiting.DCR, 3),
                    "Status": status,
                }
            )
            results_list.append(results_dict)

        # The mesh columns carry a unit only where both of their numbers share one.
        v_unit, t_unit, l_unit, mesh_unit = ("kip", "in", "ft", "in") if imperial else ("kN", "cm", "m", "")

        units_row = pd.DataFrame(
            [
                OrderedDict(
                    {
                        "Level": "",
                        "Label": "",
                        "t": t_unit,
                        "lw": l_unit,
                        "hw": l_unit,
                        "Horiz.": mesh_unit,
                        "Vert.": mesh_unit,
                        rho_h: "",
                        rho_v: "",
                        demand: v_unit,
                        capacity: v_unit,
                        "DCR": "",
                        "Status": "",
                    }
                )
            ]
        )

        results_df = pd.DataFrame(results_list)
        return translate_dataframe(pd.concat([units_row, results_df], ignore_index=True))

    # ------------------------------------------------------------------
    # Design
    # ------------------------------------------------------------------

    def design(self) -> DataFrame:
        design_df: DataFrame = self.data.reset_index(drop=True).copy()

        for node, positions in zip(self.nodes, self._node_rows):
            wall: ShearWall = node.section  # type: ignore
            node.design_shear()
            # Every row of the wall gets the mesh designed for all of them.
            design_df.loc[positions, "dbh"] = wall._d_b_h  # type: ignore
            design_df.loc[positions, "sh"] = wall._s_h  # type: ignore
            design_df.loc[positions, "dbv"] = wall._d_b_v  # type: ignore
            design_df.loc[positions, "sv"] = wall._s_v  # type: ignore

        self.design_data = design_df
        print("✅ Shear wall design completed for all walls in Summary.")
        return design_df

    # ------------------------------------------------------------------
    # Shear results
    # ------------------------------------------------------------------

    def shear_results(self, index: Optional[int] = None) -> DataFrame:
        if index is not None:
            if index < 1 or index > len(self.nodes):
                raise IndexError(f"Index {index} is out of range. Valid: 1 to {len(self.nodes)}")
            node = self.nodes[index - 1]
            return translate_dataframe(node.check_shear())

        results = []
        units_row_added = False
        for node in self.nodes:
            df = node.check_shear()
            if not units_row_added:
                results.append(df.iloc[[0]])
                units_row_added = True
            results.append(df.iloc[1:])
        out: DataFrame = pd.concat(results, ignore_index=True)
        return translate_dataframe(out)

    # ------------------------------------------------------------------
    # Excel I/O
    # ------------------------------------------------------------------

    def export_design(self, path: str) -> None:
        if not hasattr(self, "design_data"):
            raise AttributeError("No design data found. Run .design() before exporting.")

        df_numeric = self.design_data.copy()
        units_by_column = dict(zip(self.wall_list.columns, self.units_row))
        for col in df_numeric.columns:
            unit_name = units_by_column[col]
            unit = self.get_unit_variable(unit_name) if unit_name else None
            df_numeric[col] = df_numeric[col].apply(
                lambda x, u=unit: x.to(u).magnitude if hasattr(x, "magnitude") and u else x
            )

        df_export = pd.concat(
            [
                pd.DataFrame([self.units_row], columns=self.wall_list.columns),
                df_numeric,
            ],
            ignore_index=True,
        )
        df_export.to_excel(path, index=False)
        print(f"✅ Shear wall design exported to {path}")

    def import_design(self, path: str) -> None:
        wall_df = pd.read_excel(path)
        self.wall_list = wall_df
        self.check_and_process_input()
        self.convert_to_walls()
        print("✅ Shear wall design imported and summary data updated.")

    # ------------------------------------------------------------------
    # Word export
    # ------------------------------------------------------------------

    def results_detailed_doc(self, index: int = 1) -> None:
        """Export detailed results for one wall, plus summary tables for all, to Word.

        The assembly lives in :mod:`mento.reports.summaries`.
        """
        wall_summary_doc(self, index)
