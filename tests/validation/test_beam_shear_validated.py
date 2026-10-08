"""Beam shear checks and designs that reproduce a case validated outside mento.

Every test here is marked ``published_example`` and says in a ``Source:`` paragraph of
its docstring where its numbers come from: the Calcpad beam-shear sheets (kept outside
the repository), the EN 1992-1-1 shear calculators of eurocodeapplied.com, the
examples of CRSI's Design Guide on ACI 318 and CSI's ETABS software verification examples.
``tests/architecture/test_published_examples.py`` enforces both.
"""

import pytest
from pint import Quantity

from mento.node import Node
from mento.beam import RectangularBeam
from mento.material import Concrete_ACI_318_19, Concrete_EN_1992_2004, SteelBar
from mento.precompute import section_floats
from mento.rebar import max_stirrup_spacing_ACI_318_19
from mento.units import kip, inch, mm, kN, cm, psi, ksi, MPa
from mento.forces import Forces


@pytest.mark.published_example
def test_shear_check_EN_1992_2004_rebar_1(
    beam_example_EN_1992_2004_01: RectangularBeam,
) -> None:
    """Stirrups Ø6/25 under V_Ed = 100 kN.

    Source: eurocodeapplied.com, shear resistance of a reinforced concrete beam, EN 1992-1-1 §6.2.
    """
    f = Forces(V_z=100 * kN)
    beam_example_EN_1992_2004_01.set_transverse_rebar(n_stirrups=1, d_b=6 * mm, s_l=25 * cm)
    beam_example_EN_1992_2004_01.set_longitudinal_rebar_bot(n1=4, d_b1=16 * mm)
    node = Node(section=beam_example_EN_1992_2004_01, forces=f)
    results = node.check_shear()

    # Compare dictionaries with a tolerance for floating-point values, in m
    assert results.iloc[1]["Av,min"] == pytest.approx(1.6, rel=1e-3)
    assert results.iloc[1]["Av,req"] == pytest.approx(1.83, rel=1e-3)
    assert results.iloc[1]["Av"] == pytest.approx(2.262, rel=1e-3)
    assert results.iloc[1]["VEd,1"] == pytest.approx(100, rel=1e-3)
    assert results.iloc[1]["VEd,2"] == pytest.approx(100, rel=1e-3)
    assert results.iloc[1]["VRd,s"] == pytest.approx(123.924, rel=1e-3)
    assert results.iloc[1]["VRd"] == pytest.approx(123.924, rel=1e-3)
    assert results.iloc[1]["VRd,max"] == pytest.approx(312.811, rel=1e-3)
    assert results.iloc[1]["DCR"] == pytest.approx(0.8069, rel=1e-3)

    # Assert non-numeric values directly
    assert results.iloc[1]["VEd,1≤VRd,max"] is True
    assert results.iloc[1]["VEd,2≤VRd"] is True


@pytest.mark.published_example
def test_shear_check_EN_1992_2004_rebar_2(
    beam_example_EN_1992_2004_01: RectangularBeam,
) -> None:
    """Stirrups under V_Ed = 350 kN.

    Source: eurocodeapplied.com, shear resistance of a reinforced concrete beam, EN 1992-1-1 §6.2.
    """
    f = Forces(V_z=350 * kN)
    beam_example_EN_1992_2004_01.set_transverse_rebar(n_stirrups=1, d_b=6 * mm, s_l=25 * cm)
    beam_example_EN_1992_2004_01.set_longitudinal_rebar_bot(n1=4, d_b1=16 * mm)
    node = Node(section=beam_example_EN_1992_2004_01, forces=f)
    results = node.check_shear()

    # Compare dictionaries with a tolerance for floating-point values, in m
    assert results.iloc[1]["Av,min"] == pytest.approx(1.6, rel=1e-3)
    assert results.iloc[1]["Av,req"] == pytest.approx(7.533, rel=1e-3)
    assert results.iloc[1]["Av"] == pytest.approx(2.262, rel=1e-3)
    assert results.iloc[1]["VEd,1"] == pytest.approx(350, rel=1e-3)
    assert results.iloc[1]["VEd,2"] == pytest.approx(350, rel=1e-3)
    assert results.iloc[1]["VRd,s"] == pytest.approx(105.099, rel=1e-3)
    assert results.iloc[1]["VRd"] == pytest.approx(105.099, rel=1e-3)
    assert results.iloc[1]["VRd,max"] == pytest.approx(350, rel=1e-3)
    assert results.iloc[1]["DCR"] == pytest.approx(3.33, rel=1e-3)

    # Assert non-numeric values directly
    assert results.iloc[1]["VEd,1≤VRd,max"] is True
    assert results.iloc[1]["VEd,2≤VRd"] is False


