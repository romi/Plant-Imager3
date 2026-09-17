"""Unit tests for the scanner unit type aliases.

These tests verify the unit aliases in :mod:`plantimager.controller.scanner.units`
(``deg``, ``rad``, ``length_mm``, ``time_s``). They are ``typing.Annotated[float, ...]``
aliases — not ``NewType`` identity functions — so the design confirms annotation
metadata is preserved, importability, and that plain floats remain valid at runtime.
"""

import typing
import unittest
from plantimager.controller.scanner import units


class TestUnits(unittest.TestCase):
    """Tests for the scanner unit type aliases (Annotated)."""

    def test_units_are_annotated(self):
        """Each alias is Annotated[float, description]."""
        for name in ("deg", "rad", "length_mm", "time_s"):
            with self.subTest(name=name):
                alias = getattr(units, name)
                self.assertIs(typing.get_origin(alias), typing.Annotated)
                args = typing.get_args(alias)
                self.assertEqual(args[0], float)
                self.assertIsInstance(args[1], str)
                self.assertTrue(len(args[1]) > 0)

    def test_units_metadata_content(self):
        """Annotated metadata carries the unit description."""
        self.assertIn("degrees", typing.get_args(units.deg)[1].lower())
        self.assertIn("millimeters", typing.get_args(units.length_mm)[1].lower())
        self.assertIn("seconds", typing.get_args(units.time_s)[1].lower())

    def test_plain_float_usable_where_annotated_expected(self):
        """Plain floats are assignable where Annotated[float] is annotated."""
        def takes_deg(x: units.deg) -> float:
            return x

        self.assertEqual(takes_deg(5.0), 5.0)
        self.assertEqual(takes_deg(1), 1)
        self.assertIsInstance(takes_deg(1.0), float)

    def test_units_importable(self):
        """All expected unit aliases are importable from the module."""
        self.assertTrue(hasattr(units, "deg"))
        self.assertTrue(hasattr(units, "rad"))
        self.assertTrue(hasattr(units, "length_mm"))
        self.assertTrue(hasattr(units, "time_s"))
        # velocity aliases were removed
        self.assertFalse(hasattr(units, "velocity_mm_p_s"))
        self.assertFalse(hasattr(units, "velocity_deg_p_s"))


if __name__ == "__main__":
    unittest.main()
