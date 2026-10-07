import pytest
import math
from pint import Quantity

# Import all classes from your material.py and relevant units
from mento.material import (
    Material,
    Concrete,
    Concrete_ACI_318_19,
    Concrete_CIRSOC_201_25,
    Concrete_EN_1992_2004,
    Steel,
    SteelBar,
    SteelStrand,
)
from mento.units import kg, m, MPa, ksi, GPa, psi, Pa, lb, ft, kPa, mm


# Helper to check if a quantity matches another, allowing for slight float differences
def assert_quantity_equal(q1: Quantity, q2: Quantity, rtol: float = 1e-6, atol: float = 1e-9) -> None:
    """Asserts two Pint Quantities are numerically and unit-wise equal."""
    assert q1.units == q2.units, f"Units mismatch: {q1.units} vs {q2.units}"
    assert pytest.approx(q1.magnitude, rel=rtol, abs=atol) == q2.magnitude, (
        f"Magnitudes mismatch: {q1.magnitude} (actual) vs {q2.magnitude} (expected) with units {q1.units}"
    )


# --- Tests for Material (Base Class) ---


def test_material_initialization() -> None:
    """Test the basic Material class initialization."""
    mat = Material(name="Generic Material")
    assert mat.name == "Generic Material"


# --- Tests for Concrete (Base Concrete Class) ---


def test_concrete_initialization_metric_mpa() -> None:
    """Test Concrete initialization with f_c in MPa (metric)."""
    concrete = Concrete(name="H30", f_c=30 * MPa)
    assert concrete.name == "H30"  # Correctly check the name set during initialization
    assert_quantity_equal(concrete.f_c, 30 * MPa)
    assert concrete.design_code == "ACI 318-19"  # Default
    assert concrete.unit_system == "metric"
    assert_quantity_equal(concrete.density, 2500 * kg / m**3)


def test_concrete_initialization_metric_pa() -> None:
    """Test Concrete initialization with f_c in Pa (metric)."""
    concrete = Concrete(name="H25", f_c=25e6 * Pa)
    assert concrete.unit_system == "metric"
    assert_quantity_equal(concrete.density, 2500 * kg / m**3)
    assert_quantity_equal(concrete.f_c, 25e6 * Pa)  # Should convert to MPa implicitly


def test_concrete_initialization_metric_kpa() -> None:
    """Test Concrete initialization with f_c in kPa (metric)."""
    concrete = Concrete(name="H25", f_c=25000 * kPa)
    assert concrete.unit_system == "metric"
    assert_quantity_equal(concrete.density, 2500 * kg / m**3)
    assert_quantity_equal(concrete.f_c, 25000 * kPa)


def test_concrete_initialization_imperial_psi() -> None:
    """Test Concrete initialization with f_c in psi (imperial)."""
    concrete = Concrete(name="C4", f_c=4000 * psi)
    assert_quantity_equal(concrete.f_c, 4000 * psi)
    assert concrete.unit_system == "imperial"
    assert_quantity_equal(concrete.density, 155 * lb / ft**3)


def test_concrete_initialization_imperial_ksi() -> None:
    """Test Concrete initialization with f_c in ksi (imperial)."""
    concrete = Concrete(name="C4", f_c=5 * ksi)
    assert_quantity_equal(concrete.f_c, 5 * ksi)
    assert concrete.unit_system == "imperial"
    assert_quantity_equal(concrete.density, 155 * lb / ft**3)


def test_concrete_initialization_unsupported_unit() -> None:
    """Test Concrete initialization with an unsupported unit for f_c."""
    with pytest.raises(ValueError, match="Unsupported unit system for f_c"):
        Concrete(name="C25", f_c=25 * m)


def test_concrete_get_properties() -> None:
    """Test get_properties method of Concrete base class."""
    concrete = Concrete(name="C30", f_c=30 * MPa)
    props = concrete.get_properties()
    assert_quantity_equal(props["f_c"], 30 * MPa)
    assert_quantity_equal(props["density"], 2500 * kg / m**3)
    assert "design_code" not in props  # Base get_properties only includes f_c and density


# --- Tests for is_imperial ---


