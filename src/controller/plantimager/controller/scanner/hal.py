#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Hardware Abstraction Layer for Plant Imaging Systems.

This module provides abstract interfaces and data structures for hardware components
of plant imaging systems. It defines the core abstractions for CNC controllers and
data handling, enabling hardware independence in the scanning process.

Key Features:
- Abstract CNC interface for hardware-independent motion control
- Data structures for image and metadata handling
- Type-safe interfaces with proper unit annotations
- Support for different hardware implementations
- Standardized data formats for database storage
"""

from abc import ABC, ABCMeta, abstractmethod
from typing import List, Tuple, Union

import numpy as np
from plantdb.client.plantdb_client import PlantDBClient

from plantimager.commons.logging import create_logger
from plantimager.controller.scanner.path import Path, PathElement, Pose
from plantimager.controller.scanner.units import deg, length_mm

logger = create_logger(__name__)


class ChannelData(object):
    def __init__(self, name: str, data: np.array, idx: int):
        self.data = data
        self.idx = idx
        self.name = name

    def format_id(self):
        return "%05d_%s" % (self.idx, self.name)


class DataItem(object):
    def __init__(self, idx: int, image: bytes|memoryview, image_ext, metadata=None):
        self.image = image
        self.metadata = metadata
        self.idx = idx
        self.image_ext = image_ext


class AbstractCNC(metaclass=ABCMeta):
    """Abstract CNC class."""

    def __init__(self):
        pass

    @abstractmethod
    def home(self) -> None:
        pass

    @abstractmethod
    def get_position(self) -> Tuple[length_mm, length_mm, length_mm]:
        pass

    @abstractmethod
    def moveto(self, x: length_mm, y: length_mm, z: length_mm) -> None:
        pass

    @abstractmethod
    def moveto_async(self, x: length_mm, y: length_mm, z: length_mm) -> None:
        pass

    @abstractmethod
    def wait(self) -> None:
        pass