@pytest.mark.published_example
def test_shear_check_EN_1992_2004_rebar_3(
    beam_example_EN_1992_2004_01: RectangularBeam,
) -> None:
    """Stirrups under V_Ed = 500 kN.

    Source: eurocodeapplied.com, shear resistance of a reinforced concrete beam, EN 1992-1-1 §6.2.
    """
    f = Forces(V_z=500 * kN)
    beam_example_EN_1992_2004_01.set_transverse_rebar(n_stirrups=1, d_b=6 * mm, s_l=25 * cm)
    beam_example_EN_1992_2004_01.set_longitudinal_rebar_bot(n1=4, d_b1=16 * mm)
    node = Node(section=beam_example_EN_1992_2004_01, forces=f)
    results = node.check_shear()

    # Compare dictionaries with a tolerance for floating-point values, in m
    assert results.iloc[1]["Av,min"] == pytest.approx(1.6, rel=1e-3)
    assert results.iloc[1]["Av,req"] == pytest.approx(22.817, rel=1e-3)
    assert results.iloc[1]["Av"] == pytest.approx(2.26, rel=1e-3)
    assert results.iloc[1]["VEd,1"] == pytest.approx(500, rel=1e-3)
    assert results.iloc[1]["VEd,2"] == pytest.approx(500, rel=1e-3)
    assert results.iloc[1]["VRd,s"] == pytest.approx(49.566, rel=1e-3)
    assert results.iloc[1]["VRd"] == pytest.approx(49.566, rel=1e-3)
    assert results.iloc[1]["VRd,max"] == pytest.approx(453.6, rel=1e-3)
    assert results.iloc[1]["DCR"] == pytest.approx(10.088, rel=1e-3)

    # Assert non-numeric values directly
    assert results.iloc[1]["VEd,1≤VRd,max"] is False
    assert results.iloc[1]["VEd,2≤VRd"] is False


@pytest.mark.published_example
def test_shear_check_EN_1992_2004_no_rebar_2(
    beam_example_EN_1992_2004_01: RectangularBeam,
) -> None:
    """No stirrups under V_Ed = 30 kN.

    Source: eurocodeapplied.com, shear resistance of a reinforced concrete beam, EN 1992-1-1 §6.2.
    """
    f = Forces(V_z=30 * kN)
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
    assert beam_example_EN_1992_2004_01._d_shear.to("cm").magnitude == pytest.approx(57, rel=1e-3)
    assert results.iloc[1]["VRd,c"] == pytest.approx(40.09, rel=1e-3)
    assert results.iloc[1]["VRd,s"] == pytest.approx(0, rel=1e-3)
    assert results.iloc[1]["VRd"] == pytest.approx(40.09, rel=1e-3)
    assert results.iloc[1]["DCR"] == pytest.approx(0.748, rel=1e-3)

    # Assert non-numeric values directly
    assert results.iloc[1]["VEd,1≤VRd,max"] is True
    assert results.iloc[1]["VEd,2≤VRd"] is True


@pytest.mark.published_example
def test_shear_check_EN_1992_2004_no_rebar_3(
    beam_example_EN_1992_2004_01: RectangularBeam,
) -> None:
    """No stirrups under V_Ed = 30 kN with N_Ed = 50 kN.

    Source: eurocodeapplied.com, shear resistance of a reinforced concrete beam, EN 1992-1-1 §6.2.
    """
    f = Forces(N_x=50 * kN, V_z=30 * kN)
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
    assert results.iloc[1]["VRd,c"] == pytest.approx(63.59, rel=1e-3)
    assert results.iloc[1]["VRd,s"] == pytest.approx(0, rel=1e-3)
    assert results.iloc[1]["VRd"] == pytest.approx(63.59, rel=1e-3)
    assert results.iloc[1]["DCR"] == pytest.approx(0.472, rel=1e-3)

    # Assert non-numeric values directly
    assert results.iloc[1]["VEd,1≤VRd,max"] is True
    assert results.iloc[1]["VEd,2≤VRd"] is True


