"""Footing: the minimum longitudinal reinforcement of a member on the ground.

A :class:`~mento.slab.Footing` is a :class:`~mento.slab.OneWaySlab` in every
respect but one, so these tests are about that one respect. They pin the two
codes' minimum-reinforcement clauses to numbers, and they pin the property that
motivated the class: the design returns the largest applicable minimum already
applied, so a consumer never has to correct the engine's answer.
"""

import math
import warnings

import pytest

from mento.codes.aci_318_19.equations import flexure as aci_flexure
from mento.codes.en_1992_2004.equations import flexure as en_flexure
from mento.forces import Forces
from mento.material import (
    Concrete_ACI_318_19,
    Concrete_CIRSOC_201_25,
    Concrete_EN_1992_2004,
    SteelBar,
)
from mento.node import Node
from mento.codes.EN_1992_2004_beam import _minimum_flexural_reinforcement_area_EN_1992_2004
from mento.settings import BeamSettings
from mento.slab import Footing, OneWaySlab
from mento.units import cm, inch, kNm, kip, m, mm, MPa, psi

# A metre-wide strip 600 mm deep: the geometry of the reference case the
# clauses below were verified against.
_WIDTH = 1 * m
_HEIGHT = 60 * cm
_COVER = 50 * mm


@pytest.fixture
def steel_b500s() -> SteelBar:
    return SteelBar(name="B500S", f_y=500 * MPa)


def _strip(cls, concrete, steel, label, height=_HEIGHT):  # type: ignore[no-untyped-def]
    return cls(
        label=label,
        concrete=concrete,
        steel_bar=steel,
        width=_WIDTH,
        height=height,
        c_c=_COVER,
    )


def _design(section, M_y=50 * kNm):  # type: ignore[no-untyped-def]
    Node(section=section, forces=[Forces(label="C1", M_y=M_y)]).design()
    return section


# ---------------------------------------------------------------------------
# The equations themselves
# ---------------------------------------------------------------------------


def test_aci_shrinkage_and_temperature_ratio() -> None:
    """ACI 318-19 §7.6.1.1 / §24.4.3.2: 0.0018 flat, whatever the steel grade."""
    assert aci_flexure.shrinkage_and_temperature_ratio() == pytest.approx(0.0018)


@pytest.mark.parametrize(
    "h, expected",
    [
        (200.0, 1.00),  # saturated below 300 mm
        (300.0, 1.00),
        (600.0, 0.79),  # the reference case of the office
        (800.0, 0.65),
        (1200.0, 0.65),  # saturated above 800 mm
    ],
)
def test_en_crack_control_coefficient_k(h: float, expected: float) -> None:
    """EN 1992-1-1 §7.3.2(2): k interpolated with the depth."""
    assert en_flexure.crack_control_coefficient_k(h) == pytest.approx(expected)


@pytest.mark.parametrize(
    "f_yk, expected",
    [(300.0, 0.0010), (400.0, 0.0010), (450.0, 0.00095), (500.0, 0.0009), (600.0, 0.0009)],
)
def test_en_foundation_min_reinforcement_ratio(f_yk: float, expected: float) -> None:
    assert en_flexure.foundation_min_reinforcement_ratio(f_yk) == pytest.approx(expected)


def test_en_crack_control_min_reinforcement_is_equation_7_1() -> None:
    """A_s,min * sigma_s = k_c * k * f_ct,eff * A_ct, rearranged."""
    A_s_min = en_flexure.crack_control_min_reinforcement(0.4, 0.79, 2.56, 300_000.0, 500 / 1.15)
    assert A_s_min == pytest.approx(0.4 * 0.79 * 2.56 * 300_000.0 / (500 / 1.15))


# ---------------------------------------------------------------------------
# ACI 318-19 and CIRSOC 201-25
# ---------------------------------------------------------------------------


def test_aci_footing_minimum_is_the_gross_section_rule() -> None:
    """0.0018 * b * h at f_y = 420 MPa, and nothing about the effective depth."""
    concrete = Concrete_ACI_318_19(name="H25", f_c=25 * MPa)
    steel = SteelBar(name="ADN 420", f_y=420 * MPa)
    footing = _design(_strip(Footing, concrete, steel, "Z1"))

    expected = 0.0018 * (1000 * mm) * (600 * mm)
    assert footing._A_s_min_bot.to("cm**2").magnitude == pytest.approx(expected.to("cm**2").magnitude)


def test_aci_footing_takes_the_slab_minimum() -> None:
    """A member on the ground reaches the slab minimum through §13.3.2.1: both
    carry the 0.0018*Ag of ACI 318-19 §7.6.1.1, not the beam one of §9.6.1.2."""
    concrete = Concrete_ACI_318_19(name="H25", f_c=25 * MPa)
    steel = SteelBar(name="ADN 420", f_y=420 * MPa)
    footing = _design(_strip(Footing, concrete, steel, "Z1"))
    slab = _design(_strip(OneWaySlab, concrete, steel, "L1"))

    assert footing._A_s_min_bot.to("cm**2").magnitude == pytest.approx(slab._A_s_min_bot.to("cm**2").magnitude)


def test_aci_footing_minimum_does_not_scale_with_the_steel_grade() -> None:
    """The 0.0018*420/f_y of ACI 318-14 was withdrawn: 318-19 asks 0.0018*Ag for any f_y."""
    concrete = Concrete_ACI_318_19(name="H25", f_c=25 * MPa)
    footing = _design(_strip(Footing, concrete, SteelBar(name="B500S", f_y=500 * MPa), "Z1"))

    expected = 0.0018 * (1000 * mm) * (600 * mm)
    assert footing._A_s_min_bot.to("cm**2").magnitude == pytest.approx(expected.to("cm**2").magnitude)


def test_cirsoc_shares_the_aci_clause() -> None:
    """CIRSOC 201-25 publishes ACI's formulas, this one included."""
    steel = SteelBar(name="ADN 420", f_y=420 * MPa)
    aci = _design(_strip(Footing, Concrete_ACI_318_19(name="H25", f_c=25 * MPa), steel, "Z1"))
    cirsoc = _design(_strip(Footing, Concrete_CIRSOC_201_25(name="H25", f_c=25 * MPa), steel, "Z2"))

    assert cirsoc._A_s_min_bot.to("cm**2").magnitude == pytest.approx(aci._A_s_min_bot.to("cm**2").magnitude)


def test_aci_footing_minimum_in_imperial_units() -> None:
    """Same clause in US customary units, still written on b*h."""
    concrete = Concrete_ACI_318_19(name="C4000", f_c=4000 * psi)
    steel = SteelBar(name="G60", f_y=60000 * psi)
    footing = Footing(
        label="Z1",
        concrete=concrete,
        steel_bar=steel,
        width=36 * inch,
        height=24 * inch,
        c_c=2 * inch,
    )
    _design(footing, M_y=40 * kip * inch)

    expected = 0.0018 * 36 * 24  # in²
    assert footing._A_s_min_bot.to("in**2").magnitude == pytest.approx(expected)


def test_aci_footing_with_no_moment_still_gets_the_minimum() -> None:
    """Shrinkage and temperature steel does not depend on a moment being there."""
    concrete = Concrete_ACI_318_19(name="H25", f_c=25 * MPa)
    steel = SteelBar(name="ADN 420", f_y=420 * MPa)
    footing = _design(_strip(Footing, concrete, steel, "Z1"), M_y=0 * kNm)

    expected = 0.0018 * (1000 * mm) * (600 * mm)
    assert footing._A_s_bot.to("cm**2").magnitude >= expected.to("cm**2").magnitude


