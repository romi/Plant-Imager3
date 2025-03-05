import sys

from PySide6.QtCore import Qt, QByteArray
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QMainWindow
from PySide6.QtMultimedia import (QAudioOutput, QMediaFormat,
                                  QMediaPlayer, QVideoFrame, QVideoFrameFormat)
from PySide6.QtMultimediaWidgets import QVideoWidget

from pyav_receiver import PyAVReceiver

app = QApplication(sys.argv)
mediaplayer = QMediaPlayer()
mediaplayer.setSource("tcp://picamera2.wlan:8888")
videoWidget = QVideoWidget()
mediaplayer.setVideoOutput(videoWidget)
videoWidget.show()
mediaplayer.play()
sys.exit(app.exec())

