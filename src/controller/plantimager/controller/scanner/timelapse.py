"""
Handles the coordination and the scheduling of multiple scans through the TimeLapse class
"""
import importlib
import os
import re
import datetime
import time
from enum import StrEnum
from typing import Any, Literal

from PySide6.QtCore import QObject, Signal, Property, QTimer, Slot

from plantimager.commons.logging import create_logger
from plantimager.controller.camera.PiCameraComm import PiCameraComm
from plantimager.controller.scanner.grbl import CNC
from plantimager.controller.scanner.hal import AbstractCNC
from plantimager.controller.scanner.path import Path
from plantimager.controller.scanner.powermanager import PowerManager, PowerManagerMode
from plantimager.controller.scanner.scan import Scan

TIMELAPSE_FILE_PATH = os.getenv("TIMELAPSE_FILE_PATH", "./plant-imager3")
TIMELAPSE_FILE_NAME = os.getenv("TIMELAPSE_FILE_NAME", "timelapse_storage.json")

logger = create_logger(__name__)

DURATION_REGEXP = re.compile(
    r"(?:(?P<days>\d+)d)?\W?(?:(?P<hours>\d+)h)?\W?(?:(?P<minutes>\d+)m)?\W?(?P<seconds>\d+)s?"
)


def parse_duration(duration_string, /, duration_regexp: re.Pattern = DURATION_REGEXP):
    """
    Parses a duration string and converts it into a `datetime.timedelta` object.

    This function takes a duration string in a specific format and uses a regular expression
    pattern to extract the components (e.g., days, hours, minutes, seconds). The parsed
    components are then converted into a `datetime.timedelta` object for further manipulation.

    Parameters
    ----------
    duration_string : str
        A string representing the duration in the format `Xd-Xh-Xm-Xs` (e.g., `2d-3h-1m-0s`),
        where `X` represents integers for days, hours, minutes, and seconds. Each component
        may be omitted if not needed (e.g., `3h-20m`).
    duration_regexp : re.Pattern, optional
        A compiled regular expression pattern used to match and extract components from
        `duration_string`. Defaults to `DURATION_REGEXP`.
        Group Names must be keyword arguments of the datetime.timedelta objects constructor.
        (e.g., days, hours, minutes, seconds)

    Returns
    -------
    datetime.timedelta
        A `datetime.timedelta` object representing the parsed time duration.

    Raises
    ------
    RuntimeError
        If `duration_string` does not match the expected format defined by `duration_regexp`.

    Notes
    -----
    - The `DURATION_REGEXP` constant, if used as the default `duration_regexp`, must be
      pre-defined in the module. It should include named capturing groups for days (`d`),
      hours (`h`), minutes (`m`), and seconds (`s`).

    Examples
    --------
    >>> import re
    >>> import datetime
    >>> DURATION_REGEXP = re.compile(r'(?:(?P<days>\d+)d)?\W?(?:(?P<hours>\d+)h)?\W?(?:(?P<minutes>\d+)m)?\W?(?P<seconds>\d+)s?')
    >>> parse_duration("2d-3h-1m-0s", duration_regexp=DURATION_REGEXP)
    datetime.timedelta(days=2, seconds=10980)

    >>> parse_duration("3h-20m", duration_regexp=DURATION_REGEXP)
    datetime.timedelta(seconds=12000)

    >>> parse_duration("invalid-string", duration_regexp=DURATION_REGEXP)
    Traceback (most recent call last):
    ...
    RuntimeError: Failed to parse duration_string: invalid-string. Did not follow the format 2d-3h-1m-0s
    """
    match = duration_regexp.match(duration_string)
    if match:
        return datetime.timedelta(**{
            k: int(v) if v else 0 for k, v in match.groupdict().items()
        })
    else:
        raise RuntimeError(f"Failed to parse duration_string: {duration_string}. Did not follow the format 2d-3h-1m-0s")


class TimeLapseMode(StrEnum):
    INTERVAL = "interval"
    FIXED_TIMES = "fixed_times"
    ONE_SHOT = "one_shot"

class TimeLapseState(StrEnum):
    IDLE = "idle"
    ARMING = "arming"
    WAITING = "waiting"
    SCANNING = "scanning"
    STANDBY = "standby"
    COOLDOWN = "cooldown"
    COMPLETED = "completed"
    ERROR = "error"
    CANCELLED = "cancelled"