# ---------------------------------------------------------------------------
# EN 1992-2004
# ---------------------------------------------------------------------------


def test_en_footing_minimum_is_the_crack_control_rule(steel_b500s: SteelBar) -> None:
    """The reference case: h = 600 mm, C25 (f_ctm = 2.56 MPa), B500S.

    k = 0.79 at that depth, k_c = 0.40 in bending, A_ct is the half of the
    section in tension and sigma_s is f_yd, so Eq. (7.1) gives the minimum --
    and it is above the geometric one, so it governs.
    """
    concrete = Concrete_EN_1992_2004(name="C25", f_c=25 * MPa)
    footing = _design(_strip(Footing, concrete, steel_b500s, "Z1"))

    f_ctm = concrete.f_ctm.to(MPa).magnitude
    expected_mm2 = 0.4 * 0.79 * f_ctm * (1000 * 600 / 2) / (500 / 1.15)
    geometric_mm2 = 0.0009 * 1000 * 600
    assert expected_mm2 > geometric_mm2  # the crack-control rule is the governing one here

    assert footing._A_s_min_bot.to("mm**2").magnitude == pytest.approx(expected_mm2)


def test_en_footing_minimum_is_the_larger_of_the_two_rules(steel_b500s: SteelBar) -> None:
    """Which of the two rules governs depends on the depth.

    Both are proportional to h, so only k separates them: it decays past
    300 mm, and by 900 mm it has saturated at 0.65 and the crack-control
    minimum has fallen below the geometric one, which then governs.
    """
    concrete = Concrete_EN_1992_2004(name="C25", f_c=25 * MPa)
    footing = _design(_strip(Footing, concrete, steel_b500s, "Z1", height=90 * cm), M_y=100 * kNm)

    f_ctm = concrete.f_ctm.to(MPa).magnitude
    crack_mm2 = 0.4 * 0.65 * f_ctm * (1000 * 900 / 2) / (500 / 1.15)
    geometric_mm2 = 0.0009 * 1000 * 900
    assert geometric_mm2 > crack_mm2  # the geometric rule is the governing one here

    assert footing._A_s_min_bot.to("mm**2").magnitude == pytest.approx(max(crack_mm2, geometric_mm2))


def test_en_footing_minimum_is_lower_than_the_slab_minimum(steel_b500s: SteelBar) -> None:
    concrete = Concrete_EN_1992_2004(name="C25", f_c=25 * MPa)
    footing = _design(_strip(Footing, concrete, steel_b500s, "Z1"))
    slab = _design(_strip(OneWaySlab, concrete, steel_b500s, "L1"))

    assert footing._A_s_min_bot < slab._A_s_min_bot


# ---------------------------------------------------------------------------
# What the class is, and what a design returns
# ---------------------------------------------------------------------------


def test_footing_is_a_one_way_slab(steel_b500s: SteelBar) -> None:
    """Same reinforcement parameterisation, same checks -- only the minimum differs."""
    concrete = Concrete_EN_1992_2004(name="C25", f_c=25 * MPa)
    footing = _strip(Footing, concrete, steel_b500s, "Z1")

    assert isinstance(footing, OneWaySlab)
    assert footing.mode == "slab"
    assert hasattr(footing, "set_slab_longitudinal_rebar_bot")


def test_support_says_which_clause_applies(steel_b500s: SteelBar) -> None:
    concrete = Concrete_EN_1992_2004(name="C25", f_c=25 * MPa)
    assert _strip(Footing, concrete, steel_b500s, "Z1").support == "soil"
    assert _strip(OneWaySlab, concrete, steel_b500s, "L1").support == "free"


@pytest.mark.parametrize(
    "concrete, steel",
    [
        (Concrete_ACI_318_19(name="H25", f_c=25 * MPa), SteelBar(name="ADN 420", f_y=420 * MPa)),
        (Concrete_EN_1992_2004(name="C25", f_c=25 * MPa), SteelBar(name="B500S", f_y=500 * MPa)),
    ],
    ids=["aci", "en"],
)
def test_design_already_covers_the_minimum(concrete, steel) -> None:  # type: ignore[no-untyped-def]
    """The reason this lives in mento: what the design returns needs no
    correction by the consumer. A small moment is used so the minimum, and not
    the demand, is what sizes the steel."""
    footing = _design(_strip(Footing, concrete, steel, "Z1"), M_y=10 * kNm)

    assert footing._A_s_bot >= footing._A_s_min_bot
    assert footing._A_s_bot >= footing._A_s_req_bot


def test_a_footing_still_carries_its_moment(steel_b500s: SteelBar) -> None:
    """The relaxed minimum only ever relaxes the minimum: a demand above it is
    still what governs, and the designed section resists it."""
    concrete = Concrete_EN_1992_2004(name="C25", f_c=25 * MPa)
    footing = _strip(Footing, concrete, steel_b500s, "Z1")
    combo = [Forces(label="C1", M_y=300 * kNm)]
    Node(section=footing, forces=combo).design()

    assert footing._A_s_bot > footing._A_s_min_bot
    assert footing.flexure_check_results(combo)[0].bottom.DCR <= 1.0


# ---------------------------------------------------------------------------
# Detailing: how far apart the bars sit
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "concrete, steel, expected_mm",
    [
        (Concrete_ACI_318_19(name="H25", f_c=25 * MPa), SteelBar(name="ADN 420", f_y=420 * MPa), 255.0),
        (Concrete_CIRSOC_201_25(name="H25", f_c=25 * MPa), SteelBar(name="ADN 420", f_y=420 * MPa), 255.0),
        (Concrete_EN_1992_2004(name="C25", f_c=25 * MPa), SteelBar(name="B500S", f_y=500 * MPa), 300.0),
    ],
    ids=["aci", "cirsoc", "en"],
)
def test_footing_bars_are_capped_by_the_ground_practice_and_table_24_3_2(concrete, steel, expected_mm) -> None:  # type: ignore[no-untyped-def]
    """3h stops binding on a section this thick, so the footing cap is what holds.

    Under CIRSOC 201-25 the same 300 mm arrives twice over -- as the practice
    every code is given on the ground and as art. 7.7.2.3 itself. Under both
    ACI 318-19 and CIRSOC 201-25 the crack-control cap of Table 24.3.2 then
    takes over, reached through §13.3.2.1 → §7.7.2.2, with the footing's own
    cover: f_s = (2/3)*420 = 280 MPa and 50 mm to the bars give
    380 - 2.5*50 = 255 mm. EN 1992-1-1 has no such table and keeps the 300."""
    footing = _strip(Footing, concrete, steel, "Z1")

    assert footing._max_bar_spacing().to("mm").magnitude == pytest.approx(expected_mm)


@pytest.mark.parametrize(
    "concrete, steel",
    [
        (Concrete_ACI_318_19(name="H25", f_c=25 * MPa), SteelBar(name="ADN 420", f_y=420 * MPa)),
        (Concrete_EN_1992_2004(name="C25", f_c=25 * MPa), SteelBar(name="B500S", f_y=500 * MPa)),
    ],
    ids=["aci", "en"],
)
def test_footing_bars_are_floored_at_100_mm(concrete, steel) -> None:  # type: ignore[no-untyped-def]
    assert _strip(Footing, concrete, steel, "Z1")._min_bar_spacing().to("mm").magnitude == pytest.approx(100.0)


