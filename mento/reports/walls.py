"""Notebook views and Word reports for a shear wall.

The wall's counterpart to :mod:`mento.reports.views` and
:mod:`mento.reports.documents`. Both media live in one module here because the
wall's presentation is small enough that splitting it would cost more than it
explains.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional, cast

import pandas as pd
from IPython.display import Markdown, display
from mento.units import Quantity

from mento._version import __version__ as MENTO_VERSION
from mento.i18n import get_language, translate
from mento.material import Concrete_ACI_318_19, Concrete_EN_1992_2004
from mento.precompute import DISPLAY, shown, unit_label
from mento.results import DocumentBuilder, Formatter, TablePrinter
from mento.units import mm
from mento.wall_results import mesh_callout

if TYPE_CHECKING:
    from mento.forces import Forces
    from mento.shear_wall import ShearWall


def _aci(self: "ShearWall") -> Concrete_ACI_318_19:
    """The wall's concrete, narrowed.

    ``_check_shear_ACI_318_19_wall`` raises a TypeError for anything else
    before this report can be built, so the cast cannot be wrong here.
    """
    return cast(Concrete_ACI_318_19, self.concrete)


def _show(markdown: str) -> None:
    """Render Markdown in a notebook; IPython ships no type information."""
    display(Markdown(markdown))  # type: ignore[no-untyped-call]


def wall_flexure_results_detailed_doc(self: "ShearWall", force: Optional[Forces] = None) -> None:
    raise NotImplementedError("Flexure results are not implemented for ShearWall (Phase 0).")


def wall_data(self: "ShearWall") -> None:
    """Wall basic info as Markdown (length, thickness, wall height hw, materials)."""
    level_str = f"Level {self.level}, " if self.level else ""
    units = DISPLAY[self.concrete.is_imperial]
    markdown_content = (
        f"{level_str}Shear Wall {self.label}, "
        f"$l_w$={self.length.to(units['wall_length'])}, "
        f"$t$={self.thickness.to(units['length'])}, "
        f"$h_w$={self.height.to(units['wall_length'])}, "
        f"$c_c$={self.c_c.to(units['length'])}, "
        f"Concrete {self.concrete.name}, Rebar {self.steel_bar.name}."
    )
    self._md_data = markdown_content
    _show(markdown_content)
    return None


def wall_shear_results(self: "ShearWall") -> None:
    """The governing combination in one line of Markdown, in the code's own symbols."""
    if not self._shear_wall_checked:
        self._md_shear_results = "Shear results are not available."
        return None

    details = self._limiting_case_shear_details or {}
    check = details.get("check")
    if check is None:
        self._md_shear_results = "No shear to check."
        _show(self._md_shear_results)
        return None

    formatter = Formatter()
    checks_pass = details.get("checks_pass", False)
    warning = "⚠️ Some checks failed, see detailed results." if not checks_pass else ""

    imperial = self.concrete.is_imperial
    rebar_h = mesh_callout(self._d_b_h, self._s_h, imperial) if self._s_h.magnitude > 0 else "not assigned"
    rebar_v = mesh_callout(self._d_b_v, self._s_v, imperial) if self._s_v.magnitude > 0 else "not assigned"
    force_unit = unit_label("force", imperial)
    symbols = _builders_for(self)["symbols"]

    markdown_content = (
        f"Horizontal rebar: {rebar_h}, ${symbols['rho_h']}$={round(check.rho_t, 5)}, "
        f"Minimum vertical rebar: {rebar_v}, ${symbols['rho_v']}$={round(check.rho_l, 5)}, "
        f"${symbols['demand']}$={shown(check.V_u, 'force', imperial, 2)} {force_unit}, "
        f"${symbols['capacity']}$={shown(check.V_capacity, 'force', imperial, 2)} {force_unit} → "
        f"{formatter.DCR(round(check.DCR, 3))} {warning}"
    )
    self._md_shear_results = markdown_content
    _show(markdown_content)
    return None


