import datetime
from datetime import timezone
import pathlib
import tempfile
import unittest.mock as mock

import pytest
import freezegun
from unittest.mock import MagicMock, patch, call

from PySide6.QtCore import QObject

from plantimager.controller.scanner.timelapse import (
    TimeLapse,
    TimeLapseMode,
    TimeLapseState,
    parse_duration,
)
from plantimager.controller.scanner.powermanager import PowerManagerMode


# ---------------------------------------------------------------------------
# Fake QTimer — synchronous, no event loop, records intervals
# ---------------------------------------------------------------------------
class FakeTimer:
    def __init__(self, parent=None, singleShot=False, interval=0):
        self.parent = parent
        self.singleShot = singleShot
        self._interval = interval
        self.timeout = MagicMock()
        # real code does: self.timeout.connect(callable)
        self._connected = None
        self.timeout.connect = lambda fn: setattr(self, "_connected", fn)
        self._started = False
        self._stopped = False

    def setInterval(self, ms: int):
        self._interval = ms

    def interval(self):
        return self._interval

    def start(self):
        self._started = True
        self._stopped = False

    def stop(self):
        self._stopped = True
        self._started = False

    def isActive(self):
        return self._started

    # helper for integration tests that want to fire
    def fire(self):
        if self._connected:
            self._connected()

    @staticmethod
    def singleShot(ms, fn):
        # do not auto-fire in unit tests; record for assertion
        FakeTimer._last_singleShot = (ms, fn)

FakeTimer._last_singleShot = None


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def minimal_config(mode="interval", **overrides):
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
    if mode == "fixed_times":
        base["timelapse"].update({"dates": []})
    base["timelapse"].update(overrides)
    base["cam1"] = {"res_x": 640, "res_y": 480, "offset": {"x": 0, "y": 0, "z": 0, "pan": 0, "tilt": 0}}
    return base


@pytest.fixture
def tmp_xdg(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    return tmp_path


@pytest.fixture
def mock_gpio():
    with patch("plantimager.controller.scanner.powermanager.gpio.setup"), \
         patch("plantimager.controller.scanner.powermanager.gpio.write"):
        yield


@pytest.fixture
def fake_timers(monkeypatch):
    # patch both places QTimer is used: timelapse and powermanager
    monkeypatch.setattr("plantimager.controller.scanner.timelapse.QTimer", FakeTimer)
    monkeypatch.setattr("plantimager.controller.scanner.powermanager.QTimer", FakeTimer)
    return FakeTimer


@pytest.fixture
def mock_scan_class(monkeypatch):
    m = MagicMock()
    # Scan instances returned by Scan(...) need a scan() method
    instance = MagicMock()
    instance.scan.return_value = None
    m.return_value = instance
    monkeypatch.setattr("plantimager.controller.scanner.timelapse.Scan", m)
    return m, instance


@pytest.fixture
def mock_plantdb(monkeypatch):
    m = MagicMock()
    monkeypatch.setattr("plantimager.controller.scanner.timelapse.PlantDBClient", m)
    return m


def make_timelapse(config, tmp_xdg, fake_timers, mock_scan_class, mock_plantdb, mock_gpio, cnc=None):
    # cnc: MagicMock or real DummyCNC — set on PowerManager before TimeLapse (mirrors exclusive factory)
    from plantimager.controller.scanner.dummy_cnc import DummyCNC
    from plantimager.controller.scanner.powermanager import PowerManager

    if cnc is None:
        cnc = DummyCNC()

    pm = PowerManager(warmup_period=config["timelapse"].get("warmup_period", 30))
    pm.cnc = cnc
    tl = TimeLapse(
        db_url="http://dummy",
        cameras=[],
        path=[],
        timelapse_name="tl-test",
        config=config,
        power_manager=pm,
    )
    # clean init side-effects for deterministic tests
    mock_scan_class[0].reset_mock()
    mock_scan_class[1].reset_mock()
    FakeTimer._last_singleShot = None
    # remove persisted file from init so later asserts check test's persist
    from plantimager.controller.scanner.timelapse_store import get_storage_dir
    p = get_storage_dir() / "timelapse_storage.json"
    if p.exists():
        p.unlink()
    return tl, pm


# ---------------------------------------------------------------------------
# parse_duration
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "inp,expected_days,expected_seconds",
    [
        ("2d-3h-1m-0s", 2, 10860),
        ("3h-20m", 0, 12000),
        ("45s", 0, 45),
        ("1d", 1, 0),
        ("2d-3h", 2, 10800),
    ],
)
def test_parse_duration_variants(inp, expected_days, expected_seconds):
    td = parse_duration(inp)
    assert td.days == expected_days
    assert td.seconds == expected_seconds


def test_parse_duration_invalid_raises():
    with pytest.raises(RuntimeError):
        parse_duration("invalid-string")




