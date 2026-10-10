"""Los rótulos no pierden grupos de acero."""

from mento import Concrete_ACI_318_19, MPa, SteelBar
from mento.beam_summary import BeamSummary
from mento.units import mm
from tests.reports.summary_data import beams, forces


def test_summary_labels_preserve_second_group_when_first_group_is_empty():
    summary = BeamSummary(
        Concrete_ACI_318_19(name="C25", f_c=25 * MPa),
        SteelBar(name="ADN420", f_y=420 * MPa),
        beams([{"Label": "V1", "n1_bot": 4, "db1_bot": 20}], legs=4, dbs=8, sl=20),
        forces([{"Label": "V1", "Comb.": "ULS", "Vz": 50, "My": 40}]),
    )
    section = summary.nodes[0].section
    section.set_longitudinal_rebar_bot(n1=0, d_b1=0 * mm, n2=3, d_b2=12 * mm)
    _, bottom, _ = summary._rebar_labels(section)
    assert bottom == section._format_longitudinal_rebar_string(3, 12 * mm, 0, 0 * mm)
