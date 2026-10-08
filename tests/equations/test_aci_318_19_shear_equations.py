"""ACI 318-19 shear equations, checked against values read off the code itself.

These are the Phase 1 equation tests: each case is a hand-computable evaluation
of the printed clause, so a reader with the code open can verify a row without
running mento. Nothing here imports pint or touches a beam.
"""

import math

import pytest

from mento.codes.aci_318_19.equations import shear as eq


# ---------------------------------------------------------------------------
# lambda_s — Eq. 22.5.5.1.3
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "d_mm, expected",
    [
        # d = 250 mm is the transition: 2/(1+0.004*250) = 1, so lambda_s = 1.
        (250.0, 1.0),
        (100.0, 1.0),  # shallower than the transition -> capped, not > 1
        (500.0, math.sqrt(2 / 3)),  # 2/(1+2.0)
        (1000.0, math.sqrt(0.4)),  # 2/(1+4.0)
    ],
)
def test_size_effect_factor_si(d_mm, expected):
    assert eq.size_effect_factor(d_mm) == pytest.approx(expected, rel=1e-9)


@pytest.mark.parametrize(
    "d_in, expected",
    [
        (10.0, 1.0),  # transition, 2/(1+1)
        (4.0, 1.0),  # capped
        (20.0, math.sqrt(2 / 3)),
        (40.0, math.sqrt(0.4)),
    ],
)
def test_size_effect_factor_us(d_in, expected):
    assert eq.size_effect_factor(d_in, is_imperial=True) == pytest.approx(expected, rel=1e-9)


def test_size_effect_factor_never_exceeds_one():
    # The cap is the point of the clause: it may only reduce V_c.
    assert all(eq.size_effect_factor(d) <= 1.0 for d in range(10, 2000, 10))


# ---------------------------------------------------------------------------
# sigma_Nu — §22.5.5.1
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "N_u, A_g, f_c, expected",
    [
        (0.0, 100_000.0, 25.0, 0.0),  # no axial load
        (600_000.0, 100_000.0, 25.0, 1.0),  # 600e3/(6*100e3) = 1.0 MPa, under the cap
        (6_000_000.0, 100_000.0, 25.0, 1.25),  # would be 10 MPa; capped at 0.05*f_c
    ],
)
def test_axial_stress_influence(N_u, A_g, f_c, expected):
    assert eq.axial_stress_influence(N_u, A_g, f_c) == pytest.approx(expected, rel=1e-9)


# ---------------------------------------------------------------------------
# sqrt(f'c) for V_c — §22.5.3.1 and its exception §22.5.3.2
# ---------------------------------------------------------------------------

# f'c at which the cap starts to bite: 8.3**2 = 68.89 MPa, 100**2 = 10,000 psi.
F_C_AT_THE_CAP_SI = 8.3**2
F_C_AT_THE_CAP_US = 100.0**2


@pytest.mark.parametrize(
    "f_c, is_imperial, expected",
    [
        # Below the transition the clause changes nothing.
        (25.0, False, 5.0),
        (F_C_AT_THE_CAP_SI, False, 8.3),  # exactly at it
        (80.0, False, 8.3),  # sqrt(80) = 8.944 -> capped
        (4000.0, True, math.sqrt(4000.0)),
        (F_C_AT_THE_CAP_US, True, 100.0),
        (12_000.0, True, 100.0),  # sqrt(12000) = 109.5 -> capped
    ],
)
def test_sqrt_f_c_for_shear_is_capped_without_min_web_reinforcement(f_c, is_imperial, expected):
    # §22.5.3.1: sqrt(f'c) for V_c shall not exceed 8.3 MPa (100 psi).
    got = eq.sqrt_f_c_for_shear(f_c, has_min_rebar=False, is_imperial=is_imperial)
    assert got == pytest.approx(expected, rel=1e-12)


