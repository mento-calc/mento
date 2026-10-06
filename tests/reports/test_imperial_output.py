"""Acceptance of the US customary output (1.4.0).

A section whose concrete is given in psi or ksi is designed in US customary
units, and everything it shows must be written in them: the unit rows of the
DataFrames, the detailed printouts, the Word documents, the Markdown views, the
plot labels and the ``str`` of the results. Before 1.4.0 the beam and the slab
printed SI converted from the imperial inputs, and the wall a mix of both.

The beam, slab and wall are the ones of the issue that asked for it. Every
rendering is searched, in English and in Spanish, for an SI unit or a bar
written by its diameter, and for the US units and ASTM sizes that should be
there instead.
"""

from __future__ import annotations

import re
import warnings
from pathlib import Path
from typing import Callable, Dict, List

import pandas as pd
import pytest

from mento import (
    Concrete_ACI_318_19,
    Forces,
    Node,
    OneWaySlab,
    RectangularBeam,
    ShearWall,
    SteelBar,
    ft,
    inch,
    kip,
    ksi,
    psi,
    set_language,
)
from mento.beam_summary import BeamSummary
from mento.shear_wall_summary import ShearWallSummary
from tests.reports.display_render import (
    LANGUAGES,
    render_beam_summary,
    render_section,
    render_wall,
    render_wall_summary,
)

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")

#: SI units as a report writes them, and SI bars ("Ø19", not a symbol such as "Øv").
SI_UNITS = {"cm", "cm²", "cm²/m", "mm", "kN", "kNm", "kN·m", "MPa", "kg/m³", "m"}
SI_BAR = re.compile(r"Ø\d")
US_UNITS = ("in", "kip", "psi")


def _concrete() -> Concrete_ACI_318_19:
    return Concrete_ACI_318_19(name="4000", f_c=4000 * psi)


def _steel() -> SteelBar:
    return SteelBar(name="Gr60", f_y=60 * ksi)


def _beam() -> RectangularBeam:
    return RectangularBeam(
        label="B1", concrete=_concrete(), steel_bar=_steel(), width=12 * inch, height=24 * inch, c_c=1.5 * inch
    )


def _beam_forces() -> List[Forces]:
    return [
        Forces(label="1.2D+1.6L", M_y=120 * kip * ft, V_z=40 * kip),
        Forces(label="neg", M_y=-60 * kip * ft, V_z=30 * kip),
    ]


def _slab() -> OneWaySlab:
    return OneWaySlab(
        label="S1", concrete=_concrete(), steel_bar=_steel(), width=12 * inch, height=8 * inch, c_c=0.75 * inch
    )


def _wall() -> ShearWall:
    return ShearWall(
        label="W1",
        concrete=_concrete(),
        steel_bar=_steel(),
        c_c=1 * inch,
        thickness=8 * inch,
        length=10 * ft,
        height=10 * ft,
    )


def _beam_summary() -> BeamSummary:
    beam_list = pd.DataFrame(
        {
            "Label": ["", "B1", "B2"],
            "Comb.": ["", "U1", "U2"],
            "b": ["in", 12, 14],
            "h": ["in", 24, 24],
            "cc": ["in", 1.5, 1.5],
            "Nx": ["kip", 0, 5],
            "Vz": ["kip", 40, -30],
            "My": ["kip·ft", 120, -60],
            "ns": ["", 1, 1],
            "dbs": ["in", 0.375, 0.375],
            "sl": ["in", 8, 10],
            "n1": ["", 3, 2],
            "db1": ["in", 0.75, 0.75],
            "n2": ["", 0, 1],
            "db2": ["in", 0, 0.625],
            "n3": ["", 0, 0],
            "db3": ["in", 0, 0],
            "n4": ["", 0, 0],
            "db4": ["in", 0, 0],
        }
    )
    return BeamSummary(_concrete(), _steel(), beam_list)


def _wall_summary() -> ShearWallSummary:
    wall_list = pd.DataFrame(
        {
            "Level": ["", "Level 1", "Level 1"],
            "Label": ["", "W1", "W1"],
            "Comb.": ["", "E1", "E2"],
            "t": ["in", 8, 8],
            "lw": ["ft", 10, 10],
            "hw": ["ft", 10, 10],
            "cc": ["in", 1, 1],
            "Nx": ["kip", 80, 20],
            "Vz": ["kip", 150, 120],
            "My": ["kipft", 0, 0],
            "dbh": ["in", 0.5, 0.5],
            "sh": ["in", 12, 12],
            "dbv": ["in", 0.5, 0.5],
            "sv": ["in", 12, 12],
        }
    )
    return ShearWallSummary(_concrete(), _steel(), wall_list)


RENDERS: Dict[str, Callable[[Path], str]] = {
    "beam": lambda workdir: render_section(_beam(), _beam_forces(), workdir),
    "slab": lambda workdir: render_section(_slab(), [Forces(label="u", M_y=8 * kip * ft, V_z=4 * kip)], workdir),
    "wall": lambda workdir: render_wall(_wall(), [Forces(label="E", V_z=150 * kip, N_x=80 * kip)], workdir),
    "beam_summary": lambda workdir: render_beam_summary(_beam_summary(), workdir),
    "wall_summary": lambda workdir: render_wall_summary(_wall_summary(), workdir),
}


def _tokens(text: str) -> List[str]:
    """The words of a rendering, split on spaces and table pipes, stripped of punctuation."""
    return [token.strip(",.;:()$=") for token in re.split(r"[\s|]+", text)]


