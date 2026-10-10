Footing
=======

The `Footing` class models the **section** of a spread footing or raft — a one-way
slab bearing directly on the ground.

It is a `OneWaySlab` in every respect but the rules the design codes write differently
for a member on the ground: the minimum longitudinal reinforcement, the spacing the bars
are detailed at, and the thickness the section is expected to have. Everything else —
geometry, materials, reinforcement given as diameter and spacing, flexure and shear
checks through a `Node` — is the slab's, unchanged.

.. warning::

    **Sectional design only. Mento does no geotechnical calculation.**

    `Footing` answers one question: what reinforcement does this section need for
    the forces it is given. It knows nothing about the soil under it and does not
    check bearing pressure, settlement, sliding, overturning, uplift, or the plan
    dimensions the footing needs to spread its load. It does not size the footing.

    Those are the engineer's, and they come first: the plan size and the thickness
    are decided from the soil, and only then is the resulting section handed to
    `Footing`. Punching shear is a separate check — see
    :class:`~mento.punching.PunchingSlab`.

Key Concepts
------------

- **Geometry**: a strip of the footing, given as a `width` and a `height` (the total
  thickness). Results are the totals across that width, so a 1 m strip reads directly
  as per-metre values.
- **Forces**: the sectional forces at the face being designed — the moment and shear
  the soil pressure produces in the strip. Mento does not derive them from the soil;
  they are an input.
- **Reinforcement**: bar diameter and spacing, one direction at a time. A footing spans
  both ways, so it is designed as two strips, one per direction.
- **Design code**: taken from the `Concrete` object, as everywhere else in mento.
  ACI 318-19, CIRSOC 201-25 and EN 1992-2004 are all supported.

Usage
-----

1. Creating a Footing
*********************

.. code-block:: python

    from mento import Concrete_ACI_318_19, Footing, SteelBar, MPa, cm, mm, m

    concrete = Concrete_ACI_318_19(name="H25", f_c=25 * MPa)
    steel = SteelBar(name="ADN 420", f_y=420 * MPa)

    # A 1 m strip of a footing 60 cm thick
    footing = Footing(label="Z1", concrete=concrete, steel_bar=steel,
                      width=1 * m, height=60 * cm, c_c=50 * mm)

2. Checking and Designing
*************************

Exactly as for a slab: forces are attached through a `Node`, which drives the check
and the design.

.. code-block:: python

    from mento import Forces, Node, kN, kNm

    node = Node(section=footing, forces=[Forces(label="ELU 1", M_y=120 * kNm, V_z=90 * kN)])

    node.design()          # flexure + shear
    node.check_flexure()   # per-combination table
    node.check_shear()

Reinforcement can also be assigned by hand with `set_slab_longitudinal_rebar_bot()` and
`set_slab_longitudinal_rebar_top()`, and read back afterwards, the same way as for a
`OneWaySlab`. See :doc:`slabs` for the full reinforcement and results API.

What differs from a slab
------------------------

Three rules, and the design applies all of them for you:

- **Minimum reinforcement.** A member on the ground is exempt from the flexural
  minimum written for a member spanning between supports, and each code puts a
  different rule in its place. `Footing` returns the largest applicable minimum
  **already applied**, so the reinforcement it reports needs no correction afterwards.
  A face the moment puts in tension takes the minimum; a face it does not is left
  unreinforced — whether a footing carries top steel is yours to decide, since only you
  see both orthogonal sections of the element. The distribution reinforcement across the
  span is the same question asked of a different section, and is designed as one.
- **Bar spacing.** Kept between 100 and 300 mm. A design answers a heavier demand with
  a larger bar rather than with bars closer than 100 mm, and both bounds appear in the
  flexure check table.
- **One mat.** A footing is placed as a single grid, not as two independently detailed
  faces, so a design ends on **one module**: the top either at the bottom's spacing or at
  exactly twice it, so one top bar lands on every second bottom bar. Within that, mento
  picks the module and both diameters that give the least steel covering what each face
  needs — e.g. ``Ø20 c/15`` at the bottom with ``Ø20 c/30`` on top. A footing reinforced on one
  face only keeps its single grid.
- **Ø10 minimum.** A footing mesh is not detailed with the thinnest bar in the
  catalogue, so the search does not reach below Ø10 to shave the lightly loaded face.
- **Depth.** A section shallower than the code asks of a footing on soil warns when it
  is built. Under ACI 318-19 and CIRSOC 201-25 the clause is on the effective depth of
  the bottom reinforcement — §13.3.1.2 asks at least 150 mm (6 in.) — so what is
  measured is the depth left to the bars and not the overall thickness:

  .. code-block:: python

      Footing(label="Z2", concrete=concrete, steel_bar=steel,
              width=1 * m, height=18 * cm, c_c=50 * mm)
      # UserWarning: Footing Z2 leaves 12.5 cm of effective depth to the bottom
      # bars, below the 150 mm ACI 318-19 asks of a footing on soil. It is
      # designed as given.

  Under EN 1992-1-1 there is no such clause and the 250 mm of practice is compared
  against the overall thickness instead. Either way it is advice, not a limit: the
  section is still designed as given, because the depth is the engineer's to choose.
  The check is repeated with the actual bars at the end of design and when checking
  flexure or shear.

For the clauses these come from, the equations, and the readings mento takes where the
codes leave room for judgement, see :doc:`../theory/footing`.
