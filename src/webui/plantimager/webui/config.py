#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""PlantDB Configuration Interface for Plant Imager Web UI.

This module provides components and callbacks for configuring the connection to the PlantDB REST API
and managing datasets within the Plant Imager web interface.

Key Features
------------
- REST API connection configuration and testing
- Dataset listing and management
- Dynamic UI components for database status visualization
- Bootstrap-styled modals and alerts for user interaction
"""

import dash_bootstrap_components as dbc
from dash import Input
from dash import Output
from dash import State
from dash import callback
from dash import ctx
from dash import html
from dash import no_update
from plantdb.client.plantdb_client import PlantDBClient
from plantdb.client.rest_api import REST_API_PORT
from plantdb.client.rest_api import REST_API_URL
from plantdb.client.rest_api import base_url
from plantdb.client.rest_api import list_scan_names
from plantdb.client.url import is_server_available
from requests import RequestException


def _connected_status(dataset_list):
    status = dbc.Alert(children=[
        html.I(className="bi bi-check-circle-fill me-2"),
        f"Loaded {len(dataset_list)} dataset.",
    ], color="success")
    return status


def _unconnected_status():
    status = dbc.Alert([
        html.I(className="bi bi-x-octagon-fill me-2"),
        f"Could not load any dataset!",
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


# Create PlantDB REST API configuration button component for the navigation bar
cfg_button = create_dataset_cfg_icon()
cfg_tooltip = dbc.Tooltip(
    children="Configure PlantDB REST API connection and load dataset list.",
    target="plantdb-cfg-button",
    placement="bottom",
)

# Card component for PlantDB REST API configuration
plantdb_cfg_modal = html.Div(children=[
    dbc.Modal(id="plantdb-cfg-modal", children=[
        dbc.ModalHeader(
            dbc.ModalTitle(
                children=[
                    html.I(className="bi bi-database-gear-fill me-2"),
                    "PlantDB REST API configuration"
                ]
            )
        ),
        dbc.ModalBody(children=[
            # URL input field for REST API endpoint
            html.Div(children=[
                dbc.Label([html.I(className="bi bi-link-45deg me-2"), "REST API URL:"]),
                dbc.Input(id="api-address", type="url"),
                dbc.FormText(f"Use '{REST_API_URL}' for a local database.", color="secondary"),
            ]),
            # Port number input for REST API
            html.Div(children=[
                dbc.Label([html.I(className="bi bi-hdd-network me-2"), "REST API port:"]),
                dbc.Input(id="api-port", type="text"),
                dbc.FormText(f"Should be '{REST_API_PORT}' by default.", color="secondary"),
            ]),
            # URL prefix for REST API
            html.Div(children=[
                dbc.Label([html.I(className="bi bi-hdd-network me-2"), "REST API prefix:"]),
                dbc.Input(id="api-prefix", type="text"),
                dbc.FormText(f"Should be '' by default. Use if behind a proxy.", color="secondary"),
            ]),
            # SSL checkbox
            html.Div(children=[
                dbc.Checkbox(
                    id="api-ssl",
                    label="Use SSL (HTTPS)",
                    value=False,
                ),
                dbc.FormText("Enable if the server uses HTTPS instead of HTTP.", color="secondary"),
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
    ])
])


@callback(Output("plantdb-cfg-modal", "is_open"),
          Input('plantdb-cfg-button', 'n_clicks'),
          Input('connect-plantdb-button', 'n_clicks'),
          State('api-address', 'value'),
          State('api-port', 'value'),
          State('api-prefix', 'value'),
          State('api-ssl', 'value'),
          State('plantdb-cfg-modal', 'is_open'),
          prevent_initial_call=True)
def toggle_plantdb_cfg_modal(
        cfg_clicks: int,
        connect_clicks: int,
        host: str | None,
        port: int | str | None,
        prefix: str | None,
        ssl: bool | None,
        is_open: bool
) -> bool | None:
    """Toggle the visibility state of the PlantDB configuration modal.

    This callback function controls the opening and closing of the PlantDB configuration
    modal dialog. It is triggered by clicking on either:
    1. The configuration button (opens modal)
    2. The connect button (closes modal only if connection successful)

    Parameters
    ----------
    cfg_clicks : int
        Number of times the plantdb-cfg-button has been clicked.
    connect_clicks : int
        Number of times the connect-plantdb-button has been clicked.
    host : str or None
        The host value from the form.
    port : int or str or None
        The port value from the form.
    prefix : str or None
        The prefix value from the form.
    ssl : bool or None
        The SSL flag from the form.
    is_open : bool
        Current visibility state of the modal.

    Returns
    -------
    bool or None
        The new visibility state of the modal.
    """
    # Identify which button was clicked using context
    triggered_id = ctx.triggered_id

    # The configuration button was clicked - toggle modal
    if triggered_id == 'plantdb-cfg-button':
        return not is_open

    # The connect button was clicked - check the connection before closing
    elif triggered_id == 'connect-plantdb-button':
        # Only attempt to close if the modal is open
        if is_open:
            try:
                is_available = is_server_available(base_url(host, port, prefix, ssl=ssl))
            except:
                # Keep modal open if connection fails
                return True
            else:
                # Close the modal only if the connection is successful
                return not is_available

    # Return no_update if no relevant button was clicked
    return no_update


@callback(
    Output("api-address", "value"),
    Input("plantdb-cfg-modal", "is_open"),
    State("rest-api-host", "data")
)
def show_api_address(modal_is_open: bool, stored_host: str | None) -> str:
    """Callback updating the value of the 'api-address' field with stored data when opening the PlantDB configuration modal.

    Parameters
    ----------
    modal_is_open : bool
        Indicates whether the configuration modal is currently open.
    stored_host : str or None
        The stored value of the REST API host. Can be ``None`` if not previously set.

    Returns
    -------
    str
        The IP address to be used, either the stored host value or the ``REST_API_URL`` constant.
    """
    if modal_is_open:
        return stored_host if stored_host is not None else REST_API_URL
    else:
        return stored_host


# Callback to update IP port from a stored value
@callback(
    Output("api-port", "value"),
    Input("plantdb-cfg-modal", "is_open"),
    State("rest-api-port", "data")
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
        Value to be set for the "api-port" input field, either the stored port value or the ``REST_API_PORT`` constant.
    """
    if modal_is_open:
        return stored_port if stored_port is not None else REST_API_PORT
    else:
        return stored_port


