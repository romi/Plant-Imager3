"""Unit tests for the PiCameraComm state handling around camera access."""

import unittest
from unittest import mock

from PySide6.QtCore import QCoreApplication
from PySide6.QtCore import QObject

from plantimager.controller.camera.PiCameraComm import CameraStates
from plantimager.controller.camera.PiCameraComm import PiCameraComm


def make_comm(state):
    comm = PiCameraComm.__new__(PiCameraComm)
    QObject.__init__(comm)
    comm._state = state
    comm._camera = mock.MagicMock()
    comm._thread_pool = mock.MagicMock()
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


if __name__ == "__main__":
    unittest.main()