def wall_shear_results_detailed(self: "ShearWall", force: Optional[Forces] = None) -> None:
    if not self._shear_wall_checked:
        self._md_shear_results = "Shear results are not available."
        return None
    if force:
        if force.id not in self._shear_results_detailed_list:
            raise ValueError(f"No results found for Forces object with ID {force.id}.")
        result_data = self._shear_results_detailed_list[force.id]
    else:
        result_data = self._limiting_case_shear_details

    language = get_language()
    print(translate("===== SHEAR WALL DETAILED RESULTS =====", language))
    TablePrinter("MATERIALS", language).print_table_data(self._materials_shear_wall, headers="keys")
    TablePrinter("GEOMETRY", language).print_table_data(self._geometry_shear_wall, headers="keys")
    TablePrinter("FORCES", language).print_table_data(result_data["forces"], headers="keys")
    TablePrinter("MAX AND MIN LIMIT CHECKS", language).print_table_data(result_data["min_max"], headers="keys")
    TablePrinter("SHEAR STRENGTH", language).print_table_data(result_data["shear_capacity"], headers="keys")


def wall_shear_results_detailed_doc(self: "ShearWall", force: Optional[Forces] = None) -> None:
    if not self._shear_wall_checked:
        self._md_shear_results = "Shear results are not available."
        return None
    if force:
        if force.id not in self._shear_results_detailed_list:
            raise ValueError(f"No results found for Forces object with ID {force.id}.")
        result_data = self._shear_results_detailed_list[force.id]
    else:
        result_data = self._limiting_case_shear_details

    df_materials = pd.DataFrame(self._materials_shear_wall)
    df_geometry = pd.DataFrame(self._geometry_shear_wall)
    df_forces = pd.DataFrame(result_data["forces"])
    df_min_max = pd.DataFrame(result_data["min_max"])
    df_capacity = pd.DataFrame(result_data["shear_capacity"])

    doc_builder = DocumentBuilder(title="Concrete shear wall check", language=get_language())
    doc_builder.add_heading("Shear Wall {label} shear check", level=1, label=self.label)
    doc_builder.add_text(
        "Made with mento {version}. Design code: {design_code}",
        version=MENTO_VERSION,
        design_code=self.concrete.design_code,
    )
    doc_builder.add_heading("Section Data", level=2)
    doc_builder.add_table_data(df_materials)
    doc_builder.add_table_data(df_geometry)
    doc_builder.add_table_data(df_forces)
    doc_builder.add_heading("Limit checks", level=2)
    doc_builder.add_table_min_max(df_min_max)
    doc_builder.add_heading("Strength Checks", level=2)
    doc_builder.add_table_dcr(df_capacity)
    doc_builder.save(f"Shear Wall {self.label} shear check {self.concrete.design_code}.docx")


def build_wall_shear_report(self: "ShearWall", force: Forces) -> pd.DataFrame:
    """Detail tables and result row for the wall combination just checked."""
    builders = _builders_for(self)
    builders["details"](self, force)
    return cast(pd.DataFrame, builders["row"](self, force))


def wall_units_row(self: "ShearWall") -> pd.DataFrame:
    """The units row the wall's ``check_shear`` table starts with, in its code's columns."""
    return pd.DataFrame([_builders_for(self)["units_row"](self)])


# ---------------------------------------------------------------------------
# ACI 318-19 / CIRSOC 201-25
# ---------------------------------------------------------------------------


