"""Unit tests for the PiCameraComm state handling around camera access."""

import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest import mock

from PySide6.QtCore import QCoreApplication
from PySide6.QtCore import QObject

from plantimager.controller.camera.PiCameraComm import CameraStates
from plantimager.controller.camera.PiCameraComm import PiCameraComm


def make_comm(state, pool=None):
    comm = PiCameraComm.__new__(PiCameraComm)
    QObject.__init__(comm)
    comm._state = state
    comm._camera = mock.MagicMock()
    comm._thread_pool = pool or ThreadPoolExecutor(max_workers=1)
    comm._attempt_connection = mock.MagicMock()
    return comm


class TestCameraContextStateRestore(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance()
        if cls.app is None:
            cls.app = QCoreApplication([])

    def test_fresher_transition_survives_read(self):
        """A capture finishing mid-read must not be clobbered back."""
        comm = make_comm(CameraStates.WAITING)
        with comm.camera():
            comm._set_state(CameraStates.CONNECTED)
        self.assertEqual(comm.state, CameraStates.CONNECTED)

    def test_quiet_read_restores_entry_state(self):
        comm = make_comm(CameraStates.CONNECTED)
        with comm.camera():
            pass
        self.assertEqual(comm.state, CameraStates.CONNECTED)

    def test_disconnect_during_read_is_kept(self):
        comm = make_comm(CameraStates.CONNECTED)
        with comm.camera():
            comm._set_state(CameraStates.DISCONNECTED)
        self.assertEqual(comm.state, CameraStates.DISCONNECTED)


class TestAsyncAttributeSets(unittest.TestCase):
    """Multiple attribute sets in quick succession must all reach the
    camera. Previously only the first (resolution) landed: _set_attr_async
    guarded on CONNECTED state, which flips to WAITING while the
    single-threaded pool task is in flight, silently dropping every
    subsequent set (encoding, config)."""

    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance()
        if cls.app is None:
            cls.app = QCoreApplication([])

    def setUp(self):
        self.comm = make_comm(CameraStates.CONNECTED, ThreadPoolExecutor(max_workers=1))

    def tearDown(self):
        self.comm._thread_pool.shutdown(wait=True)

    def _flush(self):
        """Drain the single-threaded pool so every submitted task ran."""
        self.comm._thread_pool.shutdown(wait=True)
        self.comm._thread_pool = ThreadPoolExecutor(max_workers=1)

    def test_all_attribute_sets_reach_camera(self):
        self.comm.resolution = (2000, 1500)
        self.comm.encoding = "png"
        self.comm.config = {"AwbMode": 5}
        self._flush()
        camera = self.comm._camera
        self.assertEqual(camera.resolution, (2000, 1500))
        self.assertEqual(camera.encoding, "png")
        self.assertEqual(camera.config, {"AwbMode": 5})

    def test_encoding_set_after_resolution_reaches_camera(self):
        self.comm.resolution = (2000, 1500)
        self.comm.encoding = "png"
        self._flush()
        self.assertEqual(self.comm._camera.resolution, (2000, 1500))
        self.assertEqual(self.comm._camera.encoding, "png")

    def test_state_is_connected_after_all_sets(self):
        self.comm.resolution = (2000, 1500)
        self.comm.encoding = "png"
        self.comm.config = {"AwbMode": 5}
        self._flush()
        self.assertEqual(self.comm.state, CameraStates.CONNECTED)


if __name__ == "__main__":
    unittest.main()
