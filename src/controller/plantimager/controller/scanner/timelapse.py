"""
Handles the coordination and the scheduling of multiple scans through the TimeLapse class.

Call graph and state flow
-------------------------

State model (persisted via ``TimelapseStore``, ``IDLE`` = no file):

    IDLE(None) ──create──▶ SCHEDULED ──scan──▶ RUNNING ──ok──▶ SCHEDULED ──▶ COMPLETED
                              │                  │                    ▲
                              │                  └─fail──▶ FAILED ───┘
                              └─cancel──────────▶ CANCELLED

    ``PowerManager.mode`` (``SCAN``/``AUTO``) is displayed *alongside* the timelapse state
    in ``Scanner.qml`` — no combined ``WAITING``/``COOLDOWN`` state.

Timers vs methods
~~~~~~~~~~~~~~~~~
.. code-block:: text

    __init__
      ├─ _setup_timelapse_settings()          # builds schedule_times (UTC internally)
      │     ├─ ONE_SHOT:  [now (+warmup)]
      │     ├─ INTERVAL:  [start + k*interval]  interval = parse_duration() | int
      │     └─ FIXED_TIMES: [sorted ISO datetimes, naive→local tz→UTC]
      └─ _setup_next_scan_timer()  ──────────────────────────────────────────┐
                                                                             │
    _setup_next_scan_timer()  ◀──────────────────────────────────────────────┘
      ├─ next_idx >= len  → COMPLETED
      ├─ delta <= -grace  → skip, next_idx++, persist, recurse
      ├─ delta <=  grace  → QTimer.singleShot(0, _trigger_next_scan)
      └─ delta >   grace
           ├─ PowerManager.arm_for_scan(next_time, standby_threshold_sec)
           │     (PowerManager decides AUTO/SCAN + arms its own warm-up timer)
           └─ _next_scan_timer(delta) → SCHEDULED (persist)

    _trigger_next_scan()  ← QTimer timeout or singleShot
      ├─ scan(next_idx)  ──────────┐
      ├─ next_idx++ + persist      │
      └─ if done → COMPLETED else ─┘ → _setup_next_scan_timer()

    scan(index)  ← _trigger_next_scan
      ├─ validate index, delta = scheduled - now(UTC)
      ├─ delta >  grace  → re-arm timer (no sleep)
      ├─ delta <= -grace → skip (persist)
      └─ else
           ├─ state = RUNNING
           ├─ Scan(cnc=db_client, id=f"{id}--{slug(scheduled)}", scan_path).scan()
           ├─ state = SCHEDULED or FAILED (+ errorOccurred)
           └─ persist

    cnc_ready(cnc)  ← PowerManager.cnc_ready
      └─ if not terminal → SCHEDULED + _setup_next_scan_timer()

    cancel()  ← QML / RPC
      └─ stop timers → CANCELLED → persist → scanFinished

    Power owns only ``PowerManager``: the warm-up timer and the AUTO/SCAN
    decision live in ``PowerManager.arm_for_scan()``; ``TimeLapse`` merely
    informs it of the next scan time.

    _persist_state()  ← every state/next_idx mutation
      └─ TimelapseStore.from_timelapse(self).save()  (XDG, atomic mkstemp+fsync+replace)

    _slug_for_schedule(dt)  helper for deterministic PlantDB scan_id.
"""
import importlib
import os
import re
import datetime
from datetime import timezone
from enum import StrEnum
from typing import Any, Literal

from PySide6.QtCore import QObject, Signal, Property, QTimer, Slot

from plantimager.commons.logging import create_logger
from plantimager.controller.camera.PiCameraComm import PiCameraComm
from plantimager.controller.scanner.grbl import CNC
from plantimager.controller.scanner.hal import AbstractCNC
from plantimager.controller.scanner.path import Path
from plantimager.controller.scanner.powermanager import PowerManager
from plantimager.controller.scanner.scan import Scan
from plantdb.client.plantdb_client import PlantDBClient

logger = create_logger(__name__)

