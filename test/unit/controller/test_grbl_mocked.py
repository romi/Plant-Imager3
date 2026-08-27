import unittest
from unittest import mock

try:
    import serial
    HAS_SERIAL = True
except ImportError:
    HAS_SERIAL = False


@unittest.skipUnless(HAS_SERIAL, "pyserial not installed")
class TestGRBLMocked(unittest.TestCase):
    def setUp(self):
        self.patcher_serial = mock.patch("plantimager.controller.scanner.grbl.serial.Serial")
        self.mock_serial_class = self.patcher_serial.start()
        self.addCleanup(self.patcher_serial.stop)

        self.patcher_ports = mock.patch("serial.tools.list_ports.comports")
        self.mock_comports = self.patcher_ports.start()
        self.addCleanup(self.patcher_ports.stop)

        mock_port = mock.MagicMock()
        mock_port.device = "/dev/ttyUSB0"
        self.mock_comports.return_value = [mock_port]

        self.mock_serial = mock.MagicMock()
        self.mock_serial.readline.return_value = b"ok\r\n"
        self.mock_serial.write = mock.MagicMock()
        self.mock_serial.flushInput = mock.MagicMock()
        self.mock_serial.flushOutput = mock.MagicMock()
        self.mock_serial.reset_input_buffer = mock.MagicMock()
        self.mock_serial.reset_output_buffer = mock.MagicMock()
        self.mock_serial.close = mock.MagicMock()
        self.mock_serial.is_open = True
        self.mock_serial.in_waiting = 0
        self.mock_serial_class.return_value = self.mock_serial

        self.sleep_patcher = mock.patch("plantimager.controller.scanner.grbl.time.sleep", return_value=None)
        self.sleep_patcher.start()
        self.addCleanup(self.sleep_patcher.stop)

        # Prevent weakref finalizer from hanging (it calls stop() which needs serial)
        self.patcher_finalize = mock.patch("plantimager.controller.scanner.grbl.finalize", return_value=mock.MagicMock(detach=mock.MagicMock()))
        self.patcher_finalize.start()
        self.addCleanup(self.patcher_finalize.stop)

        # Patch hardware-dependent methods to avoid serial during setUp/tearDown
        self.patcher_wait_immobile = mock.patch("plantimager.controller.scanner.grbl.CNC.wait_until_immobile", return_value=None)
        self.patcher_wait_immobile.start()
        self.addCleanup(self.patcher_wait_immobile.stop)
        self.patcher_get_pos = mock.patch("plantimager.controller.scanner.grbl.CNC.get_position", return_value=(20, 20, 45))
        self.patcher_get_pos.start()
        self.addCleanup(self.patcher_get_pos.stop)

        from plantimager.controller.scanner.grbl import CNC
        with mock.patch.object(CNC, "_find_and_connect_cnc", return_value=None):
            with mock.patch.object(CNC, "_start", return_value=None):
                self.cnc = CNC()
                self.mock_serial.is_open = True
                self.cnc.serial_port = self.mock_serial
                self.cnc._position = (20, 20, 45)
                self.cnc.has_started = True
                self.cnc.x_lims = (0, 740)
                self.cnc.y_lims = (0, 740)
                self.cnc._min_angle = 0
                self._orig_stop = CNC.stop

    def test_compute_move_time(self):
        self.cnc.grbl_settings = {"$110": 1000, "$111": 1000, "$112": 1000, "$120": 500, "$121": 500, "$122": 500}
        # get_position is globally mocked to (20,20,45), which is fine
        t = self.cnc.compute_move_time(100, 100, 0)
        self.assertIsInstance(t, float)
        self.assertGreaterEqual(t, 0)

    def test_check_move_raises(self):
        with self.assertRaises((ValueError, AssertionError)):
            self.cnc._check_move(800, 0, 0)

    def test_angle_helpers(self):
        from plantimager.controller.scanner.grbl import angle_min_travel, angle_min_travel_distance
        self.assertAlmostEqual(angle_min_travel(0, 90), 90)
        result = angle_min_travel(350, 10)
        self.assertIsInstance(result, (float, int))
        self.assertIsInstance(angle_min_travel_distance(0, 90), (float, int))

    def test_send_cmd(self):
        self.mock_serial.readline.return_value = b"ok\r\n"
        # Patch reset_input_buffer to avoid error
        res = self.cnc.send_cmd("G0 X10")
        self.mock_serial.write.assert_called()
        # send_cmd returns stripped response
        self.assertIsInstance(res, str)

    def test_stop_does_not_raise(self):
        # stop should not raise even with mock serial
        # Use original stop but patch its dependencies
        with mock.patch.object(self.cnc.__class__, "reset_pos", return_value=None):
            with mock.patch.object(self.cnc.__class__, "wait_until_immobile", return_value=None):
                try:
                    self._orig_stop(self.cnc)
                except Exception as e:
                    self.fail(f"stop raised {e}")

    def test_get_position_with_mocked_status(self):
        # Temporarily restore real get_position for this test
        self.patcher_get_pos.stop()
        self.patcher_wait_immobile.stop()
        try:
            self.mock_serial.readline.side_effect = [b"<Idle|MPos:10.000,20.000,30.000|FS:0,0>\r\n", b"ok\r\n"]
            x, y, z = self.cnc.get_position()
            self.assertAlmostEqual(x, 10)
            self.assertAlmostEqual(y, 20)
            self.assertAlmostEqual(z, 30)
        finally:
            self.patcher_get_pos.start()
            self.patcher_wait_immobile.start()


if __name__ == "__main__":
    unittest.main()
