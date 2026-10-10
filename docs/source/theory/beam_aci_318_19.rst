Beam — ACI 318-19
=================

Provisions implemented for ``RectangularBeam`` when the section is built with
``Concrete_ACI_318_19`` or ``Concrete_CIRSOC_201_25``.

.. admonition:: CIRSOC 201-25
   :class: note

   ``Concrete_CIRSOC_201_25`` subclasses ``Concrete_ACI_318_19``. Every equation on
   this page applies unchanged. The differences are that CIRSOC is metric-only and
   ships a different reinforcing bar catalogue (it allows Ø6 mm stirrups, which the
   ACI catalogue does not). Results tables report ``design_code = "CIRSOC 201-25"``.

Scope
-----

**Implemented**

- Flexure: nominal moment of singly and doubly reinforced rectangular sections,
  required steel area, minimum and maximum reinforcement limits, ductility check.
- One-way shear: concrete contribution :math:`V_c` per Table 22.5.5.1, steel
  contribution, upper bound on total shear, minimum stirrups and spacing limits.

**Not implemented**: torsion (Ch. 22.7), deflection and crack control (Ch. 24),
development and splice lengths (Ch. 25), seismic detailing (Ch. 18), fatigue,
two-way action in the beam module (see ``PunchingSlab``), and any strut-and-tie
treatment of deep beams — the shear provisions here assume sectional behaviour.

Symbols
-------

.. list-table::
   :header-rows: 1
   :widths: 14 46 40

   * - Symbol
     - Meaning
     - Source
   * - :math:`f'_c`
     - Specified compressive strength of concrete
     - ``concrete.f_c``
   * - :math:`f_y`
     - Specified yield strength of longitudinal reinforcement
     - ``steel_bar.f_y``
   * - :math:`f_{yt}`
     - Yield strength of transverse reinforcement, capped (§20.2.2.4)
     - ``_calculate_f_yt_aci``
   * - :math:`\beta_1`
     - Stress-block depth factor (Table 22.2.2.4.3)
     - ``concrete.beta_1``
   * - :math:`\varepsilon_{cu}`
     - Ultimate concrete strain, 0.003 (§22.2.2.1)
     - ``concrete._epsilon_c``
   * - :math:`\varepsilon_y`
     - Reinforcement yield strain, :math:`f_y/E_s`
     - ``steel_bar.epsilon_y``
   * - :math:`\phi_t,\ \phi_v`
     - Strength reduction factors, 0.90 and 0.75 (§21.2)
     - ``concrete.phi_t``, ``concrete.phi_v``
   * - :math:`\lambda`
     - Lightweight concrete factor
     - ``concrete.lambda_factor``
   * - :math:`d,\ d'`
     - Effective depth to tension steel / cover to compression steel
     - ``_d_bot``, ``_c_mec_top`` (or swapped)
   * - :math:`a,\ c`
     - Stress block depth and neutral axis depth, :math:`a = \beta_1 c`
     - —
   * - :math:`\rho_w`
     - Longitudinal tension reinforcement ratio :math:`A_s/(b_w d)`
     - ``_rho_w``

Flexure
-------

Stress block
^^^^^^^^^^^^

Section strength uses the equivalent rectangular stress distribution of §22.2.2.4:
a uniform stress of :math:`0.85 f'_c` over a depth :math:`a = \beta_1 c`, with
:math:`\beta_1` from Table 22.2.2.4.3:

.. math::

   \beta_1 = \begin{cases}
   0.85 & f'_c \le 28\ \text{MPa} \\[2pt]
   0.85 - \dfrac{0.05}{7}\,(f'_c - 28) & 28 < f'_c \le 55\ \text{MPa} \\[2pt]
   0.65 & f'_c > 55\ \text{MPa}
   \end{cases}

Nominal moment — singly reinforced
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

From force equilibrium :math:`0.85 f'_c\, a\, b = A_s f_y`:

.. math::

   a = \frac{A_s f_y}{0.85 f'_c b}
   \qquad
   M_n = A_s f_y \left(d - \frac{a}{2}\right)

Implemented in ``_determine_nominal_moment_simple_reinf_ACI_318_19``. Used when
:math:`A_s \le A_{s,max}`; the tension steel is assumed to yield, which
:math:`A_{s,max}` guarantees.

Nominal moment — doubly reinforced
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

When :math:`A_s > A_{s,max}` the compression steel enters the resisting couple.
Equilibrium is written with a **displaced-concrete correction**: the compression bar
occupies a volume already accounted for by the :math:`0.85 f'_c a b` block, so its
effective contribution is :math:`(f'_s - 0.85 f'_c)`, not :math:`f'_s`.

mento solves it by strain compatibility with every bar at the stress its strain
gives it (§22.2.1.2, §20.2.2.1), the tension steel included, and nothing capped:

.. math::

   0.85 f'_c\, b\, \beta_1 c + A'_s\,(f'_s - 0.85 f'_c) = A_s f_s
   \qquad
   f_s = \min\!\left(E_s\,\varepsilon_{cu}\frac{d - c}{c},\ f_y\right),\quad
   f'_s = \min\!\left(E_s\,\varepsilon_{cu}\frac{c - d'}{c},\ f_y\right)

