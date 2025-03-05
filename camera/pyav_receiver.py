import time
from typing import Iterator

import cv2 as cv

import av

class PyAVReceiver:
    def __init__(self, uri: str, format: str):
        super().__init__()
        self.uri = uri
        self.format = format
        self._started = False
        self._wait_times = [0]*30
        self._decode_times = [0]*30
        self._base_rate: int = None


    def start(self):
        if not self._started:
            self.container = av.open(
                self.uri, "r", format=self.format, buffer_size=1024, timeout=60
            )
            self.container.flags = self.container.flags | 0x40
            self.stream = self.container.streams.video[0]
            print(self.stream.average_rate, self.stream.base_rate)
            self._base_rate = int(self.stream.base_rate)
            self._wait_times = [0] * int(self._base_rate)
            self._decode_times = [0] * int(self._base_rate)
            self._started = True
            self.t0 = None

    def frames(self) -> Iterator[av.VideoFrame]:
        self._start()
        _n_decode: int = 0
        _n_frame: int = 0
        for packet in self.container.demux(self.stream):
            t_decode = time.time()
            frames: list[av.VideoFrame] = packet.decode()
            self._decode_times[_n_decode%len(self._decode_times)] = time.time() - t_decode
            _n_decode += 1
            for frame in frames:
                if self.t0 is None:
                    self.t0 = time.time()
                    wait = 0
                else:
                    wait = frame.time - (time.time() - self.t0)
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