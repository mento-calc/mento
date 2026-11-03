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

- **Geometry**: the footing across the direction it spans, given as a `width` and a
  `height` (the total thickness). `width` is the whole footing, edge to edge, because
  its bars are counted in it: results are the totals across that width, in whole bars.
  A 1 m `width` is a footing 1 m wide, not a metre of a wider one.
- **Forces**: the sectional forces at the face being designed — the moment and shear
  the soil pressure produces across that width. Mento does not derive them from the
  soil; they are an input.
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

    # A footing 1 m wide and 60 cm thick
    footing = Footing(label="Z1", concrete=concrete, steel_bar=steel,
                      width=1 * m, height=60 * cm, c_c=50 * mm)

`c_c` sets the depth of the bars. Where the cover at the sides of the footing is not that
same number, give it as `edge_cover` (see *Whole bars* below).

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

The design applies all of these for you:

- **Whole bars.** A slab strip goes on past its edges and counts ``width / s`` bars. A
  footing ends at its edges and is built with whole bars, so that is what its steel is.
  They lie in

  .. code-block:: text

      span = width - 2 * edge_cover - 2 * bend_clearance
      n(s) = max(floor(span / s) + 1, 2)
      A_s  = n * A_b

  `edge_cover` is the cover at the sides, `c_c` unless you give it. `bend_clearance` is what
  the first bar keeps from that cover, so that it does not run into the bend of the bars
  crossing it: 4 cm by default, 1.5 in. in US customary units. At 130 cm wide with 5 cm of
  side cover the span is 112 cm, so ``Ø12/28`` is 5 bars, 5.65 cm². `layer.n` reads that
  integer, and the capacity and the DCR are computed with that area.

  .. code-block:: python

      # The top layer rests on the bottom one: c_c = cover + Ø reaches its depth,
      # and the real cover goes to the sides.
      Footing(label="Z1", concrete=concrete, steel_bar=steel,
              width=130 * cm, height=35 * cm, c_c=6.2 * cm, edge_cover=5 * cm)

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
