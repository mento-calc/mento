Units
=========================

The `mento` package is designed to work with both Metric (SI) and
Imperial unit systems. The units are managed using the `Pint` library,
which allows for seamless unit conversions and arithmetic.

Importing units
--------------------

Units are imported from mento directly, you just type what you
want to use. For example:

.. code-block:: python

    from mento import mm, cm, kN, MPa, inch, ft, ksi

Usage within `mento`
--------------------

The units in `mento` are fully compatible with the `Pint` unit
registry, allowing for easy conversions between different systems.
You can add values with different units of the same type, and change
to other units using the `.to()` method.

The example below adds attributes in different unit imported
from mento and then changes it to feet.

.. code-block:: python

    from mento import cm, m
    a = 2*m
    b = 15*cm
    c = a + b
    print(a, b, c)
    d = c.to('ft')
    print(d)
    f=10*kN
    f.to('kgf')

Available Units
---------------

The following units are available in `mento`:

* **Metric (SI)**:

  * Length: `m`, `cm`, `mm`
  * Force: `kgf`, `kN`
  * Moment: `kNm`
  * Stress: `Pa`, `kPa`, `MPa`, `GPa`
  * Mass: `kg`
  * Time: `sec`

* **Imperial**:

  * Length: `inch`, `ft`
  * Force: `lb`, `kip`
  * Stress: `psi`, `ksi`

US customary output
-------------------

A section is designed in the unit system of its concrete: an ``f_c`` in ``psi``
or ``ksi`` makes it US customary, and then everything mento shows is written in
US customary units too -- the unit rows and values of the DataFrames, the
detailed printouts, the Word reports, the Markdown views, the summaries, the
drawings and the warning messages. Only ACI 318-19 is written for these units:
``Concrete_CIRSOC_201_25`` and ``Concrete_EN_1992_2004`` raise a ``ValueError``
for an ``f_c`` in ``psi`` or ``ksi``.

.. code-block:: python

    from mento import psi, ksi, inch, ft, kip
    from mento import Concrete_ACI_318_19, SteelBar, RectangularBeam, Node, Forces

    concrete = Concrete_ACI_318_19(name="4000", f_c=4000 * psi)
    steel = SteelBar(name="Gr60", f_y=60 * ksi)
    beam = RectangularBeam(
        label="B1", concrete=concrete, steel_bar=steel,
        width=12 * inch, height=24 * inch, c_c=1.5 * inch,
    )
    node = Node(section=beam, forces=[Forces(label="1.2D+1.6L", M_y=120 * kip * ft, V_z=40 * kip)])
    node.design()
    print(node.check_flexure().to_string())
    print(node.check_shear().to_string())

.. code-block:: text

      Label      Comb. Position As,min As,req top As,req bot    As      Mu     ØMn Mu≤ØMn    DCR
    0                              in²        in²        in²   in²  kip·ft  kip·ft
    1    B1  1.2D+1.6L   Bottom   0.87        0.0       1.28  1.33   120.0  123.91   True  0.968
      Label      Comb.  Av,min  Av,req      Av    Vu   Nu    ØVc    ØVs    ØVn  ØVmax Vu≤ØVmax Vu≤ØVn    DCR
    0                   in²/ft  in²/ft  in²/ft   kip  kip    kip    kip    kip    kip
    1    B1  1.2D+1.6L    0.12   0.187   0.331  40.0  0.0  24.76  27.02  51.79  123.8     True   True  0.772

The units each quantity is shown in:

.. list-table::
   :header-rows: 1

   * - Quantity
     - SI
     - US customary
   * - f'c / fy
     - MPa / MPa
     - psi / ksi
   * - Section dimensions, d, cover, stirrup spacing
     - cm
     - in (two decimals)
   * - Bar diameter, clear spacing between bars
     - mm
     - ASTM size (``#6``) / in
   * - Wall length and height
     - cm (m in the summary)
     - ft
   * - Steel area per face
     - cm²
     - in² (two decimals)
   * - Steel area per length (stirrups, slabs, wall mesh)
     - cm²/m
     - in²/ft (three decimals)
   * - Force / moment
     - kN / kNm
     - kip / kip·ft
   * - Concrete density
     - kg/m³
     - lb/ft³

A US bar is named by its ASTM A615 size and its spacing follows an ``@``, as on a
US drawing: ``3#6`` and ``2#6+1#5`` for the bars of a face, ``#4@12 in`` for a slab
or a wall curtain, ``2 legs #3 @ 8 in`` for a two-leg stirrup. Transverse
reinforcement is written by its number of legs, translated by ``notation()``:
``2 legs Ø10 mm @ 22 cm`` / ``2 ramas Ø10 mm c/22 cm``. Its ``str()`` is English.

The table of ASTM sizes is public, so a program can use the same one::

    from mento import bar_designation, bar_diameter, inch, mm
    bar_designation(0.75 * inch)   # "#6"
    bar_diameter(6)                # 0.75 inch
    bar_designation(16 * mm)       # 'Ø0.63"' -- a diameter that is no ASTM size

Unit Formatting
---------------

The units in `mento` follow a standardized formatting scheme to
ensure clarity in outputs, showing usually 2 decimals for any attribute.
You can format and display units using the `~P` specifier in
the `Pint` library. Here’s an example:

.. code-block:: python

    from mento import kN
    F = 15.2354*kN
    print(F)
    F2 = f"Force is {F:.4f~P}" # Output: "Force is 15.2354 kN"
    print(F2)

For more advanced usage, refer to the `Pint` library documentation
to explore additional formatting options.
