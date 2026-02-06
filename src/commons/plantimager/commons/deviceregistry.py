import time
from threading import Thread, RLock
from enum import StrEnum
from typing import Callable, Literal
from uuid import uuid1

import zmq
from plantimager.commons.logging import create_logger

logger = create_logger('deviceregistry')

__all__ = ['DeviceRegistry', "register_device", "unregister_device"]

ALIVE_TIMEOUT = 20  # seconds

class EventType(StrEnum):
    REGISTER = "REGISTER"
    REGISTER_ACK = "REGISTER_ACK"
    UNREGISTER = "UNREGISTER"
    CHECK_ALIVE = "CHECK_ALIVE"
    ACK = "ACK"
    UNSUPPORTED = "UNSUPPORTED"

REGISTER_MSG = {
    "event": EventType.REGISTER,
    "payload": {
        "device_type": type,
        "addr": "",
        "name": "",
        "overwrite": bool # if present and true, the new device will replace any registered device with the same name
    }
}

REGISTER_ACK_MSG = {
    "event": EventType.REGISTER_ACK,
    "payload": {
        "name": "",
        "uuid": "",
    }
}

UNREGISTER_MSG = {
    "event": EventType.UNREGISTER,
    "payload": {
        "uuid": ""
    }
}

CHECK_ALIVE_MSG = {
    "event": EventType.CHECK_ALIVE,
    "payload": {
        "uuid": "",
        "alive_timeout": 20  # seconds (optional)
    }
}

ACK_MSG = {
    "event": EventType.ACK,
    "payload": {
        "req_event": None,
        "success": True,
    }
}

UNSUPPORTED_MSG = {
    "event": EventType.UNSUPPORTED,
    "payload": {
        "req_event": None,
    }
}

