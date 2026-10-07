"""Float-only skin diameter lookup: EN 1992-1-1:2004 Table 7.2N.

§7.3.3(3) uses half the main service steel stress for longitudinal web
reinforcement. Upward stress rounding is Mento's conservative table choice;
it avoids interpolation and extrapolation. Lengths in mm, stress in MPa.
"""

import math


def tabulated_skin_diameter(main_service_stress: float, crack_width: float) -> float:
    """Return phi-star from Table 7.2N, without the Eq. (7.7N) adjustment."""
    if not math.isfinite(main_service_stress) or main_service_stress <= 0:
        raise ValueError("Main service steel stress must be finite and positive.")
    widths = (0.4, 0.3, 0.2)
    column = next((i for i, value in enumerate(widths) if math.isclose(crack_width, value, abs_tol=1e-9)), None)
    if column is None:
        raise ValueError("skin_crack_width must be 0.2, 0.3 or 0.4 mm for Table 7.2N.")
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
    row = next((limits for sigma, limits in table if sigma >= main_service_stress / 2), None)
    if row is None or row[column] <= 0:
        raise ValueError("Skin service stress is outside Table 7.2N.")
    return float(row[column])


def adjusted_diameter(phi_star: float, f_ct_eff: float, h_cr: float, h_minus_d: float) -> float:
    """EN §7.3.3(2), Eq. (7.7N): phi-star * fct/2.9 * hcr/[8(h-d)].

    This equation does not choose the geometry to represent web steel;
    the calling adapter explicitly documents Mento's interpretation.
    """
    if any(not math.isfinite(x) or x <= 0 for x in (phi_star, f_ct_eff, h_cr, h_minus_d)):
        raise ValueError("Diameter adjustment inputs must be finite and positive.")
    return phi_star * f_ct_eff / 2.9 * h_cr / (8 * h_minus_d)
