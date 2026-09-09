import datetime
from datetime import timezone
import pathlib
import time
import subprocess
import sys
import os
import signal

import pytest
import freezegun
from unittest.mock import MagicMock, patch

from plantimager.controller.scanner.timelapse_store import TimelapseStore, get_storage_dir
from plantimager.controller.scanner.timelapse import TimeLapse, TimeLapseState
from plantimager.controller.scanner.powermanager import PowerManager, PowerManagerMode


# ---------------------------------------------------------------------------
# helpers — reuse minimal_config from test_timelapse
# ---------------------------------------------------------------------------
def _minimal_config(mode="interval", **overrides):
    base = {
        "ScanPath": {"class_name": "Circle", "kwargs": {"center_x": 0, "center_y": 0, "z": 10, "tilt": 0, "radius": 10, "n_points": 4}},
        "Metadata": {"object": {"species": "test"}, "hardware": {"model": "dummy"}},
        "timelapse": {"mode": mode, "warmup_period": 5, "grace_period": 10, "standby_threshold_sec": 60},
    }
    if mode == "interval":
        base["timelapse"].update({"interval": 60, "n_shots": 3})
    if mode == "fixed_times":
        base["timelapse"].update({"dates": []})
    base["timelapse"].update(overrides)
    base["cam1"] = {"res_x": 640, "res_y": 480, "offset": {"x": 0, "y": 0, "z": 0, "pan": 0, "tilt": 0}}
    return base


@pytest.fixture
def tmp_xdg(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    return tmp_path


class FakeTimer:
    def __init__(self, parent=None, singleShot=False, interval=0):
        self.parent = parent
        self.singleShot = singleShot
        self._interval = interval
        self.timeout = MagicMock()
        self._connected = None
        self.timeout.connect = lambda fn: setattr(self, "_connected", fn)

        self._started = False

    def setInterval(self, ms): self._interval = ms
    def start(self): self._started = True
    def stop(self): self._started = False
    def isActive(self): return self._started
    def fire(self):
        if self._connected:
            self._connected()

    @staticmethod
    def singleShot(ms, fn):
        FakeTimer._last_singleShot = (ms, fn)

FakeTimer._last_singleShot = None


@pytest.fixture
def fake_timers(monkeypatch):
    monkeypatch.setattr("plantimager.controller.scanner.timelapse.QTimer", FakeTimer)
    monkeypatch.setattr("plantimager.controller.scanner.powermanager.QTimer", FakeTimer)
    # also patch singleShot
    monkeypatch.setattr("plantimager.controller.scanner.timelapse.QTimer.singleShot", lambda ms, fn: fn())
    return FakeTimer


# ---------------------------------------------------------------------------
# 1. Store roundtrip with real TimeLapse + PowerManager (no DB)
# ---------------------------------------------------------------------------
def test_store_roundtrip_with_real_timelapse(tmp_xdg, fake_timers):
    with patch("plantimager.controller.scanner.powermanager.gpio.setup"), \
         patch("plantimager.controller.scanner.powermanager.gpio.write"), \
         patch("plantimager.controller.scanner.timelapse.PlantDBClient"):
        from plantimager.controller.scanner.dummy_cnc import DummyCNC
        cfg = _minimal_config(mode="interval", interval=60, n_shots=2)
        pm = PowerManager(warmup_period=5)
        # mock path emission to avoid QML need
        with patch.object(TimeLapse, "_setup_next_scan_timer", lambda self: None):
            tl = TimeLapse(cnc=DummyCNC(), db_url="http://dummy", cameras=[], path=[], timelapse_name="tl-int", config=cfg, power_manager=pm)
        tl.schedule_times = [datetime.datetime.now(timezone.utc) + datetime.timedelta(seconds=60 * i) for i in range(2)]
        tl.next_idx = 1
        tl.state = TimeLapseState.SCHEDULED
        from plantimager.controller.scanner.timelapse_store import TimelapseStore
        store = TimelapseStore.from_timelapse(tl)
        store.save()
        loaded = TimelapseStore.new_store_from_last()
        assert loaded.timelapse_id == "tl-int"
        assert len(loaded.schedule_times) == 2
        assert loaded.next_idx == 1
        assert loaded.state == "scheduled"


# ---------------------------------------------------------------------------
# 2. Skip two missed then run third (freezegun + store)
# ---------------------------------------------------------------------------
def test_skip_two_missed_then_run(tmp_xdg, fake_timers):
    with patch("plantimager.controller.scanner.powermanager.gpio.setup"), \
         patch("plantimager.controller.scanner.powermanager.gpio.write"), \
         patch("plantimager.controller.scanner.timelapse.PlantDBClient"), \
         patch("plantimager.controller.scanner.timelapse.Scan") as MockScan:
        MockScan.return_value.scan.return_value = None
        MockScan.return_value._start_time = 0
        MockScan.return_value._stop_time = 1
        MockScan.return_value.status = "succeeded"
        MockScan.return_value.error = None
        MockScan.return_value.scan_id = "x"
        from plantimager.controller.scanner.dummy_cnc import DummyCNC
        cfg = _minimal_config(mode="interval", interval=3600, n_shots=3, grace_period=60)
        pm = PowerManager(warmup_period=5)
        with freezegun.freeze_time("2026-08-28 12:05:00+00:00"):
            tl = TimeLapse(cnc=DummyCNC(), db_url="http://dummy", cameras=[], path=[], timelapse_name="tl-skip", config=cfg, power_manager=pm)
            # overwrite auto-generated schedule with known times
            base = datetime.datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)
            tl.schedule_times = [base, base + datetime.timedelta(seconds=60), base + datetime.timedelta(minutes=10)]
            tl.next_idx = 0
            # first two are overdue beyond grace (300s and 240s ago), third is future (5min)
            tl._setup_next_scan_timer()
            assert tl.next_idx == 2
            # third timer armed, not yet executed
            assert tl._next_scan_timer.isActive()


