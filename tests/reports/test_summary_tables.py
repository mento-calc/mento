"""The two tables of the summaries: reading, writing, and every error and warning they raise."""

import re
import string
import warnings
from pathlib import Path
from typing import Any, Callable, Dict, List, Set, Tuple

import pandas as pd
import pytest

from mento import (
    BeamSummary,
    Concrete_ACI_318_19,
    MPa,
    Node,
    OneWaySlabSummary,
    RectangularBeam,
    ShearWallSummary,
    SteelBar,
    cm,
    mm,
    set_language,
)
from mento.design_warnings import DesignWarning
from mento.i18n import ES
from mento.summary_base import STATUS_TEXT, governing, warning_tag, warning_tags
from mento.summary_tables import (
    TEMPLATES,
    WARNING_CODES,
    SummaryInputError,
    SummaryInputWarning,
    label_of,
    split_single_table,
    unit_of,
)
from tests.reports.summary_data import (
    FORCE_UNITS,
    GEOMETRY_UNITS,
    beams,
    forces,
    slabs,
    support_and_midspan,
    wall_forces,
    walls,
)

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")

CONCRETE = Concrete_ACI_318_19(name="H25", f_c=25 * MPa)
STEEL = SteelBar(name="ADN 420", f_y=420 * MPa)

#: The single table of mento 1.4.0, with the columns it had.
OLD_BEAMS = pd.DataFrame(
    {
        "Label": ["", "V1"],
        "Comb.": ["", "C"],
        "b": ["cm", 20],
        "h": ["cm", 50],
        "cc": ["mm", 25],
        "Nx": ["kN", 0],
        "Vz": ["kN", 30],
        "My": ["kNm", 40],
        "ns": ["", 1],
        "dbs": ["mm", 8],
        "sl": ["cm", 20],
        "n1": ["", 3],
        "db1": ["mm", 16],
        "n2": ["", 0],
        "db2": ["mm", 0],
        "n3": ["", 0],
        "db3": ["mm", 0],
        "n4": ["", 0],
        "db4": ["mm", 0],
    }
)
OLD_WALLS = pd.DataFrame(
    {
        "Level": ["", "L1"],
        "Label": ["", "M1"],
        "Comb.": ["", "C"],
        "t": ["cm", 20],
        "lw": ["m", 3],
        "hw": ["m", 3],
        "cc": ["mm", 25],
        "Nx": ["kN", 0],
        "Vz": ["kN", 100],
        "My": ["kNm", 0],
        "dbh": ["mm", 10],
        "sh": ["cm", 20],
        "dbv": ["mm", 10],
        "sv": ["cm", 20],
    }
)
OLD_SLABS = pd.DataFrame(
    {
        "Label": ["", "L1"],
        "Comb.": ["", "C"],
        "b": ["cm", 100],
        "h": ["cm", 15],
        "cc": ["mm", 20],
        "Nx": ["kN", 0],
        "Vz": ["kN", 30],
        "My": ["kNm", 10],
        "db1": ["mm", 10],
        "s1": ["cm", 20],
    }
)

CLASSES = {"beam": (BeamSummary, OLD_BEAMS, "beam_list"), "slab": (OneWaySlabSummary, OLD_SLABS, "slab_list")}
CLASSES["wall"] = (ShearWallSummary, OLD_WALLS, "wall_list")


# ============================================================================
# The single table of 1.5.0 is deprecated: read as split_single_table, until 2.0
# ============================================================================


@pytest.mark.parametrize("kind", ["beam", "wall"])
def test_a_single_table_is_read_with_a_deprecation_warning(kind: str, tmp_path: Path) -> None:
    """A beam or wall summary still reads the single table of 1.5.0, as split_single_table converts it."""
    cls, old, keyword = CLASSES[kind]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SummaryInputWarning)
        expected = cls(CONCRETE, STEEL, *split_single_table(old, kind)).check()
        path = tmp_path / "old.xlsx"
        old.to_excel(path, index=False)
        attempts: List[Callable[[], Any]] = [
            lambda: cls(CONCRETE, STEEL, old),
            lambda: cls(CONCRETE, STEEL, **{keyword: old}),
            lambda: cls.from_excel(CONCRETE, STEEL, path),
        ]
        for attempt in attempts:
            with pytest.warns(DeprecationWarning, match="removed in mento 2.0"):
                summary = attempt()
            pd.testing.assert_frame_equal(summary.check(), expected)
        summary = attempts[0]()
        with pytest.warns(DeprecationWarning, match=f"{keyword} is deprecated"):
            assert getattr(summary, keyword) is old
        with pytest.raises(AttributeError, match=f"no {keyword}"):
            getattr(cls(CONCRETE, STEEL, *split_single_table(old, kind)), keyword)
    with pytest.raises(TypeError, match="unexpected keyword argument 'tables'"):
        cls(CONCRETE, STEEL, tables=old)
    with pytest.raises(TypeError, match="needs the sections table"):
        cls(CONCRETE, STEEL)


