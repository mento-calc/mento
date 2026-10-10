"""Design alternatives and repeatable designs.

``flexure_design.bottom.options`` / ``.top.options`` and ``shear_design.options``
expose what the rebar search ranked, with the layout it applied first. A design
also has to be a function of its inputs: running it again, or after the bars
were changed by hand, gives the same reinforcement.
"""

import pandas as pd
import pytest

from mento import (
    BeamSettings,
    Concrete_ACI_318_19,
    Concrete_CIRSOC_201_25,
    Concrete_EN_1992_2004,
    Footing,
    Forces,
    Node,
    OneWaySlab,
    RebarOption,
    RectangularBeam,
    SteelBar,
    StirrupOption,
)
from mento.design_results import DesignNotRunError
from mento.rebar import Rebar
from mento.units import MPa, cm, kN, kNm, m, mm


def _aci_beam(settings: BeamSettings | None = None) -> RectangularBeam:
    return RectangularBeam(
        label="V101",
        concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=20 * cm,
        height=60 * cm,
        c_c=25 * mm,
        settings=settings,
    )


def _designed(forces: list[Forces], settings: BeamSettings | None = None) -> RectangularBeam:
    beam = _aci_beam(settings)
    Node(section=beam, forces=forces).design()
    return beam


HIGH_SHEAR = [Forces(label="1.2D+1.6L", V_z=250 * kN, M_y=150 * kNm)]
TWO_FACES = [
    Forces(label="1.2D+1.6L", V_z=250 * kN, M_y=150 * kNm),
    Forces(label="1.4D", V_z=120 * kN, M_y=-40 * kNm),
]


# ---------------------------------------------------------------------------
# Longitudinal options
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("face", ["bottom", "top"])
def test_the_first_option_is_the_layout_applied(face: str) -> None:
    beam = _designed(TWO_FACES)
    options = getattr(beam.flexure_design, face).options
    applied = getattr(beam.reinforcement, face)

    assert options, "a designed face reports at least the layout it carries"
    assert all(isinstance(option, RebarOption) for option in options)
    assert options[0].layers == applied.layers
    assert options[0].A_s.to("cm**2").magnitude == pytest.approx(applied.A_s.to("cm**2").magnitude)


def test_options_are_ranked_by_their_functional_and_distinct() -> None:
    options = _designed(TWO_FACES).flexure_design.bottom.options

    assert len(options) == 3
    functionals = [option.functional for option in options]
    assert None not in functionals
    assert functionals == sorted(functionals)  # type: ignore[type-var]
    assert len({option.layers for option in options}) == len(options)


def test_an_option_area_is_the_area_of_its_bars() -> None:
    for option in _designed(TWO_FACES).flexure_design.bottom.options:
        expected = sum(layer.A_s.to("cm**2").magnitude for layer in option.layers)
        assert option.A_s.to("cm**2").magnitude == pytest.approx(expected)


@pytest.mark.parametrize("count", [1, 2, 5])
def test_the_number_of_options_is_a_setting(count: int) -> None:
    beam = _designed(TWO_FACES, BeamSettings(design_options=count))

    assert len(beam.flexure_design.bottom.options) == count
    assert 1 <= len(beam.shear_design.options) <= count


@pytest.mark.parametrize("bad", [0, -1, 2.5, True])
def test_the_number_of_options_must_be_a_positive_integer(bad: object) -> None:
    with pytest.raises(ValueError, match="design_options"):
        BeamSettings(design_options=bad)


def test_options_are_empty_before_any_design() -> None:
    beam = _aci_beam()
    beam.set_longitudinal_rebar_bot(n1=3, d_b1=16 * mm)
    beam.set_transverse_rebar(n_stirrups=1, d_b=10 * mm, s_l=20 * cm)
    Node(section=beam, forces=HIGH_SHEAR).check()

    assert beam.flexure_design.bottom.options == ()
    assert beam.shear_design.options == ()


def test_options_are_dropped_once_the_bars_are_changed_by_hand() -> None:
    """Bars set by hand drop the results until the next check; the face left alone keeps its options."""
    beam = _designed(TWO_FACES)
    beam.set_longitudinal_rebar_bot(n1=4, d_b1=25 * mm)
    beam.set_transverse_rebar(n_stirrups=2, d_b=12 * mm, s_l=10 * cm)

    with pytest.raises(DesignNotRunError):
        beam.flexure_design
    with pytest.raises(DesignNotRunError):
        beam.shear_design

    beam.check(TWO_FACES)
    assert beam.flexure_design.bottom.options == ()
    assert beam.flexure_design.top.options != ()  # untouched face keeps its own
    assert beam.shear_design.options == ()


