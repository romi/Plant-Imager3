# Plant-Imager3

This repository supersedes the earlier [Plant-Imager](https://github.com/romi/plant-imager) repository, aligning with the updated design and requirements of the _Plant Imager v3_ robot.

## About

This repository contains three Python subpackages:

1. `picamera`: A Python package designed for the Raspberry Pi Zero W with a camera. It manages video streaming and image capture.
2. `controller`: A Qt-based Python package intended for the main Raspberry Pi 4 or 5. This package acts as the central controller and provides a touchscreen interface.
3. `webui`: A Dash-based Python package also for the main Raspberry Pi 4 or 5. It offers a client interface for plant scanning.

## Developers

### System Requirements

To run the QtApp, you must install the required Mesa packages.
On Ubuntu, you can do this by executing the following commands:

```shell
sudo apt update
sudo apt install libegl1-mesa libgl1-mesa-dri libgl1-mesa-glx mesa-utils
```

### Create a Virtual Environment

If needed, start by creating a virtual environment named `plant_imager3`.
Use the following command:

```shell
conda create -n plant-imager3 'python==3.11' ipython
```

### Install `plantimager.commons`

To install the `plantimager.commons` subpackage, run the following command from the root directory of the repository:

```shell
pip install -e src/commons/.
```

### Install `plantimager.controller`

To install the `plantimager.controller` subpackage, run the following command from the root directory of the repository:

```shell
pip install -e src/controller/.
```

After installation, you can start the `PlantImagerApp` with:

```shell
plant-imager-controller-app
```

### Install `plantimager.picamera`

To install the `plantimager.picamera` subpackage, run the following command from the root directory of the repository:

```shell
pip install -e src/picamera/.
```

### Install `plantimager.webui`

To install the `plantimager.webui` subpackage, run the following command from the root directory of the repository:

```shell
pip install -e src/webui/.
```

After installation, you can start the Dash `WebUI` with:

```shell
plant-imager-webui
```

You will need to connect to a running FSDB REST API.

For testing purposes, providing that you have the `plantdb.commons` and `plantdb.server` libraries installed, you may start one with:
```shell
fsdb_rest_api --test
```