def test_a_slab_keeps_the_wider_slab_limits(steel_b500s: SteelBar) -> None:
    """The tighter pair is a footing's, not every slab's."""
    slab = _strip(OneWaySlab, Concrete_EN_1992_2004(name="C25", f_c=25 * MPa), steel_b500s, "L1")

    assert slab._max_bar_spacing().to("mm").magnitude == pytest.approx(400.0)
    assert slab._min_bar_spacing() is None


@pytest.mark.parametrize("M_y", [50, 150, 300, 450, 600, 750, 900, 1100])
def test_a_designed_footing_stays_inside_the_spacing_range(steel_b500s: SteelBar, M_y: int) -> None:
    """Across the range a metre strip can carry, the design answers with a
    bigger bar rather than with bars closer than 100 mm."""
    concrete = Concrete_EN_1992_2004(name="C25", f_c=25 * MPa)
    footing = _design(_strip(Footing, concrete, steel_b500s, "Z1"), M_y=M_y * kNm)

    spacing = footing._s_b1_b.to("mm").magnitude
    assert 100.0 <= spacing <= 300.0
    assert footing.flexure_check_results([Forces(label="C1", M_y=M_y * kNm)])[0].bottom.DCR <= 1.0


def test_the_floor_is_what_holds_the_footing_apart(steel_b500s: SteelBar) -> None:
    """The same demand on a slab, which has no floor, is detailed tighter."""
    concrete = Concrete_EN_1992_2004(name="C25", f_c=25 * MPa)
    footing = _design(_strip(Footing, concrete, steel_b500s, "Z1"), M_y=900 * kNm)
    slab = _design(_strip(OneWaySlab, concrete, steel_b500s, "L1"), M_y=900 * kNm)

    assert slab._s_b1_b.to("mm").magnitude < 100.0
    assert footing._s_b1_b.to("mm").magnitude >= 100.0


def test_the_spacing_row_of_a_footing_reports_both_bounds(steel_b500s: SteelBar) -> None:
    """The check table carries the range, so a footing detailed outside it fails."""
    concrete = Concrete_EN_1992_2004(name="C25", f_c=25 * MPa)
    footing = _design(_strip(Footing, concrete, steel_b500s, "Z1"))

    row = footing._data_min_max_flexure
    index = row["Check"].index("Bar spacing bottom")
    assert row["Min."][index] == pytest.approx(100.0)
    assert row["Max."][index] == pytest.approx(300.0)


# ---------------------------------------------------------------------------
# Detailing: how thin the section may be
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "concrete, steel, height, limit",
    [
        # ACI and CIRSOC state d >= 150 mm: the 180 mm strip is covered 50 mm
        # and carries the Ø10 mat floor, so d = 180 - 50 - 10/2 = 125 mm.
        (Concrete_ACI_318_19(name="H25", f_c=25 * MPa), SteelBar(name="ADN 420", f_y=420 * MPa), 18 * cm, "150"),
        # EN states nothing, and its 250 mm is an overall thickness.
        (Concrete_EN_1992_2004(name="C25", f_c=25 * MPa), SteelBar(name="B500S", f_y=500 * MPa), 22 * cm, "250"),
    ],
    ids=["aci", "en"],
)
def test_a_thin_footing_warns(concrete, steel, height, limit) -> None:  # type: ignore[no-untyped-def]
    with pytest.warns(UserWarning, match=f"below the {limit} mm"):
        _strip(Footing, concrete, steel, "Z1", height=height)


@pytest.mark.parametrize(
    "concrete, height, cover",
    [
        # ACI 318-19 Table 20.5.1.3.1, cast against and permanently in contact
        # with ground: 75 mm. d = 220 - 75 - 10/2 = 140 mm.
        (Concrete_ACI_318_19(name="H25", f_c=25 * MPa), 220 * mm, 75 * mm),
        # CIRSOC 201-25 Tabla 20.5.1.3.1, fila (a): 60 mm for a footing not
        # under control of execution. d = 210 - 60 - 10/2 = 145 mm.
        (Concrete_CIRSOC_201_25(name="H25", f_c=25 * MPa), 210 * mm, 60 * mm),
    ],
    ids=["aci", "cirsoc"],
)
def test_the_limit_is_on_the_effective_depth_not_on_the_thickness(concrete, height, cover) -> None:  # type: ignore[no-untyped-def]
    """ACI 318-19 §13.3.1.2 / CIRSOC 201-25 art. 13.3.1.2: d >= 150 mm.

    The clause is written on the effective depth of the bottom reinforcement,
    and on a footing that sits a long way under the overall thickness, because
    the cover against the ground is large. Both sections here are over 200 mm
    thick and both fall short of the 150 mm the clause asks -- so a limit
    written on the thickness in the 200 mm range passes them in silence.
    """
    steel = SteelBar(name="ADN 420", f_y=420 * MPa)
    with pytest.warns(UserWarning, match="below the 150 mm"):
        Footing(
            label="Z1",
            concrete=concrete,
            steel_bar=steel,
            width=_WIDTH,
            height=height,
            c_c=cover,
        )


def test_a_thin_section_with_little_cover_meets_the_clause() -> None:
    """And the other way round: what §13.3.1.2 asks for is depth to the bars.

    190 mm covered 25 mm leaves 190 - 25 - 10/2 = 160 mm to the mat, over the
    150 mm of the clause, so nothing is said -- where a limit written on the
    overall thickness would report a section that complies. The cover is the
    engineer's input; mento does not impose Table 20.5.1.3.1 on it.
    """
    concrete = Concrete_ACI_318_19(name="H25", f_c=25 * MPa)
    steel = SteelBar(name="ADN 420", f_y=420 * MPa)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        Footing(
            label="Z1",
            concrete=concrete,
            steel_bar=steel,
            width=_WIDTH,
            height=190 * mm,
            c_c=25 * mm,
        )


def test_the_effective_depth_limit_in_imperial_units() -> None:
    """The in-lb edition of §13.3.1.2 prints 6 in., and that is what is compared.

    A 9 in. section covered 3 in. and detailed with the 3/8 in. floor of the
    imperial settings is left with 9 - 3 - 0.375/2 = 5.81 in.
    """
    concrete = Concrete_ACI_318_19(name="C4000", f_c=4000 * psi)
    steel = SteelBar(name="G60", f_y=60000 * psi)
    with pytest.warns(UserWarning, match="below the 6 in"):
        Footing(
            label="Z1",
            concrete=concrete,
            steel_bar=steel,
            width=36 * inch,
            height=9 * inch,
            c_c=3 * inch,
        )


@pytest.mark.parametrize(
    "concrete, expected",
    [
        (Concrete_ACI_318_19(name="H25", f_c=25 * MPa), 150 * mm),
        (Concrete_CIRSOC_201_25(name="H25", f_c=25 * MPa), 150 * mm),
        (Concrete_ACI_318_19(name="C4000", f_c=4000 * psi), 6 * inch),
    ],
    ids=["aci", "cirsoc", "aci-imperial"],
)
def test_both_codes_register_the_same_effective_depth(concrete, expected) -> None:  # type: ignore[no-untyped-def]
    """CIRSOC 201-25 art. 13.3.1.2 reprints ACI 318-19 §13.3.1.2 unchanged.

    And neither of them states an overall thickness, so the thickness hook is
    left unset rather than filled with a reading of the clause.
    """
    from mento.codes.registry import design_code

    code = design_code(concrete)
    assert code.min_effective_depth_on_soil is not None
    assert code.min_effective_depth_on_soil(concrete) == expected
    assert code.min_thickness_on_soil is None


