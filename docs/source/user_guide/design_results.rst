.. _user_guide/design_results:

Design results
==============

After a check or a design has run, the reinforcement it produced is available as plain
data through two properties of the section: ``flexure_design`` and ``shear_design``.

These return frozen objects, so they are a snapshot of the result rather than a live view
of the section. Every quantity is a pint ``Quantity`` in the unit system of the section's
concrete, and can be converted with ``.to()`` as usual.

.. code-block:: python

    from mento import Concrete_ACI_318_19, SteelBar, RectangularBeam, Node, Forces
    from mento import MPa, cm, mm, kN, kNm

    concrete = Concrete_ACI_318_19(name="H25", f_c=25 * MPa)
    steel = SteelBar(name="ADN 420", f_y=420 * MPa)
    beam = RectangularBeam(
        label="101", concrete=concrete, steel_bar=steel,
        width=20 * cm, height=60 * cm, c_c=25 * mm,
    )

    node = Node(section=beam, forces=[Forces(label="C1", V_z=80 * kN, M_y=100 * kNm)])
    node.design()

Flexure
-------

``flexure_design`` has a ``bottom`` and a ``top`` face:

.. code-block:: python

    flexure = beam.flexure_design

    flexure.bottom.A_s.to("cm**2")      # 5.15 cm², steel provided
    flexure.bottom.A_s_req.to("cm**2")  # 4.96 cm², steel required
    flexure.bottom.A_s_calc.to("cm**2") # 4.96 cm², what the moment alone asks for
    flexure.bottom.A_s_min, flexure.bottom.A_s_max
    flexure.bottom.DCR                  # 0.965
    flexure.bottom.M_capacity           # 103.6 kN·m, ØMn here; MRd under EN 1992
    flexure.bottom.n_bars               # 3

    flexure.DCR                         # worst of the two faces
    str(flexure.bottom)                 # '2Ø16 mm + 1Ø12 mm'

Each face carries its layers, in order, and only the layers that hold bars:

.. code-block:: python

    for layer in flexure.bottom.layers:
        print(layer.n, layer.d_b, layer.A_s.to("cm**2"))

A face with no reinforcement has an empty ``layers`` tuple, which is what
``str(flexure.top)`` reports as ``'no reinforcement'``.

``A_s_req`` and ``A_s_calc`` are the same number on this beam because the moment
governs. They part on a face governed by its minimum: ``A_s_req`` is the steel to detail,
``max(A_s_calc, A_s_min)`` — or the 4/3 rule under ACI — while ``A_s_calc`` is what the
moment alone asked for, and is zero with no moment. Choose bars from the first. Scale an
anchorage by ``A_s,nec / A_s,prov`` from the second: a footing mat governed by its
minimum carries little of the stress that minimum is sized for, and charging it the full
development length anchors a force that is not there.

.. code-block:: python

    face = footing.flexure_design.bottom      # a 1 m × 0.40 m strip under 20 kN·m, ACI

    face.A_s_calc.to("cm**2")                 # 1.5 cm², the moment's own demand
    face.A_s_min.to("cm**2")                  # 7.2 cm², the minimum on the ground
    face.A_s_req == face.A_s_min              # True: the minimum governs

A slab is detailed by a spacing rather than by a bar count, so each of its layers also
carries the spacing it was designed with, and reads as one bar repeated across the strip.
The bars are still there to be counted when what you need is the steel actually placed:

.. code-block:: python

    layer = slab.flexure_design.bottom.layers[0]

    layer.d_b                            # 12 mm
    layer.s.to("cm")                     # 17 cm, None on a beam
    layer.n                              # 5.88, the bars a metre carries at that spacing: 100/17
    str(layer)                           # 'Ø12 mm/17 cm'

    layer.n_placed                       # 6, the whole bars that lay it out: ceil(100/17)

    slab.flexure_design.bottom.n_bars         # 5.88, every layer of the face
    slab.flexure_design.bottom.n_bars_placed  # 6

The count of a slab layer is ``width / s`` and is not a whole number: the strip is a
slice of a slab that goes on past its edges, and its steel -- what its strength is
computed with -- is the bar area times the bars per metre, ``layer.A_s == layer.n * π
d_b² / 4`` on a slab as on a beam. ``n_placed`` is the whole number of bars that lay the
layer out at that spacing, the last one a little past the strip. On a beam the two are
the same number.

