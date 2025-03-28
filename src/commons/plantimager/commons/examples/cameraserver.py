import zmq
from simplejpeg import encode_jpeg
import numpy as np

from plantimager.commons.RPC import RPCServer, RPCProperty
from plantimager.commons.cameradevice import Camera, CameraMode


@RPCServer.create_server
class DummyCamera(Camera, RPCServer):
    def __init__(self, context: zmq.Context, url: str):
        RPCServer.__init__(self, context, url)
        self._mode = CameraMode.STILL
        self._video_url = "tcp://test_url:1234"


    @RPCServer.register_method_buffer
    def get_image(self) -> (memoryview, dict):
        if self.mode != CameraMode.STILL:
            self.mode = CameraMode.STILL
        image = np.random.randint(0, 255, (1200, 800, 3), dtype=np.uint8)
        buffer = encode_jpeg(image, quality=95, colorsubsampling="420", fastdct=True)
        return memoryview(buffer), {"format": "jpeg"}

    @RPCProperty(notify=Camera.modeChanged)
    def mode(self):
        return self._mode
    @mode.setter
    def mode(self, value):
        if value != self._mode:
            self._mode = value
            self._video_url = "tcp://test_url:1234" if value == CameraMode.VIDEO else ""
            self.videoUrlChanged.emit(self._video_url)
            self.modeChanged.emit(value)

    @RPCProperty(notify=Camera.videoUrlChanged)
    def video_url(self) -> str:
        return self._video_url


if __name__ == "__main__":
    context = zmq.Context()
    camera = DummyCamera(context, url="tcp://127.0.0.1")
    camera.register_to_registry("camera", DummyCamera.__name__, "tcp://127.0.0.1:5555")
    camera.serve_forever()