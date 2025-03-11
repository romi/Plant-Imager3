import sys
import inspect
import json
import logging
from enum import StrEnum
from decorator import decorate

import zmq
from typing import Callable, Any

from .cameradevice import Camera
from .deviceregistry import register_device

logger = logging.Logger("plantimager::RPC")
logger.addHandler(logging.StreamHandler(sys.stderr))
logger.setLevel(logging.DEBUG)

class RPCEvents(StrEnum):
    METHOD_CALL = "METHOD_CALL"
    GET_INVENTORY = "GET_INVENTORY"
    STOP_SERVER = "STOP_SERVER"

class RPCClient:
    """
    Abstract class for RPC clients.
    To use create a class inheriting from the interface and this.
    This new class must be decorated with `@RPCClient.register_interface`

    """
    def __init__(self, context: zmq.Context, url: str):
        super().__init__()
        self.context: zmq.Context = context
        self.url: str = url
        self.socket: zmq.Socket = context.socket(zmq.REQ)
        self.socket.connect(self.url)
        self.socket.send_json({
            "event": RPCEvents.GET_INVENTORY
        })
        reply = self.socket.recv_json()
        print("Got inv: ", reply)
        self._json_methods = reply["json_methods"]
        self._buffer_methods = reply["buffer_methods"]

    @classmethod
    def register_interface(cls, interface: type):
        def _decorator(target_cls: type):
            if interface not in target_cls.__bases__ or cls not in target_cls.__bases__:
                raise RuntimeError(f"{target_cls} must inherit from {interface} and {cls}.")
            for method_name, method in interface.__dict__.items():
                if inspect.isfunction(method) and not (method_name.startswith("__") and method_name.endswith("__")):
                    logger.debug(f"registering method {method_name} in {target_cls}")
                    func = decorate(method, cls._method_proxy)
                    func.__isabstractmethod__ = False  # Counts as en actual implementation
                    setattr(target_cls, method_name, func)
            # abstract methods have been implemented
            target_cls.__abstractmethods__ = frozenset()
            return target_cls
        return _decorator

    @staticmethod
    def _method_proxy(func: Callable, self, *args, **kwargs) -> Any:
        params = {
            "args": args,
            "kwargs": kwargs,
        }
        method = func.__name__
        success, res = self.execute(method, params)
        if success:
            return res
        else:
            logger.error(f"Failed to execute {method} on remote")

    def execute(self, method: Callable, params: dict) -> tuple[bool, object]:
        package = {
            "event": RPCEvents.METHOD_CALL,
            "method": method,
            "params": params,
        }
        logger.debug(f"Executing {package}", )
        self.socket.send_json(package)
        if method in self._json_methods:
            reply =  self.socket.recv_json()
            if reply["success"]:
                return True, reply["result"]
            else:
                return False, reply["error"]
        elif method in self._buffer_methods:
            reply_frames: list[zmq.Frame] = self.socket.recv_multipart(copy=False)
            print(reply_frames[0].bytes)
            buffer_info = json.loads(reply_frames[0].bytes)
            if "error" in buffer_info:
                return False, buffer_info["error"]
            else:
                return True, reply_frames[1].buffer


class RPCServer:

    _json_methods: set[str] = set()
    _buffer_methods: set[str] = set()

    def __init__(self, context: zmq.Context, url: str):
        super().__init__()
        self.context: zmq.Context = context
        self.url: str = url
        self.socket: zmq.Socket = context.socket(zmq.REP)
        self.port = self.socket.bind_to_random_port(url, 10000, 12000)

    def register_to_registry(self, type_: str, name: str, registry_address: str):
        return register_device(
            self.context, type_,
            f"{self.url}:{self.port}",
            name, registry_address
        )

    @classmethod
    def register_method_json(cls, method: Callable):
        cls._json_methods.add(method.__name__)
        return method

    @classmethod
    def register_method_buffer(cls, method: Callable):
        cls._buffer_methods.add(method.__name__)
        return method

    def _exec_json(self, method: Callable, params: dict):
        args = params["args"]
        kwargs = params["kwargs"]
        try:
            result = method(*args, **kwargs)
        except Exception as e:
            logger.error(f"Failed to execute {method} due to {e}")
            print(e, file=sys.stderr)
            print("Sending", {"success": False, "error": str(e)})
            self.socket.send_json({"success": False, "error": str(e)})
        else:
            print("Sending", {"success": True, "result": result})
            self.socket.send_json({"success": True, "result": result})

    def _exec_buffer(self, method: Callable, params: dict):
        args = params["args"]
        kwargs = params["kwargs"]
        try:
            buffer, buffer_info = method(*args, **kwargs)
        except Exception as e:
            logger.error(f"Failed to execute {method} due to {e}")
            print(e, file=sys.stderr)
            print("Sending", {"success": False, "error": str(e)})
            self.socket.send_multipart([json.dumps({"success": False, "error": str(e)})])
        else:
            print("Sending multipart")
            self.socket.send_multipart(
                [json.dumps(buffer_info).encode("utf-8"), buffer], copy=False
            )

    def serve_forever(self):
        while True:
            request = self.socket.recv_json()
            print("Received request", request)
            match request["event"]:
                case RPCEvents.GET_INVENTORY:
                    logger.info("Sending inventory")
                    logger.info({
                        "json_methods": list(self._json_methods),
                        "buffer_methods": list(self._buffer_methods),
                    })
                    self.socket.send_json({
                        "json_methods": list(self._json_methods),
                        "buffer_methods": list(self._buffer_methods),
                    })
                case RPCEvents.METHOD_CALL:
                    method: str = request["method"]
                    params: dict[str, bytes] = request["params"]
                    if method in self._json_methods and hasattr(self, method):
                        self._exec_json(getattr(self, method), params)
                    elif method in self._buffer_methods and hasattr(self, method):
                        self._exec_buffer(getattr(self, method), params)
                    else:
                        logger.error(f"Method {method} not implemented")
                        self.socket.send_json({"success": False, "error": f"Method {method} not implemented"})


@RPCClient.register_interface(Camera)
class RPCCamera(Camera, RPCClient):
    def __init__(self, context: zmq.Context, url: str):
        Camera.__init__(self)
        RPCClient.__init__(self, context, url)

class CameraServer(Camera, RPCServer):
    def __init__(self, context: zmq.Context, url: str):
        RPCServer.__init__(self, context, url)

    @RPCServer.register_method_json
    def start_video(self):
        print("Starting camera stream")



if __name__ == '__main__':
    context = zmq.Context()
    url = "tcp://127.0.0.1:6000"
    camera = RPCCamera(context, url)
    print(camera.__dict__)
    camera.start_video()
    camera.stop_video()
    camera.get_image()

