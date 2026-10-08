"""Properties every flexure design has to have, swept over sections and moments.

The examples elsewhere pin numbers; these pin behaviour across a grid wide enough
to reach the cases a single example misses -- a section past the tension-controlled
limit, a catalogue with no bars between A_s,req and A_s,max, compression steel that
only works in one layer. Each property was broken before it was written down:

* A design passes its own check. If it found a layout, that layout carries the
  moment and keeps within the code's limits; if it did not, it says so. In a sweep
  of 960 ACI 318-19 designs (b 12-25 cm, h 25-60 cm, f'c 20-30 MPa, up to twice
  the singly reinforced limit) the code before this left 311 with DCR > 1 and no
  warning, and 195 that were not tension-controlled, also without one.
* The capacity a check reports is never more than the section has. It is compared
  here with strain compatibility written out again, independently of mento: the
  check used to cut the tension steel back to A_s,max + A_s'*f_s'/f_y and keep
  phi = 0.90, which in the same sweep passed 32 designs whose real DCR was up to
  1.07.
* The steel asked for never drops as the moment grows. It fell back to A_s,max once
  the moment passed what tension steel alone can carry.
"""

import math
from typing import Any, List, Tuple

import pytest

from mento import (
    Concrete_ACI_318_19,
    Concrete_CIRSOC_201_25,
    Concrete_EN_1992_2004,
    Forces,
    Node,
    RectangularBeam,
    SteelBar,
)
from mento.slab import OneWaySlab
from mento.units import MPa, cm, kN, kNm, mm

_F_Y = 420.0
_E_S = 200000.0
_CONCRETES = {
    "ACI 318-19": Concrete_ACI_318_19,
    "CIRSOC 201-25": Concrete_CIRSOC_201_25,
    "EN 1992-2004": Concrete_EN_1992_2004,
}
#: Flags a design raises when it could not find a layout that works.
_CANNOT = {"As_below_required", "bars_do_not_fit"}
#: The warnings of a face past its maximum steel: ACI 318-19 / CIRSOC 201-25, EN 1992-1-1.
_OVER = {"not_tension_controlled", "As_above_max"}


def _independent_capacity(A_s: float, A_sp: float, d: float, dp: float, b: float, f_c: float) -> Tuple[float, float]:
    """(phi*Mn in kN·m, eps_t) by strain compatibility, ACI 318-19 §22.2 and Table 21.2.2.

    Written apart from mento on purpose: its own bisection, every bar at the stress
    its strain gives it, the compression bar net of the concrete it displaces, and
    phi from the strain the tension steel reaches. mm, MPa.
    """
    beta_1 = min(0.85, max(0.65, 0.85 - 0.05 * (f_c - 28) / 7))

    def unbalance(c: float) -> float:
        f_sp = max(-_F_Y, min(_F_Y, _E_S * 0.003 * (c - dp) / c))
        f_s = max(-_F_Y, min(_F_Y, _E_S * 0.003 * (d - c) / c))
        return 0.85 * f_c * beta_1 * c * b + A_sp * (f_sp - 0.85 * f_c) - A_s * f_s

    lo, hi = 1e-9, d
    for _ in range(200):
        mid = (lo + hi) / 2
        lo, hi = (lo, mid) if unbalance(mid) > 0 else (mid, hi)
    c = (lo + hi) / 2
    a = beta_1 * c
    f_sp = max(-_F_Y, min(_F_Y, _E_S * 0.003 * (c - dp) / c))
    M_n = 0.85 * f_c * a * b * (d - a / 2) + A_sp * (f_sp - 0.85 * f_c) * (d - dp)
    eps_t = 0.003 * (d - c) / c
    phi = max(0.65, min(0.90, 0.65 + 0.25 * (eps_t - _F_Y / _E_S) / 0.003))
    return phi * M_n / 1e6, eps_t


