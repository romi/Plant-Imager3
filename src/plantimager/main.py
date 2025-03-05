import sys
from os.path import dirname

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QFont
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle


# import QML resources in python modules
from .camera import CameraReceiver, CameraBridge

from .PlantImagerApp import rc_style
from .PlantImagerApp.ttf import rc_ttf

if __name__ == "__main__":
    app = QGuiApplication(sys.argv)
    font = QFont("Nunito Sans")
    app.setFont(font)
    QQuickStyle.setStyle("Material")
    engine = QQmlApplicationEngine()
    engine.addImportPath(dirname(__file__))
    engine.loadFromModule("PlantImagerApp", "Main")

    if not engine.rootObjects():
        sys.exit(-1)

    #view.setFlag(Qt.WindowType.FramelessWindowHint)
    ex = app.exec()
    sys.exit(ex)