"""Snapshots of everything mento shows for the metric codes.

Frozen before the imperial output was added (1.4.0), so that work could prove
the metric output did not change by a single character: the DataFrames, the
detailed printouts, the Word documents, the Markdown views, the plot labels,
the warnings and the ``str`` of the public results, for ACI 318-19 in SI,
CIRSOC 201-25 and EN 1992-2004, in English and Spanish.

A snapshot that fails shows the first line that differs. When an output is
meant to change, regenerate the files and review the diff before committing::

    MENTO_UPDATE_SNAPSHOTS=1 python -m pytest tests/reports/test_display_snapshots.py
"""

from __future__ import annotations

import difflib
import os
import warnings
from pathlib import Path
from typing import Any, Callable, Dict, List

import pandas as pd
import pytest

from mento import (
    Concrete_ACI_318_19,
    Concrete_CIRSOC_201_25,
    Concrete_EN_1992_2004,
    Footing,
    Forces,
    OneWaySlab,
    RectangularBeam,
    ShearWall,
    SteelBar,
    MPa,
    cm,
    kN,
    kNm,
    m,
    mm,
)
from mento.beam_summary import BeamSummary
from mento.shear_wall_summary import ShearWallSummary
from tests.reports.display_render import (
    SNAPSHOT_DIR,
    render_beam_summary,
    render_in_languages,
    render_section,
    render_wall,
    render_wall_summary,
)

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")

UPDATE = os.environ.get("MENTO_UPDATE_SNAPSHOTS") == "1"


def _pint_neutral(text: str) -> str:
    """The rendered text with pint's product dot written one way.

    The summary tables hold Quantities, which print in the registry's ``~P``
    format, and pint 0.26 changed the dot it joins units with there from ``·``
    (U+00B7) to ``⋅`` (U+22C5): ``kN·m`` became ``kN⋅m``. That is pint's choice,
    not an output of mento's, so the snapshots read either as the older one.
    """
    return text.replace("⋅", "·")


def _concrete(code: str) -> Any:
    if code == "aci":
        return Concrete_ACI_318_19(name="H25", f_c=25 * MPa)
    if code == "cirsoc":
        return Concrete_CIRSOC_201_25(name="H25", f_c=25 * MPa)
    return Concrete_EN_1992_2004(name="C25/30", f_c=25 * MPa)


def _steel(code: str) -> SteelBar:
    return SteelBar(name="B500S", f_y=500 * MPa) if code == "en" else SteelBar(name="ADN 420", f_y=420 * MPa)


def _beam(code: str, workdir: Path) -> str:
    beam = RectangularBeam(
        label="V101", concrete=_concrete(code), steel_bar=_steel(code), width=20 * cm, height=50 * cm, c_c=25 * mm
    )
    forces = [
        Forces(label="1.2D+1.6L", M_y=120 * kNm, V_z=150 * kN),
        Forces(label="neg", M_y=-80 * kNm, V_z=90 * kN, N_x=20 * kN),
    ]
    return render_section(beam, forces, workdir)


def _beam_check(code: str, workdir: Path) -> str:
    """A beam checked as detailed by hand, short of several limits, so its warnings are frozen too."""
    beam = RectangularBeam(
        label="V102", concrete=_concrete(code), steel_bar=_steel(code), width=20 * cm, height=50 * cm, c_c=25 * mm
    )
    beam.set_longitudinal_rebar_bot(n1=2, d_b1=10 * mm, n2=5, d_b2=25 * mm)
    beam.set_longitudinal_rebar_top(n1=2, d_b1=8 * mm)
    beam.set_transverse_rebar(n_stirrups=1, d_b=6 * mm, s_l=40 * cm)
    forces = [Forces(label="u", M_y=60 * kNm, V_z=120 * kN), Forces(label="n", M_y=-60 * kNm, V_z=30 * kN)]
    return render_section(beam, forces, workdir, design=False)


def _slab(code: str, workdir: Path) -> str:
    slab = OneWaySlab(
        label="L1", concrete=_concrete(code), steel_bar=_steel(code), width=1 * m, height=20 * cm, c_c=25 * mm
    )
    forces = [Forces(label="u", M_y=40 * kNm, V_z=60 * kN), Forces(label="neg", M_y=-25 * kNm, V_z=40 * kN)]
    return render_section(slab, forces, workdir)