# ---------------------------------------------------------------------------
# _setup_timelapse_settings
# ---------------------------------------------------------------------------
def test_setup_interval_int_and_str_interval(fake_timers, tmp_xdg, mock_gpio, mock_scan_class, mock_plantdb):
    cfg = minimal_config(mode="interval", interval=3600, n_shots=2)
    tl, _ = make_timelapse(cfg, tmp_xdg, fake_timers, mock_scan_class, mock_plantdb, mock_gpio)
    assert len(tl.schedule_times) == 2
    assert (tl.schedule_times[1] - tl.schedule_times[0]).total_seconds() == 3600
    assert tl.schedule_times[0].tzinfo == timezone.utc

    cfg2 = minimal_config(mode="interval", interval="1h30m", n_shots=2)
    tl2, _ = make_timelapse(cfg2, tmp_xdg, fake_timers, mock_scan_class, mock_plantdb, mock_gpio)
    assert (tl2.schedule_times[1] - tl2.schedule_times[0]).total_seconds() == 5400


def test_setup_fixed_times_naive_is_local(fake_timers, tmp_xdg, mock_gpio, mock_scan_class, mock_plantdb):
    # naive dates → local tz → UTC, aware → UTC directly, sorted
    cfg = minimal_config(mode="fixed_times", dates=["2026-08-28T10:00:00", "2026-08-28T08:00:00+02:00"])
    # mock local tz to be +02:00 for determinism
    import datetime as dt
    real_now = dt.datetime.now

    class FakeNow(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            # when called as datetime.now().astimezone().tzinfo, return +02:00
            if tz is None:
                # called without tz for local_tz extraction: return aware with +02
                return dt.datetime(2026, 8, 28, 0, 0, tzinfo=dt.timezone(dt.timedelta(hours=2)))
            return real_now(tz)

    with patch("plantimager.controller.scanner.timelapse.datetime.datetime", FakeNow):
        tl, _ = make_timelapse(cfg, tmp_xdg, fake_timers, mock_scan_class, mock_plantdb, mock_gpio)
    # naive 10:00 local (+02) → 08:00 UTC, aware 08:00+02 → 06:00 UTC → sorted UTC
    assert tl.schedule_times[0].isoformat() == "2026-08-28T06:00:00+00:00"
    assert tl.schedule_times[1].isoformat() == "2026-08-28T08:00:00+00:00"


def test_setup_one_shot_dummy_adds_warmup(fake_timers, tmp_xdg, mock_gpio, mock_scan_class, mock_plantdb):
    from plantimager.controller.scanner.dummy_cnc import DummyCNC
    from freezegun import freeze_time
    cfg = minimal_config(mode="one_shot", warmup_period=60)
    with freeze_time("2026-08-28 12:00:00+00:00"):
        tl_dummy, _ = make_timelapse(cfg, tmp_xdg, fake_timers, mock_scan_class, mock_plantdb, mock_gpio, cnc=DummyCNC())
        assert (tl_dummy.schedule_times[0] - datetime.datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)).total_seconds() == pytest.approx(60)


# ---------------------------------------------------------------------------
# CNC-readiness gate (cold CNC: delay interval/one-shot, skip fixed-times)
# ---------------------------------------------------------------------------
def test_not_ready_interval_delays_by_warmup(fake_timers, tmp_xdg, mock_gpio, mock_scan_class, mock_plantdb):
    # construction auto-arms while PowerManager is still AUTO (cnc set, not connected):
    # no Scan dispatched, power armed (SCAN), timer set to one warm-up
    # (fixture warmup 30 clamps to the 45s minimum — see minimums tests below)
    cfg = minimal_config(mode="interval", interval=3600, n_shots=2, warmup_period=30)
    tl, pm = make_timelapse(cfg, tmp_xdg, fake_timers, mock_scan_class, mock_plantdb, mock_gpio)
    assert tl.warmup_sec == 45
    assert tl.next_idx == 0
    assert tl._next_scan_timer._interval == 45 * 1000
    assert pm.mode == PowerManagerMode.SCAN
    mock_scan_class[0].assert_not_called()


def test_warmup_and_standby_minimums_clamped(fake_timers, tmp_xdg, mock_gpio, mock_scan_class, mock_plantdb):
    cfg = minimal_config(mode="interval", warmup_period=10, standby_threshold_sec=60)
    tl, _ = make_timelapse(cfg, tmp_xdg, fake_timers, mock_scan_class, mock_plantdb, mock_gpio)
    assert tl.warmup_sec == 45
    assert tl.standby_threshold_sec == 2 * 45


def test_minimums_env_override(fake_timers, tmp_xdg, mock_gpio, mock_scan_class, mock_plantdb, monkeypatch):
    monkeypatch.setattr("plantimager.controller.scanner.timelapse.MIN_WARMUP_SEC", 5)
    cfg = minimal_config(mode="interval", warmup_period=30, standby_threshold_sec=600)
    tl, _ = make_timelapse(cfg, tmp_xdg, fake_timers, mock_scan_class, mock_plantdb, mock_gpio)
    assert tl.warmup_sec == 30
    assert tl.standby_threshold_sec == 600


