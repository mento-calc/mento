"""Sujeción con trabas reales: mandril, colas, alternancia y crédito seccional."""

from dataclasses import replace
import math

import matplotlib.pyplot as plt
import pytest

from mento import Concrete_ACI_318_19, Forces, RectangularBeam, SteelBar
from mento.cage_detailing import CageDetailingError
from mento.compression_detailing import check_compression_detailing
from mento.crosstie_detailing import finalize_crossties, hook_distance, hook_points, hook_rule, tie_supports
from mento.units import MPa, cm, inch, kN, kNm, mm


def subject():
    b = RectangularBeam(
        concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN420", f_y=420 * MPa),
        width=80 * cm,
        height=60 * cm,
        c_c=30 * mm,
    )
    b.set_longitudinal_rebar_bot(n1=7, d_b1=25 * mm)
    b.set_longitudinal_rebar_top(n1=7, d_b1=25 * mm)
    b.set_transverse_rebar(legs=7, d_b=10 * mm, s_l=15 * cm)
    b.check([Forces(M_y=2500 * kNm, V_z=80 * kN), Forces(M_y=-2500 * kNm, V_z=80 * kN)])
    assert b._compression_faces == {"top", "bot"}
    return b


def test_both_faces_are_supported_by_one_perimeter_and_real_crossties():
    b = subject()
    entered = b.reinforcement
    g = b.detailing_geometry
    assert len(g.stirrups) == 1 and len(g.crossties) == 5
    assert check_compression_detailing(b, g).status == "passed"
    assert b.reinforcement == entered
    assert all(t.hooks == (135, 90) and t.alternate_hooks for t in g.crossties)
    assert all(
        tie_supports(bar, tie, g, b.concrete.design_code, False) for tie in g.crossties for bar in tie.engaged_bars
    )
    assert "crosstie_alternation_required" in [w.code for w in b.warnings]
    assert check_compression_detailing(b, replace(g, crossties=())).status == "failed"


@pytest.mark.parametrize(
    "changes",
    [
        {"extension": None},
        {"extension": 74 * mm},
        {"extension": math.nan * mm},
        {"bend_inner_diameter": 39 * mm},
        {"bend_inner_diameter": math.nan * mm},
        {"alternate_hooks": False},
        {"engaged_bars": ()},
        {"side": 0},
        {"hooks": (90, 90)},
    ],
)
def test_angle_metadata_or_incomplete_hooks_cannot_brace_compression_bars(changes):
    b = subject()
    g = b.detailing_geometry
    tie = g.crossties[0]
    assert not tie_supports(tie.engaged_bars[0], replace(tie, **changes), g, b.concrete.design_code, False)


def test_alternating_phase_has_real_curves_and_no_longitudinal_bar_collisions():
    b = subject()
    g = b.detailing_geometry
    for tie in g.crossties:
        for phase in (tie, replace(tie, hooks=(90, 135))):
            paths = hook_points(phase, g.stirrup_d_b)
            assert len(paths) == 2
            assert tuple(len(p) for p in paths) in ((29, 20), (20, 29))
            for bar in g.bars + g.mounting_bars:
                assert hook_distance(bar, phase, g.stirrup_d_b) >= (bar.d_b + g.stirrup_d_b).to(mm).magnitude / 2 - 1e-6
    assert finalize_crossties(g) == g


def test_overlong_tail_is_rejected_instead_of_drawn_outside_cover():
    g = subject().detailing_geometry
    long = replace(g.crossties[0], extension=2000 * mm)
    with pytest.raises(CageDetailingError, match="cover"):
        finalize_crossties(replace(g, crossties=(long,)))


def test_tail_crossing_a_real_longitudinal_bar_is_rejected():
    g = subject().detailing_geometry
    tie = g.crossties[0]
    # Un punto interior de la cola de 135°: choque exacto, sin aproximar el arco.
    path = hook_points(tie, g.stirrup_d_b)[0]
    x, y = ((path[-2][i] + path[-1][i]) / 2 for i in range(2))
    clash = replace(g.bars[0], x=x * mm, y=y * mm, layer=2)
    with pytest.raises(CageDetailingError, match="hook or tail"):
        finalize_crossties(replace(g, bars=g.bars + (clash,)))


@pytest.mark.parametrize(
    "code,imperial,diameter,bend,tail",
    [
        ("ACI 318-19", False, 10 * mm, 40, 75),
        ("CIRSOC 201-25", False, 20 * mm, 120, 120),
        ("ACI 318-19", True, 0.375 * inch, 38.1, 76.2),
        ("ACI 318-19", True, 0.75 * inch, 114.3, 114.3),
    ],
)
def test_primary_table_dimensions_without_extrapolation(code, imperial, diameter, bend, tail):
    mandrel, extension = hook_rule(code, imperial, diameter)
    assert mandrel.to(mm).magnitude == pytest.approx(bend)
    assert extension.to(mm).magnitude == pytest.approx(tail)


@pytest.mark.parametrize(
    "code,diameter", [("EN 1992-2004", 10 * mm), ("CIRSOC 201-25", 8 * mm), ("ACI 318-19", 18 * mm)]
)
def test_unmodelled_rules_are_not_silently_certified(code, diameter):
    assert hook_rule(code, False, diameter) is None


def test_plot_and_export_publish_hook_geometry_and_alternation():
    b = subject()
    fig = b.plot(show=False)
    try:
        # One band per crosstie, its two hooks part of it; the alternation is a warning, not a caption.
        ties = b.detailing_geometry.crossties
        bands = [p for p in fig.axes[0].patches if p.get_gid() == "crosstie"]
        assert len(bands) == len(ties) == 5
        for band, tie in zip(bands, ties):
            xs, ys = band.get_xy()[:, 0], band.get_xy()[:, 1]
            assert xs.min() < tie.x.to("cm").magnitude < xs.max()
            assert ys.min() < tie.y_bottom.to("cm").magnitude and tie.y_top.to("cm").magnitude < ys.max()
        assert not fig.axes[0].lines
        assert any(w.code == "crosstie_alternation_required" for w in b.warnings)
        assert not any("135°/90°" in text.get_text() for text in fig.axes[0].texts)
        data = b.detailing_geometry.to_dict("mm")
        assert all(t["alternate_hooks"] and len(t["engaged_bars"]) == 2 for t in data["crossties"])
    finally:
        plt.close(fig)
