# CLAUDE.md — mento

Guidance for Claude Code (claude.ai/code) when working in this repository.

Reinforced concrete design Python package. Covers beams, slabs, sections, materials, rebar, and design code implementations (ACI 318-19, EN 1992-2004, CIRSOC 201-25). Uses strict mypy typing, ruff formatting, and pytest with coverage.

---

## Python environment

mento requires Python >= 3.12. Which interpreter to use depends on where the session runs.

**Windows (local development):** use the `rame-env` conda environment. It is the only one
with mento's dependencies installed, so the base `anaconda3` interpreter either fails on
import or runs against stale packages.

```
C:\Users\mihdi\anaconda3\envs\rame-env\python.exe
```

`.vscode/settings.json` registers the project with the conda environment manager
(`python-envs.pythonProjects`), so the VS Code test runner and IntelliSense resolve the same
interpreter.

**Linux / Claude Code on the web:** there is no conda environment. The SessionStart hook
`.claude/hooks/session-start.sh` builds `.venv` on the first Python >= 3.12 it finds and
installs mento with `-e ".[dev]"`. Use that interpreter:

```bash
.venv/bin/python
```

If `import mento` fails, run the hook by hand: `bash .claude/hooks/session-start.sh`.

Every command below writes the interpreter as `$PY`. Substitute the one for your platform:
the `rame-env` path on Windows, `.venv/bin/python` on Linux.

---

## Running tests

```bash
# Full suite (uses pyproject.toml addopts: --cov, --cov-report=html, --cov-report=term-missing)
$PY -m pytest tests/

# Single file, fast iteration (strip addopts to avoid --cov conflicts)
$PY -m pytest tests/elements/test_beam.py --override-ini="addopts=" -v

# Single file with coverage
$PY -m pytest tests/elements/test_beam.py --override-ini="addopts=" --cov=mento --cov-report=term-missing -q

# Single test by name
$PY -m pytest tests/elements/test_beam.py::test_my_function --override-ini="addopts=" -v

# Coverage for one module only (Linux)
$PY -m pytest tests/ --override-ini="addopts=" --cov=mento --cov-report=term-missing -q | grep -E "beam|slab|rebar"
```

On Windows, pipe to `Select-String` instead of `grep`, and prefix the interpreter path with
the call operator: `& "C:\...\python.exe" -m pytest ...`.

> `--override-ini="addopts="` strips the default `--cov` flags from pyproject.toml. Required when running single files or adding custom `--cov` arguments to avoid argument conflicts.

---

## Linting and type checking

```bash
$PY -m ruff check . --fix     # lint, auto-fix
$PY -m ruff format .          # format
$PY -m mypy mento/            # strict type check
```

`make all` runs mypy, ruff and pytest in one go when the tools are on `PATH`.

Ruff config: 120-char line limit. MyPy config: `strict = true`, `allow_any_generics = true`. Package checked: `mento/`.

---

## Project structure

