#!/usr/bin/env python3
"""
controller_shared_setup.py
--------------------------

Configure the Raspberry Pi 4 to act as the USB‑ethernet controller:

* Create a NetworkManager *shared* connection on interface usb0
  (static address 10.10.11.1/24, DHCP handed out by dnsmasq).
* (Optionally) add a static‑lease file for known picamera MACs.
* Restart NetworkManager so the changes take effect.

Run as root:
    sudo python3 controller_shared_setup.py
"""

import subprocess
import sys
from pathlib import Path
import argparse

# ----------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------
NM_IFACE = "*"  # slave (wild‑card) interface selector
BRIDGE_IFACE = "br-usb0"  # actual bridge device name
BRIDGE_NAME = "usb-bridge"
SLAVE_NAME = "usb-slave"

LEASES_DIR = Path("/etc/NetworkManager/dnsmasq-shared.d")
STATIC_LEASES = LEASES_DIR / "10-static-leases.conf"

# ----------------------------------------------------------------------
# Helper
# ----------------------------------------------------------------------
def run(cmd: list[str]) -> None:
    """Run a command, raise on error, and echo it."""
    print(f"+ {' '.join(cmd)}")
    subprocess.check_call(cmd)


def connection_exists(name: str) -> bool:
    """Return True if a NetworkManager connection with *name* already exists."""
    result = subprocess.run(
        ["nmcli", "-t", "-f", "NAME", "connection", "show", name],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    return result.returncode == 0 and result.stdout.strip() == name


def add_static_lease(mac: str, ip: str) -> None:
    """Append a static DHCP lease for *mac* → *ip* to the lease file."""
    lease_line = f"dhcp-host={mac},{ip},12h\n"
    if STATIC_LEASES.exists():
        # Prevent duplicate entries
        existing = STATIC_LEASES.read_text()
        if mac in existing:
            print(f"⚠️  Lease for MAC {mac} already present – aborting.")
            sys.exit(1)
    else:
        # Ensure directory exists and write a header comment
        LEASES_DIR.mkdir(parents=True, exist_ok=True)
        STATIC_LEASES.write_text(
            "# Static DHCP reservations for USB‑Ethernet gadgets\n"
        )
        print(f"Created lease file at {STATIC_LEASES}")

    with STATIC_LEASES.open("a") as f:
        f.write(lease_line)
    print(f"Added static lease: {lease_line.strip()}")


# ----------------------------------------------------------------------
# Argument parsing
# ----------------------------------------------------------------------
parser = argparse.ArgumentParser(
    description="Setup or modify the USB‑ethernet controller NetworkManager connection."
)
parser.add_argument(
    "--controller-ip", help="IP address for the connection with subnet mask (e.g. 10.10.10.1/24)"
)
parser.add_argument(
    "--mac", help="MAC address for the static DHCP lease (e.g. de:ad:be:ef:00:01)"
)
parser.add_argument(
    "--ip", help="IP address to assign to the MAC (e.g. 10.10.11.42)"
)
parser.add_argument(
    "-u",
    "--update",
    action="store_true",
    help="Only add a new static lease; fail if the connection already exists.",
)
parser.add_argument(
    "--remove",
    action="store_true",
    help="Delete the NetworkManager connection and exit.",
)

if __name__ == "__main__":
    args = parser.parse_args()
    SHARED_ADDR = args.controller_ip

    # ----------------------------------------------------------------------
    # Main logic
    # ----------------------------------------------------------------------
    if args.remove:
        # Remove both the bridge and the slave connection if they exist
        for conn in (BRIDGE_NAME, SLAVE_NAME):
            if connection_exists(conn):
                run(["nmcli", "connection", "delete", conn])
                print(f"Removed NetworkManager connection '{conn}'.")
            else:
                print(f"No connection named '{conn}' found – nothing to remove.")
        sys.exit(0)

    # Require IP of the network if creating the connection.
    if not args.controller_ip:
        print("  --controller-ip is required when not using --update or --remove.")
        sys.exit(1)

    # Normal installation mode – fail if either profile already exists
    if connection_exists(BRIDGE_NAME) or connection_exists(SLAVE_NAME):
        print(
            f"⚠️  One of the required connections ('{BRIDGE_NAME}' or '{SLAVE_NAME}') already exists. "
            "Use --remove to delete them first, or adjust the script."
        )
        sys.exit(1)

    # ----------------------------------------------------------------------
    # 3. Create the bridge connection (shared IPv4, address on br‑usb0)
    # ----------------------------------------------------------------------
    run([
        "nmcli", "connection", "add", "type", "bridge",
        "ifname", BRIDGE_IFACE,
        "con-name", BRIDGE_NAME,
        "connection.autoconnect", "yes",
        "ipv4.method", "shared",
        "ipv4.addresses", SHARED_ADDR,
        "ipv6.method", "disabled"
    ])

    # ----------------------------------------------------------------------
    # 4. Create the wildcard slave connection that attaches to the bridge
    # ----------------------------------------------------------------------
    run([
        "nmcli", "connection", "add", "type", "ethernet",
        "ifname", NM_IFACE,  # matches any unhandled Ethernet interface
        "master", BRIDGE_IFACE,
        "slave-type", "bridge",
        "con-name", SLAVE_NAME,
        "connection.autoconnect", "yes",
        "connection.autoconnect-priority", "-999",  # low priority – bridge wins if specific config exists
        "connection.multi-connect", "multiple",
    ])

    # ----------------------------------------------------------------------
    # 4. (Optional) Add static DHCP lease for the provided MAC/IP
    # ----------------------------------------------------------------------
    if args.mac and args.ip:
        add_static_lease(args.mac, args.ip)
    else:
        # No lease requested – ensure the lease directory exists (for later use)
        LEASES_DIR.mkdir(parents=True, exist_ok=True)
        if not STATIC_LEASES.exists():
            example_entry = (
                "# Static DHCP reservations for USB‑Ethernet gadgets\n"
                "# dhcp-host=de:ad:be:ef:00:01,10.10.11.11,picamera1,12h\n"
            )
            STATIC_LEASES.write_text(example_entry)
            print(f"Created example static‑lease file at {STATIC_LEASES}")
        else:
            print(f"Static‑lease file already exists – edit {STATIC_LEASES} manually if needed")

    # ----------------------------------------------------------------------
    # 5. Restart NetworkManager so dnsmasq picks up the new config
    # ----------------------------------------------------------------------
    run(["systemctl", "restart", "NetworkManager"])

    # ----------------------------------------------------------------------
    # 6. Bring the shared connection up (useful when the script is run on a
    #    running system without a reboot)
    # ----------------------------------------------------------------------
    run(["nmcli", "connection", "up", BRIDGE_NAME])
    run(["nmcli", "connection", "up", SLAVE_NAME])

    print("\n✅ Controller configuration completed. The USB‑gadget clients should now receive"
          "\n   an IP address from 10.10.11.2‑10.10.11.254 and use 10.10.11.1 as gateway.")