@pytest.mark.parametrize("f_c, is_imperial", [(80.0, False), (120.0, False), (12_000.0, True)])
def test_sqrt_f_c_for_shear_lifts_the_cap_with_min_web_reinforcement(f_c, is_imperial):
    # §22.5.3.2: a beam or joist carrying A_v,min of Table 9.6.3.4 may exceed it.
    got = eq.sqrt_f_c_for_shear(f_c, has_min_rebar=True, is_imperial=is_imperial)
    assert got == pytest.approx(math.sqrt(f_c), rel=1e-12)


def test_sqrt_f_c_for_shear_never_raises_v_c():
    # The clause may only reduce sqrt(f'c), never increase it.
    assert all(eq.sqrt_f_c_for_shear(f_c, has_min_rebar=False) <= math.sqrt(f_c) for f_c in range(17, 150))


# ---------------------------------------------------------------------------
# v_c — Table 22.5.5.1
# ---------------------------------------------------------------------------


def test_concrete_shear_stress_with_min_rebar_si():
    # f_c = 25 MPa, lambda = 1, rho_w = 0.01, sigma_Nu = 0.
    #   row (a): 0.17*sqrt(25)          = 0.85
    #   row (b): 0.66*0.01**(1/3)*sqrt(25) = 0.7109...
    # The member may take the larger.
    got = eq.concrete_shear_stress(25.0, 1.0, 0.01, 0.0, 1.0, has_min_rebar=True)
    assert got == pytest.approx(0.85, rel=1e-9)


def test_concrete_shear_stress_without_min_rebar_si():
    # Row (c): 0.66*lambda_s*lambda*rho_w**(1/3)*sqrt(f_c)
    expected = 0.66 * 1.0 * 1.0 * 0.01 ** (1 / 3) * 5.0
    got = eq.concrete_shear_stress(25.0, 1.0, 0.01, 0.0, 1.0, has_min_rebar=False)
    assert got == pytest.approx(expected, rel=1e-9)


def test_concrete_shear_stress_row_c_scales_with_size_effect():
    # Without stirrups the size effect factor is what reduces v_c in a deep
    # member; with stirrups it does not appear at all.
    without = eq.concrete_shear_stress(25.0, 1.0, 0.01, 0.0, 0.8, has_min_rebar=False)
    full = eq.concrete_shear_stress(25.0, 1.0, 0.01, 0.0, 1.0, has_min_rebar=False)
    assert without == pytest.approx(0.8 * full, rel=1e-9)

    with_rebar_small = eq.concrete_shear_stress(25.0, 1.0, 0.01, 0.0, 0.5, has_min_rebar=True)
    with_rebar_full = eq.concrete_shear_stress(25.0, 1.0, 0.01, 0.0, 1.0, has_min_rebar=True)
    assert with_rebar_small == with_rebar_full


def test_concrete_shear_stress_us():
    # f_c = 4000 psi, rho_w = 0.01: row (a) 2*sqrt(4000) = 126.49 psi governs
    # over row (b) 8*0.01**(1/3)*sqrt(4000) = 109.0 psi.
    got = eq.concrete_shear_stress(4000.0, 1.0, 0.01, 0.0, 1.0, has_min_rebar=True, is_imperial=True)
    assert got == pytest.approx(2 * math.sqrt(4000.0), rel=1e-9)


def test_concrete_shear_stress_adds_axial_term():
    base = eq.concrete_shear_stress(25.0, 1.0, 0.01, 0.0, 1.0, has_min_rebar=True)
    with_axial = eq.concrete_shear_stress(25.0, 1.0, 0.01, 0.4, 1.0, has_min_rebar=True)
    assert with_axial == pytest.approx(base + 0.4, rel=1e-9)


