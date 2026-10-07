"""What every summary shares: two tables in, one node per section, frozen results out.

A summary reads a sections table (one row per section) and a forces table (one
row per load combination) -- see :mod:`mento.summary_tables` -- and keeps one
:class:`~mento.node.Node` per section, sections without forces included. The
nodes are the only state: the tables a summary writes are read off them, so a
design, ``to_excel`` and ``from_nodes`` all go through the same writer.

``check()`` runs ``node.check()`` on every section and keeps what it found as a
:class:`SectionVerdict` per section (:attr:`_TwoTableSummary.results`); the
table it returns is a presentation of those records. Each DCR comes with the
combinations that govern it and their demand, read off the frozen results of
the element (``FlexureCheck.M_demand``, ``ShearCheck.V_demand``), and the
verdict counts the section's warnings: a section that misses a detailing limit
is not OK.

The element-specific parts are hooks of :class:`_TwoTableSummary`: the spec of
its tables, how a row becomes a section and a section a row (exact inverses),
how a section is designed and how its reinforcement is written in ``check()``.
"""

from __future__ import annotations

import copy
import math
import warnings as _warnings
from dataclasses import dataclass
from typing import IO, TYPE_CHECKING, Any, Dict, Iterable, List, Literal, Mapping, Optional, Sequence, Tuple, Union

import pandas as pd
from pandas import DataFrame

from mento.codes.registry import design_code
from mento.design_warnings import DesignWarning, combination_label
from mento.forces import Forces
from mento.i18n import translate, translate_dataframe
from mento.material import Concrete, SteelBar
from mento.node import Node
from mento.precompute import shown, unit_label
from mento.results import FAIL_MARK, PASS_MARK, VERDICT_COLUMN
from mento.summary_tables import (
    FORCE_NAMES,
    FORCES_SHEET,
    SECTIONS_SHEET,
    UNITS,
    SummaryInputError,
    SummaryInputWarning,
    TableSpec,
    _listed,
    key_text,
    label_of,
    looks_like_single_table,
    looks_swapped,
    read_table,
    read_workbook,
    single_table_error,
    unit_of,
    write_table,
    write_workbook,
)
from mento.units import Quantity

if TYPE_CHECKING:
    from mento.reports.summaries import SummaryReport

Key = Tuple[str, str]
#: How a section is named to a method that reads one: its 1-based position, its label, or ``(Level, Label)``.
Index = Union[int, str, Tuple[str, str]]

#: Columns of the per-combination tables that hold words: ``translate_dataframe``
#: covers the first column, but "Position" sits in the middle of the flexure table.
_WORD_COLUMNS = ("Position",)


def translated(df: DataFrame) -> DataFrame:
    """A summary table in the language reports are rendered in: its headers, its first column and its words.

    The symbol columns -- ``b×h``, ``As,bot``, ``Av``, ``Mu``, ``DCRv`` -- are
    variable names, and units and numbers read the same in every language.
    """
    out = df.copy()
    for column in _WORD_COLUMNS:
        if column in out.columns:
            out[column] = [translate(value) if isinstance(value, str) else value for value in out[column]]
    return translate_dataframe(out)


def section_dimension(length: Quantity, imperial: bool, kind: str = "length") -> Any:
    """A width, a height or a cover for a summary table: whole where it is whole, else to two decimals.

    ``kind`` is the display kind of :mod:`mento.precompute`: ``"length"``
    (cm, in) by default, ``"bar"`` for a cover shown in mm.
    """
    value = shown(length, kind, imperial, 2)
    return int(value) if float(value).is_integer() else value


#: Every summary's table spec, so a table of one kind given to another is named for what it is.
_SPECS: List[TableSpec] = []


# ---------------------------------------------------------------------------
# Frozen results
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GoverningDemand:
    """The largest DCR of one kind over a section's combinations, and where it comes from.

    ``combinations`` names every combination tied at that DCR, in the order
    they were given; a name repeated within the section carries its position,
    ``"ENV (#3)"``. Empty when no combination demands anything of it (a face no
    moment puts in tension). ``demand`` is that combination's moment, with its
    sign, or its shear, in magnitude -- the one the DCR was formed from --, and
    ``axial`` its axial load (positive in compression). Where tied
    combinations differ, the demand of largest magnitude is shown; it belongs
    to one of those named.
    """

    combinations: Tuple[str, ...]
    demand: Optional[Quantity]
    axial: Optional[Quantity]
    DCR: float
    admissible: bool = True

    @property
    def complies(self) -> bool:
        """``DCR <= 1`` (to the tolerance the warnings use) and within the face's maximum steel."""
        return _within(self.DCR) and self.admissible


@dataclass(frozen=True)
class SectionVerdict:
    """What ``check()`` found for one section.

    ``status`` is ``"checked"``, ``"no_forces"`` (the forces table names no
    combination for it) or ``"no_reinforcement"`` (no bars on either face, or
    no mesh: run ``design()``); the last two have no demands and ``passes`` is
    ``None``. ``top`` and ``bottom`` are the flexure of each face and ``shear``
    the shear (the in-plane shear of a wall, which has no faces). ``warnings``
    are the section's, read right after its check; ``passes`` requires every
    DCR within 1, every face admissible and no warning.
    """

    key: Key
    status: Literal["checked", "no_forces", "no_reinforcement"]
    top: Optional[GoverningDemand]
    bottom: Optional[GoverningDemand]
    shear: Optional[GoverningDemand]
    warnings: Tuple[DesignWarning, ...]
    passes: Optional[bool]

    @property
    def level(self) -> str:
        return self.key[0]

    @property
    def label(self) -> str:
        return self.key[1]


