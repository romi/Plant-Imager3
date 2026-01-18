"""
Handles the coordination and the scheduling of multiple scans through the TimeLapse class
"""
import importlib
import os
import re
import datetime
from enum import StrEnum
from typing import Any, Literal

from PySide6.QtCore import QObject, Signal, Property, QTimer, Slot

from plantimager.controller.camera.PiCameraComm import PiCameraComm
from plantimager.controller.scanner.grbl import CNC
from plantimager.controller.scanner.hal import AbstractCNC
from plantimager.controller.scanner.path import Path
from plantimager.controller.scanner.scan import Scan

TIMELAPSE_FILE_PATH = os.getenv("TIMELAPSE_FILE_PATH", "./plant-imager3")
TIMELAPSE_FILE_NAME = os.getenv("TIMELAPSE_FILE_NAME", "timelapse_storage.json")

DURATION_REGEXP = re.compile(
    r"(?:(?P<days>\d+)d)?\W?(?:(?P<hours>\d+)h)?\W?(?:(?P<minutes>\d+)m)?\W?(?P<seconds>\d+)s?")


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
    state: TimeLapseState
    cnc: AbstractCNC
    db_url: str
    path: Path
    cameras: list[PiCameraComm]

    def __init__(self, cnc: AbstractCNC, db_url: str, cameras: list[PiCameraComm], path: Path,
                 timelapse_name: str, config: dict[str, Any], power_manager, parent=None):
        super().__init__(parent)
        self.cnc = cnc
        self.db_url = db_url
        self.cameras = cameras
        self.path = path
        self.id = timelapse_name
        self.config = config

        # timelapse settings
        timelapse_config = self.config["timelapse"]
        assert timelapse_config["mode"] in TimeLapseMode, \
            f"Unrecognized mode, expected one of {[m.value for m in TimeLapseMode]}"

        self.warmup_sec = timelapse_config["warmup_period"]
        self.grace_period = timelapse_config["grace_period"]
        self.schedule_times = []

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
            self.schedule_times = [datetime.datetime.fromisoformat(datestring) for datestring in timelapse_config["dates"]]

        self.start_at = self.schedule_times[0]

        # Dynamically import and instantiate the path class
        path_module = importlib.import_module("plantimager.controller.scanner.path")
        path_cfg = config["ScanPath"]
        self.scan_path = getattr(path_module, path_cfg["class_name"])(**path_cfg["kwargs"])
        self.pathInfoChanged.emit(self.path_info)

        # Update progress tracking based on path length
        self._max_progress = len(self.scan_path)
        self.maxProgressChanged.emit(self._max_progress)

        # Store metadata for the scan
        self.dataset_metadata = config["Metadata"]["object"]  # Biological metadata
        self.hw_metadata = config["Metadata"]["hardware"]  # Hardware metadata

        # Configure cameras
        for camera in self.cameras:
            if camera.name in config:
                res = config[camera.name]["res_x"], config[camera.name]["res_y"]
                camera.resolution = res


    @Slot
    def prepare_for_scan(self):
        pass

    @Slot(int)
    def scan(self, id):
        time = self.schedule_times[id]
        scan = Scan(
            self.cnc, self.db_url, self.cameras, self.path, f"{self.id}_{time.isoformat()}", self.config, parent=self
        )
        scan.scan()

    @property
    def n_scans(self):
        return len(self.schedule_times)