def test_concrete_shear_stress_row_c_uses_the_capped_root():
    """§22.5.3.1 reaches row (c): a member without A_v,min may not use sqrt(f'c) > 8.3.

    f_c = 80 MPa, lambda = lambda_s = 1, rho_w = 0.01, sigma_Nu = 0:
        0.01**(1/3)    = 0.2154435
        row (c) capped = 0.66*0.2154435*8.3       = 1.18020 MPa
        row (c) uncapped                          = 0.66*0.2154435*sqrt(80)
                                                  = 0.66*0.2154435*8.944272
                                                  = 1.27180 MPa,  7.8 % higher
    The uncapped value is what mento returned before §22.5.3.1 was applied, so
    this test fails without the change rather than merely passing more tightly.
    """
    expected = 0.66 * 0.01 ** (1 / 3) * 8.3
    got = eq.concrete_shear_stress(80.0, 1.0, 0.01, 0.0, 1.0, has_min_rebar=False)
    assert got == pytest.approx(expected, rel=1e-12)
    assert got == pytest.approx(1.18020, rel=1e-5)
    # And it is strictly below the pre-change value, not equal to it.
    assert got < 0.66 * 0.01 ** (1 / 3) * math.sqrt(80.0)


def test_concrete_shear_stress_row_c_uses_the_capped_root_us():
    # f_c = 12,000 psi: row (c) 8*0.01**(1/3)*100 = 172.35 psi, not 8*...*109.54.
    expected = 8 * 0.01 ** (1 / 3) * 100.0
    got = eq.concrete_shear_stress(12_000.0, 1.0, 0.01, 0.0, 1.0, has_min_rebar=False, is_imperial=True)
    assert got == pytest.approx(expected, rel=1e-12)
    assert got < 8 * 0.01 ** (1 / 3) * math.sqrt(12_000.0)


def test_concrete_shear_stress_rows_a_b_keep_the_full_root():
    """§22.5.3.2: with A_v,min in place the cap is lifted, so rows (a)/(b) do not move.

    f_c = 80 MPa, rho_w = 0.01:
        row (a) 0.17*sqrt(80)               = 1.52053 MPa   <- governs
        row (b) 0.66*0.2154435*sqrt(80)     = 1.27180 MPa
    """
    got = eq.concrete_shear_stress(80.0, 1.0, 0.01, 0.0, 1.0, has_min_rebar=True)
    assert got == pytest.approx(0.17 * math.sqrt(80.0), rel=1e-12)
    assert got == pytest.approx(1.52053, rel=1e-5)


def test_concrete_shear_stress_cap_does_not_touch_the_axial_term():
    # sigma_Nu is added after the root, so the cap must not scale it.
    base = eq.concrete_shear_stress(80.0, 1.0, 0.01, 0.0, 1.0, has_min_rebar=False)
    with_axial = eq.concrete_shear_stress(80.0, 1.0, 0.01, 0.4, 1.0, has_min_rebar=False)
    assert with_axial == pytest.approx(base + 0.4, rel=1e-12)


# ---------------------------------------------------------------------------
# Stress limits — §22.5.5.1.1, §22.5.1.2, §9.6.3.1
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fn, f_c, is_imperial, expected",
    [
        (eq.max_concrete_shear_stress, 25.0, False, 0.42 * 5.0),
        (eq.max_concrete_shear_stress, 4000.0, True, 5 * math.sqrt(4000.0)),
        (eq.shear_stress_capacity_increment, 25.0, False, 0.66 * 5.0),
        (eq.shear_stress_capacity_increment, 4000.0, True, 8 * math.sqrt(4000.0)),
        (eq.min_shear_reinforcement_threshold_stress, 25.0, False, 0.083 * 5.0),
        (eq.min_shear_reinforcement_threshold_stress, 4000.0, True, math.sqrt(4000.0)),
    ],
)
def test_stress_limits(fn, f_c, is_imperial, expected):
    assert fn(f_c, 1.0, is_imperial=is_imperial) == pytest.approx(expected, rel=1e-9)


