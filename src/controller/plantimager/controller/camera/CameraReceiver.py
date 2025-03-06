import time
from threading import Lock
from weakref import finalize

from PySide6.QtCore import Qt, QThread, QTimer, QObject, Signal, Slot, Property
from PySide6.QtGui import QImage
from PySide6.QtMultimedia import QVideoFrame, QVideoSink
from PySide6.QtQml import QmlElement

import av

from plantimager.controller.camera.pyav_receiver import PyAVReceiver
__all__ = ['CameraReceiver']


class ReceiverWorker(QThread):

    frameReady = Signal(QVideoFrame)
    endOfMediaReached = Signal()

    def __init__(self, source: str, format_: str):
        super().__init__()
        self.source = source
        self.format = format_
        self.receiver = PyAVReceiver()
        self._current_frame: av.VideoFrame = None
        self._frame_id: int = 0
        self._lock = Lock()
        self._conversion_times = [0.] * 30
        self._stop = False

    def run(self):
        try:
            while not self.receiver.open(self.source, self.format):
                time.sleep(1)
                if self._stop:
                    self.finished.emit()
                    return
        except Exception as e:
            # In any case return gracefully to properly free the thread
            print(e)
            self.finished.emit()
            return
        self._conversion_times = [0.] * self.receiver.base_rate
        for frame in self.receiver.frames():
            if self._stop:
                break
            t0 = time.time()
            frame_array = frame.reformat(format="rgb32").to_ndarray()
            image = QImage(frame_array.data, frame_array.shape[1], frame_array.shape[0], QImage.Format.Format_RGB32)
            qvideoframe = QVideoFrame(image)
            self._conversion_times[self._frame_id % self.receiver.base_rate] = time.time() - t0
            self._lock.acquire()
            self._current_frame = frame
            self._frame_id += 1
            self._lock.release()
            self.frameReady.emit(qvideoframe)
        else:
            # End of media reached: for a stream means that the sender stopped sending
            # or connection is lost
            self.finished.emit()
            self.endOfMediaReached.emit()
            return

        print("Finished")
        self.finished.emit()

    @Slot()
    def stop(self):
        self._stop = True

    @property
    def avg_conversion_time(self):
        return sum(self._conversion_times) / len(self._conversion_times)

    @Slot()
    def print_info(self):
        print(f"Frame {self._frame_id}, decode {self.receiver.avg_decode_time * 1000:.1f} ms, "
              f"conversion {self.avg_conversion_time * 1000:.1f} ms, "
              f"wait {self.receiver.avg_wait * 1000:.1f} ms", end="\n", flush=True)

QML_IMPORT_NAME = "PlantImagerApp.Camera"
QML_IMPORT_MAJOR_VERSION = 1


@QmlElement
class CameraReceiver(QObject):
    """
    Receives frames from remote camera using PyAVReceiver.
    Sets received frame to videoSink.
    """

    videoSinkChanged = Signal(QVideoSink)
    sourceChanged = Signal(str)
    formatChanged = Signal(str)
    autoPlayChanged = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._source: str = None
        self._format: str = None
        self._videoSink: QVideoSink = None
        self._auto_play: bool = False
        self.receiver: PyAVReceiver = None
        self.worker: ReceiverWorker = None
        finalize(self, self._delete_worker)

    @Slot()
    def componentComplete(self, /):
        """
        Must be from QML in the signal Component.
        At this point all static values and binding values have been assigned to the class.

        This is an awful fix required because QQmlParserStatus does not work
        Meant to use https://doc.qt.io/qtforpython-6/PySide6/QtQml/QQmlParserStatus.html instead
        :return:
        """
        if self._source and self._format:
            self._new_media()
        if self._auto_play and self._videoSink:
            self.play()
        self.videoSinkChanged.connect(lambda : self.play() if self._auto_play else None)
        self.sourceChanged.connect(self._new_media)

    @Slot()
    def _delete_worker(self):
        if self.worker and not self.worker.isFinished():
            self.worker.stop()
            if not self.worker.wait(2000):
                self.worker.terminate()
            self.worker.wait()
            self.worker.deleteLater()

    @Slot()
    def _new_media(self):
        if self.worker:
            self.worker.stop()

        if self._videoSink and self._source and self._format:
            self.worker = ReceiverWorker(self._source, self._format)
            self.worker.frameReady.connect(self._update_video_sink)
            self.worker.finished.connect(self.worker.deleteLater)
            self.worker.endOfMediaReached.connect(self._handle_worker_end_of_media)
            if self._auto_play:
                self.play()

    @Slot()
    def _handle_worker_end_of_media(self):
        if self._auto_play:
            self._new_media()
            self.play()

    @Slot(QVideoFrame)
    def _update_video_sink(self, frame: QVideoFrame):
        self._videoSink.setVideoFrame(frame)

    @Property(QObject, notify=videoSinkChanged)
    def videoSink(self):
        return self._videoSink

    @videoSink.setter
    def videoSink(self, sink: QVideoSink):
        if self._videoSink is not sink:
            self._videoSink = sink
            self.videoSinkChanged.emit(sink)

    @Property(str, notify=formatChanged)
    def format(self):
        return self._format

    @format.setter
    def format(self, format: str):
        if self._format != format:
            self._format = format
            self.formatChanged.emit(format)

    @Property(str, notify=sourceChanged)
    def source(self):
        return self._source

    @source.setter
    def source(self, source: str):
        if self._source != source:
            self._source = source
            self.sourceChanged.emit(source)

    @Property(bool, notify=autoPlayChanged)
    def autoPlay(self):
        return self._auto_play

    @autoPlay.setter
    def autoPlay(self, autoPlay: bool):
        if self._auto_play != autoPlay:
            self._auto_play = autoPlay
            self.autoPlayChanged.emit(autoPlay)

    @Slot()
    def play(self):
        self.worker.start()

    @Slot()
    def stop(self):
        self.worker.stop()

    @Slot()
    def print_info(self):
        if self.worker:
            self.worker.print_info()
        else:
            print("No media set")