def _within(dcr: float) -> bool:
    """A DCR that passes: at most 1, a rounding error past it included (1.0000000000000002 is 1)."""
    return dcr <= 1 or math.isclose(dcr, 1.0)


def _magnitude(value: Optional[Quantity]) -> float:
    return 0.0 if value is None else float(abs(value.magnitude))


def _signed(value: Optional[Quantity]) -> float:
    return 0.0 if value is None else float(value.magnitude)


def governing(
    names: Sequence[str],
    entries: Sequence[Tuple[float, Optional[Quantity], Optional[Quantity]]],
    admissible: bool = True,
) -> GoverningDemand:
    """The governing combinations among ``entries``, one ``(DCR, demand, axial)`` per combination.

    Every combination tied (``math.isclose``) at the largest DCR is named, so
    the answer does not depend on the order of the rows.
    """
    if not entries or max(entry[0] for entry in entries) == 0:
        return GoverningDemand((), None, None, 0.0, admissible)
    top = max(entry[0] for entry in entries)
    tied = [i for i, entry in enumerate(entries) if math.isclose(entry[0], top)]
    pick = max(
        tied,
        key=lambda i: (
            _magnitude(entries[i][1]),
            _signed(entries[i][1]),
            _signed(entries[i][2]),
        ),
    )
    return GoverningDemand(
        combinations=tuple(names[i] for i in tied),
        demand=entries[pick][1],
        axial=entries[pick][2],
        DCR=top,
        admissible=admissible,
    )


def verdict_passes(demands: Iterable[Optional[GoverningDemand]], warnings: Sequence[DesignWarning]) -> bool:
    """Every DCR within 1, every face within its maximum steel, and no warning."""
    return all(d.complies for d in demands if d is not None) and not warnings


# ---------------------------------------------------------------------------
# Warning tags of the check table
# ---------------------------------------------------------------------------


def warning_tag(warning: DesignWarning) -> str:
    """One warning as the check table writes it: its stable code, and the face or direction it is read on.

    ``As_below_min (bottom)``, ``mesh_ratio_below_min (v)``: the codes of
    :mod:`mento.design_warnings`, the same in every language, so a program
    reading the table reads what ``summary.warnings`` holds. The Word report
    words each one in full in its own table.
    """
    where = warning.face or warning.values.get("direction")
    return f"{warning.code} ({where})" if where else warning.code


def warning_tags(warnings: Sequence[DesignWarning]) -> str:
    """The warnings of a section for the check table, joined by commas; ``-`` for none."""
    return ", ".join(warning_tag(w) for w in warnings) or "-"


#: What the verdict column says of a section it did not check.
STATUS_TEXT = {"no_forces": "no forces", "no_reinforcement": "no reinforcement: run design()"}


# ---------------------------------------------------------------------------
# The summary
# ---------------------------------------------------------------------------


