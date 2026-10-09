"""Mechanical enforcement of the codes/ layer boundary.

ADR-0002 says the checker does not compute; ADR-0005 adds that the equations do
not convert. Both were rules that depended on review discipline, which is
exactly the kind of boundary that erodes. These tests read the source with `ast`
so a violation fails CI instead of needing to be noticed.
"""

import ast
import dataclasses
import subprocess
import sys
from pathlib import Path

import pytest

from mento.beam import RectangularBeam
from mento.forces import Forces
from mento.material import Concrete_ACI_318_19, Concrete_EN_1992_2004, SteelBar
from mento.node import Node
from mento.units import cm, kN, kNm, mm, MPa

EQUATIONS_ROOT = Path(__file__).resolve().parents[2] / "mento" / "codes"

EQUATION_MODULES = sorted(EQUATIONS_ROOT.glob("*/equations/*.py"))

# Modules that carry units are the boundary; equations must stay below it.
UNIT_MODULES = {"pint", "mento.units"}


def _parse(path: Path) -> ast.Module:
    # utf-8-sig, not utf-8: a file saved with a BOM on Windows would otherwise
    # raise SyntaxError here and fail these tests for the wrong reason.
    return ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))


def test_equation_modules_exist():
    """Guards the other tests: an empty glob would make them vacuously pass."""
    assert EQUATION_MODULES, f"no equation modules found under {EQUATIONS_ROOT}"


@pytest.mark.parametrize(
    "statement",
    [
        "from mento import RectangularBeam, Forces, Node",
        "from mento.codes.aci_318_19.equations import shear",
        "from mento.codes.en_1992_2004.equations import flexure",
        "import mento.rebar",
        "import mento.codes",
        "from mento import SectionGeometry",
        "import mento.section_geometry",
    ],
    ids=lambda s: s.split()[-1],
)
def test_each_entry_point_imports_in_a_fresh_interpreter(statement: str) -> None:
    """Import cycles hide from the suite, because pytest has already imported
    half the package by the time any test runs.

    A cycle between ``mento.rebar`` and the code modules once shipped green
    here for exactly that reason and only failed for a user typing
    ``from mento import RectangularBeam`` first. Each of these runs cold.
    """
    result = subprocess.run(
        [sys.executable, "-c", statement],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"`{statement}` fails from a cold interpreter:\n{result.stderr}"


def test_importing_the_code_layer_does_not_drag_in_presentation() -> None:
    """``mento.codes`` is calculation; matplotlib and docx belong to the report
    layer and must not be pulled in by importing it."""
    probe = "import sys, mento.codes; print('matplotlib' in sys.modules, 'docx' in sys.modules)"
    result = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False False", f"mento.codes pulled in presentation: {result.stdout!r}"


MENTO_ROOT = EQUATIONS_ROOT.parent

# Every element: the classes a user builds and calls a check on.
ELEMENT_MODULES = [
    MENTO_ROOT / name
    for name in (
        "beam.py",
        "slab.py",
        "shear_wall.py",
        "punching.py",
        "beam_summary.py",
        "slab_summary.py",
        "shear_wall_summary.py",
    )
]

PRESENTATION_LIBRARIES = {"matplotlib", "docx", "IPython"}

#: Modules of the calculation layer that are neither an element nor a design
#: code, and that a drawing reads rather than the other way round: the public
#: geometry of a section is data, which ``mento.plots`` draws.
CALCULATION_LAYER_MODULES = [MENTO_ROOT / "section_geometry.py"]


@pytest.mark.parametrize("path", ELEMENT_MODULES + CALCULATION_LAYER_MODULES, ids=lambda p: p.name)
def test_elements_do_not_import_presentation_libraries(path: Path) -> None:
    """Phase 3: an element is geometry and orchestration, not a renderer.

    Drawing lives in ``mento.plots``, tables and reports in ``mento.reports``,
    and the element only ever delegates. Importing matplotlib, python-docx or
    IPython here is the signal that presentation has leaked back in.

    A ``TYPE_CHECKING`` import is fine — a return annotation costs nothing at
    runtime — so only real imports count.
    """
    tree = _parse(path)
    type_checking_only = {
        id(node)
        for parent in ast.walk(tree)
        if isinstance(parent, ast.If)
        and (
            (isinstance(parent.test, ast.Name) and parent.test.id == "TYPE_CHECKING")
            or (isinstance(parent.test, ast.Attribute) and parent.test.attr == "TYPE_CHECKING")
        )
        for node in ast.walk(parent)
    }

    offenders = []
    for node in ast.walk(tree):
        if id(node) in type_checking_only:
            continue
        if isinstance(node, ast.Import):
            offenders += [a.name for a in node.names if a.name.split(".")[0] in PRESENTATION_LIBRARIES]
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in PRESENTATION_LIBRARIES:
                offenders.append(node.module)

    assert not offenders, (
        f"{path.name} imports presentation libraries {offenders}. "
        "Move the rendering into mento.plots or mento.reports and delegate to it."
    )


@pytest.mark.parametrize("path", CALCULATION_LAYER_MODULES, ids=lambda p: p.name)
def test_calculation_modules_do_not_import_the_presentation_layer(path: Path) -> None:
    """The geometry is what a drawing reads: it must not reach back into the drawing or the reports."""
    imported = [
        node.module
        for node in ast.walk(_parse(path))
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith(("mento.plots", "mento.reports"))
    ]
    assert not imported, f"{path.name} imports the presentation layer: {imported}"


def test_the_warnings_take_no_quantity_from_the_report_layer() -> None:
    """ADR-0004: presentation consumes result objects; a quantity of the section is the element's.

    ``mento.design_warnings`` is data the element builds, and the spacing its
    ``bar_spacing_exceeds_max`` quotes -- the centre-to-centre spacing of the
    layer nearest the tension face, against the Table 24.3.2 cap -- is a
    quantity of the section: the beam computes it
    (``RectangularBeam._tension_bar_spacing``) and the report prints it.
    It is computed there, not in ``mento.reports.tables``, and this keeps
    it so.
    The one report helper the warnings still read, ``_bar_spacing_row``,
    only labels the clear spacing the beam stores and the limits the element
    supplies.
    """
    tree = _parse(MENTO_ROOT / "design_warnings.py")
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("mento.reports")
        for alias in node.names
    }
    assert imported <= {"_bar_spacing_row"}, f"design_warnings reads {imported} from the report layer"


