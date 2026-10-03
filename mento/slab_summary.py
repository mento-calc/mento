"""A list of one-way slab strips read from two tables: the sections, and the forces each one carries."""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Tuple

from mento.bar_sizes import bar_designation
from mento.design_results import spacing_separator
from mento.i18n import translate
from mento.node import Node
from mento.reports.summaries import SLAB_REPORT
from mento.slab import OneWaySlab
from mento.summary_base import Key, _FlexuralSummary
from mento.summary_tables import (
    SummaryInputError,
    SummaryInputWarning,
    TableSpec,
    _listed,
    forces_columns,
    key_text,
    length,
    text,
    unit_of,
)
from mento.units import Quantity, cm, mm

FACES = ("top", "bot")
#: The two layers of a face: position 1, nearest the face, and position 3, a second layer inside it.
LAYERS = (1, 3)


def _face_columns(face: str) -> tuple:
    return tuple(
        column
        for layer in LAYERS
        for column in (length(f"db{layer}_{face}", "mm", "in"), length(f"s{layer}_{face}", "cm", "in"))
    )


SLAB_SPEC = TableSpec(
    kind="slab",
    element="OneWaySlabSummary",
    sections=(
        text("Level"),
        text("Label", required=True),
        length("b", "cm", "in", dimension=True),
        length("h", "cm", "in", dimension=True),
        length("cc", "mm", "in", dimension=True),
        *_face_columns("top"),
        *_face_columns("bot"),
        text("Notes"),
    ),
    forces=forces_columns(),
)


def _layers_label(layers: Any, imperial: bool) -> str:
    """The layers of a face as the summary writes them: ``Ø12/15`` (mm/cm), ``#4@8`` (in)."""
    texts = []
    for layer in layers:
        if imperial:
            texts.append(f"{bar_designation(layer.d_b)}{spacing_separator(True)}{layer.s.to('inch').magnitude:.4g}")
        else:
            texts.append(f"Ø{layer.d_b.to('mm').magnitude:.0f}/{layer.s.to('cm').magnitude:.4g}")
    return " ++ ".join(texts) or "-"


def _given(value: Optional[Quantity]) -> bool:
    return value is not None and value.magnitude > 0


class OneWaySlabSummary(_FlexuralSummary):
    """Check and design a list of one-way slab strips, read from a sections table and a forces table.

    ``sections`` has one row per strip, each face a diameter and a spacing per layer:

    ``Level, Label, b, h, cc, db1_top, s1_top, db3_top, s3_top, db1_bot, s1_bot, db3_bot, s3_bot, Notes``

    ``b`` is the width of the strip (100 cm for a metre of slab). ``db1/s1``
    is the layer nearest the face and ``db3/s3`` a second layer inside it --
    position 3 of :meth:`~mento.slab.OneWaySlab.set_slab_longitudinal_rebar_bot`,
    at a smaller effective depth, not bars laid between those of the first.
    A strip is detailed without stirrups, so the table has no stirrup columns.

    ``forces`` is the forces table of
    :class:`~mento.beam_summary.BeamSummary`. The forces are those of the strip
    of width ``b``: for ``b = 100 cm``, the forces per metre of slab.

    ``design()`` is ``Node.design()``. A strip it would give stirrups keeps
    the layers it designed, without the stirrups, and is named: ``check()``
    fails it with ``stirrups_required``.
    """

    _SPEC = SLAB_SPEC
    _ELEMENT_COLUMN = "Slab"
    _REPORT = SLAB_REPORT
    _HAS_STIRRUPS = False

    _SECTION_TYPE = OneWaySlab

    def _not_representable(self, key: Key, section: Any) -> Optional[str]:
        reason = super()._not_representable(key, section)
        if reason is None and section._stirrup_n > 0:
            reason = "stirrups, which a slab of the table does not carry"
        return reason

    def _validate_section_row(self, key: Key, row: Mapping[str, Any]) -> None:
        for face in FACES:
            placed = {}
            for layer in LAYERS:
                d_b, s = f"db{layer}_{face}", f"s{layer}_{face}"
                has_d, has_s = _given(row.get(d_b)), _given(row.get(s))
                if has_d != has_s:
                    given, missing = (d_b, s) if has_d else (s, d_b)
                    raise SummaryInputError("incomplete_group", label=repr(key_text(key)), given=given, missing=missing)
                placed[layer] = has_d
            if placed[3] and not placed[1]:
                raise SummaryInputError(
                    "incomplete_group", label=repr(key_text(key)), given=f"db3_{face}", missing=f"db1_{face}"
                )

    def _section(self, key: Key, row: Mapping[str, Any]) -> OneWaySlab:
        slab = OneWaySlab(
            label=key[1],
            concrete=self.concrete,
            steel_bar=self.steel_bar,
            width=row["b"],
            height=row["h"],
            c_c=row["cc"],
        )
        for face, setter in (
            ("top", slab.set_slab_longitudinal_rebar_top),
            ("bot", slab.set_slab_longitudinal_rebar_bot),
        ):
            if _given(row.get(f"db1_{face}")):
                setter(
                    d_b1=row[f"db1_{face}"],
                    s_b1=row[f"s1_{face}"],
                    d_b3=row[f"db3_{face}"] if _given(row.get(f"db3_{face}")) else 0 * mm,
                    s_b3=row[f"s3_{face}"] if _given(row.get(f"s3_{face}")) else 0 * mm,
                )
        return slab

    def _section_row(self, section: OneWaySlab) -> Dict[str, Any]:
        zero = 0 * unit_of("in" if self.concrete.is_imperial else "mm")
        row: Dict[str, Any] = {"b": section.width, "h": section.height, "cc": section.c_c}
        placed = section.reinforcement
        for face, reinforcement in (("top", placed.top), ("bot", placed.bottom)):
            layers = list(reinforcement.layers) + [None, None]
            for layer, position in zip(layers, LAYERS):
                row[f"db{position}_{face}"] = layer.d_b if layer is not None else zero
                row[f"s{position}_{face}"] = layer.s if layer is not None else zero
        return row

    def _rebar_labels(self, section: OneWaySlab) -> Tuple[str, str, str]:
        imperial = section.concrete.is_imperial
        placed = section.reinforcement
        return _layers_label(placed.top.layers, imperial), _layers_label(placed.bottom.layers, imperial), "-"

    def _design(self, key: Key, node: Node) -> Node:
        """``node.design()``; a strip it gives stirrups keeps its layers without them, and is named.

        ``Node.design()`` raises the longitudinal steel where that lifts the
        concrete's shear strength enough to do without stirrups (ρw in ACI
        318-19 Table 22.5.5.1(c), ρl in EN 1992-1-1 Eq. 6.2a): an ACI 100x15
        strip under 20 kN·m and 50 kN takes Ø10/14 and passes its shear on the
        concrete alone. Under 55 kN it adds stirrups, which a strip of this
        table does not carry: the layers stay, the stirrups go, and
        ``check()`` reports DCRv 1.078 with ``stirrups_required``. A slab
        starts a design with no stirrup, so taking them off moves no bar.
        """
        node.design()
        slab: OneWaySlab = node.section  # type: ignore[assignment]
        if slab._stirrup_n > 0:
            slab.set_slab_transverse_rebar(0 * mm, 0 * cm, 0 * cm)
            self._designed_short.append(key_text(key))
        return node

    def _report_design(self) -> None:
        if not self._designed_short:
            super()._report_design()
            return
        warning = SummaryInputWarning("shear_reinforcement_required", labels=_listed(self._designed_short))
        self._warn(warning)
        print(f"⚠ {translate('Slabs designed.')} {warning.message}")
