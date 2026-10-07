.. _user_guide/language:

Report language
===============

The detailed reports are written in English by default. ``set_language`` switches them to
another language for the rest of the session, so it is written once, before the reports are
produced:

.. code-block:: python

    import mento

    mento.set_language("es")

Every report produced afterwards comes out in Spanish:

.. code-block:: python

    from mento import Concrete_CIRSOC_201_25, SteelBar, RectangularBeam, Node, Forces
    from mento import MPa, cm, mm, kN, kNm

    concrete = Concrete_CIRSOC_201_25(name="H25", f_c=25 * MPa)
    steel = SteelBar(name="ADN 420", f_y=420 * MPa)
    beam = RectangularBeam(
        label="101", concrete=concrete, steel_bar=steel,
        width=20 * cm, height=60 * cm, c_c=25 * mm,
    )

    node = Node(section=beam, forces=[Forces(label="C1", V_z=80 * kN, M_y=100 * kNm)])
    node.design()

    node.shear_results_detailed()        # console tables in Spanish
    node.shear_results_detailed_doc()    # Word document in Spanish

.. code-block:: text

    ===== RESULTADOS DETALLADOS DE CORTE DE VIGA =====
    Materiales                            Variable     Valor  Unidad
    -----------------------------------  ----------  -------  --------
    Identificación de la sección                          101
    Resistencia del hormigón                 fc            25  MPa
    Tensión de fluencia del acero            fy           420  MPa

The available languages are ``"en"`` and ``"es"``:

.. code-block:: python

    mento.available_languages()   # ('en', 'es')
    mento.get_language()          # 'es'

Passing anything else raises ``ValueError`` and leaves the current language in place. So
does an explicit ``language`` argument of ``notation()``, ``arrangement()`` and the
functions behind them: ``notation("es-AR")`` raises rather than falling back to English.

What is translated
------------------

The language applies to the detailed reports of every element — ``RectangularBeam``,
``OneWaySlab`` and ``ShearWall``:

- ``flexure_results_detailed()`` and ``shear_results_detailed()``, printed to the console
- ``flexure_results_detailed_doc()`` and ``shear_results_detailed_doc()``, written to Word

and to the summaries, :doc:`beam_summary` and :doc:`shear_wall_summary`:

- ``check()``, ``flexure_results()`` and ``shear_results()``, whose DataFrames come back
  with their headers translated
- ``results_detailed_doc()``, written to Word

It also applies to:

- the text of the section drawing, ``beam.plot()``;
- the warning messages, ``DesignWarning.message``, worded when ``warnings`` is read;
- the stirrup notation and the description of the cage, asked for through ``notation()``
  and ``arrangement()`` of ``reinforcement.transverse``, ``shear_design`` or an option.

.. code-block:: python

    mento.set_language("es")
    beam.shear_design.notation()      # '2 ramas Ø6 mm c/28 cm · 14.4 cm entre ramas (máx. 40 cm)'
    beam.shear_design.arrangement()   # 'estribo perimetral'
    beam.shear_design.notation("en")  # '2 legs Ø6 mm @ 28 cm · 14.4 cm between legs (max 40 cm)'
    str(beam.shear_design)            # always English, whatever the language

Table headers, row labels and document headings are translated. These are deliberately
left as they are:

- **Variable names** — ``fc``, ``Av``, ``ØVn``, ``DCR`` are the notation of the design
  code and stay identical in every language. This is why a summary table translates
  ``Beam`` and ``Position`` but leaves ``As,bot`` and ``DCRv`` alone.
- **Units and numbers** — ``cm``, ``MPa``, ``kNm``.
- **Bar notation** — ``Ø16`` and ``#6`` stay unchanged. ``notation()`` translates
  the transverse label: ``2 legs Ø10 @ 22`` / ``2 ramas Ø10 c/22``.
- **The design code designation** — ``CIRSOC 201-25`` keeps its official name.
- **Generated file names** — a project keeps one naming scheme regardless of the language
  its reports are written in.
- **The API itself** — arguments, attributes, ``str()`` of the reinforcement, design and
  check results (``mento.design_results``) and error messages remain English;
  ``notation()``, ``arrangement()`` and the warning messages follow the language. A
  ``DesignWarning`` is the one result whose ``str()`` follows it too: its ``str()`` is its
  ``message``.

A label with no translation is written in English rather than raising, so a report always
renders.

.. note::

   The Jupyter output of the ``results`` properties is not translated yet, and stays in
   English.

Adding a language
-----------------

A language is data, not code. ``mento/i18n.py`` holds one mapping per language, from the
English string a report builder emits to its translation, and registers it in
``_CATALOGS``. The English text is the key, so the design code modules under ``mento/codes``
never have to know a language exists.

A translation only has to carry the strings it wants to change; anything absent falls back
to English. ``tests/reports/test_i18n.py`` runs the real reports for every design code and asserts
the Spanish catalog covers every string they emit, so a label added without a translation
fails the test suite.
