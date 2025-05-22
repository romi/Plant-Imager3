# How to install the service to a picamera

1) Copy (or link) the service file to `/home/romi/.config/systemd/user`
2) Enable linger for user `romi` with `loginctl enable-linger romi`
3) Reload units `systemctl --user daemon-reload`
4) Enable service with `systemctl --user enable picamera-server.service`
5) Start the service with `systemctl --user start picamera-server.service`


To access the journal

```shell
journalctl -a --user -u picamera-server
```

To view in tail mode (real-time update) -f

```shell
journalctl -a --user -u picamera-server -f -n 50
```