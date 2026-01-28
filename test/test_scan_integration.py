"""
Test the scanning process. Will spawn:
 - 2 dummy cameras from plantimager.commons.examples.cameraserver
    - The env variable PI3_CAMERASERVER_IMAGE must be the path to a dir containing images for the cameras
 - 1 PlantImagerApp from plantimager.controller.main
 - 1 plantdb empty instance

Will then connect to the PlantImagerApp with RPCController with plantimager.webui.controller_proxy.RPCController.


"""
import os
import signal
import sys
import subprocess
import time

import zmq
import tomllib
from plantimager.webui.controller_proxy import RPCController
from plantdb.client.plantdb_client import PlantDBClient


if __name__ == "__main__":

    camera_env = os.environ.copy()
    camera_env["PI3_CAMERASERVER_IMAGE"] = "/home/arthur/Documents/test_db_plantdb/tabac_20251013_1/images"
    cameras = [subprocess.Popen(
        [sys.executable, "-m", "plantimager.commons.examples.cameraserver"], env=camera_env
    ) for _ in range(2)]

    controller = subprocess.Popen(
        [sys.executable, "-m", "plantimager.controller.main"], env=os.environ
    )

    plantdb = subprocess.Popen(
        ["fsdb_rest_api", "--test", "--empty", "--host", "localhost", "--port", "5000"], env=os.environ
    )
    try:
        context = zmq.Context()
        print("--> Starting RPCController")
        rpc_controller = RPCController(context, "tcp://localhost:14567")
        print("<-- RPCController started")

        db_url = "http://localhost:5000"

        i = 0
        while len(rpc_controller.camera_names) < 2:
            print(rpc_controller.camera_names)
            time.sleep(0.5)
            i += 1
            if i > 120:
                raise TimeoutError("Cameras did not connect")


        db_client = PlantDBClient(db_url)
        db_client.login("admin", "admin")

        with open(os.path.join(os.path.dirname(__file__), "../src/webui/plantimager/webui/assets/config_scan.toml"), "r") as f:
            conf = tomllib.loads(f.read())

        conf["ScanPath"]["kwargs"]["n_points"] = 4
        n_images = len(rpc_controller.camera_names) * conf["ScanPath"]["kwargs"]["n_points"]

        for cam_name in rpc_controller.camera_names:
            conf[cam_name] = conf["picamera"].copy()

        rpc_controller.set_session_token(db_client.jwt_token)
        rpc_controller.set_db_url(db_url)
        rpc_controller.set_dataset_name("test_dataset")
        rpc_controller.set_config(conf)
        rpc_controller.run_scan()

        i = 0
        while rpc_controller.progress < rpc_controller.max_progress:
            time.sleep(1)
            i += 1
            if i > 120:
                raise TimeoutError("Scan too long")

        assert "test_dataset" in db_client.list_scans(), "Dataset `test_dataset` not found in db"
        assert "images" in db_client.list_scan_filesets("test_dataset")["filesets"], "Fileset `images` not found in db"
        assert len(db_client.list_fileset_files("test_dataset", "images")["files"]) == n_images, "No images captured"
        rpc_controller.stop_server()
        print("=======================")
        print("Test Successful !!!!!!!")
        print("=======================")
    finally:
        time.sleep(0.1)
        for cam in cameras:
            cam.send_signal(signal.SIGINT)
            try:
                cam.wait(timeout=5)
            except TimeoutError:
                cam.kill()

        plantdb.send_signal(signal.SIGINT)
        try:
            plantdb.wait(timeout=5)
        except TimeoutError:
            plantdb.kill()

        controller.send_signal(signal.SIGINT)
        try:
            controller.wait(timeout=5)
        except TimeoutError:
            controller.kill()





