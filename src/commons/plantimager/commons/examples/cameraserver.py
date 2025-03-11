import zmq
from imagecodecs import jpegxl_encode
import numpy as np

from plantimager.commons.RPC import RPCServer
from plantimager.commons.cameradevice import Camera


class DummyCamera(Camera, RPCServer):
    def __init__(self, context: zmq.Context, url: str):
        RPCServer.__init__(self, context, url)

    @RPCServer.register_method_json
    def start_video(self):
        print("Starting camera stream")
        return "VIDEO STARTED"

    @RPCServer.register_method_json
    def stop_video(self):
        print("Stopping camera stream")
        return "VIDEO STOPPED"

    @RPCServer.register_method_buffer
    def get_image(self) -> (memoryview, dict):
        image = np.random.randint(0, 2**16, (1200, 800, 3), dtype=np.uint16)
        buffer = jpegxl_encode(image, lossless=True, effort=2)
        return memoryview(buffer), {"type": "jpegxl"}

if __name__ == "__main__":
    context = zmq.Context()
    camera = DummyCamera(context, url="tcp://127.0.0.1")
    camera.register_to_registry(DummyCamera.__name__, DummyCamera.__name__, "tcp://127.0.0.1:5555")
    camera.serve_forever()