"""Errores de tabla conservan contexto y los rótulos no pierden grupos de acero."""

import pytest

from mento.beam_summary import BeamSummary
from mento.units import mm
from tests.reports.test_transverse_summary_input import beam_table, materials


def test_missing_legacy_and_explicit_face_column_is_rejected():
    table = beam_table().drop(columns="n1")
    with pytest.raises(ValueError, match="Missing reinforcement column 'n1'"):
        BeamSummary(*materials(), table)


def test_missing_all_transverse_count_columns_is_rejected():
    table = beam_table().drop(columns="n_legs")
    with pytest.raises(ValueError, match="requires 'n_legs' or legacy 'ns'"):
        BeamSummary(*materials(), table)


def test_invalid_transverse_diameter_names_beam_and_preserves_cause():
    table = beam_table()
    table.loc[1, "dbs"] = -8
    with pytest.raises(ValueError, match="V1.*invalid transverse reinforcement") as error:
        BeamSummary(*materials(), table)
    assert isinstance(error.value.__cause__, ValueError)
    assert "d_b must be greater than zero" in str(error.value.__cause__)


@pytest.mark.parametrize("missing", ["n1_bot", "db1_bot"])
def test_explicit_face_rejects_an_incomplete_count_diameter_pair(missing):
    table = beam_table()
    for n in range(1, 5):
        table[f"n{n}_bot"] = ["", 4 if n == 1 else 0]
        table[f"db{n}_bot"] = ["mm", 20 if n == 1 else 0]
    table.loc[1, missing] = 0
    with pytest.raises(ValueError, match="V1.*incomplete bottom reinforcement pair"):
        BeamSummary(*materials(), table)


def test_summary_labels_preserve_second_group_when_first_group_is_empty():
    summary = BeamSummary(*materials(), beam_table())
    section = summary.nodes[0].section
    section.set_longitudinal_rebar_bot(n1=0, d_b1=0 * mm, n2=3, d_b2=12 * mm)
    _, bottom, _ = summary._rebar_labels(section)
    assert bottom == section._format_longitudinal_rebar_string(3, 12 * mm, 0, 0 * mm)
