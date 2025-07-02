import os
import subprocess
import sys
import socket

import av
import numpy as np
import zmq
from picamera2 import Picamera2
from picamera2.encoders import H264Encoder
from picamera2.outputs import PyavOutput
from simplejpeg import encode_jpeg, encode_jpeg_yuv_planes

from plantimager.commons.RPC import RPCServer, RPCProperty
from plantimager.commons.cameradevice import Camera, CameraMode
from plantimager.commons.systemd import notify_ready, notify_stopping, notify_watchdog

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
        max_res = self.picam.camera_properties["PixelArraySize"]
        print(self.picam.camera_properties)
        self.video_config = self.picam.create_video_configuration(
            {"size": (640, 480), "format": "YUV420"},
            controls={'FrameRate': 15}
        )
        self.still_config = self.picam.create_still_configuration(
            {"size": (max_res[0]//2, max_res[1]//2), "format": "BGR888"}, lores={"size": (640, 480)},
            queue=False
        )
        self._mode = CameraMode.STILL
        self._video_url = ""
        self.picam.configure(self.still_config)
        self.picam.start()

        # video stuff
        self.encoder: H264Encoder = None
        self.output: PyavOutput_nobuffer = None

        # config
        self._rotation = 90


    def start_video(self):
        if self._mode != CameraMode.VIDEO:
            print("Starting camera stream")
            self.picam.switch_mode(self.video_config, wait=True)
            self._mode = CameraMode.VIDEO
            print("switched to video mode")
            self.encoder = H264Encoder(bitrate=10_000_000)
            self.output = PyavOutput_nobuffer("tcp://0.0.0.0:8888\?listen=1", format="mpegts")
            # self.output.error_callback = callback
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
            self._mode = CameraMode.STILL
            print("switched to still mode")
        return "VIDEO STOPPED"

    @RPCServer.register_method_buffer(timeout=None)
    def get_image(self, lores=False) -> (memoryview, dict):
        if self._mode != CameraMode.STILL:
            self.mode = CameraMode.STILL
        if lores:
            height, width = self.still_config["lores"]["size"]
            image: np.ndarray = self.picam.capture_array("lores")
            padding = image.shape[1] - height
            Y = image[:width, :height]
            U = np.zeros((width//2, height//2), dtype=np.uint8)
            V = np.zeros((width//2, height//2), dtype=np.uint8)
            U[::2, :] = image[width:width+width//4, :height//2]
            U[1::2, :] = image[width:width+width//4, height//2+padding//2:height+padding//2]
            V[::2, :] = image[width+width//4:, :height//2]
            V[1::2, :] = image[width+width//4:, height//2+padding//2:height+padding//2]
            buffer = encode_jpeg_yuv_planes(Y, U, V, quality=95, fastdct=True)
        else:
            image: np.ndarray = self.picam.capture_array()
            buffer = encode_jpeg(image, quality=95, colorsubsampling="420", fastdct=True)
        # buffer = jpegxl_encode(image, lossless=True, effort=2)
        return memoryview(buffer), {"format": "jpeg", "rotation": self._rotation, "size": image.shape, "channel": "rgb"}

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

    @RPCProperty(notify=Camera.rotationChanged)
    def rotation(self):
        return self._rotation
    @rotation.setter
    def rotation(self, value):
        if value != self._rotation:
            self._rotation = value % 360

    @RPCProperty(notify=Camera.resolutionChanged)
    def resolution(self) -> tuple[int, int]:
        return self.still_config.get("size")
    @resolution.setter
    def resolution(self, value: tuple[int, int]):
        if value != self.still_config.get("size"):
            x_max, y_max = self.picam.camera_properties["PixelArraySize"]
            self.still_config["main"]["size"] = max(60, min(value[0], x_max)), max(60, min(value[1], y_max))
            if self._mode == CameraMode.STILL:
                self.picam.switch_mode(self.still_config, wait=True)
            self.resolutionChanged.emit(self.still_config["main"]["size"])



def main():
    REGISTRY_ADDR = os.getenv("PI_REGISTRY") or "localhost:5555"
    if not REGISTRY_ADDR.startswith("tcp://"):
        REGISTRY_ADDR = "tcp://" + REGISTRY_ADDR
    context = zmq.Context()
    ip_addr = os.getenv("IP_ADDR") or subprocess.call()
    camera = RPCCamera(context, f"tcp://{ip_addr}")
    notify_ready()
    camera.register_to_registry(
        "camera",
        socket.gethostname(),
        REGISTRY_ADDR
    )
    camera.serve_forever()
    notify_stopping()

if __name__ == "__main__":
    main()