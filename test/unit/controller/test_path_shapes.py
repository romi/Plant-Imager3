"""Unit tests for the scan path shape generators.

These tests verify the concrete path classes in
:mod:`plantimager.controller.scanner.path` — ``Circle``, ``Cylinder``,
``Line``, ``CalibrationPath``, and ``CustomPath``. The design checks each
shape's length, coordinate layout, tilt handling (single value vs. iterable
that duplicates points), and error conditions, so the generated pose
sequences are correct before they are fed to the scanner.
"""

import unittest
import numpy as np
from plantimager.controller.scanner.path import (
    CalibrationPath,
    Circle,
    CustomPath,
    Cylinder,
    Line,
    Path,
)


class TestCircle(unittest.TestCase):
    """Tests for the Circle path shape."""

    def test_circle_basic(self):
        """A circle generates the requested number of points."""
        c = Circle(200, 200, 50, 0, 200, 9)
        self.assertEqual(len(c), 9)
        self.assertEqual(c.center_x, 200)
        self.assertEqual(c.radius, 200)
        self.assertFalse(c[0].exact_pose)

    def test_circle_tilt_iterable_dup(self):
        """An iterable tilt duplicates each point once per tilt value."""
        c = Circle(200, 200, 50, (0, 10), 200, 9)
        self.assertEqual(len(c), 18)
        # each position duplicated with tilt 0 then 10
        self.assertEqual(c[0].tilt, 0)
        self.assertEqual(c[1].tilt, 10)
        self.assertAlmostEqual(c[0].x, c[1].x)
        self.assertAlmostEqual(c[0].y, c[1].y)

    def test_circle_single_tilt(self):
        """A single tilt value applies to every point."""
        c = Circle(0, 0, 0, 5, 10, 4)
        self.assertEqual(len(c), 4)
        for e in c:
            self.assertEqual(e.tilt, 5)


class TestCylinder(unittest.TestCase):
    """Tests for the Cylinder path shape."""

    def test_cylinder_two_circles(self):
        """A two-circle cylinder stacks circles at each z level."""
        cyl = Cylinder(200, 200, (0, 50), 0, 200, 9, n_circles=2)
        self.assertEqual(len(cyl), 18)
        # first circle z=0, second z=50
        self.assertEqual(cyl[0].z, 0)
        self.assertEqual(cyl[9].z, 50)

    def test_cylinder_valueerror(self):
        """A single-circle cylinder raises ValueError."""
        with self.assertRaises(ValueError):
            Cylinder(200, 200, (0, 50), 0, 200, 9, n_circles=1)

    def test_cylinder_three_circles_step(self):
        """Three circles are spaced evenly across the z range."""
        cyl = Cylinder(0, 0, (0, 10), 0, 10, 4, n_circles=3)
        # range(0, 11, int(10/2)=5) -> 0,5,10
        zs = sorted(set(e.z for e in cyl))
        self.assertEqual(zs, [0, 5, 10])

    def test_cylinder_default_n_circles(self):
        """The default circle count produces the expected number of points."""
        cyl = Cylinder(0, 0, (0, 10), 0, 10, 4)
        self.assertEqual(len(cyl), 8)


class TestLine(unittest.TestCase):
    """Tests for the Line path shape."""

    def test_line_basic(self):
        """A line generates the requested number of exact-pose points."""
        line = Line(0, 0, 0, 10, 10, 10, 180, 0, 2)
        self.assertEqual(len(line), 2)
        self.assertTrue(line[0].exact_pose)
        self.assertEqual(line[0].x, 0)
        self.assertEqual(line[1].x, 10)

    def test_line_tilt_dup(self):
        """An iterable tilt duplicates each line point per tilt value."""
        line = Line(0, 0, 0, 10, 0, 0, 0, (0, 10), 2)
        self.assertEqual(len(line), 4)
        self.assertEqual(line[0].tilt, 0)
        self.assertEqual(line[1].tilt, 10)

    def test_line_valueerror(self):
        """A line with too few points raises ValueError."""
        with self.assertRaises(ValueError):
            Line(0, 0, 0, 1, 1, 1, 0, 0, 1)


class TestCalibrationPath(unittest.TestCase):
    """Tests for the CalibrationPath wrapper."""

    def test_calibration_len(self):
        """CalibrationPath appends calibration lines to the base path."""
        circ = Circle(200, 200, 50, 0, 200, 9)
        cal = CalibrationPath(circ, 5)
        self.assertEqual(len(cal), len(circ) + 10)
        # first element should be circ[0]
        self.assertAlmostEqual(cal[0].x, circ[0].x)

    def test_calibration_contains_lines(self):
        """CalibrationPath includes x- and y-axis calibration lines."""
        circ = Circle(0, 0, 0, 0, 10, 4)
        cal = CalibrationPath(circ, 3)
        # after circ, next 3 are x-axis line, then 3 y-axis line
        self.assertEqual(len(cal), 4 + 6)


class TestCustomPath(unittest.TestCase):
    """Tests for the CustomPath shape."""

    def test_custom_basic(self):
        """Waypoints map to poses using the default coordinate scheme."""
        waypoints = [[1, 2, 3, 4, 5], [6, 7, 8, 9, 10]]
        path = CustomPath(waypoints)
        self.assertEqual(len(path), 2)
        self.assertEqual(path[0].x, 1)
        self.assertEqual(path[1].tilt, 10)

    def test_custom_scheme(self):
        """A custom scheme reorders how waypoint values map to coordinates."""
        waypoints = [[1, 2, 3]]
        path = CustomPath(waypoints, scheme=("z", "y", "x"))
        self.assertEqual(path[0].z, 1)
        self.assertEqual(path[0].x, 3)

    def test_custom_assert_mismatch(self):
        """A waypoint length that does not match the scheme raises AssertionError."""
        with self.assertRaises(AssertionError):
            CustomPath([[1, 2]], scheme=("x", "y", "z", "pan", "tilt"))


if __name__ == "__main__":
    unittest.main()
