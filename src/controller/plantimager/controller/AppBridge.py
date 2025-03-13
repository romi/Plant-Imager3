import zmq
from PySide6.QtCore import QObject, QThread, Signal, Slot, QAbstractListModel, Property, QModelIndex, Qt
from PySide6.QtQml import QmlSingleton, QmlElement

from plantimager.commons import deviceregistry
from plantimager.controller.camera.CameraBridge import CameraBridge


QML_IMPORT_NAME = "PlantImagerApp"
QML_IMPORT_MAJOR_VERSION = 1
QML_IMPORT_MINOR_VERSION = 0 # Optional

@QmlElement
class DeviceList(QAbstractListModel):

    def __init__(self, parent=None):
        super(DeviceList, self).__init__(parent)
        self._data: list = []
        self.roles = {
            0: "bridge",
        }

    def rowCount(self, /, parent= ...):
        return len(self._data)

    def data(self, index: QModelIndex, /, role: int = ...) -> object:
        return self._data[index.row()][role]

    def setData(self, index: QModelIndex, value: object, /, role: int = ...) -> bool:
        if index.row() not in self._data:
            self._data[index.row()] = {}
        self._data[index.row()][role] = value
        self.dataChanged.emit(index, index)
        return True

    def roleNames(self) -> dict:
        return self.roles

    def add_new_device(self, device: CameraBridge):
        self.beginInsertRows(QModelIndex(), len(self._data), len(self._data))
        self._data.append({0: device})
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
    deviceListChanged = Signal(DeviceList)
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
        self._registryNewDevice.connect(self._create_new_device, Qt.ConnectionType.QueuedConnection)
        self._registryRemoveDevice.connect(self._remove_device_callback, Qt.ConnectionType.QueuedConnection)
        self.destroyed.connect(self.registry.stop)
        self.device_list: DeviceList = DeviceList(self)

        self._currentCamera = CameraBridge("name", "", self.context)

        self.registry.start()

    @Property(QObject, notify=currentCameraChanged)
    def currentCamera(self) -> CameraBridge:
        return self._currentCamera
    @currentCamera.setter
    def currentCamera(self, camera: CameraBridge):
        if self._currentCamera is not camera:
            self._currentCamera = camera
            self.currentCameraChanged.emit(camera)

    @Property(DeviceList, notify=deviceListChanged)
    def deviceList(self) -> DeviceList:
        return self.device_list

    @Slot(str, str, str)
    def _create_new_device(self, device_type: str, addr: str, name: str):
        if device_type.lower() == "camera": # TODO: probably wrong
            new_bridge = CameraBridge(name, addr, self.context)
            self.device_list.add_new_device(new_bridge)
            if not self.currentCamera:
                self.currentCamera = new_bridge
                self.currentCameraChanged.emit(new_bridge)

    def _new_device_callback(self, device_type: str, addr: str, name: str):
        self._registryNewDevice.emit(device_type, addr, name)

    @Slot(str, str, str)
    def _remove_device(self, device_type: str, addr: str, name: str):
        to_remove = []
        for i, device in enumerate(self.device_list._data):
            bridge: CameraBridge = device[0]
            if bridge.name == name:
                to_remove.append(bridge)
        for bridge in to_remove:
            self.device_list.remove_device(bridge)

    def _remove_device_callback(self, device_type: str, addr: str, name: str):
        self._registryRemoveDevice.emit(device_type, addr, name)