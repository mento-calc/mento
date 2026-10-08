"""Estados de resistencia y detallado separados, sin modificar el diseño."""

from __future__ import annotations

import math
from numbers import Integral
from typing import TYPE_CHECKING, Any, Sequence

from mento.i18n import translate

if TYPE_CHECKING:
    from mento.beam import RectangularBeam
    from mento.forces import Forces


def resolve_legs(legs: int | None, n_legs: int | None) -> int | None:
    """Alias preferido, sin aceptar cantidades contradictorias ni trabas ficticias."""
    for name, value in (("legs", legs), ("n_legs", n_legs)):
        if value is not None and (isinstance(value, bool) or not isinstance(value, Integral)):
            raise TypeError(f"{name} must be an integer.")
    if legs is not None and n_legs is not None and legs != n_legs:
        raise ValueError("legs and n_legs must agree when both are provided.")
    value = legs if legs is not None else n_legs
    if value is not None and (value < 0 or value == 1):
        raise ValueError("legs/n_legs: At least two legs are needed for the perimeter stirrup.")
    return value


def normalize_leg_column(frame: Any) -> Any:
    """Conservar legs en la entrada y normalizar el alias interno n_legs."""
    if "legs" not in frame.columns:
        return frame
    import pandas as pd

    if pd.notna(frame.iloc[0]["legs"]) and frame.iloc[0]["legs"] != "":
        raise ValueError("legs is a count and must have a blank units cell.")
    out = frame.copy()
    canonical: list[int | None] = []
    for index, row in out.iloc[1:].iterrows():
        values: list[int | None] = []
        for name in ("legs", "n_legs"):
            value = row.get(name)
            if pd.isna(value) or value == "":
                values.append(None)
                continue
            if isinstance(value, bool) or type(value).__name__ == "bool_":
                raise TypeError(f"{name} must be an integer (row {index}).")
            try:
                number = float(value)
            except (ValueError, TypeError) as error:
                raise ValueError(f"{name} must be an integer (row {index}).") from error
            if not number.is_integer():
                raise ValueError(f"{name} must be a finite integer (row {index}).")
            values.append(int(number))
        canonical.append(resolve_legs(*values))
    if "n_legs" in out.columns and pd.notna(out.iloc[0]["n_legs"]) and out.iloc[0]["n_legs"] != "":
        raise ValueError("n_legs is a count and must have a blank units cell.")
    out["n_legs"] = ["", *canonical]
    return out


def validate_supported_forces(beam: RectangularBeam, forces: Sequence[Forces]) -> None:
    """Rechazo de alcance Mento; no se afirma una prohibición del Eurocódigo."""
    if beam.concrete.design_code == "EN 1992-2004" and getattr(beam, "support", None) == "soil":
        if any(force.N_x.magnitude != 0 for force in forces):
            raise NotImplementedError(
                translate(
                    "Mento does not yet model axial force in EN footings (a Mento limitation, not a Eurocode prohibition). Omitting it is conservative only for compression; with tension, verify outside Mento."
                )
            )


WARNING_CATEGORY: dict[str, str] = {
    "transverse_legs_added_for_compression_support": "pending",
    "open_leg_anchorage_outside_model": "informative",
    "crosstie_alternation_required": "informative",
    "compression_detailing_en_pending": "pending",
    "cage_detailing_pending": "pending",
    "compression_detailing_failed": "failed",
    "compression_detailing_pending": "pending",
    "skin_reinforcement_required": "informative",
    "skin_reinforcement_failed": "failed",
    "skin_reinforcement_pending": "pending",
    "skin_tension_case_pending": "pending",
    "skin_detailing_invalid": "pending",
    "skin_detailing_pending": "pending",
    "skin_reinforcement_unsupported": "pending",
    "skin_detailing_infeasible": "failed",
    "cage_detailing_infeasible": "failed",
    "skin_distribution_review": "informative",
    "skin_en_required": "informative",
    "skin_en_service_pending": "pending",
    "skin_en_axial_unsupported": "pending",
    "skin_en_surface_pending": "pending",
    "As_below_min": "resistance",
    "As_above_max": "resistance",
    "not_tension_controlled": "resistance",
    "clear_spacing_below_min": "failed",
    "bar_spacing_below_min": "failed",
    "bar_spacing_exceeds_max": "failed",
    "bars_do_not_fit": "failed",
    "As_below_required": "resistance",
    "stirrups_required": "resistance",
    "force_component_not_checked": "resistance",
    "Av_below_min": "resistance",
    "stirrup_spacing_exceeds_max_l": "failed",
    "stirrup_spacing_exceeds_max_w": "failed",
    "shear_exceeds_section_limit": "resistance",
    "mesh_ratio_below_min_h": "resistance",
    "mesh_ratio_below_min_v": "resistance",
    "mesh_spacing_exceeds_max_h": "failed",
    "mesh_spacing_exceeds_max_v": "failed",
    "stirrup_spacing_exceeds_compression_support": "failed",
    "stirrup_diameter_below_compression_support": "failed",
    "stirrups_required_for_compression_support": "failed",
    "axial_load_beyond_beam": "resistance",
    "stirrup_spacing_exceeds_max": "failed",
    "mesh_ratio_below_min": "resistance",
    "mesh_spacing_exceeds_max": "failed",
}


def warning_category(code: str) -> str:
    """Mapa explícito; un código nuevo no puede aprobarse silenciosamente."""
    return WARNING_CATEGORY.get(code, "pending")


def verification_status(beam: RectangularBeam) -> dict[str, str]:
    """Resistencia de las combinaciones y detallado modelado, sin aprobado global."""
    flexure, shear = beam.flexure_checks, beam.shear_checks
    strength_failed = any(not item.complies for item in flexure) or any(item.DCR > 1 for item in shear)
    warnings = beam.warnings
    outside = {"axial_load_beyond_beam", "force_component_not_checked"}
    strength_failed = strength_failed or any(
        warning_category(w.code) == "resistance" and w.code not in outside for w in warnings
    )
    unknown_dcr = any(not math.isfinite(item.DCR) for item in shear) or any(
        not math.isfinite(face.DCR) for item in flexure for face in (item.bottom, item.top)
    )
    strength_pending = not flexure or not shear or unknown_dcr or any(w.code in outside for w in warnings)
    resistance = "failed" if strength_failed else "pending" if strength_pending else "passed"
    pending = [w for w in warnings if warning_category(w.code) == "pending"]
    failed = [w for w in warnings if warning_category(w.code) == "failed"]
    compression = getattr(beam, "compression_detailing", None)
    if compression is not None:
        compression_failed = compression.status == "failed"
        compression_pending = compression.status == "pending"
    else:
        compression_failed = False
        compression_pending = bool(getattr(beam, "_compression_faces", set()))
    cage_failed = False
    cage_pending = False
    if not beam._stirrups_optional and beam._stirrup_n:
        from mento.cage_detailing import CageDetailingError, build_cage_detailing

        try:
            geometry = build_cage_detailing(beam, include_skin=False)
            cage_pending = not geometry.bend_supported
        except CageDetailingError as error:
            cage_pending = error.reason in ("unsupported_bend", "compression_support_search")
            cage_failed = not cage_pending
    detail_failed = bool(failed) or compression_failed or cage_failed
    detail_pending = bool(pending) or compression_pending or cage_pending or not flexure or not shear
    detailing = "failed" if detail_failed else "pending" if detail_pending else "passed"
    return {"resistance": resistance, "detailing": detailing}


def status_text(status: str) -> str:
    return translate({"passed": "Pass (modelled checks)", "failed": "Fail", "pending": "Pending"}[status])
