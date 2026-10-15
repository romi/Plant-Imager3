"""Unit tests for the shared WebUI camera-control helpers."""

import io
import tomllib
import unittest

from PIL import Image

from plantimager.commons.camera_controls import AWB_MODES
from plantimager.webui.camera_controls import AWB_OPTIONS
from plantimager.webui.camera_controls import build_toml_snippet
from plantimager.webui.camera_controls import camera_control_form
from plantimager.webui.camera_controls import field_ids
from plantimager.webui.camera_controls import merge_config
from plantimager.webui.camera_controls import oriented_jpeg
from plantimager.webui.camera_controls import parse_number
from plantimager.webui.camera_controls import parse_toml_snippet


class TestAwbOptions(unittest.TestCase):
    def test_matches_shared_table(self):
        self.assertEqual(
            [(o["value"], o["label"]) for o in AWB_OPTIONS], list(AWB_MODES))
        self.assertEqual(
            [o for o in AWB_OPTIONS if o["value"] == 5][0]["label"], "Daylight")


class TestFieldIds(unittest.TestCase):
    def test_prefixed_and_unique(self):
        ids = field_ids("cam-2")
        self.assertEqual(len(set(ids.values())), 6)
        self.assertTrue(all(v.startswith("cam-2-") for v in ids.values()))
        self.assertNotEqual(field_ids("cam")["exposure"],
                            field_ids("cam-1")["exposure"])

    def test_form_builds(self):
        layout, ids = camera_control_form("cam")
        self.assertEqual(ids, field_ids("cam"))
        self.assertIsNotNone(layout)


class TestParseNumber(unittest.TestCase):
    def test_passthrough_and_strings(self):
        self.assertEqual(parse_number(5), 5)
        self.assertEqual(parse_number(7.5), 7.5)
        self.assertEqual(parse_number("5"), 5)
        self.assertEqual(parse_number("7.5"), 7.5)

    def test_empty_and_garbage_give_none(self):
        for bad in (None, "", "  ", "abc", True):
            self.assertIsNone(parse_number(bad), bad)


class TestMergeConfig(unittest.TestCase):
    def test_edits_win_none_keeps(self):
        merged = merge_config({"ExposureTime": 1, "AwbMode": 0},
                              {"ExposureTime": 5, "AwbMode": None})
        self.assertEqual(merged, {"ExposureTime": 5, "AwbMode": 0})


class TestTomlSnippet(unittest.TestCase):
    CONFIG = {"ExposureTime": 250000, "AnalogueGain": 7.0, "AwbEnable": False,
              "AwbMode": 5, "ColourGains": [3.215, 1.433]}

    def test_round_trip_preserves_types(self):
        snippet = build_toml_snippet("picamera", self.CONFIG)
        self.assertIn("[picamera.config]", snippet)
        parsed = parse_toml_snippet(snippet)
        self.assertEqual(parsed, self.CONFIG)
        reparsed = tomllib.loads(snippet)
        self.assertIs(reparsed["picamera"]["config"]["AwbEnable"], False)
        self.assertIsInstance(reparsed["picamera"]["config"]["ExposureTime"], int)

    def test_bare_keys_accepted(self):
        parsed = parse_toml_snippet("ExposureTime = 5\nAwbMode = 0\n")
        self.assertEqual(parsed, {"ExposureTime": 5, "AwbMode": 0})

    def test_garbage_rejected(self):
        with self.assertRaises(ValueError):
            parse_toml_snippet("ExposureTime = [1,2\n")
        with self.assertRaises(ValueError):
            parse_toml_snippet("[a]\nx = 1\n[b]\ny = 2\n")


class TestOrientedJpeg(unittest.TestCase):
    @staticmethod
    def _raw(width=40, height=20):
        buf = io.BytesIO()
        Image.new("RGB", (width, height), "red").save(buf, format="JPEG")
        return buf.getvalue()

    @staticmethod
    def _size(raw):
        return Image.open(io.BytesIO(raw)).size

    def test_no_rotation_passes_through(self):
        raw = self._raw()
        self.assertEqual(oriented_jpeg(raw, {}), raw)
        self.assertEqual(oriented_jpeg(raw, {"rotation": 0}), raw)

    def test_quarter_turns_swap_dimensions(self):
        raw = self._raw()
        self.assertEqual(self._size(oriented_jpeg(raw, {"rotation": 90})), (20, 40))
        self.assertEqual(self._size(oriented_jpeg(raw, {"rotation": 270})), (20, 40))
        self.assertEqual(self._size(oriented_jpeg(raw, {"rotation": 180})), (40, 20))


if __name__ == "__main__":
    unittest.main()
