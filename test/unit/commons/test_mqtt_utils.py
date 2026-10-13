"""Unit tests for the shared MQTT topic and payload helpers."""

import json
import unittest
from unittest import mock

from plantimager.commons.mqtt_utils import (
    ACTIONS,
    BROKER_DEFAULT_HOST,
    BROKER_DEFAULT_PORT,
    ONE_WAY_ACTIONS,
    broker_url,
    build_command,
    decode_command,
    encode_command,
    fleet_topic,
    is_one_way,
    split_broker_url,
    topic_for,
)


class TestMqttTopics(unittest.TestCase):
    def test_topic_for_hostname(self):
        self.assertEqual(topic_for("picamera1"),
                         "plantimager/picamera/picamera1/command")

    def test_fleet_topic_uses_all_hostname(self):
        self.assertEqual(fleet_topic(), "plantimager/picamera/all/command")


class TestMqttBrokerUrl(unittest.TestCase):
    def test_default_points_at_controller_usb_bridge(self):
        with mock.patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("MQTT_BROKER", None)
            self.assertEqual(
                broker_url(), f"tcp://{BROKER_DEFAULT_HOST}:{BROKER_DEFAULT_PORT}")

    def test_env_override_wins(self):
        with mock.patch.dict("os.environ",
                             {"MQTT_BROKER": "tcp://127.0.0.1:1883"}):
            self.assertEqual(broker_url(), "tcp://127.0.0.1:1883")

    def test_split_broker_url(self):
        self.assertEqual(split_broker_url("tcp://10.10.11.1:1883"),
                         ("10.10.11.1", 1883))


class TestMqttCommands(unittest.TestCase):
    def test_all_planned_actions_accepted(self):
        for action in ("start_service", "stop_service", "reboot", "poweroff"):
            command = build_command(action)
            self.assertEqual(command["action"], action)
            self.assertTrue(command["request_id"])
            self.assertEqual(command["issued_by"], "controller")

    def test_unknown_action_rejected(self):
        with self.assertRaises(ValueError):
            build_command("self_destruct")

    def test_encode_decode_round_trip(self):
        command = decode_command(encode_command("stop_service"))
        self.assertEqual(command["action"], "stop_service")

    def test_decode_rejects_unknown_action(self):
        with self.assertRaises(ValueError):
            decode_command(json.dumps({"action": "halt",
                                       "request_id": "x"}))

    def test_decode_rejects_missing_request_id(self):
        with self.assertRaises(ValueError):
            decode_command(json.dumps({"action": "reboot"}))

    def test_only_reboot_and_poweroff_are_one_way(self):
        self.assertEqual(set(ONE_WAY_ACTIONS), {"reboot", "poweroff"})
        for action in ACTIONS:
            self.assertEqual(is_one_way(action),
                             action in ("reboot", "poweroff"))


if __name__ == "__main__":
    unittest.main()
