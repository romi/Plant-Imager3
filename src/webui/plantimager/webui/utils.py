#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Utility Functions for Plant Imager Web UI.

This module provides common utility functions used across the Plant Imager web interface,
particularly for interacting with the PlantDB REST API and handling configuration files.

Key Features
------------
- Dataset retrieval and management
- Pipeline configuration handling
- TOML configuration file upload component
- REST API interaction helpers

Usage Examples
--------------
```python
>>> from plantimager.webui.utils import get_dataset_dict, has_pipeline_cfg
>>> # Get all datasets from the PlantDB server
>>> datasets = get_dataset_dict('localhost', '5000')
>>> # Check if a dataset has a pipeline configuration
>>> has_config = has_pipeline_cfg('localhost', '5000', 'my_plant_scan')
```
"""

from typing import Any

from dash import dcc
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


def get_dataset_dict(host: str, port: str, prefix: str) -> dict[str, Any] | None:
    """Returns the dataset dictionary for the PlantDB REST API at given host url and port.

    Parameters
    ----------
    host : str
        The hostname or IP address of the PlantDB REST API server.
    port : str
        The port number of the PlantDB REST API server.

    Returns
    -------
    dict[str, Any] | None
        The dataset dictionary for the PlantDB REST API at given host url and port.
        Returns ``None`` if no scans are found.

    See Also
    --------
    plantdb.rest_api_client.request_scan_names_list
    plantdb.rest_api_client.parse_scans_info
    """
    scans_list = request_scan_names_list(host, port=port, prefix=prefix)
    if len(scans_list) > 0:
        dataset_dict = parse_scans_info(host, port=port, prefix=prefix)
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