# Every design-code module: no longer just the beam ones, since the wall's
# report tables moved out too.
CODE_MODULES = sorted(EQUATIONS_ROOT.glob("*.py"))


def test_code_modules_are_discovered() -> None:
    """Guards the test below: an empty glob would make it vacuously pass."""
    assert len(CODE_MODULES) >= 3, f"expected the code modules under {EQUATIONS_ROOT}"


@pytest.mark.parametrize("path", CODE_MODULES, ids=lambda p: p.name)
def test_code_modules_do_not_build_report_tables(path: Path) -> None:
    """Phase 3: labelled, rounded, unit-annotated tables are presentation.

    They used to be roughly a third of each code module. They live under
    ``mento/reports/`` now, and the element decides when to build them — the
    design code does not, which is what lets a check skip them entirely.
    """
    offenders = [
        node.name
        for node in ast.walk(_parse(path))
        if isinstance(node, ast.FunctionDef)
        and (node.name.startswith("_initialize_dicts") or node.name.startswith("_compile_"))
    ]
    assert not offenders, f"{path.name} still builds report tables: {offenders}"


@pytest.mark.parametrize("path", EQUATION_MODULES, ids=lambda p: p.name)
def test_equations_do_not_import_units(path: Path) -> None:
    """ADR-0005: equations take and return floats, so they never see a Quantity."""
    offenders = []
    for node in ast.walk(_parse(path)):
        if isinstance(node, ast.Import):
            offenders += [a.name for a in node.names if a.name.split(".")[0] in {"pint"}]
        elif isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".")[0]
            if node.module in UNIT_MODULES or root == "pint":
                offenders.append(node.module)
    assert not offenders, f"{path.name} imports units: {offenders}. Equations work in plain floats (ADR-0005)."


@pytest.mark.parametrize("path", EQUATION_MODULES, ids=lambda p: p.name)
def test_equations_are_free_functions(path: Path) -> None:
    """No `self`, so no element state can leak into an equation."""
    tree = _parse(path)
    classes = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    assert not classes, f"{path.name} defines classes {classes}; equations are free functions."

    selfish = [
        n.name
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(a.arg == "self" for a in n.args.args)
    ]
    assert not selfish, f"{path.name} has functions taking self: {selfish}."


@pytest.mark.parametrize("path", EQUATION_MODULES, ids=lambda p: p.name)
def test_every_public_equation_cites_its_clause(path: Path) -> None:
    """A formula whose clause is not written down cannot be reviewed against the code."""
    missing = []
    for node in ast.walk(_parse(path)):
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
            doc = ast.get_docstring(node) or ""
            if "ACI" not in doc and "EN 199" not in doc and "CIRSOC" not in doc:
                missing.append(node.name)
    assert not missing, f"{path.name}: no code clause cited in the docstring of {missing}."


