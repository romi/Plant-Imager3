"""
# Camera Server Example

An example `DummyCamera` that serves images from a shared test dataset over
ZeroMQ RPC, acting as a stand-in for a physical camera during development.

## Key Features

- Provides a `DummyCamera` implementing the `Camera` RPC interface.
- Serves JPEG or PNG images from a directory (the test dataset by default).
- Exposes camera controls (encoding, config, mode, rotation, resolution)
  as remote properties.
"""
import io
import os
import time
from typing import Iterator
from typing import Literal

import matplotlib.pyplot as plt
import numpy as np
import zmq
from PIL import Image
from plantdb.commons.test_database import get_test_dataset
from scipy import ndimage
from simplejpeg import encode_jpeg

from plantimager.commons.RPC import RPCProperty
from plantimager.commons.RPC import RPCServer
from plantimager.commons.cameradevice import Camera
from plantimager.commons.cameradevice import CameraMode
from plantimager.commons.logging import create_logger

logger = create_logger('camera_server')
CAMERASERVER_LAG = int(os.getenv("PI3_CAMERASERVER_LAG", 0))  # in milliseconds


def image_provider() -> Iterator[np.ndarray]:
    """Generate an infinite sequence of images from a directory.

    Reads images from the directory given by the ``PI3_CAMERASERVER_IMAGE``
    environment variable, or from the ``real_plant`` test dataset if unset.

    Yields
    ------
    numpy.ndarray
        Image data loaded by ``matplotlib.pyplot.imread`` from the current file.
        The generator loops indefinitely, restarting after the last image.
    """
    image_path = os.getenv("PI3_CAMERASERVER_IMAGE")
    if image_path is None:
        dataset_path = get_test_dataset('real_plant')
        image_path = str(dataset_path / "images")

    images = sorted(os.listdir(image_path))
    n = len(images)
    i = 0
    while True:
        image = plt.imread(os.path.join(image_path, images[i % n]))
        # SimpleJPEG only supports RGB, so drop the alpha channel if it exists.
        if image.ndim == 3 and image.shape[2] == 4:
            # keep only the first three channels (R, G, B)
            image = image[:, :, :3]
        yield image
        i += 1