@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize("element", RENDERS)
def test_imperial_output_is_written_in_us_units(element: str, language: str, tmp_path: Path) -> None:
    set_language(language)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            text = RENDERS[element](tmp_path)
    finally:
        set_language("en")

    tokens = _tokens(text)
    si = sorted({token for token in tokens if token in SI_UNITS})
    assert not si, f"{element} ({language}) still shows SI units: {si}"
    assert not SI_BAR.findall(text), f"{element} ({language}) writes a bar by its diameter: {SI_BAR.findall(text)}"
    for unit in US_UNITS:
        assert unit in tokens, f"{element} ({language}) never shows {unit}"
    assert "#" in text


@pytest.fixture
def designed_beam() -> Node:
    node = Node(section=_beam(), forces=_beam_forces())
    node.design()
    node.check()
    return node


def test_imperial_dataframes_keep_their_shape_with_us_unit_rows(designed_beam: Node) -> None:
    flexure = designed_beam.check_flexure()
    shear = designed_beam.check_shear()

    assert list(flexure.columns) == [
        "Label",
        "Comb.",
        "Position",
        "As,min",
        "As,req top",
        "As,req bot",
        "As",
        "Mu",
        "ØMn",
        "Mu≤ØMn",
        "DCR",
    ]
    assert flexure.iloc[0]["Label"] == ""
    assert flexure.iloc[0][["As", "Mu", "ØMn"]].tolist() == ["in²", "kip·ft", "kip·ft"]
    assert shear.iloc[0]["Label"] == ""
    assert shear.iloc[0][["Av", "Vu", "ØVn"]].tolist() == ["in²/ft", "kip", "kip"]


def test_hand_checked_values_of_the_imperial_beam(designed_beam: Node) -> None:
    """12x24 in, f'c 4000 psi, Grade 60, Mu = 120 kip·ft, Vu = 40 kip.

    The bottom face is 3#6: 3 × π/4 × 0.75² = 1.325 in², which the table
    writes as 1.33 (mento computes π d²/4; ASTM A615 rounds #6 to 0.44 in²).
    Its ØMn is the 168.0 kN·m the table printed before 1.4.0, now in its own
    units: 168.0 / 1.35582 = 123.9 kip·ft. Vu is the 40 kip given, no longer
    177.928865 kN converted from it.
    """
    flexure = designed_beam.check_flexure()
    bottom = flexure[flexure["Position"] == "Bottom"].iloc[0]
    assert bottom["As"] == pytest.approx(1.33)
    assert bottom["ØMn"] == pytest.approx(123.9, abs=0.05)

    shear = designed_beam.check_shear()
    assert shear.iloc[1]["Vu"] == pytest.approx(40.0)
    assert shear.iloc[1]["Nu"] == pytest.approx(0.0)


def test_imperial_bars_are_written_by_their_astm_size(designed_beam: Node) -> None:
    beam = designed_beam.section
    assert beam._format_longitudinal_rebar_string(3, 0.75 * inch) == "3#6"  # type: ignore[attr-defined]
    assert beam._format_longitudinal_rebar_string(2, 0.75 * inch, 1, 0.625 * inch) == "2#6+1#5"  # type: ignore[attr-defined]
    assert [str(layer) for layer in beam.flexure_design.bottom.layers] == ["2#6", "1#6"]  # type: ignore[attr-defined]
    assert str(beam.shear_design) == "2 legs #3 @ 8 in · 8.625 in between legs (max 21.75 in)"  # type: ignore[attr-defined]


def test_the_stirrup_notation_follows_the_report_language(designed_beam: Node) -> None:
    beam = designed_beam.section
    set_language("es")
    try:
        assert beam.shear_design.notation() == "2 ramas #3 c/8 in · 8.625 in entre ramas (máx. 21.75 in)"  # type: ignore[attr-defined]
    finally:
        set_language("en")


def test_imperial_beam_summary_capacities_are_in_kip_ft(tmp_path: Path) -> None:
    """The capacity summary once printed ØMn in kN·m under a kip·ft heading: 168.0 for 3#6."""
    capacity = _beam_summary().check(capacity_check=True)
    assert capacity.iloc[0][["ØMn,top", "ØMn,bot", "ØVn"]].tolist() == ["kip·ft", "kip·ft", "kip"]
    assert capacity.iloc[1]["ØMn,bot"] == pytest.approx(123.9, abs=0.05)


def test_warnings_name_imperial_bars_by_their_astm_size() -> None:
    """An 8x20 in beam under 190 kip·ft is designed doubly reinforced, 2#4 + 1#4 on top.

    Its stirrups are then held to §9.7.6.4.3, 16 d_b of the #4 compression bars
    = 8 in. At 9 in the warning names those bars "#4", as the drawing does,
    where SI writes "Ø16 mm".
    """
    beam = RectangularBeam(
        label="B", concrete=_concrete(), steel_bar=_steel(), width=8 * inch, height=20 * inch, c_c=1 * inch
    )
    node = Node(section=beam, forces=[Forces(label="U", V_z=13 * kip, M_y=190 * kip * ft)])
    node.design()
    beam.set_transverse_rebar(n_stirrups=1, d_b=0.375 * inch, s_l=9 * inch)
    node.check()
    (spacing,) = [w for w in node.warnings if w.code == "stirrup_spacing_exceeds_compression_support"]
    assert "the #4 compression bars" in spacing.message
    assert not SI_BAR.search(spacing.message)
