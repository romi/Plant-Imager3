# test_timelapse_store.py
import json
import os
import pathlib
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock

# The module under test
from plantimager.controller.scanner.timelapse_store import TimelapseStore, ScanRecord, TIMELAPSE_STORAGE_JSON
from plantimager.controller.scanner.timelapse import TimeLapseState, TimeLapseMode


class DummyTimeLapse:
    """Minimal stand‑in for the real TimeLapse class."""
    def __init__(self):
        self.id = "tl-123"
        self.mode = TimeLapseMode.FIXED_TIMES
        self._state = TimeLapseState.STANDBY
        self.schedule_times = [
            datetime(2023, 1, 1, 12, 0, tzinfo=timezone.utc),
            datetime(2023, 1, 1, 14, 0, tzinfo=timezone.utc),
        ]
        self.next_idx = 1
        self.current_idx = 0
        self.warmup_sec = 10
        self.standby_threshold_sec = 20
        self.grace_period = 5
        self.start_at = datetime(2023, 1, 1, 11, 30, tzinfo=timezone.utc)

        # Simulate a couple of finished scans
        class DummyScan:
            def __init__(self, scan_id, start_ts, stop_ts, status, error=None):
                self.scan_id = scan_id
                self._start_time = start_ts
                self._stop_time = stop_ts
                self.status = status
                self.error = error

        self.scans = [
            DummyScan(
                "scan-1",
                datetime(2023, 1, 1, 12, 0, tzinfo=timezone.utc).timestamp(),
                datetime(2023, 1, 1, 12, 5, tzinfo=timezone.utc).timestamp(),
                "succeeded",
            ),
            DummyScan(
                "scan-2",
                datetime(2023, 1, 1, 14, 0, tzinfo=timezone.utc).timestamp(),
                datetime(2023, 1, 1, 14, 2, tzinfo=timezone.utc).timestamp(),
                "failed",
                error={"msg": "something went wrong"},
            ),
        ]


class TimelapseStoreTest(unittest.TestCase):
    def setUp(self):
        # Create an isolated directory and point the store to it
        self.tmp_dir = tempfile.TemporaryDirectory(prefix="pi3_test_timelapse_store")
        self.addCleanup(self.tmp_dir.cleanup)

        self.patcher_xdg = mock.patch.dict(os.environ, {"XDG_DATA_HOME": self.tmp_dir.name})
        self.patcher_xdg.start()
        self.addCleanup(self.patcher_xdg.stop)

    def _store_path(self):
        return pathlib.Path(self.tmp_dir.name) / "plant-imager3-app" / "timelapse_storage.json"

    def test_save_and_load_cycle(self):
        """Store a value, write it to disk, reload and compare."""
        store = TimelapseStore(
            timelapse_id="abc",
            mode="auto",
            state="running",
            schedule_times=[
                "2023-01-01T12:00:00+00:00",
                "2023-01-01T14:00:00+00:00",
            ],
            next_idx=1,
            current_idx=0,
            warmup_sec=10,
            standby_threshold_sec=20,
            grace_period=5,
            start_at="2023-01-01T11:30:00+00:00",
            scans=[
                {"scan_id": "s1", "started_at": None, "finished_at": None, "status": "pending", "error": None}
            ],
            extra={"foo": "bar"},
        )

        # Save to the temporary location
        store.save()
        self.assertTrue(self._store_path().is_file(), "JSON file should exist after save()")

        # Load it back via the classmethod
        loaded = TimelapseStore.new_store_from_last()
        self.assertIsNotNone(loaded, "new_store_from_last should return an object when file exists")

        # Compare a few representative fields
        self.assertEqual(store.timelapse_id, loaded.timelapse_id)
        self.assertEqual(store.mode, loaded.mode)
        self.assertEqual(store.state, loaded.state)
        self.assertEqual(store.schedule_times, loaded.schedule_times)
        self.assertEqual(store.scans, loaded.scans)
        self.assertEqual(store.extra, loaded.extra)

        # Verify that the raw JSON contains the version key
        with self._store_path().open("r", encoding="utf-8") as f:
            raw = json.load(f)
        self.assertIn("version", raw)
        self.assertEqual(raw["version"], store.version)

    def test_from_timelapse_and_to_kwargs_roundtrip(self):
        """Serialize a dummy TimeLapse, then deserialize via to_timelapse_kwargs."""
        dummy = DummyTimeLapse()
        store = TimelapseStore.from_timelapse(dummy)

        # Basic sanity checks on the generated store
        self.assertEqual(store.timelapse_id, dummy.id)
        self.assertEqual(store.mode, dummy.mode.value)
        self.assertEqual(store.state, dummy._state.value)
        self.assertEqual(len(store.schedule_times), 2)
        self.assertEqual(store.next_idx, dummy.next_idx)
        self.assertEqual(store.current_idx, dummy.current_idx)

        # Ensure scans are stored as dicts with proper fields
        self.assertEqual(len(store.scans), 2)
        self.assertIn("scan_id", store.scans[0])
        self.assertIn("started_at", store.scans[0])

        # Convert back to kwargs and verify types
        kwargs = store.to_timelapse_kwargs()
        self.assertIsInstance(kwargs["schedule_times"][0], datetime)
        self.assertIsInstance(kwargs["start_at"], datetime)

        # The scans list should contain actual ScanRecord instances
        self.assertTrue(all(isinstance(s, ScanRecord) for s in kwargs["scans"]))

    def test_load_missing_file_returns_none(self):
        """When the JSON file does not exist, new_store_from_last should return None."""
        # Ensure the file truly does not exist
        path = self._store_path()
        if path.is_file():
            path.unlink()
        self.assertFalse(path.is_file())

        result = TimelapseStore.new_store_from_last()
        self.assertIsNone(result, "Expected None when no persisted file is present")

    def test_version_mismatch_is_handled_gracefully(self):
        """A stored version different from the class default should still load."""
        store = TimelapseStore(timelapse_id="ver-test")
        # Manually write a JSON with a mismatching version
        bad_json = store._as_serialisable_dict()
        bad_json["version"] = 999  # unrealistic future version
        self._store_path().parent.mkdir(exist_ok=True, parents=True)
        with open(self._store_path(), "w", encoding="utf-8") as f:
            json.dump(bad_json, f)

        # Loading must not raise; it should return an object with the stored version
        loaded = TimelapseStore.new_store_from_last()
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.version, 999)


if __name__ == "__main__":
    unittest.main()