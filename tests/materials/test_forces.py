import pytest
from pint import Quantity
from pint.facets.plain import PlainQuantity
from typing import Generator

from mento.beam import RectangularBeam
from mento.forces import Forces
from mento.material import Concrete_ACI_318_19, Concrete_EN_1992_2004, SteelBar
from mento.node import Node
from mento.units import cm, ft, kN, kNm, kip, mm, MPa


# Helper to check if a quantity matches another, allowing for slight float differences
# Option A: Explicitly allow PlainQuantity
def assert_quantity_equal(
    q1: Quantity | PlainQuantity,
    q2: Quantity | PlainQuantity,
    rtol: float = 1e-9,
    atol: float = 1e-12,
) -> None:
    """Asserts two Pint Quantities are numerically and unit-wise equal."""
    assert q1.units == q2.units, f"Units mismatch: {q1.units} (actual) vs {q2.units} (expected)"
    assert pytest.approx(q1.magnitude, rel=rtol, abs=atol) == q2.magnitude, (
        f"Magnitudes mismatch: {q1.magnitude} (actual) vs {q2.magnitude} (expected) with units {q1.units}"
    )


# --- Fixtures ---


@pytest.fixture(autouse=True)
def reset_forces_id_counter() -> Generator[None, None, None]:
    """Fixture to reset the Forces._last_id counter before each test."""
    original_last_id = Forces._last_id
    Forces._last_id = 0
    yield  # Allow the test to run
    Forces._last_id = original_last_id  # Restore if needed, though usually not critical after tests


@pytest.fixture
def default_metric_forces() -> Forces:
    """A Forces instance with default metric values."""
    return Forces()


@pytest.fixture
def custom_metric_forces() -> Forces:
    """A Forces instance with custom metric values."""
    return Forces(label="Custom Metric", N_x=100 * kN, V_z=50 * kN, M_y=200 * kNm)


@pytest.fixture
def custom_imperial_forces() -> Forces:
    """A Forces instance with custom imperial values."""
    # Note: When creating, you can use any compatible units. The class will convert for display.
    return Forces(
        label="Custom Imperial",
        N_x=20 * kip,
        V_z=10 * kip,
        M_y=150 * kNm,
        unit_system="imperial",
    )


# --- Tests for Initialization (`__init__`) ---


def test_forces_default_initialization(default_metric_forces: Forces) -> None:
    """Test Forces initialization with default values."""
    assert default_metric_forces.label is None
    assert_quantity_equal(default_metric_forces._N_x, 0 * kN)
    assert_quantity_equal(default_metric_forces._V_z, 0 * kN)
    assert_quantity_equal(default_metric_forces._M_y, 0 * kNm)
    assert default_metric_forces.unit_system == "metric"
    assert default_metric_forces.id == 1  # First instance after reset


def test_forces_custom_initialization_metric(custom_metric_forces: Forces) -> None:
    """Test Forces initialization with custom metric values."""
    assert custom_metric_forces.label == "Custom Metric"
    assert_quantity_equal(custom_metric_forces._N_x, 100 * kN)
    assert_quantity_equal(custom_metric_forces._V_z, 50 * kN)
    assert_quantity_equal(custom_metric_forces._M_y, 200 * kNm)
    assert custom_metric_forces.unit_system == "metric"
    assert custom_metric_forces.id == 1  # First instance for this test (due to reset fixture)


def test_forces_custom_initialization_imperial(custom_imperial_forces: Forces) -> None:
    """Test Forces initialization with custom imperial values."""
    assert custom_imperial_forces.label == "Custom Imperial"
    assert_quantity_equal(custom_imperial_forces._N_x, 20 * kip)
    assert_quantity_equal(custom_imperial_forces._V_z, 10 * kip)
    # 150 kNm to ft*kip: 150 kN*m * (0.224809 kip/kN) * (3.28084 ft/m) = 110.63 ft*kip approx
    assert_quantity_equal(custom_imperial_forces._M_y, 150 * kNm)  # Stored internally as kNm
    assert custom_imperial_forces.unit_system == "imperial"
    assert custom_imperial_forces.id == 1


def test_forces_id_incrementing() -> None:
    """Test that the _id increments correctly for multiple instances."""
    f1 = Forces()
    f2 = Forces()
    f3 = Forces()
    assert f1.id == 1
    assert f2.id == 2
    assert f3.id == 3
    assert Forces._last_id == 3


def test_forces_id_is_read_only(default_metric_forces: Forces) -> None:
    """Test that the 'id' property is read-only."""
    with pytest.raises(AttributeError, match="property 'id' of 'Forces' object has no setter"):
        default_metric_forces.id = 99  # type: ignore[assignment]


# --- Tests for Properties (`N_x`, `V_z`, `M_y`) ---