def _compile_wall_shear_dicts(self: "ShearWall", force: Forces) -> None:
    """Populate result dicts used by detailed output methods (ACI 318-19 / CIRSOC 201-25)."""
    phi_v = _aci(self).phi_v
    imperial = self.concrete.is_imperial
    unit = unit_label("force", imperial)
    # One decimal in SI, as the tables always had; lengths in inches and feet
    # read to two, and a US f'c is a whole number of psi.
    length_digits = 2 if imperial else 1

    # Materials
    self._materials_shear_wall = {
        "Materials": [
            "Section Label",
            "Concrete strength",
            "Steel reinforcement yield strength",
            "Normalweight concrete",
            "Safety factor for shear",
        ],
        "Variable": ["", "fc", "fy", "λ", "Øv"],
        "Value": [
            self.label,
            shown(self.concrete.f_c, "stress", imperial, 0 if imperial else 2),
            shown(self.steel_bar.f_y, "steel_stress", imperial, 2),
            _aci(self).lambda_factor,
            phi_v,
        ],
        "Unit": [
            "",
            unit_label("stress", imperial),
            unit_label("steel_stress", imperial),
            "",
            "",
        ],
    }
    # Geometry
    self._geometry_shear_wall = {
        "Geometry": [
            "Wall thickness",
            "Wall length",
            "Wall height",
            "Aspect ratio",
            "Gross shear area",
        ],
        "Variable": ["t", "lw", "hw", "hw/lw", "Acv"],
        "Value": [
            shown(self.thickness, "length", imperial, length_digits),
            shown(self.length, "wall_length", imperial, length_digits),
            shown(self.height, "wall_length", imperial, length_digits),
            round(self._hw_lw, 3),
            shown(self._Acv, "area", imperial, 1),
        ],
        "Unit": [
            unit_label("length", imperial),
            unit_label("wall_length", imperial),
            unit_label("wall_length", imperial),
            "",
            unit_label("area", imperial),
        ],
    }

    rho_t_ok = bool(self._rho_t >= self._rho_t_min)
    rho_l_ok = bool(self._rho_l >= self._rho_l_min)
    s_h_ok = bool(self._s_h <= self._s_h_max) if self._s_h > 0 * mm else True
    s_v_ok = bool(self._s_v <= self._s_v_max) if self._s_v > 0 * mm else True
    Vn_max_ok = bool(self._V_u <= self._phi_V_n_max_wall)
    Vn_ok = bool(self._V_u <= self._phi_V_n_wall)

    self._all_wall_shear_checks_passed = all([rho_t_ok, rho_l_ok, Vn_max_ok, Vn_ok])

    def _v(q: Quantity) -> Any:
        return shown(q, "force", self.concrete.is_imperial, 2)

    self._forces_shear_wall = {
        "Design forces": ["Shear"],
        "Variable": ["Vu"],
        "Value": [_v(self._V_u)],
        "Unit": [unit],
    }
    self._shear_capacity_wall = {
        "Shear strength": [
            "Concrete shear strength",
            "Steel shear strength",
            "Total shear strength",
            "Maximum shear strength",
            "Demand Capacity Ratio",
        ],
        "Variable": ["ØVc", "ØVs", "ØVn", "ØVn,max", "DCR"],
        "Value": [
            _v(phi_v * self._V_c_wall),
            _v(phi_v * self._V_s_wall),
            _v(self._phi_V_n_wall),
            _v(self._phi_V_n_max_wall),
            round(self._DCRv_wall, 3),
        ],
        "Unit": [unit, unit, unit, unit, ""],
    }
    self._data_min_max_wall = {
        "Check": [
            "Horizontal reinforcement ratio",
            "Minimum vertical reinf. ratio",
            "Horizontal bar spacing (E.F.)",
            "Vertical bar spacing (E.F.)",
            "Maximum shear capacity",
            "Total shear capacity",
        ],
        "Unit": ["", "", unit_label("spacing", imperial), unit_label("spacing", imperial), unit, unit],
        "Value": [
            round(self._rho_t.to("").magnitude, 5),
            round(self._rho_l.to("").magnitude, 5),
            shown(self._s_h, "spacing", imperial, length_digits) if self._s_h > 0 * mm else 0.0,
            shown(self._s_v, "spacing", imperial, length_digits) if self._s_v > 0 * mm else 0.0,
            _v(self._V_u),
            _v(self._V_u),
        ],
        "Min.": [
            round(self._rho_t_min.to("").magnitude, 5),
            round(self._rho_l_min.to("").magnitude, 5),
            "",
            "",
            "",
            "",
        ],
        "Max.": [
            "",
            "",
            shown(self._s_h_max, "spacing", imperial, length_digits),
            shown(self._s_v_max, "spacing", imperial, length_digits),
            _v(self._phi_V_n_max_wall),
            _v(self._phi_V_n_wall),
        ],
        "Ok?": [
            "✅" if rho_t_ok else "❌",
            "✅" if rho_l_ok else "❌",
            "✅" if s_h_ok else "❌",
            "✅" if s_v_ok else "❌",
            "✅" if Vn_max_ok else "❌",
            "✅" if Vn_ok else "❌",
        ],
    }


