#!/usr/bin/python3

import socket
import time

from picamera2 import Picamera2
from picamera2.encoders import H264Encoder
from picamera2.outputs import FileOutput

picam2 = Picamera2()
video_config = picam2.create_video_configuration({"size": (1280, 720)},
                                                 controls={'FrameRate': 10})
picam2.configure(video_config)
encoder = H264Encoder(1000000)

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", 10001))
    sock.listen()

    picam2.encoders = encoder

    print("Waiting for connection...")
    conn, addr = sock.accept()
    print("Connected by", addr)
    stream = conn.makefile("wb")
    encoder.output = FileOutput(stream)
    picam2.start_encoder(encoder)
    picam2.start()
    print("Started encoder and camera")
    try:
        time.sleep(2000)
    except KeyboardInterrupt:
        pass
    finally:
        print("Stopping")
        picam2.stop()
        picam2.stop_encoder()
        conn.close()
