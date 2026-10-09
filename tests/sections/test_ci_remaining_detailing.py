"""Casos que el último reporte remoto todavía deja sin cobertura."""

import math
from dataclasses import replace
from types import SimpleNamespace

import pytest

from mento import cage_detailing as cage
from mento.compression_detailing import check_compression_detailing
from mento.crosstie_detailing import tie_supports
from mento.design_warnings import collect, compression_detailing_warnings
from mento.material import Concrete_CIRSOC_201_25
from mento.units import mm
from tests.sections.test_compression_detailing import beam, face_geometry


def test_fewer_closed_corners_preserves_resistant_bars_and_separates_mounting():
    b = beam()
    b.set_longitudinal_rebar_top(n1=3, d_b1=16 * mm)
    b.set_transverse_rebar(legs=5, d_b=10 * mm, s_l=150 * mm)
    g = b.section_geometry
    row = g.bars_on("top", 1)
    mounting = replace(row[0], d_b=10 * mm, group=0)
    corners = [
        (float(x.to(mm).magnitude), 1 if i < 4 else -1, 25.0 if i in (0, 4) else 0.0) for i, x in enumerate(g.leg_x)
    ]
    resistant, added = cage._supported_layer(row, corners, mounting, 30, math.inf, 10, 25, True)
    assert len(resistant) == 3 and len(added) == 2
    assert [(bar.d_b, bar.y, bar.group) for bar in resistant] == [(bar.d_b, bar.y, bar.group) for bar in row]
    assert all(bar.d_b == 10 * mm and bar.group == 0 for bar in added)
    assert all(a.x < b.x for a, b in zip(resistant, resistant[1:]))


def test_large_90_degree_crosstie_has_twelve_diameters_and_engages_bars():
    b = beam(width=80)
    b.set_transverse_rebar(legs=3, d_b=20 * mm, s_l=150 * mm)
    b._compression_faces = {"top"}  # Aislar la geometría de la decisión resistente.
    entered = b.reinforcement
    g = b.detailing_geometry
    assert g.crossties
    for tie in g.crossties:
        assert tie.hooks == (135, 90) and tie.alternate_hooks
        assert tie.bend_inner_diameter == 120 * mm
        assert tie.extension == 240 * mm
        assert all(tie_supports(bar, tie, g, b.concrete.design_code, False) for bar in tie.engaged_bars)
    assert b.reinforcement == entered


@pytest.mark.parametrize("expected", ["failed", "pending"])
def test_compression_face_warning_preserves_failure_or_pending_and_distance(expected):
    b = beam(Concrete_CIRSOC_201_25) if expected == "pending" else beam()
    b._compression_faces = {"top"}
    if expected == "pending":
        g = face_geometry(b, [60, 210, 360], [(0, 2)])
        g = replace(
            g,
            bars=tuple(replace(bar, y=548 * mm) for bar in g.bars),
            stirrups=tuple(replace(s, x_left=40 * mm, x_right=380 * mm) for s in g.stirrups),
            stirrup_d_b=8 * mm,
            stirrup_bend_inner_diameter=32 * mm,
        )
    else:
        g = face_geometry(b, [60, 140, 220, 300, 380], [(0, 4)])
    result = check_compression_detailing(b, g)
    assert result.status == expected
    raw = compression_detailing_warnings(SimpleNamespace(concrete=b.concrete, compression_detailing=result))
    assert len(raw) == 1
    assert raw[0].code == "compression_detailing_" + expected and raw[0].face == "top"
    assert raw[0].values["distance"] == result.faces[0].maximum_clear_distance
    warning = collect(raw)[0]
    assert warning.code == raw[0].code and warning.face == "top"
    assert raw[0].values["reason"] in warning.message
