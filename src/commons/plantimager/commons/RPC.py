import copy
import sys
import inspect
import json
import traceback
import logging
from enum import StrEnum
from functools import wraps, partial
import random
from threading import Thread
from weakref import finalize
import socket
import re

from decorator import decorate

import zmq
from typing import Callable, Any

from .deviceregistry import register_device, unregister_device
from .logging import create_logger

logger = create_logger("RPC")

class RPCEvents(StrEnum):
    PROPERTY_GET = "PROPERTY_GET"
    PROPERTY_SET = "PROPERTY_SET"
    METHOD_CALL = "METHOD_CALL"
    GET_INVENTORY = "GET_INVENTORY"
    STOP_SERVER = "STOP_SERVER"
    FIND_PEER_ADDRESS = "FIND_PEER_ADDRESS"
    INIT_SIGNALS_HANDLING = "INIT_SIGNALS_HANDLING"
    EMIT_SIGNAL = "EMIT_SIGNAL"

url_parser = re.compile("([a-zA-Z]*)://([0-9]{1,3}.[0-9]{1,3}.[0-9]{1,3}.[0-9]{1,3}):([0-9]*)")



class RPCSignal:
    def __init__(self, *arg_types):
        self.args = arg_types
        self.connections = []

    def emit(self, *args):
        for conn in self.connections:
            conn(*args)

    def connect(self, conn: Callable):
        self.connections.append(conn)

    def disconnect(self, conn: Callable=None):
        if conn:
            self.connections.remove(conn)
        else:
            self.connections.clear()



class RPCProperty(property):
    """
    Declares a property for RPC usage. When the notify signal is emitted the proxy on the RPC Client is updated.
    The signal provided in notify must be emitted in the setter when the property changes.
    """
    def __init__(self, fget=None, fset=None, fdel=None, doc=None, notify: RPCSignal = None):
        super().__init__(fget=fget, fset=fset, fdel=fdel, doc=doc)
        self._notifier = notify

    def __call__(self, func: Callable):
        return RPCProperty(fget=func, notify=self._notifier)