@pytest.mark.published_example
def test_shear_design_EN_1992_2004_1(
    beam_example_EN_1992_2004_01: RectangularBeam,
) -> None:
    """Stirrup design under V_Ed = 30 kN.

    Source: eurocodeapplied.com, shear resistance of a reinforced concrete beam, EN 1992-1-1 §6.2.
    """
    f = Forces(N_x=0 * kN, V_z=30 * kN)
    beam_example_EN_1992_2004_01.set_longitudinal_rebar_bot(n1=4, d_b1=16 * mm)
    node = Node(section=beam_example_EN_1992_2004_01, forces=f)
    results = node.design_shear()

    # Compare dictionaries with a tolerance for floating-point values, in m
    assert results.iloc[1]["Av,min"] == pytest.approx(1.6, rel=1e-3)
    assert results.iloc[1]["Av,req"] == pytest.approx(1.6, rel=1e-3)
    assert results.iloc[1]["Av"] == pytest.approx(1.62, rel=1e-3)
    assert results.iloc[1]["VEd,1"] == pytest.approx(30, rel=1e-3)
    assert results.iloc[1]["VEd,2"] == pytest.approx(30, rel=1e-3)
    assert results.iloc[1]["VRd,s"] == pytest.approx(88.52, rel=1e-3)
    assert results.iloc[1]["VRd"] == pytest.approx(88.52, rel=1e-3)
    assert results.iloc[1]["VRd,max"] == pytest.approx(312.81, rel=1e-3)
    assert results.iloc[1]["DCR"] == pytest.approx(0.339, rel=1e-3)

    # Assert non-numeric values directly
    assert results.iloc[1]["VEd,1≤VRd,max"] is True
    assert results.iloc[1]["VEd,2≤VRd"] is True


# ---------------------------------------------------------------------------
# CRSI, "Design Guide on the ACI 318 Building Code Requirements for Structural
# Concrete" (ACI 318-19 edition), Chapter 6, §6.9 Examples. The book is kept
# outside the repository ("CRSI ACI318-19 Beam design examples.pdf").
#
# f'c = 4000 psi, Grade 60, V_u taken at d from the face of the support, and
# phi*V_c from row (a) of Table 22.5.5.1, 2*lambda*sqrt(f'c)*b_w*d, which is the
# larger of rows (a) and (b) at these rho_w and what mento reads once the
# section carries A_v,min. The book's d is h - 2.5 in.; the cover, stirrup and
# bars of each case are chosen so mento's d lands on it. mento takes the shear
# d as the lesser of the two faces, so both faces get the same bars.
#
# mento lays closed stirrups of two legs, so a three-legged (Example 6.3) or a
# single-legged (Examples 6.12 and 6.18) stirrup is not reproduced: the
# stirrups set here only put the section at or above A_v,min, so V_c comes from
# the same row as in the book, and neither A_v nor phi*V_s provided is asserted
# (the book also uses nominal bar areas, 0.20 in.² for a #4, where mento uses
# pi*d_b²/4). The tolerances are half a unit of the last digit the book prints.
# ---------------------------------------------------------------------------


def _crsi_shear_check(
    label: str,
    b: float,
    h: float,
    c_c: float,
    n_bars: int,
    d_b: float,
    n_stirrups: int,
    d_b_stirrup: float,
    s: float,
    V_u: float,
) -> RectangularBeam:
    """Check one CRSI section under V_u (kip); returns the beam with its results."""
    beam = RectangularBeam(
        label=label,
        concrete=Concrete_ACI_318_19(name="fc 4000", f_c=4000 * psi),
        steel_bar=SteelBar(name="Grade 60", f_y=60 * ksi),
        width=b * inch,
        height=h * inch,
        c_c=c_c * inch,
    )
    beam.set_longitudinal_rebar_bot(n1=n_bars, d_b1=d_b * inch)
    beam.set_longitudinal_rebar_top(n1=n_bars, d_b1=d_b * inch)
    beam.set_transverse_rebar(n_stirrups=n_stirrups, d_b=d_b_stirrup * inch, s_l=s * inch)
    Node(section=beam, forces=Forces(label=label, V_z=V_u * kip)).check_shear()
    return beam