class DeviceRegistry(Thread):
    """
    A thread-based Device Registry for managing registering and unregistering devices.

    This class provides a thread-based mechanism to handle device registration and
    unregistration events. It communicates using ZeroMQ sockets and fires appropriate
    callbacks when devices are added or removed.

    Attributes
    ----------
    addr : str
        Address on which the registry will bind.
    port : str
        Port on which the registry will listen for messages.
    context : zmq.Context
        ZeroMQ context used for setting up the communication socket.
    devices : dict of str to tuple of (str, str)
        Dictionary mapping device names to a tuple of (device_type, address).
    _new_device_callbacks : list of Callable
        List of callback functions to execute when a new device is added.
    _device_removed_callbacks : list of Callable
        List of callback functions to execute when a device is removed.
    _stop : bool
        Control flag to indicate whether the registry thread should stop.
    _callback_events_to_process : dict of str (Literal["added", "removed"]) to list of tuple
        Dictionary containing lists of registered or removed devices to process
        callbacks for.
    """
    def __init__(self, context: zmq.Context, addr: str = "*", port: str = "5555"):
        super().__init__()
        self.addr: str = addr
        self.port: str = port
        self.context: zmq.Context = context
        self._lock = RLock()
        self._new_device_callbacks: list[Callable] = []
        self._device_removed_callbacks: list[Callable] = []
        self._callback_events_to_process: dict[Literal["added", "removed"], list[tuple[str, str, str]]] = {
            "added": [], "removed": []
        }
        self.devices: dict[str, tuple[str, str]] = {}  # name --> (device_type, addr)
        self.device_names: dict[str, str] = {}  # uuid --> name
        self.device_health_timeout: dict[str, int] = {} # uuid --> expiration time
        self._stop = False

    def stop(self):
        """Stop the registry thread."""
        self._device_removed_callbacks = []
        self._new_device_callbacks = []
        self._stop = True

    def run(self):
        """
        Runs the main loop for the registry service, handling device registration, unregistration, and
        device-related event callbacks. The service listens for messages using ZeroMQ (zmq) and processes
        the events accordingly.
        """
        with self.context.socket(zmq.REP) as socket:
            socket.bind(f"tcp://{self.addr}:{self.port}")
            logger.info(f"Starting registry on {self.addr}:{self.port}")
            while not self._stop:
                self._prune_unhealthy_devices()
                # Fire callbacks for removed and added devices after responding back
                for device_type, addr, name in self._callback_events_to_process["removed"]:
                    for callback in self._device_removed_callbacks:
                        callback(device_type, addr, name)
                self._callback_events_to_process["removed"].clear()
                for device_type, addr, name in self._callback_events_to_process["added"]:
                    for callback in self._new_device_callbacks:
                        callback(device_type, addr, name)
                self._callback_events_to_process["added"].clear()

                # in order for the thread to stop properly, it must not block indefinitely while waiting for
                # a message, hence polling for 100 ms and continue-ing if timeout
                if socket.poll(100) == 0:
                    continue
                message = socket.recv_json()
                event_type: str = message["event"]
                payload: dict = message["payload"]
                logger.debug(f"Received event: {event_type}, {payload}")
                match event_type:
                    case EventType.REGISTER:
                        device_type = payload["device_type"]
                        addr = payload["addr"]
                        proposed_name = payload["name"]
                        overwrite = payload["overwrite"] if "overwrite" in payload else False
                        name, uuid = self._handle_register(device_type, addr, proposed_name, overwrite=overwrite)
                        socket.send_json({
                            "event": EventType.REGISTER_ACK,
                            "payload": {
                                "name": name,
                                "uuid": str(uuid),
                            }
                        })
                    case EventType.UNREGISTER:
                        uuid = payload["uuid"]
                        if uuid in self.device_names:
                            result = self._remove_device_by_uuid(uuid)
                        else:
                            result = False
                            logger.warning(f"Device of id {uuid} not found in registry")
                        socket.send_json({
                            "event": EventType.ACK,
                            "payload": {
                                "req_event": EventType.UNREGISTER,
                                "success": result,
                            }
                        })

                    case EventType.CHECK_ALIVE:
                        uuid = payload["uuid"]
                        timeout = payload.get("alive_timeout", ALIVE_TIMEOUT)
                        if uuid in self.device_health_timeout:
                            self.device_health_timeout[uuid] = int(time.time()) + timeout
                            socket.send_json({
                                "event": EventType.ACK,
                                "payload": {
                                    "req_event": EventType.CHECK_ALIVE,
                                    "success": True,
                                }
                            })
                        else:
                            socket.send_json({
                                "event": EventType.ACK,
                                "payload": {
                                    "req_event": EventType.CHECK_ALIVE,
                                    "success": False,
                                }
                            })
                    case _:
                        logger.warning(f"Unknown event type: {event_type}")
                        socket.send_json({
                            "event": EventType.UNSUPPORTED,
                            "payload": {
                                "req_event": event_type,
                            }
                        })
        logger.info(f"Registry stopped on {self.addr}:{self.port}")

    def _prune_unhealthy_devices(self):
        """
        Remove devices whose health timeout has expired.

        This internal helper scans the ``device_health_timeout`` mapping for
        entries whose expiration timestamp is greater than the current Unix
        epoch time and removes the corresponding devices via
        ``_remove_device_by_uuid``.  It is typically invoked by a maintenance
        routine to keep the device registry up‑to‑date.

        Notes
        -----
        - The method operates on the ``device_health_timeout`` attribute, which
          maps device UUIDs (as strings) to integer expiration timestamps.
        - Devices are removed only if their stored expiration time is **greater**
          than the current time; adjust the comparison if the intended logic is
          the opposite.
        - This method is intended for internal use; external callers should
          prefer higher‑level APIs.

        See Also
        --------
        _remove_device_by_uuid : Remove a device from the registry by its UUID.

        """
        now = int(time.time())
        to_remove = [
            uuid for uuid, expiration_time in self.device_health_timeout.items()
            if expiration_time < now
        ]
        for uuid in to_remove:
            logger.info(f"Device {uuid} timed out. Removing.")
            self._remove_device_by_uuid(uuid)

    def _handle_register(self, device_type: str, addr: str, proposed_name: str, overwrite: bool=False) -> str:
        """
        Register a device while resolving address or name conflicts.

        This method checks the current device registry for existing entries that
        share the same address or name as the proposed registration.  If a conflict
        is found and ``overwrite`` is ``False``, the conflicting device is removed
        and a warning is logged.  When ``overwrite`` is ``True`` the method will
        replace any device that matches either the address or the name with the
        new registration.  After handling conflicts the device is added via
        ``_add_device`` and the final stored name is returned.

        Parameters
        ----------
        device_type
            Identifier of the device class (e.g., ``'sensor'`` or ``'actuator'``).
        addr
            Unique address of the device (for example an IP address expressed as a
            string).
        proposed_name
            Desired name under which the device should be stored in the registry.
        overwrite
            If ``True``, allow existing devices with the same name or address to be
            replaced; defaults to ``False``.

        Returns
        -------
        The name that was finally stored for the device (the result of
        ``_add_device``).

        Raises
        ------
        RuntimeError
            Propagated from ``_add_device`` if the device cannot be added.

        Notes
        -----
        * The method works on a shallow copy of ``self.devices`` to avoid mutating
          the dictionary while iterating.
        * Conflicting entries are removed before the new device is added.
        * Each conflict generates a ``warning`` level log entry describing the
          action taken.

        See Also
        --------
        _add_device, _remove_device_by_name
        """
        device_list_copy = self.devices.copy()
        for name, val in device_list_copy.items():
            _, address = val
            if address == addr and not (name == proposed_name and overwrite):
                logger.warning(f"Another device is registered at address {addr} with name {name}. Overwriting with new name {proposed_name} and removing old device with name {name}")
                self._remove_device_by_name(name)
            if name == proposed_name and overwrite:
                logger.warning(f"Registration with overwrite active. Another device found with the same name {name}. Overwriting old device at address {address} with new device at {addr}")
                self._remove_device_by_name(name)
        return self._add_device(device_type, addr, proposed_name)

    def _add_device(self, device_type: str, addr: str, proposed_name: str = None) -> str:
        with self._lock:
            i = 0
            if not proposed_name:
                name = f"{device_type}-{i}"
            else:
                name = proposed_name
            while name in self.devices:
                i += 1
                name = f"{proposed_name}-{i}"
            uuid = uuid1()
            self.device_names[str(uuid)] = name
            self.devices[name] = (device_type, addr)
            self.device_health_timeout[str(uuid)] = int(time.time()) + ALIVE_TIMEOUT

        logger.info(f"Added new device {name}")
        self._callback_events_to_process["added"].append((device_type, addr, name))
        return name, uuid

    def _remove_device_by_uuid(self, uuid: str):
        if uuid in self.device_names and self.device_names[uuid] in self.devices:
            name = self.device_names[uuid]
            device_type, addr = self.devices[name]
            with self._lock:
                del self.devices[name]
                del self.device_names[uuid]
                del self.device_health_timeout[uuid]
            logger.info(f"Removed device {name} with id {uuid} from registry. Device type: {device_type}, address: {addr}")
            self._callback_events_to_process["removed"].append((device_type, addr, name))
            return True
        return False

    def _remove_device_by_name(self, name: str):
        if name in self.devices:
            uuids = [uuid for uuid, name_ in self.device_names.items() if name == name_]
            for uuid in uuids:
                self._remove_device_by_uuid(uuid)

    def add_new_device_callback(self, callback: Callable):
        """
        Register a callback function to be executed when a new device is registered.
        """
        self._new_device_callbacks.append(callback)

    def add_device_removed_callback(self, callback: Callable):
        """
        Register a callback function to be executed when a device is removed.
        """
        self._device_removed_callbacks.append(callback)

    def get_devices(self) -> dict[str, tuple[str, str]]:
        """
        Returns the registered devices.

        Returns
        -------
        dict[str, tuple[str, str]]
            A dictionary where the keys are device identifiers as strings and the
            values are tuples containing the name and type of the device as strings.
        """
        with self._lock:
            return self.devices



