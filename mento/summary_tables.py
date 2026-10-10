"""The two tables a summary reads and writes: one of sections, one of forces.

A summary of many elements separates what a section *is* from what it
*carries*. The sections table has one row per section -- its geometry, its
cover and the reinforcement of both faces -- and the forces table one row per
load combination, naming the section it acts on by its ``Label`` (and
``Level``). Each table is a ``DataFrame`` whose first row holds the unit of
every column, as an Excel sheet with its unit row under the headers.

This module reads and writes those tables and nothing else: it knows the
columns, their units and how a cell is validated, but not which element a row
becomes. :mod:`mento.summary_base` builds the elements.

Errors and warnings carry a stable ``code``, as
:class:`~mento.design_warnings.DesignWarning` does. ``str(error)`` is the
English text (the API's errors are in English, see the language guide);
``error.message`` is the same text in the language set with
:func:`mento.set_language`.
"""

from __future__ import annotations

import difflib
import math
import numbers
from dataclasses import dataclass
from typing import IO, Any, Dict, List, Literal, Mapping, Optional, Sequence, Tuple, Union, cast

import pandas as pd
from pandas import DataFrame

from mento.i18n import translate
from mento.units import Quantity, cm, ft, inch, kip, kN, m, mm

#: The kinds of value a column holds, and so the units its unit row may give.
Kind = Literal["text", "count", "length", "force", "moment"]

#: Every unit a unit row may give, by kind: the ones the single table of the
#: summaries read, so a file that worked keeps working. A force is in kN or
#: kip and a moment in kNm or kip·ft ("kipft" too, as ShearWallSummary read it).
UNITS: Dict[str, Dict[str, Any]] = {
    "length": {"m": m, "cm": cm, "mm": mm, "in": inch, "inch": inch, "ft": ft},
    "force": {"kN": kN, "kip": kip},
    "moment": {"kNm": kN * m, "kip·ft": kip * ft, "kipft": kip * ft},
    "count": {"": None},
    "text": {"": None},
}


def unit_of(unit: str) -> Any:
    """The pint unit a unit-row string names, whatever its kind; ``KeyError`` if none does."""
    for units in UNITS.values():
        if unit in units and units[unit] is not None:
            return units[unit]
    raise KeyError(unit)


# ---------------------------------------------------------------------------
# Errors and warnings
# ---------------------------------------------------------------------------