Shear
-----

.. code-block:: python

    shear = beam.shear_design

    shear.n_stirrups        # 1, two-leg equivalent (not a piece count)
    shear.n_legs            # 2, legs crossing the shear plane
    shear.d_b               # 10 mm
    shear.s_l.to("cm")      # 27 cm, longitudinal spacing
    shear.A_v.to("cm**2/m") # 5.82 cm²/m, provided
    shear.A_v_req, shear.A_v_min
    shear.DCR               # 0.462
    shear.V_capacity        # 173 kN, ØVn here; VRd under EN 1992

    shear.s_w.to("cm")      # 14 cm, how far apart the legs are across the width
    shear.s_max_w           # 55.74 cm, the most Table 9.7.6.2.2 allows it
    shear.s_max_l           # 27.87 cm, the limit s_l is held to
    shear.s_max_l_table     # 27.87 cm, Table 9.7.6.2.2 alone
    shear.s_max_l_support   # None: §9.7.6.4.3 caps it only on stirrups that brace compression bars

    str(shear)              # '2 legs Ø10 mm @ 27 cm · 14 cm between legs (max 55.74 cm)'
    shear.notation("es")    # '2 ramas Ø10 mm c/27 cm · 14 cm entre ramas (máx. 55.74 cm)'
    shear.arrangement()     # 'single perimeter stirrup'

Input accepts ``beam.set_transverse_rebar(n_legs=4, d_b=8*mm, s_l=20*cm)``.
The legacy ``n_stirrups=2`` has the same meaning. In ``BeamSummary`` the
preferred column is ``legs`` (alias ``n_legs``, legacy ``ns``). Integer leg counts
from 2 are supported, including odd counts; contradictory inputs raise an error.

The notation leads with the legs, which is what the shear check counts: ``n_stirrups``
is a two-leg equivalent: ``n_legs = 2·n_stirrups``, not the count of closed pieces. Then come the
bar, the spacing along the member and the spacing of the legs across the width, with the
maximum it is checked against. ``str()`` is always English; ``notation(language)`` gives it
in another language (the one of :func:`mento.set_language` by default), and
``notation(compact=True)`` the short form of a table cell, ``2 legs Ø10/27``.
``arrangement()`` says how the legs are tied into a cage: ``perimeter stirrup + 4 inner
stirrups`` for ten legs -- one stirrup around the whole section and inner stirrups on the
2nd and 3rd legs, the 4th and 5th... The configuration, ``beam.reinforcement.transverse``,
reads the same without the maximum: it has not been checked.