def test_longitudinal_alternatives_are_verified_on_the_finished_beam() -> None:
    """20x60 H25 ADN 420, +150 / -40 kNm: 2Ø20 + 1Ø16 at the bottom, 2Ø12 + 1Ø10 on top, 1eØ10/13.

    An option's DCR is the worst ratio of the finished beam -- flexure and
    shear -- with that layout on its face and the other face as applied.
    Rebuilt by hand with the stirrup the design ended with, d = 600 - 25 -
    10 - d_b/2. 2Ø20 + 1Ø20 = 9.42 cm² at d = 555 mm: a = 942.5*420/(0.85*25*
    200) = 93.1 mm, phi*Mn = 0.9*942.5*420*(555 - 46.6) = 181.1 kNm, 150/181.1
    = 0.828; and the shear, phi*(Vc + Vs) = 0.75*(0.17*sqrt(25)*200*555 +
    (2*78.54/130)*420*555) = 0.75*(94.4 + 281.7) = 282.0 kN, 250/282.0 =
    0.887, which governs. 2Ø25 = 9.82 cm² at 552.5 mm: a = 97.0 mm, phi*Mn =
    187.0 kNm, 0.802; phi*Vn = 280.7 kN, 0.891.
    """
    beam = _designed(TWO_FACES)
    flexure = beam.flexure_design
    options = flexure.bottom.options

    assert [str(o) for o in options] == ["2Ø20 mm + 1Ø16 mm", "2Ø20 mm + 1Ø20 mm", "2Ø25 mm"]
    assert options[0].section_DCR == pytest.approx(max(flexure.DCR, beam.shear_design.DCR))
    assert all(o.section_DCR is not None and o.section_DCR <= 1.0 for o in options)
    assert [round(o.section_DCR, 3) for o in options] == [0.930, 0.887, 0.891]  # type: ignore[arg-type]
    assert all(o.section_DCR == options[0].section_DCR for o in flexure.top.options)  # the bottom governs all three

    for option, layout in (
        (options[1], dict(n1=2, d_b1=20 * mm, n2=1, d_b2=20 * mm)),
        (options[2], dict(n1=2, d_b1=25 * mm)),
    ):
        rebuilt = _aci_beam()
        rebuilt.set_longitudinal_rebar_bot(**layout)  # type: ignore[arg-type]
        rebuilt.set_longitudinal_rebar_top(n1=2, d_b1=12 * mm, n2=1, d_b2=10 * mm)
        rebuilt.set_transverse_rebar(n_stirrups=1, d_b=10 * mm, s_l=13 * cm)
        Node(section=rebuilt, forces=TWO_FACES).check()
        assert max(rebuilt.flexure_design.DCR, rebuilt.shear_design.DCR) == pytest.approx(option.section_DCR)


def test_an_alternative_short_of_the_moment_on_the_finished_beam_is_dropped() -> None:
    """20x60 H25 ADN 420, Mu = 80 kNm: 2Ø16 applied (A_s,req 3.94 cm²), 1eØ10/27.

    The search ranks 2Ø10 + 1Ø10 in one layer with 2Ø10 behind, 3.93 cm²,
    fourth: enough for the 3.92 cm² its own iteration asked for, read with
    the 8 mm starter stirrup, and short of the finished beam's 3.94. Built by
    hand: centroid (3*5 + 2*40)/5 = 19 mm, d = 600 - 25 - 10 - 19 = 546 mm,
    a = 392.7*420/(0.85*25*200) = 38.8 mm, phi*Mn = 0.9*392.7*420*(546 -
    19.4) = 78.2 kNm, 80/78.2 = 1.023. With the default design_options = 3
    it never reaches the list; asking for four, PR #164 offered it as
    options[3], and it is dropped now for the next row that passes, 2Ø16 +
    1Ø16. (With the corner bars seated in the stirrup bends, 2Ø16 + 1Ø12
    ranks ahead of 2Ø12 + 2Ø12.)
    """
    beam = _designed([Forces(label="ELU", M_y=80 * kNm)], BeamSettings(design_options=4))
    options = beam.flexure_design.bottom.options

    assert str(options[0]) == "2Ø16 mm"
    assert "2Ø10 mm + 1Ø10 mm + 2Ø10 mm" not in [str(o) for o in options]
    assert [str(o) for o in options] == ["2Ø16 mm", "2Ø16 mm + 1Ø12 mm", "2Ø12 mm + 2Ø12 mm", "2Ø16 mm + 1Ø16 mm"]
    assert all(o.section_DCR is not None and o.section_DCR <= 1.0 for o in options)

    beam.set_longitudinal_rebar_bot(n1=2, d_b1=10 * mm, n2=1, d_b2=10 * mm, n3=2, d_b3=10 * mm)
    Node(section=beam, forces=[Forces(label="ELU", M_y=80 * kNm)]).check()
    assert beam.flexure_design.DCR == pytest.approx(1.023, abs=0.001)


