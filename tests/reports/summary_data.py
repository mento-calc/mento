"""The two tables of a summary, built from dicts: what the summary tests share.

Each builder writes the unit row first and fills every column it knows with
zero (or an empty text) unless a row or ``defaults`` gives it. Columns not
listed in ``units`` are not written, so a test can leave the reinforcement
out entirely by passing a shorter ``units``.
"""

from typing import Any, Dict, Iterable, Mapping, Optional

import pandas as pd

BEAM_UNITS: Dict[str, str] = {"Label": "", "b": "cm", "h": "cm", "cc": "mm", "legs": "", "dbs": "mm", "sl": "cm"}
for _face in ("top", "bot"):
    for _group in range(1, 5):
        BEAM_UNITS[f"n{_group}_{_face}"] = ""
        BEAM_UNITS[f"db{_group}_{_face}"] = "mm"

#: Geometry only: what a design starts from.
GEOMETRY_UNITS: Dict[str, str] = {"Label": "", "b": "cm", "h": "cm", "cc": "mm"}

SLAB_UNITS: Dict[str, str] = {"Label": "", "b": "cm", "h": "cm", "cc": "mm"}
for _face in ("top", "bot"):
    for _layer in (1, 3):
        SLAB_UNITS[f"db{_layer}_{_face}"] = "mm"
        SLAB_UNITS[f"s{_layer}_{_face}"] = "cm"

WALL_UNITS: Dict[str, str] = {
    "Level": "",
    "Label": "",
    "t": "cm",
    "lw": "m",
    "hw": "m",
    "cc": "mm",
    "dbh": "mm",
    "sh": "cm",
    "dbv": "mm",
    "sv": "cm",
}

FORCE_UNITS: Dict[str, str] = {"Label": "", "Comb.": "", "Nx": "kN", "Vz": "kN", "My": "kNm"}
WALL_FORCE_UNITS: Dict[str, str] = {"Level": "", **FORCE_UNITS}

_TEXT = ("Level", "Label", "Comb.", "Notes")


def table(
    rows: Iterable[Mapping[str, Any]], units: Mapping[str, str], defaults: Optional[Mapping[str, Any]] = None
) -> pd.DataFrame:
    """A table: the unit row, then each row over ``defaults`` over zeros (empty text for the text columns)."""
    columns = list(units)
    base = {column: ("" if column in _TEXT else 0) for column in columns}
    data = [{**base, **(defaults or {}), **row} for row in rows]
    extra = [column for row in data for column in row if column not in columns]
    columns += list(dict.fromkeys(extra))
    return pd.DataFrame([dict(units)] + data, columns=columns)


def beams(rows: Iterable[Mapping[str, Any]], units: Mapping[str, str] = BEAM_UNITS, **defaults: Any) -> pd.DataFrame:
    """A beam sections table, 20x50 with a 25 mm cover unless told otherwise."""
    return table(rows, units, {"b": 20, "h": 50, "cc": 25, **defaults})


def slabs(rows: Iterable[Mapping[str, Any]], units: Mapping[str, str] = SLAB_UNITS, **defaults: Any) -> pd.DataFrame:
    """A slab sections table: a metre strip 15 cm thick with a 20 mm cover unless told otherwise."""
    return table(rows, units, {"b": 100, "h": 15, "cc": 20, **defaults})


def walls(rows: Iterable[Mapping[str, Any]], units: Mapping[str, str] = WALL_UNITS, **defaults: Any) -> pd.DataFrame:
    """A wall sections table: 20 cm x 3 m x 3 m with a 25 mm cover unless told otherwise."""
    return table(rows, units, {"Level": "Level 1", "t": 20, "lw": 3.0, "hw": 3.0, "cc": 25, **defaults})


def forces(rows: Iterable[Mapping[str, Any]], units: Mapping[str, str] = FORCE_UNITS) -> pd.DataFrame:
    """A forces table."""
    return table(rows, units)


def wall_forces(rows: Iterable[Mapping[str, Any]], units: Mapping[str, str] = WALL_FORCE_UNITS) -> pd.DataFrame:
    """A forces table of walls, on Level 1 unless told otherwise."""
    return table(rows, units, {"Level": "Level 1"})


#: The 20x40 of the review, ACI 318-19, H25 / ADN 420, cc 25 mm, 1eØ10/17.
SUPPORT = {"Label": "V9a", "Comb.": "apoyo", "Vz": 80, "My": -60}
MIDSPAN = {"Label": "V9t", "Comb.": "tramo", "Vz": 10, "My": 170}
NINE = {"b": 20, "h": 40, "cc": 25, "legs": 2, "dbs": 10, "sl": 17}


def support_and_midspan() -> tuple:
    """Case A: the support (3Ø16 on top, -60 kN·m) and the midspan (2Ø32 at the bottom, +170) as two sections.

    Each other face carries the 2Ø8 that 1.4.0 placed without showing it.
    """
    sections = beams(
        [
            {"Label": "V9a", "n1_top": 3, "db1_top": 16, "n1_bot": 2, "db1_bot": 8},
            {"Label": "V9t", "n1_top": 2, "db1_top": 8, "n1_bot": 2, "db1_bot": 32},
        ],
        **NINE,
    )
    return sections, forces([SUPPORT, MIDSPAN])


def one_continuous_section() -> tuple:
    """Case B: the same beam declared as one section, its bars continuous, under both combinations."""
    sections = beams([{"Label": "V9", "n1_top": 3, "db1_top": 16, "n1_bot": 2, "db1_bot": 32}], **NINE)
    return sections, forces([{**SUPPORT, "Label": "V9"}, {**MIDSPAN, "Label": "V9"}])


def geometry_only() -> tuple:
    """Case C: the sections of case A with no reinforcement, to design."""
    sections = beams([{"Label": "V9a"}, {"Label": "V9t"}], units=GEOMETRY_UNITS, b=20, h=40, cc=25)
    return sections, forces([SUPPORT, MIDSPAN])