def register_device(
        context: zmq.Context, device_type: str, addr: str, name: str, registry_url: str, overwrite: bool=False
) -> tuple[str, str]:
    """
    Register device of type `device_type` and of address `addr` to registry at `registry_url`.
    Proposes name to registry.

    Returns accepted device name and the uuid of the device if successful, otherwise an empty string.
    The uuid must be kept to unregister the device later.
    """
    with context.socket(zmq.REQ) as socket:
        with socket.connect(registry_url):
            socket.send_json({
                "event": EventType.REGISTER,
                "payload": {
                    "device_type": device_type,
                    "addr": addr,
                    "name": name,
                    "overwrite": overwrite,
                }
            })
            reply = socket.recv_json()
            event_type = reply["event"]
            payload = reply["payload"]
            if event_type == EventType.REGISTER_ACK:
                registered_name = payload["name"]
                uuid = payload["uuid"]
                return registered_name, uuid
    return "", ""


def unregister_device(context: zmq.Context, uuid: str, registry_addr: str) -> bool:
    """
    Unregister the device of the given uuid from the registry at `registry_addr`.
    Returns True if the device was unregistered successfully.
    """
    with context.socket(zmq.REQ) as socket:
        socket: zmq.Socket
        with socket.connect(registry_addr):
            socket.send_json({
                "event": EventType.UNREGISTER,
                "payload": {
                    "uuid": uuid,
                }
            })
            if socket.poll(5000, flags=zmq.POLLIN) == 0:
                logger.debug(f"No answer from registry at address {registry_addr}. Closing")
                return False
            reply = socket.recv_json()
            event_type = reply["event"]
            if event_type == EventType.ACK:
                return True
            return False