def test_a_compression_face_alternative_that_fails_the_other_face_is_dropped() -> None:
    """EN 22x60 C25 B500S, M_Ed = +400 kNm, V_Ed = 250 kN: doubly reinforced.

    Bottom 2Ø25 + 2Ø25, top 2Ø25 (9.82 cm², d' = 25 + 10 + 12.5 = 47.5 mm),
    bottom DCR 0.999 at M_Rd 400.4 kNm. The search ranked 2Ø16 + 1Ø16 + 2Ø16
    for the top by area alone (10.05 cm², more steel), but its second layer
    puts the centroid at d' = (3*43 + 2*84)/5 = 59.4 mm, the compression
    steel reaches less stress at the ductility limit and the couple gives
    less: M_Rd 395.4 kNm, bottom DCR 1.012. An alternative of the top face
    that fails the bottom is not an alternative. (The 20 cm web this test
    used before the bends were laid out is now designed another way.)
    """
    beam = RectangularBeam(
        label="V",
        concrete=Concrete_EN_1992_2004(name="C25", f_c=25 * MPa),
        steel_bar=SteelBar(name="B500S", f_y=500 * MPa),
        width=22 * cm,
        height=60 * cm,
        c_c=25 * mm,
    )
    forces = [Forces(label="ELU", M_y=400 * kNm, V_z=250 * kN)]
    Node(section=beam, forces=forces).design()
    top = beam.flexure_design.top.options

    assert str(top[0]) == "2Ø25 mm"
    assert "2Ø16 mm + 1Ø16 mm + 2Ø16 mm" not in [str(o) for o in top]
    assert all(o.section_DCR is not None and o.section_DCR <= 1.0 for o in top)

    beam.set_longitudinal_rebar_top(n1=2, d_b1=16 * mm, n2=1, d_b2=16 * mm, n3=2, d_b3=16 * mm)
    Node(section=beam, forces=forces).check()
    assert beam.flexure_design.bottom.DCR == pytest.approx(1.012, abs=0.0005)


def test_a_longitudinal_alternative_past_the_shear_limit_of_its_section_is_dropped() -> None:
    """ACI 15x25 H25 ADN 420, c_c 25 mm, Mu = 8 kNm, Vu = 97.5 kN: 2Ø10, 1eØ10/5.

    The bars set the depth the shear is read at too: d = min(d_bot, d_top).
    With 2Ø10 in one layer d = 250 - 25 - 10 - 5 = 210 mm and the limit of
    §22.5.1.2 is phi*(0.17 + 0.66)*sqrt(25)*150*d = 0.75*0.83*750*210 =
    98.05 kN: shear DCR 0.994. The search also ranked 2Ø10 + 2Ø10 in two
    layers, whose centroid sits (2*5 + 2*40)/4 = 22.5 mm in: d = 192.5 mm,
    limit 89.88 kN, DCR 1.085 and ``shear_exceeds_section_limit``, and the
    50 mm spacing past d/4 = 48.1 mm. It was offered at DCR 0.404, its
    flexure alone. 2Ø12, d = 209 mm and limit 97.58 kN, still carries it.
    (The 12 cm web this test used before the bends were laid out fits no
    pair of bars beside a Ø10.)
    """
    beam = RectangularBeam(
        label="V",
        concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=15 * cm,
        height=25 * cm,
        c_c=25 * mm,
    )
    forces = [Forces(label="ELU", M_y=8 * kNm, V_z=97.5 * kN)]
    Node(section=beam, forces=forces).design()
    options = beam.flexure_design.bottom.options

    assert str(beam.reinforcement.transverse) == "2 legs Ø10 mm @ 5 cm"
    assert "2Ø10 mm + 2Ø10 mm" not in [str(o) for o in options]
    assert [str(o) for o in options[:2]] == ["2Ø10 mm", "2Ø12 mm"]
    assert [round(o.section_DCR, 3) for o in options[:2]] == [0.994, 0.999]  # type: ignore[arg-type]
    assert all(o.section_DCR is not None and o.section_DCR <= 1.0 for o in options)

    beam.set_longitudinal_rebar_bot(n1=2, d_b1=10 * mm, n3=2, d_b3=10 * mm)
    Node(section=beam, forces=forces).check()
    assert beam.shear_design.DCR == pytest.approx(1.085, abs=0.001)
    assert {"shear_exceeds_section_limit", "stirrup_spacing_exceeds_max"} <= {w.code for w in beam.warnings}


