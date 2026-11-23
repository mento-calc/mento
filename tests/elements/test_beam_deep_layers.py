"""Beams with three and four layers of longitudinal bars (groups n5..n8).

A heavily loaded beam -- a transfer beam -- may need more steel than two
layers hold. The search reaches past two layers only when no layout in two
carries the area, and every layer behind the first follows the rule of the
second: two corner bars, no more bars than the layer in front and none thicker,
``layers_spacing`` behind the thickest bar of that layer.
"""

from __future__ import annotations

import math

import pytest

from mento import BeamSettings, BeamSummary, Concrete_ACI_318_19, Forces, Node, RectangularBeam, SteelBar
from mento.rebar import Rebar
from mento.section_geometry import layer_offsets
from mento.summary_tables import SummaryInputError
from mento.units import MPa, cm, kN, kNm, mm


@pytest.fixture()
def concrete() -> Concrete_ACI_318_19:
    return Concrete_ACI_318_19(name="C40", f_c=40 * MPa)


@pytest.fixture()
def steel() -> SteelBar:
    return SteelBar(name="ADN 420", f_y=420 * MPa)


def _beam(
    concrete: Concrete_ACI_318_19, steel: SteelBar, width: float = 30, height: float = 150, **settings
) -> RectangularBeam:
    return RectangularBeam(
        label="VA",
        concrete=concrete,
        steel_bar=steel,
        width=width * cm,
        height=height * cm,
        c_c=25 * mm,
        settings=BeamSettings(**settings) if settings else None,
    )


def _layers(row) -> list[int]:
    """The bars per layer of a search row, nearest the face first, empty layers dropped."""
    counts = [int(row.get(f"n_{group}", 0)) for group in range(1, 9)]
    return [a + b for a, b in zip(counts[0::2], counts[1::2]) if a + b]


def test_layer_offsets_stack_each_layer_behind_the_thickest_bar_in_front() -> None:
    assert layer_offsets([32, 25, 25, 0, 20, 20, 16, 0], 25) == [0, 57, 107, 152]
    # An empty layer in front still leaves its spacing, as the second layer always did.
    assert layer_offsets([16, 0, 0, 0], 25) == [0, 41]


def test_max_layers_setting_is_validated() -> None:
    assert BeamSettings().max_layers == 4
    assert BeamSettings(max_layers=2).max_layers == 2
    for bad in (0, 5, 2.0, True):
        with pytest.raises(ValueError, match="max_layers"):
            BeamSettings(max_layers=bad)


def test_four_layers_set_by_hand_give_area_centroid_and_geometry(concrete, steel) -> None:
    beam = _beam(concrete, steel)
    beam.set_longitudinal_rebar_bot(
        2, 25 * mm, 2, 25 * mm, 2, 25 * mm, 1, 25 * mm, n5=2, d_b5=20 * mm, n7=2, d_b7=16 * mm, n8=1, d_b8=16 * mm
    )
    area = (7 * 25**2 + 2 * 20**2 + 3 * 16**2) * math.pi / 4
    assert beam._A_s_bot.to("mm**2").magnitude == pytest.approx(area)

    # Layer starts: 0, 25 + 25 = 50, 50 + 25 + 25 = 100, 100 + 20 + 25 = 145 mm.
    moment = (4 * 25**2 * 12.5 + 3 * 25**2 * 62.5 + 2 * 20**2 * 110 + 3 * 16**2 * 153) * math.pi / 4
    assert beam._bot_rebar_centroid.to("mm").magnitude == pytest.approx(moment / area)
    assert beam._d_bot.to("mm").magnitude == pytest.approx(1500 - 25 - 8 - moment / area)

    geometry = beam.section_geometry
    assert [len(geometry.bars_on("bottom", layer)) for layer in (1, 2, 3, 4)] == [4, 3, 2, 3]
    y = {layer: geometry.bars_on("bottom", layer)[0].y.to("mm").magnitude for layer in (1, 2, 3, 4)}
    inner = 25 + 8
    assert y == pytest.approx({1: inner + 12.5, 2: inner + 62.5, 3: inner + 110, 4: inner + 153})
    assert {bar.group for bar in geometry.bars_on("bottom", 4)} == {7, 8}
    assert str(beam.reinforcement.bottom).count("+") == 6  # seven groups with bars


