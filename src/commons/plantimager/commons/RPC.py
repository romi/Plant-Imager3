import sys
import inspect
import json
import traceback
import logging
from enum import StrEnum
from weakref import finalize

from decorator import decorate

import zmq
from typing import Callable, Any

from .deviceregistry import register_device, unregister_device
from .logging import create_logger

logger = create_logger("RPC")

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
        logger.debug(f"Got inv: {reply}",)
        self._json_methods = reply["json_methods"]
        self._buffer_methods = reply["buffer_methods"]
        finalize(self, self.socket.close)

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
            target_cls._interface = interface.__name__
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
            err, trace = res
            logger.error(f"Failed to execute {method} on remote due to {err}")
            if logger.level == logging.DEBUG:
                print("Traceback from remote --->", file=sys.stderr)
                print(trace, file=sys.stderr, end="")
                print("<------------", file=sys.stderr)

    def execute(self, method: Callable, params: dict) -> tuple[bool, object]:
        package = {
            "event": RPCEvents.METHOD_CALL,
            "method": method,
            "params": params,
        }
        if self.socket.poll(timeout=1000, flags=zmq.POLLOUT) == 0:
            logger.warning(f"Proxy of {self._interface} at {self.url} did not respond")
            return False, (Warning(f"Proxy of {self._interface} at {self.url} did not respond"), "")
        logger.debug(f"Executing {package}")
        self.socket.send_json(package, flags=zmq.NOBLOCK)

        if method in self._json_methods:
            if self.socket.poll(timeout=10000, flags=zmq.POLLIN) == 0:
                logger.warning(f"Timeout reached, proxy of {self._interface} at {self.url} did not respond")
                return False, (Warning(f"Proxy of {self._interface} at {self.url} did not respond"), "")
            reply =  self.socket.recv_json()
            if reply["success"]:
                return True, reply["result"]
            else:
                return False, (reply["error"], reply["traceback"])
        elif method in self._buffer_methods:
            if self.socket.poll(timeout=10000, flags=zmq.POLLIN) == 0:
                logger.warning(f"Timeout reached, proxy of {self._interface} at {self.url} did not respond")
                return False, (Warning(f"Proxy of {self._interface} at {self.url} did not respond"), "")
            reply_frames: list[zmq.Frame] = self.socket.recv_multipart(copy=False)
            buffer_info = json.loads(reply_frames[0].bytes)
            if "error" in buffer_info:
                return False, (buffer_info["error"], buffer_info["traceback"])
            else:
                return True, (reply_frames[1].buffer, buffer_info)

    def stop_server(self):
        logger.info(f"Stopping server {self.url}")
        if self.socket.poll(timeout=1000, flags=zmq.POLLOUT) == 0:
            logger.info(f"Server {self.url} could not be joined (might already be dead)")
            return
        self.socket.send_json({
            "event": RPCEvents.STOP_SERVER
        }, flags=zmq.NOBLOCK)
        if self.socket.poll(timeout=1000, flags=zmq.POLLIN) == 0:
            logger.info(f"Server {self.url} did not respond (might already be dead)")
            return
        reply = self.socket.recv_json()
        logger.debug(f"Got stop reply {reply}")


class RPCServer:

    _json_methods: set[str] = set()
    _buffer_methods: set[str] = set()

    def __init__(self, context: zmq.Context, url: str):
        super().__init__()
        self.context: zmq.Context = context
        self.url: str = url
        self.socket: zmq.Socket = context.socket(zmq.REP)
        self.port = self.socket.bind_to_random_port(url, 10000, 12000)

        self._name = ""
        self._registry_addr = ""
        finalize(self, self._finalize)

    def register_to_registry(self, type_: str, name: str, registry_address: str):
        logger.debug(f"Register device {name} of type {type_} to {registry_address}")
        self._name = register_device(
            self.context, type_,
            f"{self.url}:{self.port}",
            name, registry_address
        )
        self._registry_addr = registry_address if self._name else ""
        return self._name

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
            traceback_str = traceback.format_exc(limit=10)
            print(traceback_str, file=sys.stderr)
            print(e, file=sys.stderr)
            self.socket.send_json({"success": False, "error": str(e), "traceback": traceback_str})
        else:
            self.socket.send_json({"success": True, "result": result})

    def _exec_buffer(self, method: Callable, params: dict):
        args = params["args"]
        kwargs = params["kwargs"]
        try:
            buffer, buffer_info = method(*args, **kwargs)
        except Exception as e:
            logger.error(f"Failed to execute {method} due to {e}")
            traceback_str = traceback.format_exc(limit=10)
            print(traceback_str, file=sys.stderr)
            print(e, file=sys.stderr)
            self.socket.send_multipart(
                [json.dumps({"success": False, "error": str(e), "traceback": traceback_str}).encode("utf-8")],
            )
        else:
            self.socket.send_multipart(
                [json.dumps(buffer_info).encode("utf-8"), buffer], copy=False
            )

    def serve_forever(self):
        while True:
            request = self.socket.recv_json()
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
                    logger.info(f"Executing {method} with params {params}")
                    if method in self._json_methods and hasattr(self, method):
                        self._exec_json(getattr(self, method), params)
                    elif method in self._buffer_methods and hasattr(self, method):
                        self._exec_buffer(getattr(self, method), params)
                    else:
                        logger.error(f"Method {method} not implemented")
                        self.socket.send_json({"success": False, "error": f"Method {method} not implemented"})
                case RPCEvents.STOP_SERVER:
                    self.socket.send_json({"success": True})
                    break
        logger.info("Server stopped")

    def _finalize(self):
        if self._name and self._registry_addr:
            unregister_device(self.context, self._name, self._registry_addr)
            logger.info("Device unregistered successfully")
        self.socket.close()
        logger.info("Server deleted")

