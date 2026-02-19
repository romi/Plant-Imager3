from concurrent.futures import ThreadPoolExecutor, Future
from typing import Literal
from weakref import finalize

import zmq
from PySide6.QtCore import QObject, Slot, Signal, Property

from plantimager.commons.RPC import RPCClient
from plantimager.commons.cameradevice import Camera


@RPCClient.register_interface(Camera)
class PiCameraProxy(Camera, RPCClient):
    def __init__(self, context: zmq.Context, url: str):
        Camera.__init__(self)
        RPCClient.__init__(self, context, url)


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

    def __init__(self, context: zmq.Context, url: str, parent: QObject = None):
        QObject.__init__(self, parent)
        self.camera = PiCameraProxy(context, url)
        self._thread_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"{self.__class__.__name__}Thread")
        self.camera.modeChanged.connect(lambda mode: self.modeChanged.emit(mode))
        self.camera.videoUrlChanged.connect(lambda u: self.videoUrlChanged.emit(u))
        self.camera.rotationChanged.connect(lambda rot: self.rotationChanged.emit(rot))
        self.camera.resolutionChanged.connect(lambda *res: self.resolutionChanged.emit(*res))
        self.camera.encodingChanged.connect(lambda e: self.encodingChanged.emit(e))
        self.camera.configChanged.connect(lambda c: self.configChanged.emit(c))
        finalize(self, self._finalize)

    def _finalize(self):
        self._thread_pool.shutdown(cancel_futures=True)
        self.camera.stop_server()

    @Slot(bool, result=Future)
    def getImage(self, lores=False) -> Future[tuple[memoryview, dict]]:
        """
        Submits a call to camera.get_image() and returns a future representing the pending result.
        When camera.get_image() returns and the result is available, the signal imageReady is emitted.

        Returns
        -------
        future : Future[tuple[memoryview, dict]]

        """
        def _callback(ft_: Future):
            if ft_.cancelled(): return
            res = ft_.result()
            if res:
                buffer, buffer_info = res
                self.imageReady.emit(buffer, buffer_info)
        ft = self._thread_pool.submit(self.camera.get_image, lores=lores)
        ft.add_done_callback(_callback)
        return ft

    @Property(str, notify=modeChanged)
    def mode(self) -> Literal["VIDEO", "STILL"]:
        return self.camera.mode
    @mode.setter
    def mode(self, value: Literal["VIDEO", "STILL"]):
        self._thread_pool.submit(lambda : setattr(self.camera, "mode", value))

    @Property(str, notify=videoUrlChanged)
    def videoUrl(self):
        return self.camera.video_url

    @Property(int, notify=rotationChanged)
    def rotation(self):
        return self.camera.rotation
    @rotation.setter
    def rotation(self, value: int):
        self._thread_pool.submit(lambda : setattr(self.camera, "rotation", value))

    @Property(str)
    def name(self):
        return self.camera.name

    @Property(int, notify=resolutionChanged)
    def resolution(self):
        return self.camera.resolution
    @resolution.setter
    def resolution(self, value: tuple[int, int]):
        self._thread_pool.submit(lambda : setattr(self.camera, "resolution", value))

    @Property(int, notify=encodingChanged)
    def encoding(self):
        return self.camera.resolution
    @encoding.setter
    def encoding(self, value: tuple[int, int]):
        self._thread_pool.submit(lambda : setattr(self.camera, "encoding", value))

    @Property(int, notify=configChanged)
    def config(self):
        return self.camera.config
    @config.setter
    def config(self, value: tuple[int, int]):
        self._thread_pool.submit(lambda : setattr(self.camera, "config", value))
