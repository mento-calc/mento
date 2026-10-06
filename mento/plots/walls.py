"""Drawing of a shear wall elevation.

``ShearWall.plot()`` delegates here, so the element class carries no matplotlib
of its own.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle
from mento.units import Quantity

from mento.precompute import DISPLAY
from mento.results import CUSTOM_COLORS
from mento.wall_results import mesh_callout

if TYPE_CHECKING:
    from mento.shear_wall import ShearWall


def _dimension(length: Quantity, kind: str, imperial: bool) -> str:
    """A dimension label: whole centimetres in SI, up to four figures in inches and feet."""
    value = length.to(DISPLAY[imperial][kind])
    return f"{value:.4g~P}" if imperial else f"{value:.0f~P}"


def plot_wall_elevation(self: "ShearWall", show: bool = False) -> Figure:
    """Plan view of the wall (length × thickness) with dimensions and rebar callouts."""
    lw_cm: float = self.length.to("cm").magnitude
    t_cm: float = self.thickness.to("cm").magnitude

    fig, self._ax = plt.subplots(figsize=(10, max(3, t_cm / lw_cm * 8 + 1.5)))
    # Bound once, right where plt.subplots created it.
    ax = self._ax

    # Wall outline (plan view: length horizontal, thickness vertical)
    wall = Rectangle(
        (0, 0),
        lw_cm,
        t_cm,
        linewidth=1.3,
        edgecolor=CUSTOM_COLORS["dark_gray"],
        facecolor=CUSTOM_COLORS["light_gray"],
    )
    ax.add_patch(wall)

    # Decoupled horizontal/vertical padding so thin walls aren't squashed.
    h_pad = lw_cm * 0.08
    v_pad = max(t_cm * 1.2, lw_cm * 0.04)

    dim_color = CUSTOM_COLORS["dark_blue"]
    text_color = CUSTOM_COLORS["dark_gray"]

    # ---- Length dimension (below the wall) — engineering style ----
    dim_y = -v_pad * 0.6
    tick_v = v_pad * 0.18
    ax.annotate(
        "",
        xy=(0, dim_y),
        xytext=(lw_cm, dim_y),
        arrowprops={
            "arrowstyle": "<->",
            "lw": 1,
            "color": dim_color,
            "shrinkA": 0,
            "shrinkB": 0,
        },
    )
    # Extension ticks at both endpoints
    ax.plot([0, 0], [dim_y - tick_v, dim_y + tick_v], color=dim_color, lw=1)
    ax.plot([lw_cm, lw_cm], [dim_y - tick_v, dim_y + tick_v], color=dim_color, lw=1)
    ax.text(
        lw_cm / 2,
        dim_y - tick_v * 1.6,
        _dimension(self.length, "wall_length", self.concrete.is_imperial),
        ha="center",
        va="top",
        color=text_color,
    )

    # ---- Thickness dimension (right of the wall) — engineering style ----
    x_dim = lw_cm + h_pad * 0.6
    tick_h = h_pad * 0.07
    ax.annotate(
        "",
        xy=(x_dim, 0),
        xytext=(x_dim, t_cm),
        arrowprops={
            "arrowstyle": "<->",
            "lw": 1,
            "color": dim_color,
            "shrinkA": 0,
            "shrinkB": 0,
        },
    )
    # Extension ticks at both endpoints
    ax.plot([x_dim - tick_h, x_dim + tick_h], [0, 0], color=dim_color, lw=1)
    ax.plot([x_dim - tick_h, x_dim + tick_h], [t_cm, t_cm], color=dim_color, lw=1)
    ax.text(
        x_dim + tick_h * 4,
        t_cm / 2,
        _dimension(self.thickness, "length", self.concrete.is_imperial),
        ha="left",
        va="center",
        color=text_color,
    )

    # ---- Rebar callout above the wall (same font as dimensions) ----
    def _fmt_rebar(d_b: Quantity, s: Quantity) -> str:
        if s.magnitude <= 0:
            return "not assigned"
        return mesh_callout(d_b, s, self.concrete.is_imperial)

    rebar_text = (
        f"Horizontal rebar: {_fmt_rebar(self._d_b_h, self._s_h)}\n"
        f"Minimum vertical rebar: {_fmt_rebar(self._d_b_v, self._s_v)}"
    )
    ax.text(
        lw_cm / 2,
        t_cm + v_pad * 0.35,
        rebar_text,
        ha="center",
        va="bottom",
        color=text_color,
    )

    # Compact limits — no large empty band above or below.
    ax.set_xlim(-h_pad * 0.5, lw_cm + h_pad * 2.0)
    ax.set_ylim(dim_y - tick_v * 5, t_cm + v_pad * 1.8)
    ax.axis("off")
    ax.set_title(f"Shear Wall {self.label} — plan view")

    self._fig = fig
    if show:
        plt.show()
    # Prevent Jupyter's inline backend from auto-displaying the figure twice
    # (once when plt.subplots creates it, and again as the cell's return value).
    plt.close(fig)
    return fig
