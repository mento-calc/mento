"""Cross-section support of required compression steel, §9.7.6.4.4.

ACI 318-19 SI/in-lb p.148: corner and alternate bars, 150 mm / 6 in
clear on each side along the transverse reinforcement. CIRSOC 201-25
Cap.9 p.179 prints "15 d_be or 150 mm": both readings are exposed;
disagreement is pending, not a silently selected normative interpretation.
The modelled first row uses perimeter corners or crossties with both ends
engaging peripheral bars (§25.3.5, Table 25.3.2). Angles alone are not support.
Second rows need a separate supported detail. Plain open legs are not
credited. Longitudinal alternation is specified, not checked in execution.
This does not verify development, seismic detailing or the
length along the member; it does not alter strength or the shear verdict.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from mento.units import Quantity, inch, mm

if TYPE_CHECKING:
    from mento.beam import RectangularBeam
    from mento.section_geometry import BarPosition, SectionGeometry


@dataclass(frozen=True)
class CompressionFaceDetail:
    face: str
    status: str
    supported_bars: tuple[int, ...]
    unsupported_bars: tuple[int, ...]
    maximum_clear_distance: Quantity
    limits: tuple[Quantity, ...]
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class CompressionDetailing:
    status: str
    faces: tuple[CompressionFaceDetail, ...] = ()
    reason: str = ""


def _mm(value: Quantity) -> float:
    return float(value.to("mm").magnitude)


def _corner_supported(bar: BarPosition, geometry: SectionGeometry) -> bool:
    """Recognize the same rounded-corner positions used by the cage builder.

    Closed rectangle corners have interior angle 90 degrees (<135).
    Supplementary mounting bars do not make a resistant bar supported.
    """
    d_st = _mm(geometry.stirrup_d_b)
    offset = max((_mm(geometry.stirrup_bend_inner_diameter) + d_st) / 2, (_mm(bar.d_b) + d_st) / 2)
    vertical = (_mm(bar.d_b) + d_st) / 2
    for stirrup in geometry.stirrups:
        branch = stirrup.y_top if bar.face == "top" else stirrup.y_bottom
        side_y = -1 if bar.face == "top" else 1
        if abs(_mm(bar.y - branch) - side_y * vertical) > 1e-6:
            continue
        if any(
            abs(_mm(bar.x - leg) - side * offset) <= 1e-6 for leg, side in ((stirrup.x_left, 1), (stirrup.x_right, -1))
        ):
            return True
    return False


EN_COMPRESSION_PENDING_REASON = "EN §9.2.1.2(3): compression-bar support (15φ) is not verified"


def check_compression_detailing(
    beam: RectangularBeam, geometry: SectionGeometry | None = None, unavailable: str = ""
) -> CompressionDetailing:
    """Read required faces from flexure; never infer them from mere bar presence."""
    code = beam.concrete.design_code
    if code == "EN 1992-2004" and beam._compression_faces:
        return CompressionDetailing("pending", reason=EN_COMPRESSION_PENDING_REASON)
    if code not in ("ACI 318-19", "CIRSOC 201-25") or beam._stirrups_optional:
        return CompressionDetailing("not_applicable")
    if not beam._compression_faces:
        return CompressionDetailing(
            "not_required" if beam._flexure_checked else "pending",
            reason="" if beam._flexure_checked else "flexure_not_checked",
        )
    if geometry is None:
        return CompressionDetailing("pending", reason=unavailable or "base_cage_unavailable")
    if not geometry.stirrups:
        return CompressionDetailing("failed", reason="closed_stirrups_missing")
    if not geometry.bend_supported:
        return CompressionDetailing("pending", reason="unsupported_bend")
    results = []
    for face_code in sorted(beam._compression_faces):
        face = "bottom" if face_code == "bot" else "top"
        row = sorted(geometry.bars_on(face, 1), key=lambda bar: _mm(bar.x))
        if not row:
            results.append(CompressionFaceDetail(face, "pending", (), (), 0 * mm, (), ("first_row_missing",)))
            continue
        from mento.crosstie_detailing import tie_supports

        supported = [
            _corner_supported(bar, geometry)
            or any(
                tie_supports(bar, tie, geometry, code, beam.concrete.unit_system == "imperial")
                for tie in geometry.crossties
            )
            for bar in row
        ]
        supported_indices = tuple(i + 1 for i, yes in enumerate(supported) if yes)
        unsupported_indices = tuple(i + 1 for i, yes in enumerate(supported) if not yes)
        failures: list[str] = []
        pending: list[str] = []
        unknown_ties = any(t.alternate_hooks and t.bend_inner_diameter is None for t in geometry.crossties)
        # Corner bars plus every alternate bar: an isolated unsupported bar
        # may lie between supported bars, but two successive ones may not.
        if not supported[0] or not supported[-1]:
            failures.append("corner_bar_unbraced")
        if any(not left and not right for left, right in zip(supported, supported[1:])):
            (pending if unknown_ties else failures).append(
                "crosstie_hook_rule_not_modelled" if unknown_ties else "alternate_bars_unbraced"
            )
        outer = next((s for s in geometry.stirrups if s.perimeter), None)
        for bar in geometry.bars_on(face):
            radius = (_mm(bar.d_b) + _mm(geometry.stirrup_d_b)) / 2
            if outer is None or not (
                _mm(outer.x_left) + radius - 1e-6 <= _mm(bar.x) <= _mm(outer.x_right) - radius + 1e-6
                and _mm(outer.y_bottom) + radius - 1e-6 <= _mm(bar.y) <= _mm(outer.y_top) - radius + 1e-6
            ):
                failures.append("bar_outside_closed_stirrup")
                break
        distance = 0.0
        for i, yes in enumerate(supported):
            if yes:
                continue
            left = next((j for j in range(i - 1, -1, -1) if supported[j]), None)
            right = next((j for j in range(i + 1, len(row)) if supported[j]), None)
            if left is None or right is None:
                continue  # Already fails the corner rule.
            for j in (left, right):
                clear = abs(_mm(row[i].x - row[j].x)) - (_mm(row[i].d_b) + _mm(row[j].d_b)) / 2
                distance = max(distance, clear)
        limits: tuple[Quantity, ...] = ((6 * inch if beam.concrete.unit_system == "imperial" else 150 * mm),)
        if code == "CIRSOC 201-25":
            limits = (15 * geometry.stirrup_d_b, 150 * mm)
        within = [distance <= _mm(limit) + 1e-6 for limit in limits]
        if not any(within) and not unknown_ties:
            failures.append("clear_distance_exceeded")
        elif not all(within):
            pending.append("cirsoc_limit_interpretation")
        if geometry.bars_on(face, 2):
            pending.append("second_row_support_not_modelled")
        status = "failed" if failures else "pending" if pending else "passed"
        results.append(
            CompressionFaceDetail(
                face, status, supported_indices, unsupported_indices, distance * mm, limits, tuple(failures + pending)
            )
        )
    status = (
        "failed"
        if any(r.status == "failed" for r in results)
        else ("pending" if any(r.status == "pending" for r in results) else "passed")
    )
    return CompressionDetailing(status, tuple(results))