# ---------------------------------------------------------------------------
# Phase 4 — the design-code registry
# ---------------------------------------------------------------------------

#: The modules that must not know which design codes exist. Elements, plus the
#: two layers that used to branch on the code string alongside them.
CODE_AGNOSTIC_MODULES = ELEMENT_MODULES + [
    MENTO_ROOT / "section_geometry.py",
    MENTO_ROOT / "rebar.py",
    MENTO_ROOT / "reports" / "views.py",
    MENTO_ROOT / "reports" / "summaries.py",
]

#: Every registered code's title, as a literal would spell it.
_CODE_TITLES = ("ACI 318-19", "CIRSOC 201-25", "EN 1992-2004")


@pytest.mark.parametrize("path", CODE_AGNOSTIC_MODULES, ids=lambda p: p.name)
def test_no_module_outside_codes_names_a_design_code(path: Path) -> None:
    """Phase 4: dispatch goes through the registry, never a string comparison.

    ``if self.concrete.design_code == "ACI 318-19"`` repeated across elements,
    rebar and the report views is the coupling the registry removes: a code
    missing from one of those chains failed at runtime, in whichever branch
    nobody had updated, rather than at lookup.
    """
    offenders = [
        node.value for node in ast.walk(_parse(path)) if isinstance(node, ast.Constant) and node.value in _CODE_TITLES
    ]
    assert not offenders, f"{path.name} names design codes directly: {sorted(set(offenders))}"


def test_the_registry_finds_every_code_subpackage() -> None:
    """A code registers by existing, not by being added to a list."""
    from mento.codes.registry import registered_codes

    assert set(registered_codes()) == set(_CODE_TITLES)


def test_a_new_design_code_needs_no_element_edited() -> None:
    """The exit criterion of Phase 4, executed rather than asserted.

    Registers a code that exists only for the duration of this test, reusing
    the ACI hooks, and drives a real beam through check and design with it. If
    any element still branched on a known title, this would fall into the EN
    branch or raise; that it produces ACI's own numbers is the proof that the
    dispatch is data.
    """
    from mento.codes.registry import _REGISTRY, DesignCode, design_code, register
    from mento.reports.tables import _REPORT_BUILDERS

    concrete = Concrete_ACI_318_19(name="H25", f_c=25 * MPa)
    reference = design_code(concrete)

    invented = DesignCode(
        **{
            **{f.name: getattr(reference, f.name) for f in dataclasses.fields(reference)},
            "title": "NBR 6118-2023",
            "year": 2023,
        }
    )
    register(invented)
    # Report *content* is per-code by nature, so a new code brings its tables.
    _REPORT_BUILDERS[invented.title] = _REPORT_BUILDERS[reference.title]
    try:
        beam = RectangularBeam(
            label="invented-code",
            concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
            steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
            width=30 * cm,
            height=50 * cm,
            c_c=25 * mm,
        )
        beam.concrete.design_code = invented.title
        beam.set_longitudinal_rebar_bot(n1=3, d_b1=20 * mm)
        beam.set_transverse_rebar(n_stirrups=1, d_b=8 * mm, s_l=20 * cm)
        combo = [Forces(label="C1", V_z=80 * kN, M_y=90 * kNm)]

        # Checks run and report tables build.
        assert beam.shear_check_results(combo)[0].DCR > 0
        assert beam.flexure_check_results(combo)[0].bottom.DCR > 0
        assert not beam.check_shear(combo).empty
        assert not beam.check_flexure(combo).empty

        # And it is ACI's answer, not a fallback to the other branch. Compared
        # before designing, which would change the reinforcement underneath.
        aci = RectangularBeam(
            label="aci",
            concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
            steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
            width=30 * cm,
            height=50 * cm,
            c_c=25 * mm,
        )
        aci.set_longitudinal_rebar_bot(n1=3, d_b1=20 * mm)
        aci.set_transverse_rebar(n_stirrups=1, d_b=8 * mm, s_l=20 * cm)
        assert beam.shear_check_results(combo)[0].DCR == aci.shear_check_results(combo)[0].DCR

        # Designing works too, and it is the design that assigns the bars.
        Node(section=beam, forces=combo).design()
        assert beam.reinforcement.transverse.n_stirrups > 0
    finally:
        _REGISTRY.pop(invented.title, None)
        _REPORT_BUILDERS.pop(invented.title, None)