#: The English text of each code. It is also the key of the Spanish catalog in
#: :mod:`mento.i18n`; the placeholders are filled after translation.
TEMPLATES: Dict[str, str] = {
    "single_table": (
        "{element} reads two tables, the sections and the forces, and the table given is the single table of "
        'mento 1.4.0 (it has {columns}). Convert it with `sections, forces = mento.split_single_table(table, "{kind}")` '
        "and pass both; each of its rows becomes a section of its own and that section's forces, which is what "
        "1.4.0 computed."
    ),
    "single_table_slab": (
        "{element} reads two tables, the sections and the forces, and the table given has both in one (it has "
        "{columns}). Give one row per slab in the sections table, with the layers of both faces, and one row per "
        "combination in the forces table."
    ),
    "missing_forces": (
        "{element} reads two tables; the forces table is missing. A section with no combination is a row of "
        "sections and no row of forces."
    ),
    "swapped_tables": (
        "The sections table has the force columns ({columns}) and the forces table the geometry: pass sections "
        "first, then forces."
    ),
    "missing_sheet": "The file {path} has no sheet {sheet}: a summary file holds two sheets, {sections} and {forces}.",
    "missing_columns": "The {table} table has no column {columns}. Its columns are {expected}.",
    "unknown_columns": (
        "The {table} table has columns {element} does not read: {columns}{hint}. Its columns are {expected}; "
        "free text goes in Notes."
    ),
    "wrong_element": "The {table} table has the columns of a {other} ({columns}); {element} reads {expected}.",
    "stirrups_in_slab": "A one-way slab strip is detailed without stirrups, so its sections table has no {columns}.",
    "wrong_unit": "Column {column} of the {table} table is a {kind}, and its unit row says {unit}. Use one of {allowed}.",
    "missing_label": "Row {row} ({nth} data row) of the {table} table has no Label.",
    "duplicate_combination": (
        "The forces table gives combination {combination} of {label} more than once (rows {rows}): a section "
        "takes each combination once. Give each row its own name (an envelope's Max and Min, each station of a "
        "member), or make them two sections."
    ),
    "one_leg": (
        "legs of {label} is 1: the perimeter stirrup is closed and has two legs. Give 0 for no stirrups, or 2 or "
        "more (an odd count from 3 adds crossties or open legs to the closed stirrups)."
    ),
    "duplicate_section": (
        "The sections table gives {label} more than once (rows {rows}). If they are different sections (e.g. a "
        "support and a midspan with different bars), give each its own label; if one section takes several "
        "combinations, give it one row here and its combinations in the forces table."
    ),
    "unknown_section": "The forces table names {label} (rows {rows}), which is not in the sections table.",
    "missing_value": "{column} of {label} is empty in the {table} table.",
    "not_a_number": "{column} of {label} is {value} in the {table} table, not a number.",
    "negative_value": "{column} of {label} is {value}; it cannot be negative.",
    "non_positive_dimension": "{column} of {label} is {value}; it has to be greater than zero.",
    "not_a_whole_number": "{column} of {label} is {value}; a number of bars or stirrups is a whole number.",
    "incomplete_group": "{label}: {given} is given without {missing}.",
    "mixed_materials": "Node {label} is of {its_material}; the summary is of {material}.",
    "node_not_representable": "Node {label} cannot be written as a table row: {reason}.",
    "no_forces_to_report": "{label} has no forces in the forces table, so it has no results to report.",
    "unknown_index": "The summary has no section {index}; its sections are {labels}.",
    # Warnings
    "section_without_forces": "{labels}: no forces in the forces table; kept as given and shown as not checked.",
    "no_axial_column": (
        "The forces table has no Nx column: N is taken as 0. A tension omitted makes the shear check unconservative."
    ),
    "axial_load_beyond_beam": (
        "{pairs}: Nx >= 0.10 f'c Ag in compression. ACI 318-19 / CIRSOC 201-25 §9.5.2.2 compute the moment "
        "strength with the axial load (§22.4, P-M interaction); closed stirrups or spirals follow Table 22.4.2.1. "
        "R/C9.5.2.2 does not require Chapter 10. mento checks bending alone (§22.3); this case needs separate verification."
    ),
    "shear_reinforcement_required": (
        "{labels}: Vu > φVc with the bars designed; more longitudinal steel, more thickness, a higher f'c, or shear "
        "reinforcement detailed as a beam (ACI 318-19 §7.6.3). check() gives them as failing."
    ),
    "labels_renamed": "{pairs}: repeated labels renamed; each row is a section of its own, as in 1.4.0.",
    "second_layer_same_face": (
        "{labels}: 1.4.0 read n3/n4 as a second layer of the face in tension, not the opposite face; check them "
        "against your drawings."
    ),
    "dead_cells": "{cells}: cells 1.4.0 ignored (a diameter with no bars, a stirrup with ns = 0) were dropped.",
}

#: Codes that are warnings rather than errors.
WARNING_CODES = frozenset(
    {
        "section_without_forces",
        "no_axial_column",
        "axial_load_beyond_beam",
        "shear_reinforcement_required",
        "labels_renamed",
        "second_layer_same_face",
        "dead_cells",
    }
)


class _Coded:
    """What a summary error and a summary warning share: a stable code, its values and its text."""

    code: str
    values: Dict[str, str]
    #: The template the text is written from: the code's own, or a variant of it.
    template: str

    def _set(self, code: str, template: Optional[str], values: Mapping[str, Any]) -> None:
        self.code = code
        self.template = template or code
        self.values = {name: str(value) for name, value in values.items()}

    def _template(self) -> str:
        return TEMPLATES[self.template]

    @property
    def message(self) -> str:
        """The text in the language set with :func:`mento.set_language`."""
        return translate(self._template(), **self.values)

    def _english(self) -> str:
        return self._template().format(**self.values)


