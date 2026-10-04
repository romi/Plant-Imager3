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
        self.assertEqual(self.mock_cnc.moveto.call_count, expected_upload_calls)

        # ---- Verify that after the scan the arm was parked via reset_pos ------
        # (Scan.scan() ends with cnc.reset_pos(), not a hardcoded moveto)
        self.mock_cnc.reset_pos.assert_called_once()

    # ------------------------------------------------------------------
    def test_hw_metadata_from_constant_without_config_hardware(self):
        from plantimager.controller.scanner.hardware_metadata import HARDWARE_METADATA
        config = {"Metadata": {"object": {"species": "testus plantus"}}}
        scan = Scan(
            cnc=self.mock_cnc,
            db_client=self.mock_plantdb_client,
            cameras=[self.mock_camera],
            path=self.mock_path,
            scan_id="no_hw_cfg",
            config=config,
        )
        self.assertEqual(scan.hw_metadata, HARDWARE_METADATA)

    def test_hw_metadata_constant_not_mutated(self):
        from plantimager.controller.scanner.hardware_metadata import HARDWARE_METADATA
        self.assertIsNot(self.scan.hw_metadata, HARDWARE_METADATA)
        self.scan.hw_metadata["name"] = "DummyCNC"
        self.assertNotEqual(HARDWARE_METADATA["name"], "DummyCNC")
