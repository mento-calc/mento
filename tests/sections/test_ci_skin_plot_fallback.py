"""Una falla de piel y otra de jaula conservan el modelo de cálculo; la causa va en beam.warnings."""

import warnings

import matplotlib.pyplot as plt

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
    # The drawing falls back to the calculation model silently; beam.warnings says why.
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        fig = b.plot(show=False)
    try:
        assert calls[:2] == [True, False]
        assert not any(p.get_gid() in ("skin_bar", "mounting_bar") for p in fig.axes[0].patches)
        texts = [t.get_text() for t in fig.axes[0].texts]
        assert not any(translate("Calculation model only · cage detailing not feasible") in t for t in texts)
        assert not any("clash" in t for t in texts)
        infeasible = [w for w in b.warnings if w.code == "cage_detailing_infeasible"]
        assert infeasible and "base clash" in infeasible[0].message
    finally:
        plt.close(fig)
