import weakref
from concurrent.futures import Future
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from enum import StrEnum
from typing import Any
from typing import Literal
from weakref import finalize

import zmq
from PySide6.QtCore import Property
from PySide6.QtCore import QObject
from PySide6.QtCore import Signal
from PySide6.QtCore import Slot

from plantimager.commons.RPC import RPCClient
from plantimager.commons.cameradevice import Camera
from plantimager.commons.logging import create_logger

logger = create_logger(__name__)


class CameraStates(StrEnum):
    DISCONNECTED = "disconnected"
    INVALID = "invalid"
    CONNECTED = "connected"
    WAITING = "waiting"


@RPCClient.register_interface(Camera)
class PiCameraProxy(Camera, RPCClient):
    def __init__(self, context: zmq.Context, url: str):
        Camera.__init__(self)
        RPCClient.__init__(self, context, url, timeout=5000)


class PiCameraComm(QObject):
    """
    Object that will handle communication with the picamera. Meant to live in a separate thread.

    Serves as a bridge between Qt and the picamera.

    After init use moveToThread() to change the execution context.
    """

    imageReady = Signal(memoryview, dict)
    modeChanged = Signal(str)
    videoUrlChanged = Signal(str)
    rotationChanged = Signal(int)
    resolutionChanged = Signal(int, int)
    encodingChanged = Signal(str)
    configChanged = Signal(dict)
    stateChanged = Signal(str)

    def __init__(self, context: zmq.Context, url: str, parent: QObject = None):
        QObject.__init__(self, parent)
        self._state = CameraStates.DISCONNECTED
        self._context = context
        self.url = url
        self._thread_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"{self.__class__.__name__}Thread")
        self._camera: PiCameraProxy | None = None
        self._attempt_connection()

        def _finalizer(pool, camera):
            pool.shutdown(wait=False)
            if camera:
                camera.stop_server()

        finalize(self, _finalizer, self._thread_pool, self._camera)

    def _attempt_connection(self):
        weak_self = weakref.ref(self)

        def _attempt_connection_callback(ft: Future[PiCameraProxy]):
            s = weak_self()
            if s is None:
                return
            if ft.exception() is None:
                s._camera = ft.result()
                s._camera.modeChanged.connect(lambda mode: (obj := weak_self()) and obj.modeChanged.emit(mode))
                s._camera.videoUrlChanged.connect(lambda u: (obj := weak_self()) and obj.videoUrlChanged.emit(u))
                s._camera.rotationChanged.connect(lambda rot: (obj := weak_self()) and obj.rotationChanged.emit(rot))
                s._camera.resolutionChanged.connect(
                    lambda res: (obj := weak_self()) and obj.resolutionChanged.emit(*res))
                s._camera.encodingChanged.connect(lambda e: (obj := weak_self()) and obj.encodingChanged.emit(e))
                s._camera.configChanged.connect(lambda c: (obj := weak_self()) and obj.configChanged.emit(c))
                s._set_state(CameraStates.CONNECTED)
            else:
                # logger.warning("Connection failed")
                s._attempt_connection()

        future = self._thread_pool.submit(lambda: PiCameraProxy(self._context, self.url))
        future.add_done_callback(_attempt_connection_callback)

    @contextmanager
    def camera(self):
        current_state = self.state
        try:
            if current_state == CameraStates.DISCONNECTED:
                yield None
            else:
                self._set_state(CameraStates.WAITING)
                yield self._camera
        except TimeoutError:
            self._set_state(CameraStates.DISCONNECTED)
            self._attempt_connection()
        else:
            self._set_state(current_state)

    def _set_attr_async(self, attr_name: str, value: Any) -> None:
        def callback(ft_: Future):
            if ft_.exception():
                self._set_state(CameraStates.DISCONNECTED)
                self._attempt_connection()
            else:
                self._set_state(CameraStates.CONNECTED)

        if self._camera and self.state == CameraStates.CONNECTED:
            self._set_state(CameraStates.WAITING)
            ft = self._thread_pool.submit(lambda: setattr(self._camera, attr_name, value))
            ft.add_done_callback(callback)

    @Property(str, notify=stateChanged)
    def state(self) -> CameraStates:
        return self._state

    def _set_state(self, state: CameraStates):
        if state != self._state and state in CameraStates:
            self._state = state
            self.stateChanged.emit(state.value)

    @Slot(bool, result=Future)
    def getImage(self, lores=False) -> Future[tuple[memoryview, dict]] | None:
        """
        Submits a call to camera.get_image() and returns a future representing the pending result.
        When camera.get_image() returns and the result is available, the signal imageReady is emitted.

        Returns
        -------
        Future[tuple[memoryview, dict]] or None
            Returns ``None`` when the camera is unavailable
        """

        def _callback(ft_: Future):
            if ft_.cancelled(): return
            res = ft_.result()
            if res:
                buffer, buffer_info = res
                self._set_state(CameraStates.CONNECTED)
                self.imageReady.emit(buffer, buffer_info)

        if self._camera and self.state == CameraStates.CONNECTED:
            self._set_state(CameraStates.WAITING)
            ft = self._thread_pool.submit(self._camera.get_image, lores=lores)
            ft.add_done_callback(_callback)
            return ft
        else:
            return None

    @Property(str, notify=modeChanged)
    def mode(self) -> Literal["VIDEO", "STILL"]:
        with self.camera() as camera:
            val = camera.mode if camera is not None else "STILL"
        return val

    @mode.setter
    def mode(self, value: Literal["VIDEO", "STILL"]):
        self._set_attr_async("mode", value)

    @Property(str, notify=videoUrlChanged)
    def videoUrl(self):
        with self.camera() as camera:
            val = camera.video_url if camera is not None else ""
        return val

    @Property(int, notify=rotationChanged)
    def rotation(self):
        with self.camera() as camera:
            val = camera.rotation if camera is not None else 0
        return val

    @rotation.setter
    def rotation(self, value: int):
        self._set_attr_async("rotation", value)

    @Property(str)
    def name(self):
        with self.camera() as camera:
            val = camera.name if camera is not None else ""
        return val

    @Property(int, notify=resolutionChanged)
    def resolution(self):
        with self.camera() as camera:
            val = camera.resolution if camera else (-1, -1)
        return val

    @resolution.setter
    def resolution(self, value: tuple[int, int]):
        self._set_attr_async("resolution", value)

    @Property(int, notify=encodingChanged)
    def encoding(self):
        with self.camera() as camera:
            val = camera.encoding if camera else ""
        return val

    @encoding.setter
    def encoding(self, value: tuple[int, int]):
        self._set_attr_async("encoding", value)

    @Property(int, notify=configChanged)
    def config(self):
        with self.camera() as camera:
            val = camera.config if camera else {}
        return val

    @config.setter
    def config(self, value: tuple[int, int]):
        self._set_attr_async("config", value)
