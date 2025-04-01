import sys
from enum import StrEnum
from typing import Literal
from weakref import finalize

import zmq
from PySide6.QtCore import QObject, Signal, Slot, Property
from PySide6.QtQml import QmlElement, QmlUncreatable

from plantimager.commons.logging import create_logger
from plantimager.controller.camera.PiCameraComm import PiCameraComm
from plantimager.controller.ImageProvider import imageProvider

QML_IMPORT_NAME = "PlantImagerApp.Camera"
QML_IMPORT_MAJOR_VERSION = 1

logger = create_logger("CameraBridge")

class StatusClass(StrEnum):
    OK = "ok"
    ERROR = "error"
    WARNING = "warning"
    INACTIVE = "inactive"

class States(StrEnum): # TODO: redo statuses when communication with picamera is figured out
    DISCONNECTED = "disconnected"
    INVALID = "invalid"
    CONNECTED = "connected"

STATE_TO_CLASS = {
    States.DISCONNECTED: StatusClass.INACTIVE,
    States.INVALID: StatusClass.ERROR,
    States.CONNECTED: StatusClass.OK,
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
    videoReady = Signal()
    modeChanged = Signal(str)

    def __init__(self, name: str, address: str, context: zmq.Context, parent: QObject = None):
        super().__init__(parent)
        self._name = name
        self._address = address
        self._video_source = ""
        self._image_source = ""
        if name == "empty" or address == "":
            self._status = States.INVALID
            self._camera = None
            self._mode = "STILL"
            return
        self._status = States.DISCONNECTED

        self._camera = PiCameraComm(context, address)
        self._camera.imageReady.connect(self._newImage)
        self._camera.modeChanged.connect(self._modeChanged)
        self._camera.videoUrlChanged.connect(self._videoUrlChanged)
        self._mode: Literal["VIDEO", "STILL"]  = self._camera.mode
        self._status = States.CONNECTED
        finalize(self, self._stop)
        self._i = 0

    def _stop(self):
        """Handles termination of CameraBridge (to use with weakref.finalize)"""
        logger.debug(f"finalizing bridge {self._name}")
        self._video_source = ""
        self._image_source = ""
        self._status = States.INVALID

        del self._camera
        logger.debug(f"bridge {self._name} finalized")


    @Slot()
    def getImage(self):
        if self._camera:
            self._camera.getImage()

    @Property(str, notify=modeChanged)
    def mode(self):
        return self._mode
    @mode.setter
    def mode(self, value: Literal["VIDEO", "STILL"]):
        if self._mode != value and self._camera:
            self._camera.mode = value

    @Slot(str)
    def _modeChanged(self, mode: Literal["VIDEO", "STILL"]):
        self._mode = mode
        self.modeChanged.emit(mode)

    @Slot(str)
    def _videoUrlChanged(self, videoUrl: str):
        self._video_source = videoUrl
        self.videoSourceChanged.emit(self._video_source)
        if videoUrl: self.videoReady.emit()


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

