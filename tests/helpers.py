"""Helpers shared by test modules: pint adapters for the float-only ACI 318-19 flexure functions.

The validated references are quoted in cm² and kip·ft, so the tests stay in those units
and convert at the call -- what the design path does, now that the calculation itself
runs in floats (ADR-0005). Used by ``tests/elements/test_beam.py`` and
``tests/validation/test_beam_flexure_validated.py``.
"""

from pint import Quantity

from mento.beam import RectangularBeam
from mento.codes.ACI_318_19_beam import (
    _calculate_flexural_reinforcement_ACI_318_19,
    _determine_nominal_moment_double_reinf_ACI_318_19,
    _determine_nominal_moment_simple_reinf_ACI_318_19,
)
from mento.codes.check_state import to_display
from mento.precompute import CANONICAL


def _flexural_reinforcement_in_pint(
    beam: RectangularBeam, M_u: Quantity, d: Quantity, d_prima: Quantity
) -> tuple[Quantity, Quantity, Quantity, Quantity, float, bool, bool]:
    """Pint adapter for the float contract of the ACI reinforcement helper.

    The validated references below are quoted in cm2 and kip*ft, so the tests
    stay in those units and convert at the call -- exactly what the design path
    does now that the calculation itself runs in floats.
    """
    imperial = beam.concrete.is_imperial
    canonical = CANONICAL[imperial]
    A_s_min, A_s_max, A_s_final, A_s_comp, c_d, A_s_bool, doubly, _A_s_calc = (
        _calculate_flexural_reinforcement_ACI_318_19(
            beam,
            M_u.to(canonical["moment"]).magnitude,
            d.to(canonical["length"]).magnitude,
            d_prima.to(canonical["length"]).magnitude,
        )
    )
    return (
        to_display(A_s_min, "area", imperial),
        to_display(A_s_max, "area", imperial),
        to_display(A_s_final, "area", imperial),
        to_display(A_s_comp, "area", imperial),
        c_d,
        A_s_bool,
        doubly,
    )


def _required_flexural_steel_in_pint(
    beam: RectangularBeam, M_u: Quantity, d: Quantity, d_prima: Quantity
) -> tuple[Quantity, Quantity, Quantity, Quantity]:
    """``(A_s_min, A_s_max, A_s_final, A_s_calc)`` of the ACI reinforcement helper, in pint.

    Same call as :func:`_flexural_reinforcement_in_pint`, but keeps ``A_s_calc``,
    the steel the moment alone asks for, before any minimum. A reference that
    solves a T-beam as a rectangle of width b_f prints that number, while its
    minimum stays on b_w, which a rectangular section of width b_f cannot
    reproduce.
    """
    imperial = beam.concrete.is_imperial
    canonical = CANONICAL[imperial]
    A_s_min, A_s_max, A_s_final, _A_s_comp, _c_d, _A_s_bool, _doubly, A_s_calc = (
        _calculate_flexural_reinforcement_ACI_318_19(
            beam,
            M_u.to(canonical["moment"]).magnitude,
            d.to(canonical["length"]).magnitude,
            d_prima.to(canonical["length"]).magnitude,
        )
    )
    return (
        to_display(A_s_min, "area", imperial),
        to_display(A_s_max, "area", imperial),
        to_display(A_s_final, "area", imperial),
        to_display(A_s_calc, "area", imperial),
    )


def _nominal_moment_double_in_pint(
    beam: RectangularBeam, A_s: Quantity, d: Quantity, d_prime: Quantity, A_s_prime: Quantity
) -> Quantity:
    """Pint adapter for the doubly-reinforced nominal moment, same reason."""
    imperial = beam.concrete.is_imperial
    canonical = CANONICAL[imperial]
    return to_display(
        _determine_nominal_moment_double_reinf_ACI_318_19(
            beam,
            A_s.to(canonical["area"]).magnitude,
            d.to(canonical["length"]).magnitude,
            d_prime.to(canonical["length"]).magnitude,
            A_s_prime.to(canonical["area"]).magnitude,
        ),
        "moment",
        imperial,
    )


def _nominal_moment_simple_in_pint(beam: RectangularBeam, A_s: Quantity, d: Quantity) -> Quantity:
    """Pint adapter for the simply-reinforced nominal moment, same reason."""
    imperial = beam.concrete.is_imperial
    canonical = CANONICAL[imperial]
    return to_display(
        _determine_nominal_moment_simple_reinf_ACI_318_19(
            beam, A_s.to(canonical["area"]).magnitude, d.to(canonical["length"]).magnitude
        ),
        "moment",
        imperial,
    )


def us(value: float, metric_unit: str, us_unit: str) -> float:
    """A reference quoted in SI, in the US customary unit an imperial section's tables print.

    The imperial beam tests were written when those tables printed SI, so their
    references are in cm² and kN; converting the reference, rather than
    rewriting it, keeps the validated number in sight.
    """
    return float(Quantity(value, metric_unit).to(us_unit).magnitude)
