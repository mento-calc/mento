Beam Summary
============

The ``BeamSummary`` class checks, designs and reports a list of beam sections at
once. It reads two tables: one that says what each **section** is, and one that says
what **forces** each section carries, one row per load combination.

Creating Concrete and Steel Materials
--------------------------------------

Define the concrete and steel materials to be used across all beams:

.. code-block:: python

    from mento.material import Concrete_ACI_318_19, Concrete_EN_1992_2004, SteelBar
    from mento import MPa

    # ACI 318-19
    conc = Concrete_ACI_318_19(name="C25", f_c=25 * MPa)

    # or EN 1992-2004
    conc = Concrete_EN_1992_2004(name="C25/30", f_c=25 * MPa)

    steel = SteelBar(name="ADN 420", f_y=420 * MPa)

Supported design codes: **ACI 318-19**, **EN 1992-2004**, and **CIRSOC 201-25**.

The Two Tables
--------------

Each table is a ``DataFrame`` whose first row holds the unit of every column, as an
Excel sheet with its unit row under the headers. Columns are read by name, in any order.

**Sections** — one row per section, with a ``Label`` no other row repeats:

- **Level** (optional): a storey or a group; where given, a section is the pair
  ``(Level, Label)``.
- **Label**: the section's name (V101, V9a...).
- **b**, **h**: width and height (``cm``, ``mm``, ``m``, ``in``, ``ft``).
- **cc**: clear cover to the stirrups.
- **legs**, **dbs**, **sl**: the stirrups: the number of **legs** (two per closed
  stirrup, so it is even), their diameter and their spacing along the beam.
- **n1_top, db1_top ... n4_top, db4_top** and **n1_bot, db1_bot ... n4_bot, db4_bot**:
  the bars of each face, as four groups of a number and a diameter. ``n1/db1`` and
  ``n2/db2`` make the layer nearest the face; ``n3/db3`` and ``n4/db4`` a second layer
  inside it, as :meth:`~mento.beam.RectangularBeam.set_longitudinal_rebar_bot` takes them.
- **Notes** (optional): free text — a span, a station, the name a model gives the
  member. It is kept and written back, and never read.

**Forces** — one row per load combination of a section:

- **Level** (optional) and **Label**: the section the row acts on.
- **Comb.**: the combination's name. A section takes each combination once.
- **Nx** (optional), **Vz**, **My**: in ``kN`` and ``kNm``, or ``kip`` and ``kip·ft``.
- **Notes** (optional).

Sign conventions, as everywhere in mento (:doc:`local_axes`): **Nx > 0 is
compression** (a tension taken from ETABS, which gives P positive in tension, changes
sign), **My > 0 puts the bottom face in tension**, and **Vz** is taken in magnitude.
``Nx`` enters the shear check only: a beam's flexure is checked without it. Under ACI
318-19 and CIRSOC 201-25, a compression of ``0.10 f'c Ag`` or more (§9.5.2.2) raises the
warning ``axial_load_beyond_beam``: verify axial-moment interaction (§22.4) and closed stirrups or spirals
according to Table 22.4.2.1; R/C9.5.2.2 does not require Chapter 10. A forces table with
no ``Nx`` column is read as ``N = 0``, with a warning, since a tension left out makes the
shear check unconservative.

The rules:

- A section is prismatic. If the support bars are cut before the midspan, the support and
  the midspan are **two sections**, with two labels. A section under several combinations
  is one row of sections and several rows of forces.
- A label repeated in the sections table, a forces row whose label is not in the sections
  table, and a combination given twice to one section are errors that name it.
  A section with no forces gives a warning and keeps its row, shown as not checked.
