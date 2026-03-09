import os.path
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

class DisplayMode(StrEnum):
    NORMAL = "normal"
    FOCUS = "focus"
    ZOOMED = "zoomed"
    ZOOMED_FOCUS = "zoomed-focus"
    ALIGN = "align"

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
    rotationChanged = Signal(int)
    displayModeChanged = Signal(str)

    def __init__(self, name: str, address: str, context: zmq.Context, parent: QObject = None):
        super().__init__(parent)
        self._name = name
        self._address = address
        self._video_source = ""
        self._image_source = ""
        self._displayMode = DisplayMode.NORMAL
        if name == "empty" or address == "":
            self._status = States.INVALID
            self.camera = None
            self._mode = "STILL"
            self._rotation = 0
            return
        self._status = States.DISCONNECTED

        self.camera = PiCameraComm(context, address)
        self.camera.imageReady.connect(self._newImage)
        self.camera.modeChanged.connect(self._modeChanged)
        self.camera.videoUrlChanged.connect(self._videoUrlChanged)
        self._mode: Literal["VIDEO", "STILL"]  = self.camera.mode
        self._rotation: int = self.camera.rotation
        self.camera.rotationChanged.connect(self._camera_rotation_change_handler)
        self._status = States.CONNECTED
        finalize(self, self._stop)
        self._i = 0

    def _stop(self):
        """Handles termination of CameraBridge (to use with weakref.finalize)"""
        logger.debug(f"finalizing bridge {self._name}")
        self._video_source = ""
        self._image_source = ""
        self._status = States.INVALID

        del self.camera
        logger.debug(f"bridge {self._name} finalized")


    @Slot()
    def getImage(self):
        """Gets a high-resolution image from the camera"""
        if self.camera:
            self.camera.getImage()

    @Slot()
    def getLoresImage(self):
        """Gets a low-resolution image from the camera"""
        if self.camera:
            self.camera.getImage(lores=True)

    @Property(str, notify=modeChanged)
    def mode(self):
        return self._mode
    @mode.setter
    def mode(self, value: Literal["VIDEO", "STILL"]):
        if self._mode != value and self.camera:
            self.camera.mode = value

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
        if not self._image_source:
            logger.debug("no image source")
            return ""
        if self._displayMode == DisplayMode.FOCUS:
            path = os.path.split(self._image_source)[0] + "/focus-" + os.path.split(self._image_source)[1]
        elif self._displayMode == DisplayMode.ZOOMED:
            path = os.path.split(self._image_source)[0] + "/zoomed-" + os.path.split(self._image_source)[1]
        elif self._displayMode == DisplayMode.ZOOMED_FOCUS:
            path = os.path.split(self._image_source)[0] + "/zoomed-focus-" + os.path.split(self._image_source)[1]
        elif self._displayMode == DisplayMode.ALIGN:
            path = os.path.split(self._image_source)[0] + "/align-" + os.path.split(self._image_source)[1]
        else:
            path = self._image_source
        return path

    @Slot(int)
    def _camera_rotation_change_handler(self, value: int):
        if value != self._rotation:
            self._rotation = value
            self.rotationChanged.emit(value)

    @Property(int, notify=rotationChanged)
    def rotation(self) -> int:
        return self._rotation
    @rotation.setter
    def rotation(self, value: int):
        if self.camera:
            self.camera.rotation = value % 360

    @Property(str, notify=displayModeChanged)
    def displayMode(self) -> DisplayMode:
        return self._displayMode
    @displayMode.setter
    def displayMode(self, value: DisplayMode):
        if self._displayMode != value:
            self._displayMode = value
            self.displayModeChanged.emit(self._displayMode)
            self.imageSourceChanged.emit(self.imageSource)

    @Slot()
    def nextDisplayMode(self):
        if self._displayMode == DisplayMode.NORMAL:
            self.displayMode = DisplayMode.FOCUS
            return
        elif self._displayMode == DisplayMode.FOCUS:
            self.displayMode = DisplayMode.ZOOMED
            return
        elif self._displayMode == DisplayMode.ZOOMED:
            self.displayMode = DisplayMode.ZOOMED_FOCUS
            return
        elif self._displayMode == DisplayMode.ZOOMED_FOCUS:
            self.displayMode = DisplayMode.ALIGN
            return
        elif self._displayMode == DisplayMode.ALIGN:
            self.displayMode = DisplayMode.NORMAL
            return
