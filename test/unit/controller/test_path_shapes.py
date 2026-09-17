"""Unit tests for the scan path shape generators — PIv3 Circle API.

Verifies Circle (center_x, center_y, radius, n_points) with z/tilt hard-coded to 0,
Line, CalibrationPath and CustomPath. Cylinder was removed in PIv3.
"""

import unittest
import numpy as np
from plantimager.controller.scanner.path import (
    CalibrationPath,
    Circle,
    CustomPath,
    Line,
    Path,
)


class TestCircle(unittest.TestCase):
    """Tests for the Circle path shape (PIv3 API)."""

    def test_circle_basic(self):
        """A circle generates the requested number of points with z/tilt == 0."""
        c = Circle(200, 200, 200, 9)
        self.assertEqual(len(c), 9)
        self.assertEqual(c.center_x, 200)
        self.assertEqual(c.radius, 200)
        self.assertFalse(c[0].exact_pose)
        for e in c:
            self.assertEqual(e.z, 0)
            self.assertEqual(e.tilt, 0)

    def test_circle_single_tilt(self):
        """z/tilt are hard-coded to 0 regardless of legacy kwargs."""
        c = Circle(0, 0, 10, 4, z=50, tilt=5)
        self.assertEqual(len(c), 4)
        for e in c:
            self.assertEqual(e.z, 0)
            self.assertEqual(e.tilt, 0)

    def test_circle_attributes_preserved(self):
        """Stored center/radius/n_points match construction."""
        c = Circle(150, 250, 75, 12)
        self.assertEqual(c.center_x, 150)
        self.assertEqual(c.center_y, 250)
        self.assertEqual(c.radius, 75)
        self.assertEqual(c.n_points, 12)

    def test_circle_legacy_kwargs_ignored(self):
        """Legacy z/tilt kwargs via **kwargs are ignored, not error."""
        # should not raise
        c = Circle(200, 200, 200, 9, z=50, tilt=(0, 10))
        self.assertEqual(len(c), 9)


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
        circ = Circle(200, 200, 200, 9)
        cal = CalibrationPath(circ, 5)
        self.assertEqual(len(cal), len(circ) + 10)
        self.assertAlmostEqual(cal[0].x, circ[0].x)

    def test_calibration_contains_lines(self):
        """CalibrationPath includes x- and y-axis calibration lines."""
        circ = Circle(0, 0, 10, 4)
        cal = CalibrationPath(circ, 3)
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
