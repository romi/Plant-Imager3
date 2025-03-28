from functools import partial

import zmq
from queue import Queue

from plantimager.commons.RPC import RPCClient
from plantimager.commons.cameradevice import Camera, CameraMode
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
    registry.daemon = True
    registry.start()
    device_type, addr, name = queue.get()
    camera = RPCCamera(context, addr)
    camera.modeChanged.connect(partial(print, "mode changed : "))
    camera.videoUrlChanged.connect(partial(print, "video url changed : "))
    camera.mode = CameraMode.VIDEO
    camera.mode = CameraMode.STILL
    jpeg_img = camera.get_image()
    print(jpeg_img)
    camera.mode = CameraMode.VIDEO
    print("Accessing property mode", camera.mode)
    camera.mode = CameraMode.STILL
    print("Accessing property mode", camera.mode)
    camera.stop_server()
    registry.stop()
    registry.join(5)
    del registry

