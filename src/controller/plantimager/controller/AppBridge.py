from weakref import finalize

import zmq
from PySide6.QtCore import QObject, QThread, Signal, Slot, QAbstractListModel, Property, QModelIndex, Qt, QStringListModel
from PySide6.QtQml import QmlSingleton, QmlElement

from plantimager.commons import deviceregistry
from plantimager.commons.logging import create_logger
from plantimager.controller.camera.CameraBridge import CameraBridge

logger = create_logger("AppBridge")

QML_IMPORT_NAME = "PlantImagerApp"
QML_IMPORT_MAJOR_VERSION = 1
QML_IMPORT_MINOR_VERSION = 0 # Optional


class DeviceList(QAbstractListModel):

    def __init__(self, parent=None):
        super(DeviceList, self).__init__(parent)
        self._data: list = []
        self.roles = {
            Qt.ItemDataRole.UserRole: "bridge",
        }
        self.dataChanged.connect(lambda *_: print("data changed", self._data))

    def rowCount(self, /, parent= ...):
        return len(self._data)

    def data(self, index: QModelIndex, /, role: int = ...) -> object:
        if 0 <= index.row() < self.rowCount():
            name = self.roleNames().get(role)
            if name:
                return self._data[index.row()][name]

    def setData(self, index: QModelIndex, value: object, /, role: int = ...) -> bool:
        if not (0<=index.row()<self.rowCount()):
            self._data[index.row()] = {}
        self._data[index.row()][role] = value
        self.dataChanged.emit(index, index)
        return True

    def roleNames(self) -> dict:
        return self.roles

    def add_new_device(self, device: CameraBridge):
        self.beginInsertRows(QModelIndex(), self.rowCount(), self.rowCount())
        self._data.append({"bridge": device})
        self.endInsertRows()

    def remove_device(self, device: CameraBridge):
        index = self._data.index({0: device})
        self.beginRemoveRows(QModelIndex(), index, index)
        del self._data[index]
        self.endRemoveRows()



@QmlElement
@QmlSingleton
class AppBridge(QObject):

    currentCameraChanged = Signal(QObject)
    deviceListChanged = Signal()
    _registryNewDevice = Signal(str, str, str)
    _registryRemoveDevice = Signal(str, str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.context = zmq.Context()
        self.registry = deviceregistry.DeviceRegistry(context=self.context)
        # /!\ callback will be executed in registry thread
        # callback will only emit a signal
        # connection must be queued so that the slot is executed in the main thread
        self.registry.add_new_device_callback(self._new_device_callback)
        self.registry.add_device_removed_callback(self._remove_device_callback)
        self.registry.daemon = True
        self._registryNewDevice.connect(self._create_new_device, Qt.ConnectionType.QueuedConnection)
        self._registryRemoveDevice.connect(self._remove_device, Qt.ConnectionType.QueuedConnection)
        finalize(self, self._stop)
        self.device_list: list[str] = []
        self.device_bridges: list[CameraBridge] = []

        self._currentCamera = CameraBridge("", "", self.context)

        self.registry.start()

    def _stop(self):
        logger.debug("finalizing AppBridge")
        self.registry.stop()
        self.registry.join()
        logger.debug("AppBridge finalized")

    @Property(QObject, notify=currentCameraChanged)
    def currentCamera(self) -> CameraBridge:
        return self._currentCamera
    @currentCamera.setter
    def currentCamera(self, camera: CameraBridge):
        if self._currentCamera is not camera:
            self._currentCamera = camera
            self.currentCameraChanged.emit(camera)

    @Slot(int, result=CameraBridge)
    def getCameraBridgeAtIndex(self, index: int) -> CameraBridge:
        return self.device_bridges[index]

    @Property(QObject, notify=deviceListChanged)
    def deviceList(self) -> QStringListModel:
        self.model = QStringListModel(self.device_list)
        return self.model

    @Slot(str, str, str)
    def _create_new_device(self, device_type: str, addr: str, name: str):
        logger.debug(f"New device for {addr}: {device_type}, {name}")
        if device_type.lower() == "camera":
            new_bridge = CameraBridge(name, addr, self.context)
            self.device_list.append(name)
            self.device_bridges.append(new_bridge)
            self.deviceListChanged.emit()
            if not self._currentCamera:
                self.currentCamera = new_bridge
                self.currentCameraChanged.emit(new_bridge)

    def _new_device_callback(self, device_type: str, addr: str, name: str):
        logger.debug(f"New device callback for {addr}: {device_type}, {name}")
        self._registryNewDevice.emit(device_type, addr, name)

    @Slot(str, str, str)
    def _remove_device(self, device_type: str, addr: str, name: str):
        idx = self.device_list.index(name)
        del self.device_list[idx]
        del self.device_bridges[idx]
        if len(self.device_bridges) == 0:
            self._currentCamera = CameraBridge("", "", self.context)
            self.currentCameraChanged.emit(self._currentCamera)
        self.deviceListChanged.emit()

    def _remove_device_callback(self, device_type: str, addr: str, name: str):
        if self:
            self._registryRemoveDevice.emit(device_type, addr, name)