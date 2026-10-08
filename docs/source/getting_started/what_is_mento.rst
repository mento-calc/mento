What is mento?
==============

mento designs and checks reinforced concrete members to **ACI 318-19**, **EN 1992-1-1:2004
(Eurocode 2)** and **CIRSOC 201-25**. Give it a section, its materials and a set of load
combinations; it returns the reinforcement, the demand-to-capacity ratio of every check, and a
calculation report you can hand to a reviewer.

mento does no structural analysis: the forces come from your analysis model, and mento
designs the section that has to resist them.

It is also, as far as we know, the only open source package that implements
**CIRSOC 201-25**, the Argentinian concrete design standard.

Quick start
-----------

Design a 20 × 50 cm beam for two load combinations:

.. code-block:: python

    from mento import Concrete_ACI_318_19, SteelBar, RectangularBeam, Forces, Node
    from mento import MPa, cm, mm, kN, kNm

    concrete = Concrete_ACI_318_19(name="C25", f_c=25 * MPa)
    steel = SteelBar(name="ADN 420", f_y=420 * MPa)
    beam = RectangularBeam(
        label="B101", concrete=concrete, steel_bar=steel,
        width=20 * cm, height=50 * cm, c_c=25 * mm,
    )

    forces = [
        Forces(label="1.2D+1.6L", M_y=120 * kNm, V_z=100 * kN),
        Forces(label="1.4D", M_y=80 * kNm, V_z=70 * kN),
    ]
    node = Node(section=beam, forces=forces)
    node.design()

    print(beam.reinforcement)

.. code-block:: text

    bottom: 2Ø20 mm + 1Ø16 mm / top: no reinforcement / stirrups: 1sØ10 mm/22 cm

From there:

- ``beam.plot()`` draws the section with its bars and stirrups.
- ``node.check_flexure()`` and ``node.check_shear()`` return one row per combination as a
  pandas DataFrame, with the required and provided steel, the capacity and the DCR.
- ``node.results`` shows the formatted results in a Jupyter notebook.
- ``node.flexure_results_detailed_doc()`` and ``node.shear_results_detailed_doc()`` write the
  step-by-step calculation report to Word.
- To check reinforcement you already have instead of designing it, set the bars on the beam
  and call ``node.check()``.

The :ref:`Examples <examples/index>` walk through each element and design code as a
notebook, including US customary units.

What mento covers
-----------------

.. list-table::
   :header-rows: 1
   :widths: 40 20 20 20

   * - Element
     - ACI 318-19
     - CIRSOC 201-25
     - EN 1992-1-1:2004
   * - :doc:`Rectangular beam <../user_guide/beams>`, flexure and shear
     - ✅
     - ✅
     - ✅
   * - :doc:`One-way slab <../user_guide/slabs>`, flexure and shear
     - ✅
     - ✅
     - ✅
   * - :doc:`Footing section <../user_guide/footings>`, flexure and shear
     - ✅
     - ✅
     - ✅
   * - :doc:`Shear wall <../user_guide/shear_wall>`, in-plane shear
     - ✅
     - ✅
     - ✅
   * - Slab punching shear
     - in progress
     - in progress
     - in progress

A footing is designed as a section, with the minimum reinforcement and detailing rules of a
member bearing on the ground: mento does no geotechnical calculation.

Across all of them:

- **Units throughout.** Every input carries its unit. Metric and US customary are both
  supported, and a section entered in US customary units is reported in them. See
  :doc:`../user_guide/units`.
- **Design gives you options.** Besides the arrangement it applies, a design keeps the next
  best alternatives for bars and stirrups, and warns about the detailing limits a section
  misses. See :ref:`Design results <user_guide/design_results>`.
- **Many members at once.** :doc:`BeamSummary <../user_guide/beam_summary>` and
  :doc:`ShearWallSummary <../user_guide/shear_wall_summary>` design or check a whole schedule,
  and export the designed reinforcement to Excel and back.
- **Reports.** Results come as Markdown in Jupyter, as pandas DataFrames, and as Word
  documents.

Validated against published examples
------------------------------------

The tests in
`tests/validation <https://github.com/mihdicaballero/mento/tree/main/tests/validation>`_
reproduce cases worked out outside mento: the CRSI *Design Guide on the ACI 318 Building
Code*, CSI's software verification examples, ETABS runs, The Concrete Centre's Eurocode 2
guide and eurocodeapplied.com. Each test names the example and the page its numbers come from.

The :ref:`Theory <theory/index>` pages set out the equations behind each check, with the
clause of the design code they come from.

mento is a tool to assist structural engineers, not a replacement for engineering judgement:
its results must be reviewed by a qualified engineer who takes responsibility for the design.

For more detailed help, see the :ref:`User Guide <user_guide/index>` and the
:ref:`Examples <examples/index>`.