An explicit ``language`` must be one of :func:`mento.available_languages`; anything else
raises ``ValueError``, as :func:`mento.set_language` does. The compact form prints bare
numbers, the bar in mm and the spacing in cm; ``notation(compact=True, imperial=True)``
prints ASTM bar sizes and spacings in inches (``2 legs #3@6``). Left unsaid, it follows
the unit of ``s_l``. The "Av" cell of ``BeamSummary.check()`` follows the concrete
unit system, like the "As" cells beside it: mm/cm in SI, ASTM/in in US customary.

The limits are envelopes, the tightest of every combination checked. ``s_max_l`` is the
along-length limit the stirrups are held to: Table 9.7.6.2.2 (``s_max_l_table``) or, on a
section that relies on compression bars, the cap of §9.7.6.4.3 (``s_max_l_support``) when
that is less. Under EN 1992-1-1 they are Expressions (9.6N) and (9.8N), and ``None`` on a
section with no stirrups.

Several load combinations
-------------------------

A section is normally checked against a list of combinations, and each face is often
governed by a different one. The required areas and the DCRs are the envelope over the
whole list, so they describe the combination that governs — not whichever one happened to
be checked last:

.. code-block:: python

    node = Node(section=beam, forces=[f1, f2, f3])
    node.design()

    beam.flexure_design.bottom.DCR  # worst of the three on the bottom face
    beam.shear_design.A_v_req       # largest stirrup requirement of the three

The provided reinforcement — ``A_s``, the layers and the stirrup layout — describes the
section itself and does not depend on the combination.

The capacity follows the DCR: it is the one of the combination that governs, so the two
remain the ratio they were. Under ACI 318-19 the shear resistance can differ between
combinations, since ``Vc`` depends on the axial load and on which face is in tension; the
per-combination results keep each one's own.

Capacities
----------

Each result also carries the resistance its ``DCR`` was formed from: ``M_capacity`` on a
flexure face and ``V_capacity`` on the shear result. The name is the same under every
design code — it holds ``ØMn`` and ``ØVn`` under ACI 318-19 and CIRSOC 201-25, ``MRd``
and ``VRd`` under EN 1992-1-1 — so a report that prints the symbol names it per code and
the data does not have to.

For any combination with a demand, dividing the demand by its ``DCR`` gives the capacity
back, to within the rounding the design code applies to the ratio. The field is there for
the cases the ratio cannot cover: a face carrying minimum reinforcement against no demand
has a ``DCR`` of zero and a real capacity, and two faces with identical reinforcement
report exactly the same one.

The per-combination results are available too, one per combination of the last check:

.. code-block:: python

    for check in beam.shear_checks:
        check.label, check.DCR, check.V_capacity
        check.V_s_req, check.V_s_threshold, check.spacing_halved   # the row of Table 9.7.6.2.2
        check.s_max_l_table, check.s_max_w

    for check in beam.flexure_checks:
        check.label, check.bottom.DCR, check.bottom.M_capacity

    beam.shear_design.V_capacity            # the governing combination's

``check.label`` is the name of the combination; the stirrup text is
``beam.shear_design.notation()``. ``V_s_threshold`` is the ``0.33·√f'c·bw·d``
(``4·√f'c·bw·d`` in psi) past which Table 9.7.6.2.2 halves its limits, and
``spacing_halved`` says whether that combination passed it; EN 1992-1-1 has no such row,
and gives ``None``. Enveloped with :func:`mento.design_results.envelope_shear`, the three
agree with the limits the envelope reports: ``V_s_req`` is the largest of any combination,
``V_s_threshold`` the one it was compared with, and ``spacing_halved`` is True when any
combination took the halved row -- the row the tightest limits come from.

Section geometry
----------------

``beam.section_geometry`` says where the bars and the stirrup legs are, as the checks
assume them, so that a drawing -- ``beam.plot()``, or any other -- shows the checked section
without deriving anything:

.. code-block:: python

    geometry = beam.section_geometry

    geometry.leg_x                  # (3 cm, 17 cm): centrelines of the legs, left to right
    geometry.s_w                    # 14 cm
    geometry.stirrups               # ClosedStirrup: legs, x_left, x_right, y_bottom, y_top, perimeter
    geometry.crossties              # () -- see below
    geometry.bars_on("bottom", 1)   # BarPosition: x, y, d_b, face, layer, group
    geometry.arrangement()          # 'single perimeter stirrup'
    geometry.to_dict("cm")          # the same as plain floats

It is configuration, like ``reinforcement``: readable at any time. The origin is the
bottom-left corner of the section, ``x`` across the width and ``y`` up, and every length is
a quantity in the display unit of the section (cm, or in). The positions are the model:

- **Legs**: ``2·n_stirrups`` legs spread evenly between the centres of the outermost pair,
  ``x_i = c_c + d_st/2 + i·s_w``, with ``s_w = (b - 2·c_c - d_st)/(n_legs - 1)`` -- the
  spacing the shear check holds to Table 9.7.6.2.2.
- **Cage**: a perimeter stirrup on the outermost legs and inner closed stirrups on the
  interior legs selected for required compression support; remaining interior legs
  are open. ``ClosedStirrup.legs`` and ``Crosstie.leg`` use zero-based leg indices.
  Calculation geometry has a perimeter and open interior legs; detailing geometry
  proposes closed pieces according to the real compression faces.
  The design only ever produces even counts.
- **Bars**: each layer spread between the inner faces of the outer legs, one clear
  spacing apart -- the clear spacing the checks read -- with the ``n1`` bars of a layer at
  its ends and the ``n2`` bars between them; the layers at the offsets the effective depth
  is computed with. The stirrup diameter is the one the section reserves, also with no
  stirrups placed.

The legs are not tied to the bars -- the checks do not do that either -- so an inner leg
may sit where there is no bar. That is the calculation model.

For a supported cross-section use ``beam.detailing_geometry``. It keeps the shear legs
and the resistant bars' counts, diameters, groups and vertical coordinates, while placing
the nearest-face bars at stirrup corners. Extra bars are spread between those supports.
Where a face has too few bars, ``mounting_bars`` supplies the missing corner supports,
including an otherwise empty upper face. Their diameter is controlled by
``settings.mounting_bar_diameter`` (10 mm or No. 3 by default).

.. code-block:: python

    from mento import CageDetailingError

    detail = beam.detailing_geometry
    detail.bars                    # resistant bars, including both layers
    detail.mounting_bars           # supplementary steel, excluded from resistance
    detail.to_dict("cm")           # separate bars and mounting_bars collections

This does not mutate the beam, its reinforcement or its check results. ``bars_on()``
continues to return only resistant steel. A layout must satisfy the configured clear
spacing and vibrator allowance, the code's available centre-distance cap, and clearance
from the stirrup branches and bends. If the layout cannot be produced, the property raises
``CageDetailingError``. ``plot()`` then identifies its fallback as calculation geometry
and issues a warning. The cross-section check does not supply development lengths,
hooks, seismic detailing, or strength credit for mounting bars.
The bend diameter is supplied by the code's mandrel-size rule; it does not
verify concrete failure at a bend. ``to_dict()`` without a unit uses the
section's display unit, including inches for a US customary section.

The tension-bar spacing limit is applied only to faces put in tension by the
verified load combinations. If flexure has not been checked, the drawing checks
physical fit and labels tension-bar spacing as pending; it does not infer tension
on both faces. ``Node.check_flexure()`` / ``Node.check()`` already report excessive
spacing on the tension face of each combination, and the detailing layout also
checks the moved resistant bars. Mounting bars cannot satisfy that limit in place
of resistant steel. For a single resistant bar, the face width is checked against
the available limit.

A slab strip (``OneWaySlab``, ``Footing``) publishes the section, its cover and ``s_w``, with
no bars and no legs: it is detailed by spacings, its bars per strip need not be whole, and
bars placed by the beam's rule would contradict its ``Ø10/14`` label.

Design alternatives
-------------------

A design ranks every layout that fits and applies the best one. The runners-up are kept
too, best first, with the applied layout always in first place -- but only the ones the
finished section passes with. Each longitudinal alternative is built on the beam as the
design left it, with the stirrups it ended with and the other face as applied, and kept
if the beam carries both moments and the shear with it, within the code's limits on its
reinforcement (tension-controlled under ACI 318-19 / CIRSOC 201-25, the 4 % of EN
1992-1-1) and on its stirrups. The bars set the effective depth the shear is read at as
well, so a layout in two layers, or of thicker bars, lowers the section's shear limit and
can tighten the stirrup spacing it allows. The option's ``section_DCR`` says at what
ratio: the worst of the whole section with that layout, both faces and the shear, not the
ratio of the face it is listed under. A footing offers none, because its mat is chosen as a
whole.

.. code-block:: python

    node.design()

    for option in beam.flexure_design.bottom.options:
        str(option), option.A_s, option.functional   # '2Ø16 mm + 1Ø12 mm', ...

    beam.flexure_design.top.options                  # the same for the top face
    beam.shear_design.options                        # StirrupOption: n_stirrups, d_b, s_l, s_w, A_v,
                                                     # functional, section_DCR, s_max_l, s_max_w

A longitudinal option (``RebarOption``) carries its ``layers`` — the same ``RebarLayer``
objects the applied reinforcement is read as — its area and the ``functional`` the search
ranked it by.

The stirrup alternatives are one layout per other bar diameter the code offers, lighter and
heavier alike, in order of diameter: each is the widest spacing with the fewest legs that
covers the demand read at the depth that bar gives the section. Where the spacing limit
governs they share one spacing (a 20×40 under 100 kN and 30 kN·m: ``2 legs Ø10/17``,
``2 legs Ø12/17``, ``2 legs Ø16/17``); where the demand
governs, a lighter bar sits closer and a heavier one further apart. Every alternative is
built on the finished section and checked there -- shear and flexure, since a heavier
stirrup lowers the effective depth -- and only the ones the section passes with are kept, so
the list answers "what if I use the bar I have". Each option carries its ``section_DCR``, the
worst ratio of the section built with it -- flexure included, so not always the shear's -- and
its ``functional``, what it adds in steel: the excess
of ``A_v`` over what the section asks for with that bar, plus one per extra closed stirrup.
It also carries the ``s_max_l`` and ``s_max_w`` the search held it to, read at the depth
its own bar gives the section.

How many are kept is a setting, three by default:

.. code-block:: python

    beam = RectangularBeam(..., settings=BeamSettings(design_options=5))

The options belong to the design that produced them. A check alone reports none, and
changing the bars by hand afterwards clears the options of what was changed.

Changing the bars or the stirrups by hand drops every result of the last check or design
— ``flexure_design`` and ``shear_design`` raise ``DesignNotRunError``, the per-combination
checks and the warnings they raised are empty — until the next check or design: they
described the section as it was. ``reinforcement`` always reads the section as it is.

A design depends only on its inputs. It starts from the same state every time — the
stirrup diameter the settings assume, the placeholder bars — so running it again, or after
setting reinforcement by hand, gives the same result.

Warnings
--------

A detailing limit can be missed while the strength is fine, or met while it is not, so
the limits are reported beside the ``DCR`` instead of inside it. ``beam.warnings`` (or
``node.warnings``) lists them after a check or a design, one per limit and face:

.. code-block:: python

    node.check()
    for warning in node.warnings:
        warning.code          # 'stirrup_spacing_exceeds_max'
        warning.message       # 'Stirrup spacing along the member: 35 cm exceeds the maximum 13.9 cm.'
        warning.values        # {'s': 35 cm, 's_max': 13.9 cm}
        warning.combinations  # ('1.2D+1.6L', '1.4D')

The ``code`` is stable and is what a program should compare against. The ``message`` is
written in the language set with ``mento.set_language`` when the warnings are read. The
codes and what triggers each are listed in :mod:`mento.design_warnings`.

Reading results too early
-------------------------

Both properties raise ``DesignNotRunError`` if the corresponding check or design has not
been run, rather than returning zeros that could be mistaken for a real result:

.. code-block:: python

    beam = RectangularBeam(...)
    beam.flexure_design
    # DesignNotRunError: No flexure results yet. Run node.design() or
    # node.check_flexure() before reading flexure_design.

Relation to the private attributes
----------------------------------

Sections still keep their results in private attributes such as ``_A_s_bot`` and
``_stirrup_s_l``. Those remain in place and keep working, but they are implementation
details: their names, units and meaning can change between releases. The properties
described here are the supported way to read a result from code.

``_stirrup_n`` and public ``n_stirrups`` are two-leg equivalents, which may be
semi-integer (3.5 for seven legs). ``n_legs`` is the calculation leg count. Neither
equivalent is a count of closed pieces: read ``detailing_geometry.stirrups``.

Bend provenance
---------------

``SectionGeometry.bend_supported`` is exported by ``to_dict()``. A False value
marks the 4*d_st calculation placeholder used when no supported mandrel is
available. That diameter is not a code requirement or a feasible bend detail.


Required compression-bar support
--------------------------------

``beam.compression_detailing`` checks the required compression faces identified
by the flexure calculation, not mounting steel or every bar incidentally in
compression. It exposes the status, supported first-row bar indices, maximum
clear distance on both sides, limits and reasons. ACI 318-19 §9.7.6.4.4 uses
150 mm (6 in in the in-lb edition). CIRSOC 201-25 §9.7.6.4.4 prints 15 times
the stirrup diameter or 150 mm: differing outcomes remain pending until that
interpretation is resolved. Second-row support remains pending. Open legs do not
brace compression bars; their hooks and anchorage are outside this sectional model
and have an informative notice. Missing/unavailable cages cannot pass.

Warnings and the plot identify failed or pending compression support. The
check does not change resistant steel, capacities, the shear verdict, or the
separate mandatory detailing assessment for §9.7.6.4.3. Hooks, longitudinal extent and seismic
detailing require separate verification. Extra closed pieces are a proposal: the
warning names input and proposed legs, detailing stays pending until confirmed,
and resistant areas remain based on the input.
