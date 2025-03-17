from abc import ABC, abstractmethod

class Camera(ABC):
    """
    Abstract class for camera devices.
    """

    def __init__(self):
        pass

    @abstractmethod
    def start_video(self) -> str:
        pass

    @abstractmethod
    def stop_video(self) -> str:
        pass

    @abstractmethod
    def get_image(self) -> tuple[memoryview, dict]:
        pass