# How to install the services on a picamera

Preferred: the `picamera-install` entry point (ships with the
`plantimager.picamera` package, so it works from any checkout or wheel —
no repo-relative paths):

```shell
picamera-install --user romi --registry tcp://10.10.11.1:5555 --ip 10.10.11.13 --start
```

Useful flags: `--broker tcp://10.10.11.1:26400` (lifecycle agent broker),
`--remove` (uninstall the units), `--dry-run` (print actions only).

What it does, matching the previous manual steps:

1) Writes `picamera-server.service` and `picamera-mqtt-agent.service`
   (templated with your registry/IP/broker) to `/home/romi/.config/systemd/user`
2) Enables linger for the user with `loginctl enable-linger romi`
3) Reloads units `systemctl --user daemon-reload`
4) Enables (and with `--start`, starts) both services

To access the journal:

```shell
journalctl -a --user -u picamera-server
```

To view in tail mode (real-time update) -f:

```shell
journalctl -a --user -u picamera-server -f -n 50
```

Same for the agent: replace `picamera-server` with `picamera-mqtt-agent`.
