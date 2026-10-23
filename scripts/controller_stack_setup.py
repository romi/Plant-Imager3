#!/usr/bin/env python3
"""
controller_stack_setup.py
-------------------------

Install the full controller stack by calling the per-package installers:

* ``plant-imager-controller-setup`` (controller unit + mosquitto broker)
* ``plant-imager-webui-setup`` (webui unit; skipped with a warning when
  the webui package is not installed)

Run as the target user (needs sudo privileges for the mosquitto part):

    sudo -u romi python3 controller_stack_setup.py --start
"""

import argparse
import getpass
import shutil
import subprocess
import sys


def run(cmd: list, dry_run: bool = False) -> None:
    """Run a command, raise on error, and echo it."""
    print(f"+ {' '.join(cmd)}")
    if not dry_run:
        subprocess.check_call(cmd)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Install controller + webui units and the MQTT broker.")
    parser.add_argument("--user", default=getpass.getuser(),
                        help="login user to install for (default: current user)")
    parser.add_argument("--python-bin", default=None,
                        help="venv bin dir (default: /home/<user>/miniconda3/envs/plant-imager/bin)")
    parser.add_argument("--plantdb-host",
                        default="mellitus.biologie.ens-lyon.fr")
    parser.add_argument("--plantdb-port", type=int, default=80)
    parser.add_argument("--plantdb-prefix", default="/plantdb")
    parser.add_argument("--plantdb-ssl", default="True")
    parser.add_argument("--url-prefix", default="/webui")
    parser.add_argument("--skip-mosquitto", action="store_true")
    parser.add_argument("--skip-webui", action="store_true")
    parser.add_argument("--start", action="store_true",
                        help="start the units after enabling them")
    parser.add_argument("--dry-run", action="store_true",
                        help="print actions without touching the system")
    args = parser.parse_args()

    common = ["--user", args.user]
    if args.python_bin:
        common += ["--python-bin", args.python_bin]
    if args.start:
        common.append("--start")
    if args.dry_run:
        common.append("--dry-run")

    controller = ["plant-imager-controller-setup"] + common
    if args.skip_mosquitto:
        controller.append("--skip-mosquitto")
    run(controller, args.dry_run)

    if args.skip_webui:
        return 0
    if shutil.which("plant-imager-webui-setup") is None:
        print("WARNING: plant-imager-webui-setup not found, "
              "skipping webui install (package not installed).")
        return 0
    run(["plant-imager-webui-setup"] + common + [
        "--plantdb-host", args.plantdb_host,
        "--plantdb-port", str(args.plantdb_port),
        "--plantdb-prefix", args.plantdb_prefix,
        "--plantdb-ssl", args.plantdb_ssl,
        "--url-prefix", args.url_prefix,
    ], args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
