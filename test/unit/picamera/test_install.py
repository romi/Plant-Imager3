"""Unit tests for picamera-install (templates + dry run, no system touch)."""

import io
import os
import sys
import unittest
from contextlib import redirect_stdout
from unittest import mock

# plantimager.picamera is not installed (no Pi hardware here); import it from source.
_SRC_PICAMERA = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "src", "picamera"))
if os.path.isdir(_SRC_PICAMERA) and _SRC_PICAMERA not in sys.path:
    sys.path.insert(0, _SRC_PICAMERA)

from plantimager.picamera import install as picamera_install


class TestRenderUnit(unittest.TestCase):
    def test_server_unit_templated(self):
        out = picamera_install.render_unit(
            picamera_install.template("picamera-server.service"),
            "romi", "picamera-server",
            {"PI_REGISTRY": "tcp://10.10.11.1:5555", "IP_ADDR": "10.10.11.13"})
        self.assertIn("ExecStart=/home/romi/picamera-env/bin/picamera-server", out)
        self.assertIn("Environment=PI_REGISTRY=tcp://10.10.11.1:5555", out)
        self.assertIn("Environment=IP_ADDR=10.10.11.13", out)
        self.assertNotIn("10.10.10.", out)

    def test_agent_unit_templated(self):
        out = picamera_install.render_unit(
            picamera_install.template("picamera-mqtt-agent.service"),
            "romi", "picamera-mqtt-agent",
            {"MQTT_BROKER": "tcp://10.10.11.1:26400"})
        self.assertIn("ExecStart=/home/romi/picamera-env/bin/picamera-mqtt-agent", out)
        self.assertIn("Environment=MQTT_BROKER=tcp://10.10.11.1:26400", out)


class TestDryRun(unittest.TestCase):
    def test_install_dry_run_touches_nothing(self):
        args = picamera_install.build_parser().parse_args(
            ["--user", "romi", "--registry", "tcp://1.2.3.4:5555",
             "--ip", "1.2.3.9", "--dry-run"])
        with mock.patch.object(picamera_install.os.path, "isdir", return_value=True):
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = picamera_install.install(args)
        self.assertEqual(rc, 0)
        out = buf.getvalue()
        self.assertIn("write /home/romi/.config/systemd/user/picamera-server.service", out)
        self.assertIn("loginctl enable-linger romi", out)

    def test_missing_home_fails(self):
        args = picamera_install.build_parser().parse_args(
            ["--user", "no-such-user-xyz", "--dry-run"])
        with mock.patch.object(picamera_install.os.path, "isdir", return_value=False):
            self.assertEqual(picamera_install.install(args), 1)


if __name__ == "__main__":
    unittest.main()