@pytest.mark.parametrize(
    "f_c, expected_system, expected_is_imperial",
    [
        (25 * MPa, "metric", False),
        (30 * MPa, "metric", False),
        (4000 * psi, "imperial", True),
        (4 * ksi, "imperial", True),
    ],
)
def test_is_imperial_follows_the_detected_unit_system(f_c, expected_system, expected_is_imperial) -> None:
    """The flag the design-code equations branch on must track f_c's units.

    Both coefficient sets ACI publishes are reachable only through this
    property, so an inverted comparison here would silently select the wrong
    one everywhere at once.
    """
    concrete = Concrete(name="probe", f_c=f_c)
    assert concrete.unit_system == expected_system
    assert concrete.is_imperial is expected_is_imperial


def test_is_imperial_is_the_exact_negation_of_metric() -> None:
    """unit_system has only these two values; __post_init__ rejects anything else."""
    for f_c in (25 * MPa, 4000 * psi):
        concrete = Concrete(name="probe", f_c=f_c)
        assert concrete.is_imperial == (concrete.unit_system != "metric")


# --- Tests for Concrete_ACI_318_19 ---


@pytest.fixture
def aci_metric_concrete() -> Concrete_ACI_318_19:
    """Fixture for a standard metric ACI concrete."""
    return Concrete_ACI_318_19(f_c=25 * MPa, name="C25_ACI")


@pytest.fixture
def aci_imperial_concrete() -> Concrete_ACI_318_19:
    """Fixture for a standard imperial ACI concrete."""
    return Concrete_ACI_318_19(f_c=4000 * psi, name="4ksi_ACI")


def test_aci_initialization_metric(aci_metric_concrete: Concrete_ACI_318_19) -> None:
    """Test ACI concrete initialization in metric."""
    assert aci_metric_concrete.name == "C25_ACI"
    assert_quantity_equal(aci_metric_concrete.f_c, 25 * MPa)
    assert aci_metric_concrete.design_code == "ACI 318-19"
    assert aci_metric_concrete.unit_system == "metric"
    assert_quantity_equal(aci_metric_concrete.density, 2500 * kg / m**3)

    # Expected values for 25 MPa concrete (metric)
    # E_c = (2500^1.5) * 0.043 * sqrt(25) * MPa = 125000 * 0.043 * 5 * MPa = 26875 MPa
    assert_quantity_equal(aci_metric_concrete.E_c, 26875 * MPa)
    # f_r = 0.625 * sqrt(25) * MPa = 0.625 * 5 * MPa = 3.125 MPa
    assert_quantity_equal(aci_metric_concrete.f_r, 3.125 * MPa)
    # beta_1 for 25 MPa (17 <= 25 <= 28) should be 0.85
    assert pytest.approx(aci_metric_concrete.beta_1) == 0.85
    assert pytest.approx(aci_metric_concrete.lambda_factor) == 1.0  # Normalweight
    assert pytest.approx(aci_metric_concrete.phi_v) == 0.75
    assert pytest.approx(aci_metric_concrete.phi_c) == 0.65
    assert pytest.approx(aci_metric_concrete.phi_y) == 0.90  # Note: property is phi_y but uses _phi_t


def test_aci_initialization_imperial(
    aci_imperial_concrete: Concrete_ACI_318_19,
) -> None:
    """Test ACI concrete initialization in imperial."""
    assert aci_imperial_concrete.name == "4ksi_ACI"
    assert_quantity_equal(aci_imperial_concrete.f_c, 4000 * psi)
    assert aci_imperial_concrete.design_code == "ACI 318-19"
    assert aci_imperial_concrete.unit_system == "imperial"
    assert_quantity_equal(aci_imperial_concrete.density, 155 * lb / ft**3)

    # Expected values for 4000 psi concrete (imperial)
    # E_c = (155^1.5) * 33 * sqrt(4000) * psi = 1930.5 * 33 * 63.245 * psi = 4030635.7 psi ~ 4.03e6 psi
    assert_quantity_equal(aci_imperial_concrete.E_c, (155**1.5) * 33 * math.sqrt(4000) * psi)
    # f_r = 7.5 * sqrt(4000) * psi = 7.5 * 63.245 * psi = 474.34 psi
    assert_quantity_equal(aci_imperial_concrete.f_r, 7.5 * math.sqrt(4000) * psi)
    # For beta_1, f_c must be in MPa. 4000 psi = 27.579 MPa.
    # 17 <= 27.579 <= 28, so beta_1 should be 0.85
    assert pytest.approx(aci_imperial_concrete.beta_1) == 0.85


