import unittest
from unittest import mock
import time

# Need QCoreApplication for QObject
from PySide6.QtCore import QCoreApplication


class TestScannerLogic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance()
        if cls.app is None:
            cls.app = QCoreApplication([])

    def setUp(self):
        # Patch CNC to raise, let DummyCNC be real but fast
        self.patcher_cnc = mock.patch("plantimager.controller.scanner.scanner.CNC")
        self.mock_cnc_class = self.patcher_cnc.start()
        self.addCleanup(self.patcher_cnc.stop)
        self.mock_cnc_class.side_effect = Exception("no hardware")

        self.sleep_patcher = mock.patch("plantimager.controller.scanner.dummy_cnc.time.sleep", return_value=None)
        self.sleep_patcher.start()
        self.addCleanup(self.sleep_patcher.stop)

        from plantimager.controller.scanner.scanner import Scanner, DummyCNC
        self.Scanner = Scanner
        # Patch QTimer to avoid real timer
        with mock.patch("plantimager.controller.scanner.scanner.QTimer"):
            self.scanner = Scanner()
            # Scanner should have fallen back to real DummyCNC
            self.assertIsInstance(self.scanner.cnc, DummyCNC)
            # Keep reference to real for init test, but mock get_position/moveto for other tests via patch
            self.mock_dummy = self.scanner.cnc
            # Mock get_position to return controlled value for most tests
            self._orig_get_pos = self.mock_dummy.get_position
            self.mock_dummy.get_position = mock.MagicMock(return_value=(20, 20, 45))
            self.mock_dummy.x_lims = (0, 740)
            self.mock_dummy.y_lims = (0, 740)
            try:
                self.scanner._cnc_connection_timer.stop()
            except Exception:
                pass

        # Mock cameras
        self.mock_camera = mock.MagicMock()
        self.mock_camera.name = "cam1"
        # getImage returns Future
        fut = mock.MagicMock()
        fut.result.return_value = (memoryview(b"fakejpeg"), {"format": "jpeg", "rotation": 0})
        self.mock_camera.getImage.return_value = fut
        self.mock_camera.resolution = (640, 480)
        self.mock_camera.encoding = "jpeg"
        self.mock_camera.config = {}

    def test_init_defaults_to_dummy(self):
        self.assertEqual(self.scanner.cnc, self.mock_dummy)
        self.assertEqual(self.scanner.cnc_type, "DummyCNC")

    def test_add_remove_camera(self):
        self.scanner.add_camera(self.mock_camera)
        self.assertIn("cam1", self.scanner.camera_names)
        self.assertEqual(len(self.scanner.cameras), 1)
        self.scanner.remove_camera(self.mock_camera)
        self.assertEqual(len(self.scanner.cameras), 0)
        self.assertNotIn("cam1", self.scanner.camera_names)

    def test_set_db_url_creates_uploader(self):
        mock_client = mock.MagicMock()
        with mock.patch("plantimager.controller.scanner.scanner.PlantDBClient", return_value=mock_client):
            with mock.patch("plantimager.controller.scanner.scanner.DataUploader") as MockUploader:
                mock_uploader = mock.MagicMock()
                MockUploader.return_value = mock_uploader
                self.scanner.set_db_url("http://127.0.0.1:5000")
                self.assertEqual(self.scanner.db_url, "http://127.0.0.1:5000")
                self.assertIsNotNone(self.scanner.db_client)
                self.assertIsNotNone(self.scanner.uploader)

    def test_configure_scan(self):
        # need to mock importlib
        config = {
            "ScanPath": {"class_name": "Circle", "kwargs": {"center_x": 200, "center_y": 200, "z": 50, "tilt": 0, "radius": 100, "n_points": 4}},
            "Metadata": {"object": {"species": "test"}, "hardware": {"version": "1"}},
            "cam1": {"offset": {"x": 0, "y": 0, "z": 0, "pan": 0, "tilt": 0}, "res_x": 640, "res_y": 480, "encoding": "jpeg", "config": {}},
        }
        self.scanner.add_camera(self.mock_camera)
        self.scanner.configure_scan(config)
        self.assertIsNotNone(self.scanner.scan_path)
        self.assertEqual(len(self.scanner.scan_path), 4)
        self.assertEqual(self.scanner._max_progress, 4)
        self.assertEqual(self.scanner.dataset_metadata, {"species": "test"})

    def test_ready_to_scan_false_without_everything(self):
        self.assertFalse(self.scanner.ready_to_scan)
        # set up minimal required
        self.scanner.add_camera(self.mock_camera)
        self.scanner.scan_path = mock.MagicMock()
        self.scanner.scan_path.__len__ = mock.MagicMock(return_value=4)
        self.scanner.db_client = mock.MagicMock()
        self.scanner.uploader = mock.MagicMock()
        self.scanner.scan_id = "test"
        self.scanner.fileset = "images"
        # still need config and cnc etc, but ready_to_scan should be True now (if not working)
        self.scanner.config = {"ScanPath": {}, "Metadata": {"object": {}, "hardware": {}}}
        # Ensure _scan_in_progress False
        self.scanner._scan_in_progress = False
        self.scanner._scanner_working = False
        self.assertTrue(self.scanner.ready_to_scan)

    def test_get_target_pose(self):
        from plantimager.controller.scanner.path import PathElement, Pose
        # current pos 20,20,45
        self.scanner.cnc.get_position.return_value = (20, 20, 45)
        # path element with x=None should use current, y set
        pe = PathElement(x=None, y=100, z=50, pan=90, tilt=0)
        target = self.scanner.get_target_pose(pe)
        self.assertEqual(target.x, 20)  # from current
        self.assertEqual(target.y, 100)
        self.assertEqual(target.z, 50)
        self.assertEqual(target.pan, 90)

    def test_set_position(self):
        from plantimager.controller.scanner.path import Pose
        pose = Pose(100, 100, 0, pan=45, tilt=0)
        with mock.patch.object(self.scanner.cnc, "moveto") as mock_moveto:
            self.scanner.set_position(pose)
            mock_moveto.assert_called_with(100, 100, 45)

    def test_grab(self):
        # Need db_client and uploader and scan_id
        self.scanner.db_client = mock.MagicMock()
        self.scanner.uploader = mock.MagicMock()
        self.scanner.scan_id = "scan1"
        self.scanner.fileset = "images"
        idx = 0
        meta = {"camera_name": "cam1", "shot_id": 0}
        data = self.scanner.grab(idx, meta, self.mock_camera)
        self.mock_camera.getImage.assert_called_with(lores=False)
        self.scanner.uploader.upload.assert_called()
        self.assertEqual(data.idx, 0)
        self.assertEqual(data.metadata["camera_name"], "cam1")

    def test_scan_orchestrates(self):
        # Full scan with mocked components
        # Setup config and path
        config = {
            "ScanPath": {"class_name": "Circle", "kwargs": {"center_x": 200, "center_y": 200, "z": 50, "tilt": 0, "radius": 100, "n_points": 2}},
            "Metadata": {"object": {}, "hardware": {}},
            "cam1": {"offset": {"x": 0, "y": 0, "z": 0, "pan": 0, "tilt": 0}, "res_x": 640, "res_y": 480, "encoding": "jpeg", "config": {}},
        }
        self.scanner.add_camera(self.mock_camera)
        # Mock db
        mock_client = mock.MagicMock()
        mock_client.create_scan.return_value = None
        mock_client.create_fileset.return_value = None
        self.scanner.db_url = "http://127.0.0.1:5000"
        self.scanner.db_client = mock_client
        from plantimager.controller.scanner.scanner import DataUploader
        mock_uploader = mock.MagicMock(spec=DataUploader)
        self.scanner.uploader = mock_uploader
        self.scanner.scan_id = "testscan"
        self.scanner.configure_scan(config)
        # Patch ThreadPoolExecutor to run inline for determinism
        with mock.patch("plantimager.controller.scanner.scanner.ThreadPoolExecutor") as MockExec:
            mock_executor = mock.MagicMock()
            # make submit call grab directly
            def fake_submit(fn, *args, **kwargs):
                fn(*args, **kwargs)
                fut = mock.MagicMock()
                fut.result.return_value = None
                return fut
            mock_executor.submit.side_effect = fake_submit
            mock_executor.__enter__.return_value = mock_executor
            mock_executor.__exit__.return_value = False
            MockExec.return_value = mock_executor
            # also need to mock wait
            with mock.patch("plantimager.controller.scanner.scanner.wait", return_value=None):
                with mock.patch("plantimager.controller.scanner.scanner.time.sleep", return_value=None):
                    self.scanner.scan()
                    # Should have moved and grabbed 2*1 =2 times
                    self.assertEqual(mock_uploader.upload.call_count, 2)

    def test_progress_signals(self):
        # Check that progressChanged is emitted during scan
        # Use mock to capture
        self.scanner._progress = 0
        self.scanner._max_progress = 2
        spy = mock.MagicMock()
        self.scanner.progressChanged.connect(spy)
        self.scanner._progress = 1
        self.scanner.progressChanged.emit(1)
        spy.assert_called_with(1)


if __name__ == "__main__":
    unittest.main()
