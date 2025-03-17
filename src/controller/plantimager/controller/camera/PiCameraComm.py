from concurrent.futures import ThreadPoolExecutor, Future
from weakref import finalize

import zmq
from PySide6.QtCore import QObject, Slot, Signal

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
    videoReady = Signal(str)

    def __init__(self, context: zmq.Context, url: str, parent: QObject = None):
        QObject.__init__(self, parent)
        self.camera = PiCameraProxy(context, url)
        self._thread_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"{self.__class__.__name__}Thread")
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


    @Slot()
    def startVideo(self):
        def _callback(ft_: Future):
            if ft_.cancelled(): return
            source = ft_.result()
            if source:
                self.videoReady.emit(source)
        ft = self._thread_pool.submit(self.camera.start_video)
        ft.add_done_callback(_callback)

    @Slot()
    def stopVideo(self):
        self._thread_pool.submit(self.camera.stop_video)

