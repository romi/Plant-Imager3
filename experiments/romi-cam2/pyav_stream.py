#!/usr/bin/python3

# Example using PyavOutput to serve an MPEG2 transport stream to TCP connections.
# Just point a stream playher at tcp://<Pi-ip-address>:8888

from threading import Event

from picamera2 import Picamera2
from picamera2.encoders import H264Encoder
from picamera2.outputs import PyavOutput, Output
import av


class PyavOutput_nobuffer(PyavOutput):
    def __init__(self, output_name, format=None, pts=None):
        super().__init__(output_name, format=format, pts=pts)

    def start(self):
        self._container = av.open(self._output_name, "w", format=self._format, buffer_size=1024*8)
        self._container.flags = self._container.flags | 0x40
        super(PyavOutput, self).start()


event = Event()


def callback(e):
    event.set()

if __name__ == '__main__':
    picam2 = Picamera2()
    config = picam2.create_video_configuration({"size": (640, 480), "format": "YUV420"},
                                                controls={'FrameRate': 15})
    picam2.configure(config)

    while True:
        encoder = H264Encoder(bitrate=10000000)
        output = PyavOutput_nobuffer("tcp://0.0.0.0:8888\?listen=1", format="mpegts")  # noqa
        output.error_callback = callback
        picam2.start_recording(encoder, output)

        event.wait()
        event.clear()
        print("Client disconnected")

        picam2.stop_recording()
        exit()
