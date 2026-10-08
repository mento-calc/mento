"""Rechazos de entrada y estados pendientes que faltaban en la cobertura de CI."""

from types import SimpleNamespace

import pandas as pd
import pytest

from mento import Concrete_ACI_318_19, MPa, RectangularBeam, SteelBar, cm, mm


from mento.verification import normalize_leg_column, verification_status


def test_leg_normalization_leaves_tables_without_preferred_alias_untouched():
    frame = pd.DataFrame({"n_legs": ["", 4]})
    assert normalize_leg_column(frame) is frame


def test_leg_normalization_preserves_input_and_writes_equivalent_canonical_counts():
    frame = pd.DataFrame({"legs": ["", "4", ""], "n_legs": ["", 4, 2]}, dtype=object)
    original = frame.copy(deep=True)
    out = normalize_leg_column(frame)
    assert out["n_legs"].tolist() == ["", 4, 2]
    assert out["legs"].tolist() == ["", "4", ""]
    pd.testing.assert_frame_equal(frame, original)


@pytest.mark.parametrize(
    "value, exception, message",
    [
        (True, TypeError, "must be an integer"),
        ("two", ValueError, "must be an integer"),
        (object(), ValueError, "must be an integer"),
        (2.5, ValueError, "must be a finite integer"),
        (float("inf"), ValueError, "must be a finite integer"),
    ],
)
def test_leg_column_rejects_invalid_counts_without_modifying_input(value, exception, message):
    frame = pd.DataFrame({"legs": ["", value]}, dtype=object)
    original = frame.copy(deep=True)
    with pytest.raises(exception, match=message):
        normalize_leg_column(frame)
    pd.testing.assert_frame_equal(frame, original)


@pytest.mark.parametrize("column", ["legs", "n_legs"])
def test_leg_counts_reject_a_units_cell(column):
    frame = pd.DataFrame({"legs": ["", 2], "n_legs": ["", 2]}, dtype=object)
    frame.loc[0, column] = "mm"
    with pytest.raises(ValueError, match=rf"{column} is a count and must have a blank units cell"):
        normalize_leg_column(frame)


@pytest.mark.parametrize("status, expected", [("failed", "failed"), ("pending", "pending"), ("passed", "passed")])
def test_compression_support_controls_detailing_without_changing_resistance(status, expected):
    face = SimpleNamespace(DCR=0.5)
    beam = SimpleNamespace(
        flexure_checks=[SimpleNamespace(complies=True, bottom=face, top=face)],
        shear_checks=[SimpleNamespace(DCR=0.5)],
        warnings=[],
        compression_detailing=SimpleNamespace(status=status),
        _stirrups_optional=True,
    )
    assert verification_status(beam) == {"resistance": "passed", "detailing": expected}


def _beam():
    return RectangularBeam(
        label="V1",
        concrete=Concrete_ACI_318_19(name="C25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN420", f_y=420 * MPa),
        width=30 * cm,
        height=50 * cm,
        c_c=25 * mm,
    )


def test_unchecked_beam_public_status_is_pending():
    assert _beam().verification_status == {"resistance": "pending", "detailing": "pending"}


@pytest.mark.parametrize("count", [True, 1.5])
def test_transverse_alias_rejects_invalid_legacy_count_before_mutating_reinforcement(count):
    beam = _beam()
    previous = beam.reinforcement.transverse
    with pytest.raises(TypeError, match="n_stirrups must be an integer"):
        beam.set_transverse_rebar(n_stirrups=count, legs=2, d_b=8 * mm, s_l=20 * cm)
    assert beam.reinforcement.transverse == previous
