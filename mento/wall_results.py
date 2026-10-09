"""Public, read-only view of a structural wall's mesh and its shear results.

A :class:`~mento.shear_wall.ShearWall` is reinforced with a distributed mesh,
not with the bars and stirrups of the beam it inherits from, so its results
have their own shape. Read them through these dataclasses rather than the
wall's private attributes::

    node.design()

    wall.mesh.horizontal.d_b, wall.mesh.horizontal.s   # the shear mesh
    wall.mesh.vertical.rho                             # the vertical ratio
    wall.shear_design.DCR                              # governing combination
    wall.shear_checks[0].V_capacity                    # ØVn of one combination
    wall.shear_checks[0].mesh                          # the mesh it was checked with

A result is a value of the check: each one carries the mesh it was formed
with, so a design never pairs one mesh with the DCR of another. A mesh set by
hand afterwards belongs to no check yet, and the wall drops the results until
the next one runs.

Forces and lengths are pint quantities in the section's unit system;
reinforcement ratios are plain floats.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional, Sequence, Tuple

from mento.bar_sizes import bar_designation, is_us_customary
from mento.design_results import DesignNotRunError, bar_mark, format_longitudinal_rebar, spacing_separator
from mento.units import Quantity, cm, inch, mm

if TYPE_CHECKING:
    from mento.shear_wall import ShearWall


def mesh_callout(d_b: Quantity, s: Quantity, imperial: bool) -> str:
    """One direction of a wall's mesh as the reports and the drawing write it.

    ``Ø10/20 cm E.F.`` in SI -- the bar in mm, the spacing in whole
    centimetres -- and ``#4@12 in E.F.`` in US customary, where the bar is its
    ASTM size and the spacing keeps up to four significant figures.
    """
    if imperial:
        spacing = f"{s.to(inch).magnitude:.4g} in"
        bar = bar_designation(d_b)
    else:
        spacing = f"{s.to(cm).magnitude:.0f} cm"
        bar = f"Ø{d_b.to(mm).magnitude:.0f}"
    return f"{bar}{spacing_separator(imperial)}{spacing} E.F."


@dataclass(frozen=True)
class MeshDirection:
    """The bars of one direction of the mesh: ``d_b`` every ``s``, on each curtain.

    ``rho`` is the ratio they give over the wall thickness, counting every
    curtain: ``n_curtains · A_b / (t · s)``. A zero spacing means the
    direction carries no bars.
    """

    d_b: Quantity
    s: Quantity
    rho: float
    n_curtains: int

    @property
    def has_bars(self) -> bool:
        """Whether this direction carries any bars."""
        return self.s.magnitude > 0 and self.d_b.magnitude > 0

    @property
    def A_s(self) -> Quantity:
        """Steel area per unit length of wall, every curtain counted."""
        if not self.has_bars:
            return 0 * self.d_b.units**2 / self.s.units
        return self.n_curtains * math.pi / 4 * self.d_b**2 / self.s

    def __str__(self) -> str:
        if not self.has_bars:
            return "no reinforcement"
        return f"{self.n_curtains}×" + format_longitudinal_rebar(
            0, bar_mark(self.d_b), f"{self.s:.4g~P}", imperial=is_us_customary(self.d_b)
        )


@dataclass(frozen=True)
class WallMesh:
    """The distributed reinforcement of a wall.

    ``horizontal`` carries the in-plane shear (ρt); ``vertical`` is the
    vertical mesh (ρl), sized by design to its minimum.
    """

    horizontal: MeshDirection
    vertical: MeshDirection

    def __str__(self) -> str:
        return f"horizontal: {self.horizontal} / vertical: {self.vertical}"


@dataclass(frozen=True)
class WallShearCheck:
    """The in-plane shear result of one load combination.

    ``mesh`` is the reinforcement the combination was checked with -- the
    wall's own at the time, kept here so the result stays whole once the wall
    changes. ``V_u`` and ``N_u`` are the demand of the combination, ``V_Ed``
    and ``N_Ed`` under EN 1992-1-1. ``V_capacity`` is the design shear
    strength the ``DCR`` was formed from -- ``ØVn``, or ``V_Rd`` -- and
    ``V_max`` the most the section can carry however it is reinforced:
    ``ØVn,max`` of ACI 318-19 / CIRSOC 201-25 §11.5.4.2, or ``V_Rd,max`` of
    EN 1992-1-1 Eq. (6.9) at 45°.

    ``rho_t_req`` is the horizontal ratio the combination needs, never below
    ``rho_t_min``. ``rho_l_min`` is the vertical minimum: under ACI 318-19 /
    CIRSOC 201-25 §11.6.2(a), Eq. (11.6.2) with the ``rho_t`` provided,
    capped by ``rho_t_req``; under EN 1992-1-1 §9.6.2(1), 0.002, where it is
    the horizontal minimum of §9.6.3(1) that reads the vertical mesh instead.
    Either way it depends on the mesh as much as on the combination.
    ``rho_l_max`` is the vertical maximum where the code states one (EN
    1992-1-1 §9.6.2(1), 0.04) and ``None`` where it does not. ``rho_t`` and
    ``rho_l`` are the ratios that mesh provides, and ``s_h_max`` /
    ``s_v_max`` the spacing limits of the code.
    """

    label: str
    mesh: WallMesh
    V_u: Quantity
    N_u: Quantity
    V_capacity: Quantity
    V_max: Quantity
    rho_t: float
    rho_t_req: float
    rho_t_min: float
    rho_l: float
    rho_l_min: float
    s_h_max: Quantity
    s_v_max: Quantity
    DCR: float
    rho_l_max: Optional[float] = None


@dataclass(frozen=True)
class WallShearDesign:
    """The wall's mesh and what the checked combinations demanded of it.

    ``mesh`` is the one the combinations were checked with, read off the
    checks themselves rather than off the wall, so the ``DCR`` next to it is
    its own. ``rho_t_req``, ``rho_l_min`` and ``DCR`` are the envelope over
    every combination checked; ``V_capacity`` is the ``ØVn`` (``V_Rd``) of the
    combination that governs, so the DCR is the ratio it was. The spacing
    limits are those of the governing combination. ``rho_l_max`` is the
    vertical maximum where the code states one, ``None`` where it does not.
    """

    mesh: WallMesh
    rho_t_req: float
    rho_t_min: float
    rho_l_min: float
    s_h_max: Quantity
    s_v_max: Quantity
    DCR: float
    V_capacity: Quantity
    rho_l_max: Optional[float] = None

    def __str__(self) -> str:
        return str(self.mesh)


def _ratio(value: Any) -> float:
    """A reinforcement ratio as a float, whether it arrives as a quantity or not."""
    return float(value.to("").magnitude) if isinstance(value, Quantity) else float(value)


def build_mesh(wall: ShearWall) -> WallMesh:
    """The mesh the wall carries now. Never raises: it describes the section."""
    return WallMesh(
        horizontal=MeshDirection(d_b=wall._d_b_h, s=wall._s_h, rho=_ratio(wall._rho_t), n_curtains=wall._n_curtains),
        vertical=MeshDirection(d_b=wall._d_b_v, s=wall._s_v, rho=_ratio(wall._rho_l), n_curtains=wall._n_curtains),
    )


def capture_wall_shear_check(wall: ShearWall, label: str, state: Any) -> WallShearCheck:
    """The result of the combination just checked, read off its state.

    The mesh is read off the wall here, at the check, and kept on the result:
    it is the one the state was computed with. The rest comes from the
    state's ``public_values``, which every code's wall state answers in the
    names of this result.
    """
    return WallShearCheck(
        label=label,
        mesh=build_mesh(wall),
        rho_t=_ratio(wall._rho_t),
        rho_l=_ratio(wall._rho_l),
        **state.public_values(),
    )


def _governing(checks: Sequence[WallShearCheck]) -> Optional[WallShearCheck]:
    """The combination with the largest DCR; of those tied, the smallest capacity."""
    if not checks:
        return None
    return min(checks, key=lambda check: (-check.DCR, check.V_capacity.magnitude))


def build_wall_shear_design(wall: ShearWall) -> WallShearDesign:
    """The public shear result of ``wall``.

    Built from the checks alone -- their mesh, their envelope -- so it cannot
    pair the mesh the wall carries now with the DCR of another.

    Raises:
        DesignNotRunError: if no shear check or design has been run yet, or
            the mesh was changed by hand since the last one.
    """
    checks: Tuple[WallShearCheck, ...] = tuple(getattr(wall, "_wall_shear_checks", ()))
    governing = _governing(checks)
    if governing is None:
        raise DesignNotRunError(
            "No shear results for the mesh the wall carries. "
            "Run node.design() or node.check_shear() before reading shear_design."
        )
    return WallShearDesign(
        mesh=governing.mesh,
        rho_t_req=max(check.rho_t_req for check in checks),
        rho_t_min=max(check.rho_t_min for check in checks),
        rho_l_min=max(check.rho_l_min for check in checks),
        s_h_max=governing.s_h_max,
        s_v_max=governing.s_v_max,
        DCR=governing.DCR,
        V_capacity=governing.V_capacity,
        rho_l_max=governing.rho_l_max,
    )
