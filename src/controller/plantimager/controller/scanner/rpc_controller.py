#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""RPC Controller

A module that implements a Remote Procedure Call (RPC) controller for handling client-server communication through JSON-RPC protocol.
This enables remote execution of functions with robust error handling and input validation.

Key Features
------------
- Executes RPC calls using dispatcher to route methods to appropriate handlers
- Validates input parameters against method specifications
- Handles and returns standardized error responses
- Supports both regular and notification RPC calls
- Preserves call context for security and tracing purposes
"""

from plantimager.commons.RPC import RPCProperty
from plantimager.commons.RPC import RPCServer
from plantimager.commons.controller_device import ControllerDevice
from plantimager.controller.scanner.scanner import Scanner


class RPCControllerServer(ControllerDevice, RPCServer):
    """An RPC server controlling a scanner device.

    This class combines the functionality of ControllerDevice and RPCServer to expose
    scanner control capabilities over RPC. It registers methods for configuring and
    running scans and properties for monitoring scan progress.

    Parameters
    ----------
    context : zmq.Context
        The context object for the RPC server.
    url : str
        The URL where the RPC server will be available.
    scanner : plantimager.controller.scanner.scanner.Scanner
        The scanner device to be controlled via RPC.

    Attributes
    ----------
    scanner : plantimager.controller.scanner.scanner.Scanner
        The scanner device being controlled.
    progress : int
        The current progress value of the scanner.
    max_progress : int
        The maximum progress value of the scanner.

    Notes
    -----
    This class connects the scanner's progress signals to its own signals to
    propagate progress updates to connected clients via RPC properties.

    See Also
    --------
    plantimager.commons.controller_device.ControllerDevice : Base class for controller functionality.
    plantimager.commons.RPC.RPCServer : Base class for RPC server functionality.
    plantimager.controller.scanner.scanner.Scanner : The scanner device being controlled.
    """

    def __init__(self, context, url, scanner: Scanner):
        """
        Initialize the RPC controller server.

        Parameters
        ----------
        context : zmq.Context
            The context object for the RPC server.
        url : str
            The URL where the RPC server will be available.
        scanner : plantimager.controller.scanner.scanner.Scanner
            The scanner device to be controlled via RPC.
        """
        RPCServer.__init__(self, context, url)
        self.scanner = scanner
        self.scanner.progressChanged.connect(self.progressChanged)
        self.scanner.maxProgressChanged.connect(self.maxProgressChanged)

    @RPCServer.register_method_json
    def set_config(self, config):
        """Configure the scanner with the provided configuration.

        Parameters
        ----------
        config : dict
            Configuration dictionary with scanner settings.
        """
        self.scanner.configure_scan(config)

    @RPCServer.register_method_json
    def run_scan(self):
        """Start a scanning operation with the current configuration."""
        self.scanner.scan()

    @RPCProperty(notify=ControllerDevice.progressChanged)
    def progress(self):
        """Get the current progress value of the scanner.

        Returns
        -------
        int
            The current progress value.
        """
        return self.scanner.progress

    @RPCProperty(notify=ControllerDevice.maxProgressChanged)
    def max_progress(self):
        """Get the maximum progress value of the scanner.

        Returns
        -------
        int
            The maximum progress value.
        """
        return self.scanner.max_progress

    def handle_scanner_changed(self, scanner):
        """Update the controlled scanner and synchronize progress values.

        This method is called when the scanner device changes. It updates the
        reference to the scanner and emits signals to update progress values.

        Parameters
        ----------
        scanner : plantimager.controller.scanner.scanner.Scanner
            The new scanner device to be controlled.
        """
        if self.scanner is not scanner:
            self.scanner = scanner
            self.scanner.progressChanged.emit(self.scanner.progress)
            self.scanner.maxProgressChanged.emit(self.scanner.progressChanged)
