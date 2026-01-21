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

Environment variables
---------------------
- ALLOW_PRIVATE_IP: allow the use of private IPs, useful during debug, should not be set to True in production
- CERT_PATH: specify the path to the self-signed certificates.

Usage Examples
--------------
# Run the web interface with default PlantDB REST API settings
$ python app.py

# Connect to a specific PlantDB REST API server
$ python app.py --plantdb-host example-server.local --plantdb-port 5000
"""

import argparse
import os
from pathlib import Path
from threading import Thread

import dash
import dash_bootstrap_components as dbc
import zmq
from dash import Dash
from dash import dcc
from dash import html
from plantdb.client.plantdb_client import PlantDBClient
from plantdb.client.plantdb_client import api_prefix
from plantdb.client.rest_api import PLANTDB_API_HOST
from plantdb.client.rest_api import PLANTDB_API_PORT
from plantdb.client.rest_api import PLANTDB_API_PREFIX
from werkzeug.middleware.proxy_fix import ProxyFix

from plantimager.webui.carousel import caroussel_modal
from plantimager.webui.config import plantdb_cfg_modal
from plantimager.webui.controller_proxy import RPCController
from plantimager.webui.login import login_modal
from plantimager.webui.nav import navbar_layout
from plantimager.webui.new_user import new_user_modal


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
    >>> args = parser.parse_args(['--plantdb-host', '192.168.1.100', '--plantdb-port', '5001', '--plantdb-prefix', '/plantdb'])
    >>> print(f"https://{args.plantdb_host}:{args.plantdb_port}{args.plantdb_prefix}")
    https://192.168.1.100:5001/plantdb
    """
    parser = argparse.ArgumentParser(description="PlantImager WebUI.")

    app_args = parser.add_argument_group("Dash app options")
    app_args.add_argument('--proxy', action='store_true',
                          help="Defines if the application is running behind a reverse proxy.")
    app_args.add_argument('--url-prefix', type=str, default='',
                          help="URL prefix for the application (e.g. should match NGINX location if behind proxy).")

    plantdb_args = parser.add_argument_group("PlantDB REST API options")
    plantdb_args.add_argument('--plantdb-host', type=str, default=PLANTDB_API_HOST,
                              help="Host address of the PlantDB REST API.")
    plantdb_args.add_argument('--plantdb-port', type=int, default=PLANTDB_API_PORT,
                              help="Port of the PlantDB REST API.")
    plantdb_args.add_argument('--plantdb-prefix', type=str, default=PLANTDB_API_PREFIX,
                              help="URL prefix of the PlantDB REST API.")
    plantdb_args.add_argument('--plantdb-ssl', type=bool, default=False,
                              help="Whether the PlantDB REST API is using SSL or not.")

    misc_args = parser.add_argument_group("Miscellaneous options")
    misc_args.add_argument('--debug', action='store_true',
                           help="Enable/disable all the dev tools.")
    return parser


def setup_web_app(plantdb_host: str, plantdb_port: int, plantdb_prefix: str, plantdb_ssl: str,
                  proxy: bool = False, url_prefix: str = '/webui') -> Dash:
    """Initialize and configure the Plant Imager Dash web application.

    Creates a Dash application instance with Bootstrap styling and sets up the main
    layout including navigation bar, modals, and content areas. The application
    is configured with global state storage for REST API connection details,
    user authentication, and dataset management.

    Parameters
    ----------
    plantdb_host : str
        The hostname for the PlantDB REST API server (e.g., 'localhost', '127.0.0.1', 'example.com')
    plantdb_port : int
        The port number for the PlantDB REST API server connection
    plantdb_prefix : str
        URL prefix of the PlantDB REST API server.
    plantdb_ssl : bool
        Whether the PlantDB REST API server is using SSL or not.
    proxy : bool, optional
        Boolean flag indicating whether the application is behind a reverse proxy, by default ``False``.
    url_prefix : str
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
    # Ensure `url_prefix` ends with a trailing slash (as required by Dash)
    if url_prefix and not url_prefix.endswith('/'):
        url_prefix += '/'
    else:
        url_prefix = None

    app = Dash(
        name="plantimager.webui",
        title="Plant Imager WebUI",
        external_stylesheets=[dbc.themes.BOOTSTRAP, dbc.icons.BOOTSTRAP],
        url_base_pathname=url_prefix,
        use_pages=True,
        pages_folder=str(Path(__file__).parent / "pages"),
        assets_folder=str(Path(__file__).parent / "assets"),
    )

    if proxy:
        # App is behind one proxy that sets the -For and -Host headers.
        app.server.wsgi_app = ProxyFix(app.server.wsgi_app, x_for=1, x_host=1, x_proto=1)
        # Set secure cookies
        app.server.config.update(
            SESSION_COOKIE_SECURE=True,  # Only send cookies over HTTPS
            SESSION_COOKIE_HTTPONLY=True,  # Prevent JavaScript access
            SESSION_COOKIE_SAMESITE='Strict'  # CSRF protection
        )

    # Main application layout definition
    app.layout = html.Div([
        # Global state storage
        dcc.Store(id='plantdb-host', data=plantdb_host, storage_type='session'),  # PlantDB REST API URL
        dcc.Store(id='plantdb-port', data=plantdb_port, storage_type='session'),  # PlantDB REST API port
        dcc.Store(id='plantdb-prefix', data=plantdb_prefix, storage_type='session'),  # PlantDB REST API prefix
        dcc.Store(id='plantdb-ssl', data=plantdb_ssl, storage_type='session'),  # PlantDB REST API prefix
        dcc.Store(id='connected', data=None),  # boolean flag indicating if connected to the database or not
        dcc.Store(id='logged-username', data=None, storage_type='session'),  # id of the logger user
        dcc.Store(id='logged-fullname', data=None, storage_type='session'),  # real name of the logged user
        dcc.Store(id='session-token', data=None, storage_type='session'),  # real name of the logged user
        dcc.Store(id='dataset-list', data=[]),  # list of datasets known to the database
        dcc.Store(id='dataset-id', data=None),  # name of the dataset to create (scan operation)
        dcc.Store(id='dataset-dict', data={}, storage_type='session'),
        # dictionary of dataset information, used for AG grid table
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
    - This should be used for development purposes only, refers to the wsgi.py file for production
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

    os.environ["ALLOW_PRIVATE_IP"] = 'true'
    # - Start the Dash app:
    app = setup_web_app(args.plantdb_host, args.plantdb_port, args.plantdb_prefix, args.plantdb_ssl,
                        proxy=args.proxy, url_prefix=args.url_prefix)
    app.run(host="0.0.0.0", debug=args.debug, port=8080)


if __name__ == "__main__":
    main()
