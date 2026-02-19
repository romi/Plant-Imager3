# !/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Scanner Module for Plant Imaging Systems.

A comprehensive module for controlling 3D plant imaging systems, managing the scanning process,
camera control, and data acquisition. This module coordinates the movement of CNC hardware,
image capture from multiple cameras, and data upload to a database.

Key Features:
- Automated scanning along predefined paths with precise positioning
- Multi-camera support with synchronized image capture
- Asynchronous data upload to a PlantDB database
- Progress tracking and reporting
- QML integration for GUI applications
- Fallback to dummy hardware when physical hardware is unavailable
- Comprehensive metadata collection for each captured image

Usage Examples:
```python
>>> from plantimager.controller.scanner.scanner import Scanner
>>> scanner = Scanner()
>>> scanner.set_db_url("http://localhost:5000")
>>> scanner.configure_scan(config_dict)  # Configure scan parameters
>>> scanner.set_scan_id("plant_scan_001")  # Set scan identifier
>>> scanner.scan()  # Start the scanning process
```
"""

import importlib
import time
import traceback
from concurrent.futures import ALL_COMPLETED
from concurrent.futures import FIRST_COMPLETED
from concurrent.futures import Future
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import wait
from io import BytesIO
from typing import Literal
from weakref import finalize

import numpy as np
from PySide6.QtCore import Property
from PySide6.QtCore import QObject
from PySide6.QtCore import QTimer
from PySide6.QtCore import Signal
from PySide6.QtCore import Slot
from PySide6.QtQml import QmlElement
from PySide6.QtQml import QmlUncreatable
from plantdb.client.plantdb_client import PlantDBClient
from requests.exceptions import RequestException

from plantimager.commons.logging import create_logger
from plantimager.controller.camera.PiCameraComm import PiCameraComm
from plantimager.controller.scanner.dummy_cnc import DummyCNC
from plantimager.controller.scanner.grbl import CNC
from plantimager.controller.scanner.hal import DataItem
from plantimager.controller.scanner.path import CalibrationPath2
from plantimager.controller.scanner.path import Circle
from plantimager.controller.scanner.path import CustomPath
from plantimager.controller.scanner.path import Path
from plantimager.controller.scanner.path import PathElement
from plantimager.controller.scanner.path import Pose

QML_IMPORT_NAME = "PlantImagerApp.Scanner"
QML_IMPORT_MAJOR_VERSION = 1

logger = create_logger(__name__)


class DataUploader():
    """Worker thread that uploads scan data from a queue to a plantdb instance.

    This class manages asynchronous uploads of image data to a PlantDB database
    using a thread pool. It limits the number of concurrent uploads and provides
    a queue mechanism to handle backpressure.

    Attributes
    ----------
    db_client : PlantDBClient
        Client for communicating with the PlantDB database
    jobs : set[Future]
        Set of active upload job futures
    pool : ThreadPoolExecutor
        Thread pool for executing upload tasks
    queue_size : int
        Maximum number of concurrent upload jobs

    Notes
    -----
    - Uses ThreadPoolExecutor with 4 worker threads for parallel uploads
    - Automatically shuts down the thread pool when the object is garbage collected
    - Blocks new uploads when the queue is full until a slot becomes available

    Examples
    --------
    >>> import numpy as np
    >>> from plantdb.client.plantdb_client import PlantDBClient
    >>> from plantimager.controller.scanner.scanner import DataUploader
    >>> from plantimager.controller.scanner.hal import DataItem
    >>> client = PlantDBClient("http://localhost:5000")
    >>> uploader = DataUploader(client, queue_size=10)
    >>> # Generate random RGB data (values from 0-255)
    >>> rgb_data = np.random.randint(0, 256, (200, 150, 3), dtype=np.uint8)
    >>> metadata = {'description': 'Random RGB test image', 'author': 'John Doe'}
    >>> data_item = DataItem(rgb_data, metadata)
    >>> uploader.upload("scan_001", "images", data_item)
    """

    def __init__(self, db_client: PlantDBClient, queue_size: int):
        """Initialize the DataUploader with a database client and queue size.

        Parameters
        ----------
        db_client : plantdb.client.plantdb_client.PlantDBClient
            Client for communicating with the PlantDB database
        queue_size : int
            Maximum number of concurrent upload jobs
        """
        self.db_client = db_client
        self.jobs: set[Future] = set()  # Track active upload jobs
        self.pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix=__name__)
        self.queue_size = queue_size
        # Ensure thread pool is properly shut down when object is garbage collected
        finalize(self, self.pool.shutdown, wait=True, cancel_futures=True)

    def _upload(self, scan_id: str, fileset: str, data: DataItem):
        """Internal method to perform the actual upload operation.

        Parameters
        ----------
        scan_id : str
            Identifier of the scan in the database
        fileset : str
            Identifier of the fileset within the scan
        data : DataItem
            Data item containing the image and metadata to upload

        Notes
        -----
        This is a private method called by the public upload method.
        """
        # Create a BytesIO buffer from the image data
        buffer = BytesIO(data.image)
        buffer.seek(0)  # Reset buffer position to start
        try:
            # Upload the file to the database with metadata
            response = self.db_client.create_file(
                buffer, file_id=f"{data.metadata['camera_name']}-{data.idx:0>5}", ext=data.image_ext,
                scan_id=scan_id, fileset_id=fileset, metadata=data.metadata
            )
        except Exception as e:
            # Log any exceptions that occur during upload
            traceback.print_exception(e)
        return

    def upload(self, scan_id: str, fileset: str, data: DataItem):
        """Upload data file to specified fileset of scan_id in a plantdb instance.

        This method queues an upload job to the thread pool. If the queue is full,
        it blocks until a slot becomes available.

        Parameters
        ----------
        scan_id : str
            Identifier of the scan in the database
        fileset : str
            Identifier of the fileset within the scan
        data : DataItem
            Data item containing the image and metadata to upload

        Notes
        -----
        This method may block indefinitely if the upload queue is full and
        no upload jobs are completing.
        """
        # Wait if the number of jobs submitted is greater than queue_size
        if len(self.jobs) >= self.queue_size:
            wait(self.jobs, return_when=FIRST_COMPLETED)  # blocking

        # Submit the upload job to the thread pool
        future_: Future = self.pool.submit(self._upload, scan_id, fileset, data)
        self.jobs.add(future_)  # Track the job
        future_.add_done_callback(self.jobs.remove)  # Remove job when done


@QmlElement
@QmlUncreatable("Scanner cannot be created from QML")
class Scanner(QObject):
    """Main controller for the plant imaging scanner system.

    This class coordinates the scanning process, including CNC movement control,
    camera management, image capture, and data upload. It integrates with QML
    for GUI applications and provides signals for progress tracking.

    Attributes
    ----------
    progressChanged : Signal(int)
        Signal emitted when scan progress changes
    maxProgressChanged : Signal(int)
        Signal emitted when maximum progress value changes
    readyToScanChanged : Signal(bool)
        Signal emitted when scanner ready state changes
    cameraNamesChanged : Signal(list)
        Signal emitted when the list of camera names changes
    config : dict
        Configuration dictionary for the scan
    cnc : CNC or DummyCNC
        CNC controller for hardware movement
    cameras : list[PiCameraComm]
        List of connected cameras
    db_url : str or None
        URL of the PlantDB database
    scan_path : Path or None
        Path to follow during scanning
    db_client : PlantDBClient or None
        Client for communicating with the PlantDB database
    uploader : DataUploader or None
        Data uploader for sending images to the database
    fileset : str
        Name of the fileset to store images in
    scan_id : str
        Identifier for the current scan

    Notes
    -----
    - Automatically falls back to DummyCNC if hardware connection fails
    - Requires configuration, database connection, and at least one camera to scan
    - Integrates with QML through signals and properties

    Examples
    --------
    >>> from plantimager.controller.scanner.scanner import Scanner
    >>> from plantimager.controller.camera.camera import PiCameraComm
    >>> camera = PiCameraComm()
    >>> scanner = Scanner()
    >>> scanner.set_db_url("http://localhost:5000")
    >>> scanner.add_camera(camera)
    >>> scanner.configure_scan(config_dict)
    >>> scanner.set_scan_id("plant_scan_001")
    >>> scanner.scan()
    """
    progressChanged = Signal(int)
    maxProgressChanged = Signal(int)
    readyToScanChanged = Signal(bool)
    cameraNamesChanged = Signal(list)
    cncTypeChanged = Signal(str)
    scanInProgressChanged = Signal(bool)
    scannerWorkingChanged = Signal(bool)
    pathInfoChanged = Signal(str)

    def __init__(self):
        """Initialize the Scanner with default settings.

        Notes
        -----
        Attempts to connect to a CNC controller and falls back to a dummy
        controller if the connection fails.
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

        # Progress tracking
        self._progress = 0  # Current progress
        self._max_progress = 0  # Maximum progress value

        # Database and upload components
        self.db_client: PlantDBClient | None = None  # Database client
        self.uploader: DataUploader | None = None  # Data uploader
        self.fileset = "images"  # Default fileset name
        self._access_token = ""
        self._refresh_token = ""

        self._cnc_connection_timer = QTimer()
        self._cnc_connection_timer.setInterval(5000)
        self._cnc_connection_timer.timeout.connect(self._try_connect_cnc)
        if isinstance(self.cnc, DummyCNC): self._cnc_connection_timer.start()

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

    @Property(bool, notify=scanInProgressChanged)
    def scan_in_progress(self) -> bool:
        """Check if the scanner is currently scanning."""
        return self._scan_in_progress

    @Property(bool, notify=scannerWorkingChanged)
    def scanner_working(self) -> bool:
        """Check if the scanner is currently working."""
        return self._scanner_working or self._scan_in_progress

    @Slot(QObject)
    def add_camera(self, camera: PiCameraComm):
        """Add a camera to the scanner.

        Parameters
        ----------
        camera : PiCameraComm
            Camera communication object to add

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
            Camera communication object to remove

        Notes
        -----
        Emits cameraNamesChanged and readyToScanChanged signals.

        Raises
        ------
        ValueError
            If the camera is not in the list of cameras
        """
        self.cameras.remove(camera)  # Remove camera from list
        self.cameraNamesChanged.emit(self.camera_names)  # Update camera names
        self.readyToScanChanged.emit(self.ready_to_scan)  # Update ready state

    @Property(list, notify=cameraNamesChanged)
    def camera_names(self) -> list[str]:
        """Get the list of camera names.

        Returns
        -------
        list[str]
            List of names of connected cameras

        Notes
        -----
        This property is exposed to QML and notifies via cameraNamesChanged signal.
        """
        return [cam.name for cam in self.cameras]  # Extract names from camera objects

    @Slot(str)
    def set_db_url(self, url: str):
        """Set the URL of the database to connect to.

        Parameters
        ----------
        url : str
            URL of the PlantDB database

        Notes
        -----
        Creates a new PlantDBClient and DataUploader if the URL changes.
        Emits readyToScanChanged signal if the URL changes.

        Examples
        --------
        >>> scanner.set_db_url("http://localhost:5000")
        """
        if self.db_url != url:  # Only update if URL has changed
            self.db_url = url  # Set new URL
            self.db_client = PlantDBClient(self.db_url)  # Create new client
            if self._access_token:
                # Validate existing tokens
                self.db_client._access_token = self._access_token
                self.db_client._refresh_token = self._refresh_token
                logger.debug("Validating PlantDB session token")
                if self.db_client.validate_token(self._access_token):
                    # Update them if valid
                    self._access_token = self.db_client._access_token
                    self._refresh_token = self.db_client._refresh_token
                else:
                    # Reset if not
                    logger.warning("Invalid PlantDB session token found!")
                    self._access_token = None
                    self._refresh_token = None
            self.uploader = DataUploader(self.db_client, 10)  # Create new uploader
            self.readyToScanChanged.emit(self.ready_to_scan)  # Update ready state

    @Property(int, notify=progressChanged)
    def progress(self) -> int:
        """Get the current scan progress.

        Returns
        -------
        int
            Current progress value

        Notes
        -----
        This property is exposed to QML and notifies via progressChanged signal.
        """
        return self._progress

    @Property(int, notify=maxProgressChanged)
    def max_progress(self) -> int:
        """Get the maximum scan progress value.

        Returns
        -------
        int
            Maximum progress value

        Notes
        -----
        This property is exposed to QML and notifies via maxProgressChanged signal.
        """
        return self._max_progress

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
                "ScanPath": {
                    "class_name": str,  # Name of the path class
                    "kwargs": dict  # Arguments for path constructor
                },
                "Metadata": {
                    "object": dict,  # Biological metadata
                    "hardware": dict  # Hardware metadata
                },
                # Camera configurations (camera name as key)
                "camera_name": {
                    "offset": dict,  # Camera position offset
                    # Other camera parameters
                }
            }

        Notes
        -----
        - Dynamically imports and instantiates the path class
        - Updates the maximum progress based on path length
        - Emits maxProgressChanged signal

        Examples
        --------
        >>> config = {
        ...     "ScanPath": {"class_name": "CirclePath", "kwargs": {"radius": 100}},
        ...     "Metadata": {
        ...         "object": {"species": "Arabidopsis thaliana"},
        ...         "hardware": {"scanner_version": "1.0"}
        ...     },
        ...     "camera1": {"offset": {"x": 0, "y": 0, "z": 0}}
        ... }
        >>> scanner.configure_scan(config)
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

        # Store metadata for the scan
        self.dataset_metadata = config["Metadata"]["object"]  # Biological metadata
        self.hw_metadata = config["Metadata"]["hardware"]  # Hardware metadata

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

    @Property(bool, notify=readyToScanChanged)
    def ready_to_scan(self) -> bool:
        """Check if the scanner is ready to perform a scan.

        Returns
        -------
        bool
            True if all required components are set up, False otherwise

        Notes
        -----
        This property is exposed to QML and notifies via readyToScanChanged signal.

        The scanner is ready when all of the following are available:
        - CNC controller
        - Scan path
        - At least one camera
        - Database uploader
        - Database client
        - Scan ID
        - Fileset name
        """
        # Check if all required components are available
        if (self.cnc and self.scan_path and self.cameras and
                self.uploader and self.db_client and
                hasattr(self, 'scan_id') and self.scan_id and self.fileset and
                not self._scan_in_progress and not self._scanner_working
        ):
            return True
        return False

    def get_position(self) -> Pose:
        """Get the current position of the scanner.

        Returns
        -------
        Pose
            Current position as a 5D pose (x, y, z, pan, tilt)

        Notes
        -----
        The Z and tilt values are always set to 0 as the scanner only
        supports 3D movement (X, Y, and pan rotation).
        """
        # Get raw position from CNC controller
        x, y, z = self.cnc.get_position()
        # Convert to Pose object (z is pan, tilt is always 0)
        pose = Pose(x, y, 0, pan=z, tilt=0)
        return pose

    def set_position(self, pose: Pose) -> None:
        """Set the position of the scanner from a 5D Pose.

        Parameters
        ----------
        pose : Pose
            Target position as a 5D pose (x, y, z, pan, tilt)

        Notes
        -----
        Only X, Y, and pan values are used; Z and tilt are ignored.

        Examples
        --------
        >>> pose = Pose(100, 100, 0, pan=45, tilt=0)
        >>> scanner.set_position(pose)
        """
        logger.info(f"Moving arm to {pose}")
        self._scanner_working = True
        self.scannerWorkingChanged.emit(self.scanner_working)
        # Move CNC to the specified position (only x, y, and pan are used)
        self.cnc.moveto(pose.x, pose.y, pose.pan)
        time.sleep(0.1)  # Wait for movement to complete as grbl returns a bit early

        self._scanner_working = False
        self.scannerWorkingChanged.emit(self.scanner_working)

    def set_scan_id(self, scan_id: str):
        """Set the identifier for the scan dataset.

        Parameters
        ----------
        scan_id : str
            Unique identifier for the scan in the database

        Notes
        -----
        This ID is used when creating the scan in the database and
        when uploading files.

        Examples
        --------
        >>> scanner.set_scan_id("arabidopsis_001")
        """
        self.scan_id = scan_id  # Store the scan ID

    def grab(self, idx: int, metadata: dict, camera: PiCameraComm) -> DataItem:
        """Capture an image from a camera and upload it to the database.

        This method captures an image from the specified camera, adds metadata,
        creates a DataItem, and uploads it to the database.

        Parameters
        ----------
        idx : int
            Identifier for the data item to create
        metadata : dict
            Dictionary of metadata to associate with the image
        camera : PiCameraComm
            Camera object to use for capturing the image

        Returns
        -------
        DataItem
            The created data item containing the image and metadata

        Notes
        -----
        The method performs these steps:
        1. Capture image from camera
        2. Update metadata with image information
        3. Create a DataItem
        4. Upload the data to the database

        Examples
        --------
        >>> metadata = {"camera_name": "cam1", "approximate_pose": [100, 100, 0, 45, 0]}
        >>> data_item = scanner.grab(1, metadata, camera)
        """
        # Capture image from camera
        image_future = camera.getImage(lores=False)
        buffer, buffer_info = image_future.result()  # Wait for image capture to complete

        # Update metadata with image information from camera
        metadata.update(buffer_info)

        # Create data item with image and metadata
        data = DataItem(idx, buffer, image_ext=buffer_info["format"], metadata=metadata)

        # Upload data to database
        self.uploader.upload(scan_id=self.scan_id, fileset=self.fileset, data=data)

        return data

    def get_target_pose(self, x: PathElement) -> Pose:
        """Calculate the target pose from a path element.

        This method creates a target pose by combining the current position
        with the specified values from the path element. For any attribute
        not specified in the path element, the current position value is used.

        Parameters
        ----------
        x : PathElement
            Path element containing the desired position attributes

        Returns
        -------
        Pose
            The calculated target pose

        Notes
        -----
        If a coordinate in the path element is None, the current position
        value for that coordinate is used instead.
        """
        # Get current position
        pos = self.get_position()
        # Create new pose
        target_pose = Pose()

        # For each attribute (x, y, z, pan, tilt)
        for attr in pos.attributes():
            if getattr(x, attr) is None:
                # If path element doesn't specify this attribute, use current position
                setattr(target_pose, attr, getattr(pos, attr))
            else:
                # Otherwise use the value from the path element
                setattr(target_pose, attr, getattr(x, attr))

        return target_pose

    def scan(self) -> None:
        """Execute the complete scanning process.

        This method performs a full scan by:
        1. Validating that all required components are available
        2. Creating the scan and fileset in the database
        3. Following the scan path and capturing images at each position
        4. Uploading all captured images with metadata

        Raises
        ------
        RuntimeError
            If any required component is missing

        Notes
        -----
        - Validates all prerequisites before starting
        - Creates scan and fileset in the database
        - Follows the scan path, moving the CNC to each position
        - Captures images from all cameras at each position
        - Uploads images with position and camera metadata
        - Uses a thread pool for parallel image capture
        - Updates progress throughout the scan

        Examples
        --------
        >>> scanner.set_db_url("http://localhost:5000")
        >>> scanner.configure_scan(config_dict)
        >>> scanner.set_scan_id("plant_scan_001")
        >>> scanner.scan()  # Execute the scan
        """
        # Validate all required components are available
        if not self.config: raise RuntimeError("Config not set for scan")
        if not self.scan_path: raise RuntimeError("Path not set for scan")
        if not self.db_url: raise RuntimeError("DB url not set for scan")
        if not self.db_client: raise RuntimeError("DB client not set for scan")
        if not self.uploader: raise RuntimeError("Uploader not set for scan")
        if not self.scan_id: raise RuntimeError("Scan id not set for scan")
        if not self.cameras: raise RuntimeError("No Cameras connected")

        # Update metadata if using dummy CNC
        if isinstance(self.cnc, DummyCNC):
            self.hw_metadata["name"] = "DummyCNC"

        self._scan_in_progress = True
        self.scanInProgressChanged.emit(self.scan_in_progress)

        # Create the scan on the remote database
        try:
            # Combine dataset and hardware metadata
            self.db_client.create_scan(self.scan_id, metadata=self.config)
        except RequestException as e:
            logger.error(f"{e}")
        except ValueError as e:
            logger.error(f"{e}")
            logger.error(f"Scan {self.scan_id} already exists in plantdb")

        # Create the image fileset on the remote database
        try:
            self.db_client.create_fileset(self.fileset, self.scan_id)
        except RequestException as e:
            logger.error(f"{e}")
        except ValueError as e:
            logger.error(f"{e}")
            logger.error(f"Fileset {self.fileset} already exists for scan {self.scan_id}")

        # Execute the scan using a thread pool for parallel image capture
        with ThreadPoolExecutor(max_workers=4) as executor:
            shot_id = 0  # Initialize shot counter
            self._progress = 0  # Reset progress

            # Follow each point in the scan path
            for x in self.scan_path:
                # Update progress
                self._progress += 1
                self.progressChanged.emit(self._progress)

                # Calculate and move to the target position
                pose = self.get_target_pose(x)
                self.set_position(pose)

                # Get actual arm position after movement
                arm_pose = self.get_position()
                jobs = []  # List to track image capture jobs

                # Capture images from each camera
                for camera in self.cameras:
                    name = camera.name
                    # Skip cameras not in config
                    if name not in self.config:
                        logger.debug(f"Camera {name} not in config, skipping")
                        continue

                    # Get camera parameters and calculate camera position
                    camera_param = self.config[name]
                    camera_offset = Pose(**camera_param["offset"])
                    camera_pose = arm_pose + camera_offset  # Apply offset to arm position

                    # Prepare metadata for this shot
                    metadata = {
                        **camera_param,  # Include all camera parameters
                        "camera_name": name,
                        "approximate_pose": [camera_pose.x, camera_pose.y, camera_pose.z, camera_pose.pan,
                                             camera_pose.tilt],  # Camera position
                        "shot_id": shot_id,  # Unique ID for this shot
                    }

                    # Submit image capture job to thread pool
                    jobs.append(executor.submit(self.grab, shot_id, metadata, camera))

                shot_id += 1
                # Wait for all image captures to complete before moving to next position
                wait(jobs, return_when=ALL_COMPLETED)

        # Move the arm back close to origin
        # self.cnc.moveto(10, 10,-10)
        time.sleep(1)
        # self.cnc.home()
        self.move_arm(20, 20, 45)
        self._scan_in_progress = False
        self.scanInProgressChanged.emit(self.scan_in_progress)
        logger.info(f"Scan completed")  # Log completion

    @Slot(float, float, float)
    def move_arm(self, x: float, y: float, z: float):
        """Move the arm to the specified position."""
        self.set_position(Pose(x=x, y=y, z=0, pan=z, tilt=0))

    @Slot()
    def move_to_center(self):
        """Move the arm to the center"""
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

    def set_session_token(self, tokens: tuple[str, str]):
        """Set the session token for plantdb"""
        self._access_token, self._refresh_token = tokens
        if self.db_client:
            self.db_client._access_token, self.db_client._refresh_token = tokens
            logger.debug("Validating PlantDB session token")
            self.db_client.validate_token(self._access_token)
            logger.debug("Session token valid")
