from abc import ABC, abstractmethod
from enum import StrEnum
from typing import Literal

from plantimager.commons.RPC import RPCSignal, RPCProperty

class CameraMode(StrEnum):
    VIDEO = "VIDEO"
    STILL = "STILL"

class Camera(ABC):
    """
    Abstract class for camera devices.
    """
    # Factory-validated fixed defaults (IMX477, daylight rig).
    DEFAULT_CONTROLS = {
        "AeEnable": False,
        "ExposureTime": 250000,
        "AnalogueGain": 7.0,
        "AwbEnable": False,
        "AwbMode": 5,  # daylight in libcamera's AwbMode enum
        "ColourGains": (3.215, 1.433),
        "AeMeteringMode": 1,  # Spot
        "Brightness": 0.0,
        "Contrast": 1.0,
        "Saturation": 1.0,
        "Sharpness": 1.0,
    }
    modeChanged = RPCSignal(str)
    videoUrlChanged = RPCSignal(str)
    rotationChanged = RPCSignal(int)
    resolutionChanged = RPCSignal(tuple[int, int])
    encodingChanged = RPCSignal(str)
    configChanged = RPCSignal(dict)

    @abstractmethod
    def __init__(self):
        pass

    @abstractmethod
    def get_image(self, lores=False) -> tuple[memoryview, dict]:
        pass

    @RPCProperty(notify=modeChanged)
    @abstractmethod
    def mode(self) -> Literal[CameraMode.VIDEO, CameraMode.STILL]:
        pass
    @mode.setter
    @abstractmethod
    def mode(self, mode: Literal[CameraMode.STILL, CameraMode.VIDEO]) -> None:
        pass

    @RPCProperty(notify=videoUrlChanged)
    @abstractmethod
    def video_url(self) -> str:
        pass

    @RPCProperty(notify=rotationChanged)
    @abstractmethod
    def rotation(self) -> int:
        pass

    @RPCProperty(notify=resolutionChanged)
    @abstractmethod
    def resolution(self) -> tuple[int, int]:
        pass
    @resolution.setter
    @abstractmethod
    def resolution(self, resolution: tuple[int, int]) -> None:
        pass

    @RPCProperty(notify=encodingChanged)
    @abstractmethod
    def encoding(self) -> Literal["jpeg", "png"]:
        pass
    @encoding.setter
    @abstractmethod
    def encoding(self, value: Literal["jpeg", "png"]) -> None:
        pass

    @RPCProperty(notify=configChanged)
    @abstractmethod
    def config(self) -> dict:
        pass
    @config.setter
    @abstractmethod
    def config(self, value: dict) -> None:
        pass

    def get_camera_controls(self) -> dict:
        """Advertised libcamera controls and ranges (JSON-safe schema).

        Concrete servers override this; the default only documents the
        contract so ``register_interface`` proxies it to Qt/WebUI
        clients even where a server never implemented it.
        """
        raise NotImplementedError

    def set_default_controls(self, value: dict) -> dict:
        """Validate, apply and persist new camera defaults; see above."""
        raise NotImplementedError

    def reset_controls(self, factory: bool = False) -> dict:
        """Reset live controls to persisted (or factory) defaults."""
        raise NotImplementedError
