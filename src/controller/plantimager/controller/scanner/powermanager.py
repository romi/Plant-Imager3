"""
Manages the switching on and off of the various components of the scanner via the GPIO
"""
import os

from PySide6.QtCore import QObject, Signal, Slot, Property
import gpio

from plantimager.controller.scanner.grbl import CNC


class PowerManager(QObject):

    def __init__(self, warmup_period: int, parent=None):
        super().__init__(parent)

    def cnc_power_on(self):
        pass
        self.cnc = CNC()
        self.cnc.moveto(20, 20, 45)

    def cnc_power_off(self):
        pass

    def lights_power_on(self):
        pass

    def lights_power_off(self):
        pass

    def glights_power_on(self):
        pass

    def glights_power_off(self):
        pass

    def prepare_for_scan(self):
        self.cnc_power_on()
        self.lights_power_on()
        self.glights_power_off()

    def get_cnc(self):

        return self.cnc