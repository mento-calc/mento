from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, TYPE_CHECKING, Any
import math
import warnings
from mento.units import kg, m, MPa, ksi, GPa, psi, Pa, lb, ft, kPa

# Conditional import for type checking only
if TYPE_CHECKING:
    from mento.units import Quantity


@dataclass
class Material:
    name: str  # Name will be provided by subclasses or instances


@dataclass
class Concrete(Material):
    f_c: Quantity = field(default=25 * MPa)
    design_code: str = field(default="ACI 318-19", init=False)
    unit_system: str = field(init=False)
    density: Quantity = field(init=False)

    def __post_init__(self) -> None:
        # Detect the unit system based on f_c
        # No lower bound is enforced on f_c, and the two codes do not agree on
        # one: ACI 318-19 Table 19.2.1.1 / CIRSOC 201-25 Tabla 19.2.1.1 put the
        # general minimum at 17 MPa (2500 psi) and 20 MPa respectively, and
        # CIRSOC raises it further for special frames and walls (25 MPa) and
        # piles (30 / 35 MPa). The density below is the unit weight of
        # reinforced concrete, for self-weight, not the w_c of ACI 318-19
        # §19.2.2.1(a) / CIRSOC 201-25 §19.2.2.1(a).
        if self.f_c.units == MPa or self.f_c.units == Pa or self.f_c.units == kPa:
            self.unit_system = "metric"
            self.density: Quantity = 2500 * kg / m**3
        elif self.f_c.units == psi or self.f_c.units == ksi:
            self.unit_system = "imperial"
            self.density = 155 * lb / ft**3
        else:
            raise ValueError(
                f"Unsupported unit system for f_c ({self.f_c.units}). Please use MPa, Pa, kPa, psi, or ksi."
            )

    def _require_metric(self) -> None:
        """Refuse US customary units for a code written only in SI.

        CIRSOC 201-25 and EN 1992-1-1 publish their coefficients in SI alone:
        an f'c in psi would run ACI's US customary formulas under CIRSOC's
        name, or divide by a metric constant that is not there under EN.
        """
        if self.is_imperial:
            raise ValueError(
                f"{self.design_code} is written in SI units: give f_c in MPa, not {self.f_c.units:~P}. "
                "US customary units (psi, ksi) are supported under ACI 318-19 only."
            )

    @property
    def is_imperial(self) -> bool:
        """True when the material was given in US customary units.

        ``unit_system`` only ever holds ``"metric"`` or ``"imperial"`` —
        ``__post_init__`` rejects anything else — so this is the whole story.
        It exists so callers that must pick between the two coefficient sets a
        design code publishes read a positive flag instead of re-deriving one
        with ``unit_system != "metric"`` at each site.
        """
        return self.unit_system == "imperial"

    def get_properties(self) -> Dict[str, Any]:
        # Return properties in the appropriate unit system
        properties = {"f_c": self.f_c, "density": self.density}
        return properties


