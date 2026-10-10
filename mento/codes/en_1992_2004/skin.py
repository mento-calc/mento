"""EN 1992-1-1:2004 §7.3.3(3), longitudinal web steel in pure bending.

The layout and the minimum area of Eq. (7.1) are mento's skin criterion
(:mod:`mento.skin_reinforcement`); this module supplies what is EN's own: the
1 m threshold and the diameter cap of Table 7.2N / Eq. (7.7N), read with the
service steel stress mento assumes, ``ASSUMED_SERVICE_STRESS`` of f_yk.
Annex J surface mesh is a separate detail outside the links.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from mento.codes.en_1992_2004.equations.skin import adjusted_diameter, tabulated_skin_diameter
from mento.skin_reinforcement import SkinReinforcementRequirement
from mento.units import MPa, Quantity, mm

if TYPE_CHECKING:
    from mento.beam import RectangularBeam

#: Service stress of the main tension steel over f_yk, as mento assumes it: a quasi-permanent
#: stress of the order a beam designed at the ultimate limit state carries.
ASSUMED_SERVICE_STRESS = 0.6


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
    if req.pending_reason == "axial":
        result.append(_Raw("skin_en_axial_unsupported", {}))
    elif req.status == "required":
        result.append(_Raw("skin_en_required", {"area": req.area_min_per_side, "diameter": req.diameter_max}))
    elif req.status == "unsupported":
        result.append(_Raw("skin_reinforcement_unsupported", {}))
    return result


def threshold(concrete: object) -> Quantity:
    """EN 1992-1-1 §7.3.3(3): skin steel in beams 1 m deep or more."""
    return 1000 * mm


def diameter_cap(beam: RectangularBeam, faces: tuple[str, ...], diameter: Quantity) -> Quantity:
    """The largest skin diameter, EN 1992-1-1 §7.3.3(2)-(3): Table 7.2N and Eq. (7.7N), in pure bending.

    §7.3.3(3) reads Table 7.2N with half the main service steel stress, which
    mento assumes: 0.6 f_yk, a quasi-permanent stress of the order a beam
    designed at the ultimate limit state carries. Eq. (7.7N) is read in
    two ways -- the bending depth h_cr = h/2 over the main tension layer, and
    the web as a tie across its width over the skin bar itself -- and the
    smaller governs: a Mento interpretation, not an extra expression of EN.
    Neither calculates a crack width.
    """
    from mento.cage_detailing import CageDetailingError

    settings = beam.settings
    assert settings is not None
    h = float(beam.height.to(mm).magnitude)
    width = float(beam.width.to(mm).magnitude)
    fy = float(beam.steel_bar.f_y.to(MPa).magnitude)
    fct = float(beam.concrete.f_ctm.to(MPa).magnitude)  # type: ignore[attr-defined]
    wk = _length(settings.skin_crack_width, "skin_crack_width")
    skin_edge = float((beam.c_c + beam._stirrup_d_b).to(mm).magnitude) + float(diameter.to(mm).magnitude) / 2
    bars = beam.section_geometry.bars
    try:
        phi_star = tabulated_skin_diameter(ASSUMED_SERVICE_STRESS * fy, wk)
    except ValueError as error:
        raise CageDetailingError(f"Skin service stress: {error}") from error
    caps = []
    for face in faces:
        outer = [bar for bar in bars if bar.face == face and bar.layer == 1]
        if not outer:
            raise CageDetailingError("EN skin reinforcement needs an outer tension layer.")
        total = sum(float(bar.d_b.to(mm).magnitude) ** 2 for bar in outer)
        level = sum(float(bar.y.to(mm).magnitude) * float(bar.d_b.to(mm).magnitude) ** 2 for bar in outer) / total
        edge = level if face == "bottom" else h - level
        caps.append(
            min(adjusted_diameter(phi_star, fct, h / 2, edge), adjusted_diameter(phi_star, fct, width, skin_edge))
        )
    return min(caps) * mm