def test_N_x_property_metric(custom_metric_forces: Forces) -> None:
    """Test N_x property returns correct value in metric."""
    assert_quantity_equal(custom_metric_forces.N_x, 100 * kN)


def test_V_z_property_metric(custom_metric_forces: Forces) -> None:
    """Test V_z property returns correct value in metric."""
    assert_quantity_equal(custom_metric_forces.V_z, 50 * kN)


def test_M_y_property_metric(custom_metric_forces: Forces) -> None:
    """Test M_y property returns correct value in metric."""
    assert_quantity_equal(custom_metric_forces.M_y, 200 * kNm)


def test_N_x_property_imperial(custom_imperial_forces: Forces) -> None:
    """Test N_x property returns correct value in imperial."""
    # 20 kip (already kip)
    assert_quantity_equal(custom_imperial_forces.N_x, 20 * kip)


def test_V_z_property_imperial(custom_imperial_forces: Forces) -> None:
    """Test V_z property returns correct value in imperial."""
    # 10 kip (already kip)
    assert_quantity_equal(custom_imperial_forces.V_z, 10 * kip)


def test_M_y_property_imperial(custom_imperial_forces: Forces) -> None:
    """Test M_y property returns correct value in imperial."""
    # 150 kNm converted to ft*kip (110.63 ft*kip approx)
    assert_quantity_equal(custom_imperial_forces.M_y, (150 * kNm).to("ft*kip"))


# --- Tests for `get_forces()` method ---


def test_get_forces_metric(custom_metric_forces: Forces) -> None:
    """Test get_forces returns correct dictionary in metric."""
    forces_dict = custom_metric_forces.get_forces()
    assert_quantity_equal(forces_dict["N_x"], 100 * kN)
    assert_quantity_equal(forces_dict["V_z"], 50 * kN)
    assert_quantity_equal(forces_dict["M_y"], 200 * kNm)


def test_get_forces_imperial(custom_imperial_forces: Forces) -> None:
    """Test get_forces returns correct dictionary in imperial."""
    forces_dict = custom_imperial_forces.get_forces()
    assert_quantity_equal(forces_dict["N_x"], 20 * kip)
    assert_quantity_equal(forces_dict["V_z"], 10 * kip)
    assert_quantity_equal(forces_dict["M_y"], (150 * kNm).to("ft*kip"))


# --- Tests for `set_forces()` method ---


def test_set_forces_updates_values(default_metric_forces: Forces) -> None:
    """Test set_forces updates the internal force values."""
    default_metric_forces.set_forces(N_x=20 * kN, V_z=5 * kN, M_y=30 * kNm)
    assert_quantity_equal(default_metric_forces._N_x, 20 * kN)
    assert_quantity_equal(default_metric_forces._V_z, 5 * kN)
    assert_quantity_equal(default_metric_forces._M_y, 30 * kNm)


def test_set_forces_with_default_values(default_metric_forces: Forces) -> None:
    """Test set_forces with some default values to ensure they remain unchanged."""
    default_metric_forces.set_forces(N_x=20 * kN)  # Only set N_x
    assert_quantity_equal(default_metric_forces._N_x, 20 * kN)
    assert_quantity_equal(default_metric_forces._V_z, 0 * kN)  # Should remain default
    assert_quantity_equal(default_metric_forces._M_y, 0 * kNm)  # Should remain default


# --- Tests for `compare_to()` method ---


def test_compare_to_V_z_true(custom_metric_forces: Forces) -> None:
    """Test compare_to for V_z when self > other."""
    other_forces = Forces(V_z=25 * kN)
    assert custom_metric_forces.compare_to(other_forces, by="V_z") is True


def test_compare_to_V_z_false(custom_metric_forces: Forces) -> None:
    """Test compare_to for V_z when self <= other."""
    other_forces_equal = Forces(V_z=50 * kN)
    other_forces_greater = Forces(V_z=75 * kN)
    assert custom_metric_forces.compare_to(other_forces_equal, by="V_z") is False
    assert custom_metric_forces.compare_to(other_forces_greater, by="V_z") is False


def test_compare_to_N_x(custom_metric_forces: Forces) -> None:
    """Test compare_to for N_x."""
    other_forces = Forces(N_x=50 * kN)
    assert custom_metric_forces.compare_to(other_forces, by="N_x") is True
    other_forces_larger = Forces(N_x=150 * kN)
    assert custom_metric_forces.compare_to(other_forces_larger, by="N_x") is False


def test_compare_to_M_y(custom_metric_forces: Forces) -> None:
    """Test compare_to for M_y."""
    other_forces = Forces(M_y=150 * kNm)
    assert custom_metric_forces.compare_to(other_forces, by="M_y") is True
    other_forces_larger = Forces(M_y=250 * kNm)
    assert custom_metric_forces.compare_to(other_forces_larger, by="M_y") is False