@dataclass
class Concrete_ACI_318_19(Concrete):
    """
    Concrete_ACI_318_19 represents a concrete material model based on the ACI 318-19 code provisions.
    This class extends the base `Concrete` class and implements calculation of key material properties
    according to the American Concrete Institute (ACI) 318-19 standard, including modulus of elasticity,
    modulus of rupture, and stress block parameters. It supports both metric and imperial unit systems.

    Inputs:
        name: Name of the concrete material.
        f_c: Characteristic compressive strength of concrete.

    Methods:
        get_properties() -> Dict[str, Any]: Returns a dictionary of concrete properties.
        E_c: Returns modulus of elasticity.
        f_r (property): Returns modulus of rupture.
        beta_1 (property): Returns β₁ value.
        lambda_factor (property): Returns λ factor for lightweight concrete.
        phi_v (property): Returns shear strength reduction factor.
        phi_c (property): Returns compression-controlled strength reduction factor.
        phi_y (property): Returns tension-controlled strength reduction factor.

    Usage:
        Instantiate this class to represent a concrete material with properties and code factors
        compliant with ACI 318-19, suitable for use in structural analysis and design calculations.

    Codes:
        Every property below is ACI 318-19, and CIRSOC 201-25 reprints the same
        chapters under the same numbering, so the citations are given as a pair
        and the few places the two print different numbers are flagged where
        they arise. ``Concrete_CIRSOC_201_25`` therefore inherits all of this.
    """

    _E_c: Quantity = field(init=False)
    _f_r: Quantity = field(init=False)
    #: Maximum strain at the extreme compression fibre, ACI 318-19 §22.2.2.1 /
    #: CIRSOC 201-25 §22.2.2.1: 0.003 in both.
    _epsilon_c: float = field(default=0.003, init=False)
    _beta_1: float = field(init=False)
    _lambda: float = field(init=False)
    _phi_v: float = field(init=False)
    _phi_c: float = field(init=False)
    _phi_t: float = field(init=False)
    _flexural_min_reduction: bool = field(init=False)

    def __post_init__(self) -> None:
        super().__post_init__()
        # Adjust calculations based on unit system
        #
        # E_c: ACI 318-19 §19.2.2.1(a), Eq. (19.2.2.1.a) / CIRSOC 201-25
        #   §19.2.2.1(a), ec. (19.2.2.1.a). CIRSOC 201-25 §19.2.2.1(a) differs
        #   in the range it is written for -- w_c from 1400 to 2500 kg/m3
        #   against ACI's 1440 to 2560 -- so the 2500 kg/m3 this evaluates at
        #   sits exactly on CIRSOC's upper edge. Both codes also give
        #   §19.2.2.1(b), E_c = 4700*sqrt(f'c) (57000*sqrt(f'c) in psi), which
        #   is the expression written for normalweight concrete.
        # f_r: ACI 318-19 Eq. (19.2.3.1) / CIRSOC 201-25 ec. (19.2.3.1) of
        #   §19.2.3. Both print f_r = 0.62*lambda*sqrt(f'c) (7.5*lambda in psi);
        #   the metric 0.625 without lambda below is not that expression -- it
        #   reads 0.8 % high, and drops lambda, which only agrees while the
        #   concrete is normalweight.
        if self.unit_system == "metric":
            self._E_c = ((self.density / (kg / m**3)) ** 1.5) * 0.043 * math.sqrt(self.f_c / MPa) * MPa
            self._f_r = 0.625 * math.sqrt(self.f_c / MPa) * MPa
        else:  # imperial
            self._E_c = ((self.density / (lb / ft**3)) ** 1.5) * 33 * math.sqrt(self.f_c / psi) * psi
            self._f_r = 7.5 * math.sqrt(self.f_c / psi) * psi
        self._beta_1 = self.__beta_1()
        # ACI 318-19 §19.2.4.3 / CIRSOC 201-25 §19.2.4.3: lambda = 1.0 for
        # normalweight concrete. Lightweight concrete is not offered; it would
        # read off ACI 318-19 Table 19.2.4.1(a) / CIRSOC 201-25 Tabla 19.2.4.1(a),
        # which is one of the tables the two codes do not print alike.
        self._lambda = 1  # Normalweight concrete
        # phi: ACI 318-19 Table 21.2.1 / CIRSOC 201-25 Tabla 21.2.1, identical.
        # Row (b) gives 0.75 for shear; row (a) sends moment and axial force to
        # ACI 318-19 Table 21.2.2 / CIRSOC 201-25 Tabla 21.2.2, which is where
        # the 0.65 of a compression-controlled section and the 0.90 of a
        # tension-controlled one (eps_t >= eps_ty + 0.003) come from.
        self._phi_v = 0.75  # Shear strength reduction factor
        self._phi_c = 0.65  # Compression controlled strength reduction factor
        self._phi_t = 0.90  # Tension controlled strength reduction factor
        # ACI 318-19 §9.6.1.3 / CIRSOC 201-25 §9.6.1.3: As,min need not be met
        # where the steel provided is at least one third greater than the steel
        # the analysis asks for.
        self._flexural_min_reduction = True  # True selects 4/3 of calculated steel if it's less than minimum

    def get_properties(self) -> Dict[str, Any]:
        properties = super().get_properties()
        properties["E_c"] = self._E_c
        properties["f_r"] = self._f_r
        properties["beta_1"] = self._beta_1
        properties["epsilon_c"] = self._epsilon_c
        properties["lambda"] = self._lambda
        properties["phi_v"] = self._phi_v
        properties["phi_c"] = self._phi_c
        properties["phi_t"] = self._phi_t
        return properties

    def __beta_1(self) -> float:
        """beta_1 of the equivalent rectangular stress block.

        ACI 318-19 Table 22.2.2.4.3 / CIRSOC 201-25 Tabla 22.2.2.4.3, reached
        from §22.2.2.4.3 in both. The values are the same in the two codes:
        (a) 0.85, (b) 0.85 - 0.05*(f'c - 28)/7, (c) 0.65; in psi the breaks are
        at 4000 and 8000. CIRSOC 201-25 Tabla 22.2.2.4.3 differs only in where
        row (a) starts -- 20 <= f'c against ACI's 17 <= f'c -- which is the
        lower bound on f'c of each code's Table 19.2.1.1 and not a different
        value of beta_1; below it both tables simply stop, and this returns
        0.85, the value of row (a).

        Row (b) is written for the open interval 28 < f'c < 55 (4000 < f'c <
        8000 psi) and row (c) for f'c >= 55 (>= 8000 psi), so the two break
        points themselves belong to row (c) and the ``<`` below is what the
        tables print. In psi row (b) evaluated at 8000 happens to land on 0.65
        as well, so that edge only reads differently; in MPa row (b) at 55
        gives 0.6571, 1.1 % above the 0.65 of row (c), and beta_1 feeds
        rho_max, so the strict comparison is the one that matters.

        The two codes agree on every value here, so there is nothing for the
        registry to vary.
        """
        if self.unit_system == "metric":
            fc_MPa = self.f_c.to("MPa").magnitude
            if fc_MPa <= 28:
                return 0.85
            elif fc_MPa < 55:
                return 0.85 - 0.05 / 7 * (fc_MPa - 28)
            else:
                return 0.65
        else:
            fc_psi = self.f_c.to("psi").magnitude
            if fc_psi <= 4000:
                return 0.85
            elif fc_psi < 8000:
                return 0.85 - 0.05 / 1000 * (fc_psi - 4000)
            else:
                return 0.65

    @property
    def E_c(self) -> Quantity:
        return self._E_c

    @property
    def f_r(self) -> Quantity:
        return self._f_r

    @property
    def beta_1(self) -> float:
        return self._beta_1

    @property
    def lambda_factor(self) -> float:
        return self._lambda

    @property
    def phi_v(self) -> float:
        return self._phi_v

    @property
    def phi_c(self) -> float:
        return self._phi_c

    @property
    def phi_y(self) -> float:
        return self._phi_t

    def __str__(self) -> str:
        properties = self.get_properties()
        return (
            f"Concrete Properties ({self.name}):\n"
            f"  f_c: {properties['f_c']}\n"
            f"  Density: {properties['density']}\n"
            f"  E_c: {properties['E_c']}\n"
            f"  f_r: {properties['f_r']}\n"
            f"  beta_1: {properties['beta_1']:.3f}\n"  # Format as float
            f"  epsilon_c: {properties['epsilon_c']:.4f}\n"  # Format as float
            f"  λ: {properties['lambda']:.2f}\n"
            f"  phi_v: {properties['phi_v']:.2f}\n"
            f"  phi_c: {properties['phi_c']:.2f}\n"
            f"  phi_t: {properties['phi_t']:.2f}\n"
        )