def _compile_results_wall_shear(self: "ShearWall", force: Forces) -> pd.DataFrame:
    """Build a one-row DataFrame for this force combination (ACI 318-19 / CIRSOC 201-25)."""
    phi_v = _aci(self).phi_v

    def _v(q: Quantity) -> Any:
        return shown(q, "force", self.concrete.is_imperial, 2)

    row = {
        "Label": self.label,
        "Comb.": force.label,
        "ρt,min": round(self._rho_t_min.to("").magnitude, 5),
        "ρt,req": round(self._rho_t_req.to("").magnitude, 5),
        "ρt": round(self._rho_t.to("").magnitude, 5),
        "ρl,min": round(self._rho_l_min.to("").magnitude, 5),
        "ρl": round(self._rho_l.to("").magnitude, 5),
        "Vu": _v(self._V_u),
        "ØVc": _v(phi_v * self._V_c_wall),
        "ØVs": _v(phi_v * self._V_s_wall),
        "ØVn": _v(self._phi_V_n_wall),
        "ØVn,max": _v(self._phi_V_n_max_wall),
        "Vu≤ØVn,max": bool(self._V_u <= self._phi_V_n_max_wall),
        "Vu≤ØVn": bool(self._V_u <= self._phi_V_n_wall),
        "DCR": round(self._DCRv_wall, 3),
    }
    return pd.DataFrame([row])


def _units_row_aci(self: "ShearWall") -> Dict[str, str]:
    v_unit = unit_label("force", self.concrete.is_imperial)
    return {
        "Label": "",
        "Comb.": "",
        "ρt,min": "",
        "ρt,req": "",
        "ρt": "",
        "ρl,min": "",
        "ρl": "",
        "Vu": v_unit,
        "ØVc": v_unit,
        "ØVs": v_unit,
        "ØVn": v_unit,
        "ØVn,max": v_unit,
        "Vu≤ØVn,max": "",
        "Vu≤ØVn": "",
        "DCR": "",
    }


# ---------------------------------------------------------------------------
# EN 1992-1-1
# ---------------------------------------------------------------------------


def _en(self: "ShearWall") -> Concrete_EN_1992_2004:
    """The wall's concrete, narrowed; ``_check_shear_EN_1992_2004_wall`` has already refused anything else."""
    return cast(Concrete_EN_1992_2004, self.concrete)


def _kN(q: Quantity) -> Any:
    return shown(q, "force", False, 2)


def _per_m(q: Quantity) -> Any:
    return shown(q, "per_length", False, 2)


def _at_least(value: Quantity, limit: Quantity) -> bool:
    """``value >= limit``, a value that differs from its limit by rounding alone counting as on it."""
    return bool(value >= limit) or math.isclose(value.magnitude, limit.to(value.units).magnitude)