```
mento/
├── __init__.py             Lazy-import public API via __getattr__
├── _version.py             Package version
├── units.py                Pint unit registry (m, cm, mm, kN, kNm, MPa, kip, psi, etc.)
├── material.py             Concrete_ACI_318_19, Concrete_EN_1992_2004, Concrete_CIRSOC_201_25, SteelBar, SteelStrand
├── rebar.py                Rebar — bar database and selection logic
├── bar_sizes.py            ASTM bar sizes: bar_designation("#6") / bar_diameter(6), the table imperial output and Rebar share
├── section.py              Section base class
├── section_geometry.py     SectionGeometry — where the bars and stirrup legs are, as the checks assume them
├── rectangular.py          RectangularSection — geometry and cover calculations
├── beam.py                 RectangularBeam — design, check, and result accessors
├── slab.py                 OneWaySlab and Footing — one-way slab design
├── shear_wall.py           ShearWall — in-plane shear check/design
├── column.py               Column — geometry (shape, position, edge distances) for punching shear
├── punching.py             PunchingSlab, PunchingNode, Opening, Capital — two-way punching shear
├── punching_results.py     PunchingCheck — frozen result of a punching check
├── wall_results.py         WallMesh, WallShearCheck, WallShearDesign — public results of a ShearWall
├── design_results.py       Public read-only result dataclasses (FlexureDesign, ShearDesign, SectionReinforcement, ...) — ADR-0001
├── design_warnings.py      DesignWarning — detailing limits a section misses, with stable codes (beam.warnings / node.warnings)
├── precompute.py           SectionFloats (ADR-0005); DISPLAY / DISPLAY_LABEL: the unit every report shows, per unit system
├── forces.py               Forces(label, N_x, V_z, M_y, M_x) with pint units
├── node.py                 Node(section, forces) — drives check/design
├── settings.py             BeamSettings — metric/imperial defaults for design rules
├── results.py              Formatter, TablePrinter, DocumentBuilder — display helpers
├── beam_summary.py         BeamSummary — many beam sections, read from two tables
├── slab_summary.py         OneWaySlabSummary — the same for one-way slab strips
├── shear_wall_summary.py   ShearWallSummary — the same for walls
├── summary_tables.py       The sections / forces tables of the summaries: read, write, errors
├── summary_base.py         What the summaries share (one Node per section, frozen results)
├── summary.py              Deprecated shim re-exporting BeamSummary (emits DeprecationWarning)
├── i18n.py                 set_language() — language of reports, drawing, warnings and stirrup notation()
├── plots/                  Matplotlib drawings: sections.py, walls.py, punching.py
├── reports/                Presentation layer: tables, views, documents, summaries, table_style, headings, punching
└── codes/
    ├── registry.py               DesignCode dataclass and the registered codes — every element dispatches through it
    ├── check_state.py            Check states held off the element; the report path copies them back
    ├── flexure_design.py         Flexure design engine shared by the codes (private)
    ├── wall_mesh_design.py       Wall mesh bar search shared by the codes (private)
    ├── aci_318_19/               code.py (registry entry) + equations/{flexure,shear,wall,punching}.py — floats only
    ├── en_1992_2004/             code.py + equations/{flexure,shear,wall,punching}.py
    ├── ACI_318_19_beam.py        Beam shear/flexure checks and design (functions typed `self: RectangularBeam`)
    ├── ACI_318_19_wall.py        Wall shear per ACI 318-19
    ├── ACI_318_19_punching.py    Punching checker — preconditions enforced, equations pending (Phase 2)
    ├── EN_1992_2004_beam.py      Beam shear/flexure per EN 1992-2004
    ├── EN_1992_2004_wall.py      Wall shear per EN 1992-1-1 §6.2 + §9.6 (d = 0.8 lw, vertical mesh designed first)
    └── EN_1992_2004_punching.py  Punching checker — equations pending (Phase 5)
```

---

## Test structure

```
tests/
├── conftest.py      Shared fixtures (materials, the beam examples of test_beam and validation/) + Agg backend
├── helpers.py       Pint adapters for the float-only ACI flexure functions (test_beam and validation/)
├── architecture/    Layer rules, published_example sources and placement, doc-cited tests, public API
├── equations/       Float-only clause functions (ACI flexure / shear / wall, EN, EN wall)
├── materials/       material, rebar, units, settings, forces
├── sections/        section, rectangular, node
├── elements/        beam, slab, footing, shear_wall (ACI), shear_wall_en, punching
├── design/          design_results, design_options, design_warnings, flexure_design_properties, ...
├── reports/         results, headings, table_style, i18n, beam_summary, shear_wall_summary
└── validation/      ONLY the tests marked published_example: CRSI guide, CSI/ETABS verification, ETABS runs, Concrete Centre, eurocodeapplied

scripts/
└── modules_testing.py    Manual/exploratory script; not part of the test suite
```

`tests/validation/` holds exactly the tests that reproduce a case validated outside
mento, each marked `published_example` with a `Source:` paragraph in its docstring;
`tests/architecture/test_published_examples.py` fails if a marked test lives elsewhere
or an unmarked one lives there, and fails a `Source:` that names a Calcpad sheet: a
Calcpad sheet reproduces a calculation but is not a published source, so tests checked
only against one are regression tests in the other folders (the beam ones sit at the
end of `elements/test_beam.py`). Tests written against mento itself go there too.
The release publishes the count of that folder.

`pyproject.toml` is the only pytest config. A `tests/pytest.ini` would change the
rootdir and silently disable the coverage `addopts`, so there is none.

