.. _theory/index:

Theory
======

The :ref:`User Guide <user_guide/index>` explains *how* to drive mento. This section
explains *what* it computes: the code provisions behind every check, equation by
equation, with the clause each one comes from — and, just as importantly, the
decisions mento makes where the code leaves room for judgement.

The intent is auditability. A structural engineer signing off on a design needs to
verify that the tool agrees with the code, and to know exactly where it does not
follow the most common interpretation. Every page therefore ends with a
**Validation** table mapping each check to the test that pins it and to what that
test is verified against.

A check counts as *validated* when its test reproduces numbers printed in a document
outside mento — a design guide, a textbook or code example, a software verification
manual such as CSI's ETABS examples, or a recorded run of another program — and cites
the page, table or row they come from. Those tests live in ``tests/validation/`` and
are the ones the release counts. A Calcpad sheet does not qualify on its own: it
reproduces a calculation with units, which is a good way to check one, but it
publishes nothing a reader can hold mento to. Rows whose only reference is a Calcpad
sheet are listed as regression tests.

.. toctree::
   :hidden:
   :maxdepth: 2

   beam_aci_318_19
   beam_en_1992_2004
   one_way_slab
   footing
   shear_wall_aci_318_19
   shear_wall_en_1992_2004

What is implemented
-------------------

.. list-table::
   :header-rows: 1
   :widths: 22 26 26 26

   * - Element
     - ACI 318-19 / CIRSOC 201-25
     - EN 1992-1-1:2004
     - Notes
   * - Rectangular beam
     - Flexure + shear
     - Flexure + shear
     - :doc:`ACI <beam_aci_318_19>`, :doc:`EN <beam_en_1992_2004>`
   * - One-way slab
     - Flexure + shear
     - Flexure + shear
     - Same provisions as the beam, different detailing —
       :doc:`one_way_slab`
   * - Footing
     - Flexure + shear
     - Flexure + shear
     - Slab provisions with the minimum reinforcement and detailing of a
       member on the ground — :doc:`footing`. Sectional only; no
       geotechnical calculation
   * - Shear wall
     - In-plane shear
     - In-plane shear
     - :doc:`ACI <shear_wall_aci_318_19>`, :doc:`EN <shear_wall_en_1992_2004>`
   * - Punching slab
     - Two-way shear
     - Two-way shear
     - Documented in the API reference

**CIRSOC 201-25** is the Argentine adoption of ACI 318-19. ``Concrete_CIRSOC_201_25``
subclasses ``Concrete_ACI_318_19``: the provisions are identical, the differences are
the metric-only unit system and the reinforcing bar catalogue. It is covered inside
the :doc:`ACI page <beam_aci_318_19>` rather than duplicated.

What is **not** implemented, for any code: torsion, crack width and deflection
serviceability checks, fatigue, fire design, anchorage and development length,
seismic detailing provisions, and prestressing. Nor is anything geotechnical —
mento designs sections, and the soil a footing bears on is outside its scope.

Conventions
-----------

Sign convention
^^^^^^^^^^^^^^^

A positive bending moment ``M_y`` puts the **bottom** face in tension; a negative one
puts the **top** face in tension. Every equation in this section is written for a
positive magnitude of the demand, with the effective depth ``d`` measured to the
tension face being solved and ``d'`` to the opposite face. Both faces run through the
same equations with the roles of ``d`` and ``d'`` swapped. See
:doc:`Local Axes <../user_guide/local_axes>` for the full convention.

Effective depth
^^^^^^^^^^^^^^^

``d`` is measured from the extreme compression fibre to the **centroid of the tension
reinforcement**, not to the outermost bar. mento recomputes it from the actual bar
layout — clear cover, stirrup diameter and the centroid of the layers actually
placed — rather than using a nominal estimate. This matters when comparing against
software that assumes a fixed ``d``.

Design vs. check
^^^^^^^^^^^^^^^^

A **check** takes a given reinforcement layout and reports capacity and a
demand-to-capacity ratio. A **design** searches for a layout that satisfies the
demand.

Design is iterative, because the problem is circular: the steel a section needs
depends on its effective depth, the effective depth depends on where the bars end up,
and the bars come from a discrete catalogue rather than a continuum. mento converges
the mechanical covers, selects a buildable bar layout, and then **verifies that the
layout it chose actually resists the demand** using the same capacity equations
``check_flexure`` uses. A layout returned by a design therefore passes its own check,
unless no layout in the catalogue can — in which case the section is reported with
``DCR > 1`` rather than raising.

Demand-to-capacity ratio
^^^^^^^^^^^^^^^^^^^^^^^^

The DCR reported throughout is the demand divided by the design capacity, so
``DCR ≤ 1`` means the section is adequate. mento never raises an exception because a
section is insufficient — it reports ``DCR > 1`` and lets the engineer decide.

.. warning::

   These pages describe what mento implements, not a substitute for the design codes
   themselves. Clause numbers are given so the original text can be consulted; where
   mento adopts one reading of an ambiguous provision, the page says so explicitly in
   its *Implementation decisions* section.