def test_an_en_alternative_that_lowers_the_shear_resistance_past_the_demand_is_dropped() -> None:
    """EN 15x60 C20/25 B500S, c_c 25 mm, M_Ed = -109 kNm, V_Ed = 83.3 kN.

    Applied: 2Ø20 on top, 1eØ6/37, with d = 600 - 25 - 6 - 10 = 559 mm and
    V_Rd,s = 83.58 kN, DCR 0.997. V_Rd,s grows with z = 0.9*d, so a top
    layout that sits deeper carries less: 2Ø25 at d = 556.5 mm gives 83.58 *
    556.5/559 = 83.21 kN (DCR 1.001), and 2Ø16 with 2Ø12 behind, centroid
    (402*8 + 226*47)/628 = 22.0 mm, d = 547.0 mm, 81.78 kN (DCR 1.019).
    Both were offered, at their flexural 0.701 and 0.833.
    """
    beam = RectangularBeam(
        label="V",
        concrete=Concrete_EN_1992_2004(name="C20", f_c=20 * MPa),
        steel_bar=SteelBar(name="B500S", f_y=500 * MPa),
        width=15 * cm,
        height=60 * cm,
        c_c=25 * mm,
    )
    forces = [Forces(label="ELU", M_y=-109 * kNm, V_z=83.3 * kN)]
    Node(section=beam, forces=forces).design()
    top = beam.flexure_design.top.options

    assert str(top[0]) == "2Ø20 mm"
    assert str(beam.reinforcement.transverse) == "2 legs Ø6 mm @ 37 cm"
    assert not {"2Ø25 mm", "2Ø16 mm + 2Ø12 mm"} & {str(o) for o in top}
    assert all(o.section_DCR is not None and o.section_DCR <= 1.0 for o in top)
    assert top[0].section_DCR == pytest.approx(beam.shear_design.DCR)

    beam.set_longitudinal_rebar_top(n1=2, d_b1=25 * mm)
    Node(section=beam, forces=forces).check()
    assert beam.shear_design.DCR == pytest.approx(1.001, abs=0.0005)


def test_trying_the_alternatives_leaves_the_faces_flagged_as_they_were() -> None:
    """Verifying the alternatives is the design trying layouts, not bars set by hand.

    Each pooled row is put on the face through the public setters, and those
    drop the face's ``bars_do_not_fit`` (the search's verdict on the width no
    longer describes bars set by hand). Putting the applied bars back has to
    put the flag back too, or a face the search gave up on and that still
    kept alternatives would lose its warning to the verification. Through ``design()`` the two do not
    meet today -- a face the search cannot fit keeps no table -- so the
    state is set by hand: 25x50 H25 under 120 kNm keeps two alternatives on
    the bottom, and the flag is planted on that face.
    """
    beam = RectangularBeam(
        label="V",
        concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=25 * cm,
        height=50 * cm,
        c_c=25 * mm,
    )
    forces = [Forces(label="ELU", M_y=120 * kNm, V_z=100 * kN)]
    Node(section=beam, forces=forces).design()
    assert len(beam.flexure_design.bottom.options) > 1
    beam._infeasible_faces = {"bot"}
    assert "bars_do_not_fit" in [w.code for w in beam.warnings]

    beam._verify_longitudinal_options(forces)

    assert beam._infeasible_faces == {"bot"}
    assert "bars_do_not_fit" in [w.code for w in beam.warnings]


def test_a_footing_offers_no_alternatives() -> None:
    """A footing mat is chosen as a whole; the per-face rows it replaced are not alternatives to it."""
    footing = Footing(
        label="Z1",
        concrete=Concrete_EN_1992_2004(name="C25", f_c=25 * MPa),
        steel_bar=SteelBar(name="B500S", f_y=500 * MPa),
        width=1 * m,
        height=40 * cm,
        c_c=50 * mm,
    )
    Node(section=footing, forces=[Forces(label="ELU", M_y=100 * kNm), Forces(label="ELU2", M_y=-20 * kNm)]).design()
    flexure = footing.flexure_design

    for face in (flexure.bottom, flexure.top):
        assert len(face.options) == 1
        assert face.options[0].layers == face.layers
        assert face.options[0].functional is None
        assert face.options[0].section_DCR == pytest.approx(flexure.DCR)


def test_slab_options_read_as_spacings() -> None:
    slab = OneWaySlab(
        label="L1",
        concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=1 * m,
        height=20 * cm,
        c_c=25 * mm,
    )
    Node(section=slab, forces=[Forces(label="1.2D+1.6L", M_y=40 * kNm, V_z=50 * kN)]).design()

    options = slab.flexure_design.bottom.options
    assert options[0].layers == slab.reinforcement.bottom.layers
    assert all(layer.s is not None for option in options for layer in option.layers)
    assert len({option.layers for option in options}) == len(options)


