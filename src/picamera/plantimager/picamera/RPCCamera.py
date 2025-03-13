import os
import sys
import socket

import av
import zmq
from picamera2 import Picamera2
from picamera2.encoders import H264Encoder
from picamera2.outputs import PyavOutput
from simplejpeg import encode_jpeg

from plantimager.commons.RPC import RPCServer
from plantimager.commons.cameradevice import Camera

__all__ = ['RPCCamera']

class PyavOutput_nobuffer(PyavOutput):
    def __init__(self, output_name, format=None, pts=None):
        super().__init__(output_name, format=format, pts=pts)

    def start(self):
        self._container = av.open(self._output_name, "w", format=self._format, buffer_size=1024*8)
        self._container.flags = self._container.flags | 0x40
        super(PyavOutput, self).start()


class RPCCamera(Camera, RPCServer):
    def __init__(self, context: zmq.Context, url: str):
        RPCServer.__init__(self, context, url)
        self.picam = Picamera2()
        print(self.picam.camera_properties)
        self.video_config = self.picam.create_video_configuration(
            {"size": (640, 480), "format": "YUV420"},
            controls={'FrameRate': 15}
        )
        self.still_config = self.picam.create_still_configuration(
            {"size": (2028, 1520), "format": "RGB888"},
            queue=False
        )
        self.video_started = False
        self.picam.configure(self.still_config)
        self.picam.start()

        # video stuff
        self.encoder: H264Encoder = None
        self.output: PyavOutput_nobuffer = None

    @RPCServer.register_method_json
    def start_video(self):
        if not self.video_started:
            print("Starting camera stream")
            self.picam.switch_mode(self.video_config, wait=True)
            print("switched to video mode")
            self.encoder = H264Encoder(bitrate=10_000_000)
            self.output = PyavOutput_nobuffer("tcp://0.0.0.0:8888\?listen=1", format="mpegts")
            self.output.error_callback = self.stop_video
            self.video_started = True
            self.picam.start_encoder(self.encoder, self.output)
            print("Camera stream started")
        return f"tcp://{socket.gethostname()}:8888"

    @RPCServer.register_method_json
    def stop_video(self):
        if self.video_started:
            print("Stopping camera stream")
            self.picam.stop_encoder()
            self.encoder = None
            self.output = None
            self.picam.switch_mode(self.still_config, wait=True)
            print("switched to still mode")
            self.video_started = False
        return "VIDEO STOPPED"

    @RPCServer.register_method_buffer
    def get_image(self) -> (memoryview, dict):
        image = self.picam.capture_array()
        # buffer = jpegxl_encode(image, lossless=True, effort=2)
        buffer = encode_jpeg(image, quality=95, colorsubsampling="420", fastdct=True)
        return memoryview(buffer), {"format": "jpeg"}


def main():
    REGISTRY_ADDR = os.getenv("PI_REGISTRY") or "localhost:5555"
    if not REGISTRY_ADDR.startswith("tcp://"):
        REGISTRY_ADDR = "tcp://" + REGISTRY_ADDR
    context = zmq.Context()
    camera = RPCCamera(context, "tcp://10.10.10.3")
    camera.register_to_registry(
        "camera",
        socket.gethostname(),
        REGISTRY_ADDR
    )
    camera.serve_forever()

if __name__ == "__main__":
    main()