def test_stress_limits_scale_with_lambda():
    # Lightweight concrete reduces every sqrt(f_c) term linearly.
    assert eq.max_concrete_shear_stress(25.0, 0.75) == pytest.approx(0.75 * eq.max_concrete_shear_stress(25.0, 1.0))


def test_max_concrete_shear_stress_is_capped_too():
    """§22.5.5.1.1 is a calculation of V_c, so §22.5.3.1 caps its root as well.

    f_c = 80 MPa, lambda = 1:
        capped   0.42*8.3          = 3.48600 MPa
        uncapped 0.42*sqrt(80)     = 0.42*8.944272 = 3.75659 MPa
    """
    capped = eq.max_concrete_shear_stress(80.0, 1.0)
    assert capped == pytest.approx(0.42 * 8.3, rel=1e-12)
    assert capped == pytest.approx(3.486, rel=1e-6)
    assert capped < 0.42 * math.sqrt(80.0)


def test_max_concrete_shear_stress_lifts_the_cap_with_min_web_reinforcement():
    # §22.5.3.2 again: the ceiling rises with the table value, not independently.
    got = eq.max_concrete_shear_stress(80.0, 1.0, has_min_rebar=True)
    assert got == pytest.approx(0.42 * math.sqrt(80.0), rel=1e-12)
    assert got == pytest.approx(3.75659, rel=1e-5)


def test_max_concrete_shear_stress_defaults_to_the_capped_reading():
    # No argument means the conservative branch: a caller that does not know
    # whether A_v,min is there gets the cap, not the exception.
    assert eq.max_concrete_shear_stress(80.0, 1.0) == eq.max_concrete_shear_stress(80.0, 1.0, has_min_rebar=False)


@pytest.mark.parametrize("f_c, is_imperial", [(25.0, False), (68.0, False), (4000.0, True), (9000.0, True)])
def test_the_cap_changes_nothing_below_the_transition(f_c, is_imperial):
    # Every ordinary strength: capped and uncapped must agree exactly, so the
    # clause cannot have shifted any of the validated examples.
    root = math.sqrt(f_c)
    assert eq.sqrt_f_c_for_shear(f_c, has_min_rebar=False, is_imperial=is_imperial) == root
    assert eq.max_concrete_shear_stress(f_c, 1.0, is_imperial=is_imperial) == pytest.approx(
        (5 if is_imperial else 0.42) * root, rel=1e-12
    )


# ---------------------------------------------------------------------------
# f_yt — §20.2.2.4
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("f_y, expected", [(280.0, 280.0), (420.0, 420.0), (500.0, 420.0), (600.0, 420.0)])
def test_max_yield_strength_for_shear_si(f_y, expected):
    assert eq.max_yield_strength_for_shear(f_y) == pytest.approx(expected)


@pytest.mark.parametrize("f_y, expected", [(40_000.0, 40_000.0), (60_000.0, 60_000.0), (75_000.0, 60_000.0)])
def test_max_yield_strength_for_shear_us(f_y, expected):
    assert eq.max_yield_strength_for_shear(f_y, is_imperial=True) == pytest.approx(expected)


# ---------------------------------------------------------------------------
# A_v,min — Table 9.6.3.4
# ---------------------------------------------------------------------------


def test_min_shear_reinforcement_ratio_floor_governs():
    # f_c = 25 MPa, f_yt = 420 MPa, b_w = 300 mm.
    #   0.062*sqrt(25)/420 = 7.381e-4   <-- sqrt term
    #   0.35/420           = 8.333e-4   <-- floor governs at low f_c
    # 8.333e-4 * 300 = 0.25 mm²/mm = 2.5 cm²/m, the familiar minimum.
    assert eq.min_shear_reinforcement_ratio(25.0, 420.0, 300.0) == pytest.approx(0.25, rel=1e-6)


