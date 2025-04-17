# System Architecture

This document describes the architecture of the Plant-Imager3 system, including the communication between components and the overall application layout.

## Overview

The Plant-Imager3 system consists of several components that work together to provide a complete plant imaging solution:

1. A central PyQt application that serves as the main controller
2. A Raspberry Pi camera module that captures images
3. A web UI for configuring and running scans
4. A GRBL-based plant scanner that moves the camera
5. A remote PlantDB REST API that serves as a central database repository

These components communicate with each other using various protocols, primarily ZeroMQ (ZMQ) for RPC communications and HTTP for REST API interactions.

## ZMQ-based RPC Communications

The Plant-Imager3 system uses ZeroMQ (ZMQ) for Remote Procedure Call (RPC) communications between components.
This allows different parts of the system to call methods on other parts as if they were local, even though they may be running on different devices or in different processes.

### RPC Framework

The RPC framework is implemented in the `plantimager.commons.RPC` module and consists of several key classes:

#### RPCClient

The `RPCClient` class provides a client-side interface for making remote procedure calls.
It connects to an `RPCServer` and allows calling methods on the server as if they were local methods. It also handles property access and signal connections.

```python
from plantimager.commons.RPC import RPCClient
from plantimager.commons.cameradevice import Camera

@RPCClient.register_interface(Camera)
class PiCameraProxy(Camera, RPCClient):
    def __init__(self, context: zmq.Context, url: str):
        Camera.__init__(self)
        RPCClient.__init__(self, context, url)
```

#### RPCServer

The `RPCServer` class provides a server-side interface for exposing methods to remote clients.
It listens for requests from `RPCClient` instances and executes the requested methods.

```python
from plantimager.commons.RPC import RPCServer
from plantimager.commons.cameradevice import Camera

class PiCameraServer(Camera, RPCServer):
    def __init__(self, context: zmq.Context, url: str):
        Camera.__init__(self)
        RPCServer.__init__(self, context, url)
```

#### RPCSignal

The `RPCSignal` class provides a way to emit signals from the server to the client.
This is useful for notifying clients of events or changes in the server's state.

```python
from plantimager.commons.RPC import RPCSignal

class Camera:
    modeChanged = RPCSignal(str)
    videoUrlChanged = RPCSignal(str)
    rotationChanged = RPCSignal(int)
```

#### RPCProperty

The `RPCProperty` class provides a way to expose properties from the server to the client.
This allows clients to get and set properties on the server as if they were local properties.

```python
from plantimager.commons.RPC import RPCProperty, RPCSignal

class Camera:
    modeChanged = RPCSignal(str)
    
    @RPCProperty(notify=modeChanged)
    def mode(self):
        return self._mode
    
    @mode.setter
    def mode(self, value):
        self._mode = value
        self.modeChanged.emit(value)
```

### Communication Flow

The RPC communication flow typically follows these steps:

1. The server registers itself with a device registry, making it discoverable by clients
2. The client connects to the server using a URL provided by the device registry
3. The client calls methods on the server as if they were local methods
4. The server executes the methods and returns the results to the client
5. The server can emit signals that are received by the client
6. The client can get and set properties on the server

## Application Layout

### 1. Central PyQt Application

The central PyQt application (`src/controller/plantimager/controller/main.py`) serves as the main controller for the Plant-Imager3 system.
It provides a touchscreen interface for controlling the scanner and viewing images.

Key features:
- QML-based user interface
- Integration with the camera and scanner components
- Image processing and display
- Scan configuration and execution

```python
def main():
    app = QGuiApplication(sys.argv)
    font = QFont("Nunito Sans")
    app.setFont(font)
    QQuickStyle.setStyle("Material")
    engine = QQmlApplicationEngine()
    engine.addImageProvider("provider", imageProvider)
    engine.addImportPath(dirname(__file__))
    engine.loadFromModule("PlantImagerApp", "Main")

    if not engine.rootObjects():
        sys.exit(-1)

    ex = app.exec()
    sys.exit(ex)
```

### 2. Raspberry Pi Camera

The Raspberry Pi camera module (`src/picamera/plantimager/picamera`) captures images and provides video streaming.
It runs on a Raspberry Pi Zero W and communicates with the central controller using ZMQ-based RPC.

Key features:
- Image capture
- Video streaming
- Remote control via RPC
- Integration with the central controller

The camera component exposes its functionality through the `Camera` interface:

