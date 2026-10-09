Shear Wall Summary
===================

The ``ShearWallSummary`` class lets you work with a list of shear walls and perform
checks, design, and report generation for all of them at once.

Creating Concrete and Steel Materials
--------------------------------------

Define the concrete and steel materials to be used across all walls:

.. code-block:: python

    from mento import Concrete_ACI_318_19, SteelBar, MPa

    conc = Concrete_ACI_318_19(name="H25", f_c=25 * MPa)
    steel = SteelBar(name="ADN 420", f_y=420 * MPa)

Supported design codes: **ACI 318-19**, **CIRSOC 201-25** and **EN 1992-1-1**
(``Concrete_EN_1992_2004``). The input is the same for all three; the tables name
their columns the way the code does.

Loading Input Data from Excel
------------------------------

The wall dimensions, forces, and reinforcement details are typically loaded from
an Excel input file. The file should have a specific format and units:

.. code-block:: python

    import pandas as pd

    input_df = pd.read_excel('Mento-Input.xlsx', sheet_name='Walls', usecols='B:O', skiprows=4)

The Excel file should contain the following columns:

- **Level**: Building level identifier (e.g., Level 1, Level 2).
- **Label**: Wall identifier (e.g., M1, M2).
- **Comb.**: Load combination label.
- **t**: Wall thickness in cm.
- **lw**: Wall in-plane length in m.
- **hw**: Wall height in m — the entire wall from base to top, or the clear height
  of the segment considered (Chapter 2), not the storey height.
- **cc**: Clear cover in mm.
- **Nx**: Axial force in kN.
- **Vz**: Shear force in kN.
- **My**: Moment in kNm.
- **dbh**: Horizontal (transverse) rebar diameter in mm.
- **sh**: Horizontal rebar spacing in cm.
- **dbv**: Vertical rebar diameter in mm.
- **sv**: Vertical rebar spacing in cm.

