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
    modeChanged = RPCSignal(str)
    videoUrlChanged = RPCSignal(str)
    rotationChanged = RPCSignal(int)
    resolutionChanged = RPCSignal(tuple[int, int])

    def __init__(self):
        pass

    @abstractmethod
    def get_image(self) -> tuple[memoryview, dict]:
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

