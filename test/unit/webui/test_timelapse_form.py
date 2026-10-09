"""Unit tests for the web UI timelapse form helpers (step 1).

The populate/rebuild callbacks are plain functions, so they are exercised
directly without a Dash app context — same pattern as ``test_scan_helpers``.
"""

import unittest

from dash import no_update

from plantimager.webui.scan import (
    _current_snapshot,
    _dump,
    _load_cfg,
    _local_preview_line,
    _render_preview,
    _render_timelapse_status,
    _schedule_table,
    _tl_body_style,
    _tl_row_status,
    _toggle_scan_buttons,
    _toggle_timelapse_rows,
    _validate_timelapse,
    cancel_scan,
    populate_timelapse,
    rebuild_timelapse,
    update_timelapse_snapshot,
)

BASE_TOML = """\
[ScanPath]
class_name = "Circle"

[ScanPath.kwargs]
n_points = 4
"""


def _with_timelapse(body):
    return BASE_TOML + "\n[timelapse]\n" + body


class TestPopulateTimelapse(unittest.TestCase):
    def test_absent_section_keeps_switch(self):
        out = populate_timelapse(BASE_TOML, True)
        self.assertTrue(out[0])
        self.assertEqual(list(out[1:-1]), [no_update] * 9)
        self.assertEqual(out[-1], {})
        out = populate_timelapse(BASE_TOML, False)
        self.assertFalse(out[0])
        self.assertEqual(out[-1], _tl_body_style(False))

    def test_full_section(self):
        toml = _with_timelapse(
            'mode = "interval"\ninterval = "30s"\nn_shots = 5\n'
            'dates = []\nwarmup_period = 10\ngrace_period = 120\n'
            'standby_threshold_sec = 600\non_scan_failed = "skip_scan"\nscan_retries = 0\n'
        )
        out = populate_timelapse(toml, True)
        self.assertEqual(out[:5], (True, "interval", "30s", "5", ""))
        self.assertEqual(out[5:9], ("10", "120", "600", "skip_scan"))
        self.assertEqual(out[9:11], ("0", {}))

    def test_dates_joined(self):
        toml = _with_timelapse('mode = "fixed_times"\ndates = ["2026-10-09T10:00:00", "2026-10-09T14:00:00"]\n')
        out = populate_timelapse(toml, True)
        self.assertEqual(out[1], "fixed_times")
        self.assertEqual(out[4], "2026-10-09T10:00:00\n2026-10-09T14:00:00")


class TestRebuildTimelapse(unittest.TestCase):
    def test_interval_keeps_ints(self):
        out = rebuild_timelapse(True, "interval", "30s", "5", "", "10", "120", "600",
                                "skip_scan", "0", BASE_TOML)
        tl = _load_cfg(out)["timelapse"]
        self.assertEqual(tl["mode"], "interval")
        self.assertEqual(tl["interval"], "30s")
        self.assertEqual(tl["n_shots"], 5)
        self.assertIsInstance(tl["n_shots"], int)
        self.assertIn("ScanPath", _load_cfg(out))  # other sections preserved

    def test_fixed_times_drops_interval_keys(self):
        out = rebuild_timelapse(True, "fixed_times", "30s", "5",
                                "2026-10-09T10:00:00\n2026-10-09T14:00:00\n",
                                "", "", "", "", "", BASE_TOML)
        tl = _load_cfg(out)["timelapse"]
        self.assertEqual(tl["dates"], ["2026-10-09T10:00:00", "2026-10-09T14:00:00"])
        self.assertNotIn("interval", tl)
        self.assertNotIn("n_shots", tl)

    def test_one_shot_drops_schedule_keys(self):
        out = rebuild_timelapse(True, "one_shot", "30s", "5", "2026-10-09T10:00:00",
                                "", "", "", "", "", BASE_TOML)
        tl = _load_cfg(out)["timelapse"]
        self.assertEqual(tl["mode"], "one_shot")
        self.assertNotIn("interval", tl)
        self.assertNotIn("dates", tl)

    def test_disabled_strips_section(self):
        toml = _with_timelapse('mode = "interval"\ninterval = "30s"\nn_shots = 5\n')
        out = rebuild_timelapse(False, "interval", "30s", "5", "", "", "", "",
                                "", "", toml)
        cfg = _load_cfg(out)
        self.assertNotIn("timelapse", cfg)
        self.assertIn("ScanPath", cfg)

    def test_round_trip(self):
        out = rebuild_timelapse(True, "interval", "1h30m", "12", "", "45", "120", "600",
                                "fail_timelapse", "2", BASE_TOML)
        pop = populate_timelapse(out, True)
        self.assertEqual(pop[1:5], ("interval", "1h30m", "12", ""))
        self.assertEqual(pop[8], "fail_timelapse")


