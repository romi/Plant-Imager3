# Setup g_ether USB gadget mode

## Overview

The goal is to set up the picameras (Pi Zero 2w) as USB ethernet gadgets
and then connect them to the controller (Raspberry Pi 4) via USB.

The setup is as follows:
 - Controller: ip address: 10.10.11.1/24, NetworkManager shared connection on wildcard ethernet interfaces
 - picameras: ip address: auto from dhcp server, all on the same network

## Enabling **g_ether** (USB Ethernet Gadget) – client side only  

The following checklist can be run on each Pi that will act **as the USB‑gadget (client)**.  
All commands are meant to be executed **as root** (or with `sudo`).  
Only the client‑side NetworkManager profile is created – the controller will run its own DHCP server.

---

### 1. Load the kernel modules  

```shell
# Load the modules for the current session (optional – they will be loaded automatically after reboot)
modprobe dwc2
modprobe g_ether
```


*`dwc2`* provides the USB controller driver, *`g_ether`* creates the virtual Ethernet interface (`usb0`).

---

### 2. Make the modules load on every boot  

Edit (or create) **`/etc/modules-load.d/usb-gadget.conf`** with **nano**:

```shell
sudo nano /etc/modules-load.d/usb-gadget.conf
```


Add the two module names, one per line:

```
dwc2
g_ether
```


Save (`Ctrl+O`, <Enter>) and exit (`Ctrl+X`).

### 2. bis. Use fixed MAC addresses

To use fixed MAC addresses (for static dhcp leases, for instance), we will add options to the `g_ether` module
by creating (or editing if it already exists) the file `/etc/modprobe.d/g_ether.conf`

```shell
sudo nano /etc/modprobe.d/g_ether.conf
```

Inside, add the following line and replace the MAC addresses you want:
```
options g_ether host_addr=<controller_mac> dev_addr=<gadget_mac>
```

`dev_addr` will be the MAC address of the gadget, meaning the current machine.

`host_addr` will be the MAC address of the virtual interface of the machine connected to the gadget 
(i.e., the controller).

Save and exit.

#### Generating a valid MAC address

To generate a valid locally administered unicast MAC address, you need to set
the first two least significant bits of the first byte of the address to `10`.

 - `1` for locally administered
 - `0` for unicast

