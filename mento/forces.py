from dataclasses import dataclass, field
from typing import Dict, Optional
from mento.units import Quantity

from mento.units import kN, kNm


#: Units whose name marks a force or a moment as US customary.
_US_UNIT_NAMES = ("kip", "pound", "foot", "inch")

#: The six components, in the order of a frame model's member forces (FX, FY, FZ, MX, MY, MZ).
_COMPONENTS = ("N_x", "V_y", "V_z", "M_x", "M_y", "M_z")
_MOMENTS = ("M_x", "M_y", "M_z")


def _unit_system_of(*quantities: Quantity) -> str:
    """``"imperial"`` if any force or moment given is in US customary units, else ``"metric"``."""
    for quantity in quantities:
        if quantity.magnitude != 0 and any(name in str(quantity.units) for name in _US_UNIT_NAMES):
            return "imperial"
    return "metric"


@dataclass
class Forces:
    """
    The demand on a section: one load combination, in the section's local axes.

    The six components are those of a frame model's member forces (FX, FY, FZ, MX, MY, MZ),
    in a right-handed system where x is the member axis and z points up in the section
    (see :doc:`/user_guide/local_axes`). Every component defaults to zero, so a beam is
    given only the ones it reads.

    Sign convention
    ---------------
    - ``N_x > 0`` is **compression**; tension is negative.
    - ``M_y > 0`` **compresses the +z face**: with z up, it is sagging, tension at the bottom.
    - ``M_z > 0`` **compresses the −y face**.
    - ``V_y`` and ``V_z`` are the shears along y and z. A beam reads ``V_z`` as the
      magnitude of the design shear.
    - ``M_x`` is the moment about x. On a member, whose axis is x, it is the **torsion**.
      At a punching node the axes are the slab's, with z vertical: there ``V_z`` is the
      punching load and ``M_x`` and ``M_y`` are the unbalanced moments about the slab's two
      in-plane axes.

    Attributes
    ----------
    N_x : Quantity
        Axial force along x (default 0 kN).
    V_y : Quantity
        Shear force along y (default 0 kN).
    V_z : Quantity
        Shear force along z (default 0 kN).
    M_x : Quantity
        Moment about x: torsion on a member, in-plane moment at a punching node (default 0 kN·m).
    M_y : Quantity
        Bending moment about y (default 0 kN·m).
    M_z : Quantity
        Bending moment about z (default 0 kN·m).
    unit_system : str, optional
        The unit system to use for displaying forces ('metric' or 'imperial'). By default
        the one the forces are given in: 'imperial' when any of them is in kip, lbf or
        kip·ft, 'metric' otherwise.

    Methods
    -------
    get_forces() -> dict
        Returns the six components as a dictionary keyed by name.
    set_forces() -> None
        Sets the forces of the object with the provided values.
    compare_to(other: 'Forces', by: str = 'V_z') -> bool
        Compares this force with another force based on a given attribute.
    """

    _id: int = field(init=False, repr=False)  # Instance ID, assigned internally
    _last_id: int = field(default=0, init=False, repr=False)  # Class variable to keep track of last assigned ID
    label: Optional[str] = None
    _N_x: Quantity = field(default=0 * kN)
    _V_z: Quantity = field(default=0 * kN)
    _M_y: Quantity = field(default=0 * kNm)
    _M_x: Quantity = field(default=0 * kNm)
    _V_y: Quantity = field(default=0 * kN)
    _M_z: Quantity = field(default=0 * kNm)
    unit_system: str = field(default="metric")  # Add unit_system as a field

    def __init__(
        self,
        label: Optional[str] = None,
        N_x: Quantity = 0 * kN,
        V_z: Quantity = 0 * kN,
        M_y: Quantity = 0 * kNm,
        M_x: Quantity = 0 * kNm,
        unit_system: Optional[str] = None,
        V_y: Quantity = 0 * kN,
        M_z: Quantity = 0 * kNm,
    ) -> None:
        # V_y and M_z go after unit_system so that a call passing the first
        # arguments by position keeps its meaning.
        # Increment the class variable for the next unique ID
        Forces._last_id += 1
        self._id = Forces._last_id  # Private ID assigned internally, unique per instance

        # Initialize the label
        self.label = label
        # Shown in the units the forces were given in unless told otherwise: a
        # force in kip prints in kip, as one in kN prints in kN.
        self.unit_system = unit_system if unit_system is not None else _unit_system_of(N_x, V_y, V_z, M_x, M_y, M_z)

        # Set the forces upon initialization
        self.set_forces(N_x, V_z, M_y, M_x, V_y=V_y, M_z=M_z)

    @property
    def id(self) -> int:
        """Read-only property for accessing the unique ID of the instance."""
        return self._id

    @id.setter
    def id(self, value) -> None:  # type: ignore[no-untyped-def]
        # Normalize error message across Python versions (3.10 vs 3.11+)
        raise AttributeError("property 'id' of 'Forces' object has no setter")

    def _shown(self, name: str) -> Quantity:
        """A component in the display unit of the unit system: kN / kN·m, or kip / kip·ft."""
        value: Quantity = getattr(self, f"_{name}")
        if name in _MOMENTS:
            return value.to("kN*m") if self.unit_system == "metric" else value.to("ft*kip")
        return value.to("kN") if self.unit_system == "metric" else value.to("kip")

    @property
    def N_x(self) -> Quantity:
        """Axial force along x, positive in compression (default 0 kN)."""
        return self._shown("N_x")

    @property
    def V_y(self) -> Quantity:
        """Shear force along y (default 0 kN)."""
        return self._shown("V_y")

    @property
    def V_z(self) -> Quantity:
        """Shear force along z (default 0 kN)."""
        return self._shown("V_z")

    @property
    def M_x(self) -> Quantity:
        """Moment about x: torsion on a member, an in-plane unbalanced moment at a punching node (default 0 kN·m)."""
        return self._shown("M_x")

    @property
    def M_y(self) -> Quantity:
        """Bending moment about y, positive when it compresses the +z face (default 0 kN·m)."""
        return self._shown("M_y")

    @property
    def M_z(self) -> Quantity:
        """Bending moment about z, positive when it compresses the −y face (default 0 kN·m)."""
        return self._shown("M_z")

    def get_forces(self) -> Dict[str, Quantity]:
        """Returns the forces as a dictionary keyed 'N_x', 'V_y', 'V_z', 'M_x', 'M_y', 'M_z'."""
        return {name: self._shown(name) for name in _COMPONENTS}

    def set_forces(
        self,
        N_x: Quantity = 0 * kN,
        V_z: Quantity = 0 * kN,
        M_y: Quantity = 0 * kNm,
        M_x: Quantity = 0 * kNm,
        V_y: Quantity = 0 * kN,
        M_z: Quantity = 0 * kNm,
    ) -> None:
        """Sets the forces in the object. A component not given is set to zero."""
        self._N_x = N_x
        self._V_y = V_y
        self._V_z = V_z
        self._M_x = M_x
        self._M_y = M_y
        self._M_z = M_z

    def compare_to(self, other: "Forces", by: str = "V_z") -> bool:
        """Compares this force with another force based on a selected attribute.

        Parameters
        ----------
        other : Forces
            Another Forces instance to compare with.
        by : str
            The attribute to compare by: 'N_x', 'V_y', 'V_z', 'M_x', 'M_y' or 'M_z'.

        Returns
        -------
        bool
            True if this force is greater than the other force by the selected attribute.
        """
        if by not in _COMPONENTS:
            raise ValueError(f"Comparison attribute must be one of {', '.join(repr(c) for c in _COMPONENTS)}")
        return bool(getattr(self, by) > getattr(other, by))

    def __str__(self) -> str:
        base = f"Force ID: {self.id}, Label: {self.label}, N_x: {self.N_x}, V_z: {self.V_z}, M_y: {self.M_y}"
        # The components a beam does not read are shown only when given.
        for name in ("V_y", "M_x", "M_z"):
            if getattr(self, f"_{name}").magnitude != 0:
                base += f", {name}: {self._shown(name)}"
        return base
