import importlib
import traceback
from concurrent.futures import ThreadPoolExecutor, Future, wait, FIRST_COMPLETED, ALL_COMPLETED
from http.client import responses
from io import BytesIO
from weakref import finalize

from PySide6.QtCore import QObject, Signal, Slot, Property
from PySide6.QtQml import QmlUncreatable, QmlElement
from plantdb.client.plantdb_client import PlantDBClient
from requests.exceptions import RequestException

from plantimager.commons.logging import create_logger
from plantimager.controller.camera.PiCameraComm import PiCameraComm
from plantimager.controller.scanner.dummy_cnc import DummyCNC
from plantimager.controller.scanner.grbl import CNC
from plantimager.controller.scanner.hal import DataItem
from plantimager.controller.scanner.path import Path, Pose, PathElement

QML_IMPORT_NAME = "PlantImagerApp.Scanner"
QML_IMPORT_MAJOR_VERSION = 1

logger = create_logger(__name__)


class DataUploader():
    """
    Worker thread that will upload scan data from a queue to a plantdb instance.
    """

    def __init__(self, db_client: PlantDBClient, queue_size: int):
        self.db_client = db_client
        self.jobs: set[Future] = set()
        self.pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix=__name__)
        self.queue_size = queue_size
        finalize(self, self.pool.shutdown, wait=True, cancel_futures=True)

    def _upload(self, scan_id: str, fileset: str, data: DataItem):
        buffer = BytesIO(data.image)
        buffer.seek(0)
        try:
            response = self.db_client.create_file(
                buffer, file_id=f"{data.metadata['camera_name']}-{data.idx}", ext=data.image_ext,
                scan_id=scan_id, fileset_id=fileset, metadata=data.metadata
            )
        except Exception as e:
            traceback.print_exception(e)
        return

    def upload(self, scan_id: str, fileset: str, data: DataItem):
        """
        Uploads data file to specified fileset of scan_id in a plantdb instance.

        Blocks indefinitely if upload queue is full.

        Parameters
        ----------
        scan_id
        fileset
        data

        Returns
        -------

        """
        if len(self.jobs) >= self.queue_size:  # wait if number of jobs submitted greater than queue_size
            wait(self.jobs, return_when=FIRST_COMPLETED)  # blocking
        future_: Future = self.pool.submit(self._upload, scan_id, fileset, data)
        self.jobs.add(future_)
        future_.add_done_callback(self.jobs.remove)