def _moment_at_singly_limit(b_cm: float, h_cm: float, f_c: float) -> float:
    """phi*Mn of a b x d section at rho_max, kN·m: where compression steel starts."""
    d = h_cm * 10 - 45
    beta_1 = min(0.85, max(0.65, 0.85 - 0.05 * (f_c - 28) / 7))
    a = beta_1 * 0.003 * d / (_F_Y / _E_S + 0.006)
    return 0.9 * 0.85 * f_c * a * b_cm * 10 * (d - a / 2) / 1e6


def _grid() -> List[Tuple[float, float, float, float]]:
    """Narrow and wide webs, shallow and deep, singly reinforced to well past it."""
    cases = []
    for b_cm in (12, 15, 20):
        for h_cm in (25, 30, 50):
            for f_c in (20, 30):
                M_lim = _moment_at_singly_limit(b_cm, h_cm, f_c)
                for k in (0.9, 1.15, 1.6):
                    for sign in (1, -1):
                        cases.append((b_cm, h_cm, f_c, round(sign * k * M_lim, 2)))
    return cases


def _designed(code: str, b_cm: float, h_cm: float, f_c: float, M: float) -> Tuple[RectangularBeam, Node]:
    beam = RectangularBeam(
        label="P",
        concrete=_CONCRETES[code](name="C", f_c=f_c * MPa),
        steel_bar=SteelBar(name="S", f_y=_F_Y * MPa),
        width=b_cm * cm,
        height=h_cm * cm,
        c_c=25 * mm,
    )
    node = Node(section=beam, forces=[Forces(label="M", M_y=M * kNm)])
    node.design_flexure()
    node.check_flexure()
    return beam, node


@pytest.mark.parametrize("code", ["ACI 318-19", "CIRSOC 201-25", "EN 1992-2004"])
def test_a_design_passes_its_own_check(code: str) -> None:
    """Either the layout works -- DCR <= 1, within the maximum -- or the design says it found none.

    Under ACI 318-19 and CIRSOC 201-25 the capacity it is judged by is also checked
    against strain compatibility written out apart from mento, with every bar and
    phi from eps_t: never above it, and a section that is not tension-controlled
    is reported as such. One pass over the grid does both, the designs being the
    costly part.
    """
    independent = code != "EN 1992-2004"
    silent: List[Any] = []
    overstated: List[Any] = []
    for b_cm, h_cm, f_c, M in _grid():
        beam, node = _designed(code, b_cm, h_cm, f_c, M)
        check = beam.flexure_checks[0]
        face = check.bottom if M > 0 else check.top
        codes = {warning.code for warning in node.warnings}
        assert face.M_capacity is not None and face.M_capacity.magnitude > 0, (b_cm, h_cm, f_c, M)
        # A face past its maximum explains itself (not_tension_controlled /
        # As_above_max); one short of its moment needs the design to say so.
        if (face.DCR > 1 + 1e-9 and not codes & (_CANNOT | _OVER)) or (not face.admissible and not codes & _OVER):
            silent.append((b_cm, h_cm, f_c, M, round(face.DCR, 3), sorted(codes)))
        if not independent:
            continue
        if M > 0:
            A_s, A_sp = beam._A_s_bot.to("mm**2").magnitude, beam._A_s_top.to("mm**2").magnitude
            d, dp = beam._d_bot.to("mm").magnitude, beam._c_mec_top.to("mm").magnitude
        else:
            A_s, A_sp = beam._A_s_top.to("mm**2").magnitude, beam._A_s_bot.to("mm**2").magnitude
            d, dp = beam._d_top.to("mm").magnitude, beam._c_mec_bot.to("mm").magnitude
        phi_M_n, eps_t = _independent_capacity(A_s, A_sp, d, dp, b_cm * 10, f_c)
        # Up to A_s_max mento keeps the closed form, which leaves the compression
        # steel out: never more than the section has, and equal to it past the limit.
        reported = face.M_capacity.to("kN*m").magnitude
        if reported > phi_M_n * (1 + 1e-6):
            overstated.append((b_cm, h_cm, f_c, M, round(reported, 2), round(phi_M_n, 2)))
        if eps_t < _F_Y / _E_S + 0.003 - 1e-9:
            assert "not_tension_controlled" in codes, (b_cm, h_cm, f_c, M, eps_t)
            assert not face.complies, (b_cm, h_cm, f_c, M, eps_t)
    assert not silent, f"{code}: designs that fail their own check without saying so: {silent}"
    assert not overstated, f"{code}: capacity above strain compatibility: {overstated}"


