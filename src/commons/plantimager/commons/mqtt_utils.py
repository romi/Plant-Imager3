"""Shared MQTT topic and payload helpers for picamera lifecycle control.

This module is the single source of truth for the contract between the
controller side (``plantimager.controller.mqtt_bridge.MqttBridge``) and the
pi side (``plantimager.picamera.mqtt_agent``). Both import from here, so any
change to topics, actions, or the payload schema lands on both ends at once.

Power model
-----------
Two action classes share one topic per camera:

- Recoverable: ``restart_service`` restarts the ``picamera-server``
  service — including from the stopped state, so it recovers from any
  state without rebooting. The agent itself is never managed, so it
  keeps listening. There is deliberately no bare stop: a stopped
  camera disappears from the controller GUI, leaving only a fleet
  restart able to bring it back.
- One-way: ``reboot`` / ``poweroff`` take the whole Pi down. Nothing
  listens afterwards, so recovery is a manual power-cycle (wake-on-LAN is
  a separate, later plan). Use :func:`is_one_way` to tell them apart
  before wiring a button to them.

Topic design
------------
``plantimager/picamera/<hostname>/command`` (QoS 1) addresses one camera,
where ``<hostname>`` is the Pi's ``socket.gethostname()`` — the same
identity it registers with in the ZMQ device registry. The reserved
hostname ``all`` (see :data:`FLEET_HOSTNAME`) broadcasts to the fleet,
including the one-way actions.

Payload schema
--------------
Plain JSON, no credentials: the broker only listens on the isolated USB
gadget network (see ``mosquitto.conf``), so authentication would add
nothing. Every command is ``{"action", "request_id", "issued_by"}``;
``request_id`` defaults to a random hex token so repeated deliveries of
the same MQTT packet can be told apart in logs.

Dependency rule
---------------
Importing this module must never require ``paho-mqtt``. The Qt bridge and
the pi-side agent depend on it; plain library code (and their unit tests)
must stay importable without a broker client installed.
"""

import json
import os
import uuid

BROKER_ENV_VAR = "MQTT_BROKER"
BROKER_DEFAULT_HOST = "10.10.11.1"
BROKER_DEFAULT_PORT = 26400

TOPIC_ROOT = "plantimager/picamera"
FLEET_HOSTNAME = "all"

RESTART_SERVICE = "restart_service"
REBOOT = "reboot"
POWEROFF = "poweroff"

ACTIONS = (RESTART_SERVICE, REBOOT, POWEROFF)
ONE_WAY_ACTIONS = (REBOOT, POWEROFF)


def broker_url():
    """Broker URL for paho, overridable for tests and bench setups.

    Returns
    -------
    str
        The value of the ``MQTT_BROKER`` environment variable when set,
        else ``tcp://10.10.11.1:26400`` (the controller on the USB bridge).
    """
    return os.environ.get(BROKER_ENV_VAR,
                          f"tcp://{BROKER_DEFAULT_HOST}:{BROKER_DEFAULT_PORT}")


def split_broker_url(url):
    """Split a ``tcp://host:port`` broker URL for ``paho``.

    Parameters
    ----------
    url : str
        Broker URL as returned by :func:`broker_url`.

    Returns
    -------
    tuple[str, int]
        ``(host, port)`` pair suitable for ``client.connect(host, port)``.
    """
    address = url.split("://", 1)[-1]
    host, _, port = address.rpartition(":")
    return host, int(port)


def topic_for(hostname):
    """Command topic for one camera.

    Parameters
    ----------
    hostname : str
        The camera Pi's hostname (see :func:`fleet_topic` for ``"all"``).

    Returns
    -------
    str
        E.g. ``plantimager/picamera/picamera1/command``.
    """
    return f"{TOPIC_ROOT}/{hostname}/command"


def fleet_topic():
    """Command topic reaching every camera at once.

    Returns
    -------
    str
        ``plantimager/picamera/all/command``. Broadcasts include the
        one-way actions, so publishers must confirm them explicitly.
    """
    return topic_for(FLEET_HOSTNAME)


def build_command(action, issued_by="controller", request_id=None):
    """Build a validated command dict ready for :func:`encode_command`.

    Parameters
    ----------
    action : str
        One of :data:`ACTIONS`.
    issued_by : str, optional
        Free-form origin label kept for logs and debugging.
    request_id : str, optional
        Caller-supplied idempotency token; a random hex token is
        generated when omitted.

    Returns
    -------
    dict
        ``{"action", "request_id", "issued_by"}``.

    Raises
    ------
    ValueError
        If ``action`` is not one of :data:`ACTIONS`.
    """
    if action not in ACTIONS:
        raise ValueError(f"Unknown MQTT action: {action!r}")
    return {
        "action": action,
        "request_id": request_id or uuid.uuid4().hex,
        "issued_by": issued_by,
    }


def encode_command(action, issued_by="controller", request_id=None):
    """Build a command and serialize it to its on-the-wire JSON form.

    Parameters
    ----------
    action, issued_by, request_id :
        See :func:`build_command`.

    Returns
    -------
    str
        JSON payload to publish on the camera's command topic.

    Raises
    ------
    ValueError
        If ``action`` is not one of :data:`ACTIONS`.
    """
    return json.dumps(build_command(action, issued_by, request_id))


def decode_command(payload):
    """Parse and validate an incoming command payload.

    Parameters
    ----------
    payload : str, bytes or bytearray
        Raw MQTT message payload.

    Returns
    -------
    dict
        The validated ``{"action", "request_id", "issued_by"}`` dict.
        ``issued_by`` may be absent on payloads built by hand; only
        ``action`` and ``request_id`` are enforced.

    Raises
    ------
    ValueError
        If the payload is not JSON, not an object, carries an unknown
        action, or misses ``request_id``.
    """
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
    """Whether an action leaves nothing listening afterwards.

    Parameters
    ----------
    action : str
        One of :data:`ACTIONS`.

    Returns
    -------
    bool
        True for ``reboot`` and ``poweroff``: after those, no MQTT
        command can reach the Pi again until it is powered back on.
    """
    return action in ONE_WAY_ACTIONS
