#!/usr/bin/env python
# -*- coding: utf-8 -*-

from abc import ABC
from abc import abstractmethod

from plantimager.commons.RPC import RPCSignal, RPCProperty

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