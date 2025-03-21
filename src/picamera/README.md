# plantimager.picamera package

This package is meant to be installed on a raspberry-pi such as a raspberry-pi zero 2w.


## Install instruction

### 1. Creating a venv

To install the package we need to create a venv which must also have access to the system packages

```shell
python -m venv --system-site-packages --symlinks picamera-env
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