# ---------------------------------------------------------------------------
# Stirrup options
# ---------------------------------------------------------------------------


def test_the_first_stirrup_option_is_the_one_applied() -> None:
    beam = _designed(TWO_FACES)
    design = beam.shear_design
    first = design.options[0]

    assert isinstance(first, StirrupOption)
    assert (first.n_stirrups, first.d_b, first.s_l) == (design.n_stirrups, design.d_b, design.s_l)
    assert first.A_v.to("cm**2/m").magnitude == pytest.approx(design.A_v.to("cm**2/m").magnitude)


def test_the_alternatives_are_the_other_bars_each_at_its_own_spacing() -> None:
    """Where s_max governs, every diameter lands on the same spacing: the options are the bars.

    20x60 H25, Mu 120 kNm, Vu 250 kN: d/2 = 27.9 cm is far off, and the
    threshold of Table 9.7.6.2.2 is crossed (Vs,req = (250 - 71.3)/0.75 =
    238 kN > 184 kN), so s_max,l = d/4 = 13.97 cm -> 13 cm for every bar.
    All three carry the section: the worst ratio is the flexure's, on 2Ø20.
    (Under the 150 kNm of ``HIGH_SHEAR`` the 2Ø20 + 1Ø16 leave no room for
    the 64 mm bends of a Ø16 stirrup, so it is not offered.)
    """
    options = _designed([Forces(label="1.2D+1.6L", V_z=250 * kN, M_y=120 * kNm)]).shear_design.options
    diameters = [option.d_b.to("mm").magnitude for option in options]

    assert diameters == [10, 12, 16]
    assert diameters[1:] == sorted(diameters[1:])
    assert {option.s_l for option in options} == {13 * cm}
    assert {option.n_stirrups for option in options} == {1}
    # The functional says what each heavier bar costs in steel, over the demand
    # read at that bar's own depth: 2 mm deeper per size, so a little more.
    assert [round(option.functional, 2) for option in options] == [0.18, 0.69, 1.97]
    assert all(option.section_DCR is not None and option.section_DCR <= 1.0 for option in options)
    assert [round(option.section_DCR, 3) for option in options] == [0.964, 0.968, 0.975]  # type: ignore[arg-type]


def test_an_alternative_past_the_shear_limit_of_its_own_section_is_dropped() -> None:
    """ACI 25x50 H25, Mu 150 kNm, Vu 350 kN: 2Ø25 at the bottom, 1eØ10/8 applied.

    With the Ø10 stirrup d = 500 - 25 - 10 - 12.5 = 452.5 mm and the section
    limit of §22.5.1.2 is phi*(Vc + 0.66*sqrt(25)*250*452.5) = 0.75*(96.2 +
    373.3) = 352.1 kN: DCR 0.994. The Ø16 row, 1eØ16/11, sits the bars 6 mm
    deeper, d = 446.5 mm, and the same limit falls to 347.4 kN: DCR 1.007 and
    ``shear_exceeds_section_limit``. The Ø12 row, d = 450.5 mm, still passes
    at 0.998. The search offers all three; the section is only built with two.
    """
    beam = RectangularBeam(
        label="V",
        concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=25 * cm,
        height=50 * cm,
        c_c=25 * mm,
    )
    Node(section=beam, forces=[Forces(label="ELU", V_z=350 * kN, M_y=150 * kNm)]).design()
    options = beam.shear_design.options

    assert [str(o) for o in options] == [
        "2 legs Ø10 mm @ 8 cm · 19 cm between legs (max 22.62 cm)",
        "2 legs Ø12 mm @ 11 cm · 18.8 cm between legs (max 22.53 cm)",
    ]
    assert [round(o.section_DCR, 3) for o in options] == [0.994, 0.998]  # type: ignore[arg-type]
    assert [row.d_b.to("mm").magnitude for row in beam.shear_design_results.itertuples()] == [10, 12, 16]


