"""Shared helpers for the per-package systemd installers.

``plant-imager-controller-setup`` (and the webui setup) install
``--user`` units from packaged templates: same directories, same
linger/reload/enable dance, only the unit contents differ.
``picamera-install`` instead installs system units into
``/etc/systemd/system`` (the agent runs as root so it can
reboot/poweroff the Pi): same reload/enable pattern, no linger,
sudo required.
"""

import os
import subprocess

USER_SYSTEMD_DIR = ".config/systemd/user"


def run(cmd: list, dry_run: bool = False) -> None:
    """Echo then run a command (echo only on dry run)."""
    print(f"+ {' '.join(cmd)}")
    if not dry_run:
        subprocess.check_call(cmd)


def user_unit_dir(user: str) -> str:
    """Systemd user directory for ``user`` (created on install)."""
    return os.path.join("/home", user, USER_SYSTEMD_DIR)


def replace_line(text: str, prefix: str, replacement: str) -> str:
    """Replace whole lines starting with ``prefix`` by ``replacement``."""
    return "\n".join(
        replacement if line.startswith(prefix) else line
        for line in text.splitlines()
    ) + "\n"


def enable_user_units(names: list, user: str, start: bool,
                      dry_run: bool = False) -> None:
    """Linger, reload and enable (optionally start) user units."""
    run(["loginctl", "enable-linger", user], dry_run)
    run(["systemctl", "--user", "daemon-reload"], dry_run)
    for name in names:
        run(["systemctl", "--user", "enable", name], dry_run)
        if start:
            run(["systemctl", "--user", "start", name], dry_run)


SYSTEM_UNIT_DIR = "/etc/systemd/system"


def enable_system_units(names: list, start: bool,
                        dry_run: bool = False) -> None:
    """Reload and enable (optionally start) system units (run as root)."""
    run(["systemctl", "daemon-reload"], dry_run)
    for name in names:
        run(["systemctl", "enable", name], dry_run)
        if start:
            run(["systemctl", "start", name], dry_run)
