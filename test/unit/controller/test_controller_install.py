"""Unit tests for plant-imager-controller-setup (render + dry run)."""

import io
import unittest
from contextlib import redirect_stdout
from unittest import mock

from plantimager.controller import install as controller_install


class TestRenderUnits(unittest.TestCase):

    def test_app_exec_start_templated(self):
        out = controller_install.render_app_unit("/home/romi/venv/bin")
        self.assertIn(
            "ExecStart=/home/romi/venv/bin/plant-imager-controller-app", out)
        self.assertNotIn("/home/romi/miniconda3", out)


class TestDryRun(unittest.TestCase):
    def test_install_dry_run_touches_nothing(self):
        args = controller_install.build_parser().parse_args(
            ["--user", "romi", "--skip-mosquitto", "--dry-run"])
        with mock.patch.object(controller_install.os.path, "isdir",
                               return_value=True):
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = controller_install.install(args)
        self.assertEqual(rc, 0)
        out = buf.getvalue()
        self.assertIn(
            "write /home/romi/.config/systemd/user/plant-imager-app.service", out)
        self.assertNotIn("plant-imager-webui.service", out)

    def test_remove_dry_run(self):
        args = controller_install.build_parser().parse_args(
            ["--user", "romi", "--remove", "--dry-run"])
        with mock.patch.object(controller_install.os.path, "isdir",
                               return_value=True):
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = controller_install.install(args)
        self.assertEqual(rc, 0)
        self.assertIn("- /home/romi/.config/systemd/user/plant-imager-app.service",
                      buf.getvalue())


if __name__ == "__main__":
    unittest.main()
