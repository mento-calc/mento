# Column shear — module roadmap

Status: **accepted** (2026-10-24), with decisions D1–D7 of §6 taken by the owner the same
day. Phases A to D done the same day, except B's published example (see Phase B).
Origin: the five requests mako's column shear (C12) left
for mento, collected in mako issue
[#117](https://github.com/mihdicaballero/mako/issues/117).

Companion documents: [`ROADMAP.md`](ROADMAP.md), [`punching-roadmap.md`](punching-roadmap.md)
and [`adr/`](adr/) — in particular ADR-0001 (results as values), ADR-0002 (hybrid code
layer) and ADR-0005 (float equations, pint at the boundary).

---

## 0. The question: a column element now, or more modes on the beam?

mako checks the shear of each column direction as a `RectangularBeam` with the axial load
of the combination. That works for a rectangle in compression, and it is what left five
gaps:

| # | What mako asks | Fits `RectangularBeam`? |
| --- | --- | --- |
| 1 ([#206](https://github.com/mento-calc/mento/issues/206)) | A circular section for shear (A_g = π·D²/4, b_w = D, d = 0.8·D, ACI 318-19 §22.5.2.2), so a circle in tension can be checked | **No.** `RectangularSection`, `SectionFloats`, `section_geometry`, the cage model and the reports all assume a rectangle |
| 2 ([#207](https://github.com/mento-calc/mento/issues/207)) | The column's clauses: A_v,min where V_u > 0.5·φ·V_c (ACI §10.6.2.1, with the axial load, with no shallow-member exemption); no beam minimum of EN §9.2.2(5) (§9.5.3 governs); or at least V_c / V_Rd,c in `ShearCheck` | Only as a fourth `mode` next to `"beam"`, `"slab"` and `"shear_wall"`, threaded through every `_stirrups_optional`-style branch |
| 3 ([#208](https://github.com/mento-calc/mento/issues/208)) | Legs of two diameters: the perimeter tie, plus thinner crossties | **No.** `set_transverse_rebar` takes one `d_b`, and `leg_count`, `leg_seats`, `section_geometry`, compression support and the stirrup search all build on it |
| 4 ([#209](https://github.com/mento-calc/mento/issues/209)) | A values path with no warnings: `shear_check_results` spends ~60 % of its time in `shear_warnings` | Yes, and it helps every caller |
| 5 ([#210](https://github.com/mento-calc/mento/issues/210)) | α_cw of EN 1992-1-1 Expression (6.11aN) under compression | Yes: it is a code question, not an element question |

Two of the five (4 and 5) belong to the shear check whatever the element. The other three
(1, 2, 3) describe a column, and fitting them into `RectangularBeam` means a circle inside
a rectangle class, a fourth mode on a mutable element and a two-diameter cage that the
beam's detailing does not model. `ShearWall` shows what subclassing the beam costs: it
overrides ~20 members only to make them raise `NotABeamError`.

**Decision: yes, create the column element now, for shear only.**

- The float equations are already section-agnostic. ACI's `concrete_shear_stress`,
  `axial_stress_influence`, `min_shear_reinforcement_ratio` and `max_stirrup_spacing`, and
  EN's `shear_resistance_without_reinforcement`, `max_shear_resistance` and `axial_stress`
  take A_g, b_w and d as floats. A circle needs no new physics, only a new place that
  assembles them.
- It can be the first element built to the target of `ROADMAP.md` §3.3: a stateless
  checker that returns frozen results. It does not write private attributes or reuse the
  `self: RectangularBeam` hooks. Ask 4 then comes free for columns.
- mento will need its own sectional engine for columns (P–M). That engine reads the same
  thing the shear check reads: the shape, the bars with their positions and the ties.
  Fixing that model now, with shear as its only consumer, costs little. It also gives mako
  and mento one shared description of a column section from the start.
- The P–M engine is **not** part of this roadmap. mako keeps its own until mento has one.
  On the column element, `check_flexure` raises `NotImplementedError` and points here, as
  the punching `design()` does today.

The costs: the shear check of each code gets assembled a second time, about 150 lines per
code, beside the beam's. §6 prevents drift with an equivalence test against
`RectangularBeam`. There is also a naming clash with the punching `Column` (D1).

---

## 1. What exists today

- `mento/column.py` — `Column(shape, position, b, h, edge distances)`: geometry for
  **punching** only (where the column stands in the slab). It is not a section.
- `Forces` already carries `N_x, V_y, V_z, M_x, M_y, M_z`; a column reads `V_y` and `V_z`.
- `Node(section, forces)` accepts any `Section`, not only beams.
- The registry (`codes/registry.py`) already holds element-specific optional hooks
  (`check_shear_wall`, `check_punching`), which is the slot a column hook takes.
- ACI's negative N_u (tension) already flows through `axial_stress_influence`, and EN's
  through `axial_stress`. Note 2 of Table 22.5.5.1 (V_c ≥ 0) and the `max(0, …)` of
  V_Rd,c are already applied by the callers.

---

## 2. The model

### 2.1 Elements

Two `Section` subclasses (not `RectangularBeam`), each a dataclass:

```python
RectangularColumn(label, concrete, steel_bar, width, height, c_c)   # width along y, height along z
CircularColumn(label, concrete, steel_bar, diameter, c_c)
```

`V_z` acts across `height` (b_w = width, d from height). `V_y` acts across `width`
(b_w = height, d from width). These are the local axes of `docs/source/user_guide/local_axes.rst`.

### 2.2 Longitudinal bars (needed for ρ_w and d, and later for P–M)

```python
col.set_longitudinal_rebar(d_b_corner=20*mm, n_y=2, d_b_y=16*mm, n_z=1, d_b_z=16*mm)
#   n_y bars between corners on each face parallel to y (faces of length width), n_z on each face parallel to z
circ.set_longitudinal_rebar(n=8, d_b=20*mm)
```

### 2.3 Ties — legs of two diameters (ask 3)

```python
col.set_ties(d_b=10*mm, s=15*cm, crossties_y=1, crossties_z=2, d_b_crosstie=8*mm)
circ.set_hoops(d_b=10*mm, s=15*cm, spiral=False)
```

The area per length in each direction is A_v,z / s = (2·A(d_b) + crossties_z·A(d_b_crosstie)) / s,
and the same for y. A crosstie thinner than the tie counts as a leg. Whether it is thick
enough to brace its bar is a detailing rule (§4.3), not a shear one. A hoop counts as two
legs, the usual reading of ACI 318-19 §22.5.8.5 for circular ties (clause to quote exactly
when implemented).

### 2.4 Effective depth and ρ_w

- Rectangle: d per direction = the centroid of the bars on the face far from the compressed
  one, as `RectangularBeam` reads it, so the equivalence test of §6 holds exactly. mako's
  plan records an owner's decision (2026-10-05) of d **to the extreme bar** (D2).
- Circle: d = 0.8·D and b_w = D (ACI 318-19 §22.5.2.2). The A_s of ρ_w = the bars past the
  centre line (⌊(n − 1)/2⌋, as mako takes them) (D5).

---

## 3. Results and the values path (ask 4)

```python
col.shear_check_results(forces) -> tuple[ColumnShearCheck, ...]   # one per (combination, direction)
```

```python
@dataclass(frozen=True)
class ColumnShearCheck:
    label: str
    direction: Literal["y", "z"]
    N_demand: Quantity              # positive in compression
    V_demand: Quantity
    V_concrete: Quantity            # φ·V_c (ACI/CIRSOC) or V_Rd,c (EN), with the axial load
    reinforcement_required: bool    # V_u > 0.5·φ·V_c (ACI §10.6.2.1) / V_Ed > V_Rd,c (EN §6.2.1(3))
    A_v: Quantity                   # provided in this direction
    A_v_req: Quantity               # 0 where not required
    A_v_min: Quantity               # Table 10.6.2.2 where required (ACI); 0 under EN
    V_capacity: Quantity
    DCR: float
    s_max_l: Optional[Quantity]     # where reinforcement is required
    s_max_w: Optional[Quantity]
    spacing_halved: Optional[bool]
```

Warnings are **not** computed on this path. `col.warnings` builds them from the stored
results on first read. The results are dropped on any change to the section, so a late
read always describes the section as it is.

`Node(col, forces).check()` / `.design()` run shear. `check_flexure` / `design_flexure`
raise `NotImplementedError` pointing to this document.

---

## 4. The clauses

### 4.1 ACI 318-19 / CIRSOC 201-25

| Step | Clause | Equation used |
| --- | --- | --- |
| V_c with N_u (compression and tension) | Table 22.5.5.1, §22.5.5.1.1–3 | existing `concrete_shear_stress`, `axial_stress_influence`, `size_effect_factor` |
| Circular b_w, d | §22.5.2.2 | new data, no new equation |
| Whether shear reinforcement is required | **§10.6.2.1**: V_u > 0.5·φ·V_c | **new** `column_shear_reinforcement_threshold` (one line) |
| A_v,min | §10.6.2.2 (Table 10.6.2.2 = Table 9.6.3.4) | existing `min_shear_reinforcement_ratio` |
| V_s, section limit | §22.5.8.5.3, §22.5.1.2 | existing |
| Spacing for shear | Table 10.7.6.5.2 (= Table 9.7.6.2.2) | existing `max_stirrup_spacing` with the registry caps |

### 4.2 EN 1992-1-1

| Step | Clause | Equation used |
| --- | --- | --- |
| V_Rd,c with σ_cp ≤ 0.2·f_cd | §6.2.2(1) | existing |
| Whether shear reinforcement is required | §6.2.1(3): V_Ed > V_Rd,c | existing comparison; **no** §9.2.2(5) minimum (a column is §9.5.3) |
| V_Rd,s, V_Rd,max | §6.2.3, Expressions (6.8), (6.9) | existing |
| α_cw under compression (ask 5) | Expression (6.11aN) | **new** `compression_chord_coefficient(sigma_cp, f_cd)`; whether to apply it is D4 |
| Spacing for shear | §9.2.2(6), (8) where required (mako's reading today) | existing |
| Circular section | **no clause**: Orr et al. (2010), D3 | **new**, transcribed from the paper: λ1, λ2, B_w, Expression (6.4) for a circle |

### 4.3 Detailing (later phase, as warnings, not part of shear)

ACI 318-19 §25.7.2 (tie spacing 16·d_b / 48·d_b / least dimension, tie size, every corner
and alternate bar supported, 150 mm clear) and EN 1992-1-1 §9.5.3 (s_cl,tmax, the 0.6
factor). mako already computes these (`TieDetailing`). They move to mento when the P–M
engine does, or earlier if a standalone user needs them.

---

## 5. Phases

Each phase lands on green tests, in its own PR from `main`.

**Phase A — the two asks that belong to the beam check (small, independent).**
- A1. Lazy shear warnings in `RectangularBeam.shear_check_results`: keep the states and
  build `shear_warnings` on the first read of `warnings`. Exit: the same warnings as today
  on the whole suite, and a measured gain on a mako-sized loop (target: ≥ 2× on
  `shear_check_results`).
- A2. `ShearCheck.V_concrete` (φ·V_c / V_Rd,c of the combination). Exit: hand values on the
  existing ACI and EN examples.
- Both help mako's beams too, and A2 removes mako's bare re-check before Phase B lands.
- *Done (2026-10-24).* A1: the warnings are worded on the first read of `warnings`, with
  the compression faces of the moment of the check. A 30x50 beam, 10 combinations, goes
  from 1,060 to 250 µs per check (ACI) and from 660 to 220 µs (EN). A2:
  `ShearCheck.V_concrete`, checked by hand in compression and in tension under both codes.

**Phase B — `RectangularColumn` and `CircularColumn`, ACI 318-19 / CIRSOC 201-25 shear.**
- The model of §2, `codes/aci_318_19/` checker for columns (float in, state out), the
  registry hook `check_column_shear`, `ColumnShearCheck`, the lazy warnings, `Node`.
- Exit:
  - **Equivalence**: a rectangular column with no crossties and N = 0 gives the V_c, A_v,req,
    DCR and spacings of the same `RectangularBeam` to 10⁻⁹. Only the clauses that differ on
    purpose (§10.6.2.1 against §9.6.3.1) are tested apart.
  - Hand calculations: compression, tension, a circle in tension, two-diameter legs.
  - A published example in `tests/validation/` (candidates: the column shear examples in
    Wight & MacGregor or ACI SP-17).
  - The architecture tests (`equations/` float-only, registry dispatch) unchanged and green.
- *Done (2026-10-24), but for the published example.* `mento/column_section.py`
  (`RectangularColumn`, `CircularColumn`, `ColumnShearSection`), `mento/column_results.py`
  (`ColumnShearCheck`), `mento/codes/ACI_318_19_column.py`, the hook `check_column_shear`
  and `column_shear_reinforcement_threshold` (§10.6.2.1) in the equations. The
  equivalence holds to 10⁻⁹ against `RectangularBeam` in both directions, under ACI and
  CIRSOC, with N in compression, zero and tension, with ties and bare
  (`tests/elements/test_column.py`). Hand calculations cover a compressed rectangle with
  a thinner crosstie, the §10.6.2.1 threshold against the beam's, a circle in tension, the
  √f'c cap a column keeps, the CIRSOC caps, the legs across and US customary units. A
  check costs ~170 µs per direction. **Still open: the published example.** It needs a
  worked example from a source on paper (Wight & MacGregor, ACI SP-17); it goes to
  `tests/validation/` once one is transcribed.
- Two decisions taken while building it:
  - The crossties are named after the faces whose bars they hold, as mako names them:
    `crossties_width` hold bars of the faces of length `width` and carry `V_z`.
  - The moments of a combination are reported as unread
    (`column_force_component_not_checked`). A column checked only for shear does not
    verify them, and a DCR below 1 must not read as if it did.

**Phase C — EN 1992-1-1 shear for both shapes.**
- The same checker for EN, α_cw per D4, the circle by Orr et al. (D3).
- Exit: hand calculations, a published example for the rectangle, and for the circle the
  worked example of Orr et al.
- *Done (2026-10-24).* `mento/codes/EN_1992_2004_column.py`, registered as the EN
  `check_column_shear`; the equations `compression_chord_coefficient` (6.11aN),
  `design_tensile_strength`, `uncracked_shear_resistance_circle`, `circle_flexural_tension`,
  `circular_link_efficiency`, `spiral_efficiency` and `circular_equivalent_web_width`;
  `alpha_cw_from_axial_load`, `CircularColumn.set_lever_arm(d, z)` and
  `set_hoops(..., spiral=True)`. The rectangle gives the EN beam's numbers to 10⁻⁹ in
  compression, without axial load and in tension, with ties and bare.
- What the exit criteria asked and what there is:
  - Orr et al. publish no worked example. They report predictions against tests, from a
    sectional analysis whose inputs (cover, link yield) are not all in the paper.
    `tests/validation/test_column_shear_validated.py` holds the two numbers the paper does
    print: λ1 = 0.85 for z = 0.8·D, r_sv = 0.45·D (Eq. (7); Eq. (6) gives 0.8450) and
    λ2 = 1 at zero pitch.
  - The rectangle's published example is still open, as in Phase B.
- Three decisions taken while building it (owner, 2026-10-24):
  - **d and z of a circle.** Orr et al. take them from a sectional analysis of each
    combination, which mento does not have yet. By default the neutral axis is at the
    centre (d = r + 2·r_s/π) and z = 0.77·d, the mean they found over 38 of Clarke's
    tests. `set_lever_arm(d, z)` takes the values of an analysis, such as mako's.
  - **V_Rd,c of a circle follows §6.2.2(2).** Orr's Eq. (17) is Expression (6.4),
    which applies only where the section is uncracked in bending. On a cracked Ø50 with
    no axial load it gave 199 kN, against 96 kN from Expression (6.2.a). mento reads the
    combination's moments: (6.4) where M/W − N/A_c ≤ f_ctd, otherwise (6.2.a)/(6.2.b) on
    the equivalent rectangle (B_w, d).
  - **λ1 is capped at 0.85.** Orr recommend Eq. (6) over the 0.85 of Eq. (7), but note
    λ1 ≤ 0.85 on the sections they analysed. With the default d, Eq. (6) gives about
    0.91, so mento takes the smaller of the two.

**Phase D — reports.** `shear_results_detailed` / `_doc` for a column through `reports/`, in
both languages.
- *Done (2026-10-24).* `mento/reports/columns.py` builds the tables from the
  `ColumnShearCheck` results and the column's inputs, with no state written to the element
  (ADR-0004), and the element imports it only when a report is asked for. The symbols are
  per code (`DesignCode.column_shear_symbols`). The results carry no intermediate values
  (ρ_w, λ_s, σ, θ, λ1), so the report shows the resistances and the limits, not each step
  to them. Adding those intermediates to `ColumnShearCheck` would cost every check, so it
  waits for someone to ask for them.

**Phase E — tie design and detailing (optional; see D6).** `design()` returns the lightest
tie set that satisfies shear and §4.3. mako's D28/D29 search is the reference.

**mako adoption** (after B, then C): `mako/columns/_shear.py` drops `beam_of`, `_mento_beam`,
the probe row (`_PROBE_SHEAR`) and the bare re-check, and calls the column. The `front()`
pruning and the pier logic stay in mako. Each request closed in mento comes out of
`docs/columnas/teoria.md`, as #117 asks.

---

## 6. Decisions (owner, 2026-10-24)

| | Decision | Taken |
| --- | --- | --- |
| D1 | Name, given the punching `Column` | `RectangularColumn` / `CircularColumn`, after `RectangularBeam`. The punching `Column` keeps its name. Merging the two later is its own question |
| D2 | d of a rectangle: the far face's centroid or the extreme bar | The centroid, as the beam reads it: it keeps the equivalence test exact and is the clause's definition of d. The extreme bar can come as an option if mako needs it |
| D3 | EN circular section: EN 1992-1-1 gives no rule | **Orr et al. (2010)**, the EC2 variable-angle truss extended to circular sections (*The Structural Engineer*), validated against its worked example. The alternatives weighed were Clarke & Birjandi (1993, an equivalent breadth) and Feltham (2004, *The Structural Engineer* 82(11), a factor for curved links) |
| D4 | α_cw (6.11aN) for a non-prestressed member under axial compression | The recommended note gives "1 for non-prestressed structures", and σ_cp in it is "due to the design axial force". **Decided (#210):** the column takes (6.11aN) with N_Ed/A_c of each combination by default. α_cw = 1 is not the safe side past 0.6·f_cd, where the expression drops below 1. `alpha_cw_from_axial_load=False` keeps 1. The beam keeps α_cw = 1 |
| D5 | Bars of a circle that count in ρ_w | Those past the centre line, as mako does |
| D6 | Does tie design live in mento or stay in mako? | Check in mento (B, C). The design stays in mako until the P–M engine moves the detailing over |
| D7 | Issues in mento-calc/mento | One tracking issue with the five requests as sub-issues linked to this document. That meets the "done when" of mako #117. **Opened 2026-10-24:** [#211](https://github.com/mento-calc/mento/issues/211), with [#206](https://github.com/mento-calc/mento/issues/206) (circle), [#207](https://github.com/mento-calc/mento/issues/207) (column clauses, V_c), [#208](https://github.com/mento-calc/mento/issues/208) (legs of two diameters), [#209](https://github.com/mento-calc/mento/issues/209) (values without warnings) and [#210](https://github.com/mento-calc/mento/issues/210) (α_cw). #206–#209 are resolved by this branch; #210 stays open on D4 |

---

## 7. What this roadmap does not do

- No P–M interaction and no slenderness: a separate roadmap, on the model of §2.
- No column mode on `RectangularBeam`, and no `RectangularBeam` subclass.
- No capacity design (V_e from M_pr) and no torsion: mako's C9 open question stays open.
