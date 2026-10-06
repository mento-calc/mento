"""The shear report shows the legs, their spacing and the row of Table 9.7.6.2.2.

The strength table of a beam counts the closed stirrups and the legs, and
gives the spacing of the legs across the width; under ACI 318-19 and CIRSOC
201-25 it adds, for every element, the shear the stirrups must carry, the
threshold of Table 9.7.6.2.2, the row the check took and that row's cap. Rows
are read by label, never by position.
"""

from dataclasses import replace
from typing import Any, Dict

import numpy as np
import pandas as pd
import pytest

from mento import (
    Concrete_ACI_318_19,
    Concrete_CIRSOC_201_25,
    Concrete_EN_1992_2004,
    Footing,
    Forces,
    Node,
    OneWaySlab,
    RectangularBeam,
    SteelBar,
)
from mento.codes.registry import design_code
from mento.i18n import ES
from mento.reports.tables import _spacing_table_rows
from mento.results import DocumentBuilder, round_for_display
from mento.units import MPa, cm, inch, kip, kN, kNm, ksi, mm

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")

HALVED = "Vs,req > Vs,lim → Table 9.7.6.2.2: d/4 along, d/2 across"
LOW = "Vs,req ≤ Vs,lim → Table 9.7.6.2.2: d/2 along, d across"
V_S_REQ = "Nominal shear the stirrups must carry (Vu/φ − Vc)"
THRESHOLD_SI = "Threshold of Table 9.7.6.2.2 (0.33√f'c·bw·d)"
THRESHOLD_US = "Threshold of Table 9.7.6.2.2 (4√f'c·bw·d)"
CAP = "Absolute cap of Table 9.7.6.2.2 in this row"
SUPPORT = "Stirrup spacing, lateral support of compression bars (§9.7.6.4.3)"
EN_ALONG = "Expression (9.6N) along: 0.75·d·(1 + cot α), capped at 400 mm by mento"
EN_ACROSS = "Expression (9.8N) across: 0.75·d, at most 600 mm"


def _rows(table: Dict[str, list]) -> Dict[str, tuple]:  # type: ignore[type-arg]
    """label -> (variable, value, unit)."""
    labels = next(iter(table.values()))
    return {
        label: (var, value, unit)
        for label, var, value, unit in zip(labels, table["Variable"], table["Value"], table["Unit"])
    }


def _limits(table: Dict[str, list]) -> Dict[str, tuple]:  # type: ignore[type-arg]
    return {
        label: (value, maximum, ok)
        for label, value, maximum, ok in zip(table["Check"], table["Value"], table["Max."], table["Ok?"])
    }


def _wide_cirsoc_beam(concrete: Any = None, steel: Any = None) -> RectangularBeam:
    beam = RectangularBeam(
        label="V1",
        concrete=concrete or Concrete_CIRSOC_201_25(name="H-25", f_c=25 * MPa),
        steel_bar=steel or SteelBar(name="ADN 420", f_y=420 * MPa),
        width=150 * cm,
        height=150 * cm,
        c_c=30 * mm,
    )
    Node(section=beam, forces=[Forces(label="C1", M_y=5000 * kNm, V_z=5000 * kN)]).design()
    return beam


def test_the_wide_cirsoc_beam_prints_the_legs_and_the_halved_row() -> None:
    beam = _wide_cirsoc_beam()
    rows = _rows(beam._shear_reinforcement)

    assert rows["Number of stirrups"] == ("ns", 5, "")
    assert rows["Number of legs"] == ("nl", 10, "")
    assert rows["Stirrup diameter"] == ("db", 12, "mm")
    assert rows["Stirrup spacing"] == ("s", 14, "cm")
    assert rows["Leg spacing across width"] == ("sw", 15.87, "cm")
    assert rows["Effective height"][1] == pytest.approx(144.2)
    assert rows[V_S_REQ] == ("Vs,req", 4828.12, "kN")
    assert rows[THRESHOLD_SI] == ("Vs,lim", 3568.95, "kN")
    assert rows[HALVED] == ("", "", "")
    assert LOW not in rows
    assert rows[CAP] == ("s,cap", 20.0, "cm")
    assert SUPPORT not in rows
    # Every column keeps one entry per row.
    assert len({len(column) for column in beam._shear_reinforcement.values()}) == 1

    limits = _limits(beam._data_min_max_shear)
    assert limits["Leg spacing across width (Table 9.7.6.2.2)"] == (15.87, 20.0, "✅")
    assert limits["Stirrup spacing along length"] == (14, 20.0, "✅")


