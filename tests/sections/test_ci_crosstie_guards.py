"""Una traba incompleta o mal posicionada no acredita sujeción comprimida."""

from dataclasses import replace

import pytest

from mento.cage_detailing import CageDetailingError
from mento.crosstie_detailing import finalize_crossties, hook_curves, hook_points, hook_rule, tie_supports
from mento.units import inch, mm
from tests.sections.test_crosstie_detailing import subject


@pytest.fixture(scope="module")
def geometry():
    return subject().detailing_geometry


@pytest.mark.parametrize("diameter", [0.25 * inch, 1.25 * inch])
def test_imperial_diameters_outside_table_have_no_hook_rule(diameter):
    assert hook_rule("ACI 318-19", True, diameter) is None


def test_missing_bend_or_extension_has_no_drawable_hook(geometry):
    tie = geometry.crossties[0]
    assert hook_curves(replace(tie, bend_inner_diameter=None), geometry.stirrup_d_b) == ()
    assert hook_points(replace(tie, extension=None), geometry.stirrup_d_b) == ()


def test_large_diameter_90_hook_needs_twelve_diameter_extension(geometry):
    g = replace(geometry, stirrup_d_b=20 * mm)
    tie = replace(g.crossties[0], bend_inner_diameter=120 * mm, extension=120 * mm)
    assert not tie_supports(tie.engaged_bars[0], tie, g, "CIRSOC 201-25", False)


def test_short_tie_cannot_support_or_be_finalized(geometry):
    tie = geometry.crossties[0]
    tie = replace(tie, y_top=tie.y_bottom + 10 * mm)
    assert not tie_supports(tie.engaged_bars[0], tie, geometry, "ACI 318-19", False)
    with pytest.raises(CageDetailingError, match="section height") as error:
        finalize_crossties(replace(geometry, crossties=(tie,)))
    assert error.value.reason == "bend"


def test_engaged_bar_must_exist_in_section(geometry):
    tie = geometry.crossties[0]
    absent = replace(tie.engaged_bars[0], x=-100 * mm)
    tie = replace(tie, engaged_bars=(absent, tie.engaged_bars[1]))
    assert not tie_supports(absent, tie, geometry, "ACI 318-19", False)


def test_real_bar_outside_hook_cannot_receive_support(geometry):
    tie = geometry.crossties[0]
    original = tie.engaged_bars[0]
    shifted = replace(original, x=original.x + 100 * mm)
    g = replace(geometry, bars=tuple(shifted if b == original else b for b in geometry.bars))
    tie = replace(tie, engaged_bars=(shifted, tie.engaged_bars[1]))
    assert not tie_supports(shifted, tie, g, "ACI 318-19", False)


def test_finalization_rejects_an_end_without_a_longitudinal_bar(geometry):
    with pytest.raises(CageDetailingError, match="engage one peripheral"):
        finalize_crossties(replace(geometry, bars=(), mounting_bars=()))
