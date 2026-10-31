---
paths:
  - "mento/*summary*.py"
  - "mento/summary_*.py"
  - "mento/results.py"
  - "mento/reports/summaries.py"
  - "tests/**/*summary*"
---

# results / summaries

- `Formatter`: formats pint quantities for display.
- `TablePrinter`: renders pandas DataFrames as styled tables (Markdown/IPython).
- `DocumentBuilder`: builds Word (python-docx) report documents.
- `BeamSummary` (`mento/beam_summary.py`; `mento/summary.py` is a deprecated shim), `OneWaySlabSummary` and `ShearWallSummary` read **two tables**: `Sections` (one row per section, key `(Level, Label)`, geometry and **both faces**; beam stirrups as `legs` = 2 per closed stirrup) and `Forces` (`Label, Comb., Nx, Vz, My`). The 1.4.0 single table raises; `split_single_table` converts it.
  - The `Node`s are the only state: `sections_table` / `forces_table` are read off them.
  - Element hooks: `_SPEC`, `_section(key, row)` and its exact inverse `_section_row(section)`, `_validate_section_row`, `_design`, `_rebar_labels`, `_check_record`, `_has_reinforcement`, `_sections_overview`. (#180's `_new_section`, `_set_face`, `_set_transverse`, `_designed` are gone.)
  - `.check()`: one row per section, governing combination per DCR, `Warnings` codes; `Ok?` fails on any warning; frozen `results`.
  - `.design()` is `Node.design()`, writing both faces. `from_excel` / `to_excel` / `tables` / `from_nodes`; `results_detailed_doc(index)` (position or label) in `reports/summaries.py`.
