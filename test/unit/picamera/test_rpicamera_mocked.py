import json
import os
import sys
import tempfile
import unittest
from unittest import mock
import numpy as np

# Skip if picamera2 not available on this platform (x86)
try:
    import picamera2
    HAS_PICAMERA2 = True
except ImportError:
    HAS_PICAMERA2 = False
    for _stub in ("picamera2", "picamera2.encoders", "picamera2.outputs", "av", "simplejpeg"):
        sys.modules.setdefault(_stub, mock.MagicMock(name=_stub))

# plantimager.picamera is not installed (no Pi hardware here); import it from source.
_SRC_PICAMERA = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "src", "picamera"))
if os.path.isdir(_SRC_PICAMERA) and _SRC_PICAMERA not in sys.path:
    sys.path.insert(0, _SRC_PICAMERA)


@unittest.skipIf(not HAS_PICAMERA2, "picamera2 not available (x86 skip)")
class TestRPCCameraMocked(unittest.TestCase):
    def setUp(self):
        # Create fake Picamera2
        self.patcher = mock.patch("plantimager.picamera.RPCCamera.Picamera2")
        self.mock_picam_class = self.patcher.start()
        self.addCleanup(self.patcher.stop)

        self.mock_picam = mock.MagicMock()
        self.mock_picam.camera_properties = {"PixelArraySize": (4608, 2592)}
        self.mock_picam.create_still_configuration.return_value = {
            "main": {"size": (2304, 1296), "format": "BGR888"},
            "lores": {"size": (1920, 1440)},
        }
        self.mock_picam.create_video_configuration.return_value = {
            "main": {"size": (640, 480), "format": "YUV420"}
        }
        fake_array = np.zeros((1296, 2304, 3), dtype=np.uint8)
        fake_lores = np.zeros((1440, 1920), dtype=np.uint8)
        self.mock_picam.capture_array.side_effect = lambda channel="main": fake_lores if channel == "lores" else fake_array
        self.mock_picam_class.return_value = self.mock_picam

        # Mock av and simplejpeg to avoid heavy deps
        self.av_patcher = mock.patch("plantimager.picamera.RPCCamera.av")
        self.av_patcher.start()
        self.addCleanup(self.av_patcher.stop)
        self.jpeg_patcher = mock.patch("plantimager.picamera.RPCCamera.encode_jpeg", return_value=b"fakejpeg")
        self.jpeg_patcher.start()
        self.addCleanup(self.jpeg_patcher.stop)
        self.jpeg_yuv_patcher = mock.patch("plantimager.picamera.RPCCamera.encode_jpeg_yuv_planes", return_value=b"fakeyuv")
        self.jpeg_yuv_patcher.start()
        self.addCleanup(self.jpeg_yuv_patcher.stop)

        import zmq
        self.context = zmq.Context()
        # Use random port to avoid conflict
        import random
        port = random.randint(18000, 19000)
        self.url = f"tcp://127.0.0.1:{port}"
        # Patch zmq context already created
        from plantimager.picamera.RPCCamera import RPCCamera
        # Need to mock RPCServer bind to avoid needing real network? Use real bind but random port
        # Actually RPCCamera inherits RPCServer which will bind to url; use url with no port? We'll use random port
        # Let's create with url containing port, it will bind
        try:
            self.camera = RPCCamera(self.context, self.url)
        except Exception as e:
            self.skipTest(f"Failed to create RPCCamera: {e}")

    def tearDown(self):
        try:
            self.camera.picam.stop_encoder = mock.MagicMock()
        except Exception:
            pass
        try:
            self.context.destroy(linger=0)
        except Exception:
            pass

    def test_init_half_res(self):
        self.assertEqual(self.mock_picam.create_still_configuration.called, True)
        # Check still_config stored
        self.assertIn("main", self.camera.still_config)

    def test_get_image_still(self):
        buffer, info = self.camera.get_image(lores=False)
        self.assertIsInstance(buffer, memoryview)
        self.assertEqual(info["format"], "jpeg")

    def test_get_image_lores(self):
        buffer, info = self.camera.get_image(lores=True)
        self.assertIsInstance(buffer, memoryview)
        self.assertEqual(info["format"], "jpeg")

    def test_encoding_setter(self):
        self.camera.encoding = "png"
        self.assertEqual(self.camera._encoding, "png")
        # invalid should not change
        self.camera.encoding = "invalid"
        self.assertEqual(self.camera._encoding, "png")

    def test_rotation(self):
        self.camera.rotation = 180
        self.assertEqual(self.camera._rotation, 180)
        self.camera.rotation = 400
        self.assertEqual(self.camera._rotation, 40)

    def test_resolution(self):
        # Fixed: getter now returns still_config["main"]["size"] (was None).
        self.assertEqual(self.camera.resolution, (2304, 1296))
        self.camera.resolution = (1000, 1000)
        self.assertEqual(self.camera.still_config["main"]["size"], (1000, 1000))
        self.assertEqual(self.camera.resolution, (1000, 1000))