```python
class PiCameraComm(QObject):
    """
    Object that will handle communication with the picamera. Meant to live in a separate thread.
    """

    imageReady = Signal(memoryview, dict)
    modeChanged = Signal(str)
    videoUrlChanged = Signal(str)
    rotationChanged = Signal(int)

    def __init__(self, context: zmq.Context, url: str, parent: QObject = None):
        QObject.__init__(self, parent)
        self.camera = PiCameraProxy(context, url)
        # ...
```

### 3. Web UI

The Web UI (`src/webui/plantimager/webui`) provides a web-based interface for configuring and running scans.
It communicates with the central controller using ZMQ-based RPC and with the PlantDB REST API for data storage and retrieval.

Key features:
- Dash-based web application
- Bootstrap styling
- Scan configuration and execution
- Integration with the PlantDB REST API
- User authentication and account management

```python
def main() -> None:
    # - Parse the input arguments to variables:
    parser = parsing()
    args = parser.parse_args()

    # - Create connexion with controller
    context = zmq.Context()
    controller_thread = Thread(target=lambda ctx: RPCController(ctx, "tcp://localhost:14567"), args=(context,))
    controller_thread.daemon = True
    controller_thread.start()

    # - Start the Dash app:
    app = setup_web_app(args.host, args.port)
    app.run(debug=True, port=8000)
```

### 4. GRBL-based Plant Scanner

The GRBL-based plant scanner (`src/controller/plantimager/controller/scanner/grbl.py`) controls the movement of the camera during scanning.
It communicates with the central controller and provides precise positioning of the camera.

Key features:
- Serial communication with GRBL controller
- 3-axis (X, Y, Z) movement control
- Position tracking
- Homing and calibration
- Safety features

```python
class CNC(AbstractCNC):
    """A concrete implementation of CNC machine control using GRBL firmware.

    This class provides functionality to control a CNC machine running GRBL firmware
    over a serial connection. It supports movement along X, Y, and Z axes, homing,
    position queries, and both synchronous and asynchronous operations.
    """

    def __init__(self, port: str="/dev/ttyUSB0", baud_rate: int=115200):
        # ...

    def moveto(self, x: length_mm, y: length_mm, z: deg):
        """Move the CNC machine to specified coordinates and wait until the target position is reached."""
        # ...
```

### 5. Remote PlantDB REST API

The PlantDB REST API serves as a central database repository for the Plant-Imager3 system.
It stores scan data, metadata, and images, and provides a RESTful interface for accessing this data.

Key features:
- RESTful API for data access
- Storage of scan data and metadata
- User authentication and authorization
- Integration with the Web UI and central controller

The Web UI communicates with the PlantDB REST API to store and retrieve scan data:

```python
def get_dataset_list(host: str, port: int) -> list:
    """Returns the dataset dictionary for the PlantDB REST API at given host url and port."""
    try:
        response = requests.get(f"http://{host}:{port}/scans")
        if response.status_code == 200:
            return response.json()
        else:
            return []
    except requests.exceptions.RequestException:
        return []
```

## Communication Diagram

The following diagram illustrates the communication between the different components of the Plant-Imager3 system:

```
+----------------+       ZMQ RPC       +----------------+
|                |<------------------->|                |
|  Central PyQt  |                     |  Raspberry Pi  |
|  Application   |                     |    Camera      |
|                |                     |                |
+----------------+                     +----------------+
        ^
        |
        | ZMQ RPC
        |
        v
+----------------+       HTTP          +----------------+
|                |<------------------->|                |
|     Web UI     |                     |  PlantDB REST  |
|                |                     |      API       |
|                |                     |                |
+----------------+                     +----------------+
        ^
        |
        | ZMQ RPC
        |
        v
+----------------+
|                |
|  GRBL-based    |
| Plant Scanner  |
|                |
+----------------+
```

In this diagram:
- The central PyQt application communicates with the Raspberry Pi camera and the GRBL-based plant scanner using ZMQ RPC
- The Web UI communicates with the central PyQt application using ZMQ RPC
- The Web UI and the central PyQt application communicate with the PlantDB REST API using HTTP

## Conclusion

The Plant-Imager3 system uses a distributed architecture with multiple components that communicate using ZMQ-based RPC and HTTP.
This architecture provides flexibility, scalability, and modularity, allowing the system to be deployed on different devices and adapted to different use cases.