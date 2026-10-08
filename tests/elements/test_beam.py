import math
import warnings
from pathlib import Path
from typing import Any
from unittest.mock import patch

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
from matplotlib.colors import to_rgba
from matplotlib.patches import Circle, FancyBboxPatch, Rectangle
from pint import Quantity

from mento.beam import RectangularBeam
from mento.codes.ACI_318_19_beam import (
    _flexure_capacity_ACI_318_19,
    _flexure_ductile_ACI_318_19,
    _minimum_flexural_reinforcement_ratio_ACI_318_19,
)
from mento.codes.EN_1992_2004_beam import (
    _compression_zone_limits_EN_1992_2004,
    _initialize_variables_EN_1992_2004,
    _simple_determine_nominal_moment_EN_1992_2004,
)
from mento.codes.flexure_design import _best_visited_pair
from mento.codes.registry import design_code
from mento.forces import Forces
from mento.material import (
    Concrete_ACI_318_19,
    Concrete_CIRSOC_201_25,
    Concrete_EN_1992_2004,
    SteelBar,
)
from mento.node import Node
from mento.plots.sections import _format_rebar_layer_text
from mento.precompute import section_floats
from mento.rebar import Rebar
from mento.results import CUSTOM_COLORS, DocumentBuilder
from mento.settings import BeamSettings
from mento.units import MPa, cm, ft, inch, kip, kN, kNm, ksi, mm, psi
from tests.helpers import (
    _flexural_reinforcement_in_pint,
    _nominal_moment_double_in_pint,
    _nominal_moment_simple_in_pint,
    us,
)


@pytest.fixture()
def beam_example_EN_1992_2004_02() -> RectangularBeam:
    concrete = Concrete_EN_1992_2004(name="C35", f_c=35 * MPa)
    steelBar = SteelBar(name="B500S", f_y=500 * MPa)
    section = RectangularBeam(
        label="B_Example_EN_02",
        concrete=concrete,
        steel_bar=steelBar,
        width=30 * cm,
        height=40 * cm,
        c_c=3.8 * cm,
    )
    return section


@pytest.fixture()
def beam_example_EN_1992_2004_03() -> RectangularBeam:
    concrete = Concrete_EN_1992_2004(name="C60", f_c=60 * MPa)
    steelBar = SteelBar(name="B400S", f_y=400 * MPa)
    section = RectangularBeam(
        label="B_Example_EN_03",
        concrete=concrete,
        steel_bar=steelBar,
        width=30 * cm,
        height=50 * cm,
        c_c=3 * cm,
    )
    return section


@pytest.fixture()
def beam_example_CIRSOC_201_2025() -> RectangularBeam:
    concrete = Concrete_CIRSOC_201_25(name="H25", f_c=25 * MPa)
    steel_bar = SteelBar(name="ADN 420", f_y=420 * MPa)
    section = RectangularBeam(
        label="Test",
        concrete=concrete,
        steel_bar=steel_bar,
        width=20 * cm,
        height=60 * cm,
        c_c=2.5 * cm,
    )
    return section


def build_metric_beam(settings: BeamSettings | None = None) -> RectangularBeam:
    concrete = Concrete_ACI_318_19(name="H30", f_c=30 * MPa)
    steel = SteelBar(name="ADN 420", f_y=420 * MPa)
    return RectangularBeam(
        label="additional",
        concrete=concrete,
        steel_bar=steel,
        width=30 * cm,
        height=50 * cm,
        c_c=40 * mm,
        settings=settings,
    )


@pytest.mark.parametrize(
    ("n_stirrups", "d_b", "s_l", "expected_exception", "message"),
    [
        pytest.param(0, 8 * mm, 20 * cm, ValueError, "n_stirrups", id="zero-stirrups"),
        pytest.param(-1, 8 * mm, 20 * cm, ValueError, "n_stirrups", id="negative-stirrups"),
        pytest.param(1.5, 8 * mm, 20 * cm, TypeError, "n_stirrups", id="float-stirrups"),
        pytest.param(True, 8 * mm, 20 * cm, TypeError, "n_stirrups", id="boolean-stirrups"),
        pytest.param(1, 0 * mm, 20 * cm, ValueError, "d_b", id="zero-diameter"),
        pytest.param(1, -8 * mm, 20 * cm, ValueError, "d_b", id="negative-diameter"),
        pytest.param(1, 8 * mm, 0 * cm, ValueError, "s_l", id="zero-spacing"),
        pytest.param(1, 8 * mm, -20 * cm, ValueError, "s_l", id="negative-spacing"),
        pytest.param(1, 8 * MPa, 20 * cm, TypeError, "d_b", id="diameter-wrong-units"),
        pytest.param(1, 8 * mm, 20 * MPa, TypeError, "s_l", id="spacing-wrong-units"),
        pytest.param(1, 8, 20 * cm, TypeError, "d_b", id="diameter-not-quantity"),
        pytest.param(1, 8 * mm, 20, TypeError, "s_l", id="spacing-not-quantity"),
        pytest.param(
            1,
            float("nan") * mm,
            20 * cm,
            ValueError,
            "d_b",
            id="nan-diameter",
        ),
        pytest.param(
            1,
            8 * mm,
            float("inf") * cm,
            ValueError,
            "s_l",
            id="infinite-spacing",
        ),
    ],
)
def test_set_transverse_rebar_rejects_invalid_inputs(
    n_stirrups,
    d_b,
    s_l,
    expected_exception,
    message,
) -> None:
    beam = build_metric_beam()

    with pytest.raises(expected_exception, match=message):
        beam.set_transverse_rebar(
            n_stirrups=n_stirrups,
            d_b=d_b,
            s_l=s_l,
        )


def test_set_transverse_rebar_accepts_numpy_integer() -> None:
    beam = build_metric_beam()

    beam.set_transverse_rebar(
        n_stirrups=np.int64(1),
        d_b=8 * mm,
        s_l=20 * cm,
    )

    stirrups = beam.reinforcement.transverse
    assert stirrups.n_stirrups == 1
    assert type(stirrups.n_stirrups) is int
    assert stirrups.A_v.to("cm**2/m").magnitude == pytest.approx(5.0265, rel=1e-4)


def test_set_transverse_rebar_invalid_input_preserves_previous_rebar() -> None:
    beam = build_metric_beam()
    beam.set_transverse_rebar(
        n_stirrups=1,
        d_b=8 * mm,
        s_l=20 * cm,
    )

    previous_rebar = beam.reinforcement.transverse

    with pytest.raises(ValueError, match="s_l"):
        beam.set_transverse_rebar(
            n_stirrups=2,
            d_b=10 * mm,
            s_l=0 * cm,
        )

    assert beam.reinforcement.transverse == previous_rebar


def test_beam_respects_provided_settings_unit_system() -> None:
    settings = BeamSettings(unit_system="imperial", max_bars_per_layer=3)
    beam = build_metric_beam(settings=settings)

    assert beam.settings.unit_system == "metric"
    assert beam.settings.max_bars_per_layer == 3
    assert beam.mode == "beam"


def test_rebar_designer_factory_returns_rebar() -> None:
    beam = build_metric_beam()

    assert isinstance(beam._create_rebar_designer(), Rebar)


def test_initialize_longitudinal_rebar_attributes_metric_defaults() -> None:
    beam = build_metric_beam()

    rebar = beam.reinforcement
    assert rebar.bottom.layers[0].n == 2
    assert rebar.top.layers[0].n == 2
    assert rebar.bottom.layers[0].d_b.magnitude == pytest.approx(8)
    assert rebar.top.layers[0].d_b.magnitude == pytest.approx(8)


def test_set_transverse_rebar_zero_spacing_clears_stirrups() -> None:
    beam = build_metric_beam()
    beam.set_transverse_rebar(n_stirrups=1, d_b=8 * mm, s_l=20 * cm)
    assert beam.reinforcement.transverse.A_v.to("cm**2/m").magnitude > 0

    # Clearing the stirrups must not divide by the zero spacing
    beam.set_transverse_rebar(n_stirrups=0, d_b=0 * mm, s_l=0 * cm)

    stirrups = beam.reinforcement.transverse
    assert stirrups.n_stirrups == 0
    assert stirrups.d_b.to("mm").magnitude == 0
    assert stirrups.s_l.to("cm").magnitude == 0
    assert stirrups.A_v.to("cm**2/m").magnitude == 0


def test_set_transverse_rebar_defaults_clear_stirrups_imperial(
    beam_example_imperial: RectangularBeam,
) -> None:
    beam_example_imperial.set_transverse_rebar(n_stirrups=1, d_b=0.5 * inch, s_l=6 * inch)
    assert beam_example_imperial.reinforcement.transverse.A_v.to("inch**2/ft").magnitude > 0

    beam_example_imperial.set_transverse_rebar()

    stirrups = beam_example_imperial.reinforcement.transverse
    assert stirrups.n_stirrups == 0
    assert stirrups.s_l.to("inch").magnitude == 0
    assert stirrups.A_v.to("inch**2/ft").magnitude == 0


def _high_strength_beam(label: str) -> RectangularBeam:
    """A 30x60 H-80 beam: f'c = 80 MPa, so sqrt(f'c) = 8.94 > the 8.3 of §22.5.3.1."""
    concrete = Concrete_ACI_318_19(name="H80", f_c=80 * MPa)
    steel_bar = SteelBar(name="ADN 420", f_y=420 * MPa)
    beam = RectangularBeam(
        label=label,
        concrete=concrete,
        steel_bar=steel_bar,
        width=30 * cm,
        height=60 * cm,
        c_c=25 * mm,
    )
    beam.set_longitudinal_rebar_bot(n1=3, d_b1=20 * mm)
    return beam


def test_shear_check_caps_sqrt_f_c_without_min_web_reinforcement() -> None:
    """ACI 318-19 §22.5.3.1 / CIRSOC 201-25 art. 22.5.3.1: sqrt(f'c) <= 8.3 MPa for V_c.

    The beam has no stirrups, so Table 22.5.5.1 row (c) applies and §22.5.3.2
    does not: the root is 8.3, not sqrt(80) = 8.944. rho_w and lambda_s are read
    off the beam so the assertion is about the clause and not about mento's
    effective depth; only the root is asserted by hand.

    Negative control: before the cap was applied mento returned the uncapped
    value, 7.8 % higher, so this test fails without the change.
    """
    beam = _high_strength_beam("HS-NOAV")
    # No stirrups at all -- say so, as the other no-rebar tests do.
    beam.set_transverse_rebar(n_stirrups=0, d_b=0 * mm, s_l=0 * mm)
    Node(section=beam, forces=Forces(label="ELU", V_z=60 * kN)).check_shear()

    assert beam._A_v_min.magnitude == pytest.approx(0.0)  # so row (c), and no exception
    rho_w = beam._rho_w.magnitude
    lambda_s = beam._lambda_s
    capped = 0.66 * lambda_s * rho_w ** (1 / 3) * 8.3
    uncapped = 0.66 * lambda_s * rho_w ** (1 / 3) * math.sqrt(80.0)

    assert beam._k_c_min.to("MPa").magnitude == pytest.approx(capped, rel=1e-9)
    assert capped == pytest.approx(uncapped / math.sqrt(80.0) * 8.3, rel=1e-12)
    assert beam._k_c_min.to("MPa").magnitude < uncapped


def test_shear_check_lifts_the_cap_with_min_web_reinforcement() -> None:
    """§22.5.3.2: a beam carrying A_v,min of Table 9.6.3.4 keeps the full root.

    Same section with 1eO10/20 (7.85 cm2/m) against an A_v,min of 3.96 cm2/m,
    and V_u above the §9.6.3.1 threshold so A_v,min is actually required. Rows
    (a)/(b) then apply and row (a) governs: 0.17*sqrt(80) = 1.5205 MPa.
    """
    beam = _high_strength_beam("HS-AV")
    beam.set_transverse_rebar(n_stirrups=1, d_b=10 * mm, s_l=20 * cm)
    Node(section=beam, forces=Forces(label="ELU", V_z=250 * kN)).check_shear()

    # A_v,min = max(0.062*sqrt(80), 0.35)/420*300 = 3.96 cm2/m, and A_v = 7.85.
    assert beam._A_v_min.to("cm**2/m").magnitude == pytest.approx(3.9612, rel=1e-4)
    assert beam._A_v.to("cm**2/m").magnitude > beam._A_v_min.to("cm**2/m").magnitude

    rho_w = beam._rho_w.magnitude
    row_a = 0.17 * math.sqrt(80.0)
    row_b = 0.66 * rho_w ** (1 / 3) * math.sqrt(80.0)
    assert beam._k_c_min.to("MPa").magnitude == pytest.approx(max(row_a, row_b), rel=1e-9)
    assert beam._k_c_min.to("MPa").magnitude == pytest.approx(1.520526, rel=1e-6)


def test_shear_design_CIRSOC_201_2025(
    beam_example_CIRSOC_201_2025: RectangularBeam,
) -> None:
    f = Forces(label="ELU_01", V_z=120 * kN, N_x=0 * kN)
    node = Node(section=beam_example_CIRSOC_201_2025, forces=f)
    results = node.design_shear()

    # Vs,req = (120 - 72.04)/0.75 = 63.95 kN < 0.33*sqrt(25)*200*565 = 186.45 kN (Table
    # 9.7.6.2.2): s_max = d/2 = 28.25 cm, so Ø6 c/20 -> Av = 2*0.283/0.20 = 2.83 cm²/m.
    assert results.iloc[1]["Av,min"] == pytest.approx(1.67, rel=1e-2)
    assert results.iloc[1]["Av,req"] == pytest.approx(2.69, rel=1e-2)
    assert results.iloc[1]["Av"] == pytest.approx(2.83, rel=1e-2)
    assert results.iloc[1]["ØVc"] == pytest.approx(72.04, rel=1e-2)
    assert results.iloc[1]["ØVs"] == pytest.approx(50.32, rel=1e-2)
    assert results.iloc[1]["ØVn"] == pytest.approx(122.36, rel=1e-2)
    assert results.iloc[1]["ØVmax"] == pytest.approx(351.71, rel=1e-2)
    assert results.iloc[1]["DCR"] == pytest.approx(0.981, rel=1e-2)

    assert results.iloc[1]["Vu≤ØVmax"] is True
    assert results.iloc[1]["Vu≤ØVn"] is True

    # Design result
    shear = beam_example_CIRSOC_201_2025.shear_design
    assert shear.n_stirrups == 1
    assert shear.d_b.to("mm").magnitude == 6
    assert shear.s_l.to("cm").magnitude == 20


def test_shear_spacing_threshold_compares_nominal_vs() -> None:
    """Table 9.7.6.2.2 compares the NOMINAL Vs,req = (Vu - phi*Vc)/phi with 0.33*sqrt(f'c)*bw*d.

    Vu is set so that phi*Vs = 0.9 times the threshold, i.e. Vs = 1.2 times it: the
    spacing limits must halve (d/4 along, d/2 across). Comparing phi*Vs, as Mento did
    before, would keep them at d/2 and d.
    """
    concrete = Concrete_ACI_318_19(name="H25", f_c=25 * MPa)
    steel_bar = SteelBar(name="ADN 420", f_y=420 * MPa)
    beam = RectangularBeam(
        label="T1",
        concrete=concrete,
        steel_bar=steel_bar,
        width=30 * cm,
        height=60 * cm,
        c_c=25 * mm,
    )
    beam.set_longitudinal_rebar_bot(n1=3, d_b1=20 * mm)
    beam.set_transverse_rebar(n_stirrups=1, d_b=10 * mm, s_l=10 * cm)
    # phi*Vc does not depend on Vu (N_u = 0) once Vu is above the 9.6.3.1 threshold
    # (below it Av,min = 0 and Table 22.5.5.1 changes row): read it from the check itself.
    probe = Node(section=beam, forces=Forces(label="P", V_z=300 * kN)).check_shear()
    phi_V_c = probe.iloc[1]["ØVc"]  # kN
    d = beam._d_shear.to("mm").magnitude
    threshold = 0.33 * math.sqrt(25) * 300 * d / 1000  # kN
    V_u = phi_V_c + 0.9 * threshold

    Node(section=beam, forces=Forces(label="ELU", V_z=V_u * kN)).check_shear()
    # rel 1e-3: the results table rounds ØVc to 0.01 kN.
    assert beam._V_s_req.to("kN").magnitude == pytest.approx(1.2 * threshold, rel=1e-3)
    assert beam._stirrup_s_max_l.to("mm").magnitude == pytest.approx(min(d / 4, 300), rel=1e-6)
    assert beam._stirrup_s_max_w.to("mm").magnitude == pytest.approx(min(d / 2, 300), rel=1e-6)

    # The design path reads the same Vs,req: the spacing it picks respects d/4.
    Node(section=beam, forces=Forces(label="ELU", V_z=V_u * kN)).design_shear()
    assert beam.shear_design.s_l.to("mm").magnitude <= d / 4 + 1e-6


def test_shear_spacing_threshold_uses_the_si_coefficient_0_33() -> None:
    """ACI 318-19 Table 9.7.6.2.2 in SI: the limits halve past 0.33*sqrt(f'c)*bw*d, not 0.083.

    Beam 20x60, f'c = 25 MPa, fy = 420 MPa, Vu = 120 kN. With d = 559 mm,
    phi*Vc = 0.75*0.17*sqrt(25)*200*559 = 71.3 kN, so Vs,req = (120 - 71.3)/0.75
    = 65 kN, well under 0.33*sqrt(25)*200*559 = 184 kN: s_max,l = d/2, s_max,w = d.
    Read against 0.083*sqrt(f'c)*bw*d = 46 kN -- the coefficient of §9.6.3.1, which
    1.2.0 used -- the same beam came out at d/4. Both the check and the design have
    to read the table the same way.
    """
    concrete = Concrete_ACI_318_19(name="H25", f_c=25 * MPa)
    steel_bar = SteelBar(name="ADN 420", f_y=420 * MPa)
    force = Forces(label="ELU", V_z=120 * kN)

    designed = RectangularBeam(
        label="V1", concrete=concrete, steel_bar=steel_bar, width=20 * cm, height=60 * cm, c_c=25 * mm
    )
    Node(section=designed, forces=force).design()
    d = designed._d_shear.to("mm").magnitude
    V_s_req = designed._V_s_req.to("kN").magnitude
    assert V_s_req > 0.083 * math.sqrt(25) * 200 * d / 1000
    assert V_s_req < 0.33 * math.sqrt(25) * 200 * d / 1000
    assert designed._stirrup_s_max_l.to("mm").magnitude == pytest.approx(d / 2)
    assert designed._stirrup_s_max_w.to("mm").magnitude == pytest.approx(d)
    assert designed.shear_design.s_l == 27 * cm

    # The check alone, on stirrups set by hand: the same limits (max_stirrup_spacing
    # is called from check_shear too).
    checked = RectangularBeam(
        label="V2", concrete=concrete, steel_bar=steel_bar, width=20 * cm, height=60 * cm, c_c=25 * mm
    )
    checked.set_longitudinal_rebar_bot(n1=2, d_b1=12 * mm)
    checked.set_transverse_rebar(n_stirrups=1, d_b=10 * mm, s_l=25 * cm)
    Node(section=checked, forces=force).check_shear()
    d_check = checked._d_shear.to("mm").magnitude
    assert checked._stirrup_s_max_l.to("mm").magnitude == pytest.approx(d_check / 2)
    assert checked._stirrup_s_max_w.to("mm").magnitude == pytest.approx(d_check)


def test_shear_design_spacing_along_width_wide_beam() -> None:
    """A wide section needs more than one stirrup to keep its legs within s_max,w.

    Regression test for issue #94. ``transverse_rebar`` sized the stirrups from the
    required area alone, so a 50 cm beam came back with a single two-legged stirrup whose
    legs sat 44 cm apart, against the 28 cm ACI 318-19 Table 9.7.6.2.2 allows once V_s
    passes 0.33*sqrt(f_c)*b_w*d. The check reported the violation; the design did not
    avoid it.

    Vu = 700 kN gives Vs,req = (700 - phi*Vc)/phi = 695 kN > 0.33*5*500*561 = 463 kN, so
    the limit across the width is d/2 = 28.05 cm. (The original 350 kN only crossed the
    threshold because Mento compared 0.083*sqrt(f_c) with phi*Vs; with Vs,req = 228 kN a
    single stirrup with legs 44 cm apart is within d = 56 cm and is correct.)
    """
    concrete = Concrete_ACI_318_19(name="H25", f_c=25 * MPa)
    steel_bar = SteelBar(name="ADN 420", f_y=420 * MPa)
    beam = RectangularBeam(
        label="W1",
        concrete=concrete,
        steel_bar=steel_bar,
        width=50 * cm,
        height=60 * cm,
        c_c=25 * mm,
    )
    node = Node(section=beam, forces=Forces(label="ELU_01", V_z=700 * kN, M_y=100 * kNm))
    results = node.design_shear()

    # Two stirrups, four legs: one stirrup cannot span 50 cm within the limit.
    assert beam.shear_design.n_stirrups == 2
    assert beam.shear_design.n_legs == 4
    # (50 - 2*2.5 - 1.0) / (4 - 1) = 14.67 cm between adjacent legs.
    assert beam._stirrup_s_w.to("cm").magnitude == pytest.approx(14.67, rel=1e-2)
    assert beam._stirrup_s_max_w.to("cm").magnitude == pytest.approx(28.05, rel=1e-2)
    assert beam._stirrup_s_w <= beam._stirrup_s_max_w

    # The layout still carries the demand it was sized for.
    assert float(results.iloc[1]["DCR"]) <= 1.0


def test_stirrup_spacing_caps_are_declared_per_code() -> None:
    """Table 9.7.6.2.2 caps come from each code's registry entry: ACI 318-19
    600/300 mm (24/12 in.), CIRSOC 201-25 400/200 mm."""
    from mento.codes.registry import design_code

    aci = design_code(Concrete_ACI_318_19(name="H25", f_c=25 * MPa)).stirrup_spacing_caps
    cirsoc = design_code(Concrete_CIRSOC_201_25(name="H25", f_c=25 * MPa)).stirrup_spacing_caps
    aci_imperial = Concrete_ACI_318_19(name="C4", f_c=4000 * psi)

    assert [c.to("mm").magnitude for c in aci(Concrete_ACI_318_19(name="H25", f_c=25 * MPa))] == [600, 300]
    assert [c.to("inch").magnitude for c in aci(aci_imperial)] == [24, 12]
    assert [c.to("mm").magnitude for c in cirsoc(Concrete_CIRSOC_201_25(name="H25", f_c=25 * MPa))] == [400, 200]


def test_flexural_min_fy_caps_are_declared_per_code() -> None:
    """The f_y cap inside A_s,min comes from each code's registry entry:
    ACI 318-19 §9.6.1.2 550 MPa (80,000 psi), CIRSOC 201-25 §9.6.1.2 500 MPa."""
    from mento.codes.registry import design_code

    aci_metric = Concrete_ACI_318_19(name="H25", f_c=25 * MPa)
    aci_imperial = Concrete_ACI_318_19(name="C4", f_c=4000 * psi)
    cirsoc_metric = Concrete_CIRSOC_201_25(name="H25", f_c=25 * MPa)

    aci = design_code(aci_metric).flexural_min_fy_cap
    cirsoc = design_code(cirsoc_metric).flexural_min_fy_cap

    assert aci(aci_metric).to("MPa").magnitude == 550
    assert aci(aci_imperial).to("psi").magnitude == 80_000
    assert cirsoc(cirsoc_metric).to("MPa").magnitude == 500


@pytest.mark.parametrize(
    ("concrete_class", "f_y_allowed"),
    [(Concrete_ACI_318_19, 550.0), (Concrete_CIRSOC_201_25, 500.0)],
)
def test_minimum_flexural_reinforcement_applies_the_codes_fy_cap(concrete_class: type, f_y_allowed: float) -> None:
    """A beam with a 600 MPa steel: §9.6.1.2 does not let all of it into A_s,min.

    f_c = 40 MPa, so the sqrt term governs in every reading:
    0.25*sqrt(40) = 1.58114, over 550 -> 2.8748e-3 and over 500 -> 3.1623e-3,
    against the 2.6352e-3 that the uncapped 600 would give. Only the ratio is
    checked: A_s,min = rho_min*b*d brings in the effective depth, which is the
    beam's business and not this clause's.
    """
    beam = RectangularBeam(
        label="fy600",
        concrete=concrete_class(name="H40", f_c=40 * MPa),
        steel_bar=SteelBar(name="ATR 600", f_y=600 * MPa),
        width=30 * cm,
        height=60 * cm,
        c_c=25 * mm,
    )

    # M_u in the beam's canonical unit (N*mm); only its being non-zero matters.
    rho_min = _minimum_flexural_reinforcement_ratio_ACI_318_19(beam, 100e6)

    expected = max(0.25 * math.sqrt(40.0) / f_y_allowed, 1.4 / f_y_allowed)
    assert rho_min == pytest.approx(expected, rel=1e-12)
    # Without the cap the minimum would come out light: -8.3 % under ACI,
    # -16.7 % under CIRSOC.
    assert rho_min > 0.25 * math.sqrt(40.0) / 600.0


