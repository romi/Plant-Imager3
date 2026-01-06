# Chrony NTP Server

## Overview

Accurate time is the backbone of logging, scheduled jobs, and many network services.  
This guide walks you through:
1. setting up a **Chrony** NTP server on a host connected to the internet.
2. setting up a **Chrony** NTP client on a Raspberry Pi to sync with it.
3. setting up a **Chrony** NTP server on the same Raspberry Pi.
4. setting up a **systemd-timesyncd** NTP client on a Pi Zero W to sync with it.

## 2. Set Up the NTP Server (Chrony)

### 2.1 Install Chrony

```bash
sudo apt install chrony nano
```

### 2.2 Configure the Server

1. Open the Chrony configuration filew with `nano`:
   ```bash
   sudo nano /etc/chrony/chrony.conf
   ```

2. Add a line that tells Chrony which clients are allowed to query it.  
   Replace `<client_ip>` with the Pi’s static IP or a subnet (e.g., `192.168.1.0/24`):
   ```text
   allow <client_ip>
   ```
   > `allow` restricts access; only IPs that match this line will be served.

3. Save the file <kbd>Ctrl</kbd> + <kbd>O</kbd> and exit the editor <kbd>Ctrl</kbd> + <kbd>X</kbd>.

### 2.3 Restart Chrony

```bash
sudo systemctl restart chrony
```

### 2.4 Verify the Server

```bash
chronyc tracking
```

You should see a "Reference ID" pointing to an external time source (e.g., `0.pool.ntp.org`).  
If it’s blank or shows "unknown", double‑check your internet connection and the `allow` rule.

## 3. Configure the Main Raspberry Pi (Client)

### 3.1 Install Chrony (if not already installed)

```bash
sudo apt install chrony
```

### 3.2 Tell Chrony to Use the Server

1. Create a dedicated source file:

   ```bash
   sudo nano /etc/chrony/sources.d/local-ntp-server.sources
   ```

2. Add the following line, replacing `<server_ip>` with the host’s IP:

   ```text
   server <server_ip> iburst
   ```

   > `iburst` accelerates the initial sync by sending a burst of packets.

3. Reload Chrony’s sources:

   ```bash
   sudo chronyc reload sources
   ```

### 3.3 Check Synchronization Status

```bash
timedatectl status
```

Look for  "System clock synchronized: yes ".  
If it says  "no ", run `chronyc tracking` again to see any error messages.

## 4. Configure the Main Raspberry Pi (Server)

Hereafter we assume the Main Raspberry Pi to act as an Access Point to the Raspberry Pi Zero.
They thus connect to a subnet like `10.10.10.0/24` 

1. Open the Chrony configuration filew with `nano`:
   ```bash
   sudo nano /etc/chrony/chrony.conf
   ```

2. Add a line that tells Chrony which clients are allowed to query it.
   ```text
   allow 10.10.10.0/24
   ```

3. Save the file <kbd>Ctrl</kbd> + <kbd>O</kbd> and exit the editor <kbd>Ctrl</kbd> + <kbd>X</kbd>.

4. Restart Chrony
   ```bash
   sudo systemctl restart chrony
   ```

5. Verify the Server
   ```bash
   chronyc tracking
   ```

## 5. Configure Pi Zero W Clients (systemd-timesyncd)

Pi Zero W devices can keep time with the `systemd-timesyncd` service, which is lighter than Chrony.

### 5.1 Edit the timesyncd Configuration

```bash
sudo nano /etc/systemd/timesyncd.conf
```

Add or modify the `[Time]` section:

```conf
[Time]
NTP=<server_ip>
FallbackNTP=0.debian.pool.ntp.org 1.debian.pool.ntp.org 2.debian.pool.ntp.org 3.debian.pool.ntp.org
RootDistanceMaxSec=5
PollIntervalMinSec=32
PollIntervalMaxSec=2048
```

- Replace `<server_ip>` with your Chrony server’s IP or hostname.
- The `FallbackNTP` list is used only if the server is unreachable.

### 5.2 Restart the Service

```bash
sudo systemctl restart systemd-timesyncd
```

### 5.3 Verify

```bash
timedatectl status
```

You should again see "System clock synchronized: yes".


## 6. Quick Troubleshooting

| Symptom                             | Likely Cause                      | Fix                                                                  |
|-------------------------------------|-----------------------------------|----------------------------------------------------------------------|
| `chronyc tracking` shows  "unknown" | No upstream NTP server configured | Check the `server` line in `chrony.conf` or `/etc/chrony/sources.d/` |
| Clients cannot sync                 | Wrong `allow` rule                | Ensure the IP or subnet in `chrony.conf` matches the client          |
| `systemd-timesyncd` fails           | Wrong NTP address                 | Verify the `NTP=` entry in `timesyncd.conf`                          |


## 7. Summary Checklist

1. Host: `sudo apt install chrony` 
2. Host: Add `allow <client_ip>` to `/etc/chrony/chrony.conf` 
3. Host: `sudo systemctl restart chrony` & `chronyc tracking` 
4. RPi Client: `sudo apt install chrony` 
5. RPi Client: Create `/etc/chrony/sources.d/local-ntp-server.sources` with `server <server_ip> iburst` 
6. RPi Client: `sudo chronyc reload sources` 
7. RPi Server: Add `allow 10.10.10.0/24` to `/etc/chrony/chrony.conf`
8. RPi Server: `sudo systemctl restart chrony` & `chronyc tracking`
9. Zero W: Edit `/etc/systemd/timesyncd.conf` with `NTP=<server_ip>`
10. Zero W: `sudo systemctl restart systemd-timesyncd`
11. All devices: `timedatectl status` → "System clock synchronized: yes"

Happy time‑keeping!