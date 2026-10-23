"""Unit tests for the web UI scan-page helper functions.

field_spec is now present (plantdb feature/metadata) and dash is available in
CI, so no mock dance needed.
"""

import base64
import unittest

from dash import no_update
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
    prepare_scan,
    toggle_path_rows,
    run_scan,
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
        self.assertEqual(_num("3.7"), 3.7)
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
        self.assertEqual(len(out), 1 + 10)
        self.assertEqual(out[0], "Circle")

    def test_toggle_path_rows(self):
        from plantimager.webui.scan import PATH_FIELDS, PATH_ORDER
        for cls in ("Circle", "Line"):
            with self.subTest(cls=cls):
                out = toggle_path_rows(cls)
                self.assertEqual(len(out), len(PATH_ORDER))
                shown = {f for f, style in zip(PATH_ORDER, out)
                         if style["display"] == "block"}
                self.assertEqual(shown, set(PATH_FIELDS[cls]))


class TestNumCasting(unittest.TestCase):
    """Integral form values stay int, fractional stay float."""

    def test_integers(self):
        for value in ("36", "36.0", 36, 36.0):
            result = _num(value)
            self.assertEqual(result, 36)
            self.assertIsInstance(result, int)

    def test_fractions(self):
        self.assertEqual(_num("375.5"), 375.5)
        self.assertEqual(_num(0.5), 0.5)

    def test_empty_and_garbage(self):
        self.assertIsNone(_num(None))
        self.assertIsNone(_num(""))
        self.assertEqual(_num("abc"), "abc")


class TestScanArmGate(unittest.TestCase):
    """A stale job id without a matching arm token must not scan."""

    def test_stale_trigger_refused_without_touching_hardware(self):
        response, output, armed = run_scan(
            None, 5, "", "host", "1", "", False, "token", "a = 1", "ds")
        self.assertEqual(response, "Scan not started.")
        self.assertIn("Stale trigger", output)
        self.assertIs(armed, no_update)

    def test_fresh_load_refused(self):
        response, _, armed = run_scan(
            None, 0, "", "host", "1", "", False, "token", "a = 1", "ds")
        self.assertEqual(response, "Scan not started.")
        self.assertIs(armed, no_update)

    def test_failed_prepare_leaves_disarmed_seven_tuple(self):
        result = prepare_scan(
            None, "host", "1", "", False, "access", "refresh", "", "ds", 3)
        self.assertEqual(len(result), 7)
        self.assertEqual(result[3], 3)
        self.assertEqual(result[4], "")
        self.assertIn("Not authenticated", result[5])


def _cam_toml(*names_offsets):
    import toml as toml_lib
    doc = {"ScanPath": {"class_name": "Circle",
                        "kwargs": {"center_x": 375, "center_y": 375,
                                   "radius": 350, "n_points": 36}},
           "Metadata": {"object": {}}}
    for name, z in names_offsets:
        doc[name] = {"res_x": 2000, "res_y": 1500, "encoding": "jpeg",
                     "config": {},
                     "offset": {"x": 0, "y": 0, "z": z,
                                "pan": 0, "tilt": 0}}
    return toml_lib.dumps(doc)


def _slot_vals(toml_text):
    from plantimager.webui.scan import CAM_FIELDS
    from plantimager.webui.scan import MAX_CAMERAS
    from plantimager.webui.scan import populate_cameras
    pop = populate_cameras(toml_text)
    slots = []
    for i in range(MAX_CAMERAS):
        base = 1 + MAX_CAMERAS + i * len(CAM_FIELDS)
        slots.append({f: pop[base + j] for j, f in enumerate(CAM_FIELDS)})
    return pop[0], slots


def _interval_names(slots, available):
    from unittest import mock as _mock
    from dash import no_update as _nu
    from plantimager.webui import scan as _scan
    current = [s["name"] for s in slots]
    with _mock.patch.object(_scan, "RPCController") as mock_cls:
        inst = mock_cls.instance.return_value
        inst.camera_names = available
        inst.cameraNamesChanged = _mock.MagicMock()
        inst.cameraNamesChanged.connections = []
        out = _scan.update_interval(1, *current)
    return [c if v is _nu else v for v, c in zip(out[1:], current)]


def _rebuild(toml_text, active, slots, trigger="cam-0-name.value"):
    from unittest import mock as _mock
    from plantimager.webui.scan import CAM_FIELDS
    from plantimager.webui.scan import MAX_CAMERAS
    from plantimager.webui import scan as _scan
    args = [None] * (1 + MAX_CAMERAS)
    for i in range(MAX_CAMERAS):
        for f in CAM_FIELDS:
            args.append(slots[i][f])
    args.append(list(active))
    args.append(toml_text)
    with _mock.patch.object(_scan, "callback_context") as mock_ctx:
        mock_ctx.triggered = [{"prop_id": trigger}]
        return _scan.rebuild_cameras(*args)


