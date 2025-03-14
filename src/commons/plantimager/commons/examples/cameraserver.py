import zmq
from simplejpeg import encode_jpeg
import numpy as np

from plantimager.commons.RPC import RPCServer
from plantimager.commons.cameradevice import Camera


class DummyCamera(Camera, RPCServer):
    def __init__(self, context: zmq.Context, url: str):
        RPCServer.__init__(self, context, url)

    @RPCServer.register_method_json
    def start_video(self):
        print("Starting camera stream")
        raise RuntimeError("exception test")
        return "VIDEO STARTED"

    @RPCServer.register_method_json
    def stop_video(self):
        print("Stopping camera stream")
        return "VIDEO STOPPED"

    @RPCServer.register_method_buffer
    def get_image(self) -> (memoryview, dict):
        image = np.random.randint(0, 255, (1200, 800, 3), dtype=np.uint8)
        buffer = encode_jpeg(image, quality=95, colorsubsampling="420", fastdct=True)
        return memoryview(buffer), {"format": "jpeg"}

if __name__ == "__main__":
    context = zmq.Context()
    camera = DummyCamera(context, url="tcp://127.0.0.1")
    camera.register_to_registry("camera", DummyCamera.__name__, "tcp://127.0.0.1:5555")
    camera.serve_forever()