def test_a_slab_single_table_is_rejected_with_the_way_out(tmp_path: Path) -> None:
    """OneWaySlabSummary never read a single table, so it has nothing to deprecate."""
    cls, old, keyword = CLASSES["slab"]
    path = tmp_path / "old.xlsx"
    old.to_excel(path, index=False)
    attempts: List[Callable[[], Any]] = [
        lambda: cls(CONCRETE, STEEL, old),
        lambda: cls(CONCRETE, STEEL, **{keyword: old}),
        lambda: cls.from_excel(CONCRETE, STEEL, path),
    ]
    for attempt in attempts:
        with pytest.raises(SummaryInputError) as raised:
            attempt()
        assert raised.value.code == "single_table"
        assert "split_single_table" not in str(raised.value)
        assert "one row per slab" in str(raised.value)


def test_import_design_of_a_single_table_file_is_deprecated(tmp_path: Path) -> None:
    summary = BeamSummary(CONCRETE, STEEL, *support_and_midspan())
    path = tmp_path / "old.xlsx"
    OLD_BEAMS.to_excel(path, index=False)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SummaryInputWarning)
        with pytest.warns(DeprecationWarning, match="single-table file is deprecated"):
            summary.import_design(path)
    assert len(summary.nodes) == len(OLD_BEAMS) - 1


def test_missing_or_swapped_forces_are_named() -> None:
    sections, rows = support_and_midspan()
    with pytest.raises(SummaryInputError) as raised:
        BeamSummary(CONCRETE, STEEL, sections)
    assert raised.value.code == "missing_forces"
    assert "A section with no combination is a row of sections" in str(raised.value)
    with pytest.raises(SummaryInputError) as raised:
        BeamSummary(CONCRETE, STEEL, rows, sections)
    assert raised.value.code == "swapped_tables"


# ============================================================================
# Every error, by its code
# ============================================================================

_SECTIONS = beams([{"Label": "V1"}], units=GEOMETRY_UNITS)
_FORCES = forces([{"Label": "V1", "Comb.": "C", "Vz": 10, "My": 20}])


def _beam(sections: pd.DataFrame = _SECTIONS, rows: pd.DataFrame = _FORCES) -> Any:
    return BeamSummary(CONCRETE, STEEL, sections, rows)


def _node(**kwargs: Any) -> Node:
    beam = RectangularBeam(
        label="V1", concrete=CONCRETE, steel_bar=STEEL, width=20 * cm, height=40 * cm, c_c=25 * mm, **kwargs
    )
    return Node(beam, [])


def _slab() -> Any:
    from mento import OneWaySlab

    return OneWaySlab(label="L1", concrete=CONCRETE, steel_bar=STEEL, width=100 * cm, height=15 * cm, c_c=20 * mm)


def _write(tmp_path: Path, sheets: Dict[str, pd.DataFrame]) -> Path:
    path = tmp_path / "book.xlsx"
    with pd.ExcelWriter(path) as writer:
        for name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=name, index=False)
    return path