@pytest.mark.parametrize(
    "concrete, steel",
    [
        (Concrete_ACI_318_19(name="H25", f_c=25 * MPa), SteelBar(name="ADN 420", f_y=420 * MPa)),
        (Concrete_EN_1992_2004(name="C25", f_c=25 * MPa), SteelBar(name="B500S", f_y=500 * MPa)),
    ],
    ids=["aci", "en"],
)
def test_a_footing_of_the_usual_depth_does_not_warn(concrete, steel) -> None:  # type: ignore[no-untyped-def]
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        _strip(Footing, concrete, steel, "Z1")


def test_a_thin_slab_does_not_warn(steel_b500s: SteelBar) -> None:
    """The thickness rule is a footing's; a suspended slab is as thin as it is."""
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        _strip(OneWaySlab, Concrete_EN_1992_2004(name="C25", f_c=25 * MPa), steel_b500s, "L1", height=15 * cm)


def test_a_thin_footing_is_still_designed(steel_b500s: SteelBar) -> None:
    """The warning is advice. The thickness is the engineer's to choose, and the
    design that follows is still the right design for the section given."""
    concrete = Concrete_EN_1992_2004(name="C25", f_c=25 * MPa)
    with pytest.warns(UserWarning):
        footing = _strip(Footing, concrete, steel_b500s, "Z1", height=20 * cm)
    _design(footing, M_y=20 * kNm)

    assert footing._A_s_bot >= footing._A_s_min_bot
    assert footing._A_s_bot.magnitude > 0


def test_the_warning_names_the_footing_and_the_code() -> None:
    concrete = Concrete_ACI_318_19(name="H25", f_c=25 * MPa)
    steel = SteelBar(name="ADN 420", f_y=420 * MPa)
    with pytest.warns(UserWarning) as caught:
        _strip(Footing, concrete, steel, "Z7", height=15 * cm)

    message = str(caught[0].message)
    assert "Z7" in message
    assert "ACI 318-19" in message


# ---------------------------------------------------------------------------
# A section with nothing on the tension face
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("face", ["bot", "top"], ids=["bottom", "top"])
@pytest.mark.parametrize(
    "concrete, steel",
    [
        (Concrete_ACI_318_19(name="H25", f_c=25 * MPa), SteelBar(name="ADN 420", f_y=420 * MPa)),
        (Concrete_EN_1992_2004(name="C25", f_c=25 * MPa), SteelBar(name="B500S", f_y=500 * MPa)),
    ],
    ids=["aci", "en"],
)
def test_an_unreinforced_face_reports_a_failing_dcr(concrete, steel, face) -> None:  # type: ignore[no-untyped-def]
    """Both codes answer a moment on a bare face with a DCR far above 1.

    EN used to divide by zero here, on either face. It is what a footing too
    thin to be reinforced within its spacing range now reports, so it has to be
    a number -- and a slab reinforced on one face only is checked for the
    combination that puts the other one in tension, so both branches are real.
    """
    section = _strip(OneWaySlab, concrete, steel, "L1")
    # A positive moment puts the bottom in tension, a negative one the top.
    combo = [Forces(label="C1", M_y=(50 if face == "bot" else -50) * kNm)]

    result = section.flexure_check_results(combo)[0]
    assert getattr(result, "bottom" if face == "bot" else "top").DCR > 1


# ---------------------------------------------------------------------------
# A design code that states none of these rules
# ---------------------------------------------------------------------------


def test_a_code_without_the_footing_rules_imposes_none() -> None:
    """A rule a code does not have is not a rule an element can fail.

    ``min_bar_spacing_slab``, ``max_bar_spacing_tension``,
    ``min_thickness_on_soil`` and ``min_effective_depth_on_soil`` are optional
    hooks: between them the registered codes fill them in, so this registers
    one that does not and drives a footing through it. Nothing is capped and
    nothing is warned about -- silence, rather than an error about a limit
    that was never stated.
    """
    import dataclasses

    from mento.codes.registry import _REGISTRY, DesignCode, design_code, register

    reference = design_code(Concrete_ACI_318_19(name="H25", f_c=25 * MPa))
    invented = DesignCode(
        **{
            **{f.name: getattr(reference, f.name) for f in dataclasses.fields(reference)},
            "title": "NBR 6118-2023",
            "year": 2023,
            "max_bar_spacing_slab": None,
            "max_bar_spacing_tension": None,
            "min_bar_spacing_slab": None,
            "min_thickness_on_soil": None,
            "min_effective_depth_on_soil": None,
        }
    )
    register(invented)
    try:
        concrete = Concrete_ACI_318_19(name="H25", f_c=25 * MPa)
        concrete.design_code = invented.title
        steel = SteelBar(name="ADN 420", f_y=420 * MPa)

        with warnings.catch_warnings():
            warnings.simplefilter("error")
            # Thin enough that either registered code would have warned.
            footing = _strip(Footing, concrete, steel, "Z1", height=15 * cm)

        assert footing._min_bar_spacing() is None
        assert footing._max_bar_spacing() is None
        # And the bar count is left at the slab default, since nothing bounds it.
        assert footing.settings.max_bars_per_layer >= 200
        # With no bounds there is no space to search a mat in, so none is offered
        # and the design keeps whatever the per-face search arrived at.
        assert list(footing._mat_candidates(10 * cm**2, 5 * cm**2)) == []
    finally:
        _REGISTRY.pop(invented.title, None)


# ---------------------------------------------------------------------------
# One mat: both faces at one spacing
# ---------------------------------------------------------------------------


def _design_envelope(section, M_bot, M_top):  # type: ignore[no-untyped-def]
    """Design for an envelope with a moment on each face, and return it."""
    combo = [Forces(label="C1", M_y=M_bot), Forces(label="C2", M_y=-M_top)]
    Node(section=section, forces=combo).design()
    return section, combo


@pytest.mark.parametrize(
    "concrete, steel",
    [
        (Concrete_ACI_318_19(name="H25", f_c=25 * MPa), SteelBar(name="ADN 420", f_y=420 * MPa)),
        (Concrete_EN_1992_2004(name="C25", f_c=25 * MPa), SteelBar(name="B500S", f_y=500 * MPa)),
    ],
    ids=["aci", "en"],
)
def test_a_designed_footing_is_one_mat(concrete, steel) -> None:  # type: ignore[no-untyped-def]
    """Both faces come out on one module: the top at the bottom's spacing, or at
    exactly twice it so one top bar lands on every second bottom bar.

    The bottom carries five times the top's moment here, so the two faces would
    otherwise be detailed at spacings nobody would draw on one mat.
    """
    footing, _ = _design_envelope(_strip(Footing, concrete, steel, "Z1"), 600 * kNm, 120 * kNm)

    s_bot = footing._s_b1_b.to("mm").magnitude
    s_top = footing._s_b1_t.to("mm").magnitude
    assert s_top / s_bot in (1.0, 2.0)