class SummaryInputError(_Coded, ValueError):
    """A summary table, file or node that cannot be read, with a stable ``code``.

    ``str(error)`` is in English; ``error.message`` follows
    :func:`mento.set_language`; ``error.values`` holds the texts it quotes. A
    ``ValueError``, so code that caught the summary's errors before still does.
    """

    def __init__(self, code: str, *, template: Optional[str] = None, **values: Any) -> None:
        self._set(code, template, values)
        ValueError.__init__(self, self._english())


class SummaryInputWarning(_Coded, UserWarning):
    """Something a summary read and kept, but that its reader should know; see :class:`SummaryInputError`."""

    def __init__(self, code: str, *, template: Optional[str] = None, **values: Any) -> None:
        self._set(code, template, values)
        UserWarning.__init__(self, self._english())


def _listed(items: Sequence[Any]) -> str:
    """Items quoted and joined for a message: ``'V1', 'V2'``."""
    return ", ".join(repr(str(item)) for item in items)


def _ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


# ---------------------------------------------------------------------------
# Columns
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TableColumn:
    """One column of a summary table.

    ``required`` columns must be present; an optional one that is absent is
    zero (or empty) on every row. ``metric`` and ``imperial`` are the units the
    writer gives the column by default. ``signed`` numbers may be negative
    (forces); ``dimension`` ones must be greater than zero and may not be left
    empty (geometry).
    """

    name: str
    kind: Kind
    required: bool = False
    metric: str = ""
    imperial: str = ""
    signed: bool = False
    dimension: bool = False

    def default_unit(self, imperial: bool) -> str:
        return self.imperial if imperial else self.metric

    def allowed_units(self) -> List[str]:
        return list(UNITS[self.kind])


def text(name: str, required: bool = False) -> TableColumn:
    return TableColumn(name, "text", required)


def count(name: str) -> TableColumn:
    return TableColumn(name, "count")


def length(name: str, metric: str, imperial: str, *, dimension: bool = False) -> TableColumn:
    return TableColumn(name, "length", dimension, metric, imperial, dimension=dimension)


@dataclass(frozen=True)
class TableSpec:
    """The columns of the two tables of one kind of summary.

    ``kind`` names it for :func:`split_single_table` and the messages
    (``"beam"``, ``"slab"``, ``"wall"``); ``element`` is the summary class
    name the messages quote.
    """

    kind: str
    element: str
    sections: Tuple[TableColumn, ...]
    forces: Tuple[TableColumn, ...]

    def columns(self, table: str) -> Tuple[TableColumn, ...]:
        return self.sections if table == "sections" else self.forces

    def geometry(self) -> Tuple[str, ...]:
        return tuple(column.name for column in self.sections if column.dimension)


#: The stirrup columns of a beam's sections table.
_STIRRUP_COLUMNS = ("legs", "ns", "dbs", "sl")

#: Columns of the single table of 1.4.0 that the two tables name otherwise.
_RENAMED = {"ns": "legs: the number of stirrup legs, 2 per closed stirrup"}

#: The columns a forces table names a section and a combination by, and its force columns.
FORCE_NAMES = ("Comb.", "Nx", "Vz", "My")


def forces_columns(*, moment_required: bool = True) -> Tuple[TableColumn, ...]:
    """``Level, Label, Comb., Nx, Vz, My, Notes``."""
    return (
        text("Level"),
        text("Label", required=True),
        text("Comb.", required=True),
        TableColumn("Nx", "force", False, "kN", "kip", signed=True),
        TableColumn("Vz", "force", True, "kN", "kip", signed=True),
        TableColumn("My", "moment", moment_required, "kNm", "kip·ft", signed=True),
        text("Notes"),
    )


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------


def _is_blank(value: Any) -> bool:
    """An empty cell: None, NaN, pandas' NA, or text that is only spaces."""
    if isinstance(value, str):
        return value.strip() == ""
    return value is None or (pd.api.types.is_scalar(value) and bool(pd.isna(value)))


