"""The stirrup notation, legs first, and the description of the cage.

A beam's transverse reinforcement reads ``10 legs Ø12 mm @ 14 cm · 15.87 cm
between legs (max 20 cm)``: the legs the shear check counts, the bar and the
spacing along the member, then the spacing of the legs across the width and
the most Table 9.7.6.2.2 allows it. ``str()`` is always English;
``notation()`` and ``arrangement()`` follow :func:`mento.set_language`.

Spanish expectations are built from the catalog (``ES[...]``), as the i18n
tests do, except one test that pins the specified Spanish wording on purpose.
"""

import pandas as pd
import pytest

import mento
from mento import (
    Concrete_ACI_318_19,
    Concrete_CIRSOC_201_25,
    Concrete_EN_1992_2004,
    Forces,
    Node,
    OneWaySlab,
    RectangularBeam,
    SteelBar,
)
from mento.beam_summary import BeamSummary
from mento.design_results import (
    GRID,
    STIRRUPS,
    cage_legs,
    describe_stirrup_cage,
    format_transverse_rebar,
)
from mento.i18n import ES
from mento.units import MPa, cm, inch, kN, kNm, ksi, mm

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")


def _wide_cirsoc_beam(concrete: object = None, **kwargs: object) -> RectangularBeam:
    """The wide CIRSOC beam: 150x150 cm, c_c 30 mm, CIRSOC 201-25 H-25 unless another concrete is given."""
    return RectangularBeam(
        label="V1",
        concrete=concrete or Concrete_CIRSOC_201_25(name="H-25", f_c=25 * MPa),  # type: ignore[arg-type]
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=kwargs.get("width", 150 * cm),  # type: ignore[arg-type]
        height=150 * cm,
        c_c=30 * mm,
    )


WIDE_FORCES = [Forces(label="C1", M_y=5000 * kNm, V_z=5000 * kN)]


@pytest.fixture(scope="module")
def designed() -> RectangularBeam:
    beam = _wide_cirsoc_beam()
    Node(section=beam, forces=WIDE_FORCES).design()
    return beam


def _es_beam(n_legs: int, d_b: str, s_l: str, s_w: str, s_max_w: str | None = None) -> str:
    text = ES["{n_legs} legs Ø{d_b} @ {s_l}"].format(n_legs=n_legs, d_b=d_b, s_l=s_l)
    text += " · " + ES["{s_w} between legs"].format(s_w=s_w)
    if s_max_w is not None:
        text += " " + ES["(max {s_max_w})"].format(s_max_w=s_max_w)
    return text


# ---------------------------------------------------------------------------
# The 150x150 CIRSOC beam
# ---------------------------------------------------------------------------


def test_the_wide_cirsoc_beam_reads_legs_first_in_english(designed: RectangularBeam) -> None:
    shear = designed.shear_design
    assert str(designed.reinforcement.transverse) == "10 legs Ø12 mm @ 14 cm · 15.87 cm between legs"
    assert str(shear) == "10 legs Ø12 mm @ 14 cm · 15.87 cm between legs (max 20 cm)"
    assert [str(option) for option in shear.options] == [
        "10 legs Ø12 mm @ 14 cm · 15.87 cm between legs (max 20 cm)",
        "16 legs Ø6 mm @ 5 cm · 9.56 cm between legs (max 20 cm)",
        "10 legs Ø8 mm @ 6 cm · 15.91 cm between legs (max 20 cm)",
    ]
    assert shear.notation(compact=True) == "10 legs Ø12/14"
    assert shear.arrangement() == "perimeter stirrup + 4 inner stirrups"
    assert shear.options[1].arrangement() == "perimeter stirrup + 7 inner stirrups"


def test_the_wide_cirsoc_beam_in_spanish_is_built_from_the_catalog(designed: RectangularBeam) -> None:
    shear = designed.shear_design
    assert designed.reinforcement.transverse.notation("es") == _es_beam(10, "12 mm", "14 cm", "15.87 cm")
    assert shear.notation("es") == _es_beam(10, "12 mm", "14 cm", "15.87 cm", "20 cm")
    assert shear.options[1].notation("es") == _es_beam(16, "6 mm", "5 cm", "9.56 cm", "20 cm")
    assert shear.notation("es", compact=True) == ES["{n_legs} legs Ø{d_b}/{s_l}"].format(n_legs=10, d_b=12, s_l=14)
    assert shear.arrangement("es") == " + ".join([ES["perimeter stirrup"], ES["{n} inner stirrups"].format(n=4)])


