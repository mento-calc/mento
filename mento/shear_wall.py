from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, Dict, List, NoReturn, Optional, Tuple

if TYPE_CHECKING:
    from matplotlib.figure import Figure

import pandas as pd
from pandas import DataFrame

from mento.beam import RectangularBeam
from mento.codes.registry import design_code
from mento.design_warnings import DesignWarning, collect, combination_label, unread_force_warnings, wall_warnings
from mento.forces import Forces
from mento.material import Concrete, SteelBar
from mento.plots.walls import plot_wall_elevation
from mento.reports import walls as wall_reports
from mento.settings import BeamSettings
from mento.units import MPa, Quantity, cm, dimensionless, kN, m, mm

from mento.wall_results import (
    WallMesh,
    WallShearCheck,
    WallShearDesign,
    build_mesh,
    build_wall_shear_design,
    capture_wall_shear_check,
)


class NotABeamError(AttributeError, NotImplementedError):
    """A beam result read on a wall, which is reinforced with a mesh instead.

    Raised by ``wall.reinforcement``, ``wall.flexure_design``,
    ``wall.flexure_checks`` and ``wall.flexure_check_results()``. It is an
    ``AttributeError`` so that the member is missing the way an attribute is:
    ``hasattr(wall, "reinforcement")`` is False and
    ``getattr(wall, "reinforcement", None)`` takes its default, which lets a
    loop over mixed beams and walls ask for the member instead of the class.
    It is a ``NotImplementedError`` too, for the callers that already catch
    that. The message points to ``wall.mesh``, ``wall.shear_design`` and
    ``wall.shear_checks``.
    """


