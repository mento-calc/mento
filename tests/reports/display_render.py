"""Render everything mento shows for an element as one block of text.

The snapshot tests freeze that text for the metric codes, and the imperial
acceptance test searches it for units that should not be there. Both need the
same inventory -- DataFrames, detailed printouts, Word documents, the Markdown
views, the plot labels, warnings and the ``str`` of the public results -- so it
is collected here once.

Nothing here decides a unit: it only records what mento printed.
"""

from __future__ import annotations

import contextlib
import io
import os
import re
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List

import matplotlib.pyplot as plt
import pandas as pd
from docx import Document
from matplotlib.text import Text

from mento import Forces, Node, set_language
from mento.beam import RectangularBeam
from mento.shear_wall import ShearWall
from mento.shear_wall_summary import ShearWallSummary

SNAPSHOT_DIR = Path(__file__).parent / "snapshots"
LANGUAGES = ("en", "es")
# The Word footer names the installed version, which changes with every release
# and depends on which distribution Python finds first: not what a snapshot pins.
_VERSION = re.compile(r"mento [0-9]\S*?(?=\.?(\s|$))")
# pint writes a product of units with "·" (U+00B7) up to 0.25 and "⋅" (U+22C5)
# from 0.26 -- "kN·m" or "kN⋅m" for the same quantity. mento supports both
# (pint>=0.24), so a snapshot pins the unit, not pint's choice of dot.
_PINT_DOT = "⋅"


@contextlib.contextmanager
def _in_directory(path: Path) -> Iterator[None]:
    previous = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


@contextlib.contextmanager
def captured_markdown() -> Iterator[List[str]]:
    """Collect what the notebook views would display, instead of displaying it."""
    import mento.reports.views as views
    import mento.reports.walls as walls

    shown: List[str] = []
    originals = (views._show, walls._show)
    views._show = walls._show = shown.append  # type: ignore[assignment]
    try:
        yield shown
    finally:
        views._show, walls._show = originals  # type: ignore[assignment]


def docx_text(path: Path) -> str:
    """Paragraphs and table cells of a Word document, in document order."""
    document = Document(str(path))
    lines: List[str] = []
    body = document.element.body
    for child in body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            text = "".join(node.text or "" for node in child.iter() if node.tag.endswith("}t"))
            if text.strip():
                lines.append(text)
        elif tag == "tbl":
            for row in child.iter():
                if not row.tag.endswith("}tr"):
                    continue
                cells = []
                for cell in row.iter():
                    if cell.tag.endswith("}tc"):
                        cells.append("".join(n.text or "" for n in cell.iter() if n.tag.endswith("}t")))
                lines.append(" | ".join(cells))
    return "\n".join(lines)


def plot_text(figure: Any) -> str:
    texts = [t.get_text() for t in figure.findobj(Text) if t.get_text().strip()]
    plt.close(figure)
    return "\n".join(texts)


class Transcript:
    """Sections of rendered output, written as ``### title`` blocks."""

    def __init__(self, workdir: Path) -> None:
        self.workdir = workdir
        self.parts: List[str] = []
        self._docs_seen: set[str] = set()

    def add(self, title: str, text: Any) -> None:
        text = _VERSION.sub("mento <version>", str(text)).replace(_PINT_DOT, "·")
        self.parts.append(f"### {title}\n{text}\n")

    def printed(self, title: str, call: Callable[[], Any]) -> Any:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            result = call()
        self.add(title, buffer.getvalue())
        return result

    def frame(self, title: str, df: pd.DataFrame) -> None:
        self.add(title, df.to_string())

    def documents(self, title: str, call: Callable[[], Any]) -> None:
        """Run ``call`` in the work directory and record the Word files it writes."""
        with _in_directory(self.workdir), contextlib.redirect_stdout(io.StringIO()):
            call()
        for path in sorted(self.workdir.glob("*.docx")):
            if path.name in self._docs_seen:
                continue
            self._docs_seen.add(path.name)
            self.add(f"{title}: {path.name}", docx_text(path))

    def markdown(self, title: str, call: Callable[[], Any]) -> None:
        with captured_markdown() as shown:
            call()
        self.add(title, "\n".join(shown))

    def text(self) -> str:
        return "\n".join(self.parts)


def render_section(section: RectangularBeam, forces: List[Forces], workdir: Path, design: bool = True) -> str:
    """Everything a beam, slab or footing shows after a design (unless ``design`` is off) and a check."""
    t = Transcript(workdir)
    node = Node(section=section, forces=forces)
    if design:
        node.design()
    node.check()
    t.frame("check_flexure", node.check_flexure())
    t.frame("check_shear", node.check_shear())
    t.printed("flexure_results_detailed", node.flexure_results_detailed)
    t.printed("shear_results_detailed", node.shear_results_detailed)
    t.documents("flexure_results_detailed_doc", node.flexure_results_detailed_doc)
    t.documents("shear_results_detailed_doc", node.shear_results_detailed_doc)
    t.markdown("results", lambda: node.results)
    t.add(
        "flexure_design",
        "\n".join(str(layer) for face in ("top", "bottom") for layer in getattr(section.flexure_design, face).layers),
    )
    t.add("shear_design", str(section.shear_design))
    t.add("reinforcement.transverse", str(section.reinforcement.transverse))
    t.add("warnings", "\n".join(f"{w.code}: {w.message}" for w in node.warnings))
    t.add("plot", plot_text(section.plot()))
    return t.text()


def render_wall(wall: ShearWall, forces: List[Forces], workdir: Path) -> str:
    """Everything a shear wall shows after a design and a check."""
    t = Transcript(workdir)
    wall.design(forces)
    t.frame("check_shear", wall.check_shear(forces))
    t.printed("shear_results_detailed", wall.shear_results_detailed)
    t.documents("shear_results_detailed_doc", wall.shear_results_detailed_doc)
    t.markdown("results", lambda: wall.results)
    t.add("mesh", f"{wall.mesh.horizontal}\n{wall.mesh.vertical}")
    t.add("warnings", "\n".join(f"{w.code}: {w.message}" for w in wall.warnings))
    t.add("plot", plot_text(wall.plot()))
    return t.text()


def render_beam_summary(summary: Any, workdir: Path) -> str:
    """A beam or slab summary: the tables it reads, its check, its design and its report."""
    t = Transcript(workdir)
    t.frame("sections", summary.sections_table)
    t.frame("forces", summary.forces_table)
    t.frame("check", summary.check())
    t.frame("check capacity", summary.check(capacity_check=True))
    t.frame("design", summary.design())
    t.frame("flexure_results", summary.flexure_results())
    t.frame("shear_results", summary.shear_results())
    t.frame("flexure_results capacity", summary.flexure_results(capacity_check=True))
    t.frame("shear_results capacity", summary.shear_results(capacity_check=True))
    t.documents("results_detailed_doc", lambda: summary.results_detailed_doc(1))
    return t.text()


def render_wall_summary(summary: ShearWallSummary, workdir: Path) -> str:
    t = Transcript(workdir)
    t.frame("forces", summary.forces_table)
    t.frame("design", summary.design())
    t.frame("check", summary.check())
    t.frame("shear_results", summary.shear_results())
    t.documents("results_detailed_doc", lambda: summary.results_detailed_doc(1))
    return t.text()


def render_in_languages(render: Callable[[str], str]) -> Dict[str, str]:
    """``render(language)`` once per report language, restoring English after."""
    out = {}
    try:
        for language in LANGUAGES:
            set_language(language)
            out[language] = render(language)
    finally:
        set_language("en")
    return out
