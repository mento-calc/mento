"""ASTM bar sizes: ``bar_designation`` and its inverse ``bar_diameter``."""

import pytest

from mento import bar_designation, bar_diameter, cm, inch, mm
from mento import rebar
from mento.bar_sizes import ASTM_BAR_DIAMETERS


@pytest.mark.parametrize(
    "number, inches",
    [
        (3, 0.375),
        (4, 0.5),
        (5, 0.625),
        (6, 0.75),
        (7, 0.875),
        (8, 1.0),
        (9, 1.128),
        (10, 1.27),
        (11, 1.41),
        (14, 1.693),
    ],
)
def test_each_astm_size_round_trips(number: int, inches: float) -> None:
    assert bar_diameter(number).to(inch).magnitude == pytest.approx(inches)
    assert bar_designation(inches * inch) == f"#{number}"


def test_a_diameter_is_recognised_in_any_length_unit() -> None:
    # 19.05 mm is #6 exactly; a value carried through mm and back still is.
    assert bar_designation(19.05 * mm) == "#6"
    assert bar_designation((0.625 * inch).to(cm)) == "#5"


def test_a_diameter_that_is_no_astm_size_is_written_by_its_diameter() -> None:
    """A bar entered by hand is still shown, never refused: Ø0.70", and a metric 16 mm as Ø0.63"."""
    assert bar_designation(0.7 * inch) == 'Ø0.70"'
    assert bar_designation(16 * mm) == 'Ø0.63"'


def test_an_unknown_size_number_raises_a_clear_error() -> None:
    with pytest.raises(ValueError, match="#12 is not an ASTM A615 bar size"):
        bar_diameter(12)


def test_the_imperial_catalogue_of_the_rebar_search_is_the_astm_table() -> None:
    assert list(ASTM_BAR_DIAMETERS) == [3, 4, 5, 6, 7, 8, 9, 10, 11, 14]
    assert rebar.bar_designation is bar_designation
    assert rebar.bar_diameter is bar_diameter