def _crsi_demand_on_stirrups(beam: RectangularBeam) -> float:
    """V_u - phi*V_c in kip, the shear the book asks the stirrups to carry."""
    return float((beam.concrete.phi_v * beam._V_s_req).to(kip).magnitude)


def _crsi_stirrup_spacing_limits(beam: RectangularBeam) -> tuple[Quantity, Quantity]:
    """Maximum stirrup spacing along the beam and across it, Table 9.7.6.2.2."""
    sec = section_floats(beam)
    V_s_req = beam._V_s_req.to("lbf").magnitude
    s_l, s_w = max_stirrup_spacing_ACI_318_19(beam, V_s_req, sec.width * sec.d_shear)
    return s_l * inch, s_w * inch


@pytest.mark.published_example
def test_shear_check_ACI_318_19_CRSI_example_6_3() -> None:
    """Beam 28 x 24 in., d = 21.5 in., V_u = 38.9 kip: only the minimum is required.

    phi*V_c = 57.1 kip > V_u > phi*lambda*sqrt(f'c)*b_w*d = 28.6 kip, so the stirrups
    carry nothing and A_v,min/s = max(0.75*sqrt(f'c), 50)*b_w/f_yt = 0.023 in.²/in.
    governs. s_max is d/2 along the beam and d across it. The cover of 1.75 in. with
    #3 stirrups and #6 bars gives the book's d = 21.5 in.; two closed #3 stirrups
    stand in for its three legs.

    Source: CRSI, Design Guide on the ACI 318 Building Code Requirements for
    Structural Concrete, §6.9.3, Example 6.3, p. 6-69, Step 2.
    """
    beam = _crsi_shear_check("CRSI-6.3", 28, 24, 1.75, 5, 0.75, 2, 0.375, 10, 38.9)
    assert beam._d_shear.to("inch").magnitude == pytest.approx(21.5, rel=1e-9)
    assert beam._phi_V_c.to(kip).magnitude == pytest.approx(57.1, abs=0.05)
    assert _crsi_demand_on_stirrups(beam) == 0.0
    check = beam.shear_checks[0]
    assert check.A_v_min.to("inch**2/inch").magnitude == pytest.approx(0.023, abs=5e-4)
    assert check.A_v_req.to("inch**2/inch").magnitude == pytest.approx(0.023, abs=5e-4)
    s_max_l, s_max_w = _crsi_stirrup_spacing_limits(beam)
    # The book prints d/2 = 10.8 in., 21.5/2 rounded.
    assert s_max_l.to("inch").magnitude == pytest.approx(21.5 / 2, rel=1e-9)
    assert s_max_w.to("inch").magnitude == pytest.approx(21.5, abs=0.05)


@pytest.mark.published_example
def test_shear_check_ACI_318_19_CRSI_example_6_7() -> None:
    """Beam 12 x 24 in., d = 21.5 in., V_u = 59.9 kip: strength governs the stirrups.

    phi*V_c = 24.5 kip, V_u - phi*V_c = 35.4 kip < phi*4*sqrt(f'c)*b_w*d = 49.0 kip, so
    s_max = d/2. With #4 U-stirrups (2 x 0.20 in.²) the spacing that carries the
    demand is s = phi*A_v*f_yt*d/(V_u - phi*V_c) = 10.9 in. The book takes d = 21.5 in.
    from the top 4-#8 at the support; the bottom face is given the same bars so
    mento's shear d, the lesser of the two, is the same.

    Source: CRSI, Design Guide on the ACI 318 Building Code Requirements for
    Structural Concrete, §6.9.7, Example 6.7, p. 6-84, Step 2 and Comments.
    """
    beam = _crsi_shear_check("CRSI-6.7", 12, 24, 1.5, 4, 1.0, 1, 0.5, 10, 59.9)
    assert beam._d_shear.to("inch").magnitude == pytest.approx(21.5, rel=1e-9)
    assert beam._phi_V_c.to(kip).magnitude == pytest.approx(24.5, abs=0.05)
    assert _crsi_demand_on_stirrups(beam) == pytest.approx(35.4, abs=0.05)
    check = beam.shear_checks[0]
    assert check.A_v_min.to("inch**2/inch").magnitude == pytest.approx(0.010, abs=5e-4)
    # The book's #4 U-stirrup, at its nominal 2 x 0.20 in.², over the A_v/s required.
    s_req = (2 * 0.20 * inch**2) / check.A_v_req
    assert s_req.to("inch").magnitude == pytest.approx(10.9, abs=0.05)
    s_max_l, s_max_w = _crsi_stirrup_spacing_limits(beam)
    # The book prints d/2 = 10.8 in., 21.5/2 rounded.
    assert s_max_l.to("inch").magnitude == pytest.approx(21.5 / 2, rel=1e-9)
    assert s_max_w.to("inch").magnitude == pytest.approx(21.5, abs=0.05)