- Labels are text, stripped: ``"V4 "`` is ``"V4"``, and ``101`` is ``"101"``.
- A zero is no bars: a face whose ``n1`` is 0 has no bars at all. ``legs = 0`` is a beam
  without stirrups, which keeps the starter stirrup of its settings (Ø8, #3) in its
  effective depth, as a :class:`~mento.beam.RectangularBeam` built by hand does.
- The reinforcement columns may be left out (they are zero on every row), to design from
  the geometry alone. An empty reinforcement or force cell is zero; an empty geometry
  cell, text in a numeric column, a negative bar, a bar count without its diameter or an
  odd number of legs are errors that name the section and the column.
- A row with every cell empty is skipped.

Errors are :class:`~mento.summary_tables.SummaryInputError` (a ``ValueError``) and
warnings :class:`~mento.summary_tables.SummaryInputWarning`, each with a stable ``code``.
``str(error)`` is in English; ``error.message`` follows :func:`mento.set_language`.

Example: a support and a midspan
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

ACI 318-19, H25, ADN 420, 20×40, cc 25 mm, stirrups 1eØ10/17. The support carries
3Ø16 on top under −60 kN·m and 80 kN; the midspan 2Ø32 at the bottom under +170 kN·m
and 10 kN. The support bars are cut before the midspan, so these are two sections,
each with 2Ø8 on its other face (the columns of the second layer, all zero, are left out):

.. csv-table:: Sections
   :header: "Label", "b", "h", "cc", "legs", "dbs", "sl", "n1_top", "db1_top", "n1_bot", "db1_bot"

   "", "cm", "cm", "mm", "", "mm", "cm", "", "mm", "", "mm"
   "V9a", 20, 40, 25, 2, 10, 17, 3, 16, 2, 8
   "V9t", 20, 40, 25, 2, 10, 17, 2, 8, 2, 32

.. csv-table:: Forces
   :header: "Label", "Comb.", "Nx", "Vz", "My"

   "", "", "kN", "kN", "kNm"
   "V9a", "apoyo", 0, 80, -60
   "V9t", "tramo", 0, 10, 170

``check()`` gives V9a 0.804 on top and ✅; V9t 1.263 at the bottom and ❌, with the
warnings ``not_tension_controlled (bottom)`` and
``stirrup_spacing_exceeds_compression_support`` (``test_a_support_and_a_midspan_are_two_sections``).

If the bars run through, it is one section under both combinations: one row of sections
with ``n1_top = 3, db1_top = 16, n1_bot = 2, db1_bot = 32`` and the two rows of forces
under the label ``V9``. ``check()`` then gives 0.804 on top (apoyo), 0.934 at the bottom
(tramo) and 0.548 in shear (apoyo), with no warning, as a :class:`~mento.node.Node` built
by hand (``test_continuous_bars_are_one_section_declared_once``).

The same tables in code:

.. code-block:: python

    import pandas as pd
    from mento import BeamSummary

    sections = pd.DataFrame(
        {
            "Label": ["", "V9a", "V9t"],
            "b": ["cm", 20, 20],
            "h": ["cm", 40, 40],
            "cc": ["mm", 25, 25],
            "legs": ["", 2, 2],
            "dbs": ["mm", 10, 10],
            "sl": ["cm", 17, 17],
            "n1_top": ["", 3, 2],
            "db1_top": ["mm", 16, 8],
            "n1_bot": ["", 2, 2],
            "db1_bot": ["mm", 8, 32],
        }
    )
    forces = pd.DataFrame(
        {
            "Label": ["", "V9a", "V9t"],
            "Comb.": ["", "apoyo", "tramo"],
            "Nx": ["kN", 0, 0],
            "Vz": ["kN", 80, 10],
            "My": ["kNm", -60, 170],
        }
    )
    beam_summary = BeamSummary(conc, steel, sections, forces)

Reading and Writing Excel
--------------------------

A summary file holds two sheets, ``Sections`` and ``Forces``, each with its unit row
under the headers. :meth:`~mento.beam_summary.BeamSummary.from_excel` reads them and
:meth:`~mento.beam_summary.BeamSummary.to_excel` writes them (to a path or to a
buffer such as ``io.BytesIO``); sheet names and headers are always in English, whatever
the language set, so a file reads back anywhere:

.. code-block:: python

    beam_summary = BeamSummary.from_excel(conc, steel, "Beams.xlsx")
    beam_summary.to_excel("Beams.xlsx")
    sections, forces = beam_summary.tables()   # the two tables as the file holds them

A workbook laid out otherwise — a title above the headers, columns further right — is
read with pandas and passed as two ``DataFrame``:

.. code-block:: python

    sections = pd.read_excel("Project.xlsx", sheet_name="Vigas", usecols="B:Z", skiprows=4)
    forces = pd.read_excel("Project.xlsx", sheet_name="Esfuerzos", usecols="B:G", skiprows=4)
    beam_summary = BeamSummary(conc, steel, sections, forces)

Nodes built by hand are written the same way with
:meth:`~mento.beam_summary.BeamSummary.from_nodes`: each node is a section,
labelled with its section's ``label``, and its forces its combinations. A node a row
cannot hold (settings other than the defaults, an out-of-plane moment ``M_x``, other
materials) raises instead of coming back as another section.

.. code-block:: python

    BeamSummary.from_nodes(conc, steel, [node_1, node_2]).to_excel("Beams.xlsx")

From mento 1.4.0
~~~~~~~~~~~~~~~~

The single table of mento 1.4.0 — one row per combination, the section repeated on each —
is no longer read; passing it raises ``SummaryInputError`` with code ``single_table``.
:func:`~mento.summary_tables.split_single_table` converts it, each row becoming a section
of its own with its forces, which is what 1.4.0 computed:

.. code-block:: python

    from mento import split_single_table

    old = pd.read_excel("Beams_1_4_0.xlsx")
    beam_summary = BeamSummary(conc, steel, *split_single_table(old, "beam"))

It writes the 2Ø8 (2 #3) 1.4.0 placed on the face no moment pulls, renames repeated
labels (``V1``, ``V1-2``...) and warns about every row with ``n3`` or ``n4``: 1.4.0 read
them as a second layer of the face in tension, whatever the template drawing said.

Checking
--------

``check()`` runs ``node.check()`` — flexure, then shear — on every section and returns
one row per section:

.. code-block:: python

    beam_summary.check()

- ``b×h``, ``As,top``, ``As,bot`` and ``Av``: what the section is.
- ``Comb.,top``, ``Mu,top``, ``DCRb,top`` (and the same for ``bot``): the combination
  that governs each face, its moment and the DCR. Every combination tied at that DCR is
  named. A face no combination puts in tension reads ``-`` and DCR 0.
- ``Comb.,v``, ``Vu``, ``Nu``, ``DCRv``: the same for the shear, with the axial load of
  that combination. (``MEd``, ``VEd``, ``NEd`` under EN 1992-1-1.)
- ``Warnings``: mento's warning codes (:doc:`design_results`) with the face they are read
  on, e.g. ``As_below_min (bottom)``; ``-`` for none. They are the same in every language.
- ``Ok?``: ✅ when every DCR is at most 1 **and** the section misses no limit — a section
  with warnings is ❌. A section with no forces reads "no forces", and one with no bars
  "no reinforcement: run design()".

The same, as data that does not depend on the language, is in ``beam_summary.results``:
one :class:`~mento.summary_base.SectionVerdict` per section, with the
:class:`~mento.summary_base.GoverningDemand` of each face and of the shear, its warnings
and ``passes``. ``beam_summary.warnings`` maps each ``(Level, Label)`` to its warnings.

``check(capacity_check=True)`` gives the capacities instead (``ØMn,top``, ``ØMn,bot``,
``ØVn``, or ``MRd,top``, ``MRd,bot``, ``VRd`` under EN 1992-1-1), computed on a copy of
each section with no forces, so ``results`` stays that of the forces.

Viewing Detailed Results
-------------------------

``flexure_results()`` and ``shear_results()`` give one row per combination. ``index``
picks one section, by its 1-based position in the sections table or by its label:

.. code-block:: python

    beam_summary.flexure_results()
    beam_summary.shear_results(capacity_check=True)
    beam_summary.flexure_results(index=2)
    beam_summary.shear_results(index="V9t")

Each section is a :class:`~mento.node.Node` in ``beam_summary.nodes``, in the order of the
sections table:

.. code-block:: python

    beam_summary.nodes[1].shear_results_detailed()

Designing Reinforcement
------------------------

``design()`` designs every section that has forces exactly as ``node.design()`` does, for
the envelope of its combinations (``test_design_is_node_design``), writes what it designed
into the sections table — **both faces**, and the stirrups — and checks it. It returns the
sections table:

.. code-block:: python

    designed = beam_summary.design()

So a design exported and read back is the section designed: the 20×40 midspan of the
example, designed from its geometry alone, gets 2Ø32 at the bottom and 2Ø16 + 1Ø16 on top,
and checks 0.934 before and after ``to_excel`` / ``from_excel``.

Two things follow from ``design()`` being ``Node.design()``:

- A section under positive moments only is designed with no bars on top (no hanger bars),
  while one under negative moments only gets bars at the bottom too. Add the hanger bars
  to the sections table if the drawings carry them.
- A section designed can still be ❌ for a detailing warning; its row says which.

Exporting and Importing a Design
----------------------------------

``export_design(path)`` writes the two sheets, as ``to_excel``; ``import_design(path)``
reads them back into the summary, replacing its sections and forces:

.. code-block:: python

    beam_summary.export_design("BeamDesign.xlsx")
    # ... edit the bars in the Sections sheet ...
    beam_summary.import_design("BeamDesign.xlsx")
    beam_summary.check()

What these print follows :func:`mento.set_language`.

Exporting Results to Excel
----------------------------

The DataFrames returned by ``check()``, ``flexure_results()``, and ``shear_results()``
can be written to Excel directly:

.. code-block:: python

    beam_summary.check().to_excel("results.xlsx", index=False)

Detailed Word Report
---------------------

``results_detailed_doc()`` generates a Word document (``.docx``) that contains:

- Full flexure and shear detail for one selected beam.
- The tables of all beams: the sections, the forces with their sign conventions, the
  flexure and shear results per combination, the check, and every warning worded in full,
  with the face and the combinations it is read on.

The document is saved to the current working directory with the name
``Beam_Summary_{design_code}.docx`` (e.g. ``Beam_Summary_ACI 318-19.docx``).

.. code-block:: python

    # Detailed report with beam 1 as the reference beam (default)
    beam_summary.results_detailed_doc()

    # Use beam V9t as the reference beam
    beam_summary.results_detailed_doc(index="V9t")

``index`` is the section's 1-based position in the sections table or its label. An
``IndexError`` is raised for a position out of range; a section with no forces has no
detail to report and raises ``SummaryInputError``.


Decisiones de entrega: resistencia, detallado y ramas
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``beam.verification_status`` muestra resistencia y detallado modelado por
separado. Un DCR favorable no aprueba un detallado incumplido o pendiente.
Los estados se muestran aparte en los anexos de cortante de consola y Word.
Los indicadores heredados conservan su contrato para compatibilidad.

La entrada preferida es ``legs``; ``n_legs`` continúa como alias y ``ns``
conserva su significado de cantidad de estribos cerrados. El modelo actual
solo admite pares de ramas de estribos cerrados; no define una traba suelta
ni su anclaje. Una disposición arbitraria de siete ramas requiere ampliar
el modelo, no redondear silenciosamente la cantidad ingresada.

El Word muestra ambas caras físicas y cc en la tablas Beam Sections / Slab Sections en mm (métrico) o pulgadas
(imperial). Las zapatas EN con axil no nulo se rechazan como caso todavía
no soportado por Mento; no es una prohibición del Eurocódigo.
