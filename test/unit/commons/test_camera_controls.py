"""Unit tests for the shared camera-control vocabulary."""

import unittest

from plantimager.commons.camera_controls import (
    AWB_MODES,
    COMMON_CONTROLS,
    awb_mode_name,
)
from plantimager.commons.cameradevice import Camera


class TestAwbModes(unittest.TestCase):
    def test_covers_full_libcamera_enum(self):
        self.assertEqual([v for v, _ in AWB_MODES], list(range(8)))

    def test_daylight_is_five_per_rig_docs(self):
        self.assertEqual(dict(AWB_MODES)[5], "Daylight")

    def test_name_lookup(self):
        self.assertEqual(awb_mode_name(0), "Auto")
        self.assertEqual(awb_mode_name(7), "Custom")

    def test_unknown_value_gives_placeholder(self):
        self.assertEqual(awb_mode_name(99), "?")


class TestCommonControls(unittest.TestCase):
    def test_v1_field_set(self):
        self.assertEqual(tuple(COMMON_CONTROLS),
                         ("ExposureTime", "AnalogueGain", "AwbEnable",
                          "AwbMode", "ColourGains"))


class TestCameraControlDefaults(unittest.TestCase):
    """The ABC documents the contract; servers must override it."""

    def test_ranges_endpoint_raises_by_default(self):
        with self.assertRaises(NotImplementedError):
            Camera.get_camera_controls(None)

    def test_set_defaults_raises_by_default(self):
        with self.assertRaises(NotImplementedError):
            Camera.set_default_controls(None, {})

    def test_reset_raises_by_default(self):
        with self.assertRaises(NotImplementedError):
            Camera.reset_controls(None)


if __name__ == "__main__":
    unittest.main()
