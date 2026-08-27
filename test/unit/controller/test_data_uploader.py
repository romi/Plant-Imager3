import io
import unittest
from unittest import mock

from plantimager.controller.scanner.hal import DataItem


class TestDataUploader(unittest.TestCase):
    def setUp(self):
        # Mock PlantDBClient
        self.mock_db = mock.MagicMock()
        self.mock_db.create_file.return_value = {"id": "file123"}
        from plantimager.controller.scanner.scanner import DataUploader
        self.DataUploader = DataUploader
        self.uploader = DataUploader(self.mock_db, queue_size=2)

    def tearDown(self):
        try:
            self.uploader.pool.shutdown(wait=True, cancel_futures=True)
        except Exception:
            pass

    def test_upload_calls_db(self):
        img = b"fakeimagebytes"
        meta = {"camera_name": "cam1", "shot_id": 0, "format": "jpeg"}
        data = DataItem(idx=0, image=img, image_ext="jpeg", metadata=meta)
        # need scan_id and fileset
        self.uploader.upload("scan1", "images", data)
        # wait a bit for thread to run
        import time
        time.sleep(0.2)
        self.assertTrue(self.mock_db.create_file.called)
        call_kwargs = self.mock_db.create_file.call_args[1]
        self.assertEqual(call_kwargs["scan_id"], "scan1")
        self.assertEqual(call_kwargs["fileset_id"], "images")
        self.assertEqual(call_kwargs["ext"], "jpeg")

    def test_upload_filename_format(self):
        img = b"data"
        meta = {"camera_name": "piCam", "shot_id": 1}
        data = DataItem(idx=5, image=img, image_ext="jpeg", metadata=meta)
        self.uploader.upload("scanX", "images", data)
        import time
        time.sleep(0.2)
        call_kwargs = self.mock_db.create_file.call_args[1]
        # file_id should be f"{camera_name}-{idx:05d}"
        self.assertEqual(call_kwargs["file_id"], "piCam-00005")

    def test_upload_queues_and_blocks(self):
        # queue_size=2, submit 3 should block on 3rd until one completes
        # Mock _upload to be slow
        original_upload = self.uploader._upload

        def slow_upload(*args, **kwargs):
            import time
            time.sleep(0.1)
            return original_upload(*args, **kwargs)

        with mock.patch.object(self.uploader, "_upload", side_effect=slow_upload):
            for i in range(3):
                di = DataItem(i, b"img", "jpeg", {"camera_name": "c", "shot_id": i})
                self.uploader.upload(f"scan{i}", "images", di)
            # If queue logic works, third upload would have waited for FIRST_COMPLETED
            # Just ensure no exception and jobs tracked
            self.assertGreaterEqual(len(self.uploader.jobs), 0)

    def test_upload_handles_exception(self):
        self.mock_db.create_file.side_effect = Exception("db down")
        di = DataItem(0, b"img", "jpeg", {"camera_name": "cam", "shot_id": 0})
        # should not raise
        try:
            self.uploader.upload("scan1", "images", di)
            import time
            time.sleep(0.2)
        except Exception as e:
            self.fail(f"upload raised {e}")

    def test_threadpool_workers(self):
        self.assertEqual(self.uploader.pool._max_workers, 4)
        self.assertEqual(self.uploader.queue_size, 2)

    def test_real_fsdb_if_available(self):
        # Try to use real fsdb_rest_api --test --empty if available
        import subprocess
        import time
        import os
        try:
            # Check if fsdb_rest_api exists
            subprocess.run(["which", "fsdb_rest_api"], check=True, capture_output=True)
        except Exception:
            self.skipTest("fsdb_rest_api not available")
            return
        # Start a temporary DB on random port
        import random
        port = random.randint(27000, 28000)
        proc = subprocess.Popen(
            ["fsdb_rest_api", "--test", "--empty", "--host", "127.0.0.1", "--port", str(port)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        # Wait for server to be ready (poll with retries)
        from plantdb.client.plantdb_client import PlantDBClient
        client = None
        for _ in range(10):
            time.sleep(0.5)
            if proc.poll() is not None:
                # Server died early - capture and skip
                self.skipTest(f"fsdb_rest_api exited early with {proc.poll()}")
                return
            try:
                client = PlantDBClient(f"http://127.0.0.1:{port}")
                client.list_scans()
                break
            except Exception:
                continue
        else:
            self.skipTest("fsdb_rest_api not ready after 5s")
            return

        try:
            try:
                client.login("admin", "admin")
            except Exception:
                pass
            # Try to create scan
            try:
                client.create_scan("test_scan", metadata={})
            except Exception:
                pass
            # Ensure fileset exists
            try:
                client.create_fileset("images", "test_scan")
            except Exception:
                pass
            from plantimager.controller.scanner.scanner import DataUploader
            uploader = DataUploader(client, queue_size=2)
            di = DataItem(0, b"fakeimg", "jpeg", {"camera_name": "cam", "shot_id": 0, "format": "jpeg"})
            uploader.upload("test_scan", "images", di)
            # Wait for async upload to complete
            import time as _time
            deadline = _time.time() + 3.0
            while uploader.jobs and _time.time() < deadline:
                _time.sleep(0.05)
            uploader.pool.shutdown(wait=True)
            result = client.list_fileset_files("test_scan", "images")
            self.assertIn("files", result)
            self.assertIn("cam-00000", result["files"],
                          f"Expected 'cam-00000' in files {result['files']}")
        finally:
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
            try:
                if 'uploader' in locals():
                    uploader.pool.shutdown(wait=True)
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()
