Shear Wall Summary
===================

The ``ShearWallSummary`` class checks and designs the in-plane shear of a list of
walls at once. Like :doc:`beam_summary`, it reads a **sections** table — one row per
wall — and a **forces** table — one row per load combination of a wall.

Creating Concrete and Steel Materials
--------------------------------------

Define the concrete and steel materials to be used across all walls:

.. code-block:: python

    from mento import Concrete_ACI_318_19, SteelBar, MPa

    conc = Concrete_ACI_318_19(name="H25", f_c=25 * MPa)
    steel = SteelBar(name="ADN 420", f_y=420 * MPa)

Supported design codes: **ACI 318-19** and **CIRSOC 201-25**.

Sections and Forces
-------------------

A wall is identified by its **(Level, Label)** pair: ``M1`` on ``Level 1`` and ``M1`` on
``Level 2`` are two walls. ``Level`` may be left empty; ``Label`` may not.

**Sections** — one row per wall, the pair given once:

- **Level**, **Label**: the wall.
- **t**: thickness. **lw**: in-plane length. **hw**: height — the entire wall from base
  to top, or the clear height of the segment considered (Chapter 2), not the storey
  height. **cc**: clear cover.
- **dbh**, **sh**: the horizontal mesh, bar and spacing **on each face** (two curtains).
- **dbv**, **sv**: the vertical mesh, the same.
- **Notes** (optional): free text, kept and not read.

A direction of the mesh is a bar **and** a spacing: one without the other is an error
that names the wall. Leave the four mesh columns at zero, or out, to design the mesh.

**Forces** — one row per combination: **Level**, **Label**, **Comb.**, **Nx**
(optional), **Vz**, **My** (optional), **Notes** (optional). The summary checks the
in-plane shear only: ``Vz`` is that shear, in magnitude, and ``Nx > 0`` is compression
(a tension lowers αc, ACI 318-19 §11.5.4.3). ``My`` is accepted, so a row exported from a
model can be pasted whole, and written back, but **not used**: P-M and boundary elements
are not checked here.

Units: lengths in ``cm``, ``m``, ``mm``, ``in`` or ``ft``; forces in ``kN`` or ``kip``;
moments in ``kNm`` or ``kip·ft``. Each table carries its units in its first row, and the
mesh keeps them through a design and an export: a mesh in mm/mm reads back in mm/mm.

.. csv-table:: Sections
   :header: "Level", "Label", "t", "lw", "hw", "cc", "dbh", "sh", "dbv", "sv"

   "", "", "cm", "m", "m", "mm", "mm", "cm", "mm", "cm"
   "Level 1", "M1", 20, 3.0, 3.0, 25, 8, 20, 12, 15
   "Level 2", "M1", 20, 3.0, 3.0, 25, 8, 20, 12, 15

.. csv-table:: Forces
   :header: "Level", "Label", "Comb.", "Nx", "Vz", "My"

   "", "", "", "kN", "kN", "kNm"
   "Level 1", "M1", "ELU 1", 0, 264, -172
   "Level 1", "M1", "ELU 2", -301, 152, -234
   "Level 2", "M1", "ELU 1", -150, 32.3, 143
   "Level 2", "M1", "ELU 2", 55.5, 163, -278

.. code-block:: python

    import pandas as pd
    from mento import ShearWallSummary

    sections = pd.DataFrame(
        {
            "Level": ["", "Level 1", "Level 2"],
            "Label": ["", "M1", "M1"],
            "t": ["cm", 20, 20],
            "lw": ["m", 3.0, 3.0],
            "hw": ["m", 3.0, 3.0],
            "cc": ["mm", 25, 25],
            "dbh": ["mm", 8, 8],
            "sh": ["cm", 20, 20],
            "dbv": ["mm", 12, 12],
            "sv": ["cm", 15, 15],
        }
    )
    forces = pd.DataFrame(
        {
            "Level": ["", "Level 1", "Level 1", "Level 2", "Level 2"],
            "Label": ["", "M1", "M1", "M1", "M1"],
            "Comb.": ["", "ELU 1", "ELU 2", "ELU 1", "ELU 2"],
            "Nx": ["kN", 0, -301, -150, 55.5],
            "Vz": ["kN", 264, 152, 32.3, 163],
            "My": ["kNm", -172, -234, 143, -278],
        }
    )
    wall_summary = ShearWallSummary(conc, steel, sections, forces)

    len(wall_summary.nodes)   # one node per wall
    wall_summary.labels       # [("Level 1", "M1"), ("Level 2", "M1")]

