import os
import sys
from os.path import dirname
import signal

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication, QFont
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle

from plantimager.controller.ImageProvider import imageProvider
from plantimager.commons.systemd import notify_ready, notify_watchdog, notify_stopping, notify_mainpid

# import QML resources in python modules
from plantimager.controller.camera import CameraVideoReceiver, CameraBridge
from plantimager.controller.AppBridge import AppBridge

from plantimager.controller.PlantImagerApp import rc_style
from plantimager.controller.PlantImagerApp.ttf import rc_ttf


def sigint_handler(sig, frame):
    """Handle SIGINT (ctrl+c)"""
    QGuiApplication.quit()


def main():
    if "--allow-dummy-cnc" in sys.argv:
        os.environ["PI3_ALLOW_DUMMY_CNC"] = "1"
    if "--cnc" in sys.argv:
        try:
            idx = sys.argv.index("--cnc")
            val = sys.argv[idx + 1].lower()
            if val in ("dummy", "real"):
                os.environ["PI3_CNC_MODE"] = val
        except Exception:
            pass
    app = QGuiApplication(sys.argv)

    font = QFont("Nunito Sans")
    app.setFont(font)
    QQuickStyle.setStyle("Material")
    engine = QQmlApplicationEngine()
    engine.addImageProvider("provider", imageProvider)
    engine.addImportPath(dirname(__file__))
    engine.loadFromModule("PlantImagerApp", "Loader")

    try:
        from plantimager.controller.AppBridge import _last_init_error

        if _last_init_error is not None:
            import traceback

            print("\n--- AppBridge init failed ---", file=sys.stderr)
            traceback.print_exception(
                type(_last_init_error),
                _last_init_error,
                _last_init_error.__traceback__,
            )
            sys.exit(1)
    except SystemExit:
        raise
    except Exception:
        pass

    if not engine.rootObjects():
        sys.exit(1)

    # Set a timer to let the interpreter run every so often and handle unix signals such as SIGINT
    timer = QTimer()
    timer.start(500)
    timer.timeout.connect(notify_watchdog)  # Let the interpreter run each 500 ms.
    signal.signal(signal.SIGINT, sigint_handler)

    # view.setFlag(Qt.WindowType.FramelessWindowHint)
    notify_ready()
    app.aboutToQuit.connect(notify_stopping)
    ex = app.exec()
    sys.exit(ex)

if __name__ == "__main__":
   main()