**Fixtures:** `conftest.py` holds the fixtures that several modules share
(`concrete_c25`, `steel_b500s`, `steel`, and the beam examples
`beam_example_imperial`, `beam_example_EN_1992_2004_01`, `beam_example_flexure_ACI`
that `elements/test_beam.py` and `validation/` both use) and sets the `Agg` backend
once, so no test module needs the `matplotlib.use("Agg")` incantation. Note that
`materials/test_rebar.py` defines its **own** `beam_example_imperial`, with different
geometry and settings: its module-level fixture overrides the conftest one there, on
purpose.

---

## Architecture & key patterns

**Class hierarchy:**
```
Section → RectangularSection → RectangularBeam → OneWaySlab → Footing
                                               → ShearWall
PunchingSlab (standalone dataclass); PunchingNode(slab, column, forces) pairs it with a Column
```

**Unit-system detection:** `Concrete` auto-detects metric vs. imperial from `f_c` units (MPa → metric, psi → imperial). This propagates through `BeamSettings` and all `Forces` objects — never hard-code unit assumptions.

**Design code delegation:** elements never compare `concrete.design_code` against a string; they look the code up in `codes/registry.py` (`DesignCode`) and call its hooks (`check_shear`, `design_flexure`, `check_punching`, ...). Each code's entry lives in `codes/aci_318_19/code.py` / `codes/en_1992_2004/code.py`; the hooks are module-level functions typed as `self: RectangularBeam` in `codes/ACI_318_19_beam.py` and friends, which convert on entry and call the float-only clause functions in `equations/` (ADR-0002, ADR-0005). `tests/architecture/test_architecture_boundaries.py` fails the build if these rules are broken. `Concrete_CIRSOC_201_25` subclasses `Concrete_ACI_318_19` (same formulas, metric only, `design_code = "CIRSOC 201-25"`).

**`BeamSettings` sentinel pattern:** Unset fields use `_NOT_SET` so `__post_init__` can apply metric or imperial defaults conditionally based on the detected unit system.

**`__init__.py` lazy loading:** Public API uses `__getattr__` so submodules are only imported on first attribute access. `TYPE_CHECKING` guards prevent circular imports.

---

## Key module notes

### beam

- `RectangularBeam` is a `@dataclass` that extends `RectangularSection`.
- Design code logic is factored into `codes/ACI_318_19_beam.py` and `codes/EN_1992_2004_beam.py`; beam delegates to these via direct function calls.
- `BeamSettings` controls spacing, bar diameter limits, and unit system — constructed first and passed to the beam.

### material

- Three concrete classes for different codes: `Concrete_ACI_318_19`, `Concrete_EN_1992_2004`, `Concrete_CIRSOC_201_25`.
- `SteelBar` defines yield strength and modulus.
- Unit system (metric vs. imperial) is determined by the concrete instance passed to `BeamSettings`.

### slab

- `OneWaySlab` covers one-way slab flexure and shear design.
- Shares the same material and unit infrastructure as beam.

### punching

- `PunchingSlab` takes `(concrete, steel_bar, h, c_c, outer_direction="x")`. Plan and status: [docs/architecture/punching-roadmap.md](docs/architecture/punching-roadmap.md).
- The top reinforcement is declared as bars, and `d` and ρ are **derived** from it — position 1 is the base mat, position 3 the extra bars over the column:
  ```python
  slab.set_rebar_x(d_b1=12*mm, s_b1=15*cm, d_b3=16*mm, s_b3=15*cm)
  slab.set_rebar_y(d_b1=12*mm, s_b1=15*cm)
  slab.d_x, slab.d_y, slab.d_avg, slab.rho_x, slab.rho_y, slab.rho_l, slab.A_s_x
  ```
- `rho_x` / `rho_y` / `d_avg` are read-only. `slab.d_avg = ...` raises; use `slab.set_effective_depth(d_x=..., d_y=...)`, which re-derives ρ against the depths it sets.
- With no bars declared, the depths fall back to a two-mat Ø16 / #5 layout (so `d_avg = h - c_c - 16 mm`) and `rho_x`/`rho_y` are `None`, not zero.
- `slab.data` / `node.data` render the inputs as Markdown (delegate to `mento/reports/punching.py`), like `beam.data`.
- The slab is checked through `PunchingNode(slab, column, forces, openings=None, capital=None)`. `Column` describes `shape` (`"rectangular"` / `"circular"`), `position` (`"interior"` / `"edge"` / `"corner"`), and edge distances when applicable.
- Forces at a node: **`V_z`** is the punching load (`Vu` / `VEd`), plus `M_x` and `M_y`. `N_x` is not used — see `docs/source/user_guide/local_axes.rst`.
- `node.check()` is wired: it dispatches through the code registry and returns a frozen `PunchingCheck` (`mento/punching_results.py`), not a DataFrame. The **equations are stubs that raise** — they are being recreated from a validated Calcpad sheet (Phase 2 ACI, Phase 5 EN). The checkers already refuse a force with no `V_z`, a capital or opening (Phase 3), and — for EN only — a slab with no declared ρ.
- `node.design()` raises via the registry: `design_punching` is Phase 4.

