#!/usr/bin/env python
# -*- coding: utf-8 -*-

from abc import ABC
from abc import abstractmethod

from plantimager.commons.RPC import RPCProperty
from plantimager.commons.RPC import RPCSignal


class ControllerDevice(ABC):
    """Abstract class for controller device."""

    progressChanged = RPCSignal(int)
    maxProgressChanged = RPCSignal(int)
    readyToScanChanged = RPCSignal(bool)
    cameraNamesChanged = RPCSignal(list[str])

    def __init__(self):
        pass

    @abstractmethod
    def set_db_url(self, url: str):
        """Set the database URL for the controller."""
        pass

    @abstractmethod
    def set_config(self, config: dict):
        """Send a configuration dictionary to the controller."""
        pass

    @abstractmethod
    def set_dataset_name(self, name: str):
        """Set the name of the dataset to be created."""
        pass

    @abstractmethod
    def set_api_token(self, token: str):
        """Set the session token to use for authenticated requests."""
        pass

    @abstractmethod
    def run_scan(self):
        """Start the scan."""
        pass

    @RPCProperty(notify=progressChanged)
    @abstractmethod
    def progress(self) -> int:
        """Return the current progress of the scan."""
        pass

    @RPCProperty(notify=maxProgressChanged)
    @abstractmethod
    def max_progress(self) -> int:
        """Return the maximum progress of the scan."""
        pass

    @RPCProperty(notify=readyToScanChanged)
    @abstractmethod
    def ready_to_scan(self) -> bool:
        """Return whether the controller is ready to start a scan."""
        pass

    @RPCProperty(notify=cameraNamesChanged)
    @abstractmethod
    def camera_names(self) -> list[str]:
        """Return the list of camera names."""
        pass

    def get_camera_image(self, name: str, lores: bool = True) -> tuple[memoryview, dict]:
        """Capture one image from a camera (JPEG bytes + info dict).

        Concrete servers override this; the default only documents the
        contract so ``register_interface`` proxies it to WebUI clients
        even where a server never implemented it.
        """
        raise NotImplementedError

    def get_camera_config(self, name: str) -> dict:
        """Return the live control dict of one camera; see above."""
        raise NotImplementedError

    def set_camera_config(self, name: str, config: dict) -> dict:
        """Apply a control dict to one camera, return the effective config."""
        raise NotImplementedError

    def get_camera_controls_schema(self, name: str) -> dict:
        """Return the advertised libcamera controls schema of one camera."""
        raise NotImplementedError

    def set_camera_default_controls(self, name: str, config: dict) -> dict:
        """Validate, apply and persist new defaults for one camera."""
        raise NotImplementedError

    def reset_camera_controls(self, name: str, factory: bool = False) -> dict:
        """Reset one camera to persisted (or factory) defaults."""
        raise NotImplementedError
