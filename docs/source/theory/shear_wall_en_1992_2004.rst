Shear Wall — EN 1992-1-1:2004
=============================

Provisions implemented for ``ShearWall`` with ``Concrete_EN_1992_2004``, covering
**in-plane shear** per EN 1992-1-1:2004 §6.2, with the detailing rules for walls of
§9.6.

Scope
-----

**Implemented**: in-plane shear check and design — the resistance without shear
reinforcement, the variable-angle truss of the horizontal bars, the strut limit, the
minimum and maximum areas of both directions of the mesh, and their spacing.

.. warning::

   **Flexure and axial design are not implemented for walls.** The vertical mesh is
   designed to its minimum only. Also absent: the additional tensile force in the
   vertical reinforcement of Eq. (6.18), out-of-plane shear, the transverse links of
   §9.6.4 for a wall whose vertical reinforcement exceeds 0.02 :math:`A_c`, and the
   seismic walls of EN 1998-1.

How it differs from a beam
--------------------------

The resistances are those of the :doc:`EN beam <beam_en_1992_2004>` — Eq. (6.2.a)
and (6.2.b) for the concrete, the truss of Eq. (6.8) with the horizontal bars acting
as shear reinforcement at :math:`\alpha = 90°`, the strut of Eq. (6.9), and
:math:`1 \le \cot\theta \le 2.5`. What a wall changes is the section they are written
on and the reinforcement rules around them:

1. **Effective depth.** A beam reads :math:`d` off its bars. A wall has none at a
   fixed depth — its vertical bars are spread over its length — so mento takes
   :math:`d = 0.8\,l_w`, a design assumption EN 1992-1-1 does not give, and
   :math:`z = 0.9\,d` of §6.2.3(1). The beam's own :math:`d` would be the length less
   the cover, some 20 % deeper.
2. **Longitudinal ratio.** :math:`\rho_l` of Eq. (6.2.a) is the tension
   reinforcement at the end of the wall, which ``ShearWall`` does not declare. It is
   taken as zero, so Eq. (6.2.b) gives :math:`V_{Rd,c}`.
3. **Compression chord.** :math:`\alpha_{cw}` keeps the reduction of §6.2.3(3)
   Note 3 for a chord nearly crushed by the axial load, and none of its increases.
4. **Minimum shear reinforcement.** Eq. (9.5N) belongs to a beam (§9.2.2). A wall has
   the minima of §9.6, and asks for :math:`\rho_{w,min}` on top of them only once the
   truss carries the shear.
5. **The minima depend the other way round from ACI 318-19.** The horizontal minimum
   of §9.6.3(1) is a quarter of the vertical reinforcement the wall carries, so the
   design places the vertical mesh first and the horizontal one after it.

Symbols
-------

.. list-table::
   :header-rows: 1
   :widths: 16 44 40

   * - Symbol
     - Meaning
     - Source
   * - :math:`t`
     - Wall thickness (out-of-plane)
     - ``thickness``
   * - :math:`l_w`
     - Wall length (in-plane, resists shear)
     - ``length``
   * - :math:`A_c`
     - Gross concrete area, :math:`l_w t`
     - ``_A_c_wall``
   * - :math:`d,\ z`
     - Effective depth :math:`0.8\,l_w` and lever arm :math:`0.9\,d`
     - ``_d_wall``, ``_z_wall``
   * - :math:`A_{sh},\ A_{sv}`
     - Horizontal and vertical reinforcement per unit length of wall, both faces
       together
     - ``_A_sh_wall``, ``_A_sv_wall``
   * - :math:`f_{cd}`
     - :math:`f_{ck}/\gamma_c`, with :math:`\alpha_{cc} = 1` for shear, as for the beam
     - ``_f_cd_wall``
   * - :math:`f_{ywd}`
     - :math:`f_{yk}/\gamma_s` of the horizontal bars
     - ``_f_ywd_wall``

