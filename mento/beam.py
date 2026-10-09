from contextlib import contextmanager
from dataclasses import dataclass, replace
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    FrozenSet,
    Iterable,
    Iterator,
    Literal,
    NamedTuple,
    Optional,
    Tuple,
)

if TYPE_CHECKING:
    from matplotlib.figure import Figure

    from mento.skin_reinforcement import ManualSkinRebar, SkinReinforcementRequirement
    from mento.skin_service import SkinServiceCase
import math

from mento.compression_detailing import CompressionDetailing

import numpy as np
import pandas as pd
from pandas import DataFrame

from mento.bar_sizes import bar_designation
from mento.codes.registry import design_code, units_row
from mento.design_results import (
    FlexureCheck,
    FlexureDesign,
    RebarLayer,
    RebarOption,
    SectionReinforcement,
    ShearCheck,
    ShearDesign,
    StirrupOption,
    _transverse_stirrup_count,
    build_flexure_design,
    build_reinforcement,
    build_shear_design,
    capture_flexure_check,
    capture_shear_check,
)
from mento.design_warnings import (
    DesignWarning,
    collect,
    combination_label,
    flexure_warnings,
    compression_detailing_warnings,
    shear_warnings,
    shortfall_warnings,
    skin_warnings,
    spacing_warnings,
    unread_force_warnings,
)
from mento.verification import resolve_legs, validate_supported_forces, verification_status
from mento.forces import Forces
from mento.plots.sections import plot_beam_section
from mento.precompute import refresh_section_floats
from mento.rebar import Rebar, leg_count

# from devtools import debug
from mento.rectangular import RectangularSection
from mento.reports import views
from mento.reports.documents import flexure_report_doc, shear_report_doc
from mento.reports.tables import build_flexure_report, build_shear_report
from mento.section_geometry import SectionGeometry, build_section_geometry
from mento.settings import BeamSettings
from mento.units import Quantity, cm, dimensionless, inch, kN, m, mm


def _positive_or_none(value: Quantity) -> Optional[Quantity]:
    """A spacing limit of a search row, or None where the row set none (zero)."""
    return value if value.magnitude > 0 else None


class _Verdict(NamedTuple):
    """What values-only checks of the section as it stands found, over every combination.

    ``DCR`` is the worst ratio checked; ``clean`` says the checks left no
    warning and the reinforcement keeps within the code's limits; and
    ``compression_faces`` are the faces some combination relies on as
    compression steel (see :meth:`RectangularBeam._compression_face_of`), which
    the stirrups of that section have to brace. ``fits`` says the bars of
    the faces judged fit the width -- no spacing warning, the vibrator's gap
    on top included -- whatever else the checks found, and ``admissible``
    that the face each combination puts in tension keeps within the code's
    limit on its reinforcement (``DesignCode.flexure_admissible``).
    """

    DCR: float
    clean: bool
    compression_faces: FrozenSet[str] = frozenset()
    fits: bool = True
    admissible: bool = True

    @property
    def passes(self) -> bool:
        return self.clean and self.DCR <= 1.0


class _DesignCodeAttributes:
    """Attributes the design codes write onto a section, declared for type checkers.

    Kept off ``RectangularBeam`` itself: that class is a dataclass, so an
    annotation in its body -- even one guarded by ``TYPE_CHECKING`` -- counts as a
    field to a type checker, and every private name below showed up in the editor
    as a required constructor argument. A plain base class contributes no fields,
    so the synthesized signature stays the handful the caller actually passes.
    """

    # ------------------------------------------------------------------
    # The ADR-0001 compatibility layer: declared, never assigned here.
    #
    # A check no longer writes its results to the section. These exist because
    # the report tables still read them off the element, and each design code
    # zeroes its own set through ``DesignCode.initialize_attributes``, so a
    # table asked for before any check has run finds a number instead of an
    # AttributeError.
    #
    # Declared under TYPE_CHECKING so the type checker knows they exist and
    # what they hold, without adding anything at runtime.
    #
    # They leave with the compatibility layer. A new design code should not add
    # to this list -- its report tables should read the check state instead.
    # ------------------------------------------------------------------
    if TYPE_CHECKING:
        # ACI 318-19 and CIRSOC 201-25
        _phi_V_n: Quantity
        _phi_V_s: Quantity
        _phi_V_c: Quantity
        _phi_V_max: Quantity
        _V_u: Quantity
        _M_u: Quantity
        _M_u_bot: Quantity
        _M_u_top: Quantity
        _N_u: Quantity
        _A_cv: Quantity
        _k_c_min: Quantity
        _sigma_Nu: Quantity
        V_c: Quantity
        _rho_w: Quantity
        f_yt: Quantity
        _phi_M_n_bot: Quantity
        _phi_M_n_top: Quantity
        _d_b_max_bot: Quantity
        _d_b_max_top: Quantity
        _lambda_s: float
        _max_shear_ok: bool
        _A_s_bool_bot: bool
        _A_s_bool_top: bool
        # EN 1992-2004
        _V_Ed_1: Quantity
        _V_Ed_2: Quantity
        _N_Ed: Quantity
        _M_Ed: Quantity
        _M_Ed_bot: Quantity
        _M_Ed_top: Quantity
        _M_Rd_bot: Quantity
        _M_Rd_top: Quantity
        _sigma_cd: Quantity
        _sigma_cp: Quantity
        _V_Rd_c: Quantity
        _V_Rd_s: Quantity
        _V_Rd_max: Quantity
        _V_Rd: Quantity
        _f_ywk: Quantity
        _f_ywd: Quantity
        _f_cd: Quantity
        _f_cd_shear: Quantity
        _A_p: Quantity
        _z: Quantity
        _k_value: float
        _theta: float
        _cot_theta: float
        _rho_l_shear_bot: Quantity
        _rho_l_shear_top: Quantity
        # Both
        _A_s_min_bot: Quantity
        _A_s_min_top: Quantity
        _A_s_min_eff_bot: Quantity
        _A_s_min_eff_top: Quantity
        _A_s_max_bot: Quantity
        _A_s_max_top: Quantity
        _A_s_max_eff_bot: Quantity
        _A_s_max_eff_top: Quantity
        flexure_design_results_bot: Any
        flexure_design_results_top: Any