# Callback to update IP port from a stored value
@callback(
    Output("api-prefix", "value"),
    Input("plantdb-cfg-modal", "is_open"),
    State("rest-api-prefix", "data")
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
    State("rest-api-ssl", "data")
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
    State("rest-api-host", "data"),
    State("rest-api-port", "data"),
    State("rest-api-prefix", "data"),
    State("rest-api-ssl", "data"),
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
            f"Server {base_url(host, port, prefix, ssl=ssl)} available.",
        ], color="success")
    else:
        status_form = dbc.Alert(children=[
            html.I(className="bi bi-x-octagon-fill me-2"),
            f"Server {base_url(host, port, prefix, ssl=ssl)} unavailable!",
        ], color="danger")
    return status_form


# Callback to test REST API connection and update UI accordingly
@callback(
    Output('connected', 'data'),
    Output('load-plantdb-button', 'disabled'),
    Output('rest-api-host', 'data'),
    Output('rest-api-port', 'data'),
    Output('rest-api-prefix', 'data'),
    Output('rest-api-ssl', 'data'),
    Input('connect-plantdb-button', 'n_clicks'),
    State('api-address', 'value'),
    State('api-port', 'value'),
    State('api-prefix', 'value'),
    State('api-ssl', 'value'),
    State('rest-api-host', 'data'),
    State('rest-api-port', 'data'),
    State('rest-api-prefix', 'data'),
    State('rest-api-ssl', 'data'),
)
def check_server_availability(
        _: int,
        host: str | None,
        port: int | str | None,
        prefix: str | None,
        ssl: bool | None,
        stored_host: str | None,
        stored_port: int | str | None,
        stored_prefix: str | None,
        stored_ssl: bool | None,
) -> tuple[bool, bool, str, int | str, str, bool]:
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
        A storer flag indicating whether the connection test was successful.
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

    try:
        is_server_available(base_url(host, port, prefix, ssl=ssl))
    except:
        is_available = False
    else:
        is_available = True

    if is_available:
        return True, False, host, port, prefix, ssl
    else:
        return False, True, host, port, prefix, ssl


@callback(
    Output("plantdb-cfg-button", "children"),
    Input("connected", "data"),
    State("dataset-list", "data"),
)
def update_plantdb_cfg_button(status: bool | None, dataset_list: list | None) -> list:
    """Update the PlantDB configuration button's appearance based on connection status.

    This callback function updates the visual representation of the PlantDB configuration
    button in the navigation bar depending on the connection status and dataset list state.
    It uses the create_dataset_cfg_icon function to generate the appropriate icon.

    Parameters
    ----------
    status : bool or None
        The connection status to the PlantDB REST API.
        ``None`` indicates no connection attempt has been made.
        ``True`` indicates a successful connection.
        ``False`` indicates a failed connection.
    dataset_list : list or None
        List of available datasets from the PlantDB.
        ``None`` if no datasets are loaded or connection is not established.

    Returns
    -------
    dash.html.Component
        A Dash HTML component representing the configuration button icon
        with the appropriate styling based on the connection status.
    """
    return create_dataset_cfg_icon(status, dataset_list)


# Callback to load a dataset list from PlantDB REST API
@callback(
    Output('load-status-form', 'children'),
    Output('dataset-list', 'data'),
    Input('load-plantdb-button', 'n_clicks'),
    Input('connected', 'data'),
    State('rest-api-host', 'data'),
    State('rest-api-port', 'data'),
    State('rest-api-prefix', 'data'),
    State('rest-api-ssl', 'data'),
    prevent_initial_call=True,
)
def update_dataset_list(
        n_clicks: int,
        connected: bool | None,
        host: str,
        port: int | str,
        prefix: str,
        ssl: bool,
) -> tuple[dbc.Alert, list[str]]:
    """Callback updating the dataset list and displaying the load status when a user clicks the load button.

    Parameters
    ----------
    n_clicks : int
        The n_clicks property of the load-plantdb-button element, which triggers the callback (not used).
    connected : bool
        The connection status of the PlantDB REST API server.
    host : str
       The hostname or IP address of the PlantDB REST API server.
    port : int
        The port number of the PlantDB REST API server.
    prefix : str
        The prefix of the PlantDB REST API server.
    ssl : bool
        Flag indicating whether SSL (HTTPS) is enabled.

    Returns
    -------
    dash_bootstrap_components.Alert
        An alert component indicating success or failure of dataset retrieval.
    list of str
        A list of dataset names retrieved from the server.
    """
    if not connected:
        return _unconnected_status(), []

    try:
        dataset_list = list_scan_names(host=host, port=port, prefix=prefix, ssl=ssl)
    except RequestException:
        dataset_list = []

    if dataset_list:
        status = _connected_status(dataset_list)
    else:
        status = _unconnected_status()

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