The wall height :math:`h_w` does not enter: the in-plane shear of EN 1992-1-1
depends on :math:`l_w` and :math:`t` alone.

Shear strength
--------------

Without shear reinforcement
^^^^^^^^^^^^^^^^^^^^^^^^^^^

§6.2.2(1), Eq. (6.2.a) floored by Eq. (6.2.b):

.. math::

   V_{Rd,c} = \max\Big(
       \big[C_{Rd,c}\,k\,(100\,\rho_l f_{ck})^{1/3} + k_1\sigma_{cp}\big]\,t\,d,\
       (v_{min} + k_1\sigma_{cp})\,t\,d\Big)

with :math:`k = 1 + \sqrt{200/d} \le 2`, :math:`v_{min} = 0.035\,k^{3/2} f_{ck}^{1/2}`,
:math:`\sigma_{cp} = N_{Ed}/A_c \le 0.2\,f_{cd}` (compression positive),
:math:`C_{Rd,c} = 0.18/\gamma_c` and :math:`k_1 = 0.15`. With :math:`\rho_l = 0` the
first term is :math:`k_1\sigma_{cp}\,t\,d`, below the second, and Eq. (6.2.b) governs.
A wall in net tension takes a negative :math:`\sigma_{cp}`, floored so that
:math:`V_{Rd,c} \ge 0`.

Strut
^^^^^

§6.2.3(2)-(3), Eq. (6.9) with :math:`\nu_1 = 0.6\,(1 - f_{ck}/250)` of Eq. (6.6N):

.. math::

   V_{Rd,max}(\theta) = \frac{\alpha_{cw}\, t\, z\, \nu_1 f_{cd}}{\cot\theta + \tan\theta}

The flattest strut that carries the demand is taken: :math:`\cot\theta = 2.5` while
:math:`V_{Rd,max}(\cot\theta = 2.5) \ge V_{Ed}`; otherwise the angle at which
Eq. (6.9) equals :math:`V_{Ed}`,
:math:`\theta = \tfrac{1}{2}\arcsin\big(V_{Ed}/V_{Rd,max}(45°)\big)`; and 45° past
:math:`V_{Rd,max}(45°)`, where the wall fails by the strut whatever its mesh. That
last value is the section limit ``shear_exceeds_section_limit`` reads.

Truss and design resistance
^^^^^^^^^^^^^^^^^^^^^^^^^^^

Eq. (6.8), the horizontal bars as vertical stirrups of a beam lying on its side:

.. math::

   V_{Rd,s} = A_{sh}\, z\, f_{ywd} \cot\theta

:math:`V_{Rd}` follows the clause that decides the demand, as for the EN beam. Under
:math:`V_{Rd,c}` the concrete carries the shear (§6.2.1(3)) and the wall resists the
larger of :math:`V_{Rd,c}` and its truss; past it the horizontal bars carry all of it
(§6.2.1(5)):

.. math::

   V_{Rd} = \begin{cases}
   \max\big(V_{Rd,c},\ \min(V_{Rd,s},\ V_{Rd,max})\big) & V_{Ed} \le V_{Rd,c} \\[2pt]
   \min(V_{Rd,s},\ V_{Rd,max}) & V_{Ed} > V_{Rd,c}
   \end{cases}

A wall with no horizontal bars resists :math:`V_{Rd,c}`. The DCR is
:math:`V_{Ed}/V_{Rd}`.

Required horizontal reinforcement
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. math::

   A_{sh,req} = \max\big(A_{sh,str},\ A_{sh,w},\ A_{sh,min}\big)

where, only when :math:`V_{Ed} > V_{Rd,c}`,

.. math::

   A_{sh,str} = \frac{V_{Ed}}{z\, f_{ywd} \cot\theta}
   \qquad
   A_{sh,w} = \rho_{w,min}\, t = \frac{0.08\sqrt{f_{ck}}}{f_{yk}}\, t

and both are zero otherwise.

Minimum and maximum reinforcement
---------------------------------

