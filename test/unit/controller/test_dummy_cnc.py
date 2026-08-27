import unittest
from unittest import mock
from plantimager.controller.scanner.dummy_cnc import DummyCNC


class TestDummyCNC(unittest.TestCase):
    def setUp(self):
        # patch sleep to speed up
        patcher = mock.patch("plantimager.controller.scanner.dummy_cnc.time.sleep", return_value=None)
        self.addCleanup(patcher.stop)
        patcher.start()
        self.cnc = DummyCNC()

    def test_init_defaults(self):
        self.assertEqual(self.cnc.x_lims, (0, 740))
        self.assertEqual(self.cnc.y_lims, (0, 740))
        self.assertEqual(self.cnc._position, (0, 0, 0))
        self.assertTrue(self.cnc.has_started)

    def test_check_move_raises(self):
        with self.assertRaises(ValueError):
            self.cnc._check_move(800, 0, 0)
        with self.assertRaises(ValueError):
            self.cnc._check_move(0, 800, 0)
        # z is not checked in dummy (only x,y)
        self.cnc._check_move(100, 100, 400)

    def test_home(self):
        # need real sleep mock but we patched, so home sets position immediately after thread?
        # home is synchronous with sleep 1.5 mocked -> immediate
        self.cnc.home()
        self.assertEqual(self.cnc._position, (20, 20, 0))
        self.assertFalse(self.cnc._busy)

    def test_reset_pos(self):
        self.cnc._position = (100, 100, 90)
        self.cnc.reset_pos()
        self.assertEqual(self.cnc._position, (20, 20, 0))

    def test_get_position_noise(self):
        # get_position adds uniform noise [-0.01,0.01]
        with mock.patch("plantimager.controller.scanner.dummy_cnc.random.uniform", side_effect=lambda a, b: 0.005):
            x, y, z = self.cnc.get_position()
            self.assertAlmostEqual(x, 0.005)
            self.assertAlmostEqual(y, 0.005)
            self.assertAlmostEqual(z, 0.005)

    def test_moveto_updates(self):
        self.cnc.moveto(100, 100, 45)
        # moveto does moveto_async + wait; with sleep mocked, _simulate_movement runs quickly but in thread
        # need to wait a tiny real time for thread to set position
        import time
        time.sleep(0.05)
        self.assertEqual(self.cnc._position, (100, 100, 45))

    def test_moveto_async_and_wait(self):
        self.cnc.moveto_async(200, 200, 90)
        # with sleep mocked, movement may already be done; just wait
        self.cnc.wait(timeout=2)
        import time
        time.sleep(0.05)
        self.assertEqual(self.cnc._position, (200, 200, 90))
        self.assertFalse(self.cnc._busy)

    def test_wait_timeout(self):
        self.cnc._busy = True
        with self.assertRaises(TimeoutError):
            self.cnc.wait(timeout=0.1)

    def test_moveto_async_limits(self):
        with self.assertRaises(ValueError):
            self.cnc.moveto_async(1000, 0, 0)

    def test_send_cmd(self):
        self.assertEqual(self.cnc.send_cmd("G0 X10"), "ok")

    def test_get_status(self):
        self.cnc._busy = False
        s = self.cnc.get_status()
        self.assertEqual(s["status"], "Idle")
        self.cnc._busy = True
        s = self.cnc.get_status()
        self.assertEqual(s["status"], "Run")

    def test_xy_property(self):
        self.cnc._position = (10, 20, 30)
        # x/y use get_position which adds noise, so mock noise 0
        with mock.patch("plantimager.controller.scanner.dummy_cnc.random.uniform", return_value=0):
            self.assertEqual(self.cnc.x, 10)
            self.assertEqual(self.cnc.y, 20)
            self.assertEqual(self.cnc.z, 30)

    def test_stop(self):
        self.cnc._busy = True
        self.cnc.stop()
        self.assertFalse(self.cnc._busy)


if __name__ == "__main__":
    unittest.main()