The units above are the metric ones; the unit row of the file says which apply.
An imperial wall (a concrete defined in psi) takes lengths in ``in`` (or ``inch``)
and ``ft``, forces in ``kip`` and moments in ``kipft``, and ``check()`` writes its
table in the same system: t in in, lw and hw in ft, the mesh in in (``Ø0.5/8`` is
#4 @ 8 in) and the forces in kip.

Grouping Logic
~~~~~~~~~~~~~~

Multiple rows with the same **(Level, Label)** combination represent different load
combinations for the same wall. The summary groups them automatically: one wall object
is created per unique (Level, Label) pair, and all force rows are attached to it.

All rows in a group must have identical geometry (t, lw, hw, cc). A ``ValueError``
is raised if geometry differs within a group. The mesh may be given on one row of
the wall only; rows that give a direction of it must give the same one, or a
``ValueError`` names the wall. A row with no label is a wall of its own.
``BeamSummary`` and ``OneWaySlabSummary`` group their rows the same way, by label.

For a quick test you can build the DataFrame manually:

.. code-block:: python

    data = {
        "Level": ["", "Level 1", "Level 1", "Level 1", "Level 2", "Level 2"],
        "Label": ["", "M1", "M1", "M1", "M1", "M1"],
        "Comb.": ["", "ELU 1", "ELU 2", "ELU 3", "ELU 1", "ELU 2"],
        "t": ["cm", 20, 20, 20, 20, 20],
        "lw": ["m", 3.0, 3.0, 3.0, 3.0, 3.0],
        "hw": ["m", 3.0, 3.0, 3.0, 3.0, 3.0],
        "cc": ["mm", 25, 25, 25, 25, 25],
        "Nx": ["kN", 0, 0, -301, -150, 55.5],
        "Vz": ["kN", 264, 138, 152, 32.3, 163],
        "My": ["kNm", -172, -90, -234, 143, -278],
        "dbh": ["mm", 8, 8, 8, 8, 8],
        "sh": ["cm", 20, 20, 20, 20, 20],
        "dbv": ["mm", 12, 12, 12, 12, 12],
        "sv": ["cm", 15, 15, 15, 15, 15],
    }
    input_df = pd.DataFrame(data)

Creating the ShearWallSummary Object
--------------------------------------

Once the input data is ready, create a ``ShearWallSummary`` object:

.. code-block:: python

    from mento import ShearWallSummary

    wall_summary = ShearWallSummary(concrete=conc, steel_bar=steel, wall_list=input_df)

To verify that units were applied correctly, inspect the ``data`` attribute:

.. code-block:: python

    wall_summary.data

The number of unique walls (nodes) and their keys can be inspected:

.. code-block:: python

    len(wall_summary.nodes)   # Number of unique walls
    wall_summary.wall_keys    # List of (Level, Label) tuples

Checking Wall Capacity
-----------------------

Use ``check()`` to get a summary table with DCR (Demand-Capacity Ratio) values for
all walls. The worst-case load combination is reported for each wall:

.. code-block:: python

    wall_summary.check()

The result is a DataFrame with columns: Level, Label, t, lw, hw, horizontal rebar,
vertical rebar, reinforcement ratios, worst-case shear, capacity, DCR, and a
pass/fail status (✅ / ❌). Under ACI 318-19 and CIRSOC 201-25 the ratios, shear and
capacity are ``ρt``, ``ρl``, ``Vu,max`` and ``ØVn``; under EN 1992-1-1 they are
``ρh``, ``ρv``, ``VEd,max`` and ``VRd``. The status spans **every** combination of
the wall, not only the governing one: it is ✅ when each combination is carried
(DCR ≤ 1) and the mesh misses none of the limits ``wall.warnings`` reports —
the ratios of §11.6.2, the spacing of §11.7 and the section limit of
§11.5.4.2 (ACI 318-19 / CIRSOC 201-25), or the areas of §9.6.2 and §9.6.3, their
spacing and V_Rd,max of Eq. (6.9) (EN 1992-1-1). ``ρl,min`` of ACI in particular
changes with the shear of each combination.

.. note::

    All walls must have rebar assigned before calling ``check()``. If any wall has
    no rebar (dbh/sh/dbv/sv all zero), a ``ValueError`` is raised with a suggestion
    to either run ``design()`` first or provide rebar in the input.

Viewing Detailed Results
-------------------------

For a full breakdown per wall (all load combinations) use ``shear_results()``.
It accepts an optional ``index`` (1-based) to retrieve results for a single wall:

.. code-block:: python

    # All walls — all load combinations
    wall_summary.shear_results()

    # Single wall (1-based index)
    wall_summary.shear_results(index=2)

For step-by-step detail of a specific wall you can also access the node directly:

.. code-block:: python

    wall_summary.nodes[0].shear_results_detailed()

Designing Reinforcement
------------------------

``design()`` runs automatic shear design for every wall and returns a
DataFrame with the filled rebar columns (``dbh``, ``sh``, ``dbv``, ``sv``):

.. code-block:: python

    designed_df = wall_summary.design()

The design selects horizontal and vertical mesh for the worst-case load combination
across all forces assigned to each wall.

Exporting and Importing a Design
----------------------------------

After running ``design()``, save the result to Excel so it can be reviewed or edited:

.. code-block:: python

    wall_summary.export_design("WallDesign.xlsx")

To reload an edited file and rebuild the summary with the new reinforcement:

.. code-block:: python

    wall_summary.import_design("WallDesign.xlsx")

Exporting Results to Excel
----------------------------

The DataFrames returned by ``check()`` and ``shear_results()`` can be written to
Excel directly:

.. code-block:: python

    wall_summary.check().to_excel("wall_results.xlsx", index=False)

Detailed Word Report
---------------------

``results_detailed_doc()`` generates a Word document (``.docx``) that contains:

- Full shear detail for one selected wall (materials, geometry, forces, limit checks, capacity).
- Summary tables (wall data, shear results, DCR check) for all walls.

The document is saved to the current working directory with the name
``Shear_Wall_Summary_{design_code}.docx``.

.. code-block:: python

    # Detailed report with wall 1 as the reference (default)
    wall_summary.results_detailed_doc()

    # Use wall 3 as the reference
    wall_summary.results_detailed_doc(index=3)

The ``index`` parameter is 1-based and must be within the range of walls in the
summary. An ``IndexError`` is raised for out-of-range values.
