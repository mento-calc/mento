Shear Wall
==========

The `ShearWall` class models a reinforced-concrete structural wall for **in-plane
shear analysis and design** per ACI 318-19 Chapter 11, CIRSOC 201-25 Chapter 11
and EN 1992-1-1 §6.2 with the wall detailing of §9.6. The design code is the one
the ``Concrete`` declares; the sections below describe ACI 318-19, and
:ref:`shear-wall-en` lists what changes under the Eurocode.

- Concrete shear capacity follows ACI 318-19 Eq. (11.5.4.3) with the aspect-ratio
  factor ``α_c`` defined under it, instead of a longitudinal-reinforcement term,
  capped by §11.5.4.2.
- Reinforcement is **distributed mesh** in two orthogonal directions
  (``ρt`` horizontal, ``ρl`` vertical), placed on **both faces** of the wall
  (E.F. — each face), not stirrups.
- The minimum horizontal ratio is ``ρt,min = 0.0025`` (§11.6.2(b)). The minimum
  vertical ratio follows §11.6.2(a): Eq. (11.6.2) with the horizontal ratio the
  wall **provides**, never below 0.0025 and never above the ``ρt`` the shear
  requires —
  ``ρl,min = max(0.0025, min(0.0025 + 0.5·(2.5 − hw/lw)·(ρt − 0.0025), ρt,req))``,
  with ``hw/lw`` clamped to ``[0.5, 2.5]``. A horizontal mesh heavier than the
  shear needs therefore asks for a heavier vertical mesh, up to ``ρt,req``.

