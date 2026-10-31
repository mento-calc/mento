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
```

On Windows, prefix the interpreter path with the call operator: `& "C:\...\python.exe" -m pytest ...`.

> `--override-ini="addopts="` strips the default `--cov` flags from pyproject.toml. Required when running single files or adding custom `--cov` arguments to avoid argument conflicts.

---

## Linting and type checking

```bash
$PY -m ruff check . --fix     # lint, auto-fix
$PY -m ruff format .          # format
$PY -m mypy mento/            # strict type check
```

`make all` runs mypy, ruff and pytest in one go when the tools are on `PATH`.

---

## Tests

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

**Units:** `ureg` (`mento/units.py`) is the shared `UnitRegistry` — do not create additional registries.

Notes for punching (`.claude/rules/punching.md`) and the summaries (`.claude/rules/summaries.md`)
load when you work on those files.

---

## Running mento interactively (design / check from the CLI)

To design or check a real section from a script, use the `design-section` skill. Its folder holds
the full API walkthrough and the gotchas: `.claude/skills/design-section/interactive-usage.md`.

---

## Claude Code setup in this repo

Keep this file under ~2000 words. Anything longer, or only needed for one kind of task,
belongs in `.claude/rules/` (with `paths:` frontmatter, so it loads only for matching files)
or in a skill.

---

## CI

The lint and docs jobs of `.github/workflows/tests.yml` stay on ubuntu-latest because they
are build infrastructure, not platform coverage — and the docs job installs pandoc with apt.
Only the test matrix describes the platforms mento is verified on.