def label_of(value: Any) -> str:
    """A label, a combination or a level as text, whatever the cell held.

    Empty for a blank cell; ``"101"`` for the ``101.0`` ``read_excel`` gives
    a whole number; the text, stripped, otherwise -- so ``'V4 '`` and
    ``'V4'`` are one section, and so are ``4`` and ``'4'``.
    """
    if _is_blank(value):
        return ""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, numbers.Integral):
        return str(int(value))
    if isinstance(value, numbers.Real) and float(value).is_integer():
        return str(int(float(value)))
    return str(value).strip()


def key_text(key: Tuple[str, str]) -> str:
    """A section's ``(Level, Label)`` as a message names it: ``'V1'``, or ``'Level 1 / M1'``."""
    level, label = key
    return f"{level} / {label}" if level else label


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


@dataclass
class ReadTable:
    """A table as read: its rows (one dict per data row), the unit of each column and where each row was.

    ``rows`` hold quantities for the length, force and moment columns, ints for
    the counts and text for the rest; a column the table did not give is not
    in its rows. ``positions`` are the sheet rows (the header is row 1, the
    unit row row 2) and ``nth`` the data rows, 1-based.
    """

    rows: List[Dict[str, Any]]
    units: Dict[str, str]
    given: Tuple[str, ...]
    positions: List[int]


def _signature(spec: TableSpec, table: str) -> set[str]:
    return {column.name for column in spec.columns(table)}


def _check_columns(df: DataFrame, spec: TableSpec, table: str, others: Sequence[TableSpec]) -> None:
    given = [str(column) for column in df.columns]
    own = _signature(spec, table)
    unknown = [column for column in given if column not in own]
    stirrups = [column for column in unknown if column in _STIRRUP_COLUMNS]
    if unknown:
        # Two or more columns of another element's table (stirrups aside,
        # which a slab table may carry by mistake on its own) mean the whole
        # table is that element's.
        for other in others:
            theirs = [c for c in unknown if c in _signature(other, table) and c not in _STIRRUP_COLUMNS]
            if len(theirs) >= 2:
                raise SummaryInputError(
                    "wrong_element",
                    table=table,
                    other=other.kind,
                    columns=_listed(theirs),
                    element=spec.element,
                    expected=_listed([column.name for column in spec.columns(table)]),
                )
        if spec.kind == "slab" and table == "sections" and stirrups:
            raise SummaryInputError("stirrups_in_slab", columns=_listed(stirrups))
        hints = []
        for column in unknown:
            close = difflib.get_close_matches(column, sorted(own), n=1)
            if column in _RENAMED and _RENAMED[column].split(":")[0] in own:
                hints.append(f"{column!r} -> {_RENAMED[column]}")
            elif close:
                hints.append(f"{column!r} -> {close[0]!r}")
        raise SummaryInputError(
            "unknown_columns",
            table=table,
            element=spec.element,
            columns=_listed(unknown),
            hint=f" (did you mean {', '.join(hints)}?)" if hints else "",
            expected=_listed([column.name for column in spec.columns(table)]),
        )
    missing = [column.name for column in spec.columns(table) if column.required and column.name not in given]
    if missing:
        raise SummaryInputError(
            "missing_columns",
            table=table,
            columns=_listed(missing),
            expected=_listed([column.name for column in spec.columns(table)]),
        )


def _number(value: Any) -> Optional[float]:
    """A cell as a float, None when blank; ``ValueError`` when it holds text that is no number."""
    if _is_blank(value):
        return None
    if isinstance(value, bool):
        raise ValueError(value)
    if isinstance(value, numbers.Real):
        return float(value)
    return float(str(value).strip().replace(",", "."))