def test_compare_to_different_unit_systems() -> None:
    """Comparison must account for different force units."""
    metric_force = Forces(V_z=20 * kN, unit_system="metric")
    imperial_force = Forces(V_z=5 * kip, unit_system="imperial")

    assert metric_force.compare_to(imperial_force, by="V_z") is False
    assert imperial_force.compare_to(metric_force, by="V_z") is True


def test_compare_to_invalid_attribute(custom_metric_forces: Forces) -> None:
    """Test compare_to raises ValueError for invalid attribute."""
    with pytest.raises(
        ValueError, match="Comparison attribute must be one of 'N_x', 'V_y', 'V_z', 'M_x', 'M_y', 'M_z'"
    ):
        custom_metric_forces.compare_to(Forces(), by="invalid_attr")


# --- Tests for `__str__()` method ---


def test_str_representation_metric(custom_metric_forces: Forces) -> None:
    """Test __str__ representation for metric forces."""
    s = str(custom_metric_forces)
    # The ID will depend on the order of tests due to the fixture setup, so we only check format
    assert (
        f"Force ID: {custom_metric_forces.id}, Label: Custom Metric, N_x: 100.00 kN, V_z: 50.00 kN, M_y: {custom_metric_forces.M_y:.2f~P}"
        in s
    )


def test_str_representation_imperial(custom_imperial_forces: Forces) -> None:
    """Test __str__ representation for imperial forces."""
    s = str(custom_imperial_forces)
    assert (
        f"Force ID: {custom_imperial_forces.id}, Label: Custom Imperial, N_x: 20.00 kip, V_z: 10.00 kip, M_y: {custom_imperial_forces.M_y:.2f~P}"
        in s
    )
    # M_y needs careful checking due to potential floating point and pint's default format.
    # The {custom_imperial_forces.M_y:.1f~P} format specifier ensures it's formatted as pint would do for `str()`
    # and matches the expected output including units with unicode mu for 'micro'.


def test_M_x_property_imperial() -> None:
    """Test M_x property returns ft*kip in imperial unit system (covers lines 100-103)."""
    f = Forces(label="Biaxial Imperial", V_z=10 * kip, M_x=150 * kNm, unit_system="imperial")
    result = f.M_x
    expected = (150 * kNm).to("ft*kip")
    assert result.to("ft*kip").magnitude == pytest.approx(expected.magnitude)


def test_str_with_nonzero_M_x() -> None:
    """Test __str__ includes M_x when it is non-zero (covers line 157)."""
    f = Forces(label="Biaxial", V_z=300 * kN, M_x=20 * kNm)
    s = str(f)
    assert "M_x" in s
    assert "20" in s


def test_forces_given_in_us_units_are_shown_in_them() -> None:
    """A force in kip prints in kip without being told: Forces(V_z=12 * kip) once printed 53.38 kN."""
    f = Forces(label="1.4D", V_z=12 * kip, M_y=60 * kip * ft)
    assert f.unit_system == "imperial"
    # pint writes the product dot as "·" up to 0.25 and "⋅" from 0.26.
    shown = str(f).replace("⋅", "·")
    assert shown == "Force ID: {}, Label: 1.4D, N_x: 0.00 kip, V_z: 12.00 kip, M_y: 60.00 ft·kip".format(f.id)
    assert Forces(V_z=20 * kN).unit_system == "metric"
    assert Forces().unit_system == "metric"
    assert Forces(V_z=12 * kip, unit_system="metric").V_z.to("kN").magnitude == pytest.approx(53.379, rel=1e-4)


# --- The full demand of a section (#186) ---


def test_forces_carry_the_six_components_of_a_member() -> None:
    """N_x, V_y, V_z, M_x (torsion on a member), M_y, M_z: FX..MZ of a frame model."""
    f = Forces(label="ELU", N_x=500 * kN, V_y=20 * kN, V_z=40 * kN, M_x=5 * kNm, M_y=80 * kNm, M_z=-30 * kNm)
    assert_quantity_equal(f.V_y, 20 * kN)
    assert_quantity_equal(f.M_z, -30 * kNm)
    assert list(f.get_forces()) == ["N_x", "V_y", "V_z", "M_x", "M_y", "M_z"]
    assert_quantity_equal(f.get_forces()["V_y"], 20 * kN)
    assert_quantity_equal(f.get_forces()["M_z"], -30 * kNm)
    assert f.compare_to(Forces(V_y=10 * kN), by="V_y") is True
    assert f.compare_to(Forces(M_z=0 * kNm), by="M_z") is False
    # pint writes the product dot as "·" up to 0.25 and "⋅" from 0.26.
    assert str(f).replace("⋅", "·").endswith(", M_y: 80.00 kN·m, V_y: 20.00 kN, M_x: 5.00 kN·m, M_z: -30.00 kN·m")


