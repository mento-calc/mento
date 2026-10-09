"""Section-specific cracked-service inputs, separate from design preferences.

These are supplied by an independent SLS analysis; Mento does not derive them
from ULS forces. Each case keeps its stress, neutral axis and tension face
together. The beam stores defensive copies and invalidates them on rebar edits.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from mento.units import MPa, Quantity, mm

if TYPE_CHECKING:
    from mento.beam import RectangularBeam


@dataclass(frozen=True)
class SkinServiceCase:
    """One cracked-service case for the current section and reinforcement.

    ``neutral_axis`` is measured from the compression face. ``label`` names
    the service combination, which need not be a ULS combination label.
    Reversal requires separate cases for bottom and top tension.
    """

    label: str
    tension_face: Literal["bottom", "top"]
    steel_stress: Quantity
    neutral_axis: Quantity

    def __post_init__(self) -> None:
        if not isinstance(self.label, str) or not self.label.strip():
            raise ValueError("Skin service case needs a non-empty label.")
        if self.tension_face not in ("bottom", "top"):
            raise ValueError("Skin service tension_face must be bottom or top.")
        for name, value, dimension, unit in (
            ("steel_stress", self.steel_stress, "[pressure]", MPa),
            ("neutral_axis", self.neutral_axis, "[length]", mm),
        ):
            if not isinstance(value, Quantity) or not value.check(dimension):
                raise ValueError(f"Skin service {name} must be a {dimension} quantity.")
            number = float(value.to(unit).magnitude)
            if not math.isfinite(number) or number <= 0:
                raise ValueError(f"Skin service {name} must be finite and positive.")


def service_reference(beam: RectangularBeam) -> tuple[Any, ...]:
    """The physical section the externally assessed service inputs describe."""
    assert beam.settings is not None
    return (
        beam.width,
        beam.height,
        beam.c_c,
        beam.concrete.design_code,
        beam.concrete.f_c,
        beam.steel_bar.f_y,
        beam.steel_bar.E_s,
        getattr(beam.concrete, "E_c", None),
        getattr(beam.concrete, "E_cm", None),
        getattr(beam.concrete, "f_ctm", None),
        beam.settings.layers_spacing,
        beam.reinforcement,
    )
