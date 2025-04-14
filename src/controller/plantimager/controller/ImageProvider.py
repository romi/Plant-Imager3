from PySide6.QtCore import QSize, Qt
from PySide6.QtQml import QQmlImageProviderBase
from PySide6.QtQuick import QQuickImageProvider
from PySide6.QtGui import QImage, QTransform

from plantimager.commons.logging import create_logger

logger = create_logger("ImageProvider")

class ImageProvider(QQuickImageProvider):
    """
    Provides images from memory to QML
    """

    def __init__(self):
        super().__init__(QQmlImageProviderBase.ImageType.Image)
        self.images: dict[str, QImage] = {}

    def addImageFromBuffer(self, id: str, buffer: memoryview, buffer_info: dict):
        if buffer_info["format"] == "jpeg":
            image = QImage.fromData(buffer.tobytes("C"), "JPG")
            if "rotation" in buffer_info and buffer_info["rotation"] != 0:
                transform = QTransform().rotate(buffer_info["rotation"])
                image = image.transformed(transform, mode=Qt.TransformationMode.SmoothTransformation)
            self.images[id] = image
            logger.debug(f"Added image to id: {id}")
        else:
            logger.warning(f"Unknown image format: {buffer_info['format']} for id: {id}")

    def requestImage(self, id: str, size: QSize, requestedSize: QSize, /):
        if id in self.images:
            image: QImage = self.images[id]
            size.setWidth(image.width())
            size.setHeight(image.height())
            return self.images[id]
        else:
            return QImage()


imageProvider = ImageProvider()
__all__ = ["imageProvider"]