class _TwoTableSummary:
    """A list of sections read from a sections table and a forces table; see the module docstring.

    Subclasses set :attr:`_SPEC`, :attr:`_ELEMENT_COLUMN` and :attr:`_REPORT`
    and implement the hooks below.
    """

    #: The columns of the two tables.
    _SPEC: TableSpec
    #: The header of the first column of ``check()``: ``"Beam"``, ``"Slab"``, ``"Wall"``.
    _ELEMENT_COLUMN: str = "Section"
    #: What the Word report calls the elements and its tables.
    _REPORT: "SummaryReport"
    #: The class of the sections, exactly: a subclass has settings or reinforcement a row does not hold.
    _SECTION_TYPE: type
    #: Whether ``Level`` is shown even when every section leaves it empty.
    _ALWAYS_LEVEL = False

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        spec = cls.__dict__.get("_SPEC")
        if spec is not None and spec not in _SPECS:
            _SPECS.append(spec)

    def __init__(
        self,
        concrete: Concrete,
        steel_bar: SteelBar,
        sections: Optional[DataFrame] = None,
        forces: Optional[DataFrame] = None,
        **legacy: Any,
    ) -> None:
        self.concrete: Concrete = concrete
        self.steel_bar: SteelBar = steel_bar
        unexpected = sorted(set(legacy) - {"beam_list", "slab_list", "wall_list"})
        if unexpected:
            raise TypeError(f"{type(self).__name__}() got an unexpected keyword argument {unexpected[0]!r}")
        if legacy:
            table = next(iter(legacy.values()))
            found = [str(c) for c in getattr(table, "columns", ()) if str(c) in FORCE_NAMES]
            raise single_table_error(self._SPEC, found or list(legacy))
        if sections is None:
            raise TypeError(f"{type(self).__name__}() needs the sections table and the forces table.")
        self._load(sections, forces)

    # -- reading ------------------------------------------------------------

    def _others(self) -> List[TableSpec]:
        """The specs of the other summaries, to name a table of theirs given to this one."""
        import mento.beam_summary  # noqa: F401 -- each summary registers its spec when defined
        import mento.shear_wall_summary  # noqa: F401
        import mento.slab_summary  # noqa: F401

        return [spec for spec in _SPECS if spec is not self._SPEC]

    def _load(self, sections: DataFrame, forces: Optional[DataFrame]) -> None:
        spec = self._SPEC
        if looks_like_single_table(sections, spec):
            raise single_table_error(spec, [str(c) for c in sections.columns if str(c) in FORCE_NAMES])
        if looks_swapped(sections, forces, spec):
            raise SummaryInputError(
                "swapped_tables", columns=_listed([str(c) for c in sections.columns if str(c) in FORCE_NAMES])
            )
        if forces is None:
            raise SummaryInputError("missing_forces", element=spec.element)

        section_table = read_table(sections, spec, "sections", self._others())
        force_table = read_table(forces, spec, "forces", self._others())

        keys: List[Key] = []
        seen: Dict[Key, List[int]] = {}
        for row, position in zip(section_table.rows, section_table.positions):
            key = (row.get("Level", ""), row["Label"])
            seen.setdefault(key, []).append(position)
            keys.append(key)
        for key, rows in seen.items():
            if len(rows) > 1:
                raise SummaryInputError("duplicate_section", label=repr(key_text(key)), rows=", ".join(map(str, rows)))

        nodes: List[Node] = []
        for key, row in zip(keys, section_table.rows):
            self._validate_section_row(key, row)
            nodes.append(Node(self._section(key, self._complete_row(row)), []))

        force_notes: List[List[str]] = [[] for _ in keys]
        unknown: Dict[str, List[int]] = {}
        combinations: Dict[Tuple[int, str], List[int]] = {}
        index = {key: i for i, key in enumerate(keys)}
        by_label: Dict[str, List[int]] = {}
        for i, key in enumerate(keys):
            by_label.setdefault(key[1], []).append(i)
        for row, position in zip(force_table.rows, force_table.positions):
            key = (row.get("Level", ""), row["Label"])
            at = index.get(key)
            if at is None and "Level" not in force_table.given and len(by_label.get(key[1], [])) == 1:
                at = by_label[key[1]][0]
            if at is None:
                unknown.setdefault(key_text(key), []).append(position)
                continue
            values = {name: row.get(name, 0 * unit_of("kNm" if name == "My" else "kN")) for name in ("Nx", "Vz", "My")}
            comb = row.get("Comb.", "")
            if comb:
                combinations.setdefault((at, comb), []).append(position)
            nodes[at].forces.append(
                Forces(label=comb if comb else None, N_x=values["Nx"], V_z=values["Vz"], M_y=values["My"])
            )
            force_notes[at].append(row.get("Notes", ""))
        if unknown:
            label, rows = next(iter(unknown.items()))
            raise SummaryInputError("unknown_section", label=repr(label), rows=", ".join(map(str, rows)))
        for (at, comb), rows in combinations.items():
            if len(rows) > 1:
                raise SummaryInputError(
                    "duplicate_combination",
                    combination=repr(comb),
                    label=repr(key_text(keys[at])),
                    rows=", ".join(map(str, rows)),
                )

        units = {
            "sections": self._units_for("sections", section_table.units),
            "forces": self._units_for("forces", force_table.units),
        }
        self._set_state(
            keys,
            nodes,
            [row.get("Notes", "") for row in section_table.rows],
            force_notes,
            units,
            written={
                "sections": {c for c in ("Level", "Notes") if c in section_table.given},
                "forces": {c for c in ("Level", "Notes") if c in force_table.given},
            },
        )
        if "Nx" not in force_table.given and force_table.rows:
            self._warn(SummaryInputWarning("no_axial_column"))
        self._warn_about_forces()

    def _units_for(self, table: str, given: Mapping[str, str]) -> Dict[str, str]:
        """The unit of every column: the one the table gave, or the default of the unit system."""
        imperial = self.concrete.is_imperial
        return {
            column.name: given.get(column.name, column.default_unit(imperial)) for column in self._SPEC.columns(table)
        }

    def _complete_row(self, row: Mapping[str, Any]) -> Dict[str, Any]:
        """A sections row with every column, the ones the table did not give at zero."""
        imperial = self.concrete.is_imperial
        out: Dict[str, Any] = {}
        for column in self._SPEC.sections:
            if column.name in row:
                out[column.name] = row[column.name]
            elif column.kind == "text":
                out[column.name] = ""
            elif column.kind == "count":
                out[column.name] = 0
            else:
                out[column.name] = 0 * unit_of(column.default_unit(imperial))
        return out

    def _set_state(
        self,
        keys: List[Key],
        nodes: List[Node],
        section_notes: List[str],
        force_notes: List[List[str]],
        units: Dict[str, Dict[str, str]],
        written: Dict[str, set[str]],
    ) -> None:
        self._keys: List[Key] = keys
        self._nodes: List[Node] = nodes
        self._section_notes: List[str] = section_notes
        self._force_notes: List[List[str]] = force_notes
        self._units: Dict[str, Dict[str, str]] = units
        self._written: Dict[str, set[str]] = written
        self._results: Tuple[SectionVerdict, ...] = ()
        self._input_warnings: List[SummaryInputWarning] = []

    def _warn(self, warning: SummaryInputWarning) -> None:
        self._input_warnings.append(warning)
        _warnings.warn(warning, stacklevel=4)

    def _warn_about_forces(self) -> None:
        """The warnings of what was read: sections without forces, and compressions past what a beam may take."""
        bare = [key_text(key) for key, node in zip(self._keys, self._nodes) if not node.forces]
        if bare:
            self._warn(SummaryInputWarning("section_without_forces", labels=_listed(bare)))
        beyond = []
        for key, node in zip(self._keys, self._nodes):
            limit = self._axial_limit(node.section)
            if limit is None:
                continue
            for position, force in enumerate(node.forces, 1):
                axial = force._N_x.to("kN").magnitude
                if axial >= limit.to("kN").magnitude or math.isclose(axial, limit.to("kN").magnitude):
                    beyond.append(f"{key_text(key)} / {combination_label(force.label, position)}")
        if beyond:
            self._warn(SummaryInputWarning("axial_load_beyond_beam", pairs=_listed(beyond)))

    # -- constructors -------------------------------------------------------

    @classmethod
    def from_excel(
        cls,
        concrete: Concrete,
        steel_bar: SteelBar,
        path: Union[str, IO[bytes], Any],
        *,
        sections_sheet: str = SECTIONS_SHEET,
        forces_sheet: str = FORCES_SHEET,
    ) -> Any:
        """A summary read from a file with the two sheets ``Sections`` and ``Forces``.

        Other sheets are ignored. A workbook laid out differently (a title
        above the headers, columns further right) is read with
        ``pandas.read_excel(..., skiprows=, usecols=)`` and passed as two
        ``DataFrame``.
        """
        sections, forces = read_workbook(path, sections_sheet, forces_sheet, cls._SPEC)
        return cls(concrete, steel_bar, sections, forces)

    @classmethod
    def from_nodes(
        cls,
        concrete: Concrete,
        steel_bar: SteelBar,
        nodes: Sequence[Node],
        *,
        units: Optional[Mapping[str, str]] = None,
    ) -> Any:
        """A summary of nodes built by hand, written as the two tables would hold them.

        Each node is a section, labelled with its section's ``label`` (and
        ``level``, for a wall), with its forces as its combinations. The
        summary rebuilds each section from the row it writes, so its
        ``check()`` is ``node.check()`` of every node; a node the table cannot
        hold -- settings other than the defaults, an out-of-plane moment
        ``M_x``, other materials, a stirrup diameter without stirrups -- raises
        :class:`~mento.summary_tables.SummaryInputError` rather than come back
        as another section. ``units`` sets the unit of a column of the tables
        it writes (``{"sl": "mm"}``).
        """
        summary = cls.__new__(cls)
        summary.concrete = concrete
        summary.steel_bar = steel_bar
        keys: List[Key] = []
        built: List[Node] = []
        for node in nodes:
            section = node.section
            key = (label_of(getattr(section, "level", None)), label_of(section.label))
            summary._representable(key, node)
            if key in keys:
                raise SummaryInputError(
                    "duplicate_section",
                    label=repr(key_text(key)),
                    rows=", ".join(str(i + 1) for i, k in enumerate(keys + [key]) if k == key),
                )
            keys.append(key)
            rebuilt = summary._section(key, summary._section_row(section))
            forces = [
                Forces(label=force.label, N_x=force._N_x, V_z=force._V_z, M_y=force._M_y) for force in node.forces
            ]
            built.append(Node(rebuilt, forces))
        given_units = dict(units or {})
        all_units = {
            table: {
                column.name: given_units.get(column.name, column.default_unit(concrete.is_imperial))
                for column in cls._SPEC.columns(table)
            }
            for table in ("sections", "forces")
        }
        for table in all_units.values():
            for name, unit in table.items():
                column = next(c for c in cls._SPEC.sections + cls._SPEC.forces if c.name == name)
                if unit not in column.allowed_units():
                    raise SummaryInputError(
                        "wrong_unit",
                        column=name,
                        table="given",
                        kind=column.kind,
                        unit=repr(unit),
                        allowed=_listed(column.allowed_units()),
                    )
        summary._set_state(
            keys,
            built,
            ["" for _ in keys],
            [["" for _ in node.forces] for node in built],
            all_units,
            written={"sections": set(), "forces": set()},
        )
        summary._warn_about_forces()
        return summary

    def _representable(self, key: Key, node: Node) -> None:
        """Raise if a node built by hand is not what its table row would build."""
        section: Any = node.section
        label = repr(key_text(key))
        concrete, steel = section.concrete, section.steel_bar
        same_concrete = (
            type(concrete) is type(self.concrete)
            and concrete.design_code == self.concrete.design_code
            and concrete.f_c == self.concrete.f_c
            and concrete.get_properties() == self.concrete.get_properties()
        )
        if not same_concrete:
            raise SummaryInputError(
                "mixed_materials",
                label=label,
                its_material=f"{type(concrete).__name__} f'c = {concrete.f_c}",
                material=f"{type(self.concrete).__name__} f'c = {self.concrete.f_c}",
            )
        if type(steel) is not type(self.steel_bar) or steel.get_properties() != self.steel_bar.get_properties():
            raise SummaryInputError(
                "mixed_materials",
                label=label,
                its_material=f"{type(steel).__name__} fy = {steel.f_y}, gamma_s = {steel.gamma_s}, epsilon_ud = {steel.epsilon_ud}",
                material=f"{type(self.steel_bar).__name__} fy = {self.steel_bar.f_y}, gamma_s = {self.steel_bar.gamma_s}, epsilon_ud = {self.steel_bar.epsilon_ud}",
            )
        reason = self._not_representable(key, section)
        if reason is None and any(force._M_x.magnitude != 0 for force in node.forces):
            reason = "an out-of-plane moment M_x, which the forces table has no column for"
        if reason is None:
            fresh = self._section(key, self._section_row(section))
            if fresh.settings != section.settings:
                reason = "settings other than the defaults of a new section"
        if reason is not None:
            raise SummaryInputError("node_not_representable", label=label, reason=reason)

    # -- hooks --------------------------------------------------------------

    def _section(self, key: Key, row: Mapping[str, Any]) -> Any:  # pragma: no cover - every subclass sets it
        """The section a validated row of the sections table describes."""
        raise NotImplementedError

    def _section_row(self, section: Any) -> Dict[str, Any]:  # pragma: no cover - every subclass sets it
        """The row of the sections table ``section`` is: the exact inverse of :meth:`_section`."""
        raise NotImplementedError

    def _validate_section_row(self, key: Key, row: Mapping[str, Any]) -> None:
        """Raise ``incomplete_group`` for a bar, a layer or a mesh given only in part."""

    def _not_representable(self, key: Key, section: Any) -> Optional[str]:
        """Why a section built by hand cannot be a row of the table, or ``None``."""
        if type(section) is not self._SECTION_TYPE:
            return f"it is a {type(section).__name__}, not a {self._SECTION_TYPE.__name__}"
        return None

    def _design(self, key: Key, node: Node) -> Node:
        """Design one section for its combinations: ``node.design()``."""
        node.design()
        return node

    def _has_reinforcement(self, section: Any) -> bool:  # pragma: no cover - every subclass sets it
        raise NotImplementedError

    def _axial_limit(self, section: Any) -> Optional[Quantity]:
        """The compression from which the section is no longer the element this summary checks, if any."""
        return None

    def validate_units(self, units_row: Iterable[Any]) -> None:
        """Raise ``wrong_unit`` for a unit no column of a summary table takes."""
        known = {unit for units in UNITS.values() for unit in units}
        for unit in units_row:
            if unit and unit not in known:
                raise SummaryInputError(
                    "wrong_unit",
                    column="?",
                    table="given",
                    kind="unit",
                    unit=repr(unit),
                    allowed=_listed(sorted(known - {""})),
                )

    def get_unit_variable(self, unit_str: str) -> Any:
        """The pint unit a unit-row string names; ``wrong_unit`` if none does."""
        self.validate_units([unit_str or "?"])
        return unit_of(unit_str)

    # -- state --------------------------------------------------------------

    @property
    def nodes(self) -> Tuple[Node, ...]:
        """One node per row of the sections table, in its order, sections without forces included."""
        return tuple(self._nodes)

    @property
    def labels(self) -> List[Any]:
        """The sections' labels in the order of :attr:`nodes`; ``(Level, Label)`` where any has a level."""
        if self._ALWAYS_LEVEL or any(level for level, _ in self._keys):
            return list(self._keys)
        return [label for _, label in self._keys]

    @property
    def input_warnings(self) -> Tuple[SummaryInputWarning, ...]:
        """What reading the tables had to warn about; see :class:`~mento.summary_tables.SummaryInputWarning`."""
        return tuple(self._input_warnings)

    @property
    def results(self) -> Tuple[SectionVerdict, ...]:
        """What the last ``check()`` found, one record per section; empty before the first."""
        return self._results

    @property
    def warnings(self) -> Dict[Key, Tuple[DesignWarning, ...]]:
        """The warnings of each section, by ``(Level, Label)``, as the last ``check()`` found them."""
        return {verdict.key: verdict.warnings for verdict in self._results}

    def _show_level(self) -> bool:
        return self._ALWAYS_LEVEL or any(level for level, _ in self._keys) or "Level" in self._written["sections"]

    def _section_columns(self) -> List[Any]:
        written = self._written["sections"]
        show_notes = "Notes" in written or any(self._section_notes)
        return [
            column
            for column in self._SPEC.sections
            if (column.name != "Level" or self._show_level()) and (column.name != "Notes" or show_notes)
        ]

    def _force_columns(self) -> List[Any]:
        written = self._written["forces"]
        show_notes = "Notes" in written or any(note for notes in self._force_notes for note in notes)
        return [
            column
            for column in self._SPEC.forces
            if (column.name != "Level" or self._show_level()) and (column.name != "Notes" or show_notes)
        ]

    @property
    def sections_table(self) -> DataFrame:
        """The sections as the file holds them: the unit row, then one row per section."""
        rows = []
        for key, node, note in zip(self._keys, self._nodes, self._section_notes):
            row = self._section_row(node.section)
            row.update({"Level": key[0], "Label": key[1], "Notes": note})
            rows.append(row)
        return write_table(rows, self._section_columns(), self._units["sections"])

    @property
    def forces_table(self) -> DataFrame:
        """The combinations as the file holds them: the unit row, then one row per combination."""
        units = self._units["forces"]
        rows = []
        for key, node, notes in zip(self._keys, self._nodes, self._force_notes):
            for force, note in zip(node.forces, notes + [""] * (len(node.forces) - len(notes))):
                values = {"Nx": force._N_x, "Vz": force._V_z, "My": force._M_y}
                rows.append({"Level": key[0], "Label": key[1], "Comb.": force.label or "", "Notes": note, **values})
        return write_table(rows, self._force_columns(), units)

    def tables(self) -> Tuple[DataFrame, DataFrame]:
        """``(sections, forces)``, as :attr:`sections_table` and :attr:`forces_table`."""
        return self.sections_table, self.forces_table

    def to_excel(self, target: Union[str, IO[bytes], Any]) -> None:
        """Write the sheets ``Sections`` and ``Forces`` to a path or a buffer (``io.BytesIO``).

        Sheet names and headers are always in English, whatever the language
        set with :func:`mento.set_language`, so the file reads back anywhere.
        """
        sections, forces = self.tables()
        write_workbook(target, sections, forces)

    def export_design(self, path: Union[str, IO[bytes], Any]) -> None:
        """Write the two tables, as :meth:`to_excel`, and say where."""
        self.to_excel(path)
        print(translate("✅ Sections and forces written to {path}", path=path))

    def import_design(self, path: Union[str, IO[bytes], Any]) -> None:
        """Read the two sheets of a file back into this summary, replacing its sections and forces."""
        sections, forces = read_workbook(path, SECTIONS_SHEET, FORCES_SHEET, self._SPEC)
        self._load(sections, forces)
        print(translate("✅ Sections and forces read from {path}", path=path))

    # -- design and check ---------------------------------------------------

    def design(self) -> DataFrame:
        """Design every section with forces, exactly as ``node.design()`` does, and check it.

        Sections without forces are left as given. The designed reinforcement
        replaces the given one, on both faces, so the tables written afterwards
        read back as the section designed. Returns :attr:`sections_table`.
        """
        self._designed_short: List[str] = []
        for i, (key, node) in enumerate(zip(self._keys, self._nodes)):
            if node.forces:
                self._nodes[i] = self._design(key, node)
        self.check()
        self._report_design()
        return self.sections_table

    def _report_design(self) -> None:
        print(translate("✅ Design completed for every section of the summary."))

    def check(self, capacity_check: bool = False) -> DataFrame:
        """One row per section: what it is, what governs each of its DCRs, its warnings and its verdict.

        ``capacity_check=True`` gives the capacities instead, computed on a
        copy of each section with no forces, and leaves :attr:`results` alone.
        """
        if capacity_check:
            return self._capacity_table()
        self._results = tuple(self._verdict(key, node) for key, node in zip(self._keys, self._nodes))
        return self._check_table(self._results)

    def _verdict(self, key: Key, node: Node) -> SectionVerdict:
        if not node.forces:
            return SectionVerdict(key, "no_forces", None, None, None, (), None)
        if not self._has_reinforcement(node.section):
            return SectionVerdict(key, "no_reinforcement", None, None, None, (), None)
        node.check()
        return self._check_record(key, node)

    def _check_record(self, key: Key, node: Node) -> SectionVerdict:  # pragma: no cover - every subclass sets it
        raise NotImplementedError

    def _sections_overview(self) -> DataFrame:  # pragma: no cover - every subclass sets it
        """The sections as the Word report lists them, its unit row first."""
        raise NotImplementedError

    def _check_table(self, records: Sequence[SectionVerdict]) -> DataFrame:  # pragma: no cover
        raise NotImplementedError

    def _capacity_table(self) -> DataFrame:  # pragma: no cover
        raise NotImplementedError

    @staticmethod
    def _combination_names(node: Node) -> List[str]:
        """The name of each combination of a node: its own, or ``#n``, its position, where it has none."""
        return [combination_label(force.label, position) for position, force in enumerate(node.forces, 1)]

    def _verdict_text(self, record: SectionVerdict) -> str:
        if record.passes is None:
            return translate(STATUS_TEXT[record.status])
        return PASS_MARK if record.passes else FAIL_MARK

    # -- by section ---------------------------------------------------------

    def _position(self, index: Index) -> int:
        """The 0-based position of a section: a 1-based ``int``, a label, or ``(Level, Label)``."""
        n = len(self._nodes)
        if isinstance(index, int) and not isinstance(index, bool):
            if 1 <= index <= n:
                return index - 1
            raise IndexError(f"Index {index} is out of range. Valid: 1 to {n}.")
        if isinstance(index, tuple):
            key = (label_of(index[0]), label_of(index[1]))
            if key in self._keys:
                return self._keys.index(key)
        else:
            label = label_of(index)
            matches = [i for i, key in enumerate(self._keys) if key[1] == label]
            if len(matches) == 1:
                return matches[0]
        raise SummaryInputError(
            "unknown_index", index=repr(index), labels=_listed([key_text(key) for key in self._keys])
        )

    def _node_with_forces(self, index: Index) -> Node:
        position = self._position(index)
        node = self._nodes[position]
        if not node.forces:
            raise SummaryInputError("no_forces_to_report", label=repr(key_text(self._keys[position])))
        return node


