"""La tabla debe rechazar una cantidad transversal ausente o con unidades."""

import pandas as pd
import pytest

from mento.beam_summary import BeamSummary
from mento.material import Concrete_ACI_318_19, SteelBar
from mento.units import MPa


@pytest.mark.parametrize(
    "columns,error",
    [
        ({"Label": ["", "V1"]}, "requires 'n_legs' or legacy 'ns'"),
        ({"Label": ["", "V1"], "ns": ["mm", 1]}, "ns is a count and must have a blank units cell"),
    ],
)
def test_summary_rejects_missing_count_or_a_length_as_legacy_count(columns, error):
    c = Concrete_ACI_318_19(name="H25", f_c=25 * MPa)
    s = SteelBar(name="ADN420", f_y=420 * MPa)
    with pytest.raises(ValueError, match=error):
        BeamSummary(c, s, pd.DataFrame(columns))