.. math::

   M_n = 0.85 f'_c\, a\, b \left(d - \frac{a}{2}\right) + A'_s\,(f'_s - 0.85 f'_c)(d - d')

and :math:`\phi` comes from the strain the tension steel reaches,
:math:`\varepsilon_t = \varepsilon_{cu}(d - c)/c`, through Table 21.2.2 — 0.90 while
the section is tension-controlled, down to 0.65 once :math:`\varepsilon_t \le
\varepsilon_y`. Implemented in ``nominal_moment_strain_compatibility`` and
``flexure_strength_reduction_factor`` (``codes/aci_318_19/equations/flexure.py``),
dispatched by ``_nominal_moment_face_ACI_318_19``.

While the compression steel keeps the section tension-controlled the tension steel
yields, and the solution reduces to the closed form below. Assuming the compression
steel yields as well:

.. math::

   c = \frac{A_s f_y - A'_s\,(f_y - 0.85 f'_c)}{0.85 f'_c\, b\, \beta_1}
   \qquad
   \varepsilon'_s = \frac{c - d'}{c}\,\varepsilon_{cu}

If :math:`\varepsilon'_s \ge \varepsilon_y` the assumption holds and

.. math::

   M_n = 0.85 f'_c\, a\, b \left(d - \frac{a}{2}\right)
       + A'_s\,(f_y - 0.85 f'_c)(d - d')

Otherwise the compression steel does not yield and :math:`c` is recovered from the
quadratic that results from substituting :math:`f'_s = \varepsilon_{cu} E_s (c-d')/c`
into equilibrium:

.. math::

   \underbrace{0.85 f'_c b \beta_1}_{A}\,c^2
   + \underbrace{\left[A'_s\,(\varepsilon_{cu} E_s - 0.85 f'_c) - A_s f_y\right]}_{B}\,c
   + \underbrace{\left(-d' A'_s \varepsilon_{cu} E_s\right)}_{C} = 0

with :math:`f'_{s,net} = f'_s - 0.85 f'_c` used for the couple. Implemented in
``_determine_nominal_moment_double_reinf_ACI_318_19``.

.. note::

   Past :math:`A_{s,max} + A'_s f'_{s,net}/f_y` the section is no longer
   tension-controlled. mento used to cut :math:`A_s` back to that value and keep
   :math:`\phi = 0.90`, which credited such a section with more than it carries: a
   25x40 CIRSOC 201-25 section with 3Ø32 over 4Ø16 at :math:`M_u = 206.9` kN·m read
   :math:`\phi M_n = 213.4` kN·m (DCR 0.97) against the 196.2 kN·m
   (:math:`\varepsilon_t = 0.00252`, :math:`\phi = 0.685`, DCR 1.055) it has.

Required reinforcement
^^^^^^^^^^^^^^^^^^^^^^

Inverting the singly-reinforced expression for a demand :math:`M_u`:

.. math::

   R_n = \frac{M_u}{\phi_t\, b\, d^2}
   \qquad
   A_{s,calc} = \frac{0.85 f'_c b d}{f_y}
                \left(1 - \sqrt{1 - \frac{2 R_n}{0.85 f'_c}}\right)

A negative radicand means no amount of tension steel alone develops :math:`M_u`:
the face is designed doubly reinforced, as below. (It used to stop at
:math:`A_{s,calc} = A_{s,max}` with no compression steel, so :math:`A_{s,req}` fell
as the moment grew past that point.)

Minimum reinforcement
^^^^^^^^^^^^^^^^^^^^^

§9.6.1.2 gives the mechanical minimum:

.. math::

   \rho_{min} = \max\left(\frac{0.25\sqrt{f'_c}}{f_y},\ \frac{1.4}{f_y}\right)
   \quad\text{(MPa)}
   \qquad
   \max\left(\frac{3\sqrt{f'_c}}{f_y},\ \frac{200}{f_y}\right)
   \quad\text{(psi)}

§9.6.1.3 allows :math:`A_{s,min}` to be waived if the steel provided is at least
one third greater than required, i.e. :math:`\tfrac{4}{3}A_{s,calc}`. mento applies
this only when it actually saves steel and the result still clears the geometric
minimum below — see :ref:`aci-decisions`.

Maximum reinforcement and ductility
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The upper limit keeps the section tension-controlled (CRSI Guide, Beam Theory p. 6-3,
consistent with §21.2.2):

.. math::

   \rho_{max} = 0.85\,\beta_1\,\frac{f'_c}{f_y}\,
                \frac{\varepsilon_{cu}}{\varepsilon_y + 2\varepsilon_{cu}}

The neutral axis at the tension-controlled boundary follows from strain
compatibility with :math:`\varepsilon_t = \varepsilon_y + \varepsilon_{cu}`:

.. math::

   c_t = \frac{0.003\, d}{\varepsilon_y + 0.006}

Sections with :math:`c < c_t` are ductile. The ratio :math:`c/d` is reported in the
results tables.

§9.3.3.1 requires a beam to be tension-controlled. With compression steel on the
other face the limit on the tension steel grows to

.. math::

   A_{s,max,eff} = A_{s,max} + A'_s\,\frac{f'_{s,net}}{f_y}

(:math:`f'_{s,net}` at :math:`c_t`, below; a compression bar with
:math:`f'_{s,net} \le 0` extends nothing). It is the same boundary as
:math:`\varepsilon_t = \varepsilon_y + 0.003`, read as an area. The check reports it
as ``A_s_max_eff`` and holds the face in tension to it. Past it the section is not
tension-controlled, which §9.3.3.1 (§7.3.3.1 for a one-way slab) does not allow, so it
does **not comply whatever its DCR**: the capacity already carries the lower
:math:`\phi` of the strain reached, and the DCR keeps that value, but
``admissible`` and ``complies`` of the flexure results are False, the detailed
report marks the face ❌ 9.3.3.1, and the warning ``not_tension_controlled`` cites the
article. The face a combination compresses is not held to it.

Compression steel at the ductility limit
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

When compression reinforcement is required, its stress is evaluated at :math:`c_t`
and corrected for displaced concrete:

.. math::

   f'_s = \min\!\left(0.003\,E_s\left(1 - \frac{d'}{c_t}\right),\ f_y\right)
   \qquad
   f'_{s,net} = f'_s - 0.85 f'_c

.. math::

   A'_s = \frac{M_u/\phi_t - M_{n,t}}{f'_{s,net}\,(d - d')}
   \qquad
   M_{n,t} = \rho f_y \left(d - \frac{a_{max}}{2}\right) b\, d,
   \quad a_{max} = \beta_1 c_t

That is the compression steel the moment asks for. The design places whole bars, so
the tension face usually gets more than :math:`A_{s,req}`, and it sizes the
compression steel for the steel **placed**,
:math:`A'_s \ge (A_s - A_{s,max})\,f_y/f'_{s,net}`, read at the depth of each
candidate layout — see :ref:`aci-decisions`. Where :math:`f'_{s,net} \le 0` the
compression bars sit too close to the neutral axis to help: no compression steel is
asked for, the face is asked for :math:`A_{s,max}`, and the moment it cannot reach is
the check's to report.

Maximum bar spacing (crack control)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

§9.7.2.2 sends the bars closest to the tension face to Table 24.3.2:

.. math::

   s \le \min\left(380\,\frac{280}{f_s} - 2.5\,c_c,\ 300\,\frac{280}{f_s}\right)
   \quad\text{(mm, MPa)}
   \qquad
   \min\left(15\,\frac{40000}{f_s} - 2.5\,c_c,\ 12\,\frac{40000}{f_s}\right)
   \quad\text{(in, psi)}

with :math:`f_s = \tfrac{2}{3} f_y`, which §24.3.2.1 permits in place of a service-load
calculation, and :math:`c_c` the distance from the surface of those bars to the tension
face — the clear cover plus the stirrup. With Grade 420 and 25 mm of cover to the
stirrup that is 292.5 mm (Ø10 stirrup) to 297.5 mm (Ø8). The check reads the spacing
off the layer nearest each face, centre to centre, as the section spreads it between
the stirrup legs, and holds the face the combination puts in tension to it; a wide
beam detailed with two bars — 60 cm with 2Ø25, 505 mm apart — fails it. With a single
bar nearest the face, §24.3.3 compares the width of the face instead. The detailed
report adds a *Maximum spacing* row per face, and the warning is
``bar_spacing_exceeds_max``. The bar search holds every layer it lays out to the cap
as well, so a wide web is designed with three bars where two would sit too far apart:
that 60x50 beam comes out as 3Ø20, 255 mm apart. The search reads the cap with the
stirrup the section carries when it runs — the starter stirrup, before the shear design
picks the real one — so a layout that lands within a few millimetres of the cap can be
reported by the check that follows with the heavier stirrup.

Shear
-----

Concrete contribution
^^^^^^^^^^^^^^^^^^^^^

Table 22.5.5.1, in the two-branch form that depends on whether minimum stirrups are
present. With the axial term :math:`\sigma_{Nu} = \min\!\big(N_u/(6 A_g),\,0.05 f'_c\big)`:

When :math:`A_v \ge A_{v,min}`:

.. math::

   k_c = \max\left(0.17\lambda\sqrt{f'_c},\
                   0.66\,\lambda\,\rho_w^{1/3}\sqrt{f'_c}\right) + \sigma_{Nu}

When :math:`A_v < A_{v,min}`, the size effect factor :math:`\lambda_s` applies
(§22.5.5.1.3):

.. math::

   k_c = 0.66\,\lambda_s\,\lambda\,\rho_w^{1/3}\sqrt{f'_c} + \sigma_{Nu}
   \qquad
   \lambda_s = \min\!\left(\sqrt{\frac{2}{1 + 0.004\,d}},\ 1.0\right)

(:math:`d` in mm; the imperial form is :math:`\sqrt{2/(1 + d/(10\,\text{in}))}`.)

.. note::

   The :math:`\le 1.0` cap is part of the code equation and is easy to drop. The
   size effect factor exists to **reduce** :math:`V_c` in deep members; left
   uncapped it exceeds 1 for :math:`d < 250` mm and inflates :math:`V_c` instead.
   The combination that reaches this branch — no minimum stirrups **and** a shallow
   section — is in practice a slab, which is exactly where it matters most.

The result is bounded above (§22.5.5.1.1):

.. math::

   V_c = \min\Big(0.42\,\lambda\sqrt{f'_c}\,A_{cv},\ \max(0,\ k_c A_{cv})\Big)
   \qquad A_{cv} = b_w\, d

.. important::

   :math:`\rho_w` uses the reinforcement on the **tension** face for the combination
   being checked — bottom steel for a positive moment, top steel for a negative one.
   A combination with no moment therefore uses the bottom steel. Because
   :math:`V_c \propto \rho_w^{1/3}`, a section with no longitudinal steel computes
   :math:`V_c = 0`, and with no stirrups either its shear capacity is zero. mento
   warns and reports an infinite DCR rather than raising. A *design* never produces
   that situation — see :ref:`aci-decisions` — but a *check* on a user-supplied
   layout can, and slabs start with no reinforcement on either face.

Steel contribution and total strength
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. math::

   V_s = A_v f_{yt} d
   \qquad
   \phi V_n = \phi_v \left(V_c + A_v f_{yt} d\right)

with :math:`f_{yt} \le 420` MPa (60 ksi) per §20.2.2.4. The section is also capped
by §22.5.1.2:

.. math::

   \phi V_{max} = \phi_v\left(V_c + 0.66\,\lambda\sqrt{f'_c}\,A_{cv}\right)

and the reported DCR uses :math:`\min(\phi V_n,\ \phi V_{max})` as the capacity, so
exceeding the upper bound is surfaced rather than silently allowed.

Minimum shear reinforcement
^^^^^^^^^^^^^^^^^^^^^^^^^^^

§9.6.3.1 — no minimum stirrups are required while

.. math::

   V_u < 0.083\,\phi_v\,\lambda\sqrt{f'_c}\,A_{cv}
   \quad\text{(MPa)}

Above that threshold, Table 9.6.3.4 gives

.. math::

   A_{v,min} = \max\left(0.062\sqrt{f'_c}\,\frac{b_w}{f_{yt}},\
                         0.35\,\frac{b_w}{f_{yt}}\right)
   \quad\text{(MPa)}

and the required area is

.. math::

   A_{v,req} = \max\left(\frac{V_u - \phi V_c}{\phi_v\, f_{yt}\, d},\ A_{v,min}\right)

Spacing limits
^^^^^^^^^^^^^^

Table 9.7.6.2.2, keyed on the nominal :math:`V_s` the stirrups must carry,
:math:`V_{s,req} = (V_u - \phi V_c)/\phi`. The threshold is
:math:`0.33\sqrt{f'_c}\,b_w d` (:math:`4\sqrt{f'_c}\,b_w d` in psi), with the plain root:
the table carries neither the §22.5.3.1 ceiling on :math:`\sqrt{f'_c}` nor
:math:`\lambda`. CIRSOC 201-25 Tabla 9.7.6.2.2 prints the same threshold and fractions with
other absolute caps:

.. list-table::
   :header-rows: 1
   :widths: 34 22 22 22

   * - Condition
     - :math:`s_{max}` along length
     - :math:`s_{max}` across width
     - CIRSOC 201-25 caps
   * - :math:`V_s \le 0.33\sqrt{f'_c}\,b_w d`
     - :math:`\min(d/2,\ 600\ \text{mm})`
     - :math:`\min(d,\ 600\ \text{mm})`
     - 400 mm, 400 mm
   * - :math:`V_s > 0.33\sqrt{f'_c}\,b_w d`
     - :math:`\min(d/4,\ 300\ \text{mm})`
     - :math:`\min(d/2,\ 300\ \text{mm})`
     - 200 mm, 200 mm

The check records the threshold and the row it took (``ShearCheck.V_s_threshold``,
``spacing_halved``), and the report prints both.

The limit across the width is on the legs. mento's cage is ``n`` closed stirrups, so
:math:`2n` legs, spread evenly between the centres of the outermost pair:

.. math::

   s_w = \frac{b - 2c_c - d_{b,st}}{2n - 1}

-- one closed perimeter and open interior legs in calculation geometry.
Detailing may propose 135°/90° crossties for required compression support
(§25.3.5 and Table 25.3.2), with longitudinal alternation explicitly required;
read ``beam.detailing_geometry`` for the physical arrangement. A design starts from the fewest legs that keep
:math:`s_w \le s_{max,w}`: a 150×150 CIRSOC beam whose :math:`V_{s,req}` = 4828 kN passes
the 3569 kN threshold is held to 200 mm, which eight legs (20.40 cm) miss and ten
(15.87 cm) meet, so it takes ten calculation legs (five two-leg equivalents).

Where the stirrups also brace compression bars, §9.7.6.4.3 caps the spacing along the
member at the least of 16 :math:`d_b` of the bar, 48 :math:`d_b` of the stirrup and the least
dimension of the beam. It is a limit of the section, reported apart as
``ShearDesign.s_max_l_support``; ``s_max_l`` is the lesser of it and the table's. The
report's limits table gives it a row of its own, with the verdict of the warning
``stirrup_spacing_exceeds_compression_support``, beside the along-length row it may
undercut.

.. _aci-skin:

Skin reinforcement
------------------

§9.7.2.3 asks for longitudinal skin reinforcement on both side faces of a beam deeper
than 900 mm (36 in.), over :math:`h/2` from the tension face, at the spacing
:math:`s` of §24.3.2 with :math:`c_c` the clear cover from the skin bars to the side face
and :math:`f_s = \tfrac{2}{3} f_y` (§24.3.2.1):

.. math::

   s = \min\left(380\,\frac{280}{f_s} - 2.5\,c_c,\; 300\,\frac{280}{f_s}\right) \quad [\text{mm, MPa}]

ACI asks for no area and no diameter. mento lays skin out by a criterion of its own that
meets this clause wherever it applies and goes beyond it (the same under every code):

- **From 60 cm, not 90.** Web cracks above the main bars open wider than at their level
  well before 90 cm; skin from 60 cm is common practice, and the bars are few.
- **Over the whole height.** The bars run from the bottom layer to the top layer, not over
  the tension half alone. In a continuous beam the tension face changes between span and
  support, and one layout over the whole height covers :math:`h/2` from either face with
  the same bars along the member. The count per side is the least that keeps them at
  most :math:`s` apart: :math:`n = \lceil (y_{top} - y_{bot}) / s \rceil - 1`, evenly
  spaced, the gaps to the two layers included.
- **Diameter below 1 m**: Ø8 up to a 40 cm web, Ø10 above (No. 3 / No. 4), never below
  ``BeamSettings.skin_bar_diameter``. A preference: ACI fixes none.
- **Diameter from 1 m**: the smallest that gives, inside the tension zone, the minimum
  area EN 1992-1-1 §7.3.3(3) asks of deep beams (see :ref:`en-skin`), with more bars if
  none does. mento takes it as the envelope of both codes for deep beams: ACI has no area
  requirement, and EN's grows with the width of the web. For an ACI concrete
  :math:`f_{ct}` is taken as :math:`0.30\,f'^{2/3}_c` (EN Table 3.1) and
  :math:`f_{yk} = f_y`. The tension zone ends at the neutral axis, which mento takes at
  :math:`x = 0.4\,h` from the compression face.

The status is ``required`` above 900 mm, where §9.7.2.3 applies, and ``proposed`` from
60 cm to 900 mm. Skin steel is not credited to the moment or shear strength.

.. _aci-decisions:

Implementation decisions
------------------------

Where the code leaves room for interpretation, this is what mento does.

Geometric minimum of 1.8‰
^^^^^^^^^^^^^^^^^^^^^^^^^

In addition to the §9.6.1.2 mechanical minimum, mento enforces a **geometric**
minimum of :math:`1.8\text{‰}\,b\,h` on the tension face. This is not an ACI
provision; it is common detailing practice and it prevents two degenerate outcomes:

1. When §9.6.1.3's 4/3 rule would drop the steel below any sensible detailing
   amount, the geometric minimum takes over.
2. When :math:`M_u = 0` — a shear-only load combination — §9.6.1.2 requires no
   flexural steel at all, so the design would return :math:`A_s = 0`. That is not a
   buildable layout, and it makes :math:`\rho_w = 0`, which collapses :math:`V_c` to
   zero in Table 22.5.5.1. mento adopts the geometric minimum instead.
   It goes on the **bottom** face, which a member always carries steel on, and the
   check holds a bottom with no moment to the same floor (no 4/3 relief, since there
   is no :math:`A_{s,calc}` to relieve it against), warning ``As_below_min`` if it is
   bare. A top face that no combination puts in tension is held to no minimum.

Order of the minimum-reinforcement rules
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

When :math:`A_{s,calc} < A_{s,min}`, mento evaluates :math:`\tfrac{4}{3}A_{s,calc}`
and adopts it **only if** it is both smaller than :math:`A_{s,min}` (so it actually
saves steel) and not smaller than the geometric minimum. Otherwise the governing
value is :math:`A_{s,min}`, or the geometric minimum, whichever applies. The results
tables flag whether the 4/3 rule was used.

Displaced-concrete correction
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Compression reinforcement contributes :math:`(f_y - 0.85 f'_c)` rather than
:math:`f_y`, both in equilibrium and in :math:`M_n`. Many textbook treatments omit
this and slightly overestimate capacity. mento applies it consistently.

Exact :math:`a_{max}` instead of the 0.59 shortcut
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The Whitney block depth at the ductility limit is taken as
:math:`a_{max} = \beta_1 c_t` exactly, rather than the common shortcut
:math:`d - 0.59\rho f_y d/f'_c`, which relies on :math:`0.59 \approx 1/1.7` and loses
roughly 0.3% of precision.

A design passes its own check
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The design accepts a layout only if it carries the moment **and** leaves the face in
tension within :math:`A_{s,max,eff}`. Three choices follow from that:

- **No bars between** :math:`A_{s,req}` **and** :math:`A_{s,max}`. A narrow web can
  jump from 4Ø12 to 2Ø20 with nothing in between. The design then takes the smallest
  layout past :math:`A_{s,req}` and adds the compression steel that keeps it
  tension-controlled, rather than a layout below :math:`A_{s,req}`.
- **Compression steel is chosen by depth, not only by area.** Two layers of thin bars
  sit deeper than one layer of thick ones, reach less stress and need more area. Each
  candidate is read at its own centroid, and the first — in the selector's order —
  that makes the tension face resist and stay tension-controlled is taken.
- **The faces are chosen together.** If the iteration ends on a layout that fails,
  every pair of the layouts it visited on the two faces is tried, and the lightest
  pair that works is kept; failing that, the closest within the limits. The loop
  stops early only when a *pair* of layouts repeats: one face settling while the
  other still moves is not a cycle.

When no layout works, the design leaves the closest one, and closest is read in a
fixed order: first what the design never trades for strength, then strength. A
layout must fit the width with the clear distance of §25.2.1 and, between the top
bars, room for the vibrator (``BeamSettings.vibrator_size``, site practice rather
than a clause: concrete the vibrator cannot reach is not consolidated), and it must
keep the section tension-controlled, which §9.3.3.1 (§7.3.3.1 for a slab) requires
and does not trade for a lower :math:`\phi`. Among the layouts that meet all three,
the one with the smallest DCR. A stronger layout that breaks one of them is no
solution, however close to 1 its DCR.

The layouts the iteration visits are few, and it searches the tension face under
the tension-controlled area of a section *without* compression steel. So when none
of them closes, the design also tries the layouts that fit, from two bars of the
smallest diameter allowed to two and a half times what the face carries, keeping
only those no other beats on both steel and depth: the same layout on both faces
first, then each face against what the other carries, until nothing changes. The
first face past the tension-controlled limit brought within it is progress even
while the other still is not, and a layout replaces the current one only if it
comes closer by more than 0.2 %. An ACI 40×25,
:math:`f'_c` = 25 MPa, :math:`c_c` = 40 mm under ±91.6 kN·m went from 2Ø10 + 5Ø10
in two layers on each face, DCR 1.47, to 7Ø16 in one layer, DCR 1.09, still
tension-controlled with the same bars opposite.

The design then warns ``As_below_required`` on the face that fell short and
``section_too_small_for_moment`` for the section, quoting the moment and what the
layout kept carries: the section has to grow. The same limits read on bars set by
hand are warnings of the check: ``clear_spacing_below_min``,
``clear_spacing_below_vibrator`` and ``not_tension_controlled``.

Effective depth from the real bar layout
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

:math:`d` is recomputed from the centroid of the bars actually placed, and the design
iterates on it. Software that assumes a fixed
:math:`d` — ETABS, for instance — will report slightly different required areas for
the same demand. The difference is geometric, not a disagreement about the code.

For shear, :math:`d_{shear} = \min(d_{bot},\ d_{top})`, the conservative choice when
both faces carry steel.

Validation
----------

Every row is pinned by a test. The rows verified against a published source — a
design guide, a software verification manual, a recorded program run — are tests in
``tests/validation/``, marked ``published_example``, each citing the page, table or
row its numbers come from. The other rows are tests in the rest of ``tests/``: checks
against the code clause itself, internal consistency, or regression cases whose only
reference is a Calcpad sheet, which reproduces a calculation but publishes none and
so is not counted as a validation.

.. list-table::
   :header-rows: 1
   :widths: 30 40 30

   * - Check
     - Test
     - Verified against
   * - :math:`A_{s,req}`, :math:`A_{s,min}`, :math:`A_{s,max}` at the critical
       sections of continuous beams, joists and edge beams (rectangular web and T
       sections solved as a rectangle of width :math:`b_f`)
     - ``test_flexure_ACI_318_19_CRSI_example_6_2``, ``_6_6``, ``_6_11``,
       ``_6_16``, ``_6_18``
     - CRSI, *Design Guide on the ACI 318 Building Code Requirements for Structural
       Concrete*, §6.9, Examples 6.2, 6.6, 6.11, 6.16 and 6.18 (Tables 6.24, 6.28,
       6.31, 6.34 and 6.35)
   * - :math:`A_{s,req}` and :math:`A_{s,min}`, singly reinforced rectangle
     - ``test_flexure_ACI_318_19_ETABS_example_001``
     - CSI Software Verification, ETABS, *ACI 318-19 Example 001*, pp. 2–3
   * - :math:`M_n`, singly reinforced
     - ``test_determine_nominal_moment_simple_reinf_ACI_318_19_Test_Etabs_03``
     - ETABS run *Test_Etabs_03*, recorded in the workbook
       *BEAM-01-Flexure-Rectangle ACI 318-19-v6*
   * - :math:`M_n`, doubly reinforced (steel not yielding)
     - ``test_determine_nominal_moment_double_reinf_ACI_318_19_Test_Etabs_01``
     - ETABS run *Test_Etabs_01*, same workbook
   * - :math:`M_n`, doubly reinforced (steel yielding)
     - ``test_determine_nominal_moment_double_reinf_ACI_318_19_Test_Etabs_23_yielding``
     - ETABS run *Test_Etabs_23*, same workbook
   * - :math:`A_{s,req}`, :math:`A_{s,min}` governing
     - ``test_calculate_flexural_reinforcement_ACI_318_19_Test_Etabs_05``
     - ETABS, :math:`A_{s,req} = 1.7041\ \text{in}^2`
   * - :math:`A_{s,req}`, doubly reinforced
     - ``test_calculate_flexural_reinforcement_ACI_318_19_doubly_reinforced_Test_Etabs_01``
     - ETABS
   * - :math:`\rho_{max}`
     - ``test_maximum_flexural_reinforcement_ratio_ACI_318_19_Test_Etabs_05``
       (``tests/elements/test_beam.py``)
     - Regression: the workbook's own hand calculation; the published values of
       :math:`A_{s,max}` are the CRSI rows above
   * - :math:`\rho_{min}`
     - ``test_minimum_flexural_reinforcement_ratio_ACI_318_19_Test_Etabs_05``
     - ETABS run *Test_Etabs_05*, where the minimum governs; §9.6.1.2
   * - Flexure check, full section
     - ``test_check_flexure_ACI_318_19_3`` (``tests/elements/test_beam.py``)
     - Regression against a Calcpad sheet, with the Whitney block redone by hand in
       the test
   * - Flexure check, past the tension-controlled limit
     - ``test_check_flexure_ACI_318_19_1``, ``_2``,
       ``test_check_flexure_ACI_318_19_over_reinforced_*``,
       ``test_check_flexure_CIRSOC_201_25_over_reinforced_reports_its_real_strength``
     - Strain compatibility written apart from mento, in the tests
   * - Design passes its own check; capacity is the section's
     - ``test_a_design_passes_its_own_check`` (``tests/design/test_flexure_design_properties.py``)
     - Sweep over width, depth, :math:`f'_c` and moment, against the same independent
       strain compatibility
   * - :math:`A_{s,req}` never drops as :math:`M_u` grows
     - ``test_the_steel_asked_for_grows_with_the_moment``
     - Monotonicity
   * - Flexure design, doubly reinforced
     - ``test_design_flexure_ACI_318_19_Test_Etabs_01``
     - ETABS, verified through :math:`\phi M_n \ge M_u`
   * - Shear: :math:`\phi V_c`, :math:`V_u - \phi V_c`, :math:`A_{v,min}/s`,
       :math:`A_v/s` required and :math:`s_{max}` along and across the beam
     - ``test_shear_check_ACI_318_19_CRSI_example_6_3``, ``_6_7``, ``_6_12``,
       ``_6_17``, ``_6_18``
     - CRSI, *Design Guide on the ACI 318 Building Code Requirements for Structural
       Concrete*, §6.9, Examples 6.3, 6.7, 6.12, 6.17 and 6.18
   * - Shear: :math:`\phi V_c`, :math:`\phi V_{max}`, :math:`A_v/s` and
       :math:`A_{v,min}/s`
     - ``test_shear_check_ACI_318_19_ETABS_example_001``
     - CSI Software Verification, ETABS, *ACI 318-19 Example 001*, pp. 2, 6–7
   * - Shear check, with stirrups
     - ``test_shear_check_ACI_318_19_1``, ``_2`` (``tests/elements/test_beam.py``)
     - Regression against a Calcpad sheet (axial load included)
   * - Shear check, no stirrups
     - ``test_shear_check_ACI_318_19_no_rebar_1``, ``_2`` (``tests/elements/test_beam.py``)
     - Regression against a Calcpad sheet (row (c) of Table 22.5.5.1)
   * - Shear design
     - ``test_shear_design_ACI_318_19`` (``tests/elements/test_beam.py``)
     - Regression against a Calcpad sheet
   * - Shear design, CIRSOC catalogue
     - ``test_shear_design_CIRSOC_201_2025``
     - CIRSOC 201-25 bar catalogue
   * - Threshold of Table 9.7.6.2.2
     - ``test_max_stirrup_spacing_threshold_is_033_not_0083``
       (in ``tests/equations/test_aci_318_19_shear_equations.py``)
     - Table 9.7.6.2.2: :math:`0.33\sqrt{f'_c}\,b_w d`
   * - Legs across the width
     - ``test_min_legs_along_width``
     - Hand count of :math:`s_w = (b - 2c_c - d_b)/(n_{legs} - 1)`
   * - Five stirrups for the across-width limit
     - ``test_wide_cirsoc_beam_takes_five_stirrups_for_the_across_width_limit``
     - CIRSOC 201-25 Tabla 9.7.6.2.2, 200 mm cap
   * - Geometric minimum at :math:`M_u = 0`
     - ``test_design_flexure_ACI_318_19_zero_moment_adopts_geometric_minimum``
     - Internal consistency: :math:`\rho_w > 0`, :math:`V_c > 0`
   * - Never raises on an unfittable section
     - ``test_design_flexure_rebar_infeasible_does_not_crash``
     - Public contract
   * - :math:`\lambda_s \le 1.0` cap
     - ``test_lambda_s_is_capped_at_one_imperial`` / ``_metric``
       (in ``tests/elements/test_slab.py``)
     - §22.5.5.1.3
   * - Zero capacity reported, not raised
     - ``test_shear_check_with_no_tension_reinforcement_warns_and_does_not_raise``,
       ``test_flexure_check_with_no_bottom_reinforcement_floors_phi_Mn``
       (in ``tests/elements/test_slab.py``)
     - Public contract: a check reports ``DCR``, it does not blow up
