import unittest
import numpy as np
from plantimager.controller.scanner.hal import AbstractCNC, ChannelData, DataItem


class TestChannelData(unittest.TestCase):
    def test_format_id(self):
        cd = ChannelData("mychan", np.zeros((2, 2)), idx=42)
        self.assertEqual(cd.format_id(), "00042_mychan")

    def test_fields(self):
        arr = np.ones((3, 3))
        cd = ChannelData("chan", arr, idx=1)
        self.assertEqual(cd.name, "chan")
        self.assertEqual(cd.idx, 1)
        np.testing.assert_array_equal(cd.data, arr)


class TestDataItem(unittest.TestCase):
    def test_fields(self):
        img = b"fakejpeg"
        meta = {"camera_name": "cam1", "shot_id": 0}
        di = DataItem(idx=5, image=img, image_ext="jpeg", metadata=meta)
        self.assertEqual(di.idx, 5)
        self.assertEqual(di.image, img)
        self.assertEqual(di.image_ext, "jpeg")
        self.assertEqual(di.metadata, meta)

    def test_memoryview(self):
        mv = memoryview(b"abc")
        di = DataItem(0, mv, "jpeg")
        self.assertIsInstance(di.image, memoryview)


class TestAbstractCNC(unittest.TestCase):
    def test_cannot_instantiate(self):
        with self.assertRaises(TypeError):
            AbstractCNC()

    def test_subclass_must_implement(self):
        class Incomplete(AbstractCNC):
            pass

        with self.assertRaises(TypeError):
            Incomplete()


if __name__ == "__main__":
    unittest.main()
