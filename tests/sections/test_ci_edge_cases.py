"""Estados límite de entradas y sujeción: no acreditar una jaula no verificada."""

from dataclasses import replace
from types import SimpleNamespace

import pandas as pd
import pytest

from mento import cage_detailing as cage
from mento.compression_detailing import check_compression_detailing
from mento.design_results import _transverse_stirrup_count, cage_legs, describe_stirrup_cage
from mento.verification import normalize_leg_column, verification_status
from mento.units import mm
from tests.sections.test_compression_detailing import beam, face_geometry
from tests.sections.test_r3_C2 import en_beam


@pytest.mark.parametrize("value", ["not a number", object()])
def test_invalid_leg_text_is_reported_with_row(value):
    with pytest.raises(ValueError, match="legs must be an integer.*row 1"):
        normalize_leg_column(pd.DataFrame({"legs": ["", value]}))


def test_canonical_leg_units_must_also_be_blank():
    with pytest.raises(ValueError, match="n_legs is a count"):
        normalize_leg_column(pd.DataFrame({"legs": ["", 4], "n_legs": ["mm", 4]}))


@pytest.mark.parametrize("n,legs,error", [(True, None, TypeError), (-1, None, ValueError), (None, 1, ValueError)])
def test_public_count_validation_rejects_invalid_stirrup_counts(n, legs, error):
    with pytest.raises(error):
        _transverse_stirrup_count(n, legs)


@pytest.mark.parametrize("describe", [cage_legs, describe_stirrup_cage])
def test_boolean_is_not_a_cage_leg_count(describe):
    with pytest.raises(TypeError, match="n_legs must be an integer"):
        describe(True)


def test_required_compression_without_geometry_remains_pending():
    b = beam()
    b._compression_faces = {"top"}
    result = check_compression_detailing(b, unavailable="candidate rejected")
    assert result.status == "pending" and result.reason == "candidate rejected"


def test_unmodelled_bend_cannot_pass_compression_support():
    b = beam()
    b._compression_faces = {"top"}
    result = check_compression_detailing(b, replace(b.section_geometry, bend_supported=False))
    assert result.status == "pending" and result.reason == "unsupported_bend"


def test_compressed_face_without_first_row_remains_pending():
    b = beam()
    b._compression_faces = {"top"}
    result = check_compression_detailing(b, replace(b.section_geometry, bars=()))
    assert result.status == "pending"
    assert result.faces[0].reasons == ("first_row_missing",)


def test_shifted_compression_bar_is_not_a_supported_corner():
    b = beam()
    b._compression_faces = {"top"}
    g = face_geometry(b, [60, 160], [(0, 1)])
    result = check_compression_detailing(b, replace(g, bars=(replace(g.bars[0], y=500 * mm), g.bars[1])))
    assert result.status == "failed"
    assert "corner_bar_unbraced" in result.faces[0].reasons


def test_a_single_missing_corner_does_not_invent_a_two_sided_gap():
    b = beam()
    b._compression_faces = {"top"}
    g = face_geometry(b, [60, 160], [(0, 1)])
    result = check_compression_detailing(b, replace(g, bars=(replace(g.bars[0], x=70 * mm), g.bars[1])))
    assert result.status == "failed"
    assert result.faces[0].maximum_clear_distance == 0 * mm


def test_compression_without_an_evaluator_is_pending_in_detailing():
    face = SimpleNamespace(DCR=0.2)
    b = SimpleNamespace(
        flexure_checks=[SimpleNamespace(complies=True, bottom=face, top=face)],
        shear_checks=[SimpleNamespace(DCR=0.2)],
        warnings=[],
        _compression_faces={"top"},
        _stirrups_optional=True,
    )
    assert verification_status(b) == {"resistance": "passed", "detailing": "pending"}


def test_water_fill_respects_a_centre_spacing_cap():
    g = beam().section_geometry
    bar = replace(g.bars[0], d_b=10 * mm)
    row = tuple(replace(bar, x=x * mm) for x in (10, 30, 70))
    resistant, mounting = cage._supported_layer(row, [(0, 1, 10), (80, -1, 10)], bar, 10, 30, 10, 10)
    assert not mounting
    assert [b.x.to(mm).magnitude for b in resistant] == pytest.approx([10, 40, 70])


def test_too_many_entered_legs_are_rejected_before_compression_search():
    b = beam(width=20)
    b.set_transverse_rebar(legs=20, d_b=10 * mm, s_l=150 * mm)
    b._compression_faces = {"top"}
    with pytest.raises(cage.CageDetailingError, match="legs cannot accommodate"):
        cage.build_cage_detailing(b)


def test_absent_bend_rule_is_a_pending_scope_error(monkeypatch):
    b = beam()
    monkeypatch.setattr(cage, "design_code", lambda _: SimpleNamespace(stirrup_bend_inner_diameter=None))
    with pytest.raises(cage.CageDetailingError) as error:
        cage._build_candidate(b, b.section_geometry)
    assert error.value.reason == "unsupported_bend"


