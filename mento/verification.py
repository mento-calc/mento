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
    if value is not None and (value < 0 or value % 2):
        raise ValueError(
            f"{'legs' if legs is not None else 'n_legs'} must be non-negative and even: "
            "odd legs and individual crosstie anchorage are not modelled yet."
        )
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
                    "EN footing sections with axial force are not supported yet. Supply zero axial force or use a model that includes its effects."
                )
            )


def verification_status(beam: RectangularBeam) -> dict[str, str]:
    """Resistencia de las combinaciones y detallado modelado, sin aprobado global."""
    flexure, shear = beam.flexure_checks, beam.shear_checks
    strength_failed = any(not item.complies for item in flexure) or any(item.DCR > 1 for item in shear)
    warnings = beam.warnings
    outside = {"axial_load_beyond_beam", "force_component_not_checked"}
    unknown_dcr = any(not math.isfinite(item.DCR) for item in shear) or any(
        not math.isfinite(face.DCR) for item in flexure for face in (item.bottom, item.top)
    )
    strength_pending = not flexure or not shear or unknown_dcr or any(w.code in outside for w in warnings)
    resistance = "failed" if strength_failed else "pending" if strength_pending else "passed"
    detail_warnings = [w for w in warnings if w.code not in outside]
    pending = [w for w in detail_warnings if "pending" in w.code or "not_verified" in w.code or "unsupported" in w.code]
    failed = [w for w in detail_warnings if w not in pending]
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
            geometry = build_cage_detailing(beam)
            cage_pending = not geometry.bend_supported
        except CageDetailingError:
            cage_failed = True
    detail_failed = bool(failed) or compression_failed or cage_failed
    detail_pending = bool(pending) or compression_pending or cage_pending or not flexure or not shear
    detailing = "failed" if detail_failed else "pending" if detail_pending else "passed"
    return {"resistance": resistance, "detailing": detailing}


def status_text(status: str) -> str:
    return translate({"passed": "Pass (modelled checks)", "failed": "Fail", "pending": "Pending"}[status])