# Test __beta_1 calculation ranges - metric
@pytest.mark.parametrize(
    "f_c_value, expected_beta_1",
    [
        (10 * MPa, 0.85),  # fc < 17 MPa → else branch (0.85)
        (17 * MPa, 0.85),  # boundary inferior de la zona plana
        (20 * MPa, 0.85),  # zona plana
        (28 * MPa, 0.85),  # boundary exacto 28 MPa
        (30 * MPa, 0.85 - 0.05 / 7 * (30 - 28)),  # 28 < fc < 55 MPa
        (40 * MPa, 0.85 - 0.05 / 7 * (40 - 28)),
        (55 * MPa, 0.65),  # fila (c): f'c >= 55, no la fórmula de la fila (b)
        (60 * MPa, 0.65),  # fc > 55 MPa → cap mínimo
        (70 * MPa, 0.65),
    ],
)
def test_aci_beta_1_metric(f_c_value: Quantity, expected_beta_1: float) -> None:
    """
    Verifica β₁ para hormigones métricos (MPa) según ACI 318-19.

    ACI 318-19 métrico: β₁ = 0.85 para fc ≤ 28 MPa,
    decrece 0.05 por cada 7 MPa sobre 28, con mínimo 0.65 (fc ≥ 55 MPa).
    Cubre todos los tramos de la fórmula: zona plana, zona descendente y cap.
    """
    concrete = Concrete_ACI_318_19(name="C_metric", f_c=f_c_value)
    assert pytest.approx(concrete.beta_1) == expected_beta_1


@pytest.mark.parametrize(
    "fc_psi, expected_beta_1",
    [
        # fc <= 4000 psi → β₁ = 0.85 (zona plana)
        (2500, 0.85),
        (3000, 0.85),
        (4000, 0.85),  # boundary exacto
        # 4000 < fc < 8000 psi → β₁ = 0.85 - 0.05/1000 * (fc - 4000)
        (5000, 0.80),
        (6000, 0.75),  # el caso que fallaba en Test_Etabs_05
        (7000, 0.70),
        (8000, 0.65),  # fila (c): f'c >= 8000 (la fila (b) también da 0,65 acá)
        # fc > 8000 psi → β₁ = 0.65 (mínimo)
        (9000, 0.65),
        (12000, 0.65),
    ],
)
def test_aci_beta_1_imperial(fc_psi: float, expected_beta_1: float) -> None:
    """
    Verifica β₁ para hormigones imperiales (psi) según ACI 318-19.
    Agregado: 2026-05-03

    ACI 318-19 imperial: β₁ = 0.85 para fc ≤ 4000 psi,
    decrece 0.05 por cada 1000 psi sobre 4000, con mínimo 0.65.
    Estos tests FALLAN con el código actual de material.py (bug β₁ imperial):
    material.py usa la fórmula métrica siempre, lo que da valores incorrectos
    para hormigones imperiales con fc > 4000 psi.
    Deben pasar una vez aplicado el fix en __beta_1.
    """
    concrete = Concrete_ACI_318_19(name=f"fc{fc_psi}", f_c=fc_psi * psi)
    assert pytest.approx(concrete.beta_1, rel=1e-3) == expected_beta_1


@pytest.mark.parametrize("concrete_cls", [Concrete_ACI_318_19, Concrete_CIRSOC_201_25])
def test_beta_1_upper_break_belongs_to_row_c(concrete_cls: type) -> None:
    """f'c exactly at the upper break reads row (c), not the row (b) formula.

    ACI 318-19 Table 22.2.2.4.3 / CIRSOC 201-25 Tabla 22.2.2.4.3 write row (b)
    for the open interval 28 < f'c < 55 and row (c) for f'c >= 55, so 55 MPa
    itself is 0.65. Evaluating row (b) there gives 0.85 - 0.05*27/7 = 0.657143,
    1.1 % high, and that error is carried straight into rho_max. Both codes
    print the same table, so both classes are checked.

    54.9 MPa pins the other side: just below the break row (b) still applies,
    so the fix must not turn into a cap that swallows the sloped row.
    """
    assert concrete_cls(name="C55", f_c=55 * MPa).beta_1 == pytest.approx(0.65)
    assert concrete_cls(name="C54_9", f_c=54.9 * MPa).beta_1 == pytest.approx(0.85 - 0.05 / 7 * (54.9 - 28))


