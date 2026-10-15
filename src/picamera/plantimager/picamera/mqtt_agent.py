"""MQTT lifecycle agent running on each picamera Pi.

The agent is a small always-on process (see
``services/picamera-mqtt-agent.service``) that subscribes to its own
command topic plus the fleet topic and translates incoming commands into
``systemctl`` calls. It deliberately manages only the
``picamera-server`` service plus whole-Pi reboot/poweroff — never
itself — so the agent keeps listening across restarts (``restart``
starts an inactive unit, so it recovers the camera from any state).

Privilege notes
---------------
``restart`` acts on a ``--user`` service and needs nothing beyond
an active user session (``loginctl enable-linger`` at install time).
``reboot``/``poweroff`` go through logind and assume the Pi runs no
other active sessions, which holds on a dedicated camera Pi.

The ``paho-mqtt`` import lives inside :func:`run` so that importing this
module (e.g. in unit tests or on machines without the broker client)
never requires the dependency.
"""

import socket
import subprocess

from plantimager.commons.mqtt_utils import (
    POWEROFF,
    REBOOT,
    RESTART_SERVICE,
    broker_url,
    decode_command,
    fleet_topic,
    split_broker_url,
    topic_for,
)

CAMERA_SERVICE = "picamera-server.service"


def command_argv(action):
    """Map a lifecycle action to its ``systemctl`` invocation.

    Parameters
    ----------
    action : str
        One of ``restart_service``, ``reboot``, ``poweroff``.

    Returns
    -------
    list[str]
        Argument vector for :func:`subprocess.check_call`. Service
        actions target the ``--user`` camera service; ``reboot`` and
        ``poweroff`` address the whole machine (one-way actions, see
        :mod:`plantimager.commons.mqtt_utils`).

    Raises
    ------
    ValueError
        If ``action`` is unknown. Callers should validate with
        :func:`~plantimager.commons.mqtt_utils.decode_command` first;
        this is the last line of defence before a shell-out.
    """
    if action == RESTART_SERVICE:
        return ["systemctl", "--user", "restart", CAMERA_SERVICE]
    if action == REBOOT:
        return ["systemctl", "reboot"]
    if action == POWEROFF:
        return ["systemctl", "poweroff"]
    raise ValueError(f"Unknown MQTT action: {action!r}")


def apply_command(command):
    """Run one decoded command, logging what it does first.

    Parameters
    ----------
    command : dict
        Validated ``{"action", "request_id", ...}`` mapping as returned
        by :func:`~plantimager.commons.mqtt_utils.decode_command`.
        The action and request id are printed before executing so the
        journal always shows which command caused a reboot or poweroff.

    Raises
    ------
    ValueError
        If the action is unknown (from :func:`command_argv`).
    subprocess.CalledProcessError
        If ``systemctl`` itself fails.
    """
    argv = command_argv(command["action"])
    print(f"mqtt_agent: {command['action']} ({command['request_id']})"
          f" -> {' '.join(argv)}", flush=True)
    subprocess.check_call(argv)


def run(hostname=None, broker=None):
    """Connect to the broker and serve commands until killed.

    Subscribes (QoS 1, re-subscribed on every reconnect) to the
    camera's own topic and the fleet topic. Each message is decoded
    and applied; anything invalid — bad JSON, unknown action, failing
    ``systemctl`` — is logged and ignored so one malformed publish
    can never take the agent down. This function blocks; under
    systemd, SIGTERM simply stops the loop.

    Parameters
    ----------
    hostname : str, optional
        Camera identity subscribed as
        ``plantimager/picamera/<hostname>/command``. Defaults to
        ``socket.gethostname()``, the same name the camera registers
        with in the ZMQ device registry.
    broker : str, optional
        ``tcp://host:port`` URL. Defaults to
        :func:`~plantimager.commons.mqtt_utils.broker_url`, i.e. the
        ``MQTT_BROKER`` environment variable or the controller.
    """
    import paho.mqtt.client as mqtt

    hostname = hostname or socket.gethostname()
    topics = (topic_for(hostname), fleet_topic())

    def on_connect(client, userdata, flags, reason, properties=None):
        for topic in topics:
            client.subscribe(topic, qos=1)
        print(f"mqtt_agent: {hostname} listening on {', '.join(topics)}",
              flush=True)

    def on_message(client, userdata, message):
        try:
            apply_command(decode_command(message.payload))
        except Exception as exc:
            print(f"mqtt_agent: ignoring {message.topic}: {exc}", flush=True)

    host, port = split_broker_url(broker or broker_url())
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(host, port, keepalive=60)
    client.loop_forever()


def main():
    """Entry point for the ``picamera-mqtt-agent`` console script."""
    run()


if __name__ == "__main__":
    main()
