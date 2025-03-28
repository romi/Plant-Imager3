import os
import sys
import socket

import av
import zmq
from picamera2 import Picamera2
from picamera2.encoders import H264Encoder
from picamera2.outputs import PyavOutput
from simplejpeg import encode_jpeg

from plantimager.commons.RPC import RPCServer, RPCProperty
from plantimager.commons.cameradevice import Camera, CameraMode

__all__ = ['RPCCamera']

class PyavOutput_nobuffer(PyavOutput):
    def __init__(self, output_name, format=None, pts=None):
        super().__init__(output_name, format=format, pts=pts)

    def start(self):
        self._container = av.open(self._output_name, "w", format=self._format, buffer_size=1024*8)
        self._container.flags = self._container.flags | 0x40
        super(PyavOutput, self).start()

@RPCServer.create_server
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
            {"size": (2028, 1520), "format": "BGR888"},
            queue=False
        )
        self._mode = CameraMode.STILL
        self._video_url = ""
        self.picam.configure(self.still_config)
        self.picam.start()

        # video stuff
        self.encoder: H264Encoder = None
        self.output: PyavOutput_nobuffer = None


    def start_video(self):
        if self._mode != CameraMode.VIDEO:
            print("Starting camera stream")
            self.picam.switch_mode(self.video_config, wait=True)
            print("switched to video mode")
            self.encoder = H264Encoder(bitrate=10_000_000)
            self.output = PyavOutput_nobuffer("tcp://0.0.0.0:8888\?listen=1", format="mpegts")
            self.output.error_callback = self.stop_video
            self.picam.start_encoder(self.encoder, self.output)
            print("Camera stream started")
            self._video_url = f"tcp://{socket.gethostname()}:8888"
            self.videoUrlChanged.emit(self._video_url)
        return f"tcp://{socket.gethostname()}:8888"


    def stop_video(self):
        if self._mode == CameraMode.VIDEO:
            print("Stopping camera stream")
            self.picam.stop_encoder()
            self.encoder = None
            self.output = None
            self._video_url = ""
            self.videoUrlChanged.emit(self._video_url)
            self.picam.switch_mode(self.still_config, wait=True)
            print("switched to still mode")
        return "VIDEO STOPPED"

    @RPCServer.register_method_buffer
    def get_image(self) -> (memoryview, dict):
        if self._mode != CameraMode.STILL:
            self.mode = CameraMode.STILL
        image = self.picam.capture_array()
        # buffer = jpegxl_encode(image, lossless=True, effort=2)
        buffer = encode_jpeg(image, quality=95, colorsubsampling="420", fastdct=True)
        return memoryview(buffer), {"format": "jpeg"}

    @RPCProperty(notify=Camera.modeChanged)
    def mode(self):
        return self._mode
    @mode.setter
    def mode(self, value):
        if value != self._mode and value==CameraMode.STILL:
            self.stop_video()
            self._mode = CameraMode.STILL
            self.modeChanged.emit(value)
        if value != self._mode and value==CameraMode.VIDEO:
            self.start_video()
            self._mode = CameraMode.VIDEO
            self.modeChanged.emit(value)

    @RPCProperty(notify=Camera.videoUrlChanged)
    def video_url(self) -> str:
        return self._video_url


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