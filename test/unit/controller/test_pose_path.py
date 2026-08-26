import math
import unittest
from plantimager.controller.scanner.path import Path, PathElement, Pose, circle, line1d, line3d


class TestPose(unittest.TestCase):
    def test_pose_add(self):
        a = Pose(1, 2, 3, 10, 20)
        b = Pose(5, 5, 5, 30, 40)
        c = a + b
        self.assertEqual(c.x, 6)
        self.assertEqual(c.y, 7)
        self.assertEqual(c.z, 8)
        self.assertEqual(c.pan, 40)
        self.assertEqual(c.tilt, 60)

    def test_pose_repr(self):
        p = Pose(1, 2, 3, 4, 5)
        r = repr(p)
        self.assertIn("x: 1", r)
        self.assertIn("pan: 4", r)

    def test_pose_attributes(self):
        p = Pose()
        self.assertEqual(p.attributes(), ["x", "y", "z", "pan", "tilt"])

    def test_pathelement_default(self):
        e = PathElement(1, 2, 3, 4, 5)
        self.assertTrue(e.exact_pose)
        e2 = PathElement(1, 2, 3, 4, 5, exact_pose=False)
        self.assertFalse(e2.exact_pose)


class TestCircleHelper(unittest.TestCase):
    def test_circle_three_points(self):
        x, y, p = circle(10, 10, 5, 3)
        self.assertAlmostEqual(x[0], 5.0)
        self.assertAlmostEqual(y[0], 10.0)
        self.assertAlmostEqual(p[0], 0.0)
        self.assertAlmostEqual(p[1], 120.0, places=5)
        self.assertAlmostEqual(p[2], 240.0, places=5)

    def test_circle_pan_wraps(self):
        _, _, p = circle(0, 0, 10, 4)
        for pan in p:
            self.assertGreaterEqual(pan, 0)
            self.assertLess(pan, 360)

    def test_circle_subtests(self):
        for n in [3, 9, 36]:
            with self.subTest(n=n):
                x, y, p = circle(200, 200, 100, n)
                self.assertEqual(len(x), n)
                self.assertEqual(len(y), n)
                self.assertEqual(len(p), n)


class TestLineHelpers(unittest.TestCase):
    def test_line1d(self):
        self.assertEqual(line1d(0, 10, 5), [0.0, 2.5, 5.0, 7.5, 10.0])

    def test_line1d_two_points(self):
        self.assertEqual(line1d(5, 15, 2), [5.0, 15.0])

    def test_line1d_n1_raises(self):
        with self.assertRaises(ZeroDivisionError):
            line1d(0, 10, 1)

    def test_line3d(self):
        x, y, z = line3d(0, 0, 0, 10, 10, 10, 5)
        self.assertEqual(x, [0.0, 2.5, 5.0, 7.5, 10.0])
        self.assertEqual(y, [0.0, 2.5, 5.0, 7.5, 10.0])
        self.assertEqual(z, [0.0, 2.5, 5.0, 7.5, 10.0])

    def test_line3d_delegates(self):
        x0, y0, z0 = line3d(1, 2, 3, 4, 5, 6, 3)
        # first and last should match start/stop
        self.assertAlmostEqual(x0[0], 1)
        self.assertAlmostEqual(x0[-1], 4)


class TestPath(unittest.TestCase):
    def test_path_is_list(self):
        p = Path()
        e = PathElement(0, 0, 0, 0, 0)
        p.append(e)
        self.assertEqual(len(p), 1)
        self.assertIsInstance(p, list)


if __name__ == "__main__":
    unittest.main()
