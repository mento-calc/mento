"""Tests for the public design results API (mento.design_results)."""

import math
from typing import Any, Dict

import pytest
from pandas import DataFrame

from mento import (
    Concrete_ACI_318_19,
    Concrete_CIRSOC_201_25,
    Concrete_EN_1992_2004,
    Forces,
    Node,
    RectangularBeam,
    SteelBar,
)
from mento import MPa, cm, kN, kNm, m, mm
from mento.design_results import (
    DesignNotRunError,
    FlexureCheck,
    FlexureDesign,
    FlexureFaceCheck,
    RebarLayer,
    SectionReinforcement,
    ShearCheck,
    ShearDesign,
    StirrupOption,
    envelope_flexure_face,
    envelope_shear,
    format_longitudinal_rebar,
)

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")


@pytest.fixture
def beam() -> RectangularBeam:
    concrete = Concrete_ACI_318_19(name="H25", f_c=25 * MPa)
    steel = SteelBar(name="ADN 420", f_y=420 * MPa)
    return RectangularBeam(
        label="101",
        concrete=concrete,
        steel_bar=steel,
        width=20 * cm,
        height=60 * cm,
        c_c=25 * mm,
    )


@pytest.fixture
def designed_beam(beam: RectangularBeam) -> RectangularBeam:
    node = Node(section=beam, forces=[Forces(label="C1", V_z=80 * kN, M_y=100 * kNm)])
    node.design()
    return beam


# ============================================================================
# RebarLayer
# ============================================================================


def test_rebar_layer_area_matches_the_circle_formula() -> None:
    layer = RebarLayer(n=3, d_b=16 * mm)
    assert layer.A_s.to("cm**2").magnitude == pytest.approx(3 * math.pi * (1.6**2) / 4)


# ============================================================================
# SectionReinforcement — what the section carries, readable without a check
# ============================================================================


def test_reinforcement_is_readable_before_any_check(beam: RectangularBeam) -> None:
    """The whole point of the view: no check has run, and it still answers.

    flexure_design and shear_design raise here; reinforcement must not, because
    it describes the section rather than a result.
    """
    with pytest.raises(DesignNotRunError):
        _ = beam.flexure_design
    with pytest.raises(DesignNotRunError):
        _ = beam.shear_design

    assert isinstance(beam.reinforcement, SectionReinforcement)


def test_reinforcement_reflects_the_longitudinal_setter(beam: RectangularBeam) -> None:
    beam.set_longitudinal_rebar_bot(n1=4, d_b1=16 * mm)

    bottom = beam.reinforcement.bottom
    assert bottom.layers[0].n == 4
    assert bottom.layers[0].d_b.to("mm").magnitude == pytest.approx(16)
    assert bottom.n_bars == 4
    # 4 bars of 16 mm: 4*pi*1.6^2/4 = 8.04 cm²
    assert bottom.A_s.to("cm**2").magnitude == pytest.approx(4 * math.pi * (1.6**2) / 4)


def test_reinforcement_reflects_the_transverse_setter(beam: RectangularBeam) -> None:
    beam.set_transverse_rebar(n_stirrups=2, d_b=10 * mm, s_l=15 * cm)

    stirrups = beam.reinforcement.transverse
    assert stirrups.n_stirrups == 2
    assert stirrups.n_legs == 4
    assert stirrups.d_b.to("mm").magnitude == pytest.approx(10)
    assert stirrups.s_l.to("cm").magnitude == pytest.approx(15)
    assert stirrups.A_v.to("cm**2/m").magnitude > 0


def test_reinforcement_lists_no_layers_for_a_bare_face(beam: RectangularBeam) -> None:
    beam.set_longitudinal_rebar_top(n1=0, d_b1=0 * mm)
    assert beam.reinforcement.top.layers == ()
    assert beam.reinforcement.top.n_bars == 0
    assert str(beam.reinforcement.top) == "no reinforcement"


def test_reinforcement_is_a_value_not_a_live_view(beam: RectangularBeam) -> None:
    """It is a snapshot: changing the section afterwards must not change it."""
    before = beam.reinforcement.transverse
    beam.set_transverse_rebar(n_stirrups=1, d_b=8 * mm, s_l=20 * cm)
    assert beam.reinforcement.transverse != before


def test_reinforcement_matches_the_design_after_a_design_runs(
    designed_beam: RectangularBeam,
) -> None:
    """The two views agree on what the section carries; they differ only in that
    the design also reports what the check demanded."""
    rebar = designed_beam.reinforcement
    flexure = designed_beam.flexure_design
    shear = designed_beam.shear_design

    assert rebar.bottom.layers == flexure.bottom.layers
    assert rebar.bottom.A_s == flexure.bottom.A_s
    assert rebar.top.layers == flexure.top.layers
    assert rebar.transverse.n_stirrups == shear.n_stirrups
    assert rebar.transverse.s_l == shear.s_l
    assert rebar.transverse.A_v == shear.A_v


def test_reinforcement_str_describes_both_faces_and_stirrups(beam: RectangularBeam) -> None:
    beam.set_longitudinal_rebar_bot(n1=3, d_b1=20 * mm)
    beam.set_transverse_rebar(n_stirrups=1, d_b=8 * mm, s_l=20 * cm)
    text = str(beam.reinforcement)
    assert "bottom: 3Ø20" in text
    assert "stirrups: 2 legs Ø8 mm @ 20 cm · 14.2 cm between legs" in text


def test_reinforcement_str_says_so_when_there_are_no_stirrups(beam: RectangularBeam) -> None:
    beam.set_transverse_rebar(n_stirrups=0, d_b=0 * mm, s_l=0 * cm)
    assert str(beam.reinforcement.transverse) == "no stirrups"


def test_rebar_layer_str_is_the_engineering_shorthand() -> None:
    assert str(RebarLayer(n=2, d_b=12 * mm)) == "2Ø12 mm"


