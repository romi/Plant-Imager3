"""
Use the scanner to calibrate the cameras by moving the cameras around while looking at a calibration target.


"""
import time
from importlib.metadata import metadata
from typing import List

import numpy as np

from plantimager.commons.logging import create_logger
from plantimager.controller.camera.PiCameraComm import PiCameraComm
from plantimager.controller.scanner.grbl import CNC
from plantimager.controller.camera.CameraBridge import CameraBridge
import cv2
from pyransac.ransac import find_inliers, RansacParams
from pyransac.base import Model as RansacBaseModel
from PySide6.QtCore import QAbstractTableModel, Qt, QModelIndex

logger = create_logger(__name__)


class CameraTableModel(QAbstractTableModel):
    def __init__(self, cameras_dict, parent=None):
        super().__init__(parent)
        self.cameras = cameras_dict
        # Get primary keys (camera names) as list to maintain order
        self.camera_names = sorted(cameras_dict.keys())
        # Get secondary keys (column headers) - excluding 'camera' object if you want
        if self.camera_names:
            # All secondary keys from the first camera entry
            self.columns = ["camera name"] + [
                key for key in cameras_dict[self.camera_names[0]].keys()
                if key in ["theta", "fx", "fy", "cx", "cy", "dist"]
            ]
        else:
            self.columns = ["camera name"]

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0
        return len(self.camera_names)

    def columnCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0
        return len(self.columns)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        if role == Qt.ItemDataRole.DisplayRole:
            row = index.row()
            col = index.column()

            camera_name = self.camera_names[row]

            # First column is the camera name
            if col == 0:
                return camera_name

            # Other columns are the secondary keys
            key = self.columns[col]
            value = self.cameras[camera_name][key]

            # Format the value for display
            if isinstance(value, float):
                return f"{value:.2f}"
            elif isinstance(value, list):
                return f"[{len(value)} items]"
            elif value is None:
                return "None"
            else:
                return str(value)

        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Horizontal:
                return self.columns[section]
            elif orientation == Qt.Orientation.Vertical:
                return str(section + 1)
        return None

    def updateData(self, cameras_dict):
        """Method to update the model with new data"""
        self.beginResetModel()
        self.cameras = cameras_dict
        self.camera_names = sorted(cameras_dict.keys())
        if self.camera_names:
            self.columns = ["camera name"] + [key for key in cameras_dict[self.camera_names[0]].keys()]
        else:
            self.columns = ["camera name"]
        self.endResetModel()

class ParallaxCalibModel(RansacBaseModel):

    def __init__(self, dx, dy, cx, cy, f, theta):
        self.dx = dx
        self.dy = dy
        self.cx = cx
        self.cy = cy
        self.f = f
        self.theta = theta

    def make_model(self, points: List) -> None:
        """
        Find best f and theta that match the points. Each point is (u_1, v1, u_2, v2, u_3, v_3, u_4, v_4)

        We have the following equations:
        -dx*cos(theta) = f*A
        -dx*sin(theta) = A*(v_3 - c_y) + B

        with:
        A = dy*(1/(u_4 - u_3) - 1/(u_2 - u_1))
        B = dy*(v_3 - v_1)/(u_2 - u_1)

        Parameters
        ----------
        points: List
            List of points to fit the model to.
            Each point is (u_1, v1, u_2, v2, u_3, v_3, u_4, v_4)

        Returns
        -------

        """
        points = np.array(points)
        u = points[:, ::2]
        v = points[:, 1::2]
        A = self.dy * (1/(u[:, 3] - u[:, 2]) - 1/(u[:, 1] - u[:, 0]))
        B = self.dy * (v[:, 3] - v[:, 0])/(u[:, 1] - u[:, 0])
        sign_cos_theta = np.sign(-A/self.dx)
        theta = np.arcsin(-(A*(v[:, 2] - self.cy) + B)/self.dx)
        theta[sign_cos_theta == -1] = np.pi - theta[sign_cos_theta == -1]
        f = -self.dx*np.cos(theta)/A
        self.f = np.mean(f)
        self.theta = np.mean(theta)

    def calc_error(self, point) -> float:
        """Calculate the error of the model."""
        u = point[::2]
        v = point[1::2]
        A = self.dy * (1/(u[3] - u[2]) - 1/(u[1] - u[0]))
        #B = self.dy * (v[3] - v[0])/(u[1] - u[0])
        return np.abs(self.f*A + self.dx*np.cos(self.theta))




