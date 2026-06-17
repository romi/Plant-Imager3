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

# Helper to create a dummy Future that is already resolved
def resolved_future(result):
    f = Future()
    f.set_result(result)
    return f


class DummyPose:
    """Simple stand‑in for the real Pose class used in Scan."""
    def __init__(self, x=0, y=0, z=0, pan=0, tilt=0):
        self.x = x
        self.y = y
        self.z = z
        self.pan = pan
        self.tilt = tilt

    def attributes(self):
        return ["x", "y", "z", "pan", "tilt"]

    def __add__(self, other):
        # Simple vector addition used in Scan.scan()
        return DummyPose(
            self.x + other.x,
            self.y + other.y,
            self.z + other.z,
            self.pan + other.pan,
            self.tilt + other.tilt,
        )

    def __repr__(self):
        return f"Pose({self.x},{self.y},{self.z},{self.pan},{self.tilt})"


# ----------------------------------------------------------------------
# Unit tests for the Scan class
# ----------------------------------------------------------------------
class TestScanUnit(unittest.TestCase):

    def setUp(self):
        # ---- Mock CNC ---------------------------------------------------
        self.mock_cnc = MagicMock()
        # get_position will be used by Scan.get_position()
        self.mock_cnc.get_position.return_value = (10, 20, 30)  # x, y, pan

        # ---- Mock Camera ------------------------------------------------
        self.mock_camera = MagicMock()
        self.mock_camera.name = "cam1"
        # Simulate getImage returning a Future with (buffer, info)
        fake_buffer = b'\x89PNG\r\n\x1a\n...'  # placeholder binary image data
        fake_info = {"format": "png", "size": (640, 480)}
        self.mock_camera.getImage.return_value = resolved_future((fake_buffer, fake_info))

        # ---- Mock Path --------------------------------------------------
        # Path is an iterable of PathElement‑like objects.
        # We'll use a very small dummy path (2 points).
        class DummyPathElement:
            def __init__(self, x=None, y=None, z=None, pan=None, tilt=None):
                self.x = x
                self.y = y
                self.z = z
                self.pan = pan
                self.tilt = tilt

        self.mock_path = [
            DummyPathElement(x=100, y=100, pan=45),
            DummyPathElement(x=200, y=150, pan=90),
        ]

        # ---- Mock DataUploader (so no real DB calls happen) ----------
        self.mock_uploader = MagicMock(spec=DataUploader)

        # ---- Scan instance ------------------------------------------------
        # We patch the internal DataUploader creation to inject our mock
        patcher = patch('plantimager.controller.scanner.scan.DataUploader', return_value=self.mock_uploader)
        self.addCleanup(patcher.stop)
        self.mock_data_uploader_cls = patcher.start()

        # ---- Mock PlantDBClient (so no real DB calls happen) ----------
        from plantdb.client.plantdb_client import PlantDBClient
        self.mock_plantdb_client = MagicMock(spec=PlantDBClient)

        # We patch the imported PlantDBClient creation to inject our mock
        patcher = patch('plantimager.controller.scanner.scan.PlantDBClient', return_value=self.mock_plantdb_client)
        self.addCleanup(patcher.stop)
        self.mock_plantdb_client_cls = patcher.start()

        # Minimal config required by Scan
        self.config = {
            "Metadata": {
                "object": {"species": "testus plantus"},
                "hardware": {"model": "dummy"},
            },
            "cam1": {
                "offset": {"x": 0, "y": 0, "z": 0, "pan": 0, "tilt": 0},
                "resolution": "high",
                # any other camera‑specific params can be added here
            },
        }

        self.scan = Scan(
            cnc=self.mock_cnc,
            db_client=self.mock_plantdb_client_cls("https://dummy-db"),  # not used because uploader is mocked
            cameras=[self.mock_camera],
            path=self.mock_path,
            scan_id="test_scan_001",
            config=self.config,
        )

    # ------------------------------------------------------------------
    # Test get_position – converts CNC (x, y, pan) into a Pose
    # ------------------------------------------------------------------
    def test_get_position(self):
        pose = self.scan.get_position()
        self.assertEqual(pose.x, 10)
        self.assertEqual(pose.y, 20)
        self.assertEqual(pose.z, 0)      # always 0 in Scan.get_position()
        self.assertEqual(pose.pan, 30)   # CNC returns pan as third value
        self.assertEqual(pose.tilt, 0)   # always 0

    # ------------------------------------------------------------------
    # Test get_target_pose – respects None values and falls back to current pose
    # ------------------------------------------------------------------
    def test_get_target_pose(self):
        # current pose from mocked CNC (10,20,30)
        current = self.scan.get_position()

        # Path element overwrites only x and pan, leaves y untouched
        class PE:
            x = 999
            y = None
            z = None
            pan = 45
            tilt = None

        target = self.scan.get_target_pose(PE())
        self.assertEqual(target.x, 999)           # overridden
        self.assertEqual(target.y, current.y)     # fallback
        self.assertEqual(target.z, current.z)     # fallback (0)
        self.assertEqual(target.pan, 45)          # overridden
        self.assertEqual(target.tilt, current.tilt)

    # ------------------------------------------------------------------
    # Test set_position – ensures CNC.moveto is called with correct args
    # ------------------------------------------------------------------
    def test_set_position_calls_cnc(self):
        # Use a dummy Pose (the real Pose class is imported inside scan)
        from plantimager.controller.scanner.scan import Pose
        pose = Pose(1, 2, 0, pan=33, tilt=0)

        self.scan.set_position(pose)

        self.mock_cnc.moveto.assert_called_once_with(1, 2, 33)

    # ------------------------------------------------------------------
    # Test grab – image capture, metadata enrichment and uploader call
    # ------------------------------------------------------------------
    def test_grab_uploads_data(self):
        metadata = {"camera_name": "cam1", "extra": "info"}
        data_item = self.scan.grab(idx=7, metadata=metadata, camera=self.mock_camera)

        # Verify that camera.getImage was called
        self.mock_camera.getImage.assert_called_once_with(lores=False)

        # Verify that metadata now contains the buffer_info keys
        self.assertIn("format", metadata)
        self.assertIn("size", metadata)

        # Verify that uploader.upload was called with correct arguments
        self.mock_uploader.upload.assert_called_once()
        args, kwargs = self.mock_uploader.upload.call_args
        self.assertEqual(kwargs["scan_id"], "test_scan_001")   # scan_id
        self.assertEqual(kwargs["fileset"], "images")         # fileset
        self.assertIsInstance(kwargs["data"], type(data_item))  # DataItem instance

    # ------------------------------------------------------------------
    # Test scan – full workflow with mocked components
    # ------------------------------------------------------------------
    @patch('plantimager.controller.scanner.scan.PlantDBClient')
    def test_scan_full_workflow(self, mock_db_client_cls):
        # Mock the DB client that Scan creates internally

        # Run the scan method (this will use the mocked CNC, cameras, uploader)
        self.scan.scan()
        mock_db_client = self.scan.db_client

        # ---- Verify progress signals (max_progress should equal path length) ----
        self.assertEqual(self.scan._max_progress, len(self.mock_path))
        self.assertEqual(self.scan._progress, len(self.mock_path))

        # ---- Verify DB interactions ------------------------------------------------
        # create_scan and create_fileset should have been called once each
        mock_db_client.create_scan.assert_called_once_with(
            "test_scan_001", metadata=self.scan.config
        )
        mock_db_client.create_fileset.assert_called_once_with(
            self.scan.fileset, "test_scan_001"
        )
        # update_scan_metadata should be called at the end
        mock_db_client.update_scan_metadata.assert_called_once()
        # ----- Placeholder: you can retrieve the actual metadata sent to DB here ----
        # e.g. mock_db_client.update_scan_metadata.assert_called_with(
        #           "test_scan_001", {"stop_time": <expected iso‑string>})
        # -------------------------------------------------------------------------

        # ---- Verify that the uploader was asked to upload the right number of images ----
        # For each path point we have one camera, so total uploads = len(path)
        expected_upload_calls = len(self.mock_path)
        self.assertEqual(self.mock_uploader.upload.call_count, expected_upload_calls)

        # ---- Verify that CNC was moved to each target pose -------------------------
        # There should be as many moveto calls as path points
        self.assertEqual(self.mock_cnc.moveto.call_count, expected_upload_calls + 1)  # add return call

        # ---- Verify that after the scan the arm was moved to the final safe position
        # (the last moveto in Scan.scan() after the loop)
        self.assertTrue(
            any(call_args[0][0:3] == (20, 20, 45) for call_args in self.mock_cnc.moveto.call_args_list),
            "Final safety move (20,20,45) not performed"
        )

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
                "../src/webui/plantimager/webui/assets/config_scan.toml",
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