# ---------------------------------------------------------------------------
# 3. Power AUTO vs SCAN
# ---------------------------------------------------------------------------
def test_power_auto_vs_scan(tmp_xdg, fake_timers):
    with patch("plantimager.controller.scanner.powermanager.gpio.setup"), \
         patch("plantimager.controller.scanner.powermanager.gpio.write"), \
         patch("plantimager.controller.scanner.timelapse.PlantDBClient"):
        from plantimager.controller.scanner.dummy_cnc import DummyCNC
        cfg_far = _minimal_config(mode="interval", interval=3600, n_shots=1, grace_period=10, standby_threshold_sec=60, warmup_period=5)
        pm = PowerManager(warmup_period=5)
        from freezegun import freeze_time
        with freeze_time("2026-08-28 12:00:00+00:00"):
            tl = TimeLapse(cnc=DummyCNC(), db_url="http://dummy", cameras=[], path=[], timelapse_name="tl-power", config=cfg_far, power_manager=pm)
            far = datetime.datetime.now(timezone.utc) + datetime.timedelta(seconds=3600)
            tl.schedule_times = [far]
            tl.next_idx = 0
            tl._setup_next_scan_timer()
            assert pm.mode == PowerManagerMode.AUTO
            assert pm.warmup_timer.isActive()

        # close → SCAN
        cfg_close = _minimal_config(mode="interval", interval=60, n_shots=1, grace_period=10, standby_threshold_sec=600, warmup_period=5)
        pm2 = PowerManager(warmup_period=5)
        with freeze_time("2026-08-28 12:00:00+00:00"):
            tl2 = TimeLapse(cnc=DummyCNC(), db_url="http://dummy", cameras=[], path=[], timelapse_name="tl-power2", config=cfg_close, power_manager=pm2)
            close = datetime.datetime.now(timezone.utc) + datetime.timedelta(seconds=100)
            tl2.schedule_times = [close]
            tl2.next_idx = 0
            tl2._setup_next_scan_timer()
            assert pm2.mode == PowerManagerMode.SCAN