def test_an_alternative_that_lowers_the_flexural_capacity_past_the_moment_is_dropped() -> None:
    """ACI 20x50 H25, Mu 100 kNm, Vu 120 kN: 2Ø20 at the bottom, 1eØ10/22 applied.

    The stirrup sets the depth of the bars: d = 500 - 25 - d_b,stirrup - 10.
    With a = A_s*f_y/(0.85*f'c*b) = 628.3*420/(0.85*25*200) = 62.1 mm,
    phi*Mn = 0.9*628.3*420*(d - 31.0): 100.6 kNm at the Ø10 depth (455 mm),
    DCR 0.993; 100.2 at Ø12 (453 mm), DCR 0.998; 99.2 at Ø16 (449 mm), DCR
    1.008. The shear itself is far from governing (DCR 0.74), so the Ø16 row
    fails only through the moment -- and is dropped for it.
    """
    beam = RectangularBeam(
        label="V",
        concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=20 * cm,
        height=50 * cm,
        c_c=25 * mm,
    )
    Node(section=beam, forces=[Forces(label="ELU", V_z=120 * kN, M_y=100 * kNm)]).design()
    options = beam.shear_design.options

    assert str(beam.reinforcement.bottom) == "2Ø20 mm"
    assert [str(o) for o in options] == [
        "2 legs Ø10 mm @ 22 cm · 14 cm between legs (max 45.5 cm)",
        "2 legs Ø12 mm @ 22 cm · 13.8 cm between legs (max 45.3 cm)",
    ]
    assert [round(o.section_DCR, 3) for o in options] == [0.993, 0.998]  # type: ignore[arg-type]
    assert options[0].section_DCR == pytest.approx(beam.flexure_design.DCR)


def test_an_options_ratio_is_the_sections_and_is_named_so() -> None:
    """The same 20x50 under 100 kNm and 120 kN: each result says whose ratio it carries.

    ``shear_design.DCR`` is the shear's, 120 kN against phi*(Vc + Vs) with
    the 1eØ10/22, 0.748; the flexure governs the section at 0.993. The
    applied stirrup option carries the section's 0.993, not the shear's.
    The top face carries nothing (``top.DCR`` 0.0), and its one option --
    no bars -- carries the section's 0.993 too. The options call theirs
    ``section_DCR``, so that it is not read as the shear's or the face's.
    """
    beam = RectangularBeam(
        label="V",
        concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=20 * cm,
        height=50 * cm,
        c_c=25 * mm,
    )
    Node(section=beam, forces=[Forces(label="ELU", V_z=120 * kN, M_y=100 * kNm)]).design()
    shear, flexure = beam.shear_design, beam.flexure_design

    assert shear.DCR == pytest.approx(0.748, abs=0.0005)
    assert flexure.DCR == pytest.approx(0.993, abs=0.0005)
    assert shear.options[0].section_DCR == pytest.approx(flexure.DCR)
    assert str(flexure.top) == "no reinforcement" and flexure.top.DCR == 0.0
    assert [o.section_DCR for o in flexure.top.options] == [pytest.approx(0.993, abs=0.0005)]
    assert not hasattr(shear.options[0], "DCR")
    assert not hasattr(flexure.top.options[0], "DCR")


def test_the_applied_stirrups_keep_their_dcr_when_nothing_passes() -> None:
    """20x60 H25 with Vu 450 kN is past the section limit of §22.5.1.2 however it is stirruped.

    Designed with 2Ø20 + 1Ø16 (centroid (628.3*10 + 201.1*8)/829.4 = 9.5 mm
    in) and a Ø10 stirrup, d = 600 - 25 - 10 - 9.5 = 555.5 mm and phi*Vmax =
    0.75*(0.17 + 0.66)*sqrt(25)*200*555.5 = 346 kN. No alternative can carry 450 kN, so none is offered;
    the applied layout stays first, with the 450/346 = 1.30 that says why.
    """
    beam = _designed([Forces(label="1.2D+1.6L", V_z=450 * kN, M_y=150 * kNm)])
    options = beam.shear_design.options

    assert len(options) == 1
    assert (options[0].d_b, options[0].s_l) == (beam.shear_design.d_b, beam.shear_design.s_l)
    assert options[0].section_DCR == pytest.approx(beam.shear_design.DCR)
    assert options[0].section_DCR == pytest.approx(1.30, abs=0.005)
    assert "shear_exceeds_section_limit" in [w.code for w in beam.warnings]


def test_the_stirrup_table_offers_one_layout_per_diameter() -> None:
    rebar = Rebar(_aci_beam())

    def row(n: int, d_b: float, s_l: float) -> dict:
        A_v = n * 2 * 3.14159 * (d_b * mm) ** 2 / 4 / (s_l * cm)
        return {"n_stir": n, "d_b": d_b * mm, "s_l": s_l * cm, "s_w": 14 * cm, "A_v": A_v.to("cm**2/m")}

    table = rebar._rank_stirrup_options([row(1, 10, 13), row(1, 12, 13), row(2, 10, 20)], 10 * cm**2 / m)
    kept = [(r.n_stir, r.d_b.to("mm").magnitude, r.s_l.to("cm").magnitude) for r in table.itertuples()]

    # Nothing is dropped: a heavier bar at the same spacing stays on offer.
    assert kept == [(1, 10, 13), (1, 12, 13), (2, 10, 20)]
    # Fewest stirrups first, least steel among those: the row the design applies.
    assert kept[0] == (1, 10, 13)
    # The functional of the applied row is the smallest excess, and two stirrups carry +1.
    functional = list(table["functional"])
    assert functional[0] == min(functional)
    assert functional[2] > 1


