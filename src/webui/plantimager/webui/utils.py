#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Utility Functions for Plant Imager Web UI.

This module provides common utility functions used across the Plant Imager web interface,
particularly for interacting with the PlantDB REST API and handling configuration files.
"""

try:
    import pybase64 as base64
except ImportError:
    import base64
from typing import Any

from dash import dcc
from plantdb.client.rest_api import make_api_request
from plantdb.client.rest_api import parse_scans_info
from plantdb.client.rest_api import request_check_username
from plantdb.client.rest_api import request_scan_names_list

FONT_FAMILY = '"Nunito Sans", sans-serif'

TASKS = [
    "PointCloud",
    "TriangleMesh",
    "CurveSkeleton",
    "TreeGraph",
    "AnglesAndInternodes",
]

TASK_OBJECTS = [
    "PointCloud",
    "TriangleMesh",
    "TreeGraph",
    "FruitDirection",
    "StemDirection",
]

IMAGE_TASKS = [
    'images',
    'Undistorted',
    'Masks',
]


def get_dataset_dict(host: str, port: int, prefix: str, ssl: bool, access_token: str) -> dict[str, Any] | None:
    """Returns the dataset dictionary for the PlantDB REST API at a given host url and port.

    Parameters
    ----------
    host : str
        The hostname or IP address of the PlantDB REST API server.
    port : int
        The port number of the PlantDB REST API server.
    prefix : str
        The prefix of the PlantDB REST API server.
    ssl : bool
        Whether the PlantDB REST API server is using SSL or not.
    access_token
        The PlantDB REST API access token.

    Returns
    -------
    dict[str, Any] | None
        The dataset dictionary for the PlantDB REST API at a given host url and port.
        Returns ``None`` if no scans are found.

    Examples
    --------
    >>> from plantimager.webui.utils import get_dataset_dict
    >>> from plantdb.server.test_rest_api import TestRestApiServer
    >>> server = TestRestApiServer("/data/ROMI/shared_fsdb")
    >>> server.start()
    >>> dataset_dict = get_dataset_dict('localhost', port=5000, prefix='', ssl=False)
    >>> print(list(dataset_dict))
    ['arabidopsis000', 'real_plant', 'real_plant_analyzed', 'virtual_plant', 'virtual_plant_analyzed']
    >>> print(list(dataset_dict['real_plant_analyzed']['metadata']))
    ['date', 'species', 'plant', 'environment', 'nbPhotos', 'files']
    >>> server.stop()

    See Also
    --------
    plantdb.rest_api_client.request_scan_names_list
    plantdb.rest_api_client.parse_scans_info
    """
    scans_list = sorted(request_scan_names_list(host, port=port, prefix=prefix, ssl=ssl,
                                                access_token=access_token).json())
    if len(scans_list) > 0:
        dataset_dict = parse_scans_info(host, port=port, prefix=prefix, ssl=ssl, session_token=access_token)
    else:
        dataset_dict = None
    return dataset_dict


def config_upload() -> dcc.Upload:
    """The TOML configuration file upload component.

    Returns
    -------
    dcc.Upload
        A Dash Upload component configured for TOML files.
    """
    return dcc.Upload(
        children=['Drag and Drop or Select a TOML configuration file.'],
        id="cfg-upload",
        style={
            'width': '100%',
            'height': '60px',
            'lineHeight': '60px',
            'borderWidth': '1px',
            'borderStyle': 'dashed',
            'borderRadius': '5px',
            'textAlign': 'center',
        },
        accept=".toml",
        # Do not allow multiple files to be uploaded
        multiple=False
    )


def _validate_new_username(username: str, host: str, port: str, prefix: str, ssl: bool) -> bool:
    """Check if a username exists.

    Parameters
    ----------
    new_username : str
        The username to check for.
    host : str
       The hostname or IP address of the PlantDB REST API server.
    port : int
        The port number of the PlantDB REST API server.
    prefix : str
        The prefix of the PlantDB REST API server.

    Returns
    -------
    bool
        ``True`` if the username is available, ``False`` if it already exists or there was an error.
    """
    try:
        res_data = request_check_username(host, username, port=port, prefix=prefix, ssl=ssl)
        user_exists = res_data.get('exists', False)
        if user_exists:
            return False  # Unavailable username
        else:
            return True  # Available username
    except Exception as e:
        return False


def load_image_from_url(url, session_token=None):
    """Load an image from a given URL and encode it to a base64 data URI.

    Parameters
    ----------
    url : str
        The base URL to request.
    access_token : str
        AN access token used to authenticate against PlantDB.

    Returns
    -------
    str
        A base64‑encoded data URI containing the image, or a fallback string
        such as "No Image" or "Error Loading" when the fetch is unsuccessful.

    Examples
    --------
    >>> from plantimager.webui.utils import load_image_from_url
    >>> from plantdb.server.test_rest_api import TestRestApiServer
    >>> from plantdb.client.rest_api import scan_image_url
    >>> server = TestRestApiServer("/data/ROMI/shared_fsdb")
    >>> server.start()
    >>> # Load a very small image:
    >>> load_image_from_url(scan_image_url('localhost', "real_plant", "images", "00000_rgb", port=5000, size='10'))
    'data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAUEBAQEAwUEBAQGBQUGCA0ICAcHCBALDAkNExAUExIQEhIUFx0ZFBYcFhISGiMaHB4fISEhFBkkJyQgJh0gISD/2wBDAQUGBggHCA8ICA8gFRIVICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICD/wAARCAAIAAoDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwD5asPtK6SrCMOiqCTz8oJ71zUxzPIf9o/zooqVuwP/2Q=='
    >>> server.stop()
    """
    # Fetch image and convert to base64
    try:
        response = make_api_request(url=url, session_token=access_token, timeout=5)
        if response.status_code == 200:
            content_type = response.headers.get('content-type', 'image/jpeg')
            if not content_type.startswith('image'):
                return f"Not an image: {content_type}"
            encoded_img = base64.b64encode(response.content).decode('ascii')
            img_data = f"data:{content_type};base64,{encoded_img}"
        else:
            img_data = f"No Image: {response.status_code}"
    except Exception as e:
        img_data = f"Error Loading: {e}"
    return img_data
