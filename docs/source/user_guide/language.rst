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

Passing anything else raises ``ValueError`` and leaves the current language in place.

What is translated
------------------

The language applies to the detailed reports of every element — ``RectangularBeam``,
``OneWaySlab`` and ``ShearWall``:

- ``flexure_results_detailed()`` and ``shear_results_detailed()``, printed to the console
- ``flexure_results_detailed_doc()`` and ``shear_results_detailed_doc()``, written to Word

and to the summaries, :doc:`beam_summary`, :doc:`slab_summary` and :doc:`shear_wall_summary`:

- ``check()``, ``flexure_results()`` and ``shear_results()``, whose DataFrames come back
  with their headers translated
- ``results_detailed_doc()``, written to Word
- what ``design()``, ``export_design()`` and ``import_design()`` print
- the ``message`` of the errors and warnings a summary raises reading its tables
  (:class:`~mento.summary_tables.SummaryInputError`,
  :class:`~mento.summary_tables.SummaryInputWarning`), whose ``str()`` stays in English

Table headers, row labels and document headings are translated. These are deliberately
left as they are:

- **Variable names** — ``fc``, ``Av``, ``ØVn``, ``DCR`` are the notation of the design
  code and stay identical in every language. This is why a summary table translates
  ``Beam`` and ``Position`` but leaves ``As,bot`` and ``DCRv`` alone.
- **Units and numbers** — ``cm``, ``MPa``, ``kNm``.
- **Bar notation** — ``Ø16``, ``#6``, ``@``. Only the stirrup mark is the language's:
  ``1sØ10/22`` (*stirrup*) in English, ``1eØ10/22`` (*estribo*) in Spanish.
- **The design code designation** — ``CIRSOC 201-25`` keeps its official name.
- **Generated file names** — a project keeps one naming scheme regardless of the language
  its reports are written in.
- **The tables a summary reads and writes** — the sheets ``Sections`` and ``Forces`` and
  their headers, so a file reads back in any language — and the warning codes of the
  ``Warnings`` column of ``check()`` (``As_below_min (bottom)``), which a program reads.
- **The API itself** — arguments, attributes and error messages remain English.

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
