---
paths:
  - "mento/punching*.py"
  - "mento/column.py"
  - "mento/codes/**/*punching*"
  - "mento/reports/punching.py"
  - "mento/plots/punching.py"
  - "tests/**/*punching*"
  - "docs/architecture/punching-roadmap.md"
---

# punching

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
