#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Scan Configuration and Execution Components for Plant Imager Web UI.

This module provides the user interface components and functionality for configuring
and executing plant scans in the Plant Imager system.

Key Features
------------
- TOML-based scan configuration editor
- Dataset name validation with real-time feedback
- Scan execution controls with status reporting
- Configuration file upload functionality
- Comprehensive error handling and user feedback
"""

import os
import tomllib
from base64 import b64decode
from typing import Dict

import dash_bootstrap_components as dbc
import diskcache
import zmq
from dash import DiskcacheManager
from dash import Input
from dash import Output
from dash import State
from dash import callback
from dash import dcc
from dash import html
from dash.exceptions import PreventUpdate
from plantdb.client.rest_api import plantdb_url

from plantimager.commons.RPC import NoResult
from plantimager.webui.controller_proxy import RPCController
from plantimager.webui.utils import config_upload

#: Characters not allowed in dataset names for system compatibility
FORBIDDEN_CHAR = [":", "/", "*", "#", "@", ">", "<", "?", "|", "\"", "\'"]

cache = diskcache.Cache("./cache")
background_callback_manager = DiskcacheManager(cache)

#: Get the directory where the current script (scan.py) is located
current_dir = os.path.dirname(os.path.abspath(__file__))
#: Construct the path to the sample TOML config file (`assets` directory)
default_toml_path = os.path.join(current_dir, 'assets', 'config_scan.toml')
#: Load the default TOML configuration file into a string variable
with open(default_toml_path, 'r') as f:
    default_toml = f.read()

# Card for scan configuration settings using TOML format
configuration_card = [
    dbc.Card(
        id="configuration-card",
        children=[
            dbc.CardHeader(children=[html.I(className="bi bi-code-square me-2"), "Configuration"]),
            dbc.CardBody([
                dbc.Textarea(id="scan-cfg-toml", class_name="mb-3", size='md',
                             value=default_toml,
                             title="The scan configuration in TOML format.",
                             placeholder="Scan configuration (TOML).",
                             style={'height': "65vh"}, persistence=True),
            ]),
            dbc.CardFooter([
                config_upload(),
            ], style={"align-content": 'center'})
        ]
    )
]

# Card for dataset name input with validation
dataset_name_card = [
    dbc.Card(
        id="dataset-card",
        children=[
            dbc.CardHeader(children=[html.I(className="bi bi-tag me-2"), "Dataset"]),
            dbc.CardBody(children=[
                html.Div([
                    dbc.Label("Name of the dataset to create:"),
                    dbc.Input(id="dataset-input-name", placeholder="Dataset name",
                              class_name="mb-3", invalid=True, persistence=True),
                    dbc.FormText(dcc.Markdown(
                        "The list of forbidden characters is: " + ', '.join([f'`{c}`' for c in FORBIDDEN_CHAR])
                    )),
                ]),
                html.Div(children=[
                    dbc.Alert(
                        "Dataset name already exists. Please choose a different name.",
                        color="danger",
                        dismissable=True
                    )
                ], id='dataset-exists-message', style={'display': 'none'}),
            ]),
        ]
    )
]

camera_card = [
    dbc.Card(
        id="camera-card",
        children=[
            dbc.CardHeader(children=[html.I(className="bi bi-camera me-2"), "Camera"]),
            dbc.CardBody(
                children=[
                    dcc.Markdown(id="available-cameras", children="No camera connected")
                ]
            ),
        ]
    )
]

# Card containing scan controls and status information
scan_card = [
    dbc.Card(
        id="scan-card",
        children=[
            dbc.CardHeader(children=[html.I(className="bi bi-upc-scan me-2"), "Scan"]),
            dbc.CardBody([
                dbc.Row([
                    # --- Scanner Configuration Button ---
                    dbc.Col([
                        dbc.Button(
                            children=[
                                html.I(className="bi bi-gear-fill me-2"),
                                'Configure Scanner'
                            ],
                            id='config-scan-button',
                            color="primary",
                            style={'width': '100%'},
                        ),
                    ], width=3),
                    # --- Start Scan Button ---
                    dbc.Col([
                        dbc.Button(
                            children=[
                                html.I(className="bi bi-play-fill me-2"),
                                'Start Scanning'
                            ],
                            id='start-scan-button',
                            color="success",
                            style={'width': '100%'},
                        ),
                    ], width=3),
                    # --- Cancel Scan Button ---
                    dbc.Col([
                        dbc.Button(
                            children=[
                                html.I(className="bi bi-x-circle-fill me-2"),
                                'Cancel Scan'
                            ],
                            id='cancel-scan-button',
                            disabled=True,  # inactive by default
                            color="danger",
                            style={'width': '100%'},
                        ),
                    ], width=3),
                ], align="center"),
                # --- Scan Output Section
                dbc.Row([
                    dbc.Col([
                        dbc.Alert(
                            id='scan-response',
                            children="Configure or start a scann to the the ouptut here...",
                            color="secondary",
                            className="mb-0",
                            style={'display': 'none', 'color': 'gray'}
                        )
                    ], width="auto"),
                ], align="center", style={"margin-top": "15px"}),
                # --- Scan ProgressBar Section
                dbc.Row([
                    dbc.Col([
                        dcc.Interval(id='scan-progress-interval', disabled=True, interval=1000),
                        dbc.Progress(
                            id='scan-progress', style={"margin-top": "15px"}, className="mb-3"
                        ),
                    ])
                ])
            ]),
            dbc.CardFooter([
                dbc.Accordion(
                    dbc.AccordionItem(children=[
                        dcc.Markdown(id="scan-output", children="_Run a scan first..._"),
                    ],
                        title="Detailed scan output:"
                    ),
                    start_collapsed=True, flush=True
                )
            ], style={'bs-accordion-btn-bg': '#21252908'})
        ]
    )
]

# Main container for the "scan" layout: two equally sized columns
# Left column, containing the configuration card
# Right column, containing multiple stacked cards
scan_layout = html.Div(
    children=[
        dcc.Interval(id='main-interval', disabled=False, interval=4000),
        dbc.Row([
            dbc.Col(configuration_card, md=6),
            dbc.Col(dataset_name_card + [html.Br()] + camera_card + [html.Br()] + scan_card, md=6)
        ])
    ], id="scan-page-layout"
)

progress = 0
max_progress = 100
available_cameras = []


def update_progress(val):
    global progress
    progress = val


def update_max_progress(val):
    global max_progress
    max_progress = val


def update_available_cameras(val):
    global available_cameras
    available_cameras = val


@callback(
    Output("available-cameras", "children"),
    Input("main-interval", "n_intervals"))
def update_interval(n_intervals):
    """Updates various components on a timer.

    Returns
    -------
    str
        Markdown message which is printed at 'available-cameras'.
    """
    try:
        controller = RPCController.instance()
    except RuntimeError as e:
        return f"**Controller not connected**: {e}"
    if update_available_cameras not in controller.cameraNamesChanged.connections:
        controller.cameraNamesChanged.connect(update_available_cameras)
        update_available_cameras(controller.camera_names)

    if available_cameras:
        lines = []
        for camera in available_cameras:
            lines.append(f"- {camera}")
        return "\n".join(lines)
    else:
        return "No camera connected"


@callback(Output('scan-cfg-toml', 'value'),
          Input('cfg-upload', 'contents'),
          prevent_initial_call=True)
def update_toml_cfg(contents: str) -> str:
    """Updates the TOML configuration text area with the content of the uploaded base64 encoded config file.

    Parameters
    ----------
    contents : str
        The base64 encoded string of the config file, containing both the
        content type and the encoded content, separated by a comma.

    Returns
    -------
    str
        The decoded TOML configuration string extracted from the uploaded
        base64 encoded config file.
    """
    # Parse base64 encoded config file contents and update TOML text area
    content_type, content_string = contents.split(',')
    cfg = b64decode(content_string)
    return cfg.decode()


@callback(
    Output('scan-cfg-toml', 'valid'),
    Output('scan-cfg-toml', 'invalid'),
    Input('scan-cfg-toml', 'value'),
)
def validate_toml_textarea(toml_text: str) -> tuple[bool, bool]:
    """Validate the TOML configuration entered by the user."""
    # Empty textarea should not be flagged
    if not toml_text:
        return False, False

    try:
        # Attempt to parse the TOML; we only care about success/failure
        tomllib.loads(toml_text)
        # Valid TOML → keep normal appearance
        return True, False
    except Exception:
        # Invalid TOML → add a red border for visual feedback
        return False, True


def all_valid_characters(dataset_name: str) -> bool:
    """Validates if all characters in a given dataset name are permissible.

    Parameters
    ----------
    dataset_name : str
        The name of the dataset to be validated.

    Returns
    -------
    bool
        ``True`` if all characters in the dataset name are valid otherwise, ``False``.
    """
    return sum([letter in FORBIDDEN_CHAR for letter in dataset_name]) == 0


def is_valid_dataset_name(dataset_name: str, existing_datasets: list[str]) -> bool:
    """Check if a dataset name is valid and does not already exist.

    Parameters
    ----------
    dataset_name : str
        The name of the dataset to be validated.
    existing_datasets : list of str
        A list of dataset names that already exist.

    Returns
    -------
    bool
        ``True`` if the dataset name is valid and does not exist in the list of
        existing datasets, ``False`` otherwise.
    """
    if dataset_name not in existing_datasets and all_valid_characters(dataset_name):
        return True
    else:
        return False


# Callback to validate the selected dataset name:
@callback(
    Output('dataset-input-name', 'invalid'),
    Output('dataset-input-name', 'valid'),
    Output('dataset-id', 'data'),
    Input('dataset-input-name', 'value'),
    State('dataset-list', 'data')
)
def validate_dataset_name(dataset_name: str, existing_datasets: list[str]) -> tuple[bool, bool, str]:
    """Callback to validate the selected dataset name.

    It should follow two rules:
        1. unicity: it should not exist in the database
        2. decency: no fancy/weird/impossible characters are allowed!

    Parameters
    ----------
    dataset_name : str
        The dataset name to validate.
    existing_datasets : list
        The dataset indexed dictionary that exists in the database.

    Returns
    -------
    bool
        The `invalid` state of the 'dataset-input-name' `Input` component.
    bool
        The `valid` state of the 'dataset-input-name' `Input` component.
    str
        The name of the dataset.
    """
    if dataset_name is not None and is_valid_dataset_name(dataset_name, existing_datasets):
        return False, True, dataset_name
    else:
        return True, False, dataset_name


@callback(
    Output('dataset-exists-message', 'style'),
    Input('dataset-input-name', 'value'),
    State('dataset-list', 'data')
)
def check_dataset_name_uniqueness(dataset_name: str, existing_datasets: list[str]) -> dict[str, str]:
    """Check if the specified dataset name already exists.

    Parameters
    ----------
    dataset_name : str
        The name of the dataset input by the user, which needs to be checked
        for uniqueness.
    existing_datasets : list of str
        A list containing the names of datasets that already exist.

    Returns
    -------
    Dict[str, str]
        A style dictionary for controlling the visibility of a message. If the
        dataset name already exists, the dictionary will display the message.
        Otherwise, it will hide the message.
    """
    if dataset_name in existing_datasets:
        return {'display': 'block', 'margin-top': '10px'}
    else:
        return {'display': 'none'}


@callback(
    Output('start-scan-button', 'disabled'),
    Output('config-scan-button', 'disabled'),
    Input('dataset-input-name', 'valid'),
    Input('main-interval', 'n_intervals'),
    State('start-scan-button', 'disabled')
)
def disable_scan_button(valid: bool, n_intervals: int, previous_state: bool) -> tuple[bool, bool]:
    """Disables the 'Start scanning' button based on dataset validation status and if scanner is connected.

    This callback function determines whether the 'start-scan-button' element
    should be disabled or enabled based on the validity of input provided
    to the 'dataset-input-name' element. If the input is not valid, the
    'start-scan-button' is disabled.

    Parameters
    ----------
    valid : bool
        Indicates whether the dataset input is valid.
        ``True`` if valid, ``False`` otherwise.
    n_intervals : int
        Number of times interval is raised

    Returns
    -------
    bool
        Returns ``True`` if the scan button should be disabled, and ``False``
        if it should be enabled.
    """
    try:
        RPCController.instance()
    except RuntimeError:
        if previous_state:
            raise PreventUpdate
        return True, True
    if previous_state == (not valid):
        raise PreventUpdate
    return not valid, not valid


@callback(
    Output('scan-response', 'children'),
    Output('scan-output', 'children', allow_duplicate=True),
    Input('start-scan-button', 'n_clicks'),
    State('plantdb-host', 'data'),
    State('plantdb-port', 'data'),
    State('plantdb-prefix', 'data'),
    State('plantdb-ssl', 'data'),
    State('access-token', 'data'),
    State('scan-cfg-toml', 'value'),
    State('dataset-input-name', 'value'),
    background=True,
    manager=background_callback_manager,
    prevent_initial_call=True,
    running=[
        (Output('start-scan-button', 'disabled', allow_duplicate=True), True, False),
        (Output('config-scan-button', 'disabled'), True, False),
        (Output('scan-response', 'children'), 'Scan in progress', ""),
        (Output('scan-output', 'children'), 'Scan in progress', ""),
        (Output('cancel-scan-button', 'disabled', allow_duplicate=True), False, True),
    ],
    progress=[
        Output('scan-progress', 'value'),
        Output('scan-progress', 'max'),
        Output('scan-progress', 'label'),
    ]
)
def run_scan(set_progress, _, url: str, port: str, prefix: str, ssl: bool, access_token: str, cfg: str,
             dataset_name: str):
    """Execute a plant scan with the specified configuration.

    Parameters
    ----------
    _ : Any
        Unused parameter (n_clicks from the button).
    url : str
        The hostname or IP address of the PlantDB REST API server.
    port : str
        The port number of the PlantDB REST API server.
    prefix : str
        The prefix of the PlantDB REST API server.
    ssl : bool
        Whether the PlantDB REST API server is using SSL.
    access_token : str
        The PlantDB REST API access token of the user.
    cfg : str
        The TOML configuration string for the scan.
    dataset_name : str
        The name to use for the dataset that will be created.

    Returns
    -------
    Tuple[str, str]
        A tuple containing two status messages:
        - First message: Short status for the alert component
        - Second message: Detailed status for the output component

    Raises
    ------
    RuntimeError
        If the Raspberry Pi Controller is not initialized.
    """
    # Background callbacks run in a new process. We must re-init the ZMQ context and Controller proxy.
    ctx = zmq.Context()
    # Using the same URL as app.py
    controller = RPCController(ctx, "tcp://localhost:14567")

    res: None | NoResult = controller.set_db_url(plantdb_url(url, port=port, prefix=prefix, ssl=ssl))
    if isinstance(res, NoResult):
        return f"Failed to connect to {'https' if ssl else 'http'}://{url}:{port}{prefix}", res.traceback
    res: None | NoResult = controller.set_session_token(access_token)
    if isinstance(res, NoResult):
        return "Failed to connect to set access token.", res.traceback
    res: None | NoResult = controller.set_dataset_name(dataset_name)
    if isinstance(res, NoResult):
        return f"Failed to set dataset {dataset_name}", res.traceback
    res: None | NoResult = controller.set_config(tomllib.loads(cfg))
    if isinstance(res, NoResult):
        return "Failed to configure scann", res.traceback

    m_prog = controller.max_progress

    def _update_progress(prog):
        set_progress((str(prog), str(m_prog), f"{prog}/{m_prog}"))

    controller.progressChanged.connect(_update_progress)

    res: None | NoResult = controller.run_scan()
    if isinstance(res, NoResult):
        return "Scan Failed", res.traceback

    return "Scan finished", "Scan complete"


@callback(
    Output('scan-response', 'children', allow_duplicate=True),
    Input('cancel-scan-button', 'n_clicks'),
    prevent_initial_call=True,
)
def cancel_scan(_):
    """Placeholder callback for the Cancel Scan button."""
    # TODO: implement actual cancellation logic
    return "Cancelling scan..."


@callback(
    Output('scan-response', 'children', allow_duplicate=True),
    Output('scan-output', 'children', allow_duplicate=True),
    Input('config-scan-button', 'n_clicks'),
    State('plantdb-host', 'data'),
    State('plantdb-port', 'data'),
    State('plantdb-prefix', 'data'),
    State('plantdb-ssl', 'data'),
    State('scan-cfg-toml', 'value'),
    State('dataset-input-name', 'value'),
    prevent_initial_call=True,
)
def config_scan(_, url: str, port: str, prefix: str, ssl: bool, cfg: str, dataset_name: str):
    """Configure a plant scan with the specified configuration.

    Parameters
    ----------
    _ : Any
        Unused parameter (n_clicks from the button).
    url : str
        The hostname or IP address of the PlantDB REST API server.
    port : str
        The port number of the PlantDB REST API server.
    prefix : str
        The prefix of the PlantDB REST API server.
    ssl : bool
        Whether the PlantDB REST API server is using SSL.
    cfg : str
        The TOML configuration string for the scan.
    dataset_name : str
        The name to use for the dataset that will be created.

    Returns
    -------
    Tuple[str, str]
        A tuple containing two status messages:
        - First message: Short status for the alert component
        - Second message: Detailed status for the output component

    Raises
    ------
    RuntimeError
        If the Raspberry Pi Controller is not initialized.
    """
    try:
        controller = RPCController.instance()
    except RuntimeError as e:
        return "Error: Raspberry Pi Controller not initialized!", str(e)

    res: None | NoResult = controller.set_db_url(plantdb_url(url, port=port, prefix=prefix, ssl=ssl))
    if isinstance(res, NoResult):
        return f"Failed to connect to {'https' if ssl else 'http'}://{url}:{port}{prefix}", res.traceback
    res: None | NoResult = controller.set_dataset_name(dataset_name)
    if isinstance(res, NoResult):
        return f"Failed to set dataset {dataset_name}", res.traceback
    res: None | NoResult = controller.set_config(tomllib.loads(cfg))
    if isinstance(res, NoResult):
        return "Failed to configure scan", res.traceback

    return "Scan configured", "Scan configured, ready to start"


@callback(
    Output('scan-progress', 'value'),
    Output('scan-progress', 'max'),
    Output('scan-progress', 'label'),
    Input('scan-progress-interval', 'n_intervals'),
)
def progress_bar_update(n_int):
    return progress, max_progress, f"{progress}/{max_progress}"