def test_a_full_design_passes_its_own_check_with_the_stirrups_it_ends_with() -> None:
    """ACI 318-19 20x50, f'c 25 MPa, ADN 420, c_c 25 mm, Mu = 150 kN·m, Vu = 250 kN.

    The flexure design runs at the depth of the 8 mm starter stirrup, where
    2Ø25 = 981.7 mm² carry the moment: d = 500 − 25 − 8 − 12.5 = 454.5 mm,
    a = 981.7·420 / (0.85·25·200) = 97.0 mm, φMn = 0.9·981.7·420·(454.5 − 48.5)
    = 150.66 kN·m, DCR 0.996. The shear design then settles on 1eØ10/11 for
    250 kN, the bars sink 2 mm to d = 452.5 mm and φMn = 0.9·412314·404.0 =
    149.92 kN·m: DCR 1.0005, and nothing warned, since the search never saw
    a shortfall (A_s,req = 9.823 cm² at that depth against 9.817 placed).
    ``design()`` now designs the flexure again with the stirrup it ended
    with: 2Ø25 + 1Ø20 at DCR 0.787, the same bars every time it runs. Fails
    before that with DCR 1.0005 and no warning.
    """
    beam = RectangularBeam(
        label="V",
        concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=20 * cm,
        height=50 * cm,
        c_c=25 * mm,
    )
    node = Node(section=beam, forces=[Forces(label="U", M_y=150 * kNm, V_z=250 * kN)])
    node.design()
    node.check()
    first = str(beam.reinforcement.bottom)

    assert beam._stirrup_d_b.to("mm").magnitude == pytest.approx(10.0)
    assert beam.flexure_checks[0].bottom.DCR <= 1.0
    assert beam.shear_checks[0].DCR <= 1.0
    assert [w.code for w in node.warnings] == ["cage_detailing_infeasible"]
    assert beam.flexure_design.bottom.A_s >= beam.flexure_design.bottom.A_s_req

    node.design()
    assert str(beam.reinforcement.bottom) == first


def test_a_lighter_stirrup_does_not_lift_the_minimum_past_the_bars_a_design_placed() -> None:
    """EN 1992-1-1 C25/30, B500S, 30x80, c_c 25 mm, M_Ed = 30 kN·m, V_Ed = 80 kN.

    A_s,min = 0.26·f_ctm/f_yk·b_t·d ≥ 0.0013·b_t·d (§9.2.1.1(1)), with
    f_ctm = 0.30·25^(2/3) = 2.565 MPa: 0.001334·b_t·d, which grows with d.
    At the Ø8 starter depth the design places 2Ø12 + 1Ø10 = 304.7 mm² on
    d = 761.3 mm against A_s,min = 0.001334·300·761.3 = 304.6 mm², and
    passes. The shear design then settles on 1eØ6/23, the bars rise 2 mm to
    d = 763.3 mm, A_s,min = 305.4 mm², and the design warned ``As_below_min``
    on its own bars. It now redoes the flexure with the Ø6 on the section and
    places 4Ø10 = 314.2 mm² (A_s,min 305.7 at the depth they sit). Fails
    before that with ``As_below_min``.
    """
    beam = RectangularBeam(
        label="V",
        concrete=Concrete_EN_1992_2004(name="C25", f_c=25 * MPa),
        steel_bar=SteelBar(name="B500S", f_y=500 * MPa),
        width=30 * cm,
        height=80 * cm,
        c_c=25 * mm,
    )
    node = Node(section=beam, forces=[Forces(label="U", M_y=30 * kNm, V_z=80 * kN)])
    node.design()
    node.check()

    assert beam._stirrup_d_b.to("mm").magnitude == pytest.approx(6.0)
    assert node.warnings == ()
    bottom = beam.flexure_design.bottom
    assert bottom.A_s >= bottom.A_s_min
    assert bottom.A_s.to("mm**2").magnitude == pytest.approx(314.16, abs=0.05)


