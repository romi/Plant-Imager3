"""
Define the Scan class which handles the scanning process by using the grbl CNC and DataUploader to
upload data to PlantDB
"""

import os
import subprocess
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, Future, ALL_COMPLETED, FIRST_COMPLETED
from concurrent.futures import wait as cf_wait
from io import BytesIO
from typing import Literal, Any
from weakref import finalize
from datetime import datetime

from PySide6.QtCore import QObject, Signal, Property
from plantdb.client.plantdb_client import PlantDBClient
from requests.exceptions import RequestException

from plantimager.commons.logging import create_logger
from plantimager.controller.camera.PiCameraComm import PiCameraComm
from plantimager.controller.scanner.dummy_cnc import DummyCNC
from plantimager.controller.scanner.grbl import CNC
from plantimager.controller.scanner.hal import DataItem, AbstractCNC
from plantimager.controller.scanner.path import Path, Circle, CalibrationPath2, CustomPath
from plantimager.controller.scanner.path import PathElement
from plantimager.controller.scanner.path import Pose

logger = create_logger(__name__)

DB_UPLOADER_QUEUE_SIZE = int(os.getenv("DB_UPLOADER_QUEUE_SIZE", "10"))
TZ = time.tzname[0]

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
        # Wait if number of jobs submitted is greater than queue_size
        if len(self.jobs) >= self.queue_size:
            cf_wait(self.jobs, return_when=FIRST_COMPLETED)  # blocking

        # Submit the upload job to the thread pool
        future_: Future = self.pool.submit(self._upload, scan_id, fileset, data)
        self.jobs.add(future_)  # Track the job
        future_.add_done_callback(self.jobs.remove)  # Remove job when done


class Scan(QObject):
    """
    Represents a scanner for executing complex scanning operations, including positioning,
    capturing data from multiple cameras, and uploading results to a remote database.

    This class integrates hardware (such as CNC controllers and cameras) and software
    components to automate the scanning and data gathering workflow. It also provides
    progress tracking and metadata management, making it suitable for dynamic and complex
    scanning needs.

    Attributes
    ----------
    progressChanged : Signal(int)
        Signal emitted when the scan progress changes.
    maxProgressChanged : Signal(int)
        Signal emitted when the maximum progress value changes.
    cnc : AbstractCNC
        The CNC controller for managing scanner movements.
    db_url : str
        URL of the database to upload scan data.
    db_client : PlantDBClient
        Client used for database operations.
    uploader : DataUploader
        Uploads data items to the database.
    cameras : list of PiCameraComm
        List of camera objects used for capturing images.
    path : Path
        Path object representing the set of positions for the scan.
    scan_id : str
        Unique identifier for the scan.
    fileset : str
        Name of the fileset for storing images.
    _progress : int
        Tracks the current scan progress.
    _max_progress : int
        Maximum possible progress value, derived from the length of the scan path.
    config : dict
        Configuration for the scan, including metadata and hardware settings.
    dataset_metadata : Any
        Metadata related to the biological or scanned object.
    hw_metadata : Any
        Metadata related to the hardware used.
    _start_time : int or None
        Start time of the scan in UNIX timestamp format, or None if not started.
    _stop_time : int or None
        Stop time of the scan in UNIX timestamp format, or None if not completed.

    Notes
    -----
    - This class is designed for integration with QML and emits progress signals.
    - Attributes such as `_progress` and `_max_progress` track scanning operations.
    - The scanning process is highly configurable using `config` — ensure it contains
      the necessary fields such as metadata and hardware details.
    """
    progressChanged = Signal(int)
    maxProgressChanged = Signal(int)

    def __init__(self, cnc: AbstractCNC, db_client: PlantDBClient, cameras: list[PiCameraComm], path: Path, scan_id: str,
                 config: dict[str, Any], parent=None):
        super().__init__(parent)
        self.cnc = cnc
        self.db_client = db_client
        self.uploader = DataUploader(self.db_client, queue_size=DB_UPLOADER_QUEUE_SIZE)
        self.cameras = cameras
        self.path = path
        self.scan_id = scan_id
        self.fileset = "images"
        self._progress = 0
        self._max_progress = len(path)
        self.config = config
        # Store metadata for the scan
        self.dataset_metadata = config["Metadata"]["object"]  # Biological metadata
        self.hw_metadata = config["Metadata"]["hardware"]  # Hardware metadata

        # time
        self._start_time: int | None = None
        self._stop_time: int | None = None

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
        >>> scan.set_position(pose)
        """
        logger.info(f"Moving arm to {pose}")
        # Move CNC to the specified position (only x, y, and pan are used)
        self.cnc.moveto(pose.x, pose.y, pose.pan)
        time.sleep(0.1)  # Wait for movement to complete as grbl returns a bit early

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
        >>> data_item = scan.grab(1, metadata, camera)
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

        """
        # Validate all required components are available
        if not self.config: raise RuntimeError("Config not set for scan")
        if not self.path: raise RuntimeError("Path not set for scan")
        if not self.db_client: raise RuntimeError("DB client not set for scan")
        if not self.uploader: raise RuntimeError("Uploader not set for scan")
        if not self.scan_id: raise RuntimeError("Scan id not set for scan")
        if not self.cameras: raise RuntimeError("No Cameras connected")

        # Update metadata if using dummy CNC
        if isinstance(self.cnc, DummyCNC):
            self.hw_metadata["name"] = "DummyCNC"

        self._start_time = time.time()
        time_info = {
            "timezone": TZ,
            "start_time": datetime.fromtimestamp(self._start_time).astimezone().isoformat(timespec="seconds"),
            "stop_time": None
        }
        self.config.update(time_info)

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
            for x in self.path:
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
                    name: str = camera.name
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
                cf_wait(jobs, return_when=ALL_COMPLETED)

        # Move the arm back close to origin
        #self.cnc.moveto(10, 10,-10)
        time.sleep(1)
        #self.cnc.home()
        self.cnc.moveto(20, 20, 45)

        self._stop_time = time.time()
        self.db_client.update_scan_metadata(self.scan_id, {
            "stop_time": datetime.fromtimestamp(self._stop_time).astimezone().isoformat(timespec="seconds"),
        })
        logger.info(f"Scan completed")  # Log completion