def test_the_spanish_wording_is_pinned(designed: RectangularBeam) -> None:
    """Pinned on purpose: the Spanish wording the notation was specified with, the one test that owns how it reads."""
    shear = designed.shear_design
    assert shear.notation("es") == "10 ramas Ø12 mm c/14 cm · 15.87 cm entre ramas (máx. 20 cm)"
    assert designed.reinforcement.transverse.notation("es") == "10 ramas Ø12 mm c/14 cm · 15.87 cm entre ramas"
    assert shear.notation("es", compact=True) == "10 ramas Ø12/14"
    assert shear.arrangement("es") == "estribo perimetral + 4 interiores"


@pytest.mark.parametrize(
    "key",
    [
        "{n_legs} legs Ø{d_b} @ {s_l}",
        "{s_w} between legs",
        "(max {s_max_w})",
        "{n_legs} legs Ø{d_b}/{s_l}",
        "no stirrups",
        "single perimeter stirrup",
        "perimeter stirrup",
        "1 inner stirrup",
        "{n} inner stirrups",
        "1 crosstie",
    ],
)
def test_every_notation_key_is_translated(key: str) -> None:
    assert key in ES
    assert ES[key] != key


@pytest.mark.parametrize(
    "stirrups, expected",
    [
        (4, "8 legs Ø12 mm @ 14 cm · 20.4 cm between legs (max 20 cm)"),
        (5, "10 legs Ø12 mm @ 14 cm · 15.87 cm between legs (max 20 cm)"),
    ],
)
def test_a_checked_cage_prints_the_limit_it_is_checked_against(stirrups: int, expected: str) -> None:
    """Check mode: four stirrups put the legs 20.4 cm apart against 20 cm, and the text says both."""
    beam = _wide_cirsoc_beam()
    beam.set_longitudinal_rebar_bot(n1=2, d_b1=32 * mm, n2=10, d_b2=32 * mm)
    beam.set_longitudinal_rebar_top(n1=0, d_b1=None)
    beam.set_transverse_rebar(n_stirrups=stirrups, d_b=12 * mm, s_l=14 * cm)
    Node(section=beam, forces=WIDE_FORCES).check()
    assert str(beam.shear_design) == expected


def test_other_codes_on_the_wide_cirsoc_beam() -> None:
    aci = _wide_cirsoc_beam(Concrete_ACI_318_19(name="H25", f_c=25 * MPa))
    Node(section=aci, forces=WIDE_FORCES).design()
    assert str(aci.shear_design) == "6 legs Ø16 mm @ 15 cm · 28.48 cm between legs (max 30 cm)"
    assert aci.shear_design.arrangement() == "perimeter stirrup + 2 inner stirrups"

    en = RectangularBeam(
        label="V1",
        concrete=Concrete_EN_1992_2004(name="C25", f_c=25 * MPa),
        steel_bar=SteelBar(name="B500S", f_y=500 * MPa),
        width=150 * cm,
        height=150 * cm,
        c_c=30 * mm,
    )
    Node(section=en, forces=WIDE_FORCES).design()
    assert str(en.shear_design) == "4 legs Ø12 mm @ 12 cm · 47.6 cm between legs (max 60 cm)"


# ---------------------------------------------------------------------------
# Language
# ---------------------------------------------------------------------------


def test_str_stays_english_whatever_the_language(designed: RectangularBeam) -> None:
    mento.set_language("es")
    assert str(designed.shear_design).startswith("10 legs Ø12 mm @ 14 cm")
    assert str(designed.reinforcement) == (
        "bottom: 2Ø32 mm + 10Ø32 mm / top: no reinforcement / stirrups: 10 legs Ø12 mm @ 14 cm · 15.87 cm between legs"
    )
    # notation() and arrangement() follow the language of the moment ...
    assert designed.shear_design.notation() == _es_beam(10, "12 mm", "14 cm", "15.87 cm", "20 cm")
    assert designed.shear_design.arrangement() == designed.shear_design.arrangement("es")
    # ... unless told otherwise.
    assert designed.shear_design.notation("en") == str(designed.shear_design)
    mento.set_language("en")
    assert designed.shear_design.notation("es") == _es_beam(10, "12 mm", "14 cm", "15.87 cm", "20 cm")