def test_not_ready_fixed_times_skips(fake_timers, tmp_xdg, mock_gpio, mock_scan_class, mock_plantdb):
    now = datetime.datetime.now(timezone.utc).isoformat()
    cfg = minimal_config(mode="fixed_times", dates=[now])
    tl, _ = make_timelapse(cfg, tmp_xdg, fake_timers, mock_scan_class, mock_plantdb, mock_gpio)
    assert tl.next_idx == 1
    assert tl.state == TimeLapseState.COMPLETED
    mock_scan_class[0].assert_not_called()


def test_ready_immediate_dispatch_unchanged(fake_timers, tmp_xdg, mock_gpio, mock_scan_class, mock_plantdb):
    cfg = minimal_config(mode="interval", interval=3600, n_shots=2)
    tl, pm = make_timelapse(cfg, tmp_xdg, fake_timers, mock_scan_class, mock_plantdb, mock_gpio)
    assert pm.try_set_mode(PowerManagerMode.SCAN) is True
    tl.schedule_times = [datetime.datetime.now(timezone.utc)]
    tl.next_idx = 0
    tl._setup_next_scan_timer()
    assert tl._next_scan_timer._interval == 0
    assert tl._next_scan_timer._started is True


def test_scan_defers_when_cnc_not_ready(fake_timers, tmp_xdg, mock_gpio, mock_scan_class, mock_plantdb):
    cfg = minimal_config(mode="interval", interval=60, n_shots=2)
    tl, pm = make_timelapse(cfg, tmp_xdg, fake_timers, mock_scan_class, mock_plantdb, mock_gpio)
    pm.cnc = None
    assert pm.try_set_mode(PowerManagerMode.AUTO) is True
    tl.schedule_times = [datetime.datetime.now(timezone.utc)]
    tl.next_idx = 0
    tl._setup_next_scan_timer = MagicMock()
    tl.scan(0)
    tl._setup_next_scan_timer.assert_called_once()
    mock_scan_class[0].assert_not_called()


def test_later_slot_not_ready_fails_fast(fake_timers, tmp_xdg, mock_gpio, mock_scan_class, mock_plantdb):
    cfg = minimal_config(mode="interval", interval=60, n_shots=2)
    tl, pm = make_timelapse(cfg, tmp_xdg, fake_timers, mock_scan_class, mock_plantdb, mock_gpio)
    pm.cnc = None
    assert pm.try_set_mode(PowerManagerMode.AUTO) is True
    now = datetime.datetime.now(timezone.utc)
    tl.schedule_times = [now - datetime.timedelta(seconds=60), now]
    tl.next_idx = 1
    finished, errors = MagicMock(), MagicMock()
    tl.scanFinished.connect(finished)
    tl.errorOccurred.connect(errors)
    tl._setup_next_scan_timer()
    assert tl.state == TimeLapseState.FAILED
    assert tl.next_idx == 1
    assert tl._next_scan_timer._stopped is True
    finished.assert_called_once()
    errors.assert_called_once()
    assert "standby_threshold_sec" in errors.call_args[0][0]
    mock_scan_class[0].assert_not_called()


def test_scan_later_slot_not_ready_fails_fast(fake_timers, tmp_xdg, mock_gpio, mock_scan_class, mock_plantdb):
    cfg = minimal_config(mode="interval", interval=60, n_shots=2)
    tl, pm = make_timelapse(cfg, tmp_xdg, fake_timers, mock_scan_class, mock_plantdb, mock_gpio)
    pm.cnc = None
    assert pm.try_set_mode(PowerManagerMode.AUTO) is True
    now = datetime.datetime.now(timezone.utc)
    tl.schedule_times = [now - datetime.timedelta(seconds=60), now]
    tl.next_idx = 1
    tl.scan(1)
    assert tl.state == TimeLapseState.FAILED
    assert tl.next_idx == 1
    mock_scan_class[0].assert_not_called()


def test_setup_failure_policy_defaults(fake_timers, tmp_xdg, mock_gpio, mock_scan_class, mock_plantdb):
    tl, _ = make_timelapse(minimal_config(), tmp_xdg, fake_timers, mock_scan_class, mock_plantdb, mock_gpio)
    assert tl.on_scan_failed == "skip_scan"
    assert tl.scan_retries == 0


def test_setup_failure_policy_explicit(fake_timers, tmp_xdg, mock_gpio, mock_scan_class, mock_plantdb):
    cfg = minimal_config(on_scan_failed="fail_timelapse", scan_retries=2)
    tl, _ = make_timelapse(cfg, tmp_xdg, fake_timers, mock_scan_class, mock_plantdb, mock_gpio)
    assert tl.on_scan_failed == "fail_timelapse"
    assert tl.scan_retries == 2


def test_setup_failure_policy_invalid_raises(fake_timers, tmp_xdg, mock_gpio, mock_scan_class, mock_plantdb):
    with pytest.raises(ValueError):
        make_timelapse(minimal_config(on_scan_failed="retry-forever"), tmp_xdg, fake_timers, mock_scan_class, mock_plantdb, mock_gpio)


