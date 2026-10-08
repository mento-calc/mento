"""Datos de servicio y geometría inválidos no certifican una propuesta EN."""

from dataclasses import replace
import math

import pytest

from mento import Forces, SkinServiceCase
from mento.cage_detailing import CageDetailingError
from mento.codes.en_1992_2004 import skin
from mento.codes.en_1992_2004.equations.skin import adjusted_diameter, tabulated_skin_diameter
from mento.skin_reinforcement import SkinReinforcementRequirement
from mento.units import MPa, kNm, mm
from tests.sections.test_skin_reinforcement import en_beam


@pytest.mark.parametrize("value", [10 * MPa, -1 * mm, math.nan * mm])
def test_adapter_length_guard_rejects_wrong_units_or_nonpositive_values(value):
    with pytest.raises(CageDetailingError, match="length quantity|finite and positive"):
        skin._length(value, "neutral_axis")


@pytest.mark.parametrize("stress", [-1, math.nan, math.inf])
def test_table_lookup_rejects_invalid_service_stress(stress):
    with pytest.raises(ValueError, match="finite and positive"):
        tabulated_skin_diameter(stress, 0.3)


def test_adjustment_rejects_nonphysical_effective_depth():
    with pytest.raises(ValueError, match="finite and positive"):
        adjusted_diameter(32, 2.6, 600, 0)


def test_unsupported_requirement_keeps_warning():
    b = en_beam()
    assert [w.code for w in skin.warnings(b, SkinReinforcementRequirement("unsupported"))] == [
        "skin_reinforcement_unsupported"
    ]


def test_zero_demand_is_pending_without_a_tension_case():
    b = en_beam()
    b.check_flexure([Forces()])
    req = b.skin_reinforcement
    assert req.status == "pending" and req.pending_reason == "no_tension_case"


@pytest.mark.parametrize(
    "fault,message",
    [
        ("diameter", "minimum_longitudinal_diameter"),
        ("stress", "stress exceeds f_yk"),
        ("table", "skin_crack_width"),
        ("axis", "inside the section"),
        ("distribution", "cannot be distributed"),
    ],
)
def test_service_adapter_rejects_invalid_or_unbuildable_proposals(fault, message, monkeypatch):
    b = en_beam()
    b.check_flexure([Forces(M_y=100 * kNm)])
    if fault == "diameter":
        b.settings.skin_bar_diameter = 6 * mm
    elif fault == "table":
        b.settings.skin_crack_width = 0.1 * mm
    else:
        stress = 501 * MPa if fault == "stress" else 200 * MPa
        axis = (1200 if fault == "axis" else 1150 if fault == "distribution" else 240) * mm
        cases = (SkinServiceCase("SLS", "bottom", stress, axis),)
        # El adaptador mantiene guardas defensivas aunque el setter público también rechace estos datos.
        monkeypatch.setattr(type(b), "skin_service_cases", property(lambda _: cases))
    with pytest.raises(CageDetailingError, match=message) as error:
        _ = b.skin_reinforcement
    assert error.value.reason == "skin"


def test_missing_outer_tension_layer_is_rejected(monkeypatch):
    b = en_beam()
    b.check_flexure([Forces(M_y=100 * kNm)])
    g = b.section_geometry
    monkeypatch.setattr(type(b), "section_geometry", property(lambda _: replace(g, bars=())))
    with pytest.raises(CageDetailingError, match="outer tension layer"):
        _ = b.skin_reinforcement
