import sys
from os.path import dirname

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QFont
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle

from plantimager.controller.ImageProvider import imageProvider

# import QML resources in python modules
from plantimager.controller.camera import CameraVideoReceiver, CameraBridge

from plantimager.controller.PlantImagerApp import rc_style
from plantimager.controller.PlantImagerApp.ttf import rc_ttf


def main():
    app = QGuiApplication(sys.argv)
    font = QFont("Nunito Sans")
    app.setFont(font)
    QQuickStyle.setStyle("Material")
    engine = QQmlApplicationEngine()
    engine.addImageProvider("provider", imageProvider)
    engine.addImportPath(dirname(__file__))
    engine.loadFromModule("PlantImagerApp", "Main")

    if not engine.rootObjects():
        sys.exit(-1)

    # view.setFlag(Qt.WindowType.FramelessWindowHint)
    ex = app.exec()
    sys.exit(ex)

if __name__ == "__main__":
   main()