Vertical, §9.6.2(1):

.. math::

   0.002\,A_c \le A_{s,v} \le 0.04\,A_c

Horizontal, §9.6.3(1) — written on the vertical reinforcement the wall carries:

.. math::

   A_{s,h,min} = \max\big(0.25\,A_{s,v},\ 0.001\,A_c\big)

Per unit length of wall these read :math:`A_{sv,min} = 0.002\,t`,
:math:`A_{sv,max} = 0.04\,t` and :math:`A_{sh,min} = \max(0.25\,A_{sv},\ 0.001\,t)`.

Spacing limits
--------------

§9.6.2(3) for the vertical bars and §9.6.3(2) for the horizontal ones:

.. math::

   s_{v,max} = \min(3t,\ 400\ \text{mm})
   \qquad
   s_{h,max} = 400\ \text{mm}

Design
------

The design places the two directions in the order the minima depend on each other:

1. the vertical mesh at :math:`0.002\,A_c` and :math:`s_{v,max}` — shear asks nothing
   more of it, and flexure is not implemented;
2. the horizontal mesh at the largest :math:`A_{sh,req}` over the combinations, read
   with that vertical mesh in place, and :math:`s_{h,max}`.

:math:`\theta`, :math:`V_{Rd,c}` and :math:`A_{sh,str}` do not depend on the mesh, so
one pass settles both directions, and the design gives the same mesh every time it
runs. The bars are chosen by the same search as the ACI wall, scored for least steel
and then the smaller bar, with Ø12 as a soft crack-control cap.

Implementation decisions
------------------------

:math:`d = 0.8\,l_w`
^^^^^^^^^^^^^^^^^^^^

EN 1992-1-1 gives no effective depth for a wall. 0.8 :math:`l_w` is the usual
assumption for in-plane shear, and the one ACI 318 itself prescribed up to its 2011
edition. It is a constant, ``EFFECTIVE_DEPTH_RATIO`` in
``mento/codes/EN_1992_2004_wall.py``.

No end bars
^^^^^^^^^^^

:math:`\rho_l = 0` is conservative, and rarely costs anything: in a 4.0 × 0.20 m wall
in C25/30, 4Ø16 at the end give Eq. (6.2.a) = 140.6 kN against the 156.5 kN of
Eq. (6.2.b), so the floor governs anyway. :math:`V_{Rd,c}` only decides whether the
truss and :math:`\rho_{w,min}` are asked for, and the resistance under it.

:math:`\alpha_{cw}`
^^^^^^^^^^^^^^^^^^^

§6.2.3(3) Note 3 recommends 1 for non-prestressed structures, and for a chord under
axial compression :math:`1 + \sigma_{cp}/f_{cd}` up to :math:`0.25\,f_{cd}`, 1.25 up to
:math:`0.5\,f_{cd}`, and :math:`2.5\,(1 - \sigma_{cp}/f_{cd})` up to :math:`f_{cd}`. A
wall carries the compression of the storeys above without being prestressed, so mento
keeps the branch that lowers the strut and drops the two that raise it:

.. math::

   \alpha_{cw} = \max\Big(0,\ \min\big(1,\ 2.5\,(1 - N_{Ed}/(A_c f_{cd}))\big)\Big)

That is 1 for every wall under half of :math:`f_{cd}`, and the reduction where the
axial load alone nearly crushes the chord.

:math:`\rho_{w,min}` past :math:`V_{Rd,c}`
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

§9.6 does not ask a wall for the minimum shear reinforcement of Eq. (9.5N), which is
§9.2.2's, for beams. mento asks for it once :math:`V_{Ed} > V_{Rd,c}` and the
horizontal bars carry the shear as a truss — conservative, and in practice rarely
binding next to :math:`A_{s,h,min}`.

Bar catalogue
^^^^^^^^^^^^^

