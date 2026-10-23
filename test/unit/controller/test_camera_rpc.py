"""Unit tests for the per-camera RPC surface on RPCControllerServer."""

import unittest
from concurrent.futures import Future
from contextlib import contextmanager
from unittest import mock

import zmq

from plantimager.commons.controller_device import ControllerDevice
from plantimager.controller.scanner.rpc_controller import RPCControllerServer


class FakeComm:
    """Stand-in for PiCameraComm, acting as its own RPC proxy."""

    def __init__(self, name, config):
        self._name = name
        self._config = dict(config)
        self._online = True

    @property
    def name(self):
        return self._name

    @property
    def config(self):
        return dict(self._config)

    @config.setter
    def config(self, value):
        self._config = dict(value)

    @contextmanager
    def camera(self):
        yield self if self._online else None

    def getCameraControls(self):
        return {"AwbMode": {}}

    def get_camera_controls(self):
        return {"AwbMode": {}}

    def set_default_controls(self, value):
        self._config = dict(value)
        return dict(self._config)

    def reset_controls(self, factory=False):
        self._config = {"ExposureTime": 1}
        return dict(self._config)

    def getImage(self, lores=False):
        if not self._online:
            return None
        future = Future()
        future.set_result((memoryview(b"fakejpeg"), {"format": "jpeg"}))
        return future


class TestCameraRpcSurface(unittest.TestCase):
    def setUp(self):
        self.context = zmq.Context()
        self.addCleanup(self.context.destroy, linger=0)
        self.comm = FakeComm("picamera", {"ExposureTime": 250000})
        self.scanner = mock.MagicMock()
        self.scanner.cameras = [self.comm]
        port = 19600 + (id(self) % 500)
        self.server = RPCControllerServer(
            self.context, f"tcp://127.0.0.1:{port}", self.scanner)

    def test_unknown_camera_rejected(self):
        with self.assertRaisesRegex(ValueError, "unknown camera"):
            self.server.get_camera_config("nope")

    def test_get_camera_config(self):
        self.assertEqual(self.server.get_camera_config("picamera"),
                         {"ExposureTime": 250000})

    def test_set_camera_config_returns_effective(self):
        out = self.server.set_camera_config("picamera", {"ExposureTime": 5})
        self.assertEqual(out, {"ExposureTime": 5})
        self.assertEqual(self.comm._config, {"ExposureTime": 5})

    def test_controls_schema_delegates(self):
        self.assertEqual(self.server.get_camera_controls_schema("picamera"),
                         {"AwbMode": {}})

    def test_set_defaults_and_reset(self):
        out = self.server.set_camera_default_controls(
            "picamera", {"ExposureTime": 9})
        self.assertEqual(out, {"ExposureTime": 9})
        out = self.server.reset_camera_controls("picamera")
        self.assertEqual(out, {"ExposureTime": 1})

    def test_get_camera_image(self):
        buffer, info = self.server.get_camera_image("picamera")
        self.assertEqual(bytes(buffer), b"fakejpeg")
        self.assertEqual(info["format"], "jpeg")

    def test_offline_camera_rejected(self):
        self.comm._online = False
        with self.assertRaisesRegex(ValueError, "offline"):
            self.server.get_camera_image("picamera")
        with self.assertRaisesRegex(ValueError, "offline"):
            self.server.set_camera_config("picamera", {})


class TestControllerDeviceDefaults(unittest.TestCase):
    """The ABC documents the contract; servers must override it."""

    def test_camera_verbs_raise_by_default(self):
        with self.assertRaises(NotImplementedError):
            ControllerDevice.get_camera_image(None, "cam")
        with self.assertRaises(NotImplementedError):
            ControllerDevice.get_camera_config(None, "cam")
        with self.assertRaises(NotImplementedError):
            ControllerDevice.set_camera_config(None, "cam", {})
        with self.assertRaises(NotImplementedError):
            ControllerDevice.get_camera_controls_schema(None, "cam")
        with self.assertRaises(NotImplementedError):
            ControllerDevice.set_camera_default_controls(None, "cam", {})
        with self.assertRaises(NotImplementedError):
            ControllerDevice.reset_camera_controls(None, "cam")


if __name__ == "__main__":
    unittest.main()
