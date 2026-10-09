"""Shared fixtures and test-suite configuration.

A fixture belongs here when more than one test module needs it and defines it
identically. Fixtures tied to a specific validated example — a beam from a
Calcpad case, a wall from a code table — stay in the module that asserts against
them, next to the expected values they were chosen to reproduce.
"""

from typing import Iterator

import matplotlib
import pytest

from mento.beam import RectangularBeam
from mento.material import Concrete, Concrete_ACI_318_19, Concrete_EN_1992_2004, SteelBar
from mento.i18n import get_language, set_language
from mento.units import MPa, cm, inch, ksi, psi

# Force a non-interactive backend for the whole suite, before any test module
# imports pyplot. Several modules exercise the plotting code, and without this
# they depend on whatever backend the machine happens to default to.
matplotlib.use("Agg")


@pytest.fixture(autouse=True)
def _restore_language() -> Iterator[None]:
    """Put the package language back after every test.

    ``mento.set_language`` is global, and the stirrup notation, the drawing and
    the summaries follow it; a test that switches to Spanish must not leave the
    English pins of the next one reading Spanish.
    """
    language = get_language()
    yield
    set_language(language)


@pytest.fixture()
def concrete_c25() -> Concrete:
    """Generic C25 concrete, with no design code attached."""
    return Concrete("C25")


@pytest.fixture()
def steel_b500s() -> SteelBar:
    """B500S reinforcement — the grade used by the EN examples."""
    return SteelBar(name="B500S", f_y=500 * MPa)


@pytest.fixture()
def steel() -> SteelBar:
    """ADN 420 reinforcement — the grade used by the ACI/CIRSOC examples."""
    return SteelBar(name="ADN 420", f_y=420 * MPa)


# ---------------------------------------------------------------------------
# Beam examples shared by tests/elements/test_beam.py and tests/validation/.
# tests/materials/test_rebar.py defines its own beam_example_imperial, with a
# different geometry, and its module-level fixture overrides this one there.
# ---------------------------------------------------------------------------


@pytest.fixture()
def beam_example_imperial() -> RectangularBeam:
    concrete = Concrete_ACI_318_19(name="C4", f_c=4000 * psi)
    steelBar = SteelBar(name="ADN 420", f_y=60 * ksi)
    section = RectangularBeam(
        label="V101",
        concrete=concrete,
        steel_bar=steelBar,
        width=10 * inch,
        height=16 * inch,
        c_c=1.5 * inch,
    )
    return section


@pytest.fixture()
def beam_example_EN_1992_2004_01() -> RectangularBeam:
    # Example from Calcpad EN 1992-1-1_2004 Beam Flexure 01 - Metric v2
    concrete = Concrete_EN_1992_2004(name="C25", f_c=25 * MPa)
    steelBar = SteelBar(name="B500S", f_y=500 * MPa)
    section = RectangularBeam(
        label="B_Example_EN_01",
        concrete=concrete,
        steel_bar=steelBar,
        width=20 * cm,
        height=60 * cm,
        c_c=2.6 * cm,
    )
    return section


# Shared fixture for ACI 318-19 flexure tests (test_1, test_2, test_3, over_reinforced_no_top).
# Each test that uses this fixture has its own dedicated calcpad in the "ACI 318-19 Beam Flexure 03_v3 - test_N.cpd" family.
@pytest.fixture()
def beam_example_flexure_ACI() -> RectangularBeam:
    concrete = Concrete_ACI_318_19(name="fc 4000", f_c=4000 * psi)
    steelBar = SteelBar(name="fy 60000", f_y=60 * ksi)
    section = RectangularBeam(
        concrete=concrete,
        steel_bar=steelBar,
        width=12 * inch,
        height=24 * inch,
        c_c=1.5 * inch,
        label="B-12x24",
    )
    return section
