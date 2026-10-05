Coordinate System
===================================

The local coordinate system of a structural member is a dextrorotary Cartesian system with the following orientation of axes:

- The local **x-axis** is always the longitudinal axis of the element, defined from the **beginning node (A)** to the **end node (B)**. The origin of the system is positioned at the beginning node of the member.

- The local **y-axis** and **z-axis** lie in the plane of the member's cross-section and are arranged according to dextrorotary rotation. By default:

  - The **y-axis** represents the axis of the greater moment of inertia of the member.
  - The **z-axis** represents the axis of the lesser moment of inertia of the member.

.. figure:: ../_static/local_axes/element_axes.jpeg
   :alt: Element local axes.
   :align: center
   :width: 70%

Sectional Analysis
------------------

For sectional analysis, the local **y-axis** and **z-axis** are critical for understanding the orientation of the member's cross-section.
Below is an illustration of the cross-section with the local **y-axis** and **z-axis**:

.. figure:: ../_static/local_axes/section_axes.png
   :alt: Cross-section of a member with local y and z axes
   :align: center
   :width: 25%

Sign Convention
---------------

The sign of each force component is not merely descriptive — it changes the result of
a check, so it must match the convention below.

.. list-table::
   :header-rows: 1
   :widths: 15 25 60

   * - Component
     - Positive means
     - Effect on the design
   * - ``N_x``
     - **Compression**
     - Compression adds to the concrete shear strength; tension (a negative
       ``N_x``) subtracts from it.
   * - ``M_y``
     - **Sagging** (tension at the bottom fibre)
     - Selects which face is the tension face: a positive ``M_y`` designs the
       bottom reinforcement, a negative ``M_y`` the top.
   * - ``V_z``
     - **Magnitude of the design shear**
     - Shear is checked against a symmetric resistance, so its direction does not
       change the outcome. Always pass it as a positive value.
   * - ``M_z``
     - **Compresses the −y face**
     - Bending about the z-axis. Not read by beams, slabs or walls; it is there for
       the biaxial demand of a column or a wall section.
   * - ``V_y``
     - Shear along the y-axis
     - Not read by beams, slabs or walls.
   * - ``M_x``
     - **Torsion** on a member
     - The moment about the member axis. Not read by beams yet. At a punching node it
       is an in-plane moment instead; see below.

These six components are the member forces of a frame model, in the same order: a
program's FX, FY, FZ, MX, MY, MZ in the member's local axes are ``N_x``, ``V_y``,
``V_z``, ``M_x``, ``M_y``, ``M_z``, with **z pointing up** in the section. With z up,
``M_y > 0`` compresses the +z face, which is the sagging moment of the table above.
Check the sign of FX in your program: mento takes compression as positive.

Axial force
***********

``N_x`` is **positive in compression** and negative in tension. This follows the axial
term of both implemented codes, which is added to the concrete contribution:

- ACI 318-19 §22.5.5.1 — :math:`\sigma_{Nu} = N_u / (6 A_g)`, capped at :math:`0.05 f'_c`.
- EN 1992-1-1 §6.2.2(1) — :math:`\sigma_{cp} = N_{Ed} / A_c`, capped at :math:`0.2 f_{cd}`.

A tensile axial force therefore reduces the concrete shear strength, which is the
intended behaviour. Passing a tension force as a positive number is unconservative.

Bending moment
**************

``M_y`` is **positive when it produces tension at the bottom** of the section (sagging).
The check uses the sign to pick the tension face, so a support moment must be entered as
negative for the top reinforcement to be designed.

Shear force
***********

``V_z`` is the design shear at the section under consideration. The demand-capacity ratio
is formed from its absolute value, so a sign error does not change a *check* — but the
*design* routine sizes stirrups from the largest required :math:`A_v` across the load
combinations, and a negative ``V_z`` would be read as a smaller demand. Always enter
shear as a positive magnitude.

Punching shear nodes
--------------------

A :class:`~mento.punching.PunchingNode` is not a member but a column-to-slab connection,
so it reads a different subset of the same ``Forces`` object:

.. list-table::
   :header-rows: 1
   :widths: 15 85

   * - Component
     - At a punching node
   * - ``V_z``
     - The **design punching load**: the vertical force transferred at the connection.
       This is what both codes call the demand — ``V_u`` in ACI 318-19 §22.6, ``V_Ed``
       in EN 1992-1-1 §6.4 — so it is named after the symbol you are reading in the
       clause. Enter it as a positive magnitude.
   * - ``M_x``, ``M_y``
     - The **unbalanced moments** transferred to the slab, about its two in-plane axes.
       Biaxial transfer is the normal case at a corner column, so both are read.
   * - ``N_x``
     - **Not used.** The column's axial force is usually where ``V_z`` comes from, but
       that is a modelling step, not the demand itself; see below.

Taking the column's axial load as the punching load is a simplification, and a common
one — both codes allow the load acting *inside* the control perimeter to be deducted
(EN 1992-1-1 §6.4.3(3) writes it ``V_Ed,red``), and at an edge or corner column the two
are not the same number anyway. mento takes ``V_z`` as the design punching load you have
already worked out, whichever way you worked it out.

Note that ``M_x`` means something different here than on a member, where a moment about
the longitudinal axis is torsion. At a punching node there is no longitudinal axis, and
``M_x`` is an in-plane moment on the slab.