@pytest.mark.published_example
def test_shear_check_ACI_318_19_CRSI_example_6_12() -> None:
    """Joist 7 x 28.5 in., d = 26.0 in., V_u = 31.7 kip.

    phi*V_c = 17.3 kip, V_u - phi*V_c = 14.4 kip < phi*4*sqrt(f'c)*b_w*d = 34.6 kip, so
    s_max = d/2 = 13.0 in.; A_v,min/s = 50*b_w/f_yt = 0.0058 in.²/in. The book's
    single-leg #4 is laid here as one closed #4 stirrup.

    Source: CRSI, Design Guide on the ACI 318 Building Code Requirements for
    Structural Concrete, §6.9.12, Example 6.12, pp. 6-100 and 6-101, Step 2.
    """
    beam = _crsi_shear_check("CRSI-6.12", 7, 28.5, 1.5, 2, 1.0, 1, 0.5, 12, 31.7)
    assert beam._d_shear.to("inch").magnitude == pytest.approx(26.0, rel=1e-9)
    assert beam._phi_V_c.to(kip).magnitude == pytest.approx(17.3, abs=0.05)
    assert _crsi_demand_on_stirrups(beam) == pytest.approx(14.4, abs=0.05)
    check = beam.shear_checks[0]
    assert check.A_v_min.to("inch**2/inch").magnitude == pytest.approx(0.0058, abs=5e-5)
    s_max_l, _ = _crsi_stirrup_spacing_limits(beam)
    assert s_max_l.to("inch").magnitude == pytest.approx(13.0, abs=0.05)


@pytest.mark.published_example
def test_shear_check_ACI_318_19_CRSI_example_6_17() -> None:
    """Edge beam 30 x 28.5 in., d = 26.0 in., V_u = 106.4 kip, shear alone.

    phi*V_c = 74.0 kip, V_u - phi*V_c = 32.4 kip < phi*4*sqrt(f'c)*b_w*d = 148.0 kip, so
    s_max = d/2 = 13.0 in. along the beam and 24 in. across it (the lesser of d and
    24 in.); A_v/s = (V_u - phi*V_c)/(phi*f_yt*d) = 0.0277 in.²/in. over the
    A_v,min/s = 50*b_w/f_yt = 0.025 in.²/in. that Example 6.19 prints per leg as 0.0125.
    The torsion the book adds in Examples 6.18 and 6.19 is not part of this check.

    Source: CRSI, Design Guide on the ACI 318 Building Code Requirements for
    Structural Concrete, §6.9.17, Example 6.17, pp. 6-113 and 6-114, Steps 1 and 2;
    A_v,min from §6.9.19, Example 6.19, p. 6-120, and the spacing across the width
    from §6.9.20, Example 6.20, p. 6-124.
    """
    beam = _crsi_shear_check("CRSI-6.17", 30, 28.5, 1.5, 4, 1.0, 1, 0.5, 5, 106.4)
    assert beam._d_shear.to("inch").magnitude == pytest.approx(26.0, rel=1e-9)
    assert beam._phi_V_c.to(kip).magnitude == pytest.approx(74.0, abs=0.05)
    assert _crsi_demand_on_stirrups(beam) == pytest.approx(32.4, abs=0.05)
    check = beam.shear_checks[0]
    assert check.A_v_req.to("inch**2/inch").magnitude == pytest.approx(0.0277, abs=5e-5)
    assert check.A_v_min.to("inch**2/inch").magnitude == pytest.approx(2 * 0.0125, abs=1e-4)
    s_max_l, s_max_w = _crsi_stirrup_spacing_limits(beam)
    assert s_max_l.to("inch").magnitude == pytest.approx(13.0, abs=0.05)
    assert s_max_w.to("inch").magnitude == pytest.approx(24.0, abs=0.05)


