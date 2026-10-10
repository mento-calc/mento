"""Salida de casos heredados y reposicionamiento seguro de la segunda capa."""

from dataclasses import replace
from types import SimpleNamespace

import pandas as pd
import pytest

from mento import cage_detailing as cage
from mento.beam_summary import BeamSummary
from mento.design_warnings import compression_detailing_warnings
from mento.units import mm
from mento.verification import verification_status
from tests.sections.test_compression_detailing import beam


def test_missing_compression_evaluator_is_pending_without_strength_failure():
    face = SimpleNamespace(DCR=0.2)
    subject = SimpleNamespace(
        flexure_checks=[SimpleNamespace(complies=True, bottom=face, top=face)],
        shear_checks=[SimpleNamespace(DCR=0.2)],
        warnings=[],
        _compression_faces={"top"},
        _stirrups_optional=True,
    )
    assert verification_status(subject) == {"resistance": "passed", "detailing": "pending"}


def test_unchecked_flexure_does_not_emit_a_compression_failure():
    b = beam()
    assert b.compression_detailing.reason == "flexure_not_checked"
    assert compression_detailing_warnings(b) == []


def test_legacy_export_preserves_closed_count_as_twice_as_many_legs(tmp_path):
    data = pd.DataFrame({"Label": ["V1"], "ns": [3]})
    summary = SimpleNamespace(design_data=data, units_row=["", ""], beam_list=data, _ELEMENT_COLUMN="Beam")
    path = tmp_path / "legacy.xlsx"
    BeamSummary.export_design(summary, str(path))
    exported = pd.read_excel(path)
    assert "ns" not in exported and "n_legs" not in exported
    assert exported["legs"].iloc[1] == 6


def test_arrangement_describes_multiple_internal_closed_stirrups():
    g = beam().section_geometry
    g = replace(
        g, stirrups=(g.stirrups[0], replace(g.stirrups[0], perimeter=False), replace(g.stirrups[0], perimeter=False))
    )
    assert g.arrangement("en") == "perimeter stirrup + 2 inner stirrups"


def _mm_of(value):  # type: ignore[no-untyped-def]
    return float(value.to(mm).magnitude)


def test_second_layer_crossing_an_open_leg_keeps_steel_and_height():
    b = beam()
    b.set_transverse_rebar(legs=3, d_b=10 * mm, s_l=150 * mm)
    g = b.section_geometry
    extra = replace(g.bars_on("bottom", 1)[0], layer=2, x=g.crossties[0].x, y=200 * mm)
    detail = cage._build_candidate(b, replace(g, bars=g.bars + (extra,)))
    second = detail.bars_on("bottom", 2)
    assert len(second) == 1
    # The layer behind keeps its steel and sinks with the corner bars seated in their bends.
    corner = detail.bars_on("bottom", 1)[0]
    sink = corner.y - g.bars_on("bottom", 1)[0].y
    assert sink.to(mm).magnitude > 0
    assert _mm_of(second[0].y) == pytest.approx(_mm_of(extra.y + sink)) and second[0].d_b == extra.d_b
    assert second[0].x != extra.x
    assert second[0].x == detail.bars_on("bottom", 1)[0].x


def test_en_compression_support_emits_pending_scope_warning():
    from tests.sections.test_r3_C2 import en_beam

    b = en_beam()
    b._compression_faces = {"top"}
    assert [w.code for w in compression_detailing_warnings(b)] == ["compression_detailing_en_pending"]
