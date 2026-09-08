# Full-Stack Local Development Setup

This guide explains how to run the complete Plant-Imager3 stack **locally, for development**, so you can exercise the controller, dummy cameras, and plant database together.
It mirrors the setup performed by [`test/test_scan_integration.py`](../../test/test_scan_integration.py) and is the fastest way to drive the WebUI (or an `RPCController` client) against a realistic set of services.

## What runs

The local stack is made of four cooperating processes:

| Process       | Command                                               | Purpose                                                                                 |
|---------------|-------------------------------------------------------|-----------------------------------------------------------------------------------------|
| Dummy cameras | `python -m plantimager.commons.examples.cameraserver` | Simulate cameras; register with the device registry so the controller discovers them    |
| Controller    | `python -m plantimager.controller.main`               | Qt app that hosts the RPC server on `tcp://localhost:14567` and manages the scanner/CNC |
| PlantDB       | `fsdb_rest_api --test --empty ...`                    | Empty REST API for storing scan results                                                 |
| Client        | `RPCController("tcp://localhost:14567")`              | The WebUI, or your own script, driving the controller over RPC                          |

## Prerequisites

- The `plant-imager3` Conda environment (see [index.md](index.md#development-environment)) with:
  - `plantimager.commons`, `plantimager.controller`, `plantimager.picamera` installed in editable mode
  - `plantdb.server` installed (provides the `fsdb_rest_api` command)
- Mesa/OpenGL packages to run the Qt controller app (see [index.md](index.md#development-environment))
- A display for the Qt app, or run it headless with:
  ```shell
  export QT_QPA_PLATFORM=offscreen
  ```

## 1. Start the services

In separate terminals (or as background processes), run:

### Controller (Qt app)

It hosts the RPC server on `tcp://localhost:14567` and discovers cameras via the registry:

```shell
conda activate plant-imager3
python -m plantimager.controller.main
```

!!! Notes
    - The controller falls back to a `DummyCNC` automatically when no real CNC is reachable (`scanner.py`), so this stack runs entirely without physical hardware.

### Dummy cameras

It serves images from a directory.
You have to start at least one (the test uses two):
```shell
conda activate plant-imager3
# Optional: provide a directory of images via the PI3_CAMERASERVER_IMAGE environment variable
export PI3_CAMERASERVER_IMAGE=/path/to/a/dir/of/images
# Optional: simulate network latency between frames (milliseconds)
export PI3_CAMERASERVER_LAG=100
python -m plantimager.commons.examples.cameraserver
```

!!! Notes
    - The dummy camera server reads images from a directory and serves them in a loop.
    - Provide a directory of images via the `PI3_CAMERASERVER_IMAGE` environment variable.
    - If unset, the test falls back to the bundled `real_plant` test dataset.

### PlantDB REST API:

It hosts the database that receives images and metadata (_e.g._ from the controller) and serves them (_e.g._ to the WebUI):
```shell
conda activate plant-imager3
fsdb_rest_api --test --empty --host localhost --port 23656
```

Allow the services a few seconds to start up and register with each other.

## 2. Connect a client

You can now connect to the controller over RPC exactly as the WebUI does.
For example, a quick smoke test using the `plantimager.webui.controller_proxy.RPCController` proxy:

```python
import time
import zmq
from plantimager.webui.controller_proxy import RPCController

context = zmq.Context()
controller = RPCController(context, "tcp://localhost:14567")

# Wait for the dummy cameras to be discovered
while len(controller.camera_names) < 2:
    print(f"Waiting for cameras... found: {controller.camera_names}")
    time.sleep(0.5)

print(controller.camera_names)
print(controller.ready_to_scan)
```

## 3. Run a full scan

### WebUI

Use the demo WebUI to drive the controller and run a full scan:
```shell
conda activate plant-imager3
python -m plantimager.webui.main
```

### Python API

The following mirrors `test_full_scan_process` from `test_scan_integration.py`:

1. configure the scanner
2. point it at the database
3. run a scan

```python
import os
import time
import tomllib
import zmq
from plantdb.client.plantdb_client import PlantDBClient
from plantdb.commons.auth.models import Permission
from plantimager.webui.controller_proxy import RPCController

db_url = "http://localhost:23656"
rpc_addr = "tcp://localhost:14567"

# 1. Connect to the controller
context = zmq.Context()
controller = RPCController(context, rpc_addr)

# 2. Wait for the dummy cameras to be discovered
while len(controller.camera_names) < 2:
    print(f"Waiting for cameras... found: {controller.camera_names}")
    time.sleep(0.5)

# 3. Connect to the database and get an API token
db_client = PlantDBClient(db_url)
db_client.login("admin", "admin")
api_token = db_client.create_api_token(
    600,
    {"test_dataset": (Permission.WRITE, Permission.CREATE, Permission.READ)},
)

# 4. Load and prepare the scan configuration
config_path = os.path.abspath(os.path.join(
    "src/webui/plantimager/webui/assets/config_scan.toml",
))
with open(config_path, "rb") as f:
    conf = tomllib.load(f)

conf["ScanPath"]["kwargs"]["n_points"] = 4
for cam_name in controller.camera_names:
    conf[cam_name] = conf["picamera"].copy()

# 5. Configure the controller
controller.set_api_token(api_token)
controller.set_db_url(db_url)
controller.set_dataset_name("test_dataset")
controller.set_config(conf)

# 6. Run the scan and wait for completion
controller.run_scan()
while controller.progress < controller.max_progress:
    time.sleep(1)

# 7. Verify the results were stored
print("test_dataset" in db_client.list_scans())
print(db_client.list_scan_filesets("test_dataset"))
```

## Cleanup

Stop each process with `Ctrl+C` (SIGINT).
The controller and camera servers exit gracefully on `KeyboardInterrupt`.

## Related

- [`test_scan_integration.py`](../../test/test_scan_integration.py) — the integration test this guide is based on
- [RPC.md](RPC.md) — the ZeroMQ RPC framework used between controller and WebUI
- [architecture.md](architecture.md) — how the components communicate
