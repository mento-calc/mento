One-Way Slab Summary
====================

The ``OneWaySlabSummary`` class does for a list of one-way slab strips what
:doc:`beam_summary` does for beams: it reads a **sections** table and a **forces**
table, checks the strips, designs their reinforcement and writes the design back to
Excel. The rules of the two tables — the unit row, labels, ``Level`` and ``Notes``,
errors and warnings — are those of the beam summary.

Sections
--------

One row per strip, each face a bar diameter and a spacing per layer, and no stirrups:

- **Level** (optional) and **Label**: the strip's name, unique.
- **b**: width of the strip (100 cm for a metre of slab; every result is for the strip).
- **h**: slab thickness. **cc**: clear cover.
- **db1_top, s1_top**: the top layer nearest the face, its diameter and its spacing.
- **db3_top, s3_top**: an optional second top layer, **inside** the first: position 3 of
  :meth:`~mento.slab.OneWaySlab.set_slab_longitudinal_rebar_top`, at a smaller effective
  depth — not bars laid between those of the first layer.
- **db1_bot, s1_bot, db3_bot, s3_bot**: the same at the bottom.
- **Notes** (optional).

A zero is no bars. A layer is a diameter **and** a spacing: one without the
other is an error that names the strip. Layer positions
are retained even when only the second layer is supplied. A strip is detailed
without stirrups, so a sections table with ``legs``, ``dbs`` or ``sl`` is an error, and so
is a beam's table given to the slab summary.

Forces
------

The forces table of the beam summary: ``Level`` (optional), ``Label``, ``Comb.``, ``Nx``
(optional), ``Vz``, ``My``, ``Notes`` (optional), in ``kN`` and ``kNm`` (or ``kip`` and
``kip·ft``). The forces are those of the strip of width ``b``: with ``b = 100 cm``, the
forces per metre of slab are the same numbers. ``Nx > 0`` is compression and
``My > 0`` puts the bottom face in tension.

Each layer must give both a diameter and a spacing, or leave both at zero.
An incomplete layer raises ``ValueError``; a second layer given on its own is
read even when the first layer is empty.

.. code-block:: python

    import pandas as pd
    from mento import Concrete_ACI_318_19, SteelBar, MPa, OneWaySlabSummary

    conc = Concrete_ACI_318_19(name="H25", f_c=25 * MPa)
    steel = SteelBar(name="ADN 420", f_y=420 * MPa)

    sections = pd.DataFrame(
        {
            "Label": ["", "L101", "L102"],
            "b": ["cm", 100, 100],
            "h": ["cm", 20, 15],
            "cc": ["mm", 25, 25],
            "db1_top": ["mm", 12, 0],
            "s1_top": ["cm", 15, 0],
            "db1_bot": ["mm", 12, 10],
            "s1_bot": ["cm", 15, 20],
        }
    )
    forces = pd.DataFrame(
        {
            "Label": ["", "L101", "L101", "L102"],
            "Comb.": ["", "1.2D+1.6L", "1.4D", "1.2D+1.6L"],
            "Nx": ["kN", 0, 0, 0],
            "Vz": ["kN", 50, -60, 30],
            "My": ["kNm", 40, -45, 15],
        }
    )
    slab_summary = OneWaySlabSummary(conc, steel, sections, forces)

``OneWaySlabSummary.from_excel(conc, steel, path)`` reads the sheets ``Sections`` and
``Forces``, and ``to_excel(path)`` writes them. A US customary list takes lengths in
``in``, forces in ``kip`` and moments in ``kip·ft``.

Check, Design and Results
-------------------------

The methods are those of the beam summary:

.. code-block:: python

    slab_summary.check()                 # one row per strip
    slab_summary.check(capacity_check=True)
    slab_summary.flexure_results()       # one row per combination
    slab_summary.shear_results(index="L101")
    slab_summary.design()                # fills the layers of both faces
    slab_summary.export_design("SlabDesign.xlsx")
    slab_summary.import_design("SlabDesign.xlsx")
    slab_summary.results_detailed_doc()  # Slab_Summary_{design_code}.docx

``check()`` has the columns of the beam summary but ``Av``. Its verdict counts the strip's
warnings: an ACI 318-19 100×15 strip with Ø6/25 at the bottom carries its moment (DCR
0.743) but is below the 0.0018·Ag minimum, ``As_below_min (bottom)``, ❌; one with Ø12/40
carries it too (0.772) but its spacing is past the maximum (§7.7.2.3),
``bar_spacing_exceeds_max (bottom)``, ❌.

``design()`` is ``Node.design()``, for the envelope of each strip's combinations, and
writes both faces. ``Node.design()`` raises the longitudinal steel where that lifts the
concrete's shear strength enough to do without stirrups: an ACI 100×15 strip under
20 kN·m and 50 kN takes Ø10/14 and passes its shear on the concrete alone
(``test_slab_design_is_node_design``). Under 55 kN it would need stirrups, which a strip
is not detailed with: the strip keeps the layers ``Node.design()`` chose, without
stirrups, ``design()`` names it instead of saying it completed (warning
``shear_reinforcement_required``), and ``check()`` gives it ❌ with DCRv 1.078 and
``stirrups_required`` (``test_a_slab_that_needs_shear_reinforcement_is_named``). Such a
strip needs more longitudinal steel, more thickness, a higher f'c, or shear
reinforcement detailed as a beam.

A strip designed can still be ❌ for a detailing warning: a 100×15 strip under −90 kN·m
gets Ø16/7 on top and Ø10/3 at the bottom, 0.877, below the minimum bar spacing at the
bottom (``test_a_hogging_slab_reads_back_as_designed``). The check says which.
