# plantimager.picamera package

This package is meant to be installed on a raspberry-pi such as a raspberry-pi zero 2w.


## Install instruction

### 0. System Packages

Install the following packages
```shell
sudo apt install libzmq python3-zmq python3.11-dev ffmpeg libcap-dev python3-av python3-pil libturbojpeg0 libjpeg7 python3-libcamera python3-kms++
```

### 1. Creating a venv

To install the package we need to create a venv which must also have access to the system packages

```shell
python3 -m venv --system-site-packages --symlinks picamera-env
```

Then to activate the venv:
```shell
source picamera-env/bin/activate
```

### 2. installing the package

#### From PyPI

```shell
pip install plantimager.picamera
```

#### From Source

```shell
git clone https://github.com/romi/Plant-Imager3.git
pip install Plant-Imager3/src/commons
pip install Plant-Imager3/src/picamera
```

## Using picamera

To launch the picamera RPC Server use the command

```shell
picamera-server
```