@dataclass
class Concrete_CIRSOC_201_25(Concrete_ACI_318_19):
    """Concrete class for a CIRSOC 201-25 design code with metric units.

    CIRSOC 201-25 reprints the ACI 318-19 material chapters under the same
    numbering, so every property is inherited unchanged: eps_cu = 0.003
    (§22.2.2.1), lambda = 1.0 (§19.2.4.3), phi (Tabla 21.2.1 and Tabla 21.2.2),
    E_c (§19.2.2.1) and f_r (ec. 19.2.3.1) all read the same in both.

    Where the printed text does differ, the difference is in the domain of a
    table rather than in the expression, and neither is checked here:
    CIRSOC 201-25 Tabla 19.2.1.1 puts the general minimum f'c at 20 MPa where
    ACI 318-19 Table 19.2.1.1 puts it at 17 MPa, and CIRSOC 201-25
    Tabla 22.2.2.4.3 starts its first row at 20 MPa where ACI 318-19
    Table 22.2.2.4.3 starts at 17 MPa.
    """

    def __post_init__(self) -> None:
        # Call the parent class's __post_init__ to inherit initializations
        super().__post_init__()
        # Override the design code for this specific class
        self.design_code = "CIRSOC 201-25"
        self._require_metric()


@dataclass
class Concrete_EN_1992_2004(Concrete):
    """
    Concrete_EN_1992_2004 represents concrete material properties and design parameters according to Eurocode EN 1992-1-1:2004.
    This class extends the base `Concrete` class, providing Eurocode-specific calculations for characteristic and mean strengths,
    modulus of elasticity, and other design factors. It encapsulates the following key methods:

    Inputs:
        name: Name of the concrete material.
        f_c: Characteristic compressive strength of concrete (f_ck for Eurocode).
        alpha_cc: Coefficient for long term effects on the compressive strength, §3.1.6(1).

    EN 1992-1-1 recommends α_cc = 1.0 and lets the National Annex choose between 0.8 and
    1.0. The default is 0.85, the UK National Annex value mento's EN beams were validated with.

    Methods:
        get_properties() -> Dict[str, Any]: Returns a dictionary of all relevant material properties.
        E_cm (property): Returns the secant modulus of elasticity.
        f_ck (property): Returns the characteristic compressive strength.
        f_cm (property): Returns the mean compressive strength.
        f_ctm (property): Returns the mean tensile strength.
        f_cd (property): Returns the design compressive strength α_cc·f_ck/γ_c, §3.1.6(1).
        epsilon_c2, epsilon_cu2 (properties): Strains of the parabola-rectangle diagram, Table 3.1.
        n_parabola (property): Exponent n of the parabola, Table 3.1 and eq. (3.17).
        epsilon_c3, epsilon_cu3 (properties): Strains of the bilinear diagram, Table 3.1.
        epsilon_cu1 (property): Ultimate strain of the diagram for structural analysis, Table 3.1.
        gamma_c (property): Returns the partial safety factor for concrete.
        Lambda_factor (property): Returns the λ factor.
        Eta_factor (property): Returns the η factor.

    Usage:
        This class is intended for use in structural engineering applications where concrete properties must comply with EN 1992-1-1:2004.
        It provides all necessary parameters for design and verification according to the code.
    """

    alpha_cc: float = field(default=0.85)

    def __post_init__(self) -> None:
        # Crucial: Call parent's __post_init__ first to set unit_system and density
        super().__post_init__()
        self.design_code = "EN 1992-2004"
        self._require_metric()
        # §3.1.6(1): "The value of alpha_cc for use in a Country should lie between 0,8
        # and 1,0." 1.0 is the recommended value; the UK National Annex takes 0.85.
        if not 0.8 <= self.alpha_cc <= 1.0:
            raise ValueError(f"alpha_cc must lie between 0.8 and 1.0 (EN 1992-1-1 §3.1.6(1)), got {self.alpha_cc}.")

        # The f_c passed to Concrete is the f_ck for Eurocode
        self._delta = 0.85
        self._f_ck = self.f_c
        # Converted once: lambda and eta are asked for it several times per
        # check, and f_ck does not change after construction.
        self._f_ck_MPa: float = self._f_ck.to(MPa).magnitude
        self._f_cm: Quantity = self._f_ck + 8 * MPa
        self._E_cm = 22000 * (self._f_cm.to("MPa").magnitude / 10) ** 0.3 * MPa
        self._f_ctm = 0.3 * (self._f_ck.to("MPa").magnitude) ** (2 / 3) * MPa
        self._epsilon_cu1 = (
            2.8 + 27 * ((98 - self._f_cm.to("MPa").magnitude) / 100) ** 4 if self._f_ck >= 50 * MPa else 3.5
        ) * 1e-3
        self._epsilon_c2 = (
            2.0 + 0.085 * (self._f_ck.to("MPa").magnitude - 50) ** 0.53 if self._f_ck >= 50 * MPa else 2.0
        ) * 1e-3
        self._epsilon_cu2 = (
            2.6 + 35 * ((90 - self._f_ck.to("MPa").magnitude) / 100) ** 4 if self._f_ck >= 50 * MPa else 3.5
        ) * 1e-3
        self._epsilon_c3 = (
            1.75 + 0.55 * ((self._f_ck.to("MPa").magnitude - 50) / 40) if self._f_ck >= 50 * MPa else 1.75
        ) * 1e-3
        self._epsilon_cu3 = (
            2.6 + 35 * ((90 - self._f_ck.to("MPa").magnitude) / 100) ** 4 if self._f_ck >= 50 * MPa else 3.5
        ) * 1e-3
        # Exponent of the parabola, Table 3.1 and eq. (3.17).
        self._n_parabola = (
            1.4 + 23.4 * ((90 - self._f_ck.to("MPa").magnitude) / 100) ** 4 if self._f_ck >= 50 * MPa else 2.0
        )
        self._gamma_c = 1.5
        # Kept only for the deprecated gamma_s property: gamma_s belongs to the steel.
        self._gamma_s = 1.15
        # Default values for k values EN_1992-1-1 - ART 5.5:
        # k_1..k_4 bound the neutral axis ratio x_u/d in eqs. (5.10a)/(5.10b);
        # k_5 and k_6 are plain lower bounds on the redistribution ratio delta
        # itself (Class B/C and Class A reinforcement), so they are pure numbers.
        self._k_1 = 0.44
        self._k_2 = 1.25 * (0.6 + 0.0014 / self._epsilon_cu2)
        self._k_3 = 0.54
        self._k_4 = 1.25 * (0.6 + 0.0014 / self._epsilon_cu2)
        self._k_5 = 0.7
        self._k_6 = 0.8

    def _lambda_factor(self) -> float:
        """
        Calculate the effective compression zone depth factor (λ) as per EN 1992-1-1.
        """
        f_ck_mpa = self._f_ck_MPa
        if f_ck_mpa <= 50:
            return 0.8
        else:
            return 0.8 - (f_ck_mpa - 50) / 400

    def _eta_factor(self) -> float:
        """
        Calculate the effective compressive strength factor (η) as per EN 1992-1-1.
        """
        f_ck_mpa = self._f_ck_MPa
        if f_ck_mpa <= 50:
            return 1.0
        else:
            return 1.0 - (f_ck_mpa - 50) / 200

    def get_properties(self) -> Dict[str, Any]:
        properties = super().get_properties()
        properties.update(
            {
                "E_cm": self._E_cm,
                "f_ck": self._f_ck,
                "f_cm": self._f_cm,
                "f_ctm": self._f_ctm,
                "f_cd": self.f_cd,
                "epsilon_c2": self._epsilon_c2,
                "epsilon_cu2": self._epsilon_cu2,
                "n_parabola": self._n_parabola,
                "epsilon_cu3": self._epsilon_cu3,
                "gamma_c": self._gamma_c,
                # Deprecated: gamma_s is the steel's (Steel.gamma_s). Kept so a reader of
                # this dictionary does not break.
                "gamma_s": self._gamma_s,
                "alpha_cc": self.alpha_cc,
                "lambda_factor": self._lambda_factor(),
                "eta_factor": self._eta_factor(),
            }
        )
        return properties

    @property
    def E_cm(self) -> Quantity:
        return self._E_cm

    @property
    def f_ck(self) -> Quantity:
        return self._f_ck

    @property
    def f_cm(self) -> Quantity:
        return self._f_cm

    @property
    def f_ctm(self) -> Quantity:
        return self._f_ctm

    @property
    def f_cd(self) -> Quantity:
        """Design compressive strength, f_cd = α_cc·f_ck/γ_c (§3.1.6(1), eq. (3.15))."""
        return (self.alpha_cc * self._f_ck / self._gamma_c).to("MPa")

    @property
    def epsilon_c1(self) -> float:
        """Strain at peak stress of the diagram for structural analysis, Table 3.1: 0.7·f_cm^0.31 ≤ 2.8 ‰."""
        return min(0.7 * self._f_cm.to("MPa").magnitude ** 0.31, 2.8) * 1e-3

    @property
    def epsilon_cu1(self) -> float:
        """Ultimate strain of the diagram for structural analysis, Table 3.1."""
        return self._epsilon_cu1

    @property
    def epsilon_c2(self) -> float:
        """Strain at which the parabola reaches f_cd, Table 3.1 (2.0 ‰ up to C50/60)."""
        return self._epsilon_c2

    @property
    def epsilon_cu2(self) -> float:
        """Ultimate strain of the parabola-rectangle diagram, Table 3.1 (3.5 ‰ up to C50/60)."""
        return self._epsilon_cu2

    @property
    def n_parabola(self) -> float:
        """Exponent n of the parabola, Table 3.1 and eq. (3.17): 2.0 up to C50/60."""
        return self._n_parabola

    @property
    def epsilon_c3(self) -> float:
        """Strain at which the bilinear diagram reaches f_cd, Table 3.1 (1.75 ‰ up to C50/60)."""
        return self._epsilon_c3

    @property
    def epsilon_cu3(self) -> float:
        """Ultimate strain of the bilinear and rectangular diagrams, Table 3.1 (3.5 ‰ up to C50/60)."""
        return self._epsilon_cu3

    @property
    def gamma_c(self) -> float:
        return self._gamma_c

    @property
    def gamma_s(self) -> float:
        """Deprecated: γ_s is a property of the steel. Read ``steel_bar.gamma_s``."""
        warnings.warn(
            "Concrete_EN_1992_2004.gamma_s is deprecated and will be removed in mento 2.0: "
            "the partial factor of the reinforcement belongs to the steel. Read SteelBar.gamma_s.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self._gamma_s

    @property
    def Lambda_factor(self) -> float:  # Property for lambda_factor
        return self._lambda_factor()

    @property
    def Eta_factor(self) -> float:  # Property for eta_factor
        return self._eta_factor()

    def __str__(self) -> str:
        """Customize the string representation for user-friendly display."""
        properties = self.get_properties()
        # Access magnitude for dimensionless quantities
        return (
            f"Concrete Properties ({self.name}):\n"
            f"  Design Code: {self.design_code}\n"
            f"  f_c (Characteristic): {properties['f_ck']}\n"
            f"  f_cm (Mean Compressive): {properties['f_cm']}\n"
            f"  f_ctm (Mean Tensile): {properties['f_ctm']}\n"
            f"  E_cm (Secant Modulus): {properties['E_cm']}\n"
            f"  Density: {properties['density']}\n"
            f"  f_cd: {properties['f_cd']}\n"
            f"  ε_c2: {properties['epsilon_c2']:.4f}\n"
            f"  ε_cu2: {properties['epsilon_cu2']:.4f}\n"
            f"  n: {properties['n_parabola']:.2f}\n"
            f"  ε_cu3: {properties['epsilon_cu3']:.4f}\n"
            f"  γ_c: {properties['gamma_c']:.2f}\n"
            f"  α_cc: {properties['alpha_cc']:.2f}\n"
            f"  λ Factor: {properties['lambda_factor']:.2f}\n"
            f"  Eta Factor: {properties['eta_factor']:.2f}"
        )


@dataclass
class Steel(Material):
    """Reinforcing steel, given by its specified yield strength.

    ``f_y`` is taken as given: no upper bound is enforced, and the two codes
    state theirs differently. ACI 318-19 §20.2.2.3 sends to Table 20.2.2.4(a),
    which caps f_y by application: 690 MPa for flexure, axial force and
    shrinkage and temperature in the general case, against 420 MPa for
    stirrups, ties and hoops. CIRSOC 201-25 §20.2.2.3 sends instead to
    §20.2.1.3, Tablas 20.2.1 and 20.2.2, which do not cap a value but list the
    IRAM steels the code is written for and the characteristic yield strength
    of each (AL 220: 220 MPa; ADN 420: 420 MPa; ATR 500 N and AM 500 N wires
    and welded mesh: 500 MPa). The cap that does reach a calculation, on f_yt
    for shear, is applied in the shear equations, not here.

    The design values belong to the steel as well. ``gamma_s`` is the partial
    factor of EN 1992-1-1 Table 2.1N (1.15 for persistent and transient
    situations, 1.0 for accidental ones) and ``f_yd = f_y/gamma_s``. ACI 318-19
    and CIRSOC 201-25 put the safety in φ instead, and never read either.

    ``epsilon_ud`` is the design limit on the steel strain, EN 1992-1-1
    §3.2.7(2). ``None``, the default, is the horizontal top branch of
    §3.2.7(2)b, which needs no limit, and the elastic-perfectly plastic
    steel of ACI 318-19 §20.2.2.1. A section analysis that bounds the strain
    passes the value it uses: 0.9·ε_uk (§3.2.7(2) note) or 0.01, for example.
    """

    _f_y: Quantity = field(init=False)
    _density: Quantity = field(default=7850 * kg / m**3)
    _gamma_s: float = field(default=1.15)
    _epsilon_ud: float | None = field(default=None)

    def __init__(
        self,
        name: str,
        f_y: Quantity,
        density: Quantity = 7850 * kg / m**3,
        gamma_s: float = 1.15,
        epsilon_ud: float | None = None,
    ):
        super().__init__(name)
        if gamma_s <= 0:
            raise ValueError(f"gamma_s must be positive, got {gamma_s}.")
        if epsilon_ud is not None and epsilon_ud <= 0:
            raise ValueError(f"epsilon_ud must be positive, got {epsilon_ud}.")
        self._f_y = f_y
        self._density = density
        self._gamma_s = gamma_s
        self._epsilon_ud = epsilon_ud

    @property
    def f_y(self) -> Quantity:
        return self._f_y

    @property
    def density(self) -> Quantity:
        return self._density

    @property
    def gamma_s(self) -> float:
        """Partial factor of the steel, EN 1992-1-1 Table 2.1N. Not read under ACI 318-19 or CIRSOC 201-25."""
        return self._gamma_s

    @property
    def f_yd(self) -> Quantity:
        """Design yield strength, f_yd = f_y/γ_s (EN 1992-1-1 §3.2.7(2))."""
        return self._f_y / self._gamma_s

    @property
    def epsilon_ud(self) -> float | None:
        """Design limit on the steel strain (EN 1992-1-1 §3.2.7(2)); ``None`` for no limit."""
        return self._epsilon_ud


def _check_epsilon_ud(steel: SteelBar | SteelStrand) -> None:
    """A strain limit below the yield strain would keep the steel from ever reaching f_yd."""
    if steel.epsilon_ud is not None and steel.epsilon_ud <= steel.epsilon_yd:
        raise ValueError(
            f"epsilon_ud = {steel.epsilon_ud} is not above the design yield strain f_yd/E_s = "
            f"{steel.epsilon_yd:.5f}: the steel would never yield."
        )


@dataclass
class SteelBar(Steel):
    #: ACI 318-19 §20.2.2.2 / CIRSOC 201-25 §20.2.2.2: E_s may be taken as
    #: 200,000 MPa (29,000,000 psi) for nonprestressed bars and wires. Same
    #: value in both codes; EN 1992-1-1 §3.2.7(4) takes the same 200 GPa.
    _E_s: Quantity = field(default=200 * GPa)
    _epsilon_y: Quantity = field(init=False)

    def __init__(
        self,
        name: str,
        f_y: Quantity,
        density: Quantity = 7850 * kg / m**3,
        gamma_s: float = 1.15,
        epsilon_ud: float | None = None,
    ):
        super().__init__(name, f_y, density, gamma_s, epsilon_ud)
        # eps_ty = f_y/E_s — ACI 318-19 §21.2.2.1 / CIRSOC 201-25 §21.2.2.1.
        # Both also permit 0.002 for Grade 420 (f_y = 420 MPa); the quotient is
        # kept instead, 0.0021 for that grade, which is the exact value the
        # clause rounds.
        self._epsilon_y = f_y.to("MPa") / (self._E_s.to("MPa"))
        _check_epsilon_ud(self)

    @property
    def E_s(self) -> Quantity:
        return self._E_s

    @property
    def epsilon_y(self) -> Quantity:
        return self._epsilon_y

    @property
    def epsilon_yd(self) -> float:
        """Design yield strain, f_yd/E_s: where the diagram of EN 1992-1-1 Fig. 3.8 turns."""
        return float((self.f_yd / self._E_s).to("dimensionless").magnitude)

    def get_properties(self) -> Dict[str, Any]:
        properties = {
            "E_s": self._E_s.to("GPa"),
            "f_y": self._f_y.to("MPa"),
            "epsilon_y": self._epsilon_y,
            "gamma_s": self._gamma_s,
            "f_yd": self.f_yd.to("MPa"),
            "epsilon_ud": self._epsilon_ud,
        }
        return properties

    def __str__(self) -> str:
        """Customize the string representation for user-friendly display."""
        properties = self.get_properties()
        return (
            f"SteelBar Properties ({self.name}):\n"
            f"  f_y: {properties['f_y']}\n"
            f"  E_s: {properties['E_s']}\n"
            f"  epsilon_y: {properties['epsilon_y'].magnitude:.4f}\n"
            f"  Density: {self.density}"
        )


@dataclass
class SteelStrand(Steel):
    _f_u: Quantity = field(default=1860 * MPa)
    _E_s: Quantity = field(default=190000 * MPa)
    prestress_stress: Quantity = field(default=0 * MPa)
    _epsilon_y: Quantity = field(init=False)

    def __init__(
        self,
        name: str,
        f_y: Quantity,
        density: Quantity = 7850 * kg / m**3,
        gamma_s: float = 1.15,
        epsilon_ud: float | None = None,
    ):
        super().__init__(name, f_y, density, gamma_s, epsilon_ud)
        self._epsilon_y = self._f_y / self._E_s
        _check_epsilon_ud(self)

    def get_properties(self) -> Dict[str, Any]:
        properties = {
            "E_s": self._E_s.to("MPa"),
            "f_y": self._f_y.to("MPa"),
            "f_u": self._f_u.to("MPa"),
        }
        return properties

    @property
    def f_u(self) -> Quantity:
        return self._f_u

    @property
    def E_s(self) -> Quantity:
        return self._E_s

    @property
    def epsilon_y(self) -> Quantity:
        return self._epsilon_y

    @property
    def epsilon_yd(self) -> float:
        """Design yield strain, f_yd/E_s."""
        return float((self.f_yd / self._E_s).to("dimensionless").magnitude)

    def __str__(self) -> str:
        """Customize the string representation for user-friendly display."""
        properties = self.get_properties()
        return (
            f"SteelStrand Properties ({self.name}):\n"
            f"  f_y: {properties['f_y']}\n"
            f"  f_u: {properties['f_u']}\n"
            f"  E_s: {properties['E_s']}\n"
            f"  epsilon_y: {self.epsilon_y.magnitude:.4f}\n"
            f"  Prestress Stress: {self.prestress_stress}\n"
            f"  Density: {self.density}"
        )