def test_a_whole_bar_count_given_as_a_float_reads_as_a_whole_number(beam: RectangularBeam) -> None:
    """A count entered as ``2.0`` -- a spreadsheet cell, a numpy float -- is still 2 bars.

    ``set_longitudinal_rebar_bot(2.0, 16 mm, 1.0, 12 mm)`` stores the counts
    as given. The layers pass the count through as it comes, for the bars
    per metre of a slab strip, and read that way the same beam would print
    "2.0Ø16 mm + 1.0Ø12 mm". A beam is detailed by a whole number of bars
    (see :class:`RebarLayer`), so its layers carry a whole count. The label
    itself printed a float count with its decimals in PR #164
    (``format_longitudinal_rebar(2.0, "Ø16")`` -> "2.0Ø16"): a whole count
    now reads whole whatever its type. A slab layer keeps its fractional
    count and its spacing label.
    """
    beam.set_longitudinal_rebar_bot(2.0, 16 * mm, 1.0, 12 * mm)

    bottom = beam.reinforcement.bottom
    assert str(bottom) == "2Ø16 mm + 1Ø12 mm"
    assert [type(layer.n) for layer in bottom.layers] == [int, int]
    assert bottom.n_bars == 3
    assert str(RebarLayer(n=2.0, d_b=16 * mm)) == "2Ø16 mm"
    assert format_longitudinal_rebar(2.0, "Ø16") == "2Ø16"
    assert str(RebarLayer(n=100 / 12, d_b=10 * mm, s=12 * cm)) == "Ø10 mm/12 cm"


def test_a_layer_detailed_by_a_spacing_reads_as_one_bar_at_that_spacing() -> None:
    """A slab layer carries a spacing; counting its bars is not how it is drawn."""
    layer = RebarLayer(n=6, d_b=12 * mm, s=17 * cm)

    assert str(layer) == "Ø12 mm/17 cm"
    # The area is the bars either way.
    assert layer.A_s.to("cm**2").magnitude == pytest.approx(6 * math.pi * (1.2**2) / 4)


# ============================================================================
# Reading results before running anything
# ============================================================================


def test_flexure_design_before_design_raises(beam: RectangularBeam) -> None:
    with pytest.raises(DesignNotRunError, match="No flexure results yet"):
        beam.flexure_design


def test_shear_design_before_design_raises(beam: RectangularBeam) -> None:
    with pytest.raises(DesignNotRunError, match="No shear results yet"):
        beam.shear_design


# ============================================================================
# Flexure
# ============================================================================


def test_flexure_design_reports_the_designed_bottom_steel(designed_beam: RectangularBeam) -> None:
    flexure = designed_beam.flexure_design

    assert isinstance(flexure, FlexureDesign)
    assert flexure.bottom.A_s == designed_beam._A_s_bot
    assert flexure.bottom.A_s_req == designed_beam._A_s_req_bot
    assert flexure.bottom.A_s >= flexure.bottom.A_s_req


def test_flexure_layers_match_the_private_layer_attributes(designed_beam: RectangularBeam) -> None:
    layers = designed_beam.flexure_design.bottom.layers

    assert layers, "the designed beam should carry bottom reinforcement"
    assert layers[0].n == designed_beam._n1_b
    assert layers[0].d_b == designed_beam._d_b1_b


def test_flexure_layer_areas_add_up_to_the_face_area(designed_beam: RectangularBeam) -> None:
    bottom = designed_beam.flexure_design.bottom
    total = sum(layer.A_s.to("cm**2").magnitude for layer in bottom.layers)

    assert total == pytest.approx(bottom.A_s.to("cm**2").magnitude)
    assert bottom.n_bars == sum(layer.n for layer in bottom.layers)


def test_empty_face_reports_no_layers(designed_beam: RectangularBeam) -> None:
    """A face with no bars has no layers, and says so."""
    top = designed_beam.flexure_design.top

    assert top.layers == ()
    assert top.n_bars == 0
    assert str(top) == "no reinforcement"


def test_flexure_dcr_is_the_worst_of_both_faces(designed_beam: RectangularBeam) -> None:
    flexure = designed_beam.flexure_design
    assert flexure.DCR == max(flexure.bottom.DCR, flexure.top.DCR)


def test_flexure_str_describes_both_faces(designed_beam: RectangularBeam) -> None:
    text = str(designed_beam.flexure_design)
    assert "bottom:" in text and "top:" in text


# ============================================================================
# Shear
# ============================================================================


def test_shear_design_reports_the_designed_stirrups(designed_beam: RectangularBeam) -> None:
    shear = designed_beam.shear_design

    assert isinstance(shear, ShearDesign)
    assert shear.n_stirrups == designed_beam._stirrup_n
    assert shear.d_b == designed_beam._stirrup_d_b
    assert shear.s_l == designed_beam._stirrup_s_l
    assert shear.A_v == designed_beam._A_v


def test_shear_legs_are_twice_the_stirrup_count(designed_beam: RectangularBeam) -> None:
    shear = designed_beam.shear_design
    assert shear.n_legs == shear.n_stirrups * 2


def test_shear_provided_area_covers_the_requirement(designed_beam: RectangularBeam) -> None:
    shear = designed_beam.shear_design
    assert shear.A_v >= shear.A_v_req
    assert shear.DCR <= 1.0


def test_shear_str_is_the_engineering_shorthand(designed_beam: RectangularBeam) -> None:
    shear = designed_beam.shear_design
    assert str(shear).startswith(f"{shear.n_legs} legs Ø")


def test_shear_str_without_stirrups(beam: RectangularBeam) -> None:
    """A beam checked with no stirrups reports that, rather than an empty layout."""
    node = Node(section=beam, forces=[Forces(label="C1", V_z=5 * kN)])
    node.check_shear()

    shear = beam.shear_design
    assert shear.n_stirrups == 0
    assert shear.n_legs == 0
    assert shear.A_v.magnitude == 0
    assert str(shear) == "no stirrups"


# ============================================================================
# Several load combinations: results are the envelope, not the last one checked
# ============================================================================


def _table_dcr(results: DataFrame) -> list[float]:
    """DCR of every combination in a results table, dropping the units row."""
    return [float(value) for value in results["DCR"][1:]]


# The tables round the DCR to three decimals; the results API keeps full precision.
TABLE_ROUNDING = 5e-4


