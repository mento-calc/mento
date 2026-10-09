"""Published table values and explicit equation substitutions, not beam validation cases."""

import pytest

from mento.codes.en_1992_2004.equations.skin import adjusted_diameter, tabulated_skin_diameter


@pytest.mark.parametrize(
    "stress,values",
    [
        (160, (40, 32, 25)),
        (200, (32, 25, 16)),
        (240, (20, 16, 12)),
        (280, (16, 12, 8)),
        (320, (12, 10, 6)),
        (360, (10, 8, 5)),
        (400, (8, 6, 4)),
        (450, (6, 5, None)),
    ],
)
@pytest.mark.parametrize("column,width", list(enumerate((0.4, 0.3, 0.2))))
def test_table_7_2n(stress, values, column, width):
    if values[column] is None:
        with pytest.raises(ValueError, match="outside"):
            tabulated_skin_diameter(2 * stress, width)
    else:
        assert tabulated_skin_diameter(2 * stress, width) == values[column]


def test_upward_stress_rounding_and_half_main_stress():
    assert tabulated_skin_diameter(401, 0.3) == 16
    assert tabulated_skin_diameter(500, 0.3) == 12
    assert adjusted_diameter(12, 0.3 * 25 ** (2 / 3), 300, 43) == pytest.approx(9.2560847)


@pytest.mark.parametrize(
    "stress,width", [(0, 0.3), (-1, 0.3), (float("nan"), 0.3), (901, 0.3), (400, 0.25), (400, float("nan"))]
)
def test_unsupported_table_input(stress, width):
    with pytest.raises(ValueError):
        tabulated_skin_diameter(stress, width)
