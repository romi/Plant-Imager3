"""Unit tests for the web UI scan-page helper functions.

field_spec is now present (plantdb feature/metadata) and dash is available in
CI, so no mock dance needed.
"""

import base64
import unittest

from dash.exceptions import PreventUpdate

from plantimager.webui.scan import (
    FORBIDDEN_CHAR,
    _bio_field_id,
    _dump,
    _free_camera_name,
    _load_cfg,
    _num,
    all_valid_characters,
    check_dataset_name_uniqueness,
    handle_config_upload,
    is_valid_dataset_name,
    populate_path,
    validate_toml_textarea,
)


class TestScanHelpers(unittest.TestCase):
    """Dataset-name and TOML helpers (pre-existing)."""

    def test_all_valid_characters(self):
        self.assertTrue(all_valid_characters("ok_name-123"))
        self.assertTrue(all_valid_characters("Plant123"))
        for c in FORBIDDEN_CHAR:
            with self.subTest(c=c):
                self.assertFalse(all_valid_characters(f"a{c}b"))
                self.assertFalse(all_valid_characters(c))

    def test_is_valid_dataset_name_unicity(self):
        self.assertTrue(is_valid_dataset_name("new", ["old"]))
        self.assertFalse(is_valid_dataset_name("old", ["old"]))
        self.assertFalse(is_valid_dataset_name("bad:name", []))
        self.assertFalse(is_valid_dataset_name("bad/name", ["other"]))

    def test_is_valid_empty(self):
        self.assertTrue(is_valid_dataset_name("valid123", []))

    def test_validate_toml_valid(self):
        self.assertEqual(validate_toml_textarea("a = 1\nb = 'hi'\n"), (True, False))

    def test_validate_toml_invalid(self):
        self.assertEqual(validate_toml_textarea("a = [1,2\n"), (False, True))

    def test_validate_toml_empty(self):
        self.assertEqual(validate_toml_textarea(""), (False, False))
        self.assertEqual(validate_toml_textarea(None), (False, False))

    def test_check_dataset_uniqueness(self):
        self.assertEqual(check_dataset_name_uniqueness("exists", ["exists", "other"]), {"display": "block", "margin-top": "10px"})
        self.assertEqual(check_dataset_name_uniqueness("new", ["exists"]), {"display": "none"})

    def test_forbidden_char_list(self):
        self.assertIn(":", FORBIDDEN_CHAR)
        self.assertIn("/", FORBIDDEN_CHAR)
        self.assertEqual(len(FORBIDDEN_CHAR), 11)


class TestNewScanHelpers(unittest.TestCase):
    """PIv3 scan helpers added in feature/webui_metadata."""

    def test_num_coercion(self):
        self.assertIsNone(_num(None))
        self.assertIsNone(_num(""))
        self.assertEqual(_num("3"), 3)
        self.assertEqual(_num("3.7"), 3)
        self.assertEqual(_num("0"), 0)
        self.assertEqual(_num(5), 5)
        self.assertEqual(_num("bad"), "bad")

    def test_num_preserves_zero(self):
        self.assertEqual(_num(0), 0)
        self.assertEqual(_num("0"), 0)

    def test_free_camera_name(self):
        self.assertEqual(_free_camera_name(set()), "picamera")
        self.assertEqual(_free_camera_name({"picamera"}), "picamera1")
        self.assertEqual(_free_camera_name({"picamera", "picamera1"}), "picamera2")
        self.assertEqual(_free_camera_name({"picamera", "picamera1", "picamera2"}), "picamera3")

    def test_bio_field_id(self):
        self.assertEqual(_bio_field_id("object.investigation.title"), "bio-object__investigation__title")
        self.assertEqual(_bio_field_id("a.b.c"), "bio-a__b__c")

    def test_load_cfg_empty(self):
        self.assertEqual(_load_cfg(None), {})
        self.assertEqual(_load_cfg(""), {})
        self.assertEqual(_load_cfg("[ScanPath]\nclass_name='Circle'\n"), {"ScanPath": {"class_name": "Circle"}})

    def test_dump_and_load_roundtrip(self):
        cfg = {"ScanPath": {"class_name": "Circle", "kwargs": {"radius": 100}}, "Metadata": {"object": {"species": "x"}}}
        text = _dump(cfg)
        self.assertIn("Circle", text)
        self.assertEqual(_load_cfg(text)["ScanPath"]["class_name"], "Circle")

    def test_handle_config_upload_cylinder_rejected(self):
        import toml as toml_lib
        cfg_text = toml_lib.dumps({"ScanPath": {"class_name": "Cylinder", "kwargs": {"radius": 100}}})
        contents = "data:text/plain;base64," + base64.b64encode(cfg_text.encode()).decode()
        data, is_open, children, override_val, modal_open = handle_config_upload(contents)
        self.assertIsNone(data)
        self.assertTrue(is_open)
        self.assertIn("Cylinder", children)
        self.assertFalse(modal_open)

    def test_handle_config_upload_valid_circle(self):
        import toml as toml_lib
        cfg_text = toml_lib.dumps({"ScanPath": {"class_name": "Circle", "kwargs": {"radius": 100}}})
        contents = "data:text/plain;base64," + base64.b64encode(cfg_text.encode()).decode()
        data, is_open, children, override_val, modal_open = handle_config_upload(contents)
        self.assertEqual(data, cfg_text)
        self.assertFalse(is_open)
        self.assertTrue(modal_open)

    def test_handle_config_upload_invalid_toml(self):
        bad = base64.b64encode(b"a = [1,2\n").decode()
        contents = "data:text/plain;base64," + bad
        data, is_open, children, *_ = handle_config_upload(contents)
        self.assertIsNone(data)
        self.assertTrue(is_open)

    def test_populate_path_cylinder_raises_preventupdate(self):
        import toml as toml_lib
        cfg_text = toml_lib.dumps({"ScanPath": {"class_name": "Cylinder", "kwargs": {"radius": 100}}})
        with self.assertRaises(PreventUpdate):
            populate_path(cfg_text)

    def test_populate_path_circle_no_raise(self):
        import toml as toml_lib
        cfg_text = toml_lib.dumps({"ScanPath": {"class_name": "Circle", "kwargs": {"radius": 100, "n_points": 4}}})
        out = populate_path(cfg_text)
        self.assertEqual(len(out), 1 + 10 + 10)
        self.assertEqual(out[0], "Circle")


if __name__ == "__main__":
    unittest.main()
