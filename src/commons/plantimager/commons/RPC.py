import copy
import inspect
import json
import random
import re
import socket
import sys
import traceback
import logging
import weakref
from enum import StrEnum
from functools import wraps, partial
from threading import Thread
from typing import Callable, Any
from weakref import finalize, WeakMethod

import zmq
from decorator import decorate
from zmq import ZMQBindError

from plantimager.commons.utils import is_instance_of_generic, coerce_to_generic
from plantimager.commons.deviceregistry import register_device, unregister_device, send_alive_check
from plantimager.commons.logging import create_logger
from plantimager.commons.systemd import notify_watchdog

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

url_parser = re.compile(r"([a-zA-Z]*)://([a-zA-Z.0-9]*):?([0-9]*)")


class NoResult:
    """
    Represents an outcome with no result, typically used to indicate
    an operation failure along with associated error details.

    This class encapsulates the error message and traceback information
    to provide a structured representation of operation failures, useful
    for logging or debugging purposes.

    This class is Falsey

    Attributes
    ----------
    error : str
        A string containing the error message describing the nature
        of the failure.
    traceback : str
        A string containing the traceback or detailed information
        about where and why the failure occurred.
    """
    def __init__(self, error: str, traceback: str):
        self.error = error
        self.traceback = traceback

    def __bool__(self):
        return False

class RPCSignal:
    """RPCSignal
    ---------
    Lightweight publish‑subscribe signal implementation that stores either strong
    or weak references to callables and invokes them with supplied arguments.

    Instances are created with a variable number of *type specifications* that
    describe the expected arguments for the signal.  These specifications are
    stored unchanged in the :attr:`args` attribute; they are **not** validated at
    runtime but may be used by callers for documentation or static checking.

    Connections are added via :meth:`connect` and removed via :meth:`disconnect`.
    When the signal is emitted with :meth:`emit`, each stored connection is called
    in the order it was added.  Weak references that have been garbage‑collected
    are silently ignored.

    Parameters
    ----------
    *arg_types : tuple
        Positional argument type specifications supplied at construction time.
        The contents are opaque to the implementation – they are kept only for
        external introspection.

    Attributes
    ----------
    arg_types : tuple
        The positional argument type specifications supplied to ``__init__``.
        Callers may inspect this attribute for documentation or validation
        purposes.

    connections : list
        Mutable list of connected callables or weak references.  Each entry is
        either a callable object or a :class:`weakref.WeakMethod`.  The list is
        modified by :meth:`connect` and :meth:`disconnect`.  Callables are
        invoked in the order they were added when :meth:`emit` is called.

    See Also
    --------
    weakref.WeakMethod : Standard library class used to store weak references to bound methods.
    """
    def __init__(self, *arg_types):
        """
        Initialize a new ``RPCSignal`` instance.

        Parameters
        ----------
        *arg_types : tuple
            Positional argument type specifications.  The values are stored in
            :attr:`args` but are otherwise not interpreted by the signal.

        Notes
        -----
        ``arg_types`` can be any hashable objects (e.g., ``int``, ``str``,
        ``numpy.ndarray``) that the user wishes to document as the expected
        argument types for the signal.
        """
        self.arg_types = arg_types
        self.connections = []
        self.args = arg_types
        self.connections: list[Callable | WeakMethod] = []

    def emit(self, *args):
        """Emit the signal, invoking all connected callables.

        Parameters
        ----------
        *args : tuple
            Positional arguments that will be forwarded to each connected
            callable.  The number and type of arguments should match the
            specifications stored in :attr:`args`, but this is not enforced.

        Notes
        -----
        - Weak references stored as :class:`weakref.WeakMethod` are dereferenced
          before the call; if the underlying object has been garbage‑collected,
          the entry is simply skipped.
        - Any exception raised by a connected callable propagates to the caller
          of :meth:`emit`.  The method does **not** catch or suppress errors.
        """
        args = self.validate_args(*args, coerce=True)
        for conn in self.connections:
            if isinstance(conn, WeakMethod) and (func:=conn()):
                # If the onnection is a WeakMethod and the method still lives
                func(*args)
            elif not isinstance(conn, weakref.WeakMethod):
                # If this is not a weak method (ergo an actual method)
                conn(*args)

    def validate_args(self, *args, coerce=False) -> tuple:
        """
        Validates and coerces input arguments based on expected types.

        This method validates the provided `args` against the expected types specified
        in `self.arg_types`. If `coerce` is set to `True`, it attempts to coerce the
        arguments to the expected types when a mismatch occurs. If validation or coercion
        fails, the method raises appropriate exceptions.

        Parameters
        ----------
        *args
            Positional arguments to be validated against `self.arg_types`. The number
            of arguments must match the number of expected types.
        coerce : bool, optional
            If `True`, attempts to coerce arguments to the expected type in case of a
            mismatch. Defaults to `False`.

        Returns
        -------
        tuple
            A tuple of validated (or coerced) arguments in the same order as the input.

        Raises
        ------
        RuntimeError
            Raised if the number of provided arguments does not match the number of
            expected types in `self.arg_types`.
        TypeError
            Raised if an argument type mismatch occurs and `coerce` is `False`, or if
            coercion fails when `coerce` is `True`.

        See Also
        --------
        coerce_to_generic : Function used to coerce arguments to generic types.
        is_instance_of_generic : Function to check whether an argument matches an expected type.
        """
        if len(args) != len(self.arg_types):
            logger.error(f"Expected {len(self.arg_types)} arguments, got {len(args)}.")
            raise RuntimeError(f"Expected {len(self.arg_types)} arguments, got {len(args)}.")
        new_args = []
        # Validates and coerces each argument; errors on type mismatch
        for i, (arg, arg_type) in enumerate(zip(args, self.arg_types)):
            if coerce:
                new_args.append(coerce_to_generic(arg, arg_type))
            elif is_instance_of_generic(arg, arg_type):
                new_args.append(arg)
            else:
                logger.error(f"Argument {i} of type {type(arg)} is not an instance of {arg_type}.")
                raise TypeError(f"Argument {i} of type {type(arg)} is not an instance of {arg_type}.")
        return tuple(new_args)

    def connect(self, conn: Callable | WeakMethod):
        """Connect a callable (or weak reference) to the signal.

        Parameters
        ----------
        conn : Callable or weakref.WeakMethod
            The function, bound method, or weak reference that should be called
            when the signal is emitted.

        Raises
        ------
        TypeError
            If ``conn`` is neither a callable nor a :class:`weakref.WeakMethod`.

        Notes
        -----
        The same ``conn`` is added only once; duplicate connections are ignored.
        """
        if not isinstance(conn, (weakref.WeakMethod, Callable)):
            raise TypeError("Expected callable or weakref.WeakMethod, got {}".format(type(conn)))
        if conn not in self.connections:
            self.connections.append(conn)

    def disconnect(self, conn: Callable=None):
        """Remove a previously connected callable or clear all connections.

        Parameters
        ----------
        conn : Callable, optional
            The specific callable or weak reference to remove.  If omitted (or
            ``None``), *all* connections are cleared.

        Raises
        ------
        ValueError
            If ``conn`` is provided but is not present in :attr:`connections`.

        Notes
        -----
        After a successful call, the target is no longer invoked by future
        :meth:`emit` calls.
        """
        if conn:
            self.connections.remove(conn)
        else:
            self.connections.clear()


