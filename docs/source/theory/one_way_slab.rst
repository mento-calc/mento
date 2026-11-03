One-Way Slab
============

``OneWaySlab`` subclasses ``RectangularBeam``. **The code provisions are identical** —
a one-way slab is analysed as a wide, shallow beam, and every equation on the
:doc:`ACI <beam_aci_318_19>` and :doc:`EN <beam_en_1992_2004>` pages applies
unchanged.

This page covers only what differs.

Model
-----

A one-way slab spans in one direction and is designed over a chosen width. That
``width`` becomes :math:`b` (or :math:`b_w`) in every formula, and the slab thickness
becomes :math:`h`.

.. math::

   b = \text{design width}
   \qquad
   h = \text{slab thickness}
   \qquad
   d = h - c_c - \frac{d_b}{2}

The width is a free parameter, not fixed at unity. A 1 m or 12 in width is the usual
choice for a floor or roof slab, and it is convenient because the reported areas then
read directly as cm²/m. Any other width is equally valid — a 150 cm width is a
reasonable model for a strip footing, for example — and the section is solved at that
width rather than scaled up from a unit strip.

Results are therefore absolute for the width given: :math:`A_s` is the total steel
across :math:`b`, not a per-metre intensity. Divide by the width to convert to cm²/m
when that is the more useful form.

Note the absence of a stirrup diameter in :math:`d`: slabs carry no transverse
reinforcement by default, so ``_stirrup_d_b`` starts at zero and the mechanical cover
is measured straight from the clear cover to the bar centroid.

What changes
------------

Reinforcement is specified by spacing, not count
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

``set_slab_longitudinal_rebar_bot(d_b1, s_b1, d_b3, s_b3)`` takes a **bar diameter
and a spacing** per layer, matching slab detailing practice, instead of the beam's
bar count. Internally the bar count across the width is derived from the spacing, and
from there the section behaves exactly as a beam:

.. math::

   n = \frac{b}{s}
   \qquad
   A_s = n\,\frac{\pi d_b^2}{4}

Positions 1 and 3 correspond to the first and second layer respectively.

A design is written back as a spacing
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The bar selection is the beam's, and it answers with groups of bars per layer. A
design applied to a slab is translated back into the parameterisation above: the bars
of a layer are spread over the design width, and the spacing is rounded to the whole
centimetre (inch, in imperial) so that it is one that can be detailed. It is rounded
**down**: the strip carries :math:`b/s` bars, so a spacing wider than :math:`b/n`
would carry fewer bars — and so less steel — than the search selected. Rounding down
only ever adds steel, and by less than one bar in the strip.

The count :math:`n = b/s` is not rounded either. A strip is a slice of a slab that goes
on past both of its edges, so what it carries is the bars per metre its spacing gives:
a metre of Ø10/12 carries 8.33 bars, 6.54 cm²/m, which is what every metre of that slab
carries. Counting the whole bars that would cover the strip (9, 7.07 cm²) credited it
with 8 % more steel than it has, and let a face designed to its minimum fall short of
it unnoticed. A footing does not go on past its edges, and counts whole bars: see
:doc:`footing`.

Maximum bar spacing
^^^^^^^^^^^^^^^^^^^

Area alone is not a layout: bars far enough apart leave the slab between them
unreinforced whatever they add up to. Both codes cap the centre-to-centre spacing of
the flexural reinforcement, and the design applies the cap, which only ever adds bars:

.. list-table::
   :header-rows: 1
   :widths: 25 35 40

   * - Code
     - Limit
     - Clause
   * - ACI 318-19
     - :math:`\min(3h,\ 450\ \text{mm})` — 18 in. in imperial
     - §7.7.2.3
   * - ACI 318-19 / CIRSOC 201-25
     - :math:`\min\left(380\,\tfrac{280}{f_s} - 2.5\,c_c,\ 300\,\tfrac{280}{f_s}\right)`,
       with :math:`f_s = \tfrac{2}{3} f_y` and :math:`c_c` the cover to the bars
       (in-lb: :math:`15\,\tfrac{40000}{f_s} - 2.5\,c_c` and :math:`12\,\tfrac{40000}{f_s}`)
     - §7.7.2.2 → Table 24.3.2, with §24.3.2.1 for :math:`f_s`
   * - CIRSOC 201-25
     - :math:`\min(3h,\ 300\ \text{mm})`
     - art. 7.7.2.3
   * - EN 1992-1-1
     - :math:`\min(3h,\ 400\ \text{mm})`
     - §9.3.1.1(3), principal reinforcement

The two ACI / CIRSOC limits are taken together, and the second is the one that governs
the ordinary slab: with ADN 420 or Grade 60 and 25 mm of cover it is
:math:`\min(317.5,\ 300) = 300` mm, so the 450 mm of ACI 318-19 §7.7.2.3 never binds a
slab of that grade, a deeper cover or a stronger steel tightens it further, and the two
codes agree from 10 cm of thickness up. It is written on the bars closest to the tension
face; a slab applies it on both faces, because which face is in tension changes with the
combination and the strip is detailed once. EN 1992-1-1 controls cracking through
§7.3.3 instead, and mento does not add a cap of this kind to it.

The check reports it as well: the row that gives a beam the clear distance between its
bars gives a slab the spacing it is detailed at, with this maximum beside the minimum.

.. note::

   EN §9.3.1.1(3) tightens the limit to :math:`\min(2h,\ 250\ \text{mm})` in areas
   with concentrated loads or of maximum moment. That provision is **not** applied: a
   section is checked against a set of forces, with no position along the span from
   which mento could tell that it is in one of those areas.