def test_no_stirrups_is_translatable() -> None:
    beam = _wide_cirsoc_beam()
    beam.set_transverse_rebar(n_stirrups=0, d_b=0 * mm, s_l=0 * cm)
    transverse = beam.reinforcement.transverse
    assert str(transverse) == "no stirrups"
    assert transverse.notation("es") == ES["no stirrups"]
    assert transverse.notation("es", compact=True) == ES["no stirrups"]
    assert transverse.arrangement("en") == "no stirrups"
    assert format_transverse_rebar(STIRRUPS, 0, "", "", "", language="es") == ES["no stirrups"]


# ---------------------------------------------------------------------------
# format_transverse_rebar
# ---------------------------------------------------------------------------


def test_format_transverse_rebar_keeps_its_positional_call() -> None:
    """The 1.3.0 call still works; it is English unless asked, and the grid is unchanged."""
    assert format_transverse_rebar(STIRRUPS, 5, "12 mm", "14 cm", "15.87 cm") == (
        "10 legs Ø12 mm @ 14 cm · 15.87 cm between legs"
    )
    assert format_transverse_rebar(GRID, 8, "10 mm", "8 cm", "16 cm") == "Ø10 mm/8 cm×16 cm"
    assert format_transverse_rebar(STIRRUPS, 5, "12", "14", "15.87", s_max_w="20", separator="\n") == (
        "10 legs Ø12 @ 14\n15.87 between legs (max 20)"
    )
    assert format_transverse_rebar(STIRRUPS, 4, "12", "14", "17.85", n_legs=9) == "9 legs Ø12 @ 14 · 17.85 between legs"
    mento.set_language("es")
    assert format_transverse_rebar(STIRRUPS, 1, "8", "20", "14") == "2 legs Ø8 @ 20 · 14 between legs"
    assert format_transverse_rebar(STIRRUPS, 1, "8", "20", "14", language=None) == _es_beam(2, "8", "20", "14")


# ---------------------------------------------------------------------------
# Units and compact form
# ---------------------------------------------------------------------------


def test_the_width_spacings_read_in_the_unit_of_s_l() -> None:
    """A beam built in mm with its stirrups set in mm prints every spacing in one unit."""
    beam = _wide_cirsoc_beam(width=1500 * mm)
    beam.set_transverse_rebar(n_stirrups=5, d_b=12 * mm, s_l=140 * mm)
    assert str(beam.reinforcement.transverse) == "10 legs Ø12 mm @ 140 mm · 158.7 mm between legs"
    beam.set_transverse_rebar(n_stirrups=5, d_b=12 * mm, s_l=14 * cm)
    assert str(beam.reinforcement.transverse) == "10 legs Ø12 mm @ 14 cm · 15.87 cm between legs"


def test_the_compact_form_on_imperial_and_grid_sections() -> None:
    imperial = RectangularBeam(
        label="I",
        concrete=Concrete_ACI_318_19(name="C4", f_c=4 * ksi),
        steel_bar=SteelBar(name="G60", f_y=60 * ksi),
        width=12 * inch,
        height=24 * inch,
        c_c=1.5 * inch,
    )
    imperial.set_transverse_rebar(n_stirrups=1, d_b=0.375 * inch, s_l=6 * inch)
    assert imperial.reinforcement.transverse.notation(compact=True) == "2 legs #3@6"

    slab = OneWaySlab(
        label="S",
        concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=100 * cm,
        height=25 * cm,
        c_c=25 * mm,
    )
    slab.set_slab_transverse_rebar(d_b=10 * mm, s_long=8 * cm, s_trans=16 * cm)
    transverse = slab.reinforcement.transverse
    assert transverse.layout == GRID
    assert str(transverse) == "Ø10 mm/8 cm×16 cm"
    assert transverse.notation("es") == "Ø10 mm/8 cm×16 cm"
    assert transverse.notation(compact=True) == "Ø10/8×16"
    assert transverse.arrangement() == ""
    # The drawing keeps the grid label it always had.
    slab.plot()
    assert "Ø10/8×16" in [text.get_text() for text in slab._ax.texts]