class RPCProperty(property):
    """
    RPC-enabled property descriptor.

    This subclass of :class:`property` adds optional notification support
    via an :class:`RPCSignal`.  When a property created with ``RPCProperty``
    is assigned a new value, the supplied ``notify`` signal (if provided)
    can be emitted to inform remote listeners of the change.  The class is
    typically used as a decorator on a getter function; the optional
    ``notify`` argument is stored on the resulting property object and can
    be accessed by custom setter implementations.
    The setter must explicitly emit the ''notify'' signal if a change occurred.

    Attributes
    ----------
    _notifier : RPCSignal or None
        Signal that will be emitted when the property's value changes.
        It is initialized from the ``notify`` argument of ``__init__`` and
        may be ``None`` when no notification is required.
    _auto_notify: bool
        When True, when the setter of the property is called and the value is
          modified, the _notifier is emitted.
    """
    def __init__(self, fget=None, fset=None, fdel=None, doc=None, notify: RPCSignal = None, auto_notify=False):
        """
        Initialize the property with optional RPC notification.

        This subclass of ``property`` adds support for emitting an RPC signal
        when the property value changes.  If ``auto_notify`` is ``True`` the
        signal provided via ``notify`` is emitted automatically after a successful
        set operation; otherwise the caller must trigger the notification
        manually.

        Parameters
        ----------
        fget : callable, optional
            Getter function that receives the instance and returns the attribute
            value.
        fset : callable, optional
            Setter function that receives the instance and the value to assign.
        fdel : callable, optional
            Deleter function that receives the instance and removes the attribute.
        doc : str, optional
            Documentation string for the property.
        notify : RPCSignal, optional
            RPC signal emitted when the property value is changed.
        auto_notify : bool, default: ``False``
            When ``True``, automatically emit ``notify`` after a successful set.

        See Also
        --------
        property
            Built‑in ``property`` class that this class extends.
        """
        super().__init__(fget=fget, fset=fset, fdel=fdel, doc=doc)
        self._notifier: RPCSignal | None = notify
        self._auto_notify: bool = auto_notify

    def __call__(self, func: Callable):
        return RPCProperty(fget=func, notify=self._notifier)

    def __set__(self, obj, value):
        """
        Set the property on *obj* and emit the ``_notifier`` signal if the
        observable value actually changes.

        The logic is:
        1. Retrieve the old value via the getter (if any).
        2. Call the original setter.
        3. Retrieve the new value via the getter.
        4. If ``old != new`` and a notifier exists, emit the signal with the
           new value.
        """
        # Step 1 – capture the old value (may be None if no getter)
        old_val = None
        if self._auto_notify and self.fget is not None:
            try:
                old_val = self.fget(obj)
            except Exception:
                # If the getter fails we simply ignore the old value;
                # the change‑detection will fall back to always emit.
                old_val = object()  # unique sentinel

        # Step 2 – invoke the original setter (if any)
        super().__set__(obj, value)

        # Step 3 – capture the new value via the getter (if any)
        new_val = None
        if self._auto_notify and self.fget is not None:
            try:
                new_val = self.fget(obj)
            except Exception:
                new_val = object()  # unique sentinel

        # Step 4 – emit if changed and a notifier is present
        if self._auto_notify and self._notifier is not None and old_val != new_val:
            try:
                self._notifier.emit(new_val)
            except Exception as exc:
                # We never want a notification failure to break the setter.
                logger.error(f"Failed to emit RPCProperty change signal: {exc}")



