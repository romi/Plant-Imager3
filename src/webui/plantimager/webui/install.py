"""Install the WebUI systemd user unit from the packaged template.

The webui is an optional package: this installer lives here (not in the
controller package) so controller installs never require it. A
``scripts/`` helper calls this and the controller installer together;
see ``scripts/controller_stack_setup.py``.
"""

import argparse
import getpass
import os
import sys
from importlib import resources

from plantimager.commons.systemd_install import enable_user_units
from plantimager.commons.systemd_install import replace_line
from plantimager.commons.systemd_install import run
from plantimager.commons.systemd_install import user_unit_dir

WEBUI_SERVICES = "plantimager.webui.services"
WEBUI_UNIT = "plant-imager-webui.service"


def webui_exec_start(python_bin: str, args) -> str:
    """Build the webui ``ExecStart`` line from install flags."""
    parts = [f"{python_bin}/plant-imager-webui"]
    if args.proxy:
        parts.append("--proxy")
    parts += ["--url-prefix", args.url_prefix,
              "--plantdb-host", args.plantdb_host,
              "--plantdb-port", str(args.plantdb_port),
              "--plantdb-prefix", args.plantdb_prefix,
              "--plantdb-ssl", str(args.plantdb_ssl)]
    if args.webui_port is not None:
        parts += ["--port", str(args.webui_port)]
    return "ExecStart=" + " ".join(parts)


def install(args) -> int:
    """Install or remove the WebUI unit described by ``args``."""
    unit_dir = user_unit_dir(args.user)
    if not os.path.isdir(os.path.join("/home", args.user)):
        print(f"ERROR: no directory /home/{args.user} found", file=sys.stderr)
        return 1
    if args.remove:
        path = os.path.join(unit_dir, WEBUI_UNIT)
        print(f"- {path}")
        if not args.dry_run and os.path.exists(path):
            os.remove(path)
        run(["systemctl", "--user", "daemon-reload"], args.dry_run)
        return 0
    template = resources.files(WEBUI_SERVICES).joinpath(WEBUI_UNIT).read_text()
    content = replace_line(
        template, "ExecStart=", webui_exec_start(args.python_bin, args))
    path = os.path.join(unit_dir, WEBUI_UNIT)
    print(f"write {path}")
    if not args.dry_run:
        os.makedirs(unit_dir, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
    enable_user_units([WEBUI_UNIT], args.user, args.start, args.dry_run)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Install the WebUI systemd user unit.")
    parser.add_argument("--user", default=getpass.getuser(),
                        help="login user to install for (default: current user)")
    parser.add_argument("--python-bin", default=None,
                        help="venv bin dir with the console scripts "
                             "(default: /home/<user>/miniconda3/envs/plant-imager/bin)")
    parser.add_argument("--plantdb-host",
                        default="mellitus.biologie.ens-lyon.fr")
    parser.add_argument("--plantdb-port", type=int, default=80)
    parser.add_argument("--plantdb-prefix", default="/plantdb")
    parser.add_argument("--plantdb-ssl", default="True")
    parser.add_argument("--proxy", action=argparse.BooleanOptionalAction,
                        default=True)
    parser.add_argument("--url-prefix", default="/webui")
    parser.add_argument("--webui-port", type=int, default=None)
    parser.add_argument("--start", action="store_true",
                        help="start the unit after enabling it")
    parser.add_argument("--remove", action="store_true",
                        help="remove the unit instead of installing it")
    parser.add_argument("--dry-run", action="store_true",
                        help="print actions without touching the system")
    return parser


def main(argv=None) -> None:
    """Entry point for the ``plant-imager-webui-setup`` console script."""
    args = build_parser().parse_args(argv)
    if args.python_bin is None:
        args.python_bin = (f"/home/{args.user}/miniconda3/envs/plant-imager/bin")
    raise SystemExit(install(args))


if __name__ == "__main__":
    main()
