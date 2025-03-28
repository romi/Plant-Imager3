from threading import Thread
from enum import StrEnum
from typing import Callable

import zmq
from plantimager.commons.logging import create_logger

logger = create_logger('deviceregistry')

__all__ = ['DeviceRegistry', "register_device", "unregister_device"]

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
        "name": ""
    }
}

REGISTER_ACK_MSG = {
    "event": EventType.REGISTER_ACK,
    "payload": {
        "name": ""
    }
}

UNREGISTER_MSG = {
    "event": EventType.UNREGISTER,
    "payload": {
        "device_type": type,
        "addr": "",
        "name": ""
    }
}

CHECK_ALIVE_MSG = {
    "event": EventType.CHECK_ALIVE,
    "payload": {}
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

    def __init__(self, context: zmq.Context, addr: str = "*", port: str = "5555"):
        super().__init__()
        self.addr: str = addr
        self.port: str = port
        self.context: zmq.Context = context
        self._new_device_callbacks: list[Callable] = []
        self._device_removed_callbacks: list[Callable] = []
        self.devices: dict[str, (str, str)] = {}
        self._stop = False

    def stop(self):
        self._device_removed_callbacks = []
        self._new_device_callbacks = []
        self._stop = True

    def run(self):
        with self.context.socket(zmq.REP) as socket:
            socket.bind(f"tcp://{self.addr}:{self.port}")
            logger.info(f"Starting registry on {self.addr}:{self.port}")
            while not self._stop:
                # in order for the thread to stop properly it must not block indefinitely while waiting for
                # a message hence polling for 100 ms and continue-ing if timeout
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
                        name = self._handle_register(device_type, addr, proposed_name)
                        socket.send_json({
                            "event": EventType.REGISTER_ACK,
                            "payload": {
                                "name": name,
                            }
                        })
                        for callback in self._new_device_callbacks:
                            callback(device_type, addr, name)
                    case EventType.UNREGISTER:
                        name = payload["name"]
                        if name in self.devices:
                            device_type, addr = self.devices[name]
                        result = self._remove_device(name)
                        socket.send_json({
                            "event": EventType.ACK,
                            "payload": {
                                "req_event": EventType.UNREGISTER,
                                "success": result,
                            }
                        })
                        if result:
                            for callback in self._device_removed_callbacks:
                                callback(device_type, addr, name)


                    case _:
                        logger.warning(f"Unknown event type: {event_type}")
                        socket.send_json({
                            "event": EventType.UNSUPPORTED,
                            "payload": {
                                "req_event": event_type,
                            }
                        })
        logger.info(f"Registry stopped on {self.addr}:{self.port}")

    def _handle_register(self, device_type: str, addr: str, proposed_name: str) -> str:
        for name, val in self.devices.items():
            _, address = val
            if address == addr:
                self._remove_device(name)
        return self._add_device(device_type, addr, proposed_name)

    def _add_device(self, device_type: str, addr: str, proposed_name: str = None) -> str:
        i = 0
        if not proposed_name:
            name = f"{device_type}-{i}"
        else:
            name = proposed_name
        while name in self.devices:
            i += 1
            name = f"{proposed_name}-{i}"
        self.devices[name] = (device_type, addr)

        logger.info(f"Added new device {name}")
        return name

    def _remove_device(self, name: str):
        if name in self.devices:
            device_type, addr = self.devices[name]
            del self.devices[name]
            logger.info(f"Removed device {name}")
            return True
        return False

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

    def get_devices(self) -> dict[str, (str, str)]:
        return self.devices



def register_device(context: zmq.Context, device_type: str, addr: str, name: str, registry_addr: str) -> str:
    """
    Register device of type `device_type` and of address `addr` to registry at `registry_addr`.
    Proposes name to registry.

    Returns accepted device name.
    """
    with context.socket(zmq.REQ) as socket:
        socket.connect(registry_addr)
        socket.send_json({
            "event": EventType.REGISTER,
            "payload": {
                "device_type": device_type,
                "addr": addr,
                "name": name,
            }
        })
        reply = socket.recv_json()
        event_type = reply["event"]
        payload = reply["payload"]
        if event_type == EventType.REGISTER_ACK:
            registered_name = payload["name"]
            socket.close()
            return registered_name
        socket.close()
    return ""


def unregister_device(context: zmq.Context, name: str, registry_addr:str) -> bool:
    """
    Unregister device of the given name from registry at `registry_addr`.
    Returns True if device was unregistered successfully.
    """
    with context.socket(zmq.REQ) as socket:
        socket: zmq.Socket
        socket.connect(registry_addr)
        socket.send_json({
            "event": EventType.UNREGISTER,
            "payload": {
                "name": name,
            }
        })
        if socket.poll(5000, flags=zmq.POLLIN) == 0:
            logger.debug(f"No answer from registry at address {registry_addr}. Closing")
            socket.close()
            return False
        reply = socket.recv_json()
        event_type = reply["event"]
        payload = reply["payload"]
        if event_type == EventType.ACK:
            socket.close()
            return True
        socket.close()
        return False
