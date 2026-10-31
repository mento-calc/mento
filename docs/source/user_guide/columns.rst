Columns
=======

``RectangularColumn`` and ``CircularColumn`` describe a column section -- its
shape, its longitudinal bars and its ties -- and check its **shear in both
directions**, with the axial load of each combination, under ACI 318-19,
CIRSOC 201-25 and EN 1992-1-1.

.. note::

    The column checks shear only. Flexure with axial load (the P–M
    interaction) is not in mento yet, so ``check_flexure`` raises, and the
    ties are checked but not designed: ``design`` raises too. The plan is
    ``docs/architecture/column-shear-roadmap.md`` in the repository.

Axes and directions
-------------------

The column runs along x (:doc:`local_axes`). ``width`` is measured along y and
``height`` along z. Each combination is checked twice:

- ``V_z`` acts across ``height``: the shear section is ``width`` wide, and its
  tension steel is the bars of a face of length ``width``.
- ``V_y`` acts across ``width``: the same turned, ``height`` wide.

``N_x`` enters both, positive in compression. The moments are not verified,
and a combination that carries them is warned about
(``column_force_component_not_checked``); only an EN 1992-1-1 circle reads
them, to tell whether it is cracked in bending.

A rectangular column
--------------------

.. code-block:: python

    from mento import Concrete_ACI_318_19, SteelBar, RectangularColumn, Forces, Node
    from mento import MPa, cm, mm, kN

    concrete = Concrete_ACI_318_19(name="H25", f_c=25 * MPa)
    steel = SteelBar(name="ADN 420", f_y=420 * MPa)

    column = RectangularColumn(
        label="C1", concrete=concrete, steel_bar=steel,
        width=30 * cm, height=50 * cm, c_c=25 * mm,
    )
    # Ø20 in the corners; between them, 1Ø16 on each face of length width
    # and 2Ø16 on each face of length height.
    column.set_longitudinal_rebar(d_b_corner=20 * mm, n_width=1, d_b_width=16 * mm,
                                  n_height=2, d_b_height=16 * mm)
    # A Ø10 tie every 15 cm, and one Ø8 crosstie holding a bar of each face of length height.
    column.set_ties(d_b=10 * mm, s=15 * cm, crossties_height=1, d_b_crosstie=8 * mm)

    node = Node(column, [Forces(label="1.2D+1.6L", N_x=900 * kN, V_y=60 * kN, V_z=140 * kN)])
    node.check()

    for check in column.shear_checks:
        print(check.direction, check.DCR, check.reinforcement_required, check.A_v_req)

**The legs.** The perimeter tie gives two legs in each direction. A crosstie
is one leg, in the shear it crosses: ``crossties_width`` hold bars of the faces
of length ``width``, span the height and count in ``V_z``; ``crossties_height``
count in ``V_y``. A crosstie may be thinner than the tie (``d_b_crosstie``) and
still counts. Whether it is thick enough to brace its bar is a detailing rule,
which this check does not read.

**d.** From the compressed face to the centroid of the bars of the far face,
as for a beam: a column checked in one direction gives the same numbers as a
``RectangularBeam`` of the same rectangle where the clauses are the same.

A circular column
-----------------

.. code-block:: python

    from mento import CircularColumn

    column = CircularColumn(label="C2", concrete=concrete, steel_bar=steel,
                            diameter=50 * cm, c_c=30 * mm)
    column.set_longitudinal_rebar(n=8, d_b=20 * mm)
    column.set_hoops(d_b=10 * mm, s=15 * cm)

A circle is checked as ACI 318-19 §22.5.2.2 allows: ``b_w = D`` and
``d = 0.8·D``, with the gross area of the circle in the axial term, so a
circle in tension is checked as well as one in compression. A hoop counts as
two legs. The tension steel of ρ_w is the bars past the centre line,
``(n - 1) // 2`` of them.

What a column is checked for (ACI 318-19, CIRSOC 201-25)
--------------------------------------------------------

The resistance is the beam's -- V_c of Table 22.5.5.1 with ``N_u/(6·A_g)``,
V_s of §22.5.8.5.3, the section limit of §22.5.1.2. What the column reads
from its own chapter, the same clauses in both codes:

- **When shear reinforcement is required**: §10.6.2.1, ``Vu > 0.5·ØVc``, with
  the axial load in V_c. A beam is held to §9.6.3.1 instead, which ignores the
  axial load; a compressed column needs shear reinforcement later than a beam
  of the same section, a column in tension sooner.
- **How much**: there, the area the shear asks for and at least A_v,min of
  §10.6.2.2. Elsewhere ``A_v_req`` is zero.
- **How far apart**: there, Table 10.7.6.5.2 along the column (``s_max_l``)
  and between legs across it (``s_max_w``) -- the rows of Table 9.7.6.2.2,
  with the caps of each code: 600/300 mm under ACI 318-19, 400/200 mm under
  CIRSOC 201-25.
