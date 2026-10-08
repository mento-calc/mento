<img width="800" alt="mento_github" src="https://github.com/user-attachments/assets/32128ec0-a8c2-4782-b210-1afc633f0da6" />

*An intuitive tool for structural engineers to design concrete elements efficiently.*

[![Sponsor](https://img.shields.io/badge/Sponsor-%E2%9D%A4-ea4aaa?logo=githubsponsors)](https://ko-fi.com/mentoapp)
[![Tests](https://github.com/mento-calc/mento/actions/workflows/tests.yml/badge.svg)][tests]
[![Docs](https://readthedocs.org/projects/mento-docs/badge/?version=latest)](https://mento-docs.readthedocs.io/en/latest/?badge=latest)
[![codecov](https://codecov.io/gh/mento-calc/mento/graph/badge.svg?token=9X81ZRKMCX)](https://codecov.io/gh/mento-calc/mento)
[![PyPI](https://img.shields.io/pypi/v/mento.svg)](https://pypi.org/project/mento/)
[![Python versions](https://img.shields.io/pypi/pyversions/mento.svg)](https://pypi.org/project/mento/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/mento-calc/mento/blob/main/LICENSE)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.21956634.svg)](https://doi.org/10.5281/zenodo.21956634)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/charliermarsh/ruff/main/assets/badge/v2.json)][ruff]

[tests]: https://github.com/mento-calc/mento/actions/workflows/tests.yml
[ruff]: https://github.com/charliermarsh/ruff

mento designs and checks reinforced concrete members to **ACI 318-19**, **EN 1992-1-1:2004
(Eurocode 2)** and **CIRSOC 201-25**. Give it a section, its materials and a set of load
combinations; it returns the reinforcement, the demand-to-capacity ratio of every check, and a
calculation report you can hand to a reviewer.

mento is also, as far as we know, the only open source package that implements
**CIRSOC 201-25**, the Argentinian concrete design standard.

**Try it without installing anything:** [mentocalc.com](https://mentocalc.com) runs mento in
your browser, with calculators for beams, one-way slabs and shear walls that produce the same
Word report, in English or Spanish.

## Installation

```bash
pip install mento
```

Requires Python 3.12 or newer. To try it in [Google Colab](https://colab.research.google.com/),
run `!pip install mento` in the first cell.

## Quick start

Design a 20 × 50 cm beam for two load combinations:

```python
from mento import Concrete_ACI_318_19, SteelBar, RectangularBeam, Forces, Node
from mento import MPa, cm, mm, kN, kNm

concrete = Concrete_ACI_318_19(name="C25", f_c=25 * MPa)
steel = SteelBar(name="ADN 420", f_y=420 * MPa)
beam = RectangularBeam(
    label="B101", concrete=concrete, steel_bar=steel,
    width=20 * cm, height=50 * cm, c_c=25 * mm,
)

forces = [
    Forces(label="1.2D+1.6L", M_y=120 * kNm, V_z=100 * kN),
    Forces(label="1.4D", M_y=80 * kNm, V_z=70 * kN),
]
node = Node(section=beam, forces=forces)
node.design()

print(beam.reinforcement)
```

```text
bottom: 2Ø20 mm + 1Ø16 mm / top: no reinforcement / stirrups: 1sØ10 mm/22 cm
```

<img width="220" alt="Designed section of beam B101" src="https://raw.githubusercontent.com/mento-calc/mento/main/docs/source/_static/readme/beam_section.png" />

From there:

- `beam.plot()` draws the section above.
- `node.check_flexure()` and `node.check_shear()` return one row per combination as a pandas
  DataFrame, with the required and provided steel, the capacity and the DCR.
- `node.results` shows the formatted results in a Jupyter notebook.
- `node.flexure_results_detailed_doc()` and `node.shear_results_detailed_doc()` write the
  step-by-step calculation report to Word.
- To check reinforcement you already have instead of designing it, set the bars on the beam
  and call `node.check()`.

The [examples](https://mento-docs.readthedocs.io/en/latest/examples/index.html) walk through
each element and design code as a notebook, including US customary units.

## What mento covers

| Element                                   | ACI 318-19  | CIRSOC 201-25 | EN 1992-1-1:2004 |
| ----------------------------------------- | :---------: | :-----------: | :--------------: |
| Rectangular beam, flexure and shear       |      ✅      |       ✅       |        ✅         |
| One-way slab, flexure and shear           |      ✅      |       ✅       |        ✅         |
| Footing section, flexure and shear        |      ✅      |       ✅       |        ✅         |
| Shear wall, in-plane shear                |      ✅      |       ✅       |        ✅         |
| Slab punching shear                       | in progress |  in progress  |   in progress    |

Across all of them:

- **Units throughout.** Every input carries its unit. Metric and US customary are both
  supported, and a section entered in US customary units is reported in them.
- **Design gives you options.** Besides the arrangement it applies, a design keeps the next
  best alternatives for bars and stirrups, and warns about the detailing limits a section misses.
- **Many members at once.** `BeamSummary` and `ShearWallSummary` design or check a whole
  schedule, and export the designed reinforcement to Excel and back.
- **Reports.** Results come as Markdown in Jupyter, as pandas DataFrames, and as Word documents.

## Validated against published examples

The 58 tests in
[`tests/validation`](https://github.com/mento-calc/mento/tree/main/tests/validation)
reproduce cases worked out outside mento: the CRSI *Design Guide on the ACI 318 Building
Code*, CSI's software verification examples, ETABS runs, The Concrete Centre's Eurocode 2
guide and eurocodeapplied.com. Each test names the example and the page its numbers come from.

The [theory pages](https://mento-docs.readthedocs.io/en/latest/theory/index.html) set out the
equations behind each check, with the clause of the design code they come from.

## Documentation

The full documentation is at [mento-docs.readthedocs.io](https://mento-docs.readthedocs.io/):

- [Getting started](https://mento-docs.readthedocs.io/en/latest/getting_started/index.html)
- [Examples](https://mento-docs.readthedocs.io/en/latest/examples/index.html)
- [Theory](https://mento-docs.readthedocs.io/en/latest/theory/index.html)

## Roadmap

- [x] Rectangular concrete beam section check and design for ACI 318-19 and CIRSOC 201-25.
- [x] Rectangular concrete beam section check and design for EN 1992-2004.
- [x] One way concrete slab and footing check and design for ACI 318-19 and CIRSOC 201-25.
- [x] One way concrete slab and footing check and design for EN 1992-2004.
- [x] Shear wall shear check and design for ACI 318-19 and CIRSOC 201-25.
- [x] Shear wall shear check and design for EN 1992-2004.
- [x] US customary units in, US customary units out.
- [ ] Slab shear punching check and design for ACI 318-19 and CIRSOC 201-25. (in progress)
- [ ] Slab shear punching check and design for EN 1992-2004. (in progress)
- [ ] Shear wall flexure check for ACI 318-19.
- [ ] Column check for ACI 318-19.

## Support mento

mento is built and maintained in the time left over from consulting work. If it saves you a
spreadsheet or a few hours, consider sponsoring its development:

- [Ko-fi](https://ko-fi.com/mentoapp) — one-off support, no account needed.

Sponsorship funds the roadmap above: punching shear, columns, and full EN 1992 coverage.
Sponsors are listed in this README, and Partner sponsors get their logo on
[mentocalc.com](https://mentocalc.com).

<!-- Sponsors: list Partner logos and Supporter names here once there are any. -->

Not looking to sponsor? A ⭐ on the repo or feedback in
[Discussions](https://github.com/mento-calc/mento/discussions) is also genuinely appreciated.

## Using mento at your company?

mento is free and open-source under MIT. If your team wants help going further, we offer a few things on top:

- **Team onboarding** — short remote sessions to get your engineers productive with Python, Jupyter, VS Code and Git, using mento as the starting point.
- **Custom tools** — building specific workflows on top of mento (custom reports, integrations with Revit / ETABS / Robot, batch design tools, internal company libraries).
- **Sponsored features** — if your firm needs a specific element type, design code, or check that's on the roadmap (or not), we can scope it as paid work and contribute it back.

If any of that is useful for your team, fill out [this form](https://forms.gle/QoDzczQToLa78jMo7) and we'll follow up.

## Contributing

We welcome contributions from the community to expand and enhance the package. Start with the
[contributing guide](https://github.com/mento-calc/mento/blob/main/CONTRIBUTING.md), then
look through the [open issues](https://github.com/mento-calc/mento/issues) — those labelled
`good first issue` are a good entry point. A new calculation needs a published worked example
to validate it against; the guide explains how.

Participation in this project is governed by our
[Code of Conduct](https://github.com/mento-calc/mento/blob/main/CODE_OF_CONDUCT.md).

## Disclaimer

mento is a tool to assist structural engineers, not a replacement for engineering judgement. Results must be reviewed and accepted by a qualified engineer who takes responsibility for the design. The software is provided "as is", without warranty of any kind, and the authors accept no liability for its use. Verify the output against the applicable design code before relying on it for any real structure.

## Citing mento

If mento supports your research or professional work, cite it with the DOI
[10.5281/zenodo.21956634](https://doi.org/10.5281/zenodo.21956634), which always resolves to the
latest release. Citation metadata is in
[CITATION.cff](https://github.com/mento-calc/mento/blob/main/CITATION.cff), and GitHub's
"Cite this repository" button will format it for you. The
[citing guide](https://mento-docs.readthedocs.io/en/latest/getting_started/citing.html) explains
which version to cite and gives a BibTeX entry.

## License

This project is licensed under the MIT License. See
[LICENSE](https://github.com/mento-calc/mento/blob/main/LICENSE) for the full text.