class TestTimelapseHelpers(unittest.TestCase):
    def test_num_keeps_ints(self):
        from plantimager.webui.scan import _num
        self.assertEqual(_num("5"), 5)
        self.assertIsInstance(_num("5"), int)
        self.assertEqual(_num("1.5"), 1.5)
        self.assertEqual(_num("30s"), "30s")

    def test_body_style(self):
        self.assertEqual(_tl_body_style(True), {})
        disabled = _tl_body_style(False)
        self.assertEqual(disabled["opacity"], "0.4")
        self.assertEqual(disabled["pointerEvents"], "none")

    def test_row_visibility(self):
        show, hide = {"display": "block"}, {"display": "none"}
        self.assertEqual(_toggle_timelapse_rows("interval"), (show, show, hide))
        self.assertEqual(_toggle_timelapse_rows("fixed_times"), (hide, hide, show))
        self.assertEqual(_toggle_timelapse_rows("one_shot"), (hide, hide, hide))


class TestTimelapseTitle(unittest.TestCase):
    def _ids(self, comp, found=None):
        found = [] if found is None else found
        if getattr(comp, "id", None):
            found.append(comp.id)
        for child in getattr(comp, "children", None) or []:
            if hasattr(child, "children") or getattr(child, "id", None):
                self._ids(child, found)
            elif isinstance(child, (list, tuple)):
                for c in child:
                    self._ids(c, found)
        return found

    def test_switch_overlays_header(self):
        from plantimager.webui.scan import _timelapse_item
        self.assertIn("tl-enabled", self._ids(_timelapse_item()))


class TestScanButtons(unittest.TestCase):
    def _text(self, children):
        return "".join(c for c in children if isinstance(c, str))

    def test_labels_follow_switch(self):
        start, cancel, dataset, config = _toggle_scan_buttons(True)
        self.assertIn("Start Timelapse", self._text(start))
        self.assertIn("Cancel Timelapse", self._text(cancel))
        self.assertIn("timelapse", dataset)
        self.assertIn("Configure Timelapse", self._text(config))
        start, cancel, dataset, config = _toggle_scan_buttons(False)
        self.assertIn("Start Scanning", self._text(start))
        self.assertIn("Cancel Scan", self._text(cancel))
        self.assertIn("dataset", dataset)
        self.assertIn("Configure Scanner", self._text(config))

    def test_cancel_legacy_needs_no_controller(self):
        self.assertEqual(cancel_scan(None, False), "Cancelling scan...")

    def test_cancel_timelapse_without_controller_errors(self):
        self.assertIn("not initialized", cancel_scan(None, True))


class TestPreviewRender(unittest.TestCase):
    def test_schedule_lines(self):
        md = _render_preview({
            "mode": "interval", "n_scans": 2,
            "schedule_times": ["2026-10-09T10:00:00+00:00", "2026-10-09T11:00:00+00:00"],
        })
        self.assertIn("interval", md)
        self.assertIn("#0", md)
        self.assertIn("#1", md)

    def test_local_line_falls_back(self):
        self.assertEqual(_local_preview_line("not-a-date"), "not-a-date")
        self.assertRegex(_local_preview_line("2026-10-09T10:00:00+00:00"), r"\d{2}/\d{2} \d{2}:\d{2}")