@dataclass
class RectangularBeam(RectangularSection, _DesignCodeAttributes):
    """
    Represents a reinforced concrete rectangular beam section with methods for design, checking,
    and visualization of longitudinal and transverse reinforcement according to various design codes.

    Attributes:
        settings (BeamSettings): Access to global design rules and settings.

    Methods:
        set_transverse_rebar(n_stirrups, d_b, s_l):
            Sets the transverse (stirrup) rebar configuration for the beam.
        set_longitudinal_rebar_bot(n1, d_b1, n2, d_b2, n3, d_b3, n4, d_b4):
            Sets the bottom longitudinal rebar configuration.
        set_longitudinal_rebar_top(n1, d_b1, n2, d_b2, n3, d_b3, n4, d_b4):
            Sets the top longitudinal rebar configuration.
        design_flexure(forces):
            Designs the flexural reinforcement for the beam based on provided forces and design code.
        check_flexure(forces):
            Checks the flexural capacity for all provided forces and stores results.
        design_shear(forces):
            Designs the shear reinforcement for the beam based on provided forces and design code.
        check_shear(forces):
            Checks the shear capacity for all provided forces and stores results.
        data:
            Property. Displays basic beam data in Markdown format.
        flexure_results:
            Property. Displays summary of flexural design/check results in Markdown format.
        shear_results:
            Property. Displays summary of shear design/check results in Markdown format.
        results:
            Property. Displays all available results (properties, flexure, shear) in Markdown format.
        flexure_results_detailed(force=None):
            Displays detailed flexure results for a specific force or the limiting case.
        flexure_results_detailed_doc(force=None):
            Exports detailed flexure results to a Word document.
        shear_results_detailed(force=None):
            Displays detailed shear results for a specific force or the limiting case.
        shear_results_detailed_doc(force=None):
            Exports detailed shear results to a Word document.
        plot():
            Plots the beam section with its rebar.

    Usage:
        - Instantiate with required section and material properties.
        - Use set_longitudinal_rebar_* and set_transverse_rebar to configure reinforcement.
        - Call design_flexure and design_shear to perform design.
        - Use flexure_results, shear_results, and results properties for summary output.
        - Use flexure_results_detailed and shear_results_detailed for detailed output.
        - Use plot() to visualize the rebar arrangement.

    Note:
        This class is intended for use in reinforced concrete beam design workflows,
        supporting multiple design codes and detailed reporting.
    """

    settings: Optional[BeamSettings] = None

    def __post_init__(self) -> None:
        super().__post_init__()  # Call parent attributes
        if not self.settings:
            # create defaults based on concrete's unit system
            self.settings = BeamSettings(unit_system=self.concrete.unit_system)
        else:
            # Fill missing fields with defaults from the given unit system
            # (ensures your partial BeamSettings still gets the rest of defaults)
            self.settings.unit_system = self.concrete.unit_system
            self.settings.__post_init__()  # recompute missing fields
        self._initialize_attributes()

    ##########################################################
    # INITIALIZE ATTRIBUTES
    ##########################################################

    def _initialize_attributes(self) -> None:
        """Initialize all attributes of the beam."""
        self.mode = "beam"
        # Stirrups and shear attributes
        self._stirrup_d_b = self.settings.stirrup_diameter_ini
        self._stirrup_s_l: Quantity = 0 * cm
        self._stirrup_s_w: Quantity = 0 * cm
        self._stirrup_s_max_l: Quantity = 0 * cm
        self._stirrup_s_max_w: Quantity = 0 * cm
        self._stirrup_n: float = 0  # Equivalente de dos ramas; no cuenta piezas físicas.
        self._A_v_min: Quantity = 0 * cm**2 / m
        self._A_v: Quantity = 0 * cm**2 / m
        self._A_s_req_bot: Quantity = 0 * cm**2
        self._A_s_req_top: Quantity = 0 * cm**2
        self._A_v_req: Quantity = 0 * cm**2 / m
        self._A_s_tension: Quantity = 0 * cm**2
        self._DCRv: float = 0
        self._DCRb_top: float = 0
        self._DCRb_bot: float = 0
        # One immutable result per load combination, appended by check_flexure and
        # check_shear. The attributes above only hold the combination that ran last;
        # enveloping is a pure operation over these lists.
        self._flexure_checks: list[FlexureCheck] = []
        self._shear_checks: list[ShearCheck] = []
        self._alpha: float = math.radians(90)
        self._V_s_req: Quantity = 0 * kN
        # What the last design found besides what it applied, best first, and
        # the faces it could not fit a layout on. See design_results. The pool
        # behind each face's options holds the rows of the search still to be
        # verified on the finished section, each with the row it is built from.
        self._flexure_options_b: Tuple[RebarOption, ...] = ()
        self._flexure_options_t: Tuple[RebarOption, ...] = ()
        self._flexure_option_pool_b: Tuple[Tuple[RebarOption, Dict[str, Any]], ...] = ()
        self._flexure_option_pool_t: Tuple[Tuple[RebarOption, Dict[str, Any]], ...] = ()
        self._shear_options: Tuple[StirrupOption, ...] = ()
        self._infeasible_faces: set[str] = set()
        # The faces the last design could not bring up to what they need, as
        # (area asked for, area left), by face ("bot"/"top"). See design_warnings.
        self._short_faces: Dict[str, Tuple[Quantity, Quantity]] = {}
        # The detailing limits each combination of the last checks missed,
        # before they are worded; `warnings` collapses and words them.
        self._flexure_warnings: list[Any] = []
        self._shear_warnings: list[Any] = []

        # Design checks and effective heights
        self._rho_l_bot: Quantity = 0 * dimensionless
        self._rho_l_top: Quantity = 0 * dimensionless
        self._bot_rebar_centroid = 0 * mm
        self._top_rebar_centroid = 0 * mm
        self._c_d_top: float = 0
        self._c_d_bot: float = 0
        self._shear_checked = False  # Tracks if shear check or design has been done
        self._flexure_checked = False  # Tracks if shear check or design has been done
        self._skin_service_cases: tuple[SkinServiceCase, ...] = ()
        self._manual_skin_rebar: Optional[ManualSkinRebar] = None
        self._skin_service_reference: tuple[Any, ...] | None = None
        # Depth of design calls in progress: their own bar placements keep the results.
        self._designing = 0
        self._doubly_reinforced = False  # Tracks if doubly reinforced section is used
        # The faces whose bars some combination of the last flexure check
        # relied on as compression steel: what the stirrups have to support
        # (ACI 318-19 / CIRSOC 201-25 §9.7.6.4.1). See _note_compression_face.
        self._compression_faces: set[str] = set()

        # Initialize default concrete beam attributes
        self._initialize_code_attributes()
        # Longitudinal rebar attributes
        self._initialize_longitudinal_rebar_attributes()

        # Rendered Markdown of the last view asked for, kept so a caller can
        # read the text back instead of only seeing it displayed.
        self._md_data: str = ""
        self._md_flexure_results: str = ""
        self._md_shear_results: str = ""

        # Results attributes
        self._materials_shear: Dict = {}
        self._geometry_shear: Dict = {}
        self._forces_shear: Dict = {}
        self._all_shear_checks_passed: bool = False
        self._data_min_max_shear: Dict = {}
        self._shear_reinforcement: Dict = {}
        self._shear_concrete: Dict = {}
        self._shear_all_checks: bool = False

        self._materials_flexure: Dict = {}
        self._geometry_flexure: Dict = {}
        self._forces_flexure: Dict = {}
        self._all_flexure_checks_passed: bool = False
        self._data_min_max_flexure: Dict = {}
        self._flexure_capacity_bot: Dict = {}
        self._flexure_capacity_top: Dict = {}
        self._flexure_all_checks: bool = False

    def _initialize_code_attributes(self) -> None:
        design_code(self.concrete).initialize_attributes(self)

    def _initialize_longitudinal_rebar_attributes(self) -> None:
        """Initialize all rebar-related attributes with default values."""
        # The bar counts are typed as floats: a beam's is a whole number of
        # bars, a slab strip's is width / s, the bars per strip its spacing
        # gives, which need not be (see mento.slab._bars_at_spacing).
        self._n1_b: float
        self._n2_b: float
        self._n3_b: float
        self._n4_b: float
        self._n1_t: float
        self._n2_t: float
        self._n3_t: float
        self._n4_t: float
        # Bottom rebar defaults
        self._n2_b, self._d_b2_b = 0, 0 * mm
        self._n3_b, self._d_b3_b = 0, 0 * mm
        self._n4_b, self._d_b4_b = 0, 0 * mm

        # Top rebar defaults
        self._n2_t, self._d_b2_t = 0, 0 * mm
        self._n3_t, self._d_b3_t = 0, 0 * mm
        self._n4_t, self._d_b4_t = 0, 0 * mm

        # Unit system default starter rebar for initial effective height
        if self.concrete.unit_system == "metric":
            self._n1_b, self._d_b1_b = 2, 8 * mm
            self._n1_t, self._d_b1_t = 2, 8 * mm
        else:
            self._n1_b, self._d_b1_b = 2, 3 / 8 * inch
            self._n1_t, self._d_b1_t = 2, 3 / 8 * inch

        # Update dependent attributes
        self._update_longitudinal_rebar_attributes()

    def _create_rebar_designer(self) -> Rebar:
        """Factory for the longitudinal reinforcement optimizer."""
        return Rebar(self)

    def _apply_longitudinal_design_bot(self, design: Any) -> None:
        """Apply a discrete design to the bottom reinforcement.

        ``design`` is any mapping with the rebar-designer keys (n_1..n_4,
        d_b1..d_b4); the designer hands back a pandas row, tests pass plain
        dicts.
        """
        self.set_longitudinal_rebar_bot(
            int(design.get("n_1", 0)),
            design.get("d_b1"),
            int(design.get("n_2", 0)),
            design.get("d_b2"),
            int(design.get("n_3", 0)),
            design.get("d_b3"),
            int(design.get("n_4", 0)),
            design.get("d_b4"),
        )

    def _apply_longitudinal_design_top(self, design: Any) -> None:
        """Apply a discrete design to the top reinforcement.

        See :meth:`_apply_longitudinal_design_bot` for the accepted shape.
        """
        self.set_longitudinal_rebar_top(
            int(design.get("n_1", 0)),
            design.get("d_b1"),
            int(design.get("n_2", 0)),
            design.get("d_b2"),
            int(design.get("n_3", 0)),
            design.get("d_b3"),
            int(design.get("n_4", 0)),
            design.get("d_b4"),
        )

    def _finalize_longitudinal_design(
        self,
        A_req_bot: Quantity,
        A_req_top: Quantity,
        resists: Callable[[], bool],
    ) -> None:
        """Last word on the layout, once both faces have been designed.

        Nothing to do for a beam: its two faces are detailed independently, so
        the layout the design arrived at is the layout it keeps. It exists for
        the elements whose faces are tied to each other -- a footing is placed
        as one mat, and chooses the module and both bars here.

        Args:
            A_req_bot: Steel the bottom face has to carry, minimum included.
            A_req_top: The same for the top.
            resists: Whether the layout now on the section resists both design
                moments. An element that re-selects bars has to ask, since a
                thicker bar sits deeper and lowers the effective depth it was
                chosen against.
        """

    def _option_layers(self, design: Any) -> Tuple[RebarLayer, ...]:
        """The layers a row of the longitudinal search would put on a face.

        The same reading :meth:`_apply_longitudinal_design_bot` makes of a row,
        without applying it: a beam carries each bar group as it comes.
        """
        layers = []
        for index in (1, 2, 3, 4):
            n = int(design.get(f"n_{index}", 0) or 0)
            d_b = design.get(f"d_b{index}")
            if n and d_b is not None and d_b.magnitude > 0:
                layers.append(RebarLayer(n=n, d_b=d_b))
        return tuple(layers)

    #: Rows of the search a face keeps back for verification, as a multiple of
    #: the options it will show: dropping the ones the finished section fails
    #: with still leaves the number asked for, in most cases.
    _OPTION_POOL_FACTOR = 3
    #: Rounds a full design may redo its flexure with the stirrup the shear
    #: design chose, when that stirrup moved the bars past what they carry.
    #: One is what it takes when a layout exists; the bound is for a section
    #: that has none, which then ends on a repeated state anyway.
    _DESIGN_ROUNDS = 3
    #: The ACI 318-19 / CIRSOC 201-25 article that holds this element to a
    #: tension-controlled section, which not_tension_controlled quotes.
    _tension_controlled_clause = "9.3.3.1"

    def _record_longitudinal_options(self, face: str, design: Any, table: Any) -> None:
        """Keep the layouts the search ranked for one face, the applied one first.

        Called once a face is settled, with the row applied to it and the table
        that row headed -- the table of the search run with the mechanical cover
        the design finished on. The first option is read off the section rather
        than off the row, so it is the layout the face carries even where
        something after the search changed it (a footing mat is chosen as a
        whole, after both faces). The rest follow in the order the search
        ranked them, skipping any that would be laid out the same as one
        already kept -- but they are not offered from here. The search ranks
        them by area against the requirement of its own iteration, read with
        the starter stirrup, and the section they end up on is another: the
        stirrup the shear design picks sits the bars deeper, and a doubly
        reinforced face's bars are the other face's compression steel. So the
        rows are pooled, and :meth:`_verify_longitudinal_options` builds each
        on the finished section before it is kept.

        Args:
            face: ``"b"`` or ``"t"``.
            design: The row applied to the face, or ``None`` if the search found
                none.
            table: The ranked table ``design`` came from, or ``None``.
        """

        def functional(row: Any) -> Optional[float]:
            value = row.get("functional") if hasattr(row, "get") else None
            if value is None or pd.isna(value):
                return None
            return float(value)

        applied = self.reinforcement.bottom if face == "b" else self.reinforcement.top
        area_unit = applied.A_s.units
        first = RebarOption(
            layers=applied.layers,
            A_s=applied.A_s,
            functional=(
                functional(design) if design is not None and self._option_layers(design) == applied.layers else None
            ),
        )
        pool: list[Tuple[RebarOption, Dict[str, Any]]] = []
        seen = [first.layers]
        limit = int(self.settings.design_options) * self._OPTION_POOL_FACTOR
        if table is not None and not table.empty:
            for _, row in table.iterrows():
                if len(pool) + 1 >= limit:
                    break
                layers = self._option_layers(row)
                if layers in seen:
                    continue
                seen.append(layers)
                A_s = sum((layer.A_s for layer in layers), 0 * area_unit)
                option = RebarOption(layers=layers, A_s=A_s.to(area_unit), functional=functional(row))
                pool.append((option, dict(row)))
        setattr(self, f"_flexure_options_{face}", (first,))
        setattr(self, f"_flexure_option_pool_{face}", tuple(pool))

    def _longitudinal_snapshot(self, face: str) -> Dict[str, Any]:
        """The bars of one face as attributes, to put back after trying another layout.

        Counts and diameters on a beam; on a slab the spacings as well, since
        its counts are derived from them.
        """
        names = [f"_{kind}{index}_{face}" for index in (1, 2, 3, 4) for kind in ("n", "d_b", "s_b")]
        return {name: getattr(self, name) for name in names if hasattr(self, name)}

    def _restore_longitudinal(self, snapshot: Dict[str, Any]) -> None:
        for name, value in snapshot.items():
            setattr(self, name, value)
        self._update_longitudinal_rebar_attributes()

    def _flexure_verdict(self, forces: list[Forces], faces: Tuple[str, ...]) -> _Verdict:
        """The flexure of the section as it stands, under ``forces``.

        The worst ratio over both faces and every combination. It passes when
        that ratio is at most 1, the bars of ``faces`` (``"bot"``/``"top"``)
        fit, the check leaves no steel-area warning, and the face each
        combination puts in tension keeps within the code's limit on its
        reinforcement -- the registry's ``flexure_admissible``, tension-
        controlled under ACI 318-19 / CIRSOC 201-25 §9.3.3.1 and the 4 % of
        EN 1992-1-1 §9.2.1.1(3), the same limit the design holds its own
        layout to. Every stirrup leg holds a bar of each face a combination
        puts in tension: its first layer carries at least as many bars as the
        section has legs, or its bars do not "fit" the cage. It also names the
        faces the section relies on as compression steel. Values-only checks,
        so the section is not written to.
        """
        admissible = design_code(self.concrete).flexure_admissible
        names = tuple("bottom" if face == "bot" else "top" for face in faces)
        worst = 0.0
        fits = not any(raw.face in names for raw in spacing_warnings(self))
        clean = fits
        within = True
        compression: set[str] = set()
        legs = leg_count(self)
        for force in forces:
            state = self._run_flexure_check(force, report=False)
            check = capture_flexure_check(self, force.label, state, has_axial_force=force.N_x.magnitude != 0)
            pulled = "bot" if force._M_y > 0 * kN * m else "top" if force._M_y < 0 * kN * m else None
            if pulled in faces and legs:
                bars = (self._n1_b + self._n2_b) if pulled == "bot" else (self._n1_t + self._n2_t)
                fits = fits and bars >= legs
            worst = max(worst, check.bottom.DCR, check.top.DCR)
            clean = clean and not flexure_warnings(self, force.label, state)
            tension = "bot" if force._M_y > 0 * kN * m else "top" if force._M_y < 0 * kN * m else None
            if tension is not None and admissible is not None and not admissible(self, tension):
                within = False
            braced = self._compression_face_of(force, state)
            if braced is not None:
                compression.add(braced)
        return _Verdict(worst, clean and fits and within, frozenset(compression), fits, within)

    def _verify_longitudinal_options(self, forces: list[Forces]) -> None:
        """Keep, of each face's pooled alternatives, those the finished section passes with.

        Each is built on the section as the design left it -- its stirrups,
        the other face as applied -- and judged by :meth:`_section_verdict`
        under every combination: flexure and shear. The bars set the depth
        the shear is read at as much as the moment's, ``d = min(d_bot,
        d_top)``, so a layout in two layers, or of thicker bars, lowers the
        section's shear limit and can halve its stirrup spacing limit (ACI
        318-19 Table 9.7.6.2.2): an ACI 12x25 whose 2Ø10 carry 78 kN at
        shear DCR 0.994 was offered 2Ø10 + 2Ø10, DCR 1.085 once built. And a
        layout that makes the section rely on its compression steel owes that
        steel stirrups of its own (§9.7.6.4). The ones that pass are offered,
        best first, up to the number the settings ask for, each with its
        ``section_DCR``. The applied layout is first whatever its verdict,
        with its own. Then the face is put back. Run after a flexure design, and again
        once the shear design has settled the stirrups the section is built
        with.

        The rows go on through the public setters, which clear the face's
        ``bars_do_not_fit`` -- right for bars set by hand, wrong for a layout
        the design only tries -- so the faces the search gave up on are put
        back with the bars.
        """
        limit = int(self.settings.design_options)
        infeasible = set(self._infeasible_faces)
        for face, suffix in (("bot", "b"), ("top", "t")):
            # A design records at least the layout each face carries, so there
            # is always a first option to judge.
            options: Tuple[RebarOption, ...] = getattr(self, f"_flexure_options_{suffix}")
            kept = [replace(options[0], section_DCR=self._section_verdict(forces, (face,)).DCR)]
            pool: Tuple[Tuple[RebarOption, Dict[str, Any]], ...] = getattr(self, f"_flexure_option_pool_{suffix}")
            if pool:
                snapshot = self._longitudinal_snapshot(suffix)
                apply = self._apply_longitudinal_design_bot if suffix == "b" else self._apply_longitudinal_design_top
                for option, row in pool:
                    if len(kept) >= limit:
                        break
                    apply(row)
                    verdict = self._section_verdict(forces, (face,))
                    if verdict.passes:
                        kept.append(replace(option, section_DCR=verdict.DCR))
                self._restore_longitudinal(snapshot)
            setattr(self, f"_flexure_options_{suffix}", tuple(kept))
        self._infeasible_faces = infeasible

    def _section_verdict(self, forces: list[Forces], faces: Tuple[str, ...] = ("bot", "top")) -> _Verdict:
        """The section as it stands, under ``forces``: flexure and shear.

        The worst of shear and flexure, both faces, over every combination;
        it passes when that ratio is at most 1, the shear check leaves no
        warning and the flexure passes :meth:`_flexure_verdict` with the bars
        of ``faces`` -- both by default, since a stirrup changes the width
        left to the bars as much as their depth. The shear warnings read the
        compression steel of this section, not of the last reporting check:
        a layout tried here can make the section rely on its compression bars,
        or stop relying on them, and the stirrups owe them lateral support
        (ACI 318-19 / CIRSOC 201-25 §9.7.6.4) only in the first case.
        Values-only checks, so nothing is written to the section and the
        results of the last reporting check stay what they were -- which is
        what lets a design try a layout on the section and take it off again.
        """
        flexure = self._flexure_verdict(forces, faces)
        worst, clean = flexure.DCR, flexure.clean
        braced = self._compression_faces
        self._compression_faces = set(flexure.compression_faces)
        try:
            for force in forces:
                shear_state = self._run_shear_check(force, report=False)
                worst = max(worst, capture_shear_check(self, force.label, shear_state).DCR)
                clean = clean and not shear_warnings(self, force.label, shear_state)
        finally:
            self._compression_faces = braced
        return _Verdict(worst, clean, flexure.compression_faces, flexure.fits, flexure.admissible)

    def _record_transverse_options(self, table: DataFrame, forces: list[Forces]) -> None:
        """Keep the stirrup layouts the search found, the applied one first.

        The applied layout is the first row of the ranked table. The
        alternatives are the other rows -- one per bar diameter the code
        offers, lighter and heavier alike -- in order of diameter, and each is
        built on the finished section and checked there before it is kept:
        shear and flexure, under every combination of the design. A stirrup
        is not only shear. A heavier one sits the longitudinal bars deeper,
        which raises the ``A_v`` the section needs, lowers its shear limit
        (ACI 318-19 / CIRSOC 201-25 §22.5.1.2, EN 1992-1-1 V_Rd,max) and
        lowers its moment capacity, so a row sized for the shear alone could
        be offered and fail when built: 1eØ16/11 on a 25x50 whose Ø10 cage
        passes, past the section limit by 0.7 %. The rows the section does
        not pass with are dropped; the applied one is kept whatever its
        verdict, with its ``section_DCR`` saying so.
        """
        rows = [row for _, row in table.iterrows()]
        if not rows:
            self._shear_options = ()
            return
        applied, alternatives = rows[0], rows[1:]
        alternatives.sort(key=lambda row: row["d_b"].to("mm").magnitude)
        layout = self.reinforcement.transverse.layout

        def option(row: Any, DCR: float) -> StirrupOption:
            return StirrupOption(
                n_stirrups=int(row["n_stir"]),
                d_b=row["d_b"],
                s_l=row["s_l"],
                s_w=row["s_w"],
                A_v=row["A_v"],
                functional=float(row["functional"]),
                layout=layout,
                section_DCR=DCR,
                # The limits the search held this row to, at the depth its own
                # stirrup gives the section: §9.7.6.4.3 folded into s_max_l.
                s_max_l=_positive_or_none(row["s_max_l"]),
                s_max_w=_positive_or_none(row["s_max_w"]),
            )

        options = []
        for row in [applied] + alternatives:
            self._apply_transverse_design(row)
            verdict = self._section_verdict(forces)
            if row is applied or verdict.passes:
                options.append(option(row, verdict.DCR))
        # Back to the layout the design applied, whatever was tried last.
        self._apply_transverse_design(applied)
        self._shear_options = tuple(options[: int(self.settings.design_options)])

    def _design_start_stirrup(self) -> Quantity:
        """The stirrup diameter a design starts from, whatever ran before it.

        A beam assumes the one its settings name until the shear design picks
        one, but never less than the smallest the shear design can pick: the
        flexure is sized at the depth of this stirrup, and a starter the
        catalogue does not offer is one the shear design always replaces,
        after which :meth:`_settle_design` redoes the flexure at the new
        depth. ACI 318-19 in metric starts its catalogue at Ø10 against the
        Ø8 of the settings, which made that second round the rule there. A
        slab starts with none.
        """
        catalogue = design_code(self.concrete).transverse_rebar(Rebar(self), 0 * kN, self._alpha)[0]
        return max(self.settings.stirrup_diameter_ini, min(catalogue))

    def _reset_for_design(self) -> None:
        """Return the reinforcement to where a first design starts.

        A design reads the section it runs on -- the stirrup diameter sets the
        effective depth, the bars left on a face stay there when the search
        cannot fit one -- so without this a second ``design()`` started from the
        first one's answer and could land somewhere else: 1eØ10/28 and then
        1eØ10/27 on the same beam. Starting every design from the same state is
        what makes it a function of its inputs.
        """
        self._stirrup_n = 0
        self._stirrup_d_b = self._design_start_stirrup()
        self._stirrup_s_l = 0 * cm
        self._A_v = 0 * cm**2 / m
        self._shear_options = ()
        self._reset_longitudinal_for_design()

    def _reset_longitudinal_for_design(self) -> None:
        """Return the bars and what a flexure design left about them to where one starts.

        The stirrups are kept: this is what a design that has to redo its
        flexure at the depth of the stirrup it settled on starts from (see
        :meth:`_settle_design`), and what :meth:`_reset_for_design` does once
        it has put the starter stirrup back.
        """
        self._doubly_reinforced = False
        self._compression_faces = set()
        self._flexure_options_b = ()
        self._flexure_options_t = ()
        self._flexure_option_pool_b = ()
        self._flexure_option_pool_t = ()
        self._infeasible_faces = set()
        self._short_faces = {}
        self._initialize_longitudinal_rebar_attributes()

    def _clear_top_longitudinal(self) -> None:
        """Reset the top reinforcement to the default placeholder bars."""
        if self.concrete.unit_system == "metric":
            self.set_longitudinal_rebar_top(0, 0 * mm)
        else:
            self.set_longitudinal_rebar_top(0, 0 * inch)

    ##########################################################
    # SET LONGITUDINAL AND TRANSVERSE REBAR AND UPDATE ATTRIBUTES
    ##########################################################

    @contextmanager
    def _design_in_progress(self) -> Iterator[None]:
        """Mark a design running, so the bars it places do not drop its results."""
        self._designing = getattr(self, "_designing", 0) + 1
        try:
            yield
        finally:
            self._designing -= 1

    def _drop_results(self) -> None:
        """Forget the results of the reinforcement the section carried before.

        Called by the public setters: bars or stirrups changed by hand are a
        different section, and the flexure and shear results of the last check
        or design -- ``flexure_design``, ``shear_design``, the per-combination
        checks, the warnings they raised and the notebook views -- described
        the old one. Both go, whichever setter was called: the stirrup sets
        the effective depth the flexure is computed at, and the bars set the
        depth and the ratio the shear is. They come back with the next check
        or design. A design's own placements keep them, since the design is
        what produces them. So do the design's own verdicts, the faces it
        could not bring up to their moment (``As_below_required``) or fit
        (``bars_do_not_fit``). What reads the section as it is now -- the
        reinforcement, the bar spacing -- is not a result and stays.
        """
        # SLS results are external to the design operation. Even a design's
        # own bar placements invalidate the section they were assessed on.
        self._skin_service_cases = ()
        self._skin_service_reference = None
        if getattr(self, "_designing", 0):
            return
        self._flexure_checked = False
        self._compression_faces = set()
        self._shear_checked = False
        self._flexure_checks = []
        self._flexure_warnings = []
        self._shear_checks = []
        self._shear_warnings = []
        # What the last design could not reach is a result of that design too.
        self._short_faces = {}
        self._infeasible_faces = set()

    def set_transverse_rebar(
        self,
        n_stirrups: Optional[int] = None,
        d_b: Quantity = 0 * mm,
        s_l: Quantity = 0 * cm,
        *,
        n_legs: Optional[int] = None,
        legs: Optional[int] = None,
    ) -> None:
        """Set transverse reinforcement or clear it with an all-zero input.

        Prefer ``legs``; ``n_legs`` is a compatible alias. The current model
        supports integer counts >= 2, with one perimeter closed stirrup,
        compression-support crossties with modelled hooks and remaining open legs.
        Contradictory counts are rejected.

        Use keyword-only ``legs`` for the number of shear legs. Legacy
        ``n_stirrups`` (including positional calls) still accepts integer
        two-leg equivalents, not a guaranteed number of closed pieces. If both are supplied they must
        agree. Zero with zero diameter and spacing clears the reinforcement.

        Drops the flexure and shear results of the last check or design (see
        :meth:`_drop_results`).
        """

        n_legs = resolve_legs(legs, n_legs)
        equivalent_count = _transverse_stirrup_count(n_stirrups, n_legs)

        # Diameter and spacing must be physical lengths.
        if not isinstance(d_b, Quantity) or not d_b.check("[length]"):
            raise TypeError("d_b must be a length Quantity.")
        if not isinstance(s_l, Quantity) or not s_l.check("[length]"):
            raise TypeError("s_l must be a length Quantity.")

        diameter_mm = d_b.to("mm").magnitude
        spacing_mm = s_l.to("mm").magnitude
        if not math.isfinite(diameter_mm):
            raise ValueError("d_b must be finite.")
        if not math.isfinite(spacing_mm):
            raise ValueError("s_l must be finite.")

        # An all-zero input explicitly removes the transverse reinforcement.
        if equivalent_count == 0 and diameter_mm == 0 and spacing_mm == 0:
            self._stirrup_n = 0
            self._stirrup_d_b = d_b
            self._stirrup_s_l = s_l
            self._A_v = 0 * cm**2 / m
            self._update_stirrup_dependents()
            self._drop_results()
            return

        # Every non-empty reinforcement configuration must be strictly positive.
        if equivalent_count <= 0:
            name = "n_legs" if n_legs is not None else "n_stirrups"
            raise ValueError(f"{name} must be greater than zero.")
        if diameter_mm <= 0:
            raise ValueError("d_b must be greater than zero.")
        if spacing_mm <= 0:
            raise ValueError("s_l must be greater than zero.")

        # Store the inputs only after all validations pass.
        self._stirrup_n = equivalent_count
        self._stirrup_d_b = d_b
        self._stirrup_s_l = s_l

        # A closed stirrup contributes two vertical legs.
        n_legs = int(equivalent_count * 2)
        A_db = d_b**2 * math.pi / 4
        A_vs = n_legs * A_db

        # Calculate the transverse reinforcement area per unit length.
        self._A_v = A_vs / s_l

        self._update_stirrup_dependents()
        self._drop_results()

    def _update_stirrup_dependents(self) -> None:
        """Recompute what the stirrup diameter enters into.

        The legs sit between the cover and the longitudinal bars, so a
        thicker stirrup narrows the clear space those bars have across the
        width as well as lowering the effective depths. The clear space used
        to be recomputed only when the bars were set, so stirrups set after
        them -- or changed later -- left ``clear_spacing_below_min`` reading a
        stale value until a reporting check happened to refresh it, and the
        answer depended on the order of the calls. Everything that follows
        from the stirrup goes through here.
        """
        self._calculate_min_clear_spacing()
        self._update_effective_heights()

    def _leg_spacing_across_width(self) -> Quantity:
        """Distance between adjacent stirrup legs, measured across the section.

        A beam's legs are the sides of its stirrup cage, so their spacing is not
        detailed directly: it falls out of how many legs are spread between the
        centres of the outermost pair. A slab's is a detailing decision of its
        own, which is why the two sections answer this differently and the shear
        checks ask the section instead of assuming the cage.

        Zero when the section carries no stirrups, so that a section without
        shear reinforcement reports no spacing rather than a negative one.
        """
        n_legs = self._stirrup_n * 2
        if n_legs < 2:
            return 0 * self._len_unit()
        return max(
            (self.width - 2 * self.c_c - self._stirrup_d_b) / (n_legs - 1),
            0 * self._len_unit(),
        )

    def _apply_transverse_design(self, design: Any) -> None:
        """Store the row the transverse rebar search chose.

        A hook rather than a call inlined in :meth:`design_shear`, because a
        section is detailed the way it is reinforced: a beam by a stirrup count
        and a spacing, a slab by a spacing in each direction. Only the section
        knows which of the two the row means.
        """
        self.set_transverse_rebar(design["n_stir"], design["d_b"], design["s_l"])

    def _len_unit(self) -> Quantity:
        # Base length unit for this section
        return 1 * mm if getattr(self.concrete, "unit_system", "metric") == "metric" else 1 * inch

    def _area_unit(self) -> Quantity:
        L = self._len_unit()
        return L**2

    def set_longitudinal_rebar_bot(
        self,
        n1: int,
        d_b1: Quantity | None,
        n2: int = 0,
        d_b2: Quantity | None = None,
        n3: int = 0,
        d_b3: Quantity | None = None,
        n4: int = 0,
        d_b4: Quantity | None = None,
    ) -> None:
        L = self._len_unit()
        self._n1_b = n1
        self._d_b1_b = d_b1 if d_b1 is not None else 0 * L
        self._n2_b = n2
        self._d_b2_b = d_b2 if d_b2 is not None else 0 * L
        self._n3_b = n3
        self._d_b3_b = d_b3 if d_b3 is not None else 0 * L
        self._n4_b = n4
        self._d_b4_b = d_b4 if d_b4 is not None else 0 * L
        self._face_set_by_hand("bot")
        self._update_longitudinal_rebar_attributes()
        self._drop_results()

    def set_longitudinal_rebar_top(
        self,
        n1: int,
        d_b1: Quantity | None,
        n2: int = 0,
        d_b2: Quantity | None = None,
        n3: int = 0,
        d_b3: Quantity | None = None,
        n4: int = 0,
        d_b4: Quantity | None = None,
    ) -> None:
        L = self._len_unit()
        self._n1_t = n1
        self._d_b1_t = d_b1 if d_b1 is not None else 0 * L
        self._n2_t = n2
        self._d_b2_t = d_b2 if d_b2 is not None else 0 * L
        self._n3_t = n3
        self._d_b3_t = d_b3 if d_b3 is not None else 0 * L
        self._n4_t = n4
        self._d_b4_t = d_b4 if d_b4 is not None else 0 * L
        self._face_set_by_hand("top")
        self._update_longitudinal_rebar_attributes()
        self._drop_results()

    def _face_set_by_hand(self, face: str) -> None:
        """A face given bars is no longer the face the search gave up on.

        ``bars_do_not_fit`` records, per face, that the last design found no
        layout that fits the width. That is the search's verdict on the
        width, not a property of whatever bars the face carries: bars set by
        hand afterwards are a different section, which the spacing check
        judges on its own. The design itself sets the flag after it has
        applied its layout -- through these same setters -- so it survives
        the design and goes with the first hand-set bars. ``face`` is
        ``"bot"`` or ``"top"``.
        """
        self._infeasible_faces.discard(face)

    def _calculate_longitudinal_rebar_area(self) -> None:
        """Calculate total rebar area (robust to None or zero diameters)."""
        A0 = 0 * self._area_unit()

        def area(n: int, d: Quantity | None) -> Quantity:
            # Treat None or zero diameter as zero area; works with pint
            if d is None:
                return A0
            mag = getattr(d, "magnitude", None)
            if mag is not None and mag == 0:
                return A0
            return n * (d**2) * np.pi / 4

        # Bottom
        self._A_s_bot = (
            area(self._n1_b, self._d_b1_b)
            + area(self._n2_b, self._d_b2_b)
            + area(self._n3_b, self._d_b3_b)
            + area(self._n4_b, self._d_b4_b)
        )

        # Top
        self._A_s_top = (
            area(self._n1_t, self._d_b1_t)
            + area(self._n2_t, self._d_b2_t)
            + area(self._n3_t, self._d_b3_t)
            + area(self._n4_t, self._d_b4_t)
        )

    def _layer_clear_spacing(self, n_a: int, d_a: Quantity, n_b: int, d_b: Quantity) -> Quantity:
        """The clear distance between the bars of one layer, spread evenly between the stirrup legs.

        Parameters:
            n_a (int): Number of bars in the first group of the layer.
            d_a (Quantity): Diameter of bars in the first group of the layer.
            n_b (int): Number of bars in the second group of the layer.
            d_b (Quantity): Diameter of bars in the second group of the layer.

        Returns:
            Quantity: Clear spacing for the given layer -- for a layer of one
            bar, the room left beside it.
        """
        effective_width = self.width - 2 * (self.c_c + self._stirrup_d_b)
        total_bars = n_a + n_b
        if total_bars <= 1:
            return effective_width - max(d_a, d_b)  # Clear space for one bar
        total_bar_width = n_a * d_a + n_b * d_b
        return (effective_width - total_bar_width) / (total_bars - 1)

    def _tension_bar_spacing(self, face: str) -> Optional[Tuple[Quantity, Quantity]]:
        """The centre-to-centre spacing of the bars nearest ``face``, and the most the code allows it.

        ACI 318-19 §9.7.2.2 / CIRSOC 201-25 art. 9.7.2.2 send the bars closest to
        the tension face of a beam to Table 24.3.2, a crack-control cap on their
        spacing, which the code supplies through ``max_bar_spacing_tension``. A
        slab carries the same cap inside its own spacing row (§7.7.2.2, folded
        into ``OneWaySlab._max_bar_spacing``), and a code without the hook --
        EN 1992-1-1 controls cracking through §7.3.3 instead -- has nothing of
        this kind to report, so both answer ``None``; so does a face with no bars.

        A beam is detailed by a bar count, so the spacing is read off the layer
        nearest the face the way the section spreads it: the bars evenly spaced
        between the stirrup legs (:meth:`_layer_clear_spacing`), which puts
        adjacent centres one clear distance and two half-diameters apart -- the
        larger bar of the layer, on the safe side where it mixes two. With a
        single bar nearest the face there is no pair to measure, and §24.3.3
        compares the width of the face against the same limit instead. The
        report's §24.3.2 rows and ``bar_spacing_exceeds_max`` both read this.
        ``face`` is ``"b"`` or ``"t"``.
        """
        if getattr(self, f"_s_b1_{face}", None) is not None:
            return None
        limit_of = design_code(self.concrete).max_bar_spacing_tension
        if limit_of is None:
            return None
        # The two groups of the layer nearest the face; one with no bars, or
        # bars of no size, counts for nothing.
        nearest = []
        for group in (1, 2):
            n, d_b = getattr(self, f"_n{group}_{face}"), getattr(self, f"_d_b{group}_{face}")
            nearest.append((n, d_b) if n > 0 and d_b is not None and d_b.magnitude > 0 else (0, 0 * self.width))
        (n_a, d_a), (n_b, d_b) = nearest
        if n_a + n_b == 0:
            return None
        limit: Quantity = limit_of(self)
        if n_a + n_b == 1:
            return self.width, limit
        return self._layer_clear_spacing(n_a, d_a, n_b, d_b) + max(d_a, d_b), limit

    def _calculate_min_clear_spacing(self) -> None:
        """
        Calculates the maximum clear spacing between bars for the bottom rebar layers.

        Returns:
            Quantity: The maximum clear spacing between bars in either the first or second layer.
        """
        layer_clear_spacing = self._layer_clear_spacing

        # AVAIABLE CLEAR SPACING FOR BOTTOM BARS
        # Calculate clear spacing for each layer
        spacing_layer1_b = layer_clear_spacing(self._n1_b, self._d_b1_b, self._n2_b, self._d_b2_b)
        spacing_layer2_b = layer_clear_spacing(self._n3_b, self._d_b3_b, self._n4_b, self._d_b4_b)

        # Return the maximum clear spacing between the two layers
        self._available_s_bot = min(spacing_layer1_b, spacing_layer2_b)

        # AVAIABLE CLEAR SPACING FOR TOP BARS
        # Calculate clear spacing for each layer
        spacing_layer1_t = layer_clear_spacing(self._n1_t, self._d_b1_t, self._n2_t, self._d_b2_t)
        spacing_layer2_t = layer_clear_spacing(self._n3_t, self._d_b3_t, self._n4_t, self._d_b4_t)

        # Return the maximum clear spacing between the two layers
        self._available_s_top = min(spacing_layer1_t, spacing_layer2_t)

    def _calculate_long_rebar_centroid(self) -> None:
        """
        Calculates the centroid (baricenter) of a group of rebars based on their diameters, quantities,
        and layer spacing.

        Returns:
            float: The calculated centroid height of the rebar group.
        """
        # BOTTOM BARS CENTROID
        # Calculate the vertical positions of the bar layers
        y1_b = self._d_b1_b / 2
        y2_b = self._d_b2_b / 2
        y3_b = max(self._d_b1_b, self._d_b2_b) + self.settings.layers_spacing + self._d_b3_b / 2
        y4_b = max(self._d_b1_b, self._d_b2_b) + self.settings.layers_spacing + self._d_b4_b / 2
        # Calculate the total area of each layer
        area_1_b = self._n1_b * self._d_b1_b**2 * np.pi / 4.0
        area_2_b = self._n2_b * self._d_b2_b**2 * np.pi / 4.0
        area_3_b = self._n3_b * self._d_b3_b**2 * np.pi / 4.0
        area_4_b = self._n4_b * self._d_b4_b**2 * np.pi / 4.0

        # Calculate the centroid as a weighted average
        total_area_b = area_1_b + area_2_b + area_3_b + area_4_b
        if total_area_b == 0:
            self._bot_rebar_centroid = 0 * mm
        else:
            self._bot_rebar_centroid = (
                area_1_b * y1_b + area_2_b * y2_b + area_3_b * y3_b + area_4_b * y4_b
            ) / total_area_b
        # TOP BARS CENTROID
        # Calculate the vertical positions of the bar layers
        y1_t = self._d_b1_t / 2
        y2_t = self._d_b2_t / 2
        y3_t = max(self._d_b1_t, self._d_b2_t) + self.settings.layers_spacing + self._d_b3_t / 2
        y4_t = max(self._d_b1_t, self._d_b2_t) + self.settings.layers_spacing + self._d_b4_t / 2

        # Calculate the total area of each layer
        area_1_t = self._n1_t * self._d_b1_t**2 * np.pi / 4  # Area proportional to number of bars and their diameter
        area_2_t = self._n2_t * self._d_b2_t**2 * np.pi / 4
        area_3_t = self._n3_t * self._d_b3_t**2 * np.pi / 4
        area_4_t = self._n4_t * self._d_b4_t**2 * np.pi / 4

        # Calculate the centroid as a weighted average
        total_area_t = area_1_t + area_2_t + area_3_t + area_4_t
        if total_area_t == 0:
            self._top_rebar_centroid = 0 * mm
        else:
            self._top_rebar_centroid = (
                area_1_t * y1_t + area_2_t * y2_t + area_3_t * y3_t + area_4_t * y4_t
            ) / total_area_t

    def _update_longitudinal_rebar_attributes(self) -> None:
        """Recalculate attributes dependent on rebar configuration for both top and bottom reinforcing."""
        self._calculate_longitudinal_rebar_area()
        self._calculate_long_rebar_centroid()
        self._calculate_min_clear_spacing()
        self._update_effective_heights()

    def _update_effective_heights(self) -> None:
        """Update effective heights and depths for moment and shear calculations."""
        self._c_mec_bot = self.c_c + self._stirrup_d_b + self._bot_rebar_centroid
        self._c_mec_top = self.c_c + self._stirrup_d_b + self._top_rebar_centroid
        self._d_bot = self.height - self._c_mec_bot
        self._d_top = self.height - self._c_mec_top
        # Use bottom or top effective height
        self._d_shear = min(self._d_bot, self._d_top)
        # Every geometry and reinforcement change funnels through here, so this
        # is the one place the float view can go stale. Rebuilt eagerly so that
        # no check ever has to create it -- see mento.precompute.
        refresh_section_floats(self)

    ##########################################################
    # CHECK & DESIGN FLEXURE
    ##########################################################

    def design_flexure(self, forces: list[Forces]) -> DataFrame:
        """
        Designs flexural reinforcement for the beam using the provided forces and design code.
        Identifies the limiting cases for top and bottom reinforcement, designs for those cases,
        and then checks flexural capacity for all forces.

        Returns
        -------
        DataFrame
            A DataFrame summarizing the flexural design results for all forces.

        The alternatives kept for each face are verified on the section it
        leaves (see :meth:`_verify_longitudinal_options`).
        """
        validate_supported_forces(self, forces)
        with self._design_in_progress():
            all_results = self._design_flexure(forces)
            self._verify_longitudinal_options(forces)
        return all_results

    def _design_flexure(self, forces: list[Forces]) -> DataFrame:
        """:meth:`design_flexure` without verifying the alternatives.

        What :meth:`design` runs: its alternatives are judged once, on the
        finished section, and a verification on the section a flexure pass
        leaves -- with the starter stirrup, or one a later round replaces --
        would be work thrown away.
        """
        # Initialize limiting cases
        validate_supported_forces(self, forces)
        max_M_y_top = 0 * kN * m  # For negative M_y (top reinforcement design)
        max_M_y_bot = 0 * kN * m  # For positive M_y (bottom reinforcement design)
        # Identify the limiting cases
        for force in forces:
            # For top reinforcement, consider the minimum (most negative) moment
            if force._M_y <= max_M_y_top:
                max_M_y_top = force._M_y
                self._limiting_case_bot = force
            # For bottom reinforcement, consider the maximum positive moment
            if force._M_y > max_M_y_bot:
                max_M_y_bot = force._M_y
                self._limiting_case_top = force
        # Design flexural reinforcement for the limiting cases
        design_code(self.concrete).design_flexure(self, max_M_y_bot, max_M_y_top)

        # Check flexural capacity for all forces with the assigned reinforcement
        return self.check_flexure(forces)

    @property
    def flexure_checks(self) -> Tuple[FlexureCheck, ...]:
        """One immutable flexure result per combination of the last check.

        The beam's own attributes describe whichever combination ran last;
        these describe all of them, so enveloping is a plain ``max`` over the
        tuple rather than something the check has to accumulate as it goes.
        """
        return tuple(self._flexure_checks)

    @property
    def shear_checks(self) -> Tuple[ShearCheck, ...]:
        """One immutable shear result per combination of the last check."""
        return tuple(self._shear_checks)

    def flexure_check_results(self, forces: list[Forces]) -> Tuple[FlexureCheck, ...]:
        """Check flexure and return one result per combination, building no report.

        The same numbers as :meth:`check_flexure`, without the report tables or
        the result DataFrame — which is most of what a check costs. This is the
        entry point for looping over many sections::

            worst = max(r.bottom.DCR for r in beam.flexure_check_results(combos))

        Nothing is written to the section on the ACI and CIRSOC path: the check
        returns its result and only the reporting path copies it back.
        """
        validate_supported_forces(self, forces)
        self._flexure_checks = []
        self._flexure_warnings = []
        self._compression_faces = set()
        for position, force in enumerate(forces, 1):
            state = self._run_flexure_check(force, report=False)
            self._flexure_checks.append(
                capture_flexure_check(self, force.label, state, has_axial_force=force.N_x.magnitude != 0)
            )
            self._flexure_warnings.extend(flexure_warnings(self, combination_label(force.label, position), state))
            self._flexure_warnings.extend(unread_force_warnings(force, combination_label(force.label, position)))
            self._note_compression_face(force, state)
        self._flexure_checked = True
        return tuple(self._flexure_checks)

    def _note_compression_face(self, force: Forces, state: Any) -> None:
        """Record the face ``force`` relies on as compression steel, for the stirrups' sake.

        ACI 318-19 / CIRSOC 201-25 §9.7.6.4.1 ask for lateral support of the
        compression reinforcement wherever it is required. The flexure check
        knows when: a combination whose moment needs compression steel
        (``doubly_reinforced`` on its state), or whose tension steel is
        admissible only through it (past A_s,max, within A_s,max,eff), relies
        on the face opposite the one it puts in tension (see
        :meth:`_compression_face_of`). The shear design and the shear warnings read
        the faces so recorded through the code's ``stirrup_compression_support``.
        EN records the face whose compression steel its resistance credits.
        """
        face = self._compression_face_of(force, state)
        if face is not None:
            self._compression_faces.add(face)

    @staticmethod
    def _compression_face_of(force: Forces, state: Any) -> Optional[str]:
        """The face ``force`` relies on as compression steel, per its flexure ``state``, if any.

        The face opposite the one the moment puts in tension, when the
        combination relies on compression steel: its moment needs it to be
        carried (``doubly_reinforced``), or the tension steel placed is past
        A_s,max of the singly reinforced section and complies with ACI 318-19
        / CIRSOC 201-25 §9.3.3.1 only through the compression steel opposite
        it, which lifts the limit to A_s,max,eff -- the face the report marks
        "D.R.". The design reaches the second on purpose, where the catalogue
        has nothing between the area asked for and A_s,max (see
        ``_design_tension_face``): a CIRSOC 40x80 H30 under 1196.5 kN·m takes
        11Ø25 = 54.00 cm² against A_s,max = 53.88 cm², and its two Ø10 on top
        are what make that admissible. ``None`` otherwise, and for a code
        whose state does not say.
        """
        if hasattr(state, "compression_face"):
            return state.compression_face
        if not hasattr(state, "doubly_reinforced") or force._M_y == 0 * kN * m:
            return None
        tension = "bot" if force._M_y > 0 * kN * m else "top"
        relies = bool(state.doubly_reinforced)
        if not relies:
            # Past A_s,max and within A_s,max,eff: the face complies through the
            # compression steel. Past A_s,max,eff it does not comply at all, and
            # ``As_above_max`` says so.
            A_s = state.A_s_tension
            A_s_max, A_s_max_eff = getattr(state, f"A_s_max_{tension}"), getattr(state, f"A_s_max_eff_{tension}")
            relies = (
                A_s_max > 0
                and A_s > A_s_max
                and not math.isclose(A_s, A_s_max)
                and (A_s <= A_s_max_eff or math.isclose(A_s, A_s_max_eff))
            )
        if not relies:
            return None
        return "top" if tension == "bot" else "bot"

    def shear_check_results(self, forces: list[Forces]) -> Tuple[ShearCheck, ...]:
        """Check shear and return one result per combination, building no report.

        Nothing is written to the section: the ACI check returns its result as a
        value and only the reporting path copies it back. That is what makes a
        loop over many stations safe — see :meth:`flexure_check_results` for the
        flexure counterpart, which still writes.
        """
        validate_supported_forces(self, forces)
        self._shear_checks = []
        self._shear_warnings = []
        for position, force in enumerate(forces, 1):
            state = self._run_shear_check(force, report=False)
            self._shear_checks.append(capture_shear_check(self, force.label, state))
            self._shear_warnings.extend(shear_warnings(self, combination_label(force.label, position), state))
            self._shear_warnings.extend(unread_force_warnings(force, combination_label(force.label, position)))
        self._shear_checked = True
        return tuple(self._shear_checks)

    def _run_flexure_check(self, force: Forces, *, report: bool) -> Optional[Any]:
        """Compute one flexure combination, and build its report only if asked.

        The design code does the calculation and returns it; assembling the row
        and the detail tables is presentation and lives in
        :mod:`mento.reports.tables`, which still reads the element — so the
        state is copied back only when a report is wanted.
        """
        validate_supported_forces(self, [force])
        code = design_code(self.concrete)
        state: Any = code.check_flexure(self, force)
        if report:
            code.apply_flexure_state(self, state)
        if report:
            self._flexure_report_row = build_flexure_report(self, force)
        return state

    def _run_shear_check(self, force: Forces, *, report: bool) -> Optional[Any]:
        """Compute one shear combination, and build its report only if asked.

        Returns the ACI state so a values-only caller never needs the section to
        have been written to. Building a report does need that, because the
        tables still read the element — the compatibility layer of ADR-0001.
        """
        validate_supported_forces(self, [force])
        code = design_code(self.concrete)
        state = code.check_shear(self, force)
        if report:
            code.apply_shear_state(self, state)
        if report:
            self._shear_report_row = build_shear_report(self, force, state)
        return state

    def check_flexure(self, forces: list[Forces]) -> DataFrame:
        # Initialize variables to track limiting cases
        validate_supported_forces(self, forces)
        max_dcr_top: float = 0
        max_dcr_bot: float = 0
        limiting_case_top = None
        limiting_case_bot = None
        limiting_case_top_details = None
        limiting_case_bot_details = None

        # To compile results for all forces
        self._flexure_results_list = []  # Store individual results for each force
        self._flexure_results_detailed_list: Dict[Any, Dict[str, Any]] = {}  # Store detailed results by force ID
        self._flexure_checks = []
        self._flexure_warnings = []
        self._compression_faces = set()

        for position, force in enumerate(forces, 1):
            state = self._run_flexure_check(force, report=True)
            self._note_compression_face(force, state)
            result = self._flexure_report_row
            self._flexure_results_list.append(result)

            # Store detailed results for this force
            self._flexure_results_detailed_list[force.id] = {
                "forces": self._forces_flexure.copy(),
                "min_max": self._data_min_max_flexure.copy(),
                "flexure_capacity_top": self._flexure_capacity_top.copy(),
                "flexure_capacity_bot": self._flexure_capacity_bot.copy(),
                "checks_pass": self._all_flexure_checks_passed,
            }

            # The result is a value of the check itself, not a reading of the
            # attributes it left on the beam -- those describe the last
            # combination only, and are on their way out with them.
            self._flexure_checks.append(
                capture_flexure_check(self, force.label, state, has_axial_force=force.N_x.magnitude != 0)
            )
            self._flexure_warnings.extend(flexure_warnings(self, combination_label(force.label, position), state))
            self._flexure_warnings.extend(unread_force_warnings(force, combination_label(force.label, position)))

            # Extract the DCR values for top and bottom from the results
            current_dcr_top = self._DCRb_top
            current_dcr_bot = self._DCRb_bot

            # Update top limiting case
            if current_dcr_top >= max_dcr_top:
                max_dcr_top = current_dcr_top
                limiting_case_top = result
                limiting_case_top_details = self._flexure_results_detailed_list[force.id]

            # Update bottom limiting case
            if current_dcr_bot >= max_dcr_bot:
                max_dcr_bot = current_dcr_bot
                limiting_case_bot = result
                limiting_case_bot_details = self._flexure_results_detailed_list[force.id]

        # Compile all results into a single DataFrame
        all_data = pd.concat(self._flexure_results_list, ignore_index=True)
        units_row = self._get_units_row_flexure()
        all_results = pd.concat([units_row, all_data], ignore_index=True)

        # Store limiting cases
        self._limiting_case_flexure_top = limiting_case_top
        self._limiting_case_flexure_bot = limiting_case_bot
        self._limiting_case_flexure_top_details = limiting_case_top_details
        self._limiting_case_flexure_bot_details = limiting_case_bot_details

        # Store maximum DCRs for easy access
        self._max_dcr_top = max_dcr_top
        self._max_dcr_bot = max_dcr_bot
        # Mantener también los atributos históricos en la envolvente.
        self._DCRb_top = max_dcr_top
        self._DCRb_bot = max_dcr_bot

        # Mark shear as checked
        self._flexure_checked = True

        return all_results

    ##########################################################
    # CHECK & DESIGN SHEAR
    ##########################################################

    def _clear_transverse_rebar_design(self) -> None:
        """Record a shear design that places no stirrups.

        Mirrors what the stirrup designer leaves behind for a real cage, so the
        report tables and ``BeamSummary`` read the same keys either way -- they
        just read zeros.
        """
        length_unit = "cm" if self.concrete.unit_system == "metric" else "inch"
        area_unit = "cm**2/m" if self.concrete.unit_system == "metric" else "inch**2/ft"
        empty = {
            "n_stir": 0,
            "d_b": (0 * mm).to(length_unit),
            "s_l": (0 * mm).to(length_unit),
            "s_w": (0 * mm).to(length_unit),
            "A_v": (0 * cm**2 / m).to(area_unit),
            "s_max_l": (0 * mm).to(length_unit),
            "s_max_w": (0 * mm).to(length_unit),
        }
        self.shear_design_results = pd.DataFrame([empty])
        self._best_rebar_design = self.shear_design_results.iloc[0]
        self._stirrup_s_w = empty["s_w"]
        self._stirrup_s_max_l = empty["s_max_l"]
        self._stirrup_s_max_w = empty["s_max_w"]
        self.set_transverse_rebar(0, 0 * mm, 0 * cm)

    @property
    def _stirrups_optional(self) -> bool:
        """Whether this element may be built with no transverse reinforcement at all.

        A beam never may. Stirrups run the whole length of a beam whatever the
        shear diagram says, so designing one always places at least the minimum
        area -- ACI 318-19 Table 9.6.3.4, EN 1992-1-1 Eq. (9.5N) -- even where
        the concrete alone would carry Vu. ACI 9.6.3.1 waives that minimum below
        a threshold and the check reports the waiver, but the design does not
        follow it down.

        A one-way slab is the exception both codes name: ACI 318-19 7.6.3.1 only
        calls for shear reinforcement where Vu exceeds phi*Vc, and EN 1992-1-1
        6.2.1(4) drops the minimum in members where the load can redistribute
        transversally. So a slab the concrete alone carries is designed with no
        stirrups at all, rather than given a cage it does not need.
        """
        return self.mode == "slab"

    def _shear_demand(self, forces: list[Forces]) -> Tuple[Quantity, Quantity]:
        """The governing ``(A_v_req, V_s_req)`` over the combinations, at the current depth."""
        max_A_v_req = 0 * cm**2 / m
        max_V_s_req = 0 * kN
        for force in forces:
            design_code(self.concrete).design_shear(self, force)
            # Check if this result is the limiting case
            current_A_v_req = self._A_v_req
            if current_A_v_req >= max_A_v_req:
                max_A_v_req = current_A_v_req
                max_V_s_req = self._V_s_req
        return max_A_v_req, max_V_s_req

    def _compression_faces_under(self, forces: list[Forces]) -> set[str]:
        """The faces the section as it stands relies on as compression steel under ``forces``.

        Values-only flexure checks, one per combination (see
        :meth:`_compression_face_of`); nothing is written to the section.
        """
        faces: set[str] = set()
        for force in forces:
            face = self._compression_face_of(force, self._run_flexure_check(force, report=False))
            if face is not None:
                faces.add(face)
        return faces

    def _stirrup_demand(self, forces: list[Forces], braced: set[str]) -> Tuple[Quantity, Quantity]:
        """What the section as it stands asks of its stirrups: read once per diameter the search tries.

        The governing ``(A_v_req, V_s_req)`` of :meth:`_shear_demand`, and the
        compression bars the stirrups have to brace, left in
        ``_compression_faces`` for the code's ``stirrup_compression_support``
        to read -- the diameter floor of ACI 318-19 / CIRSOC 201-25 §9.7.6.4.2
        and the spacing cap of §9.7.6.4.3. Both move with the depth the
        stirrup gives the bars. A section singly reinforced at the depth of
        the starter stirrup can rely on its compression bars at the depth of
        a heavier one: an ACI 15x50 H40 under 211.5 kNm asks 14.94 cm² against
        A_s,max = 14.98 cm² with Ø8, and its 16.10 cm² are past the 14.92 of
        the Ø10 the shear design picks, so the Ø10 has to brace the 2Ø10 on
        top at 150 mm. Read off the last flexure check alone, the stirrups
        were spaced at 210. ``braced`` -- the faces that check found -- stay
        braced whatever the depth, the conservative side.
        """
        self._compression_faces = braced | self._compression_faces_under(forces)
        return self._shear_demand(forces)

    # Factory method to select the shear design method
    def design_shear(self, forces: list[Forces]) -> DataFrame:
        """Design the stirrups for the worst of ``forces``, then check them all.

        The design starts from the stirrup diameter a first design assumes, not
        from the one the section carries, so it gives the same stirrups however
        many times it runs. The effective depth depends on the stirrup, and the
        demand and the spacing limits on the effective depth, so the search
        sizes every bar diameter it offers at the depth that diameter gives
        (:meth:`~mento.rebar.Rebar._transverse_rebar_beam`): what it applies
        was chosen against the section it makes, and passes its own check by
        construction. The design used to be re-run with the diameter it chose
        until the choice held, and a pair of diameters that kept trading places
        -- 8 → 10 → 8 -- left the last one applied against the demand of the
        other.
        """
        validate_supported_forces(self, forces)
        with self._design_in_progress():
            return self._design_shear(forces)

    def _design_shear(self, forces: list[Forces]) -> DataFrame:
        """:meth:`design_shear` without marking a design in progress."""
        validate_supported_forces(self, forces)
        self._shear_options = ()
        self._stirrup_d_b = self._design_start_stirrup()
        self._update_longitudinal_rebar_attributes()
        braced = set(self._compression_faces)

        max_A_v_req, max_V_s_req = self._shear_demand(forces)

        if self._stirrups_optional and max_A_v_req <= 0 * cm**2 / m:
            # No combination asks for shear reinforcement and the code does not
            # impose a minimum here, so the section is built without stirrups.
            self._clear_transverse_rebar_design()
            self._update_longitudinal_rebar_attributes()
            return self.check_shear(forces)

        section_rebar = Rebar(self)
        self.shear_design_results = section_rebar.transverse_rebar(
            max_A_v_req, max_V_s_req, self._alpha, demand=lambda: self._stirrup_demand(forces, braced)
        )
        self._best_rebar_design = section_rebar.transverse_rebar_design

        self._stirrup_s_l = self._best_rebar_design["s_l"]
        self._stirrup_s_w = self._best_rebar_design["s_w"]
        self._stirrup_s_max_l = self._best_rebar_design["s_max_l"]
        self._stirrup_s_max_w = self._best_rebar_design["s_max_w"]
        self._apply_transverse_design(self._best_rebar_design)
        # The search left the faces of the last diameter it tried; the check
        # reads the ones of the stirrup applied.
        self._compression_faces = braced | self._compression_faces_under(forces)
        self._record_transverse_options(self.shear_design_results, forces)

        # Update longitudinal rebar attributes
        self._update_longitudinal_rebar_attributes()

        # Step 3: Check shear adequacy for all forces using the designed rebar
        all_results = self.check_shear(forces)
        return all_results

    # Factory method to select the shear check method
    def check_shear(self, forces: list[Forces]) -> DataFrame:
        validate_supported_forces(self, forces)
        self._shear_results_list = []  # Store individual results for each force
        self._shear_results_detailed_list: Dict[Any, Dict[str, Any]] = {}  # Store detailed results by force ID
        max_dcr = 0  # Track the maximum DCR to identify the limiting case
        self._limiting_case_shear_details = None
        self._shear_checks = []
        self._shear_warnings = []

        for position, force in enumerate(forces, 1):
            state = self._run_shear_check(force, report=True)
            result = self._shear_report_row
            self._shear_results_list.append(result)

            self._shear_results_detailed_list[force.id] = {
                "forces": self._forces_shear.copy(),
                "shear_reinforcement": self._shear_reinforcement.copy(),
                "min_max": self._data_min_max_shear.copy(),
                "checks_pass": self._all_shear_checks_passed,
                "shear_concrete": self._shear_concrete.copy(),
            }

            # As in check_flexure: the value of the check, not the beam's
            # attributes afterwards.
            self._shear_checks.append(capture_shear_check(self, force.label, state))
            self._shear_warnings.extend(shear_warnings(self, combination_label(force.label, position), state))
            self._shear_warnings.extend(unread_force_warnings(force, combination_label(force.label, position)))

            # Check if this result is the limiting case
            current_dcr = result["DCR"][0]
            if current_dcr >= max_dcr:
                max_dcr = current_dcr
                self._limiting_case_shear = result
                self._limiting_case_shear_details = self._shear_results_detailed_list[force.id]

        # Compile all results into a single DataFrame
        all_data = pd.concat(self._shear_results_list, ignore_index=True)
        units_row = self._get_units_row_shear()
        all_results = pd.concat([units_row, all_data], ignore_index=True)

        # Identify the most limiting case by Demand-to-Capacity Ratio (DCR) or other criteria
        self.limiting_case_shear = all_data.loc[all_data["DCR"].idxmax()]  # Select row with highest DCR

        self._shear_checked = True  # Mark shear as checked
        return all_results

    def _get_units_row_shear(self) -> pd.DataFrame:
        """The unit row of the shear summary, in the active code's own names and the section's units."""
        return pd.DataFrame([units_row(design_code(self.concrete).units_row_shear, self.concrete.is_imperial)])

    def _get_units_row_flexure(self) -> pd.DataFrame:
        """The unit row of the flexure summary, in the active code's own names and the section's units."""
        return pd.DataFrame([units_row(design_code(self.concrete).units_row_flexure, self.concrete.is_imperial)])

    ##########################################################
    # CHECK & DESIGN ALL
    ##########################################################

    def design(self, forces: list[Forces]) -> None:
        """
        Complete design: flexure + shear + flexure check.

        Starts from the reinforcement a first design would, whatever the
        section carried before, so the same forces always give the same bars.
        The flexure is designed first, at the depth of the starter stirrup;
        the shear design then chooses the stirrup, and if that moved the bars
        past what they carry the flexure is designed again with it
        (:meth:`_settle_design`). The longitudinal alternatives are verified
        last, on the section the shear design finished: its stirrup sets the
        depth the bars sit at.
        """
        validate_supported_forces(self, forces)
        # What the search for the closest layout of a design that does not
        # close finds, by stirrup, moments and starting pair: the rounds of
        # :meth:`_settle_design` can run it again on the same ones. Only for
        # the length of this design, so a change to the section between two
        # designs is never answered from it.
        self._closest_pair_memo: Dict[tuple, Any] = {}
        try:
            with self._design_in_progress():
                self._reset_for_design()
                self._design_flexure(forces)
                self.design_shear(forces)
                self._settle_design(forces)
                self.check_flexure(forces)
                self._verify_longitudinal_options(forces)
        finally:
            del self._closest_pair_memo

    def _settle_design(self, forces: list[Forces]) -> None:
        """Redo the flexure with the stirrup the shear design chose, until the pair holds.

        The flexure design sizes the bars at the depth of the starter stirrup
        and the shear design then picks one of its own, which moves them. A
        heavier stirrup sinks them: an ACI 318-19 20x50 with f'c = 25 MPa under
        150 kN·m gets 2Ø25 at the Ø8 depth (d = 454.5 mm, φMn = 150.7 kN·m)
        and 1eØ10 for 250 kN, after which d = 452.5 mm and φMn = 149.9 kN·m:
        DCR 1.0005 and nothing to warn about, since the search never saw a
        shortfall. A lighter one lifts them, and under EN 1992-1-1 lifts
        A_s,min with d (§9.2.1.1(1)): a 30x80 under 30 kN·m gets 2Ø12 + 1Ø10 =
        3.047 cm² against 3.045 at the Ø8 depth, then 1eØ6 and 3.054 required,
        so the design warned ``As_below_min`` on its own bars. It also narrows
        or widens what is left between the legs for the bars to fit.

        So when the section as the shear design left it fails
        :meth:`_flexure_verdict`, the flexure is designed again from the
        placeholder bars with that stirrup on the section, and the stirrups
        again for the new bars, until the pair passes or comes back to a
        state already seen -- which means no layout passes at that depth
        either. Bounded by ``_DESIGN_ROUNDS``; a design that passes at once
        does nothing here, and the sequence is a function of the forces, so
        ``design()`` still gives the same bars every time.

        When no round passes, the section ends with the round that came
        closest, not with the last: a later round is designed from a
        different depth and need not be better. Closest is first what the
        design never trades for strength -- bars that fit the width, with the
        vibrator's gap on top, and a tension face within the code's limit
        (tension-controlled under ACI 318-19 / CIRSOC 201-25 §9.3.3.1, the
        4 % of EN 1992-1-1 §9.2.1.1(3)) -- and only then the smallest flexure
        DCR. A stronger layout that breaks one of those is no solution: bars
        the vibrator cannot pass leave the concrete unconsolidated, and a
        beam that is not tension-controlled is one §9.3.3.1 does not allow
        (issue #169). A stirrup that moves the bars can take a round past
        either, which is why both are judged on each round as built. The
        round kept is re-run (its result is a function of the stirrup it
        started from), and :meth:`_record_shortfall` makes sure the face
        that fails says so.
        """
        verdict = self._flexure_verdict(forces, ("bot", "top"))
        if verdict.passes:
            return
        # Each round's verdict, with the stirrup it started from (None: the
        # starter stirrup of the first).
        rounds: list[Tuple[_Verdict, Optional[Tuple[int, Quantity, Quantity]]]] = [(verdict, None)]
        seen = {self._design_state()}
        for _ in range(self._DESIGN_ROUNDS):
            start = (self._stirrup_n, self._stirrup_d_b, self._stirrup_s_l)
            self._redesign_from(start, forces)
            verdict = self._flexure_verdict(forces, ("bot", "top"))
            if verdict.passes:
                return
            rounds.append((verdict, start))
            state = self._design_state()
            if state in seen:
                break
            seen.add(state)
        last = len(rounds) - 1
        closest = min(
            range(len(rounds)),
            key=lambda i: (not rounds[i][0].fits, not rounds[i][0].admissible, rounds[i][0].DCR, i != last),
        )
        if closest != last:
            self._redesign_from(rounds[closest][1], forces)
        self._record_shortfall(forces)

    def _redesign_from(self, stirrup: Optional[Tuple[int, Quantity, Quantity]], forces: list[Forces]) -> None:
        """One design round: the flexure at the depth of ``stirrup``, then the stirrups for its bars.

        ``stirrup`` is ``(n_stirrups, d_b, s_l)`` to put on the section first,
        or ``None`` for the starter stirrup a first design assumes.
        """
        if stirrup is None:
            self._reset_for_design()
        else:
            self.set_transverse_rebar(*stirrup)
            self._reset_longitudinal_for_design()
        self._design_flexure(forces)
        self.design_shear(forces)

    def _record_shortfall(self, forces: list[Forces]) -> None:
        """Make a design that ends short of a moment say so, on the face that is short.

        The flexure design records the faces it could not bring up to what
        they need at the depth it was run at; the stirrups move that depth
        afterwards, so the section it ends on can fail a face the design
        never saw short -- the 2Ø20 of an ACI 20x25 carry 38.2 kN·m at the Ø8
        depth and not at the Ø10 one. Each face some combination leaves past
        DCR 1 and the design did not record is recorded here, with the
        ``A_s_req`` the check finds for it: ``As_below_required`` then says
        what is short, and a design never fails its own check in silence.
        """
        needed: Dict[str, Quantity] = {}
        for force in forces:
            check = capture_flexure_check(
                self,
                force.label,
                self._run_flexure_check(force, report=False),
                has_axial_force=force.N_x.magnitude != 0,
            )
            for face, result in (("bot", check.bottom), ("top", check.top)):
                if result.DCR > 1.0 and result.A_s_req is not None:
                    needed[face] = max(needed[face], result.A_s_req) if face in needed else result.A_s_req
        for face, A_s_req in needed.items():
            if face not in self._short_faces:
                self._short_faces[face] = (A_s_req, getattr(self, f"_A_s_{face}"))

    def _design_state(self) -> Tuple[float, ...]:
        """The reinforcement on the section as numbers, to tell one design round from another."""

        def value(x: Any) -> float:
            return float(x.to("mm").magnitude) if hasattr(x, "to") else float(x)

        bars = [self._longitudinal_snapshot(face) for face in ("b", "t")]
        longitudinal = tuple(value(v) for snapshot in bars for _, v in sorted(snapshot.items()))
        return longitudinal + (float(self._stirrup_n), value(self._stirrup_d_b), value(self._stirrup_s_l))

    def check(self, forces: list[Forces]) -> None:
        """
        Complete check: flexure + shear.
        """
        self.check_flexure(forces)
        self.check_shear(forces)

    ##########################################################
    # RESULTS
    ##########################################################

    @property
    def reinforcement(self) -> SectionReinforcement:
        """The reinforcement this beam currently carries, as plain data.

        Readable at any time — it describes the section, not a result, so it
        does not need a check to have run::

            beam.set_longitudinal_rebar_bot(n1=4, d_b1=16 * mm)
            beam.reinforcement.bottom.A_s
            beam.reinforcement.transverse.n_legs

        For what a check *demanded* of that reinforcement (``A_s_req``,
        ``DCR``), use :attr:`flexure_design` and :attr:`shear_design`.
        """
        return build_reinforcement(self)

    @property
    def section_geometry(self) -> SectionGeometry:
        """Where the bars and the stirrup legs of this section are, as data.

        Configuration, like :attr:`reinforcement`: readable at any time. The
        positions are the model the checks use -- the legs evenly spread at
        the ``s_w`` the shear check reads, the bars one clear spacing apart --
        so a drawing can show that section without deriving anything::

            geometry = beam.section_geometry
            geometry.leg_x, geometry.stirrups, geometry.bars_on("bottom")
            geometry.to_dict("cm")

        See :mod:`mento.section_geometry`.
        """
        return build_section_geometry(self)

    @property
    def compression_detailing(self) -> "CompressionDetailing":
        """Required compression-steel support in the modelled cross-section.

        Status is passed, failed, pending, not_required or not_applicable.
        Does not change resistance; the detailing state covers modelled checks.
        """
        from mento.compression_detailing import check_compression_detailing
        from mento.cage_detailing import CageDetailingError, build_cage_detailing

        scope = check_compression_detailing(self)
        if scope.reason != "base_cage_unavailable":
            return scope
        try:
            geometry = build_cage_detailing(self, include_skin=False)
        except (CageDetailingError, ValueError) as error:
            return check_compression_detailing(self, unavailable=str(error))
        return check_compression_detailing(self, geometry)

    @property
    def detailing_geometry(self) -> SectionGeometry:
        """A supported cage, with supplementary mounting steel listed separately.

        The calculated bar areas and vertical coordinates are preserved. Bars
        are placed at the cage corners, and mounting bars fill missing supports.
        Raises ``CageDetailingError`` if the layout cannot satisfy spacing.
        """
        from mento.cage_detailing import build_cage_detailing

        return build_cage_detailing(self)

    @property
    def skin_reinforcement(self) -> "SkinReinforcementRequirement":
        """Skin-steel requirement and proposed spacing, separate from resistance.

        Read after a flexure check/design to identify the tension faces. A
        deep unchecked beam reports pending; unsupported codes report unsupported.
        Only detailing_geometry validates the proposed bars against the cage.
        """
        from mento.skin_reinforcement import skin_requirement

        return skin_requirement(self)

    def set_skin_rebar(
        self, db_piel: Quantity, cant_piel_cara: int, posicion: Literal["top", "bottom", "total"] = "total"
    ) -> None:
        """Piel simétrica por lateral, con zona top, bottom o total.

        Respeta la cantidad ingresada. No modifica la resistencia ni los
        resultados resistentes; los chequeos de piel se leen del estado actual.
        """
        from mento.skin_reinforcement import ManualSkinRebar
        from copy import deepcopy
        from mento.design_results import GRID, transverse_layout

        supplied = ManualSkinRebar(db_piel, cant_piel_cara, posicion)
        if transverse_layout(self) == GRID:
            raise ValueError("Manual skin reinforcement is supported for beam cages, not grid sections.")
        assert self.settings is not None
        if db_piel < self.settings.minimum_longitudinal_diameter:
            raise ValueError("db_piel is below minimum_longitudinal_diameter.")
        self._manual_skin_rebar = deepcopy(supplied)

    @property
    def skin_rebar(self) -> "ManualSkinRebar | None":
        """Entrada manual defensiva; None significa diseño automático."""
        from copy import deepcopy

        return deepcopy(self._manual_skin_rebar)

    def clear_skin_rebar(self) -> None:
        """Volver a diseño automático con el diámetro de piel configurado."""
        self._manual_skin_rebar = None

    @property
    def skin_verification_status(self) -> str:
        """Estado seccional de la piel propuesta o ingresada, separado de resistencia."""
        from mento.cage_detailing import CageDetailingError

        try:
            req = self.skin_reinforcement
        except CageDetailingError:
            return "pending"  # El requisito no pudo evaluarse; no aprobarlo silenciosamente.
        if req.status == "not_applicable":
            return "not_applicable"
        if req.failures:
            return "failed"
        if req.status in ("pending", "unsupported"):
            return "pending"
        if req.status == "not_required" and not req.manual:
            return "not_required"
        try:
            geometry = self.detailing_geometry
            if len(geometry.skin_bars) != 2 * req.n_per_side:
                return "pending"
        except CageDetailingError as error:
            return "failed" if error.reason == "skin" else "pending"
        return "passed"

    def set_skin_service_cases(self, cases: Iterable["SkinServiceCase"]) -> None:
        """Attach independent SLS cases to this section's current reinforcement.

        Data is copied, not shared through BeamSettings. Set after design;
        any subsequent reinforcement placement requires fresh service inputs.
        """
        from copy import deepcopy

        from mento.skin_service import SkinServiceCase, service_reference

        cases = tuple(cases)
        keys = set()
        for case in cases:
            if not isinstance(case, SkinServiceCase):
                raise ValueError("Every skin service case must be a SkinServiceCase.")
            key = (case.label, case.tension_face)
            if key in keys:
                raise ValueError(f"Duplicate skin service case {case.label!r} for {case.tension_face} tension.")
            keys.add(key)
            if case.steel_stress > self.steel_bar.f_y or case.neutral_axis >= self.height:
                raise ValueError(
                    f"Skin service case {case.label!r}: stress exceeds f_yk or neutral axis is outside the section."
                )
        self._skin_service_cases = deepcopy(tuple(cases))
        self._skin_service_reference = deepcopy(service_reference(self))

    @property
    def skin_service_cases(self) -> tuple["SkinServiceCase", ...]:
        """Defensive copies of SLS cases; an altered section has none."""
        from copy import deepcopy

        from mento.skin_service import service_reference

        if self._skin_service_reference != service_reference(self):
            self._skin_service_cases = ()
            self._skin_service_reference = None
        return deepcopy(self._skin_service_cases)

    @property
    def flexure_design(self) -> FlexureDesign:
        """Longitudinal reinforcement of this beam, as plain data.

        Available after a flexure check or design has been run. Unlike
        :attr:`flexure_results`, which prints a table for a notebook, this
        returns an object you can read values from::

            beam.flexure_design.bottom.A_s
            beam.flexure_design.bottom.layers[0].n

        Raises:
            DesignNotRunError: if no flexure check or design has been run.
        """
        return build_flexure_design(self)

    @property
    def verification_status(self) -> dict[str, str]:
        """Estados separados de resistencia y de los chequeos de detallado modelados."""
        return verification_status(self)

    @property
    def warnings(self) -> Tuple[DesignWarning, ...]:
        """The detailing limits the section misses, as data.

        One :class:`~mento.design_warnings.DesignWarning` per limit and face,
        with a stable ``code``, a ``message`` in the language set with
        :func:`mento.set_language`, and the ``values`` it quotes::

            node.design()
            [w.code for w in beam.warnings]   # e.g. ["As_below_min"]

        The steel-area and stirrup limits come from the last flexure and shear
        checks (a design runs them), so they are empty until one has run; the
        bar spacing is read off the section as it is now. A warning never
        changes a DCR.
        """
        raws = list(self._flexure_warnings) if self._flexure_checked else []
        raws += spacing_warnings(self)
        raws += compression_detailing_warnings(self)
        from mento.design_warnings import transverse_proposal_warnings

        raws += transverse_proposal_warnings(self)
        raws += skin_warnings(self)
        raws += shortfall_warnings(self)
        raws += list(self._shear_warnings) if self._shear_checked else []
        return collect(raws)

    @property
    def shear_design(self) -> ShearDesign:
        """Transverse reinforcement of this beam, as plain data.

        Available after a shear check or design has been run::

            beam.shear_design.s_l
            beam.shear_design.A_v

        Raises:
            DesignNotRunError: if no shear check or design has been run.
        """
        return build_shear_design(self)

    ##########################################################
    # PRESENTATION — every one of these delegates
    ##########################################################
    # Rendering a result is a presentation choice, not part of the beam, so the
    # notebook views live in `mento.reports.views`, the Word reports in
    # `mento.reports.documents` and the drawing in `mento.plots.sections`.

    @property
    def data(self) -> None:
        """Show the section's basic data as Markdown."""
        return views.data(self)

    @property
    def flexure_results(self) -> None:
        """Show a summary of the flexure results as Markdown."""
        return views.flexure_results(self)

    @property
    def shear_results(self) -> None:
        """Show a summary of the shear results as Markdown."""
        return views.shear_results(self)

    @property
    def results(self) -> None:
        """Show every available result as Markdown."""
        return views.results(self)

    def flexure_results_detailed(self, force: Optional[Forces] = None) -> None:
        """Print the detailed flexure tables for one combination."""
        return views.flexure_results_detailed(self, force)

    def shear_results_detailed(self, force: Optional[Forces] = None) -> None:
        """Print the detailed shear tables for one combination."""
        return views.shear_results_detailed(self, force)

    @property
    def _report_text(self) -> Dict[str, str]:
        """Translated headings shared by the views and the Word reports."""
        return views._report_text(self)

    def _report_file_name(self, heading_key: str) -> str:
        return views._report_file_name(self, heading_key)

    # Beam results for Jupyter Notebook

    @property
    def _flexure_symbols(self) -> Dict[str, str]:
        r"""Flexural symbols of the active design code.

        ACI 318-19 and CIRSOC 201-25 work with a factored demand :math:`M_u` and a
        reduced capacity :math:`\phi M_n`; EN 1992-2004 works with :math:`M_{Ed}`
        and :math:`M_{Rd}`. Each code declares its own in its registry entry.
        """
        return design_code(self.concrete).flexure_symbols

    def flexure_results_detailed_doc(self, force: Optional[Forces] = None) -> None:
        """Write the detailed flexure results to a Word document.

        The assembly lives in :mod:`mento.reports.documents`.
        """
        flexure_report_doc(self, force)

    def shear_results_detailed_doc(self, force: Optional[Forces] = None) -> None:
        """Write the detailed shear results to a Word document.

        The assembly lives in :mod:`mento.reports.documents`.
        """
        shear_report_doc(self, force)

    def _format_longitudinal_rebar_string(self, n1: int, d_b1: Quantity, n2: int = 0, d_b2: Quantity = 0 * mm) -> str:
        """
        Returns a formatted string representing the rebars and their diameters.

        Rules:
        - If n1 and n2 have the same diameter → combine (e.g., 2Ø16 + 1Ø16 → 3Ø16)
        - If they differ → show both groups (e.g., 2Ø16+2Ø10)
        - If no bars exist → "-"

        A bar is written ``Ø16`` in SI and by its ASTM size, ``#5``, in US customary.
        """
        # Convert diameters safely
        phi1 = int(d_b1.to("mm").magnitude) if (d_b1 is not None and d_b1.magnitude > 0) else 0
        phi2 = int(d_b2.to("mm").magnitude) if (d_b2 is not None and d_b2.magnitude > 0) else 0
        imperial = self.concrete.is_imperial

        def mark(phi: int, d_b: Quantity) -> str:
            return bar_designation(d_b) if imperial else f"Ø{phi}"

        # No bars at all
        if n1 == 0 and n2 == 0:
            return "-"

        # Only one group
        if n2 == 0 or phi2 == 0:
            return f"{n1}{mark(phi1, d_b1)}"
        if n1 == 0 or phi1 == 0:
            return f"{n2}{mark(phi2, d_b2)}"

        # Same diameter → combine quantities
        if phi1 == phi2:
            return f"{n1 + n2}{mark(phi1, d_b1)}"

        # Different diameters → write both
        return f"{n1}{mark(phi1, d_b1)}+{n2}{mark(phi2, d_b2)}"

    ##########################################################
    # PLOT BEAM SECTION WITH REBAR
    ##########################################################

    def plot(self, show: bool = False) -> "Figure":
        """Draw the cross-section with its reinforcement.

        The drawing itself lives in :mod:`mento.plots.sections`; keeping it out of this
        class is what stops the element from being part matplotlib.
        """
        return plot_beam_section(self, show=show)