# ---------------------------------------------------------------------------
# Repeatable designs
# ---------------------------------------------------------------------------


def _signature(beam: RectangularBeam) -> tuple:
    return (str(beam.reinforcement), beam.shear_design.s_w, beam.flexure_design.bottom.options)


@pytest.mark.parametrize(
    "forces",
    [
        [Forces(label="V", V_z=120 * kN)],
        [Forces(label="VM", V_z=120 * kN, M_y=100 * kNm)],
        TWO_FACES,
    ],
    ids=["shear-only", "shear-and-moment", "two-faces"],
)
def test_design_gives_the_same_result_every_time(forces: list[Forces]) -> None:
    beam = _aci_beam()
    node = Node(section=beam, forces=forces)
    node.design()
    first = _signature(beam)
    node.design()
    node.design()

    assert _signature(beam) == first
    assert _signature(_designed(forces)) == first


def test_design_ignores_the_reinforcement_set_before_it() -> None:
    beam = _aci_beam()
    beam.set_longitudinal_rebar_bot(n1=4, d_b1=25 * mm)
    beam.set_longitudinal_rebar_top(n1=2, d_b1=20 * mm)
    beam.set_transverse_rebar(n_stirrups=2, d_b=16 * mm, s_l=8 * cm)
    Node(section=beam, forces=TWO_FACES).design()

    assert _signature(beam) == _signature(_designed(TWO_FACES))


@pytest.mark.parametrize(
    "forces",
    [
        TWO_FACES,
        [Forces(label="ELU", V_z=250 * kN, M_y=150 * kNm)],
    ],
    ids=["two-faces", "settles-twice"],
)
def test_a_full_design_verifies_the_alternatives_once(forces: list[Forces], monkeypatch: pytest.MonkeyPatch) -> None:
    """The alternatives are judged on the finished section, so only that verification counts.

    ``design_flexure`` verifies them on the section it leaves, which is right
    when it is called alone; inside ``design()`` any such pass would be
    overwritten by the one on the finished section. Run on every flexure
    pass, it would verify the 20x60 under +150 / -40 kNm twice, and a design
    that redoes its flexure (20x60 H25 has none, so
    the 20x50 of ``_settle_design`` stands for it: 150 kNm and 250 kN) three
    times. A guard on the cost, not on a result: the options are the same
    either way.
    """
    calls: list[int] = []
    verify = RectangularBeam._verify_longitudinal_options

    def counted(self: RectangularBeam, forces: list[Forces]) -> None:
        calls.append(1)
        verify(self, forces)

    beam = _aci_beam()
    if len(forces) == 1:
        beam = RectangularBeam(
            label="V",
            concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
            steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
            width=20 * cm,
            height=50 * cm,
            c_c=25 * mm,
        )
    Node(section=beam, forces=forces).design()
    expected = (beam.flexure_design.bottom.options, beam.flexure_design.top.options)

    monkeypatch.setattr(RectangularBeam, "_verify_longitudinal_options", counted)
    Node(section=beam, forces=forces).design()

    assert len(calls) == 1
    assert (beam.flexure_design.bottom.options, beam.flexure_design.top.options) == expected

    calls.clear()
    Node(section=beam, forces=forces).design_flexure()
    assert len(calls) == 1, "design_flexure alone still verifies what it leaves"


def test_design_shear_alone_is_repeatable() -> None:
    beam = _aci_beam()
    node = Node(section=beam, forces=[Forces(label="V", V_z=120 * kN)])
    node.design_shear()
    first = str(beam.shear_design)
    node.design_shear()

    assert str(beam.shear_design) == first


def test_the_first_design_respects_the_spacing_limit_of_the_finished_beam() -> None:
    """The spacing used to be chosen at the depth of the 8 mm starter stirrup: 28 cm past a 27.95 cm limit."""
    beam = _designed([Forces(label="V", V_z=120 * kN)])

    assert beam.shear_design.s_l <= beam._d_shear / 2
    assert beam.shear_design.s_l == 27 * cm
    assert "stirrup_spacing_exceeds_max" not in [w.code for w in beam.warnings]