def read_table(df: DataFrame, spec: TableSpec, table: str, others: Sequence[TableSpec] = ()) -> ReadTable:
    """Read and validate one table: the unit row first, then one row per section or combination.

    Columns are read by name, in any order. A row with every cell blank is
    skipped wherever it is. Raises :class:`SummaryInputError` for anything that
    cannot be read; see the module docstring.
    """
    _check_columns(df, spec, table, others)
    columns = {column.name: column for column in spec.columns(table)}
    given = tuple(str(column) for column in df.columns)
    if len(df) == 0:
        return ReadTable([], {}, given, [])
    unit_row = df.iloc[0]
    units: Dict[str, str] = {}
    for name in given:
        column = columns[name]
        raw = unit_row[name]
        unit = "" if _is_blank(raw) else str(raw).strip()
        allowed = column.allowed_units()
        if unit not in allowed:
            raise SummaryInputError(
                "wrong_unit",
                column=name,
                table=table,
                kind=column.kind,
                unit=repr(unit),
                allowed=_listed(allowed),
            )
        units[name] = unit

    rows: List[Dict[str, Any]] = []
    positions: List[int] = []
    for position in range(1, len(df)):
        raw_row = df.iloc[position]
        if all(_is_blank(raw_row[name]) for name in given):
            continue
        sheet_row = position + 2
        row: Dict[str, Any] = {}
        label = label_of(raw_row["Label"]) if "Label" in given else ""
        if "Label" in given and not label:
            raise SummaryInputError("missing_label", row=sheet_row, nth=_ordinal(position), table=table)
        named = repr(label)
        for name in given:
            column = columns[name]
            value = raw_row[name]
            if column.kind == "text":
                row[name] = label_of(value) if name != "Notes" else ("" if _is_blank(value) else str(value))
                continue
            try:
                number = _number(value)
            except ValueError:
                raise SummaryInputError("not_a_number", column=name, label=named, value=repr(value), table=table)
            if number is None:
                if column.dimension:
                    raise SummaryInputError("missing_value", column=name, label=named, table=table)
                number = 0.0
            if column.dimension and number <= 0:
                raise SummaryInputError("non_positive_dimension", column=name, label=named, value=_shown(number))
            if not column.signed and number < 0:
                raise SummaryInputError("negative_value", column=name, label=named, value=_shown(number))
            if column.kind == "count":
                if not float(number).is_integer():
                    raise SummaryInputError("not_a_whole_number", column=name, label=named, value=_shown(number))
                row[name] = int(number)
            else:
                row[name] = number * unit_of(units[name])
        rows.append(row)
        positions.append(sheet_row)
    return ReadTable(rows, units, given, positions)


def _shown(number: float) -> str:
    return str(int(number)) if float(number).is_integer() else f"{number:g}"


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------


def _significant(value: float) -> Union[int, float]:
    """A number to 12 significant figures, whole where it is whole: what the file holds."""
    if value == 0 or not math.isfinite(value):
        return 0 if value == 0 else value
    rounded = float(f"{value:.12g}")
    return int(rounded) if rounded.is_integer() else rounded


def write_table(
    rows: Sequence[Mapping[str, Any]], columns: Sequence[TableColumn], units: Mapping[str, str]
) -> DataFrame:
    """A table as a file holds it: the unit row, then each row with its numbers in the unit of their column.

    ``rows`` hold quantities, counts and text by column name; a quantity is
    converted to the unit its column gives in ``units``.
    """
    names = [column.name for column in columns]
    unit_row = {name: units.get(name, "") for name in names}
    out: List[Dict[str, Any]] = [unit_row]
    for row in rows:
        written: Dict[str, Any] = {}
        for column in columns:
            value = row.get(column.name, "" if column.kind == "text" else 0)
            if isinstance(value, Quantity):
                value = _significant(float(value.to(unit_of(units[column.name])).magnitude))
            elif column.kind == "count":
                value = int(round(float(value)))
            written[column.name] = value
        out.append(written)
    return DataFrame(out, columns=names)


# ---------------------------------------------------------------------------
# Workbooks
# ---------------------------------------------------------------------------

SECTIONS_SHEET = "Sections"
FORCES_SHEET = "Forces"


def looks_like_single_table(df: DataFrame, spec: TableSpec) -> bool:
    """Whether a table holds both what a section is and what it carries: the single table of mento 1.4.0."""
    given = {str(column) for column in df.columns}
    return bool(given & set(FORCE_NAMES)) and bool(given & set(spec.geometry()))


def looks_swapped(sections: DataFrame, forces: Optional[DataFrame], spec: TableSpec) -> bool:
    """Whether the forces were passed where the sections go, and the other way round."""
    given = {str(column) for column in sections.columns}
    if not given & set(FORCE_NAMES) or given & set(spec.geometry()):
        return False
    return forces is not None and bool({str(column) for column in forces.columns} & set(spec.geometry()))