def test_beta_1_upper_break_imperial_reads_row_c() -> None:
    """The psi table breaks at 8000 and row (c) owns that value too.

    ACI 318-19 (in-lb) Table 22.2.2.4.3: row (b) is 4000 < f'c < 8000, row (c)
    is f'c >= 8000. Row (b) evaluated at 8000 also lands on 0.65, so this pins
    the reading rather than a number, and 7999 psi keeps row (b) alive just
    below the break.
    """
    assert Concrete_ACI_318_19(name="fc8000", f_c=8000 * psi).beta_1 == pytest.approx(0.65)
    assert Concrete_ACI_318_19(name="fc7999", f_c=7999 * psi).beta_1 == pytest.approx(
        0.85 - 0.05 / 1000 * (7999 - 4000)
    )


def test_aci_get_properties(aci_metric_concrete: Concrete_ACI_318_19) -> None:
    """Test get_properties for ACI concrete."""
    props = aci_metric_concrete.get_properties()
    assert_quantity_equal(props["f_c"], aci_metric_concrete.f_c)
    assert_quantity_equal(props["density"], aci_metric_concrete.density)
    assert_quantity_equal(props["E_c"], aci_metric_concrete.E_c)
    assert_quantity_equal(props["f_r"], aci_metric_concrete.f_r)
    assert pytest.approx(props["beta_1"]) == aci_metric_concrete.beta_1
    assert pytest.approx(props["epsilon_c"]) == aci_metric_concrete._epsilon_c
    assert pytest.approx(props["lambda"]) == aci_metric_concrete.lambda_factor
    assert pytest.approx(props["phi_v"]) == aci_metric_concrete.phi_v
    assert pytest.approx(props["phi_c"]) == aci_metric_concrete.phi_c
    assert pytest.approx(props["phi_t"]) == aci_metric_concrete.phi_y  # Check the name mapping


def test_aci_str_representation(aci_metric_concrete: Concrete_ACI_318_19) -> None:
    """Test __str__ method for ACI concrete."""
    s = str(aci_metric_concrete)
    assert "Concrete Properties (C25_ACI):" in s
    assert f"  f_c: {aci_metric_concrete.f_c}" in s
    assert f"  Density: {aci_metric_concrete.density}" in s
    assert f"  E_c: {aci_metric_concrete.E_c}" in s
    assert f"  f_r: {aci_metric_concrete.f_r}" in s
    assert f"  beta_1: {aci_metric_concrete.beta_1:.3f}" in s
    assert f"  epsilon_c: {aci_metric_concrete._epsilon_c:.4f}" in s
    assert f"  λ: {aci_metric_concrete.lambda_factor:.2f}" in s
    assert f"  phi_v: {aci_metric_concrete.phi_v:.2f}" in s
    assert f"  phi_c: {aci_metric_concrete.phi_c:.2f}" in s
    assert f"  phi_t: {aci_metric_concrete.phi_y:.2f}" in s  # Using phi_y as per __str__ output


# --- Tests for Concrete_CIRSOC_201_25 ---


def test_cirsoc_initialization() -> None:
    """Test CIRSOC concrete initialization."""
    concrete = Concrete_CIRSOC_201_25(f_c=30 * MPa, name="H30_CIRSOC")
    assert concrete.name == "H30_CIRSOC"
    assert_quantity_equal(concrete.f_c, 30 * MPa)
    assert concrete.design_code == "CIRSOC 201-25"
    assert concrete.unit_system == "metric"
    assert_quantity_equal(concrete.density, 2500 * kg / m**3)
    # Verify inherited properties are calculated based on ACI logic
    assert_quantity_equal(concrete.E_c, ((2500**1.5) * 0.043 * math.sqrt(30)) * MPa)
    assert pytest.approx(concrete.beta_1) == (0.85 - 0.05 / 7 * (30 - 28))  # Should follow ACI beta_1 logic


# --- Tests for Concrete_EN_1992_2004 ---


@pytest.fixture
def en_concrete_c30() -> Concrete_EN_1992_2004:
    """Fixture for EN concrete, C30/37 class (fck=30 MPa)."""
    return Concrete_EN_1992_2004(f_c=30 * MPa, name="C30/37")


@pytest.fixture
def en_concrete_c60() -> Concrete_EN_1992_2004:
    """Fixture for EN concrete, C60/75 class (fck=60 MPa)."""
    return Concrete_EN_1992_2004(f_c=60 * MPa, name="C60/75")