def test_search_keeps_two_layers_when_two_carry_the_area(concrete, steel) -> None:
    rebar = Rebar(_beam(concrete, steel))
    table = rebar.longitudinal_rebar(50 * cm**2, face="bot")
    assert all(len(_layers(row)) <= 2 for _, row in table.iterrows())


def test_search_reaches_a_third_layer_only_when_two_fall_short(concrete, steel) -> None:
    # 30 cm wide: four Ø32 per layer at most, 64.3 cm² in two layers.
    rebar = Rebar(_beam(concrete, steel))
    table = rebar.longitudinal_rebar(80 * cm**2, face="bot")
    for _, row in table.iterrows():
        layers = _layers(row)
        assert len(layers) == 3
        assert all(behind <= front for front, behind in zip(layers, layers[1:]))
        assert row["total_as"].to("cm**2").magnitude >= 80
    best = rebar.longitudinal_rebar_design
    assert best["layer_penalty"] == 2


def test_search_reaches_a_fourth_layer_when_three_fall_short(concrete, steel) -> None:
    rebar = Rebar(_beam(concrete, steel))
    rebar.longitudinal_rebar(110 * cm**2, face="bot")
    best = rebar.longitudinal_rebar_design
    assert len(_layers(best)) == 4
    assert best["total_as"].to("cm**2").magnitude >= 110
    # Diameters only decrease from the face inward.
    sizes = [best[f"d_b{g}"].to("mm").magnitude for g in range(1, 9) if best[f"n_{g}"]]
    assert sizes == sorted(sizes, reverse=True)


def test_max_layers_two_keeps_the_old_search(concrete, steel) -> None:
    rebar = Rebar(_beam(concrete, steel, max_layers=2))
    rebar.longitudinal_rebar(80 * cm**2, face="bot")
    best = rebar.longitudinal_rebar_design
    # Nothing in two layers carries it: the fallback is the most two layers hold.
    assert len(_layers(best)) == 2
    assert best["total_as"].to("cm**2").magnitude < 80


def test_max_layers_one_keeps_a_single_layer(concrete, steel) -> None:
    rebar = Rebar(_beam(concrete, steel, max_layers=1))
    table = rebar.longitudinal_rebar(20 * cm**2, face="bot")
    assert all(len(_layers(row)) == 1 for _, row in table.iterrows())


def test_fallback_repeats_the_second_layer_when_four_fall_short(concrete, steel) -> None:
    rebar = Rebar(_beam(concrete, steel))
    rebar.longitudinal_rebar(200 * cm**2, face="bot")
    best = rebar.longitudinal_rebar_design
    assert _layers(best) == [4, 4, 4, 4]
    assert best["total_as"].to("cm**2").magnitude == pytest.approx(16 * math.pi * 3.2**2 / 4)


def test_transfer_beam_is_designed_in_three_layers(concrete, steel) -> None:
    beam = _beam(concrete, steel)
    node = Node(beam, Forces(label="C1", M_y=2600 * kNm, V_z=600 * kN))
    node.design()
    layers = [layer for layer in (1, 2, 3, 4) if beam.section_geometry.bars_on("bottom", layer)]
    assert layers == [1, 2, 3]
    assert beam.flexure_design.bottom.DCR <= 1
    # The report gives each layer its own row.
    rows = beam._flexure_capacity_bot["Bottom reinforcement check"]
    assert "Third layer bars" in rows and "Fourth layer bars" not in rows
    beam.plot()


