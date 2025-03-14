import logging
import sys
from enum import Flag, auto, StrEnum
from weakref import finalize

import zmq
from PySide6.QtCore import QThread, QObject, Signal, Slot, Property, QMetaObject, Qt
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
    videoReady = Signal()

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
        self._commThread.setObjectName(f"CommThread-{name}")
        self._camera = PiCameraComm(context, address)
        self._camera.moveToThread(self._commThread)
        self._commThread.finished.connect(self._camera.deleteLater)
        self._camera.imageReady.connect(self._newImage)
        self._camera.videoReady.connect(self._videoReady)
        finalize(self, self._stop)
        self._i = 0

        self._commThread.start()

    def _stop(self):
        """Handles termination of CameraBridge (to use with weakref.fialize)"""
        logger.debug(f"finalizing bridge {self._name}")
        self._video_source = ""
        self._image_source = ""
        self._status = States.INVALID

        del self._camera
        self._commThread.quit()
        self._commThread.wait()
        del self._commThread
        logger.debug(f"bridge {self._name} finalized")


    @Slot()
    def getImage(self):
        if self._camera:
            QMetaObject.invokeMethod(self._camera, "getImage", Qt.ConnectionType.QueuedConnection)

    @Slot()
    def startVideo(self):
        if self._camera:
            QMetaObject.invokeMethod(self._camera, "startVideo", Qt.ConnectionType.QueuedConnection)

    @Slot()
    def stopVideo(self):
        if self._camera:
            QMetaObject.invokeMethod(self._camera, "stopVideo", Qt.ConnectionType.QueuedConnection)

    @Slot(str)
    def _videoReady(self, source: str):
        self._video_source = source
        self.videoSourceChanged.emit(self._video_source)
        self.videoReady.emit()

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