def test_en_initialization_c30(en_concrete_c30: Concrete_EN_1992_2004) -> None:
    """Test EN concrete initialization for C30."""
    assert en_concrete_c30.name == "C30/37"
    assert_quantity_equal(en_concrete_c30.f_c, 30 * MPa)  # This is f_ck
    assert en_concrete_c30.design_code == "EN 1992-2004"
    assert en_concrete_c30.unit_system == "metric"
    assert_quantity_equal(en_concrete_c30.density, 2500 * kg / m**3)

    # Expected values for C30/37 (f_ck=30 MPa)
    assert_quantity_equal(en_concrete_c30.f_ck, 30 * MPa)
    assert_quantity_equal(en_concrete_c30.f_cm, 30 * MPa + 8 * MPa)  # f_ck + 8 MPa = 38 MPa
    # E_cm = 22000 * (38/10)^0.3 * MPa = 22000 * 3.8^0.3 * MPa = 22000 * 1.488 * MPa = 32736 MPa
    assert_quantity_equal(en_concrete_c30.E_cm, 22000 * (3.8) ** 0.3 * MPa)
    # f_ctm = 0.3 * (30)^(2/3) * MPa = 0.3 * 9.6548 * MPa = 2.89644 MPa
    assert_quantity_equal(en_concrete_c30.f_ctm, 0.3 * (30) ** (2 / 3) * MPa)
    assert pytest.approx(en_concrete_c30.epsilon_cu3) == 0.0035
    assert pytest.approx(en_concrete_c30.gamma_c) == 1.5
    assert pytest.approx(en_concrete_c30.alpha_cc) == 0.85  # UK National Annex, the default
    assert pytest.approx(en_concrete_c30.Lambda_factor) == 0.8  # For f_ck <= 50 MPa
    assert pytest.approx(en_concrete_c30.Eta_factor) == 1.0  # For f_ck <= 50 MPa


def test_en_initialization_c60(en_concrete_c60: Concrete_EN_1992_2004) -> None:
    """Test EN concrete initialization for C60."""
    assert_quantity_equal(en_concrete_c60.f_c, 60 * MPa)  # This is f_ck
    assert en_concrete_c60.design_code == "EN 1992-2004"

    # Expected values for C60/75 (f_ck=60 MPa)
    assert_quantity_equal(en_concrete_c60.f_ck, 60 * MPa)
    assert_quantity_equal(en_concrete_c60.f_cm, 60 * MPa + 8 * MPa)  # 68 MPa
    assert pytest.approx(en_concrete_c60.Lambda_factor) == (0.8 - (60 - 50) / 400)  # 0.8 - 10/400 = 0.775
    assert pytest.approx(en_concrete_c60.Eta_factor) == (1.0 - (60 - 50) / 200)  # 1.0 - 10/200 = 0.95


def test_en_get_properties(en_concrete_c30: Concrete_EN_1992_2004) -> None:
    """Test get_properties for EN concrete."""
    props = en_concrete_c30.get_properties()
    assert_quantity_equal(props["f_ck"], en_concrete_c30.f_ck)
    assert_quantity_equal(props["f_cm"], en_concrete_c30.f_cm)
    assert_quantity_equal(props["E_cm"], en_concrete_c30.E_cm)
    assert_quantity_equal(props["f_ctm"], en_concrete_c30.f_ctm)
    assert pytest.approx(props["epsilon_cu3"]) == en_concrete_c30.epsilon_cu3
    assert pytest.approx(props["gamma_c"]) == en_concrete_c30.gamma_c
    assert pytest.approx(props["gamma_s"]) == 1.15  # deprecated key, kept for readers of the dict
    assert_quantity_equal(props["f_cd"], en_concrete_c30.f_cd)
    assert pytest.approx(props["epsilon_c2"]) == en_concrete_c30.epsilon_c2
    assert pytest.approx(props["epsilon_cu2"]) == en_concrete_c30.epsilon_cu2
    assert pytest.approx(props["n_parabola"]) == en_concrete_c30.n_parabola
    assert pytest.approx(props["alpha_cc"]) == en_concrete_c30.alpha_cc
    assert pytest.approx(props["lambda_factor"]) == en_concrete_c30.Lambda_factor
    assert pytest.approx(props["eta_factor"]) == en_concrete_c30.Eta_factor


