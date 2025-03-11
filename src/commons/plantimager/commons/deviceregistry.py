import sys
from threading import Thread
from enum import StrEnum
from typing import Callable
import logging

logger = logging.getLogger('plantimager::deviceregistry')
logger.addHandler(logging.StreamHandler(sys.stderr))
logger.setLevel(logging.DEBUG)

import zmq


class EventType(StrEnum):
    REGISTER = "REGISTER"
    REGISTER_ACK = "REGISTER_ACK"
    UNREGISTER = "UNREGISTER"
    CHECK_ALIVE = "CHECK_ALIVE"
    ACK = "ACK"
    UNSUPORTED = "UNSUPORTED"

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

UNSUPORTED_MSG = {
    "event": EventType.UNSUPORTED,
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

    def run(self):
        with self.context.socket(zmq.REP) as socket:
            socket.bind(f"tcp://{self.addr}:{self.port}")
            logger.info(f"Starting registry on {self.addr}:{self.port}")
            while True:
                message = socket.recv_json()
                event_type: str = message["event"]
                payload: dict = message["payload"]
                match event_type:
                    case EventType.REGISTER:
                        name = self._handle_register(payload)
                        socket.send_json({
                            "event": EventType.REGISTER_ACK,
                            "payload": {
                                "name": name,
                            }
                        })
                    case EventType.UNREGISTER:
                        result = self._handle_unregister(payload)
                        socket.send_json({
                            "event": EventType.ACK,
                            "payload": {
                                "req_event": EventType.UNREGISTER,
                                "success": result,
                            }
                        })
                    case _:
                        logger.warning(f"Unknown event type: {event_type}")
                        socket.send_json({
                            "event": EventType.UNSUPORTED,
                            "payload": {
                                "req_event": event_type,
                            }
                        })

    def _handle_register(self, payload: dict):
        device_type = payload["device_type"]
        addr = payload["addr"]
        proposed_name = payload["name"]
        for name, (device_type, address) in self.devices.items():
            if address == addr:
                self._remove_device(name)
        self._add_device(device_type, addr, proposed_name)
        return True

    def _handle_unregister(self, payload: dict):
        device_type = payload["device_type"]
        addr = payload["addr"]
        name = payload["name"]
        return self._remove_device(name)


    def _add_device(self, device_type: str, addr: str, name: str = None):
        i = 0
        if not name:
            name = f"{device_type}-{i}"
        while name in self.devices:
            i += 1
            name = f"{device_type}-{i}"
        self.devices[name] = (device_type, addr)
        for callback in self._new_device_callbacks:
            callback(device_type, addr, name)
        logger.info(f"Added new device {name}")
        return name

    def _remove_device(self, name: str):
        if name in self.devices:
            device_type, addr = self.devices[name]
            del self.devices[name]
            for callback in self._device_removed_callbacks:
                callback(device_type, addr, name)
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



def register_device(context: zmq.Context, device_type: str, addr: str, name: str, registry_addr:str) -> str:
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
    return None

