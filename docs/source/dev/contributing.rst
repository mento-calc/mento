.. _dev/contributing:

Contributing to Mento
=====================

Contributions of every size are welcome, from fixing a typo in these docs to implementing a
whole new design code.

The full contributing guide lives in the repository, at `CONTRIBUTING.md
<https://github.com/mento-calc/mento/blob/main/CONTRIBUTING.md>`__. This page summarises
what you need to get started locally. By participating you agree to abide by our
:ref:`Code of Conduct <dev/codeofconduct>`.

Mento uses (and thanks):

- GitHub to host the code
- GitHub Actions to test all commits and PRs
- codecov to monitor test coverage
- ReadTheDocs to host the documentation
- ruff for linting and formatting, mypy for type checking, and pre-commit to enforce them
- pytest to write tests
- Sphinx to write docs
- pint for units
- `CalcPad`_ to reproduce the published examples a calculation is validated against
- GitHub Discussions for community support.

.. _CalcPad: https://github.com/Proektsoftbg/Calcpad

Ways to contribute
------------------

**Report an issue.** Bugs, wrong results, documentation problems and feature requests all go
to the `issue tracker <https://github.com/mento-calc/mento/issues>`__, which has
templates for each. If a design result looks wrong, include the inputs, the value Mento
produced, and the expected value with its source.

**Ask a question.** Use `Discussions
<https://github.com/mento-calc/mento/discussions>`__.

**Contribute code.** Issues labelled ``good first issue`` and ``help wanted`` are the easiest
place to start. For anything substantial, open a Discussion first so we can agree on the
approach before you write code.

Setting up your environment
---------------------------

Mento requires Python 3.12 or newer.

.. code-block:: bash

    $ git clone https://github.com/mento-calc/mento.git
    $ cd mento
    $ python -m venv venv
    $ source venv/bin/activate      # Windows: venv\Scripts\activate
    $ pip install -e ".[dev]"
    $ pre-commit install

The ``[dev]`` extra brings in the test suite, ruff, mypy and pre-commit. There is also
``[docs]`` for building the documentation, and ``[test]`` if you only need to run tests.

Development workflow
--------------------

1. Create a branch off ``main``.
2. Make your changes, with tests and documentation alongside the code.
3. Run the checks below until they are clean.
4. Open a pull request against ``main``, writing ``Closes #<issue number>`` in the
   description.

We will not merge a pull request if tests fail, if calculations are not validated against a
recognised source, if linting or type checking does not pass, or if the documentation builds
with errors.

Running the checks
------------------

.. code-block:: bash

    $ pytest                        # test suite, with coverage
    $ ruff check . --fix            # lint
    $ ruff format .                 # format
    $ mypy mento/                   # strict type checking
    $ pre-commit run --all-files    # everything the hooks enforce

To build the documentation:

.. code-block:: bash

    $ pip install -e ".[docs]"
    $ cd docs
    $ make html

Writing tests
-------------

- For bug fixes, add a regression test that fails before your change and passes after it.
- For new features, add tests in the test module matching the source module — code in
  ``mento/beam.py`` is tested in ``tests/elements/test_beam.py``. The folders of ``tests/``
  follow the package: ``equations/``, ``materials/``, ``sections/``, ``elements/``,
  ``design/``, ``reports/``, ``architecture/``.
- A test whose numbers come from a published source — a book, a code or design guide
  example, a software verification manual, a recorded run of another program — goes in
  ``tests/validation/``, and only those go there (see *Calculation validation*). A test
  checked only against a Calcpad sheet is a regression test and goes with the rest.
- Prefer plain functions to classes for tests.
- Use ``pytest.mark.parametrize`` for families of similar cases, and fixtures instead of
  constructing the same beam or material repeatedly.
- Compare physical quantities with an explicit tolerance rather than exact equality.

Calculation validation
----------------------

Every contribution that touches a design calculation must be validated before it is merged.
This is what makes Mento trustworthy.

1. Find a published reference example: the design code itself, an official design guide
   (the CRSI design guide, the Concrete Centre guides), a recognised structural engineering
   textbook, or a software verification manual (CSI's ETABS/SAFE examples). Name it in your
   issue or pull request.
2. Include the reference with your pull request: the PDF of the book, code or guide, or the
   pages you used, with the page numbers where the calculation is. When the document may not
   be redistributed, give its full citation (title, edition, section, example and page)
   instead, so a reviewer can open the page the expected numbers were read from.
3. Reproduce it in `CalcPad`_, with units, including the edge cases the implementation needs
   to handle, and include the CalcPad file with your pull request. The CalcPad sheet is the
   working reproduction; it does not replace the published reference of step 2.
4. Reference the validation source in your test module — the document, the section, the
   example number and the page — so the next reader can trace where the expected numbers
   came from.
5. Mark the test ``@pytest.mark.published_example`` when its expected numbers come from that
   published source and not from mento: the release counts these tests for the home page of
   mento-web, so the mark is a public claim. A marked test says where the number is, in a
   docstring paragraph that starts with ``Source:`` (the page, table, example or section; for
   a workbook of program runs, the sheet and the row and column), and lives in
   ``tests/validation/``; ``tests/architecture/test_published_examples.py`` checks both, and
   fails a ``Source:`` that names a CalcPad sheet. A test checked only against a CalcPad sheet,
   one that pins mento's own output, or a reading of the code the reference does not share,
   is not marked and goes with the rest.

If no published example exists for what you are implementing, say so in the pull request and
we will work out an acceptable validation path together.
