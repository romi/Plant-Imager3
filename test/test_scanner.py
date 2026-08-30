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
def scanner(monkeypatch):
    # Patch GPIO so a real PowerManager can be constructed safely.
    with patch("plantimager.controller.scanner.powermanager.gpio.setup"), \
         patch("plantimager.controller.scanner.powermanager.gpio.write"):
        yield Scanner()


def test_construction_owns_power_manager_and_falls_back_to_dummy_cnc(scanner):
    assert isinstance(scanner.cnc, DummyCNC)
    assert isinstance(scanner.power_manager, PowerManager)
    assert scanner.timelapse is None
    assert scanner.cnc_type == "DummyCNC"


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
    scanner.scan_id = "test_dataset"
    cam = MagicMock()
    cam.name = "cam1"
    scanner.cameras = [cam]
    return cam


def test_ready_to_scan_reflects_prerequisites(scanner):
    _make_ready_scanner(scanner)
    assert scanner.ready_to_scan is True
    scanner.scan_id = ""
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
    tl_id = scanner.start_timelapse(minimal_timelapse_config())
    assert tl_id.startswith("tl_")
    assert isinstance(scanner.timelapse, TimeLapse)
    assert scanner.timelapse.state == TimeLapseState.SCHEDULED
    # Second start rejected while a job is scheduled/running
    with pytest.raises(RuntimeError):
        scanner.start_timelapse(minimal_timelapse_config())


def test_cancel_timelapse_unlocks_for_new_start(scanner):
    scanner.start_timelapse(minimal_timelapse_config())
    finished = []
    scanner.timelapseFinished.connect(lambda: finished.append(True))
    scanner.cancel_timelapse()
    assert scanner.timelapse.state == TimeLapseState.CANCELLED
    assert finished == [True]
    # Terminal state unlocks a fresh start
    new_id = scanner.start_timelapse(minimal_timelapse_config())
    assert new_id.startswith("tl_")


def test_get_active_timelapse_returns_serialisable_dict(scanner):
    assert scanner.get_active_timelapse() is None
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
    tl_id = scanner.start_timelapse(minimal_timelapse_config())
    captured = []
    scanner.timelapseProgressChanged.connect(lambda c, t: captured.append((c, t)))
    tl = scanner.timelapse
    tl.progressChanged.emit(1, 3)
    assert captured == [(1, 3)]


def test_power_manager_cnc_ready_swaps_dummy_for_real(scanner, monkeypatch):
    real = MagicMock()
    real.__class__.__name__ = "CNC"
    scanner.power_manager.cnc_ready.emit(real)
    assert scanner.cnc is real
    assert scanner.cnc_type == "GRBL CNC"


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