def _two_combinations() -> list[Forces]:
    """Two combinations where the *first* governs both flexure and shear.

    The second one puts the top face in tension and is mild in shear, so it leaves
    the bottom face and the stirrup requirement at zero on its way out.
    """
    return [
        Forces(label="C1", V_z=90 * kN, M_y=100 * kNm),
        Forces(label="C2", V_z=20 * kN, M_y=-30 * kNm),
    ]


@pytest.fixture
def beam_two_combinations(beam: RectangularBeam) -> RectangularBeam:
    Node(section=beam, forces=_two_combinations()).design()
    return beam


def test_flexure_reports_the_combination_that_governs_each_face(
    beam_two_combinations: RectangularBeam,
) -> None:
    beam = beam_two_combinations
    worst = max(_table_dcr(beam.check_flexure(_two_combinations())))

    flexure = beam.flexure_design

    assert flexure.DCR == pytest.approx(worst, abs=TABLE_ROUNDING)
    assert flexure.bottom.DCR == pytest.approx(worst, abs=TABLE_ROUNDING)
    # The last combination checked required nothing at the bottom; the governing one
    # is what the result has to describe.
    assert flexure.bottom.A_s_req.magnitude > 0
    assert flexure.bottom.A_s_min.magnitude > 0
    assert flexure.bottom.A_s >= flexure.bottom.A_s_req


def test_shear_reports_the_combination_that_governs(
    beam_two_combinations: RectangularBeam,
) -> None:
    beam = beam_two_combinations
    worst = max(_table_dcr(beam.check_shear(_two_combinations())))

    shear = beam.shear_design

    assert shear.DCR == pytest.approx(worst, abs=TABLE_ROUNDING)
    assert shear.A_v_req.magnitude > 0
    assert shear.A_v >= shear.A_v_req


def test_envelope_skips_quantities_the_design_code_does_not_set() -> None:
    """A design code that leaves a quantity unset must not break the envelope.

    Both codes shipped today set all of them, so the results are built directly
    rather than through a check. An absent quantity stays absent — enveloping
    must not turn it into a zero that then competes in the max.
    """
    checks = [
        FlexureCheck(
            label="C1",
            bottom=FlexureFaceCheck(A_s_req=4 * cm**2, A_s_min=None, A_s_max=None, DCR=0.5),
            top=FlexureFaceCheck(A_s_req=None, A_s_min=None, A_s_max=None, DCR=0.0),
        )
    ]

    bottom = envelope_flexure_face(checks, "bottom")
    assert bottom.A_s_req == 4 * cm**2
    assert bottom.A_s_min is None
    assert bottom.A_s_max is None
    assert bottom.DCR == 0.5

    shear = envelope_shear([ShearCheck(label="C1", A_v_req=3 * cm**2 / m, A_v_min=None, DCR=0.4)])
    assert shear.A_v_req == 3 * cm**2 / m
    assert shear.A_v_min is None
    assert shear.DCR == 0.4


def test_envelope_takes_the_worst_of_each_quantity_independently() -> None:
    """The combination that governs A_s_req need not be the one that governs DCR,
    so each quantity is enveloped on its own."""
    checks = [
        FlexureCheck(
            label="C1",
            bottom=FlexureFaceCheck(A_s_req=9 * cm**2, A_s_min=2 * cm**2, A_s_max=30 * cm**2, DCR=0.4),
            top=FlexureFaceCheck(A_s_req=0 * cm**2, A_s_min=0 * cm**2, A_s_max=0 * cm**2, DCR=0.0),
        ),
        FlexureCheck(
            label="C2",
            bottom=FlexureFaceCheck(A_s_req=3 * cm**2, A_s_min=5 * cm**2, A_s_max=20 * cm**2, DCR=0.9),
            top=FlexureFaceCheck(A_s_req=0 * cm**2, A_s_min=0 * cm**2, A_s_max=0 * cm**2, DCR=0.0),
        ),
    ]

    bottom = envelope_flexure_face(checks, "bottom")
    assert bottom.A_s_req == 9 * cm**2  # from C1
    assert bottom.A_s_min == 5 * cm**2  # from C2
    assert bottom.DCR == 0.9  # from C2


def test_envelope_of_nothing_is_empty() -> None:
    """No combinations checked: no demand, and nothing to divide by."""
    empty = envelope_flexure_face([], "bottom")
    assert empty.A_s_req is None
    assert empty.DCR == 0.0
    assert envelope_shear([]).DCR == 0.0


@pytest.mark.parametrize(
    "concrete, steel",
    [
        (Concrete_ACI_318_19(name="H25", f_c=25 * MPa), SteelBar(name="ADN 420", f_y=420 * MPa)),
        (Concrete_EN_1992_2004(name="C25", f_c=25 * MPa), SteelBar(name="B500S", f_y=500 * MPa)),
    ],
    ids=["ACI", "EN"],
)
def test_values_only_checks_give_the_same_numbers_as_the_reporting_ones(concrete, steel) -> None:
    """The fast path must not be a different calculation, only a shorter one.

    Both design codes, because each has its own check function and its own
    report half to skip.
    """
    forces = _two_combinations()

    def build() -> RectangularBeam:
        b = RectangularBeam(label="101", concrete=concrete, steel_bar=steel, width=20 * cm, height=60 * cm, c_c=25 * mm)
        b.set_longitudinal_rebar_bot(n1=3, d_b1=20 * mm)
        b.set_transverse_rebar(n_stirrups=1, d_b=8 * mm, s_l=20 * cm)
        return b

    reporting = build()
    reporting.check_shear(forces)
    reporting.check_flexure(forces)

    values = build()
    shear = values.shear_check_results(forces)
    flexure = values.flexure_check_results(forces)

    assert [c.DCR for c in shear] == [c.DCR for c in reporting.shear_checks]
    assert [c.A_v_req for c in shear] == [c.A_v_req for c in reporting.shear_checks]
    assert [c.V_capacity for c in shear] == [c.V_capacity for c in reporting.shear_checks]
    assert [c.bottom.DCR for c in flexure] == [c.bottom.DCR for c in reporting.flexure_checks]
    assert [c.top.DCR for c in flexure] == [c.top.DCR for c in reporting.flexure_checks]
    assert [c.bottom.A_s_req for c in flexure] == [c.bottom.A_s_req for c in reporting.flexure_checks]
    assert [c.bottom.M_capacity for c in flexure] == [c.bottom.M_capacity for c in reporting.flexure_checks]
    assert [c.top.M_capacity for c in flexure] == [c.top.M_capacity for c in reporting.flexure_checks]


