#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Path Generation for Plant Imaging Systems.

This module provides classes and functions for generating and manipulating 3D paths
for plant imaging systems. It includes implementations for various path types such as
circles, cylinders, and lines, as well as utilities for path manipulation.

Key Features:
- Abstract representation of camera poses in 5D space (x, y, z, pan, tilt)
- Path generation for common scanning patterns (circles, cylinders, lines)
- Path manipulation and combination utilities
- Support for calibration paths
- Precise control over camera orientation at each path point

Usage Examples:
```python
>>> from plantimager.controller.scanner.path import Circle, Pose
>>> # Create a circular path with 10 points
>>> center_x, center_y = 200, 200  # Center coordinates in mm
>>> radius = 100  # Circle radius in mm
>>> n_points = 10  # Number of points in the circle
>>> circular_path = Circle(center_x, center_y, radius, n_points)
>>> # Access the first point in the path
>>> first_point = circular_path[0]
>>> print(f"First point: x={first_point.x}, y={first_point.y}, z={first_point.z}")
First point: x=100.0, y=200.0, z=0

```
"""

import math
from collections.abc import Iterable

import numpy as np

from .units import deg
from .units import length_mm


class Pose(object):
    """Abstract representation of a 'camera pose' as its 5D coordinates.

    Examples
    --------
    >>> from plantimager.controller.scanner.path import Pose
    >>> p = Pose(50, 250, 80, 270, 0)
    >>> print(p)
    x: 50, y: 250, z: 80, pan: 270, tilt: 0
    """

    def __init__(self, x: length_mm = 0., y: length_mm = 0., z: length_mm = 0.,
                 pan: deg = 0., tilt: deg = 0.):
        """Pose constructor.

        Parameters
        ----------
        x : length_mm, optional
            Relative distance to the origin along the x-axis.
        y : length_mm, optional
            Relative distance to the origin along the y-axis.
        z : length_mm, optional
            Relative distance to the origin along the z-axis.
        pan : deg, optional
            Relative rotation to the origin along the xy-plane.
        tilt : deg, optional
            Relative rotation to the origin orthogonal to the xy-plane.
        """
        self.x = x
        self.y = y
        self.z = z
        self.pan = pan
        self.tilt = tilt

    def __repr__(self):
        return ", ".join(f"{k}: {v}" for k, v in self.__dict__.items())

    def attributes(self) -> list[str]:
        return ["x", "y", "z", "pan", "tilt"]

    def __add__(self, other: "Pose") -> "Pose":
        return Pose(self.x + other.x, self.y + other.y, self.z + other.z, self.pan + other.pan, self.tilt + other.tilt)


class PathElement(Pose):
    """Singleton for a `Path` class.

    Examples
    --------
    >>> from plantimager.controller.scanner.path import PathElement
    >>> elt = PathElement(50, 250, 80, 270, 0, True)
    >>> print(elt)
    x: 50, y: 250, z: 80, pan: 270, tilt: 0, exact_pose: True

    """

    def __init__(self, x: length_mm | None = None, y: length_mm | None = None,
                 z: length_mm | None = None, pan: deg | None = None, tilt: deg | None = None,
                 exact_pose: bool = True):
        """
        Parameters
        ----------
        x : length_mm, optional
            Relative distance, in millimeters, to the origin along the x-axis.
        y : length_mm, optional
            Relative distance, in millimeters, to the origin along the y-axis.
        z : length_mm, optional
            Relative distance, in millimeters, to the origin along the z-axis.
        pan : deg, optional
            Relative rotation, in degrees, to the origin along the xy-plane.
        tilt : deg, optional
            Relative rotation, in degrees, to the origin orthogonal to the xy-plane.
        exact_pose : bool, optional
            If ``True``, the above parameter values are exact, else they are approximations.

        """
        super().__init__(x, y, z, pan, tilt)
        self.exact_pose = exact_pose

    def __repr__(self):
        return ", ".join(f"{k}: {v}" for k, v in self.__dict__.items())


class Path(list):
    """A path is a list of ``PathElement`` instances.

    Examples
    --------
    >>> from plantimager.controller.scanner.path import PathElement
    >>> elt = PathElement(0, 0, 0, 0, 0, True)
    >>> from plantimager.controller.scanner.path import Path
    >>> p = Path()
    >>> type(p)
    <class 'plantimager.controller.scanner.path.Path'>
    >>> p.append(elt)
    >>> p2 = Path()
    >>> p2.append(elt)
    >>> p == p2
    True
    >>> p != p2
    False

    """

    def __init__(self):
        super().__init__()


def circle(center_x: length_mm, center_y: length_mm, radius: length_mm,
           n_points: int) -> tuple[list[length_mm], list[length_mm], list[deg]]:
    """Create a 2D circle of N points with given center and radius.

    Pan orientations are also computed to always face the center of the circle.

    Parameters
    ----------
    center_x : length_mm
        Relative position of the circle center along the X-axis.
    center_y : length_mm
        Relative position of the circle center along the Y-axis.
    radius : length_mm
        Radius of the circle to create.
    n_points : int
        Number of points used to create the circle.

    Returns
    -------
    list of length_mm
        Sequence of x positions.
    list of length_mm
        Sequence of y positions.
    list of deg
        Sequence of pan orientations.

    Examples
    --------
    >>> from plantimager.controller.scanner.path import circle
    >>> circle(10, 10, 5, 3)
    ([5.0, 12.5, 12.500000000000002], [10.0, 5.669872981077806, 14.330127018922191], [0.0, 119.99999999999999, 239.99999999999997])

    """
    x, y, p = [], [], []
    for i in range(n_points):
        pan = 2 * i * math.pi / n_points
        x.append(center_x - radius * math.cos(pan))
        y.append(center_y - radius * math.sin(pan))
        pan = pan * 180 / math.pi
        p.append(pan % 360)

    return x, y, p


class Circle(Path):
    """Creates a circular path for the scanner.

    Compute the `x`, `y` & `pan` ``PathElement`` values to create that circle.

    Notes
    -----
    The `pan` is computed to always face the center of the circle.

    The `z` and `tilt` ``PathElement`` values are hard-coded to ``0.`` here;
    the offset to these values is provided by each camera configuration at scan time.

    Examples
    --------
    >>> from plantimager.controller.scanner.path import Circle
    >>> circular_path = Circle(200, 200, 50, 9)
    >>> for pose in circular_path: print(pose)
    x: 150.0, y: 200.0, z: 0, pan: 0.0, tilt: 0, exact_pose: False
    x: 161.6977778440511, y: 167.86061951567302, z: 0, pan: 40.0, tilt: 0, exact_pose: False
    x: 191.3175911166535, y: 150.7596123493896, z: 0, pan: 80.0, tilt: 0, exact_pose: False
    x: 225.0, y: 156.69872981077805, z: 0, pan: 119.99999999999999, tilt: 0, exact_pose: False
    x: 246.9846310392954, y: 182.89899283371656, z: 0, pan: 160.0, tilt: 0, exact_pose: False
    x: 246.98463103929544, y: 217.10100716628344, z: 0, pan: 200.0, tilt: 0, exact_pose: False
    x: 225.00000000000003, y: 243.30127018922192, z: 0, pan: 239.99999999999997, tilt: 0, exact_pose: False
    x: 191.3175911166535, y: 249.24038765061042, z: 0, pan: 280.0, tilt: 0, exact_pose: False
    x: 161.6977778440511, y: 232.13938048432698, z: 0, pan: 320.0, tilt: 0, exact_pose: False
    """

    def __init__(self, center_x: length_mm, center_y: length_mm, radius: length_mm,
                 n_points: int, **kwargs):
        """
        Parameters
        ----------
        center_x : length_mm
            X-axis position, in millimeters, of the circle's center, relative to the origin.
        center_y : length_mm
            Y-axis position, in millimeters, of the circle's center, relative to the origin.
        radius : length_mm
            Radius, in millimeters, of the circular path to create.
        n_points : int
            Number of points (``PathElement``) used to generate the circular path.
        """
        super().__init__()
        x, y, pan = circle(center_x, center_y, radius, n_points)

        self.center_x = center_x
        self.center_y = center_y
        self.radius = radius
        self.n_points = n_points

        for i in range(n_points):
            self.append(PathElement(x[i], y[i], 0, pan[i], 0, exact_pose=False))


def line1d(start: length_mm, stop: length_mm, n_points: int) -> list[length_mm]:
    """Create a 1D line of N points between start and stop position (included).

    Parameters
    ----------
    start : length_mm
        Line starting position, in millimeters.
    stop : length_mm
        Line ending position, in millimeters.
    n_points : int
        Number of points used to create the line of points.

    Returns
    -------
    list of length_mm
        Sequence of 1D positions.

    Examples
    --------
    >>> from plantimager.controller.scanner.path import line1d
    >>> line1d(0, 10, 5)
    [0.0, 2.5, 5.0, 7.5, 10.0]

    """
    return [(1 - i / (n_points - 1)) * start + (i / (n_points - 1)) * stop for i in range(n_points)]


def line3d(x_0: length_mm, y_0: length_mm, z_0: length_mm,
           x_1: length_mm, y_1: length_mm, z_1: length_mm,
           n_points: int) -> tuple[list[length_mm], list[length_mm], list[length_mm]]:
    """Create a 3D line of N points between start and stop position (included).

    Parameters
    ----------
    x_0 : length_mm
        Line starting position, in millimeters, for the x-axis.
    y_0 : length_mm
        Line starting position, in millimeters, for the y-axis.
    z_0 : length_mm
        Line starting position, in millimeters, for the z-axis.
    x_1 : length_mm
        Line ending position, in millimeters, for the x-axis.
    y_1 : length_mm
        Line ending position, in millimeters, for the y-axis.
    z_1 : length_mm
        Line ending position, in millimeters, for the z-axis.
    n_points : int
        Number of points used to create the linear path.

    Returns
    -------
    list of length_mm
        Sequence of x positions.
    list of length_mm
        Sequence of y positions.
    list of length_mm
        Sequence of z positions.

    Examples
    --------
    >>> from plantimager.controller.scanner.path import line3d
    >>> line3d(0, 0, 0, 10, 10, 10, 5)
    ([0.0, 2.5, 5.0, 7.5, 10.0], [0.0, 2.5, 5.0, 7.5, 10.0], [0.0, 2.5, 5.0, 7.5, 10.0])

    """
    return line1d(x_0, x_1, n_points), line1d(y_0, y_1, n_points), line1d(z_0, z_1, n_points)


class Line(Path):
    """Creates a linear path for the scanner.

    Examples
    --------
    >>> from plantimager.controller.scanner.path import Line
    >>> n_points = 2
    >>> linear_path = Line(0, 0, 0, 10, 10, 0, 180, 0, n_points)
    >>> linear_path
    [x: 0.0, y: 0.0, z: 0.0, pan: 180, tilt: 0, exact_pose: True, x: 10.0, y: 10.0, z: 0.0, pan: 180, tilt: 0, exact_pose: True]

    """

    def __init__(self, x_0: length_mm, y_0: length_mm, z_0: length_mm,
                 x_1: length_mm, y_1: length_mm, z_1: length_mm,
                 pan: deg, tilt: deg | Iterable[deg], n_points: int):
        """
        Parameters
        ----------
        x_0 : length_mm
            Line starting position, in millimeters for the x-axis.
        y_0 : length_mm
            Line starting position, in millimeters for the y-axis.
        z_0 : length_mm
            Line starting position, in millimeters for the z-axis.
        x_1 : length_mm
            Line ending position, in millimeters for the x-axis.
        y_1 : length_mm
            Line ending position, in millimeters for the y-axis.
        z_1 : length_mm
            Line ending position, in millimeters for the z-axis.
        pan : deg
            Camera pan value, in degrees, to use for the linear path.
        tilt : deg or list(deg)
            Camera tilt(s), in degrees, to use for this line.
            If an iterable is given, performs more than one camera acquisition at same xyz position.
        n_points : int
            Number of points used to create the linear path.
        """
        super().__init__()
        try:
            assert n_points >= 2
        except AssertionError:
            raise ValueError("You need a minimum of two points to make a line!")

        if not isinstance(tilt, Iterable):
            tilt = [tilt]

        x, y, z = line3d(x_0, y_0, z_0, x_1, y_1, z_1, n_points)
        for i in range(n_points):
            for t in tilt:
                self.append(PathElement(x[i], y[i], z[i], pan, t, exact_pose=True))


class CalibrationPath(Path):
    """Creates a calibration path for the scanner.

    This build two lines spanning the X & Y axes extent of the given path.

    Notes
    -----
    The calibration path is made of the path to calibrate, plus two linear paths, X & Y, in that order.

    Takes the first ``PathElement`` of the input path to calibrate as lines starting points

    Takes the max distance to input path origin along x & y axes to create X & Y lines ending points.
    Let x0, y0 & z0 be the first `ElementPath` xyz position, then:
     - line #1: (x0, y0, z0, max_dist(xi, x0), y0, z0)
     - line #2: (x0, y0, z0, x0, max_dist(yi, y0), z0)

    See Also
    --------
    romiscan.tasks.colmap.use_calibrated_poses

    Examples
    --------
    >>> from plantimager.controller.scanner.path import CalibrationPath
    >>> from plantimager.controller.scanner.path import Circle
    >>> circular_path = Circle(200, 200, 50, 9)
    >>> n_points_line = 5
    >>> calib_path = CalibrationPath(circular_path, n_points_line)
    >>> for pose in calib_path: print(pose)
    x: 150.0, y: 200.0, z: 0, pan: 0.0, tilt: 0, exact_pose: False
    x: 161.6977778440511, y: 167.86061951567302, z: 0, pan: 40.0, tilt: 0, exact_pose: False
    x: 191.3175911166535, y: 150.7596123493896, z: 0, pan: 80.0, tilt: 0, exact_pose: False
    x: 225.0, y: 156.69872981077805, z: 0, pan: 119.99999999999999, tilt: 0, exact_pose: False
    x: 246.9846310392954, y: 182.89899283371656, z: 0, pan: 160.0, tilt: 0, exact_pose: False
    x: 246.98463103929544, y: 217.10100716628344, z: 0, pan: 200.0, tilt: 0, exact_pose: False
    x: 225.00000000000003, y: 243.30127018922192, z: 0, pan: 239.99999999999997, tilt: 0, exact_pose: False
    x: 191.3175911166535, y: 249.24038765061042, z: 0, pan: 280.0, tilt: 0, exact_pose: False
    x: 161.6977778440511, y: 232.13938048432698, z: 0, pan: 320.0, tilt: 0, exact_pose: False
    x: 150.0, y: 200.0, z: 0.0, pan: 0.0, tilt: 0, exact_pose: True
    x: 143.25, y: 200.0, z: 0.0, pan: 0.0, tilt: 0, exact_pose: True
    x: 136.5, y: 200.0, z: 0.0, pan: 0.0, tilt: 0, exact_pose: True
    x: 129.75, y: 200.0, z: 0.0, pan: 0.0, tilt: 0, exact_pose: True
    x: 123.0, y: 200.0, z: 0.0, pan: 0.0, tilt: 0, exact_pose: True
    x: 150.0, y: 200.0, z: 0.0, pan: 0.0, tilt: 0, exact_pose: True
    x: 150.0, y: 212.3100969126526, z: 0.0, pan: 0.0, tilt: 0, exact_pose: True
    x: 150.0, y: 224.6201938253052, z: 0.0, pan: 0.0, tilt: 0, exact_pose: True
    x: 150.0, y: 236.93029073795782, z: 0.0, pan: 0.0, tilt: 0, exact_pose: True
    x: 150.0, y: 249.24038765061042, z: 0.0, pan: 0.0, tilt: 0, exact_pose: True
    """

    def __init__(self, path: Path, n_points_line: int):
        """
        Parameters
        ----------
        path : Path
            A path to calibrate.
        n_points_line : int
            The number of points per line.
        """
        super().__init__()
        el0 = path[0]
        # # TODO: find a better "algo" than this to select y-limit for line #1 and x-limit for line #2
        # el1 = path[len(path) // 4 - 1]
        # self.extend(Line(el0.x, el0.y, el0.z, el0.x, el1.y, el0.z, el0.pan, el0.tilt, n_points_line))
        # self.extend(Line(el0.x, el0.y, el0.z, el1.x, el0.y, el0.z, el0.pan, el0.tilt, n_points_line))
        # - Start with the path to calibrate
        self.extend(path)
        # x-axis line, from the first `ElementPath` xyz position to the most distant point from the origin along this x-axis
        x_max = path[np.argmax([pelt.x - el0.x for pelt in path])].x
        # y-axis line, from the first `ElementPath` xyz position to the most distant point from the origin along this y-axis
        y_max = path[np.argmax([pelt.y - el0.y for pelt in path])].y
        self.extend(Line(el0.x, el0.y, el0.z, x_max // 2, el0.y, el0.z, el0.pan, el0.tilt, n_points_line))
        self.extend(Line(el0.x, el0.y, el0.z, el0.x, y_max, el0.z, el0.pan, el0.tilt, n_points_line))


class CalibrationPath2(Path):
    """Creates a calibration path for the scanner.

    This path is meant to take images of a calibration pattern putting this pattern in various positions in the images.

    """

    def __init__(self, center_x: length_mm, center_y: length_mm, radius: length_mm, z: length_mm, tilt: length_mm,
                 n_points_line: int):
        """
        # TODO: remake later, target too much on the side or not visible
        """
        super().__init__()
        self.center_x = center_x
        self.center_y = center_y
        self.radius = radius
        x0, xn = center_x - radius, center_x + radius
        y0, yn = center_y - radius, center_y + radius
        self.extend(Line(x0, y0, z, x0, yn, z, 0., tilt, n_points_line))
        self.extend(Line(x0, yn, z, center_x, yn, z, 0., tilt, n_points_line // 2))
        self.extend(Line(center_x, yn, z, x0, center_y, z, -45, tilt, n_points_line // 2))
        for pan in np.arange(-30, 30, n_points_line // 2):
            self.append(Pose(x0, center_y, z, pan, tilt))


class CustomPath(Path):
    """Creates a custom path for the scanner."""

    def __init__(self, waypoints: list[list[float]], scheme: tuple[str, ...] = ("x", "y", "z", "pan", "tilt")):
        """
        Initialize a Path object with given waypoints and a scheme.

        This constructor creates a list of `Pose` objects by mapping the provided
        waypoints to the specified scheme. It ensures that each waypoint matches the
        length of the scheme and appends the resulting `Pose` objects to the path.

        Parameters
        ----------
        waypoints : list of list of float
            A list containing waypoints, where each waypoint is a list of floats
            representing positional and orientational values.
        scheme : tuple of str, optional
            A tuple of strings specifying the names of the coordinates or attributes
            in the waypoints. The length of the scheme must match the length of each
            waypoint. By default, it is `("x", "y", "z", "pan", "tilt")`.

        Raises
        ------
        AssertionError
            If any of the waypoints do not match the length of the provided scheme.

        Notes
        -----
        Each `waypoint` is converted into a dictionary by zipping the `scheme` with
        the waypoint values, and then passed as keyword arguments to the `Pose` class
        constructor. It is essential that the `scheme` matches the keys expected by
        the `Pose` class.

        Examples
        --------
        >>> from plantimager.controller.scanner.path import CustomPath
        >>> waypoints = [[25, 375, 0], [25, 475, 90], [125, 375, 180], [125, 475, 270]]
        >>> custom_path = CustomPath(waypoints, scheme=("x", "y", "pan"))
        >>> for pose in custom_path: print(pose)
        x: 25, y: 375, z: 0.0, pan: 0, tilt: 0.0
        x: 25, y: 475, z: 0.0, pan: 90, tilt: 0.0
        x: 125, y: 375, z: 0.0, pan: 180, tilt: 0.0
        x: 125, y: 475, z: 0.0, pan: 270, tilt: 0.0
        """
        super().__init__()

        for waypoint in waypoints:
            assert len(waypoint) == len(scheme)
            kwargs = dict(zip(scheme, waypoint))
            self.append(Pose(**kwargs))