def test_setup_failure_policy_negative_retries_raises(fake_timers, tmp_xdg, mock_gpio, mock_scan_class, mock_plantdb):
    with pytest.raises(ValueError):
        make_timelapse(minimal_config(scan_retries=-1), tmp_xdg, fake_timers, mock_scan_class, mock_plantdb, mock_gpio)


# ---------------------------------------------------------------------------
# scan() validation, early re-arm, skip, success/failure, deterministic id
# ---------------------------------------------------------------------------
def test_scan_rejects_invalid_index(fake_timers, tmp_xdg, mock_gpio, mock_scan_class, mock_plantdb):
    cfg = minimal_config(mode="interval", interval=60, n_shots=2)
    tl, _ = make_timelapse(cfg, tmp_xdg, fake_timers, mock_scan_class, mock_plantdb, mock_gpio)
    with pytest.raises(ValueError):
        tl.scan(999)


def test_scan_early_re_arms_timer(fake_timers, tmp_xdg, mock_gpio, mock_scan_class, mock_plantdb):
    cfg = minimal_config(mode="interval", interval=3600, n_shots=2, grace_period=120)
    tl, _ = make_timelapse(cfg, tmp_xdg, fake_timers, mock_scan_class, mock_plantdb, mock_gpio)
    # force next scheduled far in future
    future = datetime.datetime.now(timezone.utc) + datetime.timedelta(seconds=10000)
    tl.schedule_times = [future, future + datetime.timedelta(seconds=3600)]
    tl.next_idx = 0
    tl._setup_next_scan_timer = MagicMock()
    tl.scan(0)
    tl._setup_next_scan_timer.assert_called_once()
    # no Scan created
    mock_scan_class[0].assert_not_called()


def test_scan_missed_is_skipped_and_persisted(fake_timers, tmp_xdg, mock_gpio, mock_scan_class, mock_plantdb):
    cfg = minimal_config(mode="interval", interval=60, n_shots=2, grace_period=120)
    tl, pm = make_timelapse(cfg, tmp_xdg, fake_timers, mock_scan_class, mock_plantdb, mock_gpio)
    past = datetime.datetime.now(timezone.utc) - datetime.timedelta(seconds=500)  # beyond grace 120
    tl.schedule_times = [past, past + datetime.timedelta(seconds=60)]
    tl.next_idx = 0
    tl.scan(0)
    mock_scan_class[0].assert_not_called()
    # persisted (file exists)
    from plantimager.controller.scanner.timelapse_store import get_storage_dir
    assert (get_storage_dir() / "timelapse_storage.json").exists()


def test_scan_success_transitions_and_deterministic_id(fake_timers, tmp_xdg, mock_gpio, mock_plantdb):
    # use real Scan mock but check id — n=1 is bare (no container), n>1 is indexed
    scan_instances = []

    def fake_scan_ctor(cnc, db_client, cameras, path, scan_id, config, parent=None, **kwargs):
        inst = MagicMock()
        inst.scan_id = scan_id
        inst.timelapse_id = kwargs.get("timelapse_id")
        inst.scan = MagicMock()
        inst._start_time = datetime.datetime.now(timezone.utc).timestamp()
        inst._stop_time = inst._start_time + 5
        inst.status = "succeeded"
        inst.error = None
        scan_instances.append((scan_id, inst, kwargs))
        return inst

    with patch("plantimager.controller.scanner.timelapse.Scan", side_effect=fake_scan_ctor):
        # n=1 → bare scan (no timelapse container)
        cfg = minimal_config(mode="interval", interval=60, n_shots=1, grace_period=120)
        from plantimager.controller.scanner.powermanager import PowerManager
        from plantimager.controller.scanner.dummy_cnc import DummyCNC
        pm = PowerManager(warmup_period=30)
        pm.cnc = DummyCNC()
        tl = TimeLapse(db_url="http://dummy", cameras=[], path=[], timelapse_name="tl-xyz", config=cfg, power_manager=pm)
        now = datetime.datetime.now(timezone.utc)
        tl.schedule_times = [now - datetime.timedelta(seconds=10)]
        tl.next_idx = 0
        tl.state = TimeLapseState.SCHEDULED
        assert tl.plantdb_timelapse_id is None
        tl.scan(0)
        assert scan_instances[0][0] == "tl-xyz"  # bare, no slug
        assert ":" not in scan_instances[0][0]
        assert scan_instances[0][2].get("timelapse_id") is None
        assert tl.state == TimeLapseState.SCHEDULED
        assert len(tl.scans) == 1

        # n=3 → indexed scans under container
        scan_instances.clear()
        cfg2 = minimal_config(mode="interval", interval=60, n_shots=3, grace_period=120)
        pm.cnc = DummyCNC()
        tl2 = TimeLapse(db_url="http://dummy", cameras=[], path=[], timelapse_name="tl-abc", config=cfg2, power_manager=pm)
        assert tl2.plantdb_timelapse_id == "tl-abc"
        tl2.schedule_times = [now - datetime.timedelta(seconds=10) + datetime.timedelta(seconds=i*60) for i in range(3)]
        tl2.next_idx = 0
        tl2.state = TimeLapseState.SCHEDULED
        tl2.scan(0)
        assert scan_instances[0][0] == "tl-abc_0"
        assert scan_instances[0][2].get("timelapse_id") == "tl-abc"
        assert scan_instances[0][2].get("timelapse_index") == 0
        tl2.next_idx = 1
        tl2.scan(1)
        assert scan_instances[1][0] == "tl-abc_1"


