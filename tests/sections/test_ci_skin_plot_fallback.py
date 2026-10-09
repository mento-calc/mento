"""Una falla de piel y otra de jaula conservan el modelo de cálculo rotulado."""

import matplotlib.pyplot as plt
import pytest

import mento.cage_detailing as cage
from mento import Forces
from mento.cage_detailing import CageDetailingError
from mento.i18n import translate
from mento.units import kNm
from tests.sections.test_skin_reinforcement import beam


def test_plot_fallback_reports_skin_and_base_failure_without_inventing_skin(monkeypatch):
    b = beam()
    b.check_flexure([Forces(M_y=100 * kNm)])
    calls = []

    def unavailable(subject, *, include_skin=True):
        assert subject is b
        calls.append(include_skin)
        raise CageDetailingError(
            "skin clash" if include_skin else "base clash", reason="skin" if include_skin else "layout"
        )

    monkeypatch.setattr(cage, "build_cage_detailing", unavailable)
    with pytest.warns(UserWarning) as caught:
        fig = b.plot(show=False)
    try:
        messages = [str(w.message) for w in caught]
        assert any("Cage detailing is not feasible: base clash" in message for message in messages)
        assert any("Skin detailing is not feasible: skin clash" in message for message in messages)
        assert calls[:2] == [True, False]
        assert not any(p.get_gid() in ("skin_bar", "mounting_bar") for p in fig.axes[0].patches)
        assert any(
            translate("Calculation model only · cage detailing not feasible") in t.get_text() for t in fig.axes[0].texts
        )
    finally:
        plt.close(fig)