def test_the_compact_form_takes_its_unit_system_from_the_caller() -> None:
    """A metric beam with its spacing given in inches: the caller says which system the bare numbers are in."""
    beam = _wide_cirsoc_beam()
    beam.set_transverse_rebar(n_stirrups=1, d_b=8 * mm, s_l=6 * inch)
    transverse = beam.reinforcement.transverse
    assert transverse.notation(compact=True, imperial=False) == "2 legs Ø8/15.24"
    assert transverse.notation(compact=True, imperial=True) == '2 legs Ø0.31"@6'
    # Left unsaid, it follows the unit of s_l, as documented.
    assert transverse.notation(compact=True) == '2 legs Ø0.31"@6'


def test_the_beam_summary_av_cell_stays_in_mm_and_cm_with_sl_in_inches() -> None:
    """The As cells of the same row write their bars in mm; the Av cell does too, whatever unit sl came in."""
    beams = _summary_list()
    beams["sl"] = ["inch", 0, 8]
    summary = BeamSummary(
        concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        beam_list=beams,
    )
    assert list(summary.check()["Av"])[1:] == ["-", "2 legs Ø6/20.32"]


@pytest.mark.parametrize("language", ["ES", "es-AR", "sp", "fr", ""])
def test_an_unknown_language_raises_like_set_language(designed: RectangularBeam, language: str) -> None:
    """An explicit language is held to set_language's rule instead of falling back to English."""
    shear = designed.shear_design
    calls = [
        lambda: shear.notation(language),
        lambda: shear.notation(language, compact=True),
        lambda: shear.arrangement(language),
        lambda: shear.options[0].notation(language),
        lambda: shear.options[0].arrangement(language),
        lambda: designed.reinforcement.transverse.notation(language),
        lambda: designed.reinforcement.transverse.arrangement(language),
        lambda: designed.section_geometry.arrangement(language),
        lambda: describe_stirrup_cage(10, language),
        lambda: format_transverse_rebar(STIRRUPS, 5, "12", "14", "15.87", language=language),
    ]
    for call in calls:
        with pytest.raises(ValueError, match="Unknown language"):
            call()
    with pytest.raises(ValueError) as from_set_language:
        mento.set_language(language)
    with pytest.raises(ValueError) as from_notation:
        shear.notation(language)
    assert str(from_notation.value) == str(from_set_language.value)


# ---------------------------------------------------------------------------
# The cage
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "n_legs, stirrups, crossties",
    [
        (0, (), ()),
        (-2, (), ()),
        (1, (), (0,)),
        (2, ((0, 1),), ()),
        (3, ((0, 2),), (1,)),
        (4, ((0, 3), (1, 2)), ()),
        (9, ((0, 8), (1, 2), (3, 4), (5, 6)), (7,)),
        (10, ((0, 9), (1, 2), (3, 4), (5, 6), (7, 8)), ()),
        (16, ((0, 15), (1, 2), (3, 4), (5, 6), (7, 8), (9, 10), (11, 12), (13, 14)), ()),
    ],
)
def test_cage_legs(n_legs: int, stirrups: tuple, crossties: tuple) -> None:  # type: ignore[type-arg]
    assert cage_legs(n_legs) == (stirrups, crossties)


@pytest.mark.parametrize(
    "n_legs, english",
    [
        (0, "no stirrups"),
        (1, "1 crosstie"),
        (2, "single perimeter stirrup"),
        (3, "perimeter stirrup + 1 crosstie"),
        (4, "perimeter stirrup + 1 inner stirrup"),
        (9, "perimeter stirrup + 3 inner stirrups + 1 crosstie"),
        (10, "perimeter stirrup + 4 inner stirrups"),
        (16, "perimeter stirrup + 7 inner stirrups"),
    ],
)
def test_describe_stirrup_cage(n_legs: int, english: str) -> None:
    assert describe_stirrup_cage(n_legs, "en") == english
    spanish = describe_stirrup_cage(n_legs, "es")
    for part in english.split(" + "):
        key = part if part in ES else "{n} inner stirrups"
        translated = ES[key] if key == part else ES[key].format(n=part.split()[0])
        assert translated in spanish


