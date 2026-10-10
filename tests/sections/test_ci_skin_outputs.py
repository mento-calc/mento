"""Estados, avisos y tablas de piel conservan pendientes y rechazan entradas ambiguas."""

import pytest

import mento.cage_detailing as cage
import mento.skin_reinforcement as skin
from mento import BeamSummary, OneWaySlab
from mento.cage_detailing import CageDetailingError
from mento.design_warnings import skin_warnings
from mento.units import cm, mm
from tests.sections.test_manual_skin_rebar import manual_tables
from tests.sections.test_skin_reinforcement import beam


def test_manual_skin_is_rejected_for_grid_sections():
    b = beam()
    slab = OneWaySlab(concrete=b.concrete, steel_bar=b.steel_bar, width=30 * cm, height=50 * cm, c_c=30 * mm)
    with pytest.raises(ValueError, match="not grid sections"):
        slab.set_skin_rebar(10 * mm, 2, "total")


@pytest.mark.parametrize("scope", ["not_applicable", "not_required"])
def test_skin_status_preserves_exempt_scope(monkeypatch, scope):
    b = beam()
    monkeypatch.setattr(skin, "skin_requirement", lambda _: skin.SkinReinforcementRequirement(scope))
    assert b.skin_verification_status == scope


def test_unavailable_requirement_is_pending(monkeypatch):
    b = beam()

    def unavailable(_):
        raise CageDetailingError("Input unavailable", reason="skin")

    monkeypatch.setattr(skin, "skin_requirement", unavailable)
    assert b.skin_verification_status == "pending"


def test_missing_proposed_skin_bars_is_pending_and_emits_warning(monkeypatch):
    b = beam()
    g = b.section_geometry
    req = skin.SkinReinforcementRequirement("required", n_per_side=1, s_max=200 * mm)
    monkeypatch.setattr(skin, "skin_requirement", lambda _: req)
    monkeypatch.setattr(cage, "build_cage_detailing", lambda *args, **kwargs: g)
    assert b.skin_verification_status == "pending"
    assert "skin_detailing_pending" in [w.code for w in skin_warnings(b)]


@pytest.mark.parametrize("reason,expected", [("layout", "pending"), ("skin", "failed")])
def test_cage_failure_is_distinguished_from_skin_failure(monkeypatch, reason, expected):
    b = beam()
    monkeypatch.setattr(skin, "skin_requirement", lambda _: skin.SkinReinforcementRequirement("required"))

    def unavailable(*args, **kwargs):
        raise CageDetailingError("Candidate unavailable", reason=reason)

    monkeypatch.setattr(cage, "build_cage_detailing", unavailable)
    assert b.skin_verification_status == expected


@pytest.mark.parametrize("status", ["required", "unsupported"])
def test_missing_skin_rule_keeps_unsupported_warning(monkeypatch, status):
    b = beam()
    g = b.section_geometry
    monkeypatch.setattr(skin, "skin_requirement", lambda _: skin.SkinReinforcementRequirement(status))
    monkeypatch.setattr(cage, "build_cage_detailing", lambda *args, **kwargs: g)
    assert "skin_reinforcement_unsupported" in [w.code for w in skin_warnings(b)]


@pytest.mark.parametrize("column", ["n_skin", "pos_skin"])
def test_manual_counts_and_position_have_no_units(column):
    sections, rows = manual_tables()
    sections.loc[0, column] = "mm"
    b = beam()
    with pytest.raises(ValueError, match="unit row says"):
        BeamSummary(b.concrete, b.steel_bar, sections, rows)


def test_a_manual_diameter_without_unit_is_rejected_naming_the_column():
    sections, rows = manual_tables()
    sections.loc[0, "db_skin"] = ""
    b = beam()
    with pytest.raises(ValueError, match="Column db_skin of the sections table is a length"):
        BeamSummary(b.concrete, b.steel_bar, sections, rows)


def test_summary_requires_a_dimensionless_leg_count():
    sections, rows = manual_tables()
    sections.loc[0, "legs"] = "mm"
    b = beam()
    with pytest.raises(ValueError, match="unit row says"):
        BeamSummary(b.concrete, b.steel_bar, sections, rows)