def test_aci_prints_its_300_mm_cap() -> None:
    beam = _wide_cirsoc_beam(Concrete_ACI_318_19(name="H25", f_c=25 * MPa))
    rows = _rows(beam._shear_reinforcement)
    assert rows["Number of legs"] == ("nl", 6, "")
    assert HALVED in rows
    assert rows[CAP] == ("s,cap", 30.0, "cm")


def test_a_beam_under_the_threshold_prints_the_low_row() -> None:
    beam = RectangularBeam(
        label="V2",
        concrete=Concrete_CIRSOC_201_25(name="H-25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=30 * cm,
        height=100 * cm,
        c_c=25 * mm,
    )
    Node(section=beam, forces=[Forces(label="C1", M_y=100 * kNm, V_z=150 * kN)]).design()
    rows = _rows(beam._shear_reinforcement)
    assert rows[LOW] == ("", "", "")
    assert HALVED not in rows
    assert rows[CAP] == ("s,cap", 40.0, "cm")
    assert rows[V_S_REQ][1] < rows[THRESHOLD_SI][1]


def test_an_imperial_section_uses_the_psi_threshold_and_its_cap_in_inches() -> None:
    beam = RectangularBeam(
        label="I1",
        concrete=Concrete_ACI_318_19(name="C4", f_c=4 * ksi),
        steel_bar=SteelBar(name="G60", f_y=60 * ksi),
        width=24 * inch,
        height=40 * inch,
        c_c=1.5 * inch,
    )
    Node(section=beam, forces=[Forces(label="C1", M_y=400 * kip * inch * 12, V_z=380 * kip)]).design()
    rows = _rows(beam._shear_reinforcement)
    assert THRESHOLD_US in rows and THRESHOLD_SI not in rows
    assert rows[HALVED][0] == ""
    assert rows[CAP] == ("s,cap", 12, "in")


def test_the_row_follows_the_state_not_a_new_comparison() -> None:
    """The report prints the row the equation decided: flip the state, the row and cap follow."""
    beam = _wide_cirsoc_beam()
    state = design_code(beam.concrete).check_shear(beam, Forces(label="C1", M_y=5000 * kNm, V_z=5000 * kN))
    labels, _, values, _ = _spacing_table_rows(beam, state)
    assert labels[2] == HALVED and values[3] == 20.0
    labels, _, values, _ = _spacing_table_rows(beam, replace(state, spacing_halved=False))
    assert labels[2] == LOW and values[3] == 40.0


@pytest.mark.parametrize("code", ["CIRSOC", "ACI"])
def test_a_section_bracing_compression_bars_prints_the_support_cap(code: str) -> None:
    """§9.7.6.4.3 caps s at the least dimension (20 cm) of a 20x50 relying on compression bars."""
    concrete: Any = (
        Concrete_CIRSOC_201_25(name="H-25", f_c=25 * MPa)
        if code == "CIRSOC"
        else Concrete_ACI_318_19(name="H25", f_c=25 * MPa)
    )
    beam = RectangularBeam(
        label="D",
        concrete=concrete,
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=20 * cm,
        height=50 * cm,
        c_c=25 * mm,
    )
    M = 300 if code == "CIRSOC" else 260
    Node(section=beam, forces=[Forces(label="C1", M_y=M * kNm, V_z=100 * kN)]).design()
    assert SUPPORT not in _rows(beam._shear_reinforcement)
    limits = _limits(beam._data_min_max_shear)
    s_l = beam._stirrup_s_l.to("cm").magnitude
    assert limits[SUPPORT] == (round(s_l, 2), 20.0, "✅" if s_l <= 20.0 else "❌")
    # A row of its own, which _all_shear_checks_passed does not read: it keeps the four above it.
    assert beam._all_shear_checks_passed == all(ok == "✅" for ok in beam._data_min_max_shear["Ok?"][:4])
    assert len({len(column) for column in beam._data_min_max_shear.values()}) == 1


def _braced(s_l: Any, n_stirrups: int = 1) -> RectangularBeam:
    """A 20x50 CIRSOC beam relying on its top bars under -300 kN·m: §9.7.6.4.3 caps s at 20 cm."""
    beam = RectangularBeam(
        label="D",
        concrete=Concrete_CIRSOC_201_25(name="H-25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=20 * cm,
        height=50 * cm,
        c_c=25 * mm,
    )
    beam.set_longitudinal_rebar_bot(n1=2, d_b1=25 * mm, n2=1, d_b2=20 * mm)
    beam.set_longitudinal_rebar_top(n1=2, d_b1=25 * mm, n2=1, d_b2=20 * mm)
    if n_stirrups:
        beam.set_transverse_rebar(n_stirrups=n_stirrups, d_b=6 * mm, s_l=s_l)
    Node(section=beam, forces=[Forces(label="C1", M_y=-300 * kNm, V_z=100 * kN)]).check()
    return beam


def test_the_support_row_reads_the_warnings_verdict() -> None:
    """s = 22 cm: within Table 9.7.6.2.2's 22.86 cm, past the 20 cm of §9.7.6.4.3.

    The along-length row stays ✅ against the table; the §9.7.6.4.3 row says ❌,
    as the warning does, and the flag of the four rows above keeps what it was.
    """
    beam = _braced(22 * cm)
    limits = _limits(beam._data_min_max_shear)
    assert limits["Stirrup spacing along length"] == (22, 22.86, "✅")
    assert limits[SUPPORT] == (22, 20.0, "❌")
    codes = {warning.code for warning in beam.warnings}
    assert "stirrup_spacing_exceeds_compression_support" in codes
    assert beam._all_shear_checks_passed == all(ok == "✅" for ok in beam._data_min_max_shear["Ok?"][:4])
    # At the cap exactly it passes, as the warning's comparison does.
    assert _limits(_braced(20 * cm)._data_min_max_shear)[SUPPORT][2] == "✅"


def test_the_support_row_of_a_section_with_no_stirrups_fails() -> None:
    """No stirrups on a section that relies on compression bars: ❌, at the cap of the smallest stirrup allowed."""
    beam = _braced(0 * cm, n_stirrups=0)
    assert "stirrups_required_for_compression_support" in {warning.code for warning in beam.warnings}
    value, cap, ok = _limits(beam._data_min_max_shear)[SUPPORT]
    assert (value, ok) == (0, "❌")
    assert cap == 20.0


def test_en_prints_the_legs_and_where_its_limits_come_from() -> None:
    beam = _wide_cirsoc_beam(Concrete_EN_1992_2004(name="C25", f_c=25 * MPa), SteelBar(name="B500S", f_y=500 * MPa))
    rows = _rows(beam._shear_reinforcement)
    assert rows["Number of legs"] == ("nl", 4, "")
    assert rows["Leg spacing across width"] == ("sw", 47.6, "cm")
    assert rows[EN_ALONG] == ("", "", "")
    assert rows[EN_ACROSS] == ("", "", "")
    assert not {THRESHOLD_SI, THRESHOLD_US, HALVED, LOW, CAP} & set(rows)
    limits = _limits(beam._data_min_max_shear)
    assert limits["Leg spacing across width (§9.2.2(8))"][:2] == (47.6, 60.0)


@pytest.mark.parametrize("element", [OneWaySlab, Footing])
def test_slabs_and_footings_get_the_threshold_rows_and_no_leg_rows(element: type) -> None:
    section = element(
        label="S",
        concrete=Concrete_CIRSOC_201_25(name="H-25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=100 * cm,
        height=40 * cm,
        c_c=50 * mm,
    )
    Node(section=section, forces=[Forces(label="C1", M_y=100 * kNm, V_z=250 * kN)]).design()
    rows = _rows(section._shear_reinforcement)
    assert "Number of legs" not in rows and "Number of stirrups" not in rows
    assert V_S_REQ in rows and THRESHOLD_SI in rows and CAP in rows
    assert (HALVED in rows) != (LOW in rows)
    assert len({len(column) for column in section._shear_reinforcement.values()}) == 1
    assert "Stirrup spacing along width (Table 9.7.6.2.2)" in section._data_min_max_shear["Check"]


def test_an_en_slab_keeps_its_rows() -> None:
    slab = OneWaySlab(
        label="S",
        concrete=Concrete_EN_1992_2004(name="C25", f_c=25 * MPa),
        steel_bar=SteelBar(name="B500S", f_y=500 * MPa),
        width=100 * cm,
        height=30 * cm,
        c_c=25 * mm,
    )
    Node(section=slab, forces=[Forces(label="C1", M_y=60 * kNm, V_z=300 * kN)]).design()
    rows = _rows(slab._shear_reinforcement)
    assert EN_ALONG not in rows and EN_ACROSS not in rows
    assert "Stirrup spacing along width" in slab._data_min_max_shear["Check"]


def test_the_word_report_prints_whole_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    """``ns 5`` and ``nl 10``, not ``5.0``: a count is a whole number."""
    beam = _wide_cirsoc_beam()
    saved: Dict[str, Any] = {}
    monkeypatch.setattr(DocumentBuilder, "save", lambda self, filename: saved.update(doc=self.doc))
    beam.shear_results_detailed_doc()
    cells = {}
    for table in saved["doc"].tables:
        for row in table.rows:
            texts = [c.text for c in row.cells]
            if len(texts) >= 3:
                cells[texts[1]] = texts[2]
    assert cells["ns"] == "5"
    assert cells["nl"] == "10"
    assert cells["db"] == "12"
    assert cells["s"] == "14"
    assert cells["sw"] == "15.87"


def test_round_for_display_keeps_the_text_of_a_float_column() -> None:
    df = pd.DataFrame(
        {"Check": ["a", "b"], "Variable": ["x", "DCR"], "Value": np.array([14.0, 0.98765]), "Unit": ["cm", ""]}
    )
    out = round_for_display(df)
    assert [str(v) for v in out["Value"]] == ["14.0", "0.99"]
    mixed = pd.DataFrame(
        {"Check": ["a", "b"], "Variable": ["ns", "d"], "Value": pd.Series([5, 144.2], dtype=object), "Unit": ["", "cm"]}
    )
    assert [str(v) for v in round_for_display(mixed)["Value"]] == ["5", "144.2"]


@pytest.mark.parametrize(
    "key",
    [
        "Number of legs",
        "Leg spacing across width",
        "Leg spacing across width (Table 9.7.6.2.2)",
        "Leg spacing across width (§9.2.2(8))",
        "Stirrup spacing along width (Table 9.7.6.2.2)",
        THRESHOLD_SI,
        THRESHOLD_US,
        HALVED,
        LOW,
        CAP,
        SUPPORT,
        EN_ALONG,
        EN_ACROSS,
        V_S_REQ,
    ],
)
def test_every_new_report_row_is_translated(key: str) -> None:
    assert key in ES
    assert ES[key] != key