def test_scan_failure_goes_failed_and_emits(fake_timers, tmp_xdg, mock_gpio, mock_plantdb, qtbot):
    def fail_ctor(*a, **kw):
        inst = MagicMock()
        inst.scan.side_effect = RuntimeError("boom")
        inst.scan_id = kw.get("scan_id", "x")
        inst._start_time = None
        inst._stop_time = None
        inst.status = "failed"
        inst.error = {"msg": "boom"}
        return inst

    with patch("plantimager.controller.scanner.timelapse.Scan", side_effect=fail_ctor):
        cfg = minimal_config(mode="interval", interval=60, n_shots=1, grace_period=120)
        from plantimager.controller.scanner.powermanager import PowerManager
        from plantimager.controller.scanner.dummy_cnc import DummyCNC
        pm = PowerManager(warmup_period=30)
        pm.cnc = DummyCNC()
        tl = TimeLapse(db_url="http://dummy", cameras=[], path=[], timelapse_name="tl-fail", config=cfg, power_manager=pm)
        tl.schedule_times = [datetime.datetime.now(timezone.utc) - datetime.timedelta(seconds=5)]
        tl.next_idx = 0
        tl.state = TimeLapseState.SCHEDULED
        with qtbot.waitSignal(tl.errorOccurred, timeout=1000) as blocker:
            with pytest.raises(RuntimeError):
                tl.scan(0)
            assert "boom" in blocker.args[0]
        assert tl.state == TimeLapseState.FAILED


# ---------------------------------------------------------------------------
# _setup_next_scan_timer branches
# ---------------------------------------------------------------------------
def test_setup_next_scan_timer_skip_recursion(fake_timers, tmp_xdg, mock_gpio, mock_scan_class, mock_plantdb):
    cfg = minimal_config(mode="interval", interval=60, n_shots=3, grace_period=60)
    tl, _ = make_timelapse(cfg, tmp_xdg, fake_timers, mock_scan_class, mock_plantdb, mock_gpio)
    now = datetime.datetime.now(timezone.utc)
    # first two overdue
    tl.schedule_times = [now - datetime.timedelta(seconds=200), now - datetime.timedelta(seconds=150), now + datetime.timedelta(seconds=3600)]
    tl.next_idx = 0
    tl._setup_next_scan_timer()
    assert tl.next_idx == 2  # skipped 2
    assert tl.state == TimeLapseState.SCHEDULED
    assert tl._next_scan_timer.isActive()


def test_setup_next_scan_timer_immediate_singleshot(fake_timers, tmp_xdg, mock_gpio, mock_scan_class, mock_plantdb):
    cfg = minimal_config(mode="interval", interval=60, n_shots=2, grace_period=120, standby_threshold_sec=600)
    tl, _ = make_timelapse(cfg, tmp_xdg, fake_timers, mock_scan_class, mock_plantdb, mock_gpio)
    now = datetime.datetime.now(timezone.utc)
    tl.schedule_times = [now + datetime.timedelta(seconds=30)]  # within grace 120
    tl.next_idx = 0
    tl._setup_next_scan_timer()
    # B: immediate dispatch uses owned timer (start(0)) not static singleShot
    assert tl._next_scan_timer.isActive()
    assert tl._next_scan_timer.interval() == 0


def test_setup_next_scan_timer_power_auto_vs_scan(fake_timers, tmp_xdg, mock_gpio, mock_scan_class, mock_plantdb, qtbot):
    from plantimager.controller.scanner.dummy_cnc import DummyCNC
    cfg = minimal_config(mode="interval", interval=60, n_shots=2, grace_period=10, warmup_period=30, standby_threshold_sec=600)
    tl, pm = make_timelapse(cfg, tmp_xdg, fake_timers, mock_scan_class, mock_plantdb, mock_gpio)
    now = datetime.datetime.now(timezone.utc)
    # far → AUTO (power-down happens asynchronously, so wait for it) + warm-up timer armed
    tl.schedule_times = [now + datetime.timedelta(seconds=3600)]
    tl.next_idx = 0
    tl._setup_next_scan_timer()
    qtbot.waitUntil(lambda: pm.mode == PowerManagerMode.AUTO, timeout=3000)
    assert pm.warmup_timer.isActive()
    assert pm._next_warmup_date == tl.schedule_times[0] - datetime.timedelta(seconds=30)
    # close → SCAN stays powered
    tl.schedule_times = [now + datetime.timedelta(seconds=100)]
    tl.next_idx = 0
    pm.cnc = DummyCNC()  # re-attach a fresh CNC so re-entering SCAN is a stable transition
    tl._setup_next_scan_timer()
    assert pm.mode == PowerManagerMode.SCAN
    assert not pm.warmup_timer.isActive()


