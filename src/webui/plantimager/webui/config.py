#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""PlantDB Configuration Interface for Plant Imager Web UI.

This module provides components and callbacks for configuring the connection to the PlantDB API
and managing datasets within the Plant Imager web interface.

Key Features
------------
- PlantDB API connection configuration and testing
- Dataset listing and management
- Dynamic UI components for database status visualization
- Bootstrap-styled modals and alerts for user interaction

Environment variables
---------------------
- ALLOW_PRIVATE_IP: if `True`, allow the use of private IPs for PlantDB REST API URL
- CERT_PATH: specify the path to the self-signed certificates used by the PlantDB server.
- VALIDATE_HOST: if `True`, check the PlantDB REST API URL against a blacklist
"""
import os

import dash_bootstrap_components as dbc
from dash import Input
from dash import Output
from dash import State
from dash import callback
from dash import ctx
from dash import dcc
from dash import html
from dash import no_update
from dash_bootstrap_components import NavLink
from plantdb.client.rest_api import PLANTDB_HOST
from plantdb.client.rest_api import PLANTDB_PORT
from plantdb.client.rest_api import plantdb_url
from plantdb.client.rest_api import request_scan_names_list
from plantdb.client.url import is_server_available
from requests import RequestException


def server_available(host, port, prefix, ssl):
    """Checks the availability of a server.

    Parameters
    ----------
    host : str
        The IP address or hostname of the server to test.
    port : int
        The port number of the server to test.
    prefix : str
        The URL prefix of the server to test.
    ssl : bool
        Flag indicating whether SSL (HTTPS) is enabled.

    Returns
    -------
    bool
        A flag indicating whether the server is available.
    """
    allow_private_ip = os.getenv('ALLOW_PRIVATE_IP', 'false').lower() == 'true'
    cert_path = os.getenv('CERT_PATH', None)
    validate_host = os.getenv('VALIDATE_HOST', 'true').lower() == 'true'
    try:
        url = plantdb_url(host, port=port, prefix=prefix, ssl=ssl)
        availability = is_server_available(url, allow_private_ip=allow_private_ip,
                                           cert_path=cert_path, validate_host=validate_host)
    except:
        is_available = False
    else:
        is_available = availability.ok
    return is_available


def _connected_status(dataset_list):
    status = dbc.Alert(children=[
        html.I(className="bi bi-check-circle-fill me-2"),
        f"Loaded {len(dataset_list)} dataset.",
    ], color="success")
    return status


def _unconnected_status(error):
    status = dbc.Alert([
        html.I(className="bi bi-x-octagon-fill me-2"),
        f"Could not load any dataset!\n{error}",
    ], color="danger")
    return status


def dataset_cfg_status(is_connected: bool) -> html.I:
    """Generate a database status icon based on the connection state.

    Creates a Bootstrap icon element representing the database connection status.
    Returns a check icon when connected and a gear icon when disconnected.

    Parameters
    ----------
    is_connected : bool
        Flag indicating whether the database connection is established.

    Returns
    -------
    dash.html.I
        A Bootstrap icon component with the appropriate class based on connection status.
    """
    if is_connected:
        return html.I(className="bi bi-database-check fs-3")
    else:
        return html.I(className="bi bi-database-gear fs-3")


def create_dataset_cfg_icon(is_connected: bool = False, dataset_list: list | None = None) -> dbc.NavLink:
    """Create a navigation link with the database status icon and dataset counter badge.

    Creates a Bootstrap NavLink component that displays a database status icon and
    a badge showing the number of datasets. The icon changes appearance based on
    connection status.

    Parameters
    ----------
    is_connected : bool, optional
        Flag indicating whether the database connection is established,
        by default False
    dataset_list : list, optional
        List of datasets to count, by default empty list

    Returns
    -------
    dash.bootstrap_components.NavLink
        A navigation link component containing:
        - Database status icon
        - Badge showing dataset count
        The NavLink is styled and positioned according to the application's design.
    """
    if dataset_list is None:
        dataset_list = []
    return dbc.NavLink(
        children=[
            dataset_cfg_status(is_connected),
            dbc.Badge(
                children=f"{len(dataset_list)}",
                id="dataset-count-badge",
                color="primary",
                className="position-absolute top-45 start-100 translate-middle",
                pill=True
            )
        ],
        id='plantdb-cfg-button',
        n_clicks=0,
        className="position-relative align-left",
        style={'color': "#f3f3f3"},
    )


# Create PlantDB API configuration button component for the navigation bar
cfg_button = create_dataset_cfg_icon()
cfg_tooltip = dbc.Tooltip(
    children="Configure the PlantDB API",
    target="plantdb-cfg-button",
    placement="bottom",
)

# Card component for PlantDB API configuration
plantdb_cfg_modal = html.Div(children=[
    dbc.Modal(id="plantdb-cfg-modal", is_open=False, children=[
        dbc.ModalHeader(
            dbc.ModalTitle(
                children=[
                    html.I(className="bi bi-database-gear-fill me-2"),
                    "PlantDB API configuration"
                ]
            )
        ),
        dbc.ModalBody(children=[
            # URL input field for PlantDB API endpoint
            html.Div(children=[
                dbc.Label([html.I(className="bi bi-link-45deg me-2"), "PlantDB API hostname:"]),
                dbc.Input(id="api-address", type="url"),
                dbc.FormText(f"Use '{PLANTDB_HOST}' for a local database.", color="secondary"),
            ]),
            # Port number input for PlantDB API
            html.Div(children=[
                dbc.Label([html.I(className="bi bi-hdd-network me-2"), "PlantDB API port:"]),
                dbc.Input(id="api-port", type="text"),
                dbc.FormText(f"Should be '{PLANTDB_PORT}' by default.", color="secondary"),
            ]),
            # URL prefix for PlantDB API
            html.Div(children=[
                dbc.Label([html.I(className="bi bi-hdd-network me-2"), "PlantDB API prefix:"]),
                dbc.Input(id="api-prefix", type="text"),
                dbc.FormText(f"Should be empty by default. Use it if the PlantDB server is behind a proxy.",
                             color="secondary"),
            ]),
            # SSL checkbox
            html.Div(children=[
                dbc.Checkbox(
                    id="api-ssl",
                    label="Use SSL (HTTPS)",
                    value=False,
                ),
                dbc.FormText("Enable if the PlantDB server uses HTTPS instead of HTTP.", color="secondary"),
            ]),
            html.Br(),
            dbc.Row(children=[
                # Connection test button
                dbc.Col([
                    dbc.Button(
                        children=[
                            html.I(className="bi bi-plug-fill me-2"),
                            "Test connexion"
                        ],
                        id="connect-plantdb-button",
                        color="primary",
                        class_name="w-100",
                    ),
                ], width=6),
                # Dataset loading button
                dbc.Col([
                    dbc.Button(
                        children=[
                            html.I(className="bi bi-cloud-download me-2"),
                            "Load datasets"
                        ],
                        id="load-plantdb-button",
                        color="primary",
                        class_name="w-100",
                        disabled=True,
                    )
                ], width=6),
            ]),
        ]),
        dbc.ModalFooter(children=[
            # PlantDB status display
            html.Div(id="plantdb-status-form", className="w-100"),
            html.Div(id="load-status-form", className="w-100"),
        ])
    ]),
    # Interval component for auto-closing modal after successful connection
    dcc.Interval(
        id='modal-close-interval',
        interval=2000,  # 2 seconds
        n_intervals=0,
        max_intervals=1,
        disabled=True
    )
])


@callback(Output("plantdb-cfg-modal", "is_open"),
          Input('plantdb-cfg-button', 'n_clicks'),
          Input('modal-close-interval', 'n_intervals'),
          State('plantdb-cfg-modal', 'is_open'),
          prevent_initial_call=True)
def toggle_plantdb_cfg_modal(
        cfg_clicks: int,
        n_intervals: int,
        is_open: bool
) -> bool:
    """Toggle the visibility state of the PlantDB configuration modal.

    This callback function controls the opening and closing of the PlantDB configuration
    modal dialog. It is triggered by:
    1. clicking the configuration button (opens modal)
    2. the interval timer (closes modal after successful connection)

    Parameters
    ----------
    cfg_clicks : int
        Number of times the plantdb-cfg-button has been clicked.
    n_intervals : int
        Number of intervals elapsed (for auto-close after successful connection).
    is_open : bool
        Current visibility state of the modal.

    Returns
    -------
    bool
        The new visibility state of the modal.
    """
    triggered_id = ctx.triggered_id

    # The configuration button was clicked - toggle modal
    if triggered_id == 'plantdb-cfg-button':
        return not is_open

    # The interval timer fired - close the modal (only fires after successful connection)
    elif triggered_id == 'modal-close-interval':
        return False

    return no_update


@callback(
    Output("api-address", "value"),
    Input("plantdb-cfg-modal", "is_open"),
    State("plantdb-host", "data")
)
def show_api_address(modal_is_open: bool, stored_host: str | None) -> str:
    """Callback updating the value of the 'api-address' field with stored data when opening the PlantDB configuration modal.

    Parameters
    ----------
    modal_is_open : bool
        Indicates whether the configuration modal is currently open.
    stored_host : str or None
        The stored value of the PlantDB API host. Can be ``None`` if not previously set.

    Returns
    -------
    str
        The IP address to be used, either the stored host value or the ``PLANTDB_HOST`` constant.
    """
    if modal_is_open:
        return stored_host if stored_host is not None else PLANTDB_HOST
    else:
        return stored_host


# Callback to update IP port from a stored value
@callback(
    Output("api-port", "value"),
    Input("plantdb-cfg-modal", "is_open"),
    State("plantdb-port", "data")
)
def show_api_port(modal_is_open: bool, stored_port: int | None) -> int | str:
    """Callback updating the value of the 'api-port' field with stored data when opening the PlantDB configuration modal.

    Parameters
    ----------
    modal_is_open : bool
        Boolean indicating whether the configuration modal is open or closed.
    stored_port : str or None
        Stored port value retrieved from the state. Can be ``None`` if not specified.

    Returns
    -------
    str
        Value to be set for the "api-port" input field, either the stored port value or the ``PLANTDB_PORT`` constant.
    """
    if modal_is_open:
        return stored_port if stored_port is not None else PLANTDB_PORT
    else:
        return stored_port


# Callback to update IP port from a stored value
@callback(
    Output("api-prefix", "value"),
    Input("plantdb-cfg-modal", "is_open"),
    State("plantdb-prefix", "data")
)
def show_api_prefix(modal_is_open: bool, stored_prefix: str | None) -> int | str:
    """Callback updating the value of the 'api-prefix' field with stored data when opening the PlantDB configuration modal.

    Parameters
    ----------
    modal_is_open : bool
        Boolean indicating whether the configuration modal is open or closed.
    stored_prefix : str or None
        Stored prefix value retrieved from the state. Can be ``None`` if not specified.

    Returns
    -------
    str
        Value to be set for the "api-prefix" input field.
    """
    if modal_is_open:
        return stored_prefix if stored_prefix is not None else ""
    else:
        return stored_prefix


# Callback to show SSL status from stored data
@callback(
    Output("api-ssl", "value"),
    Input("plantdb-cfg-modal", "is_open"),
    State("plantdb-ssl", "data")
)
def show_api_ssl(modal_is_open: bool, stored_ssl: bool | None) -> bool:
    """Callback updating the value of the 'api-ssl' checkbox with stored data when opening the PlantDB configuration modal.

    Parameters
    ----------
    modal_is_open : bool
        Boolean indicating whether the configuration modal is open or closed.
    stored_ssl : bool or None
        Stored SSL flag retrieved from the state. Can be ``None`` if not specified.

    Returns
    -------
    bool
        Value to be set for the "api-ssl" checkbox.
    """
    if modal_is_open:
        return stored_ssl if stored_ssl is not None else False
    else:
        return stored_ssl


@callback(
    Output("plantdb-status-form", "children"),
    Input("connected", "data"),
    State("plantdb-host", "data"),
    State("plantdb-port", "data"),
    State("plantdb-prefix", "data"),
    State("plantdb-ssl", "data"),
)
def show_plantdb_status(status: bool | None, host: str, port: int, prefix: str, ssl: bool) -> dbc.Alert:
    """Display the connection status of the PlantDB server in a Bootstrap alert component.

    This callback function generates a styled alert component that shows whether the
    PlantDB server is available or not. The alert includes an icon and descriptive text
    with the server's host and port information when applicable.

    Parameters
    ----------
    status : bool or None
        Connection status of the PlantDB server:
        - ``None``: status unknown
        - ``True``: server is available
        - ``False``: server is unavailable
    host : str
        Hostname or IP address of the PlantDB server
    port : int
        Port number of the PlantDB server
    prefix : str
        URL prefix of the PlantDB server
    ssl : bool
        Flag indicating whether SSL (HTTPS) is enabled

    Returns
    -------
    dash_bootstrap_components.Alert
        A Bootstrap alert component with the appropriate styling and message based on
        the connection status:
        - Info (blue): when status is unknown
        - Success (green): when server is available
        - Danger (red): when server is unavailable
    """
    if status is None:
        status_form = dbc.Alert(children=[
            html.I(className="bi bi-info-circle-fill me-2"),
            "Unknown server availability."
        ], color="info")
    elif status:
        status_form = dbc.Alert(children=[
            html.I(className="bi bi-check-circle-fill me-2"),
            f"Server {plantdb_url(host, port=port, prefix=prefix, ssl=ssl)} available.",
        ], color="success")
    else:
        status_form = dbc.Alert(children=[
            html.I(className="bi bi-x-octagon-fill me-2"),
            f"Server {plantdb_url(host, port=port, prefix=prefix, ssl=ssl)} unavailable!",
        ], color="danger")
    return status_form


# Callback to test PlantDB API connection and update UI accordingly
@callback(
    Output('connected', 'data'),
    Output('load-plantdb-button', 'disabled'),
    Output('plantdb-host', 'data'),
    Output('plantdb-port', 'data'),
    Output('plantdb-prefix', 'data'),
    Output('plantdb-ssl', 'data'),
    Output('modal-close-interval', 'disabled'),
    Output('modal-close-interval', 'n_intervals'),
    Input('connect-plantdb-button', 'n_clicks'),
    State('api-address', 'value'),
    State('api-port', 'value'),
    State('api-prefix', 'value'),
    State('api-ssl', 'value'),
    State('plantdb-host', 'data'),
    State('plantdb-port', 'data'),
    State('plantdb-prefix', 'data'),
    State('plantdb-ssl', 'data'),
)
def check_server_availability(
        _: int,
        host: str | None,
        port: int | str | None,
        prefix: str | None,
        ssl: bool | None,
        stored_host: str,
        stored_port: int,
        stored_prefix: str,
        stored_ssl: bool,
) -> tuple[bool, bool, str, int, str, bool, bool, int]:
    """Checks the availability of a server based on the provided host and port and updates the UI accordingly.

    Parameters
    ----------
    _ : int
        The n_clicks property of the load-plantdb-button element, which triggers the callback (not used).
    host : str
        The IP address or hostname of the server to test.
    port : int
        The port number of the server to test.
    prefix : str
        The URL prefix of the server to test.
    ssl : bool
        Flag indicating whether SSL (HTTPS) is enabled.
    stored_host : str
        The previously stored server host value, used if the connection test fails.
    stored_port : int
        The previously stored server port value, used if the connection test fails.
    stored_prefix : str
        The previously stored server prefix value, used if the connection test fails.
    stored_ssl : bool
        The previously stored server SSL flag, used if the connection test fails.

    Returns
    -------
    bool
        A flag indicating whether the server is available.
    bool
        A boolean indicating whether the load button should be disabled.
    str
        The updated server host value to store.
    int
        The updated server port value to store.
    str
        The updated server prefix value to store.
    bool
        The updated server SSL flag value to store.
    bool
        Whether the modal-close-interval should be disabled.
    int
        Reset n_intervals to 0 to restart the timer.
    """
    if host is None:
        host = stored_host
    if port is None:
        port = stored_port
    if prefix is None:
        prefix = stored_prefix
    if ssl is None:
        ssl = stored_ssl

    # Handle URLs that include a protocol prefix
    if host and isinstance(host, str):
        if host.startswith("http://"):
            host = host[7:]
            ssl = False
        elif host.startswith("https://"):
            host = host[8:]
            ssl = True

    if server_available(host, port, prefix, ssl):
        # Server is available: enable load button, enable interval timer
        return True, False, host, port, prefix, ssl, False, 0
    else:
        # Server is not available: disable load button, disable interval timer
        return False, True, host, port, prefix, ssl, True, 0


@callback(
    Output("plantdb-cfg-button", "children"),
    Input("connected", "data"),
    State("dataset-list", "data"),
)
def update_plantdb_cfg_button(status: bool | None, dataset_list: list | None) -> NavLink:
    """Update the PlantDB configuration button's appearance based on connection status.

    This callback function updates the visual representation of the PlantDB configuration
    button in the navigation bar depending on the connection status and dataset list state.
    It uses the create_dataset_cfg_icon function to generate the appropriate icon.

    Parameters
    ----------
    status : bool or None
        The connection status to the PlantDB API.
        ``None`` indicates no connection attempt has been made.
        ``True`` indicates a successful connection.
        ``False`` indicates a failed connection.
    dataset_list : list or None
        List of available datasets from the PlantDB.
        ``None`` if no datasets are loaded or connection is not established.

    Returns
    -------
    dash_bootstrap_components.NavLink
        A Dash HTML component representing the configuration button icon
        with the appropriate styling based on the connection status.
    """
    return create_dataset_cfg_icon(status, dataset_list)


# Callback to load a dataset list from PlantDB API
@callback(
    Output('load-status-form', 'children'),
    Output('dataset-list', 'data'),
    Input('load-plantdb-button', 'n_clicks'),
    Input('connected', 'data'),
    State('plantdb-host', 'data'),
    State('plantdb-port', 'data'),
    State('plantdb-prefix', 'data'),
    State('plantdb-ssl', 'data'),
    State('session-token', 'data'),
    prevent_initial_call=True,
)
def update_dataset_list(
        n_clicks: int,
        connected: bool | None,
        host: str,
        port: int | str,
        prefix: str,
        ssl: bool,
        session_token: str,
) -> tuple[dbc.Alert, list[str]]:
    """Callback updating the dataset list and displaying the load status when a user clicks the load button.

    Parameters
    ----------
    n_clicks : int
        The n_clicks property of the load-plantdb-button element, which triggers the callback (not used).
    connected : bool
        The connection status of the PlantDB API server.
    host : str
       The hostname or IP address of the PlantDB API server.
    port : int
        The port number of the PlantDB API server.
    prefix : str
        The prefix of the PlantDB API server.
    ssl : bool
        Flag indicating whether SSL (HTTPS) is enabled.

    Returns
    -------
    dash_bootstrap_components.Alert
        An alert component indicating success or failure of dataset retrieval.
    list of str
        A list of dataset names retrieved from the server.
    """
    error = ""
    if not connected:
        error = "PlantDB API server not connected."
        return _unconnected_status(error=error), []

    try:
        dataset_list = sorted(request_scan_names_list(host, port=port, prefix=prefix, ssl=ssl,
                                                      session_token=session_token).json())
    except RequestException as e:
        dataset_list = []
        error = e

    if dataset_list:
        status = _connected_status(dataset_list)
    else:
        status = _unconnected_status(error=error)

    return status, dataset_list


@callback(
    Output("dataset-count-badge", "children"),
    Input("dataset-list", "data")  # Assuming you have a dataset list stored in dcc.Store
)
def update_dataset_badge(dataset_list: list) -> str:
    """Update the dataset count badge with the current number of datasets.

    This callback function updates a badge element in the UI to display the total
    number of datasets currently available in the system. It converts the length
    of the dataset list to a string for display.

    Parameters
    ----------
    dataset_list : list
        A list containing the dataset names stored in the dcc.Store component.

    Returns
    -------
    str
        String representation of the number of datasets in the list.
    """
    return str(len(dataset_list))
