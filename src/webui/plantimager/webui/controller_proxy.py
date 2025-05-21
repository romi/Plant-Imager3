#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Controller Proxy Module

This module provides a bridge between the local controller device functionality and remote RPC communication, allowing applications to interact with controller hardware through a network connection.

Key Features
------------
- Singleton pattern implementation ensuring only one controller proxy exists
- Transparent proxying of controller device methods to remote systems
- ZeroMQ-based RPC communication for reliable client-server interactions
- Consistent interface matching the local controller device API

Usage Examples
--------------
```python
>>> import zmq
>>> from plantimager.webui.controller_proxy import RPCController
>>>
>>> # Initialize the controller proxy
>>> context = zmq.Context()
>>> controller = RPCController(context, "tcp://localhost:14567")
>>>
>>> # Access the singleton instance elsewhere in your code
>>> same_controller = RPCController.instance()
>>>
>>> # Use controller methods as if they were local
>>> controller.some_method()  # This will be executed on the remote system
```
"""

import zmq

from plantimager.commons.RPC import RPCClient
from plantimager.commons.controller_device import ControllerDevice


@RPCClient.register_interface(ControllerDevice)
class RPCController(ControllerDevice, RPCClient):
    """Proxy of controller and RPC server.

    A singleton class that serves as a proxy between a controller device and an RPC server.
    Only one instance of this class can exist at a time, and it can be accessed through
    the `instance` class method.

    Parameters
    ----------
    context : zmq.Context
        The ZeroMQ context to use for communication.
    url : str
        The URL to connect to for RPC communication.

    Attributes
    ----------
    _instance : RPCController or None
        Class variable that holds the single instance of the class.

    Notes
    -----
    This class implements the Singleton design pattern.
    The first time it is instantiated, it creates a new instance and stores it in the `_instance` class variable.
    Subsequent instantiations return the existing instance.

    The class inherits from both `ControllerDevice` and `RPCClient` to provide controller
    functionality over an RPC connection.

    See Also
    --------
    plantimager.commons.controller_device.ControllerDevice : Base class for controller device functionality.
    plantimager.commons.RPC.RPCClient : Base class for RPC client functionality.

    Examples
    --------
    >>> import zmq
    >>> from plantimager.webui.controller_proxy import RPCController
    >>> context = zmq.Context()
    >>> controller = RPCController(context, "tcp://localhost:14567")
    >>> # This returns the same instance
    >>> controller2 = RPCController(context, "tcp://localhost:14567")
    >>> controller is controller2
    True
    >>> # Get the singleton instance
    >>> RPCController.instance()
    RuntimeError: Controller proxy not initialized.
    """
    _instance = None

    def __new__(cls, context: zmq.Context, url: str):
        """Create a new instance or return the existing instance.

        Parameters
        ----------
        context : zmq.Context
            The ZeroMQ context to use for communication.
        url : str
            The URL to connect to for RPC communication.

        Returns
        -------
        plantimager.commons.controller_device.RPCController
            The singleton instance of this class.
        """
        if cls._instance is None:
            instance = super(RPCController, cls).__new__(cls)
            return instance
        return cls._instance

    def __init__(self, context: zmq.Context, url: str):
        """Initialize the RPCController.

        Parameters
        ----------
        context : zmq.Context
            The ZeroMQ context to use for communication.
        url : str
            The URL to connect to for RPC communication.
        """
        RPCClient.__init__(self, context, url)
        self.__class__._instance = self

    @classmethod
    def instance(cls) -> "RPCController":
        """Get the singleton instance of the RPCController.

        Returns
        -------
        plantimager.commons.controller_device.RPCController
            The singleton instance of this class.

        Raises
        ------
        RuntimeError
            If the controller proxy has not been initialized yet.
        """
        if cls._instance is None:
            raise RuntimeError("Controller proxy not initialized.")
        return cls._instance


if __name__ == "__main__":
    context = zmq.Context()
    RPCController(context, "tcp://localhost:14567")
    controller = RPCController.instance()
    print(controller.progress)
    print(controller.max_progress)
    print(controller.ready_to_scan)
    print(controller.camera_names)
