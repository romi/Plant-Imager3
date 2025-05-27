"""
Various notifications for systemd.

see https://www.freedesktop.org/software/systemd/man/latest/sd_notify.html#
"""
import os

import sdnotify

notifier = sdnotify.SystemdNotifier()

def notify_ready():
    """Tells the service manager that service startup is finished, or the service finished re-loading its configuration.

    This is only used by systemd if the service definition file has Type=notify or Type=notify-reload set.
    """
    notifier.notify("READY=1")

def notify_watchdog():
    """
    Tells the service manager to update the watchdog timestamp.

    This is the keep-alive ping that services need to issue in regular intervals if WatchdogSec= is enabled for it.

    see https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html#WatchdogSec=
    """
    notifier.notify("WATCHDOG=1")

def notify_stopping():
    """
    Tells the service manager that the service is beginning its shutdown.

    This is useful to allow the service manager to track the service's internal state, and present it to the user.
    """
    notifier.notify("STOPPING=1")

def notify_mainpid():
    notifier.notify(f"MAINPID={os.getpid()}")