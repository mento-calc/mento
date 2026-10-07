"""EN 1992-1-1:2004 §7.3.3(3), longitudinal web steel in pure bending.

Uses §7.3.2 Eq. (7.1) and the DIAMETER route of Table 7.2N / Eq. (7.7N).
Service stress and the neutral-axis envelope are explicit SLS inputs: ULS
forces and an ultimate compression-block limit must never substitute for them.
Annex J surface mesh is a separate detail outside the links.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import TYPE_CHECKING

from mento.codes.en_1992_2004.equations.flexure import crack_control_min_reinforcement
from mento.skin_reinforcement import SkinReinforcementRequirement
from mento.units import Quantity, mm, MPa

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
    h = float(beam.height.to(mm).magnitude)
    width = float(beam.width.to(mm).magnitude)
    fy = float(beam.steel_bar.f_y.to(MPa).magnitude)
    fct = float(concrete.f_ctm.to(MPa).magnitude)
    # Pure rectangular bending: kc=0.4 and Act=b*h/2 BEFORE cracking.
    # §7.3.3(3) replaces k with 0.5 and sigma_s with characteristic fy.
    # Divide the total additional area equally between the two lateral faces.
    amin = crack_control_min_reinforcement(0.4, 0.5, fct, width * h / 2, fy) / 2
    if settings.skin_service_steel_stress is None or settings.skin_service_neutral_axis is None:
        return SkinReinforcementRequirement(
            "pending", threshold, faces, area_min_per_side=amin * mm**2, pending_reason="service"
        )
    stress = settings.skin_service_steel_stress
    if not isinstance(stress, Quantity) or not stress.check("[pressure]"):
        raise CageDetailingError("skin_service_steel_stress must be a stress quantity.")
    main_stress = float(stress.to(MPa).magnitude)
    if not math.isfinite(main_stress) or not 0 < main_stress <= fy:
        raise CageDetailingError("skin_service_steel_stress must be positive and no greater than f_yk.")
    diameter = _length(settings.skin_bar_diameter, "skin_bar_diameter")
    if settings.skin_bar_diameter < settings.minimum_longitudinal_diameter:
        raise CageDetailingError("skin_bar_diameter is below minimum_longitudinal_diameter.")
    wk = _length(settings.skin_crack_width, "skin_crack_width")
    widths = (0.4, 0.3, 0.2)
    column = next((i for i, value in enumerate(widths) if math.isclose(wk, value, abs_tol=1e-9)), None)
    if column is None:
        raise CageDetailingError("skin_crack_width must be 0.2, 0.3 or 0.4 mm for Table 7.2N.")
    # Table 7.2N, high-bond reinforcement. Round stress UP to a tabulated
    # row rather than invent interpolation or extrapolate beyond the table.
    table = (
        (160, (40, 32, 25)),
        (200, (32, 25, 16)),
        (240, (20, 16, 12)),
        (280, (16, 12, 8)),
        (320, (12, 10, 6)),
        (360, (10, 8, 5)),
        (400, (8, 6, 4)),
        (450, (6, 5, 0)),
    )
    skin_stress = main_stress / 2  # §7.3.3(3), not ACI's 2fy/3.
    row = next((limits for sigma, limits in table if sigma >= skin_stress), None)
    if row is None or row[column] <= 0:
        raise CageDetailingError("The requested skin crack-control case is outside Table 7.2N.")
    bars = beam.section_geometry.bars
    # h-d is the centroid distance of the OUTERMOST tension layer.
    # hcr=h/2 is the pure-bending tensile depth immediately BEFORE cracking;
    # x above describes the cracked SERVICE section and is not hcr.
    caps = []
    zones = []
    for face in faces:
        axes = settings.skin_service_neutral_axis
        if isinstance(axes, Mapping):
            if face not in axes:
                raise CageDetailingError(f"skin_service_neutral_axis is missing the {face} tension case.")
            axes = axes[face]
        x = _length(axes, "skin_service_neutral_axis")
        if x >= h:
            raise CageDetailingError("skin_service_neutral_axis must be inside the section, measured from compression.")
        outer = [bar for bar in bars if bar.face == face and bar.layer == 1]
        if not outer:
            raise CageDetailingError("EN skin reinforcement needs an outer tension layer.")
        total = sum(float(bar.d_b.to(mm).magnitude) ** 2 for bar in outer)
        level = sum(float(bar.y.to(mm).magnitude) * float(bar.d_b.to(mm).magnitude) ** 2 for bar in outer) / total
        edge = level if face == "bottom" else h - level
        caps.append(row[column] * (fct / 2.9) * (h / 2) / (8 * edge))
        neutral = h - x if face == "bottom" else x
        low, high = sorted((level, neutral))
        if (face == "bottom" and neutral <= level) or (face == "top" and neutral >= level):
            raise CageDetailingError("The service neutral axis must lie above the tension layer toward compression.")
        zones.append((low, high))
    dmax = min(caps)
    if diameter > dmax + 1e-9:
        raise CageDetailingError("skin_bar_diameter exceeds EN Table 7.2N adjusted by Eq. (7.7N).")
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
    for face, (a, b) in zip(faces, zones):
        zone_rows = tuple(y for y in rows if a - 1e-9 <= y <= b + 1e-9)
        levels = (a, *zone_rows, b)
        largest_gap = max(right - left for left, right in zip(levels, levels[1:]))
        reviews.append((face, len(zone_rows), largest_gap * mm))
    return SkinReinforcementRequirement(
        "required",
        threshold,
        faces,
        settings.skin_bar_diameter,
        beam.c_c + beam._stirrup_d_b,
        spacing=spacing * mm,
        n_per_side=count,
        rows=tuple(y * mm for y in rows),
        area_min_per_side=amin * mm**2,
        area_per_side=count * abar * mm**2,
        diameter_max=dmax * mm,
        distribution_reviews=tuple(reviews),
    )
