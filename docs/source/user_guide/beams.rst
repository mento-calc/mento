Beam
==========

The `Beam` class in the `mento` package is designed to model and analyze rectangular reinforced concrete beams.
It allows users to define the geometry, material properties, reinforcement and custom settings.

Key Concepts
------------

- **Beam Geometry**: Defined by `width` and `height`.
- **Material Properties**: Requires a `Concrete` object (e.g., `Concrete_ACI_318_19`) and a `SteelBar` object for reinforcement.
- **Reinforcement**: Longitudinal and transverse reinforcement can be defined using `set_longitudinal_rebar_bot`, `set_longitudinal_rebar_top`, and `set_transverse_rebar`.
- **Custom settings**: A `Beam` object can have custom settings overriding the default settings of `mento`.

Usage
-----

Below is a step-by-step guide on how to use the `Beam` class in your design workflows.

1. Creating a Beam Object
*************************

To define a beam, you need to specify its geometry, material properties, and clear cover.
The `RectangularBeam` class is used for this purpose. If no custom settings are passed to the *Beam* object, it will take the default values.

.. image:: ../_static/beam/beam.png
   :alt: Beam cross section.
   :width: 250px
   :align: center

.. code-block:: python

    from mento import Concrete_ACI_318_19, SteelBar, RectangularBeam, mm, cm, kN, MPa

    # Define materials
    concrete = Concrete_ACI_318_19(name="C25", f_c=25*MPa)
    steel = SteelBar(name="ADN 420", f_y=420*MPa)

    # Define beam geometry
    beam = RectangularBeam(label="101", concrete=concrete, steel_bar=steel, width=20*cm, height=60*cm, c_c = 2.5*cm)

2. Setting Reinforcement
************************

You can define the longitudinal and transverse reinforcement for the beam using the following methods:

- **Bottom Longitudinal Reinforcement**: Use `set_longitudinal_rebar_bot`.
- **Top Longitudinal Reinforcement**: Use `set_longitudinal_rebar_top`.
- **Transverse Reinforcement (Stirrups)**: Use `set_transverse_rebar`.

.. note::
    Consider that:

    - If no transverse reinforcement is defined, it is assumed that plain concrete will resist shear forces.
    - If no longitudinal reinforcement is defined, a minimum of 2Ø8 will be considered for metric system or 2#3 for imperial system of units. Mento won't check a beam without longitudinal rebar.
    - Skin rebar is not considered for the check or design of the beam.

**Transverse reinforcement**
This is set indicating amount of stirrups, the diameter of the stirrups and the spacing of the stirrups along the beam.

**Longitudinal reinforcement**
This is set indicating rebar for two layers, differentiating between border bars and inner bars.
Each group of bars, for each layer has a unique number id. Bars can be defined both for top and bottom of the beam,
which will be considered for negative and positive bending moments respectively.

In case a flexure analysis requires compression reinforcement additional to the tension reinforcement, the opposite reinforcement will be considered.
For example, if a positive moment is so large that the section must be reinforced at top&bottom, the top rebar will also be considered in the beam capacity for flexure.

.. image:: ../_static/beam/beam_long_rebar.png
   :alt: Beam longitudinal rebar layout.
   :width: 700px
   :align: center

.. code-block:: python

    # Set bottom longitudinal reinforcement: two layers
    beam.set_longitudinal_rebar_bot(n1=2, d_b1=16*mm, n2=1, d_b2=12*mm, n3=2, d_b3=12*mm, n4=1, d_b4=10*mm)

    # Set top longitudinal reinforcement
    beam.set_longitudinal_rebar_top(n1=2, d_b1=16*mm)

    # Set transverse reinforcement (stirrups)
    beam.set_transverse_rebar(n_legs=2, d_b=10*mm, s_l=20*cm)

3. Assigning Forces to the Beam
*******************************

Forces are applied to the beam through a `Node` object, which joins the `Beam` and `Forces` object together.
See the `Node` section for more information on how to create a `Node` and assign forces to the section.


4. Performing Checks
********************

Once the beam is defined and forces are assigned in a `Node` object, you can perform checks for shear and flexure.
See the `Node` section for more information on how to create a Node and check the section.

5. Design the section
*********************

If you don't assign transverse or longitudinal rebar, you can ask *Mento* to design for shear and flexure.
See the `Node` section for more information on how to create a Node and design the section.

6. Jupyter Notebook Results
***************************

After performing the checks, you can view the results in a formatted way in a Notebook.

