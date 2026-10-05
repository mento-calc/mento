.. _getting_started/citing:

Citing mento
============

If mento supported a paper, a thesis, a technical note or a design report, please cite it.
Citations are what make an open source engineering tool visible to the people deciding
whether to trust it, and they are the main way this project gets credit for the work.

Which version to cite
---------------------

Always cite the version you actually ran. mento reports it:

.. code-block:: python

   import mento

   print(mento.__version__)

Calculations change between versions — a corrected clause or a new code edition can move a
result — so the version is part of the reproducibility of whatever you report.

DOI
---

Every release is archived on `Zenodo <https://zenodo.org/>`_, which issues a DOI for it. Cite

.. code-block:: text

   10.5281/zenodo.21956634

which always resolves to the most recent release. Each release also has a DOI of its own,
shown on its `Zenodo record <https://doi.org/10.5281/zenodo.21956634>`_, and that is the
better one to cite when the exact version matters — which, for a tool that produces
calculations, it usually does.

Citation metadata
-----------------

The authoritative metadata lives in `CITATION.cff
<https://github.com/mento-calc/mento/blob/main/CITATION.cff>`_ at the root of the
repository. On GitHub, the **Cite this repository** button in the sidebar renders it as APA
or BibTeX for you, so you rarely need to write the entry by hand.

BibTeX
------

.. code-block:: bibtex

   @software{mento,
     author    = {Caballero, Mehdí and Romaris, Juan Pablo},
     title     = {mento: an intuitive tool for structural engineers to design concrete
                  elements efficiently},
     version   = {0.5.1},
     year      = {2026},
     doi       = {10.5281/zenodo.21956634},
     publisher = {Zenodo},
     url       = {https://doi.org/10.5281/zenodo.21956634}
   }

Replace ``version`` and ``year`` with the release you used, and swap the concept DOI for that
release's own DOI if you want the citation to point at one specific version.

Citing a design code
--------------------

mento implements published standards; it does not replace them. When your work depends on a
particular clause, cite the standard itself — ACI 318-19, EN 1992-2004 or CIRSOC 201-2025 —
alongside mento, which is the implementation you used to apply it.