class TestStatusRender(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(_render_timelapse_status(None)[0], "No timelapse")

    def test_running_multi(self):
        badge, color, text = _render_timelapse_status({
            "timelapse_id": "exp", "mode": "interval", "state": "SCHEDULED",
            "plantdb_timelapse_id": "exp", "next_idx": 1,
            "schedule_times": ["2026-10-09T10:00:00+00:00", "2026-10-09T11:00:00+00:00"],
        })
        self.assertEqual(badge, "SCHEDULED")
        self.assertEqual(color, "warning")
        self.assertIn("1/2", text)

    def test_bare_single_row(self):
        badge, color, text = _render_timelapse_status({
            "timelapse_id": "exp", "mode": "one_shot", "state": "SCHEDULED",
            "next_idx": 0,
            "schedule_times": ["2026-10-09T10:00:00+00:00"],
        })
        self.assertIn("Single scan", text)

    def test_multi_draft_without_container(self):
        # plantdb_timelapse_id only exists after arming; counts must show anyway.
        badge, color, text = _render_timelapse_status({
            "timelapse_id": "exp", "mode": "interval", "state": "CONFIGURED",
            "next_idx": 0,
            "schedule_times": ["2026-10-09T10:00:00+00:00",
                               "2026-10-09T11:00:00+00:00"],
        })
        self.assertIn("0/2", text)

    def test_failed_color(self):
        self.assertEqual(_render_timelapse_status({"state": "FAILED"})[1], "danger")

    def test_snapshot_mirror(self):
        import plantimager.webui.scan as scan_mod
        update_timelapse_snapshot({"state": "x"})
        self.assertEqual(scan_mod.latest_timelapse, {"state": "x"})
        scan_mod.latest_timelapse = None

    def test_unit_signal_rereads_without_controller(self):
        # Bare emit (no payload) with no controller leaves the mirror alone.
        import plantimager.webui.scan as scan_mod
        update_timelapse_snapshot({"state": "x"})
        update_timelapse_snapshot()
        self.assertEqual(scan_mod.latest_timelapse, {"state": "x"})
        scan_mod.latest_timelapse = None

    def test_current_snapshot_falls_back_to_mirror(self):
        update_timelapse_snapshot({"state": "SCHEDULED"})
        try:
            self.assertEqual(_current_snapshot(), {"state": "SCHEDULED"})
        finally:
            update_timelapse_snapshot(None)


class TestScheduleTable(unittest.TestCase):
    def _snap(self, **over):
        snap = {"timelapse_id": "exp", "mode": "interval", "state": "SCHEDULED",
                "plantdb_timelapse_id": "exp", "next_idx": 1,
                "schedule_times": ["2026-10-09T10:00:00+00:00",
                                   "2026-10-09T11:00:00+00:00",
                                   "2026-10-09T12:00:00+00:00"],
                "scans": [{"scan_id": "exp_0", "status": "succeeded"}]}
        snap.update(over)
        return snap

    def test_row_status_from_records(self):
        snap = self._snap()
        self.assertEqual(_tl_row_status(0, snap), "done")
        self.assertEqual(_tl_row_status(1, snap), "next")
        self.assertEqual(_tl_row_status(2, snap), "pending")

    def test_row_status_failed_and_running(self):
        snap = self._snap(scans=[{"scan_id": "exp_1", "status": "failed"}],
                          state="RUNNING")
        self.assertEqual(_tl_row_status(1, snap), "failed")
        self.assertEqual(_tl_row_status(2, snap), "pending")
        snap = self._snap(scans=[], state="RUNNING", next_idx=0)
        self.assertEqual(_tl_row_status(0, snap), "running")
        self.assertEqual(_tl_row_status(1, snap), "pending")

    def test_row_status_bare_id_match(self):
        snap = self._snap(scans=[{"scan_id": "exp", "status": "succeeded"}])
        self.assertEqual(_tl_row_status(0, snap), "done")

    def test_row_status_skipped(self):
        snap = self._snap(scans=[{"scan_id": "exp_0", "status": "skipped"}])
        self.assertEqual(_tl_row_status(0, snap), "skipped")
        snap = self._snap(scans=[], next_idx=2)
        self.assertEqual(_tl_row_status(0, snap), "skipped")

    def test_table_shape(self):
        table = _schedule_table(self._snap())
        body = table.children[1]
        self.assertEqual(len(body.children), 3)
        first = body.children[0].children
        self.assertEqual(first[0].children, "#0")


class TestValidateTimelapse(unittest.TestCase):
    def test_valid_interval(self):
        self.assertEqual(_validate_timelapse(
            {"timelapse": {"mode": "interval", "interval": "30s", "n_shots": 5}}), [])

    def test_unknown_mode(self):
        self.assertEqual(len(_validate_timelapse({"timelapse": {"mode": "bogus"}})), 1)

    def test_interval_missing_fields(self):
        issues = _validate_timelapse({"timelapse": {"mode": "interval"}})
        self.assertEqual(len(issues), 2)

    def test_n_bounds(self):
        base = {"mode": "interval", "interval": "30s"}
        self.assertTrue(_validate_timelapse({"timelapse": {**base, "n_shots": 0}}))
        self.assertTrue(_validate_timelapse({"timelapse": {**base, "n_shots": 2.5}}))
        self.assertTrue(_validate_timelapse({"timelapse": {**base, "n_shots": "many"}}))
        self.assertEqual(_validate_timelapse({"timelapse": {**base, "n_shots": 3}}), [])

    def test_fixed_times(self):
        self.assertTrue(_validate_timelapse({"timelapse": {"mode": "fixed_times"}}))
        self.assertTrue(_validate_timelapse(
            {"timelapse": {"mode": "fixed_times", "dates": ["yesterday"]}}))
        self.assertEqual(_validate_timelapse(
            {"timelapse": {"mode": "fixed_times",
                           "dates": ["2026-10-09T10:00:00"]}}), [])

    def test_retries(self):
        self.assertTrue(_validate_timelapse(
            {"timelapse": {"mode": "one_shot", "scan_retries": -1}}))
        self.assertEqual(_validate_timelapse({"timelapse": {"mode": "one_shot"}}), [])

    def test_clamped_bounds_never_rejected(self):
        self.assertEqual(_validate_timelapse(
            {"timelapse": {"mode": "interval", "interval": "30s", "n_shots": 2,
                           "warmup_period": 1, "standby_threshold_sec": 1}}), [])

    def test_upload_round_trip(self):
        toml = (BASE_TOML + '\n[picamera]\nres_x = 2000\n'
                '\n[timelapse]\nmode = "interval"\ninterval = "1h"\nn_shots = 4\n'
                'warmup_period = 45\non_scan_failed = "fail_timelapse"\n')
        out = populate_timelapse(toml, True)
        self.assertEqual(out[1:4], ("interval", "1h", "4"))
        self.assertEqual(out[8], "fail_timelapse")
        rebuilt = rebuild_timelapse(True, "interval", "1h", "4", "", "45", "", "",
                                    "fail_timelapse", "", toml)
        cfg = _load_cfg(rebuilt)
        self.assertEqual(cfg["timelapse"]["n_shots"], 4)
        self.assertEqual(cfg["picamera"]["res_x"], 2000)


if __name__ == "__main__":
    unittest.main()
