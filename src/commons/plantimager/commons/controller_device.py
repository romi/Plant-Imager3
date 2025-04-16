#!/usr/bin/env python
# -*- coding: utf-8 -*-

from abc import ABC
from abc import abstractmethod

from plantimager.commons.RPC import RPCSignal, RPCProperty

class ControllerDevice(ABC):
    """Abstract class for controller device."""

    progressChanged = RPCSignal(int)
    maxProgressChanged = RPCSignal(int)

    def __init__(self):
        pass

    @abstractmethod
    def set_config(self, config):
        """Send configuration dictionary to the controller."""
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