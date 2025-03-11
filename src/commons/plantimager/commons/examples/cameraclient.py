import zmq
from imagecodecs import jpegxl_decode, jpegxl_decode_jpeg
import numpy as np
from queue import Queue

from plantimager.commons.RPC import RPCClient
from plantimager.commons.cameradevice import Camera
from plantimager.commons.deviceregistry import DeviceRegistry


@RPCClient.register_interface(Camera)
class RPCCamera(Camera, RPCClient):
    def __init__(self, context: zmq.Context, url: str):
        Camera.__init__(self)
        RPCClient.__init__(self, context, url)

queue = Queue()

def callback(device_type: str, addr: str, name: str):
    print("{} {} {}".format(device_type, addr, name))
    queue.put((device_type, addr, name))


if __name__ == "__main__":
    context = zmq.Context()
    registry = DeviceRegistry(context)
    registry.add_new_device_callback(callback)
    registry.start()
    device_type, addr, name = queue.get()
    camera = RPCCamera(context, addr)
    print("Calling camera.start_video() ==>", camera.start_video())
    print("Calling camera.stop_video() ==>", camera.stop_video())
    jpeg_img = camera.get_image()
    print(jpegxl_decode(jpeg_img))
    print("Calling camera.start_video() ==>", camera.start_video())
    print("Calling camera.stop_video() ==>", camera.stop_video())
    registry.join()

