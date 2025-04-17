#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Unit Type Definitions for Plant Imaging Systems.

This module provides strongly typed unit definitions for physical quantities used in the
plant imaging system, enabling better type checking and preventing unit conversion errors.

Key Features:
- Type-safe unit definitions for physical quantities
- Clear distinction between different units of measurement
- Support for static type checking with mypy
- Improved code readability and maintainability
"""

from typing import NewType

# Angular units
#: Angle in degrees.
deg = NewType("deg", float)
#: Angle in radians.
rad = NewType("rad", float)

# Distance units
#: Length in millimeters.
length_mm = NewType("length_mm", float)

# Velocity units
#: Velocity in millimeters per second.
velocity_mm_p_s = NewType("velocity_mm_p_s", float)

# Time units
#: Time in seconds.
time_s = NewType("time_s", float)
