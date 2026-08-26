import unittest
from plantimager.controller.scanner import units


class TestUnits(unittest.TestCase):
    def test_newtype_identity(self):
        # NewType is identity at runtime
        self.assertEqual(units.deg(5.0), 5.0)
        self.assertEqual(units.rad(3.14), 3.14)
        self.assertEqual(units.length_mm(100), 100)
        self.assertEqual(units.velocity_mm_p_s(10), 10)
        self.assertEqual(units.time_s(2.5), 2.5)

    def test_units_are_float(self):
        self.assertIsInstance(units.deg(1.0), float)
        self.assertIsInstance(units.length_mm(1.0), float)
        # NewType is identity: int stays int, float stays float
        self.assertEqual(units.deg(1), 1)
        self.assertEqual(units.deg(1.5), 1.5)

    def test_units_importable(self):
        self.assertTrue(hasattr(units, "deg"))
        self.assertTrue(hasattr(units, "rad"))
        self.assertTrue(hasattr(units, "length_mm"))
        self.assertTrue(hasattr(units, "velocity_deg_p_s"))
        self.assertTrue(hasattr(units, "time_s"))


if __name__ == "__main__":
    unittest.main()