class CharucoBoardParams:
    """Parameters for the CharucoBoard."""
    ARUCO_DICT = cv2.aruco.DICT_4X4_1000 # Dictionary ID
    SQUARES_VERTICALLY = 10              # Number of squares vertically
    SQUARES_HORIZONTALLY = 8             # Number of squares horizontally
    SQUARE_LENGTH = 2e-2                 # Square side length (in m)
    MARKER_LENGTH = 1.5e-2               # ArUco marker side length (in m)
    MARGIN_PX = 10                       # Margins size (in pixels)


def camera_in_world(x, y, z, theta, phi):
    """
    Computes the transformation matrix of a camera in the 3D world coordinate system.

    This function computes a 4x4 transformation matrix `F` that represents the
    camera's position and orientation in the world coordinate system. The matrix
    is calculated based on the camera's location in 3D space (`x`, `y`, `z`), as
    well as its orientation specified by angles `theta` and `phi`.

    Parameters
    ----------
    x : float
        The x-coordinate of the camera's position in the 3D world.
    y : float
        The y-coordinate of the camera's position in the 3D world.
    z : float
        The z-coordinate of the camera's position in the 3D world.
    theta : float
        The pan angle in radians, measuring rotation around the z-axis of the world frame.
    phi : float
        The tilt angle in radians, measuring rotation around the x-axis of the camera frame.

    Returns
    -------
    numpy.ndarray
        A 4x4 transformation matrix representing the camera's position and orientation
        in the world coordinate system. The resulting matrix is formatted as:
        ::
            [[  sin(theta),  cos(theta)*sin(phi),  cos(theta)*cos(phi),  x],
             [-cos(theta),  sin(theta)*sin(phi),  sin(theta)*cos(phi),   y],
             [        0,              -cos(phi),              sin(phi),  z],
             [        0,                     0,                     0,   1]]

    """
    F = np.array([
        [np.sin(theta), np.cos(theta)*np.sin(phi), np.cos(theta)*np.cos(phi), x],
        [-np.cos(theta), np.sin(theta)*np.sin(phi), np.sin(theta)*np.cos(phi), y],
        [0, -np.cos(phi), np.sin(phi), z],
        [0, 0, 0, 1]
    ])
    return F

def camera_matrix(f, cx, cy):
    """Builds the camera matrix from the intrinsic parameters."""
    return np.array([
        [f, 0, cx],
        [0, f, cy],
        [0, 0, 1]
    ])


def inverse_homogeneous_transform(F):
    """
    Compute the inverse of a homogeneous transformation matrix.

    This function takes a 4x4 homogeneous transformation matrix `F` as input
    and computes its inverse. A homogeneous transformation matrix consists of
    a rotation matrix `R` and a translation vector `t`. The inverse is computed
    by transposing the rotation matrix and applying it to the negative translation
    vector.

    Parameters
    ----------
    F : ndarray
        A 4x4 array representing the homogeneous transformation matrix.
        The matrix should have the following structure:
        [[R, t],
         [0, 1]]
        where `R` is a 3x3 rotation matrix and `t` is a 3x1 translation vector.

    Returns
    -------
    F_inv : ndarray
        A 4x4 array representing the inverse of the homogeneous transformation
        matrix. The output matrix will have the same structure as `F`:
        [[R.T, -R.T @ t],
         [0, 1]]

    Raises
    ------
    ValueError
        If the input matrix `F` is not 4x4 or does not have the expected structure.

    Notes
    -----
    - The function assumes that the input matrix `F` is a valid homogeneous
      transformation matrix. No checks are performed to validate if the input
      strictly follows the properties of a homogeneous transformation.
    """
    R = F[:3, :3]
    t = F[:3, 3]
    F_inv = np.eye(4)
    F_inv[:3, :3] = R.T
    F_inv[:3, 3] = -R.T @ t
    return F_inv


