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
import unittest
import zmq
import tomllib

# Assuming these are available in your python path as per your project structure
from plantimager.webui.controller_proxy import RPCController
from plantdb.client.plantdb_client import PlantDBClient

class TestScanIntegration(unittest.TestCase):
    """
    Integration test for the scanning process.
    Spawns camera servers, controller, and database.
    """

    def setUp(self):
        # Configuration
        # You might want to point this to a generic test resource folder or use a temp dir generator
        self.images_path = os.environ.get(
            "PI3_CAMERASERVER_IMAGE",
            "/home/arthur/Documents/test_db_plantdb/tabac_20251013_1/images"
        )
        self.db_url = "http://localhost:5000"
        self.rpc_addr = "tcp://localhost:14567"

        # Prepare Environment
        self.camera_env = os.environ.copy()
        self.camera_env["PI3_CAMERASERVER_IMAGE"] = self.images_path

        # Start Processes
        print("\n[SetUp] Spawning subprocesses...")
        self.cameras = [subprocess.Popen(
            [sys.executable, "-m", "plantimager.commons.examples.cameraserver"],
            env=self.camera_env
        ) for _ in range(2)]

        self.controller = subprocess.Popen(
            [sys.executable, "-m", "plantimager.controller.main"],
            env=os.environ
        )

        self.plantdb = subprocess.Popen(
            ["fsdb_rest_api", "--test", "--empty", "--host", "localhost", "--port", "5000"],
            env=os.environ
        )

        # Wait for services to be ready
        time.sleep(5)

    def tearDown(self):
        print("\n[TearDown] Cleaning up subprocesses...")
        # Helper to safely kill a process
        def kill_proc(proc):
            if proc.poll() is None:
                proc.send_signal(signal.SIGINT)
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()

        for cam in self.cameras:
            kill_proc(cam)

        if hasattr(self, 'plantdb'):
            kill_proc(self.plantdb)

        if hasattr(self, 'controller'):
            kill_proc(self.controller)

    def test_full_scan_process(self):
        # 1. Connect RPC Controller
        context = zmq.Context()
        print("--> Starting RPCController")
        rpc_controller = RPCController(context, self.rpc_addr)
        print("<-- RPCController started")

        # 2. Wait for Cameras
        i = 0
        while len(rpc_controller.camera_names) < 2:
            print(f"Waiting for cameras... Found: {rpc_controller.camera_names}")
            time.sleep(0.5)
            i += 1
            if i > 120:
                self.fail("Timeout: Cameras did not connect within 60 seconds")

        # 3. Setup DB Client
        db_client = PlantDBClient(self.db_url)
        db_client.login("admin", "admin")

        # 4. Load Config
        # Adjust path resolution relative to this test file
        config_path = os.path.abspath(os.path.join(
            os.path.dirname(__file__),
            "../src/webui/plantimager/webui/assets/config_scan.toml"
        ))

        with open(config_path, "rb") as f:
            conf = tomllib.load(f)

        # 5. Configure Scan
        conf["ScanPath"]["kwargs"]["n_points"] = 4
        n_images = len(rpc_controller.camera_names) * conf["ScanPath"]["kwargs"]["n_points"]

        for cam_name in rpc_controller.camera_names:
            conf[cam_name] = conf["picamera"].copy()

        rpc_controller.set_session_token(db_client.jwt_token)
        rpc_controller.set_db_url(self.db_url)
        rpc_controller.set_dataset_name("test_dataset")
        rpc_controller.set_config(conf)

        # 6. Run Scan
        rpc_controller.run_scan()

        i = 0
        while rpc_controller.progress < rpc_controller.max_progress:
            time.sleep(1)
            i += 1
            if i > 120:
                self.fail("Timeout: Scan took too long")

        # 7. Assertions
        # Verify dataset exists
        self.assertIn(
            "test_dataset",
            db_client.list_scans(),
            "Dataset `test_dataset` not found in db"
        )

        # Verify filesets
        scan_filesets = db_client.list_scan_filesets("test_dataset")
        self.assertIn(
            "images",
            scan_filesets["filesets"],
            "Fileset `images` not found in db"
        )

        # Verify file count
        fileset_files = db_client.list_fileset_files("test_dataset", "images")
        self.assertEqual(
            len(fileset_files["files"]),
            n_images,
            f"Expected {n_images} images, found {len(fileset_files['files'])}"
        )

        rpc_controller.stop_server()
        print("Test Successful!")

if __name__ == "__main__":
    unittest.main()