When you run `node.results`, the output includes:

- **Top and bottom longitudinal reinforcement**.
- **Shear reinforcement**.
- **Applied moments and shear forces**.
- **Design capacity ratios (DCR)**.
- **Warnings** (if any).

Transverse reinforcement can be entered directly as an even number of legs:

.. code-block:: python

    beam.set_transverse_rebar(n_legs=4, d_b=8*mm, s_l=20*cm)

Legacy ``n_stirrups=2`` still means four legs, including positional calls.
If both counts are provided they must satisfy ``n_legs = 2*n_stirrups``;
conflicting, fractional, negative or odd leg counts raise an error. Zero
legs with zero diameter and spacing clears the reinforcement.

The output is formatted using LaTeX math notation for clarity and precision.


Example Output
--------------

Here’s an example of the output from `beam.results`, for the beam set up above checked under two
combinations, :math:`M_u = -80 \, \textsf{kNm}` with :math:`V_u = 80 \, \textsf{kN}`, and
:math:`M_u = 90 \, \textsf{kNm}`:

.. math::

    \textsf{Beam 101}, \, b = 20.00 \, \textsf{cm}, \, h = 60.00 \, \textsf{cm}, \, c_{\text{c}} = 2.50 \, \textsf{cm}, \, \textsf{Concrete C25}, \, \textsf{Rebar ADN 420}.

    \textsf{Top longitudinal rebar: } 2\phi16, \, A_{s,\text{top}} = 4.02 \, \textsf{cm}^2, \, M_u = -80 \, \textsf{kNm}, \, \phi M_n = 81.65 \, \textsf{kNm} \rightarrow \textsf{DCR} = 0.98

    \textsf{Bottom longitudinal rebar: } 2\phi16 + 1\phi12 ++ 2\phi12 + 1\phi10, \, A_{s,\text{bot}} = 8.2 \, \textsf{cm}^2, \, M_u = 90 \, \textsf{kNm}, \, \phi M_n = 155.7 \, \textsf{kNm} \rightarrow \textsf{DCR} = 0.58

    \textsf{Shear reinforcing: 2 legs } \phi10 \, \textsf{mm @ 20 cm} \cdot \textsf{14 cm between legs (max 54.29 cm)}, \, A_v = 7.85 \, \textsf{cm}^2/\textsf{m}, \, V_u = 80 \, \textsf{kN}, \, \phi V_n = 203.52 \, \textsf{kN} \rightarrow \textsf{DCR} = 0.39


Interpreting the Output
-----------------------

**Geometry and Materials**

The first line provides the beam's geometry and material properties:

- **Beam 101**: Beam identifier.
- :math:`b = 20.00 \, \textsf{cm}`: Beam width.
- :math:`h = 60.00 \, \textsf{cm}`: Beam height.
- :math:`c_{\text{c}} = 2.50 \, \textsf{cm}`: Concrete clear cover.
- **Concrete C25**: Concrete grade.
- **Rebar ADN 420**: Rebar grade.

**Longitudinal Reinforcement**

