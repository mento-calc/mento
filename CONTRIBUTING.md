# Contributing to mento

Thanks for your interest in mento. This project is built by structural engineers for
structural engineers, and contributions of every size are welcome — from fixing a typo in
the documentation to implementing a whole new design code.

By participating in this project you agree to abide by our
[Code of Conduct](CODE_OF_CONDUCT.md).

## Table of contents

- [Ways to contribute](#ways-to-contribute)
- [Setting up your environment](#setting-up-your-environment)
- [Development workflow](#development-workflow)
- [Running tests](#running-tests)
- [Linting and type checking](#linting-and-type-checking)
- [Building the documentation](#building-the-documentation)
- [Calculation validation](#calculation-validation)
- [Pull request checklist](#pull-request-checklist)
- [Project structure](#project-structure)
- [Making a release](#making-a-release)
- [Archiving on Zenodo](#archiving-on-zenodo)
- [Publishing on conda-forge](#publishing-on-conda-forge)
- [Tools we use](#tools-we-use)

## Ways to contribute

**Report a bug.** Open an [issue](https://github.com/mihdicaballero/mento/issues/new/choose)
using the bug report template. A short reproducible snippet with materials, geometry and
forces is worth more than a long description.

**Request a feature or a design code.** Use the feature request template, or the *design
code request* template when you are asking for a new code, article or check. Tell us which
standard and which clause, and point us to a worked example we can validate against.

**Ask a question or share how you use mento.** Head to
[Discussions](https://github.com/mihdicaballero/mento/discussions). Questions there often
turn into documentation improvements.

**Contribute code or documentation.** Look for issues labelled `good first issue` or
`help wanted`. If you plan to work on something substantial, open a Discussion or comment
on the issue first so we can agree on the approach before you write code.

**Implement a design code.** This is the contribution the codebase is organised around, and
it has its own guide:
[Adding a design code](https://mento-docs.readthedocs.io/en/latest/dev/adding_a_design_code.html)
describes the four functions a new standard has to provide, where to wire them in, and what
the tests and validation should cover.

## Setting up your environment

mento requires Python 3.12 or newer.

```bash
git clone https://github.com/mihdicaballero/mento.git
cd mento
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -e ".[dev]"
pre-commit install
```

Conda works equally well if you prefer it:

```bash
conda create -n mento python=3.12
conda activate mento
pip install -e ".[dev]"
pre-commit install
```

The `[dev]` extra brings in the test suite, ruff, mypy and pre-commit. There is also
`[docs]` for building the documentation, and `[test]` if you only need to run tests.

## Development workflow

1. Fork the repository and create a branch off `main`. Use a short descriptive name, for
   example `punching-en-1992` or `fix-stirrup-spacing`.
2. Make your changes, with tests and documentation alongside the code.
3. Run the checks locally (see the sections below). `pre-commit run --all-files` covers
   linting and formatting; run it until it reports no changes.
4. Push to your fork and open a pull request against `main`.
5. Reference the issue you are closing in the PR description — `Closes #123`.

We will not merge a pull request if tests fail, if calculations are not validated against a
recognised source, if linting or type checking does not pass, or if the documentation build
produces errors. All of these run automatically on your PR.

## Running tests

mento uses pytest. The default options in `pyproject.toml` already enable coverage.

```bash
# Full suite
pytest

# A single file, without the coverage options
pytest tests/elements/test_beam.py --override-ini="addopts=" -v

# A single test
pytest tests/elements/test_beam.py::test_shear_check -v --override-ini="addopts="
```

When you add code, add tests for it:

- Bug fixes get a regression test that fails before your change and passes after it.
- New features get tests in the test module matching the source module — code in
  `mento/beam.py` is tested in `tests/elements/test_beam.py`. The folders of `tests/`
  follow the package: `equations/`, `materials/`, `sections/`, `elements/`, `design/`,
  `reports/`, `architecture/`.
- A test whose numbers come from a published source — a book, a code or design guide
  example, a software verification manual, a recorded run of another program — goes in
  `tests/validation/`, and only those go there (see step 5 below). A test checked only
  against a Calcpad sheet is a regression test and goes with the rest.
- Prefer plain test functions over test classes.
- Use `pytest.mark.parametrize` for families of similar cases, and fixtures instead of
  constructing the same beam or material over and over.
- Assert on physical quantities with their units, and compare with an explicit tolerance
  rather than exact equality.

## Linting and type checking

```bash
ruff check . --fix     # lint
ruff format .          # format
mypy mento/            # strict type checking
```

mento is typed and mypy runs in `strict` mode. New code needs complete type annotations,
including for pint quantities. Tests are exempt from requiring annotations, but the package
itself is not.

Some modules do not pass strict checking yet; they are listed explicitly in the `[tool.mypy]`
overrides in `pyproject.toml`. Everything else is enforced in CI, so a clean module cannot
regress. Cleaning up one of the listed modules and deleting its entry from that list is a
genuinely useful contribution — please do it in a pull request of its own, separate from any
behaviour change.

The line limit is 120 characters. `pre-commit` runs ruff and the formatter automatically on
commit, and continuous integration runs the same checks without auto-fixing.

## Building the documentation

Documentation lives in `docs/source` and is built with Sphinx.

```bash
pip install -e ".[docs]"
cd docs
make html
```

The result opens from `docs/build/html/index.html`. Example notebooks under
`docs/source/examples/` are executed by nbsphinx at build time, so they must run cleanly
against the current version of the package.

## Calculation validation

This is the part that makes mento trustworthy, and it is what we ask of every contribution
that touches a design calculation.

Before implementing a new check or design routine:

1. **Find a published reference example.** A worked example from the design code itself,
   an official design guide (the CRSI design guide, the Concrete Centre guides), a
   recognised structural engineering textbook, or a software verification manual (CSI's
   ETABS/SAFE examples). Tell us which one in the issue or pull request.
2. **Include the reference with your pull request: the PDF of the book, code or guide, or
   the pages you used, with the page numbers where the calculation is.** A reviewer has to
   be able to open the page the expected numbers were read from. When the document may not
   be redistributed, give its full citation (title, edition, section, example and page)
   instead, so a reviewer can find it.
3. **Reproduce it in [CalcPad](https://github.com/Proektsoftbg/Calcpad)**, with units,
   including the edge cases you expect the implementation to handle, and **include the
   CalcPad file with your pull request**, so a reviewer can follow the calculation
   independently of the Python code. The CalcPad sheet is the working reproduction; it
   does not replace the published reference in step 2.
4. **Reference the validation source in your test module** — the document, the section,
   the example number and the page, so the next person can trace where the expected
   numbers came from.
5. **Mark the test `@pytest.mark.published_example`** when its expected numbers come from
   that published source and not from mento — the release counts these tests for the
   home page of mento-web, so the mark is a public claim. A marked test says where the
   number is, in a docstring paragraph that starts with `Source:` (the page, table, example
   or section; for a workbook of program runs, the sheet and the row and column), and lives
   in `tests/validation/`; `tests/architecture/test_published_examples.py` checks both, and
   fails a `Source:` that names a CalcPad sheet. A test checked only against a CalcPad
   sheet, one that pins mento's own output, or a reading of the code the reference does
   not share, is not marked and goes with the rest.

If you cannot find a published example for what you are implementing, say so in the pull
request and we will work out an acceptable validation path together.

## Pull request checklist

- [ ] Tests added or updated, and the full suite passes locally
- [ ] `mypy mento/` passes
- [ ] `pre-commit run --all-files` reports no changes
- [ ] Calculations validated against a published example, with the PDF or pages (or the
      full citation) included, and reproduced in CalcPad with the file included
- [ ] Documentation updated (user guide, docstrings, and an example notebook if the feature
      is user facing)
- [ ] Public API naming left unchanged unless the change was agreed in advance

## Project structure

```
mento/
├── material.py     Concrete and steel material classes, per design code
├── section.py      Section base class
├── rectangular.py  RectangularSection — geometry and cover
├── beam.py         RectangularBeam — check, design and visualization
├── slab.py         OneWaySlab
├── shear_wall.py   ShearWall
├── punching.py     PunchingSlab — two-way punching shear
├── column.py       Column geometry used by the punching check
├── rebar.py        Bar database and rebar selection logic
├── forces.py       Forces with pint units
├── node.py         Node — binds a section to its forces, drives check/design
├── settings.py     BeamSettings — metric and imperial design defaults
├── results.py      Formatting, tables and Word report building
├── beam_summary.py        BeamSummary — results across many beams
├── slab_summary.py        OneWaySlabSummary — results across many one-way slab strips
├── shear_wall_summary.py  ShearWallSummary — results across many walls
├── summary_tables.py      The sections and forces tables the summaries read and write
├── summary_base.py        What the summaries share: one Node per section, frozen results
├── units.py        Shared pint unit registry
└── codes/          Design code implementations (ACI 318-19, EN 1992-2004)
```

Design code logic lives in `mento/codes/`. Element classes delegate to those modules rather
than embedding code clauses directly, which is what lets a new standard be added without
touching the element classes.

`Concrete` detects the unit system from the units of `f_c` — MPa means metric, psi means
imperial — and that choice propagates through settings, forces and results. Never hard-code
a unit assumption in new code.

## Making a release

For maintainers. **Merging a pull request does not publish anything** — it only updates
`main`. Publishing to PyPI is triggered by creating a GitHub Release, and nothing else.

1. On a branch, bump `version` in `pyproject.toml`, bump `version` and `date-released` in
   [CITATION.cff](CITATION.cff), and move the `Unreleased` entries of
   [CHANGELOG.md](CHANGELOG.md) under the new version number. Merge that branch.
2. On GitHub, go to Releases → *Draft a new release*, create the tag `vX.Y.Z` against
   `main` (the leading `v` matters), and publish it. "Generate release notes" gives a
   starting point worth editing down to what users care about.
3. Publishing the release starts [`publish.yml`](.github/workflows/publish.yml), which
   builds the sdist and wheel, checks the metadata, refuses to continue if the tag does not
   match the version in `pyproject.toml`, installs the wheel and imports it, and only then
   uploads to PyPI.

Authentication uses [PyPI trusted publishing](https://docs.pypi.org/trusted-publishers/),
so there is no API token in the repository. It has to be configured once, on PyPI under the
project's *Publishing* settings and as a GitHub environment named `pypi`; until that is
done, the workflow builds everything correctly and then fails on the upload step.

To rehearse the build without publishing, run the workflow manually from the Actions tab —
`workflow_dispatch` runs the build job but skips the tag check and the upload.

Publishing a release also sets two things in motion that are not PyPI: Zenodo archives the
release and mints a DOI, and conda-forge's bot proposes a feedstock update. Both are
described below.

## Archiving on Zenodo

A DOI is what lets someone cite a specific version of mento in a paper or a technical report,
and what makes the software findable outside GitHub. [Zenodo](https://zenodo.org/) mints one
automatically for every GitHub Release, at no cost.

**This is already set up and needs nothing per release.** The repository is enabled on
Zenodo, so publishing a GitHub Release fires a webhook, Zenodo archives the source at that
tag and issues the DOIs, and the record picks up its title, authors and licence from
[CITATION.cff](CITATION.cff) — which is why keeping that file current matters.

Zenodo issues **two** DOIs: a *version DOI* for that specific release, and a *concept DOI*
that always resolves to the latest version. mento's concept DOI is
[10.5281/zenodo.21956634](https://doi.org/10.5281/zenodo.21956634); it does not change, and
it is the one wired into `CITATION.cff` and the README badge. Only the concept DOI is
recorded in the repository: a version DOI is not known until the release is published, so
keeping one there would mean a chore after every release and a stale number whenever it is
forgotten. Per release, only `version` and `date-released` in `CITATION.cff` move, which the
release procedure above already covers.

To find the DOI of a release without opening Zenodo:

```bash
curl -sI https://zenodo.org/badge/latestdoi/699526716 | grep -i location
```

If a release ever fails to appear on Zenodo, check the webhook deliveries under the
repository's *Settings → Webhooks*. GitHub sends `created`, `released` and `published` for
the same release; Zenodo accepts the first with `202` and answers `409` to the other two,
which is deduplication and not an error.

## Publishing on conda-forge

Some engineering teams install everything through conda and cannot easily mix in pip.
[conda-forge](https://conda-forge.org/) is how mento reaches them. The recipe lives in
[`conda-recipe/`](conda-recipe/) so that it stays in step with `pyproject.toml`; conda-forge
itself builds from a separate repository called a *feedstock*.

**First submission** (once, to create the feedstock):

1. Fork [conda-forge/staged-recipes](https://github.com/conda-forge/staged-recipes).
2. Copy `conda-recipe/meta.yaml` and `conda-recipe/conda_build_config.yaml` into
   `recipes/mento/` on a branch of your fork.
3. Check that `version` and `sha256` in the recipe match the release you want packaged. The
   checksum of the sdist on PyPI is:

   ```bash
   curl -sL https://pypi.org/packages/source/m/mento/mento-0.5.0.tar.gz | sha256sum
   ```

4. Open a pull request against `staged-recipes`. A conda-forge reviewer will comment; expect
   a round or two on dependency names. When it merges, the bot creates
   `conda-forge/mento-feedstock` and lists you as maintainer.

**Every release after that** is mostly automatic: within a day of the sdist appearing on
PyPI, `regro-cf-autotick-bot` opens a pull request on the feedstock with the new version and
checksum. Review it — the bot updates the version but not the dependencies — and merge.

When mento's runtime dependencies change in `pyproject.toml`, update `conda-recipe/meta.yaml`
in the same pull request, so the copy here does not drift from what the feedstock needs.

## Tools we use

mento is built with, and grateful to:

- [GitHub Actions](https://github.com/features/actions) for continuous integration
- [pytest](https://docs.pytest.org/) and [Codecov](https://codecov.io/) for tests and coverage
- [ruff](https://github.com/astral-sh/ruff) for linting and formatting, [mypy](https://mypy-lang.org/) for type checking, and [pre-commit](https://pre-commit.com/) to enforce both
- [Sphinx](https://www.sphinx-doc.org/) and [Read the Docs](https://readthedocs.org/) for documentation
- [pint](https://pint.readthedocs.io/) for units
- [CalcPad](https://github.com/Proektsoftbg/Calcpad) for calculation validation
- [GitHub Discussions](https://github.com/mihdicaballero/mento/discussions) for community support
