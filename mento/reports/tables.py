"""Report tables for beam checks — the presentation half of a check.

These builders turn the state a check leaves on a beam into the labelled,
rounded, unit-annotated tables the Word reports and notebook views display.
They lived inside the design-code modules, which made those modules roughly a
third UI text; Phase 3 of the architecture roadmap moves them here so
``codes/`` holds equations and orchestration only.

They still read and write the beam's private attributes. That is the coupling
Phase 2b could not remove while presentation was the thing storing results —
confining it to this layer is the step that makes removing it possible.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, Dict, List, cast

import pandas as pd
from mento.units import Quantity

from mento.units import inch, kN, mm

from mento.bar_sizes import bar_designation
from mento.codes.registry import design_code
from mento.design_results import GRID, format_longitudinal_rebar, transverse_layout
from mento.precompute import shown, unit_label
from mento.design_warnings import bars_side_by_side

if TYPE_CHECKING:
    from mento.beam import RectangularBeam
    from mento.material import Concrete_ACI_318_19, Concrete_EN_1992_2004
    from mento.forces import Forces
    from mento.settings import BeamSettings


def _transverse_rebar_rows(
    self: "RectangularBeam",
    d_b_shown: Quantity,
    round_to: int | None = 3,
) -> tuple[list[str], list[str], list[Any], list[str]]:
    """The rows that identify the transverse reinforcement of a section.

    A beam is a cage: the closed stirrups, the legs they put across the shear
    plane -- two each, what ``A_v`` counts -- a diameter, a spacing along the
    length, and the spacing of the legs across the width that falls out of
    the count, the one Table 9.7.6.2.2 limits. Five rows. A slab strip has no
    cage to count, so the count gives way to the spacing across the width,
    which is what actually detailed it: three rows. The columns of the table
    stay the same length either way.
    """

    imperial = self.concrete.is_imperial

    def shown_as(value: Quantity, kind: str) -> Any:
        return shown(value, kind, imperial, round_to)

    diameter = bar_value(self, d_b_shown, round_to)
    s_l = shown_as(self._stirrup_s_l, "length")
    bar, length = unit_label("bar", imperial), unit_label("length", imperial)
    if transverse_layout(self) == GRID:
        return (
            ["Stirrup diameter", "Stirrup spacing along length", "Stirrup spacing along width"],
            ["db", "sl", "sw"],
            [diameter, s_l, shown_as(self._leg_spacing_across_width(), "length")],
            [bar, length, length],
        )
    return (
        ["Number of stirrups", "Number of legs", "Stirrup diameter", "Stirrup spacing", "Leg spacing across width"],
        ["ns", "nl", "db", "s", "sw"],
        [
            self._stirrup_n,
            int(2 * self._stirrup_n),
            diameter,
            s_l,
            shown(self._leg_spacing_across_width(), "length", imperial, 2),
        ],
        ["", "", bar, length, length],
    )


def _per_length_digits(imperial: bool) -> int:
    """Decimals of a steel area per length: cm²/m to two, in²/ft -- some twenty times smaller -- to three."""
    return 3 if imperial else 2


def bar_value(self: "RectangularBeam", d_b: Quantity, digits: int | None) -> Any:
    """A bar diameter as a report table writes it: mm in SI, the ASTM size in US customary.

    A US bar is called by its number, ``#4``, not by 0.5 in, so its unit is
    blank, as ``unit_label("bar", True)`` is. No bar at all reads ``-`` there,
    where SI keeps writing 0 mm.
    """
    if self.concrete.is_imperial:
        return bar_designation(d_b) if d_b.magnitude > 0 else "-"
    return shown(d_b, "bar", False, digits)


def _longitudinal_rebar_rows(self: "RectangularBeam", face: str) -> tuple[list[str], list[str], list[Any]]:
    """The two rows that identify the longitudinal reinforcement of one face.

    A beam is a number of bars per layer, so the bars are counted: ``n1+n2``. A
    slab is one bar repeated at a spacing, and the count that falls out of a
    strip is not what it is drawn with, so each of its layers reads as a
    diameter and a spacing instead. ``face`` is ``"b"`` or ``"t"``, and there
    are two rows either way, so every column of the table stays the same length.
    """
    labels = ["First layer bars", "Second layer bars"]
    variables = []
    values = []
    # Only a section detailed by a spacing carries these; a beam has no such
    # attribute and its layers keep being reported as a number of bars. The
    # notation is chosen once for the face, so an empty second layer is still
    # written the way the rest of the face is.
    detailed_by_spacing = getattr(self, f"_s_b1_{face}", None) is not None
    for first, second in ((1, 2), (3, 4)):
        n = getattr(self, f"_n{first}_{face}")
        d_b = getattr(self, f"_d_b{first}_{face}")
        if not detailed_by_spacing:
            variables.append(f"n{first}+n{second}")
            values.append(
                self._format_longitudinal_rebar_string(
                    n, d_b, getattr(self, f"_n{second}_{face}"), getattr(self, f"_d_b{second}_{face}")
                )
            )
            continue
        spacing = getattr(self, f"_s_b{first}_{face}")
        # The bar of a position and its spacing: "Ø1/s1", or "db1@s1" where a
        # "#" would read as a bar size.
        imperial = self.concrete.is_imperial
        variables.append(f"db{first}@s{first}" if imperial else f"Ø{first}/s{first}")
        if n == 0 or d_b.magnitude == 0 or spacing.magnitude == 0:
            values.append("-")
        else:
            bar = bar_designation(d_b) if imperial else f"Ø{d_b:.4g~P}"
            values.append(format_longitudinal_rebar(n, bar, f"{spacing:.4g~P}", imperial=imperial))
    return labels, variables, values


def _bar_spacing_row(
    self: "RectangularBeam", face: str, min_clear: Quantity
) -> tuple[str, Quantity, Quantity | None, Quantity | None]:
    """The label, the value and the limits of one face's bar-spacing row.

    A beam is detailed to a clear distance between bars, and reports the
    smallest one it has against the minimum its settings ask for. A slab is
    detailed to a spacing, and what the codes limit there is how far apart the
    bars may be -- ACI 318-19 7.7.2.3, EN 1992-1-1 9.3.1.1(3) -- since bars far
    enough apart leave the slab between them unreinforced whatever they add up
    to. So the row carries the centre-to-centre spacing of the layer nearest the
    face, and a maximum along with the minimum -- and on a footing, whose bars
    are kept 100 mm apart at the closest, a minimum the code raises above the
    one the settings ask for. A face with no bars on it has nothing to check
    either way. ``face`` is ``"b"`` or ``"t"``.
    """
    side = "top" if face == "t" else "bottom"
    # Only a section detailed by a spacing carries one; a beam has no such
    # attribute and keeps reporting the clear distance between its bars.
    spacing = getattr(self, f"_s_b1_{face}", None)
    if spacing is None:
        clear: Quantity = getattr(self, f"_available_s_{'top' if face == 't' else 'bot'}")
        # A layer of one bar has no bar beside it: nothing to hold to a clear
        # distance, as ``clear_spacing_below_min`` also reads it.
        return f"Minimum spacing {side}", clear, min_clear if bars_side_by_side(self, face) else None, None
    if getattr(self, f"_n1_{face}") == 0 or spacing.magnitude == 0:
        return f"Bar spacing {side}", spacing, None, None
    max_of = getattr(self, "_max_bar_spacing", None)
    min_of = getattr(self, "_min_bar_spacing", None)
    # The value is centre to centre, so the minimum clear distance is read as
    # one bar further apart than the beam reads it. A code that asks for a
    # spacing of its own -- a footing does -- raises that floor.
    minimum: Quantity = min_clear + getattr(self, f"_d_b1_{face}")
    from_code = None if min_of is None else min_of()
    if from_code is not None:
        minimum = max(minimum, from_code)
    return (
        f"Bar spacing {side}",
        spacing,
        minimum,
        None if max_of is None else max_of(),
    )


def _append_max_bar_spacing_rows(self: "RectangularBeam", M: Quantity) -> None:
    """Add a beam's §24.3.2 rows to the flexure limits table, the tension face held to the cap.

    "Maximum spacing top" and "Maximum spacing bottom", each carrying the
    centre-to-centre spacing of the layer nearest the face against the
    crack-control cap of ACI 318-19 / CIRSOC 201-25 §24.3.2 (see
    :meth:`~mento.beam.RectangularBeam._tension_bar_spacing`). The cap is printed on both faces and
    checked on the one the combination puts in tension, the way
    :func:`_drop_max_off_tension_face` treats A_s,max: the clause is written
    on the bars closest to the face in tension, and a combination pulls one
    face or the other. A slab, whose spacing row already carries the cap,
    and a code without it add nothing, so their tables keep their four rows.
    :func:`mento.design_warnings.flexure_warnings` reads the same row.
    """
    table = self._data_min_max_flexure
    for face, label in (("t", "Maximum spacing top"), ("b", "Maximum spacing bottom")):
        row = self._tension_bar_spacing(face)
        if row is None:
            continue
        value, limit = row
        in_tension = M.magnitude > 0 if face == "b" else M.magnitude < 0
        within = value <= limit or math.isclose(value.to("mm").magnitude, limit.to("mm").magnitude)
        ok = within or not in_tension
        table["Check"].append(label)
        table["Unit"].append(unit_label("spacing", self.concrete.is_imperial))
        table["Value"].append(_shown_spacing(self, value))
        table["Min."].append("")
        table["Max."].append(_shown_spacing(self, limit))
        table["Ok?"].append("✅" if ok else "❌")
        if not ok:
            self._all_flexure_checks_passed = False


def _shown_spacing(self: "RectangularBeam", value: Quantity | None) -> Any:
    """A bar spacing or its limit for the report tables (mm, or in), blank where there is none."""
    return "" if value is None else shown(value, "spacing", self.concrete.is_imperial, 2)


def _settings(beam: RectangularBeam) -> BeamSettings:
    """The beam's settings, which ``__post_init__`` always fills in.

    They are typed ``Optional`` on the section because the constructor accepts
    ``None``; by the time a check has run and there is a report to build, they
    exist.
    """
    return cast("BeamSettings", beam.settings)


def _compile_results_EN_1992_2004_shear(self: "RectangularBeam", force: Forces) -> Dict[str, Any]:
    """One row of the EN shear results table."""
    return {
        "Label": self.label,  # Beam label
        "Comb.": force.label,
        "Av,min": round(self._A_v_min.to("cm ** 2 / m").magnitude, 2),  # Minimum shear reinforcement area
        "Av,req": round(self._A_v_req.to("cm ** 2 / m").magnitude, 2),  # Required shear reinforcing area
        "Av": round(self._A_v.to("cm ** 2 / m").magnitude, 2),  # Provided stirrup reinforcement per unit length
        "NEd": self._N_Ed.to("kN").magnitude,
        "VEd,1": self._V_Ed_1.to("kN").magnitude,  # Max Vu for the design at the support
        "VEd,2": self._V_Ed_2.to("kN").magnitude,  # Max Vu for the design at d from the support
        "VRd,c": round(self._V_Rd_c.to("kN").magnitude, 2),  # Concrete contribution to shear capacity
        "VRd,s": round(self._V_Rd_s.to("kN").magnitude, 2),  # Reinforcement contribution to shear capacity
        "VRd": round(self._V_Rd.to("kN").magnitude, 2),  # Total shear capacity
        "VRd,max": round(self._V_Rd_max.to("kN").magnitude, 2),  # Maximum shear capacity
        "VEd,1≤VRd,max": self._max_shear_ok,  # Check if applied shear is within max shear capacity
        "VEd,2≤VRd": self._V_Ed_2.to("kN").magnitude
        <= self._V_Rd.to("kN").magnitude,  # Check if applied shear is within total capacity
        "DCR": round(self._DCRv, 3),
    }


#: Which builders serve which design code.
#:
#: Report *content* is per-code by nature -- ACI's tables say phi*Vn where EN's
#: say V_Rd -- so a new code brings its own builders and adds a row here. What
#: this replaces is the string comparison that used to be repeated at every
#: call site, where a code missing from one chain failed at runtime instead of
#: at lookup. The builders cannot live in the code subpackages: importing them
#: from ``codes/`` would pull pandas, matplotlib and docx back into a layer that
#: a boundary test keeps free of them.
_REPORT_BUILDERS: Dict[str, Dict[str, Any]] = {}


def _register_report_builders(title: str, **builders: Any) -> None:
    _REPORT_BUILDERS[title] = builders


def _builders_for(self: "RectangularBeam") -> Dict[str, Any]:
    try:
        return _REPORT_BUILDERS[self.concrete.design_code]
    except KeyError:
        raise NotImplementedError(
            f"no report tables for design code: {self.concrete.design_code}. "
            f"Registered: {', '.join(sorted(_REPORT_BUILDERS)) or 'none'}"
        ) from None


def build_shear_report(self: "RectangularBeam", force: Forces, state: Any) -> pd.DataFrame:
    """Result row and detail tables for the shear combination just checked.

    ``state`` is what the check returned; the detail tables read from it what
    the compatibility layer does not carry, such as the row of Table 9.7.6.2.2.
    """
    builders = _builders_for(self)
    row = builders["shear_row"](self, force)
    builders["shear_details"](self, state)
    return row if isinstance(row, pd.DataFrame) else pd.DataFrame([row], index=[0])


def build_flexure_report(self: "RectangularBeam", force: Forces) -> pd.DataFrame:
    """Result row and detail tables for the flexure combination just checked."""
    builders = _builders_for(self)
    results = builders["flexure_row"](self, force)
    builders["flexure_details"](self)
    return pd.DataFrame([results], index=[0])


def _compile_results_ACI_shear(self: "RectangularBeam", force: Forces) -> pd.DataFrame:
    imperial = self.concrete.is_imperial
    results = {
        "Label": self.label,
        "Comb.": force.label,
        "Av,min": shown(self._A_v_min, "per_length", imperial, _per_length_digits(imperial)),
        "Av,req": shown(self._A_v_req, "per_length", imperial, _per_length_digits(imperial)),
        "Av": shown(self._A_v, "per_length", imperial, _per_length_digits(imperial)),
        "Vu": shown(self._V_u, "force", imperial),
        "Nu": shown(self._N_u, "force", imperial),
        "ØVc": shown(self._phi_V_c, "force", imperial, 2),
        "ØVs": shown(self._phi_V_s, "force", imperial, 2),
        "ØVn": shown(self._phi_V_n, "force", imperial, 2),
        "ØVmax": shown(self._phi_V_max, "force", imperial, 2),
        "Vu≤ØVmax": self._max_shear_ok,
        "Vu≤ØVn": self._V_u <= self._phi_V_n,
        "DCR": round(self._DCRv, 3),
    }
    return pd.DataFrame([results], index=[0])


def _compile_results_ACI_flexure_metric(self: "RectangularBeam", force: Forces) -> Dict[str, Any]:
    imperial = self.concrete.is_imperial
    # Create dictionaries for bottom and top rows
    if self._M_u >= 0:
        result = {
            "Label": self.label,
            "Comb.": force.label,
            "Position": "Bottom",
            "As,min": shown(self._A_s_min_bot, "area", imperial, 2),
            "As,req top": shown(self._A_s_req_top, "area", imperial, 2),
            "As,req bot": shown(self._A_s_req_bot, "area", imperial, 2),
            "As": shown(self._A_s_bot, "area", imperial, 2),
            # 'c/d': self._c_d_bot,
            "Mu": shown(self._M_u_bot, "moment", imperial, 2),
            "ØMn": shown(self._phi_M_n_bot, "moment", imperial, 2),
            "Mu≤ØMn": self._M_u_bot <= self._phi_M_n_bot,
            "DCR": round(self._DCRb_bot, 3),
        }
    else:
        result = {
            "Label": self.label,
            "Comb.": force.label,
            "Position": "Top",
            "As,min": shown(self._A_s_min_top, "area", imperial, 2),
            "As,req top": shown(self._A_s_req_top, "area", imperial, 2),
            "As,req bot": shown(self._A_s_req_bot, "area", imperial, 2),
            "As": shown(self._A_s_top, "area", imperial, 2),
            # 'c/d': self._c_d_top,
            "Mu": shown(self._M_u_top, "moment", imperial, 2),
            "ØMn": shown(self._phi_M_n_top, "moment", imperial, 2),
            "Mu≤ØMn": -self._M_u_top <= self._phi_M_n_top,
            "DCR": round(self._DCRb_top, 3),
        }
    return result


#: The row of Table 9.7.6.2.2 the check took, as the report words it: short
#: enough that the console table, which does not wrap, keeps its width.
_TABLE_9_7_6_2_2_HALVED = "Vs,req > Vs,lim → Table 9.7.6.2.2: d/4 along, d/2 across"
_TABLE_9_7_6_2_2_LOW = "Vs,req ≤ Vs,lim → Table 9.7.6.2.2: d/2 along, d across"
#: V_s,req is nominal, (Vu - φVc)/φ, where the row above it, ØVs, is factored.
_V_S_REQ_ROW = "Nominal shear the stirrups must carry (Vu/φ − Vc)"
#: The limits-table row of §9.7.6.4.3, on a section whose stirrups brace compression bars.
_SUPPORT_ROW = "Mandatory detailing: compression-bar support spacing (§9.7.6.4.3)"


def _spacing_table_rows(self: "RectangularBeam", state: Any) -> tuple[list[str], list[str], list[Any], list[str]]:
    """Why the spacing limits are what they are: the rows of Table 9.7.6.2.2.

    ACI 318-19 / CIRSOC 201-25 Table 9.7.6.2.2 halves the limits once the
    nominal shear the stirrups must carry, ``(Vu - φVc)/φ``, passes
    0.33·√f'c·bw·d (4·√f'c·bw·d in psi). The rows print that shear, the
    threshold, which row of the table the check took -- read off the
    ``state``, where the equation decided it, so nothing is compared again
    here -- and the absolute cap of that row (ACI 600/300 mm, CIRSOC
    400/200 mm). The limits themselves are the ``Max.`` column of the limits
    table, not repeated; so is the cap of §9.7.6.4.3 (:func:`_support_row`).
    """
    imperial = self.concrete.is_imperial
    V_s_req, V_s_threshold, halved, _, _ = state.spacing_quantities(imperial)
    cap_low, cap_high = design_code(self.concrete).requires("stirrup_spacing_caps")(self.concrete)
    cap = cap_high if halved else cap_low
    threshold = (
        "Threshold of Table 9.7.6.2.2 (4√f'c·bw·d)" if imperial else "Threshold of Table 9.7.6.2.2 (0.33√f'c·bw·d)"
    )
    labels = [
        _V_S_REQ_ROW,
        threshold,
        _TABLE_9_7_6_2_2_HALVED if halved else _TABLE_9_7_6_2_2_LOW,
        "Absolute cap of Table 9.7.6.2.2 in this row",
    ]
    variables = ["Vs,req", "Vs,lim", "", "s,cap"]
    values: list[Any] = [
        shown(V_s_req, "force", imperial, 2),
        shown(V_s_threshold, "force", imperial, 2),
        "",
        shown(cap, "length", imperial, 2),
    ]
    units = [unit_label("force", imperial), unit_label("force", imperial), "", unit_label("length", imperial)]
    return labels, variables, values, units


def _support_row(self: "RectangularBeam", support: Any, support_hook: Any) -> list[Any]:
    """The limits-table row of §9.7.6.4.3: ``[label, unit, s_l, min, max, ok]``.

    Its ``Ok?`` is the mandatory detailing verdict, separate from strength: the spacing
    is past the cap exactly when ``stirrup_spacing_exceeds_compression_support``
    is raised, and a section with no stirrups at all fails it, as
    ``stirrups_required_for_compression_support`` says -- quoting the cap of
    the smallest stirrup §9.7.6.4.2 allows, as that warning does. The row
    does not enter ``_all_shear_checks_passed``, which keeps reading the four
    rows above it.
    """
    s_l = self._stirrup_s_l
    if self._stirrup_n == 0:
        s_max = support_hook(self, support.d_b_min).s_max.to(s_l.units)
        ok = False
    else:
        s_max = support.s_max.to(s_l.units)
        # The comparison of mento.design_warnings: past the cap and not equal to it.
        ok = not (s_l > s_max and not math.isclose(s_l.magnitude, s_max.magnitude))
    return [
        _SUPPORT_ROW,
        unit_label("length", self.concrete.is_imperial),
        shown(s_l, "length", self.concrete.is_imperial, 2),
        "",
        shown(s_max, "length", self.concrete.is_imperial, 2),
        "✅" if ok else "❌",
    ]


def _initialize_dicts_ACI_318_19_shear(self: "RectangularBeam", state: Any) -> None:
    """Initialize the dictionaries used in check and design methods.

    ``state`` is the check state of the combination just run: the rows of
    Table 9.7.6.2.2 read the row the check took from it.
    """
    # This builder serves only ACI 318-19 and CIRSOC 201-25,
    # which is what the registry routes here.
    concrete_aci = cast("Concrete_ACI_318_19", self.concrete)
    imperial = self.concrete.is_imperial
    # Section geometry is the input as given in SI, and to two decimals in inches.
    geometry_digits = 2 if imperial else None
    self._materials_shear = {
        "Materials": [
            "Section Label",
            "Concrete strength",
            "Steel reinforcement yield strength",
            "Concrete density",
            "Normalweight concrete",
            "Safety factor for shear",
        ],
        "Variable": ["", "fc", "fy", "wc", "λ", "Øv"],
        "Value": [
            self.label,
            shown(self.concrete.f_c, "stress", imperial, 2),
            shown(self.steel_bar.f_y, "steel_stress", imperial, 2),
            shown(self.concrete.density, "density", imperial, 1),
            concrete_aci.lambda_factor,
            concrete_aci.phi_v,
        ],
        "Unit": [
            "",
            unit_label("stress", imperial),
            unit_label("steel_stress", imperial),
            unit_label("density", imperial),
            "",
            "",
        ],
    }
    self._geometry_shear = {
        "Geometry": [
            "Section height",
            "Section width",
            "Clear cover",
            "Longitudinal tension rebar",
        ],
        "Variable": ["h", "b", "cc", "As"],
        "Value": [
            shown(self.height, "length", imperial, geometry_digits),
            shown(self.width, "length", imperial, geometry_digits),
            shown(self.c_c, "length", imperial, geometry_digits),
            shown(self._A_s_tension, "area", imperial, 2),
        ],
        "Unit": [*[unit_label("length", imperial)] * 3, unit_label("area", imperial)],
    }
    self._forces_shear = {
        "Design forces": [
            "Axial, positive for compression",
            "Shear",
        ],
        "Variable": ["Nu", "Vu"],
        "Value": [
            shown(self._N_u, "force", imperial, 2),
            shown(self._V_u, "force", imperial, 2),
        ],
        "Unit": [unit_label("force", imperial)] * 2,
    }
    # Min max lists
    # With no stirrup contribution there is no stirrup to report. This used to
    # be done by zeroing the section's own diameter, which made building a
    # report change the section it describes; it is a local now.
    zero_d_b = 0 * mm if self.concrete.unit_system == "metric" else 0 * inch
    d_b_shown = self._stirrup_d_b
    # Neither code states a minimum diameter for a stirrup placed for shear
    # alone (the 10 mm, 6 mm under CIRSOC, where the catalogue starts is a
    # preference); §9.7.6.4.2 does for the stirrups that laterally support
    # compression bars, and that is the minimum the row holds them to.
    support_hook = design_code(self.concrete).stirrup_compression_support
    support = None if support_hook is None else support_hook(self, self._stirrup_d_b)
    db_min: Quantity | None
    if self._phi_V_s == 0 * kN:
        db_min = zero_d_b
        d_b_shown = zero_d_b
    else:
        db_min = None if support is None else support.d_b_min.to(self._stirrup_d_b.units)
    min_values = [
        None,
        None,
        self._A_v_min,
        db_min,
    ]  # Use None for items without a minimum constraint
    max_values = [
        self._stirrup_s_max_l,
        self._stirrup_s_max_w,
        None,
        None,
    ]  # Use None for items without a maximum constraint
    current_values = [
        self._stirrup_s_l,
        self._stirrup_s_w,
        self._A_v,
        d_b_shown,
    ]  # Current values to check
    # Generate check marks based on the range conditions
    checks = [
        "✅" if (min_val is None or curr >= min_val) and (max_val is None or curr <= max_val) else "❌"
        for curr, min_val, max_val in zip(current_values, min_values, max_values)
    ]
    self._all_shear_checks_passed = all(check == "✅" for check in checks)
    # On a beam the spacing across the width is that of the legs of the cage;
    # a slab strip details it as the second spacing of its grid. Both limits
    # are Table 9.7.6.2.2's (the slab's through §7.7.5).
    across = (
        "Stirrup spacing along width (Table 9.7.6.2.2)"
        if transverse_layout(self) == GRID
        else "Leg spacing across width (Table 9.7.6.2.2)"
    )
    self._data_min_max_shear = {
        "Check": [
            "Stirrup spacing along length",
            across,
            "Minimum shear reinforcement",
            "Minimum rebar diameter",
        ],
        "Unit": [
            unit_label("length", imperial),
            unit_label("length", imperial),
            unit_label("per_length", imperial),
            unit_label("bar", imperial),
        ],
        "Value": [
            shown(self._stirrup_s_l, "length", imperial, 2),
            shown(self._stirrup_s_w, "length", imperial, 2),
            shown(self._A_v, "per_length", imperial, _per_length_digits(imperial)),
            bar_value(self, d_b_shown, 0),
        ],
        "Min.": [
            "",
            "",
            shown(self._A_v_min, "per_length", imperial, _per_length_digits(imperial)),
            "" if db_min is None else bar_value(self, db_min, 0),
        ],
        "Max.": [
            shown(self._stirrup_s_max_l, "length", imperial, 2),
            shown(self._stirrup_s_max_w, "length", imperial, 2),
            "",
            "",
        ],
        "Ok?": checks,
    }
    if support is not None:
        # A section whose stirrups brace compression bars is held to the cap of
        # §9.7.6.4.3 too, on the spacing along the member: its own row, with
        # the warnings' verdict, beside the Table 9.7.6.2.2 row it may undercut.
        for column, cell in zip(self._data_min_max_shear, _support_row(self, support, support_hook)):
            self._data_min_max_shear[column] = [*self._data_min_max_shear[column], cell]
    # A slab strip has no cage to count: the same bar sits on a grid, so the row
    # that names a stirrup count gives way to the second spacing that actually
    # detailed it. Same three rows either way, so the columns stay aligned.
    rebar_rows, rebar_vars, rebar_values, rebar_units = _transverse_rebar_rows(self, d_b_shown)
    table_rows, table_vars, table_values, table_units = _spacing_table_rows(self, state)
    self._shear_reinforcement = {
        "Shear reinforcement strength": [
            *rebar_rows,
            "Effective height",
            "Minimum shear reinforcing",
            "Required shear reinforcing",
            "Defined shear reinforcing",
            "Shear rebar strength",
            *table_rows,
        ],
        "Variable": [*rebar_vars, "d", "Av,min", "Av,req", "Av", "ØVs", *table_vars],
        "Value": [
            *rebar_values,
            shown(self._d_shear, "length", imperial, 2),
            shown(self._A_v_min, "per_length", imperial, _per_length_digits(imperial)),
            shown(self._A_v_req, "per_length", imperial, _per_length_digits(imperial)),
            shown(self._A_v, "per_length", imperial, _per_length_digits(imperial)),
            shown(self._phi_V_s, "force", imperial, 2),
            *table_values,
        ],
        "Unit": [
            *rebar_units,
            unit_label("length", imperial),
            *[unit_label("per_length", imperial)] * 3,
            unit_label("force", imperial),
            *table_units,
        ],
    }
    check_max = "✅" if self._max_shear_ok else "❌"
    check_FU = "✅" if self._DCRv < 1 else "❌"
    self._shear_concrete = {
        "Shear strength": [
            "Effective shear area",
            "Longitudinal reinforcement ratio",
            "Size modification factor",
            "Axial stress",
            "Concrete effective shear stress",
            "Concrete strength",
            "Maximum shear strength",
            "Total shear strength",
            "Max shear check",
            "Demand Capacity Ratio",
        ],
        "Variable": [
            "Acv",
            "ρw",
            "λs",
            "σNu",
            "kc",
            "ØVc",
            "ØVmax",
            "ØVn",
            "",
            "DCR",
        ],
        "Value": [
            shown(self._A_cv, "area", imperial, 2),
            round(self._rho_w.magnitude, 5),
            round(self._lambda_s, 3),
            shown(self._sigma_Nu, "stress", imperial, 2),
            shown(self._k_c_min, "stress", imperial, 2),
            shown(self._phi_V_c, "force", imperial, 2),
            shown(self._phi_V_max, "force", imperial, 2),
            shown(self._phi_V_n, "force", imperial, 2),
            check_max,
            round(self._DCRv, 2),
        ],
        "Unit": [
            unit_label("area", imperial),
            "",
            "",
            *[unit_label("stress", imperial)] * 2,
            *[unit_label("force", imperial)] * 3,
            "",
            check_FU,
        ],
    }
    self._shear_all_checks = self._all_shear_checks_passed and (check_max == "✅") and (check_FU == "✅")


def _drop_max_off_tension_face(max_values: List[Any], M: Quantity) -> None:
    """Stop holding to A_s_max a face the combination does not put in tension.

    ``max_values`` is the list of the flexure min/max rows, top steel at 0 and
    bottom steel at 2. A_s_max limits tension steel: the bars a negative moment
    asks for on the bottom are compression steel, and a combination with no
    moment pulls neither face. The limit is still printed; only the check skips
    it. :func:`mento.design_warnings.flexure_warnings` reads it the same way.
    """
    if M.magnitude <= 0:
        max_values[2] = None
    if M.magnitude >= 0:
        max_values[0] = None


def _initialize_dicts_ACI_318_19_flexure(self: "RectangularBeam") -> None:
    # Update longitudinal rebar attributes
    self._update_longitudinal_rebar_attributes()
    """Initialize the dictionaries used in check and design methods."""
    imperial = self.concrete.is_imperial
    geometry_digits = 2 if imperial else None
    self._materials_flexure = {
        "Materials": [
            "Section Label",
            "Concrete strength",
            "Steel reinforcement yield strength",
        ],
        "Variable": ["", "fc", "fy"],
        "Value": [
            self.label,
            shown(self.concrete.f_c, "stress", imperial, 2),
            shown(self.steel_bar.f_y, "steel_stress", imperial, 2),
        ],
        "Unit": ["", unit_label("stress", imperial), unit_label("steel_stress", imperial)],
    }
    self._geometry_flexure = {
        "Geometry": [
            "Section height",
            "Section width",
            "Clear cover",
            "Mechanical top cover",
            "Mechanical bottom cover",
        ],
        "Variable": ["h", "b", "cc", "cm,top", "cm,bot"],
        "Value": [
            shown(self.height, "length", imperial, geometry_digits),
            shown(self.width, "length", imperial, geometry_digits),
            shown(self.c_c, "length", imperial, geometry_digits),
            shown(self._c_mec_top, "length", imperial, 2),
            shown(self._c_mec_bot, "length", imperial, 2),
        ],
        "Unit": [unit_label("length", imperial)] * 5,
    }
    self._forces_flexure = {
        "Design forces": [
            "Top max moment",
            "Bottom max moment",
        ],
        "Variable": ["Mu,top", "Mu,bot"],
        "Value": [
            shown(self._M_u_top, "moment", imperial, 2),
            shown(self._M_u_bot, "moment", imperial, 2),
        ],
        "Unit": [unit_label("moment", imperial)] * 2,
    }
    # Min max lists
    settings = _settings(self)
    min_spacing_top: Quantity = max(settings.clear_spacing, settings.vibrator_size, self._d_b_max_top)
    min_spacing_bot: Quantity = max(settings.clear_spacing, self._d_b_max_bot)
    label_s_top, s_top, s_top_min, s_top_max = _bar_spacing_row(self, "t", min_spacing_top)
    label_s_bot, s_bot, s_bot_min, s_bot_max = _bar_spacing_row(self, "b", min_spacing_bot)
    min_values = [
        self._A_s_min_top,
        s_top_min,
        self._A_s_min_bot,
        s_bot_min,
    ]  # Use None for items without a minimum constraint
    # The maximum is the tension-controlled limit of §9.3.3.1 with the
    # compression steel the other face carries, A_s_max + A_s'*f_s'/f_y: a
    # doubly reinforced face is held to it rather than excused from it.
    max_values = [
        self._A_s_max_eff_top,
        s_top_max,
        self._A_s_max_eff_bot,
        s_bot_max,
    ]  # Use None for items without a maximum constraint
    _drop_max_off_tension_face(max_values, self._M_u)
    current_values = [
        self._A_s_top,
        s_top,
        self._A_s_bot,
        s_bot,
    ]  # Current values to check
    # Past these a face complies only through its compression steel: D.R.
    singly_max = {0: self._A_s_max_top, 2: self._A_s_max_bot}

    ARTICLE_STR = "9.6.1.3"
    # Past the maximum the section is not tension-controlled, which §9.3.3.1
    # (§7.3.3.1 for a one-way slab) does not allow: the row and the DCR of
    # that face say which article it misses.
    tension_controlled_str = self._tension_controlled_clause
    over_max = {
        i: max_val is not None and curr > max_val
        for i, (curr, max_val) in enumerate(zip(current_values, max_values))
        if i in singly_max
    }

    checks = []
    for i, (curr, min_val, max_val) in enumerate(zip(current_values, min_values, max_values)):
        if over_max.get(i):
            checks.append(f"❌ {tension_controlled_str}")
            continue
        passed = (min_val is None or curr >= min_val) and (max_val is None or curr <= max_val)
        if passed:
            doubly = max_val is not None and i in singly_max and curr > singly_max[i]
            checks.append("✅ D.R." if doubly else "✅")
            continue

        # Below A_s_min but not below the minimum left after the 4/3 relief of
        # ACI 318-19 / CIRSOC 201-25 §9.6.1.3: the face complies, by that
        # article. Position 0 is the top face, position 2 the bottom one.
        relieved_min = {0: getattr(self, "_A_s_min_eff_top", None), 2: getattr(self, "_A_s_min_eff_bot", None)}.get(i)
        within_max = max_val is None or curr <= max_val
        if relieved_min is not None and within_max and curr >= relieved_min:
            checks.append(f"✅ {ARTICLE_STR}")
        else:
            # Any other failure: the maximum, or short of the relieved minimum
            checks.append("❌")

    self._all_flexure_checks_passed = not any(check.startswith("❌") for check in checks)
    self._data_min_max_flexure = {
        "Check": [
            "Min/Max As rebar top",
            label_s_top,
            "Min/Max As rebar bottom",
            label_s_bot,
        ],
        "Unit": [unit_label("area", imperial), unit_label("spacing", imperial)] * 2,
        "Value": [
            shown(self._A_s_top, "area", imperial, 2),
            _shown_spacing(self, s_top),
            shown(self._A_s_bot, "area", imperial, 2),
            _shown_spacing(self, s_bot),
        ],
        "Min.": [
            shown(self._A_s_min_top, "area", imperial, 2),
            _shown_spacing(self, s_top_min),
            shown(self._A_s_min_bot, "area", imperial, 2),
            _shown_spacing(self, s_bot_min),
        ],
        "Max.": [
            shown(self._A_s_max_eff_top, "area", imperial, 2),
            _shown_spacing(self, s_top_max),
            shown(self._A_s_max_eff_bot, "area", imperial, 2),
            _shown_spacing(self, s_bot_max),
        ],
        "Ok?": checks,
    }
    _append_max_bar_spacing_rows(self, self._M_u)
    # A face past its tension-controlled limit does not comply whatever its
    # DCR: it reads ❌ with the article, as its limit row does.
    check_DCR_top = f"❌ {tension_controlled_str}" if over_max[0] else "✅" if self._DCRb_top < 1 else "❌"
    check_DCR_bot = f"❌ {tension_controlled_str}" if over_max[2] else "✅" if self._DCRb_bot < 1 else "❌"
    long_rebar_top = _longitudinal_rebar_rows(self, "t")
    self._flexure_capacity_top = {
        "Top reinforcement check": [
            *long_rebar_top[0],
            "Effective height",
            "Depth of equivalent strength block ratio",
            "Minimum rebar reinforcing",
            "Required rebar reinforcing top",
            "Required rebar reinforcing bottom",
            "Defined rebar reinforcing top",
            "Longitudinal reinforcement ratio",
            "Total flexural strength",
            "Demand Capacity Ratio",
        ],
        "Variable": [
            *long_rebar_top[1],
            "d",
            "c/d",
            "As,min",
            "As,req top",
            "As,req bot",
            "As",
            "ρl",
            "ØMn",
            "DCR",
        ],
        "Value": [
            *long_rebar_top[2],
            shown(self._d_top, "length", imperial, 2),
            round(self._c_d_top, 4),
            shown(self._A_s_min_top, "area", imperial, 2),
            shown(self._A_s_req_top, "area", imperial, 2),
            shown(self._A_s_req_bot, "area", imperial, 2),
            shown(self._A_s_top, "area", imperial, 2),
            round(self._rho_l_top.magnitude, 5),
            shown(self._phi_M_n_top, "moment", imperial, 2),
            round(self._DCRb_top, 2),
        ],
        "Unit": [
            "",
            "",
            unit_label("length", imperial),
            "",
            *[unit_label("area", imperial)] * 4,
            "",
            unit_label("moment", imperial),
            check_DCR_top,
        ],
    }
    long_rebar_bot = _longitudinal_rebar_rows(self, "b")
    self._flexure_capacity_bot = {
        "Bottom reinforcement check": [
            *long_rebar_bot[0],
            "Effective height",
            "Depth of equivalent strength block ratio",
            "Minimum rebar reinforcing",
            "Required rebar reinforcing top",
            "Required rebar reinforcing bottom",
            "Defined rebar reinforcing bottom",
            "Longitudinal reinforcement ratio",
            "Total flexural strength",
            "Demand Capacity Ratio",
        ],
        "Variable": [
            *long_rebar_bot[1],
            "d",
            "c/d",
            "As,min",
            "As,req top",
            "As,req bot",
            "As",
            "ρl",
            "ØMn",
            "DCR",
        ],
        "Value": [
            *long_rebar_bot[2],
            shown(self._d_bot, "length", imperial, 2),
            round(self._c_d_bot, 4),
            shown(self._A_s_min_bot, "area", imperial, 2),
            shown(self._A_s_req_top, "area", imperial, 2),
            shown(self._A_s_req_bot, "area", imperial, 2),
            shown(self._A_s_bot, "area", imperial, 2),
            round(self._rho_l_bot.magnitude, 5),
            shown(self._phi_M_n_bot, "moment", imperial, 2),
            round(self._DCRb_bot, 2),
        ],
        "Unit": [
            "",
            "",
            unit_label("length", imperial),
            "",
            *[unit_label("area", imperial)] * 4,
            "",
            unit_label("moment", imperial),
            check_DCR_bot,
        ],
    }
    self._flexure_all_checks = self._all_flexure_checks_passed and (check_DCR_bot == "✅") and (check_DCR_top == "✅")


def _compile_results_EN_1992_2004_flexure_metric(self: "RectangularBeam", force: Forces) -> Dict[str, Any]:
    # Create dictionaries for bottom and top rows
    if self._M_Ed >= 0:
        result = {
            "Label": self.label,
            "Comb.": force.label,
            "Position": "Bottom",
            "As,min": round(self._A_s_min_bot.to("cm ** 2").magnitude, 2),
            "As,req top": round(self._A_s_req_top.to("cm ** 2").magnitude, 2),
            "As,req bot": round(self._A_s_req_bot.to("cm ** 2").magnitude, 2),
            "As": round(self._A_s_bot.to("cm ** 2").magnitude, 2),
            # 'c/d': self._c_d_bot,
            "MEd": round(self._M_Ed_bot.to("kN*m").magnitude, 2),
            "MRd": round(self._M_Rd_bot.to("kN*m").magnitude, 2),
            "MEd≤MRd": self._M_Ed_bot <= self._M_Rd_bot,
            "DCR": round(self._DCRb_bot, 3),
        }
    else:
        result = {
            "Label": self.label,
            "Comb.": force.label,
            "Position": "Top",
            "As,min": round(self._A_s_min_top.to("cm ** 2").magnitude, 2),
            "As,req top": round(self._A_s_req_top.to("cm ** 2").magnitude, 2),
            "As,req bot": round(self._A_s_req_bot.to("cm ** 2").magnitude, 2),
            "As": round(self._A_s_top.to("cm ** 2").magnitude, 2),
            # 'c/d': self._c_d_top,
            "MEd": round(self._M_Ed_top.to("kN*m").magnitude, 2),
            "MRd": round(self._M_Rd_top.to("kN*m").magnitude, 2),
            "MEd≤MRd": self._M_Ed_top <= self._M_Rd_top,
            "DCR": round(self._DCRb_top, 3),
        }
    return result


#: Where the EN spacing limits come from, for the strength table of a beam, one
#: row per direction. The 400 mm on the along-length limit is mento's own:
#: Expression (9.6N) has no cap.
_EN_SPACING_ROWS = (
    "Expression (9.6N) along: 0.75·d·(1 + cot α), capped at 400 mm by mento",
    "Expression (9.8N) across: 0.75·d, at most 600 mm",
)


def _initialize_dicts_EN_1992_2004_shear(self: "RectangularBeam", state: Any) -> None:
    """Initialize the dictionaries used in check and design methods.

    ``state`` is taken for the same signature as the ACI builder; EN 1992-1-1
    has no threshold row to read from it.
    """
    # This builder serves only EN 1992-2004,
    # which is what the registry routes here.
    concrete_en = cast("Concrete_EN_1992_2004", self.concrete)
    self._materials_shear = {
        "Materials": [
            "Section Label",
            "Concrete strength",
            "Steel reinforcement yield strength",
            "Safety factor for concrete",
            "Safety factor for steel",
            "Coefficient for long term effects and loading effects",
        ],
        "Variable": ["", "fck", "fywk", "γc", "γs", "αcc"],
        "Value": [
            self.label,
            round(concrete_en.f_ck.to("MPa").magnitude, 2),
            round(self.steel_bar.f_y.to("MPa").magnitude, 2),
            concrete_en.gamma_c,
            self.steel_bar.gamma_s,
            concrete_en.alpha_cc,
        ],
        "Unit": ["", "MPa", "MPa", "", "", ""],
    }
    self._geometry_shear = {
        "Geometry": [
            "Section height",
            "Section width",
            "Clear cover",
            "Longitudinal tension rebar",
        ],
        "Variable": ["h", "b", "cc", "As"],
        "Value": [
            self.height.to("cm").magnitude,
            self.width.to("cm").magnitude,
            self.c_c.to("cm").magnitude,
            round(self._A_s_tension.to("cm**2").magnitude, 2),
        ],
        "Unit": ["cm", "cm", "cm", "cm²"],
    }
    self._forces_shear = {
        "Design forces": [
            "Axial, positive for compression",
            "Shear",
        ],
        "Variable": ["NEd", "VEd,2"],
        "Value": [
            round(self._N_Ed.to("kN").magnitude, 2),
            round(self._V_Ed_2.to("kN").magnitude, 2),
        ],
        "Unit": ["kN", "kN"],
    }
    # Min max lists
    # Same as the ACI table above: a local, not a write to the section.
    d_b_shown = self._stirrup_d_b
    if self._V_Rd_s == 0 * kN:
        d_b_shown = 0 * mm if self.concrete.unit_system == "metric" else 0 * inch
    # Min max lists
    min_values = [
        None,
        None,
        self._A_v_min,
    ]  # Use None for items without a minimum constraint
    max_values = [
        self._stirrup_s_max_l,
        self._stirrup_s_max_w,
        None,
    ]  # Use None for items without a maximum constraint
    current_values = [
        self._stirrup_s_l,
        self._stirrup_s_w,
        self._A_v,
    ]  # Current values to check

    # Generate check marks based on the range conditions
    checks = [
        "✅" if (min_val is None or curr >= min_val) and (max_val is None or curr <= max_val) else "❌"
        for curr, min_val, max_val in zip(current_values, min_values, max_values)
    ]
    self._all_shear_checks_passed = all(check == "✅" for check in checks)
    grid = transverse_layout(self) == GRID
    self._data_min_max_shear = {
        "Check": [
            "Stirrup spacing along length",
            "Stirrup spacing along width" if grid else "Leg spacing across width (§9.2.2(8))",
            "Minimum shear reinforcement",
        ],
        "Unit": ["cm", "cm", "cm²/m"],
        "Value": [
            round(self._stirrup_s_l.to("cm").magnitude, 2),
            round(self._stirrup_s_w.to("cm").magnitude, 2),
            round(self._A_v.to("cm**2/m").magnitude, 2),
        ],
        "Min.": ["", "", round(self._A_v_min.to("cm**2/m").magnitude, 2)],
        "Max.": [
            round(self._stirrup_s_max_l.to("cm").magnitude, 2),
            round(self._stirrup_s_max_w.to("cm").magnitude, 2),
            "",
        ],
        "Ok?": checks,
    }
    rebar_rows, rebar_vars, rebar_values, rebar_units = _transverse_rebar_rows(self, d_b_shown, round_to=None)
    # A beam says where its limits come from; a slab strip's grid is
    # detailed by its own spacings.
    source: list[str] = [] if grid else list(_EN_SPACING_ROWS)
    self._shear_reinforcement = {
        "Shear reinforcement strength": [
            *rebar_rows,
            "Effective height",
            "Minimum shear reinforcing",
            "Required shear reinforcing",
            "Defined shear reinforcing",
            "Shear rebar strength",
            *source,
        ],
        "Variable": [*rebar_vars, "d", "Asw,min", "Asw,req", "Asw", "VRd,s", *["" for _ in source]],
        "Value": [
            *rebar_values,
            round(self._d_shear.to("cm").magnitude, 2),
            round(self._A_v_min.to("cm**2/m").magnitude, 2),
            round(self._A_v_req.to("cm**2/m").magnitude, 2),
            round(self._A_v.to("cm**2/m").magnitude, 2),
            round(self._V_Rd_s.to("kN").magnitude, 2),
            *["" for _ in source],
        ],
        "Unit": [*rebar_units, "cm", "cm²/m", "cm²/m", "cm²/m", "kN", *["" for _ in source]],
    }
    check_max = "✅" if self._max_shear_ok else "❌"
    check_DCR = "✅" if self._DCRv < 1 else "❌"
    rho_l: Quantity = self._rho_l_shear_bot + self._rho_l_shear_top
    self._shear_concrete = {
        "Shear strength": [
            "Longitudinal reinforcement ratio",
            "k value",
            "Axial stress",
            "Concrete strut angle",
            "Concrete strength",
            "Maximum shear strength",
            "Total shear strength",
            "Max shear check",
            "Demand Capacity Ratio",
        ],
        "Variable": ["ρl", "k", "σcd", "Θ", "VRd,c", "VRd,max", "VRd", "", "DCR"],
        "Value": [
            round(rho_l.magnitude, 4),
            round(self._k_value, 2),
            round(self._sigma_cp.to("MPa").magnitude, 2),
            round(math.degrees(self._theta), 1),
            round(self._V_Rd_c.to("kN").magnitude, 2),
            round(self._V_Rd_max.to("kN").magnitude, 2),
            round(self._V_Rd.to("kN").magnitude, 2),
            check_max,
            round(self._DCRv, 3),
        ],
        "Unit": ["", "", "MPa", "deg", "kN", "kN", "kN", "", check_DCR],
    }


def _initialize_dicts_EN_1992_2004_flexure(self: "RectangularBeam") -> None:
    # Update longitudinal rebar attributes
    # This builder serves only EN 1992-2004,
    # which is what the registry routes here.
    concrete_en = cast("Concrete_EN_1992_2004", self.concrete)
    self._update_longitudinal_rebar_attributes()
    """Initialize the dictionaries used in check and design methods."""
    self._materials_flexure = {
        "Materials": [
            "Section Label",
            "Concrete strength",
            "Steel reinforcement yield strength",
        ],
        "Variable": ["", "fck", "fyk"],
        "Value": [
            self.label,
            round(concrete_en.f_ck.to("MPa").magnitude, 2),
            round(self.steel_bar.f_y.to("MPa").magnitude, 2),
        ],
        "Unit": ["", "MPa", "MPa"],
    }
    self._geometry_flexure = {
        "Geometry": [
            "Section height",
            "Section width",
            "Clear cover",
            "Mechanical top cover",
            "Mechanical bottom cover",
        ],
        "Variable": ["h", "b", "cc", "cm,top", "cm,bot"],
        "Value": [
            self.height.to("cm").magnitude,
            self.width.to("cm").magnitude,
            self.c_c.to("cm").magnitude,
            round(self._c_mec_top.to("cm").magnitude, 2),
            round(self._c_mec_bot.to("cm").magnitude, 2),
        ],
        "Unit": ["cm", "cm", "cm", "cm", "cm"],
    }
    self._forces_flexure = {
        "Design forces": [
            "Top max moment",
            "Bottom max moment",
        ],
        "Variable": ["MEd,top", "MEd,bot"],
        "Value": [
            round(self._M_Ed_top.to("kN*m").magnitude, 2),
            round(self._M_Ed_bot.to("kN*m").magnitude, 2),
        ],
        "Unit": ["kNm", "kNm"],
    }
    # Min max lists
    settings = _settings(self)
    min_spacing_top: Quantity = max(settings.clear_spacing, settings.vibrator_size, self._d_b_max_top)
    min_spacing_bot: Quantity = max(settings.clear_spacing, self._d_b_max_bot)
    label_s_top, s_top, s_top_min, s_top_max = _bar_spacing_row(self, "t", min_spacing_top)
    label_s_bot, s_bot, s_bot_min, s_bot_max = _bar_spacing_row(self, "b", min_spacing_bot)
    min_values = [
        self._A_s_min_top,
        s_top_min,
        self._A_s_min_bot,
        s_bot_min,
    ]  # Use None for items without a minimum constraint
    max_values = [
        self._A_s_max_top,
        s_top_max,
        self._A_s_max_bot,
        s_bot_max,
    ]  # Use None for items without a maximum constraint
    current_values = [
        self._A_s_top,
        s_top,
        self._A_s_bot,
        s_bot,
    ]  # Current values to check

    # Generate check marks based on the range conditions
    checks = []
    for i, (curr, min_val, max_val) in enumerate(zip(current_values, min_values, max_values)):
        # --- EXCEPTION FOR DOUBLY REINFORCED SECTIONS ---
        # If doubly reinforced, ignore maximum limits for top (i=0) and bottom (i=2)
        if self._doubly_reinforced and i in (0, 2):
            # If it passes min, we give the special tag
            if min_val is None or curr >= min_val:
                checks.append("✅ D.R.")
                continue
            # If it fails min, let the normal logic handle it (fall through)
        # -------------------------------------------------

        passed = (min_val is None or curr >= min_val) and (max_val is None or curr <= max_val)
        if passed:
            checks.append("✅")
        else:
            checks.append("❌")
    self._all_flexure_checks_passed = not any(check in ("❌") for check in checks)
    self._data_min_max_flexure = {
        "Check": [
            "Min/Max As rebar top",
            label_s_top,
            "Min/Max As rebar bottom",
            label_s_bot,
        ],
        "Unit": ["cm²", "mm", "cm²", "mm"],
        "Value": [
            round(self._A_s_top.to("cm**2").magnitude, 2),
            _shown_spacing(self, s_top),
            round(self._A_s_bot.to("cm**2").magnitude, 2),
            _shown_spacing(self, s_bot),
        ],
        "Min.": [
            round(self._A_s_min_top.to("cm**2").magnitude, 2),
            _shown_spacing(self, s_top_min),
            round(self._A_s_min_bot.to("cm**2").magnitude, 2),
            _shown_spacing(self, s_bot_min),
        ],
        "Max.": [
            round(self._A_s_max_top.to("cm**2").magnitude, 2),
            _shown_spacing(self, s_top_max),
            round(self._A_s_max_bot.to("cm**2").magnitude, 2),
            _shown_spacing(self, s_bot_max),
        ],
        "Ok?": checks,
    }
    # EN 1992-1-1 registers no such cap (it controls cracking through §7.3.3),
    # so this adds nothing; it is here so a code that does gets the rows.
    _append_max_bar_spacing_rows(self, self._M_Ed)
    check_DCR_top = "✅" if self._DCRb_top < 1 else "❌"
    check_DCR_bot = "✅" if self._DCRb_bot < 1 else "❌"
    long_rebar_top = _longitudinal_rebar_rows(self, "t")
    self._flexure_capacity_top = {
        "Top reinforcement check": [
            *long_rebar_top[0],
            "Effective height",
            "Depth of equivalent strength block ratio",
            "Minimum rebar reinforcing",
            "Required rebar reinforcing top",
            "Required rebar reinforcing bottom",
            "Defined rebar reinforcing top",
            "Longitudinal reinforcement ratio",
            "Total flexural strength",
            "Demand Capacity Ratio",
        ],
        "Variable": [
            *long_rebar_top[1],
            "d",
            "c/d",
            "As,min",
            "As,req top",
            "As,req bot",
            "As",
            "ρl",
            "MRd",
            "DCR",
        ],
        "Value": [
            *long_rebar_top[2],
            round(self._d_top.to("cm").magnitude, 2),
            self._c_d_top,
            round(self._A_s_min_top.to("cm**2").magnitude, 2),
            round(self._A_s_req_top.to("cm**2").magnitude, 2),
            round(self._A_s_req_bot.to("cm**2").magnitude, 2),
            round(self._A_s_top.to("cm**2").magnitude, 2),
            round(self._rho_l_top.magnitude, 5),
            round(self._M_Rd_top.to("kN*m").magnitude, 2),
            round(self._DCRb_top, 2),
        ],
        "Unit": [
            "",
            "",
            "cm",
            "",
            "cm²",
            "cm²",
            "cm²",
            "cm²",
            "",
            "kNm",
            check_DCR_top,
        ],
    }
    long_rebar_bot = _longitudinal_rebar_rows(self, "b")
    self._flexure_capacity_bot = {
        "Bottom reinforcement check": [
            *long_rebar_bot[0],
            "Effective height",
            "Depth of equivalent strength block ratio",
            "Minimum rebar reinforcing",
            "Required rebar reinforcing top",
            "Required rebar reinforcing bottom",
            "Defined rebar reinforcing bottom",
            "Longitudinal reinforcement ratio",
            "Total flexural strength",
            "Demand Capacity Ratio",
        ],
        "Variable": [
            *long_rebar_bot[1],
            "d",
            "c/d",
            "As,min",
            "As,req top",
            "As,req bot",
            "As",
            "ρl",
            "MRd",
            "DCR",
        ],
        "Value": [
            *long_rebar_bot[2],
            round(self._d_bot.to("cm").magnitude, 2),
            self._c_d_bot,
            round(self._A_s_min_bot.to("cm**2").magnitude, 2),
            round(self._A_s_req_top.to("cm**2").magnitude, 2),
            round(self._A_s_req_bot.to("cm**2").magnitude, 2),
            round(self._A_s_bot.to("cm**2").magnitude, 2),
            round(self._rho_l_bot.magnitude, 5),
            round(self._M_Rd_bot.to("kN*m").magnitude, 2),
            round(self._DCRb_bot, 2),
        ],
        "Unit": [
            "",
            "",
            "cm",
            "",
            "cm²",
            "cm²",
            "cm²",
            "cm²",
            "",
            "kNm",
            check_DCR_bot,
        ],
    }
    self._flexure_all_checks = self._all_flexure_checks_passed and (check_DCR_bot == "✅") and (check_DCR_top == "✅")


# Registered at the bottom, once every builder above is defined. ACI 318-19 and
# CIRSOC 201-25 share every table: the two codes publish the same equations.
for _aci_title in ("ACI 318-19", "CIRSOC 201-25"):
    _register_report_builders(
        _aci_title,
        shear_row=_compile_results_ACI_shear,
        shear_details=_initialize_dicts_ACI_318_19_shear,
        flexure_row=_compile_results_ACI_flexure_metric,
        flexure_details=_initialize_dicts_ACI_318_19_flexure,
    )

_register_report_builders(
    "EN 1992-2004",
    shear_row=_compile_results_EN_1992_2004_shear,
    shear_details=_initialize_dicts_EN_1992_2004_shear,
    flexure_row=_compile_results_EN_1992_2004_flexure_metric,
    flexure_details=_initialize_dicts_EN_1992_2004_flexure,
)
