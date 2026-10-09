"""Published EN 1992-1-1:2004 Table 3.1 values (rounded to 0.1 MPa)."""

import pytest

from mento import Concrete_EN_1992_2004
from mento.units import MPa


@pytest.mark.parametrize(
    "fck, published_fctm", [(25, 2.6), (50, 4.1), (55, 4.2), (60, 4.4), (70, 4.6), (80, 4.8), (90, 5.0)]
)
def test_en_tensile_strength_matches_the_published_normal_and_high_strength_table(fck, published_fctm):
    concrete = Concrete_EN_1992_2004(name=f"C{fck}", f_c=fck * MPa)
    assert concrete.f_ctm.to(MPa).magnitude == pytest.approx(published_fctm, abs=0.05)