def read_workbook(
    source: Union[str, IO[bytes], Any], sections_sheet: str, forces_sheet: str, spec: TableSpec
) -> Tuple[DataFrame, DataFrame]:
    """The two sheets of a summary file, every cell as given (``dtype=object``)."""
    sheets: Dict[str, DataFrame] = pd.read_excel(source, sheet_name=None, dtype=object)
    for sheet in (sections_sheet, forces_sheet):
        if sheet not in sheets:
            if len(sheets) == 1 and looks_like_single_table(next(iter(sheets.values())), spec):
                only = next(iter(sheets.values()))
                if spec.kind in ("beam", "wall"):
                    # The file of mento 1.5.0, deprecated: read as split_single_table converts it.
                    import warnings as _warnings

                    _warnings.warn(
                        f"{spec.element} reading a single-table file is deprecated and will be removed in mento "
                        f"2.0: write it again with to_excel(), which keeps the sheets {sections_sheet!r} and "
                        f"{forces_sheet!r}.",
                        DeprecationWarning,
                        stacklevel=3,
                    )
                    return split_single_table(only, cast(Literal["beam", "wall"], spec.kind))
                found = [str(c) for c in only.columns if str(c) in FORCE_NAMES]
                raise single_table_error(spec, found)
            raise SummaryInputError(
                "missing_sheet",
                path=str(source) if isinstance(source, str) else "given",
                sheet=repr(sheet),
                sections=repr(sections_sheet),
                forces=repr(forces_sheet),
            )
    return sheets[sections_sheet], sheets[forces_sheet]


def write_workbook(target: Union[str, IO[bytes], Any], sections: DataFrame, forces: DataFrame) -> None:
    """Write the two tables as the sheets ``Sections`` and ``Forces``, headers in English."""
    with pd.ExcelWriter(cast(Any, target), engine="openpyxl") as writer:
        sections.to_excel(writer, sheet_name=SECTIONS_SHEET, index=False)
        forces.to_excel(writer, sheet_name=FORCES_SHEET, index=False)


def single_table_error(spec: TableSpec, columns: Sequence[str]) -> SummaryInputError:
    """The error for a table that mixes sections and forces, with the way out for its kind of summary."""
    template = "single_table_slab" if spec.kind == "slab" else "single_table"
    return SummaryInputError(
        "single_table", template=template, element=spec.element, columns=_listed(columns), kind=spec.kind
    )


# ---------------------------------------------------------------------------
# From the single table of mento 1.4.0
# ---------------------------------------------------------------------------

#: The columns of the single table of mento 1.4.0, by element.
_V140_BEAM = ("Label", "Comb.", "b", "h", "cc", "Nx", "Vz", "My", "ns", "dbs", "sl") + tuple(
    f"{p}{i}" for i in range(1, 5) for p in ("n", "db")
)
_V140_WALL = ("Level", "Label", "Comb.", "t", "lw", "hw", "cc", "Nx", "Vz", "My", "dbh", "sh", "dbv", "sv")


def _cell(row: Mapping[str, Any], name: str) -> Any:
    value = row.get(name, 0)
    return 0 if _is_blank(value) else value


def _num(row: Mapping[str, Any], name: str) -> float:
    number = _number(_cell(row, name))
    return 0.0 if number is None else number


def _fresh_label(label: str, taken: set[str]) -> str:
    n = 2
    while f"{label}-{n}" in taken:
        n += 1
    return f"{label}-{n}"