@unittest.skipIf(HAS_PICAMERA2, "picamera2 available, test fallback skip logic not needed")
class TestRPCCameraSkip(unittest.TestCase):
    def test_skip_when_no_picamera2(self):
        self.assertFalse(HAS_PICAMERA2)


class TestRPCCameraControls(unittest.TestCase):
    """Validator, persistence, metadata and ranges — runnable without Pi hardware."""

    CONTROLS = {
        "AeEnable": (False, True, True),
        "ExposureTime": (74, 694422939, 20000),
        "AnalogueGain": (1.0, 22.26, 1.0),
        "AwbEnable": (False, True, None),
        "AwbMode": (0, 7, 0),
        "ColourGains": (0.0, 32.0, None),
        "AeMeteringMode": (0, 3, 0),
        "NoiseReductionMode": (0, 4, 0),
        "Brightness": (-1.0, 1.0, 0.0),
        "SyncFrames": (1, 1000000, 100),
        "ScalerCrop": ((0, 0, 64, 64), (0, 0, 4056, 3040), (2, 0, 4053, 3040)),
        "FrameDurationLimits": (57502, 694434742, 33333),
        "ColourCorrectionMatrix": (0.0, 8.0, None),
    }
    META = {"ExposureTime": 249981, "AnalogueGain": 6.965986,
            "ColourGains": [3.215242, 1.432874], "FrameDuration": 250589,
            "Lux": 5.388776, "ColourTemperature": 6669,
            "SensorTemperature": 25.0}

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.params_file = os.path.join(self._tmp.name, "camera_parameters.json")
        env = mock.patch.dict(os.environ, {"CAMERA_PARAMS_FILE": self.params_file})
        env.start()
        self.addCleanup(env.stop)

        patcher = mock.patch("plantimager.picamera.RPCCamera.Picamera2")
        self.mock_picam_class = patcher.start()
        self.addCleanup(patcher.stop)
        self.camera, self.picam, self.context = self._make(19000)

        for target, value in (
                ("plantimager.picamera.RPCCamera.encode_jpeg", b"fakejpeg"),
                ("plantimager.picamera.RPCCamera.encode_jpeg_yuv_planes", b"fakeyuv")):
            p = mock.patch(target, return_value=value)
            p.start()
            self.addCleanup(p.stop)

    def _make(self, port):
        picam = mock.MagicMock()
        picam.camera_properties = {"PixelArraySize": (4608, 2592)}
        picam.create_still_configuration.return_value = {
            "main": {"size": (2304, 1296), "format": "BGR888"},
            "lores": {"size": (1920, 1440)},
        }
        picam.create_video_configuration.return_value = {
            "main": {"size": (640, 480), "format": "YUV420"}
        }
        picam.camera_controls = dict(self.CONTROLS)
        picam.capture_metadata.return_value = dict(self.META)
        self.mock_picam_class.return_value = picam
        import random
        import zmq
        context = zmq.Context()
        self.addCleanup(context.destroy, linger=0)
        from plantimager.picamera.RPCCamera import RPCCamera
        url = f"tcp://127.0.0.1:{port + random.randint(0, 500)}"
        return RPCCamera(context, url), picam, context

    def test_boot_applies_factory_defaults(self):
        self.assertEqual(self.camera._config["ExposureTime"], 250000)
        self.assertEqual(self.camera._config["AwbMode"], 5)
        self.assertEqual(self.camera._config["ColourGains"], (3.215, 1.433))
        self.assertFalse(os.path.exists(self.params_file))

    def test_config_replace_wholesale(self):
        self.camera.config = {"Brightness": 0.5}
        self.assertEqual(self.camera._config, {"Brightness": 0.5})

    def test_config_unknown_key_rejected(self):
        calls = self.picam.set_controls.call_count
        with self.assertRaisesRegex(ValueError, "not advertised"):
            self.camera.config = {"NotAControl": 1}
        self.assertEqual(self.camera._config["ExposureTime"], 250000)
        self.assertEqual(self.picam.set_controls.call_count, calls)

    def test_config_out_of_range_rejected(self):
        calls = self.picam.set_controls.call_count
        with self.assertRaisesRegex(ValueError, "out of range"):
            self.camera.config = {"ExposureTime": 99999999999}
        self.assertEqual(self.camera._config["ExposureTime"], 250000)
        self.assertEqual(self.picam.set_controls.call_count, calls)

    def test_config_rounds_float_to_int(self):
        self.camera.config = {"ExposureTime": 250000.0, "AwbMode": 5.0}
        self.assertEqual(self.camera._config["ExposureTime"], 250000)
        self.assertIsInstance(self.camera._config["ExposureTime"], int)
        self.assertEqual(self.camera._config["AwbMode"], 5)
        self.assertIsInstance(self.camera._config["AwbMode"], int)
        self.camera.config = {"AwbMode": 2.6}
        self.assertEqual(self.camera._config["AwbMode"], 3)

    def test_config_gotchas_rejected(self):
        bad = [{"ColourGains": (0, 0)}, {"ColourGains": (1.8,)},
               {"ColourGains": ("a", 1.4)},
               {"AeEnable": 1}, {"FrameRate": -5}, {"FrameRate": True}]
        for value in bad:
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.camera.config = value

    def test_config_virtual_framerate_sentinel_and_normalization(self):
        self.camera.config = {"FrameRate": 15, "ExposureTime": 0,
                              "AnalogueGain": 0, "ColourGains": [3.2, 1.4]}
        self.assertEqual(self.camera._config["FrameRate"], 15)
        self.assertEqual(self.camera._config["ExposureTime"], 0)
        self.assertEqual(self.camera._config["ColourGains"], (3.2, 1.4))

    def test_config_scalercrop_elementwise(self):
        self.camera.config = {"ScalerCrop": (0, 0, 64, 64)}
        with self.assertRaisesRegex(ValueError, "out of range"):
            self.camera.config = {"ScalerCrop": (0, 0, 63, 64)}

    def test_persistence_roundtrip(self):
        self.camera.set_default_controls({"Brightness": 0.5, "ExposureTime": 100000})
        with open(self.params_file) as fh:
            self.assertEqual(json.load(fh), {"Brightness": 0.5, "ExposureTime": 100000})
        camera, _, _ = self._make(19500)
        self.assertEqual(camera._config, {"Brightness": 0.5, "ExposureTime": 100000})

    def test_corrupt_file_falls_back_to_factory(self):
        with open(self.params_file, "w") as fh:
            fh.write("{not json")
        camera, _, _ = self._make(19600)
        self.assertEqual(camera._config["ExposureTime"], 250000)

    def test_session_setter_does_not_persist(self):
        self.camera.set_default_controls({"Brightness": -0.5})
        with open(self.params_file) as fh:
            before = fh.read()
        self.camera.config = {"Brightness": 0.9}
        with open(self.params_file) as fh:
            self.assertEqual(fh.read(), before)

    def test_reset_controls_restores_defaults(self):
        self.camera.set_default_controls({"Brightness": -0.5})
        with open(self.params_file) as fh:
            before = fh.read()
        self.camera.config = {"Brightness": 0.9}
        self.camera.reset_controls()
        self.assertEqual(self.camera._config, {"Brightness": -0.5})
        with open(self.params_file) as fh:
            self.assertEqual(fh.read(), before)

    def test_reset_controls_factory(self):
        self.camera.set_default_controls({"Brightness": -0.5})
        self.camera.reset_controls(factory=True)
        self.assertEqual(self.camera._config["ExposureTime"], 250000)
        with open(self.params_file) as fh:
            self.assertEqual(json.load(fh)["ExposureTime"], 250000)

    def test_set_default_controls_invalid_keeps_state(self):
        self.camera.set_default_controls({"Brightness": -0.5})
        with open(self.params_file) as fh:
            before = fh.read()
        calls = self.picam.set_controls.call_count
        for bad in ({"Nope": 1}, {"ExposureTime": 99999999999}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.camera.set_default_controls(bad)
        self.assertEqual(self.camera._config, {"Brightness": -0.5})
        self.assertEqual(self.picam.set_controls.call_count, calls)
        with open(self.params_file) as fh:
            self.assertEqual(fh.read(), before)

    def test_rpc_dispatch_with_omitted_arg(self):
        self.assertIn("reset_controls", self.camera._json_methods)
        self.assertIn("set_default_controls", self.camera._json_methods)
        self.camera.set_default_controls({"Brightness": 0.25})
        reply, use_buffer = self.camera._handle_method_call(
            {"method": "reset_controls", "params": {"args": [], "kwargs": {}}})
        self.assertFalse(use_buffer)
        self.assertTrue(reply["success"], reply)
        self.assertEqual(self.camera._config, {"Brightness": 0.25})

    def test_get_camera_controls_schema(self):
        ranges = self.camera.get_camera_controls()
        json.dumps(ranges)
        self.assertNotIn("FrameRate", ranges)
        self.assertEqual(ranges["AwbMode"],
                         {"type": "enum", "min": 0, "max": 7, "default": 0,
                          "allowed_values": [0, 1, 2, 3, 4, 5, 6, 7]})
        self.assertEqual(ranges["AeEnable"], {"type": "bool", "default": True})
        self.assertEqual(ranges["ExposureTime"]["type"], "scalar")
        self.assertEqual(ranges["SyncFrames"]["type"], "scalar")
        self.assertEqual(ranges["ColourGains"],
                         {"type": "tuple", "length": 2, "min": 0.0,
                          "max": 32.0, "default": None})
        self.assertEqual(ranges["ScalerCrop"]["length"], 4)
        self.assertIsInstance(ranges["ScalerCrop"]["min"], list)
        self.assertEqual(ranges["ColourCorrectionMatrix"]["length"], 9)
        self.assertIsNone(ranges["AwbEnable"]["default"])

    def test_get_camera_controls_nondict_empty(self):
        self.picam.camera_controls = mock.MagicMock()
        self.assertEqual(self.camera.get_camera_controls(), {})

    def _still_lores_arrays(self):
        self.picam.capture_array.side_effect = lambda channel="main": (
            np.zeros((2160, 1920), dtype=np.uint8) if channel == "lores"
            else np.zeros((16, 16, 3), dtype=np.uint8))

    def test_get_image_carries_metadata(self):
        self._still_lores_arrays()
        for lores in (False, True):
            _, info = self.camera.get_image(lores=lores)
            for key in ("ExposureTime", "AnalogueGain", "ColourGains",
                        "FrameDuration", "Lux", "ColourTemperature"):
                self.assertEqual(info[key], self.META[key])
            self.assertNotIn("SensorTemperature", info)
            self.assertEqual(info["format"], "jpeg")

    def test_get_image_metadata_failure_keeps_image(self):
        self._still_lores_arrays()
        self.picam.capture_metadata.side_effect = RuntimeError("hang")
        _, info = self.camera.get_image()
        self.assertEqual(info["format"], "jpeg")
        self.assertNotIn("ExposureTime", info)
        self.picam.capture_metadata.side_effect = None
        self.picam.capture_metadata.return_value = {"Lux": 5.0}
        _, info = self.camera.get_image()
        self.assertEqual(info["Lux"], 5.0)
        self.assertNotIn("ExposureTime", info)

    def test_resolution_getter_returns_main_size(self):
        self.assertEqual(self.camera.resolution, (2304, 1296))

    def test_analogue_gain_stored_as_given(self):
        self.camera.config = {"AnalogueGain": 7}
        self.assertEqual(self.camera._config, {"AnalogueGain": 7})


if __name__ == "__main__":
    unittest.main()