class RPCSignalReceiver(Thread):
    """
    A receiver thread for RPCClient to listen for and receive RPC Signals from the server and in turn
    emit the same signals in the proxy.
    """
    def __init__(self, context: zmq.Context, url: str, signals: dict[str, RPCSignal]):
        super().__init__()
        self.context = context
        self.url = url
        self._stop = False
        self.signals = signals
        self.socket: zmq.Socket = context.socket(zmq.REP)
        self.port = self.socket.bind_to_random_port(url)
        finalize(self.socket, self.socket.close)

    def run(self):
        while not self._stop:
            if self.socket.poll(100, zmq.POLLIN) == 0:
                continue
            request = self.socket.recv_json()
            if request["event"] != RPCEvents.EMIT_SIGNAL:
                logger.error(f"Expected event {RPCEvents.EMIT_SIGNAL}, got {request['event']} instead.")
                self.socket.send_json({"success": False})
                continue
            signal = request["signal"]
            args = request["args"]
            logger.debug(f"Emitting signal {signal} with args {args}")
            if request["blocking"]:
                self.signals[signal].emit(*args)
                self.socket.send_json({"success": True})
            else:
                self.socket.send_json({"success": True})
                self.signals[signal].emit(*args)
        logger.debug(f"Stopping signal receiver {self}")


    def stop(self):
        self._stop = True

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

        # replacing class attribute signals by instance signals
        for base in self.__class__.__bases__:
            for key, value in base.__dict__.items():
                if isinstance(value, RPCSignal):
                    setattr(self, key, copy.deepcopy(value))

        # Finding peer address (zmq abstract addresses so we use native sockets here)
        self.socket.send_json({"event": RPCEvents.FIND_PEER_ADDRESS})
        reply = self.socket.recv_json()
        if not reply["success"]:
            raise RuntimeError(f"FIND_PEER_ADDRESS failed")
        protocol, ip_addr, port = url_parser.match(url).groups()
        s = socket.create_connection((ip_addr, reply["port"]))
        self.own_address = s.getsockname()[0]
        self.peer_address = s.getpeername()[0]
        s.close()
        logger.debug(f"Client at address {self.own_address} connected to server at {self.peer_address}")

        # Getting RPCServer inventory
        self.socket.send_json({
            "event": RPCEvents.GET_INVENTORY
        })
        reply = self.socket.recv_json()
        logger.debug(f"Got inv: {reply}",)
        self._json_methods = reply["json_methods"]
        self._buffer_methods = reply["buffer_methods"]
        self._signals = {sig: getattr(self, sig) for sig in reply["signals"] if hasattr(self, sig)}
        self._properties = reply["properties"]
        self.name = reply["name"]

        # If signals initiate
        self._signal_receiver = None
        if self._signals:
            logger.info("Initializing signal handling")
            self._signal_receiver = RPCSignalReceiver(
                context=self.context, url=f"tcp://{self.own_address}", signals=self._signals
            )
            self._signal_receiver.daemon = True
            self._signal_receiver.start()
            signal_port = self._signal_receiver.port
            self.socket.send_json({"event": RPCEvents.INIT_SIGNALS_HANDLING, "address": self.own_address, "port": signal_port})
            reply = self.socket.recv_json()
            if not reply["success"]:
                self._signal_receiver.stop()
                self._signal_receiver.join(2)
                self._signal_receiver = None
                raise RuntimeError(f"INIT_SIGNALS_HANDLING failed")
            logger.info("Successfully initialized signal handling")

        def _finalizer():
            self.socket.close()
            if self._signal_receiver:
                self._signal_receiver.stop()
                self._signal_receiver.join(2)

        finalize(self, _finalizer)

    @classmethod
    def register_interface(cls, interface: type):
        def _decorator(target_cls: type):
            if interface not in target_cls.__bases__ or cls not in target_cls.__bases__:
                raise RuntimeError(f"{target_cls} must inherit from {interface} and {cls}.")
            for key, val in interface.__dict__.items():
                if inspect.isfunction(val) and not (key.startswith("__") and key.endswith("__")):
                    logger.debug(f"registering method {key} in {target_cls}")
                    func = decorate(val, cls._method_proxy)
                    func.__isabstractmethod__ = False  # Counts as en actual implementation
                    setattr(target_cls, key, func)
                elif isinstance(val, RPCSignal):
                    pass # nothing to do at this stage
                elif isinstance(val, RPCProperty):
                    fget = wraps(val.fget)(partial(cls._property_getter_proxy, property_name=key))
                    fset = wraps(val.fset)(partial(cls._property_setter_proxy, property_name=key))
                    prop = RPCProperty(fget=fget, fset=fset, fdel=val.fdel, doc=val.__doc__, notify=val._notifier)
                    setattr(target_cls, key, prop)
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


    def _property_getter_proxy(self, property_name: str) -> Any:
        package = {
            "event": RPCEvents.PROPERTY_GET,
            "property":  property_name
        }
        logger.debug(f"getting property {property_name}")
        self.socket.send_json(package, flags=zmq.NOBLOCK)
        if self.socket.poll(timeout=10000, flags=zmq.POLLIN) == 0:
            logger.warning(f"Timeout reached, proxy of {self._interface} at {self.url} did not respond")
            return None
        reply = self.socket.recv_json()
        if reply["success"]:
            return reply["value"]
        else:
            err, traceback_ = reply["error"], reply["traceback"]
            logger.error(f"Failed to get property {property_name} on remote due to {err}")
            if logger.level == logging.DEBUG:
                print("Traceback from remote --->", file=sys.stderr)
                print(traceback_, file=sys.stderr, end="")
                print("<------------", file=sys.stderr)
            return None

    def _property_setter_proxy(self, value: Any, property_name: str) -> None:
        package = {
            "event": RPCEvents.PROPERTY_SET,
            "property":  property_name,
            "value": value
        }
        logger.debug(f"setting property {property_name} to {value}")
        self.socket.send_json(package, flags=zmq.NOBLOCK)
        if self.socket.poll(timeout=10000, flags=zmq.POLLIN) == 0:
            logger.warning(f"Timeout reached, proxy of {self._interface} at {self.url} did not respond")
            return
        reply = self.socket.recv_json()
        if not reply["success"]:
            err, traceback_ = reply["error"], reply["traceback"]
            logger.error(f"Failed to get property {property_name} on remote due to {err}")
            if logger.level == logging.DEBUG:
                print("Traceback from remote --->", file=sys.stderr)
                print(traceback_, file=sys.stderr, end="")
                print("<------------", file=sys.stderr)
            return


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

    def __init__(self, context: zmq.Context, url: str):
        """
        RPCServer to use in combination with RPCClient.
        The server holds the concrete implementation of an interface that is made available on the network.
        To create an RPCServer create a class inheriting from an interface and RPCServer. Callable
        methods must be decorated using `RPCServer.register_method_buffer` or `RPCServer.register_method_json`.
        The server is also capable of sending signals defined by the RPCSignal class and proxying properties
        defined with RPCProperty.

        Parameters
        ----------
        context: zmq.Context
            ZMQ context used to make the various sockets necessary for communicating with the client.
        url: str
            Url where the RPCServer should listen. It should be of the form "tcp://<ip>" where ip is one
            of the local network interface ip which must be accessible from the client.

        Attributes
        ----------
        context: zmq.Context
            ZMQ context used to make the various sockets necessary for communicating with the client.
        url: str
            Url where the RPCServer is opened.
        port: int
            Port where the RPCServer is opened.
        name: int
            Name of the RPCServer as given by the deviceregistry once registered
        peer_addr: str
            Ip address of the client once connected.

        """
        super().__init__()

        self._json_methods: dict[str, Callable] = dict()
        self._buffer_methods: dict[str, Callable] = dict()
        self._rpc_properties: dict[str, property] = dict()
        self._signals: dict[str, RPCSignal] = dict()

        # replacing class attribute signals from other bases by instance signals
        for base in self.__class__.__bases__:
            for key, value in base.__dict__.items():
                if isinstance(value, RPCSignal):
                    setattr(self, key, copy.deepcopy(value))
                    self._signals[key] = getattr(self, key)

        for key, val in self.__class__.__dict__.items():
            if inspect.isfunction(val) and hasattr(val, "_is_json_method") and val._is_json_method:
                self._json_methods[key] = val
            elif inspect.isfunction(val) and hasattr(val, "_is_buffer_method") and val._is_buffer_method:
                self._buffer_methods[key] = val
            elif isinstance(val, RPCProperty):
                self._rpc_properties[key] = val
            elif isinstance(val, RPCSignal):
                # replacing class attribute signal with instance specific copy
                setattr(self, key, copy.deepcopy(val))
                self._signals[key] = getattr(self, key)

        self.context: zmq.Context = context
        self.url: str = url
        self._socket: zmq.Socket[zmq.REP] = context.socket(zmq.REP)
        self.port = self._socket.bind_to_random_port(url, 10000, 12000)

        self.name = ""
        self.registry_addr = ""
        self._signal_socket: zmq.Socket[zmq.REQ] | None = None
        self.peer_addr: str | None = None

        finalize(self, self._finalize)

    def register_to_registry(self, type_: str, name: str, registry_url: str) -> str:
        """
        Register this RPCServer to the registry at `registry_address` as a device of type `type_` and name `name`.

        Note: The name not be accepted as is and may be modified by the registry to avoid duplicate. This method
        returns the accepted name of this device.

        Parameters
        ----------
        type_: str
            Name of the device type.
        name: str
            Proposed name of the device.
        registry_url: str
            Url of the device registry. Must have the form "tcp://<ip>:<port>" if the registry uses tcp

        Returns
        -------
        accepted_name: str
            Name of this device as accepted by the registry.

        """
        logger.debug(f"Register device {name} of type {type_} to {registry_url}")
        self.name = register_device(
            self.context, type_,
            f"{self.url}:{self.port}",
            name, registry_url
        )
        self.registry_addr = registry_url if self.name else ""
        return self.name


    @staticmethod
    def register_method_json(method: Callable):
        """
        Registers this method as remote callable procedure which will transmit its output via json.
        It is advised to only send basic types and containers as output (int, float, str, bool, list, tuple, dict, ...)
        Arguments are also serialized via json.

        Parameters
        ----------
        method

        Returns
        -------
        method

        """
        method._is_json_method = True
        return method

    @staticmethod
    def register_method_buffer(method: Callable[..., tuple[memoryview|bytes, dict]]):
        """
        Registers this method as remote callable procedure which will transmit its output as a buffer-like object
        as well as a buffer_info dictionary.

        `method` may take any input which will be serialized via json and must output a 2-tuple:
        (memoryview or bytes, dict).


        Parameters
        ----------
        method

        Returns
        -------
        method

        """
        method._is_buffer_method = True
        return method

    def _send_signal(self, signal_name: str, *args):
        if not self._signal_socket:
            logger.error(f"Signal socket not initialized")
            raise RuntimeError(f"Signal socket not initialized")
        logger.debug(f"sending signal {signal_name} with args {args}")
        self._signal_socket.send_json({
            "event": RPCEvents.EMIT_SIGNAL,
            "signal": signal_name,
            "args": args,
            "blocking": False,
        })
        reply = self._signal_socket.recv_json()
        if not reply["success"]:
            logger.error(f"Signal {signal_name} failed with {reply}")

    def _exec_json(self, method: Callable, params: dict):
        args = params["args"]
        kwargs = params["kwargs"]
        try:
            result = method(self, *args, **kwargs)
        except Exception as e:
            logger.error(f"Failed to execute {method} due to {e}")
            traceback_str = traceback.format_exc(limit=10)
            print(traceback_str, file=sys.stderr)
            print(e, file=sys.stderr)
            self._socket.send_json({"success": False, "error": str(e), "traceback": traceback_str})
        else:
            self._socket.send_json({"success": True, "result": result})

    def _exec_buffer(self, method: Callable, params: dict):
        args = params["args"]
        kwargs = params["kwargs"]
        try:
            buffer, buffer_info = method(self, *args, **kwargs)
        except Exception as e:
            logger.error(f"Failed to execute {method} due to {e}")
            traceback_str = traceback.format_exc(limit=10)
            print(traceback_str, file=sys.stderr)
            print(e, file=sys.stderr)
            self._socket.send_multipart(
                [json.dumps({"success": False, "error": str(e), "traceback": traceback_str}).encode("utf-8")],
            )
        else:
            self._socket.send_multipart(
                [json.dumps(buffer_info).encode("utf-8"), buffer], copy=False
            )

    def serve_forever(self):
        """
        Starts serving requests for this RPCServer.

        Returns
        -------

        """
        while True:
            if self._socket.poll(1000, zmq.POLLIN) == 0:
                continue
            request = self._socket.recv_json()
            match request["event"]:
                case RPCEvents.FIND_PEER_ADDRESS:
                    logger.info("Finding peer address")
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    port = random.randint(49152, 65535)
                    s.bind(("", port))  # may crash if unlucky
                    s.listen(1)
                    self._socket.send_json({"success": True, "port": port})
                    c, addr_info = s.accept()
                    self.peer_addr = addr_info[0]
                    c.shutdown(socket.SHUT_RDWR)
                    c.close()
                    s.shutdown(socket.SHUT_RDWR)
                    s.close()
                    del s
                    logger.info("Connected to peer at address: {}".format(self.peer_addr))
                case RPCEvents.GET_INVENTORY:
                    logger.info("Sending inventory")
                    logger.info({
                        "json_methods": list(self._json_methods.keys()),
                        "buffer_methods": list(self._buffer_methods.keys()),
                        "signals": list(self._signals.keys()),
                        "properties": list(self._rpc_properties.keys()),
                        "name": self.name,
                    })
                    self._socket.send_json({
                        "json_methods": list(self._json_methods),
                        "buffer_methods": list(self._buffer_methods),
                        "signals": list(self._signals.keys()),
                        "properties": list(self._rpc_properties.keys()),
                        "name": self.name,
                    })
                case RPCEvents.INIT_SIGNALS_HANDLING:
                    logger.info("Initializing signal handling")
                    address, port = request["address"], request["port"]
                    self._signal_socket = self.context.socket(zmq.REQ)
                    self._signal_socket.connect(f"tcp://{address}:{port}")
                    for sig_name, sig in self._signals.items():
                        sig.connect(partial(self._send_signal, sig_name))
                    self._socket.send_json({"success": True})
                    logger.info("Successfully initialized signal handling")
                case RPCEvents.METHOD_CALL:
                    method: str = request["method"]
                    params: dict[str, bytes] = request["params"]
                    logger.info(f"Executing {method} with params {params}")
                    if method in self._json_methods:
                        self._exec_json(self._json_methods[method], params)
                    elif method in self._buffer_methods:
                        self._exec_buffer(self._buffer_methods[method], params)
                    else:
                        logger.error(f"Method {method} not implemented")
                        self._socket.send_json({"success": False, "error": f"Method {method} not implemented"})
                case RPCEvents.PROPERTY_GET:
                    prop_name: str = request["property"]
                    logger.debug(f"Getting property {prop_name}")
                    try:
                        val = getattr(self, prop_name)
                    except Exception as e:
                        logger.error(f"Failed to execute 'get property' for property {prop_name}")
                        traceback_str = traceback.format_exc(limit=10)
                        print(traceback_str, file=sys.stderr)
                        self._socket.send_json({"success": False, "error": str(e), "traceback": traceback_str})
                    else:
                        self._socket.send_json({
                            "success": True, "value": val,
                        })
                case RPCEvents.PROPERTY_SET:
                    prop_name: str = request["property"]
                    val = request["value"]
                    logger.debug(f"Setting property {prop_name} to {val}")
                    try:
                        setattr(self, prop_name, val)
                    except Exception as e:
                        logger.error(f"Failed to execute 'set property' for property {prop_name}")
                        traceback_str = traceback.format_exc(limit=10)
                        print(traceback_str, file=sys.stderr)
                        self._socket.send_json({"success": False, "error": str(e), "traceback": traceback_str})
                    else:
                        self._socket.send_json({
                            "success": True,
                        })
                case RPCEvents.STOP_SERVER:
                    self._socket.send_json({"success": True})
                    break
        logger.info("Server stopped")

    def _finalize(self):
        if self.name and self.registry_addr:
            unregister_device(self.context, self.name, self.registry_addr)
            logger.info("Device unregistered successfully")
        self._socket.close()
        logger.info("Server deleted")

