"""Unit tests for the controller MQTT bridge.

The broker client is stubbed, so no mosquitto or paho-mqtt is needed:
what is verified is topic selection, payload validity, the offline-drop
behavior, and the connected flag driving the header dot.
"""

import json
import unittest

from PySide6.QtCore import QCoreApplication

from plantimager.controller.mqtt_bridge import MqttBridge


class FakeClient:
    def __init__(self):
        self.published = []

    def publish(self, topic, payload, qos=1):
        self.published.append((topic, payload, qos))


class TestMqttBridge(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance()
        if cls.app is None:
            cls.app = QCoreApplication([])

    def setUp(self):
        self.bridge = MqttBridge(client=FakeClient())

    def test_offline_publish_drops_and_returns_false(self):
        self.assertFalse(self.bridge.publishCommand("picamera1", "restart_service"))
        self.assertEqual(self.bridge._client.published, [])

    def test_publish_command_targets_own_topic_with_valid_payload(self):
        self.bridge._on_connect(None, None, None, 0)
        self.assertTrue(self.bridge.connected)
        self.assertTrue(self.bridge.publishCommand("picamera1", "restart_service"))
        [(topic, payload, qos)] = self.bridge._client.published
        self.assertEqual(topic, "plantimager/picamera/picamera1/command")
        self.assertEqual(qos, 1)
        command = json.loads(payload)
        self.assertEqual(command["action"], "restart_service")
        self.assertTrue(command["request_id"])

    def test_publish_all_targets_fleet_topic(self):
        self.bridge._on_connect(None, None, None, 0)
        self.assertTrue(self.bridge.publishAll("reboot"))
        [(topic, payload, _)] = self.bridge._client.published
        self.assertEqual(topic, "plantimager/picamera/all/command")
        self.assertEqual(json.loads(payload)["action"], "reboot")

    def test_unknown_action_refused_without_publish(self):
        self.bridge._on_connect(None, None, None, 0)
        self.assertFalse(self.bridge.publishCommand("picamera1", "halt"))
        self.assertFalse(self.bridge.publishAll("halt"))
        self.assertEqual(self.bridge._client.published, [])

    def test_disconnect_clears_connected(self):
        self.bridge._on_connect(None, None, None, 0)
        self.bridge._on_disconnect(None, None, None, 1)
        self.assertFalse(self.bridge.connected)
        self.assertFalse(self.bridge.publishCommand("picamera1", "restart_service"))

    def test_refused_connection_stays_offline(self):
        self.bridge._on_connect(None, None, None, 5)
        self.assertFalse(self.bridge.connected)


if __name__ == "__main__":
    unittest.main()