@pytest.mark.published_example
def test_shear_check_ACI_318_19_CRSI_example_6_18() -> None:
    """The joist of Example 6.12 after the torsional redistribution: V_u = 33.1 kip at d.

    phi*V_c = 17.3 kip and V_u - phi*V_c = 15.8 kip, still under the 18.0 kip a
    single-leg #4 at d/2 provides, so the stirrups of Example 6.12 stand.

    Source: CRSI, Design Guide on the ACI 318 Building Code Requirements for
    Structural Concrete, §6.9.18, Example 6.18, p. 6-118.
    """
    beam = _crsi_shear_check("CRSI-6.18", 7, 28.5, 1.5, 2, 1.0, 1, 0.5, 12, 33.1)
    assert beam._d_shear.to("inch").magnitude == pytest.approx(26.0, rel=1e-9)
    assert beam._phi_V_c.to(kip).magnitude == pytest.approx(17.3, abs=0.05)
    assert _crsi_demand_on_stirrups(beam) == pytest.approx(15.8, abs=0.05)


# ---------------------------------------------------------------------------
# CSI Software Verification, "ACI 318-19 Example 001" and "EN 2-2004 Example
# 001" (ETABS): a simply supported singly reinforced rectangle designed for
# flexure and shear, checked by hand in the same documents. The PDFs are kept
# outside the repository.
# ---------------------------------------------------------------------------


@pytest.mark.published_example
def test_shear_check_ACI_318_19_ETABS_example_001() -> None:
    """Beam 10 x 16 in., d = 13.5 in., V_u = 37.727 kip at d from the support.

    With A_v >= A_v,min, V_c is the larger of 2*sqrt(f'c) (123.5 psi) and
    8*rho_w**(1/3)*sqrt(f'c) (93.3 psi), so phi*V_c = 12.807 kip; phi*V_max =
    phi*V_c + phi*8*sqrt(f'c)*b*d = 64.036 kip; A_v,min/s = max(0.0083, 0.0079) and
    A_v/s = (V_u - phi*V_c)/(phi*f_yt*d) = 0.041 in.²/in. Stirrup #4 and bars #8 under
    a 1.5 in. cover put d at the example's 13.5 in.; the stirrups only have to hold
    A_v,min, which selects the same row of Table 22.5.5.1.

    Source: CSI Software Verification, ETABS, "ACI 318-19 Example 001", p. 2 (Results
    Comparison) and pp. 6-7 (Hand Calculation, Shear Design, Combo1).
    """
    beam = RectangularBeam(
        label="ETABS-ACI-Ex001",
        concrete=Concrete_ACI_318_19(name="fc 4000", f_c=4000 * psi),
        steel_bar=SteelBar(name="Grade 60", f_y=60 * ksi),
        width=10 * inch,
        height=16 * inch,
        c_c=1.5 * inch,
    )
    beam.set_longitudinal_rebar_bot(n1=2, d_b1=1.0 * inch)
    beam.set_longitudinal_rebar_top(n1=2, d_b1=1.0 * inch)
    beam.set_transverse_rebar(n_stirrups=1, d_b=0.5 * inch, s_l=6 * inch)
    Node(section=beam, forces=Forces(label="Combo1", V_z=37.727 * kip)).check_shear()

    assert beam._d_shear.to("inch").magnitude == pytest.approx(13.5, rel=1e-9)
    assert beam._phi_V_c.to(kip).magnitude == pytest.approx(12.807, rel=1e-3)
    assert beam._phi_V_max.to(kip).magnitude == pytest.approx(64.036, rel=1e-3)
    check = beam.shear_checks[0]
    assert check.A_v_min.to("inch**2/inch").magnitude == pytest.approx(0.0083, abs=5e-5)
    assert check.A_v_req.to("inch**2/inch").magnitude == pytest.approx(0.041, abs=5e-4)