The same shear provisions serve both **ACI 318-19** and **CIRSOC 201-25**;
CIRSOC differs in the reinforcing-bar catalogue used for design (it allows
Ø6 mm for the transverse mesh and Ø10 mm minimum for the vertical mesh) and in
the divisor of Eq. (11.5.4.4) for a wall in net axial tension (3.5·Ag against
ACI's 3.45·Ag).

.. note::

    The module covers **shear check and design only**. Flexure design
    for shear walls is not implemented yet. Inherited flexure methods from
    ``RectangularBeam`` are not validated for wall geometry and should not be
    used. The beam's results are not offered at all: ``wall.reinforcement``,
    ``wall.flexure_design`` and ``wall.flexure_checks`` raise ``NotABeamError``,
    an ``AttributeError`` (so ``hasattr`` is ``False`` and ``getattr`` takes its
    default) that points to ``wall.mesh``, ``wall.shear_design`` and
    ``wall.shear_checks``.

Key Concepts
------------

- **Geometry**:

  - ``thickness`` (*t*) — out-of-plane dimension
  - ``length`` (*lw*) — in-plane length, resists in-plane shear
  - ``height`` (*hw*) — the height of the **entire wall** from base to top, or the
    clear height of the wall segment or pier considered (ACI 318-19 / CIRSOC 201-25
    Chapter 2). It is **not** the storey height of a multi-storey wall: ``hw / lw``
    sets ``α_c`` and ``ρl,min``, and a storey height in its place makes a slender
    wall look squat and overstates ``ØVn``.

- **Material Properties**: requires a ``Concrete`` object
  (``Concrete_ACI_318_19``, ``Concrete_CIRSOC_201_25`` or
  ``Concrete_EN_1992_2004``) and a ``SteelBar`` object.

- **Reinforcement**: distributed bars defined by **bar diameter + spacing**
  in each direction.

- **Forces**: a list of ``Forces`` objects passed to ``check_shear()`` or
  ``design_shear()`` — either directly on the wall or through a ``Node``.
  ``V_z`` is the in-plane lateral shear demand at the section.

Usage
-----

Below is a step-by-step guide on how to use the ``ShearWall`` class.

1. Creating a Shear Wall Object
*******************************

Specify the geometry, materials, and clear cover using the wall-friendly
constructor parameters ``thickness``, ``length``, and ``height``.

.. code-block:: python

    from mento import ShearWall, Concrete_ACI_318_19, SteelBar
    from mento import MPa, cm, mm, m

    concrete = Concrete_ACI_318_19(name="H25", f_c=25 * MPa)
    steel    = SteelBar(name="ADN 420", f_y=420 * MPa)

    wall = ShearWall(
        label="W1",
        concrete=concrete,
        steel_bar=steel,
        thickness=25 * cm,   # t
        length=4.0 * m,      # lw (in-plane length)
        height=3.5 * m,      # hw (height of the whole wall; hw/lw = 0.875)
        c_c=20 * mm,
    )

After construction, the dimensions are accessible as ``wall.thickness``,
``wall.length``, and ``wall.height``.

2. Setting the Distributed Reinforcement
****************************************

Use ``set_horizontal_rebar(d_b, s)`` for the horizontal (transverse) mesh that
resists in-plane shear, and ``set_vertical_rebar(d_b, s)`` for the vertical
(longitudinal) mesh. The mesh is placed on **both faces** of the wall (E.F. —
each face), so the reinforcement ratio counts both curtains:
``ρ = 2 · Ab / (t × s)``.

.. code-block:: python

    # Ø12 @ 150 mm in both directions
    wall.set_horizontal_rebar(d_b=12 * mm, s=150 * mm)
    wall.set_vertical_rebar(d_b=12 * mm, s=150 * mm)

3. Performing the Shear Check
*****************************

Call ``check_shear()`` with a list of ``Forces`` — either directly on the wall
or through a ``Node``. The returned DataFrame has one header row (units)
followed by one row per combination.

.. code-block:: python

    from mento import Forces, Node, kN

    f1 = Forces(label="1.2D+1.0E", V_z=800  * kN)
    f2 = Forces(label="0.9D+1.0E", V_z=1200 * kN)

    # Directly on the wall ...
    wall.check_shear([f1, f2])

    # ... or via a Node (recommended — enables results / detailed reports)
    node = Node(section=wall, forces=[f1, f2])
    node.check()
    node.results

Returned columns:

+--------------+-----------------------------------------------------+
| Column       | Meaning                                             |
+==============+=====================================================+
| ``ρt,min``   | Minimum horizontal reinforcement ratio (0.0025)     |
+--------------+-----------------------------------------------------+
| ``ρt,req``   | Required horizontal reinforcement ratio             |
+--------------+-----------------------------------------------------+
| ``ρt``       | Provided horizontal reinforcement ratio             |
+--------------+-----------------------------------------------------+
| ``ρl,min``   | Minimum vertical reinforcement ratio                |
+--------------+-----------------------------------------------------+
| ``ρl``       | Provided vertical reinforcement ratio               |
+--------------+-----------------------------------------------------+
| ``Vu``       | Demand shear                                        |
+--------------+-----------------------------------------------------+
| ``ØVc``      | Concrete shear strength (factored)                  |
+--------------+-----------------------------------------------------+
| ``ØVs``      | Steel shear strength (factored)                     |
+--------------+-----------------------------------------------------+
| ``ØVn``      | Total nominal shear strength (factored)             |
+--------------+-----------------------------------------------------+
| ``ØVn,max``  | Section-crushing limit (factored)                   |
+--------------+-----------------------------------------------------+
| ``DCR``      | Demand-to-capacity ratio                            |
+--------------+-----------------------------------------------------+

4. Designing the Shear Reinforcement
************************************

``design()`` is fully automatic: it sizes **both** meshes against the
worst-case force combination, applies them to the wall, and returns the
re-evaluated check DataFrame.

.. code-block:: python

    result = wall.design([f1, f2])
    # The wall now carries a designed mesh:
    print(wall._d_b_h, wall._s_h)   # horizontal (shear) bar + spacing
    print(wall._d_b_v, wall._s_v)   # vertical (minimum) bar + spacing

What it does:

1. Runs the check for every force and tracks the worst-case ``ρt,req``.
2. Selects a bar diameter and spacing for the **horizontal mesh** (against
   ``ρt,req``) and applies it via ``set_horizontal_rebar``.
3. Derives the worst-case ``ρl,min`` from §11.6.2(a) with the ``ρt`` that mesh
   provides, capped by ``ρt,req``.
4. Selects the **vertical mesh** (against ``ρl,min``), applies it via
   ``set_vertical_rebar`` and re-runs the check.


**Vertical mesh.** Because for now *mento* does not check flexure, the vertical mesh
is always sized to the §11.6.2 *minimum* — it is reported and plotted as
"Minimum vertical rebar".

.. note::

    For **CIRSOC 201-25**, ``design`` automatically uses the CIRSOC bar
    catalogue (Ø6 mm minimum transverse, Ø10 mm minimum vertical). No extra
    configuration is needed — the design code is read from the ``Concrete``
    object.

.. _shear-wall-en:

EN 1992-1-1
***********

With ``Concrete_EN_1992_2004`` the same calls check and design the wall per
EN 1992-1-1. The resistances are those of an EN beam — ``VRd,c`` of Eq. (6.2.a/b),
the truss of the horizontal bars, Eq. (6.8), and the strut, Eq. (6.9) — written on
the wall: ``d = 0.8·lw`` and ``z = 0.9·d``, no end bars (so ``VRd,c`` is the floor of
Eq. (6.2.b)), and the limits of §9.6 instead of a beam's. The theory page
:doc:`/theory/shear_wall_en_1992_2004` gives every equation and decision.

.. code-block:: python

    from mento import ShearWall, Concrete_EN_1992_2004, SteelBar, Forces, Node
    from mento import MPa, cm, mm, m, kN

    wall = ShearWall(
        label="W1",
        concrete=Concrete_EN_1992_2004(name="C25/30", f_c=25 * MPa),
        steel_bar=SteelBar(name="B500S", f_y=500 * MPa),
        thickness=20 * cm,
        length=4.0 * m,
        height=3.0 * m,      # not read by EN: the shear depends on lw and t
        c_c=25 * mm,
    )
    node = Node(section=wall, forces=[Forces(label="ULS", V_z=1200 * kN)])
    node.design()
    wall.mesh                 # horizontal: 2×Ø8 mm/25 cm / vertical: 2×Ø10 mm/37 cm
    wall.shear_design.DCR     # 0.953

What changes:

- **Columns.** ``check_shear`` reports the mesh as areas per unit length of wall,
  both faces together, in cm²/m — ``Ash,min``, ``Ash,req``, ``Ash``, ``Asv,min``,
  ``Asv`` — and the resistances as ``VRd,c``, ``VRd,s``, ``VRd`` and ``VRd,max``
  against ``VEd`` and ``NEd``.
- **Limits.** ``Asv`` between 0.002 and 0.04 of the gross area (§9.6.2(1)), ``Ash``
  at least a quarter of ``Asv`` and 0.001 of the gross area (§9.6.3(1)), vertical
  bars at most ``min(3t, 400 mm)`` apart (§9.6.2(3)) and horizontal ones 400 mm
  (§9.6.3(2)). Past ``VRd,c`` the horizontal bars also carry ``ρw,min`` of
  Eq. (9.5N).
- **Design order.** The horizontal minimum reads the vertical mesh, so the design
  places the vertical mesh first — at its minimum — and the horizontal one after
  it, the reverse of ACI.
- **Bars.** The CIRSOC catalogue: Ø6 mm and up for the horizontal mesh, Ø10 mm and
  up for the vertical one.
- **Public results.** ``wall.shear_checks`` keep their names: ``V_u`` is ``VEd``,
  ``V_capacity`` is ``VRd`` and ``V_max`` is ``VRd,max`` at 45°, the most the wall
  can carry. ``rho_l_max`` carries the 0.04 of §9.6.2(1); it is ``None`` under ACI.

5. Inspecting Intermediate Quantities
*************************************

After running a check, the relevant ACI 318-19 quantities are available as
attributes on the wall:

+----------------------+----------------------------------------------+
| Attribute            | Meaning                                      |
+======================+==============================================+
| ``_hw_lw``           | Aspect ratio ``hw / lw``                     |
+----------------------+----------------------------------------------+
| ``_alpha_c``         | ``α_c`` factor (0.25 → 0.17 metric)          |
+----------------------+----------------------------------------------+
| ``_Acv``             | Gross shear area ``lw × t``                  |
+----------------------+----------------------------------------------+
| ``_V_c_wall``        | Nominal concrete shear strength              |
+----------------------+----------------------------------------------+
| ``_V_s_wall``        | Nominal steel shear strength                 |
+----------------------+----------------------------------------------+
| ``_phi_V_n_wall``    | Factored total shear strength                |
+----------------------+----------------------------------------------+
| ``_phi_V_n_max_wall``| Factored crushing-limit shear strength       |
+----------------------+----------------------------------------------+
| ``_DCRv_wall``       | Demand-to-capacity ratio for shear           |
+----------------------+----------------------------------------------+
| ``_rho_t_req``       | Required horizontal reinforcement ratio      |
+----------------------+----------------------------------------------+
| ``_rho_l_min``       | Minimum vertical reinforcement ratio         |
+----------------------+----------------------------------------------+
| ``_s_h_max``         | §11.7.3.1 horizontal spacing limit           |
+----------------------+----------------------------------------------+
| ``_s_v_max``         | §11.7.2.1 vertical spacing limit             |
+----------------------+----------------------------------------------+
| ``_d_b_h`` / ``_s_h``| Designed horizontal bar diameter / spacing   |
+----------------------+----------------------------------------------+
| ``_d_b_v`` / ``_s_v``| Designed vertical bar diameter / spacing     |
+----------------------+----------------------------------------------+

All reinforcement ratios (``ρt``, ``ρl``) account for the mesh on **both
faces** — ``ρ = 2 · Ab / (t · s)``.

A worked example with full output is available in the
:doc:`Shear Wall ACI 318-19 example </examples/shear_wall_check_ACI_318-19>`, and
for EN 1992-1-1 in the :doc:`check </examples/shear_wall_check_EN_1992-1-1>` and
:doc:`design </examples/shear_wall_design_EN_1992-1-1>` examples.
