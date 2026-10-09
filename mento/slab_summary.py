"""A list of one-way slabs read from a table: the workflow of :class:`~mento.beam_summary.BeamSummary`."""

from typing import Any, Dict

import pandas as pd
from pandas import DataFrame

from mento.bar_sizes import bar_designation
from mento.beam_summary import BeamSummary
from mento.design_results import spacing_separator
from mento.material import Concrete, SteelBar
from mento.node import Node
from mento.reports.summaries import SLAB_REPORT
from mento.slab import OneWaySlab

#: The two layers of a face: position 1 and the optional second layer, position 3.
_SLAB_FACE_COLUMNS = ("db1", "s1", "db3", "s3")


def _layers_label(layers: Any, imperial: bool) -> str:
    """The layers of a face as the summary writes them: ``Ø12/15`` (mm/cm), ``#4@8`` (in)."""
    texts = []
    for layer in layers:
        if imperial:
            texts.append(f"{bar_designation(layer.d_b)}{spacing_separator(True)}{layer.s.to('inch').magnitude:.4g}")
        else:
            texts.append(f"Ø{layer.d_b.to('mm').magnitude:.0f}/{layer.s.to('cm').magnitude:.4g}")
    return " ++ ".join(texts) or "-"


class OneWaySlabSummary(BeamSummary):
    """Check and design a list of one-way slabs read from a table, one row per load combination.

    The table is the one :class:`~mento.beam_summary.BeamSummary` reads, with
    each face given as a bar diameter and a spacing per layer, the way a slab
    is detailed, and no stirrups:

    ``Label, Comb., b, h, cc, Nx, Vz, My, db1, s1, db3, s3``

    ``b`` is the width of the strip (100 cm for a metre of slab), ``db1``/``s1``
    the first layer of the face the row's moment puts in tension and
    ``db3``/``s3`` an optional second one. Rows that share a ``Label`` are one
    slab under several combinations, designed and checked for their envelope;
    see :meth:`~mento.beam_summary.BeamSummary.convert_to_nodes`.

    ``design()`` designs the flexural reinforcement only. A one-way slab is
    detailed without stirrups, so its shear is checked against the concrete
    alone, and a slab that needs more is one that needs to be thicker.
    """

    _ELEMENT_COLUMN = "Slab"
    _FACE_COLUMNS = _SLAB_FACE_COLUMNS
    _TRANSVERSE_COLUMNS = ()
    _REPORT = SLAB_REPORT

    def __init__(self, concrete: Concrete, steel_bar: SteelBar, slab_list: DataFrame) -> None:
        super().__init__(concrete, steel_bar, slab_list)

    @property
    def slab_list(self) -> DataFrame:
        """The table the summary was built from, its unit row first."""
        return self.beam_list

    def _new_section(self, row: pd.Series) -> OneWaySlab:
        return OneWaySlab(
            label=row["Label"],
            concrete=self.concrete,
            steel_bar=self.steel_bar,
            width=row["b"],
            height=row["h"],
            c_c=row["cc"],
        )

    def _set_face(self, section: Any, face: str, values: tuple) -> None:
        d_b1, s_b1, d_b3, s_b3 = values
        for d_b, s, layer in ((d_b1, s_b1, 1), (d_b3, s_b3, 3)):
            if (d_b.magnitude == 0) != (s.magnitude == 0):
                raise ValueError(
                    f"Slab {section.label!r}: the {face} layer {layer} needs both a diameter and a spacing."
                )
        setter = (
            section.set_slab_longitudinal_rebar_bot if face == "bottom" else section.set_slab_longitudinal_rebar_top
        )
        setter(d_b1=d_b1, s_b1=s_b1, d_b3=d_b3, s_b3=s_b3)

    def _designed(self, node: Node) -> tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
        """Design the slab's flexure for its combinations; each face as its input columns."""
        node.design()
        section: Any = node.section
        # A strip remains without stirrups, even if the shared beam design
        # proposed them. Keep its flexural layers and verify the actual strip.
        with section._design_in_progress():
            section.set_slab_transverse_rebar()
        node.check()
        return self._current_faces(section), {}

    def _current_faces(self, section: Any) -> Dict[str, Dict[str, Any]]:
        return {
            face: {
                column: getattr(section, f"_d_b{column[2:]}_{suffix}")
                if column.startswith("db")
                else getattr(section, f"_s_b{column[1:]}_{suffix}")
                for column in self._FACE_COLUMNS
            }
            for face, suffix in (("bottom", "b"), ("top", "t"))
        }

    def _report_labels(self, section: Any) -> tuple[str, str, str]:
        return self._rebar_labels(section)

    def _rebar_labels(self, section: Any) -> tuple[str, str, str]:
        imperial = section.concrete.is_imperial
        placed = section.reinforcement
        return _layers_label(placed.top.layers, imperial), _layers_label(placed.bottom.layers, imperial), "-"

    def design(self) -> DataFrame:
        """Design the flexural reinforcement of every slab for the envelope of its combinations.

        Fills in ``db1``, ``s1``, ``db3`` and ``s3``: every row of a slab gets
        the layers of the face its moment puts in tension. No stirrups are
        designed; ``check()`` reports the shear against the concrete alone.
        """
        return super().design()

    def results_detailed_doc(self, index: int = 1) -> None:
        """Export detailed results for one slab, plus summary tables for all, to Word.

        Saved as ``Slab_Summary_{design_code}.docx`` in the current directory.
        """
        super().results_detailed_doc(index)
