"""A list of one-way slabs read from a table: the workflow of :class:`~mento.beam_summary.BeamSummary`."""

from typing import Any, Dict, List, Optional

import pandas as pd
from pandas import DataFrame

from mento.bar_sizes import bar_designation
from mento.beam_summary import BeamSummary
from mento.design_results import spacing_separator
from mento.material import Concrete, SteelBar
from mento.node import Node
from mento.reports.summaries import SLAB_REPORT
from mento.slab import OneWaySlab
from mento.units import cm, mm

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
        """Design the slab for its combinations; each face as its input columns.

        :meth:`Node.design`, the way a slab built by hand is designed: it
        raises the longitudinal steel where that lifts the concrete's shear
        strength enough to do without stirrups (ρw in ACI 318-19 Table
        22.5.5.1(c), ρl in EN 1992-1-1 Eq. 6.2a). An ACI 100x15 strip under
        20 kN·m and 50 kN takes Ø10/14 and passes its shear on the concrete
        alone, where designing the flexure on its own gave Ø12/25 and DCRv
        1.058. Where even that is not enough, ``Node.design()`` adds stirrups,
        which a slab of this table does not carry: its layers are kept, the
        stirrups dropped and the slab named, and ``check()`` fails it with
        ``stirrups_required``.
        """
        slab: OneWaySlab = node.section  # type: ignore[assignment]
        node.design()
        if slab._stirrup_n > 0:
            slab.set_slab_transverse_rebar(0 * mm, 0 * cm, 0 * cm)
            self._needs_shear_reinforcement.append(str(slab.label))
        placed = slab.reinforcement

        def columns(layers: Any) -> Dict[str, Any]:
            out: Dict[str, Any] = {column: 0 for column in _SLAB_FACE_COLUMNS}
            for (d_column, s_column), layer in zip((("db1", "s1"), ("db3", "s3")), layers):
                out[d_column], out[s_column] = layer.d_b, layer.s
            return out

        return {"bottom": columns(placed.bottom.layers), "top": columns(placed.top.layers)}, {}

    def _rebar_labels(self, section: Any) -> tuple[str, str, str]:
        imperial = section.concrete.is_imperial
        placed = section.reinforcement
        return _layers_label(placed.top.layers, imperial), _layers_label(placed.bottom.layers, imperial), "-"

    def design(self) -> DataFrame:
        """Design every slab for the envelope of its combinations, as ``Node.design()`` does.

        Fills in ``db1``, ``s1``, ``db3`` and ``s3``: every row of a slab gets
        the layers of the face its moment puts in tension. No stirrups are
        kept; a slab whose shear the concrete cannot carry with the layers
        designed is named instead of reported as completed (see
        :meth:`_designed`), and ``check()`` reports it as failing.
        """
        self._needs_shear_reinforcement: List[str] = []
        designed = super().design()
        if self._needs_shear_reinforcement:
            print(
                f"⚠ Slabs designed. {', '.join(self._needs_shear_reinforcement)}: Vu > φVc with the bars designed; "
                "more longitudinal steel, more thickness, a higher f'c, or shear reinforcement detailed as a "
                "beam (ACI 318-19 §7.6.3). check() gives them as failing."
            )
        return designed

    def _design_completed_message(self) -> Optional[str]:
        """No "completed" when a slab was left needing shear reinforcement: :meth:`design` names it."""
        return None if self._needs_shear_reinforcement else super()._design_completed_message()

    def results_detailed_doc(self, index: int = 1) -> None:
        """Export detailed results for one slab, plus summary tables for all, to Word.

        Saved as ``Slab_Summary_{design_code}.docx`` in the current directory.
        """
        super().results_detailed_doc(index)