def test_the_fallback_takes_the_smaller_of_the_two_spacings(steel_b500s: SteelBar) -> None:
    """What the design falls back to when no searched mat verifies.

    Closing the wider face up only ever adds bars, which is why it needs no
    verification of its own. Driven from a layout set by hand, so that the two
    spacings going in are known and the rule can be read off the result.
    """
    concrete = Concrete_EN_1992_2004(name="C25", f_c=25 * MPa)
    footing = _strip(Footing, concrete, steel_b500s, "Z1")
    footing.set_slab_longitudinal_rebar_bot(d_b1=16 * mm, s_b1=120 * mm)
    footing.set_slab_longitudinal_rebar_top(d_b1=12 * mm, s_b1=250 * mm)
    A_s_top_before = footing._A_s_top

    footing._match_spacings_downward()

    assert footing._s_b1_b.to("mm").magnitude == pytest.approx(120.0)
    assert footing._s_b1_t.to("mm").magnitude == pytest.approx(120.0)
    # Closing the top up added bars, and left its bar alone.
    assert footing._A_s_top > A_s_top_before
    assert footing._d_b1_t.to("mm").magnitude == pytest.approx(12.0)


def test_the_mat_is_lighter_than_reconciling_the_two_spacings(steel_b500s: SteelBar) -> None:
    """Why the search exists: taking the smaller of the two spacings buys steel
    the section never asked for, and choosing the module instead does not."""
    concrete = Concrete_EN_1992_2004(name="C25", f_c=25 * MPa)
    searched, _ = _design_envelope(_strip(Footing, concrete, steel_b500s, "Z1"), 600 * kNm, 120 * kNm)

    reconciled, _ = _design_envelope(_strip(Footing, concrete, steel_b500s, "Z2"), 600 * kNm, 120 * kNm)
    reconciled._match_spacings_downward()

    assert searched._A_s_bot + searched._A_s_top <= reconciled._A_s_bot + reconciled._A_s_top


def test_matching_the_mat_never_undoes_the_design(steel_b500s: SteelBar) -> None:
    """Closing the wider face up only adds steel, so both faces still pass."""
    concrete = Concrete_EN_1992_2004(name="C25", f_c=25 * MPa)
    footing, combo = _design_envelope(_strip(Footing, concrete, steel_b500s, "Z1"), 600 * kNm, 120 * kNm)

    results = footing.flexure_check_results(combo)
    assert max(r.bottom.DCR for r in results) <= 1.0
    assert max(r.top.DCR for r in results) <= 1.0
    assert footing._A_s_bot >= footing._A_s_min_bot
    assert footing._A_s_top >= footing._A_s_min_top


def test_the_mat_is_credited_with_the_whole_bars_it_has(steel_b500s: SteelBar) -> None:
    """The mat search reads a candidate as the footing counts it, and that covers each face.

    The count the search chooses by has to be the steel the mat is credited
    with: an EN 1 m x 0.40 m footing with c_c 50 mm under +100 / -20 kN·m has
    bars lying in 82 cm, so whatever spacing it ends on, the area is that many
    whole bars and it covers what each face requires.
    """
    concrete = Concrete_EN_1992_2004(name="C25", f_c=25 * MPa)
    footing, _ = _design_envelope(_strip(Footing, concrete, steel_b500s, "Z1", height=40 * cm), 100 * kNm, 20 * kNm)

    for face, spacing, d_b in (
        (footing.reinforcement.bottom, footing._s_b1_b, footing._d_b1_b),
        (footing.reinforcement.top, footing._s_b1_t, footing._d_b1_t),
    ):
        whole = math.floor(82 * cm / spacing + 1e-9) + 1
        assert face.A_s.to("cm**2").magnitude == pytest.approx((whole * math.pi * d_b**2 / 4).to("cm**2").magnitude)
    assert footing.reinforcement.bottom.A_s >= footing.flexure_design.bottom.A_s_req
    assert footing.reinforcement.top.A_s >= footing.flexure_design.top.A_s_req


def test_the_mat_keeps_each_face_within_the_spacing_range(steel_b500s: SteelBar) -> None:
    """Matching down cannot push a face below the 100 mm floor: the module is
    one of the two spacings the design already chose."""
    concrete = Concrete_EN_1992_2004(name="C25", f_c=25 * MPa)
    footing, _ = _design_envelope(_strip(Footing, concrete, steel_b500s, "Z1"), 900 * kNm, 100 * kNm)

    for spacing in (footing._s_b1_b, footing._s_b1_t):
        assert 100.0 <= spacing.to("mm").magnitude <= 300.0


def test_each_face_keeps_its_own_diameter(steel_b500s: SteelBar) -> None:
    """Only the module is shared. A face carrying a fifth of the moment is
    still allowed its own, thinner bar."""
    concrete = Concrete_EN_1992_2004(name="C25", f_c=25 * MPa)
    footing, _ = _design_envelope(_strip(Footing, concrete, steel_b500s, "Z1"), 600 * kNm, 120 * kNm)

    assert footing._d_b1_t <= footing._d_b1_b


def test_no_mat_is_detailed_below_the_practical_bar(steel_b500s: SteelBar) -> None:
    """A footing mesh is not drawn with the thinnest bar in the catalogue, even
    where the arithmetic would allow it on the lightly loaded face."""
    concrete = Concrete_EN_1992_2004(name="C25", f_c=25 * MPa)
    footing, _ = _design_envelope(_strip(Footing, concrete, steel_b500s, "Z1"), 600 * kNm, 20 * kNm)

    assert footing._d_b1_t.to("mm").magnitude >= 10.0
    assert footing._d_b1_b.to("mm").magnitude >= 10.0


def test_a_footing_reinforced_on_one_face_gets_no_second_grid(steel_b500s: SteelBar) -> None:
    """Nothing to reconcile, and a grid is not invented to reconcile with."""
    concrete = Concrete_EN_1992_2004(name="C25", f_c=25 * MPa)
    footing = _design(_strip(Footing, concrete, steel_b500s, "Z1"), M_y=300 * kNm)

    assert footing._s_b1_b.magnitude > 0
    assert footing._s_b1_t.magnitude == 0
    assert footing._d_b1_t.magnitude == 0


def test_a_slab_still_details_its_faces_independently(steel_b500s: SteelBar) -> None:
    """The mat is a footing's; a suspended slab keeps the spacing each face
    actually needed."""
    concrete = Concrete_EN_1992_2004(name="C25", f_c=25 * MPa)
    slab, _ = _design_envelope(_strip(OneWaySlab, concrete, steel_b500s, "L1"), 600 * kNm, 120 * kNm)

    assert slab._s_b1_b != slab._s_b1_t


def test_reconciling_an_existing_mat_is_a_no_op(steel_b500s: SteelBar) -> None:
    """The fallback run on a mat that is already one leaves it alone."""
    concrete = Concrete_EN_1992_2004(name="C25", f_c=25 * MPa)
    footing = _strip(Footing, concrete, steel_b500s, "Z1")
    footing.set_slab_longitudinal_rebar_bot(d_b1=16 * mm, s_b1=150 * mm)
    footing.set_slab_longitudinal_rebar_top(d_b1=12 * mm, s_b1=150 * mm)
    before = (footing._s_b1_b, footing._s_b1_t, footing._A_s_bot, footing._A_s_top)

    footing._match_spacings_downward()

    assert (footing._s_b1_b, footing._s_b1_t, footing._A_s_bot, footing._A_s_top) == before