def test_minimum_flexural_reinforcement_fy_cap_in_us_units() -> None:
    """ACI 318-19 §9.6.1.2 in-lb: the cap is 80,000 psi.

    f_c = 6000 psi with a Grade 100 bar: 3*sqrt(6000)/80000 = 2.9047e-3.
    """
    beam = RectangularBeam(
        label="G100",
        concrete=Concrete_ACI_318_19(name="C6", f_c=6000 * psi),
        steel_bar=SteelBar(name="G100", f_y=100 * ksi),
        width=12 * inch,
        height=24 * inch,
        c_c=1.5 * inch,
    )

    # M_u in lb*in, non-zero.
    rho_min = _minimum_flexural_reinforcement_ratio_ACI_318_19(beam, 1.0e6)

    assert rho_min == pytest.approx(3 * math.sqrt(6000.0) / 80_000.0, rel=1e-12)
    assert rho_min > 3 * math.sqrt(6000.0) / 100_000.0


@pytest.mark.parametrize(
    ("concrete_class", "n_stirrups", "n_legs"),
    [(Concrete_ACI_318_19, 1, 2), (Concrete_CIRSOC_201_25, 2, 4)],
)
def test_shear_design_legs_across_width_follow_the_code_caps(
    concrete_class: type, n_stirrups: int, n_legs: int
) -> None:
    """The same 50 cm beam with Vu = 350 kN: Vs,req = 228 kN is under the threshold
    (463 kN), so the limit across the width is min(d, cap) with d = 56.1 cm.

    ACI 318-19 caps it at 600 mm: one stirrup with its legs 44 cm apart is within
    56.1 cm. CIRSOC 201-25 caps it at 400 mm: 44 cm is too far, two stirrups.
    """
    beam = RectangularBeam(
        label="W1",
        concrete=concrete_class(name="H25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=50 * cm,
        height=60 * cm,
        c_c=25 * mm,
    )
    Node(section=beam, forces=Forces(label="ELU_01", V_z=350 * kN, M_y=100 * kNm)).design_shear()

    assert beam.shear_design.n_stirrups == n_stirrups
    assert beam.shear_design.n_legs == n_legs
    assert beam._stirrup_s_w <= beam._stirrup_s_max_w


@pytest.mark.parametrize(
    "code",
    ["ACI 318-19", "EN 1992-2004", "CIRSOC 201-25"],
)
def test_shear_design_always_gives_a_beam_stirrups(code: str) -> None:
    """A beam keeps its minimum cage even with no shear on it.

    The counterpart of the slab rule: ACI 318-19 9.6.3.1 and EN 1992-1-1 9.2.2
    only waive the minimum for members that can redistribute the load
    transversally, which a beam cannot. Only ``OneWaySlab`` opts out, so this
    guards the slab fix from being generalised to every section.
    """
    concretes = {
        "ACI 318-19": Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
        "EN 1992-2004": Concrete_EN_1992_2004(name="C25", f_c=25 * MPa),
        "CIRSOC 201-25": Concrete_CIRSOC_201_25(name="H25", f_c=25 * MPa),
    }
    beam = RectangularBeam(
        label="B1",
        concrete=concretes[code],
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=20 * cm,
        height=50 * cm,
        c_c=25 * mm,
    )
    Node(section=beam, forces=Forces(label="ELU_01", M_y=30 * kNm, V_z=0 * kN)).design_shear()

    assert beam._stirrups_optional is False
    assert beam.shear_design.n_stirrups > 0
    assert beam.shear_design.A_v.to("cm**2/m").magnitude > 0


def test_a_designed_beam_is_labelled_by_its_legs() -> None:
    """A beam is written legs first, then the bar, s_l and the spacing of the legs across the width."""
    beam = RectangularBeam(
        label="B1",
        concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=20 * cm,
        height=50 * cm,
        c_c=25 * mm,
    )
    Node(section=beam, forces=Forces(label="ELU_01", M_y=30 * kNm, V_z=150 * kN)).design()

    transverse = beam.reinforcement.transverse
    assert transverse.layout == "stirrups"
    assert str(transverse) == (
        f"{transverse.n_legs} legs Ø{transverse.d_b:.4g~P} @ {transverse.s_l:.4g~P}"
        f" · {transverse.s_w.to(transverse.s_l.units):.4g~P} between legs"
    )
    assert str(transverse) == "2 legs Ø10 mm @ 23 cm · 14 cm between legs"
    assert beam._shear_reinforcement["Variable"][:5] == ["ns", "nl", "db", "s", "sw"]


def _A_v_min_table_9_6_3_4(width_cm: float, f_c: float = 25.0, f_yt: float = 420.0) -> float:
    """ACI 318-19 Table 9.6.3.4, as an area per unit length in cm2/m."""
    b_w = width_cm * 10  # mm
    return max(0.062 * math.sqrt(f_c) * b_w / f_yt, 0.35 * b_w / f_yt) * 10


@pytest.mark.parametrize("width_cm, height_cm", [(20, 40), (20, 50), (30, 60), (40, 70), (50, 80)])
@pytest.mark.parametrize("V_z_kN", [0, 10, 25])
@pytest.mark.parametrize("code", ["ACI 318-19", "EN 1992-2004", "CIRSOC 201-25"])
def test_shear_design_never_puts_a_beam_below_the_minimum_area(
    code: str, V_z_kN: int, width_cm: int, height_cm: int
) -> None:
    """A lightly loaded beam still gets the minimum cage, not merely some cage.

    ACI 318-19 9.6.3.1 waives A_v,min where Vu falls under its threshold, and the
    design used to hand that zero straight to the stirrup designer -- which then
    sized off the spacing limits alone. With the 6 mm bars CIRSOC 201-25 allows,
    a 30x60 came back with 1eO6/28cm = 2.02 cm2/m against the 2.50 cm2/m of
    Table 9.6.3.4. A beam carries stirrups over its whole length, so the minimum
    holds whatever the shear diagram says.
    """
    concretes = {
        "ACI 318-19": Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
        "EN 1992-2004": Concrete_EN_1992_2004(name="C25", f_c=25 * MPa),
        "CIRSOC 201-25": Concrete_CIRSOC_201_25(name="H25", f_c=25 * MPa),
    }
    beam = RectangularBeam(
        label="B1",
        concrete=concretes[code],
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=width_cm * cm,
        height=height_cm * cm,
        c_c=25 * mm,
    )
    Node(section=beam, forces=Forces(label="ELU_01", M_y=30 * kNm, V_z=V_z_kN * kN)).design()

    A_v = beam.shear_design.A_v.to("cm**2/m").magnitude
    A_v_min = _A_v_min_table_9_6_3_4(width_cm)
    assert A_v >= A_v_min - 1e-9, (
        f"{code}, {width_cm}x{height_cm} cm, V_z {V_z_kN} kN: designed {A_v:.2f} cm2/m, minimum {A_v_min:.2f} cm2/m"
    )


@pytest.mark.parametrize("width_cm", [20, 30, 40, 50, 60, 80, 100, 120])
@pytest.mark.parametrize("V_z_kN", [100, 250, 450])
@pytest.mark.parametrize("code", ["ACI 318-19", "EN 1992-2004", "CIRSOC 201-25"])
def test_shear_design_respects_spacing_along_width(code: str, V_z_kN: int, width_cm: int) -> None:
    """No shear design may hand back stirrup legs spaced wider than s_max,w.

    Issue #94 was not one bad case but a missing criterion, so this sweeps the widths and
    demands where it bites. Before the fix 95 of these 168 combinations were in violation.
    """
    concretes = {
        "ACI 318-19": Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
        "EN 1992-2004": Concrete_EN_1992_2004(name="C25", f_c=25 * MPa),
        "CIRSOC 201-25": Concrete_CIRSOC_201_25(name="H25", f_c=25 * MPa),
    }
    steel_bar = SteelBar(name="ADN 420", f_y=420 * MPa)
    beam = RectangularBeam(
        label="W1",
        concrete=concretes[code],
        steel_bar=steel_bar,
        width=width_cm * cm,
        height=60 * cm,
        c_c=25 * mm,
    )
    node = Node(section=beam, forces=Forces(label="ELU_01", V_z=V_z_kN * kN, M_y=100 * kNm))
    node.design_shear()

    assert beam._stirrup_s_w <= beam._stirrup_s_max_w, (
        f"{code}, width {width_cm} cm, V_z {V_z_kN} kN: legs {beam._stirrup_s_w.to('cm'):~.2f} apart, "
        f"limit {beam._stirrup_s_max_w.to('cm'):~.2f}"
    )


def test_min_legs_along_width() -> None:
    """The leg count follows the width, stays even, and never drops below one stirrup."""
    concrete = Concrete_ACI_318_19(name="H25", f_c=25 * MPa)
    steel_bar = SteelBar(name="ADN 420", f_y=420 * MPa)
    beam = RectangularBeam(
        label="W1",
        concrete=concrete,
        steel_bar=steel_bar,
        width=50 * cm,
        height=60 * cm,
        c_c=25 * mm,
    )
    rebar = Rebar(beam)
    # Legs sit (50 - 2*2.5 - 1.0) = 44 cm apart at two legs.
    assert rebar.min_legs_along_width(10 * mm, 50 * cm) == 2  # 44 <= 50, one stirrup does
    assert rebar.min_legs_along_width(10 * mm, 44 * cm) == 2  # exactly on the limit
    # Two gaps would do (22 cm), but legs come in pairs, so it rounds up to four.
    assert rebar.min_legs_along_width(10 * mm, 30 * cm) == 4
    # Two gaps no longer fit, and the three that do already need an even four legs.
    assert rebar.min_legs_along_width(10 * mm, 20 * cm) == 4  # 44/3 = 14.7 <= 20
    assert rebar.min_legs_along_width(10 * mm, 10 * cm) == 6  # 44/5 = 8.8 <= 10

    # A degenerate limit falls back to a single stirrup rather than looping forever.
    assert rebar.min_legs_along_width(10 * mm, 0 * cm) == 2


def _wide_cirsoc_beam() -> RectangularBeam:
    """The wide CIRSOC beam: CIRSOC 201-25, H-25, ADN 420, 150x150 cm, c_c 30 mm."""
    return RectangularBeam(
        label="V1",
        concrete=Concrete_CIRSOC_201_25(name="H-25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=150 * cm,
        height=150 * cm,
        c_c=30 * mm,
    )


def test_wide_cirsoc_beam_takes_five_stirrups_for_the_across_width_limit() -> None:
    """Five closed stirrups, ten legs, because of the across-width limit of Tabla 9.7.6.2.2.

    Mu = 5000 kN·m, Vu = 5000 kN. V_s,req = 4828.12 kN passes 0.33·√f'c·bw·d =
    3568.95 kN, so both limits are the halved row's, capped at 200 mm by CIRSOC:
    s_max,l = min(d/4, 200 mm) and s_max,w = min(d/2, 200 mm), 20 cm each. Four
    stirrups would put eight legs (150 - 6 - 1.2)/7 = 20.40 cm apart; five put
    ten at 15.87 cm. A_v, not the width, is what the diameter and s_l follow.
    """
    beam = _wide_cirsoc_beam()
    node = Node(section=beam, forces=[Forces(label="C1", M_y=5000 * kNm, V_z=5000 * kN)])
    node.design()

    bottom = beam.reinforcement.bottom
    assert [(layer.n, layer.d_b.to("mm").magnitude) for layer in bottom.layers] == [(2, 32), (10, 32)]
    assert beam.reinforcement.top.layers == ()
    shear = beam.shear_design
    assert (shear.n_stirrups, shear.n_legs) == (5, 10)
    assert shear.d_b.to("mm").magnitude == pytest.approx(12)
    assert shear.s_l.to("cm").magnitude == pytest.approx(14)
    assert shear.s_w.to("cm").magnitude == pytest.approx(15.8667, abs=1e-4)
    assert beam._stirrup_s_max_l.to("cm").magnitude == pytest.approx(20.0)
    assert beam._stirrup_s_max_w.to("cm").magnitude == pytest.approx(20.0)
    assert beam._V_s_req.to("kN").magnitude == pytest.approx(4828.12, abs=0.01)
    threshold = 0.33 * math.sqrt(25) * beam._A_cv.to("mm**2").magnitude / 1000
    assert threshold == pytest.approx(3568.95, abs=0.01)
    assert shear.DCR == pytest.approx(0.9904, abs=1e-4)
    # Strength passes; the deep beam still requires supplementary web steel.
    assert tuple(w.code for w in node.warnings) == ("skin_reinforcement_required",)


def test_check_state_records_the_row_of_table_9_7_6_2_2() -> None:
    """The check keeps the threshold it compared against and the row it took.

    The 150x150 CIRSOC beam passes the threshold (the halved row); a combination with
    V_s,req = 161.45 kN stays under it.
    """
    beam = _wide_cirsoc_beam()
    Node(section=beam, forces=[Forces(label="C1", M_y=5000 * kNm, V_z=5000 * kN)]).design()
    code = design_code(beam.concrete)

    high = code.check_shear(beam, Forces(label="C1", M_y=5000 * kNm, V_z=5000 * kN))
    assert high.V_s_threshold / 1000 == pytest.approx(3568.95, abs=0.01)
    assert high.V_s_threshold == 0.33 * math.sqrt(25.0) * high.A_cv
    assert high.spacing_halved is True
    V_s_req, V_s_threshold, halved, s_max_l_table, s_max_w = high.spacing_quantities(False)
    assert V_s_req.to("kN").magnitude == pytest.approx(4828.12, abs=0.01)
    assert V_s_threshold.to("kN").magnitude == pytest.approx(3568.95, abs=0.01)
    assert halved is True
    assert s_max_l_table.to("cm").magnitude == pytest.approx(20.0)
    assert s_max_w.to("cm").magnitude == pytest.approx(20.0)

    low = code.check_shear(beam, Forces(label="C2", M_y=1000 * kNm, V_z=1500 * kN))
    assert low.V_s_req / 1000 == pytest.approx(161.45, abs=0.01)
    assert low.spacing_halved is False
    # Under the threshold the row is d/2 and d, capped at 400 mm.
    assert low.stirrup_s_max_l == pytest.approx(400.0)
    assert low.stirrup_s_max_w == pytest.approx(400.0)


def test_en_check_state_has_no_threshold_and_no_limits_without_stirrups() -> None:
    """EN 1992-1-1 has no threshold row; with no stirrups the check sets no limit."""
    beam = RectangularBeam(
        label="E1",
        concrete=Concrete_EN_1992_2004(name="C25", f_c=25 * MPa),
        steel_bar=SteelBar(name="B500S", f_y=500 * MPa),
        width=30 * cm,
        height=60 * cm,
        c_c=25 * mm,
    )
    beam.set_longitudinal_rebar_bot(n1=3, d_b1=16 * mm)
    code = design_code(beam.concrete)
    bare = code.check_shear(beam, Forces(label="C1", V_z=20 * kN))
    assert bare.spacing_quantities(False) == (None, None, None, None, None)

    beam.set_transverse_rebar(n_stirrups=1, d_b=8 * mm, s_l=20 * cm)
    braced = code.check_shear(beam, Forces(label="C1", V_z=20 * kN))
    V_s_req, V_s_threshold, halved, s_max_l_table, s_max_w = braced.spacing_quantities(False)
    assert (V_s_req, V_s_threshold, halved) == (None, None, None)
    assert s_max_l_table.to("mm").magnitude == pytest.approx(braced.stirrup_s_max_l)
    assert s_max_w.to("mm").magnitude == pytest.approx(braced.stirrup_s_max_w)


# # ------- FLEXURE TEST --------------


# Not published_example: the cited Calcpad sheet no longer gives these numbers; they were
# re-baselined to mento's own output (dd0df9f) with no derivation outside mento.
def test_flexure_check_EN_1992_2004_02(
    beam_example_EN_1992_2004_01: RectangularBeam,
) -> None:
    # Example from Calcpad Validation
    f = Forces(M_y=450 * kNm)
    beam_example_EN_1992_2004_01.set_transverse_rebar(n_stirrups=1, d_b=6 * mm, s_l=15 * cm)
    beam_example_EN_1992_2004_01.set_longitudinal_rebar_bot(n1=5, d_b1=25 * mm)
    beam_example_EN_1992_2004_01.set_longitudinal_rebar_top(n1=5, d_b1=12 * mm)
    node = Node(section=beam_example_EN_1992_2004_01, forces=f)
    results = node.check_flexure()
    assert results.iloc[1]["Label"] == "B_Example_EN_01"
    assert results.iloc[1]["Position"] == "Bottom"
    assert results.iloc[1]["As,min"] == pytest.approx(1.482, rel=1e-2)
    # Doubly reinforced section. Both the required areas and M_Rd moved when the
    # ductility limit was expressed consistently: x_u/d <= 0.328 is a NEUTRAL
    # AXIS limit, so the equivalent block is lambda*x_u = 0.8*0.328*d, which
    # lowers M_lim (243.6 -> 202.6 kNm for the 01 geometry) and pushes more of
    # the demand onto the compression steel.
    assert results.iloc[1]["As,req bot"] == pytest.approx(20.64, rel=1e-3)
    assert results.iloc[1]["As,req top"] == pytest.approx(11.14, rel=1e-3)
    assert results.iloc[1]["As"] == pytest.approx(24.54, rel=1e-4)
    assert results.iloc[1]["MRd"] == pytest.approx(326.55, rel=1e-3)
    assert results.iloc[1]["DCR"] == pytest.approx(1.378, rel=1e-3)


def test_flexure_check_EN_1992_2004_03(
    beam_example_EN_1992_2004_02: RectangularBeam,
) -> None:
    f = Forces(M_y=120 * kNm)
    beam_example_EN_1992_2004_02.set_transverse_rebar(n_stirrups=1, d_b=6 * mm, s_l=15 * cm)
    beam_example_EN_1992_2004_02.set_longitudinal_rebar_bot(n1=5, d_b1=25 * mm)
    beam_example_EN_1992_2004_02.set_longitudinal_rebar_top(n1=5, d_b1=12 * mm)
    node = Node(section=beam_example_EN_1992_2004_02, forces=f)
    results = node.check_flexure()
    assert results.iloc[1]["Label"] == "B_Example_EN_02"
    assert results.iloc[1]["Position"] == "Bottom"
    assert results.iloc[1]["As,min"] == pytest.approx(1.72, rel=1e-3)
    # See test_flexure_check_EN_1992_2004_01 for the lever-arm correction:
    # was 8.691 with the duplicated lambda, 8.87 with z = d - 0.5*x_eff.
    assert results.iloc[1]["As,req bot"] == pytest.approx(8.87, rel=1e-3)
    assert results.iloc[1]["As,req top"] == pytest.approx(0, rel=1e-3)


# Not published_example: the Concrete Centre case of Lecture 3 p. 14 (C30/B500S, +370 kN·m,
# 23.07 / 4.27 cm²) was replaced by C60/B400S at -370 kN·m, and 25.85 cm² is mento's output.
def test_flexure_check_EN_1992_2004_04(
    beam_example_EN_1992_2004_03: RectangularBeam,
) -> None:
    # Regression adapted from the lecture's geometry, not its published C30/B500 case.
    f = Forces(M_y=-370 * kNm)
    beam_example_EN_1992_2004_03.set_longitudinal_rebar_top(n1=6, d_b1=25 * mm)
    beam_example_EN_1992_2004_03.set_transverse_rebar(n_stirrups=1, d_b=6 * mm, s_l=20 * cm)
    assert beam_example_EN_1992_2004_03._d_top == 45.15 * cm
    node = Node(section=beam_example_EN_1992_2004_03, forces=f)
    results = node.check_flexure()
    assert results.iloc[1]["Label"] == "B_Example_EN_03"
    assert results.iloc[1]["Position"] == "Top"
    # Table 3.1 C60: fctm=2.12*ln(1+68/10)=4.354742 MPa.
    # §9.2.1.1: .26*fctm/400 * 300 * 451.5 = 383.402 mm², shown in cm².
    assert results.iloc[1]["As,min"] == pytest.approx(3.83, abs=0.005)
    # f_ck = 60 MPa: lambda = 0.775, eta = 0.95. Same lever-arm correction as
    # test_flexure_check_EN_1992_2004_01 (was 25.639).
    assert results.iloc[1]["As,req top"] == pytest.approx(25.85, rel=1e-3)


# Not published_example: a unit test of an internal function, whose expectation is built
# from mento's own attributes.
def test_compression_zone_limits_EN_1992_2004_are_expressed_on_the_neutral_axis() -> None:
    """The ductility limits are on x_u/d; the block depth is lambda times that.

    EN 1992-1-1 5.5(4) bounds ``x_u/d`` (the neutral axis), and so does the 0.45
    cap. The equivalent rectangular block of 3.1.7(3) is ``lambda * x_u``. Both
    used to be mixed: the redistribution limit was fed in as if it already were
    a block depth, which put M_lim about 20% too high.
    """
    concrete = Concrete_EN_1992_2004(name="C25", f_c=25 * MPa)
    beam = RectangularBeam(
        label="limits",
        concrete=concrete,
        steel_bar=SteelBar(name="B500S", f_y=500 * MPa),
        width=20 * cm,
        height=60 * cm,
        c_c=2.6 * cm,
    )
    d = 560.0  # mm -- the EN equations layer works in floats
    x_u_lim, x_eff_lim = _compression_zone_limits_EN_1992_2004(beam, d)

    xi_expected = min((concrete._delta - concrete._k_1) / concrete._k_2, 0.45)
    assert xi_expected == pytest.approx(0.328, rel=1e-3)
    assert x_u_lim / d == pytest.approx(xi_expected, rel=1e-9)
    assert x_eff_lim / x_u_lim == pytest.approx(concrete._lambda_factor(), rel=1e-9)
    # M_lim built on the block depth, per The Concrete Centre's K' = 0.453*xi*(1-0.4*xi)
    f_cd = concrete.f_cd.to("MPa").magnitude
    M_lim = concrete._eta_factor() * f_cd * 200 * x_eff_lim * (560 - 0.5 * x_eff_lim)
    assert M_lim / 1e6 == pytest.approx(202.55, rel=1e-3)


def _EN_bottom_capacity(concrete: Concrete_EN_1992_2004, steel: SteelBar) -> Quantity:
    """M_Rd of a 20x60 beam with 4Ø16 at the bottom, under 100 kN·m."""
    beam = RectangularBeam(label="EN", concrete=concrete, steel_bar=steel, width=20 * cm, height=60 * cm, c_c=2.6 * cm)
    beam.set_transverse_rebar(n_stirrups=1, d_b=8 * mm, s_l=20 * cm)
    beam.set_longitudinal_rebar_bot(n1=4, d_b1=16 * mm)
    Node(section=beam, forces=[Forces(label="ELU", M_y=100 * kNm)]).check_flexure()
    capacity = beam.flexure_checks[0].bottom.M_capacity
    assert capacity is not None
    return capacity.to("kN*m")


def test_EN_beam_reads_gamma_s_from_the_steel_and_alpha_cc_from_the_concrete() -> None:
    """γ_s is the steel's and α_cc the concrete's: changing either moves M_Rd (#184, #185).

    Under-reinforced, so M_Rd ≈ A_s·f_yd·z: it rises close to 1.15 times with γ_s = 1.0,
    and only through the lever arm with α_cc = 1.0.
    """
    base = _EN_bottom_capacity(Concrete_EN_1992_2004(name="C25", f_c=25 * MPa), SteelBar(name="B500S", f_y=500 * MPa))
    no_gamma_s = _EN_bottom_capacity(
        Concrete_EN_1992_2004(name="C25", f_c=25 * MPa), SteelBar(name="B500S", f_y=500 * MPa, gamma_s=1.0)
    )
    alpha_cc_1 = _EN_bottom_capacity(
        Concrete_EN_1992_2004(name="C25", f_c=25 * MPa, alpha_cc=1.0), SteelBar(name="B500S", f_y=500 * MPa)
    )
    assert no_gamma_s.magnitude / base.magnitude == pytest.approx(1.15, rel=0.03)
    assert alpha_cc_1 > base
    assert alpha_cc_1.magnitude / base.magnitude == pytest.approx(1.0, abs=0.02)


def test_design_flexure_EN_1992_2004_infeasible_does_not_crash() -> None:
    """EN gained the "design_flexure never crashes" contract from the driver.

    The EN design used to let ``RebarDesignInfeasibleError`` propagate; sharing
    the driver with ACI means an unfittable section now degrades to whatever
    layout it has, and check_flexure reports DCR > 1.
    """
    section = RectangularBeam(
        label="en-infeasible-15x15",
        concrete=Concrete_EN_1992_2004(name="C20", f_c=20 * MPa),
        steel_bar=SteelBar(name="B500S", f_y=500 * MPa),
        width=15 * cm,
        height=15 * cm,
        c_c=2 * cm,
    )
    Node(section=section, forces=Forces(M_y=14 * kNm)).design_flexure()
    # If we got here without raising, the contract holds.


def test_design_flexure_EN_1992_2004_layout_passes_its_own_check() -> None:
    """
    Regression test: a layout produced by design_flexure must pass check_flexure.

    With a positive and a negative moment the discrete selector ended up placing
    the SAME layout (2Ø16+1Ø12) on both faces. M_Rd then took the branch
    ``A_s_prime >= A_s`` and moved the whole internal couple to the lever arm
    ``d - d'``, which is shorter than the singly reinforced ``d - 0.5*lambda*x_eff``
    used when sizing the steel -- so the beam came out with DCR = 1.02 right after
    being designed. The section is far from needing compression reinforcement
    (x_eff is well below x_eff_lim), so the compression bars must not enter the
    resisting couple at all.
    """
    beam = RectangularBeam(
        label="101",
        concrete=Concrete_EN_1992_2004(name="C25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=20 * cm,
        height=60 * cm,
        c_c=25 * mm,
    )
    node = Node(
        section=beam,
        forces=[
            Forces(label="1.4D", V_z=60 * kN, M_y=-80 * kNm),
            Forces(label="1.2D+1.6L", M_y=100 * kNm),
        ],
    )
    node.design()
    results = node.check_flexure()

    assert results.iloc[1:]["DCR"].astype(float).max() <= 1.0


def test_nominal_moment_EN_1992_2004_is_monotonic_in_compression_steel() -> None:
    """
    M_Rd must never decrease when steel is added to the compression face.

    The old formulation lost the concrete contribution as A_s' approached A_s,
    so M_Rd fell from 100.65 to 98.39 kN·m over the sweep below -- adding steel
    reduced the computed capacity.
    """
    beam = RectangularBeam(
        label="monotonic",
        concrete=Concrete_EN_1992_2004(name="C25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=20 * cm,
        height=60 * cm,
        c_c=25 * mm,
    )
    _initialize_variables_EN_1992_2004(beam)
    # The EN equations layer works in floats: mm2, mm and N*mm.
    A_s = (5.1522 * cm**2).to("mm**2").magnitude
    d = 561.44
    d_prime = 38.56

    capacities = [
        _simple_determine_nominal_moment_EN_1992_2004(beam, A_s, d, ratio * A_s, d_prime) / 1e6
        for ratio in (0.0, 0.2, 0.5, 0.8, 0.95, 1.0, 1.2)
    ]
    assert capacities == sorted(capacities)
    # Section is singly reinforced (x_eff << x_eff_lim), so A_s' is irrelevant.
    assert capacities[-1] == pytest.approx(capacities[0], rel=1e-9)


def test_en1992_high_strength_concrete_compression_reinforcement() -> None:
    """Test EN 1992 beam with f_ck > 50 MPa requiring compression reinforcement."""
    # Use high-strength concrete (f_ck = 60 MPa)
    concrete_en = Concrete_EN_1992_2004(name="C60/75", f_c=60 * MPa)
    steel = SteelBar(name="B500", f_y=500 * MPa)

    beam = RectangularBeam(
        label="TEST_EN_HIGH",
        concrete=concrete_en,
        steel_bar=steel,
        width=20 * cm,
        height=60 * cm,
        c_c=2.5 * cm,
    )

    # Apply large moment to require compression reinforcement
    # This should exceed M_lim and trigger doubly reinforced section
    forces = Forces(M_y=500 * kNm)
    node = Node(beam, forces)

    # Design the beam
    result = node.design_flexure()

    # Should complete without error
    assert result is not None
    assert isinstance(result, pd.DataFrame)

    # Beam should have compression reinforcement (top rebar)
    assert beam.flexure_design.top.A_s > 0 * cm**2

    # Beam should be marked as doubly reinforced
    assert beam._doubly_reinforced is True

    # Check that x_u calculation used k_3 and k_4 (high-strength path)
    # This is implicit in the calculation, but we can verify the section was designed
    check_result = node.check_flexure()
    assert isinstance(check_result, pd.DataFrame)


def test_en1992_normal_strength_concrete_compression_reinforcement() -> None:
    """Test EN 1992 beam with f_ck <= 50 MPa requiring compression reinforcement."""
    # Use normal-strength concrete (f_ck = 30 MPa)
    concrete_en = Concrete_EN_1992_2004(name="C30/37", f_c=30 * MPa)
    steel = SteelBar(name="B500", f_y=500 * MPa)

    beam = RectangularBeam(
        label="TEST_EN_NORMAL",
        concrete=concrete_en,
        steel_bar=steel,
        width=25 * cm,
        height=50 * cm,
        c_c=3 * cm,
    )

    # Apply large moment to require compression reinforcement
    forces = Forces(M_y=200 * kNm, N_x=0 * kN, V_z=0 * kN)
    node = Node(beam, forces)

    # Design the beam
    result = node.design_flexure()

    # Should complete without error
    assert result is not None
    assert isinstance(result, pd.DataFrame)

    # If doubly reinforced, should have top rebar
    if beam._doubly_reinforced:
        assert beam.flexure_design.top.A_s > 0 * cm**2

    # Check that x_u calculation used k_1 and k_2 (normal-strength path)
    check_result = node.check_flexure()
    assert isinstance(check_result, pd.DataFrame)


def test_en1992_negative_moment() -> None:
    """Test EN 1992 beam with f_ck <= 50 MPa requiring compression reinforcement."""
    # Use normal-strength concrete (f_ck = 30 MPa)
    concrete_en = Concrete_EN_1992_2004(name="C30/37", f_c=30 * MPa)
    steel = SteelBar(name="B500", f_y=500 * MPa)

    beam = RectangularBeam(
        label="TEST_EN_NORMAL",
        concrete=concrete_en,
        steel_bar=steel,
        width=25 * cm,
        height=50 * cm,
        c_c=3 * cm,
    )

    # Apply large moment to require compression reinforcement
    forces = Forces(M_y=-50 * kNm, N_x=0 * kN, V_z=0 * kN)
    node = Node(beam, forces)

    # Design the beam
    result = node.design_flexure()

    # Should complete without error
    assert result is not None
    assert isinstance(result, pd.DataFrame)


def test_flexural_beam_determine_nominal_moment_simple_reinf_ACI_318_19() -> None:
    """
    Test para la funcion que determina el momento nominal de una seccion armada solo con refuerzo de traccion
    ver el ejemplo en:
    Example from https://www.google.com/search?q=ACI+318+19+nominal+moment+of+section&oq=ACI+318+19+nominal+moment+of+section&gs_lcrp=EgZjaHJvbWUyBggAEEUYOTIHCAEQIRigAdIBCTIyNzkzajBqN6gCALACAA&sourceid=chrome&ie=UTF-8#fpstate=ive&vld=cid:dab5f5e7,vid:m4H0QbGDYIg,st:0
    """
    concrete = Concrete_ACI_318_19(name="C6", f_c=6000 * psi)
    steelBar = SteelBar(name="G80", f_y=80000 * psi)
    beam = RectangularBeam(
        label="B20x30",
        concrete=concrete,
        steel_bar=steelBar,
        width=20 * inch,
        height=30 * inch,
        c_c=1 * inch,
    )
    A_s = 10.92 * inch**2
    d = 27 * inch
    result = _nominal_moment_simple_in_pint(beam, A_s, d)

    # Compare dictionaries with a tolerance for floating-point values, in inch**2
    # Result: 1653.84kip.ft
    assert result.to(kip * ft).magnitude == pytest.approx(1653.84, rel=1e-2)


def test_flexural_beam_determine_nominal_moment_double_reinf_ACI_318_19() -> None:
    """
    Test para la funcion que determina el momento nominal de una seccion doblemente armada
    Example from https://www.youtube.com/watch?v=7BOuV1gCcgc
    """
    concrete = Concrete_ACI_318_19(name="C4", f_c=4000 * psi)
    steelBar = SteelBar(name="G60", f_y=60000 * psi)
    beam = RectangularBeam(
        label="B14x27",
        concrete=concrete,
        steel_bar=steelBar,
        width=14 * inch,
        height=27 * inch,
        c_c=1 * inch,
    )
    A_s = 6 * inch**2
    d = 24 * inch
    d_prime = 2.5 * inch
    A_s_prime = 1.8 * inch**2
    result = _nominal_moment_double_in_pint(beam, A_s, d, d_prime, A_s_prime)
    assert result.to(kip * ft).magnitude == pytest.approx(639.12, rel=1e-2)


def test_check_flexure_ACI_318_19_1(beam_example_flexure_ACI: RectangularBeam) -> None:
    # Testing the check of the reinforced beam with a large moment that requires
    # compression reinforcement, the moment being positive.
    # Calcpad de referencia: ACI 318-19 Beam Flexure 03_v3 - test_1.cpd
    # Geometría: b=12", h=24", fc=4000psi, fy=60ksi, Mu=400 kip·ft
    # Armado bot: 2×#11 + 2×#10 (dos capas), armado top: 2×#6
    # d = 20.3719", d' = 2.25"
    # v3 del calcpad aplica los siguientes fixes respecto de v2:
    #   1. Displaced concrete en el Check: contribucion del top usa (f_y - 0.85·fc).
    #   2. Rama D (chequeo de ductilidad): capea A_s cuando la seccion sigue sobre-armada
    #      aun con top presente (A_s > A_s_max + A_s_top·f_s'_net/f_y).
    # PENDIENTE validar valores en ETABS.
    f = Forces(label="Test_01", M_y=400 * kip * ft)
    beam_example_flexure_ACI.set_longitudinal_rebar_bot(n1=2, d_b1=1.41 * inch, n3=2, d_b3=1.27 * inch)
    beam_example_flexure_ACI.set_longitudinal_rebar_top(n1=2, d_b1=0.75 * inch)
    node = Node(section=beam_example_flexure_ACI, forces=f)
    results = node.check_flexure()
    assert beam_example_flexure_ACI._d_bot.to("inch").magnitude == pytest.approx(20.3719, rel=1e-3)
    assert results.iloc[1]["Label"] == "B-12x24"
    assert results.iloc[1]["Comb."] == "Test_01"
    assert results.iloc[1]["Position"] == "Bottom"
    assert results.iloc[1]["As,min"] == pytest.approx(us(5.257, "cm**2", "inch**2"), rel=1e-2, abs=0.005)
    assert results.iloc[1]["As,req bot"] == pytest.approx(us(33.17, "cm**2", "inch**2"), rel=1e-3, abs=0.005)
    assert results.iloc[1]["As,req top"] == pytest.approx(us(5.22, "cm**2", "inch**2"), rel=1e-2, abs=0.005)
    assert results.iloc[1]["As"] == pytest.approx(us(36.49, "cm**2", "inch**2"), rel=1e-2, abs=0.005)
    assert results.iloc[1]["Mu"] == pytest.approx(us(542.33, "kN*m", "kip*ft"), rel=1e-3, abs=0.005)
    # La seccion no esta controlada por traccion: con los 5.656 in² reales y el
    # acero comprimido, compatibilidad de deformaciones da c = 8.344 in y
    # eps_t = 0.00432 < eps_ty + 0.003 = 0.00507, asi que phi = 0.838 (Tabla 21.2.2)
    # y ØMn = 546.80 kN·m. El calcpad v3 recortaba A_s a A_s_max_total y mantenia
    # phi = 0.90 (550.34, del lado inseguro); ya no es la referencia de este valor,
    # que se verifico con una compatibilidad escrita aparte.
    assert results.iloc[1]["ØMn"] == pytest.approx(us(546.80, "kN*m", "kip*ft"), rel=1e-3, abs=0.005)
    # Y lo dice: la cara traccionada supera el tope de §9.3.3.1 con su compresion.
    over = [w for w in node.warnings if w.code == "not_tension_controlled"]
    assert [w.face for w in over] == ["bottom"]


def test_check_flexure_ACI_318_19_2(beam_example_flexure_ACI: RectangularBeam) -> None:
    # Testeo el checkeo de la viga con momento NEGATIVO que requiere armadura de compresión.
    # Calcpad de referencia: ACI 318-19 Beam Flexure 03_v3 - test_2.cpd
    # Mismo caso que test_1 con armado invertido (lo que era bot pasa a top y viceversa).
    # v3 del calcpad aplica los mismos fixes que test_1 (displaced concrete + rama D).
    # PENDIENTE validar valores en ETABS.
    f = Forces(label="Test_02", M_y=-400 * kip * ft)
    beam_example_flexure_ACI.set_longitudinal_rebar_bot(n1=2, d_b1=0.75 * inch)
    beam_example_flexure_ACI.set_longitudinal_rebar_top(n1=2, d_b1=1.41 * inch, n3=2, d_b3=1.27 * inch)
    node = Node(section=beam_example_flexure_ACI, forces=f)
    results = node.check_flexure()
    assert results.iloc[1]["Label"] == "B-12x24"
    assert results.iloc[1]["Comb."] == "Test_02"
    assert results.iloc[1]["Position"] == "Top"
    assert results.iloc[1]["As,min"] == pytest.approx(us(5.26, "cm**2", "inch**2"), rel=1e-3, abs=0.01)
    assert results.iloc[1]["As,req bot"] == pytest.approx(us(5.22, "cm**2", "inch**2"), rel=1e-2, abs=0.005)
    assert results.iloc[1]["As,req top"] == pytest.approx(us(33.17, "cm**2", "inch**2"), rel=1e-3, abs=0.005)
    assert results.iloc[1]["As"] == pytest.approx(us(36.49, "cm**2", "inch**2"), rel=1e-3, abs=0.005)
    assert results.iloc[1]["Mu"] == pytest.approx(us(-542.33, "kN*m", "kip*ft"), rel=1e-5, abs=0.005)
    # El espejo de test_1: eps_t = 0.00432, phi = 0.838, ØMn = 546.80 kN·m.
    assert results.iloc[1]["ØMn"] == pytest.approx(us(546.80, "kN*m", "kip*ft"), rel=1e-3, abs=0.005)
    over = [w for w in node.warnings if w.code == "not_tension_controlled"]
    assert [w.face for w in over] == ["top"]


@pytest.mark.parametrize(
    "concrete_class",
    [Concrete_ACI_318_19, Concrete_CIRSOC_201_25],
    ids=["ACI 318-19", "CIRSOC 201-25"],
)
def test_flexure_rho_l_belongs_to_its_own_face_ACI_318_19(
    concrete_class: type[Concrete_ACI_318_19],
) -> None:
    """rho = A_s/(b*d), one face at a time.

    ACI 318-19 Ch. 2 (2.2) defines rho as the "ratio of A_s to bd" and CIRSOC
    201-25 Cap. 2 repeats it word for word ("cuantia de la armadura traccionada,
    no tesa; relacion entre A_s y el area b.d"). The flexure report prints that
    ratio next to the A_s of the face it belongs to, so the top ratio has to be
    built from the top steel and the top effective depth.

    Top and bottom carry deliberately different bars: feeding the top ratio with
    A_s_bot -- as the code did -- fails here by a factor of four.
    """
    beam = RectangularBeam(
        label="B-30x50",
        concrete=concrete_class(name="H25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=30 * cm,
        height=50 * cm,
        c_c=30 * mm,
    )
    beam.set_transverse_rebar(n_stirrups=1, d_b=8 * mm, s_l=20 * cm)
    beam.set_longitudinal_rebar_bot(n1=3, d_b1=20 * mm)
    beam.set_longitudinal_rebar_top(n1=2, d_b1=12 * mm)
    # One layer per face, so d = h - c_c - d_be - d_b/2:
    #   d_bot = 500 - 30 - 8 - 20/2 = 452 mm
    #   d_top = 500 - 30 - 8 - 12/2 = 456 mm
    assert beam._d_bot.to(mm).magnitude == pytest.approx(452.0)
    assert beam._d_top.to(mm).magnitude == pytest.approx(456.0)

    Node(section=beam, forces=Forces(label="C1", M_y=80 * kNm)).check_flexure()

    # A_s_bot = 3*pi*20^2/4 = 942.478 mm2 -> 942.478/(300*452) = 0.0069504
    # A_s_top = 2*pi*12^2/4 = 226.195 mm2 -> 226.195/(300*456) = 0.0016535
    assert beam._rho_l_bot.magnitude == pytest.approx(0.0069504, rel=1e-4)
    assert beam._rho_l_top.magnitude == pytest.approx(0.0016535, rel=1e-4)
    # The bottom steel over the top depth -- the ratio the top face used to get
    # -- would be 942.478/(300*456) = 0.0068895, so the two faces must not land
    # on the same value.
    assert beam._rho_l_top.magnitude != pytest.approx(beam._rho_l_bot.magnitude, rel=1e-3)


def test_flexure_rho_l_belongs_to_its_own_face_EN_1992_2004() -> None:
    """Same per-face rule for EN: rho_l = A_sl/(b_w*d), EN 1992-1-1 §6.2.2(1).

    Reported, not fed to Eq. (6.2.a), so no 0.02 cap applies here -- but the
    steel still has to be the steel of the face being reported.
    """
    beam = RectangularBeam(
        label="B-20x60",
        concrete=Concrete_EN_1992_2004(name="C25", f_c=25 * MPa),
        steel_bar=SteelBar(name="B500S", f_y=500 * MPa),
        width=20 * cm,
        height=60 * cm,
        c_c=2.6 * cm,
    )
    beam.set_transverse_rebar(n_stirrups=1, d_b=6 * mm, s_l=15 * cm)
    beam.set_longitudinal_rebar_bot(n1=4, d_b1=16 * mm)
    beam.set_longitudinal_rebar_top(n1=2, d_b1=12 * mm)
    #   d_bot = 600 - 26 - 6 - 16/2 = 560 mm
    #   d_top = 600 - 26 - 6 - 12/2 = 562 mm
    assert beam._d_bot.to(mm).magnitude == pytest.approx(560.0)
    assert beam._d_top.to(mm).magnitude == pytest.approx(562.0)

    Node(section=beam, forces=Forces(label="C1", M_y=100 * kNm)).check_flexure()

    # A_s_bot = 4*pi*16^2/4 = 804.248 mm2 -> 804.248/(200*560) = 0.0071808
    # A_s_top = 2*pi*12^2/4 = 226.195 mm2 -> 226.195/(200*562) = 0.0020124
    assert beam._rho_l_bot.magnitude == pytest.approx(0.0071808, rel=1e-4)
    assert beam._rho_l_top.magnitude == pytest.approx(0.0020124, rel=1e-4)
    # The bottom steel over the top depth would be 0.0071552.
    assert beam._rho_l_top.magnitude != pytest.approx(beam._rho_l_bot.magnitude, rel=1e-3)


# ---------------------------------------------------------------------------
# ETABS-validated required-steel tests
# ---------------------------------------------------------------------------
# Source: BEAM-01-Flexure-Rectangle ACI 318-19-v6.xlsm (JPR's spreadsheet, not
# public), sheet "Flexion", rows 27-49: one row per Test_Etabs_XX with its
# geometry, materials and Mu in columns C to H, and the ETABS run in columns
# BC (As inf) and BE (As sup); column BD is the ratio hand calculation / ETABS,
# 1.0000 on every row used here. A marked test reproduces columns BC/BE of its
# row. Test_Etabs_07 to _10 and _18 are not marked: mento adopts 4/3*A_s,calc
# (ACI 318-19 §9.6.1.3) or its own geometric floor where ETABS applies A_s,min,
# so their expected value is mento's, not ETABS's -- each says so.


# Not published_example: it pins mento's 4/3*A_s,calc of ACI 318-19 §9.6.1.3, not ETABS's A_s,min
# (sheet Flexion, column BC = 2.2137 in²).
def test_calculate_flexural_reinforcement_ACI_318_19_Test_Etabs_07() -> None:
    """
    Test_Etabs_07: b=18", h=30", fc=8000psi, fy=60ksi, Mu=200 kip.ft, simple.
    Case where A_s_calc < A_s_min: per ACI 318-19 art. 9.6.1.3 the code allows
    using 4/3 * A_s_calc instead of A_s_min when it satisfies the geometric
    minimum. Mento adopts that exception.
    Expected A_s_final = 4/3 * A_s_calc = 2.187 in² (ETABS uses A_s_min = 2.214).
    """

    concrete = Concrete_ACI_318_19(name="fc8000", f_c=8000 * psi)
    steel = SteelBar(name="fy60", f_y=60 * ksi)
    beam = RectangularBeam(
        label="Test_Etabs_07", concrete=concrete, steel_bar=steel, width=18 * inch, height=30 * inch, c_c=1.5 * inch
    )
    beam.set_transverse_rebar(n_stirrups=1, d_b=0.375 * inch, s_l=12 * inch)
    d = 27.5 * inch
    d_prima = 2.5 * inch
    Mu = 200 * kip * ft
    A_s_min, A_s_max, A_s_final, A_s_comp, c_d, A_s_bool, _doubly = _flexural_reinforcement_in_pint(
        beam, Mu, d, d_prima
    )
    assert A_s_final.to("inch**2").magnitude == pytest.approx(2.1868, rel=1e-3)
    assert A_s_comp.to("inch**2").magnitude == pytest.approx(0.0, abs=1e-3)
    assert A_s_bool is True  # 4/3 rule was applied


# Not published_example: it pins mento's 4/3*A_s,calc of ACI 318-19 §9.6.1.3, not ETABS's A_s,min
# (sheet Flexion, column BC = 2.6089 in²).
def test_calculate_flexural_reinforcement_ACI_318_19_Test_Etabs_08() -> None:
    """
    Test_Etabs_08: b=20", h=30", fc=9000psi, fy=60ksi, Mu=200 kip.ft, simple.
    Case where A_s_calc < A_s_min: Mento adopts 4/3 * A_s_calc per ACI 318-19
    art. 9.6.1.3.
    Expected A_s_final = 4/3 * A_s_calc = 2.180 in² (ETABS uses A_s_min = 2.609).
    """

    concrete = Concrete_ACI_318_19(name="fc9000", f_c=9000 * psi)
    steel = SteelBar(name="fy60", f_y=60 * ksi)
    beam = RectangularBeam(
        label="Test_Etabs_08", concrete=concrete, steel_bar=steel, width=20 * inch, height=30 * inch, c_c=1.5 * inch
    )
    beam.set_transverse_rebar(n_stirrups=1, d_b=0.375 * inch, s_l=12 * inch)
    d = 27.5 * inch
    d_prima = 2.5 * inch
    Mu = 200 * kip * ft
    A_s_min, A_s_max, A_s_final, A_s_comp, c_d, A_s_bool, _doubly = _flexural_reinforcement_in_pint(
        beam, Mu, d, d_prima
    )
    assert A_s_final.to("inch**2").magnitude == pytest.approx(2.1803, rel=1e-3)
    assert A_s_comp.to("inch**2").magnitude == pytest.approx(0.0, abs=1e-3)
    assert A_s_bool is True  # 4/3 rule was applied


# Not published_example: it pins mento's 4/3*A_s,calc of ACI 318-19 §9.6.1.3, not ETABS's A_s,min
# (sheet Flexion, column BC = 4.02 in²).
def test_calculate_flexural_reinforcement_ACI_318_19_Test_Etabs_09() -> None:
    """
    Test_Etabs_09: b=24", h=36", fc=10000psi, fy=60ksi, Mu=200 kip.ft, simple.
    Big section with low Mu: A_s_calc << A_s_min. Mento adopts 4/3 * A_s_calc
    per ACI 318-19 art. 9.6.1.3.
    Expected A_s_final = 4/3 * A_s_calc = 1.779 in² (ETABS uses A_s_min = 4.02).
    """

    concrete = Concrete_ACI_318_19(name="fc10000", f_c=10000 * psi)
    steel = SteelBar(name="fy60", f_y=60 * ksi)
    beam = RectangularBeam(
        label="Test_Etabs_09", concrete=concrete, steel_bar=steel, width=24 * inch, height=36 * inch, c_c=1.5 * inch
    )
    beam.set_transverse_rebar(n_stirrups=1, d_b=0.375 * inch, s_l=12 * inch)
    d = 33.5 * inch
    d_prima = 2.5 * inch
    Mu = 200 * kip * ft
    A_s_min, A_s_max, A_s_final, A_s_comp, c_d, A_s_bool, _doubly = _flexural_reinforcement_in_pint(
        beam, Mu, d, d_prima
    )
    assert A_s_final.to("inch**2").magnitude == pytest.approx(1.7794, rel=1e-3)
    assert A_s_comp.to("inch**2").magnitude == pytest.approx(0.0, abs=1e-3)
    assert A_s_bool is True  # 4/3 rule was applied


# Not published_example: it pins mento's 4/3*A_s,calc of ACI 318-19 §9.6.1.3, not ETABS's A_s,min
# (sheet Flexion, column BC = 4.2162 in²).
def test_calculate_flexural_reinforcement_ACI_318_19_Test_Etabs_10() -> None:
    """
    Test_Etabs_10: b=24", h=36", fc=11000psi, fy=60ksi, Mu=200 kip.ft, simple.
    Same as Test_Etabs_09 with higher fc. Mento adopts 4/3 * A_s_calc per
    ACI 318-19 art. 9.6.1.3.
    Expected A_s_final = 4/3 * A_s_calc = 1.778 in² (ETABS uses A_s_min = 4.216).
    """

    concrete = Concrete_ACI_318_19(name="fc11000", f_c=11000 * psi)
    steel = SteelBar(name="fy60", f_y=60 * ksi)
    beam = RectangularBeam(
        label="Test_Etabs_10", concrete=concrete, steel_bar=steel, width=24 * inch, height=36 * inch, c_c=1.5 * inch
    )
    beam.set_transverse_rebar(n_stirrups=1, d_b=0.375 * inch, s_l=12 * inch)
    d = 33.5 * inch
    d_prima = 2.5 * inch
    Mu = 200 * kip * ft
    A_s_min, A_s_max, A_s_final, A_s_comp, c_d, A_s_bool, _doubly = _flexural_reinforcement_in_pint(
        beam, Mu, d, d_prima
    )
    assert A_s_final.to("inch**2").magnitude == pytest.approx(1.7784, rel=1e-3)
    assert A_s_comp.to("inch**2").magnitude == pytest.approx(0.0, abs=1e-3)
    assert A_s_bool is True  # 4/3 rule was applied


# Not published_example: it pins mento's geometric floor 0.0018*b*h, not ETABS's A_s,min
# (sheet Flexion, column BC = 3.2915 in²).
def test_calculate_flexural_reinforcement_ACI_318_19_Test_Etabs_18() -> None:
    """
    Test_Etabs_18: b=16", h=60", fc=8000psi, fy=75ksi, Mu=200 kip.ft, simple.
    Large-depth section with very low Mu: A_s_calc << A_s_min. The 4/3 * A_s_calc
    result undershoots the geometric minimum 1.8‰·b·h = 1.728 in², so the
    geometric minimum governs instead (A_s_bool stays False — 4/3 rule not
    effectively used).
    Expected A_s_final = A_s_geo_min = 1.728 in² (ETABS uses A_s_min = 3.292).
    """

    concrete = Concrete_ACI_318_19(name="fc8000", f_c=8000 * psi)
    steel = SteelBar(name="fy75", f_y=75 * ksi)
    beam = RectangularBeam(
        label="Test_Etabs_18", concrete=concrete, steel_bar=steel, width=16 * inch, height=60 * inch, c_c=1.5 * inch
    )
    beam.set_transverse_rebar(n_stirrups=1, d_b=0.375 * inch, s_l=12 * inch)
    d = 57.5 * inch
    d_prima = 2.5 * inch
    Mu = 200 * kip * ft
    A_s_min, A_s_max, A_s_final, A_s_comp, c_d, A_s_bool, _doubly = _flexural_reinforcement_in_pint(
        beam, Mu, d, d_prima
    )
    assert A_s_final.to("inch**2").magnitude == pytest.approx(1.7280, rel=1e-3)
    assert A_s_comp.to("inch**2").magnitude == pytest.approx(0.0, abs=1e-3)
    assert A_s_bool is False  # 4/3 rule computed but geometric minimum governs


@pytest.mark.skip(
    reason="Extreme case: 12x12 section with fc=11000psi and Mu=200 kip.ft. "
    "ETABS does not report As inf (#¡VALOR! in spreadsheet). The required "
    "compression steel (7.40 in²) exceeds the tension steel (4.42 in²), "
    "indicating the section is structurally unreasonable."
)
def test_calculate_flexural_reinforcement_ACI_318_19_Test_Etabs_21() -> None:
    """Test_Etabs_21: extreme case, skipped."""
    pass


# Not published_example: it asserts A_s >= 19.0 cm² and phi*Mn >= Mu from mento's own check;
# ETABS asks for 19.38 cm² (sheet Flexion, row 27, column BC) and the design passes below it.
def test_design_flexure_ACI_318_19_Test_Etabs_01() -> None:
    """
    Test_Etabs_01: b=12", h=20", fc=2500psi, fy=60ksi, Mu=200 kip·ft.
    Sección doblemente armada validada contra Excel BEAM-01-Flexure-Rectangle ACI 318-19-v6 y ETABS.
    ETABS (d fijo=17.5", d'=2.5"): As inf = 3.0045 in² (19.39 cm²), As sup = 0.7628 in² (4.92 cm²).

    Estrategia de verificación:
    - Se verifica que el diseño sea doblemente armado (_doubly_reinforced is True).
    - Se verifica As inf >= 19.0 cm²: el armado de tracción cubre lo requerido por ETABS,
      con tolerancia para que el selector de barras discretas supere levemente ese umbral.
    - NO se verifica As sup directamente contra ETABS porque el diseño es iterativo:
      al seleccionar las barras inferiores, su centroide real actualiza d (rec_mec), y el
      centroide de las barras superiores actualiza d'. Con d y d' convergidos (que difieren
      levemente de los 17.5" y 2.5" que ETABS asume como fijos), A_req_top converge a un
      valor menor (≈ 0.714 in² en lugar de 0.7628 in²). El selector elige barras suficientes
      para esa geometría convergida, pero menos que la estimación ETABS de d fijo.
    - En cambio se verifica φMn >= Mu con las barras finalmente diseñadas: esto garantiza
      que el diseño es estructuralmente correcto independientemente de las diferencias de
      redondeo por selección discreta de barras y convergencia de geometría.
    """
    concrete = Concrete_ACI_318_19(name="fc2500", f_c=2500 * psi)
    steel = SteelBar(name="fy60", f_y=60 * ksi)
    beam = RectangularBeam(
        label="Test_Etabs_01",
        concrete=concrete,
        steel_bar=steel,
        width=12 * inch,
        height=20 * inch,
        c_c=1.5 * inch,
    )
    beam.set_transverse_rebar(n_stirrups=1, d_b=0.375 * inch, s_l=12 * inch)

    f = Forces(label="Test_Etabs_01", M_y=200 * kip * ft)
    node = Node(section=beam, forces=f)
    results = node.design_flexure()

    assert isinstance(results, pd.DataFrame)
    assert beam._doubly_reinforced is True
    assert beam.flexure_design.bottom.A_s.to("cm**2").magnitude >= 19.0

    # Verificar que φMn con las barras diseñadas supera Mu = 200 kip·ft = 271.2 kNm
    check_results = node.check_flexure()
    phi_Mn = check_results.iloc[1]["ØMn"]  # kip·ft: the section is imperial
    assert phi_Mn >= us(271.0, "kN*m", "kip*ft")


# Not published_example: the spreadsheet has no negative-moment row; nothing external is asserted.
def test_design_flexure_ACI_318_19_negative_moment_doubly_reinforced() -> None:
    """
    Mirror of Test_Etabs_01 with NEGATIVE moment: b=12", h=20", fc=2500psi,
    fy=60ksi, Mu=-200 kip·ft. Tension is now on the top face and compression
    on the bottom, so the design must place the governing tension steel on top
    and reconcile the bottom face against the compression demand.

    Exercises the negative-moment path of _design_flexure_ACI_318_19 (including
    the bottom-face reconciliation branch) which mirrors the positive case.
    """
    concrete = Concrete_ACI_318_19(name="fc2500", f_c=2500 * psi)
    steel = SteelBar(name="fy60", f_y=60 * ksi)
    beam = RectangularBeam(
        label="Test_Etabs_01_neg",
        concrete=concrete,
        steel_bar=steel,
        width=12 * inch,
        height=20 * inch,
        c_c=1.5 * inch,
    )
    beam.set_transverse_rebar(n_stirrups=1, d_b=0.375 * inch, s_l=12 * inch)

    f = Forces(label="Test_Etabs_01_neg", M_y=-200 * kip * ft)
    node = Node(section=beam, forces=f)
    results = node.design_flexure()

    assert isinstance(results, pd.DataFrame)
    assert beam._doubly_reinforced is True
    # Tension governs on top for negative moment.
    assert beam.flexure_design.top.A_s.to("cm**2").magnitude >= 19.0


def test_design_flexure_ACI_318_19_large_negative_moment_doubly_reinforced() -> None:
    """
    Large negative moment forcing doubly reinforced design with compression
    steel on the bottom face: b=30cm, h=50cm, fc=25MPa, fy=420MPa, Mu=-400 kN·m.
    Tension governs on top; the bottom face carries compression steel.
    Complements the smaller Mu=-200 negative case with a section that clearly
    lands in the doubly reinforced regime.
    """
    concrete = Concrete_ACI_318_19(name="C25", f_c=25 * MPa)
    steel = SteelBar(name="fy420", f_y=420 * MPa)
    beam = RectangularBeam(
        label="neg_bottom_reconc",
        concrete=concrete,
        steel_bar=steel,
        width=30 * cm,
        height=50 * cm,
        c_c=2.5 * cm,
    )
    beam.set_transverse_rebar(n_stirrups=1, d_b=8 * mm, s_l=20 * cm)
    node = Node(section=beam, forces=Forces(M_y=-400 * kNm))
    results = node.design_flexure()
    assert isinstance(results, pd.DataFrame)
    assert beam._doubly_reinforced is True
    # Tension on top governs; compression steel present on the bottom face.
    flexure = beam.flexure_design
    assert flexure.top.A_s.to("cm**2").magnitude > flexure.bottom.A_s.to("cm**2").magnitude
    assert flexure.bottom.A_s.to("cm**2").magnitude > 0


def test_design_flexure_ACI_318_19_negative_moment_insufficient_section() -> None:
    """
    Negative moment on a section too small to resist it: b=15", h=15",
    fc=20MPa, fy=500MPa, Mu=-120 kN·m. The design cannot find a top layout
    that satisfies phi*Mn >= Mu, so the post-loop final verification falls back
    to _best_visited_pair (best-effort layout). The contract
    is that design_flexure never raises; check_flexure downstream reports DCR>1.
    """
    concrete = Concrete_ACI_318_19(name="C20", f_c=20 * MPa)
    steel = SteelBar(name="fy500", f_y=500 * MPa)
    beam = RectangularBeam(
        label="neg_insufficient",
        concrete=concrete,
        steel_bar=steel,
        width=15 * cm,
        height=15 * cm,
        c_c=2 * cm,
    )
    node = Node(section=beam, forces=Forces(M_y=-120 * kNm))
    results = node.design_flexure()
    assert isinstance(results, pd.DataFrame)
    # No crash = contract preserved. The section is undersized; the check would
    # flag DCR>1, but the design still returns the best-effort layout.


def test_best_visited_pair_prefers_the_lightest_admissible_pair() -> None:
    """
    _best_visited_pair: de los pares de armados que el lazo visito, gana el de
    MENOR acero que resiste y es admisible (controlado por traccion), no el de
    mayor ØMn; si ninguno resiste, el admisible que mas se acerca.

    Seccion 20x50 cm, fc=25 MPa, fy=420 MPa, c_c=2.5 cm, estribo Ø8, sin
    armadura superior (la cara superior nunca se visito: el par la deja vacia).
    Candidatos de la cara inferior, simplemente armados salvo el ultimo
    (As,max = ρmax·d·b = 0.01593·d·200, ≈ 14.6 cm²):

      2Ø20: As = 6.28 cm², d = 45.7 cm, a = 62.1 mm
            ØMn = 0.9 · 628.3·420·(457 - 31.0) = 101.2 kN·m
      2Ø25: As = 9.82 cm², d = 45.45 cm, a = 97.0 mm
            ØMn = 0.9 · 981.7·420·(454.5 - 48.5) = 150.7 kN·m
      6Ø25 en dos capas: As = 29.45 cm² > As,max → no controlada por traccion

    Con Mu = 90 kN·m resisten los dos primeros: gana 2Ø20, en cualquier orden.
    Con Mu = 200 kN·m no resiste ninguno admisible: gana 2Ø25, el que mas se
    acerca, aunque 6Ø25 tenga mas capacidad -- pasa el limite de §9.3.3.1.
    """
    beam = RectangularBeam(
        label="best_visited_pair",
        concrete=Concrete_ACI_318_19(name="C25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=20 * cm,
        height=50 * cm,
        c_c=2.5 * cm,
    )
    beam.set_transverse_rebar(n_stirrups=1, d_b=8 * mm, s_l=20 * cm)

    def layout(n1: int, d_b: Quantity, n3: int = 0) -> dict:
        area = ((n1 + n3) * np.pi * d_b**2 / 4).to("cm**2")
        return {
            "n_1": n1,
            "d_b1": d_b,
            "n_2": 0,
            "d_b2": None,
            "n_3": n3,
            "d_b3": d_b if n3 else None,
            "n_4": 0,
            "d_b4": None,
            "total_as": area,
        }

    small, large, heavy = layout(2, 20 * mm), layout(2, 25 * mm), layout(3, 25 * mm, 3)

    def assess_for(M: Quantity):  # type: ignore[no-untyped-def]
        def assess() -> tuple[bool, float]:
            M_R = _flexure_capacity_ACI_318_19(beam, "bot", M)
            return _flexure_ductile_ACI_318_19(beam, "bot"), float((M / M_R).to("dimensionless").magnitude)

        return assess

    for order in ([large, small], [small, large]):
        bot, top = _best_visited_pair(beam, {i: row for i, row in enumerate(order)}, {}, assess_for(90 * kNm))
        assert bot["total_as"].to("cm**2").magnitude == pytest.approx(6.28, rel=1e-3)
        assert top is None
        # The pair it returns is the one it leaves on the section.
        assert beam._A_s_bot.to("cm**2").magnitude == pytest.approx(6.28, rel=1e-3)
        assert beam._A_s_top.magnitude == 0

    beam._apply_longitudinal_design_bot(heavy)
    assert not _flexure_ductile_ACI_318_19(beam, "bot")
    bot, _ = _best_visited_pair(beam, {0: small, 1: heavy, 2: large}, {}, assess_for(200 * kNm))
    assert bot["total_as"].to("cm**2").magnitude == pytest.approx(9.82, rel=1e-3)


def test_design_flexure_ACI_318_19_gap_past_cap_adds_compression_steel() -> None:
    """
    Ninguna combinacion discreta cae entre As,req y As,max: el diseño pasa el
    tope con la menor que cubre As,req y arma la cara opuesta con la compresion
    que la mantiene controlada por traccion, en vez de quedarse con el fallback
    que no alcanza.

    Seccion 15x25 cm, fc=35 MPa, fy=500 MPa, c_c=2.5 cm, estribo Ø8, Mu=+40 kN·m.
    Ancho libre = 15 - 2·(2.5 + 0.8) = 8.4 cm; con la separacion libre minima
    (max(25 mm, vibrador 30 mm, d_b)) solo entran 2 barras por capa.

    d = 25 - 4.3 = 20.7 cm → As,req = 4.96 cm², As,max = 5.22 cm². Ninguna
    combinacion cae en [4.96, 5.22] (2Ø20 y 2Ø16+2Ø12 dan 6.28 cm²; 3Ø12 no
    entra), y el tope dejaba el fallback 4Ø12 = 4.52 cm² (ØMn = 34.0 kN·m).
    Antes se terminaba en 2Ø20 sin compresion: sobre-armada, capacidad
    capeada en As,max (ØMn = 41.7 kN·m) y aviso not_tension_controlled.

    Ahora 2Ø20 abajo pide compresion arriba por el exceso sobre As,max, leida
    a la profundidad de cada candidato: 2Ø12 en una capa queda a
    d' = 2.5 + 0.8 + 0.6 = 3.9 cm, mas arriba que 2Ø16, y alcanza:
      β1 = 0.80 ; εy = 0.0025 ; c_t = 0.003·207/0.0085 = 73.1 mm
      f's = (73.1 - 39)/73.1·0.003·200000 = 279.9 MPa ; f's,net = 250.1 MPa
      A's = (6.28 - 5.22)·500/250.1 = 2.12 cm² <= 2Ø12 = 2.26 cm²
      As,max_total = 5.22 + 2.26·250.1/500 = 6.35 cm² >= 6.28

    Equilibrio (acero comprimido sin fluir), c = 72.3 mm, a = 57.8 mm:
      Cc = 0.85·35·150·57.8 = 258.1 kN ; f's = 600·(72.3 - 39)/72.3 = 276.3 MPa
      Cs = 226·(276.3 - 29.75) = 55.7 kN ; T = 628·500 = 314 kN ✓
      Mn = 258.1·(207 - 28.9) + 55.7·(207 - 39) = 55.3 kN·m
      ØMn = 0.9·55.3 = 49.8 kN·m ; εt = 0.003·(207 - 72.3)/72.3 = 0.0056 >= 0.0055
    """
    beam = RectangularBeam(
        label="picard_cycle_bot",
        concrete=Concrete_ACI_318_19(name="C35", f_c=35 * MPa),
        steel_bar=SteelBar(name="ADN 500", f_y=500 * MPa),
        width=15 * cm,
        height=25 * cm,
        c_c=2.5 * cm,
    )
    beam.set_transverse_rebar(n_stirrups=1, d_b=8 * mm, s_l=20 * cm)
    node = Node(section=beam, forces=Forces(label="Mu+40", M_y=40 * kNm))
    results = node.design_flexure()

    assert isinstance(results, pd.DataFrame)
    bottom = beam.flexure_design.bottom
    assert (bottom.layers[0].n, bottom.layers[0].d_b.to("mm").magnitude) == (2, 20)
    # A single layer: the public API only lists layers that carry bars.
    assert len(bottom.layers) == 1
    assert bottom.A_s.to("cm**2").magnitude == pytest.approx(6.28, rel=1e-3)
    top = beam.flexure_design.top
    assert [(layer.n, layer.d_b.to("mm").magnitude) for layer in top.layers] == [(2, 12)]

    check_results = node.check_flexure()
    assert check_results.iloc[1]["Position"] == "Bottom"
    assert check_results.iloc[1]["ØMn"] == pytest.approx(49.84, rel=1e-3)
    assert check_results.iloc[1]["DCR"] <= 1.0
    # Past A_s_max but inside the cap the top steel extends: doubly reinforced,
    # not over-reinforced.
    assert "not_tension_controlled" not in [warning.code for warning in node.warnings]


def test_design_flexure_ACI_318_19_gap_past_cap_negative_moment_upgrades_bottom() -> None:
    """
    El mismo caso con Mu = -40 kN·m: la traccion arriba pasa el tope (2Ø20)
    y pide abajo compresion, mas que las 2Ø10 = 1.57 cm² que la cara inferior
    tomo en su primer pase (el 1.8‰ de b·h, sin momento positivo). La
    conciliacion rediseña la cara inferior: 2Ø12. Abajo no rige el vibrador,
    y con barras mas finas d' = 2.5 + 0.8 + 0.6 = 3.9 cm, f's sube y la
    compresion requerida baja a ~2.1 cm², que 2Ø12 = 2.26 cm² cubre.
    ØMn = 49.8 kN·m.
    """
    beam = RectangularBeam(
        label="picard_gap_top",
        concrete=Concrete_ACI_318_19(name="C35", f_c=35 * MPa),
        steel_bar=SteelBar(name="ADN 500", f_y=500 * MPa),
        width=15 * cm,
        height=25 * cm,
        c_c=2.5 * cm,
    )
    beam.set_transverse_rebar(n_stirrups=1, d_b=8 * mm, s_l=20 * cm)
    node = Node(section=beam, forces=Forces(label="Mu-40", M_y=-40 * kNm))
    node.design_flexure()

    flexure = beam.flexure_design
    assert [(layer.n, layer.d_b.to("mm").magnitude) for layer in flexure.top.layers] == [(2, 20)]
    assert [(layer.n, layer.d_b.to("mm").magnitude) for layer in flexure.bottom.layers] == [(2, 12)]

    check_results = node.check_flexure()
    assert check_results.iloc[1]["Position"] == "Top"
    assert check_results.iloc[1]["ØMn"] == pytest.approx(49.84, rel=1e-3)
    assert node.warnings == ()


def test_design_flexure_CIRSOC_201_25_narrow_web_fits_the_bars_its_stirrup_leaves_room_for() -> None:
    """
    Viga 12x30 cm, H25, ADN 420, c_c = 2.5 cm, Mu = +40 kN·m, Vu = 50 kN.

    Con el estribo de arranque de 8 mm el ancho libre es 12 - 2·(2.5 + 0.8) =
    5.4 cm: dos barras por capa y como mucho Ø12 (54 - 2·16 = 22 mm < 25 mm
    de separacion libre, §25.2.1). Lo mas que entraba era 2Ø12 + 2Ø12 =
    4.52 cm², por debajo de los 5.13 cm² que pide el momento, y el diseño
    quedaba con DCR 1.129 y ``As_below_required``. Pero el diseño de corte
    elige 1eØ6/12 para 50 kN, y con el Ø6 el ancho libre es 5.8 cm: 2Ø16
    entran (58 - 32 = 26 mm ≥ 25 mm). El diseño completo rehace la flexion
    con el estribo con el que termina y deja 2Ø16 + 2Ø12 = 6.28 cm² abajo
    sobre 2Ø12 arriba: DCR 0.803; el detalle de jaula se advierte por separado.
    Antes quedaba con la seccion
    declarada corta por un estribo que no lleva.
    """
    beam = RectangularBeam(
        label="101",
        concrete=Concrete_CIRSOC_201_25(name="H25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=12 * cm,
        height=30 * cm,
        c_c=25 * mm,
    )
    node = Node(section=beam, forces=[Forces(label="1.4D", V_z=50 * kN, M_y=40 * kNm)])
    node.design()

    bottom = beam.flexure_design.bottom
    assert beam._stirrup_d_b.to("mm").magnitude == pytest.approx(6.0)
    assert [(layer.n, layer.d_b.to("mm").magnitude) for layer in bottom.layers] == [(2, 16), (2, 12)]
    assert bottom.A_s.to("cm**2").magnitude == pytest.approx(6.283, rel=1e-3)
    assert bottom.DCR == pytest.approx(0.803, rel=1e-3)
    assert [w.code for w in node.warnings] == ["compression_detailing_pending", "cage_detailing_infeasible"]


def test_design_flexure_CIRSOC_201_25_narrow_web_gives_the_most_that_fits() -> None:
    """
    Viga 12x30 cm, H25, ADN 420, c_c = 2.5 cm, Mu = +60 kN·m, Vu = 50 kN.

    Con el 1eØ6/12 que elige el corte el ancho libre es 5.8 cm: dos barras
    por capa y como mucho Ø16 (58 - 2·16 = 26 mm ≥ 25 mm de §25.2.1; el Ø20
    dejaria 18). Lo mas que entra es 2Ø16 + 2Ø16 = 8.04 cm², por debajo de
    los 8.14 cm² que pide el momento (con compresion: arriba pide 7.27 y
    entran 2Ø12 + 2Ø12 = 4.52). Ni pasando el tope hay una combinacion que
    alcance, asi que el diseño deja el maximo que entra y lo dice:
    ``As_below_required`` en las dos caras, DCR 1.137.
    """
    beam = RectangularBeam(
        label="101",
        concrete=Concrete_CIRSOC_201_25(name="H25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=12 * cm,
        height=30 * cm,
        c_c=25 * mm,
    )
    node = Node(section=beam, forces=[Forces(label="1.4D", V_z=50 * kN, M_y=60 * kNm)])
    node.design()

    bottom = beam.flexure_design.bottom
    assert [(layer.n, layer.d_b.to("mm").magnitude) for layer in bottom.layers] == [(2, 16), (2, 16)]
    assert bottom.A_s.to("cm**2").magnitude == pytest.approx(8.042, rel=1e-3)
    assert bottom.DCR == pytest.approx(1.137, rel=1e-3)
    assert "bottom" in [w.face for w in node.warnings if w.code == "As_below_required"]


def test_design_flexure_ACI_318_19_compression_bottom_exceeds_provided_bottom() -> None:
    """
    Rama de re-diseño de la cara inferior cuando la compresion que exige el
    momento negativo supera lo que el primer pase de esa cara alcanzo a
    proveer (A_s_comp_bot > A_prov_bot dentro del lazo de Picard).

    Seccion 15x30 cm, fc=25 MPa, fy=420 MPa, c_c=2.5 cm, estribo Ø8,
    Mu = -80 kN·m (traccion arriba, compresion abajo).
    Ancho libre = 8.4 cm → solo 2 barras por capa.

    La cara inferior, en su primer pase, solo lleva el 1.8‰ de b·h: no hay
    momento positivo. La compresion que le pide la traccion de arriba es mucho
    mas, y la conciliacion la rediseña como armadura comprimida.

    Antes el lazo terminaba en 2Ø20 + 2Ø20 = 12.57 cm² arriba sobre 2Ø25 abajo:
    ØMn = 86.0 kN·m, pero con A_s = 12.57 > A_s_max_total = 11.78 cm² la seccion
    no estaba controlada por traccion, y el chequeo lo tapaba recortando A_s.
    Ahora la compresion se dimensiona para el acero colocado, y el diseño queda
    en 2Ø25 arriba (una capa) y 2Ø25 abajo:

      d = 30 - (2.5 + 0.8 + 1.25) = 25.45 cm ; d' = 4.55 cm ; β1 = 0.85
      ρmax = 0.85·0.85·25/420·(0.003/0.0081) = 0.01593
      A_s_max_top = 0.01593·254.5·150 = 6.08 cm² < 9.82 → hace falta compresion
      c_t = 0.003·254.5/0.0081 = 94.3 mm ; f's = (94.3 - 45.5)/94.3·600 = 310.5 MPa
      A_s_max_total = 6.08 + 9.82·(310.5 - 21.25)/420 = 12.84 cm² >= 9.82 ✓

    Equilibrio (acero comprimido sin fluir), c = 74.8 mm, a = 63.6 mm:
      Cc = 0.85·25·150·63.6 = 202.7 kN ; f's = 600·(74.8 - 45.5)/74.8 = 235.0 MPa
      Cs = 982·(235.0 - 21.25) = 209.9 kN ; T = 982·420 = 412.4 kN ✓
      Mn = 202.7·(254.5 - 31.8) + 209.9·(254.5 - 45.5) = 89.0 kN·m
      ØMn = 0.9·89.0 = 80.1 kN·m >= 80 ; εt = 0.003·(254.5 - 74.8)/74.8 = 0.0072
    """
    beam = RectangularBeam(
        label="comp_bottom_reupgrade",
        concrete=Concrete_ACI_318_19(name="C25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=15 * cm,
        height=30 * cm,
        c_c=2.5 * cm,
    )
    beam.set_transverse_rebar(n_stirrups=1, d_b=8 * mm, s_l=20 * cm)
    node = Node(section=beam, forces=Forces(label="Mu-80", M_y=-80 * kNm))
    results = node.design_flexure()

    assert isinstance(results, pd.DataFrame)
    assert beam._doubly_reinforced is True
    flexure = beam.flexure_design
    assert [(layer.n, layer.d_b.to("mm").magnitude) for layer in flexure.top.layers] == [(2, 25)]
    assert [(layer.n, layer.d_b.to("mm").magnitude) for layer in flexure.bottom.layers] == [(2, 25)]

    check_results = node.check_flexure()
    assert check_results.iloc[1]["Position"] == "Top"
    assert check_results.iloc[1]["ØMn"] == pytest.approx(80.06, rel=1e-3)
    assert check_results.iloc[1]["DCR"] <= 1.0
    # Tension-controlled strength; rounded cage fit is checked separately.
    assert [w.code for w in node.warnings] == ["compression_detailing_pending", "cage_detailing_infeasible"]


def test_check_flexure_ACI_318_19_negative_moment_no_top_steel(
    beam_example_flexure_ACI: RectangularBeam,
) -> None:
    """
    Check under NEGATIVE moment with no top steel: the top face has zero
    capacity (M_n_negative = 0), so phi_M_n_top is clamped to 0.01 kN·m to
    avoid a division-by-zero in the DCR, and the check reports a very high DCR.
    Exercises the zero-capacity guard in the negative-moment check branch.
    """
    beam_example_flexure_ACI.set_longitudinal_rebar_bot(n1=2, d_b1=0.75 * inch)
    beam_example_flexure_ACI.set_longitudinal_rebar_top(n1=0, d_b1=0 * inch)
    f = Forces(label="neg_no_top", M_y=-100 * kip * ft)
    node = Node(section=beam_example_flexure_ACI, forces=f)
    results = node.check_flexure()
    assert results.iloc[1]["Position"] == "Top"
    # Zero top steel → essentially no negative capacity → DCR >> 1.
    assert results.iloc[1]["DCR"] > 1.0


def testing_determine_nominal_moment_ACI_318_19(
    beam_example_flexure_ACI: RectangularBeam,
) -> None:
    beam_example_flexure_ACI.set_longitudinal_rebar_bot(
        n1=2,
        d_b1=1.128 * inch,
        n2=1,
        d_b2=1.128 * inch,
        n3=2,
        d_b3=1 * inch,
        n4=1,
        d_b4=1 * inch,
    )
    beam_example_flexure_ACI.set_longitudinal_rebar_top(
        n1=2,
        d_b1=1.128 * inch,
        n2=1,
        d_b2=1.128 * inch,
        n3=2,
        d_b3=1 * inch,
        n4=1,
        d_b4=1 * inch,
    )

    f = Forces(label="Test_01", M_y=400 * kip * ft)
    node_1 = Node(section=beam_example_flexure_ACI, forces=f)
    node_1.check_flexure()
    assert beam_example_flexure_ACI._phi_M_n_bot.to("kN*m").magnitude == pytest.approx(587.0589108678, rel=1e-2)
    assert beam_example_flexure_ACI._phi_M_n_top.to("kN*m").magnitude == pytest.approx(587.0589108678, rel=1e-2)


def test_check_flexure_ACI_318_19_over_reinforced_no_top(
    beam_example_flexure_ACI: RectangularBeam,
) -> None:
    """
    Sobre-armada SIN acero de compresion: A_s_bot > A_s_max y A_s_top = 0.

    Ojo: la fixture RectangularBeam inicializa A_s_top = 0.22 in² como default
    (decision original de Mihdi para el dibujo de estribos). Para forzar el
    caso "sin top puro" hay que setear top explicito en 0.

    Caso: b=12", h=24", fc=4000psi, fy=60ksi, Mu=400 kip·ft
    Armado: 6×#11 abajo (9.37 in² = 60.5 cm²), NADA arriba.
    A_s_max_bot ≈ 4.60 in² = 29.7 cm² << 60.5 → sobre-armada.

    Antes se recortaba A_s a A_s_max y se mantenia phi = 0.90 (≈ 506 kN·m). Ahora
    cuenta todo el acero, a la tension que le da su deformacion:
      c = 13.578 in, eps_t = 0.00173 < eps_ty = 0.00207 → el acero traccionado ni
      siquiera fluye, phi = 0.65 (controlada por compresion)
      ØMn = 541.18 kN·m, verificado con una compatibilidad escrita aparte.
    Y la seccion no cumple §9.3.3.1, que el aviso not_tension_controlled reporta.
    """
    f = Forces(label="Test_over_reinforced_top_zero", M_y=400 * kip * ft)
    beam_example_flexure_ACI.set_longitudinal_rebar_bot(n1=6, d_b1=1.41 * inch)
    beam_example_flexure_ACI.set_longitudinal_rebar_top(n1=0, d_b1=0 * inch)
    node = Node(section=beam_example_flexure_ACI, forces=f)
    results = node.check_flexure()
    assert results.iloc[1]["Position"] == "Bottom"
    assert results.iloc[1]["Mu"] == pytest.approx(us(542.33, "kN*m", "kip*ft"), rel=1e-3, abs=0.005)
    assert results.iloc[1]["ØMn"] == pytest.approx(us(541.18, "kN*m", "kip*ft"), rel=1e-3, abs=0.005)
    assert "not_tension_controlled" in {w.code for w in node.warnings}


def test_check_flexure_CIRSOC_201_25_over_reinforced_reports_its_real_strength() -> None:
    """
    El peor caso del barrido: CIRSOC 201-25, 25x40, H20, ADN 420, Mu = -206.90 kN·m,
    3Ø32 arriba (24.13 cm² a d = 351 mm) y 4Ø16 abajo (8.04 cm² a d' = 41 mm).

    El tope de §9.3.3.1 con esa compresion es
      A_s_max_eff = A_s_max + A_s'·f_s'/f_y = 18.72 cm² < 24.13
    asi que la seccion no esta controlada por traccion. Por compatibilidad:
      c = 190.8 mm ; eps_t = 0.003·(351 - 190.8)/190.8 = 0.00252 < 0.0051
      phi = 0.65 + 0.25·(0.00252 - 0.0021)/0.003 = 0.685 ; ØMn = 196.2 kN·m
    DCR = 206.90/196.2 = 1.055. Antes se recortaba A_s a 18.72 cm² con
    phi = 0.90 y daba ØMn = 213.4 kN·m, DCR 0.970: aprobaba una seccion que no
    resiste. Y el diseño de la misma seccion encuentra una que si.
    """
    beam = RectangularBeam(
        label="P",
        concrete=Concrete_CIRSOC_201_25(name="H20", f_c=20 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=25 * cm,
        height=40 * cm,
        c_c=25 * mm,
    )
    beam.set_transverse_rebar(n_stirrups=1, d_b=8 * mm, s_l=15 * cm)
    beam.set_longitudinal_rebar_top(3, 32 * mm)
    beam.set_longitudinal_rebar_bot(4, 16 * mm)
    assert beam._d_top.to("mm").magnitude == pytest.approx(351.0)
    assert beam._c_mec_bot.to("mm").magnitude == pytest.approx(41.0)

    node = Node(section=beam, forces=[Forces(label="M", M_y=-206.90 * kNm)])
    node.check_flexure()
    top = beam.flexure_checks[0].top
    assert top.M_capacity is not None and top.A_s_max_eff is not None
    assert top.M_capacity.to("kN*m").magnitude == pytest.approx(196.2, rel=1e-3)
    assert top.DCR == pytest.approx(1.055, rel=2e-3)
    assert top.A_s_max_eff.to("cm**2").magnitude == pytest.approx(18.72, rel=1e-3)
    assert [(w.code, w.face) for w in node.warnings if w.code == "not_tension_controlled"] == [
        ("not_tension_controlled", "top")
    ]

    node.design_flexure()
    node.check_flexure()
    assert beam.flexure_checks[0].top.DCR <= 1
    assert node.warnings == ()


def test_calculate_flexural_reinforcement_ACI_318_19_never_asks_for_negative_compression() -> None:
    """
    Seccion baja: 20x12 cm, fc = 25 MPa, fy = 420 MPa, Mu = 10 kN·m, mas de lo
    que toma sin compresion. d ≈ 75 mm y d' ≈ 45 mm, mientras que en el limite
    de ductilidad el eje neutro esta en c_t = 0.37·d ≈ 28 mm: la barra comprimida
    queda debajo del eje, f_s' - 0.85·f_c <= 0, y la division daba una armadura
    de compresion negativa. Ahora no pide ninguna, la cara no alcanza, y el
    diseño lo dice.
    """
    beam = RectangularBeam(
        label="S",
        concrete=Concrete_ACI_318_19(name="C25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=20 * cm,
        height=12 * cm,
        c_c=25 * mm,
    )
    node = Node(section=beam, forces=[Forces(label="M", M_y=10 * kNm)])
    node.design_flexure()
    node.check_flexure()
    check = beam.flexure_checks[0]
    assert check.top.A_s_req is not None
    assert check.top.A_s_req.magnitude == 0
    assert check.bottom.DCR > 1
    assert "As_below_required" in {w.code for w in node.warnings}


def test_design_flexure_EN_1992_2004_waits_for_both_faces_to_settle() -> None:
    """
    El lazo de Picard corta por ciclo solo cuando se repite el PAR de armados.
    Cortaba en cuanto una cara repetia el suyo -- lo que tambien hace una cara
    que ya convergio mientras la otra sigue ajustando --, y en esta viga dejaba
    la cara traccionada con un armado pensado para otra profundidad:
    EN 1992-2004, 20x40, C20, fy = 420 MPa, M_Ed = 204.59 kN·m. Con el corte por
    cara el diseño terminaba en DCR 1.011; esperando al par, 0.907.
    """
    beam = RectangularBeam(
        label="L",
        concrete=Concrete_EN_1992_2004(name="C20", f_c=20 * MPa),
        steel_bar=SteelBar(name="S", f_y=420 * MPa),
        width=20 * cm,
        height=40 * cm,
        c_c=25 * mm,
    )
    node = Node(section=beam, forces=[Forces(label="M", M_y=204.59 * kNm)])
    node.design_flexure()
    node.check_flexure()
    assert beam.flexure_checks[0].bottom.DCR == pytest.approx(0.907, abs=1e-3)
    assert [warning.code for warning in node.warnings] == ["compression_detailing_en_pending"]


def test_design_flexure_rebar_infeasible_does_not_crash() -> None:
    """
    Regression test for the "design_flexure never crashes" contract.

    A very small section (15x15 cm) with high-strength steel (fy=500 MPa) and
    a moment that requires more A_s than can physically fit in the width leads
    the internal rebar designer to return no valid bar combination. Before the
    fix, this triggered an unhandled IndexError from a bare `iloc[0]` on the
    empty results DataFrame; now `Rebar.longitudinal_rebar_design` raises
    `RebarDesignInfeasibleError`, which `_design_flexure_ACI_318_19` catches
    and handles gracefully by leaving that face's design as None.

    The test only asserts that design_flexure completes without raising.
    The resulting phi_M_n may be nonsensical (negative, tiny, ...); the point
    is that check_flexure downstream can still run and report DCR > 1.
    """
    section = RectangularBeam(
        label="rebar-infeasible-15x15",
        concrete=Concrete_ACI_318_19(name="C20", f_c=20 * MPa),
        steel_bar=SteelBar(name="fy500", f_y=500 * MPa),
        width=15 * cm,
        height=15 * cm,
        c_c=2 * cm,
    )
    node = Node(section=section, forces=Forces(M_y=14 * kNm))
    node.design_flexure()
    # It did not raise. And the capacity the check reports is a real one: this
    # case used to give phi*Mn = -26.14 kN·m. It says the design fell short.
    node.check_flexure()
    bottom = section.flexure_checks[0].bottom
    assert bottom.M_capacity is not None and bottom.M_capacity.magnitude > 0
    assert bottom.DCR > 1
    assert {w.code for w in node.warnings} & {"As_below_required", "bars_do_not_fit"}


def test_design_flexure_ACI_318_19_zero_moment_adopts_geometric_minimum() -> None:
    """
    Regression test: a shear-only load combination (M_y = 0) must still get the
    geometric minimum longitudinal reinforcement (1.8‰ of b·h), not A_s = 0.

    With M_u = 0 the ACI flexural minimum ratio is zero, so the design used to
    leave the section completely unreinforced. That is not a buildable layout,
    and it also breaks the shear check downstream: rho_w = 0 collapses V_c to
    zero and raises "Longitudinal rebar As cannot be zero if A_v is less than
    A_v_min." when V_u is small enough that A_v_min = 0.
    """
    beam = RectangularBeam(
        label="shear-only",
        concrete=Concrete_ACI_318_19(name="C25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=20 * cm,
        height=50 * cm,
        c_c=25 * mm,
    )
    node = Node(section=beam, forces=Forces(label="solo corte", V_z=20 * kN))

    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        node.design()

    A_s_geo_min = 1.8 / 1000 * beam.width * beam.height
    bottom = beam.flexure_design.bottom
    assert bottom.A_s >= A_s_geo_min
    assert bottom.layers[0].n > 0
    assert beam.V_c > 0 * kN


def test_check_flexure_ACI_318_19_over_reinforced_with_default_top(
    beam_example_flexure_ACI: RectangularBeam,
) -> None:
    """
    Sobre-armada CON acero de compresion presente pero insuficiente:
    A_s_bot > A_s_max_bot + A_s_top·f_s'_net/f_y.

    Mismo caso que over_reinforced_no_top pero dejando el A_s_top default de la
    fixture (0.22 in² = 1.43 cm²). Antes se recortaba A_s a A_s_max_total ≈ 31 cm²
    con phi = 0.90 (≈ 531 kN·m). Ahora, con todo el acero:
      c = 13.5 in, eps_t = 0.00177 < eps_ty → phi = 0.65, ØMn = 556.53 kN·m,
    verificado con una compatibilidad escrita aparte, y la seccion no cumple
    §9.3.3.1 (aviso not_tension_controlled).
    """
    f = Forces(label="Test_over_reinforced_default_top", M_y=400 * kip * ft)
    beam_example_flexure_ACI.set_longitudinal_rebar_bot(n1=6, d_b1=1.41 * inch)
    # sin set_longitudinal_rebar_top → A_s_top = 0.22 in² default de la fixture
    node = Node(section=beam_example_flexure_ACI, forces=f)
    results = node.check_flexure()
    assert results.iloc[1]["Position"] == "Bottom"
    assert results.iloc[1]["Mu"] == pytest.approx(us(542.33, "kN*m", "kip*ft"), rel=1e-3, abs=0.005)
    assert results.iloc[1]["ØMn"] == pytest.approx(us(556.53, "kN*m", "kip*ft"), rel=1e-3, abs=0.005)
    assert "not_tension_controlled" in {w.code for w in node.warnings}


def test_rectangular_section_plot_components(
    beam_example_flexure_ACI: RectangularBeam,
) -> None:
    """
    Test that the plot method adds the expected matplotlib components
    (main rectangle, annotations). The fixture carries no stirrups, so none is drawn.
    """
    beam_example_flexure_ACI.plot()
    ax = beam_example_flexure_ACI._ax  # Access the private _ax created by plot

    assert ax is not None, "Plot method should create and assign an Axes object."

    # Check for patches (rectangles, FancyBboxPatch)
    # Expecting: 1 main Rectangle and no stirrup: the fixture has none
    # + potentially other internal patches depending on matplotlib's rendering
    # It's safer to check for specific types and properties if possible.

    # Filter for Rectangle and FancyBboxPatch
    rectangles = [p for p in ax.patches if isinstance(p, Rectangle)]
    fancy_bboxes = [p for p in ax.patches if isinstance(p, FancyBboxPatch)]

    assert len(rectangles) >= 1, "Expected at least one Rectangle patch (the main section)."
    assert beam_example_flexure_ACI._stirrup_n == 0
    assert len(fancy_bboxes) == 0, "A beam with no stirrups draws none."

    # Check for annotations (dimensions)
    # Annotations are stored in ax.texts for text, ax.lines or ax.artists for arrows
    # matplotlib.axes.Axes.annotate returns an Annotation object.
    # Text labels are found in ax.texts
    assert len(ax.texts) == 6, "Expected 6 text annotations for dimensions (width, height)."

    # You could add more specific checks, e.g.:
    # - Check the coordinates of the main rectangle:
    main_rect = next((p for p in rectangles if p.get_x() == 0 and p.get_y() == 0), None)
    assert main_rect is not None
    assert np.isclose(main_rect.get_width() / 2.54, beam_example_flexure_ACI.width.magnitude)
    assert np.isclose(main_rect.get_height() / 2.54, beam_example_flexure_ACI.height.magnitude)
    assert main_rect.get_edgecolor() == to_rgba(CUSTOM_COLORS["dark_gray"])

    # - Check stirrup patch properties (example, will need exact dimensions based on calculation)
    #   This gets more complex quickly, focusing on existence and basic properties is often enough.

    plt.close()  # Close the figure created by the plot method


def test_rectangular_section_plot_metric_units_text(
    beam_example_EN_1992_2004_01: RectangularBeam,
) -> None:
    """
    Test that the plot method displays dimensions in metric units (cm)
    when the concrete's unit system is not 'imperial'.
    """
    beam_example_EN_1992_2004_01.plot()  # Ensure the plot method is called
    ax = beam_example_EN_1992_2004_01._ax
    assert ax is not None, "The plot method did not assign an Axes object to _ax."

    # Extract text labels
    text_labels = [t.get_text() for t in ax.texts]

    # Check if the labels contain "cm"
    assert any("cm" in label for label in text_labels), "Expected metric unit 'cm' in dimension text."
    assert "{:.0f~P}".format(beam_example_EN_1992_2004_01.width.to("cm")) in text_labels
    assert "{:.0f~P}".format(beam_example_EN_1992_2004_01.height.to("cm")) in text_labels

    plt.close()


def test_flexural_check_fails_min_top_with_flag() -> None:
    """Test flexural check fails minimum for top reinforcement with _A_s_bool_top=True."""
    # Create beam with insufficient top rebar
    concrete = Concrete_ACI_318_19(name="H35", f_c=35 * MPa)
    steelBar = SteelBar(name="ADN 420", f_y=420 * MPa)
    beam = RectangularBeam(
        label="TEST",
        concrete=concrete,
        steel_bar=steelBar,
        width=20 * cm,
        height=40 * cm,
        c_c=2.5 * cm,
    )
    f = Forces(label="ELU", M_y=-20 * kNm)
    node = Node(section=beam, forces=f)
    beam.set_longitudinal_rebar_top(n1=2, d_b1=12 * mm)

    # Check flexure
    node.check_flexure()

    checks = beam._data_min_max_flexure["Ok?"]

    # Should contain the article reference "9.6.1.3" for failing minimum
    assert "9.6.1.3" in checks[0]


def test_flexural_check_fails_min_bot_with_flag() -> None:
    """Test flexural check fails minimum for bottom reinforcement with _A_s_bool_bot=True."""
    # Create beam with insufficient bottom rebar
    concrete = Concrete_ACI_318_19(name="H35", f_c=35 * MPa)
    steelBar = SteelBar(name="ADN 420", f_y=420 * MPa)
    beam = RectangularBeam(
        label="TEST",
        concrete=concrete,
        steel_bar=steelBar,
        width=20 * cm,
        height=40 * cm,
        c_c=2.5 * cm,
    )
    f = Forces(label="ELU", M_y=20 * kNm)
    node = Node(section=beam, forces=f)
    beam.set_longitudinal_rebar_bot(n1=2, d_b1=12 * mm)

    # Check flexure
    node.check_flexure()

    # Check that the article reference appears in the checks
    checks = beam._data_min_max_flexure["Ok?"]
    assert "9.6.1.3" in checks[2]  # Position 2 is bottom rebar check


def test_flexural_check_fails_without_flag() -> None:
    """Test flexural check fails with ❌ when flags are False."""
    conc = Concrete_ACI_318_19(name="C25", f_c=25 * MPa)
    steel = SteelBar(name="ADN420", f_y=420 * MPa)

    beam = RectangularBeam(
        label="TEST",
        concrete=conc,
        steel_bar=steel,
        width=20 * cm,
        height=50 * cm,
        c_c=2.5 * cm,
    )

    # Set minimal top rebar
    beam.set_longitudinal_rebar_top(n1=1, d_b1=8 * mm)
    beam._A_s_bool_top = False  # Flag disabled

    forces = Forces(M_y=-50 * kNm, N_x=0 * kN, V_z=0 * kN)
    node = Node(beam, forces)

    node.check_flexure()

    # Should contain "❌" instead of article reference
    checks = beam._data_min_max_flexure["Ok?"]
    assert checks[0] == "❌"


def test_low_concrete_strength_negative_sqrt() -> None:
    """Test that very low concrete strength (f_c=1MPa) triggers sqrt_value < 0 condition."""
    # Very low concrete strength will cause sqrt_value to be negative
    conc = Concrete_ACI_318_19(name="C1", f_c=35 * MPa)
    steel = SteelBar(name="ADN420", f_y=420 * MPa)

    beam = RectangularBeam(
        label="TEST",
        concrete=conc,
        steel_bar=steel,
        width=20 * cm,
        height=60 * cm,
        c_c=2.5 * cm,
    )

    # Apply large moment that will cause negative sqrt_value
    forces = Forces(M_y=1000 * kNm)
    node = Node(beam, forces)

    # Design should not crash, but DCR should be > 1
    node.design_flexure()

    # No tension steel alone reaches the moment, so the face is doubly
    # reinforced: the requirement is the tension steel of the couple, past
    # A_s_max, with compression steel on top. It used to stop at A_s_max and
    # ask for no compression steel at all.
    bottom = beam.flexure_design.bottom
    top = beam.flexure_design.top
    assert bottom.A_s_req > bottom.A_s_max
    assert top.A_s_req.to("cm**2").magnitude > 0
    # Nothing that fits a 20 cm web carries it, and the section says so.
    assert {(w.code, w.face) for w in node.warnings} >= {("As_below_required", "bottom")}


def test_doubly_reinforced_ignores_max_limits() -> None:
    """Test that doubly reinforced sections bypass maximum reinforcement limits."""
    conc = Concrete_ACI_318_19(name="C35", f_c=35 * MPa)
    steel = SteelBar(name="ADN420", f_y=420 * MPa)

    beam = RectangularBeam(
        label="TEST",
        concrete=conc,
        steel_bar=steel,
        width=20 * cm,
        height=60 * cm,
        c_c=2.5 * cm,
    )

    # Large moment to trigger doubly reinforced condition
    forces = Forces(M_y=600 * kNm)
    node = Node(beam, forces)

    # Check flexure
    node.design()

    # Check for "✅  D.R." in the checks
    checks = beam._data_min_max_flexure["Ok?"]
    # Either position 0 (top) or position 2 (bottom) should have "✅  D.R."
    assert "✅ D.R." in checks[0] or "✅ D.R." in checks[2]


## BEAM RESULTS TESTS


@pytest.fixture
def sample_beam() -> RectangularBeam:
    """Create a sample beam for testing."""
    concrete = Concrete_ACI_318_19(name="C25", f_c=25 * MPa)
    steel = SteelBar(name="ADN420", f_y=420 * MPa)

    beam = RectangularBeam(
        label="TEST",
        concrete=concrete,
        steel_bar=steel,
        width=20 * cm,
        height=50 * cm,
        c_c=2.5 * cm,
    )
    return beam


def test_beam_data_property(sample_beam: RectangularBeam) -> None:
    """Test the data property displays beam information."""
    with patch("mento.reports.views.display") as mock_display:
        # Call the property
        result = sample_beam.data

        # Should return None
        assert result is None

        # Check that display was called
        mock_display.assert_called_once()

        # Check that markdown content was stored
        assert hasattr(sample_beam, "_md_data")
        assert sample_beam.label in sample_beam._md_data
        assert "Concrete" in sample_beam._md_data


def test_flexure_results_property_not_checked(sample_beam: RectangularBeam) -> None:
    """Test flexure_results property when flexure not checked."""
    with patch("mento.reports.views.display"):
        with pytest.warns(UserWarning, match="Flexural design has not been performed"):
            result = sample_beam.flexure_results

        assert result is None
        assert sample_beam._md_flexure_results == "Flexural results are not available."


def test_flexure_results_property_after_check() -> None:
    """Test flexure_results property after checking."""
    concrete = Concrete_ACI_318_19(name="C25", f_c=25 * MPa)
    steel = SteelBar(name="ADN420", f_y=420 * MPa)
    beam = RectangularBeam(
        label="TEST",
        concrete=concrete,
        steel_bar=steel,
        width=20 * cm,
        height=50 * cm,
        c_c=2.5 * cm,
    )
    beam.set_longitudinal_rebar_bot(n1=4, d_b1=16 * mm)
    beam.set_longitudinal_rebar_top(n1=2, d_b1=12 * mm)

    forces = Forces(M_y=50 * kNm)
    node = Node(beam, forces)
    node.check_flexure()

    with patch("mento.reports.views.display") as mock_display:
        result = beam.flexure_results

        # Should return None
        assert result is None

        # Display should have been called
        mock_display.assert_called_once()

        # Markdown content should contain flexure info
        assert hasattr(beam, "_md_flexure_results")
        assert "longitudinal rebar" in beam._md_flexure_results.lower()


def test_shear_results_property_not_checked(sample_beam: RectangularBeam) -> None:
    """Test shear_results property when shear not checked."""
    with patch("mento.reports.views.display"):
        with pytest.warns(UserWarning, match="Shear design has not been performed"):
            result = sample_beam.shear_results

        assert result is None
        assert sample_beam._md_shear_results == "Shear results are not available."


def test_shear_results_property_after_check() -> None:
    """Test shear_results property after checking."""
    concrete = Concrete_ACI_318_19(name="C25", f_c=25 * MPa)
    steel = SteelBar(name="ADN420", f_y=420 * MPa)
    beam = RectangularBeam(
        label="TEST",
        concrete=concrete,
        steel_bar=steel,
        width=20 * cm,
        height=50 * cm,
        c_c=2.5 * cm,
    )
    beam.set_transverse_rebar(n_stirrups=2, d_b=8 * mm, s_l=20 * cm)

    forces = Forces(M_y=0 * kNm, N_x=0 * kN, V_z=50 * kN)
    node = Node(beam, forces)
    node.check_shear()

    with patch("mento.reports.views.display") as mock_display:
        result = beam.shear_results

        assert result is None
        mock_display.assert_called_once()
        assert hasattr(beam, "_md_shear_results")
        assert "shear" in beam._md_shear_results.lower()


def test_results_property_combined() -> None:
    """Test the combined results property."""
    concrete = Concrete_ACI_318_19(name="C25", f_c=25 * MPa)
    steel = SteelBar(name="ADN420", f_y=420 * MPa)
    beam = RectangularBeam(
        label="TEST",
        concrete=concrete,
        steel_bar=steel,
        width=20 * cm,
        height=50 * cm,
        c_c=2.5 * cm,
    )
    beam.set_longitudinal_rebar_bot(n1=4, d_b1=16 * mm)
    beam.set_transverse_rebar(n_stirrups=2, d_b=8 * mm, s_l=20 * cm)

    forces = Forces(M_y=50 * kNm, N_x=0 * kN, V_z=50 * kN)
    node = Node(beam, forces)
    node.check()

    with patch("mento.reports.views.display") as mock_display:
        result = beam.results

        assert result is None
        # Display should be called multiple times (data, flexure, shear)
        assert mock_display.call_count >= 1


def test_flexure_results_detailed_not_checked(sample_beam: RectangularBeam) -> None:
    """Test flexure_results_detailed when not checked."""
    with pytest.warns(UserWarning, match="Flexural check has not been performed"):
        result = sample_beam.flexure_results_detailed()
        assert result is None


def test_flexure_results_detailed_after_check(capsys) -> None:
    """Test flexure_results_detailed prints output."""
    concrete = Concrete_ACI_318_19(name="C25", f_c=25 * MPa)
    steel = SteelBar(name="ADN420", f_y=420 * MPa)
    beam = RectangularBeam(
        label="TEST",
        concrete=concrete,
        steel_bar=steel,
        width=20 * cm,
        height=50 * cm,
        c_c=2.5 * cm,
    )
    beam.set_longitudinal_rebar_bot(n1=4, d_b1=16 * mm)
    beam.set_longitudinal_rebar_top(n1=2, d_b1=12 * mm)

    forces = Forces(M_y=50 * kNm)
    node = Node(beam, forces)
    node.check_flexure()

    beam.flexure_results_detailed()

    # Capture printed output
    captured = capsys.readouterr()
    assert "BEAM FLEXURE DETAILED RESULTS" in captured.out
    assert "Materials" in captured.out


def _designed_beam_for_code(concrete) -> RectangularBeam:
    """A designed beam carrying a positive moment, for output-wording checks."""
    steel = SteelBar(name="ADN420", f_y=420 * MPa)
    beam = RectangularBeam(
        label="SYM",
        concrete=concrete,
        steel_bar=steel,
        width=20 * cm,
        height=60 * cm,
        c_c=25 * mm,
    )
    Node(beam, Forces(label="C1", M_y=100 * kNm, V_z=80 * kN)).design()
    return beam


@pytest.mark.parametrize(
    "concrete_factory, demand, capacity, foreign_demand",
    [
        (
            lambda: Concrete_EN_1992_2004(name="C25", f_c=25 * MPa),
            "M_{Ed}",
            "M_{Rd}",
            "M_u",
        ),
        (
            lambda: Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
            "M_u",
            r"\phi M_n",
            "M_{Ed}",
        ),
        (
            lambda: Concrete_CIRSOC_201_25(name="H25", f_c=25 * MPa),
            "M_u",
            r"\phi M_n",
            "M_{Ed}",
        ),
    ],
    ids=["EN_1992_2004", "ACI_318_19", "CIRSOC_201_25"],
)
def test_flexure_markdown_uses_the_symbols_of_the_design_code(
    concrete_factory, demand: str, capacity: str, foreign_demand: str
) -> None:
    """The Jupyter markdown line must not label a Eurocode result with ACI symbols.

    EN 1992-2004 reports M_Ed against M_Rd; ACI 318-19 and CIRSOC 201-25 report
    M_u against phi*M_n.
    """
    beam = _designed_beam_for_code(concrete_factory())
    beam.flexure_results

    markdown = beam._md_flexure_results
    assert f"${demand}$" in markdown
    assert f"${capacity}$" in markdown
    assert f"${foreign_demand}$" not in markdown


@pytest.mark.parametrize(
    "concrete_factory, demand_top, demand_bot, foreign",
    [
        (
            lambda: Concrete_EN_1992_2004(name="C25", f_c=25 * MPa),
            "MEd,top",
            "MEd,bot",
            "Mu,",
        ),
        (
            lambda: Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
            "Mu,top",
            "Mu,bot",
            "MEd,",
        ),
        (
            lambda: Concrete_CIRSOC_201_25(name="H25", f_c=25 * MPa),
            "Mu,top",
            "Mu,bot",
            "MEd,",
        ),
    ],
    ids=["EN_1992_2004", "ACI_318_19", "CIRSOC_201_25"],
)
def test_flexure_detailed_forces_use_the_symbols_of_the_design_code(
    capsys, concrete_factory, demand_top: str, demand_bot: str, foreign: str
) -> None:
    """The limiting-case design-forces table must follow the active code.

    The per-code result dictionaries already carry the right wording; this pins
    the summary that ``flexure_results_detailed`` assembles for the limiting case,
    which used to be hard-coded to the ACI symbols whatever the code.
    """
    beam = _designed_beam_for_code(concrete_factory())
    beam.flexure_results_detailed()

    captured = capsys.readouterr()
    assert demand_top in captured.out
    assert demand_bot in captured.out
    assert foreign not in captured.out


def test_shear_results_detailed_not_checked(sample_beam) -> None:
    """Test shear_results_detailed when not checked."""
    with pytest.warns(UserWarning, match="Shear check has not been performed"):
        result = sample_beam.shear_results_detailed()
        assert result is None


def test_shear_results_detailed_after_check(capsys) -> None:
    """Test shear_results_detailed prints output."""
    concrete = Concrete_ACI_318_19(name="C25", f_c=25 * MPa)
    steel = SteelBar(name="ADN420", f_y=420 * MPa)
    beam = RectangularBeam(
        label="TEST",
        concrete=concrete,
        steel_bar=steel,
        width=20 * cm,
        height=50 * cm,
        c_c=2.5 * cm,
    )
    beam.set_transverse_rebar(n_stirrups=2, d_b=8 * mm, s_l=20 * cm)

    forces = Forces(M_y=0 * kNm, N_x=0 * kN, V_z=50 * kN)
    node = Node(beam, forces)
    node.check_shear()

    beam.shear_results_detailed()

    captured = capsys.readouterr()
    assert "BEAM SHEAR DETAILED RESULTS" in captured.out
    assert "Materials" in captured.out


def test_flexure_results_detailed_with_specific_force() -> None:
    """Test flexure_results_detailed with specific Forces object."""
    concrete = Concrete_ACI_318_19(name="C25", f_c=25 * MPa)
    steel = SteelBar(name="ADN420", f_y=420 * MPa)
    beam = RectangularBeam(
        label="TEST",
        concrete=concrete,
        steel_bar=steel,
        width=20 * cm,
        height=50 * cm,
        c_c=2.5 * cm,
    )
    beam.set_longitudinal_rebar_bot(n1=4, d_b1=16 * mm)

    forces = Forces(label="F1", M_y=50 * kNm, N_x=0 * kN, V_z=0 * kN)
    node = Node(beam, forces)
    node.check_flexure()

    # Should work with the specific force
    beam.flexure_results_detailed(force=forces)


def test_flexure_results_detailed_invalid_force() -> None:
    """Test flexure_results_detailed with invalid Forces object."""
    concrete = Concrete_ACI_318_19(name="C25", f_c=25 * MPa)
    steel = SteelBar(name="ADN420", f_y=420 * MPa)
    beam = RectangularBeam(
        label="TEST",
        concrete=concrete,
        steel_bar=steel,
        width=20 * cm,
        height=50 * cm,
        c_c=2.5 * cm,
    )
    beam.set_longitudinal_rebar_bot(n1=4, d_b1=16 * mm)

    forces1 = Forces(M_y=50 * kNm)
    node = Node(beam, forces1)
    node.check_flexure()

    # Try with a different force that wasn't checked
    forces2 = Forces(M_y=100 * kNm)

    with pytest.raises(ValueError, match="No results found for Forces object"):
        beam.flexure_results_detailed(force=forces2)


##########################################################
# WORD DOCUMENT EXPORTS (flexure / shear detailed doc)
##########################################################


def _build_checked_beam_doc() -> tuple[RectangularBeam, Forces]:
    """Beam with flexure and shear already checked, ready for the _doc exports."""
    concrete = Concrete_ACI_318_19(name="C25", f_c=25 * MPa)
    steel = SteelBar(name="ADN420", f_y=420 * MPa)
    beam = RectangularBeam(
        label="DOC",
        concrete=concrete,
        steel_bar=steel,
        width=20 * cm,
        height=50 * cm,
        c_c=2.5 * cm,
    )
    beam.set_longitudinal_rebar_bot(n1=4, d_b1=16 * mm)
    beam.set_longitudinal_rebar_top(n1=2, d_b1=12 * mm)
    beam.set_transverse_rebar(n_stirrups=1, d_b=8 * mm, s_l=20 * cm)

    forces = Forces(label="ELU", M_y=50 * kNm, V_z=80 * kN)
    node = Node(beam, forces)
    node.check_flexure()
    node.check_shear()
    return beam, forces


@pytest.fixture()
def saved_docs(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Intercepts DocumentBuilder.save so the doc exports run without writing files."""
    saved: list[str] = []
    monkeypatch.setattr(DocumentBuilder, "save", lambda self, filename: saved.append(filename))
    return saved


def test_flexure_results_detailed_doc_limiting_case(saved_docs: list[str]) -> None:
    """Default call builds the doc from the top/bottom limiting cases."""
    beam, _ = _build_checked_beam_doc()

    beam.flexure_results_detailed_doc()

    assert saved_docs == ["Beam DOC flexure check ACI 318-19.docx"]


def test_flexure_results_detailed_doc_with_force(saved_docs: list[str]) -> None:
    """Passing an explicit force uses that combination's stored results."""
    beam, forces = _build_checked_beam_doc()

    beam.flexure_results_detailed_doc(force=forces)

    assert saved_docs == ["Beam DOC flexure check ACI 318-19.docx"]


def test_flexure_results_detailed_doc_not_checked(saved_docs: list[str]) -> None:
    """Without a previous check the method warns and does not build a document."""
    concrete = Concrete_ACI_318_19(name="C25", f_c=25 * MPa)
    steel = SteelBar(name="ADN420", f_y=420 * MPa)
    beam = RectangularBeam(
        label="DOC",
        concrete=concrete,
        steel_bar=steel,
        width=20 * cm,
        height=50 * cm,
        c_c=2.5 * cm,
    )

    with pytest.warns(UserWarning, match="Flexural check has not been performed"):
        beam.flexure_results_detailed_doc()

    assert beam._md_flexure_results == "Flexural results are not available."
    assert saved_docs == []


def test_flexure_results_detailed_doc_invalid_force(saved_docs: list[str]) -> None:
    beam, _ = _build_checked_beam_doc()
    other_force = Forces(M_y=100 * kNm)

    with pytest.raises(ValueError, match="No results found for Forces object"):
        beam.flexure_results_detailed_doc(force=other_force)

    assert saved_docs == []


@pytest.mark.parametrize("missing_face", ["top", "bot"])
def test_flexure_results_detailed_doc_missing_limiting_case(saved_docs: list[str], missing_face: str) -> None:
    """A missing limiting case detail is reported instead of failing later on."""
    beam, _ = _build_checked_beam_doc()
    setattr(beam, f"_limiting_case_flexure_{missing_face}_details", None)

    with pytest.raises(ValueError, match="limiting case details are not available"):
        beam.flexure_results_detailed_doc()

    assert saved_docs == []


@pytest.mark.parametrize("missing_face", ["top", "bot"])
def test_flexure_results_detailed_missing_limiting_case(missing_face: str) -> None:
    """Same guard as the doc export, on the printed version."""
    beam, _ = _build_checked_beam_doc()
    setattr(beam, f"_limiting_case_flexure_{missing_face}_details", None)

    with pytest.raises(ValueError, match="limiting case details are not available"):
        beam.flexure_results_detailed()


def test_shear_results_detailed_doc_limiting_case(saved_docs: list[str]) -> None:
    beam, _ = _build_checked_beam_doc()

    beam.shear_results_detailed_doc()

    assert saved_docs == ["Beam DOC shear check ACI 318-19.docx"]


def test_shear_results_detailed_doc_with_force(saved_docs: list[str]) -> None:
    beam, forces = _build_checked_beam_doc()

    beam.shear_results_detailed_doc(force=forces)

    assert saved_docs == ["Beam DOC shear check ACI 318-19.docx"]


def test_shear_results_detailed_doc_not_checked(saved_docs: list[str]) -> None:
    concrete = Concrete_ACI_318_19(name="C25", f_c=25 * MPa)
    steel = SteelBar(name="ADN420", f_y=420 * MPa)
    beam = RectangularBeam(
        label="DOC",
        concrete=concrete,
        steel_bar=steel,
        width=20 * cm,
        height=50 * cm,
        c_c=2.5 * cm,
    )

    with pytest.warns(UserWarning, match="Shear check has not been performed"):
        beam.shear_results_detailed_doc()

    assert beam._md_shear_results == "Shear results are not available."
    assert saved_docs == []


def test_shear_results_detailed_doc_invalid_force(saved_docs: list[str]) -> None:
    beam, _ = _build_checked_beam_doc()
    other_force = Forces(V_z=200 * kN)

    with pytest.raises(ValueError, match="No results found for Forces object"):
        beam.shear_results_detailed_doc(force=other_force)

    assert saved_docs == []


def test_results_detailed_doc_write_real_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """End-to-end: the .docx files are actually written to the working directory."""
    monkeypatch.chdir(tmp_path)
    beam, _ = _build_checked_beam_doc()

    beam.flexure_results_detailed_doc()
    beam.shear_results_detailed_doc()

    assert (tmp_path / "Beam DOC flexure check ACI 318-19.docx").is_file()
    assert (tmp_path / "Beam DOC shear check ACI 318-19.docx").is_file()


##########################################################
# REBAR LABELS AND SECTION PLOT DETAILS
##########################################################


def _plot_beam(
    n_stirrups: int = 1,
    d_b_stirrup: Quantity = 8 * mm,
    s_l: Quantity = 20 * cm,
    **bottom_rebar: object,
) -> RectangularBeam:
    """Metric beam wide enough for intermediate bars, already plotted."""
    concrete = Concrete_ACI_318_19(name="C25", f_c=25 * MPa)
    steel = SteelBar(name="ADN420", f_y=420 * MPa)
    beam = RectangularBeam(
        label="PLOT",
        concrete=concrete,
        steel_bar=steel,
        width=40 * cm,
        height=50 * cm,
        c_c=2.5 * cm,
    )
    if n_stirrups > 0:
        beam.set_transverse_rebar(n_stirrups=n_stirrups, d_b=d_b_stirrup, s_l=s_l)
    if bottom_rebar:
        beam.set_longitudinal_rebar_bot(**bottom_rebar)  # type: ignore[arg-type]
    beam.plot()
    return beam


def test_plot_draws_intermediate_bars() -> None:
    """n2 > 0 adds the intermediate bars of the layer, with their own diameter."""
    beam = _plot_beam(n1=2, d_b1=16 * mm, n2=2, d_b2=12 * mm)
    circles = [p for p in beam._ax.patches if isinstance(p, Circle)]

    radii = sorted(round(c.get_radius(), 4) for c in circles)
    # 2 bottom side bars Ø16, 2 intermediate Ø12, plus the 2 default top Ø8 bars
    assert radii == [0.4, 0.4, 0.6, 0.6, 0.8, 0.8]

    texts = [t.get_text() for t in beam._ax.texts]
    assert "2Ø16+2Ø12" in texts

    plt.close()


def test_plot_single_bar_layer_is_centered() -> None:
    """A one-bar layer is centered instead of spread between the stirrup legs."""
    beam = _plot_beam(n_stirrups=0, d_b_stirrup=0 * mm, s_l=0 * cm, n1=1, d_b1=16 * mm)
    circles = [p for p in beam._ax.patches if isinstance(p, Circle)]

    bottom_bar = next(c for c in circles if np.isclose(c.get_radius(), 0.8))
    # Centred on the section, where the clear-spacing model puts it: no corner nudge.
    assert np.isclose(bottom_bar.get_center()[0], beam.width.to("cm").magnitude / 2)

    plt.close()


def test_plot_annotates_stirrups_and_draws_two_legs() -> None:
    beam = _plot_beam(n_stirrups=2, d_b_stirrup=6 * mm, s_l=20 * cm)

    # Unchecked: the configuration, with no maximum; three cage lines.
    assert [text.get_text() for text in beam._ax.texts if text.get_gid() == "stirrup_text"][:3] == [
        "4 legs Ø6 mm @ 20 cm",
        f"{beam.reinforcement.transverse.s_w.to('cm'):.4g~P} between legs",
        "perimeter stirrup + 2 open legs",
    ]

    fancy_bboxes = [p for p in beam._ax.patches if isinstance(p, FancyBboxPatch)]
    assert len(fancy_bboxes) == 2, "One perimeter stirrup, plus two open legs."

    plt.close()


def test_plot_six_legs_use_one_perimeter_and_four_open_legs() -> None:
    beam = _plot_beam(n_stirrups=3, d_b_stirrup=6 * mm, s_l=15 * cm)

    fancy_bboxes = [p for p in beam._ax.patches if isinstance(p, FancyBboxPatch)]
    assert len(fancy_bboxes) == 2, "One perimeter closed stirrup."

    texts = [t.get_text() for t in beam._ax.texts]
    assert "6 legs Ø6 mm @ 15 cm" in texts
    assert "perimeter stirrup + 4 open legs" in texts

    plt.close()


def test_plot_without_stirrups_has_no_stirrup_text() -> None:
    beam = _plot_beam(n_stirrups=0, d_b_stirrup=0 * mm, s_l=0 * cm)

    texts = [t.get_text() for t in beam._ax.texts]
    assert not any("legs" in t for t in texts)
    assert not [p for p in beam._ax.patches if isinstance(p, FancyBboxPatch)]

    plt.close()


def _outer_patches(ax: object) -> list[FancyBboxPatch]:
    """The outer line of each drawn stirrup: every other FancyBboxPatch, in drawing order."""
    return [p for p in ax.patches if isinstance(p, FancyBboxPatch)][::2]  # type: ignore[attr-defined]


def _drawn_leg_gaps(ax: object, d_cm: float) -> list[float]:
    """Centre-to-centre gaps between every drawn leg, left to right."""
    legs = sorted(x for p in _outer_patches(ax) for x in (p.get_x() + d_cm / 2, p.get_x() + p.get_width() - d_cm / 2))
    legs += [p.get_x() + d_cm / 2 for p in ax.patches if p.get_gid() == "crosstie"]  # type: ignore[attr-defined]
    legs.sort()
    return [b - a for a, b in zip(legs, legs[1:])]


def test_plot_draws_every_stirrup_at_the_legs_the_check_assumes() -> None:
    """The 150x150 CIRSOC beam under Mu 5000 kN·m, Vu 5000 kN: five stirrups, ten legs 15.87 cm apart, twelve Ø32.

    The old drawing capped the cage at three stirrups at fixed places, whose
    legs were up to 36.30 cm apart against the 20 cm the modelled 15.87 cm meets.
    """
    beam = _wide_cirsoc_beam()
    Node(section=beam, forces=[Forces(label="C1", M_y=5000 * kNm, V_z=5000 * kN)]).design()
    beam.plot()
    ax = beam._ax
    geometry = beam.detailing_geometry

    fancy = [p for p in ax.patches if isinstance(p, FancyBboxPatch)]
    assert len(fancy) == 2
    d = geometry.stirrup_d_b.to("cm").magnitude
    for outer, stirrup in zip(_outer_patches(ax), geometry.stirrups):
        assert outer.get_x() == pytest.approx(stirrup.x_left.to("cm").magnitude - d / 2)
        assert outer.get_width() == pytest.approx((stirrup.x_right - stirrup.x_left).to("cm").magnitude + d)
    gaps = _drawn_leg_gaps(ax, d)
    assert max(gaps) == pytest.approx(15.8667, abs=1e-4)
    assert gaps == pytest.approx([15.8667] * 9, abs=1e-4)

    circles = [p for p in ax.patches if isinstance(p, Circle)]
    assert len(circles) == 28
    assert len([c for c in circles if c.get_gid() == "resistant_bar"]) == 12
    assert len([c for c in circles if c.get_gid() == "mounting_bar"]) == 10
    assert len([c for c in circles if c.get_gid() == "skin_bar"]) == 6
    all_bars = geometry.bars + geometry.mounting_bars + geometry.skin_bars
    assert [c.get_center()[0] for c in circles] == pytest.approx([b.x.to("cm").magnitude for b in all_bars])
    assert [c.get_center()[1] for c in circles] == pytest.approx([b.y.to("cm").magnitude for b in all_bars])

    texts = [t.get_text() for t in ax.texts]
    assert texts[-5:] == [
        "10 legs Ø12 mm @ 14 cm",
        "15.87 cm between legs (max 20 cm)",
        "perimeter stirrup + 8 open legs",
        "Orange: mounting steel · excluded from resistance",
        "Skin: 3Ø10 per side · s=23.1 cm · excluded from resistance",
    ]
    assert "12Ø32" in texts
    plt.close()


def test_plot_of_the_aci_beam_keeps_its_legs_within_30_cm() -> None:
    beam = RectangularBeam(
        label="V1",
        concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=150 * cm,
        height=150 * cm,
        c_c=30 * mm,
    )
    Node(section=beam, forces=[Forces(label="C1", M_y=5000 * kNm, V_z=5000 * kN)]).design()
    beam.plot()
    fancy = [p for p in beam._ax.patches if isinstance(p, FancyBboxPatch)]
    assert len(fancy) == 2
    gaps = _drawn_leg_gaps(beam._ax, beam._stirrup_d_b.to("cm").magnitude)
    assert max(gaps) == pytest.approx(28.48, abs=0.005)
    assert "28.48 cm between legs (max 30 cm)" in [t.get_text() for t in beam._ax.texts]
    plt.close()


def test_plot_draws_a_crosstie_from_the_geometry() -> None:
    """The helpers take the axes and a geometry, so an odd cage can be drawn."""
    from dataclasses import replace

    from mento.plots.sections import _plot_stirrups_in_section
    from mento.section_geometry import Crosstie

    beam = _plot_beam(n_stirrups=1, d_b_stirrup=8 * mm, s_l=20 * cm)
    geometry = beam.section_geometry
    perimeter = geometry.stirrups[0]
    with_tie = replace(
        geometry,
        crossties=(Crosstie(leg=1, x=20 * cm, y_bottom=perimeter.y_bottom, y_top=perimeter.y_top),),
    )
    fig, ax = plt.subplots()
    _plot_stirrups_in_section(ax, with_tie)
    ties = [p for p in ax.patches if p.get_gid() == "crosstie"]
    assert len(ties) == 1
    assert ties[0].get_x() == pytest.approx(20 - 0.4)
    assert len([line for line in ax.lines if line.get_gid() == "crosstie_hook"]) == 0
    assert len([p for p in ax.patches if isinstance(p, FancyBboxPatch)]) == 2
    plt.close(fig)
    plt.close()


def test_plot_layer_text_follows_the_bars() -> None:
    """With d_b2 > d_b1 the label sits at the middle of the band the bars occupy."""
    beam = _plot_beam(n1=2, d_b1=12 * mm, n2=1, d_b2=25 * mm)
    label = next(t for t in beam._ax.texts if t.get_text() == "2Ø12+1Ø25")
    inner = 2.5 + beam._stirrup_d_b.to("cm").magnitude
    assert label.get_position()[1] == pytest.approx(inner + 2.5 / 2)
    plt.close()


def test_plot_follows_the_language() -> None:
    import mento

    beam = _wide_cirsoc_beam()
    Node(section=beam, forces=[Forces(label="C1", M_y=5000 * kNm, V_z=5000 * kN)]).design()
    mento.set_language("es")
    beam.plot()
    texts = [t.get_text() for t in beam._ax.texts]
    assert "estribo perimetral + 8 patas abiertas" in texts
    assert "Montaje en naranja · sin aporte resistente" in texts
    assert texts[-1] == "Piel: 3Ø10 por lateral · s=23.1 cm · sin aporte resistente"
    assert any(text.startswith("10 ramas") for text in texts)
    plt.close()


def _text_extents(beam: RectangularBeam) -> list[tuple[str, Any]]:
    """Every non-empty text of the drawing with its extent on the canvas, at the default figure size."""
    beam._fig.canvas.draw()
    return [(t.get_text(), t.get_window_extent()) for t in beam._ax.texts if t.get_text()]


@pytest.mark.parametrize("language", ["en", "es"])
def test_plot_text_fits_the_default_figure(language: str) -> None:
    """The three stirrup lines of the 150x150 beam stay inside a plain 640x480 savefig, in both languages."""
    import mento

    mento.set_language(language)
    beam = _wide_cirsoc_beam()
    Node(section=beam, forces=[Forces(label="C1", M_y=5000 * kNm, V_z=5000 * kN)]).design()
    beam.plot()
    figure_box = beam._fig.bbox
    assert (figure_box.width, figure_box.height) == (640, 480)
    for text, extent in _text_extents(beam):
        assert figure_box.x0 <= extent.x0 and extent.x1 <= figure_box.x1, text
        assert figure_box.y0 <= extent.y0 and extent.y1 <= figure_box.y1, text


def test_plot_text_of_a_flat_beam_does_not_overlap() -> None:
    """120x25 with two bottom layers: layer labels and stirrup text each print clear of the others.

    The stirrup lines sit under the section, below its width, and two layer
    labels closer than a line are moved apart.
    """
    beam = RectangularBeam(
        label="FLAT",
        concrete=Concrete_CIRSOC_201_25(name="H-25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=120 * cm,
        height=25 * cm,
        c_c=25 * mm,
    )
    beam.set_longitudinal_rebar_bot(n1=2, d_b1=16 * mm, n2=8, d_b2=16 * mm, n3=2, d_b3=12 * mm)
    beam.set_longitudinal_rebar_top(n1=2, d_b1=12 * mm, n2=6, d_b2=10 * mm)
    beam.set_transverse_rebar(n_stirrups=4, d_b=8 * mm, s_l=13 * cm)
    beam.plot()
    extents = _text_extents(beam)
    for i, (text_a, a) in enumerate(extents):
        for text_b, b in extents[i + 1 :]:
            assert not a.overlaps(b), (text_a, text_b)
    # The stirrup text reads under the section.
    section_bottom = beam._ax.transData.transform((0.0, 0.0))[1]
    stirrup_lines = [t for t in beam._ax.texts if t.get_gid() == "stirrup_text"]
    assert len(stirrup_lines) == 4
    assert stirrup_lines[-1].get_text() == "Tension-bar spacing pending · no flexure verification"
    assert all(t.get_window_extent().y1 < section_bottom for t in stirrup_lines)
    # A label with room stays at its layer: the top layer's is at the middle of its bars.
    top = beam.section_geometry.bars_on("top", 1)
    low = min((bar.y - bar.d_b / 2).to("cm").magnitude for bar in top)
    high = max((bar.y + bar.d_b / 2).to("cm").magnitude for bar in top)
    label = next(t for t in beam._ax.texts if t.get_text() == "2Ø12+6Ø10")
    assert label.get_position()[1] == pytest.approx((low + high) / 2)
    plt.close()


def test_plot_spread_keeps_labels_with_room_and_parts_those_without() -> None:
    from mento.plots.sections import _spread

    assert _spread([0.0, 50.0], 10.0) == [0.0, 50.0]
    assert _spread([0.0, 4.0], 10.0) == pytest.approx([-3.0, 7.0])
    # A group that runs into the next one merges with it.
    assert _spread([0.0, 4.0, 12.0], 10.0) == pytest.approx([16 / 3 - 10, 16 / 3, 16 / 3 + 10])


def test_plot_narrow_cage_falls_back_to_labelled_calculation_geometry() -> None:
    """ACI 20x30, Vu 100 kN: two Ø10 stirrups, legs 4.67 cm apart, less than the 5·d_st two bends take.

    The valid perimeter remains visible; unnecessary narrow closed pieces
    are no longer invented. The calculation caption still rejects this cage.
    """
    beam = RectangularBeam(
        label="N",
        concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=20 * cm,
        height=30 * cm,
        c_c=25 * mm,
    )
    Node(section=beam, forces=[Forces(label="C1", V_z=100 * kN)]).design()
    assert beam.shear_design.n_stirrups == 2
    assert beam.shear_design.s_w.to("cm").magnitude < 5 * beam._stirrup_d_b.to("cm").magnitude
    with pytest.warns(UserWarning, match="Cage detailing is not feasible"):
        beam.plot()
    assert "Calculation model only · cage detailing not feasible" in [text.get_text() for text in beam._ax.texts]
    fancy = [p for p in beam._ax.patches if isinstance(p, FancyBboxPatch)]
    assert len(fancy) == 2  # El perimetral válido permanece en la geometría de cálculo.
    assert len([p for p in beam._ax.patches if p.get_gid() == "crosstie"]) == 2
    plt.close()


def test_plot_show_true_calls_pyplot_show(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[bool] = []
    monkeypatch.setattr(plt, "show", lambda *args, **kwargs: calls.append(True))

    concrete = Concrete_ACI_318_19(name="C25", f_c=25 * MPa)
    steel = SteelBar(name="ADN420", f_y=420 * MPa)
    beam = RectangularBeam(
        label="PLOT",
        concrete=concrete,
        steel_bar=steel,
        width=20 * cm,
        height=50 * cm,
        c_c=2.5 * cm,
    )
    beam.plot(show=True)

    assert calls == [True]

    plt.close()


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        ((3, 12 * mm, 2, 12 * mm), "5Ø12"),  # slab always merges both groups
        ((0, None, 4, 10 * mm), "4Ø10"),  # only the second group has bars
        ((0, None, 0, None), ""),  # nothing to draw
        ((2, None, 0, None), ""),  # bars without a diameter are ignored
    ],
)
def test_format_rebar_layer_text_slab_mode(args: tuple, expected: str) -> None:
    beam = build_metric_beam()
    beam.mode = "slab"

    assert _format_rebar_layer_text(beam, *args) == expected


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        ((2, 16 * mm, 3, 16 * mm), "5Ø16"),  # same diameter -> merged
        ((2, 16 * mm, 3, 12 * mm), "2Ø16+3Ø12"),  # different diameters -> both groups
        ((2, 16 * mm, 0, None), "2Ø16"),
        ((0, None, 0, None), ""),
    ],
)
def test_format_rebar_layer_text_beam_mode(args: tuple, expected: str) -> None:
    beam = build_metric_beam()

    assert _format_rebar_layer_text(beam, *args) == expected


def test_format_longitudinal_rebar_string_only_second_group() -> None:
    beam = build_metric_beam()

    assert beam._format_longitudinal_rebar_string(0, 0 * mm, 2, 12 * mm) == "2Ø12"


##########################################################
# DEFENSIVE PATHS
##########################################################


def test_shear_results_detailed_with_force() -> None:
    """The printed shear report can be asked for one specific combination."""
    beam, forces = _build_checked_beam_doc()

    beam.shear_results_detailed(force=forces)


def test_shear_results_detailed_invalid_force() -> None:
    beam, _ = _build_checked_beam_doc()

    with pytest.raises(ValueError, match="No results found for Forces object"):
        beam.shear_results_detailed(force=Forces(V_z=200 * kN))


def test_flexure_results_markdown_without_top_details() -> None:
    beam, _ = _build_checked_beam_doc()
    beam._limiting_case_flexure_top_details = {}

    beam.flexure_results

    assert beam._md_flexure_results.startswith("No top moment to check.")


def test_flexure_results_markdown_without_bottom_details() -> None:
    beam, _ = _build_checked_beam_doc()
    beam._limiting_case_flexure_bot_details = {}

    beam.flexure_results

    assert beam._md_flexure_results.endswith("No bottom moment to check.")


def test_shear_results_markdown_EN_1992_without_stirrups(
    beam_example_EN_1992_2004_01: RectangularBeam,
) -> None:
    """EN 1992 wording, and the 'not assigned' label when there is no transverse rebar."""
    node = Node(section=beam_example_EN_1992_2004_01, forces=Forces(V_z=30 * kN))
    node.check_shear()

    beam_example_EN_1992_2004_01.shear_results

    markdown = beam_example_EN_1992_2004_01._md_shear_results
    assert "Shear reinforcing not assigned" in markdown
    assert "V_{Rd}" in markdown


def test_shear_results_markdown_without_limiting_case() -> None:
    beam, _ = _build_checked_beam_doc()
    beam._limiting_case_shear_details = {}

    beam.shear_results

    assert beam._md_shear_results == "No shear to check."


def test_an_unregistered_design_code_says_so_and_lists_what_is_registered() -> None:
    """The registry is the single place that knows which codes exist."""
    beam = build_metric_beam()
    beam.concrete.design_code = "NBR 6118-2014"

    with pytest.raises(NotImplementedError, match="unknown design code: NBR 6118-2014") as excinfo:
        beam._get_units_row_flexure()
    # Naming the registered codes is the point: the old error named neither the
    # code that was asked for nor the ones available.
    assert "ACI 318-19" in str(excinfo.value)
    assert "EN 1992-2004" in str(excinfo.value)

    # Every element entry point goes through the same lookup, not just this one.
    with pytest.raises(NotImplementedError, match="unknown design code"):
        beam.shear_check_results([Forces(label="C1", V_z=80 * kN)])


def test_plot_annotates_second_rebar_layer() -> None:
    """A second bottom layer gets its own label, shifted by the layer spacing."""
    beam = _plot_beam(n1=2, d_b1=16 * mm, n3=2, d_b3=12 * mm)

    texts = [t.get_text() for t in beam._ax.texts]
    assert "2Ø16" in texts
    assert "2Ø12" in texts

    plt.close()


def test_clear_top_longitudinal_imperial(beam_example_imperial: RectangularBeam) -> None:
    beam_example_imperial._clear_top_longitudinal()

    # No bars left on the top face, so it lists no layers at all.
    assert beam_example_imperial.reinforcement.top.layers == ()
    assert beam_example_imperial.reinforcement.top.n_bars == 0


def test_clearing_bottom_rebar_resets_centroid(
    beam_example_EN_1992_2004_01: RectangularBeam,
) -> None:
    """Clearing the bottom reinforcement must also clear its centroid."""
    beam = beam_example_EN_1992_2004_01

    beam.set_longitudinal_rebar_bot(n1=4, d_b1=20 * mm)
    assert beam._bot_rebar_centroid.to("mm").magnitude > 0

    beam.set_longitudinal_rebar_bot(n1=0, d_b1=0 * mm)

    assert beam._A_s_bot.to("mm**2").magnitude == pytest.approx(0)
    assert beam._bot_rebar_centroid.to("mm").magnitude == pytest.approx(0)


def test_clearing_top_rebar_resets_centroid(
    beam_example_EN_1992_2004_01: RectangularBeam,
) -> None:
    """Clearing the top reinforcement must also clear its centroid."""
    beam = beam_example_EN_1992_2004_01

    beam.set_longitudinal_rebar_top(n1=4, d_b1=20 * mm)
    assert beam._top_rebar_centroid.to("mm").magnitude > 0

    beam.set_longitudinal_rebar_top(n1=0, d_b1=0 * mm)

    assert beam._A_s_top.to("mm**2").magnitude == pytest.approx(0)
    assert beam._top_rebar_centroid.to("mm").magnitude == pytest.approx(0)


def test_longitudinal_rebar_area_ignores_none_diameters() -> None:
    """Diameters forced to None (not through the setters) count as zero area."""
    beam = build_metric_beam()
    beam.set_longitudinal_rebar_bot(n1=2, d_b1=16 * mm)
    A_s_bot = beam.reinforcement.bottom.A_s

    # Reaching into the private layer attributes on purpose: the point of the
    # test is that a None diameter left behind by an earlier layout does not
    # break the area calculation, and no public API can put one there.
    beam._d_b2_b = None
    beam._d_b3_b = None
    beam._calculate_longitudinal_rebar_area()

    assert beam.reinforcement.bottom.A_s.magnitude == pytest.approx(A_s_bot.magnitude)


# This is where pytest will collect the tests and run them
if __name__ == "__main__":
    pytest.main()


def test_check_order_does_not_change_the_flexure_result() -> None:
    """Checking shear must not change what a flexure check then reports.

    It used to: the shear check dropped the stirrup diameter the settings
    assume and recomputed the effective depths on the section, so the bottom
    DCR moved 1.84 % (0.59309 -> 0.58215, ``_d_bot`` 45.7 -> 46.5 cm) purely
    from the order of the two calls. Both checks now read the same ``d``.
    """

    def build() -> RectangularBeam:
        beam = RectangularBeam(
            label="order",
            concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
            steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
            width=30 * cm,
            height=50 * cm,
            c_c=25 * mm,
        )
        beam.set_longitudinal_rebar_bot(n1=3, d_b1=20 * mm)
        return beam

    combo = [Forces(label="C1", V_z=80 * kN, M_y=90 * kNm)]

    flexure_first = build().flexure_check_results(combo)[0]

    beam = build()
    beam.shear_check_results(combo)
    shear_first = beam.flexure_check_results(combo)[0]

    assert flexure_first.bottom.DCR == pytest.approx(shear_first.bottom.DCR)


def test_check_order_is_harmless_once_stirrups_are_configured() -> None:
    """The counterpart of the xfail above: with stirrups there is no assumption
    for the shear check to drop, so the order stops mattering."""

    def build() -> RectangularBeam:
        beam = RectangularBeam(
            label="order-ok",
            concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
            steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
            width=30 * cm,
            height=50 * cm,
            c_c=25 * mm,
        )
        beam.set_longitudinal_rebar_bot(n1=3, d_b1=20 * mm)
        beam.set_transverse_rebar(n_stirrups=1, d_b=8 * mm, s_l=20 * cm)
        return beam

    combo = [Forces(label="C1", V_z=80 * kN, M_y=90 * kNm)]

    flexure_first = build().flexure_check_results(combo)[0]
    beam = build()
    beam.shear_check_results(combo)
    shear_first = beam.flexure_check_results(combo)[0]

    assert flexure_first.bottom.DCR == pytest.approx(shear_first.bottom.DCR)


@pytest.mark.parametrize("with_stirrups", [False, True], ids=["no-stirrups", "with-stirrups"])
def test_a_check_does_not_change_the_section(with_stirrups: bool) -> None:
    """Running a check must leave the section's own identity alone.

    Geometry and reinforcement describe the section; a check only reports on
    them. Results still land on the beam as the documented compatibility layer,
    so this pins the geometry and the bars specifically — the part whose drift
    made the order of two checks matter.
    """
    beam = RectangularBeam(
        label="untouched",
        concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=30 * cm,
        height=50 * cm,
        c_c=25 * mm,
    )
    beam.set_longitudinal_rebar_bot(n1=3, d_b1=20 * mm)
    if with_stirrups:
        beam.set_transverse_rebar(n_stirrups=1, d_b=8 * mm, s_l=20 * cm)

    identity = (
        "_d_bot",
        "_d_top",
        "_d_shear",
        "_c_mec_bot",
        "_c_mec_top",
        "_stirrup_d_b",
        "_stirrup_n",
        "_stirrup_s_l",
        "_A_s_bot",
        "_A_s_top",
        "_A_v",
    )
    before = {name: getattr(beam, name) for name in identity}

    combo = [Forces(label="C1", V_z=80 * kN, M_y=90 * kNm)]
    beam.shear_check_results(combo)
    beam.flexure_check_results(combo)

    after = {name: getattr(beam, name) for name in identity}
    changed = [name for name in identity if repr(before[name]) != repr(after[name])]
    assert not changed, f"a check changed the section: {changed}"


@pytest.mark.parametrize("with_stirrups", [False, True], ids=["no-stirrups", "with-stirrups"])
@pytest.mark.parametrize(
    "concrete, steel",
    [
        (Concrete_ACI_318_19(name="H25", f_c=25 * MPa), SteelBar(name="ADN 420", f_y=420 * MPa)),
        (Concrete_EN_1992_2004(name="C25", f_c=25 * MPa), SteelBar(name="B500S", f_y=500 * MPa)),
    ],
    ids=["ACI", "EN"],
)
def test_shear_check_results_leaves_the_section_completely_untouched(
    concrete: Concrete_ACI_318_19, steel: SteelBar, with_stirrups: bool
) -> None:
    """The shear check returns its result instead of storing it.

    Not just geometry and bars: *no* attribute of the section changes. That is
    what lets a caller loop over stations without per-call cleanup, and it is
    the difference between this entry point and ``check_shear``, which does
    write the results back so the report tables can read them.
    """
    beam = RectangularBeam(
        label="pristine",
        concrete=concrete,
        steel_bar=steel,
        width=30 * cm,
        height=50 * cm,
        c_c=25 * mm,
    )
    beam.set_longitudinal_rebar_bot(n1=3, d_b1=20 * mm)
    if with_stirrups:
        beam.set_transverse_rebar(n_stirrups=1, d_b=8 * mm, s_l=20 * cm)

    # Bookkeeping the entry point is expected to update, and the report row it
    # does not build here.
    bookkeeping = ("_shear_checks", "_shear_warnings", "_shear_checked", "_shear_report_row")
    before = {k: repr(v) for k, v in vars(beam).items() if k not in bookkeeping}

    results = beam.shear_check_results([Forces(label="C1", V_z=80 * kN, M_y=90 * kNm)])

    after = {k: repr(v) for k, v in vars(beam).items() if k not in bookkeeping}
    assert results  # the check produced something, so the comparison means anything
    # Both directions: an attribute the check CREATES is a write too, and
    # comparing only the keys that existed before would miss it.
    changed = sorted(k for k in before if before[k] != after.get(k))
    added = sorted(set(after) - set(before))
    assert not changed, f"the check wrote to the section: {changed}"
    assert not added, f"the check added attributes to the section: {added}"
    assert results[0].DCR > 0


def test_check_shear_still_writes_the_results_the_report_needs() -> None:
    """The compatibility layer: the reporting path does copy the state back."""
    beam = RectangularBeam(
        label="reported",
        concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=30 * cm,
        height=50 * cm,
        c_c=25 * mm,
    )
    beam.set_longitudinal_rebar_bot(n1=3, d_b1=20 * mm)
    beam.set_transverse_rebar(n_stirrups=1, d_b=8 * mm, s_l=20 * cm)

    beam.check_shear([Forces(label="C1", V_z=80 * kN, M_y=90 * kNm)])

    assert beam._DCRv > 0
    assert beam.V_c.magnitude > 0
    assert beam._phi_V_n.magnitude > 0


@pytest.mark.parametrize("with_stirrups", [False, True], ids=["no-stirrups", "with-stirrups"])
@pytest.mark.parametrize(
    "concrete, steel",
    [
        (Concrete_ACI_318_19(name="H25", f_c=25 * MPa), SteelBar(name="ADN 420", f_y=420 * MPa)),
        (Concrete_EN_1992_2004(name="C25", f_c=25 * MPa), SteelBar(name="B500S", f_y=500 * MPa)),
    ],
    ids=["ACI", "EN"],
)
def test_flexure_check_results_leaves_the_section_completely_untouched(
    concrete: Concrete_ACI_318_19, steel: SteelBar, with_stirrups: bool
) -> None:
    """The flexure check returns its result too — same contract as shear."""
    beam = RectangularBeam(
        label="pristine-flexure",
        concrete=concrete,
        steel_bar=steel,
        width=30 * cm,
        height=50 * cm,
        c_c=25 * mm,
    )
    beam.set_longitudinal_rebar_bot(n1=3, d_b1=20 * mm)
    if with_stirrups:
        beam.set_transverse_rebar(n_stirrups=1, d_b=8 * mm, s_l=20 * cm)

    bookkeeping = ("_flexure_checks", "_flexure_checked", "_flexure_report_row")
    before = {k: repr(v) for k, v in vars(beam).items() if k not in bookkeeping}

    results = beam.flexure_check_results([Forces(label="C1", V_z=80 * kN, M_y=90 * kNm)])

    after = {k: repr(v) for k, v in vars(beam).items() if k not in bookkeeping}
    changed = sorted(k for k in before if before[k] != after.get(k))
    added = sorted(set(after) - set(before))
    assert not changed, f"the check wrote to the section: {changed}"
    assert not added, f"the check added attributes to the section: {added}"
    assert results[0].bottom.DCR > 0


def test_the_float_view_never_outlives_the_section_it_describes() -> None:
    """A stale precompute would be a silently wrong answer, not a crash."""
    beam = RectangularBeam(
        label="restirruped",
        concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=30 * cm,
        height=50 * cm,
        c_c=25 * mm,
    )
    beam.set_longitudinal_rebar_bot(n1=3, d_b1=20 * mm)
    combo = [Forces(label="C1", V_z=80 * kN, M_y=90 * kNm)]

    beam.set_transverse_rebar(n_stirrups=1, d_b=6 * mm, s_l=25 * cm)
    weak = beam.shear_check_results(combo)[0].DCR

    # Same section, more shear reinforcement: the check must see the new bars.
    beam.set_transverse_rebar(n_stirrups=1, d_b=12 * mm, s_l=10 * cm)
    strong = beam.shear_check_results(combo)[0].DCR

    assert strong < weak, f"the check reused a stale float view: {strong} vs {weak}"

    # And the view itself agrees with the section it was built from.
    floats = section_floats(beam)
    assert floats.A_v == pytest.approx(beam._A_v.to(mm).magnitude)
    assert floats.d_shear == pytest.approx(beam._d_shear.to(mm).magnitude)


def test_changing_the_geometry_rebuilds_the_float_view() -> None:
    """Longitudinal rebar moves the effective depth, so the view must follow."""
    beam = RectangularBeam(
        label="redepth",
        concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=30 * cm,
        height=50 * cm,
        c_c=25 * mm,
    )
    beam.set_longitudinal_rebar_bot(n1=2, d_b1=12 * mm)
    shallow = section_floats(beam)

    beam.set_longitudinal_rebar_bot(n1=2, d_b1=12 * mm, n2=2, d_b2=25 * mm)
    deep = section_floats(beam)

    assert deep is not shallow
    assert deep.d_shear != shallow.d_shear
    assert deep.d_shear == pytest.approx(beam._d_shear.to(mm).magnitude)


# ---------------------------------------------------------------------------
# Regression cases checked against Calcpad sheets (kept outside the repository)
# or against the hand calculation of the ETABS workbook rather than its ETABS run.
# They were marked published_example until a calculation reproduced by hand
# stopped counting as a validation source: it does not publish one. They
# stay as regression tests; the external validation of the same checks lives in
# tests/validation/ (CRSI Design Guide, CSI's ETABS verification examples,
# eurocodeapplied.com).
# ---------------------------------------------------------------------------


def test_flexure_check_EN_1992_2004_01(
    beam_example_EN_1992_2004_01: RectangularBeam,
) -> None:
    """Singly reinforced check: 20x60, C25/B500S, 4Ø16, M_Ed = 150 kN·m.

    Reference: Calcpad "EN 1992-1-1_2004 Beam Flexure 01 - Metric v2.cpd" for the case and
    A_s,min; A_s,req and M_Rd are re-derived by hand below with the closed form of
    The Concrete Centre's "How to design concrete structures using Eurocode 2",
    3. Slabs (Moss and Brooker, 2006), p. 3, Figure 1 and Table 5 (z/d for singly
    reinforced rectangular sections) -- the v2 sheet applied lambda twice to the
    lever arm and is not the source of those two.
    """
    f = Forces(M_y=150 * kNm)
    beam_example_EN_1992_2004_01.set_transverse_rebar(n_stirrups=1, d_b=6 * mm, s_l=15 * cm)
    beam_example_EN_1992_2004_01.set_longitudinal_rebar_bot(n1=4, d_b1=16 * mm)
    beam_example_EN_1992_2004_01.set_longitudinal_rebar_top(n1=0, d_b1=0 * mm)
    # Read back before any check has run: this asserts the layout that was just
    # set, not a result, which is what `reinforcement` is for.
    rebar = beam_example_EN_1992_2004_01.reinforcement
    assert rebar.bottom.A_s.to(cm**2).magnitude == pytest.approx(8.042, rel=1e-2)
    assert beam_example_EN_1992_2004_01._d_bot.to(cm).magnitude == pytest.approx(56.0, rel=1e-2)
    assert beam_example_EN_1992_2004_01.width.to(cm).magnitude == pytest.approx(20.0, rel=1e-2)
    assert rebar.transverse.d_b.to(mm).magnitude == pytest.approx(6.0, rel=1e-2)
    node = Node(section=beam_example_EN_1992_2004_01, forces=f)
    results = node.check_flexure()
    assert results.iloc[1]["Label"] == "B_Example_EN_01"
    assert results.iloc[1]["Position"] == "Bottom"
    assert results.iloc[1]["As,min"] == pytest.approx(1.49, rel=1e-2)
    # Cross-checked against the Concise Eurocode 2 closed form (The Concrete
    # Centre): K = M/(f_ck*b*d^2) = 0.09566, z/d = [1+sqrt(1-3.529K)]/2 -> z =
    # 507.89 mm, A_s = M/(0.87*f_yk*z) = 6.79 cm^2. Pure ES=0/EM=0 equilibrium
    # with the EC2 block gives the same. The previous 6.656 came from applying
    # lambda twice to the lever arm.
    assert results.iloc[1]["As,req bot"] == pytest.approx(6.79, rel=1e-3)
    assert results.iloc[1]["As,req top"] == pytest.approx(0, rel=1e-3)
    assert results.iloc[1]["As"] == pytest.approx(8.042, rel=1e-2)
    # M_Rd of the 4x16 provided: T = 804.2*434.78 = 349.7 kN, block depth
    # u = T/(eta*f_cd*b) = 123.41 mm, z = d - u/2 = 498.3 mm -> 174.24 kNm.
    assert results.iloc[1]["MRd"] == pytest.approx(174.24, rel=1e-3)
    assert results.iloc[1]["DCR"] == pytest.approx(0.861, rel=1e-3)


def test_check_flexure_ACI_318_19_3(beam_example_flexure_ACI: RectangularBeam) -> None:
    """Simple bending check: Mu pequeño → sección simple, no cae en doble armadura.

    Como es caso simple no lo tocan los fixes de doble armadura ni el displaced
    concrete, y el bloque de Whitney se rehace a mano (b = 12", d = 24 - 1.5 -
    0.375 - 1.41/2 = 21.42", A_s = 2#11 = 3.1229 in²):
      a = A_s·f_y/(0.85·f'c·b) = 3.1229·60/(0.85·4·12) = 4.5925"
      Mn = 3.1229·60·(21.42 - 4.5925/2) = 3583.3 kip·in ; ØMn = 0.9·Mn = 364.37 kN·m
      A_s,min = max(3√4000, 200)/60000·12·21.42 = 0.8568 in² = 5.53 cm²  (§9.6.1.2)
      A_s,req: 60·A_s·(21.42 - 0.7353·A_s) = 200·12/0.9 → A_s = 2.249 in² = 14.51 cm²

    Reference: Calcpad "ACI 318-19 Beam Flexure 03_v3 - test_3.cpd"; the numbers above
    are the hand check of that sheet.
    """
    f = Forces(label="Test_03", M_y=200 * kip * ft)
    beam_example_flexure_ACI.set_longitudinal_rebar_bot(n1=2, d_b1=1.41 * inch)
    beam_example_flexure_ACI.set_longitudinal_rebar_top(n1=2, d_b1=0.75 * inch)
    node = Node(section=beam_example_flexure_ACI, forces=f)
    results = node.check_flexure()

    assert results.iloc[1]["Label"] == "B-12x24"
    assert results.iloc[1]["Comb."] == "Test_03"
    assert results.iloc[1]["Position"] == "Bottom"
    assert results.iloc[1]["As,min"] == pytest.approx(us(5.53, "cm**2", "inch**2"), rel=1e-3, abs=0.005)
    assert results.iloc[1]["As,req bot"] == pytest.approx(us(14.51, "cm**2", "inch**2"), rel=1e-3, abs=0.005)
    assert results.iloc[1]["As,req top"] == pytest.approx(us(0, "cm**2", "inch**2"), rel=1e-3, abs=0.005)
    assert results.iloc[1]["As"] == pytest.approx(us(20.15, "cm**2", "inch**2"), rel=1e-3, abs=0.005)
    assert results.iloc[1]["ØMn"] == pytest.approx(us(364.37, "kN*m", "kip*ft"), rel=1e-3, abs=0.005)


def test_check_flexure_ACI_318_19_over_reinforced_but_top_redeems(
    beam_example_flexure_ACI: RectangularBeam,
) -> None:
    """
    Cubre la rama 2 (doble armadura valida gracias al aporte del top).
    A_s_bot > A_s_max_bot pero A_s_bot <= A_s_max_bot + A_s_top·f_s'_net/f_y.
    Es el caso tipico de diseño real: la seccion sola seria sobre-armada, pero
    el aporte del acero de compresion la mantiene ductil sin necesidad de cap.

    Sobre la fixture (b=12", h=24", fc=4000psi, fy=60ksi):
      Bot: 4×#10 (5.07 in² = 32.69 cm²)  >  A_s_max_bot ≈ 29.80 cm²
      Top: 2×#6  (0.88 in² = 5.70 cm²)   → A_s_max_total ≈ 35.17 cm²
      A_s_bot (32.69) <= A_s_max_total (35.17) → rama 2 → double_reinf con A_s real.

    Compatibilidad de deformaciones escrita aparte (ACI 318-19 §22.2, con el hormigón
    desplazado descontado en el acero comprimido), d = 21.49", d' = 2.25":
      c = 7.325" ; a = 0.85·c = 6.226" ; f's = f_y (la barra de arriba plastifica)
      eps_t = 0.003·(21.49 - 7.325)/7.325 = 0.0058 ≥ 0.005 → Ø = 0.90 (Tabla 21.2.2)
      Mn = 469.19 kip·ft = 636.13 kN·m ; ØMn = 572.52 kN·m
    Sin corrida de ETABS ni spColumn todavía.

    Reference: Calcpad "ACI 318-19 Beam Flexure 03_v3 - over_reinforced_but_top_redeems.cpd";
    the strain compatibility above is the hand check of that sheet.
    """
    f = Forces(label="Test_over_but_top_redeems", M_y=400 * kip * ft)
    beam_example_flexure_ACI.set_longitudinal_rebar_bot(n1=4, d_b1=1.27 * inch)
    beam_example_flexure_ACI.set_longitudinal_rebar_top(n1=2, d_b1=0.75 * inch)
    node = Node(section=beam_example_flexure_ACI, forces=f)
    results = node.check_flexure()
    assert results.iloc[1]["Position"] == "Bottom"
    assert results.iloc[1]["Mu"] == pytest.approx(us(542.33, "kN*m", "kip*ft"), rel=1e-3, abs=0.005)
    assert results.iloc[1]["ØMn"] == pytest.approx(us(572.52, "kN*m", "kip*ft"), rel=1e-3, abs=0.005)
    # Past A_s_max, within A_s_max_eff: complies, doubly reinforced, and the
    # report's maximum is the one it is held to, not the singly reinforced one.
    min_max = beam_example_flexure_ACI._data_min_max_flexure
    assert min_max["Ok?"][2] == "✅ D.R."
    assert min_max["Max."][2] == pytest.approx(us(35.17, "cm**2", "inch**2"), abs=0.005)
    assert "not_tension_controlled" not in {w.code for w in node.warnings}


def test_shear_check_EN_1992_2004_no_rebar_1(
    beam_example_EN_1992_2004_01: RectangularBeam,
) -> None:
    """A beam with no stirrups at all under a shear V_Rd,c carries alone.

    Reference: Calcpad "EN 1992-1-1_2004 Beam Shear 01 - Metric.cpd".
    """
    f = Forces(V_z=30 * kN)
    beam_example_EN_1992_2004_01.set_longitudinal_rebar_bot(n1=4, d_b1=16 * mm)
    # The reference example has no stirrups at all, so say so: the section no
    # longer infers it from n_stirrups == 0 while still assuming the settings'
    # initial diameter for d.
    beam_example_EN_1992_2004_01.set_transverse_rebar(n_stirrups=0, d_b=0 * mm, s_l=0 * mm)
    node = Node(section=beam_example_EN_1992_2004_01, forces=f)
    results = node.check_shear()

    # Compare dictionaries with a tolerance for floating-point values, in m
    assert results.iloc[1]["Av,min"] == pytest.approx(1.6, rel=1e-3)
    assert results.iloc[1]["Av,req"] == pytest.approx(1.6, rel=1e-3)
    assert results.iloc[1]["Av"] == pytest.approx(0, rel=1e-3)
    assert results.iloc[1]["VEd,1"] == pytest.approx(30, rel=1e-3)
    assert results.iloc[1]["VEd,2"] == pytest.approx(30, rel=1e-3)
    assert beam_example_EN_1992_2004_01.shear_design.d_b.to("mm").magnitude == 0
    assert beam_example_EN_1992_2004_01._d_shear.to("cm").magnitude == pytest.approx(56.6, rel=1e-3)
    assert results.iloc[1]["VRd,c"] == pytest.approx(56.51, rel=1e-3)
    assert results.iloc[1]["VRd,s"] == pytest.approx(0, rel=1e-3)
    assert results.iloc[1]["VRd"] == pytest.approx(56.51, rel=1e-3)
    assert results.iloc[1]["VRd,max"] == pytest.approx(56.51, rel=1e-3)
    assert results.iloc[1]["DCR"] == pytest.approx(0.531, rel=1e-3)

    # Assert non-numeric values directly
    assert results.iloc[1]["VEd,1≤VRd,max"] is True
    assert results.iloc[1]["VEd,2≤VRd"] is True


def test_shear_check_ACI_318_19_1(beam_example_imperial: RectangularBeam) -> None:
    """Stirrups 1e#4/6 in under V_u = 37.727 kip, no axial load.

    Reference: Calcpad "ACI 318-19 Beam Shear 01 - Imperial.cpd".
    """
    f = Forces(V_z=37.727 * kip, N_x=0 * kip)
    beam_example_imperial.set_transverse_rebar(n_stirrups=1, d_b=0.5 * inch, s_l=6 * inch)
    node = Node(section=beam_example_imperial, forces=f)
    results = node.check_shear()

    # Compare dictionaries with a tolerance for floating-point values, in m
    assert results.iloc[1]["Av,min"] == pytest.approx(us(2.12, "cm**2/m", "inch**2/ft"), rel=1e-3, abs=0.0005)
    assert results.iloc[1]["Av,req"] == pytest.approx(us(10.0623, "cm**2/m", "inch**2/ft"), rel=1e-3, abs=0.0005)
    assert results.iloc[1]["Av"] == pytest.approx(us(16.624, "cm**2/m", "inch**2/ft"), rel=1e-3, abs=0.0005)
    assert results.iloc[1]["ØVc"] == pytest.approx(us(58.288, "kN", "kip"), rel=1e-3, abs=0.005)
    assert results.iloc[1]["ØVs"] == pytest.approx(us(180.956, "kN", "kip"), rel=1e-3, abs=0.005)
    assert results.iloc[1]["ØVn"] == pytest.approx(us(239.247, "kN", "kip"), rel=1e-3, abs=0.005)
    assert results.iloc[1]["ØVmax"] == pytest.approx(us(291.44, "kN", "kip"), rel=1e-3, abs=0.005)
    assert results.iloc[1]["DCR"] == pytest.approx(0.70144, rel=1e-3)

    # Assert non-numeric values directly
    assert results.iloc[1]["Vu≤ØVmax"] is True
    assert results.iloc[1]["Vu≤ØVn"] is True


def test_shear_check_ACI_318_19_2(beam_example_imperial: RectangularBeam) -> None:
    """Stirrups 1e#4/6 in under V_u = 37.727 kip with N_u = 20 kip.

    Reference: Calcpad "ACI 318-19 Beam Shear 01 - Imperial.cpd".
    """
    f = Forces(V_z=37.727 * kip, N_x=20 * kip)
    beam_example_imperial.set_transverse_rebar(n_stirrups=1, d_b=0.5 * inch, s_l=6 * inch)
    node = Node(section=beam_example_imperial, forces=f)
    results = node.check_shear()

    # Compare dictionaries with a tolerance for floating-point values, in m
    assert results.iloc[1]["Av,min"] == pytest.approx(us(2.12, "cm**2/m", "inch**2/ft"), rel=1e-3, abs=0.0005)
    assert results.iloc[1]["Av,req"] == pytest.approx(us(9.1803, "cm**2/m", "inch**2/ft"), rel=1e-3, abs=0.0005)
    assert results.iloc[1]["Av"] == pytest.approx(us(16.624, "cm**2/m", "inch**2/ft"), rel=1e-3, abs=0.0005)
    assert results.iloc[1]["ØVc"] == pytest.approx(us(67.888, "kN", "kip"), rel=1e-3, abs=0.005)
    assert results.iloc[1]["ØVs"] == pytest.approx(us(180.959, "kN", "kip"), rel=1e-3, abs=0.005)
    assert results.iloc[1]["ØVn"] == pytest.approx(us(248.847, "kN", "kip"), rel=1e-3, abs=0.005)
    assert results.iloc[1]["ØVmax"] == pytest.approx(us(301.041, "kN", "kip"), rel=1e-3, abs=0.005)
    assert results.iloc[1]["DCR"] == pytest.approx(0.6743, rel=1e-3)

    # Assert non-numeric values directly
    assert results.iloc[1]["Vu≤ØVmax"] is True
    assert results.iloc[1]["Vu≤ØVn"] is True


def test_shear_check_ACI_318_19_no_rebar_1(
    beam_example_imperial: RectangularBeam,
) -> None:
    """A beam with no stirrups under a shear that needs them (V_u > phi*V_c).

    Reference: Calcpad "ACI 318-19 Beam Shear 01 - Imperial.cpd", the case that needs rebar.
    """
    f = Forces(V_z=8 * kip, N_x=0 * kip)
    beam_example_imperial.set_longitudinal_rebar_bot(n1=2, d_b1=0.625 * inch)
    # The reference example has no stirrups at all, so say so: the section no
    # longer infers it from n_stirrups == 0 while still assuming the settings'
    # initial diameter for d.
    beam_example_imperial.set_transverse_rebar(n_stirrups=0, d_b=0 * mm, s_l=0 * mm)
    node = Node(section=beam_example_imperial, forces=f)
    results = node.check_shear()

    # Compare dictionaries with a tolerance for floating-point values, in m
    assert results.iloc[1]["Av,min"] == pytest.approx(us(2.12, "cm**2/m", "inch**2/ft"), rel=1e-3, abs=0.0005)
    assert results.iloc[1]["Av,req"] == pytest.approx(us(2.12, "cm**2/m", "inch**2/ft"), rel=1e-3, abs=0.0005)
    assert results.iloc[1]["Av"] == pytest.approx(us(0, "cm**2/m", "inch**2/ft"), rel=1e-3, abs=0.0005)
    assert beam_example_imperial.shear_design.d_b.to("mm").magnitude == 0
    assert beam_example_imperial._d_shear.to("cm").magnitude == pytest.approx(36.04, rel=1e-3)
    assert results.iloc[1]["ØVc"] == pytest.approx(us(35.48, "kN", "kip"), rel=1e-3, abs=0.005)
    assert results.iloc[1]["ØVs"] == pytest.approx(us(0, "kN", "kip"), rel=1e-3, abs=0.005)
    assert results.iloc[1]["ØVn"] == pytest.approx(us(35.48, "kN", "kip"), rel=1e-3, abs=0.005)
    assert results.iloc[1]["ØVmax"] == pytest.approx(us(274.96, "kN", "kip"), rel=1e-3, abs=0.005)
    assert results.iloc[1]["DCR"] == pytest.approx(1.003, rel=1e-3)

    # Assert non-numeric values directly
    assert results.iloc[1]["Vu≤ØVmax"] is True
    assert results.iloc[1]["Vu≤ØVn"] is False


def test_shear_check_ACI_318_19_no_rebar_2(
    beam_example_imperial: RectangularBeam,
) -> None:
    """A beam with no stirrups under a shear that does not need them.

    Reference: Calcpad "ACI 318-19 Beam Shear 01 - Imperial.cpd", the case that does not need rebar.
    """
    f = Forces(V_z=6 * kip, N_x=0 * kip)
    beam_example_imperial.set_longitudinal_rebar_bot(n1=2, d_b1=0.625 * inch)
    # The reference example has no stirrups at all, so say so: the section no
    # longer infers it from n_stirrups == 0 while still assuming the settings'
    # initial diameter for d.
    beam_example_imperial.set_transverse_rebar(n_stirrups=0, d_b=0 * mm, s_l=0 * mm)
    node = Node(section=beam_example_imperial, forces=f)
    results = node.check_shear()

    # Compare dictionaries with a tolerance for floating-point values, in m
    assert beam_example_imperial._d_shear.to("cm").magnitude == pytest.approx(36.04, rel=1e-3)
    assert results.iloc[1]["Av,min"] == pytest.approx(us(0, "cm**2/m", "inch**2/ft"), rel=1e-3, abs=0.0005)
    assert results.iloc[1]["Av,req"] == pytest.approx(us(0, "cm**2/m", "inch**2/ft"), rel=1e-3, abs=0.0005)
    assert results.iloc[1]["Av"] == pytest.approx(us(0, "cm**2/m", "inch**2/ft"), rel=1e-3, abs=0.0005)
    assert beam_example_imperial._k_c_min.to("MPa").magnitude == pytest.approx(0.517, rel=1e-3)
    assert results.iloc[1]["ØVc"] == pytest.approx(us(35.48, "kN", "kip"), rel=1e-3, abs=0.005)
    assert results.iloc[1]["ØVs"] == pytest.approx(us(0, "kN", "kip"), rel=1e-3, abs=0.005)
    assert results.iloc[1]["ØVn"] == pytest.approx(us(35.48, "kN", "kip"), rel=1e-3, abs=0.005)
    assert results.iloc[1]["ØVmax"] == pytest.approx(us(274.96, "kN", "kip"), rel=1e-3, abs=0.005)
    assert results.iloc[1]["DCR"] == pytest.approx(0.752, rel=1e-3)

    # Assert non-numeric values directly
    assert results.iloc[1]["Vu≤ØVmax"] is True
    assert results.iloc[1]["Vu≤ØVn"] is True


def test_shear_design_ACI_318_19(beam_example_imperial: RectangularBeam) -> None:
    """Stirrup design for the beam that needs rebar.

    Reference: Calcpad "ACI 318-19 Beam Shear 01 - Imperial.cpd", the case that needs rebar.
    """
    f = Forces(V_z=37.727 * kip, N_x=0 * kip)
    beam_example_imperial.set_longitudinal_rebar_bot(n1=2, d_b1=0.625 * inch)
    node = Node(section=beam_example_imperial, forces=f)
    results = node.design_shear()

    # Compare dictionaries with a tolerance for floating-point values, in m
    assert beam_example_imperial._d_shear.to("cm").magnitude == pytest.approx(35.08, rel=1e-3)
    assert results.iloc[1]["Av,min"] == pytest.approx(us(2.12, "cm**2/m", "inch**2/ft"), rel=1e-3, abs=0.0005)
    # Nominal required Vs = (Vu - phi*Vc)/phi = (167.82 - 58.29)/0.75 = 146.04 kN
    # (it held phi*Vs = 109.53 kN before the Table 9.7.6.2.2 fix; Av,req is unchanged).
    assert beam_example_imperial._V_s_req.to("kN").magnitude == pytest.approx(146.04, rel=1e-3)
    assert results.iloc[1]["Av,req"] == pytest.approx(us(10.06, "cm**2/m", "inch**2/ft"), rel=1e-3, abs=0.0005)
    assert results.iloc[1]["ØVc"] == pytest.approx(us(58.29, "kN", "kip"), rel=1e-3, abs=0.005)
    assert results.iloc[1]["ØVs"] == pytest.approx(us(122.15, "kN", "kip"), rel=1e-3, abs=0.005)
    assert results.iloc[1]["ØVn"] == pytest.approx(us(180.44, "kN", "kip"), rel=1e-3, abs=0.005)
    assert results.iloc[1]["ØVmax"] == pytest.approx(us(291.44, "kN", "kip"), rel=1e-3, abs=0.005)
    assert results.iloc[1]["Av"] == pytest.approx(us(11.22, "cm**2/m", "inch**2/ft"), rel=1e-3, abs=0.0005)
    assert results.iloc[1]["DCR"] == pytest.approx(0.93, rel=1e-3)

    # Assert non-numeric values directly
    assert results.iloc[1]["Vu≤ØVmax"] is True
    assert results.iloc[1]["Vu≤ØVn"] is True

    # Design result
    shear = beam_example_imperial.shear_design
    assert shear.n_stirrups == 1
    assert shear.d_b.to("mm").magnitude == pytest.approx(9.525, rel=1e-3)
    assert shear.s_l.to("cm").magnitude == pytest.approx(12.7, rel=1e-3)


def test_maximum_flexural_reinforcement_ratio_ACI_318_19_Test_Etabs_05() -> None:
    """
    Test_Etabs_05: b=16", h=30", fc=6000psi, fy=60ksi.
    Agregado: 2026-05-03

    Se testea _maximum_flexural_reinforcement_ratio_ACI_318_19 directamente.
    ρ_max determina el umbral entre sección simple y doblemente armada —
    si esta fórmula falla, todo el diseño doble puede fallar silenciosamente.

    El caso usa fc=6000 psi donde β1=0.75 (no el 0.85 default para fc≤4000 psi),
    lo que ejercita el cálculo de β1 reducido.

    Excel col S: As_max = 10.4288 in²
    → ρ_max = As_max / (b × d) = 10.4288 / (16 × 27.5) = 0.02370

    Reference: BEAM-01-Flexure-Rectangle ACI 318-19-v6.xlsm, sheet Flexion, row 31 (Test_Etabs_05), column S
    (A_s,max = 10.4288 in²) -- the workbook's own hand calculation, not an ETABS result.
    """
    from mento.codes.ACI_318_19_beam import _maximum_flexural_reinforcement_ratio_ACI_318_19

    concrete = Concrete_ACI_318_19(name="fc6000", f_c=6000 * psi)
    steel = SteelBar(name="fy60", f_y=60 * ksi)
    beam = RectangularBeam(
        label="Test_Etabs_05",
        concrete=concrete,
        steel_bar=steel,
        width=16 * inch,
        height=30 * inch,
        c_c=1.5 * inch,
    )

    rho_max = _maximum_flexural_reinforcement_ratio_ACI_318_19(beam)

    # Verificación directa contra Excel: As_max = ρ_max × b × d
    d = 27.5 * inch
    As_max = rho_max * beam.width * d
    assert As_max.to("inch**2").magnitude == pytest.approx(10.4288, rel=1e-3)