def _short_beam() -> Tuple[RectangularBeam, Node]:
    """ACI 318-19 20x25, f'c 25 MPa, ADN 420, c_c 40 mm, Mu = 38.2 kN·m, Vu = 36.2 kN."""
    beam = RectangularBeam(
        label="V",
        concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=20 * cm,
        height=25 * cm,
        c_c=40 * mm,
    )
    return beam, Node(section=beam, forces=[Forces(label="U", M_y=38.2 * kNm, V_z=36.2 * kN)])


def test_a_design_with_no_layout_says_what_it_is_short_of() -> None:
    """ACI 318-19 20x25, f'c 25, c_c 40 mm, Mu = 38.2 kN·m, Vu = 36.2 kN: no layout carries it.

    The design starts at the Ø10, the smallest stirrup of the ACI 318-19
    catalogue, and the shear design keeps it (1eØ10/8). At d = 250 - 40 -
    10 - 10 = 190 mm the tension-controlled limit is c_t = 0.003·190/(0.003
    + 0.0021 + 0.003) = 70.4 mm, A_s,max = 0.85·25·200·0.85·70.4/420 =
    6.05 cm², short of what the moment asks: the flexure ends on 3Ø12 + 3Ø10
    in two layers under 2Ø25, DCR 1.166. A redesign from the stirrup the
    shear picked lands on the same state, so the loop stops there, and the
    design says what the bottom is short of: A_s,req = 6.98 cm². The same
    forces give the same bars on a second run.
    """
    beam, node = _short_beam()
    node.design()

    assert str(beam.reinforcement.bottom) == "2Ø12 mm + 1Ø12 mm + 2Ø10 mm + 1Ø10 mm"
    assert str(beam.reinforcement.top) == "2Ø25 mm"
    assert beam._stirrup_d_b.to("mm").magnitude == pytest.approx(10.0)
    assert beam.flexure_design.bottom.DCR == pytest.approx(1.166, abs=0.0005)
    short = {w.face: w for w in node.warnings if w.code == "As_below_required"}
    assert short["bottom"].values["A_s_req"].to("cm**2").magnitude == pytest.approx(6.98, abs=0.01)
    assert short["bottom"].values["A_s_req"] > short["bottom"].values["A_s"]

    node.design()
    assert str(beam.reinforcement.bottom) == "2Ø12 mm + 1Ø12 mm + 2Ø10 mm + 1Ø10 mm"