# ---------------------------------------------------------------------------
# _trigger_next_scan + cancel + cnc_ready
# ---------------------------------------------------------------------------
def test_trigger_next_scan_advances_and_completes(fake_timers, tmp_xdg, mock_gpio, mock_plantdb):
    with patch("plantimager.controller.scanner.timelapse.Scan") as MockScan:
        inst = MagicMock()
        inst.scan.return_value = None
        inst._start_time = 0
        inst._stop_time = 1
        inst.status = "succeeded"
        inst.error = None
        MockScan.return_value = inst
        cfg = minimal_config(mode="interval", interval=60, n_shots=2, grace_period=120)
        from plantimager.controller.scanner.powermanager import PowerManager
        from plantimager.controller.scanner.dummy_cnc import DummyCNC
        pm = PowerManager(warmup_period=30)
        pm.cnc = DummyCNC()
        tl = TimeLapse(db_url="http://dummy", cameras=[], path=[], timelapse_name="tl-trig", config=cfg, power_manager=pm)
        # mock timers to avoid real arming in __init__, then set schedule now
        tl._next_scan_timer = FakeTimer()
        tl.schedule_times = [datetime.datetime.now(timezone.utc) - datetime.timedelta(seconds=5),
                             datetime.datetime.now(timezone.utc) - datetime.timedelta(seconds=5)]
        tl.next_idx = 0
        tl.state = TimeLapseState.SCHEDULED
        finished = []
        tl.scanFinished.connect(lambda: finished.append(True))
        tl._trigger_next_scan()
        assert tl.next_idx == 1
        assert tl.state == TimeLapseState.SCHEDULED
        tl._trigger_next_scan()
        assert tl.next_idx == 2
        assert tl.state == TimeLapseState.COMPLETED
        assert finished


def test_cancel_persists_and_emits(fake_timers, tmp_xdg, mock_gpio, mock_scan_class, mock_plantdb, qtbot):
    cfg = minimal_config(mode="interval", interval=60, n_shots=5)
    tl, _ = make_timelapse(cfg, tmp_xdg, fake_timers, mock_scan_class, mock_plantdb, mock_gpio)
    with qtbot.waitSignal(tl.scanFinished, timeout=1000):
        tl.cancel()
    assert tl.state == TimeLapseState.CANCELLED
    assert not tl._next_scan_timer.isActive()
    from plantimager.controller.scanner.timelapse_store import get_storage_dir
    assert (get_storage_dir() / "timelapse_storage.json").exists()


def test_cnc_ready_rearms_if_not_terminal(fake_timers, tmp_xdg, mock_gpio, mock_scan_class, mock_plantdb):
    cfg = minimal_config(mode="interval", interval=60, n_shots=2)
    tl, _ = make_timelapse(cfg, tmp_xdg, fake_timers, mock_scan_class, mock_plantdb, mock_gpio)
    tl.state = TimeLapseState.COMPLETED
    tl._setup_next_scan_timer = MagicMock()
    from plantimager.controller.scanner.dummy_cnc import DummyCNC
    tl.cnc_ready(DummyCNC())
    tl._setup_next_scan_timer.assert_not_called()
    tl.state = TimeLapseState.SCHEDULED
    tl._setup_next_scan_timer.reset_mock()
    tl.cnc_ready(DummyCNC())
    tl._setup_next_scan_timer.assert_called_once()


# ---------------------------------------------------------------------------
# signal order with pytest-qt (stateChanged vs PowerManager.modeChanged)
# ---------------------------------------------------------------------------
def test_signal_emission_order_timelapse_vs_power(fake_timers, tmp_xdg, mock_gpio, mock_scan_class, mock_plantdb, qtbot):
    from plantimager.controller.scanner.dummy_cnc import DummyCNC
    cfg = minimal_config(mode="interval", interval=60, n_shots=1, grace_period=10, standby_threshold_sec=600, warmup_period=30)
    tl, pm = make_timelapse(cfg, tmp_xdg, fake_timers, mock_scan_class, mock_plantdb, mock_gpio)
    # Deterministic baseline: powered (cnc present) and in AUTO.
    pm.cnc = DummyCNC()
    pm._mode = PowerManagerMode.AUTO
    state_spy = []
    power_spy = []
    tl.stateChanged.connect(lambda s: state_spy.append(s))
    pm.modeChanged.connect(lambda m: power_spy.append(m))
    # power transition does not emit timelapse state
    assert pm.try_set_mode(PowerManagerMode.SCAN) is True
    assert power_spy == ["scan"]
    assert state_spy == []
    # timelapse state transitions do not emit power
    tl.state = TimeLapseState.RUNNING
    tl.state = TimeLapseState.SCHEDULED
    assert state_spy == ["running", "scheduled"]
    assert power_spy == ["scan"]