def test_min_shear_reinforcement_ratio_sqrt_term_governs_at_high_fc():
    # At f_c = 64 MPa the sqrt term overtakes the floor: 0.062*8/420 = 1.181e-3.
    expected = 0.062 * 8.0 / 420.0 * 300.0
    assert eq.min_shear_reinforcement_ratio(64.0, 420.0, 300.0) == pytest.approx(expected, rel=1e-9)
    assert eq.min_shear_reinforcement_ratio(64.0, 420.0, 300.0) > eq.min_shear_reinforcement_ratio(25.0, 420.0, 300.0)


def test_min_shear_reinforcement_ratio_us():
    # f_c = 4000 psi, f_yt = 60 ksi, b_w = 12 in:
    #   0.75*sqrt(4000)/60000 = 7.906e-4 ; 50/60000 = 8.333e-4 -> floor governs
    assert eq.min_shear_reinforcement_ratio(4000.0, 60_000.0, 12.0, is_imperial=True) == pytest.approx(0.01, rel=1e-6)


def test_min_shear_reinforcement_ratio_scales_with_width():
    single = eq.min_shear_reinforcement_ratio(25.0, 420.0, 300.0)
    double = eq.min_shear_reinforcement_ratio(25.0, 420.0, 600.0)
    assert double == pytest.approx(2 * single, rel=1e-12)


# ---------------------------------------------------------------------------
# V_s — §22.5.8.5.3
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Stirrup spacing limits — Table 9.7.6.2.2
# ---------------------------------------------------------------------------


# Absolute caps (under, over the Vs threshold): ACI 318-19 in mm and in, CIRSOC 201-25 in mm.
ACI_CAPS_MM = (600.0, 300.0)
ACI_CAPS_IN = (24.0, 12.0)
CIRSOC_CAPS_MM = (400.0, 200.0)


def test_max_stirrup_spacing_below_the_threshold():
    # f_c = 25, A_cv = 300*450 = 135000 mm²:
    # threshold = 0.33*5*135000 = 222,750 N. A demand under it gets the loose
    # limits: d/2 = 225 along, d = 450 across, both under the 600 mm cap.
    s_l, s_w = eq.max_stirrup_spacing(200_000.0, 25.0, 135_000.0, 450.0, *ACI_CAPS_MM)
    assert (s_l, s_w) == pytest.approx((225.0, 450.0))


def test_max_stirrup_spacing_above_the_threshold_halves_the_limits():
    s_l, s_w = eq.max_stirrup_spacing(240_000.0, 25.0, 135_000.0, 450.0, *ACI_CAPS_MM)
    # d/4 = 112.5 along, d/2 = 225 across
    assert (s_l, s_w) == pytest.approx((112.5, 225.0))


def test_max_stirrup_spacing_threshold_is_033_not_0083():
    # Regression: the metric threshold was 0.083*sqrt(f'c)*bw*d (the SI form of
    # 1*sqrt(f'c) psi, borrowed from the Av,min check of 9.6.3.1), so it halved
    # the spacing four times too early. Vs = 100 kN sits between 56 kN (the old
    # threshold) and 222.75 kN (Table 9.7.6.2.2): it keeps the loose limits.
    s_l, s_w = eq.max_stirrup_spacing(100_000.0, 25.0, 135_000.0, 450.0, *ACI_CAPS_MM)
    assert (s_l, s_w) == pytest.approx((225.0, 450.0))


def test_max_stirrup_spacing_is_capped_for_a_deep_member():
    # d = 2000 mm: d/2 = 1000 and d = 2000 both exceed the 600 mm cap.
    s_l, s_w = eq.max_stirrup_spacing(0.0, 25.0, 135_000.0, 2000.0, *ACI_CAPS_MM)
    assert (s_l, s_w) == pytest.approx((600.0, 600.0))
    # And above the threshold the cap is 300 mm.
    s_l, s_w = eq.max_stirrup_spacing(1e9, 25.0, 135_000.0, 2000.0, *ACI_CAPS_MM)
    assert (s_l, s_w) == pytest.approx((300.0, 300.0))


