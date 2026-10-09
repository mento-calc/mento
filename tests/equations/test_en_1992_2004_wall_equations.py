"""EN 1992-1-1 wall equations, §6.2.3(3) Note 3 and §9.6, against values worked by hand."""

import pytest

from mento.codes.en_1992_2004.equations import wall as wall_eq


class TestCompressionChordCoefficient:
    """alpha_cw as mento reads it for a wall: 1, or 2.5 (1 - sigma/f_cd) past half of f_cd."""

    def test_no_axial_load(self) -> None:
        assert wall_eq.compression_chord_coefficient(0.0, 16.667) == 1.0

    def test_tension_keeps_one(self) -> None:
        # 2.5 (1 + 1.25/16.667) = 2.69, capped at 1.
        assert wall_eq.compression_chord_coefficient(-1.25, 16.667) == 1.0

    def test_moderate_compression_takes_no_increase(self) -> None:
        # The Note would give 1 + 2.5/16.667 = 1.15; mento keeps 1.
        assert wall_eq.compression_chord_coefficient(2.5, 16.667) == 1.0

    def test_half_of_f_cd_is_the_edge(self) -> None:
        assert wall_eq.compression_chord_coefficient(10.0, 20.0) == pytest.approx(1.0)

    def test_high_compression_reduces_the_strut(self) -> None:
        # 2.5 (1 - 15/16.6667) = 2.5 x 0.1 = 0.25
        assert wall_eq.compression_chord_coefficient(15.0, 50 / 3) == pytest.approx(0.25)

    def test_floored_at_zero(self) -> None:
        assert wall_eq.compression_chord_coefficient(20.0, 16.667) == 0.0


class TestReinforcementLimits:
    def test_vertical_minimum_is_0_002_t(self) -> None:
        # §9.6.2(1): 0.002 A_c; per metre of a 200 mm wall, 0.4 mm²/mm = 4 cm²/m.
        assert wall_eq.min_vertical_reinforcement(200.0) == pytest.approx(0.4)

    def test_vertical_maximum_is_0_04_t(self) -> None:
        assert wall_eq.max_vertical_reinforcement(200.0) == pytest.approx(8.0)

    def test_horizontal_minimum_takes_a_quarter_of_the_vertical(self) -> None:
        # 2xØ12/200 on a 200 mm wall: A_sv = 1.131 mm²/mm, 0.25 A_sv = 0.283 > 0.001 t = 0.2.
        assert wall_eq.min_horizontal_reinforcement(1.131, 200.0) == pytest.approx(0.28275)

    def test_horizontal_minimum_floor_is_0_001_t(self) -> None:
        # A light vertical mesh: 0.25 x 0.4 = 0.1 < 0.001 x 200 = 0.2.
        assert wall_eq.min_horizontal_reinforcement(0.4, 200.0) == pytest.approx(0.2)


class TestSpacing:
    def test_vertical_spacing_thin_wall(self) -> None:
        # §9.6.2(3): 3 x 120 = 360 mm < 400 mm.
        assert wall_eq.max_vertical_spacing(120.0) == pytest.approx(360.0)

    def test_vertical_spacing_capped_at_400(self) -> None:
        assert wall_eq.max_vertical_spacing(200.0) == pytest.approx(400.0)

    def test_horizontal_spacing(self) -> None:
        # §9.6.3(2)
        assert wall_eq.MAX_HORIZONTAL_SPACING == 400.0

    def test_a_wall_is_four_times_as_long_as_it_is_thick(self) -> None:
        # §5.3.1(7)
        assert wall_eq.MIN_LENGTH_TO_THICKNESS == 4.0
