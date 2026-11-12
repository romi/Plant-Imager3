# How to install the services on a picamera

Preferred: the `picamera-install` entry point (ships with the
`plantimager.picamera` package, so it works from any checkout or wheel —
no repo-relative paths). Both units are system units, so sudo is required:

```shell
sudo picamera-install --user romi --registry tcp://10.10.11.1:5555 --ip 10.10.11.13 --start
```

The agent runs as root (only root can reboot/poweroff on MQTT command);
the camera server runs as `--user` via its `User=` directive.

Useful flags: `--broker tcp://10.10.11.1:26400` (lifecycle agent broker),
`--remove` (uninstall the units), `--dry-run` (print actions only).

What it does, matching the previous manual steps:

1) Writes `picamera-server.service` and `picamera-mqtt-agent.service`
   (templated with your user/registry/IP/broker) to `/etc/systemd/system`
2) Reloads units with `systemctl daemon-reload`
3) Enables (and with `--start`, starts) both services

To access the journal:

```shell
journalctl -u picamera-server
```

To view in tail mode (real-time update) -f:

```shell
journalctl -u picamera-server -f -n 50
```

Same for the agent: replace `picamera-server` with `picamera-mqtt-agent`.
