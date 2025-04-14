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

    After init use moveToThread() to change the execution context.
    """

    imageReady = Signal(memoryview, dict)
    modeChanged = Signal(str)
    videoUrlChanged = Signal(str)
    rotationChanged = Signal(int)

    def __init__(self, context: zmq.Context, url: str, parent: QObject = None):
        QObject.__init__(self, parent)
        self.camera = PiCameraProxy(context, url)
        self._thread_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"{self.__class__.__name__}Thread")
        self.camera.modeChanged.connect(lambda *args: self.modeChanged.emit(*args))
        self.camera.videoUrlChanged.connect(lambda *args: self.videoUrlChanged.emit(*args))
        self.camera.rotationChanged.connect(lambda *args: self.rotationChanged.emit(*args))
        finalize(self, self._finalize)

    def _finalize(self):
        self._thread_pool.shutdown(cancel_futures=True)
        self.camera.stop_server()

    @Slot()
    def getImage(self):
        def _callback(ft_: Future):
            if ft_.cancelled(): return
            res = ft_.result()
            if res:
                buffer, buffer_info = res
                self.imageReady.emit(buffer, buffer_info)
        ft = self._thread_pool.submit(self.camera.get_image)
        ft.add_done_callback(_callback)

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