- **Top longitudinal rebar**: Reinforcement at the top of the beam.

  - :math:`2\phi16``: 2 bars of 16 mm diameter.
  - :math:`A_{s,\text{top}} = 4.02 \, \textsf{cm}^2`: Area of top reinforcement.
  - :math:`M_u = -80 \, \textsf{kNm}`: Applied moment at the top.
  - :math:`\phi M_n = 81.65 \, \textsf{kNm}`: Design moment capacity at the top.
  - :math:`\textsf{DCR} = 0.98`: Design capacity ratio :math:`\textsf{DCR} = M_u / \phi M_n`.

- **Bottom longitudinal rebar**: Reinforcement at the bottom of the beam.

  - :math:`2\phi16 + 1\phi12 ++ 2\phi12 + 1\phi10`: Combination of bars.
  - :math:`A_{s,\text{bot}} = 8.2 \, \textsf{cm}^2`: Area of bottom reinforcement.
  - :math:`M_u = 90 \, \textsf{kNm}`: Applied moment at the bottom.
  - :math:`\phi M_n = 155.7 \, \textsf{kNm}`: Design moment capacity at the bottom.
  - :math:`\textsf{DCR} = 0.58`: Design capacity ratio :math:`\textsf{DCR} = M_u / \phi M_n`.

**Shear Reinforcement**

- **Shear reinforcing**: Shear reinforcement details.

  - ``2 legs Ø10 mm @ 20 cm · 14 cm between legs (max 54.29 cm)``: one closed stirrup of
    10 mm, so two legs across the shear plane, every 20 cm along the beam; the legs are
    14 cm apart across the width, against the 54.29 cm Table 9.7.6.2.2 allows.
  - :math:`A_v = 7.85 \, \textsf{cm}^2/\textsf{m}`: Area of shear reinforcement per meter.
  - :math:`V_u = 80 \, \textsf{kN}`: Applied shear force.
  - :math:`\phi V_n = 203.52 \, \textsf{kN}`: Design shear capacity.
  - :math:`\textsf{DCR} = 0.39`: Design capacity ratio :math:`\textsf{DCR} = V_u / \phi V_n`.

- **Check DCR Values**: A DCR less than 1.0 indicates that the beam is safe under the applied loads.
- **Review Warnings**: If the output includes warnings, review the design to ensure compliance with code requirements. You can check detailed results for more information.

7. Detailed Results
*******************

See the `Node` section for more information on how to display and save detailed results of the analysis.

8. Plot section
*******************

You can use the method `plot()` to visualize the beam's cross-section and reinforcement layout.

.. code-block:: python

  # Plot the beam section
  beam.plot()

The `plot()` method generates a graphical representation of the beam, including its geometry and reinforcement details.
This can be useful for verifying the input data and for presentation purposes.

The drawing reads ``beam.detailing_geometry`` (see :ref:`user_guide/design_results`):
every stirrup of the cage at the legs the shear check spreads across the width,
the resistant bars placed to support the corners, the label of
each layer on the right, and under the section the stirrup text in three lines -- legs,
bar and spacing; the spacing of the legs with its maximum once a shear check has run; and
the arrangement of the cage -- in the language of ``mento.set_language``. The limits of the
drawing are widened until every text fits the figure at its default size, and two layer
labels that would print over one another are moved apart. Where calculated bars are
insufficient to support all corners, additional mounting bars are drawn in orange and
labelled separately. Their diameter is ``settings.mounting_bar_diameter`` (10 mm or
No. 3 by default). These bars are not credited in the calculated resistance.

The supported layout preserves the calculated bar counts, diameters and vertical
coordinates, and the shear leg spacing. It checks clear spacing, the existing code's
centre-distance cap, and intersections with the branches and rounded bends. If no
supported layout is found, ``detailing_geometry`` raises ``CageDetailingError``;
``plot()`` issues a warning and draws the calculation model with an explicit caption.
A narrow stirrup is not presented as a valid hairpin by squeezing its bends.
Its rejected stirrups are omitted from the fallback drawing. Invalid mounting
diameter preferences raise ``ValueError`` rather than being presented as a
physically infeasible cage.

The inside bend diameter comes from the code: ACI/CIRSOC Table 25.3.2 uses
four bar diameters through 16 mm (No. 5 in US customary units), then six
through 25 mm (No. 8); larger transverse bars are not supported by this
table. EN Table 8.1N uses its recommended values of four diameters through
16 mm and seven above. Using four diameters for CIRSOC 6/8 mm stirrups is
a Mento extrapolation, since its bend table starts at 10 mm. These mandrel
sizes do not verify concrete failure at bends (EN Eq. 8.1), hooks or anchorage.

The tension-bar spacing limit is applied only to faces put in tension by the
verified load combinations. If flexure has not been checked, the drawing checks
physical fit and labels tension-bar spacing as pending; it does not infer tension
on both faces. ``Node.check_flexure()`` / ``Node.check()`` already report excessive
spacing on the tension face of each combination, and the detailing layout also
checks the moved resistant bars. Mounting bars cannot satisfy that limit in place
of resistant steel. For a single resistant bar, the face width is checked against
the available limit.

This is a cross-section layout, rather than a complete bending schedule: development
lengths, hook details and seismic detailing are not added by this operation. The
original, uniformly spaced calculation geometry remains ``beam.section_geometry``.

For example, a 50 x 60 cm beam with seven bottom bars, three top bars and four
stirrup legs receives one supplementary upper mounting bar. The default Ø10
mounting bar is shown separately from the three Ø16 resistant bars. Positive
and negative moments verify both tension faces:

.. code-block:: python

    from mento import (
        Concrete_CIRSOC_201_25, RectangularBeam, SteelBar, Forces, Node,
        MPa, cm, mm, kN, kNm,
    )

    beam = RectangularBeam(
        label="7 bottom + 3 top / 4 legs",
        concrete=Concrete_CIRSOC_201_25(name="H25", f_c=25*MPa),
        steel_bar=SteelBar(name="ADN420", f_y=420*MPa),
        width=50*cm, height=60*cm, c_c=30*mm,
    )
    beam.set_longitudinal_rebar_bot(n1=7, d_b1=20*mm)
    beam.set_longitudinal_rebar_top(n1=3, d_b1=16*mm)
    beam.set_transverse_rebar(n_stirrups=2, d_b=8*mm, s_l=20*cm)
    Node(section=beam, forces=[
        Forces(label="Positive", M_y=100*kNm, V_z=100*kN),
        Forces(label="Negative", M_y=-80*kNm, V_z=100*kN),
    ]).check()
    beam.plot()
    # Optional preference before producing a new drawing:
    # beam.settings.mounting_bar_diameter = 8*mm

.. image:: /_static/beam_detailing_7_3_4.png
   :alt: Seven Ø20 lower bars, three Ø16 upper bars, one orange Ø10 mounting bar and four stirrup legs.


On a US customary section the dimensions and the stirrup text are in inches and the
bar labels use ASTM sizes (for example ``3#6`` and ``2#3 (mounting)``).

Longitudinal skin reinforcement
***********************************

ACI 318-19 / CIRSOC 201-25 §9.7.2.3 requires supplementary longitudinal
steel on both lateral faces when h exceeds 900 mm (ACI in-lb: 36 in.).
The proposal covers h/2 measured from every tension face found in the
flexure checks. Reversing moments cover both halves; the pair at mid-height
is shared. Clear cover to side bars is c_c plus the stirrup diameter,
and Table 24.3.2 supplies the cap with f_s = 2f_y/3 (§24.3.2.1).

``beam.skin_reinforcement`` publishes status, tension_faces, d_b,
side_cover, s_max, spacing and n_per_side. Status ``required`` describes
an obligation and a proposal, not a check of independently supplied skin steel.
``beam.detailing_geometry.skin_bars`` validates the proposed supplementary bars
against the supported cage. They are shown in green and labelled per lateral
face. Centres are uniformly spaced from the actual tension-layer anchor up to h/2;
first-row clearance to flexural layers and steel intersections are checked.
If the layout cannot fit, it raises ``CageDetailingError`` and the plot
explicitly falls back to calculation geometry.

The diameter is independently configurable from mounting steel:

.. code-block:: python

    beam.settings.skin_bar_diameter = 10*mm  # default; 8 mm permitted by default settings
    node.check_flexure()                     # or node.check() / node.design()
    requirement = beam.skin_reinforcement
    print(requirement.status, requirement.n_per_side, requirement.s_max)
    geometry = beam.detailing_geometry
    print(geometry.to_dict("mm")["skin_bars"])
    beam.plot()

No skin bars are credited to flexural or shear capacity, areas or centroids.
The original ``section_geometry`` remains the calculation model.
The current Word flexure/shear reports and summary tables do not include the
skin proposal or its distribution review. An OK in those reports verifies
their stated checks, not this supplementary detailing. Read
``beam.skin_reinforcement``, ``beam.warnings`` and the actual section plot
separately; adding skin information to Word is outside this proposal.
``skin_reinforcement_required`` identifies a supplementary detailing requirement
beside the strength checks. Before flexure verification a beam above the height threshold reports ``pending``;
no tension face is assumed. EN uses the separate rule documented below.
Slab strips are not applicable.
This feature does not implement strut-and-tie design, anchorage, splice lengths,
seismic detailing, a full bending schedule or checking manually supplied skin bars.

For a 30 x 120 cm CIRSOC beam with four Ø20 bars on each horizontal face,
Ø8 stirrups and 30 mm cover, Mento proposes three Ø10 skin bars per lateral
face at 27.6 cm for +100/-80 kNm bending: two per half with the middle bar
shared. With positive bending alone, two Ø10 per side cover the lower half.
These are proposed layouts, not a code-mandated diameter or bar count.
Spacing starts at the innermost lateral tension-layer bar and ends at h/2,
following ACI Fig. R9.7.2.3 / CIRSOC Fig. C 9.7.2.3. This avoids clashes with
a second layer or large cover caused by measuring the first interval from
the concrete face. The ``spacing`` result is the largest pitch if the two
halves differ; explicit ``rows`` retains the actual levels.

.. image:: /_static/beam_skin_reversal.png
   :alt: Actual Mento output with four bottom and top bars and three green skin bars per lateral face.

EN 1992-1-1:2004 skin steel
--------------------------------

The separate EN rule applies from h >= 1000 mm (§7.3.3(3)). For rectangular
pure bending, Eq. (7.1) uses k_c=0.4, k=0.5, f_ct,eff=f_ctm and sigma_s=f_yk.
A_ct=b*h/2 is the tensile area immediately before cracking; the additional
area is divided equally between the lateral faces. Main flexural bars are
not credited to this supplementary minimum.

EN needs independently assessed cracked-service steel stress and neutral
axis for each service case. Mento's ultimate force checks do not supply them.
Keep the stress and axis from the same SLS analysis together in a
``SkinServiceCase``. The axis is measured from the compression face. Give
separate cases for bottom and top tension, and additional cases if their
service zones differ. Labels identify SLS combinations, not necessarily ULS
combinations. Set the cases after the section has been designed:

.. code-block:: python

    # Illustrative SLS inputs, NOT calculated from the ultimate moments:
    from mento import SkinServiceCase
    beam.set_skin_service_cases([
        SkinServiceCase("SLS+", "bottom", 400*MPa, 240*mm),
        SkinServiceCase("SLS-", "top", 300*MPa, 320*mm),
    ])
    beam.settings.skin_crack_width = 0.3*mm
    beam.settings.skin_bar_diameter = 10*mm

The proposal uses the diameter route of Table 7.2N, with half the supplied
main-steel stress. Stress is rounded up to a tabulated row; values below
160 MPa use that first row. The tabulated diameter is corrected using
Eq. (7.7N). EN does not explicitly define the geometric substitution for
lateral skin bars. Mento takes the smaller of two interpretations: h_cr=h/2
with h-d to the main outer tension layer, and a web treated as a tie across
its width, with h_cr=b and h-d to the actual skin-bar centroid from the side.
This minimum is a conservative Mento project rule, not an additional EN
equation. Both the uncracked tensile area b*h/2 and this geometric treatment
must be reviewed for the project. This simplified route does not directly
calculate w_k under §7.3.4 and does not certify its value.
Available crack widths are 0.2, 0.3 and 0.4 mm; the 0.3 mm default is a
preference to review against exposure and the applicable National Annex,
not a universal limit. This implementation assumes high-bond reinforcement
and f_ct,eff=f_ctm; early-age restraint is outside its scope.

Bars are uniformly distributed inside the links between the tension layer
and the supplied service neutral axis. With moment reversal, a single grid
covers the union, with enough area inside EACH tension zone. Extra bars in
compression receive no strength credit. The requirement publishes
area_min_per_side, area_per_side, diameter_max and actual rows.
The spacing describes the proposal; s_max is None because the selected
diameter method does not introduce a separate code spacing cap.

The proposal retains a single row when the minimum area permits it. It does
not impose a Mento minimum of two rows. ``skin_distribution_review`` reports
the number of rows per lateral face inside each service tension zone and its
largest vertical interval, including gaps to the zone boundaries. This
informative warning accompanies every EN proposal so that sparse layouts
remain visible for engineering review. These intervals are not clear
distances between bar surfaces or an additional EN spacing limit. The
diameter-route proposal does not directly calculate or certify crack width.
The drawing displays this review alongside the actual skin-steel proposal.
All service zones are checked separately for minimum area; the warning data
retains their SLS labels. The drawing summarizes the largest interval per
tension face to remain readable.

Service cases belong to the beam, not to shareable ``BeamSettings``. Inputs
and returned cases are copied defensively. Rebar setters and the design's
own placements invalidate them; material, section or layer-spacing changes
are also detected. Rechecking unchanged reinforcement preserves the cases.
Missing data for either required tension face leaves the proposal pending.

A zero-moment or capacity-only check on a section within the skin-steel
scope leaves the requirement ``pending`` with reason ``no_tension_case``;
it does not establish that skin reinforcement is unnecessary. EN axial
cases are ``unsupported`` even when their moment is zero.

Missing service inputs produce pending and no skin bars. Invalid inputs,
an excessive diameter or a physical clash raise CageDetailingError.
Axial-force combinations explicitly report unsupported: the pure-bending
minimum cannot be reused for them. Surface mesh outside the links (Annex J)
is a different detail; large bars or cover above 70 mm produce a separate
warning even for a beam below 1000 mm. This proposal does not verify that mesh.

.. image:: /_static/beam_skin_en.png
   :alt: Actual EN Mento output with supplementary green skin bars using explicit service inputs.
