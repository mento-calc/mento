---
name: design-section
description: Design or check a concrete section with mento from a script — beam, one-way slab, footing, shear wall or punching node. Use when asked to size reinforcement, verify a section against forces, get a DCR, or produce a detailed flexure/shear report for a real case, rather than to change library code.
---

# Designing or checking a section with mento

This is for *using* mento on an engineering case. For changing the library itself, follow
CLAUDE.md instead.

## 1. Pick the interpreter

- Windows: `C:\Users\mihdi\anaconda3\envs\rame-env\python.exe`
- Linux / web session: `.venv/bin/python` (run `bash .claude/hooks/session-start.sh` first if missing)

Always set `PYTHONIOENCODING=utf-8`; the reports print `≤`, `·` and `✅`.

## 2. Write a script, do not use `-c`

Put the case in a file under the scratchpad directory, not in the repository, and run it.
A one-liner with `-c` breaks on quoting as soon as the case has more than two forces.

## 3. Build the case

The full API walkthrough is in `.claude/skills/design-section/interactive-usage.md` — read it before
writing the script. The shape is always the same:

1. Materials: a concrete class per design code, plus `SteelBar`.
2. Section: `RectangularBeam` / `OneWaySlab` / `Footing` / `ShearWall` / `PunchingSlab`.
   `RectangularBeam` takes `width` and `height`, never `b` and `h`.
3. Forces: `Forces(label=..., N_x=, V_z=, M_y=, M_x=)`. `V_z` is shear, `M_y` flexure.
4. `Node(section=..., forces=[...])`, then `node.design()` or `node.check()`.

Units come from `mento` directly: `from mento import MPa, cm, mm, kN, kNm`. The unit system
(metric vs imperial) is inferred from the units of `f_c` — never hard-code an assumption.

## 4. Report back

Print with `node.flexure_results_detailed()` and `node.shear_results_detailed()`, or
`node.check_flexure().to_string()` for the compact table. `node.results` renders only in
Jupyter and produces nothing in a terminal.

In the final answer give the engineer what they asked for: the chosen bars, the governing
combination, and the DCR. Say plainly if any DCR exceeds 1.0 — a failing section reported
as a success is the worst outcome of this skill.

## 5. Sanity-check before reporting

- Do the bars fit the width? `A_s` provided should be close above `A_s_req`, not triple it.
- Is the governing combination the one you would expect by hand?
- Did `design()` actually run? Reading a result before it does raises `DesignNotRunError`.
