import socket
import subprocess

from plantimager.commons.mqtt_utils import (
    POWEROFF,
    REBOOT,
    START_SERVICE,
    STOP_SERVICE,
    broker_url,
    decode_command,
    fleet_topic,
    topic_for,
)

CAMERA_SERVICE = "picamera-server.service"


def command_argv(action):
    if action == START_SERVICE:
        return ["systemctl", "--user", "start", CAMERA_SERVICE]
    if action == STOP_SERVICE:
        return ["systemctl", "--user", "stop", CAMERA_SERVICE]
    if action == REBOOT:
        return ["systemctl", "reboot"]
    if action == POWEROFF:
        return ["systemctl", "poweroff"]
    raise ValueError(f"Unknown MQTT action: {action!r}")


def apply_command(command):
    argv = command_argv(command["action"])
    print(f"mqtt_agent: {command['action']} ({command['request_id']})"
          f" -> {' '.join(argv)}", flush=True)
    subprocess.check_call(argv)


def split_broker(url):
    address = url.split("://", 1)[-1]
    host, _, port = address.rpartition(":")
    return host, int(port)


def run(hostname=None, broker=None):
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

    host, port = split_broker(broker or broker_url())
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(host, port, keepalive=60)
    client.loop_forever()


def main():
    run()


if __name__ == "__main__":
    main()
