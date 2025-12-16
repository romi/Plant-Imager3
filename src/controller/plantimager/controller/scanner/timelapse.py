"""
Handles the coordination and the scheduling of multiple scans through the TimeLapse class
"""
import os
import time
from enum import StrEnum
from typing import Any, Literal

from PySide6.QtCore import QObject, Signal, Property, QTimer

from plantimager.controller.camera.PiCameraComm import PiCameraComm
from plantimager.controller.scanner.hal import AbstractCNC
from plantimager.controller.scanner.path import Path
from plantimager.controller.scanner.scan import Scan

TIMELAPSE_FILE_PATH = os.getenv("TIMELAPSE_FILE_PATH", "./plant-imager3")
TIMELAPSE_FILE_NAME = os.getenv("TIMELAPSE_FILE_NAME", "timelapse_storage.json")

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
    start_at: float | None  # epoch seconds, UTC
    end_at: float | None  # epoch seconds, UTC
    interval_sec: int | None
    schedule_times_utc: list[int] | None  # epoch seconds, UTC
    max_scans: int | None
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

        self.mode = TimeLapseMode(timelapse_config["mode"])
        if self.mode == TimeLapseMode.ONE_SHOT:
            self.start_at = time.time()
        elif self.mode == TimeLapseMode.INTERVAL:
            self.start_at = time.time()