``ShearWallSummary.from_excel(conc, steel, path)`` reads the sheets ``Sections`` and
``Forces``; ``to_excel(path)`` writes them; ``from_nodes(conc, steel, nodes)`` writes the
tables of walls built by hand, taking each wall's ``level``. A table in the single-table
format of mento 1.4.0 raises ``SummaryInputError``; convert it with
``mento.split_single_table(table, "wall")``, which keeps one section per (Level, Label)
with the geometry and mesh of its first row and every row as a combination.

An imperial wall (a concrete defined in psi) takes lengths in ``in`` and ``ft``, forces in
``kip`` and moments in ``kip·ft``, and ``check()`` writes its table in the same system: t
in in, lw and hw in ft, the mesh as ASTM bars (``#4@8``) and the forces in kip.

Checking Walls
--------------

``check()`` gives one row per wall:

.. code-block:: python

    wall_summary.check()

- ``t``, ``lw``, ``hw``, ``Horiz. (each face)``, ``Vert. (each face)``, ``ρt``, ``ρl``:
  the wall and its mesh.
- ``Comb.``, ``Vu``, ``Nu``, ``ØVn``, ``DCR``: the combination with the largest DCR —
  which, with a tension in another combination, need not be the largest shear — its
  shear, axial load and capacity. Every combination tied at that DCR is named.
- ``Warnings``: mento's warning codes with the direction they are read in, e.g.
  ``mesh_ratio_below_min (v)``.
- ``Status``: ✅ when every combination is carried (DCR ≤ 1) **and** the mesh misses none of
  the limits ``wall.warnings`` reports — the ratios of §11.6.2, the spacing of §11.7 and the
  section limit of §11.5.4.2, over every combination: ``ρl,min`` in particular changes
  with the shear of each one. A wall with no mesh reads "no reinforcement: run design()"
  and one with no forces "no forces"; neither stops the check of the others.

``wall_summary.results`` holds the same as data, one
:class:`~mento.summary_base.SectionVerdict` per wall.

Viewing Detailed Results
-------------------------

``shear_results()`` gives every combination; ``index`` picks one wall, by its 1-based
position in the sections table, its label or its ``(Level, Label)``:

.. code-block:: python

    wall_summary.shear_results()
    wall_summary.shear_results(index=("Level 2", "M1"))
    wall_summary.nodes[0].shear_results_detailed()

Designing Reinforcement
------------------------

``design()`` runs ``node.design()`` on every wall with forces, writes the mesh into the
sections table in the units of its columns, checks the walls and returns the sections
table:

.. code-block:: python

    designed = wall_summary.design()

The mesh designed is the shear minimum of §11.6.2 and the shear demand of §11.5, for the
worst combination of each wall — not what P-M or a boundary element would ask.

Exporting and Importing a Design
----------------------------------

.. code-block:: python

    wall_summary.export_design("WallDesign.xlsx")
    # ... edit the mesh in the Sections sheet ...
    wall_summary.import_design("WallDesign.xlsx")
    wall_summary.check()

The DataFrames returned by ``check()`` and ``shear_results()`` can be written to Excel
directly with ``to_excel``.

Detailed Word Report
---------------------

``results_detailed_doc()`` generates a Word document (``.docx``) that contains:

- Full shear detail for one selected wall (materials, geometry, forces, limit checks,
  capacity).
- The tables of all walls: the sections, the forces (``My`` is not used), the shear
  results per combination, the check, and every warning worded in full.

The document is saved to the current working directory with the name
``Shear_Wall_Summary_{design_code}.docx``.

.. code-block:: python

    wall_summary.results_detailed_doc()               # wall 1
    wall_summary.results_detailed_doc(index=("Level 2", "M1"))

``index`` is the wall's 1-based position in the sections table, its label or its
``(Level, Label)``. An ``IndexError`` is raised for a position out of range.