def split_single_table(table: DataFrame, element: Literal["beam", "wall"]) -> Tuple[DataFrame, DataFrame]:
    """Convert a table of mento 1.4.0, one row per combination, into the sections and forces tables.

    ``element`` is ``"beam"`` (:class:`~mento.beam_summary.BeamSummary`) or
    ``"wall"`` (:class:`~mento.shear_wall_summary.ShearWallSummary`).

    A beam row becomes a section of its own and that section's forces, which
    is what 1.4.0 computed: the DCRs of 1.4.0 come back. A label repeated
    becomes ``V1-2``, ``V1-3``...; a row with none ``row-<n>``. The bars of a
    row go on the face its ``My`` puts in tension (the bottom for ``My >= 0``)
    and the other face gets the 2Ø8 (2 #3) 1.4.0 placed without showing it,
    now written. A wall keeps one section per ``(Level, Label)``, with the
    geometry and mesh of its first row, and every row as a combination.

    The warnings ``labels_renamed``, ``second_layer_same_face`` and
    ``dead_cells`` (:class:`SummaryInputWarning`) say what the conversion had to
    decide.
    """
    import warnings as _warnings

    if element not in ("beam", "wall"):
        raise ValueError(f"element is 'beam' or 'wall', not {element!r}.")
    # A beam table may count its stirrups by legs (legs, or n_legs) instead of ns.
    expected = _V140_BEAM + ("legs", "n_legs") if element == "beam" else _V140_WALL
    given = [str(column) for column in table.columns]
    unknown = [column for column in given if column not in expected]
    if unknown:
        raise SummaryInputError(
            "unknown_columns",
            table="1.4.0",
            element="split_single_table",
            columns=_listed(unknown),
            hint="",
            expected=_listed(expected),
        )
    units = {name: ("" if _is_blank(table.iloc[0][name]) else str(table.iloc[0][name]).strip()) for name in given}
    data = [
        {name: table.iloc[i][name] for name in given}
        for i in range(1, len(table))
        if not all(_is_blank(table.iloc[i][name]) for name in given)
    ]
    if element == "wall":
        return _split_walls(data, units)

    imperial = any(units.get(name) in ("in", "inch", "ft", "kip", "kip·ft", "kipft") for name in given)
    filler_d = 3 / 8 if imperial else 8.0
    filler_unit = units.get("db1") or ("in" if imperial else "mm")
    if filler_unit != ("in" if imperial else "mm"):
        filler_d = float((filler_d * (inch if imperial else mm)).to(unit_of(filler_unit)).magnitude)

    sections: List[Dict[str, Any]] = []
    forces: List[Dict[str, Any]] = []
    taken = {label_of(row.get("Label")) for row in data} - {""}
    seen: set[str] = set()
    renamed: List[str] = []
    second_layer: List[str] = []
    dead: List[str] = []
    for n, row in enumerate(data, 1):
        label = label_of(row.get("Label"))
        if not label:
            label = f"row-{n}"
            while label in taken:
                label = f"{label}-x"
            renamed.append(f"row {n} -> {label!r}")
        elif label in seen:
            new = _fresh_label(label, taken)
            renamed.append(f"{label!r} -> {new!r}")
            label = new
        taken.add(label)
        seen.add(label)
        section: Dict[str, Any] = {"Label": label, "b": row.get("b"), "h": row.get("h"), "cc": row.get("cc")}
        dbs, sl = _num(row, "dbs"), _num(row, "sl")
        # ns counted closed stirrups; the sections table counts their legs.
        counts = [_num(row, name) for name in ("legs", "n_legs") if not _is_blank(row.get(name))]
        legs = int(counts[0]) if counts else 2 * int(_num(row, "ns"))
        if legs == 0 and (dbs or sl):
            dead.append(f"{label}: dbs/sl")
            dbs = sl = 0
        section.update({"legs": legs, "dbs": dbs, "sl": sl})
        groups = []
        for i in range(1, 5):
            n_i, d_i = _num(row, f"n{i}"), _num(row, f"db{i}")
            if n_i == 0 and d_i:
                dead.append(f"{label}: db{i}")
                d_i = 0
            groups.append((int(n_i), d_i))
        if groups[2][0] or groups[3][0]:
            second_layer.append(label)
        tension = "bot" if _num(row, "My") >= 0 else "top"
        filler = [(2, filler_d), (0, 0), (0, 0), (0, 0)]
        faces = {tension: groups if groups[0][0] else filler, ("top" if tension == "bot" else "bot"): filler}
        for face, face_groups in faces.items():
            for i, (n_i, d_i) in enumerate(face_groups, 1):
                section[f"n{i}_{face}"] = n_i
                section[f"db{i}_{face}"] = d_i
        sections.append(section)
        forces.append(
            {
                "Label": label,
                "Comb.": row.get("Comb.", ""),
                "Nx": row.get("Nx", 0),
                "Vz": row.get("Vz"),
                "My": row.get("My"),
            }
        )
    if renamed:
        _warnings.warn(SummaryInputWarning("labels_renamed", pairs=", ".join(renamed)), stacklevel=2)
    if second_layer:
        _warnings.warn(SummaryInputWarning("second_layer_same_face", labels=_listed(second_layer)), stacklevel=2)
    if dead:
        _warnings.warn(SummaryInputWarning("dead_cells", cells=", ".join(dead)), stacklevel=2)

    bar_unit = units.get("db1") or ("in" if imperial else "mm")
    section_units = {
        "Label": "",
        "b": units.get("b", ""),
        "h": units.get("h", ""),
        "cc": units.get("cc", ""),
        "legs": "",
        "dbs": units.get("dbs") or bar_unit,
        "sl": units.get("sl") or ("in" if imperial else "cm"),
    }
    for face in ("top", "bot"):
        for i in range(1, 5):
            section_units[f"n{i}_{face}"] = ""
            section_units[f"db{i}_{face}"] = units.get(f"db{i}") or bar_unit
    force_units = {
        "Label": "",
        "Comb.": "",
        "Nx": units.get("Nx", "kN"),
        "Vz": units.get("Vz", ""),
        "My": units.get("My", ""),
    }
    return (
        DataFrame([section_units] + sections, columns=list(section_units)),
        DataFrame([force_units] + forces, columns=list(force_units)),
    )


