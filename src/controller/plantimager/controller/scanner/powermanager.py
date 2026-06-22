"""
Manages the switching on and off of the various components of the scanner via the GPIO
"""
import os
import datetime
import inspect
from enum import StrEnum
from typing import Callable
from functools import update_wrapper

import serial
from PySide6.QtCore import QObject, Signal, Slot, Property, QTimer
import gpio

from plantimager.commons.logging import create_logger
from plantimager.controller.scanner.grbl import CNC
from plantimager.controller.scanner.hal import AbstractCNC

logger = create_logger(__name__)

GPIO_CNC_PIN = int(os.getenv("GPIO_CNC_PIN", 17))
GPIO_LIGHTS_PIN = int(os.getenv("GPIO_LIGHTS_PIN", 27))
GPIO_GROWTH_LIGHTS_PIN = int(os.getenv("GPIO_GROWTH_LIGHTS_PIN", 22))


def activity_monitor(obj: object, callback: Callable[[], None]):
    """
    Wraps all methods of the given `obj` to trigger a specified callback before executing
    the original method. This is useful for monitoring or observing object activity, such
    as logging or tracking method calls.

    This function dynamically intercepts all methods of the input `obj` object and wraps
    them such that the `callback` function is executed prior to the method's actual
    invocation. The wrapped methods retain their arguments, return values, and
    attributes.

    Parameters
    ----------
    obj : object
        The target object whose methods are to be monitored. All methods of this object
        will be wrapped to include the `callback`.
    callback : Callable[[], None]
        A zero-argument callable that is executed before any method of `obj` is invoked.

    Returns
    -------
    object
        The original `obj`, with its methods wrapped to call `callback` before
        execution.

    Raises
    ------
    AttributeError
        If an attribute of `obj` cannot be fetched or set while wrapping methods.

    Notes
    -----
    The `callback` function is expected to handle side-effects or monitoring concerns
    (e.g., logging, notifications). This function does not guarantee thread safety if
    the `obj`'s methods are accessed simultaneously from multiple threads.

    See Also
    --------
    functools.update_wrapper : Used internally to update the wrapped function's
        metadata to match the original function.

    Examples
    --------
    >>> from functools import partial
    >>> class MyClass:
    ...     def method(self, x):
    ...         print(f'Method called with {x}')
    >>> obj = MyClass()
    >>> def my_callback():
    ...     print('Callback triggered!')
    >>> monitored_obj = activity_monitor(obj, my_callback)
    >>> monitored_obj.method(10)
    Callback triggered!
    Method called with 10
    """
    for attr in dir(obj):
        if inspect.ismethod(getattr(obj, attr)):
            original_method = getattr(obj, attr)

            def f(*args, **kwargs):
                callback()
                original_method(*args, **kwargs)
            setattr(obj, attr, update_wrapper(f, original_method))
    return obj

class PowerManagerMode(StrEnum):
    SCAN = "scan"
    AUTO = "auto"  # automatic light schedule
    MANUAL = "manual"

class PowerManager(QObject):

    cnc: CNC | None
    cnc_ready = Signal(CNC)
    modeChanged = Signal(str)

    def __init__(self, warmup_period: float, parent=None):
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
        self.cnc: AbstractCNC | None = None
        self.warmup_period: float = warmup_period
        self.manual_mode_timer = QTimer(parent=self, singleShot=True, interval=60 * 5 * 1000)  # 5 minutes in ms
        self.manual_mode_timer.timeout.connect(self._manual_mode_timeout)
        self.cnc_connect_timer = QTimer(parent=self, singleShot=False, interval=1200)
        self.cnc_connect_timer.timeout.connect(self._cnc_connect)
        self._mode: PowerManagerMode = PowerManagerMode.AUTO
        self.modeChanged.connect(self._on_mode_changed)
        self._next_warmup_date: datetime.datetime | None = None
        self._resume_auto()

    @Slot()
    def _cnc_connect(self):
        """
        Establishes a connection to the CNC machine and configures its operational state.

        This method initializes and connects to a CNC machine instance if it is not
        already connected. It handles exceptions related to communication issues
        during the initialization process, ensures timers associated with CNC modes
        are started, and emits a signal indicating the CNC machine is ready.

        Notes
        -----
        - If an instance of the CNC machine (`self.cnc`) is already initialized, this method
          does not reinitialize it.

        See Also
        --------
        activity_monitor : Monitors CNC activity for logging and synchronization purposes.

        """
        if isinstance(self.cnc, CNC):
            self.cnc_connect_timer.stop()
            return

        try:
            if self.cnc is None: self.cnc = CNC()
        except serial.SerialException:
            return
        except RuntimeError:
            return

        self.cnc_connect_timer.stop()
        if self._mode == PowerManagerMode.MANUAL:
            activity_monitor(self.cnc, self.manual_mode_timer.start)
            self.manual_mode_timer.start()
        self.cnc_ready.emit(self.cnc)

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

        if self._next_warmup_date is None:
            self.mode = PowerManagerMode.AUTO
            return

        now = datetime.datetime.now()
        logger.debug(f"{self._next_warmup_date - now} -- {datetime.timedelta(seconds=self.warmup_period + 1.)}")
        if self._next_warmup_date - now < datetime.timedelta(seconds=self.warmup_period + 1.):
            self.mode = PowerManagerMode.SCAN
        else:
            self.mode = PowerManagerMode.AUTO


    def _cnc_power_on(self):
        gpio.write(GPIO_CNC_PIN, True)

    def _cnc_power_off(self):
        self.cnc.stop()
        self.cnc = None
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

    def _prepare_for_scan(self):
        self._cnc_power_on()
        self._lights_power_on()
        self._glights_power_off()

    def _resume_auto(self):
        self._cnc_power_on()
        self._lights_power_off()
        self._glights_power_on()

    def get_cnc(self):
        return self.cnc

    def set_light_policy(self, policy: dict):
        # For future automatic light management
        pass

    def set_next_auto_warmup_date(self, date: datetime.datetime):
        self._next_warmup_date = date