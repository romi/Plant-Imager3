#!/usr/bin/env python
# -*- coding: utf-8 -*-
import zmq

from plantimager.commons.RPC import RPCClient
from plantimager.commons.controller_device import ControllerDevice


@RPCClient.register_interface(ControllerDevice)
class RPCController(ControllerDevice, RPCClient):
    """Proxy of controller and RPC server."""
    _instance = None

    def __new__(cls, context: zmq.Context, url: str):
        if cls._instance is None:
            super(RPCController, cls).__new__(cls)
        return cls._instance

    def __init__(self, context: zmq.Context, url: str):
        RPCClient.__init__(self, context, url)
        self.__class__._instance = self

    @classmethod
    def instance(cls):
        if cls._instance is None:
            raise RuntimeError("Controller proxy not initialized.")
        return cls._instance
