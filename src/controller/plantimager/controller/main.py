"""
# Plant-Imager3 Controller Entry Point

Entry point for the Plant-Imager3 controller, a PySide6/QML desktop
application that drives the plant imaging hardware.

## Key Features

- Boots the Qt GUI and loads the QML user interface from the PlantImagerApp module.
- Registers the camera image provider with the QML engine.
- Keeps the Python interpreter alive via a watchdog timer so unix signals (SIGINT) are handled.
- Reports service lifecycle state (ready, watchdog, stopping) to systemd.

## Usage Examples

Run the controller directly as a script:

```shell
python src/controller/plantimager/controller/main.py
```

or

```shell
python -m plantimager.controller.main
```
"""

import signal
import sys
from os.path import dirname
from types import FrameType

from PySide6.QtCore import Qt
from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from plantimager.commons.logging import create_logger
from plantimager.commons.systemd import notify_mainpid
from plantimager.commons.systemd import notify_ready
from plantimager.commons.systemd import notify_stopping
from plantimager.commons.systemd import notify_watchdog

from plantimager.controller.ImageProvider import imageProvider

# Imports pull in QML resources (styles, fonts) that must be registered before the engine loads
from plantimager.controller.camera import CameraVideoReceiver
from plantimager.controller.camera import CameraBridge
from plantimager.controller.AppBridge import AppBridge
from plantimager.controller.PlantImagerApp import rc_style
from plantimager.controller.PlantImagerApp.ttf import rc_ttf

logger = create_logger('camera_server')


def sigint_handler(sig: signal.Signals, frame: FrameType | None) -> None:
    """
    Handle SIGINT (ctrl+c).

    Parameters
    ----------
    sig : signal.Signals
        The signal number received.
    frame : FrameType or None
        The interrupted stack frame.
    """
    QGuiApplication.quit()  # Ctrl+C only lands if the event loop keeps running, see the watchdog timer below
    logger.info(f"Received signal '{signal.strsignal(sig)}' ({sig}), quitting")
    logger.debug(f"Signal received from {frame}")


def main() -> None:
    """
    Run the Plant-Imager3 controller.

    Creates the Qt application, loads the QML UI, installs signal handling,
    and blocks in the Qt event loop until the app quits.

    Exits with a non-zero code if the QML module fails to load.
    """
    logger.info("Starting Plant-Imager3 controller")
    app = QGuiApplication(sys.argv)

    font = QFont("Nunito Sans")
    app.setFont(font)
    QQuickStyle.setStyle("Material")
    logger.debug("Using Material style and Nunito Sans font")

    engine = QQmlApplicationEngine()
    engine.addImageProvider("provider", imageProvider)
    engine.addImportPath(dirname(__file__))
    logger.debug("Loading QML module PlantImagerApp")
    engine.loadFromModule("PlantImagerApp", "Loader")

    if not engine.rootObjects():
        logger.error("Failed to load QML module PlantImagerApp, no root objects created")
        sys.exit(-1)  # A load error is fatal: there is no UI to show
    logger.info("QML module loaded successfully")

    # Keep the interpreter running so Python receives unix signals (SIGINT) between Qt's event loop iterations
    timer = QTimer()
    timer.start(500)
    timer.timeout.connect(notify_watchdog)  # Let the interpreter run each 500 ms.
    signal.signal(signal.SIGINT, sigint_handler)
    logger.debug("Watchdog timer started, SIGINT handler installed")

    # view.setFlag(Qt.WindowType.FramelessWindowHint)
    notify_ready()  # Tell systemd the service is up
    logger.info("Controller ready, entering event loop")
    app.aboutToQuit.connect(notify_stopping)  # Notify systemd on shutdown
    ex = app.exec()
    logger.info("Event loop exited with code %s", ex)
    sys.exit(ex)


if __name__ == "__main__":
    main()