def _footing(code: str, workdir: Path) -> str:
    footing = Footing(
        label="Z1", concrete=_concrete(code), steel_bar=_steel(code), width=1 * m, height=50 * cm, c_c=50 * mm
    )
    return render_section(footing, [Forces(label="u", M_y=100 * kNm, V_z=150 * kN)], workdir)


def _wall(code: str, workdir: Path) -> str:
    wall = ShearWall(
        label="M1",
        concrete=_concrete(code),
        steel_bar=_steel(code),
        c_c=25 * mm,
        thickness=20 * cm,
        length=3 * m,
        height=3 * m,
    )
    return render_wall(wall, [Forces(label="E", V_z=400 * kN, N_x=200 * kN)], workdir)


def _beam_summary(code: str, workdir: Path) -> str:
    beam_list = pd.DataFrame(
        {
            "Label": ["", "V101", "V102", "V103"],
            "Comb.": ["", "ELU 1", "ELU 2", "ELU 3"],
            "b": ["cm", 20, 20, 25],
            "h": ["cm", 50, 50, 60],
            "cc": ["mm", 25, 25, 25],
            "Nx": ["kN", 0, 0, 10],
            "Vz": ["kN", 20, -50, 100],
            "My": ["kNm", 0, -35, 60],
            "ns": ["", 0, 1.0, 1.0],
            "dbs": ["mm", 0, 6, 8],
            "sl": ["cm", 0, 20, 15],
            "n1": ["", 2.0, 2, 3.0],
            "db1": ["mm", 12, 12, 16],
            "n2": ["", 1.0, 1, 0.0],
            "db2": ["mm", 10, 16, 0],
            "n3": ["", 0.0, 0.0, 2.0],
            "db3": ["mm", 0, 0, 12],
            "n4": ["", 0, 0.0, 0],
            "db4": ["mm", 0, 0, 0],
        }
    )
    return render_beam_summary(BeamSummary(_concrete(code), _steel(code), beam_list), workdir)


def _wall_summary(code: str, workdir: Path) -> str:
    wall_list = pd.DataFrame(
        {
            "Level": ["", "Level 1", "Level 1", "Level 2"],
            "Label": ["", "M1", "M1", "M2"],
            "Comb.": ["", "ELU 1", "ELU 2", "ELU 1"],
            "t": ["cm", 20, 20, 20],
            "lw": ["m", 3.0, 3.0, 2.0],
            "hw": ["m", 3.0, 3.0, 3.0],
            "cc": ["mm", 25, 25, 25],
            "Nx": ["kN", 0, -301, 55.5],
            "Vz": ["kN", 264, 152, 163],
            "My": ["kNm", -172, -234, -278],
            "dbh": ["mm", 8, 8, 0],
            "sh": ["cm", 20, 20, 0],
            "dbv": ["mm", 12, 12, 0],
            "sv": ["cm", 15, 15, 0],
        }
    )
    return render_wall_summary(ShearWallSummary(_concrete(code), _steel(code), wall_list), workdir)


CASES: Dict[str, Callable[[str, Path], str]] = {
    "beam": _beam,
    "beam_check": _beam_check,
    "slab": _slab,
    "footing": _footing,
    "wall": _wall,
    "beam_summary": _beam_summary,
    "wall_summary": _wall_summary,
}
# EN 1992-2004 has no shear-wall check.
PARAMS: List[Any] = [
    pytest.param(element, code, id=f"{element}-{code}")
    for element in CASES
    for code in ("aci", "cirsoc", "en")
    if not (element.startswith("wall") and code == "en")
]


@pytest.mark.parametrize("element, code", PARAMS)
def test_metric_output_matches_snapshot(element: str, code: str, tmp_path: Path) -> None:
    def render(language: str) -> str:
        workdir = tmp_path / language
        workdir.mkdir()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return CASES[element](code, workdir)

    for language, rendered in render_in_languages(render).items():
        text = _pint_neutral(rendered)
        path = SNAPSHOT_DIR / f"{element}_{code}_{language}.txt"
        if UPDATE or not path.exists():
            if not UPDATE:
                pytest.fail(f"Missing snapshot {path.name}; run with MENTO_UPDATE_SNAPSHOTS=1 to create it.")
            path.parent.mkdir(exist_ok=True)
            path.write_text(text, encoding="utf-8")
            continue
        expected = path.read_text(encoding="utf-8")
        if text != expected:
            diff = "\n".join(
                list(
                    difflib.unified_diff(expected.splitlines(), text.splitlines(), path.name, "now", lineterm="", n=2)
                )[:60]
            )
            pytest.fail(f"{path.name} changed:\n{diff}")
