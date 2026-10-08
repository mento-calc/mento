"""Longitudinal skin-steel proposals, ACI 318-19 / CIRSOC 201-25 §9.7.2.3.

This steel controls web cracking. It is never credited to moment or shear
resistance, and does not make a sectional model a strut-and-tie design.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from numbers import Integral
from typing import TYPE_CHECKING, Literal

from mento.codes.registry import design_code
from mento.design_results import GRID, transverse_layout
from mento.section_geometry import BarPosition, SectionGeometry
from mento.units import Quantity, mm

if TYPE_CHECKING:
    from mento.beam import RectangularBeam


@dataclass(frozen=True)
class SkinDistributionReview:
    tension_face: str
    combination: str
    rows_per_side: int
    maximum_interval: Quantity


@dataclass(frozen=True)
class ManualSkinRebar:
    """Cantidad por cada lateral; posición referida a la altura del alma."""

    db_piel: Quantity
    cant_piel_cara: int
    posicion: Literal["top", "bottom", "total"]

    def __post_init__(self) -> None:
        if not isinstance(self.db_piel, Quantity) or not self.db_piel.check("[length]"):
            raise ValueError("db_piel must be a length quantity.")
        diameter = float(self.db_piel.to(mm).magnitude)
        if not math.isfinite(diameter) or diameter <= 0:
            raise ValueError("db_piel must be finite and positive.")
        if (
            isinstance(self.cant_piel_cara, bool)
            or not isinstance(self.cant_piel_cara, Integral)
            or self.cant_piel_cara < 0
        ):
            raise ValueError("cant_piel_cara must be a non-negative integer.")
        if self.posicion not in ("top", "bottom", "total"):
            raise ValueError("posicion must be top, bottom or total.")


@dataclass(frozen=True)
class SkinCheckZone:
    tension_face: str
    lower: Quantity
    upper: Quantity
    combination: str = ""


@dataclass(frozen=True)
class SkinReinforcementRequirement:
    """Requirement, not a certificate that a provided cage complies.

    status is required, not_required, pending, unsupported or not_applicable.
    Pending means flexure, a tension case or independent EN service inputs
    are missing; pending_reason identifies which. Unsupported is NOT an exemption.
    n_per_side counts supplementary bars on EACH lateral face, counting the
    shared mid-height bar once when both bending signs occur. spacing is the
    uniform spacing within each ACI h/2 zone, including its boundary gap.
    EN supplies explicit rows, a minimum area and an adjusted diameter limit;
    its selected diameter route has no independent s_max.
    Geometry and fit are verified by beam.detailing_geometry, which may raise.
    """

    status: Literal["required", "not_required", "pending", "unsupported", "not_applicable"]
    threshold: Quantity | None = None
    tension_faces: tuple[str, ...] = ()
    d_b: Quantity | None = None
    side_cover: Quantity | None = None
    s_max: Quantity | None = None
    spacing: Quantity | None = None
    n_per_side: int = 0
    # EN uses the diameter route, not an ACI-style spacing cap.
    rows: tuple[Quantity, ...] = ()
    area_min_per_side: Quantity | None = None
    area_per_side: Quantity | None = None
    diameter_max: Quantity | None = None
    pending_reason: str | None = None
    # Informative layout review: (tension face, rows in its service zone,
    # largest vertical interval, including gaps to the zone boundaries).
    # This is not an additional code spacing limit or a crack-width check.
    distribution_reviews: tuple[SkinDistributionReview, ...] = ()
    check_zones: tuple[SkinCheckZone, ...] = ()
    manual: bool = False
    failures: tuple[str, ...] = ()


def skin_requirement(beam: RectangularBeam) -> SkinReinforcementRequirement:
    """Evaluate supplementary skin steel, keeping its failures distinguishable."""
    from mento.cage_detailing import CageDetailingError

    try:
        requirement = _skin_requirement(beam)
        return _manual_skin_requirement(beam, requirement) if beam.skin_rebar is not None else requirement
    except CageDetailingError as error:
        raise CageDetailingError(str(error), reason="skin") from error


def _skin_requirement(beam: RectangularBeam) -> SkinReinforcementRequirement:
    if transverse_layout(beam) == GRID:
        return SkinReinforcementRequirement("not_applicable")
    code = design_code(beam.concrete)
    if code.skin_requirement is not None:
        return code.skin_requirement(beam)
    if code.skin_reinforcement_threshold is None or code.max_skin_bar_spacing is None:
        return SkinReinforcementRequirement("unsupported")
    threshold = code.skin_reinforcement_threshold(beam.concrete)
    if beam.height <= threshold:
        return SkinReinforcementRequirement("not_required", threshold)
    if not beam._flexure_checked or not beam.flexure_checks:
        return SkinReinforcementRequirement("pending", threshold)
    # Demand/capacity ratios belong to every checked combination, so reversals
    # are covered even when the last combination puts only one face in tension.
    faces = tuple(
        face for face in ("bottom", "top") if any(getattr(check, face).DCR > 0 for check in beam.flexure_checks)
    )
    if not faces:
        return SkinReinforcementRequirement("pending", threshold, pending_reason="no_tension_case")
    settings = beam.settings
    assert settings is not None
    manual = beam.skin_rebar
    diameter = manual.db_piel if manual is not None else settings.skin_bar_diameter
    from mento.cage_detailing import CageDetailingError

    if not isinstance(diameter, Quantity) or not diameter.check("[length]"):
        raise CageDetailingError("skin_bar_diameter must be a length quantity.")
    d = float(diameter.to(mm).magnitude)
    if not math.isfinite(d) or d <= 0 or diameter < settings.minimum_longitudinal_diameter:
        raise CageDetailingError("skin_bar_diameter must be finite, positive and meet minimum_longitudinal_diameter.")
    # Placed just INSIDE the perimeter stirrup. With no stirrups, the cover
    # reserved by the flexural model is retained, making the gap explicit.
    cover = beam.c_c + beam._stirrup_d_b
    cap = code.max_skin_bar_spacing(beam, cover)
    limit = float(cap.to(mm).magnitude)
    if not math.isfinite(limit) or limit <= 0:
        raise CageDetailingError("No positive skin-bar spacing is permitted for this cover and steel grade.")
    # ACI Fig. R9.7.2.3 / CIRSOC Fig. C 9.7.2.3 show the first interval
    # from the lateral tension bar, not the concrete face. Start at the
    # innermost tension layer that has lateral bars, and include h/2.
    geometry = beam.section_geometry
    midpoint = float((beam.height / 2).to(mm).magnitude)
    rows: set[float] = set()
    spacings = []
    zones = []
    for face in faces:
        second = geometry.bars_on(face, layer=2)
        anchor_bars = second if len(second) >= 2 else geometry.bars_on(face, layer=1)
        if not anchor_bars:
            raise CageDetailingError("Skin reinforcement needs a lateral tension-layer anchor.")
        level = (max if face == "bottom" else min)(float(bar.y.to(mm).magnitude) for bar in anchor_bars)
        span = abs(midpoint - level)
        if span <= 0 or (face == "bottom" and level >= midpoint) or (face == "top" and level <= midpoint):
            raise CageDetailingError("The lateral tension layer must lie within its tension half.")
        zones.append(SkinCheckZone(face, min(level, midpoint) * mm, max(level, midpoint) * mm))
        count = max(1, math.ceil(span / limit - 1e-12))
        pitch = span / count
        spacings.append(pitch)
        direction = 1 if face == "bottom" else -1
        rows.update(round(level + direction * pitch * i, 9) for i in range(1, count + 1))
    return SkinReinforcementRequirement(
        "required",
        threshold,
        faces,
        diameter,
        cover,
        cap,
        max(spacings) * mm,
        len(rows),
        rows=tuple(y * mm for y in sorted(rows)),
        check_zones=tuple(zones),
    )


def _manual_skin_requirement(beam: RectangularBeam, req: SkinReinforcementRequirement) -> SkinReinforcementRequirement:
    """Comprobar la cantidad ingresada sin aumentarla ni cambiar su zona."""
    supplied = beam.skin_rebar
    assert supplied is not None
    if req.status == "not_applicable":
        return replace(req, manual=True)
    geometry = beam.section_geometry
    diameter = supplied.db_piel
    cover = beam.c_c + beam._stirrup_d_b
    inset = float((cover + diameter / 2).to(mm).magnitude)
    height = float(beam.height.to(mm).magnitude)

    def anchor(face: str) -> float:
        second = geometry.bars_on(face, layer=2)
        bars = second if len(second) >= 2 else geometry.bars_on(face, layer=1)
        if bars:
            return (max if face == "bottom" else min)(float(bar.y.to(mm).magnitude) for bar in bars)
        return inset if face == "bottom" else height - inset

    low, high = anchor("bottom"), anchor("top")
    count = int(supplied.cant_piel_cara)
    midpoint = height / 2
    if supplied.posicion == "bottom":
        high = midpoint
    elif supplied.posicion == "top":
        low = midpoint
    failures = []
    if high <= low:
        failures.append("No height is available for the supplied skin zone.")
    settings = beam.settings
    assert settings is not None
    minimum_pitch = float((diameter + max(settings.clear_spacing, settings.vibrator_size, diameter)).to(mm).magnitude)
    maximum_count = max(0, math.floor(max(0.0, high - low) / minimum_pitch) + 1)
    if count > maximum_count:
        return replace(
            req,
            d_b=diameter,
            side_cover=cover,
            n_per_side=count,
            spacing=0 * mm,
            rows=(),
            manual=True,
            failures=("The supplied skin bars cannot fit with the required clear spacing.",),
        )
    rows: tuple[float, ...]
    if count == 0:
        rows = ()
        pitch = 0.0
    elif supplied.posicion == "total":
        pitch = (high - low) / (count + 1)
        rows = tuple(low + pitch * i for i in range(1, count + 1))
    else:
        pitch = (high - low) / count
        rows = (
            tuple(low + pitch * i for i in range(1, count + 1))
            if supplied.posicion == "bottom"
            else tuple(high - pitch * i for i in range(1, count + 1))
        )
    rows = tuple(sorted(rows))
    area = count * math.pi * float(diameter.to(mm).magnitude) ** 2 / 4 * mm**2
    if req.area_min_per_side is not None and area < req.area_min_per_side - 1e-8 * mm**2:
        failures.append("The supplied skin area per lateral face is insufficient.")
    reviews = []
    if req.status == "required":
        if supplied.posicion != "total":
            for face in req.tension_faces:
                if face != supplied.posicion:
                    failures.append(f"The supplied skin does not cover the {face} tension zone.")
        if req.diameter_max is not None and diameter > req.diameter_max:
            failures.append("The supplied skin diameter exceeds the supported EN diameter limit.")
        for zone in req.check_zones:
            a, b = float(zone.lower.to(mm).magnitude), float(zone.upper.to(mm).magnitude)
            inside = tuple(y for y in rows if a - 1e-8 <= y <= b + 1e-8)
            levels = (a, *inside, b)
            gap = max(right - left for left, right in zip(levels, levels[1:])) * mm
            if not inside:
                failures.append(f"The supplied skin does not cover the {zone.tension_face} tension zone.")
            if req.s_max is not None and gap > req.s_max + 1e-8 * mm:
                failures.append(f"The supplied skin spacing exceeds the limit in the {zone.tension_face} tension zone.")
            zone_area = len(inside) * math.pi * float(diameter.to(mm).magnitude) ** 2 / 4 * mm**2
            if req.area_min_per_side is not None and zone_area < req.area_min_per_side - 1e-8 * mm**2:
                failures.append(f"The supplied skin area is insufficient in the {zone.tension_face} tension zone.")
            if req.area_min_per_side is not None:
                reviews.append(SkinDistributionReview(zone.tension_face, zone.combination, len(inside), gap))
    return replace(
        req,
        d_b=diameter,
        side_cover=cover,
        n_per_side=count,
        spacing=pitch * mm,
        rows=tuple(y * mm for y in rows),
        area_per_side=area,
        manual=True,
        failures=tuple(dict.fromkeys(failures)),
        distribution_reviews=tuple(reviews),
    )


def add_skin_bars(beam: RectangularBeam, geometry: SectionGeometry) -> SectionGeometry:
    """Add skin bars, marking any infeasibility as specific to the skin proposal."""
    from mento.cage_detailing import CageDetailingError

    try:
        return _add_skin_bars(beam, geometry)
    except CageDetailingError as error:
        raise CageDetailingError(str(error), reason="skin") from error


def _add_skin_bars(beam: RectangularBeam, geometry: SectionGeometry) -> SectionGeometry:
    """Supplementary bars in the required zones; reject clashes rather than hide them.

    ACI starts above the lateral tension-layer bar and includes a mid-height bar; each
    gap meets its spacing cap. EN supplies explicit service-zone rows.
    The flexural layers are not credited toward the supplementary proposal.
    Reversal envelopes share rows rather than duplicating or clashing them.
    """
    from mento.cage_detailing import CageDetailingError

    req = skin_requirement(beam)
    if req.failures and not req.rows:
        raise CageDetailingError(" ".join(req.failures), reason="skin")
    if req.status != "required" and not req.manual:
        return geometry
    if not req.rows:
        return geometry
    assert req.d_b is not None and req.side_cover is not None and req.spacing is not None
    unit = geometry.width.units
    diameter = req.d_b.to(unit)
    inset: Quantity = req.side_cover.to(unit) + diameter / 2
    settings = beam.settings
    assert settings is not None

    if 2 * inset + diameter + settings.clear_spacing > geometry.width:
        raise CageDetailingError("The two lateral skin bars cannot fit within the section width.")
    # Round only the key used to merge the common midpoint across units.
    if not req.rows:
        raise CageDetailingError("A required skin proposal must specify its physical rows.", reason="skin")
    rows = {float(y.to(mm).magnitude) for y in req.rows}
    ordered_rows = sorted({round(y, 9) for y in rows})
    bars = tuple(
        BarPosition(x, (y * mm).to(unit), diameter, side, 0, 0)
        for y in ordered_rows
        for x, side in ((inset, "left"), (geometry.width - inset, "right"))
    )
    existing = geometry.bars + geometry.mounting_bars
    for index, bar in enumerate(bars):
        if not inset <= bar.y <= geometry.height - inset:
            raise CageDetailingError("Skin bars cannot meet the cover at the required spacing.")
        for other in (*existing, *bars[index + 1 :]):
            distance = (
                math.hypot(float((bar.x - other.x).to(mm).magnitude), float((bar.y - other.y).to(mm).magnitude)) * mm
            )
            minimum = (bar.d_b + other.d_b) / 2 + max(
                settings.clear_spacing, settings.vibrator_size, bar.d_b, other.d_b
            )
            if distance < minimum - 1e-8 * mm:
                raise CageDetailingError("Skin reinforcement leaves insufficient clear spacing to longitudinal bars.")
    return replace(geometry, skin_bars=bars)