def test_values_only_checks_still_produce_readable_designs() -> None:
    """They mark the section as checked, so the design results are available."""
    beam = RectangularBeam(
        label="101",
        concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=20 * cm,
        height=60 * cm,
        c_c=25 * mm,
    )
    beam.set_longitudinal_rebar_bot(n1=3, d_b1=20 * mm)
    beam.set_transverse_rebar(n_stirrups=1, d_b=8 * mm, s_l=20 * cm)

    results = beam.shear_check_results(_two_combinations())
    assert beam.shear_design.DCR == pytest.approx(max(c.DCR for c in results))

    flexure = beam.flexure_check_results(_two_combinations())
    assert beam.flexure_design.bottom.DCR == pytest.approx(max(c.bottom.DCR for c in flexure))


def test_checks_expose_one_result_per_combination(
    beam_two_combinations: RectangularBeam,
) -> None:
    """The per-combination results are public: a caller enveloping them itself
    (mako does) does not have to reach into the beam."""
    beam = beam_two_combinations
    forces = _two_combinations()

    beam.check_flexure(forces)
    beam.check_shear(forces)

    assert [c.label for c in beam.flexure_checks] == [f.label for f in forces]
    assert [c.label for c in beam.shear_checks] == [f.label for f in forces]
    # And the design results agree with enveloping them by hand.
    assert beam.shear_design.DCR == pytest.approx(max(c.DCR for c in beam.shear_checks))
    assert beam.flexure_design.bottom.DCR == pytest.approx(max(c.bottom.DCR for c in beam.flexure_checks))


def test_envelope_resets_between_checks(beam_two_combinations: RectangularBeam) -> None:
    """Checking a milder set of forces afterwards must not keep the earlier worst case."""
    beam = beam_two_combinations
    mild = [Forces(label="C3", V_z=10 * kN, M_y=10 * kNm)]

    beam.check_flexure(mild)
    beam.check_shear(mild)

    assert beam.flexure_design.DCR == pytest.approx(max(_table_dcr(beam.check_flexure(mild))), abs=TABLE_ROUNDING)
    assert beam.shear_design.DCR == pytest.approx(max(_table_dcr(beam.check_shear(mild))), abs=TABLE_ROUNDING)


# ============================================================================
# Results are a snapshot, not a live view
# ============================================================================


def test_results_are_frozen(designed_beam: RectangularBeam) -> None:
    from dataclasses import FrozenInstanceError

    with pytest.raises(FrozenInstanceError):
        designed_beam.flexure_design.bottom.A_s = 0 * cm**2  # type: ignore[misc]


# ============================================================================
# Capacity: the resistance the DCR was formed from
# ============================================================================

_BOTH_CODES = pytest.mark.parametrize(
    "concrete, steel",
    [
        (Concrete_ACI_318_19(name="H25", f_c=25 * MPa), SteelBar(name="ADN 420", f_y=420 * MPa)),
        (Concrete_EN_1992_2004(name="C25", f_c=25 * MPa), SteelBar(name="B500S", f_y=500 * MPa)),
    ],
    ids=["ACI", "EN"],
)


def _three_combinations() -> list[Forces]:
    """The two of ``_two_combinations`` plus one that demands nothing at all."""
    return [*_two_combinations(), Forces(label="C3")]


@_BOTH_CODES
def test_demand_over_dcr_gives_the_capacity_back(concrete, steel) -> None:  # type: ignore[no-untyped-def]
    """The invariant a consumer used to lean on, now guaranteed by construction.

    EN rounds the ratio to three decimals, so the comparison is made on the
    ratio rather than on the moment: a rounded DCR of 0.051 is 1 % off, a
    capacity is not.
    """
    beam = RectangularBeam(label="101", concrete=concrete, steel_bar=steel, width=20 * cm, height=60 * cm, c_c=25 * mm)
    forces = _three_combinations()
    Node(section=beam, forces=forces).design()

    tested = 0
    for check, force in zip(beam.flexure_checks, forces):
        for face in (check.bottom, check.top):
            if face.DCR > 0:
                assert abs(force.M_y) / face.M_capacity == pytest.approx(face.DCR, abs=TABLE_ROUNDING)
                tested += 1
    for check, force in zip(beam.shear_checks, forces):
        if check.DCR > 0:
            assert abs(force.V_z) / check.V_capacity == pytest.approx(check.DCR, abs=TABLE_ROUNDING)
            tested += 1
    # Bottom, top and two shear combinations: nothing above was vacuous.
    assert tested == 4


@_BOTH_CODES
def test_a_face_with_no_demand_still_reports_its_capacity(concrete, steel) -> None:  # type: ignore[no-untyped-def]
    """The case the ratio cannot cover: a footing's top mat against nothing.

    Its DCR is zero, and dividing by it says nothing. The capacity is a real
    number -- and so is the shear resistance of a slab strip with no stirrups
    and no shear, which printed as a blank cell downstream.
    """
    from mento.slab import Footing

    footing = Footing(label="Z1", concrete=concrete, steel_bar=steel, width=100 * cm, height=40 * cm, c_c=50 * mm)
    # The mild negative moment puts minimum reinforcement on the top face; the
    # first combination then finds a reinforced face with no demand on it.
    forces = [Forces(label="C1", M_y=50 * kNm), Forces(label="C2", M_y=-5 * kNm)]
    Node(section=footing, forces=forces).design()

    assert footing.flexure_design.top.A_s.magnitude > 0
    unloaded = footing.flexure_checks[0].top
    assert unloaded.DCR == 0
    assert unloaded.M_capacity.magnitude > 0
    assert footing.flexure_design.top.M_capacity == unloaded.M_capacity

    shear = footing.shear_checks[0]
    assert shear.DCR == 0
    assert shear.V_capacity.magnitude > 0
    assert footing.shear_design.V_capacity.magnitude > 0