def test_the_top_may_be_set_out_at_twice_the_bottom(steel_b500s: SteelBar) -> None:
    """The modular option is real and gets used.

    A top face carrying a tenth of the bottom's moment is drawn at double the
    bottom's module -- one top bar on every second bottom bar -- rather than
    matched to it and given steel it has no use for.
    """
    concrete = Concrete_EN_1992_2004(name="C25", f_c=25 * MPa)
    doubled = 0
    for h, M_bot, M_top in [(50, 300, 30), (60, 400, 40), (40, 200, 20), (70, 600, 60)]:
        footing, _ = _design_envelope(
            _strip(Footing, concrete, steel_b500s, "Z1", height=h * cm), M_bot * kNm, M_top * kNm
        )
        ratio = footing._s_b1_t.to("mm").magnitude / footing._s_b1_b.to("mm").magnitude
        assert ratio in (1.0, 2.0)
        doubled += ratio == 2.0

    assert doubled, "the double module was never taken, so the option is not doing anything"


# ---------------------------------------------------------------------------
# The edges of the mat search
# ---------------------------------------------------------------------------


def test_a_section_needing_nothing_is_offered_no_mat(steel_b500s: SteelBar) -> None:
    """No steel required on either face is not a mat problem."""
    concrete = Concrete_EN_1992_2004(name="C25", f_c=25 * MPa)
    footing = _strip(Footing, concrete, steel_b500s, "Z1")

    assert list(footing._mat_candidates(0 * cm**2, 0 * cm**2)) == []


def test_a_face_no_bar_can_cover_drops_that_module(steel_b500s: SteelBar) -> None:
    """A top face wanting more steel than the widest module can carry does not
    veto the search -- that module is simply not one of the candidates."""
    concrete = Concrete_EN_1992_2004(name="C25", f_c=25 * MPa)
    footing = _strip(Footing, concrete, steel_b500s, "Z1")

    # 60 cm² over the four bars a 300 mm module fits in the strip is beyond any
    # bar in the catalogue, so the wide modules drop out and the close ones stay.
    candidates = list(footing._mat_candidates(20 * cm**2, 60 * cm**2))
    assert candidates
    assert all(s_top <= 150 for (_, s_top), _ in candidates)


def test_the_fallback_leaves_a_single_grid_alone(steel_b500s: SteelBar) -> None:
    """Reconciling needs two grids; with one there is nothing to reconcile."""
    concrete = Concrete_EN_1992_2004(name="C25", f_c=25 * MPa)
    footing = _strip(Footing, concrete, steel_b500s, "Z1")
    footing.set_slab_longitudinal_rebar_bot(d_b1=16 * mm, s_b1=150 * mm)
    before = (footing._s_b1_b, footing._d_b1_b, footing._A_s_bot)

    footing._match_spacings_downward()

    assert (footing._s_b1_b, footing._d_b1_b, footing._A_s_bot) == before


def test_a_mat_that_does_not_verify_is_passed_over(steel_b500s: SteelBar) -> None:
    """The search proposes, the capacity check disposes.

    Driven with a verifier that refuses everything, so the design falls back to
    reconciling the two spacings it had already proved -- which is the point of
    keeping that rule around.
    """
    concrete = Concrete_EN_1992_2004(name="C25", f_c=25 * MPa)
    footing = _strip(Footing, concrete, steel_b500s, "Z1")
    footing.set_slab_longitudinal_rebar_bot(d_b1=16 * mm, s_b1=120 * mm)
    footing.set_slab_longitudinal_rebar_top(d_b1=12 * mm, s_b1=250 * mm)

    footing._finalize_longitudinal_design(20 * cm**2, 5 * cm**2, lambda: False)

    # Not a searched mat: the layout it started from, with the spacings matched.
    assert footing._d_b1_b.to("mm").magnitude == pytest.approx(16.0)
    assert footing._d_b1_t.to("mm").magnitude == pytest.approx(12.0)
    assert footing._s_b1_b == footing._s_b1_t == 120 * mm


@pytest.mark.parametrize(
    "height, M_bot, M_top",
    [(25 * cm, 500 * kNm, -20 * kNm), (30 * cm, 100 * kNm, -700 * kNm)],
    ids=["bottom-short", "top-short"],
)
def test_a_section_that_cannot_carry_the_moment_falls_back(steel_b500s, height, M_bot, M_top) -> None:  # type: ignore[no-untyped-def]
    """No mat verifies when the section is too small for the demand on a face.

    Each candidate is applied and rejected in turn -- the first case runs the
    bottom out of capacity, the second the top -- and the design still returns
    a layout, leaving the check to report DCR > 1 rather than raising.

    The bottom case used to be 200 kN·m, which the design now carries: 72.4 cm²
    a face, inside the 4 % of EN 1992-1-1 §9.2.1.1(3), DCR 0.50. At 500 kN·m
    not even the most either face may hold is enough. The top case used to be
    -600 kN·m, short while that 4 % was read on b*d; on the gross section,
    0.04*1000*300 = 120 cm² a face, a mat carries it (DCR 0.94), and -700
    kN·m is what no mat reaches.
    """
    concrete = Concrete_EN_1992_2004(name="C25", f_c=25 * MPa)
    footing = _strip(Footing, concrete, steel_b500s, "Z1", height=height)
    combo = [Forces(label="C1", M_y=M_bot), Forces(label="C2", M_y=M_top)]
    Node(section=footing, forces=combo).design()

    results = footing.flexure_check_results(combo)
    assert max(max(r.bottom.DCR, r.top.DCR) for r in results) > 1
    assert "As_below_required" in {w.code for w in footing.warnings}


# ---------------------------------------------------------------------------
# Which of the two EN rules governs, and at what depth
# ---------------------------------------------------------------------------


def _en_minimum_per_mille(footing):  # type: ignore[no-untyped-def]
    """A_s,min on the tension face of a metre strip, per mille of the gross section."""
    d = (footing.height - footing.c_c - 10 * mm).to("mm").magnitude
    area = _minimum_flexural_reinforcement_area_EN_1992_2004(footing, d)
    gross = (footing.width * footing.height).to("mm**2").magnitude
    return area / gross * 1000


@pytest.mark.parametrize(
    "height, expected",
    [(40 * cm, 1.097), (60 * cm, 0.932), (90 * cm, 0.900)],
    ids=["h040", "h060", "h090"],
)
def test_the_crack_rule_governs_the_thin_footings_not_the_thick(steel_b500s, height, expected) -> None:  # type: ignore[no-untyped-def]
    """Crack control is written on A_ct = b*h/2, so its ratio goes with k/2, and
    k decays from 1.00 to 0.65 between 300 and 800 mm.

    Both rules are proportional to h, so only k separates them: crack control
    governs while the section is thin, and the 0.9 per mille geometric minimum
    takes over once k has decayed — by 0.90 m it already has.
    """
    concrete = Concrete_EN_1992_2004(name="C25", f_c=25 * MPa)
    footing = _strip(Footing, concrete, steel_b500s, "Z1", height=height)

    assert _en_minimum_per_mille(footing) == pytest.approx(expected, abs=0.001)


def test_the_excess_over_the_geometric_minimum_shrinks_with_depth(steel_b500s: SteelBar) -> None:
    """The same thing read as a trend rather than three numbers."""
    concrete = Concrete_EN_1992_2004(name="C25", f_c=25 * MPa)
    excess = [
        _en_minimum_per_mille(_strip(Footing, concrete, steel_b500s, "Z1", height=h * cm)) - 0.900 for h in (40, 60, 90)
    ]

    assert excess[0] > excess[1] > 0
    assert excess[2] == pytest.approx(0.0, abs=1e-9)


