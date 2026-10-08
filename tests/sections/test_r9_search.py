"""Una búsqueda por estado, truncamiento explícito y fuerzas no obsoletas."""
import time
import pytest
from mento import Concrete_ACI_318_19, RectangularBeam, SteelBar, Forces
from mento.units import cm, mm, MPa, kNm, kN
from mento import cage_detailing as cage


def subject(width=60, count=7):
    b = RectangularBeam(concrete=Concrete_ACI_318_19(name="H25", f_c=25*MPa),
                        steel_bar=SteelBar(name="ADN420", f_y=420*MPa), width=width*cm, height=60*cm, c_c=30*mm)
    b.set_longitudinal_rebar_bot(n1=count, d_b1=20*mm)
    b.set_longitudinal_rebar_top(n1=count, d_b1=16*mm)
    b.set_transverse_rebar(legs=3 if width==60 else 6, d_b=10*mm, s_l=15*cm)
    b.check([Forces(M_y=-1500*kNm, V_z=80*kN)])
    return b


def test_one_search_per_state_and_invalidation(monkeypatch):
    b=subject()
    original=cage._search_cage_detailing
    calls=[]
    def counted(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)
    monkeypatch.setattr(cage, "_search_cage_detailing", counted)
    b.verification_status
    b.warnings
    b.compression_detailing
    b.detailing_geometry
    assert len(calls)==1
    b.set_transverse_rebar(legs=4, d_b=10*mm, s_l=15*cm)
    assert b.compression_detailing.reason=="flexure_not_checked"
    assert not b._compression_faces
    assert len(b.detailing_geometry.stirrups)==1
    assert len(calls)==2


def test_wide_cage_finishes_or_reports_bounded_search():
    b=subject(150,22)
    b.check([Forces(M_y=2500*kNm, V_z=300*kN)])
    assert b._compression_faces == {"top"}
    start=time.perf_counter()
    status=b.verification_status
    assert time.perf_counter()-start < 5
    assert status["detailing"] in ("failed", "pending")


def test_truncation_is_pending_and_cached(monkeypatch):
    b=subject()
    ticks=iter([0,3])
    monkeypatch.setattr(cage,"perf_counter",lambda:next(ticks))
    with pytest.raises(cage.CageDetailingError) as error:
        cage.build_cage_detailing(b,include_skin=False)
    assert error.value.reason=="compression_support_search"
    assert b.verification_status["detailing"]=="pending"
    assert any(w.code=="cage_detailing_pending" for w in b.warnings)
