"""
Manages the switching on and off of the various components of the scanner via the GPIO
"""
import os
import datetime
import inspect
import weakref
from enum import StrEnum
from typing import Callable
from functools import update_wrapper

import threading

import serial
from PySide6.QtCore import QObject, Signal, Slot, Property, QTimer
import gpio

from plantimager.commons.logging import create_logger
from plantimager.controller.scanner.dummy_cnc import DummyCNC
from plantimager.controller.scanner.grbl import CNC
from plantimager.controller.scanner.hal import AbstractCNC


def _stop_timers(*timers):
    for t in timers:
        if t is None:
            continue
        try:
            t.stop()
        except RuntimeError:
            pass


def _is_grbl_cnc(obj) -> bool:
    if obj is None:
        return False
    try:
        if isinstance(obj, CNC):
            return True
    except TypeError:
        pass
    return getattr(obj, "__class__", None).__name__ == "CNC"


def _allow_dummy_cnc(cli_allow: bool | None = None) -> bool:
    if cli_allow is not None:
        return cli_allow
    if os.getenv("PI3_ALLOW_DUMMY_CNC", "").lower() in ("1", "true", "yes"):
        return True
    return os.getenv("PI3_CNC_MODE", "real").lower() == "dummy"

logger = create_logger(__name__)

GPIO_CNC_PIN = int(os.getenv("GPIO_CNC_PIN", 17))
GPIO_LIGHTS_PIN = int(os.getenv("GPIO_LIGHTS_PIN", 27))
GPIO_GROWTH_LIGHTS_PIN = int(os.getenv("GPIO_GROWTH_LIGHTS_PIN", 22))


def activity_monitor(obj: object, callback: Callable[[], None]):
    """
    Wraps all methods of the given `obj` to trigger a specified callback before executing
    the original method.
    """
    for attr in dir(obj):
        try:
            got = getattr(obj, attr)
        except Exception:
            continue
        if not inspect.ismethod(got) and not inspect.isfunction(getattr(type(obj), attr, None)):
            continue
        original_method = got

        def _make_wrapper(orig):
            def f(*args, **kwargs):
                callback()
                return orig(*args, **kwargs)
            return update_wrapper(f, orig)

        setattr(obj, attr, _make_wrapper(original_method))
    return obj

class PowerManagerMode(StrEnum):
    SCAN = "scan"
    AUTO = "auto"  # automatic light schedule
    MANUAL = "manual"

