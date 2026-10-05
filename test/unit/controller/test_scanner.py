#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the hollowed-out `Scanner` UI/RPC bridge.

`Scanner` no longer runs the scan loop; it owns the device state, a single
shared `PowerManager`, and the active `TimeLapse`. These tests pin the bridge
surface that QML and the RPC controller rely on.
"""

from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import QObject, Signal

from plantimager.controller.scanner.dummy_cnc import DummyCNC
from plantimager.controller.scanner.powermanager import PowerManager
from plantimager.controller.scanner.scanner import Scanner
from plantimager.controller.scanner.timelapse import TimeLapse, TimeLapseState
from plantimager.controller.scanner.timelapse_store import TimelapseStore


def minimal_timelapse_config(mode="interval", **overrides):
    base = {
        "ScanPath": {"class_name": "Circle", "kwargs": {"center_x": 0, "center_y": 0, "z": 10, "tilt": 0, "radius": 10, "n_points": 4}},
        "Metadata": {"object": {"species": "test"}, "hardware": {"model": "dummy"}},
        "timelapse": {
            "mode": mode,
            "warmup_period": 30,
            "grace_period": 120,
            "standby_threshold_sec": 600,
        },
    }
    if mode == "interval":
        base["timelapse"].update({"interval": "1h", "n_shots": 3})
    base["timelapse"].update(overrides)
    return base


@pytest.fixture
def scanner(monkeypatch, tmp_path):
    # Isolate XDG: persisting tests must not touch (or read) the real store —
    # a leaked SCHEDULED file would otherwise trigger resume on next boot.
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    # Patch GPIO so a real PowerManager can be constructed safely.
    with patch("plantimager.controller.scanner.powermanager.gpio.setup"), \
         patch("plantimager.controller.scanner.powermanager.gpio.write"):
        yield Scanner()


def test_construction_owns_power_manager_and_falls_back_to_dummy_cnc(scanner):
    # In AUTO, no CNC (mirrors real) — even with DummyCNC flag, creation is via dispatch on MANUAL/SCAN
    assert scanner.power_manager.get_cnc() is None
    assert isinstance(scanner.power_manager, PowerManager)
    assert scanner.timelapse is None
    assert scanner.cnc_type == "None"
    assert scanner.cnc_state in ("connecting", "disconnected", "standby")
    assert not hasattr(scanner, "cnc")


class _FakeScan(QObject):
    """Minimal stand-in for `Scan` with the signals the bridge connects to."""
    progressChanged = Signal(int)
    maxProgressChanged = Signal(int)

    def __init__(self):
        super().__init__()
        self.scanned = False

    def scan(self):
        self.scanned = True


def _make_ready_scanner(scanner):
    """Give the scanner everything required for a single scan."""
    scanner.config = minimal_timelapse_config()
    from plantimager.controller.scanner.path import Circle
    scanner.scan_path = Circle(center_x=0, center_y=0, z=10, tilt=0, radius=10, n_points=4)
    scanner.db_client = MagicMock()
    scanner.set_base_name("test_dataset")
    scanner.power_manager.cnc = DummyCNC()
    cam = MagicMock()
    cam.name = "cam1"
    scanner.cameras = [cam]
    return cam


def test_ready_to_scan_reflects_prerequisites(scanner):
    _make_ready_scanner(scanner)
    assert scanner.ready_to_scan is True
    scanner.set_base_name("")
    assert scanner.ready_to_scan is False


def test_camera_add_remove_updates_names(scanner):
    cam = MagicMock()
    cam.name = "cam1"
    scanner.add_camera(cam)
    assert scanner.camera_names == ["cam1"]
    scanner.remove_camera(cam)
    assert scanner.camera_names == []


def test_scan_validates_missing_prerequisites(scanner):
    # No config yet -> RuntimeError, not a crash
    with pytest.raises(RuntimeError):
        scanner.run_scan()


def test_run_scan_delegates_to_single_scan_and_bridges_progress(scanner, monkeypatch):
    _make_ready_scanner(scanner)
    fake_scan = _FakeScan()
    monkeypatch.setattr("plantimager.controller.scanner.scanner.Scan", lambda *a, **k: fake_scan)

    captured = []
    scanner.progressChanged.connect(lambda v: captured.append(("progress", v)))
    scanner.maxProgressChanged.connect(lambda v: captured.append(("max", v)))

    scanner.run_scan()
    assert fake_scan.scanned is True
    assert scanner.scan_in_progress is False  # reset after run

    # Forwarding the fake Scan's signals feeds the bridge
    fake_scan.progressChanged.emit(2)
    fake_scan.maxProgressChanged.emit(4)
    assert ("progress", 2) in captured
    assert ("max", 4) in captured


def test_start_timelapse_returns_id_and_sets_lock(scanner):
    scanner.set_base_name("myExp")
    # need dummy db_client for timelapse container creation
    scanner.db_client = MagicMock()
    tl_id = scanner.start_timelapse(minimal_timelapse_config())
    assert tl_id == "myExp"
    assert isinstance(scanner.timelapse, TimeLapse)
    assert scanner.timelapse.state == TimeLapseState.SCHEDULED
    # Second start rejected while a job is scheduled/running
    with pytest.raises(RuntimeError):
        scanner.start_timelapse(minimal_timelapse_config())


def test_cancel_timelapse_unlocks_for_new_start(scanner):
    scanner.set_base_name("myExp")
    scanner.db_client = MagicMock()
    scanner.start_timelapse(minimal_timelapse_config())
    finished = []
    scanner.timelapseFinished.connect(lambda: finished.append(True))
    scanner.cancel_timelapse()
    assert scanner.timelapse.state == TimeLapseState.CANCELLED
    assert finished == [True]
    # Terminal state unlocks a fresh start
    scanner.set_base_name("myExp2")
    new_id = scanner.start_timelapse(minimal_timelapse_config())
    assert new_id == "myExp2"


def test_get_active_timelapse_returns_serialisable_dict(scanner):
    assert scanner.get_active_timelapse() is None
    scanner.set_base_name("myExp")
    scanner.db_client = MagicMock()
    scanner.start_timelapse(minimal_timelapse_config())
    snap = scanner.get_active_timelapse()
    assert snap is not None
    for key in ("timelapse_id", "mode", "state", "schedule_times", "scans"):
        assert key in snap


def test_preview_timelapse_returns_schedule(scanner):
    preview = scanner.preview_timelapse(minimal_timelapse_config())
    assert preview["mode"] == "interval"
    assert preview["n_scans"] == 3
    assert len(preview["schedule_times"]) == 3


def test_timelapse_progress_forwarded(scanner):
    scanner.set_base_name("myExp")
    scanner.db_client = MagicMock()
    scanner.start_timelapse(minimal_timelapse_config())
    captured = []
    scanner.timelapseProgressChanged.connect(lambda c, t: captured.append((c, t)))
    tl = scanner.timelapse
    tl.progressChanged.emit(1, 3)
    assert captured == [(1, 3)]


def test_power_manager_cnc_ready_swaps_dummy_for_real(scanner, monkeypatch):
    real = MagicMock()
    real.__class__.__name__ = "CNC"
    scanner.power_manager.cnc = real
    scanner.power_manager.cnc_ready.emit(real)
    assert scanner.power_manager.get_cnc() is real
    assert scanner.cnc_type == "GRBL CNC"
    assert scanner.cnc_state == "ready"


# ----------------------------------------------------------------------
# RPC timelapse methods delegate through the Scanner-owned timelapse
# ----------------------------------------------------------------------
def _rpc_server_with(fake_scanner):
    from plantimager.controller.scanner.rpc_controller import RPCControllerServer
    server = object.__new__(RPCControllerServer)  # bypass zmq RPCServer.__init__
    server.scanner = fake_scanner
    return server


def test_rpc_timelapse_methods_delegate_to_scanner():
    from plantimager.controller.scanner.rpc_controller import RPCControllerServer

    fake = MagicMock()
    fake.start_timelapse.return_value = "tl_123"
    fake.get_active_timelapse.return_value = {"timelapse_id": "tl_123", "state": "SCHEDULED"}
    fake.preview_timelapse.return_value = {"n_scans": 2}

    server = _rpc_server_with(fake)
    assert server.start_timelapse({"timelapse": {}}) == "tl_123"
    fake.start_timelapse.assert_called_once_with({"timelapse": {}})
    assert server.get_active_timelapse()["timelapse_id"] == "tl_123"
    server.cancel_timelapse()
    fake.cancel_timelapse.assert_called_once()
    assert server.preview_timelapse({"timelapse": {}})["n_scans"] == 2
    fake.preview_timelapse.assert_called_once_with({"timelapse": {}})


# ----------------------------------------------------------------------
# CONFIGURED draft lifecycle — Scanner bridge
# ----------------------------------------------------------------------
def test_config_start_recompute_and_discard(scanner):
    scanner.set_base_name("cfgExp")
    scanner.db_client = MagicMock()
    cfg = minimal_timelapse_config(interval="30s", n_shots=5, warmup_period=10)
    snap = scanner.config_timelapse(cfg)
    assert snap["state"] == "configured"
    assert scanner.timelapse.state == TimeLapseState.CONFIGURED
    assert scanner.get_active_timelapse()["state"] == "configured"
    # not persisted yet — file may exist from previous but CONFIGURED itself is in-memory
    pre = list(scanner.timelapse.schedule_times)
    import time
    time.sleep(0.02)
    scanner.start_timelapse()
    assert scanner.timelapse.state == TimeLapseState.SCHEDULED
    assert scanner.timelapse.schedule_times[0] > pre[0]
    # scheduled locks second config
    with pytest.raises(RuntimeError):
        scanner.config_timelapse(cfg)
    with pytest.raises(RuntimeError):
        scanner.start_timelapse(cfg)
    # cancel scheduled → CANCELLED, then new draft allowed
    scanner.cancel_timelapse()
    assert scanner.timelapse.state == TimeLapseState.CANCELLED


def test_config_replace_and_cancel_discard(scanner):
    scanner.set_base_name("cfgExp")
    scanner.db_client = MagicMock()
    cfg1 = minimal_timelapse_config(interval="30s", n_shots=5, warmup_period=10)
    cfg2 = minimal_timelapse_config(interval="60s", n_shots=3, warmup_period=10)
    scanner.config_timelapse(cfg1)
    assert len(scanner.get_active_timelapse()["schedule_times"]) == 5
    scanner.config_timelapse(cfg2)
    assert len(scanner.get_active_timelapse()["schedule_times"]) == 3
    assert scanner.timelapse.state == TimeLapseState.CONFIGURED
    scanner.cancel_timelapse()
    assert scanner.timelapse is None
    assert scanner.get_active_timelapse() is None


def test_active_snapshot_strips_api_token(scanner):
    import json
    scanner.set_base_name("tokExp")
    scanner._api_token = "secret-token"
    scanner.config_timelapse(minimal_timelapse_config())
    snap = scanner.get_active_timelapse()
    assert "secret-token" not in json.dumps(snap)


def _resume_store(state="scheduled", next_idx=0, current_idx=0, on_scan_failed="skip_scan",
                  tmp_path=None, monkeypatch=None, slot_offset_s=3600):
    """Persist a store file as a previous process would have left it."""
    import datetime
    from datetime import timezone
    from plantimager.controller.scanner.timelapse_store import TimelapseStore, get_storage_dir
    now = datetime.datetime.now(timezone.utc)
    store = TimelapseStore(
        timelapse_id="resumeExp",
        mode="interval",
        state=state,
        schedule_times=[(now + datetime.timedelta(seconds=slot_offset_s + 60 * i)).isoformat() for i in range(2)],
        next_idx=next_idx,
        current_idx=current_idx,
        warmup_sec=45,
        standby_threshold_sec=600,
        grace_period=120,
        on_scan_failed=on_scan_failed,
        scan_retries=0,
        start_at=(now + datetime.timedelta(seconds=slot_offset_s)).isoformat(),
        scans=[],
        extra={
            "config_snapshot": {
                "ScanPath": {"class_name": "Circle", "kwargs": {"center_x": 0, "center_y": 0, "z": 10, "tilt": 0, "radius": 10, "n_points": 4}},
                "Metadata": {"object": {"species": "test"}},
                "timelapse": {"mode": "interval", "interval": 60, "n_shots": 2},
            },
            "db_url": "http://dummy",
            "api_token": "resume-token",
        },
    )
    store.save()
    return store


@pytest.fixture
def resume_env(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    with patch("plantimager.controller.scanner.powermanager.gpio.setup"), \
         patch("plantimager.controller.scanner.powermanager.gpio.write"), \
         patch("plantimager.controller.scanner.scanner.PlantDBClient") as mock_client:
        yield mock_client


def test_resume_rebuilds_scheduled_job(resume_env):
    _resume_store()
    scanner = Scanner()
    tl = scanner.timelapse
    assert tl is not None
    assert tl.id == "resumeExp"
    assert tl.next_idx == 0
    assert tl.state == TimeLapseState.SCHEDULED
    assert scanner.base_name == "resumeExp"
    assert scanner.db_client is resume_env.return_value
    # exclusivity holds for the resumed job
    with pytest.raises(RuntimeError):
        scanner.start_timelapse(minimal_timelapse_config())


def test_resume_stale_running_skip_advances(resume_env):
    _resume_store(state="running", next_idx=0, current_idx=0)
    scanner = Scanner()
    tl = scanner.timelapse
    assert tl is not None
    assert tl.next_idx == 1
    assert tl.state == TimeLapseState.SCHEDULED
    assert len(tl.scans) == 1
    assert tl.scans[0].status == "failed"
    assert tl.scans[0].scan_id == "resumeExp_0"


def test_resume_stale_running_fail_goes_terminal(resume_env, qtbot):
    _resume_store(state="running", next_idx=0, current_idx=0, on_scan_failed="fail_timelapse")
    scanner = Scanner()
    tl = scanner.timelapse
    assert tl is not None
    assert tl.state == TimeLapseState.FAILED
    assert tl.next_idx == 0
    assert tl.scans[0].status == "failed"


def test_resume_dead_auth_refuses(resume_env):
    resume_env.side_effect = ValueError("Invalid API token")
    _resume_store()
    scanner = Scanner()
    assert scanner.timelapse is None
    # scanner itself still usable for a fresh job
    scanner.set_base_name("fresh")
    assert scanner.base_name == "fresh"


def test_resume_terminal_boots_idle(resume_env):
    _resume_store(state="completed", next_idx=2)
    assert Scanner().timelapse is None


def test_resume_no_snapshot_refuses(resume_env):
    import datetime
    from datetime import timezone
    from plantimager.controller.scanner.timelapse_store import TimelapseStore
    now = datetime.datetime.now(timezone.utc)
    store = TimelapseStore(timelapse_id="old", mode="interval", state="scheduled",
                           schedule_times=[now.isoformat()], next_idx=0)
    store.save()
    assert Scanner().timelapse is None


def test_one_shot_bare_stays_bare(scanner):
    scanner.set_base_name("bareExp")
    scanner.db_client = MagicMock()
    scanner.db_client.create_timelapse = MagicMock()
    cfg = minimal_timelapse_config(mode="one_shot", warmup_period=10)
    # monkeypatch interval specifics
    cfg["timelapse"].pop("interval", None)
    cfg["timelapse"].pop("n_shots", None)
    scanner.config_timelapse(cfg)
    assert scanner.timelapse.plantdb_timelapse_id is None
    scanner.start_timelapse()
    assert scanner.timelapse.plantdb_timelapse_id is None
    assert not scanner.db_client.create_timelapse.called
    assert scanner.timelapse.state == TimeLapseState.SCHEDULED
    scanner.cancel_timelapse()


def test_fixed_times_not_recomputed_on_arm(scanner):
    scanner.set_base_name("fixedExp")
    scanner.db_client = MagicMock()
    import datetime
    from datetime import timezone as tz
    future = (datetime.datetime.now(tz.utc) + datetime.timedelta(hours=1)).isoformat()
    cfg = minimal_timelapse_config(mode="fixed_times", dates=[future])
    scanner.config_timelapse(cfg)
    pre = list(scanner.timelapse.schedule_times)
    scanner.start_timelapse()
    assert scanner.timelapse.schedule_times == pre
