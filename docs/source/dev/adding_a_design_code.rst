.. _dev/adding_a_design_code:

Adding a design code
====================

This is the most valuable contribution you can make to mento, and the one the codebase is
organised around. Element classes such as ``RectangularBeam`` hold geometry, reinforcement
and results; the clauses of a standard live in their own module under ``mento/codes/``.
Adding a standard therefore means writing a new module, not editing the element classes.

This page describes the contract that module has to satisfy. ``mento/codes/ACI_318_19_beam.py``
and ``mento/codes/EN_1992_2004_beam.py`` are the two worked examples to read alongside it.

Before writing code
-------------------

Open a `discussion <https://github.com/mento-calc/mento/discussions>`_ first. Two things
are worth settling before you start:

* **A validation source.** Every calculation has to be validated against a worked example
  published outside mento: the standard itself, an official design guide, a recognised
  textbook or a software verification manual. A Calcpad sheet reproduces the example but
  does not stand in for it. Agreeing on
  which examples you will reproduce is the single best predictor of the pull request being
  mergeable. See :ref:`dev/contributing` for the validation workflow.
* **Scope.** A standard is large. One pull request that implements shear for one element
  type is much easier to review, and much more likely to land, than one that attempts an
  entire code at once. ACI 318-19 arrived that way, over several rounds.

Step 1 — the material class
---------------------------

A design code is selected by the concrete instance, in ``mento/material.py``. Add a
subclass of ``Concrete`` that sets ``design_code`` in its ``__post_init__``:

.. code-block:: python

    @dataclass
    class Concrete_AS_3600_2018(Concrete):
        def __post_init__(self) -> None:
            super().__post_init__()   # sets unit_system and density — call this first
            self.design_code = "AS 3600-2018"

If your standard is a national adoption of one already implemented, subclass that one
instead of ``Concrete`` and override only what differs. ``Concrete_CIRSOC_201_25``
subclasses ``Concrete_ACI_318_19`` and changes little more than the label.

Never read the unit system from anywhere else: ``Concrete.__post_init__`` derives it from
the units of ``f_c`` (MPa means metric, psi means imperial), and it propagates from there
through settings, forces and results.

Step 2 — the code module
------------------------

Create ``mento/codes/<CODE>_beam.py``. Its functions take the element as an explicit first
argument, annotated as the element type, rather than being methods:

.. code-block:: python

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from mento.beam import RectangularBeam

    def _check_shear_AS_3600_2018(self: "RectangularBeam", force: Forces) -> pd.DataFrame:
        ...

The ``TYPE_CHECKING`` guard is what keeps the import one-directional and avoids a circular
import, since ``beam.py`` imports this module at runtime.

Four functions form the contract that ``RectangularBeam`` dispatches to:

.. list-table::
   :header-rows: 1
   :widths: 34 44 22

   * - Function
     - Signature
     - Returns
   * - ``_check_shear_<CODE>``
     - ``(self, force: Forces)``
     - ``pd.DataFrame``
   * - ``_check_flexure_<CODE>``
     - ``(self, force: Forces)``
     - ``pd.DataFrame``
   * - ``_design_shear_<CODE>``
     - ``(self, force: Forces)``
     - ``None``
   * - ``_design_flexure_<CODE>``
     - ``(self, max_M_y_bot: Quantity, max_M_y_top: Quantity)``
     - ``None``

The two ``check`` functions are called once per load combination and return one row of
results. The two ``design`` functions size the reinforcement and write it onto the element
through ``set_longitudinal_rebar_bot`` / ``set_longitudinal_rebar_top`` /
``set_transverse_rebar``; ``design_flexure`` receives the governing moments for each face
rather than a single force, because the reinforcement is designed for the envelope.

Everything else in the module is yours to organise. Both existing modules split the work
into small helpers — ``_calculate_concrete_shear_strength_*``, ``_calculate_A_v_min_*`` and
so on — which is what makes them reviewable clause by clause, and worth imitating.

Step 3 — wire up the dispatch
-----------------------------

``beam.py`` selects the implementation from ``self.concrete.design_code`` in four places:
``design_flexure``, ``check_flexure``, ``design_shear`` and ``check_shear``. Add a branch to
each:

.. code-block:: python

    elif self.concrete.design_code == "AS 3600-2018":
        result = _check_flexure_AS_3600_2018(self, force)

Step 4 — results dictionaries
-----------------------------

Detailed output is built from dictionaries the code module populates — see
``_initialize_dicts_EN_1992_2004_shear`` for the shape. Fill these in if you want your code
to work with ``shear_results_detailed()``, the Word export and ``BeamSummary``. A pull
request that implements the calculations but not these is still worth opening; say so in
the description and it can be finished separately.

Step 5 — tests and validation
-----------------------------

Add ``tests/elements/test_<code>_beam.py`` for the behaviour, and put the worked examples in
``tests/validation/test_<code>_beam_validated.py``. At minimum:

* one test per worked example you validated against, in ``tests/validation/``, asserting
  the values the source publishes, marked ``published_example`` and with a ``Source:``
  paragraph in its docstring;
* the unit system your standard uses, and the other one too if you support both;
* a case with no shear reinforcement, and one where the demand exceeds capacity, so the
  ``DCR > 1`` path is exercised.

Prefer ``pytest.mark.parametrize`` over near-duplicate test functions, and use fixtures for
the section and materials rather than rebuilding them in each test.

.. code-block:: bash

    pytest tests/elements/test_<code>_beam.py tests/validation/ --override-ini="addopts=" -v
    mypy mento/
    pre-commit run --all-files

Note that ``mypy mento/`` is enforced in continuous integration, and that new modules are
expected to pass it: ``pyproject.toml`` carries a list of modules exempted from strict
checking, and it is meant to shrink, not grow.

Step 6 — documentation
----------------------

* Add the module to ``docs/source/api/mento.codes.rst``.
* Add the standard to the feature list in ``README.md`` and to ``CHANGELOG.md``.
* Add an example notebook under ``docs/source/examples/`` if the code is user facing.

What a reviewable pull request looks like
-----------------------------------------

* The calculations match a named published example, and the validation files are included:
  the PDF or pages of the source with the page numbers (or its full citation), and the
  Calcpad sheet that reproduces it.
* The new module does not import from other code modules; shared behaviour belongs to the
  element class or to ``rebar.py``.
* No unit assumptions are hard-coded.
* Existing public names are untouched. Adding is fine, renaming is a separate discussion.