def block_mean(ar: np.ndarray, fact: int) -> np.ndarray:
    """Downsample an array by averaging blocks of size ``fact``.

    Each block of ``fact x fact`` pixels is replaced by its mean, reducing the
    image resolution along the first two dimensions.

    Parameters
    ----------
    ar : numpy.ndarray
        Input array of shape ``(sx, sy)`` or ``(sx, sy, n_channels)``.
    fact : int
        Block size along both spatial dimensions.

    Returns
    -------
    numpy.ndarray
        Downsampled array of shape ``(sx // fact, sy // fact)`` or ``(sx // fact, sy // fact, n_channels)``.

    Raises
    ------
    AssertionError
        If ``ar`` has more than three dimensions or ``fact`` is not an int.
    """
    assert isinstance(fact, int), type(fact)
    sx, sy, *others = ar.shape
    assert len(others) <= 1, f"no more than 3 dimensions are allowed, got {len(others) + 2}"
    X, Y = np.ogrid[0:sx, 0:sy]
    regions = sy // fact * (X // fact) + Y // fact
    if others:
        regions = np.expand_dims(regions, axis=2).repeat(others[0], axis=2)
        regions *= others[0]
        for i in range(1, others[0]):
            regions[:, :, i] += i
    res = ndimage.mean(ar, labels=regions, index=np.arange(regions.max() + 1))
    res.shape = (sx // fact, sy // fact, *others)
    return res


class DummyCamera(Camera, RPCServer):
    """Dummy Camera serving images from a shared dataset for testing purposes.

    Implements the :class:`Camera` RPC interface and serves frames from an
    image directory in an endless loop, standing in for a physical camera.

    Parameters
    ----------
    context : zmq.Context
        ZeroMQ context used to create sockets for RPC communication.
    url : str
        Endpoint address that the RPC server will bind to.

    Attributes
    ----------
    encoding : {'jpeg', 'png'}
        Image encoding used when serving frames.
    config : dict
        Camera controls/parameters, e.g. ``{'Brightness': 0.5}``.
    mode : {'VIDEO', 'STILL'}
        Current capture mode.
    video_url : str
        Video stream endpoint; empty when not in ``VIDEO`` mode.
    rotation : int
        Image rotation in degrees.
    resolution : tuple of int
        Fixed resolution ``(640, 480)`` reported by the dummy camera.
    """

    def __init__(self, context: zmq.Context, url: str) -> None:
        """Initialize the dummy camera and its RPC server.

        Sets the default camera state and starts the endless image provider.

        Parameters
        ----------
        context : zmq.Context
            ZeroMQ context used to create sockets for RPC communication.
        url : str
            Endpoint address that the RPC server will bind to.
        """
        RPCServer.__init__(self, context, url)
        self._mode = CameraMode.STILL
        self._video_url = "tcp://test_url:1234"
        self._rotation = 0
        self._encoding = "jpeg"
        self._config = {}
        self._image_provider = image_provider()

    @RPCServer.register_method_buffer(timeout=10000)
    def get_image(self, lores: bool = False) -> tuple[memoryview, dict]:
        """Return a JPEG‑encoded image (as a memoryview) and a metadata dict.

        The *lores* flag is ignored for the dummy implementation.

        Parameters
        ----------
        lores : bool, default False
            Request a low-resolution image; ignored by the dummy camera.

        Returns
        -------
        tuple of (memoryview, dict)
            The encoded image bytes and a metadata dict with keys
            ``format``, ``rotation``, and ``size``.
        """
        if self.mode != CameraMode.STILL:
            self.mode = CameraMode.STILL
        image = next(self._image_provider)
        # image = block_mean(image, 5)
        # image = np.clip(image.astype(int) + np.round(np.random.normal(0.0, 0.5, image.shape)), 0, 255)
        if self._encoding == "jpeg":
            buffer = encode_jpeg(image.astype(np.uint8), quality=95, colorsubsampling="420", fastdct=True)
        elif self._encoding == "png":
            rgb_image = image[..., ::-1]
            pil_img = Image.fromarray(rgb_image)
            buf = io.BytesIO()
            pil_img.save(buf, format="PNG")
            buffer = buf.getvalue()
        else:
            raise ValueError(f"Unknown encoding: {self._encoding}")
        time.sleep(CAMERASERVER_LAG / 1000)
        return memoryview(buffer), {"format": self._encoding, "rotation": self._rotation, "size": image.shape}

    @RPCProperty(notify=Camera.encodingChanged)
    def encoding(self) -> Literal["jpeg", "png"]:
        """Return the current image encoding.

        The value determines whether frames are served as JPEG or PNG.

        Returns
        -------
        {'jpeg', 'png'}
            The image encoding used when serving frames.
        """
        return self._encoding

    @encoding.setter
    def encoding(self, value: Literal["jpeg", "png"]) -> None:
        """Set the image encoding, notifying listeners when it changes.

        Only ``jpeg`` and ``png`` are accepted; other values are ignored.

        Parameters
        ----------
        value : {'jpeg', 'png'}
            The encoding to use for served frames.
        """
        if value in ["jpeg", "png"]:
            self._encoding = value
            self.encodingChanged.emit(value)

    @RPCProperty(notify=Camera.configChanged)
    def config(self) -> dict:
        """Return the current camera configuration.

        A mapping of control names to their current values.

        Returns
        -------
        dict
            Mapping of control names to values.
        """
        return self._config

    @config.setter
    def config(self, value: dict) -> None:
        """Set camera controls/parameters from Picamera2 Appendix C.

        Updates the stored configuration and emits the config-changed signal.

        Parameters
        ----------
        value : dict
            Control names and values (e.g., {'Brightness': 0.5, 'Contrast': 1.2}).

        Notes
        -----
        Control names and values follow the Picamera2 Manual Appendix C.
        """
        self._config.update(value)
        # Apply controls to the running camera
        self.configChanged.emit(self._config)

    @RPCProperty(notify=Camera.modeChanged)
    def mode(self) -> Literal[CameraMode.VIDEO, CameraMode.STILL]:
        """Return the current capture mode.

        The value is ``STILL`` by default.

        Returns
        -------
        {'VIDEO', 'STILL'}
            The current capture mode.
        """
        return self._mode

    @mode.setter
    def mode(self, value: Literal[CameraMode.STILL, CameraMode.VIDEO]) -> None:
        """Set the capture mode, updating the video URL when entering video mode.

        Switching to ``VIDEO`` sets a test video URL; otherwise it is cleared.

        Parameters
        ----------
        value : {'STILL', 'VIDEO'}
            The capture mode to switch to.
        """
        if value != self._mode:
            self._mode = value
            self._video_url = "tcp://test_url:1234" if value == CameraMode.VIDEO else ""
            self.videoUrlChanged.emit(self._video_url)
            self.modeChanged.emit(value)

    @RPCProperty(notify=Camera.videoUrlChanged)
    def video_url(self) -> str:
        """Return the video stream endpoint.

        Empty when the camera is not in ``VIDEO`` mode.

        Returns
        -------
        str
            The video stream URL, empty when not in ``VIDEO`` mode.
        """
        return self._video_url

    @RPCProperty(notify=Camera.rotationChanged)
    def rotation(self) -> int:
        """Return the image rotation in degrees.

        Applies a clockwise rotation to served frames.

        Returns
        -------
        int
            The image rotation in degrees.
        """
        return self._rotation

    @rotation.setter
    def rotation(self, value: int) -> None:
        """Set the image rotation, notifying listeners when it changes.

        No-op when the value is unchanged.

        Parameters
        ----------
        value : int
            The rotation in degrees.
        """
        if value != self._rotation:
            self._rotation = value
            self.rotationChanged.emit(value)

    @RPCProperty(notify=Camera.resolutionChanged)
    def resolution(self) -> tuple[int, int]:
        """Return the image resolution.

        The dummy camera always reports a fixed ``(640, 480)`` resolution.

        Returns
        -------
        tuple of int
            The fixed resolution ``(640, 480)``.
        """
        return 640, 480

    @resolution.setter
    def resolution(self, value: tuple[int, int]) -> None:
        """No-op setter: the dummy camera reports a fixed resolution.

        Provided to satisfy the RPC interface; requested values are ignored.

        Parameters
        ----------
        value : tuple of int
            Requested resolution; ignored.
        """
        pass


if __name__ == "__main__":
    logger.info("Starting camera server...")
    context = zmq.Context()
    camera = DummyCamera(context, url="tcp://127.0.0.1")
    camera.register_to_registry("camera", DummyCamera.__name__, "tcp://127.0.0.1:5555", overwrite=False)
    logger.info("Camera server registered, serving forever...")
    try:
        camera.serve_forever()
    except KeyboardInterrupt:
        logger.info("Camera server stopped.")
