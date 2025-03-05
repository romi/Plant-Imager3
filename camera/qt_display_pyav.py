import sys
import time
from functools import partial
from queue import Queue
from threading import Lock

from PySide6.QtCore import Qt, QByteArray, QThread, QObject, Slot, Signal, QTimer
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QMainWindow
from PySide6.QtMultimedia import (QAudioOutput, QMediaFormat,
                                  QMediaPlayer, QVideoFrame, QVideoFrameFormat, QVideoSink)
from PySide6.QtMultimediaWidgets import QVideoWidget
import av

from pyav_receiver import PyAVReceiver

class ReceiverWorker(PyAVReceiver, QThread):

    frameReady = Signal(QVideoFrame)

    def __init__(self, uri: str, format: str):
        super().__init__(uri, format)
        self._current_frame: av.VideoFrame = None
        self._frame_id: int = 0
        self.videoBuffer = Queue(maxsize=1)
        self._lock = Lock()
        self._conversion_times = [0.] * 30
        self._stop = False

    def run(self):
        print("Receiver worker started")
        PyAVReceiver.start(self)
        self._conversion_times = [0.]*self._base_rate
        for frame in self.frames():
            if self._stop:
                break
            t0 = time.time()
            frame_array = frame.reformat(format="rgb32").to_ndarray()
            image = QImage(frame_array.data, frame_array.shape[1], frame_array.shape[0], QImage.Format.Format_RGB32)
            qvideoframe = QVideoFrame(image)
            self._conversion_times[self._frame_id%self._base_rate] = time.time() - t0
            if self.videoBuffer.full():
                self.videoBuffer.get()
            self._lock.acquire()
            self._current_frame = frame
            self._frame_id += 1
            self._lock.release()
            self.frameReady.emit(qvideoframe)
        print("Finished")
        self.stop.disconnect()
        self.finished.emit()

    @Slot(result=QVideoFrame)
    def get_next_frame(self):
        return self.videoBuffer.get()

    @Slot()
    def stop(self):
        self._stop = True
        try:
            self.exit()
        except RuntimeError:
            pass

    @property
    def avg_conversion_time(self):
        return sum(self._conversion_times) / len(self._conversion_times)

    def print_info(self):
        print(f"Frame {self._frame_id}, decode {self.avg_decode_time * 1000:.1f} ms, "
              f"conversion {self.avg_conversion_time * 1000:.1f} ms, "
              f"wait {self.avg_wait * 1000:.1f} ms", end="\n", flush=True)

def update_video_sink(video_sink: QVideoSink, frame: QVideoFrame):
    video_sink.setVideoFrame(frame)

def terminate_worker(worker: ReceiverWorker):
    worker.stop()
    worker.wait()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    videoWidget = QVideoWidget()
    videoSink = videoWidget.videoSink()
    #worker = ReceiverWorker("tcp://picamera2.wlan:8888", format="mpegts")
    worker = ReceiverWorker("tcp://localhost:8888", format="mpegts")
    worker.frameReady.connect(partial(update_video_sink, videoSink))
    worker.finished.connect(worker.deleteLater)
    worker.start()
    timer = QTimer(singleShot=False, interval=1000)
    timer.timeout.connect(worker.print_info)
    videoWidget.show()
    timer.start()
    app.aboutToQuit.connect(partial(terminate_worker, worker))
    sys.exit(app.exec())

