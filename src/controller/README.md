# [![ROMI_logo](docs/assets/images/ROMI_logo_green_25.svg)](https://romi-project.eu) / plantimager.webui

[![Licence](https://img.shields.io/github/license/romi/plantdb?color=lightgray)](https://www.gnu.org/licenses/lgpl-3.0.en.html)
[![Python Version](https://img.shields.io/python/required-version-toml?tomlFilePath=https%3A%2F%2Fraw.githubusercontent.com%2Fromi%2Fplantdb%2Frefs%2Fheads%2Fdev%2Fsrc%2Fcommons%2Fpyproject.toml&logo=python&logoColor=white)]()

A Qt-based Python package intended for the main Raspberry Pi 4 or 5.
This package acts as the central controller and provides a touchscreen interface.

This package provides the main control interface for the Plant Imager hardware:

- Qt-based touchscreen application
- Scanner control (CNC, camera)
- Hardware abstraction layer
- Image processing and display

## Environment Setup

We strongly recommend using isolated environments to install ROMI libraries.

This documentation uses `conda` as both an environment and package manager.
If you don't have`miniconda3` installed, please refer to the [official documentation](https://docs.conda.io/en/latest/miniconda.html).

To create a new conda environment for PlantDB:
``` shell
conda create -n plant-imager3 'python==3.11' ipython
```

## Installation

Activate your environment and install the packages using `pip`:

``` shell
conda activate plant-imager3  # activate your environment first!
pip install plantimager.controller
```
