#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
from base64 import b64decode

import dash_bootstrap_components as dbc
import toml
from dash import Input
from dash import Output
from dash import State
from dash import callback
from dash import dcc
from dash import html

from plantimager.webui.utils import config_upload

# Characters not allowed in dataset names for system compatibility
FORBIDDEN_CHAR = [":", "/", "*", "#", "@", ">", "<", "?", "|", "\"", "\'"]

# Get the directory where the current script (scan.py) is located
current_dir = os.path.dirname(os.path.abspath(__file__))
# Construct the path to the assets file
default_toml_path = os.path.join(current_dir, 'assets', 'hardware_scan_rx0.toml')

# Card for scan configuration settings using TOML format
configuration_card = [
    dbc.Card(
        id="configuration-card",
        children=[
            dbc.CardHeader(children=[html.I(className="bi bi-code-square me-2"), "Configuration"]),
            dbc.CardBody([
                dbc.Textarea(id="scan-cfg-toml", class_name="mb-3", size='md',
                             value=toml.dumps(toml.load(default_toml_path)),
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

# Card containing scan controls and status information
scan_card = [
    dbc.Card(
        id="scan-card",
        children=[
            dbc.CardHeader(children=[html.I(className="bi bi-camera me-2"), "Scan"]),
            dbc.CardBody([
                dbc.Row([
                    dbc.Col([
                        dcc.Loading([
                            dbc.Button(
                                children=[
                                    html.I(className="bi bi-play-fill me-2"),
                                    'Start scanning'
                                ],
                                id='start-scan-button'
                            )
                        ]),
                    ], width=6),
                    dbc.Alert(
                        id='scan-response',
                        children="Run a scan first...",
                        color="secondary",
                        className="mb-0"
                    ),
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
        dbc.Row([
            dbc.Col(configuration_card, md=6),
            dbc.Col(dataset_name_card + [html.Br()] + scan_card, md=6)
        ])
    ], id="scan-page-layout"
)


@callback(Output('scan-cfg-toml', 'value'),
          Input('cfg-upload', 'contents'),
          prevent_initial_call=True)
def update_toml_cfg(contents):
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


def all_valid_characters(dataset_name):
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


def is_valid_dataset_name(dataset_name, existing_datasets):
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
def validate_dataset_name(dataset_name, existing_datasets):
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
    if is_valid_dataset_name(dataset_name, existing_datasets):
        return False, True, dataset_name
    else:
        return True, False, dataset_name


@callback(
    Output('dataset-exists-message', 'style'),
    Input('dataset-input-name', 'value'),
    State('dataset-list', 'data')
)
def check_dataset_name_uniqueness(dataset_name, existing_datasets):
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
    dict
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
    Input('dataset-input-name', 'valid'),
)
def disable_scan_button(valid):
    """Disables the 'Start scanning' button based on dataset validation status.

    This callback function determines whether the 'start-scan-button' element
    should be disabled or enabled based on the validity of input provided
    to the 'dataset-input-name' element. If the input is not valid, the
    'start-scan-button' is disabled.

    Parameters
    ----------
    valid : bool
        Indicates whether the dataset input is valid.
        ``True`` if valid, ``False`` otherwise.

    Returns
    -------
    bool
        Returns ``True`` if the scan button should be disabled, and ``False``
        if it should be enabled.
    """
    return not valid


@callback(
    Output('scan-response', 'children'),
    Output('scan-output', 'children'),
    Input('start-scan-button', 'n_clicks'),
    State('scan-cfg-toml', 'value'),
    State('dataset-input-name', 'value'),
    prevent_initial_call=True
)
def run_scan(_, cfg, dataset_name):
    from plantimager.webui.controller_proxy import RPCController

    try:
        controller = RPCController.instance()
    except RuntimeError as e:
        return f"Error: Raspberry Pi Controller not initialized!", print(e)

    controller.set_config(cfg)
    controller.run_scan()

    return "Scan started.", "Scanning plant in progress..."