def test_beam_summary_writes_deep_layer_columns_only_when_used(concrete, steel) -> None:
    shallow = _beam(concrete, steel)
    shallow.set_longitudinal_rebar_bot(2, 25 * mm, 1, 25 * mm)
    deep = _beam(concrete, steel)
    deep.label = "VB"
    deep.set_longitudinal_rebar_bot(2, 25 * mm, 2, 25 * mm, 2, 25 * mm, 0, None, 2, 20 * mm, 1, 20 * mm)
    forces = [Forces(label="C1", M_y=500 * kNm)]

    only_shallow = BeamSummary.from_nodes(concrete, steel, [Node(shallow, forces)])
    assert "n5_bot" not in only_shallow.sections_table.columns

    both = BeamSummary.from_nodes(concrete, steel, [Node(shallow, forces), Node(deep, forces)])
    table = both.sections_table
    assert {"n5_bot", "db6_bot", "n8_top"} <= set(table.columns)
    again = BeamSummary(concrete, steel, table, both.forces_table)
    rebuilt = again._nodes[1].section
    assert rebuilt._bar_groups("bot")[4:6] == ((2, 20 * mm), (1, 20 * mm))
    assert again._rebar_labels(rebuilt)[1].count("++") == 2


def test_beam_summary_rejects_a_fourth_layer_group_without_its_first(concrete, steel) -> None:
    beam = _beam(concrete, steel)
    beam.set_longitudinal_rebar_bot(2, 25 * mm, 0, None, 2, 25 * mm, 0, None, 2, 20 * mm, 0, None, 0, None, 2, 16 * mm)
    with pytest.raises(SummaryInputError, match="n8_bot is given without n7_bot"):
        BeamSummary.from_nodes(concrete, steel, [Node(beam, [Forces(label="C1", M_y=500 * kNm)])])


def test_a_request_past_two_full_layers_still_gets_the_deepened_fallback(concrete, steel) -> None:
    # Two full layers of 8Ø32 hold 128.7 cm²; the bound that skipped every pair
    # past them left no fallback, though four layers hold 257 cm².
    beam = _beam(concrete, steel, width=60, height=200)
    beam.set_transverse_rebar(n_stirrups=1, d_b=10 * mm, s_l=20 * cm)
    rebar = Rebar(beam)
    rebar.longitudinal_rebar(290 * cm**2, face="bot")
    best = rebar.longitudinal_rebar_design
    assert len(_layers(best)) == 4
    assert best["total_as"].to("cm**2").magnitude < 290


@pytest.mark.parametrize(("width", "height", "moment"), [(16, 30, 3000), (12, 24, 900)])
def test_a_section_that_cannot_close_ends_no_further_than_in_two_layers(width, height, moment) -> None:
    """Deeper layers a short section tried are kept only if they come closer than two layers do."""
    from mento.units import ft, inch, kip, ksi, psi

    def design(max_layers: int) -> tuple[str, str, float]:
        beam = RectangularBeam(
            label="B",
            concrete=Concrete_ACI_318_19(name="4000", f_c=4000 * psi),
            steel_bar=SteelBar(name="60", f_y=60 * ksi),
            width=width * inch,
            height=height * inch,
            c_c=1.5 * inch,
            settings=BeamSettings(unit_system="imperial", max_layers=max_layers),
        )
        Node(beam, Forces(label="C", M_y=moment * kip * ft, V_z=20 * kip)).design()
        return str(beam.reinforcement.bottom), str(beam.reinforcement.top), beam.flexure_design.DCR

    deep, shallow = design(4), design(2)
    assert deep[2] <= shallow[2] + 1e-9
    assert deep == shallow


def test_a_deep_layer_narrowed_by_the_bends_is_held_to_the_face_limit() -> None:
    fits = Rebar._deep_layer_fits
    # As wide as the first layer: it fits, having fewer and thinner bars.
    assert fits(230.0, 230.0, 2, 32.0, 2, 32.0, 32.0)
    # Narrower: 4Ø32 in 226 mm leave 32.67 mm, enough for 32; in 224 mm, 32 exactly; in 220 mm, 30.67.
    assert fits(226.0, 230.0, 2, 32.0, 2, 32.0, 32.0)
    assert fits(224.0, 230.0, 2, 32.0, 2, 32.0, 32.0)
    assert not fits(220.0, 230.0, 2, 32.0, 2, 32.0, 32.0)