class ShearWall(RectangularBeam):
    """
    Reinforced concrete structural wall — shear check and design.

    The design code is whatever the concrete declares; only codes whose
    registry entry supplies the wall hooks can check one: ACI 318-19 and
    CIRSOC 201-25 (Chapter 11), and EN 1992-1-1 (§6.2 with the detailing of
    §9.6).

    Geometry:
        thickness — wall thickness  (t)         [maps to parent's ``width``]
        length    — wall in-plane length  (lw)  [maps to parent's ``height``]
        height    — wall height  (hw)           [exposed via property; replaces ``hw``]

    ``height`` is the hw of ACI 318-19 / CIRSOC 201-25 Chapter 2: the height
    of the entire wall from base to top, or the clear height of the wall
    segment or wall pier considered -- not the storey height of a
    multi-storey wall. It enters only through hw/lw, which sets αc of
    Eq. (11.5.4.3) and ρl,min of Eq. (11.6.2); a storey height in its place
    makes a slender wall look squat and overstates ØVn. EN 1992-1-1 does not
    read it: its in-plane shear depends on lw and t alone.

    Reinforcement:
        Horizontal distributed bars resist in-plane shear (ρt).
        Vertical distributed bars provide minimum vertical steel (ρl).
        Use set_horizontal_rebar() and set_vertical_rebar() instead of stirrups.
    """

    def __init__(
        self,
        *,
        concrete: Concrete,
        steel_bar: SteelBar,
        c_c: Quantity,
        thickness: Quantity,
        length: Quantity,
        height: Quantity,
        label: Optional[str] = None,
        level: Optional[str] = None,
        settings: Optional[BeamSettings] = None,
    ) -> None:
        self.level: Optional[str] = level

        # Pre-seed `_length` and `_wall_height` so parent's `__post_init__` can read
        # `self.length`/`self.height` (our properties) during cross-section computation.
        # `_wall_height` is bootstrapped to `length` so parent's `_A_x = width * height`
        # produces the correct in-plane cross-section area; we replace it after super().
        self._length: Quantity = length
        self._wall_height: Quantity = length

        super().__init__(
            concrete=concrete,
            steel_bar=steel_bar,
            c_c=c_c,
            width=thickness,
            height=length,
            label=label,
            settings=settings,
        )

        # Replace bootstrap with the actual wall height hw.
        self._wall_height = height
        # _initialize_wall_attributes was already called via __post_init__ above.

    # ------------------------------------------------------------------
    # Wall-friendly dimension properties
    # ------------------------------------------------------------------

    @property
    def thickness(self) -> Quantity:
        """Wall thickness — alias for the parent's ``width`` attribute."""
        return self.width

    @property
    def length(self) -> Quantity:
        """Wall in-plane length (the dimension that resists in-plane shear)."""
        return self._length

    @property
    def height(self) -> Quantity:  # type: ignore[override]
        """Wall height hw — the whole wall, or the segment considered (Chapter 2); replaces the legacy ``hw`` field."""
        return self._wall_height

    @height.setter
    def height(self, value: Quantity) -> None:
        # Parent's dataclass-generated ``__init__`` assigns ``self.height = length``;
        # we accept that without complaint because ``_wall_height`` is bootstrapped to
        # the same value by our ``__init__``. Subsequent user assignments update the
        # wall height hw directly.
        self._wall_height = value

    def __post_init__(self) -> None:
        super().__post_init__()
        self._initialize_wall_attributes()

    # ------------------------------------------------------------------
    # Wall-specific initialization
    # ------------------------------------------------------------------

    def _initialize_wall_attributes(self) -> None:
        self.mode = "shear_wall"

        # Distributed mesh is placed on BOTH faces of the wall (each face = E.F.).
        # The reinforcement ratio counts the bars from every curtain:
        #   ρ = n_curtains · A_b / (t · s)
        self._n_curtains: int = 2

        # Horizontal (transverse) distributed rebar
        self._d_b_h: Quantity = 0 * mm
        self._s_h: Quantity = 0 * mm
        self._rho_t: Quantity = 0 * dimensionless

        # Vertical (longitudinal) distributed rebar
        self._d_b_v: Quantity = 0 * mm
        self._s_v: Quantity = 0 * mm
        self._rho_l: Quantity = 0 * dimensionless

        # Wall shear result quantities
        self._Acv: Quantity = 0 * cm**2
        self._alpha_c: float = 0.0
        self._hw_lw: float = 0.0
        self._f_yt_wall: Quantity = 0 * mm / mm * kN / kN  # typed as dimensionless placeholder; set on first check
        self._V_u: Quantity = 0 * kN
        self._N_u: Quantity = 0 * kN
        self._V_c_wall: Quantity = 0 * kN
        self._V_s_wall: Quantity = 0 * kN
        self._V_n_wall: Quantity = 0 * kN
        self._V_n_max: Quantity = 0 * kN
        self._phi_V_n_wall: Quantity = 0 * kN
        self._phi_V_n_max_wall: Quantity = 0 * kN
        self._DCRv_wall: float = 0.0

        # EN 1992-1-1 result quantities (apply_en_wall_shear_state); per unit
        # length of wall, both faces together, where they are areas.
        self._V_Ed_wall: Quantity = 0 * kN
        self._N_Ed_wall: Quantity = 0 * kN
        self._A_c_wall: Quantity = 0 * cm**2
        self._d_wall: Quantity = 0 * cm
        self._z_wall: Quantity = 0 * cm
        self._f_cd_wall: Quantity = 0 * MPa
        self._f_ywd_wall: Quantity = 0 * MPa
        self._k_wall: float = 0.0
        self._rho_l_shear_wall: float = 0.0
        self._sigma_cp_wall: Quantity = 0 * MPa
        self._alpha_cw_wall: float = 0.0
        self._nu_1_wall: float = 0.0
        self._V_Rd_c_wall: Quantity = 0 * kN
        self._theta_wall: float = 0.0
        self._cot_theta_wall: float = 0.0
        self._V_Rd_max_wall: Quantity = 0 * kN
        self._V_Rd_s_wall: Quantity = 0 * kN
        self._V_Rd_wall: Quantity = 0 * kN
        self._V_Rd_max_45_wall: Quantity = 0 * kN
        self._max_shear_ok_wall: bool = False
        self._rho_w_min_wall: float = 0.0
        self._A_sh_wall: Quantity = 0 * cm**2 / m
        self._A_sv_wall: Quantity = 0 * cm**2 / m
        self._A_sh_str_wall: Quantity = 0 * cm**2 / m
        self._A_sh_w_wall: Quantity = 0 * cm**2 / m
        self._A_sh_min_wall: Quantity = 0 * cm**2 / m
        self._A_sh_req_wall: Quantity = 0 * cm**2 / m
        self._A_sv_min_wall: Quantity = 0 * cm**2 / m
        self._A_sv_max_wall: Quantity = 0 * cm**2 / m
        self._lw_t_wall: float = 0.0

        # Minimum ratios and spacing limits
        self._rho_t_min: Quantity = 0.0025 * dimensionless
        self._rho_l_min: Quantity = 0.0025 * dimensionless
        self._rho_t_req: Quantity = 0 * dimensionless
        self._s_h_max: Quantity = 0 * mm
        self._s_v_max: Quantity = 0 * mm

        # One public result per combination of the last check (wall_results)
        self._wall_shear_checks: List[WallShearCheck] = []
        # The components of those combinations the check passed over (V_y, M_x, M_z)
        self._unread_force_warnings: List[Any] = []

        # Status flags
        self._shear_wall_checked: bool = False
        self._all_wall_shear_checks_passed: bool = False

        # Detail dicts (mirrors beam pattern)
        self._materials_shear_wall: Dict = {}
        self._geometry_shear_wall: Dict = {}
        self._forces_shear_wall: Dict = {}
        self._shear_capacity_wall: Dict = {}
        self._data_min_max_wall: Dict = {}

    # ------------------------------------------------------------------
    # Rebar setters
    # ------------------------------------------------------------------

    def set_horizontal_rebar(self, d_b: Quantity, s: Quantity) -> None:
        """Set distributed horizontal (transverse) reinforcement.

        Bars are placed on each face (E.F.):  ρt = n_curtains · Ab / (t × s_h)
        A zero spacing means no rebar, which clears the horizontal reinforcement.

        The shear results of the last check belong to the mesh they were
        checked with, so they are dropped: ``shear_checks`` and ``warnings``
        are empty, ``shear_design`` raises and the notebook views
        (``shear_results``, ``results``) show no shear until the next check or
        design.
        """
        self._d_b_h = d_b
        self._s_h = s
        if s == 0 * mm:
            self._rho_t = 0 * dimensionless
        else:
            A_b = math.pi / 4 * d_b**2
            self._rho_t = (self._n_curtains * A_b / (self.thickness * s)).to("")
        self._drop_shear_results()

    def set_vertical_rebar(self, d_b: Quantity, s: Quantity) -> None:
        """Set distributed vertical reinforcement.

        Bars are placed on each face (E.F.):  ρl = n_curtains · Ab / (t × s_v)
        A zero spacing means no rebar, which clears the vertical reinforcement.

        Drops the shear results of the last check, as
        :meth:`set_horizontal_rebar` does.
        """
        self._d_b_v = d_b
        self._s_v = s
        if s == 0 * mm:
            self._rho_l = 0 * dimensionless
        else:
            A_b = math.pi / 4 * d_b**2
            self._rho_l = (self._n_curtains * A_b / (self.thickness * s)).to("")
        self._drop_shear_results()

    def _drop_shear_results(self) -> None:
        """Forget the shear results of the mesh the wall carried before.

        The public results (``shear_checks``) and the notebook views, which
        read the report tables of the last :meth:`check_shear`: the markdown
        summary printed the mesh the wall carries now beside the ρt and the
        DCR of the one that was checked.
        """
        self._wall_shear_checks = []
        self._unread_force_warnings = []
        self._shear_wall_checked = False

    # ------------------------------------------------------------------
    # Shear check and design (override RectangularBeam)
    # ------------------------------------------------------------------

    def check_shear(self, forces: list[Forces]) -> DataFrame:
        self._shear_results_list: list = []
        self._shear_results_detailed_list: Dict = {}
        max_dcr: float = 0.0
        self._limiting_case_shear_details = None
        self._wall_shear_checks = []
        self._unread_force_warnings = _unread_warnings(forces)

        for force in forces:
            code = design_code(self.concrete)
            state = code.requires("check_shear_wall")(self, force)
            # The report tables read the wall, so the state is applied here
            # and not on a values-only path.
            code.requires("apply_wall_shear_state")(self, state)
            self._wall_shear_checks.append(capture_wall_shear_check(self, force.label, state))
            result = wall_reports.build_wall_shear_report(self, force)

            self._shear_results_list.append(result)
            self._shear_results_detailed_list[force.id] = {
                "forces": self._forces_shear_wall.copy(),
                "shear_capacity": self._shear_capacity_wall.copy(),
                "min_max": self._data_min_max_wall.copy(),
                "checks_pass": self._all_wall_shear_checks_passed,
                # The public result of this combination, which the one-line
                # summary reads in whichever code's symbols.
                "check": self._wall_shear_checks[-1],
            }

            current_dcr = result["DCR"].iloc[0]
            if current_dcr >= max_dcr:
                max_dcr = current_dcr
                self._limiting_case_shear = result
                self._limiting_case_shear_details = self._shear_results_detailed_list[force.id]

        all_data = pd.concat(self._shear_results_list, ignore_index=True)
        units_row = self._get_units_row_shear_wall()
        all_results = pd.concat([units_row, all_data], ignore_index=True)
        self.limiting_case_shear = all_data.loc[all_data["DCR"].idxmax()]

        self._shear_wall_checked = True
        self._shear_checked = True
        return all_results

    def shear_check_results(self, forces: list[Forces]) -> Tuple[WallShearCheck, ...]:  # type: ignore[override]
        """Check shear and return one result per combination, building no report.

        The same numbers as :meth:`check_shear`, without the report tables;
        nothing is written to the wall but the results themselves.
        """
        code = design_code(self.concrete)
        self._wall_shear_checks = [
            capture_wall_shear_check(self, force.label, code.requires("check_shear_wall")(self, force))
            for force in forces
        ]
        self._unread_force_warnings = _unread_warnings(forces)
        return tuple(self._wall_shear_checks)

    def design_shear(self, forces: list[Forces]) -> DataFrame:
        """Design the horizontal (shear) mesh and the minimum vertical mesh.

        Selects a bar diameter + spacing for both directions against the
        worst-case force combination, applies them, and returns the
        re-evaluated check results.
        """
        if not forces:
            raise ValueError("design_shear requires at least one Forces object.")

        design_code(self.concrete).requires("design_shear_wall")(self, forces)

        # Re-run the check so the returned DataFrame / detail dicts reflect the mesh.
        return self.check_shear(forces)

    # ------------------------------------------------------------------
    # Units header row
    # ------------------------------------------------------------------

    def _get_units_row_shear_wall(self) -> pd.DataFrame:
        """The units row of :meth:`check_shear`, in the columns of the wall's code."""
        return wall_reports.wall_units_row(self)

    # ------------------------------------------------------------------
    # Top-level check / Node integration
    # ------------------------------------------------------------------

    def check(self, forces: list[Forces]) -> None:
        """Complete check for a shear wall: shear only (no flexure in Phase 0)."""
        self.check_shear(forces)

    def design(self, forces: list[Forces]) -> None:
        """Complete design for a shear wall: shear only (no flexure in Phase 0)."""
        self.design_shear(forces)

    # ------------------------------------------------------------------
    # Results — the mesh and the shear results, as plain data
    # ------------------------------------------------------------------

    @property
    def mesh(self) -> WallMesh:
        """The distributed reinforcement this wall carries now, as plain data.

        Readable at any time -- it describes the section, not a result::

            wall.mesh.horizontal.d_b, wall.mesh.horizontal.s, wall.mesh.horizontal.rho
            wall.mesh.vertical.A_s     # per unit length, both curtains
        """
        return build_mesh(self)

    @property
    def shear_checks(self) -> Tuple[WallShearCheck, ...]:  # type: ignore[override]
        """One immutable shear result per combination of the last check.

        Each carries the mesh it was checked with. Empty until a check or
        design has run, and again once the mesh is changed by hand.
        """
        return tuple(self._wall_shear_checks)

    @property
    def shear_design(self) -> WallShearDesign:  # type: ignore[override]
        """The checked mesh and the envelope of the last shear check or design.

        Raises:
            DesignNotRunError: if no shear check or design has been run, or
                the mesh was changed by hand since the last one.
        """
        return build_wall_shear_design(self)

    @property
    def warnings(self) -> Tuple[DesignWarning, ...]:  # type: ignore[override]
        """The mesh limits the wall misses under the last check, as data.

        Empty until a check or design has run, and again once the mesh is
        changed by hand: the limits are those of the mesh that was checked.
        See :mod:`mento.design_warnings`.
        """
        checks = tuple(self._wall_shear_checks)
        mesh = checks[0].mesh if checks else self.mesh
        unread = list(self._unread_force_warnings) if checks else []
        return collect(wall_warnings(self, mesh, checks) + unread)

    # The beam's shear attributes, read off the wall. A wall inherits ``V_c`` and
    # ``f_yt`` from RectangularBeam, whose shear check fills them; the wall has a
    # check of its own (§11.5.4) and they used to stay at the zeros the beam starts
    # with. They name the same quantities on a wall, so they read the wall's. The
    # setter is what the inherited initialisation writes its zero through. They
    # are ACI 318-19 / CIRSOC 201-25 quantities and stay at zero on an EN wall,
    # whose resistances are in its shear_checks (V_capacity is V_Rd).

    @property  # type: ignore[override]
    def V_c(self) -> Quantity:
        """Nominal shear strength of the concrete, V_c of ACI 318-19 §11.5.4.3, from the last check."""
        return self._V_c_wall

    @V_c.setter
    def V_c(self, value: Quantity) -> None:
        self._V_c_wall = value

    @property  # type: ignore[override]
    def f_yt(self) -> Quantity:
        """Yield strength of the horizontal mesh for shear, f_yt of ACI 318-19 §11.5.4.8, from the last check."""
        return self._f_yt_wall

    @f_yt.setter
    def f_yt(self, value: Quantity) -> None:
        self._f_yt_wall = value

    def _not_a_beam(self, name: str) -> NoReturn:
        raise NotABeamError(
            f"ShearWall has no {name}: it is reinforced with a distributed mesh. "
            "Read wall.mesh, wall.shear_design and wall.shear_checks instead."
        )

    @property
    def reinforcement(self) -> NoReturn:  # type: ignore[override]
        """Not available on a wall: see :attr:`mesh`. Raises :class:`NotABeamError`."""
        self._not_a_beam("beam reinforcement")

    @property
    def section_geometry(self) -> NoReturn:  # type: ignore[override]
        """Not available on a wall: it has no bars or stirrups to place. Raises :class:`NotABeamError`."""
        self._not_a_beam("section geometry")

    @property
    def skin_reinforcement(self) -> NoReturn:  # type: ignore[override]
        """Beam skin proposals do not describe a wall's distributed mesh."""
        self._not_a_beam("beam skin reinforcement")

    @property
    def skin_service_cases(self) -> NoReturn:  # type: ignore[override]
        self._not_a_beam("beam skin service cases")

    def set_skin_service_cases(self, cases: list[Any]) -> NoReturn:
        self._not_a_beam("beam skin service cases")

    @property
    def flexure_design(self) -> NoReturn:  # type: ignore[override]
        """Not available on a wall: flexure is not implemented (Phase 0). Raises :class:`NotABeamError`."""
        self._not_a_beam("flexure design")

    @property
    def flexure_checks(self) -> NoReturn:  # type: ignore[override]
        """Not available on a wall: flexure is not implemented (Phase 0). Raises :class:`NotABeamError`."""
        self._not_a_beam("flexure checks")

    def flexure_check_results(self, forces: list[Forces]) -> NoReturn:  # type: ignore[override]
        """Not available on a wall: flexure is not implemented (Phase 0). Raises :class:`NotABeamError`."""
        self._not_a_beam("flexure check")

    def check_flexure(self, forces: list[Forces]) -> DataFrame:  # type: ignore[override]
        raise NotImplementedError("Flexure check is not implemented for ShearWall (Phase 0).")

    def design_flexure(self, forces: list[Forces]) -> DataFrame:  # type: ignore[override]
        raise NotImplementedError("Flexure design is not implemented for ShearWall (Phase 0).")

    def flexure_results_detailed(self, force: Optional[Forces] = None) -> None:
        raise NotImplementedError("Flexure results are not implemented for ShearWall (Phase 0).")

    # ------------------------------------------------------------------
    # Presentation — every one of these delegates, as on RectangularBeam
    # ------------------------------------------------------------------

    def flexure_results_detailed_doc(self, force: Optional[Forces] = None) -> None:
        return wall_reports.wall_flexure_results_detailed_doc(self, force)

    @property
    def data(self) -> None:
        """Show the wall's basic data as Markdown."""
        return wall_reports.wall_data(self)

    @property
    def shear_results(self) -> None:  # type: ignore[override]
        """Show a summary of the shear results as Markdown."""
        return wall_reports.wall_shear_results(self)

    def shear_results_detailed(self, force: Optional[Forces] = None) -> None:  # type: ignore[override]
        """Print the detailed shear tables."""
        return wall_reports.wall_shear_results_detailed(self, force)

    def shear_results_detailed_doc(self, force: Optional[Forces] = None) -> None:  # type: ignore[override]
        """Write the detailed shear results to a Word document."""
        return wall_reports.wall_shear_results_detailed_doc(self, force)

    def plot(self, show: bool = False) -> "Figure":  # type: ignore[override]
        """Draw the wall elevation with its reinforcement."""
        return plot_wall_elevation(self, show=show)

    @property
    def results(self) -> None:  # type: ignore[override]
        """Display wall data + shear results in Markdown (no flexure)."""
        self.data
        if self._shear_wall_checked:
            self.shear_results
        return None

    # ------------------------------------------------------------------
    # Detailed results
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Plot — wall plan view: length lw (horizontal) × thickness t
    # ------------------------------------------------------------------


def _unread_warnings(forces: list[Forces]) -> List[Any]:
    """The components of ``forces`` a wall check does not read; see ``unread_force_warnings``."""
    return [
        raw
        for position, force in enumerate(forces, 1)
        for raw in unread_force_warnings(force, combination_label(force.label, position))
    ]
