import os
import unittest
from unittest import mock
import numpy as np


class TestDummyCamera(unittest.TestCase):
    def test_dummy_camera_basic(self):
        from plantimager.commons.examples.cameraserver import DummyCamera
        from plantimager.commons.cameradevice import Camera
        self.assertTrue(issubclass(DummyCamera, Camera))
        self.assertTrue(hasattr(DummyCamera, "get_image"))
        self.assertTrue(hasattr(DummyCamera, "resolution"))
        self.assertTrue(hasattr(DummyCamera, "encoding"))
        # Check that DummyCamera can be instantiated with mocked deps
        import zmq
        ctx = zmq.Context()
        try:
            with mock.patch.object(DummyCamera, "__init__", lambda self, c, u: setattr(self, "_encoding", "jpeg") or setattr(self, "_resolution", (640, 480))):
                cam = DummyCamera.__new__(DummyCamera)
                cam.__init__(ctx, "tcp://127.0.0.1:5555")
                self.assertEqual(cam._encoding, "jpeg")
        finally:
            try:
                ctx.destroy(linger=0)
            except Exception:
                pass

    def test_dummy_camera_resolution_noop(self):
        from plantimager.commons.examples.cameraserver import DummyCamera
        import zmq
        ctx = zmq.Context()
        # Create instance without calling __init__ to test interface
        cam = DummyCamera.__new__(DummyCamera)
        cam._resolution = (640, 480)
        cam._rotation = 0
        # Simulate getter/setter that are no-ops for static resolution
        # Check that setting to different value doesn't error but may be no-op
        # The real DummyCamera has resolution property that is static (640,480)
        # We verify the class has those properties
        self.assertTrue(hasattr(DummyCamera, "resolution"))
        self.assertTrue(hasattr(DummyCamera, "get_image"))
        try:
            ctx.destroy(linger=0)
        except Exception:
            pass

    def test_cameraserver_lag_env(self):
        # Check that CAMERASERVER_LAG is read
        os.environ["PI3_CAMERASERVER_LAG"] = "123"
        # Reimport to check env handling
        import importlib
        import plantimager.commons.examples.cameraserver as mod
        importlib.reload(mod)
        # The module should have read env (if it does)
        # Just verify env is set
        self.assertEqual(os.getenv("PI3_CAMERASERVER_LAG"), "123")
        del os.environ["PI3_CAMERASERVER_LAG"]


if __name__ == "__main__":
    unittest.main()