Detailing settings
^^^^^^^^^^^^^^^^^^

Two ``BeamSettings`` values are overridden on construction:

.. list-table::
   :header-rows: 1
   :widths: 30 20 50

   * - Setting
     - Slab value
     - Why
   * - ``max_bars_per_layer``
     - ≥ 200
     - A 1 m width at 10 cm spacing already needs 10 bars, and wider slabs or
       narrower spacings need far more. The beam default would reject valid slab
       layouts.
   * - ``max_diameter_diff``
     - 0
     - All bars within a layer must share a diameter — mixing diameters in a slab
       mat is not standard practice.

No default starter bars
^^^^^^^^^^^^^^^^^^^^^^^

A beam with no longitudinal reinforcement defined falls back to 2Ø8 (metric) or 2#3
(imperial) so that it can still be checked. A slab does not: both faces start at
zero, because a slab legitimately may have reinforcement on one face only.

Consequences for shear
----------------------

Slabs sit in the corner of the shear provisions that beams rarely reach, and this is
where the difference matters most in practice.

**ACI 318-19.** With no stirrups, :math:`A_v < A_{v,min}` always, so :math:`V_c`
always takes the branch that includes the size effect factor :math:`\lambda_s`. And
because slabs are shallow, :math:`d` is usually below the 250 mm at which
:math:`\lambda_s` reaches its :math:`\le 1.0` cap. Both conditions together mean the
cap is *active* for essentially every slab — see the note in
:ref:`the ACI shear section <aci-decisions>`.

**EN 1992-1-1.** :math:`V_{Rd,c}` from §6.2.2 governs, with the size factor
:math:`k = \min(1 + \sqrt{200/d},\, 2.0)` reaching its ceiling of 2.0 for
:math:`d \le 200` mm — again, the common slab range. §6.2.1(4) allows the minimum
shear reinforcement to be omitted in slabs, since transverse load redistribution is
possible; mento reports :math:`A_{sw,req} = A_{sw,min}` and leaves that call to the
engineer.

Consequences for flexure
------------------------

Nothing changes mechanically. What changes is the minimum reinforcement.

**ACI 318-19 and CIRSOC 201-25.** A one-way slab is designed under Chapter 7, and its
minimum is §7.6.1.1 (CIRSOC 201-25 §7.6.1), not the beam minimum of §9.6.1.2:

.. math::

   A_{s,min} = 0.0018\, b\, h

on the gross section and for every steel grade — the same ratio as the shrinkage and
temperature reinforcement of §24.4.3.2, and the one a :doc:`footing` reaches through
§13.3.2.1. The 4/3 relief of §9.6.1.3 relieves §9.6.1.2 only, so it does not apply to
a slab: a face whose moment asks for less than :math:`A_{s,min}` is designed to
:math:`A_{s,min}` itself. On a 1 m strip 200 mm deep that is 3.60 cm², where the beam
rule asked 5.63 cm².

.. note::

   Shrinkage and temperature reinforcement in the transverse direction (ACI §24.4,
   EN §9.3.1.1) is **not** computed. mento designs the spanning direction only; the
   distribution steel perpendicular to the span is the engineer's responsibility.

Validation
----------

.. list-table::
   :header-rows: 1
   :widths: 30 40 30

   * - Check
     - Test
     - Verified against
   * - Shear check, ACI, no stirrups
     - ``test_shear_check_ACI_318_19_1`` (``tests/elements/test_slab.py``)
     - Regression against a Calcpad sheet, corrected for the
       :math:`\lambda_s \le 1.0` cap; no published example yet
   * - :math:`\lambda_s` cap, both unit systems
     - ``test_lambda_s_is_capped_at_one_imperial`` / ``_metric``
     - ACI 318-19 §22.5.5.1.3
   * - Flexure check, ACI, metric
     - ``test_check_flexure_ACI_318_19_1``, ``_2``
     - Regression against a Calcpad sheet; no published example yet
   * - Spacing to bar count
     - ``test_longitudinal_rebar_spacing_updates_counts``
     - Internal consistency
   * - Design written back as a spacing
     - ``test_a_designed_slab_is_detailed_by_a_spacing_not_by_a_bar_count``,
       ``test_a_spacing_is_never_rounded_into_less_steel_than_the_design_chose``
     - Internal consistency
   * - Steel of a strip is bars per metre
     - ``test_the_steel_of_a_strip_is_the_bar_area_times_the_bars_per_metre``,
       ``test_a_slab_designed_to_its_minimum_reaches_it_in_every_metre``
     - Internal consistency; CIRSOC 201-25 §7.6.1
   * - Crack-control spacing cap
     - ``test_an_aci_slab_is_held_to_300_mm_by_table_24_3_2``,
       ``test_a_slab_spread_past_table_24_3_2_is_warned``
     - ACI 318-19 §7.7.2.2, Table 24.3.2, §24.3.2.1
   * - Maximum bar spacing
     - ``test_the_code_caps_how_far_apart_the_bars_of_a_slab_may_sit``,
       ``test_a_design_is_never_spaced_beyond_the_code_maximum``
     - ACI 318-19 §7.7.2.3, EN 1992-1-1 §9.3.1.1(3)
   * - Slab mode defaults
     - ``test_slab_initialization_sets_slab_mode_and_defaults``
     - Detailing settings above
   * - Transverse rebar handling
     - ``test_set_slab_transverse_rebar_computes_shear_area``,
       ``test_set_slab_transverse_rebar_zero_spacing_clears_shear_area``
     - Internal consistency