# ---------------------------------------------------------------------------
# 4. Deterministic id + persist (via mocked Scan) — also checks FSDB-safe
# ---------------------------------------------------------------------------
def test_deterministic_id_and_persist(tmp_xdg, fake_timers):
    with patch("plantimager.controller.scanner.powermanager.gpio.setup"), \
         patch("plantimager.controller.scanner.powermanager.gpio.write"), \
         patch("plantimager.controller.scanner.timelapse.PlantDBClient"):
        def fake_scan_ctor(cnc, db_client, cameras, path, scan_id, config, parent=None):
            inst = MagicMock()
            inst.scan_id = scan_id
            inst.scan.return_value = None
            inst._start_time = datetime.datetime.now(timezone.utc).timestamp()
            inst._stop_time = inst._start_time + 1
            inst.status = "succeeded"
            inst.error = None
            return inst

        with patch("plantimager.controller.scanner.timelapse.Scan", side_effect=fake_scan_ctor) as MockScan:
            from plantimager.controller.scanner.dummy_cnc import DummyCNC
            cfg = _minimal_config(mode="interval", interval=60, n_shots=1, grace_period=120)
            pm = PowerManager(warmup_period=5)
            with patch.object(TimeLapse, "_setup_next_scan_timer", lambda self: None):
                tl = TimeLapse(cnc=DummyCNC(), db_url="http://dummy", cameras=[], path=[], timelapse_name="tl-id", config=cfg, power_manager=pm)
            sched = datetime.datetime(2025, 11, 24, 10, 0, 0, tzinfo=timezone.utc)
            tl.schedule_times = [sched]
            tl.next_idx = 0
            # make delta within grace so scan proceeds (now = sched + 5s)
            with freezegun.freeze_time(sched + datetime.timedelta(seconds=5)):
                tl.scan(0)
            # Scan ctor called with FSDB-safe id (positional arg 4)
            assert MockScan.call_args[0][4] == f"tl-id--{tl._slug_for_schedule(sched)}"
            assert ":" not in MockScan.call_args[0][4]
            # persisted store contains one ScanRecord
            store = TimelapseStore.new_store_from_last()
            assert len(store.scans) == 1
            assert store.scans[0]["scan_id"].startswith("tl-id--")


# ---------------------------------------------------------------------------
# 5. Resume after restart (new process simulation)
# ---------------------------------------------------------------------------
def test_resume_after_restart(tmp_xdg, fake_timers):
    with patch("plantimager.controller.scanner.powermanager.gpio.setup"), \
         patch("plantimager.controller.scanner.powermanager.gpio.write"), \
         patch("plantimager.controller.scanner.timelapse.PlantDBClient"), \
         patch("plantimager.controller.scanner.timelapse.Scan") as MockScan:
        MockScan.return_value.scan.return_value = None
        MockScan.return_value._start_time = 0
        MockScan.return_value._stop_time = 1
        MockScan.return_value.status = "succeeded"
        MockScan.return_value.error = None
        MockScan.return_value.scan_id = "x"
        from plantimager.controller.scanner.dummy_cnc import DummyCNC
        cfg = _minimal_config(mode="interval", interval=60, n_shots=3, grace_period=60)
        pm = PowerManager(warmup_period=5)
        with patch.object(TimeLapse, "_setup_next_scan_timer", lambda self: None):
            tl = TimeLapse(cnc=DummyCNC(), db_url="http://dummy", cameras=[], path=[], timelapse_name="tl-resume", config=cfg, power_manager=pm)
        base = datetime.datetime.now(timezone.utc)
        tl.schedule_times = [base + datetime.timedelta(seconds=60*i) for i in range(3)]
        tl.next_idx = 1
        tl.state = TimeLapseState.SCHEDULED
        # persist
        from plantimager.controller.scanner.timelapse_store import TimelapseStore
        TimelapseStore.from_timelapse(tl).save()
        # new process
        loaded = TimelapseStore.new_store_from_last()
        kwargs = loaded.to_timelapse_kwargs()
        assert kwargs["next_idx"] == 1
        assert len(kwargs["schedule_times"]) == 3


