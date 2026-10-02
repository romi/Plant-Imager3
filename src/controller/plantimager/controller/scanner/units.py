#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
# Unit Type Definitions for Plant Imaging Systems.

Type aliases carrying unit information for the physical quantities used by the
plant imaging system. They are defined with ``typing.Annotated[float, ...]`` so
that, for type checkers, they behave exactly as ``float`` — plain ``float``
values are accepted anywhere these types are used — while the unit is preserved
as annotation metadata for documentation and static analysis.

## Key Features

- Unit semantics expressed as annotation metadata (``Annotated[float, ...]``)
- No runtime cost: values are plain ``float``, no conversion or wrapping
- Clear distinction between different units of measurement at type-check time
- Compatible with static type checking (mypy)

## Usage Examples

Unit types are interchangeable with plain floats for type checkers:

```python
>>> from plantimager.controller.scanner.units import length_mm, deg
>>> length_mm
typing.Annotated[float, 'Length in millimeters']
>>> deg
typing.Annotated[float, 'Angle in degrees']
```
"""

from typing import Annotated

#: Angle in degrees.
deg = Annotated[float, "Angle in degrees"]
#: Angle in radians.
rad = Annotated[float, "Angle in radians"]
#: Length in millimeters.
length_mm = Annotated[float, "Length in millimeters"]
#: Time in seconds.
time_s = Annotated[float, "Time in seconds"]
