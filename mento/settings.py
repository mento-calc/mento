from dataclasses import dataclass, field, fields
from typing import Any, ClassVar, Dict

from mento.units import inch, mm

# Sentinel to detect if user passed a value
_NOT_SET = object()


@dataclass
class BeamSettings:
    """
    Settings for beam design with separate metric and imperial defaults.
    Can optionally be initialized with a `Concrete` material to determine the unit system.

    Detailing preferences, not code provisions, with two exceptions that are
    printed identically by ACI 318-19 and CIRSOC 201-25:

    * ``clear_spacing`` -- ACI 318-19 §25.2.1 / CIRSOC 201-25 §25.2.1 ask for
      the greatest of 25 mm (1 in.), d_b and (4/3)*d_agg between parallel bars
      of one layer. The 25 mm here is the first of those three; the bar
      diameter is taken into account where the layer is laid out, and the
      aggregate term is not modelled.
    * ``layers_spacing`` -- ACI 318-19 §25.2.2 / CIRSOC 201-25 §25.2.2 ask for
      at least 25 mm (1 in.) of clear distance between layers.

    The rest have no clause behind them. ``vibrator_size`` is site practice.
    ``stirrup_diameter_ini`` is the stirrup assumed while the effective depth
    is first computed, before a stirrup has been chosen: neither code states a
    minimum stirrup diameter for a beam, and the 8 mm is simply a bar of the
    local catalogue (CIRSOC 201-25 §20.2.1.3, Tabla 20.2.1, which starts at
    6 mm). A design never starts below the smallest stirrup its code's
    catalogue offers, so under ACI 318-19 in metric units, whose catalogue
    starts at 10 mm, it starts at 10 mm; under CIRSOC 201-25 and EN 1992-1-1
    it starts at 8 mm, and the effective depth shifts slightly once the
    stirrup is chosen.
    ``minimum_longitudinal_diameter``, ``max_longitudinal_diameter``,
    ``max_diameter_diff`` and ``max_bars_per_layer`` bound the search, and are
    the engineer's choice.

    ``mounting_bar_diameter`` is a cross-section detailing preference: 8 mm
    in metric units, No. 3 (3/8 in.) in imperial units. It supplies missing
    supports at stirrup corners; the supplementary bars are recorded in
    ``beam.detailing_geometry.mounting_bars`` and are not credited in strength.
    This preference is not a code minimum.

    ``skin_bar_diameter`` is the smallest diameter mento's skin criterion uses
    (8 mm / No. 3), and ``skin_bar_spacing`` the most its skin bars are apart
    under a code that prints no spacing for them, EN 1992-1-1 (280 mm / 11 in.);
    see :mod:`mento.skin_reinforcement`.

    Available Parameters with Default Values:
    -----------------------------------------
    Unit system: "metric" or "imperial"

    Metric Defaults:
      - clear_spacing: 25 mm
      - stirrup_diameter_ini: 8 mm
      - vibrator_size: 30 mm
      - layers_spacing: 25 mm
      - max_diameter_diff: 5 mm
      - minimum_longitudinal_diameter: 8 mm
      - max_longitudinal_diameter: 32 mm
      - max_bars_per_layer: 12
      - design_options: 3

    Imperial Defaults:
      - clear_spacing: 1 inch
      - stirrup_diameter_ini: 3/8 inch
      - vibrator_size: 1.25 inch
      - layers_spacing: 1 inch
      - max_diameter_diff: 0.25 inch
      - minimum_longitudinal_diameter: 3/8 inch
      - max_longitudinal_diameter: 1.693 inch
      - max_bars_per_layer: 12
      - design_options: 3

    ``design_options`` is how many alternatives a design keeps per group of
    bars -- each face of longitudinal steel and the stirrups -- for
    ``flexure_design.bottom.options``, ``.top.options`` and
    ``shear_design.options``. The first is always the one applied.
    """

    # Class-level default values (documented but not shown in hover)
    _metric_defaults: ClassVar[Dict[str, Any]] = {
        "clear_spacing": 25 * mm,
        "stirrup_diameter_ini": 8 * mm,
        "vibrator_size": 30 * mm,
        "layers_spacing": 25 * mm,
        "max_diameter_diff": 5 * mm,
        "minimum_longitudinal_diameter": 8 * mm,
        "mounting_bar_diameter": 8 * mm,
        "skin_bar_diameter": 8 * mm,
        "skin_bar_spacing": 280 * mm,
        "skin_crack_width": 0.3 * mm,
        "max_longitudinal_diameter": 32 * mm,
        "max_bars_per_layer": 12,
        "design_options": 3,
    }

    _imperial_defaults: ClassVar[Dict[str, Any]] = {
        "clear_spacing": 1 * inch,
        "stirrup_diameter_ini": 3 / 8 * inch,
        "vibrator_size": 1.25 * inch,
        "layers_spacing": 1 * inch,
        "max_diameter_diff": 0.25 * inch,
        "minimum_longitudinal_diameter": 3 / 8 * inch,
        "mounting_bar_diameter": 3 / 8 * inch,
        "skin_bar_diameter": 3 / 8 * inch,
        "skin_bar_spacing": 11 * inch,
        "skin_crack_width": 0.3 * mm,
        "max_longitudinal_diameter": 1.693 * inch,
        "max_bars_per_layer": 12,
        "design_options": 3,
    }

    unit_system: str = "metric"

    clear_spacing: Any = field(default=_NOT_SET)
    stirrup_diameter_ini: Any = field(default=_NOT_SET)
    vibrator_size: Any = field(default=_NOT_SET)
    layers_spacing: Any = field(default=_NOT_SET)
    max_diameter_diff: Any = field(default=_NOT_SET)
    minimum_longitudinal_diameter: Any = field(default=_NOT_SET)
    max_longitudinal_diameter: Any = field(default=_NOT_SET)
    max_bars_per_layer: Any = field(default=_NOT_SET)
    design_options: Any = field(default=_NOT_SET)
    mounting_bar_diameter: Any = field(default=_NOT_SET)
    # Skin-steel detailing preference, not a code minimum or resistant steel.
    skin_bar_diameter: Any = field(default=_NOT_SET)
    skin_bar_spacing: Any = field(default=_NOT_SET)
    skin_crack_width: Any = field(default=_NOT_SET)

    def __post_init__(self) -> None:
        defaults = self._imperial_defaults if self.unit_system == "imperial" else self._metric_defaults

        for f in fields(self):
            if not f.init or f.name == "unit_system":
                continue

            current_value = getattr(self, f.name)

            if current_value is _NOT_SET:
                setattr(self, f.name, defaults[f.name])

        if self.max_bars_per_layer < 1:
            raise ValueError("max_bars_per_layer must be at least 1")
        if isinstance(self.design_options, bool) or not isinstance(self.design_options, int) or self.design_options < 1:
            raise ValueError("design_options must be an integer of at least 1")

    def __str__(self) -> str:
        """Returns only the current settings, excluding class defaults."""
        settings_list = []
        for name, value in vars(self).items():
            # Skip private and special attributes, and the unit_system field
            if not name.startswith("_") and name != "unit_system":
                if hasattr(value, "magnitude") and hasattr(value, "units"):  # It's a Quantity
                    settings_list.append(f"{name}: {value.magnitude:.2f} {value.units:~}")
                else:
                    settings_list.append(f"{name}: {value}")
        return "\n".join(settings_list)