(see https://en.wikipedia.org/wiki/MAC_address#Ranges_of_group_and_locally_administered_addresses)

Use the following script to generate a valid MAC address:

```python
import random

def random_locally_admin_unicast():
    # generate 6 random bytes
    mac = [random.randint(0x00, 0xFF) for _ in range(6)]
    # force the two flag bits:
    #   bit 0 = 0  (unicast)
    #   bit 1 = 1  (locally administered)
    mac[0] = (mac[0] & 0b11111100) | 0b00000010
    return ':'.join(f'{b:02x}' for b in mac)

if __name__ == '__main__':
    print(random_locally_admin_unicast())
```

---

### 3. Enable the peripheral overlay  

The Raspberry Pi must be put into **gadget (peripheral) mode**.  
Edit the boot‑configuration file that matches your firmware layout.

```shell
sudo nano /boot/firmware/config.txt
```


Add (or ensure the line exists) at the **end** of the file:

```
dtoverlay=dwc2,dr_mode=peripheral
```

---

### 4. Re‑boot (or reload the overlay)  

```shell
sudo reboot
```


After the reboot you should see a new network interface called **`usb0`**:

```shell
ip link show usb0
```


If the interface exists, the gadget side is active.

---

### 5. (Optional) Create the **NetworkManager client** profile (`nmcli`)  

> If a NetworkManager connection already exists for the _usb0_ interface, skip this part

The controller will hand out an address via DHCP, so the Pi only needs a **client** profile.

```shell
# Variables (feel free to change the name)
NM_IFACE="usb0"
CLIENT_NAME="USB Gadget (client)"
CLIENT_DHCP_TIMEOUT=6          # seconds
CLIENT_ROUTE_METRIC=100        # lower metric → preferred over other interfaces
```

```shell
nmcli connection add type ethernet \
    ifname "$NM_IFACE" \
    con-name "$CLIENT_NAME" \
    connection.autoconnect yes \
    connection.autoconnect-priority 100 \
    ipv4.method auto \
    ipv4.may-fail yes \
    ipv4.route-metric "$CLIENT_ROUTE_METRIC" \
    ipv4.dhcp-timeout "$CLIENT_DHCP_TIMEOUT" \
    ipv6.method disabled
```

### 6. Set the  *usb0* device to `managed`:

```shell
nmcli device set "$NM_IFACE" managed yes
nmcli device set "$NM_IFACE" autoconnect yes
```

This will ensure the device is always managed after a reboot:
```shell
sudo tee /etc/NetworkManager/conf.d/10-usb0-managed.conf > /dev/null <<'EOF'
[device]
match-device=interface-name:usb0
managed=true
EOF
```


---

### 7. Bring the client profile up (or let a script bring it up later)  

```shell
nmcli device up usb0"
```


If the controller’s DHCP server is reachable, `usb0` will obtain an IP address (e.g. `10.10.11.x`) and you’ll see it with:

```shell
ip -4 addr show dev usb0
```


---

## TL;DR – Quick command list  

```shell
# 1. Load modules now (optional)
modprobe dwc2 && modprobe g_ether

# 2. Persist modules
echo -e "dwc2\ng_ether" | sudo tee /etc/modules-load.d/usb-gadget.conf > /dev/null

# 3. Add overlay (new firmware)
sudo bash -c 'echo "dtoverlay=dwc2,dr_mode=peripheral" >> /boot/firmware/config.txt'

# 4. Reboot
sudo reboot

# 5. After reboot – create NM client profile
NM_IFACE="usb0"

# Clean old profiles
nmcli -t -f NAME,UUID connection show | awk -F: '$1=="'"$CLIENT_NAME"'"{print $2}' | \
while read -r u; do [ -n "$u" ] && nmcli connection delete uuid "$u"; done


# Manage interface & bring up
sudo tee /etc/NetworkManager/conf.d/10-usb0-managed.conf > /dev/null <<'EOF'
[device]
match-device=interface-name:usb0
managed=true
EOF

nmcli device set "$NM_IFACE" managed yes
```



That’s all you need on the **gadget (client)** side. Once the controller’s DHCP server is running, the Pi will automatically obtain an address and be reachable over the USB cable.

## Creating a **Shared Wildcard** connection with **nmcli**
The controller (the Raspberry Pi 4 that will run the DHCP/NAT server) needs to handle incoming USB ethernet gadget
connections dynamically. To achieve this, we set up a NetworkManager **bridge** connection that acts as the shared 
gateway, along with a wildcard **bridge-slave** connection that automatically captures and attaches any unhandled 
Ethernet interfaces (like `usb0`, `usb1`, etc.) to the bridge.

All commands assume you are root (or using `sudo`).

### 1. Define Variables
```bash
BRIDGE_NAME="usb-bridge"
BRIDGE_IFACE="br-usb0"
SLAVE_NAME="usb-slave"
SLAVE_IFACE="*" # Wildcard interface selector
SHARED_ADDR="10.10.11.1/24"
```

### 2. Create the Bridge Connection
The bridge itself has the IP configuration and runs the DHCP server via NetworkManager's `shared` IPv4 method.
```bash
nmcli connection add type bridge \
    ifname "$BRIDGE_IFACE" \
    con-name "$BRIDGE_NAME" \
    connection.autoconnect yes \
    ipv4.method shared \
    ipv4.addresses "$SHARED_ADDR" \
    ipv6.method disabled
```

### 3. Create the Wildcard Slave Connection
This connection uses the `*` wildcard interface to match any available physical/virtual ethernet device, and assigns it to the bridge as a slave. Specifying `connection.multi-connect multiple` allows multiple interfaces (e.g. `usb0`, `usb1`) to join this connection simultaneously.
```bash
nmcli connection add type ethernet \
    ifname "$SLAVE_IFACE" \
    master "$BRIDGE_IFACE" \
    slave-type bridge \
    con-name "$SLAVE_NAME" \
    connection.autoconnect yes \
    connection.autoconnect-priority -999 \
    connection.multi-connect multiple
```

*Setting `connection.autoconnect-priority -999` ensures this wildcard fallback doesn't override more specific ethernet connection profiles.*

### 4. Bring the Connections Up
Restart NetworkManager to clean the state and activate both connections:
```bash
systemctl restart NetworkManager
nmcli connection up "$BRIDGE_NAME"
nmcli connection up "$SLAVE_NAME"
```

### 5. Verify the Interfaces
Verify that the bridge device is up and has the configured IP address:
```bash
ip -4 addr show dev br-usb0
```
Expected output:
```
3: br-usb0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc noqueue state UP group default qlen 1000
    inet 10.10.11.1/24 brd 10.10.11.255 scope global br-usb0
```

When gadgets are connected to the controller, they will be dynamically captured by the `usb-slave` connection, added to the `br-usb0` bridge, and automatically leased IP addresses in the `10.10.11.x` subnet.


## Assigning a static lease to a picamera

If we want to have a stable address for the picameras, we need to assign static leases.

To assign a static lease, we must add a config file to the directory `/etc/NetworkManager/dnsmasq-shared.d/`

```shell
sudo nano /etc/NetworkManager/dnsmasq-shared.d/10-static-leases.conf
```

Inside, write the following:

```
# Static DHCP reservations for USB‑Ethernet gadgets
# Syntax: dhcp-host=MAC,IP,[hostname],[lease‑time]
dhcp-host=d2:2f:1f:e9:f9:7e,10.10.11.13,picamera3,12h
```

One line per picamera, replace the mac address with the known address of picamera.

Save and exit.

For the change to take effect, restart NetworkManager.
