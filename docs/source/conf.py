# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

import datetime
from importlib.metadata import version

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = "mento"
author = "Mehdí Caballero & Juan Pablo Romaris"

# The version info for the project you're documenting, acts as replacement for
# |version| and |release|, also used in various other places throughout the
# built documents.

try:  # pragma: no cover
    version = version(project)  # type: ignore
except Exception:  # pragma: no cover
    # we seem to have a local copy not installed without setuptools
    # so the reported version will be unknown
    version = "unknown"  # type: ignore

release = version
this_year = datetime.date.today().year
copyright = f"2025-{this_year}, mento Developers"

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration
# Add any Sphinx extension module names here, as strings. They can be extensions
# coming with Sphinx (named 'sphinx.ext.*') or your custom ones.
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.autosectionlabel",
    "sphinx.ext.doctest",
    "sphinx.ext.intersphinx",
    "sphinx.ext.coverage",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "nbsphinx",
    "sphinx_copybutton",
    "sphinx.ext.mathjax",
    "IPython.sphinxext.ipython_directive",
    "IPython.sphinxext.ipython_console_highlighting",
    "sphinx_design",
]

# Hide input and output prompts
nbsphinx_input_prompt = "%.0s"
nbsphinx_output_prompt = "%.0s"

master_doc = "index"

templates_path = ["_templates"]

source_suffix = {
    ".rst": "restructuredtext",
}

exclude_patterns = ["build"]

autodoc_inherit_docstrings = True

# Napoleon renders ``Attributes:`` and ``Methods:`` docstring sections as
# ``.. attribute::`` / ``.. method::`` directives by default. Those collide with the
# entries autodoc already emits for the same members via ``:members:``, which produced
# ~33 "duplicate object description" warnings in the API reference. The autodoc entry
# is the canonical one (it carries the signature and the source link), so the
# docstring summaries are rendered as plain prose instead:
#   - ``napoleon_use_ivar`` turns ``Attributes:`` into a ":ivar:" field list.
#   - listing "Methods" in ``napoleon_custom_sections`` overrides Napoleon's built-in
#     handler with the generic one, which emits a rubric plus a definition list.
napoleon_use_ivar = True
napoleon_custom_sections = ["Methods"]

# Section titles repeat across the user guide ("Usage", "Key Concepts", ...) and across
# the generated API pages ("Submodules"). Prefixing autosectionlabel targets with the
# document name keeps them unique. Every ``:ref:`` in the docs points at an explicit
# ``.. _label:`` target, so none of them are affected by this.
autosectionlabel_prefix_document = True

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "sphinx_book_theme"
html_static_path = ["_static"]
html_css_files = [
    "custom.css",  # Add a custom CSS file
]
html_logo = "_static/logo/mento_isotipo_transparente.png"
html_favicon = "_static/logo/mento_isotipo_transparente.png"
html_theme_options = {
    "repository_url": "https://github.com/mento-calc/mento",
    "repository_branch": "main",
    "use_repository_button": True,
    "use_issues_button": True,
}

# Output file base name for HTML help builder.
htmlhelp_basename = "mentodoc"
