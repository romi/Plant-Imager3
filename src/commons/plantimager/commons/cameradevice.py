from abc import ABC, abstractmethod

class Camera(ABC):

    def __init__(self):
        pass

    @abstractmethod
    def start_video(self):
        pass

    @abstractmethod
    def stop_video(self):
        pass

    @abstractmethod
    def get_image(self) -> tuple[memoryview, dict]:
        pass