def test_a_footing_with_no_top_moment_is_left_without_top_steel(steel_b500s: SteelBar) -> None:
    """A face that is not in tension is given no minimum, not a smaller one.

    Whether a footing carries top steel is the consumer's call — it is the only
    one that sees both orthogonal sections of the element — so a design given no
    negative moment leaves the top empty rather than reasoning about what
    minimum an unloaded face would be owed.
    """
    concrete = Concrete_EN_1992_2004(name="C25", f_c=25 * MPa)
    footing = _strip(Footing, concrete, steel_b500s, "Z1", height=40 * cm)
    combo = [Forces(label="C1", M_y=200 * kNm)]
    Node(section=footing, forces=combo).design()

    assert footing._A_s_top.magnitude == 0
    assert footing._d_b1_t.magnitude == 0
    assert footing._s_b1_t.magnitude == 0
    assert max(r.top.A_s_min for r in footing.flexure_check_results(combo)) == 0


def test_both_faces_in_tension_both_get_the_crack_minimum(steel_b500s: SteelBar) -> None:
    """A footing bending both ways has a tension zone on each face, so each is
    owed the crack-control minimum."""
    concrete = Concrete_EN_1992_2004(name="C25", f_c=25 * MPa)
    footing = _strip(Footing, concrete, steel_b500s, "Z1", height=40 * cm)
    combo = [Forces(label="M+", M_y=150 * kNm), Forces(label="M-", M_y=-60 * kNm)]
    Node(section=footing, forces=combo).design()

    results = footing.flexure_check_results(combo)
    gross = footing.width * footing.height
    for face in ("bottom", "top"):
        governing = max(getattr(r, face).A_s_min for r in results)
        assert (governing / gross).to("dimensionless").magnitude * 1000 == pytest.approx(1.097, abs=0.001)


# ---------------------------------------------------------------------------
# Whole bars: a footing ends at its edges
# ---------------------------------------------------------------------------


def _mat(width, height, c_c, d_min=12, d_max=12, **kwargs):  # type: ignore[no-untyped-def]
    """An EN C25 / B500 footing with 5 cm of real side cover, unless told otherwise."""
    kwargs.setdefault("edge_cover", 5 * cm)
    return Footing(
        label="Z1",
        concrete=Concrete_EN_1992_2004(name="C25", f_c=25 * MPa),
        steel_bar=SteelBar(name="B500", f_y=500 * MPa),
        width=width,
        height=height,
        c_c=c_c,
        settings=BeamSettings(minimum_longitudinal_diameter=d_min * mm, max_longitudinal_diameter=d_max * mm),
        **kwargs,
    )


def _designed(section, *moments):  # type: ignore[no-untyped-def]
    forces = [Forces(label=f"C{i}", M_y=moment) for i, moment in enumerate(moments)]
    Node(section=section, forces=forces).design()
    return section


@pytest.mark.parametrize(
    "width, span, A_req, n, s, A_s",
    [
        (130, 112, 5.18, 5, 28, 5.65),
        (160, 142, 6.38, 6, 28, 6.79),  # 142 / 5 = 28.4, at a whole centimetre
    ],
)
def test_a_footing_counts_the_whole_bars_that_fit_in_its_span(width, span, A_req, n, s, A_s) -> None:  # type: ignore[no-untyped-def]
    """EN, h = 35 cm, c = 5 cm, c_c = 6.2 cm, Ø12, at the minimum: span = width - 2c - 2h."""
    footing = _designed(_mat(width * cm, 35 * cm, 6.2 * cm), 20 * kNm)
    bottom = footing.flexure_design.bottom
    layer = bottom.layers[0]

    assert footing._bar_span().to("cm").magnitude == pytest.approx(span)
    assert bottom.A_s_req.to("cm**2").magnitude == pytest.approx(A_req, abs=0.01)
    assert layer.n == n
    assert layer.s.to("cm").magnitude == pytest.approx(s)
    assert layer.d_b.to("mm").magnitude == pytest.approx(12)
    assert bottom.A_s.to("cm**2").magnitude == pytest.approx(A_s, abs=0.01)


def test_with_a_free_diameter_the_lightest_whole_mat_wins() -> None:
    """Ø10 to Ø12 at 130 cm: 7Ø10 is 5.50 cm², against the 5.65 cm² of 5Ø12; 18 cm is its widest module."""
    footing = _designed(_mat(130 * cm, 35 * cm, 6.2 * cm, d_min=10), 20 * kNm)
    bottom = footing.flexure_design.bottom
    layer = bottom.layers[0]

    assert (layer.n, layer.d_b.to("mm").magnitude) == (7, pytest.approx(10))
    assert layer.s.to("cm").magnitude == pytest.approx(18)
    assert bottom.A_s.to("cm**2").magnitude == pytest.approx(5.50, abs=0.01)


def test_the_top_at_twice_the_module_counts_its_own_whole_bars() -> None:
    """h = 45 cm, c_c = 6.6 cm, Ø16, 120 cm, span 102 cm: 7 bars at 15 cm below, 4 at 30 cm above."""
    footing = _designed(_mat(120 * cm, 45 * cm, 6.6 * cm, d_min=16, d_max=16), 200 * kNm, -110 * kNm)
    bottom, top = footing.flexure_design.bottom.layers[0], footing.flexure_design.top.layers[0]

    assert (bottom.n, bottom.s.to("cm").magnitude) == (7, pytest.approx(15))
    assert (top.n, top.s.to("cm").magnitude) == (4, pytest.approx(30))


@pytest.mark.parametrize("extra", [{}, {"edge_cover": 5 * cm}])
def test_the_aci_spacing_cap_does_not_read_the_side_cover(extra) -> None:  # type: ignore[no-untyped-def]
    """Table 24.3.2 keeps reading c_c: 380 - 2.5 * 66 = 215 mm, whatever the side cover is."""
    footing = Footing(
        label="Z1",
        concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=120 * cm,
        height=45 * cm,
        c_c=6.6 * cm,
        **extra,
    )
    assert footing._max_bar_spacing().to("mm").magnitude == pytest.approx(215)


@pytest.mark.parametrize(
    "concrete, steel",
    [
        (Concrete_EN_1992_2004(name="C25", f_c=25 * MPa), SteelBar(name="B500", f_y=500 * MPa)),
        (Concrete_ACI_318_19(name="H25", f_c=25 * MPa), SteelBar(name="ADN 420", f_y=420 * MPa)),
        (Concrete_CIRSOC_201_25(name="H25", f_c=25 * MPa), SteelBar(name="ADN 420", f_y=420 * MPa)),
    ],
    ids=["EN", "ACI", "CIRSOC"],
)
@pytest.mark.parametrize("width", [100, 130, 175, 250, 400])
@pytest.mark.parametrize("moment", [30, 150])
def test_a_designed_mat_is_whole_bars_that_fit(concrete, steel, width, moment) -> None:  # type: ignore[no-untyped-def]
    """n is an int, A_s = n * A_b, (n - 1) * s <= span, and the face covers what it was asked for."""
    footing = Footing(
        label="Z1", concrete=concrete, steel_bar=steel, width=width * cm, height=50 * cm, c_c=6 * cm, edge_cover=5 * cm
    )
    _designed(footing, moment * kNm * width / 100, -0.3 * moment * kNm * width / 100)
    span = footing._bar_span().to("cm").magnitude

    for face in (footing.flexure_design.bottom, footing.flexure_design.top):
        assert face.layers
        for layer in face.layers:
            assert isinstance(layer.n, int)
            assert layer.n >= 2
            A_b = math.pi * layer.d_b**2 / 4
            assert layer.A_s.to("cm**2").magnitude == pytest.approx((layer.n * A_b).to("cm**2").magnitude)
            assert (layer.n - 1) * layer.s.to("cm").magnitude <= span + 1e-9
        assert face.A_s.to("cm**2").magnitude == pytest.approx(sum(x.A_s.to("cm**2").magnitude for x in face.layers))
        assert face.A_s >= face.A_s_req


