"""Unit tests for the :class:`plantimager.controller.scanner.dummy_cnc.DummyCNC`.

These tests exercise the dummy CNC controller's state machine: default
initialization, movement limits, homing, position reporting (with simulated
noise), async movement and waiting, status reporting, and stop/reset
behaviour. ``time.sleep`` is patched in ``setUp`` so movement simulations run
immediately instead of blocking on real delays.
"""

import unittest
from unittest import mock
from plantimager.controller.scanner.dummy_cnc import DummyCNC


class TestDummyCNC(unittest.TestCase):
    """Tests for the DummyCNC controller."""

    def setUp(self):
        # patch sleep to speed up
        patcher = mock.patch("plantimager.controller.scanner.dummy_cnc.time.sleep", return_value=None)
        self.addCleanup(patcher.stop)
        patcher.start()
        self.cnc = DummyCNC()

    def test_init_defaults(self):
        """A fresh DummyCNC has default limits, origin position, and has started."""
        self.assertEqual(self.cnc.x_lims, (0, 740))
        self.assertEqual(self.cnc.y_lims, (0, 740))
        self.assertEqual(self.cnc._position, (0, 0, 0))
        self.assertTrue(self.cnc.has_started)

    def test_check_move_raises(self):
        """Out-of-range x/y moves raise ValueError; z is not range-checked."""
        with self.assertRaises(ValueError):
            self.cnc._check_move(800, 0, 0)
        with self.assertRaises(ValueError):
            self.cnc._check_move(0, 800, 0)
        # z is not checked in dummy (only x,y)
        self.cnc._check_move(100, 100, 400)

    def test_home(self):
        """Homing moves to the home position and clears the busy flag."""
        # need real sleep mock but we patched, so home sets position immediately after thread?
        # home is synchronous with sleep 1.5 mocked -> immediate
        self.cnc.home()
        self.assertEqual(self.cnc._position, (20, 20, 0))
        self.assertFalse(self.cnc._busy)

    def test_reset_pos(self):
        """reset_pos returns the position to the home coordinates."""
        self.cnc._position = (100, 100, 90)
        self.cnc.reset_pos()
        self.assertEqual(self.cnc._position, (20, 20, 0))

    def test_get_position_noise(self):
        """get_position adds uniform noise to the reported coordinates."""
        # get_position adds uniform noise [-0.01,0.01]
        with mock.patch("plantimager.controller.scanner.dummy_cnc.random.uniform", side_effect=lambda a, b: 0.005):
            x, y, z = self.cnc.get_position()
            self.assertAlmostEqual(x, 0.005)
            self.assertAlmostEqual(y, 0.005)
            self.assertAlmostEqual(z, 0.005)

    def test_moveto_updates(self):
        """moveto moves the CNC to the requested position."""
        self.cnc.moveto(100, 100, 45)
        # moveto does moveto_async + wait; with sleep mocked, _simulate_movement runs quickly but in thread
        # need to wait a tiny real time for thread to set position
        import time
        time.sleep(0.05)
        self.assertEqual(self.cnc._position, (100, 100, 45))

    def test_moveto_async_and_wait(self):
        """moveto_async followed by wait reaches the target and clears busy."""
        self.cnc.moveto_async(200, 200, 90)
        # with sleep mocked, movement may already be done; just wait
        self.cnc.wait(timeout=2)
        import time
        time.sleep(0.05)
        self.assertEqual(self.cnc._position, (200, 200, 90))
        self.assertFalse(self.cnc._busy)

    def test_wait_timeout(self):
        """wait raises TimeoutError when the CNC stays busy past the timeout."""
        self.cnc._busy = True
        with self.assertRaises(TimeoutError):
            self.cnc.wait(timeout=0.1)

    def test_moveto_async_limits(self):
        """moveto_async rejects out-of-range coordinates with ValueError."""
        with self.assertRaises(ValueError):
            self.cnc.moveto_async(1000, 0, 0)

    def test_send_cmd(self):
        """send_cmd acknowledges any command with 'ok'."""
        self.assertEqual(self.cnc.send_cmd("G0 X10"), "ok")

    def test_get_status(self):
        """get_status reports Idle when free and Run when busy."""
        self.cnc._busy = False
        s = self.cnc.get_status()
        self.assertEqual(s["status"], "Idle")
        self.cnc._busy = True
        s = self.cnc.get_status()
        self.assertEqual(s["status"], "Run")

    def test_xy_property(self):
        """The x/y/z properties report the current position."""
        self.cnc._position = (10, 20, 30)
        # x/y use get_position which adds noise, so mock noise 0
        with mock.patch("plantimager.controller.scanner.dummy_cnc.random.uniform", return_value=0):
            self.assertEqual(self.cnc.x, 10)
            self.assertEqual(self.cnc.y, 20)
            self.assertEqual(self.cnc.z, 30)

    def test_stop(self):
        """stop clears the busy flag."""
        self.cnc._busy = True
        self.cnc.stop()
        self.assertFalse(self.cnc._busy)


if __name__ == "__main__":
    unittest.main()
