"""Shared MQTT topic and payload helpers for picamera lifecycle control.

The broker runs on the controller Pi, reachable only over the isolated USB
gadget network, so payloads are plain JSON and carry no credentials.
Only topic construction and payload validation live here on purpose:
importing this module must never require ``paho-mqtt`` (the Qt bridge and
the pi-side agent depend on it, plain library code must not).
"""

import json
import os
import uuid

BROKER_ENV_VAR = "MQTT_BROKER"
BROKER_DEFAULT_HOST = "10.10.11.1"
BROKER_DEFAULT_PORT = 1883

TOPIC_ROOT = "plantimager/picamera"
FLEET_HOSTNAME = "all"

START_SERVICE = "start_service"
STOP_SERVICE = "stop_service"
REBOOT = "reboot"
POWEROFF = "poweroff"

ACTIONS = (START_SERVICE, STOP_SERVICE, REBOOT, POWEROFF)
ONE_WAY_ACTIONS = (REBOOT, POWEROFF)


def broker_url():
    return os.environ.get(BROKER_ENV_VAR,
                          f"tcp://{BROKER_DEFAULT_HOST}:{BROKER_DEFAULT_PORT}")


def topic_for(hostname):
    return f"{TOPIC_ROOT}/{hostname}/command"


def fleet_topic():
    return topic_for(FLEET_HOSTNAME)


def build_command(action, issued_by="controller", request_id=None):
    if action not in ACTIONS:
        raise ValueError(f"Unknown MQTT action: {action!r}")
    return {
        "action": action,
        "request_id": request_id or uuid.uuid4().hex,
        "issued_by": issued_by,
    }


def encode_command(action, issued_by="controller", request_id=None):
    return json.dumps(build_command(action, issued_by, request_id))


def decode_command(payload):
    if isinstance(payload, (bytes, bytearray)):
        payload = payload.decode("utf-8")
    command = json.loads(payload)
    if not isinstance(command, dict):
        raise ValueError(f"MQTT command must be an object, got {command!r}")
    if command.get("action") not in ACTIONS:
        raise ValueError(f"Unknown MQTT action: {command.get('action')!r}")
    if not command.get("request_id"):
        raise ValueError(f"MQTT command misses request_id: {command!r}")
    return command


def is_one_way(action):
    return action in ONE_WAY_ACTIONS
