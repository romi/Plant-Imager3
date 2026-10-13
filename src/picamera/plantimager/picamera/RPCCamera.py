import io
import json
import os
import subprocess
import sys
import socket

import av
import numpy as np
import zmq
from PIL import Image
from picamera2 import Picamera2
from picamera2.encoders import H264Encoder
from picamera2.outputs import PyavOutput
from simplejpeg import encode_jpeg, encode_jpeg_yuv_planes

from plantimager.commons.RPC import RPCServer, RPCProperty
from plantimager.commons.cameradevice import Camera, CameraMode
from plantimager.commons.systemd import notify_ready, notify_stopping, notify_watchdog

__all__ = ['RPCCamera']

class PyavOutput_nobuffer(PyavOutput):
    def __init__(self, output_name, format=None, pts=None):
        super().__init__(output_name, format=format, pts=pts)

    def start(self):
        self._container = av.open(self._output_name, "w", format=self._format, buffer_size=1024*8)
        self._container.flags = self._container.flags | 0x40
        super(PyavOutput, self).start()


class RPCCamera(Camera, RPCServer):
    # (min, max) fallback when camera_controls is unavailable; live values win.
    _FALLBACK_RANGES = {
        "AeEnable": (False, True),
        "AwbEnable": (False, True),
        "ExposureTime": (74, 694422939),
        "AnalogueGain": (1.0, 22.26),
        "AwbMode": (0, 7),
        "AeMeteringMode": (0, 3),
        "ColourGains": (0.0, 32.0),
        "Brightness": (-1.0, 1.0),
        "Contrast": (0.0, 32.0),
        "Saturation": (0.0, 32.0),
        "Sharpness": (0.0, 16.0),
    }
    _TUPLE_LEN = {
        "ColourGains": 2,
        "FrameDurationLimits": 2,
        "ScalerCrop": 4,
        "ColourCorrectionMatrix": 9,
    }
    _ZERO_IS_AUTO = frozenset({"ExposureTime", "AnalogueGain"})

    def __init__(self, context: zmq.Context, url: str):
        RPCServer.__init__(self, context, url)
        self.picam = Picamera2()
        max_res = self.picam.camera_properties["PixelArraySize"]
        print(self.picam.camera_properties)
        self.video_config = self.picam.create_video_configuration(
            {"size": (640, 480), "format": "YUV420"},
            controls={'FrameRate': 15}
        )
        self.still_config = self.picam.create_still_configuration(
            {"size": (max_res[0]//2, max_res[1]//2), "format": "BGR888"}, lores={"size": (3*640, 3*480)},
            queue=False
        )
        self._mode = CameraMode.STILL
        self._video_url = ""
        self._encoding = "jpeg"
        self._config = {}  # camera parameters from Appendix C in the picamera2 doc.
        self.picam.configure(self.still_config)
        self.picam.start()
        saved = self._read_defaults_file()
        if saved is None:
            if os.path.exists(self._defaults_path()):
                print(f"warning: ignoring unreadable {self._defaults_path()}, using factory defaults")
            saved = dict(self.DEFAULT_CONTROLS)
        self.config = saved

        # video stuff
        self.encoder: H264Encoder | None = None
        self.output: PyavOutput_nobuffer | None = None

        # config
        self._rotation = 90


    def start_video(self):
        if self._mode != CameraMode.VIDEO:
            print("Starting camera stream")
            self.picam.switch_mode(self.video_config, wait=True)
            self._mode = CameraMode.VIDEO
            print("switched to video mode")
            self.encoder = H264Encoder(bitrate=10_000_000)
            self.output = PyavOutput_nobuffer("tcp://0.0.0.0:8888\?listen=1", format="mpegts")
            self.picam.start_encoder(self.encoder, self.output)
            print("Camera stream started")
            self._video_url = f"tcp://{socket.gethostname()}:8888"
            self.videoUrlChanged.emit(self._video_url)
        return f"tcp://{socket.gethostname()}:8888"


    def stop_video(self):
        if self._mode == CameraMode.VIDEO:
            print("Stopping camera stream")
            self.picam.stop_encoder()
            self.encoder = None
            self.output = None
            self._video_url = ""
            self.videoUrlChanged.emit(self._video_url)
            self.picam.switch_mode(self.still_config, wait=True)
            self._mode = CameraMode.STILL
            print("switched to still mode")
        return "VIDEO STOPPED"

    @RPCServer.register_method_buffer(timeout=None)
    def get_image(self, lores=False) -> (memoryview, dict):
        if self._mode != CameraMode.STILL:
            self.mode = CameraMode.STILL
        if lores:
            height, width = self.still_config["lores"]["size"]
            image: np.ndarray = self.picam.capture_array("lores")
            padding = image.shape[1] - height
            Y = image[:width, :height]
            U = np.zeros((width//2, height//2), dtype=np.uint8)
            V = np.zeros((width//2, height//2), dtype=np.uint8)
            U[::2, :] = image[width:width+width//4, :height//2]
            U[1::2, :] = image[width:width+width//4, height//2+padding//2:height+padding//2]
            V[::2, :] = image[width+width//4:, :height//2]
            V[1::2, :] = image[width+width//4:, height//2+padding//2:height+padding//2]
            buffer = encode_jpeg_yuv_planes(Y, U, V, quality=80, fastdct=True)
            fmt = "jpeg"
        else:
            image: np.ndarray = self.picam.capture_array()
            if self._encoding == "png":
                pil_img = Image.fromarray(image)
                buf = io.BytesIO()
                pil_img.save(buf, format="PNG")
                buffer = buf.getvalue()
                fmt = "png"
            else:
                buffer = encode_jpeg(image, quality=95, colorsubsampling="444", fastdct=True)
                fmt = "jpeg"
        info = {"format": fmt, "rotation": self._rotation, "size": image.shape, "channel": "rgb"}
        try:
            meta = self.picam.capture_metadata()
        except Exception:
            meta = {}
        for key in ("ExposureTime", "AnalogueGain", "ColourGains",
                    "FrameDuration", "Lux", "ColourTemperature"):
            if key in meta:
                info[key] = meta[key]
        return memoryview(buffer), info

    @RPCProperty(notify=Camera.encodingChanged)
    def encoding(self) -> str:
        return self._encoding
    @encoding.setter
    def encoding(self, value: str):
        if value in ["jpeg", "png"]:
            self._encoding = value
            self.encodingChanged.emit(value)

    @RPCProperty(notify=Camera.configChanged)
    def config(self) -> dict:
        return self._config
    @config.setter
    def config(self, value: dict):
        """
        Sets camera controls/parameters from Picamera2 Appendix C.

        Replace-wholesale: the given dict becomes the full control set.
        Every key is validated before anything is applied: an invalid
        dict raises and leaves the previous controls untouched.

        Parameters
        ----------
        value : dict
            Control names and values (e.g., {'Brightness': 0.5, 'Contrast': 1.2}).

        See Also
        --------
        Picamera2 Manual Appendix C:
https://pip-assets.raspberrypi.com/categories/652-raspberry-pi-camera-module-2/documents/RP-008156-DS-2-picamera2-manual.pdf?disposition=inline#%5B%7B%22num%22%3A10333%2C%22gen%22%3A0%7D%2C%7B%22name%22%3A%22XYZ%22%7D%2C70.86614%2C781.0236%2C0%5D
        """
        validated = self._validate_config(value)
        self._config = validated
        # Apply controls to the running camera
        self.picam.set_controls(self._config)
        self.configChanged.emit(self._config)

    def _validate_config(self, value: dict) -> dict:
        if not isinstance(value, dict):
            raise TypeError(f"config must be a dict, got {type(value).__name__}")
        controls = self.picam.camera_controls
        live = controls if isinstance(controls, dict) else {}
        validated = {}
        for key, val in value.items():
            if key == "FrameRate":
                if isinstance(val, bool) or not isinstance(val, (int, float)) or val <= 0:
                    raise ValueError(f"Control FrameRate must be a positive number, got {val!r}")
                validated[key] = val
                continue
            entry = live.get(key) if isinstance(live, dict) else None
            bounds = self._bounds(entry) if entry is not None else self._FALLBACK_RANGES.get(key)
            if bounds is None:
                raise ValueError(f"Control {key} is not advertised by libcamera")
            lo, hi = bounds
            want_len = self._TUPLE_LEN.get(key)
            if want_len is None and isinstance(entry, (tuple, list)) and len(entry) >= 3:
                default = entry[2]
                if isinstance(default, (tuple, list)):
                    want_len = len(default)
            if want_len is not None:
                seq = tuple(val) if isinstance(val, list) else val
                if not isinstance(seq, tuple) or len(seq) != want_len:
                    raise ValueError(f"Control {key} must be a {want_len}-tuple, got {val!r}")
                for pos, item in enumerate(seq):
                    if isinstance(item, bool) or not isinstance(item, (int, float)):
                        raise ValueError(f"Control {key} must hold numbers, got {val!r}")
                    if not self._in_bounds(item, lo, hi, pos):
                        raise ValueError(f"Control {key} value {val!r} out of range")
                if key == "ColourGains" and all(item == 0 for item in seq):
                    raise ValueError("Control ColourGains (0, 0) is not allowed")
                validated[key] = seq
                continue
            if isinstance(lo, bool) and isinstance(hi, bool):
                if not isinstance(val, bool):
                    raise ValueError(f"Control {key} must be a bool, got {val!r}")
                validated[key] = val
                continue
            if isinstance(val, bool) or not isinstance(val, (int, float)):
                raise ValueError(f"Control {key} must be a number, got {val!r}")
            if val == 0 and key in self._ZERO_IS_AUTO:
                validated[key] = val
                continue
            if isinstance(lo, int) and isinstance(hi, int) and not isinstance(val, int):
                raise ValueError(f"Control {key} must be an int, got {val!r}")
            if (lo is not None and val < lo) or (hi is not None and val > hi):
                raise ValueError(f"Control {key} value {val!r} out of range [{lo}, {hi}]")
            validated[key] = val
        return validated

    @staticmethod
    def _bounds(entry):
        if isinstance(entry, (tuple, list)) and len(entry) >= 2:
            return entry[0], entry[1]
        return getattr(entry, "min", None), getattr(entry, "max", None)

    @staticmethod
    def _in_bounds(item, lo, hi, pos):
        if isinstance(lo, (tuple, list)) and isinstance(hi, (tuple, list)):
            if pos >= len(lo) or pos >= len(hi):
                return False
            return lo[pos] <= item <= hi[pos]
        return (lo is None or lo <= item) and (hi is None or item <= hi)

    @staticmethod
    def _defaults_path():
        override = os.environ.get("CAMERA_PARAMS_FILE")
        if override:
            return override
        base = os.environ.get("XDG_CONFIG_HOME")
        if not base:
            base = os.path.join(os.path.expanduser("~"), ".config")
        return os.path.join(base, "camera_parameters.json")

    def _read_defaults_file(self):
        try:
            with open(self._defaults_path(), encoding="utf-8") as fh:
                return self._validate_config(json.load(fh))
        except (OSError, ValueError, TypeError):
            return None

    def _write_defaults_file(self):
        path = self._defaults_path()
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self._config, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, path)

    @RPCServer.register_method_json
    def set_default_controls(self, value: dict) -> dict:
        """Validate, apply and persist new camera defaults."""
        self.config = value
        self._write_defaults_file()
        return dict(self._config)

    @RPCServer.register_method_json
    def reset_controls(self, factory: bool = False) -> dict:
        """Reset live controls to the persisted defaults (factory=True: factory defaults)."""
        if factory:
            self.config = dict(self.DEFAULT_CONTROLS)
            self._write_defaults_file()
        else:
            saved = self._read_defaults_file()
            self.config = saved if saved is not None else dict(self.DEFAULT_CONTROLS)
        return dict(self._config)

    @RPCServer.register_method_json
    def get_camera_controls(self) -> dict:
        """JSON-safe snapshot of the advertised libcamera controls and ranges."""
        controls = self.picam.camera_controls
        if not isinstance(controls, dict):
            return {}
        out = {}
        for key, entry in controls.items():
            if key == "FrameRate":
                continue
            lo, hi = self._bounds(entry)
            if isinstance(entry, (tuple, list)) and len(entry) >= 3:
                default = entry[2]
            else:
                default = getattr(entry, "default", None)
            out[key] = self._control_schema(key, lo, hi, default)
        return out

    @classmethod
    def _control_schema(cls, key, lo, hi, default):
        def js(value):
            return list(value) if isinstance(value, tuple) else value
        length = cls._TUPLE_LEN.get(key)
        if length is None and isinstance(default, (tuple, list)):
            length = len(default)
        if length is None and isinstance(lo, (tuple, list)):
            length = len(lo)
        if length is not None:
            return {"type": "tuple", "length": length,
                    "min": js(lo), "max": js(hi), "default": js(default)}
        if isinstance(lo, bool) and isinstance(hi, bool):
            return {"type": "bool", "default": default}
        if isinstance(lo, int) and isinstance(hi, int) and 0 <= hi - lo <= 16:
            return {"type": "enum", "min": lo, "max": hi, "default": default,
                    "allowed_values": list(range(lo, hi + 1))}
        return {"type": "scalar", "min": lo, "max": hi, "default": default}

    @RPCProperty(notify=Camera.modeChanged)
    def mode(self):
        return self._mode
    @mode.setter
    def mode(self, value):
        if value != self._mode and value==CameraMode.STILL:
            self.stop_video()
            self._mode = CameraMode.STILL
            self.modeChanged.emit(value)
        if value != self._mode and value==CameraMode.VIDEO:
            self.start_video()
            self._mode = CameraMode.VIDEO
            self.modeChanged.emit(value)

    @RPCProperty(notify=Camera.videoUrlChanged)
    def video_url(self) -> str:
        return self._video_url

    @RPCProperty(notify=Camera.rotationChanged)
    def rotation(self):
        return self._rotation
    @rotation.setter
    def rotation(self, value):
        if value != self._rotation:
            self._rotation = value % 360

    @RPCProperty(notify=Camera.resolutionChanged)
    def resolution(self) -> tuple[int, int]:
        return self.still_config["main"]["size"]
    @resolution.setter
    def resolution(self, value: tuple[int, int]):
        if value != self.still_config["main"]["size"]:
            x_max, y_max = self.picam.camera_properties["PixelArraySize"]
            self.still_config["main"]["size"] = max(60, min(value[0], x_max)), max(60, min(value[1], y_max))
            if self._mode == CameraMode.STILL:
                self.picam.switch_mode(self.still_config, wait=True)
            self.resolutionChanged.emit(self.still_config["main"]["size"])



def main():
    REGISTRY_ADDR = os.getenv("PI_REGISTRY") or "localhost:5555"
    if not REGISTRY_ADDR.startswith("tcp://"):
        REGISTRY_ADDR = "tcp://" + REGISTRY_ADDR
    context = zmq.Context()
    ip_addr = os.getenv("IP_ADDR") or subprocess.call()
    camera = RPCCamera(context, f"tcp://{ip_addr}")
    notify_ready()
    camera.register_to_registry(
        "camera",
        socket.gethostname(),
        REGISTRY_ADDR
    )
    camera.serve_forever()
    notify_stopping()

if __name__ == "__main__":
    main()