def _compile_wall_shear_dicts_en(self: "ShearWall", force: Forces) -> None:
    """The detail tables of an EN 1992-1-1 wall: the quantities of §6.2 and the limits of §9.6.

    The reinforcement is per unit length of wall, both faces together, in
    cm²/m -- as the EN beam's shear tables write it.
    """
    concrete = _en(self)
    self._materials_shear_wall = {
        "Materials": [
            "Section Label",
            "Concrete strength",
            "Steel reinforcement yield strength",
            "Safety factor for concrete",
            "Safety factor for steel",
            "Design concrete strength",
            "Design steel strength",
        ],
        "Variable": ["", "fck", "fywk", "γc", "γs", "fcd", "fywd"],
        "Value": [
            self.label,
            shown(concrete.f_ck, "stress", False, 2),
            shown(self.steel_bar.f_y, "steel_stress", False, 2),
            concrete.gamma_c,
            self.steel_bar.gamma_s,
            shown(self._f_cd_wall, "stress", False, 2),
            shown(self._f_ywd_wall, "stress", False, 2),
        ],
        "Unit": ["", "MPa", "MPa", "", "", "MPa", "MPa"],
    }
    self._geometry_shear_wall = {
        "Geometry": [
            "Wall thickness",
            "Wall length",
            "Wall height",
            "Gross concrete area",
            "Effective height",
            "Lever arm",
        ],
        "Variable": ["t", "lw", "hw", "Ac", "d", "z"],
        "Value": [
            shown(self.thickness, "length", False, 1),
            shown(self.length, "wall_length", False, 1),
            shown(self.height, "wall_length", False, 1),
            shown(self._A_c_wall, "area", False, 1),
            shown(self._d_wall, "length", False, 1),
            shown(self._z_wall, "length", False, 1),
        ],
        "Unit": [
            unit_label("length", False),
            unit_label("wall_length", False),
            unit_label("wall_length", False),
            unit_label("area", False),
            unit_label("length", False),
            unit_label("length", False),
        ],
    }
    self._forces_shear_wall = {
        "Design forces": ["Axial, positive for compression", "Shear"],
        "Variable": ["NEd", "VEd"],
        "Value": [_kN(self._N_Ed_wall), _kN(self._V_Ed_wall)],
        "Unit": ["kN", "kN"],
    }

    spacing = unit_label("spacing", False)
    has_h, has_v = self._s_h > 0 * mm, self._s_v > 0 * mm
    ratio_ok = self._lw_t_wall >= 4 or math.isclose(self._lw_t_wall, 4)
    A_sh_ok = _at_least(self._A_sh_wall, self._A_sh_req_wall)
    A_sv_ok = _at_least(self._A_sv_wall, self._A_sv_min_wall) and _at_least(self._A_sv_max_wall, self._A_sv_wall)
    s_h_ok = _at_least(self._s_h_max, self._s_h) if has_h else True
    s_v_ok = _at_least(self._s_v_max, self._s_v) if has_v else True
    V_max_ok = bool(self._max_shear_ok_wall)
    V_ok = _at_least(self._V_Rd_wall, self._V_Ed_wall)
    oks = [ratio_ok, A_sh_ok, A_sv_ok, s_h_ok, s_v_ok, V_max_ok, V_ok]
    self._all_wall_shear_checks_passed = all(oks)

    self._data_min_max_wall = {
        "Check": [
            "Length to thickness ratio",
            "Horizontal reinforcement",
            "Vertical reinforcement",
            "Horizontal bar spacing (E.F.)",
            "Vertical bar spacing (E.F.)",
            "Maximum shear capacity",
            "Total shear capacity",
        ],
        "Unit": ["", "cm²/m", "cm²/m", spacing, spacing, "kN", "kN"],
        "Value": [
            round(self._lw_t_wall, 2),
            _per_m(self._A_sh_wall),
            _per_m(self._A_sv_wall),
            shown(self._s_h, "spacing", False, 1) if has_h else 0.0,
            shown(self._s_v, "spacing", False, 1) if has_v else 0.0,
            _kN(self._V_Ed_wall),
            _kN(self._V_Ed_wall),
        ],
        "Min.": [4, _per_m(self._A_sh_req_wall), _per_m(self._A_sv_min_wall), "", "", "", ""],
        "Max.": [
            "",
            "",
            _per_m(self._A_sv_max_wall),
            shown(self._s_h_max, "spacing", False, 1),
            shown(self._s_v_max, "spacing", False, 1),
            _kN(self._V_Rd_max_wall),
            _kN(self._V_Rd_wall),
        ],
        "Ok?": ["✅" if ok else "❌" for ok in oks],
    }
    self._shear_capacity_wall = {
        "Shear strength": [
            "k value",
            "Longitudinal reinforcement ratio",
            "Axial stress",
            "Concrete shear strength",
            "Compression chord coefficient",
            "Strength reduction factor for concrete cracked in shear",
            "Concrete strut angle",
            "Shear reinforcement for strength",
            "Minimum shear reinforcement",
            "Minimum horizontal reinforcement",
            "Steel shear strength",
            "Maximum shear strength",
            "Total shear strength",
            "Demand Capacity Ratio",
        ],
        "Variable": [
            "k",
            "ρl",
            "σcp",
            "VRd,c",
            "αcw",
            "ν1",
            "Θ",
            "Ash,str",
            "Ash,w",
            "Ash,min",
            "VRd,s",
            "VRd,max",
            "VRd",
            "DCR",
        ],
        "Value": [
            round(self._k_wall, 3),
            round(self._rho_l_shear_wall, 4),
            shown(self._sigma_cp_wall, "stress", False, 2),
            _kN(self._V_Rd_c_wall),
            round(self._alpha_cw_wall, 3),
            round(self._nu_1_wall, 3),
            round(math.degrees(self._theta_wall), 1),
            _per_m(self._A_sh_str_wall),
            _per_m(self._A_sh_w_wall),
            _per_m(self._A_sh_min_wall),
            _kN(self._V_Rd_s_wall),
            _kN(self._V_Rd_max_wall),
            _kN(self._V_Rd_wall),
            round(self._DCRv_wall, 3),
        ],
        "Unit": ["", "", "MPa", "kN", "", "", "deg", "cm²/m", "cm²/m", "cm²/m", "kN", "kN", "kN", ""],
    }