def test_a_design_that_does_not_close_goes_back_to_the_round_that_came_closest() -> None:
    """CIRSOC 201-25 20x25, H25, ADN 420, c_c 40 mm, Mu = 43.32 kN·m, Vu = 21.8 kN.

    The CIRSOC catalogue starts at Ø6, so the design starts at the Ø8 of the
    settings. Round 0 places 2Ø16 + 1Ø16 under 2Ø32 at the Ø8 depth; the
    shear design picks 1eØ10/9 and at that depth they leave DCR 1.171. The
    round redesigned at the Ø10 depth ends on 2Ø12 + 1Ø12 + 2Ø12, DCR 1.340,
    and the next one repeats it. Round 0 came closest, so it is run again
    and kept, and the bottom says what it is short of.
    """
    beam = RectangularBeam(
        label="V",
        concrete=Concrete_CIRSOC_201_25(name="H25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=20 * cm,
        height=25 * cm,
        c_c=40 * mm,
    )
    node = Node(section=beam, forces=[Forces(label="U", M_y=43.32 * kNm, V_z=21.8 * kN)])
    node.design()

    assert str(beam.reinforcement.bottom) == "2Ø16 mm + 1Ø16 mm"
    assert str(beam.reinforcement.top) == "2Ø32 mm"
    assert str(beam.reinforcement.transverse) == "2 legs Ø10 mm @ 9 cm · 11 cm between legs"
    assert beam.flexure_design.bottom.DCR == pytest.approx(1.171, abs=0.0005)
    assert "bottom" in [w.face for w in node.warnings if w.code == "As_below_required"]


def test_a_round_whose_bars_do_not_fit_is_not_the_closest() -> None:
    """ACI 318-19 12x25, f'c 20, c_c 25 mm, Mu = -21.27 kN·m: the bars that carry it do not fit.

    At the Ø8 starter width, 120 - 2*25 - 2*8 = 54 mm, 2Ø12 on top leave
    54 - 24 = 30 mm, the vibrator clearance, and 2Ø12 + 2Ø10 carry the
    moment. The stirrup the shear design settles on is a Ø10, which leaves
    50 mm: 26 mm between the Ø12, ``clear_spacing_below_min``, DCR 0.907.
    The round at the Ø10 width fits 2Ø10 per layer (50 - 20 = 30 mm) and
    no more: 2Ø10 + 2Ø10 = 3.14 cm² against 3.50 required, DCR 1.092. The
    smaller DCR belongs to bars that cannot be placed, so the round kept is
    the one whose bars fit, and it says what it is short of.
    """
    beam = RectangularBeam(
        label="V",
        concrete=Concrete_ACI_318_19(name="H20", f_c=20 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=12 * cm,
        height=25 * cm,
        c_c=25 * mm,
    )
    node = Node(section=beam, forces=[Forces(label="U", M_y=-21.27 * kNm)])
    node.design()

    assert str(beam.reinforcement.top) == "2Ø10 mm + 2Ø10 mm"
    assert beam._stirrup_d_b.to("mm").magnitude == pytest.approx(10.0)
    assert beam.flexure_design.top.DCR == pytest.approx(1.092, abs=0.0005)
    assert [(w.code, w.face) for w in node.warnings] == [
        ("compression_detailing_pending", None),
        ("cage_detailing_infeasible", None),
        ("As_below_required", "top"),
    ]
    short = next(w for w in node.warnings if w.code == "As_below_required")
    assert short.values["A_s_req"].to("cm**2").magnitude == pytest.approx(3.50, abs=0.005)


def test_the_design_rounds_stop_on_a_repeated_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """The same 20x25: the loop stops as soon as a round comes back to a state it has seen.

    Round 0 starts at the Ø10, the smallest stirrup of the ACI 318-19
    catalogue, and ends at DCR 1.166 with the 1eØ10 the shear design keeps.
    The redesign from that stirrup lands on the same bars, a state already
    seen, so the loop stops there, well within its bound, and warns what
    the section is short of. Two flexure passes, both at the Ø10 depth.
    """
    passes: List[Any] = []
    design_flexure = RectangularBeam._design_flexure

    def counted(self: RectangularBeam, forces: List[Forces]) -> Any:
        passes.append(self._stirrup_d_b.to("mm").magnitude)
        return design_flexure(self, forces)

    monkeypatch.setattr(RectangularBeam, "_design_flexure", counted)
    beam, node = _short_beam()
    node.design()

    assert passes == [10.0, 10.0]
    assert str(beam.reinforcement.bottom) == "2Ø12 mm + 1Ø12 mm + 2Ø10 mm + 1Ø10 mm"
    assert beam.flexure_design.bottom.DCR == pytest.approx(1.166, abs=0.0005)
    assert "bottom" in [w.face for w in node.warnings if w.code == "As_below_required"]


def test_a_slab_whose_shear_puts_its_stirrups_on_and_off_ends_saying_so() -> None:
    """ACI 318-19 one-way slab 100x15, f'c 20 MPa, ADN 420, c_c 25 mm, Mu = 46.9 kN·m, Vu = 60 kN.

    A slab strip may carry no stirrups at all, so its depth jumps by a whole
    bar when the shear design adds or drops them: d = 150 - 25 - 5 = 120 mm
    bare, 110 mm over a Ø10 grid. With tension-controlled
    c <= 0.003/(0.003 + 0.0051)·d, A_s,req / A_s,max are 11.76 / 15.29 cm²
    at 120 mm and 13.25 / 14.02 cm² at 110 mm. And the bars decide the
    stirrups: without them φVc = 0.75·0.66·ρw^(1/3)·√20·1000·120 (Table
    22.5.5.1(c), λs = 1) is 58.9 kN with Ø10/6 = 13.09 cm² (ρw = 0.01091),
    short of 60, and 62.6 kN with Ø10/5 = 15.71 cm² (ρw = 0.01309).

    So there is no pair that holds: Ø10/6 needs the grid, and over the grid
    it is 1 % short (13.09 < 13.25, DCR 1.010); at that depth no whole-cm
    Ø10 or Ø12 spacing lands between 13.25 and 14.02, so the design takes
    Ø10/5, which needs no stirrups and, back at 120 mm, is past A_s,max
    (15.71 > 15.29). PR #164 ended on Ø10/7 over a 1eØ10 grid, DCR 1.103,
    with no warning at all, a design failing its own check in silence. It
    now ends on the closer round, Ø10/5 with no stirrups, φMn = 58.54 kN·m (DCR 0.801, φ =
    0.88 at ε_t = 0.0049), and says what it misses: ``not_tension_controlled`` on the
    bottom. The check run afterwards finds the same.
    """
    slab = OneWaySlab(
        label="L",
        concrete=Concrete_ACI_318_19(name="H20", f_c=20 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=100 * cm,
        height=15 * cm,
        c_c=25 * mm,
    )
    node = Node(section=slab, forces=[Forces(label="U", M_y=46.9 * kNm, V_z=60 * kN)])
    node.design()
    designed = [(w.code, w.face) for w in node.warnings]

    assert str(slab.reinforcement.bottom) == "Ø10 mm/5 cm"
    assert str(slab.reinforcement.transverse) == "no stirrups"
    bottom = slab.flexure_design.bottom
    assert bottom.DCR == pytest.approx(0.801, abs=0.0005)
    assert bottom.A_s.to("cm**2").magnitude == pytest.approx(15.71, abs=0.005)
    assert bottom.A_s_max.to("cm**2").magnitude == pytest.approx(15.29, abs=0.005)
    assert ("not_tension_controlled", "bottom") in designed
    # It carries its moment, so nothing is short of it: the article says what fails.
    assert "As_below_required" not in {code for code, _ in designed}

    node.check()
    assert [(w.code, w.face) for w in node.warnings] == designed


def test_a_compression_face_is_searched_without_a_cap_left_by_an_earlier_check() -> None:
    """ACI 20x25, f'c 30, c_c 40 mm, Mu = +45.19 kN·m: the top only ever carries compression.

    With no negative moment the top is asked for the compression the bottom
    needs, and nothing caps that. The design capped it anyway with the top's
    A_s,max read off the section -- a value no round of the flexure design
    writes there: the reporting check of the round before had left it,
    7.05 cm². So the round redone with the final Ø10 stirrup searched the top
    under a cap the first round never had, and a design redone after a check
    ended somewhere else than the first one. Searched with no cap, the design
    starts at the Ø10 of the ACI 318-19 catalogue and ends on 2Ø12 + 1Ø12 +
    2Ø12 + 1Ø10 under 2Ø32, DCR 1.237, warning ``As_below_required``: the
    section is too shallow for the moment. A design redone after a check
    ends where the first one did.
    """
    beam = RectangularBeam(
        label="V",
        concrete=Concrete_ACI_318_19(name="H30", f_c=30 * MPa),
        steel_bar=SteelBar(name="S", f_y=_F_Y * MPa),
        width=20 * cm,
        height=25 * cm,
        c_c=40 * mm,
    )
    node = Node(section=beam, forces=[Forces(label="C1", M_y=45.19488336734695 * kNm)])
    node.design()

    designed = ("2Ø12 mm + 1Ø12 mm + 2Ø12 mm + 1Ø10 mm", "2Ø32 mm")
    assert (str(beam.reinforcement.bottom), str(beam.reinforcement.top)) == designed
    assert beam.flexure_design.DCR == pytest.approx(1.237, abs=5e-4)
    assert "As_below_required" in {w.code for w in node.warnings}

    node.check()
    node.design()
    assert (str(beam.reinforcement.bottom), str(beam.reinforcement.top)) == designed


@pytest.mark.parametrize("code", ["ACI 318-19", "CIRSOC 201-25"])
def test_the_steel_asked_for_grows_with_the_moment(code: str) -> None:
    """A_s,req on the tension face, and the compression it asks for, never drop as M grows.

    On a fixed section, from singly reinforced to three times the singly
    reinforced limit: the tension requirement used to fall back to A_s_max once
    the moment passed what tension steel alone carries, with no compression
    steel at all.
    """
    beam = RectangularBeam(
        label="M",
        concrete=_CONCRETES[code](name="C", f_c=25 * MPa),
        steel_bar=SteelBar(name="S", f_y=_F_Y * MPa),
        width=15 * cm,
        height=30 * cm,
        c_c=25 * mm,
    )
    beam.set_longitudinal_rebar_bot(2, 20 * mm, 0, None, 2, 20 * mm)
    beam.set_longitudinal_rebar_top(2, 20 * mm, 0, None, 2, 20 * mm)
    M_lim = _moment_at_singly_limit(15, 30, 25)
    moments = [M_lim * k / 10 for k in range(2, 31)]
    for sign in (1, -1):
        checks = beam.flexure_check_results([Forces(label=str(M), M_y=sign * M * kNm) for M in moments])
        tension = [(c.bottom if sign > 0 else c.top).A_s_req.to("cm**2").magnitude for c in checks]
        compression = [(c.top if sign > 0 else c.bottom).A_s_req.to("cm**2").magnitude for c in checks]
        for series in (tension, compression):
            assert all(b >= a - 1e-9 for a, b in zip(series, series[1:])), series
        # Past the singly reinforced limit the section asks for compression steel.
        assert compression[-1] > 0
        assert math.isfinite(tension[-1])


def test_an_en_face_a_hair_short_of_its_moment_does_not_read_as_passing() -> None:
    """EN 1992-1-1 C25/30, B500S, 20x40, 3Ø16 below, M_Ed = 1.0004·M_Rd.

    The EN check rounded its flexure DCR to three decimals before comparing
    it with 1, so a face up to 0.05 % short read 1.000 and passed, and the
    design accepted layouts that short. The ratio is now kept as computed.
    """
    beam = RectangularBeam(
        label="V",
        concrete=Concrete_EN_1992_2004(name="C25", f_c=25 * MPa),
        steel_bar=SteelBar(name="B500S", f_y=500 * MPa),
        width=20 * cm,
        height=40 * cm,
        c_c=25 * mm,
    )
    beam.set_longitudinal_rebar_bot(3, 16 * mm)
    M_Rd = beam.flexure_check_results([Forces(label="R", M_y=1 * kNm)])[0].bottom.M_capacity
    assert M_Rd is not None
    check = beam.flexure_check_results([Forces(label="U", M_y=1.0004 * M_Rd)])[0].bottom

    assert check.DCR == pytest.approx(1.0004, abs=1e-6)
    assert check.DCR > 1.0