def send_alive_check(context: zmq.Context, uuid: str, registry_url: str, alive_timeout: int=ALIVE_TIMEOUT) -> bool:
    """Check the liveness of a service with the registry.

    Send an ``EventType.CHECK_ALIVE`` request to the registry and wait for an
    ``EventType.ACK`` reply.  The function opens a ``REQ`` socket on the provided
    ZeroMQ ``context``, sends the payload containing ``uuid`` and ``alive_timeout``,
    and returns ``True`` only when an acknowledgement is received within the
    socket poll timeout (5s).  Any other reply or the lack of a reply results in
    ``False``.

    Parameters
    ----------
    context
        ZeroMQ :class:`zmq.Context` used to create the ``REQ`` socket.
    uuid
        Unique identifier of the service performing the alive check.
    registry_url
        URL of the registry (e.g., ``tcp://127.0.0.1:5555``) to which the request
        is sent.
    alive_timeout
        Timeout (in seconds) that the service claims it will stay alive.  The
        value is included in the request payload.  Defaults to ``ALIVE_TIMEOUT``.

    Returns
    -------
    bool
        ``True`` if the registry answered with ``EventType.ACK``, otherwise
        ``False``.

    Raises
    ------
    zmq.ZMQError
        Propagated if ZeroMQ encounters an error while creating the socket,
        connecting, sending, or receiving messages.

    Notes
    -----
    * The socket is created inside a ``with`` block, guaranteeing that it is
      closed when the block exits.  The explicit ``socket.close()`` calls are
      retained for clarity but are not strictly required.
    * The function uses a fixed poll timeout of 5 seconds; this value is not
      configurable via the public API.
    * ``alive_timeout`` is merely echoed back to the registry and is not used by
      this function to enforce any timing constraints.

    See Also
    --------
    `EventType` – enumeration of supported event types.
    """
    with context.socket(zmq.REQ) as socket:
        socket: zmq.Socket
        with socket.connect(registry_url):
            socket.send_json({
                "event": EventType.CHECK_ALIVE,
                "payload": {
                    "uuid": uuid,
                    "alive_timeout": alive_timeout,
                }
            })
            if socket.poll(5000, flags=zmq.POLLIN) == 0:
                logger.debug(f"No answer from registry at address {registry_url}. Closing")
                return False
            reply = socket.recv_json()
            event_type = reply["event"]
            if event_type == EventType.ACK:
                return True
            return False