### units

- Import units directly: `from mento import m, cm, mm, kN, MPa` etc.
- `ureg` is the shared `UnitRegistry` — do not create additional registries.

### results / beam_summary

- `Formatter`: formats pint quantities for display.
- `TablePrinter`: renders pandas DataFrames as styled tables (Markdown/IPython).
- `DocumentBuilder`: builds Word (python-docx) report documents.
- `BeamSummary` (`mento/beam_summary.py`; `mento/summary.py` is a deprecated shim), `OneWaySlabSummary` and `ShearWallSummary` read **two tables**: `Sections` (one row per section, key `(Level, Label)`, geometry and **both faces**; beam stirrups as `legs` = 2 per closed stirrup) and `Forces` (`Label, Comb., Nx, Vz, My`). The 1.4.0 single table raises; `split_single_table` converts it.
  - The `Node`s are the only state: `sections_table` / `forces_table` are read off them.
  - Element hooks: `_SPEC`, `_section(key, row)` and its exact inverse `_section_row(section)`, `_validate_section_row`, `_design`, `_rebar_labels`, `_check_record`, `_has_reinforcement`, `_sections_overview`. (#180's `_new_section`, `_set_face`, `_set_transverse`, `_designed` are gone.)
  - `.check()`: one row per section, governing combination per DCR, `Warnings` codes; `Ok?` fails on any warning; frozen `results`.
  - `.design()` is `Node.design()`, writing both faces. `from_excel` / `to_excel` / `tables` / `from_nodes`; `results_detailed_doc(index)` (position or label) in `reports/summaries.py`.

---

## Running mento interactively (design / check from the CLI)

The full API walkthrough — materials, section, forces, node, reading the designed rebar,
printing results outside Jupyter, and the gotchas — lives in a rule file that Claude Code
imports:

@.claude/rules/interactive-usage.md

---

## Claude Code setup in this repo

```
.claude/
├── settings.json                  Shared permissions and the SessionStart hook (committed)
├── settings.local.json            Personal overrides, machine-specific paths (gitignored)
├── hooks/session-start.sh         Builds .venv and installs mento on Linux/web sessions
├── rules/interactive-usage.md     Imported by this file via @ — how to drive mento from a script
└── skills/
    ├── design-section/            Design or check a real section with mento
    └── prepare-release/           Bump version + CHANGELOG for a release branch
```

Keep this file under ~2000 words. Anything longer, or only needed for one kind of task,
belongs in `.claude/rules/` (imported with `@`) or in a skill.

---

## CI / GitHub Actions

Workflow: `.github/workflows/tests.yml`
- Runs on push/PR to `main`
- `tests` job: Python 3.12 and 3.13 on windows-latest, installing `-e ".[test]"`.
  Runs `pytest --cov=mento --cov-config=.coveragerc --cov-report=xml`; the 3.12 job
  uploads coverage to Codecov.
- `lint` job: ubuntu-latest, `ruff check .`, `ruff format --check .` and `mypy mento/`
  (no auto-fix in CI).
- `docs` job: ubuntu-latest, installs pandoc via apt, then
  `sphinx-build -b html -W --keep-going` so warnings fail the build.

The lint and docs jobs stay on ubuntu-latest because they are build infrastructure, not
platform coverage — and the docs job installs pandoc with apt. Only the test matrix
describes the platforms mento is verified on.

---

## Common patterns

**Bare object construction (unit-testing methods without __init__):**
```python
obj = object.__new__(MyClass)
obj.some_attr = value
obj.some_method()
```

**Checking coverage for one file:** see *Running tests* above — filter the
`--cov-report=term-missing` output with `grep` (Linux) or `Select-String` (Windows).
