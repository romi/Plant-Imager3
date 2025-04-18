# Plant-Imager3

[![Licence](https://img.shields.io/github/license/romi/Plant-Imager3?color=lightgray)](https://www.gnu.org/licenses/lgpl-3.0.en.html)
[![Python Version](https://img.shields.io/python/required-version-toml?tomlFilePath=https%3A%2F%2Fraw.githubusercontent.com%2Fromi%2FPlant-Imager3%2Frefs%2Fheads%2Fdevelop%2Fsrc%2Fcommons%2Fpyproject.toml&logo=python&logoColor=white)]()

This repository supersedes the earlier [Plant-Imager](https://github.com/romi/plant-imager) repository, aligning with the updated design and requirements of the _Plant Imager v3_ robot.

![ROMI_ICON2_greenB.png](assets/images/ROMI_ICON2_greenB.png)

## Overview

This repository contains three Python subpackages:

1. `picamera`: A Python package designed for the Raspberry Pi Zero W with a camera. It manages video streaming and image capture.
2. `controller`: A Qt-based Python package intended for the main Raspberry Pi 4 or 5. This package acts as the central controller and provides a touchscreen interface.
3. `webui`: A Dash-based Python package also for the main Raspberry Pi 4 or 5. It offers a client interface for plant scanning.

## Namespace Packages

The Plant-Imager3 project uses Python namespace packages to organize its codebase:

### plantimager.commons

This package contains common utilities and interfaces used by other packages:

- RPC communication framework
- Device registry for managing hardware components
- Camera device interfaces
- Controller device interfaces
- Logging utilities

### plantimager.controller

This package provides the main control interface for the Plant Imager hardware:

- Qt-based touchscreen application
- Scanner control (CNC, camera)
- Hardware abstraction layer
- Image processing and display

### plantimager.picamera

This package runs on the Raspberry Pi Zero W and provides camera functionality:

- Video streaming
- Image capture
- RPC interface for remote control

### plantimager.webui

This package provides a web-based user interface for plant scanning:

- Dash-based web application
- Scan configuration and execution
- Integration with the controller package

## Installation

For installation instructions, please refer to the [README](https://github.com/romi/Plant-Imager3) file in the repository.