from weakref import finalize

import zmq
from PySide6.QtCore import QObject, QThread, Signal, Slot, QAbstractListModel, Property, QModelIndex, Qt, QStringListModel
from PySide6.QtQml import QmlSingleton, QmlElement

from threading import Thread

from plantimager.commons import deviceregistry
from plantimager.commons.logging import create_logger
from plantimager.controller.camera.CameraBridge import CameraBridge
from plantimager.controller.scanner.rpc_controller import RPCControllerServer
from plantimager.controller.scanner.scanner import Scanner

logger = create_logger("AppBridge")

QML_IMPORT_NAME = "PlantImagerApp"
QML_IMPORT_MAJOR_VERSION = 1
QML_IMPORT_MINOR_VERSION = 0 # Optional

@QmlElement
@QmlSingleton
class AppBridge(QObject):
    """
    Singleton class which is the main bridge of the application.

    AppBridge is a shared object accessible across the application.
    It initializes the zmq context and a device registry. When a new device is registered it creates the
    appropriate bridge for the application.

    Attributes
    ----------
    context: zmq.Context
        Unique ZMQ context of the application.
    registry: deviceregistry.DeviceRegistry
        Device registry of the application.
    device_list: list[str]
        List of device names.
    device_bridges: list[CameraBridge]
        List of camera bridges.

    """

    currentCameraChanged = Signal(QObject)
    deviceListChanged = Signal()
    scannerChanged = Signal(QObject)
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
        self._scanner = Scanner()

        self._controller_server = RPCControllerServer(self.context, "tcp://localhost:14567", self._scanner)
        self.scannerChanged.connect(self._controller_server.handle_scanner_changed)
        self._controller_thread = Thread(target=self._controller_server.serve_forever, name="RPCControllerServer")
        self._controller_thread.daemon = True
        self._controller_thread.start()

        self.registry.start()

    def _stop(self):
        """Finalizer for AppBridge, should be called through weakref.finalize"""
        logger.debug("finalizing AppBridge")
        self.registry.stop()
        self.registry.join()
        self._controller_server.stop_server()
        self._controller_thread.join(2)
        logger.debug("AppBridge finalized")

    @Property(QObject, notify=currentCameraChanged)
    def currentCamera(self) -> CameraBridge:
        return self._currentCamera
    @currentCamera.setter
    def currentCamera(self, camera: CameraBridge):
        if self._currentCamera is not camera:
            self._currentCamera = camera
            self.currentCameraChanged.emit(camera)

    @Property(QObject, notify=scannerChanged)
    def scanner(self) -> Scanner:
        return self._scanner

    @Slot(int, result=CameraBridge)
    def getCameraBridgeAtIndex(self, index: int) -> CameraBridge:
        """
        (Slot) Returns the camera bridge at a given index.
        Parameters
        ----------
        index: int
            Index of the camera bridge.

        Returns
        -------
        CameraBridge
        """
        return self.device_bridges[index]

    @Property(QObject, notify=deviceListChanged)
    def deviceList(self) -> QStringListModel:
        self.model = QStringListModel(self.device_list)
        return self.model

    @Slot(str, str, str)
    def _create_new_device(self, device_type: str, addr: str, name: str):
        """
        Slot creating a new device if device type is recognized.

        Meant to be connected to the signal `_registryNewDevice` as a QueuedConnection.
        """
        logger.debug(f"New device for {addr}: {device_type}, {name}")
        if device_type.lower() == "camera":
            new_bridge = CameraBridge(name, addr, self.context)
            self.device_list.append(name)
            self.device_bridges.append(new_bridge)
            self.deviceListChanged.emit()
            self.scanner.add_camera(new_bridge.camera)
            if not self._currentCamera:
                self.currentCamera = new_bridge
                self.currentCameraChanged.emit(new_bridge)

    def _new_device_callback(self, device_type: str, addr: str, name: str):
        """
        Callback called by deviceregistry when a new device is registered.

        This must return immediately as to avoid deadlocks.
        Parameters
        ----------
        device_type
        addr
        name

        Returns
        -------

        """
        logger.debug(f"New device callback for {addr}: {device_type}, {name}")
        # emit a signal that is connected with QueuedConnection so that it doesn't block
        self._registryNewDevice.emit(device_type, addr, name)

    @Slot(str, str, str)
    def _remove_device(self, device_type: str, addr: str, name: str):
        """
        Slot removing an existing device.

        Meant to be connected to the signal `_registryRemoveDevice` as a QueuedConnection.
        """
        idx = self.device_list.index(name)
        device = self.device_list[idx]
        self.scanner.remove_camera(device)
        del self.device_list[idx]
        del self.device_bridges[idx]
        if len(self.device_bridges) == 0:
            self._currentCamera = CameraBridge("", "", self.context)
            self.currentCameraChanged.emit(self._currentCamera)
        self.deviceListChanged.emit()

    def _remove_device_callback(self, device_type: str, addr: str, name: str):
        """
        Callback called by deviceregistry when a device is unregistered.

        This must return immediately as to avoid deadlocks.
        Parameters
        ----------
        device_type
        addr
        name

        Returns
        -------

        """
        try:
            # in case callback is called when self underlying c++ object is already destroyed
            # emit a signal that is connected with QueuedConnection so that it doesn't block
            self._registryRemoveDevice.emit(device_type, addr, name)
        except RuntimeError:
            pass