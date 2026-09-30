# test_powermanager.py
import datetime
import unittest
from unittest.mock import MagicMock, patch

from plantimager.controller.scanner.powermanager import PowerManager, PowerManagerMode


class FakeTimer:
    """Minimal stand‑in for ``QTimer`` used by PowerManager."""

    def __init__(self, parent=None, singleShot=False, interval=0):
        self._single_shot = singleShot
        self._interval = interval
        self.timeout = MagicMock()
        self._started = False

    def setInterval(self, ms):
        self._interval = ms

    def interval(self):
        return self._interval

    def start(self):
        self._started = True

    def stop(self):
        self._started = False

    def isActive(self):
        return self._started


class PowerManagerTest(unittest.TestCase):
    def setUp(self):
        self.gpio_setup_patcher = patch('plantimager.controller.scanner.powermanager.gpio.setup')
        self.gpio_write_patcher = patch('plantimager.controller.scanner.powermanager.gpio.write')
        self.cnc_patcher = patch('plantimager.controller.scanner.powermanager.CNC')
        self.qtimer_patcher = patch('plantimager.controller.scanner.powermanager.QTimer', side_effect=FakeTimer)

        self.mock_gpio_setup = self.gpio_setup_patcher.start()
        self.mock_gpio_write = self.gpio_write_patcher.start()
        self.mock_cnc_class = self.cnc_patcher.start()
        self.mock_qtimer = self.qtimer_patcher.start()

        self.pm = PowerManager(warmup_period=60.0)

    def tearDown(self):
        patch.stopall()

    def test_initial_mode_is_auto(self):
        self.assertEqual(self.pm.mode, PowerManagerMode.AUTO)

    # ------------------------------------------------------------------
    # Transitions
    # ------------------------------------------------------------------
    def test_scan_to_manual_rejected(self):
        self.pm.cnc = MagicMock()
        assert self.pm.try_set_mode(PowerManagerMode.SCAN)
        self.assertFalse(self.pm.try_set_mode(PowerManagerMode.MANUAL))
        self.assertEqual(self.pm.mode, PowerManagerMode.SCAN)

    def test_auto_to_scan_goes_starting_then_commits_on_connect(self):
        # No CNC yet: entering SCAN must pass through STARTING while connecting.
        self.assertTrue(self.pm.try_set_mode(PowerManagerMode.SCAN))
        self.assertEqual(self.pm.mode, PowerManagerMode.STARTING)
        self.assertIsNone(self.pm.get_cnc())

        # The connect result commits to the pending target.
        cnc = MagicMock()
        self.pm._on_cnc_connect_result(cnc)
        self.assertEqual(self.pm.mode, PowerManagerMode.SCAN)
        self.assertIs(self.pm.get_cnc(), cnc)

    def test_connect_result_discarded_after_abort_to_auto(self):
        # Enter SCAN (STARTING, connect in flight) then abort back to AUTO.
        self.pm.try_set_mode(PowerManagerMode.SCAN)
        self.assertEqual(self.pm.mode, PowerManagerMode.STARTING)
        self.assertTrue(self.pm.try_set_mode(PowerManagerMode.AUTO))
        self.assertEqual(self.pm.mode, PowerManagerMode.AUTO)
        self.assertIsNone(self.pm.get_cnc())

        # A late connect result must not resurrect a live CNC into AUTO.
        cnc = MagicMock()
        self.pm._on_cnc_connect_result(cnc)
        self.assertEqual(self.pm.mode, PowerManagerMode.AUTO)
        self.assertIsNone(self.pm.get_cnc())
        cnc.stop.assert_called_once()

    def test_auto_to_manual_attach_activity_monitor(self):
        self.assertTrue(self.pm.try_set_mode(PowerManagerMode.MANUAL))
        self.assertEqual(self.pm.mode, PowerManagerMode.STARTING)
        cnc = MagicMock()
        self.pm._on_cnc_connect_result(cnc)
        self.assertEqual(self.pm.mode, PowerManagerMode.MANUAL)
        self.assertTrue(self.pm.manual_mode_timer.isActive())

    def test_powerdown_goes_finalizing_then_auto(self):
        self.pm.cnc = MagicMock()
        self.pm.try_set_mode(PowerManagerMode.SCAN)
        self.assertEqual(self.pm.mode, PowerManagerMode.SCAN)

        self.assertTrue(self.pm.try_set_mode(PowerManagerMode.AUTO))
        self.assertEqual(self.pm.mode, PowerManagerMode.FINALIZING)
        # Once the park/power-down completes, land in AUTO with no CNC.
        self.pm._on_powerdown_done()
        self.assertEqual(self.pm.mode, PowerManagerMode.AUTO)
        self.assertIsNone(self.pm.get_cnc())

    # ------------------------------------------------------------------
    # Manual-mode timeout (decided by the stored next-scan time)
    # ------------------------------------------------------------------
    def test_manual_timeout_no_next_scan_goes_auto(self):
        self.pm._mode = PowerManagerMode.MANUAL
        self.pm._next_scan_at = None
        self.pm._manual_mode_timeout()
        self.assertEqual(self.pm.mode, PowerManagerMode.AUTO)

    def test_manual_timeout_next_scan_soon_goes_scan(self):
        # Next scan within the standby threshold -> stay powered in SCAN.
        self.pm._mode = PowerManagerMode.MANUAL
        self.pm.cnc = MagicMock()
        self.pm._next_scan_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=10)
        self.pm._manual_mode_timeout()
        self.assertEqual(self.pm.mode, PowerManagerMode.SCAN)

    def test_manual_timeout_next_scan_far_goes_auto(self):
        # Next scan far enough -> drop to AUTO.
        self.pm._mode = PowerManagerMode.MANUAL
        self.pm.cnc = MagicMock()
        self.pm._next_scan_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=3600)
        self.pm._manual_mode_timeout()
        self.assertEqual(self.pm.mode, PowerManagerMode.FINALIZING)
        self.pm._on_powerdown_done()
        self.assertEqual(self.pm.mode, PowerManagerMode.AUTO)

    # ------------------------------------------------------------------
    # arm_for_scan scheduling
    # ------------------------------------------------------------------
    def test_arm_for_scan_far_arms_auto_and_warmup(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        next_scan_at = now + datetime.timedelta(seconds=3600)
        self.pm.arm_for_scan(next_scan_at, standby_threshold_sec=600)

        self.assertEqual(self.pm.mode, PowerManagerMode.AUTO)
        self.assertTrue(self.pm.warmup_timer.isActive())
        self.assertEqual(self.pm._next_warmup_date, next_scan_at - datetime.timedelta(seconds=60))

    def test_arm_for_scan_close_stays_scan(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        next_scan_at = now + datetime.timedelta(seconds=100)
        self.pm.cnc = MagicMock()
        self.pm.arm_for_scan(next_scan_at, standby_threshold_sec=600)

        self.assertEqual(self.pm.mode, PowerManagerMode.SCAN)
        self.assertFalse(self.pm.warmup_timer.isActive())

    def test_warmup_timer_timeout_powers_up(self):
        self.pm.cnc = MagicMock()
        self.pm._on_warmup_timer()
        self.assertEqual(self.pm.mode, PowerManagerMode.SCAN)


if __name__ == '__main__':
    unittest.main()