def test_en_str_representation(en_concrete_c30: Concrete_EN_1992_2004) -> None:
    """Test __str__ method for EN concrete."""
    s = str(en_concrete_c30)
    assert "Concrete Properties (C30/37):" in s
    assert "Design Code: EN 1992-2004" in s
    assert f"  f_c (Characteristic): {en_concrete_c30.f_ck}" in s
    assert f"  f_cm (Mean Compressive): {en_concrete_c30.f_cm}" in s
    assert f"  f_ctm (Mean Tensile): {en_concrete_c30.f_ctm}" in s
    assert f"  E_cm (Secant Modulus): {en_concrete_c30.E_cm}" in s
    assert f"  Density: {en_concrete_c30.density}" in s
    assert f"  ε_cu3: {en_concrete_c30.epsilon_cu3:.4f}" in s
    assert f"  γ_c: {en_concrete_c30.gamma_c:.2f}" in s
    assert "γ_s" not in s  # the steel's, not the concrete's
    assert f"  α_cc: {en_concrete_c30.alpha_cc:.2f}" in s
    assert f"  λ Factor: {en_concrete_c30.Lambda_factor:.2f}" in s
    assert f"  Eta Factor: {en_concrete_c30.Eta_factor:.2f}" in s


# Table 3.1 of EN 1992-1-1 prints ε_c2, ε_cu2 (‰) and n rounded per class.
@pytest.mark.parametrize(
    "f_ck, eps_c2, eps_cu2, n",
    [
        (30, 2.0, 3.5, 2.0),
        (50, 2.0, 3.5, 2.0),
        (60, 2.3, 2.9, 1.6),
        (55, 2.2, 3.1, 1.75),
        (70, 2.4, 2.7, 1.45),
        (80, 2.5, 2.6, 1.4),
        (90, 2.6, 2.6, 1.4),
    ],
)
def test_en_parabola_rectangle_parameters_match_table_3_1(f_ck: float, eps_c2: float, eps_cu2: float, n: float) -> None:
    """ε_c2, ε_cu2 and n are public and reproduce EN 1992-1-1 Table 3.1 (#184)."""
    concrete = Concrete_EN_1992_2004(name=f"C{f_ck}", f_c=f_ck * MPa)
    assert concrete.epsilon_c2 * 1e3 == pytest.approx(eps_c2, abs=0.05)
    assert concrete.epsilon_cu2 * 1e3 == pytest.approx(eps_cu2, abs=0.05)
    assert concrete.n_parabola == pytest.approx(n, abs=0.015)  # the table rounds n to 0.05
    assert concrete.epsilon_c3 * 1e3 == pytest.approx(1.75 + 0.55 * max(f_ck - 50, 0) / 40)
    assert concrete.epsilon_cu3 == concrete.epsilon_cu2


def test_en_epsilon_c1_and_cu1_match_table_3_1() -> None:
    """C30/37: ε_c1 = 0.7·38^0.31 = 2.2 ‰, ε_cu1 = 3.5 ‰; C90/105: ε_c1 = 2.8 ‰, ε_cu1 = 2.8 ‰."""
    c30 = Concrete_EN_1992_2004(name="C30", f_c=30 * MPa)
    c90 = Concrete_EN_1992_2004(name="C90", f_c=90 * MPa)
    assert c30.epsilon_c1 * 1e3 == pytest.approx(2.2, abs=0.05)
    assert c30.epsilon_cu1 * 1e3 == pytest.approx(3.5)
    assert c90.epsilon_c1 * 1e3 == pytest.approx(2.8)
    assert c90.epsilon_cu1 * 1e3 == pytest.approx(2.8, abs=0.05)


def test_en_f_cd_follows_alpha_cc() -> None:
    """f_cd = α_cc·f_ck/γ_c, with α_cc 0.85 by default and 1.0 (the recommended value) on request."""
    default = Concrete_EN_1992_2004(name="C30", f_c=30 * MPa)
    recommended = Concrete_EN_1992_2004(name="C30", f_c=30 * MPa, alpha_cc=1.0)
    assert default.alpha_cc == 0.85
    assert_quantity_equal(default.f_cd, 17.0 * MPa)
    assert recommended.alpha_cc == 1.0
    assert_quantity_equal(recommended.f_cd, 20.0 * MPa)
    assert "f_cd: 20.00 MPa" in str(recommended) or "f_cd: 20.0 MPa" in str(recommended)


@pytest.mark.parametrize("alpha_cc", [0.79, 1.01, 0.0])
def test_en_alpha_cc_outside_the_range_of_3_1_6_is_refused(alpha_cc: float) -> None:
    """§3.1.6(1) lets a country choose α_cc between 0.8 and 1.0, nothing outside."""
    with pytest.raises(ValueError, match="alpha_cc must lie between 0.8 and 1.0"):
        Concrete_EN_1992_2004(name="C30", f_c=30 * MPa, alpha_cc=alpha_cc)


