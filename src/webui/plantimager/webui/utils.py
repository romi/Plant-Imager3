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

import requests
import toml
from dash import dcc
from plantdb.client.rest_api import base_url
from plantdb.client.rest_api import list_scan_names
from plantdb.client.rest_api import parse_scans_info

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

def get_dataset_dict(host: str, port: str) -> dict[str, Any] | None:
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
    plantdb.rest_api_client.list_scan_names
    plantdb.rest_api_client.parse_scans_info
    """
    scans_list = list_scan_names(host, port)
    if len(scans_list) > 0:
        dataset_dict = parse_scans_info(host, port)
    else:
        dataset_dict = None
    return dataset_dict


def pipeline_cfg_url(host: str, port: str, scan_id: str) -> str:
    """Get the URL corresponding to the 'pipeline.toml' backup file for the given scan ID in a PlantDB REST API.

    Parameters
    ----------
    host : str
        The hostname or IP address of the PlantDB REST API server.
    port : str
        The port number of the PlantDB REST API server.
    scan_id : str
        The name of the dataset to test for the reconstruction pipeline.

    Returns
    -------
    str
        The URL corresponding to the 'pipeline.toml' backup file for the given scan ID.
    """
    return f"{base_url(host, port)}/files/{scan_id}/pipeline.toml"


def get_pipeline_cfg(host: str, port: str, scan_id: str) -> dict[str, Any]:
    """Get the backup configuration file of the reconstruction pipeline for the given scan ID.

    Parameters
    ----------
    host : str
        The hostname or IP address of the PlantDB REST API server.
    port : str
        The port number of the PlantDB REST API server.
    scan_id : str
        The name of the dataset to test for the reconstruction pipeline.

    Returns
    -------
    dict[str, Any]
        The backup configuration for the reconstruction pipeline for the given scan ID.
        Returns an empty dictionary if no pipeline configuration is found.

    Examples
    --------
    >>> from plantimager.webui.utils import get_pipeline_cfg
    >>> get_pipeline_cfg('127.0.0.1','5000','real_plant')
    {}
    >>> cfg = get_pipeline_cfg('127.0.0.1','5000','real_plant_analyzed')
    """
    if has_pipeline_cfg(host, port, scan_id):
        return toml.loads(requests.get(pipeline_cfg_url(host, port, scan_id)).content.decode())
    else:
        return {}


def has_pipeline_cfg(host: str, port: str, scan_id: str) -> bool:
    """Test if a named dataset has a reconstruction pipeline.

    Reconstruction pipeline is named 'pipeline.toml', so we test if the request from the file ressource is ok.

    Parameters
    ----------
    host : str
        The hostname or IP address of the PlantDB REST API server.
    port : str
        The port number of the PlantDB REST API server.
    scan_id : str
        The name of the dataset to test for the reconstruction pipeline.

    Returns
    -------
    bool
        Indicates if a reconstruction pipeline is found.

    Examples
    --------
    >>> from plantimager.webui.utils import has_pipeline_cfg
    >>> has_pipeline_cfg('127.0.0.1','5000','real_plant')
    False
    >>> has_pipeline_cfg('127.0.0.1','5000','real_plant_analyzed')
    True
    """
    return requests.get(pipeline_cfg_url(host, port, scan_id)).ok


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
