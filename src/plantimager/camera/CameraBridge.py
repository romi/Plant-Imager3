from enum import Flag, auto, StrEnum

from PySide6.QtCore import Qt, QThread, QTimer, QObject, Signal, Slot, Property
from PySide6.QtGui import QImage
from PySide6.QtMultimedia import QVideoFrame, QVideoSink
from PySide6.QtQml import QmlElement

QML_IMPORT_NAME = "PlantImagerApp.Camera"
QML_IMPORT_MAJOR_VERSION = 1


class StatusClass(StrEnum):
    OK = "ok"
    ERROR = "error"
    WARNING = "warning"
    INACTIVE = "inactive"

class States(StrEnum): # TODO: redo statuses when communication with picamera is figured out
    DISCONNECTED = "disconnected"
    CONNECTED = "connected"
    VIDEO_READY = "video ready"
    VIDEO_ERROR = "video error"

STATE_TO_CLASS = {
    States.DISCONNECTED: StatusClass.INACTIVE,
    States.CONNECTED: StatusClass.OK,
    States.VIDEO_READY: StatusClass.OK,
    States.VIDEO_ERROR: StatusClass.ERROR,
}

@QmlElement
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

    def __init__(self, parent: QObject = None):
        super().__init__(parent)
        self._name = "picamera2"
        self._address = "picamera2.wlan"
        self._status = States.DISCONNECTED

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