def test_max_stirrup_spacing_cirsoc_caps_for_a_deep_member():
    # CIRSOC 201-25 Tabla 9.7.6.2.2 keeps 400/200 mm: the same deep member is
    # capped at 400 mm under the threshold and 200 mm over it, along and across.
    s_l, s_w = eq.max_stirrup_spacing(0.0, 25.0, 135_000.0, 2000.0, *CIRSOC_CAPS_MM)
    assert (s_l, s_w) == pytest.approx((400.0, 400.0))
    s_l, s_w = eq.max_stirrup_spacing(1e9, 25.0, 135_000.0, 2000.0, *CIRSOC_CAPS_MM)
    assert (s_l, s_w) == pytest.approx((200.0, 200.0))


def test_max_stirrup_spacing_us():
    # f_c = 4000 psi, A_cv = 12*20 = 240 in²: threshold = 4*sqrt(4000)*240 = 60,715 lb
    s_l, s_w = eq.max_stirrup_spacing(50_000.0, 4000.0, 240.0, 20.0, *ACI_CAPS_IN, is_imperial=True)
    assert (s_l, s_w) == pytest.approx((10.0, 20.0))  # d/2, d — both under the 24 in cap
    s_l, s_w = eq.max_stirrup_spacing(70_000.0, 4000.0, 240.0, 20.0, *ACI_CAPS_IN, is_imperial=True)
    assert (s_l, s_w) == pytest.approx((5.0, 10.0))  # d/4, d/2


def test_stirrup_spacing_threshold_is_the_table_expression():
    # The 150x150 CIRSOC beam: f'c = 25 MPa, bw = 1500 mm, d = 1442 mm.
    # 0.33*sqrt(25)*1500*1442 N = 3568.95 kN, exactly the expression the table prints.
    A_cv = 1500.0 * 1442.0
    assert eq.stirrup_spacing_threshold(25.0, A_cv) == 0.33 * math.sqrt(25.0) * A_cv
    assert eq.stirrup_spacing_threshold(25.0, A_cv) == pytest.approx(3_568_950.0)
    # 4*sqrt(f'c)*bw*d in psi.
    assert eq.stirrup_spacing_threshold(4000.0, 240.0, is_imperial=True) == 4 * math.sqrt(4000.0) * 240.0


def test_stirrup_spacing_threshold_takes_the_uncapped_root():
    # f'c = 80 MPa is past the 8.3 MPa ceiling §22.5.3.1 puts on sqrt(f'c) for
    # V_c; Table 9.7.6.2.2 has no such ceiling, so the plain root enters.
    assert eq.stirrup_spacing_threshold(80.0, 1000.0) == 0.33 * math.sqrt(80.0) * 1000.0
    assert eq.stirrup_spacing_threshold(80.0, 1000.0) > 0.33 * 8.3 * 1000.0


def test_stirrup_spacing_halved_at_and_past_the_threshold():
    A_cv = 135_000.0
    threshold = eq.stirrup_spacing_threshold(25.0, A_cv)
    # Exactly at the threshold: the first row, and max_stirrup_spacing agrees.
    assert eq.stirrup_spacing_halved(threshold, 25.0, A_cv) is False
    assert eq.max_stirrup_spacing(threshold, 25.0, A_cv, 450.0, *ACI_CAPS_MM) == (225.0, 450.0)
    # One ulp above: the halved row.
    above = math.nextafter(threshold, math.inf)
    assert eq.stirrup_spacing_halved(above, 25.0, A_cv) is True
    assert eq.max_stirrup_spacing(above, 25.0, A_cv, 450.0, *ACI_CAPS_MM) == (112.5, 225.0)


def test_stirrup_spacing_halved_with_a_nan_demand_takes_the_stricter_row():
    # As before the helper existed: a NaN demand is not "at or under" anything.
    assert eq.stirrup_spacing_halved(math.nan, 25.0, 135_000.0) is True
    assert eq.max_stirrup_spacing(math.nan, 25.0, 135_000.0, 450.0, *ACI_CAPS_MM) == (112.5, 225.0)


