#!/usr/bin/env python3
"""
picamera_gadget_setup.py
------------------------

Configure a Pi Zero 2 W to act as a USB‑ethernet (g_ether) gadget
and create the NetworkManager client profile for the virtual
interface *usb0*.

Run as root:
    sudo python3 picamera_gadget_setup.py
"""

import os
import random
import subprocess
from pathlib import Path

# ----------------------------------------------------------------------
# Helper utilities
# ----------------------------------------------------------------------
def run(cmd: list[str]) -> None:
    """Run a command, raise on error, and print it for visibility."""
    print(f"+ {' '.join(cmd)}")
    subprocess.check_call(cmd)


def random_locally_admin_unicast() -> str:
    """Return a valid locally‑administered unicast MAC address."""
    mac = [random.randint(0x00, 0xFF) for _ in range(6)]
    mac[0] = (mac[0] & 0b11111100) | 0b00000010   # set LAA + unicast bits
    return ":".join(f"{b:02x}" for b in mac)


# ----------------------------------------------------------------------
# 1. Load the required kernel modules (immediate effect)
# ----------------------------------------------------------------------
run(["modprobe", "dwc2"])
run(["modprobe", "g_ether"])

# ----------------------------------------------------------------------
# 2. Ensure the modules are loaded on every boot
# ----------------------------------------------------------------------
modules_conf = Path("/etc/modules-load.d/usb-gadget.conf")
modules_conf.write_text("dwc2\ng_ether\n")
print(f"Wrote persistent module list to {modules_conf}")

# ----------------------------------------------------------------------
# 3. Create fixed MAC addresses (optional but helpful for static DHCP)
# ----------------------------------------------------------------------
# You may replace the generated MACs with your own static values.
gadget_mac = random_locally_admin_unicast()
# The controller MAC is unknown now – leave it blank (0:0:0:0:0:0) and
# let the controller set the host_addr later if needed.
host_mac = random_locally_admin_unicast()

modprobe_conf = Path("/etc/modprobe.d/g_ether.conf")
modprobe_conf.write_text(
    f"options g_ether host_addr={host_mac} dev_addr={gadget_mac}\n"
)
print(f"====>>> Generated MAC for this gadget: {gadget_mac}")
print(f"====>>> Generated MAC for the host: {host_mac}")
print(f"Wrote {modprobe_conf}")

# ----------------------------------------------------------------------
# 4. Enable the peripheral overlay (dr_mode=peripheral)
# ----------------------------------------------------------------------
config_txt = Path("/boot/firmware/config.txt")
overlay_line = "dtoverlay=dwc2,dr_mode=peripheral\n"
if config_txt.read_text().find(overlay_line.strip()) == -1:
    with config_txt.open("a") as f:
        f.write("\n" + overlay_line)
    print(f"Appended overlay line to {config_txt}")
else:
    print("Overlay line already present – skipping")

# ----------------------------------------------------------------------
# 5. Set usb0 device to managed
# ----------------------------------------------------------------------

# Ensure the interface is marked as “managed” by NM
run(["nmcli", "device", "set", "usb0", "managed", "yes"])
run(["nmcli", "device", "set", "usb0", "autoconnect", "yes"])

# Persistent “managed” rule (required after reboot)
managed_conf = Path("/etc/NetworkManager/conf.d/10-usb0-managed.conf")
managed_conf.write_text(
    "[device]\n"
    "match-device=interface-name:usb0\n"
    "managed=true\n"
)
print(f"Wrote persistent NM managed rule to {managed_conf}")

# ----------------------------------------------------------------------
# 6. Bring the connection up now (optional – will also happen on boot)
# ----------------------------------------------------------------------
#run(["nmcli", "connection", "up", CLIENT_NAME])

print("\n✅ Gadget configuration completed. Reboot the Pi for a clean start.")