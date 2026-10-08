"""Unit tests for the web UI timelapse form helpers (step 1).

The populate/rebuild callbacks are plain functions, so they are exercised
directly without a Dash app context — same pattern as ``test_scan_helpers``.
"""

import unittest

from dash import no_update

from plantimager.webui.scan import (
    _dump,
    _load_cfg,
    _tl_body_style,
    _tl_num,
    _toggle_timelapse_rows,
    populate_timelapse,
    rebuild_timelapse,
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
    def test_tl_num_keeps_ints(self):
        self.assertEqual(_tl_num("5"), 5)
        self.assertIsInstance(_tl_num("5"), int)
        self.assertEqual(_tl_num("1.5"), 1.5)
        self.assertEqual(_tl_num("30s"), "30s")

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


if __name__ == "__main__":
    unittest.main()
