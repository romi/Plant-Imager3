import matplotlib.pyplot as plt
import zmq
from scipy import ndimage
from simplejpeg import encode_jpeg
import numpy as np
import scipy

from plantimager.commons.RPC import RPCServer, RPCProperty
from plantimager.commons.cameradevice import Camera, CameraMode

def block_mean(ar, fact):
    assert isinstance(fact, int), type(fact)
    sx, sy, *others = ar.shape
    assert len(others) <= 1, f"no more than 3 dimensions are allowed, got {len(others)+2}"
    X, Y = np.ogrid[0:sx, 0:sy]
    regions = sy//fact * (X//fact) + Y//fact
    if others:
        max_ = regions.max()
        regions = np.expand_dims(regions, axis=2).repeat(others[0], axis=2)
        regions *= others[0]
        for i in range(1, others[0]):
            regions[:, :, i] += i
    res = ndimage.mean(ar, labels=regions, index=np.arange(regions.max() + 1))
    res.shape = (sx//fact, sy//fact, *others)
    return res


class DummyCamera(Camera, RPCServer):
    def __init__(self, context: zmq.Context, url: str):
        RPCServer.__init__(self, context, url)
        self._mode = CameraMode.STILL
        self._video_url = "tcp://test_url:1234"
        self._rotation = 0

    @RPCServer.register_method_buffer(timeout=10000)
    def get_image(self, lores=False) -> (memoryview, dict):
        if self.mode != CameraMode.STILL:
            self.mode = CameraMode.STILL
        image: np.ndarray[..., np.uint8] = scipy.datasets.face()
        image = plt.imread("/home/arthur/Documents/test_db_plantdb/test_plantimager3_20250718_1/images/picamera2-14.jpeg")
        image = block_mean(image, 5)
        #image = np.clip(image.astype(int) + np.round(np.random.normal(0.0, 0.5, image.shape)), 0, 255)
        buffer = encode_jpeg(image.astype(np.uint8), quality=95, colorsubsampling="420", fastdct=True)
        return memoryview(buffer), {"format": "jpeg", "rotation": self._rotation, "size": image.shape}

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

    @RPCProperty(notify=Camera.rotationChanged)
    def rotation(self):
        return self._rotation
    @rotation.setter
    def rotation(self, value):
        if value != self._rotation:
            self._rotation = value
            self.rotationChanged.emit(value)

    @RPCProperty(notify=Camera.resolutionChanged)
    def resolution(self) -> tuple[int, int]:
        return 640, 480
    @resolution.setter
    def resolution(self, value: tuple[int, int]):
        pass


if __name__ == "__main__":
    context = zmq.Context()
    camera = DummyCamera(context, url="tcp://127.0.0.1")
    camera.register_to_registry("camera", DummyCamera.__name__, "tcp://127.0.0.1:5555")
    camera.serve_forever()