def test_en_concrete_gamma_s_is_deprecated(en_concrete_c30: Concrete_EN_1992_2004) -> None:
    """γ_s moved to the steel; the concrete still answers, with a DeprecationWarning (#185)."""
    with pytest.deprecated_call(match="SteelBar.gamma_s"):
        assert en_concrete_c30.gamma_s == 1.15


# --- Tests for Steel (Base Class) ---


def test_steel_initialization() -> None:
    """Test the Steel base class initialization."""
    steel = Steel(name="Generic Steel", f_y=400 * MPa)
    assert steel.name == "Generic Steel"
    assert_quantity_equal(steel.f_y, 400 * MPa)
    assert_quantity_equal(steel.density, 7850 * kg / m**3)


def test_steel_design_values() -> None:
    """γ_s is kept on the steel, f_yd = f_y/γ_s, and ε_ud is unbounded unless given (#185)."""
    steel = SteelBar(name="B500S", f_y=500 * MPa)
    assert steel.gamma_s == 1.15
    assert_quantity_equal(steel.f_yd.to("MPa"), (500 / 1.15) * MPa)
    assert steel.epsilon_ud is None
    assert steel.epsilon_yd == pytest.approx(500 / 1.15 / 200_000)

    bounded = SteelBar(name="B500S", f_y=500 * MPa, gamma_s=1.0, epsilon_ud=0.01)
    assert_quantity_equal(bounded.f_yd.to("MPa"), 500 * MPa)
    assert bounded.epsilon_ud == 0.01
    props = bounded.get_properties()
    assert props["gamma_s"] == 1.0
    assert props["epsilon_ud"] == 0.01
    assert_quantity_equal(props["f_yd"], 500 * MPa)

    strand = SteelStrand(name="Y1860", f_y=1600 * MPa, epsilon_ud=0.02)
    assert strand.epsilon_ud == 0.02
    assert strand.epsilon_yd == pytest.approx(1600 / 1.15 / 190_000)


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"gamma_s": 0.0}, "gamma_s must be positive"),
        ({"epsilon_ud": -0.01}, "epsilon_ud must be positive"),
        ({"epsilon_ud": 0.002}, "the steel would never yield"),
    ],
)
def test_steel_design_values_are_validated(kwargs: dict, message: str) -> None:
    """A non-positive γ_s or ε_ud, or an ε_ud below the design yield strain, is refused."""
    with pytest.raises(ValueError, match=message):
        SteelBar(name="B500S", f_y=500 * MPa, **kwargs)


def test_steel_initialization_custom_density() -> None:
    """Test Steel initialization with custom density."""
    custom_density = 7500 * kg / m**3
    steel = Steel(name="Light Steel", f_y=350 * MPa, density=custom_density)
    assert_quantity_equal(steel.density, custom_density)


# --- Tests for SteelBar ---


@pytest.fixture
def steel_bar_b500s() -> SteelBar:
    """Fixture for a typical SteelBar (B500S)."""
    return SteelBar(name="B500S", f_y=500 * MPa)


@pytest.fixture
def steel_bar_grade60() -> SteelBar:
    """Fixture for a typical SteelBar (Grade 60)."""
    return SteelBar(name="Grade 60", f_y=60 * ksi)


def test_steel_bar_initialization_metric(steel_bar_b500s: SteelBar) -> None:
    """Test SteelBar initialization in metric."""
    assert steel_bar_b500s.name == "B500S"
    assert_quantity_equal(steel_bar_b500s.f_y, 500 * MPa)
    assert_quantity_equal(steel_bar_b500s.E_s, 200 * GPa)
    assert_quantity_equal(steel_bar_b500s.density, 7850 * kg / m**3)
    # epsilon_y = 500 MPa / 200 GPa = 500e6 Pa / 200e9 Pa = 0.0025 (dimensionless)
    assert_quantity_equal(
        steel_bar_b500s.epsilon_y, 0.0025 * mm / mm
    )  # Use a dimensionless unit from pint if available, or just float


def test_steel_bar_initialization_imperial(steel_bar_grade60: SteelBar) -> None:
    """Test SteelBar initialization in imperial."""
    assert steel_bar_grade60.name == "Grade 60"
    assert_quantity_equal(steel_bar_grade60.f_y, 60 * ksi)
    assert_quantity_equal(steel_bar_grade60.E_s, 200 * GPa)  # E_s is hardcoded to 200 GPa
    # Convert E_s to psi for comparison: 200 GPa = 200e9 Pa = 29007550 psi ~ 29000 ksi
    # epsilon_y = 60 ksi / 29007.55 ksi = 0.002068
    expected_epsilon_y = (60 * ksi) / (200 * GPa).to("ksi")
    assert_quantity_equal(steel_bar_grade60.epsilon_y, expected_epsilon_y)


