#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# plantimager - Python tools for the ROMI 3D Plant Imager
#
# Copyright (C) 2018 Sony Computer Science Laboratories
# Authors: D. Colliaux, T. Wintz, P. Hanappe
#
# This file is part of plantimager.
#
# plantimager is free software: you can redistribute it
# and/or modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation, either
# version 3 of the License, or (at your option) any later version.
#
# plantimager is distributed in the hope that it will be
# useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with plantimager.  If not, see
# <https://www.gnu.org/licenses/>.

from abc import ABC
from abc import ABCMeta
from abc import abstractmethod
from typing import List
from typing import Tuple

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