class TimeLapse(QObject):

    id: str
    mode: TimeLapseMode
    start_at: datetime.datetime | None
    end_at: float | None
    interval: datetime.timedelta | None
    schedule_times: list[datetime.datetime] | None
    n_scans: int | None
    warmup_sec: int  # lights/cnc warm-up
    standby_threshold_sec: int  # stay-on cutoff to next scan
    grace_period: int  # period where late starts are accepted
    light_policy: dict  # lights mode
    scans: list[Scan]
    next_idx: int  # index of next-scheduled scan
    current_idx: int
    _state: TimeLapseState
    cnc: AbstractCNC
    db_url: str
    path: Path
    cameras: list[PiCameraComm]

    power_manager: PowerManager

    stateChanged = Signal(str)
    progressChanged = Signal(int, int) # current progress, max progress
    errorOccurred = Signal(str)
    scanFinished = Signal()

    def __init__(self, cnc: AbstractCNC, db_url: str, cameras: list[PiCameraComm], path: Path,
                 timelapse_name: str, config: dict[str, Any], power_manager: PowerManager, parent=None):
        super().__init__(parent)
        self.cnc = cnc
        self.db_url = db_url
        self.cameras = cameras
        self.path = path
        self.id = timelapse_name
        self.config = config

        # timelapse settings
        self._setup_timelapse_settings()

        # Dynamically import and instantiate the path class
        path_module = importlib.import_module("plantimager.controller.scanner.path")
        path_cfg = config["ScanPath"]
        self.scan_path = getattr(path_module, path_cfg["class_name"])(**path_cfg["kwargs"])
        self.pathInfoChanged.emit(self.path_info)

        # Update progress tracking based on path length
        self._max_progress = len(self.scan_path)
        self.progressChanged.emit(self.current_idx, self._max_progress)

        # Store metadata for the scan
        self.dataset_metadata = config["Metadata"]["object"]  # Biological metadata
        self.hw_metadata = config["Metadata"]["hardware"]  # Hardware metadata

        # Configure cameras
        for camera in self.cameras:
            if camera.name in config:
                res = config[camera.name]["res_x"], config[camera.name]["res_y"]
                camera.resolution = res

        self._state = TimeLapseState.STANDBY
        self.power_manager = power_manager

        self._next_scan_timer = QTimer(self, singleShot=True)
        self._next_scan_timer.timeout.connect(self._trigger_next_scan)
        self._powerup_timer = QTimer(self, singleShot=True)
        self._powerup_timer.timeout.connect(power_manager.prepare_for_scan)
        self._setup_next_scan_timer()

    def _setup_timelapse_settings(self):
        """
        Configures and initializes settings for a timelapse operation.

        This method sets up the internal state and scheduling parameters for
        managing a timelapse capture, based on the configuration provided
        in `self.config`. It supports multiple modes of operation, such as
        `ONE_SHOT`, `INTERVAL`, and `FIXED_TIMES`, which determine the manner
        in which photos or data are scheduled and captured.

        Parameters
        ----------
        None

        Other Parameters
        ----------------
        None

        Returns
        -------
        None

        Raises
        ------
        AssertionError
            If `timelapse_config["mode"]` is not a valid `TimeLapseMode`.
        KeyError
            If required keys are missing in the `self.config["timelapse"]` dictionary.

        Notes
        -----
        - The `TimeLapseMode` enum is used to determine the available modes. The
          valid modes are checked using an assertion.
        - For the `ONE_SHOT` mode:
          - If the `self.cnc` attribute is an instance of `CNC`, the scheduling
            starts immediately.
          - Otherwise, it incorporates a warm-up period before scheduling starts.
        - For the `INTERVAL` mode:
          - The interval between timelapse captures is derived from the `"interval"`
            configuration, parsed using the `parse_duration` utility.
          - The number of shots (`"n_shots"`) determines the total number of
            scheduled captures.
        - For the `FIXED_TIMES` mode:
          - Timelapse captures occur at specific dates and times, as defined by the
            `"dates"` configuration.
        - The `self.start_at` attribute is set to the first scheduled capture time
          in all modes.

        See Also
        --------
        TimeLapseMode : Enum specifying available timelapse modes.
        parse_duration : Utility function to parse duration strings.
        """
        timelapse_config = self.config["timelapse"]
        assert timelapse_config["mode"] in TimeLapseMode, \
            f"Unrecognized mode, expected one of {[m.value for m in TimeLapseMode]}"

        self.warmup_sec = timelapse_config["warmup_period"]
        self.grace_period = timelapse_config["grace_period"]
        self.schedule_times = []
        self.current_idx = 0
        self.next_idx = 0

        self.mode = TimeLapseMode(timelapse_config["mode"])
        if self.mode == TimeLapseMode.ONE_SHOT:
            if isinstance(self.cnc, CNC):
                self.schedule_times.append(datetime.datetime.now())
            else:
                self.schedule_times.append(datetime.datetime.now() + datetime.timedelta(seconds=self.warmup_sec))
        elif self.mode == TimeLapseMode.INTERVAL:
            if isinstance(self.cnc, CNC):
                self.start_at = datetime.datetime.now()
            else:
                self.start_at = datetime.datetime.now() + datetime.timedelta(seconds=self.warmup_sec)
            interval_str = timelapse_config["interval"]
            interval = parse_duration(interval_str)
            n_scans = int(timelapse_config["n_shots"])
            self.schedule_times = [self.start_at + interval * i for i in range(n_scans)]
        elif self.mode == TimeLapseMode.FIXED_TIMES:
            self.schedule_times = [datetime.datetime.fromisoformat(datestring) for datestring in
                                   timelapse_config["dates"]]

        self.start_at = self.schedule_times[0]


    @Slot(int)
    def scan(self, index: int):
        """
        Executes a scheduled scan based on the provided index.

        This method updates the current scanning index and triggers the `progressChanged` signal.
        It determines the interval to the next scheduled time and either waits for the appropriate
        time, proceeds with the scan, or skips it if the grace period has been violated.

        Parameters
        ----------
        index : int
            The index of the scan to execute.

        Raises
        ------
        ValueError
            If the provided `index` is invalid.

        Notes
        -----
        - The method computes the interval between the current time and the next scheduled time.
          If the interval is greater than the `grace_period`, the method pauses execution until
          the scheduled time.
        - If the time has already passed and exceeded the grace period, the scan is skipped.
        - Sleeps the thread until the scheduled time arrives if the scan occurs too early.

        See Also
        --------
        Scan.scan : Executes the actual scan process.

        Examples
        --------
        Suppose you have a scheduler with predefined `schedule_times` and `grace_period`, you can
        invoke the following method by supplying a valid scan index:

        >>> scheduler.scan(2)
        """
        self.current_idx = index
        self.progressChanged.emit(self.current_idx, self.max_progress)

        next_time = self.schedule_times[self.next_idx]
        current_time = datetime.datetime.now()
        interval = next_time - current_time
        if interval.total_seconds() > self.grace_period:
            logger.warning("Woke up too early, sleeping until time.")
            time.sleep(interval.total_seconds())
        elif interval.total_seconds() <= -self.grace_period:
            # date and grace period have passed
            logger.warning(
                f"Scan {self.next_idx} planned at {next_time.isoformat()} timed out at {current_time.isoformat()}. Skipping."
            )
            return
        scan = Scan(
            self.power_manager.cnc, self.db_url, self.cameras, self.path, f"{self.id}_{current_time.isoformat()}", self.config, parent=self
        )
        scan.scan()

    @Slot()
    def _trigger_next_scan(self):
        """
        Initiates the next scan in the scheduled timelapse sequence.

        This method triggers a scan for the index specified by `next_idx`, updates
        the index for the subsequent scan, and determines whether the timelapse sequence
        is complete. If the timelapse is finished, the state is updated to
        `TimeLapseState.COMPLETED`, and the `scanFinished` signal is emitted. Otherwise,
        it sets up a timer for the next scan.
        """
        self.scan(self.next_idx)
        self.next_idx += 1

        # check if the timelapse is completed
        if self.next_idx >= len(self.schedule_times):
            self.state = TimeLapseState.COMPLETED
            self.scanFinished.emit()
        else:
            self._setup_next_scan_timer()

    @Slot()
    def _powerup(self):
        self.power_manager.mode = PowerManagerMode.SCAN

    @Slot(object)
    def cnc_ready(self, cnc):
        self.cnc = cnc
        self.state = TimeLapseState.STANDBY

    def _setup_next_scan_timer(self):
        """Sets up a timer for the next scheduled scan."""
        next_time = self.schedule_times[self.next_idx]
        current_time = datetime.datetime.now()
        interval = next_time - current_time
        if interval.total_seconds() > self.standby_threshold_sec:
            self._powerup_timer.setInterval(int((interval.total_seconds() - self.warmup_sec) * 1000))
            self._powerup_timer.start()
            self._next_scan_timer.setInterval(int(interval.total_seconds() * 1000))
            self._next_scan_timer.start()
            self.power_manager.mode = PowerManagerMode.AUTO
            self.state = TimeLapseState.COOLDOWN
        elif interval.total_seconds() > self.grace_period:
            self._next_scan_timer.setInterval(int(interval.total_seconds() * 1000))
            self._next_scan_timer.start()
            self.state = TimeLapseState.WAITING
        else:
            self._trigger_next_scan()


    @property
    def n_scans(self):
        return len(self.schedule_times)

    @Property(str, notify=progressChanged)
    def state(self):
        return self._state
    @state.setter
    def state(self, value):
        if self._state != value:
            self._state = value
            self.progressChanged.emit(self._state)

    @Property(int, notify=progressChanged)
    def progress(self):
        return self.current_idx

    @Property(int, notify=progressChanged)
    def max_progress(self):
        return self._max_progress