def frame_with_units(units: Mapping[str, str], rows: Sequence[Mapping[str, Any]]) -> DataFrame:
    """A results table: its unit row, then its rows."""
    return pd.concat([pd.DataFrame([dict(units)]), pd.DataFrame(list(rows), columns=list(units))], ignore_index=True)


# ---------------------------------------------------------------------------
# Beams and one-way slabs: flexure on two faces, and shear
# ---------------------------------------------------------------------------


class _FlexuralSummary(_TwoTableSummary):
    """The check, the capacities and the per-combination results of beams and one-way slab strips."""

    #: Whether the check table has an ``Av`` column (a slab carries no stirrups).
    _HAS_STIRRUPS = True

    def _rebar_labels(self, section: Any) -> Tuple[str, str, str]:  # pragma: no cover - every subclass sets it
        """The top bars, the bottom bars and the stirrups, as ``check()`` writes them."""
        raise NotImplementedError

    def _has_reinforcement(self, section: Any) -> bool:
        """Whether any bar is placed on either face."""
        return any(n > 0 for face in ("bot", "top") for n, _ in section._bar_groups(face))

    def _check_record(self, key: Key, node: Node) -> SectionVerdict:
        section: Any = node.section
        names = self._combination_names(node)
        flexure = section.flexure_checks
        shear = section.shear_checks
        top = governing(
            names, [(c.top.DCR, c.M_demand, c.N_demand) for c in flexure], all(c.top.admissible for c in flexure)
        )
        bottom = governing(
            names,
            [(c.bottom.DCR, c.M_demand, c.N_demand) for c in flexure],
            all(c.bottom.admissible for c in flexure),
        )
        shear_demand = governing(names, [(c.DCR, c.V_demand, c.N_demand) for c in shear])
        found = tuple(section.warnings)
        return SectionVerdict(
            key, "checked", top, bottom, shear_demand, found, verdict_passes((top, bottom, shear_demand), found)
        )

    def _demand_columns(self) -> Tuple[str, str, str]:
        cols = design_code(self.concrete).summary_columns
        return cols["moment_demand"], cols["shear_demand"], cols["axial_demand"]

    def _section_cells(self, key: Key, section: Any) -> Dict[str, Any]:
        """The columns that say what a section is: its level, label, size and reinforcement."""
        imperial = self.concrete.is_imperial
        top, bottom, transverse = self._rebar_labels(section)
        cells: Dict[str, Any] = {}
        if self._show_level():
            cells["Level"] = key[0]
        cells[self._ELEMENT_COLUMN] = key[1]
        cells["b×h"] = f"{section_dimension(section.width, imperial)}×{section_dimension(section.height, imperial)}"
        cells["As,top"] = top
        cells["As,bot"] = bottom
        if self._HAS_STIRRUPS:
            cells["Av"] = transverse
        return cells

    def _section_units(self) -> Dict[str, str]:
        units: Dict[str, str] = {}
        if self._show_level():
            units["Level"] = ""
        units[self._ELEMENT_COLUMN] = ""
        units["b×h"] = unit_label("length", self.concrete.is_imperial)
        units["As,top"] = units["As,bot"] = ""
        if self._HAS_STIRRUPS:
            units["Av"] = ""
        return units

    def _sections_overview(self) -> DataFrame:
        """The sections as the Word report lists them: size, cover and the reinforcement as a drawing writes it."""
        imperial = self.concrete.is_imperial
        cover = "length" if imperial else "bar"
        rows = []
        for key, node in zip(self._keys, self._nodes):
            section: Any = node.section
            top, bottom, transverse = self._rebar_labels(section)
            row: Dict[str, Any] = {"Level": key[0]} if self._show_level() else {}
            row["Label"] = key[1]
            row["b×h"] = f"{section_dimension(section.width, imperial)}×{section_dimension(section.height, imperial)}"
            row["cc"] = section_dimension(section.c_c, imperial, cover)
            row["As,top"], row["As,bot"] = top, bottom
            if self._HAS_STIRRUPS:
                row["Av"] = transverse
            rows.append(row)
        units: Dict[str, str] = {"Level": ""} if self._show_level() else {}
        units.update({"Label": "", "b×h": unit_label("length", imperial), "cc": unit_label(cover, imperial)})
        units.update({"As,top": "", "As,bot": ""})
        if self._HAS_STIRRUPS:
            units["Av"] = ""
        return frame_with_units(units, rows)

    def _check_table(self, records: Sequence[SectionVerdict]) -> DataFrame:
        imperial = self.concrete.is_imperial
        M, V, N = self._demand_columns()
        moment, force = unit_label("moment", imperial), unit_label("force", imperial)

        def demand(g: Optional[GoverningDemand], kind: str) -> Tuple[str, float, float]:
            if g is None:
                return "-", math.nan, math.nan
            value = math.nan if g.demand is None else round(shown(g.demand, kind, imperial), 1)
            return ", ".join(g.combinations) or "-", value, round(g.DCR, 3)

        rows = []
        for record, node in zip(records, self._nodes):
            row = self._section_cells(record.key, node.section)
            row["Comb.,top"], row[f"{M},top"], row["DCRb,top"] = demand(record.top, "moment")
            row["Comb.,bot"], row[f"{M},bot"], row["DCRb,bot"] = demand(record.bottom, "moment")
            row["Comb.,v"], row[V], row["DCRv"] = demand(record.shear, "force")
            axial = record.shear.axial if record.shear is not None else None
            row[N] = math.nan if axial is None else round(shown(axial, "force", imperial), 1)
            row["Warnings"] = warning_tags(record.warnings)
            row[VERDICT_COLUMN] = self._verdict_text(record)
            rows.append(row)
        units = self._section_units()
        units.update(
            {
                "Comb.,top": "",
                f"{M},top": moment,
                "DCRb,top": "",
                "Comb.,bot": "",
                f"{M},bot": moment,
                "DCRb,bot": "",
                "Comb.,v": "",
                V: force,
                N: force,
                "DCRv": "",
                "Warnings": "",
                VERDICT_COLUMN: "",
            }
        )
        return translated(frame_with_units(units, rows))

    def _capacity_table(self) -> DataFrame:
        imperial = self.concrete.is_imperial
        code = design_code(self.concrete)
        cols = code.summary_columns
        digits = 2 if imperial else 1
        units = self._section_units()
        units.update({"As,top,real": unit_label("area", imperial), "As,bot,real": unit_label("area", imperial)})
        if self._HAS_STIRRUPS:
            units["Av,real"] = unit_label("per_length", imperial)
        units[cols["moment_capacity_top"]] = unit_label("moment", imperial)
        units[cols["moment_capacity_bot"]] = unit_label("moment", imperial)
        units[cols["shear_capacity"]] = unit_label("force", imperial)
        rows = []
        for key, live in zip(self._keys, self._nodes):
            # On a copy with no forces: the section's own checks and warnings stay.
            node = copy.deepcopy(live)
            node.clear_forces()
            node.add_forces(Forces())
            node.check_flexure()
            shear_results = node.check_shear()
            section: Any = node.section
            row = self._section_cells(key, section)
            row["As,top,real"] = shown(section._A_s_top, "area", imperial, digits)
            row["As,bot,real"] = shown(section._A_s_bot, "area", imperial, digits)
            if self._HAS_STIRRUPS:
                row["Av,real"] = round(shear_results["Av"][1], digits)
            row.update(code.requires("capacity_columns")(section))
            row[cols["shear_capacity"]] = shear_results[cols["shear_capacity"]][1]
            rows.append(row)
        return translated(frame_with_units(units, rows))

    # -- per combination ----------------------------------------------------

    def _process_beam_for_check(self, node: Node, check_type: str, capacity_check: bool) -> DataFrame:
        """The flexure or shear table of one node; ``capacity_check`` on a copy with no forces."""
        if check_type not in ("shear", "flexure"):
            raise ValueError("check_type must be either 'shear' or 'flexure'")
        if capacity_check:
            node = copy.deepcopy(node)
            node.clear_forces()
            node.add_forces(Forces())
        if check_type == "shear":
            return node.check_shear().iloc[1:].reset_index(drop=True)
        results = node.check_flexure().iloc[1:].reset_index(drop=True)
        if capacity_check:
            for column, value in design_code(self.concrete).requires("capacity_columns")(node.section).items():
                results[column] = value
        return results

    def _per_combination(self, check_type: str, index: Optional[Index], capacity_check: bool) -> DataFrame:
        nodes = [self._node_with_forces(index)] if index is not None else [n for n in self._nodes if n.forces]
        frames = [self._process_beam_for_check(node, check_type, capacity_check) for node in nodes]
        section: Any = (nodes or self._nodes)[0].section
        units = section._get_units_row_shear() if check_type == "shear" else section._get_units_row_flexure()
        return translated(pd.concat([units, *frames], ignore_index=True))

    def flexure_results(self, index: Optional[Index] = None, capacity_check: bool = False) -> DataFrame:
        """The flexure table of every combination, of one section or of all.

        ``index`` is the section's position in the sections table (1-based)
        or its label. ``capacity_check=True`` checks a copy of each section
        with no forces and adds the capacities, in the code's own names.
        """
        return self._per_combination("flexure", index, capacity_check)

    def shear_results(self, index: Optional[Index] = None, capacity_check: bool = False) -> DataFrame:
        """The shear table of every combination, of one section or of all; see :meth:`flexure_results`."""
        return self._per_combination("shear", index, capacity_check)

    def results_detailed_doc(self, index: Index = 1) -> None:
        """Write a Word report: the detailed results of one section, then the tables of all.

        ``index`` is the section's position (1-based) in the sections table or
        its label. Saved as ``{Beam|Slab}_Summary_{design_code}.docx`` in the
        current directory.
        """
        from mento.reports.summaries import beam_summary_doc

        beam_summary_doc(self, index)
