"""EN 1992-1-1:2004 §7.3.3(3), longitudinal web steel in pure bending.

Uses §7.3.2 Eq. (7.1) and the DIAMETER route of Table 7.2N / Eq. (7.7N).
Service stress and the neutral-axis envelope are explicit SLS inputs: ULS
forces and an ultimate compression-block limit must never substitute for them.
Annex J surface mesh is a separate detail outside the links.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from mento.codes.en_1992_2004.equations.flexure import crack_control_min_reinforcement
from mento.codes.en_1992_2004.equations.skin import adjusted_diameter, tabulated_skin_diameter
from mento.skin_reinforcement import SkinCheckZone, SkinDistributionReview, SkinReinforcementRequirement
from mento.units import MPa, Quantity, mm

if TYPE_CHECKING:
    from mento.beam import RectangularBeam


def _length(value: object, name: str) -> float:
    from mento.cage_detailing import CageDetailingError

    if not isinstance(value, Quantity) or not value.check("[length]"):
        raise CageDetailingError(f"{name} must be a length quantity.")
    result = float(value.to(mm).magnitude)
    if not math.isfinite(result) or result <= 0:
        raise CageDetailingError(f"{name} must be finite and positive.")
    return result


def warnings(beam: RectangularBeam, req: SkinReinforcementRequirement | None) -> list:
    """EN warnings and informative Annex J review, independent of web fit.

    J.1(1) covers bars or equivalent bundles >32 mm; J.1(3) covers
    cover >70 mm. These are strict thresholds in the base text. Bundles
    are not modelled and must be reviewed separately. Annex J is informative;
    National Annex choices affect its application and areas. Section 8.8(8)
    separately specifies 0.01*A_ct,ext perpendicular and 0.02*A_ct,ext
    parallel to large bars. Neither surface mesh is designed here.
    """
    from mento.design_warnings import _Raw

    result = []
    layers = beam.reinforcement.bottom.layers + beam.reinforcement.top.layers
    if beam.c_c > 70 * mm or any(layer.d_b > 32 * mm for layer in layers):
        result.append(_Raw("skin_en_surface_pending", {}))
    if req is None:
        return result
    if req.pending_reason == "service":
        result.append(_Raw("skin_en_service_pending", {}))
    elif req.pending_reason == "axial":
        result.append(_Raw("skin_en_axial_unsupported", {}))
    elif req.status == "required":
        result.append(_Raw("skin_en_required", {"area": req.area_min_per_side, "diameter": req.diameter_max}))
    elif req.status == "unsupported":
        result.append(_Raw("skin_reinforcement_unsupported", {}))
    return result


def requirement(beam: RectangularBeam) -> SkinReinforcementRequirement:
    """Web steel — EN 1992-1-1:2004 §7.3.3(3), for pure rectangular bending.

    Minimum area: §7.3.2(2), Eq. (7.1), with kc=0.4 from Eq. (7.2),
    k=0.5 and sigma_s=f_yk as specified by §7.3.3(3). Mento splits the
    total area equally between the two sides. Diameter control uses
    §7.3.3(2), Table 7.2N and Eq. (7.7N): §7.3.3(3) explicitly asks
    to assume pure tension and half the main service steel stress here,
    although the beam itself is in bending. Rounding stress up to a table
    row and selecting an equally spaced grid are Mento detailing choices.
    This is distinct from informative Annex J, §J.1(1)-(3), surface mesh.
    """
    from mento.cage_detailing import CageDetailingError
    from mento.material import Concrete_EN_1992_2004

    threshold = 1000 * mm
    if beam.height < threshold:
        return SkinReinforcementRequirement("not_required", threshold)
    if not beam._flexure_checked or not beam.flexure_checks:
        return SkinReinforcementRequirement("pending", threshold)
    faces = tuple(face for face in ("bottom", "top") if any(getattr(c, face).DCR > 0 for c in beam.flexure_checks))
    if any(check.has_axial_force for check in beam.flexure_checks):
        return SkinReinforcementRequirement("unsupported", threshold, faces, pending_reason="axial")
    if not faces:
        return SkinReinforcementRequirement("pending", threshold, pending_reason="no_tension_case")
    concrete = beam.concrete
    assert isinstance(concrete, Concrete_EN_1992_2004)
    settings = beam.settings
    assert settings is not None
    manual = beam.skin_rebar
    skin_diameter = manual.db_piel if manual is not None else settings.skin_bar_diameter
    h = float(beam.height.to(mm).magnitude)
    width = float(beam.width.to(mm).magnitude)
    fy = float(beam.steel_bar.f_y.to(MPa).magnitude)
    fct = float(concrete.f_ctm.to(MPa).magnitude)
    # Pure rectangular bending: kc=0.4 and Act=b*h/2 BEFORE cracking.
    # §7.3.3(3) replaces k with 0.5 and sigma_s with characteristic fy.
    # Divide the total additional area equally between the two lateral faces.
    amin = crack_control_min_reinforcement(0.4, 0.5, fct, width * h / 2, fy) / 2
    cases = tuple(case for case in beam.skin_service_cases if case.tension_face in faces)
    if any(not any(case.tension_face == face for case in cases) for face in faces):
        return SkinReinforcementRequirement(
            "pending", threshold, faces, area_min_per_side=amin * mm**2, pending_reason="service"
        )
    diameter = _length(skin_diameter, "skin_bar_diameter")
    if skin_diameter < settings.minimum_longitudinal_diameter:
        raise CageDetailingError("skin_bar_diameter is below minimum_longitudinal_diameter.")
    wk = _length(settings.skin_crack_width, "skin_crack_width")
    bars = beam.section_geometry.bars
    # h-d is the centroid distance of the OUTERMOST tension layer.
    # hcr=h/2 is the pure-bending tensile depth immediately BEFORE cracking;
    # x above describes the cracked SERVICE section and is not hcr.
    caps = []
    zones = []
    for case in cases:
        face = case.tension_face
        main_stress = float(case.steel_stress.to(MPa).magnitude)
        if main_stress > fy:
            raise CageDetailingError(f"Skin service case {case.label!r}: steel stress exceeds f_yk.")
        try:
            phi_star = tabulated_skin_diameter(main_stress, wk)
        except ValueError as error:
            raise CageDetailingError(f"Skin service case {case.label!r}: {error}") from error
        x = _length(case.neutral_axis, "neutral_axis")
        if x >= h:
            raise CageDetailingError(
                "SkinServiceCase.neutral_axis must be inside the section, measured from compression."
            )
        outer = [bar for bar in bars if bar.face == face and bar.layer == 1]
        if not outer:
            raise CageDetailingError("EN skin reinforcement needs an outer tension layer.")
        total = sum(float(bar.d_b.to(mm).magnitude) ** 2 for bar in outer)
        level = sum(float(bar.y.to(mm).magnitude) * float(bar.d_b.to(mm).magnitude) ** 2 for bar in outer) / total
        edge = level if face == "bottom" else h - level
        bending_cap = adjusted_diameter(phi_star, fct, h / 2, edge)
        # Mento's conservative interpretation for lateral web reinforcement:
        # also treat the web as a tie across its width, using the centroid of
        # the ACTUAL skin bar rather than only the main tension layer. The
        # minimum of these interpretations is a project rule, not an extra
        # expression printed by EN for skin steel. Neither calculates w_k.
        skin_edge = float((beam.c_c + beam._stirrup_d_b).to(mm).magnitude) + diameter / 2
        tie_cap = adjusted_diameter(phi_star, fct, width, skin_edge)
        caps.append(min(bending_cap, tie_cap))
        neutral = h - x if face == "bottom" else x
        low, high = sorted((level, neutral))
        if (face == "bottom" and neutral <= level) or (face == "top" and neutral >= level):
            raise CageDetailingError("The service neutral axis must lie above the tension layer toward compression.")
        zones.append((low, high))
    dmax = min(caps)
    check_zones = tuple(
        SkinCheckZone(case.tension_face, a * mm, b * mm, case.label) for case, (a, b) in zip(cases, zones)
    )
    if beam.skin_rebar is not None:
        return SkinReinforcementRequirement(
            "required",
            threshold,
            faces,
            skin_diameter,
            beam.c_c + beam._stirrup_d_b,
            area_min_per_side=amin * mm**2,
            diameter_max=dmax * mm,
            check_zones=check_zones,
        )
    if diameter > dmax + 1e-9:
        raise CageDetailingError("skin_bar_diameter exceeds Mento's conservative EN diameter-route proposal.")
    abar = math.pi * diameter**2 / 4
    minimum_count = max(1, math.ceil(amin / abar - 1e-12))
    low, high = min(z[0] for z in zones), max(z[1] for z in zones)
    # One uniform grid across the union avoids clashing independent grids
    # when both bending signs occur. Extra bars in compression are harmless.
    clear = max(
        float(settings.clear_spacing.to(mm).magnitude), float(settings.vibrator_size.to(mm).magnitude), diameter
    )
    max_count = max(1, math.floor((high - low) / (diameter + clear)) + 1)
    for count in range(minimum_count, max_count + 1):
        spacing = (high - low) / (count + 1)
        rows = tuple(low + spacing * i for i in range(1, count + 1))
        if all(sum(a - 1e-9 <= y <= b + 1e-9 for y in rows) >= minimum_count for a, b in zones):
            break
    else:
        raise CageDetailingError("The EN skin-steel envelope cannot be distributed.")
    # Keep the diameter-route proposal, including a single row where its
    # minimum area permits it. Expose the actual distribution for engineering
    # review; do not invent a spacing limit from the alternative Table 7.3N.
    reviews = []
    for case, (a, b) in zip(cases, zones):
        zone_rows = tuple(y for y in rows if a - 1e-9 <= y <= b + 1e-9)
        levels = (a, *zone_rows, b)
        largest_gap = max(right - left for left, right in zip(levels, levels[1:]))
        reviews.append(SkinDistributionReview(case.tension_face, case.label, len(zone_rows), largest_gap * mm))
    return SkinReinforcementRequirement(
        "required",
        threshold,
        faces,
        skin_diameter,
        beam.c_c + beam._stirrup_d_b,
        spacing=spacing * mm,
        n_per_side=count,
        rows=tuple(y * mm for y in rows),
        area_min_per_side=amin * mm**2,
        area_per_side=count * abar * mm**2,
        diameter_max=dmax * mm,
        distribution_reviews=tuple(reviews),
        check_zones=check_zones,
    )
