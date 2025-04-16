#!/usr/bin/env python
# -*- coding: utf-8 -*-
from plantimager.commons.RPC import RPCProperty
from plantimager.commons.RPC import RPCServer
from plantimager.commons.controller_device import ControllerDevice
from plantimager.controller.scanner.scanner import Scanner


class RPCControllerServer(ControllerDevice, RPCServer):

    def __init__(self, context, url, scanner: Scanner):
        RPCServer.__init__(self, context, url)
        self.scanner = scanner
        self.scanner.progressChanged.connect(self.progressChanged)
        self.scanner.maxProgressChanged.connect(self.maxProgressChanged)

    @RPCServer.register_method_json
    def set_config(self, config):
        self.scanner.configure_scan(config)

    @RPCServer.register_method_json
    def run_scan(self):
        self.scanner.scan()

    @RPCProperty(notify=ControllerDevice.progressChanged)
    def progress(self):
        return self.scanner.progress

    @RPCProperty(notify=ControllerDevice.maxProgressChanged)
    def max_progress(self):
        return self.scanner.max_progress

    def handle_scanner_changed(self, scanner):
        if self.scanner is not scanner:
            self.scanner = scanner
            self.scanner.progressChanged.emit(self.scanner.progress)
            self.scanner.maxProgressChanged.emit(self.scanner.progressChanged)