class TestCameraCardNames(unittest.TestCase):
    """The interval auto-fill must never rename real sections.

    Every default rig name looks auto-generated, so positional
    overwrite renamed sections and rebuild_cameras then deleted the
    orphaned config (e.g. picamera2 with its z-offset).
    """

    def test_order_mismatch_keeps_names(self):
        toml_text = _cam_toml(("picamera", 0), ("picamera2", -100))
        _, slots = _slot_vals(toml_text)
        self.assertEqual([s["name"] for s in slots[:2]],
                         ["picamera", "picamera2"])
        filled = _interval_names(slots, ["picamera2"])
        self.assertEqual(filled[:2], ["picamera", "picamera2"])

    def test_extra_live_camera_does_not_rename_slot(self):
        toml_text = _cam_toml(("picamera2", -100))
        _, slots = _slot_vals(toml_text)
        filled = _interval_names(slots, ["picamera", "picamera2"])
        for s, name in zip(slots, filled):
            s["name"] = name
        self.assertEqual(slots[0]["name"], "picamera2")
        new_toml, _ = _rebuild(toml_text, [0], slots)
        import tomllib
        cfg = tomllib.loads(new_toml)
        self.assertIn("picamera2", cfg)
        self.assertEqual(cfg["picamera2"]["offset"]["z"], -100)

    def test_rebuild_keeps_both_sections_when_one_offline(self):
        toml_text = _cam_toml(("picamera", 0), ("picamera2", -100))
        _, slots = _slot_vals(toml_text)
        filled = _interval_names(slots, ["picamera"])
        for s, name in zip(slots, filled):
            s["name"] = name
        new_toml, _ = _rebuild(toml_text, [0, 1], slots)
        import tomllib
        cfg = tomllib.loads(new_toml)
        self.assertEqual(cfg["picamera"]["offset"]["z"], 0)
        self.assertEqual(cfg["picamera2"]["offset"]["z"], -100)

    def test_empty_slot_still_autofills(self):
        toml_text = _cam_toml(("picamera", 0))
        _, slots = _slot_vals(toml_text)
        slots[1]["name"] = ""
        filled = _interval_names(slots, ["picamera", "picamera2"])
        self.assertEqual(filled[1], "picamera2")


class TestEncodingRoundTrip(unittest.TestCase):
    """Changing a camera's encoding in the web UI must survive the
    populate → edit → rebuild → configure round trip and land on the
    camera (issue: changing jpeg→png did not take effect)."""

    def test_encoding_survives_populate_rebuild_populate(self):
        """populate_cameras must not clobber an encoding the user just
        picked; rebuild_cameras must write it into the TOML; the scanner
        must apply it."""
        import tomllib

        from plantimager.webui import scan as _scan
        from plantimager.webui.scan import CAM_FIELDS
        from plantimager.webui.scan import MAX_CAMERAS

        toml_text = _cam_toml(("picamera", 0))

        # 1. populate form from toml (encoding = jpeg)
        _, slots = _slot_vals(toml_text)
        self.assertEqual(slots[0]["encoding"], "jpeg")

        # 2. user picks png in the encoding dropdown
        slots[0]["encoding"] = "png"

        # 3. rebuild_cameras writes the toml with encoding = png
        new_toml, _ = _rebuild(toml_text, [0], slots, trigger="cam-0-encoding.value")
        cfg = tomllib.loads(new_toml)
        self.assertEqual(cfg["picamera"]["encoding"], "png")

        # 4. populate_cameras re-reads the toml and does not clobber png back to jpeg
        pop2 = _scan.populate_cameras(new_toml)
        slots2 = []
        for i in range(MAX_CAMERAS):
            base = 1 + MAX_CAMERAS + i * len(CAM_FIELDS)
            slots2.append({f: pop2[base + j] for j, f in enumerate(CAM_FIELDS)})
        self.assertEqual(slots2[0]["encoding"], "png")

        # 5. scanner applies encoding to the camera
        from PySide6.QtCore import QCoreApplication
        from unittest import mock as _mock
        app = QCoreApplication.instance() or QCoreApplication([])
        with _mock.patch("plantimager.controller.scanner.scanner.CNC") as mock_cnc:
            mock_cnc.side_effect = Exception("no hardware")
            from plantimager.controller.scanner.scanner import Scanner
            scanner = Scanner()
        mock_camera = _mock.MagicMock()
        mock_camera.name = "picamera"
        scanner.add_camera(mock_camera)
        scanner.scan_id = "test"
        scanner.db_client = _mock.MagicMock()
        scanner.uploader = _mock.MagicMock()
        scanner.configure_scan(cfg)
        self.assertEqual(mock_camera.encoding, "png")



if __name__ == "__main__":
    unittest.main()