def test_the_cage_in_spanish_words() -> None:
    assert describe_stirrup_cage(2, "es") == "estribo perimetral"
    assert describe_stirrup_cage(10, "es") == "estribo perimetral + 4 interiores"
    assert describe_stirrup_cage(9, "es") == "estribo perimetral + 3 interiores + 1 gancho suplementario"


# ---------------------------------------------------------------------------
# Where the notation is shown
# ---------------------------------------------------------------------------


def _summary_list() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Label": ["", "V101", "V102"],
            "Comb.": ["", "ELU 1", "ELU 2"],
            "b": ["cm", 20, 20],
            "h": ["cm", 50, 50],
            "cc": ["mm", 25, 25],
            "Nx": ["kN", 0, 0],
            "Vz": ["kN", 20, 100],
            "My": ["kNm", 0, 40],
            "ns": ["", 0, 1],
            "dbs": ["mm", 0, 6],
            "sl": ["cm", 0, 20],
            "n1": ["", 2, 2],
            "db1": ["mm", 12, 12],
            "n2": ["", 0, 0],
            "db2": ["mm", 0, 0],
            "n3": ["", 0, 0],
            "db3": ["mm", 0, 0],
            "n4": ["", 0, 0],
            "db4": ["mm", 0, 0],
        }
    )


def test_the_beam_summary_av_cell_is_the_compact_notation() -> None:
    summary = BeamSummary(
        concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        beam_list=_summary_list(),
    )
    table = summary.check()
    assert list(table["Av"])[1:] == ["-", "2 legs Ø6/20"]
    mento.set_language("es")
    table = summary.check()
    assert list(table["Av"])[1:] == ["-", ES["{n_legs} legs Ø{d_b}/{s_l}"].format(n_legs=2, d_b=6, s_l=20)]


@pytest.mark.parametrize("which", ["ACI", "EN"])
def test_the_notebook_shear_line_uses_the_english_notation(which: str) -> None:
    concrete = (
        Concrete_ACI_318_19(name="H25", f_c=25 * MPa)
        if which == "ACI"
        else Concrete_EN_1992_2004(name="C25", f_c=25 * MPa)
    )
    beam = RectangularBeam(
        label="V",
        concrete=concrete,
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=20 * cm,
        height=50 * cm,
        c_c=25 * mm,
    )
    Node(section=beam, forces=[Forces(label="C1", M_y=60 * kNm, V_z=150 * kN)]).design()
    mento.set_language("es")
    beam.shear_results
    line = beam._md_shear_results
    assert line.startswith(f"Shear reinforcing {beam.shear_design.notation('en')}, ")
    assert f"={round(beam._A_v.to('cm**2/m').magnitude, 2)} cm²/m" in line


def test_the_notebook_shear_line_of_a_slab_reads_its_grid() -> None:
    """It used to print ``10eØ8/16.0 cm`` for a Ø10/8×16 grid, reading the table by position."""
    slab = OneWaySlab(
        label="S",
        concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=100 * cm,
        height=25 * cm,
        c_c=25 * mm,
    )
    slab.set_slab_longitudinal_rebar_bot(d_b1=12 * mm, s_b1=15 * cm)
    slab.set_slab_transverse_rebar(d_b=10 * mm, s_long=8 * cm, s_trans=16 * cm)
    Node(section=slab, forces=[Forces(label="C1", M_y=40 * kNm, V_z=250 * kN)]).check()
    slab.shear_results
    line = slab._md_shear_results
    assert line.startswith("Shear reinforcing Ø10 mm/8 cm×16 cm, ")
    assert f"={round(slab._A_v.to('cm**2/m').magnitude, 2)} cm²/m" in line


# ---------------------------------------------------------------------------
# The examples the user guides print
# ---------------------------------------------------------------------------


