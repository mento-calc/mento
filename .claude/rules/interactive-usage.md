# Running mento interactively (design / check from the CLI)

Loaded from CLAUDE.md. Read this before writing a script that designs or checks a section
with mento, so the API is used the way the package actually exposes it.

Reports print unicode (≤, ·, ✅, kN·m), so set `PYTHONIOENCODING=utf-8` before running or
the output dies on a codec error.

```powershell
# Windows
$env:PYTHONIOENCODING="utf-8"
& "C:\Users\mihdi\anaconda3\envs\rame-env\python.exe" script.py
```

```bash
# Linux / web session
PYTHONIOENCODING=utf-8 .venv/bin/python script.py
```

### Correct API pattern — RectangularBeam design

```python
from mento import Concrete_ACI_318_19, SteelBar, RectangularBeam, Node, Forces
from mento import MPa, cm, mm, kN, kNm

# 1. Materials
conc  = Concrete_ACI_318_19(name="H25", f_c=25 * MPa)
steel = SteelBar(name="ADN 420", f_y=420 * MPa)

# 2. Section  — use `width` and `height`, NOT `b` and `h`
beam = RectangularBeam(
    label="101", concrete=conc, steel_bar=steel,
    width=20 * cm, height=60 * cm, c_c=25 * mm,
)

# 3. Forces   — V_z for shear, M_y for flexure, N_x for axial
f1 = Forces(label="1.4D",      V_z=80 * kN)
f2 = Forces(label="1.2D+1.6L", M_y=100 * kNm)

# 4. Node     — wraps section + forces; drives design/check
node = Node(section=beam, forces=[f1, f2])
node.design()   # runs flexure + shear design for the governing combination

# 5. Results tables (DataFrame)
node.check_flexure()   # per-combination flexure table
node.check_shear()     # per-combination shear table
node.results           # combined Markdown summary (IPython)
```

### Reading the designed rebar after `node.design()`

Read results through the public dataclasses in `mento/design_results.py`; the `beam._*` attributes are implementation details and their names and units can change.

```python
fd = beam.flexure_design          # FlexureDesign: .bottom / .top are FlexureFaceDesign
fd.bottom.layers                  # tuple of RebarLayer (one per layer)
fd.bottom.A_s, fd.bottom.A_s_req  # provided / required steel area (Quantity)
fd.bottom.A_s_min, fd.bottom.A_s_max, fd.bottom.DCR, fd.bottom.M_capacity

sd = beam.shear_design            # ShearDesign: n_stirrups, d_b, s_l, A_v, ...
sd.n_legs, sd.s_w                 # legs across the shear plane (2 per stirrup) and their spacing across the width
sd.s_max_l, sd.s_max_w            # the limits they are checked against (envelope, tightest)
sd.notation(), sd.arrangement()   # '1 stirrup + 8 legs Ø12 mm @ 14 cm · 15.87 cm between legs (max 20 cm)', the cage in words
beam.section_geometry             # SectionGeometry: leg_x, stirrups, bars; .to_dict("cm") for plain floats
beam.reinforcement                # SectionReinforcement: .bottom / .top / .transverse as plain data
beam.flexure_checks, beam.shear_checks   # per-combination FlexureCheck / ShearCheck tuples
```

Reading a result before `design()` or `check()` has run raises `DesignNotRunError`.

`fd.bottom.A_s_min` is the minimum as §9.6.1.2 writes it; `fd.bottom.A_s_min_eff` is the one the
face has to meet after the 4/3 relief of §9.6.1.3 (ACI / CIRSOC). Compare `A_s` against the second.

A `ShearWall` has no bars or stirrups: read `wall.mesh.horizontal` / `.vertical` (`d_b`, `s`, `rho`),
`wall.shear_design` and `wall.shear_checks` instead.

Alternatives and warnings, after a design or check:

```python
fd.bottom.options                 # RebarOption tuple, best first; options[0] is what was applied
sd.options                        # StirrupOption tuple (n_stirrups, d_b, s_l, s_w, A_v, functional, s_max_l, s_max_w)
node.warnings                     # DesignWarning tuple: .code (stable), .message (set_language), .values
```

`design()` starts from the same state every run, so it is safe to call it repeatedly.
How many options are kept is `BeamSettings(design_options=3)`.

### Displaying results from CLI (not Jupyter)

`node.results` uses `IPython.display.Markdown` — it only renders in Jupyter notebooks. From a terminal it produces nothing useful. Use these instead:

```python
node.shear_results_detailed()    # full shear table: materials, geometry, checks, DCR
node.flexure_results_detailed()  # full flexure table: same
node.check_flexure().to_string() # compact per-combination DataFrame as plain text
node.check_shear().to_string()   # compact per-combination DataFrame as plain text
```

Always set `PYTHONIOENCODING=utf-8` before running to avoid codec errors from ≤, ·, ✅ etc.

### API gotchas to remember

- `RectangularBeam` uses `width`/`height`, **not** `b`/`h`.
- `BeamSettings(unit_system="metric")` is optional — the beam works without it.
- Forces belong to the `Node`: pass them to the constructor or call `node.add_forces()`. The beam has no forces of its own.
- `node.design()` returns `None`; results live on `node` and `beam` attributes.
- Detailed text output: `node.shear_results_detailed()` / `node.flexure_results_detailed()`.
- Export to Word: `node.shear_results_detailed_doc()` / `node.flexure_results_detailed_doc()`.
- `node.check_flexure()` / `node.check_shear()` take no arguments and use the node's forces; the beam-level `beam.check_flexure(forces)` / `beam.check_shear(forces)` require the list.
