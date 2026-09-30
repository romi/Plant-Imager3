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

import functools

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot


class _MainThreadInvoker(QObject):
    """Runs callables on the thread that creates it (the Qt main thread).

    The ``request`` signal is connected with ``BlockingQueuedConnection``,
    so emitting it from the RPC server thread blocks until the slot has
    run on the main thread — no ``QTimer.singleShot`` needed.
    """

    request = Signal(object)

    def __init__(self):
        super().__init__()
        self.request.connect(self._execute_box, Qt.ConnectionType.BlockingQueuedConnection)

    @Slot(object)
    def _execute_box(self, box):
        try:
            box["result"] = box["call"]()
        except Exception as exc:
            box["error"] = exc


def run_on_main_thread(fn):
    """Execute an RPC method on the Qt main thread, blocking for its result.

    RPC requests are served on a plain Python thread with no Qt event
    loop, so methods that create ``QObject``s (or arm their ``QTimer``s)
    must hop to the main thread or their timers never fire. Stack this
    innermost, directly above ``def``; ``functools.wraps`` plus the
    explicit copy below preserve the ``register_method_*`` flags so RPC
    registration keeps working.
    """
    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        return self._invoke_on_main_thread(functools.partial(fn, self, *args, **kwargs))

    for _attr in ("_is_json_method", "_timeout", "_is_buffer_method"):
        if hasattr(fn, _attr):
            setattr(wrapper, _attr, getattr(fn, _attr))
    return wrapper


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
        # Created here on the Qt main thread; RPC requests hop back to it
        # via run_on_main_thread. Plain QObject: no parent, owned by self.
        self._main_thread_host = _MainThreadInvoker()
        self.scanner.progressChanged.connect(self.progressChanged.emit)
        self.scanner.maxProgressChanged.connect(self.maxProgressChanged.emit)
        self.scanner.readyToScanChanged.connect(self.readyToScanChanged.emit)
        self.scanner.cameraNamesChanged.connect(self.cameraNamesChanged.emit)

    def _invoke_on_main_thread(self, call):
        """Run ``call`` on the Qt main thread and return its result.

        Falls back to a direct call when already on the main thread (a
        blocking-queued emit to self would deadlock) or when the invoker
        is missing (servers built without ``__init__``, as in unit tests).
        Server-side exceptions are re-raised so ``_exec_json`` still
        reports ``{"success": False}``.
        """
        host = getattr(self, "_main_thread_host", None)
        if host is None or QThread.currentThread() is host.thread():
            return call()
        box = {"call": call, "result": None, "error": None}
        host.request.emit(box)
        if box["error"] is not None:
            raise box["error"]
        return box["result"]

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
    def set_base_name(self, name: str):
        """Set the base name — bare scan uses it as scan_id, timelapse as timelapse_id.

        Parameters
        ----------
        name : str
            Base name for the next scan or timelapse.
        """
        self.scanner.set_base_name(name)

    @RPCServer.register_method_json
    def set_api_token(self, token: str):
        """Set the api token to use for authenticated requests.

        Parameters
        ----------
        token : str
            The session token to use for authenticated requests.
        """
        self.scanner.set_api_token(token)

    @RPCServer.register_method_json(timeout=None)
    def run_scan(self):
        """Start a scanning operation with the current configuration."""
        self.scanner.scan()

    @RPCServer.register_method_json
    @run_on_main_thread
    def config_timelapse(self, config):
        """Create a CONFIGURED draft (no arm/persist) and return its snapshot."""
        return self.scanner.config_timelapse(config)

    @RPCServer.register_method_json(timeout=None)
    @run_on_main_thread
    def start_timelapse(self, config=None):
        """Create and start a timelapse. With config=None arms the CONFIGURED draft."""
        return self.scanner.start_timelapse(config)

    @RPCServer.register_method_json()
    def get_active_timelapse(self):
        """Return a serialisable snapshot of the active timelapse, or None."""
        return self.scanner.get_active_timelapse()

    @RPCServer.register_method_json()
    def cancel_timelapse(self):
        """Cancel the active timelapse, if any."""
        self.scanner.cancel_timelapse()

    @RPCServer.register_method_json()
    def preview_timelapse(self, config):
        """Return the schedule computed for a config, without starting it.

        Parameters
        ----------
        config : dict
            Timelapse configuration to preview.

        Returns
        -------
        dict
            Computed schedule: ``{"mode": str, "schedule_times": [iso, ...],
            "n_scans": int}``.
        """
        return self.scanner.preview_timelapse(config)

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
