"""Una búsqueda por estado, truncamiento explícito y fuerzas no obsoletas."""

import itertools
import pytest
from mento import Concrete_ACI_318_19, RectangularBeam, SteelBar, Forces
from mento.units import cm, mm, MPa, kNm, kN
from mento import cage_detailing as cage


def subject(width=60, count=7):
    b = RectangularBeam(
        concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN420", f_y=420 * MPa),
        width=width * cm,
        height=60 * cm,
        c_c=30 * mm,
    )
    b.set_longitudinal_rebar_bot(n1=count, d_b1=20 * mm)
    b.set_longitudinal_rebar_top(n1=count, d_b1=16 * mm)
    b.set_transverse_rebar(legs=3 if width == 60 else 6, d_b=10 * mm, s_l=15 * cm)
    b.check([Forces(M_y=-1500 * kNm, V_z=80 * kN)])
    return b


def test_one_search_per_state_and_invalidation(monkeypatch):
    b = subject()
    original = cage._search_cage_detailing
    calls = []

    def counted(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(cage, "_search_cage_detailing", counted)
    b.verification_status
    b.warnings
    b.compression_detailing
    b.detailing_geometry
    assert len(calls) == 1
    b.set_transverse_rebar(legs=4, d_b=10 * mm, s_l=15 * cm)
    assert b.compression_detailing.reason == "flexure_not_checked"
    assert not b._compression_faces
    assert len(b.detailing_geometry.stirrups) == 1
    assert len(calls) == 2


def test_one_skin_pass_per_state_and_invalidation(monkeypatch):
    b = subject()
    original = cage._complete_skin_detail
    calls = []

    def counted(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(cage, "_complete_skin_detail", counted)
    b.verification_status
    b.warnings
    b.skin_verification_status
    first = b.detailing_geometry
    assert len(calls) == 1
    b.set_skin_rebar(10 * mm, 2, "total")
    assert len(b.detailing_geometry.skin_bars) == 4
    assert len(calls) == 2
    b.clear_skin_rebar()
    assert b.detailing_geometry == first
    assert len(calls) == 3


def wide_cage(monkeypatch, clock):
    """Jaula ancha con el reloj de la búsqueda dado; ramas probadas, una lista por búsqueda."""
    b = subject(150, 22)
    b.check([Forces(M_y=2500 * kNm, V_z=300 * kN)])
    assert b._compression_faces == {"top"}
    search, candidate = cage._search_cage_detailing, cage._build_candidate
    searches = []

    def counted_search(*args, **kwargs):
        searches.append([])
        return search(*args, **kwargs)

    def counted_candidate(beam, geometry, **kwargs):
        if not kwargs["include_skin"]:
            searches[-1].append(len(geometry.leg_x))
        return candidate(beam, geometry, **kwargs)

    monkeypatch.setattr(cage, "_search_cage_detailing", counted_search)
    monkeypatch.setattr(cage, "_build_candidate", counted_candidate)
    monkeypatch.setattr(cage, "perf_counter", clock)
    return b, searches


def test_wide_cage_finishes_when_the_budget_is_not_spent(monkeypatch):
    b, searches = wide_cage(monkeypatch, lambda: 0)
    assert b.verification_status["detailing"] in ("failed", "pending")
    assert not any(w.code == "cage_detailing_pending" for w in b.warnings)
    placed = len(b.detailing_geometry.leg_x)
    assert placed > 6
    assert searches == [list(range(6, placed + 1))]


def test_wide_cage_reports_bounded_search(monkeypatch):
    # Un segundo por lectura del reloj: el presupuesto de 2 s alcanza para dos
    # candidatos, y la lectura siguiente no vuelve a gastarlo.
    b, searches = wide_cage(monkeypatch, itertools.count().__next__)
    assert b.verification_status["detailing"] == "pending"
    assert any(w.code == "cage_detailing_pending" for w in b.warnings)
    assert b.verification_status["detailing"] == "pending"
    assert searches == [[6, 7]]


def test_truncation_is_pending_and_cached(monkeypatch):
    b = subject()
    ticks = iter([0, 3])
    monkeypatch.setattr(cage, "perf_counter", lambda: next(ticks))
    with pytest.raises(cage.CageDetailingError) as error:
        cage.build_cage_detailing(b, include_skin=False)
    assert error.value.reason == "compression_support_search"
    assert b.verification_status["detailing"] == "pending"
    assert any(w.code == "cage_detailing_pending" for w in b.warnings)


@pytest.mark.parametrize("legs", [3, 4, 5])
def test_second_layer_does_not_intersect_open_legs(legs):
    b = subject(40, 7)
    b.set_longitudinal_rebar_bot(n1=3, d_b1=20 * mm, n3=3, d_b3=20 * mm)
    b.set_longitudinal_rebar_top(n1=3, d_b1=16 * mm)
    b.set_transverse_rebar(legs=legs, d_b=10 * mm, s_l=15 * cm)
    b.check([Forces(M_y=250 * kNm, V_z=80 * kN)])
    original = b.section_geometry.to_dict("mm")
    geometry = b.detailing_geometry
    assert len(geometry.bars_on("bottom", 2)) == 3
    assert original == b.section_geometry.to_dict("mm")
    assert not any(w.code == "cage_detailing_infeasible" for w in b.warnings)


def test_candidates_use_one_perimeter_and_increasing_legs(monkeypatch):
    b = subject(150, 22)
    b.set_transverse_rebar(legs=16, d_b=8 * mm, s_l=15 * cm)
    b.check([Forces(M_y=2500 * kNm, V_z=300 * kN)])
    seen = []

    def candidate(beam, geometry, **kwargs):
        assert len(geometry.stirrups) == 1
        assert len(geometry.crossties) == len(geometry.leg_x) - 2
        seen.append(len(geometry.leg_x))
        raise cage.CageDetailingError("isolated search ordering")

    monkeypatch.setattr(cage, "_build_candidate", candidate)
    monkeypatch.setattr(cage, "perf_counter", lambda: 0)
    with pytest.raises(cage.CageDetailingError, match="isolated search ordering"):
        cage._search_cage_detailing(b)
    assert seen == list(range(16, max(seen) + 1))
