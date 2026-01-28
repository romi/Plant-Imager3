#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""RPC Controller for Plant Imaging Systems.

A module that implements a Remote Procedure Call (RPC) controller for handling client-server communication through JSON-RPC protocol.
This enables remote execution of scanner control functions with robust error handling and input validation.

Key Features
------------
- Executes RPC calls using dispatcher to route methods to appropriate handlers
- Validates input parameters against method specifications
- Handles and returns standardized error responses
- Supports both regular and notification RPC calls
- Provides properties for monitoring scan progress
- Exposes scanner configuration and control methods remotely
- Preserves call context for security and tracing purposes

Usage Examples
--------------
```python
>>> import zmq
>>> from plantimager.controller.scanner.scanner import Scanner
>>> from plantimager.controller.scanner.rpc_controller import RPCControllerServer
>>> # Create a scanner instance
>>> scanner = Scanner()
>>> # Create a ZeroMQ context
>>> context = zmq.Context()
>>> # Create an RPC server for the scanner
>>> server = RPCControllerServer(context, "tcp://*:5555", scanner)
>>> # Start the server
>>> server.start()
```
"""

from plantimager.commons.RPC import RPCProperty, RPCServer
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
        self.scanner.progressChanged.connect(self.progressChanged.emit)
        self.scanner.maxProgressChanged.connect(self.maxProgressChanged.emit)
        self.scanner.readyToScanChanged.connect(self.readyToScanChanged.emit)
        self.scanner.cameraNamesChanged.connect(self.cameraNamesChanged.emit)


    @RPCServer.register_method_json
    def set_db_url(self, url: str):
        """Set the database URL for the scanner.

        Parameters
        ----------
        url : str
            The URL, including protocol and port, of the database to connect to.
        """
        self.scanner.set_db_url(url)

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
    def set_dataset_name(self, name: str):
        """Set the name of the dataset to be created.

        Parameters
        ----------
        name : str
            The name of the dataset to be created.
        """
        self.scanner.set_scan_id(name)

    @RPCServer.register_method_json
    def set_session_token(self, token: str):
        """Set the session token for plantdb

        Parameters
        ----------
        token : str
            Session token
        """
        self.scanner.set_session_token(token)

    @RPCServer.register_method_json
    def set_session_token(self, token: str):
        """Set the session token to use for authenticated requests.

        Parameters
        ----------
        token : str
            The session token to use for authenticated requests.
        """
        self.scanner.set_session_token(token)

    @RPCServer.register_method_json(timeout=None)
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

    @RPCProperty(notify=ControllerDevice.readyToScanChanged)
    def ready_to_scan(self) -> bool:
        """Get whether the scanner is ready to start a scan.

        Returns
        -------
        bool
            True if the scanner is ready to start a scan, False otherwise.
        """
        return self.scanner.ready_to_scan

    @RPCProperty(notify=ControllerDevice.cameraNamesChanged)
    def camera_names(self) -> list[str]:
        """Return the list of camera names."""
        return self.scanner.camera_names

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
            self.scanner.progressChanged.connect(self.progressChanged.emit)
            self.scanner.maxProgressChanged.connect(self.maxProgressChanged.emit)
            self.scanner.readyToScanChanged.connect(self.readyToScanChanged.emit)
            self.scanner.cameraNamesChanged.connect(self.cameraNamesChanged.emit)
            self.progressChanged.emit(self.scanner.progress)
            self.maxProgressChanged.emit(self.scanner.max_progress)
            self.readyToScanChanged.emit(self.scanner.ready_to_scan)
            self.cameraNamesChanged.emit(self.scanner.camera_names)