def _split_walls(data: List[Dict[str, Any]], units: Dict[str, str]) -> Tuple[DataFrame, DataFrame]:
    """Walls: one section per ``(Level, Label)``, the geometry and mesh of its first row; every row a combination."""
    import warnings as _warnings

    sections: Dict[Tuple[str, str], Dict[str, Any]] = {}
    forces: List[Dict[str, Any]] = []
    renamed: List[str] = []
    for n, row in enumerate(data, 1):
        level, label = label_of(row.get("Level")), label_of(row.get("Label"))
        if not label:
            label = f"row-{n}"
            renamed.append(f"row {n} -> {label!r}")
        key = (level, label)
        if key in sections:
            for name in ("t", "lw", "hw", "cc"):
                if _num(row, name) != _num(sections[key], name):
                    raise ValueError(
                        f"Wall {key_text(key)!r}: its rows give different values of {name!r}; a wall is one "
                        "section, so give it one geometry."
                    )
            mesh = {name: _num(row, name) for name in ("dbh", "sh", "dbv", "sv")}
            if any(mesh.values()):
                previous = {name: _num(sections[key], name) for name in mesh}
                if any(previous.values()) and mesh != previous:
                    raise ValueError(f"Wall {key_text(key)!r}: its rows give different meshes.")
                sections[key].update(mesh)
        else:
            sections[key] = {
                "Level": level,
                "Label": label,
                **{name: row.get(name) for name in ("t", "lw", "hw", "cc")},
                **{name: _num(row, name) for name in ("dbh", "sh", "dbv", "sv")},
            }
        forces.append(
            {
                "Level": level,
                "Label": label,
                "Comb.": row.get("Comb.", ""),
                "Nx": row.get("Nx", 0),
                "Vz": row.get("Vz"),
                "My": row.get("My", 0),
            }
        )
    if renamed:
        _warnings.warn(SummaryInputWarning("labels_renamed", pairs=", ".join(renamed)), stacklevel=3)
    section_names = ("Level", "Label", "t", "lw", "hw", "cc", "dbh", "sh", "dbv", "sv")
    force_names = ("Level", "Label", "Comb.", "Nx", "Vz", "My")
    return (
        DataFrame(
            [{name: units.get(name, "") for name in section_names}] + list(sections.values()), columns=section_names
        ),
        DataFrame([{name: units.get(name, "") for name in force_names}] + forces, columns=force_names),
    )
