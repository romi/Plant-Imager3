"""
Manages the switching on and off of the various components of the scanner via the GPIO
"""
import os
import inspect
from enum import StrEnum
from typing import Callable
from functools import update_wrapper

import serial
from PySide6.QtCore import QObject, Signal, Slot, Property, QTimer
import gpio

from plantimager.commons.logging import create_logger
from plantimager.controller.scanner.grbl import CNC

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

class PowerManager(QObject):

    cnc: CNC | None
    cnc_ready = Signal(CNC)
    modeChanged = Signal(str)

    def __init__(self, warmup_period: int, parent=None):
        super().__init__(parent)
        gpio.setup(
            (GPIO_CNC_PIN, GPIO_LIGHTS_PIN, GPIO_GROWTH_LIGHTS_PIN),
            mode=gpio.OUT,
            initial=gpio.LOW
        )
        self.lights_power_on()
        self.cnc = None
        self.cnc_timer = QTimer(parent=self, singleShot=True, interval=60*5*1000)  # 5 minutes in ms
        self.cnc_timer.timeout.connect(self.cnc_power_off)
        self.cnc_connect_timer = QTimer(parent=self, singleShot=False, interval=1200)
        self.cnc_connect_timer.timeout.connect(self._cnc_connect)
        self._mode: PowerManagerMode = PowerManagerMode.AUTO
        self.modeChanged.connect(self._on_mode_changed)

    @Slot
    def _cnc_connect(self):
        try:
            if self.cnc is None: self.cnc = CNC()
        except serial.SerialException:
            return
        except RuntimeError:
            return
        else:
            activity_monitor(self.cnc, self.cnc_timer.start)
            self.cnc_connect_timer.stop()
            self.cnc_timer.start()
            self.cnc_ready.emit(self.cnc)

    @Slot
    def cnc_power_on(self):
        gpio.write(GPIO_CNC_PIN, True)
        self.cnc_connect_timer.start()

    @Slot
    def cnc_power_off(self):
        self.cnc.stop()
        self.cnc_timer.stop()
        self.cnc_timer.timeout.disconnect(slot=self.cnc_power_off)
        self.cnc = None
        gpio.write(GPIO_CNC_PIN, False)

    @Slot
    def lights_power_on(self):
        gpio.write(GPIO_LIGHTS_PIN, True)

    @Slot
    def lights_power_off(self):
        gpio.write(GPIO_LIGHTS_PIN, True)

    @Slot
    def glights_power_on(self):
        gpio.write(GPIO_GROWTH_LIGHTS_PIN, True)

    @Slot
    def glights_power_off(self):
        gpio.write(GPIO_GROWTH_LIGHTS_PIN, True)

    @Property(str, notify=modeChanged)
    def mode(self) -> PowerManagerMode:
        return self._mode
    @mode.setter
    def mode(self, mode: PowerManagerMode):
        if self._mode != mode:
            self._mode = mode
            self.modeChanged.emit(mode)

    @Slot(str)
    def _on_mode_changed(self, mode):
        if mode == PowerManagerMode.AUTO:
            self._resume_auto()
        elif mode == PowerManagerMode.SCAN:
            self._prepare_for_scan()
        else:
            logger.error(f"Unknown mode: {mode}")

    def _prepare_for_scan(self):
        self.cnc_power_on()
        self.lights_power_on()
        self.glights_power_off()

    def _resume_auto(self):
        self.cnc_power_on()
        self.lights_power_off()
        self.glights_power_on()

    def get_cnc(self):
        return self.cnc

    def set_light_policy(self, policy: dict):
        # For future automatic light management
        pass