class PowerManager(QObject):

    cnc: CNC | None
    cnc_ready = Signal(object)
    modeChanged = Signal(str)
    _cnc_result_signal = Signal(object)

    def __init__(self, warmup_period: float, parent=None, allow_dummy: bool | None = None):
        """
        Initialize the PowerManager instance.

        This class provides control over the power management system, including
        handling CNC connections, light toggling, and manual/automatic power
        management modes. It relies on GPIO for hardware interactions and provides
        timing mechanisms to manage various operations.

        Parameters
        ----------
        warmup_period : float
            The duration (in seconds) required for components to warm up before a
            specific operation.
        parent : optional
            The parent QObject for the timers created within the object. Defaults
            to ``None``.
        allow_dummy : bool | None
            Exclusive CNC backend: True → only DummyCNC, False/None → only GRBL CNC
            (env `PI3_ALLOW_DUMMY_CNC`/`PI3_CNC_MODE` or CLI overrides). None defers to env.

        Attributes
        ----------
        cnc : AbstractCNC or None
            Represents the CNC connection object. Defaults to ``None`` until an
            active connection is established.
        warmup_period : float
            The configured warmup period (in seconds).
        manual_mode_timer : QTimer
            A single-shot timer used to manage the manual mode timeout. It triggers
            after 5 minutes (converted to milliseconds).
        warmup_timer : QTimer
            A single-shot timer that powers up the scanner at ``next_scan - warmup_period``
            once a scan has been armed via :meth:`arm_for_scan`.
        cnc_connect_timer : QTimer
            A regular timer used to periodically attempt CNC reconnections. It is
            triggered every 1.2 seconds (1200 milliseconds).
        _mode : PowerManagerMode
            Tracks the current power management mode. Defaults to
            ``PowerManagerMode.AUTO``.
        _next_warmup_date : datetime.datetime or None
            Holds the date and time of the next warmup operation. Defaults to ``None``.
        """
        super().__init__(parent)
        gpio.setup(
            (GPIO_CNC_PIN, GPIO_LIGHTS_PIN, GPIO_GROWTH_LIGHTS_PIN),
            mode=gpio.OUT,
            initial=gpio.LOW
        )
        self._allow_dummy: bool = _allow_dummy_cnc(allow_dummy)
        self.cnc: AbstractCNC | None = None
        self._connecting: bool = False
        self._pending_cnc: AbstractCNC | None = None
        self.warmup_period: float = warmup_period
        self.manual_mode_timer = QTimer(parent=self, singleShot=True, interval=60 * 5 * 1000)  # 5 minutes in ms
        self.manual_mode_timer.timeout.connect(self._manual_mode_timeout)
        self.warmup_timer = QTimer(parent=self, singleShot=True)
        self.warmup_timer.timeout.connect(self._on_warmup_timer)
        self.cnc_connect_timer = QTimer(parent=self, singleShot=False, interval=1200)
        self.cnc_connect_timer.timeout.connect(self._dispatch_cnc_connect)
        self._cnc_result_timer = QTimer(parent=self, singleShot=True)
        self._cnc_result_timer.timeout.connect(self._on_cnc_connect_result_owned)
        self._cnc_result_signal.connect(self._on_cnc_connect_result)
        self.destroyed.connect(
            lambda _=None, _a=self.warmup_timer, _b=self.manual_mode_timer, _c=self.cnc_connect_timer, _d=self._cnc_result_timer: _stop_timers(_a, _b, _c, _d)
        )
        weakref.finalize(self, _stop_timers, self.warmup_timer, self.manual_mode_timer, self.cnc_connect_timer, self._cnc_result_timer)
        self._mode: PowerManagerMode = PowerManagerMode.AUTO
        self.modeChanged.connect(self._on_mode_changed)
        self._next_warmup_date: datetime.datetime | None = None
        self._resume_auto()
        self.cnc_connect_timer.start()
        self._dispatch_cnc_connect()

    def _create_cnc(self) -> AbstractCNC:
        if self._allow_dummy:
            return DummyCNC()
        return CNC()

    @Slot()
    def _dispatch_cnc_connect(self):
        if _is_grbl_cnc(self.cnc):
            return
        if self._allow_dummy and isinstance(self.cnc, DummyCNC):
            return
        if self._connecting:
            return
        if self.mode == PowerManagerMode.AUTO:  # No CNC on AUTO
            return
        self._connecting = True
        t = threading.Thread(target=self._do_cnc_connect_blocking, daemon=True)
        t.start()

    def _do_cnc_connect_blocking(self):
        cnc = None
        try:
            cnc = self._create_cnc()
        except (serial.SerialException, RuntimeError, Exception):
            cnc = None
        self._cnc_result_signal.emit(cnc)

    @Slot(object)
    def _on_cnc_connect_result(self, cnc):
        self._connecting = False
        if cnc is None:
            return
        if _is_grbl_cnc(self.cnc):
            return
        if self._allow_dummy and isinstance(self.cnc, DummyCNC):
            return
        self.cnc = cnc
        if self._mode == PowerManagerMode.MANUAL:
            activity_monitor(self.cnc, self.manual_mode_timer.start)
            self.manual_mode_timer.start()
        self.cnc_ready.emit(self.cnc)

    @Slot()
    def _on_cnc_connect_result_owned(self):
        cnc = getattr(self, "_pending_cnc", None)
        self._pending_cnc = None
        self._on_cnc_connect_result(cnc)


    @Slot()
    def _manual_mode_timeout(self):
        """
        Handles the timeout event for manual mode, switching modes based on
        the current time and warmup status.

        This method stops the manual mode timer and updates the power manager
        mode based on the presence of a warmup date and the time elapsed since
        `self._next_warmup_date`. Depending on the conditions met, the mode is
        set to either `SCAN` or `AUTO`.

        Notes
        -----
        - `self._next_warmup_date` must be a `datetime` object or `None`.
        - The `warmup_period` is used to determine mode-switching logic based
          on the time difference.
        - This private method is intended to be used internally within the system
          and is not part of a public API.

        Raises
        ------
        AttributeError
            If `self._next_warmup_date` or `self.warmup_period` is not properly
            initialized as expected.
        """
        self.manual_mode_timer.stop()
        if self.mode == PowerManagerMode.SCAN:
            return

        if self._next_warmup_date is None:
            self.mode = PowerManagerMode.AUTO
            return

        now = datetime.datetime.now(datetime.timezone.utc) if self._next_warmup_date and self._next_warmup_date.tzinfo else datetime.datetime.now()
        logger.debug(f"{self._next_warmup_date - now} -- {datetime.timedelta(seconds=self.warmup_period + 1.)}")
        if self._next_warmup_date - now < datetime.timedelta(seconds=self.warmup_period + 1.):
            self.mode = PowerManagerMode.SCAN
        else:
            self.mode = PowerManagerMode.AUTO


    def _cnc_power_on(self):
        gpio.write(GPIO_CNC_PIN, True)

    def _cnc_cleanup_complete(self):
        """Power down the CNC after its cleanup (after finalized)."""
        gpio.write(GPIO_CNC_PIN, False)

    def _cnc_power_off(self):
        if self.cnc is not None:
            self.cnc.stop()
            weakref.finalize(self.cnc, self._cnc_cleanup_complete)
            self.cnc = None
        else:
            gpio.write(GPIO_CNC_PIN, False)

    def _lights_power_on(self):
        gpio.write(GPIO_LIGHTS_PIN, True)

    def _lights_power_off(self):
        gpio.write(GPIO_LIGHTS_PIN, False)

    def _glights_power_on(self):
        gpio.write(GPIO_GROWTH_LIGHTS_PIN, True)

    def _glights_power_off(self):
        gpio.write(GPIO_GROWTH_LIGHTS_PIN, False)

    @Property(str, notify=modeChanged)
    def mode(self) -> PowerManagerMode:
        return self._mode
    @mode.setter
    def mode(self, mode: PowerManagerMode):
        if mode == PowerManagerMode.MANUAL and self._mode == PowerManagerMode.SCAN:
            logger.warning("Cannot transition to MANUAL mode from SCAN mode.")
            return
        if self._mode != mode:
            self._mode = mode
            self.modeChanged.emit(mode)

    @Slot(str)
    def _on_mode_changed(self, mode):
        if mode == PowerManagerMode.AUTO:
            self._resume_auto()
        elif mode == PowerManagerMode.SCAN:
            self._prepare_for_scan()
        elif mode == PowerManagerMode.MANUAL:
            self._prepare_for_scan()
        else:
            logger.error(f"Unknown mode: {mode}")

    def _apply_power(self, mode: PowerManagerMode):
        if mode == PowerManagerMode.AUTO:
            self._cnc_power_off()
            gpio.write(GPIO_LIGHTS_PIN, False)
            gpio.write(GPIO_GROWTH_LIGHTS_PIN, True)
        else:
            self._cnc_power_on()
            gpio.write(GPIO_LIGHTS_PIN, True)
            gpio.write(GPIO_GROWTH_LIGHTS_PIN, False)

    def _prepare_for_scan(self):
        self._apply_power(PowerManagerMode.SCAN)

    def prepare_for_scan(self):
        self._prepare_for_scan()

    def _resume_auto(self):
        self._apply_power(PowerManagerMode.AUTO)

    def resume_auto(self):
        self._resume_auto()

    def get_cnc(self):
        return self.cnc

    def set_light_policy(self, policy: dict):
        # For future automatic light management
        pass

    @Slot()
    def _on_warmup_timer(self):
        """Warm-up timer fired — power up the scanner for an imminent scan."""
        self.mode = PowerManagerMode.SCAN

    def arm_for_scan(self, next_scan_at: datetime.datetime, standby_threshold_sec: int):
        """
        Decide and schedule power so the scanner is ready for a scan at ``next_scan_at``.

        If the next scan is far enough away (``delta > standby_threshold_sec``) the
        manager returns to ``AUTO`` (growth lights, scanner idle) and arms its internal
        warm-up timer to power up ``warmup_period`` before the scan. Otherwise it stays
        in ``SCAN`` mode (already powered). This is the single power-policy decision;
        warnings are logged for each branch.

        Called by ``TimeLapse`` each time it re-arms for the next scheduled scan.

        Parameters
        ----------
        next_scan_at : datetime.datetime
            When the next scan will run (timezone-aware).
        standby_threshold_sec : int
            If the next scan is sooner than this many seconds, keep the scanner powered
            on in ``SCAN`` mode instead of dropping to ``AUTO``.
        """
        self.warmup_timer.stop()
        if next_scan_at.tzinfo is None:
            next_scan_at = next_scan_at.replace(tzinfo=datetime.timezone.utc)
        now = datetime.datetime.now(datetime.timezone.utc)
        delta = (next_scan_at - now).total_seconds()

        if delta > standby_threshold_sec:
            logger.info(
                f"Next scan in {delta:.0f}s (above standby threshold {standby_threshold_sec}s), "
                f"dropping to AUTO and warming up before the scan."
            )
            self._next_warmup_date = next_scan_at - datetime.timedelta(seconds=self.warmup_period)
            self.mode = PowerManagerMode.AUTO
            warmup_in = max(0, delta - self.warmup_period)
            self.warmup_timer.setInterval(int(warmup_in * 1000))
            self.warmup_timer.start()
        else:
            logger.info(
                f"Next scan in {delta:.0f}s (within standby threshold {standby_threshold_sec}s), "
                f"keeping scanner powered in SCAN mode."
            )
            if self._mode != PowerManagerMode.SCAN:
                self.mode = PowerManagerMode.SCAN
            else:
                self._prepare_for_scan()

    def try_set_mode(self, mode: PowerManagerMode) -> bool:
        self.mode = mode
        return self.mode == mode