def test_new_components_default_to_zero_and_stay_out_of_the_printout() -> None:
    """A beam's forces read and print exactly as before the new components existed."""
    f = Forces(label="1.4D", V_z=12 * kN, M_y=60 * kNm)
    assert_quantity_equal(f.V_y, 0 * kN)
    assert_quantity_equal(f.M_z, 0 * kNm)
    assert "V_y" not in str(f) and "M_z" not in str(f) and "M_x" not in str(f)
    f.set_forces(V_y=3 * kN, M_z=4 * kNm)
    assert_quantity_equal(f.V_y, 3 * kN)
    assert_quantity_equal(f.M_z, 4 * kNm)
    assert_quantity_equal(f.V_z, 0 * kN)  # set_forces still zeroes what it is not given


def test_positional_arguments_keep_their_meaning() -> None:
    """V_y and M_z were added after unit_system, so (label, N_x, V_z, M_y, M_x) by position still works."""
    f = Forces("A", 1 * kN, 2 * kN, 3 * kNm, 4 * kNm)
    assert_quantity_equal(f.N_x, 1 * kN)
    assert_quantity_equal(f.V_z, 2 * kN)
    assert_quantity_equal(f.M_y, 3 * kNm)
    assert_quantity_equal(f.M_x, 4 * kNm)


def test_new_components_in_us_units_select_imperial_and_print_in_them() -> None:
    f = Forces(V_y=5 * kip, M_z=10 * kip * ft)
    assert f.unit_system == "imperial"
    assert_quantity_equal(f.V_y, 5 * kip)
    assert f.M_z.to("ft*kip").magnitude == pytest.approx(10)
    assert f.M_z.units == (1 * ft * kip).units


def _beam(concrete: Concrete_ACI_318_19 | Concrete_EN_1992_2004, stirrups: bool = True) -> RectangularBeam:
    beam = RectangularBeam(
        label="V",
        concrete=concrete,
        steel_bar=SteelBar(name="420", f_y=420 * MPa),
        width=20 * cm,
        height=50 * cm,
        c_c=25 * mm,
    )
    if stirrups:
        beam.set_transverse_rebar(n_stirrups=1, d_b=8 * mm, s_l=20 * cm)
    beam.set_longitudinal_rebar_bot(n1=3, d_b1=16 * mm)
    beam.set_longitudinal_rebar_top(n1=2, d_b1=12 * mm)
    return beam


@pytest.mark.parametrize(
    "concrete",
    [Concrete_ACI_318_19(name="H25", f_c=25 * MPa), Concrete_EN_1992_2004(name="C25", f_c=25 * MPa)],
    ids=["ACI 318-19", "EN 1992-1-1"],
)
def test_sign_convention_N_x_positive_is_compression(concrete: Concrete_ACI_318_19) -> None:
    """N_x > 0 is compression: it raises the concrete's shear resistance, and a tension lowers it.

    Without stirrups, so that the resistance is the concrete's (V_c, V_Rd,c), the one N_x enters.
    """
    capacities = []
    for N_x in (300 * kN, 0 * kN, -100 * kN):
        beam = _beam(concrete, stirrups=False)
        Node(section=beam, forces=[Forces(label="ELU", N_x=N_x, V_z=50 * kN)]).check_shear()
        capacity = beam.shear_checks[0].V_capacity
        assert capacity is not None
        capacities.append(capacity.to("kN").magnitude)
    compressed, plain, tensioned = capacities
    assert compressed > plain > tensioned


def test_sign_convention_M_y_positive_compresses_the_top_face() -> None:
    """M_y > 0 compresses +z, the top with z up: it is sagging and loads the bottom bars."""
    sagging = _beam(Concrete_ACI_318_19(name="H25", f_c=25 * MPa))
    Node(section=sagging, forces=[Forces(label="+", M_y=60 * kNm)]).check_flexure()
    hogging = _beam(Concrete_ACI_318_19(name="H25", f_c=25 * MPa))
    Node(section=hogging, forces=[Forces(label="-", M_y=-60 * kNm)]).check_flexure()
    assert sagging.flexure_checks[0].bottom.DCR > 0 == sagging.flexure_checks[0].top.DCR
    assert hogging.flexure_checks[0].top.DCR > 0 == hogging.flexure_checks[0].bottom.DCR


def test_docstring_states_the_sign_convention() -> None:
    """The convention a frame model is read with is written where the class is documented."""
    doc = Forces.__doc__ or ""
    for statement in ("N_x > 0", "**compression**", "M_y > 0", "+z face", "M_z > 0", "−y face", "**torsion**"):
        assert statement in doc