#: An input, the error code it raises and a text the message has to quote.
ERRORS: List[Tuple[str, Callable[[Path], Any], str]] = [
    ("single_table", lambda _: OneWaySlabSummary(CONCRETE, STEEL, OLD_SLABS), "one row per slab"),
    ("missing_forces", lambda _: BeamSummary(CONCRETE, STEEL, _SECTIONS), "forces table is missing"),
    ("swapped_tables", lambda _: BeamSummary(CONCRETE, STEEL, _FORCES, _SECTIONS), "pass sections first"),
    (
        "missing_sheet",
        lambda p: BeamSummary.from_excel(CONCRETE, STEEL, _write(p, {"Sections": _SECTIONS})),
        "no sheet 'Forces'",
    ),
    ("missing_columns", lambda _: _beam(_SECTIONS.drop(columns=["h"])), "no column 'h'"),
    ("unknown_columns", lambda _: _beam(_SECTIONS.assign(db1_tp=["mm", 10])), "did you mean 'db1_tp' -> 'db1_top'"),
    ("wrong_element", lambda _: _beam(walls([{"Label": "V1"}])), "wall"),
    (
        "stirrups_in_slab",
        lambda _: OneWaySlabSummary(CONCRETE, STEEL, slabs([{"Label": "L", "legs": 2}]), _FORCES),
        "'legs'",
    ),
    (
        "duplicate_combination",
        lambda _: _beam(rows=forces([{"Label": "V1", "Comb.": "C"}, {"Label": "V1", "Comb.": " C"}])),
        "combination 'C' of 'V1'",
    ),
    ("one_leg", lambda _: _beam(beams([{"Label": "V1", "legs": 1, "dbs": 8, "sl": 20}])), "legs of 'V1' is 1"),
    ("wrong_unit", lambda _: _beam(_SECTIONS.assign(h=["kN", 50])), "Column h of the sections table is a length"),
    (
        "missing_label",
        lambda _: _beam(beams([{"Label": "V1"}, {"Label": None}], units=GEOMETRY_UNITS)),
        "Row 4 (2nd data row)",
    ),
    (
        "duplicate_section",
        lambda _: _beam(beams([{"Label": "V1"}, {"Label": "V1"}], units=GEOMETRY_UNITS)),
        "rows 3, 4",
    ),
    ("unknown_section", lambda _: _beam(rows=forces([{"Label": "V2", "Comb.": "C"}])), "'V2'"),
    ("missing_value", lambda _: _beam(_SECTIONS.assign(cc=["mm", None])), "cc of 'V1' is empty"),
    ("not_a_number", lambda _: _beam(_SECTIONS.assign(h=["cm", "cincuenta"])), "'cincuenta'"),
    ("not_a_number", lambda _: _beam(_SECTIONS.assign(h=["cm", True])), "True"),
    ("negative_value", lambda _: _beam(beams([{"Label": "V1", "n1_bot": -2, "db1_bot": 12}])), "n1_bot of 'V1' is -2"),
    ("non_positive_dimension", lambda _: _beam(_SECTIONS.assign(b=["cm", 0])), "b of 'V1' is 0"),
    ("not_a_whole_number", lambda _: _beam(beams([{"Label": "V1", "n1_bot": 2.5, "db1_bot": 12}])), "2.5"),
    (
        "incomplete_group",
        lambda _: _beam(beams([{"Label": "V1", "n2_bot": 2, "db2_bot": 12}])),
        "n2_bot is given without n1_bot",
    ),
    (
        "mixed_materials",
        lambda _: BeamSummary.from_nodes(CONCRETE, SteelBar(name="B500", f_y=500 * MPa), [_node()]),
        "the summary is of SteelBar fy = 500",
    ),
    ("node_not_representable", lambda _: OneWaySlabSummary.from_nodes(CONCRETE, STEEL, [_node()]), "not a OneWaySlab"),
    (
        "node_not_representable",
        lambda _: BeamSummary.from_nodes(CONCRETE, STEEL, [Node(_slab(), [])]),
        "it is a OneWaySlab, not a RectangularBeam",
    ),
    ("no_forces_to_report", lambda _: _beam(rows=forces([])).shear_results(index=1), "no results"),
    ("unknown_index", lambda _: _beam().shear_results(index="V9"), "its sections are 'V1'"),
]


@pytest.mark.parametrize("code, attempt, text", ERRORS, ids=[e[0] for e in ERRORS])
def test_every_input_error(code: str, attempt: Callable[[Path], Any], text: str, tmp_path: Path) -> None:
    with pytest.raises(SummaryInputError) as raised:
        attempt(tmp_path)
    assert raised.value.code == code
    assert text in str(raised.value), str(raised.value)


def test_every_error_code_is_exercised() -> None:
    """The table above covers every error the module defines (the slab variant of single_table aside)."""
    errors = set(TEMPLATES) - WARNING_CODES - {"single_table_slab"}
    assert {code for code, _, _ in ERRORS} == errors