def test_the_design_results_page_example() -> None:
    """docs/source/user_guide/design_results.rst: the shear block and the section geometry."""
    beam = RectangularBeam(
        label="101",
        concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=20 * cm,
        height=60 * cm,
        c_c=25 * mm,
    )
    Node(section=beam, forces=[Forces(label="C1", V_z=80 * kN, M_y=100 * kNm)]).design()
    shear = beam.shear_design
    assert str(shear) == "2 legs Ø10 mm @ 27 cm · 14 cm between legs (max 55.74 cm)"
    assert shear.notation("es") == "2 ramas Ø10 mm c/27 cm · 14 cm entre ramas (máx. 55.74 cm)"
    assert shear.notation(compact=True) == "2 legs Ø10/27"
    assert shear.arrangement() == "single perimeter stirrup"
    assert f"{shear.s_w.to('cm'):.4g~P}" == "14 cm"
    assert f"{shear.s_max_w:.4g~P}" == "55.74 cm"
    assert f"{shear.s_max_l:.4g~P}" == "27.87 cm"
    assert shear.s_max_l_table == shear.s_max_l
    assert shear.s_max_l_support is None
    geometry = beam.section_geometry
    assert [f"{x:.4g~P}" for x in geometry.leg_x] == ["3 cm", "17 cm"]
    assert geometry.arrangement() == "single perimeter stirrup"

    # Where the spacing limit governs, the alternatives share one spacing.
    shallow = RectangularBeam(
        label="x",
        concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=20 * cm,
        height=40 * cm,
        c_c=25 * mm,
    )
    Node(section=shallow, forces=[Forces(label="C1", V_z=100 * kN, M_y=30 * kNm)]).design()
    assert [option.notation(compact=True) for option in shallow.shear_design.options] == [
        "2 legs Ø10/17",
        "2 legs Ø12/17",
        "2 legs Ø16/17",
    ]


def test_the_language_page_example() -> None:
    """docs/source/user_guide/language.rst: a CIRSOC 20x60 in Spanish."""
    beam = RectangularBeam(
        label="101",
        concrete=Concrete_CIRSOC_201_25(name="H25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=20 * cm,
        height=60 * cm,
        c_c=25 * mm,
    )
    Node(section=beam, forces=[Forces(label="C1", V_z=80 * kN, M_y=100 * kNm)]).design()
    mento.set_language("es")
    assert beam.shear_design.notation() == "2 ramas Ø6 mm c/28 cm · 14.4 cm entre ramas (máx. 40 cm)"
    assert beam.shear_design.arrangement() == "estribo perimetral"
    assert beam.shear_design.notation("en") == "2 legs Ø6 mm @ 28 cm · 14.4 cm between legs (max 40 cm)"
    assert str(beam.shear_design) == beam.shear_design.notation("en")


def test_the_beams_page_notebook_line() -> None:
    """docs/source/user_guide/beams.rst: the flexure and shear lines of the notebook summary."""
    beam = RectangularBeam(
        label="101",
        concrete=Concrete_ACI_318_19(name="C25", f_c=25 * MPa),
        steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
        width=20 * cm,
        height=60 * cm,
        c_c=2.5 * cm,
    )
    beam.set_longitudinal_rebar_bot(n1=2, d_b1=16 * mm, n2=1, d_b2=12 * mm, n3=2, d_b3=12 * mm, n4=1, d_b4=10 * mm)
    beam.set_longitudinal_rebar_top(n1=2, d_b1=16 * mm)
    beam.set_transverse_rebar(n_stirrups=1, d_b=10 * mm, s_l=20 * cm)
    Node(
        section=beam, forces=[Forces(label="C1", M_y=-80 * kNm, V_z=80 * kN), Forces(label="C2", M_y=90 * kNm)]
    ).check()
    beam.shear_results
    line = beam._md_shear_results
    assert line.startswith("Shear reinforcing 2 legs Ø10 mm @ 20 cm · 14 cm between legs (max 54.29 cm), ")
    assert "=7.85 cm²/m" in line and "=80.0 kN" in line and "=203.52 kN" in line and "DCR}=0.39" in line
    beam.flexure_results
    top, bottom = [row for row in beam._md_flexure_results.splitlines() if row.strip()]
    assert top.startswith("Top longitudinal rebar: 2Ø16, $A_{s,top}$ = 4.02 cm², $M_u$ = -80.0 kNm, ")
    assert r"$\phi M_n$ = 81.65 kNm" in top and "DCR}=0.98" in top
    assert bottom.startswith("Bottom longitudinal rebar: 2Ø16+1Ø12 ++ 2Ø12+1Ø10, $A_{s,bot}$ = 8.2 cm², ")
    assert r"$\phi M_n$ = 155.7 kNm" in bottom and "DCR}=0.58" in bottom
