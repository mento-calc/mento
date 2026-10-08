"""Piezas reales, ramas impares y sujeción cerrada sin crédito de patas abiertas."""

import math
from dataclasses import replace
import matplotlib.pyplot as plt
import pandas as pd
import pytest
from mento import Concrete_ACI_318_19, RectangularBeam, SteelBar, Forces, BeamSummary
from mento.compression_detailing import check_compression_detailing
from mento.units import MPa, cm, mm, kNm, kN


def beam(legs=7, width=80):
    b = RectangularBeam(
        label="Mixta",
        concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN420", f_y=420 * MPa),
        width=width * cm,
        height=60 * cm,
        c_c=30 * mm,
    )
    b.set_longitudinal_rebar_bot(n1=7, d_b1=20 * mm)
    b.set_longitudinal_rebar_top(n1=3, d_b1=16 * mm)
    b.set_transverse_rebar(legs=legs, d_b=10 * mm, s_l=15 * cm)
    b.check([Forces(M_y=100 * kNm, V_z=80 * kN)])
    return b


@pytest.mark.parametrize("legs", [2, 3, 4, 7, 9])
def test_integer_legs_survive_strength_geometry_and_labels(legs):
    b = beam(legs)
    assert b.reinforcement.transverse.n_legs == legs
    assert b.shear_design.n_legs == legs
    assert b.reinforcement.transverse.A_v.to("mm").magnitude == pytest.approx(legs * math.pi * 100 / 4 / 150)
    g = b.detailing_geometry
    assert len(g.leg_x) == legs
    assert len(g.stirrups) == 1
    assert len(g.crossties) == legs - 2
    assert all(t.hooks == () for t in g.crossties)
    if legs > 2:
        assert "pata" in g.arrangement("es")
    before = b.reinforcement, b.section_geometry.to_dict("mm")
    fig = b.plot(show=False)
    assert sum(p.get_gid() == "crosstie" for p in fig.axes[0].patches) == legs - 2
    assert not any(line.get_gid() == "crosstie_hook" for line in fig.axes[0].lines)
    plt.close(fig)
    assert before == (b.reinforcement, b.section_geometry.to_dict("mm"))


def test_closed_selection_uses_the_existing_compression_check():
    b = beam(7, 80)
    b._compression_faces = {"bot"}  # Aislar la selección geométrica, no simular flexión.
    g = b.detailing_geometry
    assert len(g.stirrups) == 1
    assert g.crossties
    result = check_compression_detailing(b, g)
    assert result.status == "passed"
    assert check_compression_detailing(b, replace(g, crossties=())).status == "failed"
    assert sum(2 for _ in g.stirrups) + len(g.crossties) == len(g.leg_x) == 7


def test_extra_closed_pieces_are_shown_but_not_credited_in_shear():
    b = beam(3, 60)
    before = b.reinforcement, b.section_geometry.to_dict("mm")
    b._compression_faces = {"bot"}
    g = b.detailing_geometry
    assert check_compression_detailing(b, g).status == "passed"
    assert len(g.leg_x) > 3 and len(g.stirrups) == 1
    assert (b.reinforcement, b.section_geometry.to_dict("mm")) == before
    fig = b.plot(show=False)
    assert any("proposed legs; A_v uses" in t.get_text() for t in fig.axes[0].texts)
    plt.close(fig)


@pytest.mark.parametrize("moments,faces", [([2500], {"top"}), ([-2500], {"bot"}), ([2500, -2500], {"top", "bot"})])
def test_real_forces_activate_required_compression_support(moments, faces):
    b = beam(7, 80)
    b.set_longitudinal_rebar_bot(n1=7, d_b1=25 * mm)
    b.set_longitudinal_rebar_top(n1=7, d_b1=25 * mm)
    b.check([Forces(M_y=m * kNm, V_z=80 * kN) for m in moments])
    # Si el momento de esta sección no requiere acero comprimido, usar un
    # momento mayor; en ambos casos se evalúa flexión real, no caras inventadas.
    if not b._compression_faces:
        b.check([Forces(M_y=2 * m * kNm, V_z=80 * kN) for m in moments])
    assert b._compression_faces == faces
    assert b.compression_detailing.status == "passed"
    assert len(b.detailing_geometry.stirrups) == 1
    assert all(t.hooks == (135, 90) for t in b.detailing_geometry.crossties)


@pytest.mark.parametrize("legs", [1, -1, True, 3.5])
def test_invalid_input_is_atomic(legs):
    b = beam()
    original = b.reinforcement
    with pytest.raises((TypeError, ValueError)):
        b.set_transverse_rebar(legs=legs, d_b=10 * mm, s_l=15 * cm)
    assert b.reinforcement == original


def test_odd_summary_excel_roundtrip(tmp_path):
    data = pd.DataFrame(
        [
            ["", "", "cm", "cm", "mm", "kN", "kN", "kNm", "", "mm", "cm", "", "mm"],
            ["V1", "C1", 80, 60, 30, 0, 80, 100, 7, 10, 15, 7, 20],
        ],
        columns=["Label", "Comb.", "b", "h", "cc", "Nx", "Vz", "My", "legs", "dbs", "sl", "n1", "db1"],
    )
    for i in (2, 3, 4):
        data[f"n{i}"] = ["", 0]
        data[f"db{i}"] = ["mm", 0]
    template = beam()
    summary = BeamSummary(template.concrete, template.steel_bar, data)
    summary.design_data = summary.data.copy()
    path = tmp_path / "mixta.xlsx"
    summary.export_design(str(path))
    summary.import_design(str(path))
    assert summary.nodes[0].section.reinforcement.transverse.n_legs == 7


def test_symmetric_seven_leg_cage_keeps_the_open_leg_at_the_centre():
    b = beam(7, 80)
    b.set_longitudinal_rebar_top(n1=8, d_b1=10 * mm)
    b.check([Forces(M_y=1500 * kNm, V_z=80 * kN)])
    assert b._compression_faces == {"top"}
    g = b.detailing_geometry
    assert [s.legs for s in g.stirrups] == [(0, 6)]
    assert [t.leg for t in g.crossties] == [1, 2, 3, 4, 5]
    assert g.crossties[2].x.to(mm).magnitude == pytest.approx(400)
    assert b.compression_detailing.status == "passed"
    # La resistencia excedida no se transforma en cumplimiento por el detalle.
    assert b.verification_status["resistance"] == "failed"


@pytest.mark.parametrize("diameter", [float("nan") * mm, 0 * mm, 6 * mm])
def test_invalid_mounting_with_compression_does_not_crash_status(diameter):
    b = beam()
    b._compression_faces = {"bot"}
    b.settings.mounting_bar_diameter = diameter
    assert b.verification_status["detailing"] == "failed"
    assert "cage_detailing_infeasible" in [w.code for w in b.warnings]