def test_progress_signals(fake_timers, tmp_xdg, mock_gpio, mock_scan_class, mock_plantdb, qtbot):
    cfg = minimal_config(mode="interval", interval=60, n_shots=1)
    tl, _ = make_timelapse(cfg, tmp_xdg, fake_timers, mock_scan_class, mock_plantdb, mock_gpio)
    with qtbot.waitSignal(tl.progressChanged, timeout=1000):
        tl.current_idx = 2
        tl.progressChanged.emit(tl.current_idx, tl._max_progress)


# ---------------------------------------------------------------------------
# CONFIGURED draft — recompute at arm, no persist/power until arm
# ---------------------------------------------------------------------------
def test_configured_no_arm_no_persist(fake_timers, tmp_xdg, mock_gpio, mock_scan_class, mock_plantdb):
    from plantimager.controller.scanner.powermanager import PowerManager
    from plantimager.controller.scanner.dummy_cnc import DummyCNC
    cfg = minimal_config(mode="interval", interval=60, n_shots=3, warmup_period=30)
    pm = PowerManager(warmup_period=30)
    pm.cnc = DummyCNC()
    tl = TimeLapse(db_url="http://dummy", cameras=[], path=[], timelapse_name="tl-cfg", config=cfg, power_manager=pm, auto_start=False)
    assert tl.state == TimeLapseState.CONFIGURED
    assert not tl._next_scan_timer.isActive()
    from plantimager.controller.scanner.timelapse_store import get_storage_dir
    assert not (get_storage_dir() / "timelapse_storage.json").exists()


def test_arm_recomputes_interval_with_warmup(fake_timers, tmp_xdg, mock_gpio, mock_scan_class, mock_plantdb):
    from plantimager.controller.scanner.powermanager import PowerManager
    from plantimager.controller.scanner.dummy_cnc import DummyCNC
    import freezegun
    cfg = minimal_config(mode="interval", interval=30, n_shots=3, warmup_period=10)
    pm = PowerManager(warmup_period=10)
    pm.cnc = DummyCNC()
    with freezegun.freeze_time("2026-09-22 10:00:00+00:00"):
        tl = TimeLapse(db_url="http://dummy", cameras=[], path=[], timelapse_name="tl-arm", config=cfg, power_manager=pm, auto_start=False)
        pre = list(tl.schedule_times)
        # wait a bit then arm — schedule should move forward
        with freezegun.freeze_time("2026-09-22 10:05:00+00:00"):
            tl.arm()
            assert tl.state == TimeLapseState.SCHEDULED
            assert tl.schedule_times[0] > pre[0]
            assert (tl.schedule_times[1] - tl.schedule_times[0]).total_seconds() == 30


def test_arm_fixed_times_no_recompute(fake_timers, tmp_xdg, mock_gpio, mock_scan_class, mock_plantdb):
    from plantimager.controller.scanner.powermanager import PowerManager
    from plantimager.controller.scanner.dummy_cnc import DummyCNC
    import datetime as dt
    future = (dt.datetime.now(timezone.utc) + dt.timedelta(hours=1)).isoformat()
    cfg = minimal_config(mode="fixed_times", dates=[future])
    pm = PowerManager(warmup_period=30)
    pm.cnc = DummyCNC()
    tl = TimeLapse(db_url="http://dummy", cameras=[], path=[], timelapse_name="tl-fixed", config=cfg, power_manager=pm, auto_start=False)
    pre = list(tl.schedule_times)
    tl.arm()
    assert tl.schedule_times == pre
    assert tl.state == TimeLapseState.SCHEDULED


def test_cnc_ready_ignored_while_configured(fake_timers, tmp_xdg, mock_gpio, mock_scan_class, mock_plantdb):
    from plantimager.controller.scanner.powermanager import PowerManager
    from plantimager.controller.scanner.dummy_cnc import DummyCNC
    cfg = minimal_config(mode="interval", interval=60, n_shots=2)
    pm = PowerManager(warmup_period=30)
    pm.cnc = DummyCNC()
    tl = TimeLapse(db_url="http://dummy", cameras=[], path=[], timelapse_name="tl-cnc", config=cfg, power_manager=pm, auto_start=False)
    tl._setup_next_scan_timer = MagicMock()
    tl.cnc_ready(DummyCNC())
    tl._setup_next_scan_timer.assert_not_called()
    assert tl.state == TimeLapseState.CONFIGURED


# ---------------------------------------------------------------------------
# RPC-thread affinity — TimeLapse timers must live on the Qt main thread.
# Uses the real QTimer (no fake_timers): constructing/arming from the RPC
# server thread used to bind the timer to a thread with no event loop, so
# no scan ever fired. Fails before the run_on_main_thread fix.
# ---------------------------------------------------------------------------
def _ready_scanner_for_rpc():
    from unittest.mock import MagicMock
    from plantimager.controller.scanner.dummy_cnc import DummyCNC
    from plantimager.controller.scanner.scanner import Scanner
    from plantimager.controller.scanner.path import Circle
    scanner = Scanner()
    scanner.config = minimal_config()
    scanner.scan_path = Circle(center_x=0, center_y=0, z=10, tilt=0, radius=10, n_points=4)
    scanner.db_client = MagicMock()
    scanner.set_base_name("rpc-affinity")
    scanner.power_manager.cnc = DummyCNC()
    cam = MagicMock()
    cam.name = "cam1"
    scanner.cameras = [cam]
    return scanner


