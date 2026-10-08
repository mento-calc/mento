import pytest
from mento.design_results import cage_legs, describe_stirrup_cage


def test_one_leg_cannot_form_a_perimeter():
    for helper in (cage_legs, describe_stirrup_cage):
        with pytest.raises(ValueError, match="At least two"):
            helper(1)


@pytest.mark.parametrize("legs", [3, 7, 9])
def test_odd_helpers_keep_one_closed_perimeter_and_open_legs(legs):
    closed, opened = cage_legs(legs)
    assert closed == ((0, legs - 1),)
    assert opened == tuple(range(1, legs - 1))
    assert "open leg" in describe_stirrup_cage(legs, "en")
