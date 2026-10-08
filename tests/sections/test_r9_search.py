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


@pytest.mark.parametrize("legs",[3,4,5])
def test_second_layer_does_not_intersect_open_legs(legs):
    b=subject(40,7)
    b.set_longitudinal_rebar_bot(n1=3,d_b1=20*mm,n3=3,d_b3=20*mm)
    b.set_longitudinal_rebar_top(n1=3,d_b1=16*mm)
    b.set_transverse_rebar(legs=legs,d_b=10*mm,s_l=15*cm)
    b.check([Forces(M_y=250*kNm,V_z=80*kN)])
    original=b.section_geometry.to_dict("mm")
    geometry=b.detailing_geometry
    assert len(geometry.bars_on("bottom",2))==3
    assert original==b.section_geometry.to_dict("mm")
    assert not any(w.code=="cage_detailing_infeasible" for w in b.warnings)


def test_symmetric_candidates_are_examined_before_lexicographic_prefix(monkeypatch):
    b=subject(150,22)
    b.set_transverse_rebar(legs=16,d_b=8*mm,s_l=15*cm)
    b.check([Forces(M_y=2500*kNm,V_z=300*kN)])
    seen=[]
    target=(2,3,4,11,12,13)
    def candidate(beam,geometry,**kwargs):
        interior=tuple(i for s in geometry.stirrups[1:] for i in s.legs)
        seen.append(interior)
        if interior==target:
            raise RuntimeError("target reached")
        raise cage.CageDetailingError("isolated search ordering")
    monkeypatch.setattr(cage,"_build_candidate",candidate)
    monkeypatch.setattr(cage,"perf_counter",lambda:0)
    with pytest.raises(RuntimeError,match="target reached"):
        cage._search_cage_detailing(b)
    level=[item for item in seen if len(item)==6]
    assert all(all(15-i in item for i in item) for item in level)
