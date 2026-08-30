# !/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Scanner Module for Plant Imaging Systems.

``Scanner`` is the UI/RPC bridge for the plant imaging system. It owns the
device state (CNC, cameras, database connection) and the single shared
``PowerManager``, and delegates the actual work to the specialised classes:

* :class:`Scan`  — one 3D capture pass (path traversal, capture, upload).
* :class:`TimeLapse` — scheduling a *series* of scans over time (``interval``,
  ``fixed_times`` or a single pass). ``Scanner.timelapse`` is the active job.
* :class:`PowerManager` — GPIO power and warm-up/power-on decisions.

``Scanner`` itself does **not** run the scan loop anymore; it forwards signals
and methods to/from the active ``Scan``/``TimeLapse`` so that QML and the RPC
server keep a stable, bridge-only interface.

Key Features:
- Bridge for QML integration (properties/signals) and the RPC controller
- Owns one shared :class:`PowerManager` and the active :class:`TimeLapse`
- ``run_scan`` delegates to a single :class:`Scan` (custom dataset id)
- Fallback to dummy hardware when physical hardware is unavailable

Usage Examples:
```python
>>> from plantimager.controller.scanner.scanner import Scanner
>>> scanner = Scanner()
>>> scanner.set_db_url("http://localhost:5000")
>>> scanner.configure_scan(config_dict)  # Configure scan parameters
>>> scanner.set_scan_id("plant_scan_001")  # Set scan identifier
>>> scanner.run_scan()  # Start a single scanning operation
```
"""

import importlib
import time
import datetime
from datetime import timezone
from typing import Literal

import numpy as np
from PySide6.QtCore import Property
from PySide6.QtCore import QObject
from PySide6.QtCore import QTimer
from PySide6.QtCore import Signal
from PySide6.QtCore import Slot
from PySide6.QtQml import QmlElement
from PySide6.QtQml import QmlUncreatable
from plantdb.client.plantdb_client import PlantDBClient

from plantimager.commons.logging import create_logger
from plantimager.controller.camera.PiCameraComm import PiCameraComm
from plantimager.controller.scanner.dummy_cnc import DummyCNC
from plantimager.controller.scanner.grbl import CNC
from plantimager.controller.scanner.path import CalibrationPath2
from plantimager.controller.scanner.path import Circle
from plantimager.controller.scanner.path import CustomPath
from plantimager.controller.scanner.path import Path
from plantimager.controller.scanner.path import Pose
from plantimager.controller.scanner.powermanager import PowerManager
from plantimager.controller.scanner.scan import Scan
from plantimager.controller.scanner.timelapse import TimeLapse
from plantimager.controller.scanner.timelapse import TimeLapseState
from plantimager.controller.scanner.timelapse_store import TimelapseStore

QML_IMPORT_NAME = "PlantImagerApp.Scanner"
QML_IMPORT_MAJOR_VERSION = 1

logger = create_logger(__name__)


@QmlElement
@QmlUncreatable("Scanner cannot be created from QML")
class Scanner(QObject):
    """Main controller bridge for the plant imaging scanner system.

    This class owns the device state and delegates actual scanning work to
    :class:`Scan` / :class:`TimeLapse` / :class:`PowerManager`. It exposes the
    QML/RPC surface: camera management, CNC state, progress, path info and the
    active timelapse.

    Attributes
    ----------
    progressChanged : Signal(int)
        Signal emitted when the per-position scan progress changes.
    maxProgressChanged : Signal(int)
        Signal emitted when maximum per-position progress changes.
    readyToScanChanged : Signal(bool)
        Signal emitted when scanner ready state changes.
    cameraNamesChanged : Signal(list)
        Signal emitted when the list of camera names changes.
    timelapseChanged : Signal(QObject)
        Signal emitted when the active timelapse object is set.
    timelapseProgressChanged : Signal(int, int)
        Schedule-level progress (current scan index, total scans).
    timelapseStateChanged : Signal(str)
        Signal emitted when the timelapse state changes.
    timelapseErrorOccurred : Signal(str)
        Signal emitted when a timelapse scan fails.
    timelapseFinished : Signal()
        Signal emitted when the active timelapse reaches a terminal state.

    config : dict
        Configuration dictionary for the scan.
    cnc : CNC or DummyCNC
        CNC controller for hardware movement.
    cameras : list[PiCameraComm]
        List of connected cameras.
    db_url : str or None
        URL of the PlantDB database.
    scan_path : Path or None
        Path to follow during scanning.
    db_client : PlantDBClient or None
        Client for communicating with the PlantDB database.
    fileset : str
        Name of the fileset to store images in.
    scan_id : str
        Identifier for the current scan.
    power_manager : PowerManager
        The single shared power manager.
    timelapse : TimeLapse or None
        The active timelapse job, or None when idle.
    """

    progressChanged = Signal(int)
    maxProgressChanged = Signal(int)
    readyToScanChanged = Signal(bool)
    cameraNamesChanged = Signal(list)
    cncTypeChanged = Signal(str)
    scanInProgressChanged = Signal(bool)
    scannerWorkingChanged = Signal(bool)
    pathInfoChanged = Signal(str)
    # --- timelapse / power bridge signals ---
    timelapseChanged = Signal(QObject)
    timelapseProgressChanged = Signal(int, int)
    timelapseStateChanged = Signal(str)
    timelapseErrorOccurred = Signal(str)
    timelapseFinished = Signal()
    powerModeChanged = Signal(str)

    def __init__(self):
        """Initialize the Scanner with default settings.

        Notes
        -----
        Attempts to connect to a CNC controller and falls back to a dummy
        controller if the connection fails. A single shared :class:`PowerManager`
        is created for GPIO power and warm-up handling.
        """
        super().__init__()
        self.config = {}  # Configuration dictionary

        self._scan_in_progress = False
        self._scanner_working = False
        try:
            # Try to connect to the real CNC hardware
            self.cnc = CNC()
            self.cnc.moveto(20, 20, 45)
        except Exception as e:
            # Fall back to dummy CNC if hardware connection fails
            logger.warning(f"Could not connect to CNC, using DummyCNC instead: {e}")
            self.cnc = DummyCNC()
        self.cameras: list[PiCameraComm] = []  # List of connected cameras
        self.db_url = None  # Database URL
        self.scan_path: Path | None = None  # Path to follow during scanning

        # Per-position progress of the currently running Scan
        self._progress = 0  # Current progress
        self._max_progress = 0  # Maximum progress value

        # Database components
        self.db_client: PlantDBClient | None = None  # Database client
        self.fileset = "images"  # Default fileset name
        self._api_token = ""

        self._cnc_connection_timer = QTimer()
        self._cnc_connection_timer.setInterval(5000)
        self._cnc_connection_timer.timeout.connect(self._try_connect_cnc)
        if isinstance(self.cnc, DummyCNC): self._cnc_connection_timer.start()

        # Timelapse / power management
        self.timelapse: TimeLapse | None = None
        self._watched_scan: Scan | None = None
        self.power_manager = PowerManager(warmup_period=30.0, parent=self)
        self.power_manager.modeChanged.connect(self.powerModeChanged)
        self.power_manager.cnc_ready.connect(self._on_power_cnc_ready)
        self._resume_timelapse()

    # ------------------------------------------------------------------
    # CNC connection
    # ------------------------------------------------------------------
    @Slot()
    def _try_connect_cnc(self):
        if isinstance(self.cnc, DummyCNC):
            try:
                # Try to connect to the real CNC hardware
                self.cnc = CNC()
                self.cnc.moveto(20, 20, 45)
            except Exception as e:
                pass
            else:
                self._cnc_connection_timer.stop()
                self.cncTypeChanged.emit(self.cnc_type)

    @Property(str, notify=cncTypeChanged)
    def cnc_type(self) -> Literal["DummyCNC", "GRBL CNC"]:
        """Get the type of the CNC controller."""
        return "DummyCNC" if isinstance(self.cnc, DummyCNC) else "GRBL CNC"

    @Slot(object)
    def _on_power_cnc_ready(self, cnc):
        """PowerManager connected a real CNC; keep a reference if we only had dummy."""
        if isinstance(self.cnc, DummyCNC):
            self.cnc = cnc
            self.cncTypeChanged.emit(self.cnc_type)

    # ------------------------------------------------------------------
    # Working / ready state
    # ------------------------------------------------------------------
    @Property(bool, notify=scanInProgressChanged)
    def scan_in_progress(self) -> bool:
        """Check if a single scan (``run_scan``) is currently running."""
        return self._scan_in_progress

    @Property(bool, notify=scannerWorkingChanged)
    def scanner_working(self) -> bool:
        """Check if the scanner is currently working (scan or manual movement)."""
        return self._scanner_working or self._scan_in_progress

    # ------------------------------------------------------------------
    # Camera management
    # ------------------------------------------------------------------
    @Slot(QObject)
    def add_camera(self, camera: PiCameraComm):
        """Add a camera to the scanner.

        Parameters
        ----------
        camera : PiCameraComm
            Camera communication object to add.

        Notes
        -----
        Emits cameraNamesChanged and readyToScanChanged signals.
        """
        logger.debug(f"Adding camera {camera.name} to scanner.")
        if self.config and camera.name in self.config:
            self._configure_cameras([camera])
        self.cameras.append(camera)  # Add camera to list
        self.cameraNamesChanged.emit(self.camera_names)  # Update camera names
        self.readyToScanChanged.emit(self.ready_to_scan)  # Update ready state

    @Slot(QObject)
    def remove_camera(self, camera: PiCameraComm):
        """Remove a camera from the scanner.

        Parameters
        ----------
        camera : PiCameraComm
            Camera communication object to remove.

        Notes
        -----
        Emits cameraNamesChanged and readyToScanChanged signals.

        Raises
        ------
        ValueError
            If the camera is not in the list of cameras.
        """
        self.cameras.remove(camera)  # Remove camera from list
        self.cameraNamesChanged.emit(self.camera_names)  # Update camera names
        self.readyToScanChanged.emit(self.ready_to_scan)  # Update ready state

    @Property(list, notify=cameraNamesChanged)
    def camera_names(self) -> list[str]:
        """Get the list of camera names."""
        return [cam.name for cam in self.cameras]  # Extract names from camera objects

    # ------------------------------------------------------------------
    # Database configuration
    # ------------------------------------------------------------------
    @Slot(str)
    def set_db_url(self, url: str):
        """Set the URL of the database to connect to.

        Parameters
        ----------
        url : str
            URL of the PlantDB database.

        Notes
        -----
        Creates a new PlantDBClient and emits readyToScanChanged on change.
        """
        if self.db_url != url:  # Only update if URL has changed
            self.db_url = url  # Set new URL
            if self._api_token:
                logger.debug(f"Connecting to PlantDB with token {self._api_token}")
                self.db_client = PlantDBClient(self.db_url, api_token=self._api_token)  # Create new client
            else:
                self.db_client = PlantDBClient(self.db_url)
            self.readyToScanChanged.emit(self.ready_to_scan)  # Update ready state

    def set_api_token(self, token: str):
        """Set the API token and re-create the PlantDBClient to access the plantdb server."""
        self._api_token = token
        if self.db_client:
            logger.debug("Initializing PlantDBClient with API token...")
            self.db_client = PlantDBClient(self.db_client.base_url, api_token=self._api_token)
            logger.debug("Done.")

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------
    def configure_scan(self, config: dict):
        """Configure the scan from a configuration dictionary.

        Sets up the scanning process by configuring:
        - The path to follow during scanning
        - Metadata for the dataset (biological and hardware)
        - Camera selection and parameters

        Parameters
        ----------
        config : dict
            Configuration dictionary with the following structure:
            {
                "ScanPath": {"class_name": str, "kwargs": dict},
                "Metadata": {"object": dict, "hardware": dict},
                # Camera configurations (camera name as key)
                "camera_name": {"offset": dict, ...}
            }
        """
        self.config = config  # Store the configuration

        # Dynamically import and instantiate the path class
        path_module = importlib.import_module("plantimager.controller.scanner.path")
        path_cfg = config["ScanPath"]
        self.scan_path = getattr(path_module, path_cfg["class_name"])(**path_cfg["kwargs"])
        self.pathInfoChanged.emit(self.path_info)

        # Update progress tracking based on path length
        self._max_progress = len(self.scan_path)
        self.maxProgressChanged.emit(self._max_progress)

        # Configure cameras
        self._configure_cameras(self.cameras)

    def _configure_cameras(self, cameras: list[PiCameraComm]):
        """Configure the cameras for scanning."""
        for camera in cameras:
            if camera.name in self.config:
                res = self.config[camera.name]["res_x"], self.config[camera.name]["res_y"]
                camera.resolution = res
                camera.encoding = self.config[camera.name]["encoding"]
                camera.config = self.config[camera.name]["config"]

    def set_scan_id(self, scan_id: str):
        """Set the identifier for the scan dataset.

        Parameters
        ----------
        scan_id : str
            Unique identifier for the scan in the database.
        """
        self.scan_id = scan_id  # Store the scan ID

    @Property(bool, notify=readyToScanChanged)
    def ready_to_scan(self) -> bool:
        """Check if the scanner is ready to perform a scan.

        The scanner is ready when the required components are available and no
        scan is in progress.
        """
        if (self.cnc and self.scan_path and self.cameras and
                self.db_client and
                hasattr(self, 'scan_id') and self.scan_id and self.fileset and
                not self._scan_in_progress and not self._scanner_working
        ):
            return True
        return False

    # ------------------------------------------------------------------
    # Per-position progress (bridged to the active Scan)
    # ------------------------------------------------------------------
    @Property(int, notify=progressChanged)
    def progress(self) -> int:
        """Get the current per-position scan progress."""
        return self._progress

    @Property(int, notify=maxProgressChanged)
    def max_progress(self) -> int:
        """Get the maximum per-position scan progress value."""
        return self._max_progress

    def _bridge_scan_signals(self, scan: Scan):
        """Forward a running Scan's per-position progress to the Scanner surface."""
        prev = self._watched_scan
        if prev is not None and prev is not scan:
            try:
                prev.progressChanged.disconnect(self.progressChanged)
                prev.maxProgressChanged.disconnect(self.maxProgressChanged)
            except (RuntimeError, TypeError):
                pass
        self._watched_scan = scan
        scan.progressChanged.connect(self.progressChanged)
        scan.maxProgressChanged.connect(self.maxProgressChanged)

    # ------------------------------------------------------------------
    # Single-scan execution (bridge for the legacy `run_scan` RPC)
    # ------------------------------------------------------------------
    def run_scan(self) -> None:
        """Execute a single scanning operation by delegating to a :class:`Scan`.

        This preserves the legacy single-scan semantics: a custom dataset id
        (via :meth:`set_scan_id`) and a synchronous, blocking run whose
        per-position progress is exposed through ``progress``/``max_progress``.

        Raises
        ------
        RuntimeError
            If any required component is missing.
        """
        self.scan()

    def scan(self) -> None:
        """Delegate a single scan to :class:`Scan` (thin bridge).

        Validates prerequisites, builds a :class:`Scan` with the current
        configuration and dataset id, bridges its per-position progress and
        runs it synchronously on the calling thread.

        Raises
        ------
        RuntimeError
            If any required component is missing.
        """
        if not self.config: raise RuntimeError("Config not set for scan")
        if not self.scan_path: raise RuntimeError("Path not set for scan")
        if not self.db_client: raise RuntimeError("DB client not set for scan")
        if not self.scan_id: raise RuntimeError("Scan id not set for scan")
        if not self.cameras: raise RuntimeError("No Cameras connected")

        self._scan_in_progress = True
        self.scanInProgressChanged.emit(self.scan_in_progress)
        self._scanner_working = True
        self.scannerWorkingChanged.emit(self.scanner_working)

        scan = Scan(self.cnc, self.db_client, self.cameras, self.scan_path,
                    self.scan_id, self.config, parent=self)
        self._bridge_scan_signals(scan)
        try:
            scan.scan()
        finally:
            self._scan_in_progress = False
            self._scanner_working = False
            self.scanInProgressChanged.emit(self.scan_in_progress)
            self.scannerWorkingChanged.emit(self.scanner_working)
            logger.info("Scan completed")

    # ------------------------------------------------------------------
    # Timelapse management
    # ------------------------------------------------------------------
    def start_timelapse(self, config: dict) -> str:
        """Create and start a new :class:`TimeLapse` and return its id.

        Parameters
        ----------
        config : dict
            Configuration dictionary, including a ``"timelapse"`` sub-dict with
            ``mode`` (``interval``/``fixed_times``/``one_shot``) and scheduling
            parameters plus ``ScanPath``/``Metadata``/camera settings.

        Returns
        -------
        str
            The unique id of the created timelapse.

        Raises
        ------
        RuntimeError
            If a timelapse is already running (``SCHEDULED`` or ``RUNNING``).
        """
        if self.timelapse is not None and self.timelapse.state in (
                TimeLapseState.SCHEDULED, TimeLapseState.RUNNING):
            raise RuntimeError("A timelapse is already running")
        name = f"tl_{datetime.datetime.now(timezone.utc):%Y_%m_%d_%H%M%S}"
        tl = TimeLapse(
            cnc=self.cnc,
            db_url=self.db_url,
            cameras=self.cameras,
            path=self.scan_path,
            timelapse_name=name,
            config=config,
            power_manager=self.power_manager,
            parent=self,
        )
        # Reuse the single database connection instead of re-deriving it.
        if self.db_client is not None:
            tl.db_client = self.db_client
        self._wire_timelapse(tl)
        self.timelapse = tl
        self.timelapseChanged.emit(tl)
        return name

    def _wire_timelapse(self, tl: TimeLapse):
        """Forward a TimeLapse's signals to the Scanner bridge surface."""
        tl.stateChanged.connect(self.timelapseStateChanged)
        tl.errorOccurred.connect(self.timelapseErrorOccurred)
        tl.scanFinished.connect(self._on_timelapse_finished)
        tl.progressChanged.connect(self._on_timelapse_progress)
        tl.scanCreated.connect(self._bridge_scan_signals)

    def get_active_timelapse(self) -> dict | None:
        """Return a serialisable snapshot of the active timelapse, or None."""
        if self.timelapse is None:
            return None
        try:
            store = TimelapseStore.from_timelapse(self.timelapse)
            return store._as_serialisable_dict()
        except Exception as exc:
            logger.error(f"Failed to serialise active timelapse: {exc}")
            return None

    def cancel_timelapse(self) -> None:
        """Cancel the active timelapse.

        Raises
        ------
        RuntimeError
            If no timelapse is active.
        """
        if self.timelapse is None:
            raise RuntimeError("No active timelapse")
        self.timelapse.cancel()

    def preview_timelapse(self, config: dict) -> dict:
        """Return the computed schedule for a config, without starting it."""
        # Reuse TimeLapse's schedule computation by building a throwaway instance
        # is heavy; instead expose the deterministic schedule via the store shape.
        from plantimager.controller.scanner.timelapse import TimeLapse as _TL
        probe = _TL(cnc=self.cnc, db_url=self.db_url, cameras=self.cameras,
                    path=self.scan_path, timelapse_name="preview", config=config,
                    power_manager=self.power_manager, parent=self)
        return {
            "mode": probe.mode.value,
            "schedule_times": [dt.isoformat() for dt in probe.schedule_times],
            "n_scans": probe.n_scans,
        }

    def _on_timelapse_progress(self, current: int, total: int):
        """Forward the schedule-level (scan index / total) progress."""
        self.timelapseProgressChanged.emit(current, total)

    def _on_timelapse_finished(self):
        """A timelapse reached a terminal state; notify the bridge."""
        self.timelapseFinished.emit()

    def _on_timelapse_scan_created(self, scan: Scan):
        """Bridge the per-position progress of a timelapse-driven Scan."""
        self._bridge_scan_signals(scan)

    def _resume_timelapse(self):
        """Best-effort startup resume of a previously persisted timelapse.

        A full rehydrate (rebuilding a :class:`TimeLapse` from its persisted
        schedule/config) is follow-up work. For now, a persisted **non-terminal**
        job is logged so the operator can decide: a stale ``RUNNING`` file is
        treated as failed per the resumption policy, and the next slot is
        evaluated rather than blocking a fresh start.
        """
        try:
            store = TimelapseStore.new_store_from_last()
        except Exception as exc:
            logger.warning(f"Could not read persisted timelapse for resume: {exc}")
            return
        if store is None:
            return
        logger.info(
            f"Found persisted timelapse '{store.timelapse_id}' in state "
            f"'{store.state}' — automatic resume construction is not yet wired "
            f"(see dev_plan/timelapse_next.md); a stale RUNNING is treated as FAILED."
        )

    # ------------------------------------------------------------------
    # Manual movement (CNC panel)
    # ------------------------------------------------------------------
    def get_position(self) -> Pose:
        """Get the current position of the scanner as a 5D pose.

        Returns
        -------
        Pose
            Current position; z is pan, tilt is always 0.
        """
        x, y, z = self.cnc.get_position()
        pose = Pose(x, y, 0, pan=z, tilt=0)
        return pose

    def set_position(self, pose: Pose) -> None:
        """Set the position of the scanner from a 5D Pose.

        Notes
        -----
        Only X, Y, and pan values are used; Z and tilt are ignored.
        """
        logger.info(f"Moving arm to {pose}")
        self._scanner_working = True
        self.scannerWorkingChanged.emit(self.scanner_working)
        # Move CNC to the specified position (only x, y, and pan are used)
        self.cnc.moveto(pose.x, pose.y, pose.pan)
        time.sleep(0.1)  # Wait for movement to complete as grbl returns a bit early

        self._scanner_working = False
        self.scannerWorkingChanged.emit(self.scanner_working)

    def get_target_pose(self, x) -> Pose:
        """Calculate the target pose from a path element.

        For any attribute not specified in the path element, the current
        position value is used.
        """
        pos = self.get_position()
        target_pose = Pose()
        for attr in pos.attributes():
            if getattr(x, attr) is None:
                setattr(target_pose, attr, getattr(pos, attr))
            else:
                setattr(target_pose, attr, getattr(x, attr))
        return target_pose

    @Slot(float, float, float)
    def move_arm(self, x: float, y: float, z: float):
        """Move the arm to the specified position."""
        self.set_position(Pose(x=x, y=y, z=0, pan=z, tilt=0))

    @Slot()
    def move_to_center(self):
        """Move the arm to the center."""
        if self.scan_path and isinstance(self.scan_path, Circle):
            self.move_arm(self.scan_path.center_x, self.scan_path.center_y, 0)
        elif self.scan_path and isinstance(self.scan_path, CalibrationPath2):
            self.move_arm(self.scan_path.center_x, self.scan_path.center_y, 0)
        elif self.scan_path and isinstance(self.scan_path, CustomPath):
            points = np.array(self.scan_path)
            x, y = np.mean(points[:, 0]), np.mean(points[:, 1])
            self.move_arm(x, y, 0)
        else:
            x, y, z = (self.cnc.x_lims[0] + self.cnc.x_lims[1]) / 2, (
                        self.cnc.y_lims[0] + self.cnc.y_lims[1]) / 2, self.cnc.z
            self.move_arm(x, y, z)

    @Slot(int)
    def move_to_position_in_path(self, i: int):
        """Move the arm to the i-th position of the scan path."""
        if not self.scan_path:
            return
        pos = self.scan_path[i]
        self.set_position(self.get_target_pose(pos))

    @Property(str, notify=pathInfoChanged)
    def path_info(self) -> str:
        """Get information about the scan path."""
        if not self.scan_path:
            return "No path configured"
        if isinstance(self.scan_path, Circle):
            return f"{type(self.scan_path).__name__}: center {self.scan_path.center_x:g}, {self.scan_path.center_y:g}, radius {self.scan_path.radius:g} - {len(self.scan_path)} steps"
        if isinstance(self.scan_path, CalibrationPath2):
            return f"{type(self.scan_path).__name__}: center {self.scan_path.center_x:g}, {self.scan_path.center_y:g}, radius {self.scan_path.radius:g} - {len(self.scan_path)} steps"
        return f"{type(self.scan_path).__name__}: {len(self.scan_path)} steps"