def test_more_beam_groups_and_stirrups_given_in_part() -> None:
    cases = [
        ({"legs": 2, "dbs": 8}, "legs is given without sl"),
        ({"dbs": 8}, "dbs is given without legs"),
        ({"n1_top": 2}, "n1_top is given without db1_top"),
        ({"db1_top": 12}, "db1_top is given without n1_top"),
        ({"n1_top": 2, "db1_top": 12, "n4_top": 2, "db4_top": 12}, "n4_top is given without n3_top"),
    ]
    for row, text in cases:
        with pytest.raises(SummaryInputError, match=re.escape(text)):
            _beam(beams([{"Label": "V1", **row}]))


def test_cells_and_rows_are_read_by_name(tmp_path: Path) -> None:
    """Columns in any order, numbers given as text with a decimal comma, and the reinforcement columns optional."""
    sections = beams([{"Label": "V1", "h": "50,0", "n1_bot": "3", "db1_bot": 16}])
    shuffled = sections[list(reversed(sections.columns))]
    summary = BeamSummary(CONCRETE, STEEL, shuffled, _FORCES)
    assert summary.nodes[0].section.height == 50 * cm
    assert summary.nodes[0].section._bar_groups("bot")[0] == (3, 16 * mm)


# ============================================================================
# Warnings
# ============================================================================


def test_input_warnings_are_reset_on_import(tmp_path: Path) -> None:
    sections = beams([{"Label": "V1"}, {"Label": "V2"}], units=GEOMETRY_UNITS)
    summary = BeamSummary(CONCRETE, STEEL, sections, _FORCES)
    assert [w.code for w in summary.input_warnings] == ["section_without_forces"]
    path = tmp_path / "x.xlsx"
    BeamSummary(CONCRETE, STEEL, _SECTIONS, _FORCES).to_excel(path)
    summary.import_design(path)
    assert summary.input_warnings == ()
    assert summary.results == ()


def test_errors_and_warnings_speak_the_language_of_the_session() -> None:
    """``str()`` stays in English, as the API's errors do; ``.message`` follows ``set_language``."""
    with pytest.raises(SummaryInputError) as raised:
        _beam(rows=forces([{"Label": "V2", "Comb.": "C"}]))
    warning = SummaryInputWarning("section_without_forces", labels="'V2'")
    set_language("es")
    try:
        assert raised.value.message.startswith("La tabla de solicitaciones nombra 'V2'")
        assert str(raised.value).startswith("The forces table names 'V2'")
        assert warning.message.startswith("'V2': sin solicitaciones")
    finally:
        set_language("en")
    assert raised.value.message == str(raised.value)
    assert raised.value.values == {"label": "'V2'", "rows": "3"}


def _fields(template: str) -> Set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(template) if name}


def test_message_templates() -> None:
    """Every template has a Spanish entry with the same placeholders, and formats with sample values."""
    for code, template in TEMPLATES.items():
        assert template in ES, code
        assert _fields(ES[template]) == _fields(template), code
        sample = {name: "x" for name in _fields(template)}
        assert template.format(**sample) and ES[template].format(**sample)
    for text in (
        "✅ Design completed for every section of the summary.",
        "Slabs designed.",
        "✅ Sections and forces written to {path}",
        "✅ Sections and forces read from {path}",
        *STATUS_TEXT.values(),
        "Warnings",
        "Horiz. (each face)",
        "Vert. (each face)",
    ):
        assert text in ES, text
        assert _fields(ES[text]) == _fields(text)


def test_the_warnings_column_holds_the_codes() -> None:
    """mento's stable codes, with the face or the direction they are read on: the same in every language."""
    face = DesignWarning(code="As_below_min", message="", face="bottom")
    direction = DesignWarning(code="mesh_ratio_below_min", message="", values={"direction": "v"})
    section = DesignWarning(code="stirrups_required", message="")
    assert warning_tag(face) == "As_below_min (bottom)"
    assert warning_tag(direction) == "mesh_ratio_below_min (v)"
    set_language("es")
    try:
        assert warning_tags((face, direction, section)) == (
            "As_below_min (bottom), mesh_ratio_below_min (v), stirrups_required"
        )
    finally:
        set_language("en")
    assert warning_tags(()) == "-"


