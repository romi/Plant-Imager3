"""Unit tests for the scanner HAL data structures.

These tests verify the data containers in
:mod:`plantimager.controller.scanner.hal` — ``ChannelData``, ``DataItem``,
and the ``AbstractCNC`` base class. The design checks field storage,
``format_id`` output, memoryview handling, and that the abstract base class
cannot be instantiated without a concrete implementation.
"""

import unittest
import numpy as np
from plantimager.controller.scanner.hal import AbstractCNC, ChannelData, DataItem


class TestChannelData(unittest.TestCase):
    """Tests for the ChannelData container."""

    def test_format_id(self):
        """format_id zero-pads the index and joins it with the channel name."""
        cd = ChannelData("mychan", np.zeros((2, 2)), idx=42)
        self.assertEqual(cd.format_id(), "00042_mychan")

    def test_fields(self):
        """ChannelData stores the name, index, and data array."""
        arr = np.ones((3, 3))
        cd = ChannelData("chan", arr, idx=1)
        self.assertEqual(cd.name, "chan")
        self.assertEqual(cd.idx, 1)
        np.testing.assert_array_equal(cd.data, arr)


class TestDataItem(unittest.TestCase):
    """Tests for the DataItem container."""

    def test_fields(self):
        """DataItem stores the index, image bytes, extension, and metadata."""
        img = b"fakejpeg"
        meta = {"camera_name": "cam1", "shot_id": 0}
        di = DataItem(idx=5, image=img, image_ext="jpeg", metadata=meta)
        self.assertEqual(di.idx, 5)
        self.assertEqual(di.image, img)
        self.assertEqual(di.image_ext, "jpeg")
        self.assertEqual(di.metadata, meta)

    def test_memoryview(self):
        """DataItem preserves a memoryview image as-is."""
        mv = memoryview(b"abc")
        di = DataItem(0, mv, "jpeg")
        self.assertIsInstance(di.image, memoryview)


class TestAbstractCNC(unittest.TestCase):
    """Tests for the AbstractCNC abstract base class."""

    def test_cannot_instantiate(self):
        """AbstractCNC cannot be instantiated directly."""
        with self.assertRaises(TypeError):
            AbstractCNC()

    def test_subclass_must_implement(self):
        """A subclass that omits abstract methods cannot be instantiated."""
        class Incomplete(AbstractCNC):
            pass

        with self.assertRaises(TypeError):
            Incomplete()


if __name__ == "__main__":
    unittest.main()
