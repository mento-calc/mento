"""Longitudinal skin steel: mento's criterion, and the checks of the code where it requires skin.

Skin is laid out on both side faces of every beam 60 cm (24 in.) deep or
more, over the whole height between the bottom and top layers, so the same
bars serve a span and a support of a continuous beam:

- its count per side keeps the bars at most the code's spacing apart -- ACI
  318-19 / CIRSOC 201-25 §24.3.2 with the side cover, ``skin_bar_spacing``
  (28 cm) under EN 1992-1-1, which prints no cap;
- below 1 m its diameter is the smallest of mento's choice, Ø8 up to a 40 cm
  web and Ø10 above (No. 3 / No. 4);
- from 1 m it is the smallest diameter whose bars inside the tension zone
  give the minimum area of EN 1992-1-1 §7.3.3(3), Eq. (7.1), whatever the
  code -- with more bars if no diameter does -- and, under EN, within the
  diameter cap of Table 7.2N.

The status is ``required`` where the code requires skin (ACI / CIRSOC h > 900
mm, EN h >= 1 m) and ``proposed`` where mento lays it out on its own. This
steel controls web cracking: it is never credited to moment or shear
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
from mento.units import Quantity, inch, mm

if TYPE_CHECKING:
    from mento.beam import RectangularBeam


@dataclass(frozen=True)
class SkinDistributionReview:
    tension_face: str
    rows_per_side: int
    maximum_interval: Quantity


@dataclass(frozen=True)
class ManualSkinRebar:
    """Skin bars given by hand: ``n_per_side`` bars of ``d_b`` on each side face.

    ``position`` is where they go over the height: ``"total"`` between the
    bottom and top layers, ``"bottom"`` or ``"top"`` in the half next to that face.
    """

    d_b: Quantity
    n_per_side: int
    position: Literal["top", "bottom", "total"]

    def __post_init__(self) -> None:
        if not isinstance(self.d_b, Quantity) or not self.d_b.check("[length]"):
            raise ValueError("d_b must be a length quantity.")
        diameter = float(self.d_b.to(mm).magnitude)
        if not math.isfinite(diameter) or diameter <= 0:
            raise ValueError("d_b must be finite and positive.")
        if isinstance(self.n_per_side, bool) or not isinstance(self.n_per_side, Integral) or self.n_per_side < 0:
            raise ValueError("n_per_side must be a non-negative integer.")
        if self.position not in ("top", "bottom", "total"):
            raise ValueError("position must be top, bottom or total.")


@dataclass(frozen=True)
class SkinCheckZone:
    tension_face: str
    lower: Quantity
    upper: Quantity


@dataclass(frozen=True)
class SkinReinforcementRequirement:
    """Requirement, not a certificate that a provided cage complies.

    status is required, proposed, not_required, pending, unsupported or not_applicable:
    required where the code requires skin, proposed where mento's criterion lays it out
    without the code asking (60 cm deep or more).
    Pending means the flexure check or a tension case is missing; pending_reason
    identifies which ("no_tension_case"), and "axial" marks an unsupported EN beam
    with axial force. Unsupported is NOT an exemption.
    n_per_side counts the bars on EACH side face, in rows spread evenly over the
    whole height between the bottom and top layers; spacing is the gap between
    them, the gaps to the two layers included, and s_max the cap it meets.
    From 1 m area_min_per_side is the EN §7.3.3(3) minimum the rows inside each
    check zone give, and under EN diameter_max is the Table 7.2N cap.
    distribution_reviews is filled only for manual skin.
    Geometry and fit are verified by beam.detailing_geometry, which may raise.
    """

    status: Literal["required", "proposed", "not_required", "pending", "unsupported", "not_applicable"]
    threshold: Quantity | None = None
    tension_faces: tuple[str, ...] = ()
    d_b: Quantity | None = None
    side_cover: Quantity | None = None
    s_max: Quantity | None = None
    spacing: Quantity | None = None
    n_per_side: int = 0
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


#: Depth from which mento lays out skin, and from which its diameter follows the EN minimum area.
SKIN_FROM = 600 * mm
ENVELOPE_FROM = 1000 * mm
#: Neutral axis depth over h mento assumes in service, which is where the tension zone ends.
ASSUMED_NEUTRAL_AXIS = 0.4
#: Widest web that takes the smaller diameter below ENVELOPE_FROM.
NARROW_WEB = 400 * mm


def _imperial(beam: RectangularBeam) -> bool:
    return bool(beam.concrete.is_imperial)


def _skin_from(beam: RectangularBeam) -> Quantity:
    return 24 * inch if _imperial(beam) else SKIN_FROM


def _catalogue(beam: RectangularBeam) -> tuple[Quantity, ...]:
    """The skin diameters mento chooses from, smallest first, from the minimum the settings allow."""
    from mento.bar_sizes import bar_diameter

    settings = beam.settings
    assert settings is not None
    bars = (
        tuple(bar_diameter(n) for n in (3, 4, 5, 6)) if _imperial(beam) else tuple(d * mm for d in (8, 10, 12, 16, 20))
    )
    return tuple(d for d in bars if d >= settings.skin_bar_diameter - 1e-9 * mm) or (settings.skin_bar_diameter,)


def _anchors(beam: RectangularBeam) -> tuple[float, float]:
    """The levels (mm) the skin spans between: the inner bottom layer and the inner top layer."""
    geometry = beam.section_geometry
    inset = float((beam.c_c + beam._stirrup_d_b).to(mm).magnitude) + 10.0
    height = float(beam.height.to(mm).magnitude)

    def level(face: str) -> float:
        second = geometry.bars_on(face, layer=2)
        bars = second if len(second) >= 2 else geometry.bars_on(face, layer=1)
        if bars:
            return (max if face == "bottom" else min)(float(bar.y.to(mm).magnitude) for bar in bars)
        return inset if face == "bottom" else height - inset

    return level("bottom"), level("top")


def _minimum_area_per_side(beam: RectangularBeam) -> float:
    """EN 1992-1-1 §7.3.3(3): Eq. (7.1) with kc = 0.4, k = 0.5, sigma_s = f_yk, A_ct = b*h/2; half per side, mm².

    mento applies it from 1 m under every code, as the envelope of its criterion.
    A concrete without an EN f_ctm takes 0.30*f_c^(2/3) (Table 3.1).
    """
    from mento.units import MPa

    f_ctm = getattr(beam.concrete, "f_ctm", None)
    fct = (
        float(f_ctm.to(MPa).magnitude)
        if isinstance(f_ctm, Quantity)
        else 0.30 * float(beam.concrete.f_c.to(MPa).magnitude) ** (2 / 3)
    )
    fy = float(beam.steel_bar.f_y.to(MPa).magnitude)
    b = float(beam.width.to(mm).magnitude)
    h = float(beam.height.to(mm).magnitude)
    return 0.4 * 0.5 * fct * (b * h / 2) / fy / 2


def _skin_requirement(beam: RectangularBeam) -> SkinReinforcementRequirement:
    from mento.cage_detailing import CageDetailingError

    if transverse_layout(beam) == GRID:
        return SkinReinforcementRequirement("not_applicable")
    code = design_code(beam.concrete)
    if code.skin_reinforcement_threshold is None:
        return SkinReinforcementRequirement("unsupported")
    threshold = code.skin_reinforcement_threshold(beam.concrete)
    if beam.height < _skin_from(beam):
        return SkinReinforcementRequirement("not_required", threshold)
    code_requires = beam.height >= threshold if code.skin_threshold_inclusive else beam.height > threshold
    if not beam._flexure_checked or not beam.flexure_checks:
        return SkinReinforcementRequirement("pending", threshold)
    # Demand/capacity ratios belong to every checked combination, so reversals
    # are covered even when the last combination puts only one face in tension.
    faces = tuple(
        face for face in ("bottom", "top") if any(getattr(check, face).DCR > 0 for check in beam.flexure_checks)
    )
    envelope = beam.height >= ENVELOPE_FROM
    if envelope and code.skin_diameter_cap is not None and any(c.has_axial_force for c in beam.flexure_checks):
        # The diameter cap of the code reads a section in pure bending.
        return SkinReinforcementRequirement("unsupported", threshold, faces, pending_reason="axial")
    if not faces:
        return SkinReinforcementRequirement("pending", threshold, pending_reason="no_tension_case")
    settings = beam.settings
    assert settings is not None
    minimum = settings.skin_bar_diameter
    if not isinstance(minimum, Quantity) or not minimum.check("[length]"):
        raise CageDetailingError("skin_bar_diameter must be a length quantity.")
    if not math.isfinite(float(minimum.to(mm).magnitude)) or minimum <= 0 * mm:
        raise CageDetailingError("skin_bar_diameter must be finite and positive.")
    if minimum < settings.minimum_longitudinal_diameter:
        raise CageDetailingError("skin_bar_diameter must be finite, positive and meet minimum_longitudinal_diameter.")
    # Placed just INSIDE the perimeter stirrup.
    cover = beam.c_c + beam._stirrup_d_b
    cap = code.max_skin_bar_spacing(beam, cover) if code.max_skin_bar_spacing is not None else settings.skin_bar_spacing
    limit = float(cap.to(mm).magnitude)
    if not math.isfinite(limit) or limit <= 0:
        raise CageDetailingError("No positive skin-bar spacing is permitted for this cover and steel grade.")
    low, high = _anchors(beam)
    if high <= low:
        raise CageDetailingError("The section has no height between its layers for skin bars.")
    count = max(1, math.ceil((high - low) / limit - 1e-12) - 1)
    height = float(beam.height.to(mm).magnitude)
    # The tension zone of each face ends at the service neutral axis, which mento assumes.
    x = ASSUMED_NEUTRAL_AXIS * height
    zones = []
    for face in faces:
        anchor, neutral = (low, height - x) if face == "bottom" else (high, x)
        if (face == "bottom" and neutral <= anchor) or (face == "top" and neutral >= anchor):
            raise CageDetailingError("The service neutral axis must lie above the tension layer toward compression.")
        zones.append(SkinCheckZone(face, min(anchor, neutral) * mm, max(anchor, neutral) * mm))

    def rows_for(n: int) -> tuple[float, ...]:
        pitch = (high - low) / (n + 1)
        return tuple(low + pitch * i for i in range(1, n + 1))

    area_min = None
    diameter_max = None
    if envelope:
        area_min = _minimum_area_per_side(beam)
        candidates = _catalogue(beam)
        if code.skin_diameter_cap is not None:
            diameter_max = min(code.skin_diameter_cap(beam, faces, d) for d in candidates[:1])
            candidates = tuple(d for d in candidates if d <= code.skin_diameter_cap(beam, faces, d) + 1e-9 * mm)
            if not candidates:
                raise CageDetailingError("No skin diameter meets the diameter cap of the code.")
        clear = max(settings.clear_spacing, settings.vibrator_size)
        chosen = None
        for n in range(count, count + 20):
            rows = rows_for(n)
            for d in candidates:
                if (high - low) / (n + 1) < float((d + clear).to(mm).magnitude):
                    continue
                bar = math.pi * float(d.to(mm).magnitude) ** 2 / 4
                inside = [
                    sum(
                        float(z.lower.to(mm).magnitude) - 1e-9 <= y <= float(z.upper.to(mm).magnitude) + 1e-9
                        for y in rows
                    )
                    for z in zones
                ]
                if all(k * bar >= area_min - 1e-9 for k in inside):
                    chosen = (n, d)
                    break
            if chosen is not None:
                break
        if chosen is None:
            raise CageDetailingError("The skin cannot reach the minimum area of EN 1992-1-1 §7.3.3(3) in the web.")
        count, diameter = chosen
        if code.skin_diameter_cap is not None:
            diameter_max = code.skin_diameter_cap(beam, faces, diameter)
    else:
        narrow = 16 * inch if _imperial(beam) else NARROW_WEB
        catalogue = _catalogue(beam)
        diameter = catalogue[0] if beam.width <= narrow else (catalogue[1] if len(catalogue) > 1 else catalogue[0])
    rows = rows_for(count)
    return SkinReinforcementRequirement(
        "required" if code_requires else "proposed",
        threshold,
        faces,
        diameter,
        cover,
        cap,
        (high - low) / (count + 1) * mm,
        count,
        rows=tuple(y * mm for y in rows),
        area_min_per_side=None if area_min is None else area_min * mm**2,
        area_per_side=count * math.pi * diameter**2 / 4,
        diameter_max=diameter_max,
        check_zones=tuple(zones),
    )


def _manual_skin_requirement(beam: RectangularBeam, req: SkinReinforcementRequirement) -> SkinReinforcementRequirement:
    """Check the bars given by hand as they are: the count is not raised and their zone is not moved."""
    supplied = beam.skin_rebar
    assert supplied is not None
    if req.status == "not_applicable":
        return replace(req, manual=True)
    geometry = beam.section_geometry
    diameter = supplied.d_b
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
    count = int(supplied.n_per_side)
    midpoint = height / 2
    if supplied.position == "bottom":
        high = midpoint
    elif supplied.position == "top":
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
    elif supplied.position == "total":
        pitch = (high - low) / (count + 1)
        rows = tuple(low + pitch * i for i in range(1, count + 1))
    else:
        pitch = (high - low) / count
        rows = (
            tuple(low + pitch * i for i in range(1, count + 1))
            if supplied.position == "bottom"
            else tuple(high - pitch * i for i in range(1, count + 1))
        )
    rows = tuple(sorted(rows))
    area = count * math.pi * float(diameter.to(mm).magnitude) ** 2 / 4 * mm**2
    if req.area_min_per_side is not None and area < req.area_min_per_side - 1e-8 * mm**2:
        failures.append("The supplied skin area per lateral face is insufficient.")
    reviews = []
    if req.status == "required":
        if supplied.position != "total":
            for face in req.tension_faces:
                if face != supplied.position:
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
                reviews.append(SkinDistributionReview(zone.tension_face, len(inside), gap))
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
    """Draw the skin rows on both side faces; reject clashes rather than hide them.

    The rows come from the requirement (mento's criterion or the manual input),
    just inside the perimeter stirrup. The flexural layers are not credited
    toward the skin.
    """
    from mento.cage_detailing import CageDetailingError

    req = skin_requirement(beam)
    if req.failures and not req.rows:
        raise CageDetailingError(" ".join(req.failures), reason="skin")
    if req.status not in ("required", "proposed") and not req.manual:
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
