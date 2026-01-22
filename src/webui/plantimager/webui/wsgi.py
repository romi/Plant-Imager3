#!/usr/bin/env python
# -*- coding: utf-8 -*-


"""WSGI Entry Point for Plant Imager Web Interface

This module provides the WSGI entry point to run the Plant Imager web application using a WSGI-compatible server.
It sets up the Dash web application and configures it to connect with the REST API backend.

Key Features
------------
- Configures and initializes the Plant Imager Dash application for WSGI deployment
- Sets up the correct URL base path name for the application
- Allows for custom configuration of the server host, port, and proxy settings

Environment variables
---------------------
- ALLOW_PRIVATE_IP: if `True`, allow the use of private IPs for PlantDB REST API URL
- CERT_PATH: specify the path to the self-signed certificates used by the PlantDB server.
- VALIDATE_HOST: if `True`, check the PlantDB REST API URL against a blacklist

Usage Examples
--------------
Run the web interface with default REST API settings using a WSGI server like uWSGI
```shell
uwsgi --http :8080 --module plantimager.webui.wsgi:application --callable application --master
```

Run with Gunicorn
```shell
gunicorn wsgi:application
```

Direct call with Python for development purposes:
```shell
python src/webui/plantimager/webui/wsgi.py
```
Should then be accessible under: https://localhost:8080/webui/
"""
import os
from threading import Thread

import zmq
from dotenv import load_dotenv

from plantimager.webui.app import setup_web_app
from plantimager.webui.controller_proxy import RPCController

# - Create connexion with controller
context = zmq.Context()
controller_thread = Thread(target=lambda ctx: RPCController(ctx, "tcp://localhost:14567"), args=(context,))
controller_thread.daemon = True
controller_thread.start()

# Load environment variables from an `.env` file if present
load_dotenv()

# Get configuration from environment variables
app_config = {
    'plantdb_host': os.getenv('PLANTDB_HOST', 'localhost'),
    'plantdb_port': int(os.getenv('PLANTDB_PORT', 5000)),
    'plantdb_prefix': os.getenv('PLANTDB_PREFIX', '').lower(),
    'plantdb_ssl': os.getenv('PLANTDB_SSL', 'false').lower() == 'true',
    'proxy': os.getenv('WEBUI_PROXY', 'false').lower() == 'true',
    'url_prefix': os.getenv('WEBUI_PREFIX', '/webui'),
}

# Get the Dash application
dash_app = setup_web_app(**app_config)
# Use the Flask server attribute of the Dash application
application = dash_app.server

if __name__ == "__main__":
    from werkzeug.serving import run_simple

    run_config = {
        'hostname': os.getenv('WEBUI_HOST', '0.0.0.0'),
        'port': int(os.getenv('WEBUI_PORT', 8080)),
        'application': application,
        # Set an SSL context only if SSL is enabled
        'ssl_context': os.getenv('CERT_PATH', '/etc/nginx/ssl/cert.pem') if app_config['plantdb_ssl'] else None,
        'use_debugger': bool(os.getenv('WEBUI_DEBUG', False)),
    }
    run_simple(**run_config)