def test_the_capacity_is_the_capacity_of_the_whole_bars() -> None:
    """5Ø12/28 in a 130 cm footing carries what a strip of exactly 5 bars carries, 130 / 26."""
    concrete = Concrete_EN_1992_2004(name="C25", f_c=25 * MPa)
    steel = SteelBar(name="B500", f_y=500 * MPa)
    geometry = {"width": 130 * cm, "height": 35 * cm, "c_c": 6.2 * cm}
    footing = Footing(label="Z", concrete=concrete, steel_bar=steel, edge_cover=5 * cm, **geometry)
    slab = OneWaySlab(label="L", concrete=concrete, steel_bar=steel, **geometry)
    footing.set_slab_longitudinal_rebar_bot(d_b1=12 * mm, s_b1=28 * cm)
    slab.set_slab_longitudinal_rebar_bot(d_b1=12 * mm, s_b1=26 * cm)

    checks = []
    for section in (footing, slab):
        Node(section=section, forces=[Forces(label="C", M_y=40 * kNm)]).check_flexure()
        checks.append(section.flexure_checks[0].bottom)
    assert checks[0].M_capacity.to("kN*m").magnitude == pytest.approx(checks[1].M_capacity.to("kN*m").magnitude)
    assert checks[0].DCR == pytest.approx(checks[1].DCR)


def test_a_spacing_set_by_hand_is_counted_in_the_span_with_two_bars_at_least() -> None:
    footing = _mat(130 * cm, 35 * cm, 6.2 * cm)
    footing.set_slab_longitudinal_rebar_bot(d_b1=12 * mm, s_b1=28 * cm)
    layer = footing.reinforcement.bottom.layers[0]
    assert layer.n == 5 and isinstance(layer.n, int)
    assert layer.n_placed == 5
    assert footing.reinforcement.bottom.A_s.to("cm**2").magnitude == pytest.approx(5.65, abs=0.01)

    narrow = _mat(40 * cm, 35 * cm, 6.2 * cm)  # span 22 cm
    narrow.set_slab_longitudinal_rebar_bot(d_b1=12 * mm, s_b1=30 * cm)
    assert narrow.reinforcement.bottom.layers[0].n == 2


def test_the_side_cover_and_the_clearance_set_the_span() -> None:
    """A c_c that stands in for a depth is no side cover: at 6.2 cm, Ø12/28 would count 4 bars, not 5."""
    footing = _mat(130 * cm, 35 * cm, 6.2 * cm, edge_cover=None)
    assert footing.edge_cover == 6.2 * cm  # defaults to c_c
    assert footing.bend_clearance == 4 * cm
    assert footing._bar_span().to("cm").magnitude == pytest.approx(109.6)
    assert footing._bars_in_layer(28 * cm) == 4

    given = _mat(130 * cm, 35 * cm, 6.2 * cm, edge_cover=7.5 * cm, bend_clearance=5 * cm)
    assert given.c_c == 6.2 * cm  # c_c keeps setting the depth
    assert given._bar_span().to("cm").magnitude == pytest.approx(105)


def test_the_imperial_clearance_is_an_inch_and_a_half() -> None:
    footing = Footing(
        label="Z1",
        concrete=Concrete_ACI_318_19(name="4 ksi", f_c=4000 * psi),
        steel_bar=SteelBar(name="Gr 60", f_y=60000 * psi),
        width=60 * inch,
        height=18 * inch,
        c_c=3 * inch,
    )
    assert footing.bend_clearance == 1.5 * inch
    assert footing._bar_span().to("inch").magnitude == pytest.approx(51)

    _designed(footing, 100 * kip * inch * 12)
    layer = footing.flexure_design.bottom.layers[0]
    assert isinstance(layer.n, int)
    assert (layer.n - 1) * layer.s.to("inch").magnitude <= 51 + 1e-9


def test_the_spacing_for_a_count_gives_at_least_that_many_bars() -> None:
    """floor(span / (n - 1)), and the search may not ask for more bars than fit at s_min."""
    footing = _mat(100 * cm, 40 * cm, 6 * cm)  # span 82 cm
    assert footing._spacing_for_bars(0).magnitude == 0
    for n in range(1, 10):
        spacing = footing._spacing_for_bars(n)
        assert footing._bars_in_layer(spacing) >= max(n, 2)
        assert (footing._bars_in_layer(spacing) - 1) * spacing.to("cm").magnitude <= 82

    assert footing.settings.max_bars_per_layer == 9  # floor(82 / 10) + 1
    assert footing._spacing_for_bars(9) >= footing._min_bar_spacing()


def test_no_mat_is_offered_past_the_span() -> None:
    """Two bars never lie further apart than the span, however far the code lets them."""
    footing = _mat(40 * cm, 35 * cm, 6.2 * cm)  # span 22 cm
    candidates = list(footing._mat_candidates(2 * cm**2, 0 * cm**2))

    assert candidates
    assert max(spacing[0] for spacing, _ in candidates) <= 220


def test_the_fallback_counts_whole_bars_and_never_loses_one() -> None:
    footing = _mat(130 * cm, 35 * cm, 6.2 * cm)
    footing.set_slab_longitudinal_rebar_bot(d_b1=12 * mm, s_b1=28 * cm)
    footing.set_slab_longitudinal_rebar_top(d_b1=10 * mm, s_b1=14 * cm)
    bars_before = footing._n1_b, footing._n1_t

    footing._match_spacings_downward()

    assert footing._s_b1_b == footing._s_b1_t == 14 * cm
    assert footing._n1_b == footing._n1_t == 9
    assert isinstance(footing._n1_b, int)
    assert footing._n1_b >= bars_before[0] and footing._n1_t >= bars_before[1]


def test_what_a_design_reports_is_whole_bars() -> None:
    """layer.n, the option it came from and the totals read the same count."""
    bottom = _designed(_mat(130 * cm, 35 * cm, 6.2 * cm), 20 * kNm).flexure_design.bottom

    assert bottom.layers[0].n == bottom.layers[0].n_placed == bottom.n_bars == bottom.n_bars_placed == 5
    assert bottom.options[0].layers[0].n == 5
    assert bottom.options[0].n_bars == 5


def test_a_slab_still_counts_bars_per_strip() -> None:
    """The strip goes on past its edges: width / s, not a whole number, and no side cover to read."""
    slab = OneWaySlab(
        label="L",
        concrete=Concrete_EN_1992_2004(name="C25", f_c=25 * MPa),
        steel_bar=SteelBar(name="B500", f_y=500 * MPa),
        width=130 * cm,
        height=35 * cm,
        c_c=6.2 * cm,
    )
    slab.set_slab_longitudinal_rebar_bot(d_b1=12 * mm, s_b1=28 * cm)

    assert slab.reinforcement.bottom.layers[0].n == pytest.approx(130 / 28)
    assert slab.reinforcement.bottom.A_s.to("cm**2").magnitude == pytest.approx(5.25, abs=0.01)
    assert slab._spacing_for_bars(5).to("cm").magnitude == pytest.approx(26)
    assert not hasattr(slab, "edge_cover")