def _rpc_server_for(scanner):
    import zmq
    from plantimager.controller.scanner.rpc_controller import RPCControllerServer
    ctx = zmq.Context()
    server = RPCControllerServer(ctx, "tcp://127.0.0.1", scanner)
    return ctx, server


def _call_from_worker(app, fn, timeout=10):
    """Run ``fn`` on a plain thread (like the RPC server thread) while the
    main thread pumps the Qt event loop so queued slots get delivered."""
    import threading
    import time
    box = {}

    def target():
        try:
            box["result"] = fn()
        except Exception as exc:
            box["error"] = exc

    t = threading.Thread(target=target)
    t.start()
    deadline = time.monotonic() + timeout
    while t.is_alive() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    t.join(timeout=5)
    assert not t.is_alive(), "worker RPC call did not complete"
    if "error" in box:
        raise box["error"]
    return box.get("result")


def _assert_timer_on_main_thread(tl):
    from PySide6.QtCore import QThread
    main_thread = QThread.currentThread()
    assert tl.thread() is main_thread
    assert tl._next_scan_timer.thread() is main_thread
    assert tl._next_scan_timer.isActive()


def test_start_timelapse_from_worker_thread_binds_timer_to_main(
        tmp_xdg, mock_gpio, mock_scan_class, mock_plantdb, qtbot):
    from PySide6.QtCore import QCoreApplication
    app = QCoreApplication.instance()
    scanner = _ready_scanner_for_rpc()
    ctx, server = _rpc_server_for(scanner)
    try:
        cfg = minimal_config(mode="interval", interval=3600, n_shots=2,
                             grace_period=5, warmup_period=30)
        tl_id = _call_from_worker(app, lambda: server.start_timelapse(cfg))
        assert tl_id == "rpc-affinity"
        assert scanner.timelapse.state == TimeLapseState.SCHEDULED
        _assert_timer_on_main_thread(scanner.timelapse)
    finally:
        server._socket.close()
        ctx.term()


def test_config_then_arm_from_worker_thread(tmp_xdg, mock_gpio, mock_scan_class, mock_plantdb, qtbot):
    from PySide6.QtCore import QCoreApplication
    app = QCoreApplication.instance()
    scanner = _ready_scanner_for_rpc()
    ctx, server = _rpc_server_for(scanner)
    try:
        cfg = minimal_config(mode="interval", interval=3600, n_shots=2,
                             grace_period=5, warmup_period=30)
        snap = _call_from_worker(app, lambda: server.config_timelapse(cfg))
        assert snap["state"] == "configured"
        tl_id = _call_from_worker(app, lambda: server.start_timelapse())
        assert tl_id == "rpc-affinity"
        assert scanner.timelapse.state == TimeLapseState.SCHEDULED
        _assert_timer_on_main_thread(scanner.timelapse)
    finally:
        server._socket.close()
        ctx.term()


def test_worker_thread_rpc_error_propagates(tmp_xdg, mock_gpio, mock_scan_class, mock_plantdb, qtbot):
    from PySide6.QtCore import QCoreApplication
    from plantimager.controller.scanner.scanner import Scanner
    app = QCoreApplication.instance()
    scanner = Scanner()  # no base name set
    ctx, server = _rpc_server_for(scanner)
    try:
        cfg = minimal_config(mode="interval", interval=3600, n_shots=1)
        with pytest.raises(RuntimeError):
            _call_from_worker(app, lambda: server.start_timelapse(cfg))
    finally:
        server._socket.close()
        ctx.term()


def test_run_on_main_thread_preserves_registration():
    from plantimager.controller.scanner.rpc_controller import RPCControllerServer
    assert RPCControllerServer.config_timelapse._is_json_method is True
    assert RPCControllerServer.start_timelapse._is_json_method is True
    assert RPCControllerServer.config_timelapse._timeout == 10000
    assert RPCControllerServer.start_timelapse._timeout is None


def test_cancel_timelapse_from_worker_thread_stops_timer(
        tmp_xdg, mock_gpio, mock_scan_class, mock_plantdb, qtbot):
    from PySide6.QtCore import QCoreApplication
    app = QCoreApplication.instance()
    scanner = _ready_scanner_for_rpc()
    ctx, server = _rpc_server_for(scanner)
    try:
        cfg = minimal_config(mode="interval", interval=3600, n_shots=2,
                             grace_period=5, warmup_period=30)
        _call_from_worker(app, lambda: server.start_timelapse(cfg))
        timer = scanner.timelapse._next_scan_timer
        assert timer.isActive()
        _call_from_worker(app, lambda: server.cancel_timelapse())
        assert scanner.timelapse.state == TimeLapseState.CANCELLED
        assert not timer.isActive()
    finally:
        server._socket.close()
        ctx.term()
