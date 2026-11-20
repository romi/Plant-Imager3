"""Unit tests for plant-imager-webui-setup (render + dry run)."""

import io
import unittest
from contextlib import redirect_stdout
from unittest import mock

from plantimager.webui import install as webui_install


class TestRenderUnit(unittest.TestCase):
    def test_webui_exec_start_built_from_flags(self):
        args = webui_install.build_parser().parse_args(
            ["--plantdb-host", "example.org"])
        out = webui_install.webui_exec_start("/home/romi/venv/bin", args)
        self.assertIn(
            "ExecStart=/home/romi/venv/bin/plant-imager-webui", out)
        self.assertIn("--plantdb-host example.org", out)
        self.assertIn("--url-prefix /webui", out)

    def test_explicit_port_appended(self):
        args = webui_install.build_parser().parse_args(["--webui-port", "8080"])
        out = webui_install.webui_exec_start("/home/romi/venv/bin", args)
        self.assertIn("--port 8080", out)


class TestDryRun(unittest.TestCase):
    def test_install_dry_run_touches_nothing(self):
        args = webui_install.build_parser().parse_args(
            ["--user", "romi", "--dry-run"])
        with mock.patch.object(webui_install.os.path, "isdir",
                               return_value=True):
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = webui_install.install(args)
        self.assertEqual(rc, 0)
        self.assertIn(
            "write /home/romi/.config/systemd/user/plant-imager-webui.service",
            buf.getvalue())

    def test_remove_dry_run(self):
        args = webui_install.build_parser().parse_args(
            ["--user", "romi", "--remove", "--dry-run"])
        with mock.patch.object(webui_install.os.path, "isdir",
                               return_value=True):
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = webui_install.install(args)
        self.assertEqual(rc, 0)
        self.assertIn(
            "- /home/romi/.config/systemd/user/plant-imager-webui.service",
            buf.getvalue())


if __name__ == "__main__":
    unittest.main()