@_BOTH_CODES
def test_two_faces_with_the_same_bars_report_the_same_capacity(concrete, steel) -> None:  # type: ignore[no-untyped-def]
    """What dividing by a rounded ratio lost: the same section printed 43.3 on
    one face and 43.4 on the other."""
    beam = RectangularBeam(label="101", concrete=concrete, steel_bar=steel, width=20 * cm, height=60 * cm, c_c=25 * mm)
    beam.set_longitudinal_rebar_bot(n1=3, d_b1=16 * mm)
    beam.set_longitudinal_rebar_top(n1=3, d_b1=16 * mm)

    bottom, top = beam.flexure_check_results([Forces(label="C1", M_y=43 * kNm), Forces(label="C2", M_y=-43 * kNm)])

    assert bottom.bottom.M_capacity == top.top.M_capacity


def test_design_capacity_is_the_one_the_governing_combination_saw() -> None:
    """Under ACI 318-19 the shear resistance moves with the combination, so the
    envelope has to pick one: the one its DCR came from, or the two stop being
    a ratio."""
    beam = RectangularBeam(
        label="101",
        concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=20 * cm,
        height=60 * cm,
        c_c=25 * mm,
    )
    # Axial compression changes V_c; a zero-load combination alone must not
    # change the concrete equation for the same provided stirrups.
    forces = [*_two_combinations(), Forces(label="C3", N_x=100 * kN)]
    Node(section=beam, forces=forces).design()

    capacities = {c.V_capacity for c in beam.shear_checks}
    assert len(capacities) > 1, "the premise: V_c differs between these combinations"

    governing = max(beam.shear_checks, key=lambda c: c.DCR)
    shear = beam.shear_design
    assert shear.V_capacity == governing.V_capacity
    assert abs(forces[0].V_z) / shear.V_capacity == pytest.approx(shear.DCR)

    flexure = beam.flexure_design
    assert abs(forces[0].M_y) / flexure.bottom.M_capacity == pytest.approx(flexure.bottom.DCR)
    assert abs(forces[1].M_y) / flexure.top.M_capacity == pytest.approx(flexure.top.DCR)


def test_envelope_capacity_follows_the_dcr() -> None:
    """Built by hand, so the rule is visible: the governing combination's
    capacity, the smallest among ties, and absent when no combination set one."""

    def shear(label: str, DCR: float, V_capacity: Any) -> ShearCheck:
        return ShearCheck(label=label, A_v_req=None, A_v_min=None, DCR=DCR, V_capacity=V_capacity)

    # The largest capacity belongs to the combination that governs.
    assert envelope_shear([shear("C1", 0.4, 150 * kN), shear("C2", 0.9, 200 * kN)]).V_capacity == 200 * kN
    # Nothing demanded anywhere: the smallest is the safe reading.
    assert envelope_shear([shear("C1", 0.0, 150 * kN), shear("C2", 0.0, 120 * kN)]).V_capacity == 120 * kN
    # A code that did not set it is skipped, and stays absent if none did.
    assert envelope_shear([shear("C1", 0.9, None), shear("C2", 0.4, 150 * kN)]).V_capacity == 150 * kN
    assert envelope_shear([shear("C1", 0.9, None)]).V_capacity is None
    assert envelope_shear([]).V_capacity is None

    def face(DCR: float, M_capacity: Any) -> FlexureFaceCheck:
        return FlexureFaceCheck(A_s_req=None, A_s_min=None, A_s_max=None, DCR=DCR, M_capacity=M_capacity)

    checks = [
        FlexureCheck(label="C1", bottom=face(0.4, 100 * kNm), top=face(0.0, 40 * kNm)),
        FlexureCheck(label="C2", bottom=face(0.9, 90 * kNm), top=face(0.0, 30 * kNm)),
    ]
    assert envelope_flexure_face(checks, "bottom").M_capacity == 90 * kNm
    assert envelope_flexure_face(checks, "top").M_capacity == 30 * kNm
    assert envelope_flexure_face([], "bottom").M_capacity is None


def test_capacity_is_reported_in_the_display_units_of_the_section() -> None:
    """An imperial section reports kip·ft and kip, as every other quantity does."""
    from mento.units import ft, inch, kip, ksi, psi

    beam = RectangularBeam(
        label="101",
        concrete=Concrete_ACI_318_19(name="C4", f_c=4000 * psi),
        steel_bar=SteelBar(name="G60", f_y=60 * ksi),
        width=10 * inch,
        height=16 * inch,
        c_c=1.5 * inch,
    )
    Node(section=beam, forces=[Forces(label="C1", V_z=20 * kip, M_y=40 * kip * ft)]).design()

    assert beam.flexure_design.bottom.M_capacity.units == kip * ft
    assert beam.shear_design.V_capacity.units == kip
    assert beam.flexure_design.bottom.M_capacity.magnitude > 0


# ============================================================================
# A_s_calc: what the moment alone asks for, before the minimum
# ============================================================================


def _footing_under(concrete, steel, M_y):  # type: ignore[no-untyped-def]
    """A metre strip of a 40 cm footing, designed for one moment."""
    from mento.slab import Footing

    footing = Footing(label="Z1", concrete=concrete, steel_bar=steel, width=100 * cm, height=40 * cm, c_c=50 * mm)
    Node(section=footing, forces=[Forces(label="C1", M_y=M_y)]).design()
    return footing


@_BOTH_CODES
def test_a_face_governed_by_its_minimum_still_says_what_the_moment_asked_for(concrete, steel) -> None:  # type: ignore[no-untyped-def]
    """The case the field is for: a footing mat sized by the minimum, barely
    working. A_s_req is the minimum, as bar selection needs; A_s_calc is the
    much smaller area the moment alone demands, as an anchorage needs."""
    face = _footing_under(concrete, steel, 5 * kNm).flexure_design.bottom

    assert face.A_s_req == face.A_s_min
    assert 0 < face.A_s_calc.magnitude
    assert face.A_s_calc < 0.5 * face.A_s_min