@pytest.mark.parametrize(
    "width, height, f_c, V_z, d_b, s_l",
    [(30, 40, 20, 180, 8, 9), (25, 50, 25, 300, 8, 6)],
    ids=["threshold-crossing", "area-short"],
)
def test_the_stirrups_are_sized_at_the_depth_of_their_own_diameter(
    width: int, height: int, f_c: int, V_z: int, d_b: int, s_l: int
) -> None:
    """CIRSOC 201-25, c_c 25 mm, ADN 420, Mu = 60 kNm on the two beams of the ids.

    30x40, f'c 20, Vu 180 kN, designed with 2Ø16 + 1Ø12 at the bottom: the
    bars' centroid sits 7.56 mm in, so with a Ø8 stirrup d = 400 - 25 - 8 -
    7.56 = 359.44 mm, phi*Vc = 0.75*0.17*sqrt(20)*300*359.44 = 61.5 kN and
    Vs,req = (180 - 61.5)/0.75 = 158.0 kN, under the 0.33*sqrt(20)*300*359.44
    = 159.1 kN threshold of Tabla 9.7.6.2.2: s_max,l = d/2 = 17.97 cm.
    A_v,req = 158.0 kN / (420 MPa * 359.44 mm) = 10.47 cm²/m, which two Ø8
    legs (1.005 cm²) cover at 9 cm (11.17 cm²/m). With a Ø10 stirrup d is
    357.44 mm, Vs,req = 158.5 kN crosses the threshold (158.3 kN) and s_max,l
    halves to 8.94 cm. The design used to pass 10 → 8 → 10, hit its cap and
    apply the Ø10 row sized at the Ø8 depth, 1eØ10/15: DCR 1.005 and the
    spacing 1.7 times its limit, unwarned by the design.

    25x50, f'c 25, Vu 300 kN: the same loop applied 1eØ10/10 with A_v = 15.71
    cm²/m against the 15.78 its own depth asks for, DCR 1.0035. Sized at its
    own depth every row of the table covers its own demand and spacing limit.
    """
    beam = RectangularBeam(
        label="V",
        concrete=Concrete_CIRSOC_201_25(name="H", f_c=f_c * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=width * cm,
        height=height * cm,
        c_c=25 * mm,
    )
    Node(section=beam, forces=[Forces(label="ELU", V_z=V_z * kN, M_y=60 * kNm)]).design()
    design = beam.shear_design

    assert (design.d_b, design.s_l) == (d_b * mm, s_l * cm)
    assert design.DCR <= 1.0
    assert design.A_v >= design.A_v_req
    assert design.s_l <= beam._stirrup_s_max_l
    assert "stirrup_spacing_exceeds_max" not in [w.code for w in beam.warnings]
    table = beam.shear_design_results
    assert all(row.A_v >= row.A_v_req for row in table.itertuples())
    assert all(row.s_l <= row.s_max_l for row in table.itertuples())
    assert len(table) == 4, "one row per bar CIRSOC offers, each sized at its own depth"


def test_en_design_is_repeatable_and_reports_options() -> None:
    def make() -> RectangularBeam:
        return RectangularBeam(
            label="V",
            concrete=Concrete_EN_1992_2004(name="C25", f_c=25 * MPa),
            steel_bar=SteelBar(name="B500S", f_y=500 * MPa),
            width=20 * cm,
            height=60 * cm,
            c_c=25 * mm,
        )

    beam = make()
    node = Node(section=beam, forces=TWO_FACES)
    node.design()
    first = _signature(beam)
    node.design()

    assert _signature(beam) == first
    assert beam.flexure_design.bottom.options[0].layers == beam.reinforcement.bottom.layers
    assert beam.shear_design.options[0].s_l == beam.shear_design.s_l


def test_options_read_like_the_reinforcement() -> None:
    beam = _designed(TWO_FACES)
    bottom = beam.flexure_design.bottom.options[0]
    stirrups = beam.shear_design.options[0]

    assert str(bottom) == str(beam.reinforcement.bottom)
    assert bottom.n_bars == beam.reinforcement.bottom.n_bars
    assert str(stirrups) == str(beam.shear_design)
    assert stirrups.n_legs == beam.shear_design.n_legs
    # The same, field by field: the applied option is the design, its limits included.
    design = beam.shear_design
    assert (stirrups.n_stirrups, stirrups.d_b, stirrups.s_l) == (design.n_stirrups, design.d_b, design.s_l)
    assert stirrups.s_max_w == design.s_max_w
    assert stirrups.s_max_l == design.s_max_l
    assert str(RebarOption(layers=(), A_s=0 * cm**2)) == "no reinforcement"


def test_an_empty_stirrup_table_leaves_no_options() -> None:
    """The search hands back nothing when no bar fits at any spacing; the design then raises."""
    beam = _aci_beam()
    beam._record_transverse_options(pd.DataFrame(), HIGH_SHEAR)

    assert beam._shear_options == ()


def test_ranking_an_empty_search_gives_an_empty_table() -> None:
    table = Rebar(_aci_beam())._rank_stirrup_options([], 5 * cm**2 / m)

    assert table.empty
