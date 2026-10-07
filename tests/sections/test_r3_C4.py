import pytest
from mento.design_results import cage_legs, describe_stirrup_cage


@pytest.mark.parametrize("legs", [1, 3, 9])
def test_public_helpers_reject_odd_cages(legs):
    messages = []
    for helper in (cage_legs, describe_stirrup_cage):
        with pytest.raises(ValueError, match="odd legs .*not modelled yet") as error:
            helper(legs)
        messages.append(str(error.value))
    assert messages[0] == messages[1]
