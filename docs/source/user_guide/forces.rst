Forces
============

The `Forces` class in the `mento` package allows users to define and manipulate the primary forces acting on a structural element, such as axial force,
shear force, and bending moment. This class is designed for flexibility in defining forces, with the ability to adjust and retrieve
them in different stages of a design workflow. The forces themselves come from your analysis model: mento designs or checks the section that resists them.

Key Concepts
------------

- **Axial Force (`N_x`)**: Force applied along the axis of the element, along the x-x axis. **Positive in compression.**
- **Shear Force (`V_z`)**: Force acting perpendicular to the axis of the element, along the z-z local axis. **Always entered as a positive magnitude.**
- **Bending Moment (`M_y`)**: The moment caused by forces that induce bending about the y-y axis. **Positive when it produces tension at the bottom** of the section.
- **Unit System**: You can define the unit system to display the forces for a Force object, *metric* or *imperial*.

These are the main forces considered to  analyze a beam along it's main axis.
For Columns analysis in future releases, the Forces object will have to have shear and bending moment in both axis.

These forces are defined using compatible units from the `Pint` library, like `kN` or `kip` for forces and `kN*m` or `ft*kip` for moments.

Sign Convention
---------------

The signs are part of the input, not a formatting detail — they change the result of a check:

- **`N_x` is positive in compression**, negative in tension. Compression adds to the concrete
  shear strength (:math:`\sigma_{Nu} = N_u / 6 A_g` in ACI 318-19 §22.5.5.1,
  :math:`\sigma_{cp} = N_{Ed} / A_c` in EN 1992-1-1 §6.2.2(1)); a tensile force subtracts from
  it. Entering a tension force as a positive number is unconservative.
- **`M_y` is positive for sagging**, i.e. tension at the bottom fibre. The sign selects the
  tension face, so a support moment must be entered as negative for the top reinforcement to
  be designed.
- **`V_z` is the magnitude of the design shear.** The demand-capacity ratio uses its absolute
  value, but the design routine sizes stirrups from the largest required :math:`A_v` across the
  combinations, so a negative value would be read as a smaller demand.

See :doc:`local_axes` for the axes these components refer to.

Usage
-----

Below is a step-by-step guide on how to use the `Forces` class in your design workflows.

1. Creating a Forces Object
***************************

To define the forces acting on a structural element, instantiate a `Forces` object. You can provide initial values for axial force (`N_x`), shear force (`V_z`), and bending moment (`M_y`). If no values are provided, the forces default to zero.
The default unit_system for units display is *metric*.

.. code-block:: python

    from mento import Forces, kN, kNm

    # Define a forces object with specific values
    force = Forces(N_x=2*kN, V_z=10*kN, M_y=5*kNm)
    print(force)

2. Accessing Forces
*******************

Once a `Forces` object is created, you can access individual forces using the respective properties `N_x`, `V_z`, and `M_y`. These properties will return the forces in metric system by default, making it easy to inspect the current state of forces in your structure.

.. code-block:: python

    print(force.N_x)  # Output: 2.00 kN
    print(force.V_z)  # Output: 10.00 kN
    print(force.M_y)  # Output: 5.00 kN*m

If you want to display the Forces in *imperial system* just pass the input to the Force object when creating it.

.. code-block:: python

    force = Forces(N_x=2*kN, V_z=10*kN, M_y=5*kNm, unit_system="imperial")
    print(force.N_x)  # Output: 0.45 kip
    print(force.V_z)  # Output: 2.25 kip
    print(force.M_y)  # Output: 3.69 ft*kip

3. Modifying Forces
*******************

Forces can be modified at any point by calling the `set_forces()` method. This method allows you to update the values of `N_x`, `V_z`, and `M_y`.

.. code-block:: python

    # Update the axial and moment forces
    force.set_forces(N_x=3*kN, M_y=7*kNm)
    force.unit_system = "metric"
    print(force)

4. Retrieving Forces as a Dictionary
************************************

You can retrieve the forces in the form of a dictionary for easy manipulation, storage, or reporting. The `get_forces()` method returns a dictionary where the keys are `N_x`, `V_z`, and `M_y`, with values corresponding to the respective forces in the unit system.

.. code-block:: python

    force_dict = force.get_forces()
    print(force_dict)
    # Output: {'N_x': 3.00 kN, 'V_z': 10.00 kN, 'M_y': 7.00 kN*m}

5. Assigning a Label to a Force
*******************************

Optionally, you can assign a label to a force object to describe the specific load condition or scenario (e.g., "Crane load", "Wind load"). This is useful in complex models where multiple forces are acting on different elements.

.. code-block:: python

    force.label = "Crane load"
    print(force.label)  # Output: Crane load

6. Force Object ID
******************

Each `Forces` object is automatically assigned a unique ID, which can be accessed through the `id` property. This is helpful when tracking multiple force objects in more complex analyses.

.. code-block:: python

    print(force.id)  # Output: Unique ID (e.g., 1, 2, etc.)

7. Print Force complete properties
**********************************

Each `Forces` object con be printed in the terminal with `print(force)` method. This allows to quickly assess a Forces object.

.. code-block:: python

    print(force)  # Output: Force ID: 1, Label: Crane load, N_x: 3.00 kN, V_z: 0.00 kN, M_y: 7.00 kN·m

This flexible interface ensures that you can easily manage forces during the design and checking of structural elements, while maintaining clear and consistent units.