# ---------------------------------------------------------------------------
# 6. Live DB — opt-in, creates real scans in FSDB (one dataset per time)
# ---------------------------------------------------------------------------
@pytest.mark.live_db
def test_live_db_timelapse_creates_scans(tmp_xdg):
    # This test spawns a real FSDB REST API — heavy, only run with -m live_db
    # Mock hardware, live DB
    db_port = 23657
    db_url = f"http://localhost:{db_port}"
    plantdb_proc = subprocess.Popen(
        ["fsdb_rest_api", "--test", "--empty", "--host", "localhost", "--port", str(db_port)],
        env=os.environ,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    # wait for FSDB to be ready (poll)
    from plantdb.client.plantdb_client import PlantDBClient as _WaitClient
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            c = _WaitClient(db_url)
            try:
                c.login("admin", "admin")
            except Exception:
                pass
            c.list_scans()
            break
        except Exception:
            time.sleep(0.5)
    else:
        pytest.skip("FSDB not ready on port 23657")
    try:
        from plantdb.client.plantdb_client import PlantDBClient
        from plantimager.controller.scanner.dummy_cnc import DummyCNC
        from plantimager.controller.scanner.path import Circle

        # need gpio mock still? PowerManager will try gpio.setup — patch before import? we patch at runtime
        with patch("plantimager.controller.scanner.powermanager.gpio.setup"), \
             patch("plantimager.controller.scanner.powermanager.gpio.write"), \
             patch("plantimager.controller.scanner.timelapse.QTimer", FakeTimer), \
             patch("plantimager.controller.scanner.powermanager.QTimer", FakeTimer):
            # small fake camera
            mock_cam = MagicMock()
            mock_cam.name = "cam1"
            from concurrent.futures import Future
            f = Future(); f.set_result((b"fake", {"format": "jpg"}))
            mock_cam.getImage.return_value = f

            pm = PowerManager(warmup_period=1)
            # use INTERVAL n=2 with tiny interval for speed; center 370 is safely inside DummyCNC 0-740
            cfg = {
                "ScanPath": {"class_name": "Circle", "kwargs": {"center_x": 370, "center_y": 370, "z": 10, "tilt": 0, "radius": 10, "n_points": 2}},
                "Metadata": {"object": {"species": "live-test"}, "hardware": {"model": "dummy"}},
                "timelapse": {"mode": "interval", "interval": 2, "n_shots": 2, "warmup_period": 0, "grace_period": 60, "standby_threshold_sec": 600},
                "cam1": {"res_x": 640, "res_y": 480, "offset": {"x":0,"y":0,"z":0,"pan":0,"tilt":0}, "encoding": "jpg", "config": {}},
            }
            # create PlantDB client that will talk to live FSDB
            from plantdb.client.plantdb_client import PlantDBClient as RealClient
            # TimeLapse will create its own PlantDBClient internally; we also need one for assertions
            # Patch Timelapse to use real client? Let it create via db_url
            # create authenticated client and inject into TimeLapse
            from plantdb.commons.auth.models import Permission
            auth_client = RealClient(db_url)
            auth_client.login("admin", "admin")
            # ensure DB is ready
            for _ in range(10):
                try:
                    auth_client.list_scans()
                    break
                except Exception:
                    time.sleep(0.5)
            # use admin client directly (has full rights) — no restricted token needed for test
            tl = TimeLapse(cnc=DummyCNC(), db_url=db_url, cameras=[mock_cam], path=[], timelapse_name="tl-live", config=cfg, power_manager=pm)
            tl.db_client = auth_client  # admin session, can create any scan
            # override schedule to now+1s and now+3s to be fast
            now = datetime.datetime.now(timezone.utc)
            tl.schedule_times = [now + datetime.timedelta(seconds=1), now + datetime.timedelta(seconds=3)]
            tl.start_at = tl.schedule_times[0]
            tl.next_idx = 0
            tl.grace_period = 60
            # wait for both scans to fire
            tl._trigger_next_scan()
            tl._trigger_next_scan()
            # assert DB has two scans with deterministic ids
            client = auth_client
            scans = client.list_scans()
            # scans are prefixed with tl-live--
            live = [s for s in scans if s.startswith("tl-live--")]
            assert len(live) == 2
            # each has timelapse grouping via scan_id prefix; verify filesets exist
            for sid in live:
                fs = client.list_scan_filesets(sid)
                assert "images" in fs["filesets"] or "images" in str(fs)
    finally:
        if plantdb_proc.poll() is None:
            plantdb_proc.send_signal(signal.SIGINT)
            try:
                plantdb_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                plantdb_proc.kill()

