import logging
import sys
from enum import Flag, auto, StrEnum

import zmq
from PySide6.QtCore import QThread, QObject, Signal, Slot, Property
from PySide6.QtQml import QmlElement, QmlUncreatable

from plantimager.controller.camera.PiCameraComm import PiCameraComm
from plantimager.controller.ImageProvider import imageProvider

QML_IMPORT_NAME = "PlantImagerApp.Camera"
QML_IMPORT_MAJOR_VERSION = 1

logger = logging.Logger("AppBridge")
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.StreamHandler(sys.stderr))

class StatusClass(StrEnum):
    OK = "ok"
    ERROR = "error"
    WARNING = "warning"
    INACTIVE = "inactive"

class States(StrEnum): # TODO: redo statuses when communication with picamera is figured out
    DISCONNECTED = "disconnected"
    INVALID = "invalid"
    CONNECTED = "connected"
    VIDEO_READY = "video ready"
    VIDEO_ERROR = "video error"

STATE_TO_CLASS = {
    States.DISCONNECTED: StatusClass.INACTIVE,
    States.INVALID: StatusClass.ERROR,
    States.CONNECTED: StatusClass.OK,
    States.VIDEO_READY: StatusClass.OK,
    States.VIDEO_ERROR: StatusClass.ERROR,
}

@QmlElement
@QmlUncreatable("Camera bridge cannot be created from QML")
class CameraBridge(QObject):
    """
    Bridge for Picamera to Qt Quick

    Properties:
    name
    address
    status
    statusClass
    """

    nameChanged = Signal(str)
    addressChanged = Signal(str)
    statusChanged = Signal(str)
    statusClassChanged = Signal(str)
    videoSourceChanged = Signal(str)
    imageSourceChanged = Signal(str)

    def __init__(self, name: str, address: str, context: zmq.Context, parent: QObject = None):
        super().__init__(parent)
        self._name = name
        self._address = address
        self._video_source = ""
        self._image_source = ""
        if name == "empty" or address == "":
            self._status = States.INVALID
            self._camera = None
            return
        self._status = States.DISCONNECTED


        self._commThread = QThread()
        self._camera = PiCameraComm(context, address)
        self._camera.moveToThread(self._commThread)
        self._commThread.finished.connect(self._camera.deleteLater)
        self._camera.imageReady.connect(self._newImage)
        self.destroyed.connect(self._commThread.terminate)
        self._i = 0

        self._commThread.start()


    @Slot()
    def getImage(self):
        if self._camera:
            self._camera.getImage()

    @Slot()
    def startVideo(self):
        if self._camera:
            self._camera.startVideo()

    @Slot()
    def stopVideo(self):
        if self._camera:
            self._camera.stopVideo()

    @Slot(memoryview, dict)
    def _newImage(self, buffer: memoryview, buffer_info: dict):
        imageProvider.addImageFromBuffer(f"{self._name}-{self._i}", buffer, buffer_info)
        self._image_source = f"image://provider/{self._name}-{self._i}"
        self.imageSourceChanged.emit(self._image_source)
        self._i  = (self._i + 1) % 2

    @Property(str, notify=nameChanged)
    def name(self) -> str:
        return self._name

    @Property(str, notify=addressChanged)
    def address(self) -> str:
        return self._address

    @Property(str, notify=statusChanged)
    def status(self) -> str:
        return self._status

    @Property(str, notify=statusClassChanged)
    def statusClass(self) -> str:
        return STATE_TO_CLASS[self._status]

    @Property(str, notify=videoSourceChanged)
    def videoSource(self) -> str:
        return self._video_source

    @Property(str, notify=imageSourceChanged)
    def imageSource(self) -> str:
        return self._image_source

