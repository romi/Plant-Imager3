"""Unit tests for the shared systemd installer helpers."""

import os
import unittest

from plantimager.commons.systemd_install import replace_line
from plantimager.commons.systemd_install import run
from plantimager.commons.systemd_install import user_unit_dir


class TestReplaceLine(unittest.TestCase):
    def test_replaces_matching_lines_only(self):
        text = "ExecStart=/a\nEnvironment=X=1\nOther=yes\n"
        out = replace_line(text, "ExecStart=", "ExecStart=/b")
        self.assertEqual(out, "ExecStart=/b\nEnvironment=X=1\nOther=yes\n")

    def test_trailing_newline_kept(self):
        self.assertTrue(replace_line("a=1", "a=", "a=2").endswith("\n"))


class TestUserUnitDir(unittest.TestCase):
    def test_under_home(self):
        self.assertEqual(user_unit_dir("romi"),
                         os.path.join("/home", "romi", ".config/systemd/user"))


class TestRun(unittest.TestCase):
    def test_dry_run_prints_only(self):
        run(["definitely-not-a-real-command-xyz"], dry_run=True)


class TestEnableUnits(unittest.TestCase):
    def test_system_units_have_no_user_flavour(self):
        import io
        from contextlib import redirect_stdout
        from plantimager.commons.systemd_install import enable_system_units
        buf = io.StringIO()
        with redirect_stdout(buf):
            enable_system_units(["a.service", "b.service"], start=True,
                                dry_run=True)
        out = buf.getvalue()
        self.assertIn("systemctl daemon-reload", out)
        self.assertIn("systemctl enable a.service", out)
        self.assertIn("systemctl start b.service", out)
        self.assertNotIn("--user", out)
        self.assertNotIn("linger", out)


if __name__ == "__main__":
    unittest.main()
