"""A list of shear walls read from two tables: the sections, and the forces each one carries."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Mapping, Optional, Sequence

import pandas as pd
from pandas import DataFrame

from mento.codes.registry import design_code
from mento.bar_sizes import bar_designation
from mento.design_results import spacing_separator
from mento.node import Node
from mento.precompute import shown, unit_label
from mento.reports.summaries import WALL_REPORT
from mento.shear_wall import ShearWall
from mento.summary_base import (
    Index,
    Key,
    SectionVerdict,
    _TwoTableSummary,
    frame_with_units,
    governing,
    section_dimension,
    translated,
    verdict_passes,
    warning_tags,
)
from mento.summary_tables import (
    SummaryInputError,
    TableSpec,
    forces_columns,
    key_text,
    length,
    text,
    unit_of,
)
from mento.units import Quantity

WALL_SPEC = TableSpec(
    kind="wall",
    element="ShearWallSummary",
    sections=(
        text("Level"),
        text("Label", required=True),
        length("t", "cm", "in", dimension=True),
        length("lw", "m", "ft", dimension=True),
        length("hw", "m", "ft", dimension=True),
        length("cc", "mm", "in", dimension=True),
        length("dbh", "mm", "in"),
        length("sh", "cm", "in"),
        length("dbv", "mm", "in"),
        length("sv", "cm", "in"),
        text("Notes"),
    ),
    forces=forces_columns(moment_required=False),
)

#: The mesh columns of a wall: the bar and the spacing of each direction.
MESH = (("dbh", "sh"), ("dbv", "sv"))


def _mesh_label(d_b: Quantity, s: Quantity, imperial: bool) -> str:
    """One direction of the mesh as the summary table writes it: ``Ø10/15`` (mm/cm), ``#4@8`` (in).

    In the units the section is detailed in: an imperial bar printed in mm and
    cm rounds #4 @ 8 in to "Ø13/20", a bar and a spacing nobody placed. A US
    bar is its ASTM size, and its spacing follows an ``@``, as on a drawing.
    ``-`` for a direction with no bars.
    """
    if d_b.magnitude == 0 or s.magnitude == 0:
        return "-"
    if imperial:
        return f"{bar_designation(d_b)}{spacing_separator(True)}{s.to('inch').magnitude:.4g}"
    return f"Ø{d_b.to('mm').magnitude:.0f}/{s.to('cm').magnitude:.0f}"


def _given(value: Optional[Quantity]) -> bool:
    return value is not None and value.magnitude > 0


def _whole(value: float) -> Any:
    """A length to two decimals, whole where it is whole: 3, not 3.0."""
    rounded = round(float(value), 2)
    return int(rounded) if rounded.is_integer() else rounded


def _rounded(value: Optional[Quantity], imperial: bool) -> float:
    return math.nan if value is None else round(shown(value, "force", imperial), 1)


class ShearWallSummary(_TwoTableSummary):
    """Check and design the in-plane shear of a list of walls, read from a sections table and a forces table.

    ``sections`` has one row per wall, keyed by ``(Level, Label)``:

    ``Level, Label, t, lw, hw, cc, dbh, sh, dbv, sv, Notes``

    ``t`` is the thickness, ``lw`` the length, ``hw`` the height and ``cc`` the
    cover; ``dbh/sh`` and ``dbv/sv`` are the horizontal and vertical mesh, the
    bar and spacing on each face (two curtains). ``forces`` has one row per
    combination, ``Level, Label, Comb., Nx, Vz, My, Notes``. ``My`` is kept
    and written back but not used: the summary checks the in-plane shear
    (ACI 318-19 / CIRSOC 201-25 §11.5), and the vertical mesh it designs is the
    shear minimum of §11.6.2, not what P-M or a boundary element would ask.
    """

    _SPEC = WALL_SPEC
    _ELEMENT_COLUMN = "Wall"
    _REPORT = WALL_REPORT
    _ALWAYS_LEVEL = True

    @property
    def wall_list(self) -> DataFrame:
        """The single table this summary was built from (deprecated, removed in 2.0)."""
        return self._legacy("wall_list")

    @property
    def wall_keys(self) -> List[Any]:
        """The ``(Level, Label)`` of each wall, in the order of :attr:`nodes`: :attr:`labels`."""
        return self.labels

    _SECTION_TYPE = ShearWall

    def _validate_section_row(self, key: Key, row: Mapping[str, Any]) -> None:
        for d_b, s in MESH:
            has_d, has_s = _given(row.get(d_b)), _given(row.get(s))
            if has_d != has_s:
                given, missing = (d_b, s) if has_d else (s, d_b)
                raise SummaryInputError("incomplete_group", label=repr(key_text(key)), given=given, missing=missing)

    def _section(self, key: Key, row: Mapping[str, Any]) -> ShearWall:
        wall = ShearWall(
            level=key[0],
            label=key[1],
            concrete=self.concrete,
            steel_bar=self.steel_bar,
            thickness=row["t"],
            length=row["lw"],
            height=row["hw"],
            c_c=row["cc"],
        )
        if _given(row.get("dbh")):
            wall.set_horizontal_rebar(d_b=row["dbh"], s=row["sh"])
        if _given(row.get("dbv")):
            wall.set_vertical_rebar(d_b=row["dbv"], s=row["sv"])
        return wall

    def _section_row(self, section: ShearWall) -> Dict[str, Any]:
        zero = 0 * unit_of("in" if self.concrete.is_imperial else "mm")
        mesh = section.mesh
        row: Dict[str, Any] = {"t": section.thickness, "lw": section.length, "hw": section.height, "cc": section.c_c}
        for (d_b, s), direction in zip(MESH, (mesh.horizontal, mesh.vertical)):
            row[d_b] = direction.d_b if direction.has_bars else zero
            row[s] = direction.s if direction.has_bars else zero
        return row

    def _has_reinforcement(self, section: ShearWall) -> bool:
        return section.mesh.horizontal.has_bars or section.mesh.vertical.has_bars

    def _check_record(self, key: Key, node: Node) -> SectionVerdict:
        wall: ShearWall = node.section  # type: ignore[assignment]
        names = self._combination_names(node)
        shear = governing(names, [(check.DCR, check.V_u, check.N_u) for check in wall.shear_checks])
        found = tuple(wall.warnings)
        return SectionVerdict(key, "checked", None, None, shear, found, verdict_passes((shear,), found))

    def check(self, capacity_check: bool = False) -> DataFrame:
        """One row per wall: its geometry, its mesh, the governing combination, its warnings and its status.

        Written in the unit system of the concrete: t in cm, lw and hw in m,
        the mesh in mm/cm and the forces in kN for a metric wall; t in in, lw
        and hw in ft, the mesh in in and the forces in kip for an imperial one.
        A wall has no capacity check: ``capacity_check=True`` raises.
        """
        if capacity_check:
            raise ValueError("ShearWallSummary.check() has no capacity check.")
        return super().check()

    def _check_table(self, records: Sequence[SectionVerdict]) -> DataFrame:
        imperial = self.concrete.is_imperial
        long_unit = "ft" if imperial else "m"
        # What the code calls the ratios, the demand and the capacity: ρt / Vu / ØVn
        # under ACI 318-19 and CIRSOC 201-25, ρh / VEd / VRd under EN 1992-1-1. The
        # demand is the governing combination's, not the largest shear.
        names = design_code(self.concrete).wall_summary_columns
        rho_h, rho_v, capacity_name = names["rho_h"], names["rho_v"], names["shear_capacity"]
        demand_name = names["shear_demand"].replace(",max", "")
        axial_name = "NEd" if demand_name == "VEd" else "Nu"
        rows = []
        for record, node in zip(records, self._nodes):
            wall: ShearWall = node.section  # type: ignore[assignment]
            mesh = wall.mesh
            shear = record.shear
            capacity: Optional[Quantity] = None
            if shear is not None and shear.demand is not None:
                capacity = next(
                    check.V_capacity
                    for check in wall.shear_checks
                    if math.isclose(check.DCR, shear.DCR) and check.V_u == shear.demand
                )
            rows.append(
                {
                    "Level": record.level,
                    "Label": record.label,
                    "t": round(shown(wall.thickness, "length", imperial), 2),
                    "lw": round(wall.length.to(long_unit).magnitude, 2),
                    "hw": round(wall.height.to(long_unit).magnitude, 2),
                    "Horiz. (each face)": _mesh_label(mesh.horizontal.d_b, mesh.horizontal.s, imperial),
                    "Vert. (each face)": _mesh_label(mesh.vertical.d_b, mesh.vertical.s, imperial),
                    rho_h: round(float(mesh.horizontal.rho), 5),
                    rho_v: round(float(mesh.vertical.rho), 5),
                    "Comb.": (", ".join(shear.combinations) or "-") if shear is not None else "-",
                    demand_name: _rounded(shear.demand if shear is not None else None, imperial),
                    axial_name: _rounded(shear.axial if shear is not None else None, imperial),
                    capacity_name: _rounded(capacity, imperial),
                    "DCR": math.nan if shear is None else round(shear.DCR, 3),
                    "Warnings": warning_tags(record.warnings),
                    "Status": self._verdict_text(record),
                }
            )
        force = unit_label("force", imperial)
        mesh_unit = "in" if imperial else ""
        units = {
            "Level": "",
            "Label": "",
            "t": unit_label("length", imperial),
            "lw": long_unit,
            "hw": long_unit,
            "Horiz. (each face)": mesh_unit,
            "Vert. (each face)": mesh_unit,
            rho_h: "",
            rho_v: "",
            "Comb.": "",
            demand_name: force,
            axial_name: force,
            capacity_name: force,
            "DCR": "",
            "Warnings": "",
            "Status": "",
        }
        return translated(frame_with_units(units, rows))

    def _sections_overview(self) -> DataFrame:
        """The walls as the Word report lists them: their size, cover and mesh on each face."""
        imperial = self.concrete.is_imperial
        long_unit = "ft" if imperial else "m"
        cover = "length" if imperial else "bar"
        rows = []
        for key, node in zip(self._keys, self._nodes):
            wall: ShearWall = node.section  # type: ignore[assignment]
            mesh = wall.mesh
            rows.append(
                {
                    "Level": key[0],
                    "Label": key[1],
                    "t": section_dimension(wall.thickness, imperial),
                    "lw": _whole(wall.length.to(long_unit).magnitude),
                    "hw": _whole(wall.height.to(long_unit).magnitude),
                    "cc": section_dimension(wall.c_c, imperial, cover),
                    "Horiz. (each face)": _mesh_label(mesh.horizontal.d_b, mesh.horizontal.s, imperial),
                    "Vert. (each face)": _mesh_label(mesh.vertical.d_b, mesh.vertical.s, imperial),
                }
            )
        units = {
            "Level": "",
            "Label": "",
            "t": unit_label("length", imperial),
            "lw": long_unit,
            "hw": long_unit,
            "cc": unit_label(cover, imperial),
            "Horiz. (each face)": "in" if imperial else "",
            "Vert. (each face)": "in" if imperial else "",
        }
        return frame_with_units(units, rows)

    def _capacity_table(self) -> DataFrame:  # pragma: no cover - check() raises first
        raise ValueError("ShearWallSummary.check() has no capacity check.")

    def shear_results(self, index: Optional[Index] = None) -> DataFrame:
        """The shear table of every combination, of one wall (``index``: 1-based, or its label) or of all."""
        nodes = [self._node_with_forces(index)] if index is not None else [n for n in self._nodes if n.forces]
        first: Any = self._nodes[0].section
        frames: List[DataFrame] = [first._get_units_row_shear_wall()] if not nodes else []
        for node in nodes:
            table = node.check_shear()
            frames.append(table if not frames else table.iloc[1:])
        return translated(pd.concat(frames, ignore_index=True))

    def results_detailed_doc(self, index: Index = 1) -> None:
        """Write a Word report: the detailed shear of one wall, then the tables of all.

        ``index`` is the wall's position (1-based) in the sections table, its
        label or its ``(Level, Label)``. Saved as
        ``Shear_Wall_Summary_{design_code}.docx`` in the current directory.
        """
        from mento.reports.summaries import wall_summary_doc

        wall_summary_doc(self, index)