def _compile_results_wall_shear_en(self: "ShearWall", force: Forces) -> pd.DataFrame:
    """One row of the EN 1992-1-1 wall shear table: the areas of §9.6 and the resistances of §6.2."""
    row = {
        "Label": self.label,
        "Comb.": force.label,
        "Ash,min": _per_m(self._A_sh_min_wall),
        "Ash,req": _per_m(self._A_sh_req_wall),
        "Ash": _per_m(self._A_sh_wall),
        "Asv,min": _per_m(self._A_sv_min_wall),
        "Asv": _per_m(self._A_sv_wall),
        "NEd": _kN(self._N_Ed_wall),
        "VEd": _kN(self._V_Ed_wall),
        "VRd,c": _kN(self._V_Rd_c_wall),
        "VRd,s": _kN(self._V_Rd_s_wall),
        "VRd": _kN(self._V_Rd_wall),
        "VRd,max": _kN(self._V_Rd_max_wall),
        "VEd≤VRd,max": bool(self._max_shear_ok_wall),
        "VEd≤VRd": _at_least(self._V_Rd_wall, self._V_Ed_wall),
        "DCR": round(self._DCRv_wall, 3),
    }
    return pd.DataFrame([row])


def _units_row_en(self: "ShearWall") -> Dict[str, str]:
    area = unit_label("per_length", False)
    force = unit_label("force", False)
    return {
        "Label": "",
        "Comb.": "",
        "Ash,min": area,
        "Ash,req": area,
        "Ash": area,
        "Asv,min": area,
        "Asv": area,
        "NEd": force,
        "VEd": force,
        "VRd,c": force,
        "VRd,s": force,
        "VRd": force,
        "VRd,max": force,
        "VEd≤VRd,max": "",
        "VEd≤VRd": "",
        "DCR": "",
    }


# ---------------------------------------------------------------------------
# Which builders serve which code
# ---------------------------------------------------------------------------

#: The wall's counterpart to ``mento.reports.tables._REPORT_BUILDERS``: report
#: content is per code by nature, so each code registers its tables here by
#: title. ``symbols`` are the LaTeX names of the one-line Markdown summary.
_WALL_REPORT_BUILDERS: Dict[str, Dict[str, Any]] = {}


def _register_wall_report_builders(
    title: str,
    *,
    details: Callable[["ShearWall", Forces], None],
    row: Callable[["ShearWall", Forces], pd.DataFrame],
    units_row: Callable[["ShearWall"], Dict[str, str]],
    symbols: Dict[str, str],
) -> None:
    _WALL_REPORT_BUILDERS[title] = {"details": details, "row": row, "units_row": units_row, "symbols": symbols}


def _builders_for(self: "ShearWall") -> Dict[str, Any]:
    try:
        return _WALL_REPORT_BUILDERS[self.concrete.design_code]
    except KeyError:
        raise NotImplementedError(
            f"no wall report tables for design code: {self.concrete.design_code}. "
            f"Registered: {', '.join(sorted(_WALL_REPORT_BUILDERS)) or 'none'}"
        ) from None


# ACI 318-19 and CIRSOC 201-25 share every wall table: the same Chapter 11.
for _aci_title in ("ACI 318-19", "CIRSOC 201-25"):
    _register_wall_report_builders(
        _aci_title,
        details=_compile_wall_shear_dicts,
        row=_compile_results_wall_shear,
        units_row=_units_row_aci,
        symbols={"rho_h": "\\rho_t", "rho_v": "\\rho_l", "demand": "V_u", "capacity": "\\phi V_n"},
    )

_register_wall_report_builders(
    "EN 1992-2004",
    details=_compile_wall_shear_dicts_en,
    row=_compile_results_wall_shear_en,
    units_row=_units_row_en,
    symbols={"rho_h": "\\rho_h", "rho_v": "\\rho_v", "demand": "V_{Ed}", "capacity": "V_{Rd}"},
)