def test_governing_names_every_tie() -> None:
    from mento.units import kN

    picked = governing(["A", "B", "C"], [(0.5, 10 * kN, 0 * kN), (0.5, -12 * kN, 5 * kN), (0.2, 3 * kN, None)])
    assert picked.combinations == ("A", "B") and picked.demand == -12 * kN and picked.axial == 5 * kN
    nothing = governing(["A"], [(0.0, None, None)])
    assert (nothing.combinations, nothing.demand, nothing.DCR) == ((), None, 0.0)


# ============================================================================
# Small pieces
# ============================================================================


@pytest.mark.parametrize(
    "value, text",
    [
        (None, ""),
        (float("nan"), ""),
        (pd.NA, ""),
        ("  V4 ", "V4"),
        (101, "101"),
        (101.0, "101"),
        (1.5, "1.5"),
        (True, "True"),
        ("", ""),
    ],
)
def test_label_of(value: Any, text: str) -> None:
    assert label_of(value) == text


def test_units() -> None:
    assert unit_of("kip·ft") == unit_of("kipft")
    with pytest.raises(KeyError):
        unit_of("furlong")
    summary = _beam()
    assert summary.get_unit_variable("kNm") == unit_of("kNm")
    summary.validate_units(["", "cm", "kipft"])
    with pytest.raises(SummaryInputError, match="'furlong'"):
        summary.get_unit_variable("furlong")
    with pytest.raises(SummaryInputError):
        summary.get_unit_variable("")


def test_an_empty_table_reads_as_no_sections() -> None:
    empty = pd.DataFrame(columns=list(GEOMETRY_UNITS))
    summary = BeamSummary(CONCRETE, STEEL, empty, pd.DataFrame(columns=list(FORCE_UNITS)))
    assert summary.nodes == () and summary.labels == []
    assert len(summary.sections_table) == 1  # the unit row


def test_a_forces_row_names_a_wall_on_its_level() -> None:
    sections = walls([{"Level": "L1", "Label": "M1"}, {"Level": "L2", "Label": "M1"}])
    with pytest.raises(SummaryInputError) as raised:
        ShearWallSummary(
            CONCRETE, STEEL, sections, wall_forces([{"Level": "L3", "Label": "M1", "Comb.": "C", "Vz": 1}])
        )
    assert raised.value.code == "unknown_section" and "'L3 / M1'" in str(raised.value)


_GUIDES = Path(__file__).resolve().parents[2] / "docs" / "source" / "user_guide"


def _guide_tables(page: str) -> Dict[str, Any]:
    """Run the code block of a user guide that builds the two tables, and return what it defines."""
    text = (_GUIDES / page).read_text(encoding="utf-8")
    blocks = re.findall(r".. code-block:: python\n\n((?:    .*\n|\n)+)", text)
    code = next(block for block in blocks if "sections = pd.DataFrame(" in block)
    namespace: Dict[str, Any] = {
        "conc": Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
        "steel": SteelBar(name="ADN 420", f_y=420 * MPa),
    }
    exec("\n".join(line[4:] for line in code.splitlines()), namespace)  # noqa: S102 - the documentation's own example
    return namespace


@pytest.mark.filterwarnings("ignore::UserWarning")
def test_documented_examples() -> None:
    """The tables the user guides write in code build their summaries, and give the numbers the guides quote."""
    beam = _guide_tables("beam_summary.rst")["beam_summary"]
    support, midspan = beam.check().iloc[1], beam.check().iloc[2]
    assert (support["DCRb,top"], support["Ok?"]) == (0.804, "❌")
    assert support["Warnings"] == "cage_detailing_infeasible"
    assert (midspan["DCRb,bot"], midspan["Ok?"]) == (1.263, "❌")
    assert midspan["Warnings"] == "not_tension_controlled (bottom), stirrup_spacing_exceeds_compression_support"

    slab = _guide_tables("slab_summary.rst")["slab_summary"]
    assert slab.labels == ["L101", "L102"] and len(slab.nodes[0].forces) == 2
    assert len(slab.check()) == 3

    wall = _guide_tables("shear_wall_summary.rst")["wall_summary"]
    assert wall.labels == [("Level 1", "M1"), ("Level 2", "M1")]
    assert list(wall.check()["Status"][1:]) == ["✅", "✅"]
