"""Unit tests for the CameraBridge control surface.

``PiCameraComm`` is mocked (no registry, no hardware): what is verified
is the delegation to the comm object, the offline guards, and the
shared vocabulary exposed to QML.
"""

import unittest
from unittest import mock

import zmq
from PySide6.QtCore import QCoreApplication
from PySide6.QtCore import QObject

from plantimager.controller.camera.CameraBridge import CameraBridge
from plantimager.controller.camera.CameraBridge import DummyCameraBridge


class TestCameraBridgeControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance()
        if cls.app is None:
            cls.app = QCoreApplication([])

    def setUp(self):
        patcher = mock.patch(
            "plantimager.controller.camera.CameraBridge.PiCameraComm")
        self.addCleanup(patcher.stop)
        self.comm_class = patcher.start()
        self.bridge = CameraBridge("picamera1", "tcp://1.2.3.4:1234",
                                   zmq.Context())
        self.comm = self.comm_class.return_value

    def test_config_reads_through(self):
        self.comm.config = {"ExposureTime": 250000}
        self.assertEqual(self.bridge.config, {"ExposureTime": 250000})

    def test_config_write_sends_whole_dict(self):
        self.bridge.config = {"AwbMode": 5}
        self.assertEqual(self.comm.config, {"AwbMode": 5})

    def test_config_write_accepts_qml_js_object(self):
        from PySide6.QtQml import QJSEngine
        engine = QJSEngine()
        self.bridge.config = engine.evaluate("({ExposureTime: 5})")
        self.assertEqual(self.comm.config, {"ExposureTime": 5})

    def test_get_camera_controls_delegates(self):
        self.comm.getCameraControls.return_value = {"AwbMode": {}}
        self.assertEqual(self.bridge.getCameraControls(), {"AwbMode": {}})

    def test_set_default_controls_delegates(self):
        self.bridge.setDefaultControls({"AwbMode": 5})
        self.comm.setDefaultControls.assert_called_once_with({"AwbMode": 5})

    def test_reset_controls_delegates(self):
        self.bridge.resetControls(True)
        self.comm.resetControls.assert_called_once_with(True)

    def test_shared_vocabulary(self):
        self.assertEqual(self.bridge.controlFields,
                         ["ExposureTime", "AnalogueGain", "AwbEnable",
                          "AwbMode", "ColourGains"])
        modes = {m["value"]: m["name"] for m in self.bridge.awbModeNames}
        self.assertEqual(len(modes), 8)
        self.assertEqual(modes[5], "Daylight")


class TestDummyCameraBridgeControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance()
        if cls.app is None:
            cls.app = QCoreApplication([])

    def test_offline_guards(self):
        # Note: plain-Python reads of Property descriptors on the dummy
        # are unreliable (pre-existing quirk, QML reads go through the
        # meta-object and are unaffected); slots work everywhere.
        bridge = DummyCameraBridge(QObject())
        self.assertEqual(bridge.getCameraControls(), {})
        bridge.setDefaultControls({"AwbMode": 5})
        bridge.resetControls(True)


if __name__ == "__main__":
    unittest.main()