class Calibrate:

    def __init__(self, cnc: CNC, cameras: list[PiCameraComm]):
        self.cnc = cnc
        self.cameras = {}
        for cam in cameras:
            self.add_camera(cam)

        self.target = cv2.aruco.CharucoBoard(
            (CharucoBoardParams.SQUARES_VERTICALLY, CharucoBoardParams.SQUARES_HORIZONTALLY),
            CharucoBoardParams.SQUARE_LENGTH, CharucoBoardParams.MARKER_LENGTH,
            cv2.aruco.getPredefinedDictionary(CharucoBoardParams.ARUCO_DICT)
        )
        self.detector = cv2.aruco.CharucoDetector(self.target)

    def add_camera(self, cam: PiCameraComm):
        """Add a camera to the calibration."""
        resolution = cam.resolution
        logger.info(f"Adding camera {cam.name} with resolution {resolution}")
        from plantimager.controller.AppBridge import AppBridge
        bridges: list[CameraBridge] = AppBridge.instance.device_bridges
        bridge: CameraBridge = next(filter(lambda b: b.camera == cam, bridges))
        self.cameras[cam.name] = {
            "camera": cam,
            "bridge": bridge,
            "resolution": resolution,
            "rotation": cam.rotation,
            "theta": 0,
            "fx": max(resolution) * 1.2,
            "fy": max(resolution) * 1.2,
            "cx": resolution[1] / 2,
            "cy": resolution[0] / 2,
            "dist": None,
            "detections": [] # list of (charuco_corners, charuco_ids) tuples
        }

    def remove_camera(self, camera: PiCameraComm):
        """Remove a camera from the calibration."""
        if camera in self.cameras: self.cameras.pop(camera.name)

    def _update_camera_params(self):
        """Update and resets the camera parameters."""
        for cam_name, cam_dict in self.cameras.items():
            camera = cam_dict["camera"]
            resolution = camera.resolution
            rotation = camera.rotation
            if cam_dict["fx"] == cam_dict["fy"] == max(cam_dict["resolution"]) * 1.2:
                # default values
                cam_dict["fx"] = max(resolution) * 1.2
                cam_dict["fy"] = max(resolution) * 1.2
            cam_dict["rotation"] = rotation
            cam_dict["resolution"] = resolution
            cam_dict["theta"] = 0
            cam_dict["cx"] = resolution[1] / 2
            cam_dict["cy"] = resolution[0] / 2
            cam_dict["dist"] = None
            cam_dict["detections"] = []

    def _grab_images_and_detect(self):
        """Grab images from the cameras and detect the ChAruco target. Stores the detections in the camera dict."""
        from plantimager.controller.main import app
        futures = []
        for cam_name, cam_dict in self.cameras.items():
            cam = cam_dict["camera"]
            futures.append((cam_name, cam.getImage(lores=False)))

        for cam_name, future in futures:
            image_buffer, image_metadata = future.result()
            bridge: CameraBridge = self.cameras[cam_name]["bridge"]
            bridge._newImage(image_buffer, image_metadata)
            app.processEvents()
            image = cv2.imdecode(np.frombuffer(image_buffer, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
            if image_metadata["rotation"] == 90:
                image = cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
            # extract 2d points for the target
            charuco_corners, charuco_ids, aruco_corners, aruco_ids = self.detector.detectBoard(image)
            logger.debug(self.detector)
            logger.debug(image.shape)
            logger.debug("=====================")
            logger.debug(charuco_corners)
            logger.debug(charuco_ids)
            logger.debug("=====================")
            self.cameras[cam_name]["detections"].append((charuco_corners, charuco_ids))

    def _calibrate_all_images(self):
        """Calibrate fully"""

        for cam_name, cam_dict in self.cameras.items():
            K_init = np.array([
                [cam_dict["fx"], 0, cam_dict["cx"]],
                [0, cam_dict["fy"], cam_dict["cy"]],
                [0, 0, 1]
            ])
            corners, ids = [], []
            for charuco_corners, charuco_ids in cam_dict["detections"]:
                corners.append(charuco_corners)
                ids.append(charuco_ids)
            result, mtx, dist, rvecs, tvecs = cv2.aruco.calibrateCameraCharuco(
                corners, ids, self.target, cam_dict["resolution"], cameraMatrix=K_init,
                distCoeffs=None,
                flags=cv2.CALIB_FIX_K3 | cv2.CALIB_USE_INTRINSIC_GUESS | cv2.CALIB_FIX_PRINCIPAL_POINT,
            )
            cam_dict["fx"] = mtx[0, 0]
            cam_dict["fy"] = mtx[1, 1]
            cam_dict["cx"] = mtx[0, 2]
            cam_dict["cy"] = mtx[1, 2]
            cam_dict["dist"] = dist
            logger.info(f"Camera {cam_name} focal length estimated: {cam_dict['fx']}, {cam_dict['fy']} with confidence {result:.3f}")
            logger.info(f"Camera distortion coefficients estimated: {cam_dict['dist']}")

    def _calibrate_parallax(self, dx, dy):
        """Using the parallax, we can recover f_x and theta from the first 4 images."""
        logger.info("Calibrating using the parallax method")
        for cam_name, cam_dict in self.cameras.items():
            logger.info(f"Calibrating camera {cam_name}")
            raw_points: list[np.ndarray] = []
            ids: list[np.ndarray] = []
            assert len(cam_dict["detections"]) == 4, "must have 4 detections to calibrate"
            for charuco_corners, charuco_ids in cam_dict["detections"]:
                raw_points.append(charuco_corners[:, 0, :]) # (v, u) --> (u, v)
                assert np.all(charuco_ids[:-1] <= charuco_ids[1:]), "ids must be sorted"
                ids.append(charuco_ids[:, 0])

            # find the common ids across the 4 images and only consider points with those ids
            common_ids = np.intersect1d(ids[0], ids[1])
            for i in range(2, len(ids)):
                common_ids = np.intersect1d(common_ids, ids[i])
            points = np.zeros((len(common_ids), 8))
            for i, p in enumerate(raw_points):
                mask = np.isin(ids[i], common_ids, assume_unique=True)
                points[:, i*2:i*2+2] = p[mask, :]
            points = points.tolist()

            model = ParallaxCalibModel(dx, dy, cam_dict["cx"], cam_dict["cy"], cam_dict["fx"], 0)
            ransac_params = RansacParams(int(0.1*len(points)), 1000, 0.5, 1e-2*dx)
            inliers = find_inliers(points, model, ransac_params)
            model.make_model(inliers)
            cam_dict["fx"] = model.f
            cam_dict["fy"] = model.f
            cam_dict["theta"] = model.theta*180/np.pi #  degrees
            error = np.mean([model.calc_error(p) for p in points])
            logger.info(f"Camera {cam_name} focal length estimated: {cam_dict['fx']} with confidence {error:.3f}")
            logger.info(f"Camera tilt estimated: {cam_dict['theta']:.1f} deg")


    def calibrate(self, fast=False):
        """Calibrate the cameras."""

        self._update_camera_params()

        dx = 80
        dy = 80
        x0 = 25
        y0 = 375


        # move to the initial position facing the target,
        # then capture a group of four pictures at the 4 corners of a rectangle in the plane (x_r, y_r)
        self.cnc.moveto(x0, y0, 0)
        time.sleep(1)
        self._grab_images_and_detect()

        self.cnc.moveto(x0, y0 + dy, 0)
        time.sleep(1)
        self._grab_images_and_detect()

        self.cnc.moveto(x0 + dx, y0, 0)
        time.sleep(1)
        self._grab_images_and_detect()

        self.cnc.moveto(x0 + dx, y0 + dy, 0)
        time.sleep(1)
        self._grab_images_and_detect()

        self._calibrate_parallax(dx, dy)

        if fast:
            return

        # use position information and initial focal lengths to estimate f_x and theta to create a path
        # with which the calibration pattern will captured around the image

        for cam_name, cam_dict in self.cameras.items():
            c_F_w = camera_in_world(x0, y0, 0, cam_dict["theta"], 0)
            points3d = self.target.getObjPoints()
            K = camera_matrix(cam_dict["fx"], cam_dict["cx"], cam_dict["cy"])
            res, rvec, tvec = cv2.solvePnP(points3d, cam_dict["detections"][0], K, None)

        self._calibrate_all_images()

    def get_table_model(self):
        return CameraTableModel(self.cameras)






if __name__ == "__main__":
    import re
    import pathlib
    import json
    import glob

    from plantimager.controller.scanner.dummy_cnc import DummyCNC


    calib = Calibrate(DummyCNC(), [])

    database_path = pathlib.Path("/home/arthur/Documents/test_db_plantdb/calib_4vues")
    images_path = database_path / "images"
    image_pattern = r"(.+)-([0-9]{5})\.jpe?g"
    camera_names = list(set(
        re.match(image_pattern, f.name).group(1)
        for f in images_path.iterdir()
    ))
    for cam_name in camera_names:
        print(cam_name)
        metadata_path = glob.glob(str(database_path / f"metadata/images/{cam_name}-*.json"))[0]
        with open(metadata_path, "r") as f:
            metadata = json.load(f)
        rotation = metadata["rotation"]
        resolution = (metadata["res_x"], metadata["res_y"])
        if rotation == 90:
            resolution = (resolution[1], resolution[0])
        cameradict = {
            "camera": None,
            "bridge": None,
            "resolution": resolution,
            "rotation": rotation,
            "theta": 0,
            "fx": max(resolution) * 1.2,
            "fy": max(resolution) * 1.2,
            "cx": resolution[1] / 2,
            "cy": resolution[0] / 2,
            "dist": None,
            "detections": [] # list of (charuco_corners, charuco_ids) tuples
        }
        calib.cameras[cam_name] = cameradict
    for path in sorted(images_path.iterdir()):
        print(path)
        cam_name = re.match(image_pattern, path.name).group(1)
        with open(path, "rb") as f:
            image_buffer = f.read()
        image = cv2.imdecode(np.frombuffer(image_buffer, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
        if rotation == 90:
            image = cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
        charuco_corners, charuco_ids, aruco_corners, aruco_ids = calib.detector.detectBoard(image)
        calib.cameras[cam_name]["detections"].append((charuco_corners, charuco_ids))

    calib._calibrate_parallax(80, 80)
    calib._calibrate_all_images()