DURATION_REGEXP = re.compile(
    r"^\s*(?:(?P<days>\d+)\s*d)?\W*(?:(?P<hours>\d+)\s*h)?\W*(?:(?P<minutes>\d+)\s*m)?\W*(?:(?P<seconds>\d+)\s*s)?\s*$"
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
    if match and any(v is not None for v in match.groupdict().values()):
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
    SCHEDULED = "scheduled"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
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
    db_client: PlantDBClient | None
    path: Path
    cameras: list[PiCameraComm]

    power_manager: PowerManager

    stateChanged = Signal(str)
    progressChanged = Signal(int, int) # current progress, max progress
    errorOccurred = Signal(str)
    scanFinished = Signal()
    pathInfoChanged = Signal(str)

    def __init__(self, cnc: AbstractCNC, db_url: str, cameras: list[PiCameraComm], path: Path,
                 timelapse_name: str, config: dict[str, Any], power_manager: PowerManager, parent=None):
        super().__init__(parent)
        self.cnc = cnc
        self.db_url = db_url
        self.db_client = PlantDBClient(db_url) if db_url else None
        self.cameras = cameras
        self.path = path
        self.id = timelapse_name
        self.config = config
        self.power_manager = power_manager
        self.scans: list[Scan] = []
        self._state = TimeLapseState.SCHEDULED

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

        self._next_scan_timer = QTimer(self, singleShot=True)
        self._next_scan_timer.timeout.connect(self._trigger_next_scan)
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

        self.warmup_sec = int(timelapse_config.get("warmup_period", 30))
        self.grace_period = int(timelapse_config.get("grace_period", 120))
        self.standby_threshold_sec = int(timelapse_config.get("standby_threshold_sec", 600))
        self.light_policy = timelapse_config.get("light_policy", {})
        self.schedule_times = []
        self.current_idx = 0
        self.next_idx = 0

        self.mode = TimeLapseMode(timelapse_config["mode"])
        now_utc = datetime.datetime.now(timezone.utc)
        if self.mode == TimeLapseMode.ONE_SHOT:
            if isinstance(self.cnc, CNC):
                self.schedule_times.append(now_utc)
            else:
                self.schedule_times.append(now_utc + datetime.timedelta(seconds=self.warmup_sec))
        elif self.mode == TimeLapseMode.INTERVAL:
            if isinstance(self.cnc, CNC):
                self.start_at = now_utc
            else:
                self.start_at = now_utc + datetime.timedelta(seconds=self.warmup_sec)
            interval_raw = timelapse_config["interval"]
            if isinstance(interval_raw, int):
                interval = datetime.timedelta(seconds=interval_raw)
            else:
                interval = parse_duration(str(interval_raw))
            n_scans = int(timelapse_config["n_shots"])
            self.schedule_times = [self.start_at + interval * i for i in range(n_scans)]
        elif self.mode == TimeLapseMode.FIXED_TIMES:
            parsed = []
            local_tz = datetime.datetime.now().astimezone().tzinfo
            for datestring in timelapse_config["dates"]:
                dt = datetime.datetime.fromisoformat(datestring)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=local_tz)
                dt = dt.astimezone(timezone.utc)
                parsed.append(dt)
            self.schedule_times = sorted(parsed)

        self.start_at = self.schedule_times[0] if self.schedule_times else None


    def _slug_for_schedule(self, scheduled: datetime.datetime) -> str:
        """Deterministic, FSDB-safe slug for a scheduled time (UTC ISO, ``:``→``-``)."""
        iso = scheduled.astimezone(timezone.utc).isoformat(timespec="seconds")
        return iso.replace(":", "-").replace("+", "_")

    @Slot(int)
    def scan(self, index: int):
        """
        Executes the scan at ``schedule_times[index]`` (UTC, deterministic ``scan_id``).

        Grace/warmup is handled by ``_setup_next_scan_timer``; this method never
        blocks. If called early (``delta > grace``) it re-arms the timer; if
        ``delta <= -grace`` the scan is skipped per persistence policy (one
        dataset per time, ``skip`` without catch-up). Otherwise creates a
        ``Scan`` with ``f"{id}--{slug(scheduled)}"`` and runs it synchronously,
        transitioning ``SCHEDULED → RUNNING → SCHEDULED`` (or ``FAILED``).

        Parameters
        ----------
        index : int
            Index in ``schedule_times``; must equal ``next_idx``.

        Raises
        ------
        ValueError
            If ``index`` is out of range.
        """
        if index < 0 or index >= len(self.schedule_times):
            raise ValueError(f"Invalid scan index {index}")
        self.current_idx = index
        self.progressChanged.emit(self.current_idx, self._max_progress)

        scheduled = self.schedule_times[self.next_idx]
        now = datetime.datetime.now(timezone.utc)
        delta = (scheduled - now).total_seconds()

        if delta > self.grace_period:
            logger.warning(f"Woke up {delta:.1f}s early for scan {self.next_idx} at {scheduled.isoformat()}, re-arming timer.")
            self._setup_next_scan_timer()
            return

        if delta <= -self.grace_period:
            logger.warning(
                f"Scan {self.next_idx} planned at {scheduled.isoformat()} missed (now {now.isoformat()}, grace {self.grace_period}s). Skipping per policy."
            )
            self._persist_state()
            return

        cnc = self.power_manager.get_cnc() if self.power_manager else self.cnc
        if cnc is None:
            cnc = self.cnc
        db_client = self.db_client or PlantDBClient(self.db_url) if self.db_url else None
        scan_id = f"{self.id}--{self._slug_for_schedule(scheduled)}"
        scan_path = getattr(self, "scan_path", self.path)
        scan = Scan(cnc, db_client, self.cameras, scan_path, scan_id, self.config, parent=self)
        self.state = TimeLapseState.RUNNING
        try:
            scan.scan()
            self.scans.append(scan)
        except Exception as exc:
            logger.error(f"Scan {self.next_idx} {scan_id} failed: {exc}")
            self.scans.append(scan)
            self.state = TimeLapseState.FAILED
            self.errorOccurred.emit(str(exc))
            self._persist_state()
            raise
        finally:
            if self._state == TimeLapseState.RUNNING:
                self.state = TimeLapseState.SCHEDULED
        self._persist_state()

    @Slot()
    def _trigger_next_scan(self):
        """
        Initiates the scan at ``next_idx`` and advances the schedule.

        Called by ``_next_scan_timer`` or a zero-delay ``singleShot`` from
        ``_setup_next_scan_timer``. Wraps ``scan()`` (skipped scans do not
        raise), increments ``next_idx``, persists, and either completes
        (``COMPLETED`` + ``scanFinished``) or re-arms via
        ``_setup_next_scan_timer``.
        """
        try:
            self.scan(self.next_idx)
        except Exception:
            pass
        self.next_idx += 1
        self._persist_state()
        if self.next_idx >= len(self.schedule_times):
            self.state = TimeLapseState.COMPLETED
            self.scanFinished.emit()
            self._persist_state()
            self._next_scan_timer.stop()
        else:
            self._setup_next_scan_timer()

    @Slot(object)
    def cnc_ready(self, cnc):
        """PowerManager reports CNC connected; (re)arm schedule if not terminal."""
        self.cnc = cnc
        if self._state not in (TimeLapseState.COMPLETED, TimeLapseState.FAILED, TimeLapseState.CANCELLED):
            self.state = TimeLapseState.SCHEDULED
            self._setup_next_scan_timer()

    def _setup_next_scan_timer(self):
        """
        Arms ``_next_scan_timer`` for ``schedule_times[next_idx]`` and informs
        ``PowerManager`` of the next scan time.

        Handles ``skip`` for overdue entries (``delta <= -grace``), immediate
        dispatch when inside the grace window (``delta <= grace``), and power-aware
        scheduling otherwise. Power is delegated to ``PowerManager.arm_for_scan``
        (which decides AUTO/SCAN and arms its own warm-up timer); only the scan
        trigger timer lives here.
        """
        if self.next_idx >= len(self.schedule_times):
            self.state = TimeLapseState.COMPLETED
            return
        next_time = self.schedule_times[self.next_idx]
        if next_time.tzinfo is None:
            next_time = next_time.replace(tzinfo=timezone.utc)
        now = datetime.datetime.now(timezone.utc)
        delta = (next_time - now).total_seconds()

        if delta <= -self.grace_period:
            logger.warning(f"Scan {self.next_idx} already missed by {-delta:.1f}s, skipping.")
            self.next_idx += 1
            self._persist_state()
            if self.next_idx >= len(self.schedule_times):
                self.state = TimeLapseState.COMPLETED
                self.scanFinished.emit()
                return
            self._setup_next_scan_timer()
            return

        if delta <= self.grace_period:
            QTimer.singleShot(0, self._trigger_next_scan)
            return

        self._next_scan_timer.stop()

        if self.power_manager:
            self.power_manager.arm_for_scan(next_time, self.standby_threshold_sec)

        self._next_scan_timer.setInterval(int(delta * 1000))
        self._next_scan_timer.start()
        self.state = TimeLapseState.SCHEDULED
        self._persist_state()

    def cancel(self):
        """Cancels the timelapse, stops timers, persists ``CANCELLED``."""
        self._next_scan_timer.stop()
        self.state = TimeLapseState.CANCELLED
        self._persist_state()
        self.scanFinished.emit()

    def _persist_state(self):
        """Persists current state via ``TimelapseStore`` (atomic XDG save)."""
        try:
            from plantimager.controller.scanner.timelapse_store import TimelapseStore
            store = TimelapseStore.from_timelapse(self)
            store.save()
        except Exception as exc:
            logger.warning(f"Failed to persist timelapse state: {exc}")


    @Property(str, notify=pathInfoChanged)
    def path_info(self) -> str:
        """Human-readable description of the scan path for QML."""
        if not hasattr(self, "scan_path") or self.scan_path is None:
            return "No path configured"
        # avoid hard dependency on numpy for CustomPath
        try:
            from plantimager.controller.scanner.path import Circle, CalibrationPath2, CustomPath
        except Exception:
            return f"{type(self.scan_path).__name__}: {len(self.scan_path)} steps"
        if isinstance(self.scan_path, Circle):
            return f"{type(self.scan_path).__name__}: center {self.scan_path.center_x:g}, {self.scan_path.center_y:g}, radius {self.scan_path.radius:g} - {len(self.scan_path)} steps"
        if isinstance(self.scan_path, CalibrationPath2):
            return f"{type(self.scan_path).__name__}: center {self.scan_path.center_x:g}, {self.scan_path.center_y:g}, radius {self.scan_path.radius:g} - {len(self.scan_path)} steps"
        if isinstance(self.scan_path, CustomPath):
            try:
                import numpy as np
                pts = np.array(self.scan_path)
                x, y = float(np.mean(pts[:, 0])), float(np.mean(pts[:, 1]))
                return f"{type(self.scan_path).__name__}: center {x:g}, {y:g} - {len(self.scan_path)} steps"
            except Exception:
                return f"{type(self.scan_path).__name__}: {len(self.scan_path)} steps"
        return f"{type(self.scan_path).__name__}: {len(self.scan_path)} steps"

    @property
    def n_scans(self):
        return len(self.schedule_times)

    @Property(str, notify=stateChanged)
    def state(self):
        """Current timelapse state, QML-visible via ``stateChanged``.

        Separate from ``PowerManager.mode`` which is displayed alongside
        in ``Scanner.qml``.
        """
        return self._state

    @state.setter
    def state(self, value):
        if isinstance(value, str):
            value = TimeLapseState(value)
        if self._state != value:
            self._state = value
            self.stateChanged.emit(value.value if isinstance(value, TimeLapseState) else str(value))

    @Property(int, notify=progressChanged)
    def progress(self):
        return self.current_idx

    @Property(int, notify=progressChanged)
    def max_progress(self):
        return self._max_progress