def _etabs_en_example_001_beam(c_c: float) -> RectangularBeam:
    return RectangularBeam(
        label="ETABS-EN-Ex001",
        concrete=Concrete_EN_1992_2004(name="C30", f_c=30 * MPa),
        steel_bar=SteelBar(name="fyk 460", f_y=460 * MPa),
        width=230 * mm,
        height=550 * mm,
        c_c=c_c * mm,
    )


@pytest.mark.published_example
def test_shear_check_EN_1992_2004_ETABS_example_001() -> None:
    """Beam 230 x 550 mm, d = 490 mm, V_Ed = 110.01 kN: stirrups with cot(theta) = 2.5.

    z = 0.9*d = 441 mm and the strut runs at its flattest, tan(theta) = 0.4, so
    A_sw/s = V_Ed/(z*f_ywd*cot(theta)) = 249.5 mm²/m over the minimum
    0.08*sqrt(f_ck)/f_yk*b = 219.1 mm²/m. V_Rd,max = 369.345 kN is the CEN Default
    value, with f_cd = 20 MPa: mento takes alpha_cc = 1.0 for shear (the UK annex
    keeps 0.85 for flexure and axial load only), while the example's UK row reads
    0.85 there too and prints 313.943 kN. A_sw/s and its minimum are the same in
    both. mento's strut at 21.8 degrees, the angle the example rounds to, puts
    V_Rd,max 0.005 % under the value of tan(theta) = 0.4 exactly.

    Source: CSI Software Verification, ETABS/SAFE, "EN 2-2004 Example 001", p. 4 (Table 3)
    and pp. 23-24 (hand calculation for CEN Default).
    """
    beam = _etabs_en_example_001_beam(c_c=40)
    beam.set_longitudinal_rebar_bot(n1=3, d_b1=20 * mm)
    beam.set_longitudinal_rebar_top(n1=2, d_b1=20 * mm)
    beam.set_transverse_rebar(n_stirrups=1, d_b=10 * mm, s_l=20 * cm)
    Node(section=beam, forces=Forces(label="Combo1", V_z=110.01 * kN)).check_shear()

    assert beam._d_shear.to("mm").magnitude == pytest.approx(490, rel=1e-9)
    check = beam.shear_checks[0]
    assert check.A_v_req.to("mm**2/m").magnitude == pytest.approx(249.5, abs=0.1)
    assert check.A_v_min.to("mm**2/m").magnitude == pytest.approx(219.1, abs=0.05)
    assert beam._V_Rd_max.to(kN).magnitude == pytest.approx(369.345, rel=1e-3)


@pytest.mark.published_example
def test_shear_check_EN_1992_2004_ETABS_example_001_no_stirrups() -> None:
    """The same beam without shear or tension reinforcement: V_Rd,c = v_min*b*d.

    The example takes rho_1 = 0 at the support, so C_Rd,c*k*(100*rho_1*f_ck)^(1/3)
    vanishes and v_min = 0.035*k^(3/2)*sqrt(f_ck) = 0.4022 MPa (k = 1.6389) gives
    V_Rd,c = 45.3 kN < V_Ed: shear reinforcement is needed. With no bars and no
    stirrups, a cover of 60 mm puts d at 490 mm.

    Source: CSI Software Verification, ETABS/SAFE, "EN 2-2004 Example 001", p. 23
    (hand calculation for CEN Default).
    """
    beam = _etabs_en_example_001_beam(c_c=60)
    beam.set_longitudinal_rebar_bot(n1=0, d_b1=0 * mm)
    beam.set_longitudinal_rebar_top(n1=0, d_b1=0 * mm)
    beam.set_transverse_rebar(n_stirrups=0, d_b=0 * mm, s_l=0 * mm)
    Node(section=beam, forces=Forces(label="Combo1", V_z=110.01 * kN)).check_shear()

    assert beam._d_shear.to("mm").magnitude == pytest.approx(490, rel=1e-9)
    assert beam._V_Rd_c.to(kN).magnitude == pytest.approx(45.3, abs=0.05)
    assert beam.shear_checks[0].DCR > 1