def test_shear_strength_of_reinforcement():
    # A_v/s = 0.25 mm²/mm, f_yt = 420 MPa, d = 450 mm -> 47.25 kN
    assert eq.shear_strength_of_reinforcement(0.25, 420.0, 450.0) == pytest.approx(47_250.0, rel=1e-9)


def test_shear_strength_of_reinforcement_is_linear():
    base = eq.shear_strength_of_reinforcement(0.25, 420.0, 450.0)
    assert eq.shear_strength_of_reinforcement(0.5, 420.0, 450.0) == pytest.approx(2 * base)
    assert eq.shear_strength_of_reinforcement(0.25, 420.0, 900.0) == pytest.approx(2 * base)


# ---------------------------------------------------------------------------
# Lateral support of compression reinforcement, §9.7.6.4
# ---------------------------------------------------------------------------


def test_max_stirrup_spacing_for_compression_support_takes_the_least_of_the_three():
    """ACI 318-19 / CIRSOC 201-25 §9.7.6.4.3: 16 d_b of the bar, 48 d_b of the stirrup, least dimension."""
    # Ø16 bar, Ø10 stirrup, 20x50 beam: 256, 480, 200 -> the least dimension.
    assert eq.max_stirrup_spacing_for_compression_support(16.0, 10.0, 200.0) == 200.0
    # Ø12 bar, Ø10 stirrup, 30x60: 192, 480, 300 -> 16 d_b of the bar.
    assert eq.max_stirrup_spacing_for_compression_support(12.0, 10.0, 300.0) == 192.0
    # Ø25 bar, Ø6 stirrup, 30x60: 400, 288, 300 -> 48 d_b of the stirrup.
    assert eq.max_stirrup_spacing_for_compression_support(25.0, 6.0, 300.0) == 288.0
    # In inches the same expression: No. 5 bar, No. 3 stirrup, 12x24: 10, 18, 12 -> 10 in.
    assert eq.max_stirrup_spacing_for_compression_support(0.625, 0.375, 12.0) == 10.0


@pytest.mark.parametrize(
    "d_b_long, expected",
    [(16.0, 9.5), (25.0, 9.5), (32.0, 9.5), (32.3, 9.5), (35.8, 12.7), (40.0, 12.7)],
)
def test_min_stirrup_diameter_for_compression_support_si(d_b_long, expected):
    """ACI 318-19 §9.7.6.4.2, SI: No. 10 (9.5 mm) up to a No. 32 bar (32.3 mm), No. 13 (12.7 mm) from No. 36 (35.8 mm)."""
    assert eq.min_stirrup_diameter_for_compression_support(d_b_long) == expected


@pytest.mark.parametrize("d_b_long, expected", [(0.5, 0.375), (1.0, 0.375), (1.27, 0.375), (1.41, 0.5), (2.257, 0.5)])
def test_min_stirrup_diameter_for_compression_support_us(d_b_long, expected):
    """ACI 318-19 §9.7.6.4.2, in-lb: No. 3 up to a No. 10 bar (1.27 in), No. 4 from No. 11 (1.41 in)."""
    assert eq.min_stirrup_diameter_for_compression_support(d_b_long, is_imperial=True) == expected


@pytest.mark.parametrize(
    "d_b_long, expected",
    [(12.0, 6.0), (16.0, 6.0), (20.0, 8.0), (25.0, 8.0), (32.0, 10.0), (40.0, 12.0)],
)
def test_min_stirrup_diameter_for_compression_support_cirsoc(d_b_long, expected):
    """CIRSOC 201-25 Tabla 9.7.6.4.2: 6 mm to Ø16, 8 mm to Ø25, 10 mm to Ø32, 12 mm above."""
    assert eq.min_stirrup_diameter_for_compression_support_cirsoc(d_b_long) == expected