- The cap of 8.3 MPa on √f'c (§22.5.3.1) stays: §22.5.3.2 lifts it for beams
  and joists only.

Each result, :class:`~mento.column_results.ColumnShearCheck`, carries
``V_concrete`` (ØVc), ``reinforcement_required``, ``A_v``, ``A_v_req``,
``A_v_min``, ``V_capacity``, ``V_max``, the ``DCR`` and the spacings. The ties
of the detailing (ACI 318-19 §25.7.2) are required everywhere and are not
checked here.

EN 1992-1-1
-----------

A rectangle is checked as a beam of the same section -- V_Rd,c of
Expressions (6.2.a)/(6.2.b) with σ_cp, the truss of §6.2.3 at the strut angle
the demand fixes, V_Rd,max of Expression (6.9) -- with what a column is asked
for instead of what a beam is:

- **When shear reinforcement is required**: §6.2.1(3), ``VEd > VRd,c``. Below
  it a column is not held to the beam minimum of §9.2.2(5): its ties are those
  of §9.5.3, which this check does not read. ``A_v_min`` is zero.
- **How far apart**: there, §9.2.2(6) along the column and §9.2.2(8) across it.
- **α_cw** follows Expression (6.11aN) with the compression of each
  combination, σ_cp = N_Ed/A_c: ``1 + σ_cp/f_cd`` up to 0.25·f_cd, 1.25 up to
  0.5·f_cd, ``2.5·(1 - σ_cp/f_cd)`` up to f_cd. It raises V_Rd,max by up to
  25 % under moderate compression and lowers it past 0.6·f_cd. In tension it
  is 1. ``alpha_cw_from_axial_load=False`` keeps α_cw = 1, the value
  §6.2.3(3) Note 3 gives "for non-prestressed structures", at every
  compression -- unsafe past 0.6·f_cd:

  .. code-block:: python

      column = RectangularColumn(label="C1", concrete=concrete, steel_bar=steel,
                                 width=30 * cm, height=50 * cm, c_c=25 * mm,
                                 alpha_cw_from_axial_load=False)

**A circle.** EN 1992-1-1 has no clause for one. mento checks it by Orr,
Darby, Ibell, Denton and Shave, *Shear design of circular concrete sections
using the Eurocode 2 truss model*, The Structural Engineer 88(23-24), 2010:

- The truss of Expression (6.8) on the lever arm ``z`` between the chords,
  times the share of the link that crosses the shear: λ1 for a circular link
  (their Eq. (6), no more than the 0.85 of their Eq. (7)) and λ2 for a spiral
  (Eq. (9); ``set_hoops(..., spiral=True)``).
- V_Rd,max of Expression (6.9) on the web of their equivalent rectangle, the
  narrower of the section at the compression chord and inside the links at
  the tension chord (Eqs. (10)-(14)).
- V_Rd,c as §6.2.2(2) asks: Expression (6.4) -- Orr's Eq. (17),
  ``3πr²/4·√(f_ctd² + σ_cp·f_ctd)`` -- where the combination's flexural
  tension ``M/W − N/A_c`` stays within f_ctd, with ``M`` the resultant of
  ``M_y`` and ``M_z``; Expressions (6.2.a)/(6.2.b) on the equivalent rectangle
  where it does not. Expression (6.4) on a cracked circle gives about twice
  the cracked resistance at low axial load, which the clause does not allow.

``d`` (to the tension chord) and ``z`` come from a sectional analysis, which
mento does not run yet. By default the neutral axis is taken at the centre:
``d = r + 2·r_s/π``, the centroid of the bars of one half, and ``z = 0.77·d``,
the mean Orr et al. found over 38 tests. A sectional analysis can give its own
under the moment that governs:

.. code-block:: python

    column.set_lever_arm(d=42 * cm, z=33 * cm)   # EN 1992-1-1 only; ACI takes d = 0.8·D

Reports
-------

The shear of one combination, both directions, as console tables or a Word
document -- the combination that governs, or the one asked for -- in the
language set with :func:`mento.set_language`:

.. code-block:: python

    column.shear_results_detailed()             # the governing combination
    column.shear_results_detailed(forces[0])    # or this one
    column.shear_results_detailed_doc()         # "Column C1 shear check ACI 318-19.docx"
    column.data                                 # the inputs, one line (Jupyter)
    column.results                              # the governing combination, one line per direction

Each direction prints its limit checks (the area of the legs against what the
shear asks, the tie spacing, the legs across and the section's limit) and its
resistances, in the design code's symbols, ending on the DCR.

Warnings
--------

``column.warnings`` (or ``node.warnings``) lists what the ties miss, per
direction, in the language set with :func:`mento.set_language`:
``column_ties_below_required``, ``column_tie_spacing_exceeds_max``,
``column_leg_spacing_exceeds_max`` and ``column_shear_exceeds_section_limit``,
each with ``values["direction"]``. They are worded when read, so a loop that
only reads ``shear_check_results`` does not pay for them.
