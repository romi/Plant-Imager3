import zmq
from PySide6.QtCore import QObject, Slot, Signal
from simplejpeg import decode_jpeg

from plantimager.commons.RPC import RPCClient
from plantimager.commons.cameradevice import Camera
from plantimager.commons.deviceregistry import DeviceRegistry


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

    def __init__(self, context: zmq.Context, url: str, parent: QObject = None):
        QObject.__init__(self, parent)
        self.camera = PiCameraProxy(context, url)

    @Slot()
    def getImage(self):
        buffer, buffer_info = self.camera.get_image()
        self.imageReady.emit(buffer, buffer_info)

    @Slot()
    def startVideo(self):
        self.camera.start_video()

    @Slot()
    def stopVideo(self):
        self.camera.stop_video()

