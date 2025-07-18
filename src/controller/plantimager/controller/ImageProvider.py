import numpy as np
from PySide6.QtCore import QSize, Qt
from PySide6.QtQml import QQmlImageProviderBase
from PySide6.QtQuick import QQuickImageProvider
from PySide6.QtGui import QImage, QTransform
from math import ceil

import scipy
import skimage

from plantimager.commons.logging import create_logger

logger = create_logger("ImageProvider")


def qimage_to_ndarray_rgb(image: QImage) -> np.ndarray:
    converted_image = image.convertToFormat(QImage.Format.Format_RGB888)
    view = converted_image.bits()
    height = converted_image.height()
    width = converted_image.width()
    new_shape = (height, width, converted_image.depth() // 8)
    return  np.frombuffer(view, dtype=np.uint8).reshape(new_shape).copy()

def qimage_to_ndarray_gray(image: QImage) -> np.ndarray:
    converted_image = image.convertToFormat(QImage.Format.Format_Grayscale8)
    view = converted_image.bits()
    height = converted_image.height()
    width = converted_image.width()
    new_shape = (height, width)
    return  np.frombuffer(view, dtype=np.uint8).reshape(new_shape).copy()

def ndarray_to_qimage(arr: np.ndarray, format: QImage.Format) -> QImage:
    if format == QImage.Format.Format_Grayscale8:
        arr = arr.astype(np.uint8)
    elif format == QImage.Format.Format_RGB888:
        arr = arr.astype(np.uint8)
    else:
        raise NotImplementedError(f"Format {format.name} not supported.")
    return QImage(arr.data, arr.shape[1], arr.shape[0], format)

def compute_focus(image: np.ndarray, /,):
    """
    Computes the focus measure of an image using the Sobel filter.

    This function calculates the gradient magnitude of an input image in the
    x and y directions, combining the results to estimate focus. The computed
    focus measure highlights edges and areas of high intensity change, which
    are often indicative of regions in focus.

    see https://blog.roboflow.com/computer-vision-camera-focus-guide/#tenengrad-function

    Parameters
    ----------
    image : np.ndarray
        A 2D array representing the input grayscale image whose focus measure is to be
        computed.

    Returns
    -------
    np.ndarray
        A 2D array representing the gradient magnitude of the input image,
        where higher values correspond to more focused regions.
    """
    downscaled = skimage.transform.downscale_local_mean(image, 2).astype(np.uint8)
    grad_x = skimage.filters.sobel(downscaled, axis=0)
    grad_y = skimage.filters.sobel(downscaled, axis=1)
    #plt_imshow(downscaled, title="downscaled")
    #plt_imshow(grad_x, title="grad_x", vmin=grad_x.min(), vmax=grad_x.max())
    #plt_imshow(grad_y, title="grad_y", vmin=grad_y.min(), vmax=grad_y.max())
    magnitude = np.sqrt(grad_x**2 + grad_y**2)
    magnitude = np.astype((magnitude-magnitude.min())/magnitude.max()*255, np.uint8)
    #smoothed = scipy.ndimage.gaussian_filter(magnitude, sigma=1)
    #plt_imshow(smoothed, title="smoothed")
    #magnitude = scipy.ndimage.grey_opening(magnitude, size=(3,3))
    #plt_imshow(magnitude, title="magnitude after opening")
    #plt_imshow(np.floor(magnitude/magnitude.max()*255))
    return skimage.transform.resize(magnitude, image.shape, anti_aliasing=False, mode='constant')

def plt_imshow(image: np.ndarray, /, title: str = "", vmin=0, vmax=255, cmap="gray"):
    import matplotlib
    matplotlib.use('TkAgg')
    import matplotlib.pyplot as plt
    fig = plt.figure()
    plt.imshow(image, cmap=cmap, vmin=vmin, vmax=vmax)
    plt.title(title)
    plt.show()

def focus_highlight(image: QImage, percentile: float) -> QImage:
    """
    Enhances the focus areas of an image by adding a red highlight to regions of
    the image that have a focus value greater than a specified percentile.

    Parameters
    ----------
    image : QImage
        The input image to be processed. Must be in the QImage format.
    percentile : float
        The percentile threshold for selecting focus areas. Focus values above
        this percentile will be highlighted.

    Returns
    -------
    QImage
        A new image with highlighted focus areas in red.
    """
    image_array = qimage_to_ndarray_rgb(image)
    image_grayscale = qimage_to_ndarray_gray(image)
    focus_array = compute_focus(image_grayscale)
    focus_array = np.astype((focus_array-focus_array.min())/focus_array.max()*255, np.uint8)
    #plt_imshow(focus_array, vmin=focus_array.min(), vmax=focus_array.max())
    highlight_mask = focus_array > np.percentile(focus_array.astype(np.float32), percentile, overwrite_input=True)
    highlight_image = image_array.copy()
    highlight_image[:, :, :] = focus_array[:, :, None]
    new_mask = np.zeros_like(highlight_image, dtype=bool)
    #new_mask[:,:,1] = highlight_mask
    new_mask[:,:,0] = highlight_mask
    #highlight_image[highlight_mask] = 255 - highlight_image[highlight_mask]
    #highlight_image[new_mask] = 255
    #plt_imshow(255*highlight_mask.astype(np.uint8))
    #plt_imshow(highlight_image)
    return ndarray_to_qimage(
        highlight_image,
        QImage.Format.Format_RGB888,
    )


class ImageProvider(QQuickImageProvider):
    """
    Provides images from memory to QML
    """

    def __init__(self):
        super().__init__(QQmlImageProviderBase.ImageType.Image)
        self.images: dict[str, QImage] = {}

    def addImageFromBuffer(self, id: str, buffer: memoryview, buffer_info: dict):
        if buffer_info["format"] == "jpeg":
            image = QImage.fromData(buffer.tobytes("C"), "JPG")
            if "rotation" in buffer_info and buffer_info["rotation"] != 0:
                transform = QTransform().rotate(buffer_info["rotation"])
                image = image.transformed(transform, mode=Qt.TransformationMode.SmoothTransformation)
            self.images[id] = image
            logger.debug(f"Added image to id: {id}")
        else:
            logger.warning(f"Unknown image format: {buffer_info['format']} for id: {id}")

    def requestImage(self, id: str, size: QSize, requestedSize: QSize, /):
        if id in self.images:
            image: QImage = self.images[id]
            size.setWidth(image.width())
            size.setHeight(image.height())
            return self.images[id]
        elif id.removeprefix("focus-") in self.images:
            image: QImage = self.images[id.removeprefix("focus-")]
            image = focus_highlight(image, 90)
            size.setWidth(image.width())
            size.setHeight(image.height())
            return image
        elif id.removeprefix("zoomed-") in self.images:
            image: QImage = self.images[id.removeprefix("zoomed-")]
            w, h = image.width(), image.height()
            zoomed_image = image.copy(w//3, h//3, w//3, h//3)
            size.setWidth(zoomed_image.width())
            size.setHeight(zoomed_image.height())
            return zoomed_image
        elif id.removeprefix("align-") in self.images:
            display_width, display_height = 640, 480
            target_line_width = 1 #  pixel
            image: QImage = self.images[id.removeprefix("align-")]
            nd_image = qimage_to_ndarray_rgb(image)
            shape = nd_image.shape
            width, height = shape[0], shape[1]
            if shape[0] > shape[1]:
                width_margin = ceil((width*target_line_width/display_width - 1)/2)
                height_margin = ceil((height*target_line_width/display_height - 1)/2)
            else:
                width_margin = ceil((width*target_line_width/display_height - 1)/2) # assuming a rotation
                height_margin = ceil((height*target_line_width/display_width - 1)/2)
            nd_image[shape[0]//2-width_margin:shape[0]//2+width_margin, :] = np.array([255, 0, 0])
            nd_image[:, shape[1]//2-height_margin:shape[1]//2+height_margin] = np.array([255, 0, 0])
            aligned_image = ndarray_to_qimage(nd_image, QImage.Format.Format_RGB888)
            size.setWidth(aligned_image.width())
            size.setHeight(aligned_image.height())
            return aligned_image
        else:
            return QImage()


imageProvider = ImageProvider()
__all__ = ["imageProvider"]

def block_mean(ar: np.ndarray, fact: int) -> np.ndarray:
    assert isinstance(fact, int), type(fact)
    sx, sy, *others = ar.shape
    assert len(others) <= 1, f"no more than 3 dimensions are allowed, got {len(others)+2}"
    X, Y = np.ogrid[0:sx, 0:sy]
    regions = sy//fact * (X//fact) + Y//fact
    if others:
        max_ = regions.max()
        regions = np.expand_dims(regions, axis=2).repeat(others[0], axis=2)
        regions *= others[0]
        for i in range(1, others[0]):
            regions[:, :, i] += i
    res = scipy.ndimage.mean(ar, labels=regions, index=np.arange(regions.max() + 1))
    res.shape = (sx//fact, sy//fact, *others)
    return np.astype(res, np.uint8)

if __name__ == "__main__":
    import matplotlib.pyplot as plt

    image_ = plt.imread("/home/arthur/Images/RDPiades_2023/camera2/DSC_0100.JPG")
    #image = block_mean(image, 1)
    image_qt = ndarray_to_qimage(image_, QImage.Format.Format_RGB888)
    image_qt = focus_highlight(image_qt, 60)




