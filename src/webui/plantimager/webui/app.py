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
$ python app.py --api_host http://example-server --api_port 5000
"""

import argparse
from threading import Thread

import dash
import dash_bootstrap_components as dbc
import zmq
from dash import Dash
from dash import dcc
from dash import html
from plantdb.client.plantdb_client import PlantDBClient
from plantdb.client.rest_api import base_url
from plantdb.client.rest_api import configure_requests_with_certificate
from plantdb.client.plantdb_client import api_prefix
from werkzeug.middleware.proxy_fix import ProxyFix

from plantimager.webui.carousel import caroussel_modal
from plantimager.webui.config import plantdb_cfg_modal
from plantimager.webui.controller_proxy import RPCController
from plantimager.webui.login import login_modal
from plantimager.webui.nav import navbar_layout
from plantimager.webui.new_user import new_user_modal

REST_API_URL = "127.0.0.1"
REST_API_PORT = 5000
REST_API_PREFIX = ""


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
    >>> from plantimager.webui.app import parsing
    >>> parser = parsing()
    >>> args = parser.parse_args(['--api_host', '192.168.1.100', '--api_port', '5001', '--api_prefix', '/plantdb'])
    >>> print(f"https://{args.api_host}:{args.api_port}{args.api_prefix}")
    https://192.168.1.100:5001/plantdb
    """
    parser = argparse.ArgumentParser(description="PlantImager WebUI.")

    app_args = parser.add_argument_group("Dash app options")
    app_args.add_argument('--proxy', action='store_true',
                          help="Activate if the server is behind a reverse proxy")
    app_args.add_argument('--url-base-pathname', type=str, default='/webui/',
                          help="Base URL path for the application (should match Nginx location).")

    api_args = parser.add_argument_group("PlantDB REST API options")
    api_args.add_argument('--api_host', type=str, default=REST_API_URL,
                          help="Host address of the PlantDB REST API.")
    api_args.add_argument('--api_port', type=int, default=REST_API_PORT,
                          help="Port of the PlantDB REST API.")
    api_args.add_argument('--api_prefix', type=str, default=REST_API_PREFIX,
                          help="Prefix of the PlantDB REST API.")
    api_args.add_argument('--api_cert', type=str, default=None,
                          help="Path to the certificate file for the PlantDB REST API.")

    misc_args = parser.add_argument_group("Miscellaneous options")
    misc_args.add_argument('--debug', action='store_true',
                          help="Enable/disable all the dev tools.")
    return parser


def setup_web_app(api_url: str, api_port: int, api_prefix: str, proxy=False, url_base_pathname: str = '/webui/') -> Dash:
    """Initialize and configure the Plant Imager Dash web application.

    Creates a Dash application instance with Bootstrap styling and sets up the main
    layout including navigation bar, modals, and content areas. The application
    is configured with global state storage for REST API connection details,
    user authentication, and dataset management.

    Parameters
    ----------
    api_url : str
        The base URL for the PlantDB REST API server (e.g., 'http://localhost')
    api_port : int
        The port number for the PlantDB REST API server connection
    api_prefix : str, optional
        URL prefix of the PlantDB REST API server.
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

    - Global state management using `dcc.Store` components
    - Navigation bar with ROMI branding
    - Configuration and authentication modals
    - Main content area for scan management
    """

    app = Dash(
        name="plantimager.webui",
        title="Plant Imager",
        external_stylesheets=[dbc.themes.BOOTSTRAP, dbc.icons.BOOTSTRAP],
        url_base_pathname=url_base_pathname,
        use_pages=True,
        pages_folder="pages",
        assets_folder="assets",
    )

    if proxy:
        # App is behind one proxy that sets the -For and -Host headers.
        app.server.wsgi_app = ProxyFix(app.server.wsgi_app, x_for=1, x_host=1, x_proto=1)
        # Set secure cookies
        app.server.config.update(
            SESSION_COOKIE_SECURE=True,
            SESSION_COOKIE_SAMESITE='Lax'
        )

    # Main application layout definition
    app.layout = html.Div([
        # Global state storage
        dcc.Store(id='rest-api-host', data=api_url, storage_type='session'),  # PlantDB REST API URL
        dcc.Store(id='rest-api-port', data=api_port, storage_type='session'),  # PlantDB REST API port
        dcc.Store(id='rest-api-prefix', data=api_prefix, storage_type='session'),  # PlantDB REST API prefix
        dcc.Store(id='rest-api-ssl', data=False, storage_type='session'),  # PlantDB REST API prefix
        dcc.Store(id='connected', data=None),  # boolean flag indicating if connected to the database or not
        dcc.Store(id='logged-username', data=None, storage_type='session'),  # id of the logger user
        dcc.Store(id='logged-fullname', data=None, storage_type='session'),  # real name of the logged user
        dcc.Store(id='dataset-list', data=[]),  # list of datasets known to the database
        dcc.Store(id='dataset-id', data=None),  # name of the dataset to create (scan operation)
        dcc.Store(id='dataset-dict', data={}, storage_type='session'),  # dictionary of dataset information, used for AG grid table
        dcc.Store(id='view-dataset', data=None),  # name of the dataset to visualize (plotly carousel)
        # Navigation and modal components
        html.Div(children=[
            navbar_layout,
            plantdb_cfg_modal,
            login_modal,
            new_user_modal,
            caroussel_modal,
        ]),
        # Main content container
        # html.Div(children=[scan_layout], style={"margin": 20}),
        dcc.Location(id='url', refresh=False),
        html.Div(id='page-content',
                 children=[dash.page_container],
                 style={"margin": 20},
                 ),
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

    if args.api_cert:
        configure_requests_with_certificate(args.api_cert)

    # - Start the Dash app:
    app = setup_web_app(args.api_host, args.api_port, args.api_prefix, args.proxy)
    app.run(host="0.0.0.0", debug=args.debug, port=8080)


if __name__ == "__main__":
    main()
