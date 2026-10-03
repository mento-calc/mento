One-Way Slab Summary
====================

The ``OneWaySlabSummary`` class does for a list of one-way slabs what
:doc:`beam_summary` does for beams: it reads them from a table, checks them,
designs their reinforcement and writes the design back to Excel.

Input Data
----------

Each row is one load combination of one slab strip. The columns are those of the
beam summary, with each face given the way a slab is detailed, as a bar diameter
and a spacing per layer, and no stirrups:

- **Label**: Slab identifier (e.g., L101).
- **Comb.**: Load combination label.
- **b**: Width of the strip in cm (100 for a metre of slab; the results are for the strip).
- **h**: Slab thickness in cm.
- **cc**: Clear cover in mm.
- **Nx**: Axial force in kN.
- **Vz**: Shear force in kN.
- **My**: Moment in kNm.
- **db1, s1**: Diameter (mm) and spacing (cm) of the first layer.
- **db3, s3**: Diameter and spacing of an optional second layer (0 if none).

As in the beam summary, the bars on a row are those of the face its moment puts in
tension: the bottom for ``My >= 0``, the top otherwise. Rows that share a **Label**
are one slab under several combinations, checked and designed for their envelope;
they must agree on ``b``, ``h`` and ``cc``, and the rows that give the bars of a face
must give the same ones. A US customary list takes lengths in ``in``, forces in
``kip`` and moments in ``kip·ft``.

Each layer must give both a diameter and a spacing, or leave both at zero.
An incomplete layer raises ``ValueError``; a second layer given on its own is
read even when the first layer is empty.

.. code-block:: python

    import pandas as pd
    from mento import Concrete_ACI_318_19, SteelBar, MPa, OneWaySlabSummary

    conc = Concrete_ACI_318_19(name="H25", f_c=25 * MPa)
    steel = SteelBar(name="ADN 420", f_y=420 * MPa)

    data = {
        "Label": ["", "L101", "L101", "L102"],
        "Comb.": ["", "1.2D+1.6L", "1.4D", "1.2D+1.6L"],
        "b": ["cm", 100, 100, 100],
        "h": ["cm", 20, 20, 15],
        "cc": ["mm", 25, 25, 25],
        "Nx": ["kN", 0, 0, 0],
        "Vz": ["kN", 50, -60, 30],
        "My": ["kNm", 40, -45, 15],
        "db1": ["mm", 12, 12, 10],
        "s1": ["cm", 15, 12, 20],
        "db3": ["mm", 0, 0, 0],
        "s3": ["cm", 0, 0, 0],
    }
    slab_summary = OneWaySlabSummary(concrete=conc, steel_bar=steel, slab_list=pd.DataFrame(data))

Check, Design and Results
-------------------------

The methods are those of the beam summary:

.. code-block:: python

    slab_summary.check()                 # one row per slab, with the envelope
    slab_summary.check(capacity_check=True)
    slab_summary.flexure_results()       # one row per combination
    slab_summary.shear_results()
    slab_summary.design()                # fills db1, s1, db3, s3
    slab_summary.export_design("SlabDesign.xlsx")
    slab_summary.import_design("SlabDesign.xlsx")
    slab_summary.results_detailed_doc()  # Slab_Summary_{design_code}.docx

``design()`` designs the flexural reinforcement only. A one-way slab is detailed
without stirrups, so ``check()`` reports its shear against the concrete alone: a slab
whose shear DCR is above one needs to be thicker.