def test_steel_bar_get_properties(steel_bar_b500s: SteelBar) -> None:
    """Test get_properties for SteelBar."""
    props = steel_bar_b500s.get_properties()
    assert_quantity_equal(props["E_s"], Quantity(steel_bar_b500s.E_s.to("GPa")))
    assert_quantity_equal(props["f_y"], Quantity(steel_bar_b500s.f_y.to("MPa")))
    assert_quantity_equal(props["epsilon_y"], steel_bar_b500s.epsilon_y)


def test_steel_bar_str_representation(steel_bar_b500s: SteelBar) -> None:
    """Test __str__ method for SteelBar."""
    s = str(steel_bar_b500s)
    assert "SteelBar Properties (B500S):" in s
    assert f"  f_y: {steel_bar_b500s.f_y.to('MPa')}" in s
    assert f"  E_s: {steel_bar_b500s.E_s.to('GPa')}" in s
    assert f"  epsilon_y: {steel_bar_b500s.epsilon_y.magnitude:.4f}" in s
    assert f"  Density: {steel_bar_b500s.density}" in s


# --- Tests for SteelStrand ---


@pytest.fixture
def steel_strand_metric() -> SteelStrand:
    """Fixture for a typical SteelStrand (metric)."""
    return SteelStrand(name="Strand_1860", f_y=1600 * MPa)


def test_steel_strand_initialization_metric(steel_strand_metric: SteelStrand) -> None:
    """Test SteelStrand initialization in metric."""
    assert steel_strand_metric.name == "Strand_1860"
    assert_quantity_equal(steel_strand_metric.f_y, 1600 * MPa)
    assert_quantity_equal(steel_strand_metric.f_u, 1860 * MPa)  # Default
    assert_quantity_equal(steel_strand_metric.E_s, 190000 * MPa)  # Default
    assert_quantity_equal(steel_strand_metric.density, 7850 * kg / m**3)
    # epsilon_y = 1600 MPa / 190000 MPa = 0.008421...
    assert_quantity_equal(steel_strand_metric.epsilon_y, (1600 / 190000) * mm / mm)
    assert_quantity_equal(steel_strand_metric.prestress_stress, 0 * MPa)  # Default


def test_steel_strand_get_properties(steel_strand_metric: SteelStrand) -> None:
    """Test get_properties for SteelStrand."""
    props = steel_strand_metric.get_properties()
    assert_quantity_equal(props["E_s"], Quantity(steel_strand_metric.E_s.to("MPa")))
    assert_quantity_equal(props["f_y"], Quantity(steel_strand_metric.f_y.to("MPa")))
    assert_quantity_equal(props["f_u"], Quantity(steel_strand_metric.f_u.to("MPa")))


def test_steel_strand_str_representation(steel_strand_metric: SteelStrand) -> None:
    """Test __str__ method for SteelStrand."""
    s = str(steel_strand_metric)
    assert "SteelStrand Properties (Strand_1860):" in s
    assert f"  f_y: {steel_strand_metric.f_y.to('MPa')}" in s
    assert f"  f_u: {steel_strand_metric.f_u.to('MPa')}" in s
    assert f"  E_s: {steel_strand_metric.E_s.to('MPa')}" in s
    assert f"  Prestress Stress: {steel_strand_metric.prestress_stress}" in s
    assert f"  Density: {steel_strand_metric.density}" in s


@pytest.mark.parametrize("f_c", [4000 * psi, 4 * ksi])
@pytest.mark.parametrize("concrete_class", [Concrete_CIRSOC_201_25, Concrete_EN_1992_2004])
def test_a_metric_only_code_refuses_us_customary_units(concrete_class: type, f_c: Quantity) -> None:
    """CIRSOC 201-25 and EN 1992-1-1 publish SI coefficients only.

    Before 1.4.0 a CIRSOC concrete in psi designed with ACI's US customary
    formulas under CIRSOC's name, and an EN one failed with a ZeroDivisionError
    deep in a check.
    """
    with pytest.raises(ValueError, match="is written in SI units"):
        concrete_class(name="C", f_c=f_c)