def test_registering_the_same_code_twice_is_refused() -> None:
    """Two codes answering to one title would make dispatch order-dependent."""
    from mento.codes.registry import design_code, register

    existing = design_code(Concrete_ACI_318_19(name="H25", f_c=25 * MPa))
    with pytest.raises(ValueError, match="already registered: ACI 318-19"):
        register(existing)


def test_a_code_without_a_hook_names_itself() -> None:
    """EN has no punching design yet; the error should say which code and which hook."""
    from mento.codes.registry import design_code

    en = design_code(Concrete_EN_1992_2004(name="C25", f_c=25 * MPa))
    with pytest.raises(NotImplementedError, match="design punching is not implemented.*EN 1992-2004"):
        en.requires("design_punching")


def test_a_code_registered_without_report_tables_says_so() -> None:
    """Registering a code is not the same as writing its report tables.

    They live in ``mento.reports`` and cannot move into the code subpackages:
    importing them from ``codes/`` would pull pandas and docx back into a layer
    a boundary test keeps free of them. So the two registrations are separate,
    and missing the second one has to be a clear error rather than a KeyError
    from inside a table builder.
    """
    from mento.codes.registry import _REGISTRY, DesignCode, design_code, register

    reference = design_code(Concrete_ACI_318_19(name="H25", f_c=25 * MPa))
    invented = DesignCode(
        **{
            **{f.name: getattr(reference, f.name) for f in dataclasses.fields(reference)},
            "title": "NBR 6118-2023",
        }
    )
    register(invented)
    try:
        beam = RectangularBeam(
            label="no-tables",
            concrete=Concrete_ACI_318_19(name="H25", f_c=25 * MPa),
            steel_bar=SteelBar(name="ADN 420", f_y=420 * MPa),
            width=30 * cm,
            height=50 * cm,
            c_c=25 * mm,
        )
        beam.set_longitudinal_rebar_bot(n1=3, d_b1=20 * mm)
        beam.concrete.design_code = invented.title
        with pytest.raises(NotImplementedError, match="no report tables for design code: NBR 6118-2023"):
            beam.check_shear([Forces(label="C1", V_z=80 * kN)])
    finally:
        _REGISTRY.pop(invented.title, None)


##########################################################
# DATACLASS BODIES: WHAT THE EDITOR SHOWS THE CALLER
##########################################################

PACKAGE_MODULES = sorted(MENTO_ROOT.rglob("*.py"))


def _is_dataclass_decorated(node: ast.ClassDef) -> bool:
    for decorator in node.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        name = target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", None)
        if name == "dataclass":
            return True
    return False


def _conditionally_annotated_names(body: list[ast.stmt]) -> list[str]:
    """Names annotated inside an ``if`` / ``try`` in a class body, not at its top level."""
    found: list[str] = []
    for node in body:
        nested: list[ast.stmt] = []
        if isinstance(node, ast.If):
            nested = [*node.body, *node.orelse]
        elif isinstance(node, ast.Try):
            nested = [*node.body, *node.orelse, *node.finalbody]
        for inner in ast.walk(ast.Module(body=nested, type_ignores=[])):
            if isinstance(inner, ast.AnnAssign) and isinstance(inner.target, ast.Name):
                found.append(inner.target.id)
    return found


def test_package_modules_are_discovered() -> None:
    """Guards the test below: an empty glob would make it vacuously pass."""
    assert len(PACKAGE_MODULES) > 20, f"only {len(PACKAGE_MODULES)} modules found under {MENTO_ROOT}"


@pytest.mark.parametrize("path", PACKAGE_MODULES, ids=lambda p: p.name)
def test_dataclass_bodies_declare_no_conditional_annotations(path: Path) -> None:
    """Every annotation in a dataclass body is a constructor argument to the editor.

    A type checker reads ``if TYPE_CHECKING:`` as taken, so a name declared
    under it counts as a field even though ``dataclasses`` never sees it at
    runtime. That is how the fifty-odd compatibility-layer attributes on
    ``RectangularBeam`` became required keyword arguments in IntelliSense while
    the runtime signature stayed clean -- a defect no test that imports the
    class can catch. Declarations that are not fields belong on a plain base
    class such as ``_DesignCodeAttributes``, which contributes none.
    """
    for node in ast.walk(_parse(path)):
        if isinstance(node, ast.ClassDef) and _is_dataclass_decorated(node):
            offenders = _conditionally_annotated_names(node.body)
            assert not offenders, (
                f"{path.name}: {node.name} is a dataclass, so {offenders} read as "
                f"constructor fields to a type checker. Move them to a plain base class."
            )
