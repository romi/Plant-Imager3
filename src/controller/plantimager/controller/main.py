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
    app = QGuiApplication(sys.argv)

    font = QFont("Nunito Sans")
    app.setFont(font)
    QQuickStyle.setStyle("Material")
    engine = QQmlApplicationEngine()
    engine.addImageProvider("provider", imageProvider)
    engine.addImportPath(dirname(__file__))
    engine.loadFromModule("PlantImagerApp", "Loader")

    if not engine.rootObjects():
        sys.exit(-1)

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