@_BOTH_CODES
def test_a_face_governed_by_the_moment_reports_the_same_area_twice(concrete, steel) -> None:  # type: ignore[no-untyped-def]
    face = _footing_under(concrete, steel, 250 * kNm).flexure_design.bottom

    assert face.A_s_calc == face.A_s_req
    assert face.A_s_req > face.A_s_min


@_BOTH_CODES
def test_a_face_with_no_moment_asks_for_nothing(concrete, steel) -> None:  # type: ignore[no-untyped-def]
    """Zero, not None and not the minimum: the top face of a footing bent one way."""
    footing = _footing_under(concrete, steel, 50 * kNm)

    assert footing.flexure_checks[0].top.A_s_calc.magnitude == 0
    assert footing.flexure_design.top.A_s_calc.magnitude == 0


@_BOTH_CODES
def test_a_section_needing_compression_steel_asks_for_the_couple(concrete, steel) -> None:  # type: ignore[no-untyped-def]
    """Beyond the ductility limit the moment is carried as a couple, and the
    tension steel of that couple is what the moment asks for -- so A_s_calc
    is A_s_req there too, above the singly reinforced maximum."""
    beam = RectangularBeam(label="101", concrete=concrete, steel_bar=steel, width=20 * cm, height=40 * cm, c_c=25 * mm)
    beam.set_longitudinal_rebar_bot(n1=4, d_b1=25 * mm)
    beam.set_longitudinal_rebar_top(n1=2, d_b1=16 * mm)

    beam.check_flexure([Forces(label="C1", M_y=220 * kNm)])
    face = beam.flexure_checks[0].bottom

    assert beam._doubly_reinforced
    assert face.A_s_req > face.A_s_min
    assert face.A_s_calc == face.A_s_req


def test_a_s_calc_is_enveloped_like_a_s_req() -> None:
    """The governing combination's, skipping the ones a code did not set."""

    def face(A_s_calc: Any) -> FlexureFaceCheck:
        return FlexureFaceCheck(A_s_req=None, A_s_min=None, A_s_max=None, DCR=0.0, A_s_calc=A_s_calc)

    checks = [
        FlexureCheck(label="C1", bottom=face(3 * cm**2), top=face(None)),
        FlexureCheck(label="C2", bottom=face(5 * cm**2), top=face(None)),
    ]
    assert envelope_flexure_face(checks, "bottom").A_s_calc == 5 * cm**2
    assert envelope_flexure_face(checks, "top").A_s_calc is None
    assert envelope_flexure_face([], "bottom").A_s_calc is None


def test_a_slab_layer_is_computed_per_metre_and_placed_in_whole_bars() -> None:
    """Ø10/15 on a 1 m strip: 6.67 bars, 5.24 cm², for the strength; 7 bars to place.

    A beam's layers place the bars they count.
    """
    from mento import OneWaySlab
    from mento.design_results import placed_bars

    slab = OneWaySlab(
        label="L",
        concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=100 * cm,
        height=20 * cm,
        c_c=25 * mm,
    )
    slab.set_slab_longitudinal_rebar_bot(d_b1=10 * mm, s_b1=15 * cm)
    bottom = slab.reinforcement.bottom
    layer = bottom.layers[0]

    assert layer.n == pytest.approx(100 / 15)
    assert bottom.A_s.to("cm**2").magnitude == pytest.approx(5.236, abs=5e-4)
    assert layer.n_placed == 7
    assert bottom.n_bars_placed == 7
    # A whole count reached through the division stays whole.
    assert placed_bars(100 / 20) == 5
    assert placed_bars(5.000000001) == 5

    beam = RectangularBeam(
        label="V",
        concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=20 * cm,
        height=50 * cm,
        c_c=25 * mm,
    )
    beam.set_longitudinal_rebar_bot(n1=3, d_b1=16 * mm)
    assert beam.reinforcement.bottom.n_bars_placed == beam.reinforcement.bottom.n_bars == 3


def test_a_designed_slab_reports_the_whole_bars_it_places() -> None:
    """The design result and its options place ceil(width / s) bars of each layer."""
    from mento import OneWaySlab
    from mento.design_results import placed_bars

    slab = OneWaySlab(
        label="L",
        concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=100 * cm,
        height=20 * cm,
        c_c=25 * mm,
    )
    Node(section=slab, forces=[Forces(label="U", M_y=30 * kNm)]).design()
    bottom = slab.flexure_design.bottom

    assert bottom.n_bars_placed == sum(placed_bars(layer.n) for layer in bottom.layers)
    assert bottom.n_bars_placed >= bottom.n_bars
    assert bottom.options[0].n_bars_placed == bottom.n_bars_placed


def test_changing_the_bars_by_hand_drops_the_results_until_the_next_check() -> None:
    """The results of the last design described the old section: they go, and a check brings them back.

    A design's own placements keep them, and the reinforcement, which reads
    the section as it is, is always there.
    """
    from mento import OneWaySlab

    beam = RectangularBeam(
        label="V",
        concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=20 * cm,
        height=50 * cm,
        c_c=25 * mm,
    )
    forces = [Forces(label="U", M_y=100 * kNm, V_z=100 * kN)]
    node = Node(section=beam, forces=forces)
    node.design()
    assert beam.flexure_checks and beam.shear_checks

    beam.set_transverse_rebar(n_stirrups=1, d_b=8 * mm, s_l=30 * cm)
    with pytest.raises(DesignNotRunError):
        beam.flexure_design
    with pytest.raises(DesignNotRunError):
        beam.shear_design
    assert beam.flexure_checks == () and beam.shear_checks == ()
    assert str(beam.reinforcement.transverse) == "2 legs Ø8 mm @ 30 cm · 14.2 cm between legs"

    node.check()
    assert beam.flexure_design.DCR > 0 and beam.shear_design.DCR > 0

    slab = OneWaySlab(
        label="L",
        concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=100 * cm,
        height=20 * cm,
        c_c=25 * mm,
    )
    slab_node = Node(section=slab, forces=[Forces(label="U", M_y=20 * kNm)])
    slab_node.design()
    slab.set_slab_longitudinal_rebar_bot(d_b1=12 * mm, s_b1=20 * cm)
    with pytest.raises(DesignNotRunError):
        slab.flexure_design
    slab_node.design()
    slab.set_slab_transverse_rebar(d_b=8 * mm, s_long=20 * cm, s_trans=20 * cm)
    with pytest.raises(DesignNotRunError):
        slab.shear_design


