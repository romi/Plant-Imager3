# test_powermanager.py
import unittest
from unittest.mock import MagicMock, patch

# The PowerManager implementation is assumed to be importable from a module
# named ``power_manager`` that resides in the same package as this test file.
# Adjust the import if the actual module path differs.
from plantimager.controller.scanner.powermanager import PowerManager, PowerManagerMode


class FakeTimer:
    """
    Minimal stand‑in for ``QTimer`` used by PowerManager.
    Only the parts accessed by the tests are implemented.
    """
    def __init__(self, parent=None, singleShot=False, interval=0):
        self._single_shot = singleShot
        self.interval = interval
        self.timeout = MagicMock()
        self._started = False

    def start(self):
        self._started = True

    def stop(self):
        self._started = False

    def isActive(self):
        return self._started


class PowerManagerTest(unittest.TestCase):
    def setUp(self):
        # Patch external dependencies before creating a PowerManager instance
        self.gpio_setup_patcher = patch('plantimager.controller.scanner.powermanager.gpio.setup')
        self.gpio_write_patcher = patch('plantimager.controller.scanner.powermanager.gpio.write')
        self.cnc_patcher = patch('plantimager.controller.scanner.powermanager.CNC')
        self.qtimer_patcher = patch('plantimager.controller.scanner.powermanager.QTimer', side_effect=FakeTimer)

        self.mock_gpio_setup = self.gpio_setup_patcher.start()
        self.mock_gpio_write = self.gpio_write_patcher.start()
        self.mock_cnc_class = self.cnc_patcher.start()
        self.mock_qtimer = self.qtimer_patcher.start()

        # Use a small warm‑up period to keep the maths straightforward
        self.pm = PowerManager(warmup_period=60.0)   # 60 seconds

    def tearDown(self):
        patch.stopall()

    def test_initial_mode_is_auto(self):
        self.assertEqual(self.pm.mode, PowerManagerMode.AUTO)

    def test_mode_change_calls_correct_helpers(self):
        # Replace the private helpers with mocks so we can assert they are called
        self.pm._prepare_for_scan = MagicMock()
        self.pm._resume_auto = MagicMock()

        # Switch to SCAN – should call _prepare_for_scan
        self.pm.mode = PowerManagerMode.SCAN
        self.pm._prepare_for_scan.assert_called_once()
        self.pm._resume_auto.assert_not_called()
        self.assertEqual(self.pm.mode, PowerManagerMode.SCAN)

        # Switch to AUTO – should call _resume_auto
        self.pm._prepare_for_scan.reset_mock()
        self.pm.mode = PowerManagerMode.AUTO
        self.pm._resume_auto.assert_called_once()
        self.pm._prepare_for_scan.assert_not_called()
        self.assertEqual(self.pm.mode, PowerManagerMode.AUTO)

        # Switch to MANUAL – according to _on_mode_changed this also uses _prepare_for_scan
        self.pm._resume_auto.reset_mock()
        self.pm.mode = PowerManagerMode.MANUAL
        self.pm._prepare_for_scan.assert_called_once()
        self.pm._resume_auto.assert_not_called()
        self.assertEqual(self.pm.mode, PowerManagerMode.MANUAL)

    def test_manual_mode_timeout_no_warmup_date_switches_to_auto(self):
        # Put the manager in MANUAL mode and ensure timer stop is observed
        self.pm.mode = PowerManagerMode.MANUAL
        self.pm.manual_mode_timer.stop = MagicMock()

        # No warm‑up date -> should go to AUTO
        self.pm._next_warmup_date = None
        self.pm._manual_mode_timeout()

        self.pm.manual_mode_timer.stop.assert_called_once()
        self.assertEqual(self.pm.mode, PowerManagerMode.AUTO)

    def test_manual_mode_timeout_warmup_soon_switches_to_scan(self):
        import datetime

        # Current time
        now = datetime.datetime.now()
        # Warm‑up should happen in 10 seconds
        self.pm._next_warmup_date = now + datetime.timedelta(seconds=10)

        self.pm.mode = PowerManagerMode.MANUAL
        self.pm.manual_mode_timer.stop = MagicMock()
        self.pm._manual_mode_timeout()

        self.pm.manual_mode_timer.stop.assert_called_once()
        self.assertEqual(self.pm.mode, PowerManagerMode.SCAN)


    def test_manual_mode_timeout_elapsed_warmup_switches_to_auto(self):
        import datetime

        # Current time
        now = datetime.datetime.now()
        # Warm‑up will happen in 120 seconds
        self.pm._next_warmup_date = now + datetime.timedelta(seconds=120)

        self.pm.mode = PowerManagerMode.MANUAL
        self.pm.manual_mode_timer.stop = MagicMock()
        self.pm._manual_mode_timeout()

        self.pm.manual_mode_timer.stop.assert_called_once()
        self.assertEqual(self.pm.mode, PowerManagerMode.AUTO)


if __name__ == '__main__':
    unittest.main()