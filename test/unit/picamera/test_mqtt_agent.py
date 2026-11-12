"""Unit tests for the picamera MQTT lifecycle agent.

Only the paho-free parts are tested here: action-to-systemctl mapping and
the decode-then-apply path with ``subprocess`` mocked. The broker loop
itself needs a live mosquitto and is covered by the bench validation.
"""

import json
import os
import sys
import unittest
from unittest import mock

# plantimager.picamera is not installed (no Pi hardware here); import it from source.
_SRC_PICAMERA = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "src", "picamera"))
if os.path.isdir(_SRC_PICAMERA) and _SRC_PICAMERA not in sys.path:
    sys.path.insert(0, _SRC_PICAMERA)

from plantimager.picamera import mqtt_agent
from plantimager.commons.mqtt_utils import split_broker_url


class TestCommandArgv(unittest.TestCase):
    def test_restart_drives_system_camera_service(self):
        self.assertEqual(mqtt_agent.command_argv("restart_service"),
                         ["systemctl", "restart",
                          "picamera-server.service"])

    def test_reboot_and_poweroff_are_system_commands(self):
        self.assertEqual(mqtt_agent.command_argv("reboot"),
                         ["systemctl", "reboot"])
        self.assertEqual(mqtt_agent.command_argv("poweroff"),
                         ["systemctl", "poweroff"])

    def test_unknown_action_rejected(self):
        with self.assertRaises(ValueError):
            mqtt_agent.command_argv("self_destruct")


class TestApplyCommand(unittest.TestCase):
    def test_valid_payload_runs_mapped_command(self):
        payload = json.dumps({"action": "restart_service",
                              "request_id": "abc",
                              "issued_by": "controller"})
        with mock.patch.object(mqtt_agent.subprocess, "check_call") as call:
            mqtt_agent.apply_command(mqtt_agent.decode_command(payload))
        call.assert_called_once_with(
            ["systemctl", "restart", "picamera-server.service"])

    def test_invalid_payload_runs_nothing(self):
        with mock.patch.object(mqtt_agent.subprocess, "check_call") as call:
            with self.assertRaises(ValueError):
                mqtt_agent.apply_command(
                    mqtt_agent.decode_command(json.dumps({"action": "halt"})))
        call.assert_not_called()


class TestSplitBroker(unittest.TestCase):
    def test_tcp_url_splits_host_port(self):
        self.assertEqual(split_broker_url("tcp://10.10.11.1:1883"),
                         ("10.10.11.1", 1883))


class FakeMessage:
    def __init__(self, topic, payload):
        self.topic = topic
        self.payload = payload


class TestRunLoop(unittest.TestCase):
    """The subscribe/dispatch wiring, with broker client stubbed."""

    def test_subscribes_own_and_fleet_topics_then_dispatches(self):
        clients = []

        class FakeClient:
            def __init__(self, *args, **kwargs):
                clients.append(self)
                self.subscriptions = []

            def subscribe(self, topic, qos=1):
                self.subscriptions.append((topic, qos))

            def connect(self, host, port, keepalive=60):
                self.server = (host, port)

            def loop_forever(self):
                self.on_connect(self, None, None, 0)
                payload = json.dumps({"action": "restart_service",
                                      "request_id": "loop1",
                                      "issued_by": "test"}).encode()
                with mock.patch.object(mqtt_agent.subprocess,
                                       "check_call") as call:
                    self.on_message(self, None,
                                    FakeMessage("plantimager/picamera/all/command",
                                                payload))
                call.assert_called_once_with(
                    ["systemctl", "restart",
                     "picamera-server.service"])

        fake_paho = mock.MagicMock()
        fake_paho.mqtt.client.Client = FakeClient
        with mock.patch.dict(sys.modules, {"paho": fake_paho,
                                           "paho.mqtt": fake_paho.mqtt,
                                           "paho.mqtt.client":
                                               fake_paho.mqtt.client}):
            mqtt_agent.run(hostname="picamera9",
                           broker="tcp://10.10.11.1:1883")

        (client,) = clients
        self.assertEqual(client.server, ("10.10.11.1", 1883))
        self.assertEqual(client.subscriptions,
                         [("plantimager/picamera/picamera9/command", 1),
                          ("plantimager/picamera/all/command", 1)])


if __name__ == "__main__":
    unittest.main()
