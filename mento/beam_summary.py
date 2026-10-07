"""A list of beams read from two tables: the sections, and the forces each one carries.

The sections table has one row per beam section -- its geometry, its stirrups
and the bars of both faces -- and the forces table one row per load
combination, naming the section by its ``Label``. See :class:`BeamSummary`,
and :mod:`mento.summary_base` for the workflow every summary shares.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Tuple

from mento.bar_sizes import bar_designation
from mento.beam import RectangularBeam
from mento.design_results import spacing_separator
from mento.i18n import stirrup_mark
from mento.material import Concrete_ACI_318_19
from mento.precompute import shown
from mento.reports.summaries import BEAM_REPORT
from mento.summary_base import Key, _FlexuralSummary, section_dimension, translated
from mento.summary_tables import (
    SummaryInputError,
    TableColumn,
    TableSpec,
    count,
    forces_columns,
    key_text,
    length,
    text,
    unit_of,
)
from mento.units import Quantity

# Where the summaries of 1.4.0 kept them.
_section_dimension = section_dimension
_translated = translated

#: The bar groups of a face: 1 and 2 make the layer nearest it, 3 and 4 the layer inside.
GROUPS = (1, 2, 3, 4)
FACES = ("top", "bot")


def _face_columns(face: str) -> Tuple[TableColumn, ...]:
    columns: Tuple[TableColumn, ...] = ()
    for group in GROUPS:
        columns += (count(f"n{group}_{face}"), length(f"db{group}_{face}", "mm", "in"))
    return columns


BEAM_SPEC = TableSpec(
    kind="beam",
    element="BeamSummary",
    sections=(
        text("Level"),
        text("Label", required=True),
        length("b", "cm", "in", dimension=True),
        length("h", "cm", "in", dimension=True),
        length("cc", "mm", "in", dimension=True),
        count("legs"),
        length("dbs", "mm", "in"),
        length("sl", "cm", "in"),
        *_face_columns("top"),
        *_face_columns("bot"),
        text("Notes"),
    ),
    forces=forces_columns(),
)


def _stirrups_label(beam: RectangularBeam) -> str:
    """The stirrups of a beam as the summary writes them: ``1eØ8/15`` (mm/cm), ``1s#3@6`` (in).

    A whole number of centimetres in SI, as the table has always shown them; in
    inches up to four significant figures, since truncating 5.5 in to 5 would
    write a spacing nobody placed.
    """
    if beam._stirrup_n == 0:
        return "-"
    imperial = beam.concrete.is_imperial
    spacing = shown(beam._stirrup_s_l, "length", imperial)
    if imperial:
        bar, spacing_text = bar_designation(beam._stirrup_d_b), f"{spacing:.4g}"
    else:
        bar, spacing_text = f"Ø{int(beam._stirrup_d_b.to('mm').magnitude)}", f"{int(spacing)}"
    return f"{int(beam._stirrup_n)}{stirrup_mark()}{bar}{spacing_separator(imperial)}{spacing_text}"


def _given(value: Optional[Quantity]) -> bool:
    return value is not None and value.magnitude > 0


def _incomplete(key: Key, given: str, missing: str) -> SummaryInputError:
    return SummaryInputError("incomplete_group", label=repr(key_text(key)), given=given, missing=missing)


class BeamSummary(_FlexuralSummary):
    """Check and design a list of beam sections, read from a sections table and a forces table.

    ``sections`` has one row per section, with a unique ``Label`` (``Level``
    is optional and, where given, part of the key):

    ``Level, Label, b, h, cc, legs, dbs, sl, n1_top, db1_top ... n4_top, db4_top, n1_bot ... n4_bot, db4_bot, Notes``

    ``legs`` is the number of stirrup legs, two per closed stirrup (an odd
    number is an error: mento models closed stirrups, not single ties),
    ``dbs`` their diameter and ``sl`` their spacing. The bars of a face are four groups:
    ``n1/db1`` and ``n2/db2`` make the layer nearest the face, ``n3/db3`` and
    ``n4/db4`` a second layer inside it, as
    :meth:`~mento.beam.RectangularBeam.set_longitudinal_rebar_bot` takes them.
    Zero bars is no bars. ``legs = 0`` leaves the beam without stirrups, with
    the starter stirrup of its settings in its effective depth, as a
    ``RectangularBeam`` built by hand. The reinforcement columns may be left
    out, to design from the geometry alone.

    ``forces`` has one row per load combination, ``Level, Label, Comb., Nx,
    Vz, My, Notes``: the section it acts on, the combination's name and its
    forces (``Nx > 0`` compression, which enters the shear only; ``My > 0``
    puts the bottom face in tension). A section with several rows here is one
    section under all of them, checked and designed for their envelope; a
    support and a midspan with different bars are two sections, with two
    labels.

    Each table carries its units in its first row. :meth:`from_excel` reads
    the sheets ``Sections`` and ``Forces``, :meth:`to_excel` writes them, and
    :meth:`from_nodes` writes nodes built by hand.
    """

    _SPEC = BEAM_SPEC
    _ELEMENT_COLUMN = "Beam"
    _REPORT = BEAM_REPORT

    _SECTION_TYPE = RectangularBeam

    def _not_representable(self, key: Key, section: Any) -> Optional[str]:
        reason = super()._not_representable(key, section)
        if (
            reason is None
            and section._stirrup_n == 0
            and section._stirrup_d_b != getattr(section.settings, "stirrup_diameter_ini", None)
        ):
            reason = "a stirrup diameter without stirrups, which a row with legs = 0 does not hold"
        return reason

    def _validate_section_row(self, key: Key, row: Mapping[str, Any]) -> None:
        legs, has_dbs, has_sl = row.get("legs", 0), _given(row.get("dbs")), _given(row.get("sl"))
        if legs % 2:
            raise SummaryInputError("odd_legs", label=repr(key_text(key)), value=legs)
        if legs > 0 and not (has_dbs and has_sl):
            raise _incomplete(key, "legs", " and ".join(n for n, ok in (("dbs", has_dbs), ("sl", has_sl)) if not ok))
        if legs == 0 and (has_dbs or has_sl):
            raise _incomplete(key, " and ".join(n for n, ok in (("dbs", has_dbs), ("sl", has_sl)) if ok), "legs")
        for face in FACES:
            placed = {}
            for group in GROUPS:
                n, has_d = row.get(f"n{group}_{face}", 0), _given(row.get(f"db{group}_{face}"))
                if n > 0 and not has_d:
                    raise _incomplete(key, f"n{group}_{face}", f"db{group}_{face}")
                if n == 0 and has_d:
                    raise _incomplete(key, f"db{group}_{face}", f"n{group}_{face}")
                placed[group] = n > 0
            # A second diameter group needs the first group of the same layer.
            # A second layer may exist on its own, retaining its physical position.
            for group, needs in ((2, 1), (4, 3)):
                if placed[group] and not placed[needs]:
                    raise _incomplete(key, f"n{group}_{face}", f"n{needs}_{face}")

    def _section(self, key: Key, row: Mapping[str, Any]) -> RectangularBeam:
        beam = RectangularBeam(
            label=key[1],
            concrete=self.concrete,
            steel_bar=self.steel_bar,
            width=row["b"],
            height=row["h"],
            c_c=row["cc"],
        )
        if row.get("legs", 0) > 0:
            beam.set_transverse_rebar(n_stirrups=int(row["legs"]) // 2, d_b=row["dbs"], s_l=row["sl"])
        zero = 0 * unit_of("in" if self.concrete.is_imperial else "mm")
        for face, setter in (("top", beam.set_longitudinal_rebar_top), ("bot", beam.set_longitudinal_rebar_bot)):
            values: list[Any] = []
            for group in GROUPS:
                n = int(row.get(f"n{group}_{face}", 0))
                values += [n, row[f"db{group}_{face}"] if n > 0 else zero]
            setter(*values)
        return beam

    def _section_row(self, section: RectangularBeam) -> Dict[str, Any]:
        zero = 0 * unit_of("in" if self.concrete.is_imperial else "mm")
        row: Dict[str, Any] = {"b": section.width, "h": section.height, "cc": section.c_c}
        if section._stirrup_n > 0:
            row.update({"legs": 2 * int(section._stirrup_n), "dbs": section._stirrup_d_b, "sl": section._stirrup_s_l})
        else:
            row.update({"legs": 0, "dbs": zero, "sl": zero})
        for face in FACES:
            for group, (n, d_b) in zip(GROUPS, section._bar_groups(face)):
                bars = int(round(n))
                row[f"n{group}_{face}"] = bars
                row[f"db{group}_{face}"] = d_b if bars > 0 else zero
        return row

    def _rebar_labels(self, section: RectangularBeam) -> Tuple[str, str, str]:
        """The top bars, the bottom bars and the stirrups, as ``check()`` writes them."""

        def face(name: str) -> str:
            groups = section._bar_groups(name)
            (n1, d1), (n2, d2), (n3, d3), (n4, d4) = ((int(round(n)), d_b) for n, d_b in groups)
            if n1 == 0:
                return "-"
            out = section._format_longitudinal_rebar_string(n1, d1, n2, d2)
            if n3 != 0:
                out += f" ++ {section._format_longitudinal_rebar_string(n3, d3, n4, d4)}"
            return out

        return face("top"), face("bot"), _stirrups_label(section)

    def _axial_limit(self, section: RectangularBeam) -> Optional[Quantity]:
        """0.10 f'c Ag under ACI 318-19 and CIRSOC 201-25, the compression from which a beam is not checked in bending alone.

        §9.5.2.1 computes φMn per §22.3 for Pu < 0.10 f'c Ag and §9.5.2.2 per
        §22.4, with the axial load, from there on (Pu positive in
        compression); §9.3.3.1 holds to tension-controlled only the beams
        below it. mento checks a beam's flexure without N. EN 1992-1-1 states
        no such limit for a beam: no warning there.
        """
        if not isinstance(section.concrete, Concrete_ACI_318_19):
            return None
        return (0.10 * section.concrete.f_c * section.width * section.height).to("kN")