# ============================================================================
# Spacing limits on the public results (new in 1.4.0)
# ============================================================================


def _user_beam() -> RectangularBeam:
    """The wide CIRSOC beam: CIRSOC 201-25, H-25, ADN 420, 150x150 cm, c_c 30 mm."""
    return RectangularBeam(
        label="V1",
        concrete=Concrete_CIRSOC_201_25(name="H-25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=150 * cm,
        height=150 * cm,
        c_c=30 * mm,
    )


def test_shear_design_exposes_the_spacing_limits_of_the_wide_cirsoc_beam() -> None:
    """Both limits are 20 cm, from the halved row of Tabla 9.7.6.2.2 (V_s,req 4828 > 3569 kN)."""
    beam = _user_beam()
    Node(section=beam, forces=[Forces(label="C1", M_y=5000 * kNm, V_z=5000 * kN)]).design()
    shear = beam.shear_design

    assert shear.s_max_l.to("cm").magnitude == pytest.approx(20.0)
    assert shear.s_max_w.to("cm").magnitude == pytest.approx(20.0)
    assert shear.s_max_l_table.to("cm").magnitude == pytest.approx(20.0)
    assert shear.s_max_l_support is None
    assert shear.s_w <= shear.s_max_w and shear.s_l <= shear.s_max_l

    check = beam.shear_checks[0]
    assert check.V_s_req.to("kN").magnitude == pytest.approx(4828.12, abs=0.01)
    assert check.V_s_threshold.to("kN").magnitude == pytest.approx(3568.95, abs=0.01)
    assert check.spacing_halved is True
    assert check.s_max_l_table.to("cm").magnitude == pytest.approx(20.0)
    assert check.s_max_w.to("cm").magnitude == pytest.approx(20.0)

    assert shear.options[0].s_max_l == shear.s_max_l
    assert shear.options[0].s_max_w == shear.s_max_w


def test_shear_design_limits_are_the_envelope_not_the_last_combination() -> None:
    """C2 (V_s,req 161 kN) runs last and leaves 40 cm on the section; C1 holds it to 20."""
    beam = _user_beam()
    forces = [
        Forces(label="C1", M_y=5000 * kNm, V_z=5000 * kN),
        Forces(label="C2", M_y=1000 * kNm, V_z=1500 * kN),
    ]
    Node(section=beam, forces=forces).design()

    assert beam._stirrup_s_max_w.to("cm").magnitude == pytest.approx(40.0)
    shear = beam.shear_design
    assert shear.s_max_w.to("cm").magnitude == pytest.approx(20.0)
    assert shear.s_max_l.to("cm").magnitude == pytest.approx(20.0)
    c1, c2 = beam.shear_checks
    assert (c1.spacing_halved, c2.spacing_halved) == (True, False)
    assert c2.s_max_w.to("cm").magnitude == pytest.approx(40.0)


@pytest.mark.parametrize(
    "code, M_kNm, V_kN, table_cm",
    [("CIRSOC", 300, 100, 21.025), ("ACI", 260, 60, 21.62)],
)
def test_the_governing_along_length_limit_folds_in_the_compression_support_cap(
    code: str, M_kNm: float, V_kN: float, table_cm: float
) -> None:
    """§9.7.6.4.3 caps s at the least dimension of a 20x50 that relies on compression bars."""
    concrete: Concrete_ACI_318_19 = (
        Concrete_CIRSOC_201_25(name="H-25", f_c=25 * MPa)
        if code == "CIRSOC"
        else Concrete_ACI_318_19(name="H25", f_c=25 * MPa)
    )
    beam = RectangularBeam(
        label="D",
        concrete=concrete,
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=20 * cm,
        height=50 * cm,
        c_c=25 * mm,
    )
    Node(section=beam, forces=[Forces(label="C1", M_y=M_kNm * kNm, V_z=V_kN * kN)]).design()
    shear = beam.shear_design

    assert shear.s_max_l_table.to("cm").magnitude == pytest.approx(table_cm, abs=0.005)
    assert shear.s_max_l_support.to("cm").magnitude == pytest.approx(20.0)
    assert shear.s_max_l.to("cm").magnitude == pytest.approx(20.0)
    assert shear.options[0].s_max_l.to("cm").magnitude == pytest.approx(20.0)


def test_aci_limits_take_the_300_mm_cap_on_the_wide_cirsoc_beam() -> None:
    beam = RectangularBeam(
        label="V1",
        concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=150 * cm,
        height=150 * cm,
        c_c=30 * mm,
    )
    Node(section=beam, forces=[Forces(label="C1", M_y=5000 * kNm, V_z=5000 * kN)]).design()
    shear = beam.shear_design
    assert (shear.n_stirrups, shear.n_legs) == (3, 6)
    assert shear.s_max_l.to("cm").magnitude == pytest.approx(30.0)
    assert shear.s_max_w.to("cm").magnitude == pytest.approx(30.0)


def test_en_limits_with_and_without_stirrups() -> None:
    """EN has no threshold; (9.6N) with mento's 400 mm cap and (9.8N); none with no stirrups."""
    beam = RectangularBeam(
        label="V1",
        concrete=Concrete_EN_1992_2004(name="C25", f_c=25 * MPa),
        steel_bar=SteelBar(name="B500S", f_y=500 * MPa),
        width=150 * cm,
        height=150 * cm,
        c_c=30 * mm,
    )
    Node(section=beam, forces=[Forces(label="C1", M_y=5000 * kNm, V_z=5000 * kN)]).design()
    shear = beam.shear_design
    assert shear.s_max_l.to("cm").magnitude == pytest.approx(40.0)
    assert shear.s_max_l_table == shear.s_max_l
    assert shear.s_max_w.to("cm").magnitude == pytest.approx(60.0)
    assert shear.s_max_l_support is None
    check = beam.shear_checks[0]
    assert (check.V_s_req, check.V_s_threshold, check.spacing_halved) == (None, None, None)

    bare = RectangularBeam(
        label="V2",
        concrete=Concrete_EN_1992_2004(name="C25", f_c=25 * MPa),
        steel_bar=SteelBar(name="B500S", f_y=500 * MPa),
        width=30 * cm,
        height=60 * cm,
        c_c=25 * mm,
    )
    bare.set_longitudinal_rebar_bot(n1=3, d_b1=16 * mm)
    Node(section=bare, forces=[Forces(label="C1", V_z=20 * kN)]).check()
    shear = bare.shear_design
    assert (shear.s_max_l, shear.s_max_w, shear.s_max_l_table, shear.s_max_l_support) == (None, None, None, None)


def test_results_keep_their_positional_construction_of_1_3_0() -> None:
    """ADR-0001: the new fields come last, with defaults, so 1.3.0 calls still build."""
    check = ShearCheck("C1", 1 * cm**2 / m, 1 * cm**2 / m, 0.5, 100 * kN)
    assert check.V_s_req is None and check.s_max_w is None and check.spacing_halved is None
    option = StirrupOption(1, 10 * mm, 20 * cm, 30 * cm, 5 * cm**2 / m, 0.1, "stirrups", 0.9)
    assert option.s_max_l is None and option.s_max_w is None
    design = ShearDesign(
        1, 10 * mm, 20 * cm, 5 * cm**2 / m, 4 * cm**2 / m, 2 * cm**2 / m, 0.8, 100 * kN, 30 * cm, "stirrups", ()
    )
    assert (design.s_max_l, design.s_max_w, design.s_max_l_table, design.s_max_l_support) == (None, None, None, None)


def test_envelope_of_the_spacing_fields() -> None:
    """Tightest limits, largest V_s,req with its threshold, halved if any combination was; None with nothing set."""

    def shear(label: str, DCR: float, s_l: Any, s_w: Any, halved: Any, V_s: Any) -> ShearCheck:
        return ShearCheck(
            label=label,
            A_v_req=None,
            A_v_min=None,
            DCR=DCR,
            V_capacity=100 * kN,
            V_s_req=V_s,
            V_s_threshold=None if V_s is None else 300 * kN,
            spacing_halved=halved,
            s_max_l_table=s_l,
            s_max_w=s_w,
        )

    env = envelope_shear(
        [shear("C1", 0.9, 20 * cm, 40 * cm, True, 400 * kN), shear("C2", 0.4, 30 * cm, 30 * cm, False, 100 * kN)]
    )
    assert (env.s_max_l_table, env.s_max_w) == (20 * cm, 30 * cm)
    assert env.V_s_req == 400 * kN
    assert (env.V_s_threshold, env.spacing_halved) == (300 * kN, True)

    empty = envelope_shear([])
    assert (empty.V_s_req, empty.V_s_threshold, empty.spacing_halved, empty.s_max_l_table, empty.s_max_w) == (
        None,
        None,
        None,
        None,
        None,
    )
    nothing = envelope_shear([shear("C1", 0.5, None, None, None, None)])
    assert (nothing.V_s_req, nothing.spacing_halved, nothing.s_max_l_table, nothing.s_max_w) == (None, None, None, None)
    # A row recorded without a demand still counts; with none halved, the envelope is not.
    rows_only = [
        ShearCheck("C1", None, None, 0.5, None, spacing_halved=False),
        ShearCheck("C2", None, None, 0.5, 100 * kN, spacing_halved=True),
    ]
    assert envelope_shear(rows_only).spacing_halved is True
    assert envelope_shear(rows_only[:1]).spacing_halved is False


def test_the_envelope_row_agrees_with_its_demand_and_limits() -> None:
    """The governing DCR on the low row, another combination past the threshold: the envelope is halved.

    Under axial load the combination with the largest DCR need not be the one
    that asks the stirrups for the most shear. The envelope's limits are the
    halved row's, so its ``spacing_halved`` must say so, and ``V_s_req`` must
    read past ``V_s_threshold`` -- as on any single combination.
    """
    common: Dict[str, Any] = {"A_v_req": None, "A_v_min": None, "V_s_threshold": 300 * kN}
    low = ShearCheck(
        "C1",
        DCR=0.95,
        V_capacity=500 * kN,
        V_s_req=200 * kN,
        spacing_halved=False,
        **common,
        s_max_l_table=30 * cm,
        s_max_w=60 * cm,
    )
    high = ShearCheck(
        "C2",
        DCR=0.60,
        V_capacity=900 * kN,
        V_s_req=400 * kN,
        spacing_halved=True,
        **common,
        s_max_l_table=15 * cm,
        s_max_w=30 * cm,
    )
    env = envelope_shear([low, high])

    assert env.V_capacity == 500 * kN  # still the governing DCR's
    assert (env.V_s_req, env.V_s_threshold, env.spacing_halved) == (400 * kN, 300 * kN, True)
    assert (env.s_max_l_table, env.s_max_w) == (15 * cm, 30 * cm)
    assert (env.V_s_req > env.V_s_threshold) is env.spacing_halved


@pytest.mark.parametrize("imperial", [False, True])
@pytest.mark.parametrize("kind", ["length", "force"])
def test_the_scaled_wrap_gives_the_numbers_to_display_gives(kind: str, imperial: bool) -> None:
    """The spacing fields are wrapped with a factor taken once; the result is to_display's."""
    from mento.codes.check_state import _scaled_to_display, to_display

    for value in (0.0, 1.0, 158.66666666666666, 200.0, 3_568_950.0, 4_828_116.67, 1e-3, 12345.678):
        fast = _scaled_to_display(value, kind, imperial)
        slow = to_display(value, kind, imperial)
        assert fast.units == slow.units
        assert fast.magnitude == pytest.approx(slow.magnitude, rel=1e-15, abs=0.0)