§9.6 states no bar diameter for a wall mesh. mento uses the catalogue of CIRSOC
201-25: Ø6 mm and up for the horizontal mesh, Ø10 mm and up for the vertical one —
above the 8 mm §9.5.2(1) recommends for the longitudinal bars of a column, the
nearest rule the code has.

Reinforcement on both faces
^^^^^^^^^^^^^^^^^^^^^^^^^^^

As for the ACI wall, the mesh is placed on both faces; :math:`A_{sh}` and
:math:`A_{sv}` count both curtains. §9.6.2(2) asks for half of
:math:`A_{s,v,min}` on each face where it governs, which two equal curtains meet.

Length to thickness
^^^^^^^^^^^^^^^^^^^

§5.3.1(7) defines a wall as a member at least four times as long as it is thick. A
shorter one is a column under EN 1992-1-1; the report's limit table marks it with a
❌, and the shear is still computed.

Validation
----------

Tests live in ``tests/elements/test_shear_wall_en.py`` and
``tests/equations/test_en_1992_2004_wall_equations.py``. The reference case is the
default of the Calcpad sheet "HOR_Tabiques_Cortante_EN_1992-1-1_2004_v1", worked by
hand at the head of the test module; a reproduction, so these are regression tests.

.. list-table::
   :header-rows: 1
   :widths: 30 40 30

   * - Check
     - Test
     - Verified against
   * - :math:`A_c`, :math:`d`, :math:`z`, :math:`k`, :math:`f_{cd}`, :math:`f_{ywd}`
     - ``test_section``
     - Calcpad (regression)
   * - :math:`V_{Rd,c}`, Eq. (6.2.b)
     - ``test_concrete_resistance_is_the_floor_of_eq_6_2b``
     - Calcpad (regression)
   * - Strut, :math:`\cot\theta = 2.5`, section limit at 45°
     - ``test_strut``
     - Calcpad (regression)
   * - :math:`V_{Rd,s}`, :math:`V_{Rd}`, DCR
     - ``test_truss_and_dcr``, ``test_public_result``
     - Calcpad (regression)
   * - :math:`A_{sh,str}`, :math:`A_{sh,w}`, :math:`A_{sh,min}`, :math:`A_{sv}` limits
     - ``test_reinforcement_required``
     - Calcpad (regression)
   * - Under :math:`V_{Rd,c}`: no truss, no :math:`\rho_{w,min}`
     - ``test_under_the_concrete_resistance_no_truss_is_asked_for``
     - §6.2.1(3)
   * - Variable strut angle, and past the strut
     - ``test_the_strut_angle_follows_the_demand``,
       ``test_past_the_strut_the_wall_fails_whatever_its_mesh``
     - Eq. (6.9)
   * - Axial load: :math:`\sigma_{cp}` and its cap, :math:`\alpha_{cw}`
     - ``test_compression_raises_the_concrete_resistance``,
       ``test_high_compression_is_capped_and_reduces_the_strut``,
       ``test_tension_lowers_the_concrete_resistance``,
       ``TestCompressionChordCoefficient``
     - §6.2.2(1), §6.2.3(3)
   * - Limits of §9.6
     - ``test_vertical_minimum_is_0_002_t``,
       ``test_vertical_maximum_is_0_04_t``,
       ``test_horizontal_minimum_takes_a_quarter_of_the_vertical``,
       ``test_horizontal_minimum_floor_is_0_001_t``,
       ``test_vertical_spacing_thin_wall``, ``test_vertical_spacing_capped_at_400``
     - §9.6.2, §9.6.3
   * - Warnings
     - ``test_vertical_mesh_above_the_maximum``,
       ``test_the_spacing_warnings_quote_the_eurocode``
     - §9.6.2(1), §9.6.2(3), §9.6.3(2)
   * - Design: order, worst combination, every limit met, idempotent
     - ``test_the_calcpad_wall``, ``test_the_design_takes_the_worst_combination``,
       ``test_the_design_meets_every_limit_it_checks``,
       ``test_designing_twice_gives_the_same_mesh``
     - Internal consistency
