import os
import queue
from concurrent.futures import ThreadPoolExecutor, Future, wait, FIRST_COMPLETED, ALL_COMPLETED
from io import BytesIO
from weakref import finalize

from PySide6.QtCore import QObject, Signal, Slot, Property
from PySide6.QtQml import QmlUncreatable, QmlElement

from plantdb.client.plantdb_client import PlantDBClient

from plantimager.commons.logging import create_logger
from plantimager.controller.camera.PiCameraComm import PiCameraComm
from plantimager.controller.scanner.grbl import CNC
from plantimager.controller.scanner.path import circle, Circle, Path, Pose, PathElement
from plantimager.controller.scanner.hal import DataItem


QML_IMPORT_NAME = "PlantImagerApp.Scanner"
QML_IMPORT_MAJOR_VERSION = 1

logger = create_logger(__name__)

class DataUploader():
    """
    Worker thread that will upload scan data from a queue to a plantdb instance.
    """
    def __init__(self, db_client: PlantDBClient, queue_size: int):
        super().__init__(name=f"{__name__}-worker")
        self.db_client = db_client
        self.jobs: set[Future] = set()
        self.pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix=__name__)
        self.queue_size = queue_size
        finalize(self, self.pool.shutdown, wait=True, cancel_futures=True)

    def _upload(self, scan_id: str, fileset: str, data: DataItem):
        buffer = BytesIO(data.image)
        return self.db_client.create_file(
            buffer, name=f"{fileset}-{data.idx}", ext=data.image_ext,
            scan_id=scan_id, fileset_name=fileset, metadata=data.metadata
        )

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

    def __init__(self, config: dict):
        super().__init__()
        self.config = config
        self.cnc = CNC()
        self.cameras: list[PiCameraComm] = []
        self.db_url = os.getenv("PLANTDB_URL")
        assert self.db_url is not None, "PLANTDB_URL environment variable is not set"
        self.path: Path | None = None

        self._progress = 0
        self._max_progress = 0

        self.db_client = PlantDBClient(self.db_url)
        self.uploader = DataUploader(self.db_client, 10)

    @Slot(QObject)
    def add_camera(self, camera: PiCameraComm):
        self.cameras.append(camera)

    @Slot(QObject)
    def remove_camera(self, camera: PiCameraComm):
        self.cameras.remove(camera)

    @Slot(str)
    def set_url(self, url: str):
        self.db_url = url

    @Property(int, notify=progressChanged)
    def progress(self) -> int:
        return self._progress

    @Property(int, notify=maxProgressChanged)
    def max_progress(self) -> int:
        return self._max_progress


    def configure_scan(self, config: dict):
        """
        Configures the scan from a config dict.

        Configures the cnc, the position of the different cameras and their configuration.
        Configures the path

        Parameters
        ----------
        config

        Returns
        -------

        """
        pass

    @Property(bool, notify=readyToScanChanged)
    def ready_to_scan(self) -> bool:
        if self.cnc and self.path and self.cameras:
            return True
        return False

    def get_position(self) -> Pose:
        """Get the current position of the scanner."""
        x, y, z = self.cnc.get_position()
        pose = Pose(x, y, 0, pan=z, tilt=0)
        return pose

    def set_position(self, pose: Pose) -> None:
        """Set the position of the scanner from a 5D Pose."""
        self.cnc.moveto(pose.x, pose.y, pose.pan)

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
        data = DataItem(idx, buffer, image_ext=buffer_info["format"], metadata=metadata)
        self.uploader.upload(scan_id=self.scan_id, fileset=self.fileset, data=data)


    def inc_count(self) -> int:
        """Incremental counter used to return id for `grab` method. """
        x = self.progress
        self.progress += 1
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

    def scan(self, db_client: PlantDBClient, scan_id: str, fileset: str) -> None:
        if not self.path: raise RuntimeError("Path not set for scan")
        if not self.uploader: raise RuntimeError("Uploader not set for scan")
        self.scan_id = scan_id
        self.fileset = fileset

        with ThreadPoolExecutor(max_workers=4) as executor:
            for x in self.path:
                # move arm to position
                pose = self.get_target_pose(x)
                self.set_position(pose)

                arm_pose = self.get_position()
                jobs = []
                for camera in self.cameras:
                    name = camera.name
                    camera_param = self.config[name]
                    camera_offset = Pose(**camera_param["offset"])
                    camera_pose = arm_pose + camera_offset

                    shot_id = self.inc_count()
                    metadata = {
                        **camera_param,
                        "approximate_pose": [camera_pose.x, camera_pose.y, camera_pose.z, camera_pose.pan, camera_pose.tilt],
                        "shot_id": shot_id,
                    }
                    jobs.append(executor.submit(self.grab, shot_id, metadata, camera))

                wait(jobs, return_when=ALL_COMPLETED)





            f1 = fileset.create_file(data_item1.channels[c1].format_id())
            io.write_image(f1, data_item1.channels[c1].data, ext=self.ext)
            if data_item1.metadata is not None:
                f1.set_metadata(data_item1.metadata)
            f1.set_metadata("shot_id", "%06i" % data_item1.idx)
            f1.set_metadata("channel", c1)



    def scan_at(self, pose: Pose, exact_pose: bool = True, metadata: dict = {}) -> DataItem:
        logger.debug(f"scanning at: {pose}")
        if exact_pose:
            metadata = {**metadata, "pose": [pose.x, pose.y, pose.z, pose.pan, pose.tilt]}
        else:
            metadata = {**metadata, "approximate_pose": [pose.x, pose.y, pose.z, pose.pan, pose.tilt]}
        logger.debug(f"with metadata: {metadata}")
        self.set_position(pose)
        return self.grab(self.inc_count(), metadata=metadata)

