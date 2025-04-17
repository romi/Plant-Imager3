# Plant Imager Project Guidelines

This document outlines the coding standards and best practices for the Plant Imager project.
Following these guidelines ensures consistency, readability, and maintainability across the codebase.

## Table of Contents
- [File Structure](#file-structure)
- [Documentation Standards](#documentation-standards)
  - [Module Documentation](#module-documentation)
  - [Docstrings](#docstrings)
  - [Inline Comments](#inline-comments)
- [Type Hints](#type-hints)
- [Code Style](#code-style)
- [Examples](#examples)

## File Structure

All Python files should:
1. Start with a shebang line: `#!/usr/bin/env python3`
2. Include UTF-8 encoding declaration: `# -*- coding: utf-8 -*-`
3. Include license information if applicable
4. Follow with module documentation
5. Include imports in a logical order (standard library, third-party, local) and always split them
6. Define constants, classes, and functions

Example:
```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# plantimager - Python tools for the ROMI 3D Plant Imager
#
# Copyright (C) 2018 Sony Computer Science Laboratories
# Authors: D. Colliaux, T. Wintz, P. Hanappe
#
# This file is part of plantimager.
#
# plantimager is free software: you can redistribute it
# and/or modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation, either
# version 3 of the License, or (at your option) any later version.
#
# plantimager is distributed in the hope that it will be
# useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with plantimager.  If not, see
# <https://www.gnu.org/licenses/>.

"""Module title and brief description.

Key Features
------------

- Feature 1
- Feature 2

Usage Examples
--------------

```python
>>> import example_module
>>> example_module.function()
```
"""

import os
import time

import numpy as np

from .module import Class
```

Only apply rules 1 and 2 to __init__.py files.

## Documentation Standards

### Module Documentation

Module documentation should appear after any license information and before imports. It should include:

1. **Title and Brief Description**: One or two sentences describing the module's purpose
2. **Key Features**: A section with bullet points highlighting the module's main functionality
3. **Usage Examples**: A minimal example demonstrating how to use the module

Example:
```python
"""GRBL-based CNC Controller for Plant Imaging Systems.

A concrete implementation of CNC machine control for 3D plant imaging systems using the GRBL firmware.
This module enables precise XYZ positioning with millimeter accuracy for X/Y axes and degree accuracy for the rotational Z axis.

Key Features:
- Serial communication with GRBL controller boards
- Complete 3-axis (X, Y, Z) movement control with position tracking
- Support for both synchronous and asynchronous operations
- Safety features including position limits and homing procedures
- Comprehensive access to GRBL firmware settings
- Proper error handling and machine status reporting
- Hardware abstraction layer compliant with AbstractCNC interface

Usage Examples:
```python
>>> from plantimager.controller.scanner.grbl import CNC
>>> cnc = CNC("/dev/ttyUSB0")  # Connect to GRBL controller
>>> cnc.home()  # Perform a homing sequence
>>> cnc.moveto(100, 100, 45)  # Move to position (100mm, 100mm, 45°)
>>> x, y, z = cnc.get_position()  # Get the current position
>>> cnc.moveto_async(200, 200, 90)  # Start asynchronous movement
>>> cnc.wait()  # Wait for movement completion
```
"""
```

### Docstrings

Use the NumPy docstring format with proper section headers. Docstrings should be comprehensive yet concise.

#### Class Docstrings

Class docstrings should include:
1. A brief summary line describing the purpose
2. A more detailed description if necessary
3. Attributes section listing all public attributes
4. Notes section for important implementation details
5. Examples section with runnable code
6. References section if applicable

Example:
```python
class CNC(AbstractCNC):
    """A concrete implementation of CNC machine control using GRBL firmware.

    This class provides functionality to control a CNC machine running GRBL firmware
    over a serial connection. It supports movement along X, Y, and Z axes, homing,
    position queries, and both synchronous and asynchronous operations.

    Attributes
    ----------
    port : str
        Serial port used for communication
    baud_rate : int
        Communication baudrate (typically 115200 for Arduino UNO)
    x_lims : tuple[float, float]
        Allowed range for X-axis movement
    y_lims : tuple[float, float]
        Allowed range for Y-axis movement
    z_lims : tuple[float, float]
        Allowed range for Z-axis movement (rotationa axis)
    serial_port : serial.Serial
        Serial connection instance
    invert_x : bool
        Whether to invert X-axis direction
    invert_y : bool
        Whether to invert Y-axis direction
    invert_z : bool
        Whether to invert Z-axis direction
    grbl_settings : dict
        Current GRBL configuration parameters

    Notes
    -----
    - All movements are performed in absolute coordinates (G90 mode)
    - Units are set to millimeters (G21 mode)
    - Position limits are enforced for safety
    - Homing is performed on startup

    Examples
    --------
    >>> from plantimager.controller.scanner.grbl import CNC
    >>> cnc = CNC("/dev/ttyACM0")  # Initialize CNC connection
    >>> cnc.home()  # Perform homing sequence
    >>> cnc.moveto(100, 100, 50)  # Move to position synchronously
    >>> x, y, z = cnc.get_position()  # Get current position
    >>> cnc.moveto_async(200, 200, 50)  # Move asynchronously
    >>> cnc.wait()  # Wait for move to complete

    Raises
    ------
    ValueError
        If movement coordinates are outside allowed limits
    RuntimeError
        If unable to read position from CNC
    SerialException
        If serial communication fails

    References
    ----------
    - GRBL Commands: https://github.com/gnea/grbl/wiki/Grbl-v1.1-Commands
    - G-Code Reference: http://linuxcnc.org/docs/html/gcode/g-code.html
    """
```

#### Method Docstrings

Method docstrings should include:
1. A brief summary line describing the purpose
2. Parameters section with name, type, and description for each parameter
3. Returns section with type and description of return value
4. Raises section for any exceptions that may be raised
5. Notes section for important implementation details
6. Examples section with runnable code
7. See Also section for related methods/functions
8. References section if applicable

Example:
```python
def moveto(self, x, y, z):
    """Move the CNC machine to specified coordinates and wait until the target position is reached.

    Parameters
    ----------
    x : length_mm
        Target position along the X-axis in millimeters. Must be within the
        machine's x_lims range.
    y : length_mm
        Target position along the Y-axis in millimeters. Must be within the
        machine's y_lims range.
    z : deg
        Target position along the Z-axis in degrees. Must be within the
        machine's z_lims range.

    Raises
    ------
    ValueError
        If any of the target coordinates are outside the allowed limits defined
        in x_lims, y_lims, or z_lims.
    RuntimeError
        If the movement cannot be completed or position verification fails.

    Notes
    -----
    - The movement is performed in absolute coordinates (``G90`` mode)
    - Units are in millimeters (``G21`` mode)
    - The method will block until the movement is complete
    """
```

#### Docstring Rules

1. All sections should be properly indented
2. Parameter types should be specific, accurate, and contain the full reference (like `numpy.ndarray` and not just `ndarray`)
3. Examples should be runnable and illustrative
4. When referring to a parameter anywhere within the docstring, enclose its name in single backticks: `parameter_name`
5. When referring to a parameter default value, use double backticks: ``None``, ``True``, or ``10.0``
6. Keep descriptions clear and concise
7. Add any relevant warnings or notes
8. Include type hints for complex return values
9. Document any exceptions that may be raised
10. Avoid duplicating ideas between the longer class or method description and the notes section

### Inline Comments

Inline comments should be:
1. Concise and informative
2. Explain key logic, important variables, and non-obvious operations
3. Placed on the line above the code they describe, not at the end of the line
4. Written in complete sentences with proper punctuation
5. The comments may be grouped over several lines of code or omitted if the code is obvious 

Example:
```python
# Calculate direction signs for each axis based on homing and direction masks
# XOR operation determines if a pull-off direction should be inverted
sign_x = -1 if pulloff_mask ^ dir_mask & 1 else 1  # Check bit 0 for X axis
sign_y = -1 if pulloff_mask ^ dir_mask & 2 else 1  # Check bit 1 for Y axis
sign_z = -1 if pulloff_mask ^ dir_mask & 4 else 1  # Check bit 2 for Z axis
```

## Type Hints

All code should include comprehensive and accurate Python type hints following PEP 484, PEP 585, and PEP 604 standards.

### Type Hint Rules

1. Use proper typing modules:
   ```python
   from typing import List, Dict, Optional, Union, Callable, TypeVar, Protocol, Literal, TypedDict, NoReturn
   ```

2. Use Python 3.10+ new syntax for union types:
   ```python
   # Python 3.10+
   str | None
   int | float
   ```

4. Specify types for:
   - Function parameters and return values
   - Class attributes and methods
   - Variables with complex types
   - Generic types where appropriate

5. Use appropriate type annotations:
   - `-> None` for functions that don't return anything
   - `-> NoReturn` for functions that never return (raise exceptions)
   - `Type | None` for optional parameters
   - `Callable[[ArgType1, ArgType2], ReturnType]` for function parameters
   - `TypeVar` for polymorphic types
   - `Protocol` for duck typing
   - `Literal` for constrained string/number options
   - `TypedDict` for dictionary structures with known keys

6. Add informative type aliases for complex types:
   ```python
   from typing import Dict, List, Tuple, TypedDict

   # Type alias for a complex type
   PositionData = Tuple[float, float, float]

   # TypedDict for structured dictionaries
   class GrblStatus(TypedDict):
       status: str
       position: PositionData
   ```

7. Ensure type hints align with docstring type documentation

### Examples

Function with type hints:
```python
def get_position(self) -> tuple[length_mm, length_mm, deg]:
    """Get the current XYZ position of the CNC machine by querying GRBL controller.

    Returns
    -------
    length_mm
        Current X-axis position in millimeters
    length_mm
        Current Y-axis position in millimeters
    deg
        Current Z-axis position in degrees

    Raises
    ------
    RuntimeError
        If unable to parse position data from the GRBL response
    serial.SerialException
        If communication with the serial port fails
    """
    # Implementation...
```

Class with type hints:
```python
class CNC(AbstractCNC):
    port: str
    baud_rate: int
    x_lims: tuple[float, float]
    y_lims: tuple[float, float]
    z_lims: tuple[float, float]
    serial_port: Optional[serial.Serial]
    invert_x: bool
    invert_y: bool
    invert_z: bool
    grbl_settings: Optional[dict[str, Union[int, float]]]

    def __init__(self, port: str = "/dev/ttyUSB0", baud_rate: int = 115200) -> None:
        # Implementation...
```

## Code Style

1. Follow PEP 8 guidelines for code formatting
2. Use 4 spaces for indentation (no tabs)
4. Use meaningful variable and function names
5. Use docstrings for all public modules, classes, and functions
6. Include type hints for all function parameters and return values
7. Use constants for magic numbers and strings
8. Handle exceptions appropriately with specific exception types
9. Write unit tests for all functionality

## Examples

All examples in docstrings should:
1. Include necessary imports at the beginning
2. Be clear and runnable
3. Use concise inline explanations to separate multiple examples
4. Include expected output comments where applicable
5. Be verified by running them in a Python terminal

Example:
```python
"""
Examples
--------
>>> from plantimager.controller.scanner.grbl import CNC
>>> cnc = CNC("/dev/ttyUSB0")  # Connect to GRBL controller
>>> cnc.home()  # Perform a homing sequence
>>> cnc.moveto(100, 100, 45)  # Move to position (100mm, 100mm, 45°)
>>> x, y, z = cnc.get_position()  # Get the current position
>>> print(f"Current position: X={x}mm, Y={y}mm, Z={z}°")
Current position: X=100.0mm, Y=100.0mm, Z=45.0°

# Example of asynchronous movement
>>> cnc.moveto_async(200, 200, 90)  # Start asynchronous movement
>>> status = cnc.get_status()
>>> print(status['status'])  # Machine should be in 'Run' state
Run
>>> cnc.wait()  # Wait for movement completion
>>> status = cnc.get_status()
>>> print(status['status'])  # Machine should now be 'Idle'
Idle
"""
```
