Materials
===================

The `mento` package offers a wide range of material models,
allowing structural engineers to easily define and work with
common materials such as concrete and steel. Each material is
equipped with key mechanical properties and is compliant with
various international design codes.

Concrete Models
---------------

Concrete is one of the primary materials used in structural
engineering. In `mento`, you can work with various concrete
types, each compliant with different design codes:

* **Concrete_ACI_318_19**: Complies with the American Concrete
  Institute (ACI) 318-19 design code.
* **Concrete_EN_1992_2004**: Complies with the Eurocode 2 (EN 1992) design code.
* **Concrete_CIRSOC_201_25**: Complies with the CIRSOC 201-25 design code.

.. note::
   Create a material considering the design code that you want to use. The method for checking or designing elements won't change it's name. So just change the code and you are done.


Concrete properties depend in the design code selected. For example:

* **Compressive strength (f_c)**: The characteristic strength of
  concrete in compression for any design code, in MPa or psi units.
* **Density**: Concrete density (typically around 2500 kg/m³) for
  every code.
* **Elastic Modulus (E_c or E_cm)**: Secant modulus of elasticity
  derived from concrete strength for ACI or EC2.
* **Tensile strength (f_r or f_ctm)**: Concrete’s tensile strength
  calculated as per the design code ACI or EC2.
* **Beta_1**: A factor for the equivalent rectangular stress block,
  specific to ACI.

.. note::
   The metric system of units or imperial system of units will be automatically set based on the unit for the concrete strength.

Example: Creating ACI Concrete
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
To create concrete compliant with the ACI 318-19 standard with a
25 MPa strength:

.. code-block:: python

    from mento import Concrete_ACI_318_19, Concrete_EN_1992_2004, MPa

    concrete = Concrete_ACI_318_19(name="H25", f_c=25 * MPa)
    print(concrete)
    concrete = Concrete_EN_1992_2004(name="C25", f_c=25 * MPa)
    print(concrete)

EN 1992-1-1 design values
^^^^^^^^^^^^^^^^^^^^^^^^^

:math:`\alpha_{cc}` is a parameter of the EN concrete. EN 1992-1-1 §3.1.6(1) recommends
1.0 and lets each National Annex choose between 0.8 and 1.0; mento defaults to 0.85, the
UK National Annex value its EN beams are validated with. Pass the value your annex adopts:

.. code-block:: python

    concrete = Concrete_EN_1992_2004(name="C30", f_c=30 * MPa, alpha_cc=1.0)
    concrete.f_cd          # α_cc·f_ck/γ_c = 20 MPa
    concrete.epsilon_c2    # 0.002, Table 3.1
    concrete.epsilon_cu2   # 0.0035
    concrete.n_parabola    # 2.0, the exponent of the parabola-rectangle diagram

``epsilon_c1``, ``epsilon_cu1``, ``epsilon_c3`` and ``epsilon_cu3`` complete Table 3.1.

Steel Models
------------

Steel materials are commonly used for reinforcement bars and
prestressed tendons. `mento` provides models for these steel types:

- **SteelBar**: Reinforcing steel bars.
- **SteelStrand**: Prestressed steel strands.

Key properties of steel include:

* **Yield strength (f_y)**: The stress at which the material
  begins to deform plastically.
* **Modulus of elasticity (E_s)**: Steel’s elastic modulus,
  typically around 200 GPa.
* **Density**: Steel’s density, generally taken as 7850 kg/m³.
* **Partial factor (gamma_s)** and **design yield strength (f_yd = f_y/γ_s)**: the steel
  keeps its own γ_s, 1.15 by default (EN 1992-1-1 Table 2.1N). ACI 318-19 and CIRSOC
  201-25 put the safety in φ and never read it.
* **Design strain limit (epsilon_ud)**: EN 1992-1-1 §3.2.7(2). ``None`` by default, the
  horizontal top branch, which needs no limit; pass 0.01 or 0.9·ε_uk to bound it.

Example: Creating Reinforcing Steel
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
To create reinforcing steel with a yield strength of 420 MPa:

.. code-block:: python

    from mento import SteelBar, MPa

    steel_bar = SteelBar(name="ADN 420", f_y=420 * MPa)
    print(steel_bar)

    # EN 1992-1-1, accidental situation, strain bounded at 10 ‰
    b500 = SteelBar(name="B500S", f_y=500 * MPa, gamma_s=1.0, epsilon_ud=0.01)
    b500.f_yd        # 500 MPa

Accessing Material Properties
-----------------------------

Each material class provides a `get_properties` method that
returns a dictionary of key properties such as:

- **Concrete**: Compressive strength, tensile strength, modulus of elasticity.
- **Steel**: Yield strength, elastic modulus, and density.

Simply call this method to access material attributes. If you `print()`
a material you will get a string output with all it's properties.

.. note::
   All material properties in `mento` are automatically converted to appropriate units (MPa, kg/m³, etc.) based on the design code selected.

For more details, consult the relevant structural design codes.