def test_en_pending_compression_emits_its_scope_warning():
    from mento.design_warnings import compression_detailing_warnings

    b = en_beam()
    b._compression_faces = {"top"}
    assert [w.code for w in compression_detailing_warnings(b)] == ["compression_detailing_en_pending"]


def test_en_unbuildable_compressed_cage_reports_the_fit_error():
    b = en_beam()
    b.set_longitudinal_rebar_top(n1=30, d_b1=16 * mm)
    b._compression_faces = {"top"}
    with pytest.raises(cage.CageDetailingError, match="cannot fit"):
        cage.build_cage_detailing(b)


@pytest.mark.parametrize(
    "fault,message",
    [
        ("height", "section height"),
        ("closed", "stirrup branch or bend"),
        ("spacing", "insufficient clear spacing"),
    ],
)
def test_retained_second_layer_cannot_break_cage_fit(fault, message):
    b = beam()
    g = cage._build_candidate(b, b.section_geometry)
    bar = g.bars_on("bottom", 1)[0]
    if fault == "height":
        extra = replace(bar, layer=2, y=-20 * mm)
    elif fault == "closed":
        extra = replace(bar, layer=2, x=g.width / 2, y=g.stirrups[0].y_top)
    else:
        extra = replace(bar, layer=2, y=bar.y + 1 * mm)
    with pytest.raises(cage.CageDetailingError, match=message):
        cage._build_candidate(b, replace(g, bars=g.bars + (extra,)))


def test_retained_second_layer_cannot_intersect_an_open_leg():
    b = beam()
    b.set_transverse_rebar(legs=3, d_b=10 * mm, s_l=150 * mm)
    g = cage._build_candidate(b, b.section_geometry)
    bar = g.bars_on("bottom", 1)[0]
    # Más barras que la primera capa: no se pueden alinear automáticamente.
    extras = tuple(replace(bar, layer=2, x=g.crossties[0].x, y=200 * mm) for _ in range(5))
    with pytest.raises(cage.CageDetailingError, match="open leg"):
        cage._build_candidate(b, replace(g, bars=g.bars + extras))


def test_plot_marks_unverified_en_compression_support():
    import matplotlib.pyplot as plt

    from mento import Forces, kN, kNm
    from mento.i18n import translate

    b = en_beam()
    forces = [Forces(M_y=150 * kNm, V_z=50 * kN)]
    b.check_flexure(forces)
    b.check_shear(forces)
    assert b.compression_detailing.status == "pending"
    with pytest.warns(UserWarning, match="Required compression-bar support: pending"):
        fig = b.plot(show=False)
    caption = translate("Required compression-bar support: {status}", status=translate("pending"))
    assert any(caption in text.get_text() for text in fig.axes[0].texts)
    plt.close(fig)


def test_search_fallback_preserves_geometry_without_claiming_support(monkeypatch):
    import mento.compression_detailing as compression

    b = beam(width=20)
    b.set_longitudinal_rebar_bot(n1=2, d_b1=16 * mm)
    b.set_longitudinal_rebar_top(n1=2, d_b1=16 * mm)
    b._compression_faces = {"top"}
    # El evaluador puede reprobar toda propuesta viable: la búsqueda devuelve
    # geometría para inspección, pero esa devolución no equivale a aprobación.
    g = face_geometry(b, [60, 160], [(0, 1)])
    failed = check_compression_detailing(b, replace(g, bars=(replace(g.bars[0], y=500 * mm), g.bars[1])))
    assert failed.status == "failed"
    monkeypatch.setattr(compression, "check_compression_detailing", lambda *args, **kwargs: failed)
    detail = cage.build_cage_detailing(b)
    assert detail.stirrups
    assert b.compression_detailing.status == "failed"


def test_open_leg_draws_only_explicit_hook_metadata():
    import matplotlib.pyplot as plt

    from mento.plots.sections import _add_crosstie
    from mento.section_geometry import Crosstie

    fig, ax = plt.subplots()
    tie = Crosstie(1, 300 * mm, 50 * mm, 550 * mm, hooks=(90, 135))
    _add_crosstie(ax, tie, 1.0)
    assert len(ax.patches) == 1 and ax.patches[0].get_gid() == "crosstie"
    assert [line.get_gid() for line in ax.lines] == ["crosstie_hook", "crosstie_hook"]
    assert ax.lines[0].get_xdata() == pytest.approx([30, 34])
    assert ax.lines[0].get_ydata() == pytest.approx([5, 5])
    assert ax.lines[1].get_xdata() == pytest.approx([30, 30 + 2**0.5 * 2])
    assert ax.lines[1].get_ydata() == pytest.approx([55, 55 - 2**0.5 * 2])
    plt.close(fig)
