"""Install the picamera systemd system units from the packaged templates.

Replaces the ``cp``/``sed`` block of ``system-config/picamera/scripts/
install_picamera.sh`` (which keeps doing system setup: apt, venv, clone,
pip) with unit files resolved from this package, so installs work from
any checkout or installed wheel — never from a repo-relative path.

Both units are system units in ``/etc/systemd/system`` (sudo required):
the agent runs as root so ``reboot``/``poweroff`` work, while the
camera server keeps the login user's permissions via ``User=``.
"""

import argparse
import getpass
import os
import sys
from importlib import resources

from plantimager.commons.mqtt_utils import BROKER_DEFAULT_HOST
from plantimager.commons.mqtt_utils import BROKER_DEFAULT_PORT
from plantimager.commons.systemd_install import SYSTEM_UNIT_DIR
from plantimager.commons.systemd_install import enable_system_units
from plantimager.commons.systemd_install import replace_line
from plantimager.commons.systemd_install import run

SERVICES_PACKAGE = "plantimager.picamera.services"
VENV = "picamera-env"

#: Unit file -> console script it starts.
UNIT_ENTRIES = {
    "picamera-server.service": "picamera-server",
    "picamera-mqtt-agent.service": "picamera-mqtt-agent",
}

BROKER_DEFAULT = f"tcp://{BROKER_DEFAULT_HOST}:{BROKER_DEFAULT_PORT}"
REGISTRY_DEFAULT = "tcp://10.10.11.1:5555"


def render_unit(template: str, user: str, entry: str, env: dict) -> str:
    """Fill user-specific paths and environment into a unit template.

    Parameters
    ----------
    template : str
        Unit file text as shipped in :data:`SERVICES_PACKAGE`.
    user : str
        Target login user (owns ``/home/<user>`` and the venv; runs the
        camera server via its ``User=`` directive).
    entry : str
        Console script name, see :data:`UNIT_ENTRIES`.
    env : dict
        ``Environment=`` overrides, e.g. ``{"PI_REGISTRY": ...}``.

    Returns
    -------
    str
        Rendered unit with no template leftovers. The agent keeps its
        template ``User=root``; only the server placeholder
        (``User=romi``) is repointed.
    """
    rendered = replace_line(
        template, "ExecStart=", f"ExecStart=/home/{user}/{VENV}/bin/{entry}")
    rendered = replace_line(
        rendered, "WorkingDirectory=", f"WorkingDirectory=/home/{user}")
    rendered = replace_line(rendered, "User=romi", f"User={user}")
    for key, value in env.items():
        rendered = replace_line(
            rendered, f"Environment={key}=", f"Environment={key}={value}")
    return rendered


def template(name: str) -> str:
    """Read a unit template from the package data."""
    return resources.files(SERVICES_PACKAGE).joinpath(name).read_text()


def install(args) -> int:
    """Install or remove the units described by parsed ``args``."""
    if os.geteuid() != 0 and not args.dry_run:
        print("ERROR: picamera-install writes to /etc/systemd/system, "
              "run it with sudo", file=sys.stderr)
        return 1
    if not os.path.isdir(os.path.join("/home", args.user)):
        print(f"ERROR: no directory /home/{args.user} found", file=sys.stderr)
        return 1
    if args.remove:
        for name in UNIT_ENTRIES:
            path = os.path.join(SYSTEM_UNIT_DIR, name)
            print(f"- {path}")
            if not args.dry_run and os.path.exists(path):
                os.remove(path)
        run(["systemctl", "daemon-reload"], args.dry_run)
        return 0
    if not args.dry_run:
        os.makedirs(SYSTEM_UNIT_DIR, exist_ok=True)
    registry = args.registry or REGISTRY_DEFAULT
    server_env = {"PI_REGISTRY": registry}
    if args.ip:
        server_env["IP_ADDR"] = args.ip
    envs = {
        "picamera-server.service": server_env,
        "picamera-mqtt-agent.service": {"MQTT_BROKER": args.broker},
    }
    for name, entry in UNIT_ENTRIES.items():
        content = render_unit(template(name), args.user, entry, envs[name])
        path = os.path.join(SYSTEM_UNIT_DIR, name)
        print(f"write {path}")
        if not args.dry_run:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(content)
    enable_system_units(list(UNIT_ENTRIES), args.start, args.dry_run)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Install the picamera systemd system units (sudo required).")
    parser.add_argument("--user", default=getpass.getuser(),
                        help="login user to install for (default: current user)")
    parser.add_argument("--registry", default=REGISTRY_DEFAULT,
                        help="registry address, e.g. tcp://10.10.11.1:5555")
    parser.add_argument("--ip", default=None,
                        help="IP address of this camera")
    parser.add_argument("--broker", default=BROKER_DEFAULT,
                        help="MQTT broker URL for the lifecycle agent")
    parser.add_argument("--start", action="store_true",
                        help="start the units after enabling them")
    parser.add_argument("--remove", action="store_true",
                        help="remove the units instead of installing them")
    parser.add_argument("--dry-run", action="store_true",
                        help="print actions without touching the system")
    return parser


def main(argv=None) -> None:
    """Entry point for the ``picamera-install`` console script."""
    raise SystemExit(install(build_parser().parse_args(argv)))


if __name__ == "__main__":
    main()
