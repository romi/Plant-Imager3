import time
from typing import Iterator
from weakref import finalize

import av
av.logging.set_level(av.logging.ERROR)
av.logging.set_libav_level(av.logging.ERROR)

class PyAVReceiver:
    def __init__(self, ):
        super().__init__()
        self.uri = None
        self.format = None
        self._opened = False
        self._wait_times = [0]*30
        self._decode_times = [0]*30
        self._base_rate: int = None
        self._t0: float = None
        self._stream: av.VideoStream = None
        self._container: av.container.InputContainer | None = None
        def _finalizer():
            print("Closing stream")
            if self._container: self._container.close()
        finalize(self, _finalizer)


    def open(self, uri: str, format: str) -> bool:
        """
        Open a new video stream from uri using the specified format.
        :param uri:
        :param format:
        :return bool:
        """
        self.uri = uri
        self.format = format
        if self._container:
            self._container.close()
            self._opened = False
        try:
            self._container = av.open(
                self.uri, "r", format=self.format, buffer_size=1024, timeout=60
            )
        except UnicodeDecodeError:
            return False
        except av.TimeoutError:
            return False
        except av.ConnectionRefusedError:
            return False
        except av.FFmpegError:
            return False
        self._container.flags = self._container.flags | 0x40 # NO_BUFFER
        self._stream = self._container.streams.video[0]
        self._base_rate = int(self._stream.base_rate)
        self._wait_times = [0] * int(self._base_rate)
        self._decode_times = [0] * int(self._base_rate)
        self._opened = True
        self._t0 = None
        return True

    def close(self):
        if self._container:
            self._container.close()
            self._opened = False
            self._container = None

    def frames(self) -> Iterator[av.VideoFrame]:
        if not self._opened:
            raise RuntimeError("No container opened")
        _n_decode: int = 0
        _n_frame: int = 0
        for packet in self._container.demux(self._stream):
            t_decode = time.time()
            frames: list[av.VideoFrame] = packet.decode()
            self._decode_times[_n_decode%len(self._decode_times)] = time.time() - t_decode
            _n_decode += 1
            for frame in frames:
                if self._t0 is None:
                    self._t0 = time.time()
                    wait = 0
                else:
                    wait = frame.time - (time.time() - self._t0)
                    #print(frame.pts*frame.time_base, frame.dts*frame.time_base, time.time() - self.t0)
                self._wait_times[_n_frame%len(self._wait_times)] = wait

                # wait for the right time to present next frame if the frame is in advance
                # if the frame is too late skip it
                if wait>0:
                    time.sleep(min(wait, 1e-6))
                    yield frame
                elif wait<10:
                    print("skipped frame", _n_frame, "at", frame.time)
                else:
                    yield frame
                _n_frame += 1

                if not self._opened or self._container is None:
                    break

            if not self._opened or self._container is None:
                break


    @property
    def base_rate(self) -> int:
        return self._base_rate

    @property
    def avg_wait(self):
        return sum(self._wait_times)/len(self._wait_times)

    @property
    def avg_decode_time(self):
        return sum(self._decode_times)/len(self._decode_times)



if __name__ == "__main__":
    import cv2 as cv
    #receiver = PyAVReceiver("tcp://picamera2.wlan:8888", format="mpegts")
    receiver = PyAVReceiver("tcp://localhost:8888", format="mpegts")
    n = 0
    t1 = time.time()
    for frame in receiver.frames():
        n += 1
        t2 = time.time()
        #image = frame.to_rgb().to_ndarray()
        #opencvimage = cv.cvtColor(image, cv.COLOR_RGB2BGR)
        opencvimage = frame.reformat(format="bgr24").to_ndarray()
        t3 = time.time()
        cv.imshow(f"pyav_receiver", opencvimage)
        interval, t1 = time.time() - t1, time.time()
        if n%5 == 0:
            print(f"Frame {n}, fps={1/interval:.1f}, decode {receiver.avg_decode_time*1000:.1f} ms, "
                  f"conversion {(t3-t2)*1000:.1f} ms, imshow {(t1-t3)*1000:.1f} ms, "
                  f"wait {receiver.avg_wait*1000:.1f} ms", end="\n", flush=True)
        if cv.waitKey(1) == ord('q'):
            break