class RPCSignalReceiver(Thread):
    """
    A receiver thread for RPCClient to listen for and receive RPC Signals from the server and in turn
    emit the same signals in the proxy.
    """
    def __init__(self, context: zmq.Context, url: str, signals: dict[str, RPCSignal]):
        super().__init__(name="RPCSignalReceiver")
        self.context = context
        self.url = url
        self._stop_flag = False
        self.signals = signals
        self.socket: zmq.Socket = context.socket(zmq.REP)
        self.port = self.socket.bind_to_random_port(url)

    def run(self):
        try:
            while not self._stop_flag:
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
        finally:
            self.socket.close()
            del self.socket
        logger.debug(f"Stopping signal receiver {self}")

    def stop(self):
        self._stop_flag = True

class RPCClient:
    """
    Abstract class for RPC clients.
    To use, create a class inheriting from the interface and this.
    This new class must be decorated with `@RPCClient.register_interface`

    """

    def __init__(self, context: zmq.Context, url: str):
        super().__init__()
        self.context: zmq.Context = context
        self.url: str = url
        self.socket: zmq.Socket = context.socket(zmq.REQ)
        self.socket.connect(self.url)

        # replacing class attribute signals with instance signals
        for base in self.__class__.__bases__:
            for key, value in base.__dict__.items():
                if isinstance(value, RPCSignal):
                    setattr(self, key, copy.deepcopy(value))

        # Finding peer address (zmq abstract addresses so we use native sockets here)
        self.socket.send_json({"event": RPCEvents.FIND_PEER_ADDRESS})
        reply = self.socket.recv_json()
        if not reply["success"]:
            raise RuntimeError("FIND_PEER_ADDRESS failed")
        _, ip_addr, _ = url_parser.match(url).groups()
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
        self._json_methods: dict[str, int|None] = reply["json_methods"]
        self._buffer_methods: dict[str, int|None] = reply["buffer_methods"]
        self._signals = {sig: getattr(self, sig) for sig in reply["signals"] if hasattr(self, sig)}
        self._properties: list = reply["properties"]
        self.name: str = reply["name"]

        # If signals initiate
        self._signal_receiver = None
        if self._signals:
            logger.info("Initializing signal handling")
            self._signal_receiver = RPCSignalReceiver(
                context=self.context, url=f"tcp://{self.own_address}", signals=self._signals
            )
            self._signal_receiver.daemon = True  # FIXME: Should be False!
            self._signal_receiver.start()
            signal_port = self._signal_receiver.port
            self.socket.send_json({"event": RPCEvents.INIT_SIGNALS_HANDLING, "address": self.own_address, "port": signal_port})
            reply = self.socket.recv_json()
            if not reply["success"]:
                self._signal_receiver.stop()
                self._signal_receiver.join(2)
                self._signal_receiver = None
                raise RuntimeError("INIT_SIGNALS_HANDLING failed")
            logger.info("Successfully initialized signal handling")

        def _finalizer(sock, receiver):
            sock.close()
            if receiver:
                receiver.stop()
                receiver.join(2)
            logger.debug("Client finalized")

        finalize(self, _finalizer, self.socket, self._signal_receiver)

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
                RPCClient._print_traceback_from_remote(trace)
            return NoResult(err, trace)

    @staticmethod
    def _print_traceback_from_remote(trace: str):
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
            return NoResult("Timeout reached", "")
        reply = self.socket.recv_json()
        if reply["success"]:
            return reply["value"]
        else:
            err, traceback_ = reply["error"], reply["traceback"]
            logger.error(f"Failed to get property {property_name} on remote due to {err}")
            if logger.level == logging.DEBUG:
                RPCClient._print_traceback_from_remote(traceback_)
            return NoResult(err, traceback_)

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
                RPCClient._print_traceback_from_remote(traceback_)

    def execute(self, method_name: str, params: dict) -> tuple[bool, object]:
        package = {
            "event": RPCEvents.METHOD_CALL,
            "method": method_name,
            "params": params,
        }
        if self.socket.poll(timeout=1000, flags=zmq.POLLOUT) == 0:
            logger.error(f"Proxy of {self._interface} at {self.url} did not respond")
            raise TimeoutError(f"Proxy of {self._interface} at {self.url} did not respond")
        logger.debug(f"Executing {package}")
        self.socket.send_json(package, flags=zmq.NOBLOCK)

        if method_name in self._json_methods:
            if self.socket.poll(timeout=self._json_methods[method_name], flags=zmq.POLLIN) == 0:
                logger.error(f"Proxy of {self._interface} at {self.url} did not respond")
                raise TimeoutError(f"Proxy of {self._interface} at {self.url} did not respond")
            reply =  self.socket.recv_json()
            if reply["success"]:
                return True, reply["result"]
            else:
                return False, (reply["error"], reply["traceback"])
        elif method_name in self._buffer_methods:
            if self.socket.poll(timeout=self._buffer_methods[method_name], flags=zmq.POLLIN) == 0:
                logger.error(f"Proxy of {self._interface} at {self.url} did not respond")
                raise TimeoutError(f"Proxy of {self._interface} at {self.url} did not respond")
            reply_frames: list[zmq.Frame] = self.socket.recv_multipart(copy=False)
            buffer_info = json.loads(reply_frames[0].bytes)
            if "error" in buffer_info:
                return False, (buffer_info["error"], buffer_info["traceback"])
            else:
                return True, (reply_frames[1].buffer, buffer_info)
        return False, (Warning(f"Unknown method {method_name}"), "")

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

    def __init__(self, context: zmq.Context, url: str, alive_timeout: int = 60):
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
        alive_timeout: int, optional
            Time in seconds after which the device_registry will consider this service dead or unreachable.

        Attributes
        ----------
        context: zmq.Context
            ZMQ context used to make the various sockets necessary for communicating with the client.
        url: str
            Url where the RPCServer is opened.
        port: int
            Port where the RPCServer is opened.
        name: str
            Name of the RPCServer as given by the deviceregistry once registered
        uuid: str
            Unique identifier of this RPCServer given by the registry once registered..
        peer_addr: str
            Ip address of the client once connected.

        """
        super().__init__()

        self.context: zmq.Context = context
        self.url: str = url
        self.alive_timeout = alive_timeout
        self.uuid: str | None = None
        self.name = ""
        self.registry_addr = ""
        self.peer_addr: str | None = None

        # Containers for RPC members
        self._json_methods: dict[str, Callable] = {}
        self._buffer_methods: dict[str, Callable] = {}
        self._rpc_properties: dict[str, property] = {}
        self._signals: dict[str, RPCSignal] = {}

        # Initialize internals
        self._initialize_rpc_members()
        self._socket, self.port = self._bind_socket(url)
        self._signal_socket: zmq.Socket[zmq.REQ] | None = None
        self._stop = False

        self._setup_lifecycle_cleanup()
        self._dead = False

    def _initialize_rpc_members(self):
        """Scans class and bases for Signals, Properties, and RPC methods."""
        # 1. Inherit signals from base classes (instance-specific copy)
        for base in self.__class__.__bases__:
            for key, value in base.__dict__.items():
                if isinstance(value, RPCSignal):
                    setattr(self, key, copy.deepcopy(value))
                    self._signals[key] = getattr(self, key)

        # 2. Register members defined in this class
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

    def _bind_socket(self, url: str) -> tuple[zmq.Socket, int]:
        """Creates and binds the ZMQ REP socket."""
        socket: zmq.Socket[zmq.REP] = self.context.socket(zmq.REP)
        _, ip_addr, port_str = url_parser.match(url).groups()

        if port_str:
            port = int(port_str)
            try:
                socket.bind(url)
            except ZMQBindError:
                logger.error(f"Failed to bind to {url}")
                raise
        else:
            port = socket.bind_to_random_port(url, 10000, 12000)

        logger.debug(f"RPCServer of type {type(self)} bound to {ip_addr} on port {port}")
        return socket, port

    def _setup_lifecycle_cleanup(self):
        """Configures weakref finalizer to handle cleanup without capturing 'self'."""
        self._cleanup_state = {
            "uuid": None,
            "registry_addr": "",
            "context": self.context,
            "socket": self._socket,
            "signal_socket": None
        }

        def _server_finalizer(state, signals):
            # This function does not capture 'self'
            for signal in signals.values():
                signal.disconnect()
            if state["uuid"] and state["registry_addr"]:
                unregister_device(state["context"], state["uuid"], state["registry_addr"])
                logger.info("Device unregistered successfully")
            state["socket"].close()
            if state["signal_socket"]:
                state["signal_socket"].close()
            logger.info("Server deleted")

        finalize(self, _server_finalizer, self._cleanup_state, self._signals)

    def register_to_registry(self, type_: str, name: str, registry_url: str, overwrite=True) -> str:
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
        overwrite: bool, optional
            Wether or not this device should take preference for the use of this name and overwrite other
            conflicting devices.

        Returns
        -------
        accepted_name: str
            Name of this device as accepted by the registry.

        """
        logger.debug(f"Register device {name} of type {type_} to {registry_url}")
        self.name, self.uuid = register_device(
            self.context, type_,
            f"{self.url}:{self.port}",
            name, registry_url,
            overwrite=overwrite,
        )
        if not self.name:
            logger.warning(f"Failed to register device {name} of type {type_} as {registry_url}")
        self.registry_addr = registry_url if self.name else ""

        # Update cleanup state so finalizer knows what to unregister
        self._cleanup_state["uuid"] = self.uuid
        self._cleanup_state["registry_addr"] = self.registry_addr

        return self.name


    @staticmethod
    def register_method_json(timeout: int | None = 10000):
        """
        Registers this method as remote callable procedure which will transmit its output via json.
        It is advised to only send basic types and containers as output (int, float, str, bool, list, tuple, dict, ...)
        Arguments are also serialized via json.

        Parameters
        ----------
        timeout: int | None
            Specifies how much time in ms a client is expected to wait for the method to finish. If None, waits indefinitely.

        Returns
        -------
        decorator: Callable[Callable[..., Any], Callable[..., Any]]

        """
        if inspect.isfunction(timeout):
            timeout._is_json_method = True
            timeout._timeout = 10000
            return timeout
        def _decorator(method: Callable[..., Any]):
            method._is_json_method = True
            method._timeout = timeout
            return method
        return _decorator

    @staticmethod
    def register_method_buffer(timeout: int | None = 10000):
        """
        Registers this method as remote callable procedure which will transmit its output as a buffer-like object
        as well as a buffer_info dictionary.

        `method` may take any input which will be serialized via json and must output a 2-tuple:
        (memoryview or bytes, dict).


        Parameters
        ----------
        timeout: int | None
            Specifies how much time in ms a client is expected to wait for the method to finish. If None, waits indefinitely.

        Returns
        -------
        decorator: Callable[Callable[..., tuple[memoryview|bytes, dict]], Callable[..., tuple[memoryview|bytes, dict]]]

        """
        if inspect.isfunction(timeout):
            timeout._is_buffer_method = True
            timeout._timeout = 10000
            return timeout
        def _decorator(method: Callable[..., tuple[memoryview|bytes, dict]]):
            method._is_buffer_method = True
            method._timeout = timeout
            return method
        return _decorator

    def _send_signal(self, signal_name: str, *args):
        if not self._signal_socket:
            logger.error("Signal socket not initialized")
            raise RuntimeError("Signal socket not initialized")
        # Validate that we send a signal with arguments matching the expected types
        signal: RPCSignal = getattr(self, signal_name)
        signal.validate_args(*args)
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

    def _exec_json(self, method: Callable, params: dict) -> dict:
        args = params["args"]
        kwargs = params["kwargs"]
        try:
            result = method(*args, **kwargs)
        except Exception as e:
            logger.error(f"Failed to execute {method} due to {e}")
            traceback_str = traceback.format_exc(limit=10)
            print(traceback_str, file=sys.stderr)
            print(e, file=sys.stderr)
            return {"success": False, "error": str(e), "traceback": traceback_str}
        else:
            return {"success": True, "result": result}

    def _exec_buffer(self, method: Callable, params: dict) -> list[bytes]:
        args = params["args"]
        kwargs = params["kwargs"]
        try:
            buffer, buffer_info = method(*args, **kwargs)
        except Exception as e:
            logger.error(f"Failed to execute {method} due to {e}")
            traceback_str = traceback.format_exc(limit=10)
            print(traceback_str, file=sys.stderr)
            print(e, file=sys.stderr)
            return [json.dumps({"success": False, "error": str(e), "traceback": traceback_str}).encode("utf-8")]
        else:
            return [json.dumps(buffer_info).encode("utf-8"), buffer]

    def stop_server(self):
        """
        Stop the server and unregister the device if it has been registered.

        The method sets the internal stop flag, optionally calls
        :func:`unregister_device` to remove the device from a remote registry,
        clears the identifying attributes (``name``, ``uuid``, ``registry_addr``),
        and resets the corresponding entries in ``_cleanup_state`` to ``None``.
        This prevents a second unregister attempt during cleanup.

        Raises
        ------
        Exception
            Propagates any exception raised by :func:`unregister_device`, e.g.
            network errors or authentication failures.

        Notes
        -----
        * The device is only unregistered when all three attributes
          ``self.name``, ``self.registry_addr`` and ``self.uuid`` evaluate to
          ``True``.  If any of them is falsy, the function simply sets the
          stop flag and returns.
        * ``self._cleanup_state`` is updated after a successful unregister to
          avoid duplicate cleanup actions later in the object's lifecycle.

        See Also
        --------
        unregister_device : Function that removes a device from the registry.
        """
        self._stop = True
        if self.name and self.registry_addr and self.uuid:
            unregister_device(self.context, self.uuid, self.registry_addr)
            self.name = ""
            self.uuid = ""
            self.registry_addr = ""

            # Clear cleanup state to avoid double unregister
            self._cleanup_state["uuid"] = None
            self._cleanup_state["registry_addr"] = None

            logger.info("Device unregistered successfully")

    def serve_forever(self):
        """
        Serve the RPC server indefinitely, handling incoming requests until a stop signal is
        received.

        The method enters a loop that repeatedly notifies the watchdog, checks the server's
        liveness, waits for a request, and dispatches the request based on its ``event`` field.
        Supported events include peer discovery, inventory retrieval, signal handling
        initialization, method invocation, property access, and server shutdown.  Upon receiving
        a ``STOP_SERVER`` event the loop terminates, sockets are closed, and a log entry is
        written.

        If registered to the registry and the check_alive fails, exits the loop

        Returns
        -------
        None
            The server runs until it is stopped; no value is returned.

        Notes
        -----
        * The private attribute ``_stop`` controls the loop termination.  It is set to
          ``True`` only when a ``STOP_SERVER`` request is processed.
        * ``_socket`` and ``_signal_socket`` are closed during cleanup; if either attribute is
          ``None`` the corresponding ``close`` call is skipped.
        * ``notify_watchdog`` and ``_alive_check`` are called on every iteration to maintain
          server health monitoring.
        * The method assumes that ``_wait_for_request`` returns a mapping with an ``event``
          key; a falsy return value causes the loop to continue without processing.

        See Also
        --------
        RPCEvents : Enum defining the possible request events.
        _handle_find_peer_address, _handle_get_inventory, _handle_init_signal_handling,
        _handle_method_call, _handle_property_get, _handle_property_set :
            Private helper methods that implement the handling logic for each event type.
        """
        if self._dead:
            logger.error("RPCServer is in dead state. A new instance must be created.")
            raise RuntimeError("RPCServer is in dead state. A new instance must be created.")
        self._stop = False
        while not self._stop:
            if not self._alive_check():
                logger.error(f"Check Alive failed. Registry at {self.registry_addr} "
                             f"is unreachable or does not know this service.")
                break

            notify_watchdog()

            request = self._wait_for_request()
            if not request:
                continue
            try:
                match request["event"]:
                    case RPCEvents.FIND_PEER_ADDRESS:
                        self._handle_find_peer_address()
                    case RPCEvents.GET_INVENTORY:
                        reply = self._handle_get_inventory()
                        self._send_reply(reply)
                    case RPCEvents.INIT_SIGNALS_HANDLING:
                        reply = self._handle_init_signal_handling(request)
                        self._send_reply(reply)
                    case RPCEvents.METHOD_CALL:
                        reply, use_multipart = self._handle_method_call(request)
                        self._send_reply(reply, use_multipart)
                    case RPCEvents.PROPERTY_GET:
                        reply = self._handle_property_get(request)
                        self._send_reply(reply)
                    case RPCEvents.PROPERTY_SET:
                        reply = self._handle_property_set(request)
                        self._send_reply(reply)
                    case RPCEvents.STOP_SERVER:
                        self._socket.send_json({"success": True})
                        self._stop = True
            except Exception as exc:
                logger.error(f"Unexpected error while handling request: {exc}")
                # If we have a request, we can at least try to answer with a generic error.
                if isinstance(request, dict) and "event" in request:
                    self._send_reply(self._make_error_reply(exc, "serve_forever"))
                break   # abort the loop – we are in an inconsistent state

        # cleanup
        if self._socket:
            self._socket.close()
        if self._signal_socket:
            self._signal_socket.close()
        self._dead = True
        logger.info("Server stopped")

    def _handle_property_set(self, request: dict) -> dict:
        """
        Set an attribute on the instance based on a request dictionary.

        Parameters
        ----------
        request
            Mapping containing the keys ``"property"`` and ``"value"``.  The
            ``"property"`` entry specifies the name of the attribute to set on
            ``self`` and ``"value"`` is the value to assign.

        Returns
        -------
        dict
            ``{"success": True}`` if the attribute was set successfully, or an
            error reply dictionary generated by :meth:`_make_error_reply` when an
            exception occurs.
        """
        prop_name: str = request["property"]
        val = request["value"]
        logger.debug(f"Setting property {prop_name} to {val}")
        try:
            setattr(self, prop_name, val)
        except Exception as e:
            return self._make_error_reply(e, "set_property")
        else:
            return {"success": True}

    def _handle_property_get(self, request: dict) -> dict:
        """
        Retrieve the value of a named attribute from the instance.

        The function expects ``request`` to contain a ``"property"`` key whose
        value is the name of the attribute to read.  It logs the operation, attempts
        to obtain the attribute via :func:`getattr`, and returns a JSON‑serialisable
        response.  Any exception raised while accessing the attribute is caught and
        transformed into an error reply using :meth:`_make_error_reply`.

        Parameters
        ----------
        request
            Mapping that must include the key ``"property"`` identifying the
            attribute whose value should be returned.

        Returns
        -------
        dict
            A dictionary with the shape ``{"success": True, "value": <attr>}`` when
            the attribute is successfully retrieved, where ``<attr>`` is the value
            of the requested property.  If an exception occurs, the dictionary is
            the result of ``_make_error_reply`` and contains error information.

        Notes
        -----
        * The method never propagates exceptions; all errors are captured and
          reported via the error‑reply structure.
        * The returned dictionary is intended to be JSON‑serialisable.

        See Also
        --------
        _make_error_reply : Helper that formats a standardized error reply for
            failed property accesses.

        Examples
        --------
        >>> class Demo:
        ...     def __init__(self):
        ...         self.answer = 42
        ...     def _make_error_reply(self, exc, op):
        ...         return {"success": False, "error": str(exc), "operation": op}
        ...     _handle_property_get = _handle_property_get
        >>> d = Demo()
        >>> d._handle_property_get({"property": "answer"})
        {'success': True, 'value': 42}
        >>> d._handle_property_get({"property": "missing"})
        {'success': False, 'error': "...'"}  # error reply generated by _make_error_reply
        """
        prop_name: str = request["property"]
        logger.debug(f"Getting property {prop_name}")
        try:
            val = getattr(self, prop_name)
        except Exception as e:
            return self._make_error_reply(e, "get_property")
        else:
            return {"success": True, "value": val}

    def _handle_method_call(self, request: dict) -> tuple[dict|list[bytes], bool]:
        """
        Dispatch a JSON‑RPC request to the appropriate handler.

        The function extracts the ``method`` name and ``params`` from *request*,
        looks up the method in the internal registries and executes it using the
        appropriate execution helper.  The return value indicates both the reply
        payload and whether the payload should be sent as a multipart (buffer)
        response.

        Parameters
        ----------
        request : dict
            Mapping that must contain the keys ``"method"`` (a ``str``) and
            ``"params"`` (a ``dict`` mapping ``str`` to ``bytes``).  The method name
            determines which registered handler is invoked.

        Returns
        -------
        tuple
            ``(reply, use_buffer)`` where:

            * ``reply`` : ``dict`` or ``list[bytes]``
                If the method is registered as a JSON handler, ``reply`` is a JSON‑
                serialisable ``dict`` produced by :meth:`_exec_json`.  If the method
                is a buffer handler, ``reply`` is a ``list`` of ``bytes`` objects
                returned by :meth:`_exec_buffer`.

            * ``use_buffer`` : ``bool``
                ``True`` if the reply should be transmitted as a multipart/buffer
                response, ``False`` for a regular JSON response.

        See Also
        --------
        _exec_json : Execute a method that returns a JSON‑serialisable payload.
        _exec_buffer : Execute a method that returns raw byte buffers.
        """
        method: str = request["method"]
        params: dict[str, bytes] = request["params"]
        logger.debug(f"Executing {method} with params {params}")
        if method in self._json_methods:
            reply = self._exec_json(getattr(self, method), params)
            return reply, False  # use json
        elif method in self._buffer_methods:
            reply = self._exec_buffer(getattr(self, method), params)
            return reply, True  # use multipart
        else:
            err = f"Method {method} not implemented"
            logger.error(err)
            return {"success": False, "error": err}, False

    def _handle_init_signal_handling(self, request: dict) -> dict:
        """
        Initialize ZeroMQ signal handling based on the supplied request.

        The method creates a ``REQ`` socket, connects it to the address and port
        specified in ``request``, stores the socket in ``self._cleanup_state`` for
        later cleanup, and registers a weak callback for each signal in
        ``self._signals``.  The weak callback forwards the signal name and any
        positional or keyword arguments to ``_send_signal`` without creating a
        reference cycle.

        Parameters
        ----------
        request
            Mapping containing the keys ``'address'`` (str) and ``'port'`` (int)
            that specify the endpoint to which the signal socket should connect.

        Returns
        -------
        dict
            ``{'success': True}`` indicating that the socket was successfully
            created and all signal handlers were attached.

        Raises
        ------
        KeyError
            If ``request`` does not contain the required ``'address'`` or ``'port'``
            entries.
        """
        logger.info("Initializing signal handling")
        address, port = request["address"], request["port"]
        self._signal_socket = self.context.socket(zmq.REQ)
        self._signal_socket.connect(f"tcp://{address}:{port}")
        self._cleanup_state["signal_socket"] = self._signal_socket
        weak_send_signal = WeakMethod(self._send_signal)
        for sig_name, sig in self._signals.items():
            sig.connect(lambda *args, sig_name=sig_name, **kwargs: weak_send_signal()(sig_name, *args, **kwargs))
        logger.info("Successfully initialized signal handling")
        return {"success": True}

    def _handle_get_inventory(self) -> dict:
        """
        Retrieve a dictionary describing the current RPC inventory.

        Returns
        -------
        dict
            Mapping with the following keys:

            - ``json_methods``: ``dict`` mapping method names to their timeout values.
            - ``buffer_methods``: ``dict`` mapping method names to their timeout values.
            - ``signals``: ``list`` of registered signal names.
            - ``properties``: ``list`` of RPCProperty names.
            - ``name``: ``str`` representing the RPC object's identifier.
        """
        logger.info("Sending inventory")
        response = {
            "json_methods": {name: func._timeout for name, func in self._json_methods.items()},
            "buffer_methods": {name: func._timeout for name, func in self._buffer_methods.items()},
            "signals": list(self._signals.keys()),
            "properties": list(self._rpc_properties.keys()),
            "name": self.name,
        }
        logger.debug(response)
        return response

    def _handle_find_peer_address(self):
        """
        Find a free port, inform the peer, accept a connection, and record the peer's
        address.
        """
        logger.info("Finding peer address")
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        port = random.randint(49152, 65535)

        s.bind(("", port))  # may crash if unlucky
        s.settimeout(20.0)  # s
        s.listen(1)
        self._send_reply({"success": True, "port": port})
        try:
            c, addr_info = s.accept()
        except socket.timeout:
            s.close()
            logger.error("No peer connected to discovery socket after 20s – giving up.")
            raise RuntimeError("Failed to find peer address")
        self.peer_addr = addr_info[0]
        c.shutdown(socket.SHUT_RDWR)
        c.close()
        s.shutdown(socket.SHUT_RDWR)
        s.close()
        del s
        logger.info("Connected to peer at address: {}".format(self.peer_addr))

    def _wait_for_request(self) -> dict | None:
        if self._socket.poll(500, zmq.POLLIN) == 0:
            return None
        return self._socket.recv_json()

    def _alive_check(self) -> bool:
        if self.registry_addr:
            return send_alive_check(self.context, self.uuid, self.registry_addr, self.alive_timeout)
        return True
    # --------------------------------------------------------------------- #
    #  Utility – error reporting
    # --------------------------------------------------------------------- #
    @staticmethod
    def _make_error_reply(exc: Exception, context: str) -> dict:
        """
        Generate a structured error reply dictionary for logging and debugging.

        When an exception occurs during execution of a particular operation, this
        helper creates a response containing a failure flag, a string representation
        of the exception, and a truncated traceback.  The traceback is limited to the
        most recent ten frames to keep the output concise.

        Parameters
        ----------
        `exc`
            The caught :class:`Exception` instance.
        `context`
            Description of the operation being performed when ``exc`` was raised.

        Returns
        -------
        dict
            Mapping with keys ``success`` (always ``False``), ``error`` containing the
            exception message, and ``traceback`` containing the formatted traceback.

        Notes
        -----
        The function logs the error via the module‑level ``logger`` and prints the
        traceback to ``stderr`` to aid post‑mortem analysis.
        """
        logger.error(f"Failed to execute '{context}' – {exc}")
        tb = traceback.format_exc(limit=10)
        print(tb, file=sys.stderr)
        return {"success": False, "error": str(exc), "traceback": tb}

    def _send_reply(self, msg: dict | list[bytes], multipart=False) -> None:
        """
        Send a reply message through the internal ZeroMQ socket.

        Parameters
        ----------
        msg
            Message to be transmitted. If ``multipart`` is ``True`` the value
            must be a ``list`` of ``bytes`` objects; otherwise a JSON‑serialisable
            ``dict`` is expected.
        multipart
            When ``True`` use ``send_multipart``; otherwise use ``send_json``.
            Defaults to ``False``.

        Returns
        -------
        None
            No value is returned; the message is sent directly on the socket.

        Raises
        ------
        zmq.ZMQError
            Propagated from the underlying ZeroMQ socket if the send operation
            fails.
        """
        if multipart:
            self._socket.send_multipart(msg, copy=False)
        else:
            self._socket.send_json(msg)