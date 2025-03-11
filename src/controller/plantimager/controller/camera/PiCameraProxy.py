import zmq

from plantimager.commons.RPC import RPCClient
from plantimager.commons.cameradevice import Camera
from plantimager.commons.deviceregistry import DeviceRegistry


@RPCClient.register_interface(Camera)
class PiCameraProxy(Camera, RPCClient):
    def __init__(self, context: zmq.Context, url: str):
        Camera.__init__(self)
        RPCClient.__init__(self, context, url)



