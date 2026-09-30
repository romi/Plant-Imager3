import gc
import os
import signal
import subprocess
import sys
import time
import tomllib
import unittest
from unittest.mock import MagicMock, patch, call
from concurrent.futures import Future

import objgraph
import zmq
from plantdb.client.plantdb_client import PlantDBClient

from plantimager.controller.camera.PiCameraComm import PiCameraComm, CameraStates
# Import the classes we want to test
from plantimager.controller.scanner.scan import Scan, DataUploader


class DummyCNC:
    """Very small stand‑in for a real CNC controller."""

    def __init__(self):
        # start at an arbitrary safe pose
        self._position = (0, 0, 0)  # x, y, pan

    def get_position(self):
        """Return the current (x, y, pan) tuple."""
        return self._position

    def moveto(self, x, y, pan):
        """Record a move – in a real CNC this would command the hardware."""
        self._position = (x, y, pan)


class TestScanIntegration(unittest.TestCase):
    """End‑to‑end test that exercises ``Scan.scan`` with real services."""

    def _log_pi_camera_refs(self):
        """Print reference‑graph information for any live PiCameraComm objects.

        This method is intended to be called **after** the test has attempted
        to clean up all cameras. The generated PNG files can be inspected with
        any image viewer or opened directly from a Jupyter notebook.
        """
        gc.collect()

        pi_camera_objs = [
            obj for obj in objgraph.get_leaking_objects()
            if isinstance(obj, PiCameraComm)
        ]
        print(f"[objgraph] {len(pi_camera_objs)} leaking PiCameraComm instance(s) remain.")

        # Find all PiCameraComm instances currently alive
        pi_camera_objs = [
            obj for obj in gc.get_objects()
            if isinstance(obj, PiCameraComm)
        ]

        if not pi_camera_objs:
            print("[objgraph] No PiCameraComm instances remain.")
            return

        print(f"[objgraph] {len(pi_camera_objs)} PiCameraComm instance(s) still alive.")


        for cam in pi_camera_objs:
            cam_id = id(cam)
            out_png = f"/tmp/pi_camera_backrefs_{cam_id}.png"
            print(f"[objgraph] Writing back‑reference graph for PiCameraComm id={cam_id} → {out_png}")

            # Generate a back‑reference graph (depth 5 is usually enough)
            objgraph.show_backrefs(
                cam,
                max_depth=10,
                too_many=10,
                extra_ignore=[id(locals())],
                filename=out_png,
                refcounts=True,
            )

    def setUp(self):
        # ---------- Configuration ----------
        from plantdb.commons.test_database import get_test_dataset
        self.images_path = os.getenv("PI3_CAMERASERVER_IMAGE")
        if self.images_path is None:
            dataset_path = get_test_dataset("real_plant")
            self.images_path = str(dataset_path / "images")

        self.db_port = 23657
        self.db_url = f"http://localhost:{self.db_port}"

        # ---------- Environment for camera servers ----------
        self.camera_env = os.environ.copy()
        self.camera_env["PI3_CAMERASERVER_IMAGE"] = self.images_path
        self.camera_env["PI3_CAMERASERVER_LAG"] = "100"   # ms

        # ---------- Spawn subprocesses ----------
        print("\n[SetUp] Starting dummy services...")
        self.cameras_proc = [
            subprocess.Popen(
                [sys.executable, "-m", "plantimager.commons.examples.cameraserver"],
                env=self.camera_env,
            )
            for _ in range(2)
        ]

        self.plantdb = subprocess.Popen(
            [
                "fsdb_rest_api",
                "--test",
                "--empty",
                "--host",
                "localhost",
                "--port",
                str(self.db_port),
            ],
            env=os.environ,
        )


        # Give the processes a moment to start up
        time.sleep(5)

        # ---------- RPC controller (to get remote camera objects) ----------
        from plantimager.commons.deviceregistry import DeviceRegistry
        from plantimager.controller.camera.PiCameraComm import PiCameraComm
        self.context = zmq.Context()

        self.cameras = []
        self.registry = DeviceRegistry(self.context)
        self.registry.start()

        while len([d_type for d_type, addr in self.registry.devices.values() if d_type == "camera"]) < 2:
            time.sleep(1)

        for name, (d_type, addr) in self.registry.devices.items():
            if d_type == "camera":
                self.cameras.append(
                    PiCameraComm(self.context, addr)
                )

        while any(c.state in [CameraStates.DISCONNECTED, CameraStates.INVALID] for c in self.cameras):
            time.sleep(0.5)



        # ---------- Load scanning configuration ----------
        config_path = os.path.abspath(
            os.path.join(
                os.path.dirname(__file__),
                "../../src/webui/plantimager/webui/assets/config_scan.toml",
            )
        )
        with open(config_path, "rb") as f:
            self.conf = tomllib.load(f)

        # Reduce the number of points to keep the test fast
        self.conf["ScanPath"]["kwargs"]["n_points"] = 2
        for camera in self.cameras:
            cam_name = camera.name
            self.conf[cam_name] = self.conf["picamera"].copy()

        # ---------- Create a tiny path ----------
        class PathElement:
            def __init__(self, x, y, pan):
                self.x = x
                self.y = y
                self.z = None
                self.pan = pan
                self.tilt = None

        self.test_path = [
            PathElement(10, 10, 0),
            PathElement(20, 20, 45),
        ]

        # ---------- Dummy CNC ----------
        self.dummy_cnc = DummyCNC()

        # ---------- Scan instance ----------
        self.db_client = PlantDBClient(self.db_url)
        self.db_client.login("admin", "admin")
        self.scan = Scan(
            cnc=self.dummy_cnc,
            db_client=self.db_client,
            cameras=self.cameras,
            path=self.test_path,
            scan_id="test_integration_scan",
            config=self.conf,
        )

    def tearDown(self):
        print("\n[TearDown] Stopping services...")
        del self.scan

        for camera in self.cameras:
            camera: PiCameraComm
            camera._camera.stop_server()
            del camera

        del self.cameras

        gc.collect()


        #self._log_pi_camera_refs()  # to debug lost objects

        for proc in self.cameras_proc:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass

        # Gracefully stop subprocesses
        for proc in self.cameras_proc + [self.plantdb]:
            if proc.poll() is None:
                proc.send_signal(signal.SIGINT)
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()

        self.registry.stop()
        self.registry.join()
        self.context.term()

    def test_full_scan(self):
        """Run the scan and verify that the DB contains the expected data."""
        # --- Run the scan -------------------------------------------------

        self.scan.scan()

        # --- Verify progress ------------------------------------------------
        self.assertEqual(self.scan._max_progress, len(self.test_path))
        self.assertEqual(self.scan._progress, len(self.test_path))

        # --- Verify database content -----------------------------------------
        from plantdb.client.plantdb_client import PlantDBClient
        db_client = PlantDBClient(self.db_url)
        db_client.login("admin", "admin")

        # Dataset should exist
        self.assertIn(
            "test_integration_scan",
            db_client.list_scans(),
            "Dataset not found in PlantDB",
        )

        # Fileset "images" should be present
        filesets = db_client.list_scan_filesets("test_integration_scan")
        self.assertIn(
            "images",
            filesets["filesets"],
            "`images` fileset missing",
        )

        # Number of uploaded images should equal number of path points (2)
        files = db_client.list_fileset_files("test_integration_scan", "images")
        expected = len(self.test_path) * len(self.cameras)
        self.assertEqual(
            len(files["files"]),
            expected,
            f"Expected {expected} images, got {len(files['files'])}",
        )

if __name__ == "__main__":
    unittest.main()