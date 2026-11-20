"""Install the controller units and the MQTT broker config.

Covers the controller Pi (not the webui package, which is optional and
has its own ``plant-imager-webui-setup``): the app ``--user`` unit plus
system-wide mosquitto (apt + ``/etc/mosquitto/conf.d/``). Run as the
target user with sudo privileges. A ``scripts/`` helper calls this and
the webui installer together; see ``scripts/controller_stack_setup.py``.
"""

import argparse
import getpass
import os
import sys
import tempfile
from importlib import resources

from plantimager.commons.systemd_install import enable_user_units
from plantimager.commons.systemd_install import replace_line
from plantimager.commons.systemd_install import run
from plantimager.commons.systemd_install import user_unit_dir

CONTROLLER_SERVICES = "plantimager.controller.services"
MOSQUITTO_CONF_TARGET = "/etc/mosquitto/conf.d/plant-imager.conf"

APP_UNIT = "plant-imager-app.service"


def render_app_unit(python_bin: str) -> str:
    """Fill the controller app unit template."""
    template = resources.files(CONTROLLER_SERVICES).joinpath(APP_UNIT).read_text()
    return replace_line(
        template, "ExecStart=",
        f"ExecStart={python_bin}/plant-imager-controller-app")


def install_mosquitto(args, dry_run: bool = False) -> None:
    """Install mosquitto and deploy the broker config (needs sudo)."""
    run(["sudo", "apt", "install", "-y", "mosquitto"], dry_run)
    conf = resources.files(CONTROLLER_SERVICES).joinpath("mosquitto.conf").read_text()
    print(f"write {MOSQUITTO_CONF_TARGET}")
    if not dry_run:
        with tempfile.NamedTemporaryFile("w", suffix=".conf",
                                         delete=False) as tmp:
            tmp.write(conf)
        run(["sudo", "cp", tmp.name, MOSQUITTO_CONF_TARGET], dry_run)
        os.remove(tmp.name)
    run(["sudo", "systemctl", "restart", "mosquitto"], dry_run)
    run(["sudo", "systemctl", "enable", "mosquitto"], dry_run)


def install(args) -> int:
    """Install or remove the controller unit described by ``args``."""
    unit_dir = user_unit_dir(args.user)
    if not os.path.isdir(os.path.join("/home", args.user)):
        print(f"ERROR: no directory /home/{args.user} found", file=sys.stderr)
        return 1
    if args.remove:
        path = os.path.join(unit_dir, APP_UNIT)
        print(f"- {path}")
        if not args.dry_run and os.path.exists(path):
            os.remove(path)
        run(["systemctl", "--user", "daemon-reload"], args.dry_run)
        return 0
    if not args.skip_mosquitto:
        install_mosquitto(args, args.dry_run)
    content = render_app_unit(args.python_bin)
    path = os.path.join(unit_dir, APP_UNIT)
    print(f"write {path}")
    if not args.dry_run:
        os.makedirs(unit_dir, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
    enable_user_units([APP_UNIT], args.user, args.start, args.dry_run)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Install the controller unit and MQTT broker.")
    parser.add_argument("--user", default=getpass.getuser(),
                        help="login user to install for (default: current user)")
    parser.add_argument("--python-bin", default=None,
                        help="venv bin dir with the console scripts "
                             "(default: /home/<user>/miniconda3/envs/plant-imager/bin)")
    parser.add_argument("--skip-mosquitto", action="store_true",
                        help="skip the mosquitto install and config")
    parser.add_argument("--start", action="store_true",
                        help="start the units after enabling them")
    parser.add_argument("--remove", action="store_true",
                        help="remove the units instead of installing them")
    parser.add_argument("--dry-run", action="store_true",
                        help="print actions without touching the system")
    return parser


def main(argv=None) -> None:
    """Entry point for the ``plant-imager-controller-setup`` script."""
    args = build_parser().parse_args(argv)
    if args.python_bin is None:
        args.python_bin = (f"/home/{args.user}/miniconda3/envs/plant-imager/bin")
    raise SystemExit(install(args))


if __name__ == "__main__":
    main()
