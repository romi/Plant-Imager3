#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Plant Imager Web Interface

A web-based user interface for the Plant Imager system, providing a graphical front-end to interact with the PlantDB REST API for plant imaging, analysis, and dataset management.

Key Features
------------
- Bootstrap-styled Dash web application for plant imaging
- REST API connectivity for data operations
- User authentication and account management
- Dataset acquisition with metadata management

Usage Examples
--------------
# Run the web interface with default REST API settings
$ python app.py

# Connect to a specific REST API server
$ python app.py --host http://example-server --port 5000
"""

import argparse
from threading import Thread

import dash_bootstrap_components as dbc
import zmq
from dash import Dash
from dash import dcc
from dash import html
from werkzeug.middleware.proxy_fix import ProxyFix


from plantimager.webui.config import plantdb_cfg_modal
from plantimager.webui.controller_proxy import RPCController
from plantimager.webui.login import login_modal
from plantimager.webui.nav import navbar_layout
from plantimager.webui.new_user import new_user_modal
from plantimager.webui.scan import scan_layout

REST_API_URL = "127.0.0.1"
REST_API_PORT = 5000


def parsing() -> argparse.ArgumentParser:
    """Create and configure the command-line argument parser for the Plant Imager WebUI.

    Sets up command-line arguments for configuring the connection to the PlantDB REST API,
    including host address and port options.

    Returns
    -------
    argparse.ArgumentParser
        Configured argument parser with application options

    Examples
    --------
    >>> parser = parsing()
    >>> args = parser.parse_args(['--host', '192.168.1.100', '--port', '5001'])
    >>> print(args.host, args.port)
    192.168.1.100 5001
    """
    parser = argparse.ArgumentParser(description="PlantImager WebUI.")

    app_args = parser.add_argument_group("Dash app options")
    app_args.add_argument('--host', type=str, default=REST_API_URL,
                          help="Host address of the PlantDB REST API.")
    app_args.add_argument('--port', type=int, default=REST_API_PORT,
                          help="Port of the PlantDB REST API.")
    app_args.add_argument('--proxy', action='store_true',
                          help="Activate if the server is behind a reverse proxy")
    app_args.add_argument('--url-base-pathname', type=str, default='/webui/',
                          help="Base URL path for the application (should match Nginx location).")
    return parser


def setup_web_app(url: str, port: int, proxy=False, url_base_pathname: str = '/webui/') -> Dash:
    """Initialize and configure the Plant Imager Dash web application.

    Creates a Dash application instance with Bootstrap styling and sets up the main
    layout including navigation bar, modals, and content areas. The application
    is configured with global state storage for REST API connection details,
    user authentication, and dataset management.

    Parameters
    ----------
    url : str
        The base URL for the REST API server (e.g., 'http://localhost')
    port : int
        The port number for the REST API server connection
    proxy : bool, optional
        Boolean flag indicating whether the application is behind a reverse proxy, by default ``False``.
    url_base_pathname : str
        The base URL path where the application is served (should match Nginx location)

    Returns
    -------
    dash.Dash
        Configured Dash application instance with complete layout and callbacks

    Notes
    -----
    The application layout includes several components:
    - Global state management using dcc.Store components
    - Navigation bar with ROMI branding
    - Configuration and authentication modals
    - Main content area for scan management
    """

    app = Dash(
        name="PlantImager_WebUI",
        title="Plant Imager",
        external_stylesheets=[dbc.themes.BOOTSTRAP, dbc.icons.BOOTSTRAP],
        url_base_pathname=url_base_pathname,
    )

    if proxy:
        # App is behind one proxy that sets the -For and -Host headers.
        app.server.wsgi_app = ProxyFix(app.server.wsgi_app, x_for=1, x_host=1, x_proto=1)

    # Main application layout definition
    app.layout = html.Div([
        # Global state storage
        dcc.Store(id='rest-api-host', data=url),
        dcc.Store(id='rest-api-port', data=port),
        dcc.Store(id='connected', data=None),
        dcc.Store(id='logged-username', data=None),
        dcc.Store(id='logged-fullname', data=None),
        dcc.Store(id='dataset-list', data=[]),
        dcc.Store(id='dataset-id', data=None),
        # Navigation and modal components
        html.Div(children=[
            navbar_layout,
            plantdb_cfg_modal,
            login_modal,
            new_user_modal,
        ]),
        # Main content container
        html.Div(children=[scan_layout], style={"margin": 20}),
    ])

    return app


def main() -> None:
    """Run the Plant Imager Web Interface application.

    This function serves as the entry point for the Plant Imager Web UI. It:
    1. Parses command-line arguments for REST API connection settings
    2. Establishes a ZeroMQ connection to the controller service
    3. Initializes and runs the Dash web application

    Notes
    -----
    - The controller connection runs in a separate daemon thread
    - The Dash application runs in debug mode on port 8000
    """
    # - Parse the input arguments to variables:
    parser = parsing()
    args = parser.parse_args()

    # - Create connexion with controller
    context = zmq.Context()
    controller_thread = Thread(target=lambda ctx: RPCController(ctx, "tcp://localhost:14567"), args=(context,))
    controller_thread.daemon = True
    controller_thread.start()

    # - Start the Dash app:
    app = setup_web_app(args.host, args.port, args.proxy)
    app.run(host="0.0.0.0", debug=True, port=8080)


if __name__ == "__main__":
    main()