@QmlElement
@QmlUncreatable("Scanner cannot be created from QML")
class Scanner(QObject):
    progressChanged = Signal(int)
    maxProgressChanged = Signal(int)
    readyToScanChanged = Signal(bool)
    cameraNamesChanged = Signal(list)

    def __init__(self):
        super().__init__()
        self.config = {}
        try:
            self.cnc = CNC()
        except Exception as e:
            logger.warning(f"Could not connect to CNC, using DummyCNC instead: {e}")
            self.cnc = DummyCNC()
        self.cameras: list[PiCameraComm] = []
        self.db_url = None
        self.scan_path: Path | None = None

        self._progress = 0
        self._max_progress = 0

        self.db_client: PlantDBClient | None = None
        self.uploader: DataUploader | None = None
        self.fileset = "images"

    @Slot(QObject)
    def add_camera(self, camera: PiCameraComm):
        self.cameras.append(camera)
        self.cameraNamesChanged.emit(self.camera_names)
        self.readyToScanChanged.emit(self.ready_to_scan)

    @Slot(QObject)
    def remove_camera(self, camera: PiCameraComm):
        self.cameras.remove(camera)
        self.cameraNamesChanged.emit(self.camera_names)
        self.readyToScanChanged.emit(self.ready_to_scan)

    @Property(list, notify=cameraNamesChanged)
    def camera_names(self) -> list[str]:
        return [cam.name for cam in self.cameras]

    @Slot(str)
    def set_db_url(self, url: str):
        """Sets the url of the database to connect to."""
        if self.db_url != url:
            self.db_url = url
            self.db_client = PlantDBClient(self.db_url)
            self.uploader = DataUploader(self.db_client, 10)
            self.readyToScanChanged.emit(self.ready_to_scan)

    @Property(int, notify=progressChanged)
    def progress(self) -> int:
        return self._progress

    @Property(int, notify=maxProgressChanged)
    def max_progress(self) -> int:
        return self._max_progress

    def configure_scan(self, config: dict):
        """Configures the scan from a config dict.

        Configures the scan:
        - select the cameras
        - defines the path to follow
        - defines biological metadata
        - defines hardware metadata

        Parameters
        ----------
        config : dict
            The configuration dictionary to use for the scan.
        """
        self.config = config
        # Defines the path to follow for scanning
        path_module = importlib.import_module("plantimager.controller.scanner.path")
        path_cfg = config["Path"]
        self.scan_path = getattr(path_module, path_cfg["name"])(**path_cfg["kwargs"])
        self._max_progress = len(self.scan_path)
        self.maxProgressChanged.emit(self._max_progress)
        # Defines the dataset metadata
        self.dataset_metadata = config["Metadata"]["object"]
        # Defines the hardware metadata
        self.hw_metadata = config["Metadata"]["hardware"]

    @Property(bool, notify=readyToScanChanged)
    def ready_to_scan(self) -> bool:
        if self.cnc and self.scan_path and self.cameras and self.uploader and self.db_client and self.scan_id and self.fileset:
            return True
        return False

    def get_position(self) -> Pose:
        """Get the current position of the scanner."""
        x, y, z = self.cnc.get_position()
        pose = Pose(x, y, 0, pan=z, tilt=0)
        return pose

    def set_position(self, pose: Pose) -> None:
        """Set the position of the scanner from a 5D Pose."""
        logger.info(f"Moving arm to {pose}")
        self.cnc.moveto(pose.x, pose.y, pose.pan)

    def set_scan_id(self, scan_id: str):
        """Set the name of the dataset to create."""
        self.scan_id = scan_id

    def grab(self, idx: int, metadata: dict, camera: PiCameraComm) -> DataItem:
        """Grab data with an id and metadata using camera and sends the data to

        Parameters
        ----------
        idx : int
            Id of the data `DataItem` to create.
        metadata : dict, optional
            Dictionary of metadata associated to the camera data.
        camera : PiCameraComm
            Camera used to grab the data.
        Returns
        -------
        plantimager.hal.DataItem
            The image data.

        """
        image_future = camera.getImage()
        buffer, buffer_info = image_future.result()
        metadata.update(buffer_info)
        data = DataItem(idx, buffer, image_ext=buffer_info["format"], metadata=metadata)
        self.uploader.upload(scan_id=self.scan_id, fileset=self.fileset, data=data)

    def inc_count(self) -> int:
        """Incremental counter used to return id for `grab` method. """
        x = self._progress
        self._progress += 1
        self.progressChanged.emit(self._progress)
        return x

    def get_target_pose(self, x: PathElement) -> Pose:
        pos = self.get_position()
        target_pose = Pose()
        for attr in pos.attributes():
            if getattr(x, attr) is None:
                setattr(target_pose, attr, getattr(pos, attr))
            else:
                setattr(target_pose, attr, getattr(x, attr))
        return target_pose

    def scan(self) -> None:
        if not self.config: raise RuntimeError("Config not set for scan")
        if not self.scan_path: raise RuntimeError("Path not set for scan")
        if not self.db_url: raise RuntimeError("DB url not set for scan")
        if not self.db_client: raise RuntimeError("DB client not set for scan")
        if not self.uploader: raise RuntimeError("Uploader not set for scan")
        if not self.scan_id: raise RuntimeError("Scan id not set for scan")
        if not self.cameras: raise RuntimeError("No Cameras connected")

        if isinstance(self.cnc, DummyCNC):
            self.hw_metadata["name"] = "DummyCNC"

        # Create the scan on the remote database
        try:
            self.db_client.create_scan(self.scan_id, metadata=self.dataset_metadata | self.hw_metadata)
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

        with ThreadPoolExecutor(max_workers=4) as executor:
            shot_id = 0
            self._progress = 0
            for x in self.scan_path:
                self._progress += 1
                self.progressChanged.emit(self._progress)
                # move arm to position
                pose = self.get_target_pose(x)
                self.set_position(pose)

                arm_pose = self.get_position()
                jobs = []
                for camera in self.cameras:
                    name = camera.name
                    if name not in self.config:
                        logger.debug(f"Camera {name} not in config, skipping")
                        continue
                    camera_param = self.config[name]
                    camera_offset = Pose(**camera_param["offset"])
                    camera_pose = arm_pose + camera_offset

                    metadata = {
                        **camera_param,
                        "camera_name": name,
                        "approximate_pose": [camera_pose.x, camera_pose.y, camera_pose.z, camera_pose.pan,
                                             camera_pose.tilt],
                        "shot_id": shot_id,
                    }
                    shot_id += 1
                    jobs.append(executor.submit(self.grab, shot_id, metadata, camera))
                wait(jobs, return_when=ALL_COMPLETED)
        logger.info(f"Scan completed")
