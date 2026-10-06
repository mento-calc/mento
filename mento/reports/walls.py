"""Notebook views and Word reports for a shear wall.

The wall's counterpart to :mod:`mento.reports.views` and
:mod:`mento.reports.documents`. Both media live in one module here because the
wall's presentation is small enough that splitting it would cost more than it
explains.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional, cast

import pandas as pd
from IPython.display import Markdown, display
from mento.units import Quantity

from mento._version import __version__ as MENTO_VERSION
from mento.i18n import get_language, translate
from mento.material import Concrete_ACI_318_19
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
    if not self._shear_wall_checked:
        self._md_shear_results = "Shear results are not available."
        return None

    details = self._limiting_case_shear_details or {}
    capacity = details.get("shear_capacity", {})
    min_max = details.get("min_max", {})
    forces_dict = details.get("forces", {})
    if not capacity:
        self._md_shear_results = "No shear to check."
        _show(self._md_shear_results)
        return None

    formatter = Formatter()
    dcr = capacity["Value"][-1]
    phi_Vn = capacity["Value"][2]
    Vu = forces_dict["Value"][0]
    rho_t = min_max["Value"][0]
    rho_l = min_max["Value"][1]
    checks_pass = details.get("checks_pass", False)
    warning = "⚠️ Some checks failed, see detailed results." if not checks_pass else ""

    imperial = self.concrete.is_imperial
    rebar_h = mesh_callout(self._d_b_h, self._s_h, imperial) if self._s_h.magnitude > 0 else "not assigned"
    rebar_v = mesh_callout(self._d_b_v, self._s_v, imperial) if self._s_v.magnitude > 0 else "not assigned"
    force_unit = unit_label("force", imperial)

    markdown_content = (
        f"Horizontal rebar: {rebar_h}, $\\rho_t$={rho_t}, "
        f"Minimum vertical rebar: {rebar_v}, $\\rho_l$={rho_l}, "
        f"$V_u$={Vu} {force_unit}, $\\phi V_n$={phi_Vn} {force_unit} → "
        f"{formatter.DCR(dcr)} {warning}"
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
    _compile_wall_shear_dicts(self, force)
    return _compile_results_wall_shear(self, force)


def _compile_wall_shear_dicts(self: "ShearWall", force: Forces) -> None:
    """Populate result dicts used by detailed output methods."""
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
    """Build a one-row DataFrame for this force combination."""
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
